"""USD money as integer minor units (cents).

All monetary values in the testbed are integers of USD cents. Floating point
is never used for money. Helpers parse and format human-readable decimal
strings without ever constructing a ``float``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CURRENCY = "USD"
MINOR_UNITS_PER_MAJOR = 100

__all__ = ["CURRENCY", "MINOR_UNITS_PER_MAJOR", "format_minor", "parse_minor"]


def parse_minor(amount: str) -> int:
    """Parse a decimal USD string (e.g. ``"1,850.00"``) into integer cents.

    Thousands separators are tolerated. Values with more than two fractional
    digits, or that are otherwise malformed, raise :class:`ValueError`.
    """
    cleaned = amount.strip().replace(",", "")
    if not cleaned:
        raise ValueError("empty amount")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"not a valid decimal amount: {amount!r}") from exc
    if not value.is_finite():
        raise ValueError(f"not a finite amount: {amount!r}")
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise ValueError(f"more than two fractional digits: {amount!r}")
    minor = value.scaleb(2).to_integral_exact(rounding=ROUND_HALF_UP)
    return int(minor)


def format_minor(minor: int) -> str:
    """Format integer cents as a fixed two-decimal USD string (e.g. ``"1850.00"``)."""
    quotient, remainder = divmod(abs(minor), MINOR_UNITS_PER_MAJOR)
    sign = "-" if minor < 0 else ""
    return f"{sign}{quotient}.{remainder:02d}"
