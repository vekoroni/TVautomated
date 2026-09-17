"""Read-only access to canonical intraday underlying bars (``market_observations/intraday_bar``)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

DEFAULT_BAR_ROOT = Path(__file__).resolve().parents[3] / "data" / "canonical" / "market_observations" / "intraday_bar"


def _parse(timestamp: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def spot_at(ticker: str, session: date, timestamp: str | None, root: Path = DEFAULT_BAR_ROOT) -> float | None:
    """Close of the last completed bar ending at or before ``timestamp`` (newest stored file for the session).

    No bar ending at or before the instant means no reference price (never the nearest later bar).
    """
    instant = _parse(timestamp) if timestamp else None
    folder = Path(root) / session.isoformat() / ticker.upper()
    if instant is None or not folder.is_dir():
        return None
    files = sorted(folder.glob("*.parquet"), key=lambda f: f.stat().st_mtime)
    if not files:
        return None
    bars = pd.read_parquet(files[-1], columns=["timestamp_utc", "close", "interval_minutes"])
    if bars.empty:
        return None
    ends = pd.to_datetime(bars["timestamp_utc"], utc=True) + pd.to_timedelta(bars["interval_minutes"], unit="m")
    eligible = bars[ends <= pd.Timestamp(instant)]
    if eligible.empty:
        return None
    value = float(eligible.sort_values("timestamp_utc")["close"].iloc[-1])
    return value if value > 0 else None
