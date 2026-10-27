import sqlite3
from pathlib import Path

db_path = Path("opgg.db")
try:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")
    conn.execute("PRAGMA optimize")
    conn.close()
    print("SUCCESS: WAL checkpoint, VACUUM, and PRAGMA optimize succeeded.")
except Exception as e:
    print(f"FAILED: {e}")
