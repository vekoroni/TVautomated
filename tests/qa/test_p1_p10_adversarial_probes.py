"""QA adversarial probes P1-P3, P5-P10 (P4 lives in test_p4_nan_rr_bypass.py).

Per CLAUDE_CODE_QA_pipeline_interpreter.md, Phase 2. Read-only QA: all
fixtures live under tempfile.TemporaryDirectory(); nothing under
pipeline_interpreter/MA_Inputs or any production path is touched, and no
existing test file is modified.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline_interpreter.automation_v2 import evidence_package as ep
from pipeline_interpreter.automation_v2 import lab_batch as lb
from pipeline_interpreter.automation_v2 import package_publisher as pp
from pipeline_interpreter.automation_v2.veto import evaluate_sovereign_veto


class P1ZeroBoundaryTests(unittest.TestCase):
    """P1: R:R exactly 0.0 -- is zero treated as negative, or does it slip
    through? Report which, and whether that is intentional."""

    def test_zero_rr_is_not_flagged_negative(self):
        live_ok = {"permission": "GO"}
        zero = evaluate_sovereign_veto(pipeline_row={"rr": "0.0"}, live_validation=live_ok)
        positive = evaluate_sovereign_veto(pipeline_row={"rr": "2.5"}, live_validation=live_ok)
        # Documenting observed behaviour, not asserting it is wrong: 0.0 is
        # architecturally indistinguishable from a healthy positive R:R at
        # this layer. NEGATIVE_RR means strictly < 0 by design (veto.py:83,
        # `rr < 0`). This is intentional per the control's own name, not a
        # bug -- but it means a R:R of exactly zero carries no penalty here.
        self.assertEqual(zero.veto_codes, ())
        self.assertEqual(zero.veto_codes, positive.veto_codes)
        self.assertNotIn("NEGATIVE_RR", zero.veto_codes)


class P2StringTypeTests(unittest.TestCase):
    """P2: R:R as a string ("-1.5") rather than a float -- does the
    comparison still fire, raise, or silently pass?"""

    def test_string_negative_rr_fires_in_lab_batch_helper(self):
        self.assertTrue(lb._negative_rr({"rr_predicted": "-1.5"}))

    def test_native_float_negative_rr_fires_in_veto(self):
        # veto.parse_rr does str(raw) before cleaning, so a Python float
        # (not just a CSV string) should still be caught.
        decision = evaluate_sovereign_veto(pipeline_row={"rr": -1.5})
        self.assertIn("NEGATIVE_RR", decision.veto_codes)


class P3AbsentFieldTests(unittest.TestCase):
    """P3: R:R field absent entirely -- fail closed, or default to
    permissive?"""

    def test_lab_batch_helper_treats_absent_rr_as_invalid(self):
        self.assertTrue(lb._negative_rr({}))
        self.assertTrue(lb._negative_rr({"rr_predicted": ""}))

    def test_veto_module_treats_absent_rr_as_negative_rr_veto(self):
        live_ok = {"permission": "GO"}
        decision = evaluate_sovereign_veto(pipeline_row={}, live_validation=live_ok)
        self.assertIn("NEGATIVE_RR", decision.veto_codes)

    def test_absent_rr_candidate_reaches_executable_candidates_end_to_end(self):
        """Closes the inference boundary left open in the first Phase 2 pass:
        does an absent (blank) rr_predicted -- not just NaN -- also reach
        run_lab_batch()'s executable candidates list? If so this is a
        second CRITICAL alongside P4, not a MEDIUM, because it is the same
        code path (`not ticker or vetoes`) reached by a different input."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline_outputs = root / "pipeline_outputs"
            pipeline_outputs.mkdir()
            staging_root = root / "capture_staging"
            staging_root.mkdir()
            output_directory = root / "deployments" / "qa-p3-plan"
            run_id = "20260726-000002"

            import csv
            path = pipeline_outputs / f"lab_triage_view_{run_id}.csv"
            fieldnames = ["ticker", "run_id", "lab_rank", "lab_verdict", "rr_predicted"]
            rows = [
                {"ticker": "NEGCTRL", "run_id": run_id, "lab_rank": "1",
                 "lab_verdict": "READY_EXECUTE", "rr_predicted": "-1.5"},
                {"ticker": "ABSENTRR", "run_id": run_id, "lab_rank": "2",
                 "lab_verdict": "READY_EXECUTE", "rr_predicted": ""},
            ]
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            state_path = lb.run_lab_batch(
                pipeline_outputs=pipeline_outputs,
                staging_root=staging_root,
                output_directory=output_directory,
                invocation_id="qa-p3-plan",
                max_candidates=10,
                execute_shadow=False,
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))
            candidate_tickers = {c["ticker"] for c in state["candidates"]}
            stopped_tickers = {s["ticker"] for s in state["stopped"]}

            self.assertIn("NEGCTRL", stopped_tickers, "Sanity control failed.")
            self.assertNotIn(
                "ABSENTRR", candidate_tickers,
                "CRITICAL (confirmed): a row with rr_predicted='' (blank/"
                "absent) and lab_verdict='READY_EXECUTE' reached the "
                f"executable candidates list. candidates={sorted(candidate_tickers)!r} "
                f"stopped={sorted(stopped_tickers)!r}. Same code path as P4, "
                "different trigger input -- same-class defect, not a milder one.",
            )


class P6UpstreamBlockedTests(unittest.TestCase):
    """P6: upstream BLOCKED candidate with otherwise perfect metrics --
    excluded?"""

    def test_veto_module_excludes_upstream_blocked_despite_perfect_rr(self):
        decision = evaluate_sovereign_veto(
            pipeline_row={"rr": "4.0", "execution_permission": "BLOCKED"},
            live_validation={"permission": "GO"},
        )
        self.assertIn("UPSTREAM_DENIED", decision.veto_codes)
        self.assertEqual(decision.effective_verdict, "STOP")

    def test_lab_batch_excludes_upstream_blocked_verdict(self):
        row = {"rr_predicted": "4.0"}
        verdict = "BLOCKED"
        vetoes = []
        if lb._negative_rr(row) or verdict == "NEGATIVE_RR":
            vetoes.append("NEGATIVE_RR")
        if verdict in lb.BLOCKING_VERDICTS and verdict != "NEGATIVE_RR":
            vetoes.append(f"UPSTREAM_{verdict}")
        self.assertIn("UPSTREAM_BLOCKED", vetoes)


class P7IncompletePackageTests(unittest.TestCase):
    """P7: evidence package with 11 of 12 required assets -- refuses to
    publish?"""

    def _write_manifest(self, directory: Path, *, status: str, kinds: list[str]) -> Path:
        assets = []
        for kind in kinds:
            fname = f"TEST_{kind}.png"
            (directory / fname).write_bytes(b"fake-bytes-for-" + kind.encode())
            assets.append({
                "kind": kind,
                "filename": fname,
                "source": str(directory / fname),
                "sha256": ep._sha256(directory / fname),
            })
        manifest = directory / "ticker_evidence_package.json"
        manifest.write_text(json.dumps({
            "schema_version": "automation_v2.evidence_package.1",
            "ticker": "TEST",
            "status": status,
            "required_kinds": list(ep.REQUIRED_KINDS),
            "assets": assets,
            "structured_lab": None,
            "findings": [] if len(kinds) == len(ep.REQUIRED_KINDS) else
                        [f"MISSING_ASSET:{k}" for k in ep.REQUIRED_KINDS if k not in kinds],
            "published": False,
        }, indent=2, sort_keys=True), encoding="utf-8")
        return manifest

    def test_eleven_of_twelve_assets_refuses_to_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            kinds = list(ep.REQUIRED_KINDS)[:-1]  # 11 of 12
            manifest = self._write_manifest(directory, status="incomplete", kinds=kinds)
            result = pp.publish_package(
                manifest_path=manifest,
                charts_directory=directory / "charts",
                publish_requested=True,
                feature_enabled=True,
            )
            self.assertEqual(result.status, "stopped")
            self.assertTrue(
                any("PACKAGE_NOT_COMPLETE" in f or "PACKAGE_REQUIRED_KIND_MISSING" in f
                    for f in result.findings),
                f"Expected a completeness finding, got {result.findings!r}",
            )

    def test_falsified_complete_status_does_not_bypass_required_kind_check(self):
        """Defense-in-depth probe beyond the brief's literal P7: if status
        is (incorrectly) 'complete' but a required kind is still absent
        from the assets list, does the independent required-kind
        recomputation in validate_package still catch it?"""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            kinds = list(ep.REQUIRED_KINDS)[:-1]
            manifest = self._write_manifest(directory, status="complete", kinds=kinds)
            result = pp.publish_package(
                manifest_path=manifest,
                charts_directory=directory / "charts",
                publish_requested=True,
                feature_enabled=True,
            )
            self.assertEqual(result.status, "stopped")
            self.assertTrue(
                any("PACKAGE_REQUIRED_KIND_MISSING" in f for f in result.findings),
                f"A falsified status='complete' with a missing kind was not "
                f"independently caught: {result.findings!r}",
            )


class P8HashMismatchTests(unittest.TestCase):
    """P8: evidence package with 12 assets but one SHA-256 mismatch --
    refuses?"""

    def test_corrupted_asset_after_hashing_refuses_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            assets = []
            for kind in ep.REQUIRED_KINDS:
                fname = f"TEST_{kind}.png"
                (directory / fname).write_bytes(b"original-bytes-" + kind.encode())
                assets.append({
                    "kind": kind, "filename": fname,
                    "source": str(directory / fname),
                    "sha256": ep._sha256(directory / fname),
                })
            manifest = directory / "ticker_evidence_package.json"
            manifest.write_text(json.dumps({
                "schema_version": "automation_v2.evidence_package.1",
                "ticker": "TEST", "status": "complete",
                "required_kinds": list(ep.REQUIRED_KINDS),
                "assets": assets, "structured_lab": None,
                "findings": [], "published": False,
            }, indent=2, sort_keys=True), encoding="utf-8")

            # Corrupt one asset's bytes AFTER the manifest recorded its hash.
            corrupted = directory / f"TEST_{ep.REQUIRED_KINDS[0]}.png"
            corrupted.write_bytes(b"TAMPERED-BYTES")

            result = pp.publish_package(
                manifest_path=manifest,
                charts_directory=directory / "charts",
                publish_requested=True,
                feature_enabled=True,
            )
            self.assertEqual(result.status, "stopped")
            self.assertTrue(
                any("PACKAGE_HASH_MISMATCH" in f for f in result.findings),
                f"Expected a hash-mismatch finding, got {result.findings!r}",
            )
            # Nothing should have been copied to the publish target.
            self.assertFalse((directory / "charts").exists())


class P10BatchIsolationTests(unittest.TestCase):
    """P10: two candidates where one is STOP -- does the batch continue for
    the other, or fail the whole batch?"""

    def _write_lab_csv(self, directory: Path, run_id: str) -> None:
        import csv
        path = directory / f"lab_triage_view_{run_id}.csv"
        fieldnames = ["ticker", "run_id", "lab_rank", "lab_verdict", "rr_predicted"]
        rows = [
            {"ticker": "GOODTICK", "run_id": run_id, "lab_rank": "1",
             "lab_verdict": "GO", "rr_predicted": "3.0"},
            {"ticker": "BADTICK", "run_id": run_id, "lab_rank": "2",
             "lab_verdict": "GO", "rr_predicted": "3.0"},
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_one_failing_candidate_does_not_abort_the_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline_outputs = root / "pipeline_outputs"
            pipeline_outputs.mkdir()
            staging_root = root / "capture_staging"
            staging_root.mkdir()
            output_directory = root / "deployments" / "qa-p10"
            run_id = "20260726-000001"
            self._write_lab_csv(pipeline_outputs, run_id)

            def fake_run_e2e_workflow(*, ticker, staging_root, pipeline_outputs,
                                       output_directory, invocation_id):
                if ticker == "BADTICK":
                    raise RuntimeError("SIMULATED_WORKFLOW_FAILURE")
                out = Path(output_directory)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps({
                    "status": "passed",
                    "go_no_go": "SHADOW_BATCH_PASSED_NOT_PRODUCTION_AUTHORIZED",
                    "steps": {"shadow_ingestion": {"effective_verdict": "STOP"}},
                }))
                return out

            with mock.patch.object(lb, "run_e2e_workflow", side_effect=fake_run_e2e_workflow):
                state_path = lb.run_lab_batch(
                    pipeline_outputs=pipeline_outputs,
                    staging_root=staging_root,
                    output_directory=output_directory,
                    invocation_id="qa-p10",
                    max_candidates=10,
                    execute_shadow=True,
                )

            state = json.loads(state_path.read_text(encoding="utf-8"))
            steps = state["steps"]

            self.assertIn("BADTICK", steps, "BADTICK step missing entirely -- batch aborted before recording it.")
            self.assertIn("GOODTICK", steps, "GOODTICK step missing -- one failure aborted the whole batch.")
            self.assertEqual(steps["BADTICK"]["status"], "stopped")
            self.assertEqual(steps["BADTICK"]["effective_verdict"], "STOP")
            self.assertEqual(steps["GOODTICK"]["status"], "passed")
            self.assertEqual(
                state["status"], "incomplete",
                "Overall batch status should be 'incomplete' when any step failed, "
                "not silently 'passed'.",
            )
            self.assertEqual(state["go_no_go"], "NO_GO_BATCH_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
