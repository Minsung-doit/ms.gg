"""
AI 코치 (app/ai_coach.py)

소환사의 최근 랭크 게임(라이엇 실제 전적)을 같은 포지션 고티어 평균(수집된 고티어 솔로랭크 매치)과 비교해
강점·약점·챔피언 폭·구체적인 팁을 만든다. 숫자는 전부 실제 값이고, 지어낸 값은 쓰지 않는다.

- 규칙 기반 코칭은 항상 제공한다.
- ANTHROPIC_API_KEY 가 있으면 위 수치만 넘겨 Claude 가 한국어 코칭 요약을 쓴다(수치 밖의 내용은 쓰지 않게 지시).
  키가 없거나 실패하면 요약 없이 규칙 기반 결과만 보낸다.
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RANKED_QUEUES = (420, 440)
MIN_GAMES = 3
BENCH_TTL = 600
_bench_cache: Dict[str, Any] = {}

# 화면 포지션 코드(real_data) → 수집 매치 포지션 코드
POS_TO_COLLECTED = {"TOP": "TOP", "JUG": "JUNGLE", "MID": "MIDDLE", "BOT": "BOTTOM", "SUP": "UTILITY"}
POS_KR = {"TOP": "탑", "JUG": "정글", "MID": "미드", "BOT": "원딜", "SUP": "서포터"}

# key, 라벨, 단위, 높을수록 좋은지
METRICS = [
    ("cs_per_min", "분당 CS", "", True),
    ("deaths", "게임당 데스", "", False),
    ("kill_participation", "킬 관여율", "%", True),
    ("damage_per_min", "분당 챔피언 피해량", "", True),
    ("gold_per_min", "분당 골드", "", True),
]

TIPS = {
    "cs_per_min": "분당 CS {v} (고티어 {b}). 라인전에서는 막타를 우선하고, 귀환 전에 웨이브를 밀어 두세요. "
                  "정글은 교전 사이에 리젠된 캠프를 들르는 동선을 습관으로 만드세요.",
    "deaths": "게임당 데스 {v}회 (고티어 {b}회). 시야가 없는 강가·정글 진입과 사이드 라인에서의 늦은 귀환이 "
              "데스로 이어지기 쉽습니다. 적 정글 위치가 안 보이면 한 발 물러서세요.",
    "kill_participation": "킬 관여율 {v}% (고티어 {b}%). 용·전령 등 오브젝트 1분 전에 미리 합류하고, "
                          "라인을 밀어 둔 뒤 교전에 들어가세요.",
    "damage_per_min": "분당 피해량 {v} (고티어 {b}). 한타에서 앞 라인에 묶이기보다 딜을 넣을 수 있는 각을 기다리고, "
                      "스킬 사거리 끝에서 꾸준히 견제하세요.",
    "gold_per_min": "분당 골드 {v} (고티어 {b}). CS와 포탑 방패·플레이트를 챙기고, "
                    "할 일이 없을 때 사이드 웨이브를 정리하세요.",
}
STRENGTH = {
    "cs_per_min": "CS 수급이 고티어 평균 이상입니다 ({v} / 고티어 {b}).",
    "deaths": "죽지 않는 플레이가 좋습니다 (게임당 {v}회 / 고티어 {b}회).",
    "kill_participation": "팀 교전 합류가 좋습니다 (킬 관여 {v}% / 고티어 {b}%).",
    "damage_per_min": "교전 딜량이 강점입니다 (분당 {v} / 고티어 {b}).",
    "gold_per_min": "골드 수급이 강점입니다 (분당 {v} / 고티어 {b}).",
}


def _mine(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for r in (m.get("team1") or []) + (m.get("team2") or []):
        if r.get("is_me"):
            return r
    return None


def player_game_stats(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """화면용 매치(real_data.convert_match)에서 랭크·정상 종료 게임의 지표만 뽑는다."""
    out = []
    for m in matches:
        if m.get("is_remake") or m.get("queue_id") not in RANKED_QUEUES:
            continue
        me = _mine(m)
        minutes = (m.get("duration_sec") or 0) / 60
        if not me or minutes < 10:
            continue
        out.append({
            "win": bool(m.get("win")),
            "position": m.get("position") or "",
            "champion": (m.get("champion") or {}).get("name") or m.get("champ_name") or "",
            "champion_id": (m.get("champion") or {}).get("id") or "",
            "kills": m.get("kills") or 0,
            "deaths": m.get("deaths") or 0,
            "assists": m.get("assists") or 0,
            "cs_per_min": m.get("cs_per_min") or 0,
            "kill_participation": m.get("kill_participation") or 0,
            "damage_per_min": (me.get("damage_dealt") or 0) / minutes,
            "gold_per_min": (me.get("gold") or 0) / minutes,
            "vision_per_min": (me.get("vision_score") or 0) / minutes,
        })
    return out


def position_benchmarks() -> Dict[str, Dict[str, float]]:
    """수집된 고티어 솔로랭크 최신 패치 매치의 포지션별 평균 (10분 캐시)."""
    hit = _bench_cache.get("bench")
    if hit and time.time() - hit[0] < BENCH_TTL:
        return hit[1]
    from app.champion_stats import _get_latest_valid_matches
    _, matches = _get_latest_valid_matches()
    sums: Dict[str, Dict[str, float]] = {}
    for m in matches:
        minutes = (m.get("duration") or 0) / 60
        if minutes < 10:
            continue
        parts = m.get("participants") or []
        team_kills: Dict[Any, int] = {}
        for p in parts:
            team_kills[p.get("team_id")] = team_kills.get(p.get("team_id"), 0) + (p.get("kills") or 0)
        for p in parts:
            pos = p.get("position")
            if not pos:
                continue
            s = sums.setdefault(pos, {"n": 0, "cs_per_min": 0.0, "deaths": 0.0, "kill_participation": 0.0,
                                      "damage_per_min": 0.0, "gold_per_min": 0.0})
            tk = team_kills.get(p.get("team_id")) or 0
            s["n"] += 1
            s["cs_per_min"] += (p.get("cs") or 0) / minutes
            s["deaths"] += p.get("deaths") or 0
            s["kill_participation"] += ((p.get("kills") or 0) + (p.get("assists") or 0)) / tk * 100 if tk else 0
            s["damage_per_min"] += (p.get("damage") or 0) / minutes
            s["gold_per_min"] += (p.get("gold") or 0) / minutes
    bench = {pos: {k: v / s["n"] for k, v in s.items() if k != "n"} | {"games": s["n"]}
             for pos, s in sums.items() if s["n"] >= 30}
    _bench_cache["bench"] = (time.time(), bench)
    return bench


def _score(value: float, bench: float, higher_better: bool) -> int:
    """고티어 평균 = 50점, 평균 대비 ±40% 이면 100/0점."""
    if not bench:
        return 50
    ratio = value / bench if higher_better else (bench / value if value else 2.0)
    return int(round(max(0, min(100, 50 + (ratio - 1) / 0.4 * 50))))


def _fmt(key: str, v: float) -> str:
    if key in ("deaths", "cs_per_min"):
        return f"{v:.1f}"
    if key == "kill_participation":
        return f"{v:.0f}"
    return f"{v:,.0f}"


def build_coach_report(player: Dict[str, Any], matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    games = player_game_stats(matches)
    base = {
        "player": {"game_name": player.get("game_name"), "tag_line": player.get("tag_line"),
                   "tier": player.get("display_tier") or player.get("tier") or ""},
        "games_analyzed": len(games),
        "ai_summary": None,
        "ai_source": "rules",
    }
    if len(games) < MIN_GAMES:
        return {**base, "ready": False,
                "message": f"최근 랭크 게임이 {len(games)}판이라 코칭하기에 부족합니다. 랭크 게임을 {MIN_GAMES}판 이상 해 주세요."}

    pos_counts: Dict[str, int] = {}
    for g in games:
        pos_counts[g["position"]] = pos_counts.get(g["position"], 0) + 1
    main_pos = max(pos_counts, key=pos_counts.get)
    main_games = [g for g in games if g["position"] == main_pos]
    bench = position_benchmarks().get(POS_TO_COLLECTED.get(main_pos, ""), {})

    metrics = []
    for key, label, unit, higher in METRICS:
        if key == "cs_per_min" and main_pos == "SUP":
            continue  # 서포터는 CS를 평가하지 않는다
        value = sum(g[key] for g in main_games) / len(main_games)
        b = bench.get(key)
        metrics.append({
            "key": key, "label": label, "unit": unit,
            "value": round(value, 1), "benchmark": round(b, 1) if b is not None else None,
            "score": _score(value, b, higher) if b else None,
        })
    scored = [m for m in metrics if m["score"] is not None]
    for m in scored:
        m["verdict"] = "강점" if m["score"] >= 60 else ("약점" if m["score"] < 40 else "보통")

    ranked = sorted(scored, key=lambda m: m["score"])
    weaknesses = [m for m in ranked if m["score"] < 45][:2]
    strengths = [m for m in reversed(ranked) if m["score"] >= 55][:2]
    tips = [TIPS[m["key"]].format(v=_fmt(m["key"], m["value"]), b=_fmt(m["key"], m["benchmark"])) for m in weaknesses]
    strength_lines = [STRENGTH[m["key"]].format(v=_fmt(m["key"], m["value"]), b=_fmt(m["key"], m["benchmark"]))
                      for m in strengths]

    champs: Dict[str, Dict[str, Any]] = {}
    for g in games:
        c = champs.setdefault(g["champion"], {"name": g["champion"], "id": g["champion_id"], "games": 0, "wins": 0,
                                              "k": 0, "d": 0, "a": 0})
        c["games"] += 1
        c["wins"] += 1 if g["win"] else 0
        c["k"] += g["kills"]
        c["d"] += g["deaths"]
        c["a"] += g["assists"]
    pool = []
    for c in sorted(champs.values(), key=lambda c: (c["games"], c["wins"]), reverse=True):
        pool.append({"name": c["name"], "id": c["id"], "games": c["games"],
                     "win_rate": round(c["wins"] / c["games"] * 100, 1),
                     "kda": round((c["k"] + c["a"]) / max(1, c["d"]), 2)})
    best = next((c for c in sorted(pool, key=lambda c: (c["win_rate"], c["games"]), reverse=True)
                 if c["games"] >= 3 and c["win_rate"] >= 50), None)
    if len(pool) >= 6:
        pool_note = f"최근 {len(games)}판에 챔피언 {len(pool)}개를 썼습니다. 승률이 좋은 2~3개로 좁히면 숙련도가 빨리 오릅니다."
    else:
        pool_note = f"최근 {len(games)}판에 챔피언 {len(pool)}개로 폭이 적당합니다."
    if best:
        pool_note += f" 가장 잘 풀리는 챔피언은 {best['name']} ({best['games']}판 승률 {best['win_rate']}%)."

    heavy_death_games = sum(1 for g in games if g["deaths"] >= 8)
    wins = sum(1 for g in games if g["win"])
    report = {
        **base,
        "ready": True,
        "main_position": main_pos,
        "main_position_kr": POS_KR.get(main_pos, main_pos),
        "main_position_games": len(main_games),
        "win_rate": round(wins / len(games) * 100, 1),
        "overall_score": round(sum(m["score"] for m in scored) / len(scored)) if scored else None,
        "metrics": metrics,
        "strengths": strength_lines,
        "tips": tips,
        "champion_pool": pool[:6],
        "pool_note": pool_note,
        "death_note": (f"{len(games)}판 중 {heavy_death_games}판에서 8데스 이상 했습니다. 이런 게임의 첫 데스 장면을 다시 보세요."
                       if heavy_death_games >= 3 else None),
        "benchmark_note": (f"비교 기준: 수집된 고티어 솔로랭크 {POS_KR.get(main_pos, main_pos)} {bench.get('games', 0):,}게임 평균"
                           if bench else "고티어 비교 표본이 아직 부족합니다."),
    }
    return report


async def ai_summary(report: Dict[str, Any]) -> Optional[str]:
    """Claude 가 리포트 수치만으로 한국어 코칭 요약을 쓴다. 키가 없거나 실패하면 None."""
    if not settings.anthropic_api_key or not report.get("ready"):
        return None
    facts = {k: report.get(k) for k in ("main_position_kr", "games_analyzed", "win_rate", "overall_score",
                                        "metrics", "champion_pool", "death_note")}
    system = ("너는 리그 오브 레전드 코치다. 사용자가 준 JSON 수치만 근거로 한국어로 4~6문장 코칭을 쓴다. "
              "JSON에 없는 수치·사실·챔피언 정보는 절대 만들지 않는다. 가장 개선 효과가 큰 1~2가지를 구체적인 행동으로 제시하고, "
              "강점도 한 문장 언급한다. 존댓말, 마크다운 없이 평문.")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": settings.anthropic_model, "max_tokens": 600, "system": system,
                      "messages": [{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}]},
            )
        if resp.status_code != 200:
            logger.warning("AI coach summary failed: %s", resp.status_code)
            return None
        text = "".join(b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text").strip()
        return text or None
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("AI coach summary error: %s", type(e).__name__)
        return None
