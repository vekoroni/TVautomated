"""Thin-statistics review is uniform across the 1-20 session thesis window (ACK, 18 Sep 2026).

A row with no current actuarial edge used to become a probe candidate only when its horizon was 11_20d; the
same row at 1_5d or 6_10d went to data-insufficient review. Horizon informs, it never decides the class.
A row with no thesis horizon is reported, not defaulted.
"""

from __future__ import annotations

import pytest

import eod_candidate_engine as e

_THIN_STATS_ROW = {
    "direction": "CALL", "governed_direction": "CALL", "entry_spot": 100.0, "invalidation_state": "AVAILABLE",
    "invalidation_spot": 95.0, "signal_type": "NO_EDGE", "actuarial_signal": "NO_EDGE",
    "momentum_tier": "TIER_4_FLAT", "eil_v3_verdict": "MONITOR", "liquidity_state": "EXECUTABLE_NOW",
}


@pytest.mark.parametrize("horizon", ["1_5d", "6_10d", "11_20d"])
def test_thin_statistics_rows_are_probe_candidates_at_every_horizon_in_the_window(horizon):
    status, reason = e._eod_candidate_status({**_THIN_STATS_ROW, "horizon_bucket": horizon}, "WATCH")
    assert (status, reason) == ("EOD_PROBE_CANDIDATE", "SPARSE_ACTUARIAL_THESIS_WINDOW_REVIEW")


@pytest.mark.parametrize("horizon", ["", "unrouted", "blocked"])
def test_a_row_without_a_thesis_horizon_is_reported_not_defaulted(horizon):
    status, reason = e._eod_candidate_status({**_THIN_STATS_ROW, "horizon_bucket": horizon}, "WATCH")
    assert (status, reason) == ("EOD_DATA_INSUFFICIENT_REVIEW", "SPARSE_ACTUARIAL_HORIZON_UNAVAILABLE")
