"""Profile health check: thin trading is a ticker fact, not a provider failure (ACK 5 Oct 2026, change 2).

Run 20261005_072245: 279 partial sessions, all on thinly traded names admitted by the no-gate intake (every one
intake-flagged), put usable_ratio at 0.8785 < 0.90 with zero provider failures. The stage failed, the Lab marked
the run RUN_FATAL and every GO was shown BLOCKED. Business rules:
- A partial session on a ticker Discovery flagged as thinly traded is PARTIAL_SESSION_THIN_TRADING: counted,
  reconciled and labelled, but outside the usable-ratio denominator.
- Partial sessions on normally traded names still count in full: the 5 Sep shape (every ticker half a session)
  still fails on MIN_USABLE_RATIO.
"""
from __future__ import annotations

from pathlib import Path
import tempfile

from tests.test_avs_fix_001_w14_profile_guard import _assert_identity, _run
from tests.test_dynamic_session_phase4 import intraday_frame


def test_thin_trading_partials_do_not_fail_the_stage():
    tickers = [f"T{i:03d}" for i in range(30)] + [f"G{i:03d}" for i in range(70)]

    def behaviour(ticker):
        return intraday_frame(5, 3) if ticker.startswith("T") else intraday_frame(5)

    with tempfile.TemporaryDirectory() as directory:
        summary = _run(Path(directory), tickers, behaviour, thin_tickers={t for t in tickers if t.startswith("T")})

    assert summary["processed"] == 70 and summary["excluded"] == 30
    assert summary["thin_trading_partial_count"] == 30
    assert summary["observable_count"] == 70 and summary["usable_ratio"] == 1.0
    assert summary["guard_decision"] == "PASS"
    _assert_identity(summary)


def test_partials_on_normally_traded_names_still_fail():
    tickers = [f"P{i:03d}" for i in range(30)] + [f"G{i:03d}" for i in range(70)]

    def behaviour(ticker):
        return intraday_frame(5, 3) if ticker.startswith("P") else intraday_frame(5)

    with tempfile.TemporaryDirectory() as directory:
        summary = _run(Path(directory), tickers, behaviour, thin_tickers=set())

    assert summary["thin_trading_partial_count"] == 0
    assert summary["usable_ratio"] == 0.7 and summary["guard_decision"] == "MIN_USABLE_RATIO"


def test_thin_tickers_come_from_discovery_intake_flags(tmp_path):
    import pandas as pd
    from scripts.build_completed_market_profiles import thin_trading_tickers
    (tmp_path / "discovery").mkdir()
    pd.DataFrame({"ticker": ["AAA", "BBB", "CCC", "DDD"],
                  "intake_flags": ["AVG_VOLUME_BELOW_MIN", "NONE", "PRICE_BELOW_MIN|ADV_DOLLARS_BELOW_MIN", None]}
                 ).to_csv(tmp_path / "discovery" / "discovery_candidates_ultimate_R.csv", index=False)
    assert thin_trading_tickers(tmp_path) == {"AAA", "CCC"}
    assert thin_trading_tickers(tmp_path / "missing") == set()
