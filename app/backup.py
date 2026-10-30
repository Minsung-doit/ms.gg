"""
DB 자동 백업 (app/backup.py)

하루 한 번 SQLite 온라인 백업 API로 DB를 복사한다 (서버가 쓰는 중이어도 안전).
- 위치: OPGG_BACKUP_DIR, 없으면 DB 파일 옆 backups/ 폴더
- 파일명: opgg-YYYYMMDD.db, 최근 KEEP_BACKUPS 개만 남기고 오래된 것은 지운다
"""
import asyncio
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import List

from app import database

logger = logging.getLogger(__name__)

KEEP_BACKUPS = max(1, int(os.getenv("OPGG_BACKUP_KEEP", "7") or 7))  # 디스크가 작은 서버는 .env 로 줄인다
BACKUP_INTERVAL_SEC = 86400


def backup_dir() -> Path:
    custom = os.getenv("OPGG_BACKUP_DIR", "").strip()
    return Path(custom) if custom else Path(database.DB_PATH).parent / "backups"


def run_backup(keep: int = KEEP_BACKUPS) -> Path:
    """오늘 날짜 백업 파일을 만들고(이미 있으면 덮어씀) 오래된 백업을 정리한다."""
    target_dir = backup_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"opgg-{time.strftime('%Y%m%d')}.db"
    tmp = target.with_suffix(".db.tmp")
    src = sqlite3.connect(database.DB_PATH, timeout=30.0)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst, pages=4096)
    finally:
        dst.close()
        src.close()
    os.replace(tmp, target)  # 백업 도중 실패해도 이전 백업이 반쯤 쓴 파일로 바뀌지 않게
    for old in list_backups()[keep:]:
        old.unlink(missing_ok=True)
    logger.info("DB backup written: %s", target)
    return target


def list_backups() -> List[Path]:
    """최신순 백업 파일 목록"""
    d = backup_dir()
    return sorted(d.glob("opgg-*.db"), reverse=True) if d.exists() else []


async def backup_loop() -> None:
    """하루 한 번 백업 (오늘 백업이 이미 있으면 다음 날까지 기다린다). 백업은 스레드에서 돌려 서버를 막지 않는다."""
    while True:
        today = backup_dir() / f"opgg-{time.strftime('%Y%m%d')}.db"
        if not today.exists():
            try:
                await asyncio.to_thread(run_backup)
            except Exception as e:  # 백업 실패가 서버를 멈추면 안 된다
                logger.warning("DB backup failed: %s", e)
        await asyncio.sleep(BACKUP_INTERVAL_SEC)
