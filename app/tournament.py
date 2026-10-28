"""
라이엇 토너먼트 API (tournament-v5) — 내전용 사설 게임 코드 발급과 결과 받아 오기 (app/tournament.py)

사설 게임은 일반 전적 API(match-v5 목록)에 나오지 않는다. 라이엇이 발급한 '토너먼트 코드'로 만든 방에서 한 게임만
끝난 뒤 매치 ID를 받을 수 있고, 그 매치 상세를 한 번 불러 사람별 기록을 저장한다 (게임당 라이엇 호출 1~2회).

- RIOT_TOURNAMENT=live : 실제 코드 (라이엇이 이 앱에 토너먼트 API 사용을 승인해야 함, Production 키 필요)
- RIOT_TOURNAMENT=stub : 시험용 코드 (개발 키로 흐름만 확인, 게임 클라이언트에서는 쓸 수 없음)
- 그 외(기본) : 꺼짐 → 코드 발급 503
- 콜백: 라이엇이 게임이 끝나면 <SITE_URL>/api/riot/tournament/callback 으로 알려 준다 (프로바이더 등록 때 이 주소).
  콜백 내용은 믿지 않고, 받은 게임 ID 로 매치를 직접 불러 그 매치의 tournamentCode 가 우리 코드와 같을 때만 반영한다.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from app.database import get_connection

logger = logging.getLogger(__name__)

TOURNAMENT_HOST = "https://americas.api.riotgames.com"  # 토너먼트 API 는 지역과 관계없이 americas
CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,8}-[A-Za-z0-9-]{8,64}$")
_meta_ready = set()


def mode() -> str:
    m = os.getenv("RIOT_TOURNAMENT", "").strip().lower()
    return m if m in ("live", "stub") else ""


def _base() -> str:
    return f"{TOURNAMENT_HOST}/lol/{'tournament' if mode() == 'live' else 'tournament-stub'}/v5"


def callback_url() -> str:
    site = os.getenv("SITE_URL", "").strip().rstrip("/")
    return f"{site}/api/riot/tournament/callback" if site else ""


def _ensure_meta() -> None:
    from app import database
    key = str(database.DB_PATH)
    if key in _meta_ready:
        return
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS tournament_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()
    finally:
        conn.close()
    _meta_ready.add(key)


def _meta_get(key: str) -> Optional[str]:
    _ensure_meta()
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM tournament_meta WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _meta_set(key: str, value: str) -> None:
    _ensure_meta()
    conn = get_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO tournament_meta (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()


class TournamentError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


async def _post(path: str, body: Any, params: Optional[Dict[str, Any]] = None) -> Any:
    from app.riot_client import riot_client, RiotAPIError
    try:
        resp = await riot_client._request("POST", f"{_base()}{path}", json=body, params=params)
    except RiotAPIError as e:
        raise TournamentError(503, e.message if hasattr(e, "message") else str(e))
    if resp.status_code in (401, 403):
        raise TournamentError(503, "이 라이엇 키로는 토너먼트 API를 쓸 수 없습니다 (라이엇 승인 필요).")
    if resp.status_code == 429:
        raise TournamentError(429, "라이엇 호출 한도에 걸렸습니다. 잠시 후 다시 시도해주세요.")
    if resp.status_code != 200:
        raise TournamentError(502, f"라이엇 토너먼트 API 오류 ({resp.status_code})")
    return resp.json()


async def _tournament_id() -> int:
    """프로바이더(콜백 주소)와 토너먼트를 처음 한 번만 만들고 저장해 둔다 (모드별)"""
    m = mode()
    saved = _meta_get(f"{m}:tournament_id")
    if saved:
        return int(saved)
    provider = _meta_get(f"{m}:provider_id")
    if not provider:
        url = callback_url()
        if not url.startswith("https://") and m == "live":
            raise TournamentError(503, "SITE_URL(https 주소)이 있어야 라이엇에 결과 알림 주소를 등록할 수 있습니다.")
        provider = str(await _post("/providers", {"region": "KR", "url": url or "https://example.invalid/callback"}))
        _meta_set(f"{m}:provider_id", provider)
    community = (os.getenv("COMMUNITY_NAME", "").strip() or "carry.gg")[:40]
    tid = await _post("/tournaments", {"name": f"{community} 내전", "providerId": int(provider)})
    _meta_set(f"{m}:tournament_id", str(int(tid)))
    return int(tid)


async def create_code(game_id: int, allowed_puuids: Optional[List[str]] = None) -> Dict[str, Any]:
    """내전 게임 하나에 토너먼트 코드 1개 (5:5 소환사의 협곡, 토너먼트 드래프트). 이미 있으면 그 코드"""
    from app import inhouse
    if not mode():
        raise TournamentError(503, "라이엇 토너먼트 API가 설정되지 않았습니다 (RIOT_TOURNAMENT).")
    game = inhouse.get_game(game_id)
    if not game:
        raise TournamentError(404, "내전 기록을 찾을 수 없습니다.")
    if game.get("tournament_code"):
        return {"code": game["tournament_code"], "mode": mode()}
    body: Dict[str, Any] = {
        "mapType": "SUMMONERS_RIFT", "pickType": "TOURNAMENT_DRAFT", "spectatorType": "ALL",
        "teamSize": 5, "metadata": json.dumps({"inhouse_game": game_id}),
    }
    puuids = [p for p in (allowed_puuids or []) if p]
    if len(puuids) == 10:  # 10명 모두 인증 계정이면 그 사람들만 들어올 수 있게
        body["allowedParticipants"] = puuids
    codes = await _post("/codes", body, params={"tournamentId": await _tournament_id(), "count": 1})
    code = str((codes or [""])[0])
    if not code:
        raise TournamentError(502, "라이엇에서 코드를 받지 못했습니다.")
    inhouse.set_tournament_code(game_id, code)
    return {"code": code, "mode": mode()}


async def fetch_result(game_id: int, riot_game_id: Optional[int] = None) -> str:
    """끝난 게임의 매치를 불러 반영. 반환: ok / pending / already / mismatch / not_found"""
    from app import inhouse
    from app.riot_client import riot_client, RiotAPIError
    game = inhouse.get_game(game_id)
    if not game or not game.get("tournament_code"):
        return "not_found"
    if game.get("match_id"):
        return "already"
    code = game["tournament_code"]
    try:
        if riot_game_id is None:
            if mode() != "live":
                return "pending"
            resp = await riot_client._request("GET", f"{_base()}/games/by-code/{code}")
            games = resp.json() if resp.status_code == 200 else []
            ids = [g.get("gameId") for g in games or [] if g.get("gameId")]
            if not ids:
                return "pending"
            riot_game_id = int(ids[-1])
        match = await riot_client.get_match_detail(f"KR_{int(riot_game_id)}")
    except (RiotAPIError, ValueError):
        return "pending"
    if not match:
        return "pending"
    if ((match.get("info") or {}).get("tournamentCode") or "") != code:
        return "mismatch"  # 다른 게임 ID 를 보낸 위조 콜백 등
    return "ok" if inhouse.ingest_match(game_id, match) else "already"


async def handle_callback(payload: Dict[str, Any]) -> str:
    """라이엇 게임 종료 알림: shortCode 로 우리 게임을 찾고 gameId 로 매치를 직접 확인한다"""
    from app import inhouse
    code = str(payload.get("shortCode") or "")
    if not CODE_PATTERN.match(code):
        return "bad"
    game = inhouse.game_by_code(code)
    if not game:
        return "not_found"
    try:
        riot_game_id = int(payload.get("gameId"))
    except (TypeError, ValueError):
        return "bad"
    return await fetch_result(game["id"], riot_game_id)
