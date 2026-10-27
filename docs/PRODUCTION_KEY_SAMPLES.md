# 정식(Production) 키 승인 후 실제 데이터로 바꿀 곳

정식 키가 없어 지금은 **샘플 데이터**를 보여주는 화면 목록. 화면에는 항상 "샘플 데이터" 배너가 붙고,
실존 인물(프로·스트리머·소환사) 이름은 `샘플소환사N#SAMPLE` 로 바뀌어 있다.

| 화면 | 지금 | 정식 키 후 할 일 |
|---|---|---|
| 관전 탭 · 천상계 추천 게임 피드 (`/api/spectator/featured`, `/api/spectator/featured/{id}`) | `app/spectator_engine.py` 생성 데이터 → `app/sample_data.py` `anonymize_featured()` 로 이름 제거 + `is_sample` | 라이엇 `/lol/spectator/v5/featured-games` 응답을 `app/real_data.py` `convert_live_game()` 으로 변환해 반환. `templates/index.html` 의 `#specSampleBanner` 와 JS `isSampleSpectatorGame()` 은 `is_sample` 이 false 면 자연히 꺼짐(배너는 지울 것) |
| 랭킹 탭 · 한국 서버 티어 분포 (`/api/tier-distribution/stats`) | `get_tier_distribution_stats()` 생성 수치 + `is_sample`, 카드 부제·KPI에 "샘플" 표시 | League-V4 `entries/RANKED_SOLO_5x5/{tier}/{division}` 전 페이지를 하루 1회 집계해 저장(티어×디비전×페이지 수백 회 → 정식 키 한도 필요). 부제 문구 복원 |
| 티어표 · 칼바람(ARAM) 모드 (`/api/aram/tierlist`) | `generate_aram_tier_list()` 생성 수치 + `is_sample`, 티어표 안내줄에 "⚠ 샘플" 표시 | 수집기에 queue 450(칼바람)을 별도 한도로 추가해 `compute_tier_list` 와 같은 방식으로 집계 |

## 정식 키와 상관없이 실제 데이터인 곳
소환사 검색·프로필·최근 20게임·실시간 게임(개인)·챌린저 랭킹·장인 랭킹·멀티서치·티어표·빌드·상성·듀오 시너지·패치 변동.

## 정식 키가 있으면 더 좋아지는 곳 (지금도 실데이터, 양만 적음)
- 티어표·빌드 표본: 지금은 수집기 120초당 40회(개인 키 한도 안). 정식 키 한도로 늘리면 수집 속도↑, 다이아·에메랄드 등 티어별 필터 가능.
