import sqlite3

conn = sqlite3.connect('opgg.db')
c = conn.cursor()
indices = c.execute("SELECT tbl_name, name, sql FROM sqlite_master WHERE type='index'").fetchall()
print(f"Total indices: {len(indices)}")
for tbl, name, sql in indices:
    print(f"{tbl:25s} | {name:35s} | {sql}")
conn.close()
