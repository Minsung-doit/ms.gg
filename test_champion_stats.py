"""
test_champion_stats.py

수집된 실제 매치(collected_matches) 기반 챔피언 티어표 검증 스위트:
1. 승률, 픽률, 밴률 계산 정확성
2. 최소 표본 미만 제외
3. 최신 game_version만 사용 (버전 문자열 숫자 비교)
4. early_surrender 매치 제외
5. 매치 0개일 때 빈 결과 및 안내 문구 반환
6. /api/tierlist 및 /api/champion-analytics 200 OK 및 필수 필드 검증
7. 포지션 필터링 및 파라미터 정렬 기준 반영 검증
"""
import json
import os
import sys
import time
from typing import Any, Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from test_support import sandbox_env_writes, use_temp_db

sandbox_env_writes()
use_temp_db()

# 라이엇 API 호출 차단 (키 비움)
from app.config import settings
settings.riot_api_key = ""

from fastapi.testclient import TestClient

from app.champion_stats import clear_cache, compute_tier_list, compute_matchups, compute_head_to_head, compute_duo_synergy, compute_champion_build, compute_patch_shift, compute_pair_synergy, compute_bot_lane_matchups
import app.champion_stats as _cs
_cs.MIN_LATEST_PATCH_GAMES = 0  # 작은 표본 테스트에서 "최신 패치만" 동작을 검증
from app.database import get_connection
from app.ddragon import DDRAGON_CDN
from app.main import app
from app.match_collector import init_collector_tables

client = TestClient(app)


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def insert_test_match(
    match_id: str,
    game_version: str,
    participants: List[Dict[str, Any]],
    bans: List[int] = None,
    early_surrender: bool = False,
) -> None:
    """테스트용 압축 매치를 collected_matches 에 직접 삽입"""
    init_collector_tables()
    conn = get_connection()
    compacted = {
        "game_version": game_version,
        "game_end": 1700000000,
        "duration": 1800,
        "early_surrender": early_surrender,
        "participants": participants,
        "bans": bans or [],
    }
    conn.execute(
        """
        INSERT OR REPLACE INTO collected_matches
        (match_id, game_version, game_end, duration, data, collected_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            match_id,
            game_version,
            1700000000,
            1800,
            json.dumps(compacted, ensure_ascii=False),
            int(time.time()),
        ),
    )
    conn.commit()
    conn.close()


def test_empty_matches():
    print("=" * 80)
    print("[Suite 9-A] 매치 0개일 때 빈 결과 검증")
    print("=" * 80)

    clear_cache()
    res = compute_tier_list(position="all")
    assert res["results"] == [], "매치가 없으면 results 는 빈 리스트여야 함"
    assert res["summary"]["total_games"] == 0
    assert res["summary"]["op_count"] == 0
    assert res["sample_note"] == "아직 수집된 매치가 부족합니다."
    assert res["source"] == "collected_matches"
    _ok("매치 0개 시 빈 결과, total_games: 0, sample_note 정상 확인")


def test_champion_stats_computation():
    print("=" * 80)
    print("[Suite 9-B] 승률·픽률·밴률 계산, 최신 버전, early_surrender 제외, 최소 표본 검증")
    print("=" * 80)

    # 1. 과거 버전 "16.20" 매치 15개 생성 (Darius 122 번이 15승 100% 승률)
    #    -> 최신 버전(16.21)만 쓰이므로 결과에 Darius 가 포함되면 안 됨!
    for i in range(15):
        insert_test_match(
            match_id=f"KR_OLD_{i}",
            game_version="16.20",
            participants=[
                {"champion_id": 122, "position": "TOP", "win": True, "kills": 5, "deaths": 1, "assists": 5},
            ],
            bans=[122],
        )

    # 2. 최신 버전 "16.21" early_surrender=True 매치 5개 생성
    #    -> early_surrender 제외 규칙으로 집계에서 제외되어야 함
    for i in range(5):
        insert_test_match(
            match_id=f"KR_SURRENDER_{i}",
            game_version="16.21",
            participants=[
                {"champion_id": 86, "position": "TOP", "win": True, "kills": 1, "deaths": 0, "assists": 1},
            ],
            bans=[86],
            early_surrender=True,
        )

    # 3. 최신 버전 "16.21" 정상 매치 100개 생성
    #    - Garen (ID: 86, TOP): 40게임 출전, 24승 16패 (승률 60.0%), 밴 15회 (밴률 15.0%)
    #      픽률 = 40 / 100 * 100 = 40.0%
    #      KDA = (200 + 160) / 80 = 4.5
    #      점수 = 60.0 + 40.0 * 0.2 + 15.0 * 0.1 = 69.5
    #    - Ahri (ID: 103, MIDDLE->MID): 35게임 출전, 14승 21패 (승률 40.0%), 밴 10회 (밴률 10.0%)
    #      픽률 = 35 / 100 * 100 = 35.0%
    #      KDA = (140 + 140) / 70 = 4.0
    #      점수 = 40.0 + 35.0 * 0.2 + 10.0 * 0.1 = 48.0
    #    - Yasuo (ID: 157, MIDDLE->MID): 10게임 출전 (최소 표본 30게임 미만 -> 제외 대상)
    #    - 빈 포지션 참가자 ("position": ""): 집계 제외 확인
    for i in range(100):
        participants = []
        bans = []

        if i < 40:
            # Garen 탑
            is_win = (i < 24)
            participants.append({
                "champion_id": 86,
                "position": "TOP",
                "win": is_win,
                "kills": 5,
                "deaths": 2,
                "assists": 4,
            })
        if i < 15:
            bans.append(86)

        if i < 35:
            # Ahri 미드
            is_win = (i < 14)
            participants.append({
                "champion_id": 103,
                "position": "MIDDLE",
                "win": is_win,
                "kills": 4,
                "deaths": 2,
                "assists": 4,
            })
        if i < 10:
            bans.append(103)

        if i < 10:
            # Yasuo 미드 (표본 10게임)
            participants.append({
                "champion_id": 157,
                "position": "MIDDLE",
                "win": True,
                "kills": 10,
                "deaths": 1,
                "assists": 5,
            })

        # 빈 포지션 참가자 추가 (제외되어야 함)
        participants.append({
            "champion_id": 1,
            "position": "",
            "win": True,
            "kills": 3,
            "deaths": 1,
            "assists": 2,
        })

        insert_test_match(
            match_id=f"KR_MATCH_16_21_{i}",
            game_version="16.21",
            participants=participants,
            bans=bans,
            early_surrender=False,
        )

    clear_cache()
    res = compute_tier_list(position="all")

    # 대상 매치 수 검증 (100게임, 16.20 매치와 early_surrender 매치 제외)
    assert res["summary"]["total_games"] == 100, f"대상 매치 수는 100이어야 함: {res['summary']['total_games']}"
    assert res["patch"] == "16.21", f"최신 패치 버전은 16.21 이어야 함: {res['patch']}"
    _ok("최신 game_version(16.21)만 선택 및 early_surrender 제외 확인 (총 매치 100)")

    # 결과 분석
    champ_ids = [c["id"] for c in res["results"]]
    assert "Garen" in champ_ids, "Garen (40게임)은 결과에 포함되어야 함"
    assert "Ahri" in champ_ids, "Ahri (35게임)은 결과에 포함되어야 함"
    assert "Yasuo" not in champ_ids, "Yasuo (10게임 < 최소 표본 30)는 제외되어야 함"
    assert "Darius" not in champ_ids, "Darius (과거 버전 매치)는 제외되어야 함"
    _ok("최소 표본수 미만 제외 및 과거 버전 챔피언 제외 확인")

    # Garen 상세 지표 검증
    garen = next(c for c in res["results"] if c["id"] == "Garen")
    assert garen["games"] == 40
    assert garen["position"] == "TOP"
    assert garen["win_rate"] == 60.0, f"가렌 승률: {garen['win_rate']} != 60.0"
    assert garen["pick_rate"] == 40.0, f"가렌 픽률: {garen['pick_rate']} != 40.0"
    assert garen["ban_rate"] == 15.0, f"가렌 밴률: {garen['ban_rate']} != 15.0"
    assert garen["kda"] == 4.5, f"가렌 KDA: {garen['kda']} != 4.5"
    assert garen["name"] == "가렌"
    _ok("가렌(Garen) 승률 60.0%, 픽률 40.0%, 밴률 15.0%, KDA 4.5 정확 산출 확인")

    # Ahri 상세 지표 검증
    ahri = next(c for c in res["results"] if c["id"] == "Ahri")
    assert ahri["games"] == 35
    assert ahri["position"] == "MID"
    assert ahri["win_rate"] == 40.0, f"아리 승률: {ahri['win_rate']} != 40.0"
    assert ahri["pick_rate"] == 35.0, f"아리 픽률: {ahri['pick_rate']} != 35.0"
    assert ahri["ban_rate"] == 10.0, f"아리 밴률: {ahri['ban_rate']} != 10.0"
    assert ahri["name"] == "아리"
    _ok("아리(Ahri) 승률 40.0%, 픽률 35.0%, 밴률 10.0%, 포지션 MID 매핑 정확 산출 확인")

    # sample_note 형식 검증
    expected_note_prefix = "100게임 · "
    assert expected_note_prefix in res["sample_note"]
    assert "30게임 미만 제외" in res["sample_note"]
    _ok(f"sample_note 정상 구성: {res['sample_note']}")

    # 포지션 필터링 검증
    clear_cache()
    top_res = compute_tier_list(position="TOP")
    assert all(c["position"] == "TOP" for c in top_res["results"]), "TOP 필터 시 전원 TOP 포지션이어야 함"
    assert any(c["id"] == "Garen" for c in top_res["results"])
    assert not any(c["id"] == "Ahri" for c in top_res["results"])
    _ok("포지션별 필터링(TOP) 무결성 확인")

    clear_cache()
    mid_res = compute_tier_list(position="MID")
    assert all(c["position"] == "MID" for c in mid_res["results"]), "MID 필터 시 전원 MID 포지션이어야 함"
    assert any(c["id"] == "Ahri" for c in mid_res["results"])
    assert not any(c["id"] == "Garen" for c in mid_res["results"])
    _ok("포지션별 필터링(MID) 무결성 확인")

    # min_games 수동 지정 시 Yasuo(10게임) 포함 검증
    clear_cache()
    loose_res = compute_tier_list(position="all", min_games=5)
    loose_ids = [c["id"] for c in loose_res["results"]]
    assert "Yasuo" in loose_ids, "min_games=5 일 때는 10게임 표본인 Yasuo 가 포함되어야 함"
    _ok("min_games 수동 인자 지정 시 동적 표본 필터링 동작 확인")


def test_api_endpoints():
    print("=" * 80)
    print("[Suite 9-C] /api/tierlist 및 /api/champion-analytics 200 OK & Schema Valid")
    print("=" * 80)

    # 1. /api/tierlist 200 응답 확인
    res = client.get("/api/tierlist")
    assert res.status_code == 200, f"/api/tierlist failed: {res.status_code}"
    data = res.json()

    # 상위 필드 확인
    for k in ("results", "summary", "patch", "sample_note", "source"):
        assert k in data, f"응답에 '{k}' 키가 누락됨"

    # summary 필드 확인
    summary = data["summary"]
    for sk in ("op_count", "tier1_count", "tier2_count", "tier3_count", "tier4_count", "tier5_count", "total_games"):
        assert sk in summary, f"summary 에 '{sk}' 키가 누락됨"

    # results 각 행 필드 명세 100% 일치 확인
    # rank, id, name, image, position, games, win_rate, pick_rate, ban_rate, kda, tier, tier_num, is_op, counters
    required_row_fields = [
        "rank", "id", "name", "image", "position", "games",
        "win_rate", "pick_rate", "ban_rate", "kda", "tier",
        "tier_num", "is_op", "counters"
    ]
    results = data["results"]
    assert len(results) > 0, "테스트 데이터가 채워져 있으므로 results 는 비어있지 않아야 함"

    for row in results:
        for rf in required_row_fields:
            assert rf in row, f"각 행에 '{rf}' 필드가 누락됨: {row}"
        assert isinstance(row["counters"], list)
        assert row["tier"] in ("OP", "1티어", "2티어", "3티어", "4티어", "5티어")
        assert row["tier_num"] in (0, 1, 2, 3, 4, 5)
        assert row["is_op"] == (row["tier"] == "OP")
        assert row["image"].startswith(DDRAGON_CDN), f"이미지 URL 은 Data Dragon CDN 기반이어야 함: {row['image']}"
        assert row["image"].endswith(".png")

    _ok("/api/tierlist 응답 200 및 전체 14개 필수 필드 무결성 확인")

    # 2. 정렬 파라미터 확인 (win_rate)
    res_sorted = client.get("/api/tierlist?sort=win_rate")
    assert res_sorted.status_code == 200
    sorted_rows = res_sorted.json()["results"]
    win_rates = [r["win_rate"] for r in sorted_rows]
    assert win_rates == sorted(win_rates, reverse=True), "win_rate 정렬 시 내림차순이어야 함"
    _ok("/api/tierlist?sort=win_rate 내림차순 정렬 동작 확인")

    # 3. /api/champion-analytics 엔드포인트 200 확인
    res_analytics = client.get("/api/champion-analytics?position=TOP&tier=EMERALD_PLUS")
    assert res_analytics.status_code == 200, f"/api/champion-analytics failed: {res_analytics.status_code}"
    a_data = res_analytics.json()
    assert a_data["position"] == "TOP"
    assert all(r["position"] == "TOP" for r in a_data["results"])
    _ok("/api/champion-analytics 200 OK 및 포지션 TOP 필터링 정상 응답 확인")


def test_meta_board():
    print("=" * 80)
    print("[Suite 9-C2] /api/meta-board 승률·픽률·밴률 상위 5 (최소 표본 통과 챔피언만)")
    print("=" * 80)

    from app.cache_engine import fast_cache
    fast_cache.delete_matching("meta_board:")
    clear_cache()

    res = client.get("/api/meta-board")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["patch"] == "16.21"
    assert data["position"] == "ALL"
    for field in ("win_rate", "pick_rate", "ban_rate"):
        rows = data[field]
        assert len(rows) <= 5
        ids = [r["id"] for r in rows]
        assert len(ids) == len(set(ids)), f"{field} 에 같은 챔피언이 중복됨"
        assert "Yasuo" not in ids, "표본 미달(10게임) 챔피언은 제외되어야 함"
        values = [r["value"] for r in rows]
        assert values == sorted(values, reverse=True), f"{field} 내림차순이어야 함"
        for r in rows:
            for k in ("id", "name", "image", "games", "value"):
                assert k in r
            assert r["image"].startswith(DDRAGON_CDN)
    assert [r["id"] for r in data["win_rate"]][:2] == ["Garen", "Ahri"]
    assert data["win_rate"][0]["value"] == 60.0
    assert data["pick_rate"][0]["id"] == "Garen" and data["pick_rate"][0]["value"] == 40.0
    assert data["ban_rate"][0]["id"] == "Garen" and data["ban_rate"][0]["value"] == 15.0
    _ok("ALL: Garen 승률 60.0 / 픽률 40.0 / 밴률 15.0 1위, Yasuo(표본 미달) 제외")

    mid = client.get("/api/meta-board?position=mid").json()
    assert mid["position"] == "MID"
    assert [r["id"] for r in mid["win_rate"]] == ["Ahri"]
    assert mid["ban_rate"][0]["value"] == 10.0
    _ok("position=mid: Ahri 만 포함, 밴률 10.0")

    bad = client.get("/api/meta-board?position=XYZ")
    assert bad.status_code == 400
    _ok("잘못된 position 은 400")


def test_matchups_and_head_to_head():
    print("=" * 80)
    print("[Suite 9-D] 1:1 맞대결(head_to_head) 및 카운터 목록(matchups) 실데이터 검증")
    print("=" * 80)

    # 매치 데이터 삽입 (Ahri 103 vs Zed 238: 15게임, Ahri 103 vs Syndra 134: 12게임, Ahri 103 vs Veigar 45: 5게임)
    # 최신 버전 "16.21"
    # 1) Ahri vs Zed: 15게임 (Ahri 9승 6패, Zed 6승 9패)
    for i in range(15):
        ahri_win = (i < 9)
        participants = [
            {
                "champion_id": 103,
                "position": "MID",
                "team_id": 100,
                "win": ahri_win,
                "kills": 8, "deaths": 2, "assists": 6,
                "gold": 12000, "cs": 200, "damage": 25000,
            },
            {
                "champion_id": 238,
                "position": "MID",
                "team_id": 200,
                "win": not ahri_win,
                "kills": 5, "deaths": 4, "assists": 3,
                "gold": 11000, "cs": 180, "damage": 22000,
            },
        ]
        insert_test_match(
            match_id=f"KR_MATCH_MU_ZED_{i}",
            game_version="16.21",
            participants=participants,
            bans=[],
            early_surrender=False,
        )

    # 2) Ahri vs Syndra: 12게임 (Ahri 3승 9패, Syndra 9승 3패)
    for i in range(12):
        ahri_win = (i < 3)
        participants = [
            {
                "champion_id": 103,
                "position": "MIDDLE",
                "team_id": 100,
                "win": ahri_win,
                "kills": 3, "deaths": 6, "assists": 4,
                "gold": 9000, "cs": 150, "damage": 15000,
            },
            {
                "champion_id": 134,
                "position": "MID",
                "team_id": 200,
                "win": not ahri_win,
                "kills": 9, "deaths": 2, "assists": 7,
                "gold": 13000, "cs": 210, "damage": 27000,
            },
        ]
        insert_test_match(
            match_id=f"KR_MATCH_MU_SYN_{i}",
            game_version="16.21",
            participants=participants,
            bans=[],
            early_surrender=False,
        )

    # 3) Ahri vs Veigar: 5게임 (10게임 미만 -> 제외되어야 함)
    for i in range(5):
        participants = [
            {
                "champion_id": 103,
                "position": "MID",
                "team_id": 100,
                "win": True,
                "kills": 10, "deaths": 1, "assists": 5,
                "gold": 14000, "cs": 220, "damage": 30000,
            },
            {
                "champion_id": 45,
                "position": "MID",
                "team_id": 200,
                "win": False,
                "kills": 1, "deaths": 10, "assists": 2,
                "gold": 7000, "cs": 120, "damage": 10000,
            },
        ]
        insert_test_match(
            match_id=f"KR_MATCH_MU_VEI_{i}",
            game_version="16.21",
            participants=participants,
            bans=[],
            early_surrender=False,
        )

    clear_cache()

    # 1. compute_matchups("Ahri")
    mu_data = compute_matchups("Ahri")
    assert mu_data["champion"]["id"] == "Ahri"
    assert mu_data["main_position"] == "MID"
    matchups = mu_data["matchups"]
    # Veigar (5게임) 제외, Zed (15게임), Syndra (12게임) 만 포함
    mu_champ_ids = [m["champion"]["id"] for m in matchups]
    assert "Zed" in mu_champ_ids, "15게임 맞대결인 Zed가 포함되어야 함"
    assert "Syndra" in mu_champ_ids, "12게임 맞대결인 Syndra가 포함되어야 함"
    assert "Veigar" not in mu_champ_ids, "10게임 미만인 Veigar는 제외되어야 함"

    # 게임 수 내림차순 정렬 확인 (Zed: 15, Syndra: 12)
    assert matchups[0]["champion"]["id"] == "Zed"
    assert matchups[0]["games"] == 15
    assert matchups[0]["wins"] == 9
    assert matchups[0]["win_rate"] == 60.0
    assert matchups[0]["gold_diff"] == 1000
    assert matchups[0]["cs_diff"] == 20
    assert matchups[0]["damage_diff"] == 3000
    _ok("compute_matchups 라인 페어링, 표본 10미만 제외, 골드/CS/데미지 차이 무결성 확인")

    # 2. compute_head_to_head("Ahri", "Zed")
    h2h_data = compute_head_to_head("Ahri", "Zed")
    assert h2h_data["games"] == 15
    assert h2h_data["wins"] == 9
    assert h2h_data["win_rate"] == 60.0
    assert h2h_data["champ_a"]["id"] == "Ahri"
    assert h2h_data["champ_b"]["id"] == "Zed"
    assert h2h_data["champ_a"]["kills"] == 8.0
    assert h2h_data["champ_b"]["kills"] == 5.0
    assert h2h_data["gold_diff"] == 1000
    assert h2h_data["cs_diff"] == 20
    assert h2h_data["damage_diff"] == 3000
    _ok("compute_head_to_head 직접 맞대결 지표 및 양측 평균 스탯 확인")

    # 3. 맞대결 0게임 케이스
    h2h_zero = compute_head_to_head("Ahri", "Garen")
    assert h2h_zero["games"] == 0
    assert h2h_zero["win_rate"] == 0.0
    assert "맞대결 전적 데이터가 없습니다" in h2h_zero["message"]
    _ok("맞대결 0게임 시 games: 0 및 안내 메시지 확인")

    # 4. compute_tier_list counters 필드 확인
    clear_cache()
    tier_res = compute_tier_list(position="MID", min_games=10)
    ahri_row = next((r for r in tier_res["results"] if r["id"] == "Ahri"), None)
    assert ahri_row is not None
    assert len(ahri_row["counters"]) > 0, "Ahri의 카운터 목록이 채워져 있어야 함"
    # 승률 오름차순: Syndra(25.0%)가 Zed(60.0%)보다 먼저 와야 함
    counter_ids = [c["id"] for c in ahri_row["counters"]]
    assert counter_ids[0] == "Syndra", "최저 승률인 Syndra가 1순위 카운터여야 함"
    assert ahri_row["counters"][0]["win_rate"] == 25.0
    assert ahri_row["counters"][0]["games"] == 12
    assert "Veigar" not in counter_ids, "10게임 미만인 Veigar는 티어표 카운터에도 없어야 함"
    _ok("compute_tier_list counters 필드에 실제 상성 카운터(승률 오름차순, 표본>=10) 반영 확인")

    # 5. API 엔드포인트 테스트
    # 5-1. /api/champion-matchup?champ1=Ahri (counters 모드)
    res_c = client.get("/api/champion-matchup?champ1=Ahri")
    assert res_c.status_code == 200
    c_json = res_c.json()
    assert c_json["mode"] == "counters"
    assert c_json["champion"]["id"] == "Ahri"
    assert len(c_json["matchups"]) >= 2
    _ok("GET /api/champion-matchup?champ1=Ahri (mode: counters) 200 OK 확인")

    # 5-2. /api/champion-matchup?champ1=Ahri&champ2=Zed (head_to_head 모드)
    res_h = client.get("/api/champion-matchup?champ1=Ahri&champ2=Zed")
    assert res_h.status_code == 200
    h_json = res_h.json()
    assert h_json["mode"] == "head_to_head"
    assert h_json["games"] == 15
    assert h_json["champ_a"]["id"] == "Ahri"
    assert h_json["champ_b"]["id"] == "Zed"
    _ok("GET /api/champion-matchup?champ1=Ahri&champ2=Zed (mode: head_to_head) 200 OK 확인")

    # 5-3. /api/champion-matchup?champion=Ahri&enemy=Zed (레거시 파라미터 호환)
    res_legacy = client.get("/api/champion-matchup?champion=Ahri&enemy=Zed")
    assert res_legacy.status_code == 200
    leg_json = res_legacy.json()
    assert leg_json["mode"] == "head_to_head"
    assert leg_json["games"] == 15
    _ok("GET /api/champion-matchup?champion=Ahri&enemy=Zed (레거시 쿼리) 200 OK 확인")

    # 5-4. 존재하지 않는 챔피언 404
    res_404 = client.get("/api/champion-matchup?champ1=NonExistentChampionXYZ")
    assert res_404.status_code == 404
    _ok("GET /api/champion-matchup 존재하지 않는 챔피언 404 확인")


def _duo_team(team_id, win, adc, sup, mid=1, jug=2, top=3):
    return [
        {"champion_id": adc, "position": "BOTTOM", "team_id": team_id, "win": win},
        {"champion_id": sup, "position": "UTILITY", "team_id": team_id, "win": win},
        {"champion_id": mid, "position": "MIDDLE", "team_id": team_id, "win": win},
        {"champion_id": jug, "position": "JUNGLE", "team_id": team_id, "win": win},
        {"champion_id": top, "position": "TOP", "team_id": team_id, "win": win},
    ]


def test_duo_synergy():
    print("=" * 80)
    print("[Suite 9-E] 듀오 시너지 (같은 팀 2인 조합) 실데이터 검증")
    print("=" * 80)

    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    clear_cache()
    empty = compute_duo_synergy("bot")
    assert empty["duos"] == [] and empty["total_games"] == 0
    _ok("매치 0개면 듀오 빈 결과")

    # 블루: 카이사(145)+노틸러스(111) 12게임 9승 / 레드: 이즈리얼(81)+유미(350) 12게임 3승
    # 추가 4게임: 카이사+유미(블루, 4승) vs 이즈리얼+노틸러스(레드) -> 표본 미달(4게임)
    n = 0
    for i in range(12):
        blue_win = i < 9
        insert_test_match(f"KR_DUO_{n}", "16.21", _duo_team(100, blue_win, 145, 111) + _duo_team(200, not blue_win, 81, 350, 4, 5, 6))
        n += 1
    for i in range(4):
        insert_test_match(f"KR_DUO_{n}", "16.21", _duo_team(100, True, 145, 350) + _duo_team(200, False, 81, 111, 4, 5, 6))
        n += 1
    clear_cache()

    res = compute_duo_synergy("bot")
    pairs = {(d["a_id"], d["b_id"]): d for d in res["duos"]}
    assert set(pairs) == {("Kaisa", "Nautilus"), ("Ezreal", "Yuumi")}, f"10게임 미만 조합·다른 팀끼리는 제외돼야 함: {list(pairs)}"
    kn = pairs[("Kaisa", "Nautilus")]
    assert kn["games_played"] == 12 and kn["wins"] == 9 and kn["win_rate"] == 75.0
    assert kn["pick_rate"] == round(12 / 16 * 100, 2)
    # 카이사 BOT 16게임 13승(81.25%), 노틸러스 SUP 16게임 9승(56.25%) -> 기대 68.8, 차이 +6.2
    assert kn["expected_win_rate"] == 68.8, kn["expected_win_rate"]
    assert kn["synergy_delta"] == 6.2, kn["synergy_delta"]
    assert kn["adc_name"] == kn["a_name"] and kn["sup_id"] == "Nautilus"
    assert kn["tier"] in ("OP", "1", "2", "3", "4", "5")
    assert kn["a_image"].startswith(DDRAGON_CDN)
    _ok("같은 팀 BOTTOM+UTILITY 짝짓기, 승률·픽률·기대 승률·상승폭, 표본 미달 제외")

    flt = compute_duo_synergy("bot", None, "노틸")
    assert [d["b_id"] for d in flt["duos"]] == ["Nautilus"]
    _ok("한글 이름 부분 일치 필터")

    r = client.get("/api/duo-synergy")
    assert r.status_code == 200 and len(r.json()["duos"]) == 2
    r = client.get("/api/upper-duo-synergy?category=all")
    assert r.status_code == 200
    body = r.json()
    assert "mid_jungle" in body and "top_jungle" in body and "sample_note" in body
    bm = client.get("/api/duo-bot-matchups")
    assert bm.status_code == 200 and "matchups" in bm.json() and "sample_note" in bm.json()
    assert client.get("/api/duo-bot-matchup", params={"adc1": "a", "sup1": "b", "adc2": "c", "sup2": "d"}).status_code == 404
    pair = client.get("/api/combo-synergy-calculator", params={"champ_a": "징크스", "champ_b": "룰루"})
    assert pair.status_code == 200 and pair.json()["champion_a"]["id"] == "Jinx", pair.text
    assert client.get("/api/combo-synergy-calculator", params={"champ_a": "없는챔프", "champ_b": "룰루"}).status_code == 404
    assert client.get("/api/combo-synergy-featured").status_code == 404
    _ok("/api/duo-synergy·/api/upper-duo-synergy·2:2 맞대결 목록·조합 계산기 200 (실데이터), 생성 프리셋은 계속 차단")


def test_champion_build():
    print("=" * 80)
    print("[Suite 9-F] 챔피언 빌드 (룬·주문·종료 시점 코어·신발) 실데이터 검증")
    print("=" * 80)
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    clear_cache()
    assert compute_champion_build("없는챔피언") is None
    empty = compute_champion_build("Ahri")
    assert empty["total_games"] == 0 and empty["core_builds"] == [] and empty["quick_copy_text"] == ""
    _ok("챔피언 없으면 None, 표본 없으면 빈 목록 (기본값 지어내지 않음)")

    # 아리(103) 미드 5게임: 감전(8112, 지배 8100 + 마법 8200), 점멸(4)+점화(14)
    # 종료 인벤토리: 루덴(6655)·존야(3157)·라바돈(3089) + 마법사의 신발(3020) + 부품 도란의 반지(1056)
    for i in range(5):
        p = {"champion_id": 103, "position": "MIDDLE", "team_id": 100, "win": i < 3,
             "items": [6655, 3157, 3089, 3020, 1056, 0, 3340], "spells": [14, 4],
             "keystone": 8112, "primary_style": 8100, "sub_style": 8200}
        insert_test_match(f"KR_BUILD_{i}", "16.21", [p])
    # 아리 탑 1게임 (표본 미달 포지션)
    insert_test_match("KR_BUILD_TOP", "16.21", [{"champion_id": 103, "position": "TOP", "team_id": 100, "win": True,
                                                 "items": [], "spells": [4, 12]}])
    clear_cache()
    b = compute_champion_build("아리")
    assert b["position"] == "MID" and b["total_games"] == 5
    assert b["runes"]["keystone_id"] == 8112 and b["runes"]["games"] == 5 and b["runes"]["win_rate"] == 60.0
    assert b["rune_options"][0]["page"] is None, "perks 없는 게임만 있으면 page is None"
    assert b["rune_page_note"] == "전체 룬 페이지는 새로 수집되는 게임부터 집계됩니다."
    assert [s["id"] for s in b["spells"]] == [4, 14], "점멸이 먼저"
    core = b["core_builds"][0]
    assert sorted(i["id"] for i in core["items"]) == [3089, 3157, 6655] and core["games"] == 5
    # 미드는 신발이 자동으로 3단계가 되므로 2단계(3020)를 3단계 업그레이드로 합쳐 보여준다
    from app.champion_stats import _boots_upgrade
    upgraded = _boots_upgrade(3020)
    assert upgraded != 3020, "3020 should have a tier-3 upgrade in item data"
    assert [x["id"] for x in b["boots"]] == [upgraded]
    assert 1056 not in [x["id"] for x in b["popular_items"]], "부품은 완성 아이템 목록에서 제외"
    assert "5게임" in b["sample_note"] and b["quick_copy_text"]
    top = compute_champion_build("Ahri", "TOP")
    assert top["position"] == "TOP" and top["total_games"] == 1 and top["spell_options"] == [], "3게임 미만 항목 제외"
    _ok("룬·주문·코어·신발 집계, 주 포지션 선택, 부품 제외, 표본 미달 제외, perks 미포함 시 page is None 확인")

    # perks 6개 넣은 게임 집계 검증 (표본 3개 이상)
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    clear_cache()

    full_perks = [8112, 8139, 8137, 8135, 8226, 8237]
    full_shards = [5008, 5005, 5011]
    for i in range(4):
        p_full = {
            "champion_id": 103,
            "position": "MIDDLE",
            "team_id": 100,
            "win": i < 3,
            "items": [6655, 3157, 3089, 3020, 1056, 0, 3340],
            "spells": [14, 4],
            "keystone": 8112,
            "primary_style": 8100,
            "sub_style": 8200,
            "perks": full_perks,
            "shards": full_shards,
        }
        insert_test_match(f"KR_BUILD_FULL_{i}", "16.21", [p_full])

    clear_cache()
    b_full = compute_champion_build("아리")
    assert b_full is not None
    assert b_full["rune_options"][0]["page"] is not None
    p_opt = b_full["rune_options"][0]["page"]
    assert len(p_opt["runes"]) == 6
    assert [r["id"] for r in p_opt["runes"]] == full_perks
    assert len(p_opt["shards"]) == 3
    assert [s["id"] for s in p_opt["shards"]] == full_shards
    assert p_opt["games"] == 4
    assert p_opt["win_rate"] == 75.0
    assert b_full["rune_page_note"] == "전체 룬 페이지는 이 기능 추가 후 수집된 4게임 기준"
    assert " / " in b_full["quick_copy_text"]
    assert p_opt["runes"][0]["name"] in b_full["quick_copy_text"]
    _ok("perks 6개 넣은 게임의 전체 룬 페이지(runes 6개, shards 3개, games, win_rate, 안내 문구, quick_copy_text) 검증 완료")

    r = client.get("/api/champion-build/Ahri")
    assert r.status_code == 200 and r.json()["champion"]["id"] == "Ahri"
    assert client.get("/api/champion-build/NoSuchChamp").status_code == 404
    _ok("/api/champion-build 200 / 없는 챔피언 404")


def test_champion_build_vs():
    print("=" * 80)
    print("[Suite 9-F2] 특정 상대 맞라인 빌드 (vs 필터) 검증")
    print("=" * 80)
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    clear_cache()

    def ahri(win, spells):
        return {"champion_id": 103, "position": "MIDDLE", "team_id": 100, "win": win,
                "items": [6655, 3157, 3089, 3020], "spells": spells,
                "keystone": 8112, "primary_style": 8100, "sub_style": 8200}

    # 아리 vs 제드(238) 미드 4게임 (점멸+점화, 1승), 아리 vs 야스오(157) 미드 3게임 (점멸+정화, 3승)
    for i in range(4):
        insert_test_match(f"KR_VS_ZED_{i}", "16.21", [
            ahri(i == 0, [4, 14]),
            {"champion_id": 238, "position": "MIDDLE", "team_id": 200, "win": i != 0},
            {"champion_id": 157, "position": "TOP", "team_id": 200, "win": i != 0},  # 다른 라인 야스오는 무시
        ])
    for i in range(3):
        insert_test_match(f"KR_VS_YAS_{i}", "16.21", [
            ahri(True, [4, 1]),
            {"champion_id": 157, "position": "MIDDLE", "team_id": 200, "win": False},
        ])
    clear_cache()
    allb = compute_champion_build("Ahri")
    assert allb["total_games"] == 7 and allb["vs"] is None
    vz = compute_champion_build("Ahri", vs="Zed")
    assert vz["total_games"] == 4 and vz["win_rate"] == 25.0, vz["total_games"]
    assert vz["vs"]["id"] == "Zed" and vz["vs"]["image"]
    assert [s["id"] for s in vz["spells"]] == [4, 14]
    vy = compute_champion_build("아리", vs="157")
    assert vy["total_games"] == 3 and vy["win_rate"] == 100.0 and vy["vs"]["id"] == "Yasuo"
    assert [s["id"] for s in vy["spells"]] == [4, 1]
    assert compute_champion_build("Ahri", vs="없는챔피언") is None
    none = compute_champion_build("Ahri", vs="Lux")
    assert none["total_games"] == 0 and none["core_builds"] == []
    _ok("vs 필터: 같은 포지션 상대 팀 챔피언만, 캐시 키 분리, 없는 상대 None, 표본 없으면 빈 목록")

    r = client.get("/api/champion-build/Ahri", params={"vs": "Zed"})
    assert r.status_code == 200 and r.json()["total_games"] == 4 and r.json()["vs"]["id"] == "Zed"
    r2 = client.get("/api/champion-build/Ahri", params={"vs": "Yasuo"})
    assert r2.status_code == 200 and r2.json()["total_games"] == 3
    assert client.get("/api/champion-build/Ahri", params={"vs": "NoSuchChamp"}).status_code == 404
    _ok("/api/champion-build?vs= 200 (상대별 캐시 분리) / 없는 상대 404")


def test_champion_build_timeline_fields():
    print("=" * 80)
    print("[Suite 9-I] 빌드 창 스킬 순서 · 시작 아이템 · 구매 순서 검증")
    print("=" * 80)

    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    clear_cache()

    # 1. timeline 필드(skills, start_items, item_order)가 없는 매치만 있을 때:
    #    빈 리스트 + 안내 문구 확인
    for i in range(4):
        insert_test_match(
            match_id=f"KR_NO_TL_{i}",
            game_version="16.21",
            participants=[{
                "champion_id": 103,
                "position": "MIDDLE",
                "team_id": 100,
                "win": True,
                "items": [6655, 3157, 3089],
            }],
        )

    clear_cache()
    b_no_tl = compute_champion_build("아리")
    assert b_no_tl is not None
    assert b_no_tl["skill_orders"] == []
    assert b_no_tl["start_items"] == []
    assert b_no_tl["item_build_order"] == []
    assert b_no_tl["timeline_note"] == "스킬·시작템·구매 순서는 새로 수집되는 게임부터 집계됩니다."
    _ok("타임라인 필드가 없을 때 빈 리스트 및 안내 문구 확인")

    # 2. timeline 필드가 있는 게임 6개 + 없는 게임 2개
    # 6개 중:
    # - 3개는 item_order: [1055, 2003, 6655, 3157, 3089] (6655 > 3157 > 3089)
    # - 3개는 item_order: [1055, 2003, 3157, 6655, 3089] (3157 > 6655 > 3089) -> 순서 다르면 다른 줄
    # 모든 6개는:
    # - skills: Q 5번 -> E 5번 -> W 5번 마스터 ("Q>E>W", first3: "Q,E,W")
    # - start_items: [1055, 2003]
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    clear_cache()

    test_skills = [
        1, 3, 2, 1, 1, 4, 1, 3, 1,  # Q 5개 (lvl 9)
        4, 3, 3, 3,                 # E 5개 (lvl 13)
        2, 2, 4, 2, 2,              # W 5개 (lvl 18)
    ]
    test_start = [1055, 2003]

    for i in range(6):
        io = [1055, 2003, 6655, 3157, 3089] if i < 3 else [1055, 2003, 3157, 6655, 3089]
        insert_test_match(
            match_id=f"KR_TL_{i}",
            game_version="16.21",
            participants=[{
                "champion_id": 103,
                "position": "MIDDLE",
                "team_id": 100,
                "win": (i % 2 == 0),
                "items": [6655, 3157, 3089],
                "skills": test_skills,
                "start_items": test_start,
                "item_order": io,
            }],
        )

    # 타임라인 필드 없는 게임 2개 추가
    for i in range(2):
        insert_test_match(
            match_id=f"KR_TL_NONE_{i}",
            game_version="16.21",
            participants=[{
                "champion_id": 103,
                "position": "MIDDLE",
                "team_id": 100,
                "win": True,
                "items": [6655, 3157, 3089],
            }],
        )

    clear_cache()
    b_tl = compute_champion_build("아리")
    assert b_tl is not None
    assert b_tl["total_games"] == 8

    # timeline_note
    assert b_tl["timeline_note"] == "스킬·시작템·구매 순서는 타임라인이 수집된 6게임 기준"

    # skill_orders: 마스터 순서 문자열 "Q>E>W", first3 "Q,E,W"
    assert len(b_tl["skill_orders"]) == 1
    sk0 = b_tl["skill_orders"][0]
    assert sk0["order"] == "Q>E>W"
    assert sk0["first3"] == "Q,E,W"
    assert sk0["games"] == 6
    assert sk0["win_rate"] == 50.0
    assert sk0["pick_rate"] == 100.0

    # start_items: 시작템 조합 games
    assert len(b_tl["start_items"]) == 1
    si0 = b_tl["start_items"][0]
    assert si0["games"] == 6
    assert [it["id"] for it in si0["items"]] == [1055, 2003]

    # item_build_order: 순서 다르면 다른 줄
    assert len(b_tl["item_build_order"]) == 2
    ibo0 = b_tl["item_build_order"][0]
    ibo1 = b_tl["item_build_order"][1]
    assert ibo0["games"] == 3
    assert ibo1["games"] == 3
    ids0 = [it["id"] for it in ibo0["items"]]
    ids1 = [it["id"] for it in ibo1["items"]]
    assert ids0 != ids1
    assert set(ids0) == {6655, 3157, 3089}
    assert set(ids1) == {6655, 3157, 3089}
    _ok("스킬 마스터 순서 문자열, 시작템 조합 games, 구매 순서(순서 다르면 다른 줄), 타임라인 안내 문구 검증 완료")


def test_patch_shift():
    print("=" * 80)
    print("[Suite 9-G] 패치 변동(patch shift) 승률 집계 및 필터 검증")
    print("=" * 80)

    # 1. 매치가 전혀 없거나 DB 비었을 때
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    clear_cache()

    empty_res = compute_patch_shift()
    assert empty_res["champions"] == [], "매치가 없으면 champions는 빈 리스트여야 함"
    assert empty_res["sample_note"] == "비교할 이전 패치 데이터가 아직 없습니다."
    _ok("매치 0개 시 빈 결과 및 안내 문구 확인")

    # 2. 버전이 하나뿐일 때 ("16.20" 만 존재)
    for i in range(35):
        insert_test_match(
            match_id=f"KR_ONE_VER_{i}",
            game_version="16.20",
            participants=[
                {"champion_id": 86, "position": "TOP", "win": True},
            ],
        )
    clear_cache()
    one_ver_res = compute_patch_shift()
    assert one_ver_res["champions"] == [], "버전이 하나뿐이면 champions는 빈 리스트여야 함"
    assert one_ver_res["patch"] == "16.20"
    assert one_ver_res["prev_patch"] is None
    assert one_ver_res["sample_note"] == "비교할 이전 패치 데이터가 아직 없습니다."
    _ok("버전이 하나뿐일 때 빈 결과 및 이전 패치 없음 안내 확인")

    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()

    # 3. "16.20"(이전)과 "16.21"(최신) 매치 생성
    #    - 가렌 (86, TOP): 16.20에서 30게임 12승(40.0%), 16.21에서 40게임 24승(60.0%) -> delta +20.0%p (상승)
    #    - 다리우스 (122, TOP): 16.20에서 35게임 21승(60.0%), 16.21에서 35게임 14승(40.0%) -> delta -20.0%p (하락)
    #    - 아리 (103, MID): 16.20에서 10게임 (표본 30 미달), 16.21에서 35게임 -> 제외 대상
    #    - 야스오 (157, MID): 16.20에서 35게임, 16.21에서 10게임 (표본 30 미달) -> 제외 대상
    #    - 가렌 16.21 밴 8회 (밴률 8/40 = 20.0%)
    for i in range(40):
        parts_old = []
        if i < 30:
            parts_old.append({"champion_id": 86, "position": "TOP", "win": i < 12, "team_id": 100})
        if i < 35:
            parts_old.append({"champion_id": 122, "position": "TOP", "win": i < 21, "team_id": 200})
        if i < 10:
            parts_old.append({"champion_id": 103, "position": "MIDDLE", "win": i < 5, "team_id": 100})
        if i < 35:
            parts_old.append({"champion_id": 157, "position": "MIDDLE", "win": i < 20, "team_id": 200})
        insert_test_match(
            match_id=f"KR_SHIFT_OLD_{i}",
            game_version="16.20",
            participants=parts_old,
        )

    for i in range(40):
        parts_new = []
        bans_new = []
        parts_new.append({"champion_id": 86, "position": "TOP", "win": i < 24, "team_id": 100})
        if i < 35:
            parts_new.append({"champion_id": 122, "position": "TOP", "win": i < 14, "team_id": 200})
        if i < 35:
            parts_new.append({"champion_id": 103, "position": "MIDDLE", "win": i < 20, "team_id": 100})
        if i < 10:
            parts_new.append({"champion_id": 157, "position": "MIDDLE", "win": i < 5, "team_id": 200})
        if i < 8:
            bans_new.append(86)
        insert_test_match(
            match_id=f"KR_SHIFT_NEW_{i}",
            game_version="16.21",
            participants=parts_new,
            bans=bans_new,
        )

    clear_cache()
    assert compute_patch_shift(limit=8)["champions"] == [], "30~40게임의 ±20%p는 표본 오차 안이라 제외"
    saved_z = _cs.SHIFT_MIN_Z
    _cs.SHIFT_MIN_Z = 0.0  # 아래는 계산값 검증
    clear_cache()
    try:
        shift_res = compute_patch_shift(limit=8)
    finally:
        _cs.SHIFT_MIN_Z = saved_z
    assert shift_res["patch"] == "16.21"
    assert shift_res["prev_patch"] == "16.20"
    assert "16.20" in shift_res["sample_note"] and "16.21" in shift_res["sample_note"]

    champs = shift_res["champions"]
    # 아리, 야스오는 표본 미달로 제외되어 가렌과 다리우스 2개만 포함되어야 함
    champ_ids = [c["champ_id"] for c in champs]
    assert "Ahri" not in champ_ids, "16.20 표본 미달(10게임)인 아리는 제외되어야 함"
    assert "Yasuo" not in champ_ids, "16.21 표본 미달(10게임)인 야스오는 제외되어야 함"
    assert "Garen" in champ_ids and "Darius" in champ_ids

    # 상승(가렌)과 하락(다리우스) 교차 배치 검증
    assert champs[0]["champ_id"] == "Garen", "상승 챔피언이 먼저 나와야 함"
    assert champs[1]["champ_id"] == "Darius", "하락 챔피언이 번갈아 나와야 함"

    garen = champs[0]
    assert garen["is_buff"] is True
    assert garen["delta"] == 20.0
    assert garen["delta_winrate_str"] == "+20.0%p"
    assert garen["current_winrate"] == 60.0
    assert garen["prev_winrate"] == 40.0
    assert garen["games"] == 40
    assert garen["prev_games"] == 30
    assert garen["pick_rate"] == 100.0
    assert garen["ban_rate"] == 20.0
    assert garen["comment"] == "16.20 40.0% → 16.21 60.0% (30게임 → 40게임)"

    darius = champs[1]
    assert darius["is_buff"] is False
    assert darius["delta"] == -20.0
    assert darius["delta_winrate_str"] == "-20.0%p"
    assert darius["current_winrate"] == 40.0
    assert darius["prev_winrate"] == 60.0
    assert darius["games"] == 35
    assert darius["prev_games"] == 35
    assert darius["pick_rate"] == 87.5
    assert darius["ban_rate"] == 0.0
    assert darius["comment"] == "16.20 60.0% → 16.21 40.0% (35게임 → 35게임)"

    _ok("패치 변동 상승·하락 delta 정확성, 표본 미달 제외, 버전 단일/없음 검증 완료")


def test_new_patch_falls_back_to_previous():
    print("=" * 80)
    print("[Suite 9-H] 새 패치 표본 부족 시 직전 패치 합산")
    print("=" * 80)
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    for i in range(5):
        insert_test_match(f"KR_OLDP_{i}", "16.21", [{"champion_id": 103, "position": "MIDDLE", "team_id": 100, "win": True}])
    for i in range(2):
        insert_test_match(f"KR_NEWP_{i}", "16.22", [{"champion_id": 103, "position": "MIDDLE", "team_id": 100, "win": False}])
    _cs.MIN_LATEST_PATCH_GAMES = 3
    try:
        clear_cache()
        patch, matches = _cs._get_latest_valid_matches()
        assert patch == "16.22+16.21" and len(matches) == 7, (patch, len(matches))
        _cs.MIN_LATEST_PATCH_GAMES = 2
        clear_cache()
        patch, matches = _cs._get_latest_valid_matches()
        assert patch == "16.22" and len(matches) == 2
    finally:
        _cs.MIN_LATEST_PATCH_GAMES = 0
        clear_cache()
    _ok("새 패치가 기준 미만이면 직전 패치 합산 + 라벨 표시, 기준 이상이면 새 패치만")


def test_tier_list_prev_patch_rank():
    print("=" * 80)
    print("[Suite 9-H2] 티어표 직전 패치 순위·승률 (prev_rank / prev_win_rate)")
    print("=" * 80)
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()

    def _add(prefix, ver, cid, games, wins):
        for i in range(games):
            insert_test_match(f"KR_PREVRANK_{prefix}_{i}", ver,
                              [{"champion_id": cid, "position": "TOP", "team_id": 100, "win": i < wins}])

    # 직전 패치 16.21: 가렌 75%, 다리우스 25%
    _add("G21", "16.21", 86, 40, 30)
    _add("D21", "16.21", 122, 40, 10)
    # 최신 패치 16.22: 가렌 25%, 다리우스 75%, 티모(신규) 50%
    _add("G22", "16.22", 86, 40, 10)
    _add("D22", "16.22", 122, 40, 30)
    _add("T22", "16.22", 17, 40, 20)

    old_min = _cs.MIN_LATEST_PATCH_GAMES
    _cs.MIN_LATEST_PATCH_GAMES = 0
    try:
        clear_cache()
        res = compute_tier_list(position="TOP", min_games=10)
        assert res["patch"] == "16.22" and res["prev_patch"] == "16.21", (res["patch"], res["prev_patch"])
        rows = {r["id"]: r for r in res["results"]}
        darius, garen, teemo = rows["Darius"], rows["Garen"], rows["Teemo"]
        assert darius["rank"] == 1 and darius["prev_rank"] == 2, darius
        assert darius["prev_win_rate"] == 25.0 and darius["win_rate"] == 75.0
        assert garen["rank"] == 3 and garen["prev_rank"] == 1, garen
        assert garen["prev_win_rate"] == 75.0
        assert teemo["prev_rank"] is None and teemo["prev_win_rate"] is None

        # 직전 패치 순위도 같은 정렬 기준으로 매긴다
        clear_cache()
        res_wr = compute_tier_list(position="TOP", min_games=10, sort="win_rate")
        g = next(r for r in res_wr["results"] if r["id"] == "Garen")
        assert g["prev_rank"] == 1

        # 최신 패치 표본 부족으로 합친 라벨("16.22+16.21")이면 비교하지 않는다
        _cs.MIN_LATEST_PATCH_GAMES = 1000
        clear_cache()
        merged = compute_tier_list(position="TOP", min_games=10)
        assert "+" in merged["patch"] and merged["prev_patch"] is None
        assert all(r["prev_rank"] is None and r["prev_win_rate"] is None for r in merged["results"])
    finally:
        _cs.MIN_LATEST_PATCH_GAMES = old_min
        clear_cache()

    # 패치가 하나뿐이면 prev 값 없음
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches WHERE game_version = '16.21'")
    conn.commit()
    conn.close()
    clear_cache()
    single = compute_tier_list(position="TOP", min_games=10)
    assert single["prev_patch"] is None
    assert all(r["prev_rank"] is None for r in single["results"])
    clear_cache()
    _ok("prev_rank/prev_win_rate: 순위 상승·하락·신규, 합친 패치·단일 패치일 때 None")


def test_pair_synergy():
    print("=" * 80)
    print("[Suite 9-J] 두 챔피언 조합 시너지 및 상대 전적 검증")
    print("=" * 80)

    # 1. 존재하지 않는 챔피언 처리 검증 (None 반환)
    assert compute_pair_synergy("NonExistentChampA", "Kaisa") is None
    assert compute_pair_synergy("Kaisa", "NonExistentChampB") is None
    _ok("존재하지 않는 챔피언 입력 시 None 반환 확인")

    # 2. 매치 0개일 때 결과 검증
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    clear_cache()

    zero_res = compute_pair_synergy("Kaisa", "Nautilus")
    assert zero_res is not None
    assert zero_res["games"] == 0
    assert zero_res["wins"] == 0
    assert zero_res["win_rate"] is None
    assert zero_res["positions"] is None
    assert zero_res["a_win_rate"] is None
    assert zero_res["b_win_rate"] is None
    assert zero_res["expected_win_rate"] is None
    assert zero_res["synergy_delta"] is None
    assert zero_res["vs_games"] == 0
    assert zero_res["vs_a_win_rate"] is None
    assert zero_res["sample_note"] == "같은 팀 표본이 10게임 미만입니다 (0게임)"
    _ok("매치 0개일 때 games: 0, win_rate/synergy_delta: None 및 표본 미달 안내 문구 확인")

    # 3. 같은 팀 표본 미달 (< 10) 및 상대 팀 검증
    # 카이사(145)+노틸러스(111) 같은 팀 5게임 (3승 2패)
    for i in range(5):
        insert_test_match(
            f"KR_PAIR_SUB_{i}",
            "16.21",
            [
                {"champion_id": 145, "position": "BOTTOM", "team_id": 100, "win": i < 3},
                {"champion_id": 111, "position": "UTILITY", "team_id": 100, "win": i < 3},
            ],
        )
    clear_cache()
    sub_res = compute_pair_synergy("카이사", "노틸러스")
    assert sub_res is not None
    assert sub_res["games"] == 5
    assert sub_res["wins"] == 3
    assert sub_res["win_rate"] is None
    assert sub_res["synergy_delta"] is None
    assert sub_res["positions"] == ["BOTTOM", "UTILITY"]
    assert "같은 팀 표본이 10게임 미만입니다 (5게임)" in sub_res["sample_note"]
    assert sub_res["vs_games"] == 0
    assert sub_res["vs_a_win_rate"] is None
    _ok("같은 팀 표본 10게임 미만일 때 win_rate/synergy_delta: None 및 positions 최빈값 확인")

    # 4. 표본 >= 10: games, wins, win_rate, expected_win_rate, synergy_delta, vs_games, vs_a_win_rate
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    clear_cache()

    # 12게임: 같은 팀 (카이사 145 + 노틸러스 111) -> 9승 3패 (75.0%)
    for i in range(12):
        win = (i < 9)
        insert_test_match(
            f"KR_PAIR_SAME_{i}",
            "16.21",
            [
                {"champion_id": 145, "position": "BOTTOM", "team_id": 100, "win": win},
                {"champion_id": 111, "position": "UTILITY", "team_id": 100, "win": win},
                {"champion_id": 81, "position": "BOTTOM", "team_id": 200, "win": not win},
                {"champion_id": 350, "position": "UTILITY", "team_id": 200, "win": not win},
            ],
        )

    # 12게임: 상대 팀 (카이사 팀 100 vs 노틸러스 팀 200) -> 카이사 8승 4패 (66.7%)
    for i in range(12):
        win = (i < 8)
        insert_test_match(
            f"KR_PAIR_VS_{i}",
            "16.21",
            [
                {"champion_id": 145, "position": "BOTTOM", "team_id": 100, "win": win},
                {"champion_id": 350, "position": "UTILITY", "team_id": 100, "win": win},
                {"champion_id": 81, "position": "BOTTOM", "team_id": 200, "win": not win},
                {"champion_id": 111, "position": "UTILITY", "team_id": 200, "win": not win},
            ],
        )

    clear_cache()
    # 영문 ID로 호출 검증
    res_pair = compute_pair_synergy("Kaisa", "Nautilus")
    assert res_pair is not None
    assert res_pair["champion_a"]["id"] == "Kaisa"
    assert res_pair["champion_b"]["id"] == "Nautilus"
    assert res_pair["games"] == 12
    assert res_pair["wins"] == 9
    assert res_pair["win_rate"] == 75.0
    assert res_pair["positions"] == ["BOTTOM", "UTILITY"]

    # 단독 승률:
    # 카이사 전체: 12(같은 팀) + 12(상대 팀) = 24게임, 승수 = 9 + 8 = 17승 -> 17/24 = 70.8%
    # 노틸러스 전체: 12(같은 팀) + 12(상대 팀) = 24게임, 승수 = 9 + 4 = 13승 -> 13/24 = 54.2%
    assert res_pair["a_win_rate"] == 70.8
    assert res_pair["b_win_rate"] == 54.2
    # expected_win_rate = (70.8 + 54.2) / 2 = 62.5%
    assert res_pair["expected_win_rate"] == 62.5
    # synergy_delta = 75.0 - 62.5 = 12.5%p
    assert res_pair["synergy_delta"] == 12.5

    # 상대 전적: vs_games 12, A 쪽 승리 8 -> 66.7%
    assert res_pair["vs_games"] == 12
    assert res_pair["vs_a_win_rate"] == 66.7
    assert "최신 패치 16.21 고티어 솔로랭크 · 같은 팀 12게임" in res_pair["sample_note"]
    _ok("compute_pair_synergy games/win_rate/기대승률/시너지delta/상대전적 무결성 확인")


def test_bot_lane_matchups():
    print("=" * 80)
    print("[Suite 9-K] 바텀 2:2 맞대결 통계 검증")
    print("=" * 80)

    # 1. 매치 0개일 때 빈 결과 검증
    conn = get_connection()
    conn.execute("DELETE FROM collected_matches")
    conn.commit()
    conn.close()
    clear_cache()

    empty_res = compute_bot_lane_matchups()
    assert empty_res["matchups"] == []
    assert empty_res["total_matches"] == 0
    assert "맞대결 8게임 이상만" in empty_res["sample_note"]
    _ok("매치 0개일 때 matchups: [] 및 sample_note 확인")

    # 2. 바텀 맞대결 매치 생성:
    # Duo A: Kaisa(145) + Nautilus(111) [team 100]
    # Duo B: Ezreal(81) + Yuumi(350) [team 200]
    # 12게임:
    # Duo A: 9승 3패, gold 12000 + 6000 = 18000, kills 6 + 2 = 8
    # Duo B: 3승 9패, gold 10000 + 5000 = 15000, kills 3 + 1 = 4
    # Duo B (81, 350) < Duo A (145, 111) 이므로 duo_1=Duo B, duo_2=Duo A
    for i in range(12):
        blue_win = (i < 9)
        insert_test_match(
            f"KR_BOT_M_{i}",
            "16.21",
            [
                {"champion_id": 145, "position": "BOTTOM", "team_id": 100, "win": blue_win, "gold": 12000, "kills": 6},
                {"champion_id": 111, "position": "UTILITY", "team_id": 100, "win": blue_win, "gold": 6000, "kills": 2},
                {"champion_id": 81, "position": "BOTTOM", "team_id": 200, "win": not blue_win, "gold": 10000, "kills": 3},
                {"champion_id": 350, "position": "UTILITY", "team_id": 200, "win": not blue_win, "gold": 5000, "kills": 1},
            ],
        )

    # 표본 미달 맞대결 (4게임 < 8게임): Duo A vs Duo C (Vayne 67 + Lulu 117) -> 결과에서 제외되어야 함
    for i in range(4):
        insert_test_match(
            f"KR_BOT_SMALL_{i}",
            "16.21",
            [
                {"champion_id": 145, "position": "BOTTOM", "team_id": 100, "win": True, "gold": 11000, "kills": 5},
                {"champion_id": 111, "position": "UTILITY", "team_id": 100, "win": True, "gold": 5000, "kills": 1},
                {"champion_id": 67, "position": "BOTTOM", "team_id": 200, "win": False, "gold": 8000, "kills": 2},
                {"champion_id": 117, "position": "UTILITY", "team_id": 200, "win": False, "gold": 4000, "kills": 0},
            ],
        )

    clear_cache()
    res = compute_bot_lane_matchups(limit=12)
    assert res["total_matches"] == 16
    assert len(res["matchups"]) == 1, "4게임 맞대결은 제외되고 12게임 맞대결 1개만 포함되어야 함"

    mu = res["matchups"][0]
    # 키 정렬에 따라 duo_1은 Ezreal+Yuumi, duo_2는 Kaisa+Nautilus
    assert mu["duo_1"]["adc"]["id"] == "Ezreal"
    assert mu["duo_1"]["sup"]["id"] == "Yuumi"
    assert mu["duo_2"]["adc"]["id"] == "Kaisa"
    assert mu["duo_2"]["sup"]["id"] == "Nautilus"

    assert mu["games"] == 12
    # Duo 1(Ezreal+Yuumi)은 12게임 중 3승 -> 25.0%
    assert mu["win_rate_1"] == 25.0
    # Duo 2(Kaisa+Nautilus)은 75.0%
    assert mu["win_rate_2"] == 75.0
    # duo_1 승률 + duo_2 승률 = 100.0 검증
    assert round(mu["win_rate_1"] + mu["win_rate_2"], 1) == 100.0

    # gold_diff = duo_1 gold(15000) - duo_2 gold(18000) = -3000
    assert mu["gold_diff"] == -3000
    # kills_1 = 4.0, kills_2 = 8.0
    assert mu["kills_1"] == 4.0
    assert mu["kills_2"] == 8.0

    assert "최신 패치 16.21 고티어 솔로랭크 · 맞대결 8게임 이상만" in res["sample_note"]
    _ok("compute_bot_lane_matchups 방향 정렬, 승률 합 100, gold_diff/kills, 표본 미달 제외 검증 완료")


def run_all_champion_stats_tests():
    test_empty_matches()
    test_champion_stats_computation()
    test_api_endpoints()
    test_meta_board()
    test_matchups_and_head_to_head()
    test_duo_synergy()
    test_champion_build()
    test_champion_build_vs()
    test_champion_build_timeline_fields()
    test_patch_shift()
    test_new_patch_falls_back_to_previous()
    test_tier_list_prev_patch_rank()
    test_pair_synergy()
    test_bot_lane_matchups()
    print("🏆 [SUCCESS] Suite 9 (수집 매치 기반 챔피언 티어표 검증) 100% ALL PASS!")



if __name__ == "__main__":
    run_all_champion_stats_tests()
