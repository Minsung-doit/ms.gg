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

async def take_screenshots():
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
                
                # Navigate to localhost:3000
                await page_ws.send(json.dumps({
                    "id": 3,
                    "method": "Page.navigate",
                    "params": {"url": "http://localhost:3000/"}
                }))

                await asyncio.sleep(2.5)

                # Capture screenshot 1: Main Home
                await page_ws.send(json.dumps({
                    "id": 4,
                    "method": "Page.captureScreenshot",
                    "params": {"format": "png"}
                }))
                
                while True:
                    msg = json.loads(await page_ws.recv())
                    if msg.get("id") == 4:
                        img_data = base64.b64decode(msg["result"]["data"])
                        with open(OUTPUT_DIR / "screenshot_home.png", "wb") as f:
                            f.write(img_data)
                        print("Saved screenshot_home.png")
                        break

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(take_screenshots())
