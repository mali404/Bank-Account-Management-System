"""Tests for UTC time helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from agentbank_common.timeutil import format_iso8601, now_utc, today_iso


def test_now_utc_is_timezone_aware() -> None:
    assert now_utc().tzinfo is not None


def test_format_iso8601_uses_z_suffix() -> None:
    moment = datetime(2026, 10, 28, 12, 30, 0, tzinfo=UTC)
    assert format_iso8601(moment) == "2026-10-28T12:30:00Z"


def test_format_iso8601_assumes_utc_when_naive() -> None:
    moment = datetime(2026, 10, 28, 0, 0, 0)
    assert format_iso8601(moment).endswith("Z")


def test_today_iso() -> None:
    moment = datetime(2026, 10, 28, 23, 59, 0, tzinfo=UTC)
    assert today_iso(moment) == "2026-10-28"
