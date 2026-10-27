"""
구인 게시판이 지원하는 게임별 설정 (포지션·티어·큐).

새 게임은 GAMES 에 항목을 추가하면 등록 검증·목록 필터·화면 선택지가 함께 바뀐다.
전적 연동: 롤(riot), 배그(pubg: PUBG_API_KEY 가 있을 때만 app/pubg_api.py). 옵치는 공식 API가 없어 구인만.
"""
from typing import Any, Dict, Optional

GAMES: Dict[str, Dict[str, Any]] = {
    "lol": {
        "name": "리그 오브 레전드",
        "short": "롤",
        "positions": [["TOP", "탑"], ["JUG", "정글"], ["MID", "미드"], ["BOT", "원딜"], ["SUP", "서포터"]],
        "tiers": ["챌린저", "그랜드마스터", "마스터", "다이아몬드", "에메랄드", "플래티넘", "골드", "실버", "브론즈", "아이언"],
        # 마스터 이상은 솔로랭크 듀오 불가 (main.py 등록 검증에서 막음)
        "default_tier": "다이아몬드",
        "no_duo_tiers": {"솔로랭크": ["챌린저", "그랜드마스터", "마스터"]},
        "queues": ["솔로랭크", "자유랭크", "칼바람 나락", "내전"],
        # 내전 = 서버 멤버끼리 5:5 사설 게임 (10명)
        "party_size": {"솔로랭크": 2, "자유랭크": 5, "칼바람 나락": 5, "내전": 10},
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
