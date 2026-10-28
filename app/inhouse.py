"""내전(5:5 사설 게임) 팀 짜기.

10명의 솔로랭크 티어를 'LP 환산 점수'(아이언4 0LP = 0, 디비전마다 +100, 마스터 0LP = 2800)로 바꿔
두 팀 점수 합 차이가 가장 작은 나누기를 찾는다. 경우의 수가 126가지뿐이라 전부 계산한다.
라이엇 API는 부르지 않는다 (티어는 화면이 보낸 값 = 서버 랭킹에 이미 저장된 값).
"""
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

TIER_STEPS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"]
APEX = ("MASTER", "GRANDMASTER", "CHALLENGER")
DIVISIONS = {"IV": 0, "III": 1, "II": 2, "I": 3}
POSITIONS = ("TOP", "JUNGLE", "MID", "ADC", "SUPPORT")
MASTER_BASE = len(TIER_STEPS) * 400


def power(tier: Optional[str], rank: Optional[str] = "", lp: Optional[int] = 0) -> Optional[int]:
    """솔로랭크 티어를 한 줄 점수로. 언랭크·모르는 티어는 None"""
    t = (tier or "").upper().strip()
    lp = max(0, int(lp or 0))
    if t in APEX:
        return MASTER_BASE + lp
    if t not in TIER_STEPS:
        return None
    return TIER_STEPS.index(t) * 400 + DIVISIONS.get((rank or "").upper().strip(), 0) * 100 + min(lp, 100)


def _position_clash(team: List[Dict[str, Any]]) -> int:
    """같은 팀에 주 포지션이 겹치는 사람 수 (포지션을 안 적은 사람은 셈에서 뺌)"""
    seen: Dict[str, int] = {}
    for p in team:
        pos = p.get("position")
        if pos in POSITIONS:
            seen[pos] = seen.get(pos, 0) + 1
    return sum(n - 1 for n in seen.values() if n > 1)


def balance(players: List[Dict[str, Any]], options: int = 3) -> Dict[str, Any]:
    """players: [{name, tier, rank, lp, position?}] 정확히 10명.
    반환: 점수 차이가 작은 순서의 나누기 최대 `options`개 (다시 섞기용)."""
    if len(players) != 10:
        raise ValueError("내전은 정확히 10명이 필요합니다.")
    rows = []
    for p in players:
        rows.append({**p, "power": power(p.get("tier"), p.get("rank"), p.get("lp"))})
    known = sorted(r["power"] for r in rows if r["power"] is not None)
    # 언랭크는 나머지 사람들의 중간값으로 셈 (화면에 '추정'으로 표시)
    fallback = known[len(known) // 2] if known else 400 * 3
    for r in rows:
        r["estimated"] = r["power"] is None
        if r["estimated"]:
            r["power"] = fallback

    candidates = []
    idx = list(range(10))
    for blue in combinations(idx[1:], 4):  # 0번을 블루에 고정해 같은 나누기를 두 번 세지 않음
        blue_set = {0, *blue}
        b = [rows[i] for i in idx if i in blue_set]
        r = [rows[i] for i in idx if i not in blue_set]
        diff = abs(sum(x["power"] for x in b) - sum(x["power"] for x in r))
        clash = _position_clash(b) + _position_clash(r)
        candidates.append((diff + clash * 150, diff, clash, b, r))
    candidates.sort(key=lambda c: (c[0], c[1]))

    def team_out(team):
        total = sum(x["power"] for x in team)
        return {"players": team, "total": total, "average": round(total / 5), "average_label": power_label(round(total / 5))}

    out = []
    for _, diff, clash, b, r in candidates[:max(1, min(options, 10))]:
        out.append({"blue": team_out(b), "red": team_out(r), "diff": diff, "position_clash": clash})
    return {"options": out, "unranked_estimate": fallback if any(r["estimated"] for r in rows) else None}


def power_label(value: int) -> str:
    """점수를 사람이 읽는 티어로 (팀 평균 표시용)"""
    from app.tier_utils import TIER_NAMES_KR
    if value >= MASTER_BASE:
        return f"{TIER_NAMES_KR['MASTER']} {value - MASTER_BASE}LP"
    step, rest = divmod(max(0, value), 400)
    div = ["4", "3", "2", "1"][min(3, rest // 100)]
    return f"{TIER_NAMES_KR.get(TIER_STEPS[step], TIER_STEPS[step])} {div} {rest % 100}LP"


# ---------------------------------------------------------------------------
# 내전 기록: 나눈 팀을 저장하고, 끝나면 이긴 팀을 눌러 내전 전적을 쌓는다.
# 사람 구분은 디스코드 ID가 있으면 그것, 없으면(웹에서 직접 입력) 이름.
# ---------------------------------------------------------------------------
import json
import time

from app import communities
from app.database import get_connection

_tables_ready = set()
RESULT_EDIT_SEC = 24 * 3600  # 결과는 만든 사람이 하루 안에만 바꿀 수 있다


def _ensure_tables() -> None:
    from app import database
    key = str(database.DB_PATH)
    if key in _tables_ready:
        return
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inhouse_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                created_by TEXT NOT NULL,
                blue TEXT NOT NULL,
                red TEXT NOT NULL,
                winner TEXT,
                decided_at INTEGER
            )
        """)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(inhouse_games)")}
        # 라이엇 토너먼트 코드로 연 게임이면 코드와, 끝난 뒤 받아 온 매치 ID
        if "tournament_code" not in cols:
            conn.execute("ALTER TABLE inhouse_games ADD COLUMN tournament_code TEXT")
        if "match_id" not in cols:
            conn.execute("ALTER TABLE inhouse_games ADD COLUMN match_id TEXT")
        # 어느 디스코드 서버의 내전인지 (app/communities.py, 빈 값은 기본 서버)
        if "guild_id" not in cols:
            conn.execute("ALTER TABLE inhouse_games ADD COLUMN guild_id TEXT DEFAULT ''")
        # 사람별 경기 기록 (라이엇 매치에서만 채운다. 순위표에는 판수·승률·KDA·모스트만, 나머지는 상세에서)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inhouse_player_stats (
                game_id INTEGER NOT NULL,
                puuid TEXT NOT NULL,
                riot_name TEXT,
                side TEXT,
                win INTEGER,
                champion TEXT,
                position TEXT,
                kills INTEGER, deaths INTEGER, assists INTEGER,
                gold INTEGER, cs INTEGER, damage INTEGER, vision INTEGER, turrets INTEGER,
                duration INTEGER,
                PRIMARY KEY (game_id, puuid)
            )
        """)
        conn.commit()
    finally:
        conn.close()
    _tables_ready.add(key)


def _clean_team(team: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    out = []
    for p in team:
        name = str(p.get("name") or "").strip()[:40]
        did = str(p.get("discord_id") or "")
        out.append({"name": name, **({"discord_id": did} if did.isdigit() else {})})
    return out


def record_game(blue: List[Dict[str, Any]], red: List[Dict[str, Any]], created_by: str, guild_id: str = "") -> int:
    if len(blue) != 5 or len(red) != 5:
        raise ValueError("팀은 5명씩이어야 합니다.")
    _ensure_tables()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO inhouse_games (created_at, created_by, blue, red, guild_id) VALUES (?, ?, ?, ?, ?)",
            (int(time.time()), created_by,
             json.dumps(_clean_team(blue), ensure_ascii=False), json.dumps(_clean_team(red), ensure_ascii=False), guild_id or ""))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def set_result(game_id: int, winner: str, by: str, is_admin: bool = False) -> str:
    """반환: ok / not_found / forbidden / expired / locked (라이엇 경기 기록으로 정해진 결과는 손으로 못 바꿈)"""
    if winner not in ("blue", "red"):
        raise ValueError("winner 는 blue 또는 red")
    _ensure_tables()
    conn = get_connection()
    try:
        row = conn.execute("SELECT created_by, created_at, match_id FROM inhouse_games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return "not_found"
        if row[2]:
            return "locked"
        if not is_admin:
            if row[0] != by:
                return "forbidden"
            if time.time() - row[1] > RESULT_EDIT_SEC:
                return "expired"
        conn.execute("UPDATE inhouse_games SET winner = ?, decided_at = ? WHERE id = ?",
                     (winner, int(time.time()), game_id))
        conn.commit()
        return "ok"
    finally:
        conn.close()


def _player_key(p: Dict[str, str]) -> str:
    return f"d:{p['discord_id']}" if p.get("discord_id") else f"n:{p.get('name', '').lower()}"


def stats(days: int = 30, recent: int = 10, guild_id: str = "") -> Dict[str, Any]:
    """최근 days일 결과가 난 내전으로 사람별 승패, 그리고 최근 게임 목록 (그 디스코드 서버 내전만)"""
    _ensure_tables()
    where, args = communities.sql_match("guild_id", guild_id)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, created_at, blue, red, winner FROM inhouse_games WHERE created_at >= ?" + where + " ORDER BY id DESC",
            (int(time.time()) - days * 86400, *args)).fetchall()
    finally:
        conn.close()
    table: Dict[str, Dict[str, Any]] = {}
    games = []
    for gid, created_at, blue_s, red_s, winner in rows:
        blue, red = json.loads(blue_s), json.loads(red_s)
        if len(games) < recent:
            games.append({"id": gid, "created_at": created_at, "winner": winner,
                          "blue": [p["name"] for p in blue], "red": [p["name"] for p in red]})
        if winner not in ("blue", "red"):
            continue
        for side, team in (("blue", blue), ("red", red)):
            for p in team:
                row = table.setdefault(_player_key(p), {"name": p["name"], "wins": 0, "losses": 0})
                row["name"] = row["name"] or p["name"]
                row["wins" if side == winner else "losses"] += 1
    players = list(table.values())
    for r in players:
        r["games"] = r["wins"] + r["losses"]
        r["win_rate"] = round(r["wins"] / r["games"] * 100, 1)
    players.sort(key=lambda r: (r["wins"], r["win_rate"]), reverse=True)
    return {"players": players, "recent": games, "days": days}


def delete_game(game_id: int) -> bool:
    _ensure_tables()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM inhouse_games WHERE id = ?", (game_id,))
        conn.execute("DELETE FROM inhouse_player_stats WHERE game_id = ?", (game_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ── 라이엇 매치 결과 반영 (토너먼트 코드 게임) ─────────────────────────────

def set_tournament_code(game_id: int, code: str) -> None:
    _ensure_tables()
    conn = get_connection()
    try:
        conn.execute("UPDATE inhouse_games SET tournament_code = ? WHERE id = ?", (code, game_id))
        conn.commit()
    finally:
        conn.close()


def get_game(game_id: int) -> Optional[Dict[str, Any]]:
    _ensure_tables()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM inhouse_games WHERE id = ?", (game_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def game_by_code(code: str) -> Optional[Dict[str, Any]]:
    _ensure_tables()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM inhouse_games WHERE tournament_code = ?", (code,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def ingest_match(game_id: int, match: Dict[str, Any]) -> bool:
    """라이엇 매치 상세(match-v5)로 승패와 사람별 기록을 저장. 이미 반영된 게임이면 False"""
    info = (match or {}).get("info") or {}
    match_id = ((match or {}).get("metadata") or {}).get("matchId") or ""
    parts = info.get("participants") or []
    if len(parts) != 10:
        return False
    winner_team = next((t.get("teamId") for t in info.get("teams") or [] if t.get("win")), None)
    winner = {100: "blue", 200: "red"}.get(winner_team)
    duration = int(info.get("gameDuration") or 0)
    _ensure_tables()
    conn = get_connection()
    try:
        row = conn.execute("SELECT match_id FROM inhouse_games WHERE id = ?", (game_id,)).fetchone()
        if not row or row[0]:
            return False
        for pt in parts:
            conn.execute(
                "INSERT OR REPLACE INTO inhouse_player_stats (game_id, puuid, riot_name, side, win, champion, position, "
                "kills, deaths, assists, gold, cs, damage, vision, turrets, duration) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (game_id, pt.get("puuid", ""),
                 f"{pt.get('riotIdGameName', '')}#{pt.get('riotIdTagline', '')}".strip("#"),
                 "blue" if pt.get("teamId") == 100 else "red", 1 if pt.get("win") else 0,
                 pt.get("championName", ""), pt.get("teamPosition") or pt.get("individualPosition") or "",
                 int(pt.get("kills") or 0), int(pt.get("deaths") or 0), int(pt.get("assists") or 0),
                 int(pt.get("goldEarned") or 0),
                 int(pt.get("totalMinionsKilled") or 0) + int(pt.get("neutralMinionsKilled") or 0),
                 int(pt.get("totalDamageDealtToChampions") or 0), int(pt.get("visionScore") or 0),
                 int(pt.get("turretTakedowns") or 0), duration))
        conn.execute("UPDATE inhouse_games SET match_id = ?, winner = COALESCE(?, winner), decided_at = ? WHERE id = ?",
                     (match_id, winner, int(time.time()), game_id))
        conn.commit()
        return True
    finally:
        conn.close()


# ── 내전 순위 ───────────────────────────────────────────────────────────────
RATING_START = 1000
RATING_K = 24
PLACEMENT_GAMES = 3


def _identity_maps(conn) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, str]]:
    """인증된 서버 멤버: puuid → (키, 표시 이름), 소문자 게임 닉네임 → 키"""
    by_puuid: Dict[str, Tuple[str, str]] = {}
    by_name: Dict[str, str] = {}
    try:
        rows = conn.execute("SELECT puuid, game_name, discord_name FROM member_accounts "
                            "WHERE puuid IS NOT NULL AND verified = 1").fetchall()
    except Exception:  # 서버 랭킹 표가 아직 없을 때
        rows = []
    for puuid, game_name, discord_name in rows:
        key = f"m:{puuid}"
        by_puuid[puuid] = (key, game_name or discord_name or "")
        if game_name:
            by_name[game_name.lower()] = key
    return by_puuid, by_name


def ranking(days: int = 30, guild_id: str = "") -> Dict[str, Any]:
    """기간 안의 결과 난 내전으로 사람별 내전 점수(팀 평균 기준 Elo)·판수·승률, 라이엇 경기 기록이 있으면 KDA·모스트.
    같은 사람은 인증 계정(puuid)으로 묶고, 손으로 넣은 이름은 그 닉네임의 인증 멤버가 있으면 합친다."""
    _ensure_tables()
    since = int(time.time()) - days * 86400
    conn = get_connection()
    try:
        by_puuid, by_name = _identity_maps(conn)
        where, args = communities.sql_match("guild_id", guild_id)
        games = conn.execute(
            "SELECT id, blue, red, winner FROM inhouse_games WHERE created_at >= ? AND winner IN ('blue','red')" + where +
            " ORDER BY COALESCE(decided_at, created_at), id", (since, *args)).fetchall()
        g_where, g_args = communities.sql_match("g.guild_id", guild_id)
        stat_rows = [dict(r) for r in conn.execute(
            "SELECT s.* FROM inhouse_player_stats s JOIN inhouse_games g ON g.id = s.game_id WHERE g.created_at >= ?" + g_where,
            (since, *g_args)).fetchall()]
    finally:
        conn.close()
    stats_by_game: Dict[int, List[Dict[str, Any]]] = {}
    for r in stat_rows:
        stats_by_game.setdefault(r["game_id"], []).append(r)

    players: Dict[str, Dict[str, Any]] = {}

    def player(key: str, name: str) -> Dict[str, Any]:
        p = players.setdefault(key, {"key": key, "name": name, "rating": float(RATING_START), "wins": 0, "losses": 0,
                                     "k": 0, "d": 0, "a": 0, "detail_games": 0, "champions": {}})
        if name and not p["name"]:
            p["name"] = name
        return p

    for gid, blue_s, red_s, winner in games:
        rows = stats_by_game.get(gid)
        sides: Dict[str, List[Dict[str, Any]]] = {"blue": [], "red": []}
        if rows:  # 라이엇 기록이 있으면 실제로 뛴 10명이 기준
            for r in rows:
                key, name = by_puuid.get(r["puuid"], (f"p:{r['puuid']}", (r["riot_name"] or "").split("#")[0]))
                p = player(key, name)
                p["k"] += r["kills"]
                p["d"] += r["deaths"]
                p["a"] += r["assists"]
                p["detail_games"] += 1
                if r["champion"]:
                    p["champions"][r["champion"]] = p["champions"].get(r["champion"], 0) + 1
                sides[r["side"]].append(p)
        else:
            for side, team_s in (("blue", blue_s), ("red", red_s)):
                for t in json.loads(team_s):
                    name = t.get("name", "")
                    sides[side].append(player(by_name.get(name.lower()) or _player_key(t), name))
        if not sides["blue"] or not sides["red"]:
            continue
        avg = {side: sum(p["rating"] for p in team) / len(team) for side, team in sides.items()}
        for side, team in sides.items():
            other = "red" if side == "blue" else "blue"
            expected = 1 / (1 + 10 ** ((avg[other] - avg[side]) / 400))
            score = 1.0 if side == winner else 0.0
            for p in team:
                p["rating"] += RATING_K * (score - expected)
                p["wins" if side == winner else "losses"] += 1

    out = []
    for p in players.values():
        games_n = p["wins"] + p["losses"]
        champs = sorted(p["champions"].items(), key=lambda kv: -kv[1])[:3]
        out.append({
            "key": p["key"], "name": p["name"], "rating": round(p["rating"]), "games": games_n,
            "wins": p["wins"], "losses": p["losses"],
            "win_rate": round(p["wins"] / games_n * 100, 1) if games_n else 0.0,
            "kda": round((p["k"] + p["a"]) / max(1, p["d"]), 2) if p["detail_games"] else None,
            "most_champions": [{"champion": c, "games": n} for c, n in champs],
            "placement": games_n < PLACEMENT_GAMES,
            "has_detail": p["detail_games"] > 0,
        })
    # 배치(3판 미만)는 아래로, 그 안에서는 점수·판수 순
    out.sort(key=lambda r: (not r["placement"], r["rating"], r["games"]), reverse=True)
    for i, r in enumerate(out, start=1):
        r["rank"] = i
    return {"players": out, "days": days, "placement_games": PLACEMENT_GAMES}


def player_detail(key: str, days: int = 30, guild_id: str = "") -> Optional[Dict[str, Any]]:
    """순위표에서 한 사람을 눌렀을 때: 평균 골드·CS·딜·시야·타워 등 세부 기록 (라이엇 경기 기록이 있는 게임만)"""
    if not key.startswith(("m:", "p:")) or len(key) > 100:
        return None
    puuid = key[2:]
    _ensure_tables()
    where, args = communities.sql_match("g.guild_id", guild_id)
    conn = get_connection()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT s.*, g.created_at FROM inhouse_player_stats s JOIN inhouse_games g ON g.id = s.game_id "
            "WHERE s.puuid = ? AND g.created_at >= ?" + where + " ORDER BY g.id DESC",
            (puuid, int(time.time()) - days * 86400, *args)).fetchall()]
    finally:
        conn.close()
    if not rows:
        return {"key": key, "games": 0}
    n = len(rows)
    minutes = sum(r["duration"] for r in rows) / 60 or 1

    def avg(field: str) -> float:
        return round(sum(r[field] for r in rows) / n, 1)

    positions: Dict[str, int] = {}
    for r in rows:
        if r["position"]:
            positions[r["position"]] = positions.get(r["position"], 0) + 1
    return {
        "key": key, "games": n,
        "avg_kills": avg("kills"), "avg_deaths": avg("deaths"), "avg_assists": avg("assists"),
        "avg_gold": round(sum(r["gold"] for r in rows) / n), "avg_cs": avg("cs"),
        "cs_per_min": round(sum(r["cs"] for r in rows) / minutes, 1),
        "avg_damage": round(sum(r["damage"] for r in rows) / n), "avg_vision": avg("vision"),
        "avg_turrets": avg("turrets"),
        "positions": [{"position": k, "games": v} for k, v in sorted(positions.items(), key=lambda kv: -kv[1])],
        "recent": [{"game_id": r["game_id"], "created_at": r["created_at"], "champion": r["champion"], "win": bool(r["win"]),
                    "kills": r["kills"], "deaths": r["deaths"], "assists": r["assists"]} for r in rows[:10]],
    }


def seat_puuids(game: Dict[str, Any]) -> List[str]:
    """게임 10자리 → 인증된 서버 멤버 puuid (디스코드 ID 또는 같은 게임 닉네임). 못 찾은 자리는 빠진다"""
    _ensure_tables()
    conn = get_connection()
    try:
        try:
            rows = conn.execute("SELECT discord_id, puuid, game_name FROM member_accounts "
                                "WHERE puuid IS NOT NULL AND verified = 1").fetchall()
        except Exception:
            rows = []
    finally:
        conn.close()
    by_id = {r[0]: r[1] for r in rows}
    by_name = {(r[2] or "").lower(): r[1] for r in rows if r[2]}
    out = []
    for team in (game.get("blue"), game.get("red")):
        for seat in json.loads(team or "[]"):
            puuid = by_id.get(seat.get("discord_id", "")) or by_name.get(seat.get("name", "").lower())
            if puuid:
                out.append(puuid)
    return out


# ── 토너먼트·리그 (여러 팀이 여러 판) ─────────────────────────────────────────
# 팀·대진은 화면(team_builder.plan)이 만든 것을 그대로 저장한다. 경기마다 '시작'을 누르면 보통 내전 게임(inhouse_games)이
# 하나 만들어지고, 결과(이긴 팀 버튼·토너먼트 코드)는 그 게임에 기록된다. 대진표·순위는 게임 결과로 매번 다시 계산한다.

def _ensure_event_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inhouse_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT DEFAULT '',
            created_by TEXT NOT NULL,
            mode TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)


def create_event(mode: str, teams: List[Dict[str, Any]], matches: List[Dict[str, Any]], created_by: str,
                 guild_id: str = "", title: str = "") -> int:
    if mode not in ("tournament", "league"):
        raise ValueError("토너먼트 또는 리그만 저장합니다.")
    if not 2 <= len(teams) <= 16 or any(len(t.get("players") or []) != 5 for t in teams):
        raise ValueError("팀은 2~16개, 팀마다 5명이어야 합니다.")
    clean_teams = [{"name": str(t.get("name") or f"{i + 1}팀")[:20], "players": _clean_team(t["players"]),
                    "lanes": [str(p.get("lane") or "")[:8] for p in t["players"]]} for i, t in enumerate(teams)]
    clean_matches = []
    for m in matches:
        a, b = m.get("a"), m.get("b")
        if a is not None and not (isinstance(a, int) and 0 <= a < len(teams)):
            raise ValueError("대진의 팀 번호가 올바르지 않습니다.")
        if b is not None and not (isinstance(b, int) and 0 <= b < len(teams)):
            raise ValueError("대진의 팀 번호가 올바르지 않습니다.")
        clean_matches.append({"round": int(m.get("round") or 1), "a": a, "b": b, "game_id": None})
    if not clean_matches:
        raise ValueError("대진이 비어 있습니다.")
    _ensure_tables()
    conn = get_connection()
    try:
        _ensure_event_table(conn)
        cur = conn.execute("INSERT INTO inhouse_events (guild_id, created_by, mode, data, created_at) VALUES (?, ?, ?, ?, ?)",
                           (guild_id or "", created_by, mode,
                            json.dumps({"title": title[:40], "teams": clean_teams, "matches": clean_matches}, ensure_ascii=False),
                            int(time.time())))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def _load_event(conn, event_id: int) -> Optional[Dict[str, Any]]:
    _ensure_event_table(conn)
    row = conn.execute("SELECT * FROM inhouse_events WHERE id = ?", (event_id,)).fetchone()
    if not row:
        return None
    ev = dict(row)
    ev["data"] = json.loads(ev["data"])
    return ev


def _save_event_data(conn, event_id: int, data: Dict[str, Any]) -> None:
    conn.execute("UPDATE inhouse_events SET data = ? WHERE id = ?", (json.dumps(data, ensure_ascii=False), event_id))
    conn.commit()


def event_view(event_id: int) -> Optional[Dict[str, Any]]:
    """경기마다 승자, 토너먼트면 다음 라운드를 채우고 우승 팀, 리그면 순위표"""
    _ensure_tables()
    conn = get_connection()
    try:
        ev = _load_event(conn, event_id)
        if not ev:
            return None
        data = ev["data"]
        ids = [m["game_id"] for m in data["matches"] if m.get("game_id")]
        winners = {}
        if ids:
            for gid, w in conn.execute(f"SELECT id, winner FROM inhouse_games WHERE id IN ({','.join('?' * len(ids))})", ids):
                winners[gid] = w
        for m in data["matches"]:
            m["winner"] = None
            if m["a"] is not None and m["b"] is None:
                m["winner"] = m["a"]  # 부전승
            elif m["b"] is not None and m["a"] is None:
                m["winner"] = m["b"]
            elif m.get("game_id") and winners.get(m["game_id"]) in ("blue", "red"):
                m["winner"] = m["a"] if winners[m["game_id"]] == "blue" else m["b"]
        out = {"id": ev["id"], "mode": ev["mode"], "created_at": ev["created_at"], "created_by": ev["created_by"],
               "guild_id": ev["guild_id"], "title": data.get("title") or "", "teams": data["teams"], "matches": data["matches"]}
        if ev["mode"] == "tournament":
            last = max(m["round"] for m in data["matches"])
            cur = [m for m in data["matches"] if m["round"] == last]
            if all(m["winner"] is not None for m in cur):
                if len(cur) == 1:
                    out["champion"] = cur[0]["winner"]
                else:  # 다음 라운드: 이웃한 경기 승자끼리 (경기 수가 홀수면 마지막 승자는 부전승)
                    for i in range(0, len(cur), 2):
                        b = cur[i + 1]["winner"] if i + 1 < len(cur) else None
                        data["matches"].append({"round": last + 1, "a": cur[i]["winner"], "b": b, "game_id": None})
                    _save_event_data(conn, event_id, {k: v for k, v in data.items()})
                    return event_view(event_id)
        else:
            table = {i: {"team": i, "name": t["name"], "wins": 0, "losses": 0} for i, t in enumerate(data["teams"])}
            for m in data["matches"]:
                if m["winner"] is not None and m["a"] is not None and m["b"] is not None:
                    loser = m["b"] if m["winner"] == m["a"] else m["a"]
                    table[m["winner"]]["wins"] += 1
                    table[loser]["losses"] += 1
            out["standings"] = sorted(table.values(), key=lambda r: (-r["wins"], r["losses"], r["team"]))
        return out
    finally:
        conn.close()


def start_event_match(event_id: int, index: int, by: str, is_admin: bool = False) -> Dict[str, Any]:
    """대진 한 경기를 보통 내전 게임으로 연다 (블루 = a팀, 레드 = b팀). 반환: {status, game_id?}"""
    _ensure_tables()
    conn = get_connection()
    try:
        ev = _load_event(conn, event_id)
        if not ev:
            return {"status": "not_found"}
        if not is_admin and ev["created_by"] != by:
            return {"status": "forbidden"}
        data = ev["data"]
        if not 0 <= index < len(data["matches"]):
            return {"status": "not_found"}
        m = data["matches"][index]
        if m.get("game_id"):
            return {"status": "ok", "game_id": m["game_id"]}
        if m["a"] is None or m["b"] is None:
            return {"status": "bye"}
    finally:
        conn.close()
    gid = record_game(data["teams"][m["a"]]["players"], data["teams"][m["b"]]["players"], by, guild_id=ev["guild_id"])
    conn = get_connection()
    try:
        ev = _load_event(conn, event_id)
        ev["data"]["matches"][index]["game_id"] = gid
        _save_event_data(conn, event_id, ev["data"])
    finally:
        conn.close()
    return {"status": "ok", "game_id": gid}


def recent_events(guild_id: str = "", limit: int = 10) -> List[Dict[str, Any]]:
    _ensure_tables()
    where, args = communities.sql_match("guild_id", guild_id)
    conn = get_connection()
    try:
        _ensure_event_table(conn)
        rows = conn.execute("SELECT id, mode, data, created_at FROM inhouse_events WHERE 1 = 1" + where +
                            " ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()
    finally:
        conn.close()
    out = []
    for eid, mode, raw, created in rows:
        d = json.loads(raw)
        out.append({"id": eid, "mode": mode, "title": d.get("title") or "", "teams": len(d["teams"]), "created_at": created})
    return out
