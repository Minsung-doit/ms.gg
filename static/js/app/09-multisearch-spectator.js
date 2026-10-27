// Multi-Search Module
let currentMultiSearchSummoners = [];
let lastMultiSearchData = null;

async function shareMultiSearchToDiscord() {
  if (!lastMultiSearchData || !lastMultiSearchData.players || lastMultiSearchData.players.length === 0) {
    showToast("공유할 소환사 검색 결과가 없습니다.");
    return;
  }
  const lines = ["🎮 carry.gg 멀티서치 팀 분석:"];
  lastMultiSearchData.players.forEach(p => {
    if (p.found) {
      const tierParts = [(typeof TIER_NAMES_KR !== "undefined" && TIER_NAMES_KR[p.tier?.toUpperCase()]) || p.tier || "언랭크"];
      if (p.rank_tier && !["MASTER", "GRANDMASTER", "CHALLENGER"].includes(String(p.tier).toUpperCase())) {
        tierParts.push(p.rank_tier);
      }
      const tierStr = tierParts.join(" ");
      const wr = p.win_rate != null ? `${p.win_rate}%` : '';
      const lp = p.league_points != null ? `${p.league_points}LP` : '';
      const stats = [tierStr, lp, wr].filter(Boolean).join(" · ");
      lines.push(`• **${p.game_name}#${p.tag_line || 'KR1'}** (${stats})`);
    } else {
      lines.push(`• **${p.game_name}#${p.tag_line || 'KR1'}** (미등록)`);
    }
  });
  if (currentMultiSearchSummoners.length > 0) {
    lines.push(`🔗 ${window.location.origin}/?tab=multisearch&summoners=${encodeURIComponent(currentMultiSearchSummoners.join(","))}`);
  }
  const text = lines.join("\n");
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast("디스코드 공유 텍스트가 복사되었습니다!", "success");
    }).catch(() => {
      fallbackCopyShareUrl(text, () => showToast("디스코드 공유 텍스트가 복사되었습니다!", "success"));
    });
  } else {
    fallbackCopyShareUrl(text, () => showToast("디스코드 공유 텍스트가 복사되었습니다!", "success"));
  }
}

function shareMultiSearchResult() {
  if (!currentMultiSearchSummoners || currentMultiSearchSummoners.length === 0) {
    showToast("공유할 소환사 검색 결과가 없습니다.");
    return;
  }
  const url = `${window.location.origin}/?tab=multisearch&summoners=${encodeURIComponent(currentMultiSearchSummoners.join(","))}`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url).then(() => {
      showToast("공유 링크가 클립보드에 복사되었습니다.", "success");
    }).catch(() => {
      fallbackCopyShareUrl(url);
    });
  } else {
    fallbackCopyShareUrl(url);
  }
}

function fallbackCopyShareUrl(text, cb) {
  const t = document.createElement("textarea");
  t.value = text;
  document.body.appendChild(t);
  t.select();
  try {
    document.execCommand("copy");
    if (cb) cb();
    else showToast("🔗 링크가 복사되었습니다!");
  } catch (e) {
    prompt("아래 링크를 복사하세요:", text);
  }
  document.body.removeChild(t);
}

function clearMultiSearchResults() {
  currentMultiSearchSummoners = [];
  lastMultiSearchData = null;
  const resultArea = document.getElementById("multiSearchResultArea");
  if (resultArea) resultArea.style.display = "none";
  const loadingEl = document.getElementById("multiSearchLoading");
  if (loadingEl) loadingEl.style.display = "none";
  const predictEl = document.getElementById("aiTeamPredictBanner");
  if (predictEl) predictEl.innerHTML = "";
  const bannerEl = document.getElementById("teamSummaryBanner");
  if (bannerEl) {
    bannerEl.innerHTML = "";
    bannerEl.style.display = "none";
  }
  const cardsListEl = document.getElementById("multiSearchCardsList");
  if (cardsListEl) cardsListEl.innerHTML = "";
}

function initMultiSearch() {
  // 20-multisearch.css 동적 주입 (index.html link 태그 없이 런타임 활성화)
  if (!document.querySelector('link[href*="20-multisearch.css"]')) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/static/css/app/20-multisearch.css";
    document.head.appendChild(link);
  }

  const multiSearchForm = document.getElementById("multiSearchForm");
  const multiSearchTextarea = document.getElementById("multiSearchTextarea");
  const btnClearMultiSearch = document.getElementById("btnClearMultiSearch");
  const btnShareMultiSearch = document.getElementById("btnShareMultiSearch");

  let multiSearchDebounceTimer = null;

  const handleAutoMultiSearch = (delay = 300) => {
    if (multiSearchDebounceTimer) {
      clearTimeout(multiSearchDebounceTimer);
      multiSearchDebounceTimer = null;
    }
    const currentVal = multiSearchTextarea ? multiSearchTextarea.value.trim() : "";
    if (!currentVal) {
      clearMultiSearchResults();
      return;
    }
    multiSearchDebounceTimer = setTimeout(() => {
      runMultiSearch(currentVal, true);
    }, delay);
  };

  // Zero-Click Instant MultiSearch (300ms debounce on input & paste)
  if (multiSearchTextarea) {
    multiSearchTextarea.addEventListener("input", () => {
      handleAutoMultiSearch(300);
    });

    multiSearchTextarea.addEventListener("paste", () => {
      setTimeout(() => {
        handleAutoMultiSearch(300);
      }, 50);
    });
  }

  // Share button
  if (btnShareMultiSearch) {
    btnShareMultiSearch.addEventListener("click", shareMultiSearchResult);
  }

  // Discord Share button
  const btnShareDiscordMulti = document.getElementById("btnShareDiscordMulti");
  if (btnShareDiscordMulti) {
    btnShareDiscordMulti.addEventListener("click", shareMultiSearchToDiscord);
  }

  // Clear button
  if (btnClearMultiSearch && multiSearchTextarea) {
    btnClearMultiSearch.addEventListener("click", () => {
      if (multiSearchDebounceTimer) {
        clearTimeout(multiSearchDebounceTimer);
        multiSearchDebounceTimer = null;
      }
      multiSearchTextarea.value = "";
      clearMultiSearchResults();
      multiSearchTextarea.focus();
    });
  }

  // Form submit
  if (multiSearchForm && multiSearchTextarea) {
    multiSearchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      if (multiSearchDebounceTimer) {
        clearTimeout(multiSearchDebounceTimer);
        multiSearchDebounceTimer = null;
      }
      const val = multiSearchTextarea.value.trim();
      if (val) {
        runMultiSearch(val);
      } else {
        clearMultiSearchResults();
        showToast("소환사명을 입력하거나 픽창 채팅을 붙여넣어 주세요.");
      }
    });
  }

  // URL 파라미터(summoners) 우선 로드 지원
  const urlParams = new URLSearchParams(window.location.search);
  const summonersParam = urlParams.get("summoners");
  if (summonersParam && multiSearchTextarea) {
    const parsedNames = summonersParam.split(",").map(s => s.trim()).filter(Boolean).join("\n");
    multiSearchTextarea.value = parsedNames;
    runMultiSearch(parsedNames);
    return;
  }
}

async function runMultiSearch(rawText, isAuto = false) {
  const loadingEl = document.getElementById("multiSearchLoading");
  const resultArea = document.getElementById("multiSearchResultArea");

  if (!rawText || !rawText.trim()) {
    if (!isAuto) {
      showToast("소환사명을 입력하거나 픽창 채팅을 붙여넣어 주세요.");
    }
    clearMultiSearchResults();
    return;
  }

  if (loadingEl) loadingEl.style.display = "block";
  if (resultArea) resultArea.style.display = "none";

  try {
    const res = await fetch("/api/multi-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_text: rawText })
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      const detailMsg = errBody.detail || "멀티서치 분석 중 오류가 발생했습니다. 다시 시도해 주세요.";
      if (loadingEl) loadingEl.style.display = "none";
      showToast(detailMsg, "error");
      return;
    }

    const data = await res.json();

    if (loadingEl) loadingEl.style.display = "none";
    if (resultArea) resultArea.style.display = "block";

    if (data && data.players) {
      currentMultiSearchSummoners = data.players.map(p => p.tag_line ? `${p.game_name}#${p.tag_line}` : p.game_name);
    }
    lastMultiSearchData = data;

    renderMultiSearchResults(data);
  } catch (err) {
    if (loadingEl) loadingEl.style.display = "none";
    showToast(err.message || "멀티서치 분석 중 오류가 발생했습니다. 다시 시도해 주세요.", "error");
  }
}

function renderMultiSearchResults(data) {
  const predictEl = document.getElementById("aiTeamPredictBanner");
  const bannerEl = document.getElementById("teamSummaryBanner");
  const cardsListEl = document.getElementById("multiSearchCardsList");

  if (predictEl) predictEl.innerHTML = "";
  if (bannerEl) {
    bannerEl.innerHTML = "";
    bannerEl.style.display = "none";
  }
  if (cardsListEl) cardsListEl.innerHTML = "";

  if (!data || !data.players || data.players.length === 0) {
    if (bannerEl) {
      bannerEl.style.display = "block";
      bannerEl.innerHTML = `<div class="ms-empty-notice" style="color: var(--text-muted); padding: 1.5rem; text-align: center;">조회된 소환사가 없습니다.</div>`;
    }
    return;
  }

  // 1. 공지 배너 (서버가 주는 공지/경고가 있을 때만 표시)
  if (bannerEl && data.notice) {
    bannerEl.style.display = "block";
    bannerEl.innerHTML = `
      <div class="team-summary-notice" style="padding: 10px 14px; border-radius: 8px; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: #F59E0B; font-size: 0.86rem; font-weight: 600; display: flex; align-items: center; gap: 8px;">
        <i class="fa-solid fa-triangle-exclamation"></i>
        <span>${escapeHtml(data.notice)}</span>
      </div>
    `;
  }

  // 2. 가로 5열 카드 목록 (휴대폰은 1열 목록)
  const fragment = document.createDocumentFragment();

  data.players.forEach(p => {
    const card = document.createElement("div");
    card.className = "ms-player-card";

    const gameName = escapeHtml(p.game_name || "");
    const tagLine = escapeHtml(p.tag_line || "KR1");

    if (p.found) {
      const iconId = p.profile_icon_id != null ? p.profile_icon_id : 29;
      const iconUrl = `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/${iconId}.png`;
      const levelText = p.summoner_level != null ? `${p.summoner_level}` : "";

      // 티어·LP
      const isUnranked = !p.tier || p.tier.trim() === "" || p.tier.toUpperCase() === "UNRANKED" || p.tier.includes("언랭");
      let soloTierText = "언랭크";
      let soloLpText = "";
      let emblemUrl = "";

      if (!isUnranked) {
        const tierParts = [(typeof TIER_NAMES_KR !== "undefined" && TIER_NAMES_KR[p.tier.toUpperCase()]) || p.tier];
        // 마스터 이상은 단계(I)가 없다
        if (p.rank_tier && !["MASTER", "GRANDMASTER", "CHALLENGER"].includes(p.tier.toUpperCase())) tierParts.push(p.rank_tier);
        soloTierText = tierParts.join(" ");

        if (p.league_points != null) {
          const lpNum = typeof formatNumber === "function" ? formatNumber(p.league_points) : p.league_points;
          soloLpText = `${lpNum} LP`;
        }

        if (typeof getTierEmblemUrl === "function") {
          emblemUrl = getTierEmblemUrl(p.tier);
        }
      }

      // 시즌 승률 (50% 초과 초록 #10B981, 50% 이하 빨강 #E84057)
      const wins = Number(p.wins) || 0;
      const losses = Number(p.losses) || 0;
      const totalGames = wins + losses;
      let wrVal = p.win_rate != null ? Number(p.win_rate) : (totalGames > 0 ? Math.round((wins / totalGames) * 1000) / 10 : 0);
      const hasRecord = totalGames > 0 || p.win_rate != null;
      const wrClass = wrVal > 50 ? "ms-wr-good" : "ms-wr-bad";
      const wrBarPct = Math.min(100, Math.max(0, wrVal));

      // 연승/연패 (서버가 주는 표시가 있으면 작은 배지)
      let streakBadgeHtml = "";
      if (p.streak != null && p.streak !== "") {
        const sStr = String(p.streak);
        const isWin = sStr.includes("W") || sStr.includes("승") || (typeof p.streak === "number" && p.streak > 0);
        streakBadgeHtml = `<span class="ms-streak-badge ${isWin ? 'streak-win' : 'streak-loss'}">${escapeHtml(sStr)}</span>`;
      }

      // 서버가 주는 최근 경기/모스트 챔피언 데이터 (아이콘 + 승률 + 판수)
      let collectedHtml = "";
      const col = p.collected;
      if (col && Array.isArray(col.top_champions) && col.top_champions.length > 0) {
        const champRows = col.top_champions.slice(0, 3).map(c => {
          const cWr = c.win_rate != null ? Number(c.win_rate) : 0;
          const cWrClass = cWr > 50 ? "ms-wr-good" : "ms-wr-bad";
          const cName = escapeHtml(c.name || "");
          const cImg = escapeHtml(c.image || "");
          const cGames = c.games != null ? c.games : 0;
          return `
            <div class="ms-champ-row" title="${cName} (${cGames}판 ${cWr}%)">
              <div class="ms-champ-left">
                <img src="${cImg}" alt="${cName}" title="${cName}" class="ms-champ-icon" onerror="this.style.display='none'">
              </div>
              <div class="ms-champ-stats">
                <span class="ms-champ-wr ${cWrClass}">${cWr}%</span>
                <span class="ms-champ-games">${cGames}판</span>
              </div>
            </div>
          `;
        }).join("");

        collectedHtml = `
          <div class="ms-champs-list">
            ${champRows}
          </div>
        `;
      }

      // 주 포지션 아이콘 (수집된 포지션이 있을 때만 표시)
      let posBadgeHtml = "";
      if (col && col.main_position) {
        const posMap = {
          TOP: { img: "/static/images/positions/top.png", kr: "탑" },
          JUNGLE: { img: "/static/images/positions/jungle.png", kr: "정글" },
          JUG: { img: "/static/images/positions/jungle.png", kr: "정글" },
          MIDDLE: { img: "/static/images/positions/middle.png", kr: "미드" },
          MID: { img: "/static/images/positions/middle.png", kr: "미드" },
          BOTTOM: { img: "/static/images/positions/bottom.png", kr: "원딜" },
          BOT: { img: "/static/images/positions/bottom.png", kr: "원딜" },
          UTILITY: { img: "/static/images/positions/utility.png", kr: "서포터" },
          SUP: { img: "/static/images/positions/utility.png", kr: "서포터" }
        };
        const posInfo = posMap[String(col.main_position).toUpperCase()];
        if (posInfo) {
          posBadgeHtml = `<img src="${posInfo.img}" alt="${posInfo.kr}" title="주 포지션: ${posInfo.kr}" class="ms-pos-icon">`;
        }
      }

      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.innerHTML = `
        <div class="ms-card-top">
          <div class="ms-avatar-wrap">
            <img class="ms-avatar" src="${iconUrl}" alt="${gameName}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/29.png'">
            ${levelText ? `<span class="ms-level-badge">${levelText}</span>` : ""}
          </div>
          <div class="ms-player-meta">
            <div class="ms-name-row">
              <span class="ms-player-name" title="${gameName}#${tagLine}">${gameName}</span>
              <span class="ms-player-tag">#${tagLine}</span>
            </div>
            <div class="ms-badges-row">
              ${posBadgeHtml}
              ${streakBadgeHtml}
            </div>
          </div>
        </div>

        <div class="ms-tier-section">
          ${emblemUrl ? `<img src="${emblemUrl}" alt="" class="ms-tier-emblem" onerror="this.style.display='none'">` : ""}
          <div class="ms-tier-info">
            <div class="ms-tier-name-row">
              <span class="ms-tier-name">${escapeHtml(soloTierText)}</span>
              ${soloLpText ? `<span class="ms-tier-lp">${escapeHtml(soloLpText)}</span>` : ""}
            </div>
            ${hasRecord ? `
              <div class="ms-record-row">
                <span class="ms-record-wl">${wins}승 ${losses}패</span>
                <span class="ms-record-wr ${wrClass}">${wrVal}%</span>
              </div>
              <div class="ms-wr-bar">
                <div class="ms-wr-fill" style="width: ${wrBarPct}%;"></div>
              </div>
            ` : `
              <div class="ms-record-row">
                <span class="ms-record-wl" style="color: var(--text-muted);">전적 없음</span>
              </div>
            `}
          </div>
        </div>

        ${collectedHtml}
      `;

      const handlePlayerClick = () => {
        if (typeof openPlayerDetail === "function") {
          openPlayerDetail({ game_name: p.game_name, tag_line: p.tag_line || "KR1" });
        }
      };

      card.addEventListener("click", handlePlayerClick);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handlePlayerClick();
        }
      });
    } else {
      card.className = "ms-player-card ms-player-notfound";
      card.innerHTML = `
        <div class="ms-card-top">
          <div class="ms-avatar-wrap">
            <img class="ms-avatar ms-avatar-faint" src="https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/29.png" alt="Not found">
          </div>
          <div class="ms-player-meta">
            <div class="ms-name-row">
              <span class="ms-player-name" title="${gameName}#${tagLine}">${gameName}</span>
              <span class="ms-player-tag">#${tagLine}</span>
            </div>
          </div>
        </div>
        <div class="ms-notfound-msg">
          <i class="fa-solid fa-circle-exclamation"></i>
          <span>${escapeHtml(p.error || "소환사를 찾을 수 없습니다.")}</span>
        </div>
      `;
    }

    fragment.appendChild(card);
  });

  if (cardsListEl) cardsListEl.appendChild(fragment);
}

// Spectator v5 (실시간 인게임 관전 & 라이엇 런처) Module
let spectatorTimerInterval = null;
let currentSpectatorData = null;

// 토스트 피드백 표시 함수
function showSpectatorToast(msg, isSuccess = true) {
  const toastEl = document.getElementById("spectatorToast");
  const msgEl = document.getElementById("spectatorToastMsg");
  if (!toastEl || !msgEl) {
    if (typeof showToast === "function") showToast(msg);
    return;
  }
  msgEl.textContent = msg;
  toastEl.style.display = "flex";
  toastEl.style.background = isSuccess ? "rgba(16, 185, 129, 0.95)" : "rgba(239, 68, 68, 0.95)";
  toastEl.classList.remove("fade-out");
  toastEl.classList.add("fade-in");

  clearTimeout(toastEl._timer);
  toastEl._timer = setTimeout(() => {
    toastEl.classList.remove("fade-in");
    toastEl.classList.add("fade-out");
    setTimeout(() => {
      toastEl.style.display = "none";
    }, 300);
  }, 3200);
}

let cachedSpectatorGames = [];
let spectatorFeedTimer = null;
let currentSelectedChampFilter = "all";

// 샘플(정식 키 전) 추천 게임은 실제로 진행 중인 게임이 아니라 관전할 수 없다
function isSampleSpectatorGame(gameId) {
  const match = (cachedSpectatorGames || []).find(m => String(m.game_id) === String(gameId));
  if (match && match.is_sample) {
    showSpectatorToast("샘플 경기는 관전할 수 없습니다.", false);
    return true;
  }
  return false;
}

async function copySpectatorCommand(gameId, encKey = "", cmdType = "powershell") {
  if (isSampleSpectatorGame(gameId)) return;
  try {
    let scriptObj = null;
    const match = (cachedSpectatorGames || []).find(m => String(m.game_id) === String(gameId));
    if (match && match.spectator_script) {
      scriptObj = match.spectator_script;
    } else {
      const res = await fetch(`/api/spectator/script/${encodeURIComponent(gameId)}`);
      if (res.ok) {
        scriptObj = await res.json();
      }
    }

    let textToCopy = "";
    if (cmdType === "powershell") {
      textToCopy = scriptObj?.powershell_cmd || "";
    } else if (cmdType === "bat") {
      textToCopy = scriptObj?.bat_script || "";
    } else {
      textToCopy = scriptObj?.cmd_oneliner || "";
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(textToCopy);
    } else {
      const ta = document.createElement("textarea");
      ta.value = textToCopy;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }

    showSpectatorToast("관전 명령어가 복사되었습니다.");
  } catch (err) {
    showSpectatorToast("명령어 복사 중 오류가 발생했습니다.", false);
  }
}

function copyFeaturedSpectatorCmd(gameId) {
  copySpectatorCommand(gameId, "", "powershell");
}

function downloadSpectatorBat(gameId) {
  if (isSampleSpectatorGame(gameId)) return;
  try {
    const url = `/api/spectator/download-bat/${encodeURIComponent(gameId)}`;
    const link = document.createElement("a");
    link.href = url;
    link.download = `spectator_${gameId}.bat`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showSpectatorToast(`spectator_${gameId}.bat 파일 다운로드가 시작되었습니다.`);
  } catch (err) {
    showSpectatorToast("배치파일 다운로드에 실패했습니다.", false);
  }
}

function openLolPathModal() {
  const modal = document.getElementById("modalLolPath");
  if (modal) {
    const saved = localStorage.getItem("lol_client_path") || "C:\\Riot Games\\League of Legends\\Game";
    const inp = document.getElementById("inputLolClientPath");
    if (inp) inp.value = saved;
    modal.style.display = "flex";
  }
}

function closeLolPathModal() {
  const modal = document.getElementById("modalLolPath");
  if (modal) modal.style.display = "none";
}

function saveLolClientPath() {
  const inp = document.getElementById("inputLolClientPath");
  if (inp) {
    localStorage.setItem("lol_client_path", inp.value.trim());
    showSpectatorToast("클라이언트 경로가 저장되었습니다.");
  }
  closeLolPathModal();
}

function resetLolClientPath() {
  const inp = document.getElementById("inputLolClientPath");
  if (inp) {
    inp.value = "C:\\Riot Games\\League of Legends\\Game";
    localStorage.removeItem("lol_client_path");
    showSpectatorToast("기본 경로로 복원되었습니다.");
  }
}

async function triggerSpectateGame(gameId) {
  await copySpectatorCommand(gameId, "", "powershell");
}

const SPEC_POSITIONS = {
  TOP: { file: "top", name: "탑" },
  JUNGLE: { file: "jungle", name: "정글" },
  JUG: { file: "jungle", name: "정글" },
  MID: { file: "middle", name: "미드" },
  MIDDLE: { file: "middle", name: "미드" },
  ADC: { file: "bottom", name: "원딜" },
  BOT: { file: "bottom", name: "원딜" },
  BOTTOM: { file: "bottom", name: "원딜" },
  SUPPORT: { file: "utility", name: "서포터" },
  SUP: { file: "utility", name: "서포터" },
  UTILITY: { file: "utility", name: "서포터" }
};
const SPEC_FALLBACK_POS = [SPEC_POSITIONS.TOP, SPEC_POSITIONS.JUNGLE, SPEC_POSITIONS.MID, SPEC_POSITIONS.ADC, SPEC_POSITIONS.SUPPORT];

function getSpecPosInfo(pos, posKr, idx) {
  const p = (pos || "").toUpperCase();
  if (p && SPEC_POSITIONS[p]) return SPEC_POSITIONS[p];
  if (posKr === "탑") return SPEC_POSITIONS.TOP;
  if (posKr === "정글") return SPEC_POSITIONS.JUNGLE;
  if (posKr === "미드") return SPEC_POSITIONS.MID;
  if (posKr === "원딜") return SPEC_POSITIONS.ADC;
  if (posKr === "서포터") return SPEC_POSITIONS.SUPPORT;
  return SPEC_FALLBACK_POS[idx] || SPEC_POSITIONS.MID;
}
function openSpectatorDetailModal(gameId) {
  const card = document.querySelector(`.spec-match-card[data-game-id="${gameId}"]`);
  if (!card) return;

  const btnH2h = card.querySelector(".spec-btn-h2h");
  const existingInline = card.querySelector(`.spec-inline-h2h`);

  if (existingInline) {
    if (existingInline.style.display === "none") {
      existingInline.style.display = "block";
      if (btnH2h) btnH2h.classList.add("active");
    } else {
      existingInline.style.display = "none";
      if (btnH2h) btnH2h.classList.remove("active");
    }
    return;
  }

  const match = (cachedSpectatorGames || []).find(m => String(m.game_id) === String(gameId));
  if (!match) return;

  const h2hData = match.lane_matchups || [];
  const h2hCardsHtml = h2hData.map((lm, idx) => {
    const bp = lm.blue_player || {};
    const rp = lm.red_player || {};
    const posInfo = getSpecPosInfo(lm.position, lm.pos_kr, idx);

    const bpTierUrl = (typeof getTierEmblemUrl === "function") ? getTierEmblemUrl(bp.tier) : "/static/images/tiers/iron.png";
    const rpTierUrl = (typeof getTierEmblemUrl === "function") ? getTierEmblemUrl(rp.tier) : "/static/images/tiers/iron.png";

    const bWr = lm.blue_win_rate || 50;
    const rWr = lm.red_win_rate || 50;
    const bWrCls = Number(bWr) > 50 ? "spec-wr-good" : "spec-wr-bad";
    const rWrCls = Number(rWr) > 50 ? "spec-wr-good" : "spec-wr-bad";

    return `
      <div class="spec-h2h-row">
        <div class="spec-h2h-player blue">
          <img class="spec-pos-img" src="/static/images/positions/${posInfo.file}.png" alt="${posInfo.name}" title="${posInfo.name}">
          <img class="spec-h2h-champ-img" src="${escapeHtml(bp.champ_image || '')}" alt="${escapeHtml(bp.champ_name || '')}" title="${escapeHtml(bp.champ_name || '')}">
          <div class="spec-h2h-name-box">
            <span class="spec-h2h-player-name" onclick="openPlayerDetail({game_name: ${jsArg(bp.name || bp.game_name)}, tag_line: ${jsArg(bp.tag || 'KR1')}})" title="${escapeHtml(bp.name || bp.game_name || '')}">
              ${escapeHtml(bp.name || bp.game_name || '')}
            </span>
            <span class="spec-h2h-sub-info">
              <img class="spec-tier-emblem" src="${bpTierUrl}" alt="${escapeHtml(bp.tier || '')}" title="${escapeHtml(bp.tier || '')}">
              ${bp.champ_winrate ? `<span>${bp.champ_winrate}%</span>` : ''}
            </span>
          </div>
        </div>

        <div class="spec-h2h-center">
          <div class="spec-h2h-wr-row">
            <span class="spec-wr-num blue ${bWrCls}">${bWr}%</span>
            <span class="spec-wr-num red ${rWrCls}">${rWr}%</span>
          </div>
          <div class="spec-h2h-bar" title="블루 ${bWr}% : 레드 ${rWr}%">
            <div class="spec-h2h-bar-blue" style="width: ${bWr}%;"></div>
            <div class="spec-h2h-bar-red" style="width: ${rWr}%;"></div>
          </div>
          <div class="spec-h2h-stats">
            <span>킬 ${lm.solo_kill_blue || 50}% : ${lm.solo_kill_red || 50}%</span>
            <span>15분 ${lm.gold_diff_15 >= 0 ? '+' : ''}${lm.gold_diff_15 || 0}G</span>
          </div>
        </div>

        <div class="spec-h2h-player red">
          <div class="spec-h2h-name-box red">
            <span class="spec-h2h-player-name" onclick="openPlayerDetail({game_name: ${jsArg(rp.name || rp.game_name)}, tag_line: ${jsArg(rp.tag || 'KR1')}})" title="${escapeHtml(rp.name || rp.game_name || '')}">
              ${escapeHtml(rp.name || rp.game_name || '')}
            </span>
            <span class="spec-h2h-sub-info">
              ${rp.champ_winrate ? `<span>${rp.champ_winrate}%</span>` : ''}
              <img class="spec-tier-emblem" src="${rpTierUrl}" alt="${escapeHtml(rp.tier || '')}" title="${escapeHtml(rp.tier || '')}">
            </span>
          </div>
          <img class="spec-h2h-champ-img" src="${escapeHtml(rp.champ_image || '')}" alt="${escapeHtml(rp.champ_name || '')}" title="${escapeHtml(rp.champ_name || '')}">
          <img class="spec-pos-img" src="/static/images/positions/${posInfo.file}.png" alt="${posInfo.name}" title="${posInfo.name}">
        </div>
      </div>
    `;
  }).join('');

  const inlineDiv = document.createElement("div");
  inlineDiv.className = "spec-inline-h2h";
  inlineDiv.id = `specH2h-${gameId}`;
  inlineDiv.innerHTML = `
    <div class="spec-inline-h2h-head">
      <span class="spec-inline-h2h-title"><i class="fa-solid fa-chess-knight"></i> 라인별 맞대결 상성</span>
      <div class="spec-inline-h2h-actions">
        <button type="button" class="spec-btn-action" onclick="copySpectatorCommand(${jsArg(match.game_id)}, '', 'powershell')">
          <i class="fa-solid fa-copy"></i> 명령어 복사
        </button>
        <button type="button" class="btn-secondary spec-btn-secondary" onclick="downloadSpectatorBat(${jsArg(match.game_id)})">
          <i class="fa-solid fa-download"></i> .bat 다운로드
        </button>
      </div>
    </div>
    <div class="spec-h2h-list">
      ${h2hCardsHtml}
    </div>
  `;
  card.appendChild(inlineDiv);
  if (btnH2h) btnH2h.classList.add("active");
}

function closeSpectatorDetailModal() {
  // no-op for backward compatibility
}

function renderSpectatorPlayerRow(p, isRed = false, idx = 0) {
  const posInfo = getSpecPosInfo(p.position, p.pos_kr, idx);
  const posHtml = `<img class="spec-pos-img" src="/static/images/positions/${posInfo.file}.png" alt="${posInfo.name}" title="${posInfo.name}">`;

  const ddrVer = typeof DDRAGON_VER !== "undefined" ? DDRAGON_VER : "14.20.1";
  const champImg = p.champ_image || `https://ddragon.leagueoflegends.com/cdn/${ddrVer}/img/champion/${p.champ_id || 'Jax'}.png`;
  const champName = escapeHtml(p.champ_name || p.champ_id || "");
  const champHtml = `
    <div class="spec-champ-portrait" title="${champName}">
      <img class="spec-champ-img" src="${champImg}" alt="${champName}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/${ddrVer}/img/champion/Jax.png'">
      ${p.champ_level ? `<span class="spec-champ-lvl">${p.champ_level}</span>` : ""}
    </div>
  `;

  const sp1Icon = p.spell1?.icon || "";
  const sp1Name = escapeHtml(p.spell1?.name || "");
  const sp2Icon = p.spell2?.icon || "";
  const sp2Name = escapeHtml(p.spell2?.name || "");
  const spellsHtml = `
    <div class="spec-spells-col">
      ${sp1Icon ? `<img class="spec-spell-img" src="${sp1Icon}" alt="${sp1Name}" title="${sp1Name}">` : ""}
      ${sp2Icon ? `<img class="spec-spell-img" src="${sp2Icon}" alt="${sp2Name}" title="${sp2Name}">` : ""}
    </div>
  `;

  const kIcon = p.keystone?.icon || "";
  const kName = escapeHtml(p.keystone?.name || "");
  const sIcon = p.sub_style?.icon || "";
  const sName = escapeHtml(p.sub_style?.name || "");
  const runesHtml = (kIcon || sIcon) ? `
    <div class="spec-runes-col">
      ${kIcon ? `<img class="spec-rune-img" src="${kIcon}" alt="${kName}" title="${kName}">` : ""}
      ${sIcon ? `<img class="spec-subrune-img" src="${sIcon}" alt="${sName}" title="${sName}">` : ""}
    </div>
  ` : "";

  const gname = escapeHtml(p.game_name || "");
  const tag = escapeHtml(p.tag_line || "KR1");
  const nameHtml = `
    <div class="spec-player-identity">
      <span class="spec-player-name" data-gn="${gname}" data-tag="${tag}" title="${gname}#${tag}">
        ${gname}
      </span>
      <span class="spec-player-tag">#${tag}</span>
    </div>
  `;

  const tierStr = p.tier || p.tier_short || "UNRANKED";
  const tierUrl = (typeof getTierEmblemUrl === "function") ? getTierEmblemUrl(tierStr) : "/static/images/tiers/iron.png";
  const tierHtml = `
    <div class="spec-tier-wrap" title="${escapeHtml(tierStr)}">
      <img class="spec-tier-emblem" src="${tierUrl}" alt="${escapeHtml(tierStr)}">
    </div>
  `;

  return `
    <div class="spec-player-row ${isRed ? 'red' : 'blue'}${p.is_me ? ' is-me' : ''}">
      ${posHtml}
      ${champHtml}
      ${spellsHtml}
      ${runesHtml}
      ${nameHtml}
      ${tierHtml}
    </div>
  `;
}

function renderSpectatorFeed(matches) {
  const container = document.getElementById("spectatorFeedContainer");
  if (!container) return;

  const countBadge = document.getElementById("specLiveCountBadge");
  if (countBadge) {
    const liveCount = (matches && Array.isArray(matches)) ? matches.length : 0;
    countBadge.textContent = `LIVE ${liveCount}개`;
  }

  if (!matches || matches.length === 0) {
    container.innerHTML = `
      <div class="spec-empty-feed">
        <i class="fa-solid fa-circle-exclamation"></i>
        <div>해당 조건에 일치하는 진행 중인 인게임이 없습니다.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = matches.map((m) => {
    const bluePlayers = (m.blue_team || []).map((p, pIdx) => renderSpectatorPlayerRow(p, false, pIdx)).join('');
    const redPlayers = (m.red_team || []).map((p, pIdx) => renderSpectatorPlayerRow(p, true, pIdx)).join('');

    const bansHtml = (m.bans_blue?.length > 0 || m.bans_red?.length > 0) ? `
      <div class="spec-bans-wrap">
        <div class="spec-bans-side blue" title="블루팀 밴">
          ${(m.bans_blue || []).map(b => `<div class="spec-ban-slot" title="블루 밴: ${escapeHtml(b.name || '')}"><img class="spec-ban-img" src="${b.image}" alt="${escapeHtml(b.name || '')}"><span class="spec-ban-slash"></span></div>`).join('')}
        </div>
        <span class="spec-bans-sep">BANS</span>
        <div class="spec-bans-side red" title="레드팀 밴">
          ${(m.bans_red || []).map(b => `<div class="spec-ban-slot" title="레드 밴: ${escapeHtml(b.name || '')}"><img class="spec-ban-img" src="${b.image}" alt="${escapeHtml(b.name || '')}"><span class="spec-ban-slash"></span></div>`).join('')}
        </div>
      </div>
    ` : '';

    const durMin = Math.floor((m.elapsed_seconds || 0) / 60);
    const durSec = (m.elapsed_seconds || 0) % 60;
    const timeFormatted = `${durMin < 10 ? '0' : ''}${durMin}:${durSec < 10 ? '0' : ''}${durSec}`;
    const cleanGameMode = m.game_mode || "솔로랭크";

    return `
      <div class="spec-match-card" data-game-id="${m.game_id}">
        <div class="spec-card-head">
          <div class="spec-head-left">
            <span class="spec-queue-badge">${escapeHtml(cleanGameMode)}</span>
            <span class="spec-time-badge">
              <span class="live-dot-pulse"></span>
              <span class="spec-elapsed-timer" id="fowTimer-${m.game_id}" data-elapsed="${m.elapsed_seconds}">${timeFormatted}</span>
            </span>
          </div>
          ${bansHtml}
          <div class="spec-head-actions">
            <button type="button" class="spec-btn-action" onclick="triggerSpectateGame(${jsArg(m.game_id)})" title="인게임 관전 실행">
              <i class="fa-solid fa-play"></i> 관전
            </button>
            <button type="button" class="spec-btn-h2h" onclick="openSpectatorDetailModal(${jsArg(m.game_id)})" title="라인별 맞대결 상성">
              <i class="fa-solid fa-chess-knight"></i> 맞대결
            </button>
          </div>
        </div>
        <div class="spec-teams-grid">
          <div class="spec-team-col blue">
            <div class="spec-team-head blue">
              <span class="spec-team-side"><span class="spec-team-dot blue"></span>블루팀</span>
              ${m.blue_avg_wr ? `<span class="spec-team-avg-wr">${m.blue_avg_wr}%</span>` : ''}
            </div>
            <div class="spec-team-rows">
              ${bluePlayers}
            </div>
          </div>
          <div class="spec-team-col red">
            <div class="spec-team-head red">
              <span class="spec-team-side"><span class="spec-team-dot red"></span>레드팀</span>
              ${m.red_avg_wr ? `<span class="spec-team-avg-wr">${m.red_avg_wr}%</span>` : ''}
            </div>
            <div class="spec-team-rows">
              ${redPlayers}
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  container.querySelectorAll(".spec-player-name").forEach(link => {
    link.addEventListener("click", () => {
      const gn = link.getAttribute("data-gn");
      const tag = link.getAttribute("data-tag") || "KR1";
      if (gn && typeof openPlayerDetail === "function") {
        openPlayerDetail({ game_name: gn, tag_line: tag });
      }
    });
  });
}

function updateFeedTimers() {
  const timerEls = document.querySelectorAll(".spec-elapsed-timer, .fow-elapsed-timer");
  timerEls.forEach(el => {
    let cur = parseInt(el.getAttribute("data-elapsed") || "0", 10);
    cur++;
    el.setAttribute("data-elapsed", String(cur));
    const m = Math.floor(cur / 60);
    const s = cur % 60;
    el.textContent = `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
  });
}

function populateChampionFilterDropdown(matches) {
  const listEl = document.getElementById("specChampList");
  if (!listEl) return;

  const champMap = new Map();
  (matches || []).forEach(m => {
    (m.blue_team || []).concat(m.red_team || []).forEach(p => {
      if (p.champ_name && !champMap.has(p.champ_name)) {
        champMap.set(p.champ_name, {
          name: p.champ_name,
          id: p.champ_id,
          image: p.champ_image
        });
      }
    });
  });

  const sortedChamps = Array.from(champMap.values()).sort((a, b) => a.name.localeCompare(b.name, 'ko'));

  listEl.innerHTML = sortedChamps.map(c => `
    <div class="spec-champ-filter-item fow-champ-filter-item" data-champ="${c.name}">
      <img src="${c.image}" alt="${c.name}">
      <span>${c.name}</span>
    </div>
  `).join('');

  listEl.querySelectorAll(".spec-champ-filter-item, .fow-champ-filter-item").forEach(item => {
    item.addEventListener("click", () => {
      const cName = item.getAttribute("data-champ");
      filterFeedByChampion(cName);
      const menu = document.getElementById("specChampDropdown");
      if (menu) menu.style.display = "none";
    });
  });
}

function filterFeedByChampion(champName) {
  currentSelectedChampFilter = champName;
  const labelEl = document.getElementById("specChampFilterLabel");
  if (labelEl) {
    labelEl.textContent = (champName === "all") ? "챔피언 필터" : champName;
  }

  if (champName === "all") {
    renderSpectatorFeed(cachedSpectatorGames);
  } else {
    const filtered = cachedSpectatorGames.filter(m => {
      const allPlayers = (m.blue_team || []).concat(m.red_team || []);
      return allPlayers.some(p => p.champ_name === champName);
    });
    renderSpectatorFeed(filtered);
  }
}

let specAutoRefreshCountdown = 30;
let isSpecAutoRefreshActive = true;
let specAutoRefreshInterval = null;

async function refreshSpectatorFeed(silent = false) {
  const btn = document.getElementById("btnRefreshSpecFeed");
  const icon = btn ? btn.querySelector("i") : null;
  if (icon) icon.classList.add("fa-spin");
  if (btn) btn.disabled = true;

  try {
    const res = await fetch("/api/spectator/featured");
    if (res.ok) {
      const data = await res.json();
      cachedSpectatorGames = data.featured || [];
      if (currentSelectedChampFilter && currentSelectedChampFilter !== "all") {
        filterFeedByChampion(currentSelectedChampFilter);
      } else {
        renderSpectatorFeed(cachedSpectatorGames);
      }
      populateChampionFilterDropdown(cachedSpectatorGames);
      if (!silent) {
        showSpectatorToast("실시간 관전 피드가 최신 상태로 갱신되었습니다.", true);
      }
    } else {
      if (!silent) showSpectatorToast("피드를 새로고침할 수 없습니다.", false);
    }
  } catch (err) {
    if (!silent) showSpectatorToast("피드 새로고침 중 네트워크 오류가 발생했습니다.", false);
  } finally {
    if (icon) {
      setTimeout(() => {
        icon.classList.remove("fa-spin");
        if (btn) btn.disabled = false;
      }, 400);
    } else if (btn) {
      btn.disabled = false;
    }
  }
}

async function initSpectator() {
  if (!document.getElementById("specStylesheet") && !document.querySelector('link[href*="21-spectator.css"]')) {
    const link = document.createElement("link");
    link.id = "specStylesheet";
    link.rel = "stylesheet";
    link.href = "/static/css/app/21-spectator.css";
    document.head.appendChild(link);
  }

  // 추천 경기 피드는 정식 키 전까지 샘플(is_sample, 실존 인물 이름 제거)이며 화면에 샘플 배너를 띄운다
  const loadingEl = document.getElementById("specFeedLoading");
  if (loadingEl) loadingEl.style.display = "block";

  const btnRegion = document.getElementById("btnSpecRegion");
  const regionMenu = document.getElementById("specRegionMenu");
  if (btnRegion && regionMenu) {
    btnRegion.onclick = (e) => {
      e.stopPropagation();
      const isVisible = regionMenu.style.display === "block";
      const champDropdown = document.getElementById("specChampDropdown");
      if (champDropdown) champDropdown.style.display = "none";
      regionMenu.style.display = isVisible ? "none" : "block";
    };
  }

  const regionItems = document.querySelectorAll("#specRegionMenu .spec-dd-item, #specRegionMenu .fow-dd-item");
  regionItems.forEach(item => {
    item.onclick = (e) => {
      e.stopPropagation();
      const reg = item.getAttribute("data-region") || "KR";
      const label = document.getElementById("specRegionLabel");
      if (label) label.textContent = reg;
      regionItems.forEach(i => i.classList.remove("active"));
      item.classList.add("active");
      if (regionMenu) regionMenu.style.display = "none";
      showSpectatorToast(`[${reg}] 지역 실시간 피드로 전환되었습니다.`, true);
    };
  });

  const btnChampFilter = document.getElementById("btnSpecChampFilter");
  const champDropdown = document.getElementById("specChampDropdown");
  if (champDropdown) {
    champDropdown.addEventListener("click", (e) => {
      e.stopPropagation();
    });
  }
  if (regionMenu) {
    regionMenu.addEventListener("click", (e) => {
      e.stopPropagation();
    });
  }
  if (btnChampFilter && champDropdown) {
    btnChampFilter.onclick = (e) => {
      e.stopPropagation();
      const isVisible = champDropdown.style.display === "flex";
      if (regionMenu) regionMenu.style.display = "none";
      champDropdown.style.display = isVisible ? "none" : "flex";
      if (!isVisible && champSearchInput) {
        setTimeout(() => champSearchInput.focus(), 50);
      }
    };
  }

  const champSearchInput = document.getElementById("specChampSearchInput");
  if (champSearchInput) {
    champSearchInput.oninput = () => {
      const q = champSearchInput.value.trim().toLowerCase();
      const items = document.querySelectorAll(".spec-champ-filter-item, .fow-champ-filter-item");
      items.forEach(it => {
        const txt = it.textContent.trim().toLowerCase();
        it.style.display = txt.includes(q) ? "flex" : "none";
      });
    };
  }

  const allItem = document.querySelector('.spec-dd-item[data-champ="all"], .fow-dd-item[data-champ="all"]');
  if (allItem) {
    allItem.onclick = () => {
      filterFeedByChampion("all");
      if (champDropdown) champDropdown.style.display = "none";
    };
  }

  const btnRefresh = document.getElementById("btnRefreshSpecFeed");
  const btnAutoToggle = document.getElementById("btnToggleSpecAutoRefresh");
  const specText = document.getElementById("specAutoRefreshStatusText");
  const specBadge = document.getElementById("specCountdownBadge");

  function resetSpecCountdown() {
    specAutoRefreshCountdown = 30;
    if (specBadge && isSpecAutoRefreshActive) specBadge.textContent = "30s";
  }

  if (btnRefresh) {
    btnRefresh.onclick = () => {
      refreshSpectatorFeed();
      resetSpecCountdown();
    };
  }

  if (btnAutoToggle) {
    btnAutoToggle.onclick = () => {
      try {
        if (typeof navigator !== "undefined" && navigator.vibrate) {
          navigator.vibrate(10);
        }
      } catch (_) {}

      isSpecAutoRefreshActive = !isSpecAutoRefreshActive;
      if (isSpecAutoRefreshActive) {
        btnAutoToggle.classList.add("active");
        btnAutoToggle.classList.remove("paused");
        if (specText) specText.textContent = "LIVE";
        resetSpecCountdown();
        showSpectatorToast("30초 자동 새로고침이 활성화되었습니다 (LIVE).", true);
      } else {
        btnAutoToggle.classList.remove("active");
        btnAutoToggle.classList.add("paused");
        if (specText) specText.textContent = "PAUSED";
        if (specBadge) specBadge.textContent = "--";
        showSpectatorToast("30초 자동 새로고침이 일시 정지되었습니다.", false);
      }
    };
  }

  if (specAutoRefreshInterval) clearInterval(specAutoRefreshInterval);
  specAutoRefreshInterval = setInterval(() => {
    if (!isSpecAutoRefreshActive) return;
    if (document.hidden) return; // 절전 모드: 브라우저 탭 비활성화 시 백그라운드 호출 방지
    // 앱 내 타 탭 이동 시 불필요한 백그라운드 폴링 및 DOM 리렌더링 차단 (성능/네트워크 최적화)
    const specView = document.getElementById("viewSpectator");
    if (specView && (specView.style.display === "none" || specView.classList.contains("hidden") || !specView.classList.contains("active"))) return;

    specAutoRefreshCountdown--;
    if (specBadge) specBadge.textContent = `${specAutoRefreshCountdown}s`;
    if (specAutoRefreshCountdown <= 0) {
      resetSpecCountdown();
      refreshSpectatorFeed(true);
    }
  }, 1000);

  // 브라우저 탭 전환 절전 모드 방어 (Design Spec 5.3)
  if (!window._specVisibilityBound) {
    window._specVisibilityBound = true;
    document.addEventListener("visibilitychange", () => {
      if (typeof document === "undefined") return;
      if (document.body) {
        document.body.classList.toggle("tab-hidden", document.hidden);
      }
      if (!document.hidden && isSpecAutoRefreshActive) {
        const specView = document.getElementById("viewSpectator");
        if (specView && specView.style.display !== "none") {
          resetSpecCountdown();
          refreshSpectatorFeed(true);
        }
      }
    });
  }

  const btnPath = document.getElementById("btnSpecPathSettings");
  if (btnPath) {
    btnPath.onclick = () => openLolPathModal();
  }

  document.addEventListener("click", () => {
    if (regionMenu) regionMenu.style.display = "none";
    if (champDropdown) champDropdown.style.display = "none";
  });

  try {
    const res = await fetch("/api/spectator/featured");
    if (res.ok) {
      const data = await res.json();
      cachedSpectatorGames = data.featured || [];
      if (loadingEl) loadingEl.style.display = "none";
      renderSpectatorFeed(cachedSpectatorGames);
      populateChampionFilterDropdown(cachedSpectatorGames);

      if (spectatorFeedTimer) clearInterval(spectatorFeedTimer);
      spectatorFeedTimer = setInterval(updateFeedTimers, 1000);
    }
  } catch (err) {
    if (loadingEl) loadingEl.style.display = "none";
  }
}

window.showSpectatorToast = showSpectatorToast;
window.copySpectatorCommand = copySpectatorCommand;
window.copyFeaturedSpectatorCmd = copyFeaturedSpectatorCmd;
window.downloadSpectatorBat = downloadSpectatorBat;
window.triggerSpectateGame = triggerSpectateGame;
window.openSpectatorDetailModal = openSpectatorDetailModal;
window.closeSpectatorDetailModal = closeSpectatorDetailModal;
window.openLolPathModal = openLolPathModal;
window.closeLolPathModal = closeLolPathModal;
window.saveLolClientPath = saveLolClientPath;
window.resetLolClientPath = resetLolClientPath;
window.refreshSpectatorFeed = refreshSpectatorFeed;
window.initSpectator = initSpectator;
window.loadFeaturedSpectator = function(featuredId) {
  openSpectatorDetailModal(featuredId);
};
