from typing import Tuple, Dict, Any

TIER_ORDER = {
    "CHALLENGER": 10,
    "GRANDMASTER": 9,
    "MASTER": 8,
    "DIAMOND": 7,
    "EMERALD": 6,
    "PLATINUM": 5,
    "GOLD": 4,
    "SILVER": 3,
    "BRONZE": 2,
    "IRON": 1,
    "UNRANKED": 0,
}

DIVISION_ORDER = {
    "I": 4,
    "II": 3,
    "III": 2,
    "IV": 1,
    "": 0,
    None: 0,
}

TIER_COLORS = {
    "CHALLENGER": {"badge": "#F4C430", "bg": "rgba(244, 196, 48, 0.15)", "border": "#F4C430", "text": "#FFF275"},
    "GRANDMASTER": {"badge": "#E84057", "bg": "rgba(232, 64, 87, 0.15)", "border": "#E84057", "text": "#FF7685"},
    "MASTER": {"badge": "#9D4EDD", "bg": "rgba(157, 78, 221, 0.15)", "border": "#9D4EDD", "text": "#C77DFF"},
    "DIAMOND": {"badge": "#577590", "bg": "rgba(87, 117, 144, 0.15)", "border": "#5383E8", "text": "#70D6FF"},
    "EMERALD": {"badge": "#2D6A4F", "bg": "rgba(45, 106, 79, 0.15)", "border": "#00B4D8", "text": "#52B788"},
    "PLATINUM": {"badge": "#4EA8DE", "bg": "rgba(78, 168, 222, 0.15)", "border": "#48CAE4", "text": "#90E0EF"},
    "GOLD": {"badge": "#D4A373", "bg": "rgba(212, 163, 115, 0.15)", "border": "#E9C46A", "text": "#F4A261"},
    "SILVER": {"badge": "#8D99AE", "bg": "rgba(141, 153, 174, 0.15)", "border": "#A8DADC", "text": "#CED4DA"},
    "BRONZE": {"badge": "#A0522D", "bg": "rgba(160, 82, 45, 0.15)", "border": "#CD7F32", "text": "#DDA15E"},
    "IRON": {"badge": "#495057", "bg": "rgba(73, 80, 87, 0.15)", "border": "#6C757D", "text": "#ADB5BD"},
    "UNRANKED": {"badge": "#343A40", "bg": "rgba(52, 58, 64, 0.15)", "border": "#495057", "text": "#6C757D"},
}

TIER_NAMES_KR = {
    "CHALLENGER": "챌린저",
    "GRANDMASTER": "그랜드마스터",
    "MASTER": "마스터",
    "DIAMOND": "다이아몬드",
    "EMERALD": "에메랄드",
    "PLATINUM": "플래티넘",
    "GOLD": "골드",
    "SILVER": "실버",
    "BRONZE": "브론즈",
    "IRON": "아이언",
    "UNRANKED": "언랭크",
}

def calculate_tier_score(tier: str, rank: str = "", lp: int = 0) -> int:
    """
    티어, 디비전, LP를 기반으로 내림차순 정렬용 고유 점수를 계산합니다.
    높을수록 상위 티어입니다.
    """
    clean_tier = (tier or "UNRANKED").upper().strip()
    tier_weight = TIER_ORDER.get(clean_tier, 0)
    
    clean_rank = (rank or "").upper().strip()
    division_weight = DIVISION_ORDER.get(clean_rank, 0)
    
    # 챌린저, 그마, 마스터는 디비전이 없으므로 LP가 바로 반영됨
    safe_lp = max(0, lp or 0)
    
    return (tier_weight * 100000) + (division_weight * 1000) + safe_lp

def get_tier_meta(tier: str) -> Dict[str, Any]:
    clean_tier = (tier or "UNRANKED").upper().strip()
    colors = TIER_COLORS.get(clean_tier, TIER_COLORS["UNRANKED"])
    kr_name = TIER_NAMES_KR.get(clean_tier, "언랭크")
    return {
        "tier": clean_tier,
        "kr_name": kr_name,
        "colors": colors
    }
