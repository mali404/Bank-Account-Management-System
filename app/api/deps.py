"""FastAPI dependencies."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.security.auth import TokenError, verify_token
from app.security.rbac import Permission, Role, has_permission

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


class CurrentUser:
    __slots__ = ("user_id", "role", "request_ip")

    def __init__(self, user_id: str, role: Role, request_ip: str | None) -> None:
        self.user_id = user_id
        self.role = role
        self.request_ip = request_ip


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> CurrentUser:
    try:
        claims = verify_token(token, expected_type="access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    try:
        role = Role(claims["role"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(401, "malformed token") from exc
    ip = request.client.host if request.client else None
    return CurrentUser(user_id=claims["sub"], role=role, request_ip=ip)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_session_with_rls(
    user: CurrentUserDep,
) -> AsyncIterator[AsyncSession]:
    """Yields a session with `app.user_id` and `app.role` set so RLS filters."""
    async with get_sessionmaker()() as session:
        # SET LOCAL only persists for the current transaction; we begin one.
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.user_id', :uid, true), "
                     "       set_config('app.role',    :role, true)"),
                {"uid": user.user_id, "role": user.role.value},
            )
            yield session


SessionDep = Annotated[AsyncSession, Depends(get_session_with_rls)]


def require_permission(permission: Permission):
    """Returns a dependency that 403s if the current user lacks the permission."""

    async def _dep(user: CurrentUserDep) -> CurrentUser:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role {user.role.value} lacks {permission.value}",
            )
        return user

    return _dep


def require_any_role(*roles: Role):
    """Returns a dependency that 403s if the current user is not in the role set."""

    role_set = frozenset(roles)

    async def _dep(user: CurrentUserDep) -> CurrentUser:
        if user.role not in role_set:
            raise HTTPException(403, f"role {user.role.value} not allowed")
        return user

    return _dep


async def get_plain_session() -> AsyncIterator[AsyncSession]:
    """Session WITHOUT user authentication and WITHOUT RLS context.

    For endpoints whose caller is not a logged-in user: the TPP token
    endpoint (Basic auth) and OBIE consent/resource endpoints (TPP bearer
    tokens, which carry no user role). RLS still applies — queries against
    RLS-protected tables will return nothing until the endpoint explicitly
    sets a PSU context via `set_psu_rls_context` after consent validation.
    """
    async with get_sessionmaker()() as session:
        async with session.begin():
            yield session


PlainSessionDep = Annotated[AsyncSession, Depends(get_plain_session)]


async def set_psu_rls_context(session: AsyncSession, psu_user_id: object) -> None:
    """Adopt the PSU's identity for RLS purposes.

    A TPP acts *on behalf of* the customer who authorised the consent, so
    the natural RLS context is that customer's own: row visibility is then
    bounded by the PSU's ownership exactly as if the customer queried
    directly. Consent scoping (account_ids, permissions) is enforced
    separately by the consent service — two independent layers.
    """
    await session.execute(
        text(
            "SELECT set_config('app.user_id', :uid, true), "
            "       set_config('app.role',    'customer', true)"
        ),
        {"uid": str(psu_user_id)},
    )


async def set_system_rls_context(session: AsyncSession) -> None:
    """Escalate the session to the internal settlement context.

    Used ONLY after all application-level authorization has passed, for
    operations that must touch rows the caller legitimately cannot see —
    canonically: crediting the payee's account in a transfer. Mirrors how
    a core-banking settlement engine operates on ledgers the *initiating*
    customer has no read access to. RLS policies grant the 'system' role
    the same row visibility as staff roles.
    """
    await session.execute(
        text("SELECT set_config('app.role', 'system', true)")
    )
