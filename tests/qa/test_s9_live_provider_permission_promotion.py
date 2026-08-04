"""QA extension to Phase 2, sovereign control S9, scoped to live_provider.py.

live_provider.py (untracked, new) wires the real Claude API into
core.interpret_ticker as an AnalysisProvider, and is exercised only by
tests/test_pipeline_interpreter_automation_v2_phase5.py -- a test file the
QA brief's declared Phase 1 command does not run. It imports the same
pipeline_interpreter_engine module carrying the dirty-tree chart-evidence
changes. A live-data provider is exactly where S9 (provider interpretation
cannot promote upstream permission) would fail if it were going to fail.

This test makes NO network calls and does not import live_provider.py's real
create_live_shadow_provider() (that would require a live .env credential and
would call the Anthropic API). Instead it exercises the exact seam
live_provider.py plugs into -- the AnalysisProvider protocol consumed by
core.interpret_ticker -- with a hostile fake standing in for what a
misbehaving or manipulated LLM response could produce. This isolates "does
the sovereign layer contain provider output" from "does the network call
work," and only the former is in scope for QA.
"""
from __future__ import annotations

import unittest

from pipeline_interpreter.automation_v2.core import interpret_ticker
from pipeline_interpreter.automation_v2.models import (
    AnalysisPayload,
    CAPITAL_DENIED,
    EXECUTION_NONE,
    EvidenceManifest,
    RunStatus,
    TickerRunRequest,
)


class _HostileLiveShapedProvider:
    """Stands in for live_provider.py's LegacyClaudeProvider: implements the
    same AnalysisProvider.analyze() contract that core.interpret_ticker
    consumes, but simulates an LLM response that claims full execution
    authority -- the worst case a live text-generation provider could
    produce."""

    def analyze(self, request: TickerRunRequest) -> AnalysisPayload:
        return AnalysisPayload(
            proposed_verdict="EXECUTE",
            narrative="Confident BUY signal, full size, execute immediately.",
            trade_brief={
                "execution_permission": "FULL_EXECUTE",
                "capital_permission": "APPROVED",
                "verdict": "GO",
            },
        )


def _clean_request(**overrides) -> TickerRunRequest:
    defaults = dict(
        ticker="AAPL",
        run_id="20260726-000000",
        invocation_id="qa-s9-live",
        manifest=EvidenceManifest(
            ticker="AAPL", run_id="20260726-000000",
            invocation_id="qa-s9-live", as_of="20260726-000000", items=(),
        ),
        pipeline_row={"rr": "4.0", "execution_permission": "GO"},
        lab_context={},
        chart_assets=(),
        live_validation={"permission": "GO"},
        shadow=True,
        execution_enabled=False,
    )
    defaults.update(overrides)
    return TickerRunRequest(**defaults)


class S9LiveShapedProviderCannotPromoteTests(unittest.TestCase):
    def test_hostile_execute_proposal_cannot_promote_permission_or_verdict(self):
        request = _clean_request()
        result = interpret_ticker(request, _HostileLiveShapedProvider())

        self.assertEqual(
            result.execution_permission, EXECUTION_NONE,
            f"A provider proposing EXECUTE promoted execution_permission to "
            f"{result.execution_permission!r}",
        )
        self.assertEqual(
            result.capital_permission, CAPITAL_DENIED,
            f"A provider proposing EXECUTE promoted capital_permission to "
            f"{result.capital_permission!r}",
        )
        self.assertNotIn(
            result.effective_verdict, {"GO", "EXECUTE", "READY_EXECUTE"},
            f"effective_verdict was promoted to {result.effective_verdict!r} "
            "by a hostile provider proposal.",
        )
        self.assertEqual(result.eil_action, "STOP")

    def test_hostile_provider_even_with_perfect_upstream_row_stays_capped(self):
        """Even when the upstream pipeline_row itself already looks
        execution-ready (a realistic 'everything upstream agrees' case),
        the provider's own proposal still cannot push past WAIT."""
        request = _clean_request(
            pipeline_row={
                "rr": "5.0",
                "execution_permission": "GO",
                "capital_permission": "APPROVED",
            },
        )
        result = interpret_ticker(request, _HostileLiveShapedProvider())
        self.assertEqual(result.execution_permission, EXECUTION_NONE)
        self.assertEqual(result.capital_permission, CAPITAL_DENIED)
        self.assertIn(result.effective_verdict, {"WAIT", "STOP"})


if __name__ == "__main__":
    unittest.main()
