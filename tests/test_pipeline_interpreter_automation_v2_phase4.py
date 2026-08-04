from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline_interpreter.automation_v2.batch import run_batch
from pipeline_interpreter.automation_v2.cli import main as cli_main
from pipeline_interpreter.automation_v2.comparison import compare_legacy_to_shadow
from pipeline_interpreter.automation_v2.compatibility import (
    profile_legacy_artifacts,
)
from pipeline_interpreter.automation_v2.fixture_provider import (
    FixtureResponseProvider,
)
from pipeline_interpreter.automation_v2.models import AnalysisPayload
from pipeline_interpreter.automation_v2.replay import read_request_fixture
from pipeline_interpreter.automation_v2.retry import (
    RetryPolicy,
    RetryingProvider,
    is_retryable_provider_error,
)
from pipeline_interpreter.automation_v2.schemas import SchemaValidationError


FIXTURES = Path(__file__).parent / "fixtures" / "pipeline_interpreter_automation_v2"


def main_response(ticker: str, verdict: str = "GO") -> str:
    return (
        f"[TRADE_NARRATIVE_{ticker}]\nFixture narrative.\n"
        "[TRADE_BRIEF_CSV]\n"
        "ticker,direction,final_verdict,trade_state,rr\n"
        f"{ticker},CALL,{verdict},READY,3.0\n"
    )


def story_response(ticker: str) -> str:
    tags = (
        "SECTION_1_MACRO",
        "SECTION_2_GAMMA",
        "SECTION_3_LIQUIDITY",
        "SECTION_4_THESIS",
        "SECTION_5_CHART",
        "SECTION_6_OPTIONS",
        "SECTION_7_RISK",
        "SECTION_8_VERDICT",
    )
    return f"[JUNIOR_BRIEFING_{ticker}]\n" + "\n".join(
        f"[{tag}]\nFixture {tag}" for tag in tags
    )


class TransientProvider:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def analyze(self, request) -> AnalysisPayload:
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("temporary timeout")
        return FixtureResponseProvider(
            main_response(request.ticker), story_response(request.ticker)
        ).analyze(request)


class InvalidProvider:
    def analyze(self, request) -> AnalysisPayload:
        raise SchemaValidationError(("INVALID_MODEL_CONTRACT",))


class RetryTests(unittest.TestCase):
    def test_classifier_retries_only_transient_errors(self) -> None:
        self.assertTrue(is_retryable_provider_error(TimeoutError()))
        self.assertTrue(is_retryable_provider_error(ConnectionError()))
        self.assertFalse(
            is_retryable_provider_error(SchemaValidationError(("bad",)))
        )
        self.assertFalse(is_retryable_provider_error(ValueError("bad input")))

    def test_transient_provider_succeeds_after_bounded_retries(self) -> None:
        request = read_request_fixture(FIXTURES / "request_clean_advisory.json")
        base = TransientProvider(failures=2)
        sleeps = []
        provider = RetryingProvider(
            base,
            RetryPolicy(
                max_attempts=3,
                initial_backoff_seconds=0.1,
                multiplier=2,
                max_backoff_seconds=1,
            ),
            sleep=sleeps.append,
        )
        payload = provider.analyze(request)
        self.assertEqual(payload.proposed_verdict, "GO")
        self.assertEqual(provider.attempts, 3)
        self.assertEqual(sleeps, [0.1, 0.2])

    def test_schema_failure_is_not_retried(self) -> None:
        request = read_request_fixture(FIXTURES / "request_clean_advisory.json")
        provider = RetryingProvider(
            InvalidProvider(),
            RetryPolicy(max_attempts=3),
            sleep=lambda _: self.fail("must not sleep"),
        )
        with self.assertRaises(SchemaValidationError):
            provider.analyze(request)
        self.assertEqual(provider.attempts, 1)


class BatchTests(unittest.TestCase):
    def test_batch_is_bounded_unique_and_manifested(self) -> None:
        requests = [
            read_request_fixture(FIXTURES / "request_clean_advisory.json"),
            read_request_fixture(FIXTURES / "request_negative_rr.json"),
            read_request_fixture(FIXTURES / "request_upstream_denied.json"),
        ]

        def factory(request):
            return FixtureResponseProvider(
                main_response(request.ticker), story_response(request.ticker)
            )

        with tempfile.TemporaryDirectory() as directory:
            result = run_batch(
                batch_id="phase4",
                requests=requests,
                provider_factory=factory,
                shadow_root=directory,
                max_workers=2,
                retry_sleep=lambda _: None,
            )
            self.assertEqual(len(result.items), 3)
            self.assertEqual(
                [item.ticker for item in result.items], ["CLEAN", "DENY", "NEG"]
            )
            manifest = json.loads(
                Path(result.manifest_path).read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["counts"]["total"], 3)
            self.assertEqual(manifest["counts"]["complete"], 1)
            self.assertEqual(manifest["counts"]["stopped"], 2)
            self.assertEqual(manifest["counts"]["degraded"], 0)
            self.assertTrue(manifest["complete"])

    def test_duplicate_identity_is_rejected_before_work(self) -> None:
        value = read_request_fixture(FIXTURES / "request_clean_advisory.json")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                run_batch(
                    batch_id="duplicate",
                    requests=(value, value),
                    provider_factory=lambda _: InvalidProvider(),
                    shadow_root=directory,
                )


class ComparisonAndCliTests(unittest.TestCase):
    def test_comparison_reports_complete_sovereign_shadow(self) -> None:
        request = read_request_fixture(FIXTURES / "request_negative_rr.json")
        provider = FixtureResponseProvider(
            main_response("NEG"), story_response("NEG")
        )
        from pipeline_interpreter.automation_v2.core import interpret_ticker
        from pipeline_interpreter.automation_v2.renderers import (
            publish_complete_shadow_artifacts,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_raw = root / "legacy_raw.txt"
            legacy_story = root / "legacy_story.txt"
            legacy_html = root / "legacy.html"
            legacy_raw.write_text(
                "[TRADE_NARRATIVE_NEG]\nLegacy only", encoding="utf-8"
            )
            legacy_story.write_text(story_response("NEG"), encoding="utf-8")
            legacy_html.write_text("<html>legacy</html>", encoding="utf-8")
            legacy = profile_legacy_artifacts(
                ticker="NEG",
                raw_response=legacy_raw,
                raw_story=legacy_story,
                html=legacy_html,
            )
            shadow = publish_complete_shadow_artifacts(
                interpret_ticker(request, provider), root / "shadow"
            )
            report = compare_legacy_to_shadow(legacy, shadow)
            self.assertTrue(report.passed)
            self.assertFalse(report.legacy_complete)
            self.assertTrue(report.shadow_complete)
            self.assertTrue(report.sovereign_preserved)
            self.assertTrue(
                any(item.startswith("LEGACY_KNOWN_MISSING") for item in report.differences)
            )

    def test_cli_runs_fixture_without_live_provider(self) -> None:
        request = FIXTURES / "request_negative_rr.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.txt"
            story = root / "story.txt"
            main.write_text(main_response("NEG"), encoding="utf-8")
            story.write_text(story_response("NEG"), encoding="utf-8")
            code = cli_main(
                [
                    "run-fixture",
                    "--request",
                    str(request),
                    "--main-response",
                    str(main),
                    "--story-response",
                    str(story),
                    "--shadow-root",
                    str(root / "outputs"),
                ]
            )
            self.assertEqual(code, 0)
            artifacts = list((root / "outputs").rglob("artifact_manifest.json"))
            self.assertEqual(len(artifacts), 1)


if __name__ == "__main__":
    unittest.main()
