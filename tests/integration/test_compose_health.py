"""Live checks against the running core stack (SPEC §15, §18 M0).

Marked ``compose`` so it is excluded from the default ``make test`` run and only
executed by ``make test-compose``. Skipped automatically when docker is not
available or the stack is not running.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.compose

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT = os.environ.get("AGENTBANK_PROJECT", "agentbank")
COMPOSE = [
    "docker",
    "compose",
    "--project-name",
    PROJECT,
    "--env-file",
    str(REPO_ROOT / ".env"),
    "-f",
    str(REPO_ROOT / "deploy" / "compose.yaml"),
]
SERVICES = ["postgres", "nats", "keycloak", "step-ca"]
REALMS = ["bank-a", "bank-b", "bank-c", "staff"]
SCHEMAS = ["bank_a", "bank_b", "bank_c", "switch", "sim_mail"]


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, cwd=REPO_ROOT, timeout=60)


@pytest.fixture(scope="module", autouse=True)
def _require_stack() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker not available")
    if not (REPO_ROOT / ".env").is_file():
        pytest.skip(".env not present (run make bootstrap)")
    proc = _run([*COMPOSE, "ps", "--format", "json"])
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip("compose stack is not running (run make up)")


def _ps_states() -> dict[str, str]:
    proc = _run([*COMPOSE, "ps", "--format", "json"])
    states: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        states[row.get("Service", "")] = row.get("Health") or row.get("State", "")
    return states


def test_all_services_healthy() -> None:
    states = _ps_states()
    for svc in SERVICES:
        assert states.get(svc) == "healthy", f"{svc} is {states.get(svc)!r}"


def test_postgres_schemas_exist() -> None:
    query = "SELECT schema_name FROM information_schema.schemata;"
    proc = _run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "agentbank",
            "-d",
            "agentbank",
            "-tAc",
            query,
        ]
    )
    assert proc.returncode == 0, proc.stderr
    present = set(proc.stdout.split())
    for schema in SCHEMAS:
        assert schema in present, f"schema {schema} missing"


def test_nats_healthz_and_jetstream() -> None:
    healthz = _run(
        [*COMPOSE, "exec", "-T", "nats", "wget", "-q", "-O-", "http://localhost:8222/healthz"]
    )
    assert healthz.returncode == 0, healthz.stderr
    jsz = _run([*COMPOSE, "exec", "-T", "nats", "wget", "-q", "-O-", "http://localhost:8222/jsz"])
    assert jsz.returncode == 0, jsz.stderr
    # /jsz responds only when JetStream is enabled.
    assert "config" in jsz.stdout or "memory" in jsz.stdout


@pytest.mark.parametrize("realm", REALMS)
def test_keycloak_realm_discovery(realm: str) -> None:
    url = f"http://127.0.0.1:8080/realms/{realm}/.well-known/openid-configuration"
    proc = _run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "keycloak",
            "bash",
            "-c",
            f"exec 3<>/dev/tcp/127.0.0.1/8080; "
            f"printf 'GET /realms/{realm}/.well-known/openid-configuration HTTP/1.1\\r\\n"
            f"Host: localhost\\r\\nConnection: close\\r\\n\\r\\n' >&3; cat <&3",
        ]
    )
    assert proc.returncode == 0, f"{url}: {proc.stderr}"
    assert "issuer" in proc.stdout, f"{url}: no OIDC discovery document"


def test_step_ca_health() -> None:
    proc = _run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "step-ca",
            "step",
            "ca",
            "health",
            "--ca-url",
            "https://localhost:9000",
            "--root",
            "/home/step/certs/root_ca.crt",
        ]
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout.lower()


def test_export_root_cert() -> None:
    script = REPO_ROOT / "deploy" / "pki" / "export-root.sh"
    proc = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, cwd=REPO_ROOT, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    out_file = REPO_ROOT / "deploy" / "pki" / "out" / "root_ca.crt"
    assert out_file.is_file(), "root_ca.crt was not written"
    pem = out_file.read_text(encoding="utf-8")
    assert pem.startswith("-----BEGIN CERTIFICATE-----")
    assert "-----END CERTIFICATE-----" in pem
    assert "SHA-256 fingerprint:" in proc.stdout
