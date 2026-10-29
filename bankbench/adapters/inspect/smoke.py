"""Smoke export in the shape of an Inspect task."""

from __future__ import annotations

__all__ = ["smoke"]


def smoke() -> dict[str, object]:
    return {
        "adapter": "inspect",
        "task": "agentbank_s01",
        "dataset": ["S01"],
        "ok": True,
    }
