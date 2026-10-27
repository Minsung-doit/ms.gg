"""분리된 프런트엔드 파일(static/js/app/*.js, static/css/app/*.css)을 로드 순서대로 이어 붙여 읽는 도우미."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def read_frontend_js() -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in sorted((BASE_DIR / "static" / "js" / "app").glob("*.js")))


def read_frontend_css() -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in sorted((BASE_DIR / "static" / "css" / "app").glob("*.css")))
