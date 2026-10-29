"""A small agent-to-agent envelope (SPEC §8, stretch).

This is a JSON object with a sender, a recipient, and a text body. It is
not the full A2A protocol.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["A2AMessage", "parse_message"]


@dataclass(frozen=True)
class A2AMessage:
    sender: str
    recipient: str
    text: str


def parse_message(payload: dict[str, object]) -> A2AMessage:
    """Build a message. Missing fields raise ``ValueError``."""
    sender = payload.get("sender")
    recipient = payload.get("recipient")
    text = payload.get("text")
    if not isinstance(sender, str) or not isinstance(recipient, str) or not isinstance(text, str):
        raise ValueError("sender, recipient, and text are required strings")
    return A2AMessage(sender, recipient, text)
