import subprocess
import time
import json
import urllib.request
import asyncio
import websockets
import sys

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

async def test_frontend_actions():
    port = 9222
    cmd = [
        EDGE_PATH,
        "--headless=new",
        f"--remote-debugging-port={port}",
        "--disable-gpu",
        "--no-sandbox",
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
                await page_ws.send(json.dumps({"id": 2, "method": "Console.enable"}))
                await page_ws.send(json.dumps({"id": 3, "method": "Runtime.enable"}))
                await page_ws.send(json.dumps({"id": 4, "method": "Page.enable"}))
                
                # Navigate to localhost:3000
                await page_ws.send(json.dumps({
                    "id": 5,
                    "method": "Page.navigate",
                    "params": {"url": "http://localhost:3000/"}
                }))

                console_errors = []

                async def recv_until_idle(timeout=2.0):
                    end_time = time.time() + timeout
                    while time.time() < end_time:
                        try:
                            msg_str = await asyncio.wait_for(page_ws.recv(), timeout=0.5)
                            msg = json.loads(msg_str)
                            method = msg.get("method")
                            if method == "Runtime.exceptionThrown":
                                console_errors.append(("Runtime.exceptionThrown", msg.get("params")))
                            elif method == "Console.messageAdded":
                                m = msg.get("params", {}).get("message", {})
                                if m.get("level") in ["error"]:
                                    console_errors.append(("Console.error", m.get("text")))
                        except asyncio.TimeoutError:
                            continue

                await recv_until_idle(3.0)

                async def run_eval(js_code):
                    await page_ws.send(json.dumps({
                        "id": 100,
                        "method": "Runtime.evaluate",
                        "params": {"expression": js_code, "returnByValue": True, "awaitPromise": True}
                    }))
                    while True:
                        resp_str = await page_ws.recv()
                        resp_obj = json.loads(resp_str)
                        if resp_obj.get("id") == 100:
                            return resp_obj.get("result", {}).get("result", {}).get("value")

                print("--- 1. Initial State ---")
                res1 = await run_eval("""(() => {
                    return {
                        activeTab: document.querySelector('.nav-tab.active')?.getAttribute('data-tab'),
                        patchModalExists: !!document.getElementById('patchNotesModal'),
                        searchVal: document.getElementById('searchInput')?.value
                    };
                })()""")
                print(res1)

                print("--- 2. Click Patch Notes Button ---")
                res2 = await run_eval("""(() => {
                    const btn = document.querySelector('.patch-notes-badge') || document.querySelector('[onclick*="PatchNotes"]') || document.querySelector('[onclick*="patchNotes"]');
                    if (btn) {
                        btn.click();
                        const modal = document.getElementById('patchNotesModal');
                        return { clicked: true, modalDisplay: modal ? window.getComputedStyle(modal).display : 'no modal', modalHtmlLen: modal ? modal.innerHTML.length : 0 };
                    }
                    // Try direct function
                    if (typeof window.openPatchNotesModal === 'function') {
                        window.openPatchNotesModal();
                        const modal = document.getElementById('patchNotesModal');
                        return { fnCalled: true, modalDisplay: modal ? window.getComputedStyle(modal).display : 'no modal' };
                    }
                    return { clicked: false, btn: null };
                })()""")
                print(res2)
                await recv_until_idle(1.0)

                print("--- 3. Test Switch to Leaderboard ---")
                res3 = await run_eval("""(() => {
                    window.switchMainTab('leaderboard');
                    const lb = document.getElementById('viewLeaderboard');
                    return {
                        display: lb ? window.getComputedStyle(lb).display : 'none',
                        hasTable: !!document.querySelector('.leaderboard-table, .tier-list-table, table'),
                        tierEmblems: Array.from(document.querySelectorAll('.tier-emblem-img')).map(img => img.src)
                    };
                })()""")
                print(res3)
                await recv_until_idle(1.0)

                print("--- 4. Test Switch to Masters ---")
                res4 = await run_eval("""(() => {
                    window.switchMainTab('masters');
                    const masters = document.getElementById('viewMasters');
                    return {
                        display: masters ? window.getComputedStyle(masters).display : 'none',
                        tierEmblems: Array.from(document.querySelectorAll('#viewMasters .tier-emblem-img')).map(img => img.src)
                    };
                })()""")
                print(res4)
                await recv_until_idle(1.0)

                print("--- 5. Test Search '요네 야스오' (1:1 Matchup) ---")
                res5 = await run_eval("""(() => {
                    const inp = document.getElementById('searchInput');
                    inp.value = '요네 야스오';
                    // Trigger search
                    if (typeof window.handleSearchSubmit === 'function') {
                        window.handleSearchSubmit();
                    } else if (typeof window.performSearch === 'function') {
                        window.performSearch();
                    }
                    const vm = document.getElementById('viewMatchup');
                    return {
                        val: inp.value,
                        viewMatchupDisplay: vm ? window.getComputedStyle(vm).display : 'none',
                        hasActiveMatchup: document.querySelector('.nav-tab.active')?.getAttribute('data-tab')
                    };
                })()""")
                print(res5)
                await recv_until_idle(2.0)

                print("--- 6. Test Search 'Hide on bush#KR1' (Summoner Profile) ---")
                res6 = await run_eval("""(() => {
                    const inp = document.getElementById('searchInput');
                    inp.value = 'Hide on bush#KR1';
                    if (typeof window.handleSearchSubmit === 'function') {
                        window.handleSearchSubmit();
                    } else if (typeof window.performSearch === 'function') {
                        window.performSearch();
                    }
                    return {
                        val: inp.value
                    };
                })()""")
                print(res6)
                await recv_until_idle(3.0)

                res6_after = await run_eval("""(() => {
                    const sp = document.getElementById('summonerProfile') || document.querySelector('.summoner-profile') || document.getElementById('profileContainer');
                    return {
                        profileExists: !!sp,
                        profileDisplay: sp ? window.getComputedStyle(sp).display : 'none',
                        profileLen: sp ? sp.innerHTML.length : 0
                    };
                })()""")
                print("Profile result:", res6_after)

                print("\n=== ANY CONSOLE ERRORS CAPTURED ===")
                for ce in console_errors:
                    print(ce)

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(test_frontend_actions())
