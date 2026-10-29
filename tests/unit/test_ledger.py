"""Tests for the double-entry balance helper."""

from __future__ import annotations

import pytest

from agentbank_ledger import Posting, is_balanced, net_by_account


def test_balanced_transaction() -> None:
    postings = [
        Posting(account_id="a", direction="debit", amount_minor=1000),
        Posting(account_id="b", direction="credit", amount_minor=1000),
    ]
    assert is_balanced(postings)


def test_unbalanced_transaction() -> None:
    postings = [
        Posting(account_id="a", direction="debit", amount_minor=1000),
        Posting(account_id="b", direction="credit", amount_minor=900),
    ]
    assert not is_balanced(postings)


def test_net_by_account() -> None:
    postings = [
        Posting(account_id="a", direction="debit", amount_minor=1500),
        Posting(account_id="b", direction="credit", amount_minor=500),
        Posting(account_id="c", direction="credit", amount_minor=1000),
    ]
    assert net_by_account(postings) == {"a": -1500, "b": 500, "c": 1000}


def test_negative_amount_rejected() -> None:
    with pytest.raises(ValueError):
        Posting(account_id="a", direction="debit", amount_minor=-1).signed_minor()
