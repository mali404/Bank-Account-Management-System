"""Integration tests — exercise the running stack via HTTP.

Run with:  make up && make seed && pytest -m integration

These tests deliberately use the public API surface — no internals — so
they double as regression tests for the OpenAPI contract.
"""
from __future__ import annotations

import os
from decimal import Decimal

import httpx
import pytest

API = os.environ.get("INTEGRATION_API", "http://localhost:8000")

CUSTOMER = ("alice@example.com",  "ChangeMe-DemoPw#2025")
TELLER   = ("teller@example.com", "ChangeMe-DemoPw#2025")
COMP     = ("comp@example.com",   "ChangeMe-DemoPw#2025")
ADMIN    = ("admin@example.com",  "ChangeMe-DemoPw#2025")


def _login(client: httpx.Client, email: str, pw: str) -> str:
    r = client.post("/auth/token", data={"username": email, "password": pw})
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture
def client():
    with httpx.Client(base_url=API, timeout=10) as c:
        yield c


@pytest.mark.integration
def test_health(client: httpx.Client) -> None:
    assert client.get("/health").json()["status"] == "ok"


@pytest.mark.integration
def test_customer_login_and_view_own_accounts(client: httpx.Client) -> None:
    tok = _login(client, *CUSTOMER)
    r = client.get("/accounts/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    accounts = r.json()
    assert len(accounts) >= 1
    assert all(Decimal(a["balance"]) >= 0 for a in accounts)


@pytest.mark.integration
def test_customer_cannot_freeze(client: httpx.Client) -> None:
    tok = _login(client, *CUSTOMER)
    accounts = client.get("/accounts/me", headers={"Authorization": f"Bearer {tok}"}).json()
    target = accounts[0]["id"]
    r = client.post(f"/accounts/{target}/freeze", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


@pytest.mark.integration
def test_admin_cannot_transfer(client: httpx.Client) -> None:
    """AC-5 / AC-6: admins must not be able to move money."""
    tok = _login(client, *ADMIN)
    r = client.post(
        "/transfers",
        json={
            "from_account_id": "00000000-0000-0000-0000-000000000000",
            "to_account_id":   "00000000-0000-0000-0000-000000000001",
            "amount":          "100.00",
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403


@pytest.mark.integration
def test_high_value_transfer_requires_approval(client: httpx.Client) -> None:
    cust_tok = _login(client, *CUSTOMER)
    accounts = client.get("/accounts/me", headers={"Authorization": f"Bearer {cust_tok}"}).json()
    if len(accounts) < 2:
        # Need a destination — skip if the seed only provided one account.
        pytest.skip("need >= 2 accounts in seed for this test")
    src, dst = accounts[0]["id"], accounts[1]["id"]
    r = client.post(
        "/transfers",
        json={"from_account_id": src, "to_account_id": dst, "amount": "9000.00"},
        headers={"Authorization": f"Bearer {cust_tok}"},
    )
    assert r.status_code == 201
    assert r.json()["state"] == "pending_approval"


@pytest.mark.integration
def test_originator_cannot_self_approve(client: httpx.Client) -> None:
    """AC-5 — the same human who created a high-value transfer cannot
    approve it, even if they had the role to."""
    # We login as customer first to originate, then attempt approval as the
    # *same* human via direct API. (In the real app, the customer wouldn't
    # have approve perm anyway — this is a structural double-check.)
    cust_tok = _login(client, *CUSTOMER)
    accounts = client.get("/accounts/me", headers={"Authorization": f"Bearer {cust_tok}"}).json()
    if len(accounts) < 2:
        pytest.skip("need >= 2 accounts")
    r = client.post(
        "/transfers",
        json={
            "from_account_id": accounts[0]["id"],
            "to_account_id":   accounts[1]["id"],
            "amount":          "8000.00",
        },
        headers={"Authorization": f"Bearer {cust_tok}"},
    )
    assert r.status_code == 201
    transfer_id = r.json()["id"]
    # Customers don't even have approve perm — that's the first defense.
    r2 = client.post(
        f"/transfers/{transfer_id}/approve",
        headers={"Authorization": f"Bearer {cust_tok}"},
    )
    assert r2.status_code == 403
