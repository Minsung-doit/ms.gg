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



def test_riot_sign_on_account_verification():
    """라이엇 공식 로그인(RSO): state 위조 거부, 로그인한 본인 puuid 만 연결, 같은 계정의 이전 연결 해제, 닉네임 입력 연결 없음"""
    import os
    import httpx
    from urllib.parse import parse_qs, urlparse
    from app import community_rank
    saved = {k: os.environ.get(k) for k in ("RSO_CLIENT_ID", "RSO_CLIENT_SECRET", "SITE_URL", "MEMBER_LOGIN")}
    os.environ.pop("MEMBER_LOGIN", None)  # 로컬 모드: 멤버 ID = local-dev
    real_puuid = "p" * 78
    calls = []

    def riot(req):
        calls.append(req.url.path)
        if req.url.host == "auth.riotgames.com" and req.url.path == "/token":
            assert req.headers.get("authorization", "").startswith("Basic "), "클라이언트 비밀값은 Basic 인증으로"
            return httpx.Response(200, json={"access_token": "user-tok"})
        if req.url.path.endswith("/riot/account/v1/accounts/me"):
            assert req.headers.get("authorization") == "Bearer user-tok"
            return httpx.Response(200, json={"puuid": real_puuid, "gameName": "진짜주인", "tagLine": "KR1"})
        return httpx.Response(404, json={})

    try:
        os.environ.pop("RSO_CLIENT_ID", None)
        os.environ.pop("RSO_CLIENT_SECRET", None)
        c = fresh_client(follow_redirects=False)
        assert c.get("/auth/riot/login").headers["location"].endswith("riot_link=off"), "설정 없으면 꺼짐"
        assert c.get("/api/me").json()["riot_login_enabled"] is False

        # 같은 계정을 예전에 다른 디스코드 멤버(부계정 등)가 인증해 둔 상태
        community_rank.link_account("old-discord", {"puuid": real_puuid, "game_name": "진짜주인", "tag_line": "KR1"})

        os.environ.update(RSO_CLIENT_ID="carry-client", RSO_CLIENT_SECRET="s" * 32, SITE_URL="")
        assert c.get("/api/me").json()["riot_login_enabled"] is True

        start = c.get("/auth/riot/login")
        loc = urlparse(start.headers["location"])
        q = parse_qs(loc.query)
        assert loc.netloc == "auth.riotgames.com" and q["client_id"] == ["carry-client"] and q["scope"] == ["openid"]
        assert q["redirect_uri"][0].endswith("/auth/riot/callback")
        state = q["state"][0]

        bad = c.get("/auth/riot/callback", params={"code": "x", "state": "forged"})
        assert bad.headers["location"].endswith("riot_link=state"), "state 위조 거부"
        assert c.get("/auth/riot/callback", params={"error": "access_denied"}).headers["location"].endswith("riot_link=denied")

        with riot_http(riot):
            c.cookies.set("riot_oauth_state", state)
            done = c.get("/auth/riot/callback", params={"code": "auth-code", "state": state})
        assert done.headers["location"] == "/?tab=serverranking&riot_link=ok", done.headers
        me = c.get("/api/me").json()["account"]
        assert me == {"game_name": "진짜주인", "tag_line": "KR1", "verified": True}, me
        assert not (community_rank.get_member("old-discord") or {}).get("puuid"), "한 계정은 한 멤버에게만"
        board = community_rank.leaderboard()
        assert board["total"] == 1 and board["members"][0]["verified"] is True
        assert c.delete("/api/me/riot-account").status_code == 200
        assert community_rank.leaderboard()["total"] == 0
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ok("라이엇 로그인 인증: state 위조·취소 처리, 본인 puuid 만 연결, 한 계정은 한 멤버에게만")


def test_duo_multi_positions_queues_and_room_name():
    """포지션 여러 개('TOP,JUG'), 포지션 없는 큐(아레나·TFT), 음성방 이름은 링크의 실제 디스코드 채널 이름"""
    import httpx
    r = fresh_client().post("/api/duo-posts", json=_duo_payload(my_position="jug,top,TOP", target_position="MID,SUP", voice=False))
    assert r.status_code == 200, r.text
    post = r.json()["post"]
    assert post["my_position"] == "TOP,JUG" and post["target_position"] == "MID,SUP", post
    assert fresh_client().post("/api/duo-posts", json=_duo_payload(my_position="TOP,HACK")).status_code == 422
    assert fresh_client().post("/api/duo-posts", json=_duo_payload(my_position="ALL")).status_code == 422, "솔로랭크는 내 포지션 필수"
    for q in ("아레나", "TFT"):
        r = fresh_client().post("/api/duo-posts", json=_duo_payload(queue_type=q, my_position="ALL", voice=False))
        assert r.status_code == 200 and r.json()["post"]["my_position"] == "ALL", (q, r.text)
    for q in ("일반 (교차 선택)", "신속 대전"):
        assert fresh_client().post("/api/duo-posts", json=_duo_payload(queue_type=q, voice=False)).status_code == 200, q
    tft = lambda **kw: fresh_client().post("/api/duo-posts", json=_duo_payload(queue_type="TFT", my_position="ALL", voice=False, **kw))
    assert tft().json()["post"]["max_members"] == 8, "TFT 기본 8명"
    assert tft(max_members=3).json()["post"]["max_members"] == 3, "TFT 인원은 작성자가 고름"
    solo = tft(max_members=1).json()["post"]
    assert solo["max_members"] == 1 and solo["is_full"] is True, solo
    assert tft(max_members=9).status_code == 422, "TFT 최대 8명"
    assert fresh_client().post("/api/duo-posts", json=_duo_payload(max_members=1, voice=False)).status_code == 422, "다른 큐는 1명 불가"

    def discord(req):
        if req.url.path.endswith("/invites/abcDEF"):
            return httpx.Response(200, json={"channel": {"name": "듀오방 1"}, "guild": {"name": "우리서버"}})
        return httpx.Response(404, json={})
    with riot_http(discord):
        named = fresh_client().post("/api/duo-posts", json=_duo_payload(room_link="https://discord.gg/abcDEF", room_name="🔊 Tester의 음성방"))
        unknown = fresh_client().post("/api/duo-posts", json=_duo_payload(room_link="https://discord.gg/zzzZZZ", room_name="가짜 방 이름"))
    assert named.json()["post"]["room_name"] == "🔊 듀오방 1", named.json()["post"]
    assert unknown.json()["post"]["room_name"] == "🔊 디스코드 음성방", "작성자가 적은 이름은 쓰지 않음"
    ok("구인: 포지션 여러 개·잘못된 포지션 거부, 아레나·TFT 포지션 없음, TFT 인원 1~8, 새 큐, 음성방은 실제 채널 이름")



def test_duo_queue_and_tier_shorthand():
    """구인글: 큐 줄임말(솔랭·자랭·롤체·증칼), 티어 줄임말·단계(다1·에메2), 자랭 범위(브~다)와 범위 필터"""
    post = lambda **kw: fresh_client().post("/api/duo-posts", json=_duo_payload(voice=False, **kw))
    r = post(queue_type="솔랭", tier_kr="다1")
    assert r.status_code == 200, r.text
    p = r.json()["post"]
    assert p["queue_type"] == "솔로랭크" and p["tier_kr"] == "다이아몬드" and p["tier_label"] == "다이아몬드 1" and p["tier"] == "DIAMOND", p
    assert post(queue_type="롤체", my_position="ALL", tier_kr="에메2").json()["post"]["queue_type"] == "TFT"
    assert post(queue_type="증칼", my_position="ALL").json()["post"]["queue_type"] == "증강 칼바람"
    rng = post(queue_type="자랭", tier_kr="브~다", title="검수용 범위 글").json()["post"]
    assert rng["tier"] == "BRONZE" and rng["tier_to"] == "DIAMOND" and rng["tier_label"] == "브론즈 ~ 다이아몬드", rng
    listed = fresh_client().get("/api/duo-posts", params={"tier": "GOLD", "queue_type": "자유랭크"}).json()["posts"]
    assert any(x["id"] == rng["id"] for x in listed), "골드로 걸러도 브론즈~다이아 글이 보임"
    listed = fresh_client().get("/api/duo-posts", params={"tier": "MASTER", "queue_type": "자유랭크"}).json()["posts"]
    assert not any(x["id"] == rng["id"] for x in listed), "범위 밖 티어로는 안 보임"
    bad = post(tier_kr="다이아5")
    assert bad.status_code == 422 and "티어를 알아보지 못했어요" in bad.text, bad.text
    assert post(queue_type="아무큐").status_code == 422
    assert post(queue_type="솔랭", tier_kr="다~마").status_code == 422, "솔로랭크 범위에 마스터가 끼면 거부"
    ok("구인: 큐 줄임말(솔랭·롤체·증칼), 티어 줄임말·단계(다1), 범위(브~다)와 범위 필터, 잘못된 티어 안내")


def test_multi_server_separation():
    """여러 디스코드 서버: 구인글·내전 순위는 서버마다 따로, 다른 서버 글 참가·서버 선택 불가, 봇은 등록 서버만, 웹후크는 그 서버 채널로만"""
    import os
    import asyncio
    import httpx
    from app import community_rank, communities, member_auth
    from app.config import settings
    keys = ("MEMBER_LOGIN", "BOT_API_SECRET", "DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_GUILD_ID",
            "MEMBER_SESSION_SECRET", "COMMUNITY_GUILDS", "DISCORD_WEBHOOK_URL_222", "SITE_URL")
    saved = {k: os.environ.get(k) for k in keys}
    saved_hook = settings.discord_webhook_url
    try:
        os.environ.update(MEMBER_LOGIN="discord", DISCORD_CLIENT_ID="1", DISCORD_CLIENT_SECRET="x" * 20,
                          MEMBER_SESSION_SECRET="y" * 40, BOT_API_SECRET="z" * 32, COMMUNITY_GUILDS="111:서버A,222:서버B",
                          SITE_URL="https://example.test")
        os.environ.pop("DISCORD_GUILD_ID", None)
        settings.discord_webhook_url = ""

        def member(did, guilds, pick=None):
            community_rank.remember_member(did, f"검수용{did}")
            community_rank.set_member_guilds(did, guilds)
            c = fresh_client()
            c.cookies.set(member_auth.SESSION_COOKIE, member_auth.make_session(did))
            if pick:
                c.cookies.set(communities.CURRENT_COOKIE, pick)
            return c

        b_only = member("9001", ["222"])
        a_only = member("9002", ["111"])
        both = member("9003", ["111", "222"], pick="111")
        me = b_only.get("/api/me").json()
        assert me["community"] == "222" and [c["id"] for c in me["communities"]] == ["222"], me
        post = b_only.post("/api/duo-posts", json=_duo_payload(voice=False, title="검수용 서버B 글")).json()["post"]
        assert post["guild_id"] == "222"
        ids = lambda c: [p["id"] for p in c.get("/api/duo-posts").json()["posts"]]  # noqa: E731
        assert post["id"] in ids(b_only) and post["id"] not in ids(a_only), "다른 서버 글은 안 보임"
        assert a_only.post(f"/api/duo-posts/{post['id']}/join").status_code == 404, "다른 서버 글 참가 불가"
        assert post["id"] not in ids(both)
        assert both.post("/api/community", json={"guild_id": "333"}).status_code == 403
        assert a_only.post("/api/community", json={"guild_id": "222"}).status_code == 403, "들어가 있지 않은 서버 선택 불가"
        r = both.post("/api/community", json={"guild_id": "222"})
        assert r.status_code == 200 and "community=222" in r.headers.get("set-cookie", ""), r.text
        both.cookies.set(communities.CURRENT_COOKIE, "222")  # 테스트 클라이언트는 도메인 없는 쿠키를 따로 들고 있어 직접 바꾼다
        assert post["id"] in ids(both), "서버를 바꾸면 그 서버 글"

        bot = fresh_client()
        h = {"X-Bot-Secret": "z" * 32}
        bm = lambda g: {"discord_id": "9004", "discord_name": "검수용봇", "guild_id": g}  # noqa: E731
        assert bot.post("/api/bot/duo-posts", headers=h, json={**_duo_payload(voice=False), "member": bm("333")}).status_code == 403
        r = bot.post("/api/bot/duo-posts", headers=h, json={**_duo_payload(voice=False), "member": bm("111")})
        assert r.status_code == 200 and r.json()["post"]["guild_id"] == "111", r.text
        assert bot.post(f"/api/bot/duo-posts/{post['id']}/join", headers=h, json=bm("111")).status_code == 404

        seats = [{"name": f"검수용멤버{i}"} for i in range(10)]
        gid = b_only.post("/api/inhouse/games", json={"blue": seats[:5], "red": seats[5:]}).json()["id"]
        assert b_only.post(f"/api/inhouse/games/{gid}/result", json={"winner": "blue"}).status_code == 200
        names = lambda c: {p["name"] for p in c.get("/api/inhouse/ranking").json()["players"]}  # noqa: E731
        assert "검수용멤버0" in names(b_only) and "검수용멤버0" not in names(a_only), "내전 순위도 서버마다"

        settings.discord_webhook_url = "https://discord.com/api/webhooks/1/legacy"
        assert communities.webhook_url("111") == settings.discord_webhook_url, "기본 서버는 예전 설정 사용"
        assert communities.webhook_url("222") == "", "다른 서버 글이 기본 서버 채널로 새지 않음"
        os.environ["DISCORD_WEBHOOK_URL_222"] = "https://discord.com/api/webhooks/2/b"
        assert communities.webhook_url("222", "lol") == "https://discord.com/api/webhooks/2/b"

        def discord(req):
            if req.url.path.endswith("/oauth2/token"):
                return httpx.Response(200, json={"access_token": "t"})
            if req.url.path.endswith("/users/@me"):
                return httpx.Response(200, json={"id": "9005", "username": "검수용"})
            if req.url.path.endswith("/guilds/111/member"):
                return httpx.Response(404, json={})
            if req.url.path.endswith("/guilds/222/member"):
                return httpx.Response(200, json={"nick": "검수용별명"})
            return httpx.Response(500, json={})
        with riot_http(discord):
            res = asyncio.run(member_auth.check_membership(None, "code"))
        assert res["member"] and res["guilds"] == ["222"] and res["name"] == "검수용별명", res
    finally:
        settings.discord_webhook_url = saved_hook
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ok("여러 서버: 구인글·내전 순위 서버별 분리, 다른 서버 글 참가·서버 선택 불가, 봇은 등록 서버만, 웹후크는 그 서버 채널만")


def test_bot_tier_roles_registered_members():
    """티어 역할: 봇 비밀값 필요, 닉네임 등록(미인증)·인증 계정 모두 티어가 나옴, 등록 안 된 서버 거부.
    닉네임 등록은 다른 멤버가 인증한 계정을 가져갈 수 없고, 이미 인증한 멤버는 등록으로 덮어쓰지 않음"""
    import os
    from app import community_rank
    from app.database import get_connection
    saved = {k: os.environ.get(k) for k in ("BOT_API_SECRET", "COMMUNITY_GUILDS")}
    try:
        os.environ["BOT_API_SECRET"] = "z" * 32
        os.environ.pop("COMMUNITY_GUILDS", None)
        community_rank.remember_member("8801", "검수용인증")
        community_rank.link_account("8801", {"puuid": "q" * 78, "game_name": "검수용인증", "tag_line": "KR1"})
        conn = get_connection()
        conn.execute("INSERT OR REPLACE INTO member_accounts (discord_id, discord_name, puuid, game_name, tag_line, verified) "
                     "VALUES ('8802', '검수용미인증', ?, '검수용미인증', 'KR1', 0)", ("w" * 78,))
        conn.commit()
        conn.close()
        orig = community_rank.get_player_by_riot_id
        community_rank.get_player_by_riot_id = lambda gn, tag: {"puuid": ("q" if gn == "검수용인증" else "w") * 78, "tier": "GOLD"}
        try:
            assert fresh_client().get("/api/bot/tier-roles").status_code in (401, 403), "봇 비밀값 없으면 거부"
            h = {"X-Bot-Secret": "z" * 32}
            got = {m["discord_id"]: m["tier"] for m in fresh_client().get("/api/bot/tier-roles", headers=h).json()["members"]}
            assert got.get("8801") == "GOLD" and got.get("8802") == "GOLD", got
            assert community_rank.register_account("8803", {"puuid": "q" * 78, "game_name": "검수용인증", "tag_line": "KR1"}) == "taken"
            assert community_rank.register_account("8801", {"puuid": "e" * 78, "game_name": "검수용다른", "tag_line": "KR1"}) == "verified_already"
            os.environ["COMMUNITY_GUILDS"] = "111:검수용"
            assert fresh_client().get("/api/bot/tier-roles", params={"guild_id": "999"}, headers=h).status_code == 403
        finally:
            community_rank.get_player_by_riot_id = orig
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ok("티어 역할: 봇만 조회, 등록·인증 멤버 모두 티어, 남의 인증 계정 등록 불가, 인증 멤버는 등록으로 덮어쓰지 않음")


def test_bot_alert_role_setting():
    """구인 알림 역할: 봇 /알림역할 로 정한 역할이 .env 보다 먼저, 끄면 .env 값도 안 씀, 서버마다 따로, 봇 비밀값 필요"""
    import os
    from app.services.discord_service import duo_alert_roles
    saved = {k: os.environ.get(k) for k in ("BOT_API_SECRET", "COMMUNITY_GUILDS", "DUO_ALERT_ROLES", "DUO_ALERT_ROLES_222")}
    try:
        os.environ.update(BOT_API_SECRET="z" * 32, COMMUNITY_GUILDS="111:검수용A,222:검수용B", DUO_ALERT_ROLES="lol=5")
        os.environ.pop("DUO_ALERT_ROLES_222", None)
        h = {"X-Bot-Secret": "z" * 32}
        m = lambda g: {"discord_id": "7701", "discord_name": "검수용관리자", "guild_id": g}  # noqa: E731
        assert duo_alert_roles("111") == {"lol": "5"}, "설정 전에는 .env"
        assert fresh_client().post("/api/bot/alert-role", json={"member": m("111"), "role_id": "77"}).status_code in (401, 403)
        r = fresh_client().post("/api/bot/alert-role", headers=h, json={"member": m("111"), "game": "lol", "role_id": "77"})
        assert r.status_code == 200 and r.json()["roles"] == {"lol": "77"}, r.text
        assert duo_alert_roles("111") == {"lol": "77"} and duo_alert_roles("") == {"lol": "77"}, "기본 서버 글도 같은 역할"
        assert duo_alert_roles("222") == {}, "다른 서버에는 영향 없음"
        assert fresh_client().get("/api/bot/alert-role", params={"guild_id": "111"}, headers=h).json()["roles"] == {"lol": "77"}
        fresh_client().post("/api/bot/alert-role", headers=h, json={"member": m("111"), "game": "lol", "role_id": None})
        assert duo_alert_roles("111") == {}, "봇에서 끄면 .env 값도 쓰지 않음"
        assert fresh_client().post("/api/bot/alert-role", headers=h, json={"member": m("999"), "role_id": "1"}).status_code == 403
        assert fresh_client().post("/api/bot/alert-role", headers=h, json={"member": m("111"), "role_id": "<@&1>"}).status_code == 422
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ok("알림 역할: 봇 /알림역할 값 우선, 끄기, 서버별 분리, 봇 비밀값·등록 서버·숫자 ID만")


def test_bot_tier_role_map_per_server():
    """티어 역할 연결: 서버마다 기존 역할 ID 를 저장·조회, 여러 티어가 한 역할 공유 가능, 잘못된 코드·ID 거부"""
    import os
    saved = {k: os.environ.get(k) for k in ("BOT_API_SECRET", "COMMUNITY_GUILDS")}
    try:
        os.environ.update(BOT_API_SECRET="z" * 32, COMMUNITY_GUILDS="111:검수용A,222:검수용B")
        h = {"X-Bot-Secret": "z" * 32}
        m = lambda g: {"discord_id": "7702", "discord_name": "검수용관리자", "guild_id": g}  # noqa: E731
        r = fresh_client().post("/api/bot/tier-role-map", headers=h,
                                json={"member": m("111"), "roles": {"GOLD": "501", "MASTER": "900", "GRANDMASTER": "900"}})
        assert r.status_code == 200 and r.json()["role_map"] == {"GOLD": "501", "MASTER": "900", "GRANDMASTER": "900"}, r.text
        got = fresh_client().get("/api/bot/tier-roles", params={"guild_id": "111"}, headers=h).json()["role_map"]
        assert got["MASTER"] == got["GRANDMASTER"] == "900", "마스터+ 처럼 한 역할 공유"
        assert fresh_client().get("/api/bot/tier-roles", params={"guild_id": "222"}, headers=h).json()["role_map"] == {}, "서버별 분리"
        assert fresh_client().post("/api/bot/tier-role-map", headers=h,
                                   json={"member": m("111"), "roles": {"GOD": "1"}}).status_code == 422
        assert fresh_client().post("/api/bot/tier-role-map", headers=h,
                                   json={"member": m("111"), "roles": {"GOLD": "<@&1>"}}).status_code == 422
        assert fresh_client().post("/api/bot/tier-role-map", json={"member": m("111"), "roles": {}}).status_code in (401, 403)
        fresh_client().post("/api/bot/tier-role-map", headers=h, json={"member": m("111"), "roles": {}})
        assert fresh_client().get("/api/bot/tier-roles", params={"guild_id": "111"}, headers=h).json()["role_map"] == {}, "비우면 해제"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ok("티어 역할 연결: 서버별 기존 역할 저장, 한 역할 공유, 잘못된 값 거부, 봇만")


def test_recruit_requires_real_riot_id():
    """롤 구인글: 라이엇에 없는 닉네임은 422 (1번 묻고 기억), RECRUIT_REQUIRE_VERIFIED=1 이면 인증한 본인 계정만"""
    import os
    import httpx
    from app import community_rank, main as main_mod
    from app.riot_client import riot_client
    saved_key, saved_flag = settings.riot_api_key, os.environ.get("RECRUIT_REQUIRE_VERIFIED")
    settings.riot_api_key = "RGAPI-test-key"
    riot_client.reset_key_status()
    main_mod._RIOT_ID_SEEN.clear()
    asked = []

    def riot(req):
        if "/accounts/by-riot-id/" in req.url.path:
            asked.append(req.url.path)
            if "%EA%B0%80%EC%A7%9C" in req.url.raw_path.decode() or "가짜" in req.url.path:
                return httpx.Response(404, json={})
            return httpx.Response(200, json={"puuid": "r" * 78, "gameName": "Tester", "tagLine": "KR1"})
        return httpx.Response(404, json={})
    try:
        with riot_http(riot):
            bad = fresh_client().post("/api/duo-posts", json=_duo_payload(game_name="가짜닉", voice=False))
            assert bad.status_code == 422 and "라이엇에 없는 닉네임" in bad.text, bad.text
            assert fresh_client().post("/api/duo-posts", json=_duo_payload(game_name="가짜닉", voice=False)).status_code == 422
            assert len(asked) == 1, "같은 닉네임은 다시 묻지 않음"
            assert fresh_client().post("/api/duo-posts", json=_duo_payload(voice=False)).status_code == 200
            pubg = fresh_client().post("/api/duo-posts", json=_duo_payload(game="pubg", game_name="아무이름", tier_kr="골드",
                                                                         queue_type="일반 스쿼드", my_position="ALL", target_position="ALL", voice=False))
            assert pubg.status_code == 200, "배그는 검사 안 함"

            os.environ["RECRUIT_REQUIRE_VERIFIED"] = "1"
            community_rank.unlink_account("local-dev")
            assert fresh_client().post("/api/duo-posts", json=_duo_payload(voice=False)).status_code == 403, "인증 안 하면 못 씀"
            community_rank.link_account("local-dev", {"puuid": "r" * 78, "game_name": "Tester", "tag_line": "KR1"})
            assert fresh_client().post("/api/duo-posts", json=_duo_payload(game_name="남의닉", voice=False)).status_code == 403
            assert fresh_client().post("/api/duo-posts", json=_duo_payload(game_name="tester", voice=False)).status_code == 200
    finally:
        settings.riot_api_key = saved_key
        riot_client.reset_key_status()
        community_rank.unlink_account("local-dev")
        if saved_flag is None:
            os.environ.pop("RECRUIT_REQUIRE_VERIFIED", None)
        else:
            os.environ["RECRUIT_REQUIRE_VERIFIED"] = saved_flag
    ok("구인글: 라이엇에 없는 롤 닉네임 거부(재조회 없음), 배그 제외, 승인 후 스위치로 인증 본인 계정만")


def test_inhouse_plan_and_events():
    """팀 짜기: 10명 5:5 / 23명 여러 판(남는 3명 대기) / 40명 토너먼트(8팀) / 리그. 토너먼트는 이긴 팀이 다음 라운드, 리그는 순위표"""
    import random
    from app import team_builder
    random.seed(7)
    tiers = ["SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"]
    lanes = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"]

    def people(n):
        return [{"name": f"검수용팀원{i}", "tier": tiers[i % 5], "rank": "II", "lp": 50, "main": lanes[i % 5]} for i in range(n)]
    c = fresh_client()
    one = c.post("/api/inhouse/plan", json={"players": people(10), "mode": "single"}).json()
    opt = one["games"][0]["options"][0]
    assert len(opt["blue"]["players"]) == 5 and len(opt["red"]["players"]) == 5
    assert opt["lane_penalty"] == 0, "주 라인이 고르게 있으면 모두 주 라인"
    assert sorted(p["lane"] for p in opt["blue"]["players"]) == sorted(lanes)
    multi = c.post("/api/inhouse/plan", json={"players": people(23), "mode": "multi", "split": "tiered"}).json()
    assert len(multi["games"]) == 2 and len(multi["waitlist"]) == 3, "20명 2판 + 3명 대기"
    assert fresh_client().post("/api/inhouse/plan", json={"players": people(9)}).status_code == 422

    tour = c.post("/api/inhouse/plan", json={"players": people(40), "mode": "tournament"}).json()
    assert len(tour["teams"]) == 8 and len(tour["matches"]) == 4 and tour["team_spread"] < 300, tour["team_spread"]
    body = {"mode": "tournament", "title": "검수용 대회",
            "teams": [{"name": t["name"], "players": [{"name": p["name"], "lane": p["lane"]} for p in t["players"]]} for t in tour["teams"]],
            "matches": tour["matches"]}
    eid = c.post("/api/inhouse/events", json=body).json()["id"]
    assert fresh_client().post(f"/api/inhouse/events/{eid}/matches/0/start").status_code == 403, "만든 사람만 시작"
    for i in range(4):  # 1라운드 4경기: 모두 블루(a팀) 승
        gid = c.post(f"/api/inhouse/events/{eid}/matches/{i}/start").json()["game_id"]
        assert c.post(f"/api/inhouse/games/{gid}/result", json={"winner": "blue"}).status_code == 200
    ev = c.get(f"/api/inhouse/events/{eid}").json()
    second = [m for m in ev["matches"] if m["round"] == 2]
    assert len(second) == 2 and "champion" not in ev, "이긴 팀끼리 2라운드"
    for m in second + []:
        idx = ev["matches"].index(m)
        gid = c.post(f"/api/inhouse/events/{eid}/matches/{idx}/start").json()["game_id"]
        c.post(f"/api/inhouse/games/{gid}/result", json={"winner": "red"})
    ev = c.get(f"/api/inhouse/events/{eid}").json()
    final = [m for m in ev["matches"] if m["round"] == 3]
    gid = c.post(f"/api/inhouse/events/{eid}/matches/{ev['matches'].index(final[0])}/start").json()["game_id"]
    c.post(f"/api/inhouse/games/{gid}/result", json={"winner": "blue"})
    ev = c.get(f"/api/inhouse/events/{eid}").json()
    assert ev["champion"] == final[0]["a"] and "created_by" not in ev

    lg = c.post("/api/inhouse/plan", json={"players": people(15), "mode": "league"}).json()
    assert len(lg["teams"]) == 3 and len(lg["matches"]) == 3, "3팀 풀리그 3경기"
    lid = c.post("/api/inhouse/events", json={"mode": "league", "teams": [
        {"name": t["name"], "players": [{"name": p["name"]} for p in t["players"]]} for t in lg["teams"]], "matches": lg["matches"]}).json()["id"]
    gid = c.post(f"/api/inhouse/events/{lid}/matches/0/start").json()["game_id"]
    c.post(f"/api/inhouse/games/{gid}/result", json={"winner": "blue"})
    st = c.get(f"/api/inhouse/events/{lid}").json()["standings"]
    assert st[0]["wins"] == 1 and st[-1]["losses"] in (0, 1)
    assert fresh_client().post("/api/inhouse/events", json=dict(body, teams=body["teams"][:1])).status_code == 422
    assert team_builder.best_lanes([{"main": "TOP"}, {"main": "TOP"}, {"main": "MID"}, {"main": "ADC"}, {"main": "SUPPORT"}])[0] > 0
    ok("팀 짜기: 5:5·여러 판(대기)·토너먼트(진출·우승)·리그(순위), 라인 배정, 만든 사람만 경기 시작")


def test_bot_event_flow():
    """봇 대회: 저장(만든 멤버), 진행판 조회, 만든 사람만 경기 시작, 결과 → 다음 라운드, 다른 서버 대회는 안 보임"""
    import os
    saved = {k: os.environ.get(k) for k in ("BOT_API_SECRET", "COMMUNITY_GUILDS")}
    try:
        os.environ.update(BOT_API_SECRET="z" * 32, COMMUNITY_GUILDS="111:검수용A,222:검수용B")
        h = {"X-Bot-Secret": "z" * 32}
        owner = {"discord_id": "6601", "discord_name": "검수용주최", "guild_id": "111"}
        other = {"discord_id": "6602", "discord_name": "검수용남", "guild_id": "111"}
        far = {"discord_id": "6603", "discord_name": "검수용다른서버", "guild_id": "222"}
        teams = [{"name": f"{t + 1}팀", "players": [{"name": f"검수용봇대회{t}-{i}"} for i in range(5)]} for t in range(4)]
        body = {"mode": "tournament", "teams": teams, "matches": [{"round": 1, "a": 0, "b": 3}, {"round": 1, "a": 1, "b": 2}],
                "requested_by": owner}
        c = fresh_client()
        assert c.post("/api/bot/inhouse/events", json=body).status_code in (401, 403)
        eid = c.post("/api/bot/inhouse/events", json=body, headers=h).json()["id"]
        view = c.post(f"/api/bot/inhouse/events/{eid}/view", json={"requested_by": owner}, headers=h).json()
        assert view["is_owner"] is True and len(view["matches"]) == 2 and "created_by" not in view
        assert c.post(f"/api/bot/inhouse/events/{eid}/view", json={"requested_by": far}, headers=h).status_code == 404, "다른 서버"
        assert c.post(f"/api/bot/inhouse/events/{eid}/matches/0/start", json={"requested_by": other}, headers=h).status_code == 403
        for i in range(2):
            gid = c.post(f"/api/bot/inhouse/events/{eid}/matches/{i}/start", json={"requested_by": owner}, headers=h).json()["game_id"]
            r = c.post(f"/api/bot/inhouse/games/{gid}/result", json={"winner": "blue", "requested_by": owner}, headers=h)
            assert r.status_code == 200, r.text
        view = c.post(f"/api/bot/inhouse/events/{eid}/view", json={"requested_by": other}, headers=h).json()
        assert view["is_owner"] is False and [m for m in view["matches"] if m["round"] == 2][0]["a"] == 0, "1팀·2팀 결승"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ok("봇 대회: 저장·진행판·만든 사람만 시작·결과로 다음 라운드·다른 서버 차단")


def test_left_member_is_logged_out():
    """디스코드 서버를 나간 사람: 로그인 쿠키가 남아 있어도 다음 확인 때 401·로그인 화면 (디스코드 장애·봇이 서버에 없을 때는 막지 않음)"""
    import os
    import httpx
    from app import member_auth
    keys = ("MEMBER_LOGIN", "DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_GUILD_ID", "MEMBER_SESSION_SECRET",
            "DISCORD_BOT_TOKEN", "COMMUNITY_GUILDS")
    saved = {k: os.environ.get(k) for k in keys}
    answer = {"status": 200, "code": 0}

    def discord(req):
        if req.url.path.endswith("/guilds/777/members/4242"):
            assert req.headers.get("authorization") == "Bot fake-bot-token"
            return httpx.Response(answer["status"], json={"code": answer["code"]} if answer["status"] != 200 else {"user": {"id": "4242"}})
        return httpx.Response(404, json={})
    try:
        os.environ.update(MEMBER_LOGIN="discord", DISCORD_CLIENT_ID="1", DISCORD_CLIENT_SECRET="x" * 20, DISCORD_GUILD_ID="777",
                          MEMBER_SESSION_SECRET="y" * 40, DISCORD_BOT_TOKEN="fake-bot-token")
        os.environ.pop("COMMUNITY_GUILDS", None)
        c = fresh_client(follow_redirects=False)
        c.cookies.set(member_auth.SESSION_COOKIE, member_auth.make_session("4242"))
        with riot_http(discord):
            member_auth.forget_membership("4242")
            assert c.get("/api/duo-games").status_code == 200, "멤버면 통과"
            answer.update(status=500)
            member_auth.forget_membership("4242")
            assert c.get("/api/duo-games").status_code == 200, "디스코드 장애면 막지 않음"
            answer.update(status=404, code=10004)
            member_auth.forget_membership("4242")
            assert c.get("/api/duo-games").status_code == 200, "봇이 서버에 없는 404 는 탈퇴로 보지 않음"
            answer.update(status=404, code=10007)
            member_auth.forget_membership("4242")
            r = c.get("/api/duo-games")
            assert r.status_code == 401 and "로그아웃" in r.text, r.text
            page = c.get("/")
            assert page.status_code == 302 and page.headers["location"] == "/login?error=member"
    finally:
        member_auth.forget_membership("4242")
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ok("서버를 나간 멤버: 다음 확인(5분) 때 로그아웃, 디스코드 장애·봇 문제로는 아무도 쫓아내지 않음")

def test_inhouse_tournament_code_result_and_ranking():
    """내전 토너먼트 코드: 만든 사람만 발급, 위조 콜백(다른 게임 ID) 무시, 진짜 결과는 자동 기록·손 결과 잠금, 순위·세부 기록"""
    import os
    import httpx
    from app import inhouse
    from app.riot_client import riot_client
    saved_mode, saved_key = os.environ.get("RIOT_TOURNAMENT"), settings.riot_api_key
    os.environ["RIOT_TOURNAMENT"] = "stub"
    settings.riot_api_key = "RGAPI-test-key"
    riot_client.reset_key_status()
    code = "KR0001-aaaabbbb-cccc-dddd"
    puuids = [f"puuid-{i:02d}" + "x" * 60 for i in range(10)]

    def participant(i):
        return {"puuid": puuids[i], "riotIdGameName": f"검수용{i}", "riotIdTagline": "KR1", "teamId": 100 if i < 5 else 200,
                "win": i < 5, "championName": "Ahri" if i == 0 else "Garen", "teamPosition": "MIDDLE",
                "kills": 5, "deaths": 2, "assists": 7, "goldEarned": 12000, "totalMinionsKilled": 180,
                "neutralMinionsKilled": 10, "totalDamageDealtToChampions": 20000, "visionScore": 25, "turretTakedowns": 2}

    def match(tcode):
        return {"metadata": {"matchId": "KR_777"}, "info": {"tournamentCode": tcode, "gameDuration": 1800,
                "teams": [{"teamId": 100, "win": True}, {"teamId": 200, "win": False}],
                "participants": [participant(i) for i in range(10)]}}

    calls = []

    def riot(req):
        path = req.url.path
        calls.append(path)
        if path.endswith("/tournament-stub/v5/providers"):
            return httpx.Response(200, json=11)
        if path.endswith("/tournament-stub/v5/tournaments"):
            return httpx.Response(200, json=22)
        if path.endswith("/tournament-stub/v5/codes"):
            assert req.url.params["tournamentId"] == "22"
            return httpx.Response(200, json=[code])
        if path.endswith("/lol/match/v5/matches/KR_777"):
            return httpx.Response(200, json=match(code))
        if path.endswith("/lol/match/v5/matches/KR_666"):
            return httpx.Response(200, json=match("KR0001-other-code-0000"))
        return httpx.Response(404, json={})

    try:
        owner = fresh_client()
        seats = [{"name": f"검수용{i}"} for i in range(10)]
        gid = owner.post("/api/inhouse/games", json={"blue": seats[:5], "red": seats[5:]}).json()["id"]
        with riot_http(riot):
            assert fresh_client().post(f"/api/inhouse/games/{gid}/code").status_code == 403, "다른 사람은 코드 발급 불가"
            r = owner.post(f"/api/inhouse/games/{gid}/code")
            assert r.status_code == 200 and r.json() == {"code": code, "mode": "stub"}, r.text
            assert owner.post(f"/api/inhouse/games/{gid}/code").json()["code"] == code, "같은 게임은 같은 코드"

            cb = fresh_client()
            assert cb.post("/api/riot/tournament/callback", json={"shortCode": code, "gameId": 666}).json()["status"] == "mismatch"
            assert inhouse.get_game(gid)["winner"] is None, "다른 경기 ID 로 보낸 위조 알림은 반영 안 됨"
            assert cb.post("/api/riot/tournament/callback", json={"shortCode": "KR0001-unknown-0000", "gameId": 777}).json()["status"] == "not_found"
            assert cb.post("/api/riot/tournament/callback", json={"shortCode": code, "gameId": 777}).json()["status"] == "ok"
            assert cb.post("/api/riot/tournament/callback", json={"shortCode": code, "gameId": 777}).json()["status"] == "already"
        g = inhouse.get_game(gid)
        assert g["winner"] == "blue" and g["match_id"] == "KR_777"
        assert owner.post(f"/api/inhouse/games/{gid}/result", json={"winner": "red"}).status_code == 409, "라이엇 결과는 잠김"

        board = fresh_client().get("/api/inhouse/ranking").json()["players"]
        top = next(p for p in board if p["name"] == "검수용0")
        assert top["games"] == 1 and top["wins"] == 1 and top["kda"] == 6.0 and top["rating"] > 1000
        assert top["most_champions"] == [{"champion": "Ahri", "games": 1}] and top["placement"] is True
        assert "avg_gold" not in top, "평균 골드 같은 세부 기록은 순위표에 없음"
        detail = fresh_client().get(f"/api/inhouse/players/{top['key']}").json()
        assert detail["avg_gold"] == 12000 and detail["avg_turrets"] == 2.0 and detail["cs_per_min"] == 6.3, detail
        assert fresh_client().get("/api/inhouse/players/n:abc").status_code == 404
        loser = next(p for p in board if p["name"] == "검수용9")
        assert loser["losses"] == 1 and loser["rating"] < 1000
    finally:
        if saved_mode is None:
            os.environ.pop("RIOT_TOURNAMENT", None)
        else:
            os.environ["RIOT_TOURNAMENT"] = saved_mode
        settings.riot_api_key = saved_key
        riot_client.reset_key_status()
    assert fresh_client(follow_redirects=False).post(f"/api/inhouse/games/{gid}/code").status_code in (403, 503)
    ok("내전 토너먼트 코드: 만든 사람만 발급, 위조 알림 무시, 라이엇 결과 자동 기록·잠금, 순위(점수·KDA·모스트)·세부 기록 분리")

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
