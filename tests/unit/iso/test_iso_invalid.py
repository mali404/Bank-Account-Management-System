"""Invalid samples are rejected with the expected field path and rule."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from agentbank_iso.validate import validate_xsd

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "iso" / "invalid"
_CASES: list[dict[str, Any]] = yaml.safe_load((FIXTURES / "cases.yaml").read_text())["cases"]


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c["file"])
def test_invalid_sample_rejected(case: dict[str, Any]) -> None:
    xml = (FIXTURES / case["file"]).read_bytes()
    result = validate_xsd(xml)

    assert not result.ok, f"{case['file']} unexpectedly validated"
    assert result.message_id == case["message_id"]

    matches = [i for i in result.issues if i.path == case["path"] and i.rule == case["rule"]]
    assert matches, (
        f"{case['file']}: no issue at path {case['path']!r} with rule {case['rule']!r}; "
        f"got {[(i.path, i.rule) for i in result.issues]}"
    )


def test_wrong_namespace_when_message_id_given() -> None:
    """A document validated against the wrong message id reports a namespace issue."""
    valid = (FIXTURES / "toolong_ustrd.xml").read_bytes().replace(b"x" * 141, b"ok")
    result = validate_xsd(valid, "pain.001.001.09")
    assert not result.ok
    assert result.issues[0].rule == "iso:namespace"
    assert result.issues[0].path == "/"
