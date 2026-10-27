import sqlite3

def check_db():
    conn = sqlite3.connect('opgg.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    print("Tables in opgg.db:", tables)

    for t in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cursor.fetchone()[0]
        print(f"Table: {t} | Rows: {cnt}")

    # Check summoners/players table schema and samples
    for t in tables:
        cursor.execute(f"PRAGMA table_info({t});")
        cols = [c[1] for c in cursor.fetchall()]
        print(f"\nSchema for {t}: {cols}")
        cursor.execute(f"SELECT * FROM {t} LIMIT 5")
        samples = cursor.fetchall()
        for s in samples:
            print("  Sample:", s)

if __name__ == "__main__":
    check_db()
