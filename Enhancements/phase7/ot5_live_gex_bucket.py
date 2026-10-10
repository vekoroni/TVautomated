"""Output-trust item 5 acceptance on run 20261008_220129: McMillan's ticker GEX bucket before (SPY fields allowed) and
after (ticker fields only). Read-only; JSON receipt beside."""
import collections
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mcmillan_advisory_layer import _gex_bucket  # noqa: E402  (the fixed function)

RUN = "20261008_220129"
df = pd.read_csv(ROOT / "data/output/runs" / RUN / "execution" / f"execution_v3_5_{RUN}.csv", low_memory=False, dtype=str)


def old_bucket(row):
    """The pre-fix rule, reproduced for comparison: SPY dealer_gamma_state / gex_regime_score as fallbacks."""
    label = next((str(row.get(k)).upper() for k in ("eil_gex_regime", "dealer_gamma_state", "gex_regime", "gamma_regime",
                                                    "gamma_velocity_label") if str(row.get(k) or "").strip() not in ("", "nan")), "")
    if any(t in label for t in ("NEGATIVE", "AMPLIFY", "SHORT_GAMMA", "RISK")):
        return "AMPLIFYING_GEX"
    if any(t in label for t in ("POSITIVE", "PIN", "DAMPEN", "LONG_GAMMA")):
        return "PINNING_GEX"
    for k in ("gex_regime_score", "eil_gex_score"):
        try:
            s = float(row.get(k))
        except (TypeError, ValueError):
            continue
        if s == s:
            s = s / 100.0 if s > 1 else s
            return "AMPLIFYING_GEX" if s <= 0.40 else "PINNING_GEX" if s >= 0.60 else "UNKNOWN_GEX"
    return "UNKNOWN_GEX"


rows = [r for _, r in df.iterrows()]
moves = collections.Counter(f"{old_bucket(r)} -> {_gex_bucket(r)}" for r in rows)
out = {"run": RUN, "rows": len(rows), "spy_dealer_gamma_state": sorted(df["dealer_gamma_state"].dropna().unique().tolist()),
       "spy_gex_regime_score": sorted(df["gex_regime_score"].dropna().unique().tolist()),
       "bucket_transitions": dict(moves.most_common())}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=1))
