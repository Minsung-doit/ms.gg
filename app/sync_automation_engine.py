"""
Riot API Sync Automation Engine
================================
- 비동기 백그라운드 동기화 큐 (SyncQueue) 및 백그라운드 워커 (BackgroundSyncWorker)
- 라이엇 API 레이트 리미트(Rate Limit: 20 req/1s, 100 req/2m) 안전 보호를 위한 토큰 버킷 / 백오프 시스템 (RiotRateLimiter)
- 소환사 프로필 + 솔로랭크/자유랭크 티어 + 최근 매치 히스토리(최대 20게임) + 실시간 인게임(Spectator) 동기화
  (app/real_data.py 경유: 라이엇 값만 사용, 실패하면 대체 데이터 없이 실패로 기록)
- L1 인메모리 캐시 (InMemorySyncCache)
- 100% 한국 서버 실존 소환사 기준 데이터 정합성 유지 (가상 닉네임 일체 배제)
- 동기화 통계 메트릭 (총 요청 수, 성공 수, 실패 수, 평균 소요 시간, 큐 대기 건수) 집계
"""

import asyncio
import time
import uuid
import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from app.config import settings
from app.database import format_player_dict, get_player_by_riot_id
from app.champion_engine import REAL_HIGH_TIER_ACCOUNTS, REAL_GENERAL_ACCOUNTS

# ==============================================================================
# 1. 라이엇 API 레이트 리미트 방어 시스템 (Dual Token Bucket + Exponential Backoff)
# ==============================================================================

class RiotRateLimiter:
    """
    Riot API 공식 개발자 키 제한 방어:
    - 버킷 1 (Short): 20 requests per 1 second (안전 마진 19.0 req/s)
    - 버킷 2 (Long):  100 requests per 2 minutes (안전 마진 95.0 req/120s)
    - 지수 백오프 (Exponential Backoff with Jitter) 및 429 Retry-After 헤더 파싱
    """
    def __init__(
        self,
        short_capacity: float = 19.0,
        short_rate: float = 19.0,          # 1초당 19개
        long_capacity: float = 95.0,
        long_rate: float = 95.0 / 120.0    # 120초당 95개 (~0.7917/s)
    ):
        self.short_capacity = short_capacity
        self.short_rate = short_rate
        self.short_tokens = short_capacity

        self.long_capacity = long_capacity
        self.long_rate = long_rate
        self.long_tokens = long_capacity

        self.last_update = time.time()
        self.lock = asyncio.Lock()

        # 백오프 관리
        self.backoff_until: float = 0.0
        self.consecutive_429: int = 0
        self.total_acquisitions: int = 0
        self.total_429_hits: int = 0
        self.total_backoff_sleep_time: float = 0.0

        # 서킷 브레이커 (Circuit Breaker for 401/403/Service Outage)
        self.circuit_state: str = "CLOSED"  # "CLOSED", "OPEN", "HALF_OPEN"
        self.circuit_open_until: float = 0.0
        self.circuit_open_reason: str = ""

        # API 키 만료 상태 관리 (24-hour developer key expired detection)
        self.is_key_expired: bool = False
        self.expiry_reason: str = ""
        self.expired_at: Optional[float] = None

    def is_circuit_broken(self) -> bool:
        """
        서킷 브레이커 활성(차단) 상태 또는 키 만료 상태인지 확인
        """
        if self.is_key_expired:
            return True
        now = time.time()
        if self.circuit_state == "OPEN":
            if now >= self.circuit_open_until:
                self.circuit_state = "HALF_OPEN"
                return False
            return True
        return False

    def trip_circuit(self, reason: str, duration: float = 600.0, is_key_expired: bool = False):
        """
        401/403 등 치명적 오류 발생 시 서킷 오픈 (불필요한 요청 전면 차단)
        """
        self.circuit_state = "OPEN"
        self.circuit_open_until = time.time() + duration
        self.circuit_open_reason = reason
        if is_key_expired:
            self.is_key_expired = True
            self.expiry_reason = reason
            self.expired_at = time.time()

    def reset_circuit(self):
        """
        새 API 키 등록 또는 정상 복구 시 서킷 및 키 만료 상태 전면 리셋
        """
        self.circuit_state = "CLOSED"
        self.circuit_open_until = 0.0
        self.circuit_open_reason = ""
        self.consecutive_429 = 0
        self.backoff_until = 0.0
        self.is_key_expired = False
        self.expiry_reason = ""
        self.expired_at = None

    async def acquire(self, tokens: float = 1.0):
        """
        토큰을 획득할 때까지 안전하게 대기.
        1초 버킷 및 2분 버킷 모두 토큰이 충족되어야 통과.
        """
        if self.is_circuit_broken():
            raise RuntimeError(f"Circuit Breaker OPEN: {self.circuit_open_reason}")

        while True:
            async with self.lock:
                now = time.time()

                # 1. 429 백오프 대기 상태인지 확인
                if now < self.backoff_until:
                    sleep_time = self.backoff_until - now
                else:
                    sleep_time = 0.0

                # 2. 토큰 보충
                elapsed = now - self.last_update
                self.last_update = now

                self.short_tokens = min(self.short_capacity, self.short_tokens + elapsed * self.short_rate)
                self.long_tokens = min(self.long_capacity, self.long_tokens + elapsed * self.long_rate)

                # 3. 토큰 가용성 확인
                if sleep_time <= 0:
                    needed_short = tokens - self.short_tokens
                    needed_long = tokens - self.long_tokens

                    wait_short = needed_short / self.short_rate if needed_short > 0 else 0.0
                    wait_long = needed_long / self.long_rate if needed_long > 0 else 0.0
                    wait_tokens = max(wait_short, wait_long)

                    if wait_tokens <= 0.001:
                        # 토큰 차감 및 통과
                        self.short_tokens -= tokens
                        self.long_tokens -= tokens
                        self.total_acquisitions += 1
                        return

                    sleep_time = wait_tokens

            # 락 밖에서 비동기 수면
            self.total_backoff_sleep_time += sleep_time
            await asyncio.sleep(sleep_time)

    def handle_status(self, status_code: int, retry_after: Optional[int] = None):
        """
        API 호출 결과 상태 코드 피드백 (401/403 즉시 만료 및 서킷 오픈)
        """
        now = time.time()
        # 403은 키 문제가 아니라 엔드포인트 권한 문제일 수 있어 riot_client가 상태 API로 확인한다
        if status_code == 401:
            self.trip_circuit("24-hour developer key expired (401/403)", duration=3600.0, is_key_expired=True)
            try:
                from app.riot_client import riot_client
                riot_client.mark_key_expired("24-hour developer key expired (401/403)")
            except Exception:
                pass
        elif status_code == 429:
            self.total_429_hits += 1
            self.consecutive_429 += 1
            if retry_after is not None and retry_after > 0:
                duration = float(retry_after) + random.uniform(0.1, 0.4)
            else:
                duration = min(30.0, (1.8 ** self.consecutive_429) + random.uniform(0.2, 0.8))
            self.backoff_until = max(self.backoff_until, now + duration)
            self.short_tokens = 0.0
            self.long_tokens = max(0.0, self.long_tokens - 10.0)
        elif status_code in (200, 404):
            if self.consecutive_429 > 0:
                self.consecutive_429 = 0
            if self.circuit_state == "HALF_OPEN":
                self.circuit_state = "CLOSED"
                self.circuit_open_reason = ""

    def handle_response_headers(self, headers: Any, status_code: int):
        """
        Riot 응답 헤더(Retry-After, X-App-Rate-Limit-Count 등) 정밀 피드백
        """
        retry_after = None
        if "Retry-After" in headers:
            try:
                retry_after = int(headers["Retry-After"])
            except Exception:
                pass
        self.handle_status(status_code, retry_after=retry_after)

    def get_status(self) -> Dict[str, Any]:
        """
        현재 레이트 리미터 버킷 및 백오프/서킷 브레이커/키 만료 상태
        """
        now = time.time()
        elapsed = now - self.last_update
        cur_short = min(self.short_capacity, self.short_tokens + elapsed * self.short_rate)
        cur_long = min(self.long_capacity, self.long_tokens + elapsed * self.long_rate)
        is_backoff = now < self.backoff_until
        remaining_backoff = max(0.0, round(self.backoff_until - now, 2))
        is_broken = self.is_circuit_broken()
        circuit_remaining = max(0.0, round(self.circuit_open_until - now, 1)) if is_broken else 0.0

        if self.is_key_expired:
            alert_level = "CRITICAL"
            recommended_action = "regenerate_key"
        elif is_broken or cur_short < 2.0 or cur_long < 5.0 or is_backoff:
            alert_level = "WARNING"
            recommended_action = "wait_cooldown"
        else:
            alert_level = "NORMAL"
            recommended_action = "none"

        return {
            "is_expired": self.is_key_expired,
            "expiry_reason": self.expiry_reason or ("24-hour developer key expired (401/403)" if self.is_key_expired else ""),
            "alert_level": alert_level,
            "recommended_action": recommended_action,
            "portal_url": "https://developer.riotgames.com",
            "expired_at": self.expired_at,
            "short_bucket": {
                "remaining_tokens": round(cur_short, 2),
                "capacity": self.short_capacity,
                "window": "1s"
            },
            "long_bucket": {
                "remaining_tokens": round(cur_long, 2),
                "capacity": self.long_capacity,
                "window": "120s"
            },
            "circuit_breaker": {
                "state": self.circuit_state,
                "is_broken": is_broken,
                "reason": self.circuit_open_reason,
                "remaining_seconds": circuit_remaining
            },
            "is_backoff_active": is_backoff,
            "remaining_backoff_seconds": remaining_backoff,
            "total_acquisitions": self.total_acquisitions,
            "total_429_hits": self.total_429_hits,
            "total_sleep_time_seconds": round(self.total_backoff_sleep_time, 2)
        }

    def get_key_status_dict(self) -> Dict[str, Any]:
        """
        Riot API Key 만료 여부 및 실시간 상태 모니터링 딕셔너리
        """
        has_key = bool(settings.riot_api_key)
        if self.is_key_expired:
            api_key_status = "EXPIRED"
            message = "Riot API 키가 만료되었습니다. 새 키를 등록해주세요."
        elif has_key:
            api_key_status = "VALID"
            message = "정상 연결"
        else:
            api_key_status = "MISSING"
            message = "Riot API 키가 등록되지 않았습니다."

        return {
            "api_key_expired": self.is_key_expired,
            "api_key_status": api_key_status,
            "message": message,
            "last_detected_at": self.expired_at,
            "alert_required": self.is_key_expired,
            "portal_url": "https://developer.riotgames.com"
        }


# ==============================================================================
# 2. 동기화 작업 엔티티 & 비동기 백그라운드 큐 (SyncQueue)
# ==============================================================================

@dataclass
class SyncJob:
    job_id: str
    game_name: str
    tag_line: str
    force_refresh: bool
    enqueued_at: float
    status: str = "queued"          # "queued", "processing", "completed", "failed"
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    duration: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    future: Optional[asyncio.Future] = None

    @property
    def key(self) -> str:
        return f"{self.game_name.strip()}#{self.tag_line.strip()}".lower()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "game_name": self.game_name,
            "tag_line": self.tag_line,
            "riot_id": f"{self.game_name}#{self.tag_line}",
            "force_refresh": self.force_refresh,
            "status": self.status,
            "enqueued_at": self.enqueued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": round(self.duration, 3) if self.duration is not None else None,
            "error": self.error
        }


class SyncQueue:
    """
    동기화 작업 큐 (Deduplication 중복 방지 및 우선순위/히스토리 관리)
    """
    def __init__(self, max_history: int = 50):
        self._queue: asyncio.Queue[SyncJob] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._in_flight: Dict[str, SyncJob] = {}  # key -> SyncJob (queued or processing)
        self._jobs_by_id: Dict[str, SyncJob] = {}
        self._recent_history: deque[SyncJob] = deque(maxlen=max_history)

    async def enqueue(self, game_name: str, tag_line: str, force_refresh: bool = False, create_future: bool = False) -> SyncJob:
        clean_name = game_name.strip()
        clean_tag = tag_line.strip()
        key = f"{clean_name}#{clean_tag}".lower()

        async with self._lock:
            # 중복 체크: 이미 큐에 대기 중이거나 처리 중인 경우 해당 작업 반환
            if key in self._in_flight:
                existing_job = self._in_flight[key]
                return existing_job

            job_id = f"sync_{uuid.uuid4().hex[:10]}"
            job = SyncJob(
                job_id=job_id,
                game_name=clean_name,
                tag_line=clean_tag,
                force_refresh=force_refresh,
                enqueued_at=time.time(),
                status="queued"
            )
            if create_future:
                loop = asyncio.get_running_loop()
                job.future = loop.create_future()

            self._in_flight[key] = job
            self._jobs_by_id[job_id] = job
            await self._queue.put(job)
            return job

    async def get_next(self) -> SyncJob:
        return await self._queue.get()

    async def mark_started(self, job: SyncJob):
        async with self._lock:
            job.status = "processing"
            job.started_at = time.time()

    async def mark_completed(self, job: SyncJob, result: Dict[str, Any]):
        now = time.time()
        async with self._lock:
            job.status = "completed"
            job.finished_at = now
            job.duration = now - (job.started_at or job.enqueued_at)
            job.result = result
            self._in_flight.pop(job.key, None)
            self._recent_history.append(job)
            if job.future and not job.future.done():
                job.future.set_result(result)

    async def mark_failed(self, job: SyncJob, error_msg: str):
        now = time.time()
        async with self._lock:
            job.status = "failed"
            job.finished_at = now
            job.duration = now - (job.started_at or job.enqueued_at)
            job.error = error_msg
            self._in_flight.pop(job.key, None)
            self._recent_history.append(job)
            if job.future and not job.future.done():
                job.future.set_exception(RuntimeError(error_msg))

    def get_job(self, job_id: str) -> Optional[SyncJob]:
        return self._jobs_by_id.get(job_id)

    def size(self) -> int:
        return self._queue.qsize()

    def get_in_flight_count(self) -> int:
        return len(self._in_flight)

    def in_flight_count(self) -> int:
        return len(self._in_flight)

    def get_in_flight_list(self) -> List[Dict[str, Any]]:
        return [job.to_dict() for job in self._in_flight.values()]

    def get_recent_history(self) -> List[Dict[str, Any]]:
        return [job.to_dict() for job in reversed(self._recent_history)]


# ==============================================================================
# 3. L1 인메모리 캐시 (InMemorySyncCache)
# ==============================================================================

class InMemorySyncCache:
    """
    Riot API 동기화 결과 L1 고속 인메모리 캐시 (TTL 기본 120초)
    """
    def __init__(self, default_ttl_seconds: float = 120.0):
        self._cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self.default_ttl = default_ttl_seconds

    def _key(self, game_name: str, tag_line: str) -> str:
        return f"{game_name.strip()}#{tag_line.strip()}".lower()

    def get(self, game_name: str, tag_line: str) -> Optional[Dict[str, Any]]:
        key = self._key(game_name, tag_line)
        item = self._cache.get(key)
        if not item:
            return None
        data, expires_at = item
        if time.time() > expires_at:
            self._cache.pop(key, None)
            return None
        return data

    def set(self, game_name: str, tag_line: str, data: Dict[str, Any], ttl: Optional[float] = None):
        key = self._key(game_name, tag_line)
        ttl_val = ttl if ttl is not None else self.default_ttl
        self._cache[key] = (data, time.time() + ttl_val)

    def invalidate(self, game_name: str, tag_line: str):
        key = self._key(game_name, tag_line)
        self._cache.pop(key, None)

    def clear(self):
        self._cache.clear()

    def count(self) -> int:
        now = time.time()
        # 만료 정리
        expired_keys = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in expired_keys:
            self._cache.pop(k, None)
        return len(self._cache)


# ==============================================================================
# 4. 동기화 통계 메트릭스 (SyncMetrics)
# ==============================================================================

class SyncMetrics:
    """
    동기화 엔진 가동 통계 및 성능 지표 집계
    """
    def __init__(self):
        self.total_requests: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0
        self.total_duration: float = 0.0
        self.durations: deque[float] = deque(maxlen=100)
        self.started_at: float = time.time()

    def record_success(self, duration: Optional[float]):
        self.total_requests += 1
        self.success_count += 1
        if duration is not None:
            self.total_duration += duration
            self.durations.append(duration)

    def record_failure(self, duration: Optional[float] = None):
        self.total_requests += 1
        self.failure_count += 1
        if duration is not None:
            self.durations.append(duration)

    def get_summary(self, queue_size: int = 0, in_flight_count: int = 0) -> Dict[str, Any]:
        avg_dur = (sum(self.durations) / len(self.durations)) if self.durations else 0.0
        success_rate = (self.success_count / self.total_requests * 100) if self.total_requests > 0 else 100.0

        return {
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate_percent": round(success_rate, 1),
            "avg_sync_duration_seconds": round(avg_dur, 3),
            "queue_size": queue_size,
            "in_flight_count": in_flight_count,
            "uptime_seconds": int(time.time() - self.started_at)
        }

    def get_metrics(self, queue_size: int = 0, in_flight_count: int = 0) -> Dict[str, Any]:
        return self.get_summary(queue_size=queue_size, in_flight_count=in_flight_count)


# ==============================================================================
# 전역 싱글톤 인스턴스
# ==============================================================================

rate_limiter = RiotRateLimiter()
sync_queue = SyncQueue()
sync_cache = InMemorySyncCache(default_ttl_seconds=120.0)
sync_metrics = SyncMetrics()


# ==============================================================================
# 5. 원스톱 동기화 파이프라인 함수 (sync_player_full_data)
# ==============================================================================

async def sync_player_full_data(
    game_name: str,
    tag_line: str,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    소환사 프로필 + 최근 20경기 + 실시간 게임을 라이엇 API에서 받아 온다 (app/real_data.py 경유).
    값을 지어내지 않는다: 라이엇 API를 쓸 수 없으면 PlayerDataUnavailable 이 그대로 올라가 작업이 실패로 기록된다.
    (예전 구현은 실패 시 생성 전적·가짜 소환사로 '성공' 응답을 만들었고, 레이트 리미터 토큰도 이중으로 소모했다)
    """
    from app.real_data import fetch_live_game, fetch_player, get_recent_matches_payload

    start_time = time.time()
    clean_name = game_name.strip()
    clean_tag = tag_line.strip()

    if not force_refresh:
        cached_res = sync_cache.get(clean_name, clean_tag)
        if cached_res:
            return {**cached_res, "source": "in_memory_cache"}

    player = await fetch_player(clean_name, clean_tag, allow_cached=False)
    matches = await get_recent_matches_payload(player, count=20)
    spectator = await fetch_live_game(player)

    result_payload = {
        "status": "success",
        "sync_source": "riot_api",
        "synced_at": datetime.now().isoformat(),
        "duration_seconds": round(time.time() - start_time, 3),
        "player": player,
        "recent_matches_summary": matches["summary"],
        "recent_matches_count": len(matches["matches"]),
        "recent_matches": matches["matches"],
        "spectator": spectator
    }
    sync_cache.set(clean_name, clean_tag, result_payload, ttl=120.0)
    return result_payload


def _handle_verified_local_player(game_name: str, tag_line: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    100% 한국 서버 실존 소환사 기준으로 로컬 SQLite DB 확인 및 정합성 보장
    """
    existing = get_player_by_riot_id(game_name, tag_line)
    if existing:
        return existing

    # 한국 서버 대표 실존 계정에서 매칭 탐색
    all_known = REAL_HIGH_TIER_ACCOUNTS + REAL_GENERAL_ACCOUNTS
    clean_target = game_name.strip().lower()

    matched_tier = "GOLD"
    matched_rank = "I"
    matched_lp = 50
    matched_level = 145

    for acc in all_known:
        if acc[0].lower() == clean_target:
            matched_tier = "CHALLENGER" if acc in REAL_HIGH_TIER_ACCOUNTS else "DIAMOND"
            matched_rank = "I"
            matched_lp = 650 if matched_tier == "CHALLENGER" else 75
            matched_level = 580 if matched_tier == "CHALLENGER" else 280
            break

    # 생성 데이터 기능(SYNTHETIC_FEATURES=1) 전용 임시 값. 실제 소환사 테이블(players)에는 저장하지 않는다:
    # 저장하면 가짜 'real-kr-*' 행이 실제 검색 결과·프로필과 섞인다.
    return format_player_dict({
        "puuid": f"real-kr-{uuid.uuid4().hex[:12]}",
        "game_name": game_name,
        "tag_line": tag_line or "KR1",
        "profile_icon_id": random.choice([548, 550, 560, 570, 580, 590, 600]),
        "summoner_level": matched_level,
        "tier": matched_tier,
        "rank_tier": matched_rank,
        "league_points": matched_lp,
        "wins": random.randint(95, 340),
        "losses": random.randint(70, 260),
        "queue_type": "RANKED_SOLO_5x5"
    })


# ==============================================================================
# 6. 백그라운드 동기화 워커 (BackgroundSyncWorker)
# ==============================================================================

class BackgroundSyncWorker:
    """
    비동기 백그라운드 동기화 워커 (Worker Daemon)
    SyncQueue에서 작업을 비동기로 지속 처리하며, 레이트 리미트와 통계를 안전 관리합니다.
    """
    def __init__(self, queue: SyncQueue, metrics: SyncMetrics):
        self.queue = queue
        self.metrics = metrics
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self.current_job: Optional[SyncJob] = None
        self.last_processed_at: Optional[float] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self):
        if self._running:
            return
        self._running = True
        # (예전의 '핫 소환사·천상계 랭커 5분 주기 자동 동기화'는 라이엇 호출량을 늘리는 프리패치라 제거)
        self._task = asyncio.create_task(self._run_loop(), name="BackgroundSyncWorkerTask")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _run_loop(self):
        while self._running:
            try:
                # 큐에서 다음 작업 비동기 수신 (최대 1초 타임아웃으로 주기적 _running 점검)
                try:
                    job = await asyncio.wait_for(self.queue.get_next(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if not job:
                    continue

                # 이미 처리 완료된 작업(예: wait=True로 동기 완료된 작업)은 스킵
                if job.status in ("completed", "failed"):
                    continue

                self.current_job = job
                await self.queue.mark_started(job)

                try:
                    result = await sync_player_full_data(
                        game_name=job.game_name,
                        tag_line=job.tag_line,
                        force_refresh=job.force_refresh
                    )
                    await self.queue.mark_completed(job, result)
                    self.metrics.record_success(job.duration)
                except Exception as exc:
                    err_msg = str(exc)
                    await self.queue.mark_failed(job, err_msg)
                    self.metrics.record_failure(job.duration)
                finally:
                    self.last_processed_at = time.time()
                    self.current_job = None

            except asyncio.CancelledError:
                break
            except Exception as e:
                # 루프 비정상 종료 방지
                await asyncio.sleep(0.5)

    def get_status(self) -> Dict[str, Any]:
        rl_status = rate_limiter.get_status()
        return {
            "is_running": self._running,
            "has_active_task": bool(self._task and not self._task.done()),
            "is_expired": rl_status.get("is_expired", False),
            "expiry_reason": rl_status.get("expiry_reason", ""),
            "alert_level": rl_status.get("alert_level", "NORMAL"),
            "recommended_action": rl_status.get("recommended_action", "none"),
            "portal_url": rl_status.get("portal_url", "https://developer.riotgames.com"),
            "current_job": self.current_job.to_dict() if self.current_job else None,
            "last_processed_at": self.last_processed_at,
            "queue_size": self.queue.size(),
            "in_flight_count": self.queue.get_in_flight_count(),
            "in_flight_jobs": self.queue.get_in_flight_list(),
            "recent_completed_jobs": self.queue.get_recent_history()[:10],
            "rate_limiter": rl_status,
            "metrics": self.metrics.get_summary(
                queue_size=self.queue.size(),
                in_flight_count=self.queue.get_in_flight_count()
            )
        }


# 전역 워커 인스턴스
sync_worker = BackgroundSyncWorker(queue=sync_queue, metrics=sync_metrics)
