import sqlite3

conn = sqlite3.connect('opgg.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [r[0] for r in cursor.fetchall()]

print("=== opgg.db Tables & Row Counts ===")
for t in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = cursor.fetchone()[0]
    print(f"- {t}: {cnt} rows")

print("\n=== Check Summoner Names in All Relevant Tables ===")
for t in tables:
    cursor.execute(f"PRAGMA table_info({t});")
    cols = [c[1] for c in cursor.fetchall()]
    name_cols = [c for c in cols if any(k in c.lower() for k in ['name', 'summoner', 'riot', 'player'])]
    if name_cols:
        print(f"Table '{t}' has name columns: {name_cols}")
        for col in name_cols:
            cursor.execute(f"SELECT DISTINCT {col} FROM {t} LIMIT 10")
            print(f"  Sample from {col}:", [r[0] for r in cursor.fetchall()])
