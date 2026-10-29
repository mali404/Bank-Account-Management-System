"""Keycloak realm JSON files must parse and declare the expected realms, with no
committed credentials (SPEC §5.2, §17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REALMS = ["bank-a", "bank-b", "bank-c", "staff"]


@pytest.mark.parametrize("realm", REALMS)
def test_realm_file_valid(repo_root: Path, realm: str) -> None:
    path = repo_root / "deploy" / "keycloak" / "realms" / f"{realm}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["realm"] == realm
    assert data["enabled"] is True
    assert data["sslRequired"] == "external"


@pytest.mark.parametrize("realm", REALMS)
def test_no_committed_credentials(repo_root: Path, realm: str) -> None:
    path = repo_root / "deploy" / "keycloak" / "realms" / f"{realm}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # No users with passwords, no client secrets.
    for user in data.get("users", []):
        assert not user.get("credentials"), f"{realm}: user has committed credentials"
    for client in data.get("clients", []):
        assert "secret" not in client, f"{realm}: client has a committed secret"
