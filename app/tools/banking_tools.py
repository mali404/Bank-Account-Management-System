"""Agent tools.

Each tool calls the FastAPI backend over loopback so authorization,
RLS context, and audit logging fire identically whether invoked by a
human via curl or by an agent via the supervisor. The token used is the
same JWT the human presented — agents do not get a separate identity.
"""
from __future__ import annotations

from contextvars import ContextVar
from decimal import Decimal
from typing import Any

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel

from app.core.settings import get_settings

# The supervisor sets this before invoking the role-agent. Tools read it
# to acquire the user's JWT for the loopback HTTP call.
current_jwt: ContextVar[str] = ContextVar("current_jwt", default="")


def _client() -> httpx.Client:
    s = get_settings()
    headers = {}
    token = current_jwt.get()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=s.internal_api_base, headers=headers, timeout=10.0)


class ToolResult(BaseModel):
    ok: bool
    data: Any = None
    error: str | None = None


@tool
def view_my_accounts() -> ToolResult:
    """List the calling user's accounts. RLS guarantees same-user scope."""
    with _client() as c:
        r = c.get("/accounts/me")
    if r.is_success:
        return ToolResult(ok=True, data=r.json())
    return ToolResult(ok=False, error=f"{r.status_code}: {r.text}")


@tool
def view_account(account_id: str) -> ToolResult:
    """Fetch a specific account by id. Authorization enforced by RLS + RBAC."""
    with _client() as c:
        r = c.get(f"/accounts/{account_id}")
    if r.is_success:
        return ToolResult(ok=True, data=r.json())
    return ToolResult(ok=False, error=f"{r.status_code}: {r.text}")


@tool
def transfer_funds(
    from_account_id: str,
    to_account_id: str,
    amount: float,
    memo: str = "",
) -> ToolResult:
    """Transfer funds. May return a pending_approval state for high-value transfers."""
    with _client() as c:
        r = c.post(
            "/transfers",
            json={
                "from_account_id": from_account_id,
                "to_account_id": to_account_id,
                "amount": str(Decimal(str(amount)).quantize(Decimal("0.01"))),
                "memo": memo,
            },
        )
    if r.is_success:
        return ToolResult(ok=True, data=r.json())
    return ToolResult(ok=False, error=f"{r.status_code}: {r.text}")


@tool
def open_account(customer_id: str, account_type: str, initial_deposit: float = 0) -> ToolResult:
    """Open a new account (teller-only)."""
    with _client() as c:
        r = c.post(
            "/accounts",
            json={
                "customer_id": customer_id,
                "account_type": account_type,
                "initial_deposit": str(Decimal(str(initial_deposit)).quantize(Decimal("0.01"))),
            },
        )
    if r.is_success:
        return ToolResult(ok=True, data=r.json())
    return ToolResult(ok=False, error=f"{r.status_code}: {r.text}")


@tool
def freeze_account(account_id: str) -> ToolResult:
    """Freeze an account (compliance-only)."""
    with _client() as c:
        r = c.post(f"/accounts/{account_id}/freeze")
    if r.is_success:
        return ToolResult(ok=True, data=r.json())
    return ToolResult(ok=False, error=f"{r.status_code}: {r.text}")


@tool
def approve_high_value_transfer(transfer_id: str) -> ToolResult:
    """Approve a pending high-value transfer. Subject to AC-5."""
    with _client() as c:
        r = c.post(f"/transfers/{transfer_id}/approve")
    if r.is_success:
        return ToolResult(ok=True, data=r.json())
    return ToolResult(ok=False, error=f"{r.status_code}: {r.text}")


# Tool sets per role — single source of truth for the agent layer.
TOOLS_BY_ROLE = {
    "customer":           [view_my_accounts, transfer_funds],
    "teller":             [view_my_accounts, view_account, transfer_funds, open_account],
    "loan_officer":       [view_account],   # extend with originate_loan when you implement it
    "compliance_officer": [view_account, freeze_account, approve_high_value_transfer],
    "admin":              [],               # admins use direct API endpoints; deliberately narrow agent surface
}
