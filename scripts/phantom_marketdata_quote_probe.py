"""Probe MarketData option quote endpoint for vendor Greeks.

Use this after the chain endpoint shows Greek keys with null values. This probes
the single-contract endpoint documented for current and historical option quotes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from typing import Any, Dict, Optional

import requests


QUOTE_COLUMNS = (
    "optionSymbol,bid,bidSize,mid,ask,askSize,last,openInterest,volume,"
    "underlyingPrice,inTheMoney,intrinsicValue,extrinsicValue,updated,"
    "iv,delta,gamma,theta,vega"
)


def api_token() -> str:
    return (
        os.environ.get("MARKETDATA_API_KEY")
        or os.environ.get("MARKETDATA_TOKEN")
        or os.environ.get("MD_API_KEY")
        or ""
    ).strip()


def first(payload: Dict[str, Any], key: str) -> Any:
    value = payload.get(key)
    if isinstance(value, list) and value:
        return value[0]
    return value


def present(value: Any) -> bool:
    if value is None or value == "":
        return False
    try:
        out = float(value)
        return not (math.isnan(out) or math.isinf(out))
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe MarketData option quote endpoint for Greeks.")
    parser.add_argument("--option-symbol", required=True)
    parser.add_argument("--date", default="", help="Historical quote date, YYYY-MM-DD.")
    parser.add_argument("--no-force-columns", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    token = api_token()
    if not token:
        print(json.dumps({"status": "error", "error": "MARKETDATA_API_KEY is not set"}, indent=2))
        return 2

    params: Dict[str, Any] = {}
    if args.date:
        params["date"] = args.date
    if not args.no_force_columns:
        params["columns"] = QUOTE_COLUMNS

    symbol = args.option_symbol.strip().upper()
    url = f"https://api.marketdata.app/v1/options/quotes/{symbol}/"
    response = requests.get(
        url,
        headers={"Authorization": f"Token {token}"},
        params=params,
        timeout=args.timeout,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {"s": "error", "errmsg": response.text[:500]}

    api_status = str(payload.get("s") or "").lower()
    row_count = len(payload.get("optionSymbol", [])) if isinstance(payload.get("optionSymbol"), list) else 0
    greek_fields = ["iv", "delta", "gamma", "theta", "vega"]
    out = {
        "option_symbol": symbol,
        "url": url,
        "params": params,
        "http_status": response.status_code,
        "api_status": api_status,
        "response_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "row_count": row_count,
        "field_presence": {field: present(first(payload, field)) for field in greek_fields},
        "sample": {
            key: first(payload, key)
            for key in [
                "optionSymbol", "bid", "ask", "mid", "last", "openInterest", "volume",
                "underlyingPrice", "updated", "iv", "delta", "gamma", "theta", "vega",
            ]
            if key in payload
        },
    }
    if api_status not in {"ok", ""}:
        out["error"] = payload.get("errmsg", "")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if response.ok and api_status == "ok" and all(out["field_presence"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
