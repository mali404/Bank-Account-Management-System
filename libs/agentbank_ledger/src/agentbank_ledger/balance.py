"""Pure-Python double-entry balance check (SPEC §5.1 ledger invariant).

Each transaction's postings must net to zero (debits negative, credits
positive, in integer USD minor units). This invariant is tested per transaction
in the bank core.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

__all__ = ["Posting", "is_balanced", "net_by_account"]

Direction = Literal["debit", "credit"]


@dataclass(frozen=True, slots=True)
class Posting:
    """One leg of a double-entry transaction, in USD minor units."""

    account_id: str
    direction: Direction
    amount_minor: int

    def signed_minor(self) -> int:
        """Return the amount signed by direction (debits negative)."""
        if self.amount_minor < 0:
            raise ValueError("posting amount must be non-negative")
        return -self.amount_minor if self.direction == "debit" else self.amount_minor


def is_balanced(postings: Iterable[Posting]) -> bool:
    """Return ``True`` iff the signed postings sum to zero."""
    total = sum(p.signed_minor() for p in postings)
    return total == 0


def net_by_account(postings: Iterable[Posting]) -> dict[str, int]:
    """Return the net signed minor-unit movement per account."""
    net: dict[str, int] = defaultdict(int)
    for posting in postings:
        net[posting.account_id] += posting.signed_minor()
    return dict(net)
