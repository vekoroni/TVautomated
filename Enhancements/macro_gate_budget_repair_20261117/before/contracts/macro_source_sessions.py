"""Session-aware freshness for the saved VIX/extended-hours ETF feeds only.

No collection, redating or live-price inference. Hours describe these feeds,
not every possible overnight trading venue. Calendar uses the shared XNYS
holiday/early-close calendar; unscheduled exchange exceptions are not inferred.
References: https://www.cboe.com/tradable_products/vix/faqs
https://www.nyse.com/trade/hours-calendars
"""
from datetime import datetime, time, timedelta, timezone
import math
from canonical_data.session_clock import (
    NEW_YORK, is_xnys_session, previous_xnys_session, session_bounds,
)

VERSION = 'macro_source_sessions_v1'


def classify_source_session(group, row, now, stale_after_minutes=60):
    """Return None for feeds outside this narrow policy; fail closed otherwise."""
    vix = group == 'volatility' and row.get('symbol') in {'VIX', '^VIX'}
    etf = group == 'us_premarket' and row.get('symbol') in {'SPY', 'QQQ', 'IWM', 'DIA'}
    if not (vix or etf):
        return None
    result = dict(version=VERSION, state='INVALID_TIMESTAMP', stale=True,
                  not_live=False, mode='UNASSESSED', calendar='XNYS_SHARED_CALENDAR')
    try:
        stamp = datetime.fromisoformat(str(row.get('last_bar_utc')).replace('Z', '+00:00'))
        if now.tzinfo is None or stamp.tzinfo is None:
            return result
        now = now.astimezone(timezone.utc)
        stamp = stamp.astimezone(timezone.utc)
        if stamp > now:
            return {**result, 'state': 'FUTURE_QUOTE'}
    except (ValueError, TypeError, OverflowError):
        return result
    try:
        value = row.get('last')
        if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0:
            return {**result, 'state': 'INVALID_VALUE'}
    except (ValueError, TypeError, OverflowError):
        return {**result, 'state': 'INVALID_VALUE'}
    source_state = str(row.get('state') or 'MISSING')
    if source_state not in {'OK', 'STALE', 'CLOSED', 'NOT_YET_OPEN', 'MARKET_CLOSED_LAST_SESSION'}:
        return {**result, 'state': source_state}
    local = now.astimezone(NEW_YORK)

    def bounds(day):
        _, cash_close = session_bounds(day)
        opening = datetime.combine(day, time(3, 15) if vix else time(4), NEW_YORK)
        # VIX ends 15 minutes after cash close; ETF late session lasts four hours.
        closing = cash_close.astimezone(NEW_YORK) + timedelta(minutes=15) if vix else cash_close.astimezone(NEW_YORK) + timedelta(hours=4)
        return opening.astimezone(timezone.utc), closing.astimezone(timezone.utc)

    today = local.date()
    opened, closed = bounds(today) if is_xnys_session(today) else (None, None)
    live = opened is not None and opened <= now < closed
    if live:
        stale = bool(row.get('stale')) or (now-stamp).total_seconds() > stale_after_minutes*60
        state = 'STALE' if stale else 'OK'
        if stamp < opened:
            state, stale = 'AWAITING_CURRENT_SESSION_OBSERVATION', True
        return {**result, 'state': state, 'stale': stale, 'mode': 'LIVE_SESSION',
                'expected_session': today.isoformat(), 'session_open_utc': opened.isoformat(),
                'session_close_utc': closed.isoformat()}
    expected = today if closed is not None and now >= closed else previous_xnys_session(today)
    _, expected_close = bounds(expected)
    # One-minute end-label tolerance for the VIX final observation, not a grace
    # period that admits a prior-session quote after reopening.
    tolerance = timedelta(minutes=1 if vix else 0)
    valid = expected_close-timedelta(minutes=stale_after_minutes) <= stamp <= expected_close+tolerance
    return {**result, 'state': 'MARKET_CLOSED_LAST_SESSION' if valid else 'STALE_CLOSED_SESSION_REFERENCE',
            'stale': not valid, 'not_live': True, 'mode': 'CLOSED_SESSION_REFERENCE',
            'expected_session': expected.isoformat(), 'session_close_utc': expected_close.isoformat()}
