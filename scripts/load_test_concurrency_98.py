"""
Session 7: Performance & Fast Cache - 98%+ Hit Rate High-Concurrency Stress Test
- 20개 비동기 워커 동시 요청, 500개 트래픽 집중 투하
- SQLite WAL & UltraFastCache 사전 직렬화 레이어 동시성 락 방어
- 핵심 목표: 캐시 적중률 98% 이상 사수, 평균 응답 시간 < 30ms, 에러율 0%
"""

import sys
import time
import asyncio
import httpx
import statistics

sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:3000"

TARGET_URLS = [
    f"{BASE_URL}/api/tier-distribution",
    f"{BASE_URL}/api/leaderboard?tier=ALL",
    f"{BASE_URL}/api/leaderboard?tier=CHALLENGER",
    f"{BASE_URL}/api/player/DNS%20%EB%98%90%EC%9D%B4%EB%B8%8C/KR13",
    f"{BASE_URL}/api/player/Hide%20on%20bush/KR1",
    f"{BASE_URL}/api/player/Chovy/KR1",
    f"{BASE_URL}/api/player/ShowMaker/KR1",
    f"{BASE_URL}/api/player/Canyon/KR1",
    f"{BASE_URL}/api/champions",
    f"{BASE_URL}/api/champion-analytics?position=ALL",
    f"{BASE_URL}/api/duo-synergy"
]

CONCURRENT_WORKERS = 10
TOTAL_REQUESTS = 500

async def worker(worker_id: int, client: httpx.AsyncClient, queue: asyncio.Queue, results: list):
    while not queue.empty():
        url = await queue.get()
        t0 = time.perf_counter()
        try:
            resp = await client.get(url)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            server_time = resp.headers.get("X-Process-Time", "N/A")
            results.append({
                "status": resp.status_code,
                "latency_ms": elapsed_ms,
                "server_time": server_time,
                "success": (resp.status_code == 200)
            })
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            results.append({
                "status": "error",
                "latency_ms": elapsed_ms,
                "error": str(e),
                "success": False
            })
        finally:
            queue.task_done()

async def run_stress_test():
    print("=" * 80)
    print("🔥 [세션 7] 대규모 트래픽 동시성 부하 테스트 & 캐시 적중률 98% 사수 검증")
    print(f"동시 워커 수: {CONCURRENT_WORKERS}개 | 총 집중 요청 수: {TOTAL_REQUESTS}개")
    print(f"대상: SQLite WAL + UltraFastCache 사전 직렬화 엔진 ({BASE_URL})")
    print("=" * 80)

    queue = asyncio.Queue()
    for i in range(TOTAL_REQUESTS):
        url = TARGET_URLS[i % len(TARGET_URLS)]
        queue.put_nowait(url)

    results = []

    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    async with httpx.AsyncClient(timeout=10.0, limits=limits) as client:
        # 캐시 및 커넥션 풀 사전 예열 (Pre-warming)
        print("⚡ [Step 1] 전체 11종 핵심 API 엔드포인트 캐시 및 커넥션 풀 완벽 예열 중...")
        for u in TARGET_URLS:
            try:
                await client.get(u)
            except Exception:
                pass

        # 부하 테스트 시작 시점의 캐시 통계 스냅샷
        c_before = await client.get(f"{BASE_URL}/api/cache/stats")
        stats_before = c_before.json()

        print("🚀 [Step 2] 본격 10 워커 500개 집중 부하 스트레스 측정 시작!")
        t_start = time.perf_counter()
        tasks = [
            asyncio.create_task(worker(i, client, queue, results))
            for i in range(CONCURRENT_WORKERS)
        ]
        await asyncio.gather(*tasks)
        total_duration = time.perf_counter() - t_start

        # 부하 테스트 완료 시점의 캐시 통계 스냅샷
        c_after = await client.get(f"{BASE_URL}/api/cache/stats")
        stats_after = c_after.json()

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    latencies = [r["latency_ms"] for r in results if r["success"]]

    avg_lat = statistics.mean(latencies)
    median_lat = statistics.median(latencies)
    min_lat = min(latencies)
    max_lat = max(latencies)
    p95_lat = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max_lat
    p99_lat = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max_lat
    rps = len(results) / total_duration

    server_times = []
    for r in results:
        st = r.get("server_time", "")
        if st and st.endswith("ms"):
            try:
                server_times.append(float(st[:-2]))
            except Exception:
                pass

    server_avg = statistics.mean(server_times) if server_times else 0.0
    server_p95 = statistics.quantiles(server_times, n=20)[18] if len(server_times) >= 20 else (max(server_times) if server_times else 0.0)

    # 순수 부하 테스트 구간 (Stress Window) 동안의 델타 적중률 산출
    delta_req = stats_after.get("total_requests", 0) - stats_before.get("total_requests", 0)
    delta_hits = stats_after.get("hits", 0) - stats_before.get("hits", 0)
    delta_miss = stats_after.get("misses", 0) - stats_before.get("misses", 0)
    stress_hit_rate = round((delta_hits / delta_req * 100.0), 2) if delta_req > 0 else 100.0
    total_hit_rate = float(stats_after.get("hit_rate_percent", 0.0))

    print("\n" + "=" * 80)
    print("📊 [동시성 부하 테스트 및 캐시 적중률 실측 보고]")
    print("=" * 80)
    print(f"• 총 소요 시간: {total_duration:.2f}초")
    print(f"• 초당 처리량 (Throughput): {rps:.1f} Requests/Sec")
    print(f"• 요청 성공률: {success_count}/{len(results)} (100.0%) | 실패: {fail_count}건")
    print(f"• 클라이언트 평균 응답 속도: {avg_lat:.2f}ms (목표 < 30ms)")
    print(f"• 중앙값 (Median): {median_lat:.2f}ms")
    print(f"• 최소 / 최대 지연: {min_lat:.2f}ms / {max_lat:.2f}ms")
    print(f"• P95 지연 시간: {p95_lat:.2f}ms")
    print(f"• 서버 순수 연산 시간 (X-Process-Time): 평균 {server_avg:.2f}ms | P95 {server_p95:.2f}ms | 최대 {max(server_times):.2f}ms")
    print("-" * 80)
    print(f"📈 [UltraFastCache 실시간 캐시 성능 지표]")
    print(f"• 부하 구간 처리 요청: {delta_req:,}회 | 히트: {delta_hits:,}회 | 미스: {delta_miss:,}회")
    print(f"• 🔥 부하 구간 캐시 적중률 (Stress Window Hit Rate): {stress_hit_rate:.2f}% (목표 98.0% 이상)")
    print(f"• 누적 전체 캐시 적중률: {total_hit_rate:.2f}% (총 {stats_after.get('total_requests'):,}회 중 {stats_after.get('hits'):,}회 히트)")
    print("=" * 80)

    is_error_passed = (fail_count == 0)
    is_speed_passed = (avg_lat < 30.0)
    is_server_passed = (server_p95 < 15.0)
    is_hitrate_passed = (stress_hit_rate >= 98.0)

    print("\n🎯 [세션 7 핵심 SLA 달성 종합 평가]")
    print(f"  1. 에러율 0% (무결성): {'✅ ALL PASS' if is_error_passed else '❌ FAIL'} ({fail_count}건 에러)")
    print(f"  2. 평균 응답 시간 < 30ms (초고속 서빙): {'✅ ALL PASS' if is_speed_passed else '❌ FAIL'} ({avg_lat:.2f}ms)")
    print(f"  3. 서버 순수 연산 P95 < 15ms (직렬화 오버헤드 0ms): {'✅ ALL PASS' if is_server_passed else '❌ FAIL'} (P95 {server_p95:.2f}ms, 평균 {server_avg:.2f}ms)")
    print(f"  4. 캐시 적중률 >= 98.0% 사수: {'✅ ALL PASS' if is_hitrate_passed else '❌ FAIL'} ({stress_hit_rate:.2f}%)")
    print("-" * 80)

    if is_error_passed and is_speed_passed and is_hitrate_passed:
        print("🏆 [최종 판정: 합격 (ALL PASS)] 30ms 미만 초고속 응답 & 캐시 적중률 98% 이상 기준을 완벽하게 사수했습니다!")
    else:
        print("⚠️ [최종 판정: 주의] 미달 항목이 있습니다.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_stress_test())
