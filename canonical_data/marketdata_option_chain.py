"""MarketData transport adapter for completed-session option chains."""

from __future__ import annotations

from datetime import date, timedelta
import os
from typing import Any, Mapping, Protocol

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
    """Retrieve a historical completed-session chain without inventing time."""

    def __init__(
        self,
        *,
        api_token: str | None = None,
        transport: HttpTransport | None = None,
        timeout_seconds: int = 45,
    ) -> None:
        self.api_token = str(api_token or os.environ.get("MARKETDATA_API_KEY") or "").strip()
        if not self.api_token:
            raise MarketDataOptionChainError("MARKETDATA_API_KEY is not configured")
        self.transport = transport or requests.Session()
        self.timeout_seconds = int(timeout_seconds)

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
        url = f"https://api.marketdata.app/v1/options/chain/{ticker_up}/"
        params = {
            "date": session_date.isoformat(),
            "from": (session_date + timedelta(days=1)).isoformat(),
            "to": (session_date + timedelta(days=int(dte_max))).isoformat(),
            "minOpenInterest": int(min_open_interest),
            "columns": MARKETDATA_OPTION_CHAIN_COLUMNS,
        }
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
    "MARKETDATA_OPTION_CHAIN_COLUMNS",
    "MarketDataOptionChainAdapter",
    "MarketDataOptionChainError",
    "MarketDataOptionChainNoData",
]
