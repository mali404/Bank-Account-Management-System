"""Evidence for SC-8(1) (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("SC-8(1)")
