"""Phase 4 / RC03-RC19 parity check (read-only): the live Vanguard matching state on run 20261006_060401 versus
v7's own state function (actuarial_core_v7.calculate_core_state) on the same ticker and session.
A dimension used to match history must mean the same thing live as when the database was built.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "Enhancements" / "direction_evidence"))
from vanguard.core.actuarial_core_v7 import calculate_core_state, compute_technicals, normalise_daily_ohlcv  # noqa
from dir002_replay import read_bars  # noqa
DIMS = ["vol_regime", "trend_direction", "structure_quality", "phase_v2", "momentum_bucket", "location_bucket",
        "trend_maturity"]
live = pd.read_csv(ROOT / "data/output/runs/20261006_060401/vanguard/vanguard_signals.csv",
                   usecols=["ticker"] + [f"layer2__{d}" for d in DIMS], low_memory=False)
sample = live.sample(200, random_state=4)
rows = []
for r in sample.itertuples():
    b = read_bars(r.ticker); b = b[b.date <= "2026-10-05"].reset_index(drop=True)
    if len(b) < 260:
        continue
    tech = compute_technicals(normalise_daily_ohlcv(b))
    st = calculate_core_state(tech, len(tech) - 1)
    if st is None:
        continue
    rows.append({"ticker": r.ticker, **{f"live_{d}": getattr(r, f"layer2__{d}") for d in DIMS},
                 **{f"v7_{d}": st[d] for d in DIMS}})
df = pd.DataFrame(rows)
out = {"compared": len(df)}
for d in DIMS:
    out[d] = {"agree": f"{int((df[f'live_{d}'].astype(str) == df[f'v7_{d}'].astype(str)).sum())}/{len(df)}",
              "live_values": df[f"live_{d}"].astype(str).value_counts().head(5).to_dict(),
              "v7_values": df[f"v7_{d}"].astype(str).value_counts().head(5).to_dict()}
(Path(__file__).parent / "p4_state_parity.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=1))
