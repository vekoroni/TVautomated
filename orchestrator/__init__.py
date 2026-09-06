"""AVSHUNTER orchestration services.

Core dynamic-session contracts are safe to import without initialising legacy
API, report or email clients.  Those compatibility exports remain available
through lazy attribute resolution.
"""
from importlib import import_module

__version__ = "1.0.0"

from .dynamic_thesis import (
    BUILD_THESIS_STAGES,
    ThesisBuildReceipt,
    ThesisStageResult,
    build_thesis,
)
from .dynamic_validation import (
    FrozenThesis,
    ThesisValidationEvent,
    UnderlyingObservation,
    ValidationBatchResult,
    ValidationTransition,
    persist_validation_event,
    validate_thesis,
    validate_theses,
)
from .dynamic_release import (
    EvidenceArtifact,
    GateEvidence,
    GateStatus,
    LIVE_GATE_IDS,
    PromotionStage,
    REQUIRED_GATE_IDS,
    ReleaseAssessment,
    ReleaseStatus,
    assess_release,
    load_evidence,
    promotion_environment,
    write_assessment_atomic,
)
from .dynamic_dispatcher import (
    AcceptedThesis,
    DispatchResult,
    execute_dispatch_plan,
    operator_summary,
    persist_dispatch_plan,
    requested_action_from_cli,
    resolve_accepted_thesis,
    resolve_dispatch_plan,
)

__all__ = [
    "BUILD_THESIS_STAGES",
    "ThesisBuildReceipt",
    "ThesisStageResult",
    "build_thesis",
    "AVSHUNTEROrchestrator",
    "DataCollector",
    "ClaudeIntelligence",
    "ReportGenerator",
    "EmailSender",
    "FrozenThesis",
    "ThesisValidationEvent",
    "UnderlyingObservation",
    "ValidationBatchResult",
    "ValidationTransition",
    "persist_validation_event",
    "validate_thesis",
    "validate_theses",
    "EvidenceArtifact",
    "GateEvidence",
    "GateStatus",
    "LIVE_GATE_IDS",
    "PromotionStage",
    "REQUIRED_GATE_IDS",
    "ReleaseAssessment",
    "ReleaseStatus",
    "assess_release",
    "load_evidence",
    "promotion_environment",
    "write_assessment_atomic",
    "AcceptedThesis",
    "DispatchResult",
    "execute_dispatch_plan",
    "operator_summary",
    "persist_dispatch_plan",
    "requested_action_from_cli",
    "resolve_accepted_thesis",
    "resolve_dispatch_plan",
]


_LAZY_LEGACY_EXPORTS = {
    "AVSHUNTEROrchestrator": (".main", "AVSHUNTEROrchestrator"),
    "DataCollector": (".collector", "DataCollector"),
    "ClaudeIntelligence": (".claude_api", "ClaudeIntelligence"),
    "ReportGenerator": (".report_generator", "ReportGenerator"),
    "EmailSender": (".email_sender", "EmailSender"),
}


def __getattr__(name: str):
    target = _LAZY_LEGACY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value

