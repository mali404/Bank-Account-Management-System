"""PISP router — Payment Initiation.

A PISP payment runs through the same internal Transaction machinery as a
customer-initiated transfer. That keeps policy enforcement (high-value
threshold, separation of duties, audit chain) in one place. The OBIE
layer is just a protocol adapter.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.deps import PlainSessionDep, set_system_rls_context
from app.core.settings import get_settings
from app.models.orm import Account, Transaction
from app.observability.audit import write_event, write_event_standalone
from app.openbanking.consent_service import authorize_pisp_request
from app.openbanking.orm import DomesticPaymentConsent
from app.openbanking.schemas.obie import (
    OBAmount,
    OBDomesticPaymentConsentRequest,
    OBDomesticPaymentConsentResponseData,
    OBDomesticPaymentRequest,
    OBDomesticPaymentResponseData,
    OBInitiation,
    OBLinks,
    OBMeta,
    OBResponse,
    OBAccountIdentifier,
)
from app.openbanking.tpp_auth import TPPCallerDep

router = APIRouter(prefix="/open-banking/v4.0/pisp", tags=["open-banking:pisp"])


def _consent_id() -> str:
    return f"dpc-{uuid4()}"


def _payment_id() -> str:
    return f"pay-{uuid4()}"


# --- Consent lifecycle --------------------------------------------------


@router.post("/domestic-payment-consents", status_code=201)
async def create_payment_consent(
    body: OBDomesticPaymentConsentRequest,
    tpp: TPPCallerDep,
    session: PlainSessionDep,
    request: Request,
) -> OBResponse[OBDomesticPaymentConsentResponseData]:
    if "PISP" not in (tpp.tpp.roles or []):
        raise HTTPException(403, "TPP does not have PISP role")

    cid = _consent_id()
    now = datetime.now(UTC)
    init = body.Data.Initiation

    consent = DomesticPaymentConsent(
        id=cid,
        tpp_id=tpp.tpp.id,
        psu_user_id=None,  # set on PSU authorisation
        status="AwaitingAuthorisation",
        instructed_amount=init.InstructedAmount.Amount,
        currency=init.InstructedAmount.Currency,
        debtor_account_id=None,  # bound on PSU auth, since debtor is optional
        creditor_scheme=init.CreditorAccount.SchemeName,
        creditor_identification=init.CreditorAccount.Identification,
        creditor_name=init.CreditorAccount.Name,
        end_to_end_id=init.EndToEndIdentification,
        instruction_id=init.InstructionIdentification,
        risk=body.Risk.model_dump(mode="json"),
        created_at=now,
        status_updated_at=now,
    )
    session.add(consent)
    await session.flush()

    await write_event(
        session,
        actor_user_id=None,
        actor_role="tpp",
        action="pisp.consent.create",
        resource=cid,
        outcome="success",
        nist_control="AC-2",
        detail={
            "tpp": tpp.tpp.client_id,
            "amount": str(init.InstructedAmount.Amount),
            "currency": init.InstructedAmount.Currency,
        },
        request_ip=tpp.request_ip,
    )

    data = OBDomesticPaymentConsentResponseData(
        ConsentId=cid,
        CreationDateTime=now,
        Status="AwaitingAuthorisation",
        StatusUpdateDateTime=now,
        Initiation=init,
    )
    return OBResponse(
        Data=data,
        Links=OBLinks(Self=f"{request.base_url}open-banking/v4.0/pisp/domestic-payment-consents/{cid}"),
        Meta=OBMeta(),
    )


@router.get("/domestic-payment-consents/{consent_id}")
async def get_payment_consent(
    consent_id: str,
    tpp: TPPCallerDep,
    session: PlainSessionDep,
    request: Request,
) -> OBResponse[OBDomesticPaymentConsentResponseData]:
    c = (
        await session.execute(
            select(DomesticPaymentConsent).where(DomesticPaymentConsent.id == consent_id)
        )
    ).scalar_one_or_none()
    if c is None or c.tpp_id != tpp.tpp.id:
        raise HTTPException(404, "consent not found")
    data = OBDomesticPaymentConsentResponseData(
        ConsentId=c.id,
        CreationDateTime=c.created_at,
        Status=c.status,  # type: ignore[arg-type]
        StatusUpdateDateTime=c.status_updated_at,
        Initiation=OBInitiation(
            InstructionIdentification=c.instruction_id or str(uuid4()),
            EndToEndIdentification=c.end_to_end_id or str(uuid4()),
            InstructedAmount=OBAmount(Amount=c.instructed_amount, Currency=c.currency),
            CreditorAccount=OBAccountIdentifier(
                SchemeName=c.creditor_scheme,
                Identification=c.creditor_identification,
                Name=c.creditor_name,
            ),
        ),
    )
    return OBResponse(Data=data, Links=OBLinks(Self=str(request.url)), Meta=OBMeta())


# --- Payment execution --------------------------------------------------


@router.post("/domestic-payments", status_code=201)
async def submit_payment(
    body: OBDomesticPaymentRequest,
    tpp: TPPCallerDep,
    session: PlainSessionDep,
    request: Request,
) -> OBResponse[OBDomesticPaymentResponseData]:
    """Execute a domestic payment under an Authorised consent.

    The consent must be in Authorised state and the request must match
    the consent's initiation (amount, currency, creditor). After successful
    submission the consent transitions to Consumed and a Transaction row
    is created.

    The same high-value threshold and separation-of-duties rules apply.
    """
    settings = get_settings()
    if "PISP" not in (tpp.tpp.roles or []):
        raise HTTPException(403, "TPP does not have PISP role")
    if not tpp.consent_id or tpp.consent_id != body.Data.ConsentId:
        raise HTTPException(401, "token consent_id does not match request ConsentId")

    consent = await authorize_pisp_request(
        session, consent_id=body.Data.ConsentId, tpp=tpp.tpp, expected_state="Authorised"
    )

    # Cross-check the request payload matches the consent.
    init = body.Data.Initiation
    if (
        init.InstructedAmount.Amount.quantize(Decimal("0.01")) != consent.instructed_amount.quantize(Decimal("0.01"))
        or init.InstructedAmount.Currency != consent.currency
        or init.CreditorAccount.Identification != consent.creditor_identification
        or init.CreditorAccount.SchemeName != consent.creditor_scheme
    ):
        await write_event_standalone(
            actor_user_id=None,
            actor_role="tpp",
            action="pisp.payment.submit",
            resource=body.Data.ConsentId,
            outcome="denied",
            nist_control="AC-3",
            detail={"reason": "consent_initiation_mismatch"},
            request_ip=tpp.request_ip,
        )
        raise HTTPException(400, "request does not match consent initiation")

    if consent.debtor_account_id is None:
        raise HTTPException(409, "consent has no debtor account bound; PSU must authorise first")

    # Settlement context: the debtor's ownership was verified at consent
    # authorisation (the PSU could only bind accounts they own), and the
    # creditor's row is legitimately invisible to the PSU. The credit leg
    # therefore runs under the internal system context — same pattern as
    # the internal /transfers endpoint.
    await set_system_rls_context(session)

    # Use the existing internal money-movement primitives.
    src = (
        await session.execute(
            select(Account).where(Account.id == consent.debtor_account_id).with_for_update()
        )
    ).scalar_one_or_none()
    if src is None:
        raise HTTPException(404, "debtor account not found")
    if src.is_frozen:
        raise HTTPException(409, "debtor account frozen")
    if src.balance < consent.instructed_amount:
        raise HTTPException(409, "insufficient funds")

    # PISP payments to external creditors are out-of-scope for this demo;
    # we resolve the creditor by matching an internal account number where
    # possible (e.g. when creditor identification == an account UUID), else
    # the payment is rejected. A real ASPSP would route via Faster Payments.
    dst = None
    if consent.creditor_scheme == "UK.AGENTIC.AccountUUID":
        try:
            dst = (
                await session.execute(
                    select(Account).where(Account.id == UUID(consent.creditor_identification)).with_for_update()
                )
            ).scalar_one_or_none()
        except (ValueError, AttributeError):
            dst = None
    if dst is None:
        await write_event_standalone(
            actor_user_id=None,
            actor_role="tpp",
            action="pisp.payment.submit",
            resource=body.Data.ConsentId,
            outcome="denied",
            nist_control="AC-3",
            detail={"reason": "external_creditors_not_implemented"},
            request_ip=tpp.request_ip,
        )
        # OBIE-GAP: payments to external (faster-payments) destinations.
        raise HTTPException(501, "external creditor settlement not implemented in demo")

    # High-value path: queue pending approval; OBIE status maps accordingly.
    high_value = consent.instructed_amount > settings.high_value_threshold
    payment_id = uuid4()
    now = datetime.now(UTC)

    if high_value:
        tx = Transaction(
            id=payment_id,
            from_account_id=src.id,
            to_account_id=dst.id,
            amount=consent.instructed_amount,
            memo=f"PISP:{tpp.tpp.client_id}:{consent.id}",
            state="pending_approval",
            originator_user_id=consent.psu_user_id,  # the PSU is the originator
        )
        session.add(tx)
        await session.flush()
        obie_status = "Pending"
    else:
        src.balance = (src.balance - consent.instructed_amount).quantize(Decimal("0.01"))
        dst.balance = (dst.balance + consent.instructed_amount).quantize(Decimal("0.01"))
        tx = Transaction(
            id=payment_id,
            from_account_id=src.id,
            to_account_id=dst.id,
            amount=consent.instructed_amount,
            memo=f"PISP:{tpp.tpp.client_id}:{consent.id}",
            state="settled",
            originator_user_id=consent.psu_user_id,
            settled_at=now,
        )
        session.add(tx)
        await session.flush()
        obie_status = "AcceptedSettlementCompleted"

    # Consent transitions to Consumed regardless of pending/settled.
    consent.status = "Consumed"
    consent.status_updated_at = now
    consent.consumed_payment_id = payment_id

    await write_event(
        session,
        actor_user_id=str(consent.psu_user_id) if consent.psu_user_id else None,
        actor_role="tpp",
        action="pisp.payment.submit",
        resource=str(payment_id),
        outcome="success",
        nist_control="AC-3",
        detail={
            "tpp": tpp.tpp.client_id,
            "consent_id": consent.id,
            "amount": str(consent.instructed_amount),
            "high_value": high_value,
        },
        request_ip=tpp.request_ip,
    )

    data = OBDomesticPaymentResponseData(
        DomesticPaymentId=str(payment_id),
        ConsentId=consent.id,
        CreationDateTime=now,
        Status=obie_status,  # type: ignore[arg-type]
        StatusUpdateDateTime=now,
        Initiation=init,
    )
    return OBResponse(
        Data=data,
        Links=OBLinks(Self=f"{request.base_url}open-banking/v4.0/pisp/domestic-payments/{payment_id}"),
        Meta=OBMeta(),
        Risk=body.Risk.model_dump(mode="json"),
    )


@router.get("/domestic-payments/{payment_id}")
async def get_payment(
    payment_id: UUID,
    tpp: TPPCallerDep,
    session: PlainSessionDep,
    request: Request,
) -> OBResponse[OBDomesticPaymentResponseData]:
    tx = (
        await session.execute(select(Transaction).where(Transaction.id == payment_id))
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(404, "payment not found")

    consent = (
        await session.execute(
            select(DomesticPaymentConsent).where(DomesticPaymentConsent.consumed_payment_id == payment_id)
        )
    ).scalar_one_or_none()
    if consent is None or consent.tpp_id != tpp.tpp.id:
        raise HTTPException(403, "payment is not visible to this TPP")

    status_map = {
        "settled": "AcceptedSettlementCompleted",
        "pending_approval": "Pending",
        "approved": "AcceptedSettlementInProcess",
        "rejected": "Rejected",
        "cancelled": "Rejected",
    }
    obie_status = status_map.get(tx.state, "Pending")

    init = OBInitiation(
        InstructionIdentification=consent.instruction_id or str(uuid4()),
        EndToEndIdentification=consent.end_to_end_id or str(uuid4()),
        InstructedAmount=OBAmount(Amount=consent.instructed_amount, Currency=consent.currency),
        CreditorAccount=OBAccountIdentifier(
            SchemeName=consent.creditor_scheme,
            Identification=consent.creditor_identification,
            Name=consent.creditor_name,
        ),
    )

    data = OBDomesticPaymentResponseData(
        DomesticPaymentId=str(payment_id),
        ConsentId=consent.id,
        CreationDateTime=tx.created_at,
        Status=obie_status,  # type: ignore[arg-type]
        StatusUpdateDateTime=tx.settled_at or tx.created_at,
        Initiation=init,
    )
    return OBResponse(Data=data, Links=OBLinks(Self=str(request.url)), Meta=OBMeta())
