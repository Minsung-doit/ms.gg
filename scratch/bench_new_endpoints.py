import sys, time
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("=" * 60)
print("Benchmarking /api/spectator/live-game:")
t0 = time.perf_counter()
r1 = client.get("/api/spectator/live-game?name=Faker")
t1 = time.perf_counter()
print(f"Cold live-game: status={r1.status_code}, time={(t1-t0)*1000:.3f}ms")

t0 = time.perf_counter()
r2 = client.get("/api/spectator/live-game?name=Faker")
t1 = time.perf_counter()
print(f"FastCache Hit 1 live-game: status={r2.status_code}, time={(t1-t0)*1000:.3f}ms")

t0 = time.perf_counter()
r3 = client.get("/api/spectator/live-game?name=Faker")
t1 = time.perf_counter()
print(f"FastCache Hit 2 live-game: status={r3.status_code}, time={(t1-t0)*1000:.3f}ms")

print("=" * 60)
print("Benchmarking /api/ai-coach/receipt:")
t0 = time.perf_counter()
r1 = client.get("/api/ai-coach/receipt?name=Hide on bush")
t1 = time.perf_counter()
print(f"Cold receipt: status={r1.status_code}, time={(t1-t0)*1000:.3f}ms")

t0 = time.perf_counter()
r2 = client.get("/api/ai-coach/receipt?name=Hide on bush")
t1 = time.perf_counter()
print(f"FastCache Hit 1 receipt: status={r2.status_code}, time={(t1-t0)*1000:.3f}ms")

t0 = time.perf_counter()
r3 = client.get("/api/ai-coach/receipt?name=Hide on bush")
t1 = time.perf_counter()
print(f"FastCache Hit 2 receipt: status={r3.status_code}, time={(t1-t0)*1000:.3f}ms")
print("=" * 60)
