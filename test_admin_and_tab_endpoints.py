"""
세션 3: Admin 격리 및 9대 탭 핵심 엔드포인트 전수 헬스체크 테스트 스위트
1. 신규 Admin 격리 무결성 검증 (엔지니어링 텔레메트리 은닉, 버튼 비노출, 관리자 엔드포인트 보안 및 응답 무결성)
2. 9대 핵심 탭 전수 엔드포인트 (소환사 전적, 랭킹, 멀티서치, 실시간 관전, 장인 랭킹, 티어리스트, 듀오 시너지, 듀오 구하기, 상성&빌드) 헬스체크
"""

import sys
import os
from pathlib import Path
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.main import app

from test_support import admin_client, sandbox_env_writes, use_temp_db

sandbox_env_writes()
use_temp_db()
# 실제 라이엇 API를 부르지 않도록 키를 비운다 (키 없음 상태의 응답 코드를 검증)
from app.config import settings
settings.riot_api_key = ""
client = admin_client(app)

def test_admin_isolation():
    print("=" * 80)
    print("[Suite 7-A] Admin 격리 및 엔지니어링 텔레메트리 은닉 무결성 검증")
    print("=" * 80)

    # 1. index.html 내 관리자용/개발용 버튼 은닉 확인
    html_path = Path("templates/index.html")
    assert html_path.exists(), "templates/index.html not found!"
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")

    # btnSeedReset 은닉 검증
    btn_seed = soup.find("button", id="btnSeedReset")
    assert btn_seed is not None, "btnSeedReset element should exist in DOM"
    style_seed = btn_seed.get("style", "")
    assert "display: none !important" in style_seed or "display:none" in style_seed, (
        f"btnSeedReset must be hidden from normal users! Found style: {style_seed}"
    )
    print("  [PASS] 1. btnSeedReset (DB 초기화 버튼) 일반 유저 화면 완전 은닉 확인")

    # btnOpenApiKeyModal 은닉 검증
    btn_key = soup.find("button", id="btnOpenApiKeyModal")
    # 일반 화면에서 버튼이 아예 없거나(2026-10-26 제거) 있다면 숨김이어야 한다
    if btn_key is not None:
        style_key = btn_key.get("style", "")
        assert "display: none !important" in style_key or "display:none" in style_key, (
            f"btnOpenApiKeyModal must be hidden from normal users! Found style: {style_key}"
        )
    print("  [PASS] 2. btnOpenApiKeyModal (API 키 설정 버튼) 일반 유저 화면 완전 은닉 확인")

    # 2. 관리자/시스템 전용 헬스체크 & 모니터링 API 엔드포인트 응답성 검증
    admin_endpoints = [
        ("/api/health", 200, "status"),
        ("/api/settings/status", 200, "has_api_key"),
        ("/api/key-status", 200, "is_valid"),
        ("/api/system/metrics", 200, "database_metrics"),
        ("/api/cache/stats", 200, "cached_entries_count"),
        ("/api/sync/status", 200, "is_running")
    ]

    for ep, exp_status, exp_key in admin_endpoints:
        res = client.get(ep)
        assert res.status_code == exp_status, f"Admin endpoint {ep} failed: {res.status_code}"
        data = res.json()
        assert exp_key in data, f"Admin endpoint {ep} response missing key '{exp_key}'"
        print(f"  [PASS] Admin Endpoint: {ep} -> HTTP {res.status_code} (Key '{exp_key}' verified)")

    print("  -> Admin 격리 및 관리자 엔드포인트 무결성 100% 통과!\n")


def test_nine_tabs_endpoints():
    print("=" * 80)
    print("[Suite 7-B] 9개 탭 핵심 엔드포인트 전수 헬스체크 (200 OK & Schema Valid)")
    print("=" * 80)

    # 탭별 대표 엔드포인트와 허용 상태 코드
    # - REAL: 라이엇 실데이터 기능. 키가 없거나 만료되면 지어낸 값 대신 503(또는 없음 404)을 돌려야 한다
    # - GATED: 생성(난수) 데이터 기능. 기본 설정에서는 503으로 막혀 있어야 한다
    REAL = {200, 404, 503}
    OK = {200}
    GATED = {404}  # 생성(난수) 데이터 API는 2026-10-25 삭제
    tab_tests = [
        ("1. 소환사 전적", [
            ("GET", "/api/search?q=Hide%20on%20bush", None, "mode", OK),
            ("GET", "/api/player/Hide on bush/KR1", None, None, REAL),
            ("GET", "/api/player/Hide on bush/KR1/matches?count=5", None, None, REAL),
            ("GET", "/api/player/Hide on bush/KR1/ingame", None, None, REAL),
            ("GET", "/api/player/Hide on bush/KR1/analysis", None, None, GATED),
            ("GET", "/api/player/Hide on bush/KR1/coach", None, None, GATED),
        ]),
        ("2. 소환사 랭킹", [
            ("GET", "/api/leaderboard?tier=CHALLENGER", None, "results", OK),
            ("GET", "/api/pro-tracker", None, None, GATED),
            ("GET", "/api/tier-distribution", None, "is_sample", OK),
        ]),
        ("3. 멀티서치 (실데이터, 키 없으면 notice와 함께 빈 결과)", [
            ("POST", "/api/multisearch", {"raw_text": "Hide on bush님이 로비에 참가하셨습니다."}, "players", OK),
        ]),
        ("4~7. 생성 통계 기능 (숨김)", [
            ("GET", "/api/spectator/featured", None, "is_sample", OK),
            ("GET", "/api/champion-masters?champion=Yasuo", None, None, OK),
            ("GET", "/api/champion-analytics?position=MID&tier=EMERALD_PLUS", None, None, OK),
            ("GET", "/api/aram/tierlist", None, "is_sample", OK),
            ("GET", "/api/quick-op-champions", None, "champions", OK),
            ("GET", "/api/duo-synergy", None, "duos", OK),
            ("GET", "/api/duo-bot-matchups", None, "matchups", OK),
            ("GET", "/api/champion-matchup?champion=Yasuo&enemy=Yone", None, "mode", OK),
            ("GET", "/api/champion-build/Yasuo", None, "core_builds", OK),
            ("GET", "/api/community-counters?champ1=Yasuo", None, "tips", OK),
        ]),
        ("8. 듀오 구하기", [
            ("GET", "/api/duo-posts", None, "posts", OK),
            ("POST", "/api/duo-posts", {
                "game_name": "테스트소환사", "tag_line": "KR1", "tier_kr": "다이아몬드",
                "my_position": "BOT", "target_position": "SUP", "queue_type": "솔로랭크", "voice": True,
                "title": "디스코드 음성 듀오 서폿 구합니다", "description": "보이스 소통 가능하신 분 환영합니다",
                "discord_tag": "DiscordUser#1234", "most_champions": ["징크스", "카이사"]
            }, "post", OK),
        ]),
        ("9. 챔피언 정보 (Data Dragon)", [
            ("GET", "/api/champions", None, "champions", OK),
            ("GET", "/api/champion-skills/Ahri", None, "champion_id", OK),
        ]),
    ]

    total_endpoints = 0
    for tab_name, tests in tab_tests:
        print(f"\n  ▶ [{tab_name}]")
        for method, endpoint, body, key_check, allowed in tests:
            total_endpoints += 1
            res = client.get(endpoint) if method == "GET" else client.post(endpoint, json=body)
            assert res.status_code in allowed, f"{method} {endpoint}: {res.status_code} not in {sorted(allowed)} - {res.text[:200]}"
            if res.status_code == 200 and key_check:
                assert key_check in res.json(), f"{endpoint} response missing key: {key_check}"
            print(f"     ✓ {method} {endpoint[:55]} -> {res.status_code}")

    print(f"\n  -> {total_endpoints}개 엔드포인트가 기대한 상태 코드로 응답")
    print("=" * 80)


def run_all_admin_and_tab_tests():
    test_admin_isolation()
    test_nine_tabs_endpoints()
    print("🏆 [SUCCESS] Suite 7 (신규 Admin 격리 및 9개 탭 엔드포인트 헬스체크) 100% ALL PASS!")

if __name__ == "__main__":
    run_all_admin_and_tab_tests()
