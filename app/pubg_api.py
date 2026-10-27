"""배틀그라운드 공식 API 연결부 (app/pubg_api.py)

PUBG_API_KEY 가 있으면 닉네임으로 계정과 이번 시즌 경쟁전 기록을 가져온다. 키가 없으면 configured()=False
→ 서버는 503 으로 '키 필요'를 알리고, 구인 게시판은 지금처럼 전적 없이 동작한다.
- 키 발급: https://developer.pubg.com (무료 키는 분당 10회)
- 분당 호출은 PUBG_RPM(기본 8)으로 자체 제한, 결과는 10분, 시즌 목록은 하루 캐시
"""
import os
import time
from typing import Any, Dict, Optional

import httpx

from app.cache_engine import fast_cache
from app.rate_limit import SlidingWindowLimiter

API = "https://api.pubg.com"
PLATFORMS = ("kakao", "steam")
_limiter = SlidingWindowLimiter(max_events=max(1, int(os.getenv("PUBG_RPM", "8") or 8)), window_sec=60)


class PubgError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _key() -> str:
    return os.getenv("PUBG_API_KEY", "").strip()


def configured() -> bool:
    return bool(_key())


async def _get(client: httpx.AsyncClient, platform: str, path: str, params: Optional[dict] = None) -> Dict[str, Any]:
    if not _limiter.hit("pubg"):
        raise PubgError(429, "배그 전적 조회가 잠시 많습니다. 1분 뒤 다시 시도해 주세요.")
    r = await client.get(f"{API}/shards/{platform}{path}", params=params, headers={
        "Authorization": f"Bearer {_key()}", "Accept": "application/vnd.api+json"})
    if r.status_code == 404:
        raise PubgError(404, "배그 계정을 찾을 수 없습니다.")
    if r.status_code == 429:
        raise PubgError(429, "배그 API 호출 한도에 걸렸습니다. 잠시 후 다시 시도해 주세요.")
    if r.status_code == 401:
        raise PubgError(503, "배그 API 키가 올바르지 않습니다.")
    if r.status_code != 200:
        raise PubgError(502, "배그 API 응답 오류")
    return r.json()


async def _current_season(client: httpx.AsyncClient, platform: str) -> Optional[str]:
    ck = f"pubg:season:{platform}"
    cached = fast_cache.get(ck)
    if cached:
        return cached
    data = await _get(client, platform, "/seasons")
    sid = next((s.get("id") for s in data.get("data") or [] if (s.get("attributes") or {}).get("isCurrentSeason")), None)
    if sid:
        fast_cache.set(ck, sid, ttl=86400)
    return sid


def _ranked_summary(stats: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """경쟁전 스쿼드(없으면 아무 모드) 기록. 판수 0이면 None"""
    modes = ((stats.get("data") or {}).get("attributes") or {}).get("rankedGameModeStats") or {}
    for mode in ("squad-fpp", "squad", *modes.keys()):
        m = modes.get(mode)
        if m and m.get("roundsPlayed"):
            tier = m.get("currentTier") or {}
            return {
                "mode": mode,
                "tier": tier.get("tier"),
                "sub_tier": tier.get("subTier"),
                "rank_point": m.get("currentRankPoint"),
                "rounds": m.get("roundsPlayed"),
                "wins": m.get("wins"),
                "top10_ratio": m.get("top10Ratio"),
                "kda": m.get("kda"),
                "avg_damage": round(m["damageDealt"] / m["roundsPlayed"]) if m.get("damageDealt") is not None else None,
            }
    return None


async def lookup(name: str, platform: str = "kakao") -> Dict[str, Any]:
    if not configured():
        raise PubgError(503, "배그 전적 연동은 PUBG_API_KEY 설정 후 사용할 수 있습니다.")
    platform = platform if platform in PLATFORMS else "kakao"
    name = name.strip()
    ck = f"pubg:player:{platform}:{name.lower()}"
    cached = fast_cache.get(ck)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=8.0) as client:
        players = await _get(client, platform, "/players", {"filter[playerNames]": name})
        p = (players.get("data") or [None])[0]
        if not p:
            raise PubgError(404, "배그 계정을 찾을 수 없습니다.")
        account_id = p.get("id")
        season = await _current_season(client, platform)
        ranked = None
        if season:
            ranked = _ranked_summary(await _get(client, platform, f"/players/{account_id}/seasons/{season}/ranked"))
    out = {"name": (p.get("attributes") or {}).get("name") or name, "platform": platform,
           "account_id": account_id, "season": season, "ranked": ranked, "fetched_at": int(time.time())}
    fast_cache.set(ck, out, ttl=600)
    return out
