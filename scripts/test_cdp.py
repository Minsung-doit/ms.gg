import subprocess
import time
import urllib.request
import json
import asyncio
import os

EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# Start Edge with remote debugging
proc = subprocess.Popen([
    EDGE_EXE,
    "--headless",
    "--remote-debugging-port=9222",
    "--disable-gpu",
    "about:blank"
])

time.sleep(2)

try:
    with urllib.request.urlopen("http://localhost:9222/json") as resp:
        targets = json.loads(resp.read().decode())
        print("Edge targets:", targets)
except Exception as e:
    print("Failed to reach Edge debug port:", e)
finally:
    proc.kill()
