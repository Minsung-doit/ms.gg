"""
KR 솔로랭크 챌린저·그랜드마스터·마스터 전체 명단 (puuid → 티어).

수집 매치에는 티어가 없으므로, 참가자를 이 명단과 맞춰 게임별 티어를 정한다.
라이엇 호출은 하루 3회(리그 3개)뿐이다.
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional

from app.database import get_connection

logger = logging.getLogger(__name__)

APEX_TIERS = ("CHALLENGER", "GRANDMASTER", "MASTER")
REFRESH_SECONDS = 86400

_MEMO: Dict[str, object] = {"at": 0.0, "map": {}}


def _ensure_table() -> None:
    conn = get_connection()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS apex_tiers (puuid TEXT PRIMARY KEY, tier TEXT NOT NULL, updated_at INTEGER NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


def load_apex_map() -> Dict[str, str]:
    """puuid → 티어. 10분 동안 메모리에 둔다."""
    now = time.time()
    if now - float(_MEMO["at"]) < 600:
        return _MEMO["map"]  # type: ignore[return-value]
    _ensure_table()
    conn = get_connection()
    try:
        rows = conn.execute("SELECT puuid, tier FROM apex_tiers").fetchall()
    finally:
        conn.close()
    mp = {r[0]: r[1] for r in rows}
    _MEMO.update(at=now, map=mp)
    return mp


def game_tier(puuids: List[Optional[str]], apex: Dict[str, str]) -> str:
    """참가자 중 명단에 있는 사람이 가장 많은 티어. 아무도 없으면 'OTHER'(마스터 미만·미확인)."""
    counts = {t: 0 for t in APEX_TIERS}
    for pu in puuids:
        t = apex.get(pu or "")
        if t in counts:
            counts[t] += 1
    best = max(APEX_TIERS, key=lambda t: (counts[t], -APEX_TIERS.index(t)))
    return best if counts[best] else "OTHER"


def _last_updated() -> int:
    _ensure_table()
    conn = get_connection()
    try:
        row = conn.execute("SELECT MAX(updated_at) FROM apex_tiers").fetchone()
    finally:
        conn.close()
    return int(row[0] or 0)


async def refresh_apex_tiers() -> int:
    from app.riot_client import riot_client

    rows = []
    now = int(time.time())
    for tier in APEX_TIERS:
        league = await riot_client.get_apex_league(tier)
        rows += [(e["puuid"], tier, now) for e in league.get("entries", []) if e.get("puuid")]
    if not rows:
        return 0
    _ensure_table()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM apex_tiers")
        conn.executemany("INSERT OR REPLACE INTO apex_tiers (puuid, tier, updated_at) VALUES (?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    _MEMO["at"] = 0.0
    return len(rows)


async def refresh_loop() -> None:
    """서버를 자주 재시작해도 하루 1번만 받는다."""
    while True:
        wait = REFRESH_SECONDS - (time.time() - _last_updated())
        if wait > 0:
            await asyncio.sleep(min(wait, REFRESH_SECONDS))
            continue
        try:
            n = await refresh_apex_tiers()
            logger.info("Apex tiers refreshed: %d players", n)
        except Exception as e:
            logger.warning("Apex tier refresh failed: %s", e)
            await asyncio.sleep(3600)
