"""Far out-of-the-money, longer-dated "lottery ticket" study (read-only; ACK 17 Sep 2026).

Question: the recorded books only ever bought near-the-money contracts, so the backtest could not judge whether
buying cheap, far out-of-the-money, longer-dated contracts on the same theses would have produced the large
multiples. This builds those contracts from the stored chain and scores them the same way.

For every recorded thesis (direction, spot, stop, target, hold, forecast) it picks, from that session's stored
chain, the contract nearest each target moneyness band with days to expiry inside the band, then values it with the
shipped model and scores it with the shipped exit rules (stop, target, hold, last usable session; exit at the
stored chain bid).

Usage: python Enhancements/backtest/otm_tail_study.py
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from avshunter.c12_outcome.adapters import prices  # noqa: E402
from avshunter.shared.xnys_calendar import is_xnys_session, previous_xnys_session  # noqa: E402
import empirical_option_ev as ev  # noqa: E402

HERE = Path(__file__).resolve().parent
PRICE_DB = REPO / "data" / "canonical" / "historical_prices.sqlite"
CHAIN_DB = REPO / "data" / "phantom" / "phantom_history.db"
CALIBRATION = json.loads((REPO / "config" / "calibration" / "volatility_range_calibration_v1.json")
                         .read_text(encoding="utf-8"))
BANDS = {"near_atm": 0.0, "otm_10": 0.10, "otm_20": 0.20, "otm_30": 0.30}
# The stored chains only ever captured roughly 8-45 days to expiry, so genuinely long-dated contracts
# (3-12 months) cannot be tested from this data at all.
DTE_MIN, DTE_MAX = 25, 60
EXIT_BUFFER_SESSIONS = 2


def pick_contract(connection, ticker: str, session: date, side: str, spot: float, otm: float):
    """Cheapest-nearest contract to the target strike inside the day-to-expiry band, from the stored chain."""
    target_strike = spot * (1 + otm) if side == "call" else spot * (1 - otm)
    row = connection.execute(
        """
        SELECT option_symbol, strike, bid, ask, dte, expiration_ts
        FROM chain_snapshots
        WHERE ticker = ? AND quote_date = ? AND side = ? AND dte BETWEEN ? AND ?
          AND bid > 0 AND ask > 0 AND ask >= bid
        ORDER BY ABS(strike - ?) LIMIT 1
        """,
        (ticker, session.isoformat(), side, DTE_MIN, DTE_MAX, target_strike)).fetchone()
    return row


def exit_plan(bars, entry: date, sign: float, stop: float, target: float, hold: int, last_usable: date):
    for step, bar in enumerate([b for b in bars if b.session > entry], start=1):
        if sign * ((bar.low if sign > 0 else bar.high) - stop) <= 0:
            return "STOP", bar.session
        if sign * ((bar.high if sign > 0 else bar.low) - target) >= 0:
            return "TARGET", bar.session
        if bar.session >= last_usable:
            return "CONTRACT_LAST_USABLE", bar.session
        if step >= hold:
            return "HOLD_COMPLETE", bar.session
    return None, None


def main() -> int:
    rows = pd.read_csv(HERE / "signal_ticket_backtest_rows.csv").dropna(
        subset=["spot", "stop", "target", "hold", "forecast_vol", "iv"])
    rows = rows.drop_duplicates(["session", "ticker"])
    chain = sqlite3.connect(f"file:{CHAIN_DB.as_posix()}?mode=ro", uri=True)
    bars = prices.load_bars({str(t).upper() for t in rows.ticker}, date.fromisoformat(min(rows.session)),
                            prices.latest_session(PRICE_DB), PRICE_DB)
    out = []
    try:
        for row in rows.itertuples():
            session = date.fromisoformat(row.session)
            side = "call" if row.direction == "CALL" else "put"
            sign = 1.0 if row.direction == "CALL" else -1.0
            history = bars.get(row.ticker, [])
            for band, otm in BANDS.items():
                picked = pick_contract(chain, row.ticker, session, side, row.spot, otm)
                if picked is None:
                    continue
                symbol, strike, bid, ask, dte, expiration = picked
                expiry = (datetime.fromtimestamp(float(expiration), tz=timezone.utc).date()
                          if expiration else None)
                if expiry is None:
                    continue
                usable = expiry if is_xnys_session(expiry) else previous_xnys_session(expiry)
                for _ in range(EXIT_BUFFER_SESSIONS):
                    usable = previous_xnys_session(usable)
                valuation = ev.compute_path_option_ev(
                    side=side, spot=row.spot, strike=float(strike), dte=float(dte),
                    bid=float(bid), ask=float(ask), iv=row.iv, rate=ev.DEFAULT_RISK_FREE_RATE, target=row.target,
                    invalidation=row.stop, hold_sessions=int(row.hold), forecast_vol=row.forecast_vol,
                    calibration=CALIBRATION, paths=ev.PATH_SETTINGS["paths"], seed=ev.PATH_SETTINGS["seed"])
                reason, exit_session = exit_plan(history, session, sign, row.stop, row.target, int(row.hold), usable)
                mark = None
                if exit_session is not None:
                    got = chain.execute(
                        "SELECT bid FROM chain_snapshots WHERE ticker = ? AND quote_date = ? AND option_symbol = ?",
                        (row.ticker, exit_session.isoformat(), symbol)).fetchone()
                    mark = None if got is None else got[0]
                out.append({
                    "band": band, "session": row.session, "ticker": row.ticker, "direction": row.direction,
                    "contract": symbol, "strike": float(strike), "spot": row.spot, "dte": float(dte),
                    "entry_ask": float(ask), "spread_fraction": (ask - bid) / ((ask + bid) / 2),
                    "moneyness": sign * (row.spot - float(strike)) / row.spot,
                    "cautious": valuation.get("emp_path_r_cautious"), "upside": valuation.get("emp_path_r_upside"),
                    "valuation_flag": valuation.get("emp_path_quality_flag"),
                    "exit_reason": reason, "exit_session": exit_session.isoformat() if exit_session else None,
                    "exit_bid": mark,
                    "option_return": None if mark is None else mark / float(ask) - 1.0,
                    "state": "CLOSED" if mark is not None else ("OPEN" if reason is None else "EXIT_MARK_UNAVAILABLE"),
                })
    finally:
        chain.close()
    frame = pd.DataFrame(out)
    frame.to_csv(HERE / "otm_tail_study_rows.csv", index=False)
    closed = frame[frame.state == "CLOSED"].dropna(subset=["option_return"])
    summary = {"theses": int(len(rows)), "contracts_built": len(frame), "closed": len(closed), "bands": {}}
    for band in BANDS:
        g = closed[closed.band == band]
        summary["bands"][band] = {
            "closed": len(g),
            "median_moneyness": round(float(g.moneyness.median()), 3) if len(g) else None,
            "median_dte": round(float(g.dte.median()), 1) if len(g) else None,
            "median_entry": round(float(g.entry_ask.median()), 2) if len(g) else None,
            "median_spread": round(float(g.spread_fraction.median()), 3) if len(g) else None,
            "mean_return": round(float(g.option_return.mean()), 4) if len(g) else None,
            "median_return": round(float(g.option_return.median()), 4) if len(g) else None,
            "hit_rate": round(float((g.option_return > 0).mean()), 3) if len(g) else None,
            "share_ge_100pct": round(float((g.option_return >= 1).mean()), 4) if len(g) else None,
            "share_ge_400pct": round(float((g.option_return >= 4).mean()), 4) if len(g) else None,
            "max_return": round(float(g.option_return.max()), 2) if len(g) else None,
            "total_return_equal_weight": round(float(g.option_return.mean()), 4) if len(g) else None,
        }
    (HERE / "otm_tail_study_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
