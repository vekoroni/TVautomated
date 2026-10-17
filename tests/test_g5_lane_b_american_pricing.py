"""G5 minimal, item 1 (ACK approved 17 Oct 2026, D1 "Lane B shares the pricing module"): Lane B's decision values are
American with dividends, on the pipeline's own engine.

Design: Enhancements/options_valuation_review/G5_G9_ONE_PRICER_ONE_BASIS_DESIGN_20261017.md (status section).
Before: data/scratch/workaround/avshunter_options_standalone.py priced every contract with its own European
Black-Scholes, no dividend, rate 0.042. On the 16 Oct shortlist 18% of contracts were more than 5% off the market mid
at entry, 444 of 874 were on dividend payers, and 17 of 872 "pays at the half target" decisions flip on one basis.

Business rules:
- Every contract the shortlist can choose from is valued with domain/option_valuation.option_value (American tree,
  the ticker's dividend, the run's observed rate), and the row names the model, rate and dividend it used.
- The European value is kept beside it (*_european) so the change is visible, never silent.
- Rows the shortlist never considers keep the European context value, labelled as such.
- Lane B's own selection rules and output columns are unchanged.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "data" / "scratch" / "workaround" / "avshunter_options_standalone.py"
pytestmark = pytest.mark.skipif(not TOOL.exists(), reason="Lane B tool lives in the local scratch folder")

AS_OF = date(2026, 10, 16)


def _tool():
    spec = importlib.util.spec_from_file_location("lane_b_tool", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _chain(tool):
    rows = []
    for expiry in ("2026-11-20", "2027-01-15"):
        for k in (12.0, 13.0, 14.0, 15.0, 16.0, 17.0):
            for right in ("P", "C"):
                intr = max(k - 14.2, 0) if right == "P" else max(14.2 - k, 0)
                mid = intr + 0.9
                rows.append({"right": right, "strike": k, "expiry": expiry, "spot": 14.2, "bid": mid - 0.05,
                             "ask": mid + 0.05, "iv": 0.62, "delta": -0.5 if right == "P" else 0.5, "gamma": 0.1,
                             "theta": -0.01, "vega": 0.02, "oi": 500, "volume": 50})
    return tool.prepare_chain(pd.DataFrame(rows), AS_OF)


THESIS = pd.Series({"ledger_id": "2026-10-16_TEST_PUT", "ticker": "TEST", "side": "PUT", "q50_sessions": 10,
                    "q80_sessions": 20, "level": 12.58, "half_target": 13.11, "invalidation": 16.36,
                    "source_run": "20261015_225021"})


def _view(tool, monkeypatch, *, dividend=0.02, rate=0.0428):
    monkeypatch.setattr(tool, "MAX_PREMIUM", 5.0)
    monkeypatch.setattr(tool, "PRICING", {"rate": rate, "rate_basis": "MACRO:T3M run 20261015_225021"})
    monkeypatch.setattr(tool, "dividend_for", lambda ticker, spot: {
        "dividend_yield": dividend, "dividend_basis": "TEST_DIVIDEND"})
    c = _chain(tool)
    return tool.thesis_view(c, THESIS, tool.expiry_context(c, "TEST"))


def test_characterisation_the_pre_g5_european_value_is_kept_unchanged(monkeypatch):
    """Pins the pre-G5 formula (European BS at the contract IV, no dividend, rate 0.042, less half the spread). Before
    G5 it was the decision value; it now sits beside the American value as *_european, unchanged."""
    tool = _tool()
    v = _view(tool, monkeypatch)
    yrs = np.maximum(v["sessions_to_expiry"] - 10, 0) / 252
    old = np.maximum(tool.bs_value(np.full(len(v), 13.11), v["strike"], yrs, v["iv"], v["right"].to_numpy())
                     - (v["ask"] - v["bid"]) / 2, 0)
    assert np.allclose(v["value_at_half_target_q50_european"], old)


def test_shortlist_candidates_are_valued_american_with_dividend_and_the_run_rate(monkeypatch):
    from domain.option_valuation import option_value
    tool = _tool()
    v = _view(tool, monkeypatch)
    cand = v[tool.shortlist_candidates(v)]
    assert len(cand) > 0
    for _, r in cand.iterrows():
        years = max(r["sessions_to_expiry"] - 10, 0) / 252
        expected = option_value("PUT", 13.11, r["strike"], years, r["iv"], rate=0.0428, dividend_yield=0.02,
                                style="AMERICAN")["value"]
        assert r["value_at_half_target_q50"] == pytest.approx(max(expected - (r["ask"] - r["bid"]) / 2, 0), rel=1e-6)
        assert r["value_model"] == "AMERICAN_CRR"
        assert r["value_rate_basis"].startswith("MACRO:T3M")
        assert r["value_dividend_basis"] == "TEST_DIVIDEND"


def test_rows_the_shortlist_never_considers_keep_the_labelled_european_value(monkeypatch):
    tool = _tool()
    v = _view(tool, monkeypatch)
    other = v[~tool.shortlist_candidates(v)]
    assert len(other) > 0
    assert (other["value_model"] == "EUROPEAN_BS_NO_DIVIDEND_CONTEXT").all()
    assert np.allclose(other["value_at_half_target_q50"], other["value_at_half_target_q50_european"], equal_nan=True)


def test_an_in_the_money_put_is_worth_at_least_its_european_value(monkeypatch):
    tool = _tool()
    v = _view(tool, monkeypatch, dividend=0.0)
    cand = v[tool.shortlist_candidates(v) & (v["strike"] >= 16.0)]
    assert len(cand) > 0
    assert (cand["value_at_half_target_q50"] >= cand["value_at_half_target_q50_european"] - 1e-9).all()


def test_a_call_on_a_stock_without_dividends_uses_the_exact_closed_form(monkeypatch):
    """An American call on a non-dividend stock is never exercised early, so its value equals the European formula
    exactly; the engine's BSM is used there (17 Oct run time: 689 s with the tree on every row vs 178 s before)."""
    from domain.option_valuation import option_value
    tool = _tool()
    monkeypatch.setattr(tool, "MAX_PREMIUM", 5.0)
    monkeypatch.setattr(tool, "PRICING", {"rate": 0.0428, "rate_basis": "MACRO:T3M run X"})
    monkeypatch.setattr(tool, "dividend_for", lambda ticker, spot: {"dividend_yield": None,
                                                                    "dividend_basis": "ASSUMED_ZERO:NOT_FETCHED"})
    c = _chain(tool)
    call = THESIS.copy()
    call["side"], call["level"], call["half_target"], call["invalidation"] = "CALL", 16.0, 15.1, 13.0
    v = tool.thesis_view(c, call, tool.expiry_context(c, "TEST"))
    cand = v[tool.shortlist_candidates(v)]
    assert len(cand) > 0 and (cand["value_model"] == "BSM_EUROPEAN").all()
    r = cand.iloc[0]
    years = max(r["sessions_to_expiry"] - 10, 0) / 252
    tree = option_value("CALL", 15.1, r["strike"], years, r["iv"], rate=0.0428, dividend_yield=0.0, style="AMERICAN")
    assert r["value_at_half_target_q50"] + (r["ask"] - r["bid"]) / 2 == pytest.approx(tree["value"], rel=2e-3)


def test_the_pay_decision_follows_the_american_value_and_the_european_one_is_kept(monkeypatch):
    tool = _tool()
    v = _view(tool, monkeypatch)
    assert (v["pays_at_half_target_q50"] == (v["ret_half_target_q50"] > 0)).all()
    assert "pays_at_half_target_q50_european" in v and "ret_half_target_q50_european" in v


def test_the_run_rate_is_read_from_the_ledger_s_source_run(tmp_path):
    tool = _tool()
    run = tmp_path / "20261015_225021"
    run.mkdir()
    (run / "macro_snapshot.json").write_text(json.dumps({"rates": {"t3m": 4.28}}))
    ledger = pd.DataFrame([{"source_run": "20261015_225021"}, {"source_run": "20261015_225021"}])
    got = tool.pricing_basis_for_ledger(ledger, runs_dir=tmp_path)
    assert got["rate"] == pytest.approx(0.0428) and got["rate_basis"].startswith("MACRO:T3M")


# --- UAT 17 Oct 2026 (UAT_Report_20261017.txt) ----------------------------------------------------------------------

def test_uat06_with_no_observed_rate_the_governed_fallback_is_used_and_published(monkeypatch):
    """UAT-06: the value used 0.042 while the row said RATE_UNAVAILABLE with a blank rate."""
    from domain.option_valuation import option_value
    tool = _tool()
    v = _view(tool, monkeypatch, rate=None)
    cand = v[tool.shortlist_candidates(v) & (v["value_model"] == "AMERICAN_CRR")]
    r = cand.iloc[0]
    assert r["value_rate"] == pytest.approx(0.0422)
    assert str(r["value_rate_basis"]).startswith("GOVERNED_FALLBACK")
    years = max(r["sessions_to_expiry"] - 10, 0) / 252
    expected = option_value("PUT", 13.11, r["strike"], years, r["iv"], rate=0.0422, dividend_yield=0.02,
                            style="AMERICAN")["value"]
    assert r["value_at_half_target_q50"] == pytest.approx(max(expected - (r["ask"] - r["bid"]) / 2, 0), rel=1e-6)


def test_uat07_dividends_are_read_for_the_analysis_session_not_the_run_date(monkeypatch):
    """UAT-07: a 16 Oct replay asked the dividend cache for 17 Oct (date.today())."""
    tool = _tool()
    seen = []
    monkeypatch.setattr(tool, "AS_OF", AS_OF)
    monkeypatch.setattr(tool, "_DIVIDENDS", {})
    monkeypatch.setattr(tool, "dividend_inputs", lambda t, as_of, spot: seen.append(as_of) or {
        "dividend_yield": 0.01, "dividend_basis": f"TEST {as_of}"})
    tool.dividend_for("TEST", 14.2)
    assert seen == [AS_OF]
