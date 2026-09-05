"""Integer-only money and basis-point helpers. No binary floating point."""
from __future__ import annotations

import re

WHOLE_DOLLAR_RE = re.compile(r'^-?\d+$')
PERIOD_RE = re.compile(r'^\d{4}-\d{2}$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


class MoneyParseError(ValueError):
    """Input is not a whole-dollar integer."""


def parse_whole_dollars_to_minor(raw: str, *, field: str) -> int:
    """Convert a whole-dollar token to integer minor units (dollars * 100)."""
    text = (raw or '').strip()
    if not WHOLE_DOLLAR_RE.match(text):
        raise MoneyParseError(f'{field} is not a whole-dollar integer: {raw!r}')
    return int(text) * 100


def parse_int(raw: str, *, field: str) -> int:
    text = (raw or '').strip()
    if not WHOLE_DOLLAR_RE.match(text):
        raise MoneyParseError(f'{field} is not an integer: {raw!r}')
    return int(text)


def minor_to_usd(amount_minor: int) -> int:
    """Whole-dollar display units. Truncates toward zero; inputs are dollar-aligned."""
    return amount_minor // 100


def round_half_away_from_zero(numerator: int, denominator: int) -> int:
    """Integer division rounded half away from zero."""
    if denominator == 0:
        raise ZeroDivisionError('denominator is zero')
    sign = 1 if (numerator >= 0) == (denominator >= 0) else -1
    n, d = abs(numerator), abs(denominator)
    quotient, remainder = divmod(n, d)
    if remainder * 2 >= d:
        quotient += 1
    return sign * quotient


def percentage_variance_bps(absolute_variance: int, prior_minor: int) -> tuple[int | None, str]:
    """Return (bps_or_none, percentage_state)."""
    if prior_minor == 0 and absolute_variance == 0:
        return 0, 'comparable'
    if prior_minor == 0:
        return None, 'new_activity'
    return round_half_away_from_zero(absolute_variance * 10_000, abs(prior_minor)), 'comparable'


def share_bps(part: int, whole: int) -> int | None:
    if whole == 0:
        return None
    return round_half_away_from_zero(part * 10_000, whole)
