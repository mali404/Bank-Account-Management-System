"""Role definitions and the central policy matrix.

The matrix is the source of truth — both the agent layer (for tool exposure)
and the API layer (for endpoint guards) consult it. Defense in depth: even
if one layer is bypassed, the other still enforces.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Final


class Role(StrEnum):
    CUSTOMER = "customer"
    TELLER = "teller"
    LOAN_OFFICER = "loan_officer"
    COMPLIANCE_OFFICER = "compliance_officer"
    ADMIN = "admin"


class Permission(StrEnum):
    # Read
    VIEW_OWN_ACCOUNTS = "view_own_accounts"
    VIEW_ANY_ACCOUNT = "view_any_account"
    VIEW_TRANSACTIONS = "view_transactions"
    VIEW_AUDIT = "view_audit"

    # Write — accounts
    OPEN_ACCOUNT = "open_account"
    CLOSE_ACCOUNT = "close_account"
    FREEZE_ACCOUNT = "freeze_account"
    UNFREEZE_ACCOUNT = "unfreeze_account"

    # Write — money movement
    TRANSFER_LOW_VALUE = "transfer_low_value"   # ≤ HIGH_VALUE_THRESHOLD
    APPROVE_HIGH_VALUE = "approve_high_value"

    # Lending
    ORIGINATE_LOAN = "originate_loan"

    # Admin
    MANAGE_ROLES = "manage_roles"
    ROTATE_KEYS = "rotate_keys"


# Central policy matrix. Edit this and only this to change RBAC.
POLICY_MATRIX: Final[dict[Role, frozenset[Permission]]] = {
    Role.CUSTOMER: frozenset({
        Permission.VIEW_OWN_ACCOUNTS,
        Permission.VIEW_TRANSACTIONS,
        Permission.TRANSFER_LOW_VALUE,
    }),
    Role.TELLER: frozenset({
        Permission.VIEW_OWN_ACCOUNTS,
        Permission.VIEW_ANY_ACCOUNT,
        Permission.VIEW_TRANSACTIONS,
        Permission.OPEN_ACCOUNT,
        Permission.TRANSFER_LOW_VALUE,
    }),
    Role.LOAN_OFFICER: frozenset({
        Permission.VIEW_ANY_ACCOUNT,
        Permission.VIEW_TRANSACTIONS,
        Permission.ORIGINATE_LOAN,
    }),
    Role.COMPLIANCE_OFFICER: frozenset({
        Permission.VIEW_ANY_ACCOUNT,
        Permission.VIEW_TRANSACTIONS,
        Permission.VIEW_AUDIT,
        Permission.FREEZE_ACCOUNT,
        Permission.UNFREEZE_ACCOUNT,
        Permission.APPROVE_HIGH_VALUE,
    }),
    Role.ADMIN: frozenset({
        Permission.VIEW_AUDIT,
        Permission.MANAGE_ROLES,
        Permission.ROTATE_KEYS,
        # Note: admin deliberately does NOT have transfer/approve perms.
        # Separation of duties — admins do not move money.
    }),
}


def has_permission(role: Role, permission: Permission) -> bool:
    """Pure check against the policy matrix."""
    return permission in POLICY_MATRIX.get(role, frozenset())
