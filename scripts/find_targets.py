import sys, os
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

keywords = [
    '헤드투헤드',
    'Head-to-Head',
    '오브젝트 & 팀 골드',
    '원라이너',
    '빠른 소환사 관전',
    '챔피언을 선택해주세요',
    '상단 검색창에 초성',
    '블루팀 전력 우세',
    '주도권 우위 라이너'
]

for root, dirs, files in os.walk('.'):
    if '.git' in root or '.gemini' in root or '__pycache__' in root:
        continue
    for f in files:
        if not f.endswith(('.py', '.html', '.js', '.css', '.json')):
            continue
        fp = os.path.join(root, f)
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as file:
                lines = file.readlines()
            for idx, line in enumerate(lines, 1):
                for kw in keywords:
                    if kw in line:
                        print(f"{fp}:{idx} -> [{kw}] {line.strip()[:100]}")
        except Exception as e:
            pass
