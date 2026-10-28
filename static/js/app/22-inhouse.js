// 22-inhouse.js — 내전 팀 짜기 (5:5 사설 게임 밸런서)
// 서버 랭킹 화면(#srInhouse)에 카드로 붙어 동작한다.

(function () {
  "use strict";

  const _esc = typeof escapeHtml === "function" ? escapeHtml : function (str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  };

  const POS_NAMES_KR = {
    TOP: "탑",
    JUNGLE: "정글",
    MID: "미드",
    ADC: "원딜",
    SUPPORT: "서폿"
  };

  const POS_ICONS = {
    TOP: "fa-shield",
    JUNGLE: "fa-tree",
    MID: "fa-crosshairs",
    ADC: "fa-bullseye",
    SUPPORT: "fa-heart"
  };

  const TIER_NAMES_KR = {
    IRON: "아이언",
    BRONZE: "브론즈",
    SILVER: "실버",
    GOLD: "골드",
    PLATINUM: "플래티넘",
    EMERALD: "에메랄드",
    DIAMOND: "다이아몬드",
    MASTER: "마스터",
    GRANDMASTER: "그랜드마스터",
    CHALLENGER: "챌린저",
    UNRANKED: "언랭크"
  };

  function formatTierKr(tier, rank, lp) {
    const t = (tier || "UNRANKED").toUpperCase().trim();
    const tKr = TIER_NAMES_KR[t] || t;
    if (t === "UNRANKED") return "언랭크";
    if (t === "MASTER" || t === "GRANDMASTER" || t === "CHALLENGER") {
      return lp != null && lp > 0 ? `${tKr} ${lp}LP` : tKr;
    }
    const r = rank ? ` ${rank}` : "";
    const l = lp != null && lp > 0 ? ` ${lp}LP` : "";
    return `${tKr}${r}${l}`;
  }

  function formatNumber(num) {
    return new Intl.NumberFormat("ko-KR").format(num || 0);
  }

  // State
  let inhouseInitialized = false;
  let serverMembers = [];
  let customMembers = [];
  let selectedPlayers = [];
  let balanceOptions = [];
  let currentOptionIdx = 0;
  let customCounter = 0;
  let fetchError = null;
  let openGame = null;
  let isSavingGame = false;
  let isSubmittingResult = false;
  let selectedMode = "single";
  let modePickedByUser = false; // 직접 고르기 전에는 인원에 맞는 추천 방식을 따라간다
  let selectedSplit = "balanced";
  let currentPlan = null;
  let multiRoomGames = {};
  let currentEventId = null;

  function initInhouse() {
    const container = document.getElementById("srInhouse");
    if (!container) return;

    renderBaseLayout(container);
    restoreOpenGameIfAny();
    loadServerRankingMembers();
    loadInhouseStats();
    loadRecentEvents();
  }

  function renderBaseLayout(container) {
    container.innerHTML = `
      <div class="ih-card">
        <!-- 헤더: 제목 & 카운트 배지 -->
        <div class="ih-header">
          <div class="ih-header-left">
            <h2 class="ih-title">
              <i class="fa-solid fa-scale-balanced" style="color: var(--primary);"></i> 내전 팀 짜기
            </h2>
          </div>
          <div class="ih-header-right">
            <span class="ih-count-badge" id="ihCountBadge">선택 <strong>0</strong>명</span>
          </div>
        </div>

        <!-- 1. 멤버 목록 (서버 랭킹) -->
        <div class="ih-section">
          <div class="ih-section-header">
            <div class="ih-section-title">
              <i class="fa-solid fa-users"></i> 서버 멤버 선택
            </div>
            <button type="button" class="ih-btn-text" id="ihBtnRefreshMembers" title="서버 멤버 목록 다시 불러오기">
              <i class="fa-solid fa-arrows-rotate"></i> 새로고침
            </button>
          </div>
          <div id="ihMemberChipsContainer" class="ih-chips-wrap">
            <div class="ih-loading-members">
              <i class="fa-solid fa-spinner fa-spin"></i> 멤버 목록을 불러오는 중...
            </div>
          </div>
        </div>

        <!-- 2. 직접 추가 -->
        <div class="ih-section">
          <div class="ih-section-title">
            <i class="fa-solid fa-user-plus"></i> 직접 추가
          </div>
          <form class="ih-add-form" id="ihAddPlayerForm">
            <div class="ih-add-row">
              <div class="ih-input-wrap ih-grow">
                <input type="text" id="ihInputName" class="ih-input" placeholder="닉네임 (소환사명)" maxlength="40" autocomplete="off" required>
              </div>
              <div class="ih-select-wrap">
                <select id="ihSelectTier" class="ih-select" aria-label="티어">
                  <option value="UNRANKED">언랭크</option>
                  <option value="IRON">아이언</option>
                  <option value="BRONZE">브론즈</option>
                  <option value="SILVER">실버</option>
                  <option value="GOLD" selected>골드</option>
                  <option value="PLATINUM">플래티넘</option>
                  <option value="EMERALD">에메랄드</option>
                  <option value="DIAMOND">다이아몬드</option>
                  <option value="MASTER">마스터</option>
                  <option value="GRANDMASTER">그랜드마스터</option>
                  <option value="CHALLENGER">챌린저</option>
                </select>
              </div>
              <div class="ih-select-wrap" id="ihDivisionWrap">
                <select id="ihSelectRank" class="ih-select" aria-label="디비전">
                  <option value="IV" selected>4</option>
                  <option value="III">3</option>
                  <option value="II">2</option>
                  <option value="I">1</option>
                </select>
              </div>
              <button type="submit" id="ihBtnAdd" class="ih-btn ih-btn-primary">
                <i class="fa-solid fa-plus"></i> 추가
              </button>
            </div>
          </form>
        </div>

        <!-- 3. 참가자 명단 & 포지션 설정 -->
        <div class="ih-section">
          <div class="ih-section-header">
            <div class="ih-section-title">
              <i class="fa-solid fa-clipboard-user"></i> 참가자 명단
            </div>
            <button type="button" class="ih-btn-text" id="ihBtnClearAll" style="display: none;">
              <i class="fa-solid fa-trash-can"></i> 전체 비우기
            </button>
          </div>
          <div id="ihParticipantsList" class="ih-participants-grid">
            <div class="ih-empty-box">
              <i class="fa-solid fa-user-group"></i> 서버 멤버를 선택하거나 위에서 직접 친구를 추가해주세요 (0명)
            </div>
          </div>
        </div>

        <!-- 방식 선택 (버튼형 탭 4개 + 하위 선택 + 한 줄 설명) -->
        <div class="ih-section ih-mode-section">
          <div class="ih-section-title">
            <i class="fa-solid fa-diagram-project"></i> 방식 선택
          </div>
          <div class="ih-mode-tabs" role="tablist" id="ihModeTabs">
            <button type="button" class="ih-mode-tab active" data-mode="single" disabled>
              <i class="fa-solid fa-users"></i> 5:5 한 판
            </button>
            <button type="button" class="ih-mode-tab" data-mode="multi" disabled>
              <i class="fa-solid fa-layer-group"></i> 여러 판 동시
            </button>
            <button type="button" class="ih-mode-tab" data-mode="tournament" disabled>
              <i class="fa-solid fa-sitemap"></i> 토너먼트
            </button>
            <button type="button" class="ih-mode-tab" data-mode="league" disabled>
              <i class="fa-solid fa-trophy"></i> 리그
            </button>
          </div>
          <div class="ih-split-subwrap" id="ihSplitSubwrap" style="display: none;">
            <span class="ih-split-label"><i class="fa-solid fa-sliders"></i> 여러 판 나누기:</span>
            <button type="button" class="ih-split-chip active" data-split="balanced">모든 판 균형</button>
            <button type="button" class="ih-split-chip" data-split="tiered">실력대별 방</button>
          </div>
          <div class="ih-mode-desc" id="ihModeDesc">팀을 나누려면 최소 10명이 필요해요 (현재 0명)</div>
        </div>

        <!-- 4. 팀 나누기 액션 바 -->
        <div class="ih-action-bar">
          <button type="button" id="ihBtnBalance" class="ih-btn ih-btn-balance" disabled>
            <i class="fa-solid fa-scale-balanced"></i> 팀 나누기 (0명)
          </button>
        </div>
        <div id="ihBalanceError" class="ih-error-notice" style="display: none;"></div>

        <!-- 5. 결과 영역 (Single / Multi / Tournament Prep) -->
        <div id="ihResultSection" class="ih-result-section" style="display: none;">
          <!-- 대기자 배너 -->
          <div id="ihWaitlistWrap" style="display: none;"></div>

          <!-- 5-A: Single Mode (5:5 한 판) -->
          <div id="ihSingleResultWrap">
            <div class="ih-result-header">
              <div class="ih-result-stats">
                <span class="ih-stat-pill" id="ihResultSummaryText">
                  블루 평균 - · 점수 차 0 · 라인 손실 0
                </span>
                <span class="ih-stat-pill">
                  <i class="fa-solid fa-scale-balanced"></i> 점수 차 <strong id="ihResultDiff">0</strong>
                </span>
                <span class="ih-stat-pill" id="ihResultPenaltyPill">
                  <i class="fa-solid fa-arrows-split-up-and-left"></i> 라인 손실 <strong id="ihResultPenalty">0</strong>
                </span>
                <span class="ih-stat-pill ih-stat-warn" id="ihResultClash" style="display: none;">
                  <i class="fa-solid fa-triangle-exclamation"></i> 포지션 겹침 <strong id="ihResultClashNum">0</strong>
                </span>
              </div>
              <div class="ih-result-actions">
                <button type="button" id="ihBtnCycleOption" class="ih-btn ih-btn-secondary">
                  <i class="fa-solid fa-shuffle"></i> 다른 조합 (1/1)
                </button>
                <button type="button" id="ihBtnCopyResult" class="ih-btn ih-btn-secondary">
                  <i class="fa-solid fa-copy"></i> 복사
                </button>
                <div id="ihGameActionWrap" class="ih-game-action-wrap"></div>
              </div>
            </div>
            <div id="ihGameNotice" class="ih-error-notice" style="display: none;"></div>

            <div class="ih-teams-grid">
              <!-- 블루팀 -->
              <div class="ih-team-card ih-team-blue">
                <div class="ih-team-top">
                  <div class="ih-team-title">
                    <span class="ih-team-dot ih-dot-blue"></span> 🔵 블루팀
                  </div>
                  <div class="ih-team-avg" id="ihBlueAvg">평균 -</div>
                </div>
                <div class="ih-team-players" id="ihBluePlayers"></div>
              </div>

              <!-- 레드팀 -->
              <div class="ih-team-card ih-team-red">
                <div class="ih-team-top">
                  <div class="ih-team-title">
                    <span class="ih-team-dot ih-dot-red"></span> 🔴 레드팀
                  </div>
                  <div class="ih-team-avg" id="ihRedAvg">평균 -</div>
                </div>
                <div class="ih-team-players" id="ihRedPlayers"></div>
              </div>
            </div>
          </div>

          <!-- 5-B: Multi Mode (여러 판 동시) -->
          <div id="ihMultiResultWrap" style="display: none;"></div>

          <!-- 5-C: Tournament & League Prep (팀 구성 & 시작 버튼) -->
          <div id="ihTournamentPrepWrap" style="display: none;"></div>
        </div>

        <!-- 5.5 대회 진행 화면 -->
        <div id="ihEventViewSection" class="ih-section ih-event-section" style="display: none;"></div>

        <!-- 6. 최근 대회 -->
        <div class="ih-section ih-events-section" id="ihEventsSection" style="display: none;">
          <div class="ih-section-header">
            <div class="ih-section-title">
              <i class="fa-solid fa-sitemap"></i> 최근 대회
            </div>
            <button type="button" class="ih-btn-text" id="ihBtnRefreshEvents" title="대회 목록 새로고침">
              <i class="fa-solid fa-arrows-rotate"></i> 새로고침
            </button>
          </div>
          <div id="ihEventsListContainer" class="ih-events-list"></div>
        </div>

        <!-- 7. 내전 전적 (최근 30일) -->
        <div class="ih-section ih-stats-section">
          <div class="ih-section-header">
            <div class="ih-section-title">
              <i class="fa-solid fa-trophy" style="color: #F59E0B;"></i> 내전 순위 (최근 30일)
            </div>
            <button type="button" class="ih-btn-text" id="ihBtnRefreshStats" title="내전 전적 새로고침">
              <i class="fa-solid fa-arrows-rotate"></i> 새로고침
            </button>
          </div>
          <div id="ihStatsTableContainer">
            <div class="ih-loading-members">
              <i class="fa-solid fa-spinner fa-spin"></i> 내전 순위를 불러오는 중...
            </div>
          </div>
        </div>

        <!-- 8. 최근 내전 -->
        <div class="ih-section ih-recent-section">
          <div class="ih-section-header">
            <div class="ih-section-title">
              <i class="fa-solid fa-clock-rotate-left"></i> 최근 내전
            </div>
          </div>
          <div id="ihRecentGamesContainer">
            <div class="ih-loading-members">
              <i class="fa-solid fa-spinner fa-spin"></i> 최근 내전 기록을 불러오는 중...
            </div>
          </div>
        </div>
      </div>
    `;

    bindEvents(container);
  }

  function bindEvents(container) {
    // 1. 직접 추가 티어 변경 시 디비전 숨김/노출
    const selectTier = container.querySelector("#ihSelectTier");
    const divWrap = container.querySelector("#ihDivisionWrap");
    if (selectTier && divWrap) {
      selectTier.addEventListener("change", () => {
        const t = selectTier.value;
        const hideDivision = ["UNRANKED", "MASTER", "GRANDMASTER", "CHALLENGER"].includes(t);
        divWrap.style.display = hideDivision ? "none" : "";
      });
    }

    // 2. 직접 추가 폼 제출
    const addForm = container.querySelector("#ihAddPlayerForm");
    if (addForm) {
      addForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const inputName = container.querySelector("#ihInputName");
        const selectRank = container.querySelector("#ihSelectRank");
        if (!inputName) return;

        const name = inputName.value.trim();
        if (!name) return;

        if (selectedPlayers.length >= 80) {
          if (typeof showToast === "function") {
            showToast("내전은 최대 80명까지 선택할 수 있습니다.", "warning");
          }
          return;
        }

        const tier = selectTier ? selectTier.value : "GOLD";
        const isApexOrUnranked = ["UNRANKED", "MASTER", "GRANDMASTER", "CHALLENGER"].includes(tier);
        const rank = isApexOrUnranked ? "" : (selectRank ? selectRank.value : "IV");

        const newPlayer = {
          id: `custom_${Date.now()}_${++customCounter}`,
          name: name,
          discord_name: "",
          tier: tier,
          rank: rank,
          lp: 0,
          display_tier: formatTierKr(tier, rank, 0),
          position: null,
          isCustom: true
        };

        customMembers.push(newPlayer);
        selectedPlayers.push(newPlayer);
        inputName.value = "";

        updateUI();
      });
    }

    // 3. 멤버 칩 클릭 (이벤트 위임)
    const chipsContainer = container.querySelector("#ihMemberChipsContainer");
    if (chipsContainer) {
      chipsContainer.addEventListener("click", (e) => {
        const chip = e.target.closest(".ih-chip");
        if (!chip) return;
        const id = chip.getAttribute("data-id");
        if (!id) return;

        const all = [...serverMembers, ...customMembers];
        const found = all.find(m => m.id === id);
        if (!found) return;

        const isSel = selectedPlayers.some(p => p.id === id);
        if (isSel) {
          selectedPlayers = selectedPlayers.filter(p => p.id !== id);
        } else {
          if (selectedPlayers.length >= 80) return;
          selectedPlayers.push({ ...found, position: null });
        }
        updateUI();
      });
    }

    // 4. 참가자 명단 제어 (포지션 변경 & X 삭제)
    const partList = container.querySelector("#ihParticipantsList");
    if (partList) {
      partList.addEventListener("change", (e) => {
        if (e.target && e.target.matches(".ih-select-pos")) {
          const id = e.target.getAttribute("data-id");
          const found = selectedPlayers.find(p => p.id === id);
          if (found) {
            found.position = e.target.value || null;
          }
        }
      });

      partList.addEventListener("click", (e) => {
        const removeBtn = e.target.closest(".ih-btn-remove");
        if (removeBtn) {
          const id = removeBtn.getAttribute("data-id");
          if (id) {
            selectedPlayers = selectedPlayers.filter(p => p.id !== id);
            updateUI();
          }
        }
      });
    }

    // 5. 전체 비우기
    const clearBtn = container.querySelector("#ihBtnClearAll");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        selectedPlayers = [];
        updateUI();
      });
    }

    // 5.1 방식 선택 탭 클릭
    const modeTabs = container.querySelector("#ihModeTabs");
    if (modeTabs) {
      modeTabs.addEventListener("click", (e) => {
        const tab = e.target.closest(".ih-mode-tab");
        if (!tab || tab.disabled) return;
        const mode = tab.getAttribute("data-mode");
        if (mode && isModeValid(mode, selectedPlayers.length)) {
          selectedMode = mode;
          modePickedByUser = true;
          updateModeSelector();
          updateCountAndButton();
        }
      });
    }

    // 5.2 여러 판 하위 옵션 (split) 클릭
    const splitWrap = container.querySelector("#ihSplitSubwrap");
    if (splitWrap) {
      splitWrap.addEventListener("click", (e) => {
        const chip = e.target.closest(".ih-split-chip");
        if (!chip) return;
        const split = chip.getAttribute("data-split");
        if (split) {
          selectedSplit = split;
          updateModeSelector();
        }
      });
    }

    // 6. 멤버 새로고침
    const refreshBtn = container.querySelector("#ihBtnRefreshMembers");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        loadServerRankingMembers();
      });
    }

    // 7. 팀 나누기 버튼
    const balanceBtn = container.querySelector("#ihBtnBalance");
    if (balanceBtn) {
      balanceBtn.addEventListener("click", handleBalance);
    }

    // 8. 다른 조합 버튼
    const cycleBtn = container.querySelector("#ihBtnCycleOption");
    if (cycleBtn) {
      cycleBtn.addEventListener("click", () => {
        if (balanceOptions.length <= 1) return;
        currentOptionIdx = (currentOptionIdx + 1) % balanceOptions.length;
        renderSingleResult();
      });
    }

    // 9. 복사 버튼
    const copyBtn = container.querySelector("#ihBtnCopyResult");
    if (copyBtn) {
      copyBtn.addEventListener("click", handleCopy);
    }

    // 10. 내전 전적 새로고침 버튼
    const refreshStatsBtn = container.querySelector("#ihBtnRefreshStats");
    if (refreshStatsBtn) {
      refreshStatsBtn.addEventListener("click", () => {
        loadInhouseStats();
      });
    }

    // 11. 게임 액션 & 대회 버튼 위임
    container.addEventListener("click", (e) => {
      if (e.target.closest("#ihBtnStartGame")) {
        handleStartGame();
      } else if (e.target.closest("#ihBtnWinBlue")) {
        handleSetResult("blue");
      } else if (e.target.closest("#ihBtnWinRed")) {
        handleSetResult("red");
      } else if (e.target.closest("#ihBtnTournamentCode")) {
        handleTournamentCode();
      } else if (e.target.closest("#ihBtnSyncResult")) {
        handleSyncResult();
      } else if (e.target.closest("#ihBtnCopyCode")) {
        copyTournamentCode();
      } else if (e.target.closest(".ih-rank-tr[data-detail]")) {
        toggleRankDetail(e.target.closest(".ih-rank-tr"));
      } else if (e.target.closest("#ihBtnSaveEvent")) {
        handleSaveEvent();
      } else if (e.target.closest(".ih-multi-start-btn")) {
        handleStartMultiRoom(e.target.closest(".ih-multi-start-btn"));
      } else if (e.target.closest(".ih-multi-win-btn")) {
        handleMultiRoomResult(e.target.closest(".ih-multi-win-btn"));
      } else if (e.target.closest(".ih-event-start-btn")) {
        handleStartEventMatch(e.target.closest(".ih-event-start-btn"));
      } else if (e.target.closest(".ih-event-win-btn")) {
        handleEventMatchResult(e.target.closest(".ih-event-win-btn"));
      } else if (e.target.closest("#ihBtnCloseEvent")) {
        closeEventView();
      } else if (e.target.closest("#ihBtnRefreshEvent")) {
        refreshCurrentEvent();
      } else if (e.target.closest("#ihBtnRefreshEvents")) {
        loadRecentEvents();
      } else if (e.target.closest(".ih-recent-event-card")) {
        const card = e.target.closest(".ih-recent-event-card");
        const id = card.getAttribute("data-event-id");
        if (id) openEventView(id);
      }
    });
  }

  function isModeValid(mode, count) {
    if (count < 10) return false;
    if (mode === "single") return count === 10;
    if (mode === "multi") return count >= 20;
    if (mode === "tournament") return count >= 10;
    if (mode === "league") return count >= 15;
    return false;
  }

  function getDefaultModeForCount(count) {
    if (count === 10) return "single";
    if (count >= 20) return "multi";
    if (count >= 10) return "tournament";
    return "single";
  }

  function updateModeSelector() {
    const count = selectedPlayers.length;

    if (!modePickedByUser || !isModeValid(selectedMode, count)) {
      selectedMode = getDefaultModeForCount(count);
    }

    const tabs = document.querySelectorAll("#ihModeTabs .ih-mode-tab");
    tabs.forEach(tab => {
      const mode = tab.getAttribute("data-mode");
      const valid = isModeValid(mode, count);
      tab.disabled = !valid;
      tab.classList.toggle("active", mode === selectedMode);
    });

    const splitWrap = document.getElementById("ihSplitSubwrap");
    if (splitWrap) {
      splitWrap.style.display = selectedMode === "multi" ? "flex" : "none";
      const chips = splitWrap.querySelectorAll(".ih-split-chip");
      chips.forEach(chip => {
        chip.classList.toggle("active", chip.getAttribute("data-split") === selectedSplit);
      });
    }

    const descEl = document.getElementById("ihModeDesc");
    if (descEl) {
      if (count < 10) {
        descEl.textContent = `팀을 나누려면 최소 10명이 필요해요 (현재 ${count}명)`;
      } else if (selectedMode === "single") {
        descEl.textContent = "10명 → 5:5 1판";
      } else if (selectedMode === "multi") {
        const playing = count - (count % 10);
        const games = playing / 10;
        const wait = count % 10;
        const splitText = selectedSplit === "tiered" ? " (실력대별 방)" : " (모든 판 균형)";
        const waitText = wait > 0 ? `, ${wait}명 대기` : "";
        descEl.textContent = `${count}명 → 5:5 ${games}판${waitText}${splitText}`;
      } else if (selectedMode === "tournament") {
        const teams = Math.floor(count / 5);
        const wait = count % 5;
        const waitText = wait > 0 ? `, ${wait}명 대기` : "";
        descEl.textContent = `${count}명 → 5명씩 ${teams}팀, 대진표${waitText}`;
      } else if (selectedMode === "league") {
        const teams = Math.floor(count / 5);
        const wait = count % 5;
        const waitText = wait > 0 ? `, ${wait}명 대기` : "";
        descEl.textContent = `${count}명 → 5명씩 ${teams}팀, 풀리그 일정${waitText}`;
      }
    }
  }

  async function loadServerRankingMembers() {
    const chipsContainer = document.getElementById("ihMemberChipsContainer");
    if (chipsContainer) {
      chipsContainer.innerHTML = `
        <div class="ih-loading-members">
          <i class="fa-solid fa-spinner fa-spin"></i> 서버 멤버 목록을 불러오는 중...
        </div>
      `;
    }

    try {
      // 랭킹(인증만)이 아니라 닉네임 등록 멤버까지 고를 수 있는 목록
      const res = await fetch("/api/inhouse/members");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      fetchError = null;

      const rawMembers = Array.isArray(data.members) ? data.members : [];
      serverMembers = rawMembers.map((m, idx) => ({
        id: `sr_${idx}_${m.game_name || m.discord_name || idx}`,
        name: m.game_name || m.discord_name || "소환사",
        discord_name: m.discord_name || "",
        discord_id: m.discord_id || null,
        verified: !!m.verified,
        tier: (m.tier || "UNRANKED").toUpperCase(),
        rank: m.rank_tier || "",
        lp: m.league_points != null ? m.league_points : 0,
        display_tier: m.display_tier || formatTierKr(m.tier, m.rank_tier, m.league_points),
        position: null,
        isCustom: false
      }));
    } catch (err) {
      fetchError = "서버 멤버 목록을 불러오지 못했습니다. 직접 참가자를 추가하여 진행할 수 있습니다.";
      serverMembers = [];
    }

    updateUI();
  }

  function updateUI() {
    renderMemberChips();
    renderParticipants();
    updateModeSelector();
    updateCountAndButton();
  }

  function renderMemberChips() {
    const chipsContainer = document.getElementById("ihMemberChipsContainer");
    if (!chipsContainer) return;

    if (fetchError && serverMembers.length === 0 && customMembers.length === 0) {
      chipsContainer.innerHTML = `
        <div class="ih-error-notice">
          <i class="fa-solid fa-triangle-exclamation"></i> ${_esc(fetchError)}
        </div>
      `;
      return;
    }

    const allMembers = [...serverMembers, ...customMembers];
    if (allMembers.length === 0) {
      chipsContainer.innerHTML = `
        <div class="ih-empty-box">
          <i class="fa-solid fa-users"></i> 닉네임을 등록한 서버 멤버가 없습니다. 아래에서 직접 추가하거나, 위에서 닉네임을 등록해 주세요.
        </div>
      `;
      return;
    }

    const isFull = selectedPlayers.length >= 80;
    const chipsHtml = allMembers.map(m => {
      const isSel = selectedPlayers.some(p => p.id === m.id);
      const isDis = !isSel && isFull;
      let classes = "ih-chip";
      if (isSel) classes += " ih-selected";
      if (isDis) classes += " ih-disabled";

      return `
        <button type="button" class="${classes}" data-id="${_esc(m.id)}" ${isDis ? "disabled" : ""}>
          <span class="ih-chip-name">${_esc(m.name)}</span>
          ${m.discord_name ? `<span class="ih-chip-discord">${_esc(m.discord_name)}</span>` : ""}
          <span class="ih-chip-tier">${_esc(m.display_tier || formatTierKr(m.tier, m.rank, m.lp))}</span>
        </button>
      `;
    }).join("");

    chipsContainer.innerHTML = chipsHtml;
  }

  function renderParticipants() {
    const listEl = document.getElementById("ihParticipantsList");
    const clearBtn = document.getElementById("ihBtnClearAll");
    if (!listEl) return;

    if (clearBtn) {
      clearBtn.style.display = selectedPlayers.length > 0 ? "inline-flex" : "none";
    }

    if (selectedPlayers.length === 0) {
      listEl.innerHTML = `
        <div class="ih-empty-box">
          <i class="fa-solid fa-user-group"></i> 서버 멤버를 선택하거나 위에서 직접 친구를 추가해주세요 (0명)
        </div>
      `;
      return;
    }

    const rowsHtml = selectedPlayers.map((p, idx) => {
      const posVal = p.position || "";
      return `
        <div class="ih-participant-card">
          <div class="ih-part-num">${idx + 1}</div>
          <div class="ih-part-main">
            <strong class="ih-part-name" title="${_esc(p.name)}">${_esc(p.name)}</strong>
            ${p.discord_name ? `<span class="ih-part-discord">${_esc(p.discord_name)}</span>` : ""}
            <span class="ih-part-tier">${_esc(p.display_tier || formatTierKr(p.tier, p.rank, p.lp))}</span>
          </div>
          <div class="ih-part-actions">
            <select class="ih-select ih-select-pos" data-id="${_esc(p.id)}" aria-label="주 포지션">
              <option value="" ${posVal === "" ? "selected" : ""}>모름</option>
              <option value="TOP" ${posVal === "TOP" ? "selected" : ""}>탑</option>
              <option value="JUNGLE" ${posVal === "JUNGLE" ? "selected" : ""}>정글</option>
              <option value="MID" ${posVal === "MID" ? "selected" : ""}>미드</option>
              <option value="ADC" ${posVal === "ADC" ? "selected" : ""}>원딜</option>
              <option value="SUPPORT" ${posVal === "SUPPORT" ? "selected" : ""}>서폿</option>
            </select>
            <button type="button" class="ih-btn-remove" data-id="${_esc(p.id)}" title="제외" aria-label="제외">
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>
        </div>
      `;
    }).join("");

    listEl.innerHTML = rowsHtml;
  }

  function updateCountAndButton() {
    const count = selectedPlayers.length;
    const badge = document.getElementById("ihCountBadge");
    if (badge) {
      badge.innerHTML = `선택 <strong>${count}</strong>명`;
      badge.classList.toggle("ih-count-full", count >= 10);
    }

    const btn = document.getElementById("ihBtnBalance");
    const valid = isModeValid(selectedMode, count);
    if (btn) {
      btn.disabled = count < 10 || !valid;
      btn.innerHTML = `<i class="fa-solid fa-scale-balanced"></i> 팀 나누기 (${count}명)`;
      btn.classList.toggle("ih-ready", count >= 10 && valid);
    }
  }

  async function handleBalance() {
    const count = selectedPlayers.length;
    if (count < 10 || count > 80 || !isModeValid(selectedMode, count)) return;

    const btn = document.getElementById("ihBtnBalance");
    const errEl = document.getElementById("ihBalanceError");
    if (errEl) {
      errEl.style.display = "none";
      errEl.textContent = "";
    }
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 팀 나누는 중...';
    }

    const payload = {
      players: selectedPlayers.map(p => ({
        name: p.name,
        discord_id: p.discord_id || null,
        tier: (p.tier || "UNRANKED").toUpperCase(),
        rank: p.rank || "",
        lp: typeof p.lp === "number" ? p.lp : 0,
        main: p.position || null,
        sub: null
      })),
      mode: selectedMode,
      split: selectedSplit
    };

    try {
      const res = await fetch("/api/inhouse/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        let msg = "팀 나누기에 실패했습니다.";
        if (typeof data.detail === "string") {
          msg = data.detail;
        } else if (Array.isArray(data.detail)) {
          msg = data.detail.map(d => d.msg || JSON.stringify(d)).join(", ");
        }
        if (errEl) {
          errEl.textContent = msg;
          errEl.style.display = "block";
        }
        return;
      }

      currentPlan = data;
      renderPlanResult(data);
    } catch (err) {
      if (errEl) {
        errEl.textContent = "서버와 통신하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
        errEl.style.display = "block";
      }
    } finally {
      if (btn) {
        const canBal = selectedPlayers.length >= 10 && isModeValid(selectedMode, selectedPlayers.length);
        btn.disabled = !canBal;
        btn.innerHTML = `<i class="fa-solid fa-scale-balanced"></i> 팀 나누기 (${selectedPlayers.length}명)`;
      }
    }
  }

  function renderPlanResult(data) {
    const resSec = document.getElementById("ihResultSection");
    if (!resSec) return;

    // 대기자 배너
    const waitWrap = document.getElementById("ihWaitlistWrap");
    if (waitWrap) {
      if (Array.isArray(data.waitlist) && data.waitlist.length > 0) {
        const names = data.waitlist.map(p => _esc(p.name)).join(", ");
        waitWrap.innerHTML = `
          <div class="ih-waitlist-banner">
            <i class="fa-solid fa-user-clock"></i> 대기: <strong>${names}</strong> (다음 판에 먼저 들어가요)
          </div>
        `;
        waitWrap.style.display = "block";
      } else {
        waitWrap.innerHTML = "";
        waitWrap.style.display = "none";
      }
    }

    const singleWrap = document.getElementById("ihSingleResultWrap");
    const multiWrap = document.getElementById("ihMultiResultWrap");
    const prepWrap = document.getElementById("ihTournamentPrepWrap");

    if (data.mode === "single") {
      if (singleWrap) singleWrap.style.display = "block";
      if (multiWrap) multiWrap.style.display = "none";
      if (prepWrap) prepWrap.style.display = "none";

      balanceOptions = (data.games && data.games[0] && data.games[0].options) || [];
      currentOptionIdx = 0;
      renderSingleResult();
    } else if (data.mode === "multi") {
      if (singleWrap) singleWrap.style.display = "none";
      if (multiWrap) multiWrap.style.display = "block";
      if (prepWrap) prepWrap.style.display = "none";

      renderMultiResult(data);
    } else if (data.mode === "tournament" || data.mode === "league") {
      if (singleWrap) singleWrap.style.display = "none";
      if (multiWrap) multiWrap.style.display = "none";
      if (prepWrap) prepWrap.style.display = "block";

      renderTournamentPrep(data);
    }

    resSec.style.display = "block";
    resSec.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function renderSingleResult() {
    const singleWrap = document.getElementById("ihSingleResultWrap");
    if (!singleWrap || balanceOptions.length === 0) return;

    const opt = balanceOptions[currentOptionIdx];
    if (!opt) return;

    const diffEl = document.getElementById("ihResultDiff");
    if (diffEl) diffEl.textContent = formatNumber(opt.diff);

    const penEl = document.getElementById("ihResultPenalty");
    if (penEl) penEl.textContent = formatNumber(opt.lane_penalty || 0);

    const clashEl = document.getElementById("ihResultClash");
    const clashNumEl = document.getElementById("ihResultClashNum");
    if (clashEl && clashNumEl) {
      if (opt.position_clash > 0) {
        clashNumEl.textContent = opt.position_clash;
        clashEl.style.display = "inline-flex";
      } else {
        clashEl.style.display = "none";
      }
    }

    // 팀 요약: "블루 평균 플래 2 · 점수 차 35 · 라인 손실 0"
    const summaryEl = document.getElementById("ihResultSummaryText");
    if (summaryEl) {
      const bAvg = opt.blue ? (opt.blue.average_label || "-") : "-";
      const diffVal = opt.diff != null ? String(opt.diff) : "0";
      const penVal = opt.lane_penalty != null ? String(opt.lane_penalty) : "0";
      summaryEl.textContent = `블루 평균 ${bAvg} · 점수 차 ${diffVal} · 라인 손실 ${penVal}`;
    }

    const cycleBtn = document.getElementById("ihBtnCycleOption");
    if (cycleBtn) {
      cycleBtn.innerHTML = `<i class="fa-solid fa-shuffle"></i> 다른 조합 (${currentOptionIdx + 1}/${balanceOptions.length})`;
      cycleBtn.style.display = balanceOptions.length > 1 ? "inline-flex" : "none";
    }

    const blueAvg = document.getElementById("ihBlueAvg");
    if (blueAvg) blueAvg.textContent = `평균 ${opt.blue ? (opt.blue.average_label || "-") : "-"}`;
    const bluePlayersEl = document.getElementById("ihBluePlayers");
    if (bluePlayersEl && opt.blue) {
      bluePlayersEl.innerHTML = (opt.blue.players || []).map(p => renderPlayerItem(p)).join("");
    }

    const redAvg = document.getElementById("ihRedAvg");
    if (redAvg) redAvg.textContent = `평균 ${opt.red ? (opt.red.average_label || "-") : "-"}`;
    const redPlayersEl = document.getElementById("ihRedPlayers");
    if (redPlayersEl && opt.red) {
      redPlayersEl.innerHTML = (opt.red.players || []).map(p => renderPlayerItem(p)).join("");
    }

    renderGameActionArea();
  }

  function renderPlayerItem(p) {
    if (typeof p === "string") {
      p = { name: p };
    }
    const lane = p.lane || p.position || "";
    const posKr = lane ? (POS_NAMES_KR[lane] || lane) : "모름";
    const posIcon = lane ? (POS_ICONS[lane] || "fa-question") : "fa-question";

    // 라인 적합도 배지 (main=초록 "주", sub=노랑 "부", off=빨강 "비주", any=회색 "무관")
    let fitBadge = "";
    if (p.lane_fit) {
      const fitMap = {
        main: { label: "주", cls: "ih-fit-main", title: "주 포지션" },
        sub: { label: "부", cls: "ih-fit-sub", title: "부 포지션" },
        off: { label: "비주", cls: "ih-fit-off", title: "비주 포지션" },
        any: { label: "무관", cls: "ih-fit-any", title: "포지션 무관" }
      };
      const f = fitMap[p.lane_fit] || { label: p.lane_fit, cls: "ih-fit-any", title: "" };
      fitBadge = `<span class="ih-fit-badge ${f.cls}" title="${_esc(f.title)}">${_esc(f.label)}</span>`;
    }

    // 마우스를 올리면 rating_parts 근거 (현재 티어 / 최고 티어 보정 / 최근 20판 보정 / 내전 점수 보정, 없는 항목은 생략)
    const parts = p.rating_parts || {};
    const tooltipParts = [];
    if (parts.current != null) tooltipParts.push(`현재 티어: ${parts.current}`);
    if (parts.peak != null) tooltipParts.push(`최고 티어 보정: ${parts.peak > 0 ? "+" : ""}${parts.peak}`);
    if (parts.recent != null) tooltipParts.push(`최근 20판 보정: ${parts.recent > 0 ? "+" : ""}${parts.recent}`);
    if (parts.inhouse != null) tooltipParts.push(`내전 점수 보정: ${parts.inhouse > 0 ? "+" : ""}${parts.inhouse}`);
    const rowTooltip = tooltipParts.join(" / ");

    const ratingLabel = p.rating_label || p.display_tier || formatTierKr(p.tier, p.rank, p.lp);
    const isEst = Boolean(p.estimated);

    return `
      <div class="ih-team-player-row" ${rowTooltip ? `title="${_esc(rowTooltip)}"` : ""}>
        <div class="ih-player-left">
          <span class="ih-pos-badge" data-pos="${_esc(lane || 'NONE')}" title="${_esc(posKr)}">
            <i class="fa-solid ${posIcon}"></i> ${_esc(posKr)}
          </span>
          ${fitBadge}
          <strong class="ih-player-name" title="${_esc(p.name)}">${_esc(p.name)}</strong>
        </div>
        <div class="ih-player-right">
          <span class="ih-player-tier" ${rowTooltip ? `title="${_esc(rowTooltip)}"` : ""}>${_esc(ratingLabel)}</span>
          ${isEst ? '<span class="ih-badge-estimated" title="언랭크 계정으로 중간값으로 점수를 추정했습니다">추정</span>' : ""}
        </div>
      </div>
    `;
  }

  function formatDiscordText(opt) {
    const formatTeam = (prefix, teamData) => {
      const list = (teamData.players || []).map(p => {
        const name = typeof p === "string" ? p : (p ? p.name : "");
        const lane = typeof p === "object" && p ? (p.lane || p.position) : "";
        const pos = lane ? (POS_NAMES_KR[lane] || lane) : "";
        return pos ? `${name}(${pos})` : name;
      }).join(", ");
      return `${prefix}: ${list} (평균 ${(teamData && teamData.average_label) || ""})`;
    };

    const blue = formatTeam("🔵 블루", opt.blue);
    const red = formatTeam("🔴 레드", opt.red);
    let extra = `점수 차이 ${opt.diff || 0}LP`;
    if (opt.lane_penalty != null && opt.lane_penalty > 0) {
      extra += ` · 라인 손실 ${opt.lane_penalty}`;
    } else if (opt.position_clash > 0) {
      extra += ` · 포지션 겹침 ${opt.position_clash}명`;
    }
    return `${blue}\n${red}\n${extra}`;
  }

  function copyTextToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
    }
    return fallbackCopy(text);
  }

  function fallbackCopy(text) {
    return new Promise((resolve, reject) => {
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        ta.style.top = "-9999px";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (ok) resolve();
        else reject(new Error("Copy failed"));
      } catch (e) {
        reject(e);
      }
    });
  }

  function handleCopy() {
    let opt = balanceOptions.length > 0 ? balanceOptions[currentOptionIdx] : null;
    if (!opt && openGame) {
      opt = {
        blue: { players: openGame.blue, average_label: openGame.blue_avg },
        red: { players: openGame.red, average_label: openGame.red_avg },
        diff: openGame.diff || 0,
        lane_penalty: openGame.lane_penalty || 0,
        position_clash: openGame.position_clash || 0
      };
    }
    if (!opt) return;

    const text = formatDiscordText(opt);
    copyTextToClipboard(text).then(() => {
      const btn = document.getElementById("ihBtnCopyResult");
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-check"></i> 복사됨';
        btn.classList.add("ih-copied");
        setTimeout(() => {
          btn.innerHTML = orig;
          btn.classList.remove("ih-copied");
        }, 1500);
      }
    }).catch(() => {
      if (typeof showToast === "function") {
        showToast("클립보드 복사에 실패했습니다.", "error");
      }
    });
  }

  // ── Multi Mode (여러 판 동시) ──────────────────────────────────
  function renderMultiResult(data) {
    const multiWrap = document.getElementById("ihMultiResultWrap");
    if (!multiWrap) return;

    const games = Array.isArray(data.games) ? data.games : [];
    if (games.length === 0) {
      multiWrap.innerHTML = `<div class="ih-empty-box">나눌 수 있는 방이 없습니다.</div>`;
      return;
    }

    const roomsHtml = games.map((g, idx) => {
      const roomNum = g.room || (idx + 1);
      const opt = (g.options && g.options[0]) || null;
      if (!opt) return "";

      const roomState = multiRoomGames[roomNum] || null;

      return `
        <div class="ih-room-card" data-room="${_esc(String(roomNum))}">
          <div class="ih-room-header">
            <div class="ih-room-title">
              <i class="fa-solid fa-gamepad" style="color: var(--primary);"></i> ${_esc(String(roomNum))}번 방
            </div>
            <div class="ih-room-meta">
              <span class="ih-stat-pill">
                <i class="fa-solid fa-scale-balanced"></i> 점수 차 <strong>${_esc(String(opt.diff))}</strong>
              </span>
              <span class="ih-stat-pill">
                블루 평균 ${_esc(opt.blue?.average_label || '-')} / 레드 평균 ${_esc(opt.red?.average_label || '-')}
              </span>
            </div>
          </div>

          <div class="ih-teams-grid">
            <!-- 블루팀 -->
            <div class="ih-team-card ih-team-blue">
              <div class="ih-team-top">
                <div class="ih-team-title">
                  <span class="ih-team-dot ih-dot-blue"></span> 🔵 블루팀
                </div>
                <div class="ih-team-avg">평균 ${_esc(opt.blue?.average_label || '-')}</div>
              </div>
              <div class="ih-team-players">
                ${(opt.blue?.players || []).map(p => renderPlayerItem(p)).join("")}
              </div>
            </div>

            <!-- 레드팀 -->
            <div class="ih-team-card ih-team-red">
              <div class="ih-team-top">
                <div class="ih-team-title">
                  <span class="ih-team-dot ih-dot-red"></span> 🔴 레드팀
                </div>
                <div class="ih-team-avg">평균 ${_esc(opt.red?.average_label || '-')}</div>
              </div>
              <div class="ih-team-players">
                ${(opt.red?.players || []).map(p => renderPlayerItem(p)).join("")}
              </div>
            </div>
          </div>

          <div class="ih-room-action-bar" id="ihRoomActionBar_${_esc(String(roomNum))}">
            ${renderRoomActionContent(roomNum, opt, roomState)}
          </div>
        </div>
      `;
    }).join("");

    multiWrap.innerHTML = `<div class="ih-rooms-list">${roomsHtml}</div>`;
  }

  function renderRoomActionContent(roomNum, opt, roomState) {
    if (roomState && roomState.winner) {
      const isBlue = roomState.winner === "blue";
      return `
        <span class="ih-recorded-badge">
          <i class="fa-solid fa-check"></i> ${isBlue ? '🔵 블루 승리 기록됨' : '🔴 레드 승리 기록됨'} (#${_esc(String(roomState.game_id))})
        </span>
      `;
    }

    if (roomState && roomState.game_id) {
      return `
        <div class="ih-running-wrap">
          <span class="ih-running-badge">
            <i class="fa-solid fa-circle-dot"></i> 진행 중 #${_esc(String(roomState.game_id))}
          </span>
          <button type="button" class="ih-btn ih-btn-win ih-btn-win-blue ih-multi-win-btn" data-room="${_esc(String(roomNum))}" data-winner="blue">
            🔵 블루 승리
          </button>
          <button type="button" class="ih-btn ih-btn-win ih-btn-win-red ih-multi-win-btn" data-room="${_esc(String(roomNum))}" data-winner="red">
            🔴 레드 승리
          </button>
        </div>
      `;
    }

    return `
      <button type="button" class="ih-btn ih-btn-primary ih-multi-start-btn" data-room="${_esc(String(roomNum))}">
        <i class="fa-solid fa-play"></i> 이 방 시작
      </button>
    `;
  }

  async function handleStartMultiRoom(btn) {
    const roomNum = btn.getAttribute("data-room");
    if (!roomNum || !currentPlan || !Array.isArray(currentPlan.games)) return;

    const game = currentPlan.games.find((g, idx) => String(g.room || (idx + 1)) === String(roomNum));
    if (!game || !game.options || !game.options[0]) return;
    const opt = game.options[0];

    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 저장 중...';

    const payload = {
      blue: opt.blue.players.map(p => ({ name: String(p.name || "").trim().slice(0, 40) })),
      red: opt.red.players.map(p => ({ name: String(p.name || "").trim().slice(0, 40) }))
    };

    try {
      const res = await fetch("/api/inhouse/games", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        let msg = "방 게임을 시작하지 못했습니다.";
        if (res.status === 429) {
          msg = "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.";
        } else if (data.detail && typeof data.detail === "string") {
          msg = data.detail;
        }
        if (typeof showToast === "function") showToast(msg, "error");
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-play"></i> 이 방 시작';
        return;
      }

      multiRoomGames[roomNum] = { game_id: data.id, winner: null };
      const actionBar = document.getElementById(`ihRoomActionBar_${roomNum}`);
      if (actionBar) {
        actionBar.innerHTML = renderRoomActionContent(roomNum, opt, multiRoomGames[roomNum]);
      }
    } catch (err) {
      if (typeof showToast === "function") showToast("서버와 통신하는 중 오류가 발생했습니다.", "error");
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-play"></i> 이 방 시작';
    }
  }

  async function handleMultiRoomResult(btn) {
    const roomNum = btn.getAttribute("data-room");
    const winner = btn.getAttribute("data-winner");
    if (!roomNum || !winner || !multiRoomGames[roomNum]) return;
    const gameId = multiRoomGames[roomNum].game_id;
    if (!gameId) return;

    btn.disabled = true;

    try {
      const res = await fetch(`/api/inhouse/games/${gameId}/result`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ winner: winner })
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        let msg = "결과 기록에 실패했습니다.";
        if (data.detail && typeof data.detail === "string") {
          msg = data.detail;
        }
        if (typeof showToast === "function") showToast(msg, "error");
        btn.disabled = false;
        return;
      }

      multiRoomGames[roomNum].winner = winner;

      const game = currentPlan && Array.isArray(currentPlan.games)
        ? currentPlan.games.find((g, idx) => String(g.room || (idx + 1)) === String(roomNum))
        : null;
      const opt = game && game.options ? game.options[0] : null;

      const actionBar = document.getElementById(`ihRoomActionBar_${roomNum}`);
      if (actionBar) {
        actionBar.innerHTML = renderRoomActionContent(roomNum, opt, multiRoomGames[roomNum]);
      }

      await loadInhouseStats();
    } catch (err) {
      if (typeof showToast === "function") showToast("서버와 통신하는 중 오류가 발생했습니다.", "error");
      btn.disabled = false;
    }
  }

  // ── Tournament / League Prep ──────────────────────────────────
  function renderTournamentPrep(data) {
    const prepWrap = document.getElementById("ihTournamentPrepWrap");
    if (!prepWrap) return;

    const modeKr = data.mode === "tournament" ? "토너먼트" : "리그";
    const teams = Array.isArray(data.teams) ? data.teams : [];
    const spreadStr = data.team_spread != null ? String(data.team_spread) : "0";

    const teamsHtml = teams.map((t, idx) => `
      <div class="ih-tourney-team-card">
        <div class="ih-team-top">
          <div class="ih-team-title">
            <span class="ih-team-dot ih-dot-blue"></span> ${_esc(t.name || `${idx + 1}팀`)}
          </div>
          <div class="ih-team-avg">평균 ${_esc(t.average_label || '-')}</div>
        </div>
        <div class="ih-team-players">
          ${(t.players || []).map(p => renderPlayerItem(p)).join("")}
        </div>
      </div>
    `).join("");

    prepWrap.innerHTML = `
      <div class="ih-tourney-prep-box">
        <div class="ih-tourney-header">
          <div class="ih-section-title">
            <i class="fa-solid ${data.mode === 'tournament' ? 'fa-sitemap' : 'fa-trophy'}"></i> ${modeKr} 팀 구성 (${teams.length}팀)
          </div>
          <div class="ih-tourney-meta">
            <span class="ih-stat-pill">
              <i class="fa-solid fa-arrows-split-up-and-left"></i> 팀 점수 편차 <strong>${_esc(spreadStr)}</strong>
            </span>
          </div>
        </div>
        <div class="ih-tourney-teams-grid">
          ${teamsHtml}
        </div>
        <div class="ih-tourney-action-bar">
          <button type="button" id="ihBtnSaveEvent" class="ih-btn ih-btn-primary ih-btn-lg">
            <i class="fa-solid fa-floppy-disk"></i> 대회 저장하고 시작
          </button>
        </div>
      </div>
    `;
  }

  async function handleSaveEvent() {
    if (!currentPlan || !currentPlan.teams || !currentPlan.matches) return;
    const btn = document.getElementById("ihBtnSaveEvent");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 저장 중...';
    }

    const modeKr = currentPlan.mode === "tournament" ? "토너먼트" : "리그";
    const now = new Date();
    const dateStr = `${now.getMonth() + 1}/${now.getDate()}`;
    const title = `내전 ${modeKr} (${dateStr})`;

    const payload = {
      mode: currentPlan.mode,
      title: title,
      teams: currentPlan.teams.map((t, idx) => ({
        name: String(t.name || `${idx + 1}팀`).slice(0, 20),
        players: (t.players || []).map(p => ({
          name: String(p.name || "").trim().slice(0, 40),
          lane: String(p.lane || "").slice(0, 8)
        }))
      })),
      matches: currentPlan.matches.map(m => ({
        round: Number(m.round) || 1,
        a: m.a != null ? Number(m.a) : null,
        b: m.b != null ? Number(m.b) : null
      }))
    };

    try {
      const res = await fetch("/api/inhouse/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        let msg = "대회 저장에 실패했습니다.";
        if (typeof data.detail === "string") {
          msg = data.detail;
        } else if (Array.isArray(data.detail)) {
          msg = data.detail.map(d => d.msg || JSON.stringify(d)).join(", ");
        }
        if (typeof showToast === "function") showToast(msg, "error");
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> 대회 저장하고 시작';
        }
        return;
      }

      loadRecentEvents();
      openEventView(data.id);
    } catch (err) {
      if (typeof showToast === "function") showToast("서버와 통신하는 중 오류가 발생했습니다.", "error");
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> 대회 저장하고 시작';
      }
    }
  }

  // ── Event View (대회 화면) ─────────────────────────────────────
  async function openEventView(eventId) {
    currentEventId = eventId;
    const section = document.getElementById("ihEventViewSection");
    if (!section) return;

    section.style.display = "block";
    section.innerHTML = `
      <div class="ih-loading-members">
        <i class="fa-solid fa-spinner fa-spin"></i> 대회를 불러오는 중...
      </div>
    `;
    section.scrollIntoView({ behavior: "smooth", block: "start" });

    try {
      const res = await fetch(`/api/inhouse/events/${eventId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const ev = await res.json();
      renderEventView(ev);
    } catch (err) {
      section.innerHTML = `
        <div class="ih-error-notice">
          <i class="fa-solid fa-triangle-exclamation"></i> 대회를 불러오지 못했습니다.
          <button type="button" class="ih-btn-text" id="ihBtnCloseEvent"><i class="fa-solid fa-xmark"></i> 닫기</button>
        </div>
      `;
    }
  }

  function renderEventView(ev) {
    const section = document.getElementById("ihEventViewSection");
    if (!section || !ev) return;

    const modeKr = ev.mode === "tournament" ? "토너먼트" : "리그";
    const icon = ev.mode === "tournament" ? "fa-sitemap" : "fa-trophy";
    const teams = Array.isArray(ev.teams) ? ev.teams : [];
    const matches = Array.isArray(ev.matches) ? ev.matches : [];

    // 우승 팀 배너
    let champHtml = "";
    if (ev.champion != null && teams[ev.champion]) {
      champHtml = `
        <div class="ih-champion-banner">
          <i class="fa-solid fa-trophy"></i> 🏆 우승: <strong>${_esc(teams[ev.champion].name)}</strong>
        </div>
      `;
    }

    // 리그 순위표
    let standingsHtml = "";
    if (ev.mode === "league" && Array.isArray(ev.standings) && ev.standings.length > 0) {
      const rows = ev.standings.map((s, idx) => {
        const total = (s.wins || 0) + (s.losses || 0);
        const rate = total > 0 ? ((s.wins / total) * 100).toFixed(1) + "%" : "-";
        let rankCls = "ih-rank-num";
        if (idx === 0) rankCls += " ih-rank-gold";
        else if (idx === 1) rankCls += " ih-rank-silver";
        else if (idx === 2) rankCls += " ih-rank-bronze";
        return `
          <tr class="ih-stat-tr">
            <td class="ih-td-rank"><span class="${rankCls}">${idx + 1}</span></td>
            <td class="ih-td-name"><strong>${_esc(s.name)}</strong></td>
            <td class="ih-td-wins">${_esc(String(s.wins))}</td>
            <td class="ih-td-losses">${_esc(String(s.losses))}</td>
            <td class="ih-td-rate">${_esc(rate)}</td>
          </tr>
        `;
      }).join("");

      standingsHtml = `
        <div class="ih-league-standings-box">
          <div class="ih-section-title"><i class="fa-solid fa-list-ol"></i> 리그 순위표</div>
          <div class="ih-table-wrap">
            <table class="ih-stats-table">
              <thead>
                <tr>
                  <th class="ih-th-rank">순위</th>
                  <th class="ih-th-name">팀</th>
                  <th class="ih-th-wins">승</th>
                  <th class="ih-th-losses">패</th>
                  <th class="ih-th-rate">승률</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>
      `;
    }

    // 라운드별 경기 목록
    const distinctRounds = [...new Set(matches.map(m => m.round || 1))].sort((a, b) => a - b);
    const maxRound = distinctRounds.length > 0 ? distinctRounds[distinctRounds.length - 1] : 1;

    const roundsHtml = distinctRounds.map(r => {
      const roundMatches = matches
        .map((m, idx) => ({ ...m, origIdx: idx }))
        .filter(m => (m.round || 1) === r);

      const isFinal = ev.mode === "tournament" && r === maxRound && roundMatches.length === 1 && maxRound > 1;
      const roundTitle = isFinal ? "결승" : `${r}라운드`;

      const matchItemsHtml = roundMatches.map(m => {
        const teamA_name = m.a != null && teams[m.a] ? teams[m.a].name : "-";
        const teamB_name = m.b != null && teams[m.b] ? teams[m.b].name : "-";

        let statusHtml = "";
        if (m.a == null || m.b == null) {
          const winnerTeam = m.winner != null && teams[m.winner] ? teams[m.winner].name : "";
          statusHtml = `<span class="ih-match-badge ih-match-bye">부전승${winnerTeam ? ` (${_esc(winnerTeam)} 진출)` : ''}</span>`;
        } else if (m.winner != null) {
          const winnerTeam = teams[m.winner] ? teams[m.winner].name : "";
          statusHtml = `<span class="ih-match-badge ih-match-winner">🏆 ${_esc(winnerTeam)} 승리</span>`;
        } else if (m.game_id != null) {
          statusHtml = `
            <div class="ih-match-actions">
              <span class="ih-running-badge"><i class="fa-solid fa-circle-dot"></i> 진행 중 #${_esc(String(m.game_id))}</span>
              <button type="button" class="ih-btn ih-btn-sm ih-btn-win ih-btn-win-blue ih-event-win-btn" data-event-id="${_esc(String(ev.id))}" data-game-id="${_esc(String(m.game_id))}" data-winner="blue">
                ${_esc(teamA_name)} 승
              </button>
              <button type="button" class="ih-btn ih-btn-sm ih-btn-win ih-btn-win-red ih-event-win-btn" data-event-id="${_esc(String(ev.id))}" data-game-id="${_esc(String(m.game_id))}" data-winner="red">
                ${_esc(teamB_name)} 승
              </button>
            </div>
          `;
        } else {
          statusHtml = `
            <button type="button" class="ih-btn ih-btn-sm ih-btn-primary ih-event-start-btn" data-event-id="${_esc(String(ev.id))}" data-match-idx="${_esc(String(m.origIdx))}">
              <i class="fa-solid fa-play"></i> 경기 시작
            </button>
          `;
        }

        return `
          <div class="ih-match-row">
            <div class="ih-match-teams">
              <span class="ih-match-team-a">${_esc(teamA_name)}</span>
              <span class="ih-match-vs">VS</span>
              <span class="ih-match-team-b">${_esc(teamB_name)}</span>
            </div>
            <div class="ih-match-status-area">
              ${statusHtml}
            </div>
          </div>
        `;
      }).join("");

      return `
        <div class="ih-round-section">
          <div class="ih-round-title">
            <i class="fa-solid fa-calendar-day"></i> ${_esc(roundTitle)}
          </div>
          <div class="ih-match-list">
            ${matchItemsHtml}
          </div>
        </div>
      `;
    }).join("");

    section.innerHTML = `
      <div class="ih-event-view">
        <div class="ih-event-view-header">
          <div class="ih-header-left">
            <h3 class="ih-event-title">
              <i class="fa-solid ${icon}" style="color: var(--primary);"></i> ${_esc(ev.title || `${modeKr} #${ev.id}`)}
            </h3>
          </div>
          <div class="ih-header-right">
            <button type="button" class="ih-btn-text" id="ihBtnRefreshEvent" data-id="${_esc(String(ev.id))}">
              <i class="fa-solid fa-arrows-rotate"></i> 새로고침
            </button>
            <button type="button" class="ih-btn-text" id="ihBtnCloseEvent">
              <i class="fa-solid fa-xmark"></i> 닫기
            </button>
          </div>
        </div>

        ${champHtml}
        ${standingsHtml}

        <div class="ih-rounds-container">
          <div class="ih-section-title">
            <i class="fa-solid fa-gamepad"></i> 경기 일정 및 결과
          </div>
          ${roundsHtml}
        </div>
      </div>
    `;
  }

  function closeEventView() {
    currentEventId = null;
    const section = document.getElementById("ihEventViewSection");
    if (section) section.style.display = "none";
  }

  function refreshCurrentEvent() {
    if (currentEventId) {
      openEventView(currentEventId);
    }
  }

  async function handleStartEventMatch(btn) {
    const eventId = btn.getAttribute("data-event-id");
    const matchIdx = btn.getAttribute("data-match-idx");
    if (!eventId || matchIdx == null) return;

    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 시작 중...';

    try {
      const res = await fetch(`/api/inhouse/events/${eventId}/matches/${matchIdx}/start`, {
        method: "POST"
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        if (res.status === 403) {
          if (typeof showToast === "function") {
            showToast("대회를 만든 사람만 시작할 수 있어요", "warning");
          } else {
            alert("대회를 만든 사람만 시작할 수 있어요");
          }
        } else {
          const msg = data.detail || "경기를 시작하지 못했습니다.";
          if (typeof showToast === "function") {
            showToast(typeof msg === "string" ? msg : JSON.stringify(msg), "error");
          }
        }
        openEventView(eventId);
        return;
      }

      openEventView(eventId);
    } catch (err) {
      if (typeof showToast === "function") {
        showToast("서버와 통신하는 중 오류가 발생했습니다.", "error");
      }
      openEventView(eventId);
    }
  }

  async function handleEventMatchResult(btn) {
    const eventId = btn.getAttribute("data-event-id");
    const gameId = btn.getAttribute("data-game-id");
    const winner = btn.getAttribute("data-winner");
    if (!eventId || !gameId || !winner) return;

    btn.disabled = true;

    try {
      const res = await fetch(`/api/inhouse/games/${gameId}/result`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ winner: winner })
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const msg = data.detail || "결과를 기록하지 못했습니다.";
        if (typeof showToast === "function") {
          showToast(typeof msg === "string" ? msg : JSON.stringify(msg), "error");
        }
        openEventView(eventId);
        return;
      }

      await loadInhouseStats();
      await openEventView(eventId);
    } catch (err) {
      if (typeof showToast === "function") {
        showToast("서버와 통신하는 중 오류가 발생했습니다.", "error");
      }
      openEventView(eventId);
    }
  }

  // ── 최근 대회 목록 ───────────────────────────────────────────
  async function loadRecentEvents() {
    const section = document.getElementById("ihEventsSection");
    const container = document.getElementById("ihEventsListContainer");
    if (!section || !container) return;

    try {
      const res = await fetch("/api/inhouse/events");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const events = Array.isArray(data.events) ? data.events : [];

      if (events.length === 0) {
        section.style.display = "none";
        return;
      }

      section.style.display = "block";
      container.innerHTML = events.map(ev => {
        const modeKr = ev.mode === "tournament" ? "토너먼트" : "리그";
        const icon = ev.mode === "tournament" ? "fa-sitemap" : "fa-trophy";
        return `
          <div class="ih-recent-event-card" data-event-id="${_esc(String(ev.id))}">
            <div class="ih-recent-event-left">
              <span class="ih-event-mode-badge ih-event-mode-${_esc(ev.mode)}">
                <i class="fa-solid ${icon}"></i> ${_esc(modeKr)}
              </span>
              <strong class="ih-recent-event-title">${_esc(ev.title || `${modeKr} #${ev.id}`)}</strong>
              <span class="ih-recent-event-teams">${_esc(String(ev.teams))}팀 참가</span>
            </div>
            <div class="ih-recent-event-right">
              <span class="ih-recent-event-date"><i class="fa-regular fa-clock"></i> ${formatInhouseDate(ev.created_at)}</span>
              <i class="fa-solid fa-chevron-right ih-event-arrow"></i>
            </div>
          </div>
        `;
      }).join("");
    } catch (e) {
      section.style.display = "none";
    }
  }

  // Ongoing Game & Record Handlers
  function restoreOpenGameIfAny() {
    try {
      const raw = localStorage.getItem("inhouse_open_game");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && parsed.id && Array.isArray(parsed.blue) && Array.isArray(parsed.red)) {
          openGame = parsed;
        }
      }
    } catch (e) {
      console.warn("restoreOpenGame failed:", e);
      openGame = null;
    }

    if (openGame) {
      renderOpenGameView();
    }
  }

  function renderOpenGameView() {
    if (!openGame) return;
    const resSec = document.getElementById("ihResultSection");
    if (!resSec) return;

    resSec.style.display = "block";

    const singleWrap = document.getElementById("ihSingleResultWrap");
    const multiWrap = document.getElementById("ihMultiResultWrap");
    const prepWrap = document.getElementById("ihTournamentPrepWrap");
    if (singleWrap) singleWrap.style.display = "block";
    if (multiWrap) multiWrap.style.display = "none";
    if (prepWrap) prepWrap.style.display = "none";

    const diffEl = document.getElementById("ihResultDiff");
    if (diffEl) diffEl.textContent = formatNumber(openGame.diff || 0);

    const penEl = document.getElementById("ihResultPenalty");
    if (penEl) penEl.textContent = formatNumber(openGame.lane_penalty || 0);

    const summaryEl = document.getElementById("ihResultSummaryText");
    if (summaryEl) {
      summaryEl.textContent = `블루 평균 ${openGame.blue_avg || "-"} · 점수 차 ${openGame.diff || 0} · 라인 손실 ${openGame.lane_penalty || 0}`;
    }

    const clashEl = document.getElementById("ihResultClash");
    const clashNumEl = document.getElementById("ihResultClashNum");
    if (clashEl && clashNumEl) {
      if (openGame.position_clash > 0) {
        clashNumEl.textContent = openGame.position_clash;
        clashEl.style.display = "inline-flex";
      } else {
        clashEl.style.display = "none";
      }
    }

    const cycleBtn = document.getElementById("ihBtnCycleOption");
    if (cycleBtn) cycleBtn.style.display = "none";

    const blueAvg = document.getElementById("ihBlueAvg");
    if (blueAvg) blueAvg.textContent = `평균 ${openGame.blue_avg || "-"}`;
    const bluePlayersEl = document.getElementById("ihBluePlayers");
    if (bluePlayersEl) {
      bluePlayersEl.innerHTML = openGame.blue.map(p => renderPlayerItem(p)).join("");
    }

    const redAvg = document.getElementById("ihRedAvg");
    if (redAvg) redAvg.textContent = `평균 ${openGame.red_avg || "-"}`;
    const redPlayersEl = document.getElementById("ihRedPlayers");
    if (redPlayersEl) {
      redPlayersEl.innerHTML = openGame.red.map(p => renderPlayerItem(p)).join("");
    }

    renderGameActionArea();
  }

  function renderGameActionArea() {
    const wrap = document.getElementById("ihGameActionWrap");
    if (!wrap) return;
    // 진행 중이면 코드 안내까지 한 줄 전체를 쓴다
    wrap.classList.toggle("ih-running", Boolean(openGame && openGame.id));

    if (openGame && openGame.id) {
      wrap.innerHTML = `
        <div class="ih-running-wrap">
          <span class="ih-running-badge" title="진행 중인 내전 ID">
            <i class="fa-solid fa-circle-dot"></i> 진행 중 #${_esc(openGame.id)}
          </span>
          <button type="button" id="ihBtnWinBlue" class="ih-btn ih-btn-win ih-btn-win-blue">
            🔵 블루 승리
          </button>
          <button type="button" id="ihBtnWinRed" class="ih-btn ih-btn-win ih-btn-win-red">
            🔴 레드 승리
          </button>
        </div>
        <div class="ih-code-wrap" id="ihCodeWrap">
          ${openGame.code ? `
            <div class="ih-code-box">
              <span class="ih-code-label"><i class="fa-solid fa-ticket"></i> 토너먼트 코드</span>
              <code class="ih-code-value">${_esc(openGame.code)}</code>
              <button type="button" id="ihBtnCopyCode" class="ih-btn-text"><i class="fa-regular fa-copy"></i> 복사</button>
              <button type="button" id="ihBtnSyncResult" class="ih-btn-text"><i class="fa-solid fa-cloud-arrow-down"></i> 결과 불러오기</button>
            </div>
            <div class="ih-code-help">롤 클라이언트 → 플레이 → 사설 게임 오른쪽 위 트로피(토너먼트 코드)에 붙여 넣고 방을 만드세요. 게임이 끝나면 결과와 KDA·챔피언이 자동으로 기록됩니다.</div>
          ` : `
            <button type="button" id="ihBtnTournamentCode" class="ih-btn ih-btn-secondary">
              <i class="fa-solid fa-ticket"></i> 라이엇 토너먼트 코드 받기
            </button>
            <div class="ih-code-help">코드로 방을 만들면 승패와 챔피언·KDA가 자동 기록됩니다. 코드 없이 하면 끝나고 이긴 팀을 눌러 주세요.</div>
          `}
        </div>
      `;
    } else if (balanceOptions.length > 0) {
      wrap.innerHTML = `
        <button type="button" id="ihBtnStartGame" class="ih-btn ih-btn-primary">
          <i class="fa-solid fa-play"></i> 이 팀으로 시작
        </button>
      `;
    } else {
      wrap.innerHTML = "";
    }
  }

  async function handleStartGame() {
    if (isSavingGame) return;
    if (balanceOptions.length === 0) return;
    const opt = balanceOptions[currentOptionIdx];
    if (!opt || !opt.blue || !opt.red) return;

    const noticeEl = document.getElementById("ihGameNotice");
    if (noticeEl) {
      noticeEl.style.display = "none";
      noticeEl.textContent = "";
    }

    const btn = document.getElementById("ihBtnStartGame");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 저장 중...';
    }
    isSavingGame = true;

    const payload = {
      blue: opt.blue.players.map(p => ({ name: String(p.name || "").trim().slice(0, 40) })),
      red: opt.red.players.map(p => ({ name: String(p.name || "").trim().slice(0, 40) }))
    };

    try {
      const res = await fetch("/api/inhouse/games", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        let msg = "팀 저장에 실패했습니다.";
        if (res.status === 429) {
          msg = "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.";
        } else if (data.detail && typeof data.detail === "string") {
          msg = data.detail;
        }
        if (noticeEl) {
          noticeEl.textContent = msg;
          noticeEl.style.display = "block";
        }
        return;
      }

      openGame = {
        id: data.id,
        blue: opt.blue.players.map(p => ({
          name: p.name,
          tier: p.tier,
          rank: p.rank,
          lp: p.lp,
          position: p.position,
          display_tier: p.display_tier,
          discord_name: p.discord_name
        })),
        red: opt.red.players.map(p => ({
          name: p.name,
          tier: p.tier,
          rank: p.rank,
          lp: p.lp,
          position: p.position,
          display_tier: p.display_tier,
          discord_name: p.discord_name
        })),
        diff: opt.diff,
        position_clash: opt.position_clash,
        blue_avg: opt.blue.average_label,
        red_avg: opt.red.average_label
      };

      try {
        localStorage.setItem("inhouse_open_game", JSON.stringify(openGame));
      } catch (e) {
        console.warn("localStorage setItem inhouse_open_game failed:", e);
      }

      renderGameActionArea();
    } catch (err) {
      if (noticeEl) {
        noticeEl.textContent = "서버와 통신하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
        noticeEl.style.display = "block";
      }
    } finally {
      isSavingGame = false;
      if (btn && (!openGame || !openGame.id)) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-play"></i> 이 팀으로 시작';
      }
    }
  }

  async function handleSetResult(winner) {
    if (isSubmittingResult) return;
    if (!openGame || !openGame.id) return;
    if (winner !== "blue" && winner !== "red") return;

    const noticeEl = document.getElementById("ihGameNotice");
    if (noticeEl) {
      noticeEl.style.display = "none";
      noticeEl.textContent = "";
    }

    const btnBlue = document.getElementById("ihBtnWinBlue");
    const btnRed = document.getElementById("ihBtnWinRed");
    if (btnBlue) btnBlue.disabled = true;
    if (btnRed) btnRed.disabled = true;
    isSubmittingResult = true;

    try {
      const res = await fetch(`/api/inhouse/games/${openGame.id}/result`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ winner: winner })
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        let msg = "결과 기록에 실패했습니다.";
        if (res.status === 403) {
          msg = "팀을 저장한 사람만 결과를 정할 수 있습니다.";
        } else if (res.status === 404) {
          msg = "내전 기록을 찾을 수 없습니다.";
        } else if (res.status === 409) {
          msg = "하루가 지난 기록은 바꿀 수 없습니다.";
        } else if (res.status === 429) {
          msg = "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.";
        } else if (data.detail && typeof data.detail === "string") {
          msg = data.detail;
        }
        if (noticeEl) {
          noticeEl.textContent = msg;
          noticeEl.style.display = "block";
        }
        if (btnBlue) btnBlue.disabled = false;
        if (btnRed) btnRed.disabled = false;
        return;
      }

      const actionWrap = document.getElementById("ihGameActionWrap");
      if (actionWrap) {
        actionWrap.innerHTML = `
          <span class="ih-recorded-badge">
            <i class="fa-solid fa-check"></i> 기록됨
          </span>
        `;
      }

      try {
        localStorage.removeItem("inhouse_open_game");
      } catch (e) {
        console.warn("localStorage removeItem failed:", e);
      }

      openGame = null;

      // 전적 새로고침
      await loadInhouseStats();

      setTimeout(() => {
        renderGameActionArea();
      }, 2000);
    } catch (err) {
      if (noticeEl) {
        noticeEl.textContent = "서버와 통신하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
        noticeEl.style.display = "block";
      }
      if (btnBlue) btnBlue.disabled = false;
      if (btnRed) btnRed.disabled = false;
    } finally {
      isSubmittingResult = false;
    }
  }

  // 라이엇 토너먼트 코드 (사설 게임 결과 자동 기록)
  function saveOpenGame() {
    try {
      localStorage.setItem("inhouse_open_game", JSON.stringify(openGame));
    } catch (e) {
      console.warn("localStorage setItem inhouse_open_game failed:", e);
    }
  }

  function showGameNotice(msg) {
    const noticeEl = document.getElementById("ihGameNotice");
    if (noticeEl) {
      noticeEl.textContent = msg;
      noticeEl.style.display = msg ? "block" : "none";
    }
  }

  async function handleTournamentCode() {
    if (!openGame || !openGame.id) return;
    const btn = document.getElementById("ihBtnTournamentCode");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 발급 중...';
    }
    showGameNotice("");
    try {
      const res = await fetch(`/api/inhouse/games/${openGame.id}/code`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showGameNotice(typeof data.detail === "string" ? data.detail : "코드를 받지 못했습니다.");
        renderGameActionArea();
        return;
      }
      openGame.code = data.code;
      openGame.code_mode = data.mode;
      saveOpenGame();
      renderGameActionArea();
      if (data.mode === "stub") showGameNotice("시험용 코드입니다 (라이엇 승인 전): 실제 게임에서는 쓸 수 없습니다.");
    } catch (err) {
      showGameNotice("서버와 통신하는 중 오류가 발생했습니다.");
      renderGameActionArea();
    }
  }

  async function copyTournamentCode() {
    if (!openGame || !openGame.code) return;
    try {
      await navigator.clipboard.writeText(openGame.code);
      if (typeof showToast === "function") showToast("토너먼트 코드를 복사했습니다.", "success");
    } catch (e) {
      showGameNotice(`복사하지 못했습니다. 직접 선택해 복사하세요: ${openGame.code}`);
    }
  }

  async function handleSyncResult() {
    if (!openGame || !openGame.id) return;
    showGameNotice("");
    try {
      const res = await fetch(`/api/inhouse/games/${openGame.id}/sync`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showGameNotice(typeof data.detail === "string" ? data.detail : "결과를 불러오지 못했습니다.");
        return;
      }
      if (data.status === "ok" || data.status === "already") {
        try { localStorage.removeItem("inhouse_open_game"); } catch (e) {}
        openGame = null;
        renderGameActionArea();
        if (typeof showToast === "function") showToast("라이엇 경기 기록으로 결과를 저장했습니다.", "success");
        await loadInhouseStats();
      } else {
        showGameNotice("아직 끝난 게임이 없습니다. 게임이 끝나고 잠시 뒤 다시 눌러 주세요.");
      }
    } catch (err) {
      showGameNotice("서버와 통신하는 중 오류가 발생했습니다.");
    }
  }

  // Stats & Recent Matches Handlers
  async function loadInhouseStats() {
    const statsTableContainer = document.getElementById("ihStatsTableContainer");
    const recentGamesContainer = document.getElementById("ihRecentGamesContainer");

    try {
      const [rankRes, statsRes] = await Promise.all([
        fetch("/api/inhouse/ranking?days=30"),
        fetch("/api/inhouse/stats?days=30")
      ]);
      if (!rankRes.ok || !statsRes.ok) throw new Error(`HTTP ${rankRes.status}/${statsRes.status}`);
      const ranking = await rankRes.json();
      const data = await statsRes.json();

      renderRankingTable(ranking.players || [], ranking.placement_games || 3);
      renderRecentGames(data.recent || []);
    } catch (err) {
      if (statsTableContainer) {
        statsTableContainer.innerHTML = `
          <div class="ih-error-notice">
            <i class="fa-solid fa-triangle-exclamation"></i> 내전 순위를 불러오지 못했습니다.
          </div>
        `;
      }
      if (recentGamesContainer) {
        recentGamesContainer.innerHTML = `
          <div class="ih-error-notice">
            <i class="fa-solid fa-triangle-exclamation"></i> 최근 내전 기록을 불러오지 못했습니다.
          </div>
        `;
      }
    }
  }

  const CHAMP_IMG = "https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/";

  // 내전 순위: 챔피언 순위처럼 가로 한 줄. 평균 골드·타워 같은 세부 기록은 줄을 눌렀을 때만
  function renderRankingTable(players, placementGames) {
    const container = document.getElementById("ihStatsTableContainer");
    if (!container) return;

    if (!players || players.length === 0) {
      container.innerHTML = `
        <div class="ih-empty-box">
          <i class="fa-solid fa-circle-info"></i> 아직 기록된 내전이 없습니다.
        </div>
      `;
      return;
    }

    const rowsHtml = players.map(p => {
      const rank = p.rank;
      let rankClass = "ih-rank-num";
      if (!p.placement && rank === 1) rankClass += " ih-rank-gold";
      else if (!p.placement && rank === 2) rankClass += " ih-rank-silver";
      else if (!p.placement && rank === 3) rankClass += " ih-rank-bronze";
      const winRate = typeof p.win_rate === "number" ? p.win_rate : 0;
      const rateClass = winRate >= 50 ? "ih-rate-good" : "ih-rate-bad";
      const most = (p.most_champions || []).map(c => `
        <img class="ih-most-champ" src="${CHAMP_IMG}${_esc(c.champion)}.png" alt="${_esc(c.champion)}" title="${_esc(c.champion)} ${_esc(String(c.games))}판" loading="lazy" onerror="this.style.display='none'">
      `).join("");
      return `
        <tr class="ih-stat-tr ih-rank-tr" ${p.has_detail ? `data-detail="${_esc(p.key)}" title="눌러서 세부 기록 보기"` : ""}>
          <td class="ih-td-rank"><span class="${rankClass}">${p.placement ? "-" : _esc(String(rank))}</span></td>
          <td class="ih-td-name" title="${_esc(p.name)}">
            <span class="ih-name-truncate">${_esc(p.name)}</span>
            ${p.placement ? '<span class="ih-placement-badge" title="' + _esc(String(placementGames)) + '판 미만">배치</span>' : ""}
            ${p.has_detail ? '<i class="fa-solid fa-chevron-down ih-detail-caret"></i>' : ""}
          </td>
          <td class="ih-td-rating">${_esc(String(p.rating))}</td>
          <td class="ih-td-games">${_esc(String(p.games))}</td>
          <td class="ih-td-rate"><span class="${rateClass}">${winRate.toFixed(1)}%</span> <span class="ih-wl">${_esc(String(p.wins))}승 ${_esc(String(p.losses))}패</span></td>
          <td class="ih-td-kda">${p.kda != null ? _esc(p.kda.toFixed(2)) : "-"}</td>
          <td class="ih-td-most">${most || '<span class="ih-muted">-</span>'}</td>
        </tr>
      `;
    }).join("");

    container.innerHTML = `
      <div class="ih-table-wrap">
        <table class="ih-stats-table ih-rank-table">
          <thead>
            <tr>
              <th class="ih-th-rank">순위</th>
              <th class="ih-th-name">플레이어</th>
              <th class="ih-th-rating" title="내전 승패로 오르내리는 점수 (시작 1000, 상대 팀 평균 점수 반영)">내전 점수</th>
              <th class="ih-th-games">판수</th>
              <th class="ih-th-rate">승률</th>
              <th class="ih-th-kda" title="토너먼트 코드로 한 게임만 집계">KDA</th>
              <th class="ih-th-most">모스트</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
      <div class="ih-rank-foot">${_esc(String(placementGames))}판 미만은 배치 중으로 아래에 표시됩니다. KDA·모스트는 토너먼트 코드로 한 게임만 집계됩니다.</div>
    `;
  }

  async function toggleRankDetail(tr) {
    const next = tr.nextElementSibling;
    if (next && next.classList.contains("ih-detail-tr")) {
      next.remove();
      tr.classList.remove("ih-open");
      return;
    }
    const key = tr.getAttribute("data-detail");
    const detailTr = document.createElement("tr");
    detailTr.className = "ih-detail-tr";
    detailTr.innerHTML = `<td colspan="7"><div class="ih-detail-box"><i class="fa-solid fa-spinner fa-spin"></i> 불러오는 중...</div></td>`;
    tr.after(detailTr);
    tr.classList.add("ih-open");
    try {
      const res = await fetch(`/api/inhouse/players/${encodeURIComponent(key)}?days=30`);
      const d = await res.json();
      if (!res.ok || !d.games) throw new Error("no detail");
      const posNames = { TOP: "탑", JUNGLE: "정글", MIDDLE: "미드", BOTTOM: "원딜", UTILITY: "서폿" };
      const positions = (d.positions || []).map(x => `${_esc(posNames[x.position] || x.position)} ${_esc(String(x.games))}`).join(" · ") || "-";
      const recent = (d.recent || []).map(g => `
        <span class="ih-detail-game ${g.win ? "ih-win" : "ih-loss"}" title="#${_esc(String(g.game_id))}">
          <img src="${CHAMP_IMG}${_esc(g.champion)}.png" alt="" onerror="this.style.display='none'">
          ${_esc(String(g.kills))}/${_esc(String(g.deaths))}/${_esc(String(g.assists))}
        </span>
      `).join("");
      detailTr.querySelector(".ih-detail-box").innerHTML = `
        <div class="ih-detail-grid">
          <div><span>경기</span><strong>${_esc(String(d.games))}</strong></div>
          <div><span>평균 K/D/A</span><strong>${_esc(String(d.avg_kills))} / ${_esc(String(d.avg_deaths))} / ${_esc(String(d.avg_assists))}</strong></div>
          <div><span>평균 골드</span><strong>${_esc(Number(d.avg_gold).toLocaleString())}</strong></div>
          <div><span>평균 CS</span><strong>${_esc(String(d.avg_cs))} (분당 ${_esc(String(d.cs_per_min))})</strong></div>
          <div><span>평균 챔피언 피해</span><strong>${_esc(Number(d.avg_damage).toLocaleString())}</strong></div>
          <div><span>평균 시야 점수</span><strong>${_esc(String(d.avg_vision))}</strong></div>
          <div><span>평균 타워 철거</span><strong>${_esc(String(d.avg_turrets))}</strong></div>
          <div><span>포지션</span><strong>${positions}</strong></div>
        </div>
        ${recent ? `<div class="ih-detail-recent">${recent}</div>` : ""}
      `;
    } catch (err) {
      detailTr.querySelector(".ih-detail-box").textContent = "세부 기록을 불러오지 못했습니다.";
    }
  }

  function renderRecentGames(recent) {
    const container = document.getElementById("ihRecentGamesContainer");
    if (!container) return;

    const list = (recent || []).slice(0, 5);
    if (list.length === 0) {
      container.innerHTML = `
        <div class="ih-empty-box">
          <i class="fa-solid fa-circle-info"></i> 최근 내전 기록이 없습니다.
        </div>
      `;
      return;
    }

    const itemsHtml = list.map(g => {
      const dateStr = formatInhouseDate(g.created_at);
      const isBlueWin = g.winner === "blue";
      const isRedWin = g.winner === "red";

      let statusBadge = "";
      if (isBlueWin) {
        statusBadge = '<span class="ih-recent-badge ih-winner-blue"><i class="fa-solid fa-trophy"></i> 블루 승리</span>';
      } else if (isRedWin) {
        statusBadge = '<span class="ih-recent-badge ih-winner-red"><i class="fa-solid fa-trophy"></i> 레드 승리</span>';
      } else {
        statusBadge = '<span class="ih-recent-badge ih-winner-pending"><i class="fa-regular fa-clock"></i> 결과 미기록</span>';
      }

      const blueNames = Array.isArray(g.blue)
        ? g.blue.map(n => `<span class="ih-recent-player-name">${_esc(n)}</span>`).join(", ")
        : "";
      const redNames = Array.isArray(g.red)
        ? g.red.map(n => `<span class="ih-recent-player-name">${_esc(n)}</span>`).join(", ")
        : "";

      return `
        <div class="ih-recent-card ${isBlueWin ? 'ih-win-blue-card' : (isRedWin ? 'ih-win-red-card' : '')}">
          <div class="ih-recent-top">
            <div class="ih-recent-meta">
              <span class="ih-recent-id">#${_esc(g.id)}</span>
              <span class="ih-recent-date"><i class="fa-regular fa-clock"></i> ${dateStr}</span>
            </div>
            <div class="ih-recent-status">
              ${statusBadge}
            </div>
          </div>
          <div class="ih-recent-body">
            <div class="ih-recent-team ih-team-side-blue ${isBlueWin ? 'ih-highlight-winner' : (isRedWin ? 'ih-dimmed-loser' : '')}">
              <div class="ih-recent-team-tag">
                <span class="ih-team-dot ih-dot-blue"></span> 🔵 블루
              </div>
              <div class="ih-recent-team-members">${blueNames}</div>
            </div>
            <div class="ih-recent-divider">VS</div>
            <div class="ih-recent-team ih-team-side-red ${isRedWin ? 'ih-highlight-winner' : (isBlueWin ? 'ih-dimmed-loser' : '')}">
              <div class="ih-recent-team-tag">
                <span class="ih-team-dot ih-dot-red"></span> 🔴 레드
              </div>
              <div class="ih-recent-team-members">${redNames}</div>
            </div>
          </div>
        </div>
      `;
    }).join("");

    container.innerHTML = `<div class="ih-recent-list">${itemsHtml}</div>`;
  }

  function formatInhouseDate(sec) {
    if (!sec) return "-";
    const d = new Date(sec * 1000);
    if (isNaN(d.getTime())) return "-";
    const m = d.getMonth() + 1;
    const day = d.getDate();
    const h = String(d.getHours()).padStart(2, "0");
    const min = String(d.getMinutes()).padStart(2, "0");
    return `${m}월 ${day}일 ${h}:${min}`;
  }

  // Observer: #viewServerRanking 이 보일 때 한 번 초기화
  function checkVisibilityAndInit() {
    if (inhouseInitialized) return;
    const view = document.getElementById("viewServerRanking");
    if (!view) return;

    const isVisible = view.style.display !== "none" && window.getComputedStyle(view).display !== "none";
    if (isVisible) {
      inhouseInitialized = true;
      initInhouse();
    }
  }

  function setupObserver() {
    const view = document.getElementById("viewServerRanking");
    if (!view) return;

    checkVisibilityAndInit();
    if (inhouseInitialized) return;

    const observer = new MutationObserver(() => {
      checkVisibilityAndInit();
      if (inhouseInitialized) {
        observer.disconnect();
      }
    });

    observer.observe(view, {
      attributes: true,
      attributeFilter: ["style", "class"]
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupObserver);
  } else {
    setupObserver();
  }
})();
