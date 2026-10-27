// Recent 20 Matches Module
async function loadPlayerRecentMatches(player) {
  const loadingEl = document.getElementById("modalMatchesLoading");
  const containerEl = document.getElementById("modalMatchesContainer");
  if (!loadingEl || !containerEl) return;

  loadingEl.style.display = "block";
  containerEl.style.display = "none";

  try {
    const encName = encodeURIComponent(player.game_name);
    const encTag = encodeURIComponent(player.tag_line);
    const matchesRes = await fetch(`/api/player/${encName}/${encTag}/matches?count=20`);

    if (!matchesRes.ok) {
      const errBody = await matchesRes.json().catch(() => ({}));
      throw new Error(errBody.detail || "매치 데이터를 가져오지 못했습니다.");
    }
    const data = await matchesRes.json();

    loadingEl.style.display = "none";
    containerEl.style.display = "block";
    renderRecentMatchesContent(data, player);
  } catch (err) {
    loadingEl.style.display = "none";
    containerEl.style.display = "block";
    containerEl.innerHTML = `
      <div style="padding: 2.5rem; text-align: center; color: #E84057;">
        <i class="fa-solid fa-circle-exclamation" style="font-size: 2rem; margin-bottom: 0.5rem; display: block;"></i>
        ${escapeHtml(err.message || "최근 매치 전적을 불러오는 중 오류가 발생했습니다.")}
      </div>
    `;
  }
}
// 🌟 Blitz / Porogg Style Interactive Rich Tooltip System (.lol-rich-tooltip)
const LOL_SPELL_DB = {
  4: { name: "점멸", cd: "300초", desc: "챔피언이 커서 방향으로 짧은 거리를 순간이동합니다. 핵심 회피 및 이니시에이팅 생존기입니다.", tag: "소환사 주문" },
  14: { name: "점화", cd: "180초", desc: "5초 동안 적 대상에게 70~410의 고정 피해를 입히고 고통스러운 상처(치유 효과 40% 감소)를 적용합니다.", tag: "소환사 주문" },
  12: { name: "순간이동", cd: "360초", desc: "4초 집중 후 아군 구조물/미니언/와드로 순간이동합니다. 10분 후 강력 순간이동으로 자동 업그레이드됩니다.", tag: "소환사 주문" },
  11: { name: "강타", cd: "90초 (최대 2충전)", desc: "정글 몬스터 또는 미니언에게 600~1200의 고정 피해를 입히며 체력을 회복합니다.", tag: "소환사 주문" },
  6: { name: "유체화", cd: "210초", desc: "15초 동안 유닛 간 충돌을 무시하며 레벨에 따라 24%~48%의 이동 속도를 얻습니다.", tag: "소환사 주문" },
  7: { name: "회복", cd: "240초", desc: "자신과 대상 아군의 체력을 80~318 즉시 회복하고 1초간 이동 속도 +30%를 부여합니다.", tag: "소환사 주문" },
  3: { name: "탈진", cd: "210초", desc: "3초 동안 대상 적의 이동 속도를 35% 늦추고 해당 챔피언이 입히는 피해량을 35% 감소시킵니다.", tag: "소환사 주문" },
  21: { name: "방어막", cd: "180초", desc: "2.5초 동안 105~411의 피해를 흡수하는 방어막을 획득합니다.", tag: "소환사 주문" },
  1: { name: "정화", cd: "210초", desc: "자신에게 걸린 모든 군중 제어 효과(제압/에어본 제외)를 즉시 제거하고 강인함을 대폭 증가시킵니다.", tag: "소환사 주문" }
};

const LOL_KEYSTONE_DB = {
  8010: { name: "정복자", style: "정밀", desc: "적 공격 시 6초간 적응형 능력치 중첩 획득 (최대 12회). 최대 중첩 시 입힌 피해의 8% 체력 회복.", tag: "핵심 룬" },
  8008: { name: "치명적 속도", style: "정밀", desc: "적 공격 시 공격 속도 중첩 획득 (최대 6회). 최대 중첩 시 공속 한계 해제 및 추가 적중 마법 피해.", tag: "핵심 룬" },
  8005: { name: "집중 공격", style: "정밀", desc: "동일 적에게 평타 3회 연속 적중 시 추가 적응형 피해를 입히고 대상 취약 상태 돌입 (받는 피해 +8%).", tag: "핵심 룬" },
  8021: { name: "기민한 발놀림", style: "정밀", desc: "이동 및 공격으로 충전. 100 충전 시 평타 공격으로 체력 회복 및 1초간 이동 속도 +20%.", tag: "핵심 룬" },
  8112: { name: "감전", style: "지배", desc: "3초 동안 개별 공격/스킬 3회 적중 시 대상에게 번개가 내리쳐 폭발적인 추가 적응형 피해를 입힙니다.", tag: "핵심 룬" },
  8128: { name: "어둠의 수확", style: "지배", desc: "체력 50% 미만 적에게 피해 시 적응형 피해 및 영혼 수확. (킬 관여 시 쿨다운 1.5초 초기화)", tag: "핵심 룬" },
  9923: { name: "칼날비", style: "지배", desc: "적 챔피언 공격 시 다음 기본 공격 3회의 공격 속도가 110%~160% 폭발적으로 증가합니다.", tag: "핵심 룬" },
  8214: { name: "콩콩이 소환", style: "마법", desc: "적 공격 시 콩콩이가 날아가 피해를 입히거나, 아군에게 스킬 시전 시 보호막을 부여합니다.", tag: "핵심 룬" },
  8229: { name: "신비로운 유성", style: "마법", desc: "적에게 스킬 적중 시 해당 위치로 유성을 떨어뜨려 광역 적응형 피해를 입힙니다.", tag: "핵심 룬" },
  8230: { name: "난입", style: "마법", desc: "4초 안에 개별 공격/스킬 3회 적중 시 폭발적인 이동 속도(근접 30~60%) 및 둔화 저항력 75% 획득.", tag: "핵심 룬" },
  8437: { name: "착취의 손아귀", style: "결의", desc: "전투 4초마다 다음 평타 강화: 추가 마법 피해 + 체력 회복 + 영구 최대 체력 증가(+7, 원거리 +4).", tag: "핵심 룬" },
  8439: { name: "여진", style: "결의", desc: "적 챔피언 이동 불가 시 방어력/마법 저항력 급증 후 폭발하여 광역 마법 피해를 입힙니다.", tag: "핵심 룬" },
  8465: { name: "수호자", style: "결의", desc: "자신 또는 대상 아군이 큰 피해를 입으면 두 챔피언 모두에게 보호막 및 이동 속도를 부여합니다.", tag: "핵심 룬" },
  8351: { name: "빙결 강화", style: "영감", desc: "적을 이동 불가 상태로 만들면 결빙 광선 3줄기가 뻗어나와 지대를 얼리고 적의 피해량을 감소시킵니다.", tag: "핵심 룬" },
  8369: { name: "선제공격", style: "영감", desc: "적과 교전 개시 시 선공권을 잡으면 3초 동안 9% 추가 피해 및 피해량 비례 골드를 획득합니다.", tag: "핵심 룬" },
  8360: { name: "봉인 풀린 주문서", style: "영감", desc: "비전투 상태에서 소환사 주문을 다른 주문으로 1회성 교체 가능. 다양한 교체 시 쿨다운 감소.", tag: "핵심 룬" }
};

const LOL_ITEM_DB = {
  3078: { name: "삼위일체", type: "전설급 아이템", stats: "공격력 +45, 공격 속도 +33%, 체력 +300, 스킬 가속 +20", passive: "스킬 사용 후 다음 기본 공격 시 기본 공격력의 200% 추가 물리 피해 (주문 검)" },
  3031: { name: "무한의 대검", type: "전설급 아이템", stats: "공격력 +80, 치명타 확률 +25%", passive: "치명타 피해량이 40% 증가합니다." },
  3089: { name: "라바돈의 죽음모자", type: "전설급 아이템", stats: "주문력 +140", passive: "총 주문력이 35% 증가합니다." },
  3157: { name: "존야의 모래시계", type: "전설급 아이템", stats: "주문력 +120, 방어력 +50", passive: "사용 시 2.5초 동안 무적 및 대상 지정 불가 상태가 됩니다. (경직)" },
  3026: { name: "수호 천사", type: "전설급 아이템", stats: "공격력 +55, 방어력 +45", passive: "치명적인 피해를 입으면 4초 후 기본 체력 50% 및 마나 30%를 회복하며 부활합니다." },
  3153: { name: "몰락한 왕의 검", type: "전설급 아이템", stats: "공격력 +50, 공격 속도 +25%, 생명력 흡수 +10%", passive: "기본 공격 시 대상 현재 체력의 9%(원거리 6%) 추가 물리 피해 & 3타 적중 시 이동 속도 흡수" },
  3074: { name: "굶주린 히드라", type: "전설급 아이템", stats: "공격력 +70, 생명력 흡수 +12%, 스킬 가속 +20", passive: "기본 공격과 스킬이 주변 적에게 광역 물리 피해를 입힙니다. 사용 시 즉시 광역 베기 피해." },
  3004: { name: "마나무네", type: "전설급 아이템", stats: "공격력 +35, 최대 마나 +500, 스킬 가속 +15", passive: "최대 마나에 비례하여 공격력이 증가합니다. 최대 중첩 시 무라마나로 진화합니다." },
  3072: { name: "피바라기", type: "전설급 아이템", stats: "공격력 +80, 치명타 확률 +25%, 생명력 흡수 +18%", passive: "체력이 70% 이상일 때 공격력이 증가하며 초과 치유량이 보호막으로 전환됩니다." },
  3142: { name: "요우무의 유령검", type: "전설급 아이템", stats: "공격력 +60, 물리 관통력 +18, 비전투 이속 +40", passive: "사용 시 6초 동안 이동 속도가 20% 증가하며 유체화 효과를 얻습니다." },
  3139: { name: "헤르메스의 시밀러", type: "전설급 아이템", stats: "공격력 +40, 마법 저항력 +50, 치명타 확률 +20%", passive: "사용 시 자신에게 걸린 모든 군중 제어 효과를 즉시 해제하고 이동 속도가 증가합니다." },
  3110: { name: "얼어붙은 심장", type: "전설급 아이템", stats: "방어력 +65, 마나 +400, 스킬 가속 +20", passive: "기본 공격 피해 감소 & 주변 적의 공격 속도를 20% 감소시킵니다." },
  3065: { name: "정령의 형상", type: "전설급 아이템", stats: "체력 +400, 마법 저항력 +60, 스킬 가속 +10, 체력 재생 +100%", passive: "자신이 받는 모든 체력 회복 및 보호막 효과가 25% 증가합니다." },
  3083: { name: "워모그의 갑옷", type: "전설급 아이템", stats: "체력 +1000, 체력 재생 +100%, 이동 속도 +5%", passive: "최대 체력 조건을 만족하면 비전투 시 매초 최대 체력의 5%를 빠르게 재생합니다." },
  3020: { name: "마법사의 신발", type: "장화", stats: "마법 관통력 +18, 이동 속도 +45", passive: "마법 공격 딜러를 위한 핵심 마법 관통력 신발" },
  3006: { name: "광전사의 군화", type: "장화", stats: "공격 속도 +35%, 이동 속도 +45", passive: "원거리 딜러 및 공속 기반 브루저를 위한 신발" },
  3047: { name: "판금 장화", type: "장화", stats: "방어력 +20, 이동 속도 +45", passive: "적의 기본 공격으로 받는 피해량이 12% 감소합니다." },
  3111: { name: "헤르메스의 발걸음", type: "장화", stats: "마법 저항력 +25, 이동 속도 +45", passive: "기절, 둔화, 도발 등의 군중 제어 지속 시간을 30% 줄여줍니다 (강인함)." },
  3158: { name: "명석함의 아이오니아 장화", type: "장화", stats: "스킬 가속 +15, 소환사 주문 가속 +12, 이동 속도 +45", passive: "스킬과 소환사 주문의 쿨다운을 빠르게 회전시킵니다." },
  6673: { name: "불멸의 철갑궁", type: "전설급 아이템", stats: "공격력 +55, 치명타 확률 +25%", passive: "체력이 30% 이하로 떨어지면 3초 동안 피해를 흡수하는 보호막을 얻습니다 (생명선)." },
  6672: { name: "크라켄 학살자", type: "전설급 아이템", stats: "공격력 +50, 공격 속도 +40%, 이동 속도 +7%", passive: "3번째 기본 공격마다 추가 적응형 물리 피해를 입힙니다." },
  6671: { name: "돌풍", type: "전설급 아이템", stats: "공격력 +55, 공격 속도 +15%, 치명타 확률 +20%", passive: "사용 시 지정 방향으로 돌진하며 체력이 가장 낮은 적에게 미사일을 발사합니다." },
  3115: { name: "내셔의 이빨", type: "전설급 아이템", stats: "주문력 +90, 공격 속도 +50%, 스킬 가속 +15", passive: "기본 공격 적중 시 15(+20% AP)의 추가 마법 피해를 입힙니다." },
  3046: { name: "유령 무희", type: "전설급 아이템", stats: "공격 속도 +60%, 치명타 확률 +25%, 이동 속도 +12%", passive: "유체화 상태가 되며 적을 카이팅하기에 최적화된 능력치를 부여합니다." },
  3094: { name: "고속 연사포", type: "전설급 아이템", stats: "공격력 +35, 공격 속도 +35%, 치명타 확률 +25%", passive: "충전 시 다음 기본 공격의 사거리가 35% (최대 +150) 증가합니다." },
  3036: { name: "도미닉 경의 인사", type: "전설급 아이템", stats: "공격력 +45, 치명타 확률 +25%, 방어구 관통력 +40%", passive: "탱커 및 방어력이 높은 챔피언을 관통하는 최강의 안티탱커 아이템" },
  3033: { name: "필멸자의 운명", type: "전설급 아이템", stats: "공격력 +45, 치명타 확률 +25%, 방어구 관통력 +35%", passive: "물리 피해를 입히면 적에게 3초 동안 40% 고통스러운 상처(치유 감소)를 부여합니다." },
  3165: { name: "모렐로노미콘", type: "전설급 아이템", stats: "주문력 +90, 마법 관통력 +15, 스킬 가속 +15", passive: "마법 피해를 입히면 적에게 3초 동안 40% 고통스러운 상처(치유 감소)를 부여합니다." },
  3041: { name: "메자의 영혼약탈자", type: "전설급 아이템", stats: "주문력 +20, 체력 +100", passive: "킬 관여 시 영광 중첩을 얻어 주문력과 이속이 대폭 상승합니다 (데스 시 10중첩 손실)." },
  4637: { name: "균열 생성기", type: "전설급 아이템", stats: "주문력 +80, 체력 +350, 스킬 가속 +15", passive: "전투 지속 시 피해량이 증가하고 모든 피해 흡혈(10%)을 획득합니다." },
  3340: { name: "투명 와드", type: "장신구", stats: "쿨다운 240~120초", passive: "지정 위치에 90~120초간 시야를 밝혀주는 투명 와드를 설치합니다." },
  3364: { name: "예언자의 렌즈", type: "장신구", stats: "쿨다운 90~60초", passive: "6초간 주변의 투명 와드, 은신 함정, 은신 챔피언을 감지하고 와드를 무력화합니다." },
  2055: { name: "제어 와드", type: "소비 용품", stats: "최대 소지 2개", passive: "설치 위치 주변의 적 투명 와드 및 함정을 감지하고 무력화하는 제어 와드를 설치합니다 (체력 4)." },
  2031: { name: "충전형 물약", type: "소비 용품", stats: "최대 2충전", passive: "12초에 걸쳐 체력 100을 회복합니다. 상점 방문 시 자동으로 재충전됩니다." },
  2033: { name: "부패 물약", type: "소비 용품", stats: "최대 3충전", passive: "체력과 마나를 회복하며 공격 시 대상에게 부패 피해를 적용합니다." }
};

let lolTooltipEl = null;

function ensureLolRichTooltip() {
  if (lolTooltipEl && document.body.contains(lolTooltipEl)) return lolTooltipEl;
  let tip = document.getElementById("lolRichTooltip");
  if (!tip) {
    tip = document.createElement("div");
    tip.id = "lolRichTooltip";
    tip.className = "lol-rich-tooltip";
    tip.style.display = "none";
    document.body.appendChild(tip);
  }
  lolTooltipEl = tip;
  return lolTooltipEl;
}

function showRichTooltip(e, type, id, name, iconSrc) {
  const tip = ensureLolRichTooltip();
  let title = name || "정보";
  let subText = "";
  let bodyStats = "";
  let bodyDesc = "";
  let tag = "정보";
  let icon = iconSrc || "";

  const numId = parseInt(id, 10);

  if (type === "spell") {
    const sp = LOL_SPELL_DB[numId] || Object.values(LOL_SPELL_DB).find(x => x.name === name);
    title = sp ? sp.name : (name || "소환사 주문");
    subText = sp ? `쿨다운 ${sp.cd}` : "소환사 주문";
    bodyDesc = sp ? sp.desc : "전장에서 즉각적인 전술적 이점을 제공하는 소환사 주문입니다.";
    tag = "소환사 주문";
  } else if (type === "rune") {
    const rn = LOL_KEYSTONE_DB[numId] || Object.values(LOL_KEYSTONE_DB).find(x => x.name === name);
    title = rn ? rn.name : (name || "핵심 룬");
    subText = rn ? `${rn.style} 계열` : "빌드 핵심 룬";
    bodyDesc = rn ? rn.desc : "챔피언의 플레이스타일과 전투 메커니즘을 결정짓는 핵심 룬입니다.";
    tag = "핵심 룬";
  } else if (type === "item") {
    const it = LOL_ITEM_DB[numId];
    title = it ? it.name : (name ? `${name}` : `아이템`);
    subText = it ? it.type : "완성 아이템";
    bodyStats = it ? it.stats : "";
    bodyDesc = it ? it.passive : "챔피언의 능력치와 전술적 잠재력을 극대화하는 아이템입니다.";
    tag = "아이템";
  }

  tip.innerHTML = `
    <div class="lrt-header">
      ${icon ? `<img class="lrt-icon" src="${icon}" alt="${escapeHtml(title)}" onerror="this.style.display='none'">` : ''}
      <div class="lrt-title-wrap">
        <div class="lrt-name">${escapeHtml(title)}</div>
        ${subText ? `<div class="lrt-sub-badge">${escapeHtml(subText)}</div>` : ''}
      </div>
    </div>
    <div class="lrt-body">
      ${bodyStats ? `<div class="lrt-stats">${escapeHtml(bodyStats)}</div>` : ''}
      <div class="lrt-desc">${escapeHtml(bodyDesc)}</div>
    </div>
    <div class="lrt-footer">
      <span class="lrt-tag"><i class="fa-solid fa-sparkles" style="color: #C89B3C;"></i> ${escapeHtml(tag)}</span>
    </div>
  `;

  tip.style.display = "block";
  tip.classList.add("visible");
  updateRichTooltipPosition(e);
}

function updateRichTooltipPosition(e) {
  if (!lolTooltipEl || lolTooltipEl.style.display === "none") return;
  const padding = 14;
  const rect = lolTooltipEl.getBoundingClientRect();
  const tipWidth = rect.width || 270;
  const tipHeight = rect.height || 130;

  let left = e.clientX + padding;
  let top = e.clientY + padding;

  if (left + tipWidth > window.innerWidth - 12) {
    left = e.clientX - tipWidth - padding;
  }
  if (top + tipHeight > window.innerHeight - 12) {
    top = e.clientY - tipHeight - padding;
  }

  left = Math.max(10, left);
  top = Math.max(10, top);

  lolTooltipEl.style.left = `${left}px`;
  lolTooltipEl.style.top = `${top}px`;
}

function hideRichTooltip() {
  if (!lolTooltipEl) return;
  lolTooltipEl.classList.remove("visible");
  lolTooltipEl.style.display = "none";
}

function attachRichTooltips(container) {
  if (!container) return;
  const targets = container.querySelectorAll("[data-lol-tooltip]");
  targets.forEach(el => {
    if (el.hasAttribute("title") && el.getAttribute("title")) {
      el.setAttribute("data-stored-title", el.getAttribute("title"));
      el.removeAttribute("title");
    }

    el.addEventListener("mouseenter", (e) => {
      const type = el.getAttribute("data-tooltip-type") || "item";
      const id = el.getAttribute("data-tooltip-id") || "";
      const name = el.getAttribute("data-tooltip-name") || el.getAttribute("data-stored-title") || "";
      const img = el.querySelector("img");
      const iconSrc = img ? img.getAttribute("src") : (el.tagName === "IMG" ? el.getAttribute("src") : "");
      showRichTooltip(e, type, id, name, iconSrc);
    });

    el.addEventListener("mousemove", (e) => {
      updateRichTooltipPosition(e);
    });

    el.addEventListener("mouseleave", () => {
      hideRichTooltip();
    });
  });
}

function renderRecentMatchesContent(data, mePlayer) {
  const containerEl = document.getElementById("modalMatchesContainer");
  if (!containerEl) return;

  const matches = data.matches || [];

  // Empty State Guard (FR-01 & Design Spec 4.2): 랭크 매치 기록 없음 안내
  if (!matches || matches.length === 0) {
    containerEl.innerHTML = `
      <div class="empty-state-card hextech-empty-state" style="padding: 3.5rem 2rem; text-align: center; margin: 1.5rem 0;">
        <div style="font-size: 3rem; margin-bottom: 0.8rem; color: var(--color-gold);">🧭</div>
        <h3 style="font-size: 1.3rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.6rem;">최근 랭크 기록 없음</h3>
        <p style="font-size: 0.95rem; color: var(--text-secondary); max-width: 460px; margin: 0 auto 1.5rem; line-height: 1.6;">
          라이엇 API에서 확인되는 최근 경기 기록이 없습니다.
        </p>
      </div>
    `;
    return;
  }

  const summary = data.summary || {};

  const totalWins = summary.wins !== undefined ? summary.wins : (summary.total_wins !== undefined ? summary.total_wins : matches.filter(m => m.win).length);
  const totalLosses = summary.losses !== undefined ? summary.losses : (summary.total_losses !== undefined ? summary.total_losses : matches.filter(m => !m.win).length);
  const totalGames = summary.total_games || (totalWins + totalLosses) || matches.length || 20;
  const winRate = summary.win_rate !== undefined ? summary.win_rate : (totalGames > 0 ? Math.round((totalWins / totalGames) * 100) : 50);

  const avgKills = summary.avg_kills !== undefined ? summary.avg_kills : (matches.length > 0 ? (matches.reduce((a, m) => a + (m.kills || 0), 0) / matches.length).toFixed(1) : "0.0");
  const avgDeaths = summary.avg_deaths !== undefined ? summary.avg_deaths : (matches.length > 0 ? (matches.reduce((a, m) => a + (m.deaths || 0), 0) / matches.length).toFixed(1) : "0.0");
  const avgAssists = summary.avg_assists !== undefined ? summary.avg_assists : (matches.length > 0 ? (matches.reduce((a, m) => a + (m.assists || 0), 0) / matches.length).toFixed(1) : "0.0");
  const avgKda = summary.avg_kda !== undefined ? summary.avg_kda : (parseFloat(avgDeaths) > 0 ? ((parseFloat(avgKills) + parseFloat(avgAssists)) / parseFloat(avgDeaths)).toFixed(2) : "Perfect");

  const numKda = avgKda === "Perfect" ? 99.0 : (parseFloat(avgKda) || 0);
  const kdaColor = numKda >= 5.0 ? "#F59E0B" : (numKda >= 4.0 ? "#10B981" : (numKda >= 3.0 ? "#3B82F6" : "var(--text-heading)"));

  // KP % (Kill Participation)
  // 평균 시야 점수: 다시하기 제외, 내 행(is_me)의 vision_score
  const visionVals = matches.filter(m => !m.is_remake)
    .map(m => ((m.team1 || []).concat(m.team2 || []).find(x => x.is_me) || {}).vision_score)
    .filter(v => typeof v === "number");
  const avgVision = visionVals.length ? (visionVals.reduce((a, b) => a + b, 0) / visionVals.length).toFixed(1) : null;
  const avgKp = matches.length > 0
    ? Math.round(matches.reduce((acc, m) => acc + (m.kill_participation || 0), 0) / matches.length)
    : (summary.kill_participation || 52);

  // TOP 3 Most Played Champions
  const rawChamps = summary.most_champions || summary.fav_champions || [];
  let mostChamps = rawChamps;
  if (!mostChamps || mostChamps.length === 0) {
    const champMap = {};
    matches.forEach(m => {
      const cId = m.champ_name || m.champion?.name || "챔피언";
      const cImg = m.champ_img || m.champion?.image || "";
      if (!champMap[cId]) {
        champMap[cId] = { id: cId, name: cId, image: cImg, games: 0, wins: 0, kills: 0, deaths: 0, assists: 0 };
      }
      champMap[cId].games++;
      if (m.win) champMap[cId].wins++;
      champMap[cId].kills += m.kills || 0;
      champMap[cId].deaths += m.deaths || 0;
      champMap[cId].assists += m.assists || 0;
    });
    mostChamps = Object.values(champMap).sort((a, b) => b.games - a.games).slice(0, 3).map(c => {
      c.win_rate = Math.round((c.wins / c.games) * 100);
      c.kda = c.deaths > 0 ? ((c.kills + c.assists) / c.deaths).toFixed(2) : "Perfect";
      return c;
    });
  } else {
    mostChamps = mostChamps.slice(0, 3);
  }

  // Preferred Positions (TOP, JUG, MID, BOT, SUP)
  const positions = summary.positions || {};
  const posLabels = { TOP: "탑", JUG: "정글", MID: "미드", BOT: "원딜", SUP: "서폿" };

  const totalWrColor = winRate > 50 ? "#10B981" : "#E84057";

  // Summary HTML (OP.GG / FOW.KR Style Rich Widget)
  let summaryHtml = `
    <div class="opgg-recent20-summary-widget">
      <div class="summary-section summary-record-section">
        <div class="summary-widget-title"><i class="fa-solid fa-chart-pie" style="color: #3B82F6;"></i> 최근 20전</div>
        <div class="summary-record-flex">
          <div class="donut-chart-container">
            <svg class="donut-svg" viewBox="0 0 36 36">
              <path class="donut-circle-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              <path class="donut-circle-fill" stroke="${totalWrColor}" stroke-dasharray="${winRate}, 100" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              <text x="18" y="21" class="donut-text" fill="${totalWrColor}">${winRate}%</text>
            </svg>
          </div>
          <div class="record-text-group">
            <div class="record-counts">
              <span class="record-wins">${totalWins}승</span>
              <span class="record-losses">${totalLosses}패</span>
            </div>
            <div class="record-mini-bar">
              <div class="mini-bar-win" style="width: ${winRate}%; background: ${totalWrColor};"></div>
              <div class="mini-bar-loss" style="width: ${100 - winRate}%;"></div>
            </div>
          </div>
        </div>
      </div>

      <div class="summary-section summary-kda-section">
        <div class="summary-widget-title"><i class="fa-solid fa-bullseye" style="color: #10B981;"></i> 평균 KDA</div>
        <div class="kda-score-box">
          <span class="kda-ratio-highlight" style="color: ${kdaColor};">${avgKda}:1</span>
        </div>
        <div class="kda-numbers-row">
          <span class="kda-k">${avgKills}</span> / <span class="kda-d">${avgDeaths}</span> / <span class="kda-a">${avgAssists}</span>
        </div>
        <div class="kda-kp-row">
          <span class="kp-badge" title="최근 20경기 평균 킬관여율"><i class="fa-solid fa-crosshairs"></i> 킬관여 <strong>${avgKp}%</strong></span>
          ${avgVision !== null ? `<span class="kp-badge" title="평균 시야 점수"><i class="fa-solid fa-eye"></i> 시야 <strong>${avgVision}</strong></span>` : ""}
        </div>
      </div>

      <div class="summary-section summary-roles-section">
        <div class="summary-widget-title"><i class="fa-solid fa-compass" style="color: #8B5CF6;"></i> 선호 포지션</div>
        <div class="roles-bars-list">
          ${Object.keys(positions).length > 0 ? Object.entries(positions).map(([role, cnt]) => {
            const rName = posLabels[role] || role;
            const rPct = Math.round((cnt / (totalGames || 20)) * 100);
            return `
              <div class="role-bar-item">
                <span class="role-bar-name">${rName}</span>
                <div class="role-bar-track">
                  <div class="role-bar-fill" style="width: ${rPct}%;"></div>
                </div>
                <span class="role-bar-pct">${rPct}%</span>
              </div>
            `;
          }).join('') : '<div style="font-size: 0.75rem; color: var(--text-muted); padding: 0.5rem 0;">포지션 분석 중...</div>'}
        </div>
      </div>
      ${(summary.played_with || []).length > 0 ? `
      <div class="summary-section summary-mates-section">
        <div class="summary-widget-title"><i class="fa-solid fa-user-group" style="color: #06B6D4;"></i> 함께한 소환사</div>
        <div style="display: flex; flex-direction: column; gap: 4px; font-size: 0.78rem;">
          ${summary.played_with.map(p => `
            <div class="summary-mates-row" style="display: flex; align-items: center; gap: 8px; cursor: pointer;" onclick="openPlayerDetail({game_name: ${jsArg(p.game_name)}, tag_line: ${jsArg(p.tag_line)}})">
              <span style="font-weight: 700; color: var(--text-heading); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px;">${escapeHtml(p.game_name)}<span style="color: var(--text-muted); font-weight: 400;">#${escapeHtml(p.tag_line)}</span></span>
              <span style="margin-left: auto; color: var(--text-muted); white-space: nowrap;">${escapeHtml(String(p.games))}판 ${escapeHtml(String(p.wins))}승 ${escapeHtml(String(p.losses))}패</span>
              <span style="font-weight: 800; color: ${p.win_rate > 50 ? '#10B981' : '#E84057'}; white-space: nowrap;">${escapeHtml(String(p.win_rate))}%</span>
            </div>`).join('')}
        </div>
      </div>` : ''}
    </div>
  `;
  // 🌟 OP.GG Signature: Most Champions 7-Day Ranking List (.opgg-most-champs-widget)
  const allChampMap = {};
  matches.forEach(m => {
    const cId = m.champ_name || m.champion?.name || "챔피언";
    const cImg = normalizeChampionImgUrl(m.champ_img || m.champion?.image || cId);
    if (!allChampMap[cId]) {
      allChampMap[cId] = {
        name: cId,
        image: cImg,
        games: 0,
        wins: 0,
        losses: 0,
        kills: 0,
        deaths: 0,
        assists: 0,
        csTotal: 0,
        csPerMinSum: 0
      };
    }
    allChampMap[cId].games++;
    if (m.win) allChampMap[cId].wins++;
    else allChampMap[cId].losses++;
    allChampMap[cId].kills += (m.kills || 0);
    allChampMap[cId].deaths += (m.deaths || 0);
    allChampMap[cId].assists += (m.assists || 0);

    const csVal = typeof m.cs === 'object' && m.cs !== null ? (m.cs.total || 0) : (Number(m.cs) || 0);
    allChampMap[cId].csTotal += csVal;
    const csMin = typeof m.cs === 'object' && m.cs !== null ? (m.cs.per_min || 0) : (Number(m.cs_per_min) || (m.duration_sec ? (csVal / (m.duration_sec / 60)) : 7.2));
    allChampMap[cId].csPerMinSum += (Number(csMin) || 7.2);
  });

  const rankedChamps = Object.values(allChampMap).sort((a, b) => {
    if (b.games !== a.games) return b.games - a.games;
    return (b.wins / b.games) - (a.wins / a.games);
  });
  // 🌟 최근 20게임 KDA 변동 트렌드 인터랙티브 SVG 그래프 & 모스트 챔피언 승률 차트 대시보드
  let trendDashboardHtml = '';
  if (matches && matches.length > 0) {
    const chronologicalMatches = [...matches].reverse();
    const totalChron = chronologicalMatches.length;

    const svgWidth = 520;
    const svgHeight = 160;
    const paddingX = 35;
    const paddingTop = 25;
    const paddingBottom = 30;
    const innerW = svgWidth - paddingX * 2;
    const innerH = svgHeight - paddingTop - paddingBottom;

    const pointsData = chronologicalMatches.map((m, idx) => {
      const d = m.deaths || 0;
      const k = m.kills || 0;
      const a = m.assists || 0;
      const kdaVal = d > 0 ? (k + a) / d : (k + a > 0 ? 10.0 : 3.0);
      const isWin = Boolean(m.win);
      const champ = m.champ_name || m.champion?.name || "챔피언";
      return {
        idx: idx + 1,
        kda: parseFloat(kdaVal.toFixed(2)),
        k, d, a,
        win: isWin,
        champ
      };
    });

    const maxKda = Math.max(8.0, ...pointsData.map(p => p.kda));
    const kdaScaleMax = Math.ceil(maxKda) + 1;

    const getX = (idx) => totalChron === 1 ? svgWidth / 2 : paddingX + ((idx - 1) / (totalChron - 1)) * innerW;
    const getY = (val) => paddingTop + innerH - (Math.min(val, kdaScaleMax) / kdaScaleMax) * innerH;

    const avgKdaNum = parseFloat(avgKda) || 3.0;
    const avgY = getY(avgKdaNum);

    const polylinePoints = pointsData.map(p => `${getX(p.idx)},${getY(p.kda)}`).join(" ");
    const firstX = getX(1);
    const lastX = getX(totalChron);
    const bottomY = paddingTop + innerH;
    const areaPoints = `${firstX},${bottomY} ${polylinePoints} ${lastX},${bottomY}`;

    const svgChartHtml = `
      <svg class="kda-svg-chart" viewBox="0 0 ${svgWidth} ${svgHeight}" preserveAspectRatio="none">
        <defs>
          <linearGradient id="kdaAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#3B82F6" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#3B82F6" stop-opacity="0.0"/>
          </linearGradient>
        </defs>
        <line class="kda-chart-axis-line" x1="${paddingX}" y1="${bottomY}" x2="${svgWidth - paddingX}" y2="${bottomY}" stroke="currentColor" stroke-width="1"/>
        <line class="kda-avg-line" x1="${paddingX}" y1="${avgY}" x2="${svgWidth - paddingX}" y2="${avgY}" stroke-dasharray="4,4" stroke-width="1.5" stroke-opacity="0.85"/>
        <text class="kda-avg-text" x="${paddingX + 6}" y="${Math.max(16, avgY - 6)}" font-size="9.5" text-anchor="start" font-weight="800">평균 ${avgKdaNum.toFixed(2)}</text>
        <polygon class="kda-area-polygon" points="${areaPoints}" fill="url(#kdaAreaGrad)"/>
        <polyline class="kda-chart-polyline" points="${polylinePoints}" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
        ${pointsData.map(p => {
          const cx = getX(p.idx);
          const cy = getY(p.kda);
          const dotColor = p.win ? "#3B82F6" : "#EF4444";
          const safeChamp = typeof escapeHtml === "function" ? escapeHtml(p.champ) : p.champ;
          const titleText = `${p.idx}번째 경기 (${safeChamp}) - ${p.win ? '승리' : '패배'} | KDA: ${p.kda}:1 (${p.k}/${p.d}/${p.a})`;
          return `
            <circle class="kda-point-dot" cx="${cx}" cy="${cy}" r="4.5" fill="${dotColor}">
              <title>${titleText}</title>
            </circle>
          `;
        }).join('')}
      </svg>
    `;

    trendDashboardHtml = `
      <div class="opgg-kda-trend-dashboard">
        <div class="kda-trend-graph-card">
          <div class="trend-card-header">
            <div class="trend-card-title">
              <i class="fa-solid fa-chart-line" style="color: #60A5FA;"></i> KDA 추이
            </div>
          </div>
          <div class="kda-svg-wrapper">
            ${svgChartHtml}
          </div>
          <div class="kda-chart-legend">
            <div class="kda-legend-item"><span class="kda-legend-dot win"></span> 승</div>
            <div class="kda-legend-item"><span class="kda-legend-dot loss"></span> 패</div>
            <div class="kda-legend-item"><span class="kda-legend-dot avg"></span> 평균</div>
          </div>
        </div>

      </div>
    `;
  }

  let mostChampsWidgetHtml = '';
  if (rankedChamps.length > 0) {
    mostChampsWidgetHtml = `
      <div class="opgg-most-champs-widget">
        <div class="most-champs-header">
          <div class="most-champs-title">
            <i class="fa-solid fa-crown" style="color: #F59E0B;"></i> 챔피언
          </div>
        </div>
        <div class="most-champs-table-wrap">
          <table class="most-champs-table">
            <thead>
              <tr>
                <th class="col-champ">챔피언</th>
                <th class="col-wr">승률</th>
                <th class="col-kda">KDA</th>
                <th class="col-cs">CS</th>
              </tr>
            </thead>
            <tbody>
              ${rankedChamps.slice(0, 6).map((c, rIdx) => {
                const wr = Math.round((c.wins / c.games) * 100);
                const avgK = (c.kills / c.games).toFixed(1);
                const avgD = (c.deaths / c.games).toFixed(1);
                const avgA = (c.assists / c.games).toFixed(1);
                const kRatio = c.deaths > 0 ? ((c.kills + c.assists) / c.deaths).toFixed(2) : "Perfect";
                const numKRatio = kRatio === "Perfect" ? 99 : parseFloat(kRatio);
                const avgCs = Math.round(c.csTotal / c.games);
                const avgCsMin = (c.csPerMinSum / c.games).toFixed(1);

                let kdaBadgeCls = "normal";
                let kdaColor = "var(--text-heading)";
                if (numKRatio >= 5.0) {
                  kdaBadgeCls = "gold";
                  kdaColor = "#F59E0B";
                } else if (numKRatio >= 4.0) {
                  kdaBadgeCls = "green";
                  kdaColor = "#10B981";
                } else if (numKRatio >= 3.0) {
                  kdaBadgeCls = "blue";
                  kdaColor = "#3B82F6";
                }

                const wrColor = wr > 50 ? "#10B981" : "#E84057";

                return `
                  <tr class="most-champ-row">
                    <td class="col-champ">
                      <div class="mcc-champ-col">
                        <div class="mcc-rank-num">${rIdx + 1}</div>
                        <img class="mcc-champ-img" src="${c.image}" alt="${c.name}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
                        <div class="mcc-champ-name-wrap">
                          <span class="mcc-champ-name">${c.name}</span>
                          <span class="mcc-champ-play-games">${c.games}게임</span>
                        </div>
                      </div>
                    </td>
                    <td class="col-wr">
                      <div class="mcc-winrate-col">
                        <div class="mcc-wr-text-row">
                          <strong class="mcc-wr-pct" style="color: ${wrColor};">${wr}%</strong>
                          <span class="mcc-record-text">${c.wins}승 ${c.losses}패</span>
                        </div>
                        <div class="mcc-wr-bar-track">
                          <div class="mcc-wr-bar-fill" style="width: ${wr}%; background: ${wrColor};"></div>
                        </div>
                      </div>
                    </td>
                    <td class="col-kda">
                      <div class="mcc-kda-col">
                        <div class="mcc-kda-score-row">
                          <strong class="mcc-kda-ratio" style="color: ${kdaColor};">${kRatio === 'Perfect' ? 'Perfect' : `${kRatio}:1`}</strong>
                        </div>
                        <div class="mcc-kda-kda-row">
                          <span>${avgK}</span> / <span style="color: #EF4444;">${avgD}</span> / <span>${avgA}</span>
                        </div>
                      </div>
                    </td>
                    <td class="col-cs">
                      <div class="mcc-cs-col">
                        <div class="mcc-cs-main">CS <strong>${avgCs}</strong></div>
                        <div class="mcc-cs-sub">(${avgCsMin})</div>
                      </div>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // Queue classification helper
  const getQueueGroup = (mode) => {
    const s = String(mode || '').toLowerCase();
    if (s.includes('솔로') || s.includes('솔랭') || s.includes('solo') || s.includes('개인')) return 'solo';
    if (s.includes('자유') || s.includes('자랭') || s.includes('flex')) return 'flex';
    if (s.includes('칼바람') || s.includes('총력') || s.includes('aram') || s.includes('무작위')) return 'aram';
    return 'other';
  };

  const queueCounts = { all: matches.length, solo: 0, flex: 0, aram: 0 };
  matches.forEach(m => {
    const qg = getQueueGroup(m.game_mode);
    if (queueCounts[qg] !== undefined) queueCounts[qg]++;
  });

  // OP.GG Style Queue Filter Tab Bar HTML
  const filterBarHtml = `
    <div class="match-queue-filter-bar">
      <div class="queue-filter-btns" role="tablist" aria-label="큐 타입 필터">
        <button type="button" class="queue-filter-btn active" data-queue="all">전체 (${queueCounts.all})</button>
        <button type="button" class="queue-filter-btn" data-queue="solo">솔로랭크 (${queueCounts.solo})</button>
        <button type="button" class="queue-filter-btn" data-queue="flex">자유랭크 (${queueCounts.flex})</button>
        <button type="button" class="queue-filter-btn" data-queue="aram">칼바람 나락 (${queueCounts.aram})</button>
      </div>
      <div class="queue-filter-stat-info" id="queueFilterStatInfo"></div>
    </div>
  `;

  // Matches List HTML
  let matchesHtml = `<div class="matches-list-wrapper">`;

  matches.forEach((m, idx) => {
    const isWin = m.win;
    // 다시하기(조기 종료)는 승패가 아니므로 회색으로 따로 표시 (요약 승률에서도 서버가 제외)
    const isRemake = Boolean(m.is_remake);
    const cardClass = isRemake ? "match-card remake" : (isWin ? "match-card win" : "match-card loss");
    const resultText = isRemake ? "다시하기" : (isWin ? "승리" : "패배");
    const resultClass = isRemake ? "remake" : (isWin ? "win" : "loss");
    const meRow = (m.team1 || []).concat(m.team2 || []).find(x => x.is_me);
    const myTeam = meRow ? ((m.team1 || []).includes(meRow) ? m.team1 : m.team2) : null;
    const myTeamDamage = myTeam ? myTeam.reduce((acc, x) => acc + (x.damage_dealt || 0), 0) : 0;
    const dmgShare = myTeamDamage > 0 ? Math.round((m.total_damage_dealt || 0) / myTeamDamage * 100) : null;
    const visionScore = meRow && meRow.vision_score != null ? meRow.vision_score : null;
    const qGroup = getQueueGroup(m.game_mode);

    // OP.GG Style MVP & ACE badge
    const badgeRaw = (m.op_badge || m.badge || '').toUpperCase();
    const isMvp = badgeRaw === 'MVP';
    const isAce = badgeRaw === 'ACE';

    // KDA Tier Coloring (5.0+ Gold, 4.0+ Green, 3.0+ Blue) - 숫자는 한 번만 표시하고 배지 중복 제거
    const matchKdaNum = typeof m.kda_ratio === 'number' ? m.kda_ratio : parseFloat(m.kda_ratio || 0);
    let matchKdaColor = "var(--text-muted)";
    if (m.kda_ratio === "Perfect" || matchKdaNum >= 5.0) {
      matchKdaColor = "#F59E0B"; // 골드 (5.0 이상)
    } else if (matchKdaNum >= 4.0) {
      matchKdaColor = "#10B981"; // 그린 (4.0 이상)
    } else if (matchKdaNum >= 3.0) {
      matchKdaColor = "#3B82F6"; // 블루 (3.0 이상)
    }

    // Multikill badge
    let multiKillBadgeHtml = "";
    if (m.multi_kill) {
      const mk = String(m.multi_kill).trim();
      let mkCls = "doublekill";
      let mkIcon = "";
      if (mk.includes("펜타") || (m.multi_kill_tag && m.multi_kill_tag.includes("PENTA"))) {
        mkCls = "pentakill";
        mkIcon = '<i class="fa-solid fa-fire-flame-curved"></i> ';
      } else if (mk.includes("쿼드라") || (m.multi_kill_tag && m.multi_kill_tag.includes("QUADRA"))) {
        mkCls = "quadrakill";
        mkIcon = '<i class="fa-solid fa-bolt"></i> ';
      } else if (mk.includes("트리플") || (m.multi_kill_tag && m.multi_kill_tag.includes("TRIPLE"))) {
        mkCls = "triplekill";
        mkIcon = '<i class="fa-solid fa-burst"></i> ';
      } else {
        mkCls = "doublekill";
      }
      multiKillBadgeHtml = `<span class="mc-multikill-badge ${mkCls}" title="${m.multi_kill_tag || mk}">${mkIcon}${mk}</span>`;
    }

    // 7 Item slots (6 Core + 1 Trinket) with debossed glassmorphism & rich tooltips
    const rawItems = (m.items || []).slice(0, 6);
    while (rawItems.length < 6) rawItems.push(null);
    const trinketItem = m.trinket || null;
    const all7Items = [...rawItems, trinketItem];

    const itemSlotsHtml = all7Items.map((item, sIdx) => {
      const isTrinket = sIdx === 6;
      const itemId = typeof item === 'object' && item !== null ? item.id : item;
      const itemIcon = typeof item === 'object' && item !== null && item.icon ? item.icon : (itemId ? `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/item/${itemId}.png` : null);
      if (!itemId || !itemIcon) {
        return `<div class="mc-item-slot empty ${isTrinket ? 'trinket-slot' : ''}"></div>`;
      }
      return `
        <div class="mc-item-slot filled ${isTrinket ? 'trinket-slot' : ''}" data-lol-tooltip="true" data-tooltip-type="item" data-tooltip-id="${itemId}" data-tooltip-name="${isTrinket ? '장신구' : '아이템'} ${itemId}">
          <img class="mc-item-img" src="${itemIcon}" alt="item ${itemId}" onerror="this.parentElement.className='mc-item-slot empty'; this.remove();">
        </div>
      `;
    }).join('');

    // Team 1 & Team 2 lists
    const team1Html = (m.team1 || []).map(p => `
      <div class="mc-player-chip ${p.is_me ? 'is-me' : ''}" data-gn="${escapeHtml(p.game_name)}" data-tag="${escapeHtml(p.tag_line)}" title="${escapeHtml(p.game_name)}#${escapeHtml(p.tag_line)} (${p.champ_name})">
        <img class="mc-player-avatar" src="${p.champ_img}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
        <span class="mc-player-name">${escapeHtml(p.game_name)}</span>
      </div>
    `).join('');

    const team2Html = (m.team2 || []).map(p => `
      <div class="mc-player-chip ${p.is_me ? 'is-me' : ''}" data-gn="${escapeHtml(p.game_name)}" data-tag="${escapeHtml(p.tag_line)}" title="${escapeHtml(p.game_name)}#${escapeHtml(p.tag_line)} (${p.champ_name})">
        <img class="mc-player-avatar" src="${p.champ_img}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
        <span class="mc-player-name">${escapeHtml(p.game_name)}</span>
      </div>
    `).join('');

    // Accordion 10 players data
    const all10 = (m.team1 || []).concat(m.team2 || []);
    const maxDamage = Math.max(...all10.map(x => x.damage_dealt || 0), 1);

    const team1Kills = (m.team1 || []).reduce((acc, p) => acc + (p.kills || 0), 0);
    const team2Kills = (m.team2 || []).reduce((acc, p) => acc + (p.kills || 0), 0);
    const team1Gold = (m.team1 || []).reduce((acc, p) => acc + (p.gold || 0), 0);
    const team2Gold = (m.team2 || []).reduce((acc, p) => acc + (p.gold || 0), 0);
    const team1Damage = (m.team1 || []).reduce((acc, p) => acc + (p.damage_dealt || 0), 0);
    const team2Damage = (m.team2 || []).reduce((acc, p) => acc + (p.damage_dealt || 0), 0);

    // team1 은 항상 내 팀이다. 라이엇 teamId 100=블루, 200=레드
    const myTeamIsRed = (m.team1 || [])[0]?.team_id === 200;
    const team1SideLabel = myTeamIsRed ? '레드팀' : '블루팀';
    const team2SideLabel = myTeamIsRed ? '블루팀' : '레드팀';

    const renderAccordionTeamRows = (players, isBlue) => {
      return players.map((p, pRowIdx) => {
        const dmgPercent = Math.min(100, Math.round(((p.damage_dealt || 0) / maxDamage) * 100));
        const isMaxDmg = (p.damage_dealt || 0) === maxDamage;
        const pBadge = (p.op_badge || '').toUpperCase();
        let pBadgeSnippet = '';
        if (pBadge === 'MVP') {
          pBadgeSnippet = `<span class="acc-badge-pill mvp" title="매치 최고 기여도 MVP"><i class="fa-solid fa-crown"></i> MVP</span>`;
        } else if (pBadge === 'ACE') {
          pBadgeSnippet = `<span class="acc-badge-pill ace" title="패배팀 최고 활약 ACE"><i class="fa-solid fa-star"></i> ACE</span>`;
        }

        const pRawItems = (p.items || []).slice(0, 6);
        while (pRawItems.length < 6) pRawItems.push(null);
        const pTrinket = p.trinket || null;
        const p7Items = [...pRawItems, pTrinket];

        const pItemsHtml = p7Items.map((it, pIdx) => {
          const isPTrinket = pIdx === 6;
          const itemId = typeof it === 'object' && it !== null ? it.id : it;
          if (!itemId) {
            return `<div class="acc-item-slot empty ${isPTrinket ? 'trinket' : ''}"></div>`;
          }
          return `
            <div class="acc-item-slot filled ${isPTrinket ? 'trinket' : ''}" data-lol-tooltip="true" data-tooltip-type="item" data-tooltip-id="${itemId}" data-tooltip-name="${isPTrinket ? '장신구' : '아이템'} ${itemId}">
              <img class="acc-item-img" src="https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/item/${itemId}.png" alt="item" onerror="this.parentElement.className='acc-item-slot empty ${isPTrinket ? 'trinket' : ''}'; this.remove();">
            </div>
          `;
        }).join('');

        // Position label & icon
        // 포지션이 없는 경기(칼바람 등)는 순서로 지어내지 않고 '-'로 표시
        const posKey = String(p.position || '').toUpperCase();
        const posMap = {
          TOP: ['top', '탑'],
          JUG: ['jungle', '정글'],
          JUNGLE: ['jungle', '정글'],
          MID: ['middle', '미드'],
          MIDDLE: ['middle', '미드'],
          BOT: ['bottom', '원딜'],
          BOTTOM: ['bottom', '원딜'],
          ADC: ['bottom', '원딜'],
          SUP: ['utility', '서포터'],
          SUPPORT: ['utility', '서포터'],
          UTILITY: ['utility', '서포터']
        };
        const posInfo = posMap[posKey];
        const posHtml = posInfo
          ? `<img class="acc-pos-icon" src="/static/images/positions/${posInfo[0]}.png" alt="${posInfo[1]}" title="${posInfo[1]}">`
          : `<span class="acc-pos-empty">-</span>`;

        // KDA
        const kRatio = p.deaths > 0 ? ((p.kills + p.assists) / p.deaths).toFixed(2) : 'Perfect';
        const numKRatio = kRatio === 'Perfect' ? 99 : parseFloat(kRatio);
        const kdaColor = numKRatio >= 5.0 ? '#F59E0B' : (numKRatio >= 4.0 ? '#10B981' : (numKRatio >= 3.0 ? '#3B82F6' : 'var(--text-heading)'));

        // Tier (티어 정보가 없거나 미배치인 경우 뱃지를 렌더하지 않음)
        let tierPillHtml = '';
        if (p.tier) {
          const rawTier = String(p.tier).toUpperCase().trim();
          if (rawTier && rawTier !== 'UNRANKED' && rawTier !== 'NONE') {
            let tierShort = rawTier;
            let tierCls = 'tier-normal';
            if (rawTier.includes('CHALLENGER')) { tierShort = 'C'; tierCls = 'tier-challenger'; }
            else if (rawTier.includes('GRANDMASTER')) { tierShort = 'GM'; tierCls = 'tier-grandmaster'; }
            else if (rawTier.includes('MASTER')) { tierShort = 'M'; tierCls = 'tier-master'; }
            else if (rawTier.includes('DIAMOND')) { tierShort = 'D' + (rawTier.match(/\d+/) || [''])[0]; tierCls = 'tier-diamond'; }
            else if (rawTier.includes('EMERALD')) { tierShort = 'E' + (rawTier.match(/\d+/) || [''])[0]; tierCls = 'tier-emerald'; }
            else if (rawTier.includes('PLATINUM')) { tierShort = 'P' + (rawTier.match(/\d+/) || [''])[0]; tierCls = 'tier-platinum'; }
            else if (rawTier.includes('GOLD')) { tierShort = 'G' + (rawTier.match(/\d+/) || [''])[0]; tierCls = 'tier-gold'; }
            else if (rawTier.includes('SILVER')) { tierShort = 'S' + (rawTier.match(/\d+/) || [''])[0]; tierCls = 'tier-silver'; }
            else if (rawTier.includes('BRONZE')) { tierShort = 'B' + (rawTier.match(/\d+/) || [''])[0]; tierCls = 'tier-bronze'; }
            else if (rawTier.includes('IRON')) { tierShort = 'I' + (rawTier.match(/\d+/) || [''])[0]; tierCls = 'tier-iron'; }
            tierPillHtml = `<span class="acc-tier-pill ${tierCls}" title="${p.tier}">${tierShort}</span>`;
          }
        }

        // CS & Min
        const pCs = typeof p.cs === 'object' && p.cs !== null ? (p.cs.total || 0) : (Number(p.cs) || 0);
        const pCsMin = typeof p.cs === 'object' && p.cs !== null ? (p.cs.per_min || 0) : (p.cs_per_min || (m.duration_sec ? (pCs / (m.duration_sec / 60)).toFixed(1) : '-'));

        // Wards
        const pCw = p.control_wards !== undefined ? p.control_wards : (p.is_me && m.control_wards !== undefined ? m.control_wards : '-');
        const pWp = p.wards_placed !== undefined ? p.wards_placed : '-';

        // KP
        const pKp = p.kill_participation !== undefined ? p.kill_participation : '-';

        return `
          <tr class="acc-player-row ${p.is_me ? 'is-me' : ''}">
            <td class="col-pos">
              ${posHtml}
            </td>
            <td class="col-summoner">
              <div class="acc-player-info-cell">
                <div class="acc-champ-wrap">
                  <img class="acc-champ-img" src="${p.champ_img}" alt="${escapeHtml(p.champ_name || '')}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
                  <span class="acc-champ-lvl">Lv.${p.champ_level || '-'}</span>
                </div>
                <div class="acc-spells-col">
                  <img class="acc-spell-img" data-lol-tooltip="true" data-tooltip-type="spell" data-tooltip-id="4" data-tooltip-name="소환사 주문" src="${p.spell1_icon || 'https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/spell/SummonerFlash.png'}">
                  <img class="acc-spell-img" data-lol-tooltip="true" data-tooltip-type="spell" data-tooltip-id="14" data-tooltip-name="소환사 주문" src="${p.spell2_icon || 'https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/spell/SummonerDot.png'}">
                </div>
                <div class="acc-runes-col">
                  <img class="acc-rune-img" data-lol-tooltip="true" data-tooltip-type="rune" data-tooltip-id="8010" data-tooltip-name="핵심 룬" src="${p.primary_rune_icon || 'data:image/gif;base64,R0lGODlhAQABAAAAACw='}">
                  <img class="acc-rune-img sub" data-lol-tooltip="true" data-tooltip-type="rune" data-tooltip-id="8100" data-tooltip-name="보조 룬" src="${p.secondary_rune_icon || 'https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/7200_Domination.png'}">
                </div>
                <div class="acc-name-tier-block">
                  <div class="acc-name-line">
                    <span class="acc-player-link" data-gn="${escapeHtml(p.game_name)}" data-tag="${escapeHtml(p.tag_line || 'KR1')}">${escapeHtml(p.game_name)}</span>
                    <span class="acc-player-tag">#${escapeHtml(p.tag_line || 'KR1')}</span>
                    ${pBadgeSnippet}
                  </div>
                  ${tierPillHtml ? `<div class="acc-tier-line">${tierPillHtml}</div>` : ''}
                </div>
              </div>
            </td>
            <td class="col-kda">
              <div class="acc-kda-cell">
                <div class="acc-kda-nums">${p.kills} / <span class="acc-death-num">${p.deaths}</span> / ${p.assists}</div>
                <div class="acc-kda-sub">
                  <span class="acc-kda-ratio" style="color: ${kdaColor};">${kRatio}:1</span>
                  <span class="acc-kp-badge" title="킬관여율">${pKp}%</span>
                </div>
              </div>
            </td>
            <td class="col-damage">
              <div class="acc-damage-bar-wrap">
                <div class="acc-damage-header">
                  <span class="acc-damage-num">${formatNumber(p.damage_dealt)}</span>
                  ${isMaxDmg ? '<span class="acc-top-dmg-badge" title="최고 딜량"><i class="fa-solid fa-fire"></i> MAX</span>' : ''}
                </div>
                <div class="acc-damage-bar">
                  <div class="acc-damage-fill ${isBlue ? 'blue' : 'red'}" style="width: ${dmgPercent}%;"></div>
                </div>
              </div>
            </td>
            <td class="col-cs">
              <div class="acc-cs-wrap">
                <span class="acc-cs-num">${pCs}</span>
                <span class="acc-cs-min">(${pCsMin})</span>
              </div>
            </td>
            <td class="col-ward">
              <div class="acc-ward-val" title="제어와드 ${pCw} / 설치와드 ${pWp}">
                <span class="acc-cw"><i class="fa-solid fa-eye"></i> ${pCw}</span>
                <span class="acc-wp">(${pWp})</span>
              </div>
            </td>
            <td class="col-items">
              <div class="acc-items-row">${pItemsHtml}</div>
            </td>
          </tr>
        `;
      }).join('');
    };

    // AI Match Coach 개별 매치 전술 코칭 피드백
    let matchCoachTag = null;
    let matchCoachType = "neutral";
    let matchCoachReview = "";
    if (m.coach_metrics) {
      const cm = m.coach_metrics;
      if (cm.first_death_is_early && cm.first_death_type && cm.first_death_type.includes("솔로킬")) {
        matchCoachTag = "라인전 솔로킬 위험도 높음";
        matchCoachType = "danger";
      } else if (cm.first_death_is_early && cm.first_death_type && cm.first_death_type.includes("갱킹")) {
        matchCoachTag = "초반 3~5분 갱킹 취약";
        matchCoachType = "warning";
      } else if (cm.cs_diff_15m >= 15) {
        matchCoachTag = "라인전 분당 CS 압도";
        matchCoachType = "positive";
      } else if (cm.vision_score_15m >= 16) {
        matchCoachTag = "15분 전 적 정글 시야 우수";
        matchCoachType = "positive";
      } else if (cm.epic_object_participation >= 80) {
        matchCoachTag = "초반 오브젝트 적극 합류";
        matchCoachType = "positive";
      }
    }

    matchesHtml += `
      <div class="${cardClass}" data-queue-group="${qGroup}" data-win="${isWin}" data-match-idx="${idx}">
        <div class="match-card-main">
          <div class="mc-meta">
            <div class="mc-queue-type">${m.game_mode}</div>
            <div class="mc-time-ago">${m.time_ago}</div>
            <div class="mc-result-badge ${resultClass}">${resultText}</div>
            <div class="mc-duration">${m.duration_str}</div>
            ${isMvp ? `<span class="op-badge-pill mvp" title="팀 내 최고 기여도 MVP"><i class="fa-solid fa-crown"></i> MVP</span>` : ''}
            ${isAce ? `<span class="op-badge-pill ace" title="패배 팀 최고 활약 ACE"><i class="fa-solid fa-star"></i> ACE</span>` : ''}
            ${(!isMvp && !isAce && m.op_badge) ? `<span class="op-badge-pill general">${m.op_badge}</span>` : ''}
            ${m.op_score ? `<div class="mc-op-score" title="OP 스코어">${m.op_score}점</div>` : ''}
            ${matchCoachTag ? `<div class="mc-coach-tag-pill ${matchCoachType}" title="${escapeHtml(matchCoachReview)}"><i class="fa-solid fa-robot"></i> ${escapeHtml(matchCoachTag)}</div>` : ''}
          </div>

          <div class="mc-champ-spells">
            <div class="mc-champ-img-wrap">
              <img class="mc-champ-avatar" src="${m.champ_img}" alt="${m.champ_name}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/champion/Yasuo.png'">
              <div class="mc-champ-lvl">Lv.${m.champ_level}</div>
            </div>
            <div class="mc-spells-runes">
              <img class="mc-spell-img" data-lol-tooltip="true" data-tooltip-type="spell" data-tooltip-id="4" data-tooltip-name="${m.spells?.[0]?.name || '점멸'}" src="${m.spell1_icon || m.spells?.[0]?.icon || m.spells?.[0]?.img || 'https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/spell/SummonerFlash.png'}">
              <div class="mc-rune-icon-wrap" data-lol-tooltip="true" data-tooltip-type="rune" data-tooltip-name="${m.primary_rune || m.rune?.name || '핵심 룬'}">
                <img class="mc-rune-img primary" src="${m.primary_rune_icon || m.rune?.icon || 'data:image/gif;base64,R0lGODlhAQABAAAAACw='}">
              </div>
              <img class="mc-spell-img" data-lol-tooltip="true" data-tooltip-type="spell" data-tooltip-id="14" data-tooltip-name="${m.spells?.[1]?.name || '소환사 주문'}" src="${m.spell2_icon || m.spells?.[1]?.icon || m.spells?.[1]?.img || 'https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/spell/SummonerDot.png'}">
              <div class="mc-rune-icon-wrap sub" data-lol-tooltip="true" data-tooltip-type="rune" data-tooltip-name="${m.secondary_rune?.name || '보조 룬 스타일'}">
                <img class="mc-rune-img secondary" src="${m.secondary_rune_icon || m.secondary_rune?.icon || m.rune?.secondary_icon || 'https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/7200_Domination.png'}">
              </div>
            </div>
          </div>

          <div class="mc-kda-info">
            <div class="mc-kda-score">${m.kills} / <span style="color: #E84057;">${m.deaths}</span> / ${m.assists}</div>
            <div class="mc-kda-ratio" style="color: ${matchKdaColor}; font-weight: 800;">
              ${m.kda_ratio === 'Perfect' ? 'Perfect' : `${m.kda_ratio}:1`}
            </div>
            <div class="mc-kp-row"><i class="fa-solid fa-crosshairs"></i> 킬관여 <strong>${m.kill_participation}%</strong></div>
            ${multiKillBadgeHtml}
          </div>

          <div class="mc-cs-info">
            <div class="mc-cs-val">CS ${typeof m.cs === 'object' ? m.cs.total : m.cs} (${m.cs_per_min || (typeof m.cs === 'object' ? m.cs.per_min : '')})</div>
            <div class="mc-meta-sub" title="피해량 (팀 내 비중)"><i class="fa-solid fa-bolt-lightning" style="color: #F59E0B;"></i> ${formatNumber(m.total_damage_dealt)}${dmgShare !== null ? ` <span class="mc-dmg-share">${dmgShare}%</span>` : ""}</div>
            <div class="mc-meta-sub" title="시야 점수 · 제어 와드"><i class="fa-solid fa-eye" style="color: #EC4899;"></i> ${visionScore !== null ? `시야 ${visionScore} · ` : ""}제와 ${m.control_wards || 0}</div>
          </div>

          <div class="mc-items-grid">
            ${itemSlotsHtml}
          </div>

          <div class="mc-players-list">
            <div class="mc-team-col">${team1Html}</div>
            <div class="mc-team-col">${team2Html}</div>
          </div>

          <div class="mc-action-col">
            <button class="btn-toggle-match-detail" data-target="acc-${idx}" title="10인 상세 딜량 및 아이템 통계 보기">
              <i class="fa-solid fa-chevron-down"></i>
            </button>
          </div>
        </div>

        <div id="acc-${idx}" class="match-accordion-detail">
          <div class="accordion-teams-grid">
            <div class="acc-team-card blue-team">
              <div class="acc-team-header blue">
                <div class="acc-team-title-wrap">
                  <span class="acc-team-badge blue"><i class="fa-solid fa-shield"></i> ${team1SideLabel} (내 팀)</span>
                  <span class="acc-team-outcome ${isWin ? 'win' : 'loss'}">${isWin ? '승리' : '패배'}</span>
                </div>
                <div class="acc-team-stats-summary">
                  <span class="acc-stat-pill" title="팀 총 킬"><i class="fa-solid fa-skull"></i> <strong>${team1Kills}</strong></span>
                  <span class="acc-stat-pill" title="팀 총 골드"><i class="fa-solid fa-coins"></i> <strong>${(team1Gold / 1000).toFixed(1)}k</strong></span>
                  <span class="acc-stat-pill" title="팀 총 피해량"><i class="fa-solid fa-bolt"></i> <strong>${formatNumber(team1Damage)}</strong></span>
                </div>
              </div>
              <div class="acc-table-scroll">
                <table class="acc-team-table">
                  <thead>
                    <tr>
                      <th class="col-pos" style="width: 28px;"></th>
                      <th class="col-summoner">소환사</th>
                      <th class="col-kda" style="width: 110px; text-align: center;">KDA</th>
                      <th class="col-damage" style="width: 130px; text-align: right;">피해량</th>
                      <th class="col-cs" style="width: 75px; text-align: right;">CS</th>
                      <th class="col-ward" style="width: 65px; text-align: right;">와드</th>
                      <th class="col-items" style="width: 165px; text-align: left;">아이템</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${renderAccordionTeamRows(m.team1 || [], true)}
                  </tbody>
                </table>
              </div>
            </div>

            <div class="acc-team-card red-team">
              <div class="acc-team-header red">
                <div class="acc-team-title-wrap">
                  <span class="acc-team-badge red"><i class="fa-solid fa-shield"></i> ${team2SideLabel}</span>
                  <span class="acc-team-outcome ${!isWin ? 'win' : 'loss'}">${!isWin ? '승리' : '패배'}</span>
                </div>
                <div class="acc-team-stats-summary">
                  <span class="acc-stat-pill" title="팀 총 킬"><i class="fa-solid fa-skull"></i> <strong>${team2Kills}</strong></span>
                  <span class="acc-stat-pill" title="팀 총 골드"><i class="fa-solid fa-coins"></i> <strong>${(team2Gold / 1000).toFixed(1)}k</strong></span>
                  <span class="acc-stat-pill" title="팀 총 피해량"><i class="fa-solid fa-bolt"></i> <strong>${formatNumber(team2Damage)}</strong></span>
                </div>
              </div>
              <div class="acc-table-scroll">
                <table class="acc-team-table">
                  <thead>
                    <tr>
                      <th class="col-pos" style="width: 28px;"></th>
                      <th class="col-summoner">소환사</th>
                      <th class="col-kda" style="width: 110px; text-align: center;">KDA</th>
                      <th class="col-damage" style="width: 130px; text-align: right;">피해량</th>
                      <th class="col-cs" style="width: 75px; text-align: right;">CS</th>
                      <th class="col-ward" style="width: 65px; text-align: right;">와드</th>
                      <th class="col-items" style="width: 165px; text-align: left;">아이템</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${renderAccordionTeamRows(m.team2 || [], false)}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  });

  // Empty state for queue filter
  matchesHtml += `
    <div id="queueEmptyState" class="queue-empty-state" style="display: none;">
      <i class="fa-solid fa-filter-circle-xmark queue-empty-icon"></i>
      <div class="queue-empty-title">선택한 큐 타입의 경기 기록이 없습니다</div>
      <div class="queue-empty-desc">상단의 다른 큐 타입 탭(전체, 솔로랭크 등)을 클릭해보세요.</div>
    </div>
  </div>`;

  containerEl.innerHTML = summaryHtml + (trendDashboardHtml || '') + mostChampsWidgetHtml + filterBarHtml + matchesHtml;

  // Queue filter handler with instant reactive stat recalculation
  const filterBtns = containerEl.querySelectorAll(".queue-filter-btn");
  const matchCards = containerEl.querySelectorAll(".match-card");
  const statInfoEl = containerEl.querySelector("#queueFilterStatInfo");
  const emptyStateEl = containerEl.querySelector("#queueEmptyState");

  const updateQueueStats = (targetQueue) => {
    const filteredMatches = [];
    let visibleCount = 0;

    matchCards.forEach(card => {
      const cardQueue = card.getAttribute("data-queue-group");
      const matchIdx = parseInt(card.getAttribute("data-match-idx"), 10);
      const mData = matches[matchIdx];

      if (targetQueue === "all" || cardQueue === targetQueue) {
        card.style.display = "";
        visibleCount++;
        if (mData) filteredMatches.push(mData);
      } else {
        card.style.display = "none";
      }
    });

    if (emptyStateEl) {
      emptyStateEl.style.display = visibleCount === 0 ? "flex" : "none";
      if (visibleCount === 0) {
        const queueLabels = { all: "전체", solo: "솔로랭크", flex: "자유랭크", aram: "칼바람 나락" };
        const qTitle = emptyStateEl.querySelector(".queue-empty-title");
        if (qTitle) qTitle.textContent = `선택한 큐 타입(${queueLabels[targetQueue] || targetQueue})의 경기 기록이 없습니다`;
      }
    }

    if (filteredMatches.length > 0) {
      const fTotal = filteredMatches.length;
      const fWins = filteredMatches.filter(m => m.win).length;
      const fLosses = fTotal - fWins;
      const fWr = Math.round((fWins / fTotal) * 100);

      const fKills = filteredMatches.reduce((acc, m) => acc + (m.kills || 0), 0);
      const fDeaths = filteredMatches.reduce((acc, m) => acc + (m.deaths || 0), 0);
      const fAssists = filteredMatches.reduce((acc, m) => acc + (m.assists || 0), 0);

      const fAvgK = (fKills / fTotal).toFixed(1);
      const fAvgD = (fDeaths / fTotal).toFixed(1);
      const fAvgA = (fAssists / fTotal).toFixed(1);

      const fKdaRatio = fDeaths > 0 ? ((fKills + fAssists) / fDeaths).toFixed(2) : "Perfect";
      const fNumKda = fKdaRatio === "Perfect" ? 99.0 : parseFloat(fKdaRatio);
      const fKdaColor = fNumKda >= 5.0 ? "#F59E0B" : (fNumKda >= 4.0 ? "#10B981" : (fNumKda >= 3.0 ? "#3B82F6" : "var(--text-heading)"));

      const fKp = Math.round(filteredMatches.reduce((acc, m) => acc + (m.kill_participation || 0), 0) / fTotal);
      const wrColor = fWr > 50 ? "#10B981" : "#E84057";

      if (statInfoEl) {
        statInfoEl.innerHTML = "";
      }

      // Update top summary donut and kda cards
      const donutFill = containerEl.querySelector(".donut-circle-fill");
      const donutText = containerEl.querySelector(".donut-text");
      const recWins = containerEl.querySelector(".record-wins");
      const recLosses = containerEl.querySelector(".record-losses");
      const miniWin = containerEl.querySelector(".mini-bar-win");
      const miniLoss = containerEl.querySelector(".mini-bar-loss");
      const metaNote = containerEl.querySelector(".record-meta-note");
      const kdaHighlight = containerEl.querySelector(".kda-ratio-highlight");
      const kdaNumsRow = containerEl.querySelector(".kda-numbers-row");
      const kpBadge = containerEl.querySelector(".kp-badge strong");

      if (donutFill) {
        donutFill.setAttribute("stroke-dasharray", `${fWr}, 100`);
        donutFill.setAttribute("stroke", wrColor);
      }
      if (donutText) {
        donutText.textContent = `${fWr}%`;
        donutText.setAttribute("fill", wrColor);
      }
      if (recWins) recWins.textContent = `${fWins}승`;
      if (recLosses) recLosses.textContent = `${fLosses}패`;
      if (miniWin) {
        miniWin.style.width = `${fWr}%`;
        miniWin.style.background = wrColor;
      }
      if (miniLoss) miniLoss.style.width = `${100 - fWr}%`;
      if (metaNote) metaNote.textContent = `${fTotal}전`;
      if (kdaHighlight) {
        kdaHighlight.textContent = `${fKdaRatio}:1`;
        kdaHighlight.style.color = fKdaColor;
      }
      if (kdaNumsRow) {
        kdaNumsRow.innerHTML = `<span class="kda-k">${fAvgK}</span> / <span class="kda-d" style="color: #EF4444;">${fAvgD}</span> / <span class="kda-a">${fAvgA}</span>`;
      }
      if (kpBadge) kpBadge.textContent = `${fKp}%`;
    } else {
      if (statInfoEl) {
        statInfoEl.innerHTML = "";
      }
      const donutFill = containerEl.querySelector(".donut-circle-fill");
      const donutText = containerEl.querySelector(".donut-text");
      const recWins = containerEl.querySelector(".record-wins");
      const recLosses = containerEl.querySelector(".record-losses");
      const miniWin = containerEl.querySelector(".mini-bar-win");
      const miniLoss = containerEl.querySelector(".mini-bar-loss");
      const metaNote = containerEl.querySelector(".record-meta-note");
      const kdaHighlight = containerEl.querySelector(".kda-ratio-highlight");
      const kdaNumsRow = containerEl.querySelector(".kda-numbers-row");
      const kpBadge = containerEl.querySelector(".kp-badge strong");

      if (donutFill) {
        donutFill.setAttribute("stroke-dasharray", "0, 100");
        donutFill.setAttribute("stroke", "var(--text-muted)");
      }
      if (donutText) {
        donutText.textContent = "0%";
        donutText.setAttribute("fill", "var(--text-muted)");
      }
      if (recWins) recWins.textContent = "0승";
      if (recLosses) recLosses.textContent = "0패";
      if (miniWin) { miniWin.style.width = "0%"; }
      if (miniLoss) miniLoss.style.width = "0%";
      if (metaNote) metaNote.textContent = "0전";
      if (kdaHighlight) {
        kdaHighlight.textContent = "-";
        kdaHighlight.style.color = "var(--text-muted)";
      }
      if (kdaNumsRow) {
        kdaNumsRow.innerHTML = `<span class="kda-k">-</span> / <span class="kda-d">-</span> / <span class="kda-a">-</span>`;
      }
      if (kpBadge) kpBadge.textContent = "-";
    }
  };

  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      filterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const targetQueue = btn.getAttribute("data-queue");
      updateQueueStats(targetQueue);
    });
  });

  // Initial update
  updateQueueStats("all");

  // Accordion click handlers (Button or Main Card Click)
  containerEl.querySelectorAll(".match-card").forEach(card => {
    const cardMain = card.querySelector(".match-card-main");
    const toggleBtn = card.querySelector(".btn-toggle-match-detail");
    const accDetail = card.querySelector(".match-accordion-detail");

    const toggleAccordion = () => {
      if (!accDetail) return;
      const isOpen = accDetail.classList.contains("open");
      accDetail.classList.toggle("open", !isOpen);
      card.classList.toggle("expanded", !isOpen);
      if (toggleBtn) {
        const icon = toggleBtn.querySelector("i");
        if (icon) {
          icon.className = isOpen ? "fa-solid fa-chevron-down" : "fa-solid fa-chevron-up";
        }
      }
    };

    if (toggleBtn) {
      toggleBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleAccordion();
      });
    }

    if (cardMain) {
      cardMain.addEventListener("click", (e) => {
        if (e.target.closest(".mc-player-chip, .btn-toggle-match-detail, .acc-player-link, a, button, [data-lol-tooltip]")) {
          return;
        }
        toggleAccordion();
      });
    }
  });

  // Clicking any summoner chip or link in match cards opens their detail
  containerEl.querySelectorAll(".mc-player-chip, .acc-player-link").forEach(chip => {
    chip.addEventListener("click", (e) => {
      e.stopPropagation();
      const gn = chip.getAttribute("data-gn");
      const tag = chip.getAttribute("data-tag") || "KR1";
      if (gn) {
        openPlayerDetail({ game_name: gn, tag_line: tag });
      }
    });
  });

  // Attach interactive rich tooltips for runes, spells, items
  attachRichTooltips(containerEl);
}
// In-Game Active Spectator Module
function renderRealLiveGameHtml(data) {
  const elapsed = Math.max(0, Number(data.game_length_sec) || 0);
  const timeText = `${Math.floor(elapsed / 60)}분 ${String(elapsed % 60).padStart(2, "0")}초`;
  const icon = (src, title, type) => src
    ? `<img class="ingame-live-spell-icon" data-lol-tooltip="true" data-tooltip-type="${type || 'spell'}" data-tooltip-name="${escapeHtml(title || '')}" src="${escapeHtml(src)}" alt="${escapeHtml(title || '')}" title="${escapeHtml(title || '')}">`
    : `<span class="ingame-live-spell-icon-empty"></span>`;
  const teamHtml = (team, label, isBlue) => `
    <div class="ingame-live-team-col ${isBlue ? 'blue' : 'red'}">
      <div class="ingame-live-team-header ${isBlue ? 'blue' : 'red'}">
        <i class="fa-solid fa-shield"></i> ${label}
      </div>
      <div class="ingame-live-players-list">
        ${team.map(p => {
          const extra = [];
          if (p.league_points != null) {
            extra.push(`${escapeHtml(String(p.league_points))} LP`);
          }
          if (p.wins != null && p.losses != null && p.win_rate != null) {
            const wrCls = Number(p.win_rate) > 50 ? 'is-good' : 'is-bad';
            extra.push(`${escapeHtml(String(p.wins))}승 ${escapeHtml(String(p.losses))}패 <span class="winrate-badge ${wrCls}">${escapeHtml(String(p.win_rate))}%</span>`);
          }
          if (p.champ_mastery_level != null && p.champ_mastery_points != null) {
            const pts = Number(p.champ_mastery_points).toLocaleString();
            extra.push(`Lv.${escapeHtml(String(p.champ_mastery_level))} · ${escapeHtml(pts)}`);
          }
          if (p.champ_record && p.champ_record.games) {
            const cWrCls = Number(p.champ_record.win_rate) > 50 ? 'is-good' : 'is-bad';
            extra.push(`${escapeHtml(String(p.champ_record.games))}판 <span class="winrate-badge ${cWrCls}">${escapeHtml(String(p.champ_record.win_rate))}%</span>`);
          }
          const extraHtml = extra.length ? `<div class="ingame-live-player-extra">${extra.join(" · ")}</div>` : "";
          return `
          <div class="ingame-live-player-card ${p.is_me ? "is-me" : ""}">
            <img class="ingame-live-champ-img" src="${escapeHtml(p.champ_image)}" alt="${escapeHtml(p.champ_name)}" title="${escapeHtml(p.champ_name)}" onclick="if(window.openChampionPage) openChampionPage(${jsArg(p.champ_name || '')})" style="cursor: pointer;">
            <div class="ingame-live-spells-col">${icon(p.spell1?.icon, p.spell1?.name, 'spell')}${icon(p.spell2?.icon, p.spell2?.name, 'spell')}</div>
            <div class="ingame-live-runes-col">${icon(p.keystone?.icon, p.keystone?.name, 'rune')}${icon(p.sub_style?.icon, p.sub_style?.name, 'rune')}</div>
            <div class="ingame-live-player-meta">
              <div class="ingame-live-player-name-row">
                <span class="ingame-live-player-name ${p.hidden ? "is-hidden" : ""}" data-gn="${escapeHtml(p.game_name)}" data-tag="${escapeHtml(p.tag_line || 'KR1')}" style="cursor: pointer;">${escapeHtml(p.game_name)}</span>
                ${p.tag_line ? `<span class="ingame-live-player-tag">#${escapeHtml(p.tag_line)}</span>` : ""}
                ${p.display_tier ? `<span class="ingame-live-tier-badge">${escapeHtml(p.display_tier)}</span>` : ""}
              </div>
              ${extraHtml}
            </div>
          </div>
        `;
        }).join("")}
      </div>
    </div>`;
  const bansHtml = (bans) => (bans || []).map(b => icon(b.image, b.name, 'champ')).join("");

  return `
    <div class="ingame-live-container">
      <div class="ingame-live-top-bar">
        <div class="ingame-live-mode"><i class="fa-solid fa-satellite-dish"></i> ${escapeHtml(data.game_mode || "진행 중인 게임")}</div>
        <div class="ingame-live-time"><i class="fa-solid fa-clock"></i> ${timeText}</div>
      </div>
      <div class="ingame-live-teams-grid">
        ${teamHtml(data.blue_team || [], "블루팀", true)}
        ${teamHtml(data.red_team || [], "레드팀", false)}
      </div>
      ${(data.bans_blue?.length || data.bans_red?.length) ? `
        <div class="ingame-live-bans-bar">
          <div class="ingame-live-bans-group"><span class="bans-label blue">블루 밴</span> ${bansHtml(data.bans_blue)}</div>
          <div class="ingame-live-bans-group"><span class="bans-label red">레드 밴</span> ${bansHtml(data.bans_red)}</div>
        </div>` : ""}
      <div class="ingame-live-footer-note">라이엇 Spectator 기준</div>
    </div>
  `;
}

async function loadPlayerIngame(player) {
  const loadingEl = document.getElementById("modalIngameLoading");
  const containerEl = document.getElementById("modalIngameContainer");
  if (!loadingEl || !containerEl) return;

  loadingEl.style.display = "block";
  containerEl.style.display = "none";

  try {
    const res = await fetch(`/api/player/${encodeURIComponent(player.game_name)}/${encodeURIComponent(player.tag_line)}/ingame`);
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || "인게임 데이터를 가져오지 못했습니다.");
    }
    const data = await res.json();
    loadingEl.style.display = "none";
    containerEl.style.display = "block";
    renderIngameContent(data, player);
  } catch (err) {
    loadingEl.style.display = "none";
    containerEl.style.display = "block";
    containerEl.innerHTML = `
      <div style="padding: 2.5rem; text-align: center; color: #E84057;">
        <i class="fa-solid fa-circle-exclamation" style="font-size: 2rem; margin-bottom: 0.5rem; display: block;"></i>
        ${escapeHtml(err.message || "인게임 정보를 불러오는 중 오류가 발생했습니다.")}
      </div>
    `;
  }
}

function renderIngameContent(data, mePlayer) {
  const containerEl = document.getElementById("modalIngameContainer");
  if (!containerEl) return;

  if (!data || !data.is_active) {
    containerEl.innerHTML = `
      <div class="ingame-empty-state">
        <i class="fa-solid fa-moon ingame-empty-icon"></i>
        <div class="ingame-empty-title">진행 중인 게임 없음</div>
      </div>
    `;
    return;
  }

  // 라이엇 Spectator-V5 실제 데이터: 실제로 제공되는 정보(챔피언·주문·룬·밴·경과 시간)만 표시
  if (data.real) {
    containerEl.innerHTML = renderRealLiveGameHtml(data);
    containerEl.querySelectorAll(".ingame-live-player-name").forEach(chip => {
      chip.addEventListener("click", (e) => {
        e.stopPropagation();
        const gn = chip.getAttribute("data-gn");
        const tag = chip.getAttribute("data-tag") || "KR1";
        if (gn && typeof openPlayerDetail === "function") {
          openPlayerDetail({ game_name: gn, tag_line: tag });
        }
      });
    });
    attachRichTooltips(containerEl);
    return;
  }

  // 실제 라이엇 데이터가 아니면 보여주지 않는다 (지어낸 예측·브리핑 금지)
  containerEl.innerHTML = `
    <div class="ingame-empty-state">
      <i class="fa-solid fa-moon ingame-empty-icon"></i>
      <div class="ingame-empty-title">진행 중인 게임 없음</div>
    </div>
  `;
}
