"""Evidence for AU-9(4) (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("AU-9(4)")
