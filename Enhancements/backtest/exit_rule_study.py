"""Exit-rule study on the backtest harness (read-only; ACK 17 Sep 2026).

The 17 Sep backtest found the binding constraint is the exit, not contract selection: the invalidation level sits
about 0.6 expected moves away, the target about 1.8, and 20 of 21 scored tickets stopped out at a median of two
sessions. This replays the same recorded candidates under four exit rules, changing nothing else:

  baseline   the shipped rule: first of stop touch, target touch, planned hold, last usable session
  wide_stop  the stop moved to 1.5 expected moves over the hold (target, hold and last usable unchanged)
  no_stop    no underlying stop inside the hold: target, hold or last usable only (the premium is the maximum loss)
  revalue    no underlying stop; each session with a stored quote the option is re-valued at that session's ask and
             the position is closed when its cautious return is no longer above zero ("would I still buy it now?")

Inputs are the rows written by ``signal_ticket_backtest.py`` (recorded thesis, quote and point-in-time forecast),
daily bars, and the stored chain. Exits are marked from the chain on the exit session only; no substitution.

Usage: python Enhancements/backtest/exit_rule_study.py [--scope tickets|top_quintile|all]
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from avshunter.c12_outcome import signals as sig  # noqa: E402
from avshunter.c12_outcome.adapters import prices  # noqa: E402
from avshunter.shared.xnys_calendar import is_xnys_session, previous_xnys_session  # noqa: E402
import empirical_option_ev as ev  # noqa: E402

HERE = Path(__file__).resolve().parent
ROWS = HERE / "signal_ticket_backtest_rows.csv"
PRICE_DB = REPO / "data" / "canonical" / "historical_prices.sqlite"
CHAIN_DB = REPO / "data" / "phantom" / "phantom_history.db"
CALIBRATION = json.loads((REPO / "config" / "calibration" / "volatility_range_calibration_v1.json")
                         .read_text(encoding="utf-8"))
SETTINGS = sig.SignalSettings(
    signal_version="SIG-V1-EXIT-STUDY", blocked_final_actions=(), required_price_history_state="INTACT",
    min_cautious_return=0.0, contract_exit_buffer=2, contract_multiplier=100.0, o4_extreme_quantile=0.2,
    min_closed_signals=40, min_issue_sessions=15, interval_z=1.645)
WIDE_STOP_MOVES = 1.5
RULES = ("baseline", "wide_stop", "no_stop", "revalue")


class Chain:
    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        self._cache: dict[tuple[str, str], tuple[float | None, float | None] | None] = {}

    def quote(self, ticker: str, symbol: str, session: date):
        key = (symbol, session.isoformat())
        if key not in self._cache:
            row = self._connection.execute(
                "SELECT bid, ask FROM chain_snapshots WHERE ticker = ? AND quote_date = ? AND option_symbol = ?",
                (ticker, key[1], symbol)).fetchone()
            self._cache[key] = None if row is None else (row[0], row[1])
        return self._cache[key]

    def close(self) -> None:
        self._connection.close()


def last_usable(expiry: date, buffer_sessions: int) -> date:
    session = expiry if is_xnys_session(expiry) else previous_xnys_session(expiry)
    for _ in range(buffer_sessions):
        session = previous_xnys_session(session)
    return session


def still_worth_buying(row, session_spot: float, ask: float, sessions_held: int) -> bool | None:
    """Re-value the option at this session's ask with the remaining hold; None when it cannot be valued."""
    remaining = max(1, int(row.hold) - sessions_held)
    dte = row.dte - sessions_held * 7.0 / 5.0
    if dte <= 0 or ask is None or ask <= 0:
        return None
    result = ev.compute_path_option_ev(
        side="call" if row.direction == "CALL" else "put", spot=session_spot, strike=row.strike, dte=dte,
        bid=ask * 0.98, ask=ask, iv=row.iv, rate=ev.DEFAULT_RISK_FREE_RATE, target=row.target,
        invalidation=row.stop, hold_sessions=remaining, forecast_vol=row.forecast_vol, calibration=CALIBRATION,
        paths=ev.PATH_SETTINGS["paths"], seed=ev.PATH_SETTINGS["seed"])
    if result.get("emp_path_quality_flag") != "OK":
        return None
    return float(result["emp_path_r_cautious"]) > 0


def run_rule(row, bars, chain: Chain, rule: str) -> dict:
    sign = 1.0 if row.direction == "CALL" else -1.0
    entry = date.fromisoformat(row.session)
    expiry = sig.contract_expiry(row.contract)
    cap = last_usable(expiry, SETTINGS.contract_exit_buffer) if expiry else None
    expected_move = row.forecast_vol * math.sqrt(row.hold / 252.0)
    stop = row.stop
    if rule == "wide_stop":
        stop = row.spot * (1 - WIDE_STOP_MOVES * expected_move) if sign > 0 else row.spot * (1 + WIDE_STOP_MOVES * expected_move)
    forward = [b for b in bars if b.session > entry]
    for step, bar in enumerate(forward, start=1):
        if rule in ("baseline", "wide_stop") and sign * ((bar.low if sign > 0 else bar.high) - stop) <= 0:
            return {"state": "EXITED", "reason": "STOP", "session": bar.session, "sessions": step}
        if sign * ((bar.high if sign > 0 else bar.low) - row.target) >= 0:
            return {"state": "EXITED", "reason": "TARGET", "session": bar.session, "sessions": step}
        if cap is not None and bar.session >= cap:
            return {"state": "EXITED", "reason": "CONTRACT_LAST_USABLE", "session": bar.session, "sessions": step}
        if rule == "revalue" and step < row.hold:
            quote = chain.quote(row.ticker, row.contract, bar.session)
            if quote is not None and quote[1]:
                worth = still_worth_buying(row, bar.close, quote[1], step)
                if worth is False:
                    return {"state": "EXITED", "reason": "REVALUED_BELOW_ZERO", "session": bar.session, "sessions": step}
        if step >= row.hold:
            return {"state": "EXITED", "reason": "HOLD_COMPLETE", "session": bar.session, "sessions": step}
    return {"state": "OPEN", "reason": None, "session": None, "sessions": None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["tickets", "top_quintile", "all"], default="tickets")
    args = parser.parse_args()
    frame = pd.read_csv(ROWS)
    frame = frame.dropna(subset=["cautious", "forecast_vol", "hold", "dte", "entry_ask"])
    frame["strike"] = [int(sig.OCC.match(c)["strike"]) / 1000.0 for c in frame.contract]
    if args.scope == "tickets":
        scope = frame[frame.ticket]
    elif args.scope == "top_quintile":
        cut = frame.cautious.quantile(0.8)
        scope = frame[frame.cautious >= cut]
    else:
        scope = frame
    tickers = {str(t).upper() for t in scope.ticker}
    start = date.fromisoformat(min(scope.session))
    bars = prices.load_bars(tickers, previous_xnys_session(start), prices.latest_session(PRICE_DB), PRICE_DB)
    chain = Chain(CHAIN_DB)
    records = []
    try:
        for row in scope.itertuples():
            history = bars.get(row.ticker, [])
            for rule in RULES:
                outcome = run_rule(row, history, chain, rule)
                mark = None
                if outcome["state"] == "EXITED":
                    quote = chain.quote(row.ticker, row.contract, outcome["session"])
                    mark = None if quote is None else quote[0]
                records.append({
                    "rule": rule, "session": row.session, "ticker": row.ticker, "direction": row.direction,
                    "contract": row.contract, "cautious": row.cautious, "entry_ask": row.entry_ask,
                    "exit_reason": outcome["reason"], "sessions_held": outcome["sessions"],
                    "exit_session": outcome["session"].isoformat() if outcome["session"] else None,
                    "exit_bid": mark,
                    "state": "CLOSED" if mark is not None else ("OPEN" if outcome["state"] == "OPEN"
                                                                else "EXIT_MARK_UNAVAILABLE"),
                    "option_return": None if mark is None else mark / row.entry_ask - 1.0,
                })
    finally:
        chain.close()
    results = pd.DataFrame(records)
    results.to_csv(HERE / f"exit_rule_study_{args.scope}_rows.csv", index=False)
    summary = {"scope": args.scope, "candidates": int(len(scope)), "rules": {}}
    for rule in RULES:
        rows = results[results.rule == rule]
        closed = rows[rows.state == "CLOSED"]
        evaluated = sig.evaluate([(date.fromisoformat(s), r) for s, r in zip(closed.session, closed.option_return)],
                                 SETTINGS) if len(closed) else {}
        summary["rules"][rule] = {
            "closed": len(closed),
            "mean_return": round(float(closed.option_return.mean()), 4) if len(closed) else None,
            "median_return": round(float(closed.option_return.median()), 4) if len(closed) else None,
            "hit_rate": round(float((closed.option_return > 0).mean()), 3) if len(closed) else None,
            "worst": round(float(closed.option_return.min()), 4) if len(closed) else None,
            "best": round(float(closed.option_return.max()), 4) if len(closed) else None,
            "mean_sessions_held": round(float(closed.sessions_held.mean()), 2) if len(closed) else None,
            "exit_reasons": rows.exit_reason.value_counts().to_dict(),
            "exit_mark_unavailable": int((rows.state == "EXIT_MARK_UNAVAILABLE").sum()),
            "still_open": int((rows.state == "OPEN").sum()),
            "max_drawdown_equal_weight": round(sig.max_drawdown(
                closed.sort_values("exit_session").option_return.tolist()), 4) if len(closed) else None,
            "verdict": evaluated.get("verdict"),
        }
    (HERE / f"exit_rule_study_{args.scope}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
