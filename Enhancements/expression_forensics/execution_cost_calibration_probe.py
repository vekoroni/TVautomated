"""Execution-cost reality probe (read-only).

Question: from what is observable at entry (spread, volume, open interest, DTE, moneyness, premium),
how much of the premium does a buy-at-ask / sell-at-bid round trip cost k sessions later, and how
often does the contract stop being quoted? Uses the daily full panel in chain_snapshots.

  venv\\Scripts\\python.exe Enhancements\\expression_forensics\\execution_cost_calibration_probe.py
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sqlite3
import statistics as st

REPO = Path(__file__).resolve().parents[2]
MAIN_REPO = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
CHAINS = MAIN_REPO / "data" / "phantom" / "phantom_history.db"
OUT = Path(__file__).resolve().parent / "execution_cost_calibration_probe.json"

PAIRS = [("2026-08-28", "2026-09-05"), ("2026-09-01", "2026-09-09"), ("2026-09-04", "2026-09-11"),
         ("2026-09-08", "2026-09-15")]   # entry session, exit session (~5 sessions later)
PAIRS = [(a, b) for a, b in PAIRS]


def bucket(value, edges, labels):
    if value is None:
        return "MISSING"
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


def main():
    con = sqlite3.connect(f"file:{CHAINS.as_posix()}?mode=ro", uri=True)
    sessions = [r[0] for r in con.execute("SELECT DISTINCT quote_date FROM chain_snapshots WHERE quote_date >= '2026-08-28' ORDER BY 1")]
    pairs = []
    for i, d in enumerate(sessions):
        if i + 5 < len(sessions) and d <= "2026-09-09":
            pairs.append((d, sessions[i + 5]))
    groups = defaultdict(list)
    dropped = defaultdict(lambda: [0, 0])
    for entry_day, exit_day in pairs:
        rows = con.execute(
            """
            SELECT e.side, e.strike, e.dte, e.bid, e.ask, e.volume, e.open_interest, e.underlying_price,
                   x.bid, x.ask, x.underlying_price
            FROM chain_snapshots e
            LEFT JOIN chain_snapshots x
              ON x.ticker = e.ticker AND x.quote_date = ? AND x.option_symbol = e.option_symbol
            WHERE e.quote_date = ? AND e.ask > 0 AND e.bid > 0 AND e.ask >= e.bid AND e.dte BETWEEN 7 AND 60
            """, (exit_day, entry_day))
        for side, strike, dte, bid, ask, vol, oi, s0, xbid, xask, s1 in rows:
            mid = (bid + ask) / 2
            spread = (ask - bid) / ask
            if not s0:
                continue
            money = (s0 - strike) / s0 * (1 if side == "call" else -1)
            key = (
                bucket(spread, [0.05, 0.10, 0.20, 0.35], ["<5%", "5-10%", "10-20%", "20-35%", ">=35%"]),
                "TRADED" if (vol or 0) > 0 else "NO_VOLUME",
                bucket(oi, [10, 100, 1000], ["OI<10", "OI10-99", "OI100-999", "OI>=1000"]),
            )
            dropped[key][1] += 1
            if xbid is None or xask is None or xask <= 0:
                dropped[key][0] += 1
                continue
            xmid = (xbid + xask) / 2
            entry_cost = (ask - mid) / ask
            exit_cost = (xmid - xbid) / ask
            groups[key].append((entry_cost, exit_cost, xbid / ask - 1, xmid / mid - 1, bucket(money, [-0.10, -0.03, 0.03], ["OTM>10%", "OTM3-10%", "ATM", "ITM"]), mid))
    out = []
    for key, items in sorted(groups.items()):
        rt = [a + b for a, b, *_ in items]
        out.append({
            "entry_spread": key[0], "volume": key[1], "open_interest": key[2], "n": len(items),
            "unquoted_after_5_sessions": dropped[key][0] / dropped[key][1],
            "round_trip_cost_median": st.median(rt), "round_trip_cost_mean": st.fmean(rt),
            "entry_half_spread_median": st.median(a for a, *_ in items),
            "exit_half_spread_median": st.median(b for _, b, *_ in items),
            "ask_to_bid_return_median": st.median(c for _, _, c, *_ in items),
            "mid_to_mid_return_median": st.median(d for *_, d, _, _ in items),
        })
    OUT.write_text(json.dumps({"pairs": pairs, "cells": out}, indent=2), encoding="utf-8")
    print("pairs", pairs)
    print(f"{'spread':>7} {'vol':>9} {'oi':>10} {'n':>8} {'unquoted':>8} {'rt_cost_med':>11} {'entry_hs':>8} {'exit_hs':>8} {'ask->bid':>8} {'mid->mid':>8}")
    for c in out:
        print(f"{c['entry_spread']:>7} {c['volume']:>9} {c['open_interest']:>10} {c['n']:>8} {c['unquoted_after_5_sessions']:>8.2f} "
              f"{c['round_trip_cost_median']:>11.3f} {c['entry_half_spread_median']:>8.3f} {c['exit_half_spread_median']:>8.3f} "
              f"{c['ask_to_bid_return_median']:>8.3f} {c['mid_to_mid_return_median']:>8.3f}")


if __name__ == "__main__":
    main()
