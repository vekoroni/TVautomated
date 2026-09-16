"""XNYS trading-session calendar (pure, dependency-free).

Provenance: copied from ``canonical_data/session_clock.py`` (holiday, early-close
and session-count functions) on 16 Sep 2026 so the rebuild package does not
import the legacy ``canonical_data`` package, whose ``__init__`` pulls pandas.
Behaviour must stay identical; ``tests_rebuild/test_xnys_calendar.py`` checks
parity against the legacy module.
"""

from __future__ import annotations

from datetime import date, timedelta


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    value = date(year, month, 1)
    value += timedelta(days=(weekday - value.weekday()) % 7 + 7 * (occurrence - 1))
    return value


def _last_weekday(year: int, month: int, weekday: int) -> date:
    value = date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1)
    return value - timedelta(days=(value.weekday() - weekday) % 7)


def _observed(value: date) -> date:
    if value.weekday() == 5:
        return value - timedelta(days=1)
    if value.weekday() == 6:
        return value + timedelta(days=1)
    return value


def _easter(year: int) -> date:
    # Anonymous Gregorian algorithm.
    a, b = year % 19, year // 100
    c, d, e = year % 100, b // 4, b % 4
    f, g = (b + 8) // 25, (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def xnys_holidays(year: int) -> frozenset[date]:
    holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),              # MLK
        _nth_weekday(year, 2, 0, 3),              # Presidents
        _easter(year) - timedelta(days=2),        # Good Friday
        _last_weekday(year, 5, 0),                # Memorial
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),              # Labor
        _nth_weekday(year, 11, 3, 4),             # Thanksgiving
        _observed(date(year, 12, 25)),
    }
    if year >= 2022:
        holidays.add(_observed(date(year, 6, 19)))
    next_new_year_observed = _observed(date(year + 1, 1, 1))
    if next_new_year_observed.year == year:
        holidays.add(next_new_year_observed)
    return frozenset(holidays)


def is_xnys_session(value: date) -> bool:
    return value.weekday() < 5 and value not in xnys_holidays(value.year)


def previous_xnys_session(value: date) -> date:
    candidate = value - timedelta(days=1)
    while not is_xnys_session(candidate):
        candidate -= timedelta(days=1)
    return candidate


def xnys_sessions_between(start: date, end: date) -> int:
    """Count sessions strictly after ``start`` up to and including ``end``."""
    if end <= start:
        return 0
    sessions = 0
    candidate = start + timedelta(days=1)
    while candidate <= end:
        if is_xnys_session(candidate):
            sessions += 1
        candidate += timedelta(days=1)
    return sessions
