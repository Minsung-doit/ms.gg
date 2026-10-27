# 프런트엔드 스크립트

예전 `static/js/app.js`(약 16,000줄)를 기능 단위로 나눈 파일입니다. 모두 일반 `<script>`로
`templates/index.html`에서 **번호 순서대로** 로드되며, 최상위 함수·변수는 파일 간에 공유됩니다.

| 파일 | 내용 |
|---|---|
| 01-core.js | DOM 참조, 토스트, 검색, 검색 결과 목록, 티어 엠블럼, 광고 여백 |
| 02-player-profile.js | 프로필 캐시, 레이더/칭호, `jsArg`, 프로필 모달, AI 코치 렌더러 |
| 03-matches-ingame.js | 최근 전적, 툴팁, 실시간 인게임 |
| 04-controls-sync-search.js | 이벤트 바인딩, API 키 상태, 동기화, 자동완성, 디스코드·텔레그램, 초기화 |
| 05-tabs-theme-navigation.js | 탭 미리 불러오기, 배너, 테마, 탭 전환 |
| 06-masters-tierlist.js | 장인 랭킹, 티어표 (생성 데이터 기능 – 기본 숨김) |
| 07-bookmarks-notes-leaderboard.js | 최근 챔피언, 즐겨찾기, 소환사 메모, 랭킹, 티어 분포 |
| 08-champion-build-skills.js | 챔피언 빌드 모달, 룬 복사, 스킬 정보 |
| 09-multisearch-spectator.js | 멀티서치, 관전 피드 (생성 데이터 기능 – 기본 숨김) |
| 10-duo-synergy-finder.js | 듀오 시너지, 콤보 계산기, 듀오 구하기 |
| 11-patch-matchup-community.js | 패치노트, 1:1 상성, 커뮤니티 팁 |
| 12-home-widgets-analytics.js | 홈 위젯, 챔피언 분석 |
| 13-modals-mobile-admin.js | 모달 공통, 모바일 독/시트, 관리자 허브 |
| 14-ai-coach.js | AI 코치 (검색 버튼 오른쪽 AI 버튼, 코칭 패널, `/api/ai-coach`) |

## 규칙
- 다른 파일에 정의된 함수를 **스크립트 로드 시점에 바로** 호출하면 안 됩니다 (뒤 번호 파일은 아직 로드 전).
  이벤트 핸들러나 `DOMContentLoaded` 안에서 호출하는 것은 괜찮습니다.
- 이미지 주소의 Data Dragon 버전은 `__DDRAGON_VER__` 로 쓰면 서버가 현재 버전으로 바꿔 줍니다.
- 인라인 `onclick`에 문자열을 넣을 때는 `onclick="fn(${jsArg(value)})"` 형식만 씁니다.
