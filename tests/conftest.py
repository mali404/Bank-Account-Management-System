"""Shared pytest fixtures."""
from __future__ import annotations

import os
import secrets as _secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(scope="session", autouse=True)
def _test_secrets(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Generate ephemeral keys for tests and point env at them."""
    secrets_dir = tmp_path_factory.mktemp("secrets")

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (secrets_dir / "jwt_private.pem").write_bytes(
        priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (secrets_dir / "jwt_public.pem").write_bytes(
        priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    (secrets_dir / "audit_hmac.key").write_bytes(_secrets.token_bytes(32))
    (secrets_dir / "db_column_dek.key").write_bytes(_secrets.token_bytes(32))

    os.environ["JWT_PRIVATE_KEY_PATH"] = str(secrets_dir / "jwt_private.pem")
    os.environ["JWT_PUBLIC_KEY_PATH"] = str(secrets_dir / "jwt_public.pem")
    os.environ["AUDIT_HMAC_KEY_PATH"] = str(secrets_dir / "audit_hmac.key")
    os.environ["DB_COLUMN_DEK_PATH"] = str(secrets_dir / "db_column_dek.key")

    # Point DSNs at SQLite for unit-only paths; integration tests override.
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")
    os.environ.setdefault("DATABASE_ADMIN_URL", "sqlite:///:memory:")

    # Reset the cached settings since we just changed env.
    from app.core.settings import get_settings
    get_settings.cache_clear()
    yield secrets_dir
