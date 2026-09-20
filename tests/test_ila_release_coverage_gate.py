"""AVS-ILA-001 (audit/intelligence_lab/, 20 Sep 2026), root cause ILA-RC-08: "No release-time
field coverage gate ties producers to the Lab presentation contract. Effect: Schema drift
reaches production unnoticed." (section 8, severity P0; required fix section 9.3 item 17:
"Add run-level coverage reconciliation by stage and prevent release when required-field
coverage regresses"; acceptance test section 10 item 9.)

Scope note: ILA-RC-01 through ILA-RC-07 each turned out to share one structural pattern - a
field is real, computed, upstream data, but contracts/lab_control.py's FINAL_BOOK_FIELDS
allow-list and/or opportunity_book_row's row-construction dict silently drop it before it
ever reaches the published book (ILA-RC-03 Morning live/MSI fields, ILA-RC-07 PCR advisory
fields), or the Lab's own alias projection points at the wrong name (ILA-RC-01/02). This gate
targets exactly that recurrence class for the fields verified end-to-end this session. It
does NOT attempt the full canonical presentation-DTO redesign (section 9.1 items 1-2), which
is separate, larger design work.

Deliberately excluded from this gate: readiness_stage / readiness_label / sb_current_stage.
While building this gate, found that intelligence-lab/intelligence_lab.py live-recomputes
sb_current_stage at serve time (_compute_stage_ladder) from trigger/campaign/EIL/execution
verdicts, independently of the governed readiness_stage field (which opportunity_book_row
currently hardcodes blank regardless of input) - a possible dual-ownership defect (design
rule R2, "one owner per fact") that needs its own root-cause investigation before any gate
asserts what "correct" coverage looks like for it. Also excluded: the ILA-RC-06 Interpreter
overlay fields (interpreter_bundle_status, interpreter_assessment_status, etc.), which are
applied at serve time via a different mechanism (contracts/lab_evidence_overlay.py) and are
covered by their own gate below.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.direction_governance import resolve_governed_direction
from contracts.lab_control import FINAL_BOOK_FIELDS, write_final_opportunity_book
from contracts.lab_evidence_overlay import ASSESSMENT_FIELDS


RUN_ID = "20990101_150000"
OCC = "O:AAA990119C00100000"

# The row's own published key name for each field the Lab depends on, grouped by the audit
# root cause whose fix relies on it reaching the final book. Extend this set whenever a
# future ILA fix adds a new governed field the Lab reads directly from the book.
REQUIRED_GOVERNED_FIELDS = {
    # ILA-RC-02: GARCH / Q-Omega forecast fields; fwdVol gates the whole Q-Omega pane.
    "garch_method", "garch_forecast_vol", "garch_iv_tailwind_score",
    "garch_jump_risk_flag", "garch_forecast_confidence",
    "garch_expected_move_1_5d", "garch_expected_move_6_10d", "garch_expected_move_11_20d",
    "garch_price_bars_used",
    # ILA-RC-03: Morning live price / MSI market-structure evidence.
    "live_price", "live_vwap", "quote_timestamp_utc",
    "ms_profile_type", "ms_lifecycle", "ms_quality_class", "ms_reason_code",
    "ms_developing_poc", "ms_final_poc", "ms_value_area_low", "ms_value_area_high",
    # ILA-RC-07: PCR advisory-authority context.
    "pcr_signal", "pcr_direction_conflict_status", "pcr_direction_conflict_reason",
    "pcr_confidence_weight",
}

# ILA-RC-06: the Interpreter-lifecycle overlay fields use a separate contract
# (contracts/lab_evidence_overlay.py's ASSESSMENT_FIELDS), applied at serve time rather than
# published by write_final_opportunity_book. Gated separately below.
REQUIRED_OVERLAY_FIELDS = {
    "interpreter_bundle_status", "interpreter_bundle_prepared_utc",
    "interpreter_assessment_status",
}


def test_every_lab_dependent_field_is_allow_listed_in_the_final_book_contract():
    missing = REQUIRED_GOVERNED_FIELDS - set(FINAL_BOOK_FIELDS)
    assert not missing, (
        f"Field(s) the Lab depends on are missing from FINAL_BOOK_FIELDS and will never "
        f"reach the published book regardless of upstream data: {sorted(missing)}"
    )


def test_every_lab_dependent_overlay_field_is_allow_listed_in_the_overlay_contract():
    missing = REQUIRED_OVERLAY_FIELDS - set(ASSESSMENT_FIELDS)
    assert not missing, (
        f"Overlay field(s) the Lab depends on are missing from ASSESSMENT_FIELDS and will "
        f"be rejected by validate_overlay regardless of what the producer writes: "
        f"{sorted(missing)}"
    )


def _write_csv(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def _base_signal(**overrides):
    direction = resolve_governed_direction(
        ticker="AAA",
        run_id=RUN_ID,
        discovery_direction="CALL",
        governed_direction="CALL",
        governed_basis="test=CALL",
        row={},
        decided_at_utc="2099-01-01T01:01:01+00:00",
    )
    row = {
        "ticker": "AAA",
        "canonical_direction": "CALL",
        "lab_verdict": "MORNING_VALIDATION_REQUIRED",
        "lab_tradeable": False,
        "morning_lab_alignment_status": "NO_MORNING_BATON",
        "priority_score": 70,
        "rr": 2.0,
        "invalidation_spot": 95.0,
        "invalidation_state": "AVAILABLE",
        "invalidation_source": "TEST_GOVERNED_THESIS",
        **direction,
    }
    row.update(overrides)
    return row


def test_every_required_field_survives_a_fresh_publish_when_the_upstream_data_exists(tmp_path):
    run = tmp_path / RUN_ID
    _write_csv(
        run / "qomega" / f"garch_forecasts_{RUN_ID}.csv",
        {
            "ticker": "AAA",
            "l3_method": "GARCH",
            "l3_forward_realised_vol": 0.24,
            "l3_iv_tailwind_score": -0.05,
            "l3_jump_risk_flag": False,
            "l3_vol_forecast_conf": 82,
            "l3_expected_move_1_5d": 0.03,
            "l3_expected_move_6_10d": 0.05,
            "l3_expected_move_11_20d": 0.08,
            "l3_n_bars": 240,
        },
    )
    book = write_final_opportunity_book(
        RUN_ID,
        [_base_signal(
            contract_symbol=OCC,
            strike=100,
            expiry="2099-01-19",
            dte=30,
            monetisability_status="COMPLETE",
            monetisability_state="MONETISABLE",
            monetisability_contract_symbol=OCC,
            live_price=30.68,
            live_vwap=30.6867,
            quote_timestamp_utc="2026-09-18T15:41:30Z",
            ms_profile_type="SINGLE_DISTRIBUTION",
            ms_lifecycle="MS_NONE",
            ms_quality_class="FIVE_MINUTE_ESTIMATED",
            ms_reason_code="NO_QUALIFYING_DOUBLE_DISTRIBUTION",
            ms_developing_poc=30.68,
            ms_final_poc=30.68,
            ms_value_area_low=30.36,
            ms_value_area_high=30.80,
            pcr_signal="BULLISH",
            pcr_direction_conflict_status="PCR_CONFIRMS_REDUCED_CONFIDENCE",
            pcr_direction_conflict_reason="OI PCR confirms CALL with reduced confidence",
            pcr_confidence_weight=0.6,
        )],
        {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []},
        tmp_path,
        sync_interpreter=False,
    )
    row = book["rows"][0]

    def _is_missing(value) -> bool:
        if value is None:
            return True
        text = str(value).strip()
        return text == "" or text.lower() in {"nan", "none"}

    dropped = [field for field in sorted(REQUIRED_GOVERNED_FIELDS) if _is_missing(row.get(field))]
    assert not dropped, (
        f"Field(s) present in upstream data were dropped before reaching the published "
        f"book row: {dropped}"
    )
