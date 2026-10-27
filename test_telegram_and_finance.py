"""
carry.gg Telegram Omnichannel Messaging & Finance Division Verification Suite
텔레그램 봇 연동, CLI 이미지 브리지, 재무회계 손익분기점(BEP) 엔드포인트 전수 검증
"""

import sys
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.services.telegram_service import (
    format_telegram_player_card,
    format_telegram_finance_card,
    get_telegram_recent_photos
)
from app.finance_engine import calculate_financial_summary

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from test_support import admin_client, sandbox_env_writes, use_temp_db

sandbox_env_writes()
use_temp_db()
client = admin_client(app)

def test_telegram_and_finance_suite():
    print("=" * 80)
    print("📡 [Telegram & Finance Suite] 텔레그램 CLI 브리지 & 재무회계본부 전수 검증")
    print("=" * 80)

    # 1. 재무회계본부 핵심 지표 API 검증
    res_fin = client.get("/api/finance/summary?dau=50000")
    assert res_fin.status_code == 200, f"Finance API failed: {res_fin.status_code}"
    fin_data = res_fin.json()
    assert fin_data["status"] == "ESTIMATE" and fin_data["is_estimate"] is True
    assert "revenue_breakdown" in fin_data
    assert "cost_breakdown" in fin_data
    assert "profitability" in fin_data
    assert fin_data["profitability"]["is_profitable"] is True
    assert fin_data["profitability"]["bep_monthly_active_users"] > 0
    print(f"  [PASS] 1. GET /api/finance/summary -> 200 OK (월간 순이익: +{fin_data['profitability']['monthly_net_profit_krw']:,}원, 마진: {fin_data['profitability']['operating_margin_pct']}%)")

    # 2. 텔레그램 연동 상태 조회 엔드포인트 검증
    orig_token = settings.telegram_bot_token or ""
    orig_chat_id = settings.telegram_chat_id or ""

    res_tg_status = client.get("/api/settings/telegram-status")
    assert res_tg_status.status_code == 200, f"Telegram status check failed: {res_tg_status.status_code}"
    tg_status_data = res_tg_status.json()
    assert "has_token" in tg_status_data
    assert "has_chat_id" in tg_status_data
    print("  [PASS] 2. GET /api/settings/telegram-status -> 200 OK")

    # 3. 텔레그램 설정 저장 엔드포인트 검증
    mock_token = "123456789:AAFakeTokenForTestingTelegramCLIBridge1234"
    mock_chat_id = "987654321"
    res_tg_config = client.post("/api/settings/telegram-config", json={
        "bot_token": mock_token,
        "chat_id": mock_chat_id
    })
    assert res_tg_config.status_code == 200, f"Telegram config save failed: {res_tg_config.status_code}"
    assert res_tg_config.json()["has_token"] is True
    print("  [PASS] 3. POST /api/settings/telegram-config -> 200 OK (토큰 & Chat ID 저장 완료)")

    # 4. 저장 후 마스킹 보안 검증
    res_tg_status_after = client.get("/api/settings/telegram-status")
    data_after = res_tg_status_after.json()
    assert data_after["has_token"] is True
    assert "..." in data_after["masked_token"], "Token masking failed"
    assert not data_after["masked_token"].startswith(mock_token), "Full token exposed in masked field"
    print(f"  [PASS] 4. 텔레그램 토큰 마스킹 보안 검증 완료: {data_after['masked_token']}")

    # 5. 텔레그램 수신 사진 목록 엔드포인트 검증
    res_photos = client.get("/api/telegram/photos?limit=10")
    assert res_photos.status_code == 200, f"Photos endpoint failed: {res_photos.status_code}"
    photos_data = res_photos.json()
    assert photos_data["status"] == "success"
    assert isinstance(photos_data["photos"], list)
    print(f"  [PASS] 5. GET /api/telegram/photos -> 200 OK (수신된 이미지 {len(photos_data['photos'])}개 확인)")

    # 6. 전적 카드 및 재무 요약 HTML 포맷팅 유틸리티 검증
    mock_player = {
        "game_name": "T1 Faker",
        "tag_line": "KR1",
        "tier": "CHALLENGER",
        "league_points": 1420,
        "win_rate": 66.7,
        "wins": 140,
        "losses": 70
    }
    mock_summary = {
        "avg_kda": "4.80:1",
        "most_champions": [{"name": "아지르", "win_rate": 72}]
    }
    card_html = format_telegram_player_card(mock_player, mock_summary)
    assert "T1 Faker#KR1" in card_html
    assert "CHALLENGER" in card_html
    assert "아지르" in card_html
    print("  [PASS] 6. format_telegram_player_card -> HTML 템플릿 검증 통과")

    fin_card_html = format_telegram_finance_card(fin_data["profitability"])
    assert "재무회계본부" in fin_card_html
    assert "손익분기점" in fin_card_html
    print("  [PASS] 7. format_telegram_finance_card -> HTML 템플릿 검증 통과")

    # 7. 클린업 (원본 설정 복원)
    client.post("/api/settings/telegram-config", json={"bot_token": orig_token, "chat_id": orig_chat_id})
    print("  [PASS] 8. 테스트 종료 후 기존 텔레그램 설정 복원 완료")

    print("=" * 80)
    print("🎉 [Telegram & Finance Suite] 8개 전수 테스트 100% ALL PASS 성공!")
    print("=" * 80)

if __name__ == "__main__":
    test_telegram_and_finance_suite()
