"""
실데이터 계층 검증 (app/real_data.py)

라이엇 API 응답 형식(Account-V1, League-V4, Match-V5, Spectator-V5)을 따른 픽스처로
riot_client 를 대체해, 네트워크 없이 다음을 검증한다.
- 라이엇 응답이 화면용 구조로 정확히 변환되는지 (값을 지어내지 않는지)
- API 키가 없거나 만료되면 가짜 데이터 대신 오류를 돌려주는지
- 매치 상세가 DB에 캐시되어 다시 요청하지 않는지
- 생성 데이터 기능이 막혀 있는지
"""
import asyncio
import hashlib
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from test_support import riot_http, sandbox_env_writes, use_temp_db

sandbox_env_writes()
use_temp_db()

from fastapi.testclient import TestClient

import app.real_data as real_data
from app.cache_engine import fast_cache
from app.config import settings
from app.database import format_player_dict, get_connection, get_player_by_riot_id, upsert_player
from app.ddragon import DDRAGON_VERSION
from app.main import app
from app.riot_client import RiotAPIError, riot_client

ME = "A" * 78
OTHER = ["B" * 77 + str(i) for i in range(9)]


def ok(msg):
    print(f"  [PASS] {msg}")


def participant(puuid, team, champ, pos, win, k, d, a, name, items=(3031, 3006, 0, 0, 0, 0), keystone=8010, sub=8400):
    return {
        "puuid": puuid, "teamId": team, "championName": champ, "teamPosition": pos, "win": win,
        "kills": k, "deaths": d, "assists": a, "champLevel": 16, "riotIdGameName": name, "riotIdTagline": "KR1",
        "totalMinionsKilled": 180, "neutralMinionsKilled": 20, "goldEarned": 12345, "timePlayed": 1800,
        "totalDamageDealtToChampions": 20000 + k * 1000, "totalDamageTaken": 15000,
        "visionWardsBoughtInGame": 2, "wardsPlaced": 9, "visionScore": 25,
        "item0": items[0], "item1": items[1], "item2": items[2], "item3": items[3], "item4": items[4], "item5": items[5], "item6": 3340,
        "summoner1Id": 4, "summoner2Id": 14,
        "perks": {"styles": [{"style": 8000, "selections": [{"perk": keystone}]}, {"style": sub, "selections": []}]},
        "pentaKills": 0, "quadraKills": 0, "tripleKills": 1 if k >= 6 else 0, "doubleKills": 1 if k >= 3 else 0,
    }


def match_fixture(match_id, duration=1800, my_win=True):
    me = participant(ME, 100, "Ahri", "MIDDLE", my_win, 8, 2, 10, "실제소환사")
    team = [participant(OTHER[i], 100, c, p, my_win, 3, 4, 6, f"아군{i}")
            for i, (c, p) in enumerate([("Garen", "TOP"), ("LeeSin", "JUNGLE"), ("Jinx", "BOTTOM"), ("Thresh", "UTILITY")])]
    enemy = [participant(OTHER[4 + i], 200, c, p, not my_win, 2, 5, 3, f"적{i}")
             for i, (c, p) in enumerate([("Darius", "TOP"), ("Vi", "JUNGLE"), ("Zed", "MIDDLE"), ("Caitlyn", "BOTTOM"), ("Lux", "UTILITY")])]
    return {
        "metadata": {"matchId": match_id},
        "info": {"gameDuration": duration, "gameEndTimestamp": 1_792_000_000_000, "queueId": 420,
                 "gameVersion": "16.21.1", "participants": [me] + team + enemy},
    }


calls = {"match_detail": 0}


async def fake_profile(game_name, tag_line):
    if game_name == "없는소환사":
        raise RiotAPIError(404, f"소환사 '{game_name}#{tag_line}'을(를) 찾을 수 없습니다.")
    puuid = ME if (game_name == "실제소환사" and tag_line == "KR1") else (hashlib.sha256(f"{game_name}#{tag_line}".encode("utf-8")).hexdigest() + "00000000000000")
    return {"puuid": puuid, "game_name": game_name, "tag_line": tag_line, "profile_icon_id": 1, "summoner_level": 321,
            "tier": "GOLD", "rank_tier": "II", "league_points": 55, "wins": 30, "losses": 25, "queue_type": "RANKED_SOLO_5x5",
            "flex_tier": "UNRANKED", "flex_rank_tier": "", "flex_lp": 0, "flex_wins": 0, "flex_losses": 0}


async def fake_match_ids(puuid, count=20):
    return ["KR_1", "KR_2", "KR_3"][:count]


async def fake_match_detail(match_id):
    calls["match_detail"] += 1
    return {"KR_1": match_fixture("KR_1"), "KR_2": match_fixture("KR_2", my_win=False), "KR_3": match_fixture("KR_3", duration=200)}[match_id]


async def fake_spectator(puuid):
    return {
        "gameId": 7000000001, "gameQueueConfigId": 420, "gameLength": 615, "platformId": "KR",
        "observers": {"encryptionKey": "abcDEF123+/="},
        "bannedChampions": [{"championId": 157, "teamId": 100}, {"championId": -1, "teamId": 200}],
        "participants": [
            {"puuid": ME, "teamId": 100, "championId": 103, "riotId": "실제소환사#KR1", "spell1Id": 4, "spell2Id": 14,
             "perks": {"perkIds": [8112], "perkSubStyle": 8300}},
            {"puuid": OTHER[0], "teamId": 200, "championId": 238, "riotId": "상대#KR2", "spell1Id": 4, "spell2Id": 12,
             "perks": {"perkIds": [8010], "perkSubStyle": 8400}},
            {"teamId": 200, "championId": 555, "riotId": "Pyke", "spell1Id": 4, "spell2Id": 14,
             "perks": {"perkIds": [8010], "perkSubStyle": 8400}},  # 이름을 숨긴 소환사: puuid 없음
        ],
    }


async def fake_league(tier="CHALLENGER"):
    return {"entries": [
        {"puuid": OTHER[0], "leaguePoints": 1500, "wins": 300, "losses": 200},
        {"puuid": OTHER[1], "leaguePoints": 1800, "wins": 400, "losses": 250},
        {"puuid": OTHER[2], "leaguePoints": 1200, "wins": 100, "losses": 90},
    ]}


async def fake_account(puuid):
    if puuid == OTHER[0]:
        return None  # 이름을 확인 못 한 항목
    return {"gameName": f"챌린저{puuid[-1]}", "tagLine": "KR1"}


def install_fakes():
    settings.riot_api_key = "RGAPI-test-key"
    riot_client.reset_key_status()
    riot_client.fetch_full_player_profile = fake_profile
    riot_client.get_match_ids_by_puuid = fake_match_ids
    riot_client.get_match_detail = fake_match_detail
    riot_client.get_spectator_active_game_by_puuid = fake_spectator
    riot_client.get_apex_league = fake_league
    riot_client.get_account_by_puuid = fake_account


def test_convert_match_uses_only_riot_values():
    m = real_data.convert_match(match_fixture("KR_1"), ME)
    assert m["win"] is True and m["game_mode"] == "솔로랭크"
    assert (m["kills"], m["deaths"], m["assists"]) == (8, 2, 10) and m["kda_ratio"] == 9.0
    assert m["champ_name"] == "아리" and m["champ_img"].endswith(f"/{DDRAGON_VERSION}/img/champion/Ahri.png")
    assert m["cs"]["total"] == 200 and m["cs_per_min"] == round(200 / 30, 1)
    assert [i["id"] for i in m["items"]] == [3031, 3006] and m["items"][0]["name"], m["items"]
    assert m["spells"][0]["name"] == "점멸" and m["primary_rune_data"]["name"] == "정복자"
    assert m["secondary_rune"]["name"] == "결의"
    assert m["kill_participation"] == round(18 / (8 + 4 * 3) * 100)
    assert m["position"] == "MID" and len(m["team1"]) == 5 and len(m["team2"]) == 5
    assert all(p["tier"] == "" for p in m["team1"] + m["team2"]), "티어는 매치 데이터에 없으므로 비워야 함"
    assert m["coach_metrics"] is None
    remake = real_data.convert_match(match_fixture("KR_3", duration=200), ME)
    assert remake["is_remake"] and remake["op_badge"] is None
    ok("Match-V5 → 화면 구조 변환 (KDA·아이템·주문·룬·포지션, 티어 미기재, 다시하기 처리)")


def test_ai_coach_report_uses_real_numbers_only():
    import time
    import httpx
    from app import ai_coach

    matches = [real_data.convert_match(match_fixture(f"KR_C{i}", my_win=i % 2 == 0), ME) for i in range(5)]
    ai_coach._bench_cache["bench"] = (time.time(), {"MIDDLE": {
        "cs_per_min": 8.0, "deaths": 3.0, "kill_participation": 60.0,
        "damage_per_min": 900.0, "gold_per_min": 450.0, "games": 500}})
    try:
        rep = ai_coach.build_coach_report({"game_name": "코치대상", "tag_line": "KR1"}, matches)
        assert rep["ready"] and rep["main_position"] == "MID" and rep["games_analyzed"] == 5, rep
        by_key = {m["key"]: m for m in rep["metrics"]}
        assert by_key["cs_per_min"]["value"] == matches[0]["cs_per_min"] and by_key["cs_per_min"]["benchmark"] == 8.0
        assert by_key["deaths"]["value"] == matches[0]["deaths"]
        assert all(0 <= m["score"] <= 100 for m in rep["metrics"])
        weak = {m["key"] for m in rep["metrics"] if m["score"] < 45}
        assert len(rep["tips"]) == min(2, len(weak)), "팁은 고티어 평균보다 낮은 지표에서만"
        assert rep["win_rate"] == 60.0 and rep["champion_pool"][0]["games"] == 5
        assert not ai_coach.build_coach_report({}, matches[:2])["ready"], "랭크 3판 미만이면 코칭하지 않음"

        # 키가 없으면 AI 요약 없음, 있으면 리포트 수치만 보내고 응답 문장을 그대로 쓴다
        assert asyncio.run(ai_coach.ai_summary(rep)) is None
        sent = []

        def anthropic(req):
            sent.append(req)
            return httpx.Response(200, json={"content": [{"type": "text", "text": "데스를 줄이세요."}]})

        settings.anthropic_api_key = "sk-test"
        with riot_http(anthropic):
            assert asyncio.run(ai_coach.ai_summary(rep)) == "데스를 줄이세요."
        assert sent[0].url.host == "api.anthropic.com" and sent[0].headers["x-api-key"] == "sk-test"
        assert "코치대상" not in sent[0].content.decode(), "소환사 이름은 외부 AI로 보내지 않음"
    finally:
        settings.anthropic_api_key = ""
        ai_coach._bench_cache.clear()

    saved = settings.riot_api_key
    settings.riot_api_key = ""
    try:
        c = TestClient(app)
        codes = [c.get("/api/ai-coach", params={"name": "아무개", "tag": "KR1"}).status_code for _ in range(7)]
    finally:
        settings.riot_api_key = saved
    assert codes[0] == 503 and codes[-1] == 429, codes
    ok("AI 코치: 실제 전적 vs 고티어 평균 지표·팁, AI 요약은 수치만 전달, 키 없으면 503, IP당 호출 제한")


def test_server_ranking_link_and_board():
    """닉네임 등록(라이엇에 있는 계정만, 미인증)은 티어 역할·팀 나누기용, 서버 랭킹에는 라이엇 로그인 인증 계정만"""
    from app import community_rank
    from app import main as main_mod
    from app.database import get_connection
    install_fakes()
    c = TestClient(app)
    community_rank._ensure_tables()
    conn = get_connection()
    conn.execute("DELETE FROM member_accounts")
    conn.commit()
    conn.close()

    from app.riot_client import RiotAPIError

    async def fake_fetch(name, tag, allow_cached=True):
        return {"puuid": "p" * 78, "game_name": name, "tag_line": tag, "tier": "GOLD"}

    async def fake_account(name, tag):
        if "".join(name.split()) != "실제소환사":  # 라이엇처럼 띄어쓰기 무시
            raise RiotAPIError(404, "없음")
        return {"puuid": "p" * 78, "gameName": "실제소환사", "tagLine": "KR1"}
    orig_fetch, orig_acc = main_mod.fetch_player, riot_client.get_account_by_riot_id
    main_mod.fetch_player, riot_client.get_account_by_riot_id = fake_fetch, fake_account
    try:
        assert c.post("/api/me/riot-account", json={"game_name": "실제 소환사", "tag_line": " KR 1"}).status_code == 200, "띄어쓰기 상관없음"
        assert c.post("/api/me/riot-account", json={"game_name": "가짜닉", "tag_line": "KR1"}).status_code == 404, "없는 닉네임 거부"
        r = c.post("/api/me/riot-account", json={"game_name": "실제소환사", "tag_line": "KR1"})
        assert r.status_code == 200 and r.json()["account"]["verified"] is False, r.text
        # 봇 /계정등록 도 같은 규칙 (봇 비밀값 필요, 없는 닉네임 거부)
        import os
        saved_secret = os.environ.get("BOT_API_SECRET")
        os.environ["BOT_API_SECRET"] = "b" * 32
        try:
            bm = {"discord_id": "5501", "discord_name": "봇멤버"}
            assert c.post("/api/bot/riot-account", json={"member": bm, "game_name": "실제소환사", "tag_line": "KR1"}).status_code == 403
            h = {"X-Bot-Secret": "b" * 32}
            assert c.post("/api/bot/riot-account", headers=h, json={"member": bm, "game_name": "가짜닉", "tag_line": "KR1"}).status_code == 404
            assert c.post("/api/bot/riot-account", headers=h, json={"member": bm, "game_name": "실제소환사", "tag_line": "KR1"}).status_code == 200
            assert community_rank.get_member("5501")["verified"] == 0 and community_rank.get_member("5501")["discord_name"] == "봇멤버"
        finally:
            if saved_secret is None:
                os.environ.pop("BOT_API_SECRET", None)
            else:
                os.environ["BOT_API_SECRET"] = saved_secret
    finally:
        main_mod.fetch_player, riot_client.get_account_by_riot_id = orig_fetch, orig_acc
    assert c.get("/api/me").json()["account"] == {"game_name": "실제소환사", "tag_line": "KR1", "verified": False}
    assert c.get("/api/server-ranking").json()["total"] == 0, "등록만 한 계정은 서버 랭킹에 없음"
    picks = c.get("/api/inhouse/members").json()["members"]
    assert any(m["game_name"] == "실제소환사" and m["verified"] is False for m in picks), "내전 참가자 목록에는 등록 멤버도"
    tiers = {m["discord_id"]: m["tier"] for m in community_rank.guild_member_tiers("")}
    assert "local-dev" not in tiers, "디스코드 ID(숫자)가 아닌 행은 티어 역할 대상 아님"

    community_rank.link_account("local-dev", {"puuid": "p" * 78, "game_name": "실제소환사", "tag_line": "KR1"})
    assert c.get("/api/me").json()["account"] == {"game_name": "실제소환사", "tag_line": "KR1", "verified": True}
    board = c.get("/api/server-ranking").json()
    assert board["total"] == 1 and board["members"][0]["game_name"] == "실제소환사" and board["members"][0]["verified"] is True
    assert c.delete("/api/me/riot-account").status_code == 200
    assert c.get("/api/server-ranking").json()["total"] == 0
    ok("서버 랭킹: 닉네임 등록은 실제 계정만·미인증 표시·랭킹 제외, 라이엇 인증 계정만 순위표, 연결 해제")



def test_member_match_cache_only_missing_ranked():
    """멤버 최근 게임 받기: 솔로·자유랭크 목록만 묻고, 캐시에 있는 매치는 다시 받지 않는다"""
    import asyncio, json
    from app import community_rank
    from app.riot_client import riot_client
    from app.database import get_connection
    real_data.init_match_cache()
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO match_cache (match_id, data, game_end, fetched_at) VALUES ('KR_OLD', ?, 0, 0)",
                 (json.dumps({"info": {"queueId": 420}}),))
    conn.commit()
    conn.close()
    asked, fetched = [], []

    async def ids(puuid, count=20, queue=None, start_time=None):
        asked.append(queue)
        assert start_time and count == community_rank.MEMBER_MATCH_LIMIT
        return ["KR_OLD", "KR_NEW1"] if queue == 420 else ["KR_NEW2"]

    async def detail(mid):
        fetched.append(mid)
        return {"metadata": {"matchId": mid}, "info": {"queueId": 420, "gameEndTimestamp": 1, "participants": []}}
    o_ids, o_detail, o_gap = riot_client.get_match_ids_by_puuid, riot_client.get_match_detail, community_rank.MEMBER_MATCH_GAP_SEC
    riot_client.get_match_ids_by_puuid, riot_client.get_match_detail = ids, detail
    community_rank.MEMBER_MATCH_GAP_SEC = 0
    try:
        got = asyncio.run(community_rank.cache_member_matches("p" * 78))
    finally:
        riot_client.get_match_ids_by_puuid, riot_client.get_match_detail = o_ids, o_detail
        community_rank.MEMBER_MATCH_GAP_SEC = o_gap
        conn = get_connection()
        conn.execute("DELETE FROM match_cache WHERE match_id IN ('KR_OLD', 'KR_NEW1', 'KR_NEW2')")
        conn.commit()
        conn.close()
    assert asked == [420, 440], asked
    assert fetched == ["KR_NEW1", "KR_NEW2"] and got == 2, fetched
    ok("멤버 최근 게임: 솔로·자유랭크만, 캐시에 없는 매치만 받기")

def test_server_duos_and_mvp():
    """같이 한 게임: 캐시된 실제 매치에서 같은 팀 멤버 쌍만, 솔로·자유랭크만. MVP: 7일 LP 상승 최대"""
    import json, time
    from app import community_rank
    from app.database import get_connection
    community_rank._ensure_tables()
    real_data.init_match_cache()
    conn = get_connection()
    conn.execute("DELETE FROM member_accounts")
    for i, pu in enumerate(("PU_A", "PU_B", "PU_C")):
        conn.execute("INSERT INTO member_accounts (discord_id, discord_name, puuid, game_name, tag_line, linked_at, verified) VALUES (?,?,?,?,?,?,1)",
                     (f"d{i}", f"멤버{i}", pu, f"이름{i}", "KR1", 0))
    now_ms = int(time.time() * 1000)

    def match(mid, queue, parts):
        info = {"queueId": queue, "participants": [{"puuid": pu, "teamId": t, "win": w} for pu, t, w in parts]}
        conn.execute("INSERT OR REPLACE INTO match_cache (match_id, data, game_end, fetched_at) VALUES (?,?,?,?)",
                     (mid, json.dumps({"info": info}), now_ms, 0))
    match("M1", 420, [("PU_A", 100, True), ("PU_B", 100, True), ("PU_C", 200, False)])   # A+B 같은 팀 승, C 상대 팀
    match("M2", 420, [("PU_A", 100, False), ("PU_B", 100, False)])                      # A+B 패
    match("M3", 450, [("PU_A", 100, True), ("PU_C", 100, True)])                        # 칼바람: 제외
    conn.commit()
    conn.close()
    community_rank._DUO_MEMO.clear()
    duos = community_rank.server_duos()["duos"]
    assert len(duos) == 1, duos
    assert {duos[0]["a"]["game_name"], duos[0]["b"]["game_name"]} == {"이름0", "이름1"}
    assert duos[0]["games"] == 2 and duos[0]["win_rate"] == 50.0

    orig = community_rank.leaderboard
    community_rank.leaderboard = lambda *a: {"members": [
        {"game_name": "x", "lp_change_7d": 30}, {"game_name": "y", "lp_change_7d": 85}, {"game_name": "z", "lp_change_7d": None}]}
    try:
        assert community_rank.weekly_mvp()["game_name"] == "y"
        community_rank.leaderboard = lambda *a: {"members": [{"game_name": "x", "lp_change_7d": -10}]}
        assert community_rank.weekly_mvp() is None, "LP가 오른 멤버가 없으면 MVP 없음"
    finally:
        community_rank.leaderboard = orig
    conn = get_connection()
    conn.execute("DELETE FROM member_accounts")
    conn.execute("DELETE FROM match_cache WHERE match_id IN ('M1','M2','M3')")
    conn.commit()
    conn.close()
    ok("서버 듀오(같은 팀·랭크 게임만)와 이번 주 MVP(7일 LP 상승 최대) 계산")


def test_player_cached_summary_from_match_cache():
    """멀티서치용: 저장된 랭크 게임에서 모스트·주 포지션 (칼바람 제외, 라이엇 호출 없음)"""
    import json, time
    from app.database import get_connection
    from app.match_collector import player_cached_summary
    real_data.init_match_cache()
    pu = "P" * 78  # 라이엇 puuid 형식(78자)
    conn = get_connection()
    now = int(time.time() * 1000)
    rows = [("CS1", 420, 103, "MIDDLE", True), ("CS2", 420, 103, "MIDDLE", False), ("CS3", 440, 7, "MIDDLE", True), ("CS4", 450, 1, "", True)]
    for mid, q, champ, pos, win in rows:
        info = {"queueId": q, "participants": [{"puuid": pu, "championId": champ, "teamPosition": pos, "win": win, "kills": 5, "deaths": 2, "assists": 3}]}
        conn.execute("INSERT OR REPLACE INTO match_cache (match_id, data, game_end, fetched_at) VALUES (?,?,?,?)",
                     (mid, json.dumps({"info": info}), now, 0))
    conn.commit()
    conn.close()
    try:
        s = player_cached_summary(pu)
        assert s["games"] == 3, "칼바람(450) 제외"
        assert s["main_position"] == "MID" and s["top_champions"][0]["name"] == "아리" and s["top_champions"][0]["games"] == 2
        assert player_cached_summary("Q" * 78) is None
    finally:
        conn = get_connection()
        conn.execute("DELETE FROM match_cache WHERE match_id IN ('CS1','CS2','CS3','CS4')")
        conn.commit()
        conn.close()
    ok("멀티서치: 저장된 랭크 게임에서 모스트·주 포지션 (칼바람 제외)")


def test_rank_up_announcement_only_on_climb():
    from app.community_rank import rank_up_message as msg
    up = msg("민성", "A", "KR1", {"tier": "GOLD", "rank_tier": "I"}, {"tier": "PLATINUM", "rank_tier": "IV"})
    assert "골드 I → 플래티넘 IV" in up["embeds"][0]["description"]
    assert msg("", "A", "KR1", {"tier": "GOLD", "rank_tier": "II", "league_points": 5},
               {"tier": "GOLD", "rank_tier": "II", "league_points": 95}) is None, "같은 디비전 LP 변화는 알리지 않음"
    assert msg("", "A", "KR1", {"tier": "GOLD", "rank_tier": "III"}, {"tier": "GOLD", "rank_tier": "IV"}) is None, "강등은 알리지 않음"
    assert "마스터" in msg("", "A", "KR1", {"tier": "DIAMOND", "rank_tier": "I"}, {"tier": "MASTER", "rank_tier": "I"})["embeds"][0]["description"]
    assert "배치" in msg("x", "A", "KR1", {"tier": "UNRANKED"}, {"tier": "SILVER", "rank_tier": "II"})["embeds"][0]["description"]
    ok("서버 랭킹 승급 알림: 티어·디비전이 오를 때만 (LP 변화·강등 제외)")


def test_daily_db_backup_and_rotation():
    import os
    import sqlite3
    import tempfile
    from app import backup

    d = Path(tempfile.mkdtemp(prefix="opgg_backup_test_"))
    saved = os.environ.get("OPGG_BACKUP_DIR")
    os.environ["OPGG_BACKUP_DIR"] = str(d)
    try:
        conn = get_connection()
        conn.execute("CREATE TABLE IF NOT EXISTS backup_probe (v TEXT)")
        conn.execute("INSERT INTO backup_probe VALUES ('hello')")
        conn.commit()
        conn.close()
        for day in ("20200101", "20200102", "20200103"):
            (d / f"opgg-{day}.db").write_bytes(b"old")
        made = backup.run_backup(keep=2)
        assert sqlite3.connect(made).execute("SELECT v FROM backup_probe").fetchone()[0] == "hello"
        assert [p.name for p in backup.list_backups()] == [made.name, "opgg-20200103.db"], "최근 2개만 남김"
        assert not list(d.glob("*.tmp"))
    finally:
        if saved is None:
            os.environ.pop("OPGG_BACKUP_DIR", None)
        else:
            os.environ["OPGG_BACKUP_DIR"] = saved
    ok("DB 자동 백업: 서버 사용 중에도 온라인 백업, 오래된 백업 정리")


def test_summary_excludes_remakes():
    matches = [real_data.convert_match(match_fixture(f"KR_{i}", my_win=i % 2 == 0), ME) for i in range(4)]
    matches.append(real_data.convert_match(match_fixture("KR_R", duration=200), ME))
    s = real_data.summarize_matches(matches)
    assert (s["total_games"], s["wins"], s["losses"], s["remakes"]) == (4, 2, 2, 1)
    assert s["most_champions"][0]["name"] == "아리" and s["positions"]["MID"] == 4
    mates = s["played_with"]
    assert len(mates) == 4 and all((p["games"], p["wins"], p["losses"]) == (4, 2, 2) for p in mates), mates
    my_team = next(t for t in (matches[0]["team1"], matches[0]["team2"]) if any(r["is_me"] for r in t))
    assert {p["game_name"] for p in mates} == {r["game_name"] for r in my_team if not r["is_me"]}, "상대 팀은 제외"
    ok("전적 요약 (다시하기 제외 승패·모스트 챔피언·포지션·같은 팀으로 함께한 소환사)")


def test_no_api_key_means_no_data():
    saved = settings.riot_api_key
    settings.riot_api_key = ""
    try:
        c = TestClient(app)
        assert c.get("/api/player/아무개/KR1").status_code == 503
        assert c.get("/api/player/아무개/KR1/matches").status_code == 503
        assert c.get("/api/search", params={"q": "아무개#KR1"}).json()["mode"] == "not_found"
        assert get_player_by_riot_id("아무개", "KR1") is None, "키가 없을 때 가짜 프로필을 만들면 안 됨"
    finally:
        settings.riot_api_key = saved
    ok("API 키가 없으면 가짜 프로필/전적 대신 503·not_found, DB에 아무것도 만들지 않음")


def test_player_and_matches_via_api():
    install_fakes()
    c = TestClient(app)
    res = c.get("/api/search", params={"q": "실제소환사#KR1"})
    assert res.status_code == 200 and res.json()["mode"] == "exact", res.text
    profile = c.get("/api/player/실제소환사/KR1").json()["player"]
    assert profile["tier"] == "GOLD" and profile["tier_history"] == {"daily": [], "weekly": [], "monthly": []}
    assert profile["past_seasons"] == {} and profile["peak_tier"] is None and profile["past_tier_badges"] == []
    assert profile["flex_tier"] == "UNRANKED" and profile["flex_wins"] == 0, "자유랭크를 지어내면 안 됨"

    calls["match_detail"] = 0
    data = c.get("/api/player/실제소환사/KR1/matches", params={"count": 5, "refresh": True}).json()
    assert data["source"] == "riot_api" and len(data["matches"]) == 3 and data["summary"]["remakes"] == 1
    first_calls = calls["match_detail"]
    c.get("/api/player/실제소환사/KR1/matches", params={"count": 5, "refresh": True})
    assert first_calls == 3 and calls["match_detail"] == 3, "캐시된 매치를 다시 받으면 안 됨"
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM match_cache").fetchone()[0] == 3
    conn.close()

    assert c.get("/api/search", params={"q": "없는소환사#KR1"}).json()["mode"] == "not_found"
    assert c.get("/api/player/없는소환사/KR1").status_code == 404
    ok("검색·프로필·최근 전적 (라이엇 값만 사용, 매치 상세 DB 캐시, 없는 소환사 404)")


def test_live_game():
    install_fakes()
    data = TestClient(app).get("/api/player/실제소환사/KR1/ingame").json()
    assert data["is_active"] and data["real"] and data["game_mode"] == "솔로랭크" and data["game_length_sec"] == 615
    me = data["blue_team"][0]
    assert me["is_me"] and me["champ_name"] == "아리" and me["keystone"]["name"] == "감전" and me["spell2"]["name"] == "점화"
    assert data["red_team"][0]["tier"] is None, "모르는 소환사의 티어를 지어내면 안 됨"
    assert [b["name"] for b in data["bans_blue"]] == ["야스오"] and data["bans_red"] == []
    hidden = data["red_team"][1]
    assert hidden["hidden"] and hidden["game_name"] == "비공개 소환사" and hidden["tag_line"] == "" and not hidden["is_me"]
    ok("실시간 게임 (Spectator-V5 변환, 모르는 소환사 티어 미기재, 비공개 소환사)")


def test_live_game_scouting_info():
    install_fakes()

    api_calls = {"spectator": 0, "profile": 0, "mastery": 0}
    orig_spectator = riot_client.get_spectator_active_game_by_puuid
    orig_profile = riot_client.fetch_full_player_profile
    orig_mastery = getattr(riot_client, "get_champion_masteries_by_puuid", None)

    async def counting_spectator(puuid):
        api_calls["spectator"] += 1
        return await orig_spectator(puuid)

    async def counting_profile(name, tag):
        api_calls["profile"] += 1
        return await orig_profile(name, tag)

    async def counting_mastery(puuid, count=10):
        api_calls["mastery"] += 1
        return []

    riot_client.get_spectator_active_game_by_puuid = counting_spectator
    riot_client.fetch_full_player_profile = counting_profile
    riot_client.get_champion_masteries_by_puuid = counting_mastery

    try:
        # 1. 저장된 소환사 픽스처
        upsert_player(
            puuid=ME,
            game_name="실제소환사",
            tag_line="KR1",
            tier="GOLD",
            rank_tier="II",
            league_points=55,
            wins=30,
            losses=25,
        )

        # 2. 숙련도 DB에 행 추가 (아리 championId=103)
        real_data.init_champion_mastery_table()
        conn = get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO champion_mastery_real "
            "(puuid, champion_id, champion_points, champion_level, last_play_time, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ME, 103, 125000, 7, 1700000000, 1700000000)
        )
        conn.commit()
        conn.close()

        # 캐시 초기화 후 관전 데이터 조회
        fast_cache.delete("spectator:실제소환사:kr1")
        c = TestClient(app)
        res = c.get("/api/player/실제소환사/KR1/ingame")
        assert res.status_code == 200, res.text
        data = res.json()

        # A. 저장된 소환사: LP, 승률, 숙련도 확인
        me = data["blue_team"][0]
        assert me["is_me"] is True
        assert me["league_points"] == 55
        assert me["wins"] == 30
        assert me["losses"] == 25
        assert me["win_rate"] == 54.5
        assert me["rank_tier"] == "II"
        assert me["champ_mastery_level"] == 7
        assert me["champ_mastery_points"] == 125000

        # B. 모르는 소환사: 전부 None
        unknown = data["red_team"][0]
        assert unknown["tier"] is None
        assert unknown["display_tier"] is None
        assert unknown["league_points"] is None
        assert unknown["wins"] is None
        assert unknown["losses"] is None
        assert unknown["win_rate"] is None
        assert unknown["rank_tier"] is None
        assert unknown["champ_mastery_level"] is None
        assert unknown["champ_mastery_points"] is None

        # C. 비공개 소환사: 전부 None
        hidden = data["red_team"][1]
        assert hidden["hidden"] is True
        assert hidden["league_points"] is None
        assert hidden["wins"] is None
        assert hidden["losses"] is None
        assert hidden["win_rate"] is None
        assert hidden["rank_tier"] is None
        assert hidden["champ_mastery_level"] is None
        assert hidden["champ_mastery_points"] is None

        # D. 라이엇 가짜 함수 호출 횟수 검증 (spectator 1회 외 추가 라이엇 API 호출 없어야 함)
        assert api_calls["spectator"] == 1, "Spectator API는 1회만 호출되어야 함"
        assert api_calls["mastery"] == 0, "관전 변환에서 숙련도 라이엇 API를 새로 부르면 안 됨"
        assert api_calls["profile"] == 0, "이미 저장된 소환사는 프로필 라이엇 API를 다시 부르지 않아야 함"

        # E. wins+losses == 0 인 경우 win_rate 는 None
        upsert_player(
            puuid=ME,
            game_name="실제소환사",
            tag_line="KR1",
            tier="GOLD",
            rank_tier="II",
            league_points=0,
            wins=0,
            losses=0,
        )
        spectator_raw = asyncio.run(orig_spectator(ME))
        conv = real_data.convert_live_game(spectator_raw, ME)
        me_zero = conv["blue_team"][0]
        assert me_zero["league_points"] == 0
        assert me_zero["wins"] == 0
        assert me_zero["losses"] == 0
        assert me_zero["win_rate"] is None, "wins+losses가 0이면 win_rate는 None이어야 함"
        assert me_zero["champ_record"] is None, "수집 게임이 없으면 챔피언 전적을 지어내지 않음"
        from app import match_collector as mc
        conn = get_connection()
        conn.execute("INSERT OR IGNORE INTO collected_participants VALUES (?, 'KR_LIVE_1', 1, ?, 'MIDDLE', 1, 5, 1, 5)",
                     (ME, spectator_raw["participants"][0]["championId"]))
        conn.commit()
        conn.close()
        assert real_data.convert_live_game(spectator_raw, ME)["blue_team"][0]["champ_record"] == {"games": 1, "wins": 1, "win_rate": 100.0}
        assert mc.player_champion_record(ME, 99999) is None
    finally:
        riot_client.get_spectator_active_game_by_puuid = orig_spectator
        riot_client.fetch_full_player_profile = orig_profile
        if orig_mastery:
            riot_client.get_champion_masteries_by_puuid = orig_mastery

    ok("관전 플레이어 정보 보강 (저장된 소환사 LP·승률·숙련도, 미등록/숨김은 None, 새 라이엇 호출 없음)")


def test_challenger_ladder_keeps_real_ranks():
    install_fakes()
    res = asyncio.run(real_data.sync_challenger_ladder())
    assert res == {"status": "success", "synced_count": 2, "skipped": 1}
    rows = TestClient(app).get("/api/leaderboard").json()["results"]
    assert [(r["rank"], r["game_name"], r["league_points"]) for r in rows] == [(1, "챌린저1", 1800), (3, "챌린저2", 1200)]
    assert rows[0]["win_rate"] == round(400 / 650 * 100, 1)
    # 모스트 챔피언은 수집된 실제 게임에서만 (이 테스트엔 수집 게임이 없으므로 빈 목록), 지어낸 LP 추이는 없음
    assert rows[0]["most_champions"] == [] and "lp_history_7d" not in rows[0]
    conn = get_connection()
    top_puuid = conn.execute("SELECT puuid FROM ladder_real WHERE rank = 1").fetchone()[0]
    snaps = conn.execute("SELECT tier, league_points FROM rank_snapshots WHERE puuid = ?", (top_puuid,)).fetchall()
    conn.close()
    assert [tuple(s) for s in snaps] == [("CHALLENGER", 1800)], "래더 갱신 LP가 티어 변동 기록으로 남아야 함"
    ok("챌린저 랭킹 (실제 순위 유지, 이름 미확인 항목은 다른 이름으로 채우지 않고 제외, LP 기록 저장)")


def test_rate_limit_not_shown_as_empty_history():
    install_fakes()

    async def ids_429(puuid, count=20):
        raise RiotAPIError(429, "rate limited")

    riot_client.get_match_ids_by_puuid = ids_429
    c = TestClient(app)
    res = c.get("/api/player/실제소환사/KR1/matches", params={"count": 5, "refresh": True})
    assert res.status_code == 429, res.text
    riot_client.get_match_ids_by_puuid = fake_match_ids
    assert c.get("/api/player/실제소환사/KR1/matches", params={"count": 5}).status_code == 200, "실패 응답이 캐시되면 안 됨"
    ok("라이엇 429를 '전적 0개'로 숨기지 않고 429로 알림 (실패는 캐시하지 않음)")


def test_remake_flag_and_arena_teams():
    m = match_fixture("KR_9", duration=900)
    m["info"]["participants"][3]["gameEndedInEarlySurrender"] = True
    assert real_data.convert_match(m, ME)["is_remake"], "공식 다시하기 플래그를 써야 함"

    arena = match_fixture("KR_A")
    arena["info"]["queueId"] = 1700
    for i, p in enumerate(arena["info"]["participants"]):
        p["playerSubteamId"] = i // 2 + 1  # 2인 1팀
    conv = real_data.convert_match(arena, ME)
    assert len(conv["team1"]) == 2 and len(conv["team2"]) == 8
    assert all(r["op_badge"] is None for r in conv["team1"] + conv["team2"]), "2팀이 아니면 MVP/ACE를 매기지 않음"
    ok("다시하기 공식 플래그(gameEndedInEarlySurrender) + 아레나 등 다팀 모드 처리")


def test_ladder_summoner_id_fallback():
    install_fakes()

    async def league_old_schema(tier="CHALLENGER"):
        return {"entries": [{"summonerId": "SID-1", "leaguePoints": 1700, "wins": 10, "losses": 5}]}

    async def summoner_by_id(sid):
        return {"puuid": OTHER[5]}

    riot_client.get_apex_league = league_old_schema
    riot_client.get_summoner_by_id = summoner_by_id
    res = asyncio.run(real_data.sync_challenger_ladder())
    assert res["synced_count"] == 1
    rows = TestClient(app).get("/api/leaderboard").json()["results"]
    assert rows[0]["puuid"] == OTHER[5] and rows[0]["game_name"] == "챌린저5"
    riot_client.get_apex_league = fake_league
    ok("리그 엔트리에 puuid가 없으면 summonerId로 조회해 랭킹 구성")


def test_flex_rank_not_invented():
    row = {"tier": "DIAMOND", "rank_tier": "I", "wins": 10, "losses": 5, "league_points": 20,
           "game_name": "x", "tag_line": "KR1", "flex_tier": "", "flex_wins": 0, "flex_losses": 0}
    d = format_player_dict(row)
    assert d["flex_tier"] == "UNRANKED" and d["flex_wins"] == 0 and d["past_tier_badges"] == []
    ok("자유랭크·과거 시즌 배지를 솔로랭크에서 추정해 만들지 않음")


def test_synthetic_features_gated():
    c = TestClient(app)
    for path in ("/api/combo-synergy-featured", "/api/pro-tracker", "/api/spectator/live-game",
                 "/api/player/a/b/analysis", "/api/player/a/b/coach", "/api/patch-notes"):
        assert c.get(path).status_code == 404, path
    assert "window.SYNTHETIC_FEATURES = false" in c.get("/").text
    ok("생성(난수) 통계 API 삭제됨(404) + 화면 숨김 플래그")


def test_featured_spectator_is_labeled_sample_without_real_people():
    import json as _json
    c = TestClient(app)
    feed = c.get("/api/spectator/featured").json()
    assert feed["is_sample"] and feed["sample_notice"] and all(m["is_sample"] for m in feed["featured"])
    text = _json.dumps(feed, ensure_ascii=False)
    for real in ("Faker", "페이커", "Hide on bush", "Viper", "Chovy", "쵸비", "T1", "HLE", "GEN", "팬서", "정휘찬", "스트리머"):
        assert real not in text, f"샘플 데이터에 실존 인물/팀 이름 '{real}'이 남으면 안 됨"
    detail = c.get(f"/api/spectator/featured/{feed['featured'][0]['featured_id']}").json()
    assert detail["is_sample"] and detail["star_player"].startswith("샘플소환사")
    page = c.get("/").text
    assert "specSampleBanner" in page and "샘플 데이터" in page
    ok("추천 관전 피드: 정식 키 전까지 샘플 표시 + 실존 인물·팀 이름 제거")


def test_duo_posts_persist_in_db():
    import time as _time
    import app.duo_finder_engine as duo

    post, token = duo.create_duo_post(
        game_name="저장확인", tag_line="KR1", tier_kr="골드", my_position="MID", target_position="JUG",
        queue_type="솔로랭크", voice=False, title="DB 저장 확인", description="", most_champions=["아리"])
    assert post["id"] > 0 and post["created_at"] == "방금 전"
    stored = [p for p in duo._load_posts() if p["id"] == post["id"]]
    assert stored and stored[0]["title"] == "DB 저장 확인", "새로 불러와도 글이 남아 있어야 함 (재시작 후 유지)"
    assert duo.verify_duo_owner(post["id"], token) and not duo.verify_duo_owner(post["id"], token + "x")

    conn = get_connection()
    assert token not in conn.execute("SELECT owner_token_hash FROM duo_posts WHERE id = ?", (post["id"],)).fetchone()[0]
    conn.close()

    duo.toggle_duo_post_capacity(post["id"])
    assert [p for p in duo._load_posts() if p["id"] == post["id"]][0]["is_full"] is True, "상태 변경이 DB에 저장돼야 함"

    conn = get_connection()
    conn.execute("UPDATE duo_posts SET created_at = ? WHERE id = ?", (int(_time.time()) - duo.DUO_POST_TTL_SEC - 10, post["id"]))
    conn.commit()
    conn.close()
    assert not [p for p in duo._load_posts() if p["id"] == post["id"]], "24시간 지난 글은 목록에서 빠져야 함"
    ok("듀오 글 DB 저장 (재시작 후 유지, 토큰은 해시로 저장, 상태 변경 저장, 24시간 경과 글 제외)")


def test_ddragon_version_served():
    client = TestClient(app)
    js = "\n".join(client.get(f"/static/js/app/{f.name}").text for f in sorted(Path("static/js/app").glob("*.js")))
    assert "__DDRAGON_VER__" not in js and f"cdn/{DDRAGON_VERSION}/" in js
    assert "cdn/14.20.1" not in js
    ok(f"프런트 JS의 Data Dragon 버전 자동 치환 ({DDRAGON_VERSION})")


def _riot_account_server(accounts, summoners):
    """Account-V1 / Summoner-V4 / League-V4 를 흉내 내는 HTTP 핸들러 (accounts: '닉#태그' -> puuid)"""
    import httpx
    from urllib.parse import unquote

    def handler(req):
        path = req.url.raw_path.decode().split("?")[0]
        prefix = "/riot/account/v1/accounts/by-riot-id/"
        if path.startswith(prefix):
            name, _, tag = (unquote(x) for x in path[len(prefix):].partition("/"))
            puuid = accounts.get(f"{name}#{tag}")
            if not puuid:
                return httpx.Response(404, json={})
            return httpx.Response(200, json={"puuid": puuid, "gameName": name, "tagLine": tag})
        if "/lol/summoner/v4/summoners/by-puuid/" in path:
            puuid = path.rsplit("/", 1)[1]
            return httpx.Response(200, json=summoners[puuid]) if puuid in summoners else httpx.Response(404, json={})
        if "/lol/league/v4/entries/by-puuid/" in path:
            return httpx.Response(200, json=[])
        return httpx.Response(403, json={})
    return handler


def test_account_without_lol_summoner_is_404_not_invented():
    install_fakes()
    puuid = "S" * 78
    with riot_http(_riot_account_server({"롤안함#KR1": puuid}, {})):
        res = TestClient(app).get("/api/player/롤안함/KR1")
    assert res.status_code == 404, res.text
    assert get_player_by_riot_id("롤안함", "KR1") is None, "레벨 30·아이콘 29 같은 값을 지어내 저장하면 안 됨"
    ok("LoL 소환사 기록이 없는 라이엇 계정은 404 (레벨·아이콘을 지어내지 않음)")


def test_real_lookup_replaces_fake_row_with_same_riot_id():
    install_fakes()
    upsert_player(puuid="real-kr-0123456789ab", game_name="가짜충돌", tag_line="KR1", tier="CHALLENGER")
    real = "C" * 78
    with riot_http(_riot_account_server({"가짜충돌#KR1": real}, {real: {"profileIconId": 7, "summonerLevel": 88}})):
        c = TestClient(app)
        profile = c.get("/api/player/가짜충돌/KR1", params={"refresh": True})
        assert profile.status_code == 200 and profile.json()["player"]["puuid"] == real, profile.text
    matches = c.get("/api/player/가짜충돌/KR1/matches", params={"count": 5, "refresh": True})  # 매치 API는 픽스처 사용
    assert matches.status_code == 200, matches.text
    conn = get_connection()
    rows = conn.execute("SELECT puuid FROM players WHERE game_name = '가짜충돌'").fetchall()
    conn.close()
    assert [r[0] for r in rows] == [real], "가짜 행의 PUUID를 이어받으면 전적 조회가 404가 됨"

    # 닉네임을 넘겨받은 다른 계정: 옛 주인의 PUUID를 이어받지 않는다 (전적이 섞이지 않게)
    upsert_player(puuid="D" * 78, game_name="닉변", tag_line="KR1", tier="GOLD")
    newer = upsert_player(puuid="E" * 78, game_name="닉변", tag_line="KR1", tier="SILVER")
    assert newer["puuid"] == "E" * 78 and get_player_by_riot_id("닉변", "KR1")["puuid"] == "E" * 78
    ok("같은 닉네임#태그의 가짜·옛 계정 행을 이어받지 않고 라이엇 PUUID 기준으로 저장")


def test_riot_network_error_is_503():
    import httpx
    install_fakes()

    def down(req):
        raise httpx.ConnectError("unreachable")

    with riot_http(down):
        res = TestClient(app, raise_server_exceptions=False).get("/api/player/연결실패/KR1", params={"refresh": True})
    assert res.status_code == 503, (res.status_code, res.text)
    assert not riot_client.is_expired, "통신 실패를 키 만료로 표시하면 안 됨"
    ok("라이엇 서버 연결 실패·타임아웃은 500이 아니라 503")


def test_synthetic_local_player_not_written_to_players():
    from app.sync_automation_engine import _handle_verified_local_player
    p = _handle_verified_local_player("생성전용", "KR1")
    assert p["puuid"].startswith("real-kr-") and get_player_by_riot_id("생성전용", "KR1") is None
    ok("생성 데이터 기능용 임시 소환사는 실제 players 테이블에 저장하지 않음")


def test_legacy_ladder_sync_uses_real_path():
    import time as _time
    from app.leaderboard_engine import sync_real_riot_leaderboard
    install_fakes()
    conn = get_connection()
    conn.execute("UPDATE ladder_real SET updated_at = ?", (int(_time.time()) - 7200,))
    conn.commit()
    conn.close()
    res = asyncio.run(sync_real_riot_leaderboard(max_players=30))
    assert res["status"] == "success" and res["synced_count"] == 2, res
    names = [r["game_name"] for r in real_data.load_ladder()["results"]]
    assert names == ["챌린저1", "챌린저2"], "이름 확인 실패 항목을 다른 이름으로 채우면 안 됨"
    assert asyncio.run(sync_real_riot_leaderboard())["status"] == "skipped", "30분 안에 다시 받지 않아야 함"
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM players WHERE puuid LIKE 'real-ladder-%'").fetchone()[0] == 0
    conn.close()
    ok("데몬용 래더 동기화도 실제 경로 사용 (가짜 이름·LP 추이 없음, 30분 내 재호출 안 함)")


def test_rank_snapshots_and_tier_history():
    install_fakes()
    c = TestClient(app)

    # 1. 가짜 puuid(real- 접두사 등)는 저장되지 않음
    fake_player = {
        "puuid": "real-kr-0123456789abcdef",
        "tier": "GOLD",
        "rank_tier": "I",
        "league_points": 50,
        "wins": 10,
        "losses": 5,
        "tier_score": 1550,
    }
    real_data.record_rank_snapshot(fake_player)
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM rank_snapshots WHERE puuid = ?", (fake_player["puuid"],)).fetchone()[0] == 0
    conn.close()
    ok("가짜 puuid(real- 등)는 rank_snapshots에 저장되지 않음")

    # 2. 같은 값으로 두 번 조회 -> 스냅샷 1개 & 스냅샷 1개뿐이면 daily/weekly/monthly 모두 빈 목록
    conn = get_connection()
    conn.execute("DELETE FROM rank_snapshots WHERE puuid = ?", (ME,))
    conn.commit()
    conn.close()

    res1 = c.get("/api/player/실제소환사/KR1", params={"refresh": True})
    assert res1.status_code == 200
    conn = get_connection()
    cnt1 = conn.execute("SELECT COUNT(*) FROM rank_snapshots WHERE puuid = ?", (ME,)).fetchone()[0]
    conn.close()
    assert cnt1 == 1, f"첫 조회 후 스냅샷 1개여야 함 (got {cnt1})"

    # 스냅샷 1개뿐이면 daily/weekly/monthly 모두 빈 목록
    profile1 = res1.json()["player"]
    assert profile1["tier_history"] == {"daily": [], "weekly": [], "monthly": []}, (
        f"스냅샷이 1개일 때는 tier_history 기간별 목록이 모두 비어 있어야 함: {profile1['tier_history']}"
    )

    # 같은 값으로 두 번째 조회
    res2 = c.get("/api/player/실제소환사/KR1", params={"refresh": True})
    assert res2.status_code == 200
    conn = get_connection()
    cnt2 = conn.execute("SELECT COUNT(*) FROM rank_snapshots WHERE puuid = ?", (ME,)).fetchone()[0]
    conn.close()
    assert cnt2 == 1, f"동일한 랭크 값으로 재조회 시 중복 스냅샷이 생기지 않아야 함 (got {cnt2})"
    ok("같은 값으로 두 번 조회 시 스냅샷 1개 유지 & 점 1개면 tier_history 모두 빈 목록")

    # 3. LP가 다른 값으로 날짜를 바꿔 3번 저장 -> daily 3점, lp_change 계산이 맞음, 순서가 오래된 -> 최신
    test_puuid = "Z" * 78
    conn = get_connection()
    conn.execute("DELETE FROM rank_snapshots WHERE puuid = ?", (test_puuid,))
    conn.commit()
    conn.close()

    import time as _time
    now = int(_time.time())
    day_sec = 86400

    # 2일 전 스냅샷: 20 LP (tier_score=1420)
    p_day1 = {
        "puuid": test_puuid, "tier": "GOLD", "rank_tier": "II",
        "league_points": 20, "wins": 10, "losses": 5, "tier_score": 1420
    }
    real_data.record_rank_snapshot(p_day1, captured_at=now - 2 * day_sec)

    # 1일 전 스냅샷: 50 LP (tier_score=1450, +30)
    p_day2 = {
        "puuid": test_puuid, "tier": "GOLD", "rank_tier": "II",
        "league_points": 50, "wins": 12, "losses": 5, "tier_score": 1450
    }
    real_data.record_rank_snapshot(p_day2, captured_at=now - day_sec)

    # 오늘 스냅샷: 35 LP (tier_score=1435, -15)
    p_day3 = {
        "puuid": test_puuid, "tier": "GOLD", "rank_tier": "II",
        "league_points": 35, "wins": 12, "losses": 6, "tier_score": 1435
    }
    real_data.record_rank_snapshot(p_day3, captured_at=now)

    history = real_data.build_tier_history(test_puuid)
    daily = history.get("daily", [])
    assert len(daily) == 3, f"daily 점은 3개여야 함 (got {len(daily)}): {daily}"

    # 오래된 것 -> 최신 순서 검증
    assert daily[0]["point_date"] < daily[1]["point_date"] < daily[2]["point_date"]

    # lp_change 및 각 점의 데이터 검증
    # 첫 점: lp_change == 0
    assert daily[0]["league_points"] == 20 and daily[0]["tier_score"] == 1420
    assert daily[0]["lp_change"] == 0, f"첫 점의 lp_change는 0이어야 함 (got {daily[0]['lp_change']})"

    # 둘째 점: 1450 - 1420 = +30
    assert daily[1]["league_points"] == 50 and daily[1]["tier_score"] == 1450
    assert daily[1]["lp_change"] == 30, f"둘째 점의 lp_change는 +30이어야 함 (got {daily[1]['lp_change']})"

    # 셋째 점: 1435 - 1450 = -15
    assert daily[2]["league_points"] == 35 and daily[2]["tier_score"] == 1435
    assert daily[2]["lp_change"] == -15, f"셋째 점의 lp_change는 -15이어야 함 (got {daily[2]['lp_change']})"
    ok("날짜별 3회 스냅샷 → daily 3점, lp_change 계산(+30, -15) 및 오래된 순 정렬 검증 완료")

    # 4. 스냅샷 저장에서 예외가 나도 /api/player/... 응답은 200
    orig_record = real_data.record_rank_snapshot
    def fail_record(player, captured_at=None):
        raise RuntimeError("스냅샷 DB 쓰기 실패 시뮬레이션")

    real_data.record_rank_snapshot = fail_record
    try:
        err_res = c.get("/api/player/실제소환사/KR1", params={"refresh": True})
        assert err_res.status_code == 200, f"스냅샷 저장 실패 시에도 프로필 조회는 200이어야 함 (got {err_res.status_code})"
        assert err_res.json()["player"]["tier"] == "GOLD"
    finally:
        real_data.record_rank_snapshot = orig_record
    ok("스냅샷 저장 중 예외 발생해도 /api/player/... 정상 200 응답")


def test_multi_search_endpoint():
    install_fakes()
    fast_cache._cache.clear()
    c = TestClient(app)

    # 1. 3명 (a#KR1, b#KR2 + # 없는 이름 'solo') -> 200, players 3개, # 없는 이름은 tag_line == "KR1", 가짜 키 없음
    res = c.post("/api/multi-search", json={"summoner_names": ["a#KR1", "b#KR2", "solo"]})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total_players"] == 3
    assert len(data["players"]) == 3
    assert data["source"] == "riot_api"
    assert data["notice"] is None
    assert "team_summary" not in data
    assert "ai_prediction" not in data
    assert "analysis" not in data

    p1, p2, p3 = data["players"]
    assert p1["found"] is True and p1["game_name"] == "a" and p1["tag_line"] == "KR1"
    assert p2["found"] is True and p2["game_name"] == "b" and p2["tag_line"] == "KR2"
    assert p3["found"] is True and p3["game_name"] == "solo" and p3["tag_line"] == "KR1"

    expected_keys = {
        "found", "game_name", "tag_line", "profile_icon_id", "summoner_level",
        "tier", "rank_tier", "league_points", "wins", "losses", "win_rate",
        "flex_tier", "flex_rank_tier", "flex_lp", "flex_wins", "flex_losses"
    }
    for p in [p1, p2, p3]:
        for k in expected_keys:
            assert k in p, f"'{k}' 키가 플레이어 결과에 없음: {p}"

    # raw_text 파싱으로도 동일하게 동작하는지 확인 (# 없는 이름 -> KR1)
    fast_cache._cache.clear()
    res_raw = c.post("/api/multi-search", json={"raw_text": "x#KR1, y#KR2, z"})
    assert res_raw.status_code == 200
    data_raw = res_raw.json()
    assert data_raw["total_players"] == 3
    assert data_raw["players"][2]["game_name"] == "z"
    assert data_raw["players"][2]["tag_line"] == "KR1"

    # 2. 같은 이름 중복 + 6명 이상 입력 -> 최대 5명, 중복 제거
    fast_cache._cache.clear()
    dup_names = ["m1#KR1", "M1#kr1", "m2#KR2", "m3#KR1", "m4#KR1", "m5#KR1", "m6#KR1", "m7#KR1"]
    res_dup = c.post("/api/multi-search", json={"summoner_names": dup_names})
    assert res_dup.status_code == 200
    data_dup = res_dup.json()
    assert data_dup["total_players"] == 5
    assert len(data_dup["players"]) == 5
    extracted_names = [p["game_name"] for p in data_dup["players"]]
    assert extracted_names == ["m1", "m2", "m3", "m4", "m5"], f"중복 제거 및 5명 제한 실패: {extracted_names}"

    # 3. 가짜 프로필 함수가 한 명에 대해 404 오류를 내면 그 사람은 found: false, 나머지는 계속
    fast_cache._cache.clear()
    res_404 = c.post("/api/multi-search", json={"summoner_names": ["user1#KR1", "없는소환사#KR1", "user2#KR2"]})
    assert res_404.status_code == 200
    data_404 = res_404.json()
    assert data_404["total_players"] == 3
    assert len(data_404["players"]) == 3
    assert data_404["notice"] is None
    assert data_404["players"][0]["found"] is True and data_404["players"][0]["game_name"] == "user1"
    assert data_404["players"][1]["found"] is False
    assert data_404["players"][1]["game_name"] == "없는소환사"
    assert data_404["players"][1]["tag_line"] == "KR1"
    assert data_404["players"][1]["error"] == "소환사를 찾을 수 없습니다."
    assert data_404["players"][2]["found"] is True and data_404["players"][2]["game_name"] == "user2"

    # 4. 두 번째 사람에서 429가 나면 players는 1개, notice가 있음, 세 번째 사람은 조회되지 않음(가짜 함수 호출 횟수로 확인)
    fast_cache._cache.clear()
    call_counts = {"count": 0}
    orig_profile = riot_client.fetch_full_player_profile

    async def fake_profile_with_429(game_name, tag_line):
        call_counts["count"] += 1
        if game_name == "second":
            raise RiotAPIError(429, "라이엇 API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
        puuid = hashlib.sha256(f"{game_name}#{tag_line}".encode("utf-8")).hexdigest() + "00000000000000"
        return {
            "puuid": puuid, "game_name": game_name, "tag_line": tag_line, "profile_icon_id": 1,
            "summoner_level": 100, "tier": "GOLD", "rank_tier": "I", "league_points": 50,
            "wins": 20, "losses": 10, "queue_type": "RANKED_SOLO_5x5",
            "flex_tier": "UNRANKED", "flex_rank_tier": "", "flex_lp": 0, "flex_wins": 0, "flex_losses": 0
        }

    riot_client.fetch_full_player_profile = fake_profile_with_429
    try:
        res_429 = c.post("/api/multi-search", json={"summoner_names": ["first#KR1", "second#KR1", "third#KR1"]})
        assert res_429.status_code == 200
        data_429 = res_429.json()
        assert data_429["total_players"] == 1
        assert len(data_429["players"]) == 1
        assert data_429["players"][0]["game_name"] == "first"
        assert data_429["players"][0]["found"] is True
        assert data_429["notice"] == "라이엇 API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
        assert call_counts["count"] == 2, f"세 번째 사람은 조회되지 않아야 함 (got {call_counts['count']} calls)"

        # notice가 있는 결과는 fast_cache에 저장되지 않았는지 재호출로 확인 (호출 횟수가 증가해야 함)
        before_count = call_counts["count"]
        c.post("/api/multi-search", json={"summoner_names": ["first#KR1", "second#KR1", "third#KR1"]})
        assert call_counts["count"] > before_count, "notice가 있는 실패 응답은 캐시되지 않아야 함"
    finally:
        riot_client.fetch_full_player_profile = orig_profile

    # 빈 입력 처리 검증
    res_empty = c.post("/api/multi-search", json={"raw_text": "", "summoner_names": []})
    assert res_empty.status_code == 200
    assert res_empty.json() == {"total_players": 0, "players": [], "notice": None, "source": "riot_api"}

    ok("멀티서치 실데이터 API 검증 (순차 조회, #KR1 기본값, 중복제거/최대5명, 404 계속, 429 중단 및 notice, 캐시 비저장)")


def test_champion_masters_real_data():
    install_fakes()
    fast_cache._cache.clear()
    c = TestClient(app)

    calls = {"mastery": 0}

    async def fake_masteries(puuid, count=10):
        calls["mastery"] += 1
        if puuid == ME:
            return [
                {"championId": 103, "championPoints": 250000, "championLevel": 7, "lastPlayTime": 1700000000000},
                {"championId": 86, "championPoints": 10000, "championLevel": 4, "lastPlayTime": 1690000000000},
            ]
        elif puuid == OTHER[1]:
            return [
                {"championId": 103, "championPoints": 500000, "championLevel": 10, "lastPlayTime": 1705000000000},
            ]
        elif puuid == OTHER[3]:
            return [
                {"championId": 103, "championPoints": 999999, "championLevel": 20, "lastPlayTime": 1710000000000},
            ]
        return []

    orig_masteries = riot_client.get_champion_masteries_by_puuid
    riot_client.get_champion_masteries_by_puuid = fake_masteries

    try:
        # 1. 소환사 조회 후 숙련도 저장됨
        res = c.get("/api/player/실제소환사/KR1")
        assert res.status_code == 200, res.text
        assert calls["mastery"] == 1

        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM champion_mastery_real WHERE puuid = ? ORDER BY champion_points DESC",
            (ME,)
        ).fetchall()
        conn.close()
        assert len(rows) == 2
        assert rows[0]["champion_id"] == 103 and rows[0]["champion_points"] == 250000

        # 2. 1시간 안 재조회 시 숙련도 호출 안 함
        res2 = c.get("/api/player/실제소환사/KR1", params={"refresh": True})
        assert res2.status_code == 200
        assert calls["mastery"] == 1, "1시간 이내 재조회 시 숙련도 API를 다시 부르지 않아야 함"

        # 래더 데이터 동기화 (OTHER[1] 은 '챌린저1'로 ladder_real 에 등록됨)
        asyncio.run(real_data.sync_challenger_ladder())
        # OTHER[1] 숙련도 갱신
        asyncio.run(real_data.refresh_masteries(OTHER[1]))
        assert calls["mastery"] == 2

        # OTHER[3] 숙련도 갱신 (OTHER[3] 은 players 에도 ladder_real 에도 없음)
        asyncio.run(real_data.refresh_masteries(OTHER[3]))
        assert calls["mastery"] == 3

        # 3. /api/champion-masters?champ=Ahri 가 점수 순서대로 이름 있는 행만 반환
        fast_cache._cache.clear()
        m_res = c.get("/api/champion-masters", params={"champ": "Ahri"})
        assert m_res.status_code == 200, m_res.text
        m_data = m_res.json()
        assert m_data["source"] == "riot_api"
        assert m_data["champion"]["id"] == "Ahri"
        assert m_data["count"] == 2
        results = m_data["results"]
        assert len(results) == 2
        # Rank 1: OTHER[1] (500,000점) - ladder_real 소환사이므로 tier='CHALLENGER'
        assert results[0]["rank"] == 1
        assert results[0]["puuid"] == OTHER[1]
        assert results[0]["tier"] == "CHALLENGER"
        assert results[0]["mastery_points"] == 500000
        # Rank 2: ME (250,000점) - players 소환사이므로 tier='GOLD'
        assert results[1]["rank"] == 2
        assert results[1]["puuid"] == ME
        assert results[1]["game_name"] == "실제소환사"
        assert results[1]["mastery_points"] == 250000

        # 4. 숙련도 호출이 예외를 내도 프로필 200
        async def failing_masteries(puuid, count=10):
            raise RiotAPIError(500, "숙련도 API 장애")

        riot_client.get_champion_masteries_by_puuid = failing_masteries
        fail_res = c.get("/api/player/새소환사/KR1", params={"refresh": True})
        assert fail_res.status_code == 200, f"숙련도 실패 시에도 프로필은 200이어야 함 (got {fail_res.status_code})"

    finally:
        riot_client.get_champion_masteries_by_puuid = orig_masteries

    ok("실제 챔피언 숙련도(Champion-Mastery-V4) 및 장인랭킹 검증 (저장, 1시간 쿨다운, 점수순 정렬/미등록 제외, 예외 시 프로필 200)")


if __name__ == "__main__":
    print("=" * 80)
    print("📡 [Real Data Suite] 라이엇 실데이터 계층 검증 (픽스처, 네트워크 없음)")
    print("=" * 80)
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print("=" * 80)
    print(f"🎉 실데이터 테스트 {len(tests)}개 전부 통과")
    print("=" * 80)
