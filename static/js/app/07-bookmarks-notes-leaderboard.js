// Recent Champions (최근 검색/확인 챔피언 최대 5개) Module
function getRecentChampions() {
  try {
    return JSON.parse(localStorage.getItem("lolgg_recent_champions")) || [];
  } catch (e) {
    return [];
  }
}

function saveRecentChampion(champ) {
  if (!champ) return;
  const cid = champ.id || champ.champion_id || champ.name;
  const cname = champ.name || champ.champion_name || cid;
  if (!cid) return;

  try {
    let list = getRecentChampions();
    list = list.filter(item => item.id !== cid && item.name !== cname);
    const imgUrl = champ.image || `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/${cid}.png`;
    list.unshift({
      id: cid,
      name: cname,
      image: imgUrl
    });
    if (list.length > 5) {
      list = list.slice(0, 5);
    }
    localStorage.setItem("lolgg_recent_champions", JSON.stringify(list));
    renderRecentChampionChips();
  } catch (e) {}
}

function removeRecentChampion(champId, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  try {
    let list = getRecentChampions().filter(item => item.id !== champId && item.name !== champId);
    localStorage.setItem("lolgg_recent_champions", JSON.stringify(list));
    renderRecentChampionChips();
  } catch (e) {}
}

function renderRecentChampionChips() {
  const containers = [
    document.getElementById("modalRecentChampChips"),
    document.getElementById("tlRecentChampChips")
  ];

  const list = getRecentChampions();

  const tlWrap = document.getElementById("tlRecentChampChipsWrap");
  if (tlWrap) {
    tlWrap.style.display = list.length > 0 ? "flex" : "none";
  }

  containers.forEach(container => {
    if (!container) return;
    if (list.length === 0) {
      container.innerHTML = `<span style="font-size: 0.72rem; color: var(--text-muted); font-style: italic;">최근 검색 내역 없음</span>`;
      return;
    }
    container.innerHTML = list.map(c => `
      <div class="recent-champ-chip" onclick="openChampionBuildModal(${jsArg(c.id)})" title="${c.name} 룬 &amp; 빌드 보기">
        <img src="${c.image}" alt="${c.name}" style="width: 17px; height: 17px; border-radius: 50%; object-fit: cover;" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
        <span>${c.name}</span>
        <span class="recent-champ-chip-del" onclick="removeRecentChampion(${jsArg(c.id)}, event)" title="${c.name} 삭제">&times;</span>
      </div>
    `).join("");
  });
}
window.getRecentChampions = getRecentChampions;
window.saveRecentChampion = saveRecentChampion;
window.removeRecentChampion = removeRecentChampion;
window.renderRecentChampionChips = renderRecentChampionChips;
// Recent Searches & Bookmarks (최근 검색 & 즐겨찾기) Module
const recentSearchesBar = document.getElementById("recentSearchesBar");
const recentChipsList = document.getElementById("recentChipsList");
const btnClearAllRecent = document.getElementById("btnClearAllRecent");
const bookmarksBar = document.getElementById("bookmarksBar");
const bookmarksList = document.getElementById("bookmarksList");

function getBookmarks() {
  try {
    return JSON.parse(localStorage.getItem("lolgg_bookmarks")) || [];
  } catch (e) {
    return [];
  }
}

function saveBookmarks(bmarks) {
  try {
    localStorage.setItem("lolgg_bookmarks", JSON.stringify(bmarks));
  } catch (e) {}
  renderRecentSearchesBar();
}

function isBookmarked(game_name, tag_line) {
  if (!game_name || !tag_line) return false;
  const bmarks = getBookmarks();
  return bmarks.some(b => b.game_name.toLowerCase() === game_name.toLowerCase() && b.tag_line.toLowerCase() === tag_line.toLowerCase());
}

function toggleBookmark(player) {
  let bmarks = getBookmarks();
  const existsIdx = bmarks.findIndex(b => b.game_name.toLowerCase() === player.game_name.toLowerCase() && b.tag_line.toLowerCase() === player.tag_line.toLowerCase());
  
  if (existsIdx >= 0) {
    bmarks.splice(existsIdx, 1);
    showToast(`'${player.game_name}' 소환사를 즐겨찾기에서 해제했습니다.`, "info");
  } else {
    bmarks.push({
      game_name: player.game_name,
      tag_line: player.tag_line,
      tier: player.tier || "GOLD"
    });
    showToast(`'${player.game_name}#${player.tag_line}' 즐겨찾기에 등록되었습니다.`, "success");
  }
  saveBookmarks(bmarks);
  
  // Also sync modal bookmark button if open
  const btnBookmark = document.getElementById("btnBookmarkPlayer");
  if (btnBookmark && currentDetailPlayer && currentDetailPlayer.game_name.toLowerCase() === player.game_name.toLowerCase()) {
    btnBookmark.classList.toggle("bookmarked", isBookmarked(player.game_name, player.tag_line));
  }
}

function getRecentSearches() {
  try {
    return JSON.parse(localStorage.getItem("lolgg_recent_searches")) || [];
  } catch (e) {
    return [];
  }
}

function saveRecentSearches(list) {
  try {
    localStorage.setItem("lolgg_recent_searches", JSON.stringify(list));
  } catch (e) {}
  renderRecentSearchesBar();
}

function addRecentSearch(game_name, tag_line, tier = "UNRANKED") {
  if (!game_name || !tag_line) return;
  let list = getRecentSearches();
  // Filter out existing duplicate
  list = list.filter(item => !(item.game_name.toLowerCase() === game_name.toLowerCase() && item.tag_line.toLowerCase() === tag_line.toLowerCase()));
  // Prepend
  list.unshift({
    game_name,
    tag_line,
    tier: tier || "UNRANKED",
    timestamp: Date.now()
  });
  // Max 8
  if (list.length > 8) {
    list = list.slice(0, 8);
  }
  saveRecentSearches(list);
}

function clearAllRecentSearches() {
  localStorage.removeItem("lolgg_recent_searches");
  renderRecentSearchesBar();
  showToast("최근 검색 소환사 기록이 모두 삭제되었습니다.", "info");
}

let currentRecentTabFilter = "all";

function setupRecentFilterTabs() {
  const tabs = document.querySelectorAll(".recent-filter-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentRecentTabFilter = tab.getAttribute("data-filter") || "all";
      renderRecentSearchesBar();
    });
  });
}
// Player Custom Note (소환사 개인 메모 & 핀 고정) Module
function getPlayerNotes() {
  try {
    return JSON.parse(localStorage.getItem("lolgg_player_notes")) || {};
  } catch (e) {
    return {};
  }
}

function getPlayerNote(gameName, tagLine) {
  if (!gameName) return "";
  const notes = getPlayerNotes();
  const key = `${gameName.trim().toLowerCase()}#${(tagLine || "KR1").trim().toLowerCase()}`;
  return notes[key] || "";
}

function savePlayerNote(gameName, tagLine, noteText) {
  if (!gameName) return;
  const notes = getPlayerNotes();
  const key = `${gameName.trim().toLowerCase()}#${(tagLine || "KR1").trim().toLowerCase()}`;
  const cleanNote = (noteText || "").trim();
  if (cleanNote) {
    notes[key] = cleanNote;
  } else {
    delete notes[key];
  }
  try {
    localStorage.setItem("lolgg_player_notes", JSON.stringify(notes));
  } catch (e) {}

  // 반응형 UI 즉각 동기화
  renderRecentSearchesBar();
  if (typeof renderSearchFocusDropdown === "function") {
    renderSearchFocusDropdown();
  }
  updateModalNoteUI(gameName, tagLine, cleanNote);
  showToast(cleanNote ? `'${gameName}' 메모가 저장되었습니다.` : `'${gameName}' 메모가 삭제되었습니다.`, "success");
}

function deletePlayerNote(gameName, tagLine) {
  savePlayerNote(gameName, tagLine, "");
}

function updateModalNoteUI(gameName, tagLine, noteText) {
  const p = currentDetailFullProfile || currentDetailPlayer;
  const currName = p ? (p.game_name || "") : "";
  const currTag = p ? (p.tag_line || "KR1") : "KR1";
  if (currName.toLowerCase() === (gameName || "").toLowerCase()) {
    const btnNote = document.getElementById("btnNotePlayer");
    if (btnNote) {
      btnNote.classList.toggle("has-note", Boolean(noteText));
    }
    const nameRow = document.querySelector(".player-modal-name-row");
    let badgeEl = document.getElementById("playerCustomNoteBadge");
    if (noteText) {
      if (!badgeEl && nameRow) {
        badgeEl = document.createElement("span");
        badgeEl.id = "playerCustomNoteBadge";
        badgeEl.className = "player-custom-note-badge";
        const tagSpan = nameRow.querySelector(".player-modal-tag");
        if (tagSpan && tagSpan.nextSibling) {
          nameRow.insertBefore(badgeEl, tagSpan.nextSibling);
        } else {
          nameRow.appendChild(badgeEl);
        }
        badgeEl.addEventListener("click", () => openPlayerNoteModal(gameName, tagLine));
      }
      if (badgeEl) {
        badgeEl.innerHTML = `<i class="fa-solid fa-note-sticky"></i> ${escapeHtml(noteText)}`;
        badgeEl.title = `소환사 메모: ${noteText} (클릭하여 수정)`;
      }
    } else {
      if (badgeEl) badgeEl.remove();
    }
  }
}

let activeNoteTarget = null;

function openPlayerNoteModal(gameName, tagLine) {
  if (!gameName) return;
  activeNoteTarget = { game_name: gameName, tag_line: tagLine || "KR1" };
  const modal = document.getElementById("playerNoteModal");
  if (!modal) return;

  const nameEl = document.getElementById("noteModalPlayerName");
  const tagEl = document.getElementById("noteModalPlayerTag");
  const inputEl = document.getElementById("playerNoteInput");
  const countEl = document.getElementById("noteCharCount");
  const btnDelete = document.getElementById("btnDeleteNote");

  if (nameEl) nameEl.textContent = gameName;
  if (tagEl) tagEl.textContent = `#${tagLine || "KR1"}`;

  const currentNote = getPlayerNote(gameName, tagLine);
  if (inputEl) {
    inputEl.value = currentNote;
    if (countEl) countEl.textContent = currentNote.length;
  }
  if (btnDelete) {
    btnDelete.style.display = currentNote ? "inline-flex" : "none";
  }

  modal.style.display = "flex";
  if (inputEl) {
    setTimeout(() => {
      inputEl.focus();
      inputEl.select();
    }, 50);
  }
}

function closePlayerNoteModal() {
  const modal = document.getElementById("playerNoteModal");
  if (modal) modal.style.display = "none";
  activeNoteTarget = null;
}

function initPlayerNoteModal() {
  const modal = document.getElementById("playerNoteModal");
  if (!modal) return;

  const btnClose = document.getElementById("btnCloseNoteModal");
  const btnCancel = document.getElementById("btnCancelNote");
  const btnSave = document.getElementById("btnSaveNote");
  const btnDelete = document.getElementById("btnDeleteNote");
  const inputEl = document.getElementById("playerNoteInput");
  const countEl = document.getElementById("noteCharCount");

  if (btnClose) btnClose.addEventListener("click", closePlayerNoteModal);
  if (btnCancel) btnCancel.addEventListener("click", closePlayerNoteModal);

  if (inputEl && countEl) {
    inputEl.addEventListener("input", () => {
      countEl.textContent = inputEl.value.length;
    });
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (btnSave) btnSave.click();
      } else if (e.key === "Escape") {
        closePlayerNoteModal();
      }
    });
  }

  // Preset tag buttons
  modal.querySelectorAll(".btn-preset-tag").forEach(btn => {
    btn.addEventListener("click", () => {
      const tagText = btn.getAttribute("data-tag") || "";
      if (inputEl && tagText) {
        inputEl.value = tagText;
        if (countEl) countEl.textContent = tagText.length;
        inputEl.focus();
      }
    });
  });

  if (btnSave) {
    btnSave.addEventListener("click", () => {
      if (!activeNoteTarget || !inputEl) return;
      savePlayerNote(activeNoteTarget.game_name, activeNoteTarget.tag_line, inputEl.value);
      closePlayerNoteModal();
    });
  }

  if (btnDelete) {
    btnDelete.addEventListener("click", () => {
      if (!activeNoteTarget) return;
      deletePlayerNote(activeNoteTarget.game_name, activeNoteTarget.tag_line);
      closePlayerNoteModal();
    });
  }

  // Click outside overlay to close
  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      closePlayerNoteModal();
    }
  });
}

function renderRecentSearchesBar() {
  if (!recentChipsList) return;
  const allList = getRecentSearches();
  recentChipsList.innerHTML = "";

  const favCount = allList.filter(item => isBookmarked(item.game_name, item.tag_line)).length;
  const recentCount = allList.length;

  const favBadge = document.getElementById("favCountBadge");
  const recentBadge = document.getElementById("recentCountBadge");
  if (favBadge) favBadge.textContent = favCount;
  if (recentBadge) recentBadge.textContent = recentCount;

  if (allList.length === 0) {
    recentChipsList.innerHTML = `
      <div class="recent-empty-hint">
        <i class="fa-regular fa-clock"></i>
        <span>최근 검색 없음</span>
      </div>
    `;
    if (btnClearAllRecent) btnClearAllRecent.style.display = "none";
    return;
  }

  if (btnClearAllRecent) btnClearAllRecent.style.display = "inline-flex";

  // 즐겨찾기(isBookmarked) 소환사는 최우선 핀 고정 정렬
  let displayList = allList;
  if (currentRecentTabFilter === "fav") {
    displayList = allList.filter(item => isBookmarked(item.game_name, item.tag_line));
    if (displayList.length === 0) {
      recentChipsList.innerHTML = `
        <div class="recent-empty-hint">
          <i class="fa-solid fa-star" style="color: #F59E0B;"></i>
          <span>즐겨찾기한 소환사가 없습니다. 별표(★)를 눌러 자주 찾는 소환사를 등록해보세요!</span>
        </div>
      `;
      return;
    }
  } else if (currentRecentTabFilter === "recent") {
    displayList = allList.filter(item => !isBookmarked(item.game_name, item.tag_line));
    if (displayList.length === 0) displayList = allList;
  } else {
    // 'all' 탭에서는 즐겨찾기(⭐) 항목이 최상단에 먼저 오도록 핀 고정 정렬
    displayList = [...allList].sort((a, b) => {
      const aFav = isBookmarked(a.game_name, a.tag_line) ? 1 : 0;
      const bFav = isBookmarked(b.game_name, b.tag_line) ? 1 : 0;
      return bFav - aFav;
    });
  }

  displayList.forEach((item) => {
    const isFav = isBookmarked(item.game_name, item.tag_line);
    const tierRaw = item.tier || "UNRANKED";
    const tierShort = tierRaw.substring(0, 2).toUpperCase();
    const tierClass = `tier-${tierRaw.toLowerCase()}`;
    const note = getPlayerNote(item.game_name, item.tag_line);

    const chip = document.createElement("div");
    chip.className = `recent-chip ${isFav ? "is-favorite" : ""}`;
    chip.setAttribute("data-gn", item.game_name);
    chip.setAttribute("data-tag", item.tag_line);
    chip.setAttribute("role", "button");
    chip.setAttribute("tabindex", "0");
    if (isFav) {
      chip.title = "즐겨찾기 핀 고정 소환사";
    }

    const noteBadgeHtml = note ? `
      <span class="chip-note-badge" title="메모: ${escapeHtml(note)}">
        <i class="fa-solid fa-note-sticky"></i> ${escapeHtml(note)}
      </span>
    ` : "";

    chip.innerHTML = `
      <span class="chip-tier-badge ${tierClass}" title="티어: ${tierRaw}">${tierShort}</span>
      <span class="chip-name-wrap">
        <strong class="chip-name">${escapeHtml(item.game_name)}</strong>
        <span class="chip-tag">#${escapeHtml(item.tag_line)}</span>
      </span>
      ${noteBadgeHtml}
      <button type="button" class="chip-note-btn ${note ? 'has-note' : ''}" title="소환사 메모 작성/수정">
        <i class="fa-solid fa-pen"></i>
      </button>
      <button type="button" class="chip-star-btn ${isFav ? 'active' : ''}" title="${isFav ? '즐겨찾기 해제' : '즐겨찾기 등록 (핀 고정)'}">
        <i class="fa-solid fa-star"></i>
      </button>
      <button type="button" class="chip-del-btn" title="검색 기록 삭제">
        <i class="fa-solid fa-xmark"></i>
      </button>
    `;

    chip.addEventListener("click", (e) => {
      // Clicked star
      if (e.target.closest(".chip-star-btn")) {
        e.stopPropagation();
        toggleBookmark(item);
        return;
      }
      // Clicked note button
      if (e.target.closest(".chip-note-btn")) {
        e.stopPropagation();
        openPlayerNoteModal(item.game_name, item.tag_line);
        return;
      }
      // Clicked remove
      if (e.target.closest(".chip-del-btn")) {
        e.stopPropagation();
        chip.style.transition = "transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.18s ease";
        chip.style.transform = "scale(0.85) translateY(-4px)";
        chip.style.opacity = "0";
        setTimeout(() => {
          const updated = getRecentSearches().filter(x => !(x.game_name.toLowerCase() === item.game_name.toLowerCase() && (x.tag_line || "KR1").toLowerCase() === (item.tag_line || "KR1").toLowerCase()));
          saveRecentSearches(updated);
          showToast(`'${item.game_name}' 기록이 삭제되었습니다.`);
        }, 180);
        return;
      }
      // Clicked chip body -> navigate to player
      performSearch(`${item.game_name}#${item.tag_line}`);
    });

    recentChipsList.appendChild(chip);
  });
}

function initRecentSearches() {
  if (btnClearAllRecent) {
    btnClearAllRecent.addEventListener("click", clearAllRecentSearches);
  }
  setupRecentFilterTabs();
  initPlayerNoteModal();

  // 최근 검색은 사용자가 실제로 검색한 소환사만 보여준다 (예전엔 첫 방문 시 티어를 지어낸 예시 3명을 넣었다)
  try {
    if (localStorage.getItem("lolgg_recent_seeded")) {
      const SEEDED = ["hide on bush#kr1", "chovy#kr1", "faker#kr1"];
      const cleaned = getRecentSearches().filter(x => !(x && !x.timestamp && SEEDED.includes(`${String(x.game_name).toLowerCase()}#${String(x.tag_line).toLowerCase()}`)));
      localStorage.removeItem("lolgg_recent_seeded");
      saveRecentSearches(cleaned);
      return;
    }
  } catch (e) {}
  renderRecentSearchesBar();
}

function initBookmarks() {
  initRecentSearches();
}
// Leaderboards (소환사 랭킹) Module
let currentLbTier = "ALL";
let leaderboardDataCache = [];
let currentLbSortKey = "rank";
let currentLbSortOrder = "asc";
let isLbSortInitialized = false;

const leaderboardBody = document.getElementById("leaderboardBody");
const leaderboardLoading = document.getElementById("leaderboardLoading");
const leaderboardSearchInput = document.getElementById("leaderboardSearchInput");
const lbTierTabs = document.querySelectorAll(".lb-tier-tab");

function renderLpSparklineSvg(history, delta7d) {
  const data = Array.isArray(history) && history.length > 0 ? history : [0, 0];
  const delta = typeof delta7d === "number" ? delta7d : (data[data.length - 1] - data[0]);

  const w = 84;
  const h = 26;
  const padX = 4;
  const padY = 4;

  const minVal = Math.min(...data);
  const maxVal = Math.max(...data);
  const range = maxVal - minVal || 1;

  const points = data.map((val, idx) => {
    const x = data.length === 1
      ? w / 2
      : padX + (idx / (data.length - 1)) * (w - 2 * padX);
    const y = (h - padY) - ((val - minVal) / range) * (h - 2 * padY);
    return { x: Number(x.toFixed(1)), y: Number(y.toFixed(1)) };
  });

  const polylinePoints = points.map(p => `${p.x},${p.y}`).join(" ");
  const firstPoint = points[0];
  const lastPoint = points[points.length - 1];
  const polygonPoints = `${firstPoint.x},${h} ${polylinePoints} ${lastPoint.x},${h}`;

  let strokeColor = "#60A5FA";
  let fillColor = "rgba(96, 165, 250, 0.15)";
  let deltaClass = "delta-neutral";
  let deltaText = `${delta > 0 ? "+" : ""}${delta} LP`;

  if (delta > 0) {
    strokeColor = "#10B981";
    fillColor = "rgba(16, 185, 129, 0.15)";
    deltaClass = "delta-up";
  } else if (delta < 0) {
    strokeColor = "#EF4444";
    fillColor = "rgba(239, 68, 68, 0.15)";
    deltaClass = "delta-down";
  }

  const tooltip = `최근 7일 LP: ${data.join(" → ")} (${deltaText})`;

  return `
    <div class="lb-sparkline-wrap" title="${tooltip}">
      <svg class="lb-sparkline-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">
        <polygon points="${polygonPoints}" fill="${fillColor}" />
        <polyline points="${polylinePoints}" fill="none" stroke="${strokeColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        <circle cx="${lastPoint.x}" cy="${lastPoint.y}" r="2.5" fill="${strokeColor}" stroke="#1E293B" stroke-width="1" />
      </svg>
      <span class="lb-sparkline-delta ${deltaClass}">${deltaText}</span>
    </div>
  `;
}

function renderMomentumBadge(momentum) {
  const m = momentum || { badge_text: "기록 없음", badge_class: "streak-normal", recent_5: [] };
  const dotsHtml = (m.recent_5 || []).map(r => {
    const isWin = r === "W" || r === 1 || r === true;
    const label = isWin ? "승" : "패";
    const dotClass = isWin ? "dot-win" : "dot-loss";
    return `<span class="lb-mom-dot ${dotClass}" title="${label}"></span>`;
  }).join("");

  return `
    <div class="lb-momentum-cell">
      <div class="lb-momentum-badge ${m.badge_class || 'streak-normal'}">${m.badge_text || '전적 기록'}</div>
      <div class="lb-mom-dots" title="최근 5게임 승패">${dotsHtml}</div>
    </div>
  `;
}

function updateSortHeaderIcons() {
  const sortHeaders = document.querySelectorAll(".leaderboard-table-header .lb-sortable");
  sortHeaders.forEach(th => {
    const sortKey = th.getAttribute("data-sort");
    const icon = th.querySelector(".sort-icon");
    if (!icon) return;

    if (sortKey === currentLbSortKey) {
      th.classList.add("active-sort");
      icon.className = `fa-solid fa-sort-${currentLbSortOrder === "asc" ? "up" : "down"} sort-icon active`;
    } else {
      th.classList.remove("active-sort");
      icon.className = "fa-solid fa-sort sort-icon";
    }
  });
}

function initLeaderboardSorting() {
  if (isLbSortInitialized) return;
  isLbSortInitialized = true;

  const sortHeaders = document.querySelectorAll(".leaderboard-table-header .lb-sortable");
  sortHeaders.forEach(th => {
    th.addEventListener("click", () => {
      const sortKey = th.getAttribute("data-sort");
      if (!sortKey) return;

      if (currentLbSortKey === sortKey) {
        currentLbSortOrder = currentLbSortOrder === "asc" ? "desc" : "asc";
      } else {
        currentLbSortKey = sortKey;
        if (["lp", "sparkline", "winrate", "momentum"].includes(sortKey)) {
          currentLbSortOrder = "desc";
        } else {
          currentLbSortOrder = "asc";
        }
      }

      updateSortHeaderIcons();
      renderLeaderboard(leaderboardDataCache);
    });
  });
}

function sortLeaderboardItems(items) {
  if (!Array.isArray(items)) return [];
  const list = [...items];

  list.sort((a, b) => {
    let res = 0;
    switch (currentLbSortKey) {
      case "rank":
        res = (a.rank || 0) - (b.rank || 0);
        break;
      case "name": {
        const nameA = (a.game_name || "").toLowerCase();
        const nameB = (b.game_name || "").toLowerCase();
        res = nameA.localeCompare(nameB, "ko");
        break;
      }
      case "lp":
        res = (a.league_points || 0) - (b.league_points || 0);
        break;
      case "sparkline":
        res = (a.lp_delta_7d || 0) - (b.lp_delta_7d || 0);
        break;
      case "winrate":
        res = (a.win_rate || 0) - (b.win_rate || 0);
        if (res === 0) res = (a.wins || 0) - (b.wins || 0);
        break;
      case "momentum": {
        const sa = a.momentum?.streak_score ?? 0;
        const sb = b.momentum?.streak_score ?? 0;
        res = sa - sb;
        break;
      }
      default:
        res = (a.rank || 0) - (b.rank || 0);
    }
    return currentLbSortOrder === "asc" ? res : -res;
  });

  return list;
}
// [Session 7] Interactive Tier Distribution & LP Heatmap Engine
let tierDistributionData = null;

async function initTierDistribution() {
  // 정식 키 전까지 샘플 데이터 (화면 부제에 샘플 표시, docs/PRODUCTION_KEY_SAMPLES.md)
  const card = document.getElementById("tierDistributionCard");
  if (!card) return;

  const btnDivs = document.getElementById("btnTdViewDivisions");
  const btnGroups = document.getElementById("btnTdViewGroups");
  const barsContainer = document.getElementById("tdDivisionBars");
  const groupsContainer = document.getElementById("tdGroupCards");

  if (btnDivs && btnGroups) {
    btnDivs.addEventListener("click", () => {
      btnDivs.classList.add("active");
      btnGroups.classList.remove("active");
      if (barsContainer) barsContainer.style.display = "flex";
      if (groupsContainer) groupsContainer.style.display = "none";
    });

    btnGroups.addEventListener("click", () => {
      btnGroups.classList.add("active");
      btnDivs.classList.remove("active");
      if (barsContainer) barsContainer.style.display = "none";
      if (groupsContainer) groupsContainer.style.display = "grid";
    });
  }

  try {
    const res = await fetch("/api/tier-distribution/stats");
    if (!res.ok) return;
    const data = await res.json();
    tierDistributionData = data;
    renderTierDistributionUI(data);
  } catch (e) {
    console.error("Failed to load tier distribution stats:", e);
  }
}

function renderTierDistributionUI(data) {
  if (!data || !data.divisions) return;

  // 1. KPI 지표 렌더링
  const kpiTotal = document.getElementById("tdKpiTotal");
  const kpiPeak = document.getElementById("tdKpiPeakHotspot");
  const kpiMedian = document.getElementById("tdKpiMedian");
  const kpiApex = document.getElementById("tdKpiApex");

  if (kpiTotal && data.total_ranked_formatted) kpiTotal.textContent = `${data.total_ranked_formatted}명`;
  if (kpiPeak && data.heatmap_analysis && data.heatmap_analysis.peak_lp_hotspot) {
    kpiPeak.textContent = data.heatmap_analysis.peak_lp_hotspot;
  }
  if (kpiMedian && data.summary) kpiMedian.textContent = `${data.summary.median_tier} (${data.summary.median_percentile})`;
  if (kpiApex && data.summary) kpiApex.textContent = `${data.summary.apex_percentage} (${data.summary.apex_formatted})`;

  // 2. 인터랙티브 스펙트럼 바 렌더링
  const spectrumBar = document.getElementById("tdSpectrumBar");
  if (spectrumBar) {
    spectrumBar.innerHTML = "";
    data.divisions.forEach(d => {
      const seg = document.createElement("div");
      seg.className = "td-spectrum-seg";
      seg.style.width = `${Math.max(d.percentage, 0.45)}%`;
      seg.style.background = `linear-gradient(180deg, ${d.heatmap_color || '#3B82F6'}, ${d.colors?.badge || '#60A5FA'})`;
      seg.setAttribute("data-label", d.label);

      bindTooltipEvents(seg, d);
      spectrumBar.appendChild(seg);
    });
  }

  // 3. 27개 디비전 히스토그램 바 렌더링
  const barsGrid = document.getElementById("tdDivisionBars");
  if (barsGrid) {
    barsGrid.innerHTML = "";
    const maxCount = data.heatmap_analysis?.max_division_count || 246800;
    
    data.divisions.forEach(d => {
      const col = document.createElement("div");
      col.className = "td-bar-col";
      col.title = `${d.label}: ${d.count_formatted}명 (${d.percentage}%)`;

      const fill = document.createElement("div");
      fill.className = "td-bar-fill";
      const heightPct = Math.max(6, Math.round((d.count / maxCount) * 100));
      fill.style.height = `${heightPct}%`;
      fill.style.background = `linear-gradient(180deg, ${d.heatmap_color}, ${d.colors?.badge || '#3B82F6'})`;
      fill.style.boxShadow = `0 0 8px ${d.heatmap_glow || 'rgba(59,130,246,0.3)'}`;

      const lbl = document.createElement("span");
      lbl.className = "td-bar-lbl";
      const shortLabel = getShortDivisionLabel(d);
      lbl.textContent = shortLabel;

      col.appendChild(fill);
      col.appendChild(lbl);
      bindTooltipEvents(col, d);
      barsGrid.appendChild(col);
    });
  }

  // 4. 10대 티어 요약 카드 렌더링
  const groupsGrid = document.getElementById("tdGroupCards");
  if (groupsGrid && data.tier_groups) {
    groupsGrid.innerHTML = "";
    data.tier_groups.forEach(tg => {
      const card = document.createElement("div");
      card.className = "td-group-card";
      card.style.borderLeft = `3px solid ${tg.colors?.badge || tg.heatmap_color}`;

      let repHtml = "";
      if (tg.representative_players && tg.representative_players.length > 0) {
        const p1 = tg.representative_players[0];
        repHtml = `<div style="font-size: 0.68rem; color: #94A3B8; margin-top: 5px;">
          대표: <strong style="color: #60A5FA;">${p1.game_name}</strong> (${p1.role})
        </div>`;
      }

      card.innerHTML = `
        <div class="td-gc-top">
          <span class="td-gc-tier" style="color: ${tg.colors?.text || '#fff'}">${tg.name_kr}</span>
          <span class="td-gc-badge" style="background: rgba(255,255,255,0.08); color: ${tg.heatmap_color}; border: 1px solid ${tg.heatmap_color}40;">
            ${tg.heatmap_badge || ''}
          </span>
        </div>
        <div class="td-gc-count">${tg.count_formatted}명</div>
        <div class="td-gc-pct">${tg.percentage}% · ${tg.top_percentile_display}</div>
        ${repHtml}
      `;
      groupsGrid.appendChild(card);
    });
  }
}

function getShortDivisionLabel(d) {
  if (d.tier === "CHALLENGER") return "C";
  if (d.tier === "GRANDMASTER") return "GM";
  if (d.tier === "MASTER") return "M";
  const map = {
    "DIAMOND": "D",
    "EMERALD": "E",
    "PLATINUM": "P",
    "GOLD": "G",
    "SILVER": "S",
    "BRONZE": "B",
    "IRON": "I"
  };
  const prefix = map[d.tier] || d.tier.substring(0, 1);
  return `${prefix}${d.division || ''}`;
}

function bindTooltipEvents(elem, d) {
  const tooltip = document.getElementById("tdFloatingTooltip");
  if (!tooltip) return;

  elem.addEventListener("mouseenter", (e) => {
    updateTooltipContent(d);
    tooltip.style.display = "block";
    positionTooltip(e, tooltip);
  });

  elem.addEventListener("mousemove", (e) => {
    positionTooltip(e, tooltip);
  });

  elem.addEventListener("mouseleave", () => {
    tooltip.style.display = "none";
  });
}

function updateTooltipContent(d) {
  const badge = document.getElementById("tdTipTierBadge");
  const heatBadge = document.getElementById("tdTipHeatBadge");
  const count = document.getElementById("tdTipCount");
  const cumul = document.getElementById("tdTipCumul");
  const score = document.getElementById("tdTipDensityScore");
  const rank = document.getElementById("tdTipRankRange");
  const list = document.getElementById("tdTipHotspotsList");

  if (badge) {
    badge.textContent = d.label;
    badge.style.color = d.colors?.text || '#fff';
  }
  if (heatBadge) {
    heatBadge.textContent = d.heatmap_badge || "밀집 구간";
    heatBadge.style.color = d.heatmap_color || "#F87171";
    heatBadge.style.borderColor = `${d.heatmap_color || '#F87171'}60`;
  }
  if (count) count.textContent = `${d.count_formatted}명 (${d.percentage}%)`;
  if (cumul) cumul.textContent = `${d.top_percentile_display} (${d.rank_range})`;
  if (score) score.textContent = `${d.density_score || 0} / 100 (강도: ${Math.round((d.heatmap_intensity || 0) * 100)}%)`;
  if (rank) rank.textContent = d.lp_range || "0 ~ 100 LP";

  if (list && d.lp_hotspots) {
    list.innerHTML = "";
    d.lp_hotspots.forEach(h => {
      const row = document.createElement("div");
      row.className = "td-hotspot-item";
      row.innerHTML = `
        <span class="td-hotspot-range" style="color: ${h.color || '#E2E8F0'}">${h.lp_range}</span>
        <span style="color: #94A3B8; font-size: 0.64rem;">${h.label}</span>
        <span class="td-hotspot-pct" style="color: ${h.color || '#fff'}">${h.percentage}% (${h.estimated_formatted})</span>
      `;
      list.appendChild(row);
    });
  }
}

function positionTooltip(e, tooltip) {
  const card = document.getElementById("tierDistributionCard");
  if (!card) return;
  const rect = card.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
}

function initLeaderboard() {
  initLeaderboardSorting();
  updateSortHeaderIcons();
  initTierDistribution();

  lbTierTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      lbTierTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentLbTier = tab.getAttribute("data-lbtier");
      loadLeaderboard(currentLbTier);
    });
  });

  if (leaderboardSearchInput) {
    leaderboardSearchInput.addEventListener("input", () => {
      renderLeaderboard(leaderboardDataCache);
    });
  }

  const btnSyncRealLadder = document.getElementById("btnSyncRealLadder");
  if (btnSyncRealLadder) {
    btnSyncRealLadder.addEventListener("click", async () => {
      const origHtml = btnSyncRealLadder.innerHTML;
      btnSyncRealLadder.disabled = true;
      btnSyncRealLadder.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Riot 서버 동기화 중...</span>`;
      try {
        const res = await fetch("/api/leaderboard/sync", { method: "POST" });
        const data = await res.json();
        if (data.status === "success") {
          showToast(`⚡ 한국 서버 실시간 챌린저 ${data.synced_count}명 동기화 완료!`, "success", 3500);
          loadLeaderboard(currentLbTier);
        } else {
          showToast(data.detail || data.message || "동기화 실패", res.status === 429 ? "warning" : "error");
        }
      } catch (err) {
        showToast("Riot 서버와 통신 중 오류가 발생했습니다.", "error");
      } finally {
        btnSyncRealLadder.disabled = false;
        btnSyncRealLadder.innerHTML = origHtml;
      }
    });
  }

  loadLeaderboard(currentLbTier);
}

const lbMemoryCache = new Map();

function updateLeaderboardLatencyBadge(ms, isCached) {
  const badge = document.getElementById("lbSpeedBadge");
  if (badge) {
    badge.remove();
  }
}

async function loadLeaderboard(tier = "ALL") {
  if (!leaderboardBody || !leaderboardLoading) return;

  if (lbMemoryCache.has(tier)) {
    leaderboardDataCache = lbMemoryCache.get(tier);
    leaderboardLoading.style.display = "none";
    renderLeaderboard(leaderboardDataCache);
  } else {
    leaderboardLoading.style.display = "block";
    leaderboardBody.innerHTML = "";
  }

  try {
    const t0 = performance.now();
    const res = await fetch(`/api/leaderboard?tier=${tier}`);
    if (!res.ok) throw new Error("랭킹 데이터를 가져오지 못했습니다.");
    const data = await res.json();
    const elapsed = Math.round(performance.now() - t0);

    leaderboardDataCache = data.results || [];
    lbMemoryCache.set(tier, leaderboardDataCache);

    leaderboardLoading.style.display = "none";
    renderLeaderboard(leaderboardDataCache);
    updateLeaderboardLatencyBadge(elapsed, data.cached);
  } catch (e) {
    if (!lbMemoryCache.has(tier)) {
      leaderboardLoading.style.display = "none";
      leaderboardBody.innerHTML = `
        <div style="padding: 2.5rem; text-align: center; color: #E84057;">
          <i class="fa-solid fa-circle-exclamation" style="font-size: 1.8rem; margin-bottom: 0.5rem; display: block;"></i>
          소환사 랭킹 데이터를 불러오는 중 오류가 발생했습니다.
        </div>
      `;
    }
  }
}

function renderLeaderboard(items) {
  if (!leaderboardBody) return;

  const query = (leaderboardSearchInput?.value || "").trim().toLowerCase();

  let filtered = items;
  if (query) {
    filtered = items.filter(p => {
      return p.game_name.toLowerCase().includes(query) ||
             p.tag_line.toLowerCase().includes(query) ||
             (p.note && p.note.toLowerCase().includes(query));
    });
  }

  if (filtered.length === 0) {
    // 검색어가 없는데 비어 있으면 아직 라이엇에서 받아 온 랭킹이 없는 것이다 (키 미등록·동기화 전)
    const emptyMsg = (!query && (!items || items.length === 0))
      ? "아직 불러온 랭킹 데이터가 없습니다. 라이엇 API 키가 등록되면 챌린저 랭킹이 자동으로 동기화됩니다."
      : "일치하는 소환사가 없습니다.";
    leaderboardBody.innerHTML = `
      <div style="padding: 2.5rem; text-align: center; color: var(--text-muted);">
        <i class="fa-solid fa-magnifying-glass" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>
        ${emptyMsg}
      </div>
    `;
    return;
  }

  const sorted = sortLeaderboardItems(filtered);

  leaderboardBody.innerHTML = "";
  const fragment = document.createDocumentFragment();

  sorted.forEach(p => {
    const row = document.createElement("div");
    row.className = "leaderboard-row";

    let rankClass = "lb-col-rank";
    if (p.rank === 1) rankClass += " top-1";
    else if (p.rank === 2) rankClass += " top-2";
    else if (p.rank === 3) rankClass += " top-3";

    const tierColor = getTierColorHex(p.tier);

    row.innerHTML = `
      <div class="${rankClass}">#${p.rank}</div>
      <div class="lb-player-cell">
        <div class="lb-names">
          <div class="lb-name">${escapeHtml(p.game_name)} <span style="font-size: 0.74rem; color: var(--text-muted);">#${escapeHtml(p.tag_line)}</span></div>
          ${p.note ? `<div class="lb-tag-note"><i class="fa-solid fa-certificate" style="color: #60A5FA;"></i> ${escapeHtml(p.note)}</div>` : ''}
        </div>
        ${(p.most_champions || []).length ? `<div class="lb-most">${p.most_champions.map(c => `
          <img src="${escapeHtml(c.image)}" alt="${escapeHtml(c.name)}" title="${escapeHtml(c.name)} ${escapeHtml(String(c.games))}게임 승률 ${escapeHtml(String(c.win_rate))}%" loading="lazy">`).join("")}</div>` : ""}
      </div>
      <div class="lb-tier-cell">
        <img class="lb-emblem" src="${getTierEmblemUrl(p.tier || p.tier_kr)}" alt="" onerror="this.style.visibility='hidden';">
        <span class="lb-lp-text" style="white-space: nowrap; font-variant-numeric: tabular-nums;">${formatNumber(p.league_points)} LP</span>
      </div>
      <div class="lb-winrate-cell">
        <div class="lb-wr-top"><span class="lb-wr-text ${p.win_rate > 50 ? 'is-good' : 'is-bad'}" style="font-variant-numeric: tabular-nums;">${p.win_rate}%</span><span class="lb-record-sub" style="font-variant-numeric: tabular-nums;">${p.wins}승 ${p.losses}패</span></div>
        <div class="lb-wr-bar">
          <div class="lb-wr-bar-fill" style="width: ${p.win_rate}%;"></div>
        </div>
      </div>
      <div class="lb-action-cell">
        <button class="lb-search-btn" title="${escapeHtml(p.game_name)} 전적"><i class="fa-solid fa-magnifying-glass"></i></button>
      </div>
    `;

    // 검색창에 직접 검색한 것과 같은 화면: 검색 탭으로 이동해 Riot ID로 검색한다
    row.addEventListener("click", () => {
      switchMainTab("search");
      performSearch(`${p.game_name}#${p.tag_line || "KR1"}`);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    fragment.appendChild(row);
  });

  leaderboardBody.appendChild(fragment);

  prefetchLeaderboardTopPlayers(sorted.slice(0, 100));
}
