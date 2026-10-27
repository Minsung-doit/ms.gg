# -*- coding: utf-8 -*-
import httpx

# UTF-8 URL encoded '꿀꿀' is %EA%BF%80%EA%BF%80
url = "http://127.0.0.1:3000/api/search?q=%EA%BF%80%EA%BF%80"
r = httpx.get(url, timeout=15.0)
print("Status:", r.status_code)
data = r.json()
print("Query:", data.get("query"))
print("Count:", data.get("count"))
for i, p in enumerate(data.get("results", [])):
    print(f"#{i+1} {p['game_name']}#{p['tag_line']} | {p['display_tier']} ({p['league_points']} LP) | {p['win_rate']}%")
