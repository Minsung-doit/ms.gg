// carry.gg - 홈 '지금 구인 중' 위젯 (21-home-recruit.js)
// 마감 안 된 최신 구인글 최대 4개를 카드로 노출하고, 클릭 시 듀오 구인 탭(duofinder)으로 직결 연동한다.
(function initHomeRecruitModule() {
  "use strict";

  const DEFAULT_GAMES = {
    lol: "롤",
    pubg: "배그",
    overwatch: "옵치"
  };

  let gamesMap = Object.assign({}, DEFAULT_GAMES);

  function esc(v) {
    if (typeof window.escapeHtml === "function") return window.escapeHtml(v);
    if (v == null) return "";
    return String(v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function goToDuo(gameId) {
    const target = gameId || "lol";
    try {
      localStorage.setItem("duo_selected_game", target);
    } catch (_) {}

    if (typeof window.selectDuoGame === "function") {
      try { window.selectDuoGame(target); } catch (_) {}
    } else if (typeof selectDuoGame === "function") {
      try { selectDuoGame(target); } catch (_) {}
    }

    if (typeof window.switchMainTab === "function") {
      window.switchMainTab("duofinder");
    } else if (typeof switchMainTab === "function") {
      switchMainTab("duofinder");
    }
  }

  function renderEmpty(root) {
    root.innerHTML = `
      <div class="home-recruit-empty-bar">
        <button type="button" class="home-recruit-empty-btn" title="구인글 쓰러 가기">
          <i class="fa-solid fa-user-plus"></i> 구인글 쓰러 가기 <i class="fa-solid fa-angle-right"></i>
        </button>
      </div>`;
    root.style.display = "";
  }

  function renderCards(root, posts) {
    const cardsHtml = posts.map(p => {
      const gId = p.game || "lol";
      const gShort = gamesMap[gId] || DEFAULT_GAMES[gId] || gId;
      const title = p.title || "구인 중";
      const queue = p.queue_type || "일반";
      const cur = p.current_members != null ? p.current_members : 1;
      const max = p.max_members != null ? p.max_members : 2;
      const time = p.created_at || "";

      let authorHtml = "";
      if (p.author) {
        authorHtml = `
          <span class="hr-author hr-author-discord" title="디스코드: ${esc(p.author)}">
            <i class="fa-brands fa-discord"></i>
            <span class="hr-author-name">${esc(p.author)}</span>
          </span>`;
      } else {
        const gName = p.game_name || "호스트";
        authorHtml = `
          <span class="hr-author hr-author-game" title="${esc(gName)}">
            <span class="hr-author-name">${esc(gName)}</span>
          </span>`;
      }

      return `
        <button type="button" class="home-recruit-card" data-game="${esc(gId)}" title="${esc(gShort)} | ${esc(queue)} | ${esc(title)}">
          <div class="hr-card-top">
            <span class="hr-badge-game game-${esc(gId)}">${esc(gShort)}</span>
            <span class="hr-time">${esc(time)}</span>
          </div>
          <div class="hr-card-title">${esc(title)}</div>
          <div class="hr-card-queue-members">
            <span class="hr-queue">${esc(queue)}</span>
            <span class="hr-dot">·</span>
            <span class="hr-members">${cur}/${max}명</span>
          </div>
          <div class="hr-card-author">
            ${authorHtml}
          </div>
        </button>`;
    }).join("");

    root.innerHTML = `
      <div class="home-recruit-box">
        <div class="home-recruit-header">
          <div class="home-recruit-title-wrap">
            <span class="home-recruit-badge"><i class="fa-solid fa-users"></i> 지금 구인 중</span>
          </div>
          <button type="button" class="home-recruit-more-btn" title="구인 게시판 전체보기">
            <span>더보기</span>
            <i class="fa-solid fa-angle-right"></i>
          </button>
        </div>
        <div class="home-recruit-grid">
          ${cardsHtml}
        </div>
      </div>`;
    root.style.display = "";
  }

  async function loadHomeRecruit() {
    const root = document.getElementById("homeRecruit");
    if (!root) return;

    try {
      const [postsRes, gamesRes] = await Promise.allSettled([
        fetch("/api/duo-posts?game=all"),
        fetch("/api/duo-games")
      ]);

      if (gamesRes.status === "fulfilled" && gamesRes.value.ok) {
        try {
          const gData = await gamesRes.value.json();
          if (gData && Array.isArray(gData.games)) {
            gData.games.forEach(g => {
              if (g && g.id && g.short) {
                gamesMap[g.id] = g.short;
              }
            });
          }
        } catch (_) {}
      }

      if (postsRes.status === "fulfilled" && postsRes.value.ok) {
        const data = await postsRes.value.json();
        const posts = Array.isArray(data.posts) ? data.posts : [];
        const unclosed = posts.filter(p => !p.is_full);
        if (unclosed.length === 0) {
          renderEmpty(root);
        } else {
          renderCards(root, unclosed.slice(0, 4));
        }
      } else {
        renderEmpty(root);
      }
    } catch (err) {
      console.warn("loadHomeRecruit error:", err);
      renderEmpty(root);
    }
  }

  function bindEvents() {
    const root = document.getElementById("homeRecruit");
    if (!root) return;

    root.addEventListener("click", function(e) {
      const card = e.target.closest(".home-recruit-card");
      if (card) {
        const gameId = card.getAttribute("data-game") || "lol";
        goToDuo(gameId);
        return;
      }
      const emptyBtn = e.target.closest(".home-recruit-empty-btn");
      if (emptyBtn) {
        goToDuo("lol");
        return;
      }
      const moreBtn = e.target.closest(".home-recruit-more-btn");
      if (moreBtn) {
        goToDuo("lol");
        return;
      }
    });
  }

  window.loadHomeRecruit = loadHomeRecruit;

  function init() {
    bindEvents();
    loadHomeRecruit();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
