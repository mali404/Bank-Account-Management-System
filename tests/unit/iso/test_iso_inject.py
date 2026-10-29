"""Injection helpers and charset analysis."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from agentbank_iso import charset, inject


def test_split_ustrd_respects_max_len() -> None:
    text = "word " * 60
    lines = inject.split_ustrd(text, max_len=40)
    assert all(len(line) <= 40 for line in lines)
    assert " ".join(lines).split() == text.split()


def test_split_ustrd_hard_splits_long_word() -> None:
    lines = inject.split_ustrd("x" * 350, max_len=140)
    assert [len(x) for x in lines] == [140, 140, 70]


def test_split_ustrd_max_lines() -> None:
    lines = inject.split_ustrd("a b c d e f g", max_len=3, max_lines=2)
    assert len(lines) == 2


@given(st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E), max_size=50))
def test_tag_smuggle_round_trips(text: str) -> None:
    smuggled = inject.tag_smuggle(text)
    assert inject.tag_unsmuggle(smuggled) == text
    if text:
        assert all(0xE0000 <= ord(c) <= 0xE007F for c in smuggled)


def test_homoglyph_deterministic_with_seed() -> None:
    a = inject.homoglyph("Landlord account", seed=7)
    b = inject.homoglyph("Landlord account", seed=7)
    assert a == b
    assert a != "Landlord account"
    assert any(ord(c) > 0x7F for c in a)


def test_homoglyph_full_without_seed() -> None:
    out = inject.homoglyph("oa")
    assert out == "оа"  # both mapped to Cyrillic


def test_bidi_wrap() -> None:
    wrapped = inject.bidi_wrap("Landlord", "rlo")
    assert wrapped.startswith("‮") and wrapped.endswith("‬")
    assert "Landlord" in wrapped


def test_fit_name_truncates() -> None:
    assert inject.fit_name("x" * 200, 140) == "x" * 140
    assert inject.fit_name("short", 140) == "short"


def test_analyze_detects_tricks_and_profile_blocking() -> None:
    clean = inject.analyze("Landlord")
    assert not clean.any_trick
    assert not clean.blocked_by_latin
    assert not clean.blocked_by_extended

    homo = inject.analyze(inject.homoglyph("oa"))
    assert homo.homoglyphs and homo.non_ascii
    assert homo.blocked_by_latin and not homo.blocked_by_extended

    tagged = inject.analyze(inject.tag_smuggle("hi"))
    assert tagged.tag_chars
    assert tagged.blocked_by_latin and not tagged.blocked_by_extended

    bidi = inject.analyze(inject.bidi_wrap("hi", "rlo"))
    assert bidi.bidi_controls
    assert bidi.blocked_by_latin and not bidi.blocked_by_extended


def test_charset_latin_rejects_nonascii_extended_allows() -> None:
    assert charset.is_allowed("Plain ASCII, 123.", "latin")
    assert not charset.is_allowed("café", "latin")
    assert charset.is_allowed("café", "extended")
    # control characters are rejected by both profiles
    assert not charset.is_allowed("a\x01b", "latin")
    assert not charset.is_allowed("a\x01b", "extended")


def test_charset_latin_specials() -> None:
    assert charset.is_allowed("INV-9 (2026) /ref:a,b.", "latin")
