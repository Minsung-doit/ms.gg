// carry.gg - 홈 '이번 주 내전' 위젯 (23-home-inhouse.js)
// 최근 7일 내전 상위 3명과 가장 최근 내전 1개. 기록이 없거나 불러오지 못하면 위젯 전체를 숨긴다.
// 상자 모양은 홈 '지금 구인 중'(29-home-recruit.css)과 같은 클래스를 쓴다.
(function initHomeInhouseModule() {
  "use strict";

  const esc = (v) => (typeof window.escapeHtml === "function" ? window.escapeHtml(v) : String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;"));

  function ago(sec) {
    const d = Math.max(0, Math.floor(Date.now() / 1000) - Number(sec || 0));
    if (d < 3600) return `${Math.max(1, Math.floor(d / 60))}분 전`;
    if (d < 86400) return `${Math.floor(d / 3600)}시간 전`;
    return `${Math.floor(d / 86400)}일 전`;
  }

  function goToInhouse() {
    if (typeof window.switchMainTab === "function") window.switchMainTab("serverranking");
    setTimeout(() => document.getElementById("srInhouse")?.scrollIntoView({ behavior: "smooth", block: "start" }), 400);
  }

  function render(root, data) {
    const top = (data.players || []).slice(0, 3);
    const last = (data.recent || [])[0];
    if (!top.length && !last) {
      root.style.display = "none";
      return;
    }
    const medals = ["hi-medal-1", "hi-medal-2", "hi-medal-3"];
    const topHtml = top.map((p, i) => `
      <li class="hi-top-row">
        <span class="hi-medal ${medals[i]}">${i + 1}</span>
        <span class="hi-name" title="${esc(p.name)}">${esc(p.name)}</span>
        <span class="hi-record">${Number(p.wins) || 0}승 ${Number(p.losses) || 0}패 <em>(${esc(p.win_rate)}%)</em></span>
      </li>`).join("");

    let lastHtml = "";
    if (last) {
      const side = (names, cls, label, state) =>
        `<div class="hi-side ${cls} ${state}"><span class="hi-side-tag">${label}</span> ${(names || []).map(esc).join(", ")}</div>`;
      const bw = last.winner === "blue", rw = last.winner === "red";
      const status = bw ? "블루 승리" : rw ? "레드 승리" : "진행 중";
      lastHtml = `
        <div class="hi-last">
          <div class="hi-last-top"><span class="hi-last-label">최근 내전 · ${esc(ago(last.created_at))}</span>
            <span class="hi-status ${bw ? "hi-status-blue" : rw ? "hi-status-red" : ""}">${status}</span></div>
          ${side(last.blue, "hi-blue", "블루", bw ? "hi-win" : rw ? "hi-lose" : "")}
          ${side(last.red, "hi-red", "레드", rw ? "hi-win" : bw ? "hi-lose" : "")}
        </div>`;
    }

    root.innerHTML = `
      <div class="home-recruit-box">
        <div class="home-recruit-header">
          <div class="home-recruit-title-wrap">
            <span class="home-recruit-badge"><i class="fa-solid fa-scale-balanced"></i> 이번 주 내전</span>
          </div>
          <button type="button" class="home-recruit-more-btn hi-go" title="내전 팀 짜기">
            <span>팀 짜기</span> <i class="fa-solid fa-angle-right"></i>
          </button>
        </div>
        ${topHtml ? `<ol class="hi-top">${topHtml}</ol>` : ""}
        ${lastHtml}
      </div>`;
    root.style.display = "";
  }

  async function loadHomeInhouse() {
    const root = document.getElementById("homeInhouse");
    if (!root) return;
    try {
      const res = await fetch("/api/inhouse/stats?days=7&recent=1");
      if (!res.ok) throw new Error(String(res.status));
      render(root, await res.json());
    } catch (_) {
      root.style.display = "none";
    }
  }

  function init() {
    const root = document.getElementById("homeInhouse");
    if (!root) return;
    root.addEventListener("click", (e) => {
      if (e.target.closest(".hi-go")) goToInhouse();
    });
    loadHomeInhouse();
  }

  window.loadHomeInhouse = loadHomeInhouse;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
