// Footer buttons
const footerBtnTerms = document.getElementById("footerBtnTerms");
if (footerBtnTerms) footerBtnTerms.addEventListener("click", openTermsModal);

const footerBtnPrivacy = document.getElementById("footerBtnPrivacy");
if (footerBtnPrivacy) footerBtnPrivacy.addEventListener("click", openPrivacyModal);

const footerBtnContact = document.getElementById("footerBtnContact");
if (footerBtnContact) footerBtnContact.addEventListener("click", openContactModal);

// Close buttons
const btnCloseTermsModal = document.getElementById("btnCloseTermsModal");
if (btnCloseTermsModal) btnCloseTermsModal.addEventListener("click", closeTermsModal);
const btnCloseTermsModal2 = document.getElementById("btnCloseTermsModal2");
if (btnCloseTermsModal2) btnCloseTermsModal2.addEventListener("click", closeTermsModal);

const btnClosePrivacyModal = document.getElementById("btnClosePrivacyModal");
if (btnClosePrivacyModal) btnClosePrivacyModal.addEventListener("click", closePrivacyModal);
const btnClosePrivacyModal2 = document.getElementById("btnClosePrivacyModal2");
if (btnClosePrivacyModal2) btnClosePrivacyModal2.addEventListener("click", closePrivacyModal);

const btnCloseContactModal = document.getElementById("btnCloseContactModal");
if (btnCloseContactModal) btnCloseContactModal.addEventListener("click", closeContactModal);
const btnCancelContactModal = document.getElementById("btnCancelContactModal");
if (btnCancelContactModal) btnCancelContactModal.addEventListener("click", closeContactModal);

// Overlay click to close
window.addEventListener("click", (e) => {
  if (e.target === termsModal) closeTermsModal();
  if (e.target === privacyModal) closePrivacyModal();
  if (e.target === contactModal) closeContactModal();
});

// Contact Form submission
const contactForm = document.getElementById("contactForm");
if (contactForm) {
  contactForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const company = document.getElementById("contactCompany")?.value || "";
    const name = document.getElementById("contactName")?.value || "";
    const email = document.getElementById("contactEmail")?.value || "";
    const message = document.getElementById("contactMessage")?.value || "";

    if (!company.trim() || !name.trim() || !email.trim() || !message.trim()) {
      showToast("모든 필수 입력 사항(*)을 입력해주세요.", "error");
      return;
    }

    const btnSubmit = document.getElementById("btnSubmitContact");
    if (btnSubmit) {
      btnSubmit.disabled = true;
      btnSubmit.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 접수 처리 중...';
    }

    setTimeout(() => {
      if (btnSubmit) {
        btnSubmit.disabled = false;
        btnSubmit.innerHTML = '<i class="fa-solid fa-paper-plane"></i> 문의 제안 접수하기';
      }
      contactForm.reset();
      closeContactModal();
      showToast("문의 접수 기능은 아직 준비 중입니다. GitHub Issues(github.com/Minsung-doit/ms.gg/issues)로 문의해 주세요.", "info", 5000);
      window.open("https://github.com/Minsung-doit/ms.gg/issues", "_blank", "noopener,noreferrer");
    }, 700);
  });
}

/* ==========================================================================
   Mobile PWA Native Experience & Optimization Engine
   - 모바일 하단 네비게이션 독 & 더보기 바텀시트
   - 스마트 터치 스와이프 제스처 (좌우 탭 전환 및 충돌 방지)
   - 모바일 당겨서 새로고침
   - PWA Service Worker 생명주기 및 오프라인 감지
   - A2HS 홈 화면 추가 스마트 설치 프롬프트
   ========================================================================== */

(function initMobilePwaSpecialist() {
  // 1. 모바일 하단 네비게이션 독 및 바텀 시트 연동
  const mobileMenuSheet = document.getElementById("mobileMenuSheet");
  const mobileMenuSheetOverlay = document.getElementById("mobileMenuSheetOverlay");
  const btnOpenMobileMenuSheet = document.getElementById("btnOpenMobileMenuSheet");

  window.openMobileMenuSheet = function() {
    if (mobileMenuSheet && mobileMenuSheetOverlay) {
      mobileMenuSheetOverlay.style.display = "block";
      mobileMenuSheet.style.display = "block";
      document.body.style.overflow = "hidden"; // 배경 스크롤 방지
    }
  };

  window.closeMobileMenuSheet = function() {
    if (mobileMenuSheet && mobileMenuSheetOverlay) {
      mobileMenuSheetOverlay.style.display = "none";
      mobileMenuSheet.style.display = "none";
      document.body.style.overflow = "";
    }
  };

  if (btnOpenMobileMenuSheet) {
    btnOpenMobileMenuSheet.addEventListener("click", window.openMobileMenuSheet);
  }

  // 바텀시트 내 패치노트 버튼 연동
  const btnSheetPatchNotes = document.getElementById("btnSheetPatchNotes");
  if (btnSheetPatchNotes) {
    btnSheetPatchNotes.addEventListener("click", () => {
      window.closeMobileMenuSheet();
      const patchBtn = document.getElementById("btnOpenPatchNotes");
      if (patchBtn) patchBtn.click();
    });
  }

  // 바텀시트 내 테마 전환 연동
  const btnSheetThemeToggle = document.getElementById("btnSheetThemeToggle");
  const sheetThemeVal = document.getElementById("sheetThemeVal");
  function syncSheetThemeLabel() {
    if (!sheetThemeVal) return;
    const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
    sheetThemeVal.textContent = currentTheme === "dark" ? "다크 모드" : "라이트 모드";
  }
  syncSheetThemeLabel();

  if (btnSheetThemeToggle) {
    btnSheetThemeToggle.addEventListener("click", () => {
      const themeBtn = document.getElementById("btnThemeToggle");
      if (themeBtn) themeBtn.click();
      syncSheetThemeLabel();
    });
  }

  // 바텀시트 내 새로고침 연동
  const btnSheetRefresh = document.getElementById("btnSheetRefresh");
  if (btnSheetRefresh) {
    btnSheetRefresh.addEventListener("click", () => {
      window.closeMobileMenuSheet();
      const refBtn = document.getElementById("btnGlobalRefresh");
      if (refBtn) refBtn.click();
    });
  }

  // ESC 키로 바텀시트 닫기
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && mobileMenuSheet && mobileMenuSheet.style.display === "block") {
      window.closeMobileMenuSheet();
    }
  });

  // 가상 키보드 활성화 방어: visualViewport 리사이즈 감지 시 하단 독 자동 일시 숨김
  if (typeof window !== "undefined" && window.visualViewport) {
    const bottomDock = document.getElementById("mobileBottomDock");
    window.visualViewport.addEventListener("resize", () => {
      if (!bottomDock) return;
      const isKeyboardOpen = window.visualViewport.height < (window.innerHeight * 0.78);
      bottomDock.classList.toggle("dock-hidden-keyboard", isKeyboardOpen);
    });
  }
  // 2. 스마트 터치 스와이프 제스처
  // 지원하는 9개 전체 탭 순서 (상단 GNB 탭 순서와 100% 일치)
  const SWIPE_TABS = [
    "search",
    "leaderboard",
    "multisearch",
    "spectator",
    "masters",
    "tierlist",
    "duofinder",
    "matchup"
  ];

  let touchStartX = 0;
  let touchStartY = 0;
  let touchEndX = 0;
  let touchEndY = 0;
  let touchStartTime = 0;
  let isSwipeIgnored = false;

  // 모바일 및 태블릿 디바이스 터치 환경 판정 (스마트폰 & 태블릿 <= 1024px)
  function isMobileOrTabletDevice() {
    const hasTouch = ("ontouchstart" in window) || (navigator.maxTouchPoints > 0);
    return hasTouch && window.innerWidth <= 1024;
  }

  // 가로 스크롤 가능 컨테이너, 테이블, 차트, 캐러셀 등 충돌 요소 완벽 필터
  function shouldIgnoreSwipe(element) {
    if (!element) return false;
    if (!isMobileOrTabletDevice()) return true;

    let curr = element;
    while (curr && curr !== document.body && curr !== document.documentElement) {
      const tag = curr.tagName ? curr.tagName.toLowerCase() : "";
      // 1. 입력 폼 컨트롤, 버튼 터치 시 무시
      if (tag === "input" || tag === "textarea" || tag === "select" || tag === "button") return true;
      // 2. 테이블 및 테이블 셀 (내부 데이터 가로 스크롤 및 텍스트 탐색 보호)
      if (tag === "table" || tag === "thead" || tag === "tbody" || tag === "tr" || tag === "td" || tag === "th") return true;
      // 3. 차트, 캔버스, SVG 그래픽 (레이더 차트, 그래프 드래그 조작 보호)
      if (tag === "canvas" || tag === "svg") return true;

      if (curr.classList) {
        // 4. 모달, 바텀시트, 오버레이
        if (
          curr.classList.contains("modal") ||
          curr.classList.contains("modal-card") ||
          curr.classList.contains("modal-dialog") ||
          curr.classList.contains("mobile-sheet") ||
          curr.classList.contains("mobile-sheet-overlay") ||
          curr.classList.contains("champion-build-modal") ||
          curr.classList.contains("fow-replay-modal") ||
          curr.classList.contains("build-modal-overlay")
        ) {
          return true;
        }

        // 5. 하단 독 및 상단 네비게이션 탭 바 (탭 바 자체 스크롤 보호)
        if (
          curr.classList.contains("mobile-bottom-dock") ||
          curr.classList.contains("dock-container") ||
          curr.classList.contains("mobile-dock-btn") ||
          curr.classList.contains("nav-tabs") ||
          curr.classList.contains("nav-tabs-container") ||
          curr.classList.contains("navbar-bottom")
        ) {
          return true;
        }

        // 6. 메타 급변 챔피언 캐러셀 드래그 영역 (쇼케이스 자체 스와이프와 충돌 원천 차단)
        if (
          curr.classList.contains("patch-shift-showcase") ||
          curr.classList.contains("patch-shift-card-wrapper") ||
          curr.classList.contains("patch-shift-card") ||
          curr.id === "patchShiftShowcase" ||
          curr.id === "patchShiftCardWrapper"
        ) {
          return true;
        }

        // 7. 가로 스크롤 가능 테이블 및 데이터 그리드 래퍼
        if (
          curr.classList.contains("table-scroll") ||
          curr.classList.contains("table-responsive") ||
          curr.classList.contains("leaderboard-table-wrapper") ||
          curr.classList.contains("masters-table-wrapper") ||
          curr.classList.contains("tierlist-table-wrapper") ||
          curr.classList.contains("duo-table-wrapper") ||
          curr.classList.contains("matchup-bars-wrapper") ||
          curr.classList.contains("ranking-table") ||
          curr.classList.contains("recent-matches-table") ||
          curr.classList.contains("summoner-table")
        ) {
          return true;
        }

        // 8. 차트 래퍼 및 칩 스크롤러
        if (
          curr.classList.contains("matchup-radar-container") ||
          curr.classList.contains("chart-container") ||
          curr.classList.contains("chart-wrap") ||
          curr.classList.contains("radar-canvas-wrap") ||
          curr.classList.contains("pro-tracker-grid") ||
          curr.classList.contains("recent-chips-list") ||
          curr.classList.contains("tier-filter-chips") ||
          curr.classList.contains("chips-container") ||
          curr.classList.contains("chips-scroll") ||
          curr.classList.contains("spectator-feed-track") ||
          curr.classList.contains("ad-slot") ||
          curr.classList.contains("pwa-install-banner")
        ) {
          return true;
        }
      }

      // 9. 실제 가로 스크롤(overflow-x: auto|scroll)이 존재하는 요소 보호
      if (curr.scrollWidth > curr.clientWidth + 6) {
        try {
          const computed = window.getComputedStyle(curr);
          const ox = computed.overflowX;
          if (ox === "auto" || ox === "scroll") {
            return true;
          }
        } catch (_) {}
      }

      curr = curr.parentElement;
    }
    return false;
  }

  // 현재 활성화된 탭 이름 찾기 (.tab-view.active 기준 정확한 동기화)
  function getCurrentActiveTab() {
    const activeView = document.querySelector(".tab-view.active");
    if (activeView && activeView.id) {
      const viewMap = {
        viewSearch: "search",
        viewLeaderboard: "leaderboard",
        viewMultiSearch: "multisearch",
        viewSpectator: "spectator",
        viewMasters: "masters",
        viewTierList: "tierlist",
        viewDuoFinder: "duofinder",
        viewMatchup: "matchup"
      };
      if (viewMap[activeView.id]) return viewMap[activeView.id];
    }
    const activeBtn = document.querySelector(".nav-tab.active[data-tab], .mobile-dock-btn.active[data-tab]");
    if (activeBtn) {
      return activeBtn.getAttribute("data-tab");
    }
    return "search";
  }

  let lastMoveX = 0;
  let lastMoveY = 0;
  let lastMoveTime = 0;
  let currentVelocityX = 0;
  let gestureAxis = null; // null | "horizontal" | "vertical"

  document.addEventListener("touchstart", (e) => {
    // 모바일/태블릿 터치 환경이 아니거나 멀티 터치 시 무시
    if (!isMobileOrTabletDevice() || e.touches.length > 1) {
      isSwipeIgnored = true;
      return;
    }

    isSwipeIgnored = shouldIgnoreSwipe(e.target);
    if (isSwipeIgnored) return;

    const t = e.touches[0];
    touchStartX = t.clientX;
    touchStartY = t.clientY;
    touchEndX = t.clientX;
    touchEndY = t.clientY;
    lastMoveX = t.clientX;
    lastMoveY = t.clientY;
    touchStartTime = Date.now();
    lastMoveTime = touchStartTime;
    currentVelocityX = 0;
    gestureAxis = null;
  }, { passive: true });

  document.addEventListener("touchmove", (e) => {
    if (isSwipeIgnored || e.touches.length > 1) return;

    const t = e.touches[0];
    touchEndX = t.clientX;
    touchEndY = t.clientY;

    const now = Date.now();
    const dt = now - lastMoveTime;
    if (dt > 8) {
      currentVelocityX = (t.clientX - lastMoveX) / dt; // px/ms
      lastMoveX = t.clientX;
      lastMoveY = t.clientY;
      lastMoveTime = now;
    }

    const diffX = touchEndX - touchStartX;
    const diffY = touchEndY - touchStartY;
    const absX = Math.abs(diffX);
    const absY = Math.abs(diffY);

    // 1단계: 각도 조기 판정 필터 (최소 10px 이동 시 즉시 판정)
    if (gestureAxis === null && (absX > 10 || absY > 10)) {
      const angleRad = Math.atan2(absY, absX);
      const angleDeg = angleRad * (180 / Math.PI);

      // 30도 초과(수직 방향 기울기) 시 세로 스크롤로 판정하여 탭 스와이프 즉시 무효화
      if (angleDeg > 30 || absY > absX * 0.58) {
        gestureAxis = "vertical";
        isSwipeIgnored = true;
        return;
      } else {
        gestureAxis = "horizontal";
      }
    }

    // 2단계: 수평 제스처 확정 후 도중에 세로 움직임이 급격히 커지면 안전 취소
    if (gestureAxis === "horizontal" && absY > absX * 0.75 && absY > 25) {
      isSwipeIgnored = true;
    }
  }, { passive: true });

  document.addEventListener("touchend", () => {
    if (isSwipeIgnored || !isMobileOrTabletDevice() || gestureAxis !== "horizontal") {
      gestureAxis = null;
      isSwipeIgnored = false;
      return;
    }

    const duration = Date.now() - touchStartTime;
    const diffX = touchEndX - touchStartX;
    const diffY = touchEndY - touchStartY;
    const absX = Math.abs(diffX);
    const absY = Math.abs(diffY);

    // 각도 및 가속도 종합 판정 필터:
    // 1. 지속 시간: 60ms ~ 550ms (초고속 플릭 또는 자연스러운 스와이프)
    // 2. 각도 필터: 수평 이동이 수직 이동의 1.75배 이상 (수평축 편향 30도 이내)
    // 3. 거리 및 속도(가속도) 필터:
    //    - 충분한 이동 거리: absX >= 60px
    //    - 또는 빠른 플릭: absX >= 35px 이면서 순간 속도 |currentVelocityX| >= 0.30 px/ms
    const isDeliberateSwipe = absX >= 60;
    const isQuickFlick = absX >= 35 && Math.abs(currentVelocityX) >= 0.30;
    const isAngleValid = absX >= absY * 1.75;
    const isDurationValid = duration >= 60 && duration <= 550;

    if (isDurationValid && isAngleValid && (isDeliberateSwipe || isQuickFlick)) {
      const currentTab = getCurrentActiveTab();
      const currentIndex = SWIPE_TABS.indexOf(currentTab);

      if (currentIndex !== -1) {
        if (diffX < 0) {
          // 좌측으로 스와이프: 다음 탭으로 이동 (우측에서 슬라이드 인)
          if (currentIndex < SWIPE_TABS.length - 1) {
            const nextTab = SWIPE_TABS[currentIndex + 1];
            if (typeof window.switchMainTab === "function") {
              window.switchMainTab(nextTab, "next");
            }
          }
        } else {
          // 우측으로 스와이프: 이전 탭으로 이동 (좌측에서 슬라이드 인)
          if (currentIndex > 0) {
            const prevTab = SWIPE_TABS[currentIndex - 1];
            if (typeof window.switchMainTab === "function") {
              window.switchMainTab(prevTab, "prev");
            }
          }
        }
      }
    }

    gestureAxis = null;
    isSwipeIgnored = false;
  }, { passive: true });
  // 3. 모바일 당겨서 새로고침 (Pull to Refresh - Hextech Micro Spinner & Haptics)
  const pullRefreshEl = document.getElementById("mobilePullRefresh");
  const pullRefreshText = pullRefreshEl ? pullRefreshEl.querySelector(".pull-refresh-text") : null;
  let pullStartY = 0;
  let pullStartX = 0;
  let isPulling = false;
  let hasVibratedPull = false;
  const PULL_THRESHOLD = 75; // 75px 이상 당기면 새로고침

  window.addEventListener("touchstart", (e) => {
    if (window.innerWidth <= 768 && window.scrollY === 0 && e.touches.length === 1 && !isSwipeIgnored) {
      pullStartY = e.touches[0].clientY;
      pullStartX = e.touches[0].clientX;
      isPulling = true;
      hasVibratedPull = false;
    } else {
      isPulling = false;
    }
  }, { passive: true });

  window.addEventListener("touchmove", (e) => {
    if (!isPulling || !pullRefreshEl) return;
    const currentY = e.touches[0].clientY;
    const currentX = e.touches[0].clientX;
    const pullDistance = currentY - pullStartY;
    const pullDiffX = Math.abs(currentX - pullStartX);

    // 수평 이동이 발생하면 풀 투 리프레시 즉시 취소 (좌우 스와이프 보호)
    if (pullDiffX > pullDistance * 1.1) {
      isPulling = false;
      hasVibratedPull = false;
      pullRefreshEl.classList.remove("active", "pull-ready");
      pullRefreshEl.style.top = "-70px";
      if (pullRefreshText) pullRefreshText.textContent = "당겨서 새로고침";
      return;
    }

    if (pullDistance > 15 && window.scrollY <= 0) {
      pullRefreshEl.classList.add("active");
      const clamped = Math.min(pullDistance * 0.45, 65);
      pullRefreshEl.style.top = `${clamped - 50}px`;
      
      const spinner = pullRefreshEl.querySelector(".pull-refresh-spinner");
      if (spinner) {
        const rotation = Math.min(pullDistance * 3.2, 360);
        spinner.style.transform = `rotate(${rotation}deg)`;
      }

      // 임계값 도달 시 햅틱 피드백(15ms) 및 헥스테크 골드 상태 전환
      if (pullDistance >= PULL_THRESHOLD) {
        if (!hasVibratedPull) {
          hasVibratedPull = true;
          try {
            if (typeof navigator !== "undefined" && navigator.vibrate) {
              navigator.vibrate(15);
            }
          } catch (_) {}
          pullRefreshEl.classList.add("pull-ready");
          if (pullRefreshText) pullRefreshText.textContent = "손을 놓으면 새로고침";
        }
      } else {
        if (hasVibratedPull) {
          hasVibratedPull = false;
          pullRefreshEl.classList.remove("pull-ready");
          if (pullRefreshText) pullRefreshText.textContent = "당겨서 새로고침";
        }
      }
    }
  }, { passive: true });

  window.addEventListener("touchend", (e) => {
    if (!isPulling || !pullRefreshEl) return;
    isPulling = false;

    const pullDistance = (e.changedTouches[0] ? e.changedTouches[0].clientY : 0) - pullStartY;
    if (pullDistance >= PULL_THRESHOLD && window.scrollY <= 0) {
      pullRefreshEl.classList.remove("pull-ready");
      pullRefreshEl.classList.add("refreshing");
      pullRefreshEl.style.top = "18px";
      if (pullRefreshText) pullRefreshText.textContent = "실시간 갱신 중...";

      // 트리거 시 햅틱 진동 피드백
      try {
        if (typeof navigator !== "undefined" && navigator.vibrate) {
          navigator.vibrate(15);
        }
      } catch (_) {}

      // 새로고침 실행
      const globalRefreshBtn = document.getElementById("btnGlobalRefresh");
      if (globalRefreshBtn) {
        globalRefreshBtn.click();
      }

      setTimeout(() => {
        pullRefreshEl.classList.remove("active", "refreshing");
        pullRefreshEl.style.top = "-70px";
        if (pullRefreshText) pullRefreshText.textContent = "당겨서 새로고침";
        hasVibratedPull = false;
      }, 750);
    } else {
      pullRefreshEl.classList.remove("active", "pull-ready");
      pullRefreshEl.style.top = "-70px";
      if (pullRefreshText) pullRefreshText.textContent = "당겨서 새로고침";
      hasVibratedPull = false;
    }
  }, { passive: true });
  // 4. PWA Service Worker 등록 및 오프라인 상태 감지
  const offlineNoticeToast = document.getElementById("offlineNoticeToast");
  const offlineNoticeText = document.getElementById("offlineNoticeText");

  function showOfflineNotice(isOffline) {
    if (!offlineNoticeToast) return;
    if (isOffline) {
      if (offlineNoticeText) offlineNoticeText.textContent = "네트워크 오프라인 상태입니다. 캐시된 데이터를 표시합니다.";
      offlineNoticeToast.style.backgroundColor = "rgba(239, 68, 68, 0.95)";
      offlineNoticeToast.style.display = "flex";
    } else {
      if (offlineNoticeText) offlineNoticeText.textContent = "인터넷 연결이 복구되었습니다!";
      offlineNoticeToast.style.backgroundColor = "rgba(16, 185, 129, 0.95)";
      offlineNoticeToast.style.display = "flex";
      setTimeout(() => {
        offlineNoticeToast.style.display = "none";
        offlineNoticeToast.style.backgroundColor = "";
      }, 3000);
    }
  }

  window.showOfflineNotice = showOfflineNotice;
  window.addEventListener("offline", () => showOfflineNotice(true));
  window.addEventListener("online", () => showOfflineNotice(false));

  // 앱 로드 즉시 오프라인 여부 선제 점검
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    showOfflineNotice(true);
  }

  // 글로벌 네트워크 오류 및 오프라인 상태 자동 감지 훅
  window.addEventListener("unhandledrejection", (event) => {
    if (event && event.reason && (event.reason.message === "Failed to fetch" || event.reason.name === "TypeError")) {
      if (typeof window.showOfflineNotice === "function") {
        window.showOfflineNotice(true);
      }
    }
  });

  // Service Worker 등록
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" })
        .then((reg) => {
          // 백그라운드 업데이트 감지
          reg.addEventListener("updatefound", () => {
            const newWorker = reg.installing;
            if (newWorker) {
              newWorker.addEventListener("statechange", () => {
                if (newWorker.state === "installed" && navigator.serviceWorker.controller) {
                  // 새 버전 감지 알림
                  if (typeof showToast === "function") {
                    showToast("새 버전의 앱 리소스가 업데이트되었습니다.", "info", 3000);
                  }
                }
              });
            }
          });
        })
        .catch((err) => {
          console.warn("[PWA] Service Worker registration failed:", err);
        });
    });
  }
  // 5. A2HS (Add to Home Screen) 홈 화면에 앱 설치 유도
  let deferredInstallPrompt = null;
  const pwaInstallBanner = document.getElementById("pwaInstallBanner");
  const btnPwaInstallAccept = document.getElementById("btnPwaInstallAccept");
  const btnPwaInstallDismiss = document.getElementById("btnPwaInstallDismiss");
  const btnPwaInstallSheet = document.getElementById("btnPwaInstallSheet");

  // 이미 설치되었는지 판정 (standalone 디스플레이 모드)
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;

  window.addEventListener("beforeinstallprompt", (e) => {
    // 기본 브라우저 배너 방지
    e.preventDefault();
    deferredInstallPrompt = e;

    // 이미 설치된 상태가 아니고 사용자가 닫지 않은 경우 배너 표시
    // 한 번 닫으면 다시 띄우지 않는다
    let dismissed = null;
    try { dismissed = localStorage.getItem("lolgg_pwa_dismissed"); } catch (_) {}
    if (!isStandalone && !dismissed && pwaInstallBanner) {
      setTimeout(() => {
        pwaInstallBanner.style.display = "block";
      }, 2500); // 사용자 진입 2.5초 후 부드럽게 노출
    }

    if (btnPwaInstallSheet) {
      btnPwaInstallSheet.style.display = "flex";
    }
  });

  async function triggerPwaInstall() {
    if (!deferredInstallPrompt) {
      if (typeof showToast === "function") {
        showToast("브라우저 메뉴에서 '홈 화면에 추가' 또는 '앱 설치'를 선택해주세요.", "info", 4000);
      }
      return;
    }
    deferredInstallPrompt.prompt();
    const { outcome } = await deferredInstallPrompt.userChoice;
    if (outcome === "accepted") {
      if (pwaInstallBanner) pwaInstallBanner.style.display = "none";
      if (typeof showToast === "function") {
        showToast("carry.gg 앱 설치가 완료되었습니다!", "success", 4000);
      }
    }
    deferredInstallPrompt = null;
  }

  if (btnPwaInstallAccept) {
    btnPwaInstallAccept.addEventListener("click", triggerPwaInstall);
  }

  if (btnPwaInstallSheet) {
    btnPwaInstallSheet.addEventListener("click", () => {
      window.closeMobileMenuSheet();
      triggerPwaInstall();
    });
  }

  if (btnPwaInstallDismiss) {
    btnPwaInstallDismiss.addEventListener("click", () => {
      if (pwaInstallBanner) pwaInstallBanner.style.display = "none";
      try { localStorage.setItem("lolgg_pwa_dismissed", "true"); } catch (_) {}
    });
  }

  window.addEventListener("appinstalled", () => {
    if (pwaInstallBanner) pwaInstallBanner.style.display = "none";
    if (btnPwaInstallSheet) btnPwaInstallSheet.style.display = "none";
    deferredInstallPrompt = null;
  });

  // URL 파라미터로 탭 전환 및 멀티서치 자동 실행 지원 (예: /?tab=multisearch 또는 /?summoners=Hide+on+bush,Chovy)
  const urlParams = new URLSearchParams(window.location.search);
  const initialTab = urlParams.get("tab");
  const initialSummoners = urlParams.get("summoners");

  if (initialSummoners) {
    setTimeout(() => {
      if (typeof window.switchMainTab === "function") {
        window.switchMainTab("multisearch");
      }
      const msTextarea = document.getElementById("multiSearchTextarea");
      if (msTextarea) {
        const parsed = initialSummoners.split(",").map(s => s.trim()).filter(Boolean).join("\n");
        msTextarea.value = parsed;
        if (typeof runMultiSearch === "function") {
          runMultiSearch(parsed);
        }
      }
    }, 100);
  } else if (initialTab && typeof window.switchMainTab === "function") {
    setTimeout(() => {
      window.switchMainTab(initialTab);
    }, 50);
  }
})();
// carry.gg Admin & Operations Hub (Fallback no-ops)
window.openAdminHub = function() {};
window.closeAdminHub = function() {};
window.toggleAdminHub = function() {};

// Quick Summoner Search Helper for SaaS Hero Trending Chips
function quickSearchSummoner(name, tag = "KR1") {
  const sInput = document.getElementById("searchInput");
  const fullName = tag ? `${name}#${tag}` : name;
  if (sInput) {
    sInput.value = fullName;
  }
  if (typeof switchMainTab === "function") {
    switchMainTab("search");
  }
  if (typeof performSearch === "function") {
    performSearch(fullName);
  } else {
    const sForm = document.getElementById("searchForm");
    if (sForm) {
      if (typeof sForm.requestSubmit === "function") {
        sForm.requestSubmit();
      } else {
        const evt = new Event("submit", { cancelable: true });
        sForm.dispatchEvent(evt);
      }
    }
  }
}
window.quickSearchSummoner = quickSearchSummoner;


