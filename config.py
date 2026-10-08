import json
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_ID = os.getenv("VF_INSTANCE", "").strip()

def _read_json(path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}

BASE_CONFIG = _read_json(BASE_DIR / "config.json")
INSTANCE_CONFIG = _read_json(BASE_DIR / "instances" / INSTANCE_ID / "config.json") if INSTANCE_ID else {}
_FILE_CONFIG = {**BASE_CONFIG, **INSTANCE_CONFIG}

def _value(name, default=""):
    env_value = os.getenv(name)
    if env_value is not None and env_value.strip(): return env_value.strip()
    value = _FILE_CONFIG.get(name.lower())
    return str(value).strip() if value is not None else default

INSTANCE_NAME = _value("INSTANCE_NAME", INSTANCE_ID or "VoidFlame System")
DISCORD_TOKEN = _value("DISCORD_TOKEN")
DISCORD_CLIENT_ID = _value("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = _value("DISCORD_CLIENT_SECRET")
PUBLIC_URL = _value("PUBLIC_URL").rstrip("/")
DISCORD_REDIRECT_URI = _value("DISCORD_REDIRECT_URI") or (f"{PUBLIC_URL}/callback" if PUBLIC_URL else "")
COOKIE_SECURE = _value("COOKIE_SECURE", "false").lower() in {"1","true","yes","on"}
if PUBLIC_URL.startswith("http://"): COOKIE_SECURE = False

try: INSTANCE_GUILD_ID = int(_value("GUILD_ID", "0"))
except (TypeError, ValueError): INSTANCE_GUILD_ID = 0

configured_data = _value("DATA_DIR", f"data/{INSTANCE_ID}" if INSTANCE_ID else "data")
DATA_DIR = Path(configured_data)
DATA_DIR = DATA_DIR if DATA_DIR.is_absolute() else BASE_DIR / DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

configured_db = _value("DATABASE_PATH", str(DATA_DIR / "flame.db"))
DATABASE_PATH = Path(configured_db)
DATABASE_PATH = DATABASE_PATH if DATABASE_PATH.is_absolute() else BASE_DIR / DATABASE_PATH

try: PORT = int(os.getenv("PORT", os.getenv("SERVER_PORT", _FILE_CONFIG.get("port", "26583"))))
except (TypeError, ValueError): PORT = 26583
HOST = os.getenv("HOST", _FILE_CONFIG.get("host", "0.0.0.0")) or "0.0.0.0"
BOT_PREFIX = _FILE_CONFIG.get("prefix", "!") or "!"
BOT_NAME = INSTANCE_NAME
DASHBOARD_NAME = INSTANCE_NAME

try: OWNER_ID = int(os.getenv("OWNER_ID", _FILE_CONFIG.get("owner_id", "1293157778030071920")))
except (TypeError, ValueError): OWNER_ID = 1293157778030071920

SUPPORT_SERVER_URL = "https://discord.gg/jH3vwYJyaB"
HOSTING_PROVIDER = "Morg Hosting"

def _session_secret():
    configured = _value("SESSION_SECRET")
    if configured: return configured
    secret_file = DATA_DIR / "session.secret"
    try:
        existing = secret_file.read_text(encoding="utf-8").strip()
        if existing: return existing
    except OSError: pass
    generated = secrets.token_urlsafe(48)
    try:
        secret_file.write_text(generated, encoding="utf-8")
        try: secret_file.chmod(0o600)
        except OSError: pass
    except OSError: pass
    return generated

SESSION_SECRET = _session_secret()

if not DISCORD_TOKEN:
    raise RuntimeError(f"Discord token is missing for instance {INSTANCE_ID or 'default'}. Set DISCORD_TOKEN or instances/{INSTANCE_ID}/config.json.")
