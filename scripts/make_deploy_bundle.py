"""서버에 올릴 묶음 만들기: deploy_bundle/carrygg.tar.gz (커밋된 코드만, .env 제외) + deploy_bundle/opgg.db (현재 DB 온라인 백업).

  python scripts/make_deploy_bundle.py
업로드 방법은 docs/DEPLOY.md 4번.
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "deploy_bundle"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        print("경고: 커밋되지 않은 변경은 묶음에 들어가지 않습니다:\n" + dirty)
    tar = OUT / "carrygg.tar.gz"
    subprocess.run(["git", "archive", "--format=tar.gz", "-o", str(tar), "HEAD"], cwd=ROOT, check=True)
    print("코드:", tar, f"{tar.stat().st_size / 1e6:.1f} MB")

    from app.database import DB_PATH  # .env 의 OPGG_DB_PATH 반영
    db_out = OUT / "opgg.db"
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(db_out)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print("DB:", db_out, f"{db_out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
