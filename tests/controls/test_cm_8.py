"""Evidence for CM-8 (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("CM-8")
