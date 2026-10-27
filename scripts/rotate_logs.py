"""
OP.GG 서버 로그 로테이션 유틸리티
- server.log가 10MB를 초과하면 server_YYYY-MM-DD_HHMMSS.log로 아카이브
- 7일 이상 된 오래된 로그 파일 자동 삭제
- 단독 실행: python scripts/rotate_logs.py
- run.py 부팅 시 자동 호출 가능
"""

import os
import sys
import time
import shutil
from pathlib import Path
from datetime import datetime, timedelta

# Windows 콘솔 인코딩 방어
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "server.log"
LOG_DIR = BASE_DIR / "logs"          # 아카이브 저장 폴더
MAX_LOG_SIZE_MB = 10                 # 10MB 초과 시 로테이션
KEEP_DAYS = 7                        # 7일 이상 된 로그 자동 삭제


def rotate_if_needed() -> bool:
    """
    server.log가 MAX_LOG_SIZE_MB(10MB) 초과 시 날짜별 아카이브로 이동.
    Returns True if rotation occurred, False otherwise.
    """
    if not LOG_FILE.exists():
        print(f"[INFO] {LOG_FILE.name} 없음 — 로테이션 불필요")
        return False

    size_mb = LOG_FILE.stat().st_size / (1024 * 1024)
    if size_mb < MAX_LOG_SIZE_MB:
        print(f"[INFO] 현재 로그 크기: {size_mb:.2f}MB (기준 {MAX_LOG_SIZE_MB}MB) — 로테이션 불필요")
        return False

    # 아카이브 폴더 생성
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 아카이브 파일명: server_2026-10-18_090000.log
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    archive_path = LOG_DIR / f"server_{timestamp}.log"

    shutil.move(str(LOG_FILE), str(archive_path))
    print(f"[OK] 로그 로테이션 완료: {LOG_FILE.name} ({size_mb:.2f}MB) → {archive_path.name}")

    # 새 server.log 생성 (빈 파일)
    LOG_FILE.touch()
    print(f"[OK] 새 {LOG_FILE.name} 생성 완료")
    return True


def cleanup_old_logs():
    """logs/ 폴더에서 KEEP_DAYS(7일) 이상 된 아카이브 로그 자동 삭제"""
    if not LOG_DIR.exists():
        return

    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    deleted_count = 0
    deleted_mb = 0.0

    for log_file in LOG_DIR.glob("server_*.log"):
        try:
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            if mtime < cutoff:
                size_mb = log_file.stat().st_size / (1024 * 1024)
                log_file.unlink()
                deleted_count += 1
                deleted_mb += size_mb
                print(f"[CLEAN] 오래된 로그 삭제: {log_file.name} ({size_mb:.2f}MB, {mtime.strftime('%Y-%m-%d')})")
        except Exception as e:
            print(f"[WARN] {log_file.name} 삭제 실패: {e}")

    if deleted_count:
        print(f"[OK] 총 {deleted_count}개 로그 파일 삭제 완료 ({deleted_mb:.2f}MB 확보)")
    else:
        print(f"[INFO] {KEEP_DAYS}일 이내 로그만 존재 — 삭제 없음")


def show_log_status():
    """현재 로그 상태 요약 출력"""
    print("=" * 60)
    print("[LOG STATUS] OP.GG 서버 로그 현황")
    print("=" * 60)

    # 현재 server.log
    if LOG_FILE.exists():
        size_mb = LOG_FILE.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(LOG_FILE.stat().st_mtime)
        print(f"  현재 로그: {LOG_FILE.name}")
        print(f"  크기: {size_mb:.2f}MB / {MAX_LOG_SIZE_MB}MB (로테이션 기준)")
        print(f"  마지막 수정: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"  현재 로그: 없음")

    # 아카이브 로그 목록
    if LOG_DIR.exists():
        archives = sorted(LOG_DIR.glob("server_*.log"), reverse=True)
        total_mb = sum(f.stat().st_size for f in archives) / (1024 * 1024)
        print(f"\n  아카이브 로그: {len(archives)}개 ({total_mb:.2f}MB 합계)")
        for f in archives[:5]:
            f_mb = f.stat().st_size / (1024 * 1024)
            f_mtime = datetime.fromtimestamp(f.stat().st_mtime)
            print(f"    - {f.name} ({f_mb:.2f}MB, {f_mtime.strftime('%Y-%m-%d')})")
        if len(archives) > 5:
            print(f"    ... 외 {len(archives) - 5}개")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OP.GG 서버 로그 로테이션 유틸리티")
    parser.add_argument("--status", action="store_true", help="현재 로그 상태 출력")
    parser.add_argument("--rotate", action="store_true", help="즉시 로테이션 강제 실행")
    parser.add_argument("--cleanup", action="store_true", help="7일 이상 오래된 로그 삭제")
    parser.add_argument("--all", action="store_true", help="로테이션 + 정리 + 상태 출력 (기본 동작)")
    args = parser.parse_args()

    if args.status:
        show_log_status()
    elif args.rotate:
        rotate_if_needed()
    elif args.cleanup:
        cleanup_old_logs()
    else:
        # 기본 동작: 필요 시 로테이션 + 오래된 로그 정리
        print("=" * 60)
        print("[LOG ROTATION] OP.GG 서버 로그 로테이션 시작")
        print("=" * 60)
        rotate_if_needed()
        print()
        cleanup_old_logs()
        print()
        show_log_status()
