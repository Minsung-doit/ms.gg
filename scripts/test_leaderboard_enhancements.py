import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from app.main import app

def test_leaderboard():
    client = TestClient(app)

    print("=== 소환사 랭킹 LP 스파크라인 & 모멘텀 고도화 테스트 ===")
    res = client.get("/api/leaderboard?tier=ALL")
    assert res.status_code == 200, f"Status code {res.status_code}"
    data = res.json()
    assert "results" in data, "Missing results"
    results = data["results"]
    assert len(results) >= 50, f"Expected >= 50 rankers, got {len(results)}"

    print(f"[PASS 1] 랭커 목록 {len(results)}명 로드 완료")

    for idx, p in enumerate(results[:10]):
        assert "lp_history_7d" in p, f"Missing lp_history_7d in ranker {idx}"
        assert len(p["lp_history_7d"]) == 7, f"lp_history_7d should have 7 elements, got {len(p['lp_history_7d'])}"
        assert "lp_delta_7d" in p, f"Missing lp_delta_7d in ranker {idx}"
        assert isinstance(p["lp_delta_7d"], int), f"lp_delta_7d should be int, got {type(p['lp_delta_7d'])}"
        assert "momentum" in p, f"Missing momentum in ranker {idx}"
        mom = p["momentum"]
        assert "recent_5" in mom and len(mom["recent_5"]) == 5, f"recent_5 invalid in ranker {idx}"
        assert "badge_text" in mom and mom["badge_text"], f"badge_text empty in ranker {idx}"
        assert "badge_class" in mom and mom["badge_class"], f"badge_class empty in ranker {idx}"
        assert "streak_score" in mom, f"streak_score missing in ranker {idx}"
        delta_str = f"{p['lp_delta_7d']:+d}" if p['lp_delta_7d'] != 0 else "0"
        print(f"  #{p['rank']:02d} {p['game_name']} ({p['league_points']} LP) | 7일 추이: {delta_str} LP | 기세: {mom['badge_text']} ({mom['badge_class']}) | 최근5G: {' '.join(mom['recent_5'])}")

    print("[PASS 2] 상위 랭커 10명 스파크라인 및 모멘텀 무결성 검증 통과")

    for tier in ["CHALLENGER", "GRANDMASTER", "MASTER"]:
        t_res = client.get(f"/api/leaderboard?tier={tier}")
        assert t_res.status_code == 200
        t_data = t_res.json()
        print(f"[PASS 3] 티어 탭 필터링 ({tier}): {len(t_data.get('results', []))}명 반환 정상")

    print("\n========================================================")
    print("🏆 [SUCCESS] 소환사 랭킹 7일 LP 스파크라인 & 모멘텀 100% ALL PASS!")
    print("========================================================")

if __name__ == "__main__":
    test_leaderboard()
