# 서버에 올리기 (AWS Lightsail 서울 + 디스코드 로그인)

대상: 디스코드 서버 멤버(최대 수백 명) 전용. 라이엇 개인 키로 충분하다.
비용: Lightsail 월 약 $5 + 도메인(무료 DuckDNS 또는 연 1~2만 원).

## 1. 서버 만들기 (AWS Lightsail)
1. https://lightsail.aws.amazon.com 가입 → **Create instance**
2. 지역 **Seoul (ap-northeast-2)**, 플랫폼 **Linux/Unix**, 블루프린트 **OS Only → Ubuntu 24.04 LTS**
3. 요금제 **$5 (1 GB RAM)** → 이름 `carrygg` → Create
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
PC 에서 SSH 터널을 연 상태로 브라우저 `http://localhost:300/admin`:
```powershell
ssh -i $HOME\.ssh\lightsail-seoul.pem -L 300:127.0.0.1:300 ubuntu@<고정IP>
```
관리자 비밀번호: 서버 `/opt/carrygg/.env` 의 `ADMIN_PASSWORD` (`sudo grep ADMIN_PASSWORD /opt/carrygg/.env`).

## 6-1. 디스코드 봇과 구인 알림 (선택)
- **채널 알림**: 디스코드 채널 설정 → 연동 → 웹후크 만들기 → 주소를 `.env` 의 `DISCORD_WEBHOOK_URL` 에. 새 구인글·마감·이번 주 MVP 가 올라간다.
- **게임별 알림 역할**: 서버에 `@롤구인` 같은 역할을 만들고 (역할 오른쪽 클릭 → ID 복사, 개발자 모드 필요) `DUO_ALERT_ROLES=lol=역할ID,pubg=역할ID,overwatch=역할ID`.
- **봇 (/구인 · /구인글 · /내구인 · /내전 · /내전전적 · /전적 · /배그 · /핑)**: https://discord.com/developers/applications → 봇 만들기 → 토큰을 `DISCORD_BOT_TOKEN` 에,
  아무 긴 문자열(16자 이상)을 `BOT_API_SECRET` 에 넣고 OAuth2 URL Generator 에서 `bot` + `applications.commands` 로 서버에 초대.
  봇 초대 권한은 '메시지 보내기·링크 첨부·채널 보기'면 충분 (특수 인텐트 설정 불필요). `/내전`은 명령을 쓴 사람의 음성 채널 10명을 나눈다.
  그다음 `sudo cp deploy/carrygg-bot.service /etc/systemd/system/ && sudo systemctl enable --now carrygg-bot`.
- **배그 전적 (선택)**: https://developer.pubg.com 에서 키 발급 → `PUBG_API_KEY`. 넣으면 구인 게시판 배그 글에 전적 버튼과 봇 `/배그`가 켜진다.
- **디스코드 로그인**: OAuth2 리디렉트에 `<SITE_URL>/auth/discord/callback` 추가. 범위는 `identify guilds.members.read` (서버 별명을 이름으로 씀).
- 서버 이름 표시: `COMMUNITY_NAME=우리서버이름`.

## 7. 운영
- 상태/로그: `sudo systemctl status carrygg`, `sudo tail -f /opt/carrygg/server.log`
- 재시작: `sudo systemctl restart carrygg`
- 백업: `/var/lib/carrygg/backups/` 에 하루 1개, 7일치
- 코드 업데이트: 새 carrygg.tar.gz 를 올려 `/opt/carrygg` 에 풀고(.env 는 그대로) `sudo systemctl restart carrygg`
- PC 에서 돌던 서버는 끈다 (같은 라이엇 키로 두 곳에서 수집하면 호출 한도를 나눠 쓴다)
