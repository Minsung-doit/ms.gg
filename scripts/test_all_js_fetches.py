import urllib.request
import urllib.parse
import json
import sys

import os
from pathlib import Path

# Load Riot API key dynamically from environment or .env without hardcoding secret
_env_key = os.getenv("RIOT_API_KEY")
if not _env_key:
    _env_file = Path(__file__).resolve().parent.parent / ".env"
    if _env_file.exists():
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            if _line.startswith("RIOT_API_KEY="):
                _env_key = _line.split("=", 1)[1].strip("'\" \n")
                break
test_api_key = _env_key or "RGAPI-00000000-0000-0000-0000-000000000000"

test_calls = [
    ("POST", "/api/settings/api-key", {"api_key": test_api_key}),
    ("GET", "/api/search?q=Hide%20on%20bush", None),
    ("GET", "/api/search?q=Hide%20on%20bush%23KR1", None),
    ("GET", "/api/player/Hide%20on%20bush/KR1", None),
    ("GET", "/api/player/Hide%20on%20bush/KR1/matches?count=20", None),
    ("GET", "/api/player/Hide%20on%20bush/KR1/ai-coach", None),
    ("GET", "/api/settings/status", None),
    ("GET", "/api/key-status", None),
    ("GET", "/api/sync/status", None),
    ("GET", "/api/autocomplete", None),
    ("GET", f"/api/autocomplete?q={urllib.parse.quote('가렌')}", None),
    ("GET", "/api/settings/discord-status", None),
    ("GET", "/api/settings/telegram-status", None),
    ("GET", "/api/finance/summary", None),
    ("GET", "/api/leaderboard?tier=ALL", None),
    ("GET", "/api/leaderboard?tier=CHALLENGER", None),
    ("GET", "/api/pro-tracker", None),
    ("GET", "/api/champions", None),
    ("GET", "/api/champion-masters?champ=Yasuo&tier=all&sort=games", None),
    ("GET", "/api/champion-build/Yasuo", None),
    ("GET", "/api/aram/tierlist", None),
    ("GET", "/api/champion-analytics?position=MID&tier=emerald_plus", None),
    ("GET", "/api/tier-distribution/stats", None),
    ("GET", "/api/champion-skills/Yasuo", None),
    ("GET", "/api/spectator/featured", None),
    ("GET", "/api/duo-bot-matchups", None),
    ("GET", "/api/duo-posts", None),
    ("GET", "/api/patch-notes", None),
    ("GET", "/api/quick-op-champions", None),
    ("GET", "/api/patch-shift-champions", None),
    ("GET", "/api/champion-analytics-full/Yasuo?tier=emerald_plus", None),
    ("GET", "/api/cache/stats", None),
    ("GET", "/api/system/metrics", None),
    # Post calls
    ("POST", "/api/multi-search", {"summoner_names": ["Hide on bush", "Faker", "Chovy", "ShowMaker", "Gumayusi"]}),
    ("POST", "/api/discord/share/multisearch", {"summoners": [{"name": "Hide on bush", "tier": "CHALLENGER", "win_rate": 60.0, "kda": "3.5:1", "badges": ["연승중"]}]}),
    ("POST", "/api/discord/share/player", {"player": {"game_name": "Hide on bush", "tag_line": "KR1", "tier": "CHALLENGER", "lp": 1200, "wins": 200, "losses": 100, "win_rate": 66.7, "kda_ratio": "4.2:1"}}),
]

failures = []
successes = []

for method, path, body in test_calls:
    url = f"http://localhost:3000{path}"
    try:
        data = json.dumps(body).encode("utf-8") if body else None
        headers = {"Content-Type": "application/json"} if body else {}
        headers["User-Agent"] = "AuditBot/1.0"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            content = resp.read()
            successes.append((method, path, resp.status, len(content)))
            print(f"[PASS] {resp.status} {method} {path} (len: {len(content)})", flush=True)
    except urllib.error.HTTPError as he:
        failures.append((method, path, he.code, he.reason))
        print(f"[FAIL] {he.code} {method} {path} -> {he.reason}", flush=True)
    except Exception as e:
        failures.append((method, path, 0, str(e)))
        print(f"[ERR] {method} {path} -> {e}", flush=True)

print("=" * 60, flush=True)
print(f"Summary: {len(successes)} Successes, {len(failures)} Failures", flush=True)
if failures:
    print("FAILED ENDPOINTS:", flush=True)
    for f in failures:
        print("  -", f, flush=True)
