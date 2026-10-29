"""JWS for a payment instruction (SPEC §12 AU-10).

The switch still accepts unsigned pacs.008. This module is the signature
check a later integration can require. Keys are the same P-256 keys the
FAPI helpers use.
"""

from __future__ import annotations

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

__all__ = ["sign_instruction", "verify_instruction"]


def sign_instruction(body: dict[str, object], private: ec.EllipticCurvePrivateKey) -> str:
    """Sign ``body`` as a compact JWS."""
    encoded = jwt.encode(body, private, algorithm="ES256")
    return encoded if isinstance(encoded, str) else encoded.decode("ascii")


def verify_instruction(token: str, public: ec.EllipticCurvePublicKey) -> dict[str, object]:
    """Return the claims. A bad signature raises ``jwt.PyJWTError``."""
    claims = jwt.decode(token, public, algorithms=["ES256"])
    if not isinstance(claims, dict):
        raise jwt.PyJWTError("instruction claims are not an object")
    return {str(key): value for key, value in claims.items()}
