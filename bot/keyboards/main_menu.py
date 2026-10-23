# bot/keyboards/main_menu.py
# القائمة الرئيسية للبوت (Inline Keyboard)

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎬 تنزيل مقطع", callback_data="menu:download")],
            [
                InlineKeyboardButton("⭐ الاشتراك", callback_data="menu:subscribe"),
                InlineKeyboardButton("📊 إحصائياتي", callback_data="menu:stats"),
            ],
            [
                InlineKeyboardButton("💰 التبرع", callback_data="menu:donate"),
                InlineKeyboardButton("🆘 الدعم", callback_data="menu:support"),
            ],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """زر رجوع للقائمة الرئيسية."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu:main")]]
    )