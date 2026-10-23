# bot/handlers/menu.py
# القائمة الرئيسية + دوال مساعدة مشتركة بين كل الهاندلرز

import logging

from telegram import CallbackQuery, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot.database import crud
from bot.keyboards.main_menu import main_menu_keyboard

logger = logging.getLogger(__name__)

MAIN_MENU_TEXT = (
    "👋 أهلاً بك في بوت تنزيل الفيديوهات!\n\n"
    "🎬 نزّل فيديوهات تيك توك وتويتر (X) بأعلى جودة.\n\n"
    "اختر من القائمة:"
)


async def ensure_user(update: Update):
    """تسجيل المستخدم بقاعدة البيانات (او تحديث بياناته)."""
    user = update.effective_user
    if user is None:
        return None
    return await crud.get_or_create_user(user.id, user.username, user.first_name)


async def safe_edit(
    query: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs,
) -> None:
    """
    تعديل رسالة الكيبورد بأمان:
    - اذا النص نفسه، نتجاهل الخطأ.
    - اذا الرسالة ما تنعدل (مثلاً فيديو)، نرسل رسالة جديدة.
    """
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, **kwargs)
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        logger.info("edit failed, sending new message: %s", exc)
        if query.message:
            await query.message.reply_text(text, reply_markup=reply_markup, **kwargs)


async def menu_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الرجوع للقائمة الرئيسية، وإلغاء اي حالة انتظار."""
    query = update.callback_query
    await query.answer()
    await ensure_user(update)

    # الغاء حالات الانتظار (رابط / رسالة دعم)
    context.user_data.pop("platform", None)
    context.user_data.pop("awaiting_support", None)

    await safe_edit(query, MAIN_MENU_TEXT, main_menu_keyboard())


def get_handlers() -> list:
    return [CallbackQueryHandler(menu_main_callback, pattern=r"^menu:main$")]