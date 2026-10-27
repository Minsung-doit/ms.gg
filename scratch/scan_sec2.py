import os
import re
from pathlib import Path

BASE_DIR = Path(".")

print("=== Checking CORS, Middleware, Security Headers ===")
content = (BASE_DIR / "app" / "main.py").read_text(encoding="utf-8")
for i, line in enumerate(content.splitlines()[:220]):
    if any(k in line.lower() for k in ["cors", "middleware", "security", "trustedhost", "cookie", "header"]):
        print(f"Line {i+1}: {line}")
