# bot/handlers/download.py
# قسم تنزيل المقطع: اختيار المنصة، التحقق من الرابط، التنزيل، الارسال، والتنظيف

import asyncio
import logging
import traceback

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.error import RetryAfter, TelegramError, TimedOut
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot.config import settings
from bot.database import crud
from bot.handlers.menu import ensure_user, safe_edit
from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.keyboards.platform_menu import cancel_keyboard, platform_menu_keyboard
from bot.services.downloader import DownloaderError, DownloadResult, cleanup, download_video
from bot.services.rate_limiter import active_downloads, download_limiter
from bot.utils.notify import notify_admins
from bot.utils.validators import PLATFORM_NAMES, format_duration, format_size, parse_link

logger = logging.getLogger(__name__)

EXAMPLES = {
    "tiktok": "https://www.tiktok.com/@username/video/1234567890",
    "twitter": "https://x.com/username/status/1234567890",
}


async def menu_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """زر 'تنزيل مقطع': عرض لوحة اختيار المنصة."""
    query = update.callback_query
    await query.answer()
    await ensure_user(update)
    context.user_data.pop("awaiting_support", None)
    await safe_edit(query, "🎬 اختر المنصة:", platform_menu_keyboard())


async def platform_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بعد اختيار المنصة: نطلب الرابط."""
    query = update.callback_query
    await query.answer()
    platform = query.data.split(":", 1)[1]
    if platform not in PLATFORM_NAMES:
        return
    context.user_data["platform"] = platform
    context.user_data.pop("awaiting_support", None)
    await safe_edit(
        query,
        f"📎 أرسل رابط فيديو {PLATFORM_NAMES[platform]}:\n\nمثال:\n{EXAMPLES[platform]}",
        cancel_keyboard(),
    )


async def _edit_status(status: Message | None, text: str) -> None:
    if status is None:
        return
    try:
        await status.edit_text(text, reply_markup=back_to_menu_keyboard())
    except TelegramError:
        pass


async def _delete_quietly(status: Message | None) -> None:
    if status is None:
        return
    try:
        await status.delete()
    except TelegramError:
        pass


async def _fail(
    status: Message | None, user_id: int, platform: str, url: str, mode: str, text: str
) -> None:
    """تسجيل تنزيل فاشل (بدون خصم رصيد) وابلاغ المستخدم."""
    await crud.record_download(user_id, platform, url, mode, status="failed")
    await _edit_status(status, text)


async def _send_video(message: Message, result: DownloadResult, caption: str) -> None:
    """ارسال الفيديو. اذا تيليجرام طلب انتظار (RetryAfter) ننتظر ونعيد مرة وحدة."""
    for attempt in range(2):
        try:
            await message.reply_video(
                video=result.path,
                caption=caption,
                duration=result.duration,
                width=result.width,
                height=result.height,
                supports_streaming=True,
                reply_markup=back_to_menu_keyboard(),
                read_timeout=180,
                write_timeout=180,
                connect_timeout=30,
                pool_timeout=30,
            )
            return
        except RetryAfter as exc:
            if attempt == 1:
                raise
            wait = exc.retry_after
            if hasattr(wait, "total_seconds"):
                wait = wait.total_seconds()
            await asyncio.sleep(float(wait) + 1)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """معالجة رابط ارسله المستخدم (يستدعيه الـ router)."""
    message = update.effective_message
    user = update.effective_user
    selected = context.user_data.get("platform")

    parsed = parse_link(text)
    if parsed is None:
        await message.reply_text(
            "❌ الرابط غير صالح أو المنصة غير مدعومة.\n"
            "أرسل رابط من تيك توك أو تويتر (X).",
            reply_markup=cancel_keyboard(),
        )
        return

    platform, url = parsed
    if selected and platform != selected:
        await message.reply_text(
            f"⚠️ انت اخترت {PLATFORM_NAMES[selected]} بس هذا رابط {PLATFORM_NAMES[platform]}.\n"
            "أرسل الرابط الصحيح أو ارجع للقائمة.",
            reply_markup=cancel_keyboard(),
        )
        return

    if not active_downloads.try_start(user.id):
        await message.reply_text("⏳ عندك تنزيل شغال حالياً، انتظر يخلص.")
        return

    status: Message | None = None
    result: DownloadResult | None = None
    try:
        wait = download_limiter.hit(user.id)
        if wait:
            await message.reply_text(f"🚦 تمهّل شوية! انتظر {wait} ثانية وحاول مرة ثانية.")
            return

        await ensure_user(update)
        mode = await crud.check_quota(user.id)
        if mode is None:
            await message.reply_text(
                f"⛔ خلصت تنزيلاتك المجانية اليوم ({settings.daily_free_downloads}).\n"
                "اشترك حتى تكمل التنزيل.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("⭐ الاشتراك", callback_data="menu:subscribe")],
                        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu:main")],
                    ]
                ),
            )
            return

        status = await message.reply_text("⏳ جاري التنزيل، انتظر شوية...")

        try:
            result = await download_video(url)
        except DownloaderError as err:
            await _fail(status, user.id, platform, url, mode, err.user_message)
            return
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error while downloading %s", url)
            await notify_admins(
                context.bot,
                f"⚠️ خطأ غير متوقع بالتنزيل\nUser: {user.id}\nURL: {url}\n\n"
                f"{traceback.format_exc()[-3000:]}",
            )
            await _fail(
                status, user.id, platform, url, mode,
                "❌ صار خطأ غير متوقع، حاول مرة ثانية بعد شوية.",
            )
            return

        caption = (
            f"🎬 {result.title}\n\n"
            f"⏱ المدة: {format_duration(result.duration)}\n"
            f"📦 الحجم: {format_size(result.size_bytes)}\n"
            f"🎞 الجودة: {result.quality or 'غير معروفة'}\n"
            f"📲 المنصة: {PLATFORM_NAMES[platform]}"
        )
        if context.bot.username:
            caption += f"\n\n🤖 @{context.bot.username}"

        try:
            await _send_video(message, result, caption[:1024])
        except TimedOut:
            logger.warning("Upload timed out for %s", url)
            await _fail(
                status, user.id, platform, url, mode,
                "⌛ انتهت مهلة رفع الفيديو، حاول مرة ثانية.",
            )
            return
        except RetryAfter:
            await _fail(
                status, user.id, platform, url, mode,
                "⚠️ تيليجرام مشغول حالياً، حاول بعد شوية.",
            )
            return
        except TelegramError as exc:
            logger.error("Telegram error while sending video: %s", exc)
            await notify_admins(
                context.bot, f"⚠️ فشل ارسال فيديو\nUser: {user.id}\nURL: {url}\nError: {exc}"
            )
            await _fail(
                status, user.id, platform, url, mode,
                "❌ ما گدرت أرسل الفيديو، حاول مرة ثانية.",
            )
            return

        await crud.record_download(
            user.id, platform, url, mode, "success", result.title, result.size_bytes
        )
        context.user_data.pop("platform", None)
        await _delete_quietly(status)
    finally:
        if result is not None:
            cleanup(result.workdir)
        active_downloads.finish(user.id)


def get_handlers() -> list:
    return [
        CallbackQueryHandler(menu_download_callback, pattern=r"^menu:download$"),
        CallbackQueryHandler(platform_callback, pattern=r"^platform:(tiktok|twitter)$"),
    ]