// 3-Patch Continuous Vertical Feed Patch Notes Modal Module
const OFFICIAL_PATCH_NOTES_URL = "https://www.leagueoflegends.com/ko-kr/news/tags/patch-notes/";
function openPatchNotesModal() {
  window.open(OFFICIAL_PATCH_NOTES_URL, "_blank", "noopener");
}
window.openPatchNotesModal = openPatchNotesModal;

function initPatchNotesModal() {
  const openBtn = document.getElementById("btnOpenPatchNotes");
  const bannerBtn = document.getElementById("bannerPatchBtn");
  const closeBtn = document.getElementById("btnClosePatchNotesModal");
  const modal = document.getElementById("patchNotesModal");

  // 사이트 자체 패치노트 요약은 생성 데이터였으므로, 라이엇 공식 패치노트로 연결한다
  const handleOpen = () => openPatchNotesModal();

  if (openBtn) openBtn.addEventListener("click", handleOpen);
  if (bannerBtn) bannerBtn.addEventListener("click", handleOpen);

  if (closeBtn && modal) {
    closeBtn.addEventListener("click", () => {
      modal.classList.remove("active");
      modal.classList.remove("open");
    });
  }

  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) {
        modal.classList.remove("active");
        modal.classList.remove("open");
      }
    });
  }
}


// Initialize patch modal on script load
initPatchNotesModal();
// 1:1 Champion Matchup (1:1 챔피언 상성 매치업 & 카운터 분석)
function getChampDdragonImgUrl(c) {
  if (!c) return "";
  if (typeof c === "string") {
    if (c.startsWith("http") || c.startsWith("/")) return c;
    return `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/${c}.png`;
  }
  if (c.image) {
    if (c.image.startsWith("http") || c.image.startsWith("/")) return c.image;
    return `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/${c.image}`;
  }
  if (c.id) {
    return `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/${c.id}.png`;
  }
  return "";
}

function findChampionFromCache(query) {
  if (!query) return null;
  const list = (typeof allChampionsCache !== "undefined" && allChampionsCache && allChampionsCache.length > 0)
    ? allChampionsCache
    : [];
  const q = String(query).trim().toLowerCase().replace(/\s+/g, "");
  if (!q) return null;
  return list.find(c =>
    (c.name && c.name.toLowerCase().replace(/\s+/g, "") === q) ||
    (c.id && c.id.toLowerCase() === q)
  ) || null;
}

function updateMatchupChampIcon(inputEl, imgEl, placeholderEl) {
  if (!inputEl) return;
  const val = inputEl.value.trim();
  const champ = findChampionFromCache(val);
  if (champ) {
    const url = getChampDdragonImgUrl(champ);
    if (imgEl) {
      imgEl.src = url;
      imgEl.alt = champ.name;
      imgEl.title = champ.name;
      imgEl.style.display = "block";
    }
    if (placeholderEl) placeholderEl.style.display = "none";
  } else {
    if (imgEl) {
      imgEl.style.display = "none";
      imgEl.src = "";
    }
    if (placeholderEl) placeholderEl.style.display = "flex";
  }
}

function setMatchupIconDirect(imgEl, placeholderEl, imgUrl, name) {
  if (!imgUrl) return;
  if (imgEl) {
    imgEl.src = imgUrl;
    imgEl.alt = name || "";
    imgEl.title = name || "";
    imgEl.style.display = "block";
  }
  if (placeholderEl) placeholderEl.style.display = "none";
}

function initChampionMatchup() {
  const btnCompare = document.getElementById("btnCompareMatchup");
  const btnAnalyze = document.getElementById("btnAnalyzeCounters");
  const c1Input = document.getElementById("matchupChamp1Input");
  const c2Input = document.getElementById("matchupChamp2Input");
  const img1 = document.getElementById("matchupChamp1Img");
  const p1 = document.getElementById("matchupChamp1Placeholder");
  const img2 = document.getElementById("matchupChamp2Img");
  const p2 = document.getElementById("matchupChamp2Placeholder");
  const btnSwap = document.getElementById("btnSwapMatchupChamps");

  const syncIcons = () => {
    updateMatchupChampIcon(c1Input, img1, p1);
    updateMatchupChampIcon(c2Input, img2, p2);
  };

  if (typeof allChampionsCache === "undefined" || !allChampionsCache || allChampionsCache.length === 0) {
    if (typeof loadChampionsList === "function") {
      loadChampionsList().then(syncIcons).catch(() => {});
    } else {
      fetch("/api/champions")
        .then(r => r.json())
        .then(d => {
          if (d && d.champions) {
            allChampionsCache = d.champions;
            allChampionsCache.sort((a, b) => a.name.localeCompare(b.name, "ko"));
            syncIcons();
          }
        })
        .catch(() => {});
    }
  } else {
    syncIcons();
  }

  if (btnCompare) {
    btnCompare.addEventListener("click", () => {
      const c1 = c1Input ? c1Input.value.trim() : "";
      const c2 = c2Input ? c2Input.value.trim() : "";
      if (!c1) {
        showToast("첫 번째 챔피언을 입력해주세요.");
        return;
      }
      performMatchupCompare(c1, c2);
    });
  }

  if (btnAnalyze) {
    btnAnalyze.addEventListener("click", () => {
      const c1 = c1Input ? c1Input.value.trim() : "";
      if (!c1) {
        showToast("분석할 챔피언을 입력해주세요.");
        return;
      }
      if (c2Input) {
        c2Input.value = "";
        updateMatchupChampIcon(c2Input, img2, p2);
      }
      performMatchupCompare(c1, "");
    });
  }

  // Swap Champions 1 ↔ 2
  if (btnSwap) {
    btnSwap.addEventListener("click", () => {
      const v1 = c1Input ? c1Input.value.trim() : "";
      const v2 = c2Input ? c2Input.value.trim() : "";
      if (!v1 && !v2) return;
      if (!v2) {
        showToast("상대 챔피언을 먼저 선택해 주세요.");
        return;
      }
      if (c1Input) c1Input.value = v2;
      if (c2Input) c2Input.value = v1;
      syncIcons();
      btnSwap.style.transform = "rotate(180deg)";
      setTimeout(() => { btnSwap.style.transform = "rotate(0deg)"; }, 250);
      performMatchupCompare(v2, v1);
    });
  }

  // 168개 챔피언 실시간 한글 자동완성 드롭다운
  const setupChampAuto = (inputEl, dropEl, targetImg, targetPlaceholder) => {
    if (!inputEl || !dropEl) return;

    const filterAndRender = () => {
      const val = inputEl.value.trim();
      updateMatchupChampIcon(inputEl, targetImg, targetPlaceholder);

      if (!val) {
        dropEl.style.display = "none";
        dropEl.innerHTML = "";
        return;
      }

      const list = (typeof allChampionsCache !== "undefined" && allChampionsCache && allChampionsCache.length > 0)
        ? allChampionsCache
        : [];

      const matcher = typeof matchesChampion === "function"
        ? matchesChampion
        : (c, q) => {
            const cleanQ = q.toLowerCase().replace(/\s+/g, "");
            return (c.name && c.name.toLowerCase().replace(/\s+/g, "").includes(cleanQ)) ||
                   (c.id && c.id.toLowerCase().includes(cleanQ));
          };

      const matches = list.filter(c => matcher(c, val)).slice(0, 8);

      if (matches.length === 0) {
        dropEl.style.display = "none";
        dropEl.innerHTML = "";
        return;
      }

      dropEl.innerHTML = matches.map(m => {
        const url = getChampDdragonImgUrl(m);
        return `
          <div class="matchup-auto-item" data-name="${escapeHtml(m.name)}" data-id="${escapeHtml(m.id)}">
            <img src="${escapeHtml(url)}" alt="${escapeHtml(m.name)}" class="matchup-auto-thumb">
            <div class="matchup-auto-info">
              <span class="matchup-auto-name">${escapeHtml(m.name)}</span>
              <span class="matchup-auto-title">${escapeHtml(m.title || "")}</span>
            </div>
          </div>
        `;
      }).join("");
      dropEl.style.display = "block";

      dropEl.querySelectorAll(".matchup-auto-item").forEach(item => {
        item.addEventListener("click", () => {
          const pickedName = item.getAttribute("data-name");
          inputEl.value = pickedName;
          updateMatchupChampIcon(inputEl, targetImg, targetPlaceholder);
          dropEl.style.display = "none";
          const c1 = c1Input ? c1Input.value.trim() : "";
          const c2 = c2Input ? c2Input.value.trim() : "";
          if (c1) performMatchupCompare(c1, c2);
        });
      });
    };

    inputEl.addEventListener("input", filterAndRender);
    inputEl.addEventListener("focus", () => {
      if (inputEl.value.trim()) filterAndRender();
    });

    inputEl.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        dropEl.style.display = "none";
        const c1 = c1Input ? c1Input.value.trim() : "";
        const c2 = c2Input ? c2Input.value.trim() : "";
        if (c1) performMatchupCompare(c1, c2);
      }
    });

    document.addEventListener("click", (e) => {
      if (!inputEl.contains(e.target) && !dropEl.contains(e.target)) {
        dropEl.style.display = "none";
      }
    });
  };

  setupChampAuto(c1Input, document.getElementById("matchupAuto1"), img1, p1);
  setupChampAuto(c2Input, document.getElementById("matchupAuto2"), img2, p2);

  document.querySelectorAll(".btn-matchup-preset").forEach(btn => {
    btn.addEventListener("click", () => {
      const c1 = btn.dataset.c1;
      const c2 = btn.dataset.c2 || "";
      if (c1Input) c1Input.value = c1;
      if (c2Input) c2Input.value = c2;
      syncIcons();
      performMatchupCompare(c1, c2);
    });
  });

  performMatchupCompare("야스오", "요네");
}

function openMatchupWithChampions(c1, c2) {
  if (typeof switchMainTab === "function") {
    switchMainTab('matchup');
  }
  const c1Input = document.getElementById("matchupChamp1Input");
  const c2Input = document.getElementById("matchupChamp2Input");
  if (c1Input && c1) c1Input.value = c1;
  if (c2Input) c2Input.value = c2 || "";
  const img1 = document.getElementById("matchupChamp1Img");
  const p1 = document.getElementById("matchupChamp1Placeholder");
  const img2 = document.getElementById("matchupChamp2Img");
  const p2 = document.getElementById("matchupChamp2Placeholder");
  if (typeof updateMatchupChampIcon === "function") {
    updateMatchupChampIcon(c1Input, img1, p1);
    updateMatchupChampIcon(c2Input, img2, p2);
  }
  performMatchupCompare(c1, c2 || "");
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
window.openMatchupWithChampions = openMatchupWithChampions;

async function performMatchupCompare(c1, c2) {
  if (c1 && c2 && c1.trim().toLowerCase() === c2.trim().toLowerCase()) {
    showToast("서로 다른 챔피언을 선택해 주세요.");
    return;
  }
  const loadingEl = document.getElementById("matchupLoading");
  const cardEl = document.getElementById("matchupResultCard");

  if (loadingEl) loadingEl.style.display = "block";
  if (cardEl) cardEl.style.display = "none";

  try {
    let url = `/api/champion-matchup?champ1=${encodeURIComponent(c1)}`;
    if (c2) url += `&champ2=${encodeURIComponent(c2)}`;

    const res = await fetch(url);
    const data = await res.json();

    if (loadingEl) loadingEl.style.display = "none";

    if (!res.ok || data.status === "error") {
      showToast(data.detail || data.message || "매치업 데이터를 찾을 수 없습니다.");
      return;
    }

    const img1 = document.getElementById("matchupChamp1Img");
    const p1 = document.getElementById("matchupChamp1Placeholder");
    const img2 = document.getElementById("matchupChamp2Img");
    const p2 = document.getElementById("matchupChamp2Placeholder");
    if (data.mode === "head_to_head") {
      if (data.champ_a && data.champ_a.image) setMatchupIconDirect(img1, p1, data.champ_a.image, data.champ_a.name);
      if (data.champ_b && data.champ_b.image) setMatchupIconDirect(img2, p2, data.champ_b.image, data.champ_b.name);
    } else if (data.mode === "counters") {
      if (data.champion && data.champion.image) setMatchupIconDirect(img1, p1, data.champion.image, data.champion.name);
      if (img2) { img2.style.display = "none"; img2.src = ""; }
      if (p2) p2.style.display = "flex";
    }

    if (cardEl) {
      cardEl.style.display = "block";
      cardEl.classList.add("active");
      renderMatchupResult(data);
    }
  } catch (err) {
    if (loadingEl) loadingEl.style.display = "none";
    showToast("상성 데이터 분석 중 오류가 발생했습니다.");
  }
}
// Community Counter Board (집단지성 카운터 팁 & 투표 모듈)
let currentCommunitySort = 'popular';
let currentCommunityCategory = 'all';
let currentCommunityTier = 'all';
let currentCommunityPosition = 'ALL';

function getTierBadgeClass(tier) {
  if (!tier) return 'default';
  const t = String(tier).toLowerCase();
  if (t.includes('챌린저') || t.includes('challenger')) return 'challenger';
  if (t.includes('그랜드마스터') || t.includes('grandmaster')) return 'grandmaster';
  if (t.includes('마스터') || t.includes('master')) return 'master';
  if (t.includes('다이아') || t.includes('diamond')) return 'diamond';
  if (t.includes('에메랄드') || t.includes('emerald')) return 'emerald';
  if (t.includes('플래티넘') || t.includes('platinum')) return 'platinum';
  return 'default';
}

function getStoredVotes() {
  try {
    return JSON.parse(localStorage.getItem('cct_voted_tips') || '{}');
  } catch(e) {
    return {};
  }
}

function setStoredVote(tipId, voteType) {
  try {
    const votes = getStoredVotes();
    votes[tipId] = voteType;
    localStorage.setItem('cct_voted_tips', JSON.stringify(votes));
  } catch(e) {}
}

function renderCommunityTipCardsHtml(tips) {
  if (!tips || tips.length === 0) {
    return `
      <div class="cb-empty-state" style="text-align: center; padding: 2.5rem 1rem; color: var(--text-muted); border-radius: 8px; border: 1px dashed var(--border-color);">
        <i class="fa-solid fa-comments" style="font-size: 2rem; margin-bottom: 10px; display: block; color: var(--text-muted);"></i>
        <div style="font-size: 0.95rem; font-weight: 700; color: var(--text-heading);">아직 팁이 없습니다.</div>
        <div style="height: 12px;"></div>
        <button class="cb-btn-write-toggle" style="margin: 0 auto;" onclick="toggleCommunityWriteForm(true)">
          <i class="fa-solid fa-pen-to-square"></i> 첫 공략 작성하기
        </button>
      </div>
    `;
  }

  const storedVotes = getStoredVotes();

  return tips.map(tip => {
    const isBest = tip.is_best || tip.score >= 50;
    const myVote = storedVotes[tip.id] || null;
    const upVotedClass = myVote === 'up' ? 'voted' : '';
    const downVotedClass = myVote === 'down' ? 'voted' : '';
    const scoreColorClass = tip.score > 0 ? 'positive' : (tip.score < 0 ? 'negative' : '');
    const scoreText = tip.score > 0 ? `+${tip.score}` : `${tip.score}`;
    const catClass = tip.category || 'lane';
    const catLabel = tip.category_label || (catClass === 'lane' ? '라인전 상성' : (catClass === 'skill' ? '스킬 활용' : '한타 구도'));
    const catIcon = tip.category_icon || (catClass === 'lane' ? 'fa-swords' : (catClass === 'skill' ? 'fa-bullseye' : 'fa-shield-halved'));

    return `
      <div class="cb-tip-card ${isBest ? 'is-best' : ''}" id="cbTipCard_${tip.id}">
        <div class="cb-tip-top">
          <div class="cb-author-info">
            <span class="cb-cat-badge ${escapeHtml(catClass)}">
              <i class="fa-solid ${escapeHtml(catIcon)}"></i> ${escapeHtml(catLabel)}
            </span>
            <span class="cb-author-name">익명 소환사</span>
            ${tip.perspective ? `<span class="cb-perspective-badge">${escapeHtml(tip.perspective)}</span>` : ''}
            ${tip.position && tip.position !== 'ALL' ? `<span class="badge-pill" style="font-size: 0.7rem; padding: 2px 6px;">${escapeHtml(tip.position)}</span>` : ''}
            ${isBest ? `<span class="cb-best-tag"><i class="fa-solid fa-crown"></i> BEST 추천 꿀팁</span>` : ''}
          </div>
          <span class="cb-time-text">${escapeHtml(tip.created_at || '')}</span>
        </div>

        <div class="cb-tip-content">
          ${escapeHtml(tip.content)}
        </div>

        <div class="cb-tip-bottom">
          <div class="cb-vote-actions">
            <button class="cb-vote-btn up ${upVotedClass}" onclick="handleCommunityVote(${tip.id}, 'up', this)" title="이 공략 추천">
              <i class="fa-solid fa-thumbs-up"></i>
              <span class="cb-vote-count up-count">${tip.upvotes}</span>
            </button>
            <button class="cb-vote-btn down ${downVotedClass}" onclick="handleCommunityVote(${tip.id}, 'down', this)" title="비추천">
              <i class="fa-solid fa-thumbs-down"></i>
              <span class="cb-vote-count down-count">${tip.downvotes}</span>
            </button>
            <span class="cb-score-pill ${scoreColorClass}">순 추천: ${scoreText}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function generateCommunityBoardHtml(champ1, champ2, tips, totalCount, categoryCounts) {
  const c1Text = champ1 || "";
  const c2Text = champ2 || "";
  const catCounts = categoryCounts || { all: totalCount || (tips ? tips.length : 0), lane: 0, skill: 0, teamfight: 0 };
  const subtitle = c2Text 
    ? `${c1Text} vs ${c2Text}`
    : `${c1Text}`;

  return `
    <div class="community-board-section" id="communityCounterBoardSection">
      <div class="cb-header">
        <div class="cb-title-wrap">
          <div class="cb-icon-badge">
            <i class="fa-solid fa-users-rays"></i>
          </div>
          <div>
            <h3 class="cb-title">
              상대법 팁
              <span class="badge-pill" id="cbTotalCountBadge" style="background: rgba(99, 102, 241, 0.15); color: #818CF8; font-size: 0.75rem; font-weight: 800;">
                총 ${catCounts.all || totalCount || (tips ? tips.length : 0)}개
              </span>
            </h3>
            <p class="cb-desc">${subtitle}</p>
          </div>
        </div>

        <div class="cb-toolbar">
          <div class="cb-sort-tabs">
            <button class="cb-sort-btn ${currentCommunitySort === 'popular' ? 'active' : ''}" onclick="switchCommunitySort('popular', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">
              <i class="fa-solid fa-fire"></i> 인기순
            </button>
            <button class="cb-sort-btn ${currentCommunitySort === 'recent' ? 'active' : ''}" onclick="switchCommunitySort('recent', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">
              <i class="fa-solid fa-clock"></i> 최신순
            </button>
          </div>
          <button class="cb-btn-write-toggle" id="btnToggleCommunityWrite" onclick="toggleCommunityWriteForm()">
            <i class="fa-solid fa-pen-to-square"></i> 공략 작성하기
          </button>
        </div>
      </div>

      <div class="cb-quick-filter-bar">
        <div class="cb-filter-group">
          <span class="cb-filter-label"><i class="fa-solid fa-compass" style="color: #38BDF8;"></i> 포지션:</span>
          <div class="cb-pos-chips">
            <button class="cb-pos-chip ${currentCommunityPosition === 'ALL' ? 'active' : ''}" onclick="switchCommunityPosition('ALL', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">전체</button>
            <button class="cb-pos-chip ${currentCommunityPosition === 'TOP' ? 'active' : ''}" onclick="switchCommunityPosition('TOP', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">TOP</button>
            <button class="cb-pos-chip ${currentCommunityPosition === 'JUG' ? 'active' : ''}" onclick="switchCommunityPosition('JUG', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">JUG</button>
            <button class="cb-pos-chip ${currentCommunityPosition === 'MID' ? 'active' : ''}" onclick="switchCommunityPosition('MID', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">MID</button>
            <button class="cb-pos-chip ${currentCommunityPosition === 'BOT' ? 'active' : ''}" onclick="switchCommunityPosition('BOT', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">BOT</button>
            <button class="cb-pos-chip ${currentCommunityPosition === 'SUP' ? 'active' : ''}" onclick="switchCommunityPosition('SUP', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">SUP</button>
          </div>
        </div>
      </div>

      <div class="cb-category-tabs-wrap">
        <div class="cb-category-tabs">
          <button class="cb-cat-btn ${currentCommunityCategory === 'all' ? 'active' : ''}" onclick="switchCommunityCategory('all', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">
            전체 <span class="cb-cat-count" id="cbCatCount_all">${catCounts.all || totalCount || 0}</span>
          </button>
          <button class="cb-cat-btn ${currentCommunityCategory === 'lane' ? 'active' : ''}" onclick="switchCommunityCategory('lane', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">
            <i class="fa-solid fa-swords" style="color: #6366F1;"></i> 라인전 상성 <span class="cb-cat-count" id="cbCatCount_lane">${catCounts.lane || 0}</span>
          </button>
          <button class="cb-cat-btn ${currentCommunityCategory === 'skill' ? 'active' : ''}" onclick="switchCommunityCategory('skill', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">
            <i class="fa-solid fa-bullseye" style="color: #10B981;"></i> 스킬 활용 <span class="cb-cat-count" id="cbCatCount_skill">${catCounts.skill || 0}</span>
          </button>
          <button class="cb-cat-btn ${currentCommunityCategory === 'teamfight' ? 'active' : ''}" onclick="switchCommunityCategory('teamfight', ${jsArg(c1Text)}, ${jsArg(c2Text)}, event)">
            <i class="fa-solid fa-shield-halved" style="color: #F59E0B;"></i> 한타 구도 <span class="cb-cat-count" id="cbCatCount_teamfight">${catCounts.teamfight || 0}</span>
          </button>
        </div>
      </div>

      <div class="cb-write-card" id="cbWriteCard" style="display: none;">
        <div class="cb-write-title">
          <i class="fa-solid fa-lightbulb" style="color: #F59E0B;"></i>
          <span>나만의 1:1 상대법 한 줄 노하우 등록</span>
        </div>
        <form id="cbWriteForm" onsubmit="handleCommunityTipSubmit(event, ${jsArg(c1Text)}, ${jsArg(c2Text)})">
          <div class="cb-form-row">
            <div class="cb-input-group" style="flex: 1.3;">
              <label class="cb-input-label">공략 카테고리</label>
              <select id="cbCategory" class="cb-form-select">
                <option value="lane" selected>⚔️ 라인전 상성 (1~3렙 딜교, 웨이브)</option>
                <option value="skill">🎯 스킬 활용 (스킬 연계, 회피/스턴)</option>
                <option value="teamfight">🛡️ 한타 구도 (진입각, 포지셔닝)</option>
              </select>
            </div>
            <div class="cb-input-group" style="flex: 0.9;">
              <label class="cb-input-label">포지션</label>
              <select id="cbPosition" class="cb-form-select">
                <option value="ALL">전체</option>
                <option value="TOP">탑</option>
                <option value="JUG">정글</option>
                <option value="MID" selected>미드</option>
                <option value="BOT">원딜</option>
                <option value="SUP">서폿</option>
              </select>
            </div>
          </div>
          <div>
            <textarea id="cbContent" class="cb-form-textarea" placeholder="상대방의 주요 스킬 타이밍, 딜교환 팁, 장막/응수/스턴 카운터 메커니즘을 한 줄로 작성해주세요 (5~300자)" maxlength="300" required></textarea>
          </div>
          <div class="cb-write-footer">
            <span class="cb-char-count" id="cbCharCount">0 / 300자</span>
            <div style="display: flex; gap: 8px;">
              <button type="button" class="btn-secondary" style="padding: 7px 14px; font-size: 0.82rem;" onclick="toggleCommunityWriteForm(false)">취소</button>
              <button type="submit" class="cb-btn-submit">
                <i class="fa-solid fa-paper-plane"></i> 공략 등록
              </button>
            </div>
          </div>
        </form>
      </div>

      <div class="cb-tips-list" id="cbTipsList">
        ${renderCommunityTipCardsHtml(tips)}
      </div>
    </div>
  `;
}

function toggleCommunityWriteForm(forceOpen) {
  const card = document.getElementById("cbWriteCard");
  const toggleBtn = document.getElementById("btnToggleCommunityWrite");
  if (!card) return;
  const isShow = forceOpen !== undefined ? forceOpen : (card.style.display === "none");
  card.style.display = isShow ? "block" : "none";
  if (toggleBtn) {
    toggleBtn.innerHTML = isShow 
      ? '<i class="fa-solid fa-xmark"></i> 폼 닫기' 
      : '<i class="fa-solid fa-pen-to-square"></i> 공략 작성하기';
  }
  if (isShow) {
    const contentInp = document.getElementById("cbContent");
    if (contentInp) {
      contentInp.focus();
      contentInp.addEventListener("input", updateCbCharCount);
    }
  }
}

function updateCbCharCount() {
  const contentInp = document.getElementById("cbContent");
  const countEl = document.getElementById("cbCharCount");
  if (contentInp && countEl) {
    countEl.textContent = `${contentInp.value.length} / 300자`;
  }
}

async function handleCommunityVote(tipId, voteType, btnEl) {
  const storedVotes = getStoredVotes();
  if (storedVotes[tipId]) {
    showToast(`이미 '${storedVotes[tipId] === 'up' ? '추천' : '비추천'}' 투표하신 공략입니다.`, "warning", 2000);
    return;
  }

  try {
    const res = await fetch(`/api/community-counters/${tipId}/vote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vote_type: voteType })
    });
    const data = await res.json();
    if (data.status === "success") {
      setStoredVote(tipId, voteType);
      const card = document.getElementById(`cbTipCard_${tipId}`);
      if (card) {
        const upCount = card.querySelector(".up-count");
        const downCount = card.querySelector(".down-count");
        const scorePill = card.querySelector(".cb-score-pill");
        if (upCount) upCount.textContent = data.upvotes;
        if (downCount) downCount.textContent = data.downvotes;
        if (scorePill) {
          const sc = data.score;
          scorePill.textContent = `순 추천: ${sc > 0 ? '+' : ''}${sc}`;
          scorePill.className = `cb-score-pill ${sc > 0 ? 'positive' : (sc < 0 ? 'negative' : '')}`;
        }
        const btn = card.querySelector(`.cb-vote-btn.${voteType}`);
        if (btn) btn.classList.add("voted");
      }
      showToast(voteType === 'up' ? "공략을 추천했습니다." : "공략을 비추천했습니다.", voteType === 'up' ? "success" : "info", 2000);
    } else {
      showToast(data.detail || "투표 처리에 실패했습니다.", "error");
    }
  } catch (err) {
    showToast("서버 통신 오류가 발생했습니다.", "error");
  }
}

async function handleCommunityTipSubmit(e, champ1, champ2) {
  e.preventDefault();
  const category = document.getElementById("cbCategory")?.value || "lane";
  const position = document.getElementById("cbPosition")?.value || "ALL";
  const content = (document.getElementById("cbContent")?.value || "").trim();

  if (content.length < 5) {
    showToast("공략 팁은 5자 이상 작성해주세요.", "warning");
    return;
  }

  try {
    const res = await fetch("/api/community-counters", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        champ1: champ1,
        champ2: champ2 || null,
        category: category,
        content: content,
        position: position
      })
    });
    const data = await res.json();
    if (data.status === "success") {
      showToast("카운터 공략이 등록되었습니다.", "success", 3000);
      toggleCommunityWriteForm(false);
      const contentEl = document.getElementById("cbContent");
      if (contentEl) contentEl.value = "";
      updateCbCharCount();

      // 목록 갱신
      await refreshCommunityTipsList(champ1, champ2);
    } else {
      showToast(data.detail || "공략 등록에 실패했습니다.", "error");
    }
  } catch (err) {
    showToast("공략 등록 중 오류가 발생했습니다.", "error");
  }
}

async function switchCommunitySort(sortType, champ1, champ2, e) {
  currentCommunitySort = sortType;
  const btns = document.querySelectorAll(".cb-sort-btn");
  btns.forEach(b => b.classList.remove("active"));
  if (e && e.target) {
    e.target.closest(".cb-sort-btn")?.classList.add("active");
  }
  await refreshCommunityTipsList(champ1, champ2);
}

async function switchCommunityCategory(catType, champ1, champ2, e) {
  currentCommunityCategory = catType;
  const btns = document.querySelectorAll(".cb-cat-btn");
  btns.forEach(b => b.classList.remove("active"));
  if (e && e.target) {
    e.target.closest(".cb-cat-btn")?.classList.add("active");
  }
  await refreshCommunityTipsList(champ1, champ2);
}

async function switchCommunityTier(tierType, champ1, champ2, e) {
  currentCommunityTier = tierType;
  const btns = document.querySelectorAll(".cb-tier-chip");
  btns.forEach(b => b.classList.remove("active"));
  if (e && e.target) {
    e.target.closest(".cb-tier-chip")?.classList.add("active");
  }
  await refreshCommunityTipsList(champ1, champ2);
}

async function switchCommunityPosition(posType, champ1, champ2, e) {
  currentCommunityPosition = posType;
  const btns = document.querySelectorAll(".cb-pos-chip");
  btns.forEach(b => b.classList.remove("active"));
  if (e && e.target) {
    e.target.closest(".cb-pos-chip")?.classList.add("active");
  }
  await refreshCommunityTipsList(champ1, champ2);
}

async function refreshCommunityTipsList(champ1, champ2) {
  const listEl = document.getElementById("cbTipsList");
  const countBadge = document.getElementById("cbTotalCountBadge");
  if (!listEl) return;

  try {
    let url = `/api/community-counters?champ1=${encodeURIComponent(champ1)}&sort=${currentCommunitySort}`;
    if (currentCommunityCategory && currentCommunityCategory !== 'all') {
      url += `&category=${encodeURIComponent(currentCommunityCategory)}`;
    }
    if (currentCommunityTier && currentCommunityTier !== 'all') {
      url += `&tier=${encodeURIComponent(currentCommunityTier)}`;
    }
    if (currentCommunityPosition && currentCommunityPosition !== 'ALL') {
      url += `&position=${encodeURIComponent(currentCommunityPosition)}`;
    }
    if (champ2) url += `&champ2=${encodeURIComponent(champ2)}`;

    const res = await fetch(url);
    const data = await res.json();
    if (data.status === "success") {
      listEl.innerHTML = renderCommunityTipCardsHtml(data.tips);
      if (countBadge) countBadge.textContent = `총 ${data.total_unfiltered !== undefined ? data.total_unfiltered : data.total}개`;

      // 카테고리 탭 카운트 뱃지 실시간 동기화
      if (data.category_counts) {
        const counts = data.category_counts;
        const allEl = document.getElementById("cbCatCount_all");
        const laneEl = document.getElementById("cbCatCount_lane");
        const skillEl = document.getElementById("cbCatCount_skill");
        const tfEl = document.getElementById("cbCatCount_teamfight");
        if (allEl) allEl.textContent = counts.all || 0;
        if (laneEl) laneEl.textContent = counts.lane || 0;
        if (skillEl) skillEl.textContent = counts.skill || 0;
        if (tfEl) tfEl.textContent = counts.teamfight || 0;
      }
    }
  } catch (err) {
    console.error("Failed to refresh community tips:", err);
  }
}

// 매치업 결과(수집 매치 통계) + 그 아래 소환사들이 직접 쓰는 1:1 상대법 보드 (익명)
function renderMatchupResult(data) {
  renderMatchupStats(data);
  const cardEl = document.getElementById("matchupResultCard");
  if (!cardEl || !data) return;
  let boardEl = document.getElementById("matchupCommunityBoard");
  if (!boardEl) {
    boardEl = document.createElement("div");
    boardEl.id = "matchupCommunityBoard";
    boardEl.style.marginTop = "1.25rem";
    cardEl.insertAdjacentElement("afterend", boardEl);
  }
  const c1 = data.mode === "head_to_head" ? (data.champ_a || {}) : (data.champion || {});
  const c2 = data.mode === "head_to_head" ? (data.champ_b || {}) : {};
  const n1 = c1.name || c1.id || "";
  const n2 = c2.name || c2.id || "";
  if (!n1) {
    boardEl.innerHTML = "";
    return;
  }
  boardEl.innerHTML = generateCommunityBoardHtml(n1, n2, [], 0, null);
  refreshCommunityTipsList(n1, n2);
}

function renderMatchupStats(data) {
  const cardEl = document.getElementById("matchupResultCard");
  if (!cardEl) return;

  const esc = (s) => (typeof escapeHtml === "function" ? escapeHtml(s == null ? "" : String(s)) : String(s == null ? "" : s));
  const numOrDash = (v) => (v !== undefined && v !== null && !isNaN(v) ? v : "-");

  if (data.mode === "counters") {
    const c = data.champion || {};
    const cName = esc(c.name || c.id || "챔피언");
    const cId = esc(c.id || c.name || "");
    const cImg = esc(c.image || "");
    const mainPos = esc(data.main_position || "");
    const sampleNote = esc(data.sample_note || "");
    const totalGames = data.total_games || 0;
    const matchups = Array.isArray(data.matchups) ? data.matchups : [];

    if (matchups.length === 0) {
      cardEl.innerHTML = `
        <div class="matchup-box matchup-empty-box">
          <div class="matchup-counters-champ" style="justify-content: center; margin-bottom: 8px;">
            ${cImg ? `<img src="${cImg}" alt="${cName}" class="matchup-counters-portrait" onclick="openChampionPage(${jsArg(cId)})" title="${cName} 챔피언 페이지">` : ""}
            <h2 class="matchup-counters-name" onclick="openChampionPage(${jsArg(cId)})">${cName}</h2>
          </div>
          <div class="matchup-empty-text">${sampleNote || "아직 표본이 부족합니다 (상대별 10게임 이상)"}</div>
        </div>
      `;
      return;
    }

    const hard = matchups
      .filter(m => (m.win_rate ?? 0) <= 50)
      .sort((a, b) => (a.win_rate ?? 0) - (b.win_rate ?? 0) || (b.games ?? 0) - (a.games ?? 0));

    const easy = matchups
      .filter(m => (m.win_rate ?? 0) > 50)
      .sort((a, b) => (b.win_rate ?? 0) - (a.win_rate ?? 0) || (b.games ?? 0) - (a.games ?? 0));

    const renderCounterCol = (list, wrClass) => {
      if (!list || list.length === 0) {
        return `<div class="cp-empty">-</div>`;
      }
      return list.map(o => {
        const oName = esc(o.name || o.id || "");
        const oId = esc(o.id || o.name || "");
        const oImg = esc(o.image || "");
        const oWr = o.win_rate !== undefined && o.win_rate !== null ? `${Number(o.win_rate).toFixed(1)}%` : "-";
        const oGames = numOrDash(o.games);

        return `
          <div class="cp-mu-row" onclick="openMatchupWithChampions(${jsArg(c.name || c.id)}, ${jsArg(o.name || o.id)})" title="${oName} 1:1 비교">
            <img src="${oImg}" alt="${oName}" class="cp-icon" style="width:28px;height:28px;" onclick="event.stopPropagation(); openChampionPage(${jsArg(oId)})" title="${oName} 챔피언 페이지">
            <span class="cp-mu-name">${oName}</span>
            <span class="cp-mu-wr ${wrClass}">${oWr}</span>
            <span class="cp-mu-games">${Number(oGames).toLocaleString()}</span>
          </div>
        `;
      }).join("");
    };

    cardEl.innerHTML = `
      <div style="width: 100%; display: flex; flex-direction: column; gap: 12px;">
        <div class="matchup-box matchup-counters-header">
          <div class="matchup-counters-champ">
            ${cImg ? `<img src="${cImg}" alt="${cName}" class="matchup-counters-portrait" onclick="openChampionPage(${jsArg(cId)})" title="${cName} 챔피언 페이지">` : ""}
            <div>
              <div class="matchup-counters-name-row">
                <h2 class="matchup-counters-name" onclick="openChampionPage(${jsArg(cId)})">${cName}</h2>
                ${mainPos ? `<span class="matchup-pos-pill">${mainPos}</span>` : ""}
              </div>
              <div class="matchup-counters-note">${sampleNote || `${Number(totalGames).toLocaleString()}게임 기준`}</div>
            </div>
          </div>
        </div>

        <div class="matchup-box matchup-counters-card">
          <div class="cp-mu-grid">
            <div class="cp-mu-col">
              <div class="cp-mu-title cp-bad">상대하기 어려움</div>
              ${renderCounterCol(hard, "cp-bad")}
            </div>
            <div class="cp-mu-col">
              <div class="cp-mu-title cp-good">상대하기 쉬움</div>
              ${renderCounterCol(easy, "cp-good")}
            </div>
          </div>
        </div>
      </div>
    `;
    return;
  }

  if (data.mode === "head_to_head") {
    const ca = data.champ_a || {};
    const cb = data.champ_b || {};
    const aName = esc(ca.name || ca.id || "챔피언 A");
    const bName = esc(cb.name || cb.id || "챔피언 B");
    const aId = esc(ca.id || ca.name || "");
    const bId = esc(cb.id || cb.name || "");
    const aImg = esc(ca.image || "");
    const bImg = esc(cb.image || "");
    const games = data.games || 0;

    if (games === 0) {
      cardEl.innerHTML = `
        <div class="matchup-box matchup-empty-box">
          <div class="matchup-empty-champs">
            ${aImg ? `<img src="${aImg}" alt="${aName}" class="matchup-empty-img" onclick="openChampionPage(${jsArg(aId)})" title="${aName} 챔피언 페이지">` : ""}
            <span class="matchup-empty-vs">VS</span>
            ${bImg ? `<img src="${bImg}" alt="${bName}" class="matchup-empty-img" onclick="openChampionPage(${jsArg(bId)})" title="${bName} 챔피언 페이지">` : ""}
          </div>
          <div class="matchup-empty-text">${esc(data.message || data.sample_note || "맞대결 전적 데이터가 없습니다.")}</div>
        </div>
      `;
      return;
    }

    const aWinRate = data.win_rate !== undefined && data.win_rate !== null ? Number(data.win_rate) : 0;
    const bWinRate = Math.round((100 - aWinRate) * 10) / 10;
    const aWrClass = aWinRate > 50 ? "wr-good" : "wr-bad";
    const bWrClass = bWinRate > 50 ? "wr-good" : "wr-bad";

    const metrics = [
      { label: "KDA", a: ca.kda, b: cb.kda, fmt: (v) => numOrDash(v) },
      { label: "킬", a: ca.kills, b: cb.kills, fmt: (v) => numOrDash(v) },
      { label: "데스", a: ca.deaths, b: cb.deaths, fmt: (v) => numOrDash(v), lowerIsBetter: true },
      { label: "어시", a: ca.assists, b: cb.assists, fmt: (v) => numOrDash(v) },
      { label: "CS", a: ca.cs, b: cb.cs, fmt: (v) => numOrDash(v) },
      { label: "골드", a: ca.gold, b: cb.gold, fmt: (v) => (v !== undefined && v !== null && !isNaN(v) ? `${Number(v).toLocaleString()}G` : "-") },
      { label: "피해량", a: ca.damage, b: cb.damage, fmt: (v) => (v !== undefined && v !== null && !isNaN(v) ? Number(v).toLocaleString() : "-") },
    ];

    cardEl.innerHTML = `
      <div style="width: 100%; display: flex; flex-direction: column; gap: 12px;">
        <!-- 상단 1:1 요약 카드 -->
        <div class="matchup-box matchup-h2h-header">
          <div class="matchup-h2h-champ left" onclick="openChampionPage(${jsArg(aId)})" title="${aName} 챔피언 페이지">
            ${aImg ? `<img src="${aImg}" alt="${aName}" class="matchup-h2h-portrait ${aWrClass}">` : ""}
            <div class="matchup-h2h-meta">
              <span class="matchup-h2h-name">${aName}</span>
              <span class="matchup-h2h-wr ${aWrClass}">${aWinRate.toFixed(1)}%</span>
            </div>
          </div>

          <div class="matchup-h2h-center">
            <span class="matchup-h2h-vs">VS</span>
            <span class="matchup-h2h-games">${Number(games).toLocaleString()}게임</span>
          </div>

          <div class="matchup-h2h-champ right" onclick="openChampionPage(${jsArg(bId)})" title="${bName} 챔피언 페이지">
            <div class="matchup-h2h-meta right">
              <span class="matchup-h2h-name">${bName}</span>
              <span class="matchup-h2h-wr ${bWrClass}">${bWinRate.toFixed(1)}%</span>
            </div>
            ${bImg ? `<img src="${bImg}" alt="${bName}" class="matchup-h2h-portrait ${bWrClass}">` : ""}
          </div>
        </div>

        <!-- 스탯 비교 막대 카드 -->
        <div class="matchup-box matchup-stats-card">
          ${metrics.map(m => {
            const valA = m.a !== undefined && m.a !== null ? Number(m.a) : 0;
            const valB = m.b !== undefined && m.b !== null ? Number(m.b) : 0;
            const aIsHigher = m.lowerIsBetter ? (valA < valB) : (valA > valB);
            const bIsHigher = m.lowerIsBetter ? (valB < valA) : (valB > valA);
            const sum = valA + valB;
            const pctA = sum > 0 ? Math.max(8, Math.min(92, Math.round((valA / sum) * 100))) : 50;
            const pctB = 100 - pctA;

            const aValClass = aIsHigher ? "val-winner" : (bIsHigher ? "val-loser" : "val-neutral");
            const bValClass = bIsHigher ? "val-winner" : (aIsHigher ? "val-loser" : "val-neutral");
            const aBarClass = aIsHigher ? "bar-champ-a winner" : "bar-champ-a";
            const bBarClass = bIsHigher ? "bar-champ-b winner" : "bar-champ-b";

            return `
              <div class="matchup-stat-row">
                <div class="matchup-stat-head">
                  <span class="matchup-stat-val left ${aValClass}">${m.fmt(m.a)}</span>
                  <span class="matchup-stat-label">${m.label}</span>
                  <span class="matchup-stat-val right ${bValClass}">${m.fmt(m.b)}</span>
                </div>
                <div class="matchup-bar-track">
                  <div class="matchup-bar-fill left ${aBarClass}" style="width: ${pctA}%;"></div>
                  <div class="matchup-bar-fill right ${bBarClass}" style="width: ${pctB}%;"></div>
                </div>
              </div>
            `;
          }).join("")}
        </div>

        <!-- 상대 맞춤 빌드 (champ_a 빌드 vs champ_b) -->
        <div class="matchup-box matchup-vsbuild" id="matchupVsBuild">
          <div class="mvb-title">${aName} 빌드 vs ${bName}</div>
          <div class="mvb-empty">불러오는 중...</div>
        </div>
      </div>
    `;
    loadMatchupVsBuild(ca.id || ca.name, cb.id || cb.name);
    return;
  }
}

let _matchupVsBuildSeq = 0;
async function loadMatchupVsBuild(champA, champB) {
  const seq = ++_matchupVsBuildSeq;
  if (!champA || !champB) {
    const el0 = document.getElementById("matchupVsBuild");
    if (el0) el0.remove();
    return;
  }
  let data = null;
  try {
    const res = await fetch(`/api/champion-build/${encodeURIComponent(champA)}?vs=${encodeURIComponent(champB)}`);
    if (res.ok) data = await res.json();
  } catch (e) {
    data = null;
  }
  if (seq !== _matchupVsBuildSeq) return;
  const el = document.getElementById("matchupVsBuild");
  if (!el) return;
  el.innerHTML = renderMatchupVsBuildHtml(data);
}

function renderMatchupVsBuildHtml(data) {
  const esc = (s) => escapeHtml(s == null ? "" : String(s));
  const wrSpan = (wr, games) => {
    if (wr === undefined || wr === null) return "";
    const cls = Number(wr) > 50 ? "mvb-good" : "mvb-bad";
    return `<span class="mvb-stat"><span class="mvb-wr ${cls}">${Number(wr).toFixed(1)}%</span><span class="mvb-games">${Number(games || 0).toLocaleString()}게임</span></span>`;
  };
  const icon = (o, extra) => {
    if (!o || !o.icon) return "";
    return `<img src="${esc(o.icon)}" alt="${esc(o.name)}" title="${esc(o.name)}" class="mvb-icon${extra ? " " + extra : ""}" loading="lazy">`;
  };

  if (!data) {
    return `<div class="mvb-title">상대 맞춤 빌드</div><div class="mvb-empty">빌드 데이터를 불러오지 못했습니다.</div>`;
  }
  const champ = data.champion || {};
  const vs = data.vs || {};
  const total = Number(data.total_games || 0);
  const pos = data.position ? `<span class="mvb-pos">${esc(data.position)}</span>` : "";
  const head = `<div class="mvb-title">${esc(champ.name || champ.id)} 빌드 vs ${esc(vs.name || vs.id)}${pos}<span class="mvb-total">${total.toLocaleString()}게임${data.patch ? ` · ${esc(data.patch)} 패치` : ""}</span></div>`;
  if (total < 5) {
    return head + `<div class="mvb-empty">표본 부족 (${total}게임) — 이 상대와의 맞라인 게임이 더 수집되면 표시됩니다.</div>`;
  }

  const rows = [];
  const rune = (data.rune_options || [])[0];
  if (rune) {
    const page = rune.page;
    let runeIcons;
    if (page && Array.isArray(page.runes)) {
      runeIcons = page.runes.map((r, i) => icon(r, i === 0 ? "mvb-keystone" : "mvb-rune")).join("")
        + (page.shards || []).map(sh => icon(sh, "mvb-shard")).join("");
    } else {
      runeIcons = icon({ icon: rune.keystone_icon, name: rune.keystone_name }, "mvb-keystone")
        + icon({ icon: rune.primary_icon, name: rune.primary_tree }, "mvb-rune")
        + icon({ icon: rune.sub_icon, name: rune.sub_tree }, "mvb-rune");
    }
    const st = page || rune;
    rows.push({ label: "룬", body: `<div class="mvb-icons">${runeIcons}</div>${wrSpan(st.win_rate, st.games)}` });
  }
  const sp = (data.spell_options || [])[0];
  if (sp) {
    rows.push({
      label: "주문",
      body: `<div class="mvb-icons">${(sp.spells || []).map(x => icon(x)).join("")}</div>${wrSpan(sp.win_rate, sp.games)}`,
    });
  }
  const core = (data.core_builds || [])[0];
  if (core) {
    rows.push({ label: "코어", body: `<div class="mvb-icons">${(core.items || []).map(x => icon(x)).join("")}</div>${wrSpan(core.win_rate, core.games)}` });
  }
  const skill = (data.skill_orders || [])[0];
  if (skill && skill.order) {
    const keys = String(skill.order).split(">").map(k => `<span class="mvb-skill">${esc(k)}</span>`).join('<span class="mvb-arrow">&rsaquo;</span>');
    rows.push({ label: "스킬", body: `<div class="mvb-icons">${keys}</div>${wrSpan(skill.win_rate, skill.games)}` });
  }
  if (!rows.length) {
    return head + `<div class="mvb-empty">표본 부족 — 항목별 최소 게임 수를 넘는 빌드가 없습니다.</div>`;
  }
  return head + rows.map(r => `<div class="mvb-row"><span class="mvb-label">${r.label}</span><div class="mvb-body">${r.body}</div></div>`).join("");
}
window.loadMatchupVsBuild = loadMatchupVsBuild;


