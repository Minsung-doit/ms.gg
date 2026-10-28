"""
라이엇 공식 로그인(RSO, Riot Sign On)으로 계정 소유 인증 (app/riot_sign_on.py)

닉네임만 입력하는 연결은 남의 계정도 내 것이라고 올릴 수 있다. RSO 는 라이엇 홈페이지에서 본인이 로그인해야
puuid 를 받을 수 있어서 '이 계정의 주인'임이 확인된다.
- RSO 클라이언트는 라이엇이 승인한 Production 앱에만 발급된다. RSO_CLIENT_ID / RSO_CLIENT_SECRET 이 없으면 꺼진다.
- 흐름: /auth/riot/login → auth.riotgames.com 로그인 → /auth/riot/callback?code= → 토큰 교환
  → account-v1 /accounts/me (사용자 토큰) 로 puuid·닉네임#태그 확인 → 디스코드 멤버 계정에 '인증됨'으로 연결.
- 라이엇에 등록할 Redirect URI: <SITE_URL>/auth/riot/callback (다르게 쓰려면 RSO_REDIRECT_URI)
"""
import os
import secrets
import urllib.parse
from typing import Any, Dict

import httpx
from fastapi import Request

AUTH_BASE = "https://auth.riotgames.com"
STATE_COOKIE = "riot_oauth_state"


def _env(key: str) -> str:
    return os.getenv(key, "").strip()


def config_ok() -> bool:
    return bool(_env("RSO_CLIENT_ID") and _env("RSO_CLIENT_SECRET"))


def redirect_uri(request: Request) -> str:
    site = _env("SITE_URL").rstrip("/") or str(request.base_url).rstrip("/")
    return _env("RSO_REDIRECT_URI") or f"{site}/auth/riot/callback"


def new_state() -> str:
    return secrets.token_urlsafe(24)


def authorize_url(request: Request, state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": _env("RSO_CLIENT_ID"),
        "redirect_uri": redirect_uri(request),
        "response_type": "code",
        "scope": "openid",
        "state": state,
    })
    return f"{AUTH_BASE}/authorize?{q}"


async def fetch_account(request: Request, code: str) -> Dict[str, Any]:
    """인가 코드 → 사용자 토큰 → 로그인한 본인의 라이엇 계정 (puuid, gameName, tagLine)"""
    from app.config import settings
    async with httpx.AsyncClient(timeout=10.0) as client:
        tok = await client.post(f"{AUTH_BASE}/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(request),
        }, auth=(_env("RSO_CLIENT_ID"), _env("RSO_CLIENT_SECRET")))
        if tok.status_code != 200:
            return {"ok": False, "reason": "token"}
        access = tok.json().get("access_token", "")
        me = await client.get(
            f"https://{settings.riot_routing_region}.api.riotgames.com/riot/account/v1/accounts/me",
            headers={"Authorization": f"Bearer {access}"},
        )
    if me.status_code != 200:
        return {"ok": False, "reason": "account"}
    acc = me.json() or {}
    if not acc.get("puuid") or not acc.get("gameName"):
        return {"ok": False, "reason": "account"}
    return {"ok": True, "puuid": acc["puuid"], "game_name": acc["gameName"], "tag_line": acc.get("tagLine", "")}


def cookie_secure() -> bool:
    return _env("SITE_URL").startswith("https://")
