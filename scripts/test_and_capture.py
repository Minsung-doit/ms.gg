import subprocess
import time
import json
import urllib.request
import asyncio
import websockets
import base64
from pathlib import Path

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
OUTPUT_DIR = Path(__file__).resolve().parent

async def test_and_capture_actions():
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
                await asyncio.sleep(2.0)

                # 2. Click Patch Notes
                print("Clicking Patch Notes...")
                res = await eval_js("""(() => {
                    const btn = document.querySelector('.patch-notes-badge');
                    if (btn) btn.click();
                    const m = document.getElementById('patchNotesModal');
                    return { clicked: !!btn, display: m ? window.getComputedStyle(m).display : 'null' };
                })()""")
                print("Patch Notes:", res)
                await asyncio.sleep(0.5)
                await snap("screenshot_patch_notes.png")

                # Close modal if open
                await eval_js("""(() => {
                    const btn = document.getElementById('btnClosePatchNotesModal');
                    if (btn) btn.click();
                })()""")
                await asyncio.sleep(0.5)

                # 3. Click Light Mode
                print("Clicking Light Mode...")
                res_light = await eval_js("""(() => {
                    const btn = document.getElementById('themeToggleBtn');
                    if (btn) btn.click();
                    return { theme: document.documentElement.getAttribute('data-theme') };
                })()""")
                print("Theme:", res_light)
                await asyncio.sleep(0.5)
                await snap("screenshot_light_mode.png")

                # 4. Click Summoner Ranking (Leaderboard) in light mode
                print("Clicking Leaderboard...")
                await eval_js("window.switchMainTab('leaderboard')")
                await asyncio.sleep(1.0)
                await snap("screenshot_leaderboard_light.png")

                # Toggle back to dark mode
                await eval_js("""(() => {
                    const btn = document.getElementById('themeToggleBtn');
                    if (btn) btn.click();
                })()""")
                await asyncio.sleep(0.5)
                await snap("screenshot_leaderboard_dark.png")

                # 5. Click "요네 야스오 (1:1 상성)" chip
                print("Clicking 1:1 matchup chip...")
                await eval_js("window.switchMainTab('search')")
                await asyncio.sleep(0.5)
                res_matchup = await eval_js("""(() => {
                    const chips = Array.from(document.querySelectorAll('.saas-chip, button'));
                    const matchupChip = chips.find(c => c.innerText.includes('요네 야스오'));
                    if (matchupChip) {
                        matchupChip.click();
                        return { clicked: true, text: matchupChip.innerText };
                    }
                    return { clicked: false };
                })()""")
                print("Matchup chip:", res_matchup)
                await asyncio.sleep(1.5)
                await snap("screenshot_matchup_result.png")

                # 6. Click "야스오 (듀오 시너지 & 빌드)" chip
                print("Clicking Duo synergy chip...")
                await eval_js("window.switchMainTab('search')")
                await asyncio.sleep(0.5)
                res_duo = await eval_js("""(() => {
                    const chips = Array.from(document.querySelectorAll('.saas-chip, button'));
                    const duoChip = chips.find(c => c.innerText.includes('듀오 시너지'));
                    if (duoChip) {
                        duoChip.click();
                        return { clicked: true, text: duoChip.innerText };
                    }
                    return { clicked: false };
                })()""")
                print("Duo chip:", res_duo)
                await asyncio.sleep(1.5)
                await snap("screenshot_duo_result.png")

                # 7. Click Summoner Search "Hide on bush#KR1"
                print("Clicking Hide on bush chip...")
                await eval_js("window.switchMainTab('search')")
                await asyncio.sleep(0.5)
                res_faker = await eval_js("""(() => {
                    const chips = Array.from(document.querySelectorAll('.saas-chip, button'));
                    const fakerChip = chips.find(c => c.innerText.includes('Hide on bush'));
                    if (fakerChip) {
                        fakerChip.click();
                        return { clicked: true, text: fakerChip.innerText };
                    }
                    return { clicked: false };
                })()""")
                print("Faker chip:", res_faker)
                await asyncio.sleep(2.0)
                await snap("screenshot_faker_result.png")

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(test_and_capture_actions())
