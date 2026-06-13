"""TPP authentication.

A TPP token is structurally similar to a user token but carries:
  - `actor`: "tpp"
  - `client_id`: the TPP's OAuth client_id
  - `consent_id`: the bound consent (issued AFTER consent authorisation)
  - `aud`: the TPP client_id (FAPI requirement)

OBIE-GAP: production OBIE issues these via OIDC + FAPI flows with
mTLS-bound tokens. We issue them via a simulated client-credentials +
intent-binding flow at /open-banking/oauth/token.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, Header, Request
from jose import JWTError, jwt

from app.core.settings import get_settings
from app.db.session import get_sessionmaker
from app.openbanking.consent_service import _obie_error, load_tpp_or_403
from app.openbanking.orm import ThirdPartyProvider
from app.security.auth import _load_keys



def issue_tpp_token(
    *, tpp_client_id: str, consent_id: str | None, scopes: list[str], ttl_minutes: int = 30
) -> tuple[str, datetime]:
    """Mint a TPP-bound access token. If `consent_id` is set, the token
    is intent-bound."""
    settings = get_settings()
    private, _ = _load_keys()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=ttl_minutes)
    payload: dict[str, Any] = {
        "iss": "agentic-bank",
        "sub": tpp_client_id,
        "aud": tpp_client_id,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(uuid4()),
        "typ": "access",
        "actor": "tpp",
        "client_id": tpp_client_id,
        "scope": " ".join(scopes),
    }
    if consent_id:
        payload["consent_id"] = consent_id
        # OBIE FAPI requires the intent id in the id_token; we embed it
        # in the access token too for stateless server-side enforcement.
        payload["openbanking_intent_id"] = consent_id
    token = jwt.encode(payload, private, algorithm=settings.jwt_algorithm)
    return token, expires


async def verify_tpp_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    _, public = _load_keys()
    try:
        # Disable audience validation here — FastAPI dependency does the
        # narrower client_id check after parsing.
        claims = jwt.decode(
            token,
            public,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise _obie_error("UK.OBIE.Unauthorized", 401, f"invalid token: {exc}") from exc
    if claims.get("actor") != "tpp" or claims.get("typ") != "access":
        raise _obie_error("UK.OBIE.Unauthorized", 401, "not a TPP access token")
    return claims


class TPPCaller:
    """The authenticated TPP for the current request."""

    __slots__ = ("tpp", "consent_id", "scopes", "request_ip")

    def __init__(
        self,
        tpp: ThirdPartyProvider,
        consent_id: str | None,
        scopes: list[str],
        request_ip: str | None,
    ) -> None:
        self.tpp = tpp
        self.consent_id = consent_id
        self.scopes = scopes
        self.request_ip = request_ip


async def get_tpp_caller(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> TPPCaller:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _obie_error("UK.OBIE.Unauthorized", 401, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    claims = await verify_tpp_token(token)

    async with get_sessionmaker()() as session:
        async with session.begin():
            tpp = await load_tpp_or_403(session, client_id=claims["client_id"])

    ip = request.client.host if request.client else None
    return TPPCaller(
        tpp=tpp,
        consent_id=claims.get("consent_id"),
        scopes=claims.get("scope", "").split(),
        request_ip=ip,
    )


TPPCallerDep = Annotated[TPPCaller, Depends(get_tpp_caller)]
