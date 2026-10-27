// Duo / Recruit Finder (구인) Module
let duoGamesConfig = null;
let currentDfGame = "lol";
let currentDfPos = "ALL";
let currentDfQueue = "ALL";
let currentDfTier = "ALL";
let currentDfVoice = "ALL";

let myLolTierRank = null;
let myLolTierChecked = false;

const LOL_TIER_RANKS = {
  "IRON": 0, "아이언": 0,
  "BRONZE": 1, "브론즈": 1,
  "SILVER": 2, "실버": 2,
  "GOLD": 3, "골드": 3,
  "PLATINUM": 4, "플래티넘": 4,
  "EMERALD": 5, "에메랄드": 5,
  "DIAMOND": 6, "다이아몬드": 6,
  "MASTER": 7, "마스터": 7,
  "GRANDMASTER": 8, "그랜드마스터": 8,
  "CHALLENGER": 9, "챌린저": 9
};

function parseTierRank(tierStr) {
  if (!tierStr) return null;
  const s = String(tierStr).toUpperCase().trim();
  // 긴 이름부터 비교 ('그랜드마스터'가 '마스터'로 잡히지 않게)
  const entries = Object.entries(LOL_TIER_RANKS).sort((a, b) => b[0].length - a[0].length);
  for (const [key, rank] of entries) {
    if (s.includes(key.toUpperCase())) {
      return rank;
    }
  }
  return null;
}

let myLolPlayer = null; // 서버 랭킹에서 연결한 내 라이엇 계정 (글쓰기 자동 채우기)

async function resolveMyLolTier() {
  if (myLolTierChecked) return myLolTierRank;
  myLolTierChecked = true;
  try {
    const res = await fetch("/api/me");
    if (!res.ok) return null;
    const me = await res.json();
    if (!me || !me.account || !me.account.game_name) return null;

    const gameName = me.account.game_name;
    const tagLine = me.account.tag_line || "KR1";
    const pRes = await fetch(`/api/player/${encodeURIComponent(gameName)}/${encodeURIComponent(tagLine)}`);
    if (!pRes.ok) return null;
    const pData = await pRes.json();
    const player = pData.player;
    if (!player) return null;

    const tierRaw = player.tier || player.tier_kr || player.display_tier || "";
    myLolPlayer = player;
    myLolTierRank = parseTierRank(tierRaw);
    return myLolTierRank;
  } catch (err) {
    console.warn("Failed to resolve my tier rank:", err);
    return null;
  }
}

function getDuoPosNameKr(pos, game) {
  if (!pos || pos === "ALL") return "전체";
  const p = pos.toUpperCase();
  if (p === "TOP") return "탑";
  if (p === "JUG" || p === "JUNGLE") return "정글";
  if (p === "MID") return "미드";
  if (p === "BOT" || p === "ADC") return "원딜";
  if (p === "SUP" || p === "SUPPORT") return (game === "overwatch" ? "지원" : "서포터");
  if (p === "TANK") return "탱커";
  if (p === "DPS") return "딜러";
  return pos;
}

function getDuoPosIcon(pos) {
  if (!pos || pos === "ALL") return '<i class="fa-solid fa-layer-group"></i>';
  const p = pos.toUpperCase();
  if (p === "TOP") return '<i class="fa-solid fa-shield"></i>';
  if (p === "JUG" || p === "JUNGLE") return '<i class="fa-solid fa-tree"></i>';
  if (p === "MID") return '<i class="fa-solid fa-crosshairs"></i>';
  if (p === "BOT" || p === "ADC") return '<i class="fa-solid fa-bullseye"></i>';
  if (p === "SUP" || p === "SUPPORT") return '<i class="fa-solid fa-heart"></i>';
  if (p === "TANK") return '<i class="fa-solid fa-shield-halved"></i>';
  if (p === "DPS") return '<i class="fa-solid fa-crosshairs"></i>';
  return '<i class="fa-solid fa-gamepad"></i>';
}

function getQueueIcon(q) {
  if (!q) return "fa-gamepad";
  const str = String(q);
  if (str.includes("솔로") || str.includes("경쟁전")) return "fa-trophy";
  if (str.includes("스쿼드") || str.includes("자유") || str.includes("파티")) return "fa-users";
  if (str.includes("듀오")) return "fa-user-group";
  if (str.includes("칼바람")) return "fa-snowflake";
  if (str.includes("빠른")) return "fa-bolt";
  return "fa-gamepad";
}

async function fetchDuoGamesConfig() {
  try {
    const res = await fetch("/api/duo-games");
    if (res.ok) {
      duoGamesConfig = await res.json();
      return duoGamesConfig;
    }
  } catch (e) {
    console.error("Failed to load duo games config:", e);
  }
  duoGamesConfig = {
    default: "lol",
    games: [
      {
        id: "lol", name: "리그 오브 레전드", short: "롤",
        positions: [["TOP", "탑"], ["JUG", "정글"], ["MID", "미드"], ["BOT", "원딜"], ["SUP", "서포터"]],
        tiers: ["다이아몬드", "에메랄드", "플래티넘", "골드", "실버", "브론즈", "아이언"],
        queues: ["솔로랭크", "자유랭크", "칼바람 나락"],
        party_size: {"솔로랭크": 2, "자유랭크": 5, "칼바람 나락": 5},
        needs_tag: true, has_stats: true
      },
      {
        id: "pubg", name: "배틀그라운드", short: "배그",
        positions: [],
        tiers: ["마스터", "다이아몬드", "플래티넘", "골드", "실버", "브론즈"],
        queues: ["경쟁전 스쿼드", "일반 스쿼드", "일반 듀오"],
        party_size: {"경쟁전 스쿼드": 4, "일반 스쿼드": 4, "일반 듀오": 2},
        needs_tag: false, has_stats: false
      },
      {
        id: "overwatch", name: "오버워치 2", short: "옵치",
        positions: [["TANK", "탱커"], ["DPS", "딜러"], ["SUP", "지원"]],
        tiers: ["챔피언", "그랜드마스터", "마스터", "다이아몬드", "플래티넘", "골드", "실버", "브론즈"],
        queues: ["경쟁전", "빠른 대전"],
        party_size: {"경쟁전": 5, "빠른 대전": 5},
        needs_tag: true, has_stats: false
      }
    ]
  };
  return duoGamesConfig;
}

function getGameConfig(gameId) {
  if (!duoGamesConfig || !duoGamesConfig.games) return null;
  return duoGamesConfig.games.find(g => g.id === gameId) || duoGamesConfig.games[0];
}

function renderGameSelectButtons() {
  const bar = document.getElementById("dfGameSelectBar");
  if (!bar || !duoGamesConfig || !duoGamesConfig.games) return;
  bar.innerHTML = "";
  duoGamesConfig.games.forEach(g => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `df-game-tab-btn ${g.id === currentDfGame ? "active" : ""}`;
    btn.setAttribute("data-game", g.id);
    btn.textContent = g.short;
    btn.title = g.name;
    btn.addEventListener("click", () => {
      selectDuoGame(g.id);
    });
    bar.appendChild(btn);
  });
}

function selectDuoGame(gameId) {
  currentDfGame = gameId;
  try {
    localStorage.setItem("duo_selected_game", gameId);
  } catch (_) {}

  const bar = document.getElementById("dfGameSelectBar");
  if (bar) {
    const btns = bar.querySelectorAll(".df-game-tab-btn");
    btns.forEach(b => {
      if (b.getAttribute("data-game") === gameId) {
        b.classList.add("active");
      } else {
        b.classList.remove("active");
      }
    });
  }

  currentDfPos = "ALL";
  currentDfQueue = "ALL";
  currentDfTier = "ALL";
  currentDfVoice = "ALL";

  updateFiltersForGame(gameId);
  updateModalForGame(gameId);
  loadDuoPosts();
}

function updateFiltersForGame(gameId) {
  const game = getGameConfig(gameId);
  if (!game) return;

  // 1. Queue filter buttons
  const queueGroup = document.getElementById("dfQueueFilterGroup");
  if (queueGroup) {
    queueGroup.innerHTML = `
      <span class="df-filter-label"><i class="fa-solid fa-gamepad"></i></span>
      <button class="df-queue-btn active" data-queue="ALL"><i class="fa-solid fa-layer-group"></i> 전체</button>
      ${(game.queues || []).map(q => `
        <button class="df-queue-btn" data-queue="${escapeHtml(q)}"><i class="fa-solid ${getQueueIcon(q)}"></i> ${escapeHtml(q)}</button>
      `).join("")}
    `;
    const queueBtns = queueGroup.querySelectorAll(".df-queue-btn");
    queueBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        queueBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentDfQueue = btn.getAttribute("data-queue") || "ALL";
        loadDuoPosts();
      });
    });
  }

  // 2. Position filter buttons
  const posGroup = document.getElementById("dfPosFilterGroup");
  if (posGroup) {
    if (!game.positions || game.positions.length === 0) {
      posGroup.style.display = "none";
      currentDfPos = "ALL";
    } else {
      posGroup.style.display = "";
      posGroup.innerHTML = `
        <span class="df-filter-label"><i class="fa-solid fa-crosshairs"></i></span>
        <button class="df-pos-btn active" data-pos="ALL"><span class="df-badge-pos-icon"><i class="fa-solid fa-layer-group"></i></span> 전체</button>
        ${game.positions.map(([code, name]) => `
          <button class="df-pos-btn pos-${code.toLowerCase()}" data-pos="${escapeHtml(code)}">
            <span class="df-badge-pos-icon">${getDuoPosIcon(code)}</span> ${escapeHtml(name)}
          </button>
        `).join("")}
      `;
      const posBtns = posGroup.querySelectorAll(".df-pos-btn");
      posBtns.forEach(btn => {
        btn.addEventListener("click", () => {
          posBtns.forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          currentDfPos = btn.getAttribute("data-pos") || "ALL";
          loadDuoPosts();
        });
      });
    }
  }

  // 3. Tier filter dropdown
  const tierSelect = document.getElementById("dfTierFilter");
  if (tierSelect) {
    tierSelect.innerHTML = `<option value="ALL">전체 티어</option>` +
      (game.tiers || []).map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("");
    tierSelect.value = "ALL";
  }

  // 4. Voice buttons reset
  const voiceGroup = document.getElementById("dfVoiceFilterGroup");
  if (voiceGroup) {
    const voiceBtns = voiceGroup.querySelectorAll(".df-voice-btn");
    voiceBtns.forEach(b => {
      if (b.getAttribute("data-voice") === "ALL") {
        b.classList.add("active");
      } else {
        b.classList.remove("active");
      }
    });
  }
}

function updateModalForGame(gameId) {
  const game = getGameConfig(gameId);
  if (!game) return;

  // Title
  const titleText = document.getElementById("dfModalTitleText");
  if (titleText) titleText.textContent = `${game.name} 구인글 등록`;

  // Name
  const nameLabel = document.getElementById("dfLabelName");
  const nameInput = document.getElementById("dfInputName");
  if (nameLabel) nameLabel.textContent = game.id === "lol" ? "소환사 닉네임" : "닉네임";
  if (nameInput) nameInput.placeholder = game.id === "lol" ? "예: Hide on bush" : "예: 닉네임 입력";

  // Tag
  const tagGroup = document.getElementById("dfFormGroupTag");
  const tagInput = document.getElementById("dfInputTag");
  if (tagGroup) {
    if (game.needs_tag) {
      tagGroup.style.display = "";
      if (tagInput) {
        tagInput.value = game.id === "lol" ? "KR1" : "";
        tagInput.placeholder = game.id === "lol" ? "KR1" : "태그";
      }
    } else {
      tagGroup.style.display = "none";
      if (tagInput) tagInput.value = "";
    }
  }

  // Tier
  const tierSelect = document.getElementById("dfSelectTier");
  if (tierSelect && game.tiers) {
    tierSelect.innerHTML = game.tiers.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("");
    if (game.id === "lol") {
      tierSelect.value = "골드";
    } else if (game.tiers.length > 0) {
      tierSelect.value = game.tiers[0];
    }
  }

  // Positions
  const myPosGroup = document.getElementById("dfFormGroupMyPos");
  const targetPosGroup = document.getElementById("dfFormGroupTargetPos");
  const myPosBadges = document.getElementById("modalMyPosBadges");
  const targetPosBadges = document.getElementById("modalTargetPosBadges");
  const selectMyPos = document.getElementById("dfSelectMyPos");
  const selectTargetPos = document.getElementById("dfSelectTargetPos");

  if (!game.positions || game.positions.length === 0) {
    if (myPosGroup) myPosGroup.style.display = "none";
    if (targetPosGroup) targetPosGroup.style.display = "none";
    if (selectMyPos) selectMyPos.value = "ALL";
    if (selectTargetPos) selectTargetPos.value = "ALL";
  } else {
    if (myPosGroup) myPosGroup.style.display = "";
    if (targetPosGroup) targetPosGroup.style.display = "";

    if (myPosBadges) {
      myPosBadges.innerHTML = game.positions.map(([code, name], idx) => `
        <button type="button" class="m-pos-chip ${idx === 0 ? 'active' : ''}" data-pos="${escapeHtml(code)}" title="${escapeHtml(name)}">
          ${getDuoPosIcon(code)} ${escapeHtml(name)}
        </button>
      `).join("");
    }
    if (selectMyPos) {
      selectMyPos.innerHTML = game.positions.map(([code, name]) => `
        <option value="${escapeHtml(code)}">${escapeHtml(name)}</option>
      `).join("");
      selectMyPos.value = game.positions[0][0];
    }

    if (targetPosBadges) {
      targetPosBadges.innerHTML = game.positions.map(([code, name]) => `
        <button type="button" class="m-pos-chip" data-pos="${escapeHtml(code)}" title="${escapeHtml(name)}">
          ${getDuoPosIcon(code)} ${escapeHtml(name)}
        </button>
      `).join("") + `
        <button type="button" class="m-pos-chip active" data-pos="ALL" title="상관없음">
          <i class="fa-solid fa-layer-group"></i> 전체
        </button>
      `;
    }
    if (selectTargetPos) {
      selectTargetPos.innerHTML = game.positions.map(([code, name]) => `
        <option value="${escapeHtml(code)}">${escapeHtml(name)}</option>
      `).join("") + `<option value="ALL" selected>상관없음</option>`;
      selectTargetPos.value = "ALL";
    }

    bindModalPosChips();
  }

  // Queue & Party Size
  const selectQueue = document.getElementById("dfSelectQueue");
  const partyBadge = document.getElementById("dfPartySizeBadge");
  if (selectQueue && game.queues) {
    selectQueue.innerHTML = game.queues.map(q => `<option value="${escapeHtml(q)}">${escapeHtml(q)}</option>`).join("");
    selectQueue.value = game.queues[0];

    const updatePartyBadge = () => {
      const qVal = selectQueue.value;
      const pSize = (game.party_size && game.party_size[qVal]) || 2;
      if (partyBadge) partyBadge.textContent = `(${pSize}명)`;
    };
    selectQueue.onchange = updatePartyBadge;
    updatePartyBadge();
  }

  // Champions
  const champsGroup = document.getElementById("dfFormGroupChamps");
  const champsInput = document.getElementById("dfInputChamps");
  if (champsGroup) {
    if (game.id === "lol") {
      champsGroup.style.display = "";
    } else {
      champsGroup.style.display = "none";
      if (champsInput) champsInput.value = "";
    }
  }
}

function bindModalPosChips() {
  const selectMyPos = document.getElementById("dfSelectMyPos");
  const myPosChips = document.querySelectorAll("#modalMyPosBadges .m-pos-chip");
  myPosChips.forEach(chip => {
    chip.onclick = () => {
      myPosChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      if (selectMyPos) {
        selectMyPos.value = chip.getAttribute("data-pos") || "MID";
      }
    };
  });

  const selectTargetPos = document.getElementById("dfSelectTargetPos");
  const targetPosChips = document.querySelectorAll("#modalTargetPosBadges .m-pos-chip");
  targetPosChips.forEach(chip => {
    chip.onclick = () => {
      targetPosChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      if (selectTargetPos) {
        selectTargetPos.value = chip.getAttribute("data-pos") || "ALL";
      }
    };
  });
}

function bindModalVoiceChips() {
  const voiceCheck = document.getElementById("dfCheckVoice");
  const channelGroup = document.getElementById("dfDiscordChannelGroup");
  const voiceChips = document.querySelectorAll("#modalVoiceBadges .m-voice-chip");
  voiceChips.forEach(chip => {
    chip.onclick = () => {
      voiceChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      const isVoice = chip.getAttribute("data-voice") === "true";
      if (voiceCheck) {
        voiceCheck.checked = isVoice;
      }
      if (channelGroup) {
        channelGroup.style.display = isVoice ? "block" : "none";
      }
    };
  });
}

function openCreateDuoModal() {
  updateModalForGame(currentDfGame);
  const modal = document.getElementById("createDuoPostModal");
  if (modal) modal.classList.add("open");
  prefillDuoFormFromAccount();
}

// 롤 글쓰기: 연결된 내 계정의 닉네임·태그·티어를 빈 칸에만 채운다 (마스터 이상은 듀오 불가라 티어는 선택지에 있을 때만)
async function prefillDuoFormFromAccount() {
  if (currentDfGame !== "lol") return;
  await resolveMyLolTier();
  const p = myLolPlayer;
  if (!p || currentDfGame !== "lol") return;
  const nameEl = document.getElementById("dfInputName");
  const tagEl = document.getElementById("dfInputTag");
  const tierEl = document.getElementById("dfSelectTier");
  if (nameEl && !nameEl.value.trim()) nameEl.value = p.game_name || "";
  if (tagEl && (!tagEl.value.trim() || tagEl.value.trim() === "KR1")) tagEl.value = p.tag_line || tagEl.value;
  const tierKr = (typeof TIER_NAMES_KR !== "undefined" && TIER_NAMES_KR[String(p.tier || "").toUpperCase()]) || "";
  if (tierEl && tierKr && [...tierEl.options].some(o => o.value === tierKr)) tierEl.value = tierKr;
}
window.openCreateDuoModal = openCreateDuoModal;

function closeCreateDuoModal() {
  const modal = document.getElementById("createDuoPostModal");
  if (modal) modal.classList.remove("open");
}
window.closeCreateDuoModal = closeCreateDuoModal;

function syncTabTitles() {
  const tabSpan = document.querySelector("#tabBtnDuoFinder span");
  if (tabSpan) tabSpan.textContent = "구인";
  const tabBtn = document.getElementById("tabBtnDuoFinder");
  if (tabBtn) tabBtn.setAttribute("title", "구인");
  const mobileSheetSpan = document.querySelector('.sheet-grid-item[data-tab="duofinder"] .sheet-item-title');
  if (mobileSheetSpan) mobileSheetSpan.textContent = "구인";
}

async function initDuoFinder() {
  syncTabTitles();

  const tierSelect = document.getElementById("dfTierFilter");
  const voiceBtns = document.querySelectorAll(".df-voice-btn");
  const btnOpenModal = document.getElementById("btnOpenCreateDuoModal");
  const btnCloseModal = document.getElementById("btnCloseCreateDuoModal");
  const btnCancelModal = document.getElementById("btnCancelCreateDuo");
  const createForm = document.getElementById("createDuoForm");

  // Voice filter handler
  voiceBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      voiceBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentDfVoice = btn.getAttribute("data-voice") || "ALL";
      loadDuoPosts();
    });
  });

  // Tier filter handler
  if (tierSelect) {
    tierSelect.addEventListener("change", (e) => {
      currentDfTier = e.target.value;
      loadDuoPosts();
    });
  }

  // Load config & setup game selector
  await fetchDuoGamesConfig();

  try {
    const saved = localStorage.getItem("duo_selected_game");
    if (saved && duoGamesConfig && duoGamesConfig.games.some(g => g.id === saved)) {
      currentDfGame = saved;
    } else if (duoGamesConfig && duoGamesConfig.default) {
      currentDfGame = duoGamesConfig.default;
    }
  } catch (_) {
    currentDfGame = (duoGamesConfig && duoGamesConfig.default) || "lol";
  }

  renderGameSelectButtons();
  updateFiltersForGame(currentDfGame);
  updateModalForGame(currentDfGame);

  // Modal open/close
  if (btnOpenModal) btnOpenModal.onclick = openCreateDuoModal;

  // 실시간 갱신: 구인 탭이 보이고 글쓰기 창이 닫혀 있을 때 30초마다 목록 다시 받기 (서버 캐시도 30초)
  if (!window._duoAutoRefresh) {
    window._duoAutoRefresh = setInterval(() => {
      const view = document.getElementById("viewDuoFinder");
      const modal = document.getElementById("createDuoPostModal");
      if (document.visibilityState !== "visible" || !view || !view.classList.contains("active")) return;
      if (modal && modal.classList.contains("open")) return;
      loadDuoPosts({ silent: true });
    }, 30000);
  }
  if (btnCloseModal) btnCloseModal.onclick = closeCreateDuoModal;
  if (btnCancelModal) btnCancelModal.onclick = closeCreateDuoModal;

  bindModalVoiceChips();

  // Discord Voice Channel Dropdown Handlers
  const voiceCheck = document.getElementById("dfCheckVoice");
  const channelGroup = document.getElementById("dfDiscordChannelGroup");
  const channelSelect = document.getElementById("dfSelectDiscordChannel");
  const customUrlWrap = document.getElementById("dfCustomDiscordUrlWrap");
  const customUrlInput = document.getElementById("dfInputCustomDiscordUrl");

  voiceCheck?.addEventListener("change", () => {
    if (channelGroup) {
      channelGroup.style.display = voiceCheck?.checked ? "block" : "none";
    }
  });

  channelSelect?.addEventListener("change", () => {
    if (customUrlWrap) {
      if (channelSelect.value === "CUSTOM") {
        customUrlWrap.style.display = "block";
      } else {
        const selectedOption = channelSelect.options[channelSelect.selectedIndex];
        const dataUrl = selectedOption?.getAttribute("data-url") || "";
        if (customUrlInput && dataUrl) {
          customUrlInput.value = dataUrl;
        }
      }
    }
  });

  // Form submit
  if (createForm) {
    createForm.onsubmit = async (e) => {
      e.preventDefault();
      const activeGame = getGameConfig(currentDfGame);
      let name = document.getElementById("dfInputName")?.value || "";
      let tag = document.getElementById("dfInputTag")?.value || "";
      if (name.includes("#")) {
        const parts = name.split("#");
        name = parts[0].trim();
        tag = parts[1].trim() || tag;
      }
      if (activeGame?.needs_tag && !tag && currentDfGame === "lol") {
        tag = "KR1";
      }

      const tierKr = document.getElementById("dfSelectTier")?.value || (activeGame?.tiers && activeGame.tiers[0]) || "다이아몬드";
      const myPos = activeGame?.positions?.length ? (document.getElementById("dfSelectMyPos")?.value || "MID") : "ALL";
      const targetPos = activeGame?.positions?.length ? (document.getElementById("dfSelectTargetPos")?.value || "ALL") : "ALL";
      const queue = document.getElementById("dfSelectQueue")?.value || (activeGame?.queues && activeGame.queues[0]) || "솔로랭크";
      const voice = document.getElementById("dfCheckVoice")?.checked ?? true;
      const title = document.getElementById("dfInputTitle")?.value || "";
      const desc = document.getElementById("dfInputDesc")?.value || "";
      const discordTag = document.getElementById("dfInputDiscord")?.value || "";
      const champsVal = document.getElementById("dfInputChamps")?.value || "";
      const mostChamps = (currentDfGame === "lol" && champsVal) ? champsVal.split(",").map(c => c.trim()).filter(Boolean) : [];
      const partySize = (activeGame?.party_size && activeGame.party_size[queue]) || 2;

      let discordChannelName = "";
      let discordVoiceUrl = "";
      let roomName = "";
      let roomLink = "";
      if (voice && channelSelect) {
        if (channelSelect.value === "CUSTOM") {
          roomName = `🔊 ${name || '호스트'}의 음성방`;
          discordChannelName = roomName;
          roomLink = customUrlInput?.value.trim() || "";
          discordVoiceUrl = roomLink;
        } else {
          discordChannelName = channelSelect.value;
          roomName = channelSelect.value;
          const selectedOption = channelSelect.options[channelSelect.selectedIndex];
          discordVoiceUrl = selectedOption?.getAttribute("data-url") || "";
          roomLink = customUrlInput?.value.trim() || discordVoiceUrl || "";
        }
      }

      try {
        const res = await fetch("/api/duo-posts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            game: currentDfGame,
            game_name: name,
            tag_line: activeGame?.needs_tag ? tag : "",
            tier_kr: tierKr,
            my_position: myPos,
            target_position: targetPos,
            queue_type: queue,
            voice: voice,
            title: title,
            description: desc,
            discord_tag: discordTag,
            most_champions: mostChamps,
            discord_channel_name: discordChannelName,
            discord_voice_url: discordVoiceUrl,
            discord_invite_url: roomLink.startsWith("https://") ? roomLink : null,
            room_name: roomName,
            room_link: roomLink,
            max_members: partySize,
            host_mic: voice
          })
        });

        if (res.ok) {
          const data = await res.json();
          if (data.post && data.owner_token) saveDuoOwnerToken(data.post.id, data.owner_token);
          showToast("구인글이 등록되었습니다.", "success");
          closeCreateDuoModal();
          createForm.reset();
          loadDuoPosts();
        } else {
          const err = await res.json().catch(() => ({}));
          const detail = Array.isArray(err.detail) ? "입력값을 확인해주세요." : (err.detail || "글 등록에 실패했습니다.");
          showToast(detail, "error");
        }
      } catch (err) {
        showToast("오류가 발생했습니다.", "error");
      }
    };
  }

  loadDuoPosts();
}
window.initDuoFinder = initDuoFinder;

// silent: 30초 자동 갱신용. 스피너 없이 받아 오고, 내용이 그대로면 다시 그리지 않는다 (펼친 패널 유지)
let lastDuoPostsSig = "";
async function loadDuoPosts(opts) {
  const silent = Boolean(opts && opts.silent);
  const gridEl = document.getElementById("duoPostsGrid");
  if (!gridEl) return;

  if (!silent) {
    gridEl.innerHTML = `<div style="padding: 2rem; text-align: center; color: var(--text-muted);"><div class="spinner"></div></div>`;
  }

  try {
    if (currentDfGame === "lol") {
      await resolveMyLolTier();
    }
    await refreshMyMemberPosts();
    const res = await fetch(`/api/duo-posts?game=${encodeURIComponent(currentDfGame)}&position=${encodeURIComponent(currentDfPos)}&queue_type=${encodeURIComponent(currentDfQueue)}&tier=${encodeURIComponent(currentDfTier)}&voice=${encodeURIComponent(currentDfVoice)}`);
    if (!res.ok) throw new Error("구인글 목록 로드 실패");
    const data = await res.json();
    const sig = JSON.stringify((data.posts || []).map(p => [p.id, p.current_members, p.is_full, p.created_at, (p.joiner_names || []).length]));
    if (silent && sig === lastDuoPostsSig) return;
    lastDuoPostsSig = sig;
    renderDuoPosts(data.posts || []);
  } catch (err) {
    console.error("Duo posts fetch error:", err);
    if (silent) return;
    gridEl.innerHTML = `<div style="grid-column: 1 / -1; padding: 3rem; text-align: center; color: var(--danger-color); font-weight: 700;">구인글을 불러오는 중 오류가 발생했습니다. 다시 시도해주세요.</div>`;
  }
}
window.loadDuoPosts = loadDuoPosts;

function joinDiscordVoiceRoom(voiceUrl, inviteUrl, channelName, tag, hostName, postId) {
  const targetVoice = isRealDuoLink(voiceUrl) ? voiceUrl : (isRealDuoLink(inviteUrl) ? inviteUrl : "");
  const targetInvite = isRealDuoLink(inviteUrl) ? inviteUrl : (targetVoice.startsWith("http") ? targetVoice : "");
  if (!targetVoice) {
    showToast("작성자가 디스코드 방 링크를 등록하지 않았습니다. 디스코드 태그로 직접 연락해 주세요.", "info", 4000);
    return;
  }
  const targetName = channelName || "호스트 대기방";
  const targetTag = tag || "";
  const targetHost = hostName || "호스트";

  if (typeof navigator !== "undefined" && navigator.vibrate) {
    try { navigator.vibrate(10); } catch (_) {}
  }

  if (postId) {
    fetch(`/api/duo-posts/${postId}/discord-join`, { method: "POST" }).catch(() => {});
  }

  const modalEl = document.getElementById("discordVoiceModal");
  if (modalEl) {
    const roomEl = document.getElementById("dvmRoomName");
    const hostEl = document.getElementById("dvmHostName");
    const statusEl = document.getElementById("dvmRoomStatus");
    const tagEl = document.getElementById("dvmHostTag");

    if (roomEl) roomEl.textContent = targetName;
    if (hostEl) hostEl.textContent = targetHost;
    if (statusEl) statusEl.textContent = "작성자가 등록한 디스코드 링크로 이동합니다";
    if (tagEl) tagEl.textContent = targetTag || `${targetHost}`;

    modalEl.style.display = "flex";

    const retryBtn = document.getElementById("btnDvmRetryVoice");
    if (retryBtn) {
      retryBtn.onclick = () => {
        if (targetVoice.startsWith("http://") || targetVoice.startsWith("https://")) {
          window.open(targetVoice, "_blank", "noopener,noreferrer");
        } else {
          try { window.location.href = targetVoice; } catch (_) {}
          setTimeout(() => {
            if (targetInvite) window.open(targetInvite, "_blank", "noopener,noreferrer");
          }, 300);
        }
      };
    }

    const closeBtn = document.getElementById("btnDvmClose");
    const xBtn = document.getElementById("btnCloseDiscordVoiceModal");
    const closeModal = () => { modalEl.style.display = "none"; };
    if (closeBtn) closeBtn.onclick = closeModal;
    if (xBtn) xBtn.onclick = closeModal;
    modalEl.onclick = (e) => {
      if (e.target === modalEl) closeModal();
    };
  }

  if (targetTag && navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(targetTag).catch(() => {});
  }

  if (targetVoice.startsWith("http://") || targetVoice.startsWith("https://")) {
    window.open(targetVoice, "_blank", "noopener,noreferrer");
  } else {
    try {
      window.location.href = targetVoice;
    } catch (err) {}

    setTimeout(() => {
      if (targetInvite) {
        window.open(targetInvite, "_blank", "noopener,noreferrer");
      }
    }, 500);
  }

  showToast("호스트 대기방으로 이동합니다.", "success");
}
window.joinDiscordVoiceRoom = joinDiscordVoiceRoom;

const DUO_FULL_KEYWORDS = Object.freeze(["마감", "초과", "완료", "풀방", "FULL", "CLOSED", "2/2명", "(2/2)", "만석", "FULL_ROOM"]);

function isDuoRoomFull(p) {
  if (!p) return false;
  if (p.is_full === true) return true;
  if (typeof p.current_members === 'number' && typeof p.max_members === 'number' && p.current_members >= p.max_members) return true;
  const st = String(p.room_status || '').trim();
  if (!st) return false;
  const stUpper = st.toUpperCase();
  return DUO_FULL_KEYWORDS.some(kw => st.includes(kw) || stUpper.includes(kw));
}

const DUO_OWNER_TOKENS_KEY = "duo_owner_tokens";

// 디스코드 로그인 멤버가 쓴 글 ID (/api/duo-posts/mine). 다른 기기에서도 내 글로 보고 마감·삭제할 수 있다
let myMemberPostIds = new Set();
const MEMBER_OWNER_MARK = "member";

async function refreshMyMemberPosts() {
  try {
    const res = await fetch("/api/duo-posts/mine");
    if (!res.ok) return;
    const data = await res.json();
    myMemberPostIds = new Set((data.ids || []).map(Number));
  } catch (_) {}
}

function getDuoOwnerTokens() {
  let tokens = {};
  try {
    tokens = JSON.parse(localStorage.getItem(DUO_OWNER_TOKENS_KEY) || "{}") || {};
  } catch (_) {}
  myMemberPostIds.forEach(id => { if (!tokens[id]) tokens[id] = MEMBER_OWNER_MARK; });
  return tokens;
}

function ownerHeaders(token) {
  return token && token !== MEMBER_OWNER_MARK ? { "X-Duo-Owner-Token": token } : {};
}

function saveDuoOwnerToken(postId, token) {
  try {
    const tokens = getDuoOwnerTokens();
    tokens[postId] = token;
    localStorage.setItem(DUO_OWNER_TOKENS_KEY, JSON.stringify(tokens));
  } catch (_) {}
}

const DUO_JOINED_POSTS_KEY = "duo_joined_posts";

function getDuoJoinedPosts() {
  try {
    const raw = localStorage.getItem(DUO_JOINED_POSTS_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list.map(Number).filter(Number.isFinite) : [];
  } catch (_) {
    return [];
  }
}
window.getDuoJoinedPosts = getDuoJoinedPosts;

function isDuoPostJoined(postId) {
  if (postId == null) return false;
  const list = getDuoJoinedPosts();
  return list.includes(Number(postId));
}
window.isDuoPostJoined = isDuoPostJoined;

function addDuoJoinedPost(postId) {
  if (postId == null) return;
  try {
    const list = getDuoJoinedPosts();
    const id = Number(postId);
    if (Number.isFinite(id) && !list.includes(id)) {
      list.push(id);
      localStorage.setItem(DUO_JOINED_POSTS_KEY, JSON.stringify(list));
    }
  } catch (_) {}
}
window.addDuoJoinedPost = addDuoJoinedPost;

function removeDuoJoinedPost(postId) {
  if (postId == null) return;
  try {
    const list = getDuoJoinedPosts();
    const id = Number(postId);
    const next = list.filter(item => item !== id);
    localStorage.setItem(DUO_JOINED_POSTS_KEY, JSON.stringify(next));
  } catch (_) {}
}
window.removeDuoJoinedPost = removeDuoJoinedPost;

function isSafeDuoLink(url) {
  return /^(https:\/\/|discord:\/\/)/i.test(String(url || ""));
}

function isPlaceholderDuoLink(url) {
  const s = String(url || "");
  return s.includes("1188000000000000001") || /discord\.gg\/lolgg-duo\b/i.test(s);
}

function isRealDuoLink(url) {
  return isSafeDuoLink(url) && !isPlaceholderDuoLink(url);
}

// 내 글 삭제 (작성자 토큰으로)
async function deleteDuoPost(postId, event) {
  if (event) event.stopPropagation();
  const ownerToken = getDuoOwnerTokens()[postId];
  if (!ownerToken || !confirm("이 구인글을 삭제할까요?")) return;
  try {
    const res = await fetch(`/api/duo-posts/${encodeURIComponent(postId)}`, { method: "DELETE", headers: ownerHeaders(ownerToken) });
    if (!res.ok && res.status !== 404) throw new Error(String(res.status));
    try {
      const tokens = getDuoOwnerTokens();
      delete tokens[postId];
      localStorage.setItem(DUO_OWNER_TOKENS_KEY, JSON.stringify(tokens));
    } catch (_) {}
    showToast("구인글을 삭제했어요.", "success");
    loadDuoPosts();
  } catch (e) {
    showToast("삭제하지 못했어요. 잠시 후 다시 시도해 주세요.", "error");
  }
}
window.deleteDuoPost = deleteDuoPost;

async function toggleDuoRoomCapacity(postId, event) {
  if (event) event.stopPropagation();
  const ownerToken = getDuoOwnerTokens()[postId];
  if (!ownerToken) {
    showToast("내가 작성한 구인글만 상태를 변경할 수 있습니다.", "warning");
    return;
  }
  const forgetToken = () => {
    try {
      const tokens = getDuoOwnerTokens();
      delete tokens[postId];
      localStorage.setItem(DUO_OWNER_TOKENS_KEY, JSON.stringify(tokens));
    } catch (_) {}
  };
  try {
    const res = await fetch(`/api/duo-posts/${postId}/toggle-status`, {
      method: "POST",
      headers: ownerHeaders(ownerToken)
    });
    if (res.ok) {
      const data = await res.json();
      const isFull = data.is_full;
      showToast(
        isFull
          ? "모집이 마감되었습니다."
          : "모집 중으로 변경되었습니다.",
        isFull ? "warning" : "success"
      );
      loadDuoPosts();
    } else {
      if (res.status === 403 || res.status === 404) {
        forgetToken();
        loadDuoPosts();
      }
      showToast("방 상태 변경에 실패했습니다.", "error");
    }
  } catch (err) {
    console.error("Toggle duo room capacity failed:", err);
    showToast("방 상태 변경 중 통신 오류가 발생했습니다.", "error");
  }
}
window.toggleDuoRoomCapacity = toggleDuoRoomCapacity;

function renderDuoPosts(posts) {
  const gridEl = document.getElementById("duoPostsGrid");
  if (!gridEl) return;

  if (!posts || posts.length === 0) {
    gridEl.innerHTML = `
      <div class="df-empty-posts">
        <i class="fa-solid fa-inbox"></i>
        <div class="df-empty-msg">구인글이 없습니다.</div>
        <button type="button" class="btn-primary df-empty-create-btn" onclick="openCreateDuoModal()">
          <i class="fa-solid fa-pen-to-square"></i> 글쓰기
        </button>
      </div>
    `;
    return;
  }

  // 나에게 맞는 글 먼저:
  // 1. isFull: 정원 마감 글은 계속 맨 아래
  // 2. 롤이고 /api/me 계정의 티어를 알면, 내 티어와 가까운 글 위로
  // 3. 최신글 우선 (id 내림차순)
  const decorated = posts.map(p => {
    const isFull = isDuoRoomFull(p);
    let dist = 99;
    if (currentDfGame === "lol" && myLolTierRank !== null) {
      const pRank = parseTierRank(p.tier || p.tier_kr);
      dist = pRank !== null ? Math.abs(pRank - myLolTierRank) : 99;
    }
    return {
      post: p,
      isFull,
      dist,
      id: p.id || 0
    };
  });

  decorated.sort((a, b) => {
    if (a.isFull !== b.isFull) {
      return a.isFull ? 1 : -1;
    }
    if (currentDfGame === "lol" && myLolTierRank !== null) {
      if (a.dist !== b.dist) {
        return a.dist - b.dist;
      }
    }
    return b.id - a.id;
  });

  gridEl.innerHTML = "";
  const fragment = document.createDocumentFragment();
  const ownedPostIds = getDuoOwnerTokens();

  decorated.forEach(({ post: p }) => {
    const card = createDuoCardElement(p, ownedPostIds);
    fragment.appendChild(card);
  });

  gridEl.appendChild(fragment);
}

async function joinDuoPost(postId, event) {
  if (event) event.stopPropagation();
  const btn = event?.currentTarget || document.querySelector(`.duo-post-card[data-post-id="${postId}"] .btn-duo-join`);
  if (btn) {
    if (btn.disabled || btn.getAttribute("data-busy") === "1") return;
    btn.setAttribute("data-busy", "1");
    btn.disabled = true;
  }

  try {
    const res = await fetch(`/api/duo-posts/${postId}/join`, {
      method: "POST"
    });

    if (res.ok) {
      const data = await res.json();
      if (data.status === "ok" || data.status === "already") {
        addDuoJoinedPost(postId);
      }
      if (data.status === "already") {
        showToast("이미 참가했어요", "info");
      } else {
        showToast("참가 신청되었습니다.", "success");
      }
      if (data.post) {
        updateDuoPostCard(data.post);
      } else {
        loadDuoPosts();
      }
    } else if (res.status === 401) {
      const err = await res.json().catch(() => ({}));
      showToast(err.detail || "로그인이 필요합니다.", "warning");
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("data-busy");
      }
    } else if (res.status === 409) {
      showToast("마감된 글이에요", "warning");
      const existingCard = document.querySelector(`.duo-post-card[data-post-id="${postId}"]`);
      if (existingCard) {
        existingCard.classList.remove("is-room-open");
        existingCard.classList.add("is-room-full");
        const b = existingCard.querySelector(".btn-duo-join");
        if (b && !b.classList.contains("btn-duo-joined")) {
          b.disabled = true;
          b.classList.add("btn-duo-join-closed");
          b.innerHTML = '<i class="fa-solid fa-hand"></i> 마감';
          b.title = "현재 모집이 마감된 글입니다.";
        }
        const capPill = existingCard.querySelector(".dp-capacity-pill");
        if (capPill) {
          capPill.className = "dp-capacity-pill full";
          capPill.title = "방 인원이 정원초과되어 입장이 마감되었습니다.";
          capPill.innerHTML = '<i class="fa-solid fa-lock"></i> 정원 마감';
        }
      }
      if (btn) {
        btn.removeAttribute("data-busy");
      }
    } else if (res.status === 429) {
      const err = await res.json().catch(() => ({}));
      showToast(err.detail || "요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.", "warning");
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("data-busy");
      }
    } else {
      const err = await res.json().catch(() => ({}));
      const detail = Array.isArray(err.detail) ? "입력값을 확인해주세요." : (err.detail || "참가 신청에 실패했습니다.");
      showToast(detail, "error");
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("data-busy");
      }
    }
  } catch (err) {
    console.error("Join duo post failed:", err);
    showToast("참가 처리 중 통신 오류가 발생했습니다.", "error");
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("data-busy");
    }
  }
}
window.joinDuoPost = joinDuoPost;

async function leaveDuoPost(postId, event) {
  if (event) event.stopPropagation();
  const btn = event?.currentTarget || document.querySelector(`.duo-post-card[data-post-id="${postId}"] .btn-duo-join`);
  if (btn) {
    if (btn.disabled || btn.getAttribute("data-busy") === "1") return;
    btn.setAttribute("data-busy", "1");
    btn.disabled = true;
  }

  try {
    const res = await fetch(`/api/duo-posts/${postId}/join`, {
      method: "DELETE"
    });

    if (res.ok) {
      const data = await res.json();
      if (data.status === "ok" || data.status === "not_joined") {
        removeDuoJoinedPost(postId);
      }
      showToast("참가를 취소했어요", "info");
      if (data.post) {
        updateDuoPostCard(data.post);
      } else {
        loadDuoPosts();
      }
    } else if (res.status === 401) {
      const err = await res.json().catch(() => ({}));
      showToast(err.detail || "로그인이 필요합니다.", "warning");
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("data-busy");
      }
    } else if (res.status === 429) {
      const err = await res.json().catch(() => ({}));
      showToast(err.detail || "요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.", "warning");
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("data-busy");
      }
    } else {
      const err = await res.json().catch(() => ({}));
      const detail = Array.isArray(err.detail) ? "입력값을 확인해주세요." : (err.detail || "참가 취소에 실패했습니다.");
      showToast(detail, "error");
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("data-busy");
      }
    }
  } catch (err) {
    console.error("Leave duo post failed:", err);
    showToast("참가 취소 중 통신 오류가 발생했습니다.", "error");
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("data-busy");
    }
  }
}
window.leaveDuoPost = leaveDuoPost;

function updateDuoPostCard(p) {
  if (!p || p.id == null) return;
  const existingCard = document.querySelector(`.duo-post-card[data-post-id="${p.id}"]`);
  if (!existingCard) return;
  const ownedPostIds = getDuoOwnerTokens();
  const newCard = createDuoCardElement(p, ownedPostIds);
  existingCard.replaceWith(newCard);
}
window.updateDuoPostCard = updateDuoPostCard;

function createDuoCardElement(p, ownedPostIds) {
  if (!ownedPostIds) ownedPostIds = getDuoOwnerTokens();
  const isFull = isDuoRoomFull(p);
  const isOwner = Boolean(ownedPostIds && ownedPostIds[p.id]);
  const isJoined = isDuoPostJoined(p.id);
  const maxMembers = p.max_members || (p.queue_type === "자유랭크" || p.queue_type === "칼바람 나락" ? 5 : 2);
  const curMembers = p.current_members ?? (isFull ? maxMembers : 1);

  const card = document.createElement("div");
  card.className = "duo-post-card " + (isFull ? "is-room-full" : "is-room-open");
  card.setAttribute("data-post-id", String(p.id));

  const discordVal = p.discord_tag || (p.tag_line ? `${p.game_name}#${p.tag_line}` : p.game_name);
  const roomName = p.room_name || p.discord_channel_name || (p.voice ? `🔊 ${p.game_name}의 음성방` : "음성 미사용");
  const voiceUrl = [p.room_link, p.discord_voice_url].find(isRealDuoLink) || "";
  const inviteUrl = isRealDuoLink(p.discord_invite_url) ? p.discord_invite_url : (voiceUrl.startsWith("http") ? voiceUrl : "");
  const hasJoinLink = Boolean(voiceUrl || inviteUrl);
  const roomStatus = p.room_status || (isFull ? `🔴 정원 마감 (${curMembers}/${maxMembers}명)` : (p.voice ? `🟢 대기 중 (${curMembers}/${maxMembers}명)` : "마이크 OFF"));
  const tierEmblemUrl = p.tier_emblem || (typeof getTierCrestEmblemUrl === "function" ? getTierCrestEmblemUrl(p.tier || "DIAMOND") : `/static/images/tiers/${(p.tier || "iron").toLowerCase()}.png`);

  let queueClass = "solo";
  let queueIcon = "fa-trophy";
  if (p.queue_type) {
    if (p.queue_type.includes("자유") || p.queue_type.includes("스쿼드")) {
      queueClass = "flex";
      queueIcon = "fa-users";
    } else if (p.queue_type.includes("칼바람")) {
      queueClass = "aram";
      queueIcon = "fa-snowflake";
    }
  }

  const champDetails = p.champion_details || (p.most_champions || []).map(c => ({
    name: c,
    image: typeof normalizeChampionImgUrl === "function" ? normalizeChampionImgUrl(c) : `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/${c}.png`
  }));

  const champChipsHtml = (p.game === "lol" || !p.game) ? champDetails.map(c => `
    <div class="dp-champ-chip" onclick="openChampionBuildModal(${jsArg(c.name)})" title="${escapeHtml(c.name)} 추천 룬/빌드 열기 (1클릭 복사)">
      <img class="dp-champ-chip-img" src="${escapeHtml(c.image)}" alt="${escapeHtml(c.name)}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
      <span class="dp-champ-chip-name">${escapeHtml(c.name)}</span>
    </div>
  `).join('') : '';

  const synergyBadgeHtml = p.synergy_badge
    ? `<div class="dp-synergy-wrap"><span class="dp-synergy-pill" title="${escapeHtml(p.synergy_desc || '')}"><i class="fa-solid fa-bolt"></i> ${escapeHtml(p.synergy_badge)}</span></div>`
    : '';

  const capacityPillHtml = isFull
    ? `<span class="dp-capacity-pill full" title="방 인원이 정원초과되어 입장이 마감되었습니다."><i class="fa-solid fa-lock"></i> 정원 마감 (${curMembers}/${maxMembers}명)</span>`
    : `<span class="dp-capacity-pill open" title="방 인원이 정원 미달로 즉시 입장 가능합니다."><span class="voice-pulse-dot" style="width: 6px; height: 6px; background: #10B981;"></span> 대기 중 (${curMembers}/${maxMembers}명)</span>`;

  const hasPositions = (p.game !== "pubg") && (p.my_position && p.my_position !== "ALL" || p.target_position && p.target_position !== "ALL" || p.game === "lol");

  const joinersList = (Array.isArray(p.joiner_names) ? p.joiner_names : []).map(j => escapeHtml(String(j).trim())).filter(Boolean);
  const joinersHtml = joinersList.length > 0
    ? `<div class="dp-joiners-bar" title="참가: ${joinersList.join(', ')}"><i class="fa-solid fa-hand" style="color: #10B981; font-size: 0.74rem;"></i> <span class="dp-joiners-text">참가: ${joinersList.join(', ')}</span></div>`
    : '';

  let joinBtnHtml = '';
  if (!isOwner) {
    if (isJoined) {
      joinBtnHtml = `
        <button type="button" class="btn-duo-join btn-duo-joined" data-post-id="${Number(p.id)}" title="참가를 취소합니다." style="flex: 0.85; height: 38px;" onclick="leaveDuoPost(${Number(p.id)}, event)">
          <span class="duo-joined-label">참가함 ✓</span>
          <span class="duo-leave-label"><i class="fa-solid fa-xmark"></i> 취소</span>
        </button>
      `;
    } else if (isFull) {
      joinBtnHtml = `
        <button type="button" class="btn-duo-join btn-duo-join-closed" disabled role="button" aria-disabled="true" title="현재 모집이 마감된 글입니다." style="flex: 0.85; height: 38px;">
          <i class="fa-solid fa-hand"></i> 마감
        </button>
      `;
    } else {
      joinBtnHtml = `
        <button type="button" class="btn-duo-join" data-post-id="${Number(p.id)}" title="구인 글에 참가 신청합니다." style="flex: 0.85; height: 38px;" onclick="joinDuoPost(${Number(p.id)}, event)">
          <i class="fa-solid fa-hand"></i> 같이해요
        </button>
      `;
    }
  }

  card.innerHTML = `
    <div class="dp-card-top">
      <div class="dp-author-wrap dp-summoner-chip" data-gn="${escapeHtml(p.game_name)}" data-tag="${escapeHtml(p.tag_line || 'KR1')}" title="${escapeHtml(p.game_name)} 상세 전적 열기">
        ${(p.game || "lol") === "lol" ? `<img class="dp-tier-crest" src="${tierEmblemUrl}" alt="" onerror="this.style.display='none'">` : `<span class="dp-tier-text">${escapeHtml(p.tier_kr || "")}</span>`}
        <div>
          <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
            <span class="dp-author-name" data-gn="${escapeHtml(p.game_name)}" data-tag="${escapeHtml(p.tag_line || 'KR1')}">${escapeHtml(p.game_name)}</span>
            ${p.tag_line ? `<span class="dp-author-tag">#${escapeHtml(p.tag_line)}</span>` : ''}
            ${p.author ? `
              <span class="dp-discord-author" title="디스코드: ${escapeHtml(p.author)}">
                <i class="fa-brands fa-discord"></i>
                <span class="dp-discord-author-name">${escapeHtml(p.author)}</span>
              </span>
            ` : ''}
            ${capacityPillHtml}
          </div>
          <div style="display: flex; align-items: center; gap: 4px; margin-top: 2px;">
            <span class="dp-tier-pill tier-${(p.tier || 'DIAMOND').toLowerCase()}">${escapeHtml(p.tier_kr || p.tier || '다이아몬드')}</span>
            <span class="dp-queue-chip ${queueClass}"><i class="fa-solid ${queueIcon}"></i> ${escapeHtml(p.queue_type || '솔로랭크')}</span>
          </div>
        </div>
      </div>
      <span class="dp-time">${escapeHtml(p.created_at || '방금 전')}</span>
    </div>

    ${synergyBadgeHtml}

    <div class="dp-positions-bar">
      ${hasPositions ? `
        <div class="dp-pos-flow">
          <span class="dp-pos-badge pos-${(p.my_position||'').toLowerCase()} my" title="작성자 포지션: ${getDuoPosNameKr(p.my_position, p.game)}">
            ${getDuoPosIcon(p.my_position)} 나: ${getDuoPosNameKr(p.my_position, p.game)}
          </span>
          <i class="fa-solid fa-arrow-right-long dp-pos-arrow"></i>
          <span class="dp-pos-badge pos-${(p.target_position||'').toLowerCase()} target" title="찾는 포지션: ${getDuoPosNameKr(p.target_position, p.game)}">
            ${getDuoPosIcon(p.target_position)} 찾음: ${getDuoPosNameKr(p.target_position, p.game)}
          </span>
        </div>
      ` : '<div></div>'}
      ${isFull ? `
        <div class="host-room-status-badge room-full-badge" title="현재 방 인원이 정원초과되어 입장이 마감되었습니다 (하단 배치)">
          <i class="fa-solid fa-ban" style="color: #EF4444;"></i>
          <span style="color: #EF4444; font-weight: 800; font-size: 0.74rem;">🔴 정원 초과 <span class="host-room-count">(${curMembers}/${maxMembers}명)</span></span>
        </div>
      ` : (p.voice ? `
        <div class="host-room-status-badge voice-filter-badge on" title="음성 통화 ON">
          <span class="voice-pulse-dot"></span>
          <span class="host-room-status-text">마이크 ON</span>
          <span class="mic-active-glow" title="마이크 ON">
            <i class="fa-solid fa-microphone"></i>
            <span>ON</span>
          </span>
        </div>
      ` : `
        <div class="dp-voice-status voice-off" title="마이크 미사용">
          <i class="fa-solid fa-microphone-slash"></i> <span>마이크 OFF</span>
        </div>
      `)}
    </div>

    ${isFull ? `
      <div class="dp-room-bar room-full-bar" style="display: flex; align-items: center; justify-content: space-between; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 7px; padding: 7px 10px; margin: 8px 0; font-size: 0.77rem;">
        <span style="font-weight: 700; color: #FCA5A5; display: flex; align-items: center; gap: 6px;">
          <i class="fa-solid fa-lock"></i> ${escapeHtml(roomName)}
        </span>
        <span style="color: #EF4444; font-weight: 800; display: flex; align-items: center; gap: 5px; font-size: 0.74rem;">
          <i class="fa-solid fa-ban"></i> 정원 마감 (${curMembers}/${maxMembers}명)
        </span>
      </div>
    ` : (p.voice && hasJoinLink ? `
      <div class="dp-room-bar" style="display: flex; align-items: center; justify-content: space-between; background: rgba(88, 101, 242, 0.12); border: 1px solid rgba(88, 101, 242, 0.35); border-radius: 7px; padding: 7px 10px; margin: 8px 0; font-size: 0.77rem;">
        <span style="font-weight: 700; color: #7983F5; display: flex; align-items: center; gap: 6px;">
          <i class="fa-solid fa-headset"></i> ${escapeHtml(roomName)}
        </span>
        <span style="color: #10B981; font-weight: 800; display: flex; align-items: center; gap: 5px; font-size: 0.74rem;">
          <span class="voice-pulse-dot" style="width: 7px; height: 7px;"></span> ${escapeHtml(roomStatus)}
        </span>
      </div>
    ` : '')}

    <div class="dp-title">${escapeHtml(p.title || '')}</div>
    <div class="dp-desc">${escapeHtml(p.description || '')}</div>

    ${(p.game === "pubg" && getGameConfig("pubg")?.has_stats && p.game_name) ? `
      <div class="pg-stats-wrap">
        <button type="button" class="pg-stats-btn" data-pg-name="${escapeHtml(p.game_name)}" aria-expanded="false">
          <i class="fa-solid fa-chart-simple"></i> 전적
        </button>
        <div class="pg-stats-panel" hidden></div>
      </div>
    ` : ''}

    ${champChipsHtml ? `
      <div class="dp-champs-section">
        <span class="dp-champs-lbl"><i class="fa-solid fa-shield-cat"></i> 주챔피언:</span>
        <div class="dp-champs-chips-wrap">
          ${champChipsHtml}
        </div>
      </div>
    ` : ''}

    ${joinersHtml}

    <div class="dp-card-footer">
      <div class="dp-footer-actions" style="display: flex; align-items: center; gap: 8px; width: 100%;">
        ${isFull ? `
          <button class="btn-host-room-join btn-room-full-btn" disabled role="button" aria-disabled="true" title="현재 방 인원이 정원초과되어 입장이 마감되었습니다. (하단 정렬)" style="flex: ${isOwner ? '2' : '1.5'}; height: 38px;">
            <i class="fa-solid fa-lock"></i>
            <span class="btn-host-room-title">정원 초과 (입장 마감)</span>
          </button>
        ` : (p.voice && hasJoinLink ? `
          <button class="btn-host-room-join btn-discord-direct-join btn-join-voice esports-discord-btn" data-voice-url="${escapeHtml(voiceUrl)}" data-invite-url="${escapeHtml(inviteUrl)}" data-channel-name="${escapeHtml(roomName)}" data-tag="${escapeHtml(discordVal)}" data-host-name="${escapeHtml(p.game_name)}" data-post-id="${escapeHtml(p.id != null ? String(p.id) : '')}" role="button" aria-label="디스코드 음성방 참가" title="[🎧 호스트 대기방 입장] ${escapeHtml(roomName)}" style="flex: ${isOwner ? '2' : '1.5'}; height: 38px;">
            <span class="voice-pulse-dot"></span>
            <i class="fa-brands fa-discord" style="font-size: 1.05rem;"></i>
            <span class="btn-host-room-title">디스코드 1-클릭 음성방 참가</span>
          </button>
        ` : (p.voice ? `
          <div style="flex: ${isOwner ? '2' : '1.5'}; display: flex; align-items: center; justify-content: center; gap: 6px; background: rgba(88, 101, 242, 0.08); border: 1px solid var(--border-color); border-radius: 8px; height: 38px; font-size: 0.78rem; color: var(--text-muted); font-weight: 600; overflow: hidden;" title="디스코드 태그로 연락하세요.">
            <i class="fa-brands fa-discord"></i> <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(discordVal)}</span>
          </div>
        ` : `
          <div style="flex: ${isOwner ? '2' : '1.5'}; display: flex; align-items: center; justify-content: center; gap: 6px; background: rgba(255,255,255,0.04); border: 1px solid var(--border-color); border-radius: 8px; height: 38px; font-size: 0.78rem; color: var(--text-muted); font-weight: 600;">
            <i class="fa-solid fa-microphone-slash"></i> <span>음성 채팅 미사용 (텍스트 매칭)</span>
          </div>
        `))}
        ${joinBtnHtml}
        ${(p.game === "lol" || !p.game) ? `
          <button class="btn-secondary btn-view-profile" data-gn="${escapeHtml(p.game_name)}" data-tag="${escapeHtml(p.tag_line || 'KR1')}" style="flex: 0.65; height: 38px; padding: 6px 10px; font-size: 0.78rem; font-weight: 700;">
            <i class="fa-solid fa-chart-simple"></i> 전적
          </button>
        ` : ''}
        ${isOwner ? `<button class="btn-secondary btn-toggle-duo-cap ${isFull ? 'cap-open-act' : 'cap-full-act'}" data-post-id="${Number(p.id)}" title="${isFull ? '입장 가능 상태로 전환하여 상단으로 이동' : '정원 마감 상태로 전환하여 하단으로 이동'}" style="flex: 0.55; height: 38px; padding: 0 8px; display: inline-flex; align-items: center; justify-content: center; gap: 4px; font-size: 0.76rem; font-weight: 700;" onclick="toggleDuoRoomCapacity(${Number(p.id)}, event)">
          ${isFull ? '<i class="fa-solid fa-lock-open" style="color: #10B981;"></i> 열기' : '<i class="fa-solid fa-lock" style="color: #EF4444;"></i> 마감'}
        </button>
        <button class="btn-secondary btn-delete-duo" title="글 삭제" style="flex: 0 0 38px; height: 38px; padding: 0;" onclick="deleteDuoPost(${Number(p.id)}, event)"><i class="fa-solid fa-trash-can"></i></button>` : ''}
      </div>
    </div>
  `;

  // Event listeners
  const authorWrap = card.querySelector(".dp-author-wrap");
  const nameEl = card.querySelector(".dp-author-name");
  const viewBtn = card.querySelector(".btn-view-profile");
  const joinVoiceBtn = card.querySelector(".btn-host-room-join.btn-discord-direct-join");
  const joinBtn = card.querySelector(".btn-duo-join:not(:disabled)");

  const goProfile = (e) => {
    if (e) e.stopPropagation();
    if (p.game !== "lol" && p.game) return;
    if (typeof openPlayerDetail === "function") {
      openPlayerDetail({ game_name: p.game_name, tag_line: p.tag_line || "KR1" });
    } else if (typeof performSearch === "function") {
      performSearch(`${p.game_name}#${p.tag_line || "KR1"}`);
    }
  };
  if (p.game === "lol" || !p.game) {
    authorWrap?.addEventListener("click", goProfile);
    nameEl?.addEventListener("click", goProfile);
    viewBtn?.addEventListener("click", goProfile);
  } else {
    authorWrap?.style.setProperty("cursor", "default");
    nameEl?.style.setProperty("cursor", "default");
  }

  joinVoiceBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    const vUrl = joinVoiceBtn.getAttribute("data-voice-url") || "";
    const invUrl = joinVoiceBtn.getAttribute("data-invite-url") || "";
    const chName = joinVoiceBtn.getAttribute("data-channel-name") || "호스트 음성 대기방";
    const tag = joinVoiceBtn.getAttribute("data-tag") || "";
    const hName = joinVoiceBtn.getAttribute("data-host-name") || p.game_name || "호스트";
    const pId = joinVoiceBtn.getAttribute("data-post-id") || p.id || "";
    joinDiscordVoiceRoom(vUrl, invUrl, chName, tag, hName, pId);
  });

  joinBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    if (joinBtn.classList.contains("btn-duo-joined")) {
      leaveDuoPost(Number(p.id), e);
    } else {
      joinDuoPost(Number(p.id), e);
    }
  });

  card.querySelector(".pg-stats-btn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    togglePubgStats(e.currentTarget);
  });

  return card;
}

// 배그 글 '전적': PUBG 공식 API (서버에 PUBG_API_KEY 가 있을 때만 버튼이 보임). 카카오 → 없으면 스팀. 같은 페이지에서는 다시 부르지 않음
const pubgStatsMemo = {};

async function fetchPubgStats(name) {
  if (pubgStatsMemo[name]) return pubgStatsMemo[name];
  let last = null;
  for (const platform of ["kakao", "steam"]) {
    const res = await fetch(`/api/pubg/player?name=${encodeURIComponent(name)}&platform=${platform}`);
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      pubgStatsMemo[name] = { ok: true, data };
      return pubgStatsMemo[name];
    }
    last = { ok: false, detail: res.status === 422 ? "조회할 수 없는 닉네임이에요." : (typeof data.detail === "string" ? data.detail : "조회하지 못했어요.") };
    if (res.status !== 404) break;
  }
  if (last && /찾을 수 없/.test(last.detail)) pubgStatsMemo[name] = last;
  return last;
}

function renderPubgStats(panel, result) {
  if (!result.ok) {
    panel.innerHTML = `<div class="pg-stats-msg">${escapeHtml(result.detail)}</div>`;
    return;
  }
  const d = result.data || {};
  const r = d.ranked;
  const src = `<div class="pg-stats-src">PUBG 공식 API · ${d.platform === "steam" ? "스팀" : "카카오"}</div>`;
  if (!r) {
    panel.innerHTML = `<div class="pg-stats-msg">이번 시즌 경쟁전 기록 없음</div>${src}`;
    return;
  }
  const cell = (label, value) => value == null ? "" :
    `<div class="pg-stat"><span class="pg-stat-label">${label}</span><span class="pg-stat-value">${escapeHtml(String(value))}</span></div>`;
  panel.innerHTML = `
    <div class="pg-stats-grid">
      ${cell("티어", [r.tier, r.sub_tier].filter(Boolean).join(" ") || "-")}
      ${cell("RP", r.rank_point)}
      ${cell("판수", r.rounds != null ? `${r.rounds}판 · ${r.wins || 0}승` : null)}
      ${cell("KDA", typeof r.kda === "number" ? r.kda.toFixed(2) : null)}
      ${cell("평균 딜량", typeof r.avg_damage === "number" ? r.avg_damage.toLocaleString() : null)}
      ${cell("TOP10", typeof r.top10_ratio === "number" ? `${(r.top10_ratio * 100).toFixed(1)}%` : null)}
    </div>${src}`;
}

async function togglePubgStats(btn) {
  const panel = btn.parentElement?.querySelector(".pg-stats-panel");
  if (!panel) return;
  if (!panel.hidden) {
    panel.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    return;
  }
  panel.hidden = false;
  btn.setAttribute("aria-expanded", "true");
  const name = btn.getAttribute("data-pg-name") || "";
  if (!pubgStatsMemo[name]) panel.innerHTML = '<div class="pg-stats-msg"><i class="fa-solid fa-spinner fa-spin"></i> 불러오는 중...</div>';
  try {
    renderPubgStats(panel, await fetchPubgStats(name));
  } catch (_) {
    renderPubgStats(panel, { ok: false, detail: "서버에 연결하지 못했어요." });
  }
}

function openPlayerModal(gameName, tagLine) {
  if (typeof openPlayerDetail === "function") {
    openPlayerDetail({ game_name: gameName, tag_line: tagLine || "KR1" });
  } else if (typeof performSearch === "function") {
    performSearch(`${gameName}#${tagLine || "KR1"}`);
  }
}
window.openPlayerModal = openPlayerModal;
