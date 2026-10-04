"""AVS-PKG-002 P4 — the Evening runs without writing or reading package files.

Business rules (ACK, 27 Sep 2026, both behaviour changes approved):
- The run input manifest is the Vanguard input owner. In `manifest` mode (the default) the
  Build/Inject/Backfill package phases are skipped, the manifest build is critical, and every
  stage that used the package files works from the manifest, the canonical stores and its own
  ledger. `packages` mode remains selectable by configuration as the rollback path.
- A stale canonical history is a typed rejection recorded in the manifest, not a mid-run
  provider refetch; provider refresh is owned by Discovery's write-through before the run.
- Nothing downstream needs `packages/index.json`: the latest-run pointer, the trap engine,
  the trigger layer, the actuarial pass and Options' macro contexts resolve from the manifest.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from avshunter.c0_run.canonical_manifest import (  # noqa: E402
    build_canonical_manifest, collect_canonical_inputs, write_canonical_manifest,
)
from canonical_data.historical_prices import HistoricalPriceDatabase  # noqa: E402
from contracts.enrichment_ledger import read_enrichment_ledger  # noqa: E402

RUN = "20260925_230000"
SESSION = date(2026, 9, 25)


def _bars(n: int, last: date) -> pd.DataFrame:
    days, d = [], last
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return pd.DataFrame({"date": [x.isoformat() for x in days], "open": [50.0] * n, "high": [50.5] * n,
                         "low": [49.5] * n, "close": [50.2 + i * 0.01 for i in range(n)], "volume": [1_000_000] * n})


@pytest.fixture
def package_free_run(tmp_path, monkeypatch):
    """A run with every input the manifest cites and NO packages folder."""
    base = tmp_path
    run_dir = base / "data" / "output" / "runs" / RUN
    (run_dir / "discovery").mkdir(parents=True)
    (run_dir / "macro").mkdir()
    rows = [{"ticker": "AAA", "direction": "CALL", "stock_price": "50.2", "dominant_event": "Trend_Up"},
            {"ticker": "BBB", "direction": "PUT", "stock_price": "20.0", "dominant_event": "Distribution"}]
    for name in ("ultimate", "cds3"):
        with (run_dir / "discovery" / f"discovery_candidates_{name}_{RUN}.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    macro = {"contract_version": "macro_contract_v1_0", "macro_authority": "ADVISORY_ONLY",
             "as_of_utc": "2026-09-25T05:39:11Z", "regime_state": "TRANSITIONAL_BEARISH", "dir_bias": "BEARISH",
             "volatility_mode": "ELEVATED", "regime_drift_status": "DRIFTING", "macro_conviction": 0.5}
    (run_dir / "macro_snapshot.json").write_text(json.dumps(macro), encoding="utf-8")
    (run_dir / "macro" / "macro_runtime_gex_synced.json").write_text(json.dumps({**macro, "gex_available": True}), encoding="utf-8")
    (run_dir / "run_meta.json").write_text(json.dumps({"dynamic_plan": {"last_completed_session": SESSION.isoformat(),
                                                                         "evidence_cutoff_utc": "2026-09-25T23:00:00Z"}}), encoding="utf-8")
    db_path = base / "data" / "canonical" / "historical_prices.sqlite"
    db_path.parent.mkdir(parents=True)
    db = HistoricalPriceDatabase(db_path); db.initialise()
    for ticker in ("AAA", "BBB"):
        db.ingest(ticker, _bars(260, SESSION), provider="TEST", source_kind="DAILY_BACKFILL", source_run_id=RUN)
    monkeypatch.setenv("AVSHUNTER_HISTORICAL_PRICE_DB", str(db_path))
    inputs = collect_canonical_inputs(run_dir=run_dir, repo_root=base, actuarial_path=base / "none.parquet")
    write_canonical_manifest(run_dir, build_canonical_manifest(inputs, created_at_utc=datetime(2026, 9, 25, 23, 5, tzinfo=timezone.utc)))
    (run_dir / "vanguard").mkdir()
    with (run_dir / "vanguard" / "vanguard_signals.csv").open("w", encoding="utf-8", newline="") as fh:
        # The actuarial pass ignores a signals file under 500 bytes; real rows carry long reasoning text.
        w = csv.DictWriter(fh, fieldnames=["ticker", "verdict", "state_hash", "win_rate_20d", "reasoning"]); w.writeheader()
        w.writerows([{"ticker": "AAA", "verdict": "PASS", "state_hash": "h1", "win_rate_20d": 0.55, "reasoning": "x" * 400},
                     {"ticker": "BBB", "verdict": "PASS", "state_hash": "h2", "win_rate_20d": 0.45, "reasoning": "y" * 400}])
    (run_dir / "options").mkdir()
    assert not (run_dir / "packages").exists()
    return {"base": base, "run_dir": run_dir, "runs_dir": base / "data" / "output" / "runs"}


# ------------------------------------------------------------------ orchestrator: input mode and phase skipping
@pytest.fixture
def orch(monkeypatch, tmp_path):
    import intelligent_orchestrator as orch
    monkeypatch.setattr(orch.cfg, "BASE_DIR", tmp_path / "no_trap_here")  # trap engine file absent -> non-critical skip
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", tmp_path / "data" / "output" / "runs")
    monkeypatch.setattr(orch, "pin_run_directory", lambda *a, **k: True)
    monkeypatch.setattr(orch, "publish_cds3_discovery_worklist", lambda *a, **k: True)
    monkeypatch.setattr(orch, "prepare_cds3_governed_package_input", lambda run_id: None)
    monkeypatch.setattr(orch, "run_dropoff_audit_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(orch, "completed_profile_stage_enabled", lambda: False)
    calls = []
    monkeypatch.setattr(orch, "_run", lambda label, cmd, critical=True: calls.append((label, [str(c) for c in cmd], critical)) or True)
    monkeypatch.setattr(orch.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="Backfilled OK   : 2\n"))
    return orch, calls


def test_input_mode_defaults_to_manifest_and_packages_stays_selectable(monkeypatch):
    import intelligent_orchestrator as orch
    monkeypatch.delenv("AVSHUNTER_VANGUARD_INPUT_MODE", raising=False)
    assert orch.vanguard_input_mode() == "manifest"
    monkeypatch.setenv("AVSHUNTER_VANGUARD_INPUT_MODE", "packages")
    assert orch.vanguard_input_mode() == "packages"
    monkeypatch.setenv("AVSHUNTER_VANGUARD_INPUT_MODE", "bogus")
    with pytest.raises(ValueError):
        orch.vanguard_input_mode()


def test_manifest_mode_skips_the_package_phases_and_makes_the_manifest_critical(orch, monkeypatch, tmp_path):
    orch_mod, calls = orch
    monkeypatch.setenv("AVSHUNTER_VANGUARD_INPUT_MODE", "manifest")
    run_dir = orch_mod.cfg.RUNS_DIR / RUN
    run_dir.mkdir(parents=True)
    (run_dir / "canonical_manifest.json").write_text("{}", encoding="utf-8")  # the input record the guard requires
    assert orch_mod.run_vanguard_pipeline(RUN, tmp_path / "macro.json", evidence_session_date=SESSION.isoformat()) is True
    labels = [c[0] for c in calls]
    assert labels == ["Build Canonical Manifest", "Run VANGUARD"]
    manifest_call = next(c for c in calls if c[0] == "Build Canonical Manifest")
    assert manifest_call[2] is True and "--macro-path" in manifest_call[1]
    vanguard_call = next(c for c in calls if c[0] == "Run VANGUARD")
    assert vanguard_call[1][-2:] == ["--input-mode", "manifest"]
    assert not (orch_mod.cfg.RUNS_DIR / RUN / "packages").exists()
    # A manifest failure aborts: it is the input now.
    calls.clear()
    monkeypatch.setattr(orch_mod, "_run", lambda label, cmd, critical=True: label != "Build Canonical Manifest")
    assert orch_mod.run_vanguard_pipeline(RUN, tmp_path / "macro.json", evidence_session_date=SESSION.isoformat()) is False


def test_packages_mode_is_the_rollback_and_still_runs_the_three_phases(orch, monkeypatch, tmp_path):
    orch_mod, calls = orch
    monkeypatch.setenv("AVSHUNTER_VANGUARD_INPUT_MODE", "packages")
    (orch_mod.cfg.RUNS_DIR / RUN / "packages").mkdir(parents=True)
    (orch_mod.cfg.RUNS_DIR / RUN / "packages" / "index.json").write_text('{"packages": []}', encoding="utf-8")
    assert orch_mod.run_vanguard_pipeline(RUN, tmp_path / "macro.json", evidence_session_date=SESSION.isoformat()) is True
    labels = [c[0] for c in calls]
    assert labels == ["Build Packages from Discovery", "Inject Macro into Packages", "Build Canonical Manifest", "Run VANGUARD"]
    vanguard_call = next(c for c in calls if c[0] == "Run VANGUARD")
    assert vanguard_call[1][-2:] == ["--input-mode", "packages"]
    manifest_call = next(c for c in calls if c[0] == "Build Canonical Manifest")
    assert manifest_call[2] is False  # beside the packages, as in P1


# ------------------------------------------------------------------ stages without packages
def test_trap_engine_runs_from_the_manifest_and_writes_only_its_ledger(package_free_run):
    import importlib.util
    spec = importlib.util.spec_from_file_location("avshunter_trap_engine_p4", ROOT / "avshunter_trap_engine.py")
    trap = importlib.util.module_from_spec(spec); spec.loader.exec_module(trap)
    assert trap.run_trap_layer(run_id=RUN, runs_dir=package_free_run["runs_dir"]) is True
    ledger = read_enrichment_ledger(package_free_run["run_dir"], "trap")
    assert ledger["status"] == "PRESENT" and set(ledger["by_ticker"]) == {"AAA", "BBB"}
    assert all(b.get("tle_verdict") for b in ledger["by_ticker"].values())
    assert not (package_free_run["run_dir"] / "packages").exists()


def test_trigger_layer_runs_from_the_vanguard_rows_and_writes_ledger_and_sidecar(package_free_run):
    from trigger_layer import patch_run_packages
    stats = patch_run_packages(run_id=RUN, base_dir=package_free_run["base"],
                               vanguard_csv_path=str(package_free_run["run_dir"] / "vanguard" / "vanguard_signals.csv"))
    assert stats["patched"] == 2
    ledger = read_enrichment_ledger(package_free_run["run_dir"], "trigger")
    assert set(ledger["by_ticker"]) == {"AAA", "BBB"}
    assert all("go_eligible" in b and "quality" in b for b in ledger["by_ticker"].values())
    sidecar = package_free_run["run_dir"] / f"trigger_layer_summary_{RUN}.csv"
    with sidecar.open("r", encoding="utf-8-sig", newline="") as fh:
        assert {r["ticker"] for r in csv.DictReader(fh)} == {"AAA", "BBB"}
    assert not (package_free_run["run_dir"] / "packages").exists()


def test_actuarial_pass_runs_from_the_manifest_and_writes_only_its_ledger(package_free_run, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("actuarial_enrichment_pass_p4", ROOT / "scripts" / "actuarial_enrichment_pass.py")
    aep = importlib.util.module_from_spec(spec); spec.loader.exec_module(aep)
    monkeypatch.setattr(aep, "_load_actuarial", lambda: True)
    monkeypatch.setattr(aep, "_build_actuarial_block", lambda state: {
        "available": True, "no_match": False, "fallback_depth": 0, "win_rate_10d": 0.6, "enriched_by": "actuarial_enrichment_pass"})
    monkeypatch.setattr(aep, "validate_truth_packet", lambda block: None)
    result = aep.run_actuarial_enrichment_pass(run_id=RUN, base_dir=package_free_run["base"])
    assert result.get("success") is True, result
    assert result["packages_patched"] == 2 and result["outcomes"]["EXACT_MATCH"] == 2
    ledger = read_enrichment_ledger(package_free_run["run_dir"], "actuarial")
    assert set(ledger["by_ticker"]) == {"AAA", "BBB"}
    assert all(b.get("enriched_by") for b in ledger["by_ticker"].values())
    assert not (package_free_run["run_dir"] / "packages").exists()


def test_options_macro_contexts_come_from_the_run_reference_without_packages(package_free_run):
    from scripts.avshunter_options_intelligence import load_package_macro_contexts
    output_dir = str(package_free_run["run_dir"] / "options")
    # The fixture's runtime macro carries no enrichment extras: no contexts, no fabrication.
    assert load_package_macro_contexts(RUN, output_dir) == {}
    runtime = package_free_run["run_dir"] / "macro" / "macro_runtime_gex_synced.json"
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    payload["extras"] = {"macro_exposure_index": {"AAA": [{"theme_id": "RATES"}]}}
    runtime.write_text(json.dumps(payload), encoding="utf-8")
    contexts = load_package_macro_contexts(RUN, output_dir)
    assert set(contexts) == {"AAA", "BBB"}  # one run-level payload, cited for every manifest ticker
    assert contexts["AAA"]["extras"]["macro_exposure_index"]["AAA"][0]["theme_id"] == "RATES"


def test_latest_pointer_is_gated_on_the_manifest_not_the_package_index(package_free_run, monkeypatch):
    import intelligent_orchestrator as orch
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", package_free_run["runs_dir"])
    monkeypatch.setattr(orch.cfg, "OUTPUT_DIR", package_free_run["base"] / "data" / "output")
    orch.write_latest_json(RUN, RUN)
    latest = json.loads((package_free_run["base"] / "data" / "output" / "latest.json").read_text(encoding="utf-8"))
    assert latest["run_id"] == RUN


def test_market_profile_stage_takes_its_worklist_from_the_manifest_without_packages(package_free_run):
    # PKG-F5 (28 Sep 2026): the earlier "tolerant" rule (empty worklist) built 0 profiles and made
    # the run fatal for the Lab. The worklist is the manifest's tickers; package paths are None.
    from scripts.build_completed_market_profiles import _worklist
    assert _worklist(package_free_run["run_dir"], package_free_run["base"]) == [("AAA", None), ("BBB", None)]
