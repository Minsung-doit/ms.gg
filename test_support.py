"""
Shared helpers for the root-level test scripts.

- admin_client(): a TestClient logged in with a real signed admin session token
  (the app has no test-only auth bypass, so admin endpoints are exercised for real)
- sandbox_env_writes(): stops tests from rewriting the real .env file
- riot_http(handler): answers riot_client's HTTP requests with a local handler (no real Riot API calls)
"""
import contextlib
import app.config as app_config
from fastapi.testclient import TestClient


def sandbox_env_writes() -> None:
    app_config.safe_set_env_key = lambda key, val: None


def use_temp_db() -> None:
    """Point the app at a fresh temporary SQLite file so tests never write fixture rows into opgg.db."""
    import tempfile
    from pathlib import Path
    import app.database as database

    database.DB_PATH = Path(tempfile.mkdtemp(prefix="opgg_test_")) / "test.db"
    database.init_db()


def admin_client(app, **kwargs) -> TestClient:
    from app.admin_auth import generate_admin_token
    from app.config import settings
    cookies = {"admin_session": generate_admin_token(settings.admin_username)}
    if "cookies" in kwargs:
        cookies.update(kwargs.pop("cookies"))
    base_url = kwargs.pop("base_url", f"http://testserver:{settings.admin_port}")
    return TestClient(app, base_url=base_url, cookies=cookies, **kwargs)


@contextlib.contextmanager
def riot_http(handler):
    """
    Route every HTTP request riot_client makes to handler(httpx.Request) -> httpx.Response.
    Method stubs that other tests installed on the riot_client instance are lifted for the duration,
    so the real URL building / status handling code runs.
    """
    import httpx
    import app.riot_client as rc

    original_client = httpx.AsyncClient

    class MockAsyncClient(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    stubs = {k: v for k, v in vars(rc.riot_client).items() if callable(v)}
    for k in stubs:
        delattr(rc.riot_client, k)
    rc.httpx.AsyncClient = MockAsyncClient
    try:
        yield
    finally:
        rc.httpx.AsyncClient = original_client
        for k, v in stubs.items():
            setattr(rc.riot_client, k, v)
