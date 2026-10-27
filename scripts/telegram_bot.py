"""
carry.gg Official Telegram Bot & CLI Image Ingestion Agent
- CLI 환경의 이미지 첨부 한계를 극복하는 텔레그램 양방향 메신저 연계 봇
- 유저가 전송한 인게임 스크린샷/버그 화면 자동 다운로드 & CLI 작업공간 보존
- 슬래시 커맨드: /전적, /티어, /멀티서치, /재무, /회계, /보고서, /도움말
"""

import os
import sys
import time
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import threading
from pathlib import Path

# UTF-8 콘솔 출력 지원
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
    save_telegram_photo_file,
    format_telegram_player_card,
    format_telegram_finance_card,
    get_telegram_recent_photos
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("lolgg.telegram_bot")

API_BASE = "http://localhost:3000"

# Gemini 3.8 Flash 대화형 AI & 멀티모달 비전 클라이언트 초기화
gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
genai_client = None
if gemini_api_key:
    try:
        from google import genai
        from google.genai import types
        genai_client = genai.Client(api_key=gemini_api_key)
        logger.info("Gemini AI Client (gemini-3.8-flash) successfully initialized for Telegram Bot!")
    except Exception as e:
        logger.warning(f"Failed to initialize Gemini AI Client: {e}")


pipeline_lock = threading.Lock()
is_pipeline_running = False
current_pipeline_task = ""


PIPELINE_DISABLED_MSG = (
    "⛔ <b>원격 파이프라인 실행은 비활성화되었습니다.</b>\n\n"
    "채팅 메시지로 AI가 코드를 수정하는 자동 파이프라인은 2026-10-24 개발 지침(CLAUDE.md)에 따라 막혀 있습니다.\n"
    "작업 지시는 PC에서 직접 하고, 결과는 <code>python scripts/run_all_tests.py</code> 실제 테스트로 확인하세요."
)


def run_company_pipeline_task(order_text: str, chat_id: str, user_name: str = "회장님"):
    """
    (비활성화) 텔레그램 메시지로 run_company_pipeline.py 를 원격 실행하던 기능.
    채팅 한 줄로 AI가 감독 없이 코드를 수정하게 되므로 실행하지 않고 안내만 회신한다.
    """
    logger.warning(f"[Telegram] 원격 파이프라인 실행 요청을 거부했습니다 (@{user_name}): {order_text.strip()[:80]}")
    send_telegram_message(PIPELINE_DISABLED_MSG, chat_id=chat_id)


def ask_gemini_ai(prompt: str, user_name: str = "회장님") -> str:
    """
    텔레그램 사용자와 앤티그래비티(Antigravity) AI 간 1:1 실시간 대화 생성
    """
    if not genai_client:
        return f"안녕하세요, {user_name}님! 현재 Gemini AI 엔진이 연결되지 않았습니다. /help 명령어로 지원 기능을 확인하세요."

    system_prompt = (
        "당신은 구글 딥마인드 팀이 설계한 강력한 AI 코딩 및 롤(LoL) 데이터 분석 어시스턴트 'Antigravity(앤티그래비티)'입니다. "
        "당신은 회장님(사용자)과 텔레그램을 통해 실시간으로 1:1 대화하고 있습니다. "
        "회장님의 질문, 코딩 업무 지시, 롤 경기 분석, 일상 대화에 매우 친절하고 예의 바르며, 전문적이고 명쾌하게 한국어로 답변하십시오. "
        "특히 회장님이 텔레그램으로 코딩/기능 구현 업무 지시(오더)를 내리고 싶어 하실 경우, "
        "언제든지 편하게 '오더: ~해줘' 또는 '/오더 [지시내용]' 형태로 지시하시면 5대 본부 8대 전문직원 전사 파이프라인이 즉각 100% 완전 자율 가동되어 "
        "기획부터 개발, 보안, QA, 최종 결재 보고서까지 완료되어 텔레그램으로 보고된다고 명확하고 든든하게 안내하십시오. "
        "답변에 적절한 이모지를 섞어 메신저 스타일에 맞게 가독성 있게 작성하십시오."
    )
    fallback_models = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3-flash-preview"]
    last_err = None
    for model_name in fallback_models:
        try:
            resp = genai_client.models.generate_content(
                model=model_name,
                contents=f"[시스템 지침: {system_prompt}]\n\n[사용자({user_name})]: {prompt}"
            )
            return resp.text.strip()
        except Exception as e:
            last_err = e
            logger.warning(f"Gemini {model_name} failed: {e}, trying next model...")
            continue
    logger.error(f"All Gemini models failed in ask_gemini_ai: {last_err}")
    return f"죄송합니다, {user_name}님. 일시적인 AI 엔진 오류가 발생했습니다: {str(last_err)}"


def analyze_image_with_gemini(image_path: str, caption: str = "") -> str:
    """
    텔레그램으로 수신된 롤 인게임 스크린샷/버그 화면 멀티모달 정밀 분석
    """
    if not genai_client:
        return "이미지가 CLI 작업공간에 저장되었습니다. (Gemini AI Vision 엔진 미연결)"

    try:
        from google.genai import types
        with open(image_path, "rb") as f:
            img_bytes = f.read()

        ext = Path(image_path).suffix.lower()
        mime_type = "image/png" if ext == ".png" else "image/jpeg"
        image_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)

        prompt = (
            "이 롤(League of Legends) 게임 화면, 픽창 캡처, 스코어보드, 또는 개발 스크린샷 이미지를 심층 분석해줘. "
            "1. 화면 내용 요약 (챔피언, 킬데스, 골드/CS, 룬/아이템 상황 또는 화면 정보)\n"
            "2. 인게임 핵심 진단 (유리한 점 / 위험한 점 / 패배 또는 승리 원인 분석)\n"
            "3. 프로게이머 관점의 즉각 피드백 또는 해결책 3줄 제안\n"
            f"추가 사용자 캡션: {caption if caption else '없음'}"
        )

        fallback_models = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3-flash-preview"]
        last_err = None
        for model_name in fallback_models:
            try:
                resp = genai_client.models.generate_content(
                    model=model_name,
                    contents=[image_part, prompt]
                )
                return resp.text.strip()
            except Exception as e:
                last_err = e
                logger.warning(f"Gemini Vision {model_name} failed: {e}, trying next model...")
                continue
        logger.error(f"All Gemini models failed in analyze_image_with_gemini: {last_err}")
        return f"이미지는 정상 저장되었으나 AI 분석 중 오류가 발생했습니다: {str(last_err)}"
    except Exception as e:
        logger.error(f"Gemini image load error: {e}")
        return f"이미지 파일을 읽는 중 오류가 발생했습니다: {str(e)}"


def fetch_api_json(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    url = f"{API_BASE}{endpoint}"
    try:
        req_data = json.dumps(data).encode("utf-8") if data else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"API call error {endpoint}: {e}")
        return {}


def handle_telegram_command(cmd: str, args: str, chat_id: str) -> None:
    cmd = cmd.lower()

    if cmd in ("/start", "/help", "/도움말"):
        help_msg = (
            "🤖 <b>[carry.gg 공식 텔레그램 CLI 메신저 봇]</b>\n\n"
            "CLI 창의 이미지 첨부 한계를 극복하고 텔레그램을 통해 실시간으로 소통하는 양방향 에이전트입니다.\n\n"
            "📸 <b>이미지 첨부 & CLI 연계:</b>\n"
            "• 롤 경기 화면, 룬/아이템 캡처를 사진으로 전송하시면 <b>CLI 작업공간 자동 저장 및 Gemini AI 심층 비전 분석</b>이 회신됩니다!\n\n"
            "⚡ <b>지원 슬래시 커맨드:</b>\n"
            "• <code>/전적 [소환사명#태그]</code> - 랭크 티어, 20전 승률, KDA 조회\n"
            "• <code>/티어 [포지션]</code> - TOP, JUG, MID, ADC, SUP 1티어 순위\n"
            "• <code>/멀티서치 [채팅/소환사목록]</code> - 5인 픽창 팀 분석 리포트\n"
            "• <code>/재무</code> or <code>/회계</code> - 재무회계본부 월간 손익 및 BEP 지표\n"
            "• <code>/보고서</code> - 회장님 최종 결재 보고서 요약본\n"
            "• <code>/캡처</code> - 최근 수신된 CLI 업로드 이미지 목록\n\n"
            "<i>carry.gg Enterprise Omnichannel Agent v2026.10</i>"
        )
        send_telegram_message(help_msg, chat_id=chat_id)

    elif cmd == "/전적":
        if not args:
            send_telegram_message("⚠️ 사용법: <code>/전적 Faker#KR1</code>", chat_id=chat_id)
            return

        target = args.strip()
        name, tag = target.split("#") if "#" in target else (target, "KR1")
        data = fetch_api_json(f"/api/player/{urllib.parse.quote(name)}/{urllib.parse.quote(tag)}")
        if not data or not data.get("player"):
            send_telegram_message(f"❌ 소환사 <b>{target}</b> 전적을 찾을 수 없습니다.", chat_id=chat_id)
            return

        player = data["player"]
        summary = {"avg_kda": player.get("kda_ratio", ""), "most_champions": player.get("most_champions", [])}
        card_html = format_telegram_player_card(player, summary)
        send_telegram_message(card_html, chat_id=chat_id)

    elif cmd == "/티어":
        pos = args.strip().upper() if args else "MID"
        data = fetch_api_json("/api/champions/tier-list")
        champs = data.get("results", []) if data else []
        filtered = [c for c in champs if c.get("position", "").upper() == pos or pos in ("ALL", "전체")][:5]

        if not filtered:
            filtered = champs[:5]

        lines = [f"🏆 <b>[carry.gg {pos} 라인 1티어 챔피언 순위]</b>\n"]
        for i, c in enumerate(filtered, 1):
            lines.append(f"<b>{i}위. {c.get('name_kr', c.get('name'))}</b> | 승률: <b>{c.get('win_rate')}%</b> | 픽률: {c.get('pick_rate')}%")

        send_telegram_message("\n".join(lines), chat_id=chat_id)

    elif cmd in ("/재무", "/회계"):
        data = fetch_api_json("/api/finance/summary")
        if not data:
            send_telegram_message("재무 데이터를 불러올 수 없습니다.", chat_id=chat_id)
            return

        card = format_telegram_finance_card(data.get("profitability", {}))
        send_telegram_message(card, chat_id=chat_id)

    elif cmd == "/보고서":
        rep_msg = (
            "📄 <b>[보고서 안내]</b>\n\n"
            "reports/ 폴더의 자체 채점 보고서(100점/ALL PASS)는 실제 검증 근거가 아닙니다.\n"
            "현재 상태는 PC에서 <code>python scripts/run_all_tests.py</code> 실행 결과로 확인하세요."
        )
        send_telegram_message(rep_msg, chat_id=chat_id)

    elif cmd == "/캡처":
        photos = get_telegram_recent_photos(limit=5)
        if not photos:
            send_telegram_message("📁 아직 텔레그램을 통해 전송된 이미지가 없습니다.\n채팅창에 사진을 첨부해 보세요!", chat_id=chat_id)
            return

        lines = ["📸 <b>[CLI 작업공간 최근 수신 이미지 목록]</b>\n"]
        for p in photos:
            lines.append(f"• <code>{p['filename']}</code> ({p['size_kb']} KB)")
        send_telegram_message("\n".join(lines), chat_id=chat_id)

    elif cmd in ("/오더", "/지시", "/order", "/pipeline", "/파이프라인"):
        if not args:
            send_telegram_message(
                "⚠️ <b>사용법</b>: <code>/오더 [지시사항]</code>\n\n"
                "예시: <code>/오더 소환사 상세 화면에 최근 20게임 티어 변동 뱃지 추가하고 파이프라인 완수해줘</code>",
                chat_id=chat_id
            )
            return
        threading.Thread(target=run_company_pipeline_task, args=(args, chat_id), daemon=True).start()

    elif cmd in ("/상태", "/status", "/진행상황"):
        if is_pipeline_running:
            send_telegram_message(
                f"⚙️ <b>[현재 파이프라인 가동 중]</b>\n\n"
                f"• <b>진행 과업</b>: <code>{current_pipeline_task}</code>\n"
                f"• <b>상태</b>: 전사 5대 본부 8대 전문직원 순차 협업 중...",
                chat_id=chat_id
            )
        else:
            send_telegram_message(
                "✅ <b>[전사 파이프라인 대기 중]</b>\n\n현재 실행 중인 백그라운드 파이프라인이 없습니다.\n<code>/오더 [지시사항]</code>으로 새 업무를 하달하십시오.",
                chat_id=chat_id
            )

    else:
        send_telegram_message(f"❓ 알 수 없는 명령어입니다: <code>{cmd}</code>\n도움말은 <code>/help</code>를 입력하세요.", chat_id=chat_id)


def start_telegram_polling():
    """
    텔레그램 봇 실시간 폴링 루프
    """
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        print("=" * 70)
        print("⚠️ [Telegram Bot] TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다.")
        print("   .env 파일에 TELEGRAM_BOT_TOKEN=... 및 TELEGRAM_CHAT_ID=... 를 등록하세요.")
        print("   웹 인터페이스(상단 디스코드/텔레그램 연동) 또는 API를 통해 즉시 등록 가능합니다.")
        print("=" * 70)
        return

    print("=" * 70)
    print("🤖 [Telegram Bot] carry.gg 텔레그램 메신저 & 이미지 수신 에이전트 가동 시작!")
    print(f"   API 서버 주소: {API_BASE}")
    print("   수신 대기 모드: Long-Polling (이미지 및 명령어 실시간 수신)")
    print("=" * 70)

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=20"
            req = urllib.request.Request(url, headers={"User-Agent": "carry.gg-Telegram-Bot"})
            with urllib.request.urlopen(req, timeout=25.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if not data.get("ok"):
                time.sleep(2)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message")
                if not msg:
                    continue

                chat_id = str(msg["chat"]["id"])
                user_name = msg.get("from", {}).get("first_name", "회장님")

                # Only the owner chat configured in .env may talk to the bot: it can launch the
                # AI pipeline on this PC, so a stranger who finds the bot must be ignored, not paired.
                if not settings.telegram_chat_id or settings.telegram_chat_id != chat_id:
                    print(
                        f"🚫 [Telegram] 등록되지 않은 채팅({chat_id}, {user_name})의 메시지를 무시했습니다. "
                        f"본인이라면 .env의 TELEGRAM_CHAT_ID={chat_id} 로 직접 등록하세요."
                    )
                    continue

                # 1. 사진(Photo) 수신 처리 -> CLI 작업공간 자동 다운로드 + Gemini AI 비전 심층 분석!
                if "photo" in msg:
                    best_photo = msg["photo"][-1]
                    file_id = best_photo["file_id"]
                    caption = msg.get("caption", "")

                    print(f"\n📸 [Telegram Ingestion] @{user_name} 님으로부터 이미지 수신! 다운로드 시작...")
                    res_save = save_telegram_photo_file(file_id)

                    if res_save.get("success"):
                        saved_name = res_save["filename"]
                        size_kb = res_save["size_kb"]
                        print(f"✅ [CLI Saved] 이미지 다운로드 완료: {res_save['path']} ({size_kb} KB)")

                        # 1차 다운로드 완료 안내
                        ack_msg = (
                            f"📸 <b>[CLI 이미지 수신 및 영구 저장 완료]</b>\n\n"
                            f"• <b>파일명</b>: <code>{saved_name}</code> ({size_kb} KB)\n"
                            f"• <b>저장 경로</b>: <code>uploads/telegram/{saved_name}</code>\n"
                            f"• <b>캡션</b>: {caption if caption else '(없음)'}\n\n"
                            f"🧠 <i>앤티그래비티 AI가 이미지를 정밀 분석 중입니다...</i>"
                        )
                        send_telegram_message(ack_msg, chat_id=chat_id)

                        # 2차 Gemini 3.8 Flash Vision 심층 분석 리포트 발송
                        ai_vision = analyze_image_with_gemini(res_save["path"], caption)
                        send_telegram_message(
                            f"🧠 <b>[Antigravity AI 게임 화면 심층 분석 리포트]</b>\n\n{ai_vision}",
                            chat_id=chat_id
                        )
                    else:
                        send_telegram_message(f"❌ 이미지 저장 실패: {res_save.get('message')}", chat_id=chat_id)
                    continue

                # 2. 텍스트 명령어 처리
                text = msg.get("text", "").strip()
                if text.startswith("/"):
                    parts = text.split(maxsplit=1)
                    cmd = parts[0]
                    args = parts[1] if len(parts) > 1 else ""
                    print(f"💬 [Telegram Command] @{user_name}: {cmd} {args}")
                    handle_telegram_command(cmd, args, chat_id)
                else:
                    # 자연어 오더 감지 (예: "오더: ...", "지시: ...", "파이프라인 돌려줘/실행해줘")
                    clean_text = text.strip()
                    is_direct_order = False
                    order_content = clean_text

                    for prefix in ("오더:", "지시:", "오더 ", "지시 ", "[오더]", "[지시]"):
                        if clean_text.startswith(prefix):
                            is_direct_order = True
                            order_content = clean_text[len(prefix):].strip()
                            break

                    if not is_direct_order and "파이프라인" in clean_text and any(w in clean_text for w in ("실행", "돌려", "가동", "시작", "완수")):
                        is_direct_order = True
                        order_content = clean_text

                    if is_direct_order and order_content:
                        print(f"👑 [Telegram Direct Order] @{user_name}: {order_content}")
                        threading.Thread(target=run_company_pipeline_task, args=(order_content, chat_id, user_name), daemon=True).start()
                    else:
                        # 일반 텍스트 대화 수신 -> 앤티그래비티(Gemini AI) 실시간 1:1 대화!
                        print(f"💬 [Telegram Message] @{user_name}: {text}")
                        ai_reply = ask_gemini_ai(text, user_name)
                        send_telegram_message(ai_reply, chat_id=chat_id)

        except Exception as e:
            logger.warning(f"Polling loop notice: {e}")
            time.sleep(3)


if __name__ == "__main__":
    start_telegram_polling()
