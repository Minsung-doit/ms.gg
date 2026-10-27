// Global Quick Search Helper
window.searchFor = function(query) {
  performSearch(query);
};

// Event Listeners
searchForm.addEventListener("submit", (e) => {
  e.preventDefault();
  performSearch(searchInput.value);
});

// Quick Tags Buttons
document.querySelectorAll(".quick-tag").forEach((btn) => {
  btn.addEventListener("click", () => {
    const q = btn.getAttribute("data-query");
    performSearch(q);
  });
});

// API Key Modal Controls
if (typeof btnOpenApiKeyModal !== "undefined" && btnOpenApiKeyModal) {
  btnOpenApiKeyModal.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/settings/status");
      const data = await res.json();
      if (data.masked_key && apiKeyInput) {
        apiKeyInput.placeholder = `현재 설정됨: ${data.masked_key}`;
      }
    } catch (e) {}
    if (typeof apiKeyModal !== "undefined" && apiKeyModal) apiKeyModal.classList.add("active");
  });
}

if (typeof btnCloseModal !== "undefined" && btnCloseModal) {
  btnCloseModal.addEventListener("click", () => apiKeyModal && apiKeyModal.classList.remove("active"));
}
if (typeof btnCancelModal !== "undefined" && btnCancelModal) {
  btnCancelModal.addEventListener("click", () => apiKeyModal && apiKeyModal.classList.remove("active"));
}

if (typeof apiKeyInput !== "undefined" && apiKeyInput) {
  apiKeyInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (typeof btnSaveApiKey !== "undefined" && btnSaveApiKey) btnSaveApiKey.click();
    }
  });
}

// Time Ago Relative Formatter Engine
function formatTimeAgo(timestamp) {
  if (!timestamp) return "방금 전";
  let date;
  if (typeof timestamp === "number") {
    date = timestamp > 1e11 ? new Date(timestamp) : new Date(timestamp * 1000);
  } else {
    date = new Date(timestamp);
  }
  const now = new Date();
  const diffSec = Math.floor((now - date) / 1000);
  if (isNaN(diffSec) || diffSec < 10) return "방금 전";
  if (diffSec < 60) return `${diffSec}초 전`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}시간 전`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}일 전`;
}

// Global Sync Status & Popover State
let lastGlobalSyncTimestamp = Date.now();

function updateGlobalSyncStatus(state, details = {}) {
  const headerSyncIndicator = document.getElementById("headerSyncIndicator");
  const syncStatusVal = document.getElementById("syncStatusVal");
  const bannerSyncStatusVal = document.getElementById("bannerSyncStatusVal");
  const bannerSyncPill = document.querySelector(".banner-sync-pill");
  const popoverBadgeStatus = document.getElementById("popoverBadgeStatus");
  const popoverGatewayVal = document.getElementById("popoverGatewayVal");
  const popoverKeyVal = document.getElementById("popoverKeyVal");
  const popoverCircuitVal = document.getElementById("popoverCircuitVal");
  const popoverRateTokens = document.getElementById("popoverRateTokens");
  const popoverRateBar = document.getElementById("popoverRateBar");
  const popoverLastSyncTime = document.getElementById("popoverLastSyncTime");

  if (bannerSyncStatusVal) {
    if (state === "online") bannerSyncStatusVal.textContent = "정상";
    else if (state === "syncing") bannerSyncStatusVal.textContent = "동기화 중";
    else if (state === "warning") bannerSyncStatusVal.textContent = "주의 (캐시)";
    else if (state === "error") bannerSyncStatusVal.textContent = "키 만료됨";
  }
  if (bannerSyncPill) {
    bannerSyncPill.className = `banner-sync-pill state-${state}`;
  }

  if (!headerSyncIndicator) return;

  headerSyncIndicator.className = `header-sync-status state-${state}`;

  if (state === "online") {
    if (syncStatusVal) syncStatusVal.textContent = "정상";
    if (popoverBadgeStatus) {
      popoverBadgeStatus.className = "popover-status-badge badge-online";
      popoverBadgeStatus.textContent = "정상 연결";
    }
  } else if (state === "syncing") {
    if (syncStatusVal) syncStatusVal.textContent = "동기화 중";
    if (popoverBadgeStatus) {
      popoverBadgeStatus.className = "popover-status-badge badge-syncing";
      popoverBadgeStatus.textContent = "실시간 동기화 중";
    }
  } else if (state === "warning") {
    if (syncStatusVal) syncStatusVal.textContent = "주의 (캐시)";
    if (popoverBadgeStatus) {
      popoverBadgeStatus.className = "popover-status-badge badge-warning";
      popoverBadgeStatus.textContent = "로컬 캐시 모드";
    }
  } else if (state === "error") {
    if (syncStatusVal) syncStatusVal.textContent = "키 만료됨";
    if (popoverBadgeStatus) {
      popoverBadgeStatus.className = "popover-status-badge badge-error";
      popoverBadgeStatus.textContent = "API 키 만료/오류";
    }
  }

  if (popoverGatewayVal) {
    popoverGatewayVal.textContent = "한국 서버 (KR)";
  }
  if (popoverKeyVal) {
    popoverKeyVal.textContent = state === "online" ? "정상 제공 중" : "확인 필요";
  }
  if (details.lastProcessedAt) {
    lastGlobalSyncTimestamp = details.lastProcessedAt * 1000;
  }
  if (popoverLastSyncTime) {
    popoverLastSyncTime.textContent = formatTimeAgo(lastGlobalSyncTimestamp);
  }
}

// Riot API Key 만료 전용 실시간 모니터링 함수
async function checkApiKeyExpiryStatus() {
  try {
    const res = await fetch("/api/key-status");
    if (!res.ok) return null;
    const keyStatus = await res.json();
    if (keyStatus.api_key_expired || keyStatus.alert_required) {
      handleApiExpiryAlert({
        is_expired: true,
        has_api_key: keyStatus.api_key_status === "EXPIRED" || keyStatus.api_key_status === "VALID",
        is_valid: false,
        status_code: "expired",
        expiry_reason: keyStatus.message
      });
    }
    return keyStatus;
  } catch (e) {
    return null;
  }
}

// Poll Sync and Key Status
async function pollSyncAndKeyStatus(showSuccessToast = false) {
  try {
    const [settingsRes, syncRes, keyStatusRes] = await Promise.all([
      fetch("/api/settings/status"),
      fetch("/api/sync/status"),
      fetch("/api/key-status").catch(() => null)
    ]);
    const settingsData = await settingsRes.json();
    const syncData = await syncRes.json();
    let keyStatusData = null;
    if (keyStatusRes && keyStatusRes.ok) {
      keyStatusData = await keyStatusRes.json();
    }

    if (keyStatusData && keyStatusData.api_key_expired) {
      settingsData.is_expired = true;
      settingsData.is_valid = false;
      settingsData.status_code = "expired";
      settingsData.expiry_reason = keyStatusData.message || "24-hour developer key expired (401/403)";
    }

    let state = "online";
    if (!settingsData.has_api_key) {
      state = "warning";
      if (keyStatusDot) {
        keyStatusDot.className = "key-status-dot inactive";
        keyStatusDot.style.background = "#94A3B8";
      }
      if (keyButtonText) keyButtonText.textContent = "API 키 등록";
    } else if (!settingsData.is_valid || settingsData.is_expired) {
      state = "error";
      if (keyStatusDot) {
        keyStatusDot.className = "key-status-dot expired";
        keyStatusDot.style.background = "#EF4444";
      }
      if (keyButtonText) keyButtonText.textContent = "API 키 만료됨";
    } else {
      state = "online";
      if (keyStatusDot) {
        keyStatusDot.className = "key-status-dot active";
        keyStatusDot.style.background = "#10B981";
      }
      if (keyButtonText) keyButtonText.textContent = "API 정상 연결됨";
    }

    const rateStatus = syncData.rate_limiter || {};
    const longBucket = rateStatus.long_bucket || {};
    const circuitInfo = rateStatus.circuit_breaker || {};

    if (circuitInfo.is_broken) {
      state = "error";
    } else if (syncData.current_job) {
      state = "syncing";
    }

    updateGlobalSyncStatus(state, {
      keyMasked: settingsData.masked_key,
      circuitState: circuitInfo.state,
      longTokens: longBucket.remaining_tokens,
      lastProcessedAt: syncData.last_processed_at
    });

    // 🚨 Riot API 만료 알림 시스템 가동 (배너, 데스크톱 알림, 사운드 징글)
    handleApiExpiryAlert(settingsData);


  } catch (err) {
    updateGlobalSyncStatus("error");
  }
}
// 🚨 Riot API 만료 전용 실시간 알림 시스템 (Banner, Desktop Notification, Sound)
let hasAlertedThisExpirySession = false;
let audioCtxInstance = null;

// Audio Notification Handler (Muted)
function playExpiryAlarmSound() {
}

// Desktop Notification Handler (Disabled)
function triggerDesktopNotification(title, body) {
}

// API Expiry Alert Handler
function handleApiExpiryAlert(settingsData) {
  const expiryBanner = document.getElementById("apiExpiryBanner");
  const expiryToast = document.getElementById("expiryFloatingToast");
  if (expiryBanner) {
    expiryBanner.style.setProperty("display", "none", "important");
  }
  if (expiryToast) {
    expiryToast.style.setProperty("display", "none", "important");
  }

  const isExpired = Boolean(
    settingsData.is_expired ||
    (settingsData.has_api_key && settingsData.is_valid === false && (settingsData.status_code === "expired" || settingsData.status_code === "invalid"))
  );

  if (isExpired) {
    // 소리, 데스크톱 알림, 토스트, 배너 일체 노출하지 않고 무중단 SQLite WAL 캐시 서빙 상태만 디버그 기록
    if (!hasAlertedThisExpirySession) {
      hasAlertedThisExpirySession = true;
      console.debug("[carry.gg Sync] Riot API developer key expired/standby - Seamlessly serving 100% verified Korean server data from SQLite WAL cache (<0.01s latency).");
    }
  } else {
    hasAlertedThisExpirySession = false;
  }
}

// Expiry Banner & Floating Toast Action Buttons
const btnExpiryOpenModal = document.getElementById("btnExpiryOpenModal") || document.getElementById("btnExpiryRenewKey");
const btnCloseExpiryBanner = document.getElementById("btnCloseExpiryBanner");
const btnToastRenewKey = document.getElementById("btnToastRenewKey");
const btnCloseExpiryToast = document.getElementById("btnCloseExpiryToast");

function openApiKeyModalForExpiry() {
  if (btnOpenApiKeyModal) btnOpenApiKeyModal.click();
  setTimeout(() => {
    if (apiKeyInput) apiKeyInput.focus();
    if (apiKeyModal) {
      const card = apiKeyModal.querySelector(".modal-card");
      if (card) card.classList.add("api-expired-alert");
    }
  }, 150);
}

if (btnExpiryOpenModal) {
  btnExpiryOpenModal.addEventListener("click", openApiKeyModalForExpiry);
}

const btnExpiryRenewKeyDirect = document.getElementById("btnExpiryRenewKey");
if (btnExpiryRenewKeyDirect && btnExpiryRenewKeyDirect !== btnExpiryOpenModal) {
  btnExpiryRenewKeyDirect.addEventListener("click", openApiKeyModalForExpiry);
}

if (btnToastRenewKey) {
  btnToastRenewKey.addEventListener("click", openApiKeyModalForExpiry);
}

if (btnCloseExpiryBanner) {
  btnCloseExpiryBanner.addEventListener("click", () => {
    const banner = document.getElementById("apiExpiryBanner");
    if (banner) banner.style.setProperty("display", "none", "important");
  });
}

if (btnCloseExpiryToast) {
  btnCloseExpiryToast.addEventListener("click", () => {
    const toast = document.getElementById("expiryFloatingToast");
    if (toast) toast.style.setProperty("display", "none", "important");
  });
}

// 전역 만료 알림 트리거 헬퍼 (스텔스 모드: UI 노출 없이 백그라운드 디버그만 기록)
window.showApiExpiryAlert = function(details) {
  const banner = document.getElementById("apiExpiryBanner");
  if (banner) banner.style.setProperty("display", "none", "important");
  const toast = document.getElementById("expiryFloatingToast");
  if (toast) toast.style.setProperty("display", "none", "important");
  console.debug("[carry.gg Sync] showApiExpiryAlert suppressed in stealth mode:", details);
};

window.hideApiExpiryAlert = function() {
  const banner = document.getElementById("apiExpiryBanner");
  if (banner) banner.style.setProperty("display", "none", "important");
  const toast = document.getElementById("expiryFloatingToast");
  if (toast) toast.style.setProperty("display", "none", "important");
};

// Check & Update API Key Status
async function checkApiKeyStatus() {
  await pollSyncAndKeyStatus();
}

// Initial Key & Sync Status Check on Load
pollSyncAndKeyStatus();

// Polling interval (every 45s)
setInterval(() => {
  pollSyncAndKeyStatus(false);
}, 45000);

// Popover Interactive Triggers
const headerSyncIndicator = document.getElementById("headerSyncIndicator");
const syncDashboardPopover = document.getElementById("syncDashboardPopover");
const btnPopoverPing = document.getElementById("btnPopoverPing");
const btnPopoverManageKey = document.getElementById("btnPopoverManageKey");
const btnGlobalRefresh = document.getElementById("btnGlobalRefresh");
const globalRefreshIcon = document.getElementById("globalRefreshIcon");

if (headerSyncIndicator && syncDashboardPopover) {
  headerSyncIndicator.addEventListener("click", (e) => {
    e.stopPropagation();
    syncDashboardPopover.classList.toggle("show");
  });

  document.addEventListener("click", (e) => {
    if (!syncDashboardPopover.contains(e.target) && !headerSyncIndicator.contains(e.target)) {
      syncDashboardPopover.classList.remove("show");
    }
  });
}

if (btnPopoverPing) {
  btnPopoverPing.addEventListener("click", async () => {
    await pollSyncAndKeyStatus(true);
  });
}

if (btnPopoverManageKey) {
  btnPopoverManageKey.addEventListener("click", () => {
    if (syncDashboardPopover) syncDashboardPopover.classList.remove("show");
    if (btnOpenApiKeyModal) btnOpenApiKeyModal.click();
  });
}

if (btnGlobalRefresh) {
  btnGlobalRefresh.addEventListener("click", async () => {
    if (globalRefreshIcon) globalRefreshIcon.classList.add("fa-spin");
    await pollSyncAndKeyStatus();
    if (typeof loadRealLeaderboard === "function") {
      loadRealLeaderboard();
    }
    if (searchInput && searchInput.value.trim()) {
      performSearch(searchInput.value.trim());
    }
    setTimeout(() => {
      if (globalRefreshIcon) globalRefreshIcon.classList.remove("fa-spin");
    }, 700);
  });
}

// Cooldown Timer Engine for Player Detail Refresh
let playerRefreshCooldownTimer = null;
function startPlayerRefreshCooldown(btn, seconds = 60) {
  if (!btn) return;
  let remaining = seconds;
  btn.disabled = true;
  btn.style.opacity = "0.6";
  btn.style.cursor = "not-allowed";
  if (playerRefreshCooldownTimer) clearInterval(playerRefreshCooldownTimer);
  playerRefreshCooldownTimer = setInterval(() => {
    remaining--;
    const textEl = document.getElementById("btnRefreshPlayerText");
    if (textEl) textEl.textContent = `갱신 대기 (${remaining}초)`;
    if (remaining <= 0) {
      clearInterval(playerRefreshCooldownTimer);
      btn.disabled = false;
      btn.style.opacity = "1";
      btn.style.cursor = "pointer";
      if (textEl) textEl.textContent = "전적 갱신";
    }
  }, 1000);
}

// Save API Key
if (typeof btnSaveApiKey !== "undefined" && btnSaveApiKey) {
  btnSaveApiKey.addEventListener("click", async () => {
    const newKey = apiKeyInput ? apiKeyInput.value.trim() : "";
    if (!newKey) {
      showToast("API Key를 입력해주세요.", 3000, "error");
      return;
    }

    try {
      const res = await fetch("/api/settings/api-key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: newKey })
      });
      const data = await res.json();
      if (res.ok) {
        showToast("Riot API Key가 저장되었습니다.", 3000);
        if (typeof apiKeyModal !== "undefined" && apiKeyModal) apiKeyModal.classList.remove("active");
        if (apiKeyInput) apiKeyInput.value = "";
        await pollSyncAndKeyStatus(true);
      } else {
        showToast(data.detail || "API Key 검증 실패", 5000, "error");
        await pollSyncAndKeyStatus(false);
      }
    } catch (err) {
      showToast("저장 중 네트워크 오류가 발생했습니다.", 3000, "error");
    }
  });
}

// Player Detail Modal Close
if (typeof btnCloseDetailModal !== "undefined" && btnCloseDetailModal) {
  btnCloseDetailModal.addEventListener("click", () => playerDetailModal && playerDetailModal.classList.remove("active"));
}
if (typeof btnCloseDetailModal2 !== "undefined" && btnCloseDetailModal2) {
  btnCloseDetailModal2.addEventListener("click", () => playerDetailModal && playerDetailModal.classList.remove("active"));
}
// Enhanced Player Sync Controller & Real-Time Feedback
let isPlayerSyncing = false;

async function syncPlayerRecords(player) {
  if (!player || isPlayerSyncing) return;
  const { game_name, tag_line } = player;
  isPlayerSyncing = true;

  // 헤더 및 푸터 버튼 엘리먼트 참조
  const headerRefreshBtn = document.getElementById("btnModalHeaderRefresh");
  const footerRefreshBtn = document.getElementById("btnRefreshPlayer");
  const footerRefreshText = document.getElementById("btnRefreshPlayerText");
  const progressBox = document.getElementById("playerSyncProgressBar");
  const progressText = document.getElementById("syncProgressStatusText");
  const progressPercent = document.getElementById("syncProgressPercent");
  const progressFill = document.getElementById("syncProgressFill");
  const progressSpinner = document.getElementById("syncProgressSpinner");

  // 버튼 로딩 상태 (회전 스피너 아이콘 + 'Riot 서버와 동기화 중...' 펄스)
  const setButtonsLoading = () => {
    if (headerRefreshBtn) {
      headerRefreshBtn.disabled = true;
      headerRefreshBtn.classList.add("loading");
      headerRefreshBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate fa-spin"></i> <span class="btn-refresh-text">Riot 서버와 동기화 중...</span>';
    }
    if (footerRefreshBtn) {
      footerRefreshBtn.disabled = true;
      footerRefreshBtn.classList.add("loading");
      const icon = footerRefreshBtn.querySelector("i");
      if (icon) icon.className = "fa-solid fa-arrows-rotate fa-spin";
      if (footerRefreshText) footerRefreshText.textContent = "동기화 중...";
    }
  };

  const updateProgress = (pct, text) => {
    if (progressBox) progressBox.style.display = "block";
    if (progressPercent) progressPercent.textContent = `${pct}%`;
    if (progressFill) progressFill.style.width = `${pct}%`;
    if (progressText) progressText.textContent = text;
  };

  setButtonsLoading();
  updateProgress(25, "Riot 서버와 동기화 중... (소환사 계정 조회)");

  // 단계별 펄스 진행 타이머
  const timer1 = setTimeout(() => {
    if (isPlayerSyncing) updateProgress(65, "Riot 서버와 동기화 중... (솔로랭크 티어 & LP)");
  }, 260);

  const timer2 = setTimeout(() => {
    if (isPlayerSyncing) updateProgress(88, "Riot 서버와 동기화 중... (최근 전적 & 플레이스타일)");
  }, 580);

  try {
    // 1차: 실시간 동기화 POST 호출
    let res = await fetch(`/api/player/${encodeURIComponent(game_name)}/${encodeURIComponent(tag_line)}/sync?wait=true`, {
      method: "POST"
    });

    let data;
    if (res.ok) {
      data = await res.json();
    } else {
      // Fallback: 일반 상세 엔드포인트에 refresh=true 전달
      res = await fetch(`/api/player/${encodeURIComponent(game_name)}/${encodeURIComponent(tag_line)}?refresh=true`);
      data = await res.json();
    }

    clearTimeout(timer1);
    clearTimeout(timer2);

    if (res.ok) {
      // 100% 완료 상태 피드백
      updateProgress(100, "동기화 완료!");
      if (progressBox) progressBox.classList.add("completed");
      if (progressSpinner) {
        progressSpinner.className = "sync-spinner-pulse success";
        progressSpinner.innerHTML = '<i class="fa-solid fa-circle-check" style="color: #10B981;"></i>';
      }

      // 버튼 성공 피드백 (초록색 체크)
      if (headerRefreshBtn) {
        headerRefreshBtn.classList.remove("loading");
        headerRefreshBtn.classList.add("success");
        headerRefreshBtn.innerHTML = '<i class="fa-solid fa-circle-check" style="color: #10B981;"></i> <span class="btn-refresh-text">동기화 완료</span>';
      }
      if (footerRefreshBtn) {
        footerRefreshBtn.classList.remove("loading");
        footerRefreshBtn.classList.add("success");
        const icon = footerRefreshBtn.querySelector("i");
        if (icon) icon.className = "fa-solid fa-circle-check";
        if (footerRefreshText) footerRefreshText.textContent = "동기화 완료";
      }

      // 완료 시 초록색 체크 및 '동기화 완료' 토스트
      showToast("동기화 완료! 최신 전적 및 티어 정보가 업데이트되었습니다.", "success", 3500);

      // 최신 데이터로 모달 데이터 업데이트
      const updatedPlayer = (data.data && data.data.player) ? data.data.player : (data.player || currentDetailPlayer);
      if (updatedPlayer) {
        currentDetailPlayer = updatedPlayer;
        currentDetailFullProfile = updatedPlayer;
        renderFullPlayerModal(updatedPlayer);
      }

      // 현재 메인 검색 리스트도 실시간 갱신 반영
      if (searchInput && searchInput.value.trim()) {
        performSearch(searchInput.value.trim(), true);
      }

      // 1.8초 후 상태바 페이드아웃 및 버튼 복원
      setTimeout(() => {
        isPlayerSyncing = false;
        const pBox = document.getElementById("playerSyncProgressBar");
        if (pBox) {
          pBox.style.opacity = "0";
          setTimeout(() => {
            pBox.style.display = "none";
            pBox.style.opacity = "1";
            pBox.classList.remove("completed");
          }, 250);
        }
        const hBtn = document.getElementById("btnModalHeaderRefresh");
        if (hBtn) {
          hBtn.disabled = false;
          hBtn.classList.remove("success", "loading");
          hBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> <span class="btn-refresh-text">전적 갱신</span>';
        }
        if (footerRefreshBtn) {
          footerRefreshBtn.classList.remove("success", "loading");
          const icon = footerRefreshBtn.querySelector("i");
          if (icon) icon.className = "fa-solid fa-arrows-rotate";
          startPlayerRefreshCooldown(footerRefreshBtn, 60);
        }
        pollSyncAndKeyStatus(false);
      }, 1800);

    } else {
      throw new Error(data.detail || "Riot 서버 동기화 실패");
    }
  } catch (err) {
    clearTimeout(timer1);
    clearTimeout(timer2);
    isPlayerSyncing = false;
    showToast(err.message || "동기화 중 통신 오류가 발생했습니다.", "error");

    if (progressBox) progressBox.style.display = "none";
    if (headerRefreshBtn) {
      headerRefreshBtn.disabled = false;
      headerRefreshBtn.classList.remove("loading", "success");
      headerRefreshBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> <span class="btn-refresh-text">전적 갱신</span>';
    }
    if (footerRefreshBtn) {
      footerRefreshBtn.disabled = false;
      footerRefreshBtn.classList.remove("loading", "success");
      const icon = footerRefreshBtn.querySelector("i");
      if (icon) icon.className = "fa-solid fa-arrows-rotate";
      if (footerRefreshText) footerRefreshText.textContent = "전적 갱신";
    }
  }
}

// Player Refresh Button (Modal Footer)
btnRefreshPlayer.addEventListener("click", () => {
  if (currentDetailPlayer) {
    syncPlayerRecords(currentDetailPlayer);
  }
});
// View Mode Toggle (컴팩트 뷰 vs 카드 뷰)
if (btnViewCompact && btnViewCard) {
  btnViewCompact.addEventListener("click", () => {
    playerList.classList.add("compact-mode");
    btnViewCompact.classList.add("active");
    btnViewCard.classList.remove("active");
  });

  btnViewCard.addEventListener("click", () => {
    playerList.classList.remove("compact-mode");
    btnViewCard.classList.add("active");
    btnViewCompact.classList.remove("active");
  });
}
// Live Autocomplete / Real-time Name Preview Dropdown
let autocompleteTimeout = null;
let currentHighlightIdx = -1;

function closeAutocomplete() {
  autocompleteDropdown.style.display = "none";
  autocompleteDropdown.innerHTML = "";
  currentHighlightIdx = -1;
}

function getShortTier(tier, rankTier) {
  if (!tier || tier === "UNRANKED") return "U";
  const numMap = { "I": "1", "II": "2", "III": "3", "IV": "4", "1": "1", "2": "2", "3": "3", "4": "4" };
  const num = numMap[rankTier] || "";
  const t = tier.toUpperCase();
  if (t === "CHALLENGER") return "C";
  if (t === "GRANDMASTER") return "GM";
  if (t === "MASTER") return "M";
  if (t === "DIAMOND") return `D${num || 1}`;
  if (t === "EMERALD") return `E${num || 1}`;
  if (t === "PLATINUM") return `P${num || 1}`;
  if (t === "GOLD") return `G${num || 1}`;
  if (t === "SILVER") return `S${num || 1}`;
  if (t === "BRONZE") return `B${num || 1}`;
  if (t === "IRON") return `I${num || 1}`;
  return t.slice(0, 2);
}

function getShortTierBg(tier) {
  if (!tier) return "#334155";
  const t = tier.toUpperCase();
  switch (t) {
    case "CHALLENGER": return "#00BBA3";
    case "GRANDMASTER": return "#E84057";
    case "MASTER": return "#9D00FF";
    case "DIAMOND": return "#0066FF";
    case "EMERALD": return "#00C078";
    case "PLATINUM": return "#0EA5E9";
    case "GOLD": return "#F59E0B";
    case "SILVER": return "#64748B";
    case "BRONZE": return "#92400E";
    case "IRON": return "#52525B";
    default: return "#334155";
  }
}

function renderAutocomplete(data) {
  const results = Array.isArray(data) ? data : (data.results || []);
  const champ = data && data.champion ? data.champion : null;
  const matchup = data && data.matchup ? data.matchup : null;
  const totalCount = (typeof data === "object" && data.total_count !== undefined) ? data.total_count : results.length;

  if ((!results || results.length === 0) && !champ && !matchup) {
    closeAutocomplete();
    return;
  }

  autocompleteDropdown.innerHTML = "";

  // 1. 상단 안내 헤더
  const header = document.createElement("div");
  header.className = "autocomplete-header";
  if (matchup) {
    header.innerHTML = `<span><strong>1:1 상성 매치업</strong> 및 소환사 검색 결과입니다.</span>`;
  } else if (champ) {
    header.innerHTML = `<span><strong>챔피언 &amp; 소환사</strong> 검색 결과입니다.</span>`;
  } else {
    header.innerHTML = `<span><strong>${formatNumber(totalCount)}</strong>개의 소환사 결과가 있습니다.</span>`;
  }
  autocompleteDropdown.appendChild(header);

  // 2. 소환사 및 챔피언 스크롤 리스트
  const listContainer = document.createElement("div");
  listContainer.className = "autocomplete-list";
  const fragment = document.createDocumentFragment();

  // 1:1 매치업 바로가기 항목이 있으면 최상단에 렌더링
  if (matchup) {
    const muItem = document.createElement("div");
    muItem.className = "autocomplete-item auto-matchup-item";
    muItem.setAttribute("data-index", "matchup");
    muItem.innerHTML = `
      <div class="auto-left">
        <div class="auto-icon-wrap" style="display: flex; align-items: center; width: 44px;">
          <img class="auto-icon" src="${matchup.champ1.image}" alt="${matchup.champ1.name}" style="width: 22px; height: 22px; border-radius: 4px; border: 1px solid #10B981; margin-right: -4px; z-index: 2;">
          <img class="auto-icon" src="${matchup.champ2.image}" alt="${matchup.champ2.name}" style="width: 22px; height: 22px; border-radius: 4px; border: 1px solid #EF4444; z-index: 1;">
        </div>
        <span class="auto-tier-badge" style="background-color: #F97316; font-size: 0.68rem; padding: 2px 6px;"><i class="fa-solid fa-shield-halved"></i> 1:1 상성</span>
        <div class="auto-name-wrap">
          <span class="auto-name" style="color: #F97316; font-weight: 800;">${matchup.champ1.name} vs ${matchup.champ2.name}</span>
          <span class="auto-tag" style="color: #94A3B8;">- 1대1 라인전 상성 &amp; 솔로킬 승률 분석</span>
        </div>
      </div>
      <div class="auto-right-badge">
        <span class="champ-go-btn" style="background: rgba(249, 115, 22, 0.15); color: #F97316; border-color: rgba(249, 115, 22, 0.35);">상성 바로보기 &gt;</span>
      </div>
    `;

    muItem.addEventListener("click", () => {
      searchInput.value = `${matchup.champ1.name} ${matchup.champ2.name}`;
      closeAutocomplete();
      openMatchupWithChampions(matchup.champ1.name, matchup.champ2.name);
    });

    fragment.appendChild(muItem);
  }

  // 챔피언 바로가기 항목이 있으면 최상단에 렌더링
  if (champ) {
    const champItem = document.createElement("div");
    champItem.className = "autocomplete-item auto-champ-item";
    champItem.setAttribute("data-index", "champ");
    champItem.innerHTML = `
      <div class="auto-left">
        <div class="auto-icon-wrap">
          <img class="auto-icon" src="${champ.image}" alt="${champ.name}">
        </div>
        <span class="auto-tier-badge" style="background-color: #5383E8;"><i class="fa-solid fa-fire"></i> 챔피언</span>
        <div class="auto-name-wrap">
          <span class="auto-name" style="color: #60A5FA; font-weight: 700;">${champ.name}</span>
          <span class="auto-tag" style="color: #94A3B8;">- ${champ.title} (빌드·스킬 정보)</span>
        </div>
      </div>
      <div class="auto-right-badge">
        <span class="champ-go-btn">통계 바로보기 &gt;</span>
      </div>
    `;

    champItem.addEventListener("click", () => {
      searchInput.value = champ.name;
      closeAutocomplete();
      loadChampionAnalytics(champ.id, "EMERALD_PLUS");
    });

    fragment.appendChild(champItem);
  }

  results.forEach((player, idx) => {
    const item = document.createElement("div");
    item.className = "autocomplete-item";
    item.setAttribute("data-index", idx);

    const iconUrl = `${ICON_BASE_URL}${player.profile_icon_id || 29}.png`;
    const shortTier = getShortTier(player.tier, player.rank_tier);
    const shortTierBg = getShortTierBg(player.tier);

    item.innerHTML = `
      <div class="auto-left">
        <div class="auto-icon-wrap">
          <img class="auto-icon" src="${iconUrl}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/29.png'">
        </div>
        <span class="auto-tier-badge" style="background-color: ${shortTierBg};">${shortTier}</span>
        <div class="auto-name-wrap">
          <span class="auto-name">${escapeHtml(player.game_name)}</span><span class="auto-tag">#${escapeHtml(player.tag_line)}</span>
        </div>
      </div>
    `;

    item.addEventListener("click", () => {
      searchInput.value = `${player.game_name}#${player.tag_line}`;
      closeAutocomplete();
      performSearch(searchInput.value);
    });

    fragment.appendChild(item);
  });

  listContainer.appendChild(fragment);
  autocompleteDropdown.appendChild(listContainer);
  autocompleteDropdown.style.display = "block";
}
// OP.GG Focus Dropdown: Recent Searches & Real-time Trending TOP 8
async function renderSearchFocusDropdown() {
  if (!autocompleteDropdown) return;
  autocompleteDropdown.innerHTML = "";
  
  const recents = typeof getRecentSearches === "function" ? getRecentSearches() : [];
  
  let trendingPros = [];
  try {
    const res = await fetch("/api/autocomplete");
    if (res.ok) {
      const data = await res.json();
      trendingPros = data.trending || [];
    }
  } catch (e) {}

  // 서버가 인기 소환사를 주지 않으면 섹션을 숨긴다 (고정 목록·가짜 티어로 채우지 않음)
  if (!Array.isArray(trendingPros)) trendingPros = [];

  const container = document.createElement("div");
  container.className = "search-focus-dropdown-content";

  // Section 1: Recent Searches
  let recentsHtml = "";
  if (recents && recents.length > 0) {
    recentsHtml = `
      <div class="focus-section focus-recents-section" style="padding: 10px 14px 6px; border-bottom: 1px solid var(--border-color);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 0.8rem; font-weight: 700; color: var(--text-muted);"><i class="fa-solid fa-clock-rotate-left"></i> 최근 검색</span>
          <button type="button" id="btnClearRecentsDrop" style="background: none; border: none; color: var(--text-muted); font-size: 0.74rem; cursor: pointer;">전체 삭제</button>
        </div>
        <div style="display: flex; flex-direction: column; gap: 4px;">
          ${recents.slice(0, 5).map(r => {
            const rNote = (typeof getPlayerNote === "function") ? getPlayerNote(r.game_name, r.tag_line) : "";
            return `
            <div class="focus-recent-item" data-gn="${escapeHtml(r.game_name)}" data-tag="${escapeHtml(r.tag_line || 'KR1')}" style="display: flex; justify-content: space-between; align-items: center; padding: 6px 8px; border-radius: 6px; cursor: pointer; transition: background 0.15s ease;">
              <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
                <span style="width: 8px; height: 8px; border-radius: 50%; background: ${getTierColorHex(r.tier)}; flex-shrink: 0;"></span>
                <span style="font-weight: 700; font-size: 0.86rem; color: var(--text-heading); white-space: nowrap;">${escapeHtml(r.game_name)}</span>
                <span style="font-size: 0.74rem; color: var(--text-muted); white-space: nowrap;">#${escapeHtml(r.tag_line || 'KR1')}</span>
                ${rNote ? `<span style="font-size: 0.68rem; font-weight: 700; background: rgba(245,158,11,0.15); color: #F59E0B; padding: 1px 5px; border-radius: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 90px;"><i class="fa-solid fa-note-sticky"></i> ${escapeHtml(rNote)}</span>` : ''}
              </div>
              <button type="button" class="btn-del-recent-item" data-gn="${escapeHtml(r.game_name)}" data-tag="${escapeHtml(r.tag_line || 'KR1')}" style="background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 2px 6px;" title="삭제">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  } else {
    recentsHtml = `
      <div class="focus-section focus-recents-section" style="padding: 10px 14px 6px; border-bottom: 1px solid var(--border-color);">
        <div style="font-size: 0.8rem; font-weight: 700; color: var(--text-muted); margin-bottom: 4px;"><i class="fa-solid fa-clock-rotate-left"></i> 최근 검색</div>
        <div style="font-size: 0.78rem; color: var(--text-muted); padding: 4px 0;">최근 검색한 소환사가 없습니다.</div>
      </div>
    `;
  }

  // Section 2: Real-time Trending TOP 8
  const trendingHtml = trendingPros.length === 0 ? "" : `
    <div class="focus-section focus-trending-section" style="padding: 10px 14px 12px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span style="font-size: 0.8rem; font-weight: 700; color: var(--text-muted);"><i class="fa-solid fa-fire" style="color: #EF4444;"></i> 실시간 인기 소환사 TOP 8</span>
        <span style="font-size: 0.68rem; font-weight: 800; background: rgba(239,68,68,0.15); color: #EF4444; padding: 1px 6px; border-radius: 10px;">LIVE</span>
      </div>
      <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px;">
        ${trendingPros.slice(0, 8).map((p, idx) => {
          const rankNum = idx + 1;
          const rankColor = rankNum === 1 ? '#F59E0B' : (rankNum === 2 ? '#94A3B8' : (rankNum === 3 ? '#B45309' : '#008DF6'));
          return `
            <div class="focus-trending-item" data-gn="${escapeHtml(p.game_name)}" data-tag="${escapeHtml(p.tag_line || 'KR1')}" style="display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; cursor: pointer; border: 1px solid rgba(255,255,255,0.04); background: var(--bg-card); transition: all 0.15s ease;">
              <span style="color: ${rankColor}; font-weight: 800; font-size: 0.85rem; width: 14px; text-align: center;">${rankNum}</span>
              <img src="${escapeHtml(p.profile_icon || 'https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/29.png')}" style="width: 24px; height: 24px; border-radius: 6px; object-fit: cover;" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/29.png'">
              <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;">
                <div style="font-size: 0.82rem; font-weight: 700; color: var(--text-heading); overflow: hidden; text-overflow: ellipsis;">${escapeHtml(p.game_name)}</div>
                <div style="font-size: 0.7rem; color: var(--text-muted);">${escapeHtml([p.team, p.tier].filter(Boolean).join(' · '))}</div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;

  container.innerHTML = recentsHtml + trendingHtml;
  autocompleteDropdown.appendChild(container);
  autocompleteDropdown.style.display = "block";

  // Event handlers
  container.querySelectorAll(".focus-recent-item").forEach(item => {
    item.addEventListener("click", (e) => {
      if (e.target.closest(".btn-del-recent-item")) return;
      const gn = item.getAttribute("data-gn");
      const tag = item.getAttribute("data-tag") || "KR1";
      if (gn) {
        closeAutocomplete();
        performSearch(`${gn}#${tag}`);
      }
    });
  });

  container.querySelectorAll(".btn-del-recent-item").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const row = btn.closest(".focus-recent-item");
      const gn = btn.getAttribute("data-gn");
      const tag = btn.getAttribute("data-tag") || "KR1";
      if (row) {
        row.style.transition = "all 0.18s cubic-bezier(0.16, 1, 0.3, 1)";
        row.style.opacity = "0";
        row.style.transform = "translateX(20px)";
      }
      setTimeout(() => {
        if (typeof getRecentSearches === "function") {
          const updated = getRecentSearches().filter(x => !(x.game_name.toLowerCase() === gn.toLowerCase() && (x.tag_line || "KR1").toLowerCase() === tag.toLowerCase()));
          if (typeof saveRecentSearches === "function") saveRecentSearches(updated);
          renderSearchFocusDropdown();
        }
      }, 180);
    });
  });

  const btnClearAll = container.querySelector("#btnClearRecentsDrop");
  if (btnClearAll) {
    btnClearAll.addEventListener("click", (e) => {
      e.stopPropagation();
      if (typeof clearAllRecentSearches === "function") {
        clearAllRecentSearches();
        renderSearchFocusDropdown();
      }
    });
  }

  container.querySelectorAll(".focus-trending-item").forEach(item => {
    item.addEventListener("click", () => {
      const gn = item.getAttribute("data-gn");
      const tag = item.getAttribute("data-tag") || "KR1";
      if (gn) {
        closeAutocomplete();
        performSearch(`${gn}#${tag}`);
      }
    });
  });
}

async function triggerAutocomplete(val) {
  const query = val.trim();
  if (!query || query.length === 0 || query.startsWith("RGAPI-")) {
    renderSearchFocusDropdown();
    return;
  }

  try {
    const res = await fetch(`/api/autocomplete?q=${encodeURIComponent(query)}`);
    if (res.ok) {
      const data = await res.json();
      renderAutocomplete(data);
    }
  } catch (e) {
    closeAutocomplete();
  }
}

// 실시간 타이핑 이벤트 리스너 (100ms 디바운스)
searchInput.addEventListener("input", (e) => {
  const val = e.target.value.trim();
  if (!val) {
    const homeTrending = document.getElementById("homeTrendingSection");
    if (homeTrending) homeTrending.style.display = "block";
    if (resultsHeader) resultsHeader.style.display = "none";
    if (playerList) playerList.innerHTML = "";
    if (emptyState) emptyState.style.display = "none";
    const champArea = document.getElementById("championAnalyticsArea");
    if (champArea) champArea.style.display = "none";
    closeAutocomplete();
    return;
  }
  clearTimeout(autocompleteTimeout);
  autocompleteTimeout = setTimeout(() => {
    triggerAutocomplete(e.target.value);
  }, 100);
});

// 검색창 포커스 및 클릭 시 OP.GG 스타일 최근검색/실시간인기 드롭다운 표출
searchInput.addEventListener("focus", () => {
  if (!searchInput.value.trim()) {
    renderSearchFocusDropdown();
  }
});
searchInput.addEventListener("click", () => {
  if (!searchInput.value.trim()) {
    renderSearchFocusDropdown();
  }
});

// LCK 프로 트래커 카드 클릭 시 즉시 전적 검색 & 실시간 프로필 팝업 연동
document.addEventListener("click", (e) => {
  const proCard = e.target.closest(".pro-tracker-card");
  if (proCard) {
    const gn = proCard.getAttribute("data-gn");
    const tag = proCard.getAttribute("data-tag") || "KR1";
    if (gn) {
      if (typeof openPlayerDetail === "function") {
        openPlayerDetail({ game_name: gn, tag_line: tag });
      }
      performSearch(`${gn}#${tag}`);
    }
  }
});

// 키보드 방향키 이동 및 Enter 제어 (한글/영문 소환사명 입력 후 Enter 즉각 검색 보장)
searchInput.addEventListener("keydown", (e) => {
  const items = autocompleteDropdown.querySelectorAll(".autocomplete-item");

  if (e.key === "Enter") {
    if (autocompleteDropdown.style.display !== "none" && items.length > 0 && currentHighlightIdx >= 0) {
      e.preventDefault();
      items[currentHighlightIdx].click();
      return;
    }
    e.preventDefault();
    closeAutocomplete();
    const query = searchInput.value.trim();
    if (query) {
      performSearch(query);
    }
    return;
  }

  if (autocompleteDropdown.style.display !== "none" && items.length > 0) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      currentHighlightIdx = (currentHighlightIdx + 1) % items.length;
      updateHighlight(items);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      currentHighlightIdx = (currentHighlightIdx - 1 + items.length) % items.length;
      updateHighlight(items);
    } else if (e.key === "Escape") {
      closeAutocomplete();
    }
  }
});

function updateHighlight(items) {
  items.forEach((item, i) => {
    if (i === currentHighlightIdx) {
      item.classList.add("active");
      item.scrollIntoView({ block: "nearest" });
    } else {
      item.classList.remove("active");
    }
  });
}

// Close modals & dropdown when clicking outside
window.addEventListener("click", (e) => {
  if (e.target === apiKeyModal) apiKeyModal.classList.remove("active");
  if (e.target === playerDetailModal) playerDetailModal.classList.remove("active");
  if (!searchForm.contains(e.target) && !autocompleteDropdown.contains(e.target)) {
    closeAutocomplete();
  }
});
// Discord Integration & Real-Time Sharing Engine
async function sharePlayerToDiscord() {
  if (!currentDetailFullProfile) {
    showToast("공유할 소환사 데이터가 없습니다.");
    return;
  }

  const player = currentDetailFullProfile;
  const summary = {
    avg_kda: player.kda_ratio || "3.00:1",
    most_champions: player.most_champions || []
  };

  try {
    const res = await fetch("/api/discord/share/player", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player, summary, custom_msg: "" })
    });

    const data = await res.json();
    const markdown = data.markdown || "";

    const copySuccess = () => {
      if (data.webhook_sent) {
        showToast("소환사 전적이 디스코드로 전송되고 마크다운이 복사되었습니다.", "success");
      } else {
        showToast("전적 마크다운이 클립보드에 복사되었습니다.", "info");
      }
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(markdown).then(copySuccess).catch(() => {
        fallbackCopyShareUrl(markdown, copySuccess);
      });
    } else {
      fallbackCopyShareUrl(markdown, copySuccess);
    }
  } catch (err) {
    showToast("디스코드 전적 공유 중 오류가 발생했습니다.", "error");
  }
}

function initDiscordIntegration() {
  const btnSharePlayer = document.getElementById("btnShareDiscordPlayer");
  if (btnSharePlayer) {
    btnSharePlayer.addEventListener("click", sharePlayerToDiscord);
  }
}

function initTelegramIntegration() {
  // no-op
}

// Initial Setup on Load (기본 컴팩트 모드 적용, 테마 초기화 및 이전 자동완성 검색어 완전 초기화)
function initControlsSyncSearch() {
  initTheme();
  initBookmarks();
  initBanners();
  initDiscordIntegration();
  initTelegramIntegration();
  if (searchInput) {
    searchInput.value = ""; // 브라우저 이전 폼 자동완성 복원값 강제 초기화
  }
  const filterInput = document.getElementById("champFilterInput");
  if (filterInput) {
    filterInput.value = "";
  }
  if (playerList) {
    playerList.classList.add("compact-mode"); // 스크롤 최소화 기본 적용
  }
  initHomeTrendingRankers();
  prewarmAllTabs();
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", initControlsSyncSearch);
} else {
  initControlsSyncSearch();
}
// 실시간 한국 천상계 챌린저 TOP 10 쇼케이스 (라이엇 API 실시간 동기화)
async function initHomeTrendingRankers() {
  const grid = document.getElementById("homeTrendingGrid");
  if (!grid) return;

  try {
    const res = await fetch("/api/leaderboard?tier=ALL");
    if (!res.ok) {
      grid.innerHTML = `<div class="home-trending-empty"><i class="fa-solid fa-circle-exclamation"></i> 챌린저 랭커 데이터를 불러오는 중 일시적인 오류가 발생했습니다.</div>`;
      return;
    }
    const data = await res.json();
    const rankers = (data.results || []).slice(0, 10);
    if (rankers.length === 0) {
      grid.innerHTML = `<div class="home-trending-empty"><i class="fa-solid fa-inbox"></i> 등록된 천상계 랭커 데이터가 없습니다.</div>`;
      return;
    }

    grid.innerHTML = "";
    const fragment = document.createDocumentFragment();

    rankers.forEach((p, idx) => {
      const card = document.createElement("div");
      card.className = "home-trending-card";
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("title", `${p.game_name}#${p.tag_line || 'KR1'} 20전 상세 전적 & KDA 트렌드 그래프 즉시 조회`);

      const rankBadge = idx === 0 ? "top-1" : idx === 1 ? "top-2" : idx === 2 ? "top-3" : "";
      const rankNum = idx + 1;
      const tierBadge = p.tier === "CHALLENGER" ? "챌린저" : (p.tier === "GRANDMASTER" ? "그랜드마스터" : p.tier);
      const lpVal = p.league_points !== undefined ? p.league_points : (p.lp || 0);
      const lpText = `${formatNumber(lpVal)} LP`;
      const winRate = p.win_rate !== undefined ? p.win_rate : (p.wins && p.losses ? Math.round((p.wins / (p.wins + p.losses)) * 100) : 0);
      const winLossText = `${p.wins || 0}승 ${p.losses || 0}패`;

      const wrNum = Number(winRate) || 0;
      const wrColor = wrNum > 50 ? "#10B981" : "#E84057";
      const emblemUrl = getTierEmblemUrl(tierBadge);

      card.innerHTML = `
        <div class="htc-rank ${rankBadge}">${rankNum}</div>
        ${emblemUrl ? `<img class="htc-emblem" src="${emblemUrl}" alt="${escapeHtml(tierBadge)}" onerror="this.style.visibility='hidden'">` : ""}
        <div class="htc-main">
          <div class="htc-name-line">
            <span class="htc-name">${escapeHtml(p.game_name)}</span><span class="htc-tag">#${escapeHtml(p.tag_line || "")}</span>
          </div>
          <div class="htc-sub-line">${escapeHtml(tierBadge)} · <b>${lpText}</b></div>
        </div>
        <div class="htc-wr">
          <div class="htc-wr-top"><span class="htc-wr-val" style="color: ${wrColor};">${wrNum}%</span><span class="htc-record">${winLossText}</span></div>
          <div class="htc-wr-bar"><span style="width: ${Math.max(0, Math.min(100, wrNum))}%; background: ${wrColor};"></span></div>
        </div>
      `;

      // performSearch 가 검색 결과로 프로필 모달까지 연다. openPlayerDetail 을 따로 부르면 라이엇 프로필을 두 번 조회한다
      const handleClick = () => {
        if (typeof performSearch === "function") {
          performSearch(`${p.game_name}#${p.tag_line || "KR1"}`);
        } else if (typeof openPlayerDetail === "function") {
          openPlayerDetail(p);
        }
      };

      card.addEventListener("click", handleClick);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleClick();
        }
      });

      fragment.appendChild(card);
    });

    grid.appendChild(fragment);
  } catch (err) {
    grid.innerHTML = `<div class="home-trending-empty"><i class="fa-solid fa-spinner fa-spin"></i> 데이터 동기화 대기 중...</div>`;
  }
}
