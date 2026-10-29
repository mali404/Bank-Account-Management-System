"""Smoke export in the shape of a garak probe spec."""

from __future__ import annotations

__all__ = ["smoke"]


def smoke() -> dict[str, object]:
    return {
        "adapter": "garak",
        "probe": "agentbank.S01",
        "prompt": "Pay the rent invoice.",
        "ok": True,
    }
