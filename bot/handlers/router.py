# bot/handlers/router.py
# موجّه الرسائل النصية: دعم / رابط تنزيل / رد افتراضي

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from bot.handlers.download import handle_link
from bot.handlers.support import handle_support_message
from bot.keyboards.main_menu import main_menu_keyboard
from bot.utils.validators import extract_url


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    text = (message.text or "").strip()
    if not text:
        return

    # 1) المستخدم يكتب رسالة دعم
    if context.user_data.get("awaiting_support"):
        await handle_support_message(update, context, text)
        return

    # 2) اختار منصة، او ارسل رابط مباشرة
    if context.user_data.get("platform") or extract_url(text):
        await handle_link(update, context, text)
        return

    # 3) اي شي ثاني
    await message.reply_text("👇 اختر من القائمة:", reply_markup=main_menu_keyboard())


def get_handlers() -> list:
    return [
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, text_router
        )
    ]