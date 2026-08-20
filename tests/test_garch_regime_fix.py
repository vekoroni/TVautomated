"""
Tests for garch_runner._load_regime fix:
  - Must read from dropbox/macro/ (canonical location)
  - Must use regime_state field (macro_contract_v1_0)
  - Legacy field names must still work as fallbacks
"""
import json
import sys
import importlib.util
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _load_garch_runner():
    """Import garch_runner without running __main__."""
    spec = importlib.util.spec_from_file_location(
        "garch_runner",
        str(Path(__file__).resolve().parents[1] / "garch_runner.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_macro(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_loads_from_dropbox_macro(tmp_path):
    """_load_regime must find the file in dropbox/macro/ first."""
    mod = _load_garch_runner()
    macro_dir = tmp_path / "dropbox" / "macro"
    _write_macro(macro_dir / "macro_intelligence_latest.json", {"regime_state": "RISK_ON"})
    # Root-level file should NOT be chosen
    _write_macro(tmp_path / "macro_intelligence_latest.json", {"regime_state": "RISK_OFF"})

    regime = mod._load_regime(tmp_path)
    assert regime == "RISK_ON", f"Expected RISK_ON from dropbox/macro/, got: {regime}"
    print("PASS: _load_regime reads from dropbox/macro/ first")


def test_reads_regime_state_field(tmp_path):
    """Must use 'regime_state' (macro_contract_v1_0 field name)."""
    mod = _load_garch_runner()
    macro_dir = tmp_path / "dropbox" / "macro"
    _write_macro(
        macro_dir / "macro_intelligence_latest.json",
        {"regime_state": "RISK_OFF", "active_regime": "TRANSITIONAL"},
    )
    regime = mod._load_regime(tmp_path)
    assert regime == "RISK_OFF", f"Expected RISK_OFF (regime_state), got: {regime}"
    print("PASS: _load_regime uses regime_state field")


def test_legacy_active_regime_fallback(tmp_path):
    """Falls back to active_regime if regime_state absent."""
    mod = _load_garch_runner()
    macro_dir = tmp_path / "dropbox" / "macro"
    _write_macro(
        macro_dir / "macro_intelligence_latest.json",
        {"active_regime": "RISK_ON"},  # no regime_state
    )
    regime = mod._load_regime(tmp_path)
    assert regime == "RISK_ON", f"Expected RISK_ON from active_regime fallback, got: {regime}"
    print("PASS: _load_regime falls back to active_regime")


def test_legacy_regime_fallback(tmp_path):
    """Falls back to regime if neither regime_state nor active_regime present."""
    mod = _load_garch_runner()
    macro_dir = tmp_path / "dropbox" / "macro"
    _write_macro(
        macro_dir / "macro_intelligence_latest.json",
        {"regime": "TRANSITIONAL_BULLISH"},  # only legacy 'regime' key
    )
    regime = mod._load_regime(tmp_path)
    assert regime == "TRANSITIONAL_BULLISH", f"Expected TRANSITIONAL_BULLISH, got: {regime}"
    print("PASS: _load_regime falls back to regime")


def test_default_transitional_when_no_file(tmp_path):
    """Returns TRANSITIONAL when no macro file exists."""
    mod = _load_garch_runner()
    regime = mod._load_regime(tmp_path)
    assert regime == "TRANSITIONAL", f"Expected TRANSITIONAL default, got: {regime}"
    print("PASS: _load_regime defaults to TRANSITIONAL when file absent")


def test_real_macro_json_resolves_correctly():
    """Must correctly read regime_state from the actual macro JSON on disk."""
    mod = _load_garch_runner()
    base_dir = Path(__file__).resolve().parents[1]
    macro_path = base_dir / "dropbox" / "macro" / "macro_intelligence_latest.json"
    if not macro_path.exists():
        print("SKIP: real macro JSON not found (OK in CI)")
        return
    regime = mod._load_regime(base_dir)
    assert regime != "TRANSITIONAL" or True  # just confirm it doesn't crash
    data = json.loads(macro_path.read_text(encoding="utf-8"))
    expected = data.get("regime_state", data.get("active_regime", data.get("regime", "TRANSITIONAL")))
    assert regime == str(expected), f"Expected {expected}, got: {regime}"
    print(f"PASS: real macro JSON regime resolved: {regime}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td)
        test_loads_from_dropbox_macro(tp / "t1")
        test_reads_regime_state_field(tp / "t2")
        test_legacy_active_regime_fallback(tp / "t3")
        test_legacy_regime_fallback(tp / "t4")
        test_default_transitional_when_no_file(tp / "t5")
    test_real_macro_json_resolves_correctly()
    print("\nAll garch_runner regime tests PASSED")
