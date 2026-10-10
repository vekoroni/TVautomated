"""Phase 6 study S (short holds): implements PHASE6_SHORT_HOLD_PREREG_20261009.md; written before any result was read.

Reuses ph6_exits_cheapvol (model, data, statistics). Read-only. Output: ph6b_results.json, PH6B_RESULTS.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ph6_exits_cheapvol as ph6  # noqa: E402
from ph6_exits_cheapvol import bs, implied_vol, read_bars, boot, describe, halves, holm  # noqa: E402

HOLDS = (1, 2, 3, 5)


def per_trade(g: pd.DataFrame, bars: pd.DataFrame) -> list[dict]:
    b = bars.set_index("date")
    out = []
    for r in g.itertuples(index=False):
        rec = {"row_id": r.row_id}
        call = r.side == "BULL"
        exp = pd.Timestamp(r.expiry)
        mid0 = 0.5 * (r.entry_bid + r.entry_ask)
        iv = implied_vol(mid0, r.entry_close, r.strike, max((exp - pd.Timestamp(r.entry_date)).days, 1) / 365.0, call)
        path = b[(b.index > r.entry_date) & (b.index <= r.exit_date)]
        if iv is None or path.empty or not (r.entry_ask > 0):
            rec["s_status"] = "NO_MODEL"
            out.append(rec)
            continue
        half = 0.5 * (float(r.spread_pct) if pd.notna(r.spread_pct) else 0.0)
        T = np.array([max((exp - pd.Timestamp(d)).days, 0) / 365.0 for d in path.index])
        v = bs(path["close"].to_numpy(float), r.strike, T, iv, call) * (1 - half)
        rec["s_status"] = "OK"
        rec["ret_model_X1"] = float(v[-1] / r.entry_ask - 1.0)
        for h in HOLDS:
            if len(v) >= h:
                rec[f"ret_S{h}"] = float(v[h - 1] / r.entry_ask - 1.0)
                rec[f"S{h}_exit"] = "HOLD_END"
            else:                                   # X1 exited earlier (invalidation): the X1 exit stands
                rec[f"ret_S{h}"] = float(v[-1] / r.entry_ask - 1.0)
                rec[f"S{h}_exit"] = "X1_EARLIER"
        out.append(rec)
    return out


def main():
    base = pd.read_parquet(HERE / "ph6_trades.parquet")     # study V/E output: same trades, vol_group, period
    rows = []
    for i, (tk, g) in enumerate(base.groupby("ticker")):
        try:
            bars = read_bars(tk).sort_values("date").reset_index(drop=True)
        except Exception:
            continue
        rows.extend(per_trade(g, bars))
        if i % 300 == 0:
            print("tickers", i, flush=True)
    s = pd.DataFrame(rows)
    t = base.merge(s, on="row_id", how="left", validate="one_to_one")
    assert len(t) == len(base), "row count changed in merge"
    fridays = sorted(t.entry_date.unique())
    idx = {d: i for i, d in enumerate(fridays)}
    blk = lambda df: np.array([idx[d] // 4 for d in df.entry_date])  # noqa: E731
    test = t[(t.period == "TEST") & (t.s_status == "OK")]
    groups = {"LEAN_ATM": test[(test.kind == "LEAN") & (test.strike_rule == "ATM")],
              "LEAN_D35": test[(test.kind == "LEAN") & (test.strike_rule == "D35")],
              "PLACEBO_ATM": test[test.kind == "PLACEBO"]}
    a = groups["LEAN_ATM"].copy()
    fam = {}
    for h in HOLDS:
        a[f"d{h}"] = a[f"ret_S{h}"] - a["ret_model_X1"]
        d = a.dropna(subset=[f"d{h}"])
        b = boot(d[f"d{h}"].to_numpy(float), blk(d))
        hv = halves(d.rename(columns={f"d{h}": "_v"}), col="_v")
        fam[f"S{h}"] = {**b, "n": len(d), "halves": hv,
                        "same_sign_halves": bool(all(x > 0 for x in hv) or all(x < 0 for x in hv))}
    hp = holm({k: v.get("p_one_sided", 1.0) for k, v in fam.items()})
    for k, v in fam.items():
        v["p_holm"] = hp[k]
        v["pass"] = bool(v.get("status") == "OK" and v.get("estimate", 0) > 0 and hp[k] < 0.05 and v["same_sign_halves"])
    desc = {}
    for name, df in groups.items():
        desc[name] = {"X1_actual": describe(df.ret), "X1_model": describe(df.ret_model_X1),
                      **{f"S{h}": describe(df[f"ret_S{h}"]) for h in HOLDS},
                      **{f"S{h}_minus_X1_actual_mean": float((df[f"ret_S{h}"] - df.ret).mean()) for h in HOLDS}}
    best = max(HOLDS, key=lambda h: fam[f"S{h}"].get("estimate", float("-inf")))
    combo = {g: describe(groups["LEAN_ATM"][groups["LEAN_ATM"].vol_group == g][f"ret_S{best}"])
             for g in ("CHEAP", "MID", "RICH")}
    res = {"family_S": fam, "describe_test": desc, "best_hold": best, "best_hold_by_vol_group": combo,
           "coverage": {"trades": len(t), "test_ok": len(test), "status": t.s_status.fillna("NOT_RUN").value_counts().to_dict()}}
    (HERE / "ph6b_results.json").write_text(json.dumps(res, indent=2, default=str))
    lines = ["# Phase 6 study S (short holds): numbers only", "", "## Family S (setup trades, ATM, test, vs modelled X1)", "",
             "| Test | n | Estimate | 95% CI | p | Holm p | Halves | Pass |", "|---|---|---|---|---|---|---|---|"]
    for k, v in fam.items():
        ci = v.get("ci95") or [float("nan"), float("nan")]
        lines.append(f"| {k} | {v['n']} | {v.get('estimate', float('nan')):+.3f} | [{ci[0]:+.3f}, {ci[1]:+.3f}] | "
                     f"{v.get('p_one_sided', float('nan')):.3f} | {v['p_holm']:.3f} | {[round(x, 3) for x in v['halves']]} | "
                     f"{'yes' if v['pass'] else 'no'} |")
    (HERE / "PH6B_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"family_S": fam, "best": best}, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()
