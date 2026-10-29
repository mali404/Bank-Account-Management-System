"""Two-phase settlement ledger with TigerBeetle pending/post/void semantics.

SimNow settles each inter-bank payment as a pending transfer that is posted on
``ACSC`` and voided on ``RJCT`` or receiver timeout (SPEC §5.3). Account
positions are ``credits_posted - debits_posted``, which is what each bank's
settlement GL mirrors.

The ledger implements TigerBeetle's transfer lifecycle: a pending transfer
debits the sender's pending counter and credits the receiver's pending counter;
post moves those into the posted counters; void drops the pending counters and
leaves posted balances unchanged. The acceptance tests and ``make reset`` run
this in-process so they do not need a TigerBeetle cluster. Positions are the
figures the invariant "TigerBeetle position = bank settlement GL" checks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import SettlementError

__all__ = ["AccountPosition", "SettlementLedger", "Transfer"]


@dataclass
class AccountPosition:
    """Posted and pending debit/credit counters, in USD minor units."""

    credits_posted: int = 0
    debits_posted: int = 0
    credits_pending: int = 0
    debits_pending: int = 0

    @property
    def posted(self) -> int:
        """Net posted position (credits minus debits)."""
        return self.credits_posted - self.debits_posted

    def to_json(self) -> dict[str, int]:
        return {
            "credits_posted": self.credits_posted,
            "debits_posted": self.debits_posted,
            "credits_pending": self.credits_pending,
            "debits_pending": self.debits_pending,
        }

    @classmethod
    def from_json(cls, raw: dict[str, int]) -> AccountPosition:
        return cls(
            credits_posted=int(raw["credits_posted"]),
            debits_posted=int(raw["debits_posted"]),
            credits_pending=int(raw["credits_pending"]),
            debits_pending=int(raw["debits_pending"]),
        )


@dataclass
class Transfer:
    """One settlement transfer. ``state`` is pending, posted or voided."""

    id: str
    debit_account_id: str
    credit_account_id: str
    amount: int
    state: str = "pending"

    def to_json(self) -> dict[str, str | int]:
        return {
            "id": self.id,
            "debit_account_id": self.debit_account_id,
            "credit_account_id": self.credit_account_id,
            "amount": self.amount,
            "state": self.state,
        }


class SettlementLedger:
    """In-process TigerBeetle-semantics settlement ledger."""

    def __init__(self) -> None:
        self.accounts: dict[str, AccountPosition] = {}
        self.transfers: dict[str, Transfer] = {}

    def create_account(self, account_id: str) -> None:
        if account_id not in self.accounts:
            self.accounts[account_id] = AccountPosition()

    def fund(self, account_id: str, amount: int, treasury: str = "treasury") -> None:
        """Post funds from ``treasury`` onto ``account_id`` (prefunding)."""
        if amount < 0:
            raise SettlementError("fund amount must be non-negative")
        self.create_account(treasury)
        self.create_account(account_id)
        if amount == 0:
            return
        self.accounts[treasury].debits_posted += amount
        self.accounts[account_id].credits_posted += amount
        self.transfers[f"fund-{account_id}"] = Transfer(
            id=f"fund-{account_id}",
            debit_account_id=treasury,
            credit_account_id=account_id,
            amount=amount,
            state="posted",
        )

    def position(self, account_id: str) -> int:
        return self.accounts[account_id].posted

    def pending_debit(self, account_id: str) -> int:
        return self.accounts[account_id].debits_pending

    def available(self, account_id: str) -> int:
        acct = self.accounts[account_id]
        return acct.posted - acct.debits_pending

    def pending(self, transfer_id: str, debit: str, credit: str, amount: int) -> None:
        """Create a pending transfer. Raises if the debit account cannot cover it."""
        if amount <= 0:
            raise SettlementError("amount must be positive")
        if transfer_id in self.transfers:
            raise SettlementError(f"transfer {transfer_id} already exists")
        if debit not in self.accounts or credit not in self.accounts:
            raise SettlementError("unknown settlement account")
        if self.available(debit) < amount:
            raise SettlementError("insufficient settlement position")
        self.transfers[transfer_id] = Transfer(transfer_id, debit, credit, amount, "pending")
        self.accounts[debit].debits_pending += amount
        self.accounts[credit].credits_pending += amount

    def post(self, transfer_id: str) -> None:
        """Post a pending transfer (TigerBeetle post-pending)."""
        transfer = self._pending(transfer_id)
        self.accounts[transfer.debit_account_id].debits_pending -= transfer.amount
        self.accounts[transfer.debit_account_id].debits_posted += transfer.amount
        self.accounts[transfer.credit_account_id].credits_pending -= transfer.amount
        self.accounts[transfer.credit_account_id].credits_posted += transfer.amount
        transfer.state = "posted"

    def void(self, transfer_id: str) -> None:
        """Void a pending transfer (TigerBeetle void-pending). Posted balances stay."""
        transfer = self._pending(transfer_id)
        self.accounts[transfer.debit_account_id].debits_pending -= transfer.amount
        self.accounts[transfer.credit_account_id].credits_pending -= transfer.amount
        transfer.state = "voided"

    def positions_sum(self) -> int:
        """Sum of posted positions. A closed ledger (with treasury) sums to zero."""
        return sum(acct.posted for acct in self.accounts.values())

    def to_json(self) -> dict[str, object]:
        return {
            "accounts": {k: v.to_json() for k, v in sorted(self.accounts.items())},
            "transfers": {k: v.to_json() for k, v in sorted(self.transfers.items())},
        }

    def load_json(self, raw: dict[str, object]) -> None:
        accounts = raw["accounts"]
        transfers = raw["transfers"]
        assert isinstance(accounts, dict)
        assert isinstance(transfers, dict)
        self.accounts = {
            str(k): AccountPosition.from_json(v) for k, v in accounts.items() if isinstance(v, dict)
        }
        self.transfers = {}
        for key, value in transfers.items():
            if not isinstance(value, dict):
                continue
            self.transfers[str(key)] = Transfer(
                id=str(value["id"]),
                debit_account_id=str(value["debit_account_id"]),
                credit_account_id=str(value["credit_account_id"]),
                amount=int(value["amount"]),
                state=str(value["state"]),
            )

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), sort_keys=True), encoding="utf-8")

    def load(self, path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        self.load_json(raw)

    def _pending(self, transfer_id: str) -> Transfer:
        try:
            transfer = self.transfers[transfer_id]
        except KeyError as exc:
            raise SettlementError(f"unknown transfer {transfer_id}") from exc
        if transfer.state != "pending":
            raise SettlementError(f"transfer {transfer_id} is {transfer.state}")
        return transfer
