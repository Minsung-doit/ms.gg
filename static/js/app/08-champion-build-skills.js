// 챔피언 룬·스펠 복사, 스킬 상세. 챔피언 화면은 17-champion-page.js

// 룬 & 스펠 원클릭 클립보드 복사 엔진 (클라이언트 룬 세팅 및 채팅 공유용)
async function copyRuneAndSpellSettings(customData = null) {
  const b = customData || currentBuildData || (typeof currentChampionDataCache !== "undefined" ? currentChampionDataCache : null);
  if (!b) {
    showToast("복사할 룬 및 스펠 데이터가 없습니다.", "error");
    return;
  }

  const c = b.champion || {};
  const champName = c.name || "챔피언";
  const runes = b.runes || {};
  const spells = b.spells || [];
  const skills = b.skills || {};
  const cores = b.core_builds || b.items?.core_sets || [];
  const tierInfo = b.tier_info || {};

  // 서버 사전 생성 텍스트 또는 클라이언트 정밀 포맷 텍스트
  let copyText = b.quick_copy_text || "";

  if (!copyText) {
    // 지어낸 기본 룬·주문을 복사하지 않는다
    showToast("복사할 빌드 표본이 아직 없습니다.", "info");
    return;
  }

  let isCopied = false;
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(copyText);
      isCopied = true;
    } catch (e) {
      isCopied = false;
    }
  }

  if (!isCopied) {
    const ta = document.createElement("textarea");
    ta.value = copyText;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.style.top = "-9999px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      isCopied = document.execCommand("copy");
    } catch (e) {
      isCopied = false;
    }
    document.body.removeChild(ta);
  }

  if (isCopied) {
    showToast(`📋 [${champName}] 룬 & 주문 세팅이 복사되었습니다!`, "success", 4000);

    const btns = document.querySelectorAll("#btnCopyRunePageHeader, #btnCopyRunePage, .btn-copy-rune-inline, .cp-tool-copy");
    btns.forEach(btn => {
      const origHtml = btn.innerHTML;
      if (btn.classList.contains("cp-tool")) {
        btn.innerHTML = `<i class="fa-solid fa-check" style="color: #10B981;"></i>`;
      } else {
        btn.innerHTML = `<i class="fa-solid fa-check"></i> <span>복사 완료!</span>`;
      }
      btn.style.filter = "brightness(1.2)";
      setTimeout(() => {
        btn.innerHTML = origHtml;
        btn.style.filter = "";
      }, 2200);
    });
  } else {
    showToast("클립보드 복사에 실패했습니다.", "error");
  }
}
window.copyRuneAndSpellSettings = copyRuneAndSpellSettings;
// 14.20 Champion P/Q/W/E/R Skills Engine, Cooldown/Mana Bars & Tactical Combos
const championSkillsDataRegistry = {};

function buildChampionSkillsEngineHtml(skillsData, containerId, activeKey = "Q") {
  if (!skillsData) return "";

  const activeKeyUpper = (activeKey || "Q").toUpperCase();
  const skillsList = skillsData.skills_list || [];
  const skillsDict = skillsData.skills || {};
  const passive = skillsData.passive || {};

  let activeSkill = null;
  if (activeKeyUpper === "P") {
    activeSkill = passive;
  } else {
    activeSkill = skillsDict[activeKeyUpper] || skillsList.find(s => s.key === activeKeyUpper) || skillsList[0];
  }
  if (!activeSkill) activeSkill = skillsList[0] || {};

  const navButtonsHtml = ["P", "Q", "W", "E", "R"].map(k => {
    let sObj = (k === "P") ? passive : (skillsDict[k] || skillsList.find(s => s.key === k) || {});
    const isActive = (k === activeKeyUpper);
    const keyLower = k.toLowerCase();
    const iconUrl = sObj.icon || `https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/spell/${skillsData.champion_id}${k}.png`;
    const skillName = sObj.name || (k === "P" ? "패시브" : `${k} 스킬`);

    return `
      <div class="skill-nav-btn key-${keyLower} ${isActive ? 'active' : ''}" onclick="switchChampionSkillTab(${jsArg(containerId)}, ${jsArg(k)})" title="${k}: ${skillName}">
        <div class="skill-nav-img-wrap">
          <img class="skill-nav-img" src="${iconUrl}" alt="${skillName}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/spell/SummonerFlash.png'">
          <span class="skill-key-badge badge-${keyLower}">${k}</span>
        </div>
        <span class="skill-nav-name">${skillName}</span>
      </div>
    `;
  }).join("");

  const keyLower = (activeSkill.key || "Q").toLowerCase();
  const cdText = activeSkill.cooldown || "기본 지속 효과";
  const costText = activeSkill.cost || "소모값 없음";
  const isFree = costText.includes("소모값 없음") || costText.includes("0");
  const isEnergy = costText.includes("기력");
  const costClass = isFree ? "free" : (isEnergy ? "energy" : "");
  const rangeText = (activeSkill.range && activeSkill.range !== "-") ? `사거리 ${activeSkill.range}` : null;

  // Level-by-level Cooldown & Mana Progression Bar Engine
  const cdList = activeSkill.cooldown_list || [];
  const costList = activeSkill.cost_list || [];
  let cdEngineHtml = "";
  if (cdList.length > 1) {
    const numCds = cdList.filter(n => typeof n === 'number');
    const maxCd = numCds.length > 0 ? Math.max(...numCds) : 10;
    const barsHtml = cdList.map((cdVal, idx) => {
      const lvl = idx + 1;
      const costVal = (costList && costList[idx] !== undefined) ? costList[idx] : null;
      const fillPct = maxCd > 0 ? Math.max(22, Math.min(100, (Number(cdVal) / maxCd) * 100)) : 50;
      return `
        <div class="cd-bar-item">
          <div class="cd-level-label">${lvl}Lv</div>
          <div class="cd-value-text">${cdVal}s</div>
          <div class="cd-track" title="${lvl}Lv 재사용 대기시간 ${cdVal}초">
            <div class="cd-fill" style="width: ${fillPct}%;"></div>
          </div>
          ${(costVal !== null && costVal > 0) ? `<div class="cd-mana-cost-sub">${costVal} MP</div>` : ''}
        </div>
      `;
    }).join("");

    cdEngineHtml = `
      <div class="skill-cooldown-engine-wrap">
        <div class="cd-engine-title">
          <span><i class="fa-solid fa-stopwatch" style="color: #60A5FA;"></i> 레벨별 쿨타임(초)</span>
        </div>
        <div class="cd-bars-grid">
          ${barsHtml}
        </div>
      </div>
    `;
  }

  // Core Mechanic Box
  const mechText = activeSkill.mechanic_summary || "";
  const mechHtml = mechText ? `
    <div class="skill-mechanic-box">
      <i class="fa-solid fa-bolt" style="color: #F59E0B; margin-top: 2px; flex-shrink: 0;"></i>
      <div>${mechText}</div>
    </div>
  ` : '';

  // Scaling Box
  const scalingText = activeSkill.scaling_info || "";
  const scalingHtml = scalingText ? `
    <div class="skill-scaling-box">
      <i class="fa-solid fa-calculator" style="color: #818CF8;"></i>
      <span>${scalingText}</span>
    </div>
  ` : '';

  // Tactical Combos Guide
  const combos = skillsData.combos || [];
  let combosHtml = "";
  if (combos.length > 0) {
    const cardsHtml = combos.map(cb => {
      const diffClass = cb.difficulty?.includes("쉬움") || cb.difficulty?.includes("Easy") ? "diff-easy" : (cb.difficulty?.includes("고급") || cb.difficulty?.includes("Hard") ? "diff-hard" : "diff-normal");

      const seqPills = (cb.sequence || []).map(step => {
        let stepClass = "";
        const sUpper = step.toUpperCase();
        if (sUpper.includes("Q")) stepClass = "step-q";
        else if (sUpper.includes("W")) stepClass = "step-w";
        else if (sUpper.includes("E")) stepClass = "step-e";
        else if (sUpper.includes("R")) stepClass = "step-r";
        else if (sUpper.includes("FLASH") || sUpper.includes("점멸")) stepClass = "step-flash";

        return `<span class="combo-step-pill ${stepClass}">${step}</span>`;
      }).join('<i class="fa-solid fa-chevron-right combo-sep-arrow"></i>');

      return `
        <div class="combo-card">
          <div class="combo-card-header">
            <div class="combo-name">
              <i class="fa-solid fa-fire" style="color: #EF4444;"></i>
              <span>${cb.name}</span>
            </div>
            <span class="combo-difficulty-pill ${diffClass}">${cb.difficulty || '보통'}</span>
          </div>
          <div class="combo-sequence-pills">
            ${seqPills}
          </div>
          <div class="combo-desc-text">
            ${cb.description}
          </div>
        </div>
      `;
    }).join("");

    combosHtml = `
      <div class="skill-combos-wrap">
        <div class="skill-combos-title">
          <span><i class="fa-solid fa-wand-magic-sparkles" style="color: #F59E0B;"></i> 콤보</span>
        </div>
        <div class="combos-grid">
          ${cardsHtml}
        </div>
      </div>
    `;
  }

  return `
    <div class="champion-skills-engine-card">
      <div class="skills-engine-header">
        <div class="skills-engine-title">
          <i class="fa-solid fa-bolt-lightning" style="color: #38BDF8;"></i>
          <span>스킬</span>
        </div>
      </div>

      <div class="skills-nav-row">
        ${navButtonsHtml}
      </div>

      <div class="skill-detail-display-card">
        <div class="skill-display-top">
          <div class="skill-title-group">
            <img class="skill-detail-icon" src="${activeSkill.icon}" alt="${activeSkill.name}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/__DDRAGON_VER__/img/spell/SummonerFlash.png'">
            <div class="skill-detail-names">
              <div class="skill-detail-title-row">
                <span class="skill-detail-key-tag badge-${keyLower}">${activeSkill.key}</span>
                <span class="skill-detail-name-text">${activeSkill.name}</span>
              </div>
            </div>
          </div>

          <div class="skill-meta-pills-row">
            <span class="skill-meta-pill cooldown"><i class="fa-solid fa-clock"></i> ${cdText}</span>
            <span class="skill-meta-pill cost ${costClass}"><i class="fa-solid fa-droplet"></i> ${costText}</span>
            ${rangeText ? `<span class="skill-meta-pill range"><i class="fa-solid fa-crosshairs"></i> ${rangeText}</span>` : ''}
          </div>
        </div>

        ${mechHtml}

        <div class="skill-desc-box">
          ${activeSkill.description}
        </div>

        ${cdEngineHtml}

        ${scalingHtml}
      </div>

      ${combosHtml}
    </div>
  `;
}

function renderChampionSkillsInteractive(containerId, skillsData, activeKey = "Q") {
  const container = document.getElementById(containerId);
  if (!container || !skillsData) return;
  championSkillsDataRegistry[containerId] = skillsData;
  container.innerHTML = buildChampionSkillsEngineHtml(skillsData, containerId, activeKey);
}
window.renderChampionSkillsInteractive = renderChampionSkillsInteractive;

function switchChampionSkillTab(containerId, skillKey) {
  const skillsData = championSkillsDataRegistry[containerId];
  if (!skillsData) return;
  renderChampionSkillsInteractive(containerId, skillsData, skillKey);
}
window.switchChampionSkillTab = switchChampionSkillTab;

