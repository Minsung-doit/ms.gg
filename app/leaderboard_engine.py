"""
래더(랭킹) 호환 모듈

실제 챌린저 랭킹은 app/real_data.py (sync_challenger_ladder / load_ladder, ladder_real 테이블)가 담당한다.
예전에 이 모듈이 만들던 난수 랭킹(가짜 LP 추이·연승 배지·모스트 챔피언·레벨)과, 이름 확인에 실패하면
다른 프로게이머 이름을 채워 넣던 동기화 코드는 데이터 원칙(CLAUDE.md) 위반이라 제거했다.
"""
import time
from typing import Dict, Any
from app.champion_engine import ALL_CHAMPIONS

CHAMP_BY_ID = {c["id"].lower(): c for c in ALL_CHAMPIONS}

# 멀티서치(생성 데이터 기능, 기본 비활성) 전용 이름 목록. 순위·LP·전적 데이터가 아니다.
TOP_LADDER_REAL_PLAYERS = [
    ("Hide on bush", "KR1", "T1 Faker", ["Ahri", "Azir", "Orianna"]),
    ("Chovy", "KR1", "Gen.G Chovy", ["Yone", "Sylas", "Ahri"]),
    ("ShowMaker", "KR1", "DK ShowMaker", ["Syndra", "LeBlanc", "Kassadin"]),
    ("Canyon", "KR1", "Gen.G Canyon", ["Nidalee", "LeeSin", "KhaZix"]),
    ("Viper", "KR1", "HLE Viper", ["Ezreal", "Kaisa", "Varus"]),
    ("Ruler", "KR1", "Gen.G Ruler", ["Jinx", "Zeri", "Ashe"]),
    ("Peyz", "KR1", "JDG Peyz", ["Kaisa", "Zeri", "Aphelios"]),
    ("Gumayusi", "KR1", "T1 Gumayusi", ["Jhin", "Varus", "Caitlyn"]),
    ("Keria", "KR1", "T1 Keria", ["Thresh", "Lulu", "Nautilus"]),
    ("Zeus", "KR1", "HLE Zeus", ["Jayce", "Yone", "Aatrox"]),
    ("Kiin", "KR1", "Gen.G Kiin", ["KSante", "Renekton", "Jax"]),
    ("Oner", "KR1", "T1 Oner", ["LeeSin", "XinZhao", "Sejuani"]),
    ("Lehends", "KR1", "NS Lehends", ["Blitzcrank", "Rakan", "Singed"]),
    ("Delight", "KR1", "HLE Delight", ["Rakan", "Alistar", "Nautilus"]),
    ("Doran", "KR1", "T1 Doran", ["Gnar", "Gragas", "Renekton"]),
    ("Zeka", "KR1", "HLE Zeka", ["Akali", "Sylas", "Yone"]),
    ("Bdd", "KR1", "KT Bdd", ["Azir", "Orianna", "Taliyah"]),
    ("Deft", "KR1", "Deft", ["Ezreal", "Jinx", "Varus"]),
    ("BeryL", "KR1", "DK BeryL", ["Heimerdinger", "Braum", "Amumu"]),
    ("Peanut", "KR1", "HLE Peanut", ["Poppy", "Vi", "Sejuani"]),
    ("Pyosik", "KR1", "KT Pyosik", ["Kindred", "LeeSin", "Viego"]),
    ("Lucid", "KR1", "DK Lucid", ["LeeSin", "Viego", "Vi"]),
    ("Aiming", "KR1", "DK Aiming", ["Kaisa", "Ezreal", "Zeri"]),
    ("Kingen", "KR1", "DK Kingen", ["Aatrox", "Ornn", "Gnar"]),
    ("Cuzz", "KR1", "KDF Cuzz", ["Viego", "Sejuani", "JarvanIV"]),
    ("Pz ZZZ", "KR1", "프제짱 야스오", ["Yasuo", "Yone", "Irelia"]),
    ("율천고 최현우", "KR1", "제드 장인", ["Zed", "Talon", "Qiyana"]),
    ("제동빠", "KR1", "리신 장인", ["LeeSin", "Elise", "Nidalee"]),
    ("꿀탱탱", "KR1", "리븐 장인", ["Riven", "Fiora", "Camille"]),
    ("순당무", "KR1", "룰루 장인", ["Lulu", "Janna", "Nami"]),
    ("코레아", "KR1", "샤코 장인", ["Shaco", "Evelynn", "Kayn"]),
    ("만기퇴소", "KR1", "갱플랭크 장인", ["Gangplank", "Aatrox", "Jayce"]),
    ("눈가루", "KR1", "레넥톤 장인", ["Renekton", "Sett", "Darius"]),
    ("나라카일", "KR1", "제이스 장인", ["Jayce", "Ryze", "Cassiopeia"]),
    ("괴물쥐", "KR1", "원딜 장인", ["Ezreal", "Twitch", "KogMaw"]),
    ("과로사", "KR1", "탈론 장인", ["Talon", "Zed", "Katarina"]),
    ("Dopa", "KR1", "도파", ["TwistedFate", "Orianna", "Kassadin"]),
    ("The shy", "KR1", "더샤이", ["Aatrox", "Jayce", "Gnar"]),
    ("Nuguri", "KR1", "너구리", ["Kennen", "Jayce", "Camille"]),
    ("Uzi", "KR1", "우지", ["Vayne", "Kaisa", "Lucian"]),
    ("Kanavi", "KR1", "카나비", ["Nidalee", "LeeSin", "Belveth"]),
    ("Tarzan", "KR1", "타잔", ["Sejuani", "JarvanIV", "Olaf"]),
    ("Scout", "KR1", "스카웃", ["Azir", "Syndra", "Ryze"]),
    ("Rookie", "KR1", "루키", ["Orianna", "Syndra", "LeBlanc"]),
    ("Clid", "KR1", "클리드", ["LeeSin", "JarvanIV", "Elise"]),
    ("Teddy", "KR1", "테디", ["Ezreal", "Varus", "Ashe"]),
    ("Karis", "KR1", "카리스", ["Ahri", "Sylas", "Taliyah"]),
    ("Clozer", "KR1", "클로저", ["Irelia", "Akali", "Yone"]),
    ("Bulldog", "KR1", "불독", ["Tristana", "Corki", "Azir"]),
    ("Taeyoon", "KR1", "태윤", ["Kaisa", "Zeri", "Jinx"]),
    ("Duudu", "KR1", "두두", ["KSante", "Fiora", "Aatrox"]),
    ("Morgan", "KR1", "모건", ["Renekton", "Camille", "Sion"]),
    ("Peter", "KR1", "피터", ["Nautilus", "Rell", "Leona"]),
    ("Life", "KR1", "라이프", ["Sett", "Gragas", "JarvanIV"]),
    ("Effort", "KR1", "에포트", ["Alistar", "Nautilus", "Rakan"]),
    ("Andil", "KR1", "안딜", ["Braum", "Thresh", "Nami"]),
    ("Moham", "KR1", "모함", ["Leona", "Rell", "Alistar"]),
    ("Pollu", "KR1", "폴루", ["Rakan", "Nautilus", "Thresh"]),
    ("Sponge", "KR1", "스폰지", ["XinZhao", "Viego", "Vi"]),
    ("Sylvie", "KR1", "실비", ["JarvanIV", "Sejuani", "Poppy"]),
    ("GIDEON", "KR1", "기디온", ["LeeSin", "Nocturne", "Vi"]),
    ("Raptor", "KR1", "랩터", ["Viego", "LeeSin", "Wukong"]),
    ("Fisher", "KR1", "피셔", ["Taliyah", "Azir", "Tristana"]),
    ("FIESTA", "KR1", "피에스타", ["Yone", "Sylas", "Akali"]),
    ("Envyy", "KR1", "엔비", ["Aphelios", "Varus", "Ashe"]),
    ("Jiwoo", "KR1", "지우", ["Nilah", "Samira", "Kaisa"]),
    ("Paduck", "KR1", "파덕", ["Zeri", "Jinx", "Lucian"]),
    ("Bull", "KR1", "불", ["Kalista", "Varus", "Senna"]),
    ("Rooster", "KR1", "루스터", ["Aatrox", "Jax", "Rumble"]),
    ("Clear", "KR1", "클리어", ["Gnar", "Renekton", "KSante"]),
    ("Soboro", "KR1", "소보로", ["Camille", "Fiora", "Irelia"]),
    ("IlllIIIIll", "KR1", "챌린저 랭커", ["LeeSin", "Nidalee", "Graves"]),
    ("민재는 아가야", "KR1", "천상계 랭커", ["TwistedFate", "Ahri", "Vex"]),
    ("꿀꿀", "KR1", "챌린저 꿀꿀", ["Gragas", "Malphite", "Ornn"]),
    ("홍길동", "KR1", "천상계 홍길동", ["Shen", "Poppy", "TahmKench"]),
    ("Poby", "KR1", "T1 Poby (윤성원)", ["Orianna", "Azir", "Syndra"]),
    ("Smash", "KR1", "T1 Smash (신금재)", ["KaiSa", "Ezreal", "Jhin"]),
    ("Guwon", "KR1", "T1 Guwon (구관모)", ["LeeSin", "Sejuani", "JarvanIV"]),
    ("Clozer", "KR1", "BNK Clozer (이주현)", ["Irelia", "Yone", "Akali"]),
    ("Clear", "KR1", "BNK Clear (송현민)", ["Rumble", "Gnar", "Renekton"]),
    ("Raptor", "KR1", "BNK Raptor (전어진)", ["Vi", "Nocturne", "Poppy"]),
    ("Hena", "KR1", "BNK Hena (박증환)", ["Varus", "Ashe", "MissFortune"]),
    ("Duro", "KR1", "Gen.G Duro (주민규)", ["Alistar", "Rell", "Nautilus"]),
    ("Sponge", "KR1", "DRX Sponge (배영준)", ["XinZhao", "Sejuani", "Viego"]),
    ("Setab", "KR1", "DRX Setab (송경진)", ["Taliyah", "Tristana", "Corki"]),
    ("Teddy", "KR1", "DRX Teddy (박진성)", ["Kalista", "Caitlyn", "Senna"]),
    ("Pleata", "KR1", "DRX Pleata (손민우)", ["Rakan", "Leona", "Braum"]),
    ("Frog", "KR1", "DRX Frog (이민섭)", ["Kennen", "Jax", "Aatrox"]),
    ("Cuzz", "KR1", "KDF Cuzz (문우찬)", ["Viego", "LeeSin", "Nidalee"]),
    ("DuDu", "KR1", "KDF DuDu (이동주)", ["KSante", "Gnar", "Aatrox"]),
    ("BuLLDoG", "KR1", "KDF BuLLDoG (이태영)", ["Yone", "Sylas", "Jayce"]),
    ("Andil", "KR1", "KDF Andil (유관우)", ["Nautilus", "Thresh", "Blitzcrank"]),
    ("Taeyoon", "KR1", "소환사 Taeyoon", ["Lucian", "Aphelios", "Zeri"]),
    ("VicLa", "KR1", "소환사 VicLa", ["Ahri", "LeBlanc", "Akali"]),
    ("Calix", "KR1", "천상계 Calix", ["Viktor", "Syndra", "Orianna"]),
    ("Paduck", "KR1", "천상계 Paduck", ["Jinx", "Sivir", "Vayne"]),
    ("Execute", "KR1", "천상계 Execute", ["Bard", "Pyke", "Thresh"]),
    ("Quantum", "KR1", "천상계 Quantum", ["Graves", "KhaZix", "Kindred"]),
    ("Dal", "KR1", "T1 Dal (문성원)", ["Camille", "Fiora", "Jayce"]),
    ("Rekan", "KR1", "소환사 Rekan", ["Lulu", "Nami", "Karma"])
]

# 라이엇 래더는 1회 동기화에 50건 이상 호출하므로 이 간격 안에 갱신된 랭킹이 있으면 다시 받지 않는다
LADDER_MIN_SYNC_INTERVAL_SEC = 1800


async def sync_real_riot_leaderboard(max_players: int = 50) -> Dict[str, Any]:
    """
    예전 이름 호환용 (scripts/run_production_daemon.py 가 사용).
    실제 동기화는 real_data.sync_challenger_ladder 에 맡긴다 (레이트 리미터 경유, 값을 지어내지 않음).
    """
    from app.real_data import PlayerDataUnavailable, load_ladder, sync_challenger_ladder

    updated_at = load_ladder()["updated_at"] or 0
    if time.time() - updated_at < LADDER_MIN_SYNC_INTERVAL_SEC:
        return {"status": "skipped", "message": "최근 30분 안에 갱신된 랭킹이 있어 다시 받지 않았습니다.", "updated_at": updated_at}
    try:
        return await sync_challenger_ladder(top_n=max_players)
    except PlayerDataUnavailable as e:
        return {"status": "error", "message": e.detail}
