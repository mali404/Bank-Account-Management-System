"""Identifier helpers: UUIDs, UETRs and ISO 20022 message identifiers.

The generators accept an optional :class:`random.Random` so that seeded runs
produce deterministic identifiers, which the reproducibility oracles depend on.
"""

from __future__ import annotations

import re
import uuid
from random import Random

# A UETR is a UUID version 4 (RFC 4122) rendered lower-case.
_UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

# ISO 20022 identifiers such as MsgId and EndToEndId are RestrictedFINXMax35Text.
MAX_ISO_ID_LEN = 35
_ISO_ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

__all__ = [
    "MAX_ISO_ID_LEN",
    "is_valid_uetr",
    "new_end_to_end_id",
    "new_msg_id",
    "new_uetr",
    "new_uuid4",
]


def _uuid4(rng: Random | None) -> uuid.UUID:
    if rng is None:
        return uuid.uuid4()
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def new_uuid4(rng: Random | None = None) -> str:
    """Return a new UUID4 string, deterministic when ``rng`` is supplied."""
    return str(_uuid4(rng))


def new_uetr(rng: Random | None = None) -> str:
    """Return a new UETR (a lower-case UUID4), deterministic when ``rng`` is supplied."""
    return str(_uuid4(rng))


def is_valid_uetr(value: str) -> bool:
    """Return ``True`` iff ``value`` is a well-formed UETR (UUID4)."""
    return bool(_UUID4_RE.match(value))


def _iso_id(prefix: str, rng: Random | None) -> str:
    chooser = rng if rng is not None else Random()
    budget = MAX_ISO_ID_LEN - len(prefix)
    if budget <= 0:
        raise ValueError(f"prefix {prefix!r} leaves no room for a suffix")
    suffix = "".join(chooser.choice(_ISO_ID_ALPHABET) for _ in range(budget))
    return f"{prefix}{suffix}"


def new_msg_id(prefix: str = "MSG", rng: Random | None = None) -> str:
    """Generate an ISO 20022 MsgId (<= 35 chars), deterministic when ``rng`` is supplied."""
    return _iso_id(prefix, rng)


def new_end_to_end_id(prefix: str = "E2E", rng: Random | None = None) -> str:
    """Generate an ISO 20022 EndToEndId (<= 35 chars), deterministic when ``rng`` is supplied."""
    return _iso_id(prefix, rng)
