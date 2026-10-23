# bot/handlers/subscription.py
# قسم الاشتراك: عرض الباقات، ارسال الفاتورة، PreCheckout، والدفع الناجح (Stars)

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from bot.database import crud
from bot.database.models import utcnow
from bot.handlers.menu import ensure_user, safe_edit
from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.keyboards.subscription_menu import subscription_menu_keyboard
from bot.services.payments import (
    PLANS,
    apply_successful_payment,
    send_plan_invoice,
    validate_precheckout,
)
from bot.utils.notify import notify_admins

logger = logging.getLogger(__name__)


async def subscribe_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض حالة الاشتراك + الباقات."""
    query = update.callback_query
    await query.answer()
    await ensure_user(update)
    stats = await crud.get_user_stats(update.effective_user.id)

    if stats and stats["unlimited"]:
        days_left = max((stats["expires_at"] - utcnow()).days, 0)
        status = (
            f"✅ اشتراك غير محدود\n"
            f"📅 ينتهي بتاريخ: {stats['expires_at']:%Y-%m-%d} (باقي {days_left} يوم)"
        )
    else:
        status = "🆓 حساب مجاني"

    balance = stats["balance"] if stats else 0
    plans = "\n".join(
        f"• {p.title}: {p.stars} ⭐ — {p.description}" for p in PLANS.values()
    )
    text = (
        "⭐ الاشتراك\n\n"
        f"حالتك: {status}\n"
        f"💎 رصيدك المتبقي: {balance} تنزيل\n\n"
        f"الباقات المتوفرة:\n{plans}\n\n"
        "اختر الباقة، وراح توصلك فاتورة الدفع بنجوم تيليجرام:"
    )
    await safe_edit(query, text, subscription_menu_keyboard())


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ارسال فاتورة الباقة المختارة."""
    query = update.callback_query
    code = query.data.split(":", 1)[1]
    try:
        ok = await send_plan_invoice(context, query.message.chat_id, code)
    except TelegramError as exc:
        logger.error("send_invoice failed: %s", exc)
        await query.answer("⚠️ ما گدرت أرسل الفاتورة، حاول مرة ثانية.", show_alert=True)
        return
    if ok:
        await query.answer()
    else:
        await query.answer("❌ الباقة غير موجودة.", show_alert=True)


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """لازم نرد خلال 10 ثواني: نوافق على الفاتورة الصحيحة فقط."""
    query = update.pre_checkout_query
    if validate_precheckout(query.invoice_payload, query.total_amount, query.currency):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="الفاتورة غير صالحة، حاول مرة ثانية.")


async def successful_payment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """بعد نجاح الدفع: نمنح الباقة (مرة وحدة فقط لكل charge_id)."""
    message = update.effective_message
    payment = message.successful_payment
    user = update.effective_user
    await ensure_user(update)

    status, plan = await apply_successful_payment(user.id, payment)

    if status == "ok" and plan is not None:
        if plan.credits:
            gift = f"🎁 تمت إضافة {plan.credits} تنزيل لرصيدك."
        else:
            gift = f"🎁 تم تفعيل الاشتراك غير المحدود لمدة {plan.days} يوم."
        text = f"✅ تم الدفع بنجاح!\n\n{gift}\n\nشكراً لدعمك 💙"
    elif status == "donation":
        text = "💖 شكراً جزيلاً على تبرعك! دعمك يساعدنا نكمل."
    elif status == "duplicate":
        text = "ℹ️ هذه العملية تمت معالجتها سابقاً."
    else:
        text = (
            "⚠️ صار خطأ بمعالجة الدفع.\n"
            "تواصل مع الدعم وراح نحلها لك (احتفظ بهذه الرسالة)."
        )
        await notify_admins(
            context.bot,
            f"🚨 دفعة بحاجة مراجعة\nUser: {user.id}\n"
            f"Charge: {payment.telegram_payment_charge_id}\n"
            f"Payload: {payment.invoice_payload}\nStars: {payment.total_amount}",
        )

    await message.reply_text(text, reply_markup=back_to_menu_keyboard())


def get_handlers() -> list:
    return [
        CallbackQueryHandler(subscribe_menu_callback, pattern=r"^menu:subscribe$"),
        CallbackQueryHandler(buy_callback, pattern=r"^buy:\w+$"),
        PreCheckoutQueryHandler(precheckout_callback),
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback),
    ]