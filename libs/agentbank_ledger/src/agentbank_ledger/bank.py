"""One bank core: customers, accounts, the app/ops operations and ISO participation.

The customer app and the ops API are methods on :class:`Bank`. ``agentbank_ledger.api``
exposes the same operations over HTTP. FAPI token checks arrive in M3; until then
the HTTP layer takes an explicit customer or staff principal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from random import Random

from agentbank_common.ids import new_end_to_end_id, new_msg_id, new_uetr
from agentbank_iso import builders, models
from agentbank_iso.errors import FieldLengthError

from .books import HOUSE, BankBooks
from .errors import LedgerError
from .simnow import ReturnDecision, SimNow, SwitchReply

__all__ = ["Bank", "BankProfile", "Ids"]


@dataclass(frozen=True)
class BankProfile:
    """The fields of ``config/banks/*.yaml`` the core enforces."""

    id: str
    name: str
    routing: str
    per_payment_limit_minor: int
    daily_limit_minor: int
    new_payee_cooling_hours: int
    name_check: bool
    step_up_threshold_minor: int
    stricter_when_agent_initiated: bool
    fapi_variant: str


class Ids:
    """ISO identifiers. Pass a seeded ``Random`` when the run must be reproducible."""

    def __init__(self, rng: Random | None = None) -> None:
        self.rng = rng

    def msg(self, prefix: str = "M") -> str:
        return new_msg_id(prefix, self.rng)

    def e2e(self) -> str:
        return new_end_to_end_id("E", self.rng)

    def uetr(self) -> str:
        return new_uetr(self.rng)


class Bank:
    """A simulated bank participant."""

    def __init__(
        self,
        profile: BankProfile,
        db_path: Path,
        *,
        clock: Callable[[], date],
        moment: Callable[[], datetime],
        ids: Ids | None = None,
    ) -> None:
        self.profile = profile
        self.books = BankBooks(db_path, profile.routing)
        self.clock = clock
        self.moment = moment
        self.ids = ids or Ids()
        self.switch: SimNow | None = None
        self.response_delay_s = 0.0
        self.auto_accept_returns = True
        self.hold_outbound = False
        self._return_holds: dict[str, tuple[str, int]] = {}
        self._pending_recalls: dict[str, models.Camt056CancellationRequest] = {}
        self._queued: dict[str, dict[str, object]] = {}

    @property
    def bank_id(self) -> str:
        return self.profile.id

    @property
    def routing(self) -> str:
        return self.profile.routing

    def open_books(self, prefund_minor: int) -> None:
        self.books.open_day(prefund_minor, self._ts())

    # --- customers and accounts -------------------------------------------- #
    def add_customer(
        self,
        name: str,
        email: str,
        phone: str = "",
        risk_tier: str = "standard",
        notes: str = "",
    ) -> str:
        self.books.add_customer(email, name, email, phone, risk_tier, notes)
        self.books.audit(self._ts(), "customer.create", email)
        return email

    def add_account(self, customer_id: str, kind: str, number: str) -> str:
        account_id = f"{self.bank_id}:{number}"
        self.books.add_account(account_id, customer_id, kind, number)
        return account_id

    def deposit(self, account_id: str, amount_minor: int, description: str = "DEPOSIT") -> None:
        """Credit a customer from the house account (opening balances and payroll)."""
        if amount_minor <= 0:
            raise LedgerError("amount must be positive")
        if self.books.net_credit(HOUSE) < amount_minor:
            raise LedgerError("house account cannot fund this deposit")
        txn = self.ids.msg("D")
        self.books.transfer(HOUSE, account_id, amount_minor, txn, self._ts())
        self.books.add_transaction(
            txn, account_id, amount_minor, "credit", description, self.profile.name, "", None
        )

    def available(self, account_id: str) -> int:
        return self.books.net_credit(account_id)

    def list_accounts(self, customer_id: str) -> list[dict[str, object]]:
        rows = []
        for row in self.books.accounts_of(customer_id):
            rows.append(
                {
                    "accountId": row["id"],
                    "type": row["type"],
                    "number": row["number"],
                    "routing": row["routing"],
                    "currency": row["currency"],
                    "status": row["status"],
                    "availableMinor": self.available(str(row["id"])),
                }
            )
        return rows

    def list_transactions(self, account_id: str) -> list[dict[str, object]]:
        return [dict(row) for row in self.books.list_transactions(account_id)]

    def add_payee(
        self,
        customer_id: str,
        name: str,
        account_number: str,
        routing: str,
        created_by: str = "user",
    ) -> str:
        payee_id = self.ids.msg("PY")
        self.books.add_payee(
            {
                "id": payee_id,
                "customer_id": customer_id,
                "name": name,
                "account_number": account_number,
                "routing": routing,
                "created_by": created_by,
                "created_at": self._ts(),
                "verified": 0,
            }
        )
        return payee_id

    def list_payees(self, customer_id: str) -> list[dict[str, object]]:
        return [dict(row) for row in self.books.payees_of(customer_id)]

    def internal_transfer(
        self, src_account: str, dst_account: str, amount_minor: int, description: str = "TRANSFER"
    ) -> str:
        self._require_open(src_account, amount_minor)
        txn = self.ids.msg("I")
        self.books.transfer(src_account, dst_account, amount_minor, txn, self._ts())
        self.books.add_transaction(
            txn, src_account, amount_minor, "debit", description, "", "", None
        )
        self.books.add_transaction(
            self.ids.msg("I"), dst_account, amount_minor, "credit", description, "", "", None
        )
        return txn

    # --- inter-bank -------------------------------------------------------- #
    def send_interbank(
        self,
        debtor_account_id: str,
        creditor_name: str,
        creditor_account: str,
        creditor_routing: str,
        amount_minor: int,
        remittance: tuple[str, ...] = (),
        *,
        principal: str = "",
        via: str = "app",
        idempotency_key: str | None = None,
        consent_id: str | None = None,
        agent_run_id: str | None = None,
        hold: bool = False,
        approved: bool = False,
    ) -> SwitchReply:
        """Debit the customer and send a pacs.008. Rejects release the hold."""
        self.books.set_business_date(self.clock().isoformat())
        if idempotency_key:
            prior = self.books.payment_by_idempotency(idempotency_key)
            if prior is not None:
                return SwitchReply(str(prior["status"]), None, b"", 0.0, "idempotent replay")
        if hold or self.hold_outbound:
            payment_id = self.ids.msg("H")
            self._queued[payment_id] = {
                "debtor_account_id": debtor_account_id,
                "creditor_name": creditor_name,
                "creditor_account": creditor_account,
                "creditor_routing": creditor_routing,
                "amount_minor": amount_minor,
                "remittance": remittance,
                "principal": principal,
                "via": via,
                "idempotency_key": idempotency_key,
                "consent_id": consent_id,
                "agent_run_id": agent_run_id,
                "approved": True,
            }
            self.books.add_payment(
                self._payment_row(
                    payment_id,
                    "",
                    "",
                    debtor_account_id,
                    creditor_name,
                    creditor_account,
                    creditor_routing,
                    amount_minor,
                    "HELD",
                    principal,
                    via,
                    consent_id,
                    agent_run_id,
                    None,
                    idempotency_key,
                    "out",
                )
            )
            return SwitchReply("HELD", None, b"", 0.0, payment_id)
        limit = self._payment_limit(via)
        if amount_minor > limit or amount_minor > self.profile.daily_limit_minor:
            return SwitchReply("RJCT", "AM02", b"", 0.0, "bank limit")
        spent = self.books.outbound_today(debtor_account_id)
        if spent + amount_minor > self.profile.daily_limit_minor:
            return SwitchReply("RJCT", "AM02", b"", 0.0, "daily limit")
        cooled = self._cooling_block(debtor_account_id, creditor_account, creditor_routing)
        if cooled:
            return SwitchReply("RJCT", "AM02", b"", 0.0, cooled)
        if via == "agent" and amount_minor >= self.profile.step_up_threshold_minor and not approved:
            hitl_id = self.ids.msg("HIT")
            self.books.add_hitl(hitl_id, principal or debtor_account_id, creditor_account, "OPEN")
            return SwitchReply("HELD", "STEP", b"", 0.0, hitl_id)
        try:
            self._require_open(debtor_account_id, amount_minor)
        except LedgerError as exc:
            return SwitchReply("RJCT", "AM04", b"", 0.0, str(exc))
        try:
            document, payment = self._build_pacs008(
                debtor_account_id,
                creditor_name,
                creditor_account,
                creditor_routing,
                amount_minor,
                remittance,
            )
        except FieldLengthError as exc:
            return SwitchReply("RJCT", "FF01", b"", 0.0, str(exc))
        wrapped = builders.envelope(
            models.BusinessHeader(
                from_routing=self.routing,
                to_routing=creditor_routing,
                biz_msg_idr=self.ids.msg("B"),
                msg_def_idr="pacs.008.001.08",
                created_at=self.moment(),
            ),
            document,
        )
        txn = self.ids.msg("HLD")
        self.books.hold(debtor_account_id, amount_minor, txn, self._ts())
        reply = self._switch().submit(wrapped)
        status = "ACSC" if reply.tx_status == "ACSC" else "RJCT"
        if reply.tx_status == "ACSC":
            self.books.settle_hold(debtor_account_id, amount_minor, self.ids.msg("SET"), self._ts())
            self.books.add_transaction(
                self.ids.msg("TX"),
                debtor_account_id,
                amount_minor,
                "debit",
                "INSTANT PAYMENT",
                creditor_name,
                " ".join(remittance),
                payment.msg_id,
            )
        else:
            self.books.release_hold(
                debtor_account_id, amount_minor, self.ids.msg("REL"), self._ts()
            )
        self.books.add_payment(
            self._payment_row(
                self.ids.msg("P"),
                payment.end_to_end_id,
                payment.uetr,
                debtor_account_id,
                creditor_name,
                creditor_account,
                creditor_routing,
                amount_minor,
                status,
                principal,
                via,
                consent_id,
                agent_run_id,
                payment.msg_id,
                idempotency_key,
                "out",
            )
        )
        self.books.audit(self._ts(), "payment." + status, payment.uetr)
        return reply

    def release_payment(self, payment_id: str) -> SwitchReply:
        queued = self._queued.pop(payment_id, None)
        if queued is None:
            raise LedgerError(f"payment {payment_id} is not held")
        self.books.update_payment_status(payment_id, "RELEASED")
        amount = queued["amount_minor"]
        if not isinstance(amount, int):
            raise LedgerError("queued payment amount is not an int")
        key = queued["idempotency_key"]
        consent = queued["consent_id"]
        run_id = queued["agent_run_id"]
        return self.send_interbank(
            str(queued["debtor_account_id"]),
            str(queued["creditor_name"]),
            str(queued["creditor_account"]),
            str(queued["creditor_routing"]),
            amount,
            queued["remittance"] if isinstance(queued["remittance"], tuple) else (),
            principal=str(queued["principal"]),
            via=str(queued["via"]),
            idempotency_key=key if isinstance(key, str) else None,
            consent_id=consent if isinstance(consent, str) else None,
            agent_run_id=run_id if isinstance(run_id, str) else None,
            approved=bool(queued["approved"]),
        )

    def request_return(self, uetr: str, reason: str = "CUST") -> SwitchReply:
        """Send camt.056 for an outbound payment we settled. Auto-accept returns funds."""
        row = self.books.payment_by_uetr(uetr, "out")
        if row is None or str(row["status"]) != "ACSC":
            return SwitchReply("RJCT", "FF01", b"", 0.0, "payment is not settled")
        req = models.Camt056CancellationRequest(
            assignment_id=self.ids.msg("A"),
            created_at=self.moment(),
            assigner_routing=self.routing,
            assignee_routing=str(row["creditor_routing"]),
            case_id=self.ids.msg("C"),
            orgnl_msg_id=str(row["iso_msg_id"] or ""),
            orgnl_msg_nm_id="pacs.008.001.08",
            orgnl_end_to_end_id=str(row["e2e_id"]),
            orgnl_uetr=uetr,
            cancellation_reason_code=reason,
        )
        document = builders.build_camt056(req)
        wrapped = self._wrap(document, "camt.056.001.08", str(row["creditor_routing"]))
        return self._switch().submit(wrapped)

    def respond_return(self, uetr: str, accept: bool) -> SwitchReply:
        """Ops answer to a parked camt.056 (used when auto-accept is off)."""
        req = self._pending_recalls.pop(uetr, None)
        if req is None:
            raise LedgerError(f"no parked recall for {uetr}")
        if not accept:
            xml = self._camt029(req, "RJCR")
            return self._switch().submit(xml)
        decision = self._accept_recall(req)
        if decision.pacs004_xml is None:
            return SwitchReply("RJCT", "AM04", b"", 0.0, "cannot fund the return")
        return self._switch().submit(decision.pacs004_xml)

    # --- participant callbacks --------------------------------------------- #
    def account_exists(self, number: str) -> bool:
        return self.books.account_by_number(number) is not None

    def on_credit_settled(self, payment: models.Pacs008Payment) -> None:
        account = self.books.account_by_number(payment.creditor_account)
        if account is None:
            raise LedgerError("credited account disappeared")
        account_id = str(account["id"])
        txn = self.ids.msg("IN")
        self.books.receive(account_id, payment.amount_minor, txn, self._ts())
        self.books.add_transaction(
            txn,
            account_id,
            payment.amount_minor,
            "credit",
            "INSTANT PAYMENT",
            payment.debtor_name,
            " ".join(payment.remittance),
            payment.msg_id,
        )
        self.books.add_payment(
            self._payment_row(
                self.ids.msg("P"),
                payment.end_to_end_id,
                payment.uetr,
                account_id,
                payment.debtor_name,
                payment.debtor_account,
                payment.debtor_agent,
                payment.amount_minor,
                "ACSC",
                "",
                "iso",
                None,
                None,
                payment.msg_id,
                None,
                "in",
            )
        )
        note = models.Camt054Notification(
            msg_id=self.ids.msg("N"),
            created_at=self.moment(),
            notification_id=self.ids.msg("NID"),
            account_id=payment.creditor_account,
            entries=(
                models.Entry(
                    amount_minor=payment.amount_minor,
                    credit_debit="CRDT",
                    additional_entry_info="credit",
                    remittance=payment.remittance,
                ),
            ),
        )
        self.books.add_document(
            self.ids.msg("DOC"),
            "camt.054",
            builders.build_camt054(note).decode("utf-8"),
            customer_id=str(account["customer_id"] or ""),
        )

    def on_cancellation(self, req: models.Camt056CancellationRequest) -> ReturnDecision:
        if not self.auto_accept_returns:
            self._pending_recalls[req.orgnl_uetr] = req
            return ReturnDecision(accept=False, deferred=True)
        return self._accept_recall(req)

    def on_return_settled(self, original: models.Pacs008Payment, amount: int) -> None:
        """The creditor bank's hold becomes a settlement-asset decrease."""
        held = self._return_holds.pop(original.uetr, None)
        if held is None:
            return
        account_id, held_amount = held
        if held_amount != amount:
            raise LedgerError("return amount does not match the hold")
        self.books.settle_hold(account_id, amount, self.ids.msg("RSET"), self._ts())
        self.books.add_transaction(
            self.ids.msg("TX"),
            account_id,
            amount,
            "debit",
            "RETURN",
            original.debtor_name,
            "",
            original.msg_id,
        )
        row = self.books.payment_by_uetr(original.uetr, "in")
        if row is not None:
            self.books.update_payment_status(str(row["id"]), "RETURNED")

    def on_return_received(self, original: models.Pacs008Payment, amount: int) -> None:
        row = self.books.payment_by_uetr(original.uetr, "out")
        if row is None:
            raise LedgerError("original outbound payment is missing")
        account_id = str(row["debtor_acct"])
        self.books.receive(account_id, amount, self.ids.msg("RCV"), self._ts())
        self.books.add_transaction(
            self.ids.msg("TX"),
            account_id,
            amount,
            "credit",
            "RETURN",
            original.creditor_name,
            "",
            original.msg_id,
        )
        self.books.update_payment_status(str(row["id"]), "RETURNED")

    def release_return_hold(self, uetr: str) -> None:
        held = self._return_holds.pop(uetr, None)
        if held is None:
            return
        account_id, amount = held
        self.books.release_hold(account_id, amount, self.ids.msg("RREL"), self._ts())

    def on_rfp(self, rfp: models.Pain013Rfp) -> None:
        self.books.add_rfp(
            {
                "id": self.ids.msg("RFP"),
                "end_to_end_id": rfp.end_to_end_id,
                "amount_minor": rfp.amount_minor,
                "creditor_name": rfp.creditor_name,
                "creditor_routing": rfp.creditor_agent,
                "debtor_name": rfp.debtor_name,
                "remittance": " ".join(rfp.remittance),
                "status": "PENDING",
            }
        )

    def on_rfp_status(self, status: models.Pain014RfpStatus) -> None:
        self.books.update_rfp(status.orgnl_end_to_end_id, status.tx_status)

    def send_rfp(
        self,
        creditor_name: str,
        debtor_name: str,
        debtor_routing: str,
        amount_minor: int,
        remittance: tuple[str, ...] = (),
    ) -> SwitchReply:
        e2e = self.ids.e2e()
        rfp = models.Pain013Rfp(
            msg_id=self.ids.msg("R"),
            created_at=self.moment(),
            initiating_party=creditor_name,
            pmt_inf_id=self.ids.msg("PI"),
            end_to_end_id=e2e,
            amount_minor=amount_minor,
            execution_date=self.clock(),
            debtor_name=debtor_name,
            debtor_agent=debtor_routing,
            creditor_name=creditor_name,
            creditor_agent=self.routing,
            remittance=remittance,
        )
        document = builders.build_pain013(rfp)
        self.books.add_rfp(
            {
                "id": self.ids.msg("RFP"),
                "end_to_end_id": e2e,
                "amount_minor": amount_minor,
                "creditor_name": creditor_name,
                "creditor_routing": self.routing,
                "debtor_name": debtor_name,
                "remittance": " ".join(remittance),
                "status": "SENT",
            }
        )
        return self._switch().submit(self._wrap(document, "pain.013.001.07", debtor_routing))

    def respond_rfp(self, end_to_end_id: str, accept: bool) -> SwitchReply:
        rows = [row for row in self.books.rfp_rows() if row["end_to_end_id"] == end_to_end_id]
        if not rows:
            raise LedgerError(f"unknown RfP {end_to_end_id}")
        row = rows[0]
        status = models.Pain014RfpStatus(
            msg_id=self.ids.msg("RS"),
            created_at=self.moment(),
            initiating_party=str(row["debtor_name"]),
            orgnl_msg_id=end_to_end_id,
            orgnl_msg_nm_id="pain.013.001.07",
            orgnl_pmt_inf_id=end_to_end_id,
            orgnl_end_to_end_id=end_to_end_id,
            tx_status="ACCP" if accept else "RJCT",
        )
        document = builders.build_pain014(status)
        self.books.update_rfp(end_to_end_id, status.tx_status)
        creditor_routing = str(row["creditor_routing"])
        return self._switch().submit(self._wrap(document, "pain.014.001.07", creditor_routing))

    def rfp_inbox(self) -> list[dict[str, object]]:
        return [dict(row) for row in self.books.rfp_rows("PENDING")]

    def pay_rfp(
        self, end_to_end_id: str, debtor_account_id: str, creditor_account: str
    ) -> SwitchReply:
        rows = [row for row in self.books.rfp_rows() if row["end_to_end_id"] == end_to_end_id]
        if not rows:
            raise LedgerError(f"unknown RfP {end_to_end_id}")
        row = rows[0]
        reply = self.send_interbank(
            debtor_account_id,
            str(row["creditor_name"]),
            creditor_account,
            str(row["creditor_routing"]),
            int(row["amount_minor"]),
            remittance=(str(row["remittance"]),) if row["remittance"] else (),
        )
        if reply.tx_status == "ACSC":
            self.books.update_rfp(end_to_end_id, "PAID")
        return reply

    def notifications(self) -> list[str]:
        return [str(row["body"]) for row in self.books.documents_named("camt.054")]

    def grant_consent(
        self,
        client_id: str,
        sub: str,
        scopes: str,
        limits_json: str = "{}",
        expires_at: str = "",
    ) -> str:
        consent_id = self.ids.msg("CN")
        self.books.add_consent(
            {
                "id": consent_id,
                "client_id": client_id,
                "sub": sub,
                "scopes": scopes,
                "status": "AUTHORIZED",
                "limits_json": limits_json,
                "payees_json": "[]",
                "expires_at": expires_at or self._ts(),
                "revoked_at": None,
            }
        )
        return consent_id

    def list_consents(self, sub: str) -> list[dict[str, object]]:
        return [dict(row) for row in self.books.consents_rows() if row["sub"] == sub]

    def revoke_consent(self, consent_id: str, sub: str) -> None:
        row = self.books.consent(consent_id)
        if row is None or str(row["sub"]) != sub:
            raise LedgerError("unknown consent")
        self.books.update_consent(consent_id, status="REVOKED", revoked_at=self._ts())

    # --- ops --------------------------------------------------------------- #
    def freeze_account(self, account_id: str) -> None:
        self.books.set_account_status(account_id, "FROZEN")
        self.books.audit(self._ts(), "account.freeze", account_id)

    def unfreeze_account(self, account_id: str) -> None:
        self.books.set_account_status(account_id, "OPEN")

    def open_case(self, summary: str) -> str:
        case_id = self.ids.msg("CS")
        self.books.add_case(case_id, "OPEN", summary)
        return case_id

    def close_case(self, case_id: str) -> None:
        self.books.update_case(case_id, "CLOSED")

    def customer_profile(self, customer_id: str) -> dict[str, object] | None:
        for row in self.books.customers():
            if row["id"] == customer_id:
                return dict(row)
        return None

    def payment_queue(self) -> list[dict[str, object]]:
        return [dict(row) for row in self.books.payments_rows() if row["status"] == "HELD"]

    def approve_hitl(self, hitl_id: str) -> None:
        self.books.update_hitl(hitl_id, "APPROVED")

    def deny_hitl(self, hitl_id: str) -> None:
        self.books.update_hitl(hitl_id, "DENIED")

    # --- internals --------------------------------------------------------- #
    def _accept_recall(self, req: models.Camt056CancellationRequest) -> ReturnDecision:
        inbound = self.books.payment_by_uetr(req.orgnl_uetr, "in")
        if inbound is None or str(inbound["status"]) != "ACSC":
            return ReturnDecision(accept=False, camt029_xml=self._camt029(req, "RJCR"))
        account_id = str(inbound["debtor_acct"])
        amount = int(inbound["amount_minor"])
        if self.available(account_id) < amount:
            return ReturnDecision(accept=False, camt029_xml=self._camt029(req, "RJCR"))
        self.books.hold(account_id, amount, self.ids.msg("RH"), self._ts())
        self._return_holds[req.orgnl_uetr] = (account_id, amount)
        returned = models.Pacs004Return(
            msg_id=self.ids.msg("RT"),
            created_at=self.moment(),
            orgnl_msg_id=req.orgnl_msg_id,
            orgnl_msg_nm_id="pacs.008.001.08",
            orgnl_end_to_end_id=req.orgnl_end_to_end_id,
            orgnl_uetr=req.orgnl_uetr,
            returned_amount_minor=amount,
            settlement_date=self.clock(),
            return_reason_code="FOCR",
        )
        document = builders.build_pacs004(returned)
        # Funds move back to the original debtor agent, who sent the camt.056.
        wrapped = self._wrap(document, "pacs.004.001.10", req.assigner_routing)
        return ReturnDecision(accept=True, pacs004_xml=wrapped)

    def _camt029(self, req: models.Camt056CancellationRequest, code: str) -> bytes:
        res = models.Camt029Resolution(
            assignment_id=self.ids.msg("Z"),
            created_at=self.moment(),
            assigner_routing=self.routing,
            assignee_routing=req.assigner_routing,
            status_confirmation=code,
            orgnl_end_to_end_id=req.orgnl_end_to_end_id,
            orgnl_uetr=req.orgnl_uetr,
        )
        return self._wrap(builders.build_camt029(res), "camt.029.001.09", req.assigner_routing)

    def _build_pacs008(
        self,
        debtor_account_id: str,
        creditor_name: str,
        creditor_account: str,
        creditor_routing: str,
        amount_minor: int,
        remittance: tuple[str, ...],
    ) -> tuple[bytes, models.Pacs008Payment]:
        account = self.books.account(debtor_account_id)
        if account is None:
            raise LedgerError("unknown debtor account")
        customer_id = str(account["customer_id"] or "")
        profile = self.customer_profile(customer_id)
        debtor_name = str(profile["name"]) if profile else self.profile.name
        payment = models.Pacs008Payment(
            msg_id=self.ids.msg("M"),
            created_at=self.moment(),
            end_to_end_id=self.ids.e2e(),
            uetr=self.ids.uetr(),
            amount_minor=amount_minor,
            settlement_date=self.clock(),
            debtor_name=debtor_name,
            debtor_account=str(account["number"]),
            debtor_agent=self.routing,
            creditor_name=creditor_name,
            creditor_account=creditor_account,
            creditor_agent=creditor_routing,
            remittance=remittance,
        )
        return builders.build_pacs008(payment), payment

    def _wrap(self, document: bytes, message_id: str, to_routing: str) -> bytes:
        return builders.envelope(
            models.BusinessHeader(
                from_routing=self.routing,
                to_routing=to_routing,
                biz_msg_idr=self.ids.msg("B"),
                msg_def_idr=message_id,
                created_at=self.moment(),
            ),
            document,
        )

    def _require_open(self, account_id: str, amount_minor: int) -> None:
        account = self.books.account(account_id)
        if account is None:
            raise LedgerError("unknown account")
        if str(account["status"]) != "OPEN":
            raise LedgerError("account is frozen")
        if amount_minor <= 0:
            raise LedgerError("amount must be positive")
        if self.available(account_id) < amount_minor:
            raise LedgerError("insufficient funds")

    def _payment_limit(self, via: str) -> int:
        limit = self.profile.per_payment_limit_minor
        if via == "agent" and self.profile.stricter_when_agent_initiated:
            return limit // 2
        return limit

    def _cooling_block(self, debtor_account_id: str, creditor_account: str, routing: str) -> str:
        if self.profile.new_payee_cooling_hours <= 0:
            return ""
        account = self.books.account(debtor_account_id)
        if account is None or account["customer_id"] is None:
            return ""
        customer_id = str(account["customer_id"])
        cutoff = self.moment() - timedelta(hours=self.profile.new_payee_cooling_hours)
        for payee in self.books.payees_of(customer_id):
            same_account = str(payee["account_number"]) == creditor_account
            same_routing = str(payee["routing"]) == routing
            if same_account and same_routing:
                created = datetime.fromisoformat(str(payee["created_at"]))
                if created > cutoff:
                    return "new payee is inside the cooling period"
        return ""

    def _payment_row(
        self,
        payment_id: str,
        e2e: str,
        uetr: str,
        debtor_acct: str,
        creditor_name: str,
        creditor_acct: str,
        creditor_routing: str,
        amount: int,
        status: str,
        principal: str,
        via: str,
        consent_id: str | None,
        agent_run_id: str | None,
        iso_msg_id: str | None,
        idempotency_key: str | None,
        direction: str,
    ) -> dict[str, object]:
        return {
            "id": payment_id,
            "e2e_id": e2e or payment_id[:35],
            "uetr": uetr or payment_id[:36],
            "debtor_acct": debtor_acct,
            "creditor_name": creditor_name,
            "creditor_acct": creditor_acct,
            "creditor_routing": creditor_routing,
            "amount_minor": amount,
            "status": status,
            "initiated_by_principal": principal,
            "initiated_via": via,
            "consent_id": consent_id,
            "agent_run_id": agent_run_id,
            "iso_msg_id": iso_msg_id,
            "idempotency_key": idempotency_key,
            "direction": direction,
            "created_on": self.clock().isoformat(),
        }

    def _switch(self) -> SimNow:
        if self.switch is None:
            raise LedgerError("bank is not attached to the switch")
        return self.switch

    def _ts(self) -> str:
        return self.moment().isoformat()
