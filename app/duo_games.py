"""
구인 게시판이 지원하는 게임별 설정 (포지션·티어·큐).

새 게임은 GAMES 에 항목을 추가하면 등록 검증·목록 필터·화면 선택지가 함께 바뀐다.
전적 연동: 롤(riot), 배그(pubg: PUBG_API_KEY 가 있을 때만 app/pubg_api.py). 옵치는 공식 API가 없어 구인만.
"""
import re
from typing import Any, Dict, Optional, Tuple

GAMES: Dict[str, Dict[str, Any]] = {
    "lol": {
        "name": "리그 오브 레전드",
        "short": "롤",
        "positions": [["TOP", "탑"], ["JUG", "정글"], ["MID", "미드"], ["BOT", "원딜"], ["SUP", "서포터"]],
        "tiers": ["챌린저", "그랜드마스터", "마스터", "다이아몬드", "에메랄드", "플래티넘", "골드", "실버", "브론즈", "아이언"],
        # 마스터 이상은 솔로랭크 듀오 불가 (main.py 등록 검증에서 막음)
        "default_tier": "다이아몬드",
        "no_duo_tiers": {"솔로랭크": ["챌린저", "그랜드마스터", "마스터"]},
        # 일반 (교차 선택) = 소환사의 협곡 일반 드래프트, 신속 대전 = Swiftplay, TFT = 전략적 팀 전투(롤토체스)
        "queues": ["솔로랭크", "자유랭크", "일반 (교차 선택)", "신속 대전", "칼바람 나락", "증강 칼바람", "아레나", "TFT", "내전"],
        # 내전 = 서버 멤버끼리 5:5 사설 게임 (10명), 아레나 = 2인 1팀, TFT 로비 = 8명
        "party_size": {"솔로랭크": 2, "자유랭크": 5, "일반 (교차 선택)": 5, "신속 대전": 5, "칼바람 나락": 5,
                       "증강 칼바람": 5, "아레나": 2, "TFT": 8, "내전": 10},
        # 사람들이 실제로 쓰는 줄임말 (띄어쓰기·대소문자 무시, parse_queue)
        "queue_aliases": {
            "솔로랭크": ["솔랭", "솔로", "솔로랭", "솔큐", "듀오", "듀오랭크"],
            "자유랭크": ["자랭", "자유", "자유랭", "자랭크", "플렉스", "flex"],
            "일반 (교차 선택)": ["일반", "일겜", "일반게임", "노말", "교차", "교차선택", "드래프트"],
            "신속 대전": ["신속", "신속대전", "스위프트", "swiftplay"],
            "칼바람 나락": ["칼바", "칼바람", "칼바람나락", "아람", "aram", "무작위"],
            "증강 칼바람": ["증칼", "증바람", "증강칼바람", "증강칼바"],
            "아레나": ["투투", "arena"],
            "TFT": ["롤체", "롤토체스", "롤체스", "전략적팀전투", "tft"],
            "내전": ["사설", "커스텀", "내전방"],
        },
        # 티어 줄임말: 다이아1·다1·에메2·에2·그마·챌 (parse_tier)
        "tier_aliases": {
            "챌린저": ["챌", "챌린", "c"], "그랜드마스터": ["그마", "그랜마", "gm"], "마스터": ["마", "마스", "m"],
            "다이아몬드": ["다", "다이아", "d"], "에메랄드": ["에", "에메", "e"],
            "플래티넘": ["플", "플래", "플레", "플레티넘", "플래티", "p"],
            "골드": ["골", "g"], "실버": ["실", "s"], "브론즈": ["브", "브론", "b"], "아이언": ["아", "아이", "i"],
        },
        # 단계(1~4)가 있는 티어
        "tier_divisions": ["다이아몬드", "에메랄드", "플래티넘", "골드", "실버", "브론즈", "아이언"],
        # 포지션이 없는 큐: 내 포지션 선택을 받지 않는다
        "no_position_queues": ["칼바람 나락", "증강 칼바람", "아레나", "TFT"],
        # 작성자가 최대 인원을 직접 고르는 큐 [최소, 최대] (기본값은 party_size)
        "adjustable_party": {"TFT": [1, 8]},
        "needs_tag": True,
        "stats_api": "riot",
    },
    "pubg": {
        "name": "배틀그라운드",
        "short": "배그",
        "positions": [],
        "tiers": ["마스터", "다이아몬드", "플래티넘", "골드", "실버", "브론즈"],
        "queues": ["경쟁전 스쿼드", "일반 스쿼드", "일반 듀오"],
        "party_size": {"경쟁전 스쿼드": 4, "일반 스쿼드": 4, "일반 듀오": 2},
        "needs_tag": False,
        "stats_api": "pubg",  # app/pubg_api.py, 키 없으면 has_stats=False
    },
    "overwatch": {
        "name": "오버워치 2",
        "short": "옵치",
        "positions": [["TANK", "탱커"], ["DPS", "딜러"], ["SUP", "지원"]],
        "tiers": ["챔피언", "그랜드마스터", "마스터", "다이아몬드", "플래티넘", "골드", "실버", "브론즈"],
        "queues": ["경쟁전", "빠른 대전"],
        "party_size": {"경쟁전": 5, "빠른 대전": 5},
        "needs_tag": True,
        "stats_api": None,  # 공식 전적 API 없음
    },
}

DEFAULT_GAME = "lol"


def get_game(game: Optional[str]) -> Optional[Dict[str, Any]]:
    return GAMES.get((game or DEFAULT_GAME).strip().lower())


def _norm(text: str) -> str:
    return "".join((text or "").split()).lower()


def parse_queue(game: Dict[str, Any], text: Optional[str]) -> Optional[str]:
    """'솔랭'·'자랭'·'롤체'·'증칼' 같은 줄임말을 정식 큐 이름으로 (모르면 None)"""
    key = _norm(text)
    if not key:
        return None
    for q in game["queues"]:
        if _norm(q) == key or key in (_norm(a) for a in (game.get("queue_aliases") or {}).get(q, [])):
            return q
    return None


_TIER_SEP = re.compile(r"\s*[~～〜\-]\s*")


def _parse_one_tier(game: Dict[str, Any], text: str) -> Optional[Tuple[str, Optional[int]]]:
    m = re.fullmatch(r"(.+?)\s*([1-5])?", text.strip())
    if not m:
        return None
    name, div = _norm(m.group(1)), m.group(2)
    aliases = game.get("tier_aliases") or {}
    for tier in game["tiers"]:
        if name == _norm(tier) or name in (_norm(a) for a in aliases.get(tier, [])):
            if div and (tier not in (game.get("tier_divisions") or []) or int(div) > 4):
                return None
            return tier, int(div) if div else None
    return None


def parse_tier(game: Dict[str, Any], text: Optional[str]) -> Optional[Dict[str, Any]]:
    """'다이아1'·'다1'·'에메 2'·'브~다'·'골2~플3' → {tier_kr(낮은 쪽), tier_to(높은 쪽), tiers(포함 티어), label}"""
    parts = _TIER_SEP.split((text or "").strip())
    if not parts[0] or len(parts) > 2:
        return None
    parsed = [_parse_one_tier(game, p) for p in parts]
    if any(p is None for p in parsed):
        return None
    order = game["tiers"]  # 높은 티어가 앞
    rank = lambda t: (order.index(t[0]), t[1] or 0)  # noqa: E731  같은 티어면 4단계가 더 낮음
    parsed.sort(key=rank, reverse=True)  # 낮은 쪽 먼저
    low, high = parsed[0], parsed[-1]
    show = lambda t: f"{t[0]} {t[1]}" if t[1] else t[0]  # noqa: E731
    label = show(low) if low == high else f"{show(low)} ~ {show(high)}"
    tiers = order[order.index(high[0]):order.index(low[0]) + 1]
    return {"tier_kr": low[0], "tier_to": high[0], "tiers": tiers, "label": label}


def position_codes(game: str) -> set:
    return {code for code, _ in (GAMES[game]["positions"] or [])}


def _has_stats(api: Optional[str]) -> bool:
    if api == "pubg":
        from app import pubg_api
        return pubg_api.configured()
    return bool(api)


def public_config() -> Dict[str, Any]:
    """화면용 설정 (등록 폼 선택지·필터)"""
    return {"default": DEFAULT_GAME, "games": [
        {"id": gid, **{k: v for k, v in g.items() if k != "stats_api"}, "has_stats": _has_stats(g["stats_api"])}
        for gid, g in GAMES.items()
    ]}
