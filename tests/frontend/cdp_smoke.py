"""헤드리스 Chrome(CDP)으로 페이지를 열고 JS 단계를 실행한 뒤 콘솔 오류·예외·HTTP 4xx/5xx를 출력한다.

사용 예:
  python tests/frontend/cdp_smoke.py http://127.0.0.1:3100/ "wait:3" "document.title"

라이엇 API를 직접 부르지 않는다. 로컬 서버(PORT=3100)만 대상으로 쓴다.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def _free_port():
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


DEBUG_PORT = _free_port()  # 다른 세션의 디버깅 크롬과 겹치지 않도록 매번 빈 포트 사용


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.i = 0
        self.events = []

    def send(self, method, params=None):
        self.i += 1
        mid = self.i
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                return msg
            self.events.append(msg)

    def pump(self, seconds):
        end = time.time() + seconds
        self.ws.settimeout(0.2)
        while time.time() < end:
            try:
                self.events.append(json.loads(self.ws.recv()))
            except Exception:
                pass
        self.ws.settimeout(30)

    def eval(self, expr):
        r = self.send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
        res = r.get("result", {})
        if "exceptionDetails" in res:
            d = res["exceptionDetails"]
            return "EXC: " + str(d.get("exception", {}).get("description", d.get("text")))[:500]
        return res.get("result", {}).get("value")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    url = sys.argv[1]
    steps = sys.argv[2:]
    chrome = next(p for p in CHROME_CANDIDATES if os.path.exists(p))
    profile = tempfile.mkdtemp(prefix="cdp_smoke_")
    proc = subprocess.Popen(
        [chrome, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}", f"--user-data-dir={profile}",
         "--remote-allow-origins=*", "--disable-gpu", "--no-first-run", "--window-size=1400,900", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        page = None
        for _ in range(50):
            try:
                targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json").read())
                page = [t for t in targets if t["type"] == "page"][0]
                break
            except Exception:
                time.sleep(0.2)
        c = CDP(page["webSocketDebuggerUrl"])
        for domain in ("Runtime", "Log", "Network", "Page"):
            c.send(domain + ".enable")
        c.send("Page.navigate", {"url": url})
        c.pump(5)
        for step in steps:
            if step.startswith("wait:"):
                c.pump(float(step[5:]))
                continue
            if step.startswith("viewport:"):  # viewport:390x844 (모바일 폭 확인용)
                w, h = (int(v) for v in step[9:].split("x"))
                c.send("Emulation.setDeviceMetricsOverride",
                       {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 800})
                c.pump(1)
                continue
            if step.startswith("shot:"):  # shot:<파일경로.png> 현재 화면 캡처
                import base64
                data = c.send("Page.captureScreenshot", {"format": "png"})
                with open(step[5:], "wb") as f:
                    f.write(base64.b64decode((data.get("result") or data).get("data", "")))
                print(">> screenshot", step[5:])
                continue
            print(">>", step[:160])
            print("   =", json.dumps(c.eval(step), ensure_ascii=False)[:4000])
            c.pump(1.5)
        for e in c.events:
            m = e.get("method")
            p = e.get("params", {})
            if m == "Runtime.exceptionThrown":
                d = p["exceptionDetails"]
                desc = d.get("exception", {}).get("description", d.get("text"))
                print("EXCEPTION:", str(desc)[:400], d.get("url", ""), d.get("lineNumber"))
            elif m == "Runtime.consoleAPICalled" and p["type"] in ("error", "warning", "assert"):
                print("CONSOLE", p["type"], " ".join(str(a.get("value", a.get("description", ""))) for a in p["args"])[:400])
            elif m == "Log.entryAdded" and p["entry"]["level"] in ("error", "warning"):
                print("LOG", p["entry"]["level"], p["entry"]["text"][:300], p["entry"].get("url", ""))
            elif m == "Network.responseReceived" and p["response"]["status"] >= 400:
                print("HTTP", p["response"]["status"], p["response"]["url"])
    finally:
        proc.kill()


if __name__ == "__main__":
    main()
