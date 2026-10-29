"""Evidence for CA-8 (SPEC §12)."""

from __future__ import annotations

from controls.evidence import check


def test_control() -> None:
    check("CA-8")
