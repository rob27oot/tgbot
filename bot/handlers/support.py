# bot/handlers/support.py
# قسم الدعم: رابط حساب الدعم + ارسال رسالة للمشرفين (تنحفظ بجدول support_tickets)

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot.config import settings
from bot.database import crud
from bot.handlers.menu import ensure_user, safe_edit
from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.keyboards.platform_menu import cancel_keyboard
from bot.services.rate_limiter import RateLimiter
from bot.utils.notify import notify_admins

logger = logging.getLogger(__name__)

MAX_TICKET_LENGTH = 1500
support_limiter = RateLimiter(max_calls=3, period=300)  # 3 رسائل كل 5 دقايق


async def support_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await ensure_user(update)
    context.user_data.pop("platform", None)
    context.user_data.pop("awaiting_support", None)

    rows = []
    text = "🆘 الدعم\n\n"
    if settings.support_username:
        link = f"https://t.me/{settings.support_username}"
        text += f"تگدر تتواصل مباشرة مع الدعم:\n{link}\n\n"
        rows.append([InlineKeyboardButton("💬 تواصل مع الدعم", url=link)])
    text += "أو ارسل رسالتك من هنا وراح توصل للمشرف."
    rows.append([InlineKeyboardButton("✉️ إرسال رسالة للمشرف", callback_data="support:write")])
    rows.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu:main")])

    await safe_edit(query, text, InlineKeyboardMarkup(rows))


async def support_write_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("platform", None)
    context.user_data["awaiting_support"] = True
    await safe_edit(query, "✍️ اكتب رسالتك وارسلها هسه:", cancel_keyboard())


async def handle_support_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    """يستدعيه الـ router لما المستخدم يكون بحالة 'ينتظر رسالة دعم'."""
    message = update.effective_message
    user = update.effective_user

    if len(text) > MAX_TICKET_LENGTH:
        await message.reply_text(
            f"⚠️ رسالتك طويلة، اختصرها لأقل من {MAX_TICKET_LENGTH} حرف.",
            reply_markup=cancel_keyboard(),
        )
        return

    wait = support_limiter.hit(user.id)
    if wait:
        await message.reply_text(f"🚦 ارسلت رسائل كثيرة، انتظر {wait} ثانية.")
        return

    await ensure_user(update)
    ticket_id = await crud.create_ticket(user.id, text)
    context.user_data.pop("awaiting_support", None)

    username = f"@{user.username}" if user.username else "بدون يوزر"
    await notify_admins(
        context.bot,
        f"🆘 رسالة دعم جديدة #{ticket_id}\n"
        f"👤 {user.first_name or ''} ({username})\n"
        f"🆔 {user.id}\n\n{text}",
    )
    await message.reply_text(
        f"✅ وصلت رسالتك (رقم #{ticket_id})، راح نرد عليك بأقرب وقت.",
        reply_markup=back_to_menu_keyboard(),
    )


def get_handlers() -> list:
    return [
        CallbackQueryHandler(support_menu_callback, pattern=r"^menu:support$"),
        CallbackQueryHandler(support_write_callback, pattern=r"^support:write$"),
    ]