"""Immutable domain contracts for Pipeline Interpreter automation v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


EXECUTION_NONE = "NONE_PIPELINE_INTERPRETER_ONLY"
CAPITAL_DENIED = "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION"


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return a shallow immutable copy suitable for a run boundary."""
    return MappingProxyType(dict(value or {}))


class RunStatus(str, Enum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    kind: str
    source: str
    ticker: str
    run_id: str
    as_of: str = ""
    sha256: str = ""
    required: bool = False
    fresh: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class EvidenceManifest:
    ticker: str
    run_id: str
    invocation_id: str
    as_of: str
    items: tuple[EvidenceItem, ...] = ()
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "findings", tuple(self.findings))

    def validate(self) -> tuple[str, ...]:
        findings = list(self.findings)
        if not self.ticker:
            findings.append("MISSING_TICKER")
        if not self.run_id:
            findings.append("MISSING_RUN_ID")
        if not self.invocation_id:
            findings.append("MISSING_INVOCATION_ID")
        for item in self.items:
            if item.ticker and item.ticker != self.ticker:
                findings.append(
                    f"TICKER_MISMATCH:{item.kind}:{item.ticker}:{self.ticker}"
                )
            if item.run_id and item.run_id != self.run_id:
                findings.append(
                    f"RUN_ID_MISMATCH:{item.kind}:{item.run_id}:{self.run_id}"
                )
            if item.required and not item.fresh:
                findings.append(f"STALE_REQUIRED_EVIDENCE:{item.kind}")
        return tuple(dict.fromkeys(findings))


@dataclass(frozen=True, slots=True)
class TickerRunRequest:
    ticker: str
    run_id: str
    invocation_id: str
    manifest: EvidenceManifest
    pipeline_row: Mapping[str, Any]
    lab_context: Mapping[str, Any] = field(default_factory=dict)
    option_context: tuple[Mapping[str, Any], ...] = ()
    chart_assets: tuple[str, ...] = ()
    macro_context: Mapping[str, Any] = field(default_factory=dict)
    sector_context: Mapping[str, Any] = field(default_factory=dict)
    trader_note: str = ""
    live_validation: Mapping[str, Any] = field(default_factory=dict)
    mode: str = "full"
    shadow: bool = True
    execution_enabled: bool = False

    def __post_init__(self) -> None:
        ticker = self.ticker.strip().upper()
        object.__setattr__(self, "ticker", ticker)
        object.__setattr__(self, "pipeline_row", _freeze_mapping(self.pipeline_row))
        object.__setattr__(self, "lab_context", _freeze_mapping(self.lab_context))
        object.__setattr__(
            self,
            "option_context",
            tuple(_freeze_mapping(row) for row in self.option_context),
        )
        object.__setattr__(self, "chart_assets", tuple(self.chart_assets))
        object.__setattr__(self, "macro_context", _freeze_mapping(self.macro_context))
        object.__setattr__(self, "sector_context", _freeze_mapping(self.sector_context))
        object.__setattr__(
            self, "live_validation", _freeze_mapping(self.live_validation)
        )
        if ticker != self.manifest.ticker:
            raise ValueError("request ticker must match evidence manifest ticker")
        if self.run_id != self.manifest.run_id:
            raise ValueError("request run_id must match evidence manifest run_id")
        if self.invocation_id != self.manifest.invocation_id:
            raise ValueError(
                "request invocation_id must match evidence manifest invocation_id"
            )
        if self.execution_enabled:
            raise ValueError("automation_v2 is shadow-only; execution cannot be enabled")


@dataclass(frozen=True, slots=True)
class AnalysisPayload:
    proposed_verdict: str = "WAIT"
    narrative: str = ""
    trade_brief: Mapping[str, Any] = field(default_factory=dict)
    junior_briefing: Mapping[str, Any] = field(default_factory=dict)
    raw_response: str = ""
    raw_story: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_brief", _freeze_mapping(self.trade_brief))
        object.__setattr__(
            self, "junior_briefing", _freeze_mapping(self.junior_briefing)
        )


@dataclass(frozen=True, slots=True)
class TickerRunResult:
    ticker: str
    run_id: str
    invocation_id: str
    status: RunStatus
    proposed_verdict: str
    effective_verdict: str
    veto_codes: tuple[str, ...]
    execution_permission: str = EXECUTION_NONE
    capital_permission: str = CAPITAL_DENIED
    eil_action: str = "STOP"
    analysis: AnalysisPayload | None = None
    findings: tuple[str, ...] = ()
    provider_error: str = ""
    completed_at: str = ""
    shadow: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "veto_codes", tuple(self.veto_codes))
        object.__setattr__(self, "findings", tuple(self.findings))
        if not self.completed_at:
            object.__setattr__(
                self,
                "completed_at",
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
        if self.execution_permission != EXECUTION_NONE:
            raise ValueError("interpreter execution permission must remain NONE")
        if self.capital_permission != CAPITAL_DENIED:
            raise ValueError("interpreter capital permission must remain denied")

