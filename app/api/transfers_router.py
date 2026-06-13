"""Transfer endpoints — the core money-movement surface.

Implements:
  * AC-5 separation of duties (originator != approver)
  * High-value threshold gating (configurable)
  * Atomic settlement via a single transaction with row locking
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import (
    CurrentUserDep,
    SessionDep,
    require_permission,
    set_system_rls_context,
)
from app.core.settings import get_settings
from app.models.orm import Account, Transaction
from app.observability.audit import write_event, write_event_standalone
from app.schemas.api import TransferCreate, TransferOut
from app.security.rbac import Permission, Role

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post(
    "",
    response_model=TransferOut,
    status_code=201,
    dependencies=[Depends(require_permission(Permission.TRANSFER_LOW_VALUE))],
)
async def create_transfer(
    body: TransferCreate,
    user: CurrentUserDep,
    session: SessionDep,
) -> Transaction:
    settings = get_settings()

    if body.from_account_id == body.to_account_id:
        raise HTTPException(400, "cannot transfer to the same account")

    # Phase 1 — authorization under the CALLER's RLS context.
    # For customers, RLS makes only their own accounts visible, so a
    # successful read here *is* the ownership proof for the debit leg.
    # The destination is deliberately NOT read here: callers have no right
    # to see the payee's ledger row.
    src_visible = (
        await session.execute(select(Account.id).where(Account.id == body.from_account_id))
    ).scalar_one_or_none()
    if src_visible is None:
        raise HTTPException(404, "source account not found")

    # Phase 2 — settlement under the internal system context (the caller
    # has been authorized; the credit leg requires touching a row the
    # caller legitimately cannot see). Lock in deterministic order.
    await set_system_rls_context(session)

    a_id, b_id = sorted([body.from_account_id, body.to_account_id])
    a = (
        await session.execute(
            select(Account).where(Account.id == a_id).with_for_update()
        )
    ).scalar_one_or_none()
    b = (
        await session.execute(
            select(Account).where(Account.id == b_id).with_for_update()
        )
    ).scalar_one_or_none()
    if a is None or b is None:
        raise HTTPException(404, "account not found")

    # Re-resolve to from/to.
    src = a if a.id == body.from_account_id else b
    dst = b if a.id == body.from_account_id else a

    if src.is_frozen or dst.is_frozen:
        raise HTTPException(409, "one or both accounts are frozen")
    if src.balance < body.amount:
        raise HTTPException(409, "insufficient funds")

    high_value = body.amount > settings.high_value_threshold

    if high_value:
        # Create a pending_approval transaction. No funds move yet.
        tx = Transaction(
            id=uuid4(),
            from_account_id=src.id,
            to_account_id=dst.id,
            amount=body.amount,
            memo=body.memo,
            state="pending_approval",
            originator_user_id=UUID(user.user_id),
        )
        session.add(tx)
        await session.flush()
        await write_event(
            session,
            actor_user_id=user.user_id,
            actor_role=user.role.value,
            action="transfer.create",
            resource=str(tx.id),
            outcome="pending_approval",
            nist_control="AC-5",
            detail={
                "amount": str(body.amount),
                "from": str(src.id),
                "to": str(dst.id),
                "high_value": True,
            },
            request_ip=user.request_ip,
        )
        return tx

    # Low-value path: settle atomically.
    src.balance = (src.balance - body.amount).quantize(Decimal("0.01"))
    dst.balance = (dst.balance + body.amount).quantize(Decimal("0.01"))
    tx = Transaction(
        id=uuid4(),
        from_account_id=src.id,
        to_account_id=dst.id,
        amount=body.amount,
        memo=body.memo,
        state="settled",
        originator_user_id=UUID(user.user_id),
        settled_at=datetime.now(UTC),
    )
    session.add(tx)
    await session.flush()

    await write_event(
        session,
        actor_user_id=user.user_id,
        actor_role=user.role.value,
        action="transfer.settle",
        resource=str(tx.id),
        outcome="success",
        nist_control="AC-3",
        detail={
            "amount": str(body.amount),
            "from": str(src.id),
            "to": str(dst.id),
            "high_value": False,
        },
        request_ip=user.request_ip,
    )
    return tx


@router.post(
    "/{transfer_id}/approve",
    response_model=TransferOut,
    dependencies=[Depends(require_permission(Permission.APPROVE_HIGH_VALUE))],
)
async def approve_transfer(
    transfer_id: UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> Transaction:
    tx = (
        await session.execute(
            select(Transaction).where(Transaction.id == transfer_id).with_for_update()
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(404, "transfer not found")
    if tx.state != "pending_approval":
        raise HTTPException(409, f"cannot approve in state {tx.state}")

    # AC-5: separation of duties — originator cannot self-approve.
    if str(tx.originator_user_id) == user.user_id:
        await write_event_standalone(
            actor_user_id=user.user_id,
            actor_role=user.role.value,
            action="transfer.approve",
            resource=str(tx.id),
            outcome="denied",
            nist_control="AC-5",
            detail={"reason": "self_approval_blocked"},
            request_ip=user.request_ip,
        )
        raise HTTPException(403, "originator cannot approve own transfer")

    # Lock and settle.
    src = (
        await session.execute(
            select(Account).where(Account.id == tx.from_account_id).with_for_update()
        )
    ).scalar_one()
    dst = (
        await session.execute(
            select(Account).where(Account.id == tx.to_account_id).with_for_update()
        )
    ).scalar_one()

    if src.is_frozen or dst.is_frozen:
        raise HTTPException(409, "account frozen since pending")
    if src.balance < tx.amount:
        # Funds moved between pending and approval. Reject — and the
        # rejection must persist even though we raise: do it in its own
        # committed transaction (the request transaction rolls back).
        from sqlalchemy import update as sa_update

        from app.db.session import get_sessionmaker

        async with get_sessionmaker()() as reject_session:
            async with reject_session.begin():
                await reject_session.execute(
                    sa_update(Transaction)
                    .where(Transaction.id == tx.id)
                    .values(state="rejected")
                )
                await write_event(
                    reject_session,
                    actor_user_id=user.user_id,
                    actor_role=user.role.value,
                    action="transfer.approve",
                    resource=str(tx.id),
                    outcome="denied",
                    nist_control="AC-3",
                    detail={"reason": "insufficient_funds_at_approval"},
                    request_ip=user.request_ip,
                )
        raise HTTPException(409, "insufficient funds at approval time")

    src.balance = (src.balance - tx.amount).quantize(Decimal("0.01"))
    dst.balance = (dst.balance + tx.amount).quantize(Decimal("0.01"))
    tx.state = "settled"
    tx.approver_user_id = UUID(user.user_id)
    tx.settled_at = datetime.now(UTC)

    await write_event(
        session,
        actor_user_id=user.user_id,
        actor_role=user.role.value,
        action="transfer.approve",
        resource=str(tx.id),
        outcome="success",
        nist_control="AC-5",
        detail={
            "originator": str(tx.originator_user_id),
            "amount": str(tx.amount),
        },
        request_ip=user.request_ip,
    )
    return tx
