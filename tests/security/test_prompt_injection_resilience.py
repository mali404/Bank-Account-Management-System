"""Tests for prompt-injection resilience properties.

These do not require an LLM to run — they verify the *structural* defenses
that make injection ineffective:
  1. Role is server-derived, never agent-supplied.
  2. Tools are typed; tool selection at the agent layer cannot expand the
     set assigned by TOOLS_BY_ROLE.
  3. The trust boundary at the API layer re-checks RBAC.
"""
from __future__ import annotations

import pytest

from app.security.rbac import Permission, Role, has_permission
from app.tools.banking_tools import TOOLS_BY_ROLE


@pytest.mark.security
def test_tools_by_role_align_with_policy_matrix() -> None:
    """If the policy matrix says role X cannot do action Y, then no tool that
    performs Y should be in TOOLS_BY_ROLE[X]."""
    # Map tool names to the permissions they require.
    TOOL_PERMS = {
        "view_my_accounts": Permission.VIEW_OWN_ACCOUNTS,
        "view_account": Permission.VIEW_ANY_ACCOUNT,
        "transfer_funds": Permission.TRANSFER_LOW_VALUE,
        "open_account": Permission.OPEN_ACCOUNT,
        "freeze_account": Permission.FREEZE_ACCOUNT,
        "approve_high_value_transfer": Permission.APPROVE_HIGH_VALUE,
    }
    for role_str, tool_objs in TOOLS_BY_ROLE.items():
        role = Role(role_str)
        for tool_obj in tool_objs:
            tool_name = getattr(tool_obj, "name", str(tool_obj))
            required = TOOL_PERMS.get(tool_name)
            if required is None:
                continue
            assert has_permission(role, required), (
                f"role {role} has agent tool {tool_name} but lacks permission {required}"
            )


@pytest.mark.security
def test_admin_has_no_money_tools() -> None:
    """Admin agent surface must not include any money-moving tool."""
    money_tool_names = {"transfer_funds", "approve_high_value_transfer", "originate_loan"}
    admin_tools = TOOLS_BY_ROLE["admin"]
    admin_tool_names = {getattr(t, "name", str(t)) for t in admin_tools}
    assert not (admin_tool_names & money_tool_names)


@pytest.mark.security
def test_customer_has_no_freeze_or_approve() -> None:
    cust_tools = TOOLS_BY_ROLE["customer"]
    names = {getattr(t, "name", str(t)) for t in cust_tools}
    assert "freeze_account" not in names
    assert "approve_high_value_transfer" not in names
    assert "open_account" not in names
