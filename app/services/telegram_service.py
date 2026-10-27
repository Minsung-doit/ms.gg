"""
carry.gg Telegram Omnichannel Messaging & Image Bridge Service
텔레그램 봇 API를 통한 양방향 텍스트/이미지 송수신 및 CLI 메신저 브리지 엔진
"""

import os
import html
import json
import time
import logging
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, List
from app.config import settings
from app.services.discord_service import _player_card_fields

logger = logging.getLogger("lolgg.telegram")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "uploads" / "telegram"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_telegram_api_url(method: str) -> Optional[str]:
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        return None
    return f"https://api.telegram.org/bot{token}/{method}"


def send_telegram_message(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML"
) -> Dict[str, Any]:
    """
    텔레그램 봇으로 텍스트/HTML 메시지를 발송합니다.
    """
    target_chat_id = (chat_id or settings.telegram_chat_id or "").strip()
    if not target_chat_id:
        return {"success": False, "message": "등록된 텔레그램 Chat ID가 없습니다."}

    api_url = get_telegram_api_url("sendMessage")
    if not api_url:
        return {"success": False, "message": "등록된 텔레그램 Bot Token이 없습니다."}

    payload = {
        "chat_id": target_chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }

    try:
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            if res_data.get("ok"):
                return {"success": True, "message": "메시지 전송 성공", "result": res_data.get("result")}
            return {"success": False, "message": f"텔레그램 응답 오류: {res_data}"}
    except urllib.error.HTTPError as e:
        logger.error(f"Telegram sendMessage HTTP error: {e.code} - {e.reason}")
        return {"success": False, "message": f"텔레그램 HTTP 에러 {e.code}"}
    except Exception as e:
        logger.error(f"Telegram sendMessage error: {e}")
        return {"success": False, "message": f"네트워크 오류: {str(e)}"}


def send_telegram_photo(
    photo_path_or_url: str,
    caption: str = "",
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    텔레그램으로 이미지(URL 또는 로컬 파일)를 전송합니다.
    """
    target_chat_id = (chat_id or settings.telegram_chat_id or "").strip()
    if not target_chat_id:
        return {"success": False, "message": "등록된 텔레그램 Chat ID가 없습니다."}

    api_url = get_telegram_api_url("sendPhoto")
    if not api_url:
        return {"success": False, "message": "등록된 텔레그램 Bot Token이 없습니다."}

    # 1. URL 형태인 경우 JSON으로 전송
    if photo_path_or_url.startswith("http://") or photo_path_or_url.startswith("https://"):
        payload = {
            "chat_id": target_chat_id,
            "photo": photo_path_or_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
        try:
            data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                api_url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return {"success": True, "message": "사진 전송 성공", "result": res_data.get("result")}
        except Exception as e:
            return {"success": False, "message": f"URL 사진 전송 오류: {str(e)}"}

    # 2. 로컬 파일인 경우 보안 경로 검증 및 멀티파트 폼데이터 전송
    clean_p = photo_path_or_url.strip().replace("\\", "/")
    if ".." in clean_p or clean_p.startswith("~"):
        return {"success": False, "message": "허용되지 않는 파일 경로(상위 디렉터리 탐색)입니다."}

    file_path = (BASE_DIR / clean_p).resolve() if not Path(clean_p).is_absolute() else Path(clean_p).resolve()
    try:
        file_path.relative_to(BASE_DIR.resolve())
    except ValueError:
        return {"success": False, "message": "작업공간 외부 파일은 전송할 수 없습니다."}

    allowed_img_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    if file_path.suffix.lower() not in allowed_img_exts:
        return {"success": False, "message": "전송 가능한 이미지 형식(.png, .jpg, .webp, .gif)이 아닙니다."}

    sensitive_names = {".env", "opgg.db", "server.log"}
    if file_path.name.lower() in sensitive_names or any(file_path.name.lower().endswith(x) for x in [".key", ".pem", ".env", ".db"]):
        return {"success": False, "message": "보안상 접근이 차단된 파일입니다."}

    if not file_path.exists() or not file_path.is_file():
        return {"success": False, "message": f"로컬 파일이 존재하지 않습니다: {photo_path_or_url}"}

    try:
        boundary = "----WebKitFormBoundary" + hex(int(time.time() * 1000))[2:]
        lines = []

        # chat_id
        lines.append(f"--{boundary}".encode())
        lines.append(b'Content-Disposition: form-data; name="chat_id"')
        lines.append(b"")
        lines.append(str(target_chat_id).encode())

        # caption
        if caption:
            lines.append(f"--{boundary}".encode())
            lines.append(b'Content-Disposition: form-data; name="caption"')
            lines.append(b"")
            lines.append(caption.encode("utf-8"))
            lines.append(f"--{boundary}".encode())
            lines.append(b'Content-Disposition: form-data; name="parse_mode"')
            lines.append(b"")
            lines.append(b"HTML")

        # photo file
        filename = file_path.name
        with open(file_path, "rb") as f:
            file_data = f.read()

        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="photo"; filename="{filename}"'.encode())
        lines.append(b"Content-Type: image/jpeg")
        lines.append(b"")
        lines.append(file_data)
        lines.append(f"--{boundary}--".encode())
        lines.append(b"")

        body = b"\r\n".join(lines)
        req = urllib.request.Request(
            api_url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            return {"success": True, "message": "로컬 사진 전송 성공", "result": res_data.get("result")}
    except Exception as e:
        return {"success": False, "message": f"로컬 사진 전송 실패: {str(e)}"}


def save_telegram_photo_file(file_id: str, custom_filename: Optional[str] = None) -> Dict[str, Any]:
    """
    텔레그램 사용자가 채팅방으로 보낸 사진을 서버 로컬 디렉토리(uploads/telegram/)에 저장합니다.
    """
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        return {"success": False, "message": "텔레그램 봇 토큰 미설정"}

    try:
        # 1. getFile 호출하여 파일 경로(file_path) 획득
        get_file_url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
        req = urllib.request.Request(get_file_url, headers={"User-Agent": "carry.gg-Telegram-Bridge"})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            file_info = json.loads(resp.read().decode("utf-8"))

        if not file_info.get("ok"):
            return {"success": False, "message": "텔레그램 파일 정보 획득 실패"}

        remote_path = file_info["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{token}/{remote_path}"

        # 2. 로컬 파일로 다운로드
        ext = Path(remote_path).suffix or ".jpg"
        ts = int(time.time())
        local_name = custom_filename or f"tg_img_{ts}_{file_id[:8]}{ext}"
        local_target = UPLOAD_DIR / local_name

        req_dl = urllib.request.Request(download_url, headers={"User-Agent": "carry.gg-Telegram-Bridge"})
        with urllib.request.urlopen(req_dl, timeout=20.0) as resp_dl, open(local_target, "wb") as out_f:
            data = resp_dl.read()
            out_f.write(data)

        file_size_kb = round(len(data) / 1024, 1)
        logger.info(f"Telegram image downloaded: {local_target} ({file_size_kb} KB)")

        return {
            "success": True,
            "filename": local_name,
            "path": str(local_target),
            "size_kb": file_size_kb,
            "timestamp": ts,
            "url_path": f"/uploads/telegram/{local_name}"
        }
    except Exception as e:
        logger.error(f"Failed to download telegram photo: {e}")
        return {"success": False, "message": f"사진 다운로드 실패: {str(e)}"}


def get_telegram_recent_photos(limit: int = 20) -> List[Dict[str, Any]]:
    """
    텔레그램을 통해 수신된 최근 이미지 목록을 반환합니다.
    """
    if not UPLOAD_DIR.exists():
        return []

    photos = []
    files = sorted(UPLOAD_DIR.glob("*.*"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[:limit]:
        stat = f.stat()
        photos.append({
            "filename": f.name,
            "path": str(f),
            "size_kb": round(stat.st_size / 1024, 1),
            "modified_time": int(stat.st_mtime),
            "url_path": f"/uploads/telegram/{f.name}"
        })
    return photos


def format_telegram_player_card(player: Optional[Dict[str, Any]] = None, summary: Optional[Dict[str, Any]] = None) -> str:
    """
    텔레그램 전용 소환사 전적 HTML 포맷
    """
    # parse_mode=HTML이므로 값은 모두 이스케이프 (이름에 <, & 가 있으면 텔레그램이 메시지를 거부함)
    f = _player_card_fields(player or {}, summary or {})
    e = {k: html.escape(v) for k, v in f.items()}

    return (
        f"🏆 <b>[carry.gg 소환사 전적] {e['name']}#{e['tag']}</b>\n\n"
        f"🛡️ <b>솔로랭크</b>: <code>{e['tier']}</code> ({e['lp']})\n"
        f"📊 <b>솔로랭크 승률</b>: <b>{e['win_rate']}</b> ({e['record']})\n"
        f"⚡ <b>평균 KDA</b>: <b>{e['kda']}</b>\n"
        f"👑 <b>모스트 챔피언</b>: {e['most']}\n\n"
        f"🔗 <a href='http://localhost:3000/?q={urllib.parse.quote(f['name'])}%23{urllib.parse.quote(f['tag'])}'>carry.gg 웹 상세 보기</a>"
    )


def format_telegram_finance_card(finance: Optional[Dict[str, Any]] = None) -> str:
    """
    재무회계본부 핵심 재무 요약 HTML 포맷
    """
    # calculate_financial_summary() 전체 결과와 그 안의 profitability 묶음 둘 다 받는다.
    # (호출부는 profitability만 넘기는데, 거기엔 매출·비용 키가 없어 예전엔 항상 0원으로 찍혔음)
    finance = finance or {}
    flat: Dict[str, Any] = {}
    for section in ("revenue_breakdown", "cost_breakdown", "profitability"):
        if isinstance(finance.get(section), dict):
            flat.update(finance[section])
    flat.update({k: v for k, v in finance.items() if not isinstance(v, dict)})

    def won(key: str) -> str:
        v = flat.get(key)
        return f"{v:,}원" if isinstance(v, (int, float)) and not isinstance(v, bool) else "-"

    margin = flat.get("operating_margin_pct")
    bep_mau = flat.get("bep_monthly_active_users")

    return (
        f"📊 <b>[carry.gg 재무회계본부] 월간 재무 추정 요약</b>\n\n"
        f"💰 <b>월간 예상 광고 매출</b>: <b>{won('monthly_ad_revenue_krw')}</b>\n"
        f"📉 <b>월간 운영 인프라 비용</b>: <b>{won('monthly_infra_cost_krw')}</b>\n"
        f"📈 <b>월간 순 영업 이익</b>: <b>{won('monthly_net_profit_krw')}</b> (영업이익률: <b>{margin if margin is not None else '-'}%</b>)\n"
        f"🎯 <b>손익분기점 (BEP) MAU</b>: <b>{f'{bep_mau:,}명' if isinstance(bep_mau, int) else '-'}</b>\n\n"
        f"ℹ️ <i>DAU·eCPM 가정으로 계산한 추정치이며 실제 매출이 아닙니다.</i>"
    )
