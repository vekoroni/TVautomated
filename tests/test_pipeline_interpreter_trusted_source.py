import csv
import sys
import types
from pathlib import Path


def _write_csv(path: Path, ticker: str, extra: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ticker": ticker}
    if extra:
        row.update(extra)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)


def _import_commands():
    if "anthropic" not in sys.modules:
        sys.modules["anthropic"] = types.SimpleNamespace(Anthropic=lambda *a, **k: None)
    repo_root = Path(__file__).resolve().parents[1]
    interp_dir = repo_root / "pipeline_interpreter"
    if str(interp_dir) not in sys.path:
        sys.path.insert(0, str(interp_dir))
    import pipeline_interpreter_commands as commands
    import pipeline_interpreter_engine as engine
    return commands, engine


def test_trusted_source_prefers_lab_triage_view(tmp_path, monkeypatch):
    # This test exercises the two-cycle legacy compatibility path.  The
    # production configuration deliberately enables the governed manifest
    # resolver, so isolate the legacy path explicitly instead of inheriting
    # machine-level rollout state.
    monkeypatch.setenv("MSI_INTERPRETER_RESOLVER", "0")
    commands, engine = _import_commands()
    ma_inputs = tmp_path / "MA_Inputs"
    ma_pipeline = ma_inputs / "pipeline_outputs"

    _write_csv(
        ma_pipeline / "morning_candidates_20260101_000000.csv",
        "AAA",
        {"source": "morning_candidates"},
    )
    lab_path = ma_pipeline / "lab_triage_view_20260101_000000.csv"
    _write_csv(lab_path, "AAA", {"source": "lab"})

    old_engine_inputs, old_engine_pipeline = engine.MA_INPUTS, engine.MA_PIPELINE
    old_cmd_inputs, old_cmd_pipeline = commands.MA_INPUTS, commands.MA_PIPELINE
    try:
        engine.MA_INPUTS = ma_inputs
        engine.MA_PIPELINE = ma_pipeline
        commands.MA_INPUTS = ma_inputs
        commands.MA_PIPELINE = ma_pipeline
        path, reason = commands.get_trusted_interpreter_source(ticker="AAA")
        assert Path(path) == lab_path
        assert reason == "trusted_lab_view"
    finally:
        engine.MA_INPUTS = old_engine_inputs
        engine.MA_PIPELINE = old_engine_pipeline
        commands.MA_INPUTS = old_cmd_inputs
        commands.MA_PIPELINE = old_cmd_pipeline


def test_explicit_source_still_wins_when_valid(tmp_path, monkeypatch):
    # Explicit loose files are supported only while the governed resolver is
    # disabled.  Make that contract part of the fixture.
    monkeypatch.setenv("MSI_INTERPRETER_RESOLVER", "0")
    commands, engine = _import_commands()
    ma_inputs = tmp_path / "MA_Inputs"
    ma_pipeline = ma_inputs / "pipeline_outputs"

    lab_path = ma_pipeline / "lab_triage_view_20260101_000000.csv"
    explicit_path = tmp_path / "manual.csv"
    _write_csv(lab_path, "AAA", {"source": "lab"})
    _write_csv(explicit_path, "AAA", {"source": "manual"})

    old_engine_inputs, old_engine_pipeline = engine.MA_INPUTS, engine.MA_PIPELINE
    old_cmd_inputs, old_cmd_pipeline = commands.MA_INPUTS, commands.MA_PIPELINE
    try:
        engine.MA_INPUTS = ma_inputs
        engine.MA_PIPELINE = ma_pipeline
        commands.MA_INPUTS = ma_inputs
        commands.MA_PIPELINE = ma_pipeline
        path, reason = commands.get_trusted_interpreter_source(
            ticker="AAA",
            explicit_path=str(explicit_path),
        )
        assert Path(path) == explicit_path
        assert reason == "explicit"
    finally:
        engine.MA_INPUTS = old_engine_inputs
        engine.MA_PIPELINE = old_engine_pipeline
        commands.MA_INPUTS = old_cmd_inputs
        commands.MA_PIPELINE = old_cmd_pipeline


def test_msi_resolver_disables_all_loose_file_source_fallbacks(tmp_path, monkeypatch):
    commands, _ = _import_commands()
    explicit_path = tmp_path / "manual.csv"
    _write_csv(explicit_path, "AAA", {"source": "manual"})
    monkeypatch.setenv("MSI_INTERPRETER_RESOLVER", "1")
    path, reason = commands.get_trusted_interpreter_source(
        ticker="AAA", explicit_path=str(explicit_path)
    )
    assert path == ""
    assert reason == "governed_manifest_only"
