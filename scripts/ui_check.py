"""화면 자동 점검 (실행 중인 서버 필요: python run.py)

    python -X utf8 scripts/ui_check.py [http://127.0.0.1:3000]

모든 탭·챔피언 페이지·소환사 페이지를 다크/화이트 × 데스크톱/휴대폰(390px)/태블릿(820px)으로 열어서
1) 자바스크립트 오류  2) 가로 넘침(화면보다 넓음)  3) 화이트 모드에 남은 어두운 큰 상자
4) 배경과 대비가 너무 낮은 글자(2.0 미만) 를 찾는다. 문제가 없으면 종료 코드 0.
"""
import json
import subprocess
import sys

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000"
SCREENS = [
    ("search", "switchMainTab('search')"),
    ("leaderboard", "switchMainTab('leaderboard')"),
    ("multisearch", "switchMainTab('multisearch')"),
    ("spectator", "switchMainTab('spectator')"),
    ("masters", "switchMainTab('masters')"),
    ("tierlist", "switchMainTab('tierlist')"),
    ("duofinder", "switchMainTab('duofinder')"),
    ("matchup", "openMatchupWithChampions('야스오','요네')"),
    ("serverranking", "switchMainTab('serverranking')"),
    ("champion", "openChampionPage('Ahri')"),
    ("summoner", "performSearch('Hide on bush#KR1')"),
]
VIEWPORTS = ["1384x805", "820x1180", "390x844"]

# 페이지 안에서 실행해 결과를 JSON 문자열로 돌려준다
PROBE = r"""(() => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(',').map(Number); return {r:v[0],g:v[1],b:v[2],a:v[3] ?? 1}; };
  const L = ({r,g,b}) => [r,g,b].map(x => { x/=255; return x <= 0.03928 ? x/12.92 : ((x+0.055)/1.055)**2.4; }).reduce((s,x,i) => s + x*[0.2126,0.7152,0.0722][i], 0);
  const bgOf = el => { for (let e = el; e; e = e.parentElement) { const s = getComputedStyle(e); if (s.backgroundImage !== 'none') return null; const c = parse(s.backgroundColor); if (c && c.a > 0.6) return c; } return null; };
  const light = document.documentElement.getAttribute('data-theme') === 'light';
  const out = {width: document.documentElement.scrollWidth, view: innerWidth, dark: [], faint: []};
  document.querySelectorAll('.tab-view.active *').forEach(el => {
    if (!el.offsetParent) return;
    const s = getComputedStyle(el);
    if (s.filter && s.filter !== 'none') return;
    const r = el.getBoundingClientRect();
    if (light && r.width >= 160 && r.height >= 40) {
      const c = parse(s.backgroundColor);
      if (c && c.a >= 0.5 && L(c) < 0.05) out.dark.push(String(el.className).split(' ')[0]);
    }
    if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1)) return;
    const fg = parse(s.color), bg = bgOf(el);
    if (!fg || !bg) return;
    const a = L(fg), b = L(bg), ratio = (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
    if (ratio < 2.0) out.faint.push(String(el.className).split(' ')[0] + ' "' + el.textContent.trim().slice(0,12) + '" ' + ratio.toFixed(1));
  });
  out.dark = [...new Set(out.dark)].slice(0,5); out.faint = [...new Set(out.faint)].slice(0,5);
  return JSON.stringify(out);
})()"""


def run(viewport: str, theme: str) -> list:
    steps = [BASE + "/", f"viewport:{viewport}", "wait:3", f"applyTheme('{theme}'); 1"]
    for name, js in SCREENS:
        wait = "wait:7" if name == "summoner" else "wait:4"
        steps += [f"{js}; 1", wait, f"'@@{name}@@' + {PROBE}"]
    try:  # 크롬 하나가 멈춰도 전체가 끝없이 기다리지 않게
        r = subprocess.run([sys.executable, "-X", "utf8", "tests/frontend/cdp_smoke.py", *steps],
                           capture_output=True, text=True, encoding="utf-8", timeout=180)
    except subprocess.TimeoutExpired:
        return [f"[{viewport} {theme}] 시간 초과 (180초): 화면 점검을 끝내지 못함"]
    print(f"  {viewport} {theme} 점검 완료", flush=True)
    problems = []
    for line in r.stdout.splitlines():
        if "EXC" in line or ("LOG error" in line and "vibrate" not in line):
            problems.append(f"[{viewport} {theme}] JS 오류: {line.strip()[:160]}")
        if "@@" in line and line.lstrip().startswith("= "):
            raw = line.split("= ", 1)[1].strip()
            raw = json.loads(raw)  # cdp_smoke 가 문자열을 JSON 따옴표로 감싸 출력
            name, payload = raw.split("@@")[1], json.loads(raw.split("@@")[2])
            if payload["width"] > payload["view"] + 1:
                problems.append(f"[{viewport} {theme}] {name}: 가로 넘침 {payload['width']}px > {payload['view']}px")
            if payload["dark"]:
                problems.append(f"[{viewport} {theme}] {name}: 화이트 모드 어두운 상자 {payload['dark']}")
            if payload["faint"]:
                problems.append(f"[{viewport} {theme}] {name}: 대비 낮은 글자 {payload['faint']}")
    return problems


def main() -> int:
    problems = []
    for vp in VIEWPORTS:
        for theme in ("dark", "light"):
            problems += run(vp, theme)
    if problems:
        print("\n".join(problems))
        print(f"\n문제 {len(problems)}건")
        return 1
    print(f"화면 점검 통과: {len(SCREENS)}개 화면 × {len(VIEWPORTS)}개 폭 × 다크/화이트")
    return 0


if __name__ == "__main__":
    sys.exit(main())
