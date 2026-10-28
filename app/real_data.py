"""
실제 라이엇 API 데이터 계층

- 소환사 조회: Account-V1 -> Summoner-V4 -> League-V4 (riot_client.fetch_full_player_profile)
- 최근 전적: Match-V5 (매치 상세는 변하지 않으므로 SQLite match_cache 에 영구 캐시)
- 화면이 기대하는 기존 전적 JSON 구조로 변환

이 모듈은 어떤 값도 지어내지 않는다. 라이엇 데이터에 없는 값은 None/빈 값으로 둔다.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.champion_engine import CHAMPION_MAP_BY_ID
from app.config import settings
from app.database import get_connection, get_player_by_riot_id, is_riot_puuid, upsert_player
from app.ddragon import champion_img, item_info, item_img, rune_info, rune_style_info, spell_info
from app.riot_client import RiotAPIError, riot_client

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

QUEUE_NAMES = {
    420: "솔로랭크", 440: "자유랭크", 450: "칼바람 나락", 400: "일반 (선택)", 430: "일반 (블라인드)",
    490: "빠른 대전", 480: "신속 대전", 700: "격전", 1700: "아레나", 1900: "U.R.F.", 900: "U.R.F.",
    1020: "단일 챔피언", 1300: "돌격 넥서스", 2400: "칼바람 난투",
}
POSITION_MAP = {"TOP": "TOP", "JUNGLE": "JUG", "MIDDLE": "MID", "BOTTOM": "BOT", "UTILITY": "SUP"}
POS_KR = {"TOP": "탑", "JUG": "정글", "MID": "미드", "BOT": "원딜", "SUP": "서폿"}
POSITION_ORDER = {"TOP": 0, "JUG": 1, "MID": 2, "BOT": 3, "SUP": 4}
REMAKE_MAX_SEC = 300
MATCH_FETCH_CONCURRENCY = 4


class PlayerDataUnavailable(Exception):
    """라이엇 데이터를 가져올 수 없음 (status_code: 404 없음 / 503 키 없음·만료 / 429 한도)"""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _riot_error(e: RiotAPIError) -> PlayerDataUnavailable:
    code = getattr(e, "status_code", None) or 500
    if code == 404:
        return PlayerDataUnavailable(404, getattr(e, "message", "") or "소환사를 찾을 수 없습니다.")
    if code == 429:
        return PlayerDataUnavailable(429, "라이엇 API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
    return PlayerDataUnavailable(503, "라이엇 API에 연결할 수 없습니다. 관리자에게 API 키 상태를 확인해달라고 요청하세요.")


# ---------------------------------------------------------------------------
# 티어/LP 스냅샷 & 히스토리 (rank_snapshots)
# ---------------------------------------------------------------------------

def init_rank_snapshots() -> None:
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rank_snapshots (
            puuid TEXT NOT NULL,
            captured_at INTEGER NOT NULL,
            tier TEXT NOT NULL,
            rank_tier TEXT,
            league_points INTEGER NOT NULL,
            wins INTEGER NOT NULL,
            losses INTEGER NOT NULL,
            tier_score INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rank_snapshots_puuid_time ON rank_snapshots(puuid, captured_at)")
    conn.commit()
    conn.close()


def record_rank_snapshot(player: Dict[str, Any], captured_at: Optional[int] = None) -> None:
    puuid = player.get("puuid")
    if not is_riot_puuid(puuid):
        return
    tier = (player.get("tier") or "").strip().upper()
    if not tier or tier == "UNRANKED":
        return

    rank_tier = (player.get("rank_tier") or "").strip().upper()
    league_points = int(player.get("league_points", 0))
    wins = int(player.get("wins", 0))
    losses = int(player.get("losses", 0))
    tier_score = int(player.get("tier_score", 0))

    init_rank_snapshots()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT tier, rank_tier, league_points, wins, losses FROM rank_snapshots "
            "WHERE puuid = ? ORDER BY captured_at DESC, rowid DESC LIMIT 1",
            (puuid,)
        )
        last = cur.fetchone()
        if last:
            last_tier = (last["tier"] or "").strip().upper()
            last_rank = (last["rank_tier"] or "").strip().upper()
            last_lp = int(last["league_points"])
            last_wins = int(last["wins"])
            last_losses = int(last["losses"])
            if (
                last_tier == tier
                and last_rank == rank_tier
                and last_lp == league_points
                and last_wins == wins
                and last_losses == losses
            ):
                return

        ts = captured_at if captured_at is not None else player.get("captured_at")
        if ts is None:
            ts = int(time.time())
        else:
            ts = int(ts)

        conn.execute(
            "INSERT INTO rank_snapshots (puuid, captured_at, tier, rank_tier, league_points, wins, losses, tier_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (puuid, ts, tier, rank_tier, league_points, wins, losses, tier_score)
        )
        conn.commit()
    finally:
        conn.close()


def build_tier_history(puuid: str) -> Dict[str, List[Dict[str, Any]]]:
    empty_history = {"daily": [], "weekly": [], "monthly": []}
    if not is_riot_puuid(puuid):
        return empty_history

    init_rank_snapshots()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT captured_at, tier, rank_tier, league_points, wins, losses, tier_score "
            "FROM rank_snapshots WHERE puuid = ? ORDER BY captured_at ASC, rowid ASC",
            (puuid,)
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return empty_history

    now_ts = int(time.time())
    now_dt = datetime.fromtimestamp(now_ts, tz=KST)
    today = now_dt.date()

    # 1. Daily: 최근 30일, 날짜(KST)별 그날 마지막 스냅샷 1개씩
    daily_start_date = today - timedelta(days=29)
    daily_groups: Dict[Any, Any] = {}
    for r in rows:
        dt = datetime.fromtimestamp(r["captured_at"], tz=KST)
        d = dt.date()
        if daily_start_date <= d <= today:
            daily_groups[d] = (dt, r)

    # 2. Weekly: 최근 12주, 주(월요일 시작, KST)별 마지막 스냅샷 1개씩
    current_monday = today - timedelta(days=today.weekday())
    weekly_start_monday = current_monday - timedelta(weeks=11)
    weekly_groups: Dict[Any, Any] = {}
    for r in rows:
        dt = datetime.fromtimestamp(r["captured_at"], tz=KST)
        m = dt.date() - timedelta(days=dt.weekday())
        if weekly_start_monday <= m <= current_monday:
            weekly_groups[m] = (dt, m, r)

    # 3. Monthly: 최근 12개월, 월별 마지막 스냅샷 1개씩
    monthly_groups: Dict[Any, Any] = {}
    for r in rows:
        dt = datetime.fromtimestamp(r["captured_at"], tz=KST)
        month_diff = (today.year - dt.year) * 12 + (today.month - dt.month)
        if 0 <= month_diff < 12:
            key = (dt.year, dt.month)
            monthly_groups[key] = (dt, r)

    daily_points = []
    prev_score = None
    for d in sorted(daily_groups.keys()):
        dt, r = daily_groups[d]
        ts = int(r["tier_score"])
        lp_change = 0 if prev_score is None else (ts - prev_score)
        prev_score = ts
        daily_points.append({
            "point_date": dt.strftime("%Y-%m-%d"),
            "date_label": dt.strftime("%m/%d"),
            "tier": r["tier"],
            "rank_tier": r["rank_tier"] or "",
            "league_points": int(r["league_points"]),
            "tier_score": ts,
            "wins": int(r["wins"]),
            "losses": int(r["losses"]),
            "lp_change": lp_change,
        })

    weekly_points = []
    prev_score = None
    for m in sorted(weekly_groups.keys()):
        dt, monday, r = weekly_groups[m]
        ts = int(r["tier_score"])
        lp_change = 0 if prev_score is None else (ts - prev_score)
        prev_score = ts
        weekly_points.append({
            "point_date": dt.strftime("%Y-%m-%d"),
            "date_label": monday.strftime("%m/%d주"),
            "tier": r["tier"],
            "rank_tier": r["rank_tier"] or "",
            "league_points": int(r["league_points"]),
            "tier_score": ts,
            "wins": int(r["wins"]),
            "losses": int(r["losses"]),
            "lp_change": lp_change,
        })

    monthly_points = []
    prev_score = None
    for ym in sorted(monthly_groups.keys()):
        dt, r = monthly_groups[ym]
        ts = int(r["tier_score"])
        lp_change = 0 if prev_score is None else (ts - prev_score)
        prev_score = ts
        monthly_points.append({
            "point_date": dt.strftime("%Y-%m-%d"),
            "date_label": dt.strftime("%Y.%m"),
            "tier": r["tier"],
            "rank_tier": r["rank_tier"] or "",
            "league_points": int(r["league_points"]),
            "tier_score": ts,
            "wins": int(r["wins"]),
            "losses": int(r["losses"]),
            "lp_change": lp_change,
        })

    return {
        "daily": daily_points if len(daily_points) >= 2 else [],
        "weekly": weekly_points if len(weekly_points) >= 2 else [],
        "monthly": monthly_points if len(monthly_points) >= 2 else [],
    }


# ---------------------------------------------------------------------------
# 소환사
# ---------------------------------------------------------------------------

async def fetch_player(game_name: str, tag_line: str, allow_cached: bool = True) -> Dict[str, Any]:
    """라이엇 API로 소환사를 조회해 DB에 저장하고 반환. API를 쓸 수 없으면 실제 데이터로 저장된 캐시만 허용."""
    if settings.riot_api_key:
        try:
            live = await riot_client.fetch_full_player_profile(game_name, tag_line)
            player = upsert_player(**live)
            player["data_source"] = "riot_api"
            try:
                record_rank_snapshot(player)
            except Exception as e:
                logger.warning("Failed to record rank snapshot for %s: %s", player.get("puuid"), e)
            try:
                puuid = player.get("puuid")
                if is_riot_puuid(puuid):
                    last_up = get_mastery_updated_at(puuid)
                    if last_up is None or (time.time() - last_up >= 3600):
                        await refresh_masteries(puuid)
            except Exception as e:
                logger.warning("Failed to refresh masteries for %s: %s", player.get("puuid"), e)
            return player
        except RiotAPIError as e:
            err = _riot_error(e)
            if err.status_code == 404:
                raise err
            cached = get_player_by_riot_id(game_name, tag_line) if allow_cached else None
            if cached and is_riot_puuid(cached.get("puuid")):
                cached["data_source"] = "cache"
                cached["stale_reason"] = err.detail
                return cached
            raise err
    cached = get_player_by_riot_id(game_name, tag_line) if allow_cached else None
    if cached and is_riot_puuid(cached.get("puuid")):
        cached["data_source"] = "cache"
        cached["stale_reason"] = "라이엇 API 키가 등록되지 않아 마지막으로 저장된 정보를 표시합니다."
        return cached
    raise PlayerDataUnavailable(503, "라이엇 API 키가 등록되지 않아 소환사 정보를 조회할 수 없습니다.")


def public_profile(player: Dict[str, Any]) -> Dict[str, Any]:
    """프로필 응답. 라이엇 API가 제공하지 않는 과거 시즌/최고·최저 티어는 비워 둔다. 티어 변동은 실제 스냅샷으로 구성."""
    out = dict(player)
    puuid = player.get("puuid")
    if is_riot_puuid(puuid):
        out["tier_history"] = build_tier_history(puuid)
    else:
        out["tier_history"] = {"daily": [], "weekly": [], "monthly": []}
    out["past_seasons"] = {}
    out["past_tier_badges"] = []
    for key in ("peak_tier", "peak_rank_tier", "peak_lp", "peak_season",
                "lowest_tier", "lowest_rank_tier", "lowest_lp", "lowest_season"):
        out[key] = None
    out["top_masteries"] = load_top_masteries(puuid) if is_riot_puuid(puuid) else []
    return out


def load_top_masteries(puuid: str, limit: int = 5) -> List[Dict[str, Any]]:
    """저장된 챔피언 숙련도 상위 (소환사 조회 때 이미 받아 둔 값, 추가 호출 없음)"""
    init_champion_mastery_table()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT champion_id, champion_points, champion_level FROM champion_mastery_real "
            "WHERE puuid = ? ORDER BY champion_points DESC LIMIT ?",
            (puuid, limit),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for cid, pts, lvl in rows:
        c = _CHAMP_BY_KEY.get(str(cid))
        if not c:
            continue
        out.append({"id": c.get("id"), "name": c.get("name"), "image": champion_img(c.get("image") or c["id"]),
                    "points": int(pts), "level": int(lvl)})
    return out


# ---------------------------------------------------------------------------
# 매치 캐시 (SQLite)
# ---------------------------------------------------------------------------

def init_match_cache() -> None:
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS match_cache (
            match_id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            game_end INTEGER,
            fetched_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _load_cached_matches(match_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not match_ids:
        return {}
    init_match_cache()
    conn = get_connection()
    rows = conn.execute(
        f"SELECT match_id, data FROM match_cache WHERE match_id IN ({','.join('?' * len(match_ids))})",
        match_ids,
    ).fetchall()
    conn.close()
    return {r[0]: json.loads(r[1]) for r in rows}


def _store_matches(matches: List[Dict[str, Any]]) -> None:
    if not matches:
        return
    conn = get_connection()
    now = int(time.time())
    conn.executemany(
        "INSERT OR REPLACE INTO match_cache (match_id, data, game_end, fetched_at) VALUES (?, ?, ?, ?)",
        [
            (m["metadata"]["matchId"], json.dumps(m, ensure_ascii=False), m["info"].get("gameEndTimestamp"), now)
            for m in matches
        ],
    )
    conn.commit()
    conn.close()


async def fetch_recent_matches(puuid: str, count: int = 20) -> List[Dict[str, Any]]:
    """최근 매치 원본(Match-V5) 목록. 캐시에 없는 매치만 라이엇 API로 받는다."""
    if not settings.riot_api_key:
        raise PlayerDataUnavailable(503, "라이엇 API 키가 등록되지 않아 전적을 조회할 수 없습니다.")
    if not is_riot_puuid(puuid):
        raise PlayerDataUnavailable(404, "라이엇에서 확인된 소환사가 아닙니다.")

    try:
        match_ids = await riot_client.get_match_ids_by_puuid(puuid, count=count)
    except RiotAPIError as e:
        raise _riot_error(e)

    cached = _load_cached_matches(match_ids)
    missing = [mid for mid in match_ids if mid not in cached]
    sem = asyncio.Semaphore(MATCH_FETCH_CONCURRENCY)

    async def fetch_one(mid: str) -> Optional[Dict[str, Any]]:
        async with sem:
            return await riot_client.get_match_detail(mid)

    results = await asyncio.gather(*(fetch_one(mid) for mid in missing), return_exceptions=True)
    fetched = [m for m in results if isinstance(m, dict) and m.get("info")]
    _store_matches(fetched)  # 받은 것은 캐시해 두고, 하나라도 실패했으면 일부만 보여주지 않고 오류를 알린다
    errors = [r for r in results if isinstance(r, RiotAPIError)]
    if errors:
        raise _riot_error(errors[0])
    other = next((r for r in results if isinstance(r, BaseException)), None)
    if other:
        raise PlayerDataUnavailable(503, "라이엇 API와 통신 중 오류가 발생했습니다.")
    by_id = {**cached, **{m["metadata"]["matchId"]: m for m in fetched}}
    return [by_id[mid] for mid in match_ids if mid in by_id]


# ---------------------------------------------------------------------------
# Match-V5 -> 화면용 JSON 변환
# ---------------------------------------------------------------------------

def _kda(k: int, d: int, a: int) -> float:
    if d == 0:
        return 10.0 if (k + a) > 0 else 0.0
    return round((k + a) / d, 2)


def _time_ago(end_ms: Optional[int]) -> str:
    if not end_ms:
        return ""
    minutes = max(0, int((time.time() * 1000 - end_ms) / 60000))
    if minutes < 60:
        return f"{minutes}분 전"
    if minutes < 1440:
        return f"{minutes // 60}시간 전"
    return f"{minutes // 1440}일 전"


def _champion(p: Dict[str, Any]) -> Dict[str, str]:
    cid = p.get("championName", "")
    info = CHAMPION_MAP_BY_ID.get(cid.lower())
    return {
        "id": cid,
        "name": info["name"] if info else cid,
        "image": champion_img(info["image"] if info else cid),
    }


def _multi_kill(p: Dict[str, Any]):
    for field, kr, tag in (("pentaKills", "펜타킬", "PENTAKILL"), ("quadraKills", "쿼드라킬", "QUADRAKILL"),
                           ("tripleKills", "트리플킬", "TRIPLEKILL"), ("doubleKills", "더블킬", "DOUBLEKILL")):
        if p.get(field, 0) > 0:
            return kr, tag
    return None, None


def _runes(p: Dict[str, Any]):
    styles = (p.get("perks") or {}).get("styles") or []
    keystone = rune_info(styles[0]["selections"][0]["perk"]) if styles and styles[0].get("selections") else rune_info(0)
    secondary = rune_style_info(styles[1]["style"]) if len(styles) > 1 else rune_style_info(0)
    return keystone, secondary


def _participant_row(p: Dict[str, Any], team_kills: int, puuid: str) -> Dict[str, Any]:
    champ = _champion(p)
    k, d, a = p.get("kills", 0), p.get("deaths", 0), p.get("assists", 0)
    pos = POSITION_MAP.get(p.get("teamPosition") or p.get("individualPosition") or "", "")
    duration_min = max(1.0, p.get("timePlayed", 0) / 60) if p.get("timePlayed") else None
    cs = p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0)
    gold = p.get("goldEarned", 0)
    keystone, secondary = _runes(p)
    s1, s2 = spell_info(p.get("summoner1Id")), spell_info(p.get("summoner2Id"))
    multi_kill, multi_kill_tag = _multi_kill(p)
    return {
        "is_me": p.get("puuid") == puuid,
        "puuid": p.get("puuid"),
        "game_name": p.get("riotIdGameName") or p.get("summonerName", ""),
        "tag_line": p.get("riotIdTagline", ""),
        "position": pos,
        "position_kr": POS_KR.get(pos, ""),
        "tier": "",
        "champ_id": champ["id"],
        "champ_name": champ["name"],
        "champ_img": champ["image"],
        "champ_level": p.get("champLevel", 0),
        "kills": k,
        "deaths": d,
        "assists": a,
        "kda_ratio": _kda(k, d, a),
        "kill_participation": min(100, round((k + a) / team_kills * 100)) if team_kills else 0,
        "damage_dealt": p.get("totalDamageDealtToChampions", 0),
        "damage_taken": p.get("totalDamageTaken", 0),
        "cs": cs,
        "cs_per_min": round(cs / duration_min, 1) if duration_min else 0,
        "gold": gold,
        "gold_str": f"{gold / 1000:.1f}k",
        "control_wards": p.get("visionWardsBoughtInGame", 0),
        "wards_placed": p.get("wardsPlaced", 0),
        "vision_score": p.get("visionScore", 0),
        "items": [p.get(f"item{i}", 0) for i in range(6) if p.get(f"item{i}", 0)],
        "trinket": p.get("item6", 0),
        "spell1_icon": s1["icon"],
        "spell2_icon": s2["icon"],
        "spells": [s1, s2],
        "primary_rune": keystone,
        "secondary_rune": secondary,
        "primary_rune_icon": keystone["icon"],
        "secondary_rune_icon": secondary["icon"],
        "multi_kill": multi_kill,
        "multi_kill_tag": multi_kill_tag,
        "win": bool(p.get("win")),
        "team_id": p.get("teamId"),
    }


def _performance_score(row: Dict[str, Any], max_damage: int) -> float:
    """KDA와 팀 내 피해량 비중으로 계산하는 0~10 경기력 지표 (라이엇 공식 지표 아님)"""
    kda = (row["kills"] + row["assists"]) / max(1, row["deaths"])
    dmg_ratio = row["damage_dealt"] / max(1, max_damage)
    return round(min(10.0, max(0.0, 3.0 + kda * 0.9 + dmg_ratio * 3.5)), 1)


def convert_match(raw: Dict[str, Any], puuid: str) -> Optional[Dict[str, Any]]:
    info = raw.get("info") or {}
    participants = info.get("participants") or []
    me = next((p for p in participants if p.get("puuid") == puuid), None)
    if not me:
        return None

    def group(p):
        # 아레나 등은 teamId 대신 playerSubteamId 로 팀이 나뉜다
        return p.get("playerSubteamId") or p.get("teamId")

    team_kills = {}
    for p in participants:
        team_kills[group(p)] = team_kills.get(group(p), 0) + p.get("kills", 0)
    rows = [_participant_row(p, team_kills.get(group(p), 0), puuid) for p in participants]
    for r, p in zip(rows, participants):
        r["team_id"] = group(p)
    max_damage = max((r["damage_dealt"] for r in rows), default=0)
    for r in rows:
        r["op_score"] = _performance_score(r, max_damage)
        r["op_badge"] = None

    my_team = group(me)
    team1 = sorted([r for r in rows if r["team_id"] == my_team], key=lambda r: POSITION_ORDER.get(r["position"], 9))
    team2 = sorted([r for r in rows if r["team_id"] != my_team], key=lambda r: POSITION_ORDER.get(r["position"], 9))

    duration = int(info.get("gameDuration", 0))
    is_remake = any(p.get("gameEndedInEarlySurrender") for p in participants) or duration < REMAKE_MAX_SEC
    win = bool(me.get("win"))
    two_teams = len({r["team_id"] for r in rows}) == 2
    if not is_remake and two_teams and team1 and team2:
        winners, losers = (team1, team2) if win else (team2, team1)
        max(winners, key=lambda r: r["op_score"])["op_badge"] = "MVP"
        max(losers, key=lambda r: r["op_score"])["op_badge"] = "ACE"

    mine = next(r for r in team1 if r["is_me"])
    end_ms = info.get("gameEndTimestamp") or (info.get("gameStartTimestamp", 0) + duration * 1000)
    queue_id = info.get("queueId")
    duration_str = f"{duration // 60}분 {duration % 60:02d}초"
    items = [item_info(i) or {"id": i, "name": "", "icon": item_img(i)} for i in mine["items"]]
    trinket = item_info(mine["trinket"]) if mine["trinket"] else None

    return {
        "match_id": raw.get("metadata", {}).get("matchId"),
        "queue_id": queue_id,
        "game_mode": QUEUE_NAMES.get(queue_id, info.get("gameMode", "")),
        "game_duration": duration_str,
        "duration_str": duration_str,
        "duration_sec": duration,
        "is_remake": is_remake,
        "time_ago": _time_ago(end_ms),
        "match_date": datetime.fromtimestamp(end_ms / 1000).strftime("%Y-%m-%d %H:%M") if end_ms else "",
        "game_version": info.get("gameVersion", ""),
        "win": win,
        "op_score": mine["op_score"],
        "op_badge": mine["op_badge"],
        "champ_name": mine["champ_name"],
        "champ_img": mine["champ_img"],
        "champ_level": mine["champ_level"],
        "kills": mine["kills"],
        "deaths": mine["deaths"],
        "assists": mine["assists"],
        "kda_ratio": mine["kda_ratio"],
        "kill_participation": mine["kill_participation"],
        "total_damage_dealt": mine["damage_dealt"],
        "cs": {"total": mine["cs"], "per_min": mine["cs_per_min"]},
        "cs_per_min": mine["cs_per_min"],
        "spell1_icon": mine["spell1_icon"],
        "spell2_icon": mine["spell2_icon"],
        "spells": mine["spells"],
        "primary_rune": mine["primary_rune"]["name"],
        "primary_rune_icon": mine["primary_rune_icon"],
        "primary_rune_data": mine["primary_rune"],
        "secondary_rune": mine["secondary_rune"],
        "secondary_rune_icon": mine["secondary_rune_icon"],
        "rune": {
            "name": mine["primary_rune"]["name"],
            "icon": mine["primary_rune_icon"],
            "secondary_name": mine["secondary_rune"]["name"],
            "secondary_icon": mine["secondary_rune_icon"],
        },
        "champion": {"id": mine["champ_id"], "name": mine["champ_name"], "image": mine["champ_img"], "level": mine["champ_level"]},
        "kda": {"kills": mine["kills"], "deaths": mine["deaths"], "assists": mine["assists"],
                "ratio": mine["kda_ratio"], "kill_participation": mine["kill_participation"]},
        "multi_kill": mine["multi_kill"],
        "multi_kill_tag": mine["multi_kill_tag"],
        "badge": mine["op_badge"],
        "items": items,
        "trinket": trinket,
        "control_wards": mine["control_wards"],
        "max_damage_in_game": max_damage,
        "team1": team1,
        "team2": team2,
        "team1_score": sum(r["kills"] for r in team1),
        "team2_score": sum(r["kills"] for r in team2),
        "position": mine["position"],
        "coach_metrics": None,
    }


def summarize_matches(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    counted = [m for m in matches if not m.get("is_remake")]
    wins = sum(1 for m in counted if m["win"])
    losses = len(counted) - wins
    k = sum(m["kills"] for m in counted)
    d = sum(m["deaths"] for m in counted)
    a = sum(m["assists"] for m in counted)
    n = len(counted) or 1

    champs: Dict[str, Dict[str, Any]] = {}
    positions = {"TOP": 0, "JUG": 0, "MID": 0, "BOT": 0, "SUP": 0}
    for m in counted:
        c = champs.setdefault(m["champ_name"], {
            "id": m["champion"]["id"], "name": m["champ_name"], "image": m["champ_img"],
            "games": 0, "wins": 0, "losses": 0, "kills": 0, "deaths": 0, "assists": 0,
        })
        c["games"] += 1
        c["wins"] += 1 if m["win"] else 0
        c["losses"] += 0 if m["win"] else 1
        c["kills"] += m["kills"]
        c["deaths"] += m["deaths"]
        c["assists"] += m["assists"]
        if m.get("position") in positions:
            positions[m["position"]] += 1

    # 같은 팀으로 2판 이상 함께한 소환사 (최근 매치 안에서만)
    mates: Dict[str, Dict[str, Any]] = {}
    for m in counted:
        my_team = next((t for t in (m.get("team1") or [], m.get("team2") or []) if any(r.get("is_me") for r in t)), [])
        for r in my_team:
            if r.get("is_me") or not r.get("puuid") or not r.get("game_name"):
                continue
            pm = mates.setdefault(r["puuid"], {"game_name": r["game_name"], "tag_line": r.get("tag_line") or "",
                                               "games": 0, "wins": 0})
            pm["games"] += 1
            pm["wins"] += 1 if m["win"] else 0
    played_with = sorted((p for p in mates.values() if p["games"] >= 2),
                         key=lambda p: (p["games"], p["wins"]), reverse=True)[:5]
    for p in played_with:
        p["losses"] = p["games"] - p["wins"]
        p["win_rate"] = round(p["wins"] / p["games"] * 100, 1)

    most = sorted(champs.values(), key=lambda c: (c["games"], c["wins"]), reverse=True)[:6]
    for c in most:
        c["win_rate"] = round(c["wins"] / c["games"] * 100, 1)
        c["kda"] = c["kda_ratio"] = _kda(c["kills"], c["deaths"], c["assists"])

    return {
        "total_games": len(counted),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(counted) * 100, 1) if counted else 0,
        "avg_kills": round(k / n, 1),
        "avg_deaths": round(d / n, 1),
        "avg_assists": round(a / n, 1),
        "avg_kda": _kda(k, d, a),
        "most_champions": most,
        "champions": most,
        "positions": positions,
        "played_with": played_with,
        "remakes": len(matches) - len(counted),
    }


# ---------------------------------------------------------------------------
# 실시간 게임 (Spectator-V5)
# ---------------------------------------------------------------------------

_CHAMP_BY_KEY = {str(c["key"]): c for c in CHAMPION_MAP_BY_ID.values()}


def convert_live_game(game: Dict[str, Any], target_puuid: str) -> Dict[str, Any]:
    """Spectator-V5 응답을 화면용으로 변환. 티어는 이전에 라이엇에서 조회해 저장된 소환사만 표시한다."""
    def champ(key) -> Dict[str, str]:
        c = _CHAMP_BY_KEY.get(str(key))
        return {"id": c["id"], "name": c["name"], "image": champion_img(c["image"])} if c else {"id": "", "name": "", "image": ""}

    from app.match_collector import player_champion_record
    participants = game.get("participants") or []
    length = int(game.get("gameLength", 0))
    queue_id = game.get("gameQueueConfigId")
    bans = game.get("bannedChampions") or []

    init_champion_mastery_table()
    mastery_map: Dict[tuple, tuple] = {}
    valid_puuids = list({p["puuid"] for p in participants if p.get("puuid")})
    if valid_puuids:
        conn = get_connection()
        try:
            placeholders = ",".join("?" for _ in valid_puuids)
            cur = conn.cursor()
            cur.execute(
                f"SELECT puuid, champion_id, champion_level, champion_points "
                f"FROM champion_mastery_real WHERE puuid IN ({placeholders})",
                valid_puuids
            )
            for row in cur.fetchall():
                p_uid = row["puuid"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[0]
                c_id = row["champion_id"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1]
                c_lvl = row["champion_level"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[2]
                c_pts = row["champion_points"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[3]
                mastery_map[(p_uid, int(c_id))] = (int(c_lvl), int(c_pts))
        finally:
            conn.close()

    def player(p: Dict[str, Any]) -> Dict[str, Any]:
        # 랭크에서 이름을 숨긴 소환사는 puuid가 없고 riotId 자리에 챔피언 이름이 온다
        hidden = not p.get("puuid")
        riot_id = "" if hidden else (p.get("riotId") or "")
        name, _, tag = riot_id.partition("#")
        if hidden:
            name = "비공개 소환사"
        known = get_player_by_riot_id(name, tag) if name and tag else None
        is_known = bool(known and is_riot_puuid(known.get("puuid")))

        perks = p.get("perks") or {}
        perk_ids = perks.get("perkIds") or []
        c = champ(p.get("championId"))

        tier = known.get("tier") if is_known else None
        display_tier = known.get("display_tier") if is_known else None
        league_points = int(known["league_points"]) if (is_known and known.get("league_points") is not None) else None
        wins = int(known["wins"]) if (is_known and known.get("wins") is not None) else None
        losses = int(known["losses"]) if (is_known and known.get("losses") is not None) else None
        if is_known and wins is not None and losses is not None and (wins + losses > 0):
            win_rate = round(wins / (wins + losses) * 100, 1)
        else:
            win_rate = None
        rank_tier = (str(known.get("rank_tier") or "").strip() or None) if is_known else None

        puuid = p.get("puuid")
        cid = p.get("championId")
        if puuid and cid is not None:
            m = mastery_map.get((puuid, int(cid)))
            champ_mastery_level = m[0] if m else None
            champ_mastery_points = m[1] if m else None
        else:
            champ_mastery_level = None
            champ_mastery_points = None

        return {
            "is_me": not hidden and p.get("puuid") == target_puuid,
            "hidden": hidden,
            "game_name": name,
            "tag_line": tag,
            "champ_name": c["name"],
            "champ_image": c["image"],
            "spell1": spell_info(p.get("spell1Id")),
            "spell2": spell_info(p.get("spell2Id")),
            "keystone": rune_info(perk_ids[0]) if perk_ids else rune_info(0),
            "sub_style": rune_style_info(perks.get("perkSubStyle")),
            "tier": tier,
            "display_tier": display_tier,
            "league_points": league_points,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "rank_tier": rank_tier,
            "champ_mastery_level": champ_mastery_level,
            "champ_mastery_points": champ_mastery_points,
            # 수집된 고티어 게임 기준 이 챔피언 전적 (없으면 None, 추가 호출 없음)
            "champ_record": player_champion_record(puuid, cid) if puuid and cid is not None else None,
        }

    return {
        "is_active": True,
        "real": True,
        "game_id": game.get("gameId"),
        "queue_id": queue_id,
        "game_mode": QUEUE_NAMES.get(queue_id, game.get("gameMode", "")),
        "game_length_sec": max(0, length),
        "game_start_time": game.get("gameStartTime"),
        # 블루(100) 외 참가자는 모두 상대 쪽에 표시 (아레나 등 2팀이 아닌 모드에서도 누락되지 않게)
        "blue_team": [player(p) for p in participants if p.get("teamId") == 100],
        "red_team": [player(p) for p in participants if p.get("teamId") != 100],
        "bans_blue": [champ(b.get("championId")) for b in bans if b.get("teamId") == 100 and b.get("championId", -1) > 0],
        "bans_red": [champ(b.get("championId")) for b in bans if b.get("teamId") == 200 and b.get("championId", -1) > 0],
        "encryption_key": (game.get("observers") or {}).get("encryptionKey"),
        "platform_id": game.get("platformId", "KR"),
    }


async def fetch_live_game(player: Dict[str, Any]) -> Dict[str, Any]:
    if not settings.riot_api_key:
        raise PlayerDataUnavailable(503, "라이엇 API 키가 등록되지 않아 실시간 게임을 조회할 수 없습니다.")
    try:
        game = await riot_client.get_spectator_active_game_by_puuid(player["puuid"])
    except RiotAPIError as e:
        raise _riot_error(e)
    if not game:
        return {"is_active": False, "real": True, "message": "현재 진행 중인 게임이 없습니다."}
    return convert_live_game(game, player["puuid"])


# ---------------------------------------------------------------------------
# 챌린저 랭킹 (League-V4 + Account-V1)
# ---------------------------------------------------------------------------

# 챌린저 상위 N명 (2026-10-28 사용자 결정: 50 → 300). 닉네임 조회는 1명당 1회라 확인한 이름을 7일 동안 저장해 두고
# 새로 들어온 사람·7일 지난 이름만 다시 묻는다 (하루 약 1 + 신규 진입자 + 300/7 회)
LADDER_NAMED_TOP_N = 300
LADDER_NAME_TTL_SEC = 7 * 86400
# 장인 숙련도는 예전 승인 범위(하루 약 50회) 그대로 상위 50명만
LADDER_MASTERY_TOP_N = 50


def init_ladder_table() -> None:
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ladder_real (
            rank INTEGER PRIMARY KEY,
            puuid TEXT NOT NULL,
            game_name TEXT NOT NULL,
            tag_line TEXT NOT NULL,
            tier TEXT NOT NULL,
            league_points INTEGER NOT NULL,
            wins INTEGER NOT NULL,
            losses INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ladder_names (
            puuid TEXT PRIMARY KEY,
            game_name TEXT NOT NULL,
            tag_line TEXT NOT NULL,
            checked_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _cached_ladder_names(puuids: List[str]) -> Dict[str, Dict[str, str]]:
    """7일 안에 확인한 닉네임 (puuid → {gameName, tagLine})"""
    if not puuids:
        return {}
    conn = get_connection()
    try:
        out: Dict[str, Dict[str, str]] = {}
        since = int(time.time()) - LADDER_NAME_TTL_SEC
        for i in range(0, len(puuids), 500):
            chunk = puuids[i:i + 500]
            for p, gn, tag in conn.execute(
                    f"SELECT puuid, game_name, tag_line FROM ladder_names WHERE checked_at >= ? AND puuid IN ({','.join('?' * len(chunk))})",
                    (since, *chunk)).fetchall():
                out[p] = {"gameName": gn, "tagLine": tag}
        return out
    finally:
        conn.close()


def _remember_ladder_names(rows: List[Dict[str, Any]]) -> None:
    now = int(time.time())
    conn = get_connection()
    try:
        conn.executemany("INSERT OR REPLACE INTO ladder_names (puuid, game_name, tag_line, checked_at) VALUES (?, ?, ?, ?)",
                         [(r["puuid"], r["gameName"], r["tagLine"], now) for r in rows])
        conn.commit()
    finally:
        conn.close()


def load_ladder(query: str = "") -> Dict[str, Any]:
    init_ladder_table()
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM ladder_real ORDER BY rank").fetchall()]
    conn.close()
    q = query.strip().lower()
    results = []
    for r in rows:
        if q and q not in r["game_name"].lower() and q not in r["tag_line"].lower():
            continue
        total = r["wins"] + r["losses"]
        results.append({
            **r,
            "tier_kr": "챌린저",
            "total_games": total,
            "win_rate": round(r["wins"] / total * 100, 1) if total else 0,
        })
    return {"results": results, "updated_at": rows[0]["updated_at"] if rows else None}


async def sync_challenger_ladder(top_n: int = LADDER_NAMED_TOP_N) -> Dict[str, Any]:
    """라이엇 챌린저 리그 상위 top_n 명의 실제 순위·LP·승패·닉네임을 저장한다."""
    if not settings.riot_api_key:
        raise PlayerDataUnavailable(503, "라이엇 API 키가 등록되지 않아 랭킹을 갱신할 수 없습니다.")
    try:
        league = await riot_client.get_apex_league("CHALLENGER")
    except RiotAPIError as e:
        raise _riot_error(e)

    entries = sorted(league.get("entries", []), key=lambda e: e.get("leaguePoints", 0), reverse=True)[:top_n]
    sem = asyncio.Semaphore(MATCH_FETCH_CONCURRENCY)
    init_ladder_table()
    known = _cached_ladder_names([e["puuid"] for e in entries if e.get("puuid")])
    looked_up: List[Dict[str, Any]] = []

    async def resolve(rank: int, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if entry.get("puuid") in known:  # 7일 안에 확인한 이름은 다시 묻지 않는다
            return {**entry, "rank": rank, **known[entry["puuid"]]}
        async with sem:
            try:
                # 리그 엔트리에 puuid가 없으면(구 스키마) summonerId 로 소환사를 조회해 puuid를 얻는다
                puuid = entry.get("puuid")
                if not puuid and entry.get("summonerId"):
                    summoner = await riot_client.get_summoner_by_id(entry["summonerId"])
                    puuid = (summoner or {}).get("puuid")
                if not puuid:
                    return None
                account = await riot_client.get_account_by_puuid(puuid)
            except RiotAPIError:
                return None
        if not account or not account.get("gameName"):
            return None  # 이름을 확인하지 못한 항목은 다른 이름으로 채우지 않고 제외
        row = {**entry, "puuid": puuid, "rank": rank, "gameName": account["gameName"], "tagLine": account.get("tagLine", "")}
        looked_up.append(row)
        return row

    resolved = [r for r in await asyncio.gather(*(resolve(i + 1, e) for i, e in enumerate(entries))) if r]
    if looked_up:
        _remember_ladder_names(looked_up)
    if not resolved:
        raise PlayerDataUnavailable(503, "챌린저 랭킹 닉네임을 확인하지 못했습니다. 잠시 후 다시 시도해주세요.")

    now = int(time.time())
    init_ladder_table()
    conn = get_connection()
    conn.execute("DELETE FROM ladder_real")
    conn.executemany(
        "INSERT INTO ladder_real (rank, puuid, game_name, tag_line, tier, league_points, wins, losses, updated_at) "
        "VALUES (?, ?, ?, ?, 'CHALLENGER', ?, ?, ?, ?)",
        [
            (r["rank"], r["puuid"], r["gameName"], r["tagLine"], r.get("leaguePoints", 0), r.get("wins", 0), r.get("losses", 0), now)
            for r in resolved
        ],
    )
    conn.commit()
    conn.close()
    # 래더 갱신(하루 1회)에서 받은 LP로 티어 변동 기록을 쌓는다 (추가 호출 없음)
    from app.tier_utils import calculate_tier_score
    for r in resolved:
        lp = int(r.get("leaguePoints", 0))
        try:
            record_rank_snapshot({
                "puuid": r["puuid"], "tier": "CHALLENGER", "rank_tier": "I", "league_points": lp,
                "wins": r.get("wins", 0), "losses": r.get("losses", 0),
                "tier_score": calculate_tier_score("CHALLENGER", "I", lp),
            }, captured_at=now)
        except Exception as e:
            logger.warning("Ladder rank snapshot failed for %s: %s", r["puuid"], e)
    return {"status": "success", "synced_count": len(resolved), "skipped": len(entries) - len(resolved)}


async def get_recent_matches_payload(player: Dict[str, Any], count: int = 20) -> Dict[str, Any]:
    raw = await fetch_recent_matches(player["puuid"], count=count)
    matches = [m for m in (convert_match(r, player["puuid"]) for r in raw) if m]
    return {"source": "riot_api", "summary": summarize_matches(matches), "matches": matches}


# ---------------------------------------------------------------------------
# 실제 챔피언 숙련도 및 장인 랭킹 (Champion-Mastery-V4)
# ---------------------------------------------------------------------------

def init_champion_mastery_table() -> None:
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS champion_mastery_real (
            puuid TEXT NOT NULL,
            champion_id INTEGER NOT NULL,
            champion_points INTEGER NOT NULL,
            champion_level INTEGER NOT NULL,
            last_play_time INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (puuid, champion_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_champion_mastery_champ_pts "
        "ON champion_mastery_real(champion_id, champion_points DESC)"
    )
    conn.commit()
    conn.close()


def get_mastery_updated_at(puuid: str) -> Optional[int]:
    init_champion_mastery_table()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(updated_at) FROM champion_mastery_real WHERE puuid = ?",
            (puuid,)
        ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return None
    finally:
        conn.close()


async def refresh_masteries(puuid: str) -> None:
    if not is_riot_puuid(puuid):
        return
    masteries = await riot_client.get_champion_masteries_by_puuid(puuid, 10)
    now = int(time.time())
    init_champion_mastery_table()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM champion_mastery_real WHERE puuid = ?", (puuid,))
        if masteries:
            rows = [
                (
                    puuid,
                    int(m["championId"]),
                    int(m["championPoints"]),
                    int(m.get("championLevel", 0)),
                    int(m.get("lastPlayTime", 0)),
                    now,
                )
                for m in masteries
                if "championId" in m and "championPoints" in m
            ]
            if rows:
                conn.executemany(
                    "INSERT INTO champion_mastery_real "
                    "(puuid, champion_id, champion_points, champion_level, last_play_time, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    rows,
                )
        conn.commit()
    finally:
        conn.close()


async def sync_ladder_masteries() -> Dict[str, int]:
    init_ladder_table()
    init_champion_mastery_table()
    conn = get_connection()
    try:
        rows = conn.execute("SELECT puuid FROM ladder_real ORDER BY rank ASC LIMIT ?", (LADDER_MASTERY_TOP_N,)).fetchall()
    finally:
        conn.close()

    refreshed = 0
    skipped = 0
    now = time.time()

    for r in rows:
        puuid = r["puuid"] if isinstance(r, dict) or hasattr(r, "__getitem__") else r[0]
        if not is_riot_puuid(puuid):
            skipped += 1
            continue

        last_up = get_mastery_updated_at(puuid)
        if last_up is not None and (now - last_up < 86400):
            skipped += 1
            continue

        try:
            await refresh_masteries(puuid)
            refreshed += 1
        except RiotAPIError as e:
            if getattr(e, "status_code", None) in (401, 403, 429):
                logger.warning("sync_ladder_masteries stopped due to RiotAPIError(%s): %s", e.status_code, e)
                break
            raise
        except Exception as e:
            logger.warning("Failed to refresh masteries for ladder puuid %s: %s", puuid, e)

    return {"refreshed": refreshed, "skipped": skipped}


def load_champion_masters(champion_id: int, limit: int = 100) -> Dict[str, Any]:
    init_champion_mastery_table()
    init_ladder_table()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT puuid, champion_points, champion_level, last_play_time "
            "FROM champion_mastery_real "
            "WHERE champion_id = ? "
            "ORDER BY champion_points DESC",
            (int(champion_id),)
        )
        rows = cur.fetchall()
        if not rows:
            return {"results": [], "count": 0}

        results: List[Dict[str, Any]] = []
        rank = 1

        for r in rows:
            puuid = r["puuid"]
            if not is_riot_puuid(puuid):
                continue

            # 1. players 테이블 확인 (같은 puuid, is_riot_puuid)
            p_cur = conn.execute(
                "SELECT game_name, tag_line, tier, rank_tier, league_points, profile_icon_id, summoner_level "
                "FROM players WHERE puuid = ? LIMIT 1",
                (puuid,)
            )
            p_row = p_cur.fetchone()

            if p_row and is_riot_puuid(puuid):
                results.append({
                    "rank": rank,
                    "puuid": puuid,
                    "game_name": p_row["game_name"],
                    "tag_line": p_row["tag_line"],
                    "tier": p_row["tier"],
                    "rank_tier": p_row["rank_tier"] or "",
                    "league_points": int(p_row["league_points"] or 0),
                    "profile_icon_id": p_row["profile_icon_id"],
                    "summoner_level": p_row["summoner_level"],
                    "mastery_points": int(r["champion_points"]),
                    "mastery_level": int(r["champion_level"]),
                    "last_play_time": int(r["last_play_time"]),
                })
                rank += 1
            else:
                # 2. ladder_real 확인 (이름·LP, 티어는 CHALLENGER)
                l_cur = conn.execute(
                    "SELECT game_name, tag_line, league_points "
                    "FROM ladder_real WHERE puuid = ? LIMIT 1",
                    (puuid,)
                )
                l_row = l_cur.fetchone()
                if l_row:
                    results.append({
                        "rank": rank,
                        "puuid": puuid,
                        "game_name": l_row["game_name"],
                        "tag_line": l_row["tag_line"],
                        "tier": "CHALLENGER",
                        "rank_tier": "",
                        "league_points": int(l_row["league_points"] or 0),
                        "profile_icon_id": None,
                        "summoner_level": None,
                        "mastery_points": int(r["champion_points"]),
                        "mastery_level": int(r["champion_level"]),
                        "last_play_time": int(r["last_play_time"]),
                    })
                    rank += 1
                else:
                    # 둘 다 없으면 제외 (이름을 지어내지 않음)
                    continue

            if len(results) >= limit:
                break

        return {"results": results, "count": len(results)}
    finally:
        conn.close()
