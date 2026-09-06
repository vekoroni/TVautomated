"""Frame-preserving MarketData stock-candle adapter.

The legacy latest-price bridge intentionally synthesises one partial-session
bar.  This adapter owns the separate canonical intraday contract: every
provider candle remains a distinct observation and provider time, observation
time, and acquisition time are never conflated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import pandas as pd

from .session_clock import session_bounds


MARKETDATA_PROVIDER = "MARKETDATA"
NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True)
class MarketDataCandleResponse:
    """Transport envelope retained alongside the provider JSON payload."""

    payload: Mapping[str, Any]
    http_status: int
    headers: Mapping[str, str]
    acquired_at_utc: datetime
    rate_limit_limit: str | None = None
    rate_limit_remaining: str | None = None
    rate_limit_reset: str | None = None
    rate_limit_consumed: str | None = None
    provider_status: str = ""

    def __post_init__(self) -> None:
        if self.acquired_at_utc.tzinfo is None:
            raise ValueError("MarketData response acquisition time must be timezone-aware")
        object.__setattr__(
            self,
            "rate_limit_limit",
            self.rate_limit_limit or _header_value(self.headers, "x-api-ratelimit-limit", "ratelimit-limit") or None,
        )
        object.__setattr__(
            self,
            "rate_limit_remaining",
            self.rate_limit_remaining or _header_value(self.headers, "x-api-ratelimit-remaining", "ratelimit-remaining") or None,
        )
        object.__setattr__(
            self,
            "rate_limit_reset",
            self.rate_limit_reset or _header_value(self.headers, "x-api-ratelimit-reset", "ratelimit-reset") or None,
        )
        object.__setattr__(
            self,
            "rate_limit_consumed",
            self.rate_limit_consumed or _header_value(self.headers, "x-api-ratelimit-consumed", "ratelimit-consumed") or None,
        )
        object.__setattr__(
            self,
            "provider_status",
            self.provider_status or str(self.payload.get("s", "")).strip().lower(),
        )


class MarketDataCandleNoData(RuntimeError):
    """A valid provider response that contains no candles for the request."""

    reason_code = "PROVIDER_NO_DATA"

    def __init__(self, message: str, *, response: MarketDataCandleResponse) -> None:
        super().__init__(message)
        self.response = response


class MarketDataCandleTransportError(RuntimeError):
    """An HTTP or provider-status failure, distinct from a no-data result."""

    reason_code = "PROVIDER_TRANSPORT_ERROR"

    def __init__(self, message: str, *, response: MarketDataCandleResponse) -> None:
        super().__init__(message)
        self.response = response


def _header_value(headers: Mapping[str, str], *names: str) -> str:
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return ""


def _segment_for_timestamp(timestamp: pd.Timestamp, *, open_utc: datetime, close_utc: datetime) -> str:
    observed = timestamp.to_pydatetime()
    if observed < open_utc:
        return "PREMARKET"
    if observed >= close_utc:
        return "AFTER_HOURS"
    return "REGULAR"


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
    provider_http_status: int = 200,
    provider_headers: Mapping[str, str] | None = None,
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
    regular_open_utc, regular_close_utc = session_bounds(session_date)
    frame["session_segment"] = frame["timestamp_utc"].map(
        lambda value: _segment_for_timestamp(
            pd.Timestamp(value), open_utc=regular_open_utc, close_utc=regular_close_utc
        )
    )
    frame["adjustment_convention"] = adjustment_convention.strip().upper()
    frame["provider"] = MARKETDATA_PROVIDER
    frame["provider_observed_at_utc"] = pd.to_datetime(observed, utc=True)
    frame["observed_at"] = frame["provider_observed_at_utc"]
    frame["acquired_at_utc"] = acquired.astimezone(timezone.utc)
    headers = provider_headers or {}
    frame["provider_http_status"] = int(provider_http_status)
    frame["provider_rate_limit_remaining"] = _header_value(
        headers, "x-api-ratelimit-remaining", "ratelimit-remaining"
    )
    frame["provider_rate_limit_limit"] = _header_value(
        headers, "x-api-ratelimit-limit", "ratelimit-limit"
    )
    frame["provider_rate_limit_reset"] = _header_value(
        headers, "x-api-ratelimit-reset", "ratelimit-reset"
    )
    frame["provider_rate_limit_consumed"] = _header_value(
        headers, "x-api-ratelimit-consumed", "ratelimit-consumed"
    )
    frame.attrs.update({
        "provider_http_status": int(provider_http_status),
        "provider_headers": dict(headers),
        "provider_status": status,
    })
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
        request_json: Callable[
            [str, Mapping[str, str], Mapping[str, str], int],
            Mapping[str, Any] | MarketDataCandleResponse,
        ] | None = None,
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
    ) -> MarketDataCandleResponse:
        request_url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(request_url, headers=dict(headers), method="GET")
        acquired = datetime.now(timezone.utc)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw_headers = {str(key): str(value) for key, value in response.headers.items()}
                return MarketDataCandleResponse(
                    payload=json.loads(response.read().decode("utf-8")),
                    http_status=int(response.status),
                    headers=raw_headers,
                    acquired_at_utc=acquired,
                )
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"s": "error", "errmsg": raw[:500]}
            return MarketDataCandleResponse(
                payload=payload,
                http_status=int(error.code),
                headers={str(key): str(value) for key, value in error.headers.items()},
                acquired_at_utc=acquired,
            )
        except urllib.error.URLError as error:
            return MarketDataCandleResponse(
                payload={"s": "error", "errmsg": str(error.reason)},
                http_status=0,
                headers={},
                acquired_at_utc=acquired,
            )

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
        url = f"https://api.marketdata.app/v1/stocks/candles/{int(interval_minutes)}/{ticker.strip().upper()}/"
        # MarketData interprets naked candle-window timestamps as exchange
        # wall-clock time.  Sending UTC Z values silently truncates the
        # completed session by the UTC/ET offset.
        # The canonical resolver's range contract is inclusive of both bar
        # opens. MarketData's ``to`` boundary is exclusive, so advance it by
        # one interval here at the provider anti-corruption boundary. Keeping
        # this conversion in the adapter prevents every domain caller from
        # needing to understand provider-specific timestamp semantics.
        provider_end_utc = end_utc + timedelta(minutes=int(interval_minutes))
        params = {
            "from": start_utc.astimezone(NEW_YORK).replace(tzinfo=None).isoformat(timespec="seconds"),
            "to": provider_end_utc.astimezone(NEW_YORK).replace(tzinfo=None).isoformat(timespec="seconds"),
            "extended": "false" if session_segment.strip().upper() == "REGULAR" else "true",
            "adjustsplits": "true",
        }
        raw_response = self.request_json(
            url,
            params,
            {"Authorization": f"Token {self.api_token}"},
            self.timeout_seconds,
        )
        if isinstance(raw_response, MarketDataCandleResponse):
            response = raw_response
        else:
            response = MarketDataCandleResponse(
                payload=raw_response,
                http_status=200,
                headers={},
                acquired_at_utc=datetime.now(timezone.utc),
            )
        payload = response.payload
        provider_status = str(payload.get("s", "")).strip().lower()
        if provider_status in {"no_data", "no data", "nodata"}:
            raise MarketDataCandleNoData(
                f"MarketData returned no_data for {ticker.strip().upper()} {session_date}",
                response=response,
            )
        if response.http_status >= 400 or provider_status not in {"ok", "success"}:
            reason = payload.get("errmsg") or payload.get("error") or provider_status or "MISSING_STATUS"
            raise MarketDataCandleTransportError(
                f"MarketData candle request failed HTTP {response.http_status}: {reason}",
                response=response,
            )
        return parse_marketdata_stock_candles(
            payload,
            ticker=ticker,
            session_date=session_date,
            interval_minutes=interval_minutes,
            session_segment=session_segment,
            adjustment_convention="SPLIT_ADJUSTED",
            acquired_at_utc=response.acquired_at_utc,
            provider_http_status=response.http_status,
            provider_headers=response.headers,
        )
