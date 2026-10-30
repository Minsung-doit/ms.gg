import os
import sys
import time
import traceback
import asyncio
import uvicorn
from app.config import settings

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.log")
LOG_MAX_BYTES = 5 * 1024 * 1024

# 로그가 끝없이 커지지 않게: 켤 때 5MB 를 넘었으면 server.log.1 로 옮기고 새로 시작 (한 개만 보관)
try:
    if os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
        os.replace(LOG_FILE, LOG_FILE + ".1")
except OSError:
    pass

# Line-buffered file handle for both stdout and stderr
log_file_obj = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
sys.stdout = log_file_obj
sys.stderr = log_file_obj

async def start_dual_servers():
    config_user = uvicorn.Config(
        "app.main:app",
        host=settings.host,  # 기본 127.0.0.1 (같은 와이파이에 공개하려면 .env에 HOST=0.0.0.0)
        port=settings.port,
        reload=False,
        log_level="warning",
        access_log=False,
        lifespan="on"
    )
    config_admin = uvicorn.Config(
        "app.main:app",
        host="127.0.0.1",  # 관리자 포트는 이 PC에서만 접근
        port=settings.admin_port,
        reload=False,
        log_level="warning",
        access_log=False,
        lifespan="off"
    )
    server_user = uvicorn.Server(config_user)
    server_admin = uvicorn.Server(config_admin)

    await asyncio.gather(
        server_user.serve(),
        server_admin.serve()
    )

def run_with_watchdog():
    print("=" * 60)
    print(f"[{time.ctime()}] carry.gg Dual Server Architecture Starting...")
    print(f"🎮 Public User Storefront: http://localhost:{settings.port}")
    print(f"👑 Dedicated Admin Domain: http://localhost:{settings.admin_port} (and /admin)")
    print("Auto-Restart Watchdog Enabled")
    print("=" * 60)
    log_file_obj.flush()

    while True:
        try:
            asyncio.run(start_dual_servers())
        except Exception as e:
            err_msg = traceback.format_exc()
            print(f"[{time.ctime()}] Server encountered error: {e}\n{err_msg}")
            log_file_obj.flush()
            time.sleep(1)
        else:
            print(f"[{time.ctime()}] Server exited. Auto-restarting in 1 second...")
            log_file_obj.flush()
            time.sleep(1)

if __name__ == "__main__":
    run_with_watchdog()
