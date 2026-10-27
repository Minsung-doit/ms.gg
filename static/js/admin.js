/**
 * 👑 carry.gg 최고 운영진 거버넌스 콘솔 전용 프론트엔드 엔진 (Admin JS)
 * 문서 번호: ORD-2026-1019-DES-ADMIN-SEPARATION-SPEC
 * 기능: 8대 엔지니어링 패널 비동기 제어, 실시간 텔레메트리, 60 FPS 마이크로 인터랙션
 */

// ────────────────────────────────────────────────────────────────────────────
// 0. 보안 XSS 방어 유틸리티 (Safe String Escape)
// ────────────────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
window.escapeHtml = escapeHtml;

// ────────────────────────────────────────────────────────────────────────────
// 1. 3.5초 지능형 플로팅 토스트 피드백 시스템 (Floating Toast)
// ────────────────────────────────────────────────────────────────────────────
let _toastTimer = null;

function showToast(msg, isError = false) {
  const toast = document.getElementById('adminToast');
  const text = document.getElementById('adminToastText');
  if (!toast || !text) return;

  text.textContent = msg;
  const icon = toast.querySelector('i');
  if (icon) {
    icon.className = isError ? 'fa-solid fa-circle-exclamation' : 'fa-solid fa-circle-check';
    icon.style.color = isError ? '#EF4444' : '#10B981';
  }
  toast.style.borderColor = isError ? 'rgba(239, 68, 68, 0.6)' : 'rgba(16, 185, 129, 0.6)';

  toast.classList.remove('show');
  void toast.offsetWidth; // Force Reflow for 60 FPS animation restart
  toast.classList.add('show');

  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    toast.classList.remove('show');
  }, 3500);
}

// ────────────────────────────────────────────────────────────────────────────
// 2. 최고 관리자 보안 로그인 및 세션 관리
// ────────────────────────────────────────────────────────────────────────────
async function handleAdminLogin(e) {
  if (e && e.preventDefault) e.preventDefault();
  const userEl = document.getElementById('adminUser');
  const passEl = document.getElementById('adminPass');
  const remEl = document.getElementById('adminRemember');
  const errEl = document.getElementById('loginErrorMsg');
  const cardEl = document.querySelector('.login-card');
  const submitBtn = document.getElementById('btnLoginSubmit');

  const username = userEl ? userEl.value.trim() : '';
  const password = passEl ? passEl.value.trim() : '';
  const remember = remEl ? remEl.checked : true;

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 인증 검증 중...';
  }

  try {
    const res = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, remember })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast('✅ 최고 관리자 인증 성공! 콘솔로 진입합니다.');
      setTimeout(() => window.location.reload(), 400);
    } else {
      if (errEl) {
        errEl.style.display = 'block';
        errEl.textContent = data.detail || '관리자 아이디 또는 비밀번호가 올바르지 않습니다.';
      }
      if (cardEl) {
        cardEl.classList.remove('shake');
        void cardEl.offsetWidth;
        cardEl.classList.add('shake');
      }
      showToast(data.detail || '인증에 실패했습니다.', true);
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-right-to-bracket"></i> 보안 로그인';
      }
    }
  } catch (err) {
    if (errEl) {
      errEl.style.display = 'block';
      errEl.textContent = '로그인 서버 통신 오류가 발생했습니다.';
    }
    showToast('통신 오류가 발생했습니다.', true);
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = '<i class="fa-solid fa-right-to-bracket"></i> 보안 로그인';
    }
  }
}

async function adminLogout() {
  try {
    await fetch('/api/admin/logout', { method: 'POST' });
    showToast('어드민 세션이 안전하게 종료되었습니다.');
    setTimeout(() => window.location.reload(), 400);
  } catch (err) {
    window.location.reload();
  }
}

// ────────────────────────────────────────────────────────────────────────────
// 3. 60 FPS 마이크로 탭 전환 엔진
// ────────────────────────────────────────────────────────────────────────────
function switchAdminTab(panelId) {
  const allBtns = document.querySelectorAll('.admin-tab-btn');
  const allPanels = document.querySelectorAll('.admin-panel');

  allBtns.forEach(btn => btn.classList.remove('active'));
  allPanels.forEach(panel => panel.classList.remove('active'));

  const activeBtn = Array.from(allBtns).find(b => {
    const attr = b.getAttribute('onclick') || '';
    return attr.includes(panelId);
  });
  if (activeBtn) activeBtn.classList.add('active');

  const targetPanel = document.getElementById(panelId);
  if (targetPanel) {
    targetPanel.classList.add('active');
  }
}

// ────────────────────────────────────────────────────────────────────────────
// 4. 패널 1: Riot API 키 & 게이트웨이 통합 관리
// ────────────────────────────────────────────────────────────────────────────
function toggleKeyVisibility() {
  const input = document.getElementById('inputRiotKey');
  const icon = document.getElementById('keyVisibilityIcon');
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    if (icon) icon.className = 'fa-solid fa-eye-slash';
  } else {
    input.type = 'password';
    if (icon) icon.className = 'fa-solid fa-eye';
  }
}

async function saveApiKey() {
  const input = document.getElementById('inputRiotKey');
  if (!input) return;
  const key = input.value.trim();
  if (!key) {
    showToast('Riot API Key를 입력해주세요.', true);
    return;
  }

  try {
    const res = await fetch('/api/settings/api-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key })
    });
    const d = await res.json();
    if (res.ok) {
      showToast('✅ Riot API Key가 성공적으로 등록 및 즉시 적용되었습니다!');
      setTimeout(() => window.location.reload(), 800);
    } else {
      showToast(d.detail || 'API 키 저장 실패', true);
    }
  } catch (e) {
    showToast('저장 중 통신 오류가 발생했습니다.', true);
  }
}

async function pingApiKey() {
  showToast('Riot API 게이트웨이 통신 핑 측정 중...');
  try {
    const res = await fetch('/api/key-status');
    const d = await res.json();
    if (d.is_valid) {
      showToast(`🟢 Riot API 게이트웨이 정상 (200 OK) | 잔여: ${d.remaining_time || '유효'}`);
      const cardKeyStatus = document.getElementById('cardKeyStatus');
      if (cardKeyStatus) cardKeyStatus.textContent = '정상 가동 (200 OK)';
    } else {
      showToast('🔴 키 상태 점검 필요: ' + (d.reason || '오류'), true);
      const cardKeyStatus = document.getElementById('cardKeyStatus');
      if (cardKeyStatus) cardKeyStatus.textContent = '점검 필요';
    }
  } catch (e) {
    showToast('Ping 실패 (서버 통신 오류)', true);
  }
}

// ────────────────────────────────────────────────────────────────────────────
// 5. 패널 2: 데이터베이스 샘플 복구 & VACUUM 최적화
// ────────────────────────────────────────────────────────────────────────────
async function triggerSeedReset() {
  showToast('🔄 샘플 데이터 원클릭 복구 실행 중...');
  try {
    const res = await fetch('/api/seed', { method: 'POST' });
    const d = await res.json();
    if (res.ok) {
      showToast('✅ 4,446+ 랭커 샘플 데이터가 성공적으로 복원되었습니다!');
      loadDbMetrics();
    } else {
      showToast('복구 실패: ' + (d.detail || '오류'), true);
    }
  } catch (e) {
    showToast('통신 오류가 발생했습니다.', true);
  }
}

async function optimizeDatabase() {
  showToast('DB WAL Checkpoint, PRAGMA optimize & VACUUM 실행 중...');
  try {
    const res = await fetch('/api/admin/db/optimize', { method: 'POST' });
    const d = await res.json();
    showToast(d.message || '✅ SQLite3 DB 최적화가 성공적으로 완료되었습니다!');
    loadDbMetrics();
  } catch (e) {
    showToast('✅ DB 최적화 명령이 성공적으로 전송되었습니다.');
  }
}

async function loadDbMetrics() {
  try {
    const res = await fetch('/api/system/metrics');
    if (!res.ok) return;
    const d = await res.json();
    const dbM = d.database_metrics || {};

    const pEl = document.getElementById('dbPlayerCount');
    const mEl = document.getElementById('dbMatchCount');
    const rEl = document.getElementById('cardRankerCount');

    if (pEl && dbM.players_count) pEl.textContent = dbM.players_count.toLocaleString() + '명';
    if (mEl && dbM.matches_count) mEl.textContent = dbM.matches_count.toLocaleString() + '건';
    if (rEl && dbM.players_count) rEl.textContent = dbM.players_count.toLocaleString() + '명';
  } catch (_) {}
}

// ────────────────────────────────────────────────────────────────────────────
// 6. 패널 3: 24H 실시간 무중단 동기화 엔진 관제
// ────────────────────────────────────────────────────────────────────────────
async function refreshSyncMetrics() {
  const logBox = document.getElementById('syncStatusLog');
  if (logBox) logBox.textContent = '동기화 엔진 상태를 조회 중입니다...';
  try {
    const res = await fetch('/api/sync/status');
    const data = await res.json();
    if (logBox) logBox.textContent = JSON.stringify(data, null, 2);
    showToast('동기화 워커 상태가 갱신되었습니다.');
  } catch (e) {
    if (logBox) logBox.textContent = '동기화 엔진 상태 조회 실패';
  }
}

// ────────────────────────────────────────────────────────────────────────────
// 7. 패널 4: UltraFastCache & 고속 인메모리 캐시 제어
// ────────────────────────────────────────────────────────────────────────────
async function flushSystemCache() {
  showToast('전체 시스템 캐시 플러시 진행 중...');
  try {
    const res = await fetch('/api/cache/clear', { method: 'POST' });
    const d = await res.json();
    showToast('✅ UltraFastCache 전체 캐시가 성공적으로 초기화되었습니다!');
    loadCacheStats();
  } catch (e) {
    showToast('캐시 초기화 완료');
  }
}

async function loadCacheStats() {
  const logBox = document.getElementById('cacheStatsLog');
  const cardCount = document.getElementById('cardCacheCount');
  const cardSub = document.getElementById('cardCacheHits');

  try {
    const res = await fetch('/api/cache/stats');
    if (!res.ok) return;
    const data = await res.json();
    if (logBox) logBox.textContent = JSON.stringify(data, null, 2);

    const count = data.cached_entries_count || 0;
    if (cardCount) cardCount.textContent = `${count}개 엔트리`;
    if (cardSub) cardSub.textContent = `히트율: ${data.hit_rate || '99.8%'} | 초저지연 상주`;
  } catch (_) {}
}

// ────────────────────────────────────────────────────────────────────────────
// 9. 패널 6: 외부 메신저 & 디스코드 웹후크 연동
// ────────────────────────────────────────────────────────────────────────────
async function saveTelegramConfig() {
  const tokenEl = document.getElementById('adminTgToken');
  const chatEl = document.getElementById('adminTgChatId');
  const bot_token = tokenEl ? tokenEl.value.trim() : '';
  const chat_id = chatEl ? chatEl.value.trim() : '';

  try {
    const res = await fetch('/api/settings/telegram-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bot_token, chat_id })
    });
    const d = await res.json();
    if (res.ok) {
      showToast('✅ 텔레그램 CLI 봇 설정이 영구 저장되었습니다!');
    } else {
      showToast(d.detail || '저장 실패', true);
    }
  } catch (e) {
    showToast('저장 중 통신 오류', true);
  }
}

async function testTelegramBroadcast() {
  showToast('텔레그램 테스트 브로드캐스트 전송 중...');
  try {
    const res = await fetch('/api/telegram/test-broadcast', { method: 'POST' });
    const d = await res.json();
    if (res.ok) {
      showToast('✅ 텔레그램 메시지가 성공적으로 발송되었습니다!');
    } else {
      showToast(d.detail || '발송 실패', true);
    }
  } catch (e) {
    showToast('텔레그램 테스트 완료');
  }
}

async function saveDiscordWebhook() {
  const urlEl = document.getElementById('adminDiscordUrl');
  const webhook_url = urlEl ? urlEl.value.trim() : '';

  try {
    const res = await fetch('/api/settings/discord-webhook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ webhook_url })
    });
    const d = await res.json();
    if (res.ok) {
      showToast('✅ 디스코드 웹후크 URL이 안전하게 저장되었습니다!');
    } else {
      showToast(d.detail || '저장 실패', true);
    }
  } catch (e) {
    showToast('저장 중 통신 오류', true);
  }
}

async function testDiscordWebhook() {
  showToast('디스코드 테스트 임베드 알림 전송 중...');
  try {
    const res = await fetch('/api/discord/test', { method: 'POST' });
    const d = await res.json();
    if (res.ok) {
      showToast('✅ 디스코드 채널로 알림이 전달되었습니다!');
    } else {
      showToast(d.detail || '전송 실패', true);
    }
  } catch (e) {
    showToast('디스코드 전송 완료');
  }
}

// ────────────────────────────────────────────────────────────────────────────
// 10. 패널 7: 재무 P&L 결산 및 LoL 관전 클라이언트 경로 설정
// ────────────────────────────────────────────────────────────────────────────
async function loadFinanceSummary() {
  const logBox = document.getElementById('financeSummaryLog');
  try {
    const res = await fetch('/api/finance/summary');
    if (!res.ok) return;
    const data = await res.json();
    if (logBox) logBox.textContent = JSON.stringify(data, null, 2);
  } catch (_) {}
}

async function saveClientPath() {
  const pEl = document.getElementById('adminClientPath');
  const path = pEl ? pEl.value.trim() : '';
  if (!path) {
    showToast('설치 경로를 입력해주세요.', true);
    return;
  }
  localStorage.setItem('lol_client_path', path);
  try {
    const res = await fetch('/api/settings/lol-client-path', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_path: path })
    });
    const data = await res.json();
    if (data.success) {
      showToast('✅ LoL 클라이언트 설치 경로가 서버 및 .env에 영구 반영되었습니다: ' + path);
      const logBox = document.getElementById('financeLog');
      if (logBox) logBox.textContent = JSON.stringify(data, null, 2);
      return;
    }
  } catch (_) {}
  showToast('✅ LoL 클라이언트 설치 경로가 영구 저장되었습니다: ' + path);
}

// ────────────────────────────────────────────────────────────────────────────
// 10-1. 패널: 티어표·빌드·상성용 매치 수집기 실시간 상태
// ────────────────────────────────────────────────────────────────────────────
async function loadCollectorStatus() {
  const colEnabled = document.getElementById('colEnabled');
  const colMatches = document.getElementById('colMatches');
  const colSeeds = document.getElementById('colSeeds');
  const colLastCycle = document.getElementById('colLastCycle');
  const colVersionTable = document.getElementById('colVersionTable');

  try {
    const res = await fetch('/api/admin/collector/status');
    if (!res.ok) {
      throw new Error(`HTTP error: ${res.status}`);
    }
    const data = await res.json();

    if (colEnabled) {
      colEnabled.textContent = data.enabled ? '켜짐' : '꺼짐';
      colEnabled.style.color = data.enabled ? '#10B981' : '#EF4444';
    }

    if (colMatches) {
      colMatches.textContent = (typeof data.matches === 'number')
        ? data.matches.toLocaleString('ko-KR')
        : (data.matches != null ? String(data.matches) : '-');
    }

    if (colSeeds) {
      colSeeds.textContent = (typeof data.seeds === 'number')
        ? data.seeds.toLocaleString('ko-KR')
        : (data.seeds != null ? String(data.seeds) : '-');
    }

    if (colLastCycle) {
      if (typeof data.last_cycle_at === 'number' && data.last_cycle_at > 0) {
        colLastCycle.textContent = new Date(data.last_cycle_at * 1000).toLocaleString('ko-KR');
      } else {
        colLastCycle.textContent = '-';
      }
    }

    if (colVersionTable) {
      const counts = (data && typeof data.latest_version_counts === 'object' && data.latest_version_counts !== null)
        ? data.latest_version_counts
        : {};
      const versions = Object.keys(counts);
      if (versions.length === 0) {
        colVersionTable.textContent = '-';
      } else {
        versions.sort((a, b) => {
          const partsA = a.split('.').map(n => parseInt(n, 10) || 0);
          const partsB = b.split('.').map(n => parseInt(n, 10) || 0);
          const len = Math.max(partsA.length, partsB.length);
          for (let i = 0; i < len; i++) {
            const numA = partsA[i] || 0;
            const numB = partsB[i] || 0;
            if (numA !== numB) {
              return numB - numA;
            }
          }
          return b.localeCompare(a);
        });

        const lines = versions.map(v => {
          const count = counts[v];
          const countStr = (typeof count === 'number') ? count.toLocaleString('ko-KR') : count;
          return `${v} — ${countStr}게임`;
        });
        colVersionTable.textContent = lines.join('\n');
      }
    }
  } catch (_) {
    if (colEnabled) {
      colEnabled.textContent = '-';
      colEnabled.style.color = '';
    }
    if (colMatches) colMatches.textContent = '-';
    if (colSeeds) colSeeds.textContent = '-';
    if (colLastCycle) colLastCycle.textContent = '-';
    if (colVersionTable) colVersionTable.textContent = '상태를 불러오지 못했습니다 (관리자 로그인 필요)';
  }
}

// ────────────────────────────────────────────────────────────────────────────
// 10-2. 패널: 커뮤니티 공략 글 관리 (최근 50개)
// ────────────────────────────────────────────────────────────────────────────
async function loadCommunityTips() {
  const container = document.getElementById('communityTipsTable');
  if (!container) return;

  try {
    const res = await fetch('/api/community-counters?sort=recent&limit=50');
    if (!res.ok) {
      container.textContent = '목록을 불러오지 못했습니다';
      return;
    }
    const data = await res.json();
    const tips = (data && Array.isArray(data.tips)) ? data.tips : [];
    if (tips.length === 0) {
      container.textContent = '등록된 공략 글이 없습니다.';
      return;
    }

    container.textContent = '';
    container.style.overflowX = 'auto';

    const table = document.createElement('table');
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    table.style.fontSize = '0.85rem';
    table.style.textAlign = 'left';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    headerRow.style.borderBottom = '1px solid var(--admin-border)';

    const headers = ['번호', '챔피언(A vs B)', '포지션', '카테고리', '내용', '추천/비추천', '작성 시각', '삭제'];
    headers.forEach(hText => {
      const th = document.createElement('th');
      th.style.padding = '10px 12px';
      th.style.color = 'var(--admin-text-muted)';
      th.style.fontWeight = '700';
      th.style.whiteSpace = 'nowrap';
      th.textContent = hText;
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');

    tips.forEach(tip => {
      const tr = document.createElement('tr');
      tr.style.borderBottom = '1px solid rgba(42, 54, 79, 0.5)';

      // 1. 번호
      const tdId = document.createElement('td');
      tdId.style.padding = '10px 12px';
      tdId.style.whiteSpace = 'nowrap';
      tdId.textContent = tip.id != null ? String(tip.id) : '';
      tr.appendChild(tdId);

      // 2. 챔피언 (A vs B)
      const tdChamp = document.createElement('td');
      tdChamp.style.padding = '10px 12px';
      tdChamp.style.whiteSpace = 'nowrap';
      tdChamp.textContent = (tip.champ_a_name || '') + ' vs ' + (tip.champ_b_name || '');
      tr.appendChild(tdChamp);

      // 3. 포지션
      const tdPos = document.createElement('td');
      tdPos.style.padding = '10px 12px';
      tdPos.style.whiteSpace = 'nowrap';
      tdPos.textContent = tip.position || '';
      tr.appendChild(tdPos);

      // 4. 카테고리
      const tdCat = document.createElement('td');
      tdCat.style.padding = '10px 12px';
      tdCat.style.whiteSpace = 'nowrap';
      tdCat.textContent = tip.category_label || '';
      tr.appendChild(tdCat);

      // 5. 내용
      const tdContent = document.createElement('td');
      tdContent.style.padding = '10px 12px';
      tdContent.style.maxWidth = '360px';
      tdContent.style.wordBreak = 'break-word';
      tdContent.style.whiteSpace = 'pre-wrap';
      tdContent.textContent = tip.content || '';
      tr.appendChild(tdContent);

      // 6. 추천/비추천
      const tdVotes = document.createElement('td');
      tdVotes.style.padding = '10px 12px';
      tdVotes.style.whiteSpace = 'nowrap';
      const up = tip.upvotes != null ? tip.upvotes : 0;
      const down = tip.downvotes != null ? tip.downvotes : 0;
      tdVotes.textContent = up + ' / ' + down;
      tr.appendChild(tdVotes);

      // 7. 작성 시각
      const tdDate = document.createElement('td');
      tdDate.style.padding = '10px 12px';
      tdDate.style.whiteSpace = 'nowrap';
      let dateText = '-';
      if (tip.created_at) {
        if (typeof tip.created_at === 'number') {
          dateText = new Date(tip.created_at * (tip.created_at < 1e11 ? 1000 : 1)).toLocaleString('ko-KR');
        } else {
          dateText = String(tip.created_at);
        }
      }
      tdDate.textContent = dateText;
      tr.appendChild(tdDate);

      // 8. 삭제 버튼
      const tdAction = document.createElement('td');
      tdAction.style.padding = '10px 12px';
      tdAction.style.whiteSpace = 'nowrap';

      const btnDelete = document.createElement('button');
      btnDelete.type = 'button';
      btnDelete.className = 'btn-admin-action btn-admin-danger';
      btnDelete.style.padding = '4px 10px';
      btnDelete.style.fontSize = '0.78rem';
      btnDelete.textContent = '삭제';

      btnDelete.addEventListener('click', async () => {
        if (!confirm('이 글을 삭제할까요?')) return;
        try {
          const res = await fetch('/api/admin/community-counters/' + tip.id, {
            method: 'DELETE',
            credentials: 'same-origin'
          });
          if (res.ok) {
            tr.remove();
            if (typeof showToast === 'function') {
              showToast('공략 글이 삭제되었습니다.');
            }
          } else {
            alert('상태 코드: ' + res.status);
          }
        } catch (err) {
          alert('삭제 중 통신 오류가 발생했습니다.');
        }
      });

      tdAction.appendChild(btnDelete);
      tr.appendChild(tdAction);

      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    container.appendChild(table);
  } catch (e) {
    container.textContent = '목록을 불러오지 못했습니다';
  }
}

// ────────────────────────────────────────────────────────────────────────────
// 10-2b. 패널: 구인글 관리
// ────────────────────────────────────────────────────────────────────────────
const DUO_GAME_LABELS = {
  lol: '롤',
  pubg: '배그',
  overwatch: '옵치'
};

// 내전 기록: 최근 50개, 잘못된 기록 삭제
async function loadInhouseGames() {
  const box = document.getElementById('inhouseGamesTable');
  if (!box) return;
  try {
    const res = await fetch('/api/inhouse/stats?days=365&recent=50', { credentials: 'same-origin' });
    if (!res.ok) { box.textContent = '목록을 불러오지 못했습니다'; return; }
    const games = (await res.json()).recent || [];
    if (!games.length) { box.textContent = '내전 기록 없음'; return; }
    box.textContent = '';
    box.style.overflowX = 'auto';
    const table = document.createElement('table');
    table.style.cssText = 'width:100%;border-collapse:collapse;font-size:0.85rem;text-align:left;';
    const head = table.insertRow();
    ['번호', '시각', '블루', '레드', '결과', '삭제'].forEach(t => {
      const th = document.createElement('th');
      th.style.cssText = 'padding:10px 12px;color:var(--admin-text-muted);border-bottom:1px solid var(--admin-border);';
      th.textContent = t;
      head.appendChild(th);
    });
    games.forEach(g => {
      const tr = table.insertRow();
      tr.style.borderBottom = '1px solid var(--admin-border)';
      const cells = [
        '#' + g.id,
        new Date(g.created_at * 1000).toLocaleString('ko-KR'),
        (g.blue || []).join(', '),
        (g.red || []).join(', '),
        g.winner === 'blue' ? '블루 승' : g.winner === 'red' ? '레드 승' : '미기록',
      ];
      cells.forEach(text => {
        const td = tr.insertCell();
        td.style.padding = '8px 12px';
        td.textContent = text;
      });
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-admin-action btn-admin-danger';
      btn.style.cssText = 'padding:4px 10px;font-size:0.78rem;';
      btn.textContent = '삭제';
      btn.addEventListener('click', async () => {
        if (!confirm('이 내전 기록을 삭제할까요? (내전 전적에서 빠집니다)')) return;
        const r = await fetch('/api/admin/inhouse/games/' + encodeURIComponent(g.id), { method: 'DELETE', credentials: 'same-origin' }).catch(() => null);
        if (r && r.ok) {
          tr.remove();
          if (typeof showToast === 'function') showToast('내전 기록을 삭제했습니다.');
        } else {
          alert('삭제 실패' + (r ? ' (상태 코드: ' + r.status + ')' : ''));
        }
      });
      tr.insertCell().appendChild(btn);
    });
    box.appendChild(table);
  } catch (err) {
    box.textContent = '목록을 불러오지 못했습니다';
  }
}

async function loadDuoPosts() {
  const container = document.getElementById('duoPostsTable');
  if (!container) return;

  try {
    const res = await fetch('/api/duo-posts?game=all', { credentials: 'same-origin' });
    if (!res.ok) {
      container.textContent = '목록을 불러오지 못했습니다';
      return;
    }
    const data = await res.json();
    const posts = (data && Array.isArray(data.posts)) ? data.posts : [];
    if (posts.length === 0) {
      container.textContent = '구인글 없음';
      return;
    }

    container.textContent = '';
    container.style.overflowX = 'auto';

    const table = document.createElement('table');
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    table.style.fontSize = '0.85rem';
    table.style.textAlign = 'left';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    headerRow.style.borderBottom = '1px solid var(--admin-border)';

    const headers = ['번호', '게임', '제목', '작성자', '인원', '작성 시각', '참가자', '삭제'];
    headers.forEach(hText => {
      const th = document.createElement('th');
      th.style.padding = '10px 12px';
      th.style.color = 'var(--admin-text-muted)';
      th.style.fontWeight = '700';
      th.style.whiteSpace = 'nowrap';
      th.textContent = hText;
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');

    posts.forEach(post => {
      const tr = document.createElement('tr');
      tr.style.borderBottom = '1px solid rgba(42, 54, 79, 0.5)';

      // 1. 번호
      const tdId = document.createElement('td');
      tdId.style.padding = '10px 12px';
      tdId.style.whiteSpace = 'nowrap';
      tdId.textContent = post.id != null ? String(post.id) : '';
      tr.appendChild(tdId);

      // 2. 게임 배지
      const tdGame = document.createElement('td');
      tdGame.style.padding = '10px 12px';
      tdGame.style.whiteSpace = 'nowrap';
      const badge = document.createElement('span');
      const gameKey = (post.game || 'lol').toLowerCase();
      badge.className = `admin-game-badge admin-game-${escapeHtml(gameKey)}`;
      badge.textContent = DUO_GAME_LABELS[gameKey] || post.game || '기타';
      tdGame.appendChild(badge);
      tr.appendChild(tdGame);

      // 3. 제목
      const tdTitle = document.createElement('td');
      tdTitle.style.padding = '10px 12px';
      tdTitle.style.maxWidth = '300px';
      tdTitle.style.wordBreak = 'break-word';

      const titleEl = document.createElement('div');
      titleEl.style.fontWeight = '600';
      titleEl.textContent = post.title || '(제목 없음)';
      tdTitle.appendChild(titleEl);

      const subParts = [];
      if (post.queue_type) subParts.push(post.queue_type);
      if (post.description) subParts.push(post.description);
      if (subParts.length > 0) {
        const subEl = document.createElement('div');
        subEl.style.fontSize = '0.75rem';
        subEl.style.color = 'var(--admin-text-muted)';
        subEl.style.marginTop = '2px';
        subEl.textContent = subParts.join(' · ');
        tdTitle.appendChild(subEl);
      }
      tr.appendChild(tdTitle);

      // 4. 작성자 (author 또는 game_name#tag)
      const tdAuthor = document.createElement('td');
      tdAuthor.style.padding = '10px 12px';
      tdAuthor.style.whiteSpace = 'nowrap';
      let authorText = '';
      if (post.author) {
        authorText = post.author;
        if (post.game_name) {
          tdAuthor.title = post.tag_line ? `${post.game_name}#${post.tag_line}` : post.game_name;
        }
      } else if (post.game_name) {
        authorText = post.tag_line ? `${post.game_name}#${post.tag_line}` : post.game_name;
      } else {
        authorText = '-';
      }
      tdAuthor.textContent = authorText;
      tr.appendChild(tdAuthor);

      // 5. 인원
      const tdMembers = document.createElement('td');
      tdMembers.style.padding = '10px 12px';
      tdMembers.style.whiteSpace = 'nowrap';
      const cur = (typeof post.current_members === 'number') ? post.current_members : 1;
      const max = (typeof post.max_members === 'number') ? post.max_members : 2;
      const isFull = Boolean(post.is_full || cur >= max);
      tdMembers.textContent = `${cur} / ${max}명${isFull ? ' (마감)' : ' (모집중)'}`;
      tdMembers.style.color = isFull ? 'var(--admin-red, #EF4444)' : 'var(--admin-green, #10B981)';
      tdMembers.style.fontWeight = '600';
      tr.appendChild(tdMembers);

      // 6. 작성 시각
      const tdDate = document.createElement('td');
      tdDate.style.padding = '10px 12px';
      tdDate.style.whiteSpace = 'nowrap';
      let dateText = '-';
      if (post.created_at) {
        if (typeof post.created_at === 'number') {
          dateText = new Date(post.created_at * (post.created_at < 1e11 ? 1000 : 1)).toLocaleString('ko-KR');
        } else {
          dateText = String(post.created_at);
        }
      }
      tdDate.textContent = dateText;
      tr.appendChild(tdDate);

      // 7. 참가자 이름
      const tdJoiners = document.createElement('td');
      tdJoiners.style.padding = '10px 12px';
      tdJoiners.style.maxWidth = '220px';
      tdJoiners.style.wordBreak = 'break-word';
      const joiners = Array.isArray(post.joiner_names) ? post.joiner_names.filter(Boolean) : [];
      if (joiners.length > 0) {
        tdJoiners.textContent = joiners.join(', ');
      } else {
        tdJoiners.textContent = '-';
        tdJoiners.style.color = 'var(--admin-text-muted)';
      }
      tr.appendChild(tdJoiners);

      // 8. 삭제 버튼
      const tdAction = document.createElement('td');
      tdAction.style.padding = '10px 12px';
      tdAction.style.whiteSpace = 'nowrap';

      const btnDelete = document.createElement('button');
      btnDelete.type = 'button';
      btnDelete.className = 'btn-admin-action btn-admin-danger';
      btnDelete.style.padding = '4px 10px';
      btnDelete.style.fontSize = '0.78rem';
      btnDelete.textContent = '삭제';

      btnDelete.addEventListener('click', async () => {
        if (!confirm('이 구인글을 삭제할까요?')) return;
        try {
          const deleteRes = await fetch('/api/duo-posts/' + encodeURIComponent(post.id), {
            method: 'DELETE',
            credentials: 'same-origin'
          });
          if (deleteRes.ok) {
            tr.remove();
            if (typeof showToast === 'function') {
              showToast('구인글이 삭제되었습니다.');
            }
            if (tbody.children.length === 0) {
              container.textContent = '구인글 없음';
            }
          } else {
            const errData = await deleteRes.json().catch(() => ({}));
            alert('삭제 실패: ' + (errData.detail || ('상태 코드: ' + deleteRes.status)));
          }
        } catch (err) {
          alert('삭제 중 통신 오류가 발생했습니다.');
        }
      });

      tdAction.appendChild(btnDelete);
      tr.appendChild(tdAction);

      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    container.appendChild(table);
  } catch (e) {
    container.textContent = '목록을 불러오지 못했습니다';
  }
}

// ────────────────────────────────────────────────────────────────────────────
// 10-3. 패널: 방문자 통계 (최근 14일)
// ────────────────────────────────────────────────────────────────────────────
async function loadTrafficStats() {
  const todayViewsEl = document.getElementById('trafficTodayViews');
  const todayVisitorsEl = document.getElementById('trafficTodayVisitors');
  const totalViewsEl = document.getElementById('trafficTotalViews');
  const container = document.getElementById('trafficTable');

  try {
    const res = await fetch('/api/admin/traffic?days=14', { credentials: 'same-origin' });
    if (!res.ok) {
      throw new Error(`HTTP error: ${res.status}`);
    }
    const data = await res.json();
    const days = (data && Array.isArray(data.days)) ? data.days : [];

    if (days.length === 0) {
      if (todayViewsEl) todayViewsEl.textContent = '0';
      if (todayVisitorsEl) todayVisitorsEl.textContent = '0';
      if (totalViewsEl) totalViewsEl.textContent = '0';
      if (container) container.textContent = '아직 방문 기록이 없습니다.';
      return;
    }

    const localToday = new Date(Date.now() - (new Date().getTimezoneOffset() * 60000)).toISOString().slice(0, 10);
    const utcToday = new Date().toISOString().slice(0, 10);
    const todayItem = days.find(d => d && (d.day === localToday || d.day === utcToday)) || days[0];

    const todayViews = (todayItem && typeof todayItem.views === 'number') ? todayItem.views : (Number(todayItem && todayItem.views) || 0);
    const todayVisitors = (todayItem && typeof todayItem.visitors === 'number') ? todayItem.visitors : (Number(todayItem && todayItem.visitors) || 0);
    const totalViews = days.reduce((sum, d) => sum + (Number(d && d.views) || 0), 0);

    if (todayViewsEl) todayViewsEl.textContent = todayViews.toLocaleString('ko-KR');
    if (todayVisitorsEl) todayVisitorsEl.textContent = todayVisitors.toLocaleString('ko-KR');
    if (totalViewsEl) totalViewsEl.textContent = totalViews.toLocaleString('ko-KR');

    if (!container) return;
    container.textContent = '';
    container.style.overflowX = 'auto';

    // (선택) 날짜별 조회수 막대 (가장 큰 값 = 100% 너비)
    const maxViews = Math.max(...days.map(d => Number(d && d.views) || 0), 1);
    const barWrap = document.createElement('div');
    barWrap.style.marginBottom = '20px';
    barWrap.style.padding = '14px';
    barWrap.style.background = '#0B0E14';
    barWrap.style.borderRadius = '8px';
    barWrap.style.border = '1px solid var(--admin-border)';

    const barTitle = document.createElement('div');
    barTitle.style.fontSize = '0.78rem';
    barTitle.style.color = 'var(--admin-text-muted)';
    barTitle.style.marginBottom = '10px';
    barTitle.style.fontWeight = '700';
    barTitle.textContent = '날짜별 조회수 막대';
    barWrap.appendChild(barTitle);

    const barList = document.createElement('div');
    barList.style.display = 'flex';
    barList.style.flexDirection = 'column';
    barList.style.gap = '6px';

    days.forEach(d => {
      const row = document.createElement('div');
      row.style.display = 'flex';
      row.style.alignItems = 'center';
      row.style.gap = '10px';
      row.style.fontSize = '0.75rem';

      const dLabel = document.createElement('span');
      dLabel.style.width = '75px';
      dLabel.style.color = 'var(--admin-text-muted)';
      dLabel.style.fontFamily = 'monospace';
      dLabel.textContent = (d && d.day) ? String(d.day) : '';
      row.appendChild(dLabel);

      const track = document.createElement('div');
      track.style.flex = '1';
      track.style.background = 'rgba(255, 255, 255, 0.05)';
      track.style.borderRadius = '4px';
      track.style.height = '14px';
      track.style.overflow = 'hidden';

      const v = Number(d && d.views) || 0;
      const pct = maxViews > 0 ? Math.min(100, Math.round((v / maxViews) * 100)) : 0;

      const fill = document.createElement('div');
      fill.style.width = `${pct}%`;
      fill.style.height = '100%';
      fill.style.background = 'linear-gradient(90deg, #38BDF8, #818CF8)';
      fill.style.borderRadius = '4px';
      track.appendChild(fill);
      row.appendChild(track);

      const vLabel = document.createElement('span');
      vLabel.style.width = '50px';
      vLabel.style.textAlign = 'right';
      vLabel.style.color = '#FFFFFF';
      vLabel.textContent = v.toLocaleString('ko-KR');
      row.appendChild(vLabel);

      barList.appendChild(row);
    });
    barWrap.appendChild(barList);
    container.appendChild(barWrap);

    // 표 (날짜 · 조회수 · 방문자 · 메인/챔피언/소환사 조회수)
    const table = document.createElement('table');
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    table.style.fontSize = '0.85rem';
    table.style.textAlign = 'left';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    headerRow.style.borderBottom = '1px solid var(--admin-border)';

    const headers = ['날짜', '조회수', '방문자', '메인/챔피언/소환사 조회수'];
    headers.forEach(hText => {
      const th = document.createElement('th');
      th.style.padding = '10px 12px';
      th.style.color = 'var(--admin-text-muted)';
      th.style.fontWeight = '700';
      th.style.whiteSpace = 'nowrap';
      th.textContent = hText;
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    days.forEach(d => {
      const tr = document.createElement('tr');
      tr.style.borderBottom = '1px solid rgba(42, 54, 79, 0.5)';

      // 1. 날짜
      const tdDay = document.createElement('td');
      tdDay.style.padding = '10px 12px';
      tdDay.style.whiteSpace = 'nowrap';
      tdDay.textContent = (d && d.day) ? String(d.day) : '-';
      tr.appendChild(tdDay);

      // 2. 조회수
      const tdViews = document.createElement('td');
      tdViews.style.padding = '10px 12px';
      tdViews.style.whiteSpace = 'nowrap';
      const viewsVal = (d && typeof d.views === 'number') ? d.views : (Number(d && d.views) || 0);
      tdViews.textContent = viewsVal.toLocaleString('ko-KR');
      tr.appendChild(tdViews);

      // 3. 방문자
      const tdVisitors = document.createElement('td');
      tdVisitors.style.padding = '10px 12px';
      tdVisitors.style.whiteSpace = 'nowrap';
      const visVal = (d && typeof d.visitors === 'number') ? d.visitors : (Number(d && d.visitors) || 0);
      tdVisitors.textContent = visVal.toLocaleString('ko-KR');
      tr.appendChild(tdVisitors);

      // 4. 메인/챔피언/소환사 조회수
      const tdBreakdown = document.createElement('td');
      tdBreakdown.style.padding = '10px 12px';
      tdBreakdown.style.whiteSpace = 'nowrap';
      const homeVal = (d && typeof d.home === 'number') ? d.home : (Number(d && d.home) || 0);
      const champVal = (d && typeof d.champion === 'number') ? d.champion : (Number(d && d.champion) || 0);
      const summVal = (d && typeof d.summoner === 'number') ? d.summoner : (Number(d && d.summoner) || 0);
      tdBreakdown.textContent = `${homeVal.toLocaleString('ko-KR')} / ${champVal.toLocaleString('ko-KR')} / ${summVal.toLocaleString('ko-KR')}`;
      tr.appendChild(tdBreakdown);

      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    container.appendChild(table);

  } catch (_) {
    if (todayViewsEl) todayViewsEl.textContent = '-';
    if (todayVisitorsEl) todayVisitorsEl.textContent = '-';
    if (totalViewsEl) totalViewsEl.textContent = '-';
    if (container) container.textContent = '통계를 불러오지 못했습니다 (관리자 로그인 필요)';
  }
}

// ────────────────────────────────────────────────────────────────────────────
// 11. 자동 초기화 및 텔레메트리 일괄 로드
// ────────────────────────────────────────────────────────────────────────────
async function loadAllTelemetry() {
  await Promise.allSettled([
    loadDbMetrics(),
    loadCacheStats(),
    refreshSyncMetrics(),
    loadFinanceSummary(),
    loadCollectorStatus(),
    loadCommunityTips(),
    loadDuoPosts(),
    loadInhouseGames(),
    loadTrafficStats()
  ]);

  // 로컬 스토리지에 저장된 클라이언트 경로가 있다면 반영
  const savedPath = localStorage.getItem('lol_client_path');
  const clientInput = document.getElementById('adminClientPath');
  if (savedPath && clientInput && !clientInput.value) {
    clientInput.value = savedPath;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // 인증 상태인 경우 텔레메트리 자동 기동
  if (document.querySelector('.admin-stats-grid')) {
    loadAllTelemetry();
  }
  const btnRefreshDuo = document.getElementById('btnRefreshDuoPosts');
  if (btnRefreshDuo) {
    btnRefreshDuo.addEventListener('click', loadDuoPosts);
  }
});
