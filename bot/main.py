import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keep_alive import keep_alive

# bot/main.py
# نقطة الدخول: اعداد اللوگ، تسجيل الهاندلرز، معالجة الأخطاء، وتشغيل البوت
# التشغيل: python -m bot.main

import logging
import traceback
from logging.handlers import RotatingFileHandler

from telegram import BotCommand, BotCommandScopeChat, Update
from telegram.error import Conflict, NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import Application, ContextTypes, TypeHandler

from bot.config import BASE_DIR, settings
from bot.database import crud
from bot.database.init_db import init_db
from bot.handlers import (
    admin,
    donate,
    download,
    menu,
    router,
    start,
    stats,
    subscription,
    support,
)
from bot.utils.notify import notify_admins

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """اللوگ بالشاشة وبملف bot.log (يدور تلقائياً)."""
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    file_handler = RotatingFileHandler(
        BASE_DIR / "bot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    logging.basicConfig(level=logging.INFO, handlers=[console, file_handler])

    # httpx يطبع روابط فيها توكن البوت بمستوى INFO، فنسكته
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def post_init(application: Application) -> None:
    """يشتغل مرة وحدة قبل بدء البوت: القاعدة + المحظورين + اوامر البوت."""
    await init_db()
    await crud.load_banned_ids()

    public_commands = [
        BotCommand("start", "القائمة الرئيسية"),
        BotCommand("menu", "القائمة الرئيسية"),
        BotCommand("stats", "إحصائياتي"),
    ]
    await application.bot.set_my_commands(public_commands)

    # اوامر الأدمن تظهر لك انت بس
    admin_commands = public_commands + [
        BotCommand("admin", "أوامر الأدمن"),
        BotCommand("users", "قائمة المستخدمين"),
        BotCommand("user", "معلومات مستخدم"),
        BotCommand("ban", "حظر مستخدم"),
        BotCommand("unban", "فك حظر"),
        BotCommand("broadcast", "إعلان للجميع"),
        BotCommand("refund", "استرجاع نجوم"),
    ]
    for admin_id in settings.admin_ids:
        try:
            await application.bot.set_my_commands(
                admin_commands, scope=BotCommandScopeChat(admin_id)
            )
        except TelegramError as exc:
            logger.warning("Could not set admin commands for %s: %s", admin_id, exc)

    me = await application.bot.get_me()
    logger.info("Bot started as @%s (id=%s)", me.username, me.id)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج الأخطاء العام: التفاصيل للوگ وللمشرفين فقط، المستخدم يشوف رسالة عامة."""
    err = context.error

    if isinstance(err, (TimedOut, NetworkError)):
        logger.warning("Network problem: %s", err)
        return
    if isinstance(err, RetryAfter):
        logger.warning("Flood control, retry after %s", err.retry_after)
        return
    if isinstance(err, Conflict):
        logger.error("Conflict: في نسخة ثانية من البوت شغالة بنفس التوكن!")
        return

    logger.error("Unhandled exception", exc_info=err)

    tb = "".join(traceback.format_exception(None, err, err.__traceback__))
    user_id = update.effective_user.id if isinstance(update, Update) and update.effective_user else "?"
    await notify_admins(context.bot, f"🚨 خطأ بالبوت\nUser: {user_id}\n\n{tb[-3500:]}")

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ صار خطأ غير متوقع، حاول مرة ثانية بعد شوية."
            )
        except Exception:  # noqa: BLE001
            pass


def build_application() -> Application:
    app = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(post_init)
        .concurrent_updates(True)  # حتى تنزيل مستخدم ما يوقف باقي المستخدمين
        .build()
    )

    # بوابة الحظر: تشتغل أول شي (group -1) قبل كل الهاندلرز
    app.add_handler(TypeHandler(Update, admin.ban_gate), group=-1)

    # الترتيب مهم: الـ router (الرسائل النصية) لازم يكون آخر واحد
    for module in (start, menu, download, subscription, donate, support, stats, admin, router):
        app.add_handlers(module.get_handlers())

    app.add_error_handler(error_handler)
    return app


def main() -> None:
    setup_logging()
    logger.info("Starting bot...")
    keep_alive()   # ⬅️ السطر الجديد الوحيد
    build_application().run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()