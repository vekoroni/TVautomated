"""
FIX-CACHE — _lab_cache_signature() must invalidate on changes to the primary
signal-source files (eil_enriched, options_intelligence), not only on changes
to the morning-validation handoff files.

Diagnosed in BASELINE.md (Phase 0.3): the same run_id produced different
Trigger_Score / Horizon_* values in the audited 2026-07-31 export than a
live re-derivation of the same run folder — with the underlying CSVs on disk
unchanged since the run. The mechanism: _lab_cache_signature() only
fingerprints morning_validation/morning_packet/eod_candidates paths
(intelligence_lab.py:_morning_handoff_paths), so a stale in-memory cache of
eil_enriched/options_intelligence data is never invalidated even though those
files can still be rewritten while a Lab session is open.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_lab_module():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("intelligence_lab_for_cache_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, columns: list[str], row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = [str(row.get(col, "")) for col in columns]
    path.write_text(",".join(columns) + "\n" + ",".join(values) + "\n", encoding="utf-8")


def test_lab_reload_detects_fresh_eil_enriched_output_without_manual_cache_clear():
    """eil_enriched is the primary signal source (not a morning-validation
    handoff file) — a change to it must still invalidate the cache."""
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_id = "20990101_100000"
        lab.RUNS_DIR = tmp_path / "runs"
        lab._run_cache.clear()

        run_dir = lab.RUNS_DIR / run_id
        eil_path = run_dir / "superbrain" / f"eil_enriched_{run_id}.csv"
        eil_columns = ["ticker", "direction", "strike", "expiry", "premium_mid",
                       "target_price", "invalidation_price", "lab_verdict", "trigger_score"]

        _write_csv(eil_path, eil_columns, {
            "ticker": "AAA", "direction": "CALL", "strike": "100", "expiry": "2099-01-19",
            "premium_mid": "1.0", "target_price": "110", "invalidation_price": "95",
            "lab_verdict": "GO", "trigger_score": "0.0",
        })

        first = lab._load_run(run_id, force_reload=True)
        first_sig = first["signals"][0]
        assert first_sig["trigger_score"] == "0.0"

        time.sleep(0.02)
        _write_csv(eil_path, eil_columns, {
            "ticker": "AAA", "direction": "CALL", "strike": "100", "expiry": "2099-01-19",
            "premium_mid": "1.0", "target_price": "110", "invalidation_price": "95",
            "lab_verdict": "GO", "trigger_score": "3.5",
        })

        second = lab._load_run(run_id)  # no force_reload — this is the bug path
        second_sig = second["signals"][0]
        assert second is not first
        assert second_sig["trigger_score"] == "3.5", (
            "cache served a stale eil_enriched value; "
            "_lab_cache_signature() is not fingerprinting the eil_enriched path"
        )


def test_lab_reload_detects_fresh_options_intelligence_output_without_manual_cache_clear():
    """options_intelligence_latest.csv backs every opt__-prefixed field
    (including the trigger_score collision documented in LAB_QA_REPORT.md F5) —
    a change to it must also invalidate the cache."""
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_id = "20990101_110000"
        lab.RUNS_DIR = tmp_path / "runs"
        lab._run_cache.clear()

        run_dir = lab.RUNS_DIR / run_id
        eil_path = run_dir / "superbrain" / f"eil_enriched_{run_id}.csv"
        eil_columns = ["ticker", "direction", "strike", "expiry", "premium_mid",
                       "target_price", "invalidation_price", "lab_verdict"]
        _write_csv(eil_path, eil_columns, {
            "ticker": "AAA", "direction": "CALL", "strike": "100", "expiry": "2099-01-19",
            "premium_mid": "1.0", "target_price": "110", "invalidation_price": "95",
            "lab_verdict": "GO",
        })

        opt_path = run_dir / "options" / f"options_intelligence_{run_id}.csv"
        opt_columns = ["ticker", "rr_options", "trigger_score"]
        _write_csv(opt_path, opt_columns, {"ticker": "AAA", "rr_options": "0.0", "trigger_score": "0.0"})

        first = lab._load_run(run_id, force_reload=True)
        first_sig = first["signals"][0]
        assert first_sig["opt__trigger_score"] == "0.0"

        time.sleep(0.02)
        _write_csv(opt_path, opt_columns, {"ticker": "AAA", "rr_options": "2.1", "trigger_score": "55.0"})

        second = lab._load_run(run_id)  # no force_reload — this is the bug path
        second_sig = second["signals"][0]
        assert second is not first
        assert second_sig["opt__trigger_score"] == "55.0", (
            "cache served a stale options_intelligence value; "
            "_lab_cache_signature() is not fingerprinting the options_intelligence path"
        )
