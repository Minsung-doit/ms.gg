# -*- coding: utf-8 -*-
import httpx
import urllib.parse

test_names = ["민재는 아가야", "홍길동", "고양이", "꿀꿀"]

for name in test_names:
    q = urllib.parse.quote(name)
    r = httpx.get(f"http://127.0.0.1:3000/api/search?q={q}", timeout=15.0)
    data = r.json()
    count = data.get("count", 0)
    results = data.get("results", [])
    print("=" * 60)
    print(f"[{name}] 검색 결과: 총 {count}명의 동명인")
    print("=" * 60)
    for i, p in enumerate(results[:5]):
        print(f"#{i+1:2d} {p['game_name']} #{p['tag_line']} | {p['display_tier']} ({p['league_points']} LP) | Lv.{p['summoner_level']}")
    if len(results) > 5:
        print("  ... (중략) ...")
        last = results[-1]
        print(f"#{len(results):2d} {last['game_name']} #{last['tag_line']} | {last['display_tier']} | Lv.{last['summoner_level']}")
    print()
