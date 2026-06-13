"""Simulated OBIE OAuth flow.

In production OBIE, the flow is:
  1. TPP redirects PSU to /authorize?openbanking_intent_id={ConsentId}&...
  2. PSU authenticates with ASPSP and chooses which accounts to authorise
  3. ASPSP returns an authorization code via redirect_uri
  4. TPP exchanges code at /token for an access token bound to the consent

We provide two simplified endpoints suitable for a portfolio demo:

  POST /open-banking/oauth/authorise-consent
       Used by a logged-in PSU (Bearer = user token) to grant a consent.
       Updates consent.status -> Authorised, binds psu_user_id, account_ids
       (AISP) or debtor_account_id (PISP).

  POST /open-banking/oauth/token
       Used by a TPP (HTTP Basic = client_id:client_secret) to exchange
       an authorised consent_id for an access token bound to that consent.

OBIE-GAP: no /authorize redirect endpoint, no PKCE, no PAR, no JAR/RAR,
no mTLS. The structure is faithful; the protocol details are not.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Form, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUserDep, PlainSessionDep, SessionDep
from app.models.orm import Account, Customer
from app.observability.audit import write_event
from app.openbanking.consent_service import _obie_error, load_tpp_or_403
from app.openbanking.orm import (
    AccountAccessConsent,
    DomesticPaymentConsent,
    ThirdPartyProvider,
)
from app.openbanking.tpp_auth import issue_tpp_token
from app.security.auth import verify_password

router = APIRouter(prefix="/open-banking/oauth", tags=["open-banking:oauth"])


class AuthoriseConsentBody(BaseModel):
    consent_id: str
    consent_type: Literal["aisp", "pisp"]
    # AISP: which of the PSU's accounts to expose
    account_ids: list[UUID] = []
    # PISP: which account to debit
    debtor_account_id: UUID | None = None


@router.post("/authorise-consent")
async def authorise_consent(
    body: AuthoriseConsentBody,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    """PSU authorises a previously-created consent.

    Caller is a logged-in customer (Bearer = the user's access token).
    """
    # Customer must own the accounts they're granting.
    cust = (
        await session.execute(select(Customer).where(Customer.user_id == UUID(user.user_id)))
    ).scalar_one_or_none()
    if cust is None:
        raise HTTPException(403, "only customers can authorise consents")

    owned_account_ids = {
        a_id for (a_id,) in (
            await session.execute(select(Account.id).where(Account.customer_id == cust.id))
        )
    }

    if body.consent_type == "aisp":
        consent = (
            await session.execute(
                select(AccountAccessConsent).where(AccountAccessConsent.id == body.consent_id)
            )
        ).scalar_one_or_none()
        if consent is None or consent.status != "AwaitingAuthorisation":
            raise HTTPException(404, "consent not awaiting authorisation")
        # Customer can only authorise accounts they own.
        not_owned = [aid for aid in body.account_ids if aid not in owned_account_ids]
        if not_owned:
            raise HTTPException(403, f"not owner of accounts: {not_owned}")
        consent.psu_user_id = UUID(user.user_id)
        consent.account_ids = [str(a) for a in body.account_ids]
        consent.status = "Authorised"
        consent.status_updated_at = datetime.now(UTC)
        await write_event(
            session,
            actor_user_id=user.user_id,
            actor_role=user.role.value,
            action="aisp.consent.authorise",
            resource=body.consent_id,
            outcome="success",
            nist_control="AC-3",
            detail={"account_ids": [str(a) for a in body.account_ids]},
            request_ip=user.request_ip,
        )
        return {"consent_id": body.consent_id, "status": "Authorised"}

    # PISP
    p_consent = (
        await session.execute(
            select(DomesticPaymentConsent).where(DomesticPaymentConsent.id == body.consent_id)
        )
    ).scalar_one_or_none()
    if p_consent is None or p_consent.status != "AwaitingAuthorisation":
        raise HTTPException(404, "consent not awaiting authorisation")
    if body.debtor_account_id is None or body.debtor_account_id not in owned_account_ids:
        raise HTTPException(403, "debtor account must be owned by the PSU")
    p_consent.psu_user_id = UUID(user.user_id)
    p_consent.debtor_account_id = body.debtor_account_id
    p_consent.status = "Authorised"
    p_consent.status_updated_at = datetime.now(UTC)
    await write_event(
        session,
        actor_user_id=user.user_id,
        actor_role=user.role.value,
        action="pisp.consent.authorise",
        resource=body.consent_id,
        outcome="success",
        nist_control="AC-3",
        detail={"debtor_account_id": str(body.debtor_account_id)},
        request_ip=user.request_ip,
    )
    return {"consent_id": body.consent_id, "status": "Authorised"}


# --- /token endpoint ----------------------------------------------------


def _decode_basic_auth(authorization: str | None) -> tuple[str, str]:
    """Decode HTTP Basic auth credentials. Returns (client_id, client_secret)."""
    if not authorization or not authorization.lower().startswith("basic "):
        raise _obie_error("UK.OBIE.Unauthorized", 401, "missing basic auth")
    import base64

    try:
        decoded = base64.b64decode(authorization.split(" ", 1)[1]).decode("utf-8")
        cid, secret = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError) as exc:
        raise _obie_error("UK.OBIE.Unauthorized", 401, "malformed basic auth") from exc
    return cid, secret


@router.post("/token")
async def token(
    session: PlainSessionDep,
    grant_type: Annotated[str, Form()],
    consent_id: Annotated[str | None, Form()] = None,
    scope: Annotated[str, Form()] = "",
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str | int]:
    """Token endpoint for TPPs.

    Supported grant types:
      - client_credentials  → unbound token (used to call /consents endpoints)
      - intent              → consent-bound token (after PSU authorisation)

    OBIE-GAP: real OBIE uses `authorization_code` after PSU redirect. Our
    `intent` grant skips the redirect and assumes the TPP knows the
    consent_id directly.
    """
    cid, secret = _decode_basic_auth(authorization)
    tpp = await load_tpp_or_403(session, client_id=cid)
    if not verify_password(secret, tpp.client_secret_hash):
        raise _obie_error("UK.OBIE.Unauthorized", 401, "invalid client credentials")

    if grant_type == "client_credentials":
        access, exp = issue_tpp_token(
            tpp_client_id=tpp.client_id,
            consent_id=None,
            scopes=scope.split(),
        )
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": int((exp - datetime.now(UTC)).total_seconds()),
            "scope": scope,
        }

    if grant_type == "intent":
        if not consent_id:
            raise HTTPException(400, "intent grant requires consent_id")
        # Verify the consent exists, belongs to this TPP, and is Authorised.
        aac = (
            await session.execute(
                select(AccountAccessConsent).where(AccountAccessConsent.id == consent_id)
            )
        ).scalar_one_or_none()
        dpc = None
        if aac is None:
            dpc = (
                await session.execute(
                    select(DomesticPaymentConsent).where(DomesticPaymentConsent.id == consent_id)
                )
            ).scalar_one_or_none()
        consent_obj: AccountAccessConsent | DomesticPaymentConsent | None = aac or dpc
        if consent_obj is None or consent_obj.tpp_id != tpp.id or consent_obj.status != "Authorised":
            raise _obie_error(
                "UK.OBIE.Resource.InvalidConsentStatus",
                403,
                "consent not authorised for this TPP",
            )
        access, exp = issue_tpp_token(
            tpp_client_id=tpp.client_id,
            consent_id=consent_id,
            scopes=scope.split(),
        )
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": int((exp - datetime.now(UTC)).total_seconds()),
            "scope": scope,
            "consent_id": consent_id,
        }

    raise HTTPException(400, f"unsupported grant_type: {grant_type}")
