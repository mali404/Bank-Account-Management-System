"""UTC time helpers and ISO 8601 formatting.

The testbed stamps everything in UTC (AU-8). ISO 20022 ``CreDtTm`` values use
the same formatting.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["format_iso8601", "now_utc", "today_iso"]


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(UTC)


def format_iso8601(moment: datetime) -> str:
    """Format a ``datetime`` as an ISO 8601 string with a trailing ``Z`` for UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def today_iso(moment: datetime | None = None) -> str:
    """Return the UTC calendar date (``YYYY-MM-DD``) for ``moment`` (or now)."""
    return (moment or now_utc()).astimezone(UTC).date().isoformat()
