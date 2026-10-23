# bot/services/payments.py
# باقات الاشتراك + ارسال فواتير نجوم تيليجرام (XTR) + معالجة الدفع بدون تكرار

import logging
from dataclasses import dataclass

from telegram import LabeledPrice
from telegram.ext import ContextTypes

from bot.database import crud

logger = logging.getLogger(__name__)

CURRENCY = "XTR"  # عملة نجوم تيليجرام، ما تحتاج provider_token


@dataclass(frozen=True)
class Plan:
    code: str
    title: str
    description: str
    stars: int
    credits: int  # عدد التنزيلات المضافة للرصيد
    days: int  # عدد ايام الاشتراك غير المحدود


PLANS: dict[str, Plan] = {
    "p100": Plan("p100", "باقة 50 تنزيل", "50 تنزيل اضافي بدون مدة انتهاء", 100, 50, 0),
    "p250": Plan("p250", "باقة 150 تنزيل", "150 تنزيل اضافي بدون مدة انتهاء", 250, 150, 0),
    "p500": Plan("p500", "اشتراك غير محدود", "تنزيلات غير محدودة لمدة 30 يوم", 500, 0, 30),
}

DONATE_AMOUNTS = (10, 50, 100)


async def send_plan_invoice(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, plan_code: str
) -> bool:
    """ارسال فاتورة باقة. يرجع False اذا الباقة غير موجودة."""
    plan = PLANS.get(plan_code)
    if plan is None:
        return False
    await context.bot.send_invoice(
        chat_id=chat_id,
        title=plan.title,
        description=plan.description,
        payload=f"plan:{plan.code}",
        provider_token="",
        currency=CURRENCY,
        prices=[LabeledPrice(plan.title, plan.stars)],
    )
    return True


async def send_donation_invoice(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, stars: int
) -> bool:
    """ارسال فاتورة تبرع بمبلغ مخصص."""
    if stars not in DONATE_AMOUNTS:
        return False
    await context.bot.send_invoice(
        chat_id=chat_id,
        title="تبرع للبوت",
        description=f"شكراً لدعمك! تبرع بـ {stars} نجمة",
        payload=f"donate:{stars}",
        provider_token="",
        currency=CURRENCY,
        prices=[LabeledPrice("تبرع", stars)],
    )
    return True


def validate_precheckout(payload: str, total_amount: int, currency: str) -> bool:
    """التحقق من الفاتورة قبل ما يدفع المستخدم (PreCheckoutQuery)."""
    if currency != CURRENCY:
        return False
    kind, _, value = (payload or "").partition(":")
    if kind == "plan":
        plan = PLANS.get(value)
        return plan is not None and plan.stars == total_amount
    if kind == "donate":
        return value.isdigit() and int(value) in DONATE_AMOUNTS and int(value) == total_amount
    return False


async def apply_successful_payment(user_id: int, payment) -> tuple[str, Plan | None]:
    """
    معالجة دفعة ناجحة (SuccessfulPayment).
    يرجع (الحالة, الباقة):
      ok        = تم المنح
      donation  = تبرع تم تسجيله
      duplicate = العملية مكررة (نفس charge_id) ولا نمنح مرة ثانية
      invalid   = فاتورة غير معروفة (لازم المشرف يراجعها)
    """
    charge_id = payment.telegram_payment_charge_id
    kind, _, value = (payment.invoice_payload or "").partition(":")

    # نتأكد المستخدم موجود بالقاعدة حتى ما تفشل العملية
    if await crud.get_user(user_id) is None:
        await crud.get_or_create_user(user_id, None, None)

    if kind == "plan":
        plan = PLANS.get(value)
        if plan is None or plan.stars != payment.total_amount:
            logger.error("Invalid plan payment: charge=%s payload=%s", charge_id, payment.invoice_payload)
            return "invalid", None
        granted = await crud.add_payment_and_grant(
            user_id, charge_id, plan.code, plan.stars, plan.credits, plan.days
        )
        return ("ok" if granted else "duplicate"), plan

    if kind == "donate":
        granted = await crud.add_payment_and_grant(
            user_id, charge_id, "donate", payment.total_amount, 0, 0
        )
        return ("donation" if granted else "duplicate"), None

    logger.error("Unknown payment payload: charge=%s payload=%s", charge_id, payment.invoice_payload)
    return "invalid", None