"""Seal a PSP access token so the stored bytes are not the token (SC-28)."""

from __future__ import annotations

from cryptography.fernet import Fernet

__all__ = ["open_token", "seal_token"]


def seal_token(token: str, key: bytes) -> bytes:
    """Encrypt ``token`` with a Fernet key. The token is not a substring of the result."""
    return Fernet(key).encrypt(token.encode("utf-8"))


def open_token(blob: bytes, key: bytes) -> str:
    """Reverse :func:`seal_token`."""
    return Fernet(key).decrypt(blob).decode("utf-8")
