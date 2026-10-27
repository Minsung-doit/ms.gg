import re
import sys
import subprocess
import time

# Ensure UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# 공개 포트(3000)만 터널로 내보낸다. 관리자 포트(300)는 절대 터널로 열지 않는다.
# StrictHostKeyChecking=no 는 중간자 공격을 허용하므로 accept-new(최초 1회만 신뢰, 이후 키 변경 시 차단)를 쓴다.
cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-R", "80:127.0.0.1:3000", "nokey@localhost.run"]

print("\n========================================================", flush=True)
print("  OPGG 외부 공유 링크 생성 중입니다. 잠시만 기다려주세요...", flush=True)
print("========================================================\n", flush=True)
print("  [주의] 링크를 아는 사람은 누구나 이 PC의 사이트에 접속할 수 있습니다.", flush=True)
print("         공개 포트에서도 /admin 로그인 화면이 열리므로 ADMIN_PASSWORD를 길고 고유하게 유지하세요.", flush=True)
print("         공유가 끝나면 바로 창을 닫으세요.\n", flush=True)

proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    errors="ignore",
    bufsize=1
)

url_found = None
url_pattern = re.compile(r"https://[a-zA-Z0-9.-]+\.lhr\.life")

while True:
    line = proc.stdout.readline()
    if not line:
        break
    match = url_pattern.search(line)
    if match:
        url_found = match.group(0)
        break

if url_found:
    # Copy to Windows clipboard
    try:
        subprocess.run("clip", input=url_found, text=True, check=True)
        clipboard_msg = "✅ 클립보드에 자동 복사되었습니다! (디스코드에서 Ctrl + V 누르면 바로 붙여넣기 가능)"
    except Exception:
        clipboard_msg = "마우스로 위 링크를 드래그하여 복사하세요."

    print("\n" + "="*65, flush=True)
    print("  🎉 외부 공유 링크가 성공적으로 생성되었습니다!", flush=True)
    print("="*65, flush=True)
    print(f"\n  👉 친구에게 보낼 웹사이트 주소:", flush=True)
    print(f"     \033[92m\033[1m{url_found}\033[0m\n", flush=True)
    print(f"  {clipboard_msg}", flush=True)
    print("\n" + "="*65, flush=True)
    print("  [안내] 공유를 끝내려면 이 창을 닫으시거나 Ctrl + C를 누르세요.", flush=True)
    print("="*65 + "\n", flush=True)

    try:
        while proc.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        proc.terminate()
else:
    print("\n❌ 링크 생성에 실패했습니다. 다시 시도해 주세요.", flush=True)
    proc.terminate()
