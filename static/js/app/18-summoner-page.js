// 소환사 전적: 팝업 대신 페이지(/summoner/<닉네임>-<태그>).
// 기존 전적 창(#playerDetailModal)을 페이지 칸(#viewSummoner)으로 옮겨 그대로 쓴다.
// 창이 열리면(.active) 이 페이지로 이동하고, 닫히면 검색 화면으로 돌아간다.
(function () {
  const view = document.getElementById("viewSummoner");
  const modal = document.getElementById("playerDetailModal");
  if (!view || !modal) return;

  view.appendChild(modal);
  modal.classList.add("as-page");

  new MutationObserver(() => {
    const open = modal.classList.contains("active");
    const onPage = view.classList.contains("active");
    if (open && !onPage) {
      switchMainTab("summoner");
      window.scrollTo({ top: 0 });
    } else if (!open && onPage) {
      switchMainTab("search");
    }
  }).observe(modal, { attributes: true, attributeFilter: ["class"] });
})();
