"""F6: Discovery's Crabel and Wyckoff detail reaches the Lab book (display only; ACK 19 Sep 2026).

Run 20260918_112522: Discovery computed 35 Crabel/Wyckoff fields per candidate (events, next expected event,
transition probabilities at 5/10/20 bars, phase maturity); none reached the book. Discovery owns them; the book
takes them from the run's Discovery file by ticker, fills only what is missing, and flags a missing file.
"""

from __future__ import annotations

import csv
from pathlib import Path

from contracts import lab_control as lab


def _discovery(folder: Path, rows: list[dict]) -> Path:
    path = folder / "discovery_candidates_ultimate_RUN.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({k for r in rows for k in r}))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_the_book_field_list_names_every_structure_detail_field():
    assert len(lab.STRUCTURE_DETAIL_FIELDS) == 35
    for field in (*lab.STRUCTURE_DETAIL_FIELDS, "structure_detail_state"):
        assert field in lab.FINAL_BOOK_FIELDS, field


def test_discovery_detail_is_attached_by_ticker_without_overwriting(tmp_path):
    path = _discovery(tmp_path, [
        {"ticker": "ABC", "wyckoff_validation_next_expected_event": "SOS", "crabel_pattern": "NR7",
         "wyckoff_validation_transition_probability_10_bars": "0.42"},
    ])
    signals = [{"ticker": "ABC", "crabel_pattern": "NR4"}, {"ticker": "XYZ"}]
    out = lab.attach_discovery_structure_detail(signals, path)
    abc, xyz = out
    assert abc["wyckoff_validation_next_expected_event"] == "SOS"
    assert abc["wyckoff_validation_transition_probability_10_bars"] == "0.42"
    assert abc["crabel_pattern"] == "NR4"                     # the row's own value is never overwritten
    assert abc["structure_detail_state"] == "DISCOVERY_DETAIL_ATTACHED"
    assert xyz["structure_detail_state"] == "TICKER_NOT_IN_DISCOVERY"


def test_a_missing_discovery_file_is_flagged(tmp_path):
    out = lab.attach_discovery_structure_detail([{"ticker": "ABC"}], tmp_path / "absent.csv")
    assert out[0]["structure_detail_state"] == "DISCOVERY_FILE_UNAVAILABLE"


def test_the_book_row_carries_the_detail():
    sig = {"ticker": "ABC", "final_direction": "CALL", "wyckoff_validation_next_expected_event": "SOS",
           "structure_detail_state": "DISCOVERY_DETAIL_ATTACHED"}
    row = lab.opportunity_book_row(sig, "RUN-T", 1)
    assert row["wyckoff_validation_next_expected_event"] == "SOS"
    assert row["structure_detail_state"] == "DISCOVERY_DETAIL_ATTACHED"


def test_the_book_writer_attaches_the_detail_before_building():
    import inspect
    source = inspect.getsource(lab.write_final_opportunity_book)
    assert "attach_discovery_structure_detail(" in source
