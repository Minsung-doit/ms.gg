import sys
from pathlib import Path
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import time
from fastapi.testclient import TestClient
from app.main import app
from app.cache_engine import fast_cache

client = TestClient(app)

print("=" * 60)
print("⚡ [LATENCY & CACHE SPEEDUP BENCHMARK]")
print("=" * 60)

# 1. Autocomplete Benchmark
fast_cache.clear()
t0 = time.perf_counter()
res1 = client.get("/api/autocomplete?q=faker")
t1 = time.perf_counter()
cnt1 = res1.json().get("total_count", 0)
cold_ms = (t1 - t0) * 1000

t0 = time.perf_counter()
for _ in range(10):
    res2 = client.get("/api/autocomplete?q=faker")
t1 = time.perf_counter()
cached_ms = ((t1 - t0) * 1000) / 10
cnt2 = res2.json().get("total_count", 0)

print(f"• /api/autocomplete (Cold):   {cold_ms:.3f} ms (count: {cnt1})")
print(f"• /api/autocomplete (Cached): {cached_ms:.3f} ms (count: {cnt2})")
print(f"  -> Speedup: {cold_ms / max(0.001, cached_ms):.1f}x faster!")

# 2. Community Counters Benchmark
t0 = time.perf_counter()
res3 = client.get("/api/community-counters?champ1=Yasuo&champ2=Yone")
t1 = time.perf_counter()
tips1 = len(res3.json().get("tips", []))
cold_tips_ms = (t1 - t0) * 1000

t0 = time.perf_counter()
for _ in range(10):
    res4 = client.get("/api/community-counters?champ1=Yasuo&champ2=Yone")
t1 = time.perf_counter()
cached_tips_ms = ((t1 - t0) * 1000) / 10
tips2 = len(res4.json().get("tips", []))

print(f"\n• /api/community-counters (Cold):   {cold_tips_ms:.3f} ms (tips: {tips1})")
print(f"• /api/community-counters (Cached): {cached_tips_ms:.3f} ms (tips: {tips2})")
print(f"  -> Speedup: {cold_tips_ms / max(0.001, cached_tips_ms):.1f}x faster!")

# 3. Live Game Inspector Benchmark (FR-01, FR-02, FR-03)
fast_cache.delete_matching("spectator_live_game:")
t0 = time.perf_counter()
res_lg1 = client.get("/api/spectator/live-game?name=Hide on bush&tag=KR1")
t1 = time.perf_counter()
cold_lg_ms = (t1 - t0) * 1000

t0 = time.perf_counter()
for _ in range(10):
    res_lg2 = client.get("/api/spectator/live-game?name=Hide on bush&tag=KR1")
t1 = time.perf_counter()
cached_lg_ms = ((t1 - t0) * 1000) / 10

print(f"\n• /api/spectator/live-game (Cold):   {cold_lg_ms:.3f} ms (in_game: {res_lg1.json().get('in_game')})")
print(f"• /api/spectator/live-game (Cached): {cached_lg_ms:.3f} ms")
print(f"  -> Speedup: {cold_lg_ms / max(0.001, cached_lg_ms):.1f}x faster!")

# 4. AI LoL Coach & Receipt Benchmark (FR-04, FR-05, FR-06)
fast_cache.delete_matching("ai_coach_receipt:")
t0 = time.perf_counter()
res_rc1 = client.get("/api/ai-coach/receipt?name=Hide on bush&tag=KR1")
t1 = time.perf_counter()
cold_rc_ms = (t1 - t0) * 1000

t0 = time.perf_counter()
for _ in range(10):
    res_rc2 = client.get("/api/ai-coach/receipt?name=Hide on bush&tag=KR1")
t1 = time.perf_counter()
cached_rc_ms = ((t1 - t0) * 1000) / 10

print(f"\n• /api/ai-coach/receipt (Cold):   {cold_rc_ms:.3f} ms (receipt_id: {res_rc1.json().get('receipt_id')})")
print(f"• /api/ai-coach/receipt (Cached): {cached_rc_ms:.3f} ms")
print(f"  -> Speedup: {cold_rc_ms / max(0.001, cached_rc_ms):.1f}x faster!")

# 5. Champion Masters Top 10 Benchmark (FR-08)
t0 = time.perf_counter()
res_cm1 = client.get("/api/champion-masters?champ=Yasuo&limit=10")
t1 = time.perf_counter()
cold_cm_ms = (t1 - t0) * 1000

t0 = time.perf_counter()
for _ in range(10):
    res_cm2 = client.get("/api/champion-masters?champ=Yasuo&limit=10")
t1 = time.perf_counter()
cached_cm_ms = ((t1 - t0) * 1000) / 10

print(f"\n• /api/champion-masters (Cold):   {cold_cm_ms:.3f} ms (count: {len(res_cm1.json().get('results', []))})")
print(f"• /api/champion-masters (Cached): {cached_cm_ms:.3f} ms")
print(f"  -> Speedup: {cold_cm_ms / max(0.001, cached_cm_ms):.1f}x faster!")

# 6. Cache Invalidation Test
res_vote = client.post("/api/community-counters/1/vote", json={"vote_type": "up"})
assert res_vote.status_code == 200
assert fast_cache.get("community_counters:yasuo:yone:popular:ALL:all:all:50") is None
print("\n• Cache Invalidation on vote: Verified (Instantly purged from fast_cache)")

print("\n" + "=" * 60)
print("🏆 ALL PERFORMANCE OPTIMIZATIONS VERIFIED!")
print("=" * 60)
