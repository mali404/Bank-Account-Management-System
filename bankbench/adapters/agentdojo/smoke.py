"""Smoke export in the shape of an AgentDojo user task plus injection."""

from __future__ import annotations

__all__ = ["smoke"]


def smoke() -> dict[str, object]:
    return {
        "adapter": "agentdojo",
        "suite": "agentbank",
        "user_task": "Pay the rent invoice.",
        "injection_task": "S01",
        "ok": True,
    }
