"""Batch 2 of the scenario register - layer D exits (ACK 19 Sep 2026). Read-only research code.

Reuses the 17 Sep exit-study harness (same rows, bars, stored-chain marks; no substitution) and adds:
  S-EXIT-1  fixed_1 / fixed_3 / fixed_5 / fixed_10: exit after h sessions (or the contract's last usable session)
  S-EXIT-2  no_stop: no underlying stop inside the hold (target, hold or last usable only)
  S-EXIT-3  wide_stop: stop at 1.5 expected moves over the hold
  S-EXIT-8  fair_value_floor: S-EXIT-6 with the fair-value exit suspended once the bid is >= 2 x the entry ask
  S-EXIT-6  fair_value: no stop; each session with a quote, hold only while the option's expected (central) value of
            holding exceeds what selling at the BID pays now - the fair version of the degenerate re-buy-at-ask rule
  baseline  as is: stop / target / planned hold / last usable
Every rule reports the right-tail measures and the paired difference against the baseline on the same trades.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exit_rule_study as base  # noqa: E402  (the 17 Sep harness)

sig, ev, prices = base.sig, base.ev, base.prices
RULES = ("baseline", "no_stop", "wide_stop", "fixed_1", "fixed_3", "fixed_5", "fixed_10", "fair_value",
         "fair_value_floor")
TAIL_FLOOR = 2.0          # S-EXIT-8: at bid >= 2 x entry ask (+100%) the fair-value exit is suspended


def worth_holding(row, spot: float, bid: float, ask: float, sessions_held: int) -> bool | None:
    """Expected exit value of holding the rest of the plan versus selling at the bid now."""
    remaining = max(1, int(row.hold) - sessions_held)
    dte = row.dte - sessions_held * 7.0 / 5.0
    if dte <= 0 or not bid or bid <= 0 or not ask or ask <= 0:
        return None
    result = ev.compute_path_option_ev(
        side="call" if row.direction == "CALL" else "put", spot=spot, strike=row.strike, dte=dte,
        bid=bid, ask=bid, iv=row.iv, rate=ev.DEFAULT_RISK_FREE_RATE, target=row.target,
        invalidation=spot * 0.01 if row.direction == "CALL" else spot * 100.0,   # unreachable: no stop
        hold_sessions=remaining, forecast_vol=row.forecast_vol, calibration=base.CALIBRATION,
        paths=ev.PATH_SETTINGS["paths"], seed=ev.PATH_SETTINGS["seed"])
    if result.get("emp_path_quality_flag") != "OK":
        return None
    return float(result["emp_path_r_central"]) > 0          # priced against the bid: holding beats selling now


def run(row, bars, chain, rule: str) -> dict:
    if rule in ("baseline", "no_stop", "wide_stop"):
        return base.run_rule(row, bars, chain, rule)
    sign = 1.0 if row.direction == "CALL" else -1.0
    entry = date.fromisoformat(row.session)
    expiry = sig.contract_expiry(row.contract)
    cap = base.last_usable(expiry, base.SETTINGS.contract_exit_buffer) if expiry else None
    fixed = int(rule.split("_")[1]) if rule.startswith("fixed_") else None
    for step, bar in enumerate([b for b in bars if b.session > entry], start=1):
        if cap is not None and bar.session >= cap:
            return {"state": "EXITED", "reason": "CONTRACT_LAST_USABLE", "session": bar.session, "sessions": step}
        if fixed is not None and step >= fixed:
            return {"state": "EXITED", "reason": f"FIXED_{fixed}", "session": bar.session, "sessions": step}
        if rule in ("fair_value", "fair_value_floor"):
            if sign * ((bar.high if sign > 0 else bar.low) - row.target) >= 0:
                return {"state": "EXITED", "reason": "TARGET", "session": bar.session, "sessions": step}
            quote = chain.quote(row.ticker, row.contract, bar.session)
            protected = (rule == "fair_value_floor" and quote is not None and quote[0]
                         and quote[0] >= TAIL_FLOOR * row.entry_ask)
            if quote is not None and step < row.hold and not protected:
                keep = worth_holding(row, bar.close, quote[0], quote[1], step)
                if keep is False:
                    return {"state": "EXITED", "reason": "SELL_BEATS_HOLD", "session": bar.session, "sessions": step}
            if step >= row.hold:
                return {"state": "EXITED", "reason": "HOLD_COMPLETE", "session": bar.session, "sessions": step}
    return {"state": "OPEN", "reason": None, "session": None, "sessions": None}


def tail(returns: pd.Series) -> dict:
    r = returns.dropna()
    positive = r[r > 0].sum()
    return {
        "closed": int(len(r)), "mean": round(float(r.mean()), 4), "median": round(float(r.median()), 4),
        "hit_rate": round(float((r > 0).mean()), 3),
        **{f"share_ge_{int(t * 100)}pct": round(float((r >= t).mean()), 4) for t in (0.5, 1.0, 2.0, 5.0)},
        "largest_winner": round(float(r.max()), 4),
        "tail_contribution": round(float(r[r >= 1.0].sum() / positive), 3) if positive > 0 else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["tickets", "top_quintile"], default="top_quintile")
    args = parser.parse_args()
    frame = pd.read_csv(base.ROWS).dropna(subset=["cautious", "forecast_vol", "hold", "dte", "entry_ask"])
    frame["strike"] = [int(sig.OCC.match(c)["strike"]) / 1000.0 for c in frame.contract]
    scope = frame[frame.ticket] if args.scope == "tickets" else frame[frame.cautious >= frame.cautious.quantile(0.8)]
    bars = prices.load_bars({str(t).upper() for t in scope.ticker},
                            base.previous_xnys_session(date.fromisoformat(min(scope.session))),
                            prices.latest_session(base.PRICE_DB), base.PRICE_DB)
    chain = base.Chain(base.CHAIN_DB)
    records = []
    try:
        for row in scope.itertuples():
            for rule in RULES:
                out = run(row, bars.get(row.ticker, []), chain, rule)
                mark = None
                if out["state"] == "EXITED":
                    quote = chain.quote(row.ticker, row.contract, out["session"])
                    mark = None if quote is None else quote[0]
                records.append({"rule": rule, "key": f"{row.session}|{row.ticker}|{row.contract}",
                                "direction": row.direction, "reason": out["reason"], "sessions": out["sessions"],
                                "ret": None if mark is None else mark / row.entry_ask - 1.0})
    finally:
        chain.close()
    res = pd.DataFrame(records)
    res.to_csv(HERE / f"exit_scenarios_layer_d_{args.scope}_rows.csv", index=False)
    wide = res.pivot_table(index="key", columns="rule", values="ret", aggfunc="first")
    summary = {"scope": args.scope, "candidates": int(len(scope)), "rules": {}}
    for rule in RULES:
        rows = res[res.rule == rule]
        paired = wide[["baseline", rule]].dropna() if rule != "baseline" else None
        diff = (paired[rule] - paired["baseline"]) if paired is not None and len(paired) > 2 else None
        summary["rules"][rule] = {
            **tail(rows["ret"]),
            "mean_sessions_held": round(float(rows["sessions"].dropna().mean()), 2),
            "exit_reasons": rows["reason"].value_counts().to_dict(),
            "by_direction": {d: tail(g["ret"]) for d, g in rows.groupby("direction")},
            "paired_vs_baseline": None if diff is None else {
                "n": int(len(diff)), "mean_diff": round(float(diff.mean()), 4),
                "t": round(float(diff.mean() / diff.std() * math.sqrt(len(diff))), 2) if diff.std() > 0 else None},
        }
    (HERE / f"exit_scenarios_layer_d_{args.scope}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({r: {k: v for k, v in s.items() if k not in ("by_direction", "exit_reasons")}
                      for r, s in summary["rules"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
