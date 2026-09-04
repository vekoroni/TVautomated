from __future__ import annotations

import json
from pathlib import Path

from msi_runtime import MSIRuntimeFlags
from tools.msi_production_readiness import assess_run


RUN_ID = "20990101_010101"
ACTIVE = MSIRuntimeFlags(
    v2_capture=True,
    cds_resolver=True,
    minute_bars=True,
    structure=True,
    lab_v3_view=True,
    macro_advisory=True,
    interpreter_resolver=True,
    screen_adapter=False,
)


def test_evening_run_is_explicitly_pending_morning_gate(tmp_path: Path) -> None:
    run_root = tmp_path / RUN_ID
    run_root.mkdir(parents=True)
    (run_root / "run_meta.json").write_text(
        json.dumps({"run_id": RUN_ID, "run_status": "COMPLETED"}),
        encoding="utf-8",
    )
    report = assess_run(RUN_ID, runs_dir=tmp_path, flags=ACTIVE)
    assert report["status"] == "PENDING_MORNING_GATE"
    assert report["errors"] == []


def test_missing_handoff_after_morning_gate_fails(tmp_path: Path) -> None:
    run_root = tmp_path / RUN_ID
    morning = run_root / "morning_validation"
    morning.mkdir(parents=True)
    (run_root / "run_meta.json").write_text(
        json.dumps({"run_id": RUN_ID, "run_status": "COMPLETED"}),
        encoding="utf-8",
    )
    (morning / f"morning_validated_trades_{RUN_ID}.csv").write_text(
        "ticker\nAAA\n",
        encoding="utf-8",
    )
    report = assess_run(RUN_ID, runs_dir=tmp_path, flags=ACTIVE)
    assert report["status"] == "FAIL"
    assert "HANDOFF_MISSING_AFTER_MORNING_GATE" in report["errors"]


def test_disabled_structured_flags_fail_evening_readiness(tmp_path: Path) -> None:
    run_root = tmp_path / RUN_ID
    run_root.mkdir(parents=True)
    (run_root / "run_meta.json").write_text("{}", encoding="utf-8")
    report = assess_run(RUN_ID, runs_dir=tmp_path, flags=MSIRuntimeFlags())
    assert report["status"] == "FAIL"
    assert report["errors"][0].startswith("STRUCTURED_FLAGS_DISABLED:")
