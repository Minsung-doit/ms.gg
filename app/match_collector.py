"""
매치 수집기 (app/match_collector.py)

고티어 솔로랭크(queue 420) 매치를 꾸준히 모아 압축 저장합니다.
- 자체 호출 한도: 120초당 40회
- 솔로랭크(queueId == 420)만 선별
- compact_match 로 필요한 필드만 압축 저장
- 시드 최대 5,000개 관리
"""
import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from app.config import settings
from app.database import get_connection, is_riot_puuid
from app.riot_client import RiotAPIError, riot_client

logger = logging.getLogger(__name__)

MAX_SEEDS = 5000
# 패치당 이만큼 모이면 통계 표본으로 충분하므로 수집 속도를 낮춘다 (저장 공간·통계 계산 시간 보호)
MAX_MATCHES_PER_PATCH = 20000
FULL_PATCH_PAUSE_SEC = 600
# 최신 2개 패치보다 오래된 매치는 통계에 쓰지 않으므로 지운다 (1시간에 한 번)
KEEP_VERSIONS = 2
PRUNE_INTERVAL_SEC = 3600
_last_prune_at: float = 0.0
_last_cycle_at: Optional[float] = None


class CollectorRateLimiter:
    """
    수집기 자체 호출 속도 제한기
    - 한도: 120초당 40회
    """

    def __init__(self, max_calls: int = 40, period: float = 120.0):
        self.max_calls = max_calls
        self.period = period
        self.calls: List[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.time()
                # 윈도우(120초)를 벗어난 과거 호출 기록 제거
                self.calls = [t for t in self.calls if now - t < self.period]
                if len(self.calls) < self.max_calls:
                    self.calls.append(now)
                    return
                # 가장 오래된 호출이 만료될 때까지 대기
                sleep_time = self.period - (now - self.calls[0]) + 0.05
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

    def reset(self) -> None:
        self.calls.clear()


collector_rate_limiter = CollectorRateLimiter(max_calls=40, period=120.0)


def init_collector_tables() -> None:
    """수집기용 SQLite 테이블 및 인덱스 초기화"""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS collected_matches (
                match_id TEXT PRIMARY KEY,
                game_version TEXT,
                game_end INTEGER,
                duration INTEGER,
                data TEXT,
                collected_at INTEGER
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_collected_matches_version ON collected_matches(game_version)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS collector_seeds (
                puuid TEXT PRIMARY KEY,
                source TEXT,
                last_crawled INTEGER DEFAULT 0,
                added_at INTEGER
            )
        """)
        # 소환사별 수집 게임 색인 (멀티서치 등에서 추가 호출 없이 최근 챔피언을 보여주기 위함)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS collected_participants (
                puuid TEXT NOT NULL,
                match_id TEXT NOT NULL,
                game_end INTEGER,
                champion_id INTEGER,
                position TEXT,
                win INTEGER,
                kills INTEGER,
                deaths INTEGER,
                assists INTEGER,
                PRIMARY KEY (puuid, match_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_collected_participants_puuid ON collected_participants(puuid, game_end DESC)"
        )
        conn.commit()
        _backfill_participants(conn)
    finally:
        conn.close()


_participants_backfilled = False


def _participant_rows(match_id: str, compacted: Dict[str, Any]) -> List[tuple]:
    return [
        (p["puuid"], match_id, compacted.get("game_end"), p.get("champion_id"), p.get("position"),
         1 if p.get("win") else 0, p.get("kills"), p.get("deaths"), p.get("assists"))
        for p in compacted.get("participants") or []
        if p.get("puuid")
    ]


def _backfill_participants(conn) -> None:
    """색인 테이블이 생기기 전에 저장된 매치를 한 번만 채운다."""
    global _participants_backfilled
    if _participants_backfilled:
        return
    _participants_backfilled = True
    if conn.execute("SELECT 1 FROM collected_participants LIMIT 1").fetchone():
        return
    missing = conn.execute("SELECT match_id, data FROM collected_matches").fetchall()
    rows: List[tuple] = []
    for match_id, data in missing:
        try:
            rows.extend(_participant_rows(match_id, json.loads(data)))
        except (TypeError, ValueError):
            continue
    if rows:
        conn.executemany("INSERT OR IGNORE INTO collected_participants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        logger.info("Collector: indexed %s participants from %s matches", len(rows), len(missing))


_POS_FROM_RIOT = {"TOP": "TOP", "JUNGLE": "JUG", "MIDDLE": "MID", "BOTTOM": "BOT", "UTILITY": "SUP"}


def player_cached_summary(puuid: str, limit: int = 20) -> Optional[Dict[str, Any]]:
    """누군가 이 소환사 전적을 열어 저장된 최근 랭크 게임(match_cache)에서 모스트·주 포지션 (라이엇 호출 없음).
    player_collected_summary 와 같은 모양으로 돌려준다. 없으면 None."""
    if not is_riot_puuid(puuid):
        return None
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT data FROM match_cache WHERE data LIKE ? ORDER BY game_end DESC LIMIT ?",
            (f"%{puuid}%", limit * 2),
        ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    from app.champion_stats import _resolve_champion
    from app.ddragon import champion_img
    champs: Dict[int, Dict[str, int]] = {}
    positions: Dict[str, int] = {}
    games = wins = 0
    for (raw,) in rows:
        try:
            info = json.loads(raw).get("info") or {}
        except Exception:
            continue
        if info.get("queueId") not in (420, 440):
            continue
        me = next((p for p in info.get("participants") or [] if p.get("puuid") == puuid), None)
        if not me:
            continue
        games += 1
        win = 1 if me.get("win") else 0
        wins += win
        c = champs.setdefault(int(me.get("championId") or 0), {"games": 0, "wins": 0, "k": 0, "d": 0, "a": 0})
        c["games"] += 1
        c["wins"] += win
        c["k"] += me.get("kills") or 0
        c["d"] += me.get("deaths") or 0
        c["a"] += me.get("assists") or 0
        pos = _POS_FROM_RIOT.get((me.get("teamPosition") or "").upper())
        if pos:
            positions[pos] = positions.get(pos, 0) + 1
        if games >= limit:
            break
    if not games:
        return None
    top = []
    for cid, c in sorted(champs.items(), key=lambda kv: (kv[1]["games"], kv[1]["wins"]), reverse=True)[:3]:
        info = _resolve_champion(cid) or {}
        top.append({"id": info.get("id") or str(cid), "name": info.get("name") or str(cid),
                    "image": champion_img(info.get("image") or info.get("id") or str(cid)),
                    "games": c["games"], "wins": c["wins"], "win_rate": round(c["wins"] / c["games"] * 100, 1),
                    "kda": round((c["k"] + c["a"]) / max(1, c["d"]), 2)})
    return {"games": games, "wins": wins, "win_rate": round(wins / games * 100, 1), "top_champions": top,
            "main_position": max(positions, key=positions.get) if positions else "",
            "note": f"최근 랭크 {games}게임 기준"}


def player_collected_summary(puuid: str, limit: int = 20) -> Optional[Dict[str, Any]]:
    """수집된 고티어 솔로랭크 게임 중 그 소환사의 최근 limit판 요약 (라이엇 호출 없음). 없으면 None."""
    if not is_riot_puuid(puuid):
        return None
    init_collector_tables()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT champion_id, position, win, kills, deaths, assists FROM collected_participants "
            "WHERE puuid = ? ORDER BY game_end DESC LIMIT ?",
            (puuid, limit),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    from app.champion_stats import _resolve_champion
    from app.ddragon import champion_img
    champs: Dict[int, Dict[str, Any]] = {}
    positions: Dict[str, int] = {}
    for cid, pos, win, k, d, a in rows:
        c = champs.setdefault(cid, {"games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0})
        c["games"] += 1
        c["wins"] += win
        c["kills"] += k or 0
        c["deaths"] += d or 0
        c["assists"] += a or 0
        if pos:
            positions[pos] = positions.get(pos, 0) + 1
    top = []
    for cid, c in sorted(champs.items(), key=lambda kv: (kv[1]["games"], kv[1]["wins"]), reverse=True)[:3]:
        info = _resolve_champion(cid) or {}
        top.append({
            "id": info.get("id") or str(cid),
            "name": info.get("name") or str(cid),
            "image": champion_img(info.get("image") or info.get("id") or str(cid)),
            "games": c["games"],
            "wins": c["wins"],
            "win_rate": round(c["wins"] / c["games"] * 100, 1),
            "kda": round((c["kills"] + c["assists"]) / max(1, c["deaths"]), 2),
        })
    wins = sum(r[2] for r in rows)
    return {
        "games": len(rows),
        "wins": wins,
        "win_rate": round(wins / len(rows) * 100, 1),
        "top_champions": top,
        "main_position": max(positions, key=positions.get) if positions else "",
        "note": f"수집된 고티어 솔로랭크 최근 {len(rows)}게임 기준",
    }


def player_champion_record(puuid: str, champion_id: int) -> Optional[Dict[str, Any]]:
    """수집된 게임 중 그 소환사가 그 챔피언으로 한 판 수·승률 (없으면 None)"""
    if not is_riot_puuid(puuid) or champion_id is None:
        return None
    init_collector_tables()
    conn = get_connection()
    try:
        games, wins = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(win), 0) FROM collected_participants WHERE puuid = ? AND champion_id = ?",
            (puuid, int(champion_id)),
        ).fetchone()
    finally:
        conn.close()
    if not games:
        return None
    return {"games": games, "wins": wins, "win_rate": round(wins / games * 100, 1)}


def compact_match(raw: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    라이엇 Match-V5 상세 데이터에서 queueId == 420(솔로랭크)인 매치만 압축 구조로 추출.
    queueId가 420이 아니면 None 반환.
    """
    if not isinstance(raw, dict):
        return None
    info = raw.get("info")
    if not isinstance(info, dict):
        return None
    if info.get("queueId") != 420:
        return None

    # game_version: 앞 두 자리 (예: "16.21.123.456" -> "16.21")
    raw_version = info.get("gameVersion")
    if raw_version:
        parts = str(raw_version).split(".")
        game_version = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else str(raw_version)
    else:
        game_version = None

    # game_end: ms -> 초
    end_ms = info.get("gameEndTimestamp")
    game_end = int(end_ms // 1000) if end_ms is not None else None

    # duration: 초
    dur = info.get("gameDuration")
    duration = int(dur) if dur is not None else None

    raw_participants = info.get("participants") or []
    early_surrender = any(bool(p.get("gameEndedInEarlySurrender")) for p in raw_participants)

    participants = []
    for p in raw_participants:
        perks = p.get("perks") or {}
        styles = perks.get("styles") or []
        style0 = styles[0] if len(styles) > 0 and isinstance(styles[0], dict) else {}
        style1 = styles[1] if len(styles) > 1 and isinstance(styles[1], dict) else {}
        selections0 = style0.get("selections") or []
        selections1 = style1.get("selections") or []
        keystone = (
            selections0[0].get("perk")
            if len(selections0) > 0 and isinstance(selections0[0], dict)
            else None
        )
        primary_style = style0.get("style")
        sub_style = style1.get("style")

        perk_list = []
        if isinstance(selections0, list):
            for s in selections0[:4]:
                if isinstance(s, dict) and s.get("perk") is not None:
                    perk_list.append(s.get("perk"))
        if isinstance(selections1, list):
            for s in selections1[:2]:
                if isinstance(s, dict) and s.get("perk") is not None:
                    perk_list.append(s.get("perk"))

        stat_perks = perks.get("statPerks") if isinstance(perks, dict) else None
        shard_list = []
        if isinstance(stat_perks, dict):
            off = stat_perks.get("offense")
            flx = stat_perks.get("flex")
            df = stat_perks.get("defense")
            if off is not None and flx is not None and df is not None:
                shard_list = [off, flx, df]

        tot_minions = p.get("totalMinionsKilled")
        neu_minions = p.get("neutralMinionsKilled")
        if tot_minions is not None or neu_minions is not None:
            cs = (tot_minions or 0) + (neu_minions or 0)
        else:
            cs = None

        items = [p.get(f"item{i}") for i in range(7)]
        spells = [p.get("summoner1Id"), p.get("summoner2Id")]

        participants.append({
            "puuid": p.get("puuid"),
            "team_id": p.get("teamId"),
            "win": bool(p.get("win")) if p.get("win") is not None else None,
            "champion_id": p.get("championId"),
            "position": p.get("teamPosition"),
            "items": items,
            "spells": spells,
            "keystone": keystone,
            "primary_style": primary_style,
            "sub_style": sub_style,
            "perks": perk_list,
            "shards": shard_list,
            "kills": p.get("kills"),
            "deaths": p.get("deaths"),
            "assists": p.get("assists"),
            "cs": cs,
            "gold": p.get("goldEarned"),
            "damage": p.get("totalDamageDealtToChampions"),
        })

    bans = []
    for team in info.get("teams") or []:
        for b in team.get("bans") or []:
            cid = b.get("championId")
            if cid is not None and cid != -1:
                bans.append(cid)

    return {
        "game_version": game_version,
        "game_end": game_end,
        "duration": duration,
        "early_surrender": early_surrender,
        "participants": participants,
        "bans": bans,
    }


START_ITEM_WINDOW_MS = 60_000  # 시작 아이템: 게임 시작 1분 안에 산 것


def apply_timeline(compacted: Dict[str, Any], timeline: Optional[Dict[str, Any]]) -> None:
    """
    타임라인에서 참가자별로 뽑아 compacted 참가자에 추가 (없으면 필드를 넣지 않음):
    - skills: 스킬 레벨업 순서 (1=Q 2=W 3=E 4=R)
    - start_items: 1분 안에 산 아이템 (되돌리기·판매 반영)
    - item_order: 처음 산 순서대로의 아이템 ID (중복 제외, 최대 20개)
    """
    info = (timeline or {}).get("info") if isinstance(timeline, dict) else None
    frames = info.get("frames") if isinstance(info, dict) else None
    if not isinstance(frames, list):
        return
    parts = compacted.get("participants") or []
    skills: Dict[int, List[int]] = {i: [] for i in range(1, len(parts) + 1)}
    start: Dict[int, List[int]] = {i: [] for i in skills}
    order: Dict[int, List[int]] = {i: [] for i in skills}
    for frame in frames:
        for ev in (frame or {}).get("events") or []:
            pid = ev.get("participantId")
            if pid not in skills:
                continue
            etype = ev.get("type")
            ts = ev.get("timestamp") or 0
            if etype == "SKILL_LEVEL_UP" and ev.get("levelUpType", "NORMAL") == "NORMAL":
                slot = ev.get("skillSlot")
                if slot in (1, 2, 3, 4):
                    skills[pid].append(slot)
            elif etype == "ITEM_PURCHASED":
                item = ev.get("itemId")
                if not item:
                    continue
                if ts <= START_ITEM_WINDOW_MS:
                    start[pid].append(item)
                if item not in order[pid] and len(order[pid]) < 20:
                    order[pid].append(item)
            elif etype in ("ITEM_UNDO", "ITEM_SOLD") and ts <= START_ITEM_WINDOW_MS:
                item = ev.get("beforeId") if etype == "ITEM_UNDO" else ev.get("itemId")
                if item in start[pid]:
                    start[pid].remove(item)
    for i, p in enumerate(parts, start=1):
        p["skills"] = skills[i][:18]
        p["start_items"] = sorted(start[i])
        p["item_order"] = order[i]


def seed_from_ladder() -> int:
    """ladder_real의 puuid를 collector_seeds에 source='ladder'로 추가 (이미 있으면 무시)"""
    init_collector_tables()
    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            rows = cur.execute(
                "SELECT puuid FROM ladder_real WHERE puuid IS NOT NULL AND puuid != ''"
            ).fetchall()
        except Exception:
            rows = []
        now = int(time.time())
        inserted = 0
        for r in rows:
            puuid = r[0]
            if is_riot_puuid(puuid):
                cur.execute(
                    "INSERT OR IGNORE INTO collector_seeds (puuid, source, last_crawled, added_at) VALUES (?, 'ladder', 0, ?)",
                    (puuid, now),
                )
                if cur.rowcount > 0:
                    inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


def _add_match_seeds(puuids: List[str]) -> int:
    """매치 참가자 puuid를 collector_seeds에 추가하되 총수 5000 초과 방지"""
    valid_puuids = [p for p in puuids if p and is_riot_puuid(p)]
    if not valid_puuids:
        return 0
    conn = get_connection()
    try:
        cur = conn.cursor()
        count = cur.execute("SELECT COUNT(*) FROM collector_seeds").fetchone()[0]
        if count >= MAX_SEEDS:
            return 0

        now = int(time.time())
        inserted = 0
        for p in valid_puuids:
            if count >= MAX_SEEDS:
                break
            cur.execute(
                "INSERT OR IGNORE INTO collector_seeds (puuid, source, last_crawled, added_at) VALUES (?, 'match', 0, ?)",
                (p, now),
            )
            if cur.rowcount > 0:
                count += 1
                inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


def _parse_ver(v: str):
    return tuple(int(x) if x.isdigit() else 0 for x in str(v).split("."))


def prune_old_versions(keep: int = KEEP_VERSIONS) -> int:
    """최신 keep개 패치보다 오래된 매치를 지우고 지운 행 수를 돌려준다."""
    conn = get_connection()
    try:
        versions = [r[0] for r in conn.execute(
            "SELECT DISTINCT game_version FROM collected_matches WHERE game_version IS NOT NULL AND game_version != ''"
        ).fetchall()]
        old = sorted(versions, key=_parse_ver, reverse=True)[keep:]
        if not old:
            return 0
        cur = conn.execute(
            f"DELETE FROM collected_matches WHERE game_version IN ({','.join('?' * len(old))})", old
        )
        conn.execute(
            "DELETE FROM collected_participants WHERE match_id NOT IN (SELECT match_id FROM collected_matches)"
        )
        conn.commit()
        logger.info("Collector: pruned %s matches from old versions %s", cur.rowcount, old)
        return cur.rowcount
    finally:
        conn.close()


def latest_version_is_full() -> bool:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT game_version, COUNT(*) FROM collected_matches GROUP BY game_version").fetchall()
    finally:
        conn.close()
    if not rows:
        return False
    latest = max(rows, key=lambda r: _parse_ver(r[0] or ""))
    return latest[1] >= MAX_MATCHES_PER_PATCH


async def run_collector_cycle() -> None:
    """
    수집기 1회 주기 실행:
    1. last_crawled가 가장 오래된 시드 1명 선택 (24시간 내 크롤한 사람은 제외)
    2. get_match_ids_by_puuid(puuid, count=20, queue=420, start_time=지금-14일)
    3. 이미 collected_matches에 있는 ID 제외, 나머지 하나씩 get_match_detail -> compact_match -> 저장
    4. 시드의 last_crawled 갱신
    """
    init_collector_tables()
    now = int(time.time())
    cutoff = now - 86400  # 24시간 전

    global _last_prune_at
    if now - _last_prune_at >= PRUNE_INTERVAL_SEC:
        _last_prune_at = now
        prune_old_versions()
    if latest_version_is_full():
        # 새 패치 매치는 계속 받아야 하므로 멈추지 않고 느리게만 돈다
        await asyncio.sleep(FULL_PATCH_PAUSE_SEC)

    conn = get_connection()
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT puuid, last_crawled FROM collector_seeds WHERE last_crawled <= ? ORDER BY last_crawled ASC LIMIT 1",
            (cutoff,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        logger.info("Collector: No seed eligible for crawl. Sleeping 600s.")
        await asyncio.sleep(600)
        return

    puuid = row[0]
    start_time = now - 14 * 86400

    await collector_rate_limiter.acquire()
    match_ids = await riot_client.get_match_ids_by_puuid(
        puuid, count=20, queue=420, start_time=start_time
    )

    if match_ids:
        conn = get_connection()
        try:
            cur = conn.cursor()
            placeholders = ",".join("?" * len(match_ids))
            existing_rows = cur.execute(
                f"SELECT match_id FROM collected_matches WHERE match_id IN ({placeholders})",
                match_ids,
            ).fetchall()
            existing_ids = {r[0] for r in existing_rows}
        finally:
            conn.close()
        new_match_ids = [mid for mid in match_ids if mid not in existing_ids]
    else:
        new_match_ids = []

    for mid in new_match_ids:
        await collector_rate_limiter.acquire()
        raw_detail = await riot_client.get_match_detail(mid)
        if not raw_detail:
            continue
        compacted = compact_match(raw_detail)
        if compacted is None:
            continue
        # 스킬 순서·시작 아이템용 타임라인 (같은 수집기 한도 안에서 1회 더 호출)
        await collector_rate_limiter.acquire()
        try:
            apply_timeline(compacted, await riot_client.get_match_timeline(mid))
        except RiotAPIError as e:
            if e.status_code in (401, 429, 503):
                raise
            logger.warning("Collector: timeline %s failed (%s), saving without it", mid, e.status_code)

        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO collected_matches
                (match_id, game_version, game_end, duration, data, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    compacted["game_version"],
                    compacted["game_end"],
                    compacted["duration"],
                    json.dumps(compacted, ensure_ascii=False),
                    int(time.time()),
                ),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO collected_participants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _participant_rows(mid, compacted),
            )
            conn.commit()
        finally:
            conn.close()

        participant_puuids = [
            p["puuid"] for p in compacted.get("participants", []) if p.get("puuid")
        ]
        _add_match_seeds(participant_puuids)

    # 시드의 last_crawled 갱신
    now_after = int(time.time())
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE collector_seeds SET last_crawled = ? WHERE puuid = ?",
            (now_after, puuid),
        )
        conn.commit()
    finally:
        conn.close()


async def collector_loop() -> None:
    """
    백그라운드 수집기 무한 루프
    """
    global _last_cycle_at
    while True:
        try:
            if not settings.riot_api_key:
                logger.info("Collector: Riot API Key not configured. Sleeping 300s.")
                await asyncio.sleep(300)
                continue

            await run_collector_cycle()
            _last_cycle_at = time.time()
        except asyncio.CancelledError:
            break
        except RiotAPIError as e:
            if e.status_code == 429:
                logger.warning("Collector: Riot API 429 Rate Limit. Sleeping 120s.")
                await asyncio.sleep(120)
            elif e.status_code in (401, 403):
                logger.warning(
                    "Collector: Riot API Key invalid/expired (%d). Sleeping 1h.",
                    e.status_code,
                )
                await asyncio.sleep(3600)
            elif e.status_code == 503:
                logger.warning("Collector: Riot API 503 Service Unavailable. Sleeping 60s.")
                await asyncio.sleep(60)
            else:
                logger.warning(
                    "Collector: Riot API Error (%d: %s). Sleeping 60s.",
                    e.status_code,
                    e.message,
                )
                await asyncio.sleep(60)
        except Exception as e:
            logger.exception("Collector: Unexpected error in cycle: %s. Sleeping 60s.", e)
            await asyncio.sleep(60)


def collector_status() -> Dict[str, Any]:
    """수집기 실시간 상태 메타데이터 조회"""
    init_collector_tables()
    enabled = os.getenv("MATCH_COLLECTOR", "1").strip() != "0"
    conn = get_connection()
    try:
        cur = conn.cursor()
        matches_count = cur.execute("SELECT COUNT(*) FROM collected_matches").fetchone()[0]
        seeds_count = cur.execute("SELECT COUNT(*) FROM collector_seeds").fetchone()[0]

        rows = cur.execute(
            """
            SELECT game_version, COUNT(*)
            FROM collected_matches
            WHERE game_version IS NOT NULL
            GROUP BY game_version
            ORDER BY COUNT(*) DESC
            """
        ).fetchall()
        version_counts = {r[0]: r[1] for r in rows}
    finally:
        conn.close()

    return {
        "enabled": enabled,
        "matches": matches_count,
        "seeds": seeds_count,
        "latest_version_counts": version_counts,
        "last_cycle_at": _last_cycle_at,
    }
