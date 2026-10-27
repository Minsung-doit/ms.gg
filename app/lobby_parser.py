"""픽창·로비 채팅 복사 텍스트에서 소환사명(라이엇 ID) 목록을 뽑는다 (멀티서치용)."""
import re
from typing import List


def parse_summoner_names(raw_text: str) -> List[str]:
    """
    롤 클라이언트 픽창 채팅 복사 텍스트, 쉼표, 줄바꿈 등에서 순수 소환사명(및 Riot ID) 100% 정밀 추출.
    - 한국어 클라이언트: 'XXX님이 로비/방/대기실/그룹/챔피언 선택에 참가하셨습니다.'
    - 채팅형 텍스트: 'XXX: 탑 가실분', '[아군] XXX: ...', '[전체] XXX: ...'
    - 영문 클라이언트: 'XXX joined the lobby/champion select/room'
    - 일반 구분자: 줄바꿈, 쉼표(,), 세미콜론(;), 슬래시(/), 파이프(|), 탭(\t)
    - 번호 리스트 형식: '1. XXX', '1) XXX'
    - 타임스탬프 제거: '[12:34:56]', '[오후 1:23]'
    - 시스템 알림 필터링: 'XXX님이 나갔습니다', '채팅에 연결되었습니다' 등 완벽 제외
    """
    if not raw_text or not raw_text.strip():
        return []

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    extracted = []

    for line in lines:
        clean = line.strip()
        # 1. 타임스탬프 접두사 제거 (예: [12:34:56], [오후 1:23], 12:34)
        clean = re.sub(r'^(?:\[\s*(?:오전|오후)?\s*\d{1,2}:\d{2}(?::\d{2})?\s*\]|\d{1,2}:\d{2}(?::\d{2})?)\s*', '', clean).strip()

        # 2. 채팅 채널 태그 제거 (예: [아군], [전체], [팀], [그룹], [Party], [Team])
        clean = re.sub(r'^\[(?:아군|전체|팀|그룹|파티|Party|All|Team)\]\s*', '', clean).strip()

        # 3. 퇴장/시스템 알림 메시지 무시
        if re.search(r'(?:나갔습니다|퇴장했습니다|퇴장하셨습니다|left the|disconnected|연결되었습니다|연결이 끊어졌습니다|재접속|시작되었습니다)', clean, re.I):
            continue

        # 4. 한국어 클라이언트 로비/방/대기실/챔피언 선택 참가 메시지 완벽 지원
        # 예: "Hide on bush님이 로비에 참가하셨습니다.", "Chovy님이 챔피언 선택 창에 입장했습니다.", "Zeus님이 게임 로비에 들어왔습니다."
        m_kr = re.search(r'^(.*?)\s*님이\s*(?:게임\s*)?(?:로비|방|대기실|대기방|그룹|파티|챔피언\s*선택(?:\s*창)?|픽창)(?:에|을|으로)?\s*(?:참가|입장|참여|들어왔)(?:하셨습니다|했습니다|하였습니다|함|습니다)?\.?', clean)
        if m_kr:
            name = m_kr.group(1).strip()
            name = re.sub(r'^\[.*?\]\s*', '', name).strip()
            if name and len(name) <= 24:
                extracted.append(name)
                continue

        # 5. 영문 클라이언트 로비/방 참가 메시지 완벽 지원
        # 예: "Faker joined the lobby", "Chovy entered champion select", "Gumayusi has joined the party"
        m_en = re.search(r'^(.*?)\s+(?:has\s+)?(?:joined|entered)\s+(?:the\s+)?(?:game\s+)?(?:lobby|room|group|party|champion\s+select|champ\s+select)\.?', clean, re.I)
        if m_en:
            name = m_en.group(1).strip()
            name = re.sub(r'^\[.*?\]\s*', '', name).strip()
            if name and len(name) <= 24:
                extracted.append(name)
                continue

        # 6. 픽창 채팅 메시지 형식 (예: "Hide on bush: 탑 가실분", "Chovy: 미드 밴좀")
        m_chat = re.search(r'^([^:]+?)\s*:\s*(.*)$', clean)
        if m_chat:
            possible_name = m_chat.group(1).strip()
            if possible_name and len(possible_name) <= 24 and not any(kw in possible_name for kw in ['시스템', 'System', '알림', 'Notice', '공지']):
                extracted.append(possible_name)
                continue

        # 7. 구분자(쉼표, 세미콜론, 슬래시, 파이프, 탭)로 복수 인원이 나열된 경우
        delimiters = [',', ';', '/', '|', '\t']
        matched_delim = None
        for d in delimiters:
            if d in clean:
                matched_delim = d
                break

        if matched_delim:
            parts = [p.strip() for p in clean.split(matched_delim) if p.strip()]
            for p in parts:
                p_clean = re.sub(r'^(?:\[.*?\]|\d+\.|\d+\))\s*', '', p).strip()
                p_clean = re.sub(r'\s*님이\s*(?:로비|방|대기실|챔피언).*$', '', p_clean).strip()
                if p_clean and len(p_clean) <= 24:
                    extracted.append(p_clean)
            continue

        # 8. 번호 리스트 형식 (예: "1. Zeus", "2) Oner") 또는 순수 단일 닉네임 라인
        clean_single = re.sub(r'^(?:\[.*?\]|\d+\.|\d+\))\s*', '', clean).strip()
        clean_single = re.sub(r'\s*님이\s*(?:로비|방|대기실|챔피언).*$', '', clean_single).strip()
        if clean_single and len(clean_single) <= 24:
            extracted.append(clean_single)

    # 중복 제거 (대소문자/공백 무시 유지)
    seen = set()
    result = []
    for item in extracted:
        clean_item = item.strip()
        if not clean_item:
            continue
        key_no_space = clean_item.lower().replace(" ", "")
        if key_no_space not in seen:
            seen.add(key_no_space)
            result.append(clean_item)
            if len(result) >= 10:
                break

    return result
