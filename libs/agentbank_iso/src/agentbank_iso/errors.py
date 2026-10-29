"""Typed errors raised by the ISO library."""

from __future__ import annotations

__all__ = ["BuildError", "FieldLengthError", "IsoError", "ParseError"]


class IsoError(Exception):
    """Base class for all :mod:`agentbank_iso` errors."""


class BuildError(IsoError):
    """A domain model could not be turned into a valid message."""


class FieldLengthError(BuildError):
    """A free-text field exceeded the XSD ``maxLength`` for its element."""

    def __init__(self, field: str, max_length: int, actual: int) -> None:
        self.field = field
        self.max_length = max_length
        self.actual = actual
        super().__init__(f"{field} is {actual} characters; the schema allows at most {max_length}")


class ParseError(IsoError):
    """Raw XML could not be parsed into a binding instance."""
