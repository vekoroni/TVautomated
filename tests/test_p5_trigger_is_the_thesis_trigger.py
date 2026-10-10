"""Phase 5.2: the trigger on the card is the thesis's own trigger (one candidate, one story).

Business rules:
- EOD and the Lab set trigger_price from thesis_trigger_level (source THESIS_TRIGGER_LEVEL).
- The Wall-Break break level is kept as legacy_wbs_trigger_price / legacy_wbs_trigger_source; it never becomes the
  trigger (Phase 0: trigger_price came from Wall-Break on 1,039 of 1,039 rows and differed from the thesis
  candidate's own trigger on 1,038).
- No thesis trigger -> trigger_price stays missing with source NOT_AVAILABLE_NO_THESIS_TRIGGER (never borrowed).
"""
import eod_candidate_engine as eod
from contracts import lab_control as lc


def test_eod_trigger_comes_from_the_thesis():
    out = eod._governed_trigger_fields({"thesis_trigger_level": 101.5, "wbs_phase_c_trigger": 97.0,
                                        "trigger_price": ""})
    assert out["trigger_price"] == 101.5 and out["trigger_price_source"] == "THESIS_TRIGGER_LEVEL"
    assert out["legacy_wbs_trigger_price"] == 97.0
    assert out["legacy_wbs_trigger_source"] == "WBS_PHASE_C_CONFIRMED_BREAK"


def test_eod_without_a_thesis_trigger_stays_missing():
    out = eod._governed_trigger_fields({"wbs_phase_c_trigger": 97.0})
    assert out["trigger_price"] is None and out["trigger_price_source"] == "NOT_AVAILABLE_NO_THESIS_TRIGGER"
    assert out["legacy_wbs_trigger_price"] == 97.0


def test_lab_never_fills_the_trigger_from_wall_break():
    row = {"trigger_price": None, "wbs_phase_c_trigger": 97.0, "wbs_phase_b_trigger": 95.0}
    prov = {}
    lc._recompute_governed_lab_fields(row, prov)
    assert row.get("trigger_price") in (None, "")
    assert row.get("legacy_wbs_trigger_price") == 97.0


def test_lab_fills_the_trigger_from_the_thesis():
    row = {"trigger_price": None, "thesis_trigger_level": 101.5, "wbs_phase_c_trigger": 97.0}
    lc._recompute_governed_lab_fields(row, {})
    assert row["trigger_price"] == 101.5 and row["trigger_price_source"] == "THESIS_TRIGGER_LEVEL"


def test_lab_card_trigger_never_falls_back_to_other_sources():
    sig = {"wbs_phase_c_trigger": 97.0, "eod__wbs_phase_b_trigger": 95.0, "scenario_entry_trigger": 96.0}
    assert lc._trigger_price(sig) in (None, "")
    assert lc._trigger_price({**sig, "thesis_trigger_level": 101.5}) == 101.5
