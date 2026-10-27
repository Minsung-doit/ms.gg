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

  function initInhouse() {
    const container = document.getElementById("srInhouse");
    if (!container) return;

    renderBaseLayout(container);
    restoreOpenGameIfAny();
    loadServerRankingMembers();
    loadInhouseStats();
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
            <span class="ih-count-badge" id="ihCountBadge">선택 <strong>0</strong>/10</span>
          </div>
        </div>

        <!-- 1. 멤버 목록 (서버 랭킹) -->
        <div class="ih-section">
          <div class="ih-section-header">
            <div class="ih-section-title">
              <i class="fa-solid fa-users"></i> 서버 멤버 선택
              <span class="ih-section-hint">클릭하여 선택/해제</span>
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
            <span class="ih-section-hint">연결 안 한 친구 추가용</span>
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
              <span class="ih-section-hint">각 참가자의 주 포지션을 지정해주세요</span>
            </div>
            <button type="button" class="ih-btn-text" id="ihBtnClearAll" style="display: none;">
              <i class="fa-solid fa-trash-can"></i> 전체 비우기
            </button>
          </div>
          <div id="ihParticipantsList" class="ih-participants-grid">
            <div class="ih-empty-box">
              <i class="fa-solid fa-user-group"></i> 서버 멤버를 선택하거나 위에서 직접 친구를 추가해주세요 (0/10)
            </div>
          </div>
        </div>

        <!-- 4. 팀 나누기 액션 바 -->
        <div class="ih-action-bar">
          <button type="button" id="ihBtnBalance" class="ih-btn ih-btn-balance" disabled>
            <i class="fa-solid fa-scale-balanced"></i> 팀 나누기 (0/10)
          </button>
        </div>
        <div id="ihBalanceError" class="ih-error-notice" style="display: none;"></div>

        <!-- 5. 결과 영역 (블루팀 / 레드팀) -->
        <div id="ihResultSection" class="ih-result-section" style="display: none;">
          <div class="ih-result-header">
            <div class="ih-result-stats">
              <span class="ih-stat-pill">
                <i class="fa-solid fa-scale-balanced"></i> 점수 차이 <strong id="ihResultDiff">0</strong>LP
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

        <!-- 6. 내전 전적 (최근 30일) -->
        <div class="ih-section ih-stats-section">
          <div class="ih-section-header">
            <div class="ih-section-title">
              <i class="fa-solid fa-trophy" style="color: #F59E0B;"></i> 내전 전적 (최근 30일)
            </div>
            <button type="button" class="ih-btn-text" id="ihBtnRefreshStats" title="내전 전적 새로고침">
              <i class="fa-solid fa-arrows-rotate"></i> 새로고침
            </button>
          </div>
          <div id="ihStatsTableContainer">
            <div class="ih-loading-members">
              <i class="fa-solid fa-spinner fa-spin"></i> 내전 전적을 불러오는 중...
            </div>
          </div>
        </div>

        <!-- 7. 최근 내전 -->
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

        if (selectedPlayers.length >= 10) {
          if (typeof showToast === "function") {
            showToast("내전은 최대 10명까지만 선택할 수 있습니다.", "warning");
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
          if (selectedPlayers.length >= 10) return;
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
        renderResult();
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

    // 11. 게임 액션 버튼 위임 (이 팀으로 시작 / 블루 승리 / 레드 승리)
    container.addEventListener("click", (e) => {
      if (e.target.closest("#ihBtnStartGame")) {
        handleStartGame();
      } else if (e.target.closest("#ihBtnWinBlue")) {
        handleSetResult("blue");
      } else if (e.target.closest("#ihBtnWinRed")) {
        handleSetResult("red");
      }
    });
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
      const res = await fetch("/api/server-ranking");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      fetchError = null;

      const rawMembers = Array.isArray(data.members) ? data.members : [];
      serverMembers = rawMembers.map((m, idx) => ({
        id: `sr_${idx}_${m.game_name || m.discord_name || idx}`,
        name: m.game_name || m.discord_name || "소환사",
        discord_name: m.discord_name || "",
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
          <i class="fa-solid fa-users"></i> 등록된 서버 랭킹 멤버가 없습니다. 아래에서 직접 친구를 추가해주세요.
        </div>
      `;
      return;
    }

    const isFull = selectedPlayers.length >= 10;
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
          <i class="fa-solid fa-user-group"></i> 서버 멤버를 선택하거나 위에서 직접 친구를 추가해주세요 (0/10)
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
      badge.innerHTML = `선택 <strong>${count}</strong>/10`;
      badge.classList.toggle("ih-count-full", count === 10);
    }

    const btn = document.getElementById("ihBtnBalance");
    if (btn) {
      btn.disabled = count !== 10;
      btn.innerHTML = `<i class="fa-solid fa-scale-balanced"></i> 팀 나누기 (${count}/10)`;
      btn.classList.toggle("ih-ready", count === 10);
    }
  }

  async function handleBalance() {
    if (selectedPlayers.length !== 10) return;

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
        tier: p.tier || "UNRANKED",
        rank: p.rank || "",
        lp: typeof p.lp === "number" ? p.lp : 0,
        position: p.position || null
      }))
    };

    try {
      const res = await fetch("/api/inhouse/balance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok) {
        const msg = data.detail || "팀 나누기에 실패했습니다.";
        if (errEl) {
          errEl.textContent = typeof msg === "string" ? msg : JSON.stringify(msg);
          errEl.style.display = "block";
        }
        return;
      }

      balanceOptions = Array.isArray(data.options) ? data.options : [];
      currentOptionIdx = 0;

      if (balanceOptions.length > 0) {
        renderResult();
        const resSec = document.getElementById("ihResultSection");
        if (resSec) {
          resSec.style.display = "block";
          resSec.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      } else {
        if (errEl) {
          errEl.textContent = "나눌 수 있는 최적 팀 조합을 찾지 못했습니다.";
          errEl.style.display = "block";
        }
      }
    } catch (err) {
      if (errEl) {
        errEl.textContent = "서버와 통신하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
        errEl.style.display = "block";
      }
    } finally {
      if (btn) {
        btn.disabled = selectedPlayers.length !== 10;
        btn.innerHTML = `<i class="fa-solid fa-scale-balanced"></i> 팀 나누기 (${selectedPlayers.length}/10)`;
      }
    }
  }

  function renderResult() {
    const resSec = document.getElementById("ihResultSection");
    if (!resSec || balanceOptions.length === 0) return;

    const opt = balanceOptions[currentOptionIdx];
    if (!opt) return;

    const diffEl = document.getElementById("ihResultDiff");
    if (diffEl) diffEl.textContent = formatNumber(opt.diff);

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

    const cycleBtn = document.getElementById("ihBtnCycleOption");
    if (cycleBtn) {
      cycleBtn.innerHTML = `<i class="fa-solid fa-shuffle"></i> 다른 조합 (${currentOptionIdx + 1}/${balanceOptions.length})`;
      cycleBtn.style.display = balanceOptions.length > 1 ? "inline-flex" : "none";
    }

    const blueAvg = document.getElementById("ihBlueAvg");
    if (blueAvg) blueAvg.textContent = `평균 ${opt.blue.average_label || "-"}`;
    const bluePlayersEl = document.getElementById("ihBluePlayers");
    if (bluePlayersEl) {
      bluePlayersEl.innerHTML = opt.blue.players.map(p => renderPlayerItem(p)).join("");
    }

    const redAvg = document.getElementById("ihRedAvg");
    if (redAvg) redAvg.textContent = `평균 ${opt.red.average_label || "-"}`;
    const redPlayersEl = document.getElementById("ihRedPlayers");
    if (redPlayersEl) {
      redPlayersEl.innerHTML = opt.red.players.map(p => renderPlayerItem(p)).join("");
    }

    renderGameActionArea();
  }

  function renderPlayerItem(p) {
    if (typeof p === "string") {
      p = { name: p };
    }
    const posKr = p.position ? (POS_NAMES_KR[p.position] || p.position) : "모름";
    const posIcon = p.position ? (POS_ICONS[p.position] || "fa-question") : "fa-question";
    const tierKr = p.display_tier || formatTierKr(p.tier, p.rank, p.lp);
    const isEst = Boolean(p.estimated);

    return `
      <div class="ih-team-player-row">
        <div class="ih-player-left">
          <span class="ih-pos-badge" data-pos="${_esc(p.position || 'NONE')}" title="${_esc(posKr)}">
            <i class="fa-solid ${posIcon}"></i> ${_esc(posKr)}
          </span>
          <strong class="ih-player-name" title="${_esc(p.name)}">${_esc(p.name)}</strong>
        </div>
        <div class="ih-player-right">
          <span class="ih-player-tier">${_esc(tierKr)}</span>
          ${isEst ? '<span class="ih-badge-estimated" title="언랭크 계정으로 중간값으로 점수를 추정했습니다">추정</span>' : ""}
        </div>
      </div>
    `;
  }

  function formatDiscordText(opt) {
    const formatTeam = (prefix, teamData) => {
      const list = (teamData.players || []).map(p => {
        const name = typeof p === "string" ? p : (p ? p.name : "");
        const pos = typeof p === "object" && p && p.position ? (POS_NAMES_KR[p.position] || p.position) : "";
        return pos ? `${name}(${pos})` : name;
      }).join(", ");
      return `${prefix}: ${list} (평균 ${(teamData && teamData.average_label) || ""})`;
    };

    const blue = formatTeam("🔵 블루", opt.blue);
    const red = formatTeam("🔴 레드", opt.red);
    let extra = `점수 차이 ${opt.diff}LP`;
    if (opt.position_clash > 0) {
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

    const diffEl = document.getElementById("ihResultDiff");
    if (diffEl) diffEl.textContent = formatNumber(openGame.diff || 0);

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

  // Stats & Recent Matches Handlers
  async function loadInhouseStats() {
    const statsTableContainer = document.getElementById("ihStatsTableContainer");
    const recentGamesContainer = document.getElementById("ihRecentGamesContainer");

    try {
      const res = await fetch("/api/inhouse/stats?days=30");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      renderStatsTable(data.players || []);
      renderRecentGames(data.recent || []);
    } catch (err) {
      if (statsTableContainer) {
        statsTableContainer.innerHTML = `
          <div class="ih-error-notice">
            <i class="fa-solid fa-triangle-exclamation"></i> 내전 전적을 불러오지 못했습니다.
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

  function renderStatsTable(players) {
    const container = document.getElementById("ihStatsTableContainer");
    if (!container) return;

    const top10 = (players || []).slice(0, 10);
    if (top10.length === 0) {
      container.innerHTML = `
        <div class="ih-empty-box">
          <i class="fa-solid fa-circle-info"></i> 아직 기록된 내전이 없습니다.
        </div>
      `;
      return;
    }

    const rowsHtml = top10.map((p, idx) => {
      const rank = idx + 1;
      const wins = typeof p.wins === "number" ? p.wins : 0;
      const losses = typeof p.losses === "number" ? p.losses : 0;
      const games = p.games || (wins + losses);
      const winRate = typeof p.win_rate === "number"
        ? p.win_rate
        : (games > 0 ? Math.round((wins / games) * 1000) / 10 : 0);
      const rateColor = winRate > 50 ? "#10B981" : "#E84057";

      let rankClass = "ih-rank-num";
      if (rank === 1) rankClass += " ih-rank-gold";
      else if (rank === 2) rankClass += " ih-rank-silver";
      else if (rank === 3) rankClass += " ih-rank-bronze";

      return `
        <tr class="ih-stat-tr">
          <td class="ih-td-rank"><span class="${rankClass}">${rank}</span></td>
          <td class="ih-td-name" title="${_esc(p.name)}">
            <span class="ih-name-truncate">${_esc(p.name)}</span>
          </td>
          <td class="ih-td-wins">${wins}승</td>
          <td class="ih-td-losses">${losses}패</td>
          <td class="ih-td-rate" style="color: ${rateColor}; font-weight: 700;">${winRate.toFixed(1)}%</td>
        </tr>
      `;
    }).join("");

    container.innerHTML = `
      <div class="ih-table-wrap">
        <table class="ih-stats-table">
          <thead>
            <tr>
              <th class="ih-th-rank">순위</th>
              <th class="ih-th-name">이름</th>
              <th class="ih-th-wins">승</th>
              <th class="ih-th-losses">패</th>
              <th class="ih-th-rate">승률</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    `;
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
