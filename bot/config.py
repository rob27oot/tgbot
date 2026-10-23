# bot/config.py
# تحميل متغيرات البيئة من ملف .env والتحقق منها

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)


def _get_int(name: str, default: int) -> int:
    """قراءة رقم صحيح من البيئة مع قيمة افتراضية."""
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"القيمة {name} لازم تكون رقم صحيح")


def _get_admin_ids() -> list[int]:
    """تحويل ADMIN_IDS من نص إلى قائمة أرقام."""
    raw = os.getenv("ADMIN_IDS", "").strip()
    if not raw:
        return []
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise RuntimeError("ADMIN_IDS لازم تكون أرقام مفصولة بفاصلة")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    master_phone: str
    support_username: str
    admin_ids: list[int]
    database_url: str
    max_file_size_mb: int
    daily_free_downloads: int
    download_dir: Path

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


def load_settings() -> Settings:
    """تحميل الإعدادات والتحقق من وجود القيم الأساسية."""
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN فارغ. حطه بملف .env")

    download_dir = BASE_DIR / "downloads"
    download_dir.mkdir(exist_ok=True)

    return Settings(
        bot_token=token,
        master_phone=os.getenv("MASTER_PHONE", "").strip(),
        support_username=os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@"),
        admin_ids=_get_admin_ids(),
        database_url=os.getenv(
            "DATABASE_URL", "sqlite+aiosqlite:///./bot.db"
        ).strip(),
        max_file_size_mb=_get_int("MAX_FILE_SIZE_MB", 50),
        daily_free_downloads=_get_int("DAILY_FREE_DOWNLOADS", 3),
        download_dir=download_dir,
    )


settings = load_settings()