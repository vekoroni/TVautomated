"""BEH-001 candidate life cycle across runs (C-03 core, RQ-2; A2 Part 4).

Pure rules; persistence lives in canonical_data.behavioural_candidate_ledger.

- Identity is the Candidate_ID (ticker, timeframe, scope, signal type, event bar).
- An event is recorded only when something changed: FIRST_SEEN, STATE_CHANGED,
  LEVELS_REVISED, NO_LONGER_DETECTED, REAPPEARED. An unchanged reading is UNCHANGED
  and adds nothing.
- NO_LONGER_DETECTED needs evidence: the ticker was read this run and the candidate
  was not produced. A ticker that was not read closes nothing (rule R1).
- A successor's parent travels in its FIRST_SEEN event (failure -> next logic).
- Failing or reaching the outcome ends a stage, never the ticker (ACK, 1 Oct). Only a
  ticker that stops trading (last bar stale beyond the configured sessions) ends its life
  cycle: TICKER_NOT_TRADING. New bars later give REAPPEARED.
"""
from __future__ import annotations

from typing import Iterable, List, Mapping, Optional

import numpy as np

FIRST_SEEN = "FIRST_SEEN"
STATE_CHANGED = "STATE_CHANGED"
LEVELS_REVISED = "LEVELS_REVISED"
NO_LONGER_DETECTED = "NO_LONGER_DETECTED"
REAPPEARED = "REAPPEARED"
TICKER_NOT_TRADING = "TICKER_NOT_TRADING"
CLOSED = frozenset({NO_LONGER_DETECTED, TICKER_NOT_TRADING})
UNCHANGED = "UNCHANGED"
LEVEL_FIELDS = ("Trigger_Level", "Invalidation_Level", "Outcome_Level")


def _levels_differ(a: Mapping, b: Mapping, tolerance: float) -> bool:
    for field in LEVEL_FIELDS:
        x, y = a.get(field), b.get(field)
        if (x is None) != (y is None):
            return True
        if x is not None and abs(float(x) - float(y)) > tolerance * max(abs(float(x)), abs(float(y)), 1e-12):
            return True
    return False


def not_trading(last_bar: Mapping[str, str], after_sessions: int) -> set:
    """Tickers whose last bar is more than ``after_sessions`` business days behind the
    latest bar of the run (delisted, halted or no longer supplied)."""
    dates = {t.upper(): str(d)[:10] for t, d in (last_bar or {}).items() if d}
    if not dates:
        return set()
    latest = max(dates.values())
    return {t for t, d in dates.items() if np.busday_count(d, latest) > after_sessions}


def transitions(previous: Mapping[str, Mapping], current: Iterable[Mapping], read_tickers: Iterable[str],
                *, level_tolerance: float, stopped: Iterable[str] = ()) -> List[dict]:
    """Events for one run.

    ``previous``: candidate id -> its latest recorded event (with ``event_type``,
    ``signal_state``, ``ticker`` and the level fields). ``current``: this run's candidates.
    Returns one dict per current candidate (``event_type`` may be UNCHANGED) plus one
    NO_LONGER_DETECTED per previously live candidate of a read ticker that is absent.
    """
    read = {str(t).upper() for t in read_tickers}
    stopped = {str(t).upper() for t in stopped}
    out: List[dict] = []
    seen = set()
    for c in current:
        cid = c["Candidate_ID"]
        if cid in seen:
            continue
        seen.add(cid)
        last: Optional[Mapping] = previous.get(cid)
        if str(c.get("Ticker", cid.split("|")[0])).upper() in stopped:
            kind = UNCHANGED if last is not None and last["event_type"] == TICKER_NOT_TRADING else TICKER_NOT_TRADING
        elif last is None:
            kind = FIRST_SEEN
        elif last["event_type"] in CLOSED:
            kind = REAPPEARED
        elif last["signal_state"] != c.get("Signal_State"):
            kind = STATE_CHANGED
        elif _levels_differ(last, c, level_tolerance):
            kind = LEVELS_REVISED
        else:
            kind = UNCHANGED
        out.append({"event_type": kind, "candidate": c,
                    "previous_state": None if last is None else last["signal_state"]})
    for cid, last in previous.items():
        if cid in seen or last["event_type"] in CLOSED:
            continue
        if str(last["ticker"]).upper() in stopped:
            out.append({"event_type": TICKER_NOT_TRADING, "candidate": None, "candidate_id": cid,
                        "previous_state": last["signal_state"], "last": last})
        elif str(last["ticker"]).upper() in read:
            out.append({"event_type": NO_LONGER_DETECTED, "candidate": None, "candidate_id": cid,
                        "previous_state": last["signal_state"], "last": last})
    return out
