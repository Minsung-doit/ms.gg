# 🚀 [OP.GG / carry.gg] 상용 정식 서비스 런칭 마스터 가이드
### (Google AdSense 광고 승인 & Riot Production API 24시간 풀 가동 체계)

---

## 📌 목차
1. [구글 애드센스(Google AdSense) 광고 승인 및 수익화 가이드](#1-구글-애드센스-수익화-및-광고-연동-가이드)
2. [라이엇 API 키](#2-라이엇-api-키)
3. [키가 없거나 만료됐을 때의 동작](#3-키가-없거나-만료됐을-때의-동작)
4. [상용 서버 도메인 연결, SSL(HTTPS) 및 24시간 백그라운드 배포](#4-상용-서버-도메인-연결-및-24시간-백그라운드-배포)

---

## 1. 구글 애드센스 수익화 및 광고 연동 가이드

현재 코드베이스는 구글 애드센스 심사 통과 요건(Privacy Policy, Terms, Contact Modal, ads.txt 표준 서빙)을 **100% 프로덕션 규격으로 사전 완비**해 두었습니다.

### 1.1 애드센스 신청 절차 (Step-by-Step)
1. **구글 애드센스 웹사이트 접속**: [https://www.google.com/adsense](https://www.google.com/adsense)
2. **시작하기**: 구글 계정으로 로그인 후 보유하신 상용 도메인(예: `lolgg.kr`, `myopgg.com`) 입력.
3. **사이트 연결 (AdSense 코드 발급)**:
   - 애드센스에서 발급해주는 본인 고유의 게시자 ID 확인: `ca-pub-XXXXXXXXXXXXXXXX`
4. **.env 파일에 게시자 ID 등록**:
   ```env
   GOOGLE_ADSENSE_CLIENT_ID='ca-pub-1234567890123456'
   ```
   - 등록 즉시 [`templates/index.html`](../templates/index.html) 상단에 공식 Google AdSense 로더 스크립트가 자동 활성화되며, 하단 및 사이드바 광고 슬롯이 활성화됩니다.
5. **`ads.txt` 파일 확인**:
   - 구글 크롤러가 사이트 루트의 `https://당신도메인/ads.txt`를 검사합니다.
   - 프로젝트 루트의 [`ads.txt`](../ads.txt) 파일에 발급받은 pub-ID를 기입하십시오:
     ```text
     google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0
     ```
   - 백엔드에 `/ads.txt` 엔드포인트가 영구 마운트되어 있어 즉시 200 OK로 서빙됩니다.

### 1.2 애드센스 승인 통과 핵심 팁 (100% 승인 보장 세팅)
* **필수 정적 페이지 완비 여부**: 구글 심사팀은 개인정보처리방침과 이용약관이 없는 사이트를 무조건 거절합니다. 본 플랫폼은 푸터의 `개인정보처리방침`, `이용약관`, `광고 및 제휴문의` 모달이 이미 완벽히 구현되어 있습니다.
* **콘텐츠 품질**: 화면의 소환사·전적·랭킹 정보는 라이엇 API 값만 씁니다. 난수로 만든 통계 기능(티어표·빌드·상성 등)은 `SYNTHETIC_FEATURES=0`(기본)으로 꺼져 있으므로, 심사 전에 실제로 보여줄 콘텐츠가 충분한지 직접 확인하세요.

---

## 2. 라이엇 API 키

키 종류(개발용·개인용·정식), 신청 순서, 신청서 제품 설명 초안은 [`docs/RIOT_API_KEY_GUIDE.md`](RIOT_API_KEY_GUIDE.md)에 정리되어 있습니다.
요청 한도와 승인 기간은 라이엇 공식 문서(https://developer.riotgames.com/docs/portal)를 기준으로 확인하세요.

하지 말 것:
- 개발용 키를 자동으로 재발급하는 브라우저 자동화 (`auto_renew_riot_key.py`는 2026-10-25 삭제)
- 키 여러 개를 돌려 써서 만료·호출 한도를 피하는 방식 (`RIOT_API_KEY_POOL`)

---

## 3. 키가 없거나 만료됐을 때의 동작

- 키가 없거나 만료되면 실데이터 API는 503, 없는 소환사는 404를 돌려줍니다. 대체(가짜) 데이터를 만들어 보여주지 않습니다.
- 이미 받아 둔 매치 상세는 `match_cache`에 저장되어 같은 매치를 다시 요청하지 않습니다.
- 공개 서비스 중 24시간 만료가 문제라면 개인용/정식 키를 신청하는 것이 유일한 해결책입니다.

---

## 4. 상용 서버 도메인 연결 및 24시간 백그라운드 배포

### 4.1 Nginx 리버스 프록시 설정 예시 (Linux/Cloud)
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # 관리자 화면·API는 공개 도메인에서 막는다 (관리자는 서버 PC의 127.0.0.1:300/admin 에서만)
    location ^~ /admin { return 404; }
    location ^~ /api/admin/ { return 404; }
    if ($arg_mode = "admin") { return 404; }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/www/opgg/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }
}
```

### 4.2 24시간 무중단 백그라운드 서비스 등록 (Systemd 예시)
`/etc/systemd/system/lolgg.service`:
```ini
[Unit]
Description=carry.gg Commercial Production FastAPI Server
After=network.target

[Service]
# root로 실행하지 않는다: 전용 계정 생성 예) sudo useradd --system --home /var/www/opgg lolgg
User=lolgg
WorkingDirectory=/var/www/opgg
ExecStart=/var/www/opgg/venv/bin/python run.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
- 활성화: `sudo systemctl daemon-reload && sudo systemctl enable --now lolgg`
