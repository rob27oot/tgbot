# bot/database/models.py
# تعريف جداول قاعدة البيانات: users, downloads, subscriptions, payments, support_tickets

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """الوقت الحالي UTC بدون tzinfo (حتى يشتغل مع SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    """جدول المستخدمين. الـ id هو ايدي تيليجرام نفسه."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)  # رصيد التنزيلات المدفوعة
    sub_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # نهاية الاشتراك غير المحدود
    banned: Mapped[bool] = mapped_column(Boolean, default=False)  # محظور من استخدام البوت
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Download(Base):
    """سجل التنزيلات."""

    __tablename__ = "downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(16))  # tiktok / twitter
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="free")  # free / credit / unlimited
    status: Mapped[str] = mapped_column(String(16), default="success")  # success / failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Subscription(Base):
    """سجل الاشتراكات التي اشتراها المستخدم."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    plan_code: Mapped[str] = mapped_column(String(32))
    credits_added: Mapped[int] = mapped_column(Integer, default=0)
    days_added: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Payment(Base):
    """سجل المدفوعات بنجوم تيليجرام. charge_id فريد لمنع التكرار."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    charge_id: Mapped[str] = mapped_column(String(256), unique=True)
    plan_code: Mapped[str] = mapped_column(String(32))
    stars: Mapped[int] = mapped_column(Integer)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False)  # تم استرجاعها
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SupportTicket(Base):
    """رسائل الدعم."""

    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)