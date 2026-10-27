"""
Champion Skills Engine (P/Q/W/E/R Skills, Cooldowns, Mana, Coefficients, and Combos)
League of Legends Patch 14.20 Data Dragon based skill intelligence database.
Provides complete skill metrics, level-by-level cooldown progressions, resource costs,
and tactical combo guides for all 168+ champions.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.champion_engine import find_champion, ALL_CHAMPIONS
from app.ddragon import DDRAGON_CDN

DATA_FILE = Path(__file__).resolve().parent / "champion_full_data.json"

# In-memory storage of raw DataDragon 14.20 full champion data
_RAW_DATA_CACHE: Optional[Dict[str, Any]] = None
# champion_full_data.json에 기록된 Data Dragon 버전 (응답의 patch_version은 이 값을 그대로 쓴다)
_RAW_DATA_VERSION: Optional[str] = None

def _load_raw_data() -> Dict[str, Any]:
    global _RAW_DATA_CACHE, _RAW_DATA_VERSION
    if _RAW_DATA_CACHE is not None:
        return _RAW_DATA_CACHE
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = json.load(f)
                _RAW_DATA_CACHE = content.get("data", {})
                _RAW_DATA_VERSION = content.get("version")
                return _RAW_DATA_CACHE
        except Exception:
            _RAW_DATA_CACHE = {}
    return {}

def _strip_html(text: str) -> str:
    """HTML 태그 및 Riot 템플릿 변수를 자연스러운 텍스트로 정리"""
    if not text:
        return ""
    t = re.sub(r'<br\s*/?>', ' ', text, flags=re.IGNORECASE)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'\{\{[^}]+\}\}', '', t)
    t = re.sub(r'@[^@]+@', '', t)
    t = re.sub(r'%[^%]+%', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

# ==============================================================================
# 1. 주요 핵심 챔피언 맞춤형 스킬 메커니즘 & 실전 추천 콤보 가이드 (14.20 메타)
# ==============================================================================
CURATED_CHAMPION_DETAILS: Dict[str, Dict[str, Any]] = {
    "Yasuo": {
        "resource_type": "기류 (노코스트)",
        "mechanics": {
            "P": "치명타 확률 2배 전환 (추가 피해 10% 감소) & 이동 시 기류 보호막 완충",
            "Q": "2회 적중 시 3스택 회오리 에어본 발사. 공격 속도에 비례해 쿨다운/시전 시간 감소 (최소 1.33초)",
            "W": "3.75초 동안 모든 방향의 적 원거리 투사체 및 스킬 공격 절대 차단 (포탑 제외)",
            "E": "대상을 뚫고 돌진하며 마법 피해. 연속 시전 시 피해량 최대 50% 증가. E 시전 중 Q 사용 시 원형 에어본 발동",
            "R": "공중에 뜬 모든 적에게 순간이동하여 1초간 제압 후 타격. 15초 동안 치명타 공격에 추가 방어구 관통력 50% 획득"
        },
        "scalings": {
            "Q": "100% 공격력 (치명타 및 온힛 효과 적용)",
            "W": "투사체 방어 지속시간 3.75초 (레벨 무관)",
            "E": "20% 추가 공격력 + 60% 주문력",
            "R": "150% 추가 공격력 + 방관 50% 버프"
        },
        "combos": [
            {
                "name": "국민 EQ 점멸 (배달 에어본)",
                "sequence": ["E", "Q", "Flash", "AA", "R"],
                "difficulty": "고급",
                "description": "미니언이나 대상에게 돌진(E)하면서 Q(회오리)를 누른 직후 점멸로 상대 예상 위치에 즉각 원형 에어본을 꽂아넣은 뒤 평타 후 궁극기로 연계합니다."
            },
            {
                "name": "에어본 공중 2단 딜 콤보 (에어본 연계)",
                "sequence": ["Q3 (회오리)", "E", "Q", "R"],
                "difficulty": "보통",
                "description": "원거리 회오리로 상대를 띄운 후, 가까운 미니언에 EQ를 시전하는 모션 중에 R을 눌러 공중에서 EQ 대미지와 R 대미지를 동시에 폭발시킵니다."
            },
            {
                "name": "라인전 치고 빠지기 딜교환",
                "sequence": ["E (원거리 미니언)", "Q (상대)", "AA", "E (근거리 미니언 탈출)"],
                "difficulty": "쉬움",
                "description": "미니언을 타고 들어가 실드로 상대 반격을 흡수하며 Q와 평타로 딜교환 후 다른 미니언을 타고 안전하게 빠져나옵니다."
            }
        ]
    },
    "Yone": {
        "resource_type": "노코스트",
        "mechanics": {
            "P": "두 번째 평타마다 마법 피해 50% 혼합 타격 & 치명타 확률 2배 전환",
            "Q": "2스택 충전 시 전방 돌진하며 적들을 에어본. 공격 속도에 비례해 쿨다운/시전 시간 감소",
            "W": "전방 부채꼴 베기 (최대 체력 비례 피해). 챔피언 타격 시 비례 보호막 획득",
            "E": "육신을 두고 영혼 상태로 돌진 (이속 증가). 상태 종료 시 해당 기간 입힌 피해의 25~35%를 고정 피해로 재폭발",
            "R": "경로상의 모든 적을 베고 순간이동하며 중심으로 끌어당겨 공중에 띄움"
        },
        "scalings": {
            "Q": "105% 총 공격력 (치명타 적용)",
            "W": "적 최대 체력의 11~15% 혼합 피해 + 챔피언당 실드 증가",
            "E": "입힌 피해량의 25/27.5/30/32.5/35% 고정 피해 폭발",
            "R": "80% 공격력(물리) + 80% 공격력(마법) 혼합 계수"
        },
        "combos": [
            {
                "name": "영혼 해방 올인 콤보",
                "sequence": ["E", "Q3 (돌진 에어본)", "AA", "W", "R", "AA", "E (복귀 처형)"],
                "difficulty": "보통",
                "description": "E로 영혼 상태로 진입하여 돌진 에어본(Q3)과 궁극기(R)로 확정 CC를 넣은 후 평타와 W를 섞고 안전하게 복귀하며 고정 피해 폭발로 마무리합니다."
            },
            {
                "name": "깜짝 궁극기 이니시에이션",
                "sequence": ["E", "R", "W", "Q", "AA", "E"],
                "difficulty": "쉬움",
                "description": "시야 밖에서 E 시전 후 즉시 궁극기로 다인 넉업을 유발하고 광역 실드(W)를 챙기며 한타를 개시합니다."
            }
        ]
    },
    "Zed": {
        "resource_type": "기력 (Energy)",
        "mechanics": {
            "P": "체력 50% 이하 대상 평타 시 대상 최대 체력의 6~10% 추가 마법 피해",
            "Q": "전방으로 관통 표창을 날려 물리 피해. 그림자 분신도 동일하게 표창 투척",
            "W": "그림자 분신을 지정 위치에 생성. 재시전 시 그림자와 위치 교환. 분신과 동시 적중 시 기력 회복",
            "E": "주변을 회전하여 물리 피해. 분신이 맞히면 적중 적 둔화. 챔피언 적중 시 W 쿨다운 3초 감소",
            "R": "무적 상태로 대상에게 도약하여 그림자를 남기고 죽음의 표식 부여. 3초간 입힌 피해의 25/40/55%를 물리 피해로 재폭발"
        },
        "scalings": {
            "Q": "110% 추가 공격력",
            "W": "기력 회복 30/35/40/45/50",
            "E": "65% 추가 공격력",
            "R": "100% 총 공격력 + 표식 누적 피해 25/40/55%"
        },
        "combos": [
            {
                "name": "라인전 국민 WEQ 감전 포킹",
                "sequence": ["W", "E", "Q", "W (교환)", "AA (패시브)"],
                "difficulty": "쉬움",
                "description": "W 그림자를 적 방향으로 보내자마자 슬로우(E)를 묻혀 둔화된 적에게 확정 쌍표창(Q)을 적중시켜 감전을 터뜨립니다."
            },
            {
                "name": "트리플 표창 암살 올인 (R-W-E-Q)",
                "sequence": ["R", "W", "E", "Q (3표창)", "AA", "R (복귀)"],
                "difficulty": "고급",
                "description": "궁극기로 진입한 뒤 적의 도주로 쪽에 W를 깔아 본체 + R 그림자 + W 그림자 3개 위치에서 일제히 표창을 꽂아 즉사시킵니다."
            }
        ]
    },
    "LeeSin": {
        "resource_type": "기력 (Energy)",
        "mechanics": {
            "P": "스킬 시전 후 다음 2회의 기본 공격 속도가 증가하고 기력을 회복합니다.",
            "Q": "음파 적중 시 위치 노출. 공명의 일격 재시전 시 대상에게 돌진하며 대상 잃은 체력 비례 피해",
            "W": "아군/와드 도약 시 보호막 부여. 재시전 시 생명력 흡수 및 주문 흡혈 획득",
            "E": "지면을 강타해 마법 피해 및 은신 감지. 재시전 시 주변 적 둔화",
            "R": "대상을 강력하게 걷어차 뒤로 날려보내며 충돌하는 모든 적을 에어본"
        },
        "scalings": {
            "Q": "115% 추가 공격력 (잃은 체력 비례 최대 100% 증폭)",
            "W": "보호막: 50~250 (+80% 주문력) / 피흡: 10~26%",
            "E": "100% 추가 공격력",
            "R": "200% 추가 공격력 + 걷어찬 대상 추가 체력의 12/15/18%"
        },
        "combos": [
            {
                "name": "인섹킥 (InSec Kick 와드 배달)",
                "sequence": ["Q1", "Q2", "와드 (뒤편)", "W", "R"],
                "difficulty": "고급",
                "description": "음파(Q)를 맞히고 날아가는 도중 적 후방에 와드를 깔고 방호(W)로 넘어간 직후 궁극기(R)로 아군 진영으로 배달합니다."
            },
            {
                "name": "R-점멸 당구킥 (광역 넉업)",
                "sequence": ["Q1", "Q2", "R", "Flash", "AA"],
                "difficulty": "고급",
                "description": "적에게 궁극기를 시전하는 모션 도중 점멸로 각도를 틀어 일직선상의 다수 적을 맞히는 광역 당구킥을 완성합니다."
            },
            {
                "name": "근접 확정 원콤 (R-Q 확정 연계)",
                "sequence": ["E1", "AA", "R", "Q1", "Q2"],
                "difficulty": "보통",
                "description": "근접에서 적을 먼저 차버린(R) 날아가는 경로에 음파(Q)를 던져 100% 확정 적중시킨 후 잃은 체력 비례 피해로 마무리합니다."
            }
        ]
    },
    "Ahri": {
        "resource_type": "마나 (Mana)",
        "mechanics": {
            "P": "미니언 9마리 또는 챔피언 처치/어시스트 관여 시 즉시 체력 회복",
            "Q": "구슬을 던져 마법 피해를 입히고 돌아올 때 100% 고정 피해로 전환 타격",
            "W": "이동 속도가 순간 급증하며 주변 대상에게 여우불 3발 발사",
            "E": "적을 매혹하여 자신 쪽으로 무방비하게 끌어당김",
            "R": "지정 방향으로 돌진하며 주변 적에게 정령 미사일 발사 (기본 3회, 킬 관여 시 1회 충전)"
        },
        "scalings": {
            "Q": "45% 주문력 (왕복 총 90% 주문력 계수)",
            "W": "30% 주문력 (단일 대상 집중 타격)",
            "E": "60% 주문력 + 1.2~2.0초 지속",
            "R": "35% 주문력 (회당) / 최대 3~5회 시전"
        },
        "combos": [
            {
                "name": "매혹 점멸 기습 콤보 (E-Flash)",
                "sequence": ["E", "Flash", "Q", "W", "R", "AA"],
                "difficulty": "보통",
                "description": "E(매혹)을 누르자마자 점멸을 사용하여 모션 딜레이 없이 시야 밖에서 반응 불가능한 매혹을 꽂아넣은 후 Q-W-R 폭딜을 넣습니다."
            },
            {
                "name": "카이팅 돌진 암살 콤보",
                "sequence": ["R", "E", "Q", "W", "R (거리 조절)", "R (추격/탈출)"],
                "difficulty": "쉬움",
                "description": "R 돌진으로 사거리를 좁힌 뒤 확정 매혹을 맞히고 Q 왕복 고정딜과 여우불로 딜을 넣고 남은 R로 거리를 조절합니다."
            }
        ]
    },
    "Garen": {
        "resource_type": "노코스트",
        "mechanics": {
            "P": "8초간 피해를 입지 않으면 초당 최대 체력의 1.5~10.1%를 초고속 재생",
            "Q": "모든 둔화 효과 즉시 해제 & 이동 속도 35% 증가 & 다음 평타 침묵 및 급소 타격",
            "W": "기본 지속 효과로 방마저 최대 30 획득. 시전 시 4초간 받는 피해 30% 감소 및 강인함 60% 획득",
            "E": "3초간 회전하며 물리 피해. 6회 타격당한 적은 방어력 25% 파쇄. 가장 가까운 적 25% 추가 피해",
            "R": "대상 잃은 체력의 25/30/35%에 해당하는 100% 고정 피해 처형"
        },
        "scalings": {
            "Q": "50% 총 공격력 (포탑 적용)",
            "W": "방어력/마법저항력 중첩당 +0.2 (최대 30)",
            "E": "공격 속도 25%마다 회전 수 1회 증가 (기본 7~14회)",
            "R": "150/300/450 + 대상 잃은 체력의 25/30/35% 고정 피해"
        },
        "combos": [
            {
                "name": "국민 뚝배기 원콤 (Q-E-방깎-점화-R)",
                "sequence": ["Q (접근 침묵)", "E (6타 방깎)", "점화", "R (고정딜 처형)"],
                "difficulty": "쉬움",
                "description": "Q로 접근해 상대를 침묵시켜 도주기를 봉인한 후 E 회전베기로 방어력을 25% 깎고 점화와 궁극기(R) 고정 피해로 처형합니다."
            },
            {
                "name": "W 방어 반격 딜교환",
                "sequence": ["W (CC 흡수)", "Q", "E", "AA"],
                "difficulty": "쉬움",
                "description": "상대의 핵심 CC나 폭딜 타이밍에 W를 켜 강인함 60%로 흡수한 뒤 둔화를 Q로 풀며 역으로 진입합니다."
            }
        ]
    },
    "Darius": {
        "resource_type": "마나 (Mana)",
        "mechanics": {
            "P": "출혈 5스택 달성 시 녹서스의 힘 발동 (공격력 30~230 증가 & 평타마다 5스택 즉시 부여)",
            "Q": "도끼날 외곽 타격 시 적 챔피언당 잃은 체력의 13% 회복 (최대 39%)",
            "W": "다음 기본 공격 피해 증가 & 적 90% 둔화 & 평타 모션 캔슬",
            "E": "기본 지속으로 방어구 관통력 15~35% 획득. 시전 시 전방 적을 끌어당김",
            "R": "출혈 스택당 피해량 20% 증가 (최대 100% 증폭 고정 피해). 대상 처치 시 쿨타임 초기화"
        },
        "scalings": {
            "Q": "100/110/120/130/140% 총 공격력 (외곽 타격)",
            "W": "140/145/150/155/160% 총 공격력",
            "E": "방어구 관통력 15/20/25/30/35% 패시브 부여",
            "R": "125/250/375 (+75% 추가 공격력) -> 5스택 시 피해량 2배 (고정 피해)"
        },
        "combos": [
            {
                "name": "5스택 초고속 확정 처형",
                "sequence": ["AA", "W (평캔 90% 둔화)", "Q (외곽 확정)", "AA", "E (당기기)", "AA", "R"],
                "difficulty": "보통",
                "description": "평타 후 W로 캔슬하여 90% 둔화를 걸어 도끼날 외곽 Q를 100% 적중시키고, 도망치는 상대를 E로 당겨 5스택 단두대(R)로 처형합니다."
            },
            {
                "name": "E 선진입 기습 딜교환",
                "sequence": ["E (당기기)", "AA", "W (평캔)", "Q (외곽)", "AA"],
                "difficulty": "쉬움",
                "description": "사거리 535의 포획(E)으로 상대를 끌어온 후 즉시 평-W-외곽 Q를 확정 적중시켜 출혈 스택과 피흡 이득을 챙깁니다."
            }
        ]
    },
    "Aatrox": {
        "resource_type": "노코스트",
        "mechanics": {
            "P": "최대 체력의 4~12% 추가 피해를 입히고 가한 피해의 80%만큼 체력 회복",
            "Q": "3연속 검격. 검 끝(외곽) 적중 시 60% 추가 피해 및 에어본 유발",
            "W": "사슬을 던져 마법 피해 및 둔화. 1.5초 후 중심부로 끌어당김",
            "E": "짧은 돌진기. 챔피언에게 가한 물리 피해의 16~26%를 상시 체력 흡혈",
            "R": "이속 및 공격력 20~40% 증가 & 모든 치유 효과 25~45% 증폭 & 킬 관여 시 지속시간 연장"
        },
        "scalings": {
            "Q": "총 공격력 60/70/80/90/100% -> 외곽 타격 시 1.6배",
            "E": "충전 시간 9~5초 / 물리 피해 흡혈 16~26%",
            "R": "추가 공격력의 20/30/40% 총 공격력 버프"
        },
        "combos": [
            {
                "name": "QE 외곽 연계 풀콤보",
                "sequence": ["Q1", "E (사거리 조절)", "W", "Q2 (대각선)", "AA (패시브)", "W (끌어당김)", "Q3 (중앙 강타)"],
                "difficulty": "보통",
                "description": "Q1 시전 중 E 돌진으로 외곽 끝을 맞춰 띄운 뒤 W를 걸고, Q2로 슬로우를 연계해 W 끌림 위치에 Q3을 내려찍습니다."
            },
            {
                "name": "세계의 종결자 한타 돌진",
                "sequence": ["R (이속/공증)", "Q1", "E", "W", "Q2", "Q3 (점멸)"],
                "difficulty": "보통",
                "description": "R을 켜 이동 속도와 공격력을 급증시킨 뒤 E 돌진과 연계하여 적 딜러진 중앙에 Q3 점멸 강타로 한타를 폭파합니다."
            }
        ]
    },
    "Riven": {
        "resource_type": "노코스트",
        "mechanics": {
            "P": "스킬 시전 후 다음 기본 공격에 추가 물리 피해 부여 (최대 3회 중첩)",
            "Q": "3단 돌진 검격. 3번째 타격은 주변 모든 적을 공중에 띄움",
            "W": "주변 모든 적을 즉시 0.75초간 기절시키고 물리 피해",
            "E": "지정 방향으로 돌진하며 1.5초간 피해 흡수 보호막 획득",
            "R": "15초간 공격력 20% 증가 & 사거리 확장. 재시전 시 바람 가르기 투사체 발사 (잃은 체력 비례)"
        },
        "scalings": {
            "Q": "45/50/55/60/65% 총 공격력",
            "W": "100% 추가 공격력",
            "E": "100% 추가 공격력 보호막",
            "R": "공격력 20% 증가 + 바람 가르기 최대 300% 피해"
        },
        "combos": [
            {
                "name": "패스트 Q 평캔 콤보 (Fast Q AA Cancel)",
                "sequence": ["AA", "Q1", "땅 클릭 (모션 취소)", "AA", "Q2", "땅 클릭", "AA", "Q3"],
                "difficulty": "고급",
                "description": "평타 모션이 들어가자마자 Q를 쓰고 땅을 클릭해 Q 후딜레이를 캔슬하여 1초 안에 3연속 평타+스킬 폭딜을 꽂아넣습니다."
            },
            {
                "name": "E-R 모션 캔슬 기습 이니시",
                "sequence": ["E", "R1 (돌진 중 캔슬)", "Q3 (에어본)", "W (기절)", "AA", "R2 (바람가르기)"],
                "difficulty": "보통",
                "description": "E 돌진 중에 궁극기 켜는 모션을 캔슬하여 딜레이 없이 R을 켜고 에어본과 기절을 연속 연계합니다."
            }
        ]
    },
    "Jax": {
        "resource_type": "마나 (Mana)",
        "mechanics": {
            "P": "기본 공격 시 공격 속도 3.5~11% 증가 (최대 8중첩)",
            "Q": "아군/적군/와드로 도약하며 물리 피해",
            "W": "다음 기본 공격에 추가 마법 피해 부여 및 사거리 50 증가 (평캔 가능)",
            "E": "2초간 모든 기본 공격 완전 회피 & 광역 피해 25% 감소. 재시전 시 주변 적 1초 기절",
            "R": "주변 적을 타격해 마법 피해를 입히고 적 챔피언 수에 비례해 방어력과 마법 저항력 획득"
        },
        "scalings": {
            "Q": "100% 추가 공격력 + 60% 주문력",
            "W": "60% 주문력 + 온힛 적용",
            "E": "회피한 공격 횟수당 피해량 최대 100% 증가",
            "R": "방어력 +15~40 (+챔피언당 추가 방마저)"
        },
        "combos": [
            {
                "name": "E 돌진 확정 스턴 콤보",
                "sequence": ["E (반격 충전)", "Q (도약)", "AA", "W (평캔)", "E (스턴)", "R (방마저 버프)"],
                "difficulty": "쉬움",
                "description": "E를 미리 돌리며 Q로 진입해 평타-W를 욱여넣고 E를 터뜨려 기절시킨 후 R을 켜 맞다이에서 압승합니다."
            },
            {
                "name": "와드 도약 생존 및 기습",
                "sequence": ["와드 설치", "Q (와드 도약)", "E (반격)", "AA", "W"],
                "difficulty": "보통",
                "description": "위험한 갱킹 상황이나 장거리 추격 시 와드를 깔고 Q로 도약하여 벽을 넘거나 거리를 좁혀 기습합니다."
            }
        ]
    },
    "Ezreal": {
        "resource_type": "마나 (Mana)",
        "mechanics": {
            "P": "스킬 적중 시 공격 속도 10% 증가 (최대 5스택 50%)",
            "Q": "신비한 화살 적중 시 모든 스킬 재사용 대기시간 1.5초 감소 (온힛 적용)",
            "W": "적이나 구조물에 4초간 구체 부착. 다음 스킬이나 공격 타격 시 폭발하며 마나 회복",
            "E": "지정 위치로 순간이동하며 가장 가까운 적에게 화살 발사 (벽 넘기 가능)",
            "R": "맵 전체를 가로지르는 에너지파를 발사하여 통과하는 모든 적에게 마법 피해"
        },
        "scalings": {
            "Q": "130% 공격력 + 15% 주문력 (쿨감 1.5초 핵심)",
            "W": "60% 추가 공격력 + 70~90% 주문력",
            "E": "50% 추가 공격력 + 75% 주문력",
            "R": "100% 추가 공격력 + 90% 주문력"
        },
        "combos": [
            {
                "name": "W-E 앞비전 극딜 암살",
                "sequence": ["W", "E (앞비전)", "AA", "Q", "AA"],
                "difficulty": "보통",
                "description": "W를 맞힌 후 앞비전(E)을 타면 비전 화살이 W 부착 대상을 우선 추적해 즉시 W를 폭발시키며 Q로 마무리합니다."
            },
            {
                "name": "최장거리 저격 포킹",
                "sequence": ["W", "Q", "AA (패시브 유지)"],
                "difficulty": "쉬움",
                "description": "최대 사거리에서 W-Q 연계로 상대 체력을 깎고 패시브 공속을 5스택으로 유지합니다."
            }
        ]
    },
    "KaiSa": {
        "resource_type": "마나 (Mana)",
        "mechanics": {
            "P": "4스택 플라즈마 중첩 후 폭발 시 적 잃은 체력의 15% 마법 피해 (아군 CC도 스택 중첩)",
            "Q": "미사일 6발 (진화 시 12발) 발사. 단일 대상 집중 타격 시 폭발적 피해",
            "W": "초장거리 미사일 발사. 적중 시 플라즈마 2스택 (진화 시 3스택 및 쿨 75% 환급)",
            "E": "이속 대폭 증가 (진화 시 0.5초 투명화). 종료 후 공격 속도 버프 획득",
            "R": "플라즈마 표식이 있는 적 주변 초장거리 순간 돌진 및 거대 보호막 획득"
        },
        "scalings": {
            "Q": "50% 추가 공격력 + 20% 주문력 (단일 집중 시 계수 대폭 증가)",
            "W": "130% 공격력 + 120% 주문력 (핵심 포킹)",
            "E": "공격 속도 40~80% 증가",
            "R": "120% 공격력 + 120% 주문력 보호막"
        },
        "combos": [
            {
                "name": "W 저격 사냥본능 암살 (W-R-Q-AA)",
                "sequence": ["W (장거리 저격)", "R (돌진 보호막)", "AA", "Q", "E (은신 카이팅)", "AA (플라즈마 폭발)"],
                "difficulty": "보통",
                "description": "장거리 W로 2스택을 묻힌 즉시 궁극기(R)로 날아가 보호막을 얻고 평타-Q-평타로 5스택 플라즈마를 폭발시킵니다."
            },
            {
                "name": "고속 충전 카이팅 콤보",
                "sequence": ["E (공속 버프)", "AA", "Q (미사일 전탄)", "AA", "AA (패시브)"],
                "difficulty": "쉬움",
                "description": "E로 위치를 잡고 진화된 Q 미사일로 폭딜을 넣으며 빠르게 4타 플라즈마를 터뜨립니다."
            }
        ]
    },
    "Thresh": {
        "resource_type": "마나 (Mana)",
        "mechanics": {
            "P": "주변에 떨어진 영혼을 수집하여 영구적으로 방어력과 주문력 획득",
            "Q": "사형 선고를 날려 적을 기절시키고 당김. 재시전 시 적에게 직접 날아감",
            "W": "랜턴을 던져 아군에게 실드를 주고 랜턴을 클릭한 아군을 자신에게 끌어당김",
            "E": "사슬을 휘둘러 적을 앞이나 뒤로 밀쳐내며 둔화. 평타 차징 시 추가 마법 피해",
            "R": "영혼 감옥 5개 벽을 생성하여 벽을 뚫는 적에게 대량의 피해와 99% 둔화 부여"
        },
        "scalings": {
            "Q": "90% 주문력 + 1.5초 기절",
            "W": "영혼당 실드량 증가",
            "E": "차징 시 영혼 수 + 80~200% 총 공격력 온힛",
            "R": "100% 주문력 + 99% 둔화"
        },
        "combos": [
            {
                "name": "랜턴 배달 그랩 (W-Q-Q-E)",
                "sequence": ["W (아군 위치)", "Q1 (적 적중)", "Q2 (적에게 돌진)", "E (아군 쪽으로 밀치기)", "R"],
                "difficulty": "보통",
                "description": "정글러에게 랜턴을 던져 탑승시킨 뒤 그랩(Q)으로 적에게 날아가 2인이 동시에 적 챔피언 위로 덮칩니다."
            },
            {
                "name": "선 E 슬로우 후 확정 Q",
                "sequence": ["점멸", "E (뒤로 끌기)", "AA", "Q (확정 적중)", "R"],
                "difficulty": "쉬움",
                "description": "도주기가 있는 적에게 E로 먼저 슬로우와 넉백을 걸어 무빙을 제한한 후 확정적으로 그랩을 꽂습니다."
            }
        ]
    },
    "Blitzcrank": {
        "resource_type": "마나 (Mana)",
        "mechanics": {
            "P": "체력이 30% 이하로 떨어지면 최대 마나의 30%에 해당하는 보호막 생성",
            "Q": "로켓 손을 뻗어 적을 자신 바로 앞으로 즉시 끌어당김",
            "W": "이동 속도와 공격 속도가 순간 급증. 효과 종료 후 1.5초간 자체 둔화",
            "E": "다음 기본 공격으로 대상을 공중에 띄움 (평타 모션 캔슬)",
            "R": "주변 적의 모든 보호막을 즉시 파괴하고 광역 침묵 0.5초 부여"
        },
        "scalings": {
            "Q": "120% 주문력 계수",
            "E": "175% 총 공격력",
            "R": "100% 주문력 + 보호막 즉시 삭제"
        },
        "combos": [
            {
                "name": "국민 배달 콤보 (W-Q-E-R)",
                "sequence": ["W (가속 접근)", "Q (당기기)", "E (에어본)", "R (실드 삭제 및 침묵)"],
                "difficulty": "쉬움",
                "description": "W로 빠르게 접근하여 상대를 당겨온 후 E 에어본으로 띄우고 궁극기로 적의 점멸 및 스킬을 침묵으로 봉쇄합니다."
            },
            {
                "name": "점멸 확정 넉업 콤보 (Flash-E-R-Q)",
                "sequence": ["Flash", "E (즉발 에어본)", "R (침묵)", "Q (초근접 확정 그랩)"],
                "difficulty": "보통",
                "description": "투사체 보고 피하는 상대에게 점멸 E로 먼저 에어본을 꽂아 무빙을 봉쇄한 후 초근접에서 100% 확률로 그랩을 성공시킵니다."
            }
        ]
    }
}

# ==============================================================================
# 2. 챔피언 스킬 상세 데이터 단일 조회 엔진
# ==============================================================================
def get_champion_skills_data(champ_query: str) -> Optional[Dict[str, Any]]:
    """
    특정 챔피언의 P/Q/W/E/R 스킬명, 아이콘 경로, 레벨별 쿨다운(초), 마나 소모량,
    스킬 메커니즘, 계수 및 추천 콤보 가이드 반환.
    """
    champ_obj = find_champion(champ_query)
    if not champ_obj:
        return None

    champ_id = champ_obj["id"]
    champ_name = champ_obj.get("name", champ_id)
    title = champ_obj.get("title", "")

    raw_data = _load_raw_data()
    c_raw = raw_data.get(champ_id)

    # Data Dragon 원본이 없으면 쿨다운·소모값을 지어내지 않고 '정보 없음'(None)으로 처리
    if not c_raw:
        return None

    # 1. Passive Data Parsing
    p_raw = c_raw.get("passive", {})
    p_img = p_raw.get("image", {}).get("full", f"{champ_id}_Passive.png")
    passive_data = {
        "key": "P",
        "key_label": "패시브",
        "name": p_raw.get("name", "기본 지속 효과"),
        "icon": f"{DDRAGON_CDN}/img/passive/{p_img}",
        "description": _strip_html(p_raw.get("description", "")),
        "cooldown": "기본 지속 효과",
        "cooldown_list": [0],
        "cost": "소모값 없음",
        "mana_cost": "소모값 없음",
        "cost_type": "소모값 없음",
        "range": "-",
        "mechanic_summary": CURATED_CHAMPION_DETAILS.get(champ_id, {}).get("mechanics", {}).get("P"),
        "scaling_info": CURATED_CHAMPION_DETAILS.get(champ_id, {}).get("scalings", {}).get("P")
    }

    # 2. Spells (Q, W, E, R) Parsing
    spells_raw = c_raw.get("spells", [])
    keys = ["Q", "W", "E", "R"]
    skills_dict = {"P": passive_data}
    skills_list = [passive_data]

    curated = CURATED_CHAMPION_DETAILS.get(champ_id, {})
    curated_mechanics = curated.get("mechanics", {})
    curated_scalings = curated.get("scalings", {})
    resource_type = curated.get("resource_type") or c_raw.get("partype", "마나")

    for idx, key in enumerate(keys):
        if idx < len(spells_raw):
            sp = spells_raw[idx]
            sp_img = sp.get("image", {}).get("full", f"{champ_id}{key}.png")
            cd_burn = sp.get("cooldownBurn", "0")
            cd_list = sp.get("cooldown", [0])
            cost_burn = sp.get("costBurn", "0")
            cost_list = sp.get("cost", [0])
            cost_type_raw = sp.get("costType", "")

            # Formatted cooldown display
            cd_display = f"{cd_burn} 초" if cd_burn and cd_burn != "0" else "패시브 / 쿨타임 없음"

            # Formatted cost display
            if cost_burn == "0" or not cost_burn:
                cost_display = "소모값 없음"
                cost_type = "소모값 없음"
            elif "기력" in cost_type_raw or "energy" in str(cost_type_raw).lower() or "기력" in resource_type:
                cost_display = f"{cost_burn} 기력"
                cost_type = "기력"
            elif "체력" in cost_type_raw or "health" in str(cost_type_raw).lower():
                cost_display = f"{cost_burn} 체력"
                cost_type = "체력"
            else:
                cost_display = f"{cost_burn} 마나"
                cost_type = "마나"

            # Extract mechanic summary
            mech = curated_mechanics.get(key)
            if not mech:
                desc_first_line = _strip_html(sp.get("description", "")).split(".")[0]
                mech = desc_first_line or None

            # 계수는 Data Dragon에 숫자로 나오지 않으므로 직접 정리한 챔피언 외에는 비워 둔다
            scaling = curated_scalings.get(key)

            skill_info = {
                "key": key,
                "key_label": f"{key} 스킬" if key != "R" else "R (궁극기)",
                "name": sp.get("name", f"{champ_name} {key}"),
                "icon": f"{DDRAGON_CDN}/img/spell/{sp_img}",
                "description": _strip_html(sp.get("description", "")),
                "cooldown": cd_display,
                "cooldown_burn": cd_burn,
                "cooldown_list": cd_list,
                "cost": cost_display,
                "mana_cost": cost_display,
                "cost_burn": cost_burn,
                "cost_list": cost_list,
                "cost_type": cost_type,
                "range": str(sp.get("rangeBurn", sp.get("range", ["-"])[0])),
                "mechanic_summary": mech,
                "scaling_info": scaling
            }
            skills_dict[key] = skill_info
            skills_list.append(skill_info)

    # 3. Tactical Combo Guide
    # 직접 정리한 챔피언만 콤보를 준다. 나머지 챔피언에 붙이던 "Q-E-평타-W" 같은 공통 문구는
    # 챔피언과 무관하게 만든 내용이라 빈 목록으로 둔다.
    combos = curated.get("combos") or []

    return {
        "champion_id": champ_id,
        "champion_name": champ_name,
        "title": title,
        "resource_type": resource_type,
        "passive": passive_data,
        "skills": skills_dict,
        "skills_list": skills_list,
        "combos": combos,
        # 예전 값("Q > E > W")은 모든 챔피언에 똑같이 넣던 고정값이었다. 실제 선마 통계가 없으므로 비워 둔다.
        "skill_master_order": None,
        "patch_version": _RAW_DATA_VERSION,
        "status": "success"
    }
