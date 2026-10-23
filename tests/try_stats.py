# tests/try_stats.py
# اختبار نص الاحصائيات بدون تيليجرام: python -m tests.try_stats

import asyncio

from bot.config import settings
from bot.database import crud
from bot.database.init_db import init_db
from bot.handlers.stats import build_stats_text


async def main() -> None:
    await init_db()
    admin_id = settings.admin_ids[0] if settings.admin_ids else 111
    await crud.get_or_create_user(admin_id, "admin", "Admin")
    await crud.record_download(
        admin_id, "tiktok", "https://tiktok.com/x", "free", title="test", size_bytes=1000
    )
    print(await build_stats_text(admin_id))


asyncio.run(main())