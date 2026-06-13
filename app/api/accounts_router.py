"""Account-related endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep, require_permission
from app.models.orm import Account, Customer
from app.observability.audit import write_event
from app.schemas.api import AccountCreate, AccountOut
from app.security.rbac import Permission

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/me", response_model=list[AccountOut])
async def list_my_accounts(
    user: CurrentUserDep,
    session: SessionDep,
) -> list[Account]:
    """Customer-facing: list accounts for the calling user.

    RLS guarantees customer can only see their own; staff roles see all
    in this listing. We additionally constrain to the caller's customer row.
    """
    customer = (
        await session.execute(select(Customer).where(Customer.user_id == UUID(user.user_id)))
    ).scalar_one_or_none()
    if customer is None:
        return []
    return list(
        (
            await session.execute(
                select(Account).where(Account.customer_id == customer.id).order_by(Account.created_at)
            )
        )
        .scalars()
        .all()
    )


@router.get("/{account_id}", response_model=AccountOut)
async def get_account(
    account_id: UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> Account:
    """Fetch a specific account. RLS handles authorization at row level."""
    acc = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if acc is None:
        # Could be 403 (RLS hid it) or 404 — surfaced as 404 to avoid
        # leaking existence to unauthorized callers.
        raise HTTPException(404, "account not found")
    return acc


@router.post(
    "",
    response_model=AccountOut,
    status_code=201,
    dependencies=[Depends(require_permission(Permission.OPEN_ACCOUNT))],
)
async def open_account(
    body: AccountCreate,
    user: CurrentUserDep,
    session: SessionDep,
) -> Account:
    import secrets

    acc = Account(
        customer_id=body.customer_id,
        account_number=str(secrets.randbelow(10**12)).zfill(12),
        account_type=body.account_type,
        balance=body.initial_deposit,
    )
    session.add(acc)
    await session.flush()

    await write_event(
        session,
        actor_user_id=user.user_id,
        actor_role=user.role.value,
        action="account.open",
        resource=str(acc.id),
        outcome="success",
        nist_control="AC-3",
        detail={
            "customer_id": str(body.customer_id),
            "account_type": body.account_type,
            "initial_deposit": str(body.initial_deposit),
        },
        request_ip=user.request_ip,
    )
    return acc


@router.post(
    "/{account_id}/freeze",
    dependencies=[Depends(require_permission(Permission.FREEZE_ACCOUNT))],
)
async def freeze_account(
    account_id: UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    acc = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if acc is None:
        raise HTTPException(404, "account not found")
    acc.is_frozen = True
    await write_event(
        session,
        actor_user_id=user.user_id,
        actor_role=user.role.value,
        action="account.freeze",
        resource=str(acc.id),
        outcome="success",
        nist_control="AC-3",
        request_ip=user.request_ip,
    )
    return {"status": "frozen", "account_id": str(acc.id)}
