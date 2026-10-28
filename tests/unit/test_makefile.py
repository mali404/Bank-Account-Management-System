"""The Makefile must declare the SPEC §15 targets."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REQUIRED_TARGETS = [
    "bootstrap",
    "up",
    "down",
    "ps",
    "logs",
    "health",
    "pki-root",
    "test",
    "test-compose",
    "lint",
    "format",
    "typecheck",
    "check",
    "compose-config",
    "clean",
    "seed",
    "reset",
    "bench",
    "report",
    "controls-check",
]


@pytest.fixture(scope="module")
def makefile(repo_root: Path) -> str:
    return (repo_root / "Makefile").read_text(encoding="utf-8")


@pytest.mark.parametrize("target", REQUIRED_TARGETS)
def test_target_present(makefile: str, target: str) -> None:
    assert re.search(rf"(?m)^{re.escape(target)}:", makefile), f"missing target {target}"


def test_help_is_default_goal(makefile: str) -> None:
    assert ".DEFAULT_GOAL := help" in makefile


def test_compose_uses_project_and_env_file(makefile: str) -> None:
    assert "--project-name" in makefile
    assert "--env-file .env" in makefile
