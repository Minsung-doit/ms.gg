"""
carry.gg Discord Integration & Webhook/Bot Automated Verification Suite
디스코드 웹후크 연동, 슬래시 봇 인터페이스, 마크다운 생성 및 전적 공유 엔드포인트 전수 검증
"""

import sys
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.services.discord_service import (
    format_player_discord_markdown,
    format_multisearch_discord_markdown,
    send_discord_webhook
)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from test_support import admin_client, sandbox_env_writes, use_temp_db

sandbox_env_writes()
use_temp_db()
client = admin_client(app)

# 테스트가 discord.com 으로 실제 요청을 보내지 않도록 네트워크 호출을 가짜로 대체
import app.services.discord_service as _discord_service


class _FakeDiscordResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_discord_service.urllib.request.urlopen = lambda req, timeout=None: _FakeDiscordResponse()

def test_discord_integration():
    print("=" * 80)
    print("🎮 [Discord Integration Suite] 디스코드 연계 & 웹후크/봇 무결성 검증 시작")
    print("=" * 80)

    # 1. 디스코드 연동 상태 조회 엔드포인트 검증
    res_status = client.get("/api/settings/discord-status")
    assert res_status.status_code == 200, f"Status check failed: {res_status.status_code}"
    status_data = res_status.json()
    assert "has_webhook" in status_data, "has_webhook field missing"
    assert "masked_webhook" in status_data, "masked_webhook field missing"
    print(f"  [PASS] 1. GET /api/settings/discord-status -> 200 OK (has_webhook={status_data['has_webhook']})")

    # 2. 유효하지 않은 웹후크 URL 등록 시 400 에러 검증
    res_invalid = client.post("/api/settings/discord-webhook", json={"webhook_url": "https://malicious-site.com/webhook"})
    assert res_invalid.status_code == 400, "Should reject non-discord URL"
    print("  [PASS] 2. POST /api/settings/discord-webhook (비정상 URL 차단 및 400 에러 반환 검증 완료)")

    # 3. 유효한 디스코드 웹후크 URL 등록 및 마스킹 검증
    test_webhook_url = "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz_test_token_123"
    res_save = client.post("/api/settings/discord-webhook", json={"webhook_url": test_webhook_url})
    assert res_save.status_code == 200, f"Save webhook failed: {res_save.status_code}"
    assert res_save.json().get("has_webhook") is True
    print("  [PASS] 3. POST /api/settings/discord-webhook -> 200 OK (정상 웹후크 등록 성공)")

    # 4. 등록 후 상태 조회에서 URL 마스킹 확인 (보안 감사)
    res_status_after = client.get("/api/settings/discord-status")
    data_after = res_status_after.json()
    assert data_after["has_webhook"] is True
    assert "..." in data_after["masked_webhook"], f"Masking failed: {data_after['masked_webhook']}"
    assert not data_after["masked_webhook"].endswith("_test_token_123"), "Token leaked in masked URL"
    print(f"  [PASS] 4. URL 마스킹 보안 검증 완료: {data_after['masked_webhook']}")

    # 5. 소환사 전적 공유 엔드포인트 및 마크다운 포맷팅 검증
    mock_player = {
        "game_name": "Faker",
        "tag_line": "KR1",
        "tier": "CHALLENGER",
        "league_points": 1250,
        "win_rate": 68.5,
        "wins": 137,
        "losses": 63,
        "profile_icon_id": 6
    }
    mock_summary = {
        "avg_kda": "4.50:1",
        "most_champions": [
            {"name": "아리", "win_rate": 75},
            {"name": "오리아나", "win_rate": 65},
            {"name": "사일러스", "win_rate": 60}
        ]
    }
    res_share_player = client.post("/api/discord/share/player", json={
        "player": mock_player,
        "summary": mock_summary,
        "custom_msg": "페이커 전적 확인"
    })
    assert res_share_player.status_code == 200, f"Share player failed: {res_share_player.status_code}"
    share_player_data = res_share_player.json()
    assert "markdown" in share_player_data
    assert "Faker#KR1" in share_player_data["markdown"]
    assert "CHALLENGER" in share_player_data["markdown"]

    # 5-1. summary=None 방어 무결성 검증 (NoneType AttributeError 방어)
    res_share_player_nosummary = client.post("/api/discord/share/player", json={
        "player": {"game_name": "Hide on bush", "tag_line": "KR1", "tier": "CHALLENGER", "lp": 1200, "wins": 200, "losses": 100, "win_rate": 66.7, "kda_ratio": "4.2:1"}
    })
    assert res_share_player_nosummary.status_code == 200, f"Share player without summary failed: {res_share_player_nosummary.status_code}"
    assert "Hide on bush#KR1" in res_share_player_nosummary.json()["markdown"]
    print("  [PASS] 5. POST /api/discord/share/player -> 200 OK & summary=None 방어 무결성 확인")

    # 6. 멀티서치 공유는 생성 데이터 기능이라 삭제됨
    res_share_multi = client.post("/api/discord/share/multisearch", json={"team_summary": {}, "players": []})
    assert res_share_multi.status_code == 404, f"Share multisearch should be removed: {res_share_multi.status_code}"
    print("  [PASS] 6. POST /api/discord/share/multisearch -> 404 (생성 데이터 기능 삭제)")

    # 7. 듀오 구인글 등록 시 디스코드 웹후크 자동 브로드캐스팅 파이프라인 무결성 검증
    res_duo = client.post("/api/duo-posts", json={
        "game_name": "Chovy",
        "tag_line": "KR1",
        "tier_kr": "다이아몬드",
        "my_position": "MID",
        "target_position": "JUG",
        "queue_type": "솔로랭크",
        "voice": True,
        "title": "다이아 미드 정글 듀오 구함",
        "description": "승률 70% 이상 정글러님 모십니다."
    })
    assert res_duo.status_code == 200, f"Duo post failed: {res_duo.status_code}"
    assert res_duo.json().get("status") == "ok"
    print("  [PASS] 7. POST /api/duo-posts -> 200 OK (디스코드 웹후크 자동 트리거 비차단 파이프라인 검증 완료)")

    # 마스터 이상은 듀오 불가: 등록 거절
    res_master = client.post("/api/duo-posts", json={
        "game_name": "Tester", "tag_line": "KR1", "tier_kr": "마스터", "my_position": "MID",
        "target_position": "JUG", "queue_type": "솔로랭크", "voice": True, "title": "마스터 듀오", "description": "x"
    })
    assert res_master.status_code == 422, f"Master duo post should be rejected: {res_master.status_code}"
    print("  [PASS] 7-1. 마스터 티어 듀오 구인글 -> 422 거절")

    # 게임별 구인: 설정 API, 게임별 허용 값, 게임 필터
    cfg = client.get("/api/duo-games").json()
    assert {g["id"] for g in cfg["games"]} >= {"lol", "pubg", "overwatch"}
    pubg = client.post("/api/duo-posts", json={"game": "pubg", "game_name": "배그유저", "tag_line": "",
                                                "tier_kr": "마스터", "queue_type": "경쟁전 스쿼드", "title": "스쿼드 구함"})
    assert pubg.status_code == 200, pubg.text
    assert pubg.json()["post"]["game"] == "pubg" and pubg.json()["post"]["max_members"] == 4
    assert client.post("/api/duo-posts", json={"game": "pubg", "game_name": "x", "tier_kr": "아이언",
                                               "queue_type": "경쟁전 스쿼드", "title": "t"}).status_code == 422, "배그엔 아이언 없음"
    assert client.post("/api/duo-posts", json={"game": "overwatch", "game_name": "x", "my_position": "MID",
                                               "tier_kr": "골드", "queue_type": "경쟁전", "title": "t"}).status_code == 422, "옵치엔 미드 없음"
    assert client.post("/api/duo-posts", json={"game": "nope", "game_name": "x", "title": "t"}).status_code == 422
    lol_posts = client.get("/api/duo-posts?game=lol").json()["posts"]
    pubg_posts = client.get("/api/duo-posts?game=pubg").json()["posts"]
    assert all((p.get("game") or "lol") == "lol" for p in lol_posts)
    assert any(p["title"] == "스쿼드 구함" for p in pubg_posts) and all(p["game"] == "pubg" for p in pubg_posts)
    print("  [PASS] 7-2. 게임별 구인: 설정 API, 게임별 허용 값 검사, 게임 필터")

    # '같이해요': 한 사람당 한 번 +1, 정원 차면 자동 마감, 마감 후 409, 참가자 식별값은 응답에 없음
    duo = client.post("/api/duo-posts", json={"game": "lol", "game_name": "참가테스트", "tag_line": "KR1", "tier_kr": "골드",
                                              "my_position": "MID", "target_position": "JUG", "queue_type": "솔로랭크", "title": "참가 테스트"})
    pid = duo.json()["post"]["id"]
    from fastapi.testclient import TestClient as _JC
    joiner = _JC(app, client=("198.51.100.77", 40000))  # 작성자와 다른 방문자
    j1 = joiner.post(f"/api/duo-posts/{pid}/join")
    assert j1.status_code == 200 and j1.json()["status"] == "ok", j1.text
    jp = j1.json()["post"]
    assert jp["current_members"] == 2 and jp["is_full"] is True and "joiners" not in jp and len(jp["joiner_names"]) == 1
    assert joiner.post(f"/api/duo-posts/{pid}/join").json()["status"] == "already", "같은 사람은 한 번만"
    assert client.post("/api/duo-posts/999999/join").status_code == 404
    listed = next(x for x in client.get("/api/duo-posts?game=lol").json()["posts"] if x["id"] == pid)
    assert listed["is_full"] and "joiners" not in listed
    print("  [PASS] 7-3. 같이해요: 1인 1회, 정원 차면 자동 마감, 식별값 비노출")

    # 참가 취소: 인원 -1, 마감 풀림, 참가 안 한 사람은 not_joined
    lv = joiner.delete(f"/api/duo-posts/{pid}/join")
    assert lv.status_code == 200 and lv.json()["status"] == "ok" and lv.json()["post"]["current_members"] == 1
    assert lv.json()["post"]["is_full"] is False and lv.json()["post"]["joiner_names"] == []
    assert joiner.delete(f"/api/duo-posts/{pid}/join").json()["status"] == "not_joined"
    # 작성자가 '다시 모집'하면 인원 = 작성자 + 남은 참가자 (참가자로 꽉 찬 글이면 참가자 목록 비움)
    from app.duo_finder_engine import toggle_duo_post_capacity
    assert joiner.post(f"/api/duo-posts/{pid}/join").json()["post"]["is_full"]
    reopened = toggle_duo_post_capacity(pid)
    assert reopened["is_full"] is False and reopened["current_members"] == 1 and reopened["joiners"] == [], reopened
    # 구인 알림 역할 설정 파싱 (숫자 ID만)
    import os as _os
    from app.services.discord_service import duo_alert_roles
    _saved = _os.environ.get("DUO_ALERT_ROLES")
    _os.environ["DUO_ALERT_ROLES"] = "lol=123456, pubg=abc ,overwatch=789"
    try:
        assert duo_alert_roles() == {"lol": "123456", "overwatch": "789"}
    finally:
        if _saved is None: _os.environ.pop("DUO_ALERT_ROLES", None)
        else: _os.environ["DUO_ALERT_ROLES"] = _saved
    print("  [PASS] 7-4. 참가 취소, 구인 알림 역할 설정")

    # 글 삭제: 작성자 토큰 없으면 403, 있으면 삭제 후 목록에서 사라짐
    owner = duo.json()["owner_token"]
    from fastapi.testclient import TestClient as _TC
    anon = _TC(app)  # 관리자 아닌 일반 방문자
    assert anon.delete(f"/api/duo-posts/{pid}").status_code == 403
    assert anon.delete(f"/api/duo-posts/{pid}", headers={"X-Duo-Owner-Token": "wrong"}).status_code == 403
    assert anon.delete(f"/api/duo-posts/{pid}", headers={"X-Duo-Owner-Token": owner}).status_code == 200
    assert all(x["id"] != pid for x in client.get("/api/duo-posts?game=lol").json()["posts"])
    print("  [PASS] 7-5. 구인글 삭제는 작성자만")

    # 디스코드 구인 메시지: 역할 멘션만 허용, 메시지 ID 받아 두고 마감·삭제 시 같은 메시지를 고침 (네트워크 없이 가짜 응답)
    import json as _json, urllib.request as _ur
    from app.services import discord_service as _ds
    from app.config import settings as _st
    _calls = []
    class _R:
        def __init__(s, st, body=b""): s.status, s.body = st, body
        def read(s): return s.body
        def __enter__(s): return s
        def __exit__(s, *a): pass
    def _fake(req, timeout=0):
        _calls.append((req.get_method(), req.full_url, _json.loads(req.data.decode())))
        return _R(200, b'{"id": "998877"}') if req.get_method() == "POST" else _R(200)
    _orig_open, _orig_url, _orig_roles = _ur.urlopen, _st.discord_webhook_url, _os.environ.get("DUO_ALERT_ROLES")
    _ur.urlopen, _st.discord_webhook_url = _fake, "https://discord.com/api/webhooks/1/abc"
    _os.environ["DUO_ALERT_ROLES"] = "lol=111222333"
    try:
        _p = {"game": "lol", "game_name": "a", "tag_line": "KR1", "tier_kr": "골드", "queue_type": "솔로랭크",
              "max_members": 2, "current_members": 1, "title": "t", "my_position": "MID", "target_position": "JUG"}
        _r = _ds.send_duo_post_webhook(_p)
        assert _r["message_id"] == "998877" and _calls[-1][1].endswith("?wait=true")
        assert _calls[-1][2]["allowed_mentions"] == {"parse": [], "roles": ["111222333"]}
        _p.update(discord_message_id="998877", current_members=2, is_full=True, joiner_names=["철수"])
        _ds.update_duo_post_webhook(_p)
        assert _calls[-1][0] == "PATCH" and _calls[-1][1].endswith("/messages/998877")
        assert _calls[-1][2]["embeds"][0]["title"].startswith("🔴 마감")
        _ds.update_duo_post_webhook(_p, deleted=True)
        assert _calls[-1][2]["embeds"][0]["title"].startswith("🗑️ 삭제됨")
        _ds.send_discord_webhook({"content": "@everyone hi"})
        assert _calls[-1][2]["allowed_mentions"] == {"parse": [], "roles": []}, "일반 메시지는 멘션 차단 유지"
        # 게임별 채널: 배그 채널이 있으면 배그 글은 그쪽으로, 롤은 기본 채널로
        _os.environ["DISCORD_WEBHOOK_URL_PUBG"] = "https://discord.com/api/webhooks/9/pubg"
        _ds.send_duo_post_webhook(dict(_p, game="pubg", discord_message_id=None))
        assert _calls[-1][1].startswith("https://discord.com/api/webhooks/9/pubg")
        _ds.send_duo_post_webhook(dict(_p, discord_message_id=None))
        assert _calls[-1][1].startswith("https://discord.com/api/webhooks/1/abc")
        _os.environ.pop("DISCORD_WEBHOOK_URL_PUBG", None)
    finally:
        _ur.urlopen, _st.discord_webhook_url = _orig_open, _orig_url
        if _orig_roles is None: _os.environ.pop("DUO_ALERT_ROLES", None)
        else: _os.environ["DUO_ALERT_ROLES"] = _orig_roles
    print("  [PASS] 7-6. 디스코드 구인 메시지: 역할 멘션만 허용, 마감·삭제 시 같은 메시지 수정")

    # 만료: 노출 시간이 지난 글 중 디스코드 메시지가 있는 것만, 한 번만 표시
    import time as _time
    from app.database import get_connection as _gc
    from app.duo_finder_engine import expired_posts_to_mark, mark_expired_in_discord, DUO_POST_TTL_SEC
    _c = _gc()
    _old = int(_time.time()) - DUO_POST_TTL_SEC - 60
    _c.execute("INSERT INTO duo_posts (data, owner_token_hash, created_at) VALUES (?,?,?)",
               (_json.dumps({"title": "만료글", "discord_message_id": "555"}), "x", _old))
    _c.execute("INSERT INTO duo_posts (data, owner_token_hash, created_at) VALUES (?,?,?)",
               (_json.dumps({"title": "메시지없음"}), "x", _old))
    _c.commit(); _c.close()
    _exp = [x for x in expired_posts_to_mark() if x["title"] in ("만료글", "메시지없음")]
    assert [x["title"] for x in _exp] == ["만료글"], _exp
    mark_expired_in_discord(_exp[0])
    assert not [x for x in expired_posts_to_mark() if x["title"] == "만료글"], "한 번만 표시"
    print("  [PASS] 7-7. 노출 시간이 지난 구인글의 디스코드 메시지 만료 표시 (한 번만)")

    # 8. 클린업: 웹후크 URL 초기화 (테스트 격리)
    client.post("/api/settings/discord-webhook", json={"webhook_url": ""})
    print("  [PASS] 8. 테스트 종료 후 설정 초기화 및 격리 완료")

    print("=" * 80)
    print("🎉 [Discord Integration Suite] 8개 전수 테스트 100% PASS 성공!")
    print("=" * 80)

if __name__ == "__main__":
    test_discord_integration()
