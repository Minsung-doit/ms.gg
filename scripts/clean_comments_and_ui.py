import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "templates" / "index.html"
APP_JS = ROOT / "static" / "js" / "app.js"

def clean_index_html():
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        content = f.read()

    orig_len = len(content)
    
    # 1. HTML Comments removal (keep only Pretendard Web Font CDN)
    def comment_replacer(match):
        c = match.group(0)
        if 'Pretendard' in c:
            return c
        return ''

    # Count comments before
    all_comments = re.findall(r'<!--.*?-->', content, flags=re.DOTALL)
    print(f"[index.html] Original comments count: {len(all_comments)}")

    # Replace comments
    content = re.sub(r'<!--(?!\s*(?:\[if|Pretendard|Font Awesome)).*?-->', '', content, flags=re.DOTALL)

    # 2. Remove .ad-spec-desc (all 7 elements)
    ad_desc_pattern = r'[ \t]*<span class="ad-spec-desc">.*?</span>\r?\n?'
    desc_matches = re.findall(ad_desc_pattern, content, flags=re.DOTALL)
    print(f"[index.html] Found .ad-spec-desc elements: {len(desc_matches)}")
    content = re.sub(ad_desc_pattern, '', content, flags=re.DOTALL)

    # 3. Remove .champ-sort-hint
    sort_hint_pattern = r'[ \t]*<div class="champ-sort-hint">.*?</div>\r?\n?'
    hint_matches = re.findall(sort_hint_pattern, content, flags=re.DOTALL)
    print(f"[index.html] Found .champ-sort-hint elements: {len(hint_matches)}")
    content = re.sub(sort_hint_pattern, '', content, flags=re.DOTALL)

    # 4. Refine .fow-path-desc
    old_fow_desc = '<p class="fow-path-desc">관전 바로가기 실행을 위한 리그 오브 레전드 Game 폴더 경로를 지정합니다. 기본 경로는 대부분의 PC에서 자동으로 인식됩니다.</p>'
    new_fow_desc = '<p class="fow-path-desc">리그 오브 레전드 Game 실행 폴더 경로를 설정합니다.</p>'
    if old_fow_desc in content:
        content = content.replace(old_fow_desc, new_fow_desc)
        print("[index.html] Refined .fow-path-desc successfully.")
    else:
        print("[index.html] Warning: old .fow-path-desc text not found exactly.")

    # 5. Clean up excessive consecutive blank lines (more than 2 newlines -> 2 newlines)
    content = re.sub(r'\n{3,}', '\n\n', content)

    # Comments count after
    remaining_comments = re.findall(r'<!--.*?-->', content, flags=re.DOTALL)
    print(f"[index.html] Remaining comments count: {len(remaining_comments)}")

    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[index.html] Completed. Size changed from {orig_len} to {len(content)} bytes.")

def clean_app_js():
    with open(APP_JS, 'r', encoding='utf-8') as f:
        content = f.read()

    orig_len = len(content)

    # 1. HTML comments inside template literals in app.js
    comments_in_js = re.findall(r'<!--.*?-->', content, flags=re.DOTALL)
    print(f"[app.js] Original HTML comments count: {len(comments_in_js)}")
    content = re.sub(r'[ \t]*<!--.*?-->\r?\n?', '', content, flags=re.DOTALL)
    remaining_html_comments = re.findall(r'<!--.*?-->', content, flags=re.DOTALL)
    print(f"[app.js] Remaining HTML comments count: {len(remaining_html_comments)}")

    # 2. Refine amateur / verbose subtitle texts
    replacements = [
        ('한국 서버 솔로랭크 빅데이터 기반 정밀 분석', 'KR 솔로랭크 정밀 분석'),
        ('천상계 맞대결 솔로랭크 빅데이터 기반', '마스터+ 솔로랭크 기준'),
        ('14.20 실시간 랭크 빅데이터 기반', '14.20 랭크 분석 기준'),
        ('실전 맞대결 전술 가이드', '상성 플레이 팁'),
        ('한국 서버 에메랄드+ 솔로랭크 빅데이터', 'KR 에메랄드+ 솔로랭크'),
        ('${c.name} 전체 챔피언 라인전 상성 빅데이터', '${c.name} 전체 라인전 상성 통계')
    ]

    for old_text, new_text in replacements:
        c_count = content.count(old_text)
        content = content.replace(old_text, new_text)
        print(f"[app.js] Replaced '{old_text}' -> '{new_text}': {c_count} occurrences")

    # 3. Clean up excessive consecutive blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)

    with open(APP_JS, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[app.js] Completed. Size changed from {orig_len} to {len(content)} bytes.")

if __name__ == '__main__':
    clean_index_html()
    clean_app_js()
