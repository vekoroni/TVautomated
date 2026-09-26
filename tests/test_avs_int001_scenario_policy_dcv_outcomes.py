"""INT-001 scenario suite 4: governed policy lookup, staged data contract, competing-risk outcomes.

  P1  the Options stage is run on a Saturday, a Sunday and a Monday exchange holiday: the
      ticket-spread limit must resolve from the last completed XNYS session, never today;
  P2  a transient registry failure must not be cached as 'unavailable' for the whole run;
  D1  the data-contract validator is staged: price history can be valid while the regime is
      still missing, and a NaN, stale or short history is a typed rejection, never repaired
      by fabrication;
  O1  first-passage outcome labels over 1/5/10/20 sessions for CALL and PUT theses with gap
      fills, same-session ambiguity, censoring, data gaps and timeouts.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from avshunter.c12_outcome.geometry import classify  # noqa: E402
from avshunter.c12_outcome.model import Bar, OutcomeState, TargetState  # noqa: E402
from avshunter.c12_outcome.passage import evaluate_passage  # noqa: E402
from avshunter.shared.xnys_calendar import is_xnys_session, xnys_session_on_or_before  # noqa: E402
from scripts import avshunter_options_intelligence as oi  # noqa: E402
from scripts.data_contract_validator import DataContractValidator as DCV  # noqa: E402


# ------------------------------------------------------------------------------- P1 / P2
@pytest.fixture(autouse=True)
def _clear_policy_cache():
    oi._TICKET_SPREAD_LIMIT_CACHE.clear()
    yield
    oi._TICKET_SPREAD_LIMIT_CACHE.clear()


@pytest.mark.parametrize("today,expected_session", [
    (date(2026, 9, 26), date(2026, 9, 25)),    # Saturday -> Friday
    (date(2026, 9, 27), date(2026, 9, 25)),    # Sunday -> Friday
    (date(2026, 11, 26), date(2026, 11, 25)),  # Thanksgiving -> preceding Wednesday
    (date(2026, 11, 27), date(2026, 11, 27)),  # Black Friday is a (short) session
])
def test_p1_ticket_policy_resolves_on_the_last_completed_session(monkeypatch, today, expected_session):
    assert xnys_session_on_or_before(today) == expected_session
    assert is_xnys_session(expected_session)
    monkeypatch.setattr(oi, "_iv_evidence_session", lambda: today)
    limit = oi.ticket_spread_limit_fraction()
    assert limit == pytest.approx(0.10)
    assert list(oi._TICKET_SPREAD_LIMIT_CACHE) == [expected_session.isoformat()]
    fraction, state = oi._rr_options_tradeability(1.90, 2.05)
    assert fraction == pytest.approx(0.15 / 1.975, rel=1e-4)
    assert state != oi.RR_TRADEABILITY_LIMIT_UNAVAILABLE


def test_p1c_session_before_the_policy_effective_date_is_typed_unavailable_not_defaulted(monkeypatch):
    # Labor Day 2026 resolves to 2026-09-04, before outcome.signal.max_entry_spread_fraction@1
    # is effective in config/registry; the registry raises and the lookup must say unavailable.
    assert xnys_session_on_or_before(date(2026, 9, 7)) == date(2026, 9, 4)
    monkeypatch.setattr(oi, "_iv_evidence_session", lambda: date(2026, 9, 7))
    assert oi.ticket_spread_limit_fraction() is None
    assert oi._TICKET_SPREAD_LIMIT_CACHE == {}
    _, state = oi._rr_options_tradeability(1.90, 2.05)
    assert state == oi.RR_TRADEABILITY_LIMIT_UNAVAILABLE


def test_p2_registry_failure_is_reported_not_cached_and_no_literal_is_borrowed(monkeypatch):
    monkeypatch.setattr(oi, "_iv_evidence_session", lambda: date(2026, 9, 26))
    import avshunter.config.adapters as adapters

    def broken(*_args, **_kwargs):
        raise OSError("registry unreadable")
    monkeypatch.setattr(adapters, "load_registry", broken)
    assert oi.ticket_spread_limit_fraction() is None
    assert oi._TICKET_SPREAD_LIMIT_CACHE == {}
    fraction, state = oi._rr_options_tradeability(1.90, 2.05)
    assert fraction == pytest.approx(0.15 / 1.975, rel=1e-4)
    assert state == oi.RR_TRADEABILITY_LIMIT_UNAVAILABLE
    monkeypatch.undo()
    monkeypatch.setattr(oi, "_iv_evidence_session", lambda: date(2026, 9, 26))
    assert oi.ticket_spread_limit_fraction() == pytest.approx(0.10)


def test_p1b_unpriced_or_crossed_quotes_never_get_a_spread_fraction():
    for bid, ask in ((None, 2.0), (2.0, None), (0.0, 2.0), (2.1, 2.0), (-1.0, 1.0)):
        fraction, state = oi._rr_options_tradeability(bid, ask)
        assert fraction is None
        assert state == oi.RR_TRADEABILITY_QUOTE_UNAVAILABLE


# ------------------------------------------------------------------------------- D1
def _bars(n: int, *, last: date | None = None, null_at: int | None = None) -> list[dict]:
    last = last or datetime.now(timezone.utc).date()
    rows = []
    for i in range(n):
        day = last - timedelta(days=n - 1 - i)
        close = 50.0 + i * 0.05
        rows.append({"date": day.isoformat(), "open": close - 0.2, "high": close + 0.4,
                     "low": close - 0.5, "close": close, "volume": 1_000_000})
    if null_at is not None:
        rows[null_at]["close"] = None
    return rows


def test_d1_price_history_can_pass_while_regime_is_still_pending():
    package = {"ticker": "ACME", "ohlcv": _bars(260)}
    assert DCV.validate_price_history(package) == (True, "VALID")
    assert DCV.validate(package) == (False, "MISSING_REGIME")
    assert DCV.confidence_level(package) == "HIGH"
    package["regime_snapshot"] = {"regime": "TRANSITIONAL"}
    assert DCV.validate(package) == (True, "VALID")


@pytest.mark.parametrize("package,reason_prefix", [
    ({"ticker": "A"}, "NO_OHLCV"),
    ({"ticker": "A", "ohlcv": _bars(30)}, "INSUFFICIENT_HISTORY"),
    ({"ticker": "A", "ohlcv": _bars(260, null_at=255)}, "NULLS_IN_CRITICAL_COLS (close)"),
    ({"ticker": "A", "ohlcv": _bars(260, last=date(2026, 8, 1))}, "STALE_DATA"),
])
def test_d1_typed_rejections_are_never_repaired_by_fabrication(package, reason_prefix):
    ok, reason = DCV.validate_price_history(package)
    assert ok is False
    assert reason.startswith(reason_prefix)
    repaired, changed, why = DCV.attempt_repair(package)
    assert changed is False
    assert why in {"NO_REPAIRABLE_SOURCE", "ALREADY_PRESENT"}
    if why == "NO_REPAIRABLE_SOURCE":
        assert repaired["data_failure"] is True
    ok_after, _ = DCV.validate_price_history(repaired)
    assert ok_after is False


def test_d1_repair_promotes_timeseries_without_inventing_bars():
    package = {"ticker": "A", "timeseries": {"ohlcv_daily": _bars(220)}, "regime_snapshot": {"r": 1}}
    repaired, changed, why = DCV.attempt_repair(package)
    assert changed is True and why == "REPAIRED_FROM_TIMESERIES"
    assert repaired["ohlcv"] is package["timeseries"]["ohlcv_daily"]
    assert repaired["data_contract"]["ohlcv_repair_source"] == "timeseries.ohlcv_daily"
    assert DCV.validate(repaired) == (True, "VALID")
    annotated = DCV.annotate(repaired)
    assert annotated["data_contract"]["dcv_bars"] == 220
    assert annotated["data_contract"]["dcv_valid"] is True
    assert DCV.confidence_level(repaired) == "HIGH"


def test_d1_a_short_but_usable_history_is_low_confidence_not_rejected():
    package = {"ticker": "A", "ohlcv": _bars(120), "regime_snapshot": {"r": 1}}
    assert DCV.validate(package) == (True, "VALID")
    assert DCV.confidence_level(package) == "LOW"


# ------------------------------------------------------------------------------- O1
def _sessions(n: int, start: date = date(2026, 9, 28)) -> list[date]:
    out, day = [], start
    while len(out) < n:
        if is_xnys_session(day):
            out.append(day)
        day += timedelta(days=1)
    return out


def _bar(day: date, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(day, o, h, l, c)


def _flat_bars(days: list[date], level: float) -> dict[date, Bar]:
    return {d: _bar(d, level, level + 0.3, level - 0.3, level) for d in days}


def test_o1_call_target_first_on_session_three_with_r_multiple():
    geometry = classify("CALL", 100.0, 95.0, 110.0, "ACME261120C00100000")
    assert geometry.scorable and geometry.target_state is TargetState.LEVEL
    days = _sessions(5)
    bars = _flat_bars(days, 101.0)
    bars[days[2]] = _bar(days[2], 103.0, 111.2, 102.5, 109.0)
    outcome = evaluate_passage(geometry, days, bars, 5)
    assert outcome.state is OutcomeState.TARGET_FIRST
    assert outcome.resolution_session == 3
    assert outcome.exit_price == 110.0
    assert outcome.r_multiple == pytest.approx(2.0)
    assert outcome.return_to_exit_pct == pytest.approx(0.10)
    assert outcome.mfe_pct == pytest.approx(0.112)


def test_o1_put_stop_first_with_gap_open_beyond_the_level_fills_at_the_open():
    geometry = classify("PUT", 100.0, 105.0, 90.0, "ACME261120P00100000")
    days = _sessions(5)
    bars = _flat_bars(days, 99.0)
    bars[days[1]] = _bar(days[1], 107.0, 108.0, 105.5, 106.0)  # gap through the stop
    outcome = evaluate_passage(geometry, days, bars, 5)
    assert outcome.state is OutcomeState.STOP_FIRST
    assert outcome.resolution_session == 2
    assert outcome.exit_price == 107.0
    assert outcome.r_multiple == pytest.approx(-1.4)
    assert outcome.mae_pct == pytest.approx(-0.08)


def test_o1_same_session_touch_of_target_and_stop_is_ambiguous_not_a_win():
    geometry = classify("CALL", 100.0, 95.0, 110.0, "ACME261120C00100000")
    days = _sessions(5)
    bars = _flat_bars(days, 100.0)
    bars[days[0]] = _bar(days[0], 100.0, 110.5, 94.5, 100.0)
    outcome = evaluate_passage(geometry, days, bars, 5)
    assert outcome.state is OutcomeState.AMBIGUOUS
    assert outcome.resolution_session == 1
    assert outcome.r_multiple < 0  # the fill assumed is the adverse one


def test_o1_open_windows_are_censored_and_gaps_are_typed_not_scored():
    geometry = classify("CALL", 100.0, 95.0, 110.0, "ACME261120C00100000")
    days = _sessions(10)
    partial = evaluate_passage(geometry, days[:4], _flat_bars(days[:4], 101.0), 10)
    assert partial.state is OutcomeState.OPEN_CENSORED
    assert partial.sessions_observed == 4 and partial.exit_price is None
    assert not partial.state.terminal
    bars = _flat_bars(days, 101.0)
    del bars[days[6]]
    gap = evaluate_passage(geometry, days, bars, 10)
    assert gap.state is OutcomeState.DATA_GAP
    assert gap.sessions_observed == 6
    timeout = evaluate_passage(geometry, days, _flat_bars(days, 101.0), 10)
    assert timeout.state is OutcomeState.TIMEOUT
    assert timeout.exit_price == 101.0
    assert timeout.return_to_exit_pct == pytest.approx(0.01)


def test_o1_missing_target_or_wrong_side_stop_cannot_manufacture_a_target_first():
    no_target = classify("CALL", 100.0, 95.0, None, "ACME261120C00100000")
    assert no_target.target_state is TargetState.NONE
    days = _sessions(5)
    bars = _flat_bars(days, 130.0)  # far above any plausible target
    outcome = evaluate_passage(no_target, days, bars, 5)
    assert outcome.state is OutcomeState.TIMEOUT
    wrong_side = classify("CALL", 100.0, 104.0, 110.0, "ACME261120C00100000")
    assert not wrong_side.scorable
    assert evaluate_passage(wrong_side, days, bars, 5).state is OutcomeState.NOT_SCORABLE
    side_mismatch = classify("PUT", 100.0, 105.0, 90.0, "ACME261120C00100000")
    assert side_mismatch.contract_state.value == "SIDE_MISMATCH"


@pytest.mark.parametrize("window", [1, 5, 10, 20])
def test_o1_each_declared_horizon_scores_the_same_path_consistently(window):
    geometry = classify("PUT", 50.0, 53.0, 44.0, "ACME261120P00050000")
    days = _sessions(20)
    bars = _flat_bars(days, 49.5)
    bars[days[7]] = _bar(days[7], 47.0, 47.5, 43.5, 44.2)  # target on session 8
    outcome = evaluate_passage(geometry, days[:window], bars, window)
    if window < 8:
        assert outcome.state is OutcomeState.TIMEOUT
        assert outcome.resolution_session == window
    else:
        assert outcome.state is OutcomeState.TARGET_FIRST
        assert outcome.resolution_session == 8
        assert outcome.r_multiple == pytest.approx(2.0)
