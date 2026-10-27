from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import deque
from typing import List, Dict, Any, Optional, Set, Tuple
from app.champion_engine import CHAMPION_MAP_BY_NAME, CHAMPION_MAP_BY_ID
from app.database import get_connection
from app.ddragon import DDRAGON_CDN

def enrich_champion_tag(champ_name: str) -> Dict[str, str]:
    clean = (champ_name or "").strip()
    key = clean.lower().replace(" ", "")
    c_info = CHAMPION_MAP_BY_NAME.get(key)
    if c_info:
        img_name = c_info.get("image", "Yasuo.png")
        return {
            "name": c_info.get("name", clean),
            "id": c_info.get("id", "Yasuo"),
            "image": f"{DDRAGON_CDN}/img/champion/{img_name}"
        }
    return {
        "name": clean,
        "id": clean,
        "image": f"{DDRAGON_CDN}/img/champion/Yasuo.png"
    }

def get_tier_emblem(tier_code: str) -> str:
    t = (tier_code or "").lower().strip()
    if t not in ("iron", "bronze", "silver", "gold", "platinum", "emerald", "diamond", "master", "grandmaster", "challenger"):
        t = "iron"
    return f"/static/images/tiers/{t}.png"

# 예전 코드가 글에 자동으로 붙이던 가짜 디스코드 주소 (저장된 옛 글에서 걸러 내는 용도로만 사용)
DISCORD_SERVER_ID = "1188000000000000001"
DEFAULT_DISCORD_INVITE_URL = "https://discord.gg/lolgg-duo"

def _drop_placeholder_link(url: Optional[str]) -> Optional[str]:
    """예전 코드·프런트가 기본값으로 채우던 가짜 디스코드 주소는 '링크 없음'으로 취급"""
    if not url:
        return None
    clean = url.strip()
    if f"/channels/{DISCORD_SERVER_ID}/" in clean or clean.rstrip("/") == DEFAULT_DISCORD_INVITE_URL:
        return None
    return clean


def _scrub_placeholder_links(post: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("discord_voice_url", "discord_invite_url", "room_link"):
        if key in post:
            post[key] = _drop_placeholder_link(post.get(key))
    return post


def resolve_discord_channel_and_voice(
    my_pos: str,
    target_pos: str,
    queue_type: str,
    voice: bool,
    custom_channel_name: Optional[str] = None,
    custom_voice_url: Optional[str] = None,
    custom_invite_url: Optional[str] = None,
    room_name: Optional[str] = None,
    room_link: Optional[str] = None
) -> Dict[str, Any]:
    if not voice:
        return {
            "discord_channel_name": None,
            "discord_voice_url": None,
            "discord_invite_url": custom_invite_url or None,
            "is_voice_active": False,
            "room_name": None,
            "room_link": None,
            "room_status": "마이크 미사용",
            "host_mic": False
        }

    # 링크는 작성자가 직접 넣은 디스코드 주소만 쓴다.
    # (예전에는 존재하지 않는 서버 ID 1188000000000000001의 채널 주소와 discord.gg/lolgg-duo를 자동으로 붙였음)
    # 방 상태(room_status)는 실제 인원 기준으로 create_duo_post에서 계산하므로 여기서는 비워 둔다.
    ch_name = room_name or custom_channel_name or None
    v_url = room_link or custom_voice_url or None
    return {
        "discord_channel_name": ch_name,
        "discord_voice_url": v_url,
        "discord_invite_url": custom_invite_url or None,
        "is_voice_active": True,
        "room_name": ch_name,
        "room_link": v_url,
        "room_status": None,
        "host_mic": True
    }


DUO_FULL_KEYWORDS_LOWER: tuple = (
    "마감", "초과", "완료", "풀방", "full", "closed", "2/2명", "(2/2)", "만석", "full_room"
)

def is_room_full(p: Dict[str, Any]) -> bool:
    """
    다차원 정원 초과/마감 판별 엔진 (Capacity Status Engine):
    1. is_full 플래그가 True인 경우 -> O(1) 초고속 즉시 반환
    2. current_members >= max_members 인 경우 (타입 안전 파싱 및 방어적 수치 비교)
    3. room_status 문자열에 '마감', '초과', '완료', '2/2', '풀방', 'FULL', 'Closed' 등이 포함된 경우
    - 사전 불변 튜플(DUO_FULL_KEYWORDS_LOWER) 기반 루프 내 메모리 할당 및 .lower() 반복 연산 100% 제거
    """
    if not isinstance(p, dict):
        return False
    if p.get("is_full") is True:
        return True
    try:
        curr = p.get("current_members")
        mx = p.get("max_members")
        if curr is not None and mx is not None:
            if int(curr) >= int(mx):
                return True
    except (ValueError, TypeError):
        pass

    status = str(p.get("room_status", "") or "").strip()
    if not status:
        return False
    status_lower = status.lower()
    return any(k in status_lower for k in DUO_FULL_KEYWORDS_LOWER)


# 사용자 구인글은 SQLite duo_posts 테이블에 저장한다 (재시작해도 유지).
# '지금 같이 할 사람' 게시판이라 기본 6시간 지나면 목록에서 뺀다 (DUO_POST_TTL_HOURS 로 조정, 1~48)
def _ttl_hours() -> float:
    try:
        return min(48.0, max(1.0, float(os.getenv("DUO_POST_TTL_HOURS", "6"))))
    except ValueError:
        return 6.0


DUO_POST_TTL_SEC = int(_ttl_hours() * 3600)
DUO_POST_RETENTION_SEC = 86400 * 7
MAX_DUO_POSTS = 500


def init_duo_posts_table() -> None:
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS duo_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            owner_token_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_duo_posts_created ON duo_posts(created_at DESC)")
    conn.commit()
    conn.close()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _relative_time(created_at: int) -> str:
    minutes = max(0, int((time.time() - created_at) / 60))
    if minutes < 1:
        return "방금 전"
    if minutes < 60:
        return f"{minutes}분 전"
    return f"{minutes // 60}시간 전"


def _load_posts() -> List[Dict[str, Any]]:
    init_duo_posts_table()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, data, created_at FROM duo_posts WHERE created_at >= ? ORDER BY id DESC LIMIT ?",
        (int(time.time()) - DUO_POST_TTL_SEC, MAX_DUO_POSTS),
    ).fetchall()
    conn.close()
    posts = []
    for row_id, data, created_at in rows:
        post = _scrub_placeholder_links(json.loads(data))
        post["id"] = row_id
        post["created_at"] = _relative_time(created_at)
        posts.append(post)
    return posts


def _save_post_data(post_id: int, post: Dict[str, Any]) -> None:
    stored = {k: v for k, v in post.items() if k not in ("id", "created_at")}
    conn = get_connection()
    conn.execute("UPDATE duo_posts SET data = ? WHERE id = ?", (json.dumps(stored, ensure_ascii=False), post_id))
    conn.commit()
    conn.close()


def verify_duo_owner(post_id: int, token: str) -> bool:
    if not token or post_id <= 0:
        return False
    init_duo_posts_table()
    conn = get_connection()
    row = conn.execute("SELECT owner_token_hash FROM duo_posts WHERE id = ?", (post_id,)).fetchone()
    conn.close()
    return bool(row) and hmac.compare_digest(row[0], _token_hash(token))

def get_duo_posts(
    position: Optional[str] = None, 
    queue_type: Optional[str] = None,
    tier: Optional[str] = None,
    voice: Optional[str] = None,
    game: Optional[str] = None,
) -> List[Dict[str, Any]]:
    game_key = (game or "lol").strip().lower()
    pos_aliases = None
    if position and position != "ALL":
        pos_upper = position.upper().strip()
        pos_aliases = {
            "TOP": ["TOP"],
            "JUG": ["JUG", "JUNGLE"],
            "JUNGLE": ["JUG", "JUNGLE"],
            "MID": ["MID"],
            "BOT": ["BOT", "ADC"],
            "ADC": ["BOT", "ADC"],
            "SUP": ["SUP", "SUPPORT"],
            "SUPPORT": ["SUP", "SUPPORT"],
        }.get(pos_upper, [pos_upper])

    q_clean = queue_type.strip() if (queue_type and queue_type != "ALL") else None
    t_upper = tier.upper().strip() if (tier and tier != "ALL") else None
    v_upper = str(voice).upper().strip() if (voice and voice != "ALL") else None

    filtered = []
    for p in _load_posts():
        if game_key != "all" and (p.get("game") or "lol") != game_key:
            continue
        if pos_aliases:
            my_p = p.get("my_position", "").upper()
            tgt_p = p.get("target_position", "").upper()
            if not (any(a in [my_p, tgt_p] for a in pos_aliases) or tgt_p == "ALL"):
                continue
        if q_clean:
            pq = p.get("queue_type", "")
            if not (q_clean in pq or pq in q_clean):
                continue
        if t_upper:
            pt = p.get("tier", "").upper()
            pt_kr = p.get("tier_kr", "")
            if not (pt == t_upper or pt_kr == tier.strip()):
                continue
        if v_upper:
            p_voice = p.get("voice")
            if v_upper in ["ON", "TRUE", "1"] and not p_voice:
                continue
            elif v_upper in ["OFF", "FALSE", "0"] and p_voice:
                continue

        # Enrich discord voice details, champion details, and tier emblem if missing
        if "discord_channel_name" not in p or "discord_voice_url" not in p:
            ch_data = resolve_discord_channel_and_voice(
                p.get("my_position", "MID"),
                p.get("target_position", "ALL"),
                p.get("queue_type", "솔로랭크"),
                p.get("voice", True),
                p.get("discord_channel_name"),
                p.get("discord_voice_url"),
                p.get("discord_invite_url"),
                p.get("room_name"),
                p.get("room_link")
            )
            p.update(ch_data)
        if "room_name" not in p or not p.get("room_name"):
            p["room_name"] = p.get("discord_channel_name") or (f"🔊 {p.get('game_name', '호스트')}의 음성방" if p.get("voice") else "음성 미사용")
        if "room_link" not in p or not p.get("room_link"):
            p["room_link"] = p.get("discord_voice_url") or ""
        if "max_members" not in p:
            is_flex = "자유랭크" in p.get("queue_type", "") or "5인" in p.get("room_name", "") or "칼바람" in p.get("queue_type", "")
            p["max_members"] = 5 if is_flex else 2
        if "current_members" not in p:
            p["current_members"] = 1
        if "is_full" not in p:
            p["is_full"] = is_room_full(p)
        if "room_status" not in p or not p.get("room_status"):
            if p.get("is_full"):
                p["room_status"] = f"🔴 정원 마감 ({p.get('current_members', 2)}/{p.get('max_members', 2)}명)"
            else:
                p["room_status"] = f"🟢 대기 중 ({p.get('current_members', 1)}/{p.get('max_members', 2)}명)" if p.get("voice") else "마이크 미사용"
        if "host_mic" not in p:
            p["host_mic"] = bool(p.get("voice"))
        if "champion_details" not in p and p.get("most_champions"):
            p["champion_details"] = [enrich_champion_tag(c) for c in p["most_champions"]]
        if "tier_emblem" not in p:
            p["tier_emblem"] = get_tier_emblem(p.get("tier", "DIAMOND"))

        filtered.append(public_post(p))

    # 🌟 [회장님 특명] 방 인원이 정원초과면 자동으로 하단으로 내리고 정원 미달인 방은 상단에 우선 노출
    # is_room_full == False (정원 미달) -> 0 (상단 우선 배치)
    # is_room_full == True (정원 초과/마감) -> 1 (하단 자동 배치)
    filtered.sort(key=lambda item: (1 if is_room_full(item) else 0, -item.get("id", 0)))

    return filtered

def create_duo_post(
    game_name: str,
    tag_line: str,
    tier_kr: str,
    my_position: str,
    target_position: str,
    queue_type: str,
    voice: bool,
    title: str,
    description: str,
    discord_tag: Optional[str] = None,
    most_champions: Optional[List[str]] = None,
    discord_channel_name: Optional[str] = None,
    discord_voice_url: Optional[str] = None,
    discord_invite_url: Optional[str] = None,
    room_name: Optional[str] = None,
    room_link: Optional[str] = None,
    room_status: Optional[str] = None,
    host_mic: Optional[bool] = None,
    current_members: Optional[int] = 1,
    max_members: Optional[int] = 2,
    is_full: Optional[bool] = False,
    game: Optional[str] = "lol",
    author: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """새 구인글을 등록하고 (게시글, 작성자 토큰)을 반환"""
    tier_map = {
        "챌린저": "CHALLENGER",
        "그랜드마스터": "GRANDMASTER",
        "마스터": "MASTER",
        "다이아몬드": "DIAMOND",
        "에메랄드": "EMERALD",
        "플래티넘": "PLATINUM",
        "골드": "GOLD",
        "실버": "SILVER",
        "브론즈": "BRONZE",
        "아이언": "IRON"
    }
    tier_code = tier_map.get(tier_kr or "다이아몬드", "DIAMOND")

    clean_discord = (discord_tag or "").strip()
    if not clean_discord:
        clean_discord = f"{game_name}#{tag_line}" if tag_line else game_name

    # 실제 챔피언 이름만 허용 (임의 문자열이 화면/HTML에 섞이지 않도록 정규화)
    champs = []
    for c in (most_champions or [])[:3]:
        key = (c or "").strip().lower().replace(" ", "")
        c_info = CHAMPION_MAP_BY_NAME.get(key) or CHAMPION_MAP_BY_ID.get(key)  # 한글명 또는 영문 ID(Ahri)
        if c_info and c_info.get("name") not in champs:
            champs.append(c_info.get("name"))

    discord_voice_url = _drop_placeholder_link(discord_voice_url)
    discord_invite_url = _drop_placeholder_link(discord_invite_url)
    room_link = _drop_placeholder_link(room_link)

    ch_info = resolve_discord_channel_and_voice(
        my_position or "MID",
        target_position or "ALL",
        queue_type or "솔로랭크",
        bool(voice),
        discord_channel_name or room_name,
        discord_voice_url or room_link,
        discord_invite_url,
        room_name=room_name,
        room_link=room_link
    )

    cur_mem = current_members if current_members is not None else 1
    mx_mem = max_members if max_members is not None else (5 if ("자유랭크" in (queue_type or "") or "칼바람" in (queue_type or "")) else 2)
    room_full_flag = is_full if is_full is not None else (cur_mem >= mx_mem)

    default_status = f"🔴 정원 마감 ({cur_mem}/{mx_mem}명)" if room_full_flag else (f"🟢 대기 중 ({cur_mem}/{mx_mem}명)" if voice else "마이크 미사용")
    final_room_name = room_name or ch_info["room_name"] or (f"🔊 {game_name}의 음성방" if voice else "음성 미사용")
    final_room_link = room_link or ch_info["room_link"] or ""
    final_room_status = room_status or default_status
    final_host_mic = host_mic if host_mic is not None else bool(voice)

    new_post = {
        "game_name": game_name,
        "tag_line": tag_line,
        "discord_tag": clean_discord,
        "discord_channel_name": ch_info["discord_channel_name"],
        "discord_voice_url": ch_info["discord_voice_url"],
        "discord_invite_url": ch_info["discord_invite_url"],
        "is_voice_active": ch_info["is_voice_active"],
        "room_name": final_room_name,
        "room_link": final_room_link,
        "room_status": final_room_status,
        "current_members": cur_mem,
        "max_members": mx_mem,
        "is_full": room_full_flag,
        "host_mic": final_host_mic,
        "tier": tier_code,
        "tier_kr": tier_kr or "다이아몬드",
        "game": game or "lol",
        "author": author,
        "tier_emblem": get_tier_emblem(tier_code),
        "my_position": my_position or "MID",
        "target_position": target_position or "ALL",
        "queue_type": queue_type or "솔로랭크",
        "voice": bool(voice),
        "title": title,
        "description": description,
        "most_champions": champs,
        "champion_details": [enrich_champion_tag(c) for c in champs],
        # 포지션 조합만 보고 정해 둔 고정 점수(98점·96점 등)라 실제 시너지 통계가 아니므로 내보내지 않는다
        "synergy_score": None,
        "synergy_badge": None,
        "synergy_desc": None,
        "likes": 0
    }

    owner_token = secrets.token_urlsafe(24)
    now = int(time.time())
    init_duo_posts_table()
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO duo_posts (data, owner_token_hash, created_at) VALUES (?, ?, ?)",
        (json.dumps(new_post, ensure_ascii=False), _token_hash(owner_token), now),
    )
    conn.execute("DELETE FROM duo_posts WHERE created_at < ?", (now - DUO_POST_RETENTION_SEC,))
    conn.commit()
    conn.close()

    new_post["id"] = cur.lastrowid
    new_post["created_at"] = "방금 전"
    return new_post, owner_token

def toggle_duo_post_capacity(post_id: int) -> Optional[Dict[str, Any]]:
    """방 인원 정원 초과/미달 상태 실시간 토글 (호스트 또는 시스템)"""
    for p in _load_posts():
        if p.get("id") == post_id:
            currently_full = is_room_full(p)
            q_type = str(p.get("queue_type", ""))
            is_flex = "자유랭크" in q_type or "칼바람" in q_type or "5인" in str(p.get("room_name", ""))
            try:
                max_m = int(p.get("max_members") or (5 if is_flex else 2))
            except (ValueError, TypeError):
                max_m = 5 if is_flex else 2
            p["max_members"] = max_m

            if currently_full:
                joiners = p.get("joiners") or []
                if 1 + len(joiners) >= max_m:
                    joiners = []
                p["joiners"] = joiners
                cur = 1 + len(joiners)
                p["is_full"] = False
                p["current_members"] = cur
                p["room_status"] = f"🟢 대기 중 ({cur}/{max_m}명)"
            else:
                p["is_full"] = True
                p["current_members"] = max_m
                p["room_status"] = f"🔴 정원 마감 ({max_m}/{max_m}명)"
            _save_post_data(post_id, p)
            return p
    return None

def _owner_key(post_id: int, member_key: str) -> str:
    return _token_hash(f"owner:{post_id}:{member_key}")[:24]


def set_post_owner(post_id: int, member_key: str) -> None:
    """작성자 디스코드 멤버(member:<ID>, 웹 로그인·봇 공통)를 기록한다.
    - 자기 글에 '같이해요'를 못 누르고, 다른 기기·디스코드 봇에서도 마감·삭제할 수 있다.
    - IP 는 기록하지 않는다 (PC방처럼 여러 명이 같은 IP 를 쓰면 남의 글을 지울 수 있게 되므로)."""
    if member_key and member_key.startswith("member:"):
        set_post_field(post_id, "owner_k", _owner_key(post_id, member_key))


def is_post_owner(post_id: int, member_key: str) -> bool:
    if not (member_key and member_key.startswith("member:")):
        return False
    p = get_post(post_id)
    return bool(p and p.get("owner_k") and hmac.compare_digest(p["owner_k"], _owner_key(post_id, member_key)))


def posts_owned_by(member_key: str) -> List[int]:
    """지금 목록에 있는 글 중 이 멤버가 쓴 글 ID"""
    if not (member_key and member_key.startswith("member:")):
        return []
    return [p["id"] for p in _load_posts() if p.get("owner_k") == _owner_key(p["id"], member_key)]


def join_duo_post(post_id: int, joiner_key: str, joiner_name: str) -> Dict[str, Any]:
    """'같이해요': 한 사람(로그인 멤버 ID 또는 IP)당 한 번 인원 +1, 정원이 차면 자동 마감.
    반환 status: ok / already / full / own / not_found"""
    for p in _load_posts():
        if p.get("id") != post_id:
            continue
        if p.get("owner_k") and p["owner_k"] == _owner_key(post_id, joiner_key):
            return {"status": "own", "post": p}
        joiners = p.get("joiners") or []
        key = _token_hash(f"join:{post_id}:{joiner_key}")[:24]
        if any(j.get("k") == key for j in joiners):
            return {"status": "already", "post": p}
        max_m = int(p.get("max_members") or 2)
        cur = int(p.get("current_members") or 1)
        if p.get("is_full") or cur >= max_m:
            return {"status": "full", "post": p}
        joiners.append({"k": key, "name": (joiner_name or "")[:32]})
        cur += 1
        p["joiners"] = joiners
        p["current_members"] = cur
        p["is_full"] = cur >= max_m
        p["room_status"] = f"🔴 정원 마감 ({cur}/{max_m}명)" if p["is_full"] else f"🟢 대기 중 ({cur}/{max_m}명)"
        _save_post_data(post_id, p)
        return {"status": "ok", "post": p}
    return {"status": "not_found", "post": None}


def set_post_field(post_id: int, key: str, value: Any) -> None:
    """저장된 글 하나의 필드만 바꾼다 (예: 디스코드 메시지 ID)"""
    for p in _load_posts():
        if p.get("id") == post_id:
            p[key] = value
            _save_post_data(post_id, p)
            return


def get_post(post_id: int) -> Optional[Dict[str, Any]]:
    return next((p for p in _load_posts() if p.get("id") == post_id), None)


def expired_posts_to_mark() -> List[Dict[str, Any]]:
    """노출 시간이 지났고 디스코드 메시지가 있으며 아직 '만료' 표시를 안 한 글 (최근 7일 안)"""
    init_duo_posts_table()
    now = int(time.time())
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, data FROM duo_posts WHERE created_at < ? AND created_at >= ?",
            (now - DUO_POST_TTL_SEC, now - DUO_POST_RETENTION_SEC),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for row_id, data in rows:
        try:
            p = json.loads(data)
        except Exception:
            continue
        if p.get("discord_message_id") and not p.get("discord_expired_marked"):
            p["id"] = row_id
            out.append(p)
    return out


def mark_expired_in_discord(post: Dict[str, Any]) -> None:
    post["discord_expired_marked"] = True
    _save_post_data(int(post["id"]), {k: v for k, v in post.items() if k != "id"})


def delete_duo_post(post_id: int) -> bool:
    init_duo_posts_table()
    conn = get_connection()
    try:
        n = conn.execute("DELETE FROM duo_posts WHERE id = ?", (post_id,)).rowcount
        conn.commit()
    finally:
        conn.close()
    return n > 0


def leave_duo_post(post_id: int, joiner_key: str) -> Dict[str, Any]:
    """참가 취소: 내 참가 기록을 빼고 인원 -1 (마감이었으면 다시 모집 중). status: ok / not_joined / not_found"""
    for p in _load_posts():
        if p.get("id") != post_id:
            continue
        key = _token_hash(f"join:{post_id}:{joiner_key}")[:24]
        joiners = p.get("joiners") or []
        if not any(j.get("k") == key for j in joiners):
            return {"status": "not_joined", "post": p}
        p["joiners"] = [j for j in joiners if j.get("k") != key]
        max_m = int(p.get("max_members") or 2)
        cur = max(1, int(p.get("current_members") or 1) - 1)
        p["current_members"] = cur
        p["is_full"] = cur >= max_m
        p["room_status"] = f"🔴 정원 마감 ({cur}/{max_m}명)" if p["is_full"] else f"🟢 대기 중 ({cur}/{max_m}명)"
        _save_post_data(post_id, p)
        return {"status": "ok", "post": p}
    return {"status": "not_found", "post": None}


def public_post(p: Dict[str, Any]) -> Dict[str, Any]:
    """화면에 내보낼 글: 참가자 식별값(k)은 빼고 이름만"""
    out = dict(p)
    out["joiner_names"] = [j.get("name") or "멤버" for j in p.get("joiners") or []]
    out.pop("joiners", None)
    out.pop("owner_k", None)
    return out


# Alias for compatibility
add_duo_post = create_duo_post
# 디스코드 1-클릭 다이렉트 음성방 입장 클릭 로깅 & 전환율(CTR) 분석 추적기
DISCORD_JOIN_LOGS: deque = deque(maxlen=1000)
DISCORD_JOIN_STATS: Dict[str, Any] = {
    "total_clicks": 0,
    "unique_posts": set(),
    "last_click_at": None
}

def _duo_post_exists(post_id: int) -> bool:
    init_duo_posts_table()
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM duo_posts WHERE id = ? AND created_at >= ?",
        (post_id, int(time.time()) - DUO_POST_TTL_SEC),
    ).fetchone()
    conn.close()
    return bool(row)


def record_discord_join(post_id: int, client_ip: Optional[str] = None) -> Dict[str, Any]:
    # 없는 글 번호로 클릭 수를 부풀리지 못하게 실제 구인글만 집계
    if not _duo_post_exists(post_id):
        return {"status": "not_found", "post_id": post_id, "joined": False}
    now = time.time()
    DISCORD_JOIN_STATS["total_clicks"] += 1
    # Bounded set to prevent memory leak
    if len(DISCORD_JOIN_STATS["unique_posts"]) < 10000:
        DISCORD_JOIN_STATS["unique_posts"].add(post_id)
    DISCORD_JOIN_STATS["last_click_at"] = now

    entry = {
        "post_id": post_id,
        "timestamp": now,
        "client_ip": client_ip or "127.0.0.1"
    }
    DISCORD_JOIN_LOGS.append(entry)

    return {
        "status": "ok",
        "post_id": post_id,
        "joined": True,
        "total_clicks": DISCORD_JOIN_STATS["total_clicks"],
        "unique_posts_count": len(DISCORD_JOIN_STATS["unique_posts"]),
        "timestamp": now
    }

def get_discord_join_stats() -> Dict[str, Any]:
    return {
        "status": "ok",
        "total_clicks": DISCORD_JOIN_STATS["total_clicks"],
        "unique_posts_count": len(DISCORD_JOIN_STATS["unique_posts"]),
        "last_click_at": DISCORD_JOIN_STATS["last_click_at"],
        "recent_logs_count": len(DISCORD_JOIN_LOGS)
    }
