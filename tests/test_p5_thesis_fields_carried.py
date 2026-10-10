"""Phase 5.1: the thesis's own fields travel Discovery -> EOD -> Morning -> Lab unchanged (one candidate, one story).

Business rule: the fields Discovery's thesis step publishes (the governing candidate's trigger level and identity,
the spine rule and its top timeframe, conflicts, intraday alignment, last event) and Vanguard's context flags are
defined ONCE (contracts/thesis_record.py) and every consumer's field list reads that definition, so no stage can
silently drop or rename them. Phase 0: the card could not show the thesis trigger level or candidate id at all.
"""
import importlib.util
from pathlib import Path

from contracts.thesis_record import THESIS_SPINE_FIELDS, VANGUARD_CONTEXT_FIELDS

ROOT = Path(__file__).resolve().parents[1]


def test_the_definition_contains_the_story_fields():
    assert {"thesis_trigger_level", "thesis_trigger_candidate_id", "thesis__top_timeframe", "thesis__last_event",
            "thesis__last_event_date", "thesis__intraday_alignment"} <= set(THESIS_SPINE_FIELDS)
    assert "vanguard_context_flags" in VANGUARD_CONTEXT_FIELDS


def test_eod_merges_and_publishes_the_definition():
    src = (ROOT / "eod_candidate_engine.py").read_text(encoding="utf-8-sig")
    merge_block = src.split("DISC_MERGE_COLS = [", 1)[1].split("]", 1)[0]
    assert "*THESIS_SPINE_FIELDS" in merge_block
    assert "*VANGUARD_CONTEXT_FIELDS" in src.split("VAN_MERGE_COLS = [", 1)[1].split("]", 1)[0]
    assert "for spine_col in (*THESIS_SPINE_FIELDS, *VANGUARD_CONTEXT_FIELDS):" in src


def test_lab_book_keeps_the_definition():
    from contracts.lab_control import FINAL_BOOK_FIELDS
    assert set(THESIS_SPINE_FIELDS) | set(VANGUARD_CONTEXT_FIELDS) <= set(FINAL_BOOK_FIELDS)


def test_lab_api_compaction_keeps_the_definition():
    spec = importlib.util.spec_from_file_location("ilab", ROOT / "intelligence-lab" / "intelligence_lab.py")
    lab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lab)
    row = {"ticker": "X", **{f: "v" for f in THESIS_SPINE_FIELDS}, **{f: "v" for f in VANGUARD_CONTEXT_FIELDS},
           "ib_state": "ALIGNED"}
    out = lab._compact_lab_signal(row)
    assert set(THESIS_SPINE_FIELDS) | set(VANGUARD_CONTEXT_FIELDS) | {"ib_state"} <= set(out)


def test_the_lab_book_row_carries_the_values_not_only_the_column_names():
    # Phase 5.3 finding (8 Oct 2026): FINAL_BOOK_FIELDS listed the thesis fields but opportunity_book_row never copied
    # them, so the book would publish the columns blank. The Morning intraday build-up (ib_*) travels the same way.
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    from contracts.thesis_record import INTRADAY_BUILDUP_FIELDS
    carried = (*THESIS_SPINE_FIELDS, *VANGUARD_CONTEXT_FIELDS, *INTRADAY_BUILDUP_FIELDS)
    sig = {"ticker": "X", "signal_price": 100.0, **{f: f"v_{f}" for f in carried}}
    row = opportunity_book_row(sig, "RUN", 1)
    assert {f: row.get(f) for f in carried} == {f: f"v_{f}" for f in carried}
    assert set(INTRADAY_BUILDUP_FIELDS) <= set(FINAL_BOOK_FIELDS)
