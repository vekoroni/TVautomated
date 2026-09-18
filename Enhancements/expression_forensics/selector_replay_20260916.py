"""Replay `select_best_contract` on last night's recorded chains (read-only, no provider calls).

Run once per code tree; the tree is chosen by --root (its `scripts/avshunter_options_intelligence.py` is
imported). Inputs: options output of run 20260916_223756 (ctx fields per ticker) and the 2026-09-16
MARKETDATA chain rows in phantom `chain_snapshots` (the canonical evening chain projection).

  venv\\Scripts\\python.exe selector_replay_20260916.py --root <tree> --out <csv>
  [--run 20260917_214854 --session 2026-09-17]   (18 Sep 2026: any recorded run; the horizon the run's
  selector actually used - contract_rejection_horizon - is replayed when recorded)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
import sys

import pandas as pd

MAIN = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
RUN = MAIN / "data" / "output" / "runs" / "20260916_223756" / "options" / "options_intelligence_20260916_223756.csv"
CHAINS = MAIN / "data" / "phantom" / "phantom_history.db"
SESSION = "2026-09-16"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--run", default="20260916_223756")
    parser.add_argument("--session", default=SESSION)
    args = parser.parse_args()
    run_csv = MAIN / "data" / "output" / "runs" / args.run / "options" / f"options_intelligence_{args.run}.csv"
    sys.path.insert(0, args.root)
    logging.disable(logging.WARNING)
    from scripts import avshunter_options_intelligence as oi   # noqa: E402

    rows = pd.read_csv(run_csv, low_memory=False)
    con = sqlite3.connect(f"file:{CHAINS.as_posix()}?mode=ro", uri=True)
    out = []
    for _, r in rows.iterrows():
        direction = str(r.get("final_direction") or "").upper()
        used = r.get("contract_rejection_horizon")
        horizon = used if isinstance(used, str) and used in ("1_5d", "6_10d", "11_20d") else r.get("horizon_bucket")
        if direction not in ("CALL", "PUT") or horizon not in ("1_5d", "6_10d", "11_20d"):
            continue
        chain_rows = con.execute(
            "SELECT option_symbol, side, strike, dte, expiration_ts, bid, ask, mid, open_interest, volume, iv, delta, "
            "gamma, theta, vega, underlying_price FROM chain_snapshots WHERE ticker = ? AND quote_date = ? AND source = 'MARKETDATA'",
            (r["ticker"], args.session)).fetchall()
        if not chain_rows:
            out.append({"ticker": r["ticker"], "chain_rows": 0})
            continue
        payload = []
        for sym, side, strike, dte, exp_ts, bid, ask, mid, oi_, vol, iv, delta, gamma, theta, vega, und in chain_rows:
            quote = oi._normalise_option_quote(bid, ask, mid)
            payload.append({
                "underlying": r["ticker"], "symbol": sym, "right": "C" if side == "call" else "P", "strike": strike,
                "dte": dte, "expiration_date": datetime.fromtimestamp(exp_ts, tz=timezone.utc).date().isoformat() if exp_ts else None,
                "open_interest": oi_, "volume": vol, "implied_vol": iv, "gamma": gamma, "delta": delta, "theta": theta,
                "vega": vega, "bid": quote["bid"], "ask": quote["ask"], "mid": quote["mid"], "spread_pct": quote["spread_pct"],
                "quote_quality": quote["quote_quality"], "quality_flags": quote["quality_flags"], "underlying_price": und,
            })
        chain = oi._chain_v2_to_options_frame(payload)
        spot = float(r.get("stock_price") or r.get("entry_price") or 0) or float(chain_rows[0][-1] or 0)
        window = oi.governed_dte_window(horizon)
        hold = int(r.get("layer2__recommended_hold_days") or 0) or window[1]
        ctx = {"ticker": r["ticker"], "direction": direction, "spot": spot, "entry": float(r.get("entry_price") or spot),
               "structural_target": r.get("structural_target") if pd.notna(r.get("structural_target")) else None,
               "dte_window": window, "dte_config": oi.governed_dte_config(horizon), "hold_days": hold,
               "horizon_bucket": horizon}
        chosen = oi.select_best_contract(chain, ctx)
        out.append({"ticker": r["ticker"], "horizon": horizon, "direction": direction, "chain_rows": len(chain_rows),
                    "recorded_contract": r.get("contract_occ_symbol"), "recorded_spread": r.get("contract_spread_pct"),
                    "selected": chosen.get("symbol") if chosen else None,
                    "selected_spread": chosen.get("spread_pct") if chosen else None,
                    "selected_quality": chosen.get("quote_quality") if chosen else None,
                    "selected_delta": chosen.get("delta") if chosen else None,
                    "selected_dte": chosen.get("dte") if chosen else None,
                    "spread_limit": oi.horizon_spread_limit(horizon),
                    "spread_above_limit": chosen.get("spread_above_limit") if chosen else None,
                    "runway_state": chosen.get("contract_runway_state") if chosen else None,
                    "recorded_liquidity_state": r.get("liquidity_state")})
    pd.DataFrame(out).to_csv(args.out, index=False)
    print(f"replayed {len(out)} tickers -> {args.out}")


if __name__ == "__main__":
    main()
