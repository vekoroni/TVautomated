"""Disabled-by-default bridge between legacy consumers and CDS-2 prices."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Iterable, Mapping

import pandas as pd

from .feature_flags import CanonicalFeatureFlags
from .historical_prices import HistoricalPriceDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "canonical" / "historical_prices.sqlite"
DEFAULT_HISTORY_MAX_STALENESS_DAYS = 5
_METRICS_LOCK = Lock()


def database_path(environment: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    configured = str(env.get("AVSHUNTER_HISTORICAL_PRICE_DB", "")).strip()
    return Path(configured) if configured else DEFAULT_DATABASE_PATH


def _flags(environment: Mapping[str, str] | None = None) -> CanonicalFeatureFlags:
    return CanonicalFeatureFlags.from_environment(environment)


def history_staleness_days(
    last_date: date | datetime | str | object,
    *,
    reference_date: date | None = None,
) -> int | None:
    """Return calendar age for one completed daily bar, or ``None`` if invalid."""
    try:
        if isinstance(last_date, datetime):
            resolved = last_date.date()
        elif isinstance(last_date, date):
            resolved = last_date
        else:
            resolved = datetime.fromisoformat(str(last_date).strip()[:10]).date()
        reference = reference_date or datetime.now(timezone.utc).date()
        return (reference - resolved).days
    except (TypeError, ValueError):
        return None


def history_date_is_fresh(
    last_date: date | datetime | str | object,
    *,
    max_staleness_days: int = DEFAULT_HISTORY_MAX_STALENESS_DAYS,
    reference_date: date | None = None,
) -> bool:
    """Apply the governed CDS-2 daily-history freshness contract."""
    age = history_staleness_days(last_date, reference_date=reference_date)
    return age is not None and 0 <= age <= max_staleness_days


def canonical_history_is_fresh(
    frame: pd.DataFrame | None,
    *,
    max_staleness_days: int = DEFAULT_HISTORY_MAX_STALENESS_DAYS,
    reference_date: date | None = None,
) -> bool:
    """Return whether a canonical frame can safely short-circuit a provider fetch."""
    if frame is None or frame.empty or "date" not in frame.columns:
        return False
    return history_date_is_fresh(
        frame["date"].max(),
        max_staleness_days=max_staleness_days,
        reference_date=reference_date,
    )


def read_canonical_history(
    ticker: str,
    *,
    bars: int | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    max_staleness_days: int | None = DEFAULT_HISTORY_MAX_STALENESS_DAYS,
    reference_date: date | None = None,
    environment: Mapping[str, str] | None = None,
) -> pd.DataFrame | None:
    """Return ACTIVE canonical history only when it satisfies freshness policy.

    Set ``max_staleness_days=None`` only for refresh code that needs to inspect
    the stale boundary before requesting and committing the missing tail.
    """
    flags = _flags(environment)
    if not flags.enabled or flags.ohlcv_mode != "ACTIVE":
        return None
    path = database_path(environment)
    if not path.exists():
        return None
    frame = HistoricalPriceDatabase(path).read(
        ticker, start_date=start_date, end_date=end_date, bars=bars
    )
    if frame.empty:
        return None
    last_date = frame["date"].max()
    frame.attrs["data_source"] = "CANONICAL_HISTORICAL_PRICE_DB"
    frame.attrs["data_as_of"] = str(last_date.date())
    frame.attrs["staleness_days"] = history_staleness_days(
        last_date, reference_date=reference_date
    )
    if max_staleness_days is not None and not canonical_history_is_fresh(
        frame,
        max_staleness_days=max_staleness_days,
        reference_date=reference_date,
    ):
        return None
    return frame


def write_through_fetched_history(
    ticker: str,
    data: pd.DataFrame | Iterable[Mapping[str, object]],
    *,
    provider: str,
    source_kind: str,
    source_run_id: str | None = None,
    partial_current_session: bool = False,
    environment: Mapping[str, str] | None = None,
):
    """Persist a successful full-OHLCV fetch before downstream consumption."""
    flags = _flags(environment)
    if not flags.enabled or not flags.write_through:
        return None
    path = database_path(environment)
    database = HistoricalPriceDatabase(path)
    database.initialise()
    partial_dates: tuple[str, ...] = ()
    if partial_current_session:
        partial_dates = (datetime.now(timezone.utc).date().isoformat(),)
    return database.ingest(
        ticker,
        data,
        provider=provider,
        source_kind=source_kind,
        source_run_id=source_run_id,
        partial_dates=partial_dates,
    )


def observe_shadow_history(
    ticker: str,
    legacy_frame: pd.DataFrame,
    *,
    consumer: str,
    environment: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Record parity metrics in SHADOW mode and always return legacy data."""
    flags = _flags(environment)
    if not flags.enabled or flags.ohlcv_mode != "SHADOW":
        return legacy_frame
    path = database_path(environment)
    if not path.exists() or legacy_frame is None or legacy_frame.empty:
        return legacy_frame
    canonical = HistoricalPriceDatabase(path).read(ticker)
    if canonical.empty:
        payload = {
            "ticker": ticker.strip().upper(),
            "consumer": consumer,
            "status": "CANONICAL_MISS",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        left = legacy_frame.copy()
        left.columns = [str(column).lower().strip() for column in left.columns]
        left["date"] = pd.to_datetime(left["date"], errors="coerce").dt.normalize()
        overlap = left.merge(canonical, on="date", suffixes=("_legacy", "_canonical"))
        maximum_close_difference = None
        if not overlap.empty:
            maximum_close_difference = float(
                (overlap["close_legacy"] - overlap["close_canonical"]).abs().max()
            )
        payload = {
            "ticker": ticker.strip().upper(),
            "consumer": consumer,
            "status": "COMPARED",
            "legacy_rows": len(left),
            "canonical_rows": len(canonical),
            "overlap_rows": len(overlap),
            "max_abs_close_difference": maximum_close_difference,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
    metrics_value = str(
        (os.environ if environment is None else environment).get(
            "AVSHUNTER_CDS2_METRICS_PATH", ""
        )
    ).strip()
    metrics_path = (
        Path(metrics_value)
        if metrics_value
        else PROJECT_ROOT / "data" / "canonical" / "shadow_metrics.jsonl"
    )
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with _METRICS_LOCK:
        with metrics_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")
    return legacy_frame
