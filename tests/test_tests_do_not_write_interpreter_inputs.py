"""A test run never writes into the Pipeline Interpreter's real inputs folder (ACK approved 15 Nov 2026).

Business rule: pipeline_interpreter\\MA_Inputs\\pipeline_outputs holds real run outputs only. The Interpreter reads the
newest file of each kind by file time, so a fixture written there by a test is read in place of the real run.

Root cause found 15 Nov 2026: the pipeline writers copy their output into that folder after writing it (the candidate
manifest does so for every run id except "TEST"). test_book_integrity_e3_e4_e5_e7 calls the manifest builder with run
id "E3", which left execution_v3_5_E3.csv and morning_candidates_E3.csv in the real folder on every test run.
tests\\conftest.py now replaces that copy with a no-op for the whole test session.
"""
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
REAL_INPUTS = REPO / "pipeline_interpreter" / "MA_Inputs" / "pipeline_outputs"


def _copy_after_writing(path: Path):
    """The call the pipeline writers make after writing an output file (eod_candidate_engine.build_candidate_manifest)."""
    import sys
    sys.path.insert(0, str(REPO / "pipeline_interpreter"))
    from ma_inputs_sync import on_pipeline_complete
    return on_pipeline_complete(str(path), output_dir=str(path.parent))


def test_the_writers_copy_step_does_nothing_during_a_test_run(tmp_path):
    name = "morning_candidates_GUARDCHECK.csv"
    source, landed = tmp_path / name, REAL_INPUTS / name
    pd.DataFrame([{"ticker": "AAA"}]).to_csv(source, index=False)
    try:
        assert _copy_after_writing(source) == []
        assert not landed.exists(), f"a test wrote {landed}"
    finally:
        landed.unlink(missing_ok=True)   # never leave a fixture behind, even when the rule fails


def test_building_a_candidate_manifest_in_a_test_leaves_the_real_folder_alone():
    from tests.test_book_integrity_e3_e4_e5_e7 import _eod_row, _manifest

    targets = [REAL_INPUTS / "execution_v3_5_E3.csv", REAL_INPUTS / "morning_candidates_E3.csv"]
    before = {p: (p.stat().st_mtime_ns if p.exists() else None) for p in targets}
    _manifest([_eod_row("AAA", route="OPTIONS_GO_REVIEW")])
    after = {p: (p.stat().st_mtime_ns if p.exists() else None) for p in targets}
    assert after == before, "the candidate manifest test wrote into the Interpreter's real inputs folder"
