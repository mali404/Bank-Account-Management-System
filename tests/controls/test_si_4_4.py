"""Evidence for SI-4(4) (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("SI-4(4)")
