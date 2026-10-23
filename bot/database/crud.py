# bot/database/crud.py
# عمليات قاعدة البيانات (انشاء/قراءة/تحديث) لكل الأقسام

from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from bot.config import settings
from bot.database.init_db import async_session
from bot.database.models import (
    Download,
    Payment,
    Subscription,
    SupportTicket,
    User,
    utcnow,
)


def _today_start() -> datetime:
    return datetime.combine(utcnow().date(), time.min)


# ---------------------------------------------------------------- المستخدمين
async def get_or_create_user(
    user_id: int, username: str | None, first_name: str | None
) -> User:
    """جلب المستخدم أو انشاؤه، وتحديث اسمه اذا تغيّر."""
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            user = User(id=user_id, username=username, first_name=first_name)
            session.add(user)
        else:
            user.username = username
            user.first_name = first_name
        await session.commit()
        return user


async def get_user(user_id: int) -> User | None:
    async with async_session() as session:
        return await session.get(User, user_id)


# ---------------------------------------------------------------- الحصة
def has_unlimited(user: User) -> bool:
    return user.sub_expires_at is not None and user.sub_expires_at > utcnow()


async def check_quota(user_id: int) -> str | None:
    """
    يرجع طريقة السماح بالتنزيل:
    unlimited (اشتراك فعال) / free (من المجاني اليومي) / credit (من الرصيد) / None (ممنوع)
    """
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            return None
        if has_unlimited(user):
            return "unlimited"

        used_today = await session.scalar(
            select(func.count(Download.id)).where(
                Download.user_id == user_id,
                Download.mode == "free",
                Download.status == "success",
                Download.created_at >= _today_start(),
            )
        )
        if (used_today or 0) < settings.daily_free_downloads:
            return "free"
        if user.balance > 0:
            return "credit"
        return None


async def record_download(
    user_id: int,
    platform: str,
    url: str,
    mode: str,
    status: str = "success",
    title: str | None = None,
    size_bytes: int | None = None,
) -> None:
    """تسجيل تنزيل، وخصم الرصيد اذا نجح وكان مدفوع."""
    async with async_session() as session:
        session.add(
            Download(
                user_id=user_id,
                platform=platform,
                url=url,
                title=(title or "")[:250] or None,
                size_bytes=size_bytes,
                mode=mode,
                status=status,
            )
        )
        if status == "success" and mode == "credit":
            user = await session.get(User, user_id)
            if user and user.balance > 0:
                user.balance -= 1
        await session.commit()


# ---------------------------------------------------------------- المدفوعات
async def payment_exists(charge_id: str) -> bool:
    async with async_session() as session:
        found = await session.scalar(
            select(Payment.id).where(Payment.charge_id == charge_id)
        )
        return found is not None


async def add_payment_and_grant(
    user_id: int,
    charge_id: str,
    plan_code: str,
    stars: int,
    credits: int,
    days: int,
) -> bool:
    """
    تسجيل الدفع ومنح الباقة. يرجع False اذا العملية مكررة (نفس charge_id).
    """
    async with async_session() as session:
        if await session.scalar(
            select(Payment.id).where(Payment.charge_id == charge_id)
        ):
            return False

        user = await session.get(User, user_id)
        if user is None:
            return False

        session.add(
            Payment(user_id=user_id, charge_id=charge_id, plan_code=plan_code, stars=stars)
        )
        session.add(
            Subscription(
                user_id=user_id,
                plan_code=plan_code,
                credits_added=credits,
                days_added=days,
            )
        )

        if credits:
            user.balance += credits
        if days:
            base = user.sub_expires_at if has_unlimited(user) else utcnow()
            user.sub_expires_at = base + timedelta(days=days)

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return False
        return True


# ---------------------------------------------------------------- الاحصائيات
async def get_user_stats(user_id: int) -> dict | None:
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            return None

        total = await session.scalar(
            select(func.count(Download.id)).where(
                Download.user_id == user_id, Download.status == "success"
            )
        )
        today = await session.scalar(
            select(func.count(Download.id)).where(
                Download.user_id == user_id,
                Download.status == "success",
                Download.created_at >= _today_start(),
            )
        )
        return {
            "total": total or 0,
            "today": today or 0,
            "balance": user.balance,
            "unlimited": has_unlimited(user),
            "expires_at": user.sub_expires_at,
            "joined_at": user.joined_at,
        }


async def get_global_stats() -> dict:
    async with async_session() as session:
        users = await session.scalar(select(func.count(User.id)))
        downloads = await session.scalar(
            select(func.count(Download.id)).where(Download.status == "success")
        )
        stars = await session.scalar(select(func.coalesce(func.sum(Payment.stars), 0)))
        rows = await session.execute(
            select(Download.platform, func.count(Download.id))
            .where(Download.status == "success")
            .group_by(Download.platform)
            .order_by(func.count(Download.id).desc())
        )
        return {
            "users": users or 0,
            "downloads": downloads or 0,
            "stars": stars or 0,
            "platforms": [(p, c) for p, c in rows.all()],
        }


# ---------------------------------------------------------------- الدعم
async def create_ticket(user_id: int, message: str) -> int:
    async with async_session() as session:
        ticket = SupportTicket(user_id=user_id, message=message)
        session.add(ticket)
        await session.commit()
        return ticket.id
    

# ---------------------------------------------------------------- الأدمن
_banned_ids: set[int] = set()  # نسخة بالذاكرة حتى ما نسأل القاعدة بكل رسالة


async def load_banned_ids() -> None:
    """تحميل المحظورين من القاعدة عند تشغيل البوت."""
    async with async_session() as session:
        rows = await session.scalars(select(User.id).where(User.banned.is_(True)))
        _banned_ids.clear()
        _banned_ids.update(rows.all())


def is_banned(user_id: int) -> bool:
    return user_id in _banned_ids


async def set_banned(user_id: int, banned: bool) -> bool:
    """حظر/فك حظر. يرجع False اذا المستخدم غير مسجّل بالبوت."""
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            return False
        user.banned = banned
        await session.commit()
    if banned:
        _banned_ids.add(user_id)
    else:
        _banned_ids.discard(user_id)
    return True


async def count_users() -> int:
    async with async_session() as session:
        return await session.scalar(select(func.count(User.id))) or 0


async def list_users(offset: int, limit: int) -> list[User]:
    async with async_session() as session:
        rows = await session.scalars(
            select(User).order_by(User.joined_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.all())


async def find_user(query: str) -> User | None:
    """بحث بالايدي (ارقام) او باليوزر (@name)."""
    query = query.strip()
    async with async_session() as session:
        if query.isdigit():
            return await session.get(User, int(query))
        name = query.lstrip("@").lower()
        return await session.scalar(
            select(User).where(func.lower(User.username) == name)
        )


async def get_user_payments(user_id: int, limit: int = 5) -> list[Payment]:
    async with async_session() as session:
        rows = await session.scalars(
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        return list(rows.all())


async def get_payment(charge_id: str) -> Payment | None:
    async with async_session() as session:
        return await session.scalar(
            select(Payment).where(Payment.charge_id == charge_id)
        )


async def mark_refunded(charge_id: str) -> None:
    async with async_session() as session:
        payment = await session.scalar(
            select(Payment).where(Payment.charge_id == charge_id)
        )
        if payment is not None:
            payment.refunded = True
            await session.commit()


async def revoke_grant(user_id: int, credits: int, days: int) -> None:
    """سحب ما انمنح بالباقة بعد الاسترجاع (رصيد التنزيلات / ايام الاشتراك)."""
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            return
        if credits:
            user.balance = max(user.balance - credits, 0)
        if days and user.sub_expires_at is not None:
            new_expiry = user.sub_expires_at - timedelta(days=days)
            user.sub_expires_at = new_expiry if new_expiry > utcnow() else None
        await session.commit()


async def get_broadcast_recipients() -> list[int]:
    async with async_session() as session:
        rows = await session.scalars(select(User.id).where(User.banned.is_(False)))
        return list(rows.all())