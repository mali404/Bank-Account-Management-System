"""Evidence for RA-5 (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("RA-5")
