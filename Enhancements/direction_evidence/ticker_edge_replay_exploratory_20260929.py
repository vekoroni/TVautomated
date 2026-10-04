"""EXPLORATORY follow-up to the pre-registered replay study (not part of the pre-registered test).

For the few segments whose edge over the market was positive in all three periods, check whether the option result
is an edge or market beta / survivorship: option EV of the segment MINUS the option EV of every signal on the same
side in the same session ("option excess"), with block-bootstrap intervals; by calendar year; and without rows whose
forward window contains an extreme overnight gap. Hold fixed at the one chosen on discovery.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(sys.argv[1])
z = np.load(D / "per_signal_arrays.npz", allow_pickle=True)
masks = pd.read_parquet(D / "segment_masks.parquet")
res = pd.read_csv(D / "segment_results.csv").set_index("segment")
lift, opt, is_sig, period, block, sess, extreme, direction = (z[k] for k in (
    "lift", "opt", "is_signal", "period", "block", "session", "extreme", "direction"))
year = np.array([s[:4] for s in sess])
rng = np.random.default_rng(4)

# same-side, same-session mean option return of all signals (the "market" for an option buyer on that side)
side_mean = {}
for h in range(opt.shape[1]):
    df = pd.DataFrame({"s": sess, "d": direction, "o": opt[:, h]})[is_sig]
    side_mean[h] = df.groupby(["s", "d"])["o"].mean()
key = pd.MultiIndex.from_arrays([sess, direction])


def excess(mask, h):
    base = side_mean[h - 1].reindex(key).to_numpy()
    v = opt[:, h - 1] - base
    m = mask & ~np.isnan(v)
    if m.sum() < 50:
        return np.nan, np.nan, np.nan, int(m.sum())
    uniq, inv = np.unique(block[m], return_inverse=True)
    sums, cnt = np.bincount(inv, weights=v[m]), np.bincount(inv)
    pk = rng.integers(0, len(uniq), size=(1000, len(uniq)))
    bt = sums[pk].sum(1) / cnt[pk].sum(1)
    return float(sums.sum() / cnt.sum()), *np.percentile(bt, [5, 95]).tolist(), int(m.sum())


CANDIDATES = [s for s in res.index if all(res.loc[s, f"{p}_lift"] > 0 for p in ("disc", "val", "test"))]
print(f"segments positive in all three periods: {len(CANDIDATES)} of {len(res)}\n")
rows = []
for s in CANDIDATES:
    h = int(res.loc[s, "hold"])
    m = masks[s].to_numpy()
    rec = {"segment": s, "hold": h}
    for per in ("DISC", "VAL", "TEST"):
        e, lo, hi, n = excess(m & (period == per), h)
        rec.update({f"{per}_opt_excess": e, f"{per}_lo": lo, f"{per}_hi": hi, f"{per}_n": n})
    e, lo, hi, n = excess(m & ~extreme, h)
    rec.update({"all_no_gap_excess": e, "all_no_gap_lo": lo})
    for y in ("2022", "2023", "2024", "2025", "2026"):
        rec[f"y{y}"] = excess(m & (year == y), h)[0]
    rows.append(rec)
out = pd.DataFrame(rows).sort_values("VAL_opt_excess", ascending=False)
pd.set_option("display.width", 260)
print(out.round(4).to_string(index=False))
out.to_csv(D / "exploratory_option_excess.csv", index=False)
