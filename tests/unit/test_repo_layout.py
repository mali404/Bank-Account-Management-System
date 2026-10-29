"""The repository top-level layout must match SPEC §14."""

from __future__ import annotations

from pathlib import Path

import pytest

TOP_LEVEL_FILES = [
    "LICENSE",
    "NOTICE",
    "README.md",
    "SPEC.md",
    "SAFETY.md",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "Makefile",
    "pyproject.toml",
    "uv.lock",
]

TOP_LEVEL_DIRS = [
    "deploy",
    "config",
    "libs",
    "services",
    "agents",
    "iso20022",
    "data",
    "scenarios",
    "tasks",
    "templates",
    "bankbench",
    "controls",
    "tests",
    "docs",
    "results",
]

LIBS = [
    "agentbank_common",
    "agentbank_iso",
    "agentbank_fdx",
    "agentbank_ledger",
    "agentbank_gateway",
]

# Second-level directories from SPEC §14, each with a README.md.
SERVICES = [
    "bank-core",
    "psp-core",
    "switch",
    "sim-mail",
    "merchant-sim",
    "user-sim",
    "attacker-console",
    "iso-validator",
    "mcp-bank",
    "mcp-psp",
    "mcp-mail-docs",
    "mcp-kb",
    "mcp-ops",
    "mcp-evil",
]
AGENTS = ["cba", "ops", "rec", "ppa", "pen", "ins", "adv"]
ADAPTERS = ["agentdojo", "garak", "pyrit", "promptfoo", "inspect"]

SUBDIR_READMES = (
    [f"services/{s}" for s in SERVICES]
    + [f"agents/{a}" for a in AGENTS]
    + [f"bankbench/adapters/{a}" for a in ADAPTERS]
    + ["data/generator"]
)

PLACEHOLDER_FILES = [
    "iso20022/xsd/MANIFEST.yaml",
    "controls/controls.yaml",
    "controls/audit_events.yaml",
    "deploy/pki/export-root.sh",
]


@pytest.mark.parametrize("name", TOP_LEVEL_FILES)
def test_top_level_file_exists(repo_root: Path, name: str) -> None:
    assert (repo_root / name).is_file()


@pytest.mark.parametrize("name", TOP_LEVEL_DIRS)
def test_top_level_dir_exists(repo_root: Path, name: str) -> None:
    assert (repo_root / name).is_dir()


@pytest.mark.parametrize("name", LIBS)
def test_workspace_library_layout(repo_root: Path, name: str) -> None:
    lib = repo_root / "libs" / name
    assert (lib / "pyproject.toml").is_file()
    assert (lib / "src" / name / "__init__.py").is_file()
    assert (lib / "src" / name / "py.typed").is_file()


@pytest.mark.parametrize("rel", SUBDIR_READMES)
def test_subdir_has_readme(repo_root: Path, rel: str) -> None:
    path = repo_root / rel
    assert path.is_dir(), f"missing directory {rel}"
    assert (path / "README.md").is_file(), f"missing {rel}/README.md"


@pytest.mark.parametrize("rel", PLACEHOLDER_FILES)
def test_placeholder_file_exists(repo_root: Path, rel: str) -> None:
    assert (repo_root / rel).is_file(), f"missing {rel}"
