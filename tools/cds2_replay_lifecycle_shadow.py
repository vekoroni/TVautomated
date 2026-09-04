"""Reconcile reference-run stage membership through the CDS lifecycle offline."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data import (  # noqa: E402
    CanonicalRegistry,
    DatasetType,
    LifecycleManager,
    LifecycleState,
)


def _tickers(path: Path) -> set[str]:
    if not path.exists():
        return set()
    frame = pd.read_csv(path, usecols=lambda column: column.lower() == "ticker")
    if "ticker" not in {column.lower() for column in frame.columns}:
        return set()
    column = next(column for column in frame.columns if column.lower() == "ticker")
    return {
        str(value).strip().upper()
        for value in frame[column].dropna()
        if str(value).strip()
    }


def replay(
    *,
    run_id: str,
    registry_path: Path,
    shadow_run_id: str,
) -> dict[str, object]:
    run_root = ROOT / "data" / "output" / "runs" / run_id
    stage_specs = (
        (
            "DISCOVERY",
            ROOT / "data" / "output" / f"discovery_candidates_ultimate_{run_id}.csv",
            LifecycleState.ACTIVE_DISCOVERY,
        ),
        ("VANGUARD", run_root / "vanguard" / "vanguard_signals.csv", LifecycleState.ACTIVE_CORE),
        (
            "OPTIONS",
            run_root / "options" / f"options_intelligence_{run_id}.csv",
            LifecycleState.ACTIVE_OPTIONS,
        ),
        (
            "SUPERBRAIN",
            run_root / "superbrain" / f"superbrain_enriched_{run_id}.csv",
            LifecycleState.ACTIVE_OPTIONS,
        ),
        (
            "EIL",
            run_root / "superbrain" / f"eil_enriched_{run_id}.csv",
            LifecycleState.ACTIVE_OPTIONS,
        ),
        (
            "GARCH",
            run_root / "qomega" / f"garch_forecasts_{run_id}.csv",
            LifecycleState.ACTIVE_OPTIONS,
        ),
        (
            "MORNING",
            run_root / "morning_validation" / f"morning_candidates_{run_id}.csv",
            LifecycleState.ACTIVE_MORNING,
        ),
    )
    stages = [
        (name, path, state, _tickers(path))
        for name, path, state in stage_specs
    ]
    missing_files = [str(path) for name, path, state, values in stages if not path.exists()]
    universe = set().union(*(values for name, path, state, values in stages))
    registry = CanonicalRegistry(registry_path)
    registry.initialise()
    registry.register_run(
        shadow_run_id,
        "CDS2_OFFLINE_SHADOW",
        date.fromisoformat(run_id[:8][:4] + "-" + run_id[:8][4:6] + "-" + run_id[:8][6:8]),
        metadata={"source_run_id": run_id, "network_calls": 0},
    )
    lifecycle = LifecycleManager(registry)
    for ticker in sorted(universe):
        lifecycle.register(
            shadow_run_id,
            ticker,
            stage="DISCOVERY",
            allowed_capabilities=(DatasetType.DAILY_OHLCV,),
        )

    stage_reports: list[dict[str, object]] = []
    reentries = 0
    drops = 0
    for stage_name, path, target_state, stage_tickers in stages:
        for ticker in sorted(universe):
            event = lifecycle.latest(shadow_run_id, ticker)
            assert event is not None
            if ticker in stage_tickers:
                if event.stage != stage_name or event.state != target_state:
                    if event.state is LifecycleState.DROPPED_STAGE:
                        reentries += 1
                    lifecycle.transition(
                        shadow_run_id,
                        ticker,
                        target_state,
                        stage=stage_name,
                        reason_code="PRESENT_IN_STAGE_ARTIFACT",
                        expected_version=event.version,
                        allowed_capabilities=(DatasetType.DAILY_OHLCV,),
                    )
            elif event.state not in {
                LifecycleState.DROPPED_STAGE,
                LifecycleState.DROPPED_TERMINAL_DATA,
                LifecycleState.DROPPED_TERMINAL_LOGIC,
                LifecycleState.DEFERRED_CURRENT_RUN,
                LifecycleState.COMPLETED,
            }:
                lifecycle.transition(
                    shadow_run_id,
                    ticker,
                    LifecycleState.DROPPED_STAGE,
                    stage=stage_name,
                    reason_code=f"ABSENT_FROM_{stage_name}_ARTIFACT",
                    expected_version=event.version,
                )
                drops += 1
        worklist = lifecycle.create_worklist(
            shadow_run_id,
            stage_name,
            DatasetType.DAILY_OHLCV,
            stage_tickers,
        )
        reconciliation = lifecycle.reconcile_worklist(
            shadow_run_id,
            stage_name,
            DatasetType.DAILY_OHLCV,
            stage_tickers,
        )
        stage_reports.append(
            {
                "stage": stage_name,
                "artifact": str(path),
                "artifact_exists": path.exists(),
                "artifact_tickers": len(stage_tickers),
                "worklist_tickers": len(worklist),
                "missing": list(reconciliation.missing),
                "unexpected": list(reconciliation.unexpected),
                "reconciled": reconciliation.reconciled,
            }
        )

    accepted = not missing_files and all(item["reconciled"] for item in stage_reports)
    return {
        "contract_version": "cds2_lifecycle_shadow_v1",
        "source_run_id": run_id,
        "shadow_run_id": shadow_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "universe_tickers": len(universe),
        "transition_drop_events": drops,
        "stage_reentry_events": reentries,
        "missing_artifacts": missing_files,
        "stages": stage_reports,
        "accepted": accepted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "data" / "canonical" / "control_plane.sqlite",
    )
    parser.add_argument("--shadow-run-id")
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    shadow_run_id = arguments.shadow_run_id or (
        f"CDS2_SHADOW_{arguments.run_id}_"
        + datetime.now(timezone.utc).strftime("%H%M%S")
    )
    report = replay(
        run_id=arguments.run_id,
        registry_path=arguments.registry,
        shadow_run_id=shadow_run_id,
    )
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps({
        "accepted": report["accepted"],
        "universe_tickers": report["universe_tickers"],
        "transition_drop_events": report["transition_drop_events"],
        "stage_reentry_events": report["stage_reentry_events"],
        "stage_counts": {
            item["stage"]: item["artifact_tickers"] for item in report["stages"]
        },
    }, sort_keys=True))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
