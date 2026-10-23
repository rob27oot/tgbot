# bot/handlers/stats.py
# قسم الاحصائيات: للمستخدم العادي + احصائيات البوت الكلية للمشرفين

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from bot.config import settings
from bot.database import crud
from bot.database.models import utcnow
from bot.handlers.menu import ensure_user, safe_edit
from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.utils.validators import PLATFORM_NAMES


def _fmt_date(dt) -> str:
    return dt.strftime("%Y-%m-%d") if dt else "—"


async def build_stats_text(user_id: int) -> str:
    """بناء نص الاحصائيات. المشرفون يشوفون قسم اضافي للبوت كله."""
    stats = await crud.get_user_stats(user_id)
    if stats is None:
        return "ما لگيت بياناتك، ارسل /start وحاول مرة ثانية."

    if stats["unlimited"]:
        days_left = max((stats["expires_at"] - utcnow()).days, 0)
        sub_line = (
            f"✅ اشتراك غير محدود\n"
            f"   ينتهي بتاريخ: {_fmt_date(stats['expires_at'])} (باقي {days_left} يوم)"
        )
    else:
        sub_line = "🆓 حساب مجاني"

    lines = [
        "📊 إحصائياتك",
        "",
        f"📥 إجمالي تنزيلاتك: {stats['total']}",
        f"📅 تنزيلات اليوم: {stats['today']}",
        f"🎁 التنزيلات المجانية يومياً: {settings.daily_free_downloads}",
        f"💎 رصيدك المتبقي: {stats['balance']} تنزيل",
        f"⭐ حالة الاشتراك: {sub_line}",
        f"🗓 تاريخ الانضمام: {_fmt_date(stats['joined_at'])}",
    ]

    if user_id in settings.admin_ids:
        g = await crud.get_global_stats()
        platforms = (
            "\n".join(
                f"   • {PLATFORM_NAMES.get(name, name)}: {count}"
                for name, count in g["platforms"]
            )
            or "   —"
        )
        lines += [
            "",
            "━━━━━━━━━━━━━━",
            "👑 إحصائيات البوت (للمشرفين)",
            "",
            f"👥 عدد المستخدمين: {g['users']}",
            f"📥 إجمالي التنزيلات: {g['downloads']}",
            f"⭐ إجمالي النجوم المستلمة: {g['stars']}",
            "🏆 المنصات الأكثر استخداماً:",
            platforms,
        ]

    return "\n".join(lines)


async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await ensure_user(update)
    text = await build_stats_text(update.effective_user.id)
    await safe_edit(query, text, back_to_menu_keyboard())


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ensure_user(update)
    text = await build_stats_text(update.effective_user.id)
    await update.effective_message.reply_text(text, reply_markup=back_to_menu_keyboard())


def get_handlers() -> list:
    return [
        CallbackQueryHandler(stats_callback, pattern=r"^menu:stats$"),
        CommandHandler("stats", stats_command),
    ]