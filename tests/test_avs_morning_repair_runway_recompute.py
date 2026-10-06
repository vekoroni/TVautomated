"""Morning contract repair (ACK 5 Oct 2026, fixes E and F).

Run 20261005_072245: the Morning repair swapped the contract on 413 rows (141 in lanes A/B). The anticipated value,
time fit, pays verdict and earnings-inside-contract stayed as computed for the Evening contract (SYNA: an
18 Dec 125 call's 13.8x shown beside a 16 Oct 110 call). And the repair could choose a contract that expires before
the move is due (34 of 141 before q80, 7 before the median time) - against "buy more runway than the move".
Business rules:
- F: a repair alternative that expires before the evidence runway (q80 hold) is skipped (SHORT_RUNWAY).
- E: when the Morning uses a different contract, the anticipated move and the earnings timing are recomputed for
  that contract, and the GO check reads the recomputed pays verdict.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import morning_gate


def test_option_symbol_expiry_is_read():
    assert morning_gate._occ_expiry("SYNA261016C00110000") == date(2026, 10, 16)
    assert morning_gate._occ_expiry("NOT_A_SYMBOL") is None


def test_short_runway_alternatives_are_skipped(monkeypatch):
    tried = []

    def hydrate(row, symbol):
        tried.append(symbol)
        return {"selected_contract_symbol": symbol}

    monkeypatch.setattr(morning_gate, "_hydrate_live_structure", hydrate)
    monkeypatch.setattr(morning_gate, "_check_contract", lambda live, spread, row: (True, "PASS"))
    monkeypatch.setattr(morning_gate, "_today_session", lambda: date(2026, 10, 5))
    row = {"alternative_contract_1": "SYNA261016C00110000", "alternative_contract_2": "SYNA261218C00125000",
           "planned_hold_sessions": 21, "planned_hold_source": "DURATION_EVIDENCE_Q80:1d:n=900"}
    live = morning_gate._try_live_repair_alternatives(row, "SYNA261120C00120000", 0.18)
    assert tried == ["SYNA261218C00125000"]                       # 16 Oct (9 sessions) < 21-session runway
    assert live["morning_repair_contract_symbol"] == "SYNA261218C00125000"
    assert "SYNA261016C00110000:SKIP:SHORT_RUNWAY" in live["morning_repair_attempts"]


def test_without_an_evidence_runway_no_alternative_is_filtered(monkeypatch):
    monkeypatch.setattr(morning_gate, "_hydrate_live_structure", lambda row, s: {"selected_contract_symbol": s})
    monkeypatch.setattr(morning_gate, "_check_contract", lambda live, spread, row: (True, "PASS"))
    monkeypatch.setattr(morning_gate, "_today_session", lambda: date(2026, 10, 5))
    row = {"alternative_contract_1": "SYNA261016C00110000", "planned_hold_source": "NO_EVIDENCE_HOLD"}
    live = morning_gate._try_live_repair_alternatives(row, "", 0.18)
    assert live["morning_repair_contract_symbol"] == "SYNA261016C00110000"


ROW = {"ticker": "SYNA", "direction": "CALL", "signal_price": 100.0, "contract_symbol": "SYNA261218C00125000",
       "thesis_outcome_level": 110.0, "thesis_outcome_definition": "RANGE_RESISTANCE", "thesis_event_timeframe": "1d",
       "thesis_structure_alignment": "ALIGNED", "thesis_duration_test": "OUTCOME",
       "thesis_duration_status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "thesis_duration_n": 500,
       "thesis_duration_q50_bars": 10, "thesis_duration_q80_bars": 21, "target_reachable_vol_annual": 0.5,
       "planned_hold_sessions": 21, "bar_data_asof": "2026-10-02", "anticipated_value_multiple_q50": 13.8,
       "earnings_state": "SCHEDULED", "earnings_date": "2026-11-05", "earnings_report_time": "UNKNOWN"}


def test_repaired_contract_gets_its_own_anticipated_move_and_earnings_timing():
    live = {"live_contract_symbol": "SYNA261016C00110000", "live_contract_ask": 2.0, "live_contract_iv": 0.6}
    out = morning_gate._recompute_for_morning_contract(ROW, live)
    assert out["anticipated_contract_basis"] == "MORNING_CONTRACT_RECOMPUTED:SYNA261016C00110000"
    assert out["anticipated_value_multiple_q50"] is None                   # expires before the 10-session median
    assert out["anticipated_time_fit"] == "CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME"
    assert out["earnings_inside_expiry"] is False                          # 5 Nov is after the 16 Oct expiry


def test_unchanged_contract_is_not_recomputed():
    live = {"live_contract_symbol": "SYNA261218C00125000", "live_contract_ask": 4.0, "live_contract_iv": 0.6}
    assert morning_gate._recompute_for_morning_contract(ROW, live) == {}


def test_the_go_check_reads_the_recomputed_pays_verdict_and_evening_carries_the_inputs():
    import inspect
    import eod_candidate_engine
    src = inspect.getsource(morning_gate)
    assert '_u(out.get("anticipated_pays_state") or row.get("anticipated_pays_state"))' in src
    eod = inspect.getsource(eod_candidate_engine)
    for field in ("thesis_event_timeframe", "thesis_structure_alignment", "target_reachable_vol_annual"):
        assert f'"{field}"' in eod
