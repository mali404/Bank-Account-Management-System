"""Evidence for IA-2(1) (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("IA-2(1)")
