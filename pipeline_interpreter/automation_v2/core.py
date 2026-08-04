"""Pure ticker interpretation orchestration."""

from __future__ import annotations

from typing import Protocol

from .models import AnalysisPayload, RunStatus, TickerRunRequest, TickerRunResult
from .veto import (
    EVIDENCE_INVALID,
    SovereignPolicy,
    apply_sovereign_overlay,
    evaluate_sovereign_veto,
)


class AnalysisProvider(Protocol):
    def analyze(self, request: TickerRunRequest) -> AnalysisPayload:
        """Analyze the complete immutable request without mutating it."""


def interpret_ticker(
    request: TickerRunRequest,
    provider: AnalysisProvider,
    *,
    policy: SovereignPolicy | None = None,
) -> TickerRunResult:
    """Interpret one ticker without filesystem access or global mutation."""
    findings = request.manifest.validate()
    preflight = evaluate_sovereign_veto(
        pipeline_row=request.pipeline_row,
        evidence_findings=findings,
        live_validation=request.live_validation,
        policy=policy,
    )

    if EVIDENCE_INVALID in preflight.veto_codes:
        return TickerRunResult(
            ticker=request.ticker,
            run_id=request.run_id,
            invocation_id=request.invocation_id,
            status=RunStatus.STOPPED,
            proposed_verdict="NOT_RUN",
            effective_verdict=preflight.effective_verdict,
            veto_codes=preflight.veto_codes,
            eil_action=preflight.eil_action,
            findings=findings,
        )

    try:
        analysis = provider.analyze(request)
    except Exception as exc:
        provider_finding = f"ANALYSIS_PROVIDER_FAILURE:{type(exc).__name__}"
        veto_codes = tuple(dict.fromkeys((*preflight.veto_codes, provider_finding)))
        return TickerRunResult(
            ticker=request.ticker,
            run_id=request.run_id,
            invocation_id=request.invocation_id,
            status=RunStatus.DEGRADED,
            proposed_verdict="NOT_AVAILABLE",
            effective_verdict="STOP",
            veto_codes=veto_codes,
            eil_action="STOP",
            findings=findings,
            provider_error=str(exc),
        )

    effective = apply_sovereign_overlay(analysis.proposed_verdict, preflight)
    status = RunStatus.STOPPED if effective.blocked else RunStatus.COMPLETE
    return TickerRunResult(
        ticker=request.ticker,
        run_id=request.run_id,
        invocation_id=request.invocation_id,
        status=status,
        proposed_verdict=analysis.proposed_verdict.strip().upper() or "WAIT",
        effective_verdict=effective.effective_verdict,
        veto_codes=effective.veto_codes,
        eil_action=effective.eil_action,
        analysis=analysis,
        findings=findings,
    )
