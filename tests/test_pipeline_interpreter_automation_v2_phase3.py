from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from pipeline_interpreter.automation_v2.core import interpret_ticker
from pipeline_interpreter.automation_v2.models import (
    EvidenceManifest,
    RunStatus,
    TickerRunRequest,
)
from pipeline_interpreter.automation_v2.parser import parse_legacy_responses
from pipeline_interpreter.automation_v2.provider import (
    LegacyClaudeProvider,
    LegacyEnginePromptFactory,
)
from pipeline_interpreter.automation_v2.renderers import (
    publish_complete_shadow_artifacts,
)
from pipeline_interpreter.automation_v2.schemas import SchemaValidationError
from pipeline_interpreter.automation_v2.veto import NEGATIVE_RR


def main_response(ticker: str = "F", verdict: str = "GO", rr: str = "2.0") -> str:
    return (
        f"[TRADE_NARRATIVE_{ticker}]\nValidated narrative.\n"
        "[TRADE_BRIEF_CSV]\n"
        "ticker,direction,final_verdict,trade_state,rr,"
        "execution_permission,capital_permission\n"
        f"{ticker},PUT,{verdict},READY,{rr},EXEC,CAPITAL_APPROVED\n"
    )


def story_response(ticker: str = "F") -> str:
    sections = [
        ("SECTION_1_MACRO", "Macro"),
        ("SECTION_2_GAMMA", "Gamma"),
        ("SECTION_3_LIQUIDITY", "Liquidity"),
        ("SECTION_4_THESIS", "Thesis"),
        ("SECTION_5_CHART", "Chart"),
        ("SECTION_6_OPTIONS", "Options"),
        ("SECTION_7_RISK", "Risk"),
        ("SECTION_8_VERDICT", "Verdict"),
    ]
    return f"[JUNIOR_BRIEFING_{ticker}]\n" + "\n".join(
        f"[{tag}]\n{content}" for tag, content in sections
    )


def request(
    *,
    rr: str = "2.0",
    charts: tuple[str, ...] = (),
    invocation: str = "inv-phase3",
    lab_context: dict | None = None,
    macro_context: dict | None = None,
) -> TickerRunRequest:
    manifest = EvidenceManifest(
        ticker="F",
        run_id="run-1",
        invocation_id=invocation,
        as_of="2026-07-25T09:45:00Z",
    )
    return TickerRunRequest(
        ticker="F",
        run_id="run-1",
        invocation_id=invocation,
        manifest=manifest,
        pipeline_row={"ticker": "F", "rr": rr},
        lab_context=lab_context or {},
        chart_assets=charts,
        macro_context=macro_context or {},
        live_validation={"status": "LIVE_CONFIRMED"},
    )


class Factory:
    def __init__(self) -> None:
        self.main_requests = []
        self.story_requests = []

    def build_main(self, value: TickerRunRequest) -> str:
        self.main_requests.append(value)
        return f"MAIN:{value.ticker}:{len(value.chart_assets)}"

    def build_story(self, value: TickerRunRequest, main: str) -> str:
        self.story_requests.append((value, main))
        return f"STORY:{value.ticker}:{len(value.chart_assets)}"


class FakeApi:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append((prompt, kwargs))
        if prompt.startswith("MAIN:"):
            return main_response()
        return story_response()


class ParserSchemaTests(unittest.TestCase):
    def test_parses_complete_legacy_contract(self) -> None:
        parsed = parse_legacy_responses(
            ticker="F",
            main_response=main_response(),
            story_response=story_response(),
        )
        self.assertEqual(parsed.trade_brief.ticker, "F")
        self.assertEqual(parsed.trade_brief.final_verdict, "GO")
        self.assertEqual(len(parsed.junior_briefing.sections), 8)

    def test_markdown_separator_after_csv_is_not_a_second_trade_row(self) -> None:
        parsed = parse_legacy_responses(
            ticker="F",
            main_response=main_response() + "\n---\n",
            story_response=story_response(),
        )
        self.assertEqual(parsed.trade_brief.ticker, "F")

    def test_missing_trade_brief_fails_schema(self) -> None:
        with self.assertRaises(SchemaValidationError) as context:
            parse_legacy_responses(
                ticker="F",
                main_response="[TRADE_NARRATIVE_F]\nOnly narrative",
                story_response=story_response(),
            )
        self.assertIn("MAIN_MISSING:TRADE_BRIEF_CSV", context.exception.findings)

    def test_wrong_trade_brief_ticker_fails_schema(self) -> None:
        with self.assertRaises(SchemaValidationError) as context:
            parse_legacy_responses(
                ticker="F",
                main_response=main_response("NFLX"),
                story_response=story_response(),
            )
        self.assertTrue(
            any(
                finding.startswith("TRADE_BRIEF_TICKER_MISMATCH")
                for finding in context.exception.findings
            )
        )


class ProviderTests(unittest.TestCase):
    def test_concrete_factory_keeps_full_context_in_image_and_story_paths(self) -> None:
        calls = {"main": [], "story": []}

        def single_builder(ticker, pipeline_row, **kwargs):
            calls["main"].append((ticker, pipeline_row, kwargs))
            return "LEGACY_SINGLE"

        def story_builder(**kwargs):
            calls["story"].append(kwargs)
            return "LEGACY_STORY"

        value = request(
            charts=("F_daily.png",),
            lab_context={
                "lab_verdict": "STOP",
                "conflict_state": "HARD_CONFLICT",
            },
            macro_context={"regime": "RISK_OFF"},
        )
        factory = LegacyEnginePromptFactory(single_builder, story_builder)
        main = factory.build_main(value)
        story = factory.build_story(value, main_response="VALIDATED")
        self.assertEqual(len(calls["main"]), 1)
        self.assertTrue(main.startswith("AUTOMATION V2 OUTPUT ORDER"))
        self.assertLess(
            main.index("[TRADE_BRIEF_CSV]"),
            main.index("LEGACY_SINGLE"),
        )
        self.assertTrue(calls["main"][0][2]["chart_images_present"])
        self.assertIn("HARD_CONFLICT", main)
        self.assertIn("RISK_OFF", main)
        self.assertIn("HARD_CONFLICT", story)
        self.assertIn("RISK_OFF", story)
        self.assertIn("VALIDATED", story)
        self.assertEqual(calls["story"][0]["chart_images"], ["F_daily.png"])

    def test_images_and_complete_request_reach_both_model_stages(self) -> None:
        factory = Factory()
        api = FakeApi()
        provider = LegacyClaudeProvider(factory, api)
        value = request(charts=("F_daily.png", "F_options_chain.png"))
        payload = provider.analyze(value)
        self.assertEqual(payload.proposed_verdict, "GO")
        self.assertIs(factory.main_requests[0], value)
        self.assertIs(factory.story_requests[0][0], value)
        self.assertEqual(len(api.calls), 2)
        self.assertEqual(
            api.calls[0][1]["images"],
            ["F_daily.png", "F_options_chain.png"],
        )
        self.assertEqual(api.calls[0][1]["images"], api.calls[1][1]["images"])
        self.assertTrue(api.calls[0][1]["use_web_search"])
        self.assertTrue(api.calls[1][1]["use_web_search"])

    def test_schema_failure_degrades_core_to_stop(self) -> None:
        factory = Factory()

        def invalid_api(prompt: str, **kwargs) -> str:
            return "[TRADE_NARRATIVE_F]\nMissing structured contract"

        result = interpret_ticker(
            request(), LegacyClaudeProvider(factory, invalid_api)
        )
        self.assertEqual(result.status, RunStatus.DEGRADED)
        self.assertEqual(result.effective_verdict, "STOP")
        self.assertIn("SchemaValidationError", result.veto_codes[-1])


class RendererTests(unittest.TestCase):
    def _result(self, rr: str = "-1.0"):
        return interpret_ticker(
            request(rr=rr),
            LegacyClaudeProvider(Factory(), FakeApi()),
        )

    def test_complete_shadow_artifact_set_applies_sovereign_overlay(self) -> None:
        result = self._result()
        self.assertIn(NEGATIVE_RR, result.veto_codes)
        with tempfile.TemporaryDirectory() as directory:
            output = publish_complete_shadow_artifacts(result, directory)
            names = {path.name for path in output.iterdir()}
            self.assertEqual(len(names), 6)
            self.assertIn("artifact_manifest.json", names)
            csv_path = next(output.glob("ticker_f_trade_brief_*.csv"))
            with csv_path.open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["final_verdict"], "STOP")
            self.assertEqual(row["trade_state"], "STOPPED")
            self.assertEqual(row["eil_action"], "STOP")
            self.assertIn(NEGATIVE_RR, row["sovereign_vetoes"])
            self.assertEqual(
                row["execution_permission"], "NONE_PIPELINE_INTERPRETER_ONLY"
            )
            self.assertEqual(
                row["capital_permission"],
                "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION",
            )
            manifest = json.loads(
                (output / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(manifest["complete"])
            self.assertEqual(len(manifest["artifacts"]), 5)
            self.assertTrue(all(item["sha256"] for item in manifest["artifacts"]))

    def test_renderer_failure_leaves_no_final_invocation_directory(self) -> None:
        result = self._result(rr="2.0")

        def broken_renderer(result, row):
            raise RuntimeError("render failed")

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                publish_complete_shadow_artifacts(
                    result, directory, html_renderer=broken_renderer
                )
            final = (
                Path(directory)
                / result.run_id
                / result.ticker
                / result.invocation_id
            )
            self.assertFalse(final.exists())


if __name__ == "__main__":
    unittest.main()
