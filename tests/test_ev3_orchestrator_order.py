from __future__ import annotations

from pathlib import Path


def test_ev3_runs_after_horizon_router_and_raw_options_patch() -> None:
    source = (Path(__file__).parents[1] / "intelligent_orchestrator.py").read_text(
        encoding="utf-8",
    )
    workflow = source[source.index("def evening_workflow(") :]
    options = workflow.index("if not run_options_intelligence(")
    router = workflow.index("_hr_result = run_horizon_router")
    raw_target = workflow.index('f"options_intelligence_{canonical_run_id}.csv"')
    patch = workflow.index("_oi_horizon_patched = patch_horizon_fields_into_csv")
    ev3 = workflow.index("run_ev3_governed_shadow(canonical_run_id")
    assert options < router < raw_target < patch < ev3


def test_morning_manifest_uses_final_execution_authority_not_eil() -> None:
    source = (Path(__file__).parents[1] / "intelligent_orchestrator.py").read_text(
        encoding="utf-8",
    )
    phase10 = source[source.index("# ── PHASE 10: EOD Candidate Engine") :]
    build_call = phase10[phase10.index("build_candidate_manifest(") :]

    assert 'f"execution_v3_5_{canonical_run_id}.csv"' in phase10
    assert "eil_path       = _execution_authority_csv" in build_call
    assert "if _execution_authority_csv.exists()" in phase10


def test_horizon_patch_rederives_ev3_planned_hold_atomically() -> None:
    source = (Path(__file__).parents[1] / "intelligent_orchestrator.py").read_text(
        encoding="utf-8",
    )
    helper = source[
        source.index("def patch_horizon_fields_into_csv") :
        source.index("def run_superbrain_passthrough")
    ]

    assert '"1_5d": 5' in helper
    assert '"6_10d": 10' in helper
    assert '"11_20d": 20' in helper
    assert 'patched["planned_hold_sessions"]' in helper
    # ACK 18 Sep 2026: the hold is the governed thesis window; the anticipated move follows the thesis horizon.
    assert "THESIS_WINDOW_D2" in helper
    assert "FINAL_HORIZON_ROUTER_ENDPOINT_V1" not in helper


def test_production_launchers_use_governed_orchestrator() -> None:
    root = Path(__file__).parents[1]
    evening = (root / "run_evening.bat").read_text(encoding="utf-8")
    morning = (root / "run_premarket.bat").read_text(encoding="utf-8")

    assert 'intelligent_orchestrator.py" --evening' in evening
    assert 'intelligent_orchestrator.py" --morning' in morning
    assert "avshunter_discovery_v3_HYBRID.py" not in evening
    assert "premarket_intelligence_v3_HYBRID.py" not in morning
    assert "run_shadow_automation" not in evening + morning


def test_ev3_authority_switch_is_retired_and_overlay_is_advisory() -> None:
    source = (Path(__file__).parents[1] / "intelligent_orchestrator.py").read_text(
        encoding="utf-8",
    )
    config = source[source.index("EV3_AUTHORITY_REQUESTED") : source.index("EV3_FUNCTIONAL_TEST_NOW_UTC")]
    overlay = source[source.index("def run_ev3_authority_overlay") : source.index("def run_phantom_layer")]

    assert "EV3_AUTHORITY_ENABLED = False" in config
    assert 'command.append("--enable-authority")' not in overlay
    assert "permanently advisory mode" in overlay
