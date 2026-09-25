"""F1.b — the ledger records the cohort pair (legacy vs shadow contract, with quotes) before the outcome.

Design: Enhancements/research/rca/F1B_LEDGER_SELECTION_PAIR_RCA_AND_DESIGN_20260925.md

Business rules (ACK, 25 Sep 2026):
- The Lab book carries the shadow selector's fields (contract_value_*): they are extracted from the run sources.
- Every candidate event carries selection_pair: both symbols, both quotes with their basis, the shadow's value
  facts and forecast provenance, and prospective_cohort with the registered cohort id.
- Derived values say so (EVENING_CHAIN_DERIVED_BID); unknown stays unknown (SHADOW_UNAVAILABLE, None).
"""

from __future__ import annotations

import csv
import json

from canonical_data.decision_outcome_ledger import (
    PROSPECTIVE_COHORT,
    candidate_events_from_rows,
    selection_pair_from_row,
)
from contracts.lab_control import (
    _enrich_lab_extract_rows_from_run_sources,
    _lab_extract_field_aliases,
)

RUN_ID, NOW = "20260926_061500", "2026-09-26T06:20:00Z"
LEGACY, SHADOW = "AAA261120C00100000", "AAA261120C00095000"
CONTRACT_VALUE_FIELDS = (
    "contract_value_selection_mode", "contract_value_basis", "contract_value_quality_flag",
    "contract_value_r_central", "contract_value_r_cautious", "contract_value_score_choice_symbol",
    "contract_value_best_symbol", "contract_value_best_r_central", "contract_value_alternatives",
    "contract_value_forecast_source", "contract_value_forecast_run_id", "contract_value_forecast_age_sessions",
)


def _base_row(ticker="AAA"):
    return {"ticker": ticker, "thesis_id": f"TH:{ticker}", "governed_direction": "CALL",
            "selected_contract_symbol": LEGACY, "selected_quote_snapshot_id": "QS-1", "final_action": "MONITOR",
            "contract_bid": "2.40", "contract_ask": "2.60", "selected_quote_timestamp_utc": "2026-09-25T20:00:00Z"}


def _shadow_fields(best=SHADOW):
    alternatives = [
        {"symbol": LEGACY, "ask": 2.60, "spread_pct": 0.08, "r_central": 0.05, "quality_flag": "OK"},
        {"symbol": SHADOW, "ask": 4.20, "spread_pct": 0.05, "r_central": 0.12, "quality_flag": "OK"},
    ]
    return {"contract_value_selection_mode": "SHADOW", "contract_value_basis": "SCORE_VALUE_SHADOW",
            "contract_value_quality_flag": "OK", "contract_value_r_central": 0.05, "contract_value_r_cautious": -0.2,
            "contract_value_score_choice_symbol": LEGACY, "contract_value_best_symbol": best,
            "contract_value_best_r_central": 0.12, "contract_value_alternatives": json.dumps(alternatives),
            "contract_value_forecast_source": "L3_ON_DISK", "contract_value_forecast_run_id": "20260925_061649",
            "contract_value_forecast_age_sessions": 1}


# ── Characterisation ───────────────────────────────────────────────────────────────────────────────────────
def test_characterisation_a_row_without_shadow_fields_keeps_every_existing_key_and_says_shadow_unavailable():
    row = _base_row()
    event = candidate_events_from_rows([row], run_id=RUN_ID, occurred_at_utc=NOW, decision_stage="EOD_THESIS")[0]
    for key in ("decision_stage", "direction", "selected_contract_symbol", "selected_quote_snapshot_id",
                "final_action", "target_price", "invalidation_price", "hidden_state_label"):
        assert key in event.payload, key
    pair = event.payload["selection_pair"]
    assert pair["pair_state"] == "SHADOW_UNAVAILABLE"
    assert pair["legacy_contract_symbol"] == LEGACY
    assert pair["shadow_contract_symbol"] is None and pair["symbols_differ"] is None


# ── Business rules ─────────────────────────────────────────────────────────────────────────────────────────
def test_an_evening_row_records_the_full_pair_with_a_derived_shadow_bid():
    pair = selection_pair_from_row({**_base_row(), **_shadow_fields()})
    assert pair["pair_state"] == "PAIR_RECORDED"
    assert pair["legacy_quote_basis"] == "EVENING_CHAIN"
    assert (pair["legacy_bid"], pair["legacy_ask"]) == (2.40, 2.60)
    assert pair["legacy_quote_timestamp_utc"] == "2026-09-25T20:00:00Z"
    assert pair["shadow_contract_symbol"] == SHADOW and pair["symbols_differ"] is True
    assert pair["shadow_quote_basis"] == "EVENING_CHAIN_DERIVED_BID"
    assert pair["shadow_ask"] == 4.20
    assert abs(pair["shadow_bid"] - 4.20 * (2 - 0.05) / (2 + 0.05)) < 1e-9
    assert pair["shadow_quote_timestamp_utc"] == "2026-09-25T20:00:00Z"
    assert pair["shadow_r_central"] == 0.12 and pair["shadow_quality_flag"] == "OK"
    assert pair["shadow_forecast_source"] == "L3_ON_DISK" and pair["shadow_forecast_age_sessions"] == 1


def test_a_morning_row_uses_the_requote_for_the_legacy_contract():
    row = {**_base_row(), **_shadow_fields(), "execution_viability_bid": 2.55, "execution_viability_ask": 2.70,
           "execution_viability_quote_provider_timestamp_utc": "2026-09-26T13:46:00Z"}
    pair = selection_pair_from_row(row)
    assert pair["legacy_quote_basis"] == "MORNING_REQUOTE"
    assert (pair["legacy_bid"], pair["legacy_ask"]) == (2.55, 2.70)
    assert pair["legacy_quote_timestamp_utc"] == "2026-09-26T13:46:00Z"


def test_identical_symbols_are_a_recorded_pair_that_does_not_differ():
    pair = selection_pair_from_row({**_base_row(), **_shadow_fields(best=LEGACY)})
    assert pair["pair_state"] == "PAIR_RECORDED" and pair["symbols_differ"] is False


def test_a_legacy_contract_without_any_quote_is_flagged():
    row = {**_base_row(), **_shadow_fields()}
    row.update(contract_bid="", contract_ask="")
    assert selection_pair_from_row(row)["pair_state"] == "LEGACY_QUOTE_MISSING"


def test_the_event_carries_the_registered_cohort():
    event = candidate_events_from_rows([_base_row()], run_id=RUN_ID, occurred_at_utc=NOW, decision_stage="EOD_THESIS")[0]
    assert event.payload["prospective_cohort"]["cohort_id"] == PROSPECTIVE_COHORT["cohort_id"] == "COHORT_1_SHADOW_SELECTOR_20260925"
    assert event.payload["prospective_cohort"]["variant_counter"] == 15


def test_the_lab_extract_carries_the_shadow_selector_fields(tmp_path):
    aliases = _lab_extract_field_aliases()
    for field in CONTRACT_VALUE_FIELDS:
        assert field in aliases, field
    run_id = "20260926_061500"
    options = tmp_path / run_id / "options"
    options.mkdir(parents=True)
    with (options / f"options_intelligence_{run_id}.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = ["ticker", "trade_idea_id", *CONTRACT_VALUE_FIELDS]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerow({"ticker": "AAA", "trade_idea_id": f"{run_id}:AAA:CALL:NA:NA", **_shadow_fields()})
    rows = [{"ticker": "AAA", "trade_idea_id": f"{run_id}:AAA:CALL:NA:NA"}]
    _enrich_lab_extract_rows_from_run_sources(rows, tmp_path, run_id)
    assert rows[0]["contract_value_best_symbol"] == SHADOW
    assert rows[0]["contract_value_basis"] == "SCORE_VALUE_SHADOW"
    assert rows[0]["contract_value_forecast_source"] == "L3_ON_DISK"
