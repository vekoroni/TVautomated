from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.direction_governance import resolve_governed_direction
from contracts.lab_control import opportunity_book_row, write_final_opportunity_book


RUN_ID = "20990101_140000"
OCC = "O:AAA990119C00100000"


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


def _load_lab_module():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("intelligence_lab_governed_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_alternative_contract_is_not_promoted_to_selected_contract():
    row = opportunity_book_row(
        _base_signal(
            alternative_contract_1=OCC,
            strike=100,
            expiry="2099-01-19",
            dte=30,
            rr_premium_expected=2.5,
        ),
        RUN_ID,
        1,
    )
    assert row["contract_symbol"] == ""
    assert row["contract_data_state"] == "NOT_APPLICABLE_NO_SELECTED_CONTRACT"
    assert row["strike"] == ""
    assert row["expiry"] == ""
    assert row["dte"] == ""
    assert row["rr_predicted"] == ""
    assert row["rr_underlying"] == 2.0


def test_trigger_quality_never_falls_back_to_numeric_trigger_score():
    missing = opportunity_book_row(
        _base_signal(trigger_quality="", trigger_score=55.0), RUN_ID, 1
    )
    explicit_none = opportunity_book_row(
        _base_signal(trigger_quality="NONE", trigger_score=55.0), RUN_ID, 1
    )

    assert missing["trigger_quality"] == ""
    assert explicit_none["trigger_quality"] == "NONE"
    assert float(explicit_none["trigger_score"]) == 55.0


def test_lab_blocks_actionable_row_without_governed_direction_lineage():
    row = opportunity_book_row(
        {
            "ticker": "BAD",
            "lab_verdict": "GO_LIMIT",
            "lab_tradeable": True,
            "final_action": "BUY_SMALL",
            "direction": "CALL",
        },
        RUN_ID,
        1,
    )
    assert row["lab_tradeable"] is False
    assert row["lab_verdict"] == "BLOCKED"
    assert row["final_action"] == "BLOCK"
    assert row["direction_integrity_status"] == "FAIL"
    assert row["lab_execution_status"] == "DIRECTION_INTEGRITY_FAILED"


def test_governed_book_preserves_owned_ev3_trigger_spread_and_garch_fields(tmp_path):
    run = tmp_path / RUN_ID
    _write_csv(
        run / "execution" / f"execution_v3_5_{RUN_ID}.csv",
        {"ticker": "AAA", "trigger_primary": "BREAKOUT", "trigger_codes": "BREAKOUT|VOLUME", "trigger_score": 81},
    )
    _write_csv(
        run / "superbrain" / f"eil_enriched_{RUN_ID}.csv",
        {
            "ticker": "AAA",
            "ev3_status": "EVALUATED_SHADOW",
            "ev3_reason_code": "SHADOW_ONLY",
            "ev3_structure": "LONG_SINGLE",
            "ev3_contract_symbol": OCC,
            "ev3_ev_conservative_return": 0.12,
            "ev3_ev_lower_bound_return": 0.04,
        },
    )
    _write_csv(
        run / "options" / f"options_intelligence_{RUN_ID}.csv",
        {
            "ticker": "AAA", "contract_symbol": OCC,
            "contract_spread_pct": 0.07, "rr_premium_expected": 1.8,
        },
    )
    _write_csv(
        run / "qomega" / f"garch_forecasts_{RUN_ID}.csv",
        {
            "ticker": "AAA",
            "l3_method": "GARCH",
            "l3_forward_realised_vol": 0.24,
            "l3_iv_tailwind_score": -0.05,
            "l3_jump_risk_flag": False,
            "l3_vol_forecast_conf": 82,
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
        )],
        {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []},
        tmp_path,
        sync_interpreter=False,
    )
    row = book["rows"][0]

    assert row["lab_schema_version"] == "lab_signal_book_v4"
    assert row["pipeline_mode"] == "EOD"
    assert row["contract_data_state"] == "AVAILABLE"
    assert row["spread_pct"] == "0.07"
    assert "rr_premium_expected" not in row
    assert "rr_predicted" not in row
    assert row["ev3_status"] == "EVALUATED_SHADOW"
    assert row["ev3_ev_conservative_return"] == "0.12"
    assert row["economics_comparable"] is True
    assert row["selected_structure_id"] == row["monetisability_evaluation_id"]
    assert row["selected_structure_id"] == row["ev3_evaluation_id"]
    assert "rr_contract_symbol" not in row
    assert row["ev3_data_state"] == "AVAILABLE"
    assert row["trigger_primary"] == "BREAKOUT"
    assert row["trigger_data_state"] == "AVAILABLE"
    assert row["garch_method"] == "GARCH"
    assert row["garch_data_state"] == "AVAILABLE"
    assert row["macro_data_role"] == "ADVISORY_ONLY"
    assert row["morning_data_state"] == "NOT_RUN_EOD"
    provenance = json.loads(row["field_provenance_json"])
    assert provenance["trigger_primary"] == "execution_v3_5"
    assert provenance["ev3_status"] == "eil_enriched"
    assert provenance["spread_pct"] == "options_intelligence"
    assert provenance["garch_method"] == "garch_forecasts"
    assert book["reconciliation"]["input_rows"] == 1
    assert book["reconciliation"]["output_rows"] == 1
    assert book["reconciliation"]["duplicate_trade_idea_ids"] == 0
    assert book["reconciliation"]["economics_mismatch_rows"] == 0


def test_lab_publication_converts_pandas_style_nan_to_json_null(tmp_path):
    book = write_final_opportunity_book(
        RUN_ID,
        [_base_signal(
            catalyst_date=float("nan"),
            catalyst_direction_bias=float("nan"),
            catalyst_event_status=float("nan"),
            contract_changed=float("nan"),
            executable_now=float("nan"),
            legacy_nested={"missing": float("nan")},
        )],
        {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []},
        tmp_path,
        sync_interpreter=False,
    )

    raw = Path(book["json_path"]).read_text(encoding="utf-8")

    def reject_non_standard_constant(value: str):
        raise AssertionError(f"non-standard JSON constant: {value}")

    payload = json.loads(raw, parse_constant=reject_non_standard_constant)
    row = payload["rows"][0]
    assert row["catalyst_date"] is None
    assert row["catalyst_direction_bias"] is None
    assert row["catalyst_event_status"] is None
    assert row["contract_changed"] is None
    assert row["executable_now"] is None
    assert json.loads(row["source_payload_json"])["legacy_nested"]["missing"] is None
    assert book["rows"][0] == row

    with Path(book["csv_path"]).open("r", encoding="utf-8", newline="") as fh:
        csv_row = next(csv.DictReader(fh))
    assert csv_row["catalyst_date"] == ""
    assert csv_row["contract_changed"] == ""


def test_cross_contract_ev_is_fail_closed_and_never_populates_selected_contract_ev():
    row = opportunity_book_row(
        _base_signal(
            lab_verdict="GO_LIMIT",
            lab_tradeable=True,
            contract_symbol="O:AAA990119C00100000",
            instrument="LONG_CALL",
            strike=100,
            expiry="2099-01-19",
            dte=30,
            rr_premium_expected=3.5,
            monetisability_status="COMPLETE",
            monetisability_state="MONETISABLE",
            monetisability_contract_symbol="O:AAA990119C00100000",
            ev3_status="EVALUATED_SHADOW",
            ev3_structure="BULL_CALL_DEBIT",
            ev3_contract_symbol=(
                "BULL_CALL_DEBIT:AAA990119C00100000/AAA990119C00105000"
            ),
            ev3_ev_conservative_return=-0.25,
        ),
        RUN_ID,
        1,
    )

    assert row["economics_comparable"] is True
    assert row["economics_mismatch_reason"] == ""
    assert row["selected_contract_symbols"] == '["AAA990119C00100000"]'
    assert row["ev3_contract_symbol"].startswith("BULL_CALL_DEBIT:")
    assert row["ev_predicted"] == ""
    assert row["ev3_ev_conservative_return"] == -0.25
    assert row["ev3_selected_contract_aligned"] is False
    assert row["lab_tradeable"] is True
    assert row["lab_verdict"] == "GO_LIMIT"


def test_exact_contract_ev_and_monetisability_share_one_governed_evaluation_identity():
    row = opportunity_book_row(
        _base_signal(
            lab_verdict="GO_LIMIT",
            lab_tradeable=True,
            contract_symbol=OCC,
            instrument="LONG_CALL",
            strike=100,
            expiry="2099-01-19",
            dte=30,
            premium_mid=1.05,
            contract_bid=1.0,
            contract_ask=1.1,
            rr_premium_expected=1.8,
            monetisability_status="COMPLETE",
            monetisability_state="MONETISABLE",
            monetisability_contract_symbol=OCC,
            ev3_status="EVALUATED_SHADOW",
            ev3_structure="LONG_SINGLE",
            ev3_contract_symbol=OCC,
            ev3_ev_conservative_return=0.12,
        ),
        RUN_ID,
        1,
    )

    assert row["economics_comparable"] is True
    assert row["economics_mismatch_reason"] == ""
    assert row["selected_structure_id"] == row["monetisability_evaluation_id"]
    assert row["selected_structure_id"] == row["ev3_evaluation_id"]
    assert row["monetisability_contract_symbol"] == OCC
    assert row["ev_predicted"] == 0.12
    assert row["lab_tradeable"] is True


def test_post_merge_rejects_rr_and_quote_fields_from_a_different_contract(tmp_path):
    run = tmp_path / RUN_ID
    selected = "O:AAA990119C00100000"
    previous = "O:AAA990119C00105000"
    _write_csv(
        run / "options" / f"options_intelligence_{RUN_ID}.csv",
        {
            "ticker": "AAA",
            "contract_symbol": previous,
            "contract_mid": 4.25,
            "rr_premium_expected": 7.5,
        },
    )
    book = write_final_opportunity_book(
        RUN_ID,
        [_base_signal(
            lab_verdict="GO_LIMIT",
            lab_tradeable=True,
            contract_symbol=selected,
            instrument="LONG_CALL",
            ev3_status="EVALUATED_SHADOW",
            ev3_structure="LONG_SINGLE",
            ev3_contract_symbol=selected,
            ev3_ev_conservative_return=0.12,
        )],
        {"pipeline_mode": "MORNING", "fatal_flags": [], "stale_flags": []},
        tmp_path,
        sync_interpreter=False,
    )
    row = book["rows"][0]

    assert row["contract_mid"] == ""
    assert "rr_premium_expected" not in row
    assert "rr_contract_symbol" not in row
    assert row["economics_comparable"] is False
    assert row["economics_mismatch_reason"] == "MONETISABILITY_NOT_EVALUATED_FOR_SELECTED_CONTRACT"
    assert row["lab_tradeable"] is False
    assert row["lab_verdict"] == "CONTRACT_REPAIR"
    assert "CONTRACT_JOIN_REJECTED:options_intelligence:rr_premium_expected" in row["data_quality_flags"]


def test_legacy_repaired_contract_cannot_inherit_unidentified_rr():
    row = opportunity_book_row(
        _base_signal(
            lab_verdict="GO_LIMIT",
            lab_tradeable=True,
            contract_symbol="O:AAA990119C00100000",
            contract_symbol_original="O:AAA990119C00105000",
            contract_repair_resolved_at_open="TRUE",
            rr_premium_expected=6.0,
            ev3_status="EVALUATED_SHADOW",
            ev3_structure="LONG_SINGLE",
            ev3_contract_symbol="O:AAA990119C00100000",
            ev3_ev_conservative_return=0.20,
        ),
        RUN_ID,
        1,
    )

    assert row["rr_contract_symbol"] == ""
    assert row["economics_comparable"] is False
    assert row["economics_mismatch_reason"] == "MONETISABILITY_NOT_EVALUATED_FOR_SELECTED_CONTRACT"
    assert row["lab_tradeable"] is False


def test_browser_prefers_governed_book_and_keeps_governed_fields(tmp_path):
    lab = _load_lab_module()
    lab.RUNS_DIR = tmp_path
    payload = {
        "lab_schema_version": "lab_signal_book_v2",
        "run_id": RUN_ID,
        "candidate_count": 1,
        "rows": [{
            "lab_schema_version": "lab_signal_book_v2",
            "ticker": "AAA",
            "trade_idea_id": f"{RUN_ID}:AAA:CALL:100:2099-01-19",
            "ev3_status": "EVALUATED_SHADOW",
            "trigger_primary": "BREAKOUT",
            "contract_data_state": "AVAILABLE",
            "garch_method": "GARCH",
        }],
    }
    path = tmp_path / RUN_ID / "intelligence_lab" / f"final_opportunity_book_{RUN_ID}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    governed = lab._governed_lab_book(RUN_ID)
    assert governed["rows"][0]["ev3_status"] == "EVALUATED_SHADOW"
    with lab.app.test_request_context("/api/run/test"):
        slim = lab._slim_lab_payload({"signals": governed["rows"]})
    signal = slim["signals"][0]
    assert signal["trigger_primary"] == "BREAKOUT"
    assert signal["contract_data_state"] == "AVAILABLE"
    assert signal["garch_method"] == "GARCH"


def test_governed_projection_supplies_display_aliases_without_granting_eod_entry():
    lab = _load_lab_module()
    projected = lab._governed_ui_projection({
        "lab_schema_version": "lab_signal_book_v2",
        "ticker": "CRWV",
        "pipeline_mode": "EOD",
        "morning_data_state": "NOT_RUN_EOD",
        "contract_symbol": "O:CRWV260918P00085000",
        "strike": "85",
        "expiry": "2026-09-18",
        "contract_mid": "6.10",
        "premium_mid": "6.10",
        "sector": "Information Technology",
        "wbs_grade": "PROBABLE",
        "wbs": "51.9",
        "wbs_momentum_alignment_state": "UNAVAILABLE_NO_INTRADAY_PCR",
        "garch_forecast_vol": "0.938",
        "readiness_stage": 3,
        "readiness_label": "EOD_PREP_COMPLETE_MORNING_VALIDATION_REQUIRED",
        "readiness_enter_now": False,
    })
    assert projected["opt__premium_mid"] == "6.10"
    assert projected["opt__recommended_contract"] == "O:CRWV260918P00085000"
    assert projected["wbs__wbs_grade"] == "PROBABLE"
    assert projected["wbs__momentum_alignment_state"] == "UNAVAILABLE_NO_INTRADAY_PCR"
    assert projected["garch__l3_vol_forecast"] == "0.938"
    assert projected["sb_enter_now_stages"] == ""
    assert projected["sb_alert_stages"] == "3"
    assert projected["position_size_display"] == "HUMAN DETERMINED"


def test_post_merge_materialization_recovers_owned_lab_fields(tmp_path):
    run = tmp_path / RUN_ID
    _write_csv(
        run / "options" / f"options_intelligence_{RUN_ID}.csv",
        {
            "ticker": "AAA",
            "contract_symbol": OCC,
            "contract_mid": 6.1,
            "positive_factors": "CHEAP_VOL",
            "negative_factors": "GAMMA_MOVING_AWAY",
            "pcr_vol_status": "OI_ONLY",
        },
    )
    _write_csv(
        run / "vanguard" / f"vanguard_signals_enriched_{RUN_ID}.csv",
        {"ticker": "AAA", "gics_sector_norm": "Information Technology", "sector_etf": "XLK"},
    )
    _write_csv(
        run / "superbrain" / f"wall_break_scores_{RUN_ID}.csv",
        {
            "ticker": "AAA",
            "wbs": 51.9,
            "wbs_grade": "POSSIBLE",
            "wbs_phase_b_trigger": 71.4,
            "wbs_phase_c_trigger": 69.65,
            "wbs_entry_guidance": "Wait for confirmed break",
        },
    )
    book = write_final_opportunity_book(
        RUN_ID,
        [_base_signal(contract_symbol=OCC, strike=100, expiry="2099-01-19", dte=30)],
        {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []},
        tmp_path,
        sync_interpreter=False,
    )
    row = book["rows"][0]
    assert row["premium_mid"] == "6.1"
    assert row["sector"] == "Information Technology"
    assert row["sector_etf"] == "XLK"
    assert row["positive_factors"] == "CHEAP_VOL"
    assert row["entry_plan"] == "Wait for confirmed break"
    assert row["trigger_price"] == "69.65"
    assert row["trigger_price_source"] == "WBS_PHASE_C_CONFIRMED_BREAK"
    assert row["wbs_momentum_alignment_state"] == "UNAVAILABLE_NO_INTRADAY_PCR"
    assert row["readiness_stage"] == 3
    assert row["readiness_enter_now"] is False
    provenance = json.loads(row["field_provenance_json"])
    assert provenance["contract_mid"] == "options_intelligence"
    assert provenance["sector"] == "vanguard_signals_enriched"
    assert provenance["trigger_price"] == "wall_break_scores"


def test_governed_materializer_corrects_legacy_put_wbs_missing_pcr_bonus(tmp_path):
    run = tmp_path / RUN_ID
    _write_csv(
        run / "options" / f"options_intelligence_{RUN_ID}.csv",
        {"ticker": "AAA", "pcr_vol_status": "OI_ONLY"},
    )
    _write_csv(
        run / "superbrain" / f"wall_break_scores_{RUN_ID}.csv",
        {
            "ticker": "AAA",
            "wbs": 56.9,
            "wbs_grade": "PROBABLE",
            "wbs_f5_momentum": 7.0,
            "wbs_notes": "GV=MOVING_AWAY + PCR_vol=1.00 confirms PUT pressure",
        },
    )
    book = write_final_opportunity_book(
        RUN_ID,
        [_base_signal(canonical_direction="PUT", final_direction="PUT")],
        {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []},
        tmp_path,
        sync_interpreter=False,
    )
    row = book["rows"][0]
    assert row["wbs"] == 51.9
    assert row["wbs_grade"] == "POSSIBLE"
    assert row["wbs_f5_momentum"] == 2.0
    assert row["wbs_pcr_volume_state"] == "UNAVAILABLE_LEGACY_BONUS_REMOVED"
    assert "WBS_LEGACY_MISSING_PCR_BONUS_REMOVED" in row["data_quality_flags"]
    provenance = json.loads(row["field_provenance_json"])
    assert provenance["wbs"] == "governed_materializer:wbs_missing_pcr_legacy_correction"


def test_copied_wbs_fields_do_not_make_unscored_candidate_look_scored(tmp_path):
    run = tmp_path / RUN_ID
    _write_csv(
        run / "superbrain" / f"wall_break_scores_{RUN_ID}.csv",
        {"ticker": "OTHER", "wbs": 70, "wbs_grade": "PROBABLE"},
    )
    book = write_final_opportunity_book(
        RUN_ID,
        [_base_signal(wbs=65, wbs_grade="PROBABLE")],
        {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []},
        tmp_path,
        sync_interpreter=False,
    )
    row = book["rows"][0]
    assert row["wbs"] == ""
    assert row["wbs_grade"] == ""
    assert row["wbs_data_state"] == "NOT_APPLICABLE_NOT_SCORED"


def test_ui_has_no_synthetic_call_default_and_ev_is_advisory_only():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert "s.direction||'CALL'" not in html
    assert "s.direction||s.canonical_direction||'—'" in html
    function_body = html.split("function getMonetisationFailure(s) {", 1)[1].split("function formatEv", 1)[0]
    assert "getEvDecisionHint" not in function_body
    assert "getOptionRr" not in function_body
    assert "EV3 Advisory State" in html
    assert "EV3 Conservative EV" in html
    assert "economics_comparable" in html
    assert "NOT COMPARABLE" in html
    assert "Quote Hydration" in html
    assert "Monetisability Check" in html
    assert ">R:R<" not in html
    assert "EV3 Contract Alignment" in html
    assert "getSelectedContract(s)" in html
    assert "s.ev2_decision_hint||'â€”'" not in html
