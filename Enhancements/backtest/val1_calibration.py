"""S-VAL-1 (scenario register, ACK 20 Sep 2026): calibration by bucket, predicted vs realised return.

Definition (frozen, SCENARIO_REGISTER_20260919.md line 326): "calibration by bucket: predicted vs realised
return, per decile of central and cautious value. H+, N -> trust in the cost model."

Population: H, every row with a market-verified closed option outcome (option_state == 'CLOSED'), from
signal_ticket_backtest_rows.csv - not restricted to ticket == True. Only 91/8950 rows ever became a ticket
(8397 were rejected on CAUTIOUS_RETURN_NOT_POSITIVE alone, per M13), so a ticket-only population would be
19 closed rows - too thin and too selection-biased to test calibration. The frozen text asks whether
predicted value tracks realised return; that question is best answered across the full predicted-value
range, ticketed or not, since option_return is computed the same way (real subsequent chain snapshots)
regardless of whether a ticket was cut. `central`/`cautious` are the path-model's own stored predictions
(compute_path_option_ev's emp_path_r_central / emp_path_r_cautious, written at scoring time - not
reconstructed here). This is the H slice of the H+, N requirement; N will extend this once tonight's
run's candidates mature and close.

D5 relevance: value selection is still SHADOW pending this check (open decision, 19 Sep 2026).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO = Path(__file__).resolve().parents[2]
ROWS = REPO / "Enhancements" / "backtest" / "signal_ticket_backtest_rows.csv"
OUT = Path(__file__).resolve().parent / "val1_calibration_H.json"

N_BUCKETS = 5


def decile_table(df: pd.DataFrame, predictor: str) -> list[dict]:
    d = df[[predictor, "option_return"]].dropna()
    d = d[np.isfinite(d[predictor]) & np.isfinite(d["option_return"])]
    if len(d) < N_BUCKETS * 4:
        return []
    d["bucket"] = pd.qcut(d[predictor], N_BUCKETS, labels=False, duplicates="drop")
    rows = []
    for b, g in d.groupby("bucket"):
        rows.append({
            "bucket": int(b),
            "n": int(len(g)),
            f"{predictor}_median": round(float(g[predictor].median()), 4),
            "option_return_mean": round(float(g["option_return"].mean()), 4),
            "option_return_median": round(float(g["option_return"].median()), 4),
            "win_rate": round(float((g["option_return"] > 0).mean()), 4),
        })
    rows.sort(key=lambda r: r["bucket"])
    rho, p = spearmanr(d[predictor], d["option_return"])
    monotonic = all(rows[i]["option_return_mean"] <= rows[i + 1]["option_return_mean"] + 1e-9
                     for i in range(len(rows) - 1))
    return {"buckets": rows, "spearman_rho": round(float(rho), 4), "spearman_p": round(float(p), 4),
            "monotonic_increasing": bool(monotonic)}


def main() -> int:
    rows = pd.read_csv(ROWS, low_memory=False)
    closed = rows[rows.option_state == "CLOSED"].copy()
    print(f"H rows total: {len(rows)} | ticketed: {int((rows['ticket'] == True).sum())} | "  # noqa: E712
          f"closed (this population): {len(closed)} (of which ticketed: {int((closed['ticket'] == True).sum())})")  # noqa: E712

    result = {
        "scenario": "S-VAL-1",
        "population": "H (signal_ticket_backtest_rows.csv), option_state=='CLOSED' (ticketed and non-ticketed)",
        "n_rows": int(len(closed)),
        "n_ticketed": int((closed["ticket"] == True).sum()),  # noqa: E712
        "central": decile_table(closed, "central"),
        "cautious": decile_table(closed, "cautious"),
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(f"Written: {OUT}")

    for key in ("central", "cautious"):
        tbl = result[key]
        if not tbl:
            print(f"{key}: insufficient rows for decile analysis")
            continue
        print(f"\n{key}: spearman_rho={tbl['spearman_rho']} p={tbl['spearman_p']} monotonic={tbl['monotonic_increasing']}")
        for b in tbl["buckets"]:
            print(f"  bucket {b['bucket']}  n={b['n']:4d}  pred_median={b[f'{key}_median']:+.4f}  "
                  f"realised_mean={b['option_return_mean']:+.4f}  realised_median={b['option_return_median']:+.4f}  "
                  f"win_rate={b['win_rate']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
