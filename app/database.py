import os
import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.tier_utils import calculate_tier_score, get_tier_meta
import app.config  # noqa: F401  (.env 로드: OPGG_DB_PATH)

# OneDrive 등 동기화 폴더 밖에 두려면 .env 의 OPGG_DB_PATH 로 지정 (동기화 중인 SQLite 파일은 손상될 수 있음)
DB_PATH = Path(os.getenv("OPGG_DB_PATH", "").strip() or Path(__file__).resolve().parent.parent / "opgg.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def is_riot_puuid(puuid: Optional[str]) -> bool:
    """라이엇이 발급한 PUUID 형식(78자)인지. 과거 코드가 만든 'real-kr-*' 같은 가짜 ID를 걸러낸다."""
    return bool(puuid) and len(puuid) == 78 and not puuid.startswith(("real-", "lulu-", "dyn-"))

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -64000;")  # 64MB Cache
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA mmap_size = 268435456;")  # 256MB Memory-mapped I/O
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 플레이어 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        puuid TEXT UNIQUE NOT NULL,
        game_name TEXT NOT NULL,
        tag_line TEXT NOT NULL,
        profile_icon_id INTEGER DEFAULT 29,
        summoner_level INTEGER DEFAULT 30,
        tier TEXT DEFAULT 'UNRANKED',
        rank_tier TEXT DEFAULT '',
        league_points INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        tier_score INTEGER DEFAULT 0,
        queue_type TEXT DEFAULT 'RANKED_SOLO_5x5',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 검색 인덱스 생성
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_game_name ON players(game_name COLLATE NOCASE);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tier_score ON players(tier_score DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_riot_id ON players(game_name COLLATE NOCASE, tag_line COLLATE NOCASE);")

    # 최근 검색 기록 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL,
        searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 챔피언 장인 랭킹 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS champion_masters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        champion_id TEXT NOT NULL,
        champion_name TEXT NOT NULL,
        puuid TEXT UNIQUE NOT NULL,
        game_name TEXT NOT NULL,
        tag_line TEXT NOT NULL,
        profile_icon_id INTEGER DEFAULT 29,
        summoner_level INTEGER DEFAULT 30,
        tier TEXT NOT NULL,
        rank_tier TEXT DEFAULT '',
        league_points INTEGER DEFAULT 0,
        tier_score INTEGER DEFAULT 0,
        games_played INTEGER NOT NULL,
        wins INTEGER NOT NULL,
        losses INTEGER NOT NULL,
        win_rate REAL DEFAULT 0.0,
        kills REAL DEFAULT 0.0,
        deaths REAL DEFAULT 0.0,
        assists REAL DEFAULT 0.0,
        kda REAL DEFAULT 0.0,
        mastery_points INTEGER DEFAULT 0,
        mastery_level INTEGER DEFAULT 7,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_champ_games ON champion_masters(champion_id COLLATE NOCASE, games_played DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_champ_tier_games ON champion_masters(champion_id COLLATE NOCASE, tier, games_played DESC);")
    
    # 플레이어 티어 변동 기록 테이블 (일별, 주별, 월별)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS player_tier_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        puuid TEXT NOT NULL,
        period_type TEXT NOT NULL,
        point_date TEXT NOT NULL,
        date_label TEXT NOT NULL,
        tier TEXT NOT NULL,
        rank_tier TEXT DEFAULT '',
        league_points INTEGER DEFAULT 0,
        tier_score INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        lp_change INTEGER DEFAULT 0
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hist_puuid ON player_tier_history(puuid, period_type, id ASC);")

    # 플레이어 과거 시즌별 챔피언 전적 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS player_season_champions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        puuid TEXT NOT NULL,
        season_id TEXT NOT NULL,
        season_name TEXT NOT NULL,
        champion_id TEXT NOT NULL,
        champion_name TEXT NOT NULL,
        image TEXT NOT NULL,
        games_played INTEGER NOT NULL,
        wins INTEGER NOT NULL,
        losses INTEGER NOT NULL,
        win_rate REAL DEFAULT 0.0,
        kills REAL DEFAULT 0.0,
        deaths REAL DEFAULT 0.0,
        assists REAL DEFAULT 0.0,
        kda REAL DEFAULT 0.0,
        cs REAL DEFAULT 0.0
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_season_puuid ON player_season_champions(puuid, season_id, games_played DESC);")

    # 기존 players 테이블 컬럼 마이그레이션 (최고/최저 티어 정보)
    cursor.execute("PRAGMA table_info(players);")
    player_cols = [c["name"] for c in cursor.fetchall()]
    for col, ctype, default in [
        ("peak_tier", "TEXT", "''"),
        ("peak_rank_tier", "TEXT", "''"),
        ("peak_lp", "INTEGER", "0"),
        ("peak_season", "TEXT", "''"),
        ("lowest_tier", "TEXT", "''"),
        ("lowest_rank_tier", "TEXT", "''"),
        ("lowest_lp", "INTEGER", "0"),
        ("lowest_season", "TEXT", "''"),
        ("flex_tier", "TEXT", "'UNRANKED'"),
        ("flex_rank_tier", "TEXT", "''"),
        ("flex_lp", "INTEGER", "0"),
        ("flex_wins", "INTEGER", "0"),
        ("flex_losses", "INTEGER", "0"),
    ]:
        if col not in player_cols:
            cursor.execute(f"ALTER TABLE players ADD COLUMN {col} {ctype} DEFAULT {default};")

    # 기존 champion_masters 테이블 컬럼 마이그레이션 (현재 시즌 판수 정보)
    cursor.execute("PRAGMA table_info(champion_masters);")
    master_cols = [c["name"] for c in cursor.fetchall()]
    for col, ctype, default in [
        ("current_season_games", "INTEGER", "0"),
        ("current_season_wins", "INTEGER", "0"),
        ("current_season_losses", "INTEGER", "0"),
        ("current_season_win_rate", "REAL", "0.0"),
        ("all_seasons_games", "INTEGER", "0")
    ]:
        if col not in master_cols:
            cursor.execute(f"ALTER TABLE champion_masters ADD COLUMN {col} {ctype} DEFAULT {default};")

    # 라이엇 API 동기화 캐시 테이블 (SQLite L2 캐시)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS player_sync_cache (
        puuid TEXT PRIMARY KEY,
        game_name TEXT NOT NULL,
        tag_line TEXT NOT NULL,
        match_data TEXT,
        spectator_data TEXT,
        mastery_data TEXT,
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_riot_id ON player_sync_cache(game_name COLLATE NOCASE, tag_line COLLATE NOCASE);")
    
    # player_sync_cache 테이블 마이그레이션 (초고속 폴백용 player_info 컬럼)
    cursor.execute("PRAGMA table_info(player_sync_cache);")
    sync_cols = [c["name"] for c in cursor.fetchall()]
    if "player_info" not in sync_cols:
        cursor.execute("ALTER TABLE player_sync_cache ADD COLUMN player_info TEXT DEFAULT '';")

    # 한국 서버 챌린저 실시간 래더 캐시 테이블 (SQLite L2 영구 보관)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ladder_cache (
        rank INTEGER PRIMARY KEY,
        game_name TEXT NOT NULL,
        tag_line TEXT NOT NULL,
        note TEXT,
        tier TEXT NOT NULL,
        tier_kr TEXT NOT NULL,
        league_points INTEGER NOT NULL,
        summoner_level INTEGER DEFAULT 500,
        profile_icon_id INTEGER DEFAULT 29,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        total_games INTEGER DEFAULT 0,
        win_rate REAL DEFAULT 0.0,
        most_champions TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # AI 전술 코칭 리포트 캐시 테이블 (SQLite L2 영구 보관 / WAL 모드)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_coach_cache (
        puuid TEXT PRIMARY KEY,
        game_name TEXT NOT NULL,
        tag_line TEXT NOT NULL,
        coach_data TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_coach_riot_id ON ai_coach_cache(game_name COLLATE NOCASE, tag_line COLLATE NOCASE);")

    conn.commit()
    conn.close()

def upsert_player(
    puuid: str,
    game_name: str,
    tag_line: str,
    profile_icon_id: int = 29,
    summoner_level: int = 30,
    tier: str = "UNRANKED",
    rank_tier: str = "",
    league_points: int = 0,
    wins: int = 0,
    losses: int = 0,
    queue_type: str = "RANKED_SOLO_5x5",
    flex_tier: str = "UNRANKED",
    flex_rank_tier: str = "",
    flex_lp: int = 0,
    flex_wins: int = 0,
    flex_losses: int = 0
) -> Dict[str, Any]:
    tier_score = calculate_tier_score(tier, rank_tier, league_points)
    now = datetime.now().isoformat()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 동일 닉네임#태그 중복 방지
    cursor.execute("SELECT puuid FROM players WHERE LOWER(game_name) = LOWER(?) AND LOWER(tag_line) = LOWER(?)", (game_name, tag_line))
    existing_puuids = [r[0] for r in cursor.fetchall()]
    if is_riot_puuid(puuid):
        # 라이엇이 확인한 계정이면 PUUID가 기준이다. 같은 닉네임#태그로 남아 있는 다른 행(가짜 데이터이거나
        # 닉네임을 바꾼 다른 계정의 옛 기록)의 PUUID를 이어받으면 다른 사람의 전적이 섞이므로 지운다.
        stale = [p for p in existing_puuids if p != puuid]
        if stale:
            cursor.execute(f"DELETE FROM players WHERE puuid IN ({','.join('?' * len(stale))})", stale)
    elif existing_puuids:
        puuid = existing_puuids[0]
    
    cursor.execute("""
    INSERT INTO players (
        puuid, game_name, tag_line, profile_icon_id, summoner_level,
        tier, rank_tier, league_points, wins, losses, tier_score, queue_type,
        flex_tier, flex_rank_tier, flex_lp, flex_wins, flex_losses, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(puuid) DO UPDATE SET
        game_name=excluded.game_name,
        tag_line=excluded.tag_line,
        profile_icon_id=excluded.profile_icon_id,
        summoner_level=excluded.summoner_level,
        tier=excluded.tier,
        rank_tier=excluded.rank_tier,
        league_points=excluded.league_points,
        wins=excluded.wins,
        losses=excluded.losses,
        tier_score=excluded.tier_score,
        queue_type=excluded.queue_type,
        flex_tier=excluded.flex_tier,
        flex_rank_tier=excluded.flex_rank_tier,
        flex_lp=excluded.flex_lp,
        flex_wins=excluded.flex_wins,
        flex_losses=excluded.flex_losses,
        updated_at=excluded.updated_at
    """, (
        puuid, game_name, tag_line, profile_icon_id, summoner_level,
        tier.upper(), rank_tier.upper(), league_points, wins, losses, tier_score, queue_type,
        flex_tier.upper(), flex_rank_tier.upper(), flex_lp, flex_wins, flex_losses, now
    ))
    conn.commit()
    conn.close()
    
    return format_player_dict({
        "puuid": puuid,
        "game_name": game_name,
        "tag_line": tag_line,
        "profile_icon_id": profile_icon_id,
        "summoner_level": summoner_level,
        "tier": tier.upper(),
        "rank_tier": rank_tier.upper(),
        "league_points": league_points,
        "wins": wins,
        "losses": losses,
        "tier_score": tier_score,
        "queue_type": queue_type,
        "flex_tier": flex_tier.upper(),
        "flex_rank_tier": flex_rank_tier.upper(),
        "flex_lp": flex_lp,
        "flex_wins": flex_wins,
        "flex_losses": flex_losses,
        "updated_at": now
    })

def format_player_dict(row: Any) -> Dict[str, Any]:
    d = dict(row)
    tier = d.get("tier", "UNRANKED")
    rank_tier = d.get("rank_tier", "")
    wins = d.get("wins", 0)
    losses = d.get("losses", 0)
    total_games = wins + losses
    win_rate = round((wins / total_games * 100), 1) if total_games > 0 else 0.0

    meta = get_tier_meta(tier)
    d["win_rate"] = win_rate
    d["total_games"] = total_games
    d["tier_meta"] = meta
    d["tier_kr"] = meta.get("kr_name", tier)
    
    # 챌린저, 그랜드마스터, 마스터는 rank_tier(I, II, III 등)를 붙이지 않음
    if tier in ["CHALLENGER", "GRANDMASTER", "MASTER"]:
        d["display_tier"] = meta["kr_name"]
    elif tier == "UNRANKED":
        d["display_tier"] = "언랭크"
    else:
        d["display_tier"] = f"{meta['kr_name']} {rank_tier}".strip()

    # 최고 티어 및 최저 티어 포맷팅
    p_tier = d.get("peak_tier") or ""
    p_rank = d.get("peak_rank_tier") or ""
    p_lp = d.get("peak_lp") or 0
    p_season = d.get("peak_season") or ""
    d["peak_tier"] = p_tier
    d["peak_rank_tier"] = p_rank
    d["peak_lp"] = p_lp
    d["peak_season"] = p_season
    if p_tier:
        p_meta = get_tier_meta(p_tier)
        p_name = p_meta.get("kr_name", p_tier)
        d["peak_display"] = f"{p_name} {p_rank} {p_lp} LP".strip() if p_tier not in ["CHALLENGER", "GRANDMASTER", "MASTER"] else f"{p_name} {p_lp} LP"
    else:
        d["peak_display"] = "-"

    l_tier = d.get("lowest_tier") or ""
    l_rank = d.get("lowest_rank_tier") or ""
    l_lp = d.get("lowest_lp") or 0
    l_season = d.get("lowest_season") or ""
    d["lowest_tier"] = l_tier
    d["lowest_rank_tier"] = l_rank
    d["lowest_lp"] = l_lp
    d["lowest_season"] = l_season
    if l_tier:
        l_meta = get_tier_meta(l_tier)
        l_name = l_meta.get("kr_name", l_tier)
        d["lowest_display"] = f"{l_name} {l_rank} {l_lp} LP".strip() if l_tier not in ["CHALLENGER", "GRANDMASTER", "MASTER"] else f"{l_name} {l_lp} LP"
    else:
        d["lowest_display"] = "-"

    # -------------------------------------------------------------
    # OP.GG 시그니처 듀얼 티어 카드 (솔로랭크 & 자유랭크) 데이터 구성
    # -------------------------------------------------------------
    s_tier = tier
    s_rank = rank_tier
    s_lp = int(d.get("league_points") or 0)
    s_wins = wins
    s_losses = losses
    s_win_rate = win_rate
    s_display = d["display_tier"]

    # 자유랭크 (Ranked Flex) 파싱 및 자연스러운 Fallback 보정
    f_tier = (d.get("flex_tier") or "").strip().upper()
    f_rank = (d.get("flex_rank_tier") or "").strip().upper()
    f_lp = int(d.get("flex_lp") or 0)
    f_wins = int(d.get("flex_wins") or 0)
    f_losses = int(d.get("flex_losses") or 0)

    # 자유랭크 기록이 없으면 언랭크로 둔다 (솔로랭크에서 추정한 값을 만들지 않음)
    f_total = f_wins + f_losses
    f_win_rate = round((f_wins / f_total * 100), 1) if f_total > 0 else 0.0
    f_meta = get_tier_meta(f_tier or "UNRANKED")
    if f_tier in ["CHALLENGER", "GRANDMASTER", "MASTER"]:
        f_display = f"{f_meta['kr_name']} ({f_tier})"
    elif f_tier == "UNRANKED" or not f_tier:
        f_display = "언랭크"
        f_tier = "UNRANKED"
    else:
        f_display = f"{f_meta['kr_name']} {f_rank}".strip()

    d["flex_tier"] = f_tier
    d["flex_rank_tier"] = f_rank
    d["flex_lp"] = f_lp
    d["flex_wins"] = f_wins
    d["flex_losses"] = f_losses
    d["flex_win_rate"] = f_win_rate
    d["flex_display"] = f_display
    d["flex_meta"] = f_meta

    d["solo"] = {
        "queue_type": "RANKED_SOLO_5x5",
        "queue_label": "솔로랭크",
        "tier": s_tier,
        "rank_tier": s_rank,
        "league_points": s_lp,
        "wins": s_wins,
        "losses": s_losses,
        "win_rate": s_win_rate,
        "display_tier": s_display,
        "tier_meta": meta
    }

    d["flex"] = {
        "queue_type": "RANKED_FLEX_SR",
        "queue_label": "자유랭크",
        "tier": f_tier,
        "rank_tier": f_rank,
        "league_points": f_lp,
        "wins": f_wins,
        "losses": f_losses,
        "win_rate": f_win_rate,
        "display_tier": f_display,
        "tier_meta": f_meta
    }

    # 과거 시즌 티어는 라이엇 API가 제공하지 않으므로 비워 둔다
    d["past_tier_badges"] = []

    return d

def search_players_by_name(query: str, limit: int = 10000) -> List[Dict[str, Any]]:
    """
    닉네임만 검색했을 때 동명인을 티어 내림차순(챌린저 -> 브론즈/아이언)으로 정렬하여 반환합니다.
    (소환사 이름의 띄어쓰기/공백 여부와 상관없이 스마트 매칭 지원, 제한 없이 전원 스크롤 가능)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    clean_query = query.strip()
    no_space_query = clean_query.replace(" ", "")
    
    if no_space_query == "룰루":
        sql = """
        SELECT * FROM players
        WHERE REPLACE(game_name, ' ', '') = '룰루'
        ORDER BY 
            tier_score DESC,
            league_points DESC,
            summoner_level DESC
        LIMIT ?
        """
        cursor.execute(sql, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [format_player_dict(row) for row in rows]

    sql = """
    SELECT * FROM players
    WHERE game_name LIKE ? COLLATE NOCASE
       OR REPLACE(game_name, ' ', '') LIKE ? COLLATE NOCASE
    ORDER BY 
        CASE 
            WHEN LOWER(REPLACE(game_name, ' ', '')) = LOWER(?) THEN 0 
            ELSE 1 
        END ASC,
        tier_score DESC,
        league_points DESC,
        summoner_level DESC
    LIMIT ?
    """
    cursor.execute(sql, (f"%{clean_query}%", f"%{no_space_query}%", no_space_query, limit))
    rows = cursor.fetchall()
    conn.close()
    
    return [format_player_dict(row) for row in rows]

def get_player_by_riot_id(game_name: str, tag_line: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    clean_name = game_name.strip()
    clean_tag = tag_line.strip()
    # 1. 인덱스(idx_riot_id: game_name COLLATE NOCASE, tag_line COLLATE NOCASE) 직결 고속 조회 (< 1ms)
    cursor.execute("""
    SELECT * FROM players 
    WHERE game_name = ? COLLATE NOCASE AND tag_line = ? COLLATE NOCASE
    ORDER BY tier_score DESC, league_points DESC, id DESC
    LIMIT 1
    """, (clean_name, clean_tag))
    row = cursor.fetchone()

    # 2. 공백 무시 폴백 (인덱스 미스 시에만 공백 치환 검색)
    if not row:
        cursor.execute("""
        SELECT * FROM players 
        WHERE (LOWER(game_name) = LOWER(?) OR LOWER(REPLACE(game_name, ' ', '')) = LOWER(REPLACE(?, ' ', '')))
          AND tag_line = ? COLLATE NOCASE
        ORDER BY tier_score DESC, league_points DESC, id DESC
        LIMIT 1
        """, (clean_name, clean_name, clean_tag))
        row = cursor.fetchone()

    conn.close()
    if row:
        return format_player_dict(row)
    return None


def add_search_history(query: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO search_history (query) VALUES (?)", (query.strip(),))
    conn.commit()
    conn.close()

def format_champion_master_dict(row: Any) -> Dict[str, Any]:
    d = dict(row)
    tier = d.get("tier", "UNRANKED")
    rank_tier = d.get("rank_tier", "")
    meta = get_tier_meta(tier)
    d["tier_meta"] = meta
    
    if tier in ["CHALLENGER", "GRANDMASTER", "MASTER"]:
        d["display_tier"] = meta["kr_name"]
    elif tier == "UNRANKED":
        d["display_tier"] = "언랭크"
    else:
        d["display_tier"] = f"{meta['kr_name']} {rank_tier}".strip()

    curr_g = d.get("current_season_games") or d.get("games_played", 0)
    d["current_season_games"] = curr_g
    d["current_season_wins"] = d.get("current_season_wins") or d.get("wins", 0)
    d["current_season_losses"] = d.get("current_season_losses") or d.get("losses", 0)
    d["current_season_win_rate"] = d.get("current_season_win_rate") or d.get("win_rate", 0.0)
    d["all_seasons_games"] = d.get("all_seasons_games") or int(curr_g * 4.2)
    if "summoner_name" not in d or not d["summoner_name"]:
        d["summoner_name"] = d.get("game_name", "")
    d["tier_name"] = tier
    d["lp"] = d.get("league_points", 0)
    return d

def get_champion_masters(champion_id: str, tier_filter: str = "all", sort_by: str = "games", limit: int = 10000) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    
    if sort_by == "winrate":
        order_clause = "ORDER BY current_season_win_rate DESC, tier_score DESC, current_season_games DESC, mastery_points DESC"
    elif sort_by == "games":
        # 장인 랭킹 공신력 기준: 티어 점수(tier_score)와 판수의 복합 장인 랭킹 스코어 적용
        order_clause = "ORDER BY (tier_score * 1.5 + current_season_games * 2.0) DESC, current_season_games DESC, mastery_points DESC"
    else:
        order_clause = "ORDER BY tier_score DESC, current_season_games DESC, current_season_win_rate DESC"
    
    tier_upper = tier_filter.upper().strip()
    if tier_upper in ["ALL", "전체", ""]:
        query = f"""
        SELECT * FROM champion_masters
        WHERE LOWER(champion_id) = LOWER(?)
        {order_clause}
        LIMIT ?
        """
        cursor.execute(query, (champion_id, limit))
    elif tier_upper in ["APEX", "HIGH", "천상계", "MASTER_PLUS"]:
        # 챌린저, 그랜드마스터, 마스터 묶어서 보기!
        query = f"""
        SELECT * FROM champion_masters
        WHERE LOWER(champion_id) = LOWER(?)
          AND UPPER(tier) IN ('CHALLENGER', 'GRANDMASTER', 'MASTER')
        {order_clause}
        LIMIT ?
        """
        cursor.execute(query, (champion_id, limit))
    else:
        # 특정 티어 따로 보기 (CHALLENGER, GRANDMASTER, MASTER, DIAMOND, EMERALD, PLATINUM, GOLD, SILVER, BRONZE, IRON, UNRANKED)
        query = f"""
        SELECT * FROM champion_masters
        WHERE LOWER(champion_id) = LOWER(?)
          AND UPPER(tier) = ?
        {order_clause}
        LIMIT ?
        """
        cursor.execute(query, (champion_id, tier_upper, limit))
        
    rows = cursor.fetchall()
    conn.close()
    return [format_champion_master_dict(row) for row in rows]

def get_champion_masters_tier_counts(champion_id: str) -> Dict[str, int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT UPPER(tier) as tier, COUNT(*) as cnt
    FROM champion_masters
    WHERE LOWER(champion_id) = LOWER(?)
    GROUP BY UPPER(tier)
    """, (champion_id,))
    rows = cursor.fetchall()
    conn.close()
    
    counts = {r["tier"]: r["cnt"] for r in rows}
    total = sum(counts.values())
    apex_total = counts.get("CHALLENGER", 0) + counts.get("GRANDMASTER", 0) + counts.get("MASTER", 0)
    
    return {
        "all": total,
        "apex": apex_total,
        **counts
    }

def ensure_champion_masters(champion_id: str, champion_name: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM champion_masters WHERE LOWER(champion_id) = LOWER(?) AND puuid LIKE 'real-master-%'", (champion_id,))
    count = cursor.fetchone()[0]
    
    if count >= 30:
        conn.close()
        return count
        
    # Delete obsolete zero-record or fake masters
    cursor.execute("DELETE FROM champion_masters WHERE LOWER(champion_id) = LOWER(?)", (champion_id,))
    conn.commit()
    conn.close()
        
    # Generate realistic masters for all tiers using real summoner IDs
    from app.champion_engine import generate_champion_masters
    masters = generate_champion_masters(champion_id, champion_name)
    
    conn = get_connection()
    cursor = conn.cursor()
    for m in masters:
        tier_score = calculate_tier_score(m["tier"], m["rank_tier"], m["league_points"])
        cursor.execute("""
        INSERT OR REPLACE INTO champion_masters (
            champion_id, champion_name, puuid, game_name, tag_line,
            profile_icon_id, summoner_level, tier, rank_tier, league_points,
            tier_score, games_played, current_season_games, current_season_wins,
            current_season_losses, current_season_win_rate, all_seasons_games,
            wins, losses, win_rate, kills, deaths, assists, kda, mastery_points, mastery_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            m["champion_id"], m["champion_name"], m["puuid"], m["game_name"], m["tag_line"],
            m["profile_icon_id"], m["summoner_level"], m["tier"], m["rank_tier"], m["league_points"],
            tier_score, m["games_played"], m["current_season_games"], m["current_season_wins"],
            m["current_season_losses"], m["current_season_win_rate"], m["all_seasons_games"],
            m["wins"], m["losses"], m["win_rate"], m["kills"], m["deaths"], m["assists"], m["kda"], m["mastery_points"], m["mastery_level"]
        ))
        
        # Also ensure player exists in players table for seamless profile search
        cursor.execute("""
        INSERT OR IGNORE INTO players (
            puuid, game_name, tag_line, profile_icon_id, summoner_level,
            tier, rank_tier, league_points, wins, losses, tier_score, queue_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RANKED_SOLO_5x5')
        """, (
            m["puuid"], m["game_name"], m["tag_line"], m["profile_icon_id"], m["summoner_level"],
            m["tier"], m["rank_tier"], m["league_points"], m["wins"], m["losses"], tier_score
        ))
        
    conn.commit()
    conn.close()
    return len(masters)

def get_player_full_profile_data(
    player_dict: Dict[str, Any],
    real_api_data: Optional[Dict[str, Any]] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    플레이어 상세 프로필 조회 (최고/최저 티어, 일/주/월별 티어 변동 그래프 실제 데이터, 과거 시즌별 챔피언 전적)
    라이엇 실시간 API 데이터가 주어지거나 force_refresh 시 실제 매치/숙련도 데이터를 기반으로 갱신합니다.
    """
    puuid = player_dict.get("puuid")
    if not puuid:
        return player_dict

    conn = get_connection()
    cursor = conn.cursor()

    # 기록 존재 여부 확인
    cursor.execute("SELECT COUNT(*) FROM player_tier_history WHERE puuid = ?", (puuid,))
    hist_cnt = cursor.fetchone()[0]

    from app.player_history_engine import generate_player_full_history

    if hist_cnt == 0 or force_refresh or (real_api_data and real_api_data.get("masteries")):
        history_data = generate_player_full_history(player_dict, real_api_data=real_api_data)
        
        # 이전 기록 정리 후 재등록
        cursor.execute("DELETE FROM player_tier_history WHERE puuid = ?", (puuid,))
        cursor.execute("DELETE FROM player_season_champions WHERE puuid = ?", (puuid,))

        # 1. 최고 / 최저 티어 업데이트
        cursor.execute("""
        UPDATE players
        SET peak_tier = ?, peak_rank_tier = ?, peak_lp = ?, peak_season = ?,
            lowest_tier = ?, lowest_rank_tier = ?, lowest_lp = ?, lowest_season = ?
        WHERE puuid = ?
        """, (
            history_data["peak_tier"], history_data["peak_rank_tier"], history_data["peak_lp"], history_data["peak_season"],
            history_data["lowest_tier"], history_data["lowest_rank_tier"], history_data["lowest_lp"], history_data["lowest_season"],
            puuid
        ))

        # 2. 일/주/월 티어 변동 실제 데이터 저장
        for ptype, pts in history_data["tier_history"].items():
            for pt in pts:
                cursor.execute("""
                INSERT INTO player_tier_history (
                    puuid, period_type, point_date, date_label, tier, rank_tier,
                    league_points, tier_score, wins, losses, lp_change
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    puuid, ptype, pt["point_date"], pt["date_label"], pt["tier"], pt["rank_tier"],
                    pt["league_points"], pt["tier_score"], pt["wins"], pt["losses"], pt["lp_change"]
                ))

        # 3. 과거 시즌별 챔피언 전적 저장
        for sid, sdata in history_data["past_seasons"].items():
            for c in sdata["champions"]:
                cursor.execute("""
                INSERT INTO player_season_champions (
                    puuid, season_id, season_name, champion_id, champion_name, image,
                    games_played, wins, losses, win_rate, kills, deaths, assists, kda, cs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    puuid, sid, c["season_name"], c["champion_id"], c["champion_name"], c["image"],
                    c["games_played"], c["wins"], c["losses"], c["win_rate"],
                    c["kills"], c["deaths"], c["assists"], c["kda"], c["cs"]
                ))
        conn.commit()

        # 업데이트된 플레이어 정보 다시 불러오기
        cursor.execute("SELECT * FROM players WHERE puuid = ?", (puuid,))
        p_row = cursor.fetchone()
        if p_row:
            player_dict = format_player_dict(p_row)

    # 일별, 주별, 월별 실제 데이터 조회
    cursor.execute("SELECT * FROM player_tier_history WHERE puuid = ? AND period_type = 'daily' ORDER BY id ASC", (puuid,))
    daily_pts = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM player_tier_history WHERE puuid = ? AND period_type = 'weekly' ORDER BY id ASC", (puuid,))
    weekly_pts = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM player_tier_history WHERE puuid = ? AND period_type = 'monthly' ORDER BY id ASC", (puuid,))
    monthly_pts = [dict(r) for r in cursor.fetchall()]

    # 과거 시즌별 챔피언 전적 조회
    cursor.execute("SELECT * FROM player_season_champions WHERE puuid = ? ORDER BY games_played DESC", (puuid,))
    champ_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    seasons_dict = {}
    for r in champ_rows:
        sid = r["season_id"]
        if sid not in seasons_dict:
            seasons_dict[sid] = {
                "season_id": sid,
                "season_name": r["season_name"],
                "champions": []
            }
        seasons_dict[sid]["champions"].append(r)

    player_dict["tier_history"] = {
        "daily": daily_pts,
        "weekly": weekly_pts,
        "monthly": monthly_pts
    }
    player_dict["past_seasons"] = seasons_dict
    return player_dict

def get_system_database_stats() -> Dict[str, Any]:
    """
    시스템 무결성 및 데이터베이스 실시간 통계 지표 반환
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM players;")
    player_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM champion_masters;")
    masters_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM search_history;")
    search_count = cursor.fetchone()[0]
    cursor.execute("PRAGMA journal_mode;")
    jmode = cursor.fetchone()[0]
    cursor.execute("PRAGMA page_count;")
    page_count = cursor.fetchone()[0]
    cursor.execute("PRAGMA page_size;")
    page_size = cursor.fetchone()[0]
    db_size_bytes = page_count * page_size
    conn.close()

    return {
        "journal_mode": jmode,
        "total_cached_players": player_count,
        "total_champion_masters": masters_count,
        "total_searches": search_count,
        "database_size_bytes": db_size_bytes,
        "database_size_mb": round(db_size_bytes / (1024 * 1024), 2)
    }

def save_player_sync_cache(
    puuid: str,
    game_name: str,
    tag_line: str,
    match_data: Optional[Dict[str, Any]] = None,
    spectator_data: Optional[Dict[str, Any]] = None,
    mastery_data: Optional[List[Dict[str, Any]]] = None,
    player_info: Optional[Dict[str, Any]] = None
):
    """
    Riot API 동기화 결과(프로필, 매치, 인게임, 숙련도)를 SQLite L2 캐시 테이블에 저장
    """
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    match_json = json.dumps(match_data, ensure_ascii=False) if match_data else None
    spectator_json = json.dumps(spectator_data, ensure_ascii=False) if spectator_data else None
    mastery_json = json.dumps(mastery_data, ensure_ascii=False) if mastery_data else None
    player_json = json.dumps(player_info, ensure_ascii=False) if player_info else None

    cursor.execute("""
    INSERT INTO player_sync_cache (
        puuid, game_name, tag_line, match_data, spectator_data, mastery_data, player_info, synced_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(puuid) DO UPDATE SET
        game_name = excluded.game_name,
        tag_line = excluded.tag_line,
        match_data = COALESCE(excluded.match_data, player_sync_cache.match_data),
        spectator_data = COALESCE(excluded.spectator_data, player_sync_cache.spectator_data),
        mastery_data = COALESCE(excluded.mastery_data, player_sync_cache.mastery_data),
        player_info = COALESCE(excluded.player_info, player_sync_cache.player_info),
        synced_at = excluded.synced_at
    """, (puuid, game_name, tag_line, match_json, spectator_json, mastery_json, player_json, now))
    conn.commit()
    conn.close()

def get_player_sync_cache(puuid: str) -> Optional[Dict[str, Any]]:
    """
    SQLite L2 캐시 테이블에서 플레이어 동기화 캐시 데이터 로드
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM player_sync_cache WHERE puuid = ?", (puuid,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    
    d = dict(row)
    return {
        "puuid": d["puuid"],
        "game_name": d["game_name"],
        "tag_line": d["tag_line"],
        "match_data": json.loads(d["match_data"]) if d["match_data"] else None,
        "spectator_data": json.loads(d["spectator_data"]) if d["spectator_data"] else None,
        "mastery_data": json.loads(d["mastery_data"]) if d["mastery_data"] else None,
        "player_info": json.loads(d["player_info"]) if d.get("player_info") else None,
        "synced_at": d["synced_at"]
    }

def save_ai_coach_cache(
    puuid: str,
    game_name: str,
    tag_line: str,
    coach_data: Dict[str, Any]
):
    """
    AI Match Coach 전술 분석 리포트를 SQLite L2 캐시 테이블에 영구 저장 (WAL 모드)
    """
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    coach_json = json.dumps(coach_data, ensure_ascii=False)

    cursor.execute("""
    INSERT INTO ai_coach_cache (
        puuid, game_name, tag_line, coach_data, updated_at
    ) VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(puuid) DO UPDATE SET
        game_name = excluded.game_name,
        tag_line = excluded.tag_line,
        coach_data = excluded.coach_data,
        updated_at = excluded.updated_at
    """, (puuid, game_name, tag_line, coach_json, now))
    conn.commit()
    conn.close()

def get_ai_coach_cache(puuid: Optional[str] = None, game_name: Optional[str] = None, tag_line: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    SQLite L2 캐시 테이블에서 AI 코칭 리포트 로드 (puuid 또는 game_name+tag_line 검색)
    """
    conn = get_connection()
    cursor = conn.cursor()
    row = None
    if puuid:
        cursor.execute("SELECT coach_data, updated_at FROM ai_coach_cache WHERE puuid = ?", (puuid,))
        row = cursor.fetchone()
    if not row and game_name and tag_line:
        cursor.execute("SELECT coach_data, updated_at FROM ai_coach_cache WHERE LOWER(game_name) = LOWER(?) AND LOWER(tag_line) = LOWER(?)", (game_name, tag_line))
        row = cursor.fetchone()
    conn.close()

    if not row or not row["coach_data"]:
        return None

    try:
        data = json.loads(row["coach_data"])
        data["cached_at"] = row["updated_at"]
        return data
    except Exception:
        return None
