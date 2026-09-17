"""The rebuild calendar copy must match the legacy session clock exactly."""

from __future__ import annotations

from datetime import date, timedelta

from avshunter.shared import xnys_calendar as rebuild


def test_parity_with_legacy_session_clock():
    from canonical_data import session_clock as legacy

    day = date(2021, 1, 1)
    end = date(2030, 12, 31)
    while day <= end:
        assert rebuild.is_xnys_session(day) == legacy.is_xnys_session(day), day
        day += timedelta(days=1)
    for year in range(2021, 2031):
        assert rebuild.xnys_holidays(year) == legacy.xnys_holidays(year)


def test_session_state_parity_with_legacy_snapshot():
    from datetime import datetime, timezone
    from canonical_data import session_clock as legacy

    instants = []
    start = datetime(2026, 3, 6, 0, 0, tzinfo=timezone.utc)   # spans the US DST change
    for hours in range(0, 24 * 21, 1):
        instants.append(start + timedelta(hours=hours, minutes=7))
    instants += [
        datetime(2026, 11, 27, 18, 5, tzinfo=timezone.utc),   # day after Thanksgiving early close
        datetime(2026, 12, 24, 18, 5, tzinfo=timezone.utc),
        datetime(2026, 9, 16, 22, 37, tzinfo=timezone.utc),
        datetime(2026, 9, 17, 13, 45, tzinfo=timezone.utc),
    ]
    for instant in instants:
        phase, session, last_completed = rebuild.session_state(instant)
        snapshot = legacy.session_snapshot(instant)
        assert phase.value == snapshot.state.value, instant
        assert session == snapshot.session_date, instant
        assert last_completed == snapshot.last_completed_session, instant


def test_known_2026_holidays_are_not_sessions():
    for holiday in (date(2026, 4, 3), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7)):
        assert not rebuild.is_xnys_session(holiday)
    assert rebuild.is_xnys_session(date(2026, 9, 17))


def test_session_counting():
    assert rebuild.xnys_sessions_between(date(2026, 9, 4), date(2026, 9, 8)) == 1  # Labor Day between
    assert rebuild.previous_xnys_session(date(2026, 9, 8)) == date(2026, 9, 4)
    assert rebuild.xnys_sessions_between(date(2026, 9, 10), date(2026, 9, 9)) == 0
