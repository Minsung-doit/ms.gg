"""내전(5:5 사설 게임) 팀 짜기.

10명의 솔로랭크 티어를 'LP 환산 점수'(아이언4 0LP = 0, 디비전마다 +100, 마스터 0LP = 2800)로 바꿔
두 팀 점수 합 차이가 가장 작은 나누기를 찾는다. 경우의 수가 126가지뿐이라 전부 계산한다.
라이엇 API는 부르지 않는다 (티어는 화면이 보낸 값 = 서버 랭킹에 이미 저장된 값).
"""
from itertools import combinations
from typing import Any, Dict, List, Optional

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


def record_game(blue: List[Dict[str, Any]], red: List[Dict[str, Any]], created_by: str) -> int:
    if len(blue) != 5 or len(red) != 5:
        raise ValueError("팀은 5명씩이어야 합니다.")
    _ensure_tables()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO inhouse_games (created_at, created_by, blue, red) VALUES (?, ?, ?, ?)",
            (int(time.time()), created_by,
             json.dumps(_clean_team(blue), ensure_ascii=False), json.dumps(_clean_team(red), ensure_ascii=False)))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def set_result(game_id: int, winner: str, by: str, is_admin: bool = False) -> str:
    """반환: ok / not_found / forbidden / expired"""
    if winner not in ("blue", "red"):
        raise ValueError("winner 는 blue 또는 red")
    _ensure_tables()
    conn = get_connection()
    try:
        row = conn.execute("SELECT created_by, created_at FROM inhouse_games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return "not_found"
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


def stats(days: int = 30, recent: int = 10) -> Dict[str, Any]:
    """최근 days일 결과가 난 내전으로 사람별 승패, 그리고 최근 게임 목록"""
    _ensure_tables()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, created_at, blue, red, winner FROM inhouse_games WHERE created_at >= ? ORDER BY id DESC",
            (int(time.time()) - days * 86400,)).fetchall()
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
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
