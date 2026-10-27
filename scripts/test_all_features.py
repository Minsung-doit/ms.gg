import subprocess
import time
import json
import urllib.request
import asyncio
import websockets
import base64
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
OUTPUT_DIR = Path(__file__).resolve().parent

async def test_all_features():
    port = 9222
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

                async def snap(filename):
                    await page_ws.send(json.dumps({
                        "id": 20,
                        "method": "Page.captureScreenshot",
                        "params": {"format": "png"}
                    }))
                    while True:
                        msg = json.loads(await page_ws.recv())
                        if msg.get("id") == 20:
                            img_data = base64.b64decode(msg["result"]["data"])
                            with open(OUTPUT_DIR / filename, "wb") as f:
                                f.write(img_data)
                            print(f"Saved {filename}")
                            break

                # 1. Load Home
                await page_ws.send(json.dumps({"id": 4, "method": "Page.navigate", "params": {"url": "http://localhost:3000/"}}))
                await asyncio.sleep(2.5)

                # 2. Click Theme Toggle Button (#btnThemeToggle)
                print("1. Testing Theme Toggle...")
                theme_before = await eval_js("document.documentElement.getAttribute('data-theme')")
                print(f"Theme before click: {theme_before}")
                click_res = await eval_js("""(() => {
                    const btn = document.getElementById('btnThemeToggle');
                    if (btn) {
                        btn.click();
                        return { found: true, currentTheme: document.documentElement.getAttribute('data-theme') };
                    }
                    return { found: false };
                })()""")
                print(f"Theme click result: {click_res}")
                await asyncio.sleep(0.5)
                await snap("step1_theme_light.png")

                # 3. Click Patch Notes (#btnOpenPatchNotes)
                print("2. Testing Patch Notes Modal...")
                pn_res = await eval_js("""(() => {
                    const btn = document.getElementById('btnOpenPatchNotes');
                    if (btn) {
                        btn.click();
                        const m = document.getElementById('patchNotesModal');
                        return {
                            found: true,
                            modalDisplay: m ? window.getComputedStyle(m).display : 'none',
                            modalClasses: m ? m.className : '',
                            modalBodyText: document.getElementById('patchNotesModalBody')?.innerText.slice(0, 150)
                        };
                    }
                    return { found: false };
                })()""")
                print(f"Patch Notes modal result: {pn_res}")
                await asyncio.sleep(1.0)
                # Check after async fetch
                pn_after = await eval_js("""(() => {
                    const m = document.getElementById('patchNotesModal');
                    return {
                        modalDisplay: m ? window.getComputedStyle(m).display : 'none',
                        modalBodyText: document.getElementById('patchNotesModalBody')?.innerText.slice(0, 150)
                    };
                })()""")
                print(f"Patch Notes body after 1s: {pn_after}")
                await snap("step2_patch_notes_modal.png")

                # Close modal
                await eval_js("""(() => {
                    const btn = document.getElementById('btnClosePatchNotesModal');
                    if (btn) btn.click();
                })()""")
                await asyncio.sleep(0.5)

                # 4. Switch to Leaderboard
                print("3. Testing Leaderboard...")
                await eval_js("window.switchMainTab('leaderboard')")
                await asyncio.sleep(1.0)
                lb_res = await eval_js("""(() => {
                    const rows = Array.from(document.querySelectorAll('#leaderboardTableBody tr'));
                    return {
                        rowCount: rows.length,
                        firstRowHtml: rows[0] ? rows[0].innerHTML.slice(0, 300) : 'no rows'
                    };
                })()""")
                print(f"Leaderboard: {lb_res}")
                await snap("step3_leaderboard.png")

                # 5. Search for "요네 야스오"
                print("4. Testing 1:1 Matchup Search...")
                await eval_js("window.switchMainTab('search')")
                await asyncio.sleep(0.5)
                m_res = await eval_js("""(() => {
                    const inp = document.getElementById('searchInput');
                    inp.value = '요네 야스오';
                    performSearch('요네 야스오');
                })()""")
                await asyncio.sleep(2.0)
                m_state = await eval_js("""(() => {
                    const vm = document.getElementById('viewMatchup');
                    return {
                        viewMatchupDisplay: vm ? window.getComputedStyle(vm).display : 'none',
                        activeTab: document.querySelector('.nav-tab.active')?.getAttribute('data-tab'),
                        c1Val: document.getElementById('matchupChamp1Input')?.value,
                        c2Val: document.getElementById('matchupChamp2Input')?.value,
                        headerTitle: document.querySelector('#viewMatchup .matchup-header')?.innerText
                    };
                })()""")
                print(f"Matchup search result: {m_state}")
                await snap("step4_matchup_page.png")

                # 6. Search for "야스오" (Champion analytics with duo synergy integrated)
                print("5. Testing Champion Search...")
                await eval_js("window.switchMainTab('search')")
                await asyncio.sleep(0.5)
                c_res = await eval_js("""(() => {
                    const inp = document.getElementById('searchInput');
                    inp.value = '야스오';
                    performSearch('야스오');
                })()""")
                await asyncio.sleep(2.0)
                c_state = await eval_js("""(() => {
                    const ca = document.getElementById('championAnalyticsArea');
                    const duoSection = document.getElementById('champDuoSynergySection') || document.querySelector('.champ-duo-synergy');
                    return {
                        caDisplay: ca ? window.getComputedStyle(ca).display : 'none',
                        duoSectionExists: !!duoSection,
                        duoSectionDisplay: duoSection ? window.getComputedStyle(duoSection).display : 'none',
                        caTitle: ca ? ca.querySelector('h2, .champ-header-name')?.innerText : 'none'
                    };
                })()""")
                print(f"Champion search result: {c_state}")
                await snap("step5_champion_page.png")

                # 7. Search for "Hide on bush#KR1" (Summoner search)
                print("6. Testing Summoner Search...")
                await eval_js("window.switchMainTab('search')")
                await asyncio.sleep(0.5)
                await eval_js("""(() => {
                    const inp = document.getElementById('searchInput');
                    inp.value = 'Hide on bush#KR1';
                    performSearch('Hide on bush#KR1');
                })()""")
                await asyncio.sleep(2.0)
                f_state = await eval_js("""(() => {
                    const cards = Array.from(document.querySelectorAll('.player-card'));
                    return {
                        cardCount: cards.length,
                        firstCardText: cards[0] ? cards[0].innerText.slice(0, 200) : 'no card'
                    };
                })()""")
                print(f"Summoner search result: {f_state}")
                await snap("step6_summoner_result.png")

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(test_all_features())
