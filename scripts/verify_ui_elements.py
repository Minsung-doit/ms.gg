import subprocess
import time
import json
import urllib.request
import asyncio
import websockets
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
port = 9222

async def inspect_ui():
    cmd = [
        EDGE_PATH,
        "--headless=new",
        f"--remote-debugging-port={port}",
        "--disable-gpu",
        "--no-sandbox",
        "--window-size=1600,1000",
        "about:blank"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(20):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as resp:
                    data = json.loads(resp.read().decode())
                    ws_url = data.get("webSocketDebuggerUrl")
                    if ws_url:
                        break
            except Exception:
                time.sleep(0.3)
        
        if not ws_url:
            print("Failed to get debugger URL")
            return

        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": "about:blank"}}))
            resp = json.loads(await ws.recv())
            target_id = resp["result"]["targetId"]

            page_ws_url = f"ws://127.0.0.1:{port}/devtools/page/{target_id}"
            async with websockets.connect(page_ws_url) as page_ws:
                await page_ws.send(json.dumps({"id": 2, "method": "Page.enable"}))
                await page_ws.send(json.dumps({"id": 3, "method": "Runtime.enable"}))
                
                async def eval_js(code):
                    await page_ws.send(json.dumps({
                        "id": 10,
                        "method": "Runtime.evaluate",
                        "params": {"expression": code, "returnByValue": True, "awaitPromise": True}
                    }))
                    while True:
                        msg = json.loads(await page_ws.recv())
                        if msg.get("id") == 10:
                            return msg.get("result", {}).get("result", {}).get("value")

                await page_ws.send(json.dumps({"id": 4, "method": "Page.navigate", "params": {"url": "http://localhost:3000/"}}))
                await asyncio.sleep(2.5)

                # =========================================================
                # 1. Dark & Light Theme Contrast Verification
                # =========================================================
                print("=== 1. THEME CONTRAST TEST ===")
                # Dark Mode
                await eval_js("document.documentElement.setAttribute('data-theme', 'dark')")
                await asyncio.sleep(0.3)
                dark_colors = await eval_js("""(() => {
                    const title = document.querySelector('.brand-title');
                    const tabInactive = document.querySelector('.nav-tab:not(.active)');
                    const tabActive = document.querySelector('.nav-tab.active');
                    return {
                        brandColor: title ? window.getComputedStyle(title).color : null,
                        tabInactiveColor: tabInactive ? window.getComputedStyle(tabInactive).color : null,
                        tabActiveColor: tabActive ? window.getComputedStyle(tabActive).color : null,
                    };
                })()""")
                print(f"[Dark Mode] brand: {dark_colors['brandColor']}, tabInactive: {dark_colors['tabInactiveColor']}, tabActive: {dark_colors['tabActiveColor']}")

                # Light Mode
                await eval_js("document.documentElement.setAttribute('data-theme', 'light')")
                await asyncio.sleep(0.3)
                light_colors = await eval_js("""(() => {
                    const title = document.querySelector('.brand-title');
                    const tabInactive = document.querySelector('.nav-tab:not(.active)');
                    const tabActive = document.querySelector('.nav-tab.active');
                    return {
                        brandColor: title ? window.getComputedStyle(title).color : null,
                        tabInactiveColor: tabInactive ? window.getComputedStyle(tabInactive).color : null,
                        tabActiveColor: tabActive ? window.getComputedStyle(tabActive).color : null,
                    };
                })()""")
                print(f"[Light Mode] brand: {light_colors['brandColor']}, tabInactive: {light_colors['tabInactiveColor']}, tabActive: {light_colors['tabActiveColor']}")

                # =========================================================
                # 2. Leaderboard & Riot Tier Emblems
                # =========================================================
                print("\n=== 2. LEADERBOARD & AUTHENTIC TIER EMBLEMS ===")
                await eval_js("window.switchMainTab('leaderboard')")
                await asyncio.sleep(2.5)
                lb_data = await eval_js("""(() => {
                    const rows = Array.from(document.querySelectorAll('#leaderboardBody .leaderboard-row'));
                    const firstRow = rows[0];
                    const emblemImg = firstRow ? firstRow.querySelector('.tier-emblem-img') : null;
                    const spectrum = document.getElementById('tdSpectrumBar');
                    const segs = spectrum ? spectrum.querySelectorAll('.td-spectrum-seg') : [];
                    return {
                        rowCount: rows.length,
                        firstRanker: firstRow ? firstRow.querySelector('.lb-name')?.innerText?.replace(/\\s+/g, ' ') : null,
                        firstTier: firstRow ? firstRow.querySelector('.lb-tier-cell')?.innerText?.replace(/\\s+/g, ' ') : null,
                        emblemSrc: emblemImg ? emblemImg.src : null,
                        emblemSize: emblemImg ? `${window.getComputedStyle(emblemImg).width} x ${window.getComputedStyle(emblemImg).height}` : null,
                        spectrumSegmentsCount: segs.length
                    };
                })()""")
                print(f"Leaderboard rowCount: {lb_data['rowCount']}")
                print(f"First ranker: {lb_data['firstRanker']}")
                print(f"First tier: {lb_data['firstTier']}")
                print(f"Emblem URL: {lb_data['emblemSrc']}")
                print(f"Emblem size: {lb_data['emblemSize']}")
                print(f"LP Spectrum segments: {lb_data['spectrumSegmentsCount']}")

                # =========================================================
                # 3. 1:1 Matchup ("요네 야스오" search space query)
                # =========================================================
                print("\n=== 3. 1:1 MATCHUP SEARCH (요네 야스오) ===")
                await eval_js("window.switchMainTab('search')")
                await asyncio.sleep(0.5)
                await eval_js("document.getElementById('searchInput').value = '요네 야스오'")
                await eval_js("performSearch('요네 야스오')")
                await asyncio.sleep(2.5)
                mu_data = await eval_js("""(() => {
                    const vm = document.getElementById('viewMatchup');
                    const name1 = document.querySelector('.mu-champ-name');
                    const title1 = document.querySelector('.mu-champ-title');
                    const tracks = Array.from(document.querySelectorAll('.mu-bar-track-wrap'));
                    const barsA = Array.from(document.querySelectorAll('.mu-bar-fill-a'));
                    return {
                        matchupVisible: vm && window.getComputedStyle(vm).display !== 'none',
                        activeTab: document.querySelector('.nav-tab.active')?.getAttribute('data-tab'),
                        champ1Name: name1 ? name1.innerText : null,
                        champ1Color: name1 ? window.getComputedStyle(name1).color : null,
                        champ1TitleColor: title1 ? window.getComputedStyle(title1).color : null,
                        trackCount: tracks.length,
                        firstBarTarget: barsA[0] ? barsA[0].getAttribute('data-target-width') : null
                    };
                })()""")
                print(f"Matchup visible: {mu_data['matchupVisible']}")
                print(f"Active nav tab: {mu_data['activeTab']}")
                print(f"Champ 1 name: {mu_data['champ1Name']} (color: {mu_data['champ1Color']})")
                print(f"Duel progress bar tracks count: {mu_data['trackCount']}")
                print(f"Duel first bar target width: {mu_data['firstBarTarget']}")

                # =========================================================
                # 4. Champion Analytics & Integrated Duo Synergy & Masters ("야스오")
                # =========================================================
                print("\n=== 4. CHAMPION ANALYTICS & MASTERS SHOWCASE (야스오) ===")
                await eval_js("window.switchMainTab('search')")
                await asyncio.sleep(0.5)
                await eval_js("document.getElementById('searchInput').value = '야스오'")
                await eval_js("performSearch('야스오')")
                await asyncio.sleep(2.5)
                champ_data = await eval_js("""(() => {
                    const ca = document.getElementById('championAnalyticsArea');
                    const duoSection = document.querySelector('.champ-duo-synergy-section');
                    const duoTitle = duoSection ? duoSection.querySelector('.champ-duo-title')?.innerText : null;
                    const duoCards = Array.from(document.querySelectorAll('.champ-duo-card'));
                    const partners = duoCards.map(c => c.querySelector('.champ-duo-name span')?.innerText);
                    const coreBuildCards = Array.from(document.querySelectorAll('.champ-v2-card'));
                    const homeTrending = document.getElementById('homeTrendingSection');
                    const mastersSection = document.getElementById('champMastersShowcaseSection');
                    const masterRows = mastersSection ? Array.from(mastersSection.querySelectorAll('.champ-master-horizontal-row')) : [];
                    const firstMaster = masterRows[0];
                    const firstEmblem = firstMaster ? firstMaster.querySelector('.tier-emblem-img') : null;
                    return {
                        analyticsVisible: ca && window.getComputedStyle(ca).display !== 'none',
                        duoSectionFound: !!duoSection,
                        duoTitle: duoTitle,
                        duoPartners: partners,
                        cardCount: coreBuildCards.length,
                        homeTrendingHidden: homeTrending && window.getComputedStyle(homeTrending).display === 'none',
                        mastersSectionFound: !!mastersSection,
                        mastersTitle: mastersSection ? mastersSection.querySelector('.champ-masters-title')?.innerText : null,
                        masterRowsCount: masterRows.length,
                        firstMasterName: firstMaster ? firstMaster.querySelector('.champ-master-game-name')?.innerText : null,
                        firstMasterScore: firstMaster ? firstMaster.querySelector('.champ-master-score-col')?.innerText?.replace(/\\s+/g, ' ') : null,
                        firstMasterEmblemSize: firstEmblem ? `${window.getComputedStyle(firstEmblem).width} x ${window.getComputedStyle(firstEmblem).height}` : null
                    };
                })()""")
                print(f"Analytics visible: {champ_data['analyticsVisible']}")
                print(f"Duo synergy partners: {champ_data['duoPartners']}")
                print(f"Home trending hidden: {champ_data['homeTrendingHidden']}")
                print(f"Masters section title: {champ_data['mastersTitle']}")
                print(f"Masters row count: {champ_data['masterRowsCount']}")
                print(f"Top 1 master: {champ_data['firstMasterName']} ({champ_data['firstMasterScore']})")
                print(f"Top 1 master emblem size: {champ_data['firstMasterEmblemSize']}")

                # =========================================================
                # 5. Skyscraper Wing Ads (Dynamic Blanks Margin)
                # =========================================================
                print("\n=== 5. SKYSCRAPER WING ADS ===")
                sky_data = await eval_js("""(() => {
                    const left = document.getElementById('leftSkyscraperAd');
                    const right = document.getElementById('rightSkyscraperAd');
                    return {
                        leftExists: !!left,
                        rightExists: !!right,
                        leftDisplay: left ? window.getComputedStyle(left).display : null,
                        rightDisplay: right ? window.getComputedStyle(right).display : null,
                        leftLeft: left ? window.getComputedStyle(left).left : null,
                        rightRight: right ? window.getComputedStyle(right).right : null,
                        windowInnerWidth: window.innerWidth
                    };
                })()""")
                print(f"Left ad display: {sky_data['leftDisplay']}, left: {sky_data['leftLeft']}")
                print(f"Right ad display: {sky_data['rightDisplay']}, right: {sky_data['rightRight']}")
                print(f"Viewport width: {sky_data['windowInnerWidth']}px")

                # =========================================================
                # 6. Patch Notes Modal (3 Patches, Continuous Vertical Feed)
                # =========================================================
                print("\n=== 6. PATCH NOTES MODAL ===")
                await eval_js("document.getElementById('btnOpenPatchNotes').click()")
                await asyncio.sleep(1.5)
                pn_data = await eval_js("""(() => {
                    const modal = document.getElementById('patchNotesModal');
                    const tabs = Array.from(document.querySelectorAll('.pn-version-tab'));
                    const sections = Array.from(document.querySelectorAll('.pn-feed-section'));
                    const secTitles = sections.map(s => s.querySelector('.pn-section-title')?.innerText?.replace(/\\s+/g, ' '));
                    const feedCards = Array.from(document.querySelectorAll('.pn-feed-card'));
                    return {
                        modalOpen: modal && (modal.classList.contains('active') || modal.classList.contains('open')),
                        versions: tabs.map(t => t.innerText.trim().replace(/\\s+/g, ' ')),
                        sectionTitles: secTitles,
                        totalFeedCards: feedCards.length
                    };
                })()""")
                print(f"Modal opened: {pn_data['modalOpen']}")
                print(f"Patch version tabs: {pn_data['versions']}")
                print(f"Vertical sections: {pn_data['sectionTitles']}")
                print(f"Total patch cards: {pn_data['totalFeedCards']}")

                # =========================================================
                # 7. Dedicated Admin Domain (localhost:300/admin)
                # =========================================================
                print("\n=== 7. DEDICATED ADMIN DOMAIN (localhost:300/admin) ===")
                try:
                    with urllib.request.urlopen("http://localhost:300/admin", timeout=3) as a_resp:
                        a_html = a_resp.read().decode('utf-8', errors='replace')
                        print(f"Admin proxy status: HTTP {a_resp.status}")
                        print(f"Admin console detected: {'어드민' in a_html or 'Admin' in a_html}")
                except Exception as ex:
                    print(f"Admin proxy test error: {ex}")

                print("\n🎉 ALL 7 ADVANCED UI SUITES INSPECTED COMPREHENSIVELY!")

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(inspect_ui())
