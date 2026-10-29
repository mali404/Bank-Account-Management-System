"""Evidence for SR-3 (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("SR-3")
