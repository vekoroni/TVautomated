"""XNYS trading-session calendar (pure, dependency-free).

Provenance: copied from ``canonical_data/session_clock.py`` (holiday, early-close
and session-count functions) on 16 Sep 2026 so the rebuild package does not
import the legacy ``canonical_data`` package, whose ``__init__`` pulls pandas.
Behaviour must stay identical; ``tests_rebuild/test_xnys_calendar.py`` checks
parity against the legacy module.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


class SessionPhase(str, Enum):
    CLOSED = "CLOSED"
    PREMARKET = "PREMARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"


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


def is_early_close(value: date) -> bool:
    if not is_xnys_session(value):
        return False
    thanksgiving = _nth_weekday(value.year, 11, 3, 4)
    if value == thanksgiving + timedelta(days=1):
        return True
    if value.month == 12 and value.day == 24:
        return True
    return (value.month, value.day) in {(7, 3), (7, 2)} and (
        value + timedelta(days=1) == date(value.year, 7, 4)
        or date(value.year, 7, 4).weekday() == 5
    )


def session_bounds(value: date) -> tuple[datetime, datetime]:
    if not is_xnys_session(value):
        raise ValueError(f"{value} is not an XNYS session")
    open_local = datetime.combine(value, time(9, 30), NEW_YORK)
    close_local = datetime.combine(value, time(13 if is_early_close(value) else 16, 0), NEW_YORK)
    return open_local.astimezone(timezone.utc), close_local.astimezone(timezone.utc)


def session_state(instant: datetime) -> tuple[SessionPhase, date | None, date]:
    """Return (phase, market_session_or_None, last_completed_session) for an aware instant.

    Same rules as legacy ``session_snapshot``: premarket from 04:00 ET, after hours
    until 20:00 ET; the current session counts as completed from its close.
    """
    if instant.tzinfo is None:
        raise ValueError("session clock requires a timezone-aware instant")
    instant = instant.astimezone(timezone.utc)
    today = instant.astimezone(NEW_YORK).date()
    if not is_xnys_session(today):
        return SessionPhase.CLOSED, None, previous_xnys_session(today)
    open_utc, close_utc = session_bounds(today)
    premarket_utc = datetime.combine(today, time(4), NEW_YORK).astimezone(timezone.utc)
    after_hours_end = datetime.combine(today, time(20), NEW_YORK).astimezone(timezone.utc)
    if instant < premarket_utc or instant >= after_hours_end:
        phase = SessionPhase.CLOSED
    elif instant < open_utc:
        phase = SessionPhase.PREMARKET
    elif instant < close_utc:
        phase = SessionPhase.REGULAR
    else:
        phase = SessionPhase.AFTER_HOURS
    last_completed = today if instant >= close_utc else previous_xnys_session(today)
    return phase, today, last_completed


def previous_xnys_session(value: date) -> date:
    candidate = value - timedelta(days=1)
    while not is_xnys_session(candidate):
        candidate -= timedelta(days=1)
    return candidate


def xnys_session_on_or_before(value: date) -> date:
    """The session itself, or the latest XNYS session before a weekend or holiday."""
    return value if is_xnys_session(value) else previous_xnys_session(value)


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
