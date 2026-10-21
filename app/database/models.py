from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram ID
    language: Mapped[str | None] = mapped_column(String(2))
    currency: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    available_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=0, server_default="0")
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=0, server_default="0")
    earned_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=0, server_default="0")
    withdrawn_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=0, server_default="0")
    accepted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_submission_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("available_usd >= 0 AND reserved_usd >= 0", name="nonnegative_funds"),
        CheckConstraint("language IS NULL OR language IN ('ru','en')", name="valid_language"),
        CheckConstraint("currency IS NULL OR currency IN ('USD','RUB')", name="valid_currency"),
    )


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(120))
    name_en: Mapped[str] = mapped_column(String(120))
    description_ru: Mapped[str] = mapped_column(Text, default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    conditions_ru: Mapped[str] = mapped_column(Text, default="")
    conditions_en: Mapped[str] = mapped_column(Text, default="")
    rate: Mapped[Decimal] = mapped_column(Numeric(16, 8))
    image: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (CheckConstraint("rate > 0", name="positive_rate"),)


class AcceptedKey(Base):
    __tablename__ = "accepted_keys"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    balance_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    purchase_rate: Mapped[Decimal] = mapped_column(Numeric(16, 8))
    discount: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    csv_region_restricted: Mapped[bool] = mapped_column(Boolean)
    test_region_restricted: Mapped[bool] = mapped_column(Boolean)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    rate_source: Mapped[str] = mapped_column(Text)
    rate_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payment_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    credited_amount: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), default="credited")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CryptoOption(Base):
    __tablename__ = "crypto_options"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16))
    network: Mapped[str] = mapped_column(String(32))
    address_kind: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_token: Mapped[str] = mapped_column(String(36), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    currency: Mapped[str] = mapped_column(String(3))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    rate_source: Mapped[str] = mapped_column(Text)
    rate_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    method: Mapped[str] = mapped_column(String(16))
    destination_label: Mapped[str] = mapped_column(String(80))
    encrypted_details: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    admin_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("amount > 0 AND amount_usd > 0", name="positive_withdrawal"),
        CheckConstraint(
            "status IN ('pending','processing','paid','rejected','cancelled')",
            name="withdrawal_status",
        ),
    )


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16))
    accepted_key_id: Mapped[int | None] = mapped_column(ForeignKey("accepted_keys.id"), unique=True)
    withdrawal_id: Mapped[int | None] = mapped_column(ForeignKey("withdrawals.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("withdrawal_event_once", "withdrawal_id", "kind", unique=True),)


class Administrator(Base):
    __tablename__ = "administrators"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(16), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Configuration(Base):
    __tablename__ = "configuration"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int] = mapped_column(BigInteger)
    event: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VerificationAttempt(Base):
    __tablename__ = "verification_attempts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[str] = mapped_column(String(48))
    outcome: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PendingAcceptance(Base):
    __tablename__ = "pending_acceptances"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    balance_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    purchase_rate: Mapped[Decimal] = mapped_column(Numeric(16, 8))
    csv_region_restricted: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
