"""static/images/pwa-icon.svg 를 헤드리스 Chrome으로 PNG 아이콘(512·192·180)으로 렌더링한다.

로고를 바꾸면 SVG만 고치고 이 스크립트를 다시 실행한다:
  python scripts/render_pwa_icons.py
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests" / "frontend"))
from cdp_smoke import CDP, CHROME_CANDIDATES, _free_port  # noqa: E402

IMAGES = Path(__file__).resolve().parent.parent / "static" / "images"
TARGETS = {"pwa-icon-512.png": 512, "pwa-icon-192.png": 192, "apple-touch-icon.png": 180}


def main() -> None:
    chrome = next(p for p in CHROME_CANDIDATES if os.path.exists(p))
    port = _free_port()
    proc = subprocess.Popen(
        [chrome, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={tempfile.mkdtemp()}",
         "--remote-allow-origins=*", "--disable-gpu", "--no-first-run", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        page = None
        for _ in range(50):
            try:
                page = [t for t in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read())
                        if t["type"] == "page"][0]
                break
            except Exception:
                time.sleep(0.2)
        c = CDP(page["webSocketDebuggerUrl"])
        c.send("Page.enable")
        svg = (IMAGES / "pwa-icon.svg").read_text(encoding="utf-8")
        for name, size in TARGETS.items():
            html = ("<html><body style='margin:0;background:transparent'>"
                    f"<div style='width:{size}px;height:{size}px'>{svg.replace('<svg ', f'<svg style=\"width:{size}px;height:{size}px\" ', 1)}</div>"
                    "</body></html>")
            c.send("Emulation.setDeviceMetricsOverride", {"width": size, "height": size, "deviceScaleFactor": 1, "mobile": False})
            c.send("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
            c.send("Page.navigate", {"url": "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode()})
            c.pump(1.5)
            shot = c.send("Page.captureScreenshot", {"format": "png", "clip": {"x": 0, "y": 0, "width": size, "height": size, "scale": 1}})
            (IMAGES / name).write_bytes(base64.b64decode(shot["result"]["data"]))
            print("wrote", name, size)
    finally:
        proc.kill()


if __name__ == "__main__":
    main()
