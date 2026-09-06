"""Stateless, shadow-mode Pipeline Interpreter automation.

This package is intentionally not wired into the production command router.
"""

from .batch import BatchResult, run_batch
from .core import AnalysisProvider, interpret_ticker
from .legacy_adapter import LegacyInputSpec, build_request_from_legacy
from .metrics import (
    AcceptanceReport,
    AcceptanceThresholds,
    TrialMetric,
    evaluate_acceptance,
)
from .models import (
    AnalysisPayload,
    EvidenceItem,
    EvidenceManifest,
    RunStatus,
    TickerRunRequest,
    TickerRunResult,
)
from .provider import LegacyClaudeProvider, LegacyEnginePromptFactory
from .renderers import publish_complete_shadow_artifacts
from .retry import RetryPolicy, RetryingProvider
from .rollout import RolloutConfig, RolloutMode
from .veto import SovereignDecision, SovereignPolicy, evaluate_sovereign_veto

__all__ = [
    "AnalysisPayload",
    "AnalysisProvider",
    "AcceptanceReport",
    "AcceptanceThresholds",
    "BatchResult",
    "EvidenceItem",
    "EvidenceManifest",
    "LegacyInputSpec",
    "LegacyClaudeProvider",
    "LegacyEnginePromptFactory",
    "RunStatus",
    "RetryPolicy",
    "RetryingProvider",
    "RolloutConfig",
    "RolloutMode",
    "SovereignDecision",
    "SovereignPolicy",
    "TickerRunRequest",
    "TickerRunResult",
    "TrialMetric",
    "build_request_from_legacy",
    "evaluate_sovereign_veto",
    "evaluate_acceptance",
    "interpret_ticker",
    "publish_complete_shadow_artifacts",
    "run_batch",
]

