"""
Alternative Contract Selector — AVSHUNTER Pipeline Interpreter
When the conflict resolver detects misdiagnosis, selects an alternative
contract in the dominant direction and fetches its live Greeks.
"""

from __future__ import annotations
import math
import sys
import os
from datetime import date, timedelta
from typing import Any

# morning_gate lives one directory up
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from morning_gate import _fetch_live_contract


# ---------------------------------------------------------------------------
# OCC symbol helpers
# ---------------------------------------------------------------------------

def _build_occ_symbol(
    ticker: str,
    expiry_date: str,   # YYYYMMDD
    direction: str,     # CALL or PUT
    strike: float,
) -> str:
    """
    OCC format: TICKER + YYMMDD + C/P + 8-digit strike (price * 1000).
    Example: FIVN260618C00023000
    """
    yy = expiry_date[2:4]
    mm = expiry_date[4:6]
    dd = expiry_date[6:8]
    cp = "C" if direction.upper() == "CALL" else "P"
    strike_int = int(round(strike * 1000))
    return f"{ticker.upper()}{yy}{mm}{dd}{cp}{strike_int:08d}"


def _select_strike(live_price: float, direction: str) -> float:
    """
    Select nearest round strike to live_price.
    CALL: round up; PUT: round down.
    """
    if live_price < 10:
        increment = 0.50
    elif live_price < 50:
        increment = 1.00
    elif live_price < 100:
        increment = 2.50
    else:
        increment = 5.00

    if direction.upper() == "CALL":
        return math.ceil(live_price / increment) * increment
    else:
        return math.floor(live_price / increment) * increment


def _next_monthly_expiry() -> str:
    """Return YYYYMMDD of the third Friday of the next calendar month."""
    today = date.today()
    # First day of next month
    if today.month == 12:
        first = date(today.year + 1, 1, 1)
    else:
        first = date(today.year, today.month + 1, 1)

    # Find third Friday
    fridays = 0
    d = first
    while True:
        if d.weekday() == 4:  # Friday
            fridays += 1
            if fridays == 3:
                return d.strftime("%Y%m%d")
        d += timedelta(days=1)


def _parse_expiry_from_occ(occ_symbol: str) -> str | None:
    """
    Extract YYYYMMDD from OCC symbol characters 6:12 (YYMMDD).
    Returns None if unparseable.
    """
    try:
        stripped = occ_symbol.strip()
        # OCC: root (up to 6 chars) + YYMMDD + C/P + strike (8 digits)
        # Find the C/P character after the date portion
        # Try positions 6..12 for a 6-digit date
        for start in range(min(len(stripped) - 15, 10), -1, -1):
            candidate = stripped[start:start + 6]
            if candidate.isdigit():
                yy = int(candidate[:2])
                mm = int(candidate[2:4])
                dd = int(candidate[4:6])
                if 1 <= mm <= 12 and 1 <= dd <= 31:
                    year = 2000 + yy
                    return f"{year:04d}{mm:02d}{dd:02d}"
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def select_alternative_contract(
    row: dict,
    dominant_direction: str,
    live_price: float,
) -> dict[str, Any]:
    """
    Build and fetch an alternative contract in dominant_direction.
    Returns alternative trade package or error dict.
    """
    ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
    if not ticker:
        return {
            "alt_direction":        dominant_direction,
            "alt_contract_symbol":  "",
            "alt_strike":           None,
            "alt_expiry":           "",
            "alt_bid":              None,
            "alt_ask":              None,
            "alt_mid":              None,
            "alt_spread_pct":       None,
            "alt_iv":               None,
            "alt_delta":            None,
            "alt_contract_status":  "FETCH_FAILED",
            "alt_selection_reason": "ticker field missing from row",
        }

    # Resolve expiry from original contract symbol
    original_occ = str(
        row.get("evening_contract_symbol")
        or row.get("contract_symbol")
        or row.get("recommended_contract")
        or ""
    ).strip()
    expiry_date = _parse_expiry_from_occ(original_occ) if original_occ else None

    expiry_source = "original_contract"
    if expiry_date is None:
        expiry_date = _next_monthly_expiry()
        expiry_source = "next_monthly_default"

    # Strike selection
    strike = _select_strike(live_price, dominant_direction)

    # Build OCC symbol
    occ_symbol = _build_occ_symbol(ticker, expiry_date, dominant_direction, strike)

    selection_reason = (
        f"Pipeline misdiagnosis detected — switching from "
        f"{row.get('direction','?')} to {dominant_direction}. "
        f"Strike {strike:.2f} selected from live_price={live_price:.2f}. "
        f"Expiry {expiry_date} via {expiry_source}."
    )

    # Fetch live Greeks
    try:
        live_data = _fetch_live_contract(ticker, occ_symbol)
    except Exception as exc:
        return {
            "alt_direction":        dominant_direction,
            "alt_contract_symbol":  occ_symbol,
            "alt_strike":           strike,
            "alt_expiry":           expiry_date,
            "alt_bid":              None,
            "alt_ask":              None,
            "alt_mid":              None,
            "alt_spread_pct":       None,
            "alt_iv":               None,
            "alt_delta":            None,
            "alt_contract_status":  "FETCH_FAILED",
            "alt_selection_reason": f"{selection_reason} Fetch error: {exc}",
        }

    bid        = live_data.get("live_contract_bid")
    ask        = live_data.get("live_contract_ask")
    spread_pct = live_data.get("live_contract_spread_pct")
    iv         = live_data.get("live_contract_iv")
    delta      = live_data.get("live_contract_delta")

    mid = None
    if bid is not None and ask is not None:
        try:
            mid = round((float(bid) + float(ask)) / 2, 4)
        except (ValueError, TypeError):
            pass

    status = "LIVE_QUOTE" if bid is not None else "NO_QUOTE"

    return {
        "alt_direction":        dominant_direction,
        "alt_contract_symbol":  occ_symbol,
        "alt_strike":           strike,
        "alt_expiry":           expiry_date,
        "alt_bid":              bid,
        "alt_ask":              ask,
        "alt_mid":              mid,
        "alt_spread_pct":       spread_pct,
        "alt_iv":               iv,
        "alt_delta":            delta,
        "alt_contract_status":  status,
        "alt_selection_reason": selection_reason,
    }
