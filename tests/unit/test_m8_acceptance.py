"""M8 stretch items: each one is either a small check or an explicit off switch."""

from __future__ import annotations

from pathlib import Path

import jwt
import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey

from agentbank_fdx.fapi import generate_p256
from agentbank_fdx.instructions import sign_instruction, verify_instruction
from agentbank_gateway.a2a import parse_message


def test_signed_instruction_round_trips_and_rejects_tampering() -> None:
    private = generate_p256()
    public = private.public_key()
    assert isinstance(public, EllipticCurvePublicKey)
    token = sign_instruction({"uetr": "abc", "amount_minor": 185000}, private)
    assert verify_instruction(token, public)["uetr"] == "abc"
    head, payload, signature = token.split(".")
    flipped = "A" if signature[-1] != "A" else "B"
    with pytest.raises(jwt.PyJWTError):
        verify_instruction(f"{head}.{payload}.{signature[:-1]}{flipped}", public)


def test_canada_profile_is_not_the_default(repo_root: Path) -> None:
    raw = yaml.safe_load((repo_root / "config" / "profiles" / "canada-cdb.yaml").read_text())
    assert isinstance(raw, dict)
    assert raw["status"] == "read-only"
    assert raw["default"] is False


def test_a2a_envelope_parses() -> None:
    message = parse_message({"sender": "pen", "recipient": "cba", "text": "confirm payee"})
    assert message.sender == "pen"
    assert message.recipient == "cba"


def test_web_channel_is_off(repo_root: Path) -> None:
    raw = yaml.safe_load((repo_root / "config" / "channels" / "web.yaml").read_text())
    assert isinstance(raw, dict)
    assert raw["enabled"] is False


def test_mojaloop_overlay_stays_empty(repo_root: Path) -> None:
    raw = yaml.safe_load((repo_root / "deploy" / "compose.mojaloop.yaml").read_text())
    assert isinstance(raw, dict)
    assert raw["services"] == {}
    text = (repo_root / "deploy" / "mojaloop" / "README.md").read_text(encoding="utf-8")
    assert "SimNow" in text
