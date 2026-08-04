"""Shadow-only adapter and isolated artifact publisher."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .core import AnalysisProvider, interpret_ticker
from .models import TickerRunRequest, TickerRunResult
from .veto import SovereignPolicy


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, MappingProxyType):
        return {key: _json_value(item) for key, item in value.items()}
    if is_dataclass(value):
        return {
            item.name: _json_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def publish_shadow_result(
    result: TickerRunResult, shadow_root: str | Path
) -> Path:
    """Write only to an explicitly supplied shadow root."""
    root = Path(shadow_root).resolve()
    invocation_dir = root / result.run_id / result.ticker / result.invocation_id
    invocation_dir.mkdir(parents=True, exist_ok=False)
    output = invocation_dir / "ticker_run_result.shadow.json"
    output.write_text(
        json.dumps(_json_value(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output


def run_shadow(
    request: TickerRunRequest,
    provider: AnalysisProvider,
    shadow_root: str | Path,
    *,
    policy: SovereignPolicy | None = None,
) -> tuple[TickerRunResult, Path]:
    if not request.shadow or request.execution_enabled:
        raise ValueError("shadow runner accepts shadow-only, execution-disabled requests")
    result = interpret_ticker(request, provider, policy=policy)
    return result, publish_shadow_result(result, shadow_root)
