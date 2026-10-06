"""What the option market charges for a move, from executable chain quotes (MarketData.app
chains stored in the phantom history DB, read-only). No pricing model: the ATM straddle's own
bid/mid/ask is the market's price for movement over its expiry."""

from __future__ import annotations

import math
from pathlib import Path
import sqlite3
from typing import Mapping, Sequence

import pandas as pd


def atm_straddle(chain: pd.DataFrame, target_dte_calendar: int) -> dict | None:
    """ATM straddle on the first expiry whose DTE covers the target (runway: never a shorter
    expiry). ATM = strike nearest the underlying with a two-sided call and put quote."""
    if chain is None or chain.empty:
        return None
    eligible = chain[chain["dte"] >= target_dte_calendar]
    if eligible.empty:
        return None
    dte = float(eligible["dte"].min())
    expiry = eligible[eligible["dte"] == dte]
    spot = float(expiry["underlying_price"].dropna().median())
    quoted = expiry[(expiry["bid"] > 0) & (expiry["ask"] >= expiry["bid"])]
    calls = quoted[quoted["side"] == "call"].set_index("strike")
    puts = quoted[quoted["side"] == "put"].set_index("strike")
    strikes = sorted(set(calls.index) & set(puts.index), key=lambda k: (abs(k - spot), k))
    if not strikes:
        return None
    strike = strikes[0]
    call, put = calls.loc[strike], puts.loc[strike]
    if isinstance(call, pd.DataFrame):
        call = call.iloc[0]
    if isinstance(put, pd.DataFrame):
        put = put.iloc[0]
    mid = float(call["mid"] + put["mid"])
    bid, ask = float(call["bid"] + put["bid"]), float(call["ask"] + put["ask"])
    return {
        "dte": int(dte), "strike": float(strike), "spot": round(spot, 4),
        "straddle_bid": round(bid, 4), "straddle_mid": round(mid, 4), "straddle_ask": round(ask, 4),
        "implied_move_pct": round(mid / spot * 100.0, 4), "implied_move_ask_pct": round(ask / spot * 100.0, 4),
        "spread_pct_of_mid": round((ask - bid) / mid * 100.0, 3) if mid > 0 else None,
    }


def scale_to_sessions(move_pct: float, dte_calendar: int, sessions: int) -> float:
    """Square-root-of-time scaling of an expiry's implied move to a horizon in sessions."""
    expiry_sessions = max(1.0, dte_calendar * 252.0 / 365.0)
    return move_pct * math.sqrt(min(1.0, sessions / expiry_sessions))


def load_implied_moves(db: Path, tickers: Sequence[str], as_of: str, sessions: pd.DatetimeIndex,
                       targets: Mapping[str, int]) -> dict:
    """Per ticker: latest quote date <= as_of and an ATM straddle for each horizon target."""
    if not db.exists():
        return {}
    out = {}
    with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as connection:
        for ticker in tickers:
            quote_date = connection.execute(
                "SELECT MAX(quote_date) FROM chain_snapshots WHERE ticker = ? AND quote_date <= ?", (ticker, as_of)
            ).fetchone()[0]
            if not quote_date:
                continue
            chain = pd.read_sql_query(
                "SELECT side, strike, dte, bid, ask, mid, underlying_price FROM chain_snapshots "
                "WHERE ticker = ? AND quote_date = ?", connection, params=(ticker, quote_date))
            behind = int(((sessions > pd.Timestamp(quote_date)) & (sessions <= pd.Timestamp(as_of))).sum())
            moves = {}
            for horizon, target in targets.items():
                straddle = atm_straddle(chain, int(target))
                if straddle:
                    straddle["implied_move_horizon_pct"] = round(
                        scale_to_sessions(straddle["implied_move_pct"], straddle["dte"], int(horizon)), 4)
                moves[str(horizon)] = straddle
            out[ticker] = {"quote_date": quote_date, "sessions_old": behind, "moves": moves}
    return out
