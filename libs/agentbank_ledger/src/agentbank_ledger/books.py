"""Double-entry bank books on SQLAlchemy (SPEC §5.1).

Every ``post`` is rejected unless the legs sum to zero (debits negative,
credits positive). The settlement account is an asset: its position is
debits minus credits, and that figure is what the switch settlement ledger
must equal. Customer and house balances are liabilities (credits minus debits).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import case, create_engine, func, insert, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from .balance import Direction, Posting, is_balanced
from .errors import LedgerError
from .schema import (
    HOUSE,
    SETTLEMENT,
    SUSPENSE,
    accounts,
    audit_outbox,
    cases,
    consents,
    customers,
    documents,
    hitl_requests,
    kb_docs,
    ledger_entries,
    metadata,
    payees,
    payments,
    rfps,
    transactions,
)

__all__ = ["HOUSE", "SETTLEMENT", "SUSPENSE", "BankBooks"]

Leg = tuple[str, Direction, int]


class BankBooks:
    """One bank's books, stored in a single SQLite file (or any SQLAlchemy URL)."""

    def __init__(self, db_path: Path, routing: str) -> None:
        self.db_path = db_path
        self.routing = routing
        self._business_date = ""
        self.engine = self._make_engine()
        metadata.create_all(self.engine)
        self._ensure_internal()

    def _make_engine(self) -> Engine:
        return create_engine(
            f"sqlite:///{self.db_path}",
            poolclass=NullPool,
            connect_args={"check_same_thread": False},
        )

    def close(self) -> None:
        self.engine.dispose()

    def reopen(self) -> None:
        self.close()
        self.engine = self._make_engine()

    def _ensure_internal(self) -> None:
        with self.engine.begin() as conn:
            for account_id, number, kind in (
                (SETTLEMENT, "SETTLEMENT", "SETTLEMENT"),
                (SUSPENSE, "SUSPENSE", "SUSPENSE"),
                (HOUSE, "HOUSE", "HOUSE"),
            ):
                found = conn.execute(
                    select(accounts.c.id).where(accounts.c.id == account_id)
                ).first()
                if found is None:
                    conn.execute(
                        insert(accounts).values(
                            id=account_id,
                            customer_id=None,
                            type=kind,
                            number=number,
                            routing=self.routing,
                            currency="USD",
                            status="OPEN",
                        )
                    )

    def open_day(self, prefund_minor: int, ts: str) -> None:
        """Fund the settlement asset and the house liability for ``prefund_minor``."""
        if self.net_credit(SETTLEMENT) != 0:
            return
        self.post(
            "opening",
            ((SETTLEMENT, "debit", prefund_minor), (HOUSE, "credit", prefund_minor)),
            ts=ts,
        )

    def post(self, txn_id: str, legs: Sequence[Leg], *, ts: str) -> None:
        """Insert a balanced set of ledger entries. Rejects an unbalanced txn."""
        postings = [Posting(account_id=a, direction=d, amount_minor=m) for a, d, m in legs]
        if not postings or not is_balanced(postings):
            raise LedgerError(f"transaction {txn_id} is not balanced")
        for account_id, _direction, amount in legs:
            if amount < 0:
                raise LedgerError("amounts must be non-negative")
            if self._account(account_id) is None:
                raise LedgerError(f"unknown account {account_id}")
        with self.engine.begin() as conn:
            conn.execute(
                insert(ledger_entries),
                [
                    {
                        "txn_id": txn_id,
                        "account_id": account_id,
                        "direction": direction,
                        "amount_minor": amount,
                        "ts": ts,
                    }
                    for account_id, direction, amount in legs
                ],
            )

    def net_credit(self, account_id: str) -> int:
        """Credits minus debits. Positive for a liability (customer, house, suspense)."""
        debits, credits = self._sums(account_id)
        return credits - debits

    def settlement_position(self) -> int:
        """Asset position of the settlement GL (debits minus credits)."""
        return -self.net_credit(SETTLEMENT)

    def suspense_balance(self) -> int:
        return self.net_credit(SUSPENSE)

    def hold(self, account_id: str, amount: int, txn_id: str, ts: str) -> None:
        """Move funds from a customer liability into suspense."""
        self.post(
            txn_id,
            ((account_id, "debit", amount), (SUSPENSE, "credit", amount)),
            ts=ts,
        )

    def release_hold(self, account_id: str, amount: int, txn_id: str, ts: str) -> None:
        self.post(
            txn_id,
            ((SUSPENSE, "debit", amount), (account_id, "credit", amount)),
            ts=ts,
        )

    def settle_hold(self, account_id: str, amount: int, txn_id: str, ts: str) -> None:
        """Clear suspense and reduce the settlement asset (funds have left the bank)."""
        del account_id
        self.post(
            txn_id,
            ((SUSPENSE, "debit", amount), (SETTLEMENT, "credit", amount)),
            ts=ts,
        )

    def receive(self, account_id: str, amount: int, txn_id: str, ts: str) -> None:
        """Increase the settlement asset and the customer liability (funds arrived)."""
        self.post(
            txn_id,
            ((SETTLEMENT, "debit", amount), (account_id, "credit", amount)),
            ts=ts,
        )

    def transfer(self, src: str, dst: str, amount: int, txn_id: str, ts: str) -> None:
        """Move a liability balance from ``src`` to ``dst`` (house or customer)."""
        self.post(txn_id, ((src, "debit", amount), (dst, "credit", amount)), ts=ts)

    def invariant_errors(self) -> list[str]:
        """Per-txn balance and the all-entry sum. Empty means the books are consistent."""
        errors: list[str] = []
        grouped: dict[str, list[Posting]] = defaultdict(list)
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(
                    ledger_entries.c.txn_id,
                    ledger_entries.c.account_id,
                    ledger_entries.c.direction,
                    ledger_entries.c.amount_minor,
                )
            ).all()
        for txn_id, account_id, direction, amount in rows:
            grouped[str(txn_id)].append(
                Posting(account_id=str(account_id), direction=direction, amount_minor=int(amount))
            )
        for txn_id, postings in grouped.items():
            if not is_balanced(postings):
                errors.append(f"txn {txn_id} does not sum to zero")
        if self.suspense_balance() < 0:
            errors.append("suspense balance is negative")
        return errors

    def add_customer(
        self, customer_id: str, name: str, email: str, phone: str, risk_tier: str, notes: str
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(customers).values(
                    id=customer_id,
                    name=name,
                    email=email,
                    phone=phone,
                    risk_tier=risk_tier,
                    notes=notes,
                )
            )

    def add_account(
        self, account_id: str, customer_id: str, kind: str, number: str, status: str = "OPEN"
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(accounts).values(
                    id=account_id,
                    customer_id=customer_id,
                    type=kind,
                    number=number,
                    routing=self.routing,
                    currency="USD",
                    status=status,
                )
            )

    def set_account_status(self, account_id: str, status: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(accounts).where(accounts.c.id == account_id).values(status=status))

    def account_by_number(self, number: str) -> Mapping[str, Any] | None:
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(accounts).where(accounts.c.number == number)).mappings().first()
            )
        return dict(row) if row is not None else None

    def account(self, account_id: str) -> Mapping[str, Any] | None:
        return self._account(account_id)

    def accounts_of(self, customer_id: str) -> list[Mapping[str, Any]]:
        with self.engine.connect() as conn:
            rows = (
                conn.execute(select(accounts).where(accounts.c.customer_id == customer_id))
                .mappings()
                .all()
            )
        return [dict(r) for r in rows]

    def customers(self) -> list[Mapping[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(customers).order_by(customers.c.id)).mappings().all()
        return [dict(r) for r in rows]

    def all_accounts(self) -> list[Mapping[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(accounts).order_by(accounts.c.id)).mappings().all()
        return [dict(r) for r in rows]

    def add_transaction(
        self,
        txn_id: str,
        account_id: str,
        amount_minor: int,
        direction: str,
        description: str,
        counterparty_name: str,
        remittance_info: str,
        iso_msg_id: str | None,
        status: str = "BOOK",
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(transactions).values(
                    id=txn_id,
                    account_id=account_id,
                    amount_minor=amount_minor,
                    direction=direction,
                    description=description,
                    counterparty_name=counterparty_name,
                    remittance_info=remittance_info,
                    iso_msg_id=iso_msg_id,
                    status=status,
                )
            )

    def list_transactions(self, account_id: str) -> list[Mapping[str, Any]]:
        with self.engine.connect() as conn:
            rows = (
                conn.execute(select(transactions).where(transactions.c.account_id == account_id))
                .mappings()
                .all()
            )
        return [dict(r) for r in rows]

    def add_payment(self, row: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(payments).values(**row))

    def update_payment_status(self, payment_id: str, status: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(payments).where(payments.c.id == payment_id).values(status=status))

    def payment_by_uetr(self, uetr: str, direction: str | None = None) -> Mapping[str, Any] | None:
        stmt = select(payments).where(payments.c.uetr == uetr)
        if direction is not None:
            stmt = stmt.where(payments.c.direction == direction)
        with self.engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return dict(row) if row is not None else None

    def payment_by_idempotency(self, key: str) -> Mapping[str, Any] | None:
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(payments).where(payments.c.idempotency_key == key))
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def payments_rows(self) -> list[Mapping[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(payments).order_by(payments.c.id)).mappings().all()
        return [dict(r) for r in rows]

    def set_business_date(self, day: str) -> None:
        self._business_date = day

    def _today_stamp(self) -> str:
        return self._business_date

    def outbound_today(self, account_id: str) -> int:
        """Sum of outbound payment amounts that are not rejected, for the daily limit."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(payments.c.amount_minor).where(
                    payments.c.debtor_acct == account_id,
                    payments.c.direction == "out",
                    payments.c.created_on == self._today_stamp(),
                    payments.c.status.in_(("ACSC", "PENDING", "HELD")),
                )
            ).all()
        return sum(int(r[0]) for r in rows)

    def add_payee(self, row: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(payees).values(**row))

    def payees_of(self, customer_id: str) -> list[Mapping[str, Any]]:
        with self.engine.connect() as conn:
            rows = (
                conn.execute(select(payees).where(payees.c.customer_id == customer_id))
                .mappings()
                .all()
            )
        return [dict(r) for r in rows]

    def add_rfp(self, row: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(rfps).values(**row))

    def update_rfp(self, end_to_end_id: str, status: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(rfps).where(rfps.c.end_to_end_id == end_to_end_id).values(status=status)
            )

    def rfp_rows(self, status: str | None = None) -> list[Mapping[str, Any]]:
        stmt = select(rfps)
        if status is not None:
            stmt = stmt.where(rfps.c.status == status)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt.order_by(rfps.c.id)).mappings().all()
        return [dict(r) for r in rows]

    def add_document(
        self, doc_id: str, name: str, body: str, customer_id: str | None = None, hidden: str = ""
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(documents).values(
                    id=doc_id, customer_id=customer_id, name=name, body=body, hidden=hidden
                )
            )

    def documents_named(self, name: str) -> list[Mapping[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(documents).where(documents.c.name == name)).mappings().all()
        return [dict(r) for r in rows]

    def add_kb(self, doc_id: str, title: str, body: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(kb_docs).values(id=doc_id, title=title, body=body))

    def kb_all(self) -> list[Mapping[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(kb_docs).order_by(kb_docs.c.id)).mappings().all()
        return [dict(r) for r in rows]

    def add_consent(self, row: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(consents).values(**row))

    def consents_rows(self) -> list[Mapping[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(consents).order_by(consents.c.id)).mappings().all()
        return [dict(r) for r in rows]

    def consent(self, consent_id: str) -> Mapping[str, Any] | None:
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(consents).where(consents.c.id == consent_id)).mappings().first()
            )
        return dict(row) if row is not None else None

    def update_consent(self, consent_id: str, **values: object) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(consents).where(consents.c.id == consent_id).values(**values))

    def add_case(self, case_id: str, status: str, summary: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(cases).values(id=case_id, status=status, summary=summary))

    def update_case(self, case_id: str, status: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(cases).where(cases.c.id == case_id).values(status=status))

    def add_hitl(self, hitl_id: str, customer_id: str, payload: str, status: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(hitl_requests).values(
                    id=hitl_id, customer_id=customer_id, payload=payload, status=status
                )
            )

    def update_hitl(self, hitl_id: str, status: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(hitl_requests).where(hitl_requests.c.id == hitl_id).values(status=status)
            )

    def audit(self, ts: str, action: str, detail: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(audit_outbox).values(ts=ts, action=action, detail=detail[:4000]))

    def _account(self, account_id: str) -> Mapping[str, Any] | None:
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(accounts).where(accounts.c.id == account_id)).mappings().first()
            )
        return dict(row) if row is not None else None

    def _sums(self, account_id: str) -> tuple[int, int]:
        debit_sum = func.coalesce(
            func.sum(
                case(
                    (ledger_entries.c.direction == "debit", ledger_entries.c.amount_minor),
                    else_=0,
                )
            ),
            0,
        )
        credit_sum = func.coalesce(
            func.sum(
                case(
                    (ledger_entries.c.direction == "credit", ledger_entries.c.amount_minor),
                    else_=0,
                )
            ),
            0,
        )
        stmt = select(debit_sum, credit_sum).where(ledger_entries.c.account_id == account_id)
        with self.engine.connect() as conn:
            debits, credits = _one(conn, stmt)
        return debits, credits


def _one(conn: Connection, stmt: Any) -> tuple[int, int]:
    row = conn.execute(stmt).one()
    return int(row[0]), int(row[1])
