"""MarketData transport adapter for completed-session option chains."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import os
from typing import Any, Callable, Mapping, Protocol
from zoneinfo import ZoneInfo

import requests


MARKETDATA_OPTION_CHAIN_COLUMNS = (
    "s,optionSymbol,underlying,expiration,side,strike,firstTraded,dte,updated,"
    "bid,bidSize,mid,ask,askSize,last,openInterest,volume,inTheMoney,"
    "intrinsicValue,extrinsicValue,underlyingPrice,iv,delta,gamma,theta,vega,"
    "contractMultiplier"
)


class HttpResponse(Protocol):
    status_code: int
    ok: bool
    text: str

    def json(self) -> Any: ...


class HttpTransport(Protocol):
    def get(self, url: str, **kwargs: Any) -> HttpResponse: ...


class MarketDataOptionChainError(RuntimeError):
    pass


class MarketDataOptionChainNoData(MarketDataOptionChainError):
    pass


def exchange_today() -> date:
    """Today's date on the exchange (XNYS, America/New_York)."""
    return datetime.now(ZoneInfo("America/New_York")).date()


def _response_error_detail(response: HttpResponse, *, api_token: str) -> str:
    """Return a bounded provider error without echoing headers or credentials."""
    try:
        payload = response.json()
    except Exception:
        payload = None
    detail = str(getattr(response, "text", "") or "")
    if isinstance(payload, Mapping):
        for key in ("errmsg", "error", "message", "detail"):
            value = payload.get(key)
            if value:
                detail = str(value)
                break
    if api_token:
        detail = detail.replace(api_token, "[REDACTED]")
    return " ".join(detail.split())[:300]


class MarketDataOptionChainAdapter:
    """Retrieve a completed-session chain without inventing time.

    P0-4 (ACK 18 Sep 2026, GEX-D9): the provider accepts ``date`` only for historical sessions, so it is sent only
    when the requested session is before today's exchange date. For today's session (after the close) the plain
    request returns today's chain; the store validates that every chain belongs to the requested session.
    """

    def __init__(
        self,
        *,
        api_token: str | None = None,
        transport: HttpTransport | None = None,
        timeout_seconds: int = 45,
        today: Callable[[], date] | None = None,
    ) -> None:
        self.api_token = str(api_token or os.environ.get("MARKETDATA_API_KEY") or "").strip()
        if not self.api_token:
            raise MarketDataOptionChainError("MARKETDATA_API_KEY is not configured")
        self.transport = transport or requests.Session()
        self.timeout_seconds = int(timeout_seconds)
        self.today = today or exchange_today

    def fetch(
        self,
        ticker: str,
        *,
        session_date: date,
        dte_max: int,
        min_open_interest: int = 0,
    ) -> Mapping[str, Any]:
        ticker_up = str(ticker).strip().upper()
        if not ticker_up:
            raise ValueError("ticker is required")
        if dte_max < 1:
            raise ValueError("dte_max must be positive")
        today = self.today()
        if session_date > today:
            raise ValueError(f"cannot request a future session ({session_date} > {today})")
        url = f"https://api.marketdata.app/v1/options/chain/{ticker_up}/"
        params = {
            "from": (session_date + timedelta(days=1)).isoformat(),
            "to": (session_date + timedelta(days=int(dte_max))).isoformat(),
            "minOpenInterest": int(min_open_interest),
            "columns": MARKETDATA_OPTION_CHAIN_COLUMNS,
        }
        if session_date < today:
            params = {"date": session_date.isoformat(), **params}
        response = self.transport.get(
            url,
            headers={"Authorization": f"Token {self.api_token}"},
            params=params,
            timeout=self.timeout_seconds,
        )
        if response.status_code == 404:
            raise MarketDataOptionChainNoData(
                f"MarketData has no {ticker_up} option chain for {session_date}"
            )
        if not response.ok:
            detail = _response_error_detail(response, api_token=self.api_token)
            raise MarketDataOptionChainError(
                f"MarketData option chain failed for {ticker_up}: HTTP {response.status_code}"
                + (f" ({detail})" if detail else "")
            )
        try:
            payload = response.json()
        except Exception as error:
            raise MarketDataOptionChainError(
                f"MarketData returned invalid JSON for {ticker_up}"
            ) from error
        if not isinstance(payload, Mapping):
            raise MarketDataOptionChainError("MarketData option-chain payload is not an object")
        status = str(payload.get("s") or "").strip().lower()
        if status in {"no_data", "nodata"}:
            raise MarketDataOptionChainNoData(
                f"MarketData has no {ticker_up} option chain for {session_date}"
            )
        if status != "ok":
            raise MarketDataOptionChainError(
                f"MarketData option-chain status for {ticker_up} is {status or 'missing'}"
            )
        return payload


__all__ = [
    "exchange_today",
    "MARKETDATA_OPTION_CHAIN_COLUMNS",
    "MarketDataOptionChainAdapter",
    "MarketDataOptionChainError",
    "MarketDataOptionChainNoData",
]
