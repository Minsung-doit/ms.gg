"""
디스코드 서버 랭킹 (app/community_rank.py)

멤버가 디스코드 로그인 후 자기 라이엇 ID를 연결하면, 연결된 계정들을 솔로랭크 티어·LP 순으로 보여준다.
- 연결할 때 라이엇에서 실제 계정을 확인한다(없는 ID는 연결 불가).
- 하루 한 번 연결된 계정의 랭크를 다시 받아 온다(멤버 1명당 3~4회 호출, 5초 간격).
- 7일 LP 변화는 rank_snapshots(실제 기록)에서 계산한다.
- 같이 한 게임: 캐시된 실제 매치(match_cache)에서 멤버 둘 이상이 같은 팀이었던 게임.
  (2026-10-28 사용자 결정) 하루 한 번 랭크 갱신 때 인증 멤버의 최근 30일 솔로·자유랭크 매치도 받아 둔다
  (멤버 1명당 목록 2회 + 캐시에 없는 매치만, 1명당 최대 MEMBER_MATCH_LIMIT 개). MEMBER_MATCH_FETCH=0 이면 끔.
- 이번 주 MVP: 7일 LP 변화가 가장 큰 멤버. 웹후크가 있으면 일주일에 한 번 디스코드에 알린다.
"""
import json
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from app.database import get_connection, get_player_by_riot_id, is_riot_puuid
from app.tier_utils import TIER_NAMES_KR, calculate_tier_score

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SEC = 86400
REFRESH_GAP_SEC = 5
MEMBER_MATCH_QUEUES = (420, 440)  # 솔로랭크, 자유랭크
MEMBER_MATCH_LIMIT = 20  # 큐마다 최근 몇 판까지
MEMBER_MATCH_GAP_SEC = 1.5
_initialized = set()


def _ensure_tables() -> None:
    from app import database
    key = str(database.DB_PATH)
    if key in _initialized:
        return
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS member_accounts (
                discord_id TEXT PRIMARY KEY,
                discord_name TEXT DEFAULT '',
                puuid TEXT,
                game_name TEXT,
                tag_line TEXT,
                linked_at INTEGER
            )
        """)
        # verified: 라이엇 공식 로그인(RSO)으로 본인 계정임을 확인했으면 1. 0 인 행(예전 닉네임 입력 연결)은 어디에도 쓰지 않는다
        cols = {r[1] for r in conn.execute("PRAGMA table_info(member_accounts)")}
        if "verified" not in cols:
            conn.execute("ALTER TABLE member_accounts ADD COLUMN verified INTEGER DEFAULT 0")
        # 멤버가 들어가 있는 디스코드 서버 (여러 서버 지원, app/communities.py). 행이 없는 예전 멤버는 기본 서버
        conn.execute("CREATE TABLE IF NOT EXISTS member_guilds (discord_id TEXT, guild_id TEXT, PRIMARY KEY (discord_id, guild_id))")
        conn.commit()
    finally:
        conn.close()
    _initialized.add(key)


def remember_member(discord_id: str, discord_name: str) -> None:
    """디스코드 로그인 때 표시 이름을 저장 (랭킹에서 '누구 계정인지' 보여주기용)"""
    _ensure_tables()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO member_accounts (discord_id, discord_name) VALUES (?, ?) "
            "ON CONFLICT(discord_id) DO UPDATE SET discord_name = excluded.discord_name",
            (discord_id, (discord_name or "")[:40]),
        )
        conn.commit()
    finally:
        conn.close()


def set_member_guilds(discord_id: str, guild_ids: List[str]) -> None:
    """디스코드 로그인 때 확인한 서버 목록으로 바꾼다"""
    _ensure_tables()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM member_guilds WHERE discord_id = ?", (discord_id,))
        conn.executemany("INSERT OR IGNORE INTO member_guilds (discord_id, guild_id) VALUES (?, ?)",
                         [(discord_id, g) for g in guild_ids if g])
        conn.commit()
    finally:
        conn.close()


def add_member_guild(discord_id: str, guild_id: str) -> None:
    """봇 명령을 그 서버에서 쓴 멤버 = 그 서버 멤버"""
    if not guild_id:
        return
    _ensure_tables()
    conn = get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO member_guilds (discord_id, guild_id) VALUES (?, ?)", (discord_id, guild_id))
        conn.commit()
    finally:
        conn.close()


def guilds_of(discord_id: str) -> List[str]:
    _ensure_tables()
    conn = get_connection()
    try:
        return [r[0] for r in conn.execute("SELECT guild_id FROM member_guilds WHERE discord_id = ?", (discord_id,)).fetchall()]
    finally:
        conn.close()


def _guild_filter(guild_id: str) -> tuple:
    """member_accounts 를 그 서버 멤버로 거르는 SQL 조각. 서버 설정이 없으면 거르지 않는다"""
    from app import communities
    if not communities.ids():
        return "", ()
    gid = guild_id or communities.default_id()
    sql = " AND (discord_id IN (SELECT discord_id FROM member_guilds WHERE guild_id = ?)"
    if gid == communities.default_id():
        sql += " OR discord_id NOT IN (SELECT discord_id FROM member_guilds)"
    return sql + ")", (gid,)


def get_member(discord_id: str) -> Optional[Dict[str, Any]]:
    _ensure_tables()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM member_accounts WHERE discord_id = ?", (discord_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def link_account(discord_id: str, player: Dict[str, Any]) -> None:
    """라이엇 공식 로그인으로 본인임이 확인된 계정만 연결한다 (닉네임 입력 연결은 없음)"""
    _ensure_tables()
    conn = get_connection()
    try:
        # 한 계정은 한 멤버에게만: 같은 계정을 이전에 다른 디스코드 멤버가 인증해 두었으면 그 연결을 푼다
        conn.execute("UPDATE member_accounts SET puuid = NULL, game_name = NULL, tag_line = NULL, linked_at = NULL, "
                     "verified = 0 WHERE puuid = ? AND discord_id != ?", (player["puuid"], discord_id))
        conn.execute(
            "INSERT INTO member_accounts (discord_id, puuid, game_name, tag_line, linked_at, verified) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(discord_id) DO UPDATE SET puuid = excluded.puuid, game_name = excluded.game_name, "
            "tag_line = excluded.tag_line, linked_at = excluded.linked_at, verified = excluded.verified",
            (discord_id, player["puuid"], player["game_name"], player["tag_line"], int(time.time()), 1),
        )
        conn.commit()
    finally:
        conn.close()


def register_account(discord_id: str, player: Dict[str, Any]) -> str:
    """닉네임 등록 (라이엇에 있는 계정인지만 확인, 본인 인증 아님 → verified=0).
    티어 역할·내전 팀 나누기에는 쓰고, 서버 랭킹·내전 순위에는 올리지 않는다 (2026-10-28 사용자 결정).
    반환: ok / verified_already (이미 라이엇 인증 계정이 있음) / taken (다른 멤버가 인증한 계정)"""
    _ensure_tables()
    conn = get_connection()
    try:
        mine = conn.execute("SELECT verified FROM member_accounts WHERE discord_id = ?", (discord_id,)).fetchone()
        if mine and mine[0]:
            return "verified_already"
        other = conn.execute("SELECT 1 FROM member_accounts WHERE puuid = ? AND verified = 1 AND discord_id != ?",
                             (player["puuid"], discord_id)).fetchone()
        if other:
            return "taken"
        conn.execute(
            "INSERT INTO member_accounts (discord_id, puuid, game_name, tag_line, linked_at, verified) VALUES (?, ?, ?, ?, ?, 0) "
            "ON CONFLICT(discord_id) DO UPDATE SET puuid = excluded.puuid, game_name = excluded.game_name, "
            "tag_line = excluded.tag_line, linked_at = excluded.linked_at, verified = 0",
            (discord_id, player["puuid"], player["game_name"], player["tag_line"], int(time.time())),
        )
        conn.commit()
        return "ok"
    finally:
        conn.close()


def unlink_account(discord_id: str) -> None:
    _ensure_tables()
    conn = get_connection()
    try:
        conn.execute("UPDATE member_accounts SET puuid = NULL, game_name = NULL, tag_line = NULL, linked_at = NULL, "
                     "verified = 0 WHERE discord_id = ?", (discord_id,))
        conn.commit()
    finally:
        conn.close()


def _lp_change_7d(conn, puuid: str, current_score: int) -> Optional[int]:
    """7일 전(또는 그 뒤 첫) 기록 대비 티어 점수 변화. 점수는 티어·디비전·LP를 합친 값이라 같은 디비전 안에서는 LP 변화와 같다."""
    row = conn.execute(
        "SELECT tier_score FROM rank_snapshots WHERE puuid = ? AND captured_at >= ? ORDER BY captured_at ASC LIMIT 1",
        (puuid, int(time.time()) - 7 * 86400),
    ).fetchone()
    if not row or row[0] is None:
        return None
    return int(current_score) - int(row[0])


def leaderboard(guild_id: str = "") -> Dict[str, Any]:
    """라이엇 공식 로그인(RSO)으로 인증한 계정만 순위에 올린다 (그 디스코드 서버 멤버만)"""
    _ensure_tables()
    where, args = _guild_filter(guild_id)
    conn = get_connection()
    try:
        members = [dict(r) for r in conn.execute(
            "SELECT discord_id, discord_name, puuid, game_name, tag_line, linked_at, verified FROM member_accounts "
            "WHERE puuid IS NOT NULL AND verified = 1" + where, args).fetchall()]
        rows: List[Dict[str, Any]] = []
        for m in members:
            p = get_player_by_riot_id(m["game_name"], m["tag_line"]) or {}
            if p.get("puuid") and p.get("puuid") != m["puuid"]:
                p = {}
            tier = (p.get("tier") or "UNRANKED").upper()
            score = calculate_tier_score(tier, p.get("rank_tier") or "", int(p.get("league_points") or 0)) if tier != "UNRANKED" else -1
            wins, losses = int(p.get("wins") or 0), int(p.get("losses") or 0)
            rows.append({
                "discord_name": m["discord_name"] or "",
                "game_name": m["game_name"],
                "tag_line": m["tag_line"],
                "verified": bool(m.get("verified")),
                "profile_icon_id": p.get("profile_icon_id"),
                "summoner_level": p.get("summoner_level"),
                "tier": tier,
                "rank_tier": p.get("rank_tier") or "",
                "display_tier": p.get("display_tier") or ("언랭크" if tier == "UNRANKED" else tier),
                "league_points": int(p.get("league_points") or 0),
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / (wins + losses) * 100, 1) if wins + losses else None,
                "lp_change_7d": _lp_change_7d(conn, m["puuid"], score) if score >= 0 else None,
                "score": score,
                "updated_at": p.get("last_updated") or p.get("updated_at"),
            })
    finally:
        conn.close()
    rows.sort(key=lambda r: (r["score"], r["wins"]), reverse=True)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
        r.pop("score", None)
    return {"members": rows, "total": len(rows)}


APEX_TIERS = ("MASTER", "GRANDMASTER", "CHALLENGER")


def _tier_label(tier: str, rank: str) -> str:
    t = (tier or "UNRANKED").upper()
    name = TIER_NAMES_KR.get(t, t)
    return name if t in APEX_TIERS or t == "UNRANKED" else f"{name} {rank or ''}".strip()


def _division_key(tier: str, rank: str) -> int:
    """승급 판단용: 티어·디비전만 (LP 제외). 언랭크는 -1"""
    t = (tier or "UNRANKED").upper()
    if t == "UNRANKED":
        return -1
    return calculate_tier_score(t, "" if t in APEX_TIERS else (rank or ""), 0)


def rank_up_message(discord_name: str, game_name: str, tag_line: str,
                    old: Dict[str, Any], new: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """티어·디비전이 올랐으면 디스코드 웹후크 임베드, 아니면 None (같은 디비전 안 LP 변화는 알리지 않음)"""
    before = _division_key(old.get("tier"), old.get("rank_tier"))
    after = _division_key(new.get("tier"), new.get("rank_tier"))
    if after <= before:
        return None
    who = f"{discord_name} ({game_name}#{tag_line})" if discord_name else f"{game_name}#{tag_line}"
    old_label = _tier_label(old.get("tier"), old.get("rank_tier"))
    new_label = _tier_label(new.get("tier"), new.get("rank_tier"))
    text = (f"**{who}** 님이 **{new_label}** 배치를 받았습니다!" if before < 0
            else f"**{who}** 님이 **{old_label} → {new_label}** 로 승급했습니다!")
    return {"embeds": [{"title": "🎉 승급 축하!", "description": text, "color": 0x10B981}]}


async def cache_member_matches(puuid: str) -> int:
    """멤버의 최근 30일 솔로·자유랭크 매치 중 캐시에 없는 것만 받아 둔다 (같이 한 게임 계산용). 받은 개수"""
    from app.real_data import _load_cached_matches, _store_matches
    from app.riot_client import riot_client
    since = int(time.time()) - DUO_LOOKBACK_DAYS * 86400
    ids: List[str] = []
    for queue in MEMBER_MATCH_QUEUES:
        ids += await riot_client.get_match_ids_by_puuid(puuid, count=MEMBER_MATCH_LIMIT, queue=queue, start_time=since)
    cached = _load_cached_matches(ids)
    got = 0
    for mid in ids:
        if mid in cached:
            continue
        match = await riot_client.get_match_detail(mid)
        if match and match.get("info"):
            _store_matches([match])
            got += 1
        await asyncio.sleep(MEMBER_MATCH_GAP_SEC)
    return got


async def refresh_linked_accounts() -> int:
    """연결된 계정 랭크 갱신 (실제 라이엇 조회). 실패한 계정은 기존 값 유지."""
    from app.real_data import fetch_player, PlayerDataUnavailable
    from app.riot_client import RiotAPIError
    _ensure_tables()
    conn = get_connection()
    try:
        targets = [tuple(r) for r in conn.execute(
            "SELECT game_name, tag_line, discord_name, discord_id, puuid, verified FROM member_accounts WHERE puuid IS NOT NULL").fetchall()]
    finally:
        conn.close()
    from app import communities
    announce = os.getenv("RANKUP_ANNOUNCE", "1").strip() != "0"
    fetch_matches = os.getenv("MEMBER_MATCH_FETCH", "1").strip() != "0"
    done = new_matches = 0
    for name, tag, discord_name, discord_id, puuid, verified in targets:
        try:
            old = get_player_by_riot_id(name, tag) or {}
            new = await fetch_player(name, tag, allow_cached=False)
            done += 1
            msg = rank_up_message(discord_name or "", name, tag, old, new) if announce and old and verified else None
            if msg:
                # 그 멤버가 들어가 있는 서버마다 그 서버 채널에 알린다
                from app.services.discord_service import send_discord_webhook
                for gid in communities.member_guilds(discord_id) or [""]:
                    hook = communities.webhook_url(gid)
                    if hook:
                        await asyncio.to_thread(send_discord_webhook, msg, hook)
        except PlayerDataUnavailable as e:
            if e.status_code in (429, 503):
                break  # 한도·키 문제면 다음 주기에
        except Exception as e:
            logger.warning("member refresh failed: %s", type(e).__name__)
        # 최근 게임은 등록 멤버까지 (내전 팀 짜기의 최근 퍼포먼스·라인, 2026-10-28 사용자 승인)
        if fetch_matches and is_riot_puuid(puuid):
            try:
                new_matches += await cache_member_matches(puuid)
            except RiotAPIError as e:
                if e.status_code in (401, 403, 429):
                    break
            except Exception as e:
                logger.warning("member match fetch failed: %s", type(e).__name__)
        await asyncio.sleep(REFRESH_GAP_SEC)
    if new_matches:
        _DUO_MEMO.clear()  # 같이 한 게임 다시 계산
        logger.info("Server ranking: cached %s new member matches", new_matches)
    return done


async def refresh_loop() -> None:
    while True:
        try:
            n = await refresh_linked_accounts()
            if n:
                logger.info("Server ranking: refreshed %s linked accounts", n)
        except Exception as e:
            logger.warning("Server ranking refresh failed: %s", e)
        try:
            await asyncio.to_thread(post_weekly_mvp_if_due)
        except Exception as e:
            logger.warning("Weekly MVP post failed: %s", e)
        await asyncio.sleep(REFRESH_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# 같이 한 게임 (멤버 듀오)
# ---------------------------------------------------------------------------
DUO_LOOKBACK_DAYS = 30
_DUO_MEMO: Dict[str, Dict[str, Any]] = {}


def _linked_members(guild_id: str = "") -> Dict[str, Dict[str, Any]]:
    _ensure_tables()
    where, args = _guild_filter(guild_id)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT puuid, discord_name, game_name, tag_line FROM member_accounts WHERE puuid IS NOT NULL AND verified = 1" + where,
            args).fetchall()
    finally:
        conn.close()
    return {r[0]: {"discord_name": r[1] or "", "game_name": r[2], "tag_line": r[3]} for r in rows}


def member_tiers(discord_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """디스코드 ID → 등록·인증한 계정의 저장된 솔로랭크 (내전 팀 나누기용, 라이엇 호출 없음, 등록 안 했으면 빠짐)"""
    _ensure_tables()
    ids = [str(i) for i in discord_ids if str(i).isdigit()][:20]
    if not ids:
        return {}
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT discord_id, puuid, game_name, tag_line FROM member_accounts WHERE puuid IS NOT NULL "
            f"AND discord_id IN ({','.join('?' * len(ids))})", ids).fetchall()
    finally:
        conn.close()
    out: Dict[str, Dict[str, Any]] = {}
    for did, puuid, gn, tag in rows:
        p = get_player_by_riot_id(gn, tag) or {}
        if p.get("puuid") and p.get("puuid") != puuid:
            p = {}
        out[str(did)] = {"game_name": gn, "tag_line": tag, "tier": (p.get("tier") or "UNRANKED").upper(),
                         "rank": p.get("rank_tier") or "", "lp": int(p.get("league_points") or 0)}
    return out


def inhouse_members(guild_id: str = "") -> List[Dict[str, Any]]:
    """내전 참가자 고르기용: 그 서버에서 닉네임을 등록했거나 라이엇 인증한 멤버 (저장된 솔로랭크, 라이엇 호출 없음).
    랭킹이 아니라서 미인증(닉네임 등록) 멤버도 넣고 verified 로 구분한다"""
    _ensure_tables()
    where, args = _guild_filter(guild_id)
    conn = get_connection()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT discord_id, discord_name, puuid, game_name, tag_line, verified FROM member_accounts "
            "WHERE puuid IS NOT NULL" + where, args).fetchall()]
    finally:
        conn.close()
    out = []
    for m in rows:
        p = get_player_by_riot_id(m["game_name"], m["tag_line"]) or {}
        if p.get("puuid") and p.get("puuid") != m["puuid"]:
            p = {}
        tier = (p.get("tier") or "UNRANKED").upper()
        out.append({
            "discord_id": m["discord_id"] if str(m["discord_id"]).isdigit() else None,
            "discord_name": m["discord_name"] or "",
            "game_name": m["game_name"], "tag_line": m["tag_line"], "verified": bool(m["verified"]),
            "tier": tier, "rank_tier": p.get("rank_tier") or "", "league_points": int(p.get("league_points") or 0),
            "display_tier": p.get("display_tier") or ("언랭크" if tier == "UNRANKED" else tier),
            "score": calculate_tier_score(tier, p.get("rank_tier") or "", int(p.get("league_points") or 0)) if tier != "UNRANKED" else -1,
        })
    out.sort(key=lambda r: r.pop("score"), reverse=True)
    return out


def guild_member_tiers(guild_id: str = "") -> List[Dict[str, Any]]:
    """티어 역할 자동 부여용: 그 서버 멤버마다 등록·인증한 계정의 솔로랭크 티어 (등록 안 했거나 언랭크면 None → 티어 역할을 뗀다)"""
    _ensure_tables()
    where, args = _guild_filter(guild_id)
    conn = get_connection()
    try:
        rows = conn.execute("SELECT discord_id, puuid, game_name, tag_line, verified FROM member_accounts WHERE 1 = 1" + where,
                            args).fetchall()
    finally:
        conn.close()
    out = []
    for did, puuid, gn, tag, verified in rows:
        tier = None
        if puuid and str(did).isdigit():
            p = get_player_by_riot_id(gn, tag) or {}
            if not p.get("puuid") or p.get("puuid") == puuid:
                t = (p.get("tier") or "").upper()
                tier = t if t in TIER_NAMES_KR and t != "UNRANKED" else None
        if str(did).isdigit():
            out.append({"discord_id": str(did), "tier": tier})
    return out


def server_duos(limit: int = 20, guild_id: str = "") -> Dict[str, Any]:
    """최근 30일 캐시된 솔로·자유랭크 게임에서 같은 팀이었던 멤버 쌍의 판수·승률 (서버별 10분 메모)"""
    memo = _DUO_MEMO.get(guild_id)
    if memo and time.time() - memo["at"] < 600:
        return memo["data"]
    members = _linked_members(guild_id)
    pairs: Dict[tuple, Dict[str, int]] = {}
    if len(members) >= 2:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT data FROM match_cache WHERE game_end >= ?",
                (int((time.time() - DUO_LOOKBACK_DAYS * 86400) * 1000),),
            ).fetchall()
        except Exception:
            rows = []
        finally:
            conn.close()
        member_set = set(members)
        for (raw,) in rows:
            # 멤버가 한 명도 없는 게임은 파싱하지 않는다
            if not raw or not any(pu in raw for pu in member_set):
                continue
            try:
                info = (json.loads(raw).get("info") or {})
            except Exception:
                continue
            if info.get("queueId") not in (420, 440):
                continue
            by_team: Dict[Any, List[Dict[str, Any]]] = {}
            for p in info.get("participants") or []:
                if p.get("puuid") in member_set:
                    by_team.setdefault(p.get("teamId"), []).append(p)
            for team in by_team.values():
                team.sort(key=lambda p: p["puuid"])
                for i in range(len(team)):
                    for j in range(i + 1, len(team)):
                        st = pairs.setdefault((team[i]["puuid"], team[j]["puuid"]), {"games": 0, "wins": 0})
                        st["games"] += 1
                        st["wins"] += 1 if team[i].get("win") else 0
    rows_out = []
    for (a, b), st in sorted(pairs.items(), key=lambda kv: (-kv[1]["games"], -kv[1]["wins"]))[:limit]:
        rows_out.append({
            "a": members[a], "b": members[b],
            "games": st["games"], "wins": st["wins"],
            "win_rate": round(st["wins"] / st["games"] * 100, 1),
        })
    data = {"duos": rows_out, "days": DUO_LOOKBACK_DAYS}
    _DUO_MEMO[guild_id] = {"at": time.time(), "data": data}
    return data


# ---------------------------------------------------------------------------
# 이번 주 MVP
# ---------------------------------------------------------------------------
MVP_INTERVAL_SEC = 7 * 86400


def weekly_mvp(guild_id: str = "") -> Optional[Dict[str, Any]]:
    """7일 LP 변화가 가장 큰(양수) 멤버"""
    best = None
    for m in leaderboard(guild_id)["members"]:
        d = m.get("lp_change_7d")
        if d is not None and d > 0 and (best is None or d > best["lp_change_7d"]):
            best = m
    return best


def weekly_inhouse_king(min_games: int = 3, guild_id: str = "") -> Optional[Dict[str, Any]]:
    """최근 7일 내전에서 3판 이상 하고 가장 많이 이긴 사람 (기록이 없으면 None)"""
    from app import inhouse
    best = [p for p in inhouse.stats(days=7, recent=1, guild_id=guild_id)["players"] if p["games"] >= min_games and p["wins"] > 0]
    return best[0] if best else None


def post_weekly_mvp_if_due() -> bool:
    """서버마다: 웹후크가 설정돼 있고 지난 게시 후 7일이 지났으면 MVP를 그 서버 채널에 올린다"""
    if os.getenv("WEEKLY_MVP_ANNOUNCE", "1").strip() == "0":
        return False
    from app import communities
    posted = False
    for gid in communities.ids() or [""]:
        hook = communities.webhook_url(gid)
        if hook and _post_weekly_mvp(gid, hook):
            posted = True
    return posted


def _post_weekly_mvp(guild_id: str, hook: str) -> bool:
    # 예전(서버 하나) 기록 키는 기본 서버가 이어 쓴다
    from app import communities
    key = "mvp_posted_at" if not guild_id or guild_id == communities.default_id() else f"mvp_posted_at:{guild_id}"
    _ensure_tables()
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS community_state (key TEXT PRIMARY KEY, value TEXT)")
        row = conn.execute("SELECT value FROM community_state WHERE key = ?", (key,)).fetchone()
        last = int(row[0]) if row and str(row[0]).isdigit() else 0
        if time.time() - last < MVP_INTERVAL_SEC:
            return False
        mvp = weekly_mvp(guild_id)
        king = weekly_inhouse_king(guild_id=guild_id)
        if not mvp and not king:
            return False
        from app.services.discord_service import send_discord_webhook, _md_label
        embeds = []
        if mvp:
            name = mvp.get("discord_name") or mvp["game_name"]
            text = (f"**{name}** ({mvp['game_name']}#{mvp['tag_line']})\n"
                    f"{mvp['display_tier']} {mvp['league_points']}LP · 7일간 +{mvp['lp_change_7d']}")
            embeds.append({"title": "🏆 이번 주 서버 MVP", "description": text, "color": 0xF59E0B})
        if king:
            embeds.append({"title": "⚔️ 이번 주 내전 왕", "color": 0x5865F2,
                           "description": f"**{_md_label(king['name'])}** {king['wins']}승 {king['losses']}패 ({king['win_rate']}%)"})
        send_discord_webhook({"embeds": embeds}, hook)
        conn.execute("INSERT OR REPLACE INTO community_state (key, value) VALUES (?, ?)", (key, str(int(time.time()))))
        conn.commit()
        return True
    finally:
        conn.close()


def is_linkable(player: Dict[str, Any]) -> bool:
    return bool(player) and is_riot_puuid(player.get("puuid"))
