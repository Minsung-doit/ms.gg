from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse, RedirectResponse
import secrets
import httpx
from pydantic import BaseModel, Field, field_validator, model_validator
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import urllib.parse
import time
import sys
import re
import os
import logging

logger = logging.getLogger(__name__)
from app.ddragon import DDRAGON_CDN, DDRAGON_VERSION, champion_img

# 1:1 상성 매치업 다이렉트 검색어 분할용 사전 컴파일 정규식 (매 요청 시 재컴파일 병목 0ms 제거)
DELIM_MATCHUP_PATTERN = re.compile(r'\s*(?:vs\.?|대|/)\s*|\s+', re.IGNORECASE)

from app.config import settings
from app.admin_auth import (
    is_admin_authenticated,
    is_admin_port,
    generate_admin_token,
    verify_admin_access,
    revoke_all_admin_sessions,
    admin_login_limiter,
    ADMIN_SESSION_TTL
)
from app.rate_limit import (
    enforce as enforce_rate_limit,
    SlidingWindowLimiter,
    duo_post_limiter,
    community_tip_limiter,
    community_vote_limiter,
    discord_share_limiter,
    leaderboard_sync_limiter,
    player_sync_limiter,
    discord_join_limiter,
    ai_coach_limiter,
    member_link_limiter,
    ai_summary_daily_limiter,
)
from app.database import (
    init_db,
    search_players_by_name,
    get_player_by_riot_id,
    add_search_history,
    get_system_database_stats,
)
from app.riot_client import RiotAPIError, riot_client
from app.real_data import (
    PlayerDataUnavailable,
    fetch_player,
    public_profile,
    get_recent_matches_payload,
    is_riot_puuid,
    init_match_cache,
    init_ladder_table,
    load_ladder,
    sync_challenger_ladder,
    fetch_live_game,
    init_champion_mastery_table,
    load_champion_masters,
    sync_ladder_masteries
)
from app.champion_engine import ALL_CHAMPIONS, find_champion, CHAMPION_MAP_BY_NAME, CHAMPION_MAP_BY_ID
from app.match_collector import player_collected_summary, player_cached_summary
from app.sample_data import SAMPLE_NOTICE, anonymize_featured
from app.ai_coach import build_coach_report, ai_summary
from app.traffic import record_page_view, traffic_summary
from app import member_auth, community_rank, riot_sign_on, communities
from app.champion_stats import compute_tier_list, compute_matchups, compute_head_to_head, compute_duo_synergy, compute_champion_build, compute_pair_synergy, compute_bot_lane_matchups
from app.champion_skills_data import get_champion_skills_data
from app.spectator_engine import generate_spectator_launch_script, get_featured_matches
from app.lobby_parser import parse_summoner_names
from app.aram_engine import generate_aram_tier_list
from app.duo_finder_engine import (
    get_duo_posts,
    create_duo_post,
    record_discord_join,
    get_discord_join_stats,
    toggle_duo_post_capacity,
    verify_duo_owner,
)
from app.tier_distribution_engine import get_tier_distribution_stats
from app.community_counter_engine import (
    init_community_tips_db,
    get_community_tips,
    add_community_tip,
    vote_community_tip
)
from app.sync_automation_engine import sync_queue, sync_worker, rate_limiter
from fastapi.middleware.gzip import GZipMiddleware
from app.cache_engine import fast_cache
from app.services.discord_service import (
    send_duo_post_webhook,
    send_player_share_webhook,
    format_player_discord_markdown,
    test_discord_webhook,
)
from app.services.telegram_service import send_telegram_message, send_telegram_photo, get_telegram_recent_photos
from app.finance_engine import calculate_financial_summary
import asyncio

def parse_matchup_pair(query: str) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    FR-02: 1:1 상성 매치업 다이렉트 검색 인텐트 분석기
    - 공백 구분: '요네 야스오', '야스오 요네', 'Yone Yasuo'
    - 구분자 지원: '요네 vs 야스오', '요네vs야스오', '요네 vs. 야스오', '요네 / 야스오', '요네/야스오', '요네 대 야스오', '요네대야스오'
    - 공백 없는 챔피언 결합어: '요네야스오', '야스오요네'
    - 초성 2챔피언 매치업: 'ㅇㄴ ㅇㅅㅇ'
    """
    clean = query.strip()
    if not clean:
        return None

    # 단일 챔피언 완전 일치 여부 선제 확인 (단일 챔피언 검색 보호)
    single = find_champion(clean)
    if single:
        c_clean_name = single["name"].replace(" ", "").lower()
        c_clean_id = single["id"].lower()
        q_no_space = clean.replace(" ", "").lower()
        if q_no_space == c_clean_name or q_no_space == c_clean_id:
            return None

    # 1. 정규식 구분자(vs, vs., 대, /, 공백) 기반 토큰 분할
    splits = [s.strip() for s in DELIM_MATCHUP_PATTERN.split(clean) if s.strip()]
    if len(splits) == 2:
        c1 = find_champion(splits[0])
        c2 = find_champion(splits[1])
        if c1 and c2 and c1["id"].lower() != c2["id"].lower():
            return (c1, c2)
    elif len(splits) > 2:
        for i in range(1, len(splits)):
            p1 = " ".join(splits[:i]).strip()
            p2 = " ".join(splits[i:]).strip()
            c1 = find_champion(p1)
            c2 = find_champion(p2)
            if c1 and c2 and c1["id"].lower() != c2["id"].lower():
                return (c1, c2)

    # 2. 공백 없는 붙여쓰기 보정 (예: '요네야스오', '야스오요네')
    clean_no_space = clean.replace(" ", "")
    if len(clean_no_space) >= 4:
        for k in range(2, len(clean_no_space) - 1):
            p1 = clean_no_space[:k]
            p2 = clean_no_space[k:]
            c1 = find_champion(p1)
            c2 = find_champion(p2)
            if c1 and c2 and c1["id"].lower() != c2["id"].lower():
                if (c1["name"].replace(" ", "").lower() == p1.lower() or c1["id"].lower() == p1.lower()) and \
                   (c2["name"].replace(" ", "").lower() == p2.lower() or c2["id"].lower() == p2.lower()):
                    return (c1, c2)

    return None

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="carry.gg Summoner Search", version="2.0.0")

# 1. 초고속 JSON 전송을 위한 GZip 압축 미들웨어 (4KB 이상 대형 페이로드만 압축하여 CPU 절약)
app.add_middleware(GZipMiddleware, minimum_size=4000)

def _bot_secret_ok(request: Request) -> bool:
    import hmac as _hmac
    secret = os.getenv("BOT_API_SECRET", "").strip()
    given = request.headers.get("X-Bot-Secret", "")
    return len(secret) >= 16 and bool(given) and _hmac.compare_digest(given.encode(), secret.encode())


@app.middleware("http")
async def require_discord_member(request: Request, call_next):
    """MEMBER_LOGIN=discord 이면 디스코드 서버 멤버만 사이트를 쓸 수 있다 (관리자 포트는 별도 인증)."""
    if not member_auth.login_enabled() or is_admin_port(request):
        return await call_next(request)
    path = request.url.path
    # 디스코드 봇(scripts/discord_bot.py)은 로그인 대신 BOT_API_SECRET 으로 API만 쓴다
    if path.startswith("/api/") and _bot_secret_ok(request):
        return await call_next(request)
    if not member_auth.is_public_path(path):
        uid = member_auth.session_user(request)
        if not uid:
            if path.startswith("/api/"):
                return JSONResponse(status_code=401, content={"detail": "디스코드 로그인이 필요합니다.", "login_url": "/login"})
            target = path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(url="/login?next=" + urllib.parse.quote(target, safe=""), status_code=302)
        # 디스코드 서버를 나갔거나 추방된 사람은 로그인이 남아 있어도 끊는다 (5분마다 확인)
        if not await member_auth.still_member(uid):
            resp = (JSONResponse(status_code=401, content={"detail": "디스코드 서버 멤버가 아니라서 로그아웃되었습니다.", "login_url": "/login"})
                    if path.startswith("/api/") else RedirectResponse(url="/login?error=member", status_code=302))
            resp.delete_cookie(member_auth.SESSION_COOKIE)
            return resp
    response = await call_next(request)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"  # 멤버 전용 사이트는 검색엔진에 올리지 않는다
    return response


LOGIN_ERRORS = {
    "member": "이 사이트는 지정된 디스코드 서버 멤버만 이용할 수 있습니다.",
    "state": "로그인 요청이 만료되었습니다. 다시 시도해주세요.",
    "discord": "디스코드에서 정보를 받지 못했습니다. 잠시 후 다시 시도해주세요.",
    "denied": "디스코드 로그인을 취소했습니다.",
}


@app.get("/login", response_class=HTMLResponse)
async def member_login_page(request: Request, next: str = "/", error: str = ""):
    if member_auth.login_enabled() and member_auth.session_user(request):
        return RedirectResponse(url=member_auth.safe_next(next), status_code=302)
    return templates.TemplateResponse(request=request, name="login.html", context={
        "site_name": SITE_NAME,
        "next_path": member_auth.safe_next(next),
        "message": LOGIN_ERRORS.get(error, ""),
        "configured": member_auth.config_ok(),
    })


@app.get("/auth/discord/login")
async def member_discord_login(request: Request, next: str = "/"):
    if not member_auth.config_ok():
        return RedirectResponse(url="/login", status_code=302)
    state = member_auth.new_state()
    resp = RedirectResponse(url=member_auth.authorize_url(request, state), status_code=302)
    resp.set_cookie(member_auth.STATE_COOKIE, f"{state}|{member_auth.safe_next(next)}", max_age=600,
                    httponly=True, samesite="lax", secure=member_auth.cookie_secure())
    return resp


@app.get("/auth/discord/callback")
async def member_discord_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    saved_state, _, next_path = request.cookies.get(member_auth.STATE_COOKIE, "").partition("|")
    if error:
        return RedirectResponse(url="/login?error=denied", status_code=302)
    if not code or not state or not saved_state or not secrets.compare_digest(state, saved_state):
        return RedirectResponse(url="/login?error=state", status_code=302)
    try:
        result = await member_auth.check_membership(request, code)
    except httpx.HTTPError:
        result = {"ok": False}
    if not result.get("ok"):
        return RedirectResponse(url="/login?error=discord", status_code=302)
    if not result.get("member"):
        resp = RedirectResponse(url="/login?error=member", status_code=302)
        resp.delete_cookie(member_auth.STATE_COOKIE)
        return resp
    community_rank.remember_member(result["discord_id"], result.get("name", ""))
    community_rank.set_member_guilds(result["discord_id"], result.get("guilds") or [])
    member_auth.forget_membership(result["discord_id"])  # 다시 들어온 사람은 바로 다시 확인
    resp = RedirectResponse(url=member_auth.safe_next(next_path), status_code=302)
    resp.delete_cookie(member_auth.STATE_COOKIE)
    resp.set_cookie(member_auth.SESSION_COOKIE, member_auth.make_session(result["discord_id"]),
                    max_age=member_auth.SESSION_TTL, httponly=True, samesite="lax", secure=member_auth.cookie_secure())
    return resp


def _member_id(request: Request) -> Optional[str]:
    """디스코드 로그인 사용자 ID. 로그인 기능이 꺼진 로컬 개발에서는 테스트용 ID 하나를 쓴다."""
    if member_auth.login_enabled():
        return member_auth.session_user(request)
    return "local-dev"


def _current_guild(request: Request) -> str:
    """지금 보고 있는 디스코드 서버 (app/communities.py). 서버 설정이 없으면 "" (구분 없음)"""
    mid = _member_id(request) if member_auth.login_enabled() else None
    return communities.current(request, mid)


def _guild_allowed(row_guild: Optional[str], request: Request) -> bool:
    """글·게임이 내가 들어가 있는 서버 것인지 (다른 서버 글에 참가하지 못하게)"""
    if not communities.ids():
        return True
    mid = _member_id(request) if member_auth.login_enabled() else None
    allowed = communities.member_guilds(mid) if mid else communities.ids()
    return (row_guild or communities.default_id()) in allowed


@app.get("/api/me")
async def get_me(request: Request):
    member_id = _member_id(request)
    member = community_rank.get_member(member_id) if member_id else None
    # verified: 라이엇 로그인으로 본인 인증 (서버 랭킹·내전 순위에 올라감). False 면 닉네임 등록만 (티어 역할·팀 나누기용)
    account = ({"game_name": member["game_name"], "tag_line": member["tag_line"], "verified": bool(member.get("verified"))}
               if member and member.get("puuid") else None)
    mine = communities.member_guilds(member_id if member_auth.login_enabled() else None)
    return {"login_enabled": member_auth.login_enabled(), "logged_in": bool(member_id),
            "discord_name": (member or {}).get("discord_name", ""), "account": account,
            "riot_login_enabled": riot_sign_on.config_ok(),
            # 여러 서버에 들어가 있으면 화면 위에서 서버를 바꿀 수 있다
            "communities": [{"id": g, "name": communities.name_of(g) or "디스코드 서버"} for g in mine],
            "community": _current_guild(request)}


class CommunityPick(BaseModel):
    guild_id: str = Field(min_length=1, max_length=32, pattern=r"^\d+$")


@app.post("/api/community")
async def pick_community(req: CommunityPick, request: Request):
    """보고 있을 디스코드 서버 바꾸기 (내가 들어가 있는 서버만)"""
    mid = _member_id(request) if member_auth.login_enabled() else None
    if req.guild_id not in communities.member_guilds(mid):
        raise HTTPException(status_code=403, detail="들어가 있지 않은 서버입니다.")
    resp = JSONResponse({"status": "ok", "community": req.guild_id, "name": communities.name_of(req.guild_id)})
    resp.set_cookie(communities.CURRENT_COOKIE, req.guild_id, max_age=365 * 86400, httponly=True, samesite="lax",
                    secure=member_auth.cookie_secure())
    return resp


RIOT_LINK_DONE = "/?tab=serverranking&riot_link="


@app.get("/auth/riot/login")
async def riot_login(request: Request):
    """라이엇 공식 로그인으로 본인 계정 인증 시작 (디스코드 로그인한 멤버만)"""
    if not riot_sign_on.config_ok():
        return RedirectResponse(url=RIOT_LINK_DONE + "off", status_code=302)
    if not _member_id(request):
        return RedirectResponse(url="/login?next=" + urllib.parse.quote("/?tab=serverranking"), status_code=302)
    state = riot_sign_on.new_state()
    resp = RedirectResponse(url=riot_sign_on.authorize_url(request, state), status_code=302)
    resp.set_cookie(riot_sign_on.STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax",
                    secure=riot_sign_on.cookie_secure())
    return resp


@app.get("/auth/riot/callback")
async def riot_login_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    saved_state = request.cookies.get(riot_sign_on.STATE_COOKIE, "")
    member_id = _member_id(request)

    def done(result: str) -> RedirectResponse:
        resp = RedirectResponse(url=RIOT_LINK_DONE + result, status_code=302)
        resp.delete_cookie(riot_sign_on.STATE_COOKIE)
        return resp

    if error:
        return done("denied")
    if not riot_sign_on.config_ok() or not member_id:
        return done("off" if member_id else "login")
    if not code or not state or not saved_state or not secrets.compare_digest(state, saved_state):
        return done("state")
    enforce_rate_limit(member_link_limiter, request, "member_link")
    try:
        account = await riot_sign_on.fetch_account(request, code)
    except httpx.HTTPError:
        account = {"ok": False}
    if not account.get("ok"):
        return done("riot")
    # 티어·아이콘은 기존 소환사 조회로 채운다. 조회가 안 돼도 인증한 puuid·닉네임으로는 연결한다.
    player = {"puuid": account["puuid"], "game_name": account["game_name"], "tag_line": account["tag_line"]}
    try:
        fetched = await fetch_player(account["game_name"], account["tag_line"], allow_cached=False)
        if fetched.get("puuid") == account["puuid"]:
            player = fetched
    except PlayerDataUnavailable:
        pass
    community_rank.link_account(member_id, player)
    return done("ok")


class RegisterRiotAccountRequest(BaseModel):
    # 띄어쓰기는 상관없다 (라이엇 조회가 공백·대소문자를 무시). 이름의 연속 공백은 하나로, 태그의 공백은 뺀다
    game_name: str = Field(min_length=1, max_length=24)
    tag_line: str = Field(min_length=2, max_length=8)

    @field_validator("game_name")
    @classmethod
    def _clean_name(cls, v):
        v = " ".join(v.split())
        if not v or len(v.replace(" ", "")) > 16:
            raise ValueError("닉네임은 16자까지입니다.")
        return v

    @field_validator("tag_line")
    @classmethod
    def _clean_tag(cls, v):
        v = "".join(v.split()).lstrip("#")
        if not 2 <= len(v) <= 5:
            raise ValueError("태그는 2~5자입니다.")
        return v


@app.post("/api/me/riot-account")
async def register_my_riot_account(req: RegisterRiotAccountRequest, request: Request):
    """닉네임 등록: 라이엇에 실제로 있는 계정만 (본인 인증 아님 → 티어 역할·팀 나누기용, 랭킹·내전 순위에는 안 올라감)"""
    member_id = _member_id(request)
    if not member_id:
        raise HTTPException(status_code=401, detail="디스코드 로그인이 필요합니다.")
    enforce_rate_limit(member_link_limiter, request, "member_link")
    return await _register_riot_account(member_id, req)


async def _register_riot_account(member_id: str, req: RegisterRiotAccountRequest) -> Dict[str, Any]:
    """라이엇 호출은 계정 확인 1회만 (봇이 오래 기다리지 않게). 티어는 바로 뒤에 따로 받아 둔다"""
    if not settings.riot_api_key:
        raise HTTPException(status_code=503, detail="라이엇 API 키가 등록되지 않아 닉네임을 확인할 수 없습니다.")
    try:
        account = await riot_client.get_account_by_riot_id(req.game_name, req.tag_line)
    except RiotAPIError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"라이엇에 없는 닉네임이에요: {req.game_name}#{req.tag_line}")
        if e.status_code == 429:
            raise HTTPException(status_code=429, detail="라이엇 응답이 몰려 있어요. 잠시 후 다시 시도해 주세요.")
        raise HTTPException(status_code=503, detail="라이엇에서 확인하지 못했어요. 잠시 후 다시 시도해 주세요.")
    player = {"puuid": account.get("puuid"), "game_name": account.get("gameName") or req.game_name,
              "tag_line": account.get("tagLine") or req.tag_line}
    if not community_rank.is_linkable(player):
        raise HTTPException(status_code=404, detail="라이엇에서 확인되지 않는 소환사입니다.")
    status = community_rank.register_account(member_id, player)
    if status == "ok":
        async def _fill_tier(name=player["game_name"], tag=player["tag_line"]):
            try:
                await fetch_player(name, tag, allow_cached=False)  # 티어 역할에 쓸 솔로랭크
            except Exception as e:
                logger.warning("tier fetch after nickname registration failed: %s", type(e).__name__)
        task = asyncio.create_task(_fill_tier())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    if status == "verified_already":
        raise HTTPException(status_code=409, detail="이미 라이엇 로그인으로 인증한 계정이 있어요. 바꾸려면 연결을 먼저 해제해 주세요.")
    if status == "taken":
        raise HTTPException(status_code=409, detail="다른 멤버가 라이엇 로그인으로 인증한 계정입니다.")
    return {"status": "ok", "account": {"game_name": player["game_name"], "tag_line": player["tag_line"], "verified": False}}


@app.delete("/api/me/riot-account")
async def unlink_my_riot_account(request: Request):
    member_id = _member_id(request)
    if not member_id:
        raise HTTPException(status_code=401, detail="디스코드 로그인이 필요합니다.")
    community_rank.unlink_account(member_id)
    return {"status": "success"}


@app.get("/api/server-ranking")
async def get_server_ranking(request: Request):
    """연결된 멤버 계정의 솔로랭크 순위 (DB 값, 하루 1회 라이엇에서 갱신) + 이번 주 MVP + 같이 한 게임 (지금 서버만)"""
    guild = _current_guild(request)
    data = community_rank.leaderboard(guild)
    best = None
    for m in data["members"]:
        d = m.get("lp_change_7d")
        if d is not None and d > 0 and (best is None or d > best["lp_change_7d"]):
            best = m
    data["mvp"] = best
    data["duos"] = community_rank.server_duos(guild_id=guild)["duos"]
    return data


@app.get("/logout")
async def member_logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(member_auth.SESSION_COOKIE)
    return resp


# 생성(난수) 데이터 API는 2026-10-25에 삭제했다. 화면의 옛 생성 기능 UI를 숨기는 플래그만 남긴다
# (templates/index.html 의 synthetic_features, JS 의 window.SYNTHETIC_FEATURES).
SYNTHETIC_FEATURES_ENABLED = os.getenv("SYNTHETIC_FEATURES", "0").strip() == "1"

# 2. 성능 지표 및 응답 헤더 미들웨어 (모든 요청의 실제 처리 시간을 밀리초 단위로 기록 및 브라우저 캐시 헤더 주입)
@app.middleware("http")
async def add_performance_and_headers(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"
    response.headers["X-Engine"] = "FastAPI + SQLite WAL Tuned"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    path = request.url.path
    if path.startswith("/static/"):
        if path.endswith("/sw.js") or path.endswith("/service-worker.js"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        else:
            response.headers["Cache-Control"] = "public, max-age=86400"
    elif path.startswith("/api/"):
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache"
    return response

@app.middleware("http")
async def block_admin_on_public_port(request: Request, call_next):
    # 관리자 화면·API는 관리자 포트(127.0.0.1 전용)에서만 연다. 공개 포트에서는 존재하지 않는 것처럼 404.
    path = request.url.path
    if (path == "/admin" or path.startswith(("/admin/", "/api/admin/"))) and not is_admin_port(request):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return await call_next(request)

def _static_version() -> int:
    """CSS·JS 주소 뒤 ?v= 값: 정적 파일이 바뀔 때만 바뀐다 (예전엔 매 요청 시각이라 방문할 때마다 1.7MB 를 다시 받았다)"""
    newest = 0.0
    for p in (BASE_DIR / "static").rglob("*"):
        if p.is_file() and p.suffix in (".js", ".css"):
            newest = max(newest, p.stat().st_mtime)
    return int(newest)


STATIC_VERSION = _static_version()


class CachedStaticFiles(StaticFiles):
    """
    브라우저 캐싱 극대화를 위한 커스텀 정적 파일 서빙 클래스
    - 정적 에셋(CSS, JS, 이미지, 폰트 등)에 Cache-Control: public, max-age=86400 주입
    - sw.js 서비스워커 파일은 실시간 업데이트를 위해 no-cache 보장
    """
    _versioned_js_cache: Dict[str, Tuple[float, bytes]] = {}

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if path.endswith(".js") and response.status_code == 200:
            response = self._with_ddragon_version(path, response)
        if not (path.endswith("sw.js") or path.endswith("service-worker.js")):
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    def _with_ddragon_version(self, path: str, response):
        """JS 파일의 __DDRAGON_VER__ 표식을 현재 Data Dragon 버전으로 치환해 서빙 (버전 하드코딩 방지)"""
        full_path, _ = self.lookup_path(path)
        if not full_path:
            return response
        mtime = os.path.getmtime(full_path)
        cached = self._versioned_js_cache.get(full_path)
        if not cached or cached[0] != mtime:
            raw = Path(full_path).read_bytes()
            cached = (mtime, raw.replace(b"__DDRAGON_VER__", DDRAGON_VERSION.encode("ascii")))
            self._versioned_js_cache[full_path] = cached
        return Response(content=cached[1], media_type="text/javascript; charset=utf-8")

# 정적 파일 및 템플릿 마운트
app.mount("/static", CachedStaticFiles(directory=str(BASE_DIR / "static")), name="static")
# 텔레그램 메신저 수신 이미지 디렉토리 마운트
(BASE_DIR / "uploads" / "telegram").mkdir(parents=True, exist_ok=True)
# uploads/ (텔레그램으로 받은 개인 이미지)는 공개 정적 경로로 노출하지 않음
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_background_tasks = set()

@app.on_event("startup")
async def on_startup():
    init_db()
    init_community_tips_db()
    init_match_cache()
    init_ladder_table()
    init_champion_mastery_table()

    # 서버를 자주 재시작해도 매번 51회씩 호출하지 않도록, 30분 안에 갱신된 랭킹이 있으면 건너뛴다
    # 그 뒤로는 24시간마다 랭킹과 장인(숙련도) 정보를 다시 받는다 (숙련도는 24시간 안에 받은 사람은 건너뜀)
    if settings.riot_api_key:
        async def _initial_ladder_sync():
            while True:
                ladder_updated_at = load_ladder()["updated_at"] or 0
                if time.time() - ladder_updated_at > 1800:
                    try:
                        await sync_challenger_ladder()
                    except PlayerDataUnavailable:
                        pass
                    except Exception as e:
                        logger.warning("Failed ladder sync: %s", e)
                try:
                    await sync_ladder_masteries()
                except Exception as e:
                    logger.warning("Failed ladder masteries sync: %s", e)
                await asyncio.sleep(86400)
        # 이벤트 루프는 태스크를 약하게 참조하므로 끝날 때까지 참조를 들고 있어야 중간에 사라지지 않는다
        task = asyncio.create_task(_initial_ladder_sync())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    # 매치 수집기 백그라운드 태스크 (MATCH_COLLECTOR != "0")
    if os.getenv("MATCH_COLLECTOR", "1").strip() != "0":
        from app.match_collector import init_collector_tables, seed_from_ladder, collector_loop
        init_collector_tables()
        seed_from_ladder()
        collector_task = asyncio.create_task(collector_loop())
        _background_tasks.add(collector_task)
        collector_task.add_done_callback(_background_tasks.discard)

    # 서버 랭킹: 연결된 멤버 계정 랭크를 하루 1회 갱신
    if settings.riot_api_key and os.getenv("MATCH_COLLECTOR", "1").strip() != "0":
        rank_task = asyncio.create_task(community_rank.refresh_loop())
        _background_tasks.add(rank_task)
        rank_task.add_done_callback(_background_tasks.discard)

    # 마스터 이상 전체 명단 (하루 1회, 호출 3번): 수집 게임의 티어 구분용
    if settings.riot_api_key and os.getenv("MATCH_COLLECTOR", "1").strip() != "0":
        from app.apex_tiers import refresh_loop as apex_refresh_loop
        apex_task = asyncio.create_task(apex_refresh_loop())
        _background_tasks.add(apex_task)
        apex_task.add_done_callback(_background_tasks.discard)

    # 무거운 통계(티어표·홈 위젯)를 미리 계산해 두고 캐시(10분)가 끝나기 전에 다시 계산한다.
    # 첫 방문자나 만료 직후 방문자가 1~3초씩 기다리지 않게. 계산은 별도 스레드에서.
    async def _stats_warm_loop():
        from app import champion_stats as cs

        def warm():
            cs._MATCHES_MEMO.clear()
            for key in [k for k in list(cs._CACHE) if not k.startswith(("build:", "matchups:", "prevpatch:"))]:
                cs._CACHE.pop(key, None)
            for pos in ("all", "TOP", "JUG", "MID", "BOT", "SUP"):
                cs.compute_tier_list(position=pos)
                cs.compute_tier_list(position=pos, sort="tier")
            return cs.compute_patch_shift(limit=8)

        while True:
            try:
                shift = await asyncio.to_thread(warm)
                fast_cache.set("patch_shift:real", shift, ttl=600)
                fast_cache.delete("quick_op_champs:real")
                fast_cache.delete_matching("meta_board:")
                fast_cache.delete_matching("champion_analytics:")
            except Exception as e:
                logger.warning("Stats warm-up failed: %s", e)
            await asyncio.sleep(540)

    # 노출 시간이 지난 구인글의 디스코드 메시지를 '⏰ 만료'로 고친다 (10분마다)
    async def _duo_expire_loop():
        from app.duo_finder_engine import expired_posts_to_mark, mark_expired_in_discord
        from app.services.discord_service import update_duo_post_webhook
        while True:
            await asyncio.sleep(600)
            try:
                for p in await asyncio.to_thread(expired_posts_to_mark):
                    await asyncio.to_thread(update_duo_post_webhook, p, False, True)
                    await asyncio.to_thread(mark_expired_in_discord, p)
                    await asyncio.sleep(1)  # 디스코드 속도 제한 여유
            except Exception as e:
                logger.warning("Duo expire sweep failed: %s", e)

    expire_task = asyncio.create_task(_duo_expire_loop())
    _background_tasks.add(expire_task)
    expire_task.add_done_callback(_background_tasks.discard)

    warm_task = asyncio.create_task(_stats_warm_loop())
    _background_tasks.add(warm_task)
    warm_task.add_done_callback(_background_tasks.discard)

    # DB 자동 백업 (하루 1회, 최근 7개 보관). OPGG_BACKUP=0 으로 끔
    if os.getenv("OPGG_BACKUP", "1").strip() != "0":
        from app.backup import backup_loop
        backup_task = asyncio.create_task(backup_loop())
        _background_tasks.add(backup_task)
        backup_task.add_done_callback(_background_tasks.discard)


@app.on_event("shutdown")












def on_shutdown():
    sync_worker.stop()

class ApiKeyRequest(BaseModel):
    api_key: str

class CommunityTipCreate(BaseModel):
    champ1: str = Field(max_length=30)
    champ2: Optional[str] = Field(None, max_length=30)
    content: str = Field(max_length=300)
    author_name: Optional[str] = Field("익명 소환사", max_length=16)
    author_tag: Optional[str] = Field("KR1", max_length=5)
    author_tier: Optional[str] = Field("다이아몬드", max_length=10)
    position: Optional[str] = Field("ALL", max_length=10)
    category: Optional[str] = Field("lane", max_length=20)

class CommunityTipVote(BaseModel):
    vote_type: str  # "up" or "down"

@app.get("/manifest.json")
async def get_manifest():
    manifest_path = BASE_DIR / "static" / "manifest.json"
    if manifest_path.exists():
        return FileResponse(
            manifest_path,
            media_type="application/manifest+json",
            headers={"Cache-Control": "public, max-age=3600"}
        )
    raise HTTPException(status_code=404, detail="Manifest not found")

@app.get("/sw.js")
@app.get("/service-worker.js")
async def get_service_worker():
    sw_path = BASE_DIR / "static" / "sw.js"
    if sw_path.exists():
        return FileResponse(
            sw_path,
            media_type="application/javascript",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Service-Worker-Allowed": "/"
            }
        )
    raise HTTPException(status_code=404, detail="Service worker not found")

@app.get("/robots.txt", response_class=Response)
async def get_robots_txt(request: Request):
    """
    검색엔진 로봇 수집 표준 규약 (Robots.txt)
    - 상용 검색엔진(Googlebot, Yeti, Bingbot 등) 색인 허용
    - 사이트맵 위치 안내
    """
    base_url = (os.getenv("SITE_URL", "").strip() or str(request.base_url)).rstrip("/")
    if member_auth.login_enabled():
        return Response(content="User-agent: *\nDisallow: /\n", media_type="text/plain; charset=utf-8")
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"}
    )

_ADS_TXT_CACHE: Optional[str] = None

@app.get("/ads.txt", response_class=Response)
async def get_ads_txt():
    """
    구글 애드센스(Google AdSense) 및 프로그래매틱 광고 검증 표준 ads.txt 서빙
    - https://support.google.com/adsense/answer/7532444
    """
    global _ADS_TXT_CACHE
    if _ADS_TXT_CACHE is None:
        ads_file = BASE_DIR / "ads.txt"
        if ads_file.exists():
            with open(ads_file, "r", encoding="utf-8") as f:
                _ADS_TXT_CACHE = f.read()
        else:
            client_id = getattr(settings, "google_adsense_client_id", "ca-pub-0000000000000000")
            pub_id = client_id.replace("ca-", "")
            _ADS_TXT_CACHE = f"google.com, {pub_id}, DIRECT, f08c47fec0942fa0\n"

    return Response(
        content=_ADS_TXT_CACHE,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"}
    )

@app.get("/sitemap.xml", response_class=Response)
async def get_sitemap_xml(request: Request):
    """
    상용 검색엔진 최적화(SEO)를 위한 표준 Sitemap XML 동적 생성 및 서빙
    - 메인 검색, 챔피언 티어, 장인 랭킹, 래더 순위, 듀오 시너지 등 주요 탭
    - 전체 170+ 챔피언별 티어 및 장인 랭킹 상세 딥링크 포함
    """
    from datetime import date
    if member_auth.login_enabled():
        raise HTTPException(status_code=404)
    base_url = (os.getenv("SITE_URL", "").strip() or str(request.base_url)).rstrip("/")
    today_str = date.today().isoformat()

    # 주요 서비스 경로
    routes = [
        {"loc": f"{base_url}/", "changefreq": "daily", "priority": "1.0"},
        {"loc": f"{base_url}/?tab=tierlist", "changefreq": "daily", "priority": "0.9"},
        {"loc": f"{base_url}/?tab=masters", "changefreq": "daily", "priority": "0.9"},
        {"loc": f"{base_url}/?tab=leaderboard", "changefreq": "hourly", "priority": "0.9"},
        {"loc": f"{base_url}/?tab=matchup", "changefreq": "daily", "priority": "0.8"},
        {"loc": f"{base_url}/?tab=duofinder", "changefreq": "daily", "priority": "0.7"},
        {"loc": f"{base_url}/?tab=multisearch", "changefreq": "weekly", "priority": "0.7"},
        {"loc": f"{base_url}/?tab=spectator", "changefreq": "weekly", "priority": "0.7"},
    ]

    # 챔피언 빌드 주소 (/champion/ahri) 전체
    for champ in ALL_CHAMPIONS:
        champ_id = champ.get("id")
        if champ_id:
            routes.append({"loc": f"{base_url}/champion/{champ_id.lower()}", "changefreq": "daily", "priority": "0.8"})

    # 챌린저 랭커 전적 주소 (이미 조회된 실제 소환사만)
    for r in load_ladder()["results"]:
        routes.append({
            "loc": f"{base_url}/summoner/{urllib.parse.quote(r['game_name'] + '-' + r['tag_line'])}",
            "changefreq": "daily",
            "priority": "0.6",
        })

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    for r in routes:
        xml_lines.append(
            f'  <url>\n'
            f'    <loc>{r["loc"]}</loc>\n'
            f'    <lastmod>{today_str}</lastmod>\n'
            f'    <changefreq>{r["changefreq"]}</changefreq>\n'
            f'    <priority>{r["priority"]}</priority>\n'
            f'  </url>'
        )
    xml_lines.append('</urlset>')

    sitemap_xml = "\n".join(xml_lines)
    return Response(
        content=sitemap_xml,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"}
    )

class AdminLoginRequest(BaseModel):
    username: str
    password: str
    remember: Optional[bool] = False

@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
async def read_admin_console(request: Request):
    """
    개발진 & 운영진 전용 어드민 거버넌스 콘솔 대시보드
    - 최고 관리자 보안 세션 인증 (is_admin_authenticated)
    - 백엔드 제어 가능한 7대 엔지니어링 패널 전면 제공
    """
    auth = is_admin_authenticated(request)
    has_api_key = bool(settings.riot_api_key)
    masked_key = ""
    if has_api_key:
        masked_key = settings.riot_api_key[:8] + "..." + settings.riot_api_key[-4:]
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "authenticated": auth,
            "has_api_key": has_api_key,
            "masked_key": masked_key,
            "region": settings.riot_region.upper(),
            "port": request.url.port or settings.admin_port,
            "client_path": settings.lol_client_path,
            "timestamp": STATIC_VERSION,
        }
    )

@app.post("/api/admin/login")
async def admin_login(req: AdminLoginRequest, request: Request):
    """
    최고 관리자 보안 로그인 엔드포인트
    - 타이밍 부채널 공격 방어 (hmac.compare_digest 상수시간 검증)
    - IP별 연속 실패 시 일정 시간 잠금 (무차별 대입 방어)
    """
    import hmac
    # 잠금 키에 실제 수신 포트를 포함: 외부 공유 터널(모든 방문자가 127.0.0.1로 보임)로 들어온
    # 실패 시도가 관리자 전용 포트(300)의 로컬 로그인까지 잠그지 못하도록 분리
    server_port = (request.scope.get("server") or (None, None))[1]
    client_ip = f"{request.client.host if request.client else 'unknown'}:{server_port}"
    retry_after = admin_login_limiter.retry_after(client_ip)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail=f"로그인 시도가 너무 많습니다. {retry_after}초 후 다시 시도해주세요.",
            headers={"Retry-After": str(retry_after)}
        )

    valid_user = hmac.compare_digest(req.username.strip().lower(), settings.admin_username.lower())
    valid_pass = hmac.compare_digest(req.password.strip().encode("utf-8"), settings.admin_password.encode("utf-8"))
    if not (valid_user and valid_pass):
        admin_login_limiter.record_failure(client_ip)
        raise HTTPException(status_code=401, detail="관리자 아이디 또는 비밀번호가 올바르지 않습니다.")

    admin_login_limiter.reset(client_ip)
    max_age = ADMIN_SESSION_TTL if req.remember else 86400
    token = generate_admin_token(settings.admin_username, ttl=max_age)
    res = JSONResponse(content={
        "success": True,
        "message": "최고 관리자 인증에 성공하였습니다.",
        "token": token,
        "user": req.username.strip()
    })
    res.set_cookie(
        key="admin_session",
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        path="/"
    )
    return res

@app.post("/api/admin/logout")
async def admin_logout(request: Request):
    # 쿠키 삭제만으로는 복사된 토큰이 만료 전까지 유효하므로, 인증된 로그아웃이면 기존 세션 전체 폐기
    if is_admin_authenticated(request):
        revoke_all_admin_sessions()
    res = JSONResponse(content={"success": True, "message": "로그아웃되었습니다."})
    res.delete_cookie(key="admin_session", httponly=True, samesite="lax", path="/")
    return res

@app.post("/api/admin/db/optimize")
async def admin_db_optimize(request: Request):
    verify_admin_access(request)
    """
    SQLite 3 WAL VACUUM, PRAGMA wal_checkpoint 및 PRAGMA optimize 최적화 실행
    - asyncio.to_thread 비동기 워커 오프로드로 이벤트 루프 블로킹 및 레이턴시 병목 원천 차단
    """
    import sqlite3
    import app.database as database
    db_path = Path(database.DB_PATH)  # 앱이 실제로 쓰는 DB (테스트에서는 임시 DB)

    def _do_optimize():
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
        conn.execute("PRAGMA optimize")
        conn.close()

    try:
        await asyncio.to_thread(_do_optimize)
        fast_cache.delete("system:metrics")
        size_mb = round(db_path.stat().st_size / (1024 * 1024), 2)
        return {
            "success": True,
            "message": f"데이터베이스 WAL Checkpoint, VACUUM 디스크 압축 및 PRAGMA optimize 최적화가 성공적으로 완료되었습니다. (현재 DB 크기: {size_mb} MB)",
            "db_size_mb": size_mb
        }
    except Exception as e:
        return {"success": False, "message": f"최적화 중 오류: {str(e)}"}

SITE_NAME = "carry.gg"
DEFAULT_PAGE_TITLE = f"{SITE_NAME} - 롤 전적 검색 & 챔피언 티어/장인랭킹"
DEFAULT_PAGE_DESCRIPTION = (
    "리그 오브 레전드 전적 검색 사이트. 라이엇 API 실제 전적, 고티어 솔로랭크 게임으로 만든 챔피언 티어표·빌드·상성, "
    "장인 랭킹, 멀티서치, AI 코치를 한곳에서 확인하세요."
)


_BOT_UA = re.compile(r"bot|crawl|spider|slurp|headless|preview|python|curl|httpx|testclient", re.I)


def _render_index(request: Request, title: str = DEFAULT_PAGE_TITLE, description: str = DEFAULT_PAGE_DESCRIPTION,
                  canonical_path: str = "/", status_code: int = 200):
    """공개 화면. 챔피언·소환사 주소는 같은 화면에 제목·설명·대표 주소만 바꿔 준다 (검색엔진 색인용)."""
    ua = request.headers.get("user-agent", "")
    if status_code == 200 and not _BOT_UA.search(ua):
        try:
            record_page_view(request.url.path, request.client.host if request.client else "", ua)
        except Exception as e:  # 통계 실패가 화면을 막으면 안 된다
            logger.warning("traffic record failed: %s", e)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        status_code=status_code,
        context={
            "has_api_key": bool(settings.riot_api_key),
            "region": settings.riot_region.upper(),
            "timestamp": STATIC_VERSION,  # 정적 파일 버전 (템플릿의 ?v=)
            "adsense_client_id": settings.google_adsense_client_id,
            "ddragon_cdn": DDRAGON_CDN,
            "synthetic_features": SYNTHETIC_FEATURES_ENABLED,
            "page_title": title,
            "page_description": description,
            # 대표 주소는 Host 헤더가 아니라 설정값으로 (요청 헤더로 바꿀 수 있으면 검색엔진 캐시 오염 위험)
            "canonical_url": os.getenv("SITE_URL", "").strip().rstrip("/") + canonical_path,
            "member_login": member_auth.login_enabled(),
            # 디스코드 서버 이름 (예: "OO서버"). 비우면 "우리 서버"로 표시
            "community_name": communities.name_of(_current_guild(request)),
            # 들어가 있는 서버가 둘 이상이면 머리말에서 서버를 바꾼다
            "community_options": [{"id": g, "name": communities.name_of(g) or "디스코드 서버"}
                                  for g in communities.member_guilds(_member_id(request) if member_auth.login_enabled() else None)],
            "community_current": _current_guild(request),
        }
    )


@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    # 관리자 포트로 들어온 요청만 관리자 콘솔을 보여준다 (Host 헤더·?mode=admin은 누구나 조작할 수 있어 쓰지 않음)
    if is_admin_port(request):
        return await read_admin_console(request)
    return _render_index(request)


@app.get("/champion/{champ}", response_class=HTMLResponse)
async def champion_page(request: Request, champ: str):
    """챔피언 빌드 주소 (/champion/ahri). 화면은 메인과 같고 JS가 빌드 창을 연다."""
    if is_admin_port(request):
        raise HTTPException(status_code=404)
    meta = _exact_champion(urllib.parse.unquote(champ)) or _champion_hit(find_champion(urllib.parse.unquote(champ)))
    if not meta:
        return _render_index(request, title=f"챔피언을 찾을 수 없습니다 - {SITE_NAME}", status_code=404)
    build = compute_champion_build(meta["id"]) or {}
    desc = f"{meta['name']} 빌드·룬·스킬 순서·카운터. 고티어 솔로랭크 수집 게임 기준"
    if build.get("total_games"):
        desc += f" {build['total_games']:,}게임"
        if build.get("win_rate") is not None:
            desc += f", 승률 {build['win_rate']}%"
        cores = build.get("core_builds") or []
        if cores:
            desc += ", 코어 " + " · ".join(i.get("name", "") for i in cores[0].get("items", []) if i.get("name"))
    desc += "."
    return _render_index(
        request,
        title=f"{meta['name']} 빌드·룬·카운터 ({'.'.join(DDRAGON_VERSION.split('.')[:2])}) - {SITE_NAME}",
        description=desc,
        canonical_path=f"/champion/{meta['id'].lower()}",
    )


@app.get("/summoner/{riot_id}", response_class=HTMLResponse)
async def summoner_page(request: Request, riot_id: str):
    """소환사 전적 주소 (/summoner/Hide on bush-KR1). 제목은 이미 조회된 소환사만 DB에서 채운다 (라이엇 호출 없음)."""
    if is_admin_port(request):
        raise HTTPException(status_code=404)
    raw = urllib.parse.unquote(riot_id)
    name, _, tag = raw.rpartition("-")
    if not name or not tag:
        return _render_index(request, title=f"소환사를 찾을 수 없습니다 - {SITE_NAME}", status_code=404)
    canonical = "/summoner/" + urllib.parse.quote(f"{name}-{tag}")
    known = get_player_by_riot_id(name, tag)
    if known and is_riot_puuid(known.get("puuid")):
        p = public_profile(known)
        tier = p.get("display_tier") or p.get("tier") or "언랭크"
        lp = f" {p['league_points']:,}LP" if p.get("league_points") and p.get("tier") not in (None, "", "UNRANKED") else ""
        return _render_index(
            request,
            title=f"{p['game_name']}#{p['tag_line']} 전적 - {tier}{lp} | {SITE_NAME}",
            description=f"{p['game_name']}#{p['tag_line']}의 솔로랭크 {tier}{lp}, 최근 20게임 전적, 모스트 챔피언, AI 코치.",
            canonical_path=canonical,
        )
    return _render_index(
        request,
        title=f"{name}#{tag} 전적 검색 - {SITE_NAME}",
        description=f"{name}#{tag}의 리그 오브 레전드 전적, 랭크, 최근 게임을 확인하세요.",
        canonical_path=canonical,
    )

@app.get("/api/health")
async def get_health():
    """
    서버 헬스체크 및 실시간 라이엇 API 연결 상태
    """
    return {
        "status": "ok",
        "timestamp": int(time.time()),
        "has_api_key": bool(settings.riot_api_key),
        "region": settings.riot_region.upper(),
        "database": "SQLite 3 WAL"
    }

@app.get("/api/settings/status")
async def get_settings_status(request: Request):
    has_api_key = bool(settings.riot_api_key)
    show_key_hint = is_admin_authenticated(request)
    masked_key = ""
    status_info = {"valid": False, "status": "missing", "reason": "API 키가 등록되지 않았습니다."}
    is_valid = False
    status_code = "missing"
    is_expired = False
    expiry_reason = ""
    recommended_action = "none"

    if has_api_key:
        if show_key_hint:
            masked_key = settings.riot_api_key[:8] + "..." + settings.riot_api_key[-4:]
        # 런타임에서 401/403으로 이미 만료 감지된 경우 즉시 반영
        if riot_client.is_expired or rate_limiter.is_key_expired:
            is_valid = False
            status_code = "expired"
            is_expired = True
            expiry_reason = riot_client.expiry_reason or "24-hour developer key expired (401/403)"
            status_info = {"valid": False, "status": "expired", "reason": expiry_reason}
        else:
            status_info = await riot_client.verify_key()
            is_valid = status_info.get("valid", False)
            status_code = status_info.get("status", "missing")
            is_expired = has_api_key and (not is_valid) and (status_code in ["expired", "invalid", "error"])
            if is_expired:
                expiry_reason = status_info.get("reason", "24-hour developer key expired (401/403)")

    if is_expired:
        alert_level = "CRITICAL"
        recommended_action = "regenerate_key"
    elif not has_api_key:
        alert_level = "WARNING"
        recommended_action = "register_key"
    elif rate_limiter.is_circuit_broken() or rate_limiter.short_tokens < 2.0 or rate_limiter.long_tokens < 5.0:
        alert_level = "WARNING"
        recommended_action = "wait_cooldown"
    else:
        alert_level = "NORMAL"
        recommended_action = "none"

    return {
        "has_api_key": has_api_key,
        "masked_key": masked_key,
        "region": settings.riot_region.upper(),
        "routing_region": settings.riot_routing_region,
        "is_valid": is_valid,
        "status_code": status_code,
        "status_message": status_info.get("reason", ""),
        "is_expired": is_expired,
        "expiry_reason": expiry_reason or ("24-hour developer key expired (401/403)" if is_expired else ""),
        "alert_level": alert_level,
        "recommended_action": recommended_action,
        "alert_title": "Riot API 키 갱신 필요 (키 미인식 / 만료)" if is_expired else ("API 키 미등록" if not has_api_key else "정상 연결"),
        "alert_message": "라이엇 개발자 포털에서 'Regenerate API Key'를 눌렀거나 24시간이 경과하여 기존 키가 비활성화되었습니다. developer.riotgames.com 대시보드에 표시된 최신 키를 복사하여 등록해주세요." if is_expired else "",
        "portal_url": "https://developer.riotgames.com"
    }

@app.get("/api/key-status")
async def get_key_status_endpoint():
    """
    Riot API Key 만료 여부 및 실시간 상태 모니터링 엔드포인트
    - 24시간 개발자 키 만료 감지 시 프론트엔드 알람 즉시 트리거
    """
    status_dict = riot_client.get_key_status_dict()
    if rate_limiter.is_key_expired:
        status_dict["api_key_expired"] = True
        status_dict["api_key_status"] = "EXPIRED"
        status_dict["message"] = "Riot API 키가 만료되었습니다. 새 키를 등록해주세요."
        status_dict["alert_required"] = True
        if not status_dict.get("last_detected_at"):
            status_dict["last_detected_at"] = rate_limiter.expired_at

    # 프론트엔드 및 하위 호환성 필드 완벽 결합
    status_dict.update({
        "has_api_key": bool(settings.riot_api_key),
        "is_valid": not status_dict["api_key_expired"] and bool(settings.riot_api_key),
        "is_expired": status_dict["api_key_expired"],
        "expiry_reason": status_dict["message"] if status_dict["api_key_expired"] else "",
        "alert_level": "CRITICAL" if status_dict["api_key_expired"] else ("WARNING" if not settings.riot_api_key else "NORMAL"),
        "recommended_action": "regenerate_key" if status_dict["api_key_expired"] else ("register_key" if not settings.riot_api_key else "none"),
        "portal_url": "https://developer.riotgames.com"
    })
    return status_dict

@app.post("/api/settings/api-key")
async def update_api_key(payload: ApiKeyRequest, request: Request):
    verify_admin_access(request)
    key = payload.api_key.strip()
    settings.update_api_key(key)
    rate_limiter.reset_circuit()
    riot_client.reset_key_status()

    if key:
        check = await riot_client.verify_key(test_key=key)
        if not check.get("valid"):
            return {
                "success": True,
                "applied": True,
                "warning": f"키가 즉시 적용되었습니다. (라이엇 상태: {check.get('reason')})",
                "status_code": check.get("status"),
                "is_expired": True if check.get("status") in ["expired", "invalid", "error"] else False,
                "alert_level": "CRITICAL" if check.get("status") in ["expired", "invalid", "error"] else "WARNING",
                "expiry_reason": check.get("reason", "24-hour developer key expired (401/403)"),
                "recommended_action": "regenerate_key",
                "portal_url": "https://developer.riotgames.com",
                "has_api_key": True
            }

    return {
        "success": True,
        "applied": True,
        "message": "Riot API Key가 성공적으로 즉시 등록 및 적용되었습니다.",
        "has_api_key": bool(key)
    }

class LolClientPathRequest(BaseModel):
    client_path: str

@app.get("/api/settings/lol-client-path")
async def get_lol_client_path(request: Request):
    """
    LoL 클라이언트 설치 경로 조회 (로컬 PC 경로이므로 관리자 전용)
    """
    verify_admin_access(request)
    return {
        "success": True,
        "client_path": settings.lol_client_path
    }

@app.post("/api/settings/lol-client-path")
async def update_lol_client_path_endpoint(payload: LolClientPathRequest, request: Request):
    verify_admin_access(request)
    """
    LoL 클라이언트 인게임 관전 실행 경로 영구 설정 (.env 및 인메모리 Settings 반영)
    """
    path = payload.client_path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="유효한 클라이언트 경로를 입력해주세요.")
    settings.update_lol_client_path(path)
    return {
        "success": True,
        "message": f"LoL 클라이언트 설치 경로가 영구 반영되었습니다: {settings.lol_client_path}",
        "client_path": settings.lol_client_path
    }


def _champion_hit(champ: Optional[dict]) -> Optional[dict]:
    if not champ:
        return None
    return {"id": champ["id"], "name": champ["name"], "title": champ.get("title", ""),
            "image": champion_img(champ["image"])}


def _exact_champion(q: str) -> Optional[dict]:
    """검색어가 챔피언 한글명/영문 ID와 정확히 같을 때만 (소환사명 오인식 방지)"""
    clean = q.strip().lower().replace(" ", "")
    return _champion_hit(CHAMPION_MAP_BY_NAME.get(clean) or CHAMPION_MAP_BY_ID.get(clean))


@app.get("/api/search")
async def search_summoner(q: str = Query(..., min_length=1, description="닉네임 또는 닉네임#태그")):
    clean_q = q.strip()
    add_search_history(clean_q)

    # 1. 태그가 포함된 검색인 경우 (예: 'Hide on bush#KR1')
    if "#" in clean_q:
        parts = clean_q.split("#", 1)
        game_name = parts[0].strip()
        tag_line = parts[1].strip()

        try:
            player = await fetch_player(game_name, tag_line)
        except PlayerDataUnavailable as e:
            return {"mode": "not_found", "query": clean_q, "detail": e.detail, "reason_code": e.status_code}
        return {
            "mode": "exact",
            "query": clean_q,
            "source": player.get("data_source"),
            "notice": player.get("stale_reason"),
            # 프로필 API와 같은 형태 (티어 변동·숙련도 포함, 제공되지 않는 과거 시즌 값은 비움)
            "player": public_profile(player)
        }

    # 2. 태그 없이 챔피언 이름과 정확히 같으면 챔피언 빌드로 (소환사는 '이름#태그'로 검색)
    champ_hit = _exact_champion(clean_q)
    if champ_hit:
        return {"mode": "champion_build", "query": clean_q, "champion": champ_hit}

    # 3. 태그 없이 닉네임만 검색: 이전에 라이엇에서 실제로 조회된 소환사(DB) + 가장 흔한 기본 태그(KR1) 실시간 확인
    #    (과거의 '동명인 자동 생성'·'챔피언/상성 검색'은 실제 데이터가 아니어서 제거. 호출량 때문에 태그는 KR1만 시도)
    results = [p for p in search_players_by_name(clean_q, limit=200) if is_riot_puuid(p.get("puuid"))]
    known = {(p["game_name"].lower(), p["tag_line"].lower()) for p in results}
    if settings.riot_api_key and not riot_client.is_expired and (clean_q.lower(), "kr1") not in known:
        try:
            results.append(await fetch_player(clean_q, "KR1", allow_cached=False))
        except PlayerDataUnavailable:
            pass

    if not results:
        detail = f"'{clean_q}' 소환사를 찾지 못했습니다. 닉네임#태그 형식(예: Hide on bush#KR1)으로 검색해보세요."
        if not settings.riot_api_key or riot_client.is_expired:
            detail += " (현재 라이엇 API에 연결되어 있지 않아 이전에 조회된 소환사만 검색됩니다.)"
        return {"mode": "not_found", "query": clean_q, "detail": detail}

    return {
        "mode": "duplicate_list",
        "query": clean_q,
        "count": len(results),
        "results": results
    }

@app.get("/api/autocomplete")
@app.get("/api/search/autocomplete")
async def autocomplete_summoner(q: Optional[str] = Query("", description="검색 쿼리")):
    clean_q = q.strip()
    if not clean_q or clean_q.startswith("RGAPI-"):
        return {
            "query": clean_q,
            "total_count": 0,
            "results": [],
            "champion": None,
            "trending": []
        }

    # UltraFastCache 사전 직렬화(Response) 캐시 조회 (60초 TTL, 서브밀리초 응답)
    cache_key = f"autocomplete:{clean_q.lower()}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    # 자동완성은 라이엇에서 실제로 조회된 적 있는 소환사만 제안 (생성 데이터·챔피언 통계 제안 없음)
    all_results = [p for p in search_players_by_name(clean_q, limit=50) if is_riot_puuid(p.get("puuid"))]

    res = {
        "query": clean_q,
        "total_count": len(all_results),
        "count": len(all_results),
        "results": all_results,
        "champion": _champion_hit(find_champion(clean_q)),
        "matchup": None,
        "trending": []
    }



    return fast_cache.set_and_respond(cache_key, res, ttl=60)



@app.get("/api/champion-skills/{champion_name}")
async def get_champion_skills_endpoint(champion_name: str):
    """
    14.20 패치 기준 챔피언 P/Q/W/E/R 스킬 상세 정보, 쿨다운(초), 마나 소모량, 핵심 스킬 메커니즘 및 추천 스킬 콤보 가이드
    """
    clean_name = urllib.parse.unquote(champion_name).strip()
    cache_key = f"champion_skills:{clean_name.lower()}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    data = get_champion_skills_data(clean_name)
    if not data:
        raise HTTPException(status_code=404, detail=f"챔피언 '{clean_name}'의 스킬 정보를 찾을 수 없습니다.")

    return fast_cache.set_and_respond(cache_key, data, ttl=3600)

@app.get("/api/player/{game_name}/{tag_line}")
async def get_player_detail(game_name: str, tag_line: str, refresh: bool = False):
    """
    소환사 프로필 (라이엇 Account/Summoner/League API, 120초 캐시)
    """
    # 다른 엔드포인트(동기화 시 캐시 삭제)와 같은 키를 쓰도록 디코딩 후 정규화
    clean_gn = urllib.parse.unquote(game_name).strip().lower()
    clean_tag = urllib.parse.unquote(tag_line).strip().lower()
    cache_key = f"player_detail:{clean_gn}:{clean_tag}"

    if not refresh:
        cached_resp = fast_cache.get_response(cache_key)
        if cached_resp is not None:
            return cached_resp

    try:
        player = await fetch_player(game_name, tag_line)
    except PlayerDataUnavailable as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    res = {"source": player.get("data_source"), "notice": player.get("stale_reason"), "player": public_profile(player)}
    return fast_cache.set_and_respond(cache_key, res, ttl=120)

@app.post("/api/player/{game_name}/{tag_line}/sync")
async def trigger_player_sync(
    request: Request,
    game_name: str,
    tag_line: str,
    wait: bool = Query(False, description="동기화 완료까지 대기할지 여부 (True면 동기화 결과 반환, False면 큐 등록 후 비동기 202 응답)"),
    force_refresh: bool = Query(True, description="강제 새로고침 여부")
):
    """
    '전적 갱신' 버튼: 라이엇 API에서 소환사 프로필·랭크를 즉시 다시 받아오고 캐시를 비운다.
    (wait/force_refresh 파라미터는 기존 프런트 호환용으로만 남아 있음)
    """
    enforce_rate_limit(player_sync_limiter, request, "player_sync")
    clean_name = urllib.parse.unquote(game_name).strip()
    clean_tag = urllib.parse.unquote(tag_line).strip()

    # 라이엇 API에서 즉시 다시 받아온다 (실패 시 저장된 값으로 대체하지 않고 오류를 알린다)
    try:
        player = await fetch_player(clean_name, clean_tag, allow_cached=False)
    except PlayerDataUnavailable as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    fast_cache.delete_matching(f"player_detail:{clean_name.lower()}:{clean_tag.lower()}")
    fast_cache.delete_matching(f"player_matches:{clean_name.lower()}:{clean_tag.lower()}")
    return {
        "status": "completed",
        "message": f"'{player['game_name']}#{player['tag_line']}' 소환사 정보를 라이엇 API에서 새로 받아왔습니다.",
        "data": {"player": public_profile(player)}
    }


@app.get("/api/sync/status")
async def get_sync_status():
    """
    동기화 워커 상태, 큐 모니터링, 레이트 리미터 잔여 토큰 및 누적 메트릭스 조회
    """
    return sync_worker.get_status()

@app.get("/api/sync/job/{job_id}")
async def get_sync_job_status(job_id: str):
    """
    특정 동기화 작업(job_id)의 현재 상태 및 결과 조회
    """
    job = sync_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"작업 ID '{job_id}'를 찾을 수 없습니다.")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "target": f"{job.game_name}#{job.tag_line}",
        "enqueued_at": job.enqueued_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "duration": job.duration,
        "error": job.error,
        "has_result": bool(job.result),
        "result_summary": {
            "player": job.result.get("player") if job.result else None,
            "recent_matches_count": job.result.get("recent_matches_count") if job.result else 0,
            "spectator_active": job.result.get("spectator", {}).get("is_active") if job.result else False
        } if job.result else None
    }


@app.get("/api/champions")
async def list_champions(q: Optional[str] = None):
    """
    챔피언 목록 조회 및 검색 (이름 또는 영문 ID) - 초고속 인메모리 캐시 적용
    """
    clean_q = (q or "").strip().lower().replace(" ", "")
    cache_key = f"champions:{clean_q}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    if not clean_q:
        res = {"total": len(ALL_CHAMPIONS), "champions": ALL_CHAMPIONS}
    else:
        filtered = [
            c for c in ALL_CHAMPIONS
            if clean_q in c["name"].lower().replace(" ", "") or clean_q in c["id"].lower()
        ]
        res = {"total": len(filtered), "champions": filtered}

    return fast_cache.set_and_respond(cache_key, res, ttl=600)

@app.get("/api/champion-masters/most-mastered")
async def get_most_mastered_champion():
    """장인 데이터가 가장 많은 챔피언 (장인 탭 첫 화면 기본 선택용)"""
    from app.database import get_connection
    from app.champion_stats import _resolve_champion
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT champion_id, COUNT(*) n FROM champion_mastery_real GROUP BY champion_id ORDER BY n DESC LIMIT 1"
        ).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()
    champ = _resolve_champion(int(row[0])) if row else None
    return {"id": champ["id"] if champ else None, "masters": row[1] if row else 0}

@app.get("/api/champion-masters")
async def get_champion_masters_endpoint(
    champ: Optional[str] = Query(None, description="챔피언 영문ID 또는 한글이름 (예: Yasuo, 야스오)"),
    champion: Optional[str] = Query(None, description="대체 파라미터"),
    champ_id: Optional[str] = Query(None, description="대체 파라미터"),
    tier: str = Query("all", description="티어 필터 (all, apex, CHALLENGER, GRANDMASTER, MASTER, DIAMOND, EMERALD, PLATINUM, GOLD, SILVER, BRONZE, IRON, UNRANKED)"),
    sort: str = Query("games", description="정렬 기준: games (판수 내림차순) 또는 winrate (승률 내림차순)"),
    limit: int = Query(10000, ge=1, le=10000)
):
    """
    특정 챔피언에 대해 판수 또는 승률 기준 장인 소환사 랭킹 조회
    - tier='all': 전체 티어
    - tier='apex': 천상계 묶음 (챌린저, 그랜드마스터, 마스터)
    - sort='games': 판수 내림차순 (기본)
    - sort='winrate': 승률 내림차순
    """
    target = champ or champion or champ_id
    if not target:
        raise HTTPException(status_code=400, detail="챔피언 파라미터(champ 또는 champion)를 입력해주세요.")

    champ_obj = find_champion(target)
    if not champ_obj:
        raise HTTPException(status_code=404, detail=f"'{target}' 챔피언을 찾을 수 없습니다.")

    champ_id = champ_obj["id"]
    champ_name = champ_obj["name"]

    cache_key = f"champion_masters:{champ_id}:{tier}:{sort}:{limit}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    masters_data = load_champion_masters(int(champ_obj["key"]), limit=min(limit, 100))
    res = {
        "champion": {
            "id": champ_obj["id"],
            "name": champ_obj["name"],
            "image": champ_obj.get("image", f"{champ_obj['id']}.png")
        },
        "results": masters_data["results"],
        "count": masters_data["count"],
        "source": "riot_api",
        "note": ""
    }
    return fast_cache.set_and_respond(cache_key, res, ttl=600)





    res = {
        "champion": champ_obj,
        "tier_filter": tier,
        "sort_by": sort,
        "tier_counts": tier_counts,
        "count": len(masters),
        "results": masters,
        "masters": masters
    }
    return fast_cache.set_and_respond(cache_key, res, ttl=300)

@app.get("/api/champion-analytics")
@app.get("/api/champion-tier-list")
@app.get("/api/champions/tier-list")
@app.get("/api/tierlist")
@app.get("/api/tier-list")
async def get_champion_analytics(
    position: str = Query("all", description="라인 포지션: all, TOP, JUG, MID, BOT, SUP"),
    tier: str = Query("EMERALD_PLUS", description="티어: CHALLENGER, GRANDMASTER, MASTER_PLUS, DIAMOND_PLUS, EMERALD_PLUS, PLATINUM_PLUS, GOLD_PLUS, ALL_LOWER, ALL"),
    patch: str = Query("14.20", description="패치버전: 14.20, 14.19, 14.18"),
    region: str = Query("KR", description="서버 지역: KR, GLOBAL, NA, EUW"),
    sort: str = Query("tier", description="정렬 기준: tier, win_rate, pick_rate, ban_rate, games")
):
    """
    168개 전체 챔피언 라인별/티어별/패치별/지역별 랭킹 및 티어표 (OP부터 5티어까지, 승률·픽률·밴률·표본수 종합 산출)
    초고속 인메모리 캐싱 레이어 적용
    """
    cache_key = f"champion_analytics:{position}:{tier}:{patch}:{region}:{sort}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    data = compute_tier_list(position=position, sort=sort, tier=tier)
    res = dict(data)
    res["position"] = position.upper()
    res["tier"] = tier
    res["region"] = region.upper()
    res["sort_by"] = sort
    res["count"] = len(res.get("results") or [])
    return fast_cache.set_and_respond(cache_key, res, ttl=300)

    tier_list = []
    _unused = dict(


        tier=tier,
        patch=patch,
        region=region,
        sort_by=sort
    )

    op_count = sum(1 for c in tier_list if c["tier"] == "OP")
    t1_count = sum(1 for c in tier_list if c["tier"] == "1티어")
    t2_count = sum(1 for c in tier_list if c["tier"] == "2티어")
    t3_count = sum(1 for c in tier_list if c["tier"] == "3티어")
    t4_count = sum(1 for c in tier_list if c["tier"] == "4티어")
    t5_count = sum(1 for c in tier_list if c["tier"] == "5티어")
    total_games = sum(c.get("games", 0) for c in tier_list)

    res = {
        "position": position.upper(),
        "tier": tier,
        "patch": patch,
        "region": region.upper(),
        "sort_by": sort,
        "count": len(tier_list),
        "summary": {
            "op_count": op_count,
            "tier1_count": t1_count,
            "tier2_count": t2_count,
            "tier3_count": t3_count,
            "tier4_count": t4_count,
            "tier5_count": t5_count,
            "total_games": total_games
        },
        "results": tier_list
    }
    return fast_cache.set_and_respond(cache_key, res, ttl=300)

@app.get("/api/quick-op-champions")
async def get_quick_op_champions():
    """
    메인 화면 라인별 1위 챔피언 (수집된 고티어 솔로랭크 매치 기반 티어표에서 포지션별 1위)
    """
    cache_key = "quick_op_champs:real"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    positions = [
        {"position": "TOP", "pos_kr": "탑", "icon": "fa-shield"},
        {"position": "JUG", "pos_kr": "정글", "icon": "fa-paw"},
        {"position": "MID", "pos_kr": "미드", "icon": "fa-wand-magic-sparkles"},
        {"position": "BOT", "pos_kr": "원딜", "icon": "fa-crosshairs"},
        {"position": "SUP", "pos_kr": "서포터", "icon": "fa-heart"}
    ]
    champions = []
    patch = ""
    for pos_info in positions:
        lane = compute_tier_list(position=pos_info["position"])
        patch = lane.get("patch") or patch
        if lane["results"]:
            # 픽률 1% 미만은 표본이 적어 승률이 튀므로 대표 1위에서 뺀다 (없으면 전체 1위)
            top_c = next((c for c in lane["results"] if c["pick_rate"] >= 1.0), lane["results"][0])
            champions.append({
                **pos_info,
                "id": top_c["id"],
                "name": top_c["name"],
                "image": top_c["image"],
                "tier": top_c["tier"],
                "win_rate": top_c["win_rate"],
                "pick_rate": top_c["pick_rate"],
                "ban_rate": top_c["ban_rate"],
                "games": top_c["games"],
            })

    res = {"patch": patch, "champions": champions, "source": "collected_matches"}
    return fast_cache.set_and_respond(cache_key, res, ttl=600)

META_BOARD_POSITIONS = ("ALL", "TOP", "JUG", "MID", "BOT", "SUP")


@app.get("/api/meta-board")
async def get_meta_board(position: str = Query("ALL", description="ALL, TOP, JUG, MID, BOT, SUP")):
    """
    메인 화면 메타 보드: 수집 매치 티어표(최소 표본 통과 챔피언)에서 승률·픽률·밴률 상위 5
    """
    pos_key = (position or "ALL").strip().upper()
    if pos_key not in META_BOARD_POSITIONS:
        raise HTTPException(status_code=400, detail="position은 ALL, TOP, JUG, MID, BOT, SUP 중 하나여야 합니다.")

    cache_key = f"meta_board:{pos_key}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    tl = compute_tier_list(position="all" if pos_key == "ALL" else pos_key)
    rows = tl.get("results") or []

    def top5(field: str) -> list:
        out, seen = [], set()
        for c in sorted(rows, key=lambda r: (r.get(field) or 0, r.get("games") or 0), reverse=True):
            # 전체 보기에서는 같은 챔피언이 여러 라인으로 나올 수 있어 한 번만 넣는다
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            out.append({
                "id": c["id"],
                "name": c["name"],
                "image": c["image"],
                "position": c.get("position"),
                "games": c["games"],
                "value": c[field],
            })
            if len(out) == 5:
                break
        return out

    res = {
        "patch": tl.get("patch") or "",
        "position": pos_key,
        "win_rate": top5("win_rate"),
        "pick_rate": top5("pick_rate"),
        "ban_rate": top5("ban_rate"),
        "sample_note": tl.get("sample_note") or "",
        "source": "collected_matches",
    }
    return fast_cache.set_and_respond(cache_key, res, ttl=600)

@app.get("/api/player/{game_name}/{tag_line}/matches")
async def get_player_matches(game_name: str, tag_line: str, count: int = Query(20, ge=5, le=30), refresh: bool = False):
    """
    소환사의 최근 20경기 상세 매치 전적 (승/패, 룬, 스펠, 아이템, 딜량 그래프, 10인 플레이어 명단)
    - UltraFastCache 사전 직렬화(Response) 캐싱 적용 (180초 TTL, 0.1ms 고속 응답 및 연산 병목 제거)
    """
    clean_name = urllib.parse.unquote(game_name).strip()
    clean_tag = urllib.parse.unquote(tag_line).strip()
    cache_key = f"player_matches:{clean_name.lower()}:{clean_tag.lower()}:{count}"

    if not refresh:
        cached_resp = fast_cache.get_response(cache_key)
        if cached_resp is not None:
            return cached_resp

    try:
        player = get_player_by_riot_id(clean_name, clean_tag)
        if not player or not is_riot_puuid(player.get("puuid")):
            player = await fetch_player(clean_name, clean_tag)
        match_data = await get_recent_matches_payload(player, count=count)
    except PlayerDataUnavailable as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return fast_cache.set_and_respond(cache_key, match_data, ttl=120)

@app.get("/api/ai-coach")
async def get_ai_coach(
    request: Request,
    name: str = Query(..., min_length=1, max_length=40, description="소환사 닉네임"),
    tag: str = Query("KR1", max_length=10, description="태그"),
):
    """
    AI 코치: 최근 랭크 게임(라이엇 실제 전적)을 같은 포지션 고티어 평균과 비교한 강점·약점·팁.
    ANTHROPIC_API_KEY 가 있으면 같은 수치로 Claude 요약을 붙인다. 30분 캐시.
    """
    clean_name = name.strip()
    clean_tag = (tag or "").strip().lstrip("#") or "KR1"
    cache_key = f"ai_coach:{clean_name.lower()}:{clean_tag.lower()}"
    cached = fast_cache.get(cache_key)
    if cached is not None:
        return cached
    enforce_rate_limit(ai_coach_limiter, request, "ai_coach")
    try:
        player = get_player_by_riot_id(clean_name, clean_tag)
        if not player or not is_riot_puuid(player.get("puuid")):
            player = await fetch_player(clean_name, clean_tag)
        match_data = await get_recent_matches_payload(player, count=20)
    except PlayerDataUnavailable as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    report = build_coach_report(public_profile(player), match_data["matches"])
    if report.get("ready") and settings.anthropic_api_key and ai_summary_daily_limiter.hit("global"):
        summary = await ai_summary(report)
        if summary:
            report["ai_summary"] = summary
            report["ai_source"] = "claude"
    fast_cache.set(cache_key, report, ttl=1800)
    return report





@app.get("/api/leaderboard")
async def get_leaderboard(
    tier: str = Query("ALL", description="티어 필터: ALL, CHALLENGER, GRANDMASTER, MASTER"),
    q: Optional[str] = Query(None, description="소환사 닉네임 검색")
):
    """
    한국 서버 솔로랭크 래더 랭킹 (1위 ~ 100위 천상계 프로 및 챌린저 랭커)
    초고속 인메모리 캐싱 및 SQLite L2 연계 (응답 속도 1~5ms 유지)
    """
    clean_q = (q or "").strip()
    # 실제 라이엇 챌린저 리그 데이터만 제공 (그랜드마스터/마스터는 아직 미지원)
    ladder = load_ladder(clean_q) if tier.upper() in ("ALL", "CHALLENGER") else {"results": [], "updated_at": None}
    # 모스트 챔피언: 수집기가 이미 모은 이 선수들의 최근 게임에서 (라이엇 추가 호출 없음, 5분 캐시)
    most_cache = fast_cache.get("leaderboard_most")
    if most_cache is None:
        most_cache = {}
        for r in ladder["results"]:
            summ = player_collected_summary(r.get("puuid"), limit=50)
            if summ:
                most_cache[r["puuid"]] = summ["top_champions"]
        fast_cache.set("leaderboard_most", most_cache, ttl=300)
    for r in ladder["results"]:
        r["most_champions"] = most_cache.get(r.get("puuid"), [])
    return {
        "tier_filter": tier,
        "query": clean_q,
        "total": len(ladder["results"]),
        "results": ladder["results"],
        "updated_at": ladder["updated_at"],
        "source": "riot_api"
    }

@app.post("/api/leaderboard/sync")
async def sync_leaderboard_api(request: Request):
    """
    Riot API 공식 엔드포인트에서 실제 한국 서버 챌린저 실시간 래더 데이터를 동기화
    - 서버 전체 5분 1회 (관리자는 제한 없음)
    """
    if not is_admin_authenticated(request) and not leaderboard_sync_limiter.hit("global"):
        raise HTTPException(status_code=429, detail="래더는 최근에 이미 갱신되었습니다. 5분 후 다시 시도해주세요.")
    try:
        return await sync_challenger_ladder()
    except PlayerDataUnavailable as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@app.get("/api/champion-build/{champ_id}")
async def get_champion_build(champ_id: str, position: Optional[str] = Query(None), tier: Optional[str] = Query(None),
                             vs: Optional[str] = Query(None)):
    """
    수집된 고티어 솔로랭크 매치 기반 룬·소환사 주문·종료 시점 코어 아이템·신발 (app/champion_stats.py)
    """
    clean_cid = champ_id.strip().lower()
    cache_key = f"champion_build:{clean_cid}:{(position or '').lower()}:{(tier or '').lower()}:{(vs or '').strip().lower()}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    build_data = compute_champion_build(urllib.parse.unquote(champ_id), position, tier, vs)
    if build_data is None:
        raise HTTPException(status_code=404, detail="챔피언을 찾을 수 없습니다.")
    return fast_cache.set_and_respond(cache_key, build_data, ttl=600)

@app.get("/api/player/{game_name}/{tag_line}/ingame")
@app.get("/api/spectator/live/{game_name}/{tag_line}")
async def get_player_ingame(game_name: str, tag_line: str):
    """
    소환사의 실시간 진행 중인 게임 (Riot Spectator-V5). 게임 중이 아니면 is_active: false.
    (과거의 '추천 경기'·'시뮬레이션' 응답은 실제 데이터가 아니어서 제거)
    """
    clean_name = urllib.parse.unquote(game_name).strip()
    clean_tag = urllib.parse.unquote(tag_line).strip()
    cache_key = f"spectator:{clean_name.lower()}:{clean_tag.lower()}"
    cached = fast_cache.get(cache_key)
    if cached:
        return cached

    try:
        player = get_player_by_riot_id(clean_name, clean_tag)
        if not player or not is_riot_puuid(player.get("puuid")):
            player = await fetch_player(clean_name, clean_tag)
        live = await fetch_live_game(player)
    except PlayerDataUnavailable as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    fast_cache.set(cache_key, live, ttl=30)
    return live


@app.get("/api/spectator/featured")
async def get_featured_spectator_matches(refresh: bool = False):
    """
    실시간 추천 게임 (Featured In-Game Live) 3개 이상 리스트 및 관전 카드 메타데이터
    - 페이커, 쵸비, 제우스, 쇼메이커 등 한국 서버 챌린저 실시간 경기
    - Riot API 레이트 리미트 보호를 위한 서버단 15초 인메모리/L2 WAL 캐시 적용 (30초 주기 호출 시 100% 캐시 히트 또는 신선 데이터 전달 보장)
    """
    cache_key = "spectator:featured_v2"
    if not refresh:
        cached_resp = fast_cache.get_response(cache_key)
        if cached_resp is not None:
            return cached_resp

    # 정식 키 전까지 라이엇 추천 게임 API가 403이라 샘플(실존 인물 이름 제거)로 보여준다
    matches = anonymize_featured(get_featured_matches())
    res = {
        "status": "success",
        "is_sample": True,
        "sample_notice": SAMPLE_NOTICE,
        "total": len(matches),
        "featured": matches,
        "auto_refresh_interval_sec": 30,
        "cache_ttl_sec": 15,
        "recommended_presets": [
            {
                "id": m["featured_id"],
                "game_name": m["star_player"],
                "tag_line": m["star_tag"],
                "title": m["star_title"],
                "pro_name_kr": m["pro_name_kr"],
                "team": m["team"],
                "tier": m["average_tier"],
                "match_badge": m["match_badge"],
                "headline": m["headline"],
                "game_id": m["game_id"],
                "champ_name": m["card_summary"]["champ_name"],
                "champ_image": m["card_summary"]["champ_image"],
                "elapsed_time_str": m["elapsed_time_str"]
            }
            for m in matches
        ]
    }
    return fast_cache.set_and_respond(cache_key, res, ttl=15)

@app.get("/api/spectator/featured/{featured_id}")
async def get_featured_spectator_match_detail(featured_id: str):
    """
    특정 추천 경기 10인 대전 상세 데이터 및 관전 실행 스크립트 조회
    - UltraFastCache 사전 직렬화(Response) 캐싱 적용 (15초 TTL)
    """
    cache_key = f"spectator:match_detail:{featured_id.lower().strip()}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    match = next((m for m in anonymize_featured(get_featured_matches()) if m.get("featured_id") == featured_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="추천 실시간 경기를 찾을 수 없습니다.")
    return fast_cache.set_and_respond(cache_key, match, ttl=15)

@app.get("/api/spectator/script/{game_id}")
async def get_spectator_launch_script_endpoint(game_id: str, encryption_key: Optional[str] = None):
    """
    라이엇 클라이언트 관전 실행 커맨드 생성기 (OP.GG / FOW.KR 동일 기능)
    - 윈도우 파워쉘 원라이너 및 배치(.bat) 스크립트
    """
    try:
        return generate_spectator_launch_script(game_id=game_id, encryption_key=encryption_key, platform_id="KR")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@app.get("/api/spectator/download-bat/{game_id}")
async def download_spectator_bat(game_id: str, encryption_key: Optional[str] = None):
    """
    라이엇 관전 배치파일 (.bat) 원클릭 다운로드
    - 사용자 PC에서 실행되는 파일이므로 game_id/encryption_key는 엔진에서 형식 검증 (명령 주입 차단)
    """
    try:
        script = generate_spectator_launch_script(game_id=game_id, encryption_key=encryption_key, platform_id="KR")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    bat_content = script["bat_script"]
    filename = f"spectator_{game_id}.bat"
    return Response(
        content=bat_content.encode("cp949", errors="replace"), # 윈도우 cmd 기본 인코딩
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

class MultiSearchRequest(BaseModel):
    raw_text: Optional[str] = ""
    summoner_names: Optional[List[str]] = None

@app.post("/api/multi-search")
@app.post("/api/multisearch")
async def multi_search(req: MultiSearchRequest):
    """
    롤 클라이언트 픽창 또는 쉼표/줄바꿈 텍스트로부터 최대 5인 팀원 실제 라이엇 데이터 일괄 조회
    """
    raw_names = []
    if req.summoner_names and len(req.summoner_names) > 0:
        raw_names = req.summoner_names
    elif req.raw_text:
        raw_names = parse_summoner_names(req.raw_text)

    parsed_targets: List[Tuple[str, str]] = []
    seen = set()
    for item in raw_names:
        if not item or not isinstance(item, str):
            continue
        s = item.strip()
        if not s:
            continue
        if "#" in s:
            parts = s.split("#", 1)
            n = parts[0].strip()
            t = parts[1].strip() or "KR1"
        else:
            n = s
            t = "KR1"
        if not n:
            continue
        dedup_key = (n.lower(), t.lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        parsed_targets.append((n, t))
        if len(parsed_targets) >= 5:
            break

    if not parsed_targets:
        return {
            "total_players": 0,
            "players": [],
            "notice": None,
            "source": "riot_api"
        }

    # 캐시 확인 (소환사 이름 조합 기반)
    sorted_key = "multisearch:" + ",".join(sorted([f"{n.lower()}#{t.lower()}" for n, t in parsed_targets]))
    cached = fast_cache.get(sorted_key)
    if cached:
        return cached

    players: List[Dict[str, Any]] = []
    notice: Optional[str] = None

    for name, tag in parsed_targets:
        try:
            player = await fetch_player(name, tag)
            p = public_profile(player)
            wins = p.get("wins") if p.get("wins") is not None else 0
            losses = p.get("losses") if p.get("losses") is not None else 0
            win_rate = p.get("win_rate")
            if win_rate is None:
                total_games = wins + losses
                win_rate = round(wins / total_games * 100, 1) if total_games > 0 else 0.0

            players.append({
                "found": True,
                "game_name": p.get("game_name"),
                "tag_line": p.get("tag_line"),
                "profile_icon_id": p.get("profile_icon_id"),
                "summoner_level": p.get("summoner_level"),
                "tier": p.get("tier"),
                "rank_tier": p.get("rank_tier"),
                "league_points": p.get("league_points"),
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "flex_tier": p.get("flex_tier"),
                "flex_rank_tier": p.get("flex_rank_tier"),
                "flex_lp": p.get("flex_lp"),
                "flex_wins": p.get("flex_wins"),
                "flex_losses": p.get("flex_losses"),
                # 수집된 고티어 게임에 있으면 최근 챔피언 (라이엇 추가 호출 없음)
                "collected": player_collected_summary(player.get("puuid")) or player_cached_summary(player.get("puuid")),
            })
        except PlayerDataUnavailable as e:
            if e.status_code == 404:
                players.append({
                    "found": False,
                    "game_name": name,
                    "tag_line": tag,
                    "error": "소환사를 찾을 수 없습니다."
                })
                continue
            else:
                notice = e.detail
                break

    result = {
        "total_players": len(players),
        "players": players,
        "notice": notice,
        "source": "riot_api"
    }
    if notice is None:
        fast_cache.set(sorted_key, result, ttl=120)
    return result

@app.get("/api/aram/tierlist")
@app.get("/api/aram-tier-list")
async def get_aram_tierlist():
    """
    칼바람 나락 (ARAM) 168명 챔피언 티어표, 승률, 픽률 및 밸런스 계수 - 초고속 캐싱
    """
    # 칼바람 통계는 솔로랭크 수집기와 별도 호출량이 필요해 정식 키 전까지 샘플로 보여준다
    cache_key = "aram:tierlist:sample"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    data = [{**c, "image": champion_img(c.get("image") or c.get("id") or "")} for c in generate_aram_tier_list()]
    res = {
        "mode": "ARAM",
        "patch": ".".join(DDRAGON_VERSION.split(".")[:2]),
        "total": len(data),
        "champions": data,
        "is_sample": True,
        "sample_notice": "샘플 데이터 (실제 수치 아님)",
    }
    return fast_cache.set_and_respond(cache_key, res, ttl=300)

@app.get("/api/duo-synergy")
async def get_duo_synergy(adc: Optional[str] = Query(None), sup: Optional[str] = Query(None)):
    """
    바텀 원딜 + 서포터 듀오 시너지 랭킹 및 궁합 분석 - 초고속 캐싱
    """
    clean_adc = (adc or "").strip().lower()
    clean_sup = (sup or "").strip().lower()
    cache_key = f"duo_synergy:{clean_adc}:{clean_sup}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    res = compute_duo_synergy("bot", adc, sup)
    return fast_cache.set_and_respond(cache_key, res, ttl=300)


@app.get("/api/duo-bot-matchups")
async def get_all_bot_duo_matchups_api():
    """수집된 고티어 솔로랭크 매치의 바텀 2:2 맞대결 (표본이 많은 순, 10분 캐시)"""
    data = compute_bot_lane_matchups(limit=12)
    return {"total": len(data["matchups"]), **data}

class ComboSynergyRequest(BaseModel):
    champ_a: str
    champ_b: str

@app.get("/api/combo-synergy-calculator")
async def get_combo_synergy_calculator_get(
    champ_a: Optional[str] = Query(None, description="챔피언 A 이름 또는 ID"),
    champ_b: Optional[str] = Query(None, description="챔피언 B 이름 또는 ID")
):
    """
    2인 챔피언 선택 시 즉각적인 콤보 시너지 분석 알고리즘 (GET 엔드포인트)
    - UltraFastCache 사전 직렬화(Response) 캐싱 적용 (300초 TTL)
    """
    if not champ_a or not champ_b:
        raise HTTPException(status_code=400, detail="champ_a와 champ_b 파라미터가 모두 필요합니다.")
    return _pair_synergy_or_404(champ_a, champ_b)


def _pair_synergy_or_404(champ_a: str, champ_b: str) -> Dict[str, Any]:
    """수집된 실제 매치 기반 두 챔피언 조합 (같은 팀 승률·기대 승률 대비·맞상대 승률)"""
    data = compute_pair_synergy(champ_a.strip(), champ_b.strip())
    if data is None:
        raise HTTPException(status_code=404, detail="챔피언을 찾을 수 없습니다.")
    return data

@app.post("/api/combo-synergy-calculator")
async def get_combo_synergy_calculator_post(req: ComboSynergyRequest):
    """
    2인 챔피언 선택 시 즉각적인 콤보 시너지 분석 알고리즘 (POST 엔드포인트)
    """
    if not req.champ_a or not req.champ_b:
        raise HTTPException(status_code=400, detail="champ_a와 champ_b가 모두 필요합니다.")
    return _pair_synergy_or_404(req.champ_a, req.champ_b)



@app.get("/api/upper-duo-synergy")
async def get_upper_duo_synergy_api(
    category: Optional[str] = Query("all", description="카테고리: mid_jug, top_jug, all"),
    champ_a: Optional[str] = Query(None, description="미드/탑 챔피언 검색"),
    champ_b: Optional[str] = Query(None, description="정글 챔피언 검색")
):
    """
    상체 듀오 시너지 랭킹 (미드+정글, 탑+정글)
    - UltraFastCache 사전 직렬화(Response) 캐싱 적용 (300초 TTL)
    """
    clean_k = f"upper_synergy:{category}:{champ_a or ''}:{champ_b or ''}"
    cached_resp = fast_cache.get_response(clean_k)
    if cached_resp is not None:
        return cached_resp

    res = {}
    if category in ["mid_jug", "all"]:
        mid = compute_duo_synergy("mid_jug", champ_a, champ_b)
        res["mid_jungle"] = mid["duos"]
        res["sample_note"] = mid["sample_note"]
    if category in ["top_jug", "all"]:
        top = compute_duo_synergy("top_jug", champ_a, champ_b)
        res["top_jungle"] = top["duos"]
        res["sample_note"] = top["sample_note"]

    return fast_cache.set_and_respond(clean_k, res, ttl=300)


@app.get("/api/patch-shift-champions")
@app.get("/api/patch-shift")
async def get_patch_shift_champions_api():
    """
    직전 패치 대비 승률이 많이 오르거나 내린 챔피언 (수집된 고티어 솔로랭크 매치, app/champion_stats.py)
    """
    from app.champion_stats import compute_patch_shift
    cache_key = "patch_shift:real"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp
    return fast_cache.set_and_respond(cache_key, compute_patch_shift(limit=8), ttl=600)

# 게임별 포지션·티어·큐는 app/duo_games.py (롤: 마스터 이상은 듀오 불가)
from app import duo_games
# Only Discord invite / channel links may be attached to user-submitted posts
DUO_LINK_PATTERN = re.compile(r"^(https://(www\.)?(discord\.gg|discord\.com|discordapp\.com)/|discord://discord\.com/)[A-Za-z0-9_\-./?=&%#]*$")

class CreateDuoPostRequest(BaseModel):
    game: Optional[str] = Field("lol", max_length=20)
    game_name: str = Field(min_length=1, max_length=16)
    tag_line: Optional[str] = Field("KR1", max_length=5)
    tier_kr: Optional[str] = Field("다이아몬드", max_length=24)
    # tier_kr 을 풀어 서버가 채운다 (보내도 덮어씀)
    tier_to: Optional[str] = None
    tier_label: Optional[str] = None
    my_position: Optional[str] = Field("ALL", max_length=40)
    target_position: Optional[str] = Field("ALL", max_length=40)
    queue_type: Optional[str] = None
    voice: Optional[bool] = True
    title: str = Field(min_length=1, max_length=60)
    description: str = Field("", max_length=500)
    discord_tag: Optional[str] = Field(None, max_length=40)
    most_champions: Optional[List[str]] = Field(None, max_length=3)
    discord_channel_name: Optional[str] = Field(None, max_length=40)
    discord_voice_url: Optional[str] = Field(None, max_length=200)
    discord_invite_url: Optional[str] = Field(None, max_length=200)
    room_name: Optional[str] = Field(None, max_length=40)
    room_link: Optional[str] = Field(None, max_length=200)
    room_status: Optional[str] = Field(None, max_length=40)
    host_mic: Optional[bool] = None
    current_members: Optional[int] = Field(1, ge=1, le=10)
    max_members: Optional[int] = Field(None, ge=1, le=10)
    is_full: Optional[bool] = False

    @field_validator("tag_line")
    @classmethod
    def _check_tag(cls, v):
        if v and not re.fullmatch(r"[0-9A-Za-z가-힣]{2,5}", v.strip()):
            raise ValueError("태그는 2~5자의 영문/숫자/한글만 가능합니다.")
        return v.strip() if v else v

    @model_validator(mode="after")
    def _check_game_fields(self):
        """게임별 허용 값 검사 (app/duo_games.py)"""
        game = duo_games.get_game(self.game)
        if not game:
            raise ValueError("지원하지 않는 게임입니다.")
        self.game = (self.game or duo_games.DEFAULT_GAME).strip().lower()
        aliases = {"JUNGLE": "JUG", "ADC": "BOT", "SUPPORT": "SUP"} if self.game == "lol" else {}
        codes = duo_games.position_codes(self.game)
        if self.queue_type:
            # 줄임말(솔랭·자랭·롤체·증칼)도 받는다
            self.queue_type = duo_games.parse_queue(game, self.queue_type) or self.queue_type
        queue = self.queue_type or game["queues"][0]
        no_pos = queue in (game.get("no_position_queues") or [])
        for field in ("my_position", "target_position"):
            # 여러 포지션은 "TOP,JUG" 처럼 쉼표로 (게임 정의 순서로 정리, 중복 제거)
            picked = {aliases.get(x, x) for x in (getattr(self, field) or "ALL").upper().replace(" ", "").split(",") if x}
            if "ALL" in picked or not picked or no_pos:
                v = "ALL"
            else:
                if not picked <= codes:
                    raise ValueError("올바르지 않은 포지션입니다.")
                v = ",".join(code for code, _ in game["positions"] if code in picked)
            if self.game == "lol" and field == "my_position" and v == "ALL" and not no_pos:
                raise ValueError("내 포지션을 선택해 주세요.")
            setattr(self, field, v)
        # 티어는 '다이아1'·'에2'·'브~다' 처럼 줄임말·단계·범위로도 받는다 (duo_games.parse_tier)
        tier_info = duo_games.parse_tier(game, self.tier_kr) if self.tier_kr else None
        if self.tier_kr and not tier_info:
            raise ValueError("티어를 알아보지 못했어요. 예: 다이아1, 에2, 골드, 브~다")
        self.queue_type = self.queue_type or game["queues"][0]
        if self.queue_type not in game["queues"]:
            raise ValueError("올바르지 않은 큐 종류입니다.")
        if tier_info:
            self.tier_kr, self.tier_to, self.tier_label = tier_info["tier_kr"], tier_info["tier_to"], tier_info["label"]
            if set(tier_info["tiers"]) & set((game.get("no_duo_tiers") or {}).get(self.queue_type, [])):
                raise ValueError("마스터 이상은 솔로랭크 듀오를 할 수 없습니다.")
        else:
            self.tier_to = self.tier_label = None
        span = (game.get("adjustable_party") or {}).get(self.queue_type)
        if span and self.max_members is not None and not span[0] <= self.max_members <= span[1]:
            raise ValueError(f"최대 인원은 {span[0]}~{span[1]}명으로 정해 주세요.")
        if not span and self.max_members is not None and self.max_members < 2:
            raise ValueError("최대 인원은 2명 이상이어야 합니다.")
        if not self.tier_kr:
            self.tier_kr = game.get("default_tier") or game["tiers"][0]
        return self

    @field_validator("discord_voice_url", "discord_invite_url", "room_link")
    @classmethod
    def _check_link(cls, v):
        if v and not DUO_LINK_PATTERN.match(v.strip()):
            raise ValueError("디스코드 링크(discord.gg / discord.com)만 등록할 수 있습니다.")
        return v.strip() if v else v

# ---------------------------------------------------------------------------
# 디스코드 봇 전용 (scripts/discord_bot.py): 봇이 멤버 대신 구인글을 쓰고 참가한다.
# BOT_API_SECRET 이 서버와 봇에 같은 값으로 있어야 하고, 없으면 이 경로들은 꺼져 있다.
# ---------------------------------------------------------------------------
bot_action_limiter = SlidingWindowLimiter(max_events=6, window_sec=60)
# 내전 진행(여러 방 저장·대회 경기 시작·결과)은 주최자 한 명이 연달아 누르므로 따로 넉넉하게
bot_inhouse_limiter = SlidingWindowLimiter(max_events=60, window_sec=60)


def _verify_bot(request: Request) -> None:
    if len(os.getenv("BOT_API_SECRET", "").strip()) < 16:
        raise HTTPException(status_code=503, detail="디스코드 봇 연동이 설정되지 않았습니다.")
    if not _bot_secret_ok(request):
        raise HTTPException(status_code=403, detail="봇 인증 실패")


class BotMember(BaseModel):
    discord_id: str = Field(min_length=1, max_length=32, pattern=r"^\d+$")
    discord_name: str = Field(min_length=1, max_length=32)
    # 명령을 쓴 디스코드 서버 (여러 서버 지원). 등록되지 않은 서버면 거절
    guild_id: Optional[str] = Field(default=None, max_length=32, pattern=r"^\d+$")


def _bot_guild(member: BotMember) -> str:
    """봇 명령이 온 서버 → 저장할 서버 ID. 그 서버 멤버로도 기록해 둔다"""
    gid = communities.resolve(member.guild_id)
    if gid is None:
        raise HTTPException(status_code=403, detail="이 디스코드 서버는 carry.gg에 등록되지 않았어요. 관리자에게 문의해 주세요.")
    if gid:
        community_rank.add_member_guild(member.discord_id, gid)
    return gid


class BotCreatePost(CreateDuoPostRequest):
    member: BotMember


class BotRegisterRiotAccountRequest(RegisterRiotAccountRequest):
    member: BotMember


@app.post("/api/bot/riot-account")
async def bot_register_riot_account(req: BotRegisterRiotAccountRequest, request: Request):
    """봇 /계정등록 닉네임#태그 (웹 닉네임 등록과 같음)"""
    _verify_bot(request)
    _bot_rate(req.member)
    _bot_guild(req.member)
    community_rank.remember_member(req.member.discord_id, req.member.discord_name)
    return await _register_riot_account(req.member.discord_id, req)


def _bot_rate(member: BotMember, limiter: Optional[SlidingWindowLimiter] = None) -> None:
    # 봇은 한 곳(IP)에서 오므로 IP가 아니라 디스코드 사용자별로 제한
    if not (limiter or bot_action_limiter).hit(f"bot:{member.discord_id}"):
        raise HTTPException(status_code=429, detail="잠시 후 다시 시도해주세요.")


@app.post("/api/bot/duo-posts")
async def bot_create_post(req: BotCreatePost, request: Request):
    _verify_bot(request)
    _bot_rate(req.member)
    guild = _bot_guild(req.member)
    await _check_recruit_identity(req, req.member.discord_id)
    res = _create_recruit_post(req, req.member.discord_name, owner_key=f"member:{req.member.discord_id}", guild_id=guild)
    res.pop("owner_token", None)  # 봇 글은 웹 작성자 토큰이 필요 없음
    return res


class BotAlertRoleRequest(BaseModel):
    member: BotMember
    game: str = Field(default="lol", pattern="^(lol|pubg|overwatch)$")
    role_id: Optional[str] = Field(default=None, max_length=32, pattern=r"^\d+$")  # 비우면 알림 끔


@app.post("/api/bot/alert-role")
async def bot_set_alert_role(req: BotAlertRoleRequest, request: Request):
    """구인 알림 역할 정하기 (봇 /알림역할 — 디스코드에서 '서버 관리' 권한이 있는 사람만 보이는 명령)"""
    _verify_bot(request)
    _bot_rate(req.member)
    gid = _bot_guild(req.member)
    communities.set_alert_role(gid, req.game, req.role_id)
    return {"status": "ok", "roles": communities.alert_role_ids(gid)}


@app.get("/api/bot/alert-role")
async def bot_get_alert_role(request: Request, guild_id: str = Query("", max_length=32, pattern=r"^\d*$")):
    """봇 /알림받기 가 붙였다 뗄 역할"""
    _verify_bot(request)
    gid = communities.resolve(guild_id)
    if gid is None:
        raise HTTPException(status_code=403, detail="등록되지 않은 디스코드 서버입니다.")
    return {"roles": communities.alert_role_ids(gid)}


@app.get("/api/bot/tier-roles")
async def bot_tier_roles(request: Request, guild_id: str = Query("", max_length=32, pattern=r"^\d*$")):
    """티어 역할 자동 부여: 이 서버 멤버의 인증 계정 솔로랭크 티어 (라이엇 호출 없음, 저장된 값)"""
    _verify_bot(request)
    gid = communities.resolve(guild_id)
    if gid is None:
        raise HTTPException(status_code=403, detail="등록되지 않은 디스코드 서버입니다.")
    return {"members": community_rank.guild_member_tiers(gid), "role_map": communities.tier_role_map(gid)}


class BotTierRoleMapRequest(BaseModel):
    member: BotMember
    # 티어 코드 → 역할 ID (전체를 바꾼다, 빠진 티어는 연결 해제)
    roles: Dict[str, Optional[str]] = Field(default_factory=dict, max_length=10)


@app.post("/api/bot/tier-role-map")
async def bot_set_tier_role_map(req: BotTierRoleMapRequest, request: Request):
    """서버마다 이미 있는 역할을 티어에 연결 (봇 /티어역할 연결·자동연결, '역할 관리' 권한자만 보이는 명령)"""
    _verify_bot(request)
    _bot_rate(req.member)
    gid = _bot_guild(req.member)
    bad = [c for c, r in req.roles.items() if c not in communities.TIER_CODES or (r is not None and not str(r).isdigit())]
    if bad:
        raise HTTPException(status_code=422, detail="티어 코드나 역할 ID가 올바르지 않습니다.")
    return {"role_map": communities.set_tier_role_map(gid, req.roles)}


@app.post("/api/bot/duo-posts/mine")
async def bot_my_posts(member: BotMember, request: Request):
    _verify_bot(request)
    from app.duo_finder_engine import posts_owned_by, get_post, public_post
    ids = posts_owned_by(f"member:{member.discord_id}")
    return {"posts": [public_post(p) for p in (get_post(i) for i in ids) if p]}


@app.post("/api/bot/duo-posts/{post_id}/toggle")
async def bot_toggle_post(post_id: int, member: BotMember, request: Request):
    _verify_bot(request)
    _bot_rate(member)
    from app.duo_finder_engine import is_post_owner, public_post
    if not is_post_owner(post_id, f"member:{member.discord_id}"):
        raise HTTPException(status_code=403, detail="내가 올린 구인글만 바꿀 수 있어요.")
    return {"status": "ok", "post": public_post(_toggle_post(post_id))}


@app.post("/api/bot/duo-posts/{post_id}/delete")
async def bot_delete_post(post_id: int, member: BotMember, request: Request):
    _verify_bot(request)
    _bot_rate(member)
    from app.duo_finder_engine import is_post_owner
    if not is_post_owner(post_id, f"member:{member.discord_id}"):
        raise HTTPException(status_code=403, detail="내가 올린 구인글만 지울 수 있어요.")
    _delete_post(post_id)
    return {"status": "ok"}


@app.post("/api/bot/duo-posts/{post_id}/join")
async def bot_join_post(post_id: int, member: BotMember, request: Request):
    """웹사이트 디스코드 로그인과 같은 키(member:<디스코드ID>)라, 웹·디스코드 어디서 눌러도 한 번만 참가"""
    _verify_bot(request)
    _bot_rate(member)
    from app.duo_finder_engine import join_duo_post, public_post, get_post
    guild = _bot_guild(member)
    target = get_post(post_id)
    if target and not communities.same(target.get("guild_id"), guild):
        raise HTTPException(status_code=404, detail="구인글을 찾을 수 없습니다.")
    res = join_duo_post(post_id, f"member:{member.discord_id}", member.discord_name)
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail="구인글을 찾을 수 없습니다.")
    if res["status"] == "own":
        raise HTTPException(status_code=409, detail="내가 올린 구인글이에요.")
    if res["status"] == "full":
        raise HTTPException(status_code=409, detail="이미 마감된 글입니다.")
    fast_cache.delete_matching("duo_posts:")
    post = res["post"]
    if res["status"] == "ok" and post.get("discord_message_id"):
        from app.services.discord_service import update_duo_post_webhook
        asyncio.create_task(asyncio.to_thread(update_duo_post_webhook, post))
    return {"status": res["status"], "post": public_post(post)}


class InhousePlayer(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    tier: str = Field(default="UNRANKED", max_length=16)
    rank: str = Field(default="", max_length=4)
    lp: int = Field(default=0, ge=0, le=5000)
    position: Optional[str] = Field(default=None, pattern="^(TOP|JUNGLE|MID|ADC|SUPPORT)$")


class InhouseRequest(BaseModel):
    players: List[InhousePlayer] = Field(min_length=10, max_length=10)


@app.post("/api/inhouse/balance")
async def inhouse_balance(req: InhouseRequest):
    """내전 10명을 티어 합이 비슷한 두 팀으로 (저장·라이엇 호출 없음)"""
    from app import inhouse
    return inhouse.balance([p.model_dump() for p in req.players])


class BotInhouseRequest(BaseModel):
    members: List[BotMember] = Field(min_length=10, max_length=10)
    requested_by: BotMember  # 명령을 쓴 사람 (사용자별 제한)


@app.post("/api/bot/inhouse")
async def bot_inhouse(req: BotInhouseRequest, request: Request):
    """디스코드 음성 채널 10명 → 연결된 계정 티어로 팀 나누기 (연결 안 한 사람은 언랭크=추정)"""
    _verify_bot(request)
    _bot_rate(req.requested_by, bot_inhouse_limiter)
    from app import inhouse
    tiers = community_rank.member_tiers([m.discord_id for m in req.members])
    players = []
    for m in req.members:
        t = tiers.get(m.discord_id) or {}
        players.append({"name": m.discord_name, "tier": t.get("tier", "UNRANKED"), "rank": t.get("rank", ""),
                        "lp": t.get("lp", 0), "position": None, "linked": bool(t),
                        "discord_id": m.discord_id})
    return inhouse.balance(players)


# 토너먼트(8팀 7경기)는 경기마다 시작·결과·코드를 누르므로 넉넉하게
inhouse_limiter = SlidingWindowLimiter(max_events=60, window_sec=600)


class InhouseSeat(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    discord_id: Optional[str] = Field(default=None, max_length=32, pattern=r"^\d+$")


class InhouseGameRequest(BaseModel):
    blue: List[InhouseSeat] = Field(min_length=5, max_length=5)
    red: List[InhouseSeat] = Field(min_length=5, max_length=5)


class InhouseResultRequest(BaseModel):
    winner: str = Field(pattern="^(blue|red)$")


def _inhouse_result_response(status: str) -> Dict[str, Any]:
    if status == "not_found":
        raise HTTPException(status_code=404, detail="내전 기록을 찾을 수 없습니다.")
    if status == "forbidden":
        raise HTTPException(status_code=403, detail="팀을 저장한 사람만 결과를 정할 수 있습니다.")
    if status == "expired":
        raise HTTPException(status_code=409, detail="하루가 지난 기록은 바꿀 수 없습니다.")
    if status == "locked":
        raise HTTPException(status_code=409, detail="라이엇 경기 기록으로 정해진 결과는 바꿀 수 없습니다.")
    return {"status": "ok"}


@app.post("/api/inhouse/games")
async def inhouse_save_game(req: InhouseGameRequest, request: Request):
    """나눈 팀 저장 → 끝나면 /result 로 이긴 팀 기록"""
    from app import inhouse
    enforce_rate_limit(inhouse_limiter, request, "inhouse")
    _, key = _duo_joiner(request)
    gid = inhouse.record_game([x.model_dump() for x in req.blue], [x.model_dump() for x in req.red], key,
                             guild_id=_current_guild(request))
    return {"id": gid}


@app.post("/api/inhouse/games/{game_id}/result")
async def inhouse_set_result(game_id: int, req: InhouseResultRequest, request: Request):
    from app import inhouse
    enforce_rate_limit(inhouse_limiter, request, "inhouse")
    admin = is_admin_authenticated(request)
    key = "" if admin else _duo_joiner(request)[1]
    return _inhouse_result_response(inhouse.set_result(game_id, req.winner, key, is_admin=admin))


def _inhouse_owner_or_admin(game_id: int, request: Request) -> Dict[str, Any]:
    from app import inhouse
    game = inhouse.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="내전 기록을 찾을 수 없습니다.")
    if not is_admin_authenticated(request) and game["created_by"] != _duo_joiner(request)[1]:
        raise HTTPException(status_code=403, detail="팀을 저장한 사람만 할 수 있습니다.")
    return game


async def _issue_tournament_code(game: Dict[str, Any]) -> Dict[str, Any]:
    from app import inhouse, tournament
    try:
        return await tournament.create_code(game["id"], inhouse.seat_puuids(game))
    except tournament.TournamentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@app.post("/api/inhouse/games/{game_id}/code")
async def inhouse_tournament_code(game_id: int, request: Request):
    """라이엇 토너먼트 코드 발급: 클라이언트 '사설 게임 → 토너먼트 코드'에 넣으면 그 게임 결과가 자동 기록된다"""
    enforce_rate_limit(inhouse_limiter, request, "inhouse")
    return await _issue_tournament_code(_inhouse_owner_or_admin(game_id, request))


@app.post("/api/inhouse/games/{game_id}/sync")
async def inhouse_tournament_sync(game_id: int, request: Request):
    """끝난 토너먼트 코드 게임의 결과를 라이엇에서 직접 불러오기 (알림을 못 받았을 때)"""
    from app import tournament
    enforce_rate_limit(inhouse_limiter, request, "inhouse")
    _inhouse_owner_or_admin(game_id, request)
    return {"status": await tournament.fetch_result(game_id)}


tournament_callback_limiter = SlidingWindowLimiter(max_events=30, window_sec=60)


@app.post("/api/riot/tournament/callback")
async def riot_tournament_callback(request: Request):
    """라이엇 게임 종료 알림. 내용은 믿지 않고 매치를 직접 불러 우리 코드인지 확인한 뒤에만 반영"""
    from app import tournament
    enforce_rate_limit(tournament_callback_limiter, request, "tournament_callback")
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="bad payload")
    return {"status": await tournament.handle_callback(payload)}


class PlanPlayer(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    discord_id: Optional[str] = Field(default=None, max_length=32, pattern=r"^\d+$")
    tier: Optional[str] = Field(default=None, max_length=16)
    rank: Optional[str] = Field(default="", max_length=4)
    lp: Optional[int] = Field(default=0, ge=0, le=5000)
    main: Optional[str] = Field(default=None, pattern="^(TOP|JUNGLE|MID|ADC|SUPPORT)$")
    sub: Optional[str] = Field(default=None, pattern="^(TOP|JUNGLE|MID|ADC|SUPPORT)$")


class InhousePlanRequest(BaseModel):
    players: List[PlanPlayer] = Field(min_length=10, max_length=80)
    mode: str = Field(default="auto", pattern="^(auto|single|multi|tournament|league)$")
    split: str = Field(default="balanced", pattern="^(balanced|tiered)$")


inhouse_plan_limiter = SlidingWindowLimiter(max_events=20, window_sec=600)


@app.post("/api/inhouse/plan")
async def inhouse_plan(req: InhousePlanRequest, request: Request):
    """N명 팀 짜기 (app/team_builder.py): 5:5 한 판 / 여러 판 동시(균형·실력대별) / 토너먼트 / 리그. 라이엇 호출 없음"""
    from app import team_builder
    enforce_rate_limit(inhouse_plan_limiter, request, "inhouse_plan")
    try:
        return await asyncio.to_thread(team_builder.plan, [p.model_dump() for p in req.players], req.mode, req.split,
                                       _current_guild(request))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


class EventSeat(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    discord_id: Optional[str] = Field(default=None, max_length=32, pattern=r"^\d+$")
    lane: Optional[str] = Field(default=None, max_length=8)


class EventTeam(BaseModel):
    name: str = Field(default="", max_length=20)
    players: List[EventSeat] = Field(min_length=5, max_length=5)


class EventMatch(BaseModel):
    round: int = Field(default=1, ge=1, le=20)
    a: Optional[int] = Field(default=None, ge=0, le=15)
    b: Optional[int] = Field(default=None, ge=0, le=15)


class InhouseEventRequest(BaseModel):
    mode: str = Field(pattern="^(tournament|league)$")
    title: str = Field(default="", max_length=40)
    teams: List[EventTeam] = Field(min_length=2, max_length=16)
    matches: List[EventMatch] = Field(min_length=1, max_length=130)


@app.post("/api/inhouse/events")
async def inhouse_create_event(req: InhouseEventRequest, request: Request):
    """토너먼트·리그 저장 (팀·대진은 /api/inhouse/plan 결과). 만든 사람만 경기를 시작할 수 있다"""
    from app import inhouse
    enforce_rate_limit(inhouse_limiter, request, "inhouse")
    _, key = _duo_joiner(request)
    try:
        eid = inhouse.create_event(req.mode, [t.model_dump() for t in req.teams], [m.model_dump() for m in req.matches],
                                   key, guild_id=_current_guild(request), title=req.title)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"id": eid}


@app.get("/api/inhouse/events")
async def inhouse_list_events(request: Request):
    from app import inhouse
    return {"events": inhouse.recent_events(_current_guild(request))}


@app.get("/api/inhouse/events/{event_id}")
async def inhouse_get_event(event_id: int, request: Request):
    """대진표(토너먼트는 이긴 팀이 다음 라운드로)·순위표(리그)"""
    from app import inhouse
    ev = inhouse.event_view(event_id)
    if not ev or not _guild_allowed(ev.get("guild_id"), request):
        raise HTTPException(status_code=404, detail="대회를 찾을 수 없습니다.")
    ev.pop("created_by", None)
    ev.pop("guild_id", None)
    return ev


@app.post("/api/inhouse/events/{event_id}/matches/{index}/start")
async def inhouse_start_event_match(event_id: int, index: int, request: Request):
    """대진 한 경기를 내전 게임으로 열기 → 이긴 팀 기록·토너먼트 코드는 보통 내전과 같은 경로 (/api/inhouse/games/{id}/...)"""
    from app import inhouse
    enforce_rate_limit(inhouse_limiter, request, "inhouse")
    admin = is_admin_authenticated(request)
    res = inhouse.start_event_match(event_id, index, "" if admin else _duo_joiner(request)[1], is_admin=admin)
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없습니다.")
    if res["status"] == "forbidden":
        raise HTTPException(status_code=403, detail="대회를 만든 사람만 경기를 시작할 수 있습니다.")
    if res["status"] == "bye":
        raise HTTPException(status_code=409, detail="부전승 경기입니다.")
    return res


class BotInhouseEventRequest(InhouseEventRequest):
    requested_by: BotMember


class BotRequester(BaseModel):
    requested_by: BotMember


@app.post("/api/bot/inhouse/events")
async def bot_create_event(req: BotInhouseEventRequest, request: Request):
    """봇: /내전 토너먼트·리그 결과로 대회 저장 (만든 사람 = 명령을 쓴 디스코드 멤버)"""
    from app import inhouse
    _verify_bot(request)
    _bot_rate(req.requested_by, bot_inhouse_limiter)
    guild = _bot_guild(req.requested_by)
    try:
        eid = inhouse.create_event(req.mode, [t.model_dump() for t in req.teams], [m.model_dump() for m in req.matches],
                                   f"member:{req.requested_by.discord_id}", guild_id=guild, title=req.title)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"id": eid}


@app.post("/api/bot/inhouse/events/{event_id}/view")
async def bot_view_event(event_id: int, req: BotRequester, request: Request):
    """봇: 대회 진행판 (대진·승자·우승·순위). 같은 서버 대회만"""
    from app import inhouse
    _verify_bot(request)
    guild = _bot_guild(req.requested_by)
    ev = inhouse.event_view(event_id)
    if not ev or not communities.same(ev.get("guild_id"), guild):
        raise HTTPException(status_code=404, detail="대회를 찾을 수 없습니다.")
    ev["is_owner"] = ev.pop("created_by", None) == f"member:{req.requested_by.discord_id}"
    ev.pop("guild_id", None)
    return ev


@app.post("/api/bot/inhouse/events/{event_id}/matches/{index}/start")
async def bot_start_event_match(event_id: int, index: int, req: BotRequester, request: Request):
    """봇: 대진 한 경기 시작 → game_id (결과는 /api/bot/inhouse/games/{id}/result, 대회를 만든 사람만)"""
    from app import inhouse
    _verify_bot(request)
    _bot_rate(req.requested_by, bot_inhouse_limiter)
    _bot_guild(req.requested_by)
    res = inhouse.start_event_match(event_id, index, f"member:{req.requested_by.discord_id}")
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없습니다.")
    if res["status"] == "forbidden":
        raise HTTPException(status_code=403, detail="대회를 만든 사람만 경기를 시작할 수 있어요.")
    if res["status"] == "bye":
        raise HTTPException(status_code=409, detail="부전승 경기입니다.")
    return res


class BotInhousePlanRequest(BaseModel):
    members: List[BotMember] = Field(min_length=10, max_length=80)
    requested_by: BotMember
    mode: str = Field(default="auto", pattern="^(auto|single|multi|tournament|league)$")
    split: str = Field(default="balanced", pattern="^(balanced|tiered)$")


@app.post("/api/bot/inhouse/plan")
async def bot_inhouse_plan(req: BotInhousePlanRequest, request: Request):
    """봇: 음성 채널 사람들(10~80명) → 팀 짜기. 등록·인증 멤버는 저장된 티어·기록, 아니면 참가자 중간값(추정)"""
    from app import team_builder
    _verify_bot(request)
    _bot_rate(req.requested_by, bot_inhouse_limiter)
    guild = _bot_guild(req.requested_by)
    players = [{"name": m.discord_name, "discord_id": m.discord_id} for m in req.members]
    try:
        return await asyncio.to_thread(team_builder.plan, players, req.mode, req.split, guild)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/inhouse/members")
async def inhouse_member_list(request: Request):
    """내전 참가자 고르기: 이 서버에서 닉네임 등록·라이엇 인증한 멤버 (랭킹과 달리 미인증도 포함)"""
    return {"members": community_rank.inhouse_members(_current_guild(request))}


@app.get("/api/inhouse/ranking")
async def inhouse_ranking(request: Request, days: int = Query(30, ge=1, le=365)):
    """내전 순위: 내전 점수·판수·승률·KDA·모스트 (세부 기록은 /api/inhouse/players/{key}), 지금 서버 내전만"""
    from app import inhouse
    return inhouse.ranking(days=days, guild_id=_current_guild(request))


@app.get("/api/inhouse/players/{key}")
async def inhouse_player_detail(key: str, request: Request, days: int = Query(30, ge=1, le=365)):
    from app import inhouse
    detail = inhouse.player_detail(key, days=days, guild_id=_current_guild(request))
    if detail is None:
        raise HTTPException(status_code=404, detail="라이엇 경기 기록이 있는 플레이어만 세부 기록을 볼 수 있습니다.")
    return detail


@app.get("/api/inhouse/stats")
async def inhouse_stats(request: Request, days: int = Query(30, ge=1, le=365), recent: int = Query(10, ge=1, le=50)):
    from app import inhouse
    return inhouse.stats(days=days, recent=recent, guild_id=_current_guild(request))


@app.delete("/api/admin/inhouse/games/{game_id}")
async def admin_delete_inhouse_game(game_id: int, request: Request):
    """잘못 기록된 내전 삭제 (관리자 콘솔 전용)"""
    verify_admin_access(request)
    from app import inhouse
    if not inhouse.delete_game(game_id):
        raise HTTPException(status_code=404, detail="내전 기록을 찾을 수 없습니다.")
    return {"status": "ok"}


class BotInhouseGameRequest(InhouseGameRequest):
    requested_by: BotMember


class BotInhouseResultRequest(InhouseResultRequest):
    requested_by: BotMember


class BotInhouseCodeRequest(BaseModel):
    requested_by: BotMember


@app.post("/api/bot/inhouse/games/{game_id}/code")
async def bot_inhouse_tournament_code(game_id: int, req: BotInhouseCodeRequest, request: Request):
    from app import inhouse
    _verify_bot(request)
    _bot_rate(req.requested_by, bot_inhouse_limiter)
    game = inhouse.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="내전 기록을 찾을 수 없습니다.")
    if game["created_by"] != f"member:{req.requested_by.discord_id}":
        raise HTTPException(status_code=403, detail="팀을 나눈 사람만 코드를 받을 수 있어요.")
    return await _issue_tournament_code(game)


@app.post("/api/bot/inhouse/games")
async def bot_inhouse_save_game(req: BotInhouseGameRequest, request: Request):
    from app import inhouse
    _verify_bot(request)
    _bot_rate(req.requested_by, bot_inhouse_limiter)
    gid = inhouse.record_game([x.model_dump() for x in req.blue], [x.model_dump() for x in req.red],
                             f"member:{req.requested_by.discord_id}", guild_id=_bot_guild(req.requested_by))
    return {"id": gid}


@app.post("/api/bot/inhouse/games/{game_id}/result")
async def bot_inhouse_set_result(game_id: int, req: BotInhouseResultRequest, request: Request):
    from app import inhouse
    _verify_bot(request)
    _bot_rate(req.requested_by, bot_inhouse_limiter)
    return _inhouse_result_response(inhouse.set_result(game_id, req.winner, f"member:{req.requested_by.discord_id}"))


pubg_lookup_limiter = SlidingWindowLimiter(max_events=20, window_sec=600)


@app.get("/api/pubg/player")
async def pubg_player(request: Request, name: str = Query(..., min_length=2, max_length=24, pattern=r"^[A-Za-z0-9_\-]+$"),
                      platform: str = Query("kakao", pattern="^(kakao|steam)$")):
    """배그 닉네임 → 이번 시즌 경쟁전 기록 (PUBG_API_KEY 필요, 없으면 503)"""
    from app import pubg_api
    if not pubg_api.configured():
        raise HTTPException(status_code=503, detail="배그 전적 연동은 PUBG_API_KEY 설정 후 사용할 수 있습니다.")
    enforce_rate_limit(pubg_lookup_limiter, request, "pubg")
    try:
        return await pubg_api.lookup(name, platform)
    except pubg_api.PubgError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@app.get("/api/duo-games")
async def get_duo_games():
    """구인 게시판 게임별 설정 (포지션·티어·큐)"""
    return duo_games.public_config()


@app.get("/api/duo-posts")
@app.get("/api/duo/posts")
async def fetch_duo_posts(
    request: Request,
    game: Optional[str] = Query("lol"),
    position: Optional[str] = Query("ALL"),
    queue_type: Optional[str] = Query("ALL"),
    tier: Optional[str] = Query("ALL"),
    voice: Optional[str] = Query("ALL")
):
    """
    듀오 구인구직 게시글 목록 조회 (포지션, 큐, 티어, 음성채팅 실시간 필터링, 30초 고속 캐시 적용)
    🌟 회장님 특명: 방 인원이 정원초과면 자동으로 하단으로 내리고 정원 미달인 방은 상단에 우선 노출
    """
    guild = _current_guild(request)
    cache_key = f"duo_posts:{guild}:{game}:{position}:{queue_type}:{tier}:{voice}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    posts = get_duo_posts(position=position, queue_type=queue_type, tier=tier, voice=voice, game=game, guild_id=guild)
    res = {
        "total": len(posts),
        "posts": posts
    }
    return fast_cache.set_and_respond(cache_key, res, ttl=30)

@app.post("/api/duo-posts")
@app.post("/api/duo/posts")
async def add_duo_post(req: CreateDuoPostRequest, request: Request):
    """
    듀오 구인구직 새 글 등록 (디스코드 호스트 대기방 1-클릭 다이렉트 직결 연동 지원)
    - 응답의 owner_token은 작성자만 받으며, 이후 방 상태 변경 시 X-Duo-Owner-Token 헤더로 제출
    """
    enforce_rate_limit(duo_post_limiter, request, "duo")
    await _check_recruit_identity(req, _member_id(request))
    # 디스코드 로그인 멤버면 디스코드 닉네임을 글에 붙인다 (누가 올렸는지 서버 멤버가 알아보게)
    author = None
    if member_auth.login_enabled():
        mid = _member_id(request)
        member = community_rank.get_member(mid) if mid else None
        if member and member.get("discord_name"):
            author = member["discord_name"]
    # 음성방 이름은 작성자가 적은 값 대신 링크의 실제 디스코드 채널 이름 (못 받으면 일반 이름)
    link = req.discord_voice_url or req.room_link
    if req.voice and link and DUO_LINK_PATTERN.match(link):
        from app import discord_channels
        real = await discord_channels.channel_name(link)
        req.room_name = req.discord_channel_name = f"🔊 {real}" if real else "🔊 디스코드 음성방"
    return _create_recruit_post(req, author, owner_key=_duo_joiner(request)[1], guild_id=_current_guild(request))


_RIOT_ID_SEEN: Dict[str, Tuple[float, bool]] = {}  # '닉#태그' 소문자 → (확인 시각, 있음)


def _norm_riot_id(name: str, tag: str) -> str:
    return f"{''.join((name or '').split()).lower()}#{''.join((tag or '').split()).lower()}"


async def _check_recruit_identity(req: "CreateDuoPostRequest", member_id: Optional[str]) -> None:
    """롤 구인글 닉네임 검사 (2026-10-28 사용자 결정).
    - 지금: 라이엇에 실제로 있는 닉네임#태그만 (Account-V1 1회, 있음 1시간·없음 10분 기억). 키가 없거나 라이엇이 응답하지 않으면 막지 않는다.
    - RECRUIT_REQUIRE_VERIFIED=1 (Production·RSO 승인 뒤): 라이엇 로그인으로 인증한 본인 계정으로만"""
    if req.game != "lol":
        return
    name, tag = (req.game_name or "").strip(), (req.tag_line or "").strip()
    if os.getenv("RECRUIT_REQUIRE_VERIFIED", "").strip() == "1":
        member = community_rank.get_member(member_id) if member_id else None
        if not member or not member.get("verified") or not member.get("puuid"):
            raise HTTPException(status_code=403, detail="라이엇 로그인으로 계정을 인증한 멤버만 구인글을 쓸 수 있어요. 서버 랭킹 탭에서 인증해 주세요.")
        if _norm_riot_id(name, tag) != _norm_riot_id(member["game_name"], member["tag_line"]):
            raise HTTPException(status_code=403, detail=f"인증한 본인 계정({member['game_name']}#{member['tag_line']})으로만 구인글을 쓸 수 있어요.")
        return
    if not settings.riot_api_key:
        return
    key = _norm_riot_id(name, tag)
    seen = _RIOT_ID_SEEN.get(key)
    if seen and time.time() - seen[0] < (3600 if seen[1] else 600):
        exists = seen[1]
    else:
        try:
            await riot_client.get_account_by_riot_id(name, tag)
            exists = True
        except RiotAPIError as e:
            if e.status_code != 404:
                logger.warning("recruit riot id check skipped: %s", e.status_code)
                return  # 한도·키 문제로 확인 못 하면 글쓰기를 막지 않는다
            exists = False
        if len(_RIOT_ID_SEEN) > 5000:
            _RIOT_ID_SEEN.clear()
        _RIOT_ID_SEEN[key] = (time.time(), exists)
    if not exists:
        raise HTTPException(status_code=422, detail=f"라이엇에 없는 닉네임이에요: {name}#{tag} (닉네임과 태그를 확인해 주세요)")


def _create_recruit_post(req: "CreateDuoPostRequest", author: Optional[str], owner_key: str = "",
                         guild_id: str = "") -> Dict[str, Any]:
    default_max = duo_games.get_game(req.game)["party_size"].get(req.queue_type, 2)
    final_max_members = req.max_members if req.max_members is not None else default_max
    post, owner_token = create_duo_post(
        game_name=req.game_name,
        tag_line=(req.tag_line or "KR1") if duo_games.get_game(req.game)["needs_tag"] else "",
        tier_kr=req.tier_kr or "다이아몬드",
        tier_to=req.tier_to,
        tier_label=req.tier_label,
        my_position=req.my_position,
        target_position=req.target_position,
        queue_type=req.queue_type or "솔로랭크",
        voice=bool(req.voice),
        title=req.title,
        description=req.description,
        discord_tag=req.discord_tag,
        most_champions=req.most_champions,
        discord_channel_name=req.discord_channel_name or req.room_name,
        discord_voice_url=req.discord_voice_url or req.room_link,
        discord_invite_url=req.discord_invite_url,
        room_name=req.room_name or req.discord_channel_name,
        room_link=req.room_link or req.discord_voice_url,
        room_status=req.room_status,
        host_mic=req.host_mic,
        current_members=req.current_members if req.current_members is not None else 1,
        max_members=final_max_members,
        is_full=bool(req.is_full) or (req.current_members or 1) >= final_max_members,
        game=req.game,
        author=author,
        guild_id=guild_id,
    )
    if owner_key and post.get("id") is not None:
        from app.duo_finder_engine import set_post_owner
        set_post_owner(int(post["id"]), owner_key)
    fast_cache.delete_matching("duo_posts:")
    
    # 디스코드 채널(게임별 채널이 있으면 그곳)에 올리고, 나중에 마감·삭제를 반영하도록 메시지 ID를 저장
    from app.services.discord_service import duo_webhook_url
    if duo_webhook_url(post.get("game"), post.get("guild_id")):
        def _post_and_remember(p=post):
            res = send_duo_post_webhook(p)
            if res.get("message_id") and p.get("id") is not None:
                from app.duo_finder_engine import set_post_field
                set_post_field(int(p["id"]), "discord_message_id", res["message_id"])
        asyncio.create_task(asyncio.to_thread(_post_and_remember))

    return {"status": "ok", "post": post, "owner_token": owner_token}

@app.post("/api/duo-posts/{post_id}/toggle-status")
@app.post("/api/duo/posts/{post_id}/toggle-status")
async def toggle_duo_status_endpoint(post_id: int, request: Request):
    """
    방 인원 정원 초과(마감) / 정원 미달(모집 중) 상태 실시간 토글
    마감되면 자동으로 목록 하단으로 이동, 미달로 전환되면 상단으로 승격
    - 글 작성자(X-Duo-Owner-Token) 또는 관리자만 변경 가능
    """
    if not _can_manage_post(post_id, request):
        raise HTTPException(status_code=403, detail="내가 작성한 구인글만 상태를 변경할 수 있습니다.")
    post = _toggle_post(post_id)
    return {
        "status": "success",
        "post_id": post_id,
        "is_full": post.get("is_full", False),
        "current_members": post.get("current_members", 1),
        "max_members": post.get("max_members", 2),
        "room_status": post.get("room_status", ""),
        "post": post
    }

def _duo_joiner(request: Request):
    """참가자 식별: 로그인 멤버면 디스코드 ID, 로그인이 꺼진 로컬은 IP. (이름, 키)"""
    from app.rate_limit import client_ip as _client_ip
    name, key = "", _client_ip(request)
    if member_auth.login_enabled():
        mid = _member_id(request)
        if not mid:
            raise HTTPException(status_code=401, detail="디스코드 로그인이 필요합니다.")
        key = f"member:{mid}"
        name = (community_rank.get_member(mid) or {}).get("discord_name") or ""
    return name, key


@app.delete("/api/duo-posts/{post_id}")
async def delete_duo_post_endpoint(post_id: int, request: Request):
    """구인글 삭제: 작성자(X-Duo-Owner-Token) 또는 관리자만"""
    if not _can_manage_post(post_id, request):
        raise HTTPException(status_code=403, detail="내가 작성한 구인글만 삭제할 수 있습니다.")
    _delete_post(post_id)
    return {"status": "ok", "post_id": post_id}


def _can_manage_post(post_id: int, request: Request) -> bool:
    """작성자 토큰(글 쓴 브라우저) · 작성자 디스코드 멤버(다른 기기) · 관리자"""
    from app.duo_finder_engine import is_post_owner
    if verify_duo_owner(post_id, request.headers.get("X-Duo-Owner-Token", "")) or is_admin_authenticated(request):
        return True
    mid = _member_id(request) if member_auth.login_enabled() else None
    return bool(mid) and is_post_owner(post_id, f"member:{mid}")


def _toggle_post(post_id: int) -> Dict[str, Any]:
    post = toggle_duo_post_capacity(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="구인글을 찾을 수 없습니다.")
    fast_cache.delete_matching("duo_posts:")
    if post.get("discord_message_id"):
        from app.services.discord_service import update_duo_post_webhook
        asyncio.create_task(asyncio.to_thread(update_duo_post_webhook, post))
    return post


def _delete_post(post_id: int) -> None:
    from app.duo_finder_engine import delete_duo_post, get_post
    old = get_post(post_id)
    if old and old.get("discord_message_id"):
        from app.services.discord_service import update_duo_post_webhook
        asyncio.create_task(asyncio.to_thread(update_duo_post_webhook, old, True))
    if not delete_duo_post(post_id):
        raise HTTPException(status_code=404, detail="구인글을 찾을 수 없습니다.")
    fast_cache.delete_matching("duo_posts:")


@app.get("/api/duo-posts/mine")
async def my_duo_posts(request: Request):
    """로그인 멤버가 쓴 글 ID (다른 기기에서도 마감·삭제 버튼을 보이게). 로그인 기능이 꺼져 있으면 빈 목록"""
    from app.duo_finder_engine import posts_owned_by
    mid = _member_id(request) if member_auth.login_enabled() else None
    return {"ids": posts_owned_by(f"member:{mid}") if mid else []}


@app.delete("/api/duo-posts/{post_id}/join")
async def leave_duo_post_endpoint(post_id: int, request: Request):
    """참가 취소 (인원 -1, 마감이었으면 다시 모집 중)"""
    from app.duo_finder_engine import leave_duo_post, public_post
    enforce_rate_limit(discord_join_limiter, request, "duo_join")
    _, key = _duo_joiner(request)
    res = leave_duo_post(post_id, key)
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail="구인글을 찾을 수 없습니다.")
    fast_cache.delete_matching("duo_posts:")
    if res["status"] == "ok" and res["post"].get("discord_message_id"):
        from app.services.discord_service import update_duo_post_webhook
        asyncio.create_task(asyncio.to_thread(update_duo_post_webhook, res["post"]))
    return {"status": res["status"], "post": public_post(res["post"])}


@app.post("/api/duo-posts/{post_id}/join")
async def join_duo_post_endpoint(post_id: int, request: Request):
    """'같이해요': 인원 +1 (한 사람당 한 번), 정원이 차면 마감. 디스코드 채널에 참가·마감 알림"""
    from app.duo_finder_engine import join_duo_post, public_post, get_post
    enforce_rate_limit(discord_join_limiter, request, "duo_join")
    name, key = _duo_joiner(request)
    target = get_post(post_id)
    if target and not _guild_allowed(target.get("guild_id"), request):
        raise HTTPException(status_code=404, detail="구인글을 찾을 수 없습니다.")
    res = join_duo_post(post_id, key, name)
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail="구인글을 찾을 수 없습니다.")
    if res["status"] == "own":
        raise HTTPException(status_code=409, detail="내가 올린 구인글이에요.")
    if res["status"] == "full":
        raise HTTPException(status_code=409, detail="이미 마감된 글입니다.")
    post = res["post"]
    fast_cache.delete_matching("duo_posts:")
    if res["status"] == "ok" and post.get("discord_message_id"):
        from app.services.discord_service import update_duo_post_webhook
        asyncio.create_task(asyncio.to_thread(update_duo_post_webhook, post))
    # 원래 메시지가 인원을 고쳐 보여주므로, 따로 알리는 건 정원이 찼을 때만 (채널 도배 방지)
    from app.services.discord_service import duo_webhook_url
    game_hook = duo_webhook_url(post.get("game"), post.get("guild_id"))
    if res["status"] == "ok" and game_hook and (post.get("is_full") or not post.get("discord_message_id")):
        cur, mx = post.get("current_members"), post.get("max_members")
        who = name or "멤버"
        text = f"**{who}** 님이 참가했습니다 · {post.get('title', '')} ({cur}/{mx}명)"
        if post.get("is_full"):
            text += " · 🔴 마감"
        payload = {"embeds": [{"description": text, "color": 0xEF4444 if post.get("is_full") else 0x10B981}]}
        try:
            from app.services.discord_service import send_discord_webhook
            asyncio.create_task(asyncio.to_thread(send_discord_webhook, payload, game_hook))
        except Exception:
            pass
    return {"status": res["status"], "post": public_post(post)}


@app.post("/api/duo-posts/{post_id}/discord-join")
@app.post("/api/duo/posts/{post_id}/discord-join")
async def track_discord_voice_join(post_id: int, request: Request):
    """
    유저의 디스코드 1-클릭 다이렉트 음성방 입장 클릭 이벤트 로깅 및 전환율 수집 (Analytics)
    """
    enforce_rate_limit(discord_join_limiter, request, "discord_join")
    client_ip = request.client.host if request.client else "127.0.0.1"
    res = record_discord_join(post_id, client_ip=client_ip)
    fast_cache.delete("duo:discord_joins_analytics")
    return res

@app.get("/api/duo-posts/analytics/discord-joins")
async def get_discord_joins_analytics():
    """
    디스코드 1-클릭 다이렉트 음성방 입장 클릭 통계 (Analytics)
    """
    cache_key = "duo:discord_joins_analytics"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp
    stats = get_discord_join_stats()
    return fast_cache.set_and_respond(cache_key, stats, ttl=10)

@app.get("/api/tier-distribution")
@app.get("/api/tier-distribution/stats")
async def get_tier_distribution():
    """
    한국 서버 솔로랭크 전체 티어 분포도 통계 (446만 유저 전수 집계)
    - 아이언 IV부터 챌린저까지 인원수, 점유율, 누적 상위 백분위
    - 초고속 캐시 레이어로 1ms 미만 응답 속도 보장
    """
    cache_key = "tier_distribution:stats"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    # 전체 티어 분포는 모든 티어의 League-V4 목록이 필요해 정식 키 전까지 샘플로 보여준다
    data = {**get_tier_distribution_stats(), "is_sample": True,
            "sample_notice": "샘플 데이터 (실제 수치 아님)"}
    return fast_cache.set_and_respond(cache_key, data, ttl=600)

@app.get("/api/champion-matchup")
async def get_champion_matchup(
    champ1: Optional[str] = Query(None, description="첫 번째 챔피언 이름 또는 ID"),
    champ2: Optional[str] = Query(None, description="두 번째 챔피언 이름 또는 ID (생략 시 카운터 요약 반환)"),
    champion: Optional[str] = Query(None, description="첫 번째 챔피언 대체 파라미터"),
    champion_a: Optional[str] = Query(None, description="첫 번째 챔피언 대체 파라미터 (champion_a)"),
    vs: Optional[str] = Query(None, description="두 번째 상대 챔피언 대체 파라미터"),
    champion_b: Optional[str] = Query(None, description="두 번째 상대 챔피언 대체 파라미터 (champion_b)"),
    enemy: Optional[str] = Query(None, description="두 번째 상대 챔피언 대체 파라미터 (enemy)"),
    position: Optional[str] = Query(None, description="라인 포지션 (TOP, JUG, MID, BOT, SUP, ALL)"),
    category: Optional[str] = Query(None, description="커뮤니티 팁 카테고리 필터 ('lane', 'skill', 'teamfight', 'all')"),
    tier: Optional[str] = Query(None, description="소환사 티어/장인 필터 ('all', 'high_elo', 'pro_expert', 'challenger', 'master', 'diamond', 'emerald')"),
    author_tier: Optional[str] = Query(None, description="소환사 티어 필터 별칭")
):
    """
    1:1 챔피언 상대법 및 상성 매치업 분석 (솔로킬 확률, 15분 CS/골드 격차, 승률)
    """
    first_champ = champ1 or champion or champion_a
    second_champ = champ2 or vs or champion_b or enemy

    if not first_champ:
        raise HTTPException(status_code=400, detail="첫 번째 챔피언(champ1, champion, champion_a 중 하나)을 입력해주세요.")

    first_meta = find_champion(urllib.parse.unquote(first_champ).strip())
    if not first_meta:
        raise HTTPException(status_code=404, detail=f"챔피언 '{first_champ}'을(를) 찾을 수 없습니다.")

    if second_champ:
        second_meta = find_champion(urllib.parse.unquote(second_champ).strip())
        if not second_meta:
            raise HTTPException(status_code=404, detail=f"상대 챔피언 '{second_champ}'을(를) 찾을 수 없습니다.")
        data = compute_head_to_head(int(first_meta["key"]), int(second_meta["key"]))
        return {
            "mode": "head_to_head",
            **data,
        }
    else:
        data = compute_matchups(int(first_meta["key"]))
        return {
            "mode": "counters",
            **data,
        }
    """
    # REMOVED_LEGACY
    cat_clean = (category or "all").lower().strip()
    tier_clean = (tier or author_tier or "all").lower().strip()

    cache_key = f"champ_matchup_v2:{c1_clean}:{c2_clean}:{pos_clean}:{cat_clean}:{tier_clean}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    if second_champ:
        res = calculate_1v1_matchup(first_champ, second_champ, position=position)
    else:
        res = get_champion_counters_summary(first_champ, position=position)

    if res.get("status") == "error":
        raise HTTPException(status_code=404, detail=res.get("message", "챔피언을 찾을 수 없습니다."))

    # Session 9: 집단지성 커뮤니티 카운터 팁 데이터 자동 주입
    try:
        tips_data = get_community_tips(
            first_champ,
            second_champ,
            sort_by="popular",
    
            category=category,
            tier=tier or author_tier
        )
        res["community_tips"] = tips_data.get("tips", [])
        res["community_tips_total"] = tips_data.get("total", 0)
        res["community_category_counts"] = tips_data.get("category_counts", {})
        res["community_active_category"] = tips_data.get("active_category", "all")
        res["community_active_tier"] = tips_data.get("active_tier", "all")
    except Exception as e:
        res["community_tips"] = []
        res["community_tips_total"] = 0
        res["community_category_counts"] = {}
        res["community_active_category"] = "all"
    """


# Session 9: Community Counter Board (집단지성 카운터 팁 & 투표 전담 API)
@app.get("/api/community-counters")
async def get_community_counters_api(
    champ1: Optional[str] = Query(None, description="첫 번째 챔피언 이름 또는 ID"),
    champ2: Optional[str] = Query(None, description="두 번째 상대 챔피언 이름 또는 ID"),
    sort: str = Query("popular", description="정렬 기준: 'popular'(추천순) 또는 'recent'(최신순)"),
    position: Optional[str] = Query(None, description="라인 포지션 (TOP, JUG, MID, BOT, SUP, ALL)"),
    category: Optional[str] = Query(None, description="카테고리 필터: 'lane', 'skill', 'teamfight', 'all'"),
    tier: Optional[str] = Query(None, description="소환사 티어/장인 필터 ('all', 'high_elo', 'pro_expert', 'challenger', 'master', 'diamond', 'emerald')"),
    author_tier: Optional[str] = Query(None, description="소환사 티어 필터 별칭"),
    limit: int = Query(50, description="최대 조회 개수")
):
    """
    각 챔피언 매치업별 유저 집단지성 한 줄 공략 팁 및 실시간 투표 집계 조회
    - UltraFastCache 사전 직렬화(Response) 캐싱 적용 (60초 TTL, 서브밀리초 응답)
    """
    c1_c = (champ1 or "").strip().lower()
    c2_c = (champ2 or "").strip().lower()
    pos_c = (position or "ALL").strip().upper()
    cat_c = (category or "all").strip().lower()
    tier_c = (tier or author_tier or "all").strip().lower()
    cache_key = f"community_counters:{c1_c}:{c2_c}:{sort}:{pos_c}:{cat_c}:{tier_c}:{limit}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp

    try:
        data = get_community_tips(
            champ1,
            champ2,
            sort_by=sort, position=position,
    
            category=category,
            tier=tier or author_tier,
            limit=limit
        )
        return fast_cache.set_and_respond(cache_key, data, ttl=60)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"커뮤니티 팁 조회 중 오류 발생: {str(e)}")

@app.post("/api/community-counters")
async def create_community_counter_api(payload: CommunityTipCreate, request: Request):
    """
    유저가 직접 매치업 상대법 한 줄 공략 등록
    """
    enforce_rate_limit(community_tip_limiter, request, "tip")
    try:
        new_tip = add_community_tip(
            champ1=payload.champ1,
            champ2=payload.champ2,
            content=payload.content,
            author_name=payload.author_name,
            author_tag=payload.author_tag,
            author_tier=payload.author_tier,
            position=payload.position,
            category=payload.category or "lane"
        )
        # 커뮤니티 팁 및 1:1 상성 연계 캐시 즉시 일괄 무효화
        fast_cache.delete_matching("community_counters:")
        fast_cache.delete_matching("champ_matchup_v2:")
        return {
            "status": "success",
            "message": "카운터 공략 팁이 성공적으로 등록되었습니다.",
            "tip": new_tip
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"공략 등록 실패: {str(e)}")


@app.get("/api/admin/traffic")
async def get_admin_traffic(request: Request, days: int = Query(14, ge=1, le=90)):
    """관리자: 일별 페이지 조회수·순 방문자 수 (IP는 저장하지 않음)"""
    verify_admin_access(request)
    return traffic_summary(days)


@app.delete("/api/admin/community-counters/{tip_id}")
async def delete_community_counter_admin(tip_id: int, request: Request):
    """관리자: 부적절한 커뮤니티 공략 글 삭제"""
    verify_admin_access(request)
    from app.database import get_connection
    conn = get_connection()
    try:
        deleted = conn.execute("DELETE FROM community_counter_tips WHERE id = ?", (tip_id,)).rowcount
        conn.commit()
    finally:
        conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="해당 글이 없습니다.")
    return {"status": "success", "deleted": tip_id}


@app.post("/api/community-counters/{tip_id}/vote")
async def vote_community_counter_api(tip_id: int, payload: CommunityTipVote, request: Request):
    """
    카운터 공략 팁 실시간 추천(up) / 비추천(down) 투표
    """
    enforce_rate_limit(community_vote_limiter, request, "vote")
    try:
        res = vote_community_tip(tip_id=tip_id, vote_type=payload.vote_type)
        # 투표 즉각 반영을 위한 캐시 무효화
        fast_cache.delete_matching("community_counters:")
        fast_cache.delete_matching("champ_matchup_v2:")
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"투표 처리 실패: {str(e)}")


@app.get("/api/system/metrics")
async def get_system_metrics():
    """
    서버 시스템 아키텍처 및 데이터베이스 실시간 모니터링 메트릭
    - 5초 TTL UltraFastCache 인메모리 캐싱으로 반복 SQLite 테이블 카운트 부하 제거
    """
    cache_key = "system:metrics"
    cached = fast_cache.get(cache_key)
    if cached is not None:
        return cached

    db_stats = get_system_database_stats()
    has_api_key = bool(settings.riot_api_key)
    result = {
        "status": "healthy",
        "system_name": "carry.gg Production Engine",
        "timestamp": int(time.time()),
        "architecture": {
            "web_framework": "FastAPI (Async ASGI)",
            "database_engine": "SQLite 3 (WAL Mode Enabled)",
            "journal_mode": db_stats.get("journal_mode"),
            "riot_api_configured": has_api_key,
            "rate_limiter_active": True,
            "concurrency_protection": "Token Bucket & SQLite WAL Isolation"
        },
        "database_metrics": db_stats,
        "features": {
            "real_korean_summoners_enforced": True,
            "champion_masters_default_blank": True,
            "champions_hangul_sorted": True,
            "infinite_scroll_supported": True,
            "theme_toggle_supported": True,
            "ultra_fast_cache_enabled": True
        }
    }
    fast_cache.set(cache_key, result, ttl=5)
    return result

@app.get("/api/cache/stats")
async def get_cache_stats(request: Request):
    """
    Performance & Ladder Tuner 초고속 캐싱 엔진 성능 및 적중률 통계 (세션 7)
    - 캐시 키 목록에는 다른 방문자가 검색한 소환사 이름이 들어 있으므로 관리자에게만 보여준다
    """
    stats = fast_cache.get_stats()
    if not is_admin_authenticated(request):
        stats.pop("active_keys", None)
    return stats

@app.post("/api/cache/clear")
async def clear_cache_api(request: Request):
    verify_admin_access(request)
    """
    초고속 인메모리 캐시 플러시 (수동 초기화)
    """
    fast_cache.clear()
    return {"success": True, "status": "success", "message": "초고속 인메모리 캐시가 성공적으로 초기화되었습니다."}
# 디스코드(Discord) 연계 및 실시간 브로드캐스팅 API
class DiscordWebhookConfigRequest(BaseModel):
    webhook_url: str

class DiscordWebhookTestRequest(BaseModel):
    webhook_url: Optional[str] = None

class DiscordSharePlayerRequest(BaseModel):
    player: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None
    custom_msg: Optional[str] = ""

class DiscordShareMultiSearchRequest(BaseModel):
    team_summary: Optional[Dict[str, Any]] = None
    players: Optional[List[Dict[str, Any]]] = None
    summoners: Optional[List[Dict[str, Any]]] = None  # Alias 호환 지원!


@app.get("/api/settings/discord-status")
async def get_discord_status(request: Request):
    """
    디스코드 웹후크 연동 상태 및 마스킹된 URL 조회 (관리자 전용)
    """
    verify_admin_access(request)
    url = (settings.discord_webhook_url or "").strip()
    has_webhook = bool(url)
    masked_url = ""
    if has_webhook:
        if len(url) > 35:
            masked_url = url[:33] + "..." + url[-4:]
        else:
            masked_url = url[:10] + "..."
    return {
        "has_webhook": has_webhook,
        "masked_webhook": masked_url,
        "webhook_url": url if not has_webhook else masked_url
    }


@app.post("/api/settings/discord-webhook")
async def set_discord_webhook(req: DiscordWebhookConfigRequest, request: Request):
    verify_admin_access(request)
    """
    디스코드 웹후크 URL 저장 및 .env 영구 갱신
    """
    url = (req.webhook_url or "").strip()
    if url and not (url.startswith("https://discord.com/api/webhooks/") or url.startswith("https://discordapp.com/api/webhooks/")):
        raise HTTPException(status_code=400, detail="유효한 디스코드 웹후크 URL(https://discord.com/api/webhooks/...)을 입력해주세요.")
    
    settings.update_discord_webhook(url)
    return {"status": "success", "message": "디스코드 웹후크 URL이 성공적으로 저장되었습니다.", "has_webhook": bool(url)}


@app.post("/api/discord/test")
@app.post("/api/discord/webhook/test")
async def test_discord_webhook_route(request: Request, req: Optional[DiscordWebhookTestRequest] = None):
    verify_admin_access(request)
    """
    디스코드 웹후크 테스트 메시지 전송
    """
    url = (req.webhook_url if req and req.webhook_url else settings.discord_webhook_url or "").strip()
    if not url:
        return {
            "success": False,
            "message": "테스트할 디스코드 웹후크 URL이 설정되지 않았습니다.",
            "configured": False
        }
    
    res = await asyncio.to_thread(test_discord_webhook, url)
    return res


@app.post("/api/discord/share/player")
async def share_player_to_discord(req: DiscordSharePlayerRequest, request: Request):
    """
    소환사 전적 카드를 디스코드 웹후크로 전송 및 마크다운 텍스트 생성
    """
    enforce_rate_limit(discord_share_limiter, request, "share")
    player = req.player or {}
    summary = req.summary or {}
    markdown = format_player_discord_markdown(player, summary)
    webhook_res = None
    if settings.discord_webhook_url:
        webhook_res = await asyncio.to_thread(send_player_share_webhook, player, summary, req.custom_msg or "")
    
    return {
        "status": "success",
        "markdown": markdown,
        "webhook_sent": bool(webhook_res and webhook_res.get("success")),
        "webhook_result": webhook_res
    }


# 재무회계본부 (Finance & Accounting) API
@app.get("/api/finance/summary")
async def get_financial_summary_endpoint(request: Request, dau: int = Query(45000, ge=100, le=10000000)):
    """
    carry.gg 재무회계본부 월간 손익(P&L), 광고 매출, 인프라 비용 및 BEP 분석 (관리자 전용)
    - 실측 매출이 아니라 DAU·eCPM 가정으로 계산한 추정치
    """
    verify_admin_access(request)
    cache_key = f"finance:summary:{dau}"
    cached_resp = fast_cache.get_response(cache_key)
    if cached_resp is not None:
        return cached_resp
    summary = calculate_financial_summary(dau=dau)
    return fast_cache.set_and_respond(cache_key, summary, ttl=60)
# 텔레그램(Telegram) 옴니채널 메신저 & CLI 이미지 브리지 API
class TelegramConfigRequest(BaseModel):
    bot_token: Optional[str] = ""
    chat_id: Optional[str] = ""

class TelegramSendMessageRequest(BaseModel):
    text: str
    chat_id: Optional[str] = None

class TelegramSendPhotoRequest(BaseModel):
    photo_path_or_url: str
    caption: Optional[str] = ""
    chat_id: Optional[str] = None


@app.get("/api/settings/telegram-status")
async def get_telegram_status(request: Request):
    """
    텔레그램 봇 토큰 및 Chat ID 등록 상태 및 마스킹된 토큰 조회 (관리자 전용)
    """
    verify_admin_access(request)
    token = (settings.telegram_bot_token or "").strip()
    chat_id = (settings.telegram_chat_id or "").strip()
    has_token = bool(token)
    has_chat_id = bool(chat_id)
    masked_token = ""
    if has_token:
        if len(token) > 15:
            masked_token = token[:8] + "..." + token[-4:]
        else:
            masked_token = token[:4] + "..."
    return {
        "has_token": has_token,
        "has_chat_id": has_chat_id,
        "masked_token": masked_token,
        "chat_id": chat_id,
        "is_configured": has_token and has_chat_id
    }


@app.post("/api/settings/telegram-config")
async def set_telegram_config(req: TelegramConfigRequest, request: Request):
    verify_admin_access(request)
    """
    텔레그램 Bot Token 및 Chat ID 저장 및 .env 영구 갱신
    """
    settings.update_telegram_config(bot_token=req.bot_token or "", chat_id=req.chat_id or "")
    return {
        "status": "success",
        "message": "텔레그램 설정이 성공적으로 저장되었습니다.",
        "has_token": bool(settings.telegram_bot_token),
        "has_chat_id": bool(settings.telegram_chat_id)
    }


@app.post("/api/telegram/test-broadcast")
async def send_telegram_test_broadcast(request: Request):
    verify_admin_access(request)
    """
    텔레그램 운영진 테스트 브로드캐스트 전송
    """
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return {
            "success": False,
            "message": "텔레그램 봇 토큰(BOT_TOKEN) 및 챗 ID(CHAT_ID)가 설정되어 있지 않습니다.",
            "configured": False
        }
    summary_text = (
        "👑 <b>[carry.gg] 최고 운영진 거버넌스 콘솔 알림</b>\n\n"
        "⚡ <b>시스템 상태</b>: 정상 가동 (200 OK)\n"
        f"🌐 <b>일반 서비스 포트</b>: {settings.port}\n"
        f"🛡️ <b>어드민 관제 포트</b>: {settings.admin_port}\n"
        f"🔑 <b>Riot API 키 상태</b>: {'등록됨' if settings.riot_api_key else '미등록'}\n"
        f"🕒 <b>발송 시각</b>: {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    res = await asyncio.to_thread(send_telegram_message, summary_text, settings.telegram_chat_id)
    return res


@app.post("/api/telegram/send-message")
async def send_telegram_message_endpoint(req: TelegramSendMessageRequest, request: Request):
    verify_admin_access(request)
    """
    텔레그램으로 텍스트/HTML 메시지 전송
    """
    if not req.text:
        raise HTTPException(status_code=400, detail="전송할 텍스트가 없습니다.")
    res = await asyncio.to_thread(send_telegram_message, req.text, req.chat_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "텔레그램 전송 실패"))
    return res


@app.post("/api/telegram/send-photo")
async def send_telegram_photo_endpoint(req: TelegramSendPhotoRequest, request: Request):
    verify_admin_access(request)
    """
    텔레그램으로 이미지 파일 또는 URL 전송
    """
    if not req.photo_path_or_url:
        raise HTTPException(status_code=400, detail="전송할 이미지 경로 또는 URL이 없습니다.")
    res = await asyncio.to_thread(send_telegram_photo, req.photo_path_or_url, req.caption or "", req.chat_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "텔레그램 사진 전송 실패"))
    return res


@app.get("/api/telegram/photos")
async def get_telegram_photos_endpoint(request: Request, limit: int = Query(20, ge=1, le=100)):
    """
    텔레그램을 통해 CLI 작업공간으로 수신된 최근 이미지 목록 반환 (관리자 전용)
    """
    verify_admin_access(request)
    return {
        "status": "success",
        "photos": get_telegram_recent_photos(limit=limit)
    }


@app.get("/api/admin/collector/status")
async def get_admin_collector_status(request: Request):
    verify_admin_access(request)
    from app.match_collector import collector_status
    return collector_status()






