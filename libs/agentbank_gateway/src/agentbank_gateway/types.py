"""Core typed interfaces shared by the agent gateway and defenses (SPEC §19).

These types are a stable interface: do not change them without a version bump.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "Allow",
    "AskHuman",
    "Decision",
    "Deny",
    "Message",
    "Role",
    "RunContext",
    "TaggedValue",
    "ToolCall",
    "Trust",
]

Role = Literal["system", "user", "assistant", "tool"]
Trust = Literal["trusted", "untrusted"]


@dataclass(frozen=True, slots=True)
class Message:
    """A single chat message passed to or from the LLM."""

    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class TaggedValue:
    """A tool-output value carrying provenance and a trust label.

    MCP tool servers wrap externally sourced free text this way (SPEC §5.5) so
    defenses can reason about where a value came from and whether it is trusted.
    """

    value: str
    provenance: str
    trust: Trust = "untrusted"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A request by the agent to invoke a tool with structured arguments."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None


@dataclass(slots=True)
class RunContext:
    """Per-run context threaded through every defense hook (SPEC §5.4)."""

    run_id: str
    scenario_id: str | None = None
    task_id: str | None = None
    defense_profile: str = "D0"
    seed: int = 42
    tool_call_budget: int = 25
    tool_calls_made: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Allow:
    """Permit a tool call."""


@dataclass(frozen=True, slots=True)
class Deny:
    """Block a tool call, with a human-readable reason."""

    reason: str


@dataclass(frozen=True, slots=True)
class AskHuman:
    """Route a tool call to a human-in-the-loop approval step."""

    prompt: str


# Decision returned by ``Defense.on_tool_call``.
Decision = Allow | Deny | AskHuman
