// carry.gg - 홈 메타 보드 (20-meta-board.js)
// /api/meta-board?position=... 의 승률·픽률·밴률 상위 5를 3열로 그린다.
// 값은 수집된 솔로랭크 매치 집계만 쓴다. 표본이 없으면 섹션을 숨긴다 (예시 값을 그리지 않음).
(function initMetaBoard() {
  "use strict";

  const board = document.getElementById("metaBoard");
  if (!board) return;

  const patchEl = document.getElementById("metaBoardPatch");
  const noteEl = document.getElementById("metaBoardNote");
  const lists = {
    win_rate: document.getElementById("metaBoardWin"),
    pick_rate: document.getElementById("metaBoardPick"),
    ban_rate: document.getElementById("metaBoardBan"),
  };
  const laneBtns = Array.from(board.querySelectorAll(".meta-lane-btn"));
  const responseCache = {};
  let currentPos = "ALL";
  let requestSeq = 0;
  let hasShown = false;

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

  function fmtPct(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(1) + "%" : "-";
  }

  function renderList(field, rows) {
    const ol = lists[field];
    if (!ol) return;
    if (!rows || rows.length === 0) {
      ol.innerHTML = `<li class="meta-row-empty">표본 부족</li>`;
      return;
    }
    ol.innerHTML = rows.map((c, i) => {
      let valueClass = "";
      if (field === "win_rate") valueClass = Number(c.value) > 50 ? "is-up" : "is-down";
      return `
        <li>
          <button type="button" class="meta-row" data-champ-id="${esc(c.id)}" title="${esc(c.name)} 챔피언 페이지 (${esc(String(c.games))}게임)">
            <span class="meta-rank">${i + 1}</span>
            <img class="meta-champ-img" src="${esc(c.image)}" alt="" loading="lazy" width="28" height="28" onerror="this.style.visibility='hidden'">
            <span class="meta-champ-name">${esc(c.name)}</span>
            <span class="meta-value ${valueClass}">${esc(fmtPct(c.value))}</span>
          </button>
        </li>`;
    }).join("");
  }

  function render(data) {
    const total = (data.win_rate || []).length + (data.pick_rate || []).length + (data.ban_rate || []).length;
    if (total === 0 && !hasShown) {
      board.style.display = "none";
      return;
    }
    hasShown = true;
    board.style.display = "";
    if (patchEl && data.patch) patchEl.textContent = data.patch;
    renderList("win_rate", data.win_rate);
    renderList("pick_rate", data.pick_rate);
    renderList("ban_rate", data.ban_rate);
    if (noteEl) noteEl.textContent = data.sample_note || "";
  }

  async function load(pos) {
    currentPos = pos;
    laneBtns.forEach((b) => {
      const on = b.dataset.pos === pos;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (responseCache[pos]) {
      render(responseCache[pos]);
      return;
    }
    const seq = ++requestSeq;
    try {
      const res = await fetch(`/api/meta-board?position=${encodeURIComponent(pos)}`);
      if (!res.ok) throw new Error("meta-board " + res.status);
      const data = await res.json();
      responseCache[pos] = data;
      if (seq === requestSeq && currentPos === pos) render(data);
    } catch (e) {
      if (!hasShown) board.style.display = "none";
    }
  }

  laneBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.pos && btn.dataset.pos !== currentPos) load(btn.dataset.pos);
    });
  });

  board.addEventListener("click", (e) => {
    const row = e.target.closest(".meta-row");
    if (!row || !board.contains(row)) return;
    const id = row.dataset.champId;
    if (id && typeof window.openChampionPage === "function") {
      window.openChampionPage(id, currentPos !== "ALL" ? currentPos : null);
    }
  });

  load("ALL");
})();
