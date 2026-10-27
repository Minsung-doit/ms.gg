// Server Ranking (서버 랭킹) Module

async function loadServerRanking() {
  const menuBtn = document.getElementById("btnOpenMobileMenuSheet");
  if (menuBtn) {
    menuBtn.classList.add("active");
  }
  document.querySelectorAll(".sheet-grid-item[data-tab]").forEach(item => {
    item.classList.toggle("active", item.getAttribute("data-tab") === "serverranking");
  });

  const accountEl = document.getElementById("srMyAccount");
  const boardEl = document.getElementById("srBoard");

  if (accountEl && !accountEl.innerHTML) {
    accountEl.innerHTML = `
      <div class="sr-loading">
        <i class="fa-solid fa-spinner fa-spin"></i> 내 계정 정보를 불러오는 중...
      </div>
    `;
  }
  if (boardEl && !boardEl.innerHTML) {
    boardEl.innerHTML = `
      <div class="sr-loading">
        <i class="fa-solid fa-spinner fa-spin"></i> 서버 랭킹 순위표를 불러오는 중...
      </div>
    `;
  }

  try {
    const [meRes, boardRes] = await Promise.all([
      fetch("/api/me"),
      fetch("/api/server-ranking")
    ]);

    const me = meRes.ok ? await meRes.json() : null;
    const board = boardRes.ok ? await boardRes.json() : null;

    renderMyAccountCard(me);
    renderServerBoard(board);
  } catch (err) {
    console.error("loadServerRanking failed:", err);
    if (typeof showToast === "function") {
      showToast("서버 랭킹 정보를 불러오는 중 오류가 발생했습니다.", "error");
    }
  }
}

async function connectRiotAccount(e) {
  if (e && e.preventDefault) e.preventDefault();
  const input = document.getElementById("srRiotIdInput");
  if (!input) return;
  const riotId = input.value.trim();
  if (!riotId) {
    if (typeof showToast === "function") {
      showToast("닉네임#태그 형식으로 입력해주세요.", "warning");
    }
    return;
  }

  const btn = document.getElementById("btnConnectRiotAccount");
  if (btn) btn.disabled = true;

  try {
    const res = await fetch("/api/me/riot-account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ riot_id: riotId })
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      if (typeof showToast === "function") {
        showToast(data.detail || data.message || "라이엇 계정이 성공적으로 연결되었습니다.", "success");
      }
      loadServerRanking();
    } else {
      if (typeof showToast === "function") {
        showToast(data.detail || "계정 연결 실패", "error");
      }
    }
  } catch (err) {
    if (typeof showToast === "function") {
      showToast("서버와 통신하는 중 오류가 발생했습니다.", "error");
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function disconnectRiotAccount() {
  if (!confirm("정말 라이엇 계정 연결을 해제하시겠습니까?")) return;
  const btn = document.getElementById("btnDisconnectRiotAccount");
  if (btn) btn.disabled = true;

  try {
    const res = await fetch("/api/me/riot-account", {
      method: "DELETE"
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      if (typeof showToast === "function") {
        showToast(data.detail || data.message || "라이엇 계정 연결이 해제되었습니다.", "success");
      }
      loadServerRanking();
    } else {
      if (typeof showToast === "function") {
        showToast(data.detail || "계정 연결 해제 실패", "error");
      }
    }
  } catch (err) {
    if (typeof showToast === "function") {
      showToast("서버와 통신하는 중 오류가 발생했습니다.", "error");
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderMyAccountCard(me) {
  const container = document.getElementById("srMyAccount");
  if (!container) return;

  if (!me) {
    container.innerHTML = `
      <div class="sr-card sr-card-error">
        <span>내 계정 정보를 가져올 수 없습니다.</span>
      </div>
    `;
    return;
  }

  // 1. 로그인 기능이 켜져 있는데(login_enabled) 로그인 안 됨(logged_in false)
  if (me.login_enabled && !me.logged_in) {
    container.innerHTML = `
      <div class="sr-card sr-card-login">
        <div class="sr-login-icon"><i class="fa-brands fa-discord" style="color: #5865F2;"></i></div>
        <div class="sr-login-text">
          <strong>디스코드 로그인 후 연결할 수 있습니다</strong>
          <span class="sr-sub-desc">디스코드 계정으로 로그인하여 내 라이엇 계정을 서버 랭킹에 등록해보세요.</span>
        </div>
        <a href="/login" class="sr-btn sr-btn-discord">
          <i class="fa-brands fa-discord"></i> 디스코드 로그인
        </a>
      </div>
    `;
    return;
  }

  // 2. 연결됨: "내 계정: 닉네임#태그" + "연결 해제" 버튼(confirm)
  if (me.account && me.account.game_name) {
    const gn = me.account.game_name;
    const tag = me.account.tag_line || "";
    container.innerHTML = `
      <div class="sr-card sr-card-linked">
        <div class="sr-linked-info">
          <span class="sr-label"><i class="fa-solid fa-id-badge"></i> 내 계정:</span>
          <span class="sr-name-highlight">
            <strong class="sr-linked-gn">${escapeHtml(gn)}</strong><span class="sr-linked-tag">#${escapeHtml(tag)}</span>
          </span>
          ${me.discord_name ? `<span class="sr-discord-tag">(${escapeHtml(me.discord_name)})</span>` : ""}
        </div>
        <button type="button" id="btnDisconnectRiotAccount" class="sr-btn sr-btn-danger" onclick="disconnectRiotAccount()">
          <i class="fa-solid fa-unlink"></i> 연결 해제
        </button>
      </div>
    `;
    return;
  }

  // 3. 연결 안 됨: 입력칸(placeholder "닉네임#태그") + "연결" 버튼
  container.innerHTML = `
    <div class="sr-card sr-card-unlinked">
      <div class="sr-unlinked-title">
        <i class="fa-solid fa-link"></i>
        <span>라이엇 계정 연결</span>
        ${me.discord_name ? `<span class="sr-discord-tag">${escapeHtml(me.discord_name)}</span>` : ""}
      </div>
      <form class="sr-connect-form" onsubmit="connectRiotAccount(event)">
        <input type="text" id="srRiotIdInput" class="sr-input" placeholder="닉네임#태그" autocomplete="off" required>
        <button type="submit" id="btnConnectRiotAccount" class="sr-btn sr-btn-primary">
          <i class="fa-solid fa-plus"></i> 연결
        </button>
      </form>
    </div>
  `;
}

function renderServerBoard(data) {
  const container = document.getElementById("srBoard");
  if (!container) return;

  if (!data || !Array.isArray(data.members) || data.members.length === 0) {
    container.innerHTML = `
      <div class="sr-card sr-empty-board">
        <i class="fa-solid fa-users sr-empty-icon"></i>
        <div class="sr-empty-text">아직 연결한 멤버가 없습니다.</div>
      </div>
    `;
    return;
  }

  const rowsHtml = data.members.map((m, idx) => {
    const rank = m.rank != null ? m.rank : (idx + 1);
    let rankBadgeClass = "";
    let medalIcon = "";
    if (rank === 1) {
      rankBadgeClass = "sr-top-1";
      medalIcon = '<i class="fa-solid fa-crown sr-medal-icon"></i> ';
    } else if (rank === 2) {
      rankBadgeClass = "sr-top-2";
      medalIcon = '<i class="fa-solid fa-medal sr-medal-icon"></i> ';
    } else if (rank === 3) {
      rankBadgeClass = "sr-top-3";
      medalIcon = '<i class="fa-solid fa-award sr-medal-icon"></i> ';
    }

    // 프로필 아이콘 (없으면 생략)
    const iconBase = (typeof ICON_BASE_URL !== "undefined") ? ICON_BASE_URL : "https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/";
    const iconHtml = (m.profile_icon_id != null && m.profile_icon_id !== "")
      ? `<img class="sr-avatar" src="${iconBase}${escapeHtml(String(m.profile_icon_id))}.png" alt="" onerror="this.style.display='none'">`
      : "";

    // 디스코드 이름(회색 작은 글씨)
    const discordHtml = m.discord_name
      ? `<span class="sr-discord-name">${escapeHtml(m.discord_name)}</span>`
      : "";

    // 닉네임#태그
    const gn = m.game_name || "-";
    const tag = m.tag_line || "";
    const nameHtml = `
      <div class="sr-identity">
        <div class="sr-riot-id">
          <strong class="sr-game-name">${escapeHtml(gn)}</strong>${tag ? `<span class="sr-tag">#${escapeHtml(tag)}</span>` : ""}
        </div>
        ${discordHtml}
      </div>
    `;

    // 티어(display_tier + LP)
    const tierDisplay = m.display_tier ? escapeHtml(m.display_tier) : (m.tier ? escapeHtml(m.tier) : "-");
    const lpDisplay = (m.league_points != null) ? `${formatNumber(m.league_points)} LP` : "";
    const tierFull = lpDisplay && !tierDisplay.includes("LP")
      ? `${tierDisplay} <span class="sr-lp">${lpDisplay}</span>`
      : tierDisplay;

    // 승/패/승률 (가짜 값 금지, 없으면 "-")
    let recordText = "-";
    const wrNum = m.win_rate != null ? parseFloat(m.win_rate) : null;
    const wrClass = wrNum != null ? (wrNum > 50 ? "sr-wr-high" : "sr-wr-low") : "";
    if (m.wins != null && m.losses != null) {
      const wrText = m.win_rate != null ? `${m.win_rate}%` : "-";
      recordText = `${formatNumber(m.wins)}승 ${formatNumber(m.losses)}패 <span class="sr-wr ${wrClass}">(${wrText})</span>`;
    } else if (m.win_rate != null) {
      recordText = `<span class="sr-wr ${wrClass}">${m.win_rate}%</span>`;
    }

    // 7일 변화(양수 초록 "+N", 음수 빨강, null 이면 "-")
    let deltaHtml = '<span class="sr-delta sr-delta-null">-</span>';
    if (m.lp_change_7d != null) {
      if (m.lp_change_7d > 0) {
        deltaHtml = `<span class="sr-delta sr-delta-up">+${m.lp_change_7d}</span>`;
      } else if (m.lp_change_7d < 0) {
        deltaHtml = `<span class="sr-delta sr-delta-down">${m.lp_change_7d}</span>`;
      } else {
        deltaHtml = `<span class="sr-delta sr-delta-zero">0</span>`;
      }
    }

    return `
      <div class="sr-row ${rankBadgeClass}" role="button" tabindex="0" onclick="openPlayerDetail({game_name: ${jsArg(m.game_name || '')}, tag_line: ${jsArg(m.tag_line || '')}})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click();}">
        <div class="sr-col-rank">
          <span class="sr-rank-num">${medalIcon}${rank}</span>
        </div>
        <div class="sr-col-player">
          ${iconHtml}
          ${nameHtml}
        </div>
        <div class="sr-col-tier">
          <span class="sr-tier-text">${tierFull}</span>
        </div>
        <div class="sr-col-record">
          ${recordText}
        </div>
        <div class="sr-col-delta">
          ${deltaHtml}
        </div>
      </div>
    `;
  }).join("");

  // 이번 주 MVP (7일 LP 상승 1위)와 같이 한 게임 (멤버 듀오)
  const mvp = data.mvp;
  const mvpHtml = mvp ? `
    <div class="sr-mvp-card" onclick="openPlayerDetail({game_name: ${jsArg(mvp.game_name)}, tag_line: ${jsArg(mvp.tag_line)}})">
      <i class="fa-solid fa-trophy sr-mvp-icon"></i>
      <div class="sr-mvp-main">
        <div class="sr-mvp-label">이번 주 MVP</div>
        <div class="sr-mvp-name">${escapeHtml(mvp.discord_name || mvp.game_name)} <span class="sr-mvp-riot">${escapeHtml(mvp.game_name)}#${escapeHtml(mvp.tag_line)}</span></div>
      </div>
      <div class="sr-mvp-lp">+${escapeHtml(String(mvp.lp_change_7d))} LP</div>
    </div>` : "";
  const duos = Array.isArray(data.duos) ? data.duos : [];
  const duoName = (x) => escapeHtml(x.discord_name || x.game_name);
  const duosHtml = duos.length ? `
    <div class="sr-duo-card">
      <div class="sr-duo-title"><i class="fa-solid fa-user-group"></i> 같이 한 게임 <span class="sr-duo-sub">최근 30일</span></div>
      ${duos.map(d => `
        <div class="sr-duo-row">
          <span class="sr-duo-names">${duoName(d.a)} <span class="sr-duo-plus">+</span> ${duoName(d.b)}</span>
          <span class="sr-duo-wr ${d.win_rate > 50 ? "is-good" : "is-bad"}">${escapeHtml(String(d.win_rate))}%</span>
          <span class="sr-duo-games">${escapeHtml(String(d.games))}판</span>
        </div>`).join("")}
    </div>` : "";

  container.innerHTML = mvpHtml + `
    <div class="sr-board-wrapper">
      <div class="sr-board-header">
        <div class="sr-col-rank">순위</div>
        <div class="sr-col-player">소환사</div>
        <div class="sr-col-tier">티어</div>
        <div class="sr-col-record">승패 (승률)</div>
        <div class="sr-col-delta">7일</div>
      </div>
      <div class="sr-board-body">
        ${rowsHtml}
      </div>
    </div>
  ` + duosHtml;
}

window.loadServerRanking = loadServerRanking;
window.connectRiotAccount = connectRiotAccount;
window.disconnectRiotAccount = disconnectRiotAccount;
window.renderMyAccountCard = renderMyAccountCard;
window.renderServerBoard = renderServerBoard;

if (typeof window._tabLoaders === "object" && window._tabLoaders) {
  window._tabLoaders.serverranking = loadServerRanking;
}
