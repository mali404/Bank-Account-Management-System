"""ORM models. PII columns are stored encrypted via pgcrypto;
the ORM exposes them through hybrid properties that decrypt on read."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('customer','teller','loan_officer','compliance_officer','admin')",
            name="users_role_valid",
        ),
    )


class Customer(Base):
    """Customer profile. PII columns are bytea (pgcrypto)."""

    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    # Stored as bytea in DDL; access via SQL with pgp_sym_decrypt(...).
    full_name_encrypted: Mapped[bytes] = mapped_column("full_name", nullable=False)
    gov_id_encrypted: Mapped[bytes] = mapped_column("gov_id", nullable=False)
    dob_encrypted: Mapped[bytes] = mapped_column("dob", nullable=False)
    kyc_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    account_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    account_type: Mapped[str] = mapped_column(String(16), nullable=False)
    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("balance >= 0", name="accounts_balance_nonnegative"),
        CheckConstraint(
            "account_type IN ('checking','savings','loan')",
            name="accounts_type_valid",
        ),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    from_account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True
    )
    to_account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    memo: Mapped[str] = mapped_column(Text, default="", nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    originator_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    approver_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="transactions_amount_positive"),
        CheckConstraint(
            "state IN ('pending_approval','approved','settled','rejected','cancelled')",
            name="transactions_state_valid",
        ),
        # Separation of duties — originator cannot approve own.
        CheckConstraint(
            "approver_user_id IS NULL OR approver_user_id <> originator_user_id",
            name="transactions_separation_of_duties",
        ),
        Index("ix_transactions_from", "from_account_id"),
        Index("ix_transactions_to", "to_account_id"),
        Index("ix_transactions_state", "state"),
    )


class AuditEvent(Base):
    """Append-only. INSERT only at the runtime DB user. See migration 001."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actor_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    nist_control: Mapped[str | None] = mapped_column(String(16), nullable=True)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    request_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    prev_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    hmac: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_canonical: Mapped[str] = mapped_column(Text, nullable=False)


# Avoid unused-import warnings — referenced by Alembic migration env.
__all__ = ["Base", "User", "Customer", "Account", "Transaction", "AuditEvent"]
_ = relationship  # silence ruff
