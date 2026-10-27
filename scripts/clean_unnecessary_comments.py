#!/usr/bin/env python3
"""
Clean Unnecessary Comments Script (정리 스크립트)
- static/js/app.js: 불필요한 장식용 구분선(// ===, // ---) 및 중복 주석 제거
- static/css/style.css: 불필요한 장식용 구분선(/* === */) 제거
- app/main.py & app/duo_finder_engine.py: 불필요한 장식용 구분선(# ===, # ---) 제거
"""

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

TARGETS = [
    ("static/js/app.js", r'(?m)^\s*//\s*[-=]{5,}\s*\n'),
    ("static/css/style.css", r'(?m)^\s*/\*\s*[-=]{5,}.*?\*/\s*\n'),
    ("app/main.py", r'(?m)^\s*#\s*[-=]{5,}\s*\n'),
    ("app/duo_finder_engine.py", r'(?m)^\s*#\s*[-=]{5,}\s*\n'),
]

def clean_comments():
    total_removed = 0
    for rel_path, pattern in TARGETS:
        file_path = BASE_DIR / rel_path
        if not file_path.exists():
            continue
        text = file_path.read_text(encoding="utf-8")
        orig_count = len(text.splitlines())
        cleaned = re.sub(pattern, '', text)
        new_count = len(cleaned.splitlines())
        removed = orig_count - new_count
        if removed > 0:
            file_path.write_text(cleaned, encoding="utf-8")
            print(f"[CLEANED] {rel_path}: {removed}개의 불필요한 주석 구분선 제거 완료 ({orig_count} -> {new_count} lines)")
            total_removed += removed
        else:
            print(f"[UNCHANGED] {rel_path}: 이미 정갈함 유지 중")

    print(f"\n총 {total_removed}개의 불필요한 주석 라인이 성공적으로 정리되었습니다.")

if __name__ == "__main__":
    clean_comments()
