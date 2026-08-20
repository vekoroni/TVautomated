"""
eil_eod_resolver.py
AVSHUNTER Execution Intelligence Layer - EOD Cross-Sectional Resolver
Makeo Consulting Limited - May 2026

Provides cross-sectional enrichment for EOD runs.

Current status: compatibility stub. It exposes the interface expected by
execution_intelligence_runner.py and returns rows unchanged until the full
cross-sectional resolver is implemented.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
import logging
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_MARKET_OPEN_UTC = time(13, 30)
_MARKET_CLOSE_UTC = time(20, 15)
_VARIANCE_FIELDS = (
    "adx_14",
    "iv_percentile",
    "ivp",
    "atr_percentile_rank",
    "contract_spread_pct",
    "expected_move_pct",
)


def get_eil_data_mode(now: datetime | None = None) -> str:
    """
    Return the EIL data mode expected by execution_intelligence_runner.py.

    The full resolver will eventually make this calendar-aware. For now this
    mirrors the runner's simple UTC market-hours check so deploying this stub
    cannot crash EIL or accidentally force live behavior off-hours.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current_utc = current.astimezone(timezone.utc).time()
    return "LIVE" if _MARKET_OPEN_UTC <= current_utc <= _MARKET_CLOSE_UTC else "EOD_SYNTHETIC"


def resolve_eod_context(
    row: dict[str, Any],
    discovery_df=None,
    options_df=None,
    actuarial_df=None,
    run_id: str = "",
) -> dict[str, Any]:
    """
    Enrich a single EIL row with cross-sectional EOD context.

    Compatibility stub: returns a shallow copy of the input row unchanged.
    """
    ticker = row.get("ticker", "?") if isinstance(row, dict) else "?"
    logger.debug("eil_eod_resolver: compatibility pass-through for %s", ticker)
    return dict(row)


class EodContextResolver:
    """Compatibility wrapper exposing the .resolve(row) API used by EIL."""

    def __init__(self, run_dir: str | Path | None = None, base_dir: str | Path | None = None, **_: Any) -> None:
        self.run_dir = Path(run_dir).resolve() if run_dir else None
        self.base_dir = Path(base_dir).resolve() if base_dir else None

    def resolve(self, row: dict[str, Any]) -> dict[str, Any]:
        return resolve_eod_context(row, run_id=self.run_dir.name if self.run_dir else "")


def resolve_eod_context_batch(
    rows: list[dict[str, Any]],
    discovery_df=None,
    options_df=None,
    actuarial_df=None,
    run_id: str = "",
) -> list[dict[str, Any]]:
    """Batch version of resolve_eod_context."""
    return [resolve_eod_context(row, discovery_df, options_df, actuarial_df, run_id) for row in rows]


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def check_eod_variance(rows: Iterable[dict[str, Any]], min_std: float = 0.01) -> dict[str, Any]:
    """
    Lightweight non-blocking variance check used for EOD startup logging.

    Missing fields are ignored. With this compatibility stub, a low-variance
    result should warn only; it must never block the run.
    """
    materialized = list(rows)
    variances: dict[str, float] = {}
    frozen: list[str] = []

    for field in _VARIANCE_FIELDS:
        values = [_to_float(row.get(field)) for row in materialized if isinstance(row, dict)]
        values = [v for v in values if v is not None]
        if len(values) < 2:
            continue
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        std = variance ** 0.5
        variances[field] = std
        if std < min_std:
            frozen.append(field)

    return {
        "ok": not frozen,
        "n_rows": len(materialized),
        "frozen": frozen,
        "variances": variances,
    }
