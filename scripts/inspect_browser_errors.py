import subprocess
import time
import json
import urllib.request
import asyncio
import websockets
import sys

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

async def capture_browser_console():
    # Start Edge in headless mode with remote debugging
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
        # Wait for port to open
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
            # Create a new target / page
            await ws.send(json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": "about:blank"}}))
            resp = json.loads(await ws.recv())
            target_id = resp["result"]["targetId"]

            # Connect to page target
            page_ws_url = f"ws://127.0.0.1:{port}/devtools/page/{target_id}"
            async with websockets.connect(page_ws_url) as page_ws:
                # Enable Console and Runtime
                await page_ws.send(json.dumps({"id": 2, "method": "Console.enable"}))
                await page_ws.send(json.dumps({"id": 3, "method": "Runtime.enable"}))
                await page_ws.send(json.dumps({"id": 4, "method": "Network.enable"}))
                
                # Navigate to localhost:3000
                await page_ws.send(json.dumps({
                    "id": 5,
                    "method": "Page.navigate",
                    "params": {"url": "http://localhost:3000/"}
                }))

                console_messages = []
                runtime_exceptions = []
                failed_requests = []

                # Listen for events for 5 seconds
                request_map = {}

                # Enable Page
                await page_ws.send(json.dumps({"id": 50, "method": "Page.enable"}))

                start_time = time.time()
                while time.time() - start_time < 5:
                    try:
                        msg_str = await asyncio.wait_for(page_ws.recv(), timeout=1.0)
                        msg = json.loads(msg_str)
                        method = msg.get("method")
                        params = msg.get("params", {})
                        
                        if method == "Network.requestWillBeSent":
                            req_id = params.get("requestId")
                            req_url = params.get("request", {}).get("url")
                            request_map[req_id] = req_url
                        elif method == "Console.messageAdded":
                            console_messages.append(params.get("message"))
                        elif method == "Runtime.exceptionThrown":
                            runtime_exceptions.append(params.get("exceptionDetails"))
                        elif method == "Runtime.consoleAPICalled":
                            console_messages.append(params)
                        elif method == "Network.responseReceived":
                            status = params.get("response", {}).get("status")
                            url = params.get("response", {}).get("url")
                            if status >= 400:
                                failed_requests.append(f"{status}: {url}")
                        elif method == "Network.loadingFailed":
                            req_id = params.get("requestId")
                            url = request_map.get(req_id, "unknown")
                            failed_requests.append(f"FAILED: {params.get('errorText')} - {url}")
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        print(f"Error receiving: {e}")
                        break

                # Evaluate state of frontend
                eval_script = """(() => {
                    const views = Array.from(document.querySelectorAll('.tab-view')).map(el => ({
                        id: el.id,
                        display: window.getComputedStyle(el).display,
                        htmlLen: el.innerHTML.length,
                        textSnippet: el.innerText.trim().slice(0, 100)
                    }));
                    return {
                        title: document.title,
                        bodyLen: document.body.innerHTML.length,
                        hasAppJs: typeof window.switchMainTab === 'function',
                        hasSearchInput: !!document.getElementById('searchInput'),
                        views: views,
                        windowErrors: window._caughtErrors || []
                    };
                })()"""
                await page_ws.send(json.dumps({
                    "id": 99,
                    "method": "Runtime.evaluate",
                    "params": {"expression": eval_script, "returnByValue": True}
                }))
                
                eval_val = None
                for _ in range(20):
                    resp_str = await page_ws.recv()
                    resp_obj = json.loads(resp_str)
                    if resp_obj.get("id") == 99:
                        eval_val = resp_obj.get("result", {}).get("result", {}).get("value")
                        break

                print("=== PAGE EVALUATION ===")
                print(json.dumps(eval_val, indent=2, ensure_ascii=False))

                print("=== RUNTIME EXCEPTIONS ===")
                for exc in runtime_exceptions:
                    print(json.dumps(exc, indent=2, ensure_ascii=False))

                print("\n=== CONSOLE MESSAGES (Error / Warn) ===")
                for msg in console_messages:
                    mtype = msg.get("type") or msg.get("level")
                    if mtype in ["error", "warning", "assert"]:
                        print(json.dumps(msg, indent=2, ensure_ascii=False))

                print("\n=== FAILED REQUESTS (>= 400) ===")
                for fr in failed_requests:
                    print(fr)

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(capture_browser_console())
