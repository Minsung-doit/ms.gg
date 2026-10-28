// AI 코치: 검색창의 소환사(닉네임#태그)를 최근 랭크 게임 기준으로 고티어 평균과 비교해 코칭 (/api/ai-coach)

// 글자 없는 AI 로고: 안테나가 반짝이고 눈을 깜빡이는 귀여운 로봇 얼굴
function aiCoachLogoSvg() {
  return `
    <svg class="ai-coach-logo" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <line x1="16" y1="3.5" x2="16" y2="8" stroke="#E0E7FF" stroke-width="1.8" stroke-linecap="round"/>
      <circle class="ai-bot-antenna" cx="16" cy="3.4" r="2.2" fill="#FDE047"/>
      <rect x="2.3" y="14" width="3" height="7" rx="1.5" fill="#C7D2FE"/>
      <rect x="26.7" y="14" width="3" height="7" rx="1.5" fill="#C7D2FE"/>
      <rect x="4.5" y="8" width="23" height="19" rx="8" fill="#FFFFFF"/>
      <rect x="7.5" y="11.5" width="17" height="10.5" rx="5" fill="#1E1B4B"/>
      <g class="ai-bot-eyes" fill="#67E8F9">
        <ellipse cx="12.4" cy="16.4" rx="2" ry="2.5"/>
        <ellipse cx="19.6" cy="16.4" rx="2" ry="2.5"/>
      </g>
      <path d="M13.6 19.6 Q16 21.4 18.4 19.6" fill="none" stroke="#67E8F9" stroke-width="1.2" stroke-linecap="round"/>
      <circle cx="8.6" cy="23.6" r="1.4" fill="#F9A8D4" opacity="0.9"/>
      <circle cx="23.4" cy="23.6" r="1.4" fill="#F9A8D4" opacity="0.9"/>
    </svg>`;
}

function ensureAiCoachOverlay() {
  let overlay = document.getElementById("aiCoachOverlay");
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.id = "aiCoachOverlay";
  overlay.className = "ai-coach-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "AI 코치");
  overlay.innerHTML = `<div class="ai-coach-panel"><div id="aiCoachContent"></div></div>`;
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeAiCoach();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && overlay.classList.contains("open")) closeAiCoach();
  });
  document.body.appendChild(overlay);
  return overlay;
}

function closeAiCoach() {
  const overlay = document.getElementById("aiCoachOverlay");
  if (overlay) overlay.classList.remove("open");
}
window.closeAiCoach = closeAiCoach;

function aiCoachHead(sub) {
  return `
    <div class="ai-coach-head">
      <span class="ai-coach-btn" aria-hidden="true">${aiCoachLogoSvg()}</span>
      <div>
        <div class="ai-coach-title">AI 코치</div>
        <div class="ai-coach-sub">${sub}</div>
      </div>
      <button type="button" class="ai-coach-close" onclick="closeAiCoach()" aria-label="닫기">✕</button>
    </div>`;
}

async function openAiCoach(rawQuery) {
  const q = (rawQuery || "").trim();
  if (!q) {
    showToast("소환사명#태그를 입력한 뒤 AI 코치를 눌러주세요. (예: 닉네임#KR1)", "info", 3500);
    const input = document.getElementById("searchInput");
    if (input) input.focus();
    return;
  }
  const [name, tag] = q.includes("#") ? q.split("#", 2).map(s => s.trim()) : [q, "KR1"];
  const overlay = ensureAiCoachOverlay();
  const content = document.getElementById("aiCoachContent");
  overlay.classList.add("open");
  content.innerHTML = `${aiCoachHead(`${escapeHtml(name)}#${escapeHtml(tag || "KR1")}`)}
    <div class="ai-coach-body" style="align-items: center; padding: 2.5rem;">
      <div class="spinner"></div>
      <div class="ai-coach-note">최근 랭크 게임을 고티어 평균과 비교하는 중...</div>
    </div>`;

  try {
    const res = await fetch(`/api/ai-coach?name=${encodeURIComponent(name)}&tag=${encodeURIComponent(tag || "KR1")}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "코칭 데이터를 불러오지 못했습니다.");
    renderAiCoach(data);
  } catch (err) {
    content.innerHTML = `${aiCoachHead(`${escapeHtml(name)}#${escapeHtml(tag || "KR1")}`)}
      <div class="ai-coach-body"><div style="color: #F87171; font-weight: 700;">${escapeHtml(err.message)}</div></div>`;
  }
}
window.openAiCoach = openAiCoach;

function renderAiCoach(d) {
  const content = document.getElementById("aiCoachContent");
  if (!content) return;
  const p = d.player || {};
  const who = `${escapeHtml(p.game_name || "")}#${escapeHtml(p.tag_line || "")}${p.tier ? ` · ${escapeHtml(p.tier)}` : ""}`;

  if (!d.ready) {
    content.innerHTML = `${aiCoachHead(who)}<div class="ai-coach-body"><div>${escapeHtml(d.message || "")}</div></div>`;
    return;
  }

  const fmt = (m, v) => {
    if (v === null || v === undefined) return "-";
    const n = Number(v);
    const s = m.key === "damage_per_min" || m.key === "gold_per_min" ? Math.round(n).toLocaleString() : String(v);
    return `${escapeHtml(s)}${escapeHtml(m.unit || "")}`;
  };
  const barColor = (s) => s >= 60 ? "#10B981" : (s < 40 ? "#F87171" : "#A78BFA");
  const metrics = (d.metrics || []).map(m => `
    <div class="ai-coach-metric">
      <span style="font-weight: 700;">${escapeHtml(m.label)}${m.verdict ? ` <span style="color: ${barColor(m.score)}; font-size: 0.72rem;">${escapeHtml(m.verdict)}</span>` : ""}</span>
      <div class="ai-coach-bar" title="가운데 선 = 고티어 평균"><div style="width: ${m.score ?? 50}%; background: ${barColor(m.score ?? 50)};"></div></div>
      <span style="text-align: right; color: var(--text-muted);"><strong style="color: var(--text-heading);">${fmt(m, m.value)}</strong> / 고티어 ${fmt(m, m.benchmark)}</span>
    </div>`).join("");
  const list = (items) => items && items.length
    ? `<ul class="ai-coach-list">${items.map(t => `<li>${escapeHtml(t)}</li>`).join("")}</ul>`
    : `<div class="ai-coach-note">해당 없음</div>`;
  const pool = (d.champion_pool || []).map(c => `
    <div class="ai-coach-pool-item">
      ${c.id ? `<img src="https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/${encodeURIComponent(c.id)}.png" alt="">` : ""}
      <span style="font-weight: 700;">${escapeHtml(c.name)}</span>
      <span style="color: var(--text-muted);">${escapeHtml(String(c.games))}판 ${escapeHtml(String(c.win_rate))}% · KDA ${escapeHtml(String(c.kda))}</span>
    </div>`).join("");
  const summary = d.ai_summary
    ? `<div class="ai-coach-summary">${escapeHtml(d.ai_summary)}<div class="ai-coach-note" style="margin-top: 6px;">AI 요약 · 아래 실제 수치만 근거로 작성</div></div>`
    : "";
  const score = d.overall_score ?? 50;

  content.innerHTML = `
    ${aiCoachHead(`${who} · 최근 랭크 ${escapeHtml(String(d.games_analyzed))}판`)}
    <div class="ai-coach-body">
      <div class="ai-coach-score-row">
        <div class="ai-coach-score" style="--score: ${Number(score) || 0};"><span>${escapeHtml(String(d.overall_score ?? "-"))}</span><small>종합</small></div>
        <div>
          <div style="font-weight: 800; color: var(--text-heading);">주 포지션 ${escapeHtml(d.main_position_kr || "-")} (${escapeHtml(String(d.main_position_games))}판) · 승률 ${escapeHtml(String(d.win_rate))}%</div>
          <div class="ai-coach-note">50점 = 같은 포지션 고티어 평균. ${escapeHtml(d.benchmark_note || "")}</div>
        </div>
      </div>
      ${summary}
      <div><div class="ai-coach-section-title">지표 비교</div>${metrics}</div>
      <div><div class="ai-coach-section-title" style="color: #34D399;">강점</div>${list(d.strengths)}</div>
      <div><div class="ai-coach-section-title" style="color: #F87171;">개선하면 좋은 점</div>${list(d.tips)}</div>
      ${d.death_note ? `<div class="ai-coach-note" style="color: #FBBF24;">${escapeHtml(d.death_note)}</div>` : ""}
      <div><div class="ai-coach-section-title">챔피언 폭</div><div class="ai-coach-pool">${pool}</div>
        <div class="ai-coach-note" style="margin-top: 6px;">${escapeHtml(d.pool_note || "")}</div></div>
    </div>`;
}

// 버튼 자리는 templates/index.html 검색 버튼 바로 오른쪽 (#btnAiCoach)
function initAiCoachButton() {
  const btn = document.getElementById("btnAiCoach");
  if (!btn || btn.dataset.ready) return;
  btn.dataset.ready = "1";
  btn.innerHTML = aiCoachLogoSvg();
  btn.addEventListener("click", () => {
    const input = document.getElementById("searchInput");
    openAiCoach(input ? input.value : "");
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initAiCoachButton);
} else {
  initAiCoachButton();
}
