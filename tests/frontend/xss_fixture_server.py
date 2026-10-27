"""프런트 XSS 점검용 픽스처 서버 (네트워크 없음, 임시 DB)

라이엇 응답 형식의 픽스처에 HTML/JS 조각이 든 Riot ID·이름을 넣어 앱을 띄운다.
브라우저에서 화면을 열어 `window.__xss` 가 생기지 않는지 확인하는 용도다.

  python -X utf8 tests/frontend/xss_fixture_server.py          # http://127.0.0.1:3102
  python -X utf8 tests/frontend/cdp_smoke.py http://127.0.0.1:3102/ "openPlayerModal('x','KR1'); 1" "wait:4" "window.__xss"

외부 HTTP는 전부 막는다 (실제 라이엇 API를 부르지 않는다).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from test_support import sandbox_env_writes, use_temp_db  # noqa: E402


async def _no_network(self, request, *args, **kwargs):
    raise httpx.ConnectError(f"xss_fixture_server: 외부 호출 차단 ({request.url})")

httpx.AsyncClient.send = _no_network

sandbox_env_writes()
use_temp_db()

import uvicorn  # noqa: E402

from app.config import settings  # noqa: E402
from app.riot_client import riot_client  # noqa: E402
from app.main import app  # noqa: E402

# 각 문자열이 HTML로 해석되면 window.__xss 배열에 표식을 남긴다
def evil(label):
    return f"\"'><img src=x onerror=\"(window.__xss=window.__xss||[]).push('{label}')\">"

ME = "A" * 78
OTHER = ["B" * 77 + str(i) for i in range(9)]
EVIL_NAME = evil("name")
EVIL_TAG = "K<b>1"


def participant(puuid, team, champ, pos, win, k, d, a, name, tag="KR1"):
    return {
        "puuid": puuid, "teamId": team, "championName": champ, "teamPosition": pos, "win": win,
        "kills": k, "deaths": d, "assists": a, "champLevel": 16, "riotIdGameName": name, "riotIdTagline": tag,
        "totalMinionsKilled": 180, "neutralMinionsKilled": 20, "goldEarned": 12345, "timePlayed": 1800,
        "totalDamageDealtToChampions": 20000 + k * 1000, "totalDamageTaken": 15000,
        "visionWardsBoughtInGame": 2, "wardsPlaced": 9, "visionScore": 25,
        "item0": 3031, "item1": 3006, "item2": 0, "item3": 0, "item4": 0, "item5": 0, "item6": 3340,
        "summoner1Id": 4, "summoner2Id": 14,
        "perks": {"styles": [{"style": 8000, "selections": [{"perk": 8010}]}, {"style": 8400, "selections": []}]},
        "pentaKills": 0, "quadraKills": 0, "tripleKills": 1 if k >= 6 else 0, "doubleKills": 1 if k >= 3 else 0,
    }


def match_fixture(match_id, my_win=True):
    me = participant(ME, 100, "Ahri", "MIDDLE", my_win, 8, 2, 10, EVIL_NAME, EVIL_TAG)
    team = [participant(OTHER[i], 100, c, p, my_win, 3, 4, 6, evil(f"ally{i}"), evil(f"allytag{i}"))
            for i, (c, p) in enumerate([("Garen", "TOP"), ("LeeSin", "JUNGLE"), ("Jinx", "BOTTOM"), ("Thresh", "UTILITY")])]
    enemy = [participant(OTHER[4 + i], 200, c, p, not my_win, 2, 5, 3, evil(f"enemy{i}"))
             for i, (c, p) in enumerate([("Darius", "TOP"), ("Vi", "JUNGLE"), ("Zed", "MIDDLE"), ("Caitlyn", "BOTTOM"), ("Lux", "UTILITY")])]
    return {
        "metadata": {"matchId": match_id},
        "info": {"gameDuration": 1800, "gameEndTimestamp": 1_792_000_000_000, "queueId": 420,
                 "gameVersion": "16.21.1", "participants": [me] + team + enemy},
    }


async def fake_profile(game_name, tag_line):
    return {"puuid": ME, "game_name": EVIL_NAME, "tag_line": EVIL_TAG, "profile_icon_id": 1, "summoner_level": 321,
            "tier": "GOLD", "rank_tier": "II", "league_points": 55, "wins": 30, "losses": 25, "queue_type": "RANKED_SOLO_5x5",
            "flex_tier": "UNRANKED", "flex_rank_tier": "", "flex_lp": 0, "flex_wins": 0, "flex_losses": 0}


async def fake_match_ids(puuid, count=20):
    return ["KR_1", "KR_2"][:count]


async def fake_match_detail(match_id):
    return match_fixture(match_id, my_win=match_id == "KR_1")


async def fake_spectator(puuid):
    return {
        "gameId": 7000000001, "gameQueueConfigId": 420, "gameLength": 615, "platformId": "KR",
        "observers": {"encryptionKey": "abcDEF123+/="},
        "bannedChampions": [{"championId": 157, "teamId": 100}],
        "participants": [
            {"puuid": ME, "teamId": 100, "championId": 103, "riotId": f"{EVIL_NAME}#{EVIL_TAG}", "spell1Id": 4, "spell2Id": 14,
             "perks": {"perkIds": [8112], "perkSubStyle": 8300}},
            {"puuid": OTHER[0], "teamId": 200, "championId": 238, "riotId": evil("live") + "#KR2", "spell1Id": 4, "spell2Id": 12,
             "perks": {"perkIds": [8010], "perkSubStyle": 8400}},
        ],
    }


async def fake_league(tier="CHALLENGER"):
    return {"entries": [{"puuid": OTHER[1], "leaguePoints": 1800, "wins": 400, "losses": 250},
                        {"puuid": OTHER[2], "leaguePoints": 1200, "wins": 100, "losses": 90}]}


async def fake_account(puuid):
    return {"gameName": evil("ladder" + puuid[-1]), "tagLine": "K'R\"1"}


async def fake_verify(test_key=None):
    return {"valid": True, "status": "valid", "reason": "fixture"}


settings.riot_api_key = "RGAPI-fixture-key"
riot_client.reset_key_status()
riot_client.verify_key = fake_verify
riot_client.fetch_full_player_profile = fake_profile
riot_client.get_match_ids_by_puuid = fake_match_ids
riot_client.get_match_detail = fake_match_detail
riot_client.get_spectator_active_game_by_puuid = fake_spectator
riot_client.get_apex_league = fake_league
riot_client.get_account_by_puuid = fake_account

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3102
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
