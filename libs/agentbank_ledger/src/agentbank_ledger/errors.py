"""Errors raised by the bank ledgers and the settlement ledger."""

from __future__ import annotations


class LedgerError(Exception):
    """A bank-ledger operation could not be posted."""


class SettlementError(Exception):
    """A two-phase settlement transfer could not be created, posted or voided."""
