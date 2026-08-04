from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline_interpreter.automation_v2.compatibility import (
    profile_legacy_artifacts,
)
from pipeline_interpreter.automation_v2.legacy_adapter import (
    AmbiguousTickerError,
    LegacyInputSpec,
    MissingTickerError,
    build_request_from_legacy,
)
from pipeline_interpreter.automation_v2.replay import (
    read_request_fixture,
    write_request_fixture,
)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class LegacyAdapterTests(unittest.TestCase):
    def test_builds_request_only_from_exact_explicit_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pipeline = root / "pipeline.csv"
            lab = root / "lab.csv"
            charts = root / "charts"
            charts.mkdir()
            write_csv(
                pipeline,
                [
                    {"run_id": "run-1", "ticker": "F", "rr": "2.0"},
                    {"run_id": "run-1", "ticker": "NFLX", "rr": "3.0"},
                ],
            )
            write_csv(
                lab,
                [
                    {"run_id": "run-1", "ticker": "F", "lab_verdict": "WAIT"},
                    {"run_id": "run-1", "ticker": "NFLX", "lab_verdict": "GO"},
                ],
            )
            (charts / "F_daily.png").write_bytes(b"f")
            (charts / "NFLX_daily.png").write_bytes(b"nflx")
            request = build_request_from_legacy(
                LegacyInputSpec(
                    ticker="F",
                    run_id="run-1",
                    invocation_id="inv-1",
                    as_of=datetime.now(timezone.utc).isoformat(),
                    pipeline_csv=pipeline,
                    lab_csv=lab,
                    chart_roots=(charts,),
                    require_lab=True,
                )
            )
            self.assertEqual(request.pipeline_row["ticker"], "F")
            self.assertEqual(request.lab_context["ticker"], "F")
            self.assertEqual(
                [Path(path).name for path in request.chart_assets],
                ["F_daily.png"],
            )
            self.assertEqual(request.manifest.validate(), ())
            self.assertTrue(all(item.sha256 for item in request.manifest.items))

    def test_missing_exact_ticker_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pipeline = Path(directory) / "pipeline.csv"
            write_csv(pipeline, [{"run_id": "run-1", "ticker": "NFLX"}])
            with self.assertRaises(MissingTickerError):
                build_request_from_legacy(
                    LegacyInputSpec(
                        ticker="F",
                        run_id="run-1",
                        invocation_id="inv-1",
                        as_of=datetime.now(timezone.utc).isoformat(),
                        pipeline_csv=pipeline,
                    )
                )

    def test_duplicate_exact_ticker_fails_as_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pipeline = Path(directory) / "pipeline.csv"
            write_csv(
                pipeline,
                [
                    {"run_id": "run-1", "ticker": "F", "rr": "1"},
                    {"run_id": "run-1", "ticker": "F", "rr": "2"},
                ],
            )
            with self.assertRaises(AmbiguousTickerError):
                build_request_from_legacy(
                    LegacyInputSpec(
                        ticker="F",
                        run_id="run-1",
                        invocation_id="inv-1",
                        as_of=datetime.now(timezone.utc).isoformat(),
                        pipeline_csv=pipeline,
                    )
                )

    def test_row_run_mismatch_is_a_manifest_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pipeline = Path(directory) / "pipeline.csv"
            write_csv(pipeline, [{"run_id": "wrong-run", "ticker": "F"}])
            request = build_request_from_legacy(
                LegacyInputSpec(
                    ticker="F",
                    run_id="run-1",
                    invocation_id="inv-1",
                    as_of=datetime.now(timezone.utc).isoformat(),
                    pipeline_csv=pipeline,
                )
            )
            self.assertIn(
                "ROW_RUN_ID_MISMATCH:pipeline:wrong-run:run-1",
                request.manifest.validate(),
            )

    def test_stale_required_pipeline_is_a_manifest_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pipeline = Path(directory) / "pipeline.csv"
            write_csv(pipeline, [{"run_id": "run-1", "ticker": "F"}])
            request = build_request_from_legacy(
                LegacyInputSpec(
                    ticker="F",
                    run_id="run-1",
                    invocation_id="inv-1",
                    as_of=(
                        datetime.now(timezone.utc) + timedelta(hours=48)
                    ).isoformat(),
                    pipeline_csv=pipeline,
                    max_age_hours=1,
                )
            )
            self.assertIn(
                "STALE_REQUIRED_EVIDENCE:pipeline",
                request.manifest.validate(),
            )

    def test_request_round_trip_is_replayable_and_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pipeline = root / "pipeline.csv"
            fixture = root / "request.json"
            write_csv(
                pipeline,
                [{"run_id": "run-1", "ticker": "F", "rr": "-1.0"}],
            )
            request = build_request_from_legacy(
                LegacyInputSpec(
                    ticker="F",
                    run_id="run-1",
                    invocation_id="inv-1",
                    as_of=datetime.now(timezone.utc).isoformat(),
                    pipeline_csv=pipeline,
                )
            )
            write_request_fixture(request, fixture)
            replayed = read_request_fixture(fixture)
            self.assertEqual(replayed.ticker, request.ticker)
            self.assertEqual(dict(replayed.pipeline_row), dict(request.pipeline_row))
            self.assertEqual(
                replayed.manifest.items[0].sha256,
                request.manifest.items[0].sha256,
            )
            with self.assertRaises(TypeError):
                replayed.pipeline_row["rr"] = "9.0"


class CompatibilityContractTests(unittest.TestCase):
    def test_complete_synthetic_contract_profiles_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.txt"
            story = root / "story.txt"
            html = root / "ticker.html"
            raw.write_text(
                "[TRADE_NARRATIVE_F]\ntext\n[TRADE_BRIEF_CSV]\nheader\n",
                encoding="utf-8",
            )
            story.write_text(
                "\n".join(
                    [
                        "[JUNIOR_BRIEFING_F]",
                        "[SECTION_1_MACRO]",
                        "[SECTION_2_GAMMA]",
                        "[SECTION_3_LIQUIDITY]",
                        "[SECTION_4_THESIS]",
                        "[SECTION_5_CHART]",
                        "[SECTION_6_OPTIONS]",
                        "[SECTION_7_RISK]",
                        "[SECTION_8_VERDICT]",
                    ]
                ),
                encoding="utf-8",
            )
            html.write_text("<html></html>", encoding="utf-8")
            profile = profile_legacy_artifacts(
                ticker="F", raw_response=raw, raw_story=story, html=html
            )
            self.assertTrue(profile.complete)
            self.assertEqual(profile.missing_required, ())

    def test_observed_baseline_distinguishes_known_missing_contract(self) -> None:
        baseline = (
            Path(__file__).parents[1]
            / "pipeline_interpreter"
            / "automation_v2"
            / "baselines"
            / "legacy_observed_20260528.json"
        )
        value = json.loads(baseline.read_text(encoding="utf-8"))
        self.assertEqual(
            value["classification"],
            "observed_legacy_not_intended_complete_contract",
        )
        self.assertIn(
            "[TRADE_BRIEF_CSV]",
            value["runs"]["NFLX_20260528_2052"]["known_missing"],
        )


if __name__ == "__main__":
    unittest.main()
