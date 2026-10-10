"""Phase 5.3 acceptance on real data (offline replay, read-only; never touches live data/ or the network).

Two questions:
1. GO-set change on the last Evening run (20261006_060401, evidence session 2026-10-05): the run's state-category
   trigger_go_eligible vs the thesis's own event readiness replayed through Discovery on the same bars.
2. Does event readiness separate outcomes? On past Fridays, for directed (adopted) theses: forward close-to-close
   move on the thesis side over 5 and 10 sessions, READY_FOR_HUMAN_REVIEW vs WAIT_TRIGGER. Descriptive only.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "Enhancements" / "direction_evidence"))
import avshunter_discovery_ULTIMATE as disc  # noqa: E402
from WyckoffEngine_3101_v2 import WyckoffEngine_3101_v2 as W  # noqa: E402
from dir002_replay import read_bars  # noqa: E402

RUN = "20261006_060401"
EVIDENCE = "2026-10-05"
PAST_FRIDAYS = ("2026-07-10", "2026-07-31", "2026-08-21", "2026-09-11")
N_RUN, N_PAST = int(sys.argv[1]) if len(sys.argv) > 1 else 300, int(sys.argv[2]) if len(sys.argv) > 2 else 150
cfg, wy = disc.UltimateConfig(), W()


def scan(ticker, bars, asof):
    b = bars[bars.date <= asof].reset_index(drop=True)
    if len(b) < 60:
        return None
    s, _ = disc._scan_with_lifecycle(ticker, b, cfg, wy)
    return s


ex = pd.read_csv(ROOT / f"data/output/runs/{RUN}/execution/execution_v3_5_{RUN}.csv", low_memory=False,
                 usecols=lambda c: c in {"ticker", "trigger_go_eligible", "trigger_primary"})
ex["old_go"] = ex.trigger_go_eligible.astype(str).str.upper().isin({"TRUE", "1", "YES"})
rng = np.random.default_rng(53)
pick = list(rng.choice(ex.ticker.dropna().unique(), min(N_RUN, ex.ticker.nunique()), replace=False))
rows, bars_cache = [], {}
for t in pick:
    try:
        bars_cache[t] = read_bars(t)
        s = scan(t, bars_cache[t], EVIDENCE)
    except Exception as e:  # replay only: record, never hide
        rows.append({"ticker": t, "readiness": f"REPLAY_ERROR:{type(e).__name__}"})
        continue
    rows.append({"ticker": t, "readiness": (s or {}).get("thesis__readiness") or "NO_SIGNAL_ROW",
                 "side": (s or {}).get("thesis__side")})
new = pd.DataFrame(rows).merge(ex[["ticker", "old_go", "trigger_primary"]].drop_duplicates("ticker"), on="ticker")
q1 = {"tickers": len(new), "old_go_true": int(new.old_go.sum()),
      "new_ready": int((new.readiness == "READY_FOR_HUMAN_REVIEW").sum()),
      "readiness_mix": new.readiness.value_counts().to_dict(),
      "old_vs_new": {str(k): v for k, v in pd.crosstab(new.old_go, new.readiness == "READY_FOR_HUMAN_REVIEW")
                     .rename(columns=str).to_dict(orient="index").items()},
      "old_go_primary_mix": new.loc[new.old_go, "trigger_primary"].value_counts().to_dict()}

out = []
for t in pick[:N_PAST]:
    bars = bars_cache.get(t)
    if bars is None:
        continue
    for d in PAST_FRIDAYS:
        try:
            s = scan(t, bars, d)
        except Exception:
            continue
        if not s or s.get("thesis__side") not in {"BULL", "BEAR"}:
            continue
        fwd = bars[bars.date > d].reset_index(drop=True)
        c0 = float(bars[bars.date <= d].close.iloc[-1])
        sign = 1.0 if s["thesis__side"] == "BULL" else -1.0
        rec = {"ticker": t, "date": d, "readiness": s.get("thesis__readiness"), "side": s["thesis__side"]}
        for h in (5, 10):
            rec[f"ret{h}_side_pct"] = sign * (float(fwd.close.iloc[h - 1]) / c0 - 1) * 100 if len(fwd) >= h else None
        out.append(rec)
p = pd.DataFrame(out)
q2 = {}
if len(p):
    for r, g in p.groupby("readiness"):
        q2[r] = {"n": len(g), **{f"{c}_{k}": round(float(f(g[c].dropna())), 2) if g[c].notna().any() else None
                                 for c in ("ret5_side_pct", "ret10_side_pct")
                                 for k, f in (("mean", np.mean), ("median", np.median))},
                 "hit10_pct": round(float((g.ret10_side_pct.dropna() > 0).mean() * 100), 1) if g.ret10_side_pct.notna().any() else None}
res = {"q1_go_set_change_run_" + RUN: q1, "q2_forward_by_readiness_past_fridays": q2,
       "note": "Descriptive replay; survivorship as per read_bars source; not a significance test."}
(Path(__file__).parent / "p53_go_set_change.json").write_text(json.dumps(res, indent=2, default=str))
print(json.dumps(res, indent=2, default=str))
