"""Quote evidence pointer (ACK 17 Sep 2026).

Root cause: a Morning row can display the morning quote while ``selected_quote_dataset_id`` still identifies the
evening dataset — after the 17 Sep rerun that was 661 of 1,333 rows (terminal replay, invalid quote identity, or a
reused observation). Worker 3 compares the Lab row's quote with the dataset the row points to and isolates any
disagreement, so 18% of tickers lost their prepared evidence.

Rule: the pointer identifies the dataset holding the quote the row displays. When the row's contract quote is the
morning quote and a morning quote dataset exists, the pointer is that dataset; otherwise it is left untouched.
"""

from __future__ import annotations

import morning_gate

EVENING = "evening-dataset"
MORNING = "morning-dataset"


def row(**overrides) -> dict:
    values = {"ticker": "CLX", "selected_quote_dataset_id": EVENING, "morning_quote_dataset_id": MORNING,
              "contract_bid": 2.6, "contract_ask": 2.75, "morning_contract_bid": 2.6, "morning_contract_ask": 2.75}
    values.update(overrides)
    return values


def test_pointer_follows_the_displayed_morning_quote():
    result = row()
    morning_gate._align_selected_quote_dataset(result)
    assert result["selected_quote_dataset_id"] == MORNING


def test_pointer_untouched_when_the_row_shows_a_different_quote():
    result = row(contract_bid=3.0, contract_ask=3.4)
    morning_gate._align_selected_quote_dataset(result)
    assert result["selected_quote_dataset_id"] == EVENING


def test_pointer_untouched_without_a_morning_dataset_or_quote():
    for overrides in ({"morning_quote_dataset_id": ""}, {"morning_contract_bid": None},
                      {"morning_contract_ask": ""}, {"contract_bid": None}):
        result = row(**overrides)
        morning_gate._align_selected_quote_dataset(result)
        assert result["selected_quote_dataset_id"] == EVENING, overrides


def test_pointer_set_when_the_row_has_no_pointer_yet():
    result = row(selected_quote_dataset_id="")
    morning_gate._align_selected_quote_dataset(result)
    assert result["selected_quote_dataset_id"] == MORNING


def test_alignment_runs_after_morning_persistence(monkeypatch):
    """Every persistence outcome — including the early returns — leaves a consistent pointer."""
    seen = {}

    def fake_persist(result, *_args, **_kwargs):
        result["morning_liquidity_persistence_status"] = "TERMINAL_REPLAY_REUSED"   # early return, pointer untouched

    monkeypatch.setattr(morning_gate, "_persist_morning_liquidity_result", fake_persist)
    result = row()
    fake_persist(result, "run", None, None)
    morning_gate._align_selected_quote_dataset(result)
    seen["pointer"] = result["selected_quote_dataset_id"]
    assert seen["pointer"] == MORNING
