// carry.gg - 상단 헤더 검색창 & 자동완성 모듈 (19-header-search.js)
// 1. 헤더 검색창: 입력 후 Enter -> performSearch(text)
// 2. 자동완성: 챔피언(allChampionsCache / loadChampionsList / matchesChampion) -> openChampionPage(c.id)
//    최근 검색 소환사: getRecentSearches() 전역 함수 재사용
// 3. 홈 화면(viewSearch active)에서는 큰 검색창이 있으므로 헤더 검색창 숨김
// 4. 모바일(390px): 아이콘 버튼으로 축소 후 탭 시 전체 폭 확장

(function initHeaderSearch() {
  "use strict";

  // DOM Elements
  const wrapper = document.getElementById("headerSearchWrapper");
  const form = document.getElementById("headerSearchForm");
  const input = document.getElementById("headerSearchInput");
  const dropdown = document.getElementById("headerSearchDropdown");
  const btnClear = document.getElementById("btnHeaderSearchClear");
  const btnMobileOpen = document.getElementById("btnHeaderSearchMobileOpen");
  const btnMobileClose = document.getElementById("btnHeaderSearchMobileClose");

  if (!wrapper || !form || !input || !dropdown) {
    return;
  }

  let debounceTimer = null;
  let currentHighlightIdx = -1;

  // ── HTML Escape Helper ──
  function esc(str) {
    if (typeof window.escapeHtml === "function") {
      return window.escapeHtml(str);
    }
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // ── 챔피언 캐시 확보 헬퍼 ──
  async function getChampionsList() {
    if (typeof window.allChampionsCache !== "undefined" && Array.isArray(window.allChampionsCache) && window.allChampionsCache.length > 0) {
      return window.allChampionsCache;
    }
    if (typeof window.loadChampionsList === "function") {
      try {
        await window.loadChampionsList();
        if (typeof window.allChampionsCache !== "undefined" && Array.isArray(window.allChampionsCache) && window.allChampionsCache.length > 0) {
          return window.allChampionsCache;
        }
      } catch (_) {}
    }
    try {
      const res = await fetch("/api/champions");
      if (res.ok) {
        const data = await res.json();
        const list = data.champions || [];
        list.sort((a, b) => (a.name || "").localeCompare(b.name || "", "ko"));
        window.allChampionsCache = list;
        return list;
      }
    } catch (_) {}
    return [];
  }

  // ── 챔피언 검색 매칭 판정 ──
  function matchChampion(c, query) {
    if (typeof window.matchesChampion === "function") {
      return window.matchesChampion(c, query);
    }
    if (!query) return true;
    const q = String(query).trim().toLowerCase().replace(/\s+/g, "");
    if (!q) return true;
    const name = String(c.name || "").toLowerCase().replace(/\s+/g, "");
    const id = String(c.id || "").toLowerCase().replace(/\s+/g, "");
    const title = String(c.title || "").toLowerCase().replace(/\s+/g, "");
    return name.includes(q) || id.includes(q) || title.includes(q);
  }

  // ── 챔피언 아이콘 URL 추출 ──
  function getChampionImgUrl(c) {
    if (!c) return "";
    if (c.image) {
      if (c.image.startsWith("http://") || c.image.startsWith("https://") || c.image.startsWith("/")) {
        return c.image;
      }
      return `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/${c.image}`;
    }
    if (c.id) {
      return `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/${c.id}.png`;
    }
    return "";
  }

  // ── 최근 검색 소환사 가져오기 (전역 함수 getRecentSearches 재사용) ──
  function getRecentList() {
    if (typeof window.getRecentSearches === "function") {
      try {
        const res = window.getRecentSearches();
        if (Array.isArray(res)) return res;
      } catch (_) {}
    }
    return [];
  }

  // ── 1. 홈 화면 여부 판정 및 헤더 검색창 숨김/노출 제어 ──
  function isHomeScreen() {
    const viewSearch = document.getElementById("viewSearch");
    if (!viewSearch) return false;
    const isHidden = viewSearch.style.display === "none";
    const isActive = viewSearch.classList.contains("active");
    return isActive && !isHidden;
  }

  function updateVisibility() {
    if (isHomeScreen()) {
      wrapper.classList.add("header-search-hidden");
      closeDropdown();
      collapseMobile();
    } else {
      wrapper.classList.remove("header-search-hidden");
    }
  }

  // 뷰 상태 변경 감지: MutationObserver + switchMainTab 훅
  const viewSearchEl = document.getElementById("viewSearch");
  if (viewSearchEl) {
    const obs = new MutationObserver(() => updateVisibility());
    obs.observe(viewSearchEl, { attributes: true, attributeFilter: ["class", "style"] });
  }

  const origSwitchMainTab = window.switchMainTab;
  window.switchMainTab = function(targetTab, direction) {
    const res = typeof origSwitchMainTab === "function" ? origSwitchMainTab.apply(this, arguments) : undefined;
    updateVisibility();
    return res;
  };

  window.addEventListener("DOMContentLoaded", updateVisibility);
  window.addEventListener("pageshow", updateVisibility);
  window.addEventListener("popstate", updateVisibility);
  setTimeout(updateVisibility, 50);

  // ── 2. 검색 실행 (Enter / 클릭) ──
  function doSearch(text) {
    const q = (text || "").trim();
    if (!q) return;

    closeDropdown();
    collapseMobile();

    if (typeof window.performSearch === "function") {
      window.performSearch(q);
    } else {
      const mainSearchInput = document.getElementById("searchInput");
      const mainSearchForm = document.getElementById("searchForm");
      if (mainSearchInput) mainSearchInput.value = q;
      if (mainSearchForm) {
        if (typeof mainSearchForm.requestSubmit === "function") {
          mainSearchForm.requestSubmit();
        } else {
          const evt = new Event("submit", { cancelable: true });
          mainSearchForm.dispatchEvent(evt);
        }
      }
    }
  }

  // 챔피언 선택 실행
  function selectChampion(champId, champName) {
    closeDropdown();
    collapseMobile();
    if (input) input.value = champName || champId;

    if (typeof window.openChampionPage === "function") {
      window.openChampionPage(champId);
    } else if (typeof window.openChampionBuildModal === "function") {
      window.openChampionBuildModal(champId);
    } else if (typeof window.performSearch === "function") {
      window.performSearch(champName || champId);
    }
  }

  // ── 3. 드롭다운 닫기 / 열기 ──
  function closeDropdown() {
    dropdown.style.display = "none";
    dropdown.innerHTML = "";
    currentHighlightIdx = -1;
  }

  function updateClearBtn() {
    if (!btnClear) return;
    btnClear.style.display = (input.value && input.value.trim().length > 0) ? "inline-flex" : "none";
  }

  // ── 4. 자동완성 렌더링 ──
  async function renderHeaderDropdown() {
    const query = (input.value || "").trim();
    currentHighlightIdx = -1;

    // 쿼리가 비어 있을 때: 최근 검색 소환사 표출
    if (!query) {
      const recents = getRecentList();
      if (!recents || recents.length === 0) {
        closeDropdown();
        return;
      }

      let html = `
        <div class="hs-drop-header">
          <span><i class="fa-solid fa-clock-rotate-left" style="margin-right: 4px;"></i>최근 검색</span>
          <span style="font-size: 0.68rem; opacity: 0.7;">${recents.slice(0, 5).length}개</span>
        </div>
      `;

      recents.slice(0, 5).forEach((r, idx) => {
        const gn = r.game_name || "";
        const tag = r.tag_line || "KR1";
        const full = `${gn}#${tag}`;
        html += `
          <div class="hs-drop-item hs-recent-item" data-type="recent" data-index="${idx}" data-gn="${esc(gn)}" data-tag="${esc(tag)}">
            <div class="hs-recent-left">
              <span class="hs-recent-dot"></span>
              <span class="hs-recent-name">${esc(gn)}</span>
              <span class="hs-recent-tag">#${esc(tag)}</span>
            </div>
            <button type="button" class="hs-recent-del" data-gn="${esc(gn)}" data-tag="${esc(tag)}" title="삭제" aria-label="기록 삭제">
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>
        `;
      });

      dropdown.innerHTML = html;
      dropdown.style.display = "block";
      bindDropdownEvents();
      return;
    }

    // 쿼리가 있을 때: 일치 챔피언 + 일치 최근 검색어
    const champions = await getChampionsList();
    const matchedChamps = champions.filter(c => matchChampion(c, query)).slice(0, 6);

    const recents = getRecentList();
    const matchedRecents = recents.filter(r => {
      const gn = (r.game_name || "").toLowerCase();
      const qLower = query.toLowerCase();
      return gn.includes(qLower);
    }).slice(0, 3);

    if (matchedChamps.length === 0 && matchedRecents.length === 0) {
      dropdown.innerHTML = `
        <div class="hs-empty">
          <span>'${esc(query)}' 검색 (Enter)</span>
        </div>
      `;
      dropdown.style.display = "block";
      return;
    }

    let html = "";
    let itemCounter = 0;

    // 챔피언 섹션
    if (matchedChamps.length > 0) {
      html += `
        <div class="hs-drop-header">
          <span><i class="fa-solid fa-fire" style="color: var(--primary); margin-right: 4px;"></i>챔피언</span>
        </div>
      `;

      matchedChamps.forEach(c => {
        const imgUrl = getChampionImgUrl(c);
        html += `
          <div class="hs-drop-item hs-champ-item" data-type="champ" data-index="${itemCounter++}" data-cid="${esc(c.id)}" data-cname="${esc(c.name)}">
            <div class="hs-item-left">
              <img class="hs-champ-img" src="${esc(imgUrl)}" alt="${esc(c.name)}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
              <div class="hs-item-meta">
                <span class="hs-champ-name">${esc(c.name)}</span>
                ${c.title ? `<span class="hs-champ-title">${esc(c.title)}</span>` : ""}
              </div>
            </div>
            <span class="hs-tag-pill">챔피언</span>
          </div>
        `;
      });
    }

    // 최근 검색어 섹션
    if (matchedRecents.length > 0) {
      html += `
        <div class="hs-drop-header">
          <span><i class="fa-solid fa-clock-rotate-left" style="margin-right: 4px;"></i>소환사 기록</span>
        </div>
      `;

      matchedRecents.forEach(r => {
        const gn = r.game_name || "";
        const tag = r.tag_line || "KR1";
        html += `
          <div class="hs-drop-item hs-recent-item" data-type="recent" data-index="${itemCounter++}" data-gn="${esc(gn)}" data-tag="${esc(tag)}">
            <div class="hs-recent-left">
              <span class="hs-recent-dot"></span>
              <span class="hs-recent-name">${esc(gn)}</span>
              <span class="hs-recent-tag">#${esc(tag)}</span>
            </div>
            <button type="button" class="hs-recent-del" data-gn="${esc(gn)}" data-tag="${esc(tag)}" title="삭제" aria-label="기록 삭제">
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>
        `;
      });
    }

    dropdown.innerHTML = html;
    dropdown.style.display = "block";
    bindDropdownEvents();
  }

  // ── 5. 드롭다운 이벤트 바인딩 ──
  function bindDropdownEvents() {
    dropdown.querySelectorAll(".hs-champ-item").forEach(item => {
      item.addEventListener("click", () => {
        const cid = item.getAttribute("data-cid");
        const cname = item.getAttribute("data-cname");
        selectChampion(cid, cname);
      });
    });

    dropdown.querySelectorAll(".hs-recent-item").forEach(item => {
      item.addEventListener("click", (e) => {
        if (e.target.closest(".hs-recent-del")) return;
        const gn = item.getAttribute("data-gn");
        const tag = item.getAttribute("data-tag") || "KR1";
        doSearch(`${gn}#${tag}`);
      });
    });

    dropdown.querySelectorAll(".hs-recent-del").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const gn = btn.getAttribute("data-gn");
        const tag = btn.getAttribute("data-tag") || "KR1";
        if (typeof window.getRecentSearches === "function" && typeof window.saveRecentSearches === "function") {
          const list = window.getRecentSearches();
          const updated = list.filter(item => !(
            String(item.game_name).toLowerCase() === String(gn).toLowerCase() &&
            String(item.tag_line || "KR1").toLowerCase() === String(tag || "KR1").toLowerCase()
          ));
          window.saveRecentSearches(updated);
        }
        renderHeaderDropdown();
      });
    });
  }

  // ── 6. 키보드 내비게이션 (방향키 및 Enter) ──
  function setHighlight(idx) {
    const items = dropdown.querySelectorAll(".hs-drop-item");
    if (!items.length) return;
    if (idx < 0) idx = items.length - 1;
    if (idx >= items.length) idx = 0;
    currentHighlightIdx = idx;

    items.forEach((it, i) => {
      if (i === idx) {
        it.classList.add("hs-highlighted");
        it.scrollIntoView({ block: "nearest" });
      } else {
        it.classList.remove("hs-highlighted");
      }
    });
  }

  input.addEventListener("keydown", (e) => {
    const isDropOpen = dropdown.style.display === "block";

    if (e.key === "ArrowDown") {
      if (isDropOpen) {
        e.preventDefault();
        setHighlight(currentHighlightIdx + 1);
      }
    } else if (e.key === "ArrowUp") {
      if (isDropOpen) {
        e.preventDefault();
        setHighlight(currentHighlightIdx - 1);
      }
    } else if (e.key === "Enter") {
      if (isDropOpen && currentHighlightIdx >= 0) {
        const items = dropdown.querySelectorAll(".hs-drop-item");
        if (items[currentHighlightIdx]) {
          e.preventDefault();
          items[currentHighlightIdx].click();
          return;
        }
      }
      e.preventDefault();
      doSearch(input.value);
    } else if (e.key === "Escape") {
      closeDropdown();
      collapseMobile();
      input.blur();
    }
  });

  // ── 7. 실시간 타이핑 (100ms 디바운스) ──
  input.addEventListener("input", () => {
    updateClearBtn();
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      renderHeaderDropdown();
    }, 100);
  });

  input.addEventListener("focus", () => {
    updateClearBtn();
    renderHeaderDropdown();
  });

  // 폼 제출 핸들러
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    doSearch(input.value);
  });

  // 지우기 버튼
  if (btnClear) {
    btnClear.addEventListener("click", () => {
      input.value = "";
      updateClearBtn();
      input.focus();
      renderHeaderDropdown();
    });
  }

  // 외부 클릭 시 드롭다운 닫기
  document.addEventListener("click", (e) => {
    if (!wrapper.contains(e.target)) {
      closeDropdown();
      collapseMobile();
    }
  });

  // ── 8. 모바일(390px) 전용 펼침 / 접힘 컨트롤 ──
  function expandMobile() {
    wrapper.classList.add("is-expanded");
    input.focus();
    updateClearBtn();
    renderHeaderDropdown();
  }

  function collapseMobile() {
    wrapper.classList.remove("is-expanded");
    closeDropdown();
  }

  if (btnMobileOpen) {
    btnMobileOpen.addEventListener("click", () => {
      expandMobile();
    });
  }

  if (btnMobileClose) {
    btnMobileClose.addEventListener("click", () => {
      collapseMobile();
    });
  }

  // 초기 상태 설정
  updateVisibility();
})();
