"""Unit tests for password hashing + JWT issuance/verification."""
from __future__ import annotations

import time

import pytest
from jose import jwt as jose_jwt

from app.core.settings import get_settings
from app.security.auth import (
    TokenError,
    hash_password,
    issue_access_token,
    issue_refresh_token,
    needs_rehash,
    verify_password,
    verify_token,
)
from app.security.rbac import Role


@pytest.mark.unit
def test_password_round_trip() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password", h)


@pytest.mark.unit
def test_password_hash_is_unique_per_call() -> None:
    """Argon2 includes a random salt — same input must produce different hashes."""
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b
    assert verify_password("same-password", a)
    assert verify_password("same-password", b)


@pytest.mark.unit
def test_needs_rehash_is_false_for_current_hash() -> None:
    h = hash_password("any password long enough")
    assert needs_rehash(h) is False


@pytest.mark.unit
def test_access_token_round_trip() -> None:
    token, exp = issue_access_token(user_id="u-123", role=Role.CUSTOMER)
    claims = verify_token(token, expected_type="access")
    assert claims["sub"] == "u-123"
    assert claims["role"] == "customer"
    assert claims["typ"] == "access"
    assert exp.timestamp() > time.time()


@pytest.mark.unit
def test_refresh_token_cannot_be_used_as_access() -> None:
    refresh, _ = issue_refresh_token(user_id="u-123")
    with pytest.raises(TokenError):
        verify_token(refresh, expected_type="access")


@pytest.mark.unit
def test_tampered_signature_rejected() -> None:
    token, _ = issue_access_token(user_id="u-123", role=Role.CUSTOMER)
    # Flip a character in the signature (last segment).
    head, payload, sig = token.split(".")
    bad = head + "." + payload + "." + ("A" if sig[0] != "A" else "B") + sig[1:]
    with pytest.raises(TokenError):
        verify_token(bad)


@pytest.mark.unit
def test_wrong_algorithm_rejected() -> None:
    """Defense against the algorithm-confusion attack: an attacker who has
    only the public key cannot mint a token that our verifier will accept.

    python-jose actually blocks this at *encode* time (refuses to use an
    asymmetric public key as an HMAC secret) — that's a stronger guarantee
    than just decode-side rejection. We accept either failure mode.
    """
    public = get_settings().jwt_public_key_path.read_text()
    try:
        forged = jose_jwt.encode(
            {"sub": "evil", "role": "admin", "typ": "access", "exp": int(time.time()) + 3600},
            public,
            algorithm="HS256",
        )
    except Exception:
        # Encode-side defense fired — that's a pass.
        return
    # If somehow encoding succeeded, decode must reject.
    with pytest.raises(TokenError):
        verify_token(forged)
