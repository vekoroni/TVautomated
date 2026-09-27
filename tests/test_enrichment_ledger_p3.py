"""AVS-PKG-002 P3 — stage facts go to per-run enrichment ledgers, not back into input files.

Business rules (R2 one owner per fact; INT-001 §3 joins by run_id + ticker, never proximity):
- The trap engine (5.5), the actuarial pass (8.5) and the trigger layer (8.6) each append their
  per-ticker output to their own ledger `runs/<run>/enrichment/<stage>_<run>.jsonl`, keyed by
  run_id, ticker, calculation version and recorded time. While packages still exist the patch
  into the package continues unchanged (P3 keeps both).
- Readers (Options trap contexts, the EIL actuarial map, the post-hoc EIL injection, the
  trigger eligibility mirror) read the ledger first and fall back to packages; with the ledger
  present and the packages gone they return the same facts.
- A ledger from another run is refused; a missing ledger is a typed absence, never a zero.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.enrichment_ledger import (  # noqa: E402
    LEDGER_DIRNAME, ledger_path, load_actuarial_map, load_trap_contexts, load_trigger_blocks,
    read_enrichment_ledger, write_enrichment_ledger,
)

RUN = "20260925_230000"


def _package(ticker: str, **discovery) -> dict:
    return {
        "package_version": "v1", "ticker": ticker, "run_id": RUN,
        "discovery": {"ticker": ticker, "direction": "CALL", "stock_price": 50.0, **discovery},
        "macro": {"payload": {}}, "actuarial": {"deferred": True, "available": False},
    }


@pytest.fixture
def run_tree(tmp_path):
    base = tmp_path
    run_dir = base / "data" / "output" / "runs" / RUN
    pkg_dir = run_dir / "packages"
    pkg_dir.mkdir(parents=True)
    entries = []
    for ticker in ("AAA", "BBB"):
        path = pkg_dir / f"{ticker}.package.json"
        path.write_text(json.dumps(_package(ticker)), encoding="utf-8")
        entries.append({"ticker": ticker, "package_path": str(path), "status": "BUILT"})
    (pkg_dir / "index.json").write_text(json.dumps({"run_id": RUN, "packages": entries}), encoding="utf-8")
    (run_dir / "options").mkdir()
    return {"base": base, "run_dir": run_dir, "pkg_dir": pkg_dir}


# ------------------------------------------------------------------ the ledger contract
def test_ledger_round_trip_is_keyed_by_run_and_ticker_and_refuses_other_runs(run_tree):
    run_dir = run_tree["run_dir"]
    path = write_enrichment_ledger(run_dir, RUN, "trap", [
        {"ticker": "AAA", "payload": {"tle_verdict": "NO_TRADE"}, "calculation_version": "tle_v1"},
        {"ticker": "BBB", "payload": {"tle_verdict": "CHASE"}, "calculation_version": "tle_v1"},
        {"ticker": "AAA", "payload": {"tle_verdict": "EARLY_PROBE"}, "calculation_version": "tle_v1"},
    ])
    assert path == ledger_path(run_dir, "trap") == run_dir / LEDGER_DIRNAME / f"trap_{RUN}.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert all(r["run_id"] == RUN and r["stage"] == "trap" and r["recorded_at_utc"] for r in records)
    loaded = read_enrichment_ledger(run_dir, "trap")
    assert loaded["status"] == "PRESENT" and loaded["run_id"] == RUN and loaded["record_count"] == 3
    assert loaded["by_ticker"]["AAA"]["tle_verdict"] == "EARLY_PROBE"  # last record wins, append-only
    assert loaded["by_ticker"]["BBB"]["tle_verdict"] == "CHASE"
    # Another run's ledger is refused by identity, not by path.
    foreign = read_enrichment_ledger(run_dir, "trap", expected_run_id="20260101_000000")
    assert foreign["status"] == "RUN_MISMATCH" and foreign["by_ticker"] == {}
    absent = read_enrichment_ledger(run_dir, "actuarial")
    assert absent["status"] == "MISSING" and absent["by_ticker"] == {} and absent["record_count"] == 0


# ------------------------------------------------------------------ trap engine (5.5) -> Options
def test_trap_engine_writes_its_ledger_and_options_reads_it_without_packages(run_tree, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("avshunter_trap_engine_p3", ROOT / "avshunter_trap_engine.py")
    trap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trap)
    from scripts.avshunter_options_intelligence import load_package_tle_contexts

    assert trap.run_trap_layer(run_id=RUN, runs_dir=run_tree["base"] / "data" / "output" / "runs") is True
    from_packages = {t: json.loads((run_tree["pkg_dir"] / f"{t}.package.json").read_text(encoding="utf-8"))["tle"]
                     for t in ("AAA", "BBB")}
    ledger = read_enrichment_ledger(run_tree["run_dir"], "trap")
    assert ledger["status"] == "PRESENT" and ledger["by_ticker"] == from_packages

    output_dir = str(run_tree["run_dir"] / "options")
    with_packages = load_package_tle_contexts(RUN, output_dir)
    assert set(with_packages) == {"AAA", "BBB"} and with_packages["AAA"]["tle_verdict"]
    import shutil
    shutil.rmtree(run_tree["pkg_dir"])
    assert load_package_tle_contexts(RUN, output_dir) == with_packages
    assert load_trap_contexts(run_tree["run_dir"]) == with_packages


# ------------------------------------------------------------------ trigger layer (8.6) -> eligibility mirror
def test_trigger_layer_writes_its_ledger_and_eligibility_is_read_from_it(run_tree):
    from trigger_layer import patch_run_packages

    stats = patch_run_packages(run_id=RUN, base_dir=run_tree["base"], vanguard_csv_path=None)
    assert stats["patched"] == 2
    from_packages = {t: json.loads((run_tree["pkg_dir"] / f"{t}.package.json").read_text(encoding="utf-8"))["triggers"]
                     for t in ("AAA", "BBB")}
    blocks = load_trigger_blocks(run_tree["run_dir"])
    assert blocks == from_packages
    eligibility = {t: bool(b.get("go_eligible", False)) for t, b in blocks.items()}
    assert set(eligibility) == {"AAA", "BBB"}
    import shutil
    shutil.rmtree(run_tree["pkg_dir"])
    assert load_trigger_blocks(run_tree["run_dir"]) == from_packages


# ------------------------------------------------------------------ actuarial pass (8.5) -> EIL
def test_actuarial_pass_writes_its_ledger_and_the_eil_injection_reads_it_without_packages(run_tree, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("actuarial_enrichment_pass_p3", ROOT / "scripts" / "actuarial_enrichment_pass.py")
    aep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aep)
    # The no-Vanguard-row branch needs no actuarial cache; it still records what it decided.
    ticker, outcome = aep._patch_package(run_tree["pkg_dir"] / "AAA.package.json", None)
    assert (ticker, outcome) == ("AAA", "NO_VANGUARD_ROW")
    patched = json.loads((run_tree["pkg_dir"] / "AAA.package.json").read_text(encoding="utf-8"))["actuarial"]
    ledger = read_enrichment_ledger(run_tree["run_dir"], "actuarial")
    assert ledger["status"] == "PRESENT" and ledger["by_ticker"]["AAA"] == patched

    # A record with the enrichment marker is what the EIL consumers key on.
    write_enrichment_ledger(run_tree["run_dir"], RUN, "actuarial", [{
        "ticker": "BBB", "calculation_version": "actuarial_enrichment_pass",
        "payload": {"enriched_by": "actuarial_enrichment_pass", "win_rate_10d": 0.61, "efficiency_10d": 0.4,
                    "expected_move_10d": 0.07, "risk_10d": 0.03, "penalty_multiplier": 1.0, "valid": True,
                    "fallback_depth": 0, "sample_size": 120, "no_match": False},
    }])
    import shutil
    shutil.rmtree(run_tree["pkg_dir"])
    actuarial_map = load_actuarial_map(run_tree["run_dir"])
    assert set(actuarial_map) == {"BBB"}  # only enriched records, exactly as the package scan did
    assert actuarial_map["BBB"]["win_rate_10d"] == 0.61

    import intelligent_orchestrator as orch
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", run_tree["base"] / "data" / "output" / "runs")
    eil = run_tree["run_dir"] / "superbrain" / f"eil_enriched_{RUN}.csv"
    eil.parent.mkdir()
    with eil.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ticker", "score"])
        writer.writeheader(); writer.writerows([{"ticker": "AAA", "score": 1}, {"ticker": "BBB", "score": 2}])
    orch.inject_actuarial_into_eil_csv(RUN)
    with eil.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = {r["ticker"]: r for r in csv.DictReader(fh)}
    assert rows["BBB"]["actuarial_win_rate_10d"] in ("0.61", "0.61000")
    assert rows["AAA"]["actuarial_win_rate_10d"] in ("", "nan")  # no fact, no zero


def test_eil_runner_and_orchestrator_mirror_read_the_ledger_first():
    runner = (ROOT / "execution_intelligence_runner.py").read_text(encoding="utf-8", errors="replace")
    assert "load_actuarial_map(" in runner
    orchestrator = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8", errors="replace")
    assert "load_trigger_blocks(" in orchestrator
