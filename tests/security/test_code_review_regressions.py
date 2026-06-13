"""Regression tests for defects found in the pre-release code review.

Each test pins one fix from docs/code_review.md so it cannot silently
regress. Structural checks are deliberate: they fail loudly if someone
reverts the pattern, without needing a live database.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.security
def test_obie_routers_do_not_use_user_session_dep() -> None:
    """Review #1: TPP-facing endpoints must not depend on user-JWT auth.

    `SessionDep` chains to `get_current_user` (user bearer token); TPP
    callers present Basic auth or TPP tokens and would always 401.
    """
    for fname in ("router_aisp.py", "router_pisp.py"):
        src = (ROOT / "app" / "openbanking" / fname).read_text()
        assert "PlainSessionDep" in src, f"{fname} must use PlainSessionDep"
        assert "import SessionDep" not in src.replace("PlainSessionDep", ""), (
            f"{fname} must not import the user-auth SessionDep"
        )


@pytest.mark.security
def test_rls_policies_recognize_system_context() -> None:
    """Review #12: settlement must run under the 'system' RLS context,
    because the payer legitimately cannot see the payee's ledger row."""
    sql = (ROOT / "migrations" / "002_rls.sql").read_text()
    assert sql.count("'system'") >= 3, "all three RLS policies must include 'system'"


@pytest.mark.security
def test_denied_outcomes_use_standalone_audit() -> None:
    """Review #5: audit records for denied outcomes must survive the
    request-transaction rollback triggered by HTTPException."""
    auth_src = (ROOT / "app" / "api" / "auth_router.py").read_text()
    assert "write_event_standalone" in auth_src, "failed logins must persist to audit"

    transfers_src = (ROOT / "app" / "api" / "transfers_router.py").read_text()
    assert "write_event_standalone" in transfers_src, (
        "blocked self-approvals must persist to audit"
    )


@pytest.mark.unit
def test_audit_verification_uses_canonical_payload() -> None:
    """Review #8: verify_chain must read payload_canonical (the exact bytes
    that were HMAC'd), never the JSONB column (which normalizes values)."""
    from app.observability import audit

    src = inspect.getsource(audit.verify_chain)
    assert "payload_canonical" in src
    assert "payload_json" not in src

    sql = (ROOT / "migrations" / "001_init.sql").read_text()
    assert "payload_canonical" in sql


@pytest.mark.unit
def test_audit_writes_are_serialized_on_postgres() -> None:
    """Review #8: concurrent appends must not fork the HMAC chain."""
    from app.observability import audit

    src = inspect.getsource(audit.write_event)
    assert "pg_advisory_xact_lock" in src


@pytest.mark.unit
def test_dockerfile_builds_in_correct_order() -> None:
    """Review #3: app source must be copied before `pip install .`, and
    the --prefix site-packages must be on PYTHONPATH."""
    df = (ROOT / "infra" / "docker" / "Dockerfile").read_text()
    assert df.index("COPY app ./app") < df.index("pip install --prefix=/install")
    assert "/install/lib/python3.12/site-packages" in df


@pytest.mark.unit
def test_compose_secret_paths_match_mounts() -> None:
    """Review #4: env paths must point at the actual compose mounts
    (/run/secrets/<name> — no file extension)."""
    compose = (ROOT / "infra" / "docker" / "docker-compose.yml").read_text()
    for name in ("jwt_private", "jwt_public", "audit_hmac", "db_column_dek"):
        assert f"/run/secrets/{name}\n" in compose or f"/run/secrets/{name}" in compose


@pytest.mark.unit
def test_rate_limiting_is_wired() -> None:
    """Review #9: a Limiter without middleware + handler is inert."""
    src = (ROOT / "app" / "main.py").read_text()
    assert "SlowAPIMiddleware" in src
    assert "RateLimitExceeded" in src
