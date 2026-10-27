import asyncio
import json
import urllib.request
import subprocess
import time
import os

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE_PATH):
    EDGE_PATH = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

async def test_tabs():
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--remote-debugging-port=9222",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "http://localhost:3000"
    ]
    proc = subprocess.Popen(cmd)
    try:
        await asyncio.sleep(2)
        # Fetch targets
        req = urllib.request.urlopen("http://127.0.0.1:9222/json")
        targets = json.loads(req.read().decode())
        page_target = next(t for t in targets if t.get("type") == "page")
        ws_url = page_target["webSocketDebuggerUrl"]
        print("WebSocket debugger URL:", ws_url)
    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(test_tabs())
