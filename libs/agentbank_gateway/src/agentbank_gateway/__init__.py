"""Agent gateway: defense plugin host and taint-tracking interfaces (SPEC §5.4, §19)."""

from __future__ import annotations

from .defense import Defense, NoDefense
from .defenses import (
    BankControls,
    Camel,
    Combo,
    Detector,
    EgressDlp,
    Hitl,
    PolicyFilter,
    Sandwich,
    Spotlighting,
    ToolPruning,
)
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
    "BankControls",
    "Camel",
    "Combo",
    "Decision",
    "Defense",
    "Deny",
    "Detector",
    "EgressDlp",
    "Hitl",
    "Message",
    "NoDefense",
    "PolicyFilter",
    "RunContext",
    "Sandwich",
    "Spotlighting",
    "TaggedValue",
    "ToolCall",
    "ToolPruning",
    "available",
    "get_defense",
    "register_defense",
]
