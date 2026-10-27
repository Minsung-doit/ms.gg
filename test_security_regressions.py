"""
Security regression suite (2026-10-24 audit fixes)

Each check reproduces an attack that worked before the fix and asserts it is now blocked.
"""
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from test_support import sandbox_env_writes, admin_client, riot_http, use_temp_db

sandbox_env_writes()
use_temp_db()

from app.main import app
from app.config import settings
from app.admin_auth import generate_admin_token, verify_admin_token
import app.services.discord_service as discord_service

BASE_DIR = Path(__file__).resolve().parent
_ip_counter = [0]


def fresh_client(admin_port: bool = False, **kwargs) -> TestClient:
    """Each call looks like a different remote visitor (separate rate-limit buckets).
    admin_port=True sends requests to the admin listener; otherwise they hit the public port."""
    _ip_counter[0] += 1
    if admin_port:
        kwargs.setdefault("base_url", f"http://testserver:{settings.admin_port}")
    return TestClient(app, client=(f"203.0.113.{_ip_counter[0]}", 40000), **kwargs)


def ok(msg):
    print(f"  [PASS] {msg}")


ADMIN_ONLY_ENDPOINTS = [
        ("get", "/api/finance/summary"),
        ("get", "/api/settings/telegram-status"),
        ("get", "/api/settings/discord-status"),
        ("get", "/api/settings/lol-client-path"),
        ("get", "/api/telegram/photos"),
        ("post", "/api/cache/clear"),
        ("post", "/api/settings/api-key"),
        ("post", "/api/admin/db/optimize"),
]


def test_admin_endpoints_require_login():
    admin, public = fresh_client(admin_port=True), fresh_client()
    bodies = {"/api/settings/api-key": {"api_key": "RGAPI-00000000-0000-0000-0000-000000000000"}}
    for method, path in ADMIN_ONLY_ENDPOINTS:
        extra = {"json": bodies[path]} if path in bodies else {}
        res = getattr(admin, method)(path, **extra)
        assert res.status_code == 401, f"admin port {method.upper()} {path} -> {res.status_code} (expected 401)"
        res = getattr(public, method)(path, **extra)
        assert res.status_code == 404, f"public port {method.upper()} {path} -> {res.status_code} (expected 404)"
    ok(f"관리자 API {len(ADMIN_ONLY_ENDPOINTS)}종: 관리자 포트 비로그인 401, 공개 포트 404")


def test_admin_console_only_on_admin_port():
    public = fresh_client()
    assert public.get("/admin").status_code == 404
    assert public.post("/api/admin/login", json={"username": "admin", "password": "x"}).status_code == 404
    # 정적 파일 주소의 ?v=<초> 는 요청 시각마다 달라지므로 비교에서 뺀다
    strip_ver = lambda html: re.sub(r"\?v=\d+", "", html)
    index_html = strip_ver(public.get("/").text)
    for res in (public.get("/?mode=admin"), public.get("/", headers={"Host": "admin.localhost"}),
                public.get("/", headers={"Host": f"localhost:{settings.admin_port}"})):
        assert res.status_code == 200 and strip_ver(res.text) == index_html, "public port served the admin console"
    admin = fresh_client(admin_port=True)
    assert admin.get("/admin").status_code == 200
    assert admin.get("/").text != index_html
    # Gemini 파이프라인을 원격으로 띄우던 API는 삭제됨
    assert fresh_client(admin_port=True, cookies={"admin_session": generate_admin_token(settings.admin_username)})         .post("/api/admin/pipeline/trigger").status_code in (404, 405)
    ok("관리자 콘솔은 관리자 포트에서만 (Host 헤더·?mode=admin 우회 차단, 파이프라인 실행 API 삭제)")


def test_no_password_in_query_and_no_loopback_bypass():
    # Old: ?admin_key=<password> logged in; loopback + Host: x:300 skipped auth entirely
    c = TestClient(app, client=("127.0.0.1", 40000), base_url=f"http://testserver:{settings.admin_port}")
    res = c.post(f"/api/cache/clear?admin_key={settings.admin_password}", headers={"Host": "localhost:300"})
    assert res.status_code == 401, res.status_code
    ok("URL 비밀번호 로그인 / 루프백+포트 우회 차단")


def test_tokens_are_signed_and_expire():
    good = generate_admin_token(settings.admin_username)
    assert verify_admin_token(good)
    user, exp, sig = good.rsplit(".", 2)
    assert not verify_admin_token(f"{user}.{int(exp) + 999999}.{sig}"), "tampered expiry accepted"
    assert not verify_admin_token(generate_admin_token(settings.admin_username, ttl=-1)), "expired token accepted"
    assert not verify_admin_token("logged_out")
    assert fresh_client(admin_port=True, cookies={"admin_session": good}).post("/api/cache/clear").status_code == 200

    original = settings.admin_password
    try:
        settings.admin_password = original + "-rotated"
        assert not verify_admin_token(good), "token survived password change"
    finally:
        settings.admin_password = original
    ok("서명 토큰 위조/만료 거부, 비밀번호 변경 시 기존 토큰 무효화")


def test_no_hardcoded_default_password():
    assert settings.admin_password != "opgg2026!"
    assert settings.admin_token_secret != "lolgg-admin-super-secret-token-key-2026"
    config_src = (BASE_DIR / "app" / "config.py").read_text(encoding="utf-8")
    assert "opgg2026!" not in config_src
    ok("기본 관리자 비밀번호/시크릿 하드코딩 제거")


def test_login_bruteforce_lockout():
    c = fresh_client(admin_port=True)
    codes = [c.post("/api/admin/login", json={"username": "admin", "password": f"wrong{i}"}).status_code for i in range(6)]
    assert codes[:5] == [401] * 5, codes
    assert codes[5] == 429, codes
    # Even the correct password is refused while locked out
    res = c.post("/api/admin/login", json={"username": settings.admin_username, "password": settings.admin_password})
    assert res.status_code == 429
    ok("로그인 5회 실패 시 잠금 (429)")


def test_admin_login_flow():
    c = fresh_client(admin_port=True)
    res = c.post("/api/admin/login", json={"username": settings.admin_username, "password": settings.admin_password})
    token = res.json()["token"]
    assert res.status_code == 200 and verify_admin_token(token)
    assert c.get("/api/finance/summary").status_code == 200
    c.post("/api/admin/logout")
    assert c.get("/api/finance/summary").status_code == 401
    # A copied token must not outlive the logout (Gemini cross-review finding)
    stolen = fresh_client(admin_port=True).get("/api/finance/summary", headers={"Authorization": f"Bearer {token}"})
    assert stolen.status_code == 401, stolen.status_code
    ok("정상 로그인 → 관리자 API 접근 → 로그아웃 후 복사된 토큰까지 차단")


def _duo_payload(**over):
    payload = {
        "game_name": "Tester", "tag_line": "KR1", "tier_kr": "골드",
        "my_position": "MID", "target_position": "JUG", "queue_type": "솔로랭크",
        "voice": True, "title": "듀오 구해요", "description": "테스트",
        "most_champions": ["아리"],
    }
    payload.update(over)
    return payload


def test_duo_post_rejects_malicious_links():
    c = fresh_client()
    for bad in ["javascript:alert(1)", "https://evil.example.com/discord.gg", "http://discord.gg/x"]:
        res = c.post("/api/duo-posts", json=_duo_payload(room_link=bad))
        assert res.status_code == 422, f"{bad} -> {res.status_code}"
    ok("듀오 글 비디스코드/javascript: 링크 거부 (422)")


def test_duo_post_xss_champion_names_dropped():
    c = fresh_client()
    evil = "x');alert(document.cookie)//"
    res = c.post("/api/duo-posts", json=_duo_payload(most_champions=[evil, "<img src=x onerror=alert(1)>", "아리"]))
    assert res.status_code == 200, res.text
    post = res.json()["post"]
    assert post["most_champions"] == ["아리"], post["most_champions"]
    ok("듀오 글 챔피언 칸 스크립트 주입 제거 (실존 챔피언만 저장)")


def test_duo_post_accepts_english_champion_ids():
    res = fresh_client().post("/api/duo-posts", json=_duo_payload(most_champions=["Ahri", "Yasuo"]))
    assert res.status_code == 200 and len(res.json()["post"]["most_champions"]) == 2, res.text
    ok("듀오 글 영문 챔피언 ID(Ahri, Yasuo)도 정상 인식")


def test_spectator_bat_command_injection_blocked():
    c = fresh_client()
    for path in [
        '/api/spectator/download-bat/12345" & calc.exe & rem "',
        "/api/spectator/download-bat/12345?encryption_key=x%22%20%26%20calc%20%26%20rem",
        "/api/spectator/script/1;Start-Process calc",
    ]:
        assert c.get(path).status_code == 400, path
    res = c.get("/api/spectator/download-bat/7182900123?encryption_key=abcDEF123%2B%2F%3D")
    assert res.status_code == 200 and b"7182900123" in res.content and b"abcDEF123+/=" in res.content
    ok("관전 .bat/PowerShell 스크립트 명령 주입 차단 (게임 ID·키 형식 검증)")


def test_duo_toggle_requires_owner():
    c = fresh_client()
    res = c.post("/api/duo-posts", json=_duo_payload())
    body = res.json()
    post_id, token = body["post"]["id"], body["owner_token"]

    listing = c.get("/api/duo-posts").text
    assert token not in listing, "owner token leaked in listing"
    assert fresh_client().post(f"/api/duo-posts/{post_id}/toggle-status").status_code == 403
    assert fresh_client().post(f"/api/duo-posts/{post_id}/toggle-status", headers={"X-Duo-Owner-Token": "guess"}).status_code == 403
    assert c.post(f"/api/duo-posts/{post_id}/toggle-status", headers={"X-Duo-Owner-Token": token}).status_code == 200
    ok("듀오 글 상태 변경은 작성자 토큰 보유자만 가능 (타인 403)")


def test_duo_post_rate_limit():
    c = fresh_client()
    codes = [c.post("/api/duo-posts", json=_duo_payload()).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429], codes
    ok("듀오 글 도배 제한 (10분 3건)")


def test_discord_webhook_blocks_mass_mentions():
    sent = {}

    class FakeResp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        sent["body"] = req.data.decode("utf-8")
        return FakeResp()

    original = discord_service.urllib.request.urlopen
    discord_service.urllib.request.urlopen = fake_urlopen
    try:
        discord_service.send_discord_webhook({"content": "@everyone 공짜 스킨"}, webhook_url="https://discord.com/api/webhooks/1/x")
    finally:
        discord_service.urllib.request.urlopen = original
    import json as _json
    am = _json.loads(sent["body"])["allowed_mentions"]
    assert am.get("parse") == [] and not am.get("roles") and not am.get("users"), am
    # 호출하는 쪽이 역할 ID를 넘겨도 숫자 ID만 통과 (문자열 '@everyone' 같은 값은 버림)
    discord_service.urllib.request.urlopen = fake_urlopen
    try:
        discord_service.send_discord_webhook({"content": "x", "allowed_mentions": {"parse": ["everyone"], "roles": ["@everyone", "123"]}},
                                             webhook_url="https://discord.com/api/webhooks/1/x")
    finally:
        discord_service.urllib.request.urlopen = original
    am = _json.loads(sent["body"])["allowed_mentions"]
    assert am == {"parse": [], "roles": ["123"]}, am
    ok("디스코드 웹훅 @everyone/@here 멘션 차단 (설정한 숫자 역할 ID만 허용)")


def test_discord_share_rate_limit():
    original = settings.discord_webhook_url
    settings.discord_webhook_url = ""  # never post to the real channel from tests
    try:
        c = fresh_client()
        codes = [c.post("/api/discord/share/player", json={"player": {}, "summary": {}}).status_code for _ in range(6)]
    finally:
        settings.discord_webhook_url = original
    assert codes == [200] * 5 + [429], codes
    ok("디스코드 공유 버튼 채널 도배 제한 (10분 5건)")


def test_riot_quota_protected():
    from app.rate_limit import leaderboard_sync_limiter
    leaderboard_sync_limiter.hit("global")  # simulate a sync that just ran (no real Riot calls in tests)
    assert fresh_client().post("/api/leaderboard/sync").status_code == 429
    ok("래더 동기화 서버 전체 5분 1회 제한 (Riot API 할당량 보호)")


def test_public_page_and_uploads():
    c = fresh_client()
    assert c.get("/api/settings/status").json().get("masked_key") == ""
    assert c.get("/uploads/telegram/anything.jpg").status_code == 404
    ok("공개 페이지에 API 키 일부 비노출, 텔레그램 업로드 비공개")


def test_no_unsafe_inline_handler_args():
    js = "\n".join(f.read_text(encoding="utf-8") for f in sorted((BASE_DIR / "static" / "js" / "app").glob("*.js")))
    unsafe = re.findall(r"on(?:click|change|keydown)=\"[^\"]*'\$\{", js)
    assert not unsafe, f"{len(unsafe)} inline handlers still interpolate '${{...}}' strings"
    assert "function jsArg(" in js
    ok("인라인 onclick 문자열 인자 전부 jsArg() 이스케이프 적용")


def test_telegram_bot_does_not_auto_pair():
    src = (BASE_DIR / "scripts" / "telegram_bot.py").read_text(encoding="utf-8")
    assert "update_telegram_config(chat_id=chat_id)" not in src
    ok("텔레그램 봇 미등록 채팅 자동 페어링 제거")


def test_ai_pipeline_removed():
    # 권한 확인 없이 AI가 코드를 고치던 사내 파이프라인과 키 자동 재발급 스크립트는 삭제됐다
    for rel in ("run_company_pipeline.py", "create_cli_shortcut.py", "setup_shortcuts.py",
                "scripts/legacy/auto_renew_riot_key.py", "company"):
        assert not (BASE_DIR / rel).exists(), rel
    c = fresh_client(admin_port=True, cookies={"admin_session": generate_admin_token(settings.admin_username)})
    assert c.get("/api/company/artifact", params={"path": "CLAUDE.md"}).status_code == 404
    ok("AI 파이프라인·키 자동 재발급 스크립트·산출물 파일 조회 API 제거")


def test_riot_id_cannot_rewrite_riot_api_path():
    import httpx
    from app.riot_client import riot_client

    paths = []

    def riot(req):
        paths.append(req.url.raw_path.decode())
        return httpx.Response(403, json={})  # 라이엇은 없는 경로에 403을 준다

    saved_key = settings.riot_api_key
    settings.riot_api_key = "RGAPI-test-key"
    riot_client.reset_key_status()
    try:
        with riot_http(riot):
            c = fresh_client()
            for q in ("#", "a/b#KR1", "x#KR1/../../../../lol/status/v4/platform-data", "a?b#KR1", "닉#"):
                assert c.get("/api/search", params={"q": q}).json()["mode"] == "not_found", q
                assert not riot_client.is_expired, f"검색어 {q!r} 하나로 키가 만료 처리되면 안 됨"
            c.get("/api/search", params={"q": "Hide on bush#KR1"})
    finally:
        settings.riot_api_key = saved_key
        riot_client.reset_key_status()
    # 정상 경로의 403 뒤에는 키 확인용 상태 API 1회만 추가된다
    assert paths == ["/riot/account/v1/accounts/by-riot-id/Hide%20on%20bush/KR1",
                     "/lol/status/v4/platform-data"], paths
    ok("검색어로 라이엇 API 경로 조작·키 만료 유발 차단 (닉네임/태그 인코딩·검증)")


def test_public_status_poll_keeps_429_backoff():
    import asyncio
    import httpx
    from app.riot_client import riot_client
    from app.sync_automation_engine import rate_limiter

    saved_key = settings.riot_api_key
    settings.riot_api_key = "RGAPI-test-key"
    riot_client.reset_key_status()
    rate_limiter.handle_status(429, retry_after=60)
    backoff = rate_limiter.backoff_until
    try:
        with riot_http(lambda req: httpx.Response(200, json={})):
            assert asyncio.run(riot_client.verify_key())["valid"]
        assert rate_limiter.backoff_until == backoff, "공개 상태 조회가 429 백오프를 지우면 안 됨"
    finally:
        settings.riot_api_key = saved_key
        riot_client.reset_key_status()
    ok("키 상태 확인(공개 /api/settings/status)이 라이엇 429 백오프를 초기화하지 않음")


def test_endpoint_403_does_not_expire_valid_key():
    import asyncio
    import httpx
    from app.riot_client import riot_client

    def riot(status_code):
        def handler(req):
            if req.url.path == "/lol/status/v4/platform-data":
                return httpx.Response(status_code, json={})
            return httpx.Response(403, json={})  # 이 키로 못 쓰는 엔드포인트
        return handler

    saved_key = settings.riot_api_key
    settings.riot_api_key = "RGAPI-test-key"
    url = f"https://{riot_client.region}.api.riotgames.com/lol/spectator/v5/featured-games"
    try:
        riot_client.reset_key_status()
        with riot_http(riot(200)):
            assert asyncio.run(riot_client._request("GET", url)).status_code == 403
        assert not riot_client.is_expired, "키가 유효한데 엔드포인트 403 하나로 1시간 차단되면 안 됨"
        riot_client.reset_key_status()
        with riot_http(riot(403)):
            asyncio.run(riot_client._request("GET", url))
        assert riot_client.is_expired, "상태 API도 거부하면 키 만료로 처리"
    finally:
        settings.riot_api_key = saved_key
        riot_client.reset_key_status()
    ok("엔드포인트 권한 403은 키 만료로 처리하지 않음 (상태 API로 확인)")


def test_search_champion_name_opens_build_without_riot_call():
    import httpx
    calls = []
    saved_key = settings.riot_api_key
    settings.riot_api_key = "RGAPI-test-key"
    try:
        with riot_http(lambda req: calls.append(req.url.raw_path.decode()) or httpx.Response(404, json={})):
            c = fresh_client()
            res = c.get("/api/search", params={"q": "아리"}).json()
            assert res["mode"] == "champion_build" and res["champion"]["id"] == "Ahri", res
            assert c.get("/api/search", params={"q": "ahri"}).json()["mode"] == "champion_build"
            assert c.get("/api/autocomplete", params={"q": "아리"}).json()["champion"]["id"] == "Ahri"
            # 태그를 붙이면 소환사 검색
            assert c.get("/api/search", params={"q": "아리#KR1"}).json()["mode"] == "not_found"
    finally:
        settings.riot_api_key = saved_key
    assert calls == ["/riot/account/v1/accounts/by-riot-id/%EC%95%84%EB%A6%AC/KR1"], calls
    ok("챔피언 이름 검색은 소환사 KR1 조회 없이 챔피언 빌드로 연결")


def test_community_tips_anonymous_and_admin_deletable():
    c = fresh_client()
    res = c.post("/api/community-counters", json={
        "champ1": "야스오", "champ2": "요네", "category": "skill", "position": "MID",
        "content": "요네 E 복귀 위치를 보고 장막을 까세요.",
        "author_name": "Faker", "author_tag": "KR1", "author_tier": "챌린저",
    })
    assert res.status_code == 200, res.text
    tips = c.get("/api/community-counters", params={"champ1": "야스오", "champ2": "요네"}).json()["tips"]
    mine = [t for t in tips if "장막" in t["content"]]
    assert mine and mine[0]["author_name"] == "익명 소환사" and mine[0]["author_tier"] == "", "이름·티어 사칭 불가"
    tip_id = mine[0]["id"]
    assert c.delete(f"/api/admin/community-counters/{tip_id}").status_code in (401, 403, 404), "공개 포트·비로그인 삭제 불가"
    admin = fresh_client(admin_port=True, cookies={"admin_session": generate_admin_token(settings.admin_username)})
    assert admin.delete(f"/api/admin/community-counters/{tip_id}").status_code == 200
    assert not [t for t in c.get("/api/community-counters", params={"champ1": "야스오"}).json()["tips"] if t["id"] == tip_id]
    ok("커뮤니티 공략: 모든 글 익명(이름·티어 사칭 불가), 관리자만 삭제")


def test_seo_pages_escape_and_404():
    c = fresh_client()
    page = c.get("/champion/ahri")
    assert page.status_code == 200 and "<title>아리 빌드" in page.text and 'rel="canonical" href="/champion/ahri"' in page.text
    assert c.get("/champion/%EC%95%84%EB%A6%AC").text.count('/champion/ahri"') >= 2, "한글 주소도 영문 대표 주소로"
    assert c.get("/champion/nope").status_code == 404
    evil = c.get("/summoner/%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E-KR1")
    head = evil.text.split("</head>")[0]
    assert evil.status_code == 200 and "<img src=x" not in head and "&lt;img src=x" in head, "닉네임은 HTML 이스케이프"
    sitemap = c.get("/sitemap.xml").text
    assert "/champion/ahri</loc>" in sitemap and "?tab=protracker" not in sitemap
    ok("챔피언·소환사 주소: 제목·대표 주소·404, 닉네임 이스케이프, 사이트맵")


def test_traffic_counts_pages_without_storing_ip():
    from app.database import get_connection
    browser = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130.0"}
    c = fresh_client()
    for path in ("/", "/", "/champion/ahri"):
        c.get(path, headers=browser)
    c.get("/", headers={"User-Agent": "Googlebot/2.1"})
    assert c.get("/api/admin/traffic").status_code in (401, 403, 404), "공개 포트에서 통계 비공개"
    admin = fresh_client(admin_port=True, cookies={"admin_session": generate_admin_token(settings.admin_username)})
    today = admin.get("/api/admin/traffic").json()["days"][0]
    assert today["home"] >= 2 and today["champion"] >= 1 and today["visitors"] >= 1, today
    conn = get_connection()
    stored = " ".join(r[0] for r in conn.execute("SELECT visitor FROM traffic_visitors").fetchall())
    conn.close()
    assert "testclient" not in stored and "127.0.0.1" not in stored, "IP 원문을 저장하지 않음"
    ok("방문자 통계: 페이지 조회·순 방문자(일별 해시, IP 미저장), 봇 제외, 관리자만 조회")


def test_discord_member_login_gate():
    import os
    import httpx
    from urllib.parse import parse_qs, urlparse
    env = {"MEMBER_LOGIN": "discord", "DISCORD_CLIENT_ID": "111", "DISCORD_CLIENT_SECRET": "sec",
           "DISCORD_GUILD_ID": "999", "SITE_URL": ""}
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    guilds = {"value": [{"id": "999"}]}  # 지정 서버(999)가 있으면 멤버 정보 200, 없으면 404

    def discord(req):
        if req.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if req.url.path.endswith("/users/@me"):
            return httpx.Response(200, json={"id": "424242", "username": "member"})
        if req.url.path.endswith("/users/@me/guilds/999/member"):
            if any(g["id"] == "999" for g in guilds["value"]):
                return httpx.Response(200, json={"nick": "서버별명", "user": {"id": "424242"}})
            return httpx.Response(404, json={"message": "Unknown Guild"})
        return httpx.Response(404)

    try:
        c = fresh_client(follow_redirects=False)
        r = c.get("/champion/ahri")
        assert r.status_code == 302 and r.headers["location"].startswith("/login?next=%2Fchampion%2Fahri"), r.headers
        assert c.get("/api/tierlist").status_code == 401
        assert c.get("/login").status_code == 200 and "디스코드로 로그인" in c.get("/login").text
        assert c.get("/robots.txt").text.strip().endswith("Disallow: /")
        assert c.get("/sitemap.xml").status_code in (302, 404), "사이트맵 비공개"

        # 외부 주소로 돌려보내는 next 는 무시
        start = c.get("/auth/discord/login", params={"next": "//evil.example/x"})
        q = parse_qs(urlparse(start.headers["location"]).query)
        assert q["scope"] == ["identify guilds.members.read"] and q["client_id"] == ["111"]
        state = q["state"][0]
        assert start.cookies.get("discord_oauth_state", "").strip('"').endswith("|/"), "외부 next 거부"

        # state 위조 → 거부
        bad = c.get("/auth/discord/callback", params={"code": "x", "state": "forged"})
        assert bad.headers["location"] == "/login?error=state"

        with riot_http(discord):
            guilds["value"] = [{"id": "123"}]
            c.cookies.set("discord_oauth_state", f"{state}|/champion/ahri")
            nm = c.get("/auth/discord/callback", params={"code": "x", "state": state})
            assert nm.headers["location"] == "/login?error=member" and "member_session" not in nm.cookies, "서버 멤버가 아니면 거부"

            guilds["value"] = [{"id": "999"}]
            c.cookies.set("discord_oauth_state", f"{state}|/champion/ahri")
            ok_res = c.get("/auth/discord/callback", params={"code": "x", "state": state})
        assert ok_res.headers["location"] == "/champion/ahri" and ok_res.cookies.get("member_session")
        c.cookies.set("member_session", ok_res.cookies.get("member_session"))
        page = c.get("/champion/ahri")
        assert page.status_code == 200 and page.headers.get("x-robots-tag") == "noindex, nofollow"
        from app import community_rank
        assert (community_rank.get_member("424242") or {}).get("discord_name") == "서버별명", "서버 별명을 표시 이름으로"

        forged = fresh_client(follow_redirects=False, cookies={"member_session": "424242.9999999999.deadbeef"})
        assert forged.get("/").status_code == 302, "서명이 틀린 쿠키 거부"
        admin = fresh_client(admin_port=True, cookies={"admin_session": generate_admin_token(settings.admin_username)})
        assert admin.get("/api/admin/traffic").status_code == 200, "관리자 포트는 디스코드 로그인과 무관"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    assert fresh_client().get("/").status_code == 200, "MEMBER_LOGIN 을 끄면 다시 열림"
    ok("디스코드 멤버 전용: 비로그인 차단(페이지 302·API 401), state·오픈 리다이렉트·위조 쿠키 거부, 비멤버 거부, 색인 금지")


def test_cache_stats_hide_searched_names():
    from app.cache_engine import fast_cache
    fast_cache.set("autocomplete:다른사람검색", {"x": 1}, ttl=60)
    assert "active_keys" not in fresh_client().get("/api/cache/stats").json()
    assert "autocomplete:다른사람검색" in admin_client(app).get("/api/cache/stats").json()["active_keys"]
    ok("캐시 통계의 키 목록(다른 방문자 검색어)은 관리자에게만 노출")


def test_discord_join_click_rate_limit():
    c = fresh_client()
    codes = [c.post("/api/duo-posts/1/discord-join").status_code for _ in range(31)]
    assert codes == [200] * 30 + [429], codes
    ok("디스코드 입장 클릭 통계 부풀리기 제한 (1분 30건)")


def test_db_optimize_targets_app_database():
    real_db = BASE_DIR / "opgg.db"
    before = real_db.stat().st_mtime_ns if real_db.exists() else None
    res = admin_client(app).post("/api/admin/db/optimize").json()
    assert res["success"], res
    after = real_db.stat().st_mtime_ns if real_db.exists() else None
    assert before == after, "테스트(임시 DB) 중에 실제 opgg.db를 만들거나 VACUUM하면 안 됨"
    ok("DB 최적화는 앱이 쓰는 DB(테스트에서는 임시 DB)를 대상으로 실행")



def test_bot_api_requires_secret():
    """디스코드 봇 전용 경로: 비밀값이 없으면 꺼짐(503), 틀리면 403, 맞으면 디스코드 사용자 이름으로 글·참가"""
    import os
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    body = {"game": "lol", "game_name": "봇테스트", "tag_line": "KR1", "tier_kr": "골드", "my_position": "MID",
            "target_position": "ALL", "queue_type": "자유랭크", "title": "봇 글",
            "member": {"discord_id": "1234567890", "discord_name": "디코유저"}}
    saved = os.environ.get("BOT_API_SECRET")
    try:
        os.environ.pop("BOT_API_SECRET", None)
        assert c.post("/api/bot/duo-posts", json=body).status_code == 503
        os.environ["BOT_API_SECRET"] = "s" * 32
        assert c.post("/api/bot/duo-posts", json=body).status_code == 403
        assert c.post("/api/bot/duo-posts", json=body, headers={"X-Bot-Secret": "wrong"}).status_code == 403
        bad = dict(body, member={"discord_id": "abc", "discord_name": "x"})
        assert c.post("/api/bot/duo-posts", json=bad, headers={"X-Bot-Secret": "s" * 32}).status_code == 422
        r = c.post("/api/bot/duo-posts", json=body, headers={"X-Bot-Secret": "s" * 32})
        assert r.status_code == 200 and r.json()["post"]["author"] == "디코유저" and "owner_token" not in r.json()
        pid = r.json()["post"]["id"]
        m = {"discord_id": "222", "discord_name": "참가자"}
        assert c.post(f"/api/bot/duo-posts/{pid}/join", json=m).status_code == 403
        j = c.post(f"/api/bot/duo-posts/{pid}/join", json=m, headers={"X-Bot-Secret": "s" * 32})
        assert j.status_code == 200 and j.json()["status"] == "ok" and j.json()["post"]["joiner_names"] == ["참가자"]
        again = c.post(f"/api/bot/duo-posts/{pid}/join", json=m, headers={"X-Bot-Secret": "s" * 32})
        assert again.json()["status"] == "already", "같은 디스코드 사용자는 한 번만"
        # 봇이 붙이는 음성 채널 링크는 화이트리스트 통과, 롤은 포지션 필수
        voice = dict(body, member={"discord_id": "999000", "discord_name": "v"},
                     discord_voice_url="https://discord.com/channels/111/222", discord_channel_name="내전방")
        v = c.post("/api/bot/duo-posts", json=voice, headers={"X-Bot-Secret": "s" * 32})
        assert v.status_code == 200 and v.json()["post"]["discord_voice_url"] == "https://discord.com/channels/111/222", v.text
        nopos = dict(body, member={"discord_id": "999001", "discord_name": "n"}, my_position="ALL")
        assert c.post("/api/bot/duo-posts", json=nopos, headers={"X-Bot-Secret": "s" * 32}).status_code == 422
        # 작성자 멤버: 자기 글 참가 불가, 내 글 목록, 남은 못 바꾸고 작성자는 마감·삭제 가능
        H = {"X-Bot-Secret": "s" * 32}
        me, other = {"discord_id": "1234567890", "discord_name": "디코유저"}, {"discord_id": "555", "discord_name": "남"}
        own = c.post(f"/api/bot/duo-posts/{pid}/join", json=me, headers=H)
        assert own.status_code == 409 and "내가 올린" in own.json()["detail"], own.text
        mine = c.post("/api/bot/duo-posts/mine", json=me, headers=H).json()["posts"]
        assert any(p["id"] == pid for p in mine) and all("owner_k" not in p for p in mine)
        assert c.post(f"/api/bot/duo-posts/{pid}/toggle", json=other, headers=H).status_code == 403
        assert c.post(f"/api/bot/duo-posts/{pid}/delete", json=other, headers=H).status_code == 403
        t = c.post(f"/api/bot/duo-posts/{pid}/toggle", json=me, headers=H)
        assert t.status_code == 200 and t.json()["post"]["is_full"] is True, t.text
        assert c.post(f"/api/bot/duo-posts/{pid}/delete", json=me, headers=H).status_code == 200
        assert all(p["id"] != pid for p in c.get("/api/duo-posts?game=lol").json()["posts"])
        # 웹: 로그인 기능이 꺼져 있으면 '내 글'은 빈 목록 (IP 로 남의 글을 관리하지 않음)
        assert c.get("/api/duo-posts/mine").json() == {"ids": []}
    finally:
        if saved is None:
            os.environ.pop("BOT_API_SECRET", None)
        else:
            os.environ["BOT_API_SECRET"] = saved
    ok("디스코드 봇 전용 경로: 비밀값 없으면 꺼짐, 틀리면 거절, 사용자별 1회 참가")


def test_member_gate_lets_only_bot_secret_through():
    """멤버 로그인을 켜면 로그인 없는 API는 401, 올바른 봇 비밀값만 통과 (틀린 값·짧은 설정값은 안 됨)"""
    import os
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    saved = {k: os.environ.get(k) for k in ("MEMBER_LOGIN", "BOT_API_SECRET", "DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_GUILD_ID", "MEMBER_SESSION_SECRET")}
    try:
        os.environ.update(MEMBER_LOGIN="discord", DISCORD_CLIENT_ID="1", DISCORD_CLIENT_SECRET="x" * 20,
                          DISCORD_GUILD_ID="2", MEMBER_SESSION_SECRET="y" * 40, BOT_API_SECRET="z" * 32)
        assert c.get("/api/duo-posts").status_code == 401
        assert c.get("/api/duo-posts", headers={"X-Bot-Secret": "wrong"}).status_code == 401
        assert c.get("/api/duo-posts", headers={"X-Bot-Secret": "z" * 32}).status_code == 200
        assert c.get("/", headers={"X-Bot-Secret": "z" * 32}, follow_redirects=False).status_code == 302, "봇 비밀값은 API만"
        os.environ["BOT_API_SECRET"] = "short"
        assert c.get("/api/duo-posts", headers={"X-Bot-Secret": "short"}).status_code == 401, "16자 미만 설정은 무효"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ok("멤버 전용 사이트: 로그인 없으면 401, 봇 비밀값(API만)만 통과")


if __name__ == "__main__":
    print("=" * 80)
    print("🛡️ [Security Regression Suite] 2026-10-24 보안 감사 수정사항 회귀 검증")
    print("=" * 80)
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print("=" * 80)
    print(f"🎉 보안 회귀 테스트 {len(tests)}개 전부 통과")
    print("=" * 80)
