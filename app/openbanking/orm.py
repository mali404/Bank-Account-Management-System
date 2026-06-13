"""ORM models for Open Banking consents and TPP registration.

Lives in its own module to keep the OBIE surface optional / separable.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.orm import Base


class ThirdPartyProvider(Base):
    """A registered TPP. In production this would be sourced from the OBIE
    Directory; we admin-register for the demo. OBIE-GAP."""

    __tablename__ = "third_party_providers"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    client_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client_secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    organisation_name: Mapped[str] = mapped_column(String(200), nullable=False)
    software_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(8)), nullable=False, default=list
    )  # e.g. {"AISP", "PISP", "CBPII"}
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(
        ARRAY(String(512)), nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "roles <@ ARRAY['AISP','PISP','CBPII']::varchar[]",
            name="tpp_roles_valid",
        ),
    )


class AccountAccessConsent(Base):
    """AISP consent (OBIE Account Information)."""

    __tablename__ = "account_access_consents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # ConsentId
    tpp_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("third_party_providers.id"), nullable=False
    )
    psu_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="AwaitingAuthorisation")
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    account_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    expiration_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_request: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('AwaitingAuthorisation','Authorised','Rejected','Revoked','Expired')",
            name="aac_status_valid",
        ),
    )


class DomesticPaymentConsent(Base):
    """PISP consent for a single domestic payment."""

    __tablename__ = "domestic_payment_consents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # ConsentId
    tpp_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("third_party_providers.id"), nullable=False
    )
    psu_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="AwaitingAuthorisation")
    instructed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    debtor_account_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True
    )
    creditor_scheme: Mapped[str] = mapped_column(String(64), nullable=False)
    creditor_identification: Mapped[str] = mapped_column(String(256), nullable=False)
    creditor_name: Mapped[str | None] = mapped_column(String(140), nullable=True)
    end_to_end_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instruction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    consumed_payment_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('AwaitingAuthorisation','Authorised','Consumed','Rejected','Expired')",
            name="dpc_status_valid",
        ),
        CheckConstraint("instructed_amount > 0", name="dpc_amount_positive"),
    )


__all__ = [
    "ThirdPartyProvider",
    "AccountAccessConsent",
    "DomesticPaymentConsent",
]
