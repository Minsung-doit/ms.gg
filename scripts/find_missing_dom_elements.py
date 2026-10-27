import re
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent

with open(ROOT / 'templates' / 'index.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
html_ids = set()
for tag in soup.find_all(id=True):
    html_ids.add(tag['id'])

# 프런트 JS는 static/js/app/01~13-*.js 로 나뉘어 있다 (CLAUDE.md)
js_files = sorted((ROOT / 'static' / 'js' / 'app').glob('*.js'))

missing = []

for js_path in js_files:
    js_lines = js_path.read_text(encoding='utf-8').splitlines()
    for line_no, line in enumerate(js_lines, start=1):
        # Match getElementById("...")
        matches = re.findall(r'getElementById\([\'"]([a-zA-Z0-9_\-]+)[\'"]\)', line)
        for elem_id in matches:
            if elem_id not in html_ids:
                missing.append((f"{js_path.name}:{line_no}", elem_id, line.strip()[:100]))

print(f"Total HTML IDs found in index.html: {len(html_ids)}")
print(f"Total missing getElementById references: {len(missing)}")
print("=" * 60)

# Deduplicate
seen = set()
for line_no, elem_id, code in missing:
    if elem_id not in seen:
        seen.add(elem_id)
        print(f"[MISSING ID] '{elem_id}' at {line_no}:\n   {code}")
