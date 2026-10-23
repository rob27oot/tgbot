# bot/keyboards/subscription_menu.py
# كيبورد الباقات + كيبورد التبرع بالنجوم

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.payments import DONATE_AMOUNTS, PLANS


def subscription_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{plan.title} — {plan.stars} ⭐", callback_data=f"buy:{plan.code}")]
        for plan in PLANS.values()
    ]
    rows.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def donate_menu_keyboard() -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(f"{amount} ⭐", callback_data=f"donate_stars:{amount}")
        for amount in DONATE_AMOUNTS
    ]
    return InlineKeyboardMarkup(
        [row, [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu:main")]]
    )