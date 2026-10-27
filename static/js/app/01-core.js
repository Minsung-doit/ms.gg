// 디스코드 멤버 로그인이 만료되면(API 401 + login_url) 로그인 화면으로 보낸다
(function () {
  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await originalFetch.apply(this, args);
    if (res.status === 401) {
      try {
        const body = await res.clone().json();
        if (body && body.login_url) {
          location.href = `${body.login_url}?next=${encodeURIComponent(location.pathname + location.search)}`;
        }
      } catch (e) {}
    }
    return res;
  };
})();

// carry.gg Frontend Application

const DDRAGON_VER = "__DDRAGON_VER__";
const ICON_BASE_URL = `https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VER}/img/profileicon/`;

// DOM Elements
const searchForm = document.getElementById("searchForm");
const searchInput = document.getElementById("searchInput");
const resultsHeader = document.getElementById("resultsHeader");
const searchKeyword = document.getElementById("searchKeyword");
const resultCountBadge = document.getElementById("resultCountBadge");
const playerList = document.getElementById("playerList");
const loadingState = document.getElementById("loadingState");
const emptyState = document.getElementById("emptyState");
const autocompleteDropdown = document.getElementById("autocompleteDropdown");
const btnViewCompact = document.getElementById("btnViewCompact");
const btnViewCard = document.getElementById("btnViewCard");

// Modal & API Key Elements
const apiKeyModal = document.getElementById("apiKeyModal");
const btnOpenApiKeyModal = document.getElementById("btnOpenApiKeyModal");
const btnCloseModal = document.getElementById("btnCloseModal");
const btnCancelModal = document.getElementById("btnCancelModal");
const btnSaveApiKey = document.getElementById("btnSaveApiKey");
const apiKeyInput = document.getElementById("apiKeyInput");
const keyStatusDot = document.getElementById("keyStatusDot");
const keyButtonText = document.getElementById("keyButtonText");

// Player Detail Modal Elements
const playerDetailModal = document.getElementById("playerDetailModal");
const playerDetailContent = document.getElementById("playerDetailContent");
const btnCloseDetailModal = document.getElementById("btnCloseDetailModal");
const btnCloseDetailModal2 = document.getElementById("btnCloseDetailModal2");
const btnRefreshPlayer = document.getElementById("btnRefreshPlayer");

const toast = document.getElementById("toast");

let currentDetailPlayer = null;

// Enhanced Toast Helper (Supports Success, Error, Warning, Info with Icons & Hextech Styling)
let toastTimer = null;
function showToast(message, type = "info", duration = 3000) {
  if (typeof type === "number") {
    duration = type;
    type = "info";
  }
  const toastEl = toast || document.getElementById("toast");
  if (!toastEl) return;
  if (toastTimer) clearTimeout(toastTimer);

  let iconHtml = '<i class="fa-solid fa-circle-info toast-icon" style="color: #60A5FA;"></i>';
  if (type === "success") {
    iconHtml = '<i class="fa-solid fa-circle-check toast-icon" style="color: #10B981;"></i>';
  } else if (type === "error") {
    iconHtml = '<i class="fa-solid fa-circle-exclamation toast-icon" style="color: #EF4444;"></i>';
  } else if (type === "warning") {
    iconHtml = '<i class="fa-solid fa-triangle-exclamation toast-icon" style="color: #F59E0B;"></i>';
  }

  toastEl.innerHTML = `${iconHtml}<span class="toast-message-text" style="flex: 1;"></span><button type="button" class="toast-close" title="닫기" onclick="this.parentElement.classList.remove('show');"><i class="fa-solid fa-xmark"></i></button>`;
  // 메시지에는 소환사명·서버 오류 문구가 들어가므로 HTML이 아닌 텍스트로 넣는다
  toastEl.querySelector(".toast-message-text").textContent = message == null ? "" : String(message);
  toastEl.className = `toast toast-${type} show`;

  toastTimer = setTimeout(() => {
    toastEl.classList.remove("show");
  }, duration);
}

// Format Numbers
function formatNumber(num) {
  return new Intl.NumberFormat("ko-KR").format(num || 0);
}

// Save API Key Helper
async function saveApiKeyDirectly(key) {
  try {
    const res = await fetch("/api/settings/api-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key })
    });
    const data = await res.json();
    if (res.ok) {
      if (keyStatusDot) keyStatusDot.className = "key-status-dot active";
      if (keyButtonText) keyButtonText.textContent = "API 키 등록됨";
      if (apiKeyInput) apiKeyInput.value = "";
      if (searchInput.value.trim()) {
        performSearch(searchInput.value.trim());
      }
    } else {
      showToast(data.detail || "API Key 등록 실패");
    }
  } catch (err) {
    showToast("API Key 등록 중 오류가 발생했습니다.");
  }
}

// Search Function
async function performSearch(query) {
  if (!query || !query.trim()) return;
  closeAutocomplete();

  const trimmed = query.trim();

  // 사용자가 검색창에 API Key를 직접 입력한 경우 자동 감지 및 등록!
  if (trimmed.startsWith("RGAPI-")) {
    await saveApiKeyDirectly(trimmed);
    return;
  }

  // [자동 연동] 픽창 복사 텍스트 또는 쉼표 다중 소환사명 감지 시 멀티서치로 자동 전환
  if (trimmed.includes("님이 로비에") || trimmed.includes("joined the lobby") || trimmed.includes("님이 방에") || trimmed.includes("대기실에") || (trimmed.includes(",") && trimmed.split(",").length >= 2) || trimmed.includes("\n")) {
    switchMainTab("multisearch");
    const msTextarea = document.getElementById("multiSearchTextarea");
    if (msTextarea) {
      msTextarea.value = trimmed;
      runMultiSearch(trimmed);
    }
    return;
  }

  searchInput.value = trimmed;

  // UI State: Loading
  const champArea = document.getElementById("championAnalyticsArea");
  if (champArea) champArea.style.display = "none";
  const homeTrending = document.getElementById("homeTrendingSection");
  if (homeTrending) homeTrending.style.display = "none";
  playerList.innerHTML = "";
  emptyState.style.display = "none";
  loadingState.style.display = "block";
  resultsHeader.style.display = "none";

  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(trimmed)}`);
    const data = await res.json();

    loadingState.style.display = "none";

    if (!res.ok) {
      if (emptyState) {
        emptyState.style.display = "block";
        emptyState.innerHTML = `
          <div class="state-icon" style="color: #F59E0B;"><i class="fa-solid fa-triangle-exclamation"></i></div>
          <div class="state-title">검색 서버와 일시적으로 통신할 수 없습니다</div>
          <div class="state-desc" style="margin-bottom: 1rem;">
            ${escapeHtml(data.detail || "서버 통신 중 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")}
          </div>
          <button type="button" class="btn-hextech" onclick="performSearch(${jsArg(trimmed)})" style="padding: 8px 18px; border-radius: var(--radius-md); background: var(--bg-surface); color: var(--text-primary); border: 1px solid var(--border-color); cursor: pointer;">
            <i class="fa-solid fa-rotate-right"></i> 다시 시도
          </button>
        `;
      }
      if (emptyState) emptyState.scrollIntoView({ behavior: "smooth", block: "center" });
      showToast(data.detail || "검색 중 오류가 발생했습니다.", "error");
      return;
    }

    if (data.mode === "matchup_1v1") {
      // 1:1 챔피언 상성 매치업 자동 라우팅 및 분석 페이지 즉각 표출
      if (typeof openMatchupWithChampions === "function") {
        openMatchupWithChampions(data.champ1.name, data.champ2.name);
      } else {
        switchMainTab("matchup");
        const c1Inp = document.getElementById("matchupChamp1Input");
        const c2Inp = document.getElementById("matchupChamp2Input");
        if (c1Inp && data.champ1) c1Inp.value = data.champ1.name;
        if (c2Inp && data.champ2) c2Inp.value = data.champ2.name;
        if (typeof performMatchupCompare === "function") {
          performMatchupCompare(data.champ1.name, data.champ2.name);
        }
      }
      if (typeof updateSkyscraperPosition === "function") setTimeout(updateSkyscraperPosition, 100);
      return;
    }

    if (data.mode === "champion_build" && data.champion) {
      // 챔피언 이름 검색: 실데이터 빌드 창을 연다
      if (homeTrending) homeTrending.style.display = "block";
      loadChampionAnalytics(data.champion.id);
      return;
    }

    if (data.mode === "exact") {
      // 단일 소환사 결과
      resultsHeader.style.display = "flex";
      searchKeyword.textContent = `'${trimmed}'`;
      resultCountBadge.textContent = "1";
      if (typeof addRecentSearch === "function") {
        addRecentSearch(data.player.game_name, data.player.tag_line, data.player.tier);
      }
      renderPlayers([data.player]);
      resultsHeader.scrollIntoView({ behavior: "smooth", block: "start" });
      // 방금 라이엇에서 받은 프로필을 재사용해 모달을 열 때 API를 다시 호출하지 않는다
      playerProfileCache.set(getPlayerCacheKey(data.player.game_name, data.player.tag_line), data.player);
      if (typeof openPlayerDetail === "function") {
        openPlayerDetail(data.player);
      }
      if (typeof updateSkyscraperPosition === "function") setTimeout(updateSkyscraperPosition, 100);
    } else {
      // 동명인 검색 결과
      const count = data.count || 0;
      if (count === 0) {
        if (emptyState) {
          emptyState.style.display = "block";
          emptyState.innerHTML = `
            <div class="state-icon" style="color: var(--color-gold);"><i class="fa-solid fa-compass"></i></div>
            <div class="state-title">${data.reason_code === 503 ? "지금은 라이엇 API에서 소환사 정보를 가져올 수 없습니다" : "소환사를 찾을 수 없습니다"}</div>
            <div class="state-desc">
              ${data.detail ? `${escapeHtml(data.detail)}<br>` : ""}
              ${data.reason_code === 503 ? "" : `• Riot ID의 이름과 태그(예: <code>소환사명#KR1</code>)가 정확한지 확인해주세요.<br>
              • 최근 닉네임을 변경하셨다면 변경된 소환사명을 입력해주세요.`}
            </div>
          `;
          emptyState.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        return;
      }

      resultsHeader.style.display = "flex";
      searchKeyword.textContent = `'${trimmed}'`;
      resultCountBadge.textContent = count;

      if (typeof addRecentSearch === "function" && data.results && data.results.length > 0) {
        addRecentSearch(data.results[0].game_name, data.results[0].tag_line, data.results[0].tier);
      }
      renderPlayers(data.results);
      resultsHeader.scrollIntoView({ behavior: "smooth", block: "start" });
      if (typeof updateSkyscraperPosition === "function") setTimeout(updateSkyscraperPosition, 100);
    }
  } catch (err) {
    if (loadingState) loadingState.style.display = "none";
    if (emptyState) {
      emptyState.style.display = "block";
      emptyState.innerHTML = `
        <div class="state-icon" style="color: #F59E0B;"><i class="fa-solid fa-triangle-exclamation"></i></div>
        <div class="state-title">검색 서버와 일시적으로 통신할 수 없습니다</div>
        <div class="state-desc" style="margin-bottom: 1rem;">
          네트워크 연결을 확인하거나 아래 [다시 시도] 버튼을 눌러주세요.
        </div>
        <button type="button" class="btn-hextech" onclick="performSearch(${jsArg(trimmed)})" style="padding: 8px 18px; border-radius: var(--radius-md); background: var(--bg-surface); color: var(--text-primary); border: 1px solid var(--border-color); cursor: pointer;">
          <i class="fa-solid fa-rotate-right"></i> 다시 시도
        </button>
      `;
    }
    showToast("검색 서버와 일시적으로 통신할 수 없습니다.", "error");
  }
}

// Render Players List (페이지 넘김 없이 전원 스크롤 렌더링)
function renderPlayers(players) {
  playerList.innerHTML = "";
  const fragment = document.createDocumentFragment();

  players.forEach((player, index) => {
    const card = document.createElement("div");
    card.className = "player-card";
    card.setAttribute("data-tier", player.tier);

    const isUnranked = player.tier === "UNRANKED";
    const meta = player.tier_meta || { kr_name: player.tier, colors: {} };
    const tierColor = isUnranked ? "#64748B" : (meta.colors?.border || "#495057");
    const tierText = isUnranked ? "미배치" : (player.display_tier || player.tier);
    const lpText = isUnranked ? `소환사 레벨 Lv.${player.summoner_level}` : `${formatNumber(player.league_points)} LP`;
    const iconUrl = `${ICON_BASE_URL}${player.profile_icon_id || 29}.png`;

    const topRankClass = index === 0 ? "top-1" : index === 1 ? "top-2" : index === 2 ? "top-3" : "";

    card.innerHTML = `
      <div class="card-left">
        <div class="rank-index ${topRankClass}">#${index + 1}</div>
        <div class="profile-wrapper">
          <img 
            class="profile-icon" 
            src="${iconUrl}" 
            alt="${escapeHtml(player.game_name)}"
            onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/29.png'"
          >
          <div class="level-badge">Lv.${player.summoner_level}</div>
        </div>
        <div class="player-identity">
          <div class="riot-id-display">
            <span class="game-name">${escapeHtml(player.game_name)}</span>
            <span class="tag-line">#${escapeHtml(player.tag_line)}</span>
          </div>
          <div class="queue-type-badge">
            <i class="fa-solid fa-gamepad"></i> ${isUnranked ? "미배치 계정" : (player.queue_type === "RANKED_SOLO_5x5" ? "솔로랭크" : "자유랭크")}
          </div>
        </div>
      </div>

      <div class="card-right">
        <div class="tier-display-box">
          <div class="tier-badge" style="color: ${tierColor};">
            <img class="tier-emblem-img" src="${getTierEmblemUrl(player.tier || tierText)}" alt="${tierText}" onerror="this.style.display='none';">
            <span>${tierText}</span>
          </div>
          <div class="lp-text" style="${isUnranked ? 'color: #94A3B8; font-weight: normal;' : ''}">${lpText}</div>
        </div>

        <div class="winrate-box">
          <div class="winrate-text">
            ${player.wins + player.losses > 0 ? `승률 ${player.win_rate}%` : (isUnranked ? "랭크 전적 없음" : "기록 없음")}
          </div>
          <div class="winrate-bar-container">
            <div class="winrate-bar-fill" style="width: ${player.win_rate || 0}%;"></div>
          </div>
          <div class="record-text">
            ${player.wins + player.losses > 0 ? `${player.wins}승 ${player.losses}패 (총 ${player.total_games}게임)` : `소환사 레벨 ${player.summoner_level}`}
          </div>
        </div>
      </div>
    `;

    // Click to open detail modal
    card.addEventListener("click", () => {
      openPlayerDetail(player);
    });

    fragment.appendChild(card);
  });

  playerList.appendChild(fragment);
}

// Open Player Detail Modal with Full Tier History (Daily/Weekly/Monthly) and Past Seasons Champions
let currentActiveGraphPeriod = "daily"; // 'daily', 'weekly', 'monthly'
let currentActiveSeasonId = null;
let currentDetailFullProfile = null;

function getTierColorHex(tier) {
  if (!tier) return "#94A3B8";
  const t = tier.toUpperCase();
  switch (t) {
    case "CHALLENGER": return "#00BBA3";
    case "GRANDMASTER": return "#E84057";
    case "MASTER": return "#9D00FF";
    case "DIAMOND": return "#0066FF";
    case "EMERALD": return "#00C078";
    case "PLATINUM": return "#0EA5E9";
    case "GOLD": return "#F59E0B";
    case "SILVER": return "#8D99AE";
    case "BRONZE": return "#92400E";
    case "IRON": return "#52525B";
    default: return "#64748B";
  }
}

// Authentic Riot Ranked Tier Emblem Resolver (Zero Latency Local Assets)
function getTierEmblemUrl(tier) {
  if (!tier) return "/static/images/tiers/iron.png";
  const s = String(tier).toLowerCase().trim();
  if (s.includes("challenger") || s.includes("챌린저")) return "/static/images/tiers/challenger.png";
  if (s.includes("grandmaster") || s.includes("그랜드마스터") || s.includes("그마")) return "/static/images/tiers/grandmaster.png";
  if (s.includes("master") || s.includes("마스터")) return "/static/images/tiers/master.png";
  if (s.includes("diamond") || s.includes("다이아몬드") || s.includes("다이아")) return "/static/images/tiers/diamond.png";
  if (s.includes("emerald") || s.includes("에메랄드")) return "/static/images/tiers/emerald.png";
  if (s.includes("platinum") || s.includes("플래티넘") || s.includes("플레")) return "/static/images/tiers/platinum.png";
  if (s.includes("gold") || s.includes("골드")) return "/static/images/tiers/gold.png";
  if (s.includes("silver") || s.includes("실버")) return "/static/images/tiers/silver.png";
  if (s.includes("bronze") || s.includes("브론즈")) return "/static/images/tiers/bronze.png";
  if (s.includes("iron") || s.includes("아이언")) return "/static/images/tiers/iron.png";
  return "/static/images/tiers/iron.png";
}
window.getTierEmblemUrl = getTierEmblemUrl;

// Dynamic Skyscraper Ad Margin Alignment Engine (Aligns strictly to left/right blank gutters)
function updateSkyscraperPosition() {
  const leftAd = document.getElementById("leftSkyscraperAd");
  const rightAd = document.getElementById("rightSkyscraperAd");
  if (!leftAd || !rightAd) return;

  if (window.innerWidth < 1240) {
    leftAd.style.display = "none";
    rightAd.style.display = "none";
    return;
  }

  const activeView = document.querySelector(".tab-view.active") || 
                     document.querySelector(".tab-view:not([style*='display: none'])") ||
                     document.getElementById("viewSearch");
  if (!activeView || activeView.style.display === "none") {
    leftAd.style.display = "none";
    rightAd.style.display = "none";
    return;
  }

  const candidateSelectors = [
    "#championAnalyticsArea",
    ".champ-v2-container",
    ".leaderboard-container",
    ".masters-layout-wrapper",
    ".tierlist-container",
    ".matchup-container",
    ".multisearch-container",
    ".spec-root-container",
    ".duo-finder-container",
    ".profile-container",
    ".saas-features-grid",
    ".hero-section",
    ".main-container",
    ".container"
  ];

  let minLeft = window.innerWidth;
  let maxRight = 0;
  let found = false;

  for (const sel of candidateSelectors) {
    const el = activeView.querySelector(sel);
    if (el && el.offsetWidth > 0 && el.offsetHeight > 0) {
      const style = window.getComputedStyle(el);
      if (style.display !== "none" && style.visibility !== "hidden") {
        const r = el.getBoundingClientRect();
        if (r.width > 240) {
          minLeft = Math.min(minLeft, r.left);
          maxRight = Math.max(maxRight, r.right);
          found = true;
        }
      }
    }
  }

  if (!found) {
    const r = activeView.getBoundingClientRect();
    minLeft = r.left;
    maxRight = r.right;
  }

  const winWidth = window.innerWidth;
  const adWidth = 160;
  const safetyGutter = 16;
  const minRequiredGutter = adWidth + safetyGutter; // 176px

  const leftBlank = minLeft;
  const rightBlank = winWidth - maxRight;

  // STRICT ZERO-COLLISION: If either side has insufficient margin, hide both skyscraper wings immediately!
  if (leftBlank >= minRequiredGutter && rightBlank >= minRequiredGutter) {
    leftAd.style.display = "block";
    rightAd.style.display = "block";
    const leftPos = Math.max(8, Math.floor((leftBlank - adWidth) / 2));
    const rightPos = Math.max(8, Math.floor((rightBlank - adWidth) / 2));
    leftAd.style.left = `${leftPos}px`;
    leftAd.style.right = "auto";
    rightAd.style.right = `${rightPos}px`;
    rightAd.style.left = "auto";
  } else {
    leftAd.style.display = "none";
    rightAd.style.display = "none";
  }
}
window.updateSkyscraperPosition = updateSkyscraperPosition;
window.addEventListener("resize", updateSkyscraperPosition);
window.addEventListener("scroll", () => {
  if (typeof updateSkyscraperPosition === "function") {
    requestAnimationFrame(updateSkyscraperPosition);
  }
}, { passive: true });

function getDisplayTierString(tier, rankTier, lp) {
  if (!tier || tier === "UNRANKED") return "언랭크";
  const tKr = TIER_NAMES_KR[tier.toUpperCase()] || tier;
  if (["CHALLENGER", "GRANDMASTER", "MASTER"].includes(tier.toUpperCase())) {
    return lp !== undefined && lp !== null ? `${tKr} (${formatNumber(lp)} LP)` : tKr;
  }
  const r = rankTier ? ` ${rankTier}` : "";
  return lp !== undefined && lp !== null ? `${tKr}${r} (${formatNumber(lp)} LP)` : `${tKr}${r}`;
}
