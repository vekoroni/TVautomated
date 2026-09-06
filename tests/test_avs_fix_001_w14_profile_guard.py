"""AVS-FIX-001 W1.4 (QT-D03, AVS-PRE-001 EBC) — profile-stage guard semantics.

The defect: `usable_ratio` divided published profiles by the WHOLE input, so a
session in which many tickers simply did not trade looked like a coverage
failure even when every observable ticker produced a profile. And
`failure_ratio` counted only provider transport failures, so ATR and other data
defects never reached the systemic-failure guard at all.

The population is now four disjoint buckets satisfying
`input = processed + excluded + deferred + exceptions`:

    processed   a governed profile was published
    excluded    bars arrived but could not represent the session (PARTIAL)
    deferred    there was nothing to observe (future session, inactive ticker)
    exceptions  the provider or the calculation failed

`usable_ratio = processed / (input - deferred)` and
`failure_ratio = exceptions / input`, and the stage publishes one named
`guard_decision` rather than a combination of booleans.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile

import pytest

from canonical_data.marketdata_stock_candles import (
    MarketDataCandleNoData,
    MarketDataCandleResponse,
    MarketDataCandleTransportError,
)
from scripts.build_completed_market_profiles import build_completed_profiles

from tests.test_dynamic_session_phase4 import (
    SESSION,
    _create_profile_run,
    intraday_frame,
)


def _response(http_status: int, provider_status: str = "no_data"):
    return MarketDataCandleResponse(
        payload={"s": provider_status},
        http_status=http_status,
        headers={},
        acquired_at_utc=datetime.now(timezone.utc),
    )


def _no_data():
    return MarketDataCandleNoData("no data", response=_response(200, "no_data"))


def _transport(http_status: int = 503):
    return MarketDataCandleTransportError(
        "provider unavailable", response=_response(http_status, "error")
    )


def _run(root: Path, tickers, behaviour, **kwargs):
    run_id = _create_profile_run(root, tuple(tickers))

    def factory(_session, _interval):
        def fetch(ticker, start, end):
            action = behaviour(ticker)
            if isinstance(action, BaseException):
                raise action
            return action
        return fetch

    return build_completed_profiles(
        run_id=run_id, session_date=SESSION, base_dir=root,
        fetch_factory=factory, **kwargs
    )


def _assert_identity(summary):
    assert summary["input_count"] == (
        summary["processed"] + summary["excluded"]
        + summary["deferred"] + summary["hard_exception_count"]
    ), summary
    assert summary["reconciled"] is True


def test_healthy_shape_passes():
    with tempfile.TemporaryDirectory() as directory:
        summary = _run(
            Path(directory), [f"T{i:03d}" for i in range(10)],
            lambda ticker: intraday_frame(5),
        )
    assert summary["processed"] == 10
    assert summary["usable_ratio"] == 1.0
    assert summary["failure_ratio"] == 0.0
    assert summary["guard_decision"] == "PASS"
    assert summary["stage_status"] == "PASS"
    assert summary["systemic_failure"] is False
    _assert_identity(summary)


def test_zero_usable_shape_fails_on_min_usable_ratio():
    """The 20260905_151448 shape: nothing usable, some no_data, some defects.

    Scaled down from 1,587 in / 0 usable / 46 no_data / 50 ATR exceptions,
    preserving the ratio that decides the guard: the failure ratio stays under
    max_failure_ratio, so MIN_USABLE_RATIO must be the reason the stage stops,
    not MAX_FAILURE_RATIO.
    """
    tickers = (
        [f"D{i:03d}" for i in range(46)]
        + [f"X{i:03d}" for i in range(4)]
        + [f"P{i:03d}" for i in range(50)]
    )

    def behaviour(ticker):
        if ticker.startswith("D"):
            return _no_data()
        if ticker.startswith("X"):
            return _transport()
        return intraday_frame(5, 3)     # bars present, session unrepresentable

    with tempfile.TemporaryDirectory() as directory:
        summary = _run(Path(directory), tickers, behaviour, max_failure_ratio=0.05)

    assert summary["processed"] == 0
    assert summary["deferred"] == 46
    assert summary["deferred_by_reason"] == {"TICKER_INACTIVE": 46}
    assert summary["excluded"] == 50
    assert summary["hard_exception_count"] == 4
    assert summary["usable_ratio"] == 0.0
    assert summary["failure_ratio"] == pytest.approx(4 / 100)
    assert summary["provider_systemic_failure"] is False
    assert summary["guard_decision"] == "MIN_USABLE_RATIO"
    assert summary["stage_status"] == "FAIL"
    _assert_identity(summary)


def test_heavy_deferral_with_healthy_remainder_passes():
    """Deferrals do not trip the guard.

    12% of the universe did not trade; of the rest, every ticker produced a
    profile. Under the old denominator this reported usable_ratio 0.88 and
    stopped the stage. There is nothing wrong with this run.
    """
    tickers = [f"D{i:03d}" for i in range(12)] + [f"G{i:03d}" for i in range(88)]

    def behaviour(ticker):
        return _no_data() if ticker.startswith("D") else intraday_frame(5)

    with tempfile.TemporaryDirectory() as directory:
        summary = _run(Path(directory), tickers, behaviour)

    assert summary["deferred"] == 12
    assert summary["processed"] == 88
    assert summary["observable_count"] == 88
    assert summary["usable_ratio"] == 1.0
    assert summary["guard_decision"] == "PASS"
    # The old formula, for contrast: 88/100 = 0.88, below the 0.90 gate.
    assert summary["processed"] / summary["input_count"] < summary["min_usable_ratio"]
    _assert_identity(summary)


def test_transport_failures_trip_max_failure_ratio():
    tickers = [f"X{i:03d}" for i in range(10)] + [f"G{i:03d}" for i in range(90)]

    def behaviour(ticker):
        return _transport() if ticker.startswith("X") else intraday_frame(5)

    with tempfile.TemporaryDirectory() as directory:
        summary = _run(Path(directory), tickers, behaviour, min_usable_ratio=0.5)

    assert summary["hard_exception_count"] == 10
    assert summary["failure_ratio"] == pytest.approx(0.10)
    assert summary["guard_decision"] == "MAX_FAILURE_RATIO"
    assert summary["stage_status"] == "FAIL"
    _assert_identity(summary)


def test_entitlement_and_rate_limit_are_named_separately():
    def behaviour(ticker):
        if ticker == "AUTH":
            return _transport(403)
        if ticker == "RATE":
            return _transport(429)
        return _transport(503)

    with tempfile.TemporaryDirectory() as directory:
        summary = _run(
            Path(directory), ["AUTH", "RATE", "DOWN"], behaviour,
            max_failure_ratio=1.0, min_usable_ratio=0.0,
        )

    assert summary["exceptions_by_reason"] == {
        "ENTITLEMENT_DENIED": 1, "PROVIDER_UNAVAILABLE": 1, "RATE_LIMITED": 1,
    }
    _assert_identity(summary)


def test_summary_publishes_every_operator_field():
    with tempfile.TemporaryDirectory() as directory:
        summary = _run(Path(directory), ["AAPL"], lambda ticker: intraday_frame(5))
    for field in (
        "input_count", "processed", "usable_ratio", "partial_session_count",
        "excluded", "deferred", "deferred_by_reason", "exceptions_by_reason",
        "failure_ratio", "guard_decision", "stage_status",
        "population_identity", "reconciled", "observable_count",
    ):
        assert field in summary, field


def test_guard_grants_nothing():
    """The guard can only stop the stage. It never authorises anything."""
    with tempfile.TemporaryDirectory() as directory:
        summary = _run(Path(directory), ["AAPL"], lambda ticker: intraday_frame(5))
    forbidden = {"final_action", "capital_permission", "execution_authority"}
    assert set(summary) & forbidden == set()
    assert summary["guard_decision"] in {
        "PASS", "MIN_USABLE_RATIO", "MAX_FAILURE_RATIO",
        "POPULATION_RECONCILIATION_FAILED",
    }
