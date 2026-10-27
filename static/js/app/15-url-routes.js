// 실제 주소: /champion/<id> 는 챔피언 페이지(17-champion-page.js), /summoner/<닉네임>-<태그> 는 소환사 전적 창.
// 열면 주소가 바뀌고(공유·뒤로 가기 가능), 닫거나 다른 탭으로 가면 / 로 돌아간다. 서버는 같은 화면에 제목·설명만 바꿔 준다.
(function () {
  const champPath = (id) => `/champion/${encodeURIComponent(String(id).toLowerCase())}`;
  const summonerPath = (name, tag) => `/summoner/${encodeURIComponent(`${name}-${tag || "KR1"}`)}`;
  let applyingRoute = false;

  function parseRoute(pathname) {
    let m = pathname.match(/^\/champion\/([^/]+)\/?$/);
    if (m) return { type: "champion", id: decodeURIComponent(m[1]) };
    m = pathname.match(/^\/summoner\/([^/]+)\/?$/);
    if (m) {
      const raw = decodeURIComponent(m[1]);
      const i = raw.lastIndexOf("-");
      if (i > 0 && i < raw.length - 1) return { type: "summoner", name: raw.slice(0, i), tag: raw.slice(i + 1) };
    }
    return null;
  }

  function setPath(path) {
    if (applyingRoute || location.pathname === path) return;
    history.pushState({}, "", path);
  }

  function wrapChampionPage() {
    const original = window.openChampionPage;
    if (typeof original !== "function") return;
    window.openChampionPage = async function (champId, ...rest) {
      setPath(champPath(champId));
      const result = await original.call(this, champId, ...rest);
      // 한글 이름으로 열었어도 주소는 영문 ID로 맞춘다
      const id = window.currentBuildData && window.currentBuildData.champion && window.currentBuildData.champion.id;
      if (id && location.pathname.startsWith("/champion/")) history.replaceState({}, "", champPath(id));
      return result;
    };
    window.openChampionBuildModal = (champId) => window.openChampionPage(champId);
  }

  // 챔피언 페이지에서 다른 탭으로 가면 주소를 / 로
  const originalSwitch = window.switchMainTab;
  if (typeof originalSwitch === "function") {
    window.switchMainTab = function (tab, ...rest) {
      if (tab !== "champion" && parseRoute(location.pathname)?.type === "champion") setPath("/");
      return originalSwitch.call(this, tab, ...rest);
    };
  }

  const originalOpenPlayer = window.openPlayerDetail;
  if (typeof originalOpenPlayer === "function") {
    window.openPlayerDetail = function (player, ...rest) {
      if (player && player.game_name) setPath(summonerPath(player.game_name, player.tag_line));
      return originalOpenPlayer.call(this, player, ...rest);
    };
  }

  // 창이 닫히면 / 로
  function watchClose(modal, type) {
    if (!modal) return;
    new MutationObserver(() => {
      const route = parseRoute(location.pathname);
      if (!modal.classList.contains("active") && route && route.type === type) setPath("/");
    }).observe(modal, { attributes: true, attributeFilter: ["class"] });
  }
  watchClose(document.getElementById("playerDetailModal"), "summoner");

  function applyRoute(route) {
    applyingRoute = true;
    try {
      const playerModal = document.getElementById("playerDetailModal");
      if (!route) {
        if (playerModal) playerModal.classList.remove("active");
        const pageView = document.querySelector("#viewChampion.active, #viewSummoner.active");
        if (pageView) window.switchMainTab("search");
      } else if (route.type === "champion") {
        window.openChampionPage(route.id);
      } else if (route.type === "summoner") {
        window.openPlayerDetail({ game_name: route.name, tag_line: route.tag });
      }
    } finally {
      applyingRoute = false;
    }
  }

  window.addEventListener("popstate", () => applyRoute(parseRoute(location.pathname)));

  // 챔피언 페이지 스크립트(17)는 이 파일 다음에 실리므로 문서가 다 읽힌 뒤에 감싼다
  function start() {
    wrapChampionPage();
    const initial = parseRoute(location.pathname);
    if (initial) applyRoute(initial);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
