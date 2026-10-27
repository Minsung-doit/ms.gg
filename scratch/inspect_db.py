import sqlite3

conn = sqlite3.connect('opgg.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print('Tables in opgg.db:')
for t in tables:
    cur.execute(f"SELECT count(*) FROM {t}")
    print(f"  - {t}: {cur.fetchone()[0]:,} rows")
conn.close()
