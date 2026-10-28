"""
carry.gg Discord Integration Service
디스코드 웹후크(Discord Webhook) 브로드캐스팅 & 리치 임베드 공유 엔진
"""

import os
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, Optional, List
from app.config import settings
from app.ddragon import DDRAGON_CDN

logger = logging.getLogger("lolgg.discord")

DISCORD_BLURPLE = 0x5865F2
DISCORD_EMERALD = 0x10B981
DISCORD_GOLD = 0xF59E0B
DISCORD_CRIMSON = 0xEF4444


# 공유 카드에 들어가는 값은 브라우저가 보낸 프로필이므로 형식을 믿지 않는다.
# 값이 없거나 숫자가 아니면 "-"로 비워 둔다 (승률 50%·KDA 3.00:1 같은 기본값을 지어내지 않음).
def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _md_label(text: Any) -> str:
    """[라벨](주소) 안에 넣는 사용자 문자열에서 링크 문법을 깨는 문자를 제거"""
    return "".join(ch for ch in str(text or "") if ch not in "[]()<>")


def _player_card_fields(player: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, str]:
    name = str(player.get("game_name") or player.get("name") or "소환사")
    tag = str(player.get("tag_line") or "KR1")
    tier = str(player.get("tier") or "UNRANKED")
    lp = _int_or_none(player.get("league_points") if player.get("league_points") is not None else player.get("lp"))
    wins = _int_or_none(player.get("wins"))
    losses = _int_or_none(player.get("losses"))
    win_rate = player.get("win_rate")
    if not isinstance(win_rate, (int, float)) or isinstance(win_rate, bool):
        win_rate = round(wins / (wins + losses) * 100, 1) if wins is not None and losses is not None and wins + losses > 0 else None
    record = f"{wins}승 {losses}패" if wins is not None and losses is not None else "전적 없음"
    kda = summary.get("avg_kda") or player.get("kda_ratio") or player.get("kda") or "-"
    most_list = summary.get("most_champions") or []
    most_items = [
        f"{c.get('name') or c.get('id') or ''}" + (f" ({c['win_rate']}%)" if c.get("win_rate") is not None else "")
        for c in (most_list if isinstance(most_list, list) else [])[:3] if isinstance(c, dict)
    ]
    return {
        "name": name,
        "tag": tag,
        "tier": tier,
        "lp": f"{lp:,} LP" if lp is not None else "- LP",
        "win_rate": f"{win_rate}%" if win_rate is not None else "-",
        "record": record,
        "kda": str(kda),
        "most": ", ".join(i for i in most_items if i) or "기록 없음",
        "profile_icon_id": str(_int_or_none(player.get("profile_icon_id")) or 29),
    }


def send_discord_webhook(payload: Dict[str, Any], webhook_url: Optional[str] = None, wait: bool = False) -> Dict[str, Any]:
    """
    Discord Webhook 엔드포인트로 리치 임베드 JSON 페이로드를 안전하게 전송합니다.
    """
    target_url = (webhook_url or settings.discord_webhook_url or "").strip()
    if not target_url:
        return {"success": False, "message": "등록된 디스코드 웹후크 URL이 없습니다."}

    if not (target_url.startswith("https://discord.com/api/webhooks/") or target_url.startswith("https://discordapp.com/api/webhooks/")):
        return {"success": False, "message": "올바른 디스코드 웹후크 URL 형식이 아닙니다."}

    # User-submitted text (duo posts, shares) must never ping @everyone/@here/roles/users.
    # 예외: 서버 설정에 넣은 구인 알림 역할 ID(숫자)만 명시적으로 허용
    roles = [str(r) for r in (payload.get("allowed_mentions") or {}).get("roles", []) if str(r).isdigit()]
    payload = {**payload, "allowed_mentions": {"parse": [], "roles": roles}}

    try:
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            target_url + ("?wait=true" if wait else ""),
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "carry.gg-Discord-Integration/2026.10"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            status = resp.status
            if status in (200, 204):
                out = {"success": True, "message": "디스코드 웹후크 전송 성공"}
                if wait and status == 200:
                    try:
                        out["message_id"] = str(json.loads(resp.read().decode("utf-8")).get("id") or "")
                    except Exception:
                        pass
                return out
            return {"success": False, "message": f"디스코드 응답 코드: {status}"}
    except urllib.error.HTTPError as e:
        logger.error(f"Discord webhook HTTP error: {e.code} - {e.reason}")
        return {"success": False, "message": f"디스코드 웹후크 오류 (HTTP {e.code})"}
    except Exception as e:
        logger.error(f"Discord webhook network error: {e}")
        return {"success": False, "message": f"네트워크 오류: {str(e)}"}


def _duo_embed(post: Dict[str, Any], deleted: bool = False, expired: bool = False) -> Dict[str, Any]:
    game_name = post.get("game_name", "소환사")
    tag_line = post.get("tag_line", "KR1")
    tier_kr = post.get("tier_label") or post.get("tier_kr", "언랭크")
    my_pos = post.get("my_position", "ALL")
    target_pos = post.get("target_position", "ALL")
    title = post.get("title", "듀오 구합니다")
    desc = post.get("description") or ""
    room_name = _md_label(post.get("discord_channel_name") or post.get("room_name") or "🔊 음성방")
    # 작성자가 링크를 넣지 않았으면 링크 없이 방 이름만 보낸다 (가짜 초대 주소를 붙이지 않음)
    voice_url = post.get("discord_voice_url") or post.get("room_link")

    from app import duo_games
    game = duo_games.get_game(post.get("game")) or duo_games.GAMES["lol"]
    names = dict(game["positions"] or [])
    who = f"**{game_name}#{tag_line}**" if tag_line and game["needs_tag"] else f"**{game_name}**"
    if post.get("author"):
        who += f" · {_md_label(post['author'])}"
    fields = [{"name": "작성자", "value": f"{who} ({tier_kr})", "inline": True},
              {"name": "큐", "value": f"{post.get('queue_type', '')} · {post.get('current_members', 1)}/{post.get('max_members', 2)}명", "inline": True}]
    if game["positions"]:
        def pos_label(v: str) -> str:  # "TOP,JUG" → "탑·정글"
            return "·".join(names[c] for c in str(v).split(",") if c in names) or "상관없음"
        fields.append({"name": "포지션", "value": f"{pos_label(my_pos)} → {pos_label(target_pos)}", "inline": True})
    state = "🗑️ 삭제됨 · " if deleted else ("⏰ 만료 · " if expired else ("🔴 마감 · " if post.get("is_full") else ""))
    deleted = deleted or expired  # 만료도 설명·참가자는 지우고 회색으로
    embed = {
        "title": f"{state}🎮 [{game['short']} 구인] {title}",
        "description": "" if deleted else desc,
        "color": 0x64748B if deleted else (0xEF4444 if post.get("is_full") else DISCORD_EMERALD),
        "fields": fields + [
            {
                "name": "🔊 디스코드 음성 채널",
                "value": f"[{room_name}]({voice_url})" if voice_url else f"{room_name} (링크 없음)",
                "inline": False
            }
        ],
        "footer": {
            "text": "carry.gg 구인"
        }
    }
    joiners = post.get("joiner_names") or [j.get("name") or "멤버" for j in post.get("joiners") or []]
    if joiners and not deleted:
        embed["fields"].append({"name": "참가", "value": ", ".join(_md_label(n) for n in joiners)[:1000], "inline": False})
    if post.get("queue_type") == "내전" and post.get("is_full") and not deleted:
        embed["fields"].append({"name": "팀 나누기", "value": "다 모였으면 음성 채널에서 `/내전` 을 입력하세요.", "inline": False})
    return embed


def duo_webhook_url(game: Optional[str], guild_id: Optional[str] = "") -> str:
    """그 디스코드 서버(·게임)의 구인 채널 웹후크 (app/communities.py). 다른 서버 채널로는 보내지 않는다"""
    from app import communities
    return communities.webhook_url(guild_id or "", game or "lol")


def send_duo_post_webhook(post: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    신규 구인글을 디스코드 채널에 올린다. 반환값의 message_id 로 나중에 '마감'·'삭제됨' 상태를 고친다.
    """
    post = post or {}
    target = duo_webhook_url(post.get("game"), post.get("guild_id"))
    if not target:
        return {"success": False, "message": "웹후크 URL 미설정"}
    embed = _duo_embed(post)
    payload = {
        "username": "carry.gg 구인",
        "avatar_url": f"{DDRAGON_CDN}/img/profileicon/29.png",
        "embeds": [embed]
    }
    # 구인 알림: 게임별 디스코드 역할을 멘션해 그 역할을 단 멤버에게 알림이 가게 한다.
    # 서버 관리자가 역할(@롤구인 등)을 만들고 .env 에 DUO_ALERT_ROLES=lol=역할ID,pubg=역할ID 로 넣으면 켜진다.
    role_id = duo_alert_roles(post.get("guild_id") or "").get(post.get("game") or "lol")
    if role_id:
        payload["content"] = f"<@&{role_id}>"
        payload["allowed_mentions"] = {"roles": [role_id]}

    return send_discord_webhook(payload, webhook_url=target, wait=True)


def update_duo_post_webhook(post: Dict[str, Any], deleted: bool = False, expired: bool = False) -> Dict[str, Any]:
    """처음 올린 디스코드 구인 메시지를 지금 상태(인원·마감·참가자·삭제)로 고친다"""
    mid = str(post.get("discord_message_id") or "")
    target = duo_webhook_url(post.get("game"), post.get("guild_id"))
    if not (mid.isdigit() and target.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/"))):
        return {"success": False, "message": "고칠 메시지가 없습니다."}
    body = json.dumps({"embeds": [_duo_embed(post, deleted=deleted, expired=expired)], "allowed_mentions": {"parse": []}},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{target}/messages/{mid}", data=body, method="PATCH",
                                 headers={"Content-Type": "application/json", "User-Agent": "carry.gg-Discord-Integration/2026.10"})
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return {"success": resp.status in (200, 204)}
    except Exception as e:
        logger.warning("Discord webhook edit failed: %s", e)
        return {"success": False, "message": str(e)}


def duo_alert_roles(guild_id: str = "") -> Dict[str, str]:
    """구인 알림 역할 {'lol': '123'} (숫자 ID만). 봇 /알림역할 값이 먼저, 없으면 DUO_ALERT_ROLES(_<서버ID>)"""
    from app import communities
    return communities.alert_role_ids(guild_id)


def send_player_share_webhook(player: Optional[Dict[str, Any]] = None, summary: Optional[Dict[str, Any]] = None, custom_msg: str = "") -> Dict[str, Any]:
    """
    소환사 전적 카드를 디스코드 채널로 실시간 공유합니다.
    """
    f = _player_card_fields(player or {}, summary or {})
    name, tag = f["name"], f["tag"]

    embed = {
        "title": f"🏆 [carry.gg 전적 분석] {name}#{tag}",
        "url": f"http://localhost:3000/?q={urllib.parse.quote(name)}%23{urllib.parse.quote(tag)}",
        "color": DISCORD_BLURPLE,
        "fields": [
            {
                "name": "🛡️ 랭크 티어",
                "value": f"**{f['tier']}** ({f['lp']})",
                "inline": True
            },
            {
                "name": "📊 솔로랭크 승률",
                "value": f"**{f['win_rate']}** ({f['record']})",
                "inline": True
            },
            {
                "name": "⚡ 평균 KDA",
                "value": f"**{f['kda']}**",
                "inline": True
            },
            {
                "name": "👑 모스트 챔피언 TOP 3",
                "value": f["most"],
                "inline": False
            }
        ],
        "footer": {
            "text": "carry.gg 실시간 소환사 전적 검색",
            "icon_url": f"{DDRAGON_CDN}/img/profileicon/{f['profile_icon_id']}.png"
        }
    }

    if custom_msg:
        embed["description"] = f"💬 *\"{custom_msg}\"*"

    payload = {
        "username": "carry.gg 전적 봇",
        "avatar_url": f"{DDRAGON_CDN}/img/profileicon/29.png",
        "embeds": [embed]
    }

    return send_discord_webhook(payload)


def send_multisearch_share_webhook(team_summary: Optional[Dict[str, Any]] = None, players: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    5인 멀티서치 분석 결과를 디스코드 채널로 공유합니다.
    """
    team_summary = team_summary or {}
    players = players or []
    avg_tier = team_summary.get("team_avg_tier_kr") or team_summary.get("avg_tier") or "-"
    avg_wr = team_summary.get("team_avg_win_rate") or team_summary.get("avg_win_rate") or "-"
    meta_banpick = team_summary.get("meta_banpick") or {}
    op_picks = ", ".join([p.get("name", "") for p in meta_banpick.get("op_picks", [])[:3]]) or "자유 선택"
    must_bans = ", ".join([b.get("name", "") for b in meta_banpick.get("must_bans", [])[:3]]) or "-"

    player_lines = []
    for p in players[:5]:
        p = p or {}
        p_name = p.get("game_name") or p.get("name", "")
        p_tier = p.get("tier_kr") or p.get("tier", "")
        p_wr = p.get("win_rate") if p.get("win_rate") is not None else "-"
        p_badge = p.get("danger_badge") or (p.get("badges", [""])[0] if isinstance(p.get("badges"), list) and p.get("badges") else "")
        badge_str = f" `[{p_badge}]`" if p_badge else ""
        player_lines.append(f"• **{p_name}** | {p_tier} ({p_wr}%){badge_str}")

    embed = {
        "title": "📋 [carry.gg] 5인 픽창 멀티서치 팀 분석 리포트",
        "color": DISCORD_GOLD,
        "fields": [
            {
                "name": "⭐ 팀 종합 지표",
                "value": f"평균 티어: **{avg_tier}** | 팀 평균 승률: **{avg_wr}%**",
                "inline": False
            },
            {
                "name": "👥 5인 소환사 라인업",
                "value": "\n".join(player_lines) if player_lines else "소환사 정보 없음",
                "inline": False
            },
            {
                "name": "💡 추천 메타 밴픽 가이드",
                "value": f"• 추천 OP 픽: `{op_picks}`\n• 필밴 권장: `{must_bans}`",
                "inline": False
            }
        ],
        "footer": {
            "text": "carry.gg 5인 멀티서치 시스템"
        }
    }

    payload = {
        "username": "carry.gg 멀티서치",
        "embeds": [embed]
    }

    return send_discord_webhook(payload)


def format_player_discord_markdown(player: Optional[Dict[str, Any]] = None, summary: Optional[Dict[str, Any]] = None) -> str:
    """
    디스코드 채팅방에 직접 붙여넣을 수 있는 마크다운 텍스트를 반환합니다.
    """
    f = _player_card_fields(player or {}, summary or {})
    name, tag = f["name"], f["tag"]

    return (
        f">>> 🏆 **[carry.gg] 소환사 전적 분석** | **{name}#{tag}**\n"
        f"• **솔로랭크 티어**: {f['tier']} ({f['lp']})\n"
        f"• **솔로랭크 승률**: {f['win_rate']} ({f['record']}) | **평균 KDA**: {f['kda']}\n"
        f"• **모스트 챔피언**: {f['most']}\n"
        f"🔗 *상세 전적 보기: <http://localhost:3000/?q={urllib.parse.quote(name)}%23{urllib.parse.quote(tag)}>*"
    )


def format_multisearch_discord_markdown(team_summary: Optional[Dict[str, Any]] = None, players: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    디스코드 음성방/텍스트 채팅방에 붙여넣을 5인 멀티서치 마크다운 텍스트를 반환합니다.
    """
    team_summary = team_summary or {}
    players = players or []
    avg_tier = team_summary.get("team_avg_tier_kr") or team_summary.get("avg_tier") or "-"
    avg_wr = team_summary.get("team_avg_win_rate") or team_summary.get("avg_win_rate") or "-"
    lines = [
        f">>> 📋 **[carry.gg] 5인 픽창 멀티서치 분석** (팀 평균: **{avg_tier}** · {avg_wr}%)"
    ]
    for p in players[:5]:
        p = p or {}
        p_name = p.get("game_name") or p.get("name", "")
        p_tier = p.get("tier_kr") or p.get("tier", "")
        p_wr = p.get("win_rate") if p.get("win_rate") is not None else "-"
        p_badge = p.get("danger_badge") or (p.get("badges", [""])[0] if isinstance(p.get("badges"), list) and p.get("badges") else "")
        badge_str = f" `[{p_badge}]`" if p_badge else ""
        lines.append(f"• **{p_name}**: {p_tier} ({p_wr}%){badge_str}")

    return "\n".join(lines)


def test_discord_webhook(webhook_url: str) -> Dict[str, Any]:
    """
    웹후크 URL 유효성을 검증하기 위해 테스트 메시지를 발송합니다.
    """
    test_payload = {
        "username": "carry.gg 연동 테스트",
        "avatar_url": f"{DDRAGON_CDN}/img/profileicon/29.png",
        "embeds": [
            {
                "title": "✅ carry.gg 디스코드 웹후크 연동 성공!",
                "description": "축하합니다! carry.gg와 디스코드 채널이 성공적으로 연동되었습니다.\n이제 듀오 구인글, 전적 공유 및 알림이 실시간으로 이 채널에 전송됩니다.",
                "color": DISCORD_EMERALD,
                "fields": [
                    {"name": "연동 상태", "value": "🟢 정상 가동 (Active)", "inline": True},
                    {"name": "서비스 주소", "value": "http://localhost:3000", "inline": True}
                ],
                "footer": {"text": "carry.gg Enterprise Discord Webhook Hub"}
            }
        ]
    }
    return send_discord_webhook(test_payload, webhook_url=webhook_url)
