import json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _load_file_config():
    path = BASE_DIR / "config.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


_FILE_CONFIG = _load_file_config()


def _value(name, default=""):
    env_value = os.getenv(name)
    if env_value is not None and env_value.strip():
        return env_value.strip()
    value = _FILE_CONFIG.get(name.lower())
    return str(value).strip() if value is not None else default


DATA_DIR = Path(os.getenv("DATA_DIR", _FILE_CONFIG.get("data_dir", BASE_DIR / "data")))
DATA_DIR = DATA_DIR if DATA_DIR.is_absolute() else BASE_DIR / DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

DISCORD_TOKEN = _value("DISCORD_TOKEN")
DISCORD_CLIENT_ID = _value("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = _value("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = _value("DISCORD_REDIRECT_URI")
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", _FILE_CONFIG.get("database_path", DATA_DIR / "flame.db")))
DATABASE_PATH = DATABASE_PATH if DATABASE_PATH.is_absolute() else BASE_DIR / DATABASE_PATH

PORT = int(os.getenv("PORT", _FILE_CONFIG.get("port", "10000")))
HOST = os.getenv("HOST", _FILE_CONFIG.get("host", "0.0.0.0"))

BOT_PREFIX = "!"
BOT_NAME = "VoidFlame System"
DASHBOARD_NAME = "VoidFlame System"
OWNER_ID = int(os.getenv("OWNER_ID", _FILE_CONFIG.get("owner_id", "1293157778030071920")))
SUPPORT_SERVER_URL = "https://discord.gg/jH3vwYJyaB"


def _session_secret():
    # Dashboard OAuth is optional. Persist the generated secret so no SESSION_SECRET
    # environment variable is required and sessions survive normal restarts.
    configured = _value("SESSION_SECRET")
    if configured:
        return configured

    secret_file = DATA_DIR / "session.secret"
    try:
        existing = secret_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass

    generated = secrets.token_urlsafe(48)
    try:
        secret_file.write_text(generated, encoding="utf-8")
        try:
            secret_file.chmod(0o600)
        except OSError:
            pass
    except OSError:
        # Ephemeral filesystems can still run the bot; the dashboard session will
        # simply be reset after a restart.
        pass
    return generated


SESSION_SECRET = _session_secret()

if not DISCORD_TOKEN:
    raise RuntimeError(
        "Discord token is missing. Set DISCORD_TOKEN or create config.json "
        "next to bot.py using config.json.example."
    )
