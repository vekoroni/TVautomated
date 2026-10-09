"""Business rule for bond_macro_intelligence.py (ACK 9 Oct 2026, same rule as the macro producers).

A pre-open run (AVSH_SESSION_CUTOFF set by Run-MacroInputs.ps1) never treats a partial "today"
bar as a finished session: IEF / HYG / LQD / ZN closes stop at the last completed US session.
Without the variable (manual runs) nothing is cut. No network.
"""

from __future__ import annotations

import pandas as pd

import bond_macro_intelligence as bond


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _bars(*days):
    ms = lambda d: int(pd.Timestamp(d).value // 10**6)
    results = [{"t": ms(d), "o": 10.0 + i, "h": 10.5 + i, "l": 9.5 + i, "c": 10.0 + i, "v": 100}
               for i, d in enumerate(days)]
    return {"resultsCount": len(results), "results": results}


def test_a_bar_dated_after_the_last_completed_us_session_is_not_used(monkeypatch):
    monkeypatch.setenv("AVSH_SESSION_CUTOFF", "2026-10-08")
    monkeypatch.setattr(bond.requests, "get",
                        lambda *a, **k: _Response(_bars("2026-10-07", "2026-10-08", "2026-10-09")))
    df = bond.fetch_polygon_ohlcv("HYG")
    assert str(df.index.max()) == "2026-10-08"
    assert df["close"].iloc[-1] == 11.0


def test_without_a_cut_off_every_bar_is_kept(monkeypatch):
    monkeypatch.delenv("AVSH_SESSION_CUTOFF", raising=False)
    monkeypatch.setattr(bond.requests, "get",
                        lambda *a, **k: _Response(_bars("2026-10-07", "2026-10-08", "2026-10-09")))
    df = bond.fetch_polygon_ohlcv("HYG")
    assert str(df.index.max()) == "2026-10-09"


def test_a_cut_that_leaves_no_bar_is_missing_not_an_empty_frame(monkeypatch):
    monkeypatch.setenv("AVSH_SESSION_CUTOFF", "2026-10-06")
    monkeypatch.setattr(bond.requests, "get", lambda *a, **k: _Response(_bars("2026-10-07", "2026-10-08")))
    assert bond.fetch_polygon_ohlcv("HYG") is None
