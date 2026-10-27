import os
import secrets
from pathlib import Path
from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)

def safe_set_env_key(key: str, val: str):
    val_str = str(val or "").strip()
    try:
        if not ENV_FILE.exists():
            ENV_FILE.touch()
        set_key(str(ENV_FILE), key, val_str)
    except Exception:
        try:
            content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
            lines = content.splitlines()
            found = False
            new_lines = []
            for line in lines:
                if line.startswith(f"{key}="):
                    new_lines.append(f"{key}={val_str}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"{key}={val_str}")
            ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception:
            pass

def _ensure_secret(key: str, nbytes: int) -> str:
    """Return the env value, or generate a random one and persist it to .env (no hardcoded defaults)."""
    val = os.getenv(key, "").strip()
    if not val:
        val = secrets.token_urlsafe(nbytes)
        os.environ[key] = val
        safe_set_env_key(key, val)
        print(f"[config] {key}가 설정되어 있지 않아 무작위 값을 생성해 {ENV_FILE}에 저장했습니다.")
    return val

class Settings:
    riot_api_key: str = os.getenv("RIOT_API_KEY", "").strip()
    riot_region: str = os.getenv("RIOT_REGION", "kr").strip().lower()
    riot_routing_region: str = os.getenv("RIOT_ROUTING_REGION", "asia").strip().lower()
    port: int = int(os.getenv("PORT", "3000"))
    google_adsense_client_id: str = os.getenv("GOOGLE_ADSENSE_CLIENT_ID", "ca-pub-0000000000000000").strip()
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    @classmethod
    def update_api_key(cls, new_key: str):
        cls.riot_api_key = new_key.strip()
        os.environ["RIOT_API_KEY"] = cls.riot_api_key
        safe_set_env_key("RIOT_API_KEY", cls.riot_api_key)

    @classmethod
    def update_discord_webhook(cls, new_webhook_url: str):
        cls.discord_webhook_url = new_webhook_url.strip()
        os.environ["DISCORD_WEBHOOK_URL"] = cls.discord_webhook_url
        safe_set_env_key("DISCORD_WEBHOOK_URL", cls.discord_webhook_url)

    @classmethod
    def update_telegram_config(cls, bot_token: str = None, chat_id: str = None):
        if bot_token is not None:
            cls.telegram_bot_token = bot_token.strip()
            os.environ["TELEGRAM_BOT_TOKEN"] = cls.telegram_bot_token
            safe_set_env_key("TELEGRAM_BOT_TOKEN", cls.telegram_bot_token)
        if chat_id is not None:
            cls.telegram_chat_id = chat_id.strip()
            os.environ["TELEGRAM_CHAT_ID"] = cls.telegram_chat_id
            safe_set_env_key("TELEGRAM_CHAT_ID", cls.telegram_chat_id)

    host: str = os.getenv("HOST", "127.0.0.1").strip()
    admin_port: int = int(os.getenv("ADMIN_PORT", "300"))
    admin_domain: str = os.getenv("ADMIN_DOMAIN", "localhost:300/admin").strip()
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin").strip()
    admin_password: str = _ensure_secret("ADMIN_PASSWORD", 12)
    admin_token_secret: str = _ensure_secret("ADMIN_TOKEN_SECRET", 32)
    lol_client_path: str = os.getenv("LOL_CLIENT_PATH", "C:\\Riot Games\\League of Legends\\Game").strip()
    # AI 코치 요약 문장 (없으면 규칙 기반 코칭만 표시)
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5").strip()

    @classmethod
    def update_lol_client_path(cls, new_path: str):
        cls.lol_client_path = new_path.strip()
        os.environ["LOL_CLIENT_PATH"] = cls.lol_client_path
        safe_set_env_key("LOL_CLIENT_PATH", cls.lol_client_path)

    @classmethod
    def update_admin_password(cls, new_pw: str):
        cls.admin_password = new_pw.strip()
        os.environ["ADMIN_PASSWORD"] = cls.admin_password
        safe_set_env_key("ADMIN_PASSWORD", cls.admin_password)

settings = Settings()
