"""Evidence for AC-2(4) (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("AC-2(4)")
