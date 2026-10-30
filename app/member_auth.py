"""
디스코드 서버 멤버 전용 로그인 (app/member_auth.py)

라이엇 개인(Personal) 키는 '소규모 비공개 커뮤니티'용이라, 사이트를 지정한 디스코드 서버 멤버에게만 연다.
- MEMBER_LOGIN=discord 이면 켜진다 (로컬 개발은 기본 꺼짐).
- 디스코드 OAuth2 (scope: identify guilds.members.read) → 등록된 서버(app/communities.py) 중 하나라도 멤버면 로그인 쿠키 발급.
  등록된 서버마다 내 멤버 정보를 물어본다 (다른 서버 목록은 받지 않는다. 표시 이름은 첫 서버 별명 → 전역 이름 → 사용자명 순)
- 쿠키는 서명된 '<디스코드ID>.<만료>.<서명>' (7일).
- 서버를 나간·추방된 사람은 5분 안에 끊긴다 (still_member: 봇 토큰으로 5분마다 멤버인지 다시 확인, 2026-10-30).
- 설정이 빠졌는데 켜져 있으면 아무도 들여보내지 않는다 (실수로 공개되지 않게).
"""
import asyncio
import hashlib
import hmac
import os
import secrets
import time
import urllib.parse
from typing import Any, Dict, Optional

import httpx
from fastapi import Request

DISCORD_API = "https://discord.com/api/v10"
SESSION_COOKIE = "member_session"
STATE_COOKIE = "discord_oauth_state"
SESSION_TTL = 7 * 86400

# 로그인 없이 열려 있어야 하는 주소 (로그인 화면·정적 파일·헬스 체크)
# /api/riot/tournament/callback: 라이엇 서버가 보내는 내전 결과 알림 (로그인 없음, 내용은 매치를 직접 불러 확인)
PUBLIC_PREFIXES = ("/login", "/logout", "/auth/discord/", "/static/", "/api/health", "/api/riot/tournament/callback")
PUBLIC_PATHS = {"/robots.txt", "/manifest.json", "/sw.js", "/favicon.ico"}


def _env(key: str) -> str:
    return os.getenv(key, "").strip()


def login_enabled() -> bool:
    return _env("MEMBER_LOGIN").lower() == "discord"


def config_ok() -> bool:
    from app import communities
    return all(_env(k) for k in ("DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET")) and bool(communities.ids())


def _secret() -> bytes:
    from app.config import settings
    # 별도 값이 없으면 관리자 토큰 비밀값에서 파생 (관리자 비밀값을 바꾸면 멤버 세션도 모두 끊긴다)
    base = _env("MEMBER_SESSION_SECRET") or f"member:{settings.admin_token_secret}"
    return base.encode("utf-8")


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_session(discord_id: str, ttl: int = SESSION_TTL) -> str:
    payload = f"{discord_id}.{int(time.time()) + ttl}"
    return f"{payload}.{_sign(payload)}"


def session_user(request: Request) -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE, "")
    try:
        discord_id, expires, sig = token.rsplit(".", 2)
        if int(expires) < time.time() or not discord_id.isdigit():
            return None
    except (ValueError, AttributeError):
        return None
    return discord_id if hmac.compare_digest(sig, _sign(f"{discord_id}.{expires}")) else None


def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def safe_next(next_path: Optional[str]) -> str:
    """로그인 뒤 돌아갈 주소: 이 사이트 안의 경로만 (외부 주소로 보내는 오픈 리다이렉트 방지)"""
    if not next_path or not next_path.startswith("/") or next_path.startswith("//") or "\\" in next_path:
        return "/"
    return next_path


def redirect_uri(request: Request) -> str:
    site = _env("SITE_URL").rstrip("/") or str(request.base_url).rstrip("/")
    return _env("DISCORD_REDIRECT_URI") or f"{site}/auth/discord/callback"


def authorize_url(request: Request, state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": _env("DISCORD_CLIENT_ID"),
        "redirect_uri": redirect_uri(request),
        "response_type": "code",
        "scope": "identify guilds.members.read",
        "state": state,
        "prompt": "none",
    })
    return f"https://discord.com/oauth2/authorize?{q}"


def new_state() -> str:
    return secrets.token_urlsafe(24)


async def check_membership(request: Request, code: str) -> Dict[str, Any]:
    """인가 코드를 토큰으로 바꾸고, 사용자 ID와 들어가 있는 등록 서버 목록(guilds)을 돌려준다."""
    from app import communities
    guild_ids = communities.ids()
    async with httpx.AsyncClient(timeout=10.0) as client:
        tok = await client.post(f"{DISCORD_API}/oauth2/token", data={
            "client_id": _env("DISCORD_CLIENT_ID"),
            "client_secret": _env("DISCORD_CLIENT_SECRET"),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(request),
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if tok.status_code != 200:
            return {"ok": False, "reason": "token"}
        headers = {"Authorization": f"Bearer {tok.json().get('access_token', '')}"}
        me = await client.get(f"{DISCORD_API}/users/@me", headers=headers)
        if me.status_code != 200:
            return {"ok": False, "reason": "profile"}
        # 등록된 서버마다 내 멤버 정보: 200 이면 멤버(별명 포함), 404 면 멤버 아님
        joined, nick = [], None
        for gid in guild_ids:
            gm = await client.get(f"{DISCORD_API}/users/@me/guilds/{gid}/member", headers=headers)
            if gm.status_code == 429:  # 이 경로는 한도가 낮다: 잠깐 기다렸다 한 번 더
                wait = min(float((gm.json() or {}).get("retry_after", 1) or 1), 3.0)
                await asyncio.sleep(wait)
                gm = await client.get(f"{DISCORD_API}/users/@me/guilds/{gid}/member", headers=headers)
            if gm.status_code == 200:
                joined.append(gid)
                nick = nick or (gm.json() or {}).get("nick")
            elif gm.status_code != 404:
                return {"ok": False, "reason": "profile"}
    user = me.json()
    return {"ok": True, "member": bool(joined), "guilds": joined, "discord_id": str(user.get("id", "")),
            "name": nick or user.get("global_name") or user.get("username") or ""}


MEMBERSHIP_RECHECK_SEC = 300
_membership_seen: Dict[str, Any] = {}  # 디스코드 ID → (확인 시각, 멤버인가)
# 디스코드 오류 코드: 10007 그 서버 멤버가 아님, 10013 없는(삭제된) 계정. 봇이 서버에 없을 때의 404(10004)와 구분
NOT_MEMBER_CODES = (10007, 10013)


async def still_member(discord_id: str) -> bool:
    """로그인한 사람이 아직 등록된 디스코드 서버 멤버인지 (5분 기억). 봇 토큰이 없거나 디스코드가 답하지 않으면 막지 않는다"""
    from app import communities
    token = _env("DISCORD_BOT_TOKEN")
    guild_ids = communities.ids()
    if not token or not guild_ids or not discord_id.isdigit():
        return True
    hit = _membership_seen.get(discord_id)
    if hit and time.time() - hit[0] < MEMBERSHIP_RECHECK_SEC:
        return hit[1]
    joined, unsure = [], False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for gid in guild_ids:
                r = await client.get(f"{DISCORD_API}/guilds/{gid}/members/{discord_id}",
                                     headers={"Authorization": f"Bot {token}"})
                if r.status_code == 200:
                    joined.append(gid)
                elif r.status_code == 404 and (r.json() or {}).get("code") in NOT_MEMBER_CODES:
                    continue
                else:  # 한도·봇이 서버에 없음·디스코드 장애: 판단하지 않는다
                    unsure = True
    except (httpx.HTTPError, ValueError):
        unsure = True
    if not joined and unsure:
        _membership_seen[discord_id] = (time.time() - MEMBERSHIP_RECHECK_SEC + 60, True)  # 1분 뒤 다시 확인
        return True
    if len(_membership_seen) > 10000:
        _membership_seen.clear()
    _membership_seen[discord_id] = (time.time(), bool(joined))
    if joined and not unsure:
        from app import community_rank
        community_rank.set_member_guilds(discord_id, joined)  # 들어가 있는 서버 목록도 최신으로
    return bool(joined)


def forget_membership(discord_id: str) -> None:
    _membership_seen.pop(discord_id, None)


def cookie_secure() -> bool:
    return _env("SITE_URL").startswith("https://")
