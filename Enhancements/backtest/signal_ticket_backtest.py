"""Backtest of the signal ticket rules on recorded evening books (read-only; ACK 17 Sep 2026).

Question: applied to each recorded evening book, would the ticket filter (the option's cautious return at the
entry premium, above zero, on a tradeable contract) have separated winners from losers?

It runs the SHIPPED rules — ``avshunter.c12_outcome.signals.decide`` / ``plan_exit`` / ``mark_signal`` /
``evaluate`` and ``empirical_option_ev.compute_path_expression_ev`` — so what is measured is the code that issues
live tickets, not a re-implementation.

Point-in-time inputs only:
  - thesis (direction, stop, target, hold), contract, and its end-of-day bid/ask/IV as the run recorded them;
  - the volatility forecast recomputed from bars up to that session with the production Layer 3 model (older runs
    did not record it), together with DQ-12 price-history integrity;
  - the Abdi-Ranaldo share spread from bars up to that session.

Differences from a live ticket, stated rather than hidden:
  - entry at the evening close quote, not the morning intraday quote, so there is no morning requote, no
    delayed-quote adjustment and no morning gate;
  - exits are marked from the stored chain on the exit session only; a session with no stored chain row is
    EXIT_MARK_UNAVAILABLE, never the nearest date. Daily chains exist only for recent weeks, so option P&L
    coverage is thin before September 2026.

Two layers are reported: the thesis layer (underlying reaches target or stop, full coverage) and the option layer
(return on premium where both marks exist), each for tickets and for the candidates the filter rejected.

Usage: python Enhancements/backtest/signal_ticket_backtest.py [--sessions N] [--limit-tickers N]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
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
from avshunter.c12_outcome.model import Bar  # noqa: E402
from avshunter.shared.xnys_calendar import is_xnys_session, previous_xnys_session  # noqa: E402
import empirical_option_ev as ev  # noqa: E402
import layer3_forward_variance as l3  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNS = REPO / "data" / "output" / "runs"
PRICE_DB = REPO / "data" / "canonical" / "historical_prices.sqlite"
CHAIN_DB = REPO / "data" / "phantom" / "phantom_history.db"
CALIBRATION = json.loads((REPO / "config" / "calibration" / "volatility_range_calibration_v1.json")
                         .read_text(encoding="utf-8"))
SETTINGS = sig.SignalSettings(
    signal_version="SIG-V1-BACKTEST", blocked_final_actions=("BLOCK", "CONTRACT_REPAIR"),
    required_price_history_state="INTACT", contract_exit_buffer=2,
    contract_multiplier=100.0, o4_extreme_quantile=0.2, min_closed_signals=40, min_issue_sessions=15,
    interval_z=1.645, thesis_window_sessions=20,
    max_out_of_the_money=0.05, max_entry_spread_fraction=0.10, max_tickets_per_session=5)
FORECAST_BARS = 260
SPREAD_LIMIT = 0.25          # governed reviewable ceiling (long_option_execution policy), fraction of mid


@dataclass(frozen=True, slots=True)
class Candidate:
    session: date
    run_id: str
    ticker: str
    direction: str
    contract: str
    strike: float
    expiry: date
    dte: float
    bid: float
    ask: float
    iv: float
    spot: float
    stop: float
    target: float
    hold: int
    forecast_vol: float
    share_spread: float | None
    price_history_state: str
    forecast_method: str


def sessions_with_books(limit: int | None) -> list[tuple[date, str, Path]]:
    """One run per evidence session (the latest), newest first."""
    found: dict[date, tuple[str, Path]] = {}
    for run_dir in sorted(RUNS.iterdir()):
        path = run_dir / "options" / f"options_intelligence_{run_dir.name}.csv"
        if not path.is_file():
            continue
        try:
            stamp = date(int(run_dir.name[:4]), int(run_dir.name[4:6]), int(run_dir.name[6:8]))
        except ValueError:
            continue
        session = stamp if is_xnys_session(stamp) else previous_xnys_session(stamp)
        found[session] = (run_dir.name, path)          # later run of the same session wins
    ordered = [(s, *found[s]) for s in sorted(found, reverse=True)]
    return ordered[:limit] if limit else ordered


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_bars(tickers: set[str], start: date, end: date) -> dict[str, list[Bar]]:
    return prices.load_bars(tickers, start, end, PRICE_DB)


def forecast_for(bars: list[Bar], ticker: str, iv: float | None) -> tuple[float | None, str, str]:
    """Point-in-time Layer 3 forecast (and DQ-12 state) from bars up to and including the session."""
    if len(bars) < 30:
        return None, "NO_FORECAST", "INSUFFICIENT_HISTORY"
    frame = pd.DataFrame({"close": [b.close for b in bars], "high": [b.high for b in bars],
                          "low": [b.low for b in bars],
                          "trading_date": [b.session.isoformat() for b in bars]})
    result = l3.compute_forward_variance(ticker, frame, implied_vol=iv)
    raw = result.forward_realised_vol_raw if result.forward_realised_vol_raw else result.forward_realised_vol
    return raw, result.method, result.price_history_state


def share_spread_from(bars: list[Bar]) -> float | None:
    window = bars[-ev.PATH_SETTINGS["share_spread_window_sessions"]:]
    if len(window) < ev.PATH_SETTINGS["share_spread_min_sessions"]:
        return None
    return ev.abdi_ranaldo_spread([b.high for b in window], [b.low for b in window], [b.close for b in window])


def candidates_for(session: date, run_id: str, path: Path, bars: dict[str, list[Bar]],
                   limit_tickers: int | None) -> tuple[list[Candidate], dict[str, int]]:
    frame = pd.read_csv(path, low_memory=False)
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    out: list[Candidate] = []
    for row in frame.to_dict("records"):
        if limit_tickers and len(out) >= limit_tickers:
            break
        ticker = str(row.get("ticker") or "").upper()
        direction = str(row.get("final_direction") or row.get("direction") or "").upper()
        contract = str(row.get("contract_occ_symbol") or "").upper()
        if direction not in ("CALL", "PUT"):
            skip("DIRECTION_NOT_CALL_OR_PUT")
            continue
        match = sig.OCC.match(contract)
        if not match or match["side"] != direction[0]:
            skip("NO_CONTRACT")
            continue
        bid, ask = _num(row.get("contract_bid")), _num(row.get("contract_ask"))
        iv = _num(row.get("contract_iv"))
        spot = _num(row.get("underlying_price"))
        stop = _num(row.get("invalidation_spot"))
        target = _num(row.get("structural_target")) or _num(row.get("target_spot"))
        hold = _num(row.get("layer2__recommended_hold_days"))
        dte = _num(row.get("contract_dte")) or _num(row.get("dte"))
        expiry = sig.contract_expiry(contract)
        if None in (bid, ask, iv, spot, stop, target, hold, dte) or expiry is None:
            skip("THESIS_OR_QUOTE_INCOMPLETE")
            continue
        history = bars.get(ticker) or []
        history = [b for b in history if b.session <= session]
        forecast, method, history_state = forecast_for(history, ticker, iv)
        if history_state != "INTACT":
            skip("PRICE_HISTORY_NOT_INTACT")
            continue
        if forecast is None or forecast <= 0:
            skip("FORECAST_UNAVAILABLE")
            continue
        out.append(Candidate(session=session, run_id=run_id, ticker=ticker, direction=direction, contract=contract,
                             strike=int(match["strike"]) / 1000.0, expiry=expiry, dte=float(dte), bid=bid, ask=ask,
                             iv=iv, spot=spot, stop=stop, target=target, hold=int(round(hold)),
                             forecast_vol=forecast, share_spread=share_spread_from(history),
                             price_history_state=history_state, forecast_method=method))
    return out, skipped


def prepared_from(candidate: Candidate) -> sig.Prepared:
    """The same inputs a live ticket carries, taken from the evening close instead of the morning quote."""
    spread = (candidate.ask - candidate.bid) / ((candidate.ask + candidate.bid) / 2.0) if candidate.bid > 0 else None
    last_usable = candidate.expiry
    for _ in range(SETTINGS.contract_exit_buffer):
        last_usable = previous_xnys_session(last_usable if is_xnys_session(last_usable) else previous_xnys_session(last_usable))
    executable = (candidate.bid > 0 and candidate.ask >= candidate.bid and spread is not None
                  and spread <= SPREAD_LIMIT and last_usable > candidate.session)
    return sig.Prepared(
        ticker=candidate.ticker, direction=candidate.direction, contract_symbol=candidate.contract,
        strike=candidate.strike, expiry=candidate.expiry, last_usable_session=last_usable, live_spot=candidate.spot,
        live_spot_utc=None, stop=candidate.stop, target=candidate.target, hold_sessions=candidate.hold,
        quote_bid=candidate.bid, quote_ask=candidate.ask, quote_timestamp_utc=None,
        quote_state=sig.QUOTE_CURRENT_SESSION, adjustment_state="EVENING_CLOSE_QUOTE", spot_at_quote=None,
        delta=None, shift=None, bid=candidate.bid, ask=candidate.ask, option_executable=executable,
        iv=candidate.iv, iv_source="EVENING_CONTRACT",
        path_inputs=dict(side="call" if candidate.direction == "CALL" else "put", spot=candidate.spot,
                         strike=candidate.strike, dte=candidate.dte, bid=candidate.bid, ask=candidate.ask,
                         iv=candidate.iv, rate=ev.DEFAULT_RISK_FREE_RATE, target=candidate.target,
                         invalidation=candidate.stop, hold_sessions=candidate.hold,
                         forecast_vol=candidate.forecast_vol, share_spread=candidate.share_spread))


class ChainBids:
    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)

    def bid(self, ticker: str, symbol: str, session: date) -> float | None:
        row = self._connection.execute(
            "SELECT bid FROM chain_snapshots WHERE ticker = ? AND quote_date = ? AND option_symbol = ?",
            (ticker, session.isoformat(), symbol)).fetchone()
        return None if row is None else row[0]

    def close(self) -> None:
        self._connection.close()


def thesis_outcome(candidate: Candidate, forward: list[Bar]) -> tuple[str, date | None, int | None]:
    """What the underlying did: the first of stop, target or the planned hold (close-based on the entry session)."""
    sign = 1.0 if candidate.direction == "CALL" else -1.0
    for step, bar in enumerate(forward, start=1):
        if sign * ((bar.low if sign > 0 else bar.high) - candidate.stop) <= 0:
            return "STOP", bar.session, step
        if sign * ((bar.high if sign > 0 else bar.low) - candidate.target) >= 0:
            return "TARGET", bar.session, step
        if step >= candidate.hold:
            return "HOLD_COMPLETE", bar.session, step
    return "OPEN", None, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=None, help="most recent N book sessions")
    parser.add_argument("--limit-tickers", type=int, default=None, help="first N candidates per session (smoke)")
    args = parser.parse_args()

    books = sessions_with_books(args.sessions)
    if not books:
        print("no recorded books found", file=sys.stderr)
        return 2
    as_of = prices.latest_session(PRICE_DB)
    chain = ChainBids(CHAIN_DB)
    rows: list[dict] = []
    skipped_all: dict[str, int] = {}
    try:
        for session, run_id, path in books:
            frame = pd.read_csv(path, low_memory=False, usecols=["ticker"])
            tickers = {str(t).upper() for t in frame["ticker"].dropna()}
            history = load_bars(tickers, previous_xnys_session(session) - pd.Timedelta(days=FORECAST_BARS * 2).to_pytimedelta(), as_of)
            candidates, skipped = candidates_for(session, run_id, path, history, args.limit_tickers)
            for reason, count in skipped.items():
                skipped_all[reason] = skipped_all.get(reason, 0) + count
            for candidate in candidates:
                prepared = prepared_from(candidate)
                valuation = ev.compute_path_expression_ev(**prepared.path_inputs, calibration=CALIBRATION,
                                                          paths=ev.PATH_SETTINGS["paths"], seed=ev.PATH_SETTINGS["seed"])
                reason, fields = sig.decide(prepared, valuation, SETTINGS)
                forward = [b for b in history.get(candidate.ticker, []) if b.session > candidate.session]
                state, exit_session, step = thesis_outcome(candidate, forward)
                record = {
                    "session": candidate.session.isoformat(), "run_id": candidate.run_id, "ticker": candidate.ticker,
                    "direction": candidate.direction, "contract": candidate.contract, "entry_ask": candidate.ask,
                    "entry_bid": candidate.bid, "spot": candidate.spot, "stop": candidate.stop,
                    "target": candidate.target, "hold": candidate.hold, "dte": candidate.dte, "iv": candidate.iv,
                    "forecast_vol": candidate.forecast_vol, "forecast_method": candidate.forecast_method,
                    "spread_fraction": (candidate.ask - candidate.bid) / ((candidate.ask + candidate.bid) / 2.0),
                    "cautious": valuation.get("emp_path_r_cautious"), "central": valuation.get("emp_path_r_central"),
                    "upside": valuation.get("emp_path_r_upside"),
                    "valuation_flag": valuation.get("emp_path_quality_flag"),
                    "ticket": reason is None, "rejection": reason,
                    "thesis_state": state, "thesis_exit_session": exit_session.isoformat() if exit_session else None,
                    "thesis_sessions": step,
                }
                if state != "OPEN" and exit_session is not None:
                    last_usable = prepared.last_usable_session
                    capped = min(exit_session, last_usable) if last_usable else exit_session
                    mark = chain.bid(candidate.ticker, candidate.contract, capped)
                    record["exit_session_marked"] = capped.isoformat()
                    record["exit_bid"] = mark
                    record["option_return"] = None if mark is None else mark / candidate.ask - 1.0
                    record["option_state"] = "CLOSED" if mark is not None else "EXIT_MARK_UNAVAILABLE"
                else:
                    record["option_state"] = "OPEN"
                rows.append(record)
            print(f"{session.isoformat()} {run_id}: {len(candidates)} candidates, "
                  f"{sum(1 for r in rows if r['session'] == session.isoformat() and r['ticket'])} tickets", flush=True)
    finally:
        chain.close()

    frame = pd.DataFrame(rows)
    frame.to_csv(HERE / "signal_ticket_backtest_rows.csv", index=False)
    summary = summarise(frame, skipped_all)
    (HERE / "signal_ticket_backtest_summary.json").write_text(json.dumps(summary, indent=2, default=str),
                                                              encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


def summarise(frame: pd.DataFrame, skipped: dict[str, int]) -> dict:
    def group(rows: pd.DataFrame) -> dict:
        closed = rows[rows.option_state == "CLOSED"]
        thesis = rows[rows.thesis_state.isin(["STOP", "TARGET", "HOLD_COMPLETE"])]
        evaluated = sig.evaluate([(date.fromisoformat(s), r) for s, r in
                                  zip(closed.session, closed.option_return)], SETTINGS) if len(closed) else {}
        return {
            "candidates": len(rows), "sessions": int(rows.session.nunique()),
            "thesis_scored": len(thesis),
            "thesis_target_share": round(float((thesis.thesis_state == "TARGET").mean()), 3) if len(thesis) else None,
            "thesis_stop_share": round(float((thesis.thesis_state == "STOP").mean()), 3) if len(thesis) else None,
            "option_closed": len(closed),
            "option_mean_return": round(float(closed.option_return.mean()), 4) if len(closed) else None,
            "option_median_return": round(float(closed.option_return.median()), 4) if len(closed) else None,
            "option_hit_rate": round(float((closed.option_return > 0).mean()), 3) if len(closed) else None,
            "option_worst": round(float(closed.option_return.min()), 4) if len(closed) else None,
            "exit_mark_unavailable": int((rows.option_state == "EXIT_MARK_UNAVAILABLE").sum()),
            "still_open": int((rows.option_state == "OPEN").sum()),
            "median_spread_fraction": round(float(rows.spread_fraction.median()), 4) if len(rows) else None,
            "verdict": evaluated.get("verdict"),
            "mean_interval": [round(evaluated["low"], 4), round(evaluated["high"], 4)]
            if evaluated.get("low") is not None else None,
        }

    tickets = frame[frame.ticket]
    rejected = frame[~frame.ticket]
    return {
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds"),
        "signal_version": SETTINGS.signal_version,
        "sessions": sorted(frame.session.unique().tolist()),
        "candidates_skipped_before_valuation": skipped,
        "tickets": group(tickets),
        "rejected_candidates": group(rejected),
        "rejection_reasons": rejected.rejection.value_counts().head(10).to_dict(),
        "caveats": [
            "entry at the recorded evening close ask, not the morning intraday quote",
            "no morning requote, delayed-quote adjustment or morning gate",
            "exit marks come from the stored chain on the exit session only (no nearest-date substitution)",
            "daily chains exist only for recent weeks, so option P&L coverage is thin before September 2026",
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
