import sqlite3
import json

def check_rankers():
    conn = sqlite3.connect('opgg.db')
    c = conn.cursor()
    print("--- Top 10 Rankers by tier_score / league_points ---")
    rankers = c.execute("""
        SELECT game_name, tag_line, tier, rank_tier, league_points, wins, losses, tier_score 
        FROM players 
        ORDER BY tier_score DESC 
        LIMIT 10
    """).fetchall()
    for r in rankers:
        print(f"  {r[0]}#{r[1]} | {r[2]} {r[3]} ({r[4]} LP) | {r[5]}W {r[6]}L | Score: {r[7]}")

    print("\n--- Specific Famous Players ---")
    famous = ['Hide on bush', 'Chovy', 'ShowMaker', 'Canyon', 'Zeus', 'Gumayusi', 'Keria', 'Viper', 'Ruler', 'Deft']
    for name in famous:
        p = c.execute("SELECT game_name, tag_line, tier, rank_tier, league_points, wins, losses FROM players WHERE game_name = ?", (name,)).fetchone()
        if p:
            print(f"  Found {p[0]}#{p[1]} | {p[2]} {p[3]} ({p[4]} LP) | {p[5]}W {p[6]}L")
        else:
            print(f"  NOT Found: {name}")

    print("\n--- Ladder Cache Sample ---")
    ladder = c.execute("SELECT rank, game_name, tag_line, tier, league_points, win_rate FROM ladder_cache ORDER BY rank ASC LIMIT 5").fetchall()
    for l in ladder:
        print(f"  Rank #{l[0]}: {l[1]}#{l[2]} | {l[3]} ({l[4]} LP) | WinRate: {l[5]}%")

    print("\n--- Player Sync Cache Check ---")
    sync_cnt = c.execute("SELECT count(*) FROM player_sync_cache").fetchone()[0]
    print(f"  Total synced in player_sync_cache: {sync_cnt}")
    sample_sync = c.execute("SELECT game_name, tag_line, synced_at, length(match_data) FROM player_sync_cache LIMIT 3").fetchall()
    for s in sample_sync:
        print(f"  Synced: {s[0]}#{s[1]} at {s[2]} (matches json size: {s[3]} bytes)")

    conn.close()

if __name__ == '__main__':
    check_rankers()
