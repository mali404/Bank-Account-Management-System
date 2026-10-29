"""FDX-inspired error model and FAPI headers (SPEC §5.1).

The error shape ``{code, message, debugMessage}`` is authored from public
descriptions, not copied from the member-gated FDX specification. ``debugMessage``
is deliberately free text: it is an injection channel (SPEC §8, channel C7).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FDX_INTERACTION_ID_HEADER", "FdxError"]

# Echoed on every FDX-style request/response (SPEC §5.1).
FDX_INTERACTION_ID_HEADER = "x-fapi-interaction-id"


@dataclass(frozen=True, slots=True)
class FdxError:
    """An FDX-style error body."""

    code: str
    message: str
    debug_message: str | None = None

    def to_dict(self) -> dict[str, str]:
        """Render as the wire JSON body (``debugMessage`` omitted when absent)."""
        body = {"code": self.code, "message": self.message}
        if self.debug_message is not None:
            body["debugMessage"] = self.debug_message
        return body
