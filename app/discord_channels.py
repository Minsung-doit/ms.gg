"""
구인글 음성방 링크 → 디스코드의 실제 채널 이름 (app/discord_channels.py)

- 초대 링크 (discord.gg/코드, discord.com/invite/코드): 디스코드 공개 초대 정보 API (인증 불필요)
- 채널 링크 (discord.com/channels/서버ID/채널ID): 봇 토큰(DISCORD_BOT_TOKEN)이 있고 봇이 그 서버에 있을 때만
- 이름을 못 받으면 None (호출한 쪽에서 '디스코드 음성방' 같은 일반 이름을 쓴다). 10분 캐시, 3초 제한.
"""
import os
import re
import time
from typing import Dict, Optional, Tuple

import httpx

DISCORD_API = "https://discord.com/api/v10"
_INVITE = re.compile(r"^(?:https://)?(?:www\.)?(?:discord\.gg/|discord(?:app)?\.com/invite/)([A-Za-z0-9-]{2,32})/?$")
_CHANNEL = re.compile(r"^(?:https://(?:www\.)?|discord://)discord(?:app)?\.com/channels/(\d{15,21})/(\d{15,21})/?$")
_CACHE: Dict[str, Tuple[float, Optional[str]]] = {}
_TTL = 600


async def channel_name(url: Optional[str]) -> Optional[str]:
    url = (url or "").strip()
    if not url:
        return None
    hit = _CACHE.get(url)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    name = None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            m = _INVITE.match(url)
            if m:
                r = await client.get(f"{DISCORD_API}/invites/{m.group(1)}")
                if r.status_code == 200:
                    name = ((r.json() or {}).get("channel") or {}).get("name")
            else:
                m = _CHANNEL.match(url)
                token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
                if m and token:
                    r = await client.get(f"{DISCORD_API}/channels/{m.group(2)}", headers={"Authorization": f"Bot {token}"})
                    data = r.json() if r.status_code == 200 else {}
                    if str(data.get("guild_id", "")) == m.group(1):
                        name = data.get("name")
    except (httpx.HTTPError, ValueError):
        name = None
    name = (name or "").strip()[:36] or None
    _CACHE[url] = (time.time(), name)
    if len(_CACHE) > 500:
        _CACHE.clear()
    return name
