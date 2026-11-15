"""Session-wide test guards.

Interpreter inputs (ACK approved 15 Nov 2026): a test run never writes into pipeline_interpreter\\MA_Inputs.
The pipeline writers (eod_candidate_engine, execution_intelligence_runner, morning_validation, contracts.lab_control)
end with ``from ma_inputs_sync import on_pipeline_complete`` and copy what they wrote into the Interpreter's real
inputs folder. Called from a test, that left fixtures there which the Interpreter then read as the newest run.
The copy step is replaced by a no-op for the whole session. The real module is loaded by file path, so nothing is
added to sys.path and every other function in it is unchanged. Tests that need the real copy patch it themselves
(tests\\test_morning_handoff_finalizer.py uses pipeline_interpreter.ma_inputs_sync and is not affected).
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SYNC_FILE = Path(__file__).resolve().parents[1] / "pipeline_interpreter" / "ma_inputs_sync.py"


def _no_copy_during_tests(output_csv_path, output_dir=None):
    """Stands in for ma_inputs_sync.on_pipeline_complete: copies nothing, reports nothing copied."""
    return []


@pytest.fixture(scope="session", autouse=True)
def interpreter_inputs_are_not_written_by_tests():
    previous = sys.modules.get("ma_inputs_sync")
    module = previous
    if module is None and SYNC_FILE.exists():
        spec = importlib.util.spec_from_file_location("ma_inputs_sync", SYNC_FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules["ma_inputs_sync"] = module
    original = getattr(module, "on_pipeline_complete", None) if module is not None else None
    if module is not None:
        module.on_pipeline_complete = _no_copy_during_tests
    yield
    if module is not None and original is not None:
        module.on_pipeline_complete = original
    if previous is None:
        sys.modules.pop("ma_inputs_sync", None)
