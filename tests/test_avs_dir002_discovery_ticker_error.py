"""DIR-002 DSC-20: one ticker's scan exception is a visible ERROR lifecycle row;
the run continues and reconciliation still holds."""
import pandas as pd

import avshunter_discovery_ULTIMATE as discovery


def test_scan_exception_becomes_error_outcome(monkeypatch):
    def boom(*args, **kwargs):
        raise ZeroDivisionError("synthetic")

    monkeypatch.setattr(discovery, "scan_ticker_ultimate", boom)
    signal, outcome = discovery._scan_with_lifecycle("ERRT", pd.DataFrame(), None, None)
    assert signal is None
    assert outcome["outcome"] == "ERROR"
    assert outcome["lifecycle_state"] == "ERROR_STAGE"
    assert outcome["reason_code"] == "SCAN_EXCEPTION_ZeroDivisionError"


def test_reason_code_from_eligibility_is_preserved(monkeypatch):
    def reject(ticker, df, cfg, engine, *, eligibility_diagnostic):
        eligibility_diagnostic["reason_code"] = "ELIG_PRICE_RANGE"
        return None

    monkeypatch.setattr(discovery, "scan_ticker_ultimate", reject)
    signal, outcome = discovery._scan_with_lifecycle("LOWP", pd.DataFrame(), None, None)
    assert signal is None
    assert outcome["outcome"] == "DROP"
    assert outcome["reason_code"] == "ELIG_PRICE_RANGE"
