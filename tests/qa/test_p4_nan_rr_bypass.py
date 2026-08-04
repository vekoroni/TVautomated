"""QA adversarial probe P4 — NaN R:R sovereign-veto bypass.

Read-only QA test. Does not modify pipeline_interpreter/automation_v2 source.
Written under the QA brief (CLAUDE_CODE_QA_pipeline_interpreter.md), Phase 2,
probe P4: "R:R is NaN -- NaN < 0 is False in Python. Does a NaN R:R become GO?"

This module writes only under a per-test tempfile.TemporaryDirectory(); it
never touches pipeline_interpreter/MA_Inputs or any production path.
"""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pipeline_interpreter.automation_v2.lab_batch import _negative_rr, run_lab_batch
from pipeline_interpreter.automation_v2.veto import evaluate_sovereign_veto


class NegativeRRHelperNanBypassTests(unittest.TestCase):
    """Unit-level probe directly against lab_batch._negative_rr()."""

    def test_negative_rr_helper_does_not_silently_pass_nan(self):
        result = _negative_rr({"rr_predicted": "nan"})
        self.assertTrue(
            result,
            "_negative_rr({'rr_predicted': 'nan'}) returned False. "
            "A NaN R:R is being treated as 'not negative' -- the guard does "
            "not fire on NaN. Root cause: Decimal('nan') < 0 raises "
            "decimal.InvalidOperation, and that exception is caught by the "
            "same `except InvalidOperation: return False` clause meant for "
            "unparseable strings, conflating 'cannot parse' with 'NaN'.",
        )


class SovereignVetoNanBypassTests(unittest.TestCase):
    """Unit-level probe directly against veto.evaluate_sovereign_veto()."""

    def test_evaluate_sovereign_veto_does_not_crash_on_nan_rr(self):
        row = {
            "rr": "nan",
            "execution_permission": "READY_EXECUTE",
        }
        try:
            decision = evaluate_sovereign_veto(pipeline_row=row)
        except InvalidOperation as exc:
            self.fail(
                "evaluate_sovereign_veto() raised decimal.InvalidOperation "
                f"on a NaN R:R instead of returning a decision ({exc}). "
                "The comparison `rr < 0` in veto.py has no try/except, so "
                "a NaN R:R crashes this function outright rather than "
                "either vetoing or explicitly passing it. Whether that is "
                "fail-closed depends entirely on whether every caller of "
                "evaluate_sovereign_veto wraps it in a broad except -- "
                "core.interpret_ticker's try/except only wraps "
                "provider.analyze(), not this call."
            )
        self.assertIn(
            "NEGATIVE_RR",
            decision.veto_codes,
            "evaluate_sovereign_veto() did not crash on NaN R:R, but also "
            f"did not veto it: veto_codes={decision.veto_codes!r}, "
            f"effective_verdict={decision.effective_verdict!r}.",
        )


class LabBatchNanRRPlanningBypassTests(unittest.TestCase):
    """End-to-end probe: does a NaN-R:R row reach the executable candidate
    list produced by Phase 3's actual entry point, run_lab_batch(), with
    execute_shadow=False (the exact mode the QA brief's Phase 3 uses)?"""

    def _write_lab_csv(self, directory: Path, run_id: str) -> Path:
        path = directory / f"lab_triage_view_{run_id}.csv"
        fieldnames = ["ticker", "run_id", "lab_rank", "lab_verdict", "rr_predicted"]
        rows = [
            {
                "ticker": "NEGCTRL",
                "run_id": run_id,
                "lab_rank": "1",
                "lab_verdict": "READY_EXECUTE",
                "rr_predicted": "-1.5",
            },
            {
                "ticker": "NANBYPASS",
                "run_id": run_id,
                "lab_rank": "2",
                "lab_verdict": "READY_EXECUTE",
                "rr_predicted": "nan",
            },
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_nan_rr_candidate_does_not_reach_executable_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline_outputs = root / "pipeline_outputs"
            pipeline_outputs.mkdir()
            staging_root = root / "capture_staging"
            staging_root.mkdir()
            output_directory = root / "deployments" / "qa-p4-plan"
            run_id = "20260726-000000"

            self._write_lab_csv(pipeline_outputs, run_id)

            state_path = run_lab_batch(
                pipeline_outputs=pipeline_outputs,
                staging_root=staging_root,
                output_directory=output_directory,
                invocation_id="qa-p4-plan",
                max_candidates=10,
                execute_shadow=False,
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))

            candidate_tickers = {c["ticker"] for c in state["candidates"]}
            stopped_tickers = {s["ticker"] for s in state["stopped"]}

            self.assertIn(
                "NEGCTRL",
                stopped_tickers,
                "Sanity control failed: an ordinary negative R:R (-1.5) row "
                "did not land in 'stopped'. Test fixture or veto logic "
                "changed in a way that invalidates this probe.",
            )

            self.assertIn(
                "NANBYPASS",
                stopped_tickers,
                "CRITICAL: a row with rr_predicted='nan' and "
                "lab_verdict='READY_EXECUTE' was NOT placed in 'stopped' "
                f"by run_lab_batch(). candidates={sorted(candidate_tickers)!r} "
                f"stopped={sorted(stopped_tickers)!r}. "
                "This is Phase 3's actual planning entry point "
                "(execute_shadow=False) -- the same mode the QA brief's "
                "Phase 3 lab_batch_cli invocation uses. A human reading "
                "lab_batch_state.json would see NANBYPASS listed as a "
                "legitimate candidate, not flagged NEGATIVE_RR.",
            )
            self.assertNotIn(
                "NANBYPASS",
                candidate_tickers,
                "CRITICAL: rr_predicted='nan' reached the executable "
                "'candidates' list produced by run_lab_batch(). "
                f"candidates={sorted(candidate_tickers)!r}",
            )


if __name__ == "__main__":
    unittest.main()
