"""FDX-inspired resource routes (SPEC §5.1). Not an FDX schema and not certified.

The shapes below are written from the public description of the resources
(accounts, transactions, consents, and a testbed payments extension). Error
bodies use ``{code, message, debugMessage}``. ``debugMessage`` is free text
on purpose: it is injection channel C7.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.responses import Response

from agentbank_ledger.bank import Bank
from agentbank_ledger.simnow import SwitchReply

from .errors import FDX_INTERACTION_ID_HEADER, FdxError
from .fapi import AccessClaims, FapiError, FapiGate

__all__ = ["mount_fdx"]


class ConsentIn(BaseModel):
    customer_id: str
    scopes: str = "fdx:payments fdx:accounts:read"
    per_payment_minor: int = 0
    expires_at: str = ""


class PaymentIn(BaseModel):
    consent_id: str
    debtor_account_id: str
    creditor_name: str
    creditor_account: str
    creditor_routing: str
    amount_minor: int
    remittance: list[str] = Field(default_factory=list)


class PayeeIn(BaseModel):
    name: str
    account_number: str
    routing: str


def mount_fdx(app: FastAPI, bank: Bank, gate: FapiGate) -> None:
    """Add ``/fdx/v6`` and the OAuth endpoints the resource server relies on."""

    @app.middleware("http")
    async def interaction_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/fdx"):
            incoming = request.headers.get(FDX_INTERACTION_ID_HEADER) or str(uuid.uuid4())
            response.headers[FDX_INTERACTION_ID_HEADER] = incoming
        return response

    @app.exception_handler(FapiError)
    def on_fapi(request: Request, exc: FapiError) -> JSONResponse:
        if request.url.path.startswith("/fdx"):
            body = FdxError(exc.error.upper(), exc.description).to_dict()
            return JSONResponse(status_code=exc.status, content=body)
        return JSONResponse(
            status_code=exc.status,
            content={"error": exc.error, "error_description": exc.description},
        )

    def endpoint(request: Request) -> str:
        return str(request.base_url).rstrip("/") + request.url.path

    def access(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        dpop: Annotated[str | None, Header()] = None,
        x_client_cert_sha256: Annotated[str | None, Header()] = None,
    ) -> AccessClaims:
        return gate.check_resource(
            request.method, endpoint(request), authorization, dpop, x_client_cert_sha256
        )

    Principal = Annotated[AccessClaims, Depends(access)]

    @app.post("/oauth/par")
    def par(
        request: Request,
        client_assertion: Annotated[str, Form()],
        client_assertion_type: Annotated[str, Form()],
        client_id: Annotated[str, Form()],
        redirect_uri: Annotated[str, Form()],
        scope: Annotated[str, Form()],
        code_challenge: Annotated[str, Form()],
        code_challenge_method: Annotated[str, Form()],
        consent_id: Annotated[str, Form()] = "",
        sub: Annotated[str, Form()] = "",
    ) -> dict[str, object]:
        request_uri = gate.push(
            client_assertion=client_assertion,
            client_assertion_type=client_assertion_type,
            audience=endpoint(request),
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            consent_id=consent_id,
            sub=sub,
        )
        return {"request_uri": request_uri, "expires_in": 90}

    @app.get("/oauth/authorize")
    def authorize(request_uri: Annotated[str | None, Query()] = None) -> dict[str, str]:
        code, redirect_uri, sub = gate.authorize(request_uri)
        consent_id = gate.consent_of(code)
        if consent_id:
            row = bank.books.consent(consent_id)
            if row is not None and str(row["status"]) == "AWAITING_AUTHORISATION":
                bank.books.update_consent(consent_id, status="AUTHORIZED")
        return {"code": code, "redirect_uri": redirect_uri, "sub": sub}

    @app.post("/oauth/token")
    def token(
        request: Request,
        grant_type: Annotated[str, Form()],
        client_assertion: Annotated[str, Form()] = "",
        client_assertion_type: Annotated[str, Form()] = "",
        code: Annotated[str, Form()] = "",
        code_verifier: Annotated[str, Form()] = "",
        client_secret: Annotated[str, Form()] = "",
        dpop: Annotated[str | None, Header()] = None,
        x_client_cert_sha256: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        if client_secret:
            raise FapiError(
                401, "invalid_client", "client_secret is not accepted; use private_key_jwt"
            )
        access_token = gate.issue_token(
            grant_type=grant_type,
            client_assertion=client_assertion,
            client_assertion_type=client_assertion_type,
            audience=endpoint(request),
            code=code,
            code_verifier=code_verifier,
            dpop=dpop,
            cert_sha256=x_client_cert_sha256,
            htu=endpoint(request),
        )
        kind = "DPoP" if gate.variant == "dpop" else "Bearer"
        return {"access_token": access_token, "token_type": kind, "expires_in": 600}

    @app.get("/fdx/v6/accounts")
    def accounts(principal: Principal) -> dict[str, object]:
        _require_scope(principal.scope, "fdx:accounts:read")
        return {"accounts": bank.list_accounts(principal.sub)}

    @app.get("/fdx/v6/accounts/{account_id}")
    def account(account_id: str, principal: Principal) -> dict[str, object]:
        _require_scope(principal.scope, "fdx:accounts:read")
        for row in bank.list_accounts(principal.sub):
            if row["accountId"] == account_id:
                return row
        raise FapiError(404, "account_not_found", "account is not visible to this customer")

    @app.get("/fdx/v6/accounts/{account_id}/transactions")
    def transactions(
        account_id: str, principal: Principal, offset: int = 0, limit: int = 100
    ) -> dict[str, object]:
        _require_scope(principal.scope, "fdx:accounts:read")
        _owned(bank, principal.sub, account_id)
        rows = bank.list_transactions(account_id)
        return {"transactions": rows[offset : offset + limit], "offset": offset, "limit": limit}

    @app.get("/fdx/v6/accounts/{account_id}/statements")
    def statements(account_id: str, principal: Principal) -> dict[str, object]:
        _require_scope(principal.scope, "fdx:accounts:read")
        _owned(bank, principal.sub, account_id)
        return {"statements": []}

    @app.get("/fdx/v6/accounts/{account_id}/payment-networks")
    def networks(account_id: str, principal: Principal) -> dict[str, object]:
        _require_scope(principal.scope, "fdx:accounts:read")
        _owned(bank, principal.sub, account_id)
        row = bank.books.account(account_id)
        if row is None:
            raise FapiError(404, "account_not_found", "account is not visible to this customer")
        return {
            "paymentNetworks": [
                {
                    "routingNumber": row["routing"],
                    "accountNumber": row["number"],
                    "type": "US_ACH",
                }
            ]
        }

    @app.get("/fdx/v6/customers/current")
    def current(principal: Principal) -> dict[str, object]:
        profile = bank.customer_profile(principal.sub)
        if profile is None:
            raise FapiError(404, "customer_not_found", "no customer for this token")
        return profile

    @app.post("/fdx/v6/payment-consents")
    def create_consent(body: ConsentIn, principal: Principal) -> dict[str, str]:
        _require_scope(principal.scope, "fdx:payments")
        if bank.customer_profile(body.customer_id) is None:
            raise FapiError(404, "customer_not_found", "customer is not at this bank")
        consent_id = bank.grant_consent(
            principal.client_id,
            body.customer_id,
            body.scopes,
            limits_json=json.dumps({"perPaymentMinor": body.per_payment_minor}),
            expires_at=body.expires_at,
        )
        bank.books.update_consent(consent_id, status="AWAITING_AUTHORISATION")
        return {"consentId": consent_id, "status": "AWAITING_AUTHORISATION"}

    @app.get("/fdx/v6/consents/{consent_id}")
    def read_consent(consent_id: str, principal: Principal) -> dict[str, object]:
        return _consent_for(bank, consent_id, principal.sub)

    @app.put("/fdx/v6/consents/{consent_id}/revocation")
    def revoke(consent_id: str, principal: Principal) -> dict[str, str]:
        _consent_for(bank, consent_id, principal.sub)
        bank.revoke_consent(consent_id, principal.sub)
        return {"consentId": consent_id, "status": "REVOKED"}

    @app.post("/fdx/v6/payments", status_code=201)
    def pay(
        body: PaymentIn,
        principal: Principal,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, object]:
        _require_scope(principal.scope, "fdx:payments")
        if principal.consent_id and principal.consent_id != body.consent_id:
            raise FapiError(403, "consent_mismatch", "token is bound to a different consent")
        row = _consent_for(bank, body.consent_id, principal.sub)
        status = str(row["status"])
        if status == "REVOKED":
            raise FapiError(403, "consent_revoked", "consent has been revoked")
        if status != "AUTHORIZED":
            raise FapiError(403, "consent_not_authorised", "consent is not authorised")
        if str(row["client_id"]) != principal.client_id:
            raise FapiError(403, "consent_mismatch", "consent belongs to another client")
        _limit(row, body.amount_minor)
        _owned(bank, principal.sub, body.debtor_account_id)
        reply = bank.send_interbank(
            body.debtor_account_id,
            body.creditor_name,
            body.creditor_account,
            body.creditor_routing,
            body.amount_minor,
            tuple(body.remittance),
            principal=principal.sub,
            via="psp",
            idempotency_key=idempotency_key,
            consent_id=body.consent_id,
        )
        return _payment_body(bank, reply, body.consent_id)

    @app.get("/fdx/v6/payments/{payment_id}")
    def payment(payment_id: str, principal: Principal) -> dict[str, object]:
        _require_scope(principal.scope, "fdx:payments")
        for row in bank.books.payments_rows():
            if row["id"] == payment_id and str(row["initiated_by_principal"]) == principal.sub:
                return dict(row)
        raise FapiError(404, "payment_not_found", "payment is not visible to this customer")

    @app.post("/fdx/v6/payees", status_code=201)
    def payee(body: PayeeIn, principal: Principal) -> dict[str, str]:
        _require_scope(principal.scope, "fdx:payments")
        payee_id = bank.add_payee(
            principal.sub, body.name, body.account_number, body.routing, created_by="psp"
        )
        return {"payeeId": payee_id}


def _require_scope(scope: str, needed: str) -> None:
    if needed not in scope.split():
        raise FapiError(403, "insufficient_scope", f"token is missing {needed}")


def _owned(bank: Bank, customer_id: str, account_id: str) -> None:
    owned = {str(row["accountId"]) for row in bank.list_accounts(customer_id)}
    if account_id not in owned:
        raise FapiError(404, "account_not_found", "account is not visible to this customer")


def _consent_for(bank: Bank, consent_id: str, sub: str) -> dict[str, object]:
    row = bank.books.consent(consent_id)
    if row is None or str(row["sub"]) != sub:
        raise FapiError(403, "consent_mismatch", "consent is not held by this customer")
    return dict(row)


def _limit(row: dict[str, object], amount_minor: int) -> None:
    raw = row.get("limits_json") or "{}"
    try:
        limits = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise FapiError(403, "consent_limit", "consent limits are unreadable") from exc
    cap = limits.get("perPaymentMinor") if isinstance(limits, dict) else None
    if isinstance(cap, int) and cap > 0 and amount_minor > cap:
        raise FapiError(403, "consent_limit", "amount exceeds the consent per-payment limit")


def _payment_body(bank: Bank, reply: SwitchReply, consent_id: str) -> dict[str, object]:
    payment_id = ""
    for row in reversed(bank.books.payments_rows()):
        if row.get("consent_id") == consent_id:
            payment_id = str(row["id"])
            break
    status = "COMPLETED" if reply.tx_status == "ACSC" else "REJECTED"
    return {
        "paymentId": payment_id,
        "status": status,
        "txStatus": reply.tx_status,
        "reasonCode": reply.reason_code,
    }
