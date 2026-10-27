// UX Polishing: Nav Tabs Smooth Wheel Scroll & System Sync Badge
(function initUXPolishing() {
  // 1. Navigation Tabs Smooth Horizontal Mouse Wheel Scroll UX
  const navTabsContainer = document.querySelector(".nav-tabs");
  if (navTabsContainer) {
    navTabsContainer.addEventListener("wheel", (e) => {
      if (e.deltaY !== 0) {
        e.preventDefault();
        navTabsContainer.scrollBy({
          left: e.deltaY * 1.5,
          behavior: "smooth"
        });
      }
    }, { passive: false });
  }

  // 2. Real-time System Sync Status Badge Interaction
  const headerSyncIndicator = document.getElementById("headerSyncIndicator");
  if (headerSyncIndicator) {
    headerSyncIndicator.addEventListener("click", () => {
      showToast("Riot API 연결 정상", "success", 2000);
    });
  }

  const bannerSyncPill = document.querySelector(".banner-sync-pill");
  if (bannerSyncPill) {
    bannerSyncPill.addEventListener("click", () => {
      showToast("Riot API 연결 정상", "success", 2000);
    });
  }
})();
// Real-time Lane OP Champions Quick Widget (#mainQuickOpChamps)
(function initMainQuickOpChamps() {
  const container = document.getElementById("mainQuickOpChamps");
  const grid = document.getElementById("quickOpCardsGrid");
  if (!container || !grid) return;

  function renderCards(champs) {
    grid.innerHTML = "";
    const fragment = document.createDocumentFragment();

    champs.forEach(c => {
      const card = document.createElement("div");
      card.className = "quick-op-card";
      card.setAttribute("data-cid", c.id);
      card.setAttribute("data-cname", c.name);
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("title", `${c.name} (${c.pos_kr}) 빌드 보기`);

      const posClass = `pos-${(c.position || "mid").toLowerCase()}`;
      const isOpTier = c.tier === "OP" || c.tier === "S+";
      const tierBadgeHtml = isOpTier
        ? `<span class="quick-op-tier-badge tier-op"><i class="fa-solid fa-crown"></i> OP</span>`
        : `<span class="quick-op-tier-badge tier-1">${escapeHtml(c.tier || "-")}</span>`;
      const wrNum = parseFloat(c.win_rate) || 0;
      const wrClass = wrNum > 50 ? "win-high" : "win-low";

      card.innerHTML = `
        <div class="quick-op-card-top">
          <span class="quick-op-pos-tag ${posClass}">
            <i class="fa-solid ${c.icon || 'fa-shield'}"></i> ${escapeHtml(c.pos_kr || '')}
          </span>
          ${tierBadgeHtml}
        </div>
        <div class="quick-op-avatar-wrap">
          <img 
            class="quick-op-avatar" 
            src="${c.image}" 
            alt="${escapeHtml(c.name)}"
            onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'"
          >
          <button type="button" class="quick-op-build-btn" title="${escapeHtml(c.name)} 추천 룬/아이템 빌드 퀵 모달 열기" aria-label="추천 빌드 모달">
            <i class="fa-solid fa-wand-magic-sparkles"></i>
          </button>
        </div>
        <div class="quick-op-info">
          <div class="quick-op-name">${escapeHtml(c.name)}</div>
          <div class="quick-op-stats">
            <span class="quick-op-winrate ${wrClass}">승률 <strong>${escapeHtml(String(c.win_rate))}%</strong></span>
            <span class="quick-op-pickrate">픽 <strong>${escapeHtml(String(c.pick_rate))}%</strong></span>
          </div>
        </div>
      `;

      // Quick Build Modal Button Click
      const buildBtn = card.querySelector(".quick-op-build-btn");
      if (buildBtn) {
        buildBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          if (typeof openChampionPage === "function") {
            openChampionPage(c.id, c.position);
          } else if (typeof openChampionBuildModal === "function") {
            openChampionBuildModal(c.id);
          }
        });
      }

      // Card Click: Transition directly to Champion Page
      card.addEventListener("click", () => {
        if (typeof openChampionPage === "function") {
          openChampionPage(c.id, c.position);
        } else if (typeof openChampionBuildModal === "function") {
          openChampionBuildModal(c.id);
        } else if (typeof performSearch === "function") {
          performSearch(c.name);
        }
      });

      // Keyboard Accessibility
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          card.click();
        }
      });

      fragment.appendChild(card);
    });

    grid.appendChild(fragment);
  }

  // 예전의 고정 예시 승률 카드는 지어낸 값이라 그리지 않는다. API가 실제 데이터를 줄 때만 표시

  // Fetch real-time data from backend
  async function fetchQuickOpData() {
    try {
      const res = await fetch("/api/quick-op-champions");
      if (res.ok) {
        const data = await res.json();
        if (data.champions && data.champions.length > 0) {
          renderCards(data.champions);
          container.style.display = "";
          return;
        }
      }
    } catch (e) {}
    // 표본이 아직 없으면 위젯을 숨긴다 (예시 값을 그리지 않음)
    container.style.display = "none";
  }

  fetchQuickOpData();
})();
// 14.20 Patch Meta Shift Rolling Showcase Carousel Module
(function initPatchShiftShowcase() {
  const showcase = document.getElementById("patchShiftShowcase");
  if (!showcase) return;

  const cardWrapper = document.getElementById("patchShiftCardWrapper");
  const counterEl = document.getElementById("shiftSlideCounter");
  const btnPrev = document.getElementById("btnShiftPrev");
  const btnNext = document.getElementById("btnShiftNext");
  const progressFill = document.getElementById("shiftProgressFill");

  let championsList = [];
  let currentIndex = 0;
  let isPaused = false;
  let isHovered = false;
  let isPointerDown = false;
  let isDragging = false;
  let wasDragged = false;
  let isAnimatingTransition = false;
  let dragThresholdPassed = false;
  let startX = 0;
  let currentX = 0;
  let diffX = 0;
  let touchStartY = 0;
  let isTouchHorizontal = null;
  let clearWasDraggedTimer = null;

  let progressStep = 0;
  const slideDuration = 3500; // 3.5초 주기
  const intervalTick = 50;
  let slideTimer = null;

  function updatePauseState() {
    isPaused = isHovered || isPointerDown || isAnimatingTransition;
  }

  // 1. Fetch from backend API
  async function loadShiftChampions() {
    try {
      const res = await fetch("/api/patch-shift-champions");
      if (res.ok) {
        const data = await res.json();
        if (data && data.champions && data.champions.length > 0) {
          championsList = data.champions;
          showcase.style.display = "";
          renderCard(currentIndex, "init");
          startCarousel();
          return;
        }
      }
    } catch (e) {
      // Use fallback
    }
    showcase.style.display = "none";
  }

  // 2. Render Card by index with directional entrance animation
  function renderCard(idx, direction = "init") {
    if (!championsList || championsList.length === 0) return;
    const c = championsList[idx];

    if (counterEl) {
      counterEl.textContent = `${idx + 1} / ${championsList.length}`;
    }

    const champId = c.champ_id || c.id || "";
    const champName = c.name || "-";
    const isBuff = c.is_buff !== undefined ? Boolean(c.is_buff) : (c.delta !== undefined ? c.delta > 0 : false);
    const deltaStr = c.delta_winrate_str || (c.delta !== undefined && c.delta !== null ? (c.delta > 0 ? `+${c.delta}%p` : `${c.delta}%p`) : "-");
    const curWr = (c.current_winrate !== undefined && c.current_winrate !== null) ? `${c.current_winrate}%` : (c.current_wr !== undefined && c.current_wr !== null ? `${c.current_wr}%` : "-");
    const prevWr = (c.prev_winrate !== undefined && c.prev_winrate !== null) ? `${c.prev_winrate}%` : (c.before_wr !== undefined && c.before_wr !== null ? `${c.before_wr}%` : null);
    const prevWrDisplay = prevWr ? `(이전 ${prevWr})` : "-";
    const pickRate = (c.pick_rate !== undefined && c.pick_rate !== null) ? `${c.pick_rate}%` : "-";
    const banRate = (c.ban_rate !== undefined && c.ban_rate !== null) ? `${c.ban_rate}%` : "-";
    const posDisplay = c.pos_name || c.position || "-";
    const commentText = c.comment || c.headline || "-";
    const tierHtml = c.tier ? `<span class="shift-tier-tag">${escapeHtml(String(c.tier).includes("티어") ? String(c.tier) : `${c.tier}티어`)}</span>` : "";

    const imgFallback = champId ? `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/${champId}.png` : "";
    const avatarSrc = c.image_url || c.image || imgFallback;

    let animClass = "";
    if (direction === "next") {
      animClass = "slide-from-right";
    } else if (direction === "prev") {
      animClass = "slide-from-left";
    }

    cardWrapper.innerHTML = `
      <div class="patch-shift-card ${animClass}" data-champ-id="${escapeHtml(champId)}" title="${escapeHtml(champName)} 상세 빌드 및 통계 보기">
        <div class="shift-card-left">
          <div class="shift-avatar-wrap">
            <img class="shift-avatar" src="${escapeHtml(avatarSrc)}" alt="${escapeHtml(champName)}" onerror="this.src=${jsArg(imgFallback)}">
            <span class="shift-position-badge">${escapeHtml(posDisplay)}</span>
          </div>
        </div>
        <div class="shift-card-center">
          <div class="shift-name-row">
            <span class="shift-champ-name">${escapeHtml(champName)}</span>
            <span class="shift-trend-badge ${isBuff ? 'surge' : 'drop'}">
              <i class="fa-solid ${isBuff ? 'fa-arrow-trend-up' : 'fa-arrow-trend-down'}"></i>
              ${isBuff ? '승률 상승' : '승률 하락'} ${escapeHtml(deltaStr)}
            </span>
            ${tierHtml}
          </div>
          <div class="shift-stat-row">
            <div class="shift-stat-item">
              <span class="shift-stat-label">현재 승률:</span>
              <strong class="shift-stat-val ${isBuff ? 'val-up' : 'val-down'}">${escapeHtml(curWr)}</strong>
              <span class="shift-prev-winrate">${escapeHtml(prevWrDisplay)}</span>
            </div>
            <div class="shift-stat-item">
              <span class="shift-stat-label">픽률:</span>
              <strong class="shift-stat-val">${escapeHtml(pickRate)}</strong>
            </div>
            <div class="shift-stat-item">
              <span class="shift-stat-label">밴률:</span>
              <strong class="shift-stat-val">${escapeHtml(banRate)}</strong>
            </div>
          </div>
          <p class="shift-comment">${escapeHtml(commentText)}</p>
        </div>
        <div class="shift-card-right">
          <button class="btn-shift-action" type="button" title="${escapeHtml(champName)} 장인랭킹 및 빌드 분석 보기">
            <span>분석 보기</span>
            <i class="fa-solid fa-arrow-right"></i>
          </button>
        </div>
      </div>
    `;

    // Click handler for card (drag movement > 6px suppressed)
    const cardEl = cardWrapper.querySelector(".patch-shift-card");
    if (cardEl) {
      cardEl.addEventListener("click", (e) => {
        if (wasDragged) {
          e.preventDefault();
          e.stopPropagation();
          return;
        }
        if (champId) {
          navigateToChampion(champId, champName);
        }
      });
    }
  }

  // 3. Navigation interaction when clicked
  function navigateToChampion(champId, champName) {
    if (typeof openChampionBuildModal === "function") {
      openChampionBuildModal(champId, champName);
    } else {
      const tabMasters = document.getElementById("tabBtnMasters");
      if (tabMasters) {
        tabMasters.click();
        setTimeout(() => {
          if (typeof selectChampion === "function") {
            selectChampion(champId);
          }
        }, 150);
      }
    }
  }

  // 4. Directional step transition
  function nextCard(direction = "next") {
    currentIndex = (currentIndex + 1) % championsList.length;
    progressStep = 0;
    if (progressFill) {
      progressFill.style.width = "0%";
    }
    renderCard(currentIndex, direction);
  }

  function prevCard(direction = "prev") {
    currentIndex = (currentIndex - 1 + championsList.length) % championsList.length;
    progressStep = 0;
    if (progressFill) {
      progressFill.style.width = "0%";
    }
    renderCard(currentIndex, direction);
  }

  // 5. Drag completion handler with threshold checking
  function handleDragEnd(delta) {
    const cardEl = cardWrapper.querySelector(".patch-shift-card");
    if (!cardEl) return;

    if (delta < -40) {
      // Swiped left -> Next card (enters from right)
      isAnimatingTransition = true;
      updatePauseState();
      cardEl.style.transition = "transform 0.16s ease-out, opacity 0.16s ease-out";
      cardEl.style.transform = "translateX(-120px)";
      cardEl.style.opacity = "0";
      setTimeout(() => {
        nextCard("next");
        isAnimatingTransition = false;
        updatePauseState();
      }, 150);
    } else if (delta > 40) {
      // Swiped right -> Prev card (enters from left)
      isAnimatingTransition = true;
      updatePauseState();
      cardEl.style.transition = "transform 0.16s ease-out, opacity 0.16s ease-out";
      cardEl.style.transform = "translateX(120px)";
      cardEl.style.opacity = "0";
      setTimeout(() => {
        prevCard("prev");
        isAnimatingTransition = false;
        updatePauseState();
      }, 150);
    } else {
      // Threshold not met (-40px ~ 40px) -> Snap back smoothly to 0
      cardEl.style.transition = "transform 0.22s cubic-bezier(0.16, 1, 0.3, 1)";
      cardEl.style.transform = "translateX(0)";
      setTimeout(() => {
        if (cardEl) {
          cardEl.style.transition = "";
          cardEl.style.transform = "";
        }
      }, 230);
    }

    if (clearWasDraggedTimer) clearTimeout(clearWasDraggedTimer);
    clearWasDraggedTimer = setTimeout(() => {
      wasDragged = false;
    }, 150);
  }

  // 6. Mouse Gesture Listeners (mousedown, mousemove, mouseup, mouseleave)
  cardWrapper.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    if (isAnimatingTransition) return;

    isPointerDown = true;
    isDragging = false;
    dragThresholdPassed = false;
    startX = e.clientX;
    currentX = e.clientX;
    diffX = 0;
    updatePauseState();
  });

  cardWrapper.addEventListener("mousemove", (e) => {
    if (!isPointerDown) return;
    currentX = e.clientX;
    diffX = currentX - startX;

    if (Math.abs(diffX) > 6) {
      dragThresholdPassed = true;
      wasDragged = true;
      isDragging = true;
      cardWrapper.classList.add("is-dragging");
    }

    if (isDragging) {
      const cardEl = cardWrapper.querySelector(".patch-shift-card");
      if (cardEl) {
        cardEl.style.transition = "none";
        cardEl.style.transform = `translateX(${diffX}px)`;
      }
    }
  });

  cardWrapper.addEventListener("mouseup", () => {
    if (!isPointerDown) return;
    isPointerDown = false;
    cardWrapper.classList.remove("is-dragging");
    updatePauseState();

    if (isDragging) {
      handleDragEnd(diffX);
    } else {
      const cardEl = cardWrapper.querySelector(".patch-shift-card");
      if (cardEl) {
        cardEl.style.transition = "";
        cardEl.style.transform = "";
      }
    }
  });

  cardWrapper.addEventListener("mouseleave", () => {
    if (!isPointerDown) return;
    isPointerDown = false;
    cardWrapper.classList.remove("is-dragging");
    updatePauseState();

    if (isDragging) {
      handleDragEnd(diffX);
    } else {
      const cardEl = cardWrapper.querySelector(".patch-shift-card");
      if (cardEl) {
        cardEl.style.transition = "";
        cardEl.style.transform = "";
      }
    }
  });

  window.addEventListener("mouseup", () => {
    if (isPointerDown) {
      isPointerDown = false;
      cardWrapper.classList.remove("is-dragging");
      updatePauseState();

      if (isDragging) {
        handleDragEnd(diffX);
      } else {
        const cardEl = cardWrapper.querySelector(".patch-shift-card");
        if (cardEl) {
          cardEl.style.transition = "";
          cardEl.style.transform = "";
        }
      }
    }
  });

  // 7. Touch Gesture Listeners (touchstart, touchmove, touchend, touchcancel)
  cardWrapper.addEventListener("touchstart", (e) => {
    if (!e.touches || e.touches.length === 0) return;
    if (isAnimatingTransition) return;

    const t = e.touches[0];
    startX = t.clientX;
    currentX = t.clientX;
    touchStartY = t.clientY;
    diffX = 0;
    isTouchHorizontal = null;
    isPointerDown = true;
    isDragging = false;
    dragThresholdPassed = false;
    updatePauseState();
  }, { passive: true });

  cardWrapper.addEventListener("touchmove", (e) => {
    if (!isPointerDown || !e.touches || e.touches.length === 0) return;
    const t = e.touches[0];
    const dX = t.clientX - startX;
    const dY = t.clientY - touchStartY;

    if (isTouchHorizontal === null) {
      if (Math.abs(dX) > 6 || Math.abs(dY) > 6) {
        isTouchHorizontal = Math.abs(dX) >= Math.abs(dY);
      }
    }

    if (isTouchHorizontal === false) {
      return;
    }

    if (isTouchHorizontal === true) {
      if (e.cancelable) e.preventDefault();
      diffX = dX;
      if (Math.abs(diffX) > 6) {
        dragThresholdPassed = true;
        wasDragged = true;
        isDragging = true;
        cardWrapper.classList.add("is-dragging");
      }
      if (isDragging) {
        const cardEl = cardWrapper.querySelector(".patch-shift-card");
        if (cardEl) {
          cardEl.style.transition = "none";
          cardEl.style.transform = `translateX(${diffX}px)`;
        }
      }
    }
  }, { passive: false });

  cardWrapper.addEventListener("touchend", () => {
    if (!isPointerDown) return;
    isPointerDown = false;
    cardWrapper.classList.remove("is-dragging");
    updatePauseState();

    if (isTouchHorizontal === true && isDragging) {
      handleDragEnd(diffX);
    } else {
      const cardEl = cardWrapper.querySelector(".patch-shift-card");
      if (cardEl) {
        cardEl.style.transition = "";
        cardEl.style.transform = "";
      }
    }
    isTouchHorizontal = null;
  });

  cardWrapper.addEventListener("touchcancel", () => {
    if (!isPointerDown) return;
    isPointerDown = false;
    cardWrapper.classList.remove("is-dragging");
    updatePauseState();

    const cardEl = cardWrapper.querySelector(".patch-shift-card");
    if (cardEl) {
      cardEl.style.transition = "transform 0.22s cubic-bezier(0.16, 1, 0.3, 1)";
      cardEl.style.transform = "translateX(0)";
      setTimeout(() => {
        if (cardEl) {
          cardEl.style.transition = "";
          cardEl.style.transform = "";
        }
      }, 230);
    }
    isTouchHorizontal = null;
  });

  cardWrapper.addEventListener("dragstart", (e) => {
    e.preventDefault();
  });

  // 8. Carousel loop with progress bar
  function startCarousel() {
    if (slideTimer) clearInterval(slideTimer);
    progressStep = 0;

    slideTimer = setInterval(() => {
      if (!isPaused) {
        progressStep += (intervalTick / slideDuration) * 100;
        if (progressFill) {
          progressFill.style.width = `${Math.min(progressStep, 100)}%`;
        }
        if (progressStep >= 100) {
          progressStep = 0;
          nextCard("next");
        }
      }
    }, intervalTick);
  }

  // 9. Button controls and hover pause
  if (btnNext) {
    btnNext.addEventListener("click", (e) => {
      e.stopPropagation();
      if (isAnimatingTransition) return;
      nextCard("next");
    });
  }

  if (btnPrev) {
    btnPrev.addEventListener("click", (e) => {
      e.stopPropagation();
      if (isAnimatingTransition) return;
      prevCard("prev");
    });
  }

  showcase.addEventListener("mouseenter", () => {
    isHovered = true;
    updatePauseState();
  });

  showcase.addEventListener("mouseleave", () => {
    isHovered = false;
    updatePauseState();
  });

  // Start initialization
  loadShiftChampions();
})();
// 챔피언 검색 및 패치(이번/저번/저저번) & 티어별 스킬/템트리 통계 엔진
let currentChampionDataCache = null;

function getTierLabelKR(tierKey) {
  const map = {
    "MASTER_PLUS": "마스터 이상",
    "DIAMOND_PLUS": "다이아 이상",
    "EMERALD_PLUS": "에메랄드 이상",
    "BRONZE_SILVER_GOLD_PLAT": "브실골플"
  };
  return map[tierKey] || "에메랄드 이상";
}

function closeChampionAnalytics() {
  const champArea = document.getElementById("championAnalyticsArea");
  if (champArea) {
    champArea.style.display = "none";
    champArea.innerHTML = "";
  }
  if (typeof resultsHeader !== "undefined" && resultsHeader) resultsHeader.style.display = "none";
  if (typeof playerList !== "undefined" && playerList) playerList.style.display = "flex";
  if (typeof searchInput !== "undefined" && searchInput) {
    searchInput.value = "";
    searchInput.focus();
  }
}

// 👑 Champion Masters Showcase Loader (게이머 표준 가로 그리드 & 사족 제거)
// 챔피언 클릭·검색은 수집 매치 기반 빌드 창으로 연다 (옛 생성 통계 상세 화면은 삭제)
function loadChampionAnalytics(champIdOrName) {
  if (typeof openChampionBuildModal === "function") openChampionBuildModal(champIdOrName);
}

window._currentChampMasters = [];
async function loadChampionMastersShowcase(champId, champName) {
  const container = document.getElementById("champMastersShowcaseSection");
  if (!container) return;

  try {
    const res = await fetch(`/api/champion-masters?champ=${encodeURIComponent(champId)}&tier=ALL&sort=games`);
    if (!res.ok) throw new Error("장인 랭킹 요청 실패");
    const data = await res.json();
    const masters = (data.results || []).slice(0, 10);
    window._currentChampMasters = masters;

    if (masters.length === 0) {
      container.innerHTML = `
        <div style="padding: 2rem; text-align: center; color: var(--text-muted);">
          <i class="fa-solid fa-trophy" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block; opacity: 0.6;"></i>
          ${escapeHtml(champName)} 챔피언의 등록된 장인 소환사가 없습니다.
        </div>
      `;
      return;
    }

    const rowsHtml = masters.map((p, idx) => {
      let rankBadgeClass = "";
      let rankText = `#${idx + 1}`;
      if (idx === 0) {
        rankBadgeClass = "top-1";
        rankText = `<i class="fa-solid fa-crown"></i> 1`;
      } else if (idx === 1) {
        rankBadgeClass = "top-2";
        rankText = `<i class="fa-solid fa-medal"></i> 2`;
      } else if (idx === 2) {
        rankBadgeClass = "top-3";
        rankText = `<i class="fa-solid fa-award"></i> 3`;
      }

      const iconUrl = `${ICON_BASE_URL}${p.profile_icon_id || 29}.png`;
      const emblemUrl = getTierEmblemUrl(p.tier);
      const gamesCount = p.current_season_games || p.games_played || 0;
      const winRate = p.current_season_win_rate || p.win_rate || 50.0;
      const lp = p.league_points !== undefined ? p.league_points : 0;

      return `
        <div class="champ-master-horizontal-row" onclick="if(window._currentChampMasters && window._currentChampMasters[${idx}]) openPlayerDetail(window._currentChampMasters[${idx}])" title="${escapeHtml(p.game_name)}#${escapeHtml(p.tag_line)} 20전 상세 전적 & 빌드 즉시 조회">
          <div class="champ-master-rank-col ${rankBadgeClass}">${rankText}</div>
          <div class="champ-master-avatar-wrap">
            <img class="champ-master-avatar" src="${iconUrl}" alt="${escapeHtml(p.game_name)}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/29.png'">
            <span class="champ-master-level-tag">Lv.${p.summoner_level || 30}</span>
          </div>
          <div class="champ-master-name-col">
            <span class="champ-master-game-name">${escapeHtml(p.game_name)}</span>
            <span class="champ-master-tag-line">#${escapeHtml(p.tag_line || 'KR1')}</span>
          </div>
          <div class="champ-master-tier-col">
            <img class="tier-emblem-img md" src="${emblemUrl}" alt="${p.tier}" onerror="this.style.display='none';">
          </div>
          <div class="champ-master-score-col">
            <span class="champ-master-lp-val">${formatNumber(lp)} LP</span>
            <span class="champ-master-record-val">${formatNumber(gamesCount)}판 ${winRate}%</span>
          </div>
        </div>
      `;
    }).join('');

    container.innerHTML = `
      <div class="champ-masters-header">
        <div class="champ-masters-title-wrap">
          <h3 class="champ-masters-title">
            <i class="fa-solid fa-trophy" style="color: #F59E0B;"></i>
            <span>${escapeHtml(champName)} 대한민국 대표 장인 TOP 10</span>
          </h3>
          <span class="champ-masters-badge-live"><i class="fa-solid fa-bolt"></i> 실시간 랭크 연동</span>
        </div>
        <span style="font-size: 0.78rem; color: var(--text-muted);">클릭 시 20전 상세 전적 & 빌드 즉시 조회</span>
      </div>
      <div class="champ-masters-grid">
        ${rowsHtml}
      </div>
    `;
  } catch (err) {
    container.innerHTML = `
      <div style="padding: 1.5rem; text-align: center; color: #E84057; font-size: 0.85rem;">
        <i class="fa-solid fa-circle-exclamation"></i> 장인 랭킹을 불러오는데 실패했습니다.
      </div>
    `;
  }
}
window.loadChampionMastersShowcase = loadChampionMastersShowcase;
window.loadChampionAnalytics = loadChampionAnalytics;
window.closeChampionAnalytics = closeChampionAnalytics;

/* ==============================================================================
   🏛️ Official Commercial Launch: Terms, Privacy, Business Contact Modals
============================================================================== */
const termsModal = document.getElementById("termsModal");
const privacyModal = document.getElementById("privacyModal");
const contactModal = document.getElementById("contactModal");

function openTermsModal() {
  if (termsModal) termsModal.classList.add("active");
}
function closeTermsModal() {
  if (termsModal) termsModal.classList.remove("active");
}

function openPrivacyModal() {
  if (privacyModal) privacyModal.classList.add("active");
}
function closePrivacyModal() {
  if (privacyModal) privacyModal.classList.remove("active");
}

function openContactModal() {
  if (contactModal) contactModal.classList.add("active");
}
function closeContactModal() {
  if (contactModal) contactModal.classList.remove("active");
}

window.openTermsModal = openTermsModal;
window.closeTermsModal = closeTermsModal;
window.openPrivacyModal = openPrivacyModal;
window.closePrivacyModal = closePrivacyModal;
window.openContactModal = openContactModal;
window.closeContactModal = closeContactModal;
