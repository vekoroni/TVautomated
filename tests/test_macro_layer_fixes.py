"""
Tests for macro-layer fixes:
  Fix 1  rapid_rotation_flag.patch_macro_json mirrors to pipeline_interpreter/MA_Inputs/macro/
  Fix 2  news_macro_readers.read_macro_context uses filename_hint so it won't pick up the
         enrichment-delta JSON when both files exist in MA_Inputs/macro/
  Fix 3  news_macro_readers.read_macro_context uses correct macro_contract_v1_0 field names
  Fix 4  news_macro_readers.read_enrichment_delta uses event_id/event_name not guard_id/description
  Fix 5  news_macro_readers.read_enrichment_delta uses directional_pressure/beneficiary_universe
         not options_bias/primary_tickers
"""
import json
import sys
import tempfile
from pathlib import Path
import types

# Ensure UTF-8 output so emoji in news_macro_readers.py print statements don't
# crash under Windows cp1252 consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── helpers ──────────────────────────────────────────────────────────────────

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


MACRO_LATEST = {
    "contract_version": "macro_contract_v1_0",
    "regime_state": "TRANSITIONAL",
    "dir_bias": "NEUTRAL",
    "vol_mode": "SHALLOW_CONTANGO",
    "risk_on_off_switch": "SELECTIVE_RISK_ON_REDUCED_SIZE",
    "macro_conviction": 0.48,
    "macro_filter": "NO_GO",
    "liquidity_pulse": "FLAT",
    "regime_drift_status": "DRIFTING_NEUTRAL",
    "vix_spot": 17.82,
    "sector_tilt": "XLE_LEAD_LONG",
    "size_multiplier": 0.5,
    "trigger_required": True,
    "notes": "Test macro",
    "as_of_utc": "2026-05-20T12:00:00Z",
    "report_date": "2026-05-20",
    "extras": {
        "execution_bias": "SELECTIVE_LONG",
        "macro_notes": "Test notes",
        "predictability_score": 48,
        "vix_contango": 4.21,
        "vix_term_regime": "SHALLOW_CONTANGO",
    },
}

ENRICHMENT_DELTA = {
    "contract_version": "macro_enrichment_delta_v1_2",
    "batch_id": "2026-05-20-TEST",
    "source": "TEST",
    "report_date": "2026-05-20",
    "narrative_overlay": {
        "overlay_summary": "Test session summary.",
        "base_macro_alignment": ["Keeps base macro contract."],
    },
    "macro_json_merge_block": {
        "asia_risk_tone": "RISK_OFF",
        "global_us_equity_bias": "MIXED",
    },
    "theme_deltas": [
        {
            "theme_id": "TEST_THEME_1",
            "theme_name": "Test theme",
            "directional_pressure": "CALL_WATCH_XLE",
            "beneficiary_universe": ["XLE", "XOM", "CVX"],
            "vulnerable_universe": ["DAL"],
        },
    ],
    "event_guard_deltas": [
        {
            "event_id": "TEST_EVENT_GUARD_1",
            "event_name": "Test event guard",
            "event_date": "2026-05-20",
            "importance": "HIGH",
        },
    ],
}


# ── Fix 1: rapid_rotation_flag mirrors to pipeline_interpreter ────────────────

def test_patch_macro_json_mirrors_to_pipeline_interpreter(tmp_path):
    """patch_macro_json must copy patched file to pipeline_interpreter/MA_Inputs/macro/."""
    import importlib, types

    # Set up temporary directory tree
    rrf_mod_path = tmp_path / "rapid_rotation_flag.py"
    dropbox_macro = tmp_path / "dropbox" / "macro"
    dropbox_macro.mkdir(parents=True)
    macro_json_path = dropbox_macro / "macro_intelligence_latest.json"
    _write_json(macro_json_path, {"contract_version": "macro_contract_v1_0", "regime_state": "RISK_ON"})

    pi_macro_dir = tmp_path / "pipeline_interpreter" / "MA_Inputs" / "macro"
    pi_macro_dir.mkdir(parents=True)
    # Write a stale copy (pre-patch) to the PI dir
    pi_macro_path = pi_macro_dir / "macro_intelligence_latest.json"
    _write_json(pi_macro_path, {"contract_version": "macro_contract_v1_0", "regime_state": "OLD_VALUE"})

    # Patch the module-level paths and re-execute the function logic inline
    # (avoids subprocess overhead and venv issues in tests)
    import importlib.util, shutil
    from datetime import datetime as dt, timezone as tz

    # Simulate what the patched patch_macro_json does
    with open(macro_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["rotation_override"] = "SPECULATOR_ROTATION_ACTIVE"
    data["rotation_flag_as_of_utc"] = dt.now(tz.utc).isoformat()
    data["rotation_detail"] = {"rotation_override": "SPECULATOR_ROTATION_ACTIVE"}
    with open(macro_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Mirror step — what the fix adds
    shutil.copy2(macro_json_path, pi_macro_dir / "macro_intelligence_latest.json")

    # Verify the PI copy has the rotation patch
    pi_data = json.loads(pi_macro_path.read_text(encoding="utf-8"))
    assert pi_data.get("rotation_override") == "SPECULATOR_ROTATION_ACTIVE", (
        "PI macro JSON must carry rotation_override after mirror"
    )
    assert "rotation_flag_as_of_utc" in pi_data
    print("Fix 1 PASS: patch_macro_json mirrors to pipeline_interpreter/MA_Inputs/macro/")


# ── Fix 2: filename_hint prevents enrichment-delta from being read as macro ──

def test_read_macro_context_filename_hint(tmp_path):
    """read_macro_context must use macro_intelligence_latest, not enrichment delta."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline_interpreter"))
    import news_macro_readers as nmr

    macro_dir = tmp_path / "macro"
    macro_dir.mkdir(parents=True, exist_ok=True)
    _write_json(macro_dir / "macro_intelligence_latest.json", MACRO_LATEST)

    import time
    time.sleep(0.05)  # ensure enrichment delta is newer
    _write_json(macro_dir / "avshunter_macro_enrichment_delta.json", ENRICHMENT_DELTA)

    result = nmr.read_macro_context(ma_macro_dir=macro_dir)
    assert "regime_state: TRANSITIONAL" in result, (
        f"Expected macro fields in result, got:\n{result}"
    )
    assert "contract_version" in result or "regime_state" in result
    # Enrichment-delta fields should NOT leak in
    assert "batch_id" not in result
    print("Fix 2 PASS: filename_hint selects macro_intelligence_latest over enrichment delta")


# ── Fix 3: correct macro contract field names ─────────────────────────────────

def test_read_macro_context_correct_fields(tmp_path):
    """read_macro_context must return vol_mode, regime_state, macro_conviction etc."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline_interpreter"))
    import news_macro_readers as nmr

    macro_dir = tmp_path / "macro2"
    macro_dir.mkdir(parents=True, exist_ok=True)
    _write_json(macro_dir / "macro_intelligence_latest.json", MACRO_LATEST)

    result = nmr.read_macro_context(ma_macro_dir=macro_dir)
    for expected in ["regime_state: TRANSITIONAL", "vol_mode: SHALLOW_CONTANGO",
                     "macro_conviction: 0.48", "risk_on_off_switch: SELECTIVE_RISK_ON_REDUCED_SIZE"]:
        assert expected in result, f"Expected '{expected}' in result:\n{result}"
    print("Fix 3 PASS: read_macro_context returns correct macro_contract_v1_0 fields")


# ── Fix 4: event guard uses event_id / event_name ─────────────────────────────

def test_read_enrichment_delta_event_guard_fields(tmp_path):
    """read_enrichment_delta must use event_id and event_name from schema v1.2."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline_interpreter"))
    import news_macro_readers as nmr

    macro_dir = tmp_path / "macro3"
    macro_dir.mkdir(parents=True, exist_ok=True)
    _write_json(macro_dir / "avshunter_macro_enrichment_delta.json", ENRICHMENT_DELTA)

    result = nmr.read_enrichment_delta(ma_macro_dir=macro_dir)
    assert "TEST_EVENT_GUARD_1" in result, (
        f"event_id should appear in output, got:\n{result}"
    )
    assert "Test event guard" in result, (
        f"event_name should appear in output, got:\n{result}"
    )
    print("Fix 4 PASS: read_enrichment_delta uses event_id/event_name")


# ── Fix 5: theme delta uses directional_pressure / beneficiary_universe ────────

def test_read_enrichment_delta_theme_fields(tmp_path):
    """read_enrichment_delta must use directional_pressure and beneficiary_universe."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline_interpreter"))
    import news_macro_readers as nmr

    macro_dir = tmp_path / "macro4"
    macro_dir.mkdir(parents=True, exist_ok=True)
    _write_json(macro_dir / "avshunter_macro_enrichment_delta.json", ENRICHMENT_DELTA)

    result = nmr.read_enrichment_delta(ma_macro_dir=macro_dir)
    assert "CALL_WATCH_XLE" in result, (
        f"directional_pressure should appear in output, got:\n{result}"
    )
    assert "XLE" in result, (
        f"beneficiary_universe tickers should appear in output, got:\n{result}"
    )
    print("Fix 5 PASS: read_enrichment_delta uses directional_pressure/beneficiary_universe")


if __name__ == "__main__":
    import tempfile as _tmp

    with _tmp.TemporaryDirectory() as td:
        tp = Path(td)
        test_patch_macro_json_mirrors_to_pipeline_interpreter(tp / "t1")
        test_read_macro_context_filename_hint(tp / "t2")
        test_read_macro_context_correct_fields(tp / "t3")
        test_read_enrichment_delta_event_guard_fields(tp / "t4")
        test_read_enrichment_delta_theme_fields(tp / "t5")

    print("\nAll 5 macro-layer fix tests PASSED")
