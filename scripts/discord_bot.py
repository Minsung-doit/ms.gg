#!/usr/bin/env python3
"""
================================================================================
👑 carry.gg Enterprise Official Discord Bot
================================================================================
디스코드 서버에서 실시간 소환사 전적, 챔피언 티어, 5인 픽창 멀티서치, 듀오 구인글을
조회하고 공유할 수 있는 carry.gg 공식 디스코드 봇입니다.

[지원 슬래시 커맨드]:
  • /전적 [소환사명#태그]     : 솔로랭크 티어, 최근 20전 승률/KDA, 모스트 챔피언 3종 조회
  • /티어 [라인] [챔피언]    : 해당 라인 14.20 메타 OP/티어 순위, 승률, 카운터 3종, 3코어 빌드
  • /멀티서치 [픽창 텍스트]   : 픽창 로비 5인 분석, 연승/연패 주의 알림 및 메타 밴픽 추천
  • /듀오                    : 현재 실시간 등록된 듀오 구인글 TOP 5 및 음성 채널 바로가기
  • /핑                      : 봇 응답 속도 및 carry.gg 백엔드 API 레이턴시 측정

[실행 방법]:
  1. pip install discord.py aiohttp
  2. .env 파일에 DISCORD_BOT_TOKEN="본인의_봇_토큰" 추가
  3. python scripts/discord_bot.py
================================================================================
"""

import asyncio
import os
import re
import sys
from typing import Optional
import time
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
API_BASE_URL = os.getenv("LOLGG_API_URL", "http://localhost:3000").rstrip("/")
# 봇 전용 서버 경로용 비밀값 (서버 .env 의 BOT_API_SECRET 과 같은 값). 없으면 /구인글·같이해요 버튼은 안내만 한다
BOT_API_SECRET = os.getenv("BOT_API_SECRET", "").strip()
try:
    sys.path.insert(0, str(BASE_DIR))
    from app.ddragon import DDRAGON_CDN  # 이미지 주소 버전은 app/ddragon.py 한 곳에서
except Exception:
    DDRAGON_CDN = "https://ddragon.leagueoflegends.com/cdn/latest"
try:
    from app import duo_games  # /구인글 큐 자동완성 (줄임말 풀이는 서버가 한다)
except Exception:
    duo_games = None
# 사이트 주소 (임베드 제목 링크). 없으면 링크 없이
SITE_URL = os.getenv("SITE_URL", "").strip().rstrip("/")
# 티어 역할 자동 부여: 1 이면 1시간마다 (라이엇 로그인으로 인증한 멤버만, 이름이 맞는 역할만 건드림)
TIER_ROLE_SYNC = os.getenv("TIER_ROLE_SYNC", "").strip() == "1"
TIER_ROLE_PREFIX = os.getenv("TIER_ROLE_PREFIX", "").strip()[:20]
TIER_ROLE_INTERVAL_SEC = 3600
# 낮은 티어부터 (역할 이름 · 색)
TIER_ROLES = [("IRON", "아이언", 0x6B6B6B), ("BRONZE", "브론즈", 0x8C5A3C), ("SILVER", "실버", 0x9AA4AF),
              ("GOLD", "골드", 0xD4AF37), ("PLATINUM", "플래티넘", 0x3FB7A6), ("EMERALD", "에메랄드", 0x2ECC71),
              ("DIAMOND", "다이아몬드", 0x5B8DEF), ("MASTER", "마스터", 0x9B59B6), ("GRANDMASTER", "그랜드마스터", 0xE74C3C),
              ("CHALLENGER", "챌린저", 0xF1C40F)]

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("lolgg.bot")

try:
    import discord
    from discord import app_commands
    from discord.ext import commands
    import aiohttp
    HAS_DISCORD_PY = True
except ImportError:
    HAS_DISCORD_PY = False


if not HAS_DISCORD_PY:
    print("=" * 70)
    print("⚠️ [안내] discord.py 라이브러리가 설치되어 있지 않습니다.")
    print("   설치 명령: pip install discord.py aiohttp")
    print("   본 스크립트는 디스코드 연계 가이드 및 독립형 봇으로 완벽히 구성되어 있습니다.")
    print("=" * 70)


class LolGgDiscordBot(commands.Bot if HAS_DISCORD_PY else object):
    def __init__(self):
        if HAS_DISCORD_PY:
            intents = discord.Intents.default()
            # 슬래시 커맨드만 쓰므로 메시지 본문 권한(개발자 포털에서 따로 켜야 하는 권한)은 요청하지 않는다
            super().__init__(command_prefix="!", intents=intents)
        self.session = None

    async def setup_hook(self):
        if HAS_DISCORD_PY:
            # 멤버 로그인을 켠 사이트에서도 봇이 API를 쓸 수 있도록 비밀값을 모든 요청에 붙인다
            self.session = aiohttp.ClientSession(headers={"X-Bot-Secret": BOT_API_SECRET} if BOT_API_SECRET else None)
            await self.tree.sync()
            logger.info("✅ carry.gg 슬래시 커맨드가 전역 동기화되었습니다.")

    async def close(self):
        if self.session:
            await self.session.close()
        if HAS_DISCORD_PY:
            await super().close()


bot = LolGgDiscordBot() if HAS_DISCORD_PY else None


if HAS_DISCORD_PY:
    @bot.event
    async def on_ready():
        logger.info(f"🤖 carry.gg 디스코드 봇 로그인 성공: {bot.user.name} ({bot.user.id})")
        activity = discord.Activity(type=discord.ActivityType.watching, name="소환사의 협곡 | /전적")
        await bot.change_presence(status=discord.Status.online, activity=activity)
        if TIER_ROLE_SYNC and not getattr(bot, "_tier_loop_started", False):
            bot._tier_loop_started = True
            asyncio.create_task(_tier_role_loop())

    # ── 티어 역할 자동 부여 ─────────────────────────────────────────────
    # 사이트에 라이엇 로그인(RSO)으로 인증한 멤버의 솔로랭크 티어에 맞는 역할을 달아 준다.
    # 서버마다 역할 이름이 다르므로, 관리자가 이미 있는 역할을 티어에 연결해 둔다 (/티어역할 자동연결·연결, 사이트에 저장).
    # 연결된 역할만 건드리고, 사이트에 없는 멤버는 손대지 않는다. 연결이 없으면 '아이언'~'챌린저' 이름 역할을 쓴다.
    # 봇에 '역할 관리' 권한이 있어야 하고, 봇 역할이 티어 역할보다 위에 있어야 한다.
    TIER_KR = {code: name for code, name, _ in TIER_ROLES}
    # 역할 이름에서 티어를 알아볼 말. 장식(이모지·기호·숫자)과 '롤'·'티어' 같은 앞뒤 말을 뺀 나머지가 이 말과 같아야 한다
    # ('서버 마스터'·'길드마스터'·'플레이어' 같은 역할을 티어로 잘못 잡지 않도록 부분 일치는 쓰지 않음)
    TIER_NAME_HINTS = {
        "GRANDMASTER": ("그랜드마스터", "그마", "grandmaster", "gm"),
        "CHALLENGER": ("챌린저", "챌린져", "챌", "challenger"),
        "MASTER": ("마스터", "master"),
        "DIAMOND": ("다이아", "다이아몬드", "diamond", "dia"),
        "EMERALD": ("에메랄드", "에메", "emerald"),
        "PLATINUM": ("플래티넘", "플레티넘", "플래", "플레", "platinum", "plat"),
        "GOLD": ("골드", "gold"),
        "SILVER": ("실버", "silver"),
        "BRONZE": ("브론즈", "브론", "bronze"),
        "IRON": ("아이언", "iron"),
    }
    TIER_NAME_PREFIXES = ("롤", "lol")
    TIER_NAME_SUFFIXES = ("티어", "유저", "등급", "이상", "plus")
    # 관리·운영 권한이 있는 역할은 티어 역할로 쓰지 않는다 (뗐다 붙였다 하면 안 되는 역할)
    UNSAFE_ROLE_PERMS = ("administrator", "manage_guild", "manage_roles", "manage_channels", "manage_messages",
                         "kick_members", "ban_members", "moderate_members")

    def _safe_tier_role(role) -> bool:
        return not (role.is_default() or role.managed or any(getattr(role.permissions, p, False) for p in UNSAFE_ROLE_PERMS))

    def _guess_tier(role_name: str):
        core = re.sub(r"[^a-z가-힣]", "", role_name.lower())
        for pre in TIER_NAME_PREFIXES:
            if core.startswith(pre) and len(core) > len(pre):
                core = core[len(pre):]
        for suf in TIER_NAME_SUFFIXES:
            if core.endswith(suf) and len(core) > len(suf):
                core = core[:-len(suf)]
        for code, hints in TIER_NAME_HINTS.items():
            if core in hints:
                return code
        return None

    async def _fetch_tier_data(guild):
        """사이트에서 (멤버 티어 목록, 저장된 티어→역할 연결)"""
        async with bot.session.get(f"{API_BASE_URL}/api/bot/tier-roles", params={"guild_id": str(guild.id)}, timeout=10) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            data = await resp.json()
        return data.get("members") or [], data.get("role_map") or {}

    async def _save_tier_map(interaction, mapping: dict) -> bool:
        body = {"member": _member_of(interaction), "roles": {c: str(r) for c, r in mapping.items() if r}}
        async with bot.session.post(f"{API_BASE_URL}/api/bot/tier-role-map", json=body, headers=_bot_headers(), timeout=5) as resp:
            return resp.status == 200

    def _tier_role_map(guild, saved: dict) -> dict:
        """티어 코드 → 역할. 저장된 연결이 있으면 그것, 없으면 '아이언'~'챌린저' 이름 역할"""
        roles = {}
        if saved:
            for code, rid in saved.items():
                role = guild.get_role(int(rid)) if str(rid).isdigit() else None
                if role:
                    roles[code] = role
            return roles
        for code, name, _ in TIER_ROLES:
            role = discord.utils.get(guild.roles, name=f"{TIER_ROLE_PREFIX}{name}")
            if role:
                roles[code] = role
        return roles

    def _map_text(guild, roles: dict) -> str:
        lines = []
        for code, name, _ in reversed(TIER_ROLES):
            role = roles.get(code)
            lines.append(f"{name}: {role.mention if role else '— (연결 안 됨)'}")
        return "\n".join(lines)

    async def sync_tier_roles(guild) -> dict:
        """반환: {'changed': n, 'checked': n} 또는 {'error': 이유}"""
        me = guild.me
        if not me or not me.guild_permissions.manage_roles:
            return {"error": "봇에 '역할 관리' 권한이 없어요."}
        try:
            members, saved = await _fetch_tier_data(guild)
        except Exception:
            return {"error": "사이트 서버에서 멤버 목록을 받지 못했어요."}
        roles = _tier_role_map(guild, saved)
        if not roles:
            return {"error": "연결된 티어 역할이 없어요. `/티어역할 자동연결` 이나 `/티어역할 연결` 로 먼저 연결해 주세요."}
        usable = {code: r for code, r in roles.items() if r < me.top_role and _safe_tier_role(r)}
        if not usable:
            return {"error": "봇 역할을 서버 설정 → 역할에서 티어 역할들보다 위로 올려 주세요."}
        tier_roles = set(usable.values())
        changed = checked = 0
        for m in members:
            try:
                member = guild.get_member(int(m["discord_id"])) or await guild.fetch_member(int(m["discord_id"]))
            except (discord.NotFound, discord.HTTPException, ValueError):
                continue
            checked += 1
            want = usable.get(m.get("tier") or "")
            remove = [r for r in member.roles if r in tier_roles and r != want]
            add = want is not None and want not in member.roles
            try:
                if remove:
                    await member.remove_roles(*remove, reason="carry.gg 티어 역할 (솔로랭크 변경)")
                if add:
                    await member.add_roles(want, reason="carry.gg 티어 역할 (라이엇 인증 솔로랭크)")
                if remove or add:
                    changed += 1
                    await asyncio.sleep(1)  # 디스코드 역할 변경 한도
            except discord.Forbidden:
                return {"error": "역할을 바꿀 권한이 없어요. 봇 역할 위치를 확인해 주세요.", "changed": changed}
        return {"changed": changed, "checked": checked}

    async def _tier_role_loop():
        while True:
            for guild in list(bot.guilds):
                try:
                    res = await sync_tier_roles(guild)
                    if res.get("changed"):
                        logger.info("tier roles %s: %s", guild.id, res)
                except Exception as e:
                    logger.warning("tier role sync failed: %s", type(e).__name__)
            await asyncio.sleep(TIER_ROLE_INTERVAL_SEC)

    # ── 구인 알림 역할 ──────────────────────────────────────────────────
    # 관리자는 서버에 이미 있는 역할(@롤 등)을 알림 역할로 고르고, 멤버는 /알림받기 로 직접 달고 뗀다
    ALERT_GAME_CHOICES = [app_commands.Choice(name="롤", value="lol"), app_commands.Choice(name="배그", value="pubg"),
                          app_commands.Choice(name="옵치", value="overwatch")]

    @bot.tree.command(name="알림역할", description="(관리자) 새 구인글이 올라올 때 멘션할 역할을 정합니다. 이미 있는 역할을 골라도 됩니다.")
    @app_commands.describe(역할="멘션할 역할 (비우면 이 게임 알림을 끕니다)", 게임="어느 게임 구인글 알림인지 (기본 롤)")
    @app_commands.choices(게임=ALERT_GAME_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def cmd_alert_role(interaction: discord.Interaction, 역할: Optional[discord.Role] = None,
                             게임: Optional[app_commands.Choice[str]] = None):
        if not BOT_API_SECRET:
            await interaction.response.send_message("봇 연동이 설정되지 않았어요.", ephemeral=True)
            return
        perms = getattr(interaction.user, "guild_permissions", None)
        if not perms or not perms.manage_guild:
            await interaction.response.send_message("'서버 관리' 권한이 있는 사람만 정할 수 있어요.", ephemeral=True)
            return
        game = 게임.value if 게임 else "lol"
        if 역할 is not None and (역할.is_default() or 역할.managed):
            await interaction.response.send_message("@everyone 이나 봇 전용 역할은 알림 역할로 쓸 수 없어요.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        body = {"member": _member_of(interaction), "game": game, "role_id": str(역할.id) if 역할 else None}
        try:
            async with bot.session.post(f"{API_BASE_URL}/api/bot/alert-role", json=body, headers=_bot_headers(), timeout=5) as resp:
                status = resp.status
                data = await resp.json(content_type=None)
        except Exception:
            await interaction.followup.send("⚠️ 사이트 서버에 연결하지 못했어요.", ephemeral=True)
            return
        if status != 200:
            await interaction.followup.send(f"정하지 못했어요 ({data.get('detail', status) if isinstance(data, dict) else status}).",
                                            ephemeral=True)
            return
        name = {"lol": "롤", "pubg": "배그", "overwatch": "옵치"}[game]
        if 역할 is None:
            await interaction.followup.send(f"🔕 {name} 구인글 알림 멘션을 껐어요.", ephemeral=True)
            return
        msg = f"✅ 이제 {name} 구인글이 올라오면 {역할.mention} 을 멘션해요. 멤버는 `/알림받기` 로 직접 이 역할을 달고 뗄 수 있어요."
        if not 역할.mentionable:
            msg += "\n⚠️ 이 역할은 '멘션 허용'이 꺼져 있어요. 서버 설정 → 역할에서 켜야 알림이 갑니다."
        me = interaction.guild.me if interaction.guild else None
        if me and (not me.guild_permissions.manage_roles or 역할 >= me.top_role):
            msg += "\nℹ️ `/알림받기` 를 쓰려면 봇에 '역할 관리' 권한이 있고 봇 역할이 이 역할보다 위에 있어야 해요."
        await interaction.followup.send(msg, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @bot.tree.command(name="계정등록", description="내 롤 닉네임을 등록합니다 (티어 역할·내전 팀 나누기용, 랭킹은 사이트에서 라이엇 로그인 인증).")
    @app_commands.describe(닉네임="닉네임#태그 (예: 닉네임#KR1)")
    @app_commands.guild_only()
    async def cmd_register_riot_account(interaction: discord.Interaction, 닉네임: str):
        if not BOT_API_SECRET:
            await interaction.response.send_message("봇 연동이 설정되지 않았어요.", ephemeral=True)
            return
        name, sep, tag = (닉네임 or "").rpartition("#")
        name = name.strip()
        tag = tag.strip()
        if not sep or not name or not tag:
            await interaction.response.send_message("닉네임#태그 형식으로 입력해 주세요.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        body = {"member": _member_of(interaction), "game_name": name, "tag_line": tag}
        try:
            async with bot.session.post(f"{API_BASE_URL}/api/bot/riot-account", json=body, headers=_bot_headers(), timeout=25) as resp:
                status = resp.status
                data = await resp.json(content_type=None)
        except Exception:
            await interaction.followup.send("⚠️ 서버에 연결하지 못했어요.", ephemeral=True)
            return
        if status == 200:
            acc = data.get("account") if isinstance(data, dict) else None
            gn = (acc.get("game_name") if acc else None) or name
            tl = (acc.get("tag_line") if acc else None) or tag
            await interaction.followup.send(
                f"✅ {gn}#{tl} 를 등록했어요. 티어 역할은 1시간 안에 맞춰져요. 서버 랭킹에 올라가려면 사이트에서 라이엇 로그인으로 인증해 주세요.",
                ephemeral=True,
            )
        else:
            why = _error_text(data)
            reason = why or status
            await interaction.followup.send(f"등록하지 못했어요: {reason}", ephemeral=True)

    @bot.tree.command(name="알림받기", description="새 구인글 알림 역할을 달거나 뗍니다 (한 번 더 쓰면 해제).")
    @app_commands.describe(게임="어느 게임 구인글 알림인지 (기본 롤)")
    @app_commands.choices(게임=ALERT_GAME_CHOICES)
    @app_commands.guild_only()
    async def cmd_alert_me(interaction: discord.Interaction, 게임: Optional[app_commands.Choice[str]] = None):
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("서버 안에서만 쓸 수 있어요.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        game = 게임.value if 게임 else "lol"
        try:
            async with bot.session.get(f"{API_BASE_URL}/api/bot/alert-role", params={"guild_id": str(guild.id)},
                                       headers=_bot_headers(), timeout=5) as resp:
                data = await resp.json(content_type=None) if resp.status == 200 else {}
                roles = (data or {}).get("roles") or {}
        except Exception:
            roles = {}
        role = guild.get_role(int(roles[game])) if roles.get(game, "").isdigit() else None
        if role is None:
            await interaction.followup.send("이 서버는 아직 알림 역할이 정해지지 않았어요. 관리자에게 `/알림역할` 을 부탁해 주세요.",
                                            ephemeral=True)
            return
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="carry.gg /알림받기 해제")
                await interaction.followup.send(f"🔕 {role.name} 역할을 뗐어요. 이제 구인 알림이 오지 않아요.", ephemeral=True)
            else:
                await interaction.user.add_roles(role, reason="carry.gg /알림받기")
                await interaction.followup.send(f"🔔 {role.name} 역할을 달았어요. 새 구인글이 올라오면 알림이 와요.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("봇이 이 역할을 달 수 없어요. 관리자에게 봇의 '역할 관리' 권한과 역할 순서를 확인해 달라고 해 주세요.",
                                            ephemeral=True)

    tier_group = app_commands.Group(name="티어역할", description="(관리자) 솔로랭크 티어 역할 연결·부여",
                                    guild_only=True, default_permissions=discord.Permissions(manage_roles=True))
    TIER_CHOICES = [app_commands.Choice(name=name, value=code) for code, name, _ in reversed(TIER_ROLES)]

    async def _tier_guild(interaction):
        if interaction.guild is None:
            await interaction.response.send_message("서버 안에서만 쓸 수 있어요.", ephemeral=True)
            return None
        await interaction.response.defer(ephemeral=True)
        return interaction.guild

    @tier_group.command(name="자동연결", description="서버에 이미 있는 역할 이름(다이아, 💎 Diamond 등)을 보고 티어에 연결합니다.")
    async def cmd_tier_auto(interaction: discord.Interaction):
        guild = await _tier_guild(interaction)
        if guild is None:
            return
        found, dupes = {}, {}
        for role in guild.roles:
            if not _safe_tier_role(role):
                continue
            code = _guess_tier(role.name)
            if not code:
                continue
            if code in found:
                dupes.setdefault(code, [found[code]]).append(role)
            else:
                found[code] = role
        for code in dupes:  # '다이아1'·'다이아2' 처럼 한 티어에 역할이 여러 개면 직접 고르게 둔다
            found.pop(code, None)
        if not found:
            await interaction.followup.send("이름으로 알아볼 수 있는 티어 역할이 없어요. `/티어역할 연결` 로 하나씩 연결하거나 "
                                            "`/티어역할 만들기` 로 새로 만들어 주세요.", ephemeral=True)
            return
        try:
            ok = await _save_tier_map(interaction, {c: r.id for c, r in found.items()})
        except Exception:
            ok = False
        if not ok:
            await interaction.followup.send("⚠️ 사이트에 저장하지 못했어요. 잠시 후 다시 시도해 주세요.", ephemeral=True)
            return
        msg = "✅ 이렇게 연결했어요.\n" + _map_text(guild, found)
        if dupes:
            msg += "\n\n⚠️ 한 티어에 역할이 여러 개라 비워 둔 티어: " + ", ".join(
                f"{TIER_KR[c]}({', '.join(r.name for r in rs[:4])})" for c, rs in dupes.items())
            msg += "\n`/티어역할 연결` 로 하나를 골라 주세요."
        top = guild.me.top_role
        if any(r >= top for r in found.values()):
            msg += "\n\nℹ️ 봇 역할보다 위에 있는 역할은 달아 줄 수 없어요. 서버 설정 → 역할에서 봇 역할을 위로 올려 주세요."
        msg += "\n틀린 곳은 `/티어역할 연결` 로 고칠 수 있어요."
        await interaction.followup.send(msg, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @tier_group.command(name="연결", description="티어 하나를 서버의 기존 역할에 연결합니다 (역할을 비우면 연결 해제).")
    @app_commands.describe(티어="솔로랭크 티어", 역할="연결할 역할 (여러 티어가 같은 역할을 써도 됩니다, 예: 마스터+)")
    @app_commands.choices(티어=TIER_CHOICES)
    async def cmd_tier_link(interaction: discord.Interaction, 티어: app_commands.Choice[str], 역할: Optional[discord.Role] = None):
        guild = await _tier_guild(interaction)
        if guild is None:
            return
        if 역할 is not None and not _safe_tier_role(역할):
            await interaction.followup.send("@everyone·봇 전용 역할이나 관리 권한이 있는 역할은 티어 역할로 쓸 수 없어요.", ephemeral=True)
            return
        try:
            _, saved = await _fetch_tier_data(guild)
            saved = dict(saved)
            if 역할 is None:
                saved.pop(티어.value, None)
            else:
                saved[티어.value] = str(역할.id)
            ok = await _save_tier_map(interaction, saved)
        except Exception:
            ok = False
        if not ok:
            await interaction.followup.send("⚠️ 사이트에 저장하지 못했어요. 잠시 후 다시 시도해 주세요.", ephemeral=True)
            return
        await interaction.followup.send(("✅ 연결했어요.\n" if 역할 else "연결을 풀었어요.\n") + _map_text(guild, _tier_role_map(guild, saved)),
                                        ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @tier_group.command(name="보기", description="지금 티어마다 어떤 역할이 연결돼 있는지 봅니다.")
    async def cmd_tier_show(interaction: discord.Interaction):
        guild = await _tier_guild(interaction)
        if guild is None:
            return
        try:
            _, saved = await _fetch_tier_data(guild)
        except Exception:
            await interaction.followup.send("⚠️ 사이트 서버에 연결하지 못했어요.", ephemeral=True)
            return
        roles = _tier_role_map(guild, saved)
        head = "저장된 연결" if saved else "저장된 연결이 없어 이름이 같은 역할을 씁니다"
        await interaction.followup.send(f"**{head}**\n{_map_text(guild, roles)}", ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())

    @tier_group.command(name="만들기", description="티어 역할이 없는 서버용: 아이언~챌린저 역할을 새로 만들고 연결합니다.")
    async def cmd_tier_create(interaction: discord.Interaction):
        guild = await _tier_guild(interaction)
        if guild is None:
            return
        if not guild.me.guild_permissions.manage_roles:
            await interaction.followup.send("봇에 '역할 관리' 권한이 없어요. 봇을 다시 초대하거나 봇 역할에 권한을 주세요.", ephemeral=True)
            return
        try:
            _, saved = await _fetch_tier_data(guild)
        except Exception:
            saved = {}
        existing = _tier_role_map(guild, saved)
        made = []
        try:
            for code, name, color in TIER_ROLES:
                if code not in existing:
                    existing[code] = await guild.create_role(name=f"{TIER_ROLE_PREFIX}{name}", colour=discord.Colour(color),
                                                             reason="carry.gg 티어 역할 만들기")
                    made.append(name)
        except discord.Forbidden:
            await interaction.followup.send("역할을 만들 권한이 없어요.", ephemeral=True)
            return
        try:
            await _save_tier_map(interaction, {c: r.id for c, r in existing.items()})
        except Exception:
            pass
        msg = f"✅ 만든 역할: {', '.join(made)}" if made else "모든 티어에 이미 역할이 연결돼 있어요."
        await interaction.followup.send(msg + "\n봇 역할이 이 역할들보다 위에 있어야 역할을 달아 줄 수 있어요 (서버 설정 → 역할에서 끌어 올리기).",
                                        ephemeral=True)

    @tier_group.command(name="맞추기", description="라이엇 인증 멤버의 티어 역할을 지금 바로 맞춥니다.")
    async def cmd_tier_sync(interaction: discord.Interaction):
        guild = await _tier_guild(interaction)
        if guild is None:
            return
        res = await sync_tier_roles(guild)
        if res.get("error"):
            await interaction.followup.send(f"⚠️ {res['error']}", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ 인증 멤버 {res['checked']}명 확인, {res['changed']}명 역할을 바꿨어요. "
                                            "(라이엇 로그인으로 계정을 인증한 멤버만 대상)", ephemeral=True)

    bot.tree.add_command(tier_group)

    # 1. /전적 커맨드
    @bot.tree.command(name="전적", description="소환사의 솔로랭크 티어, 최근 20전 승률/KDA 및 모스트 챔피언을 조회합니다.")
    @app_commands.describe(소환사="소환사명#태그 (예: 닉네임#KR1)")
    async def cmd_search(interaction: discord.Interaction, 소환사: str):
        await interaction.response.defer()
        target_name = 소환사.strip()
        url = f"{API_BASE_URL}/api/search?q={aiohttp.helpers.quote(target_name)}"

        try:
            async with bot.session.get(url, timeout=6.0) as resp:
                if resp.status != 200:
                    await interaction.followup.send(f"❌ 소환사 **{target_name}**의 전적을 찾을 수 없습니다.")
                    return
                data = await resp.json()

            mode = data.get("mode")
            if mode == "champion":
                c = data.get("champion_stats", {}).get("champion", {})
                await interaction.followup.send(f"💡 `{target_name}`은(는) 챔피언명입니다. `/티어` 커맨드를 사용해주세요.")
                return

            player = data.get("player")
            if not player and data.get("results"):
                player = data.get("results")[0]

            if not player:
                await interaction.followup.send(f"❌ `{target_name}`에 대한 소환사 정보가 존재하지 않습니다.")
                return

            name = player.get("game_name", "")
            tag = player.get("tag_line", "")
            tier_text = player.get("display_tier") or player.get("tier") or "언랭크"
            wins, losses = player.get("wins") or 0, player.get("losses") or 0
            link = f"{SITE_URL}/summoner/{aiohttp.helpers.quote(f'{name}-{tag}')}" if SITE_URL else None
            embed = discord.Embed(title=f"{name}#{tag}", url=link, color=0x5865F2)
            if player.get("profile_icon_id") is not None:
                embed.set_thumbnail(url=f"{DDRAGON_CDN}/img/profileicon/{player['profile_icon_id']}.png")
            lp = f" {player.get('league_points'):,} LP" if player.get("league_points") is not None and player.get("tier") not in (None, "UNRANKED") else ""
            embed.add_field(name="솔로랭크", value=f"**{tier_text}**{lp}", inline=True)
            if wins + losses:
                embed.add_field(name="승률", value=f"**{round(wins / (wins + losses) * 100, 1)}%** ({wins}승 {losses}패)", inline=True)
            if player.get("summoner_level"):
                embed.add_field(name="레벨", value=f"Lv.{player['summoner_level']}", inline=True)
            masteries = player.get("top_masteries") or []
            if masteries:
                embed.add_field(name="숙련도", value="\n".join(f"• {m.get('name')} Lv.{m.get('level')} ({m.get('points', 0):,})" for m in masteries[:3]), inline=False)
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Command /전적 error: {e}")
            await interaction.followup.send("⚠️ 전적 조회 중 일시적인 서버 통신 오류가 발생했습니다.")

    # 2. /티어 커맨드
    @bot.tree.command(name="티어", description="라인별 챔피언 티어, 승률, 픽률, 카운터 3종을 조회합니다.")
    @app_commands.describe(
        라인="라인 포지션 선택",
        챔피언="챔피언 이름 (예: 야스오, 리 신, 아리)"
    )
    @app_commands.choices(라인=[
        app_commands.Choice(name="전체 (ALL)", value="all"),
        app_commands.Choice(name="탑 (TOP)", value="TOP"),
        app_commands.Choice(name="정글 (JUG)", value="JUG"),
        app_commands.Choice(name="미드 (MID)", value="MID"),
        app_commands.Choice(name="원딜 (BOT)", value="BOT"),
        app_commands.Choice(name="서포터 (SUP)", value="SUP")
    ])
    async def cmd_tier(interaction: discord.Interaction, 라인: app_commands.Choice[str], 챔피언: str = ""):
        await interaction.response.defer()
        pos_val = 라인.value
        url = f"{API_BASE_URL}/api/champion-analytics?position={pos_val}&tier=EMERALD_PLUS"

        try:
            async with bot.session.get(url, timeout=5.0) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ 챔피언 티어표 데이터를 불러올 수 없습니다.")
                    return
                data = await resp.json()

            results = data.get("results", [])
            champ_query = 챔피언.strip().replace(" ", "")

            if champ_query:
                matched = [c for c in results if champ_query in c.get("name", "").replace(" ", "") or champ_query.lower() in c.get("id", "").lower()]
                if not matched:
                    await interaction.followup.send(f"❌ `{챔피언}`에 해당하는 챔피언을 찾을 수 없습니다.")
                    return
                c = matched[0]
                embed = discord.Embed(
                    title=f"⚔️ [carry.gg] {c.get('name')} ({c.get('id')}) 메타 티어 리포트",
                    color=0xF59E0B if c.get("tier") in ("OP", "1티어") else 0x38BDF8
                )
                embed.set_thumbnail(url=c.get("image"))
                embed.add_field(name="🏆 메타 티어", value=f"**{c.get('tier')}** (순위 #{c.get('rank')}위)", inline=True)
                embed.add_field(name="📈 승률 / 픽률", value=f"승률 **{c.get('win_rate')}%** | 픽률 **{c.get('pick_rate')}%**", inline=True)
                embed.add_field(name="🚫 밴률", value=f"**{c.get('ban_rate')}%** {c.get('ban_badge', '')}", inline=True)

                counters = c.get("counters", [])
                if counters:
                    c_text = ", ".join([f"**{x.get('name')}**({x.get('win_rate')}%)" for x in counters[:3]])
                    embed.add_field(name="⚠️ 상대하기 힘든 카운터 TOP 3", value=c_text, inline=False)

                embed.set_footer(text=f"carry.gg {data.get('patch') or ''} 패치 · {라인.name} · 표본 {c.get('games', 0):,}판")
                await interaction.followup.send(embed=embed)
            else:
                top5 = results[:5]
                top_text = "\n".join([f"• **#{c.get('rank')} {c.get('name')}**: {c.get('tier')} (승률 {c.get('win_rate')}% · 픽률 {c.get('pick_rate')}%)" for c in top5])
                embed = discord.Embed(
                    title=f"👑 [carry.gg] {라인.name} 1티어 & OP 챔피언 골드 라인업",
                    description=top_text,
                    color=0xF59E0B
                )
                embed.set_footer(text="carry.gg 에메랄드+ 티어표 • 특정 챔피언은 '/티어 [라인] [챔피언명]'으로 상세 조회")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Command /티어 error: {e}")
            await interaction.followup.send("⚠️ 챔피언 티어 조회 중 오류가 발생했습니다.")

    # 3. /멀티서치 커맨드
    @bot.tree.command(name="멀티서치", description="픽창 로비 채팅을 붙여넣어 5인 아군의 전적과 연승/연패를 분석합니다.")
    @app_commands.describe(픽창텍스트="픽창 복사 텍스트 (예: Hide on bush님이 로비에 참가하셨습니다...)")
    async def cmd_multisearch(interaction: discord.Interaction, 픽창텍스트: str):
        await interaction.response.defer()
        url = f"{API_BASE_URL}/api/multisearch"

        try:
            async with bot.session.post(url, json={"raw_text": 픽창텍스트}, timeout=8.0) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ 5인 멀티서치 분석에 실패했습니다.")
                    return
                data = await resp.json()

            players = data.get("players", [])
            embed = discord.Embed(title="멀티서치", color=0x10B981)
            lines = []
            for p in players:
                if not p.get("found", True):
                    lines.append(f"• **{p.get('game_name', '?')}**: 찾을 수 없음")
                    continue
                w, l = p.get("wins") or 0, p.get("losses") or 0
                rec = f"{round(w / (w + l) * 100, 1)}% ({w}승 {l}패)" if w + l else "랭크 기록 없음"
                tier = (p.get("tier") or "UNRANKED")
                tier_txt = "언랭크" if tier == "UNRANKED" else f"{tier} {p.get('rank_tier') or ''}".strip()
                col = p.get("collected") or {}
                champs = ", ".join(c.get("name", "") for c in (col.get("top_champions") or [])[:3])
                lines.append(f"• **{p.get('game_name')}#{p.get('tag_line', '')}**: {tier_txt} · {rec}" + (f" · {champs}" if champs else ""))
            embed.add_field(name="소환사", value="\n".join(lines)[:1000] if lines else "소환사 없음", inline=False)
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Command /멀티서치 error: {e}")
            await interaction.followup.send("⚠️ 멀티서치 분석 중 오류가 발생했습니다.")

    # 4. /듀오 커맨드
    # 4. /구인 · /구인글 : 웹사이트 구인 게시판과 같은 글 (게임별)
    GAME_CHOICES = [
        app_commands.Choice(name="롤", value="lol"),
        app_commands.Choice(name="배그", value="pubg"),
        app_commands.Choice(name="옵치", value="overwatch"),
    ]

    def _bot_headers():
        return {"X-Bot-Secret": BOT_API_SECRET}

    def _member_of(interaction: discord.Interaction) -> dict:
        """명령을 쓴 사람 + 그 디스코드 서버 (서버마다 구인글·내전이 따로 저장된다)"""
        m = {"discord_id": str(interaction.user.id), "discord_name": interaction.user.display_name[:32]}
        if interaction.guild_id:
            m["guild_id"] = str(interaction.guild_id)
        return m

    def _error_text(data) -> str:
        """서버 입력 검사 메시지 ('Value error, 티어를 알아보지 못했어요…') 를 그대로 보여 준다"""
        detail = data.get("detail") if isinstance(data, dict) else None
        if isinstance(detail, list) and detail and isinstance(detail[0], dict):
            return str(detail[0].get("msg", "")).replace("Value error, ", "")
        return detail if isinstance(detail, str) else ""

    async def _queue_autocomplete(interaction: discord.Interaction, current: str):
        """큐 칸: 고른 게임의 큐를 보여 주고, '솔랭'·'롤체' 같은 줄임말로 쳐도 맞는 큐가 뜬다"""
        game = getattr(interaction.namespace, "게임", None) or "lol"
        cfg = duo_games.get_game(game) if duo_games else None
        if not cfg:
            return []
        key = "".join(current.split()).lower()
        picked = []
        for q in cfg["queues"]:
            names = [q] + (cfg.get("queue_aliases") or {}).get(q, [])
            if not key or any(key in "".join(n.split()).lower() for n in names):
                picked.append(app_commands.Choice(name=q, value=q))
        return picked[:25]

    class JoinView(discord.ui.View):
        """목록의 글마다 '같이해요' 버튼. 누른 사람의 디스코드 계정으로 참가 (웹 로그인과 같은 사람으로 셈)"""
        def __init__(self, posts):
            super().__init__(timeout=600)
            for idx, p in enumerate(posts[:5]):
                btn = discord.ui.Button(label=f"#{idx + 1} 같이해요", style=discord.ButtonStyle.success,
                                        disabled=bool(p.get("is_full")))
                btn.callback = self._make_cb(p)
                self.add_item(btn)

        def _make_cb(self, post):
            async def cb(interaction: discord.Interaction):
                if not BOT_API_SECRET:
                    await interaction.response.send_message("봇 연동이 설정되지 않았어요. 웹사이트에서 참가해 주세요.", ephemeral=True)
                    return
                member = _member_of(interaction)
                try:
                    async with bot.session.post(f"{API_BASE_URL}/api/bot/duo-posts/{post['id']}/join",
                                                json=member, headers=_bot_headers(), timeout=5) as resp:
                        data = await resp.json(content_type=None)
                        status = resp.status
                except Exception:
                    await interaction.response.send_message("⚠️ 서버에 연결하지 못했어요.", ephemeral=True)
                    return
                if status == 200 and data.get("status") == "ok":
                    p = data["post"]
                    msg = f"✅ 참가했어요: **{p.get('title', '')}** ({p.get('current_members')}/{p.get('max_members')}명)"
                elif status == 200:
                    msg = "이미 참가한 글이에요."
                elif status == 409:
                    msg = data.get("detail") if isinstance(data, dict) and isinstance(data.get("detail"), str) else "이미 마감된 글이에요."
                elif status == 429:
                    msg = "잠시 후 다시 눌러 주세요."
                else:
                    msg = "참가하지 못했어요. 웹사이트에서 다시 시도해 주세요."
                await interaction.response.send_message(msg, ephemeral=True)
            return cb

    @bot.tree.command(name="구인", description="지금 올라온 구인글을 보고 바로 '같이해요'로 참가합니다.")
    @app_commands.describe(게임="게임 선택")
    @app_commands.choices(게임=GAME_CHOICES)
    async def cmd_recruit_list(interaction: discord.Interaction, 게임: app_commands.Choice[str]):
        await interaction.response.defer()
        try:
            async with bot.session.get(f"{API_BASE_URL}/api/duo-posts", params={"game": 게임.value}, timeout=5) as resp:
                data = await resp.json(content_type=None) if resp.status == 200 else {}
        except Exception:
            data = {}
        posts = [p for p in (data.get("posts") or []) if not p.get("is_full")][:5]
        if not posts:
            await interaction.followup.send(f"지금 올라온 {게임.name} 구인글이 없어요. `/구인글`로 직접 올려 보세요.")
            return
        embed = discord.Embed(title=f"🎮 {게임.name} 구인 중", url=SITE_URL or None, color=0x10B981)
        for idx, p in enumerate(posts):
            who = p.get("author") or p.get("game_name") or ""
            room = p.get("discord_voice_url") or p.get("room_link")
            line = f"{p.get('queue_type', '')} · {p.get('current_members', 1)}/{p.get('max_members', 2)}명 · {p.get('tier_label') or p.get('tier_kr', '')} · {who}"
            if room:
                line += f"\n[음성방 입장]({room})"
            embed.add_field(name=f"#{idx + 1} {p.get('title', '')}", value=line[:1000], inline=False)
        await interaction.followup.send(embed=embed, view=JoinView(posts))

    class MyPostsView(discord.ui.View):
        """내 구인글마다 [마감/다시 모집] [삭제] 버튼 (누른 사람이 작성자일 때만 서버가 받아 준다)"""
        def __init__(self, posts):
            super().__init__(timeout=600)
            for idx, p in enumerate(posts[:5]):
                toggle = discord.ui.Button(label=f"#{idx + 1} {'다시 모집' if p.get('is_full') else '마감'}",
                                           style=discord.ButtonStyle.secondary, row=idx)
                toggle.callback = self._make_cb(p, "toggle")
                delete = discord.ui.Button(label=f"#{idx + 1} 삭제", style=discord.ButtonStyle.danger, row=idx)
                delete.callback = self._make_cb(p, "delete")
                self.add_item(toggle)
                self.add_item(delete)

        def _make_cb(self, post, action):
            async def cb(interaction: discord.Interaction):
                member = _member_of(interaction)
                try:
                    async with bot.session.post(f"{API_BASE_URL}/api/bot/duo-posts/{post['id']}/{action}",
                                                json=member, timeout=5) as resp:
                        status = resp.status
                        data = await resp.json(content_type=None)
                except Exception:
                    await interaction.response.send_message("⚠️ 서버에 연결하지 못했어요.", ephemeral=True)
                    return
                if status == 200 and action == "delete":
                    msg = f"🗑️ 삭제했어요: **{post.get('title', '')}**"
                elif status == 200:
                    msg = "🔴 마감했어요." if data.get("post", {}).get("is_full") else "🟢 다시 모집 중이에요."
                elif status == 404:
                    msg = "이미 없어진 글이에요."
                elif status == 429:
                    msg = "잠시 후 다시 눌러 주세요."
                else:
                    msg = data.get("detail") if isinstance(data, dict) and isinstance(data.get("detail"), str) else "바꾸지 못했어요."
                await interaction.response.send_message(msg, ephemeral=True)
            return cb

    @bot.tree.command(name="내구인", description="내가 올린 구인글을 보고 마감·다시 모집·삭제합니다.")
    async def cmd_my_posts(interaction: discord.Interaction):
        if not BOT_API_SECRET:
            await interaction.response.send_message("봇 연동이 설정되지 않았어요. 웹사이트에서 관리해 주세요.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        member = _member_of(interaction)
        try:
            async with bot.session.post(f"{API_BASE_URL}/api/bot/duo-posts/mine", json=member, timeout=5) as resp:
                data = await resp.json(content_type=None) if resp.status == 200 else {}
        except Exception:
            data = {}
        posts = (data.get("posts") or [])[:5]
        if not posts:
            await interaction.followup.send("지금 올라가 있는 내 구인글이 없어요.", ephemeral=True)
            return
        embed = discord.Embed(title="📋 내 구인글", color=0x5865F2)
        for idx, p in enumerate(posts):
            state = "🔴 마감" if p.get("is_full") else "🟢 모집 중"
            embed.add_field(name=f"#{idx + 1} {p.get('title', '')}"[:250],
                            value=f"{state} · {p.get('queue_type', '')} · {p.get('current_members', 1)}/{p.get('max_members', 2)}명 · {p.get('created_at', '')}",
                            inline=False)
        await interaction.followup.send(embed=embed, view=MyPostsView(posts), ephemeral=True)

    @bot.tree.command(name="구인글", description="디스코드에서 바로 구인글을 올립니다 (웹사이트·채널에 같이 올라감).")
    @app_commands.describe(게임="게임", 큐="큐 (줄임말 OK: 솔랭·자랭·일반·칼바·증칼·롤체·아레나·내전)",
                           티어="내 티어 (줄임말·범위 OK: 다이아1, 에2, 그마, 브~다)", 제목="한 줄 제목", 닉네임="게임 닉네임 (롤·옵치는 닉네임#태그)",
                           포지션="내 포지션 (롤은 필수, 칼바람·아레나·롤체는 비워 두기)",
                           인원="최대 인원 (비우면 큐 기본 인원, 롤체는 1~8명)")
    @app_commands.autocomplete(큐=_queue_autocomplete)
    @app_commands.choices(게임=GAME_CHOICES, 포지션=[
        app_commands.Choice(name=n, value=v) for n, v in (("탑", "TOP"), ("정글", "JUG"), ("미드", "MID"), ("원딜", "BOT"),
                                                         ("서포터·지원", "SUP"), ("탱커", "TANK"), ("딜러", "DPS"))])
    async def cmd_recruit_post(interaction: discord.Interaction, 게임: app_commands.Choice[str], 큐: str, 티어: str, 제목: str, 닉네임: str,
                               포지션: Optional[app_commands.Choice[str]] = None,
                               인원: Optional[app_commands.Range[int, 1, 10]] = None):
        if not BOT_API_SECRET:
            await interaction.response.send_message("봇 연동이 설정되지 않았어요. 웹사이트에서 글을 올려 주세요.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        name, _, tag = 닉네임.partition("#")
        body = {"game": 게임.value, "game_name": name.strip()[:16], "tag_line": tag.strip()[:5], "queue_type": 큐.strip(),
                "tier_kr": 티어.strip(), "title": 제목.strip()[:60],
                "member": _member_of(interaction)}
        # 포지션 필수 여부·큐 줄임말·티어 범위는 서버가 판단하고, 틀리면 이유를 돌려준다
        if 포지션 is not None and 게임.value != "pubg":
            body["my_position"] = 포지션.value
        if 인원 is not None:
            body["max_members"] = 인원
        # 음성 채널에 들어가 있으면 그 채널 링크를 글에 붙인다 (누르면 바로 입장)
        vc = getattr(getattr(interaction.user, "voice", None), "channel", None)
        if vc is not None and interaction.guild_id:
            body["discord_voice_url"] = f"https://discord.com/channels/{interaction.guild_id}/{vc.id}"
            body["discord_channel_name"] = vc.name[:40]
        try:
            async with bot.session.post(f"{API_BASE_URL}/api/bot/duo-posts", json=body, headers=_bot_headers(), timeout=5) as resp:
                status = resp.status
                data = await resp.json(content_type=None)
        except Exception:
            await interaction.followup.send("⚠️ 서버에 연결하지 못했어요.", ephemeral=True)
            return
        if status == 200:
            await interaction.followup.send("✅ 구인글을 올렸어요. 채널에 곧 표시됩니다.", ephemeral=True)
        elif status == 422:
            why = _error_text(data) or "큐·티어는 게임에 맞는 이름으로 적어 주세요."
            await interaction.followup.send(f"입력값을 확인해 주세요: {why}", ephemeral=True)
        elif status == 429:
            await interaction.followup.send("너무 자주 올렸어요. 잠시 후 다시 시도해 주세요.", ephemeral=True)
        else:
            await interaction.followup.send(f"올리지 못했어요 ({data.get('detail', status) if isinstance(data, dict) else status}).", ephemeral=True)

    # 4-1. /내전 : 음성 채널 사람들을 실력·라인을 맞춰 5:5·여러 판·토너먼트·리그로
    @bot.tree.command(name="내전", description="음성 채널 사람들(10~80명)을 실력·라인을 맞춰 5:5·여러 판·토너먼트·리그로 나눕니다.")
    @app_commands.describe(
        방식="진행 방식 (기본: 자동)",
        나누기="방 나누기 방식 (기본: 모든 판 균형, 여러 판일 때만 적용)",
        범위="참가자 모을 음성 채널 범위 (기본: 내 음성 채널)",
    )
    @app_commands.choices(
        방식=[
            app_commands.Choice(name="자동", value="auto"),
            app_commands.Choice(name="5:5 한 판", value="single"),
            app_commands.Choice(name="여러 판 동시", value="multi"),
            app_commands.Choice(name="토너먼트", value="tournament"),
            app_commands.Choice(name="리그", value="league"),
        ],
        나누기=[
            app_commands.Choice(name="모든 판 균형", value="balanced"),
            app_commands.Choice(name="실력대별 방", value="tiered"),
        ],
        범위=[
            app_commands.Choice(name="내 음성 채널", value="channel"),
            app_commands.Choice(name="같은 카테고리의 모든 음성 채널", value="category"),
        ],
    )
    async def cmd_inhouse(
        interaction: discord.Interaction,
        방식: Optional[app_commands.Choice[str]] = None,
        나누기: Optional[app_commands.Choice[str]] = None,
        범위: Optional[app_commands.Choice[str]] = None,
    ):
        voice = getattr(interaction.user, "voice", None)
        channel = voice.channel if voice else None
        if channel is None:
            await interaction.response.send_message("먼저 내전할 음성 채널에 들어가 주세요.", ephemeral=True)
            return

        mode = 방식.value if 방식 else "auto"
        split = 나누기.value if 나누기 else "balanced"
        scope = 범위.value if 범위 else "channel"

        vcs = [channel]
        if scope == "category" and getattr(channel, "category", None) is not None:
            vcs = getattr(channel.category, "voice_channels", None) or [c for c in channel.category.channels if isinstance(c, discord.VoiceChannel)]

        seen = set()
        people = []
        for vc in vcs:
            for m in vc.members:
                if m.bot or m.id in seen:
                    continue
                seen.add(m.id)
                people.append(m)

        if len(people) < 10:
            await interaction.response.send_message(f"음성 채널에 10명 이상 있어야 해요 (지금 {len(people)}명).", ephemeral=True)
            return

        capped_note = ""
        if len(people) > 80:
            capped_note = "참가자가 80명을 넘어 앞의 80명만 진행해요.\n"
            people = people[:80]

        if not BOT_API_SECRET:
            await interaction.response.send_message("봇 연동이 설정되지 않았어요. 웹사이트 서버 랭킹 화면의 '내전 팀 짜기'를 써 주세요.", ephemeral=True)
            return

        await interaction.response.defer()
        body = {
            "members": [{"discord_id": str(m.id), "discord_name": m.display_name[:32]} for m in people],
            "requested_by": _member_of(interaction),
            "mode": mode,
            "split": split,
        }
        try:
            async with bot.session.post(f"{API_BASE_URL}/api/bot/inhouse/plan", json=body, headers=_bot_headers(), timeout=20) as resp:
                status = resp.status
                data = await resp.json(content_type=None)
        except Exception:
            await interaction.followup.send("⚠️ 서버에 연결하지 못했어요.")
            return

        if status != 200 or not isinstance(data, dict):
            why = _error_text(data) if isinstance(data, dict) else ""
            await interaction.followup.send("팀을 나누지 못했어요: " + (why or str(status)))
            return

        def player_line(p: dict) -> str:
            lane_map = {"TOP": "탑", "JUNGLE": "정글", "MID": "미드", "ADC": "원딜", "SUPPORT": "서폿"}
            lane = lane_map.get(p.get("lane"), p.get("lane") or "")
            fit = "(부)" if p.get("lane_fit") == "sub" else ("(비주)" if p.get("lane_fit") == "off" else "")
            est = " (추정)" if not p.get("linked") else ""
            rating = p.get("rating_label") or ""
            name = p.get("name") or ""
            mid = f" · {rating}" if rating else ""
            return f"{lane}{fit} · {name}{mid}{est}"

        actual_mode = data.get("mode") or mode
        waitlist = data.get("waitlist") or []
        wait_text = ""
        if waitlist:
            wait_names = ", ".join(p.get("name") or "" for p in waitlist if p.get("name"))
            if wait_names:
                wait_text = f"대기: {wait_names} (다음 판에 먼저)\n"
        if capped_note:
            wait_text = f"{capped_note}{wait_text}"

        if actual_mode in ("single", "multi"):
            games = data.get("games") or []
            if not games:
                await interaction.followup.send("팀을 나누지 못했어요.")
                return

            def team_text(team: dict) -> str:
                lines = [player_line(p) for p in team.get("players", [])]
                if team.get("average_label"):
                    lines.append(f"평균: {team['average_label']}")
                return "\n".join(lines)

            by = body["requested_by"]
            seat = lambda team: [{"name": (p.get("name") or "")[:40], "discord_id": p.get("discord_id")} for p in team.get("players", [])]

            for idx, g in enumerate(games):
                options = g.get("options") or []
                if not options:
                    continue
                best = options[0]
                if actual_mode == "single":
                    title = f"⚔️ 내전 팀 ({channel.name})"
                else:
                    room_no = g.get("room") or (idx + 1)
                    title = f"⚔️ {room_no}번 방"

                diff = best.get("diff", 0)
                penalty = best.get("lane_penalty", 0)
                desc = f"점수 차 {diff} · 라인 손실 {penalty}"
                if idx == 0 and wait_text:
                    desc = f"{wait_text}{desc}"

                embed = discord.Embed(title=title, color=0x5865F2, description=desc[:4000])
                embed.add_field(name="🔵 블루", value=team_text(best["blue"])[:1000], inline=True)
                embed.add_field(name="🔴 레드", value=team_text(best["red"])[:1000], inline=True)
                embed.set_footer(text="티어는 사이트에 등록·인증한 계정 기준 · 끝나면 이긴 팀을 눌러 기록")

                game_id = None
                try:
                    async with bot.session.post(
                        f"{API_BASE_URL}/api/bot/inhouse/games",
                        headers=_bot_headers(),
                        timeout=5,
                        json={"blue": seat(best["blue"]), "red": seat(best["red"]), "requested_by": by}
                    ) as gresp:
                        if gresp.status == 200:
                            gdata = await gresp.json(content_type=None)
                            if isinstance(gdata, dict):
                                game_id = gdata.get("id")
                except Exception:
                    pass

                if game_id:
                    await interaction.followup.send(embed=embed, view=InhouseResultView(game_id))
                else:
                    await interaction.followup.send(embed=embed)

        elif actual_mode in ("tournament", "league"):
            teams = data.get("teams") or []
            matches = data.get("matches") or []
            if not teams:
                await interaction.followup.send("팀을 나누지 못했어요.")
                return

            site_guide = f"대회 진행·결과 기록은 사이트에서: {SITE_URL}/?tab=serverranking" if SITE_URL else "대회 진행·결과 기록은 사이트 서버 랭킹 탭에서"
            mode_label = "토너먼트" if actual_mode == "tournament" else "리그"

            embeds = []
            if len(teams) <= 8:
                emb = discord.Embed(
                    title=f"⚔️ 내전 {mode_label} 팀",
                    color=0x5865F2,
                    description=wait_text.strip() if wait_text else None
                )
                for t in teams:
                    name_val = f"{t.get('name', '팀')} ({t.get('average_label', '')})"
                    val = "\n".join(player_line(p) for p in t.get("players", []))
                    emb.add_field(name=name_val[:250], value=val[:1000], inline=True)
                emb.set_footer(text=site_guide)
                embeds.append(emb)
            else:
                emb1 = discord.Embed(
                    title=f"⚔️ 내전 {mode_label} 팀 (1)",
                    color=0x5865F2,
                    description=wait_text.strip() if wait_text else None
                )
                for t in teams[:8]:
                    name_val = f"{t.get('name', '팀')} ({t.get('average_label', '')})"
                    val = "\n".join(player_line(p) for p in t.get("players", []))
                    emb1.add_field(name=name_val[:250], value=val[:1000], inline=True)
                emb1.set_footer(text=site_guide)
                embeds.append(emb1)

                emb2 = discord.Embed(
                    title=f"⚔️ 내전 {mode_label} 팀 (2)",
                    color=0x5865F2
                )
                for t in teams[8:]:
                    name_val = f"{t.get('name', '팀')} ({t.get('average_label', '')})"
                    val = "\n".join(player_line(p) for p in t.get("players", []))
                    emb2.add_field(name=name_val[:250], value=val[:1000], inline=True)
                emb2.set_footer(text=site_guide)
                embeds.append(emb2)

            rounds = {}
            for m in matches:
                rnd = m.get("round", 1)
                rounds.setdefault(rnd, []).append(m)

            lines = []
            for rnd in sorted(rounds.keys()):
                r_strs = []
                for m in rounds[rnd]:
                    a_idx, b_idx = m.get("a"), m.get("b")
                    name_a = teams[a_idx]["name"] if a_idx is not None and a_idx < len(teams) else None
                    name_b = teams[b_idx]["name"] if b_idx is not None and b_idx < len(teams) else None
                    if name_a and name_b:
                        r_strs.append(f"{name_a} vs {name_b}")
                    elif name_a:
                        r_strs.append(f"{name_a} (부전승)")
                    elif name_b:
                        r_strs.append(f"{name_b} (부전승)")
                if r_strs:
                    lines.append(f"{rnd}라운드: {', '.join(r_strs)}")

            schedule_title = "⚔️ 토너먼트 대진" if actual_mode == "tournament" else "⚔️ 리그 일정"
            sched_body = "\n".join(lines)
            desc_text = f"{sched_body}\n\n{site_guide}" if sched_body else site_guide
            match_emb = discord.Embed(
                title=schedule_title,
                color=0x5865F2,
                description=desc_text[:4000]
            )
            match_emb.set_footer(text=site_guide)
            embeds.append(match_emb)

            guild_str = interaction.guild.name if interaction.guild else ""
            event_title = f"{guild_str} 내전 {mode_label}".strip()[:40]
            create_view = EventCreateView(
                creator_id=interaction.user.id,
                mode=actual_mode,
                title=event_title,
                teams=teams,
                matches=matches,
            )
            await interaction.followup.send(embeds=embeds, view=create_view)
        else:
            await interaction.followup.send("팀을 나누지 못했어요.")

    @bot.tree.command(name="배그", description="배그 닉네임으로 이번 시즌 경쟁전 기록을 봅니다 (사이트에 PUBG 키가 있어야 함).")
    @app_commands.describe(닉네임="배그 닉네임", 플랫폼="카카오 또는 스팀")
    @app_commands.choices(플랫폼=[app_commands.Choice(name="카카오", value="kakao"), app_commands.Choice(name="스팀", value="steam")])
    async def cmd_pubg(interaction: discord.Interaction, 닉네임: str, 플랫폼: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer()
        platform = 플랫폼.value if 플랫폼 else "kakao"
        try:
            async with bot.session.get(f"{API_BASE_URL}/api/pubg/player", params={"name": 닉네임.strip(), "platform": platform}, timeout=10) as resp:
                status = resp.status
                data = await resp.json(content_type=None)
        except Exception:
            await interaction.followup.send("⚠️ 서버에 연결하지 못했어요.")
            return
        if status != 200:
            msg = data.get("detail") if isinstance(data, dict) and isinstance(data.get("detail"), str) else "조회하지 못했어요."
            await interaction.followup.send(msg)
            return
        r = data.get("ranked")
        embed = discord.Embed(title=f"{discord.utils.escape_markdown(data.get('name', ''))} ({'스팀' if platform == 'steam' else '카카오'})", color=0xF2A900)
        if not r:
            embed.description = "이번 시즌 경쟁전 기록이 없어요."
        else:
            embed.add_field(name="티어", value=f"**{r.get('tier') or '-'} {r.get('sub_tier') or ''}** ({r.get('rank_point') or 0} RP)", inline=True)
            embed.add_field(name="판수", value=f"{r.get('rounds')}판 · {r.get('wins') or 0}승", inline=True)
            if r.get("kda") is not None:
                embed.add_field(name="KDA", value=f"{r['kda']:.2f}", inline=True)
            if r.get("avg_damage") is not None:
                embed.add_field(name="평균 딜량", value=f"{r['avg_damage']:,}", inline=True)
            if r.get("top10_ratio") is not None:
                embed.add_field(name="TOP10", value=f"{round(r['top10_ratio'] * 100, 1)}%", inline=True)
        embed.set_footer(text=f"경쟁전 {r.get('mode')}" if r else "PUBG 공식 API")
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="내전전적", description="최근 30일 내전 승패 순위를 봅니다.")
    async def cmd_inhouse_stats(interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with bot.session.get(f"{API_BASE_URL}/api/inhouse/stats", timeout=5) as resp:
                data = await resp.json(content_type=None) if resp.status == 200 else {}
        except Exception:
            data = {}
        players = (data.get("players") or [])[:10]
        if not players:
            await interaction.followup.send("아직 기록된 내전이 없어요. `/내전`으로 팀을 나누고 끝나면 이긴 팀을 눌러 주세요.")
            return
        lines = [f"{i}. **{discord.utils.escape_markdown(p['name'])}** {p['wins']}승 {p['losses']}패 ({p['win_rate']}%)"
                 for i, p in enumerate(players, start=1)]
        embed = discord.Embed(title="🏆 내전 전적 (최근 30일)", url=SITE_URL or None, description="\n".join(lines)[:4000], color=0xF59E0B)
        await interaction.followup.send(embed=embed)

    class InhouseResultView(discord.ui.View):
        """내전이 끝나면 팀을 나눈 사람이 이긴 팀을 누른다"""
        def __init__(self, game_id):
            super().__init__(timeout=6 * 3600)
            self.game_id = game_id
            for label, winner, style in (("🔵 블루 승리", "blue", discord.ButtonStyle.primary),
                                         ("🔴 레드 승리", "red", discord.ButtonStyle.danger)):
                btn = discord.ui.Button(label=label, style=style)
                btn.callback = self._make_cb(winner, label)
                self.add_item(btn)
            code_btn = discord.ui.Button(label="🎟️ 토너먼트 코드", style=discord.ButtonStyle.secondary)
            code_btn.callback = self._code_cb
            self.add_item(code_btn)

        async def _code_cb(self, interaction: discord.Interaction):
            """라이엇 토너먼트 코드: 사설 게임을 이 코드로 만들면 승패·KDA·챔피언이 자동 기록된다"""
            by = _member_of(interaction)
            try:
                async with bot.session.post(f"{API_BASE_URL}/api/bot/inhouse/games/{self.game_id}/code",
                                            json={"requested_by": by}, timeout=10) as resp:
                    status = resp.status
                    data = await resp.json(content_type=None)
            except Exception:
                status, data = 0, {}
            if status == 200:
                note = "\n⚠️ 시험용 코드라 실제 게임에서는 쓸 수 없어요." if data.get("mode") == "stub" else ""
                await interaction.response.send_message(
                    f"🎟️ 토너먼트 코드: `{data.get('code', '')}`\n"
                    "롤 클라이언트 → 플레이 → 사설 게임 오른쪽 위 트로피 아이콘에 붙여 넣고 방을 만드세요. "
                    "게임이 끝나면 결과와 KDA·챔피언이 자동으로 기록돼요." + note)
                return
            detail = (data or {}).get("detail") if isinstance(data, dict) else None
            msg = {403: "팀을 나눈 사람만 코드를 받을 수 있어요.", 429: "잠시 후 다시 눌러 주세요."}.get(
                status, detail if isinstance(detail, str) else "코드를 받지 못했어요.")
            await interaction.response.send_message(msg, ephemeral=True)

        def _make_cb(self, winner, label):
            async def cb(interaction: discord.Interaction):
                by = _member_of(interaction)
                try:
                    async with bot.session.post(f"{API_BASE_URL}/api/bot/inhouse/games/{self.game_id}/result",
                                                json={"winner": winner, "requested_by": by}, timeout=5) as resp:
                        status = resp.status
                except Exception:
                    status = 0
                msg = {200: f"기록했어요: {label}", 403: "팀을 나눈 사람만 결과를 기록할 수 있어요.",
                       409: "하루가 지났거나 라이엇 경기 기록으로 이미 정해진 내전이에요.",
                       429: "잠시 후 다시 눌러 주세요."}.get(status, "기록하지 못했어요.")
                await interaction.response.send_message(msg, ephemeral=status != 200)
            return cb

    async def _event_board(event_id: int, requester: dict):
        """대회 진행판을 그리는 공통 함수. 반환: (embed, view) 또는 (None, 이유)"""
        try:
            async with bot.session.post(
                f"{API_BASE_URL}/api/bot/inhouse/events/{event_id}/view",
                headers=_bot_headers(),
                json={"requested_by": requester},
                timeout=10,
            ) as resp:
                status = resp.status
                data = await resp.json(content_type=None) if resp.status in (200, 400, 403, 404, 422) else {}
        except Exception:
            return None, "서버에 연결하지 못했어요."

        if status != 200 or not isinstance(data, dict):
            why = _error_text(data) if isinstance(data, dict) else ""
            return None, why or f"대회 정보를 불러오지 못했어요 ({status})."

        title = data.get("title") or "내전 대회"
        embed = discord.Embed(title=f"🏆 {title}"[:256], color=0x5865F2)

        desc_lines = []
        teams = data.get("teams") or []
        champ_idx = data.get("champion")
        if champ_idx is not None:
            try:
                c_idx = int(champ_idx)
                c_name = teams[c_idx].get("name") if 0 <= c_idx < len(teams) else f"{c_idx + 1}팀"
            except (ValueError, TypeError):
                c_name = str(champ_idx)
            desc_lines.append(f"🏆 우승: {c_name}\n")

        matches = data.get("matches") or []
        rounds = {}
        for idx, m in enumerate(matches):
            rnd = m.get("round", 1)
            rounds.setdefault(rnd, []).append((idx, m))

        max_round = max(rounds.keys()) if rounds else 1
        mode = data.get("mode") or "tournament"

        for rnd in sorted(rounds.keys()):
            r_matches = rounds[rnd]
            if mode == "tournament" and rnd == max_round and len(r_matches) == 1:
                rnd_label = "결승"
            else:
                rnd_label = f"{rnd}라운드"
            desc_lines.append(f"**{rnd_label}**")

            for idx, m in r_matches:
                a_idx, b_idx = m.get("a"), m.get("b")
                name_a = teams[a_idx].get("name", f"{(a_idx or 0) + 1}팀") if a_idx is not None and a_idx < len(teams) else None
                name_b = teams[b_idx].get("name", f"{(b_idx or 0) + 1}팀") if b_idx is not None and b_idx < len(teams) else None
                winner_idx = m.get("winner")

                if a_idx is None or b_idx is None:
                    bye_team = name_a or name_b or "팀"
                    desc_lines.append(f"{bye_team} (부전승)")
                else:
                    t_vs = f"{name_a} vs {name_b}"
                    if winner_idx is not None:
                        w_name = teams[winner_idx].get("name", f"{winner_idx + 1}팀") if winner_idx < len(teams) else f"{winner_idx + 1}팀"
                        desc_lines.append(f"{t_vs} — ✅ {w_name} 승")
                    elif m.get("game_id"):
                        desc_lines.append(f"{t_vs} — 진행 중")
                    else:
                        desc_lines.append(f"{t_vs} — 대기")
            desc_lines.append("")

        embed.description = "\n".join(desc_lines).strip()[:4000]

        standings = data.get("standings") or []
        if standings:
            st_lines = []
            for i, s in enumerate(standings, start=1):
                s_name = s.get("name") or f"{s.get('team', 0) + 1}팀"
                st_lines.append(f"{i}. {s_name} {s.get('wins', 0)}승 {s.get('losses', 0)}패")
            st_val = "\n".join(st_lines)
            if len(st_val) > 1024:
                st_val = st_val[:1020] + "..."
            embed.add_field(name="📊 순위표", value=st_val, inline=False)

        if SITE_URL:
            embed.set_footer(text=f"사이트에서도 볼 수 있어요: {SITE_URL}/?tab=serverranking")

        view = EventBoardView(event_id, data)
        return embed, view

    class EventCreateView(discord.ui.View):
        """내전 토너먼트/리그 팀 편성이 완료되었을 때 대회 생성을 시작하는 뷰"""
        def __init__(self, creator_id: int, mode: str, title: str, teams: list, matches: list):
            super().__init__(timeout=12 * 3600)
            self.creator_id = creator_id
            self.mode = mode
            self.title = title
            self.teams = teams
            self.matches = matches
            self._started = False

        @discord.ui.button(label="🏆 이 팀으로 대회 시작", style=discord.ButtonStyle.success)
        async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.creator_id:
                await interaction.response.send_message("대회를 연 사람만 시작할 수 있어요.", ephemeral=True)
                return

            if self._started:
                await interaction.response.send_message("이미 대회가 시작되었어요.", ephemeral=True)
                return
            self._started = True

            by = _member_of(interaction)
            clean_teams = [
                {
                    "name": (t.get("name") or "팀")[:20],
                    "players": [
                        {
                            "name": (p.get("name") or "소환사")[:40],
                            "discord_id": str(p["discord_id"]) if p.get("discord_id") and str(p["discord_id"]).isdigit() else None,
                            "lane": p.get("lane"),
                        }
                        for p in t.get("players", [])
                    ],
                }
                for t in self.teams
            ]
            clean_matches = [
                {
                    "round": int(m.get("round", 1)),
                    "a": m.get("a"),
                    "b": m.get("b"),
                }
                for m in self.matches
            ]
            body = {
                "mode": self.mode,
                "title": self.title,
                "teams": clean_teams,
                "matches": clean_matches,
                "requested_by": by,
            }

            try:
                async with bot.session.post(
                    f"{API_BASE_URL}/api/bot/inhouse/events",
                    headers=_bot_headers(),
                    json=body,
                    timeout=10,
                ) as resp:
                    status = resp.status
                    data = await resp.json(content_type=None) if resp.status in (200, 400, 403, 404, 409, 422) else {}
            except Exception:
                status, data = 0, {}

            if status != 200 or not isinstance(data, dict) or not data.get("id"):
                self._started = False
                why = _error_text(data) if isinstance(data, dict) else ""
                await interaction.response.send_message(why or "대회를 저장하지 못했어요.", ephemeral=True)
                return

            event_id = int(data["id"])
            board_embed, board_view = await _event_board(event_id, by)
            if not board_embed or not board_view:
                self._started = False
                await interaction.response.send_message(board_view or "진행판을 불러오지 못했어요.", ephemeral=True)
                return

            button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=board_embed, view=board_view)

    class EventBoardView(discord.ui.View):
        """대회 진행판 버튼 뷰 (시작 / 승리 / 새로고침)"""
        def __init__(self, event_id: int, data: Optional[dict] = None):
            super().__init__(timeout=12 * 3600)
            self.event_id = event_id
            if data:
                self._build_buttons(data)
            else:
                self._add_refresh_button()

        def _add_refresh_button(self):
            ref_btn = discord.ui.Button(label="🔄 새로고침", style=discord.ButtonStyle.secondary)
            ref_btn.callback = self._make_refresh_cb()
            self.add_item(ref_btn)

        def _build_buttons(self, data: dict):
            teams = data.get("teams") or []
            matches = data.get("matches") or []
            mode = data.get("mode") or "tournament"
            champion = data.get("champion")

            # 우승(champion)이 나오거나 리그의 모든 경기가 끝나면 버튼은 "🔄 새로고침" 만.
            is_ended = (champion is not None) or (
                mode == "league" and matches and all(m.get("winner") is not None for m in matches)
            ) or (matches and all(m.get("winner") is not None for m in matches))

            if not is_ended:
                if mode == "tournament":
                    current_round = max((m.get("round", 1) for m in matches), default=1)
                    candidates = [
                        (idx, m) for idx, m in enumerate(matches)
                        if m.get("round") == current_round and m.get("winner") is None and m.get("a") is not None and m.get("b") is not None
                    ]
                else:
                    candidates = [
                        (idx, m) for idx, m in enumerate(matches)
                        if m.get("winner") is None and m.get("a") is not None and m.get("b") is not None
                    ]

                for idx, m in candidates:
                    a_idx, b_idx = m["a"], m["b"]
                    name_a = (teams[a_idx].get("name") if a_idx < len(teams) else f"{a_idx + 1}팀")[:30]
                    name_b = (teams[b_idx].get("name") if b_idx < len(teams) else f"{b_idx + 1}팀")[:30]
                    gid = m.get("game_id")

                    if not gid:
                        if len(self.children) + 1 + 1 > 25:
                            break
                        btn = discord.ui.Button(label=f"▶ {name_a} vs {name_b}"[:80], style=discord.ButtonStyle.secondary)
                        btn.callback = self._make_start_cb(idx)
                        self.add_item(btn)
                    else:
                        if len(self.children) + 2 + 1 > 25:
                            break
                        btn_a = discord.ui.Button(label=f"{name_a} 승"[:80], style=discord.ButtonStyle.primary)
                        btn_a.callback = self._make_result_cb(gid, "blue")
                        self.add_item(btn_a)

                        btn_b = discord.ui.Button(label=f"{name_b} 승"[:80], style=discord.ButtonStyle.danger)
                        btn_b.callback = self._make_result_cb(gid, "red")
                        self.add_item(btn_b)

            self._add_refresh_button()

        def _make_start_cb(self, match_idx: int):
            async def cb(interaction: discord.Interaction):
                by = _member_of(interaction)
                try:
                    async with bot.session.post(
                        f"{API_BASE_URL}/api/bot/inhouse/events/{self.event_id}/matches/{match_idx}/start",
                        headers=_bot_headers(),
                        json={"requested_by": by},
                        timeout=10,
                    ) as resp:
                        status = resp.status
                        data = await resp.json(content_type=None) if resp.status in (200, 400, 403, 404, 409, 422) else {}
                except Exception:
                    status, data = 0, {}

                if status == 200:
                    new_embed, new_view = await _event_board(self.event_id, by)
                    if new_embed and new_view:
                        await interaction.response.edit_message(embed=new_embed, view=new_view)
                    else:
                        await interaction.response.send_message(new_view or "진행판을 갱신하지 못했어요.", ephemeral=True)
                    return

                if status == 403:
                    msg = "대회를 만든 사람만 진행할 수 있어요."
                elif status == 409:
                    msg = "부전승 경기예요."
                elif status == 404:
                    msg = "경기를 찾을 수 없어요."
                else:
                    msg = _error_text(data) if isinstance(data, dict) else ""
                    if not msg:
                        msg = f"경기를 시작하지 못했어요 ({status})."
                await interaction.response.send_message(msg, ephemeral=True)
            return cb

        def _make_result_cb(self, game_id: int, winner: str):
            async def cb(interaction: discord.Interaction):
                by = _member_of(interaction)
                try:
                    async with bot.session.post(
                        f"{API_BASE_URL}/api/bot/inhouse/games/{game_id}/result",
                        headers=_bot_headers(),
                        json={"winner": winner, "requested_by": by},
                        timeout=10,
                    ) as resp:
                        status = resp.status
                        data = await resp.json(content_type=None) if resp.status in (200, 400, 403, 404, 409, 422) else {}
                except Exception:
                    status, data = 0, {}

                if status == 200:
                    new_embed, new_view = await _event_board(self.event_id, by)
                    if new_embed and new_view:
                        await interaction.response.edit_message(embed=new_embed, view=new_view)
                    else:
                        await interaction.response.send_message(new_view or "진행판을 갱신하지 못했어요.", ephemeral=True)
                    return

                if status == 403:
                    msg = "대회를 만든 사람만 진행할 수 있어요."
                elif status == 409:
                    msg = "하루가 지났거나 라이엇 경기 기록으로 이미 정해진 내전이에요."
                elif status == 404:
                    msg = "내전 기록을 찾을 수 없어요."
                else:
                    msg = _error_text(data) if isinstance(data, dict) else ""
                    if not msg:
                        msg = f"결과를 기록하지 못했어요 ({status})."
                await interaction.response.send_message(msg, ephemeral=True)
            return cb

        def _make_refresh_cb(self):
            async def cb(interaction: discord.Interaction):
                by = _member_of(interaction)
                new_embed, new_view = await _event_board(self.event_id, by)
                if new_embed and new_view:
                    await interaction.response.edit_message(embed=new_embed, view=new_view)
                else:
                    await interaction.response.send_message(new_view or "진행판을 갱신하지 못했어요.", ephemeral=True)
            return cb

    # 5. /핑 커맨드
    @bot.tree.command(name="핑", description="디스코드 봇 및 carry.gg 백엔드 서버 지연 시간을 측정합니다.")
    async def cmd_ping(interaction: discord.Interaction):
        await interaction.response.defer()
        bot_latency = round(bot.latency * 1000, 1)
        # 사이트 서버는 실제로 /api/health 를 불러서 확인
        t0 = time.perf_counter()
        try:
            async with bot.session.get(f"{API_BASE_URL}/api/health", timeout=5) as resp:
                ok = resp.status == 200
                backend = f"{'정상' if ok else '오류'} (HTTP {resp.status}, {round((time.perf_counter() - t0) * 1000)}ms)"
        except Exception:
            ok, backend = False, "연결 안 됨"
        embed = discord.Embed(
            title="🏓 퐁! carry.gg 봇 상태",
            description=f"• 디스코드 지연: **{bot_latency}ms**\n• 사이트 서버: **{backend}**",
            color=0x10B981 if ok else 0xEF4444
        )
        await interaction.followup.send(embed=embed)


def main():
    if not HAS_DISCORD_PY:
        print("❌ discord.py 라이브러리가 필요합니다. 'pip install discord.py aiohttp' 를 실행하십시오.")
        sys.exit(1)

    if not BOT_TOKEN:
        print("⚠️ DISCORD_BOT_TOKEN이 .env 파일에 설정되어 있지 않습니다.")
        print("   디스코드 개발자 포털(https://discord.com/developers/applications)에서 봇을 생성하고")
        print("   .env 파일에 DISCORD_BOT_TOKEN=\"your_token_here\" 를 추가한 뒤 다시 실행하세요.")
        sys.exit(0)

    logger.info("🚀 carry.gg 공식 디스코드 봇을 시작합니다...")
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
