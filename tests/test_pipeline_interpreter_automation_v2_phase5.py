from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline_interpreter.automation_v2.cli import main as cli_main
from pipeline_interpreter.automation_v2.field_comparison import (
    compare_trade_briefs,
)
from pipeline_interpreter.automation_v2.fixture_provider import (
    FixtureResponseProvider,
)
from pipeline_interpreter.automation_v2.metrics import (
    AcceptanceThresholds,
    TrialMetric,
    evaluate_acceptance,
)
from pipeline_interpreter.automation_v2.live_provider import (
    _load_repository_anthropic_key,
)
from pipeline_interpreter.automation_v2.replay import read_request_fixture
from pipeline_interpreter.automation_v2.rollout import (
    RolloutMode,
    load_rollout_config,
    run_with_legacy_fallback,
)
from pipeline_interpreter.automation_v2.trial import run_shadow_trial


FIXTURES = Path(__file__).parent / "fixtures" / "pipeline_interpreter_automation_v2"


def main_response(ticker: str) -> str:
    return (
        f"[TRADE_NARRATIVE_{ticker}]\nNarrative.\n"
        "[TRADE_BRIEF_CSV]\n"
        "ticker,direction,final_verdict,trade_state,rr,horizon,dte\n"
        f"{ticker},PUT,GO,READY,2.5,1-5D,14\n"
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
        f"[{tag}]\n{tag}" for tag in tags
    )


def metric(**overrides) -> TrialMetric:
    values = {
        "ticker": "F",
        "run_id": "run",
        "invocation_id": "inv",
        "status": "complete",
        "effective_verdict": "WAIT",
        "duration_ms": 100,
        "provider_attempts": 1,
        "schema_valid": True,
        "artifact_complete": True,
        "sovereign_preserved": True,
        "evidence_valid": True,
    }
    values.update(overrides)
    return TrialMetric(**values)


class AcceptanceTests(unittest.TestCase):
    def test_acceptance_requires_minimum_volume_and_all_safety_invariants(self) -> None:
        report = evaluate_acceptance(
            [metric(invocation_id=f"inv-{index}") for index in range(5)]
        )
        self.assertTrue(report.accepted)
        self.assertEqual(report.sovereign_preserved_rate, 1.0)

    def test_acceptance_fails_closed_on_sovereign_or_sample_failure(self) -> None:
        report = evaluate_acceptance(
            [metric(sovereign_preserved=False)],
            AcceptanceThresholds(minimum_trials=2),
        )
        self.assertFalse(report.accepted)
        self.assertTrue(
            any(item.startswith("INSUFFICIENT_TRIALS") for item in report.failures)
        )
        self.assertTrue(
            any(
                item.startswith("SOVEREIGN_PRESERVED_RATE")
                for item in report.failures
            )
        )


class FieldComparisonTests(unittest.TestCase):
    def test_sovereign_fields_are_excluded_from_parity_measurement(self) -> None:
        legacy = {
            "ticker": "F",
            "direction": "PUT",
            "horizon": "1-5D",
            "final_verdict": "GO",
            "execution_permission": "EXEC",
        }
        shadow = {
            "ticker": "F",
            "direction": "PUT",
            "horizon": "1-5D",
            "final_verdict": "STOP",
            "execution_permission": "NONE_PIPELINE_INTERPRETER_ONLY",
        }
        report = compare_trade_briefs(legacy, shadow)
        self.assertNotIn(
            "final_verdict", [difference.field for difference in report.differences]
        )
        self.assertIn("final_verdict", report.sovereign_fields_excluded)


class RolloutTests(unittest.TestCase):
    def test_rollout_defaults_off_and_rejects_production_mode(self) -> None:
        self.assertEqual(load_rollout_config({}).mode, RolloutMode.OFF)
        with self.assertRaises(ValueError):
            load_rollout_config(
                {"AVSHUNTER_INTERPRETER_AUTOMATION_V2": "PRODUCTION"}
            )

    def test_shadow_failure_always_returns_legacy_result(self) -> None:
        observed = []

        def shadow():
            observed.append(True)
            raise RuntimeError("shadow failed")

        value = run_with_legacy_fallback(
            config=load_rollout_config(
                {"AVSHUNTER_INTERPRETER_AUTOMATION_V2": "SHADOW"}
            ),
            legacy=lambda: "LEGACY_RESULT",
            shadow_observer=shadow,
        )
        self.assertEqual(value, "LEGACY_RESULT")
        self.assertEqual(observed, [True])


class TrialTests(unittest.TestCase):
    def test_shadow_key_loader_overrides_process_precedence_without_logging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "ANTHROPIC_API_KEY=sk-ant-api03-test-value\n",
                encoding="utf-8",
            )
            self.assertEqual(
                _load_repository_anthropic_key(env_file),
                "sk-ant-api03-test-value",
            )

    def test_trial_emits_metrics_outside_hashed_artifact_directory(self) -> None:
        request = read_request_fixture(FIXTURES / "request_negative_rr.json")
        provider = FixtureResponseProvider(
            main_response("NEG"), story_response("NEG")
        )
        with tempfile.TemporaryDirectory() as directory:
            trial = run_shadow_trial(
                request=request,
                provider=provider,
                shadow_root=directory,
                retry_sleep=lambda _: None,
            )
            self.assertTrue(trial.metric.schema_valid)
            self.assertTrue(trial.metric.artifact_complete)
            self.assertTrue(trial.metric.sovereign_preserved)
            metric_path = Path(trial.metric_path)
            artifact_path = Path(trial.artifact_path)
            self.assertTrue(metric_path.is_file())
            self.assertEqual(metric_path.parent, artifact_path.parent)
            self.assertNotEqual(metric_path.parent, artifact_path)

    def test_live_cli_requires_explicit_billable_call_confirmation(self) -> None:
        with self.assertRaises(SystemExit) as context:
            cli_main(
                [
                    "run-live-shadow",
                    "--request",
                    str(FIXTURES / "request_clean_advisory.json"),
                    "--shadow-root",
                    "unused",
                ]
            )
        self.assertIn(
            "--confirm-shadow-live-provider is required", str(context.exception)
        )


if __name__ == "__main__":
    unittest.main()
