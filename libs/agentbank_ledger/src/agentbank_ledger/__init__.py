"""Double-entry ledger helpers and (later) a TigerBeetle settlement wrapper.

Milestone M2 fills this package with the bank-core ledger helpers and the
TigerBeetle settlement wrapper. M0 ships a pure-Python double-entry balance
check used by the ledger invariant tests.
"""

from __future__ import annotations

from .balance import Posting, is_balanced, net_by_account

__version__ = "0.1.0"

__all__ = ["Posting", "is_balanced", "net_by_account"]
