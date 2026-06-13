"""AISP router — Account Information.

Implements the OBIE v4.0 read endpoints behind FAPI-shaped consent
enforcement. Internal account data is mapped to OBIE wire shapes at the
boundary; the underlying tables are unchanged.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.deps import PlainSessionDep, set_psu_rls_context
from app.models.orm import Account, Transaction
from app.observability.audit import write_event
from app.openbanking.consent_service import authorize_aisp_request
from app.openbanking.orm import AccountAccessConsent
from app.openbanking.schemas.obie import (
    OBAccount,
    OBAccountAccessConsentRequest,
    OBAccountAccessConsentResponseData,
    OBAccountIdentifier,
    OBAccountListData,
    OBAmount,
    OBBalance,
    OBBalanceListData,
    OBLinks,
    OBMeta,
    OBResponse,
    OBTransaction,
    OBTransactionListData,
)
from app.openbanking.tpp_auth import TPPCallerDep

router = APIRouter(prefix="/open-banking/v4.0/aisp", tags=["open-banking:aisp"])


def _consent_id() -> str:
    return f"aac-{uuid4()}"


# --- Consent lifecycle --------------------------------------------------


@router.post("/account-access-consents", status_code=201)
async def create_account_access_consent(
    body: OBAccountAccessConsentRequest,
    tpp: TPPCallerDep,
    session: PlainSessionDep,
    request: Request,
) -> OBResponse[OBAccountAccessConsentResponseData]:
    """Step 1: TPP creates a consent. PSU has not yet authorised.

    OBIE-GAP: in production the TPP token here would be a client-credentials
    token (no consent_id yet), and step 2 would be the PSU authorisation
    via the OAuth `/authorize` endpoint with `openbanking_intent_id={ConsentId}`.
    Our /open-banking/oauth/token endpoint simulates the post-authorisation
    token issuance.
    """
    if "AISP" not in (tpp.tpp.roles or []):
        raise HTTPException(403, "TPP does not have AISP role")

    cid = _consent_id()
    now = datetime.now(UTC)
    consent = AccountAccessConsent(
        id=cid,
        tpp_id=tpp.tpp.id,
        psu_user_id=None,
        status="AwaitingAuthorisation",
        permissions=list(body.Data.Permissions),
        account_ids=[],
        expiration_at=body.Data.ExpirationDateTime,
        transaction_from=body.Data.TransactionFromDateTime,
        transaction_to=body.Data.TransactionToDateTime,
        created_at=now,
        status_updated_at=now,
        raw_request=body.model_dump(mode="json"),
    )
    session.add(consent)
    await session.flush()

    await write_event(
        session,
        actor_user_id=None,
        actor_role="tpp",
        action="aisp.consent.create",
        resource=cid,
        outcome="success",
        nist_control="AC-2",
        detail={"tpp": tpp.tpp.client_id, "permissions": list(body.Data.Permissions)},
        request_ip=tpp.request_ip,
    )

    data = OBAccountAccessConsentResponseData(
        ConsentId=cid,
        CreationDateTime=now,
        Status="AwaitingAuthorisation",
        StatusUpdateDateTime=now,
        Permissions=body.Data.Permissions,
        ExpirationDateTime=body.Data.ExpirationDateTime,
        TransactionFromDateTime=body.Data.TransactionFromDateTime,
        TransactionToDateTime=body.Data.TransactionToDateTime,
    )
    return OBResponse(
        Data=data,
        Links=OBLinks(Self=f"{request.base_url}open-banking/v4.0/aisp/account-access-consents/{cid}"),
        Meta=OBMeta(),
    )


@router.get("/account-access-consents/{consent_id}")
async def get_account_access_consent(
    consent_id: str,
    tpp: TPPCallerDep,
    session: PlainSessionDep,
    request: Request,
) -> OBResponse[OBAccountAccessConsentResponseData]:
    consent = (
        await session.execute(
            select(AccountAccessConsent).where(AccountAccessConsent.id == consent_id)
        )
    ).scalar_one_or_none()
    if consent is None or consent.tpp_id != tpp.tpp.id:
        raise HTTPException(404, "consent not found")
    data = OBAccountAccessConsentResponseData(
        ConsentId=consent.id,
        CreationDateTime=consent.created_at,
        Status=consent.status,  # type: ignore[arg-type]
        StatusUpdateDateTime=consent.status_updated_at,
        Permissions=consent.permissions,  # type: ignore[arg-type]
        ExpirationDateTime=consent.expiration_at,
        TransactionFromDateTime=consent.transaction_from,
        TransactionToDateTime=consent.transaction_to,
    )
    return OBResponse(
        Data=data,
        Links=OBLinks(Self=str(request.url)),
        Meta=OBMeta(),
    )


@router.delete("/account-access-consents/{consent_id}", status_code=204)
async def revoke_consent(
    consent_id: str,
    tpp: TPPCallerDep,
    session: PlainSessionDep,
) -> None:
    consent = (
        await session.execute(
            select(AccountAccessConsent).where(AccountAccessConsent.id == consent_id)
        )
    ).scalar_one_or_none()
    if consent is None or consent.tpp_id != tpp.tpp.id:
        raise HTTPException(404, "consent not found")
    consent.status = "Revoked"
    consent.status_updated_at = datetime.now(UTC)
    await write_event(
        session,
        actor_user_id=None,
        actor_role="tpp",
        action="aisp.consent.revoke",
        resource=consent_id,
        outcome="success",
        nist_control="AC-3",
        detail={"tpp": tpp.tpp.client_id},
        request_ip=tpp.request_ip,
    )


# --- Resource endpoints -------------------------------------------------


def _account_to_obie(acc: Account) -> OBAccount:
    return OBAccount(
        AccountId=str(acc.id),
        Status="Enabled" if not acc.is_frozen else "Disabled",
        StatusUpdateDateTime=acc.created_at,
        Currency="USD",  # demo data is USD; real ASPSPs vary
        AccountSubType=(
            "CurrentAccount" if acc.account_type == "checking"
            else "Savings" if acc.account_type == "savings"
            else "Loan"
        ),
        Account=[
            OBAccountIdentifier(
                # We don't have UK sort codes; use a custom namespaced scheme.
                SchemeName="UK.AGENTIC.AccountUUID",
                Identification=str(acc.id),
                Name=acc.account_number,
            )
        ],
    )


@router.get("/accounts")
async def list_accounts(
    tpp: TPPCallerDep,
    session: PlainSessionDep,
    request: Request,
) -> OBResponse[OBAccountListData]:
    if not tpp.consent_id:
        raise HTTPException(401, "token has no consent binding")
    consent = await authorize_aisp_request(
        session,
        consent_id=tpp.consent_id,
        tpp=tpp.tpp,
        required_permission="ReadAccountsBasic",
    )
    await set_psu_rls_context(session, consent.psu_user_id)
    rows = (
        await session.execute(
            select(Account).where(Account.id.in_([UUID(a) for a in consent.account_ids]))
        )
    ).scalars().all()
    return OBResponse(
        Data=OBAccountListData(Account=[_account_to_obie(a) for a in rows]),
        Links=OBLinks(Self=str(request.url)),
        Meta=OBMeta(),
    )


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: UUID,
    tpp: TPPCallerDep,
    session: PlainSessionDep,
    request: Request,
) -> OBResponse[OBAccountListData]:
    if not tpp.consent_id:
        raise HTTPException(401, "token has no consent binding")
    consent = await authorize_aisp_request(
        session,
        consent_id=tpp.consent_id,
        tpp=tpp.tpp,
        required_permission="ReadAccountsBasic",
        account_id=str(account_id),
    )
    await set_psu_rls_context(session, consent.psu_user_id)
    acc = (await session.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if acc is None:
        raise HTTPException(404, "account not found")
    return OBResponse(
        Data=OBAccountListData(Account=[_account_to_obie(acc)]),
        Links=OBLinks(Self=str(request.url)),
        Meta=OBMeta(),
    )


@router.get("/accounts/{account_id}/balances")
async def get_balances(
    account_id: UUID,
    tpp: TPPCallerDep,
    session: PlainSessionDep,
    request: Request,
) -> OBResponse[OBBalanceListData]:
    if not tpp.consent_id:
        raise HTTPException(401, "token has no consent binding")
    consent = await authorize_aisp_request(
        session,
        consent_id=tpp.consent_id,
        tpp=tpp.tpp,
        required_permission="ReadBalances",
        account_id=str(account_id),
    )
    await set_psu_rls_context(session, consent.psu_user_id)
    acc = (await session.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if acc is None:
        raise HTTPException(404, "account not found")
    bal = OBBalance(
        AccountId=str(acc.id),
        Amount=OBAmount(Amount=acc.balance, Currency="USD"),
        CreditDebitIndicator="Credit" if acc.balance >= 0 else "Debit",
        Type="InterimBooked",
        DateTime=datetime.now(UTC),
    )
    return OBResponse(
        Data=OBBalanceListData(Balance=[bal]),
        Links=OBLinks(Self=str(request.url)),
        Meta=OBMeta(),
    )


@router.get("/accounts/{account_id}/transactions")
async def get_transactions(
    account_id: UUID,
    tpp: TPPCallerDep,
    session: PlainSessionDep,
    request: Request,
) -> OBResponse[OBTransactionListData]:
    if not tpp.consent_id:
        raise HTTPException(401, "token has no consent binding")
    consent = await authorize_aisp_request(
        session,
        consent_id=tpp.consent_id,
        tpp=tpp.tpp,
        required_permission="ReadTransactionsDetail",
        account_id=str(account_id),
    )
    await set_psu_rls_context(session, consent.psu_user_id)
    q = select(Transaction).where(
        (Transaction.from_account_id == account_id) | (Transaction.to_account_id == account_id)
    )
    if consent.transaction_from:
        q = q.where(Transaction.created_at >= consent.transaction_from)
    if consent.transaction_to:
        q = q.where(Transaction.created_at <= consent.transaction_to)
    rows = (await session.execute(q.order_by(Transaction.created_at.desc()))).scalars().all()

    obs = []
    for tx in rows:
        # Credit if money came IN to this account, Debit if went OUT.
        is_credit = tx.to_account_id == account_id
        obs.append(
            OBTransaction(
                AccountId=str(account_id),
                TransactionId=str(tx.id),
                Status="Booked" if tx.state == "settled" else "Pending",
                BookingDateTime=tx.settled_at or tx.created_at,
                ValueDateTime=tx.settled_at,
                TransactionInformation=tx.memo or None,
                Amount=OBAmount(Amount=tx.amount.quantize(Decimal("0.01")), Currency="USD"),
                CreditDebitIndicator="Credit" if is_credit else "Debit",
            )
        )

    return OBResponse(
        Data=OBTransactionListData(Transaction=obs),
        Links=OBLinks(Self=str(request.url)),
        Meta=OBMeta(),
    )
