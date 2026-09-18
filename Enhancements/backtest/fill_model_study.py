"""Fill-model study (read-only; ACK 18 Sep 2026).

Our backtests assumed the worst case: buy at the ask, sell at the bid. Muravyev and Pearson (2020, RFS 33(11),
"Options Trading Costs Are Lower than You Think") measure effective spreads of 20-40% of the quoted spread for
traders who time execution, and an average effective spread a quarter smaller than conventional estimates.

This re-marks the recorded backtest trades under three fill models, changing nothing else:

  quoted   entry at the ask, exit at the bid                       (effective spread fraction 1.00)
  timed    entry and exit 30% of the half-spread away from mid     (0.30, the mid-point of the paper's 20-40%)
  mid      entry and exit at the mid                               (0.00, an upper bound, not achievable in full)

Exit quotes come from the stored chain on the exit session; a session without a stored row is not marked.

Usage: python Enhancements/backtest/fill_model_study.py
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from avshunter.c12_outcome import signals as sig  # noqa: E402

HERE = Path(__file__).resolve().parent
CHAIN_DB = REPO / "data" / "phantom" / "phantom_history.db"
MODELS = {"quoted": 1.00, "timed": 0.30, "mid": 0.00}
SETTINGS = sig.SignalSettings(
    signal_version="FILL-STUDY", blocked_final_actions=(), required_price_history_state="INTACT",
    min_cautious_return=0.0, contract_exit_buffer=2, contract_multiplier=100.0, o4_extreme_quantile=0.2,
    min_closed_signals=40, min_issue_sessions=15, interval_z=1.645, min_dte_cover=1.5,
    min_contract_dte_days=21, max_out_of_the_money=0.05)


def price(bid: float, ask: float, fraction: float, side: str) -> float | None:
    """Entry pays, exit receives: mid +/- fraction x half the quoted spread."""
    if bid is None or ask is None or not np.isfinite(bid) or not np.isfinite(ask) or ask <= 0 or ask < bid:
        return None
    mid, half = (bid + ask) / 2.0, (ask - bid) / 2.0
    value = mid + fraction * half if side == "entry" else mid - fraction * half
    return value if value > 0 else None


def main() -> int:
    rows = pd.read_csv(HERE / "signal_ticket_backtest_rows.csv")
    rows = rows[rows.exit_session_marked.notna() & rows.entry_bid.notna() & rows.entry_ask.notna()]
    chain = sqlite3.connect(f"file:{CHAIN_DB.as_posix()}?mode=ro", uri=True)
    records = []
    try:
        for row in rows.itertuples():
            quote = chain.execute(
                "SELECT bid, ask FROM chain_snapshots WHERE ticker = ? AND quote_date = ? AND option_symbol = ?",
                (row.ticker, row.exit_session_marked, row.contract)).fetchone()
            if quote is None or quote[0] is None or quote[1] is None:
                continue
            exit_bid, exit_ask = float(quote[0]), float(quote[1])
            record = {"session": row.session, "ticker": row.ticker, "contract": row.contract,
                      "ticket": bool(row.ticket), "cautious": row.cautious,
                      "entry_spread": (row.entry_ask - row.entry_bid) / ((row.entry_ask + row.entry_bid) / 2),
                      "exit_spread": (exit_ask - exit_bid) / ((exit_ask + exit_bid) / 2) if exit_ask + exit_bid > 0 else None,
                      "thesis_state": row.thesis_state}
            for name, fraction in MODELS.items():
                entry = price(row.entry_bid, row.entry_ask, fraction, "entry")
                exit_price = price(exit_bid, exit_ask, fraction, "exit")
                record[f"return_{name}"] = None if (entry is None or exit_price is None) else exit_price / entry - 1.0
            records.append(record)
    finally:
        chain.close()
    frame = pd.DataFrame(records)
    frame.to_csv(HERE / "fill_model_study_rows.csv", index=False)

    def stats(group: pd.DataFrame, column: str) -> dict:
        values = group[column].dropna()
        if values.empty:
            return {}
        return {"closed": len(values), "mean": round(float(values.mean()), 4),
                "median": round(float(values.median()), 4),
                "hit_rate": round(float((values > 0).mean()), 3),
                "share_ge_100pct": round(float((values >= 1).mean()), 4)}

    top = frame[frame.cautious >= frame.cautious.quantile(0.8)] if len(frame) else frame
    summary = {
        "source": "signal_ticket_backtest_rows.csv re-marked with stored exit quotes",
        "models": {k: f"effective spread fraction {v:.2f}" for k, v in MODELS.items()},
        "median_entry_spread": round(float(frame.entry_spread.median()), 4) if len(frame) else None,
        "median_exit_spread": round(float(frame.exit_spread.median()), 4) if len(frame) else None,
        "all_candidates": {name: stats(frame, f"return_{name}") for name in MODELS},
        "top_cautious_quintile": {name: stats(top, f"return_{name}") for name in MODELS},
        "tickets": {name: stats(frame[frame.ticket], f"return_{name}") for name in MODELS},
        "reference": "Muravyev & Pearson (2020) RFS 33(11): effective spreads 20-40% of quoted for timed execution",
    }
    (HERE / "fill_model_study_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
