import re
import httpx
from typing import Optional, Dict, Any, List
from urllib.parse import quote
from app.config import settings

# 라이엇 ID(닉네임#태그)에 올 수 없는 문자 (경로·쿼리 구분자, 제어 문자)
RIOT_ID_FORBIDDEN = re.compile(r"[/\\?#%\x00-\x1f\x7f]")

class RiotAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"[{status_code}] {message}")

class RiotClient:
    def __init__(self):
        self._is_expired: bool = False
        self._expiry_reason: str = ""
        self._expired_at: Optional[float] = None
        self._last_checked_at: Optional[float] = None
        self._verify_cache_res: Optional[Dict[str, Any]] = None
        self._verify_cache_time: float = 0.0
        self._last_403_check: float = 0.0

    @property
    def api_key(self) -> str:
        return settings.riot_api_key

    @property
    def region(self) -> str:
        return settings.riot_region

    @property
    def routing_region(self) -> str:
        return settings.riot_routing_region

    @property
    def is_expired(self) -> bool:
        return self._is_expired

    @property
    def expiry_reason(self) -> str:
        return self._expiry_reason

    def mark_key_expired(self, reason: str = "24-hour developer key expired (401/403)"):
        """
        401/403 감지 시 즉시 키 만료 상태 플래그 설정 및 서킷 브레이커 동기화
        """
        import time
        self._is_expired = True
        self._expiry_reason = reason
        self._expired_at = time.time()
        self._last_checked_at = time.time()
        self._verify_cache_res = None
        self._verify_cache_time = 0.0
        try:
            from app.sync_automation_engine import rate_limiter
            rate_limiter.trip_circuit(reason, duration=3600.0, is_key_expired=True)
        except Exception:
            pass

    def reset_key_status(self):
        """
        새 API 키 등록 시 상태 초기화 및 서킷 브레이커 리셋
        """
        import time
        self._is_expired = False
        self._expiry_reason = ""
        self._expired_at = None
        self._last_403_check = 0.0
        self._last_checked_at = time.time()
        self._verify_cache_res = None
        self._verify_cache_time = 0.0
        try:
            from app.sync_automation_engine import rate_limiter
            rate_limiter.reset_circuit()
        except Exception:
            pass

    def get_expiry_metadata(self) -> Dict[str, Any]:
        """
        프론트엔드 및 상태 엔드포인트용 키 만료 세부 메타데이터
        """
        if self._is_expired:
            alert_level = "CRITICAL"
            recommended_action = "regenerate_key"
        elif not self.api_key:
            alert_level = "WARNING"
            recommended_action = "register_key"
        else:
            alert_level = "NORMAL"
            recommended_action = "none"

        return {
            "is_expired": self._is_expired,
            "expiry_reason": self._expiry_reason or ("24-hour developer key expired (401/403)" if self._is_expired else ""),
            "alert_level": alert_level,
            "recommended_action": recommended_action,
            "portal_url": "https://developer.riotgames.com",
            "expired_at": self._expired_at,
            "last_checked_at": self._last_checked_at
        }

    def get_key_status_dict(self) -> Dict[str, Any]:
        """
        Riot API Key 만료 여부 및 실시간 상태 모니터링 딕셔너리
        """
        if self._is_expired:
            api_key_status = "EXPIRED"
            message = "Riot API 키가 만료되었습니다. 새 키를 등록해주세요."
        elif self.api_key:
            api_key_status = "VALID"
            message = "정상 연결"
        else:
            api_key_status = "MISSING"
            message = "Riot API 키가 등록되지 않았습니다."

        return {
            "api_key_expired": self._is_expired,
            "api_key_status": api_key_status,
            "message": message,
            "last_detected_at": self._expired_at,
            "alert_required": self._is_expired,
            "portal_url": "https://developer.riotgames.com"
        }

    def _get_headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise RiotAPIError(401, "Riot API Key가 등록되지 않았습니다. 우측 상단 'API 키 설정'에서 등록해주세요.")
        return {
            "X-Riot-Token": self.api_key,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "OPGG-Clone-Local/1.0"
        }

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        중앙 집중식 HTTP 전송 계층:
        - 서킷 브레이커 차단 검사 (만료 시 빠른 실패)
        - 레이트 리미터 토큰 자동 획득 (1 req = 1 token)
        - 응답 헤더(Retry-After, Rate-Limit-Count) 자동 파싱 피드백
        - 401/403 응답 시 즉시 키 만료 상태 플래그 설정
        """
        from app.sync_automation_engine import rate_limiter
        if rate_limiter.is_circuit_broken() or self._is_expired:
            self.mark_key_expired("24-hour developer key expired (401/403)")
            raise RiotAPIError(401, f"서킷 브레이커 차단 상태: {rate_limiter.circuit_open_reason or '24-hour developer key expired (401/403)'}")

        await rate_limiter.acquire(1.0)
        headers = self._get_headers()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        timeout = kwargs.pop("timeout", 10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method, url, headers=headers, **kwargs)
                rate_limiter.handle_response_headers(resp.headers, resp.status_code)
                if resp.status_code == 401:
                    self.mark_key_expired("24-hour developer key expired (401/403)")
                elif resp.status_code == 403:
                    # 403은 '이 키로 못 쓰는 엔드포인트'(관전 featured 등)일 때도 온다.
                    # 모든 키가 쓸 수 있는 상태 API로 확인해서 키가 거부될 때만 만료 처리한다.
                    await self._confirm_key_after_403(client)
                return resp
        except httpx.HTTPError as e:
            # 타임아웃·연결 실패를 500으로 흘리지 않고 '라이엇 연결 불가'(503)로 알린다
            raise RiotAPIError(503, f"라이엇 API 서버와 통신하지 못했습니다 ({type(e).__name__})") from e

    async def _confirm_key_after_403(self, client: httpx.AsyncClient) -> None:
        """403 응답 뒤 키 자체가 거부되는지 상태 API로 확인 (60초에 최대 1회)"""
        import time
        from app.sync_automation_engine import rate_limiter
        now = time.time()
        if now - self._last_403_check < 60.0:
            return
        self._last_403_check = now
        url = f"https://{self.region}.api.riotgames.com/lol/status/v4/platform-data"
        try:
            await rate_limiter.acquire(1.0)
            resp = await client.get(url, headers={"X-Riot-Token": self.api_key})
        except Exception:
            return
        if resp.status_code in (401, 403):
            self.mark_key_expired("Riot API 서버 인증 실패 (401 Unknown API Key / 403 Forbidden)")

    async def verify_key(self, test_key: Optional[str] = None) -> Dict[str, Any]:
        """
        API 키의 유효성을 실시간으로 확인합니다.
        - test_key가 없는 경우 15초 인메모리 캐싱으로 불필요한 반복 외부 네트워크 I/O 및 레이턴시 병목 차단
        """
        import time
        now = time.time()
        key = (test_key or self.api_key or "").strip()
        if not key:
            return {"valid": False, "status": "missing", "reason": "API 키가 등록되지 않았습니다."}

        if test_key is None and self._verify_cache_res is not None and (now - self._verify_cache_time < 15.0):
            return self._verify_cache_res

        self._last_checked_at = now
        url = f"https://{self.region}.api.riotgames.com/lol/status/v4/platform-data"
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url, headers={"X-Riot-Token": key})
                if resp.status_code == 200:
                    # 만료로 표시돼 있던 키가 다시 통과할 때만 상태를 초기화한다.
                    # (정상 상태에서 초기화하면 429 백오프까지 지워져 공개 상태 조회만으로 한도 보호가 풀린다)
                    from app.sync_automation_engine import rate_limiter
                    if test_key is not None or self._is_expired or rate_limiter.is_key_expired:
                        self.reset_key_status()
                    res = {"valid": True, "status": "valid", "reason": "정상 연결됨 (Active)"}
                elif resp.status_code in [401, 403]:
                    reason_msg = "Riot API 서버 인증 실패 (401 Unknown API Key / 403 Forbidden)"
                    self.mark_key_expired(reason_msg)
                    res = {"valid": False, "status": "expired", "reason": reason_msg}
                elif resp.status_code == 429:
                    res = {"valid": True, "status": "rate_limited", "reason": "API 요청 한도 초과(키는 유효함)"}
                else:
                    res = {"valid": False, "status": "error", "reason": f"오류 응답 ({resp.status_code})"}
        except Exception as e:
            res = {"valid": False, "status": "network_error", "reason": f"라이엇 서버 통신 실패 ({str(e)})"}

        if test_key is None:
            self._verify_cache_res = res
            self._verify_cache_time = now
        return res

    async def get_account_by_riot_id(self, game_name: str, tag_line: str) -> Dict[str, Any]:
        """
        Riot Account-V1 API: 닉네임과 태그로 PUUID를 조회합니다.
        """
        if not game_name.strip() or not tag_line.strip():
            raise RiotAPIError(404, "닉네임과 태그를 모두 입력해주세요. (예: Hide on bush#KR1)")
        if RIOT_ID_FORBIDDEN.search(game_name + tag_line):
            # 라이엇 ID에 쓸 수 없는 문자: 호출하지 않고 '없는 소환사'로 처리
            raise RiotAPIError(404, f"소환사 '{game_name}#{tag_line}'을(를) 찾을 수 없습니다.")
        # 사용자 입력이므로 경로 구분자까지 인코딩한다. 그대로 넣으면 '/', '..' 등으로 다른 라이엇 경로를
        # 호출하게 되고, 라이엇이 403을 돌려주면 키가 만료된 것으로 표시돼 사이트 전체 조회가 멈춘다.
        url = (f"https://{self.routing_region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
               f"{quote(game_name, safe='')}/{quote(tag_line, safe='')}")
        resp = await self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            raise RiotAPIError(404, f"소환사 '{game_name}#{tag_line}'을(를) 찾을 수 없습니다.")
        elif resp.status_code in [401, 403]:
            raise RiotAPIError(resp.status_code, "Riot API Key가 만료되었거나 올바르지 않습니다.")
        elif resp.status_code == 429:
            raise RiotAPIError(429, "Riot API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
        else:
            raise RiotAPIError(resp.status_code, f"Riot API 요청 실패: {resp.text}")

    async def get_account_by_puuid(self, puuid: str) -> Optional[Dict[str, Any]]:
        """Riot Account-V1 API: PUUID로 현재 닉네임#태그를 조회합니다. (없으면 None)"""
        url = f"https://{self.routing_region}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}"
        resp = await self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in [401, 403, 429]:
            raise RiotAPIError(resp.status_code, "Riot API 키 만료 또는 요청 한도 초과")
        return None

    async def get_apex_league(self, tier: str = "CHALLENGER") -> Dict[str, Any]:
        """League-V4: 챌린저/그랜드마스터/마스터 솔로랭크 리그 전체 엔트리"""
        path = {"CHALLENGER": "challengerleagues", "GRANDMASTER": "grandmasterleagues", "MASTER": "masterleagues"}[tier]
        url = f"https://{self.region}.api.riotgames.com/lol/league/v4/{path}/by-queue/RANKED_SOLO_5x5"
        resp = await self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        raise RiotAPIError(resp.status_code, f"{tier} 리그 조회 실패")

    async def get_summoner_by_puuid(self, puuid: str) -> Optional[Dict[str, Any]]:
        """
        LoL Summoner-V4 API: PUUID로 소환사 레벨, 프로필 아이콘 등을 조회합니다. (LoL 기록이 없는 계정이면 None)
        """
        url = f"https://{self.region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
        resp = await self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            return None
        else:
            raise RiotAPIError(resp.status_code, f"소환사 정보 조회 실패: {resp.text}")

    async def get_league_entries_by_puuid(self, puuid: str) -> List[Dict[str, Any]]:
        """
        LoL League-V4 API: PUUID로 솔로랭크 및 자유랭크 티어 정보를 조회합니다.
        """
        url = f"https://{self.region}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
        resp = await self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            return []
        else:
            raise RiotAPIError(resp.status_code, f"리그 정보 조회 실패: {resp.text}")

    async def fetch_full_player_profile(self, game_name: str, tag_line: str) -> Dict[str, Any]:
        """
        통합 플레이어 데이터 수집:
        Account API -> Summoner API -> League API
        """
        account = await self.get_account_by_riot_id(game_name, tag_line)
        puuid = account["puuid"]
        real_game_name = account["gameName"]
        real_tag_line = account["tagLine"]

        summoner = await self.get_summoner_by_puuid(puuid)
        if not summoner:
            # 라이엇 계정은 있지만 LoL 소환사 기록이 없음 (레벨·아이콘을 지어내지 않고 '없는 소환사'로 처리)
            raise RiotAPIError(404, f"'{real_game_name}#{real_tag_line}' 계정에 리그 오브 레전드 소환사 기록이 없습니다.")
        profile_icon_id = summoner.get("profileIconId")
        summoner_level = summoner.get("summonerLevel")

        league_entries = await self.get_league_entries_by_puuid(puuid)
        
        # 솔로랭크 및 자유랭크 엔트리 모두 추출
        solo_entry = None
        flex_entry = None
        for entry in league_entries:
            q_type = entry.get("queueType")
            if q_type == "RANKED_SOLO_5x5":
                solo_entry = entry
            elif q_type == "RANKED_FLEX_SR":
                flex_entry = entry

        # 솔로랭크 기본값
        if solo_entry:
            tier = solo_entry.get("tier", "UNRANKED")
            rank_tier = solo_entry.get("rank", "")
            league_points = solo_entry.get("leaguePoints", 0)
            wins = solo_entry.get("wins", 0)
            losses = solo_entry.get("losses", 0)
            queue_type = solo_entry.get("queueType", "RANKED_SOLO_5x5")
        else:
            # 자유랭크만 있으면 솔로랭크는 언랭크 (자유랭크 값은 flex_* 필드로만 보여준다)
            tier = "UNRANKED"
            rank_tier = ""
            league_points = 0
            wins = 0
            losses = 0
            queue_type = "RANKED_SOLO_5x5"

        # 자유랭크 필드 추출
        flex_tier = flex_entry.get("tier", "UNRANKED") if flex_entry else "UNRANKED"
        flex_rank_tier = flex_entry.get("rank", "") if flex_entry else ""
        flex_lp = flex_entry.get("leaguePoints", 0) if flex_entry else 0
        flex_wins = flex_entry.get("wins", 0) if flex_entry else 0
        flex_losses = flex_entry.get("losses", 0) if flex_entry else 0

        return {
            "puuid": puuid,
            "game_name": real_game_name,
            "tag_line": real_tag_line,
            "profile_icon_id": profile_icon_id,
            "summoner_level": summoner_level,
            "tier": tier,
            "rank_tier": rank_tier,
            "league_points": league_points,
            "wins": wins,
            "losses": losses,
            "queue_type": queue_type,
            "flex_tier": flex_tier,
            "flex_rank_tier": flex_rank_tier,
            "flex_lp": flex_lp,
            "flex_wins": flex_wins,
            "flex_losses": flex_losses
        }

    async def get_champion_masteries_by_puuid(self, puuid: str, count: int = 15) -> List[Dict[str, Any]]:
        """
        LoL Champion-Mastery-V4: 소환사의 실제 챔피언 숙련도 목록 조회
        """
        url = f"https://{self.region}.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/top?count={count}"
        try:
            resp = await self._request("GET", url)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return []

    async def get_champion_mastery_by_champion(self, puuid: str, champion_id: int) -> Optional[Dict[str, Any]]:
        """
        LoL Champion-Mastery-V4: 소환사의 특정 챔피언 숙련도 단건 조회
        """
        url = f"https://{self.region}.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/by-champion/{champion_id}"
        try:
            resp = await self._request("GET", url)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    async def get_match_ids_by_puuid(
        self,
        puuid: str,
        count: int = 20,
        queue: Optional[int] = None,
        start_time: Optional[int] = None,
    ) -> List[str]:
        """
        LoL Match-V5: 최근 실제 매치 ID 목록 조회 (최대 count개)
        """
        url = f"https://{self.routing_region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}"
        if queue is not None:
            url += f"&queue={queue}"
        if start_time is not None:
            url += f"&startTime={start_time}"
        resp = await self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return []
        # 429/5xx/401 을 '전적 없음'으로 숨기지 않고 호출자에게 알린다
        raise RiotAPIError(resp.status_code, f"매치 목록 조회 실패 ({resp.status_code})")

    async def get_match_detail(self, match_id: str) -> Optional[Dict[str, Any]]:
        """
        LoL Match-V5: 특정 매치 상세 기록 조회
        """
        url = f"https://{self.routing_region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        resp = await self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None
        raise RiotAPIError(resp.status_code, f"매치 상세 조회 실패 ({resp.status_code})")

    async def get_match_timeline(self, match_id: str) -> Optional[Dict[str, Any]]:
        """LoL Match-V5: 매치 타임라인 (스킬 레벨업·아이템 구매 이벤트). 수집기 전용"""
        url = f"https://{self.routing_region}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        resp = await self._request("GET", url, timeout=15.0)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None
        raise RiotAPIError(resp.status_code, f"매치 타임라인 조회 실패 ({resp.status_code})")

    async def get_summoner_by_id(self, summoner_id: str) -> Optional[Dict[str, Any]]:
        """Summoner-V4 (encryptedSummonerId): 리그 엔트리에 puuid가 없을 때 puuid를 얻기 위해 사용"""
        url = f"https://{self.region}.api.riotgames.com/lol/summoner/v4/summoners/{summoner_id}"
        resp = await self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None
        raise RiotAPIError(resp.status_code, f"소환사 조회 실패 ({resp.status_code})")

    async def get_spectator_active_game_by_puuid(self, puuid: str) -> Optional[Dict[str, Any]]:
        """
        LoL Spectator-V5: 소환사의 실시간 진행 중인 게임(Active Game) 조회
        """
        url = f"https://{self.region}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"
        try:
            resp = await self._request("GET", url)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                return None
            elif resp.status_code in [401, 403]:
                raise RiotAPIError(resp.status_code, "Riot API Key가 만료되었거나 올바르지 않습니다.")
            elif resp.status_code == 429:
                raise RiotAPIError(429, "Riot API 요청 한도를 초과했습니다.")
        except RiotAPIError:
            raise
        except Exception:
            pass
        return None

riot_client = RiotClient()
