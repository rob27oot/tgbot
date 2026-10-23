# bot/keyboards/platform_menu.py
# لوحة اختيار المنصة (تيك توك / تويتر)

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def platform_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎵 تيك توك", callback_data="platform:tiktok"),
                InlineKeyboardButton("🐦 تويتر (X)", callback_data="platform:twitter"),
            ],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu:main")],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    """زر الغاء اثناء انتظار الرابط."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ إلغاء", callback_data="menu:main")]]
    )