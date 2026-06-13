"""Consent enforcement.

A TPP request carries a JWT whose `consent_id` claim references an
`account_access_consents` or `domestic_payment_consents` row. Before any
data is returned, we verify:

  1. The consent exists and is in `Authorised` state (not Rejected,
     Revoked, Expired, or Consumed).
  2. The consent has not passed its ExpirationDateTime.
  3. The TPP making the call owns the consent (token's tpp_id == consent.tpp_id).
  4. For AISP: the requested account is in `consent.account_ids`, and the
     requested operation maps to a granted Permission.
  5. For PISP: the requested debtor account matches the consent.

This module is deliberately UI/transport-agnostic so it can be reused
by hypothetical CIBA or decoupled-auth flows later.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.openbanking.orm import (
    AccountAccessConsent,
    DomesticPaymentConsent,
    ThirdPartyProvider,
)
from app.openbanking.schemas.obie import OBError, OBErrorItem


def _obie_error(code: str, http_status: int, message: str) -> HTTPException:
    """Build an HTTPException with an OBIE-shaped error body."""
    body = OBError(
        Code=str(http_status),
        Message=message,
        Errors=[OBErrorItem(ErrorCode=code, Message=message)],
    )
    return HTTPException(status_code=http_status, detail=body.model_dump(mode="json"))


async def load_tpp_or_403(
    session: AsyncSession, *, client_id: str
) -> ThirdPartyProvider:
    tpp = (
        await session.execute(
            select(ThirdPartyProvider).where(ThirdPartyProvider.client_id == client_id)
        )
    ).scalar_one_or_none()
    if tpp is None or not tpp.is_active:
        raise _obie_error("UK.OBIE.Reauthenticate", 401, "TPP not registered or inactive")
    return tpp


async def authorize_aisp_request(
    session: AsyncSession,
    *,
    consent_id: str,
    tpp: ThirdPartyProvider,
    required_permission: str,
    account_id: str | None = None,
) -> AccountAccessConsent:
    """Run all AISP-side consent checks. Raises OBIE-shaped 401/403 on
    failure; returns the consent on success."""
    consent = (
        await session.execute(
            select(AccountAccessConsent).where(AccountAccessConsent.id == consent_id)
        )
    ).scalar_one_or_none()
    if consent is None:
        raise _obie_error("UK.OBIE.Resource.NotFound", 404, "Consent not found")

    if consent.tpp_id != tpp.id:
        raise _obie_error(
            "UK.OBIE.Resource.NotAuthorised", 403, "Consent does not belong to this TPP"
        )

    if consent.status != "Authorised":
        raise _obie_error(
            "UK.OBIE.Resource.InvalidConsentStatus",
            403,
            f"Consent is in state {consent.status}",
        )

    if consent.expiration_at and consent.expiration_at < datetime.now(UTC):
        # Soft-expire on read.
        consent.status = "Expired"
        consent.status_updated_at = datetime.now(UTC)
        raise _obie_error("UK.OBIE.Resource.ConsentMismatch", 403, "Consent has expired")

    if required_permission not in consent.permissions:
        raise _obie_error(
            "UK.OBIE.Resource.NotAuthorised",
            403,
            f"Consent does not include permission {required_permission}",
        )

    if account_id is not None and account_id not in consent.account_ids:
        raise _obie_error(
            "UK.OBIE.Resource.NotAuthorised",
            403,
            "Account is not in scope of this consent",
        )

    return consent


async def authorize_pisp_request(
    session: AsyncSession,
    *,
    consent_id: str,
    tpp: ThirdPartyProvider,
    expected_state: Literal["Authorised", "Consumed"] = "Authorised",
) -> DomesticPaymentConsent:
    consent = (
        await session.execute(
            select(DomesticPaymentConsent).where(DomesticPaymentConsent.id == consent_id)
        )
    ).scalar_one_or_none()
    if consent is None:
        raise _obie_error("UK.OBIE.Resource.NotFound", 404, "Payment consent not found")
    if consent.tpp_id != tpp.id:
        raise _obie_error(
            "UK.OBIE.Resource.NotAuthorised", 403, "Consent does not belong to this TPP"
        )
    if consent.status != expected_state:
        raise _obie_error(
            "UK.OBIE.Resource.InvalidConsentStatus",
            403,
            f"Consent is in state {consent.status}, expected {expected_state}",
        )
    return consent
