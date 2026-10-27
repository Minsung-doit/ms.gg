import asyncio
import websockets
import urllib.request
import json
import sys
import subprocess
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

async def check():
    port = 9222
    proc = subprocess.Popen([
        EDGE_PATH, "--headless=new", f"--remote-debugging-port={port}", "--disable-gpu", "--no-sandbox", "about:blank"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.5)
        targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read().decode())
        target = targets[0]
        async with websockets.connect(target["webSocketDebuggerUrl"]) as ws:
            async def eval_js(expr):
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}
                }))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == 1:
                        return msg.get("result", {}).get("result", {}).get("value")

            # Navigate and wait for DOMContentLoaded
            await ws.send(json.dumps({"id": 2, "method": "Page.navigate", "params": {"url": "http://localhost:3000/"}}))
            await asyncio.sleep(3.5)

            # Switch to leaderboard
            await eval_js("window.switchMainTab('leaderboard')")
            await asyncio.sleep(2.0)
            cell_html = await eval_js("document.querySelector('.lb-tier-cell')?.outerHTML")
            print("LB TIER CELL:", cell_html)
            
            # Switch to masters
            await eval_js("window.switchMainTab('masters')")
            await asyncio.sleep(2.0)
            m_cell_html = await eval_js("document.querySelector('#viewMasters .masters-tier-cell, #viewMasters [class*=\"tier\"], #viewMasters .master-rank-tier')?.outerHTML")
            print("MASTERS CELL:", m_cell_html)
    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(check())
