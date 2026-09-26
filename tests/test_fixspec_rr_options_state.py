"""Fix Spec Fix 1b (adjusted, decision D1 approved 24 Sep 2026): rr_options carries a state.

Business rules, for long calls and long puts alike (sign-aware geometry):
- `rr_options_state` names why the number is what it is: PRICED_TARGET_ABOVE_BREAKEVEN (> 0),
  PRICED_TARGET_INSIDE_BREAKEVEN (−1 < rr ≤ 0), STRIKE_BEYOND_TARGET (−1.0 exactly).
- An unpriced mark (missing, ≤ 0, not finite) or a contract with no quote at all is never
  floored to $0.01 and never computed: economics are NOT_EVALUATED with the reason, and
  `rr_options` is None with `rr_options_state` MARK_UNPRICED / QUOTE_MISSING.
- The entry spread is measured against the governed ticket limit
  (`outcome.signal.max_entry_spread_fraction`, read from the registry, never a literal) and
  published as `rr_options_spread_fraction` + `rr_options_tradeability`; a wide spread flags
  the row but does not null a computable number (R11, rank don't gate).
- Every consumer accepts None + state. R:R and its state stay in the research artefacts;
  the Lab book strips rr_ fields by an earlier governed decision, which this fix respects.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from scripts import avshunter_options_intelligence as oi  # noqa: E402
from contracts.lab_control import FINAL_BOOK_FIELDS, write_final_opportunity_book  # noqa: E402
from test_ila_release_coverage_gate import OCC, RUN_ID, _base_signal  # noqa: E402

SCRIPT = ROOT / "scripts" / "avshunter_options_intelligence.py"


def _ctx(direction: str, entry: float, target: float) -> dict:
    return {"spot": entry, "entry": entry, "structural_target": target, "hold_days": 10,
            "direction": direction, "win_prob": 55.0}


def _contract(mark, strike, bid=None, ask=None, **extra) -> dict:
    c = {"mark": mark, "strike": strike, "theta": -0.02, "vega": 0.05, "delta": 0.4, "dte": 30, **extra}
    if bid is not None:
        c["bid"] = bid
    if ask is not None:
        c["ask"] = ask
    return c


@pytest.fixture(autouse=True)
def ticket_limit(monkeypatch):
    monkeypatch.setattr(oi, "ticket_spread_limit_fraction", lambda: 0.10)


# ------------------------------------------------------------------ priced states, both directions
@pytest.mark.parametrize("direction,entry,target,strike,mark,state", [
    ("CALL", 100.0, 120.0, 105.0, 2.0, "PRICED_TARGET_ABOVE_BREAKEVEN"),
    ("PUT", 100.0, 80.0, 95.0, 2.0, "PRICED_TARGET_ABOVE_BREAKEVEN"),
    ("CALL", 100.0, 106.0, 105.0, 2.0, "PRICED_TARGET_INSIDE_BREAKEVEN"),
    ("PUT", 100.0, 94.0, 95.0, 2.0, "PRICED_TARGET_INSIDE_BREAKEVEN"),
    ("CALL", 100.0, 104.0, 105.0, 2.0, "STRIKE_BEYOND_TARGET"),
    ("PUT", 100.0, 96.0, 95.0, 2.0, "STRIKE_BEYOND_TARGET"),
])
def test_priced_rows_state_their_geometry(direction, entry, target, strike, mark, state):
    econ = oi.compute_trade_economics(_contract(mark, strike, bid=1.95, ask=2.05), _ctx(direction, entry, target), {"ivp_label": "FAIR"})
    assert econ["economics_state"] == "EVALUATED"
    assert econ["rr_options_state"] == state
    rr = econ["rr_options"]
    if state == "PRICED_TARGET_ABOVE_BREAKEVEN":
        assert rr > 0
    elif state == "PRICED_TARGET_INSIDE_BREAKEVEN":
        assert -1.0 < rr <= 0
    else:
        assert rr == -1.0
    assert econ["rr_premium_expected"] == rr
    assert econ["rr_options_spread_fraction"] == pytest.approx(0.10 / 2.0)
    assert econ["rr_options_tradeability"] == "WITHIN_TICKET_SPREAD_LIMIT"


def test_target_exactly_at_breakeven_is_inside_breakeven_for_both_directions():
    call = oi.compute_trade_economics(_contract(2.0, 105.0, 1.9, 2.1), _ctx("CALL", 100.0, 107.0), {})
    put = oi.compute_trade_economics(_contract(2.0, 95.0, 1.9, 2.1), _ctx("PUT", 100.0, 93.0), {})
    for econ in (call, put):
        assert econ["rr_options"] == 0.0
        assert econ["rr_options_state"] == "PRICED_TARGET_INSIDE_BREAKEVEN"


# ------------------------------------------------------------------ unpriced: no floor, no number
@pytest.mark.parametrize("mark", [0.0, None, float("nan"), -0.5])
@pytest.mark.parametrize("direction,target,strike", [("CALL", 120.0, 105.0), ("PUT", 80.0, 95.0)])
def test_unpriced_mark_is_not_floored_or_computed(mark, direction, target, strike):
    econ = oi.compute_trade_economics(_contract(mark, strike, bid=0.0, ask=0.0), _ctx(direction, 100.0, target), {"ivp_label": "FAIR"})
    assert econ["economics_state"] == "NOT_EVALUATED"
    assert econ["economics_reason"] == "MARK_UNPRICED"
    assert econ["rr_options"] is None and econ["rr_premium_expected"] is None
    assert econ["rr_options_state"] == "MARK_UNPRICED"
    assert econ["breakeven_price"] is None and econ["option_gain"] is None
    assert econ["rr_options_tradeability"] == "QUOTE_UNAVAILABLE"


@pytest.mark.parametrize("direction,target,strike", [("CALL", 120.0, 105.0), ("PUT", 80.0, 95.0)])
def test_priced_mark_without_any_quote_is_quote_missing(direction, target, strike):
    for contract in (_contract(2.0, strike), _contract(2.0, strike, bid=0.0, ask=0.0), _contract(2.0, strike, bid=None, ask=None)):
        econ = oi.compute_trade_economics(contract, _ctx(direction, 100.0, target), {})
        assert econ["economics_state"] == "NOT_EVALUATED"
        assert econ["economics_reason"] == "QUOTE_MISSING"
        assert econ["rr_options"] is None and econ["rr_options_state"] == "QUOTE_MISSING"
        assert econ["rr_options_tradeability"] == "QUOTE_UNAVAILABLE"


def test_existing_not_evaluated_cases_carry_the_state_too():
    non_directional = oi.compute_trade_economics(_contract(2.0, 100.0, 1.9, 2.1), _ctx("STRANGLE", 100.0, 120.0), {})
    no_target = oi.compute_trade_economics(_contract(2.0, 100.0, 1.9, 2.1), _ctx("CALL", 100.0, None), {})
    for econ in (non_directional, no_target):
        assert econ["economics_state"] == "NOT_EVALUATED"
        assert econ["rr_options"] is None
        assert econ["rr_options_state"] == "NOT_EVALUATED"
        assert econ["rr_options_tradeability"] == "NOT_EVALUATED"


# ------------------------------------------------------------------ spread flags, never nulls
def test_wide_spread_flags_the_row_against_the_ticket_limit_but_keeps_the_number():
    econ = oi.compute_trade_economics(_contract(2.0, 105.0, bid=1.5, ask=2.5), _ctx("CALL", 100.0, 120.0), {})
    assert econ["rr_options"] > 0
    assert econ["rr_options_spread_fraction"] == pytest.approx(0.5)
    assert econ["rr_options_tradeability"] == "ABOVE_TICKET_SPREAD_LIMIT"


def test_ticket_limit_comes_from_the_governed_registry(monkeypatch):
    monkeypatch.undo()
    from avshunter.config.adapters import load_registry
    registry_value = float(load_registry().resolve(date(2026, 9, 24)).get("outcome.signal.max_entry_spread_fraction").value)
    assert oi.ticket_spread_limit_fraction() == registry_value == 0.10
    assert "0.10" not in SCRIPT.read_text(encoding="utf-8").split("def ticket_spread_limit_fraction")[1].split("\ndef ")[0]


def test_ticket_limit_resolves_last_xnys_session_on_a_weekend(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(oi, "_iv_evidence_session", lambda: date(2026, 9, 26))
    oi._TICKET_SPREAD_LIMIT_CACHE.clear()
    assert oi.ticket_spread_limit_fraction() == 0.10


def test_transient_registry_failure_is_not_cached_as_permanent_unavailability(monkeypatch):
    monkeypatch.undo()
    from avshunter.config import adapters
    original = adapters.load_registry
    oi._TICKET_SPREAD_LIMIT_CACHE.clear()
    monkeypatch.setattr(oi, "_iv_evidence_session", lambda: date(2026, 9, 26))

    def unavailable():
        raise OSError("transient registry read failure")

    monkeypatch.setattr(adapters, "load_registry", unavailable)
    assert oi.ticket_spread_limit_fraction() is None
    monkeypatch.setattr(adapters, "load_registry", original)
    assert oi.ticket_spread_limit_fraction() == 0.10


def test_ticket_policy_cache_is_scoped_to_resolved_session(monkeypatch):
    monkeypatch.undo()
    current = {"date": date(2026, 9, 24)}
    monkeypatch.setattr(oi, "_iv_evidence_session", lambda: current["date"])
    oi._TICKET_SPREAD_LIMIT_CACHE.clear()
    assert oi.ticket_spread_limit_fraction() == 0.10
    current["date"] = date(2026, 9, 25)
    assert oi.ticket_spread_limit_fraction() == 0.10
    assert {"2026-09-24", "2026-09-25"} <= set(oi._TICKET_SPREAD_LIMIT_CACHE)


def test_the_dollar_floor_is_gone_from_the_engine():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "if mark <= 0: mark = 0.01" not in source


# ------------------------------------------------------------------ consumers and artefacts
def test_state_travels_with_rr_in_the_research_artefacts_and_stays_out_of_the_lab_book(tmp_path):
    """R:R and its state are research artefacts (options CSV, SuperBrain/EIL, EOD engine).

    The Lab book strips every rr_ field by an earlier governed decision ("neither a v4
    ranking input nor a required/displayed Lab field"); the state follows that decision.
    """
    engine = SCRIPT.read_text(encoding="utf-8")
    assert "'rr_options_state','rr_options_tradeability','rr_options_spread_fraction'" in engine   # CSV pass-through
    superbrain = (ROOT / "scripts" / "avshunter_superbrain_layer.py").read_text(encoding="utf-8")
    assert superbrain.count("rr_options_state") >= 2
    eod = (ROOT / "eod_candidate_engine.py").read_text(encoding="utf-8")
    assert eod.count("rr_options_state") >= 2
    book = write_final_opportunity_book(RUN_ID, [_base_signal(
        contract_symbol=OCC, strike=100, expiry="2099-01-19", dte=30,
        opt__rr_options=None, opt__rr_options_state="MARK_UNPRICED",
    )], {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []}, tmp_path, sync_interpreter=False)
    row = book["rows"][0]
    assert not any(key.startswith("rr_") for key in row)
    assert not any(key.startswith("rr_") for key in FINAL_BOOK_FIELDS if key in row)
