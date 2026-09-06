"""One controlled live/offline shadow trial with metrics."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .core import interpret_ticker
from .metrics import TrialMetric
from .models import CAPITAL_DENIED, EXECUTION_NONE, TickerRunRequest
from .renderers import publish_complete_shadow_artifacts
from .retry import RetryPolicy, RetryingProvider
from .serialization import to_plain
from .shadow import publish_shadow_result


@dataclass(frozen=True, slots=True)
class TrialResult:
    metric: TrialMetric
    artifact_path: str
    metric_path: str


def run_shadow_trial(
    *,
    request: TickerRunRequest,
    provider: object,
    shadow_root: str | Path,
    retry_policy: RetryPolicy | None = None,
    retry_sleep=None,
) -> TrialResult:
    retrying = RetryingProvider(
        provider,
        policy=retry_policy or RetryPolicy(),
        sleep=retry_sleep or time.sleep,
    )
    started = time.perf_counter()
    result = interpret_ticker(request, retrying)
    duration_ms = round((time.perf_counter() - started) * 1000)
    if result.analysis is not None:
        artifact_path = publish_complete_shadow_artifacts(result, shadow_root)
        complete = (artifact_path / "artifact_manifest.json").is_file()
    else:
        artifact_path = publish_shadow_result(result, shadow_root)
        complete = False
    sovereign = (
        result.execution_permission == EXECUTION_NONE
        and result.capital_permission == CAPITAL_DENIED
        and result.eil_action == "STOP"
        and result.effective_verdict not in {"GO", "EXEC"}
    )
    error_class = (
        result.veto_codes[-1].split(":", 1)[-1]
        if result.provider_error and result.veto_codes
        else ""
    )
    metric = TrialMetric(
        ticker=result.ticker,
        run_id=result.run_id,
        invocation_id=result.invocation_id,
        status=result.status.value,
        effective_verdict=result.effective_verdict,
        duration_ms=duration_ms,
        provider_attempts=retrying.attempts,
        schema_valid=result.analysis is not None,
        artifact_complete=complete,
        sovereign_preserved=sovereign,
        evidence_valid=not result.findings,
        error_class=error_class,
    )
    metric_root = artifact_path.parent
    metric_name = (
        f"{artifact_path.name}.trial_metric.json"
        if artifact_path.is_dir()
        else f"{request.invocation_id}.trial_metric.json"
    )
    metric_path = metric_root / metric_name
    metric_path.write_text(
        json.dumps(to_plain(metric), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return TrialResult(metric, str(artifact_path), str(metric_path))

