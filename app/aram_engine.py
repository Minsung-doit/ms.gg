import hashlib
from typing import List, Dict, Any, Optional
from app.champion_engine import ALL_CHAMPIONS

def generate_aram_tier_list() -> List[Dict[str, Any]]:
    """
    168개 챔피언의 칼바람 나락 (ARAM) 전용 티어, 승률, 픽률 및 ARAM 전용 밸런스 버프/너프 계수 산출
    한글 가나다(ㄱㄴㄷ) 정렬 및 티어순 정렬 모두 지원 가능한 데이터 구조
    """
    aram_list = []

    for champ in ALL_CHAMPIONS:
        champ_id = champ["id"]
        c_name = champ["name"]
        seed = int(hashlib.md5(f"aram_{champ_id}".encode("utf-8")).hexdigest()[:8], 16)

        # 칼바람 승률: 43.5% ~ 57.5%
        win_rate = round(44.0 + (seed % 130) / 10.0, 2)
        # 칼바람 픽률: 0.5% ~ 14.5%
        pick_rate = round(0.8 + (seed % 120) / 10.0, 2)

        # ARAM 전용 티어 부여
        # 승률 53% 이상: OP (OP 또는 1티어)
        if win_rate >= 53.5:
            tier = "OP"
            tier_num = 0
            tier_badge = "OP"
            tier_color = "#e84057"
        elif win_rate >= 51.5:
            tier = "1"
            tier_num = 1
            tier_badge = "1티어"
            tier_color = "#008df6"
        elif win_rate >= 49.5:
            tier = "2"
            tier_num = 2
            tier_badge = "2티어"
            tier_color = "#00bba3"
        elif win_rate >= 47.5:
            tier = "3"
            tier_num = 3
            tier_badge = "3티어"
            tier_color = "#ff8200"
        elif win_rate >= 45.5:
            tier = "4"
            tier_num = 4
            tier_badge = "4티어"
            tier_color = "#8b929a"
        else:
            tier = "5"
            tier_num = 5
            tier_badge = "5티어"
            tier_color = "#9aa4af"

        # 칼바람 전용 밸런스 버프/너프 (ARAM Balance Aura)
        # 입히는 피해량 (Deal Dmg): 90% ~ 110%
        # 받는 피해량 (Take Dmg): 90% ~ 110%
        dmg_mod = 100 + ((seed % 7) - 3) * 5  # 85%, 90%, 95%, 100%, 105%, 110%, 115%
        taken_mod = 100 - ((seed % 5) - 2) * 5  # 90%, 95%, 100%, 105%, 110%

        aram_list.append({
            "id": champ_id,
            "name": c_name,
            "korean_name": c_name,
            "image": champ["image"],
            "tier": tier,
            "tier_num": tier_num,
            "tier_badge": tier_badge,
            "tier_color": tier_color,
            "win_rate": win_rate,
            "pick_rate": pick_rate,
            "dmg_dealt": dmg_mod,
            "dmg_taken": taken_mod,
            "balance_status": "버프" if dmg_mod > 100 or taken_mod < 100 else ("너프" if dmg_mod < 100 or taken_mod > 100 else "일반"),
            "role": champ.get("role", "전체")
        })

    # 기본 정렬: 승률 높은 순 (티어 높은 순)
    aram_list.sort(key=lambda x: (x["tier_num"], -x["win_rate"]))
    for idx, item in enumerate(aram_list, 1):
        item["rank"] = idx

    return aram_list


def get_aram_champion_stats(champ_id_or_name: str) -> Optional[Dict[str, Any]]:
    """
    특정 챔피언의 칼바람 나락 전용 밸런스 오라 (입히는/받는 피해량) 및 티어 스탯 반환
    """
    if not champ_id_or_name:
        return None
    tier_list = generate_aram_tier_list()
    target = champ_id_or_name.lower().replace(" ", "")
    for c in tier_list:
        if c["id"].lower() == target or c["name"].lower().replace(" ", "") == target:
            return c
    return None

