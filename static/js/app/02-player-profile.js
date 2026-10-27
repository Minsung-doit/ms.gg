// Ensure polished summoner stylesheet is loaded
(function ensurePolishStylesheet() {
  if (typeof document !== "undefined" && !document.getElementById("polishSummonerCss")) {
    const link = document.createElement("link");
    link.id = "polishSummonerCss";
    link.rel = "stylesheet";
    link.href = "/static/css/app/24-polish-summoner.css";
    document.head.appendChild(link);
  }
})();

// Ultra-Fast Player Profile Cache & Prefetch Engine
const playerProfileCache = new Map();

function getPlayerCacheKey(name, tag) {
  return `${(name || "").trim().toLowerCase()}#${(tag || "KR1").trim().toLowerCase()}`;
}

async function prefetchPlayerDetail(player) {
  if (!player || !player.game_name) return;
  const key = getPlayerCacheKey(player.game_name, player.tag_line);
  if (playerProfileCache.has(key)) return;

  try {
    const res = await fetch(`/api/player/${encodeURIComponent(player.game_name)}/${encodeURIComponent(player.tag_line || 'KR1')}`);
    if (res.ok) {
      const data = await res.json();
      if (data && data.player) {
        playerProfileCache.set(key, data.player);
      }
    }
  } catch (e) {
    // Background prefetch silent ignore
  }
}

function prefetchLeaderboardTopPlayers(players) {
  // 프로필 조회는 라이엇 API를 실제로 호출하므로 랭킹 화면에서 대량 프리패치는 하지 않는다 (API 할당량 보호)
}

async function openPlayerDetail(player) {
  currentDetailPlayer = player;
  playerDetailModal.classList.remove("load-failed");
  currentActiveGraphPeriod = "daily";
  const key = getPlayerCacheKey(player.game_name, player.tag_line);

  // 최근 검색 기록에는 실제로 불러온 소환사만 남긴다 (없는 소환사·조회 실패는 제외)
  const rememberSearch = (p) => {
    if (typeof addRecentSearch === "function") addRecentSearch(p.game_name, p.tag_line, p.tier);
  };

  // 1. 프리패치 캐시 히트: 0ms (50ms 이내) 즉각 모달 렌더링
  if (playerProfileCache.has(key)) {
    const cachedPlayer = playerProfileCache.get(key);
    currentDetailFullProfile = cachedPlayer;
    rememberSearch(cachedPlayer);
    renderFullPlayerModal(cachedPlayer);
    playerDetailModal.classList.add("active");
    return;
  }

  // 2. 캐시 미스 시: 모달 오픈 및 백그라운드 페치
  playerDetailContent.innerHTML = `
    <div style="padding: 2.5rem; text-align: center; color: var(--text-muted);">
      <div class="spinner" style="margin: 0 auto 1rem;"></div>
      <div>소환사 전체 전적 데이터 및 과거 시즌 기록을 불러오는 중...</div>
    </div>
  `;
  playerDetailModal.classList.add("active");

  try {
    const res = await fetch(`/api/player/${encodeURIComponent(player.game_name)}/${encodeURIComponent(player.tag_line)}`);
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || "소환사 상세 정보를 불러올 수 없습니다.");
    }
    const data = await res.json();
    const fullPlayer = data.player || player;
    playerProfileCache.set(key, fullPlayer); // 캐시 보관
    currentDetailFullProfile = fullPlayer;
    rememberSearch(fullPlayer);
    renderFullPlayerModal(fullPlayer);
  } catch (err) {
    // 못 찾았을 때는 공유·갱신 버튼을 숨긴다 (보여줄 전적이 없음)
    playerDetailModal.classList.add("load-failed");
    playerDetailContent.innerHTML = `
      <div style="padding: 2rem; text-align: center; color: #E84057;">
        <i class="fa-solid fa-circle-exclamation" style="font-size: 1.8rem; margin-bottom: 0.5rem; display: block;"></i>
        ${escapeHtml(err.message || "데이터를 불러오는 중 오류가 발생했습니다.")}
        <div style="margin-top: 8px; font-size: 0.82rem; color: var(--text-muted);">이름#태그 형식(예: Hide on bush#KR1)인지 확인해 주세요.</div>
      </div>
    `;
  }
}

function openPlayerModal(gameName, tagLine) {
  if (typeof gameName === "object" && gameName !== null) {
    return openPlayerDetail(gameName);
  }
  return openPlayerDetail({ game_name: gameName, tag_line: tagLine || "KR1" });
}
window.openPlayerModal = openPlayerModal;
window.openPlayerDetail = openPlayerDetail;
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Safe argument for inline on*="" handlers: a JSON string literal, HTML-escaped for the attribute
function jsArg(v) {
  return escapeHtml(JSON.stringify(v == null ? "" : String(v)));
}

// 언랭크(티어 없음)는 엠블럼을 비워 둔다 (아이언 그림을 보여주면 아이언으로 오해)
function getTierCrestEmblemUrl(tier) {
  const raw = String(tier || "").trim().toUpperCase();
  if (!raw || raw === "UNRANKED" || raw.includes("언랭")) return "";
  if (typeof getTierEmblemUrl === "function") {
    return getTierEmblemUrl(tier);
  }
  const t = String(tier).toLowerCase().trim();
  const validTiers = ["iron", "bronze", "silver", "gold", "platinum", "emerald", "diamond", "master", "grandmaster", "challenger"];
  for (const vt of validTiers) {
    if (t.includes(vt)) return `/static/images/tiers/${vt}.png`;
  }
  return "";
}

const KOREAN_CHAMP_TO_EN_ID = {"가렌": "Garen", "갈리오": "Galio", "갱플랭크": "Gangplank", "그라가스": "Gragas", "그레이브즈": "Graves", "그웬": "Gwen", "나르": "Gnar", "나미": "Nami", "나서스": "Nasus", "나피리": "Naafiri", "노틸러스": "Nautilus", "녹턴": "Nocturne", "누누와 윌럼프": "Nunu", "니달리": "Nidalee", "니코": "Neeko", "닐라": "Nilah", "다리우스": "Darius", "다이애나": "Diana", "드레이븐": "Draven", "라이즈": "Ryze", "라칸": "Rakan", "람머스": "Rammus", "럭스": "Lux", "럼블": "Rumble", "레나타 글라스크": "Renata", "레넥톤": "Renekton", "레오나": "Leona", "렉사이": "RekSai", "렐": "Rell", "렝가": "Rengar", "루시안": "Lucian", "룰루": "Lulu", "르블랑": "Leblanc", "리 신": "LeeSin", "리븐": "Riven", "리산드라": "Lissandra", "릴리아": "Lillia", "마스터 이": "MasterYi", "마오카이": "Maokai", "말자하": "Malzahar", "말파이트": "Malphite", "모데카이저": "Mordekaiser", "모르가나": "Morgana", "문도 박사": "DrMundo", "미스 포츈": "MissFortune", "밀리오": "Milio", "바드": "Bard", "바루스": "Varus", "바이": "Vi", "베이가": "Veigar", "베인": "Vayne", "벡스": "Vex", "벨베스": "Belveth", "벨코즈": "Velkoz", "볼리베어": "Volibear", "브라움": "Braum", "브라이어": "Briar", "브랜드": "Brand", "블라디미르": "Vladimir", "블리츠크랭크": "Blitzcrank", "비에고": "Viego", "빅토르": "Viktor", "뽀삐": "Poppy", "사미라": "Samira", "사이온": "Sion", "사일러스": "Sylas", "샤코": "Shaco", "세나": "Senna", "세라핀": "Seraphine", "세주아니": "Sejuani", "세트": "Sett", "소나": "Sona", "소라카": "Soraka", "쉔": "Shen", "쉬바나": "Shyvana", "스몰더": "Smolder", "스웨인": "Swain", "스카너": "Skarner", "시비르": "Sivir", "신 짜오": "XinZhao", "신드라": "Syndra", "신지드": "Singed", "쓰레쉬": "Thresh", "아리": "Ahri", "아무무": "Amumu", "아우렐리온 솔": "AurelionSol", "아이번": "Ivern", "아지르": "Azir", "아칼리": "Akali", "아크샨": "Akshan", "아트록스": "Aatrox", "아펠리오스": "Aphelios", "알리스타": "Alistar", "애니": "Annie", "애니비아": "Anivia", "애쉬": "Ashe", "야스오": "Yasuo", "에코": "Ekko", "엘리스": "Elise", "오공": "MonkeyKing", "오로라": "Aurora", "오른": "Ornn", "오리아나": "Orianna", "올라프": "Olaf", "요네": "Yone", "요릭": "Yorick", "우디르": "Udyr", "우르곳": "Urgot", "워윅": "Warwick", "유미": "Yuumi", "이렐리아": "Irelia", "이블린": "Evelynn", "이즈리얼": "Ezreal", "일라오이": "Illaoi", "자르반 4세": "JarvanIV", "자야": "Xayah", "자이라": "Zyra", "자크": "Zac", "잔나": "Janna", "잭스": "Jax", "제드": "Zed", "제라스": "Xerath", "제리": "Zeri", "제이스": "Jayce", "조이": "Zoe", "직스": "Ziggs", "진": "Jhin", "질리언": "Zilean", "징크스": "Jinx", "초가스": "Chogath", "카르마": "Karma", "카밀": "Camille", "카사딘": "Kassadin", "카서스": "Karthus", "카시오페아": "Cassiopeia", "카이사": "Kaisa", "카직스": "Khazix", "카타리나": "Katarina", "칼리스타": "Kalista", "케넨": "Kennen", "케이틀린": "Caitlyn", "케인": "Kayn", "케일": "Kayle", "코그모": "KogMaw", "코르키": "Corki", "퀸": "Quinn", "크산테": "KSante", "클레드": "Kled", "키아나": "Qiyana", "킨드레드": "Kindred", "타릭": "Taric", "탈론": "Talon", "탈리야": "Taliyah", "탐 켄치": "TahmKench", "트런들": "Trundle", "트리스타나": "Tristana", "트린다미어": "Tryndamere", "트위스티드 페이트": "TwistedFate", "트위치": "Twitch", "티모": "Teemo", "파이크": "Pyke", "판테온": "Pantheon", "피들스틱": "Fiddlesticks", "피오라": "Fiora", "피즈": "Fizz", "하이머딩거": "Heimerdinger", "헤카림": "Hecarim", "흐웨이": "Hwei", "누누와윌럼프": "Nunu", "레나타글라스크": "Renata", "리신": "LeeSin", "마스터이": "MasterYi", "문도박사": "DrMundo", "미스포츈": "MissFortune", "신짜오": "XinZhao", "아우렐리온솔": "AurelionSol", "자르반4세": "JarvanIV", "탐켄치": "TahmKench", "트위스티드페이트": "TwistedFate"};

function normalizeChampionImgUrl(imgOrName) {
  if (!imgOrName) return "https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png";
  if (typeof imgOrName !== "string") return "https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png";
  if (imgOrName.startsWith("http://") || imgOrName.startsWith("https://")) return imgOrName;
  let clean = imgOrName.replace(/\.png$/i, "").trim();
  const cleanNoSpace = clean.replace(/\s+/g, "");
  if (typeof KOREAN_CHAMP_TO_EN_ID !== "undefined") {
    if (KOREAN_CHAMP_TO_EN_ID[clean]) clean = KOREAN_CHAMP_TO_EN_ID[clean];
    else if (KOREAN_CHAMP_TO_EN_ID[cleanNoSpace]) clean = KOREAN_CHAMP_TO_EN_ID[cleanNoSpace];
  }
  return `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/${clean}.png`;
}

/**
 * OP.GG 시그니처 [솔로랭크 & 자유랭크 듀얼 티어 카드] HTML 생성기
 * - 2단 대칭 카드 레이아웃 (.player-tier-cards-dual)
 * - 고해상도 공식 엠블럼 크레스트, 티어명, LP, 승/패/승률
 * - LP 승급 진행도 바 (75 / 100 LP (승급전까지 25 LP))
 * - 이전 시즌 티어 히스토리 뱃지 (S2024 마스터, S2023 챌린저 등)
 */
function renderDualTierCardsHtml(p) {
  // 1. 솔로랭크 데이터 추출
  const solo = p.solo || {
    tier: p.tier || "UNRANKED",
    rank_tier: p.rank_tier || "",
    league_points: p.league_points || 0,
    wins: p.wins || 0,
    losses: p.losses || 0,
    win_rate: p.win_rate || 0,
    display_tier: p.display_tier || "언랭크"
  };
  const soloTier = (solo.tier || "UNRANKED").toUpperCase();
  const soloColor = getTierColorHex(soloTier);
  const soloCrest = getTierCrestEmblemUrl(soloTier);
  const soloLp = Number(solo.league_points) || 0;
  const soloWins = Number(solo.wins) || 0;
  const soloLosses = Number(solo.losses) || 0;
  const soloTotal = soloWins + soloLosses;
  const soloWinRate = solo.win_rate ? Number(solo.win_rate) : (soloTotal > 0 ? Math.round((soloWins / soloTotal) * 100) : 0);

  // 솔로랭크 LP 승급 진행도 바 계산
  let soloProgressPct = 0;
  let soloLpText = "";
  const isSoloApex = ["MASTER", "GRANDMASTER", "CHALLENGER"].includes(soloTier);
  if (soloTier === "UNRANKED") {
    soloProgressPct = 0;
    soloLpText = "0 / 100 LP";
  } else if (isSoloApex) {
    soloProgressPct = 100;
    soloLpText = `${formatNumber(soloLp)} LP`;
  } else {
    soloProgressPct = Math.min(100, Math.max(0, soloLp));
    soloLpText = `${soloProgressPct} / 100 LP`;
  }

  // 2. 자유랭크 데이터 추출
  const flex = p.flex || {
    tier: p.flex_tier || "UNRANKED",
    rank_tier: p.flex_rank_tier || "",
    league_points: p.flex_lp || 0,
    wins: p.flex_wins || 0,
    losses: p.flex_losses || 0,
    win_rate: p.flex_win_rate || 0,
    display_tier: p.flex_display || "언랭크"
  };
  const flexTier = (flex.tier || "UNRANKED").toUpperCase();
  const flexColor = getTierColorHex(flexTier);
  const flexCrest = getTierCrestEmblemUrl(flexTier);
  const flexLp = Number(flex.league_points) || 0;
  const flexWins = Number(flex.wins) || 0;
  const flexLosses = Number(flex.losses) || 0;
  const flexTotal = flexWins + flexLosses;
  const flexWinRate = flex.win_rate ? Number(flex.win_rate) : (flexTotal > 0 ? Math.round((flexWins / flexTotal) * 100) : 0);

  // 자유랭크 LP 승급 진행도 바 계산
  let flexProgressPct = 0;
  let flexLpText = "";
  const isFlexApex = ["MASTER", "GRANDMASTER", "CHALLENGER"].includes(flexTier);
  if (flexTier === "UNRANKED") {
    flexProgressPct = 0;
    flexLpText = "0 / 100 LP";
  } else if (isFlexApex) {
    flexProgressPct = 100;
    flexLpText = `${formatNumber(flexLp)} LP`;
  } else {
    flexProgressPct = Math.min(100, Math.max(0, flexLp));
    flexLpText = `${flexProgressPct} / 100 LP`;
  }

  // 과거 시즌 히스토리 뱃지 (라이엇 API가 제공하지 않으므로 데이터가 있을 때만 표시)
  const pastBadges = p.past_tier_badges || [];

  const pastBadgesHtml = pastBadges.map(b => `
    <span class="past-season-badge" title="과거 시즌: ${escapeHtml(b.label || '')}">
      <i class="fa-solid fa-medal" style="color: ${getTierColorHex(b.tier)}; margin-right: 3px;"></i>${escapeHtml(b.label || '')}
    </span>
  `).join("");

  return `
    <div class="player-tier-cards-dual">
      <div class="tier-dual-card solo-rank-card" style="border-left-color: ${soloColor};">
        <div>
          <div class="tier-dual-header">
            <span class="tier-dual-queue-badge">
              <i class="fa-solid fa-user"></i> 솔로랭크
            </span>
          </div>
          <div class="tier-dual-body">
            ${soloCrest ? `
            <div class="tier-dual-crest-wrap">
              <img class="tier-dual-crest" src="${soloCrest}" alt="${soloTier}">
            </div>` : ''}
            <div class="tier-dual-info">
              <div class="tier-dual-name-row">
                <span class="tier-dual-name" style="--tier-color: ${soloColor}; color: ${soloColor};">${escapeHtml(solo.display_tier)}</span>
                ${(soloTotal > 0 && soloTier !== 'UNRANKED') ? `<span class="tier-dual-lp">${formatNumber(soloLp)} LP</span>` : ''}
              </div>
              <div class="tier-dual-winloss">
                ${soloTotal > 0 ? `
                  <span class="wins-text">${soloWins}승</span>
                  <span class="losses-text">${soloLosses}패</span>
                  <span class="winrate-badge ${soloWinRate > 50 ? 'is-good' : 'is-bad'}">${soloWinRate}%</span>
                ` : `
                  <span class="tier-unranked-note" style="color: var(--text-muted);">배치 전적 없음</span>
                `}
              </div>
            </div>
          </div>
        </div>

        <div>
          ${(!isSoloApex && soloTier !== 'UNRANKED' && soloTotal > 0) ? `
          <div class="tier-lp-progress-section">
            <div class="tier-lp-labels-row">
              <span><i class="fa-solid fa-chart-simple"></i> LP 승급</span>
              <span class="tier-lp-target-text">${soloLpText}</span>
            </div>
            <div class="tier-lp-track">
              <div class="tier-lp-fill" style="width: ${soloProgressPct}%; background: linear-gradient(90deg, ${soloColor}, #60A5FA);"></div>
            </div>
          </div>` : ''}

          ${pastBadges.length ? `
          <div class="tier-past-badges-row">
            <span class="tier-past-label"><i class="fa-solid fa-clock-rotate-left"></i> 히스토리:</span>
            ${pastBadgesHtml}
          </div>` : ''}
        </div>
      </div>

      <div class="tier-dual-card flex-rank-card" style="border-left-color: ${flexColor};">
        <div>
          <div class="tier-dual-header">
            <span class="tier-dual-queue-badge">
              <i class="fa-solid fa-users"></i> 자유랭크
            </span>
          </div>
          <div class="tier-dual-body">
            ${flexCrest ? `
            <div class="tier-dual-crest-wrap">
              <img class="tier-dual-crest" src="${flexCrest}" alt="${flexTier}">
            </div>` : ''}
            <div class="tier-dual-info">
              <div class="tier-dual-name-row">
                <span class="tier-dual-name" style="--tier-color: ${flexColor}; color: ${flexColor};">${escapeHtml(flex.display_tier)}</span>
                ${(flexTotal > 0 && flexTier !== 'UNRANKED') ? `<span class="tier-dual-lp">${formatNumber(flexLp)} LP</span>` : ''}
              </div>
              <div class="tier-dual-winloss">
                ${flexTotal > 0 ? `
                  <span class="wins-text">${flexWins}승</span>
                  <span class="losses-text">${flexLosses}패</span>
                  <span class="winrate-badge ${flexWinRate > 50 ? 'is-good' : 'is-bad'}">${flexWinRate}%</span>
                ` : `
                  <span class="tier-unranked-note" style="color: var(--text-muted);">배치 전적 없음</span>
                `}
              </div>
            </div>
          </div>
        </div>

        <div>
          ${(!isFlexApex && flexTier !== 'UNRANKED' && flexTotal > 0) ? `
          <div class="tier-lp-progress-section">
            <div class="tier-lp-labels-row">
              <span><i class="fa-solid fa-chart-simple"></i> LP 승급</span>
              <span class="tier-lp-target-text">${flexLpText}</span>
            </div>
            <div class="tier-lp-track">
              <div class="tier-lp-fill" style="width: ${flexProgressPct}%; background: linear-gradient(90deg, ${flexColor}, #A78BFA);"></div>
            </div>
          </div>` : ''}

        </div>
      </div>
    </div>
  `;
}

function renderFullPlayerModal(p) {
  const meta = p.tier_meta || { kr_name: p.tier, colors: {} };
  const currTierColor = meta.colors?.border || getTierColorHex(p.tier);
  const iconUrl = `${ICON_BASE_URL}${p.profile_icon_id || 29}.png`;
  const tierCrestUrl = getTierCrestEmblemUrl(p.tier);
  
  const peakTierColor = getTierColorHex(p.peak_tier);
  const lowestTierColor = getTierColorHex(p.lowest_tier);
  
  const peakTierDisplay = getDisplayTierString(p.peak_tier, p.peak_rank_tier, p.peak_lp);
  const lowestTierDisplay = getDisplayTierString(p.lowest_tier, p.lowest_rank_tier, p.lowest_lp);

  // Past seasons keys
  const pastSeasons = p.past_seasons || {};
  const seasonKeys = Object.keys(pastSeasons).sort().reverse();
  currentActiveSeasonId = seasonKeys.length > 0 ? seasonKeys[0] : null;
  const hasTierHistory = ["daily", "weekly", "monthly"].some(k => (p.tier_history?.[k] || []).length > 0);
  // 일별 기록이 아직 없으면 점이 있는 첫 기간(주별·월별)으로 연다
  if (hasTierHistory && !(p.tier_history?.[currentActiveGraphPeriod] || []).length) {
    currentActiveGraphPeriod = ["daily", "weekly", "monthly"].find(k => (p.tier_history?.[k] || []).length > 0);
  }

  // Custom player note
  const playerNote = (typeof getPlayerNote === "function") ? getPlayerNote(p.game_name, p.tag_line) : "";
  const noteBadgeHtml = playerNote ? `
    <span class="player-custom-note-badge" id="playerCustomNoteBadge" title="소환사 메모: ${escapeHtml(playerNote)} (클릭하여 수정)">
      <i class="fa-solid fa-note-sticky"></i> ${escapeHtml(playerNote)}
    </span>
  ` : "";

  playerDetailContent.innerHTML = `
    <div class="player-modal-header-card">
      <div class="player-modal-profile">
        <div class="player-modal-avatar-wrap">
          <img class="player-modal-avatar" src="${iconUrl}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/profileicon/29.png'">
          <div class="player-modal-lvl">Lv.${p.summoner_level}</div>
        </div>
        <div class="player-modal-info">
          <div class="player-modal-name-row">
            <span class="player-modal-name">${escapeHtml(p.game_name)}</span>
            <span class="player-modal-tag">#${escapeHtml(p.tag_line)}</span>
            ${noteBadgeHtml}
            <div id="modalProfileBadgeContainer" class="modal-badge-container"></div>
            <button id="btnBookmarkPlayer" class="btn-star-bookmark ${isBookmarked(p.game_name, p.tag_line) ? 'bookmarked' : ''}" title="즐겨찾기 추가/해제">
              <i class="fa-solid fa-star"></i>
            </button>
            <button id="btnNotePlayer" class="btn-note-player ${playerNote ? 'has-note' : ''}" title="소환사 개인 메모 작성/수정">
              <i class="fa-solid fa-pen-to-square"></i>
            </button>
          </div>
          <div class="player-modal-sync-time">
            <i class="fa-regular fa-clock"></i> 마지막 동기화: ${p.updated_at ? p.updated_at.split(".")[0].replace("T", " ") : "방금 전"}
          </div>
        </div>
      </div>
      <div class="player-modal-header-actions">
        <button id="btnModalHeaderSpectator" class="btn-player-spectator" title="이 소환사의 실시간 관전">
          <i class="fa-solid fa-tower-broadcast"></i>
          <span>실시간 관전</span>
        </button>
        <button id="btnModalHeaderRefresh" class="btn-player-refresh" title="전적 갱신">
          <i class="fa-solid fa-arrows-rotate"></i>
          <span class="btn-refresh-text">전적 갱신</span>
        </button>
      </div>
    </div>

    <div id="playerSyncProgressBar" class="player-sync-progress-box" style="display: none;">
      <div class="sync-progress-info">
        <div class="sync-progress-status-left">
          <span id="syncProgressSpinner" class="sync-spinner-pulse"><i class="fa-solid fa-arrows-rotate fa-spin"></i></span>
          <span id="syncProgressStatusText" class="sync-progress-text">Riot 서버와 동기화 중...</span>
        </div>
        <div id="syncProgressPercent" class="sync-progress-percent">0%</div>
      </div>
      <div class="sync-progress-track">
        <div id="syncProgressFill" class="sync-progress-fill" style="width: 0%;"></div>
      </div>
    </div>

    <div class="modal-nav-tabs">
      <button id="btnModalTabSummary" class="modal-nav-tab active">
        <i class="fa-solid fa-clock-rotate-left"></i> 전적
      </button>
      <button id="btnModalTabIngame" class="modal-nav-tab">
        <i class="fa-solid fa-satellite-dish" style="color: #10B981;"></i> 인게임
      </button>
    </div>

    <div id="modalSummaryTabContent">
      ${renderDualTierCardsHtml(p)}
      ${(p.top_masteries || []).length ? `
      <div class="profile-mastery-strip" aria-label="챔피언 숙련도">
        ${p.top_masteries.map(m => `
          <button type="button" class="pm-item" onclick="openChampionPage(${jsArg(m.id)})" title="${escapeHtml(m.name)} 숙련도 ${escapeHtml(String(m.points))}">
            <img src="${escapeHtml(m.image)}" alt="${escapeHtml(m.name)}">
            <span class="pm-lvl">${escapeHtml(String(m.level))}</span>
            <span class="pm-pts">${m.points >= 10000 ? (m.points / 10000).toFixed(1) + "만" : escapeHtml(String(m.points))}</span>
          </button>`).join("")}
      </div>` : ""}

      ${p.peak_tier ? `
      <div class="tier-summary-grid">
        <div class="tier-card" style="border-left: 4px solid ${peakTierColor};">
          <div>
            <div class="tier-card-label">
              <i class="fa-solid fa-trophy" style="color: #F59E0B;"></i> 과거 최고 티어
            </div>
            <div class="tier-card-badge-row">
              <span class="tier-card-value" style="color: ${peakTierColor};">${peakTierDisplay}</span>
            </div>
          </div>
          <div class="tier-card-sub">
            <i class="fa-regular fa-calendar-check" style="color: #F59E0B;"></i> ${p.peak_season || '과거 시즌 달성'}
          </div>
        </div>

        <div class="tier-card" style="border-left: 4px solid ${lowestTierColor};">
          <div>
            <div class="tier-card-label">
              <i class="fa-solid fa-arrow-trend-down" style="color: #94A3B8;"></i> 과거 최저 티어
            </div>
            <div class="tier-card-badge-row">
              <span class="tier-card-value" style="color: ${lowestTierColor};">${lowestTierDisplay}</span>
            </div>
          </div>
          <div class="tier-card-sub">
            <i class="fa-regular fa-clock" style="color: #94A3B8;"></i> ${p.lowest_season || '과거 시즌 기록'}
          </div>
        </div>
      </div>` : ''}
      ${p.data_source === "cache" && p.stale_reason ? `
      <div class="player-data-notice" style="margin: 0.75rem 0; padding: 0.6rem 0.9rem; border-radius: 8px; background: rgba(245, 158, 11, 0.12); color: #B45309; font-size: 0.82rem; font-weight: 600;">
        <i class="fa-solid fa-circle-info"></i> ${escapeHtml(p.stale_reason)}
      </div>` : ''}

      ${hasTierHistory ? `<div class="player-modal-content-grid">
        <div class="player-modal-graph-col">
          <div id="tierGraphSection" class="tier-graph-section">
            <div class="tier-graph-header">
              <div class="tier-graph-title">
                <i class="fa-solid fa-chart-line" style="color: var(--primary);"></i> 티어 변동 추이
              </div>
              <div class="tier-graph-tabs">
                <button class="tier-graph-tab ${currentActiveGraphPeriod === 'daily' ? 'active' : ''}" data-period="daily">일별</button>
                <button class="tier-graph-tab ${currentActiveGraphPeriod === 'weekly' ? 'active' : ''}" data-period="weekly">주별</button>
                <button class="tier-graph-tab ${currentActiveGraphPeriod === 'monthly' ? 'active' : ''}" data-period="monthly">월별</button>
              </div>
            </div>

            <div class="tier-graph-canvas-wrap">
              <svg id="tierGraphSvg" class="tier-graph-svg" viewBox="0 0 760 190" preserveAspectRatio="none"></svg>
              <div id="tierGraphTooltip" class="tier-graph-tooltip"></div>
            </div>

            <div id="tierGraphFooterStats" class="tier-graph-footer-stats">
            </div>
          </div>
        </div>

        <aside class="player-modal-side-ad-col">
          <div class="ad-slot ad-rectangle" data-ad-format="rectangle">
            <div class="ad-placeholder-box ad-box-rectangle">
              <span class="ad-badge-tag">SPONSORED</span>
              <div class="ad-placeholder-info" style="text-align: center; align-items: center;">
                <i class="fa-solid fa-rectangle-ad" style="font-size: 1.6rem; color: #F59E0B; margin-bottom: 4px;"></i>
                <span class="ad-spec-title" style="justify-content: center;">맞춤형 기어 &amp; 파트너 배너</span>
                <span class="ad-spec-desc">300 × 250 Medium Rectangle</span>
              </div>
              <button type="button" class="ad-inquiry-btn" onclick="window.openContactModal &amp;&amp; window.openContactModal();">광고 문의</button>
            </div>
          </div>
        </aside>
      </div>` : ''}

      ${seasonKeys.length ? `<div class="past-seasons-section">
        <div class="past-seasons-header">
          <div class="past-seasons-title">
            <i class="fa-solid fa-clock-rotate-left" style="color: #F59E0B;"></i> 과거 시즌 전적
          </div>
          <div id="seasonTabsWrap" class="season-tabs-wrap">
            ${seasonKeys.map((sid, idx) => {
              const sName = pastSeasons[sid]?.season_name || sid;
              return `<button class="season-tab-btn ${idx === 0 ? 'active' : ''}" data-season="${sid}">${sName}</button>`;
            }).join('')}
          </div>
        </div>

        <div id="seasonChampsTableWrap" class="season-champs-table-wrapper">
        </div>
      </div>` : ''}
    </div>

    <div id="modalMatchesTabContent">
      <div id="modalMatchesLoading" class="state-box" style="padding: 2.5rem; text-align: center;">
        <div class="spinner" style="margin: 0 auto 1rem;"></div>
        <div class="state-title">최근 20경기 상세 매치 데이터를 불러오는 중...</div>
      </div>
      <div id="modalMatchesContainer" style="display: none;"></div>
    </div>

    <div id="modalIngameTabContent" style="display: none;">
      <div id="modalIngameLoading" class="state-box" style="padding: 2.5rem; text-align: center;">
        <div class="spinner" style="margin: 0 auto 1rem;"></div>
        <div class="state-title">실시간 게임 진행 여부를 확인하는 중...</div>
      </div>
      <div id="modalIngameContainer" style="display: none;"></div>
    </div>
  `;

  // Attach modal sub-tab navigation (Defensive Null-Safe Binding)
  const btnModalTabSummary = document.getElementById("btnModalTabSummary");
  const btnModalTabMatches = document.getElementById("btnModalTabMatches");
  const btnModalTabIngame = document.getElementById("btnModalTabIngame");
  const modalSummaryTabContent = document.getElementById("modalSummaryTabContent");
  const modalMatchesTabContent = document.getElementById("modalMatchesTabContent");
  const modalIngameTabContent = document.getElementById("modalIngameTabContent");

  let matchesLoaded = false;
  let ingameLoaded = false;

  const showSubTab = (tab) => {
    btnModalTabSummary?.classList.toggle("active", tab === "summary");
    btnModalTabMatches?.classList.toggle("active", tab === "matches");
    btnModalTabIngame?.classList.toggle("active", tab === "ingame");

    if (modalSummaryTabContent) modalSummaryTabContent.style.display = tab === "summary" ? "block" : "none";
    if (modalMatchesTabContent) modalMatchesTabContent.style.display = (tab === "summary" || tab === "matches") ? "block" : "none";
    if (modalIngameTabContent) modalIngameTabContent.style.display = tab === "ingame" ? "block" : "none";
  };

  btnModalTabSummary?.addEventListener("click", () => showSubTab("summary"));
  matchesLoaded = true;
  loadPlayerRecentMatches(p);

  btnModalTabMatches?.addEventListener("click", async () => {
    showSubTab("matches");
    if (!matchesLoaded) {
      matchesLoaded = true;
      await loadPlayerRecentMatches(p);
    }
  });

  btnModalTabIngame?.addEventListener("click", async () => {
    showSubTab("ingame");
    if (!ingameLoaded) {
      ingameLoaded = true;
      await loadPlayerIngame(p);
    }
  });

  // Header spectator button handler
  const btnModalHeaderSpectator = document.getElementById("btnModalHeaderSpectator");
  if (btnModalHeaderSpectator) {
    btnModalHeaderSpectator.addEventListener("click", () => {
      // 이 소환사의 실제 진행 중인 게임은 프로필의 '실시간 인게임' 탭에서 보여준다
      btnModalTabIngame?.click();
    });
  }

  // Bookmark button handler
  const btnBookmark = document.getElementById("btnBookmarkPlayer");
  if (btnBookmark) {
    btnBookmark.addEventListener("click", () => {
      toggleBookmark(p);
      btnBookmark.classList.toggle("bookmarked", isBookmarked(p.game_name, p.tag_line));
    });
  }

  // Personal Note button handler
  const btnNote = document.getElementById("btnNotePlayer");
  if (btnNote) {
    btnNote.addEventListener("click", () => {
      if (typeof openPlayerNoteModal === "function") {
        openPlayerNoteModal(p.game_name, p.tag_line);
      }
    });
  }

  // Personal Note badge click handler (edit note directly)
  const noteBadgeEl = document.getElementById("playerCustomNoteBadge");
  if (noteBadgeEl) {
    noteBadgeEl.addEventListener("click", () => {
      if (typeof openPlayerNoteModal === "function") {
        openPlayerNoteModal(p.game_name, p.tag_line);
      }
    });
  }

  // Header modal refresh button handler
  const btnModalHeaderRefresh = document.getElementById("btnModalHeaderRefresh");
  if (btnModalHeaderRefresh) {
    btnModalHeaderRefresh.addEventListener("click", () => {
      syncPlayerRecords(p);
    });
  }

  // Attach event listeners for mini graph button
  const btnMiniGraph = document.getElementById("btnMiniTierGraph");
  const graphSec = document.getElementById("tierGraphSection");
  if (btnMiniGraph && graphSec) {
    btnMiniGraph.addEventListener("click", () => {
      graphSec.scrollIntoView({ behavior: "smooth", block: "center" });
      graphSec.style.boxShadow = "0 0 20px rgba(83, 131, 232, 0.6)";
      setTimeout(() => {
        graphSec.style.boxShadow = "";
      }, 1500);
    });
  }

  // Attach graph tab events
  const graphTabs = playerDetailContent.querySelectorAll(".tier-graph-tab");
  graphTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      graphTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentActiveGraphPeriod = tab.getAttribute("data-period");
      renderTierGraphSVG(p.tier_history?.[currentActiveGraphPeriod] || [], currentActiveGraphPeriod);
    });
  });

  // Attach past season tab events
  const seasonBtns = playerDetailContent.querySelectorAll(".season-tab-btn");
  seasonBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      seasonBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const sid = btn.getAttribute("data-season");
      renderSeasonChampionsTable(pastSeasons[sid]);
    });
  });

  // Initial graph render
  if (hasTierHistory) renderTierGraphSVG(p.tier_history?.[currentActiveGraphPeriod] || [], currentActiveGraphPeriod);

  // Initial past season table render
  if (currentActiveSeasonId && pastSeasons[currentActiveSeasonId]) {
    renderSeasonChampionsTable(pastSeasons[currentActiveSeasonId]);
  }
}

function renderTierGraphSVG(points, periodType) {
  const svg = document.getElementById("tierGraphSvg");
  const tooltip = document.getElementById("tierGraphTooltip");
  const footerStats = document.getElementById("tierGraphFooterStats");
  if (!svg || !points || points.length === 0) return;

  const w = 760;
  const h = 190;
  const padLeft = 70;
  const padRight = 30;
  const padTop = 25;
  const padBottom = 35;
  const plotW = w - padLeft - padRight;
  const plotH = h - padTop - padBottom;

  const scores = points.map(pt => pt.tier_score);
  let minScore = Math.min(...scores);
  let maxScore = Math.max(...scores);
  if (minScore === maxScore) {
    minScore -= 100;
    maxScore += 100;
  }
  const scoreRange = maxScore - minScore || 1;

  // Compute (x, y) coordinates
  const coords = points.map((pt, i) => {
    const x = padLeft + (i / (points.length - 1)) * plotW;
    const y = padTop + (1 - (pt.tier_score - minScore) / scoreRange) * plotH;
    return { x, y, pt };
  });

  // SVG Grids and Path
  let svgHtml = `
    <defs>
      <linearGradient id="tierGraphGrad" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#5383E8" stop-opacity="0.38"/>
        <stop offset="100%" stop-color="#5383E8" stop-opacity="0.0"/>
      </linearGradient>
    </defs>
  `;

  // Draw 3 horizontal grid lines
  const gridLevels = 3;
  for (let l = 0; l <= gridLevels; l++) {
    const gy = padTop + (l / gridLevels) * plotH;
    svgHtml += `
      <line x1="${padLeft}" y1="${gy}" x2="${w - padRight}" y2="${gy}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3,3" />
    `;
  }

  // Build SVG path
  let pathD = `M ${coords[0].x} ${coords[0].y}`;
  for (let i = 1; i < coords.length; i++) {
    pathD += ` L ${coords[i].x} ${coords[i].y}`;
  }

  // Area path for gradient fill
  const areaD = `${pathD} L ${coords[coords.length - 1].x} ${padTop + plotH} L ${coords[0].x} ${padTop + plotH} Z`;

  svgHtml += `<path d="${areaD}" fill="url(#tierGraphGrad)" />`;
  svgHtml += `<path d="${pathD}" fill="none" stroke="#5383E8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />`;

  // Draw X axis date labels and interactive circles
  coords.forEach((c, idx) => {
    // Only show text label for select points to prevent overlap
    const shouldShowLabel = points.length <= 14 ? (idx % 2 === 0 || idx === points.length - 1) : (idx % 3 === 0 || idx === points.length - 1);
    if (shouldShowLabel) {
      svgHtml += `
        <text x="${c.x}" y="${h - 10}" fill="#94A3B8" font-size="11" font-weight="600" text-anchor="middle">
          ${c.pt.date_label || c.pt.point_date}
        </text>
      `;
    }

    svgHtml += `
      <circle 
        class="tier-graph-dot" 
        cx="${c.x}" 
        cy="${c.y}" 
        r="4.5" 
        fill="#FFFFFF" 
        stroke="#5383E8" 
        stroke-width="2.5" 
        data-index="${idx}"
        style="cursor: pointer; transition: transform 0.15s ease;"
      />
    `;
  });

  svg.innerHTML = svgHtml;

  // Add interactive hover listeners to circle dots
  const dots = svg.querySelectorAll(".tier-graph-dot");
  dots.forEach(dot => {
    dot.addEventListener("mouseenter", (e) => {
      const idx = parseInt(dot.getAttribute("data-index"), 10);
      const c = coords[idx];
      const pt = c.pt;
      dot.setAttribute("r", "7");
      dot.setAttribute("fill", "#60A5FA");

      const tKr = TIER_NAMES_KR[pt.tier?.toUpperCase()] || pt.tier;
      const rankPart = ["CHALLENGER", "GRANDMASTER", "MASTER"].includes(pt.tier) ? "" : ` ${pt.rank_tier}`;
      const changeText = pt.lp_change >= 0 ? `+${pt.lp_change}` : `${pt.lp_change}`;
      const changeColor = pt.lp_change >= 0 ? '#10B981' : '#E84057';

      tooltip.innerHTML = `
        <div style="font-weight: 800; color: #FFFFFF; margin-bottom: 2px;">${pt.date_label} (${pt.point_date})</div>
        <div style="color: #60A5FA; font-weight: 700; display: flex; align-items: center; gap: 4px;"><img class="tier-emblem-img sm" src="${getTierEmblemUrl(pt.tier)}" alt="${tKr}" onerror="this.style.display='none';"> ${tKr}${rankPart} (${formatNumber(pt.league_points)} LP)</div>
        <div style="color: #94A3B8; font-size: 0.72rem; margin-top: 2px;">
          전적: ${pt.wins}승 ${pt.losses}패 (<span style="color: ${changeColor}; font-weight: 700;">${changeText} LP</span>)
        </div>
      `;
      tooltip.style.left = `${(c.x / w) * 100}%`;
      tooltip.style.top = `${c.y}px`;
      tooltip.style.display = "block";
    });

    dot.addEventListener("mouseleave", () => {
      dot.setAttribute("r", "4.5");
      dot.setAttribute("fill", "#FFFFFF");
      tooltip.style.display = "none";
    });
  });

  // Render footer stats summary
  if (footerStats && points.length > 0) {
    const firstPt = points[0];
    const lastPt = points[points.length - 1];
    const totalChange = lastPt.league_points - firstPt.league_points + (lastPt.tier_score - firstPt.tier_score > 50000 ? 100 : 0);
    const totalWins = points.reduce((acc, p) => acc + (p.wins || 0), 0);
    const totalLosses = points.reduce((acc, p) => acc + (p.losses || 0), 0);
    const totalGames = totalWins + totalLosses;
    const wr = totalGames > 0 ? (totalWins / totalGames * 100).toFixed(1) : 0;
    const changeColor = totalChange >= 0 ? '#10B981' : '#E84057';
    const changeSign = totalChange >= 0 ? '+' : '';

    footerStats.innerHTML = `
      <div>
        <i class="fa-regular fa-calendar"></i> 기간: <strong>${firstPt.date_label}</strong> ~ <strong>${lastPt.date_label}</strong>
      </div>
      <div>
        기간 전적: <span style="color: #4171D6; font-weight: 700;">${totalWins}승</span> <span style="color: #E84057; font-weight: 700;">${totalLosses}패</span> (승률 ${wr}%)
      </div>
      <div>
        티어 변동: <strong style="color: ${changeColor};">${changeSign}${totalChange} LP</strong>
      </div>
    `;
  }
}

function renderSeasonChampionsTable(seasonData) {
  const wrap = document.getElementById("seasonChampsTableWrap");
  if (!wrap) return;

  if (!seasonData || !seasonData.champions || seasonData.champions.length === 0) {
    wrap.innerHTML = `
      <div style="padding: 1.5rem; text-align: center; color: var(--text-muted);">
        해당 시즌 플레이 기록이 없습니다.
      </div>
    `;
    return;
  }

  const rows = seasonData.champions.map(c => {
    return `
      <tr>
        <td>
          <div class="season-champ-info">
            <img class="season-champ-avatar" src="${c.image}" alt="${c.champion_name}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
            <div class="season-champ-name">${c.champion_name}</div>
          </div>
        </td>
        <td style="font-weight: 700;">${formatNumber(c.games_played)}판</td>
        <td>
          <div style="font-weight: 700; color: ${c.win_rate >= 55 ? '#10B981' : (c.win_rate >= 50 ? '#60A5FA' : '#E84057')};">
            ${c.win_rate}%
          </div>
          <div class="season-winrate-bar">
            <div class="season-winrate-fill" style="width: ${c.win_rate}%;"></div>
          </div>
          <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">
            ${c.wins}승 ${c.losses}패
          </div>
        </td>
        <td>
          <div style="font-weight: 800; color: #10B981;">${c.kda}:1</div>
          <div style="font-size: 0.72rem; color: var(--text-muted);">${c.kills} / ${c.deaths} / ${c.assists}</div>
        </td>
        <td>
          <div style="font-weight: 700; color: var(--text-main);">${c.cs}</div>
          <div style="font-size: 0.72rem; color: var(--text-muted);">CS/게임</div>
        </td>
      </tr>
    `;
  }).join('');

  wrap.innerHTML = `
    <table class="season-champs-table">
      <thead>
        <tr>
          <th>챔피언</th>
          <th>플레이 판수</th>
          <th>승률 및 전적</th>
          <th>평균 KDA</th>
          <th>CS</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;
}
