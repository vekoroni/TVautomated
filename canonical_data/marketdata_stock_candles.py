"""Frame-preserving MarketData stock-candle adapter.

The legacy latest-price bridge intentionally synthesises one partial-session
bar.  This adapter owns the separate canonical intraday contract: every
provider candle remains a distinct observation and provider time, observation
time, and acquisition time are never conflated.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from typing import Any, Callable, Mapping
import urllib.parse
import urllib.request

import pandas as pd


MARKETDATA_PROVIDER = "MARKETDATA"


def _timestamp_series(values: list[Any]) -> pd.Series:
    numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    if numeric.notna().all():
        magnitude = float(numeric.abs().max()) if len(numeric) else 0.0
        unit = "ms" if magnitude >= 10**11 else "s"
        return pd.to_datetime(numeric, unit=unit, errors="raise", utc=True)
    return pd.to_datetime(pd.Series(values), errors="raise", utc=True)


def parse_marketdata_stock_candles(
    payload: Mapping[str, Any],
    *,
    ticker: str,
    session_date: date,
    interval_minutes: int,
    session_segment: str = "REGULAR",
    adjustment_convention: str = "SPLIT_ADJUSTED",
    acquired_at_utc: datetime | None = None,
) -> pd.DataFrame:
    """Parse parallel MarketData arrays without aggregating or dropping rows."""
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    status = str(payload.get("s", "")).strip().lower()
    if status not in {"ok", "success"}:
        if status in {"no_data", "no data", "nodata"}:
            return pd.DataFrame()
        raise ValueError(f"MarketData candle response is not successful: {status or 'MISSING_STATUS'}")

    names = {"t": "timestamp_utc", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    arrays = {short: list(payload.get(short) or []) for short in names}
    lengths = {short: len(values) for short, values in arrays.items()}
    if not lengths["t"] and all(length == 0 for length in lengths.values()):
        return pd.DataFrame()
    if len(set(lengths.values())) != 1:
        raise ValueError(f"MarketData candle parallel-array length mismatch: {lengths}")
    if not lengths["t"]:
        raise ValueError("MarketData candle response has values but no timestamps")

    frame = pd.DataFrame({names[key]: values for key, values in arrays.items()})
    frame["timestamp_utc"] = _timestamp_series(arrays["t"])
    acquired = acquired_at_utc or datetime.now(timezone.utc)
    if acquired.tzinfo is None:
        raise ValueError("acquired_at_utc must be timezone-aware")
    observed_raw = payload.get("updated") or payload.get("observed_at")
    if isinstance(observed_raw, list):
        if len(observed_raw) not in {0, len(frame)}:
            raise ValueError("MarketData observed_at parallel-array length mismatch")
        observed = _timestamp_series(observed_raw) if observed_raw else frame["timestamp_utc"]
    elif observed_raw is None:
        observed = frame["timestamp_utc"]
    else:
        observed = pd.Series([pd.to_datetime(observed_raw, unit="s" if isinstance(observed_raw, (int, float)) else None, utc=True)] * len(frame))

    frame["ticker"] = ticker.strip().upper()
    frame["session_date"] = session_date.isoformat()
    frame["interval_minutes"] = int(interval_minutes)
    frame["session_segment"] = session_segment.strip().upper()
    frame["adjustment_convention"] = adjustment_convention.strip().upper()
    frame["provider"] = MARKETDATA_PROVIDER
    frame["provider_observed_at_utc"] = pd.to_datetime(observed, utc=True)
    frame["observed_at"] = frame["provider_observed_at_utc"]
    frame["acquired_at_utc"] = acquired.astimezone(timezone.utc)
    return frame


class MarketDataStockCandleAdapter:
    """Callable provider adapter for ``CanonicalMinuteBarResolver``.

    ``request_json`` is injectable so URL construction and parsing can be
    tested without network access.  The default transport uses the same token
    authentication convention as the existing AVSHUNTER MarketData clients.
    """

    def __init__(
        self,
        api_token: str,
        *,
        timeout_seconds: int = 20,
        request_json: Callable[[str, Mapping[str, str], Mapping[str, str], int], Mapping[str, Any]] | None = None,
    ) -> None:
        self.api_token = str(api_token).strip()
        self.timeout_seconds = int(timeout_seconds)
        self.request_json = request_json or self._request_json

    @staticmethod
    def _request_json(
        url: str,
        params: Mapping[str, str],
        headers: Mapping[str, str],
        timeout_seconds: int,
    ) -> Mapping[str, Any]:
        request_url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(request_url, headers=dict(headers), method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_range(
        self,
        ticker: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        session_date: date,
        interval_minutes: int = 5,
        session_segment: str = "REGULAR",
    ) -> pd.DataFrame:
        if not self.api_token:
            raise ValueError("MarketData API token is required")
        if start_utc.tzinfo is None or end_utc.tzinfo is None:
            raise ValueError("MarketData candle range must be timezone-aware")
        acquired = datetime.now(timezone.utc)
        url = f"https://api.marketdata.app/v1/stocks/candles/{int(interval_minutes)}/{ticker.strip().upper()}/"
        params = {
            "from": start_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "to": end_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "extended": "false" if session_segment.strip().upper() == "REGULAR" else "true",
            "adjustsplits": "true",
        }
        payload = self.request_json(
            url,
            params,
            {"Authorization": f"Token {self.api_token}"},
            self.timeout_seconds,
        )
        return parse_marketdata_stock_candles(
            payload,
            ticker=ticker,
            session_date=session_date,
            interval_minutes=interval_minutes,
            session_segment=session_segment,
            adjustment_convention="SPLIT_ADJUSTED",
            acquired_at_utc=acquired,
        )
