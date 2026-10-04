"""BEH-001 (ACK, 1 Oct): Discovery reads behaviour on every timeframe it can
and publishes every candidate with its evidence. Option-motivated eligibility,
tier and horizon outcomes are attributes for downstream owners, never a gate
on whether the behaviour is read or published."""
import copy

import pandas as pd

import avshunter_discovery_ULTIMATE as discovery
from domain.structure_behaviour.engine import analyse_ticker
from domain.structure_behaviour.policy import load_policy
from test_beh001_sequences import TREND_DOWN, zigzag_bars


def long_daily(points, years=6):
    bars = zigzag_bars(points * 30, bars_per_leg=6)
    return bars.iloc[: 252 * years].reset_index(drop=True)


def test_weekly_and_monthly_are_read_from_daily_bars():
    daily = long_daily(TREND_DOWN + list(reversed(TREND_DOWN)))
    result = analyse_ticker("ABC", daily, None, load_policy(), intraday_status="NO_INTRADAY_DATA")
    assert {"1w", "1mo"} <= set(result["readings"])
    assert result["readings"]["1w"]["Status"] == "EVALUATED"
    assert result["readings"]["1mo"]["Status"] in {"EVALUATED", "NOT_EVALUATED_INSUFFICIENT_BARS"}


def test_short_history_makes_higher_timeframes_not_evaluated_not_failed():
    short = zigzag_bars(TREND_DOWN * 3)
    result = analyse_ticker("ABC", short, None, load_policy(), intraday_status="NO_INTRADAY_DATA")
    assert result["readings"]["1mo"]["Status"].startswith("NOT_EVALUATED")


def test_ineligible_ticker_still_gets_its_behavioural_reading():
    daily = long_daily(TREND_DOWN)
    daily[["open", "high", "low", "close"]] = daily[["open", "high", "low", "close"]] / 40  # ~$2 stock
    daily["volume"] = 10_000.0                                                          # illiquid
    cfg = discovery.UltimateConfig()
    signal, outcome = discovery._scan_with_lifecycle("PENNY", daily, cfg, discovery.WyckoffEngine(min_bars=20))
    assert signal is None and outcome["outcome"] == "DROP"
    candidates = discovery._beh001_candidates_for_drop("PENNY", daily, cfg, outcome)
    assert isinstance(candidates, list)
    for c in candidates:
        assert c["Discovery_Outcome"] == "DROP"
        assert c["Discovery_Reason"] == outcome["reason_code"]
