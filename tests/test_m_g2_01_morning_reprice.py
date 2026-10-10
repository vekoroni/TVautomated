"""M-G2-01 (Morning verification 20261008_220129; ACK approved 10 Oct 2026): every contract is repriced in the Morning.

Root cause: morning_gate._recompute_for_morning_contract returned nothing when the Morning kept the Evening's contract
("the Evening values stand"), so 25 of 35 GO rows showed Evening value estimates beside Morning quotes, unlabelled
(JBLU 1.05x -> about 1.00x, MSFT 1.20x -> 1.00x on the captured Morning inputs). The basis label never reached the
book either (anticipated_contract_basis was not a carried field).

Business rules:
- Unchanged and replacement contracts alike are valued by the one engine on the Morning quote (ask, bid, IV) and the
  Morning spot; the GO check reads that current pays state.
- The frozen Evening value is kept beside it under eod_* names (never overwritten), with the basis and time of each.
- A contract without a usable Morning quote keeps the Evening value, labelled EVENING_REFERENCE:NO_MORNING_QUOTE.
- The basis, time and Evening reference travel to the book and the card.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import morning_gate  # noqa: E402
from domain.anticipated_move import ANTICIPATED_MOVE_FIELDS  # noqa: E402

ROW = {"ticker": "JBLU", "direction": "CALL", "signal_price": 5.0, "contract_symbol": "JBLU261120C00005000",
       "thesis_outcome_level": 5.6, "thesis_outcome_definition": "RANGE_RESISTANCE", "thesis_event_timeframe": "1d",
       "thesis_structure_alignment": "ALIGNED", "thesis_duration_test": "OUTCOME",
       "thesis_duration_status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "thesis_duration_n": 500,
       "thesis_duration_q50_bars": 10, "thesis_duration_q80_bars": 21, "target_reachable_vol_annual": 0.6,
       "planned_hold_sessions": 21, "invalidation_eod": 4.6,
       "anticipated_value_multiple_q50": 1.0543, "anticipated_pays_state": "PAYS",
       "scenario_target_return_on_premium": 0.0543, "anticipated_contract_symbol": "JBLU261120C00005000",
       "anticipated_valued_at_utc": "2026-10-08T20:00:00+00:00"}


def _live(symbol="JBLU261120C00005000", ask=0.62, bid=0.58, iv=0.62):
    return {"live_contract_symbol": symbol, "live_contract_ask": ask, "live_contract_bid": bid, "live_contract_iv": iv,
            "live_price": 5.05, "quote_provider_timestamp_utc": "2026-10-09T13:46:00+00:00"}


def test_an_unchanged_contract_is_repriced_on_the_morning_quote(monkeypatch):
    monkeypatch.setattr(morning_gate, "_today_session", lambda: date(2026, 10, 9))
    out = morning_gate._recompute_for_morning_contract(ROW, _live())
    assert out["anticipated_contract_basis"] == "MORNING_REPRICED:JBLU261120C00005000"
    assert out["anticipated_valued_at_utc"] == "2026-10-09T13:46:00+00:00"
    assert out["valuation_entry_cost_usd_per_share"] > 0.62            # the Morning ask plus the opening fee
    assert out["anticipated_value_multiple_q50"] is not None
    # the frozen Evening value is kept beside it, never overwritten
    assert (out["eod_anticipated_value_multiple_q50"], out["eod_anticipated_pays_state"]) == (1.0543, "PAYS")
    assert out["eod_scenario_target_return_on_premium"] == 0.0543
    assert out["eod_anticipated_valued_at_utc"] == "2026-10-08T20:00:00+00:00"


def test_a_replacement_contract_keeps_its_recomputed_label_and_the_evening_reference(monkeypatch):
    monkeypatch.setattr(morning_gate, "_today_session", lambda: date(2026, 10, 9))
    out = morning_gate._recompute_for_morning_contract(ROW, _live(symbol="JBLU261218C00005000", ask=0.80, bid=0.74))
    assert out["anticipated_contract_basis"] == "MORNING_CONTRACT_RECOMPUTED:JBLU261218C00005000"
    assert out["anticipated_contract_symbol"] == "JBLU261218C00005000"
    assert out["eod_anticipated_value_multiple_q50"] == 1.0543


def test_without_a_morning_quote_the_evening_value_stands_labelled(monkeypatch):
    monkeypatch.setattr(morning_gate, "_today_session", lambda: date(2026, 10, 9))
    out = morning_gate._recompute_for_morning_contract(ROW, _live(ask=None, bid=None))
    assert out == {"anticipated_contract_basis": "EVENING_REFERENCE:NO_MORNING_QUOTE",
                   "eod_anticipated_value_multiple_q50": 1.0543, "eod_anticipated_pays_state": "PAYS",
                   "eod_scenario_target_return_on_premium": 0.0543,
                   "eod_anticipated_valued_at_utc": "2026-10-08T20:00:00+00:00"}


def test_the_basis_time_and_evening_reference_reach_the_book():
    from contracts.lab_control import opportunity_book_row
    new = {"anticipated_contract_basis", "anticipated_valued_at_utc", "eod_anticipated_value_multiple_q50",
           "eod_anticipated_pays_state", "eod_scenario_target_return_on_premium", "eod_anticipated_valued_at_utc"}
    assert new <= set(ANTICIPATED_MOVE_FIELDS)
    row = opportunity_book_row({"ticker": "JBLU", "direction": "CALL", "anticipated_contract_basis": "MORNING_REPRICED:X",
                                "eod_anticipated_value_multiple_q50": 1.0543}, "RUN", 1)
    assert row["anticipated_contract_basis"] == "MORNING_REPRICED:X" and row["eod_anticipated_value_multiple_q50"] == 1.0543


def test_the_evening_valuation_states_its_own_basis_and_time():
    import inspect
    import eod_candidate_engine
    src = inspect.getsource(eod_candidate_engine)
    assert 'candidate["anticipated_contract_basis"] = "EVENING_COMPLETED_SESSION_QUOTE"' in src


def test_the_card_says_which_quote_valued_the_contract():
    card = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    row = {"ticker": "JBLU", "direction": "CALL", "anticipated_contract_basis": "MORNING_REPRICED:JBLU261120C00005000",
           "anticipated_valued_at_utc": "2026-10-09T13:46:00+00:00", "anticipated_value_multiple_q50": 0.99,
           "eod_anticipated_value_multiple_q50": 1.0543, "scenario_target_return_on_premium": -0.01,
           "scenario_exit_sessions": 10}
    out = subprocess.run(["node"], input=card + f"\nconst h = renderTradeCard({json.dumps(row)});\n"
                         "console.log(JSON.stringify({m: h.includes('Morning quote 2026-10-09T13:46'),"
                         " e: h.includes('Evening reference 1.05')}));",
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"m": True, "e": True}


def test_the_does_not_pay_message_quotes_the_morning_value_not_the_evening_one():
    import inspect
    src = inspect.getsource(morning_gate)
    assert ('f"The anticipated move values this contract at {out.get(\'anticipated_value_multiple_q50\') '
            'or row.get(\'anticipated_value_multiple_q50\')}x') in src
