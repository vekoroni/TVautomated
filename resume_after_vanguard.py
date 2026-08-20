#!/usr/bin/env python3
"""
AVSHUNTER manual resume runner.
Starts AFTER Vanguard has completed successfully.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

import intelligent_orchestrator as orch


def call_if_exists(label, func_name, *args, critical=False, **kwargs):
    print("\n" + "=" * 80)
    print(label)
    print("=" * 80)

    func = getattr(orch, func_name, None)
    if func is None:
        msg = f"SKIP: function not found: {func_name}"
        print(msg)
        if critical:
            raise RuntimeError(msg)
        return None

    try:
        result = func(*args, **kwargs)
        print(f"RESULT: {result}")
        return result
    except TypeError as e:
        print(f"SIGNATURE MISMATCH in {func_name}: {e}")
        if critical:
            raise
        return None
    except Exception as e:
        print(f"FAILED in {func_name}: {e}")
        if critical:
            raise
        return None


def run_actuarial_enrichment(run_id: str) -> None:
    print("\n" + "=" * 80)
    print("PHASE 8.5: ACTUARIAL ENRICHMENT PASS")
    print("=" * 80)

    cfg = orch.cfg
    path = cfg.ACTUARIAL_ENRICHMENT_PASS

    if not path.exists():
        print(f"SKIP: Actuarial enrichment pass not found: {path}")
        return

    try:
        spec = importlib.util.spec_from_file_location("actuarial_enrichment_pass", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.run_actuarial_enrichment_pass(
            run_id=run_id,
            base_dir=cfg.BASE_DIR,
        )
        print(f"RESULT: {result}")
    except Exception as e:
        print(f"WARNING: Actuarial enrichment failed non-critically: {e}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-mode", default="EOD", choices=["EOD", "LATEST"])
    args = parser.parse_args()

    run_id = args.run_id
    data_mode = args.data_mode

    cfg = orch.cfg
    run_dir = cfg.RUNS_DIR / run_id
    vanguard_csv = run_dir / "vanguard" / "vanguard_signals.csv"

    print("=" * 80)
    print(f"AVSHUNTER RESUME AFTER VANGUARD | run_id={run_id} | data_mode={data_mode}")
    print("=" * 80)

    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    if not vanguard_csv.exists():
        raise FileNotFoundError(f"Vanguard output missing: {vanguard_csv}")

    print(f"Confirmed run dir      : {run_dir}")
    print(f"Confirmed Vanguard CSV : {vanguard_csv}")

    call_if_exists(
        "PHASE 8a-0: POSITION LOCK CHECK",
        "run_position_lock_check",
        run_id,
        critical=False,
    )

    call_if_exists(
        "PHASE 8a: OPTIONS INTELLIGENCE",
        "run_options_intelligence",
        run_id,
        critical=False,
    )

    print("\n" + "=" * 80)
    print("PHASE 1B: HORIZON ROUTER")
    print("=" * 80)
    try:
        orch.run_horizon_router(cfg.MACRO_FILE, run_id)
    except Exception as e:
        print(f"WARNING: Horizon router failed non-critically: {e}")

    print("\n" + "=" * 80)
    print("PHASE 1B-B: PATCH HORIZON FIELDS INTO OPTIONS CSV")
    print("=" * 80)
    try:
        oi_horizon_target = (
            cfg.RUNS_DIR / run_id / "options" /
            f"vanguard_signals_enriched_{run_id}.csv"
        )
        orch.patch_horizon_fields_into_csv(
            run_id=run_id,
            target_csv=oi_horizon_target,
            label="options_intelligence_OI",
        )
    except Exception as e:
        print(f"WARNING: Horizon patch failed non-critically: {e}")

    run_actuarial_enrichment(run_id)

    call_if_exists("PHASE 8c: CORE INTEL EXPORTER", "run_core_intel_exporter", run_id)
    call_if_exists("PHASE 8d: SUPERBRAIN LAYER", "run_superbrain_layer", run_id)
    call_if_exists("PHASE 8e: MONETISATION POLICY", "run_monetisation_policy", run_id)
    call_if_exists("PHASE 8f: WALL BREAK SCORER", "run_wall_break_scorer", run_id)
    call_if_exists("PHASE 9: EXECUTION INTELLIGENCE LAYER", "run_execution_intelligence_layer", run_id)
    call_if_exists("PHASE 9A: EIL POST-ACTUARIAL INJECT", "_eil_post_actuarial_inject", run_id)
    call_if_exists("PHASE 10A: GARCH / Q-OMEGA LAYER", "run_garch_layer", run_id)
    call_if_exists("PHASE 8.6B: TRIGGER LAYER", "run_trigger_layer", run_id)
    call_if_exists("PHASE 9B: ENHANCEMENT LAYER", "run_enhancement_layer", run_id)
    call_if_exists("PHASE 9C: TRADE BOOK BUILDER", "run_trade_book_builder", run_id)
    call_if_exists("PHASE 10: EOD CANDIDATE ENGINE", "run_eod_candidate_engine", run_id)
    call_if_exists("FINAL: GENERATE REPORT", "generate_report", run_id)

    print("\n" + "=" * 80)
    print("RESUME COMPLETE — now validate output folders.")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
