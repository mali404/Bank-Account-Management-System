"""Authentication endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import SessionDep
from app.db.session import get_sessionmaker
from app.models.orm import User
from app.observability.audit import write_event, write_event_standalone
from app.schemas.api import TokenResponse
from app.security.auth import (
    issue_access_token,
    issue_refresh_token,
    needs_rehash,
    verify_password,
)
from app.security.rbac import Role

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    """OAuth2 password flow. Username field carries email."""
    # Use a non-RLS session for login (we don't have a user yet).
    async with get_sessionmaker()() as session:
        async with session.begin():
            user = (
                await session.execute(
                    select(User).where(User.email == form.username)
                )
            ).scalar_one_or_none()

            ip = request.client.host if request.client else None

            if user is None or not verify_password(form.password, user.password_hash):
                await write_event_standalone(
                    actor_user_id=None,
                    actor_role=None,
                    action="auth.login",
                    resource=form.username,
                    outcome="denied",
                    nist_control="IA-2",
                    request_ip=ip,
                    detail={"reason": "invalid_credentials"},
                )
                # Constant-ish error to discourage user enumeration.
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid credentials",
                )

            if not user.is_active:
                await write_event_standalone(
                    actor_user_id=str(user.id),
                    actor_role=user.role,
                    action="auth.login",
                    resource=form.username,
                    outcome="denied",
                    nist_control="AC-2",
                    request_ip=ip,
                    detail={"reason": "user_disabled"},
                )
                raise HTTPException(401, "account disabled")

            # Optional rehash if Argon2 params have improved
            if needs_rehash(user.password_hash):
                from app.security.auth import hash_password

                user.password_hash = hash_password(form.password)

            role = Role(user.role)
            access, access_exp = issue_access_token(user_id=str(user.id), role=role)
            refresh, refresh_exp = issue_refresh_token(user_id=str(user.id))

            await write_event(
                session,
                actor_user_id=str(user.id),
                actor_role=user.role,
                action="auth.login",
                resource=form.username,
                outcome="success",
                nist_control="IA-2",
                request_ip=ip,
            )

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
    )
