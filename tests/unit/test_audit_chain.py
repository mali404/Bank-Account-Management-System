"""Unit-level tests for the audit HMAC chain logic.

We test the pure HMAC-computation function rather than DB writes here.
DB-level append-only enforcement is exercised in tests/security/.
"""
from __future__ import annotations

import pytest

from app.observability.audit import _compute_hmac


@pytest.mark.unit
def test_hmac_chain_is_deterministic() -> None:
    payload = {"action": "x", "actor": "y"}
    a = _compute_hmac("PREV", payload)
    b = _compute_hmac("PREV", payload)
    assert a == b


@pytest.mark.unit
def test_hmac_changes_when_payload_changes() -> None:
    p1 = {"action": "x", "actor": "y"}
    p2 = {"action": "x", "actor": "z"}
    assert _compute_hmac("PREV", p1) != _compute_hmac("PREV", p2)


@pytest.mark.unit
def test_hmac_changes_when_prev_changes() -> None:
    p = {"action": "x"}
    assert _compute_hmac("A", p) != _compute_hmac("B", p)
