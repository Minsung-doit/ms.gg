# 서버에 올리기 (AWS Lightsail 서울 + 디스코드 로그인)

대상: 디스코드 서버 멤버(최대 수백 명) 전용 (디스코드 로그인으로 막힌 사이트).
라이엇 키: 멤버 전용 시험 운영은 개인(Personal) 키. 누구나 들어오는 공개 서비스나 유료화는 Production 승인 뒤에만 (docs/RIOT_API_KEY_GUIDE.md).
비용: Lightsail 2 GB 요금제(금액은 Lightsail 화면 기준) + 도메인(무료 DuckDNS 또는 연 1~2만 원).

## 1. 서버 만들기 (AWS Lightsail)
1. https://lightsail.aws.amazon.com 가입 → **Create instance**
2. 지역 **Seoul (ap-northeast-2)**, 플랫폼 **Linux/Unix**, 블루프린트 **OS Only → Ubuntu 24.04 LTS**
3. 요금제 **2 GB RAM** (1 GB 는 매치 수집기·봇을 같이 돌리기에 부족) → 이름 `carrygg` → Create
4. 인스턴스 → **Networking**
   - **Attach static IP** (고정 IP, 무료)
   - IPv4 방화벽에 **HTTPS (443)** 추가 (SSH 22, HTTP 80 은 기본으로 열려 있음)
5. **Account → SSH keys** 에서 서울 기본 키(.pem) 다운로드 → `C:\Users\<나>\.ssh\lightsail-seoul.pem`

## 2. 주소(도메인)
- 무료: https://www.duckdns.org 로그인 → 하위 도메인 만들기(예: `jangin`) → IP 에 고정 IP 입력 → `jangin.duckdns.org`
- 정식 이름을 사면(예: jangin.gg) DNS 에 **A 레코드 → 고정 IP** 하나만 추가하면 된다.

## 3. 디스코드 로그인 앱
1. https://discord.com/developers/applications → **New Application** (이름: 사이트 이름)
2. **OAuth2** 메뉴
   - **Client ID** 복사, **Reset Secret** 으로 Client Secret 복사 (한 번만 보임)
   - **Redirects** 에 `https://<도메인>/auth/discord/callback` 추가 → Save
3. 서버 ID: 디스코드 설정 → 고급 → **개발자 모드** 켜기 → 서버 아이콘 우클릭 → **서버 ID 복사**

## 4. 코드·데이터 올리기 (PC 에서)
Claude 가 `deploy_bundle/` 에 코드 압축본(carrygg.tar.gz)과 현재 DB 백업을 만들어 둔다. PowerShell:
```powershell
scp -i $HOME\.ssh\lightsail-seoul.pem deploy_bundle\carrygg.tar.gz deploy_bundle\opgg.db ubuntu@<고정IP>:/tmp/
ssh -i $HOME\.ssh\lightsail-seoul.pem ubuntu@<고정IP>
```

## 5. 서버에서 설치 (ssh 접속한 창)
```bash
sudo mkdir -p /opt/carrygg /var/lib/carrygg
sudo tar -xzf /tmp/carrygg.tar.gz -C /opt/carrygg
sudo mv /tmp/opgg.db /var/lib/carrygg/opgg.db
sudo cp /opt/carrygg/deploy/env.server.example /opt/carrygg/.env
sudo nano /opt/carrygg/.env        # 라이엇 키, 도메인, 디스코드 값 3개 채우기 → Ctrl+O, Enter, Ctrl+X
sudo bash /opt/carrygg/deploy/setup.sh <도메인>
```
1~2분 뒤 `https://<도메인>` 접속 → 디스코드 로그인 → 사이트.

## 6. 관리자 콘솔 (서버 밖에서는 안 열림)
서버에서는 관리자 포트가 3300 이다 (리눅스는 1024 미만 포트를 일반 계정이 못 연다, setup.sh 가 `ADMIN_PORT=3300` 을 넣어 둠).
PC 에서 SSH 터널을 연 상태로 브라우저 `http://localhost:3300/admin`:
```powershell
ssh -i $HOME\.ssh\lightsail-seoul.pem -L 3300:127.0.0.1:3300 ubuntu@<고정IP>
```
관리자 비밀번호: 서버 `/opt/carrygg/.env` 의 `ADMIN_PASSWORD` (`sudo grep ADMIN_PASSWORD /opt/carrygg/.env`).

## 6-1. 디스코드 봇과 구인 알림 (선택)
- **채널 알림**: 디스코드 채널 설정 → 연동 → 웹후크 만들기 → 주소를 `.env` 의 `DISCORD_WEBHOOK_URL` 에. 새 구인글·마감·이번 주 MVP 가 올라간다.
- **게임별 알림 역할**: 서버 관리자가 디스코드에서 `/알림역할 역할:@롤` (이미 있는 역할도 됨, 역할에 '멘션 허용' 필요).
  멤버는 `/알림받기` 로 직접 달고 뗀다 (봇에 '역할 관리' 권한, 봇 역할이 그 역할보다 위). `.env` 의 `DUO_ALERT_ROLES=lol=역할ID` 도 계속 되며 봇에서 정한 값이 먼저.
- **봇 (/구인 · /구인글 · /내구인 · /내전 · /내전전적 · /전적 · /배그 · /핑)**: https://discord.com/developers/applications → 봇 만들기 → 토큰을 `DISCORD_BOT_TOKEN` 에,
  아무 긴 문자열(16자 이상)을 `BOT_API_SECRET` 에 넣고 OAuth2 URL Generator 에서 `bot` + `applications.commands` 로 서버에 초대.
  봇 초대 권한: 채널 보기·메시지 보내기·링크 첨부·**역할 관리**(알림받기·티어 역할) — 초대 주소의 permissions=268454912. 특수 인텐트 설정 불필요.
  `/내전`은 음성 채널(또는 같은 카테고리의 모든 음성 채널) 10~80명을 5:5·여러 판·토너먼트·리그로 나누고, 토너먼트·리그는 봇 진행판 버튼으로 진행한다.
  setup.sh 는 `.env` 에 `DISCORD_BOT_TOKEN` 이 있으면 봇 서비스(carrygg-bot)도 켠다. 나중에 넣었다면 `sudo cp deploy/carrygg-bot.service /etc/systemd/system/ && sudo systemctl enable --now carrygg-bot`.
- **티어 역할 자동 부여 (선택)**: 봇 초대 권한에 '역할 관리'를 더해 다시 초대 → 디스코드에서 서버의 기존 티어 역할을 연결한다.
  `/티어역할 자동연결` (역할 이름 '다이아', '💎 Diamond', '롤 골드' 등을 알아봄) → `/티어역할 보기` 로 확인 → 틀린 곳은 `/티어역할 연결 티어:골드 역할:@...`.
  한 역할을 여러 티어에 연결해도 된다 (예: 마스터·그마·챌 → @마스터+). 티어 역할이 없는 서버는 `/티어역할 만들기`.
  관리 권한이 있는 역할은 연결할 수 없다. 봇 역할을 티어 역할들보다 위로 올리고 `.env` 에 `TIER_ROLE_SYNC=1` 이면 1시간마다,
  `/티어역할 맞추기` 로 바로 맞춘다. 라이엇 로그인으로 인증한 멤버의 연결된 역할만 바꾸고, 다른 멤버·역할은 건드리지 않는다.
- **배그 전적 (선택)**: https://developer.pubg.com 에서 키 발급 → `PUBG_API_KEY`. 넣으면 구인 게시판 배그 글에 전적 버튼과 봇 `/배그`가 켜진다.
- **디스코드 로그인**: OAuth2 리디렉트에 `<SITE_URL>/auth/discord/callback` 추가. 범위는 `identify guilds.members.read` (서버 별명을 이름으로 씀).
- **라이엇 로그인 계정 인증 (RSO)**: Production 키 승인 뒤 라이엇 개발자 포털에서 RSO 클라이언트를 신청 → `RSO_CLIENT_ID` / `RSO_CLIENT_SECRET`.
  Redirect URI 는 `<SITE_URL>/auth/riot/callback`. 서버 랭킹 계정 연결은 라이엇 로그인 인증으로만 받으므로, 이 값이 없으면 멤버가 계정을 연결할 수 없다.
- **내전 토너먼트 코드 (선택)**: Production 앱 승인 뒤 앱 메시지로 토너먼트 API 사용을 신청 → 승인되면 `RIOT_TOURNAMENT=live`.
  라이엇에 등록되는 결과 알림 주소는 `<SITE_URL>/api/riot/tournament/callback` (https, 처음 코드를 발급할 때 자동 등록).
  코드로 만든 사설 게임만 승패·KDA·챔피언·골드 등이 자동 기록되고, 코드 없이 한 내전은 이긴 팀 버튼으로만 기록된다.
- 서버 이름 표시: `COMMUNITY_NAME=우리서버이름`.
- **디스코드 서버 여러 곳 (선택)**: `COMMUNITY_GUILDS=서버ID:서버이름,서버ID:서버이름` (첫 서버가 기본 서버).
  구인글·내전 기록·서버 랭킹·주간 MVP 가 서버마다 따로 보이고, 두 서버 이상에 들어가 있는 멤버는 머리말에서 서버를 바꾼다.
  채널 알림은 서버마다 `DISCORD_WEBHOOK_URL_<서버ID>` (게임별 `DISCORD_WEBHOOK_URL_<서버ID>_PUBG`), 알림 역할은 `DUO_ALERT_ROLES_<서버ID>`.
  기본 서버만 예전 이름(`DISCORD_WEBHOOK_URL`, `DUO_ALERT_ROLES`)도 쓴다. 다른 서버 글이 기본 서버 채널로 새지 않도록 대신 쓰지 않는다.
  봇은 서버마다 따로 초대하고, 등록되지 않은 서버에서 쓰면 안내만 한다.

## 7. 운영
- 상태/로그: `sudo systemctl status carrygg`, `sudo tail -f /opt/carrygg/server.log`
- 재시작: `sudo systemctl restart carrygg`
- 백업: `/var/lib/carrygg/backups/` 에 하루 1개, 7일치
- 코드 업데이트: 새 carrygg.tar.gz 를 올려 `/opt/carrygg` 에 풀고(.env 는 그대로) `sudo systemctl restart carrygg carrygg-bot`
  (새 파이썬 패키지가 생겼으면 그 전에 `sudo -u carrygg /opt/carrygg/venv/bin/pip install -r /opt/carrygg/requirements-server.txt`)
- 올리기 전에: 대화창 등에 노출된 적 있는 비밀값(봇 토큰, 관리자 비밀번호)은 새로 발급·변경해서 서버 `.env` 에만 넣는다.
- PC 에서 돌던 서버는 끈다 (같은 라이엇 키로 두 곳에서 수집하면 호출 한도를 나눠 쓴다)
