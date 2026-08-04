"""Bounded, stateless multi-ticker shadow coordination."""

from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .core import interpret_ticker
from .models import TickerRunRequest, TickerRunResult
from .renderers import publish_complete_shadow_artifacts
from .retry import RetryPolicy, RetryingProvider
from .serialization import to_plain
from .shadow import publish_shadow_result


ProviderFactory = Callable[[TickerRunRequest], object]


@dataclass(frozen=True, slots=True)
class BatchItem:
    ticker: str
    run_id: str
    invocation_id: str
    status: str
    effective_verdict: str
    attempts: int
    artifact_path: str
    error: str = ""


@dataclass(frozen=True, slots=True)
class BatchResult:
    batch_id: str
    items: tuple[BatchItem, ...]
    manifest_path: str


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(fd)
    temp = Path(temp_name)
    try:
        temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def run_batch(
    *,
    batch_id: str,
    requests: Iterable[TickerRunRequest],
    provider_factory: ProviderFactory,
    shadow_root: str | Path,
    max_workers: int = 2,
    retry_policy: RetryPolicy | None = None,
    retry_sleep: Callable[[float], None] | None = None,
) -> BatchResult:
    request_list = tuple(requests)
    if not batch_id.strip():
        raise ValueError("batch_id is required")
    if not request_list:
        raise ValueError("at least one request is required")
    if max_workers < 1:
        raise ValueError("max_workers must be at least one")
    identities = {
        (request.run_id, request.ticker, request.invocation_id)
        for request in request_list
    }
    if len(identities) != len(request_list):
        raise ValueError("duplicate run/ticker/invocation identity in batch")

    root = Path(shadow_root).resolve()

    def run_one(request: TickerRunRequest) -> BatchItem:
        provider = RetryingProvider(
            provider_factory(request),
            policy=retry_policy or RetryPolicy(),
            sleep=retry_sleep or __import__("time").sleep,
        )
        result: TickerRunResult = interpret_ticker(request, provider)
        if result.analysis is not None:
            artifact_path = publish_complete_shadow_artifacts(result, root)
        else:
            artifact_path = publish_shadow_result(result, root)
        return BatchItem(
            ticker=result.ticker,
            run_id=result.run_id,
            invocation_id=result.invocation_id,
            status=result.status.value,
            effective_verdict=result.effective_verdict,
            attempts=provider.attempts,
            artifact_path=str(artifact_path),
            error=result.provider_error,
        )

    items = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(request_list))) as pool:
        futures = {pool.submit(run_one, request): request for request in request_list}
        for future in as_completed(futures):
            items.append(future.result())
    items.sort(key=lambda item: (item.run_id, item.ticker, item.invocation_id))

    manifest_path = root / "batches" / f"batch_{batch_id}.json"
    if manifest_path.exists():
        raise FileExistsError(manifest_path)
    complete_count = sum(item.status == "complete" for item in items)
    stopped_count = sum(item.status == "stopped" for item in items)
    degraded_count = sum(item.status == "degraded" for item in items)
    _atomic_json(
        manifest_path,
        {
            "schema_version": "automation_v2.batch.1",
            "batch_id": batch_id,
            "shadow": True,
            "complete": degraded_count == 0,
            "counts": {
                "total": len(items),
                "complete": complete_count,
                "stopped": stopped_count,
                "degraded": degraded_count,
            },
            "items": [to_plain(item) for item in items],
        },
    )
    return BatchResult(
        batch_id=batch_id,
        items=tuple(items),
        manifest_path=str(manifest_path),
    )
