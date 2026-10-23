# bot/handlers/admin.py
# أوامر الأدمن: حظر، إعلان جماعي، استرجاع نجوم، قائمة المستخدمين والبحث
# + بوابة الحظر (ban_gate) اللي تمنع المحظورين من استخدام البوت

import asyncio
import html
import logging
import uuid
from functools import wraps

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from bot.config import settings
from bot.database import crud
from bot.handlers.menu import safe_edit
from bot.services.payments import PLANS

logger = logging.getLogger(__name__)

PAGE_SIZE = 10
MAX_BROADCAST_LENGTH = 3500

HELP_TEXT = (
    "👑 أوامر الأدمن\n\n"
    "/users [رقم الصفحة] — قائمة المستخدمين\n"
    "/user ايدي أو @يوزر — معلومات مستخدم\n"
    "/ban ايدي — حظر مستخدم\n"
    "/unban ايدي — فك الحظر\n"
    "/broadcast النص — إعلان لكل المستخدمين\n"
    "/refund رقم_العملية — استرجاع نجوم دفعة\n\n"
    "رقم العملية تلگاه بـ /user تحت آخر الدفعات."
)


def _fmt_date(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"


def admin_only(func):
    """يتجاهل اي شخص مو أدمن (بدون ما يرد عليه)."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or user.id not in settings.admin_ids:
            return
        await func(update, context)

    return wrapper


# ---------------------------------------------------------------- بوابة الحظر
async def ban_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تشتغل قبل كل الهاندلرز (group=-1): المحظور ما يوصل لأي شي."""
    user = update.effective_user
    if user is None or user.id in settings.admin_ids:
        return
    if not crud.is_banned(user.id):
        return
    # الدفعات الجارية ما نوقفها حتى ما تضيع فلوس مستخدم
    if update.pre_checkout_query or (update.message and update.message.successful_payment):
        return

    try:
        if update.callback_query:
            await update.callback_query.answer("⛔ تم حظرك من استخدام البوت.", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text("⛔ تم حظرك من استخدام البوت.")
    except TelegramError:
        pass
    raise ApplicationHandlerStop


# ---------------------------------------------------------------- الأوامر
@admin_only
async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT)


@admin_only
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    page = 1
    if context.args and context.args[0].isdigit():
        page = max(int(context.args[0]), 1)

    total = await crud.count_users()
    rows = await crud.list_users((page - 1) * PAGE_SIZE, PAGE_SIZE)
    if not rows:
        await update.effective_message.reply_text("ما أكو مستخدمين بهالصفحة.")
        return

    pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    lines = [f"👥 المستخدمين ({total}) — صفحة {page}/{pages}", ""]
    for u in rows:
        name = html.escape(u.first_name or "-")
        uname = f"@{html.escape(u.username)}" if u.username else "بدون يوزر"
        flag = " 🚫" if u.banned else ""
        lines.append(f"• <code>{u.id}</code> {name} ({uname}){flag}")
    lines += ["", "للتفاصيل: /user ايدي"]
    if page < pages:
        lines.append(f"الصفحة الجاية: /users {page + 1}")

    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@admin_only
async def user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("الاستخدام: /user ايدي  أو  /user @يوزر")
        return

    user = await crud.find_user(context.args[0])
    if user is None:
        await update.effective_message.reply_text("❌ ما لگيت هذا المستخدم.")
        return

    stats = await crud.get_user_stats(user.id)
    payments = await crud.get_user_payments(user.id, 5)

    name = html.escape(user.first_name or "-")
    uname = f"@{html.escape(user.username)}" if user.username else "بدون يوزر"
    if stats and stats["unlimited"]:
        sub = f"✅ غير محدود حتى {_fmt_date(stats['expires_at'])}"
    else:
        sub = "🆓 مجاني"

    lines = [
        f"👤 <b>{name}</b> ({uname})",
        f"🆔 <code>{user.id}</code>",
        f"🗓 انضم: {_fmt_date(user.joined_at)}",
        f"🚫 محظور: {'نعم' if user.banned else 'لا'}",
        "",
        f"📥 التنزيلات: {stats['total'] if stats else 0} (اليوم: {stats['today'] if stats else 0})",
        f"💎 الرصيد: {user.balance}",
        f"⭐ الاشتراك: {sub}",
    ]
    if payments:
        lines += ["", "💳 آخر الدفعات:"]
        for p in payments:
            note = " (مسترجعة)" if p.refunded else ""
            lines.append(
                f"• {p.stars}⭐ {html.escape(p.plan_code)}{note}\n"
                f"  <code>{html.escape(p.charge_id)}</code>"
            )

    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


def _parse_user_id(args: list[str]) -> int | None:
    return int(args[0]) if args and args[0].isdigit() else None


@admin_only
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = _parse_user_id(context.args)
    if uid is None:
        await update.effective_message.reply_text("الاستخدام: /ban 123456789")
        return
    if uid in settings.admin_ids:
        await update.effective_message.reply_text("⚠️ ما تگدر تحظر أدمن.")
        return
    if await crud.set_banned(uid, True):
        await update.effective_message.reply_text(f"🚫 تم حظر المستخدم {uid}.")
    else:
        await update.effective_message.reply_text("❌ هذا المستخدم غير مسجّل بالبوت.")


@admin_only
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = _parse_user_id(context.args)
    if uid is None:
        await update.effective_message.reply_text("الاستخدام: /unban 123456789")
        return
    if await crud.set_banned(uid, False):
        await update.effective_message.reply_text(f"✅ تم فك الحظر عن {uid}.")
    else:
        await update.effective_message.reply_text("❌ هذا المستخدم غير مسجّل بالبوت.")


# ---------------------------------------------------------------- الاعلان
@admin_only
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parts = (update.effective_message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await update.effective_message.reply_text("الاستخدام: /broadcast نص الاعلان")
        return
    text = parts[1].strip()
    if len(text) > MAX_BROADCAST_LENGTH:
        await update.effective_message.reply_text(
            f"⚠️ النص طويل، اختصره لأقل من {MAX_BROADCAST_LENGTH} حرف."
        )
        return
    if context.bot_data.get("broadcast_running"):
        await update.effective_message.reply_text("⏳ في إعلان شغال حالياً، انتظر ينتهي.")
        return

    nonce = uuid.uuid4().hex[:8]
    context.bot_data["pending_broadcast"] = {"nonce": nonce, "text": text}
    recipients = len(await crud.get_broadcast_recipients())

    await update.effective_message.reply_text(
        f"📢 معاينة الإعلان:\n\n{text}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"راح يوصل لـ {recipients} مستخدم. تأكيد الإرسال؟",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ إرسال", callback_data=f"admin:bc_ok:{nonce}"),
                    InlineKeyboardButton("❌ إلغاء", callback_data=f"admin:bc_cancel:{nonce}"),
                ]
            ]
        ),
    )


async def _run_broadcast(bot, admin_chat_id: int, text: str, bot_data: dict) -> None:
    sent = failed = 0
    try:
        for uid in await crud.get_broadcast_recipients():
            try:
                await bot.send_message(chat_id=uid, text=text)
                sent += 1
            except RetryAfter as exc:
                wait = exc.retry_after
                if hasattr(wait, "total_seconds"):
                    wait = wait.total_seconds()
                await asyncio.sleep(float(wait) + 1)
                try:
                    await bot.send_message(chat_id=uid, text=text)
                    sent += 1
                except TelegramError:
                    failed += 1
            except TelegramError:
                failed += 1  # غالباً المستخدم حاظر البوت
            await asyncio.sleep(0.05)  # ~20 رسالة بالثانية، تحت حد تيليجرام
        await bot.send_message(
            chat_id=admin_chat_id,
            text=f"✅ انتهى الإعلان\n📨 وصل: {sent}\n❌ فشل: {failed} (غالباً حاظرين البوت)",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Broadcast crashed")
    finally:
        bot_data["broadcast_running"] = False


async def broadcast_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    if user is None or user.id not in settings.admin_ids:
        return

    _, action, nonce = query.data.split(":")
    pending = context.bot_data.get("pending_broadcast")

    if not pending or pending["nonce"] != nonce:
        await safe_edit(query, "⚠️ هذا الإعلان قديم أو انلغى. ارسل /broadcast من جديد.")
        return
    if action == "bc_cancel":
        context.bot_data.pop("pending_broadcast", None)
        await safe_edit(query, "❌ تم إلغاء الإعلان.")
        return
    if context.bot_data.get("broadcast_running"):
        await safe_edit(query, "⏳ في إعلان شغال حالياً، انتظر ينتهي.")
        return

    text = pending["text"]
    context.bot_data.pop("pending_broadcast", None)
    context.bot_data["broadcast_running"] = True
    await safe_edit(query, "🚀 بدأ الإرسال، راح توصلك رسالة لما ينتهي.")
    context.application.create_task(
        _run_broadcast(context.bot, query.message.chat_id, text, context.bot_data)
    )


# ---------------------------------------------------------------- الاسترجاع
@admin_only
async def refund_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not context.args:
        await message.reply_text("الاستخدام: /refund رقم_العملية\n(تلگاه بـ /user ايدي)")
        return

    payment = await crud.get_payment(context.args[0])
    if payment is None:
        await message.reply_text("❌ ما لگيت عملية بهذا الرقم.")
        return
    if payment.refunded:
        await message.reply_text("ℹ️ هذي العملية انسترجعت قبل.")
        return

    try:
        await context.bot.refund_star_payment(
            user_id=payment.user_id,
            telegram_payment_charge_id=payment.charge_id,
        )
    except TelegramError as exc:
        logger.error("Refund failed for %s: %s", payment.charge_id, exc)
        await message.reply_text(f"❌ تيليجرام رفض الاسترجاع:\n{exc}")
        return

    await crud.mark_refunded(payment.charge_id)

    revoked = ""
    plan = PLANS.get(payment.plan_code)
    if plan:
        await crud.revoke_grant(payment.user_id, plan.credits, plan.days)
        revoked = "\n↩️ انسحبت الباقة من حسابه."

    await message.reply_text(
        f"✅ تم استرجاع {payment.stars}⭐ للمستخدم {payment.user_id}.{revoked}"
    )
    try:
        await context.bot.send_message(
            chat_id=payment.user_id,
            text=f"💫 تم استرجاع {payment.stars} نجمة لحسابك.",
        )
    except TelegramError:
        pass


def get_handlers() -> list:
    return [
        CommandHandler("admin", admin_help),
        CommandHandler("users", users_command),
        CommandHandler("user", user_command),
        CommandHandler("ban", ban_command),
        CommandHandler("unban", unban_command),
        CommandHandler("broadcast", broadcast_command),
        CommandHandler("refund", refund_command),
        CallbackQueryHandler(
            broadcast_confirm_callback, pattern=r"^admin:bc_(ok|cancel):\w+$"
        ),
    ]