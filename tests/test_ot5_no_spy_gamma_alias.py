"""Output-trust item 5 (D5-4; ACK approved 9 Oct 2026): SPY's dealer gamma is never shown as the ticker's.

Root cause: the Interpreter's market-structure projection aliased the ticker's gex_regime / gex_score to the macro
packet's SPY dealer_gamma_state / gex_regime_score, and the McMillan advisory layer read the same SPY fields as the
ticker's GEX bucket. Live run 20261008_220129: every one of 2,788 ticker rows carries dealer_gamma_state
NEGATIVE_GAMMA and gex_regime_score 0.3 - so every ticker's "Regime" read NEGATIVE_GAMMA, and McMillan labelled the 692
rows whose own EIL regime was NEUTRAL as AMPLIFYING from SPY's 0.3.

Business rules:
- A ticker's GEX regime and score come only from its own chain (gex_regime / eil_gex_regime, gex_score / eil_gex_score).
- The market-wide SPY value is shown separately, labelled "Market (SPY)".
- Missing ticker GEX is shown as missing (never filled from SPY).
"""
from __future__ import annotations

from pipeline_interpreter.automation_v2.market_structure import MARKET_STRUCTURE_FIELDS, project_market_structure
from types import SimpleNamespace

SPY = {"dealer_gamma_state": "NEGATIVE_GAMMA", "gex_regime_score": 0.3}


def _request(row):
    # the projection reads only these attributes of TickerRunRequest (whose manifest validation is out of scope here)
    return SimpleNamespace(pipeline_row=row, lab_context={}, live_validation={}, macro_context={})


def test_the_ticker_regime_is_its_own_and_spy_is_labelled_market():
    out = project_market_structure(_request({**SPY, "eil_gex_regime": "DAMPENING", "eil_gex_score": 85.0}))
    assert (out["gex_regime"], out["gex_score"]) == ("DAMPENING", 85.0)
    assert (out["market_dealer_gamma_state"], out["market_gex_regime_score"]) == ("NEGATIVE_GAMMA", 0.3)
    assert {"market_dealer_gamma_state", "market_gex_regime_score"} <= set(MARKET_STRUCTURE_FIELDS)


def test_missing_ticker_gex_is_missing_not_spy():
    out = project_market_structure(_request(dict(SPY)))
    assert out["gex_regime"] == "" and out["gex_score"] == ""


def test_mcmillan_gex_bucket_never_reads_spy():
    from mcmillan_advisory_layer import _gex_bucket
    assert _gex_bucket({**SPY, "eil_gex_regime": "NEUTRAL", "eil_gex_score": 60.0}) == "PINNING_GEX"
    assert _gex_bucket({**SPY, "eil_gex_regime": "NEUTRAL", "eil_gex_score": 50.0}) == "UNKNOWN_GEX"
    assert _gex_bucket(dict(SPY)) == "UNKNOWN_GEX"


def test_the_interpreter_report_labels_market_gamma_as_spy():
    src = open("pipeline_interpreter/automation_v2/renderers.py", encoding="utf-8").read()
    assert '("Market (SPY) gamma", "market_dealer_gamma_state")' in src
    assert '("Ticker regime", "gex_regime")' in src
