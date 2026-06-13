#!/usr/bin/env python
"""Generate keys for local development.

Generates:
  secrets/jwt_private.pem  — RSA-2048 private (RS256)
  secrets/jwt_public.pem   — RSA-2048 public
  secrets/audit_hmac.key   — 32 bytes random
  secrets/db_column_dek.key — 32 bytes random

Do NOT commit `secrets/` — it's gitignored. For non-local use, store in
AWS Secrets Manager, Vault, or your secret store of choice.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "secrets"
    out.mkdir(parents=True, exist_ok=True)

    # JWT keypair
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (out / "jwt_private.pem").write_bytes(
        priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (out / "jwt_public.pem").write_bytes(
        priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    # Symmetric keys
    (out / "audit_hmac.key").write_bytes(secrets.token_bytes(32))
    (out / "db_column_dek.key").write_bytes(secrets.token_bytes(32))

    # Tighten permissions
    for p in out.iterdir():
        os.chmod(p, 0o600)

    print(f"keys written to {out}")


if __name__ == "__main__":
    main()
