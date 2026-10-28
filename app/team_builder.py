"""
내전 팀 짜기 엔진 (app/team_builder.py, 2026-10-28)

AI(언어 모델)가 아니라 점수 모델 + 최적화 계산이다. 같은 입력이면 같은 결과가 나오고, 근거(점수·라인)를 보여 줄 수 있다.
라이엇 API는 부르지 않는다. 쓰는 값은 모두 이미 저장된 것:
  - 현재 솔로랭크 (등록·인증 멤버의 저장된 티어, 또는 화면에서 고른 티어)
  - 최고 티어: 우리가 쌓은 티어 기록(rank_snapshots)에서만 (라이엇 API는 지난 시즌·최고 티어를 주지 않는다)
  - 최근 퍼포먼스: 하루 한 번 받아 둔 최근 30일 솔로·자유랭크 (승률, 같은 판 10명 평균 대비 KDA)
  - 내전 점수: 우리 내전 기록 Elo (판수가 쌓일수록 비중↑)
  - 라인: 최근 게임에서 많이 간 라인(주·부) 또는 직접 고른 라인

점수 단위는 'LP 환산'(inhouse.power: 아이언4 0LP = 0, 디비전 +100, 마스터 0LP = 2800).

나누기:
  - 10명 → 5:5: 126가지 나누기 × 팀마다 라인 배정 120가지를 전부 계산 (팀 점수 차 + 라인 손실 + 라인 맞상대 차)
  - N명 → K팀(5명씩): 실력 순 뱀 드래프트 후 맞바꾸기로 다듬기 (팀 점수 고르게 + 라인 손실)
  - 방식: 한 판 / 여러 판 동시(균형·실력대별) / 토너먼트(대진표) / 리그(풀리그 일정). 5·10의 배수가 아니면 남는 사람은 대기.
"""
import json
import time
from itertools import combinations, permutations
from typing import Any, Dict, List, Optional, Tuple

from app.inhouse import POSITIONS, power, power_label

# 라인 배정 손실 (LP 환산 점수와 같은 단위)
POS_COST_MAIN = 0
POS_COST_SUB = 60
POS_COST_UNKNOWN = 30  # 라인 정보가 없는 사람 (아무 데나)
POS_COST_OFF = 160
LANE_GAP_WEIGHT = 0.15  # 같은 라인 맞상대 점수 차이의 비중

PEAK_WEIGHT = 0.25       # 최고 티어가 지금보다 높으면 그 차이의 25%만큼 올려 본다 (최대 400)
PERF_MAX = 100           # 최근 퍼포먼스 보정 최대 ±100
INHOUSE_FULL_GAMES = 10  # 내전 10판 이상이면 내전 점수 비중 최대
INHOUSE_SCALE = 2.0      # 내전 Elo 1점 = 2점 (Elo 50 ≈ 한 디비전)
INHOUSE_MAX_WEIGHT = 0.6

RIOT_POS = {"TOP": "TOP", "JUNGLE": "JUNGLE", "MIDDLE": "MID", "MID": "MID", "BOTTOM": "ADC", "ADC": "ADC",
            "UTILITY": "SUPPORT", "SUPPORT": "SUPPORT"}
RECENT_DAYS = 30
RECENT_GAMES = 20


# ── 사람별 점수 ─────────────────────────────────────────────────────────────

def _peak_powers(puuids: List[str]) -> Dict[str, int]:
    from app.database import get_connection
    if not puuids:
        return {}
    out: Dict[str, int] = {}
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT puuid, tier, rank_tier, league_points FROM rank_snapshots WHERE puuid IN ({','.join('?' * len(puuids))})",
            puuids).fetchall()
    except Exception:  # 기록 표가 아직 없을 때
        rows = []
    finally:
        conn.close()
    for puuid, tier, rank, lp in rows:
        p = power(tier, rank, lp)
        if p is not None and p > out.get(puuid, -1):
            out[puuid] = p
    return out


def _recent_stats(puuids: List[str]) -> Dict[str, Dict[str, Any]]:
    """최근 30일 캐시된 솔로·자유랭크에서 사람별 최근 20판: 승률, 같은 판 평균 대비 KDA, 라인 횟수 (한 번 훑기)"""
    from app.database import get_connection
    want = set(p for p in puuids if p)
    if not want:
        return {}
    conn = get_connection()
    try:
        rows = conn.execute("SELECT data FROM match_cache WHERE game_end >= ? ORDER BY game_end DESC",
                            (int((time.time() - RECENT_DAYS * 86400) * 1000),)).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    games: Dict[str, List[Dict[str, Any]]] = {p: [] for p in want}
    for (raw,) in rows:
        if not raw or not any(p in raw for p in want):
            continue
        try:
            info = (json.loads(raw).get("info") or {})
        except Exception:
            continue
        if info.get("queueId") not in (420, 440):
            continue
        parts = info.get("participants") or []
        kdas = [(x.get("kills", 0) + x.get("assists", 0)) / max(1, x.get("deaths", 0)) for x in parts]
        lobby = sum(kdas) / len(kdas) if kdas else 0
        for x in parts:
            pu = x.get("puuid")
            if pu in want and len(games[pu]) < RECENT_GAMES:
                games[pu].append({"win": bool(x.get("win")), "pos": RIOT_POS.get(x.get("teamPosition") or "", ""),
                                  "kda": (x.get("kills", 0) + x.get("assists", 0)) / max(1, x.get("deaths", 0)),
                                  "lobby": lobby})
    out = {}
    for pu, gs in games.items():
        if not gs:
            continue
        n = len(gs)
        wr = sum(g["win"] for g in gs) / n
        rel = sum(g["kda"] / g["lobby"] for g in gs if g["lobby"] > 0) / n if any(g["lobby"] > 0 for g in gs) else 1.0
        lanes: Dict[str, int] = {}
        for g in gs:
            if g["pos"]:
                lanes[g["pos"]] = lanes.get(g["pos"], 0) + 1
        out[pu] = {"games": n, "win_rate": round(wr * 100, 1), "kda_rel": round(rel, 2), "lanes": lanes}
    return out


def _lanes_from_counts(lanes: Dict[str, int]) -> Tuple[Optional[str], Optional[str]]:
    ranked = sorted(lanes.items(), key=lambda kv: -kv[1])
    total = sum(lanes.values())
    main = ranked[0][0] if ranked else None
    sub = ranked[1][0] if len(ranked) > 1 and ranked[1][1] >= max(2, total * 0.2) else None
    return main, sub


def rate_players(players: List[Dict[str, Any]], guild_id: str = "") -> List[Dict[str, Any]]:
    """players: [{name, discord_id?, tier?, rank?, lp?, main?, sub?, position?}] → 점수·라인·근거를 붙여 돌려준다.
    디스코드 ID(또는 같은 게임 닉네임)로 등록·인증 멤버를 찾으면 저장된 티어·기록을 쓴다."""
    from app import community_rank, inhouse
    from app.database import get_connection, get_player_by_riot_id
    community_rank._ensure_tables()
    conn = get_connection()
    try:
        accounts = [dict(r) for r in conn.execute(
            "SELECT discord_id, puuid, game_name, tag_line, verified FROM member_accounts WHERE puuid IS NOT NULL").fetchall()]
    finally:
        conn.close()
    by_did = {a["discord_id"]: a for a in accounts}
    by_name = {(a["game_name"] or "").replace(" ", "").lower(): a for a in accounts if a["game_name"]}

    rows = []
    for p in players:
        acc = by_did.get(str(p.get("discord_id") or "")) or by_name.get((p.get("name") or "").replace(" ", "").lower())
        stored = {}
        if acc:
            stored = get_player_by_riot_id(acc["game_name"], acc["tag_line"]) or {}
            if stored.get("puuid") and stored.get("puuid") != acc["puuid"]:
                stored = {}
        tier = stored.get("tier") or p.get("tier")
        rank = stored.get("rank_tier") if stored.get("tier") else p.get("rank")
        lp = stored.get("league_points") if stored.get("tier") else p.get("lp")
        rows.append({**p, "puuid": acc["puuid"] if acc else None, "linked": bool(acc),
                     "current": power(tier, rank, lp), "tier": tier, "rank": rank, "lp": lp})

    puuids = [r["puuid"] for r in rows if r["puuid"]]
    peaks = _peak_powers(puuids)
    recent = _recent_stats(puuids)
    ih = {}
    try:
        for x in inhouse.ranking(days=180, guild_id=guild_id)["players"]:
            ih[x["key"]] = x
    except Exception:
        pass

    known = sorted(r["current"] for r in rows if r["current"] is not None)
    fallback = known[len(known) // 2] if known else 1200  # 정보가 없으면 참가자 중간값 (없으면 골드)
    for r in rows:
        parts = {}
        base = r["current"]
        r["estimated"] = base is None
        if base is None:
            base = fallback
        parts["current"] = base
        peak = peaks.get(r["puuid"]) if r["puuid"] else None
        if peak is not None and peak > base:
            parts["peak"] = round(min(400, (peak - base) * PEAK_WEIGHT))
        st = recent.get(r["puuid"]) if r["puuid"] else None
        if st:
            sample = min(st["games"], RECENT_GAMES) / RECENT_GAMES
            wr_part = max(-1.0, min(1.0, (st["win_rate"] / 100 - 0.5) / 0.15))  # 승률 35%~65% → -1~+1
            kda_part = max(-1.0, min(1.0, (st["kda_rel"] - 1.0) / 0.5))       # 판 평균의 0.5배~1.5배 → -1~+1
            parts["recent"] = round((0.6 * wr_part + 0.4 * kda_part) * PERF_MAX * sample)
        ihx = ih.get(f"m:{r['puuid']}") if r["puuid"] else None
        if ihx is None and r.get("discord_id"):
            ihx = ih.get(f"d:{r['discord_id']}")
        if ihx and ihx.get("games"):
            w = INHOUSE_MAX_WEIGHT * min(ihx["games"], INHOUSE_FULL_GAMES) / INHOUSE_FULL_GAMES
            parts["inhouse"] = round(w * (ihx["rating"] - 1000) * INHOUSE_SCALE)
        r["rating"] = int(sum(parts.values()))
        r["rating_parts"] = parts
        r["rating_label"] = power_label(max(0, r["rating"]))
        # 라인: 직접 고른 것 > 최근 게임
        main = r.get("main") or r.get("position")
        sub = r.get("sub")
        if not main and st:
            main, sub = _lanes_from_counts(st["lanes"])
        r["main"] = main if main in POSITIONS else None
        r["sub"] = sub if sub in POSITIONS and sub != r["main"] else None
        r["recent"] = st
    return rows


# ── 라인 배정 ───────────────────────────────────────────────────────────────

def _pos_cost(p: Dict[str, Any], lane: str) -> int:
    if not p.get("main"):
        return POS_COST_UNKNOWN
    if lane == p["main"]:
        return POS_COST_MAIN
    if lane == p.get("sub"):
        return POS_COST_SUB
    return POS_COST_OFF


_ASSIGN_MEMO: Dict[Tuple, Tuple[int, Tuple[str, ...]]] = {}


def best_lanes(team: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
    """5명 → 라인 배정 120가지 중 손실이 가장 작은 것 (손실, 사람 순서대로 라인)"""
    key = tuple((p.get("main"), p.get("sub")) for p in team)
    if key in _ASSIGN_MEMO:
        cost, lanes = _ASSIGN_MEMO[key]
        return cost, list(lanes)
    best = None
    for perm in permutations(POSITIONS, len(team)):
        c = sum(_pos_cost(p, lane) for p, lane in zip(team, perm))
        if best is None or c < best[0]:
            best = (c, perm)
            if c == 0:
                break
    if len(_ASSIGN_MEMO) > 20000:
        _ASSIGN_MEMO.clear()
    _ASSIGN_MEMO[key] = best
    return best[0], list(best[1])


def _team_out(team: List[Dict[str, Any]], lanes: Optional[List[str]] = None, name: str = "") -> Dict[str, Any]:
    if lanes is None:
        _, lanes = best_lanes(team)
    order = {lane: i for i, lane in enumerate(POSITIONS)}
    members = sorted(({**_public(p), "lane": lane, "lane_fit": _fit(p, lane)} for p, lane in zip(team, lanes)),
                     key=lambda m: order.get(m["lane"], 9))
    total = sum(p["rating"] for p in team)
    return {"name": name, "players": members, "total": total, "average": round(total / len(team)),
            "average_label": power_label(max(0, round(total / len(team))))}


def _fit(p: Dict[str, Any], lane: str) -> str:
    if not p.get("main"):
        return "any"
    return "main" if lane == p["main"] else ("sub" if lane == p.get("sub") else "off")


def _public(p: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("name", "discord_id", "tier", "rank", "lp", "rating", "rating_label", "rating_parts", "main", "sub",
            "estimated", "linked")
    out = {k: p.get(k) for k in keep}
    if p.get("recent"):
        out["recent"] = {"games": p["recent"]["games"], "win_rate": p["recent"]["win_rate"], "kda_rel": p["recent"]["kda_rel"]}
    return out


# ── 5:5 한 판 (10명) ───────────────────────────────────────────────────────

def split_ten(rows: List[Dict[str, Any]], options: int = 3) -> List[Dict[str, Any]]:
    if len(rows) != 10:
        raise ValueError("5:5 는 정확히 10명이 필요합니다.")
    cands = []
    for blue in combinations(range(1, 10), 4):  # 0번은 블루 고정 (같은 나누기를 두 번 세지 않음)
        bset = {0, *blue}
        b = [rows[i] for i in range(10) if i in bset]
        r = [rows[i] for i in range(10) if i not in bset]
        bc, bl = best_lanes(b)
        rc, rl = best_lanes(r)
        diff = abs(sum(x["rating"] for x in b) - sum(x["rating"] for x in r))
        lane_rating = {}
        for p, lane in zip(b, bl):
            lane_rating[lane] = [p["rating"], 0]
        for p, lane in zip(r, rl):
            lane_rating.setdefault(lane, [0, 0])[1] = p["rating"]
        lane_gap = sum(abs(a - c) for a, c in lane_rating.values())
        cost = diff + bc + rc + LANE_GAP_WEIGHT * lane_gap
        cands.append((cost, diff, bc + rc, lane_gap, b, bl, r, rl))
    cands.sort(key=lambda c: c[0])
    out = []
    for cost, diff, pos_cost, lane_gap, b, bl, r, rl in cands[:max(1, min(options, 5))]:
        out.append({"blue": _team_out(b, bl, "블루"), "red": _team_out(r, rl, "레드"), "diff": diff,
                    "lane_penalty": pos_cost, "lane_gap": lane_gap, "score": round(cost)})
    return out


# ── K팀 (5명씩) ─────────────────────────────────────────────────────────────

def make_teams(rows: List[Dict[str, Any]], k: int, time_limit: float = 4.0) -> List[List[Dict[str, Any]]]:
    """5k명 → 5명씩 k팀. 뱀 드래프트 후 두 사람 맞바꾸기로 (팀 점수 편차 + 라인 손실)을 줄인다"""
    if len(rows) != 5 * k or k < 2:
        raise ValueError("팀 수와 인원이 맞지 않습니다.")
    order = sorted(rows, key=lambda p: -p["rating"])
    teams: List[List[Dict[str, Any]]] = [[] for _ in range(k)]
    for i, p in enumerate(order):
        rnd, pos = divmod(i, k)
        teams[pos if rnd % 2 == 0 else k - 1 - pos].append(p)
    mean = sum(p["rating"] for p in rows) / k

    def team_cost(t):
        return abs(sum(p["rating"] for p in t) - mean) + best_lanes(t)[0]

    costs = [team_cost(t) for t in teams]
    deadline = time.time() + time_limit
    improved = True
    while improved and time.time() < deadline:
        improved = False
        for a in range(k):
            for b in range(a + 1, k):
                for i in range(5):
                    for j in range(5):
                        ta, tb = teams[a][:], teams[b][:]
                        ta[i], tb[j] = tb[j], ta[i]
                        ca, cb = team_cost(ta), team_cost(tb)
                        if ca + cb < costs[a] + costs[b] - 1e-6:
                            teams[a], teams[b], costs[a], costs[b] = ta, tb, ca, cb
                            improved = True
                if time.time() >= deadline:
                    break
    return teams


# ── 방식별 계획 ─────────────────────────────────────────────────────────────

def _bracket(team_count: int) -> List[Dict[str, Any]]:
    """싱글 엘리미네이션 1라운드 (시드 1-최하위, 2-그다음 ...). 팀 수가 2의 거듭제곱이 아니면 상위 시드가 부전승"""
    size = 1
    while size < team_count:
        size *= 2
    seeds = [1]
    while len(seeds) < size:  # 표준 시드 배치 (1·2번 시드가 결승에서 만나게)
        n = len(seeds) * 2
        seeds = [s for x in seeds for s in (x, n + 1 - x)]
    matches = []
    for i in range(0, size, 2):
        a, b = seeds[i], seeds[i + 1]
        matches.append({"round": 1, "a": a - 1 if a <= team_count else None, "b": b - 1 if b <= team_count else None})
    return matches


def _round_robin(team_count: int) -> List[Dict[str, Any]]:
    """풀리그 일정 (원형 방식): 라운드마다 모든 팀이 한 번씩 (홀수면 한 팀 휴식)"""
    ids: List[Optional[int]] = list(range(team_count))
    if len(ids) % 2:
        ids.append(None)
    n = len(ids)
    out = []
    for rnd in range(n - 1):
        for i in range(n // 2):
            a, b = ids[i], ids[n - 1 - i]
            if a is not None and b is not None:
                out.append({"round": rnd + 1, "a": a, "b": b})
        ids = [ids[0]] + [ids[-1]] + ids[1:-1]
    return out


TEAM_NAMES = ["1팀", "2팀", "3팀", "4팀", "5팀", "6팀", "7팀", "8팀", "9팀", "10팀", "11팀", "12팀", "13팀", "14팀", "15팀", "16팀"]
MAX_PLAYERS = 80


def plan(players: List[Dict[str, Any]], mode: str = "auto", split: str = "balanced", guild_id: str = "",
         options: int = 3) -> Dict[str, Any]:
    """mode: single(5:5 한 판) / multi(여러 5:5 동시) / tournament / league / auto(10명이면 single, 아니면 multi)
    split(multi 전용): balanced(모든 판 균형) / tiered(실력대별 방)"""
    if len(players) < 10:
        raise ValueError("내전은 10명 이상이 필요합니다.")
    if len(players) > MAX_PLAYERS:
        raise ValueError(f"한 번에 {MAX_PLAYERS}명까지 나눌 수 있습니다.")
    rows = rate_players(players, guild_id)
    if mode == "auto":
        mode = "single" if len(rows) < 20 else "multi"
    unit = 10 if mode in ("single", "multi") else 5
    if mode == "single":
        unit_count = 10
    else:
        unit_count = len(rows) - len(rows) % unit
    # 남는 사람: 들어온 순서 뒤쪽부터 대기 (다음 판에 먼저 넣어 돌아가며 쉬기)
    playing, waiting = rows[:unit_count], rows[unit_count:]
    result: Dict[str, Any] = {"mode": mode, "split": split if mode == "multi" else None,
                              "waitlist": [_public(p) for p in waiting], "player_count": len(rows)}
    if mode == "single":
        result["games"] = [{"options": split_ten(playing, options)}]
        return result
    if mode == "multi":
        g = len(playing) // 10
        if split == "tiered":
            order = sorted(playing, key=lambda p: -p["rating"])
            groups = [order[i * 10:(i + 1) * 10] for i in range(g)]
        else:
            teams = make_teams(playing, 2 * g)
            teams.sort(key=lambda t: -sum(p["rating"] for p in t))
            groups = [teams[2 * i] + teams[2 * i + 1] for i in range(g)]
        result["games"] = [{"room": i + 1, "options": split_ten(grp, 1 if g > 2 else min(options, 2))}
                           for i, grp in enumerate(groups)]
        return result
    if mode in ("tournament", "league"):
        k = len(playing) // 5
        if k < 2:
            raise ValueError("토너먼트·리그는 10명(2팀) 이상이 필요합니다.")
        teams = make_teams(playing, k)
        teams.sort(key=lambda t: -sum(p["rating"] for p in t))  # 시드: 팀 점수 순
        result["teams"] = [_team_out(t, None, TEAM_NAMES[i] if i < len(TEAM_NAMES) else f"{i + 1}팀") for i, t in enumerate(teams)]
        totals = [t["total"] for t in result["teams"]]
        result["team_spread"] = max(totals) - min(totals)
        result["matches"] = _bracket(k) if mode == "tournament" else _round_robin(k)
        return result
    raise ValueError("알 수 없는 방식입니다.")
