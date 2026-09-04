from __future__ import annotations

import json
from pathlib import Path

from morning_handoff_finalizer import _msi_identity_preflight


RUN_ID = "20990101_010101"


def _complete_row() -> dict[str, str]:
    return {
        "run_id": RUN_ID,
        "ticker": "AAA",
        "thesis_id": "THESIS:AAA:1",
        "trade_idea_id": "IDEA:AAA:1",
        "selected_structure_id": "STRUCTURE:AAA:1",
        "selected_contract_symbol": "AAA990119C00100000",
        "selected_quote_snapshot_id": "QUOTE:AAA:1",
    }


def test_identity_preflight_passes_and_persists_diagnostic(tmp_path: Path) -> None:
    report = _msi_identity_preflight(
        run_id=RUN_ID,
        run_dir=tmp_path,
        rows=[_complete_row()],
    )
    assert report["status"] == "PASS"
    assert report["failed_rows"] == 0
    saved = json.loads(Path(report["report_path"]).read_text(encoding="utf-8"))
    assert saved["status"] == "PASS"
    assert saved["actionable_rows"] == 1


def test_identity_preflight_reports_every_missing_field_without_minting(
    tmp_path: Path,
) -> None:
    incomplete = _complete_row()
    incomplete["thesis_id"] = ""
    incomplete["selected_contract_symbol"] = ""
    incomplete["selected_quote_snapshot_id"] = ""
    report = _msi_identity_preflight(
        run_id=RUN_ID,
        run_dir=tmp_path,
        rows=[incomplete],
    )
    assert report["status"] == "FAIL"
    assert report["failed_rows"] == 1
    assert report["failures"] == [
        {
            "ticker": "AAA",
            "missing": [
                "thesis_id",
                "selected_contract_symbol",
                "selected_quote_snapshot_id",
            ],
            "observed_run_id": RUN_ID,
        }
    ]


def test_identity_preflight_rejects_cross_run_identity(tmp_path: Path) -> None:
    row = _complete_row()
    row["run_id"] = "20990102_010101"
    report = _msi_identity_preflight(
        run_id=RUN_ID,
        run_dir=tmp_path,
        rows=[row],
    )
    assert report["status"] == "FAIL"
    assert report["failures"][0]["missing"] == ["run_id_mismatch"]
