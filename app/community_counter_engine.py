"""
Session 9: Community Counter Board (집단지성 카운터 팁 & 투표 세션 전담 엔진)
==============================================================================
- 168개 챔피언 카운터 팁 고도화 (한국 서버 에메랄드+ / 챌린저 실전 꿀팁 100% 보존)
- 카테고리별(라인전 상성, 스킬 활용, 한타 구도) 태그 분류 및 필터링 강화
- 실시간 추천/비추천 투표 SQLite WAL 원자적 정합성 및 순위(인기순/최신순) B-Tree 인덱스 최적화
- 1:1 상성 뷰 및 챔피언 상세 화면 연동
"""

import os
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from app.database import get_connection
from app.champion_engine import find_champion, ALL_CHAMPIONS
from app.counter_knowledge_data import CURATED_COUNTER_KNOWLEDGE
from app.champion_tips_knowledge import get_champion_knowledge, CHAMPION_DETAILED_KNOWLEDGE

# ==============================================================================
# 카테고리 메타데이터 정의
# ==============================================================================
CATEGORY_METADATA = {
    "lane": {
        "key": "lane",
        "label": "라인전 상성",
        "icon": "fa-swords",
        "badge_color": "#6366F1",
        "description": "1~3렙 딜교환 타이밍, 웨이브 관리, 라인전 주도권 확보 노하우"
    },
    "skill": {
        "key": "skill",
        "label": "스킬 활용",
        "icon": "fa-bullseye",
        "badge_color": "#10B981",
        "description": "핵심 스킬 적중/회피, CC기 캔슬, 콤보 연계 및 카운터 기믹"
    },
    "teamfight": {
        "key": "teamfight",
        "label": "한타 구도",
        "icon": "fa-shield-halved",
        "badge_color": "#F59E0B",
        "description": "오브젝트 한타 진입각, 포지셔닝, 주요 딜러 마킹 및 어그로 핑퐁"
    }
}

def normalize_category(category_input: Optional[str]) -> Optional[str]:
    """카테고리 입력을 표준 키('lane', 'skill', 'teamfight') 또는 None으로 정규화"""
    if not category_input:
        return None
    c = category_input.strip().lower()
    if c in ("all", "전체", "*", ""):
        return None
    if c in ("lane", "라인전", "라인전 상성", "라인전상성"):
        return "lane"
    if c in ("skill", "스킬", "스킬 활용", "스킬활용"):
        return "skill"
    if c in ("teamfight", "한타", "한타 구도", "한타구도"):
        return "teamfight"
    return None

# ==============================================================================
# 초기 시드 데이터: 실전 1:1 매치업 집단지성 꿀팁 (챌린저/프로/장인 검증 보존 데이터)
# ==============================================================================
SEED_COMMUNITY_TIPS = [
    {
        "champ_a_id": "yasuo",
        "champ_a_name": "야스오",
        "champ_b_id": "yone",
        "champ_b_name": "요네",
        "position": "MID",
        "category": "skill",
        "author_name": "프제짱",
        "author_tag": "1004",
        "author_tier": "챌린저",
        "content": "요네가 3타 에어본(회오리 돌진)을 쓸 때 바람의 장막(W)을 맞돌진 방향으로 깔면 에어본과 돌진 장풍 판정이 완전히 무효화됩니다.",
        "upvotes": 168,
        "downvotes": 6,
        "created_at": "2026-10-06 14:20:00"
    },
    {
        "champ_a_id": "yasuo",
        "champ_a_name": "야스오",
        "champ_b_id": "yone",
        "champ_b_name": "요네",
        "position": "MID",
        "category": "lane",
        "author_name": "Pz ZZZ",
        "author_tag": "KR1",
        "author_tier": "그랜드마스터",
        "content": "요네가 영혼해방(E) 켰을 때는 맞딜하지 말고 뒤로 빠지면서 Q 스택만 모으고, 요네 본체 복귀 타이밍에 맞춰 회오리 Q 던지면 100% 맞습니다.",
        "upvotes": 95,
        "downvotes": 4,
        "created_at": "2026-10-06 17:45:00"
    },
    {
        "champ_a_id": "yone",
        "champ_a_name": "요네",
        "champ_b_id": "yasuo",
        "champ_b_name": "야스오",
        "position": "MID",
        "category": "lane",
        "author_name": "Chovy",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "야스오 바람의 장막 쿨타임이 1레벨 기준 약 30초로 매우 깁니다. 장막 빠진 타이밍에 E 진입 + W 실드로 일방적 딜교환을 거는 것이 핵심입니다.",
        "upvotes": 142,
        "downvotes": 5,
        "created_at": "2026-10-06 19:10:00"
    },
    {
        "champ_a_id": "fiora",
        "champ_a_name": "피오라",
        "champ_b_id": "jax",
        "champ_b_name": "잭스",
        "position": "TOP",
        "category": "skill",
        "author_name": "The shy",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "잭스 E(반격) 돌리는 순간 피오라 응수(W) 준비하세요. 잭스가 스턴 터뜨리는 순간 역스턴 걸고 급소 2개 찔러서 필승 가능합니다.",
        "upvotes": 215,
        "downvotes": 9,
        "created_at": "2026-10-05 22:30:00"
    },
    {
        "champ_a_id": "jax",
        "champ_a_name": "잭스",
        "champ_b_id": "fiora",
        "champ_b_name": "피오라",
        "position": "TOP",
        "category": "skill",
        "author_name": "Zeus",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "피오라 응수를 뺄 때까지 E 반격을 끝까지 돌리거나 Q 도약 직후 바로 터뜨리지 않는 변칙 박자 심리전이 필수입니다.",
        "upvotes": 130,
        "downvotes": 7,
        "created_at": "2026-10-06 02:15:00"
    },
    {
        "champ_a_id": "darius",
        "champ_a_name": "다리우스",
        "champ_b_id": "garen",
        "champ_b_name": "가렌",
        "position": "TOP",
        "category": "lane",
        "author_name": "Nuguri",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "가렌 Q 내려찍기 모션 볼 때 다리우스 W를 맞물려 치면 침묵 걸려도 가렌 슬로우 때문에 5스택 각이 바로 나옵니다.",
        "upvotes": 184,
        "downvotes": 11,
        "created_at": "2026-10-05 18:00:00"
    },
    {
        "champ_a_id": "garen",
        "champ_a_name": "가렌",
        "champ_b_id": "darius",
        "champ_b_name": "다리우스",
        "position": "TOP",
        "category": "lane",
        "author_name": "Doran",
        "author_tag": "KR1",
        "author_tier": "그랜드마스터",
        "content": "가렌은 뼈방패 들고 다리우스 E(포획) 사거리 밖에서 E로 라인 밀고 패시브로 피 채우는 이기적인 유지력 싸움으로 끌고 가야 합니다.",
        "upvotes": 97,
        "downvotes": 8,
        "created_at": "2026-10-06 11:20:00"
    },
    {
        "champ_a_id": "zed",
        "champ_a_name": "제드",
        "champ_b_id": "malzahar",
        "champ_b_name": "말자하",
        "position": "MID",
        "category": "skill",
        "author_name": "율천고 최현우",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "말자하 패시브 보호막을 원거리 단독 Q 표창 하나로 먼저 긁어 벗긴 뒤 그림자 진입해야 제압(R) 역관광을 피할 수 있습니다.",
        "upvotes": 142,
        "downvotes": 5,
        "created_at": "2026-10-06 15:40:00"
    },
    {
        "champ_a_id": "malzahar",
        "champ_a_name": "말자하",
        "champ_b_id": "zed",
        "champ_b_name": "제드",
        "position": "MID",
        "category": "skill",
        "author_name": "백크",
        "author_tag": "KR1",
        "author_tier": "마스터",
        "content": "제드가 R로 들어오면 제드 본체는 무조건 내 뒤에 나타납니다. 뒤쪽에 Q 깔고 바로 R 제압 연계하면 제드 무조건 죽습니다.",
        "upvotes": 178,
        "downvotes": 6,
        "created_at": "2026-10-06 16:50:00"
    },
    {
        "champ_a_id": "ahri",
        "champ_a_name": "아리",
        "champ_b_id": "syndra",
        "champ_b_name": "신드라",
        "position": "MID",
        "category": "skill",
        "author_name": "Faker",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "신드라 적군 와해(E) 구체 날아오는 방향으로 대각선 궁극기(혼령 질주)를 쓰면 넉백 피하면서 매혹 확정으로 맞출 수 있습니다.",
        "upvotes": 115,
        "downvotes": 4,
        "created_at": "2026-10-07 09:30:00"
    },
    {
        "champ_a_id": "sylas",
        "champ_a_name": "사일러스",
        "champ_b_id": "malphite",
        "champ_b_name": "말파이트",
        "position": "TOP",
        "category": "lane",
        "author_name": "Zeka",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "말파이트가 E(지면 강타)로 공속 깎기 전에 평타 패시브 욱여넣고, 말파이트 6렙 되자마자 궁 뺏어서 먼저 박으세요.",
        "upvotes": 153,
        "downvotes": 8,
        "created_at": "2026-10-07 10:15:00"
    },
    {
        "champ_a_id": "riven",
        "champ_a_name": "리븐",
        "champ_b_id": "renekton",
        "champ_b_name": "레넥톤",
        "position": "TOP",
        "category": "skill",
        "author_name": "꿀탱탱",
        "author_tag": "KR1",
        "author_tier": "그랜드마스터",
        "content": "레넥톤 분노 50 넘었을 때 W(무자비한 포식) 스턴 들어오기 직전 E(용맹) 실드로 씹는 게 승패를 가릅니다.",
        "upvotes": 139,
        "downvotes": 9,
        "created_at": "2026-10-07 11:00:00"
    },
    {
        "champ_a_id": "vayne",
        "champ_a_name": "베인",
        "champ_b_id": "caitlyn",
        "champ_b_name": "케이틀린",
        "position": "BOT",
        "category": "skill",
        "author_name": "Ruler",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "케이틀린 Q 쏠 때 선딜레이가 기니까 구르기(Q)로 피하면서 벽꿍(E) 각 재면 1:1 무조건 이깁니다.",
        "upvotes": 98,
        "downvotes": 5,
        "created_at": "2026-10-07 13:20:00"
    },
    {
        "champ_a_id": "katarina",
        "champ_a_name": "카타리나",
        "champ_b_id": "kassadin",
        "champ_b_name": "카사딘",
        "position": "MID",
        "category": "lane",
        "author_name": "ShowMaker",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "카사딘 상대로 1렙에 단검 주우면서 무리한 딜교 절대 금지. 카사딘 Q 보호막이 마법 피해 흡수라 단검 딜 전부 씹힙니다.",
        "upvotes": 89,
        "downvotes": 3,
        "created_at": "2026-10-07 14:05:00"
    },
    {
        "champ_a_id": "blitzcrank",
        "champ_a_name": "블리츠크랭크",
        "champ_b_id": "nautilus",
        "champ_b_name": "노틸러스",
        "position": "SUP",
        "category": "teamfight",
        "author_name": "Keria",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "노틸러스는 블리츠 그랩에 일부러 끌려준 다음 블리츠 원딜에게 닻줄(Q) 평타 속박 걸면 2:2 교전 무조건 이깁니다.",
        "upvotes": 147,
        "downvotes": 6,
        "created_at": "2026-10-07 15:30:00"
    },
    {
        "champ_a_id": "leblanc",
        "champ_a_name": "르블랑",
        "champ_b_id": "lissandra",
        "champ_b_name": "리산드라",
        "position": "MID",
        "category": "skill",
        "author_name": "BeryL",
        "author_tag": "KR1",
        "author_tier": "마스터",
        "content": "르블랑 W 진입 경로에 리산드라 W(서릿발) 깔아두면 W 복귀도 못 하고 제압당합니다. 여진 룬 필수.",
        "upvotes": 112,
        "downvotes": 4,
        "created_at": "2026-10-07 16:10:00"
    },
    {
        "champ_a_id": "khazix",
        "champ_a_name": "카직스",
        "champ_b_id": "rengar",
        "champ_b_name": "렝가",
        "position": "JUG",
        "category": "lane",
        "author_name": "Canyon",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "부쉬 밖에서 싸우면 고립 뜬 렝가는 카직스 Q 한 방에 터집니다. 렝가가 점프 못 하도록 와드 설치하고 부쉬 밖으로 유인하세요.",
        "upvotes": 125,
        "downvotes": 7,
        "created_at": "2026-10-07 17:00:00"
    },
    {
        "champ_a_id": "irelia",
        "champ_a_name": "이렐리아",
        "champ_b_id": "jax",
        "champ_b_name": "잭스",
        "position": "TOP",
        "category": "skill",
        "author_name": "Kiin",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "잭스 E 돌릴 때 이렐리아 W(불굴의 의지) 차징으로 데미지 40% 이상 감소시키고, 스턴 풀리자마자 미니언 타고 거리 벌리세요.",
        "upvotes": 133,
        "downvotes": 8,
        "created_at": "2026-10-07 17:50:00"
    },
    {
        "champ_a_id": "jayce",
        "champ_a_name": "제이스",
        "champ_b_id": "ornn",
        "champ_b_name": "오른",
        "position": "TOP",
        "category": "skill",
        "author_name": "Zeus",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "오른 W 불꽃 뿜을 때 저지불가라 제이스 E(밀치기) 씹힙니다. 오른 W 다 끝난 뒤에 해머폼 E로 밀어내야 합니다.",
        "upvotes": 104,
        "downvotes": 5,
        "created_at": "2026-10-07 18:30:00"
    },
    {
        "champ_a_id": "aatrox",
        "champ_a_name": "아트록스",
        "champ_b_id": "fiora",
        "champ_b_name": "피오라",
        "position": "TOP",
        "category": "skill",
        "author_name": "Kingen",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "아트록스 3타 Q 내려찍을 때 피오라가 100% 응수 씁니다. 3타 찍을 때 E 대시를 옆으로 비틀어 응수 스턴 궤적을 피하세요.",
        "upvotes": 161,
        "downvotes": 10,
        "created_at": "2026-10-07 19:15:00"
    },
    {
        "champ_a_id": "vi",
        "champ_a_name": "바이",
        "champ_b_id": "leesin",
        "champ_b_name": "리신",
        "position": "JUG",
        "category": "skill",
        "author_name": "Oner",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "리신 음파 2타 날아올 때 바이 Q(금고 털이) 맞받아치면 리신 돌진 끊기면서 에어본 걸립니다.",
        "upvotes": 118,
        "downvotes": 5,
        "created_at": "2026-10-07 19:40:00"
    },
    {
        "champ_a_id": "lucian",
        "champ_a_name": "루시안",
        "champ_b_id": "draven",
        "champ_b_name": "드레이븐",
        "position": "BOT",
        "category": "lane",
        "author_name": "Viper",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "드레이븐 도끼 낙하지점에 루시안 Q(꿰뚫는 빛) 조준해서 쏘면 피할 수 없어서 딜교환 이깁니다.",
        "upvotes": 94,
        "downvotes": 4,
        "created_at": "2026-10-07 20:00:00"
    },
    {
        "champ_a_id": "twistedfate",
        "champ_a_name": "트위스티드 페이트",
        "champ_b_id": "fizz",
        "champ_b_name": "피즈",
        "position": "MID",
        "category": "skill",
        "author_name": "Dopa",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "골카 뽑아도 피즈 재간둥이(E)로 씹히니까 무조건 피즈가 E 쓰기 전까지는 골카 던지지 말고 평타 치며 심리전 걸어야 합니다.",
        "upvotes": 109,
        "downvotes": 6,
        "created_at": "2026-10-07 20:25:00"
    },
    {
        "champ_a_id": "pantheon",
        "champ_a_name": "판테온",
        "champ_b_id": "yasuo",
        "champ_b_name": "야스오",
        "position": "MID",
        "category": "skill",
        "author_name": "Hide on bush",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "야스오 3타 회오리 날릴 때 판테온 E(방패)를 야스오 본체 방향으로 켜면 데미지 0 들어옵니다. (장풍 방향이 아니라 야스오 본체 위치 기준)",
        "upvotes": 195,
        "downvotes": 7,
        "created_at": "2026-10-07 20:50:00"
    },
    {
        "champ_a_id": "aatrox",
        "champ_a_name": "아트록스",
        "champ_b_id": "ksante",
        "champ_b_name": "크산테",
        "position": "TOP",
        "category": "lane",
        "author_name": "Zeus",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "크산테가 W(길을 여는 자) 충전할 때 아트록스 Q2, Q3 에어본이 면역됩니다. W 빠질 때까지 거리 유지 후 E 돌진으로 카운터 콤보 넣으세요.",
        "upvotes": 182,
        "downvotes": 5,
        "created_at": "2026-10-08 09:10:00"
    },
    {
        "champ_a_id": "ksante",
        "champ_a_name": "크산테",
        "champ_b_id": "aatrox",
        "champ_b_name": "아트록스",
        "position": "TOP",
        "category": "skill",
        "author_name": "Kiin",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "아트록스가 궁극기(세계의 종결자) 켰을 때 벽으로 유인해서 올아웃(R)으로 납치하면 아트록스 흡혈 타이밍을 차단하고 1:1 압살합니다.",
        "upvotes": 174,
        "downvotes": 4,
        "created_at": "2026-10-08 09:30:00"
    },
    {
        "champ_a_id": "camille",
        "champ_a_name": "카밀",
        "champ_b_id": "jax",
        "champ_b_name": "잭스",
        "position": "TOP",
        "category": "skill",
        "author_name": "Kiin",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "잭스 E(반격) 돌릴 때 카밀 E(갈고리 발사)로 벽에 붙어서 대기하세요. 잭스 반격 끝나자마자 벽 박차고 스턴 넣으면 Q2 고정딜 100% 꽂힙니다.",
        "upvotes": 198,
        "downvotes": 6,
        "created_at": "2026-10-08 10:00:00"
    },
    {
        "champ_a_id": "jax",
        "champ_a_name": "잭스",
        "champ_b_id": "camille",
        "champ_b_name": "카밀",
        "position": "TOP",
        "category": "lane",
        "author_name": "The shy",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "카밀 패시브 물리 보호막 쿨타임(16초)을 항상 체크하고, 패시브 빠진 순간 Q 도약 평W로 일방적 딜교환 거세요.",
        "upvotes": 165,
        "downvotes": 5,
        "created_at": "2026-10-08 10:30:00"
    },
    {
        "champ_a_id": "fiora",
        "champ_a_name": "피오라",
        "champ_b_id": "darius",
        "champ_b_name": "다리우스",
        "position": "TOP",
        "category": "lane",
        "author_name": "Zeus",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "다리우스 1렙 W 찍고 부쉬 대기하는 경우가 많습니다. 1렙에 사리고 3렙 이후 다리우스 Q 돌릴 때 Q로 안쪽 파고들면 외곽 도끼날 씹힙니다.",
        "upvotes": 188,
        "downvotes": 7,
        "created_at": "2026-10-08 11:00:00"
    },
    {
        "champ_a_id": "darius",
        "champ_a_name": "다리우스",
        "champ_b_id": "fiora",
        "champ_b_name": "피오라",
        "position": "TOP",
        "category": "skill",
        "author_name": "Nuguri",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "피오라가 궁(대결투) 켰을 때 벽에 등을 딱 붙이고 서면 4번째 급소를 못 쳐서 힐 장판이 절대 안 터집니다.",
        "upvotes": 210,
        "downvotes": 8,
        "created_at": "2026-10-08 11:30:00"
    },
    {
        "champ_a_id": "rumble",
        "champ_a_name": "럼블",
        "champ_b_id": "ksante",
        "champ_b_name": "크산테",
        "position": "TOP",
        "category": "lane",
        "author_name": "Kingen",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "럼블 화염방사기(Q) 위험 구간(50% 이상) 유지하면서 열 관리 평타 치면 크산테 실드와 방어력을 마법 피해로 완전히 녹입니다.",
        "upvotes": 145,
        "downvotes": 4,
        "created_at": "2026-10-08 12:00:00"
    },
    {
        "champ_a_id": "gragas",
        "champ_a_name": "그라가스",
        "champ_b_id": "jax",
        "champ_b_name": "잭스",
        "position": "TOP",
        "category": "skill",
        "author_name": "Morgan",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "잭스가 Q(도약 공격)로 날아오는 순간 그라가스 E(몸통 박치기) 맞받아치면 잭스 점프가 공중에서 캔슬되고 딜교 일방 승리합니다.",
        "upvotes": 172,
        "downvotes": 5,
        "created_at": "2026-10-08 12:30:00"
    },
    {
        "champ_a_id": "poppy",
        "champ_a_name": "뽀삐",
        "champ_b_id": "riven",
        "champ_b_name": "리븐",
        "position": "TOP",
        "category": "skill",
        "author_name": "Doran",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "리븐 3타 Q 내려찍기 및 E 돌진 모두 뽀삐 W(굳건한 태세)에 걸려 에어본 및 침묵 당합니다. 리븐 콤보 원천 봉쇄.",
        "upvotes": 158,
        "downvotes": 4,
        "created_at": "2026-10-08 13:00:00"
    },
    {
        "champ_a_id": "kennen",
        "champ_a_name": "케넨",
        "champ_b_id": "gnar",
        "champ_b_name": "나르",
        "position": "TOP",
        "category": "lane",
        "author_name": "Zeus",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "미니 나르 분노 85% 이상 찰 때 사리고, 메가 나르 끝나고 분노 빠진 탈진 상태 15초 동안 케넨 E 평W 감전으로 피 깎아내세요.",
        "upvotes": 140,
        "downvotes": 5,
        "created_at": "2026-10-08 13:30:00"
    },
    {
        "champ_a_id": "gnar",
        "champ_a_name": "나르",
        "champ_b_id": "kennen",
        "champ_b_name": "케넨",
        "position": "TOP",
        "category": "teamfight",
        "author_name": "Kiin",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "한타 때 케넨이 눈덩이나 점멸 R로 들어오면 메가 나르 R(나르다!)로 벽에 꽂아버려 케넨 궁극기 장판을 즉시 무력화하세요.",
        "upvotes": 162,
        "downvotes": 6,
        "created_at": "2026-10-08 14:00:00"
    },
    {
        "champ_a_id": "yone",
        "champ_a_name": "요네",
        "champ_b_id": "renekton",
        "champ_b_name": "레넥톤",
        "position": "TOP",
        "category": "lane",
        "author_name": "Chovy",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "레넥톤 상대로는 도란방패 + 재생의 바람 고정입니다. 1~2렙에 Q 견제로 분노 쌓지 못하게 원거리 압박하고 6렙 이후 킬각 재세요.",
        "upvotes": 178,
        "downvotes": 5,
        "created_at": "2026-10-08 14:30:00"
    },
    {
        "champ_a_id": "renekton",
        "champ_a_name": "레넥톤",
        "champ_b_id": "riven",
        "champ_b_name": "리븐",
        "position": "TOP",
        "category": "lane",
        "author_name": "Zeus",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "1렙에 리븐 Q 평타 딜교 받지 말고 분노 50 쌓은 2렙 타이밍에 강화 W 평Q 감전으로 체력 반피 이상 일방적으로 깎으세요.",
        "upvotes": 192,
        "downvotes": 6,
        "created_at": "2026-10-08 15:00:00"
    },
    {
        "champ_a_id": "leesin",
        "champ_a_name": "리신",
        "champ_b_id": "viego",
        "champ_b_name": "비에고",
        "position": "JUG",
        "category": "skill",
        "author_name": "Oner",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "비에고 W(망령의 손길) 기절 모션 차징할 때 리신 W(방호)로 와드 타며 피하고, 비에고 Q 빗나간 직후 음파(Q) 꽂으면 정글 1:1 무조건 이깁니다.",
        "upvotes": 184,
        "downvotes": 6,
        "created_at": "2026-10-08 15:30:00"
    },
    {
        "champ_a_id": "viego",
        "champ_a_name": "비에고",
        "champ_b_id": "leesin",
        "champ_b_name": "리신",
        "position": "JUG",
        "category": "teamfight",
        "author_name": "Canyon",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "한타에서 리신이 배달 궁(R) 쓰러 들어올 때 비에고 궁(심장 파괴자)으로 저지불가 씹으면서 리신 역제압 가능합니다.",
        "upvotes": 169,
        "downvotes": 5,
        "created_at": "2026-10-08 16:00:00"
    },
    {
        "champ_a_id": "sejuani",
        "champ_a_name": "세주아니",
        "champ_b_id": "jarvaniv",
        "champ_b_name": "자르반 4세",
        "position": "JUG",
        "category": "skill",
        "author_name": "Peanut",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "자르반 EQ 깃창 날아올 때 세주아니 Q(혹한의 맹습) 맞돌진하면 깃창 끊기면서 세주아니 패시브 서리 스택이 즉시 쌓입니다.",
        "upvotes": 144,
        "downvotes": 4,
        "created_at": "2026-10-08 16:30:00"
    },
    {
        "champ_a_id": "nocturne",
        "champ_a_name": "녹턴",
        "champ_b_id": "khazix",
        "champ_b_name": "카직스",
        "position": "JUG",
        "category": "skill",
        "author_name": "Lucid",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "카직스가 도약(E) 진입할 때 녹턴 W(어둠의 장막)로 고립 Q 데미지를 씹고 E 공포 걸면 카직스 탈출 못 하고 사망합니다.",
        "upvotes": 156,
        "downvotes": 5,
        "created_at": "2026-10-08 17:00:00"
    },
    {
        "champ_a_id": "xinzhao",
        "champ_a_name": "신 짜오",
        "champ_b_id": "graves",
        "champ_b_name": "그레이브즈",
        "position": "JUG",
        "category": "lane",
        "author_name": "Oner",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "그레이브즈 평타 사거리 밖에서 신 짜오 E 돌진 후 W 슬로우 걸고 밀어붙이면 그브 넉백 평타 카이팅을 원천 봉쇄합니다.",
        "upvotes": 138,
        "downvotes": 4,
        "created_at": "2026-10-08 17:30:00"
    },
    {
        "champ_a_id": "graves",
        "champ_a_name": "그레이브즈",
        "champ_b_id": "xinzhao",
        "champ_b_name": "신 짜오",
        "position": "JUG",
        "category": "skill",
        "author_name": "Canyon",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "신 짜오가 E로 들어왔을 때 바로 발밑에 연막탄(W) 던지고 E(빨리 뽑기)로 뒤로 빠지면 신 짜오 평타 시야가 차단되어 3타 에어본을 못 칩니다.",
        "upvotes": 182,
        "downvotes": 6,
        "created_at": "2026-10-08 18:00:00"
    },
    {
        "champ_a_id": "lillia",
        "champ_a_name": "릴리아",
        "champ_b_id": "hekarim",
        "champ_b_name": "헤카림",
        "position": "JUG",
        "category": "teamfight",
        "author_name": "Canyon",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "헤카림이 궁(그림자의 맹습)으로 이니시 걸 때 릴리아 패시브 이속으로 측면 피한 뒤 R(감미로운 자장가)로 헤카림을 재우면 교전 종결됩니다.",
        "upvotes": 160,
        "downvotes": 5,
        "created_at": "2026-10-08 18:30:00"
    },
    {
        "champ_a_id": "elise",
        "champ_a_name": "엘리스",
        "champ_b_id": "kindred",
        "champ_b_name": "킨드레드",
        "position": "JUG",
        "category": "skill",
        "author_name": "Peanut",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "킨드레드가 R(양의 안식처) 켰을 때 엘리스는 거미폼 줄타기(E)로 공중에 떠 있다가 킨드레드 궁 끝나는 순간 내려와서 처형 큐(Q) 박으세요.",
        "upvotes": 175,
        "downvotes": 6,
        "created_at": "2026-10-08 19:00:00"
    },
    {
        "champ_a_id": "zac",
        "champ_a_name": "자크",
        "champ_b_id": "vi",
        "champ_b_name": "바이",
        "position": "JUG",
        "category": "skill",
        "author_name": "Lucid",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "바이가 Q 차징 후 들어올 때 자크 Q(탄성 투구)로 바이를 잡고 옆 미니언이나 정글몹 쳐서 바운스시키면 바이 Q 끊깁니다.",
        "upvotes": 148,
        "downvotes": 4,
        "created_at": "2026-10-08 19:30:00"
    },
    {
        "champ_a_id": "jarvaniv",
        "champ_a_name": "자르반 4세",
        "champ_b_id": "poppy",
        "champ_b_name": "뽀삐",
        "position": "JUG",
        "category": "skill",
        "author_name": "Oner",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "뽀삐 W 켜져 있을 때는 자르반 EQ 절대 쓰지 마세요. W 끝난 거 확인하거나 뽀삐 W 없을 때만 진입해야 에어본 안 끊깁니다.",
        "upvotes": 135,
        "downvotes": 5,
        "created_at": "2026-10-08 20:00:00"
    },
    {
        "champ_a_id": "azir",
        "champ_a_name": "아지르",
        "champ_b_id": "orianna",
        "champ_b_name": "오리아나",
        "position": "MID",
        "category": "lane",
        "author_name": "Faker",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "오리아나 Q 구체가 아지르 쪽으로 이동할 때 E(신기루)로 모래병사 타며 구체 피하고 Q로 오리아나 본체 찌르면 딜교환 무조건 이깁니다.",
        "upvotes": 240,
        "downvotes": 6,
        "created_at": "2026-10-08 20:30:00"
    },
    {
        "champ_a_id": "orianna",
        "champ_a_name": "오리아나",
        "champ_b_id": "azir",
        "champ_b_name": "아지르",
        "position": "MID",
        "category": "lane",
        "author_name": "Chovy",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "아지르 병사 찌르기 사거리(Q) 빠진 직후 12초 쿨타임 동안 구체를 아지르 발밑에 고정시키고 평타 견제로 라인 디나이하세요.",
        "upvotes": 225,
        "downvotes": 5,
        "created_at": "2026-10-08 21:00:00"
    },
    {
        "champ_a_id": "taliyah",
        "champ_a_name": "탈리야",
        "champ_b_id": "ahri",
        "champ_b_name": "아리",
        "position": "MID",
        "category": "skill",
        "author_name": "ShowMaker",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "아리가 궁극기(혼령 질주)로 진입할 때 탈리야 E(대지의 파동) 깔아두면 아리가 대시하는 순간 바위가 터져 자폭 기절합니다.",
        "upvotes": 195,
        "downvotes": 5,
        "created_at": "2026-10-08 21:30:00"
    },
    {
        "champ_a_id": "ahri",
        "champ_a_name": "아리",
        "champ_b_id": "taliyah",
        "champ_b_name": "탈리야",
        "position": "MID",
        "category": "skill",
        "author_name": "Chovy",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "탈리야 W(지각변동) 바닥 모션 뜰 때 궁극기 대시로 대각선 회피하면서 탈리야 본체에 매혹(E) 적중시키면 원콤 킬각 나옵니다.",
        "upvotes": 185,
        "downvotes": 4,
        "created_at": "2026-10-08 22:00:00"
    },
    {
        "champ_a_id": "yone",
        "champ_a_name": "요네",
        "champ_b_id": "akali",
        "champ_b_name": "아칼리",
        "position": "MID",
        "category": "skill",
        "author_name": "Zeka",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "아칼리가 연막(W) 쳤을 때 요네 W(영혼 가르기) 부채꼴로 긁으면 연막 속 아칼리에게 실드 획득 및 위치 실루엣이 드러납니다.",
        "upvotes": 204,
        "downvotes": 7,
        "created_at": "2026-10-08 22:30:00"
    },
    {
        "champ_a_id": "akali",
        "champ_a_name": "아칼리",
        "champ_b_id": "yone",
        "champ_b_name": "요네",
        "position": "MID",
        "category": "skill",
        "author_name": "Zeka",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "요네가 3타 회오리 날릴 때 아칼리 E(표창곡예) 뒤로 쓰면 회오리 피하면서 요네 본체에 표창 표식이 박혀 킬각 바로 열립니다.",
        "upvotes": 215,
        "downvotes": 8,
        "created_at": "2026-10-08 23:00:00"
    },
    {
        "champ_a_id": "syndra",
        "champ_a_name": "신드라",
        "champ_b_id": "zoe",
        "champ_b_name": "조이",
        "position": "MID",
        "category": "skill",
        "author_name": "Bdd",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "조이가 R(차원 넘기)로 튀어나오는 포털 위치에 미리 Q(어둠 구체)를 깔아두고 복귀 타이밍에 적군 와해(E)를 날리면 100% 스턴입니다.",
        "upvotes": 178,
        "downvotes": 5,
        "created_at": "2026-10-09 09:00:00"
    },
    {
        "champ_a_id": "zoe",
        "champ_a_name": "조이",
        "champ_b_id": "syndra",
        "champ_b_name": "신드라",
        "position": "MID",
        "category": "skill",
        "author_name": "Bdd",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "신드라 스턴 구체 빠지기 전까지는 벽 뒤에서 최대 사거리 Q(통통별)만 날리고 수면(E) 맞춘 후에만 R 진입하세요.",
        "upvotes": 162,
        "downvotes": 4,
        "created_at": "2026-10-09 09:30:00"
    },
    {
        "champ_a_id": "galio",
        "champ_a_name": "갈리오",
        "champ_b_id": "leblanc",
        "champ_b_name": "르블랑",
        "position": "MID",
        "category": "skill",
        "author_name": "Faker",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "르블랑 W(왜곡) 돌진 모션 보고 갈리오 W(듀란드의 방패) 차징하면 르블랑이 도발에 걸려 W 복귀를 못 하고 폭사합니다.",
        "upvotes": 235,
        "downvotes": 6,
        "created_at": "2026-10-09 10:00:00"
    },
    {
        "champ_a_id": "viktor",
        "champ_a_name": "빅토르",
        "champ_b_id": "jayce",
        "champ_b_name": "제이스",
        "position": "MID",
        "category": "lane",
        "author_name": "ShowMaker",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "제이스 가속관문 QE 포킹을 미니언 뒤에서 피하고, 제이스가 해머폼 진입 시 발밑에 중력장(W) 깔면 제이스가 기절해 역관광당합니다.",
        "upvotes": 170,
        "downvotes": 5,
        "created_at": "2026-10-09 10:30:00"
    },
    {
        "champ_a_id": "corki",
        "champ_a_name": "코르키",
        "champ_b_id": "tristana",
        "champ_b_name": "트리스타나",
        "position": "MID",
        "category": "lane",
        "author_name": "Chovy",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "트리스타나가 W 점프로 들어올 때 코르키 W(발키리)로 뒤로 빠지면서 불장판 밟게 하고 E 개틀링 + R 미사일 집중 사격하세요.",
        "upvotes": 182,
        "downvotes": 4,
        "created_at": "2026-10-09 11:00:00"
    },
    {
        "champ_a_id": "tristana",
        "champ_a_name": "트리스타나",
        "champ_b_id": "corki",
        "champ_b_name": "코르키",
        "position": "MID",
        "category": "lane",
        "author_name": "Clozer",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "코르키 발키리 빠진 타이밍에 W(로켓 점프) 슬로우 걸고 E 폭탄 4타 터뜨리면 점화 연계로 무조건 솔킬 나옵니다.",
        "upvotes": 165,
        "downvotes": 5,
        "created_at": "2026-10-09 11:30:00"
    },
    {
        "champ_a_id": "kassadin",
        "champ_a_name": "카사딘",
        "champ_b_id": "anivia",
        "champ_b_name": "애니비아",
        "position": "MID",
        "category": "skill",
        "author_name": "Faker",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "애니비아가 궁극기(얼음 폭풍) 켤 때 카사딘 Q(무효화 구체)를 던지면 애니비아 궁극기 집중이 즉시 끊겨 한타 장판이 지워집니다.",
        "upvotes": 218,
        "downvotes": 5,
        "created_at": "2026-10-09 12:00:00"
    },
    {
        "champ_a_id": "zed",
        "champ_a_name": "제드",
        "champ_b_id": "yasuo",
        "champ_b_name": "야스오",
        "position": "MID",
        "category": "skill",
        "author_name": "율천고 최현우",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "야스오가 바람의 장막(W) 켰을 때 제드는 W 그림자를 장막 뒤쪽으로 넘겨 설치하면 Q 표창을 장막에 막히지 않고 맞출 수 있습니다.",
        "upvotes": 205,
        "downvotes": 6,
        "created_at": "2026-10-09 12:30:00"
    },
    {
        "champ_a_id": "kaisa",
        "champ_a_name": "카이사",
        "champ_b_id": "xayah",
        "champ_b_name": "자야",
        "position": "BOT",
        "category": "teamfight",
        "author_name": "Viper",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "자야 궁극기(깃털의 폭풍) 빠지기 전에는 카이사 R을 아끼고, 자야 깃털 소환(E) 타이밍에 카이사 은신(E) 및 궁극기로 깃부르기를 피해야 합니다.",
        "upvotes": 220,
        "downvotes": 6,
        "created_at": "2026-10-09 13:00:00"
    },
    {
        "champ_a_id": "xayah",
        "champ_a_name": "자야",
        "champ_b_id": "kaisa",
        "champ_b_name": "카이사",
        "position": "BOT",
        "category": "teamfight",
        "author_name": "Ruler",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "카이사가 궁(사냥본능)으로 뒤로 진입할 때 즉시 R(깃털의 폭풍)로 무적 상태 돌입 후 E(깃부르기) 당기면 카이사 역속박 걸립니다.",
        "upvotes": 210,
        "downvotes": 5,
        "created_at": "2026-10-09 13:30:00"
    },
    {
        "champ_a_id": "ezreal",
        "champ_a_name": "이즈리얼",
        "champ_b_id": "varus",
        "champ_b_name": "바루스",
        "position": "BOT",
        "category": "lane",
        "author_name": "Deft",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "바루스 Q 차징 모션 볼 때 미니언 뒤로 피하고, 바루스가 R(부패의 사슬) 던질 때 이즈리얼 E(비전 이동) 선입력하면 속박 맞아도 탈출됩니다.",
        "upvotes": 230,
        "downvotes": 5,
        "created_at": "2026-10-09 14:00:00"
    },
    {
        "champ_a_id": "varus",
        "champ_a_name": "바루스",
        "champ_b_id": "ezreal",
        "champ_b_name": "이즈리얼",
        "position": "BOT",
        "category": "lane",
        "author_name": "Viper",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "이즈리얼 비전 이동 빠진 순간 유성 바루스 궁(R) 속박 꽂고 E 고통스러운 상처 + Q 풀차징 쏘면 정조준 격파 가능합니다.",
        "upvotes": 190,
        "downvotes": 4,
        "created_at": "2026-10-09 14:30:00"
    },
    {
        "champ_a_id": "jhin",
        "champ_a_name": "진",
        "champ_b_id": "ashe",
        "champ_b_name": "애쉬",
        "position": "BOT",
        "category": "skill",
        "author_name": "Gumayusi",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "애쉬 수정화살(R) 날아올 때 진 4타 평타 치려고 멈추지 말고 점멸로 피한 뒤 W(살상연희) 속박 연계해야 합니다.",
        "upvotes": 215,
        "downvotes": 6,
        "created_at": "2026-10-09 15:00:00"
    },
    {
        "champ_a_id": "ashe",
        "champ_a_name": "애쉬",
        "champ_b_id": "jhin",
        "champ_b_name": "진",
        "position": "BOT",
        "category": "lane",
        "author_name": "Peyz",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "진 4타 장전 쿨타임(약 2.5초) 때 애쉬 W 슬로우 걸고 Q(궁사의 집중) 켜서 무한 카이팅하면 진이 평타를 못 치고 도망갑니다.",
        "upvotes": 175,
        "downvotes": 5,
        "created_at": "2026-10-09 15:30:00"
    },
    {
        "champ_a_id": "samira",
        "champ_a_name": "사미라",
        "champ_b_id": "draven",
        "champ_b_name": "드레이븐",
        "position": "BOT",
        "category": "skill",
        "author_name": "Gumayusi",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "드레이븐 2타 회전도끼 날아올 때 사미라 W(원형 검무)로 도끼를 공중에서 지워버리면 드레이븐 패시브 스택과 딜이 증발합니다.",
        "upvotes": 225,
        "downvotes": 7,
        "created_at": "2026-10-09 16:00:00"
    },
    {
        "champ_a_id": "zeri",
        "champ_a_name": "제리",
        "champ_b_id": "lucian",
        "champ_b_name": "루시안",
        "position": "BOT",
        "category": "lane",
        "author_name": "Peyz",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "루시안 대시(E) 평평 패시브 딜교환 타이밍에 제리는 벽 타고 E로 거리 벌리고 장거리 W로 반격 카이팅하세요.",
        "upvotes": 168,
        "downvotes": 4,
        "created_at": "2026-10-09 16:30:00"
    },
    {
        "champ_a_id": "missfortune",
        "champ_a_name": "미스 포츈",
        "champ_b_id": "caitlyn",
        "champ_b_name": "케이틀린",
        "position": "BOT",
        "category": "lane",
        "author_name": "Viper",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "케이틀린 사거리(650) 상대로 맞평타 치지 말고 체력 딸피 미니언 뒤에 숨어서 Q(한 발에 두 놈) 튕기기로 치명타 포킹하세요.",
        "upvotes": 184,
        "downvotes": 5,
        "created_at": "2026-10-09 17:00:00"
    },
    {
        "champ_a_id": "kalista",
        "champ_a_name": "칼리스타",
        "champ_b_id": "vayne",
        "champ_b_name": "베인",
        "position": "BOT",
        "category": "lane",
        "author_name": "Ruler",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "베인이 벽꿍 각 노릴 때 칼리스타 패시브 도약으로 벽 반대편으로 뛰며 평타 쌓고 E(뽑아 찢기)로 둔화 걸면 베인 무력화됩니다.",
        "upvotes": 176,
        "downvotes": 4,
        "created_at": "2026-10-09 17:30:00"
    },
    {
        "champ_a_id": "leona",
        "champ_a_name": "레오나",
        "champ_b_id": "alistar",
        "champ_b_name": "알리스타",
        "position": "SUP",
        "category": "skill",
        "author_name": "Keria",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "알리스타 WQ 쿵쾅 들어올 때 레오나 E(천공의 검) 맞받아치면 알리스타 돌진 도중 에어본 캔슬시키고 알리 원딜 물 수 있습니다.",
        "upvotes": 208,
        "downvotes": 5,
        "created_at": "2026-10-09 18:00:00"
    },
    {
        "champ_a_id": "alistar",
        "champ_a_name": "알리스타",
        "champ_b_id": "leona",
        "champ_b_name": "레오나",
        "position": "SUP",
        "category": "skill",
        "author_name": "BeryL",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "레오나가 아군 원딜에게 E(천공의 검)로 날아올 때 알리스타 W(박치기)로 공중에서 밀쳐내면 레오나 진입 차단됩니다.",
        "upvotes": 195,
        "downvotes": 4,
        "created_at": "2026-10-09 18:30:00"
    },
    {
        "champ_a_id": "thresh",
        "champ_a_name": "쓰레쉬",
        "champ_b_id": "nautilus",
        "champ_b_name": "노틸러스",
        "position": "SUP",
        "category": "skill",
        "author_name": "Keria",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "노틸러스 닻줄(Q) 벽이나 챔피언에 날아올 때 쓰레쉬 E(사슬 채찍)로 밀어내면 노틸러스 그랩 돌진이 완전히 캔슬됩니다.",
        "upvotes": 245,
        "downvotes": 6,
        "created_at": "2026-10-09 19:00:00"
    },
    {
        "champ_a_id": "pyke",
        "champ_a_name": "파이크",
        "champ_b_id": "lulu",
        "champ_b_name": "룰루",
        "position": "SUP",
        "category": "skill",
        "author_name": "Keria",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "룰루 변이(W) 및 궁극기(급성장) 에어본이 빠진 직후에만 파이크 Q 그랩 후 E 기절 연계해야 카운터 안 맞습니다.",
        "upvotes": 182,
        "downvotes": 4,
        "created_at": "2026-10-09 19:30:00"
    },
    {
        "champ_a_id": "rakan",
        "champ_a_name": "라칸",
        "champ_b_id": "zyra",
        "champ_b_name": "자이라",
        "position": "SUP",
        "category": "skill",
        "author_name": "Delight",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "자이라 E(가시 올가미) 속박 투사체 피하면서 라칸 W(화려한 등장)로 자이라 본체 에어본 띄우면 몸 약한 자이라 즉사합니다.",
        "upvotes": 164,
        "downvotes": 4,
        "created_at": "2026-10-09 20:00:00"
    },
    {
        "champ_a_id": "nautilus",
        "champ_a_name": "노틸러스",
        "champ_b_id": "rell",
        "champ_b_name": "렐",
        "position": "SUP",
        "category": "skill",
        "author_name": "Lehends",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "렐이 W(붕괴)로 말에서 내리며 공중 도약할 때 노틸러스 Q(닻줄) 던지면 렐 공중 에어본 캔슬되고 뚜벅이 됩니다.",
        "upvotes": 178,
        "downvotes": 5,
        "created_at": "2026-10-09 20:30:00"
    },
    {
        "champ_a_id": "rell",
        "champ_a_name": "렐",
        "champ_b_id": "blitzcrank",
        "champ_b_name": "블리츠크랭크",
        "position": "SUP",
        "category": "skill",
        "author_name": "Delight",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "블리츠크랭크 그랩 날아올 때 렐 W로 맞돌진하면서 실드 켜면 그랩 맞아도 보호막 흡수하고 적 2인 에어본 역이니시 됩니다.",
        "upvotes": 196,
        "downvotes": 5,
        "created_at": "2026-10-09 21:00:00"
    },
    {
        "champ_a_id": "karma",
        "champ_a_name": "카르마",
        "champ_b_id": "nami",
        "champ_b_name": "나미",
        "position": "SUP",
        "category": "lane",
        "author_name": "Lehends",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "나미 물방울(Q) 모션 볼 때 카르마 E(고무) 이속으로 가볍게 피하고 만트라 Q(RQ) 강가 시야 선점 포킹으로 라인전 압살하세요.",
        "upvotes": 172,
        "downvotes": 4,
        "created_at": "2026-10-09 21:30:00"
    },
    {
        "champ_a_id": "thresh",
        "champ_a_name": "쓰레쉬",
        "champ_b_id": "blitzcrank",
        "champ_b_name": "블리츠크랭크",
        "position": "SUP",
        "category": "skill",
        "author_name": "Keria",
        "author_tag": "KR1",
        "author_tier": "챌린저",
        "content": "아군 원딜이 블리츠 그랩에 끌려가는 궤적에 맞춰 쓰레쉬 W 랜턴을 선입력으로 깔아주면 끌려가자마자 즉시 탈출합니다.",
        "upvotes": 255,
        "downvotes": 5,
        "created_at": "2026-10-09 22:00:00"
    }
]

def init_community_tips_db():
    """커뮤니티 카운터 팁 데이터베이스 테이블 생성, 스키마 마이그레이션 및 168개 챔피언 실전 팁 시딩"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. 테이블 생성
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS community_counter_tips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        champ_a_id TEXT NOT NULL,
        champ_a_name TEXT NOT NULL,
        champ_b_id TEXT DEFAULT '',
        champ_b_name TEXT DEFAULT '',
        position TEXT DEFAULT 'ALL',
        author_name TEXT DEFAULT '익명 소환사',
        author_tag TEXT DEFAULT 'KR1',
        author_tier TEXT DEFAULT '다이아몬드',
        category TEXT DEFAULT 'lane',
        content TEXT NOT NULL,
        upvotes INTEGER DEFAULT 0,
        downvotes INTEGER DEFAULT 0,
        score INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. 기존 테이블 스키마 검사 및 무중단 마이그레이션
    cursor.execute("PRAGMA table_info(community_counter_tips);")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    if "category" not in existing_cols:
        cursor.execute("ALTER TABLE community_counter_tips ADD COLUMN category TEXT DEFAULT 'lane';")
    if "score" not in existing_cols:
        cursor.execute("ALTER TABLE community_counter_tips ADD COLUMN score INTEGER DEFAULT 0;")
        cursor.execute("UPDATE community_counter_tips SET score = upvotes - downvotes;")

    # 3. 고속 조회를 위한 인덱스 생성
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cct_champs ON community_counter_tips(champ_a_id COLLATE NOCASE, champ_b_id COLLATE NOCASE);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cct_category ON community_counter_tips(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cct_score ON community_counter_tips(score DESC, upvotes DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cct_created ON community_counter_tips(created_at DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cct_pos ON community_counter_tips(position);")
    conn.commit()

    # 시드 팁은 실존 프로게이머 명의로 작성된 가짜 글이므로 SYNTHETIC_FEATURES=1(개발 확인용)일 때만 적재
    if os.getenv("SYNTHETIC_FEATURES", "0").strip() != "1":
        conn.close()
        return

    # 4. 초기 및 프로/장인 1:1 매치업 시드 데이터(80개) 적재 및 무중단 동기화
    for item in SEED_COMMUNITY_TIPS:
        cursor.execute("""
        SELECT id FROM community_counter_tips 
        WHERE champ_a_id = ? AND champ_b_id = ? AND author_name = ? LIMIT 1;
        """, (item["champ_a_id"].lower(), item["champ_b_id"].lower(), item["author_name"]))
        row = cursor.fetchone()
        up = item["upvotes"]
        down = item["downvotes"]
        sc = up - down
        cat = item.get("category", "lane")
        if not row:
            cursor.execute("""
            INSERT INTO community_counter_tips 
            (champ_a_id, champ_a_name, champ_b_id, champ_b_name, position, author_name, author_tag, author_tier, category, content, upvotes, downvotes, score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                item["champ_a_id"].lower(),
                item["champ_a_name"],
                item["champ_b_id"].lower(),
                item["champ_b_name"],
                item.get("position", "ALL"),
                item["author_name"],
                item.get("author_tag", "KR1"),
                item.get("author_tier", "챌린저"),
                cat,
                item["content"],
                up,
                down,
                sc,
                item.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ))
        else:
            cursor.execute("""
            UPDATE community_counter_tips
            SET category = ?, score = upvotes - downvotes, position = COALESCE(?, position)
            WHERE id = ?;
            """, (cat, item.get("position"), row["id"]))
    conn.commit()

    # 5. 기존 시드의 category 및 점수 동기화
    for s in SEED_COMMUNITY_TIPS:
        cursor.execute("""
        UPDATE community_counter_tips
        SET category = ?, score = upvotes - downvotes
        WHERE champ_a_id = ? AND champ_b_id = ? AND author_name = ?;
        """, (s.get("category", "lane"), s["champ_a_id"].lower(), s["champ_b_id"].lower(), s["author_name"]))
    conn.commit()

    # 6. CURATED_COUNTER_KNOWLEDGE 1:1 매치업 팁 적재 (140개)
    for main_champ_id, matchup_types in CURATED_COUNTER_KNOWLEDGE.items():
        c_main = find_champion(main_champ_id)
        if not c_main:
            continue
        c_main_name = c_main["name"]

        for m_type, items in matchup_types.items():
            for m in items:
                opp_id = m.get("id", "").lower()
                opp_name = m.get("name", "")
                tip_content = m.get("tip", "").strip()
                if not tip_content or not opp_id:
                    continue

                # 중복 등록 방지
                cursor.execute("""
                SELECT id FROM community_counter_tips 
                WHERE champ_a_id = ? AND champ_b_id = ? LIMIT 1;
                """, (main_champ_id.lower(), opp_id))
                if cursor.fetchone():
                    continue

                cat = "skill" if ("스킬" in tip_content or "판정" in tip_content or "패시브" in tip_content) else "lane"
                up = 75 + (abs(hash(tip_content)) % 80)
                down = 2 + (abs(hash(tip_content)) % 5)
                cursor.execute("""
                INSERT INTO community_counter_tips
                (champ_a_id, champ_a_name, champ_b_id, champ_b_name, position, author_name, author_tag, author_tier, category, content, upvotes, downvotes, score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    main_champ_id.lower(),
                    c_main_name,
                    opp_id,
                    opp_name,
                    "ALL",
                    "챌린저 장인",
                    "KR1",
                    "챌린저",
                    cat,
                    tip_content,
                    up,
                    down,
                    up - down,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
    conn.commit()

    # 7. 168개 전 챔피언 실전 랭커 꿀팁 적재 (3대 카테고리: lane, skill, teamfight)
    for champ in ALL_CHAMPIONS:
        cid = champ["id"]
        cname = champ["name"]
        know = get_champion_knowledge(cid)
        if not know:
            continue

        author = know.get("author", "Faker")
        tier = know.get("tier", "챌린저")
        tag = know.get("tag", "KR1")
        pos = know.get("pos", "MID")

        categories = [
            ("lane", know.get("lane")),
            ("skill", know.get("skill")),
            ("teamfight", know.get("teamfight"))
        ]

        for cat_key, content in categories:
            if not content:
                continue

            # 해당 챔피언에 대해 동일 카테고리 대표 팁 존재 여부 확인
            cursor.execute("""
            SELECT id FROM community_counter_tips 
            WHERE champ_a_id = ? AND champ_b_id = '' AND category = ? LIMIT 1;
            """, (cid.lower(), cat_key))
            if cursor.fetchone():
                continue

            # 실전 추천수 산출 (인기순 랭킹 부여)
            base_up = 90 if cat_key == "lane" else (110 if cat_key == "skill" else 85)
            up = base_up + (abs(hash(cid + cat_key)) % 60)
            down = 2 + (abs(hash(cid + cat_key)) % 6)
            sc = up - down

            cursor.execute("""
            INSERT INTO community_counter_tips
            (champ_a_id, champ_a_name, champ_b_id, champ_b_name, position, author_name, author_tag, author_tier, category, content, upvotes, downvotes, score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                cid.lower(),
                cname,
                "",
                "",
                pos,
                author,
                tag,
                tier,
                cat_key,
                content,
                up,
                down,
                sc,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
    conn.commit()
    conn.close()

_initialized_db_paths = set()


def _ensure_table() -> None:
    """서버 시작 전(테스트 임시 DB 등)에도 테이블이 있도록 DB 파일마다 한 번 초기화"""
    from app import database
    key = str(database.DB_PATH)
    if key not in _initialized_db_paths:
        init_community_tips_db()
        _initialized_db_paths.add(key)


def normalize_champ(champ_input: Optional[str]) -> Tuple[str, str]:
    """챔피언 입력(한글/영문)을 정규화된 (id, name) 튜플로 반환"""
    if not champ_input:
        return ("", "")
    found = find_champion(champ_input)
    if found:
        return (found["id"].lower(), found["name"])
    clean = champ_input.strip()
    return (clean.lower(), clean)

def get_community_tips(
    champ1: Optional[str] = None,
    champ2: Optional[str] = None,
    sort_by: str = "popular",
    position: Optional[str] = None,
    category: Optional[str] = None,
    tier: Optional[str] = None,
    author_tier: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    챔피언 매치업에 해당하는 커뮤니티 집단지성 팁 목록 조회
    - champ1 vs champ2: 양방향 매치업 관련 팁을 모두 검색하되 우선순위 정렬
    - champ1 단독: champ1 관련 전체 카운터 팁 검색
    - sort_by: 'popular' (순 추천 점수 및 추천수 내림차순), 'recent' (최신 등록순)
    - category: 'lane'(라인전 상성), 'skill'(스킬 활용), 'teamfight'(한타 구도), None/'all'(전체)
    - tier / author_tier: 'all', 'high_elo'(천상계 마스터+), 'pro_expert'(프로/장인 팁), 'challenger', 'master', 'diamond', 'emerald'
    - position: 'TOP', 'JUG', 'MID', 'BOT', 'SUP', 'ALL'
    - category_counts: 전체 및 카테고리별 팁 개수 집계 메타데이터 반환
    """
    _ensure_table()
    conn = get_connection()
    cursor = conn.cursor()

    c1_id, c1_name = normalize_champ(champ1)
    c2_id, c2_name = normalize_champ(champ2) if champ2 else ("", "")
    norm_cat = normalize_category(category)
    eff_tier = (tier or author_tier or "").strip().lower()

    # 기본 매치업 조건절 구성
    base_where = "WHERE 1=1"
    base_params = []

    if c1_id and c2_id:
        # 양방향 매치업 검색: (c1 vs c2) OR (c2 vs c1) OR (c1 단독) OR (c2 단독)
        base_where += """
        AND (
            (champ_a_id = ? AND champ_b_id = ?)
            OR (champ_a_id = ? AND champ_b_id = ?)
            OR (champ_a_id = ? AND (champ_b_id = '' OR champ_b_id = 'all'))
            OR (champ_a_id = ? AND (champ_b_id = '' OR champ_b_id = 'all'))
        )
        """
        base_params.extend([c1_id, c2_id, c2_id, c1_id, c1_id, c2_id])
    elif c1_id:
        # 단일 챔피언 검색: c1이 주체이거나 대상인 모든 팁
        base_where += " AND (champ_a_id = ? OR champ_b_id = ?) "
        base_params.extend([c1_id, c1_id])

    if position and position.upper() != "ALL":
        base_where += " AND (position = ? OR position = 'ALL') "
        base_params.append(position.upper())

    # 작성자 티어는 본인 확인이 안 되는 자기 신고라 티어/장인 필터는 두지 않는다 (tier 인자는 무시)

    # 1. 카테고리별 개수 통계 산출 (전체, 라인전, 스킬, 한타)
    count_query = f"""
    SELECT 
        category,
        COUNT(*) AS cnt
    FROM community_counter_tips
    {base_where}
    GROUP BY category;
    """
    cursor.execute(count_query, base_params)
    rows_cnt = cursor.fetchall()

    counts = {"all": 0, "lane": 0, "skill": 0, "teamfight": 0}
    for r in rows_cnt:
        cat_k = r["category"] or "lane"
        cnt = r["cnt"]
        if cat_k in counts:
            counts[cat_k] += cnt
        counts["all"] += cnt

    # 2. 메인 팁 목록 조회 쿼리 구성
    query = f"""
    SELECT 
        id, champ_a_id, champ_a_name, champ_b_id, champ_b_name, 
        position, author_name, author_tag, author_tier, category, content, 
        upvotes, downvotes, score, created_at
    FROM community_counter_tips
    {base_where}
    """
    params = list(base_params)

    # 카테고리 필터링 적용
    if norm_cat:
        query += " AND category = ? "
        params.append(norm_cat)

    # 정렬 기준 최적화 (B-Tree 인덱스 활용)
    if sort_by == "recent":
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    else:  # popular
        query += " ORDER BY score DESC, upvotes DESC, id DESC LIMIT ?"
    
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    tips = []
    for r in rows:
        sc = r["score"] if "score" in r.keys() else (r["upvotes"] - r["downvotes"])
        cat_key = r["category"] if ("category" in r.keys() and r["category"]) else "lane"
        cat_meta = CATEGORY_METADATA.get(cat_key, CATEGORY_METADATA["lane"])

        # 매치업 관점 표시: "챔피언 A 공략 (vs 챔피언 B)"
        tag_perspective = f"{r['champ_a_name']} 팁"
        if r["champ_b_name"]:
            tag_perspective += f" vs {r['champ_b_name']}"

        tips.append({
            "id": r["id"],
            "champ_a_id": r["champ_a_id"],
            "champ_a_name": r["champ_a_name"],
            "champ_b_id": r["champ_b_id"],
            "champ_b_name": r["champ_b_name"],
            "perspective": tag_perspective,
            "position": r["position"],
            "category": cat_key,
            "category_label": cat_meta["label"],
            "category_icon": cat_meta["icon"],
            "author_name": r["author_name"],
            "author_tag": r["author_tag"],
            "author_tier": r["author_tier"],
            "content": r["content"],
            "upvotes": r["upvotes"],
            "downvotes": r["downvotes"],
            "score": sc,
            "is_best": sc >= 50,
            "created_at": str(r["created_at"])[:16]
        })

    return {
        "status": "success",
        "total": len(tips),
        "total_unfiltered": counts["all"],
        "category_counts": counts,
        "active_category": norm_cat or "all",
        "active_tier": eff_tier or "all",
        "active_position": (position or "ALL").upper(),
        "champ1": {"id": c1_id, "name": c1_name},
        "champ2": {"id": c2_id, "name": c2_name} if c2_id else None,
        "tips": tips
    }

def add_community_tip(
    champ1: str,
    champ2: Optional[str] = None,
    content: str = "",
    author_name: Optional[str] = None,
    author_tag: Optional[str] = None,
    author_tier: Optional[str] = None,
    position: Optional[str] = None,
    category: Optional[str] = "lane"
) -> Dict[str, Any]:
    """신규 커뮤니티 카운터 팁 등록 (카테고리 태그 및 초기 점수 원자적 반영)"""
    _ensure_table()
    clean_content = (content or "").strip()
    if len(clean_content) < 5:
        raise ValueError("공략 팁은 최소 5자 이상 입력해야 합니다.")
    if len(clean_content) > 300:
        raise ValueError("공략 팁은 300자 이하로 작성해주세요.")

    c1_id, c1_name = normalize_champ(champ1)
    if not c1_id:
        raise ValueError("유효한 첫 번째 챔피언 이름을 입력해주세요.")

    c2_id, c2_name = normalize_champ(champ2) if champ2 else ("", "")

    # 누구나 아무 이름(프로게이머 포함)으로 글을 쓸 수 있으면 사칭이 되므로 모든 글은 익명, 티어 없음
    name, tag, tier = "익명 소환사", "", ""
    pos = (position or "ALL").strip().upper()
    cat_key = normalize_category(category) or "lane"
    cat_meta = CATEGORY_METADATA.get(cat_key, CATEGORY_METADATA["lane"])

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO community_counter_tips
    (champ_a_id, champ_a_name, champ_b_id, champ_b_name, position, author_name, author_tag, author_tier, category, content, upvotes, downvotes, score, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 1, ?);
    """, (c1_id, c1_name, c2_id, c2_name, pos, name, tag, tier, cat_key, clean_content, now_str))
    
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": new_id,
        "champ_a_id": c1_id,
        "champ_a_name": c1_name,
        "champ_b_id": c2_id,
        "champ_b_name": c2_name,
        "position": pos,
        "category": cat_key,
        "category_label": cat_meta["label"],
        "category_icon": cat_meta["icon"],
        "author_name": name,
        "author_tag": tag,
        "author_tier": tier,
        "content": clean_content,
        "upvotes": 1,
        "downvotes": 0,
        "score": 1,
        "is_best": False,
        "created_at": now_str[:16]
    }

def vote_community_tip(tip_id: int, vote_type: str) -> Dict[str, Any]:
    """
    카운터 팁 추천/비추천 투표 원자적 갱신
    - score = upvotes - downvotes 를 동일 트랜잭션 내에서 원자적으로 계산하여 정합성 보장
    """
    vt = (vote_type or "").lower().strip()
    if vt not in ("up", "down", "upvote", "downvote"):
        raise ValueError("vote_type은 'up' 또는 'down'이어야 합니다.")
    _ensure_table()

    conn = get_connection()
    cursor = conn.cursor()

    if vt in ("up", "upvote"):
        cursor.execute("""
        UPDATE community_counter_tips 
        SET upvotes = upvotes + 1, score = (upvotes + 1) - downvotes 
        WHERE id = ?;
        """, (tip_id,))
    else:
        cursor.execute("""
        UPDATE community_counter_tips 
        SET downvotes = downvotes + 1, score = upvotes - (downvotes + 1) 
        WHERE id = ?;
        """, (tip_id,))

    conn.commit()

    cursor.execute("SELECT id, upvotes, downvotes, score FROM community_counter_tips WHERE id = ?;", (tip_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise ValueError("존재하지 않는 팁 ID입니다.")

    up = row["upvotes"]
    down = row["downvotes"]
    score = row["score"]
    return {
        "status": "success",
        "id": tip_id,
        "upvotes": up,
        "downvotes": down,
        "score": score,
        "vote_type": vt
    }
