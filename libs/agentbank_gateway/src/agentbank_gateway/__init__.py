"""Agent gateway: defense plugin host and taint-tracking interfaces (SPEC §5.4, §19)."""

from __future__ import annotations

from .defense import Defense, NoDefense
from .registry import available, get_defense, register_defense
from .types import (
    Allow,
    AskHuman,
    Decision,
    Deny,
    Message,
    RunContext,
    TaggedValue,
    ToolCall,
)

__version__ = "0.1.0"

__all__ = [
    "Allow",
    "AskHuman",
    "Decision",
    "Defense",
    "Deny",
    "Message",
    "NoDefense",
    "RunContext",
    "TaggedValue",
    "ToolCall",
    "available",
    "get_defense",
    "register_defense",
]
