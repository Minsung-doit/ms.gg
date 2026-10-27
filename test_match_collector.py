"""
매치 수집기 종합 검증 스위트 (test_match_collector.py)

검증 내용:
1. compact_match: 420 아니면 None / 필드 추출 검증 / 저장 크기 압축률 검증
2. run_collector_cycle: 새 매치만 상세 조회, 이미 있는 매치 스킵, 참가자 시드 추가, 시드 5000개 상한
3. 속도 제한: 120초당 40회 한도 검증 (짧은 시간에 41번째 호출 블로킹)
4. collector_loop: 429 오류 발생 시 루프 생존 및 지속 동작
5. /api/admin/collector/status: 공개 포트 404, 관리자 포트 비로그인 401, 관리자 로그인 200
"""
import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from test_support import admin_client, sandbox_env_writes, use_temp_db

sandbox_env_writes()
use_temp_db()

from fastapi.testclient import TestClient

import app.match_collector as mc
from app.config import settings
from app.database import get_connection
from app.main import app
from app.riot_client import RiotAPIError, riot_client


def ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def make_fixture_match(queue_id: int = 420, match_id: str = "KR_7000000001") -> Dict[str, Any]:
    """테스트용 Match-V5 픽스처 생성"""
    participants = []
    for i in range(10):
        puuid = f"TEST_PUUID_{str(i).zfill(67)}"
        team_id = 100 if i < 5 else 200
        participants.append({
            "puuid": puuid,
            "teamId": team_id,
            "win": i < 5,
            "championId": 100 + i,
            "championName": f"Champ_{i}",
            "teamPosition": ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"][i % 5],
            "item0": 3031,
            "item1": 3006,
            "item2": 3046,
            "item3": 0,
            "item4": 0,
            "item5": 0,
            "item6": 3340,
            "summoner1Id": 4,
            "summoner2Id": 14,
            "perks": {
                "statPerks": {
                    "offense": 5008,
                    "flex": 5005,
                    "defense": 5011,
                },
                "styles": [
                    {
                        "style": 8000,
                        "selections": [
                            {"perk": 8010},
                            {"perk": 9104},
                            {"perk": 8299},
                            {"perk": 8014},
                        ],
                    },
                    {
                        "style": 8400,
                        "selections": [
                            {"perk": 8410},
                            {"perk": 8451},
                        ],
                    },
                ]
            },
            "kills": 5 + i,
            "deaths": 2,
            "assists": 8,
            "totalMinionsKilled": 150,
            "neutralMinionsKilled": 30,
            "goldEarned": 12000 + i * 500,
            "totalDamageDealtToChampions": 20000 + i * 1000,
            "gameEndedInEarlySurrender": False,
        })

    return {
        "metadata": {
            "matchId": match_id,
            "participants": [p["puuid"] for p in participants],
        },
        "info": {
            "queueId": queue_id,
            "gameVersion": "16.21.621.1234",
            "gameEndTimestamp": 1700000000000,  # ms
            "gameDuration": 1800,  # sec
            "participants": participants,
            "teams": [
                {
                    "teamId": 100,
                    "bans": [{"championId": 157}, {"championId": 238}, {"championId": -1}],
                },
                {
                    "teamId": 200,
                    "bans": [{"championId": 64}, {"championId": 11}],
                },
            ],
        },
    }


def test_compact_match():
    print("=" * 80)
    print("▶ 1. compact_match 변환 및 압축 검증")
    print("=" * 80)

    # 1) queueId != 420 인 경우 None 반환
    norm_match = make_fixture_match(queue_id=440)
    assert mc.compact_match(norm_match) is None, "queueId 420이 아니면 None이어야 함"
    assert mc.compact_match({}) is None
    assert mc.compact_match(None) is None
    ok("420(솔로랭크) 외 큐 필터링 확인 (queue 440 -> None)")

    # 2) 420 매치 필드 정상 추출
    solo_match = make_fixture_match(queue_id=420)
    res = mc.compact_match(solo_match)
    assert res is not None, "420 매치는 정상 반환되어야 함"
    assert res["game_version"] == "16.21", f"버전 앞 두자리 추출 실패: {res['game_version']}"
    assert res["game_end"] == 1700000000, f"밀리초->초 변환 실패: {res['game_end']}"
    assert res["duration"] == 1800, f"게임 시간 실패: {res['duration']}"
    assert res["early_surrender"] is False, "조기 서렌더 확인 실패"
    assert len(res["participants"]) == 10, f"참가자 10명 확인 실패: {len(res['participants'])}"

    p0 = res["participants"][0]
    assert p0["puuid"].startswith("TEST_PUUID_")
    assert p0["team_id"] == 100
    assert p0["win"] is True
    assert p0["champion_id"] == 100
    assert p0["position"] == "TOP"
    assert p0["items"] == [3031, 3006, 3046, 0, 0, 0, 3340]
    assert p0["spells"] == [4, 14]
    assert p0["keystone"] == 8010
    assert p0["primary_style"] == 8000
    assert p0["sub_style"] == 8400
    assert p0["perks"] == [8010, 9104, 8299, 8014, 8410, 8451], f"perks 6개 순서 실패: {p0['perks']}"
    assert p0["shards"] == [5008, 5005, 5011], f"shards 3개 실패: {p0['shards']}"
    assert p0["kills"] == 5
    assert p0["deaths"] == 2
    assert p0["assists"] == 8
    assert p0["cs"] == 180  # 150 + 30
    assert p0["gold"] == 12000
    assert p0["damage"] == 20000
    ok("참가자 10명 및 필수 필드 정상 추출 확인")

    # 2-1) perks가 없는 원본 매치 참가자 -> perks, shards 빈 리스트 검증
    no_perks_match = make_fixture_match(queue_id=420)
    del no_perks_match["info"]["participants"][0]["perks"]
    res_no_perks = mc.compact_match(no_perks_match)
    assert res_no_perks["participants"][0]["perks"] == [], "perks 없는 원본이면 perks는 빈 리스트여야 함"
    assert res_no_perks["participants"][0]["shards"] == [], "perks 없는 원본이면 shards는 빈 리스트여야 함"
    ok("perks 6개 순서·shards 3개 추출 및 perks 없는 원본 빈 리스트 확인")

    # 밴 목록 (-1 제외)
    assert res["bans"] == [157, 238, 64, 11], f"밴 목록 확인 실패: {res['bans']}"
    ok("밴 목록 추출 (-1 제외) 확인")

    # 3) 저장 크기 압축률 검증
    raw_size = len(json.dumps(solo_match, ensure_ascii=False))
    compact_size = len(json.dumps(res, ensure_ascii=False))
    ratio = compact_size / raw_size
    # 픽스처는 실제 응답(약 85KB)보다 훨씬 작아 비율이 높게 나온다. 실제 매치는 약 4.6%로 압축됨 (2026-10-25 측정)
    assert ratio < 0.6, f"압축률 미달: 원본 {raw_size}바이트 -> 압축 {compact_size}바이트 ({ratio:.1%})"
    ok(f"저장 크기 대폭 압축 확인 ({raw_size}B -> {compact_size}B, {ratio:.1%})")


def make_fixture_timeline() -> Dict[str, Any]:
    """참가자 1: Q-E-W-Q, 시작템 도란검+포션(와드 샀다가 되돌림), 3분에 롱소드"""
    ev = lambda t, **kw: {"timestamp": t, "participantId": 1, **kw}
    return {"info": {"frames": [
        {"events": [
            ev(5000, type="ITEM_PURCHASED", itemId=1055),
            ev(6000, type="ITEM_PURCHASED", itemId=2003),
            ev(7000, type="ITEM_PURCHASED", itemId=3340),
            ev(8000, type="ITEM_UNDO", beforeId=3340, afterId=0),
            ev(9000, type="SKILL_LEVEL_UP", skillSlot=1, levelUpType="NORMAL"),
        ]},
        {"events": [
            ev(70000, type="SKILL_LEVEL_UP", skillSlot=3, levelUpType="NORMAL"),
            ev(80000, type="SKILL_LEVEL_UP", skillSlot=4, levelUpType="EVOLVE"),
            ev(150000, type="SKILL_LEVEL_UP", skillSlot=2, levelUpType="NORMAL"),
            ev(180000, type="ITEM_PURCHASED", itemId=1036),
            ev(200000, type="SKILL_LEVEL_UP", skillSlot=1, levelUpType="NORMAL"),
            {"timestamp": 210000, "participantId": 0, "type": "SKILL_LEVEL_UP", "skillSlot": 2},
        ]},
    ]}}


def test_apply_timeline():
    compacted = mc.compact_match(make_fixture_match())
    mc.apply_timeline(compacted, make_fixture_timeline())
    p1, p2 = compacted["participants"][0], compacted["participants"][1]
    assert p1["skills"] == [1, 3, 2, 1], p1["skills"]
    assert p1["start_items"] == [1055, 2003], "되돌린 와드·1분 뒤 구매는 시작템이 아님"
    assert p1["item_order"] == [1055, 2003, 3340, 1036]
    assert p2["skills"] == [] and p2["start_items"] == []
    bare = mc.compact_match(make_fixture_match())
    mc.apply_timeline(bare, None)
    assert "skills" not in bare["participants"][0], "타임라인이 없으면 필드를 지어내지 않음"
    ok("타임라인: 스킬 순서(진화 제외)·시작템(되돌리기 반영)·구매 순서 추출, 없으면 필드 없음")


def test_collector_cycle_and_seeds():
    print("=" * 80)
    print("▶ 2. run_collector_cycle 수집 주기 및 시드 관리 검증")
    print("=" * 80)

    use_temp_db()
    mc.init_collector_tables()

    seed_puuid = f"SEED_PUUID_{'1' * 67}"
    now = int(time.time())

    conn = get_connection()
    # 24시간 이전에 추가된 시드 1개 생성 (last_crawled = 0)
    conn.execute(
        "INSERT INTO collector_seeds (puuid, source, last_crawled, added_at) VALUES (?, 'ladder', 0, ?)",
        (seed_puuid, now - 100000),
    )
    # 이미 저장된 매치 1개 준비
    conn.execute(
        "INSERT INTO collected_matches (match_id, game_version, game_end, duration, data, collected_at) "
        "VALUES ('KR_ALREADY_EXISTS', '16.21', 1700000000, 1800, '{}', ?)",
        (now,),
    )
    conn.commit()
    conn.close()

    call_history = {"get_match_detail": []}

    async def mock_get_match_ids(puuid, count=20, queue=None, start_time=None):
        return ["KR_ALREADY_EXISTS", "KR_NEW_MATCH_1"]

    async def mock_get_match_detail(mid):
        call_history["get_match_detail"].append(mid)
        if mid == "KR_NEW_MATCH_1":
            return make_fixture_match(queue_id=420, match_id="KR_NEW_MATCH_1")
        return None

    async def mock_get_timeline(mid):
        call_history.setdefault("timeline", []).append(mid)
        return make_fixture_timeline()

    # riot_client 모킹
    orig_get_ids = riot_client.get_match_ids_by_puuid
    orig_get_detail = riot_client.get_match_detail
    orig_get_timeline = riot_client.get_match_timeline
    riot_client.get_match_ids_by_puuid = mock_get_match_ids
    riot_client.get_match_detail = mock_get_match_detail
    riot_client.get_match_timeline = mock_get_timeline

    try:
        asyncio.run(mc.run_collector_cycle())
    finally:
        riot_client.get_match_ids_by_puuid = orig_get_ids
        riot_client.get_match_detail = orig_get_detail
        riot_client.get_match_timeline = orig_get_timeline
    assert call_history["timeline"] == ["KR_NEW_MATCH_1"], call_history

    # 이미 있는 매치는 건너뛰고 새 매치만 get_match_detail 호출되었는지 확인
    assert "KR_ALREADY_EXISTS" not in call_history["get_match_detail"], "기존 매치는 상세 호출 금지"
    assert "KR_NEW_MATCH_1" in call_history["get_match_detail"], "새 매치만 상세 호출되어야 함"
    ok("새 매치만 상세 조회하고 이미 존재하는 매치는 스킵 확인")

    # 매치 저장 확인
    conn = get_connection()
    row = conn.execute("SELECT match_id, game_version FROM collected_matches WHERE match_id = 'KR_NEW_MATCH_1'").fetchone()
    assert row is not None, "새 매치가 collected_matches 에 저장되어야 함"
    assert row["game_version"] == "16.21"
    saved = json.loads(conn.execute("SELECT data FROM collected_matches WHERE match_id = 'KR_NEW_MATCH_1'").fetchone()[0])
    assert saved["participants"][0]["skills"] == [1, 3, 2, 1] and saved["participants"][0]["start_items"] == [1055, 2003]
    p0 = saved["participants"][0]
    summ = mc.player_collected_summary(p0["puuid"])
    assert summ and summ["games"] == 1 and summ["top_champions"][0]["games"] == 1, summ
    assert mc.player_collected_summary("X" * 78) is None, "수집 게임이 없으면 None (지어내지 않음)"

    # 시드의 last_crawled 갱신 확인
    seed_row = conn.execute("SELECT last_crawled FROM collector_seeds WHERE puuid = ?", (seed_puuid,)).fetchone()
    assert seed_row is not None and seed_row["last_crawled"] > 0, "크롤 후 last_crawled 가 갱신되어야 함"

    # 참가자 10명이 collector_seeds 에 추가되었는지 확인
    match_seeds_count = conn.execute("SELECT COUNT(*) FROM collector_seeds WHERE source = 'match'").fetchone()[0]
    assert match_seeds_count == 10, f"참가자 10명이 시드로 추가되어야 함 (현재: {match_seeds_count})"
    ok("새 매치 저장, 시드 last_crawled 갱신, 참가자 시드 추가 확인")
    conn.close()

    # 시드 5000개 상한 검증
    conn = get_connection()
    # 시드를 5000개까지 미리 채움
    current_count = conn.execute("SELECT COUNT(*) FROM collector_seeds").fetchone()[0]
    needed = 5000 - current_count
    if needed > 0:
        dummy_rows = [
            (f"DUMMY_PUUID_{str(idx).zfill(66)}", "dummy", 0, now)
            for idx in range(needed)
        ]
        conn.executemany("INSERT OR IGNORE INTO collector_seeds VALUES (?, ?, ?, ?)", dummy_rows)
        conn.commit()

    total_before = conn.execute("SELECT COUNT(*) FROM collector_seeds").fetchone()[0]
    assert total_before == 5000, f"테스트 전 시드 수 5000 맞춤 확인 (현재: {total_before})"

    # 추가 시도 (5000개 초과 추가 방지)
    new_puuids = [f"OVERFLOW_PUUID_{str(idx).zfill(63)}" for idx in range(20)]
    mc._add_match_seeds(new_puuids)

    total_after = conn.execute("SELECT COUNT(*) FROM collector_seeds").fetchone()[0]
    assert total_after == 5000, f"5000개 초과 방지 실패 (현재: {total_after})"
    ok("시드 총수 5000개 상한 초과 방지 확인")
    conn.close()


def test_rate_limiter():
    print("=" * 80)
    print("▶ 3. 속도 제한기 (120초당 40회) 검증")
    print("=" * 80)

    limiter = mc.CollectorRateLimiter(max_calls=40, period=120.0)

    async def _run_limit_test():
        # 40회 호출은 윈도우 내 즉시 통과
        for _ in range(40):
            await limiter.acquire()
        assert len(limiter.calls) == 40, f"40회 등록 확인 (현재: {len(limiter.calls)})"

        # 41번째 호출은 대기해야 하므로 짧은 시간(0.05초) 안에 완료되지 않아야 함
        blocked = False
        try:
            await asyncio.wait_for(limiter.acquire(), timeout=0.05)
        except asyncio.TimeoutError:
            blocked = True

        assert blocked, "41번째 호출이 대기하지 않고 즉시 통과됨 (속도 제한 실패)"

    asyncio.run(_run_limit_test())
    ok("40회 즉시 통과 후 41번째 호출 대기(블로킹) 동작 확인")


def test_collector_loop_survives_429():
    print("=" * 80)
    print("▶ 4. collector_loop 429 오류 발생 시 루프 생존 검증")
    print("=" * 80)

    cycle_count = 0
    yield_sleep = asyncio.sleep  # 패치 전 진짜 sleep (실제 사이클은 네트워크 대기로 양보하므로 가짜 사이클도 양보시킨다)

    async def mock_cycle():
        nonlocal cycle_count
        cycle_count += 1
        await yield_sleep(0)
        if cycle_count == 1:
            # 1회차에 429 오류 발생
            raise RiotAPIError(429, "Rate limit exceeded")
        # 2회차는 정상 통과

    async def _test():
        real_sleep = asyncio.sleep  # 아래에서 asyncio.sleep을 가짜로 바꾸므로, 양보용 진짜 sleep을 먼저 잡아 둔다
        orig_key = settings.riot_api_key
        settings.riot_api_key = "RGAPI-TEST-KEY"
        try:
            with patch("app.match_collector.run_collector_cycle", side_effect=mock_cycle):
                with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                    # 루프 실행 태스크 시작
                    loop_task = asyncio.create_task(mc.collector_loop())

                    # 루프가 2회 사이클을 돌 때까지 잠깐 양보
                    for _ in range(10):
                        if cycle_count >= 2:
                            break
                        await real_sleep(0.01)

                    loop_task.cancel()
                    try:
                        await loop_task
                    except asyncio.CancelledError:
                        pass

                    assert cycle_count >= 2, f"429 발생 후 루프가 죽지 않고 다음 사이클 진입 확인 (실행횟수: {cycle_count})"
                    # 429에 따른 120초 대기 함수 호출 여부 확인
                    sleep_calls = [c[0][0] for c in mock_sleep.call_args_list if c[0]]
                    assert 120 in sleep_calls, f"429 발생 시 120초 대기 확인 (호출 목록: {sleep_calls})"
        finally:
            settings.riot_api_key = orig_key

    asyncio.run(_test())
    ok("429 오류 발생 시 120초 백오프 후 루프가 종료되지 않고 지속 실행 확인")


def test_admin_collector_status():
    print("=" * 80)
    print("▶ 5. 관리자 /api/admin/collector/status 엔드포인트 격리 및 응답 검증")
    print("=" * 80)

    # 1) 공개 포트 접근 -> 404
    public_client = TestClient(app, base_url="http://testserver:3000")
    res_pub = public_client.get("/api/admin/collector/status")
    assert res_pub.status_code == 404, f"공개 포트에서는 404여야 함 (현재: {res_pub.status_code})"
    ok("공개 포트(3000) 접근 시 404 확인")

    # 2) 관리자 포트 비로그인 -> 401
    admin_unauthed = TestClient(app, base_url=f"http://testserver:{settings.admin_port}")
    res_unauth = admin_unauthed.get("/api/admin/collector/status")
    assert res_unauth.status_code == 401, f"비로그인 관리자 접근 시 401이어야 함 (현재: {res_unauth.status_code})"
    ok("관리자 포트 비로그인 시 401 확인")

    # 3) 관리자 포트 로그인 -> 200
    adm_client = admin_client(app)
    res_adm = adm_client.get("/api/admin/collector/status")
    assert res_adm.status_code == 200, f"관리자 로그인 시 200이어야 함 (현재: {res_adm.status_code})"
    data = res_adm.json()
    assert "enabled" in data
    assert "matches" in data
    assert "seeds" in data
    assert "latest_version_counts" in data
    assert "last_cycle_at" in data
    ok("관리자 로그인 시 200 및 메타데이터 필드(enabled, matches, seeds, latest_version_counts, last_cycle_at) 확인")


def test_prune_and_full_patch_slowdown():
    print("=" * 80)
    print("▶ 6. 오래된 패치 정리 + 패치당 상한 도달 시 감속")
    print("=" * 80)
    use_temp_db()
    mc.init_collector_tables()
    conn = get_connection()
    for i, ver in enumerate(["16.19", "16.20", "16.21", "16.21", "16.9"]):
        conn.execute(
            "INSERT INTO collected_matches (match_id, game_version, game_end, duration, data, collected_at) "
            "VALUES (?, ?, 0, 0, '{}', 0)", (f"KR_PRUNE_{i}", ver))
    conn.commit()
    conn.close()
    removed = mc.prune_old_versions(keep=2)
    conn = get_connection()
    left = sorted(r[0] for r in conn.execute("SELECT DISTINCT game_version FROM collected_matches").fetchall())
    conn.close()
    assert removed == 2 and left == ["16.20", "16.21"], (removed, left)
    print("  [PASS] 최신 2개 패치만 남김 (16.9 < 16.19 숫자 비교)")

    orig_cap = mc.MAX_MATCHES_PER_PATCH
    try:
        mc.MAX_MATCHES_PER_PATCH = 2
        assert mc.latest_version_is_full() is True
        mc.MAX_MATCHES_PER_PATCH = 3
        assert mc.latest_version_is_full() is False
        mc.MAX_MATCHES_PER_PATCH = 2
        slept = []

        async def fake_sleep(sec):
            slept.append(sec)

        with patch.object(mc.asyncio, "sleep", fake_sleep):
            asyncio.run(mc.run_collector_cycle())  # 시드가 없어도 먼저 감속 대기
        assert mc.FULL_PATCH_PAUSE_SEC in slept, slept
    finally:
        mc.MAX_MATCHES_PER_PATCH = orig_cap
    print("  [PASS] 최신 패치가 상한에 도달하면 주기마다 감속 대기")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("carry.gg 티어표·상성용 매치 수집기 (Match Collector) 단위 및 통합 테스트")
    print("=" * 80)

    test_compact_match()
    test_apply_timeline()
    test_collector_cycle_and_seeds()
    test_rate_limiter()
    test_collector_loop_survives_429()
    test_admin_collector_status()
    test_prune_and_full_patch_slowdown()

    print("\n" + "=" * 80)
    print("티어표·상성용 매치 수집기 검증 완료")
    print("=" * 80)
