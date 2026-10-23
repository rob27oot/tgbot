# bot/utils/notify.py
# ارسال تنبيهات للمشرفين (اخطاء، تذاكر دعم، مدفوعات مشكوك بيها)

import logging

from telegram import Bot
from telegram.error import TelegramError

from bot.config import settings

logger = logging.getLogger(__name__)


async def notify_admins(bot: Bot, text: str) -> None:
    """ارسال رسالة لكل المشرفين. لو واحد منهم ما فتح البوت نتجاهله."""
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=text[:4000])
        except TelegramError as exc:
            logger.warning("Could not notify admin %s: %s", admin_id, exc)