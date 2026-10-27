import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_new_endpoints():
    print("=" * 80)
    print("Testing /api/spectator/live-game & /api/ai-coach/receipt")
    print("=" * 80)

    # 1. Test /api/spectator/live-game
    res1 = client.get("/api/spectator/live-game?name=Hide on bush&tag=KR1")
    assert res1.status_code == 200, f"live-game status: {res1.status_code}"
    d1 = res1.json()
    print("1. /api/spectator/live-game keys:", list(d1.keys()))
    assert d1.get("in_game") is True, f"in_game should be True, got {d1.get('in_game')}"
    assert "analysis_bundle" in d1, "analysis_bundle missing"
    ab = d1["analysis_bundle"]
    assert "win_prediction" in ab, "win_prediction missing"
    assert "comp_briefing" in ab, "comp_briefing missing"
    assert "lane_matchups" in ab, "lane_matchups missing"
    assert "vip_targets" in ab, "vip_targets missing"
    print("  analysis_bundle keys:", list(ab.keys()))
    print("  win_prediction:", ab["win_prediction"])
    print("  vip_targets count:", len(ab["vip_targets"]))
    print("  lane_matchups count:", len(ab["lane_matchups"]))
    print("  first lane matchup dominance_label:", ab["lane_matchups"][0].get("dominance_label"))
    assert ab["lane_matchups"][0].get("dominance_label") in ["상성 우세", "백중세", "상성 열세"]

    # 2. Test /api/ai-coach/receipt
    res2 = client.get("/api/ai-coach/receipt?name=Hide on bush&tag=KR1")
    assert res2.status_code == 200, f"receipt status: {res2.status_code}"
    d2 = res2.json()
    print("\n2. /api/ai-coach/receipt keys:", list(d2.keys()))
    assert "receipt_id" in d2, "receipt_id missing"
    assert "radar_scores" in d2, "radar_scores missing"
    assert "tier_benchmarks" in d2, "tier_benchmarks missing"
    assert "recommended_champions" in d2, "recommended_champions missing"
    assert "items" in d2, "items missing"
    assert len(d2["recommended_champions"]) >= 2, "At least 2 recommended champions required"
    print("  receipt_id:", d2["receipt_id"])
    print("  receipt_type:", d2["receipt_type"])
    print("  radar_scores:", d2["radar_scores"])
    print("  tier_benchmarks:", d2["tier_benchmarks"])
    print("  recommended_champions:", d2["recommended_champions"])
    print("\n[SUCCESS] Both live-game and receipt APIs passed 100%!")

if __name__ == "__main__":
    test_new_endpoints()
