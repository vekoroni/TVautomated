"""AVS-PKG-002 P2 — Vanguard reads its inputs by reference, behind a flag, with byte parity.

Business rules:
- The run manifest cites the discovery file the packages were actually built from (the CDS-3
  governed input when it exists) and the runtime macro the injector used, so a reference
  loader reproduces the same inputs.
- A thin, in-memory package built from the cited sources by the SAME owners (package builder,
  macro injector, canonical backfill) equals the stored package except declared wall-clock
  stamps and the stored package's stale DCV annotation (finding PKG-F1).
- `run_vanguard_from_packages.py` keeps `packages` as its default input mode; `manifest` mode
  is opt-in, fails closed without a manifest, and produces the same Vanguard rows and rejects.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from avshunter.c0_run.canonical_manifest import build_canonical_manifest, collect_canonical_inputs  # noqa: E402
from avshunter.c0_run.thin_package import (  # noqa: E402
    DECLARED_STAMP_KEYS, build_thin_package_from_run, package_diff_keys,
)

REAL_RUN = "20260926_173730"
REAL_DIR = ROOT / "data" / "output" / "runs" / REAL_RUN
RUNNER = ROOT / "scripts" / "run_vanguard_from_packages.py"
PY = ROOT / "venv" / "Scripts" / "python.exe"
needs_real_run = pytest.mark.skipif(not (REAL_DIR / "packages").is_dir(), reason="retained package run not present")


# ------------------------------------------------------------------ P1 amendment: cite what was really used
def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_manifest_cites_the_governed_discovery_input_and_the_runtime_macro(tmp_path, monkeypatch):
    run = tmp_path / "data" / "output" / "runs" / "20260925_230000"
    _write(run / "discovery" / "discovery_candidates_ultimate_20260925_230000.csv", "ticker,signal_price,extra\nAAA,1,x\nBBB,2,y\n")
    _write(run / "discovery" / "discovery_candidates_cds3_20260925_230000.csv", "ticker,signal_price\nAAA,1\n")
    _write(run / "macro_snapshot.json", json.dumps({"macro_authority": "ADVISORY_ONLY", "as_of_utc": "2026-09-25T05:00:00Z", "regime_state": "X"}))
    _write(run / "macro" / "macro_runtime_gex_synced.json", json.dumps({"macro_authority": "ADVISORY_ONLY", "regime_state": "X", "gex": 1}))
    _write(run / "run_meta.json", json.dumps({"dynamic_plan": {"last_completed_session": "2026-09-25"}}))
    monkeypatch.setenv("AVSHUNTER_HISTORICAL_PRICE_DB", str(tmp_path / "absent.sqlite"))

    inputs = collect_canonical_inputs(run_dir=run, repo_root=tmp_path, actuarial_path=tmp_path / "none.parquet")
    manifest = build_canonical_manifest(inputs, created_at_utc=datetime(2026, 9, 25, 23, 5, tzinfo=timezone.utc))
    discovery = manifest["sources"]["discovery"]
    assert discovery["path"].endswith("discovery_candidates_cds3_20260925_230000.csv")
    assert discovery["governed_input"] is True and discovery["row_count"] == 1
    assert [r["ticker"] for r in manifest["tickers"]] == ["AAA"]
    runtime = manifest["sources"]["macro_runtime"]
    assert runtime["status"] == "PRESENT" and runtime["path"].endswith("macro_runtime_gex_synced.json")
    assert runtime["sha256"] == hashlib.sha256((run / "macro" / "macro_runtime_gex_synced.json").read_bytes()).hexdigest()

    (run / "discovery" / "discovery_candidates_cds3_20260925_230000.csv").unlink()
    (run / "macro" / "macro_runtime_gex_synced.json").unlink()
    manifest2 = build_canonical_manifest(collect_canonical_inputs(run_dir=run, repo_root=tmp_path, actuarial_path=tmp_path / "none.parquet"),
                                         created_at_utc=datetime(2026, 9, 25, 23, 5, tzinfo=timezone.utc))
    assert manifest2["sources"]["discovery"]["governed_input"] is False
    assert [r["ticker"] for r in manifest2["tickers"]] == ["AAA", "BBB"]
    assert manifest2["sources"]["macro_runtime"]["status"] == "MISSING"


# ------------------------------------------------------------------ thin package == stored package (minus declared stamps)
@needs_real_run
@pytest.mark.parametrize("ticker", ["AAPL", "VST", "XLF"])
def test_thin_package_reproduces_the_stored_package_except_declared_stamps(ticker):
    stored_path = REAL_DIR / "packages" / f"{ticker}.package.json"
    if not stored_path.is_file():
        pytest.skip(f"{ticker} not in the retained run")
    stored = json.loads(stored_path.read_text(encoding="utf-8-sig"))
    before = hashlib.sha256(stored_path.read_bytes()).hexdigest()
    thin = build_thin_package_from_run(
        REAL_DIR, ticker,
        ingested_utc=stored["macro"]["ingested_utc"],          # reproduce the injector's stamp
        today=date.fromisoformat(stored["bar_data_as_of"]) if stored.get("bar_data_days_old") == 0 else None,
    )
    assert hashlib.sha256(stored_path.read_bytes()).hexdigest() == before  # read-only
    assert thin["ticker"] == ticker and thin["run_id"] == REAL_RUN
    assert thin["ohlcv_daily"] == stored["ohlcv_daily"]
    assert thin["daily_df"] == thin["ohlcv"] == thin["timeseries"]["ohlcv_daily"] == thin["ohlcv_daily"]
    assert thin["macro"]["payload"] == stored["macro"]["payload"]
    assert thin["macro_quant_packet"] == stored["macro_quant_packet"]
    assert thin["discovery"] == stored["discovery"]
    # Phase 8.5 patches the actuarial block AFTER Vanguard reads the package; at Vanguard time
    # it is the deferred block, which the thin package carries.
    assert thin["actuarial"]["deferred"] is True
    unexplained = package_diff_keys(stored, thin) - DECLARED_STAMP_KEYS
    assert unexplained == set(), sorted(unexplained)
    # PKG-F1: the thin package carries the truthful data-contract verdict, not the stale annotation.
    assert thin["data_contract"]["dcv_valid"] is True and thin["data_contract"]["dcv_bars"] == len(stored["ohlcv_daily"])
    assert thin["data_failure"] is False


# ------------------------------------------------------------------ runner modes
def test_runner_default_mode_is_packages_and_manifest_mode_fails_closed_without_a_manifest(tmp_path):
    source = RUNNER.read_text(encoding="utf-8")
    assert '"--input-mode"' in source and 'choices=("packages", "manifest")' in source
    assert 'AVSHUNTER_VANGUARD_INPUT_MODE", "packages"' in source  # environment default is packages
    help_text = subprocess.run([str(PY), str(RUNNER), "--help"], cwd=str(ROOT), capture_output=True, text=True, timeout=300).stdout
    assert "--input-mode {packages,manifest}" in help_text
    run_dir = tmp_path / "data" / "output" / "runs" / "20260101_000000"
    (run_dir / "packages").mkdir(parents=True)
    (run_dir / "packages" / "index.json").write_text('{"packages": []}', encoding="utf-8")
    result = subprocess.run([str(PY), str(RUNNER), "--run-id", "20260101_000000", "--input-mode", "manifest"],
                            cwd=str(tmp_path), capture_output=True, text=True, timeout=600)
    assert result.returncode == 3
    assert "canonical_manifest.json" in (result.stdout + result.stderr)


def _rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return sorted(csv.DictReader(fh), key=lambda r: r["ticker"])


WALL_CLOCK_COLUMNS = {"timestamp", "layer1__profile__timestamp"}  # Vanguard stamps its own run time
REJECT_IDENTITY_COLUMNS = {"package_path"}


SUBSET = int(os.environ.get("AVSHUNTER_P2_GATE_LIMIT", "25"))
POST_VANGUARD_KEYS = ("tle", "triggers", "eligible_for_trade")


def _reset_to_vanguard_time(pkg: dict) -> dict:
    """Undo the patches later Evening phases wrote into the stored package after Vanguard read it."""
    from scripts.build_packages_from_discovery import _ACTUARIAL_DEFERRED_BLOCK
    out = dict(pkg)
    out["actuarial"] = dict(_ACTUARIAL_DEFERRED_BLOCK)
    for key in list(out):
        if key in POST_VANGUARD_KEYS or key.startswith("market_profile_"):
            out.pop(key, None)
    dc = dict(out.get("data_contract") or {})
    for key in list(dc):
        if key.startswith("actuarial_"):
            dc.pop(key)
    dc["actuarial_data_quality"] = "OHLCV_OK"
    dc["actuarial_penalty_at_build"] = 1.0
    out["data_contract"] = dc
    return out


@needs_real_run
def test_p2_gate_manifest_mode_equals_packages_mode_at_the_same_moment(tmp_path):
    """Vanguard's rows depend on live state outside the package (actuarial cache, profile
    registry, canonical history), so Friday's stored rows are not a control. The control is a
    packages-mode run NOW over the stored packages reset to their Vanguard-time state, against
    a manifest-mode run NOW; the two must be identical except wall-clock stamps."""
    index = json.loads((REAL_DIR / "packages" / "index.json").read_text(encoding="utf-8-sig"))
    entries = [e for e in index.get("packages") or [] if e.get("package_path")][:SUBSET]
    assert entries
    # Temporary root with the reset packages; nothing in the real run is touched.
    fake_run = tmp_path / "root" / "data" / "output" / "runs" / REAL_RUN
    (fake_run / "packages").mkdir(parents=True)
    kept = []
    for entry in entries:
        source = Path(entry["package_path"])
        if not source.is_absolute():
            source = ROOT / source
        pkg = _reset_to_vanguard_time(json.loads(source.read_text(encoding="utf-8-sig")))
        target = fake_run / "packages" / source.name
        target.write_text(json.dumps(pkg), encoding="utf-8")
        kept.append({**entry, "package_path": str(target)})
    (fake_run / "packages" / "index.json").write_text(json.dumps({**index, "packages": kept}), encoding="utf-8")
    before = {p: p.stat().st_mtime for p in (REAL_DIR / "vanguard").glob("*")}

    out_pk, out_mf = tmp_path / "packages_mode", tmp_path / "manifest_mode"
    out_pk.mkdir(); out_mf.mkdir()
    pk = subprocess.run([str(PY), str(RUNNER), "--run-id", REAL_RUN, "--input-mode", "packages",
                         "--limit", str(SUBSET), "--output-dir", str(out_pk)],
                        cwd=str(tmp_path / "root"), capture_output=True, text=True, timeout=7200)
    assert pk.returncode == 0, pk.stdout[-2000:] + pk.stderr[-2000:]
    mf = subprocess.run([str(PY), str(RUNNER), "--run-id", REAL_RUN, "--input-mode", "manifest",
                         "--limit", str(SUBSET), "--output-dir", str(out_mf)],
                        cwd=str(ROOT), capture_output=True, text=True, timeout=7200)
    assert mf.returncode == 0, mf.stdout[-2000:] + mf.stderr[-2000:]
    assert {p: p.stat().st_mtime for p in (REAL_DIR / "vanguard").glob("*")} == before  # read-only

    p_pass, p_rej = _rows(out_pk / "vanguard_signals.csv"), _rows(out_pk / "vanguard_rejects.csv")
    m_pass, m_rej = _rows(out_mf / "vanguard_signals.csv"), _rows(out_mf / "vanguard_rejects.csv")
    assert [r["ticker"] for r in p_pass] == [r["ticker"] for r in m_pass]
    assert [r["ticker"] for r in p_rej] == [r["ticker"] for r in m_rej]
    assert p_pass or p_rej
    differing = {}
    for a, b in zip(p_pass, m_pass):
        for col in set(a) | set(b):
            if col not in WALL_CLOCK_COLUMNS and a.get(col) != b.get(col):
                differing.setdefault(col, []).append(a["ticker"])
    for a, b in zip(p_rej, m_rej):
        for col in set(a) | set(b):
            if col not in REJECT_IDENTITY_COLUMNS and a.get(col) != b.get(col):
                differing.setdefault(col, []).append(a["ticker"])
    assert differing == {}, {k: v[:5] for k, v in differing.items()}
