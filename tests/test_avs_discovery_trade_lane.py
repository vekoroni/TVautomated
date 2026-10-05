"""Discovery stamps the trade lane and drops tickers with no live setup (ACK 4 Oct 2026).

"Discovery should still do its job but there should be still drops based on the new rules."
Business rules:
- Every analysed ticker carries trade_lane (A / B / C) with the setup that set it and its measured hit rates.
- A ticker with no live BEH-001 setup is dropped for this run as NO_LIVE_SETUP (it re-enters next run);
  its behavioural candidates are still published, read once.
- Lanes A, B and C all continue downstream: C stays visible for human judgement.
"""
import pandas as pd

import avshunter_discovery_ULTIMATE as discovery
from test_beh001_no_upstream_constraints import long_daily
from test_beh001_sequences import TREND_DOWN


def test_analysed_ticker_carries_its_trade_lane():
    signal, outcome = discovery._scan_with_lifecycle("LANE", long_daily(TREND_DOWN), discovery.UltimateConfig(),
                                                     discovery.WyckoffEngine(min_bars=20))
    assert outcome is None or outcome["reason_code"] == "NO_LIVE_SETUP"
    if signal is not None:
        assert signal["trade_lane"] in {"A", "B", "C"}
        assert signal["trade_lane_version"] == "beh001_lanes_v1"


def _stub(lane):
    def scan(ticker, df, cfg, engine, *, eligibility_diagnostic):
        return {"ticker": ticker, "trade_lane": lane, "_beh001_candidates": [{"Candidate_ID": "X"}]}
    return scan


def test_no_live_setup_drops_with_its_candidates(monkeypatch):
    monkeypatch.setattr(discovery, "scan_ticker_ultimate", _stub("NO_LIVE_SETUP"))
    signal, outcome = discovery._scan_with_lifecycle("NONE", pd.DataFrame(), None, None)
    assert signal is None
    assert outcome["outcome"] == "DROP" and outcome["reason_code"] == "NO_LIVE_SETUP"
    assert outcome["_beh001_candidates"] == [{"Candidate_ID": "X"}]


def test_lane_c_continues_downstream(monkeypatch):
    monkeypatch.setattr(discovery, "scan_ticker_ultimate", _stub("C"))
    signal, outcome = discovery._scan_with_lifecycle("WATCH", pd.DataFrame(), None, None)
    assert outcome is None and signal["trade_lane"] == "C"


def test_intraday_only_ticker_drops_with_its_candidates(monkeypatch):
    monkeypatch.setattr(discovery, "scan_ticker_ultimate", _stub("INTRADAY_ONLY_UNTESTED"))
    signal, outcome = discovery._scan_with_lifecycle("THIN", pd.DataFrame(), None, None)
    assert signal is None and outcome["reason_code"] == "INTRADAY_ONLY_UNTESTED"
    assert outcome["_beh001_candidates"] == [{"Candidate_ID": "X"}]
