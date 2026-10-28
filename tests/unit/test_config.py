"""Config sanity: bank routing numbers are in the fictitious range and all
e-mail addresses use .test domains (SPEC §3.1, §16, §17)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

BANKS = ["bank-a", "bank-b", "bank-c"]
PSPS = ["psp-agg", "psp-pis", "psp-pfm"]
ROUTING_RE = re.compile(r"^9999000\d\d$")
# Match only real email addresses (a dotted domain). Persona handles such as
# "alice@bank-b" that appear in note text have no dotted domain and are skipped.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")


def _load(repo_root: Path, rel: str) -> dict[str, Any]:
    data = yaml.safe_load((repo_root / rel).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.mark.parametrize("bank", BANKS)
def test_bank_routing_is_fictitious(repo_root: Path, bank: str) -> None:
    cfg = _load(repo_root, f"config/banks/{bank}.yaml")
    assert cfg["id"] == bank
    assert "name" in cfg
    assert "profile" in cfg
    assert ROUTING_RE.match(str(cfg["routing"])), cfg["routing"]


def test_bank_routings_unique(repo_root: Path) -> None:
    routings = {_load(repo_root, f"config/banks/{b}.yaml")["routing"] for b in BANKS}
    assert len(routings) == len(BANKS)


@pytest.mark.parametrize(
    "rel", [f"config/banks/{b}.yaml" for b in BANKS] + [f"config/psps/{p}.yaml" for p in PSPS]
)
def test_emails_use_test_domain(repo_root: Path, rel: str) -> None:
    text = (repo_root / rel).read_text(encoding="utf-8")
    for match in EMAIL_RE.findall(text):
        assert match.endswith(".test"), f"{rel}: {match} is not a .test domain"


def test_switch_participant_limit_default(repo_root: Path) -> None:
    cfg = _load(repo_root, "config/switch/participants.yaml")
    assert cfg["defaults"]["participant_limit_minor"] == 10_000_000  # $100,000.00


def test_d0_defense_config(repo_root: Path) -> None:
    cfg = _load(repo_root, "config/defenses/D0.yaml")
    assert cfg["id"] == "D0"
    assert cfg["plugin"] == "agentbank_gateway.NoDefense"
