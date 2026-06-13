"""Security-focused tests.

These tests encode banking invariants as explicit assertions. They live
in tests/security/ so a security reviewer can find them quickly.
"""
from __future__ import annotations

import pytest

from app.security.rbac import POLICY_MATRIX, Permission, Role


@pytest.mark.security
def test_separation_of_duties_pillar_admin_no_money() -> None:
    """AC-5: admins must not have any money-movement permission."""
    money_perms = {
        Permission.TRANSFER_LOW_VALUE,
        Permission.APPROVE_HIGH_VALUE,
        Permission.ORIGINATE_LOAN,
    }
    assert not (POLICY_MATRIX[Role.ADMIN] & money_perms)


@pytest.mark.security
def test_least_privilege_no_role_has_everything() -> None:
    """No single role should hold every permission."""
    all_perms = set(Permission)
    for role, perms in POLICY_MATRIX.items():
        assert perms != all_perms, f"role {role} holds all permissions — violates AC-6"


@pytest.mark.security
def test_only_one_role_can_freeze_accounts() -> None:
    freezers = {r for r, p in POLICY_MATRIX.items() if Permission.FREEZE_ACCOUNT in p}
    assert freezers == {Role.COMPLIANCE_OFFICER}


@pytest.mark.security
def test_only_one_role_can_originate_loans() -> None:
    originators = {r for r, p in POLICY_MATRIX.items() if Permission.ORIGINATE_LOAN in p}
    assert originators == {Role.LOAN_OFFICER}


@pytest.mark.security
def test_only_one_role_can_manage_roles() -> None:
    managers = {r for r, p in POLICY_MATRIX.items() if Permission.MANAGE_ROLES in p}
    assert managers == {Role.ADMIN}
