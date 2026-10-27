import sys, re
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

print('=== 1. index.html UI 내 설명/안내 문구 전수 스캔 ===')
lines = html.splitlines()
for idx, line in enumerate(lines, 1):
    # 가이드, 설명, 팁 관련 키워드 검색
    for kw in ['확인하실 수 있습니다', '확인할 수 있습니다', '표시됩니다', '제공합니다', '비교합니다', 
               '분석합니다', '입력하세요', '클릭하시면', '클릭하면', '찾아보세요', '자동 전환', 
               'tip', 'desc', 'guide', 'notice', 'info-note', 'help', 'hint', 'fow-loading-text', 'fow-path-desc',
               '배너 광고', 'Google AdSense', '스폰서', '광고 문의', '엔지니어링']:
        if kw in line:
            print(f"index.html:{idx} [{kw}] -> {line.strip()[:110]}")

print('\n=== 2. static/js/app.js 내 UI 렌더링 설명/안내 문구 전수 스캔 ===')
with open('static/js/app.js', 'r', encoding='utf-8', errors='ignore') as f:
    js = f.read()

js_lines = js.splitlines()
for idx, line in enumerate(js_lines, 1):
    for kw in ['확인하실 수 있습니다', '확인할 수 있습니다', '표시됩니다', '제공합니다', '비교합니다', 
               '분석합니다', '클릭하시면', '클릭하면', '찾아보세요', '원라이너', '파워쉘', '시뮬레이터',
               '엔지니어링', '완전 은닉', '빅데이터 기반', '전술 가이드', '알림']:
        if kw in line and not line.strip().startswith('//') and not line.strip().startswith('/*'):
            print(f"app.js:{idx} [{kw}] -> {line.strip()[:110]}")
