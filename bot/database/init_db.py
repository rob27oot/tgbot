# bot/database/init_db.py
# إنشاء الاتصال بقاعدة البيانات والجداول (مع اضافة الأعمدة الجديدة تلقائياً)
# للتشغيل اليدوي: python -m bot.database.init_db

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from bot.database.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# أعمدة اضيفت بعد الاصدار الأول (SQLite ما يضيف أعمدة جديدة لجدول موجود)
_NEW_COLUMNS = {
    "users": {"banned": "BOOLEAN NOT NULL DEFAULT 0"},
    "payments": {"refunded": "BOOLEAN NOT NULL DEFAULT 0"},
}


async def _add_missing_columns(conn) -> None:
    if engine.dialect.name != "sqlite":
        return
    for table, columns in _NEW_COLUMNS.items():
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in result.fetchall()}
        for name, ddl in columns.items():
            if name not in existing:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                logger.info("Added column %s.%s", table, name)


async def init_db() -> None:
    """انشاء كل الجداول اذا مو موجودة + اضافة الأعمدة الناقصة."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_columns(conn)
    logger.info("Database tables are ready")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_db())
    print("تم انشاء الجداول بنجاح")