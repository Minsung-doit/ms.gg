import sqlite3

conn = sqlite3.connect('opgg.db')
c = conn.cursor()

c.execute("SELECT id, game_name, tag_line, tier, league_points FROM players WHERE game_name LIKE '%홍길동%' OR game_name = 'Faker'")
rows = c.fetchall()
print(f"Players with 홍길동 or Faker ({len(rows)}):")
for r in rows:
    print(r)

c.execute("SELECT id, champ_a_name, champ_b_name, author_name, tip_text FROM community_counter_tips WHERE author_name LIKE '%테스트%' OR author_name = 'Faker'")
tips = c.fetchall()
print(f"\nTips with 테스트 or Faker ({len(tips)}):")
for t in tips:
    print(t)
