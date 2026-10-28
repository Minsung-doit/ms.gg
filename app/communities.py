"""
여러 디스코드 서버 (app/communities.py)

한 사이트·한 봇으로 디스코드 서버 여러 곳을 받는다. 구인글·내전·서버 랭킹은 서버마다 따로 보인다.
- COMMUNITY_GUILDS=서버ID:이름,서버ID:이름  (없으면 예전처럼 DISCORD_GUILD_ID + COMMUNITY_NAME 한 곳)
- 첫 서버가 '기본 서버'. 서버 구분이 없던 예전 글·내전·멤버는 기본 서버 것으로 본다.
- 채널 알림은 서버마다: DISCORD_WEBHOOK_URL_<서버ID> (게임별 DISCORD_WEBHOOK_URL_<서버ID>_PUBG),
  알림 역할은 DUO_ALERT_ROLES_<서버ID>. 기본 서버만 예전 이름(DISCORD_WEBHOOK_URL, DUO_ALERT_ROLES)도 쓴다.
  다른 서버 글이 기본 서버 채널로 새지 않게, 기본 서버가 아니면 예전 이름으로 대신하지 않는다.
- 서버가 하나도 설정되지 않았으면(로컬 개발) 서버 구분 없이 모두 한곳 ("") 으로 처리한다.
"""
import os
from typing import Dict, List, Optional

from fastapi import Request

CURRENT_COOKIE = "community"


def _env(key: str) -> str:
    return os.getenv(key, "").strip()


def configured() -> List[Dict[str, str]]:
    """[{'id': 서버ID, 'name': 이름}] (설정 순서 그대로, 첫 번째가 기본 서버)"""
    out: List[Dict[str, str]] = []
    raw = _env("COMMUNITY_GUILDS")
    if raw:
        for part in raw.split(","):
            gid, _, name = part.strip().partition(":")
            gid = gid.strip()
            if gid.isdigit() and all(c["id"] != gid for c in out):
                out.append({"id": gid, "name": name.strip()[:30]})
    elif _env("DISCORD_GUILD_ID").isdigit():
        out.append({"id": _env("DISCORD_GUILD_ID"), "name": _env("COMMUNITY_NAME")[:30]})
    return out


def ids() -> List[str]:
    return [c["id"] for c in configured()]


def default_id() -> str:
    all_ids = ids()
    return all_ids[0] if all_ids else ""


def name_of(guild_id: str) -> str:
    for c in configured():
        if c["id"] == guild_id:
            return c["name"]
    return _env("COMMUNITY_NAME")[:30] if not ids() else ""


def resolve(guild_id: Optional[str]) -> Optional[str]:
    """봇·요청이 알려 준 서버 ID → 저장할 서버 ID. 설정이 없으면 "", 등록되지 않은 서버면 None"""
    all_ids = ids()
    if not all_ids:
        return ""
    gid = str(guild_id or "").strip()
    return gid if gid in all_ids else None


def same(row_guild: Optional[str], current: str) -> bool:
    """저장된 서버 값(예전 값은 비어 있음)이 지금 서버와 같은지"""
    if not ids():
        return True
    return (row_guild or default_id()) == (current or default_id())


def member_guilds(discord_id: Optional[str]) -> List[str]:
    """로그인한 멤버가 들어가 있는 (등록된) 서버. 서버 기록이 없는 예전 멤버는 기본 서버"""
    all_ids = ids()
    if not all_ids or not discord_id:
        return all_ids
    from app import community_rank
    mine = [g for g in community_rank.guilds_of(discord_id) if g in all_ids]
    return mine or [all_ids[0]]


def current(request: Request, discord_id: Optional[str] = None) -> str:
    """지금 보고 있는 서버: 쿠키로 고른 서버가 내 서버면 그것, 아니면 내 첫 서버"""
    all_ids = ids()
    if not all_ids:
        return ""
    allowed = member_guilds(discord_id) if discord_id else all_ids
    want = request.cookies.get(CURRENT_COOKIE, "")
    return want if want in allowed else allowed[0]


def webhook_url(guild_id: str, game: Optional[str] = None) -> str:
    """서버(·게임)별 디스코드 채널 웹후크. 기본 서버만 예전 설정 이름으로 대신한다"""
    gid = guild_id or default_id()
    suffix = f"_{game.strip().upper()}" if game and game.strip() else ""
    keys = []
    if gid:
        keys += [f"DISCORD_WEBHOOK_URL_{gid}{suffix}", f"DISCORD_WEBHOOK_URL_{gid}"]
    if not gid or gid == default_id():
        from app.config import settings
        keys += [f"DISCORD_WEBHOOK_URL{suffix}"] if suffix else []
        for k in keys:
            if _env(k):
                return _env(k)
        # 관리자 콘솔에서 바꾼 값(settings)이 먼저, 없으면 환경 변수
        return (settings.discord_webhook_url or _env("DISCORD_WEBHOOK_URL") or "").strip()
    for k in keys:
        if _env(k):
            return _env(k)
    return ""


def _settings_table(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS community_settings (guild_id TEXT, key TEXT, value TEXT, PRIMARY KEY (guild_id, key))")


def get_setting(guild_id: str, key: str) -> Optional[str]:
    """서버별 설정 (디스코드 봇 관리자 명령으로 바꾸는 값). 없으면 None"""
    from app.database import get_connection
    conn = get_connection()
    try:
        _settings_table(conn)
        row = conn.execute("SELECT value FROM community_settings WHERE guild_id = ? AND key = ?",
                           (guild_id or default_id(), key)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def set_setting(guild_id: str, key: str, value: Optional[str]) -> None:
    from app.database import get_connection
    conn = get_connection()
    try:
        _settings_table(conn)
        if value is None:
            conn.execute("DELETE FROM community_settings WHERE guild_id = ? AND key = ?", (guild_id or default_id(), key))
        else:
            conn.execute("INSERT OR REPLACE INTO community_settings (guild_id, key, value) VALUES (?, ?, ?)",
                         (guild_id or default_id(), key, value))
        conn.commit()
    finally:
        conn.close()


def alert_role_ids(guild_id: str) -> Dict[str, str]:
    """게임 → 구인 알림 역할 ID. 봇 /알림역할 로 정한 값이 먼저, 없는 게임은 .env (DUO_ALERT_ROLES_<서버ID>, 기본 서버는 DUO_ALERT_ROLES)"""
    out: Dict[str, str] = {}
    for raw in (alert_roles_raw(guild_id), get_setting(guild_id, "alert_roles") or ""):
        for part in raw.split(","):
            game, _, rid = part.partition("=")
            if game.strip() and rid.strip().isdigit():
                out[game.strip().lower()] = rid.strip()
            elif game.strip() and rid.strip() == "off":  # 봇에서 끈 게임은 .env 값도 쓰지 않는다
                out.pop(game.strip().lower(), None)
    return out


def set_alert_role(guild_id: str, game: str, role_id: Optional[str]) -> None:
    current = {}
    for part in (get_setting(guild_id, "alert_roles") or "").split(","):
        g, _, rid = part.partition("=")
        if g.strip():
            current[g.strip()] = rid.strip()
    current[game] = role_id if role_id else "off"
    set_setting(guild_id, "alert_roles", ",".join(f"{g}={r}" for g, r in current.items()))


TIER_CODES = ("IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER")


def tier_role_map(guild_id: str) -> Dict[str, str]:
    """티어 → 그 서버의 기존 역할 ID (봇 /티어역할 연결·자동연결로 정함). 여러 티어가 한 역할을 같이 써도 된다 (예: 마스터+)"""
    out: Dict[str, str] = {}
    for part in (get_setting(guild_id, "tier_roles") or "").split(","):
        code, _, rid = part.partition("=")
        if code in TIER_CODES and rid.isdigit():
            out[code] = rid
    return out


def set_tier_role_map(guild_id: str, mapping: Dict[str, Optional[str]]) -> Dict[str, str]:
    clean = {c: r for c, r in mapping.items() if c in TIER_CODES and r and str(r).isdigit()}
    set_setting(guild_id, "tier_roles", ",".join(f"{c}={clean[c]}" for c in TIER_CODES if c in clean) or None)
    return tier_role_map(guild_id)


def alert_roles_raw(guild_id: str) -> str:
    gid = guild_id or default_id()
    if gid and _env(f"DUO_ALERT_ROLES_{gid}"):
        return _env(f"DUO_ALERT_ROLES_{gid}")
    return _env("DUO_ALERT_ROLES") if (not gid or gid == default_id()) else ""


def sql_match(column: str, guild_id: str) -> tuple:
    """SQL WHERE 조각: column 이 지금 서버 것인지 (예전 빈 값은 기본 서버). 설정이 없으면 거르지 않음"""
    if not ids():
        return "", ()
    gid = guild_id or default_id()
    if gid == default_id():
        return f" AND ({column} = ? OR {column} IS NULL OR {column} = '')", (gid,)
    return f" AND {column} = ?", (gid,)
