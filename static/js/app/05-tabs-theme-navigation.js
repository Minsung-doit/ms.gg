// Background Pre-warm for All 9 Tabs (빈 탭 0초 방지)
// 생성(난수) 데이터 기반 탭: SYNTHETIC_FEATURES 가 꺼져 있으면 미리 불러오지 않고 열 수도 없다
// (관전 탭은 2026-10-25부터 샘플 배너와 함께 열린다: app/sample_data.py)
const SYNTHETIC_TABS = new Set([]);

function prewarmAllTabs() {
  const tabs = ["leaderboard", "multisearch", "tierlist", "spectator", "masters", "duofinder", "matchup"]
    .filter(tab => window.SYNTHETIC_FEATURES || !SYNTHETIC_TABS.has(tab));
  const prewarmTasks = tabs.map(tab => () => {
    if (window._tabLoaders && typeof window._tabLoaders[tab] === "function") window._tabLoaders[tab]();
  });

  prewarmTasks.forEach((task, i) => {
    setTimeout(() => {
      try {
        task();
      } catch (e) {
        console.warn("Prewarm task failed:", e);
      }
    }, 150 + (i * 120));
  });
}
window.initHomeTrendingRankers = initHomeTrendingRankers;
window.prewarmAllTabs = prewarmAllTabs;

// Banners Interactivity Module
function initBanners() {
  // Top Live Notification Banner
  const topLiveBanner = document.getElementById("topLiveBanner");
  const btnCloseTopBanner = document.getElementById("btnCloseTopBanner");
  const bannerPatchBtn = document.getElementById("bannerPatchBtn");

  try {
    if (localStorage.getItem("hide_top_banner") === "true" && topLiveBanner) {
      topLiveBanner.classList.add("hidden");
    }
  } catch (e) {}

  if (btnCloseTopBanner && topLiveBanner) {
    btnCloseTopBanner.addEventListener("click", () => {
      topLiveBanner.classList.add("hidden");
      try {
        localStorage.setItem("hide_top_banner", "true");
      } catch (e) {}
    });
  }

  if (bannerPatchBtn) {
    bannerPatchBtn.addEventListener("click", () => {
      const btnPatch = document.getElementById("btnOpenPatchNotes");
      if (btnPatch) btnPatch.click();
    });
  }

  // Hero 3-Column Feature Banners
  const bannerCardPatch = document.getElementById("bannerCardPatch");
  const bannerCardMulti = document.getElementById("bannerCardMulti");
  const bannerCardMasters = document.getElementById("bannerCardMasters");

  if (bannerCardPatch) {
    const handlePatch = () => {
      const btnPatch = document.getElementById("btnOpenPatchNotes");
      if (btnPatch) btnPatch.click();
    };
    bannerCardPatch.addEventListener("click", handlePatch);
    bannerCardPatch.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handlePatch();
      }
    });
  }

  if (bannerCardMulti) {
    const handleMulti = () => {
      const tabMulti = document.getElementById("tabBtnMultiSearch");
      if (tabMulti) tabMulti.click();
    };
    bannerCardMulti.addEventListener("click", handleMulti);
    bannerCardMulti.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleMulti();
      }
    });
  }

  if (bannerCardMasters) {
    const handleMasters = () => {
      const tabMasters = document.getElementById("tabBtnMasters");
      if (tabMasters) tabMasters.click();
    };
    bannerCardMasters.addEventListener("click", handleMasters);
    bannerCardMasters.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleMasters();
      }
    });
  }

  const bannerCardSpectator = document.getElementById("bannerCardSpectator");
  if (bannerCardSpectator) {
    const handleSpectator = () => {
      switchMainTab("spectator");
    };
    bannerCardSpectator.addEventListener("click", handleSpectator);
    bannerCardSpectator.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleSpectator();
      }
    });
  }
}
// Theme Toggle (화이트 / 블랙 모드) Module
const btnThemeToggle = document.getElementById("btnThemeToggle");
const themeIcon = document.getElementById("themeIcon");
const themeLabel = document.getElementById("themeLabel");

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem("lolgg_theme", theme);
  } catch (e) {}

  if (theme === "light") {
    if (themeIcon) themeIcon.className = "fa-solid fa-moon";
    if (themeLabel) themeLabel.textContent = "블랙 모드";
    if (btnThemeToggle) btnThemeToggle.setAttribute("title", "블랙 모드(다크)로 전환");
  } else {
    if (themeIcon) themeIcon.className = "fa-solid fa-sun";
    if (themeLabel) themeLabel.textContent = "화이트 모드";
    if (btnThemeToggle) btnThemeToggle.setAttribute("title", "화이트 모드(라이트)로 전환");
  }
}

function initTheme() {
  let saved = "dark";
  try {
    saved = localStorage.getItem("lolgg_theme") || "dark";
  } catch (e) {}
  applyTheme(saved);

  if (btnThemeToggle) {
    btnThemeToggle.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "dark";
      const next = current === "dark" ? "light" : "dark";
      applyTheme(next);
    });
  }
}
// Tab Switching (소환사 검색 vs 소환사 랭킹 vs 장인 랭킹 vs 챔피언 티어표)
const tabBtnSearch = document.getElementById("tabBtnSearch");
const tabBtnLeaderboard = document.getElementById("tabBtnLeaderboard");
const tabBtnMasters = document.getElementById("tabBtnMasters");
const tabBtnTierList = document.getElementById("tabBtnTierList");
const tabBtnMultiSearch = document.getElementById("tabBtnMultiSearch");
const viewSearch = document.getElementById("viewSearch");
const viewLeaderboard = document.getElementById("viewLeaderboard");
const viewMasters = document.getElementById("viewMasters");
const viewTierList = document.getElementById("viewTierList");
const viewMultiSearch = document.getElementById("viewMultiSearch");
const tabBtnDuoFinder = document.getElementById("tabBtnDuoFinder");
const tabBtnMatchup = document.getElementById("tabBtnMatchup");
const viewDuoFinder = document.getElementById("viewDuoFinder");
const viewMatchup = document.getElementById("viewMatchup");

let isLeaderboardInitialized = false;
let isMastersInitialized = false;
let isTierListInitialized = false;
let isMultiSearchInitialized = false;
let isSpectatorInitialized = false;
let isDuoFinderInitialized = false;
let isMatchupInitialized = false;

// 전역 탭 로더 레지스트리
window._tabLoaders = {
  leaderboard: function() {
    if (!isLeaderboardInitialized) {
      isLeaderboardInitialized = true;
      initLeaderboard();
    } else {
      loadLeaderboard(currentLbTier || "ALL");
    }
  },
  multisearch: function() {
    if (!isMultiSearchInitialized) {
      isMultiSearchInitialized = true;
      initMultiSearch();
    }
  },
  spectator: function() {
    if (!isSpectatorInitialized) {
      isSpectatorInitialized = true;
      initSpectator();
    }
  },
  masters: function() {
    if (!isMastersInitialized) {
      isMastersInitialized = true;
      initChampionMasters();
    } else if (!currentChampId && allChampionsCache && allChampionsCache.length > 0) {
      selectChampion(allChampionsCache[0].id);
    }
  },
  tierlist: function() {
    if (!isTierListInitialized) {
      isTierListInitialized = true;
      initChampionTierList();
    }
  },
  duofinder: function() {
    if (!isDuoFinderInitialized) {
      isDuoFinderInitialized = true;
      initDuoFinder();
    }
  },
  matchup: function() {
    if (!isMatchupInitialized) {
      isMatchupInitialized = true;
      initChampionMatchup();
    }
  },
  serverranking: function() { loadServerRanking(); }
};

// 전역 탭 전환 엔진 (모든 탭 100% 즉시 전환 & 데이터 연동 보장)
window.switchMainTab = function(targetTab, direction = null) {
  if (!targetTab) return;
  if (!window._tabLoaders[targetTab] && !["search", "serverranking", "champion", "summoner"].includes(targetTab)) targetTab = "search";
  // 소환사 페이지를 떠나면 전적 창을 닫는다 (주소도 / 로 돌아감)
  if (targetTab !== "summoner") document.getElementById("playerDetailModal")?.classList.remove("active");
  if (!window.SYNTHETIC_FEATURES && SYNTHETIC_TABS.has(targetTab)) {
    showToast("이 기능은 실제 데이터 기반으로 준비 중입니다.", "info");
    targetTab = "search";
  }

  // 햅틱 진동 피드백 (모바일 환경에서 탭 터치/스와이프 시 미세 햅틱)
  try {
    if (typeof navigator !== "undefined" && navigator.vibrate) {
      navigator.vibrate(10);
    }
  } catch (_) {}

  const tabMapping = {
    search: { btn: document.getElementById("tabBtnSearch"), view: document.getElementById("viewSearch") },
    leaderboard: { btn: document.getElementById("tabBtnLeaderboard"), view: document.getElementById("viewLeaderboard") },
    multisearch: { btn: document.getElementById("tabBtnMultiSearch"), view: document.getElementById("viewMultiSearch") },
    spectator: { btn: document.getElementById("tabBtnSpectator"), view: document.getElementById("viewSpectator") },
    masters: { btn: document.getElementById("tabBtnMasters"), view: document.getElementById("viewMasters") },
    tierlist: { btn: document.getElementById("tabBtnTierList"), view: document.getElementById("viewTierList") },
    duofinder: { btn: document.getElementById("tabBtnDuoFinder"), view: document.getElementById("viewDuoFinder") },
    matchup: { btn: document.getElementById("tabBtnMatchup"), view: document.getElementById("viewMatchup") },
    serverranking: { btn: document.getElementById("tabBtnServerRanking"), view: document.getElementById("viewServerRanking") },
    champion: { btn: null, view: document.getElementById("viewChampion") },
    summoner: { btn: null, view: document.getElementById("viewSummoner") }
  };

  // 1. 모든 탭 버튼 상태 업데이트 (상단 GNB & 모바일 하단 독 연동)
  document.querySelectorAll(".nav-tab, .mobile-dock-btn").forEach(btn => {
    const tabName = btn.getAttribute("data-tab");
    if (tabName) {
      const isActive = (tabName === targetTab);
      btn.classList.toggle("active", isActive);
      if (btn.classList.contains("mobile-dock-btn")) {
        btn.setAttribute("aria-selected", isActive ? "true" : "false");
      }
    }
  });

  // 1-2. 모바일 하단 독 '전체메뉴' 버튼 및 바텀시트 서브탭 동기화
  const sheetSubTabs = ["masters", "tierlist", "matchup", "duofinder"];
  const isSheetSubTab = sheetSubTabs.includes(targetTab);
  const menuBtn = document.getElementById("btnOpenMobileMenuSheet");
  if (menuBtn) {
    menuBtn.classList.toggle("active", isSheetSubTab);
    menuBtn.classList.toggle("active-subtab", isSheetSubTab);
  }

  document.querySelectorAll(".sheet-grid-item[data-tab]").forEach(item => {
    const tabName = item.getAttribute("data-tab");
    item.classList.toggle("active", tabName === targetTab);
  });

  // 1-3. 상단 GNB 가로 스크롤 활성 탭 중앙 정렬 동기화
  const activeGnb = document.querySelector(`.nav-tab[data-tab="${targetTab}"]`);
  if (activeGnb && typeof activeGnb.scrollIntoView === "function") {
    activeGnb.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }

  // 2. 모든 탭 뷰 전환 (display & active & directional slide class)
  document.querySelectorAll(".tab-view").forEach(view => {
    view.style.setProperty("display", "none", "important");
    view.classList.remove("active", "tab-slide-next", "tab-slide-prev");
  });

  const currentTabObj = tabMapping[targetTab];
  if (currentTabObj && currentTabObj.view) {
    currentTabObj.view.style.setProperty("display", "block", "important");
    if (direction === "next") {
      currentTabObj.view.classList.add("tab-slide-next");
    } else if (direction === "prev") {
      currentTabObj.view.classList.add("tab-slide-prev");
    }
    currentTabObj.view.classList.add("active");
  } else {
    // ID 기반 fallback
    const viewIdMap = {
      search: "viewSearch",
      leaderboard: "viewLeaderboard",
      multisearch: "viewMultiSearch",
      spectator: "viewSpectator",
      masters: "viewMasters",
      tierlist: "viewTierList",
      duofinder: "viewDuoFinder",
      matchup: "viewMatchup",
      serverranking: "viewServerRanking"
    };
    const el = document.getElementById(viewIdMap[targetTab]);
    if (el) {
      el.style.setProperty("display", "block", "important");
      if (direction === "next") {
        el.classList.add("tab-slide-next");
      } else if (direction === "prev") {
        el.classList.add("tab-slide-prev");
      }
      el.classList.add("active");
    }
  }

  // 화면 최상단 부드러운 스크롤
  window.scrollTo({ top: 0, behavior: "smooth" });

  try {
    if (window._tabLoaders && typeof window._tabLoaders[targetTab] === "function") {
      window._tabLoaders[targetTab]();
    }
  } catch (err) {
    console.error("Tab initialization error:", targetTab, err);
  }

  // 4. 활성 탭 본문 영역에 맞춘 좌/우 스카이스크래퍼 광고 마진 동적 재정렬
  if (typeof updateSkyscraperPosition === "function") {
    setTimeout(updateSkyscraperPosition, 30);
  }
};

// 상단 네비게이션 탭 및 하단 독 이벤트 위임 (자식 요소 클릭 포함 100% 보장)
document.addEventListener("click", (e) => {
  const navTabBtn = e.target.closest(".nav-tab, .mobile-dock-btn[data-tab]");
  if (navTabBtn) {
    const tabName = navTabBtn.getAttribute("data-tab");
    if (tabName) {
      e.preventDefault();
      window.switchMainTab(tabName);
    }
  }
});

// 모바일 하단 도크 터치 즉시 햅틱 피드백 (0ms 레이턴시)
document.addEventListener("touchstart", (e) => {
  const dockBtn = e.target.closest(".mobile-dock-btn, .sheet-grid-item");
  if (dockBtn) {
    try {
      if (typeof navigator !== "undefined" && navigator.vibrate) {
        navigator.vibrate(10);
      }
    } catch (_) {}
  }
}, { passive: true });
