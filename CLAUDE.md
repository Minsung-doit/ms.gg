# carry.gg (opgg) — 개발 지침

## 개발 방식 (2026-10-24 저녁 변경: 토큰 사용량 절감)
- 작업을 나눠 맡는다:
  - **Gemini 3.8 Flash** (`agy` 스킬): 범위가 명확한 큰 구현(새 화면·기능 추가 등). 한 번에 하나의 작업, 대상 파일을 명시해서 맡긴다.
  - **Claude 직접**: 몇 줄짜리 수정, 보안 수정, CSS 중복 제거처럼 실수하면 위험한 작업, 여러 파일에 걸친 설계 변경, git 병합.
- Claude는 Gemini 작업의 diff를 검토하고 테스트로 판정한다.
- **PoC 단계 (2026-10-25 결정): 속도 우선.** 검토는 비판적으로 하되, 고치는 것은 P0/P1만:
  - P0: 보안 구멍, 사이트·JS 파일 전체 장애, 라이엇 키 정지 위험(정책 위반·호출량 폭증), 가짜 데이터를 실제처럼 노출
  - P1: 핵심 기능(검색·프로필·전적·관전·멀티서치) 동작 불가
  - 그 외(줄바꿈 섞임, 빈 줄, 중복 코드, 문구, 사소한 UI)는 고치지 않고 넘어간다. 재작업 요청도 P0/P1일 때만.
- Gemini 작업은 반드시 Claude가 diff 확인 + `python scripts/run_all_tests.py` 통과 후에만 커밋한다. Gemini의 자체 보고("완료/PASS")는 근거로 쓰지 않는다.
- 데이터 원칙(아래)을 어기는 변경(가짜 값, 호출량 증가)은 되돌린다. Gemini 역할 지침은 `GEMINI.md`.
- Claude가 병렬 서브에이전트를 여러 개 띄우지 않는다 (토큰 한도 소진).
- `--dangerously-skip-permissions`는 어디에도 쓰지 않는다.
- 완료 판정은 실제 테스트 결과로만 한다. 자체 채점 리포트(100점/ALL PASS)는 근거로 쓰지 않는다. (옛 `reports/`·`orders/`·사내 AI 파이프라인은 2026-10-25 삭제)

## 서버 (2026-10-30~, 테스트 운영)
- AWS EC2 시드니 t3.small (Ubuntu 24.04, **Python 3.12**), Caddy(HTTPS) 뒤에서 디스코드 로그인(MEMBER_LOGIN=discord)으로 멤버만 입장. 주소·접속 정보는 사용자 바탕 화면 `carrygg_서버_접속정보.txt`.
- 서버가 진짜 데이터. PC 에서 사이트·봇을 같이 켜지 않는다 (같은 라이엇 키·봇 토큰).
- PC 는 Python 3.14 라서 클래스 본문에서 뒤에 정의된 이름을 써도 돌지만 서버 3.12 에서는 NameError → 모델은 쓰는 이름보다 아래에 둔다. 배포 전 서버 venv 로 `import app.main` 확인.
- 코드 올리기: `python scripts/make_deploy_bundle.py` → scp → `/opt/carrygg` 에 풀기(.env 유지) → `sudo systemctl restart carrygg carrygg-bot`.

## 실행 / 테스트
- 서버: `python run.py` → 공개 http://127.0.0.1:3000 , 관리자 http://127.0.0.1:300/admin (비밀번호는 `.env`의 `ADMIN_PASSWORD`)
- 화면 점검: 서버 실행 중 `python -X utf8 scripts/ui_check.py` — 11개 화면 × 데스크톱/태블릿/휴대폰 × 다크/화이트에서 JS 오류·가로 넘침·화이트 모드 어두운 상자·낮은 대비 글자. UI 변경 후 반드시 실행.
- 전체 테스트: `python scripts/run_all_tests.py` (실데이터 `test_real_data.py`, 보안 회귀 `test_security_regressions.py` 포함)
- 관리자 API 테스트는 `test_support.admin_client()`로 실제 서명 토큰을 사용한다. 테스트 전용 인증 우회는 두지 않는다.
- DB에 쓰는 테스트는 `test_support.use_temp_db()`로 임시 DB를 쓴다. 실제 `opgg.db`에 픽스처를 남기지 않는다.
- 패치 데이터 갱신: `python scripts/update_game_data.py` 후 서버 재시작 (버전은 `app/ddragon.py`가 유일한 출처)

## 데이터 원칙 (2026-10-24 결정)
- 화면에 보이는 소환사·전적·랭킹·관전 정보는 라이엇 API 값만 쓴다 (`app/real_data.py`). 없는 값은 비워 두고 지어내지 않는다.
- 키가 없거나 만료되면 503, 없는 소환사는 404. 대체 데이터(가짜 프로필·시뮬레이션)를 만들지 않는다.
- 난수로 만든 통계 기능(티어표·빌드·상성·장인·AI 코치 등)은 `SYNTHETIC_FEATURES=0`(기본)으로 막혀 있다.
  실제 데이터로 다시 만들기 전에는 켜지 않는다. 막히는 API 목록은 `app/main.py`의 `SYNTHETIC_API_PATTERN`.
- 라이엇 API 호출량을 늘리는 변경(목록 프리패치, 화면당 다수 호출)은 하지 않는다. 매치 상세는 `match_cache`로 캐시.
  - 예외 (2026-10-25 사용자 승인): 장인랭킹용 챔피언 숙련도 — 소환사 조회 시 +1회, 챌린저 래더 숙련도 하루 1회 갱신(약 43회/일).
  - 예외 (2026-10-25 사용자 승인): 티어표·상성용 매치 수집기(`app/match_collector.py`) — 자체 한도 120초당 40회(공용 한도 95회 중 나머지는 방문자용), 솔로랭크만, 압축 저장. `MATCH_COLLECTOR=0`으로 끔. 최신 패치가 2만 게임이면 10분마다 1명만 크롤(감속), 최신 2개 패치보다 오래된 매치는 1시간마다 삭제.
  - 예외 (2026-10-28 사용자 승인): 챌린저 랭킹 상위 300명 (`LADDER_NAMED_TOP_N`). 닉네임은 `ladder_names` 에 7일 저장해 새로 들어온 사람·7일 지난 이름만 다시 조회. 장인 숙련도는 상위 50명(`LADDER_MASTERY_TOP_N`)만.
  - 예외 (2026-10-28 사용자 승인): 서버 랭킹 하루 1회 갱신 때 등록·인증 멤버의 최근 30일 솔로·자유랭크 매치 (같이 한 게임은 인증 멤버만, 팀 짜기 퍼포먼스·라인은 등록 멤버까지) (`community_rank.cache_member_matches`, 1명당 목록 2회 + 캐시에 없는 매치만). `MEMBER_MATCH_FETCH=0` 으로 끔.
- AI 코치(`app/ai_coach.py`, `/api/ai-coach`): 실제 전적 vs 수집된 고티어 포지션 평균. `ANTHROPIC_API_KEY`가 있으면 리포트 수치만(소환사 이름 제외) Claude로 보내 요약을 받는다. IP당 10분 6회, AI 요약은 서버 전체 하루 300회.
- 정식 키가 필요한 화면은 샘플 데이터 + 화면 표시(목록: `docs/PRODUCTION_KEY_SAMPLES.md`). 샘플에 실존 인물 이름을 쓰지 않는다.
- Data Dragon 이미지 주소는 하드코딩하지 않는다: 파이썬은 `DDRAGON_CDN`, JS는 `__DDRAGON_VER__` 표식.

## 프런트엔드 구조
- JS: `static/js/app/01~13-*.js` (순서대로 로드, 최상위 이름 공유). 설명은 `static/js/app/README.md`.
- CSS: `static/css/app/01~13-*.css` (원래 style.css를 순서대로 나눈 조각, 순서 변경 금지).

## 구인 허브 (2026-10-27, 사업 방향: 소~중형 디스코드 서버용)
- 게임별 포지션·티어·큐·인원은 `app/duo_games.py` 한 곳 (롤·배그·옵치). 새 게임은 여기에만 추가.
- 구인글: 노출 `DUO_POST_TTL_HOURS`(기본 6), '같이해요' 참가 키는 로그인 멤버 `member:<디스코드ID>`(봇과 공유)·로컬은 IP.
- 글 작성자: 쓴 브라우저의 작성자 토큰(localStorage) + 디스코드 멤버(`owner_k`, member:<ID> 해시). 멤버는 다른 기기·봇 `/내구인`에서도 마감·삭제, 자기 글 참가 불가. IP 로는 작성자를 기록하지 않는다 (PC방 공유 IP).
- 디스코드 채널 메시지는 `?wait=true`로 ID를 받아 두고 참가·마감·삭제·만료 때 같은 메시지를 PATCH. 역할 멘션은 `DUO_ALERT_ROLES` 의 숫자 ID만.
- 디스코드 봇(`scripts/discord_bot.py`): `/구인`·`/구인글`·`/내구인`·`/내전`·`/내전전적`·`/배그` 은 `/api/bot/...` (헤더 `X-Bot-Secret`=`BOT_API_SECRET`, 16자 이상). 멤버 로그인을 켜도 이 헤더가 맞으면 API만 통과.
- 배그 전적: `app/pubg_api.py` + `GET /api/pubg/player` (`PUBG_API_KEY` 없으면 503, 분당 8회 자체 제한, 10분 캐시). 키가 있을 때만 `/api/duo-games` 의 배그 `has_stats`=true.
- 계정 (2026-10-28 사용자 결정, 두 단계):
  - 닉네임 등록 `POST /api/me/riot-account` (라이엇에 있는 계정만, verified=0): 티어 역할·내전 팀 나누기용. 다른 멤버가 인증한 계정은 불가, 인증한 멤버는 덮어쓰지 않음.
  - 라이엇 로그인 RSO (`app/riot_sign_on.py`, verified=1): 서버 랭킹·내전 순위·승급 알림·같이 한 게임은 이것만. 한 계정은 한 멤버에게만. `RSO_CLIENT_ID/SECRET` 이 없으면 버튼 '준비 중'.
- 롤 구인글 닉네임 (2026-10-28): `_check_recruit_identity` — 라이엇에 없는 닉네임#태그는 422 (Account-V1 1회, 메모리 기억). `RECRUIT_REQUIRE_VERIFIED=1`(Production·RSO 승인 뒤 켬)이면 인증한 본인 계정으로만.
- 테스트는 `test_support.no_real_riot_key()` 로 .env 의 진짜 키를 비운다 (가짜 키는 테스트가 직접 넣음).
- 내전 순위·기록 (2026-10-28): `inhouse.ranking()` 내전 점수(시작 1000, 팀 평균 Elo K=24)·판수·승률·KDA·모스트, 3판 미만은 '배치'. 평균 골드·CS·딜·시야·타워는 `GET /api/inhouse/players/{key}` (순위표 줄을 눌렀을 때만).
  경기 기록은 라이엇 토너먼트 코드 게임에서만 (`app/tournament.py`, `RIOT_TOURNAMENT=live|stub`, 기본 꺼짐). 콜백 `POST /api/riot/tournament/callback` 은 로그인 없이 열려 있지만 내용은 믿지 않고 매치를 직접 불러 `info.tournamentCode` 가 우리 코드일 때만 반영. 라이엇 결과가 들어온 게임은 손 결과 409.
- 내전 팀 짜기 엔진 (2026-10-28): `app/team_builder.py` — 점수 = 현재 티어 + 최고 티어 보정(우리 rank_snapshots) + 최근 20판(승률·판 평균 대비 KDA) + 내전 Elo(판수 비중). 라인 주·부(최근 게임 또는 직접). 10명 전수 계산, N명은 뱀 드래프트+맞바꾸기. `POST /api/inhouse/plan` (single/multi[balanced|tiered]/tournament/league, 남는 인원 대기), 토너먼트·리그 저장 `inhouse_events` (`/api/inhouse/events`, 경기 시작 = 보통 내전 게임 생성, 대진·순위는 게임 결과로 계산). 봇 `POST /api/bot/inhouse/plan`.
- 내전 팀 짜기 (예전 10명 전용): `app/inhouse.py` (LP 환산 점수, 126가지 전부 계산), 웹 `POST /api/inhouse/balance`, 봇 `POST /api/bot/inhouse`(연결된 계정 티어, 라이엇 호출 없음). 기록: `inhouse_games` 표, 팀 저장한 사람(member:<ID>/IP)만 24시간 안에 결과 지정(관리자는 언제나), `GET /api/inhouse/stats`.

## 여러 디스코드 서버 (2026-10-28)
- `app/communities.py`: `COMMUNITY_GUILDS=ID:이름,...` (없으면 `DISCORD_GUILD_ID`+`COMMUNITY_NAME` 한 곳, 그것도 없으면 구분 없음 ""). 첫 서버가 기본 서버, 서버 값이 비어 있는 예전 데이터는 기본 서버 것.
- 서버별로 나뉘는 것: 구인글(JSON `guild_id`), `inhouse_games.guild_id`, 서버 랭킹·같이 한 게임·주간 MVP(`member_guilds` 표), 웹후크·알림 역할(`DISCORD_WEBHOOK_URL_<ID>`, `DUO_ALERT_ROLES_<ID>`). 기본 서버가 아니면 예전 설정 이름으로 대신하지 않는다 (다른 서버 채널로 새는 것 방지).
- 지금 서버: 쿠키 `community` 가 내 서버(`member_guilds`)일 때만, 아니면 내 첫 서버. 다른 서버 글 참가는 404. 봇은 `member.guild_id` 를 보내고 등록 안 된 서버면 403.

- 구인 알림 역할 (2026-10-28): 봇 `/알림역할`(서버 관리 권한) → `community_settings` 표 `alert_roles`, `.env` `DUO_ALERT_ROLES(_<ID>)` 보다 먼저 ("off" 면 끔). 멤버는 `/알림받기` 로 직접 토글.
- 티어 역할 (2026-10-28): 서버마다 기존 역할을 연결 (`community_settings.tier_roles`, `POST /api/bot/tier-role-map`). 봇 `/티어역할 자동연결|연결|보기|만들기|맞추기` + `TIER_ROLE_SYNC=1` 이면 1시간마다. 자동연결은 장식·'롤'·'티어'를 뺀 이름이 티어 말과 같을 때만, 관리 권한 있는 역할은 제외. `GET /api/bot/tier-roles?guild_id=` 는 그 서버 멤버의 인증(verified) 계정 솔로랭크만 (미인증·언랭크 None → 역할 뗌). 이름이 맞는 티어 역할만 건드린다.

## 보안 규칙
- 관리자 API는 `verify_admin_access(request)` 필수. 공개 쓰기 API는 `app/rate_limit.py` 제한기를 건다.
- 프런트 인라인 핸들러에 문자열을 넣을 때는 `onclick="fn(${jsArg(value)})"` 형식만 쓴다 (`'${...}'` 금지, `escapeHtml`은 onclick 안에서 보호 효과 없음).
- 사용자 입력 링크는 서버에서 화이트리스트 검증(`DUO_LINK_PATTERN`)한다.
