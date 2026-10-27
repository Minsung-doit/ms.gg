/* ==========================================================================
   carry.gg Service Worker (PWA Offline & Fast Cache Engine)
   Session 10: Mobile PWA Specialist
   ========================================================================== */

// 캐시 이름을 바꾸면 activate 단계에서 이전 버전 캐시(분할 전 app.js 시절 HTML·JS 포함)를 모두 지운다
const CACHE_NAME = 'lolgg-pwa-v3';

// 오프라인 안내용으로만 쓰는 최소 에셋 (HTML은 넣지 않는다: 매 요청 ?v= 가 바뀌는 페이지라 캐시본이 곧 낡은 버전이 된다)
const PRECACHE_ASSETS = [
  '/manifest.json',
  '/static/images/pwa-icon-192.png',
  '/static/images/pwa-icon-512.png',
  '/static/images/apple-touch-icon.png',
  '/static/images/pwa-icon.svg'
];

const OFFLINE_HTML = `<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>carry.gg - 오프라인 모드</title><style>body{background:#0f131a;color:#f8fafc;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;padding:20px;box-sizing:border-box;text-align:center}.box{background:#1a202c;padding:32px 24px;border-radius:16px;border:1px solid #334155;max-width:400px}h1{color:#e84057;font-size:1.4rem;margin-bottom:12px}p{color:#94a3b8;font-size:0.95rem;line-height:1.5;margin-bottom:20px}button{background:#38bdf8;color:#0f172a;border:none;padding:10px 20px;border-radius:8px;font-weight:700;font-size:0.95rem;cursor:pointer}</style></head><body><div class="box"><h1>오프라인 상태입니다</h1><p>현재 인터넷 연결이 불안정하거나 끊겼습니다.<br>네트워크 연결을 확인한 후 다시 시도해주세요.</p><button onclick="window.location.reload()">새로고침</button></div></body></html>`;

// 1. Service Worker 설치 (Install Event)
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => Promise.allSettled(
        PRECACHE_ASSETS.map((url) =>
          fetch(url, { cache: 'no-cache' }).then((res) => {
            if (res.ok) return cache.put(url, res);
          }).catch(() => {/* Ignore individual precache failures */})
        )
      ))
      .then(() => self.skipWaiting())
  );
});

// 2. 활성화: 현재 버전이 아닌 캐시는 전부 삭제 (이전 lolgg-pwa-v2.0.0 / lolgg-pwa-dynamic-v1 포함)
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

// 3. 네트워크 요청 가로채기 (Fetch Event)
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // 1) API: 서비스워커가 관여하지 않는다.
  //    - 실데이터 API(전적·관전·랭킹)는 라이엇 호출로 수 초가 걸릴 수 있어 타임아웃으로 끊으면 안 되고,
  //    - 오래된 응답을 캐시에서 꺼내 보여주거나 200 "offline" 응답을 지어내면 안 된다.
  //    오프라인이면 fetch 가 실패하고 화면이 각자 오류 상태를 보여준다.
  if (url.pathname.startsWith('/api/')) return;

  // 2) HTML 페이지: 항상 네트워크 (낡은 HTML이 낡은 ?v= 스크립트를 부르지 않도록). 실패할 때만 오프라인 안내
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() => new Response(OFFLINE_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8' } }))
    );
    return;
  }

  // 3) 같은 출처 정적 파일: 네트워크 우선, 오프라인일 때만 캐시. ?v= 는 요청마다 바뀌므로 경로 기준 한 벌만 보관
  if (url.origin === self.location.origin && (url.pathname.startsWith('/static/') || url.pathname === '/manifest.json')) {
    const cacheKey = url.origin + url.pathname;
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(cacheKey, copy));
          }
          return res;
        })
        .catch(() => caches.match(cacheKey).then((cached) => cached || Response.error()))
    );
    return;
  }

  // 4) 그 외(CDN 이미지·폰트 등)는 브라우저 기본 동작에 맡긴다
});

// 4. 클라이언트 메시지 수신 핸들러 (업데이트 알림 등)
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
