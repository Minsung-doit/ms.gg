import threading
import time
from collections import deque
from typing import Dict, Deque

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    """Per-key sliding window limiter for public write endpoints (in-memory, per process)."""

    def __init__(self, max_events: int, window_sec: int, max_keys: int = 50000):
        self.max_events = max_events
        self.window_sec = window_sec
        self.max_keys = max_keys
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Record an event; return False if the key is over its limit."""
        now = time.time()
        with self._lock:
            events = self._events.get(key)
            if events is None:
                if len(self._events) >= self.max_keys:
                    self._events.clear()
                events = self._events[key] = deque()
            while events and now - events[0] >= self.window_sec:
                events.popleft()
            if len(events) >= self.max_events:
                return False
            events.append(now)
            return True


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce(limiter: SlidingWindowLimiter, request: Request, scope: str = "") -> None:
    if not limiter.hit(f"{scope}:{client_ip(request)}"):
        raise HTTPException(status_code=429, detail="요청이 너무 많습니다. 잠시 후 다시 시도해주세요.")


duo_post_limiter = SlidingWindowLimiter(max_events=3, window_sec=600)
community_tip_limiter = SlidingWindowLimiter(max_events=5, window_sec=600)
community_vote_limiter = SlidingWindowLimiter(max_events=30, window_sec=60)
# 공개 공유 버튼이 운영 디스코드 채널로 바로 전송되므로 채널 도배 방지
discord_share_limiter = SlidingWindowLimiter(max_events=5, window_sec=600)
# Riot API 할당량 보호: 래더 동기화는 1회에 50건 이상 호출하므로 서버 전체 기준으로 제한
leaderboard_sync_limiter = SlidingWindowLimiter(max_events=1, window_sec=300)
player_sync_limiter = SlidingWindowLimiter(max_events=10, window_sec=60)
# 듀오 글 디스코드 입장 클릭 통계 (공개 쓰기) 부풀리기 방지
discord_join_limiter = SlidingWindowLimiter(max_events=30, window_sec=60)
# AI 코치: 전적 조회(라이엇 호출)와 유료 AI 요약이 붙으므로 IP당 10분 6회, AI 요약은 서버 전체 하루 300회
ai_coach_limiter = SlidingWindowLimiter(max_events=6, window_sec=600)
ai_summary_daily_limiter = SlidingWindowLimiter(max_events=300, window_sec=86400)
# 서버 랭킹 계정 연결: 라이엇 조회가 붙으므로 IP당 10분 5회
member_link_limiter = SlidingWindowLimiter(max_events=5, window_sec=600)
