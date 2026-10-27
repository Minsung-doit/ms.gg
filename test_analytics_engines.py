"""
분석 엔진 회귀 검증 (2026-10-24 Analytics Engines 점검)

SYNTHETIC_FEATURES=0 상태에서도 열려 있는 경로(관전 스크립트, 듀오 구인, 챔피언 스킬,
디스코드/텔레그램 공유 카드)가 값을 지어내지 않는지, 잘못된 입력에 500이 나지 않는지 확인한다.
네트워크 호출 없음.
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from test_support import sandbox_env_writes, use_temp_db

sandbox_env_writes()
use_temp_db()

from fastapi.testclient import TestClient

import app.champion_skills_data as skills
import app.duo_finder_engine as duo
import app.services.discord_service as discord_service
from app.config import settings
from app.main import app
from app.services.telegram_service import format_telegram_finance_card, format_telegram_player_card
from app.finance_engine import calculate_financial_summary
from app.spectator_engine import generate_spectator_launch_script, spectator_launch_script_or_none

_ip = [0]


def client() -> TestClient:
    _ip[0] += 1
    return TestClient(app, client=(f"198.51.100.{_ip[0]}", 40000), raise_server_exceptions=False)


def ok(msg):
    print(f"  [PASS] {msg}")


def _duo_payload(**over):
    payload = {
        "game_name": "엔진점검", "tag_line": "KR1", "tier_kr": "골드",
        "my_position": "MID", "target_position": "JUG", "queue_type": "솔로랭크",
        "voice": True, "title": "듀오 구해요", "description": "",
    }
    payload.update(over)
    return payload


def test_spectator_script_needs_real_key():
    c = client()
    assert c.get("/api/spectator/script/7182900123").status_code == 400
    assert c.get("/api/spectator/download-bat/7182900123").status_code == 400
    assert spectator_launch_script_or_none(7182900123) is None
    res = c.get("/api/spectator/download-bat/7182900123?encryption_key=Abc123%2B%2F%3D")
    assert res.status_code == 200 and b"Abc123+/=" in res.content
    assert b"chcp 65001" not in res.content, ".bat은 cp949로 내려가므로 UTF-8 코드페이지로 바꾸면 한글이 깨짐"
    assert "[경고]".encode("cp949") in res.content
    ok("관전 스크립트: 암호화 키가 없으면 지어내지 않고 400, .bat 한글 인코딩 일치")


def test_duo_post_has_no_fabricated_links_or_scores():
    c = client()
    post = c.post("/api/duo-posts", json=_duo_payload(queue_type="자유랭크")).json()["post"]
    for key in ("discord_voice_url", "discord_invite_url", "room_link"):
        assert not post.get(key), f"{key}={post.get(key)} (링크를 넣지 않았는데 주소가 생김)"
    assert post["max_members"] == 5 and "(1/5명)" in post["room_status"], post["room_status"]
    assert post["synergy_score"] is None and post["synergy_badge"] is None

    # 프런트가 기본값으로 넣어 보내는 가짜 주소는 링크 없음으로 처리
    post = c.post("/api/duo-posts", json=_duo_payload(
        room_link="discord://discord.com/channels/1188000000000000001/1188000000000000011",
        discord_invite_url="https://discord.gg/lolgg-duo")).json()["post"]
    assert not post["room_link"] and not post["discord_invite_url"], post

    real_link = "https://discord.gg/abcDEF"
    post = c.post("/api/duo-posts", json=_duo_payload(room_link=real_link)).json()["post"]
    assert post["room_link"] == real_link
    listed = [p for p in c.get("/api/duo-posts").json()["posts"] if p["id"] == post["id"]]
    assert listed and listed[0]["room_link"] == real_link
    ok("듀오 글: 가짜 디스코드 서버 주소·고정 시너지 점수 제거, 방 인원 상태가 실제 정원 반영")


def test_duo_post_inhouse_queue_and_apex_rule():
    post = client().post("/api/duo-posts", json=_duo_payload(queue_type="내전", tier_kr="마스터")).json()["post"]
    assert post["max_members"] == 10, post
    r = client().post("/api/duo-posts", json=_duo_payload(queue_type="솔로랭크", tier_kr="챌린저"))
    assert r.status_code == 422, r.text
    client().post("/api/duo-posts", json=_duo_payload(queue_type="내전", tier_kr="그랜드마스터"))
    masters = client().get("/api/duo-posts", params={"game": "lol", "tier": "마스터"}).json()["posts"]
    assert masters and all(p["tier_kr"] == "마스터" for p in masters), [p["tier_kr"] for p in masters]
    ok("구인: 내전 큐는 10명, 마스터 이상 솔로랭크 듀오 글은 막음, 티어 필터는 정확히 그 티어만")


def test_duo_discord_join_counts_only_real_posts():
    c = client()
    before = duo.DISCORD_JOIN_STATS["total_clicks"]
    res = c.post("/api/duo-posts/987654/discord-join").json()
    assert res["status"] == "not_found" and duo.DISCORD_JOIN_STATS["total_clicks"] == before
    post_id = c.post("/api/duo-posts", json=_duo_payload()).json()["post"]["id"]
    res = c.post(f"/api/duo-posts/{post_id}/discord-join").json()
    assert res["joined"] is True and duo.DISCORD_JOIN_STATS["total_clicks"] == before + 1
    ok("디스코드 입장 클릭: 없는 글 번호로는 집계되지 않음")


def test_champion_skills_only_real_values():
    data = client().get("/api/champion-skills/Annie").json()
    assert data["patch_version"] == skills._RAW_DATA_VERSION and data["patch_version"] != "14.20.1"
    assert data["skill_master_order"] is None
    assert data["combos"] == [], "직접 정리하지 않은 챔피언에 공통 콤보 문구를 붙이지 않음"
    assert data["skills"]["Q"]["scaling_info"] is None
    raw_q = skills._load_raw_data()["Annie"]["spells"][0]
    assert data["skills"]["Q"]["cooldown_burn"] == raw_q["cooldownBurn"]
    assert data["skills"]["Q"]["name"] == raw_q["name"]

    # Data Dragon 원본이 없는 챔피언은 쿨다운 10/9/8/7/6 같은 값을 지어내지 않고 404
    saved = skills._RAW_DATA_CACHE.pop("Annie")
    try:
        from app.cache_engine import fast_cache
        fast_cache.delete_matching("champion_skills:")
        assert client().get("/api/champion-skills/Annie").status_code == 404
    finally:
        skills._RAW_DATA_CACHE["Annie"] = saved
    ok("챔피언 스킬: Data Dragon 값만 사용 (패치 버전·쿨다운 일치, 고정 선마/콤보/계수 없음)")


def test_discord_share_card_robust_and_not_invented():
    settings.discord_webhook_url = ""
    # 공유 API는 IP당 10분 5회 제한이 있어 요청마다 다른 방문자로 보낸다
    for body in ({"player": {"game_name": "a", "lp": "abc"}}, {"player": {"wins": "3", "losses": None}},
                 {"summary": {"most_champions": ["Ahri", None]}}, {"player": {"league_points": "1,200"}}):
        res = client().post("/api/discord/share/player", json=body)
        assert res.status_code == 200, (body, res.status_code)
    md = client().post("/api/discord/share/player", json={"player": {"game_name": "Hide on bush", "tag_line": "KR1"}}).json()["markdown"]
    assert "50%" not in md and "3.00:1" not in md and "최근 20전" not in md, md
    md = client().post("/api/discord/share/player", json={"player": {"game_name": "x", "wins": 30, "losses": 10}}).json()["markdown"]
    assert "75.0%" in md and "30승 10패" in md, md
    ok("디스코드 전적 공유: 잘못된 값에도 500 없음, 없는 승률·KDA를 50%·3.00:1로 채우지 않음")


def test_discord_duo_webhook_no_fake_invite():
    sent = []

    class _Resp:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    orig_urlopen, orig_url = discord_service.urllib.request.urlopen, settings.discord_webhook_url
    discord_service.urllib.request.urlopen = lambda req, timeout=None: (sent.append(req.data.decode("utf-8")), _Resp())[1]
    settings.discord_webhook_url = "https://discord.com/api/webhooks/1/test"
    try:
        discord_service.send_duo_post_webhook({"game_name": "a", "voice": True, "room_name": "방](https://evil.example)"})
    finally:
        discord_service.urllib.request.urlopen, settings.discord_webhook_url = orig_urlopen, orig_url
    assert sent and "lolgg-duo" not in sent[0] and "evil.example)" not in sent[0].replace("\\", ""), sent
    assert "](https://evil" not in sent[0]
    ok("듀오 웹후크: 링크 없는 글에 가짜 초대 주소를 붙이지 않음, 방 이름으로 링크 문법 주입 불가")


def test_telegram_cards():
    fin = calculate_financial_summary(dau=45000)
    card = format_telegram_finance_card(fin["profitability"])
    assert "A+" not in card and "추정" in card and " 0원" not in card, card
    full = format_telegram_finance_card(fin)
    assert f"{fin['revenue_breakdown']['monthly_ad_revenue_krw']:,}원" in full
    assert f"{fin['cost_breakdown']['monthly_infra_cost_krw']:,}원" in full

    card = format_telegram_player_card({"game_name": "<b>x&y", "tag_line": "KR1", "lp": "n/a"}, {})
    assert "&lt;b&gt;x&amp;y" in card and "50%" not in card
    ok("텔레그램 카드: 재무 추정치 매출·비용이 0원으로 찍히지 않음, 소환사 이름 HTML 이스케이프")


def test_inhouse_balance():
    from app import inhouse
    assert inhouse.power("IRON", "IV", 0) == 0
    assert inhouse.power("GOLD", "I", 50) == 3 * 400 + 300 + 50
    assert inhouse.power("MASTER", "I", 120) == inhouse.MASTER_BASE + 120
    assert inhouse.power("UNRANKED") is None
    tiers = ["CHALLENGER", "DIAMOND", "DIAMOND", "EMERALD", "PLATINUM", "GOLD", "GOLD", "SILVER", "BRONZE", "UNRANKED"]
    players = [{"name": f"p{i}", "tier": t, "rank": "II", "lp": 10} for i, t in enumerate(tiers)]
    res = inhouse.balance(players)
    best = res["options"][0]
    assert len(best["blue"]["players"]) == 5 and len(best["red"]["players"]) == 5
    assert best["diff"] == abs(best["blue"]["total"] - best["red"]["total"])
    assert best["diff"] <= min(o["diff"] for o in res["options"]) or best["position_clash"] < max(o["position_clash"] for o in res["options"])
    assert res["unranked_estimate"] is not None
    # 포지션이 겹치지 않는 나누기를 우선
    pos = ["TOP", "TOP", "JUNGLE", "JUNGLE", "MID", "MID", "ADC", "ADC", "SUPPORT", "SUPPORT"]
    same = [{"name": f"q{i}", "tier": "GOLD", "rank": "II", "lp": 0, "position": pos[i]} for i in range(10)]
    assert inhouse.balance(same)["options"][0]["position_clash"] == 0
    r = client().post("/api/inhouse/balance", json={"players": players})
    assert r.status_code == 200 and r.json()["options"][0]["diff"] == best["diff"], r.text
    assert client().post("/api/inhouse/balance", json={"players": players[:9]}).status_code == 422


def test_bot_inhouse_requires_secret_and_uses_linked_tiers():
    import os
    from unittest import mock
    members = [{"discord_id": str(1000 + i), "discord_name": f"m{i}"} for i in range(10)]
    body = {"members": members, "requested_by": members[0]}
    with mock.patch.dict(os.environ, {"BOT_API_SECRET": "x" * 20}):
        assert client().post("/api/bot/inhouse", json=body).status_code == 403
        with mock.patch("app.community_rank.member_tiers", return_value={"1000": {"tier": "GOLD", "rank": "I", "lp": 10}}):
            r = client().post("/api/bot/inhouse", json=body, headers={"X-Bot-Secret": "x" * 20})
    assert r.status_code == 200, r.text
    everyone = r.json()["options"][0]["blue"]["players"] + r.json()["options"][0]["red"]["players"]
    linked = [p for p in everyone if p["linked"]]
    assert len(linked) == 1 and linked[0]["tier"] == "GOLD" and not linked[0]["estimated"]
    assert all(p["estimated"] for p in everyone if not p["linked"])


def test_inhouse_records():
    import os
    from unittest import mock
    from test_support import admin_client
    blue = [{"name": f"B{i}"} for i in range(5)]
    red = [{"name": f"R{i}"} for i in range(4)] + [{"name": "Discord", "discord_id": "777"}]
    c = client()
    gid = c.post("/api/inhouse/games", json={"blue": blue, "red": red}).json()["id"]
    assert client().post(f"/api/inhouse/games/{gid}/result", json={"winner": "blue"}).status_code == 403  # 다른 사람
    assert c.post(f"/api/inhouse/games/{gid}/result", json={"winner": "green"}).status_code == 422
    assert c.post(f"/api/inhouse/games/{gid}/result", json={"winner": "red"}).status_code == 200
    assert c.post("/api/inhouse/games/99999/result", json={"winner": "red"}).status_code == 404
    st = client().get("/api/inhouse/stats").json()
    by = {p["name"]: p for p in st["players"]}
    assert by["R0"]["wins"] == 1 and by["B0"]["losses"] == 1 and by["Discord"]["win_rate"] == 100.0
    assert st["recent"][0]["id"] == gid and st["recent"][0]["winner"] == "red"
    # 관리자는 바꿀 수 있음
    assert admin_client(app).post(f"/api/inhouse/games/{gid}/result", json={"winner": "blue"}).status_code == 200
    # 봇: 저장한 디스코드 사용자만 결과 지정
    me, other = {"discord_id": "42", "discord_name": "me"}, {"discord_id": "43", "discord_name": "x"}
    h = {"X-Bot-Secret": "y" * 20}
    with mock.patch.dict(os.environ, {"BOT_API_SECRET": "y" * 20}):
        bid = client().post("/api/bot/inhouse/games", json={"blue": blue, "red": red, "requested_by": me}, headers=h).json()["id"]
        assert client().post(f"/api/bot/inhouse/games/{bid}/result", json={"winner": "blue", "requested_by": other}, headers=h).status_code == 403
        assert client().post(f"/api/bot/inhouse/games/{bid}/result", json={"winner": "blue", "requested_by": me}, headers=h).status_code == 200
        assert client().post("/api/bot/inhouse/games", json={"blue": blue, "red": red, "requested_by": me}).status_code == 403
    # 삭제는 관리자 콘솔에서만
    assert client().delete(f"/api/admin/inhouse/games/{gid}").status_code in (401, 403, 404)
    assert admin_client(app).delete(f"/api/admin/inhouse/games/{gid}").status_code == 200
    assert admin_client(app).delete(f"/api/admin/inhouse/games/{gid}").status_code == 404
    assert all(g["id"] != gid for g in client().get("/api/inhouse/stats").json()["recent"])


def test_pubg_socket():
    import os
    import httpx
    from unittest import mock
    import app.pubg_api as pubg
    from app.cache_engine import fast_cache
    from app import duo_games
    with mock.patch.dict(os.environ, {"PUBG_API_KEY": ""}):
        assert client().get("/api/pubg/player", params={"name": "Tester"}).status_code == 503
        assert not next(g for g in duo_games.public_config()["games"] if g["id"] == "pubg")["has_stats"]
    seen = []

    def handler(req):
        seen.append(req.url.path)
        assert req.headers["Authorization"] == "Bearer k" and "vnd.api+json" in req.headers["Accept"]
        if req.url.path.endswith("/players") and req.url.params.get("filter[playerNames]") == "Nobody":
            return httpx.Response(404)
        if req.url.path.endswith("/players"):
            return httpx.Response(200, json={"data": [{"id": "account.abc", "attributes": {"name": "Tester"}}]})
        if req.url.path.endswith("/seasons"):
            return httpx.Response(200, json={"data": [{"id": "s1", "attributes": {"isCurrentSeason": False}},
                                                      {"id": "s2", "attributes": {"isCurrentSeason": True}}]})
        if req.url.path.endswith("/seasons/s2/ranked"):
            return httpx.Response(200, json={"data": {"attributes": {"rankedGameModeStats": {"squad": {
                "currentTier": {"tier": "Gold", "subTier": "2"}, "currentRankPoint": 2250, "roundsPlayed": 10,
                "wins": 1, "top10Ratio": 0.4, "kda": 1.5, "damageDealt": 2500}}}}})
        return httpx.Response(500)

    orig = httpx.AsyncClient
    class Mock(orig):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **k)
    fast_cache.delete_matching("pubg:")
    with mock.patch.dict(os.environ, {"PUBG_API_KEY": "k"}), mock.patch.object(pubg.httpx, "AsyncClient", Mock):
        r = client().get("/api/pubg/player", params={"name": "Tester", "platform": "steam"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["season"] == "s2" and d["ranked"]["tier"] == "Gold" and d["ranked"]["avg_damage"] == 250
        assert all(p.startswith("/shards/steam/") for p in seen)
        n = len(seen)
        client().get("/api/pubg/player", params={"name": "Tester", "platform": "steam"})
        assert len(seen) == n, "10분 캐시"
        assert client().get("/api/pubg/player", params={"name": "Nobody"}).status_code == 404
        assert client().get("/api/pubg/player", params={"name": "<script>"}).status_code == 422
        assert next(g for g in duo_games.public_config()["games"] if g["id"] == "pubg")["has_stats"]
    fast_cache.delete_matching("pubg:")
    ok("배그 연결부: 키 없으면 503, 키 있으면 이번 시즌 경쟁전 기록, 캐시·입력 검증")


def test_weekly_inhouse_king_announce():
    import os
    from unittest import mock
    from app import inhouse, community_rank
    from app.database import get_connection
    conn = get_connection(); conn.execute("DELETE FROM inhouse_games"); conn.commit(); conn.close()
    blue = [{"name": "King"}] + [{"name": f"b{i}"} for i in range(4)]
    red = [{"name": f"r{i}"} for i in range(5)]
    assert community_rank.weekly_inhouse_king() is None
    for _ in range(3):
        gid = inhouse.record_game(blue, red, "me")
        inhouse.set_result(gid, "blue", "me")
    king = community_rank.weekly_inhouse_king()
    assert king and king["wins"] == 3 and king["losses"] == 0
    sent = []
    with mock.patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/x", "WEEKLY_MVP_ANNOUNCE": "1"}),          mock.patch("app.community_rank.weekly_mvp", return_value=None),          mock.patch("app.services.discord_service.send_discord_webhook", side_effect=lambda m, *a, **k: sent.append(m)):
        conn = get_connection(); conn.execute("CREATE TABLE IF NOT EXISTS community_state (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("DELETE FROM community_state"); conn.commit(); conn.close()
        assert community_rank.post_weekly_mvp_if_due()
    assert sent and sent[0]["embeds"][0]["title"].endswith("내전 왕"), sent
    ok("주간 알림: MVP 가 없어도 이번 주 내전 왕(3판 이상 최다승)을 올림")


if __name__ == "__main__":
    print("=" * 80)
    print("🧮 [Analytics Engines Suite] 열린 경로의 생성 데이터 누출·오류 회귀 검증")
    print("=" * 80)
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print("=" * 80)
    print(f"🎉 분석 엔진 회귀 테스트 {len(tests)}개 전부 통과")
    print("=" * 80)
