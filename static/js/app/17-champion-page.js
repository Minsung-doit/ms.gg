// 챔피언 페이지 (/champion/<id>): 검색·티어표 등에서 챔피언을 열면 팝업 대신 이 화면으로 이동한다.
// 수집된 고티어 솔로랭크 게임 기반 (/api/champion-build). 글자는 줄이고 아이콘으로 구분한다 (이름은 마우스를 올리면 보임).

const CP_POSITIONS = [
  ["TOP", "top", "탑"], ["JUG", "jungle", "정글"], ["MID", "middle", "미드"], ["BOT", "bottom", "원딜"], ["SUP", "utility", "서포터"],
];
const CP_POS_MIN_GAMES = 20; // 이보다 적게 플레이된 라인은 선택지에서 뺀다
const CP_TIER_LABELS = [["CHALLENGER", "C"], ["GRANDMASTER", "GM"], ["MASTER", "M"], ["OTHER", "기타"]];

let cpCurrent = null; // 지금 보고 있는 빌드 데이터
let cpTier = "ALL"; // 게임 티어 필터 (ALL / MASTER_PLUS / GRANDMASTER_PLUS / CHALLENGER)
const CP_TIER_FILTERS = [["ALL", "전체"], ["MASTER_PLUS", "마스터+"], ["GRANDMASTER_PLUS", "그마+"], ["CHALLENGER", "챌린저"]];

function cpPosIcon(pos, size = 22) {
  const p = CP_POSITIONS.find(x => x[0] === pos);
  if (!p) return "";
  return `<img class="cp-pos-icon" src="/static/images/positions/${p[1]}.png" alt="${p[2]}" title="${p[2]}" style="width:${size}px;height:${size}px;">`;
}

function cpIcon(src, title, size = 32, cls = "") {
  if (!src) return "";
  return `<img class="cp-icon ${cls}" src="${escapeHtml(src)}" alt="${escapeHtml(title || "")}" title="${escapeHtml(title || "")}" style="width:${size}px;height:${size}px;" loading="lazy">`;
}

const cpPct = (v) => (v === null || v === undefined) ? "-" : `${escapeHtml(String(v))}%`;
const cpNum = (v) => (v === null || v === undefined) ? "-" : escapeHtml(Number(v).toLocaleString("ko-KR"));
// 승률 50% 초과는 초록, 50% 이하는 빨강
const cpWrClass = (wr) => (Number(wr) > 50 ? "cp-good" : "cp-bad");

// 승률 · 픽률 · 게임 수 (표 머리글에 한 번만 이름을 쓰고, 칸에는 숫자만)
function cpStats(o) {
  return `
    <span class="cp-stat ${cpWrClass(o.win_rate)}">${cpPct(o.win_rate)}</span>
    <span class="cp-stat cp-muted">${cpPct(o.pick_rate)}</span>
    <span class="cp-stat cp-muted">${cpNum(o.games)}</span>`;
}

function cpBlock(title, body, head = true) {
  if (!body) return "";
  return `
    <section class="cp-block">
      <div class="cp-block-head"><h3>${title}</h3>${head ? `<div class="cp-cols"><span>승률</span><span>픽률</span><span>게임</span></div>` : ""}</div>
      ${body}
    </section>`;
}

function cpRows(list, render) {
  if (!list || !list.length) return "";
  return list.map(o => `<div class="cp-row"><div class="cp-row-main">${render(o)}</div>${cpStats(o)}</div>`).join("");
}

const cpItems = (items, sep = "") => (items || []).map(it => cpIcon(it.icon, it.name, 30)).join(sep);
const CP_ARROW = '<i class="fa-solid fa-chevron-right cp-sep"></i>';

function cpSkillKeys(order, skills) {
  return (order || "").split(/[>,]/).map(k => k.trim()).filter(Boolean).map(k => {
    const s = skills && skills[k];
    return `<span class="cp-skill">${s && s.icon ? cpIcon(s.icon, s.name, 28) : ""}<b class="cp-skill-key key-${k.toLowerCase()}">${escapeHtml(k)}</b></span>`;
  });
}

function cpRenderRunes(b) {
  return cpRows(b.rune_options, r => {
    const page = r.page;
    if (!page) return `${cpIcon(r.keystone_icon, r.keystone_name, 30)}${cpIcon(r.sub_icon, r.sub_tree, 20, "cp-round")}`;
    const runes = (page.runes || []).map((rn, i) => cpIcon(rn.icon, rn.name, i === 0 ? 32 : 24, i === 0 ? "" : "cp-round")).join("");
    const shards = (page.shards || []).map(sh => cpIcon(sh.icon, sh.name, 18, "cp-round cp-shard")).join("");
    return `${runes}${cpIcon(r.sub_icon, r.sub_tree, 18, "cp-round cp-faint")}<span class="cp-shards">${shards}</span>`;
  });
}

// 가장 많이 쓰는 룬 페이지를 트리 전체로: 고른 룬은 밝게, 나머지는 흐리게 (op.gg·lol.ps 방식)
function cpRenderRuneTree(b) {
  const top = (b.rune_options || [])[0];
  const page = top && top.page;
  if (!page || !(page.primary_tree || []).length) return "";
  const rowHtml = (row, big) => `<div class="cp-rt-row">${row.map(rn =>
    cpIcon(rn.icon, rn.name, big ? 36 : 28, `cp-round ${rn.on ? "cp-rt-on" : "cp-rt-off"}`)).join("")}</div>`;
  return `
    <div class="cp-rune-tree">
      <div class="cp-rt-col">
        ${cpIcon(top.primary_icon, top.primary_tree, 22, "cp-round cp-rt-style")}
        ${page.primary_tree.map((row, i) => rowHtml(row, i === 0)).join("")}
      </div>
      <div class="cp-rt-col">
        ${cpIcon(top.sub_icon, top.sub_tree, 22, "cp-round cp-rt-style")}
        ${(page.secondary_tree || []).map(row => rowHtml(row, false)).join("")}
        <div class="cp-rt-shards">${(page.shard_rows || []).map(row => `<div class="cp-rt-row">${row.map(sh =>
          cpIcon(sh.icon, sh.name, 20, `cp-round cp-shard ${sh.on ? "cp-rt-on" : "cp-rt-off"}`)).join("")}</div>`).join("")}</div>
      </div>
      <div class="cp-rt-stat"><span class="${cpWrClass(page.win_rate)}">${cpPct(page.win_rate)}</span><span class="cp-mu-games">${cpNum(page.games)}</span></div>
    </div>`;
}

// 게임 시간대별 승률 (lol.ps 파워 커브처럼). 막대 높이 = 승률, 50% 기준선
function cpRenderPowerCurve(pc) {
  if (!pc || !pc.some(x => x.games >= 10)) return "";
  const label = (x) => x.to ? (x.from ? `${x.from}~${x.to}분` : `~${x.to}분`) : `${x.from}분~`;
  const h = (wr) => Math.max(4, Math.min(100, ((wr - 35) / 30) * 100)); // 35~65% 범위를 막대 높이로
  return `
    <section class="cp-block">
      <div class="cp-block-head"><h3>시간대별 승률</h3></div>
      <div class="cp-pc">
        <div class="cp-pc-mid" title="50%"></div>
        ${pc.map(x => `
          <div class="cp-pc-col" title="${escapeHtml(label(x))} ${escapeHtml(String(x.games))}게임">
            <span class="cp-pc-val ${x.games >= 10 ? cpWrClass(x.win_rate) : "cp-muted"}">${x.games >= 10 ? cpPct(x.win_rate) : "-"}</span>
            <div class="cp-pc-track"><div class="cp-pc-bar ${x.games >= 10 ? cpWrClass(x.win_rate) : ""}" style="height: ${x.games >= 10 ? h(x.win_rate) : 0}%;"></div></div>
            <span class="cp-pc-lbl">${escapeHtml(label(x))}</span>
            <span class="cp-mu-games">${cpNum(x.games)}</span>
          </div>`).join("")}
      </div>
    </section>`;
}

function cpRenderCounters(m) {
  if (!m || (!m.hard.length && !m.easy.length)) return "";
  const col = (list, cls) => list.map(o => `
    <div class="cp-mu-row" onclick="openMatchupWithChampions(${jsArg(cpCurrent && cpCurrent.champion ? cpCurrent.champion.name : "")}, ${jsArg(o.name)})" title="${escapeHtml(o.name)} 1:1 상성">
      ${cpIcon(o.image, o.name, 28)}
      <span class="cp-mu-name">${escapeHtml(o.name)}</span>
      <span class="cp-mu-wr ${cls}">${cpPct(o.win_rate)}</span>
      <span class="cp-mu-games">${cpNum(o.games)}</span>
    </div>`).join("") || `<div class="cp-empty">-</div>`;
  return `
    <section class="cp-block">
      <div class="cp-block-head"><h3>상성</h3><span class="cp-note">상대별 ${escapeHtml(String(m.min_games))}게임 이상</span></div>
      <div class="cp-mu-grid">
        <div><div class="cp-mu-title cp-bad">상대하기 어려움</div>${col(m.hard, "cp-bad")}</div>
        <div><div class="cp-mu-title cp-good">상대하기 쉬움</div>${col(m.easy, "cp-good")}</div>
      </div>
    </section>`;
}

function cpRenderSynergy(syn) {
  if (!syn || !syn.base_games) return "";
  const lanes = (syn.positions || []).filter(p => (p.champions || []).length);
  if (!lanes.length) return "";
  const tiers = (t) => CP_TIER_LABELS.filter(([k]) => t && t[k])
    .map(([k, l]) => `<span class="cp-tier-chip" title="${k === "OTHER" ? "마스터 미만 또는 확인 안 됨" : k}">${l} ${escapeHtml(String(t[k]))}</span>`).join("");
  return `
    <section class="cp-block">
      <div class="cp-block-head"><h3>잘 맞는 챔피언</h3><span class="cp-note" title="${escapeHtml(syn.tier_note || "")}">평균 ${cpPct(syn.base_win_rate)}</span></div>
      <div class="cp-syn-grid">
        ${lanes.map(l => `
          <div class="cp-syn-lane">
            <div class="cp-syn-lane-head">${cpPosIcon(l.position, 20)}</div>
            ${l.champions.map(o => `
              <div class="cp-syn-row" onclick="openChampionPage(${jsArg(o.id)})" title="${escapeHtml(o.name)}">
                ${cpIcon(o.image, o.name, 26)}
                <div class="cp-syn-main"><span class="cp-mu-name">${escapeHtml(o.name)}</span><span class="cp-syn-tiers">${tiers(o.tiers)}</span></div>
                <div class="cp-syn-num"><span class="${cpWrClass(o.win_rate)}">${cpPct(o.win_rate)}</span><span class="cp-mu-games">${cpNum(o.games)}</span></div>
              </div>`).join("")}
          </div>`).join("")}
      </div>
    </section>`;
}

function cpRender(b, skills) {
  const view = document.getElementById("championPageContent");
  if (!view) return;
  const c = b.champion || {};
  // 티어 필터를 걸면 픽률·밴률·순위(전체 티어 기준)는 숨기고 승률은 필터된 게임으로
  const filtered = b.tier_filter && b.tier_filter !== "ALL";
  const s = filtered ? { tier: (b.summary || {}).tier, tier_num: (b.summary || {}).tier_num, win_rate: b.win_rate } : (b.summary || {});
  const skillMap = skills && skills.skills;

  const lanes = (b.positions || []).filter(p => p.games >= CP_POS_MIN_GAMES || p.position === b.position);
  const laneBtns = lanes.map(p => `
    <button type="button" class="cp-lane ${p.position === b.position ? "active" : ""}" onclick="openChampionPage(${jsArg(c.id)}, ${jsArg(p.position)})" title="${escapeHtml(String(p.games))}게임">
      ${cpPosIcon(p.position, 24)}
    </button>`).join("");

  const tierBadge = s.tier ? `<span class="cp-tier-badge tier-${escapeHtml(String(s.tier_num ?? ""))}">${escapeHtml(String(s.tier))}</span>` : "";

  const skillRows = cpRows(b.skill_orders, o => cpSkillKeys(o.order, skillMap).join(CP_ARROW)
    + (o.first3 ? `<span class="cp-first3" title="1~3레벨 스킬 순서">${cpSkillKeys(o.first3, null).join("")}</span>` : ""));
  // 레벨별 스킬 표 (가장 많이 쓰는 마스터 순서 기준, 레벨마다 가장 많이 찍은 스킬)
  const topLevels = (b.skill_orders && b.skill_orders[0] && b.skill_orders[0].levels) || [];
  const skillGrid = topLevels.some(Boolean) ? `
    <div class="cp-skill-grid" style="grid-template-columns: 28px repeat(${topLevels.length}, minmax(0, 1fr));">
      <span></span>${topLevels.map((_, i) => `<span class="cp-sg-lv">${i + 1}</span>`).join("")}
      ${["Q", "W", "E", "R"].map(k => `
        <span class="cp-sg-key">${skillMap && skillMap[k] && skillMap[k].icon ? cpIcon(skillMap[k].icon, skillMap[k].name, 22) : `<b class="cp-skill-key key-${k.toLowerCase()}">${k}</b>`}</span>
        ${topLevels.map(v => `<span class="cp-sg-cell ${v === k ? `on key-${k.toLowerCase()}` : ""}">${v === k ? k : ""}</span>`).join("")}`).join("")}
    </div>` : "";
  const tierBtns = CP_TIER_FILTERS.map(([key, label]) => `
    <button type="button" class="cp-tier-filter ${(b.tier_filter || "ALL") === key ? "active" : ""}" onclick="cpSetTier(${jsArg(key)})">${label}</button>`).join("");
  const pp = b.prev_patch;
  const prevPatch = !filtered && pp && pp.win_rate != null && s.win_rate != null ? (() => {
    const d = Math.round((s.win_rate - pp.win_rate) * 10) / 10;
    return `<small class="cp-prev ${d > 0 ? "cp-good" : d < 0 ? "cp-bad" : ""}" title="${escapeHtml(pp.patch)} ${escapeHtml(String(pp.win_rate))}% (${escapeHtml(String(pp.games))}게임)">${d > 0 ? "▲" : d < 0 ? "▼" : ""}${Math.abs(d)}</small>`;
  })() : "";

  const body = b.total_games ? `
    <div class="cp-grid">
      <div class="cp-col">
        ${cpBlock("룬", cpRenderRuneTree(b) + cpRenderRunes(b))}
        ${cpBlock("소환사 주문", cpRows(b.spell_options, o => (o.spells || []).map(sp => cpIcon(sp.icon, sp.name, 30)).join("")))}
        ${cpBlock("시작 아이템", cpRows(b.start_items, o => cpItems(o.items)))}
        ${cpBlock("신발", cpRows(b.boots, o => cpIcon(o.icon, o.name, 30)))}
        ${cpBlock("코어 아이템", cpRows(b.core_builds, o => cpItems(o.items)))}
        ${cpBlock("구매 순서", cpRows(b.item_build_order, o => cpItems(o.items, CP_ARROW)))}
        ${(b.late_items || []).some(l => l.length) ? cpBlock("4·5·6번째 아이템", `<div class="cp-late-grid">${b.late_items.map((list, i) => `
          <div class="cp-late-col"><div class="cp-late-head">${i + 4}</div>${list.map(o => `
            <div class="cp-late-cell">${cpIcon(o.icon, o.name, 30)}<span class="${cpWrClass(o.win_rate)}">${cpPct(o.win_rate)}</span><span class="cp-mu-games">${cpNum(o.games)}</span></div>`).join("")}</div>`).join("")}</div>`, false) : ""}
        ${cpBlock("스킬", skillGrid + skillRows)}
        ${(b.popular_items || []).length ? cpBlock("많이 산 아이템", `<div class="cp-item-grid">${b.popular_items.map(o => `
          <div class="cp-item-cell">${cpIcon(o.icon, o.name, 34)}<span class="${cpWrClass(o.win_rate)}">${cpPct(o.win_rate)}</span><span class="cp-mu-games">${cpPct(o.pick_rate)}</span></div>`).join("")}</div>`, false) : ""}
      </div>
      <div class="cp-col">
        ${cpRenderPowerCurve(b.power_curve)}
        ${cpRenderCounters(b.matchups)}
        ${cpRenderSynergy(b.synergy)}
      </div>
    </div>
    <div id="championPageSkillsArea" class="cp-skills-detail"></div>` : `<div class="cp-empty-page">아직 이 챔피언의 수집된 게임이 없습니다.</div>`;

  let cleanSampleNote = "";
  if (b.sample_note) {
    const patchMatch = b.sample_note.match(/(\d+\.\d+(\.\d+)?)\s*패치/);
    const gamesMatch = b.sample_note.match(/([\d,]+)\s*게임/);
    if (patchMatch && gamesMatch) {
      cleanSampleNote = `${patchMatch[1]} 패치 · ${gamesMatch[1]}게임`;
    } else {
      cleanSampleNote = b.sample_note.replace(/수집된\s*고티어\s*솔로랭크\s*/g, '').replace(/분석\s*기준/g, '').trim();
    }
  }

  view.innerHTML = `
    <header class="cp-header">
      ${cpIcon(c.image, c.name, 72, "cp-portrait")}
      <div class="cp-head-main">
        <div class="cp-name-row">
          <h1 class="cp-name">${escapeHtml(c.name || "-")}</h1>${tierBadge}
          ${b.total_games ? `<button type="button" class="cp-tool cp-tool-copy" onclick="copyRuneAndSpellSettings()" title="룬·주문 복사"><i class="fa-solid fa-copy"></i></button>` : ""}
          ${typeof openChampionMastersDirectly === "function" ? `<button type="button" class="cp-tool" onclick="openChampionMastersDirectly(${jsArg(c.id)})" title="${escapeHtml(c.name || "")} 장인 랭킹"><i class="fa-solid fa-crown"></i></button>` : ""}
        </div>
        <div class="cp-lanes">${laneBtns}</div>
        <div class="cp-tier-filters">${tierBtns}</div>
      </div>
      <dl class="cp-head-stats">
        <div><dt>승률</dt><dd class="${cpWrClass(s.win_rate)}">${cpPct(s.win_rate)}${prevPatch}</dd></div>
        ${filtered ? "" : `<div><dt>픽률</dt><dd>${cpPct(s.pick_rate)}</dd></div>
        <div><dt>밴률</dt><dd>${cpPct(s.ban_rate)}</dd></div>`}
        ${!filtered && s.kda ? `<div><dt>KDA</dt><dd>${escapeHtml(String(s.kda))}</dd></div>` : ""}
        <div><dt>게임</dt><dd>${cpNum(b.total_games)}</dd></div>
        ${s.rank ? `<div><dt>순위</dt><dd>${escapeHtml(String(s.rank))}<small>/${escapeHtml(String(s.rank_total))}</small></dd></div>` : ""}
      </dl>
    </header>
    ${cleanSampleNote ? `<div class="cp-sample">${escapeHtml(cleanSampleNote)}</div>` : ""}
    ${body}`;

  if (skills && document.getElementById("championPageSkillsArea") && typeof renderChampionSkillsInteractive === "function") {
    renderChampionSkillsInteractive("championPageSkillsArea", skills, "Q");
  }
}

const cpSkillsCache = {};

async function openChampionPage(champId, position = null) {
  if (!champId) return;
  const view = document.getElementById("championPageContent");
  if (typeof switchMainTab === "function") switchMainTab("champion");
  window.scrollTo({ top: 0 });
  if (view && (!cpCurrent || String(cpCurrent.champion?.id).toLowerCase() !== String(champId).toLowerCase())) {
    view.innerHTML = `<div class="cp-loading"><div class="spinner"></div></div>`;
  }
  try {
    const params = new URLSearchParams();
    if (position) params.set("position", position);
    if (cpTier !== "ALL") params.set("tier", cpTier);
    const q = params.toString() ? `?${params}` : "";
    const res = await fetch(`/api/champion-build/${encodeURIComponent(champId)}${q}`);
    if (!res.ok) throw new Error(res.status === 404 ? "notfound" : "build");
    const b = await res.json();
    cpCurrent = b;
    window.currentBuildData = b;
    const id = b.champion?.id;
    if (typeof saveRecentChampion === "function" && id) {
      saveRecentChampion({ id, name: b.champion?.name || id, image: b.champion?.image });
    }
    if (id && !cpSkillsCache[id]) {
      cpSkillsCache[id] = fetch(`/api/champion-skills/${encodeURIComponent(id)}`).then(r => r.ok ? r.json() : null).catch(() => null);
    }
    const skills = id ? await cpSkillsCache[id] : null;
    if (cpCurrent !== b) return; // 그 사이 다른 챔피언을 열었으면 그리지 않는다
    cpRender(b, skills);
    document.title = `${b.champion?.name || ""} 빌드 · 룬 · 상성 - carry.gg`;
  } catch (e) {
    if (view) view.innerHTML = `<div class="cp-empty-page">
      ${e && e.message === "notfound" ? "챔피언을 찾을 수 없습니다." : "챔피언 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}
      <div style="margin-top: 12px;"><button type="button" class="btn-secondary" onclick="switchMainTab('tierlist')">챔피언 목록</button></div>
    </div>`;
  }
}
window.openChampionPage = openChampionPage;

// 티어 필터: 지금 보는 챔피언·라인 그대로 다시 불러온다
function cpSetTier(tier) {
  cpTier = tier;
  if (cpCurrent && cpCurrent.champion) openChampionPage(cpCurrent.champion.id, cpCurrent.position);
}
window.cpSetTier = cpSetTier;
// 예전 이름으로 부르는 곳(티어표·최근 챔피언·검색 등)도 페이지로 연다
window.openChampionBuildModal = (champId) => openChampionPage(champId);
