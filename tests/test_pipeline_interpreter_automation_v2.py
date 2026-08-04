from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline_interpreter.automation_v2.core import interpret_ticker
from pipeline_interpreter.automation_v2.evidence import (
    build_chart_manifest,
    discover_ticker_assets,
    filename_belongs_to_ticker,
)
from pipeline_interpreter.automation_v2.models import (
    AnalysisPayload,
    EvidenceManifest,
    RunStatus,
    TickerRunRequest,
)
from pipeline_interpreter.automation_v2.shadow import run_shadow
from pipeline_interpreter.automation_v2.veto import NEGATIVE_RR


class StaticProvider:
    def __init__(self, verdict: str = "GO") -> None:
        self.verdict = verdict
        self.calls = 0

    def analyze(self, request: TickerRunRequest) -> AnalysisPayload:
        self.calls += 1
        return AnalysisPayload(
            proposed_verdict=self.verdict,
            narrative=f"{request.ticker} shadow analysis",
            trade_brief={"ticker": request.ticker},
        )


class FailingProvider:
    def analyze(self, request: TickerRunRequest) -> AnalysisPayload:
        raise RuntimeError("provider unavailable")


def make_request(
    ticker: str = "NFLX",
    rr: object = "2.5",
    invocation_id: str = "inv-1",
) -> TickerRunRequest:
    manifest = EvidenceManifest(
        ticker=ticker,
        run_id="run-1",
        invocation_id=invocation_id,
        as_of="2026-07-25T09:45:00Z",
    )
    return TickerRunRequest(
        ticker=ticker,
        run_id="run-1",
        invocation_id=invocation_id,
        manifest=manifest,
        pipeline_row={"ticker": ticker, "option_rr": rr},
        live_validation={"status": "LIVE_CONFIRMED"},
    )


class EvidenceIdentityTests(unittest.TestCase):
    def test_exact_ticker_token_prevents_f_nflx_collision(self) -> None:
        self.assertTrue(filename_belongs_to_ticker("F_daily.png", "F"))
        self.assertFalse(filename_belongs_to_ticker("NFLX_daily.png", "F"))
        self.assertTrue(filename_belongs_to_ticker("NFLX_daily.png", "NFLX"))

    def test_discovery_returns_only_exact_ticker_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "F_daily.png").write_bytes(b"f")
            (root / "NFLX_daily.png").write_bytes(b"nflx")
            found = discover_ticker_assets((root,), "F")
            self.assertEqual([path.name for path in found], ["F_daily.png"])

    def test_manifest_rejects_ambiguous_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "F_daily.png"
            wrong = root / "NFLX_daily.png"
            valid.write_bytes(b"f")
            wrong.write_bytes(b"nflx")
            manifest = build_chart_manifest(
                ticker="F",
                run_id="run-1",
                invocation_id="inv-1",
                as_of="2026-07-25T09:45:00Z",
                assets=(valid, wrong),
            )
            self.assertEqual(len(manifest.items), 1)
            self.assertIn(
                "REJECTED_AMBIGUOUS_ASSET:NFLX_daily.png", manifest.findings
            )


class SovereignVetoTests(unittest.TestCase):
    def test_negative_rr_is_negative_rr_stop_and_never_executes(self) -> None:
        provider = StaticProvider("GO")
        result = interpret_ticker(make_request(rr="-1.25"), provider)
        self.assertEqual(provider.calls, 1)
        self.assertIn(NEGATIVE_RR, result.veto_codes)
        self.assertEqual(result.effective_verdict, "STOP")
        self.assertEqual(result.eil_action, "STOP")
        self.assertNotIn(result.effective_verdict, {"GO", "EXEC"})
        self.assertEqual(result.execution_permission, "NONE_PIPELINE_INTERPRETER_ONLY")
        self.assertEqual(
            result.capital_permission,
            "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION",
        )

    def test_provider_go_cannot_promote_advisory_interpreter(self) -> None:
        result = interpret_ticker(make_request(), StaticProvider("GO"))
        self.assertEqual(result.status, RunStatus.COMPLETE)
        self.assertEqual(result.proposed_verdict, "GO")
        self.assertEqual(result.effective_verdict, "WAIT")
        self.assertEqual(result.eil_action, "STOP")

    def test_provider_failure_degrades_to_stop(self) -> None:
        result = interpret_ticker(make_request(), FailingProvider())
        self.assertEqual(result.status, RunStatus.DEGRADED)
        self.assertEqual(result.effective_verdict, "STOP")
        self.assertEqual(result.eil_action, "STOP")
        self.assertTrue(result.provider_error)


class StateIsolationAndShadowTests(unittest.TestCase):
    def test_sequential_requests_do_not_leak_ticker_context(self) -> None:
        provider = StaticProvider()
        first = interpret_ticker(make_request("F", invocation_id="inv-f"), provider)
        second = interpret_ticker(
            make_request("NFLX", invocation_id="inv-nflx"), provider
        )
        self.assertEqual(first.ticker, "F")
        self.assertEqual(second.ticker, "NFLX")
        self.assertEqual(first.analysis.trade_brief["ticker"], "F")
        self.assertEqual(second.analysis.trade_brief["ticker"], "NFLX")

    def test_shadow_publisher_uses_unique_invocation_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, output = run_shadow(
                make_request(invocation_id="inv-unique"),
                StaticProvider(),
                directory,
            )
            self.assertTrue(output.is_file())
            self.assertIn("inv-unique", output.parts)
            self.assertTrue(result.shadow)

    def test_execution_enabled_request_is_rejected(self) -> None:
        manifest = EvidenceManifest(
            ticker="F",
            run_id="run-1",
            invocation_id="inv-1",
            as_of="2026-07-25T09:45:00Z",
        )
        with self.assertRaises(ValueError):
            TickerRunRequest(
                ticker="F",
                run_id="run-1",
                invocation_id="inv-1",
                manifest=manifest,
                pipeline_row={"ticker": "F"},
                execution_enabled=True,
            )


if __name__ == "__main__":
    unittest.main()
