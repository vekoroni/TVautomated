"""Standalone production-interpreter probe for WS2 orchestrator helpers."""

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import intelligent_orchestrator as orchestrator  # noqa: E402


def run_probe(base_dir: Path) -> None:
    run_id = "WS2_RUNTIME_PROBE"
    runs_dir = base_dir / "runs"
    run_dir = runs_dir / run_id
    superbrain_dir = run_dir / "superbrain"
    options_dir = run_dir / "options"
    execution_dir = run_dir / "execution"
    for directory in (superbrain_dir, options_dir, execution_dir):
        directory.mkdir(parents=True, exist_ok=True)

    pd.DataFrame([{"ticker": "AAA", "composite": 60.0}]).to_csv(
        superbrain_dir / f"superbrain_enriched_{run_id}.csv", index=False
    )
    pd.DataFrame([{
        "ticker": "AAA",
        "crabel_state": "COMPRESSION",
        "crabel_compression": True,
        "atr_percentile_rank": 20.0,
        "dominant_trend": "UP",
    }]).to_csv(options_dir / f"vanguard_signals_enriched_{run_id}.csv", index=False)
    pd.DataFrame([{
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
    }]).to_csv(run_dir / f"trigger_layer_summary_{run_id}.csv", index=False)

    original_runs_dir = orchestrator.cfg.RUNS_DIR
    try:
        orchestrator.cfg.RUNS_DIR = runs_dir
        stats = orchestrator.commute_trigger_spine_before_eil(run_id)
        governed_path = superbrain_dir / f"superbrain_enriched_{run_id}.csv"
        governed = pd.read_csv(governed_path, low_memory=False)
        governed.to_csv(execution_dir / f"execution_v3_5_{run_id}.csv", index=False)
        enriched_path = superbrain_dir / f"eil_enriched_{run_id}.csv"
        governed.to_csv(enriched_path, index=False)
        verification = orchestrator.verify_trigger_spine_after_eil(run_id)
        changed = governed.copy()
        changed.loc[0, "trigger_quality"] = "STRONG"
        changed.to_csv(enriched_path, index=False)
        try:
            orchestrator.verify_trigger_spine_after_eil(run_id)
        except RuntimeError as error:
            assert "changed after EIL" in str(error)
        else:
            raise AssertionError("WS2 mismatch guard did not fail closed")
        governed.to_csv(enriched_path, index=False)
    finally:
        orchestrator.cfg.RUNS_DIR = original_runs_dir

    assert stats["rows"] == 1
    assert stats["patched"] == 1
    assert governed.loc[0, "trigger_primary"] == "RANGE_BREAK"
    assert governed.loc[0, "trigger_quality"] == "SINGLE"
    assert governed.loc[0, "trigger_handoff_schema_version"] == "trigger_handoff_v1"
    assert verification == {"rows": 1, "mismatches": 0}


if __name__ == "__main__":
    destination = ROOT / "audit" / "pipeline_logic_review" / "ws2_runtime_probe"
    run_probe(destination)
    print("WS2_RUNTIME_PROBE_PASS")
