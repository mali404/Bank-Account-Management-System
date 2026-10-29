"""Evidence for AC-6(10) (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("AC-6(10)")
