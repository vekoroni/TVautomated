
# ORCHESTRATOR ADAPTER (FIXED VERSION)

import pandas as pd
from datetime import datetime


def validate_ohlcv(df):
    required_cols = {"open", "high", "low", "close", "volume"}

    if not isinstance(df, pd.DataFrame):
        return False, "BAD_TYPE"

    if df.empty:
        return False, "EMPTY"

    if not required_cols.issubset(set(df.columns)):
        return False, "MISSING_COLUMNS"

    if len(df) < 200:
        return False, "INSUFFICIENT_HISTORY"

    last_date = pd.to_datetime(df.index[-1])
    now = pd.Timestamp.utcnow()

    if (now - last_date).days > 5:
        return False, "STALE_DATA"

    return True, "OK"


def adapt(orchestrator_output):
    ticker = orchestrator_output.get("ticker", "")
    df = orchestrator_output.get("ohlcv")

    valid, reason = validate_ohlcv(df)

    if not valid:
        return {
            "ok": False,
            "ticker": ticker,
            "reason": reason
        }

    return {
        "ok": True,
        "ticker": ticker,
        "rows": len(df)
    }
