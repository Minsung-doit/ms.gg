import sqlite3

conn = sqlite3.connect('opgg.db')
c = conn.cursor()
c.execute('PRAGMA table_info(community_counter_tips)')
print('Columns:', [r[1] for r in c.fetchall()])
c.execute("SELECT * FROM community_counter_tips WHERE author_name LIKE '%테스트%'")
print('Flagged tips:', c.fetchall())
