import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def load_env_file(path=None):
    env_path = Path(path or BASE_DIR / ".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-this-secret-key")
    DATABASE_PATH = os.environ.get(
        "DATABASE_PATH",
        str(BASE_DIR / "instance" / "warehouse_dashboard.sqlite3"),
    )
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "")
    WAREHOUSE_MANAGER_EMAIL = os.environ.get("WAREHOUSE_MANAGER_EMAIL", "")


def env_config():
    return {
        "SECRET_KEY": os.environ.get("SECRET_KEY", "dev-change-this-secret-key"),
        "DATABASE_PATH": os.environ.get(
            "DATABASE_PATH",
            str(BASE_DIR / "instance" / "warehouse_dashboard.sqlite3"),
        ),
        "SMTP_HOST": os.environ.get("SMTP_HOST", ""),
        "SMTP_PORT": int(os.environ.get("SMTP_PORT", "587") or 587),
        "SMTP_USERNAME": os.environ.get("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD", ""),
        "SMTP_FROM": os.environ.get("SMTP_FROM", ""),
        "WAREHOUSE_MANAGER_EMAIL": os.environ.get("WAREHOUSE_MANAGER_EMAIL", ""),
    }
