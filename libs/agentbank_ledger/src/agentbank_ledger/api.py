"""HTTP app and ops APIs for one bank (SPEC §5.1).

M2 authenticates with an explicit principal header. M3 replaces these checks
with FAPI 2.0 access tokens. ``X-Customer-Id`` is the customer email;
``X-Staff-Id`` is the staff principal.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .bank import Bank
from .errors import LedgerError
from .simnow import SwitchReply

__all__ = ["create_bank_app"]


class PayeeIn(BaseModel):
    name: str
    account_number: str
    routing: str


class TransferIn(BaseModel):
    src_account: str
    dst_account: str
    amount_minor: int
    description: str = "TRANSFER"


class PaymentIn(BaseModel):
    debtor_account_id: str
    creditor_name: str
    creditor_account: str
    creditor_routing: str
    amount_minor: int
    remittance: list[str] = Field(default_factory=list)
    idempotency_key: str | None = None
    via: str = "app"
    consent_id: str | None = None
    hold: bool = False


class RfpIn(BaseModel):
    creditor_name: str
    debtor_name: str
    debtor_routing: str
    amount_minor: int
    remittance: list[str] = Field(default_factory=list)


class RfpPayIn(BaseModel):
    debtor_account_id: str
    creditor_account: str


class ReturnIn(BaseModel):
    uetr: str
    reason: str = "CUST"


class ReturnDecisionIn(BaseModel):
    accept: bool


class CaseIn(BaseModel):
    summary: str


def create_bank_app(bank: Bank) -> FastAPI:
    """Build the customer app and the ops API for ``bank``."""
    app = FastAPI(title=bank.profile.name)

    def customer(x_customer_id: Annotated[str | None, Header()] = None) -> str:
        if not x_customer_id or bank.customer_profile(x_customer_id) is None:
            raise HTTPException(status_code=401, detail="unknown customer")
        return x_customer_id

    def staff(x_staff_id: Annotated[str | None, Header()] = None) -> str:
        if not x_staff_id:
            raise HTTPException(status_code=401, detail="missing staff principal")
        return x_staff_id

    def owned(customer_id: str, account_id: str) -> None:
        owned_ids = {str(row["accountId"]) for row in bank.list_accounts(customer_id)}
        if account_id not in owned_ids:
            raise HTTPException(status_code=404, detail="account not found")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "bank": bank.bank_id}

    @app.get("/app/v1/accounts")
    def accounts(customer_id: Annotated[str, Depends(customer)]) -> list[dict[str, object]]:
        return bank.list_accounts(customer_id)

    @app.get("/app/v1/accounts/{account_id}/transactions")
    def transactions(
        account_id: str, customer_id: Annotated[str, Depends(customer)]
    ) -> list[dict[str, object]]:
        owned(customer_id, account_id)
        return bank.list_transactions(account_id)

    @app.get("/app/v1/payees")
    def payees(customer_id: Annotated[str, Depends(customer)]) -> list[dict[str, object]]:
        return bank.list_payees(customer_id)

    @app.post("/app/v1/payees")
    def create_payee(
        body: PayeeIn, customer_id: Annotated[str, Depends(customer)]
    ) -> dict[str, str]:
        payee_id = bank.add_payee(customer_id, body.name, body.account_number, body.routing)
        return {"payeeId": payee_id}

    @app.post("/app/v1/transfers")
    def transfer(
        body: TransferIn, customer_id: Annotated[str, Depends(customer)]
    ) -> dict[str, str]:
        owned(customer_id, body.src_account)
        try:
            txn = bank.internal_transfer(
                body.src_account, body.dst_account, body.amount_minor, body.description
            )
        except LedgerError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"transactionId": txn}

    @app.post("/app/v1/payments")
    def payment(
        body: PaymentIn, customer_id: Annotated[str, Depends(customer)]
    ) -> dict[str, object]:
        owned(customer_id, body.debtor_account_id)
        reply = bank.send_interbank(
            body.debtor_account_id,
            body.creditor_name,
            body.creditor_account,
            body.creditor_routing,
            body.amount_minor,
            tuple(body.remittance),
            principal=customer_id,
            via=body.via,
            idempotency_key=body.idempotency_key,
            consent_id=body.consent_id,
            hold=body.hold,
        )
        return _reply(reply)

    @app.get("/app/v1/rfps")
    def rfps(customer_id: Annotated[str, Depends(customer)]) -> list[dict[str, object]]:
        del customer_id
        return bank.rfp_inbox()

    @app.post("/app/v1/rfps")
    def send_rfp(body: RfpIn, customer_id: Annotated[str, Depends(customer)]) -> dict[str, object]:
        del customer_id
        return _reply(
            bank.send_rfp(
                body.creditor_name,
                body.debtor_name,
                body.debtor_routing,
                body.amount_minor,
                tuple(body.remittance),
            )
        )

    @app.post("/app/v1/rfps/{end_to_end_id}/respond")
    def respond_rfp(
        end_to_end_id: str,
        body: ReturnDecisionIn,
        customer_id: Annotated[str, Depends(customer)],
    ) -> dict[str, object]:
        del customer_id
        try:
            reply = bank.respond_rfp(end_to_end_id, body.accept)
        except LedgerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _reply(reply)

    @app.post("/app/v1/rfps/{end_to_end_id}/pay")
    def pay_rfp(
        end_to_end_id: str,
        body: RfpPayIn,
        customer_id: Annotated[str, Depends(customer)],
    ) -> dict[str, object]:
        owned(customer_id, body.debtor_account_id)
        try:
            reply = bank.pay_rfp(end_to_end_id, body.debtor_account_id, body.creditor_account)
        except LedgerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _reply(reply)

    @app.get("/app/v1/consents")
    def consents(customer_id: Annotated[str, Depends(customer)]) -> list[dict[str, object]]:
        return bank.list_consents(customer_id)

    @app.post("/app/v1/consents/{consent_id}/revoke")
    def revoke(consent_id: str, customer_id: Annotated[str, Depends(customer)]) -> dict[str, str]:
        try:
            bank.revoke_consent(consent_id, customer_id)
        except LedgerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "REVOKED"}

    @app.post("/app/v1/hitl/{hitl_id}/approve")
    def approve_hitl(
        hitl_id: str, customer_id: Annotated[str, Depends(customer)]
    ) -> dict[str, str]:
        del customer_id
        bank.approve_hitl(hitl_id)
        return {"status": "APPROVED"}

    @app.post("/app/v1/hitl/{hitl_id}/deny")
    def deny_hitl(hitl_id: str, customer_id: Annotated[str, Depends(customer)]) -> dict[str, str]:
        del customer_id
        bank.deny_hitl(hitl_id)
        return {"status": "DENIED"}

    @app.get("/ops/v1/queue")
    def queue(staff_id: Annotated[str, Depends(staff)]) -> list[dict[str, object]]:
        del staff_id
        return bank.payment_queue()

    @app.post("/ops/v1/payments/{payment_id}/release")
    def release(payment_id: str, staff_id: Annotated[str, Depends(staff)]) -> dict[str, object]:
        del staff_id
        try:
            reply = bank.release_payment(payment_id)
        except LedgerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _reply(reply)

    @app.post("/ops/v1/cases")
    def open_case(body: CaseIn, staff_id: Annotated[str, Depends(staff)]) -> dict[str, str]:
        del staff_id
        return {"caseId": bank.open_case(body.summary)}

    @app.post("/ops/v1/cases/{case_id}/close")
    def close_case(case_id: str, staff_id: Annotated[str, Depends(staff)]) -> dict[str, str]:
        del staff_id
        bank.close_case(case_id)
        return {"status": "CLOSED"}

    @app.post("/ops/v1/returns")
    def request_return(
        body: ReturnIn, staff_id: Annotated[str, Depends(staff)]
    ) -> dict[str, object]:
        del staff_id
        return _reply(bank.request_return(body.uetr, body.reason))

    @app.post("/ops/v1/returns/{uetr}/respond")
    def respond_return(
        uetr: str, body: ReturnDecisionIn, staff_id: Annotated[str, Depends(staff)]
    ) -> dict[str, object]:
        del staff_id
        try:
            reply = bank.respond_return(uetr, body.accept)
        except LedgerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _reply(reply)

    @app.get("/ops/v1/customers/{customer_id}")
    def profile(customer_id: str, staff_id: Annotated[str, Depends(staff)]) -> dict[str, object]:
        del staff_id
        row = bank.customer_profile(customer_id)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown customer")
        return row

    @app.post("/ops/v1/accounts/{account_id}/freeze")
    def freeze(account_id: str, staff_id: Annotated[str, Depends(staff)]) -> dict[str, str]:
        del staff_id
        bank.freeze_account(account_id)
        return {"status": "FROZEN"}

    @app.post("/ops/v1/accounts/{account_id}/unfreeze")
    def unfreeze(account_id: str, staff_id: Annotated[str, Depends(staff)]) -> dict[str, str]:
        del staff_id
        bank.unfreeze_account(account_id)
        return {"status": "OPEN"}

    return app


def _reply(reply: SwitchReply) -> dict[str, object]:
    return {
        "txStatus": reply.tx_status,
        "reasonCode": reply.reason_code,
        "detail": reply.detail,
        "elapsedS": reply.elapsed_s,
    }
