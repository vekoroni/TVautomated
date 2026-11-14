"""Exact-contract presentation from saved fields and the local XNYS calendar; no live clock or quotes."""
from datetime import date, timedelta
import math
import re


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
        return v if math.isfinite(v) and v >= 0 else None
    except (ValueError, TypeError):
        return None


def _date(value):
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def saved_contract_details(fields):
    symbol = str(fields.get("contract_symbol") or "").strip()
    match = re.fullmatch(r"(.+?)(\d{6})([CP])(\d{8})", symbol)
    issues = []
    strike = None
    side = None
    symbol_expiry = None
    if match:
        try:
            symbol_expiry = date(2000+int(match[2][:2]), int(match[2][2:4]), int(match[2][4:6]))
            strike = int(match[4])/1000
            side = "Call" if match[3] == "C" else "Put"
        except ValueError:
            issues.append("INVALID_OCC_EXPIRY")
    elif symbol:
        issues.append("OCC_SYMBOL_NOT_PARSEABLE")
    expiry = _date(fields.get("expiry"))
    if expiry is not None and symbol_expiry is not None and expiry != symbol_expiry:
        issues.append("SAVED_EXPIRY_CONFLICTS_WITH_OCC")
    source_strike = _number(fields.get("strike"))
    if source_strike is not None and strike is not None and abs(source_strike-strike)>0.00001:
        issues.append("SAVED_STRIKE_CONFLICTS_WITH_OCC")
    # An expiry decoded from the exact saved OCC is deterministic, not an inferred contract.
    expiry = expiry or symbol_expiry
    calendar_dte = _number(fields.get("dte"))
    trading_dte = _number(fields.get("contract_dte"))
    quote_timestamp = next((fields.get(k) for k in ("selected_quote_timestamp_utc",
                           "quote_provider_timestamp_utc", "anticipated_valued_at_utc")
                            if _date(fields.get(k)) is not None), None)
    quote_date = _date(quote_timestamp)
    reference_date = quote_date
    reference_basis = "Saved quote/valuation date; DTE reference not independently reconciled" if quote_date else None
    if expiry and calendar_dte is not None and calendar_dte.is_integer():
        try:
            implied_reference = expiry-timedelta(days=int(calendar_dte))
        except (OverflowError, ValueError):
            implied_reference = None
        if implied_reference:
            reference_date = implied_reference
            reference_basis = "Derived from saved expiry minus saved calendar DTE"
            if quote_date == implied_reference:
                reference_basis = "Saved quote date; calendar DTE reconciled to saved expiry"
            elif quote_date:
                issues.append("DTE_REFERENCE_DIFFERS_FROM_QUOTE_DATE")
    from domain.trade_timing import sessions_between
    saved_trading_dte = trading_dte
    if expiry and reference_date:
        trading_dte = sessions_between(reference_date, expiry)
        if saved_trading_dte is not None and saved_trading_dte != trading_dte:
            issues.append("SAVED_TRADING_DTE_DIFFERS_FROM_EXACT_XNYS_COUNT")
    return {"contract_symbol": symbol or None, "strike": strike, "call_put": side,
            "expiry": expiry.isoformat() if expiry else None,
            "calendar_dte": calendar_dte, "trading_sessions_remaining": trading_dte,
            "saved_trading_sessions_remaining": saved_trading_dte,
            "saved_reference_date": reference_date.isoformat() if reference_date else None,
            "reference_basis": reference_basis, "saved_quote_timestamp": quote_timestamp,
            "strike_basis": "Decoded from exact saved OCC symbol" if strike is not None else None,
            "trading_sessions_basis": "Exact XNYS sessions after saved reference through expiry" if expiry and reference_date else "UNASSESSED_MISSING_DATES",
            "state": "IDENTITY_CONFLICT" if any("CONFLICTS" in s or "INVALID_OCC" in s for s in issues)
                     else "AVAILABLE" if symbol and strike is not None else "INCOMPLETE",
            "issues": issues, "authority": "DISPLAY_ONLY", "live_countdown": False}
