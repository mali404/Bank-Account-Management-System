"""Charset profiles for the switch inbound pipeline (SPEC §5.3).

Two profiles gate free-text content, used by :mod:`agentbank_iso.usage_rules`
and reported by :func:`agentbank_iso.inject.analyze`:

``latin`` (strict)
    Only the printable characters of the classic SWIFT/ISO 20022 restricted
    Latin "x" set: ``A–Z a–z 0–9`` and the specials ``/ - ? : ( ) . , ' +`` and
    the space. Everything else — any non-ASCII character, control characters,
    homoglyphs, Unicode tag characters and bidirectional controls — is rejected.

``extended`` (weak — a deliberately weaker defense knob)
    Allows arbitrary Unicode. It rejects only the traditional control
    characters (C0 ``U+0000–U+001F``, ``DEL`` ``U+007F`` and C1 ``U+0080–U+009F``)
    but *deliberately allows* Unicode tag characters (``U+E0000–U+E007F``) and
    bidirectional controls, so attacks smuggled through those code points pass.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "LATIN_SPECIALS",
    "PROFILES",
    "CharsetViolation",
    "first_violation",
    "is_allowed",
    "violations",
]

LATIN_SPECIALS = frozenset(" /-?:().,'+")

# Unicode ranges of interest.
TAG_RANGE = range(0xE0000, 0xE0080)
BIDI_CONTROLS = frozenset(
    {0x061C, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}
)


def _is_control(cp: int) -> bool:
    return cp < 0x20 or cp == 0x7F or 0x80 <= cp <= 0x9F


def _latin_ok(cp: int) -> bool:
    ch = chr(cp)
    return ch.isascii() and (ch.isalnum() or ch in LATIN_SPECIALS)


def _extended_ok(cp: int) -> bool:
    # Everything except the traditional control characters is allowed.
    return not _is_control(cp)


@dataclass(frozen=True)
class CharsetProfile:
    """A named predicate over code points."""

    name: str

    def allows(self, cp: int) -> bool:
        if self.name == "latin":
            return _latin_ok(cp)
        if self.name == "extended":
            return _extended_ok(cp)
        raise ValueError(f"unknown charset profile {self.name!r}")


PROFILES: dict[str, CharsetProfile] = {
    "latin": CharsetProfile("latin"),
    "extended": CharsetProfile("extended"),
}


@dataclass(frozen=True)
class CharsetViolation:
    """One disallowed character."""

    index: int
    char: str
    codepoint: int

    @property
    def display(self) -> str:
        return f"U+{self.codepoint:04X}"


def violations(text: str, profile: str) -> tuple[CharsetViolation, ...]:
    """Return every character in ``text`` disallowed by ``profile``."""
    prof = _profile(profile)
    out = []
    for index, ch in enumerate(text):
        cp = ord(ch)
        if not prof.allows(cp):
            out.append(CharsetViolation(index=index, char=ch, codepoint=cp))
    return tuple(out)


def first_violation(text: str, profile: str) -> CharsetViolation | None:
    """Return the first disallowed character, or ``None`` if the text is clean."""
    prof = _profile(profile)
    for index, ch in enumerate(text):
        cp = ord(ch)
        if not prof.allows(cp):
            return CharsetViolation(index=index, char=ch, codepoint=cp)
    return None


def is_allowed(text: str, profile: str) -> bool:
    """Return ``True`` iff every character of ``text`` is allowed by ``profile``."""
    return first_violation(text, profile) is None


def _profile(name: str) -> CharsetProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown charset profile {name!r}") from None
