"""
방문자 통계 (app/traffic.py)

페이지(HTML) 요청만 센다. 개인정보를 남기지 않도록 IP는 저장하지 않고,
'날짜별로 바뀌는 비밀 값 + IP + 브라우저 정보'의 해시만 그날의 순 방문자 수를 세는 데 쓴다
(다음 날이면 같은 사람도 다른 해시가 되어 날짜를 넘어 추적할 수 없다).
"""
import hashlib
import secrets
import time
from typing import Any, Dict, List

from app.database import get_connection

_DAY_SALT: Dict[str, str] = {}
KEEP_DAYS = 90
_initialized = set()


def _ensure_tables() -> None:
    from app import database
    key = str(database.DB_PATH)
    if key in _initialized:
        return
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traffic_daily (
                day TEXT NOT NULL,
                page TEXT NOT NULL,
                views INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, page)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traffic_visitors (
                day TEXT NOT NULL,
                visitor TEXT NOT NULL,
                PRIMARY KEY (day, visitor)
            )
        """)
        conn.commit()
    finally:
        conn.close()
    _initialized.add(key)


def page_kind(path: str) -> str:
    if path.startswith("/champion/"):
        return "champion"
    if path.startswith("/summoner/"):
        return "summoner"
    return "home"


def record_page_view(path: str, ip: str, user_agent: str) -> None:
    _ensure_tables()
    day = time.strftime("%Y-%m-%d")
    salt = _DAY_SALT.get(day)
    if salt is None:
        _DAY_SALT.clear()  # 지난 날짜 비밀 값은 버린다
        salt = _DAY_SALT[day] = secrets.token_hex(16)
    visitor = hashlib.sha256(f"{salt}|{ip}|{user_agent}".encode("utf-8")).hexdigest()[:24]
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO traffic_daily (day, page, views) VALUES (?, ?, 1) "
            "ON CONFLICT(day, page) DO UPDATE SET views = views + 1",
            (day, page_kind(path)),
        )
        conn.execute("INSERT OR IGNORE INTO traffic_visitors (day, visitor) VALUES (?, ?)", (day, visitor))
        conn.commit()
    finally:
        conn.close()


def traffic_summary(days: int = 14) -> Dict[str, Any]:
    _ensure_tables()
    conn = get_connection()
    try:
        cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - KEEP_DAYS * 86400))
        conn.execute("DELETE FROM traffic_visitors WHERE day < ?", (cutoff,))
        conn.commit()
        rows = conn.execute("SELECT day, page, views FROM traffic_daily ORDER BY day DESC").fetchall()
        uniques = dict(conn.execute("SELECT day, COUNT(*) FROM traffic_visitors GROUP BY day").fetchall())
    finally:
        conn.close()
    by_day: Dict[str, Dict[str, Any]] = {}
    for day, page, views in rows:
        d = by_day.setdefault(day, {"day": day, "views": 0, "home": 0, "champion": 0, "summoner": 0})
        d["views"] += views
        d[page] = d.get(page, 0) + views
    out: List[Dict[str, Any]] = []
    for day in sorted(by_day, reverse=True)[:days]:
        out.append({**by_day[day], "visitors": uniques.get(day, 0)})
    return {"days": out}
