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
- 내전 팀 짜기: `app/inhouse.py` (LP 환산 점수, 126가지 전부 계산), 웹 `POST /api/inhouse/balance`, 봇 `POST /api/bot/inhouse`(연결된 계정 티어, 라이엇 호출 없음). 기록: `inhouse_games` 표, 팀 저장한 사람(member:<ID>/IP)만 24시간 안에 결과 지정(관리자는 언제나), `GET /api/inhouse/stats`.

## 보안 규칙
- 관리자 API는 `verify_admin_access(request)` 필수. 공개 쓰기 API는 `app/rate_limit.py` 제한기를 건다.
- 프런트 인라인 핸들러에 문자열을 넣을 때는 `onclick="fn(${jsArg(value)})"` 형식만 쓴다 (`'${...}'` 금지, `escapeHtml`은 onclick 안에서 보호 효과 없음).
- 사용자 입력 링크는 서버에서 화이트리스트 검증(`DUO_LINK_PATTERN`)한다.
