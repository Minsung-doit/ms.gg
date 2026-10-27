import hashlib
import hmac
import os
import threading
import time
from fastapi import Request, HTTPException
import app.config as app_config
from app.config import settings

ADMIN_SESSION_TTL = 86400 * 30

def _sign(payload: str) -> str:
    # Password is mixed into the key so changing the admin password revokes every issued token
    key = f"{settings.admin_token_secret}:{settings.admin_password}".encode("utf-8")
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

def generate_admin_token(username: str = "admin", ttl: int = ADMIN_SESSION_TTL) -> str:
    """Issue a signed, expiring admin session token: '<username>.<issued_at>.<expires_at>.<signature>'"""
    issued_at = time.time_ns()
    expires_at = int(time.time()) + int(ttl)
    payload = f"{username}.{issued_at}.{expires_at}"
    return f"{payload}.{_sign(payload)}"

def _revoked_before() -> int:
    try:
        return int(os.getenv("ADMIN_SESSIONS_REVOKED_AT", "0") or 0)
    except ValueError:
        return 0

def revoke_all_admin_sessions() -> None:
    """Logout: every token issued up to now stops working (persisted so it survives restarts)."""
    now = str(time.time_ns())
    os.environ["ADMIN_SESSIONS_REVOKED_AT"] = now
    app_config.safe_set_env_key("ADMIN_SESSIONS_REVOKED_AT", now)

def verify_admin_token(token: str) -> bool:
    try:
        username, issued_at, expires_at, sig = token.rsplit(".", 3)
        if int(expires_at) < time.time() or int(issued_at) <= _revoked_before():
            return False
    except (ValueError, AttributeError):
        return False
    return username == settings.admin_username and hmac.compare_digest(sig, _sign(f"{username}.{issued_at}.{expires_at}"))

def is_admin_authenticated(request: Request) -> bool:
    """Admin is authenticated only by a valid signed session token (cookie or Bearer header)."""
    cookie_token = request.cookies.get("admin_session", "")
    if cookie_token and verify_admin_token(cookie_token):
        return True

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and verify_admin_token(auth_header[7:].strip()):
        return True

    return False

def is_admin_port(request: Request) -> bool:
    """True only when the socket port receiving the request matches settings.admin_port."""
    server = request.scope.get("server")
    if not server or len(server) < 2:
        return False
    try:
        return int(server[1]) == int(settings.admin_port)
    except (TypeError, ValueError):
        return False

def verify_admin_access(request: Request) -> bool:
    """Enforces admin authentication on mutating management/settings endpoints."""
    if not is_admin_port(request):
        raise HTTPException(status_code=404, detail="Not Found")
    if not is_admin_authenticated(request):
        raise HTTPException(
            status_code=401,
            detail="최고 관리자 인증 세션이 필요합니다. 관리자 콘솔(/admin)에서 먼저 로그인해주세요."
        )
    return True


class LoginRateLimiter:
    """Locks an IP out after repeated failed admin logins (in-memory, per process)."""

    def __init__(self, max_failures: int = 5, window_sec: int = 600, lockout_sec: int = 900, max_keys: int = 50000):
        self.max_failures = max_failures
        self.window_sec = window_sec
        self.lockout_sec = lockout_sec
        self.max_keys = max_keys
        self._failures = {}
        self._locked_until = {}
        self._lock = threading.Lock()

    def retry_after(self, ip: str) -> int:
        with self._lock:
            remaining = self._locked_until.get(ip, 0) - time.time()
            return int(remaining) + 1 if remaining > 0 else 0

    def record_failure(self, ip: str) -> None:
        now = time.time()
        with self._lock:
            if len(self._failures) >= self.max_keys:
                # Bound memory: forget stale failure history but keep active lockouts
                self._failures.clear()
                self._locked_until = {k: v for k, v in self._locked_until.items() if v > now}
            recent = [t for t in self._failures.get(ip, []) if now - t < self.window_sec]
            recent.append(now)
            self._failures[ip] = recent
            if len(recent) >= self.max_failures:
                self._locked_until[ip] = now + self.lockout_sec
                self._failures[ip] = []

    def reset(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)
            self._locked_until.pop(ip, None)


admin_login_limiter = LoginRateLimiter()
