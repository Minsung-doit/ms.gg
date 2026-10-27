# 라이엇 API 키 안내 (2026-10-24 작성)

> 정책은 바뀔 수 있으니 신청 전에 반드시 공식 문서를 확인하세요:
> https://developer.riotgames.com/docs/portal , https://developer.riotgames.com/application-process.html

## 키 종류

| 종류 | 용도 | 유효기간 / 한도 | 비고 |
|---|---|---|---|
| 개발용 (Development) | 혼자 시험·프로토타입 | 24시간마다 만료 | 공개 서비스용이 아님 |
| 개인용 (Personal) | 개발자 본인 또는 소규모 비공개 커뮤니티 | 만료 없음, 초당 20회·2분당 100회 | 제품 등록 필요, 한도 상향 불가 |
| 정식 (Production) | 일반 공개 서비스 | 만료 없음 | 제품 등록 + 검증, 실제 도메인 필요, 승인까지 수개월 걸린다는 후기 있음 |

## 이 사이트에 맞는 순서
1. ~~개인용 키 신청~~ (2026-10-25 완료, `.env`의 `RIOT_API_KEY`)
2. **공개 서비스로 운영할 때**: 도메인을 연결한 뒤 정식 키를 신청한다. 승인 전까지는 공개 홍보를 하지 않는다.

## 신청 전 점검 (현재 상태)
- [x] 라이엇 데이터가 아닌 생성(난수) 통계를 실제 통계처럼 보여주지 않음 (2026-10-24 제거, `SYNTHETIC_FEATURES=0`)
- [x] 실존 프로게이머 이름을 가짜 기록에 쓰지 않음 (생성 소환사·시드 공략 팁 삭제)
- [x] 라이엇 비보증 고지문을 사이트 푸터에 표시
- [x] 호출량 제한: 매치 상세 DB 캐시, 랭킹 갱신 5분 1회, 소환사 갱신 IP당 1분 10회, 랭킹 화면 대량 프리패치 제거
- [x] 개발자 포털 로그인 자동화 스크립트 사용 중단 (`auto_renew_riot_key.py`, 2026-10-25 삭제)
- [x] 사이트 이름 carry.gg로 통일 (2026-10-25, 화면 표기 LOL.GG 교체)
- [x] 수집기 호출량 상한: 120초당 40회, 최신 패치 2만 게임이면 감속, 오래된 패치 자동 삭제
- [ ] 실제 도메인 연결 (정식 키 신청 시 필요)

## 제품 설명 초안 (영문, 신청서에 붙여 넣고 상황에 맞게 수정)

> carry.gg is a Korean-language League of Legends stats site.
> Users search a Riot ID to see the player's current Solo/Flex rank (League-V4), recent matches
> (Match-V5: champion, KDA, items, runes, spells, teams), top champion mastery (Champion-Mastery-V4) and
> whether they are in a game (Spectator-V5 active-games). A ladder page lists Korean Challenger players.
> Aggregate pages (champion tier list, builds/runes, 1v1 matchups, duo synergy, patch-to-patch win-rate shifts)
> are computed only from high-tier Korean solo-queue matches we collect through Match-V5, starting from the
> apex ladders. The collector has its own budget (40 requests / 120 s, the rest of the limit is kept for
> visitors), stores each match once in compact form, slows down once a patch has 20,000 games and deletes
> matches older than the two latest patches. Match details are cached so each match is requested once, ladder and
> mastery refreshes run once a day, and per-user refreshes are rate limited. No generated or estimated numbers are
> shown as statistics; pages without enough real data are hidden. Riot's legal boilerplate is in the footer.
> APIs used: ACCOUNT-V1, SUMMONER-V4, LEAGUE-V4, MATCH-V5, CHAMPION-MASTERY-V4, SPECTATOR-V5.

## 키 등록
관리자 콘솔(http://127.0.0.1:300/admin)의 Riot API 키 패널에 붙여 넣으면 즉시 적용되고 `.env`에 저장됩니다.
