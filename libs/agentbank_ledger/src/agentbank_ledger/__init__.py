"""Bank books, the SimNow switch, and settlement.

M0 shipped the pure-Python double-entry balance check. M2 adds the bank
ledger, the in-process switch, and a settlement ledger that follows
TigerBeetle's pending / post / void lifecycle. The public names below stay
stable for the balance tests; the rest of the package is imported by module.
"""

from __future__ import annotations

from .balance import Posting, is_balanced, net_by_account

__version__ = "0.1.0"

__all__ = ["Posting", "is_balanced", "net_by_account"]
