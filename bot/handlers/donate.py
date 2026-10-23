# bot/handlers/donate.py
# قسم التبرع: رقم الماستر (قابل للنسخ) + التبرع بنجوم تيليجرام

import html
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot.config import settings
from bot.handlers.menu import ensure_user, safe_edit
from bot.keyboards.subscription_menu import donate_menu_keyboard
from bot.services.payments import send_donation_invoice

logger = logging.getLogger(__name__)


async def donate_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await ensure_user(update)

    if settings.master_phone:
        phone_block = (
            "💳 رقم الماستر (اضغط على الرقم لنسخه):\n"
            f"<code>{html.escape(settings.master_phone)}</code>"
        )
    else:
        phone_block = "💳 رقم الماستر غير متوفر حالياً."

    text = (
        "💰 <b>التبرع</b>\n\n"
        "البوت مجاني ويحتاج مصاريف تشغيل، وأي دعم منك يساعدنا نكمل ونطور 💙\n\n"
        f"{phone_block}\n\n"
        "⭐ أو تبرع بنجوم تيليجرام، اختر المبلغ:"
    )
    await safe_edit(query, text, donate_menu_keyboard(), parse_mode=ParseMode.HTML)


async def donate_stars_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        stars = int(query.data.split(":", 1)[1])
        ok = await send_donation_invoice(context, query.message.chat_id, stars)
    except (ValueError, TelegramError) as exc:
        logger.error("donation invoice failed: %s", exc)
        await query.answer("⚠️ ما گدرت أرسل الفاتورة، حاول مرة ثانية.", show_alert=True)
        return
    if ok:
        await query.answer()
    else:
        await query.answer("❌ مبلغ غير صالح.", show_alert=True)


def get_handlers() -> list:
    return [
        CallbackQueryHandler(donate_menu_callback, pattern=r"^menu:donate$"),
        CallbackQueryHandler(donate_stars_callback, pattern=r"^donate_stars:\d+$"),
    ]