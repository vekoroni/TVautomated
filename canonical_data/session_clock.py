"""Shared XNYS session clock and semantic freshness evaluation.

The calendar implementation is dependency-free and covers regular US equity
holidays, observed dates, early closes and US DST through ``zoneinfo``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")


class SessionState(str, Enum):
    CLOSED = "CLOSED"
    PREMARKET = "PREMARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"


class FreshnessState(str, Enum):
    FRESH = "FRESH"
    EOD_CURRENT = "EOD_CURRENT"
    STALE = "STALE"
    MISSING = "MISSING"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    state: SessionState
    session_date: date | None
    regular_open_utc: datetime | None
    regular_close_utc: datetime | None
    last_completed_session: date
    last_closed_minute_utc: datetime | None


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
    # The last open session before Independence Day is an early close when it
    # falls on July 3 (or July 2 when July 4 is Saturday).
    return (value.month, value.day) in {(7, 3), (7, 2)} and (
        value + timedelta(days=1) == date(value.year, 7, 4)
        or date(value.year, 7, 4).weekday() == 5
    )


def previous_xnys_session(value: date) -> date:
    candidate = value - timedelta(days=1)
    while not is_xnys_session(candidate):
        candidate -= timedelta(days=1)
    return candidate


def advance_xnys_sessions(value: date, count: int) -> date:
    """Advance an XNYS session by an exact non-negative session count."""

    sessions = int(count)
    if sessions != count or sessions < 0:
        raise ValueError("session count must be a non-negative integer")
    if not is_xnys_session(value):
        raise ValueError(f"{value} is not an XNYS session")
    result = value
    for _ in range(sessions):
        result += timedelta(days=1)
        while not is_xnys_session(result):
            result += timedelta(days=1)
    return result


def xnys_sessions_between(start: date, end: date) -> int:
    """Count XNYS trading sessions strictly after `start` up to and including `end`.

    AVS-FIX-001 W1.5. AVS-MVP-001 §4 states its holding rule as "DTE >= 2 x
    hold", where the hold is measured in trading sessions -- so the DTE beside
    it has to be measured the same way. Calendar days would make a Friday
    expiry look like three days of life over a long weekend when it has one
    session left.

    Returns 0 when `end` is on or before `start`, and never a negative number:
    an already-expired contract has no sessions left, it does not have minus
    two of them.
    """

    if end <= start:
        return 0
    sessions = 0
    candidate = start + timedelta(days=1)
    while candidate <= end:
        if is_xnys_session(candidate):
            sessions += 1
        candidate += timedelta(days=1)
    return sessions


def session_bounds(value: date) -> tuple[datetime, datetime]:
    if not is_xnys_session(value):
        raise ValueError(f"{value} is not an XNYS session")
    open_local = datetime.combine(value, time(9, 30), NEW_YORK)
    close_local = datetime.combine(value, time(13 if is_early_close(value) else 16, 0), NEW_YORK)
    return open_local.astimezone(timezone.utc), close_local.astimezone(timezone.utc)


def session_snapshot(now: datetime | None = None) -> SessionSnapshot:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("session clock requires a timezone-aware instant")
    instant = instant.astimezone(timezone.utc)
    local = instant.astimezone(NEW_YORK)
    today = local.date()
    if not is_xnys_session(today):
        return SessionSnapshot(SessionState.CLOSED, None, None, None, previous_xnys_session(today), None)
    open_utc, close_utc = session_bounds(today)
    premarket_utc = datetime.combine(today, time(4), NEW_YORK).astimezone(timezone.utc)
    after_hours_end = datetime.combine(today, time(20), NEW_YORK).astimezone(timezone.utc)
    if instant < premarket_utc or instant >= after_hours_end:
        state = SessionState.CLOSED
    elif instant < open_utc:
        state = SessionState.PREMARKET
    elif instant < close_utc:
        state = SessionState.REGULAR
    else:
        state = SessionState.AFTER_HOURS
    last_session = today if instant >= close_utc else previous_xnys_session(today)
    closed_minute = instant.replace(second=0, microsecond=0) - timedelta(minutes=1) if state is SessionState.REGULAR else None
    return SessionSnapshot(state, today, open_utc, close_utc, last_session, closed_minute)


def evaluate_freshness(
    *,
    as_of: datetime | None,
    dataset_session: date | None,
    domain: str,
    now: datetime | None = None,
    live_ttl_seconds: int = 60,
) -> FreshnessState:
    """Apply semantic freshness; TTL seeds remain caller-owned configuration."""
    if as_of is None:
        return FreshnessState.MISSING
    if as_of.tzinfo is None:
        return FreshnessState.INVALID
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    observed = as_of.astimezone(timezone.utc)
    if observed > instant + timedelta(seconds=1):
        return FreshnessState.INVALID
    snapshot = session_snapshot(instant)
    kind = domain.strip().upper()
    if kind in {"OPTION_CHAIN", "COMPLETED_SESSION", "EOD"}:
        return FreshnessState.EOD_CURRENT if dataset_session == snapshot.last_completed_session else FreshnessState.STALE
    return FreshnessState.FRESH if (instant - observed).total_seconds() <= live_ttl_seconds else FreshnessState.STALE
