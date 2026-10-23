# bot/handlers/start.py
# امر /start و /menu: تسجيل المستخدم وعرض القائمة الرئيسية

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.handlers.menu import MAIN_MENU_TEXT, ensure_user
from bot.keyboards.main_menu import main_menu_keyboard


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ensure_user(update)
    context.user_data.clear()  # نبدأ من جديد
    await update.effective_message.reply_text(
        MAIN_MENU_TEXT, reply_markup=main_menu_keyboard()
    )


def get_handlers() -> list:
    return [
        CommandHandler("start", start_command),
        CommandHandler("menu", start_command),
    ]