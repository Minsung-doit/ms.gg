"""
carry.gg Telegram CLI Bridge Tool
터미널(CLI) 환경에서 텔레그램 메신저와 양방향 텍스트/이미지를 송수신하는 유틸리티
"""

import sys
import argparse
from pathlib import Path

# UTF-8 출력 지원
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.services.telegram_service import (
    send_telegram_message,
    send_telegram_photo,
    get_telegram_recent_photos,
    format_telegram_finance_card
)
from app.finance_engine import calculate_financial_summary


def main():
    parser = argparse.ArgumentParser(description="carry.gg Telegram CLI Bridge Tool")
    parser.add_argument("--send", type=str, help="텔레그램으로 보낼 텍스트 메시지")
    parser.add_argument("--send-photo", type=str, help="텔레그램으로 전송할 로컬 이미지 파일 경로")
    parser.add_argument("--caption", type=str, default="", help="이미지와 함께 전송할 캡션")
    parser.add_argument("--chat-id", type=str, help="대상 Telegram Chat ID (생략 시 .env 기본값 사용)")
    parser.add_argument("--list-photos", action="store_true", help="텔레그램을 통해 수신된 최근 이미지 목록 출력")
    parser.add_argument("--finance", action="store_true", help="재무회계본부 핵심 지표를 텔레그램으로 발송")
    parser.add_argument("--interactive", action="store_true", help="CLI 대화형 메신저 모드 실행")

    args = parser.parse_args()

    print("=" * 70)
    print("📡 [carry.gg Telegram CLI Bridge]")
    print(f"   Bot Token 설정 상태: {'✅ 등록됨' if settings.telegram_bot_token else '❌ 미등록'}")
    print(f"   Chat ID 설정 상태: {'✅ 등록됨' if settings.telegram_chat_id else '❌ 미등록'}")
    print("=" * 70)

    if args.send:
        print(f"▶ 텔레그램으로 메시지 발송: '{args.send}'")
        res = send_telegram_message(args.send, chat_id=args.chat_id)
        if res.get("success"):
            print("✅ 발송 성공!")
        else:
            print(f"❌ 발송 실패: {res.get('message')}")

    elif args.send_photo:
        print(f"▶ 텔레그램으로 이미지 발송: '{args.send_photo}'")
        res = send_telegram_photo(args.send_photo, caption=args.caption, chat_id=args.chat_id)
        if res.get("success"):
            print("✅ 이미지 발송 성공!")
        else:
            print(f"❌ 이미지 발송 실패: {res.get('message')}")

    elif args.list_photos:
        photos = get_telegram_recent_photos(limit=10)
        print(f"📁 수신된 텔레그램 이미지 ({len(photos)}개):")
        for idx, p in enumerate(photos, 1):
            print(f"  {idx}. {p['filename']} ({p['size_kb']} KB) -> {p['path']}")

    elif args.finance:
        print("▶ 재무회계본부 지표 계산 및 텔레그램 브로드캐스팅...")
        fin_data = calculate_financial_summary()
        card_html = format_telegram_finance_card(fin_data["profitability"])
        res = send_telegram_message(card_html, chat_id=args.chat_id)
        if res.get("success"):
            print("✅ 재무 지표 발송 완료!")
        else:
            print(f"❌ 발송 실패: {res.get('message')}")

    elif args.interactive:
        print("\n💬 [CLI 대화형 메신저 모드 시작] (종료하려면 'exit' 또는 'quit' 입력)")
        print("텍스트를 입력하면 즉시 텔레그램 채널로 전송됩니다.\n")
        while True:
            try:
                line = input("CLI ➔ 텔레그램: ").strip()
                if line.lower() in ("exit", "quit", "q"):
                    print("대화형 메신저 모드를 종료합니다.")
                    break
                if not line:
                    continue
                res = send_telegram_message(line, chat_id=args.chat_id)
                if res.get("success"):
                    print("  [전송됨]")
                else:
                    print(f"  [전송 실패: {res.get('message')}]")
            except (KeyboardInterrupt, EOFError):
                break

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
