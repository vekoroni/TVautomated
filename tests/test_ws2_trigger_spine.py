from pathlib import Path
import sys
import types

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution_schema import (  # noqa: E402
    TRIGGER_HANDOFF_SCHEMA_VERSION,
    validate_trigger_handoff_row,
)


def _trigger_row(**overrides):
    row = {
        "ticker": "AAA",
        "trigger_codes": "RANGE_BREAK",
        "trigger_count": 1,
        "trigger_primary": "RANGE_BREAK",
        "trigger_quality": "SINGLE",
        "trigger_score": 2.0,
        "trigger_go_eligible": True,
        "trigger_stale": False,
        "trigger_freshness_state": "FRESH",
        "trigger_data_asof": "2026-09-01T20:00:00Z",
        "trigger_handoff_schema_version": TRIGGER_HANDOFF_SCHEMA_VERSION,
    }
    row.update(overrides)
    return row


def test_trigger_handoff_accepts_governed_categories():
    validate_trigger_handoff_row(_trigger_row())
    validate_trigger_handoff_row(
        _trigger_row(
            trigger_codes="NONE",
            trigger_count=0,
            trigger_primary="NONE",
            trigger_quality="NONE",
            trigger_score=0,
            trigger_go_eligible=False,
        )
    )


@pytest.mark.parametrize(
    "field,value",
    (("trigger_primary", 55), ("trigger_primary", "55.0"), ("trigger_quality", 2)),
)
def test_trigger_handoff_rejects_numeric_categorical_values(field, value):
    with pytest.raises(ValueError, match="categorical|domain"):
        validate_trigger_handoff_row(_trigger_row(**{field: value}))


def test_trigger_layer_output_survives_execution_spine_into_eod_book(tmp_path, monkeypatch):
    from eod_candidate_engine import build_candidate_manifest
    from trigger_layer import enrich_csv

    monkeypatch.setitem(
        sys.modules,
        "ma_inputs_sync",
        types.SimpleNamespace(on_pipeline_complete=lambda *args, **kwargs: None),
    )

    run_id = "WS2_TEST"
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / run_id
    superbrain_dir = run_dir / "superbrain"
    execution_dir = run_dir / "execution"
    for directory in (superbrain_dir, execution_dir):
        directory.mkdir(parents=True, exist_ok=True)

    spine_path = superbrain_dir / f"superbrain_enriched_{run_id}.csv"
    pd.DataFrame([{
        "ticker": "AAA",
        "direction": "CALL",
        "options_direction": "CALL",
            "signal_price": 100.0,
            "target_price": 110.0,
            "invalidation_state": "AVAILABLE",
            "invalidation_spot": 95.0,
            "invalidation_source": "TEST_GOVERNED_STRUCTURE",
            "composite": 65.0,
        "options_score": 45.0,
        "rr_underlying": 2.0,
        "eil_v3_verdict": "EXECUTE",
        "effective_execution_verdict": "MORNING_VALIDATION_REQUIRED",
        "capital_permission": "EOD_CANDIDATE_ONLY",
        "eod_candidate_authorized": True,
        "execution_authorized": False,
        "pse_execution_mode": "CURRENT_EDGE_REVIEW",
        "sb_conv_score": 3.0,
        "sb_campaign": "CORE_CAMPAIGN",
        "final_route": "OPTIONS_GO_REVIEW",
        "recommended_contract": "AAA260619C00100000",
        "contract_strike": 100.0,
        "contract_premium": 2.0,
        "contract_dte": 30,
    }]).to_csv(spine_path, index=False)
    pd.DataFrame([_trigger_row()]).to_csv(
        run_dir / f"trigger_layer_summary_{run_id}.csv", index=False
    )

    stats = enrich_csv(spine_path, inplace=True)
    governed = pd.read_csv(spine_path)
    governed["trigger_handoff_schema_version"] = TRIGGER_HANDOFF_SCHEMA_VERSION
    execution_path = execution_dir / f"execution_v3_5_{run_id}.csv"
    governed.to_csv(execution_path, index=False)
    output_path = run_dir / f"morning_candidates_{run_id}.csv"
    book = build_candidate_manifest(
        eil_path=execution_path,
        output_path=output_path,
        run_id=run_id,
        max_candidates=10,
    )

    assert stats["patched"] == 1
    assert governed.loc[0, "trigger_primary"] == "RANGE_BREAK"
    assert governed.loc[0, "trigger_quality"] == "SINGLE"
    assert governed.loc[0, "trigger_handoff_schema_version"] == TRIGGER_HANDOFF_SCHEMA_VERSION
    assert book.loc[0, "trigger_primary"] == "RANGE_BREAK"
    assert book.loc[0, "trigger_quality"] == "SINGLE"
    rank_audit = pd.read_csv(run_dir / f"ws2_trigger_rank_audit_{run_id}.csv")
    assert rank_audit.loc[0, "ticker"] == "AAA"
    assert rank_audit.loc[0, "trigger_quality"] == "SINGLE"
    assert rank_audit.loc[0, "trigger_neutral_rank"] == 1
    assert rank_audit.loc[0, "trigger_rank_delta"] == 0


def test_production_path_no_longer_uses_late_trigger_overlay():
    source = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8")
    commute_at = source.index("commute_trigger_spine_before_eil(canonical_run_id)")
    eil_at = source.index("run_execution_intelligence_layer(canonical_run_id)")
    assert commute_at < eil_at
    assert "trigger_overlay_path = _eil_csv" not in source
    assert "trigger_overlay_path = None" in source
