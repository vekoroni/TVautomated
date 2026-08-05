"""Probe MarketData option-chain response shape for PHANTOM Greek extraction.

This intentionally prints only field-level diagnostics, not the API token.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict

import requests


DEFAULT_COLUMNS = (
    "optionSymbol,underlying,expiration,side,strike,firstTraded,dte,updated,"
    "bid,bidSize,mid,ask,askSize,last,openInterest,volume,inTheMoney,"
    "intrinsicValue,extrinsicValue,underlyingPrice,iv,delta,gamma,theta,vega"
)


def api_token() -> str:
    return (
        os.environ.get("MARKETDATA_API_KEY")
        or os.environ.get("MARKETDATA_TOKEN")
        or os.environ.get("MD_API_KEY")
        or ""
    ).strip()


def is_present(value: Any) -> bool:
    if value is None or value == "":
        return False
    try:
        float(value)
        return True
    except Exception:
        return False


def field_count(payload: Dict[str, Any], key: str) -> int:
    values = payload.get(key)
    if not isinstance(values, list):
        return 0
    return sum(1 for value in values if is_present(value))


def sample_row(payload: Dict[str, Any]) -> Dict[str, Any]:
    symbols = payload.get("optionSymbol") if isinstance(payload.get("optionSymbol"), list) else []
    if not symbols:
        return {}
    out: Dict[str, Any] = {}
    for key in [
        "optionSymbol", "expiration", "side", "strike", "dte", "bid", "ask", "mid",
        "openInterest", "volume", "underlyingPrice", "iv", "delta", "gamma", "theta", "vega",
    ]:
        values = payload.get(key)
        if isinstance(values, list) and values:
            out[key] = values[0]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe MarketData option chain Greek fields.")
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--date", default="", help="Historical quote date, YYYY-MM-DD.")
    parser.add_argument("--expiration", required=True, help="Expiration date, YYYY-MM-DD.")
    parser.add_argument("--side", choices=["call", "put"], default="call")
    parser.add_argument("--min-open-interest", type=int, default=1)
    parser.add_argument("--strike-limit", type=int, default=40)
    parser.add_argument("--no-force-columns", action="store_true", help="Do not send explicit Greek column request.")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    token = api_token()
    if not token:
        print(json.dumps({"status": "error", "error": "MARKETDATA_API_KEY is not set"}, indent=2))
        return 2

    params: Dict[str, Any] = {
        "expiration": args.expiration,
        "side": args.side,
        "range": "all",
        "minOpenInterest": int(args.min_open_interest),
    }
    if args.date:
        params["date"] = args.date
    if args.strike_limit > 0:
        params["strikeLimit"] = int(args.strike_limit)
    if not args.no_force_columns:
        params["columns"] = DEFAULT_COLUMNS

    url = f"https://api.marketdata.app/v1/options/chain/{args.ticker.upper()}/"
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

    row_count = len(payload.get("optionSymbol", [])) if isinstance(payload.get("optionSymbol"), list) else 0
    api_status = str(payload.get("s") or ("ok" if row_count else "")).lower()
    out = {
        "ticker": args.ticker.upper(),
        "url": url,
        "params": params,
        "http_status": response.status_code,
        "api_status": api_status,
        "response_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "row_count": row_count,
        "field_counts": {
            key: field_count(payload, key)
            for key in ["iv", "delta", "gamma", "theta", "vega"]
        },
        "sample_row": sample_row(payload),
    }
    if api_status not in {"ok", ""}:
        out["error"] = payload.get("errmsg", "")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if response.ok and row_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
