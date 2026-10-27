import subprocess
import time
import urllib.request
import json
import os

EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
LOG_FILE = os.path.abspath("edge_debug.log")
if os.path.exists(LOG_FILE):
    os.remove(LOG_FILE)

# Run Edge with logging
cmd = [
    EDGE_EXE,
    "--headless",
    "--enable-logging",
    f"--log-file={LOG_FILE}",
    "--v=1",
    "--dump-dom",
    "http://localhost:3000/"
]

p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
stdout, stderr = p.communicate(timeout=10)

print(f"Edge exited with code {p.returncode}")
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        log_content = f.read()
        print("=== EDGE LOG CONTENT ===")
        print(log_content[:3000])
else:
    print("No log file produced.")
