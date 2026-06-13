"""Tamper-evident audit log.

Each row's HMAC includes the previous row's HMAC. Tampering breaks the chain
and is detectable by `scripts/audit_verify.py`.

Design notes (post-review hardening):

* **Serialization of writers** — concurrent transactions could read the same
  `prev_hmac` and fork the chain. We take a Postgres transaction-scoped
  advisory lock before reading the chain head, serializing audit appends
  without locking any business tables.
* **Canonical payload storage** — the HMAC is computed over a canonical JSON
  encoding. We persist that exact text in `payload_canonical` and verify
  against it byte-for-byte. (Verifying via the JSONB column would be fragile:
  JSONB normalizes key order and numeric representation.)
* **Rollback-proof denial events** — audit records written inside a request
  transaction die with it when the request raises. `write_event_standalone`
  commits in its own transaction and MUST be used for `denied` outcomes that
  precede an HTTPException.

The runtime DB user has INSERT-only on this table; UPDATE/DELETE are revoked
in `migrations/001_init.sql`.
"""
from __future__ import annotations

import hmac
import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings

_AUDIT_ADVISORY_LOCK_KEY = 0x41554449  # "AUDI"


def _load_hmac_key() -> bytes:
    return get_settings().audit_hmac_key_path.read_bytes().strip()


def _canonical_json(obj: dict[str, Any]) -> str:
    """Stable JSON encoding used as HMAC input. Persisted verbatim."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _compute_hmac(prev_hmac: str, payload: dict[str, Any]) -> str:
    return _compute_hmac_canonical(prev_hmac, _canonical_json(payload))


def _compute_hmac_canonical(prev_hmac: str, canonical: str) -> str:
    key = _load_hmac_key()
    msg = prev_hmac.encode("utf-8") + canonical.encode("utf-8")
    return hmac.new(key, msg, sha256).hexdigest()


async def write_event(
    session: AsyncSession,
    *,
    actor_user_id: str | None,
    actor_role: str | None,
    action: str,
    resource: str | None,
    outcome: str,
    nist_control: str | None = None,
    detail: dict[str, Any] | None = None,
    request_ip: str | None = None,
) -> str:
    """Append an audit event inside the caller's transaction.

    Use this for events that should commit *with* the business change
    (e.g. a settled transfer). For denied outcomes that will be followed
    by an HTTPException, use `write_event_standalone` instead — otherwise
    the rollback destroys the audit record.
    """
    payload = {
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
        "action": action,
        "resource": resource,
        "outcome": outcome,
        "nist_control": nist_control,
        "detail": detail or {},
        "request_ip": request_ip,
        "ts": datetime.now(UTC).isoformat(),
    }
    canonical = _canonical_json(payload)

    # Serialize appends. Advisory locks are Postgres-only; unit tests run
    # against SQLite where single-writer semantics make the lock moot.
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_ADVISORY_LOCK_KEY}
        )

    row = await session.execute(
        text("SELECT hmac FROM audit_events ORDER BY id DESC LIMIT 1")
    )
    prev = row.scalar_one_or_none() or "GENESIS"
    new_hmac = _compute_hmac_canonical(prev, canonical)

    result = await session.execute(
        text(
            """
            INSERT INTO audit_events
              (actor_user_id, actor_role, action, resource, outcome,
               nist_control, detail, request_ip, prev_hmac, hmac,
               payload_json, payload_canonical)
            VALUES
              (:actor_user_id, :actor_role, :action, :resource, :outcome,
               :nist_control, CAST(:detail AS JSONB), :request_ip,
               :prev_hmac, :hmac, CAST(:payload AS JSONB), :payload_canonical)
            RETURNING id
            """
        ),
        {
            **payload,
            "detail": json.dumps(payload["detail"], default=str),
            "prev_hmac": prev,
            "hmac": new_hmac,
            "payload": canonical,
            "payload_canonical": canonical,
        },
    )
    return str(result.scalar_one())


async def write_event_standalone(**kwargs: Any) -> str:
    """Append an audit event in its OWN transaction.

    Required for `denied` outcomes that precede an HTTPException: the
    request transaction is about to roll back, and audit records must
    survive it (NIST AU-2: failed access attempts are auditable events).
    """
    from app.db.session import get_sessionmaker  # local import avoids cycle

    async with get_sessionmaker()() as session:
        async with session.begin():
            return await write_event(session, **kwargs)


async def verify_chain(session: AsyncSession) -> tuple[bool, int | None]:
    """Walk the chain. Returns (ok, first_bad_id_or_None).

    Verification reads `payload_canonical` (the exact byte string that was
    HMAC'd at write time), never the JSONB column.
    """
    prev = "GENESIS"
    cursor = await session.execute(
        text(
            "SELECT id, prev_hmac, hmac, payload_canonical "
            "FROM audit_events ORDER BY id ASC"
        )
    )
    for ev_id, stored_prev, stored_hmac, canonical in cursor:
        if stored_prev != prev:
            return False, int(ev_id)
        if _compute_hmac_canonical(prev, canonical) != stored_hmac:
            return False, int(ev_id)
        prev = stored_hmac
    return True, None
