#!/usr/bin/env python3
"""
opgg.db 에서 코드가 생성한(라이엇 실제 데이터가 아닌) 행을 삭제한다. 실행 전 DB 전체를 백업한다.

남기는 것: 라이엇 형식 PUUID를 가진 소환사의 라이엇 제공 필드(티어·LP·승패·레벨·아이콘), 검색 기록, 매치 캐시
지우는 것: 생성 소환사, 장인 랭킹, 티어 변동 기록, 과거 시즌 전적, 동기화/AI코치 캐시, 옛 래더 캐시, 시드 공략 팁

사용법: 서버를 끈 뒤  python scripts/purge_synthetic_data.py
"""
import shutil
import sqlite3
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from app.database import DB_PATH  # noqa: E402  (OPGG_DB_PATH 반영)
RIOT_PUUID_SQL = "(length(puuid) = 78 AND puuid NOT LIKE 'real-%' AND puuid NOT LIKE 'lulu-%' AND puuid NOT LIKE 'dyn-%')"


def main() -> int:
    if not DB_PATH.exists():
        print("opgg.db 가 없습니다.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    backup = DB_PATH.with_name(f"opgg_backup_{time.strftime('%Y%m%d_%H%M%S')}.db")
    shutil.copy2(DB_PATH, backup)
    print(f"백업: {backup}")

    conn = sqlite3.connect(DB_PATH)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    report = {}

    def run(label: str, sql: str):
        if sql.split()[2] not in tables and not sql.startswith("UPDATE"):
            return
        report[label] = conn.execute(sql).rowcount

    run("생성 소환사", f"DELETE FROM players WHERE NOT {RIOT_PUUID_SQL}")
    for table in ("champion_masters", "player_tier_history", "player_season_champions",
                  "player_sync_cache", "ai_coach_cache", "ladder_cache", "community_counter_tips"):
        run(table, f"DELETE FROM {table}")
    if "players" in tables:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
        peak_cols = [c for c in ("peak_tier", "peak_rank_tier", "peak_lp", "peak_season",
                                 "lowest_tier", "lowest_rank_tier", "lowest_lp", "lowest_season") if c in cols]
        if peak_cols:
            report["최고/최저 티어 초기화"] = conn.execute(
                f"UPDATE players SET {', '.join(f'{c} = NULL' for c in peak_cols)}"
            ).rowcount
    conn.commit()
    conn.execute("VACUUM")
    remaining = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    conn.close()

    for label, count in report.items():
        print(f"  {label}: {count}행")
    print(f"남은 소환사: {remaining}명 (모두 라이엇 형식 PUUID)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
