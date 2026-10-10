"""Phase 5.5: the Morning repairs the CONTRACT inside the thesis; it never changes the thesis.

Business rules (design §10 Morning; ACK E02 6 Oct 2026: the option expresses the ticker assessment and can never
change it):
- A repair alternative whose right (call/put) does not express the thesis side is skipped and labelled
  OFF_THESIS_SIDE, even when its quote passes. Runs 20261001-20261006: 0 of 7,546 Evening alternatives were off-side,
  so this pins today's behaviour at the point where the swap is decided.
- The repair never edits the thesis fields of the row (side, trigger, target, invalidation, governing candidate).
"""
import copy

import morning_gate as mg

PUT_ALT, CALL_ALT = "AAA990119P00095000", "AAA990119C00105000"


def _row():
    return {"ticker": "AAA", "governed_direction": "PUT", "thesis__side": "BEAR", "thesis_trigger_level": 98.0,
            "thesis_trigger_candidate_id": "AAA|1d|UT|2098-12-20", "structural_target": 90.0,
            "invalidation_price": 104.0, "thesis_id": "AAA:PUT:2098-12-31:OLM2",
            "alternative_contract_1": CALL_ALT, "alternative_contract_2": PUT_ALT}


def _patch(monkeypatch):
    monkeypatch.setattr(mg, "_hydrate_live_structure", lambda row, sym: {"selected_contract_symbol": sym,
                                                                         "live_contract_bid": 1.0,
                                                                         "live_contract_ask": 1.05})
    monkeypatch.setattr(mg, "_check_contract", lambda live, thr, row=None: (True, "PASS"))


def test_an_off_side_alternative_is_skipped_even_when_its_quote_passes(monkeypatch):
    _patch(monkeypatch)
    live = mg._try_live_repair_alternatives(_row(), "AAA990119P00100000", 0.25)
    assert live["morning_repair_contract_symbol"] == PUT_ALT
    assert f"{CALL_ALT}:SKIP:OFF_THESIS_SIDE" in live["morning_repair_attempts"]


def test_the_thesis_side_is_read_from_the_thesis_when_the_direction_alias_is_missing(monkeypatch):
    _patch(monkeypatch)
    row = {**_row(), "governed_direction": ""}
    live = mg._try_live_repair_alternatives(row, "AAA990119P00100000", 0.25)
    assert live["morning_repair_contract_symbol"] == PUT_ALT


def test_the_repair_never_edits_the_thesis(monkeypatch):
    _patch(monkeypatch)
    row = _row()
    before = copy.deepcopy(row)
    mg._try_live_repair_alternatives(row, "AAA990119P00100000", 0.25)
    assert row == before
