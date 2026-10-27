import os
import re
from pathlib import Path

BASE_DIR = Path(".")

print("=== Scanning for Raw SQL Formatting ===")
for p in BASE_DIR.glob("app/**/*.py"):
    content = p.read_text(encoding="utf-8")
    for i, line in enumerate(content.splitlines()):
        if "execute" in line and ("%" in line or "format(" in line or 'f"' in line or "f'" in line):
            print(f"{p}:{i+1}: {line.strip()[:100]}")

print("\n=== Scanning for Subprocess / Shell Execution ===")
for p in BASE_DIR.glob("app/**/*.py"):
    content = p.read_text(encoding="utf-8")
    for i, line in enumerate(content.splitlines()):
        if any(term in line for term in ["subprocess", "os.system", "os.popen", "popen"]):
            print(f"{p}:{i+1}: {line.strip()[:100]}")
