"""Tests for integer USD minor-unit money helpers."""

from __future__ import annotations

import pytest

from agentbank_common.money import format_minor, parse_minor


@pytest.mark.parametrize(
    ("text", "minor"),
    [
        ("0", 0),
        ("1850.00", 185000),
        ("1,850.00", 185000),
        ("0.01", 1),
        ("0.1", 10),
        ("12", 1200),
        ("-5.25", -525),
    ],
)
def test_parse_minor(text: str, minor: int) -> None:
    assert parse_minor(text) == minor


@pytest.mark.parametrize("bad", ["", "abc", "1.234", "1.2.3", "$5"])
def test_parse_minor_rejects_bad(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_minor(bad)


@pytest.mark.parametrize(
    ("minor", "text"),
    [(0, "0.00"), (185000, "1850.00"), (1, "0.01"), (-525, "-5.25"), (99, "0.99")],
)
def test_format_minor(minor: int, text: str) -> None:
    assert format_minor(minor) == text


def test_round_trip() -> None:
    for minor in (0, 1, 99, 100, 185000, -4200):
        assert parse_minor(format_minor(minor)) == minor
