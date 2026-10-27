"""
app/champion_stats.py

수집된 실제 매치(collected_matches) 기반 챔피언 티어표 및 라인별 통계 계산 엔진.
- 가장 최근 game_version 매치만 대상 (버전 문자열 숫자 비교)
- early_surrender 매치 제외
- 빈 포지션 제외 (TOP, JUG, MID, BOT, SUP 매핑)
- 최소 표본수 미만 제외 (지어내거나 보정하지 않음)
- 점수 = win_rate + pick_rate * 0.2 + ban_rate * 0.1
  상위 5% OP, 다음 15% 1티어, 다음 25% 2티어, 다음 30% 3티어, 다음 15% 4티어, 나머지 5티어
- 결과 10분 캐시 (포지션별)
"""
import json
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from app.champion_engine import ALL_CHAMPIONS, find_champion
from app.database import get_connection
from app.ddragon import champion_img

# Data Dragon 챔피언 숫자 키(key: "86") -> 챔피언 메타데이터 매핑
_CHAMP_BY_KEY: Dict[int, Dict[str, Any]] = {}
for _c in ALL_CHAMPIONS:
    _k = _c.get("key")
    if _k is not None and str(_k).isdigit():
        _CHAMP_BY_KEY[int(_k)] = _c

# 포지션 매핑: TOP->TOP, JUNGLE->JUG, MIDDLE->MID, BOTTOM->BOT, UTILITY->SUP
POSITION_MAP: Dict[str, str] = {
    "TOP": "TOP",
    "JUNGLE": "JUG",
    "JUG": "JUG",
    "MIDDLE": "MID",
    "MID": "MID",
    "BOTTOM": "BOT",
    "BOT": "BOT",
    "UTILITY": "SUP",
    "SUP": "SUP",
}

# 10분 모듈 캐시 (key -> (timestamp, dict))
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
CACHE_TTL: float = 600.0
# 최신 패치 매치가 이보다 적으면 직전 패치 매치를 합쳐 계산한다 (패치 라벨은 "16.22+16.21")
MIN_LATEST_PATCH_GAMES: int = 500
# 패치 변동: 승률 차이가 표준오차의 이 배수 이상일 때만 표시 (작은 표본의 우연한 변화 제외)
SHIFT_MIN_Z: float = 2.0


def clear_cache() -> None:
    """테스트 또는 강제 갱신용 캐시 비우기"""
    _CACHE.clear()
    _MATCHES_MEMO.clear()


# 티어 점수용 승률: 표본이 작을수록 50%로 당긴다 (가상의 200게임 50% 승률을 더함).
# 화면에 보이는 승률은 실제 값 그대로이고, 45게임 64% 같은 우연이 OP로 올라가는 것만 막는다.
SHRINK_PRIOR_GAMES = 200


def _shrunk_win_rate(wins: int, games: int) -> float:
    return (wins + SHRINK_PRIOR_GAMES * 0.5) / (games + SHRINK_PRIOR_GAMES) * 100


def _parse_version(v: Optional[str]) -> Tuple[int, ...]:
    """버전 문자열을 숫자로 비교하기 위해 정수 튜플로 파싱 (예: '16.21' -> (16, 21))"""
    if not v:
        return (-1,)
    parts = []
    for chunk in str(v).strip().split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if digits:
            parts.append(int(digits))
        else:
            parts.append(0)
    return tuple(parts) if parts else (-1,)


def _empty_response(patch: str = "", note: str = "아직 수집된 매치가 부족합니다.") -> Dict[str, Any]:
    return {
        "results": [],
        "summary": {
            "op_count": 0,
            "tier1_count": 0,
            "tier2_count": 0,
            "tier3_count": 0,
            "tier4_count": 0,
            "tier5_count": 0,
            "total_games": 0,
        },
        "patch": patch,
        "sample_note": note,
        "source": "collected_matches",
    }


def _resolve_champion(champ_id: Any) -> Optional[Dict[str, Any]]:
    """정수 key, 문자열 ID 또는 한글 챔피언명으로 챔피언 메타데이터 조회"""
    if champ_id is None:
        return None
    if isinstance(champ_id, int):
        return _CHAMP_BY_KEY.get(champ_id)
    if isinstance(champ_id, str):
        c_str = champ_id.strip()
        if c_str.isdigit():
            return _CHAMP_BY_KEY.get(int(c_str))
        return find_champion(c_str)
    return None


_MATCHES_MEMO: Dict[str, Any] = {}


def _get_latest_valid_matches() -> Tuple[str, List[Dict[str, Any]]]:
    """최신 패치 매치 목록 (10분 메모: 챔피언마다 빌드를 열 때 전체 매치를 다시 읽지 않도록)"""
    hit = _MATCHES_MEMO.get("latest")
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    res = _load_latest_valid_matches()
    _MATCHES_MEMO["latest"] = (time.time(), res)
    return res


def _load_latest_valid_matches() -> Tuple[str, List[Dict[str, Any]]]:
    """collected_matches 테이블에서 가장 최근 game_version 매치 중 early_surrender 제외 매치 조회"""
    conn = get_connection()
    try:
        cur = conn.cursor()
        table_exists = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collected_matches'"
        ).fetchone()
        if not table_exists:
            return ("", [])

        ver_rows = cur.execute(
            "SELECT DISTINCT game_version FROM collected_matches WHERE game_version IS NOT NULL AND game_version != ''"
        ).fetchall()
        if not ver_rows:
            return ("", [])

        versions = [r[0] if isinstance(r, (tuple, list)) else r["game_version"] for r in ver_rows]
        versions = [v for v in versions if v]
        if not versions:
            return ("", [])

        ordered = sorted(versions, key=_parse_version, reverse=True)
        latest_version = ordered[0]
        match_rows = cur.execute(
            "SELECT data FROM collected_matches WHERE game_version = ?",
            (latest_version,),
        ).fetchall()
        # 새 패치 직후엔 표본이 거의 없어 모든 통계가 비므로, 충분히 쌓일 때까지 직전 패치를 함께 쓴다
        if len(match_rows) < MIN_LATEST_PATCH_GAMES and len(ordered) > 1:
            match_rows += cur.execute(
                "SELECT data FROM collected_matches WHERE game_version = ?",
                (ordered[1],),
            ).fetchall()
            latest_version = f"{ordered[0]}+{ordered[1]}"
    finally:
        conn.close()

    valid_matches: List[Dict[str, Any]] = []
    for r in match_rows:
        raw_data = r[0] if isinstance(r, (tuple, list)) else r["data"]
        if not raw_data:
            continue
        if isinstance(raw_data, str):
            try:
                m = json.loads(raw_data)
            except Exception:
                continue
        elif isinstance(raw_data, dict):
            m = raw_data
        else:
            continue

        if m.get("early_surrender"):
            continue
        valid_matches.append(m)

    return (latest_version, valid_matches)


def _filter_matches_by_tier(valid_matches: List[Dict[str, Any]], allowed_tiers: Any) -> List[Dict[str, Any]]:
    """게임 티어 필터 (allowed_tiers가 없으면 그대로)"""
    if not allowed_tiers:
        return valid_matches
    from app.apex_tiers import game_tier, load_apex_map
    apex = load_apex_map()
    return [m for m in valid_matches
            if game_tier([p.get("puuid") for p in m.get("participants") or []], apex) in allowed_tiers]


def _evaluate_tier_rows(
    valid_matches: List[Dict[str, Any]],
    pos_key: str,
    min_games: Optional[int],
    sort: Optional[str],
) -> Tuple[List[Dict[str, Any]], int]:
    """매치 목록 하나를 집계해 점수·티어·rank가 매겨진 행 목록과 최소 표본 기준을 돌려준다 (현재/직전 패치 공용)"""
    target_match_count = len(valid_matches)
    ban_counts: Dict[int, int] = {}
    champ_pos_stats: Dict[Tuple[int, str], Dict[str, Any]] = {}
    # 맞라인 상대 집계: (내 챔피언 ID, 내 포지션, 상대 챔피언 ID) -> {"games": int, "wins": int}
    matchup_pair_stats: Dict[Tuple[int, str, int], Dict[str, int]] = {}

    for m in valid_matches:
        # 밴 카운트 (매치당 챔피언 1회)
        match_bans = set()
        for b in (m.get("bans") or []):
            try:
                bid = int(b)
                if bid > 0:
                    match_bans.add(bid)
            except (ValueError, TypeError):
                continue
        for bid in match_bans:
            ban_counts[bid] = ban_counts.get(bid, 0) + 1

        # 참가자 집계 및 맞라인 분류
        pos_participants: Dict[str, List[Dict[str, Any]]] = {}
        for p in (m.get("participants") or []):
            raw_pos = (p.get("position") or "").strip().upper()
            pos = POSITION_MAP.get(raw_pos)
            if not pos:
                # 빈 포지션 참가자는 제외
                continue

            raw_cid = p.get("champion_id")
            if raw_cid is None:
                continue
            try:
                cid = int(raw_cid)
            except (ValueError, TypeError):
                continue
            if cid <= 0:
                continue

            pos_participants.setdefault(pos, []).append(p)

            st_key = (cid, pos)
            st = champ_pos_stats.get(st_key)
            if not st:
                st = {
                    "champion_id": cid,
                    "position": pos,
                    "games": 0,
                    "wins": 0,
                    "kills": 0,
                    "deaths": 0,
                    "assists": 0,
                }
                champ_pos_stats[st_key] = st

            st["games"] += 1
            if p.get("win"):
                st["wins"] += 1
            st["kills"] += int(p.get("kills") or 0)
            st["deaths"] += int(p.get("deaths") or 0)
            st["assists"] += int(p.get("assists") or 0)

        # 맞라인 집계: 같은 match, 같은 pos, 다른 team
        for pos, plist in pos_participants.items():
            for i in range(len(plist)):
                for j in range(i + 1, len(plist)):
                    p1 = plist[i]
                    p2 = plist[j]
                    if p1.get("team_id") != p2.get("team_id"):
                        c1 = int(p1["champion_id"])
                        c2 = int(p2["champion_id"])

                        k1 = (c1, pos, c2)
                        st1 = matchup_pair_stats.setdefault(k1, {"games": 0, "wins": 0})
                        st1["games"] += 1
                        if p1.get("win"):
                            st1["wins"] += 1

                        k2 = (c2, pos, c1)
                        st2 = matchup_pair_stats.setdefault(k2, {"games": 0, "wins": 0})
                        st2["games"] += 1
                        if p2.get("win"):
                            st2["wins"] += 1

    # 포지션 필터링
    candidates_data: List[Dict[str, Any]] = []
    for (cid, pos), st in champ_pos_stats.items():
        if pos_key != "ALL" and pos != pos_key:
            continue
        candidates_data.append(st)

    # 최소 표본: min_games가 None이면 max(30, 대상 매치 수 * 0.005)
    if min_games is None:
        min_games_threshold = max(30, int(target_match_count * 0.005))
    else:
        min_games_threshold = int(min_games)

    filtered_candidates = [c for c in candidates_data if c["games"] >= min_games_threshold]

    evaluated: List[Dict[str, Any]] = []
    for c in filtered_candidates:
        cid = c["champion_id"]
        pos = c["position"]
        games = c["games"]
        wins = c["wins"]

        win_rate = round((wins / games) * 100, 1)
        pick_rate = round((games / target_match_count) * 100, 1)
        ban_matches = ban_counts.get(cid, 0)
        ban_rate = round((ban_matches / target_match_count) * 100, 1)
        kda = round((c["kills"] + c["assists"]) / max(1, c["deaths"]), 2)
        score = round(_shrunk_win_rate(wins, games) + (pick_rate * 0.2) + (ban_rate * 0.1), 2)

        info = _CHAMP_BY_KEY.get(cid)
        if info:
            champ_id_str = info["id"]
            champ_name = info["name"]
            champ_img_url = champion_img(info.get("image") or champ_id_str)
        else:
            champ_id_str = str(cid)
            champ_name = str(cid)
            champ_img_url = champion_img(str(cid))

        # 카운터: 그 챔피언·포지션의 맞라인 상대 중 games >= 10이고 내 승률 가장 낮은 순 3개
        champ_counters = []
        for (my_cid, my_pos, opp_cid), mst in matchup_pair_stats.items():
            if my_cid == cid and my_pos == pos and mst["games"] >= 10:
                mst_g = mst["games"]
                mst_w = mst["wins"]
                mst_wr = round((mst_w / mst_g) * 100, 1)
                champ_counters.append((mst_wr, mst_g, opp_cid))

        # 내 승률 오름차순 (가장 낮은 순), 게임 수 내림차순
        champ_counters.sort(key=lambda x: (x[0], -x[1]))
        top_counters = []
        for mst_wr, mst_g, opp_cid in champ_counters[:3]:
            opp_info = _CHAMP_BY_KEY.get(opp_cid)
            if opp_info:
                o_id = opp_info["id"]
                o_name = opp_info["name"]
                o_img = champion_img(opp_info.get("image") or o_id)
            else:
                o_id = str(opp_cid)
                o_name = str(opp_cid)
                o_img = champion_img(str(opp_cid))
            top_counters.append({
                "id": o_id,
                "name": o_name,
                "image": o_img,
                "win_rate": mst_wr,
                "games": mst_g,
            })

        evaluated.append({
            "id": champ_id_str,
            "name": champ_name,
            "image": champ_img_url,
            "position": pos,
            "games": games,
            "win_rate": win_rate,
            "pick_rate": pick_rate,
            "ban_rate": ban_rate,
            "kda": kda,
            "score": score,
            "counters": top_counters,
        })

    # 티어 산정: 점수 내림차순 정렬 후 백분위 부여
    # 상위 5% -> OP, 다음 15% -> 1티어, 다음 25% -> 2티어, 다음 30% -> 3티어, 다음 15% -> 4티어, 나머지 -> 5티어
    evaluated.sort(
        key=lambda x: (x["score"], x["win_rate"], x["pick_rate"], x["games"]),
        reverse=True,
    )
    n_eval = len(evaluated)
    for idx, item in enumerate(evaluated):
        pct = idx / n_eval if n_eval > 0 else 0.0
        if pct < 0.05:
            tier = "OP"
            tier_num = 0
        elif pct < 0.20:
            tier = "1티어"
            tier_num = 1
        elif pct < 0.45:
            tier = "2티어"
            tier_num = 2
        elif pct < 0.75:
            tier = "3티어"
            tier_num = 3
        elif pct < 0.90:
            tier = "4티어"
            tier_num = 4
        else:
            tier = "5티어"
            tier_num = 5

        item["tier"] = tier
        item["tier_num"] = tier_num
        item["is_op"] = (tier == "OP")

    # 파라미터 정렬 기준 반영 (win_rate, pick_rate, ban_rate, games)
    if sort == "win_rate":
        evaluated.sort(key=lambda x: (x["win_rate"], x["score"]), reverse=True)
    elif sort == "pick_rate":
        evaluated.sort(key=lambda x: (x["pick_rate"], x["win_rate"]), reverse=True)
    elif sort == "ban_rate":
        evaluated.sort(key=lambda x: (x["ban_rate"], x["pick_rate"]), reverse=True)
    elif sort == "games":
        evaluated.sort(key=lambda x: (x["games"], x["win_rate"]), reverse=True)

    # rank 순위 부여 (1부터)
    for idx, item in enumerate(evaluated):
        item["rank"] = idx + 1

    return evaluated, min_games_threshold


def compute_tier_list(
    position: str = "all",
    min_games: Optional[int] = None,
    sort: Optional[str] = None,
    tier: Optional[str] = None,
) -> Dict[str, Any]:
    """
    collected_matches 테이블에서 가장 최근 game_version 매치를 집계하여
    포지션별/전체 챔피언 티어표를 계산합니다.
    """
    pos_key = (position or "all").strip().upper()
    tier_key = (tier or "").strip().upper()
    allowed_tiers = BUILD_TIER_FILTERS.get(tier_key)
    cache_key = f"{pos_key}:{min_games}:{sort}:{tier_key if allowed_tiers else ''}"
    now = time.time()

    if cache_key in _CACHE:
        cached_time, cached_val = _CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_val

    latest_version, valid_matches = _get_latest_valid_matches()
    valid_matches = _filter_matches_by_tier(valid_matches, allowed_tiers)
    target_match_count = len(valid_matches)
    if target_match_count == 0:
        res = _empty_response(patch=latest_version)
        _CACHE[cache_key] = (now, res)
        return res

    evaluated, min_games_threshold = _evaluate_tier_rows(valid_matches, pos_key, min_games, sort)

    # 패치 변동: 직전 패치를 같은 포지션·티어 필터·정렬로 순위 매겨 비교 (합친 패치 라벨이면 비교하지 않음)
    prev_version: Optional[str] = None
    if latest_version and "+" not in latest_version:
        cur_ver, prev_ver = _get_two_latest_versions()
        if cur_ver == latest_version and prev_ver:
            prev_version = prev_ver
    prev_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if prev_version:
        prev_matches = _filter_matches_by_tier(_get_valid_matches_for_version(prev_version), allowed_tiers)
        if prev_matches:
            prev_rows, _ = _evaluate_tier_rows(prev_matches, pos_key, min_games, sort)
            prev_map = {(r["id"], r["position"]): r for r in prev_rows}
        else:
            prev_version = None
    for item in evaluated:
        prev = prev_map.get((item["id"], item["position"]))
        item["prev_rank"] = prev["rank"] if prev else None
        item["prev_win_rate"] = prev["win_rate"] if prev else None

    summary = {
        "op_count": sum(1 for r in evaluated if r["tier"] == "OP"),
        "tier1_count": sum(1 for r in evaluated if r["tier"] == "1티어"),
        "tier2_count": sum(1 for r in evaluated if r["tier"] == "2티어"),
        "tier3_count": sum(1 for r in evaluated if r["tier"] == "3티어"),
        "tier4_count": sum(1 for r in evaluated if r["tier"] == "4티어"),
        "tier5_count": sum(1 for r in evaluated if r["tier"] == "5티어"),
        "total_games": target_match_count,
    }

    sample_note = (
        f"{target_match_count:,}게임 · {int(min_games_threshold)}게임 미만 제외"
    )

    res = {
        "results": evaluated,
        "summary": summary,
        "patch": latest_version,
        "prev_patch": prev_version,
        "sample_note": sample_note,
        "source": "collected_matches",
    }
    _CACHE[cache_key] = (now, res)
    return res


def compute_matchups(champion_id: Any) -> Dict[str, Any]:
    """
    수집된 실제 매치 기반 특정 챔피언의 맞라인 상대별 상성 통계 계산.
    - 맞라인: 같은 매치에서 같은 position이고 팀이 다른 두 참가자
    - 최신 game_version, early_surrender 제외
    - 최소 표본: games >= 10 만 포함
    - 10분 캐시
    """
    champ_meta = _resolve_champion(champion_id)
    if not champ_meta:
        return {
            "champion": {
                "id": str(champion_id),
                "name": str(champion_id),
                "image": champion_img(str(champion_id)),
            },
            "main_position": "",
            "total_games": 0,
            "matchups": [],
            "patch": "",
            "sample_note": "챔피언 정보를 찾을 수 없습니다.",
        }

    target_cid = int(champ_meta["key"])
    cache_key = f"matchups:{target_cid}"
    now = time.time()
    if cache_key in _CACHE:
        cached_time, cached_val = _CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_val

    latest_version, valid_matches = _get_latest_valid_matches()
    champ_info = {
        "id": champ_meta["id"],
        "name": champ_meta["name"],
        "image": champion_img(champ_meta.get("image") or champ_meta["id"]),
    }
    if not valid_matches:
        res = {
            "champion": champ_info,
            "main_position": "",
            "total_games": 0,
            "matchups": [],
            "patch": latest_version,
            "sample_note": "아직 수집된 매치가 부족합니다.",
        }
        _CACHE[cache_key] = (now, res)
        return res

    pos_counts: Dict[str, int] = {}
    # 라인별로 따로 모은 뒤 주 라인 것만 쓴다 (원딜로 한 판의 상대가 미드 상성에 섞이지 않게)
    opp_by_pos: Dict[str, Dict[int, Dict[str, Any]]] = {}

    for m in valid_matches:
        pos_participants: Dict[str, List[Dict[str, Any]]] = {}
        for p in (m.get("participants") or []):
            raw_pos = (p.get("position") or "").strip().upper()
            pos = POSITION_MAP.get(raw_pos)
            if not pos:
                continue
            raw_cid = p.get("champion_id")
            if raw_cid is None:
                continue
            try:
                cid = int(raw_cid)
            except (ValueError, TypeError):
                continue
            if cid <= 0:
                continue
            pos_participants.setdefault(pos, []).append(p)

        for pos, plist in pos_participants.items():
            my_plist = [p for p in plist if int(p.get("champion_id") or 0) == target_cid]
            if not my_plist:
                continue
            for my_p in my_plist:
                pos_counts[pos] = pos_counts.get(pos, 0) + 1
                opponents = [p for p in plist if p.get("team_id") != my_p.get("team_id")]
                for opp_p in opponents:
                    try:
                        opp_cid = int(opp_p.get("champion_id") or 0)
                    except (ValueError, TypeError):
                        continue
                    if opp_cid <= 0:
                        continue

                    st = opp_by_pos.setdefault(pos, {}).setdefault(opp_cid, {
                        "games": 0, "wins": 0,
                        "kills": 0, "deaths": 0, "assists": 0,
                        "gold": 0, "opp_gold": 0,
                        "cs": 0.0, "opp_cs": 0.0,
                        "damage": 0, "opp_damage": 0,
                    })
                    st["games"] += 1
                    if my_p.get("win"):
                        st["wins"] += 1
                    st["kills"] += int(my_p.get("kills") or 0)
                    st["deaths"] += int(my_p.get("deaths") or 0)
                    st["assists"] += int(my_p.get("assists") or 0)
                    st["gold"] += int(my_p.get("gold") or 0)
                    st["opp_gold"] += int(opp_p.get("gold") or 0)
                    st["cs"] += float(my_p.get("cs") or 0)
                    st["opp_cs"] += float(opp_p.get("cs") or 0)
                    st["damage"] += int(my_p.get("damage") or 0)
                    st["opp_damage"] += int(opp_p.get("damage") or 0)

    main_position = max(pos_counts, key=pos_counts.get) if pos_counts else ""
    total_games = pos_counts.get(main_position, 0)
    opp_stats = opp_by_pos.get(main_position, {})

    matchups: List[Dict[str, Any]] = []
    for opp_cid, st in opp_stats.items():
        if st["games"] < 10:
            continue
        g = st["games"]
        w = st["wins"]
        wr = round((w / g) * 100, 1)
        kda = round((st["kills"] + st["assists"]) / max(1, st["deaths"]), 2)
        gold_diff = round((st["gold"] - st["opp_gold"]) / g)
        cs_diff = round((st["cs"] - st["opp_cs"]) / g, 1)
        damage_diff = round((st["damage"] - st["opp_damage"]) / g)

        opp_info = _CHAMP_BY_KEY.get(opp_cid)
        if opp_info:
            o_id = opp_info["id"]
            o_name = opp_info["name"]
            o_img = champion_img(opp_info.get("image") or o_id)
        else:
            o_id = str(opp_cid)
            o_name = str(opp_cid)
            o_img = champion_img(str(opp_cid))

        matchups.append({
            "id": o_id,
            "name": o_name,
            "image": o_img,
            "champion": {"id": o_id, "name": o_name, "image": o_img},
            "games": g,
            "wins": w,
            "win_rate": wr,
            "kda": kda,
            "gold_diff": gold_diff,
            "cs_diff": cs_diff,
            "damage_diff": damage_diff,
        })

    matchups.sort(key=lambda x: x["games"], reverse=True)
    sample_note = (
        f"최신 패치 {latest_version} 솔로랭크 기준 · 상대별 10게임 이상만 표시"
        if matchups
        else "아직 표본이 부족합니다(상대별 10게임 이상만 표시)"
    )

    res = {
        "champion": champ_info,
        "main_position": main_position,
        "total_games": total_games,
        "matchups": matchups,
        "patch": latest_version,
        "sample_note": sample_note,
    }
    _CACHE[cache_key] = (now, res)
    return res


def compute_head_to_head(champ_a_id: Any, champ_b_id: Any) -> Dict[str, Any]:
    """
    수집된 실제 매치 기반 두 챔피언의 맞라인 1:1 상대전적 통계 계산.
    - 둘이 같은 매치에서 같은 position이고 팀이 다른 경기만 집계
    - 최신 game_version, early_surrender 제외
    - 0경기면 games: 0과 안내 문구만 반환
    - 10분 캐시
    """
    meta_a = _resolve_champion(champ_a_id)
    meta_b = _resolve_champion(champ_b_id)
    if not meta_a or not meta_b:
        return {
            "champ_a": {"id": str(champ_a_id), "name": str(champ_a_id), "image": champion_img(str(champ_a_id))},
            "champ_b": {"id": str(champ_b_id), "name": str(champ_b_id), "image": champion_img(str(champ_b_id))},
            "games": 0,
            "wins": 0,
            "win_rate": 0.0,
            "message": "챔피언 정보를 찾을 수 없습니다.",
            "patch": "",
            "sample_note": "챔피언 정보를 찾을 수 없습니다.",
        }

    cid_a = int(meta_a["key"])
    cid_b = int(meta_b["key"])
    cache_key = f"h2h:{cid_a}:{cid_b}"
    now = time.time()
    if cache_key in _CACHE:
        cached_time, cached_val = _CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_val

    latest_version, valid_matches = _get_latest_valid_matches()
    info_a = {
        "id": meta_a["id"],
        "name": meta_a["name"],
        "image": champion_img(meta_a.get("image") or meta_a["id"]),
    }
    info_b = {
        "id": meta_b["id"],
        "name": meta_b["name"],
        "image": champion_img(meta_b.get("image") or meta_b["id"]),
    }

    games = 0
    a_wins = 0
    tot_a_kills = 0
    tot_a_deaths = 0
    tot_a_assists = 0
    tot_a_cs = 0.0
    tot_a_gold = 0
    tot_a_damage = 0

    tot_b_kills = 0
    tot_b_deaths = 0
    tot_b_assists = 0
    tot_b_cs = 0.0
    tot_b_gold = 0
    tot_b_damage = 0

    for m in valid_matches:
        pos_participants: Dict[str, List[Dict[str, Any]]] = {}
        for p in (m.get("participants") or []):
            raw_pos = (p.get("position") or "").strip().upper()
            pos = POSITION_MAP.get(raw_pos)
            if not pos:
                continue
            raw_cid = p.get("champion_id")
            if raw_cid is None:
                continue
            try:
                cid = int(raw_cid)
            except (ValueError, TypeError):
                continue
            if cid in (cid_a, cid_b):
                pos_participants.setdefault(pos, []).append(p)

        for pos, plist in pos_participants.items():
            for i in range(len(plist)):
                for j in range(i + 1, len(plist)):
                    p1 = plist[i]
                    p2 = plist[j]
                    if p1.get("team_id") != p2.get("team_id"):
                        c1 = int(p1["champion_id"])
                        c2 = int(p2["champion_id"])
                        if (c1 == cid_a and c2 == cid_b) or (c1 == cid_b and c2 == cid_a):
                            pa = p1 if c1 == cid_a else p2
                            pb = p2 if c1 == cid_a else p1
                            games += 1
                            if pa.get("win"):
                                a_wins += 1
                            tot_a_kills += int(pa.get("kills") or 0)
                            tot_a_deaths += int(pa.get("deaths") or 0)
                            tot_a_assists += int(pa.get("assists") or 0)
                            tot_a_cs += float(pa.get("cs") or 0)
                            tot_a_gold += int(pa.get("gold") or 0)
                            tot_a_damage += int(pa.get("damage") or 0)

                            tot_b_kills += int(pb.get("kills") or 0)
                            tot_b_deaths += int(pb.get("deaths") or 0)
                            tot_b_assists += int(pb.get("assists") or 0)
                            tot_b_cs += float(pb.get("cs") or 0)
                            tot_b_gold += int(pb.get("gold") or 0)
                            tot_b_damage += int(pb.get("damage") or 0)

    if games == 0:
        res = {
            "champ_a": info_a,
            "champ_b": info_b,
            "games": 0,
            "wins": 0,
            "win_rate": 0.0,
            "message": "맞대결 전적 데이터가 없습니다. (수집된 0게임)",
            "patch": latest_version,
            "sample_note": "맞대결 전적이 없습니다.",
        }
        _CACHE[cache_key] = (now, res)
        return res

    a_win_rate = round((a_wins / games) * 100, 1)
    stats_a = {
        "kda": round((tot_a_kills + tot_a_assists) / max(1, tot_a_deaths), 2),
        "kills": round(tot_a_kills / games, 1),
        "deaths": round(tot_a_deaths / games, 1),
        "assists": round(tot_a_assists / games, 1),
        "cs": round(tot_a_cs / games, 1),
        "gold": round(tot_a_gold / games),
        "damage": round(tot_a_damage / games),
    }
    stats_b = {
        "kda": round((tot_b_kills + tot_b_assists) / max(1, tot_b_deaths), 2),
        "kills": round(tot_b_kills / games, 1),
        "deaths": round(tot_b_deaths / games, 1),
        "assists": round(tot_b_assists / games, 1),
        "cs": round(tot_b_cs / games, 1),
        "gold": round(tot_b_gold / games),
        "damage": round(tot_b_damage / games),
    }
    res = {
        "champ_a": {**info_a, **stats_a, "stats": stats_a},
        "champ_b": {**info_b, **stats_b, "stats": stats_b},
        "games": games,
        "wins": a_wins,
        "win_rate": a_win_rate,
        "gold_diff": round((tot_a_gold - tot_b_gold) / games),
        "cs_diff": round((tot_a_cs - tot_b_cs) / games, 1),
        "damage_diff": round((tot_a_damage - tot_b_damage) / games),
        "patch": latest_version,
        "sample_note": f"최신 패치 {latest_version} 맞라인 {games}게임 기준",
    }
    _CACHE[cache_key] = (now, res)
    return res


def compute_duo_synergy(
    kind: str = "bot",
    filter_a: Optional[str] = None,
    filter_b: Optional[str] = None,
) -> Dict[str, Any]:
    """
    수집된 실제 매치 기반 같은 팀 2인 조합(듀오 시너지) 통계 계산.
    - kind:
      "bot": BOTTOM(a) + UTILITY(b)
      "mid_jug": MIDDLE(a) + JUNGLE(b)
      "top_jug": TOP(a) + JUNGLE(b)
    - 한 팀에 그 포지션이 정확히 한 명씩일 때만 한 조합으로 집계
    - 최신 game_version, early_surrender 제외
    - 최소 표본수: games >= max(10, 대상 매치 수 * 0.002)
    - 점수 = win_rate + pick_rate * 0.2
    - 티어: 상위 5% OP, 15% 1, 25% 2, 30% 3, 15% 4, 나머지 5
    - 필터: filter_a / filter_b 영문 ID 또는 한글 이름 대소문자 무시 부분 일치
    - 10분 모듈 캐시 (kind 단위, 필터는 캐시된 전체 결과에 적용)
    """
    kind_clean = (kind or "bot").strip().lower()
    if kind_clean == "mid_jug":
        pos_a, pos_b = "MID", "JUG"
    elif kind_clean == "top_jug":
        pos_a, pos_b = "TOP", "JUG"
    else:
        kind_clean = "bot"
        pos_a, pos_b = "BOT", "SUP"

    cache_key = f"duo:{kind_clean}"
    now = time.time()

    cached_base: Optional[Dict[str, Any]] = None
    if cache_key in _CACHE:
        cached_time, cached_val = _CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            cached_base = cached_val

    if cached_base is None:
        latest_version, valid_matches = _get_latest_valid_matches()
        target_match_count = len(valid_matches)
        if target_match_count == 0:
            cached_base = {
                "kind": kind_clean,
                "total_games": 0,
                "patch": latest_version,
                "sample_note": "아직 수집된 매치가 부족합니다.",
                "duos": [],
            }
            _CACHE[cache_key] = (now, cached_base)
        else:
            pos_champ_games: Dict[Tuple[str, int], int] = {}
            pos_champ_wins: Dict[Tuple[str, int], int] = {}
            duo_stats: Dict[Tuple[int, int], Dict[str, int]] = {}

            for m in valid_matches:
                team_participants: Dict[Any, Dict[str, List[Dict[str, Any]]]] = {}
                for p in (m.get("participants") or []):
                    raw_pos = (p.get("position") or "").strip().upper()
                    pos = POSITION_MAP.get(raw_pos)
                    if not pos:
                        continue
                    raw_cid = p.get("champion_id")
                    if raw_cid is None:
                        continue
                    try:
                        cid = int(raw_cid)
                    except (ValueError, TypeError):
                        continue

                    tid = p.get("team_id")
                    win = bool(p.get("win"))

                    pos_champ_games[(pos, cid)] = pos_champ_games.get((pos, cid), 0) + 1
                    if win:
                        pos_champ_wins[(pos, cid)] = pos_champ_wins.get((pos, cid), 0) + 1

                    team_participants.setdefault(tid, {}).setdefault(pos, []).append(p)

                for tid, pos_map in team_participants.items():
                    list_a = pos_map.get(pos_a) or []
                    list_b = pos_map.get(pos_b) or []
                    if len(list_a) == 1 and len(list_b) == 1:
                        pa = list_a[0]
                        pb = list_b[0]
                        try:
                            cid_a = int(pa["champion_id"])
                            cid_b = int(pb["champion_id"])
                        except (ValueError, TypeError):
                            continue

                        duo_key = (cid_a, cid_b)
                        if duo_key not in duo_stats:
                            duo_stats[duo_key] = {"games": 0, "wins": 0}
                        duo_stats[duo_key]["games"] += 1
                        if pa.get("win"):
                            duo_stats[duo_key]["wins"] += 1

            min_sample_threshold = max(10.0, target_match_count * 0.002)
            evaluated: List[Dict[str, Any]] = []

            for (cid_a, cid_b), st in duo_stats.items():
                games = st["games"]
                if games < min_sample_threshold:
                    continue
                wins = st["wins"]
                win_rate = round((wins / games) * 100, 1)
                pick_rate = round((games / target_match_count) * 100, 2)

                a_g = pos_champ_games.get((pos_a, cid_a), 0)
                a_w = pos_champ_wins.get((pos_a, cid_a), 0)
                a_wr = (a_w / a_g * 100) if a_g > 0 else 0.0

                b_g = pos_champ_games.get((pos_b, cid_b), 0)
                b_w = pos_champ_wins.get((pos_b, cid_b), 0)
                b_wr = (b_w / b_g * 100) if b_g > 0 else 0.0

                expected_win_rate = round((a_wr + b_wr) / 2.0, 1)
                synergy_delta = round(win_rate - expected_win_rate, 1)
                score = round(_shrunk_win_rate(st["wins"], games) + pick_rate * 0.2, 2)

                meta_a = _resolve_champion(cid_a)
                meta_b = _resolve_champion(cid_b)

                a_id = meta_a["id"] if meta_a else str(cid_a)
                a_name = meta_a["name"] if meta_a else str(cid_a)
                a_img = champion_img(meta_a.get("image") or meta_a["id"]) if meta_a else champion_img(str(cid_a))

                b_id = meta_b["id"] if meta_b else str(cid_b)
                b_name = meta_b["name"] if meta_b else str(cid_b)
                b_img = champion_img(meta_b.get("image") or meta_b["id"]) if meta_b else champion_img(str(cid_b))

                row: Dict[str, Any] = {
                    "a_id": a_id,
                    "a_name": a_name,
                    "a_image": a_img,
                    "b_id": b_id,
                    "b_name": b_name,
                    "b_image": b_img,
                    "games_played": games,
                    "wins": wins,
                    "win_rate": win_rate,
                    "pick_rate": pick_rate,
                    "expected_win_rate": expected_win_rate,
                    "synergy_delta": synergy_delta,
                    "score": score,
                }

                if kind_clean == "bot":
                    row["adc_id"] = a_id
                    row["adc_name"] = a_name
                    row["adc_image"] = a_img
                    row["sup_id"] = b_id
                    row["sup_name"] = b_name
                    row["sup_image"] = b_img
                elif kind_clean == "mid_jug":
                    row["mid_id"] = a_id
                    row["mid_name"] = a_name
                    row["mid_image"] = a_img
                    row["jug_id"] = b_id
                    row["jug_name"] = b_name
                    row["jug_image"] = b_img
                elif kind_clean == "top_jug":
                    row["top_id"] = a_id
                    row["top_name"] = a_name
                    row["top_image"] = a_img
                    row["jug_id"] = b_id
                    row["jug_name"] = b_name
                    row["jug_image"] = b_img

                evaluated.append(row)

            evaluated.sort(
                key=lambda x: (x["score"], x["win_rate"], x["pick_rate"], x["games_played"]),
                reverse=True,
            )
            n_eval = len(evaluated)
            for idx, item in enumerate(evaluated):
                pct = idx / n_eval if n_eval > 0 else 0.0
                if pct < 0.05:
                    tier = "OP"
                    tier_badge = "OP"
                elif pct < 0.20:
                    tier = "1"
                    tier_badge = "1티어"
                elif pct < 0.45:
                    tier = "2"
                    tier_badge = "2티어"
                elif pct < 0.75:
                    tier = "3"
                    tier_badge = "3티어"
                elif pct < 0.90:
                    tier = "4"
                    tier_badge = "4티어"
                else:
                    tier = "5"
                    tier_badge = "5티어"

                item["tier"] = tier
                item["tier_badge"] = tier_badge
                item["rank"] = idx + 1

            min_display_games = int(min_sample_threshold) if min_sample_threshold.is_integer() else round(min_sample_threshold, 1)
            sample_note = (
                f"고티어 솔로랭크 {target_match_count}게임 기준 · 조합 {min_display_games}게임 미만 제외 · 기대 승률 = 두 챔피언 개별 승률 평균"
            )

            cached_base = {
                "kind": kind_clean,
                "total_games": target_match_count,
                "patch": latest_version,
                "sample_note": sample_note,
                "duos": evaluated,
            }
            _CACHE[cache_key] = (now, cached_base)

    all_duos = cached_base.get("duos", [])
    fa = (filter_a or "").strip().lower()
    fb = (filter_b or "").strip().lower()

    if not fa and not fb:
        filtered_duos = list(all_duos)
    else:
        filtered_duos = []
        for d in all_duos:
            if fa:
                match_a = (fa in d["a_id"].lower()) or (fa in d["a_name"].lower())
                if not match_a:
                    continue
            if fb:
                match_b = (fb in d["b_id"].lower()) or (fb in d["b_name"].lower())
                if not match_b:
                    continue
            filtered_duos.append(d)

    return {
        "kind": kind_clean,
        "total": len(filtered_duos),
        "duos": filtered_duos,
        "total_games": cached_base.get("total_games", 0),
        "patch": cached_base.get("patch", ""),
        "sample_note": cached_base.get("sample_note", ""),
    }


# ── 챔피언 빌드 (수집 매치의 종료 시점 인벤토리·룬·주문) ──────────────────────
# 압축 매치에는 구매 순서가 없으므로 "코어"는 게임 종료 시 가진 완성 아이템 3개 조합이다.
from itertools import combinations

from app import ddragon as _dd

BUILD_MIN_GAMES = 3

STAT_SHARD_NAMES: Dict[int, str] = {
    5008: "적응형 능력치",
    5005: "공격 속도",
    5007: "스킬 가속",
    5010: "이동 속도",
    5001: "체력 증가",
    5011: "체력",
    5013: "강인함 및 둔화 저항",
    5002: "방어력",
    5003: "마법 저항력",
}


# 능력치 파편 줄 (공격 / 유연 / 방어)
STAT_SHARD_ROWS: Tuple[Tuple[int, ...], ...] = ((5008, 5005, 5007), (5008, 5010, 5001), (5011, 5013, 5001))


def _item_kind(item_id: int) -> Optional[str]:
    """'legendary' | 'boots' | None (부품·소모품·장신구 등)"""
    item = _dd._ITEMS.get(str(item_id))
    if not item:
        return None
    tags = item.get("tags") or []
    gold = (item.get("gold") or {}).get("total", 0)
    # 3단계 신발은 Boots 태그가 없고 2단계 신발에서 올라간다
    built_from_boots = any("Boots" in ((_dd._ITEMS.get(str(f)) or {}).get("tags") or []) for f in item.get("from") or [])
    if "Boots" in tags or built_from_boots:
        return "boots" if gold >= 900 else None
    if "Consumable" in tags or "Trinket" in tags or item.get("into"):
        return None
    return "legendary" if gold >= 2200 else None


def _boots_upgrade(item_id: int) -> int:
    """2단계 신발이면 3단계 업그레이드 신발 ID, 아니면 그대로"""
    for nxt in (_dd._ITEMS.get(str(item_id)) or {}).get("into") or []:
        if _item_kind(int(nxt)) == "boots":
            return int(nxt)
    return item_id


def _tier_summary(champ_id: Optional[str], position: Optional[str]) -> Optional[Dict[str, Any]]:
    """티어표에서 이 챔피언·라인의 티어·승률·픽률·밴률·순위"""
    if not champ_id or not position:
        return None
    tl = compute_tier_list(position)
    rows = tl.get("results") or []
    for r in rows:
        if r.get("id") == champ_id:
            keys = ("tier", "tier_num", "rank", "games", "win_rate", "pick_rate", "ban_rate", "kda")
            return {**{k: r.get(k) for k in keys}, "rank_total": len(rows)}
    return None


def _prev_patch_stat(cid: int, pos: Optional[str]) -> Optional[Dict[str, Any]]:
    """직전 패치의 같은 챔피언·라인 게임 수·승률 (최신 패치와 비교용)"""
    if not pos:
        return None
    _, prev = _get_two_latest_versions()
    if not prev:
        return None
    key = f"prevpatch:{prev}:{cid}:{pos}"
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    games = wins = 0
    for m in _get_valid_matches_for_version(prev):
        for p in m.get("participants") or []:
            if p.get("champion_id") == cid and POSITION_MAP.get((p.get("position") or "").upper()) == pos:
                games += 1
                wins += 1 if p.get("win") else 0
    res = {"patch": prev, "games": games, "win_rate": round(wins / games * 100, 1) if games else None} if games else None
    _CACHE[key] = (time.time(), res)
    return res


# 게임 시간대별 승률 (파워 커브): 25분 미만 / 25~30 / 30~35 / 35분 이상
POWER_CURVE_BUCKETS = ((0, 25), (25, 30), (30, 35), (35, 999))


def compute_power_curve(cid: int, main_pos: Optional[str], matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stats = [{"games": 0, "wins": 0} for _ in POWER_CURVE_BUCKETS]
    for m in matches:
        dur = (m.get("duration") or 0) / 60
        if dur <= 0:
            continue
        me = next((p for p in m.get("participants") or [] if p.get("champion_id") == cid
                   and POSITION_MAP.get((p.get("position") or "").upper()) == main_pos), None)
        if not me:
            continue
        for i, (lo, hi) in enumerate(POWER_CURVE_BUCKETS):
            if lo <= dur < hi:
                stats[i]["games"] += 1
                stats[i]["wins"] += 1 if me.get("win") else 0
                break
    return [{"from": lo, "to": hi if hi < 999 else None, "games": st["games"],
             "win_rate": round(st["wins"] / st["games"] * 100, 1) if st["games"] else None}
            for (lo, hi), st in zip(POWER_CURVE_BUCKETS, stats)]


LANE_MATCHUP_MIN_GAMES = 5


def compute_lane_matchups(cid: int, main_pos: Optional[str], matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """main_pos 에서 맞라인 상대 챔피언별 승률 (상대별 LANE_MATCHUP_MIN_GAMES 게임 이상)."""
    stats: Dict[int, Dict[str, int]] = {}
    for m in matches:
        parts = m.get("participants") or []
        me = next((p for p in parts if p.get("champion_id") == cid
                   and POSITION_MAP.get((p.get("position") or "").upper()) == main_pos), None)
        if not me:
            continue
        opp = next((p for p in parts if p.get("team_id") != me.get("team_id")
                    and POSITION_MAP.get((p.get("position") or "").upper()) == main_pos), None)
        if not opp or not opp.get("champion_id"):
            continue
        st = stats.setdefault(int(opp["champion_id"]), {"games": 0, "wins": 0})
        st["games"] += 1
        st["wins"] += 1 if me.get("win") else 0
    rows = []
    for ck, st in stats.items():
        meta = _CHAMP_BY_KEY.get(ck)
        if not meta or st["games"] < LANE_MATCHUP_MIN_GAMES:
            continue
        rows.append({"id": meta.get("id"), "name": meta.get("name"),
                     "image": champion_img(meta.get("image") or meta["id"]),
                     "games": st["games"], "wins": st["wins"],
                     "win_rate": round(st["wins"] / st["games"] * 100, 1)})
    rows.sort(key=lambda r: r["win_rate"])
    return {
        "position": main_pos,
        "min_games": LANE_MATCHUP_MIN_GAMES,
        "hard": [r for r in rows if r["win_rate"] <= 50],
        "easy": [r for r in reversed(rows) if r["win_rate"] > 50],
    }


def _rate_row(st: Dict[str, int], total: int) -> Dict[str, Any]:
    games = st["games"]
    return {
        "games": games,
        "win_rate": round(st["wins"] / games * 100, 1) if games else None,
        "pick_rate": round(games / total * 100, 1) if total else None,
    }


def _top(counter: Dict[Any, Dict[str, int]], total: int, n: int) -> List[Tuple[Any, Dict[str, Any]]]:
    rows = [(k, st) for k, st in counter.items() if st["games"] >= BUILD_MIN_GAMES]
    rows.sort(key=lambda kv: (kv[1]["games"], kv[1]["wins"]), reverse=True)
    return [(k, _rate_row(st, total)) for k, st in rows[:n]]


# 빌드 티어 필터: 게임 티어(참가자 중 가장 많은 티어, app/apex_tiers.py) 기준
BUILD_TIER_FILTERS: Dict[str, Tuple[str, ...]] = {
    "MASTER_PLUS": ("MASTER", "GRANDMASTER", "CHALLENGER"),
    "GRANDMASTER_PLUS": ("GRANDMASTER", "CHALLENGER"),
    "CHALLENGER": ("CHALLENGER",),
}


def compute_champion_build(champion: Any, position: Optional[str] = None, tier: Optional[str] = None,
                           vs: Any = None) -> Optional[Dict[str, Any]]:
    """챔피언이 없으면 None. 표본이 없으면 빈 목록과 안내 문구.
    vs: 맞라인 상대 챔피언(id/이름). 주어지면 주 포지션에서 같은 포지션 상대가 그 챔피언인 게임만 집계."""
    meta = _resolve_champion(champion)
    if not meta or meta.get("key") is None:
        return None
    cid = int(meta["key"])
    vs_meta = None
    if vs is not None and str(vs).strip():
        vs_meta = _resolve_champion(vs)
        if not vs_meta or vs_meta.get("key") is None:
            return None
    vs_cid = int(vs_meta["key"]) if vs_meta else None
    want_pos = POSITION_MAP.get((position or "").strip().upper()) if position else None
    tier_key = (tier or "").strip().upper()
    allowed_tiers = BUILD_TIER_FILTERS.get(tier_key)

    cache_key = f"build:{cid}:{want_pos or ''}:{tier_key if allowed_tiers else ''}:{vs_cid or ''}"
    now = time.time()
    hit = _CACHE.get(cache_key)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]

    patch, matches = _get_latest_valid_matches()
    if allowed_tiers:
        from app.apex_tiers import game_tier, load_apex_map
        apex = load_apex_map()
        matches = [m for m in matches
                   if game_tier([p.get("puuid") for p in m.get("participants") or []], apex) in allowed_tiers]
    mine: List[Dict[str, Any]] = []
    pos_count: Dict[str, int] = {}
    for m in matches:
        parts = m.get("participants") or []
        for p in parts:
            if p.get("champion_id") != cid:
                continue
            pos = POSITION_MAP.get((p.get("position") or "").upper())
            if not pos:
                continue
            pos_count[pos] = pos_count.get(pos, 0) + 1
            entry = {**p, "_pos": pos}
            if vs_cid is not None:
                opp = next((o for o in parts if o.get("team_id") != p.get("team_id")
                            and POSITION_MAP.get((o.get("position") or "").upper()) == pos), None)
                entry["_opp"] = opp.get("champion_id") if opp else None
            mine.append(entry)

    main_pos = want_pos or (max(pos_count, key=pos_count.get) if pos_count else None)
    games = [p for p in mine if p["_pos"] == main_pos
             and (vs_cid is None or p.get("_opp") == vs_cid)]
    total = len(games)

    runes: Dict[Tuple, Dict[str, int]] = {}
    spells: Dict[Tuple, Dict[str, int]] = {}
    cores: Dict[Tuple, Dict[str, int]] = {}
    boots: Dict[int, Dict[str, int]] = {}
    items: Dict[int, Dict[str, int]] = {}
    skill_orders: Dict[str, Dict[str, Any]] = {}
    start_items: Dict[Tuple[int, ...], Dict[str, int]] = {}
    item_build_orders: Dict[Tuple[int, ...], Dict[str, int]] = {}
    # 4·5·6번째로 완성한 전설 아이템 (코어 3개 이후 선택지)
    late_items: List[Dict[int, Dict[str, int]]] = [{}, {}, {}]

    def add(counter, key, win):
        st = counter.setdefault(key, {"games": 0, "wins": 0})
        st["games"] += 1
        st["wins"] += 1 if win else 0

    for p in games:
        win = bool(p.get("win"))
        if p.get("keystone"):
            add(runes, (p.get("keystone"), p.get("primary_style"), p.get("sub_style")), win)
        sp = [s for s in (p.get("spells") or []) if s]
        if len(sp) == 2:
            add(spells, tuple(sorted(sp, key=lambda s: (s != 4, s))), win)  # 점멸 먼저
        legend, boot = [], None
        for it in p.get("items") or []:
            kind = _item_kind(it) if it else None
            if kind == "legendary" and it not in legend:
                legend.append(it)
            elif kind == "boots":
                boot = it
        for it in legend:
            add(items, it, win)
        if boot and main_pos == "MID":
            boot = _boots_upgrade(boot)
        if boot:
            add(boots, boot, win)
        # 종료 인벤토리에 이 3개가 모두 있던 게임 수 (슬롯 순서는 구매 순서가 아니므로 순서 없는 조합)
        for combo in combinations(sorted(legend), 3):
            add(cores, combo, win)

        # 타임라인 스킬 마스터 순서 집계 (skills 길이 6 이상)
        sk = p.get("skills")
        if sk and len(sk) >= 6:
            mastered = []
            sk_counts = {"Q": 0, "W": 0, "E": 0}
            slot_map = {1: "Q", 2: "W", 3: "E"}
            for s in sk:
                if s in slot_map:
                    s_name = slot_map[s]
                    sk_counts[s_name] += 1
                    if sk_counts[s_name] == 5 and s_name not in mastered:
                        mastered.append(s_name)
            rem = [k for k in ("Q", "W", "E") if k not in mastered]
            rem.sort(key=lambda k: (-sk_counts[k], ("Q", "W", "E").index(k)))
            ord_str = ">".join(mastered + rem)
            f3_str = ",".join(slot_map.get(s, "R" if s == 4 else str(s)) for s in sk[:3])
            st_sk = skill_orders.setdefault(ord_str, {"games": 0, "wins": 0, "first3": {}, "levels": [{} for _ in range(15)]})
            st_sk["games"] += 1
            if win:
                st_sk["wins"] += 1
            st_sk["first3"][f3_str] = st_sk["first3"].get(f3_str, 0) + 1
            # 레벨별(1~15) 어떤 스킬을 찍었는지: 표에서 레벨마다 가장 많이 찍은 스킬을 보여준다
            for lv, s in enumerate(sk[:15]):
                key = slot_map.get(s, "R" if s == 4 else None)
                if key:
                    st_sk["levels"][lv][key] = st_sk["levels"][lv].get(key, 0) + 1

        # 타임라인 시작 아이템 집계 (빈 리스트 제외)
        si = p.get("start_items")
        if si:
            add(start_items, tuple(sorted(si)), win)

        # 타임라인 아이템 구매 순서 집계 (전설 아이템 앞 3개 순서 그대로)
        io = p.get("item_order")
        if io:
            leg_order = []
            for it in io:
                if it and _item_kind(it) == "legendary" and it not in leg_order:
                    leg_order.append(it)
            if len(leg_order) >= 3:
                add(item_build_orders, tuple(leg_order[:3]), win)
            for slot, it in enumerate(leg_order[3:6]):
                add(late_items[slot], it, win)

    def item_obj(i):
        return _dd.item_info(i) or {"id": i, "name": "", "icon": _dd.item_img(i)}

    n_perk_games = sum(1 for p in games if len(p.get("perks") or []) == 6)

    rune_rows = []
    for (ks, ps, ss), stat in _top(runes, total, 3):
        k, pst, sst = _dd.rune_info(ks), _dd.rune_style_info(ps), _dd.rune_style_info(ss)
        combo_games = [
            p for p in games
            if p.get("keystone") == ks and p.get("primary_style") == ps and p.get("sub_style") == ss
        ]
        perk_games = [p for p in combo_games if len(p.get("perks") or []) == 6]
        page = None
        if perk_games:
            page_counter: Dict[Tuple[int, ...], Dict[str, Any]] = {}
            for p in perk_games:
                r_tuple = tuple(p["perks"])
                st = page_counter.setdefault(r_tuple, {"games": 0, "wins": 0, "shards": {}})
                st["games"] += 1
                if p.get("win"):
                    st["wins"] += 1
                sh = p.get("shards") or []
                if len(sh) == 3:
                    sh_tuple = tuple(sh)
                    st["shards"][sh_tuple] = st["shards"].get(sh_tuple, 0) + 1

            sorted_pages = sorted(
                page_counter.items(),
                key=lambda kv: (kv[1]["games"], kv[1]["wins"]),
                reverse=True,
            )
            best_runes, best_stat = sorted_pages[0]

            if best_stat["games"] >= BUILD_MIN_GAMES:
                best_shards = None
                if best_stat["shards"]:
                    best_shards = max(best_stat["shards"], key=lambda k: best_stat["shards"][k])
                if not best_shards:
                    all_shards: Dict[Tuple[int, ...], int] = {}
                    for p in perk_games:
                        sh = p.get("shards") or []
                        if len(sh) == 3:
                            sh_t = tuple(sh)
                            all_shards[sh_t] = all_shards.get(sh_t, 0) + 1
                    if all_shards:
                        best_shards = max(all_shards, key=lambda k: all_shards[k])

                page = {
                    "runes": [
                        {
                            "id": rid,
                            "name": (_dd.rune_info(rid) or {}).get("name", ""),
                            "icon": (_dd.rune_info(rid) or {}).get("icon", ""),
                        }
                        for rid in best_runes
                    ],
                    "shards": [
                        {
                            "id": sid,
                            "name": STAT_SHARD_NAMES.get(sid, ""),
                            "icon": f"/static/images/shards/{sid}.png" if sid in STAT_SHARD_NAMES else None,
                        }
                        for sid in best_shards
                    ] if best_shards else [],
                    "games": best_stat["games"],
                    "win_rate": round(best_stat["wins"] / best_stat["games"] * 100, 1) if best_stat["games"] else 0.0,
                    # 룬 트리 전체 (선택한 룬만 밝게 표시용)
                    "primary_tree": _dd.rune_tree(ps, best_runes),
                    "secondary_tree": _dd.rune_tree(ss, best_runes, skip_keystone=True),
                    "shard_rows": [
                        [{"id": sid, "name": STAT_SHARD_NAMES.get(sid, ""), "icon": f"/static/images/shards/{sid}.png",
                          "on": bool(best_shards) and len(best_shards) > row and best_shards[row] == sid}
                         for sid in options]
                        for row, options in enumerate(STAT_SHARD_ROWS)
                    ],
                }

        rune_rows.append({
            "keystone_id": ks, "keystone_name": k["name"], "keystone_icon": k["icon"],
            "primary_tree": pst["name"], "primary_icon": pst["icon"],
            "sub_tree": sst["name"], "sub_icon": sst["icon"],
            "page": page,
            **stat,
        })
    spell_rows = [{"spells": [_dd.spell_info(s) for s in pair], **stat} for pair, stat in _top(spells, total, 3)]
    popularity = {i: st["games"] for i, st in items.items()}
    core_rows = [{"items": [item_obj(i) for i in sorted(combo, key=lambda i: -popularity.get(i, 0))], **stat}
                 for combo, stat in _top(cores, total, 5)]
    boot_rows = [{**item_obj(i), **stat} for i, stat in _top(boots, total, 3)]
    item_rows = [{**item_obj(i), **stat} for i, stat in _top(items, total, 10)]

    n_timeline = sum(1 for p in games if p.get("skills") is not None)

    valid_skill_orders = [
        (order, st) for order, st in skill_orders.items()
        if st["games"] >= BUILD_MIN_GAMES
    ]
    valid_skill_orders.sort(key=lambda kv: (kv[1]["games"], kv[1]["wins"]), reverse=True)
    skill_order_rows = []
    for order, st in valid_skill_orders[:2]:
        best_f3 = max(st["first3"], key=lambda k: (st["first3"][k], k)) if st["first3"] else ""
        skill_order_rows.append({
            "order": order,
            "first3": best_f3,
            "levels": [max(lv, key=lv.get) if lv else None for lv in st["levels"]],
            **_rate_row(st, n_timeline),
        })

    start_item_rows = [
        {"items": [item_obj(i) for i in combo], **stat}
        for combo, stat in _top(start_items, n_timeline, 3)
    ]

    item_build_rows = [
        {"items": [item_obj(i) for i in combo], **stat}
        for combo, stat in _top(item_build_orders, n_timeline, 3)
    ]

    late_item_rows = [
        [{**item_obj(i), **stat} for i, stat in _top(counter, sum(st["games"] for st in counter.values()), 4)]
        for counter in late_items
    ]

    has_timeline_sample = bool(skill_order_rows or start_item_rows or item_build_rows)
    timeline_note = (
        f"스킬·시작템·구매 순서는 타임라인이 수집된 {n_timeline}게임 기준"
        if has_timeline_sample
        else "스킬·시작템·구매 순서는 새로 수집되는 게임부터 집계됩니다."
    )

    has_any_page = any(r.get("page") is not None for r in rune_rows)
    rune_page_note = (
        f"전체 룬 페이지는 이 기능 추가 후 수집된 {n_perk_games}게임 기준"
        if has_any_page
        else "전체 룬 페이지는 새로 수집되는 게임부터 집계됩니다."
    )

    name = meta.get("name") or meta.get("id")
    note = (f"고티어 솔로랭크 {patch} 패치 · {name} {total}게임 기준 · 게임 종료 시점 아이템 · {BUILD_MIN_GAMES}게임 미만 항목 제외"
            if total else "아직 이 챔피언의 수집된 게임이 없습니다.")
    copy_lines = [f"[{name} {patch} 빌드 · {total}게임 기준]"]
    if rune_rows:
        r = rune_rows[0]
        copy_lines.append(f"룬: {r['keystone_name']} ({r['primary_tree']} + {r['sub_tree']}) 승률 {r['win_rate']}%")
        p0 = r.get("page")
        if p0 and p0.get("runes"):
            r_names = [rn["name"] for rn in p0["runes"] if rn.get("name")]
            if r_names:
                copy_lines.append(" / ".join(r_names))
    if spell_rows:
        copy_lines.append("주문: " + " + ".join(s["name"] for s in spell_rows[0]["spells"]))
    if core_rows:
        copy_lines.append("코어: " + " > ".join(i["name"] for i in core_rows[0]["items"]))

    res = {
        "champion": {"id": meta.get("id"), "name": name,
                     "image": champion_img(meta.get("image") or meta["id"]), "position": main_pos},
        "position": main_pos,
        "positions": [{"position": k, "games": v} for k, v in sorted(pos_count.items(), key=lambda kv: -kv[1])],
        "total_games": total,
        "patch": patch,
        "sample_note": note,
        "runes": rune_rows[0] if rune_rows else {},
        "rune_options": rune_rows,
        "rune_page_note": rune_page_note,
        "spells": spell_rows[0]["spells"] if spell_rows else [],
        "spell_options": spell_rows,
        "core_builds": core_rows,
        "boots": boot_rows,
        "popular_items": item_rows,
        "skill_orders": skill_order_rows,
        "start_items": start_item_rows,
        "item_build_order": item_build_rows,
        "late_items": late_item_rows,
        "timeline_note": timeline_note,
        "tier_filter": tier_key if allowed_tiers else "ALL",
        "vs": ({"id": vs_meta.get("id"), "name": vs_meta.get("name") or vs_meta.get("id"),
                "image": champion_img(vs_meta.get("image") or vs_meta["id"])} if vs_meta else None),
        "win_rate": round(sum(1 for p in games if p.get("win")) / total * 100, 1) if total else None,
        "prev_patch": None if "+" in (patch or "") else _prev_patch_stat(cid, main_pos),
        "synergy": compute_teammate_synergy(cid, main_pos, matches),
        "matchups": compute_lane_matchups(cid, main_pos, matches),
        "power_curve": compute_power_curve(cid, main_pos, matches),
        "summary": _tier_summary(meta.get("id"), main_pos),
        "quick_copy_text": "\n".join(copy_lines) if total else "",
        "source": "collected_matches",
    }
    _CACHE[cache_key] = (now, res)
    return res


# 잘 맞는 팀원: 같은 팀 다른 라인 챔피언과 함께한 게임의 승률
SYNERGY_MIN_GAMES = 10
SYNERGY_PRIOR_GAMES = 50  # 순위용: 적은 표본의 우연한 고승률이 1위가 되지 않게 50%로 당김 (표시 승률은 실제 값)
SYNERGY_TOP_N = 10
SYNERGY_TIER_KEYS = ("CHALLENGER", "GRANDMASTER", "MASTER", "OTHER")


def compute_teammate_synergy(cid: int, main_pos: Optional[str], matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """main_pos 로 플레이한 cid 게임에서 라인별 팀원 챔피언의 게임 수·승률·게임 티어별 표본수."""
    from app.apex_tiers import game_tier, load_apex_map

    apex = load_apex_map()
    by_pos: Dict[str, Dict[int, Dict[str, Any]]] = {}
    base_games = base_wins = 0
    for m in matches:
        parts = m.get("participants") or []
        me = next((p for p in parts if p.get("champion_id") == cid
                   and POSITION_MAP.get((p.get("position") or "").upper()) == main_pos), None)
        if not me:
            continue
        win = bool(me.get("win"))
        base_games += 1
        base_wins += win
        tier = game_tier([p.get("puuid") for p in parts], apex)
        for p in parts:
            pos = POSITION_MAP.get((p.get("position") or "").upper())
            if p is me or p.get("team_id") != me.get("team_id") or not pos or pos == main_pos:
                continue
            st = by_pos.setdefault(pos, {}).setdefault(
                p.get("champion_id"), {"games": 0, "wins": 0, "tiers": {k: 0 for k in SYNERGY_TIER_KEYS}})
            st["games"] += 1
            st["wins"] += win
            st["tiers"][tier] += 1

    positions = []
    for pos in ("TOP", "JUG", "MID", "BOT", "SUP"):
        if pos == main_pos:
            continue
        rows = []
        for ck, st in (by_pos.get(pos) or {}).items():
            meta = _CHAMP_BY_KEY.get(ck)
            if not meta or st["games"] < SYNERGY_MIN_GAMES:
                continue
            score = (st["wins"] + SYNERGY_PRIOR_GAMES * 0.5) / (st["games"] + SYNERGY_PRIOR_GAMES)
            rows.append((score, {
                "id": meta.get("id"), "name": meta.get("name"),
                "image": champion_img(meta.get("image") or meta["id"]),
                "games": st["games"], "wins": st["wins"],
                "win_rate": round(st["wins"] / st["games"] * 100, 1),
                "tiers": st["tiers"],
            }))
        rows.sort(key=lambda r: -r[0])
        positions.append({"position": pos, "champions": [r for _, r in rows[:SYNERGY_TOP_N]]})

    return {
        "position": main_pos,
        "base_games": base_games,
        "base_win_rate": round(base_wins / base_games * 100, 1) if base_games else None,
        "positions": positions,
        "min_games": SYNERGY_MIN_GAMES,
        "tier_note": "게임 티어: 참가자 중 가장 많은 티어 (KR 마스터 이상 명단 기준). 기타 = 마스터 미만 또는 확인 안 됨",
    }


# 패치별 비교용 경로(직전 패치·패치 변동·이전 순위)가 쓰는 필드만 (아이템·룬·스킬 제외, 메모리 절약)
_LIGHT_KEYS = ("champion_id", "position", "win", "team_id", "kills", "deaths", "assists", "puuid")


def _get_valid_matches_for_version(version: str) -> List[Dict[str, Any]]:
    """지정 패치 매치 목록 (10분 메모: 챔피언 페이지마다 직전 패치 전체를 다시 읽지 않도록)"""
    key = f"ver:{version}"
    hit = _MATCHES_MEMO.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    res = _load_valid_matches_for_version(version)
    _MATCHES_MEMO[key] = (time.time(), res)
    return res


def _load_valid_matches_for_version(version: str) -> List[Dict[str, Any]]:
    """collected_matches 테이블에서 지정 game_version 매치 중 early_surrender 제외 매치 조회"""
    if not version:
        return []
    conn = get_connection()
    try:
        cur = conn.cursor()
        table_exists = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collected_matches'"
        ).fetchone()
        if not table_exists:
            return []

        match_rows = cur.execute(
            "SELECT data FROM collected_matches WHERE game_version = ?",
            (version,),
        ).fetchall()
    finally:
        conn.close()

    valid_matches: List[Dict[str, Any]] = []
    for r in match_rows:
        raw_data = r[0] if isinstance(r, (tuple, list)) else r["data"]
        if not raw_data:
            continue
        if isinstance(raw_data, str):
            try:
                m = json.loads(raw_data)
            except Exception:
                continue
        elif isinstance(raw_data, dict):
            m = raw_data
        else:
            continue

        if m.get("early_surrender"):
            continue
        # 한 판씩 바로 가볍게 만들어 담는다 (전체를 다 읽은 뒤 줄이면 메모리 최고치가 그대로 남음)
        valid_matches.append({"participants": [{k: pp.get(k) for k in _LIGHT_KEYS} for pp in m.get("participants") or []],
                              "bans": m.get("bans"), "duration": m.get("duration")})

    return valid_matches


def _get_two_latest_versions() -> Tuple[Optional[str], Optional[str]]:
    """collected_matches 테이블의 버전들을 _parse_version으로 정렬해 가장 높은 두 개 반환. 하나뿐이면 previous는 None."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        table_exists = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collected_matches'"
        ).fetchone()
        if not table_exists:
            return (None, None)

        ver_rows = cur.execute(
            "SELECT DISTINCT game_version FROM collected_matches WHERE game_version IS NOT NULL AND game_version != ''"
        ).fetchall()
        if not ver_rows:
            return (None, None)
    finally:
        conn.close()

    versions = [r[0] if isinstance(r, (tuple, list)) else r["game_version"] for r in ver_rows]
    versions = [v for v in versions if v]
    if not versions:
        return (None, None)

    unique_versions = sorted(list(set(versions)), key=_parse_version, reverse=True)
    latest = unique_versions[0]
    previous = unique_versions[1] if len(unique_versions) > 1 else None
    return (latest, previous)


def compute_patch_shift(limit: int = 8) -> Dict[str, Any]:
    """
    최신 두 패치(latest, previous) 간 챔피언 포지션별 승률 변동(patch shift)을 수집된 매치로 집계.
    - 두 패치 모두 표본 기준 games >= max(30, match_count * 0.005)인 조합만
    - delta = 현재 승률 - 이전 승률 (%p, 소수 1자리)
    - |delta| 큰 순으로 상승 limit//2개, 하락 limit//2개 골라 번갈아 반환
    """
    cache_key = f"patch_shift:{limit}"
    now = time.time()
    if cache_key in _CACHE:
        cached_time, cached_val = _CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_val

    latest, previous = _get_two_latest_versions()
    if not latest or not previous:
        res = {
            "champions": [],
            "patch": latest or "",
            "prev_patch": previous,
            "sample_note": "비교할 이전 패치 데이터가 아직 없습니다.",
        }
        _CACHE[cache_key] = (now, res)
        return res

    latest_matches = _get_valid_matches_for_version(latest)
    prev_matches = _get_valid_matches_for_version(previous)

    M = len(latest_matches)
    N = len(prev_matches)
    if M == 0 or N == 0:
        res = {
            "champions": [],
            "patch": latest,
            "prev_patch": previous,
            "sample_note": "비교할 이전 패치 데이터가 아직 없습니다.",
        }
        _CACHE[cache_key] = (now, res)
        return res

    ban_counts: Dict[int, int] = {}
    for m in latest_matches:
        match_bans = set()
        for b in (m.get("bans") or []):
            try:
                bid = int(b)
                if bid > 0:
                    match_bans.add(bid)
            except (ValueError, TypeError):
                resolved = find_champion(str(b).strip())
                if resolved and resolved.get("key") and str(resolved["key"]).isdigit():
                    match_bans.add(int(resolved["key"]))
        for bid in match_bans:
            ban_counts[bid] = ban_counts.get(bid, 0) + 1

    cur_stats: Dict[Tuple[int, str], Dict[str, int]] = {}
    for m in latest_matches:
        for p in (m.get("participants") or []):
            raw_pos = (p.get("position") or "").strip().upper()
            pos = POSITION_MAP.get(raw_pos)
            if not pos:
                continue
            raw_cid = p.get("champion_id")
            if raw_cid is None:
                continue
            cid = None
            try:
                cid = int(raw_cid)
            except (ValueError, TypeError):
                resolved = find_champion(str(raw_cid).strip())
                if resolved and resolved.get("key") and str(resolved["key"]).isdigit():
                    cid = int(resolved["key"])
            if not cid or cid <= 0:
                continue

            st = cur_stats.setdefault((cid, pos), {"games": 0, "wins": 0})
            st["games"] += 1
            if p.get("win"):
                st["wins"] += 1

    prev_stats: Dict[Tuple[int, str], Dict[str, int]] = {}
    for m in prev_matches:
        for p in (m.get("participants") or []):
            raw_pos = (p.get("position") or "").strip().upper()
            pos = POSITION_MAP.get(raw_pos)
            if not pos:
                continue
            raw_cid = p.get("champion_id")
            if raw_cid is None:
                continue
            cid = None
            try:
                cid = int(raw_cid)
            except (ValueError, TypeError):
                resolved = find_champion(str(raw_cid).strip())
                if resolved and resolved.get("key") and str(resolved["key"]).isdigit():
                    cid = int(resolved["key"])
            if not cid or cid <= 0:
                continue

            st = prev_stats.setdefault((cid, pos), {"games": 0, "wins": 0})
            st["games"] += 1
            if p.get("win"):
                st["wins"] += 1

    cur_threshold = max(30, int(M * 0.005))
    prev_threshold = max(30, int(N * 0.005))

    candidates: List[Dict[str, Any]] = []
    for (cid, pos), c_st in cur_stats.items():
        if c_st["games"] < cur_threshold:
            continue
        p_st = prev_stats.get((cid, pos))
        if not p_st or p_st["games"] < prev_threshold:
            continue

        cur_games = c_st["games"]
        cur_wins = c_st["wins"]
        prev_games = p_st["games"]
        prev_wins = p_st["wins"]

        cur_wr = round((cur_wins / cur_games) * 100, 1)
        prev_wr = round((prev_wins / prev_games) * 100, 1)
        delta = round(cur_wr - prev_wr, 1)
        # 표본 오차 안의 변화는 우연일 수 있어 뺀다 (40게임씩이면 2배 기준 약 ±22%p)
        p1, p2 = cur_wins / cur_games, prev_wins / prev_games
        se = math.sqrt(p1 * (1 - p1) / cur_games + p2 * (1 - p2) / prev_games) * 100
        if abs(cur_wr - prev_wr) < SHIFT_MIN_Z * se:
            continue
        is_buff = delta > 0
        delta_str = f"+{delta:.1f}%p" if is_buff else f"{delta:.1f}%p"

        pick_rate = round((cur_games / M) * 100, 1)
        ban_rate = round((ban_counts.get(cid, 0) / M) * 100, 1)

        info = _resolve_champion(cid)
        if info:
            champ_id_str = info.get("id") or str(cid)
            champ_name = info.get("name") or champ_id_str
            champ_img_url = champion_img(info.get("image") or champ_id_str)
        else:
            champ_id_str = str(cid)
            champ_name = str(cid)
            champ_img_url = champion_img(str(cid))

        comment = f"{previous} {prev_wr}% → {latest} {cur_wr}% ({prev_games}게임 → {cur_games}게임)"

        candidates.append({
            "champ_id": champ_id_str,
            "name": champ_name,
            "position": pos,
            "image_url": champ_img_url,
            "is_buff": is_buff,
            "delta": delta,
            "delta_winrate_str": delta_str,
            "current_winrate": cur_wr,
            "prev_winrate": prev_wr,
            "games": cur_games,
            "prev_games": prev_games,
            "pick_rate": pick_rate,
            "ban_rate": ban_rate,
            "comment": comment,
        })

    half = max(1, limit // 2) if limit > 0 else 0
    surges = sorted([c for c in candidates if c["delta"] > 0], key=lambda x: (-x["delta"], -x["games"]))[:half]
    drops = sorted([c for c in candidates if c["delta"] < 0], key=lambda x: (x["delta"], -x["games"]))[:half]

    mixed: List[Dict[str, Any]] = []
    for i in range(max(len(surges), len(drops))):
        if i < len(surges):
            mixed.append(surges[i])
        if i < len(drops):
            mixed.append(drops[i])

    res = {
        "champions": mixed,
        "patch": latest,
        "prev_patch": previous,
        "sample_note": f"고티어 솔로랭크 {previous} {N}게임 · {latest} {M}게임 비교 · 두 패치 모두 표본 기준 이상인 챔피언만",
    }
    _CACHE[cache_key] = (now, res)
    return res


def compute_pair_synergy(champ_a: Any, champ_b: Any) -> Optional[Dict[str, Any]]:
    """
    수집된 실제 매치 기반 두 챔피언의 조합 시너지 및 상대 전적 계산.
    - 두 인자는 _resolve_champion 이 받는 아무 형식(한글명·영문 ID·key). 하나라도 못 찾으면 None 반환.
    - 같은 팀 매치: games, wins, win_rate, positions (최빈 포지션 조합)
    - 단독 승률: a_win_rate, b_win_rate (최신 패치 전체 게임 기준), expected_win_rate (둘의 평균), synergy_delta (win_rate - expected)
    - 상대 팀 매치: vs_games, vs_a_win_rate (A 승률)
    - games < 10 이면 win_rate/synergy_delta 는 None, vs_games < 10 이면 vs_a_win_rate 는 None
    - 10분 캐시 (키 f"pair:{a_key}:{b_key}")
    """
    meta_a = _resolve_champion(champ_a)
    meta_b = _resolve_champion(champ_b)
    if not meta_a or not meta_b:
        return None

    a_key = meta_a.get("key")
    b_key = meta_b.get("key")
    if a_key is None or b_key is None:
        return None

    try:
        cid_a = int(a_key)
        cid_b = int(b_key)
    except (ValueError, TypeError):
        return None

    cache_key = f"pair:{a_key}:{b_key}"
    now = time.time()
    if cache_key in _CACHE:
        cached_time, cached_val = _CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_val

    patch, matches = _get_latest_valid_matches()

    a_solo_games = 0
    a_solo_wins = 0
    b_solo_games = 0
    b_solo_wins = 0

    games = 0
    wins = 0
    pos_counts: Dict[Tuple[str, str], int] = {}

    vs_games = 0
    vs_a_wins = 0

    for m in matches:
        participants = m.get("participants") or []

        # 단독 승률 집계 (최신 패치 전체 게임 기준)
        for p in participants:
            try:
                pid = int(p.get("champion_id") or 0)
            except (ValueError, TypeError):
                continue
            if pid == cid_a:
                a_solo_games += 1
                if p.get("win"):
                    a_solo_wins += 1
            if pid == cid_b:
                b_solo_games += 1
                if p.get("win"):
                    b_solo_wins += 1

        # 팀별 참가자 분류
        teams: Dict[Any, List[Dict[str, Any]]] = {}
        for p in participants:
            tid = p.get("team_id")
            if tid is not None:
                teams.setdefault(tid, []).append(p)

        # 1) 같은 팀 검사
        found_same_team = False
        for tid, plist in teams.items():
            pa = next((p for p in plist if int(p.get("champion_id") or 0) == cid_a), None)
            pb = next((p for p in plist if int(p.get("champion_id") or 0) == cid_b), None)
            if pa is not None and pb is not None and pa is not pb:
                games += 1
                if pa.get("win"):
                    wins += 1

                raw_pos_a = (pa.get("position") or "").strip().upper()
                raw_pos_b = (pb.get("position") or "").strip().upper()
                norm_pos_a = (
                    "BOTTOM" if raw_pos_a == "BOT"
                    else "UTILITY" if raw_pos_a == "SUP"
                    else "MIDDLE" if raw_pos_a == "MID"
                    else "JUNGLE" if raw_pos_a == "JUG"
                    else raw_pos_a
                )
                norm_pos_b = (
                    "BOTTOM" if raw_pos_b == "BOT"
                    else "UTILITY" if raw_pos_b == "SUP"
                    else "MIDDLE" if raw_pos_b == "MID"
                    else "JUNGLE" if raw_pos_b == "JUG"
                    else raw_pos_b
                )
                pair_pos = (norm_pos_a, norm_pos_b)
                pos_counts[pair_pos] = pos_counts.get(pair_pos, 0) + 1
                found_same_team = True
                break

        # 2) 서로 상대 팀 (다른 팀) 검사
        if not found_same_team and cid_a != cid_b:
            team_a_p = None
            team_b_p = None
            for p in participants:
                try:
                    pid = int(p.get("champion_id") or 0)
                except (ValueError, TypeError):
                    continue
                if pid == cid_a and team_a_p is None:
                    team_a_p = p
                elif pid == cid_b and team_b_p is None:
                    team_b_p = p

            if team_a_p is not None and team_b_p is not None:
                if team_a_p.get("team_id") != team_b_p.get("team_id"):
                    vs_games += 1
                    if team_a_p.get("win"):
                        vs_a_wins += 1

    a_win_rate = round((a_solo_wins / a_solo_games) * 100, 1) if a_solo_games > 0 else None
    b_win_rate = round((b_solo_wins / b_solo_games) * 100, 1) if b_solo_games > 0 else None

    if a_win_rate is not None and b_win_rate is not None:
        expected_win_rate = round((a_win_rate + b_win_rate) / 2.0, 1)
    else:
        expected_win_rate = None

    if pos_counts:
        best_pos = max(pos_counts, key=pos_counts.get)
        positions = [best_pos[0], best_pos[1]]
    else:
        positions = None

    if games >= 10:
        win_rate = round((wins / games) * 100, 1)
        synergy_delta = round(win_rate - expected_win_rate, 1) if expected_win_rate is not None else None
        sample_note = f"최신 패치 {patch} 고티어 솔로랭크 · 같은 팀 {games}게임"
    else:
        win_rate = None
        synergy_delta = None
        sample_note = f"같은 팀 표본이 10게임 미만입니다 ({games}게임)"

    if vs_games >= 10:
        vs_a_win_rate = round((vs_a_wins / vs_games) * 100, 1)
    else:
        vs_a_win_rate = None

    res = {
        "champion_a": {
            "id": meta_a["id"],
            "name": meta_a["name"],
            "image": champion_img(meta_a.get("image") or meta_a["id"]),
        },
        "champion_b": {
            "id": meta_b["id"],
            "name": meta_b["name"],
            "image": champion_img(meta_b.get("image") or meta_b["id"]),
        },
        "games": games,
        "wins": wins,
        "win_rate": win_rate,
        "positions": positions,
        "a_win_rate": a_win_rate,
        "b_win_rate": b_win_rate,
        "expected_win_rate": expected_win_rate,
        "synergy_delta": synergy_delta,
        "vs_games": vs_games,
        "vs_a_win_rate": vs_a_win_rate,
        "patch": patch,
        "sample_note": sample_note,
    }
    _CACHE[cache_key] = (now, res)
    return res


def compute_bot_lane_matchups(limit: int = 12) -> Dict[str, Any]:
    """
    수집된 실제 매치 기반 바텀 2:2 (BOTTOM 원딜 + UTILITY 서포터) 맞대결 통계 계산.
    - 최신 패치 매치마다 팀별 (BOTTOM 챔피언, UTILITY 챔피언) 쌍을 구함
    - 키는 (duo_x, duo_y) 를 정렬해 한 방향으로 모으되 duo_1 기준 승수 정확히
    - games >= max(8, 매치 수 * 0.0005) 인 맞대결만, games 많은 순 limit개
    - 10분 캐시
    """
    cache_key = f"bot_matchups:{limit}"
    now = time.time()
    if cache_key in _CACHE:
        cached_time, cached_val = _CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_val

    patch, matches = _get_latest_valid_matches()
    total_matches = len(matches)
    min_games = max(8, int(total_matches * 0.0005))
    sample_note = f"최신 패치 {patch} 고티어 솔로랭크 · 맞대결 {min_games}게임 이상만"

    if total_matches == 0:
        res = {
            "matchups": [],
            "patch": patch,
            "total_matches": 0,
            "sample_note": sample_note,
        }
        _CACHE[cache_key] = (now, res)
        return res

    matchup_stats: Dict[Tuple[Tuple[int, int], Tuple[int, int]], Dict[str, int]] = {}

    for m in matches:
        teams: Dict[Any, List[Dict[str, Any]]] = {}
        for p in (m.get("participants") or []):
            tid = p.get("team_id")
            if tid is not None:
                teams.setdefault(tid, []).append(p)

        team_duos: List[Tuple[Any, Tuple[int, int], Dict[str, Any], Dict[str, Any]]] = []
        for tid, plist in teams.items():
            adcs = [p for p in plist if (p.get("position") or "").strip().upper() in ("BOTTOM", "BOT")]
            sups = [p for p in plist if (p.get("position") or "").strip().upper() in ("UTILITY", "SUP")]
            if len(adcs) == 1 and len(sups) == 1:
                adc_p = adcs[0]
                sup_p = sups[0]
                try:
                    adc_cid = int(adc_p.get("champion_id") or 0)
                    sup_cid = int(sup_p.get("champion_id") or 0)
                    if adc_cid > 0 and sup_cid > 0 and adc_cid != sup_cid:
                        team_duos.append((tid, (adc_cid, sup_cid), adc_p, sup_p))
                except (ValueError, TypeError):
                    continue

        if len(team_duos) == 2:
            t1_id, duo_a, adc_a_p, sup_a_p = team_duos[0]
            t2_id, duo_b, adc_b_p, sup_b_p = team_duos[1]
            if t1_id != t2_id:
                gold_a = int(adc_a_p.get("gold") or 0) + int(sup_a_p.get("gold") or 0)
                gold_b = int(adc_b_p.get("gold") or 0) + int(sup_b_p.get("gold") or 0)
                kills_a = int(adc_a_p.get("kills") or 0) + int(sup_a_p.get("kills") or 0)
                kills_b = int(adc_b_p.get("kills") or 0) + int(sup_b_p.get("kills") or 0)
                win_a = bool(adc_a_p.get("win"))
                win_b = bool(adc_b_p.get("win"))

                if duo_a <= duo_b:
                    d1, d2 = duo_a, duo_b
                    w1 = win_a
                    g1, g2 = gold_a, gold_b
                    k1, k2 = kills_a, kills_b
                else:
                    d1, d2 = duo_b, duo_a
                    w1 = win_b
                    g1, g2 = gold_b, gold_a
                    k1, k2 = kills_b, kills_a

                st = matchup_stats.setdefault((d1, d2), {
                    "games": 0, "wins_1": 0, "gold_1": 0, "gold_2": 0, "kills_1": 0, "kills_2": 0
                })
                st["games"] += 1
                if w1:
                    st["wins_1"] += 1
                st["gold_1"] += g1
                st["gold_2"] += g2
                st["kills_1"] += k1
                st["kills_2"] += k2

    def _champ_dict(cid: int) -> Dict[str, str]:
        meta = _resolve_champion(cid)
        if meta:
            c_id = meta.get("id") or str(cid)
            c_name = meta.get("name") or c_id
            c_img = champion_img(meta.get("image") or c_id)
        else:
            c_id = str(cid)
            c_name = str(cid)
            c_img = champion_img(str(cid))
        return {"id": c_id, "name": c_name, "image": c_img}

    evaluated: List[Dict[str, Any]] = []
    for (d1, d2), st in matchup_stats.items():
        g = st["games"]
        if g < min_games:
            continue
        w1 = st["wins_1"]
        wr1 = round((w1 / g) * 100, 1)
        wr2 = round(100.0 - wr1, 1)
        gold_diff = round((st["gold_1"] - st["gold_2"]) / g)
        kills_1 = round(st["kills_1"] / g, 1)
        kills_2 = round(st["kills_2"] / g, 1)

        evaluated.append({
            "duo_1": {
                "adc": _champ_dict(d1[0]),
                "sup": _champ_dict(d1[1]),
            },
            "duo_2": {
                "adc": _champ_dict(d2[0]),
                "sup": _champ_dict(d2[1]),
            },
            "games": g,
            "win_rate_1": wr1,
            "win_rate_2": wr2,
            "gold_diff": gold_diff,
            "kills_1": kills_1,
            "kills_2": kills_2,
        })

    evaluated.sort(key=lambda x: (x["games"], x["win_rate_1"]), reverse=True)
    matchups = evaluated[:limit]

    res = {
        "matchups": matchups,
        "patch": patch,
        "total_matches": total_matches,
        "sample_note": sample_note,
    }
    _CACHE[cache_key] = (now, res)
    return res


