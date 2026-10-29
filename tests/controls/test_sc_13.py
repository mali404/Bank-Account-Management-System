"""Evidence for SC-13 (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("SC-13")
