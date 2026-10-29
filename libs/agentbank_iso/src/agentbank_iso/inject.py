"""Injection helpers: place payloads inside ISO 20022 length/charset limits.

These are pure functions (no network, no randomness unless a seed is supplied)
used to construct and analyse prompt-injection payloads for the ISO free-text
channels (SPEC §6.2, §8 C3–C6/C12). They cover splitting across 140-character
``Ustrd`` lines, Latin→Cyrillic/Greek homoglyph substitution, Unicode tag-char
smuggling, bidirectional wrapping, name fitting, and a detector that also says
whether the ``latin`` / ``extended`` charset profiles would block the text.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

from .charset import BIDI_CONTROLS, TAG_RANGE, is_allowed

__all__ = [
    "BIDI_KINDS",
    "HOMOGLYPHS",
    "InjectionReport",
    "analyze",
    "bidi_wrap",
    "fit_name",
    "homoglyph",
    "split_ustrd",
    "tag_smuggle",
    "tag_unsmuggle",
]

# Tag characters: printable ASCII 0x20–0x7E map to U+E0020–U+E007E.
_TAG_BASE = 0xE0000

# Common Latin → Cyrillic/Greek confusables (deterministic mapping).
HOMOGLYPHS: dict[str, str] = {
    "a": "а",  # CYRILLIC SMALL LETTER A (U+0430)
    "c": "с",  # CYRILLIC SMALL LETTER ES (U+0441)
    "e": "е",  # CYRILLIC SMALL LETTER IE (U+0435)
    "i": "і",  # CYRILLIC SMALL LETTER BYELORUSSIAN-UKRAINIAN I (U+0456)
    "j": "ј",  # CYRILLIC SMALL LETTER JE (U+0458)
    "o": "о",  # CYRILLIC SMALL LETTER O (U+043E)
    "p": "р",  # CYRILLIC SMALL LETTER ER (U+0440)
    "s": "ѕ",  # CYRILLIC SMALL LETTER DZE (U+0455)
    "x": "х",  # CYRILLIC SMALL LETTER HA (U+0445)
    "y": "у",  # CYRILLIC SMALL LETTER U (U+0443)
    "A": "Α",  # GREEK CAPITAL LETTER ALPHA (U+0391)
    "B": "В",  # CYRILLIC CAPITAL LETTER VE (U+0412)
    "E": "Е",  # CYRILLIC CAPITAL LETTER IE (U+0415)
    "H": "Н",  # CYRILLIC CAPITAL LETTER EN (U+041D)
    "O": "О",  # CYRILLIC CAPITAL LETTER O (U+041E)
    "P": "Р",  # CYRILLIC CAPITAL LETTER ER (U+0420)
    "T": "Т",  # CYRILLIC CAPITAL LETTER TE (U+0422)
    "X": "Х",  # CYRILLIC CAPITAL LETTER HA (U+0425)
}

# bidi wrap kinds: control to open, control to close.
BIDI_KINDS: dict[str, tuple[str, str]] = {
    "rlo": ("‮", "‬"),  # RIGHT-TO-LEFT OVERRIDE … POP DIRECTIONAL FORMATTING
    "lro": ("‭", "‬"),  # LEFT-TO-RIGHT OVERRIDE … POP
    "rli": ("⁧", "⁩"),  # RIGHT-TO-LEFT ISOLATE … POP DIRECTIONAL ISOLATE
    "lri": ("⁦", "⁩"),  # LEFT-TO-RIGHT ISOLATE … PDI
    "fsi": ("⁨", "⁩"),  # FIRST STRONG ISOLATE … PDI
}


def split_ustrd(text: str, max_len: int = 140, max_lines: int | None = None) -> list[str]:
    """Split ``text`` into lines of at most ``max_len`` characters.

    Splitting is word-aware: it breaks on spaces where possible and hard-splits
    any single word longer than ``max_len``. If ``max_lines`` is given the result
    is truncated to that many lines.
    """
    if max_len < 1:
        raise ValueError("max_len must be >= 1")
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        chunks = _hard_split(word, max_len) if len(word) > max_len else [word]
        for chunk in chunks:
            if not current:
                current = chunk
            elif len(current) + 1 + len(chunk) <= max_len:
                current = f"{current} {chunk}"
            else:
                lines.append(current)
                current = chunk
    if current:
        lines.append(current)
    if not lines:
        lines = [""]
    if max_lines is not None:
        lines = lines[:max_lines]
    return lines


def _hard_split(word: str, max_len: int) -> list[str]:
    return [word[i : i + max_len] for i in range(0, len(word), max_len)]


def homoglyph(text: str, mapping: dict[str, str] | None = None, seed: int | None = None) -> str:
    """Replace Latin characters with confusables.

    With ``seed`` the substitution is deterministic but partial (roughly half of
    the eligible characters, chosen by the seeded RNG); without a seed every
    eligible character is substituted. A custom ``mapping`` overrides the default
    :data:`HOMOGLYPHS` table.
    """
    table = mapping if mapping is not None else HOMOGLYPHS
    rng = Random(seed) if seed is not None else None
    out = []
    for ch in text:
        repl = table.get(ch)
        if repl is not None and (rng is None or rng.random() < 0.5):
            out.append(repl)
        else:
            out.append(ch)
    return "".join(out)


def tag_smuggle(text: str) -> str:
    """Encode printable ASCII as invisible Unicode tag characters."""
    out = []
    for ch in text:
        cp = ord(ch)
        if 0x20 <= cp <= 0x7E:
            out.append(chr(_TAG_BASE + cp))
        else:
            out.append(ch)
    return "".join(out)


def tag_unsmuggle(text: str) -> str:
    """Decode Unicode tag characters back to printable ASCII (inverse of smuggle)."""
    out = []
    for ch in text:
        cp = ord(ch)
        if cp in TAG_RANGE and 0x20 <= cp - _TAG_BASE <= 0x7E:
            out.append(chr(cp - _TAG_BASE))
        else:
            out.append(ch)
    return "".join(out)


def bidi_wrap(text: str, kind: str = "rlo") -> str:
    """Wrap ``text`` in a bidirectional control pair (``rlo``/``lro``/isolates)."""
    try:
        open_ctrl, close_ctrl = BIDI_KINDS[kind]
    except KeyError:
        raise ValueError(f"unknown bidi kind {kind!r}; choose from {sorted(BIDI_KINDS)}") from None
    return f"{open_ctrl}{text}{close_ctrl}"


def fit_name(text: str, max_len: int = 140) -> str:
    """Truncate ``text`` to at most ``max_len`` characters (keeps it XSD-valid)."""
    if max_len < 1:
        raise ValueError("max_len must be >= 1")
    return text[:max_len]


@dataclass(frozen=True)
class InjectionReport:
    """What tricks a piece of text contains and which profiles would block it."""

    homoglyphs: bool
    tag_chars: bool
    bidi_controls: bool
    control_chars: bool
    non_ascii: bool
    blocked_by_latin: bool
    blocked_by_extended: bool

    @property
    def any_trick(self) -> bool:
        return self.homoglyphs or self.tag_chars or self.bidi_controls or self.control_chars


_CONFUSABLE_TARGETS = frozenset(HOMOGLYPHS.values())


def analyze(text: str) -> InjectionReport:
    """Report which injection tricks ``text`` uses and how the profiles treat it."""
    tag_chars = any(ord(ch) in TAG_RANGE for ch in text)
    bidi = any(ord(ch) in BIDI_CONTROLS for ch in text)
    control = any(ord(ch) < 0x20 or ord(ch) == 0x7F or 0x80 <= ord(ch) <= 0x9F for ch in text)
    non_ascii = any(ord(ch) > 0x7F for ch in text)
    homoglyphs = any(ch in _CONFUSABLE_TARGETS for ch in text)
    return InjectionReport(
        homoglyphs=homoglyphs,
        tag_chars=tag_chars,
        bidi_controls=bidi,
        control_chars=control,
        non_ascii=non_ascii,
        blocked_by_latin=not is_allowed(text, "latin"),
        blocked_by_extended=not is_allowed(text, "extended"),
    )
