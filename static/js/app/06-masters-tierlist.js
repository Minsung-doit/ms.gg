// 챔피언 티어표나 모달 등에서 특정 챔피언 장인 랭킹으로 바로 이동하는 글로벌 헬퍼
window.openChampionMastersDirectly = function(champId) {
  window.switchMainTab("masters");
  if (typeof selectChampion === "function") {
    selectChampion(champId);
  }
};
// Champion Masters Module
let currentChampId = null; // 디폴트 값 없음 (완전 공란 상태로 시작)
let currentTierFilter = "all";
let currentSort = "games"; // "games" (판수 내림차순) 또는 "winrate" (승률 내림차순)
let allChampionsCache = [];

const CHAMP_IMG_BASE = `https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VER}/img/champion/`;

// DOM Elements: Empty & Content Area
const mastersEmptyState = document.getElementById("mastersEmptyState");
const mastersContentArea = document.getElementById("mastersContentArea");
const selectedChampImg = document.getElementById("selectedChampImg");
const selectedChampName = document.getElementById("selectedChampName");
const selectedChampTitle = document.getElementById("selectedChampTitle");
const selectedChampId = document.getElementById("selectedChampId");
const btnDeselectChamp = document.getElementById("btnDeselectChamp");

// DOM Elements: Left Sidebar & Search
const champFilterInput = document.getElementById("champFilterInput");
const btnChampFilterClear = document.getElementById("btnChampFilterClear");
const champFilteredCount = document.getElementById("champFilteredCount");
const champGrid = document.getElementById("champGrid");

// DOM Elements: Masters Header & List
const mastersChampTitle = document.getElementById("mastersChampTitle");
const mastersCurrentTierText = document.getElementById("mastersCurrentTierText");
const mastersSortDesc = document.getElementById("mastersSortDesc");
const mastersTotalCount = document.getElementById("mastersTotalCount");
const mastersLoading = document.getElementById("mastersLoading");
const mastersList = document.getElementById("mastersList");
const tierBtns = document.querySelectorAll(".tier-btn");


const TIER_NAMES_KR = {
  "all": "전체 티어",
  "apex": "마스터 이상",
  "CHALLENGER": "챌린저",
  "GRANDMASTER": "그랜드마스터",
  "MASTER": "마스터",
  "DIAMOND": "다이아몬드",
  "EMERALD": "에메랄드",
  "PLATINUM": "플래티넘",
  "GOLD": "골드",
  "SILVER": "실버",
  "BRONZE": "브론즈",
  "IRON": "아이언",
  "UNRANKED": "미배치"
};

// Korean Choseong (초성) List for ㄱㄴㄷ search matching (ㅇㅅㅇ, ㄹㅅ, ㅈㄷ, etc.)
const CHOSUNG_LIST = [
  'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ',
  'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
];

function getChosung(str) {
  let result = '';
  for (let i = 0; i < str.length; i++) {
    const code = str.charCodeAt(i) - 44032;
    if (code >= 0 && code <= 11171) {
      result += CHOSUNG_LIST[Math.floor(code / 588)];
    } else {
      result += str.charAt(i);
    }
  }
  return result;
}

function matchesChampion(c, query) {
  if (!query) return true;
  const q = query.trim().toLowerCase().replace(/\s+/g, '');
  if (!q) return true;

  const name = (c.name || '').toLowerCase().replace(/\s+/g, '');
  const id = (c.id || '').toLowerCase().replace(/\s+/g, '');
  const title = (c.title || '').toLowerCase().replace(/\s+/g, '');

  // 1. Partial/Exact substring match
  if (name.includes(q) || id.includes(q) || title.includes(q)) {
    return true;
  }

  // 2. Chosung match (e.g. ㅇㅅㅇ -> 야스오)
  const nameChosung = getChosung(name);
  if (nameChosung.includes(q)) {
    return true;
  }

  return false;
}

async function initChampionMasters() {
  await loadChampionsList();

  // 첫 화면은 장인 데이터가 가장 많은 챔피언 (없으면 가나다순 첫 챔피언)
  if (!currentChampId) {
    let defaultChamp = (allChampionsCache && allChampionsCache.length > 0) ? allChampionsCache[0].id : "Garen";
    try {
      const top = await (await fetch("/api/champion-masters/most-mastered")).json();
      if (top && top.id) defaultChamp = top.id;
    } catch (e) {}
    selectChampion(defaultChamp);
  } else {
    selectChampion(currentChampId);
  }
}

// Fetch 168+ champions and sort strictly in Korean alphabetical order (ㄱㄴㄷㄹ... 가나다순)
async function loadChampionsList() {
  try {
    const res = await fetch("/api/champions");
    if (res.ok) {
      const data = await res.json();
      allChampionsCache = data.champions || [];
      // 한글 ㄱㄴㄷㄹ... 순서로 정렬 (가렌, 갈리오, 갱플랭크, 그라가스...)
      allChampionsCache.sort((a, b) => a.name.localeCompare(b.name, 'ko'));
      renderChampionGrid(allChampionsCache);
    }
  } catch (e) {
    console.error("Champions fetch error:", e);
  }
}

// Render 168 Champions small portraits in left sidebar
function renderChampionGrid(list) {
  if (!champGrid) return;
  champGrid.innerHTML = "";

  if (champFilteredCount) {
    champFilteredCount.textContent = `${list.length}개`;
  }

  if (list.length === 0) {
    champGrid.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 2rem 0.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
        <i class="fa-solid fa-ban" style="font-size: 1.5rem; display: block; margin-bottom: 0.5rem; opacity: 0.6;"></i>
        일치하는 챔피언이 없습니다.
      </div>
    `;
    return;
  }

  list.forEach(c => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "champ-thumb-item";
    item.setAttribute("data-champ-id", c.id);
    item.setAttribute("title", `${c.name} (${c.title || c.id})`);

    if (currentChampId && c.id.toLowerCase() === currentChampId.toLowerCase()) {
      item.classList.add("active");
    }

    const imgUrl = `${CHAMP_IMG_BASE}${c.image || c.id + '.png'}`;
    item.innerHTML = `
      <img class="champ-thumb-img" src="${imgUrl}" alt="${c.name}" loading="lazy" onerror="this.src='${CHAMP_IMG_BASE}${c.id}.png'">
      <span class="champ-thumb-name">${c.name}</span>
    `;

    item.addEventListener("click", () => {
      selectChampion(c.id);
    });

    champGrid.appendChild(item);
  });
}

// Champion Selection: Show main ranking card and highlight portrait
function selectChampion(champId) {
  if (!champId) {
    deselectChampion();
    return;
  }

  currentChampId = champId;

  // Highlight active portrait in sidebar grid
  if (champGrid) {
    const allThumbs = champGrid.querySelectorAll(".champ-thumb-item");
    allThumbs.forEach(t => {
      if (t.getAttribute("data-champ-id").toLowerCase() === champId.toLowerCase()) {
        t.classList.add("active");
        t.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } else {
        t.classList.remove("active");
      }
    });
  }

  // Switch right pane: hide empty state, show content area
  if (mastersEmptyState) mastersEmptyState.style.display = "none";
  if (mastersContentArea) mastersContentArea.style.display = "block";

  // Load masters data
  loadChampionMasters(currentChampId, currentTierFilter, currentSort);
}

// Deselect Champion: Return to blank state
function deselectChampion() {
  currentChampId = null;

  const showcaseEl = document.getElementById("mastersBuildShowcase");
  if (showcaseEl) showcaseEl.style.display = "none";

  // Remove active highlight in grid
  if (champGrid) {
    const allThumbs = champGrid.querySelectorAll(".champ-thumb-item");
    allThumbs.forEach(t => t.classList.remove("active"));
  }

  // Switch right pane: show empty state, hide content area
  if (mastersEmptyState) mastersEmptyState.style.display = "flex";
  if (mastersContentArea) mastersContentArea.style.display = "none";
}

// Filter Champions in Real-time via Search Input
if (champFilterInput) {
  champFilterInput.addEventListener("input", (e) => {
    const q = e.target.value;
    if (btnChampFilterClear) {
      btnChampFilterClear.style.display = q ? "block" : "none";
    }
    const filtered = allChampionsCache.filter(c => matchesChampion(c, q));
    renderChampionGrid(filtered);
  });
}

// Clear Search Input Button
if (btnChampFilterClear) {
  btnChampFilterClear.addEventListener("click", () => {
    if (champFilterInput) {
      champFilterInput.value = "";
      champFilterInput.focus();
    }
    btnChampFilterClear.style.display = "none";
    renderChampionGrid(allChampionsCache);
  });
}

// Deselect Champion Button (공란으로 리셋)
if (btnDeselectChamp) {
  btnDeselectChamp.addEventListener("click", () => {
    deselectChampion();
  });
}


// Load Masters Data for selected champion & tier & sort
async function loadChampionMasters(champ, tier, sort = currentSort) {
  if (!champ) {
    deselectChampion();
    return;
  }
  if (!mastersList) return;

  mastersLoading.style.display = "block";
  mastersList.innerHTML = "";

  try {
    const res = await fetch(`/api/champion-masters?champ=${encodeURIComponent(champ)}&tier=${encodeURIComponent(tier)}&sort=${encodeURIComponent(sort)}`);
    const data = await res.json();
    mastersLoading.style.display = "none";

    if (!res.ok) {
      showToast(data.detail || "장인 랭킹을 불러오는데 실패했습니다.");
      return;
    }

    // Update Champion Header Card
    const c = data.champion;
    if (c) {
      selectedChampImg.src = `${CHAMP_IMG_BASE}${c.image || c.id + '.png'}`;
      selectedChampImg.onerror = () => {
        selectedChampImg.src = `${CHAMP_IMG_BASE}${c.id}.png`;
      };
      selectedChampName.textContent = c.name;
      selectedChampTitle.textContent = c.title;
      selectedChampId.textContent = "";
      mastersChampTitle.textContent = c.name;
    }

    // Update Tier Indicator & Total Count
    mastersCurrentTierText.textContent = TIER_NAMES_KR[tier] || tier;
    mastersTotalCount.textContent = formatNumber(data.count || 0);

    // Update Tier Button Badges
    const badgeAll = document.getElementById("badge-all");
    const badgeApex = document.getElementById("badge-apex");
    if (badgeAll) badgeAll.textContent = "";
    if (badgeApex) badgeApex.textContent = "";

    ["CHALLENGER", "GRANDMASTER", "MASTER", "DIAMOND", "EMERALD", "PLATINUM", "GOLD", "SILVER", "BRONZE", "IRON", "UNRANKED"].forEach(t => {
      const b = document.getElementById(`badge-${t}`);
      if (b) b.textContent = "";
    });

    if (mastersSortDesc) {
      mastersSortDesc.textContent = "";
    }

    renderMastersList(data.results);
  } catch (e) {
    mastersLoading.style.display = "none";
    showToast("장인 랭킹 서버와 통신할 수 없습니다.");
  }
}

async function loadMastersBuildShowcase(champId) {
  const showcaseEl = document.getElementById("mastersBuildShowcase");
  const mbsChampName = document.getElementById("mbsChampName");
  const mbsGrid = document.getElementById("mbsGrid");
  const btnOpenModal = document.getElementById("btnOpenMastersBuildModal");
  const btnCopyRunes = document.getElementById("btnCopyMastersRunes");

  if (!showcaseEl || !mbsGrid || !champId) return;

  try {
    const res = await fetch(`/api/champion-build/${encodeURIComponent(champId)}`);
    if (!res.ok) {
      showcaseEl.style.display = "none";
      return;
    }
    const b = await res.json();
    const c = b.champion || {};
    const runes = b.runes || {};
    const cores = b.core_builds || b.items?.core_sets || [];
    const boots = b.boots || b.items?.boots || [];
    const spells = b.spells || [];

    if (mbsChampName) mbsChampName.textContent = c.name || champId;

    // 1. 3-core items chain
    let coreHtml = '<span style="font-size: 0.74rem; color: var(--text-muted);">빌드 데이터 집계 중</span>';
    if (cores.length > 0) {
      const bestCore = cores[0];
      const items = bestCore.items || [];
      const itemIcons = items.map((it, idx) => `
        <div class="mbs-item-box" title="${it.name || ''} (${formatNumber(it.cost || 0)}G)">
          <img class="mbs-item-img" src="${it.icon}" alt="${it.name || ''}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/item/1001.png'">
        </div>
        ${idx < items.length - 1 ? '<i class="fa-solid fa-angle-right mbs-chain-arrow"></i>' : ''}
      `).join('');
      coreHtml = `
        <div class="mbs-items-chain">${itemIcons}</div>
        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 6px;">
          <span style="font-size: 0.7rem; color: var(--text-muted);">${items.map(it => it.name).join(' + ')}</span>
          <span class="mbs-stat-pill win">승률 ${bestCore.win_rate ?? '-'}%</span>
        </div>
      `;
    }

    // 2. Runes
    const kIcon = runes.keystone_icon || "";
    const kName = runes.keystone_name || "-";
    const sIcon = runes.sub_icon || "";
    const sName = runes.sub_tree || "-";
    const runeHtml = `
      <div class="mbs-runes-row">
        <img class="mbs-rune-img" src="${kIcon}" alt="${kName}" title="핵심 룬: ${kName}">
        <img class="mbs-rune-img sub" src="${sIcon}" alt="${sName}" title="보조 룬: ${sName}">
        <div style="display: flex; flex-direction: column;">
          <span style="font-size: 0.78rem; font-weight: 800; color: var(--text-heading);">${kName}</span>
          <span style="font-size: 0.68rem; color: var(--text-muted);">${runes.primary_tree || ''} + ${sName}</span>
        </div>
        <span class="mbs-stat-pill win" style="margin-left: auto;">승률 ${runes.win_rate ?? '-'}%</span>
      </div>
    `;

    // 3. Spells & Boots
    const bestBoot = boots.length > 0 ? (boots[0].item || boots[0]) : null;
    const spellsHtml = (spells || []).slice(0, 2).map(sp => `
      <img src="${sp.icon}" alt="${sp.name || ''}" style="width: 28px; height: 28px; border-radius: 4px;" title="${sp.name || ''}">
    `).join('');
    const bootHtml = bestBoot ? `
      <img src="${bestBoot.icon}" alt="${bestBoot.name || ''}" style="width: 28px; height: 28px; border-radius: 4px; border: 1px solid var(--border-color);" title="${bestBoot.name || ''}">
    ` : '';
    const spellsBootsHtml = `
      <div style="display: flex; align-items: center; gap: 8px;">
        <div style="display: flex; gap: 4px;">${spellsHtml}</div>
        ${bootHtml ? `<span style="color: var(--text-muted); font-size: 0.7rem;">+</span>${bootHtml}` : ''}
        <span class="mbs-stat-pill win" style="margin-left: auto;">픽률 ${runes.pick_rate ?? '-'}%</span>
      </div>
    `;

    mbsGrid.innerHTML = `
      <div class="mbs-card-col">
        <div class="mbs-col-label"><i class="fa-solid fa-cubes-stacked" style="color: #F59E0B;"></i> 많이 가는 코어 아이템</div>
        ${coreHtml}
      </div>
      <div class="mbs-card-col">
        <div class="mbs-col-label"><i class="fa-solid fa-gem" style="color: #A855F7;"></i> 핵심 룬 세팅</div>
        ${runeHtml}
      </div>
      <div class="mbs-card-col">
        <div class="mbs-col-label"><i class="fa-solid fa-bolt" style="color: #38BDF8;"></i> 추천 스펠 &amp; 신발</div>
        ${spellsBootsHtml}
      </div>
    `;

    showcaseEl.style.display = "block";

    if (btnOpenModal) {
      btnOpenModal.onclick = () => {
        if (typeof openChampionBuildModal === "function") {
          openChampionBuildModal(champId);
        }
      };
    }

    if (btnCopyRunes) {
      btnCopyRunes.onclick = async () => {
        const copyTxt = b.quick_copy_text || "";
        if (!copyTxt) { showToast("복사할 빌드 표본이 아직 없습니다.", "info"); return; }
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(copyTxt);
          }
          showToast(`📋 [${c.name}] 추천 룬 세팅이 클립보드에 복사되었습니다!`, "success");
        } catch(e) {
          showToast("클립보드 복사에 실패했습니다.", "error");
        }
      };
    }
  } catch (err) {
    showcaseEl.style.display = "none";
  }
}

function renderMastersList(results) {
  if (!results || results.length === 0) {
    mastersList.innerHTML = `
      <div style="padding: 2.5rem; text-align: center; color: var(--text-muted);">
        <i class="fa-solid fa-circle-exclamation" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>
        해당 티어 조건에 등록된 장인 소환사가 없습니다.
      </div>
    `;
    return;
  }

  mastersList.innerHTML = "";
  const fragment = document.createDocumentFragment();

  results.forEach((p, idx) => {
    const row = document.createElement("div");
    row.className = "master-row";

    const rank = p.rank != null ? p.rank : (idx + 1);
    let rankHtml = `#${rank}`;
    let rankClass = "rank-badge";
    if (rank === 1) {
      rankHtml = `<i class="fa-solid fa-crown"></i> 1위`;
      rankClass += " top-1";
    } else if (rank === 2) {
      rankHtml = `<i class="fa-solid fa-medal"></i> 2위`;
      rankClass += " top-2";
    } else if (rank === 3) {
      rankHtml = `<i class="fa-solid fa-award"></i> 3위`;
      rankClass += " top-3";
    }

    const iconHtml = p.profile_icon_id != null
      ? `<div class="master-icon-wrap">
          <img class="master-icon" src="https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/${escapeHtml(p.profile_icon_id)}.png" alt="" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/29.png'">
          ${p.summoner_level != null ? `<div class="master-level">Lv.${escapeHtml(p.summoner_level)}</div>` : ""}
        </div>`
      : "";

    let tierHtml = "";
    if (p.tier) {
      const tierText = (TIER_NAMES_KR[p.tier] || p.tier) + (p.rank_tier ? ` ${p.rank_tier}` : "");
      const lpText = (p.league_points !== undefined && p.league_points !== null)
        ? `${typeof formatNumber === "function" ? formatNumber(p.league_points) : p.league_points} LP`
        : "";
      const emblemUrl = typeof getTierEmblemUrl === "function" ? getTierEmblemUrl(p.tier) : "";
      tierHtml = `
        <div class="master-tier-text" style="display: flex; align-items: center; gap: 5px; white-space: nowrap;">
          ${emblemUrl ? `<img class="tier-emblem-img md" src="${emblemUrl}" alt="" onerror="this.style.display='none';">` : ""}
          <span style="white-space: nowrap; word-break: keep-all;">${escapeHtml(tierText)}</span>
        </div>
        ${lpText ? `<div class="master-lp-text" style="white-space: nowrap; font-variant-numeric: tabular-nums;">${escapeHtml(lpText)}</div>` : ""}
      `;
    }

    const masteryLvl = p.mastery_level != null ? `Lv.${escapeHtml(p.mastery_level)}` : "-";
    const masteryPts = p.mastery_points != null
      ? (typeof formatNumber === "function" ? formatNumber(p.mastery_points) : p.mastery_points)
      : "-";

    let lastPlayText = "-";
    if (p.last_play_time) {
      const diffMs = Date.now() - Number(p.last_play_time);
      const diffDays = Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
      lastPlayText = `${diffDays}일 전`;
    }

    row.innerHTML = `
      <div class="col-rank">
        <span class="${rankClass}">${rankHtml}</span>
      </div>
      <div class="col-player master-player-info">
        ${iconHtml}
        <div class="master-names">
          <div class="master-name">${escapeHtml(p.game_name || "")}</div>
          <div class="master-tag">#${escapeHtml(p.tag_line || "KR1")}</div>
        </div>
      </div>
      <div class="col-tier master-tier-info">
        ${tierHtml}
      </div>
      <div class="col-mastery-level master-mastery-lvl" style="font-size: 0.88rem; font-weight: 700; color: var(--text-heading); text-align: center; font-variant-numeric: tabular-nums;">
        ${masteryLvl}
      </div>
      <div class="col-mastery-points master-mastery-pts" style="font-size: 0.88rem; font-weight: 700; color: #F59E0B; text-align: right; font-variant-numeric: tabular-nums;">
        <i class="fa-solid fa-trophy" style="margin-right: 4px;"></i>${escapeHtml(masteryPts)}
      </div>
      <div class="col-last-play" style="font-size: 0.82rem; color: var(--text-muted); text-align: right;">
        ${escapeHtml(lastPlayText)}
      </div>
    `;

    // Row click -> Open Player Detail
    row.addEventListener("click", () => {
      if (typeof openPlayerDetail === "function") {
        openPlayerDetail({ game_name: p.game_name, tag_line: p.tag_line });
      }
    });

    fragment.appendChild(row);
  });

  mastersList.appendChild(fragment);
}

// Tier Filter Buttons
tierBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    tierBtns.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentTierFilter = btn.getAttribute("data-tier");
    if (currentChampId) {
      loadChampionMasters(currentChampId, currentTierFilter, currentSort);
    }
  });
});
// Champion Tier List & Analytics Module
let currentTlPosition = "all";
let currentTlTier = "EMERALD_PLUS";
let currentTlPatch = "14.20";
let currentTlRegion = "KR";
let currentTlSort = "tier";
let tierListDataCache = [];
// 직전 패치 라벨 (서버 prev_patch). 없거나 합친 패치면 null → 순위 변동 표시 안 함
let tierListPrevPatch = null;

const tierlistBody = document.getElementById("tierlistBody");
const tierlistLoading = document.getElementById("tierlistLoading");
const tierlistSearchInput = document.getElementById("tierlistSearchInput");
const posTabs = document.querySelectorAll(".pos-tab");
const tlSortBtns = document.querySelectorAll(".tl-sort-btn");

const POS_NAMES_KR = {
  "TOP": "탑",
  "JUG": "정글",
  "MID": "미드",
  "BOT": "원딜",
  "SUP": "서포터"
};

let currentTlMode = "ranked"; // "ranked" or "aram"
let aramDataCache = [];

function initChampionTierList() {
  const btnModeRanked = document.getElementById("btnModeRanked");
  const btnModeAram = document.getElementById("btnModeAram");
  const tierlistTitle = document.getElementById("tierlistTitle");
  const posFilterBar = document.querySelector(".tierlist-filter-bar");
  const thCounters = document.querySelector(".tl-col-counters");
  const thBanrate = document.querySelector(".tl-col-banrate");
  const thGames = document.querySelector(".tl-col-games");
  const tlAdvancedToolbar = document.getElementById("tlAdvancedToolbar");

  const tlRegionSelect = document.getElementById("tlRegionSelect");
  const tlTierSelect = document.getElementById("tlTierSelect");
  const tlPatchSelect = document.getElementById("tlPatchSelect");

  if (tlRegionSelect) {
    tlRegionSelect.value = currentTlRegion;
    tlRegionSelect.addEventListener("change", (e) => {
      currentTlRegion = e.target.value;
      loadChampionTierList();
    });
  }

  // 게임 티어 필터 (서버가 마스터 이상 명단으로 게임 티어를 판정)
  document.querySelectorAll(".tl-tier-filter").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tl-tier-filter").forEach(b => b.classList.toggle("active", b === btn));
      currentTlTier = btn.dataset.tltier;
      loadChampionTierList();
    });
  });

  if (tlTierSelect) {
    tlTierSelect.value = currentTlTier;
    tlTierSelect.addEventListener("change", (e) => {
      currentTlTier = e.target.value;
      loadChampionTierList();
    });
  }

  if (tlPatchSelect) {
    tlPatchSelect.value = currentTlPatch;
    tlPatchSelect.addEventListener("change", (e) => {
      currentTlPatch = e.target.value;
      loadChampionTierList();
    });
  }

  const tierlistTableWrapper = document.getElementById("tierlistTableWrapper");

  if (btnModeRanked && btnModeAram) {
    btnModeRanked.addEventListener("click", () => {
      if (currentTlMode === "ranked") return;
      currentTlMode = "ranked";
      btnModeRanked.classList.add("active");
      btnModeAram.classList.remove("active");
      if (tierlistTableWrapper) tierlistTableWrapper.classList.remove("mode-aram");
      if (tierlistTitle) tierlistTitle.textContent = "챔피언 랭킹 & 티어표";
      if (posFilterBar) posFilterBar.style.display = "flex";
      if (tlAdvancedToolbar) tlAdvancedToolbar.style.display = "flex";
      if (thCounters) thCounters.textContent = "카운터";
      if (thBanrate) thBanrate.textContent = "밴률";
      if (thGames) thGames.style.display = "block";
      loadChampionTierList();
    });

    btnModeAram.addEventListener("click", () => {
      if (currentTlMode === "aram") return;
      currentTlMode = "aram";
      btnModeAram.classList.add("active");
      btnModeRanked.classList.remove("active");
      if (tierlistTableWrapper) tierlistTableWrapper.classList.add("mode-aram");
      if (tierlistTitle) tierlistTitle.textContent = "칼바람 나락 챔피언 티어 & 밸런스";
      if (posFilterBar) posFilterBar.style.display = "none";
      if (tlAdvancedToolbar) tlAdvancedToolbar.style.display = "none";
      if (thCounters) thCounters.textContent = "칼바람 밸런스 오라 (입히는/받는 피해)";
      if (thBanrate) thBanrate.textContent = "밸런스";
      if (thGames) thGames.style.display = "none";
      loadAramTierList();
    });
  }

  // Position Tab click events (0ms 즉각 필터링 및 백그라운드 동기화)
  posTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      posTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentTlPosition = tab.getAttribute("data-pos");

      const cacheKey = `${currentTlPosition}:${currentTlTier}:${currentTlPatch}:${currentTlRegion}:${currentTlSort}`;
      const allKey = `all:${currentTlTier}:${currentTlPatch}:${currentTlRegion}:${currentTlSort}`;

      if (tierListPosClientCache.has(cacheKey)) {
        const cached = tierListPosClientCache.get(cacheKey);
        tierListDataCache = cached.results || [];
        tierListPrevPatch = cached.prev_patch || null;
        updateTierListSummaryChips(cached.summary);
        renderChampionTierList(tierListDataCache);
        loadChampionTierList(true); // background revalidate
      } else if (tierListPosClientCache.has(allKey)) {
        const allData = tierListPosClientCache.get(allKey);
        const allResults = allData.results || [];
        const filtered = currentTlPosition === "all"
          ? allResults
          : allResults.filter(c => c.position === currentTlPosition || (c.allowed_positions && c.allowed_positions.includes(currentTlPosition)));
        
        // 전체 목록에서 다시 매긴 순위는 직전 패치 순위와 기준이 달라 변동 표시를 숨긴다 (정확한 응답이 오면 다시 그림)
        tierListDataCache = filtered.map((c, i) => ({ ...c, rank: i + 1, prev_rank: undefined, prev_win_rate: undefined }));
        renderChampionTierList(tierListDataCache);
        loadChampionTierList(true); // background exact sync
      } else {
        loadChampionTierList(false);
      }
    });
  });

  // Sort buttons click events
  tlSortBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tlSortBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentTlSort = btn.getAttribute("data-tlsort");
      if (currentTlMode === "ranked") {
        loadChampionTierList();
      } else {
        renderAramTierList(aramDataCache);
      }
    });
  });

  // Table header columns direct sorting (티어, 승률, 픽률, 밴률, 표본수 1클릭 즉각 정렬)
  const headerColMap = [
    { selector: ".tierlist-table-header .tl-col-tier", sort: "tier" },
    { selector: ".tierlist-table-header .tl-col-winrate", sort: "win_rate" },
    { selector: ".tierlist-table-header .tl-col-pickrate", sort: "pick_rate" },
    { selector: ".tierlist-table-header .tl-col-banrate", sort: "ban_rate" },
    { selector: ".tierlist-table-header .tl-col-games", sort: "games" }
  ];

  headerColMap.forEach(item => {
    const el = document.querySelector(item.selector);
    if (el) {
      el.style.cursor = "pointer";
      el.title = `클릭하여 ${el.textContent.trim()} 기준 정렬`;
      el.addEventListener("click", () => {
        tlSortBtns.forEach(b => {
          b.classList.toggle("active", b.getAttribute("data-tlsort") === item.sort);
        });
        currentTlSort = item.sort;
        if (currentTlMode === "ranked") {
          loadChampionTierList();
        } else {
          renderAramTierList(aramDataCache);
        }
      });
    }
  });

  // Live Search Input filter
  if (tierlistSearchInput) {
    tierlistSearchInput.addEventListener("input", () => {
      if (currentTlMode === "ranked") {
        renderChampionTierList(tierListDataCache);
      } else {
        renderAramTierList(aramDataCache);
      }
    });
  }

  // Initial fetch
  loadChampionTierList();
}

async function loadAramTierList() {
  if (!tierlistBody || !tierlistLoading) return;

  tierlistLoading.style.display = "block";
  tierlistBody.innerHTML = "";

  try {
    const res = await fetch("/api/aram/tierlist");
    if (!res.ok) throw new Error("칼바람 티어표 데이터를 가져오지 못했습니다.");
    const data = await res.json();
    aramDataCache = data.champions || [];
    tierlistLoading.style.display = "none";
    const aramNote = document.getElementById("tlSampleNote");
    if (aramNote) aramNote.textContent = data.is_sample ? `⚠ ${data.sample_notice}` : (data.sample_note || "");
    renderAramTierList(aramDataCache);
  } catch (err) {
    tierlistLoading.style.display = "none";
    tierlistBody.innerHTML = `
      <div style="padding: 2.5rem; text-align: center; color: #E84057;">
        <i class="fa-solid fa-circle-exclamation" style="font-size: 1.8rem; margin-bottom: 0.5rem; display: block;"></i>
        칼바람 티어표 데이터를 불러오는 중 오류가 발생했습니다.
      </div>
    `;
  }
}

function renderAramTierList(items) {
  if (!tierlistBody) return;

  const query = (tierlistSearchInput?.value || "").trim().toLowerCase().replace(/\s+/g, '');

  let filtered = items;
  if (query) {
    filtered = items.filter(c => {
      const name = c.name.toLowerCase().replace(/\s+/g, '');
      const id = c.id.toLowerCase();
      const chosung = getChosung(c.name);
      return name.includes(query) || id.includes(query) || chosung.includes(query);
    });
  }

  if (filtered.length === 0) {
    tierlistBody.innerHTML = `
      <div style="padding: 2.5rem; text-align: center; color: var(--text-muted);">
        <i class="fa-solid fa-magnifying-glass" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>
        일치하는 챔피언이 없습니다.
      </div>
    `;
    return;
  }

  // 챔피언 가나다 순서 및 정렬 기준 반영 (win_rate, pick_rate, name/games, tier)
  const sortedList = [...filtered];
  if (currentTlSort === "win_rate") {
    sortedList.sort((a, b) => b.win_rate - a.win_rate);
  } else if (currentTlSort === "pick_rate") {
    sortedList.sort((a, b) => b.pick_rate - a.pick_rate);
  } else if (currentTlSort === "name" || currentTlSort === "games") {
    // 한글 가나다(ㄱㄴㄷㄹ) 순서 정렬 완벽 보장
    sortedList.sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  } else {
    // 기본: 티어 순 -> 승률 높은 순
    sortedList.sort((a, b) => (a.tier_num - b.tier_num) || (b.win_rate - a.win_rate));
  }

  tierlistBody.innerHTML = "";
  const fragment = document.createDocumentFragment();

  sortedList.forEach((c, idx) => {
    const row = document.createElement("div");
    row.className = "tierlist-row";

    const tierClass = c.tier === "OP" ? "tier-pill tier-pill-1" : `tier-pill tier-pill-${c.tier}`;
    
    // 밸런스 계수 뱃지 (입히는 피해량, 받는 피해량)
    const dmgDealText = c.dmg_dealt > 100 ? `+${c.dmg_dealt - 100}%` : (c.dmg_dealt < 100 ? `${c.dmg_dealt - 100}%` : `0%`);
    const dmgTakeText = c.dmg_taken > 100 ? `+${c.dmg_taken - 100}%` : (c.dmg_taken < 100 ? `${c.dmg_taken - 100}%` : `0%`);
    const auraBadge = `
      <span class="aram-balance-badge ${c.balance_status === '버프' ? 'aram-buff' : (c.balance_status === '너프' ? 'aram-nerf' : '')}">
        피해량 ${dmgDealText} / 받는 피해 ${dmgTakeText}
      </span>
    `;

    row.innerHTML = `
      <div class="tl-col-rank">${idx + 1}</div>
      <div class="tl-col-champ">
        <div class="tl-champ-info" style="cursor: pointer;" title="${c.name} 칼바람 추천 빌드 & 밸런스 오라 확인">
          <img class="tl-champ-avatar" src="${c.image}" alt="${c.name}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
          <div class="tl-champ-name">${c.name}</div>
        </div>
      </div>
      <div class="tl-col-tier">
        <span class="${tierClass}" style="${c.tier === 'OP' ? 'background: #E84057; color: #fff;' : ''}">${c.tier_badge}</span>
      </div>
      <div class="tl-col-position">
        <span class="tl-pos-tag" style="background: rgba(96, 165, 250, 0.15); color: #60A5FA;">칼바람</span>
      </div>
      <div class="tl-col-winrate">
        <div class="tl-rate-num" style="color: ${c.win_rate >= 50.0 ? '#10B981' : '#E84057'};">${c.win_rate}%</div>
        <div class="tl-mini-bar">
          <div class="tl-mini-bar-fill" style="width: ${c.win_rate}%; background: ${c.win_rate >= 50.0 ? '#10B981' : '#E84057'};"></div>
        </div>
      </div>
      <div class="tl-col-pickrate">
        <div class="tl-rate-num">${c.pick_rate}%</div>
        <div class="tl-mini-bar">
          <div class="tl-mini-bar-fill" style="width: ${Math.min(100, c.pick_rate * 6)}%; background: #5383E8;"></div>
        </div>
      </div>
      <div class="tl-col-banrate">
        <span class="badge-pill" style="font-size: 0.72rem; ${c.balance_status === '버프' ? 'background: rgba(0, 187, 163, 0.15); color: #00bba3;' : (c.balance_status === '너프' ? 'background: rgba(232, 64, 87, 0.15); color: #e84057;' : 'color: var(--text-muted);')}">${c.balance_status}</span>
      </div>
      <div class="tl-col-counters">
        ${auraBadge}
      </div>
      <div class="tl-col-action" style="display: flex; gap: 4px;">
        <button class="btn-goto-masters" title="${c.name} 장인 랭킹 바로가기">
          <i class="fa-solid fa-crown"></i> 장인
        </button>
        <button class="btn-goto-build" data-cid="${c.id}" title="${c.name} 칼바람 추천 룬/아이템 빌드">
          <i class="fa-solid fa-wand-magic-sparkles"></i> 빌드
        </button>
      </div>
    `;

    // Click events
    const champInfo = row.querySelector(".tl-champ-info");
    const mastersBtn = row.querySelector(".btn-goto-masters");
    const buildBtn = row.querySelector(".btn-goto-build");

    const openAramBuild = () => {
      openChampionBuildModal(c.id, {
        is_aram: true,
        dmg_dealt: c.dmg_dealt,
        dmg_taken: c.dmg_taken,
        balance_status: c.balance_status,
        champ_name: c.name,
        champ_image: c.image
      });
    };

    const goMasters = () => {
      switchMainTab("masters");
      selectChampion(c.id);
    };

    champInfo?.addEventListener("click", openAramBuild);
    mastersBtn?.addEventListener("click", goMasters);
    buildBtn?.addEventListener("click", (e) => {
      e.stopPropagation();
      openAramBuild();
    });

    fragment.appendChild(row);
  });

  tierlistBody.appendChild(fragment);
}

const tierListPosClientCache = new Map();

function updateTierListSummaryChips(summary) {
  if (!summary) return;
  const chipOp = document.getElementById("chipOpCount");
  const chipT1 = document.getElementById("chipT1Count");
  const chipT2 = document.getElementById("chipT2Count");
  const chipT3 = document.getElementById("chipT3Count");
  const chipT4 = document.getElementById("chipT4Count");
  const chipT5 = document.getElementById("chipT5Count");
  const chipGames = document.getElementById("chipTotalGames");

  if (chipOp) chipOp.innerHTML = `<i class="fa-solid fa-fire"></i> OP <strong>${summary.op_count || 0}</strong>`;
  if (chipT1) chipT1.innerHTML = `1티어 <strong>${summary.tier1_count || 0}</strong>`;
  if (chipT2) chipT2.innerHTML = `2티어 <strong>${summary.tier2_count || 0}</strong>`;
  if (chipT3) chipT3.innerHTML = `3티어 <strong>${summary.tier3_count || 0}</strong>`;
  if (chipT4) chipT4.innerHTML = `4티어 <strong>${summary.tier4_count || 0}</strong>`;
  if (chipT5) chipT5.innerHTML = `5티어 <strong>${summary.tier5_count || 0}</strong>`;
  if (chipGames) chipGames.innerHTML = `<i class="fa-solid fa-chart-simple"></i> 총 표본수: <strong>${formatNumber(summary.total_games || 0)} 게임</strong>`;
}

async function loadChampionTierList(isBackground = false) {
  if (!tierlistBody || !tierlistLoading) return;

  const cacheKey = `${currentTlPosition}:${currentTlTier}:${currentTlPatch}:${currentTlRegion}:${currentTlSort}`;

  const setSampleNote = (note) => {
    let noteEl = document.getElementById("tlSampleNote");
    if (!noteEl) {
      const summaryEl = document.getElementById("tlSummaryChips");
      if (summaryEl) {
        noteEl = document.createElement("div");
        noteEl.id = "tlSampleNote";
        noteEl.className = "tl-sample-note";
        summaryEl.parentNode.insertBefore(noteEl, summaryEl.nextSibling);
      }
    }
    if (noteEl) {
      noteEl.textContent = note || "";
    }
  };

  if (!isBackground && tierListPosClientCache.has(cacheKey)) {
    const cached = tierListPosClientCache.get(cacheKey);
    tierListDataCache = cached.results || [];
    tierListPrevPatch = cached.prev_patch || null;
    tierlistLoading.style.display = "none";
    updateTierListSummaryChips(cached.summary);
    setSampleNote(cached.sample_note);
    if (!tierListDataCache || tierListDataCache.length === 0) {
      tierlistBody.innerHTML = `
        <div style="padding: 2.5rem; text-align: center; color: var(--text-muted);">
          <i class="fa-solid fa-circle-exclamation" style="font-size: 1.8rem; margin-bottom: 0.5rem; display: block;"></i>
          아직 수집된 매치가 부족합니다. 데이터가 쌓이면 자동으로 채워집니다.
        </div>
      `;
    } else {
      renderChampionTierList(tierListDataCache);
    }
    return;
  }

  if (!isBackground) {
    tierlistLoading.style.display = "block";
    tierlistBody.innerHTML = "";
  }

  try {
    const res = await fetch(`/api/champion-analytics?position=${encodeURIComponent(currentTlPosition)}&tier=${encodeURIComponent(currentTlTier)}&patch=${encodeURIComponent(currentTlPatch)}&region=${encodeURIComponent(currentTlRegion)}&sort=${encodeURIComponent(currentTlSort)}`);
    if (!res.ok) throw new Error("티어표 데이터를 가져오지 못했습니다.");
    const data = await res.json();
    
    tierListPosClientCache.set(cacheKey, data);
    tierListDataCache = data.results || [];
    tierListPrevPatch = data.prev_patch || null;
    tierlistLoading.style.display = "none";

    updateTierListSummaryChips(data.summary);
    setSampleNote(data.sample_note);
    if (!tierListDataCache || tierListDataCache.length === 0) {
      tierlistBody.innerHTML = `
        <div style="padding: 2.5rem; text-align: center; color: var(--text-muted);">
          <i class="fa-solid fa-circle-exclamation" style="font-size: 1.8rem; margin-bottom: 0.5rem; display: block;"></i>
          아직 수집된 매치가 부족합니다. 데이터가 쌓이면 자동으로 채워집니다.
        </div>
      `;
    } else {
      renderChampionTierList(tierListDataCache);
    }
  } catch (err) {
    if (!isBackground) {
      tierlistLoading.style.display = "none";
      tierlistBody.innerHTML = `
        <div style="padding: 2.5rem; text-align: center; color: #E84057;">
          <i class="fa-solid fa-circle-exclamation" style="font-size: 1.8rem; margin-bottom: 0.5rem; display: block;"></i>
          챔피언 랭킹 데이터를 불러오는 중 오류가 발생했습니다.
        </div>
      `;
    }
  }
}

function renderChampionTierList(items) {
  if (!tierlistBody) return;

  const query = (tierlistSearchInput?.value || "").trim().toLowerCase().replace(/\s+/g, '');

  let filtered = items;
  if (query) {
    filtered = items.filter(c => {
      const name = c.name.toLowerCase().replace(/\s+/g, '');
      const id = c.id.toLowerCase();
      const chosung = getChosung(c.name);
      return name.includes(query) || id.includes(query) || chosung.includes(query);
    });
  }

  if (filtered.length === 0) {
    tierlistBody.innerHTML = `
      <div style="padding: 2.5rem; text-align: center; color: var(--text-muted);">
        <i class="fa-solid fa-magnifying-glass" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>
        일치하는 챔피언이 없습니다.
      </div>
    `;
    return;
  }

  tierlistBody.innerHTML = "";
  const fragment = document.createDocumentFragment();

  filtered.forEach((c) => {
    const isFirstInPos = c.rank === 1;
    const isSPlus = c.tier === "OP" || c.tier === "S+" || c.is_op || c.is_s_plus || c.is_s_plus_op;
    const posKr = POS_NAMES_KR[c.position] || c.position || "전체";
    const posFile = { TOP: "top", JUG: "jungle", MID: "middle", BOT: "bottom", SUP: "utility" }[c.position];

    const row = document.createElement("div");
    row.className = `tierlist-row ${c.tier === 'OP' ? 'row-op-tier' : ''} ${isFirstInPos ? 'row-pos-first-highlight' : ''}`;

    // 티어: OP / 1~5 (숫자만)
    const tierNum = isSPlus ? "OP" : String(c.tier || "5티어").replace("티어", "");
    const tierCls = isSPlus ? "op" : tierNum;
    const tierBadgeHtml = `<span class="tier-pill tier-pill-${tierCls}" title="${escapeHtml(String(c.tier || ""))}">${escapeHtml(tierNum)}</span>`;
    // 직전 패치 대비 순위 변동 (▲ 상승 / ▼ 하락 / NEW: 직전 패치엔 표본 미달·미등장)
    let rankMoveHtml = "";
    if (tierListPrevPatch && c.prev_rank !== undefined) {
      const prevRank = c.prev_rank === null ? null : Number(c.prev_rank);
      const curRank = Number(c.rank);
      const prevTitle = `${escapeHtml(String(tierListPrevPatch))} 패치`;
      if (prevRank === null) {
        rankMoveHtml = `<span class="tl-rank-move new" title="${prevTitle}에는 없음">NEW</span>`;
      } else if (Number.isFinite(prevRank) && Number.isFinite(curRank) && prevRank !== curRank) {
        const up = curRank < prevRank;
        rankMoveHtml = `<span class="tl-rank-move ${up ? "up" : "down"}" title="${prevTitle} ${prevRank}위">${up ? "▲" : "▼"}${Math.abs(prevRank - curRank)}</span>`;
      }
    }
    const rankBadgeHtml = `<span class="rank-index-num">${c.rank}</span>${rankMoveHtml}`;

    // 직전 패치 대비 승률 변화
    let wrDeltaHtml = "";
    if (tierListPrevPatch && c.prev_win_rate !== null && c.prev_win_rate !== undefined) {
      const d = Math.round((Number(c.win_rate) - Number(c.prev_win_rate)) * 10) / 10;
      if (Number.isFinite(d)) {
        const cls = d > 0 ? "up" : (d < 0 ? "down" : "flat");
        const txt = d > 0 ? `+${d.toFixed(1)}` : d.toFixed(1);
        wrDeltaHtml = `<div class="tl-wr-delta ${cls}" title="${escapeHtml(String(tierListPrevPatch))} 패치 ${Number(c.prev_win_rate)}%">${txt}</div>`;
      }
    }

    // Counter chips HTML (클릭 시 원클릭 1:1 상성 분석 즉시 이동)
    const countersHtml = (c.counters || []).map(cnt => `
      <div class="counter-chip" style="cursor: pointer;" onclick="openMatchupWithChampions(${jsArg(c.name)}, ${jsArg(cnt.name)})" title="${c.name} vs ${cnt.name} 1:1 맞대결 상성 분석 보기 (상대 승률: ${cnt.win_rate}%)">
        <img class="counter-chip-avatar" src="${cnt.image}" alt="${cnt.name}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
        <span class="counter-chip-rate">${cnt.win_rate}%</span>
      </div>
    `).join('');

    row.innerHTML = `
      <div class="tl-col-rank">${rankBadgeHtml}</div>
      <div class="tl-col-champ">
        <div class="tl-champ-info" style="cursor: pointer;" title="${escapeHtml(c.name)}">
          <img class="tl-champ-avatar" src="${c.image}" alt="${escapeHtml(c.name)}" onerror="this.style.visibility='hidden'">
          <span class="tl-champ-name">${escapeHtml(c.name)}</span>
        </div>
      </div>
      <div class="tl-col-tier">
        ${tierBadgeHtml}
      </div>
      <div class="tl-col-position">
        ${posFile ? `<img class="tl-pos-img" src="/static/images/positions/${posFile}.png" alt="${posKr}" title="${posKr}">` : ""}
      </div>
      <div class="tl-col-winrate" style="text-align: right;">
        <div class="tl-rate-num" style="color: ${c.win_rate > 50 ? '#10B981' : '#E84057'}; font-variant-numeric: tabular-nums;">${c.win_rate}%</div>
        <div class="tl-mini-bar" style="margin-left: auto;">
          <div class="tl-mini-bar-fill" style="width: ${c.win_rate}%; background: ${c.win_rate > 50 ? '#10B981' : '#E84057'};"></div>
        </div>
        ${wrDeltaHtml}
      </div>
      <div class="tl-col-pickrate" style="text-align: right;">
        <div class="tl-rate-num" style="font-variant-numeric: tabular-nums;">${c.pick_rate}%</div>
        <div class="tl-mini-bar" style="margin-left: auto;">
          <div class="tl-mini-bar-fill" style="width: ${Math.min(100, c.pick_rate * 3.5)}%; background: #5383E8;"></div>
        </div>
      </div>
      <div class="tl-col-banrate" style="text-align: right;">
        <div class="tl-rate-num" style="color: ${c.ban_rate >= 20 ? '#EF4444' : 'var(--text-main)'}; font-variant-numeric: tabular-nums;">${c.ban_rate}%</div>
        <div class="tl-mini-bar" style="margin-left: auto;">
          <div class="tl-mini-bar-fill" style="width: ${Math.min(100, c.ban_rate * 2)}%; background: #EF4444;"></div>
        </div>
      </div>
      <div class="tl-col-games" style="text-align: right;">
        <span class="tl-games-text" style="font-variant-numeric: tabular-nums;">${formatNumber(c.games)}</span>
      </div>
      <div class="tl-col-counters">
        <div class="tl-counter-chips">${countersHtml}</div>
      </div>
      <div class="tl-col-action">
        <button class="tl-icon-btn btn-goto-masters" title="${escapeHtml(c.name)} 장인 랭킹"><i class="fa-solid fa-crown"></i></button>
        <button class="tl-icon-btn btn-goto-matchup" title="${escapeHtml(c.name)} 1:1 상성"><i class="fa-solid fa-crosshairs"></i></button>
      </div>
    `;

    const openBuild = () => {
      openChampionBuildModal(c.id);
    };
    const gotoMasters = () => {
      window.openChampionMastersDirectly(c.id);
    };

    // 행 어디를 눌러도 챔피언 페이지. 카운터 아이콘·오른쪽 버튼은 각자 동작
    row.style.cursor = "pointer";
    row.addEventListener("click", openBuild);
    row.querySelector(".btn-goto-masters").addEventListener("click", (e) => { e.stopPropagation(); gotoMasters(); });
    row.querySelector(".btn-goto-matchup").addEventListener("click", (e) => { e.stopPropagation(); openMatchupWithChampions(c.name, ""); });
    row.querySelectorAll(".counter-chip").forEach(chip => chip.addEventListener("click", (e) => e.stopPropagation()));

    fragment.appendChild(row);
  });

  tierlistBody.appendChild(fragment);
  renderRecentChampionChips();
}
