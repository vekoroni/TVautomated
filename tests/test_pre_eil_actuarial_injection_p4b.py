"""AVS-PKG-002 P4b — the pre-EIL actuarial injection reads the actuarial ledger, not packages.

Live proving of P4 (Evening 20260927_205123) surfaced one package reader the P4 survey missed:
the FIX-ACTUARIAL-SEQ block inside `evening_workflow` that stamps actuarial columns into
`superbrain_enriched` BEFORE EIL runs. It required `packages/` to exist, so on the package-free
Evening it skipped, left `_actuarial_loaded_before_eil` false, and the run's integrity label
degraded to ACTUARIAL_MISSING although the actuarial ledger held 1,616 enriched tickers.

Business rule: the injection sources its map exactly like every other consumer (ledger first,
package files as fallback) and reports its fill rate; with the ledger present and no packages
folder it patches the same rows it would have patched from the package files.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.enrichment_ledger import write_enrichment_ledger  # noqa: E402

RUN = "20260925_230000"


@pytest.fixture
def run_with_ledger(tmp_path, monkeypatch):
    import intelligent_orchestrator as orch
    runs = tmp_path / "data" / "output" / "runs"
    run_dir = runs / RUN
    (run_dir / "superbrain").mkdir(parents=True)
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", runs)
    sb = run_dir / "superbrain" / f"superbrain_enriched_{RUN}.csv"
    with sb.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "score"]); w.writeheader()
        w.writerows([{"ticker": "AAA", "score": 1}, {"ticker": "BBB", "score": 2}, {"ticker": "CCC", "score": 3}])
    write_enrichment_ledger(run_dir, RUN, "actuarial", [
        {"ticker": "AAA", "calculation_version": "actuarial_enrichment_pass",
         "payload": {"enriched_by": "actuarial_enrichment_pass", "win_rate_10d": 0.61, "efficiency_10d": 0.4,
                     "expected_move_10d": 0.07, "risk_10d": 0.03, "penalty_multiplier": 1.0, "valid": True,
                     "fallback_depth": 0, "sample_size": 120, "no_match": False}},
        {"ticker": "BBB", "calculation_version": "actuarial_enrichment_pass",
         "payload": {"enriched_by": "actuarial_enrichment_pass", "win_rate_10d": 0.52, "efficiency_10d": 0.3,
                     "expected_move_10d": 0.05, "risk_10d": 0.04, "penalty_multiplier": 0.9, "valid": True,
                     "fallback_depth": 1, "sample_size": 40, "no_match": False}},
        {"ticker": "CCC", "calculation_version": "actuarial_enrichment_pass",
         "payload": {"enriched_pass_attempted": True, "enrichment_pass_result": "NO_VANGUARD_ROW"}},
    ])
    assert not (run_dir / "packages").exists()
    return orch, run_dir, sb


def test_pre_eil_injection_is_a_function_that_reads_the_ledger_without_packages(run_with_ledger):
    orch, run_dir, sb = run_with_ledger
    result = orch.inject_actuarial_into_superbrain_pre_eil(RUN)
    assert result["source"] == "LEDGER"
    assert result["patched"] == 2 and result["total_rows"] == 3
    assert result["fill_rate"] == pytest.approx(2 / 3, abs=1e-4)  # reported to 4 dp, as the integrity JSON always has
    assert result["loaded_before_eil"] is False  # 66 % is below the 80 % soft gate: degraded, not trusted
    with sb.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = {r["ticker"]: r for r in csv.DictReader(fh)}
    assert rows["AAA"]["actuarial_win_rate_10d"] in ("0.61", "0.61000")
    assert rows["BBB"]["actuarial_enriched_by"] == "actuarial_enrichment_pass"
    assert rows["CCC"]["actuarial_win_rate_10d"] in ("", "nan")  # no fact, no zero
    assert rows["AAA"]["actuarial_loaded_pre_eil"] == "True"


def test_pre_eil_injection_reports_trusted_when_fill_rate_clears_the_soft_gate(run_with_ledger):
    orch, run_dir, sb = run_with_ledger
    write_enrichment_ledger(run_dir, RUN, "actuarial", [{
        "ticker": "CCC", "calculation_version": "actuarial_enrichment_pass",
        "payload": {"enriched_by": "actuarial_enrichment_pass", "win_rate_10d": 0.55, "efficiency_10d": 0.3,
                    "expected_move_10d": 0.05, "risk_10d": 0.04, "penalty_multiplier": 1.0, "valid": True,
                    "fallback_depth": 0, "sample_size": 90, "no_match": False}}], append=True)
    result = orch.inject_actuarial_into_superbrain_pre_eil(RUN)
    assert result["patched"] == 3 and result["fill_rate"] == pytest.approx(1.0)
    assert result["loaded_before_eil"] is True


def test_pre_eil_injection_is_typed_when_neither_ledger_nor_packages_exist(tmp_path, monkeypatch):
    import intelligent_orchestrator as orch
    runs = tmp_path / "runs"
    (runs / RUN / "superbrain").mkdir(parents=True)
    (runs / RUN / "superbrain" / f"superbrain_enriched_{RUN}.csv").write_text("ticker,score\nAAA,1\n", encoding="utf-8")
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", runs)
    result = orch.inject_actuarial_into_superbrain_pre_eil(RUN)
    assert result["source"] == "NONE" and result["patched"] == 0 and result["loaded_before_eil"] is False
    assert result["reason"] == "NO_ACTUARIAL_FACTS"


def test_evening_workflow_calls_the_function_and_keys_the_flag_on_its_result():
    import inspect
    import intelligent_orchestrator as orch
    source = inspect.getsource(orch.evening_workflow)
    assert "inject_actuarial_into_superbrain_pre_eil(" in source
    assert '_glob_seq.glob(str(_pkg_dir_seq / "*.package.json"))' not in source
