"""Unit tests for the RBAC policy matrix.

These are simple but valuable: they're the canary for any accidental
permission grant. If a future change accidentally gives admins the
APPROVE_HIGH_VALUE permission, this file fails immediately.
"""
from __future__ import annotations

import pytest

from app.security.rbac import POLICY_MATRIX, Permission, Role, has_permission


@pytest.mark.unit
def test_every_role_present_in_matrix() -> None:
    for role in Role:
        assert role in POLICY_MATRIX, f"role {role} missing from POLICY_MATRIX"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("role", "permission", "expected"),
    [
        (Role.CUSTOMER, Permission.TRANSFER_LOW_VALUE, True),
        (Role.CUSTOMER, Permission.APPROVE_HIGH_VALUE, False),
        (Role.CUSTOMER, Permission.FREEZE_ACCOUNT, False),
        (Role.TELLER, Permission.OPEN_ACCOUNT, True),
        (Role.TELLER, Permission.APPROVE_HIGH_VALUE, False),
        (Role.LOAN_OFFICER, Permission.ORIGINATE_LOAN, True),
        (Role.LOAN_OFFICER, Permission.TRANSFER_LOW_VALUE, False),
        (Role.COMPLIANCE_OFFICER, Permission.FREEZE_ACCOUNT, True),
        (Role.COMPLIANCE_OFFICER, Permission.APPROVE_HIGH_VALUE, True),
        (Role.COMPLIANCE_OFFICER, Permission.TRANSFER_LOW_VALUE, False),
        (Role.ADMIN, Permission.MANAGE_ROLES, True),
        # Critical: admin must NOT move money or approve transfers.
        (Role.ADMIN, Permission.TRANSFER_LOW_VALUE, False),
        (Role.ADMIN, Permission.APPROVE_HIGH_VALUE, False),
    ],
)
def test_policy_matrix(role: Role, permission: Permission, expected: bool) -> None:
    assert has_permission(role, permission) is expected


@pytest.mark.unit
def test_admin_does_not_move_money() -> None:
    """Pillar property: admins administer, they don't transact.
    Encoded as a separate test so the failure message is unambiguous."""
    forbidden_for_admin = {
        Permission.TRANSFER_LOW_VALUE,
        Permission.APPROVE_HIGH_VALUE,
        Permission.ORIGINATE_LOAN,
    }
    admin_perms = POLICY_MATRIX[Role.ADMIN]
    intersection = admin_perms & forbidden_for_admin
    assert intersection == set(), f"admin has forbidden perms: {intersection}"


@pytest.mark.unit
def test_only_compliance_can_approve_high_value() -> None:
    approvers = {r for r in Role if has_permission(r, Permission.APPROVE_HIGH_VALUE)}
    assert approvers == {Role.COMPLIANCE_OFFICER}
