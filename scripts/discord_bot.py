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

import os
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
# 사이트 주소 (임베드 제목 링크). 없으면 링크 없이
SITE_URL = os.getenv("SITE_URL", "").strip().rstrip("/")

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

    # 1. /전적 커맨드
    @bot.tree.command(name="전적", description="소환사의 솔로랭크 티어, 최근 20전 승률/KDA 및 모스트 챔피언을 조회합니다.")
    @app_commands.describe(소환사="소환사명#태그 (예: Hide on bush#KR1)")
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
                member = {"discord_id": str(interaction.user.id), "discord_name": interaction.user.display_name[:32]}
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
            line = f"{p.get('queue_type', '')} · {p.get('current_members', 1)}/{p.get('max_members', 2)}명 · {p.get('tier_kr', '')} · {who}"
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
                member = {"discord_id": str(interaction.user.id), "discord_name": interaction.user.display_name[:32]}
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
        member = {"discord_id": str(interaction.user.id), "discord_name": interaction.user.display_name[:32]}
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
    @app_commands.describe(게임="게임", 큐="큐 (롤: 솔로랭크/자유랭크/칼바람 나락/내전, 배그: 경쟁전 스쿼드/일반 스쿼드/일반 듀오, 옵치: 경쟁전/빠른 대전)",
                           티어="내 티어 (예: 골드)", 제목="한 줄 제목", 닉네임="게임 닉네임 (롤·옵치는 닉네임#태그)",
                           포지션="내 포지션 (롤은 필수, 옵치는 선택, 배그는 비워 두기)")
    @app_commands.choices(게임=GAME_CHOICES, 포지션=[
        app_commands.Choice(name=n, value=v) for n, v in (("탑", "TOP"), ("정글", "JUG"), ("미드", "MID"), ("원딜", "BOT"),
                                                         ("서포터·지원", "SUP"), ("탱커", "TANK"), ("딜러", "DPS"))])
    async def cmd_recruit_post(interaction: discord.Interaction, 게임: app_commands.Choice[str], 큐: str, 티어: str, 제목: str, 닉네임: str,
                               포지션: Optional[app_commands.Choice[str]] = None):
        if not BOT_API_SECRET:
            await interaction.response.send_message("봇 연동이 설정되지 않았어요. 웹사이트에서 글을 올려 주세요.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        name, _, tag = 닉네임.partition("#")
        body = {"game": 게임.value, "game_name": name.strip()[:16], "tag_line": tag.strip()[:5], "queue_type": 큐.strip(),
                "tier_kr": 티어.strip(), "title": 제목.strip()[:60],
                "member": {"discord_id": str(interaction.user.id), "discord_name": interaction.user.display_name[:32]}}
        if 게임.value == "lol" and 포지션 is None:
            await interaction.followup.send("롤 구인글은 `포지션`을 골라 주세요.", ephemeral=True)
            return
        if 포지션 is not None and 게임.value != "pubg":
            body["my_position"] = 포지션.value
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
            await interaction.followup.send("입력값을 확인해 주세요 (큐·티어는 게임에 맞는 이름으로).", ephemeral=True)
        elif status == 429:
            await interaction.followup.send("너무 자주 올렸어요. 잠시 후 다시 시도해 주세요.", ephemeral=True)
        else:
            await interaction.followup.send(f"올리지 못했어요 ({data.get('detail', status) if isinstance(data, dict) else status}).", ephemeral=True)

    # 4-1. /내전 : 명령을 쓴 사람이 있는 음성 채널 10명을 티어가 비슷한 두 팀으로
    @bot.tree.command(name="내전", description="내가 들어가 있는 음성 채널의 10명을 티어가 비슷한 5:5 두 팀으로 나눕니다.")
    async def cmd_inhouse(interaction: discord.Interaction):
        voice = getattr(interaction.user, "voice", None)
        channel = voice.channel if voice else None
        if channel is None:
            await interaction.response.send_message("먼저 내전할 음성 채널에 들어가 주세요.", ephemeral=True)
            return
        people = [m for m in channel.members if not m.bot]
        if len(people) != 10:
            await interaction.response.send_message(f"음성 채널에 정확히 10명이 있어야 해요 (지금 {len(people)}명).", ephemeral=True)
            return
        if not BOT_API_SECRET:
            await interaction.response.send_message("봇 연동이 설정되지 않았어요. 웹사이트 서버 랭킹 화면의 '내전 팀 짜기'를 써 주세요.", ephemeral=True)
            return
        await interaction.response.defer()
        body = {"members": [{"discord_id": str(m.id), "discord_name": m.display_name[:32]} for m in people],
                "requested_by": {"discord_id": str(interaction.user.id), "discord_name": interaction.user.display_name[:32]}}
        try:
            async with bot.session.post(f"{API_BASE_URL}/api/bot/inhouse", json=body, timeout=5) as resp:
                status = resp.status
                data = await resp.json(content_type=None)
        except Exception:
            await interaction.followup.send("⚠️ 서버에 연결하지 못했어요.")
            return
        if status != 200 or not data.get("options"):
            await interaction.followup.send("잠시 후 다시 시도해 주세요." if status == 429 else "팀을 나누지 못했어요.")
            return
        best = data["options"][0]

        def team_text(team):
            return "\n".join(
                f"• {p['name']}" + (" (티어 미연결·추정)" if not p.get("linked") else "")
                for p in team["players"]) + f"\n평균: **{team['average_label']}**"

        embed = discord.Embed(title=f"⚔️ 내전 팀 ({channel.name})", color=0x5865F2,
                              description=f"두 팀 점수 차이 {best['diff']} (100 = 디비전 하나)")
        embed.add_field(name="🔵 블루", value=team_text(best["blue"])[:1000], inline=True)
        embed.add_field(name="🔴 레드", value=team_text(best["red"])[:1000], inline=True)
        embed.set_footer(text="티어는 사이트 서버 랭킹에 연결한 계정 기준 · 끝나면 이긴 팀을 눌러 내전 전적에 기록")
        by = body["requested_by"]
        seat = lambda team: [{"name": p["name"][:40], "discord_id": p.get("discord_id")} for p in team["players"]]
        game_id = None
        try:
            async with bot.session.post(f"{API_BASE_URL}/api/bot/inhouse/games", timeout=5,
                                        json={"blue": seat(best["blue"]), "red": seat(best["red"]), "requested_by": by}) as resp:
                if resp.status == 200:
                    game_id = (await resp.json(content_type=None)).get("id")
        except Exception:
            pass
        if game_id:
            await interaction.followup.send(embed=embed, view=InhouseResultView(game_id))
        else:
            await interaction.followup.send(embed=embed)

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

        def _make_cb(self, winner, label):
            async def cb(interaction: discord.Interaction):
                by = {"discord_id": str(interaction.user.id), "discord_name": interaction.user.display_name[:32]}
                try:
                    async with bot.session.post(f"{API_BASE_URL}/api/bot/inhouse/games/{self.game_id}/result",
                                                json={"winner": winner, "requested_by": by}, timeout=5) as resp:
                        status = resp.status
                except Exception:
                    status = 0
                msg = {200: f"기록했어요: {label}", 403: "팀을 나눈 사람만 결과를 기록할 수 있어요.",
                       409: "하루가 지난 내전은 바꿀 수 없어요.", 429: "잠시 후 다시 눌러 주세요."}.get(status, "기록하지 못했어요.")
                await interaction.response.send_message(msg, ephemeral=status != 200)
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
