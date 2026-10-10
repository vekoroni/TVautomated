"""Output-trust item 6 acceptance on run 20261008_220129: rows labelled IV_HISTORY_252D and the samples they actually
used. Read-only; JSON receipt beside."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RUN = "20261008_220129"
df = pd.read_csv(ROOT / "data/output/runs" / RUN / "options" / f"options_intelligence_{RUN}.csv", low_memory=False)
hist = df[df["ivp_source"] == "IV_HISTORY_252D"]
w = pd.to_numeric(hist["iv_rank_window_sessions"], errors="coerce")
full = json.loads((ROOT / "config/governed_constants_v1.json").read_text(encoding="utf-8"))["iv_history"]["full_window_samples"]
out = {"run": RUN, "rows": len(df), "labelled_IV_HISTORY_252D": len(hist),
       "samples": {"min": int(w.min()), "median": float(w.median()), "max": int(w.max())},
       "short_history_rows": int((w < full).sum()), "full_window_rows": int((w >= full).sum()),
       "other_sources": df.loc[df["ivp_source"] != "IV_HISTORY_252D", "ivp_source"].fillna("MISSING").value_counts().to_dict(),
       "smci": hist.loc[hist["ticker"] == "SMCI", ["iv_percentile", "iv_rank", "ivp_label", "iv_rank_window_sessions"]]
       .to_dict("records")}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(json.dumps(out, indent=1, default=str))
