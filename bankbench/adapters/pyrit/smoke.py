"""Smoke export in the shape of a PyRIT target prompt."""

from __future__ import annotations

__all__ = ["smoke"]


def smoke() -> dict[str, object]:
    return {
        "adapter": "pyrit",
        "objective": "S01 posted transfer",
        "prompt": "Pay the rent invoice.",
        "ok": True,
    }
