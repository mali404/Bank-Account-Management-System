"""Authentication primitives: Argon2id password hashing + JWT (RS256) issuance."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.settings import get_settings
from app.security.rbac import Role

# Argon2id parameters — OWASP-recommended baseline (2024+).
# memory_cost in KiB; 47 MiB. Tune up on faster hardware.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=47104,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(plaintext: str) -> str:
    return _hasher.hash(plaintext)


def verify_password(plaintext: str, stored_hash: str) -> bool:
    try:
        _hasher.verify(stored_hash, plaintext)
    except VerifyMismatchError:
        return False
    return True


def needs_rehash(stored_hash: str) -> bool:
    """Returns True if the hash was generated with weaker parameters
    than current. Call after a successful verify and rehash if so."""
    return _hasher.check_needs_rehash(stored_hash)


# --- JWT ---


class TokenError(Exception):
    """Raised on any JWT validation failure."""


def _load_keys() -> tuple[str, str]:
    s = get_settings()
    return (
        s.jwt_private_key_path.read_text(),
        s.jwt_public_key_path.read_text(),
    )


def issue_access_token(*, user_id: str, role: Role) -> tuple[str, datetime]:
    s = get_settings()
    private, _ = _load_keys()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=s.jwt_access_ttl_minutes)
    payload = {
        "sub": user_id,
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(uuid4()),
        "typ": "access",
    }
    token = jwt.encode(payload, private, algorithm=s.jwt_algorithm)
    return token, expires


def issue_refresh_token(*, user_id: str) -> tuple[str, datetime]:
    s = get_settings()
    private, _ = _load_keys()
    now = datetime.now(UTC)
    expires = now + timedelta(days=s.jwt_refresh_ttl_days)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(uuid4()),
        "typ": "refresh",
    }
    token = jwt.encode(payload, private, algorithm=s.jwt_algorithm)
    return token, expires


def verify_token(token: str, *, expected_type: str = "access") -> dict[str, Any]:
    s = get_settings()
    _, public = _load_keys()
    try:
        claims = jwt.decode(token, public, algorithms=[s.jwt_algorithm])
    except JWTError as exc:
        raise TokenError(str(exc)) from exc
    if claims.get("typ") != expected_type:
        raise TokenError(f"unexpected token type: {claims.get('typ')}")
    return claims
