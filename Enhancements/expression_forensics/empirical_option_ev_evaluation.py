"""Acceptance-first evaluation of empirical_option_ev.py against realised option outcomes (read-only).

For every recorded evening options output (`data/output/runs/<run>/options/options_intelligence_<run>.csv`) that
carries the actuarial return percentiles, compute `compute_empirical_option_ev` for each row with a selected
contract (production code, imported from --root), then join to the C12 expression outcomes
(`data/canonical/outcome_scoring.sqlite`, version c12-expression-v1.1.0, MARKED) by run, ticker and contract
symbol, and measure whether the predicted expected return on premium orders the realised return.

  venv\\Scripts\\python.exe empirical_option_ev_evaluation.py --root C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd

MAIN = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
OUT = Path(__file__).resolve().parent / "empirical_option_ev_evaluation.json"


def candidate_from_row(r: dict) -> dict:
    c = {}
    for k, v in r.items():
        if k.startswith("layer2__outcomes__"):
            c[k[len("layer2__outcomes__"):]] = v
    for src, dst in (("contract_bid", "bid"), ("contract_ask", "ask"), ("contract_iv", "live_iv"),
                     ("stock_price", "live_spot"), ("underlying_price", "live_spot"), ("entry_spot", "live_spot"), ("strike", "strike"), ("contract_dte", "dte"), ("dte", "dte"),
                     ("final_direction", "direction"), ("layer2__recommended_hold_days", "hold_days"),
                     ("layer2__preferred_horizon", "preferred_horizon"), ("layer2__n_obs_5d", "n_obs_5d"),
                     ("layer2__n_obs_10d", "n_obs_10d"), ("layer2__n_obs_20d", "n_obs_20d"),
                     ("l3_forward_realised_vol", "forecast_vol")):
        if src in r and r[src] is not None and not (isinstance(r[src], float) and np.isnan(r[src])) and dst not in c:
            c[dst] = r[src]
    c.setdefault("state_match_method", r.get("layer2__state_match_method") or r.get("layer2__outcomes__state_match_method"))
    return c


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    sys.path.insert(0, args.root)
    logging.disable(logging.WARNING)
    from empirical_option_ev import compute_empirical_option_ev   # noqa: E402

    con = sqlite3.connect(f"file:{(MAIN / 'data/canonical/outcome_scoring.sqlite').as_posix()}?mode=ro", uri=True)
    outcomes = pd.read_sql_query(
        """SELECT s.run_id, p.ticker, p.contract_symbol, p.evidence_session, e.return_on_premium, e.underlying_state,
                  e.exit_reason, e.entry_source
           FROM expression_outcomes e JOIN prediction_records p USING (prediction_id)
           JOIN prediction_sightings s USING (prediction_id)
           WHERE e.expression_version = 'c12-expression-v1.1.0' AND e.state = 'MARKED'""", con)
    rows, flags = [], {}
    for path in sorted(glob.glob(str(MAIN / "data/output/runs/*/options/options_intelligence_*.csv"))):
        name = os.path.basename(path)
        run = name[len("options_intelligence_"):-len(".csv")]
        if not run[:8].isdigit() or "_" not in run or len(run) != 15:
            continue
        head = pd.read_csv(path, nrows=0).columns
        if not any(c.startswith("layer2__outcomes__ret_pctl_") for c in head):
            continue
        frame = pd.read_csv(path, low_memory=False)
        sym_col = "contract_occ_symbol" if "contract_occ_symbol" in frame.columns else None
        for r in frame.to_dict("records"):
            if not sym_col or not isinstance(r.get(sym_col), str):
                continue
            result = compute_empirical_option_ev(candidate_from_row(r))
            flags[result["emp_quality_flag"]] = flags.get(result["emp_quality_flag"], 0) + 1
            rows.append({"run_id": run, "ticker": r["ticker"], "contract_symbol": r[sym_col], **result})
    pred = pd.DataFrame(rows)
    joined = pred.merge(outcomes, on=["run_id", "ticker", "contract_symbol"], how="inner").drop_duplicates(
        subset=["run_id", "ticker", "contract_symbol"])
    ok = joined[joined["emp_quality_flag"] == "OK"].dropna(subset=["emp_expected_r", "return_on_premium"])
    out = {"runs_with_percentiles": int(pred["run_id"].nunique()) if len(pred) else 0, "rows_scored_by_module": len(pred),
           "quality_flags": flags, "joined_to_realised": len(joined), "ok_joined": len(ok)}
    if len(ok) >= 30:
        ok = ok.copy()
        out["spearman_predicted_vs_realised"] = float(ok["emp_expected_r"].rank().corr(ok["return_on_premium"].rank()))
        by_session = [g["emp_expected_r"].rank().corr(g["return_on_premium"].rank())
                      for _, g in ok.groupby("evidence_session") if len(g) >= 10]
        out["spearman_by_session_median"] = float(np.nanmedian(by_session)) if by_session else None
        out["sessions_with_10plus"] = len(by_session)
        ok["decile"] = pd.qcut(ok["emp_expected_r"].rank(method="first"), 5, labels=False)
        out["realised_by_predicted_quintile"] = ok.groupby("decile").agg(
            n=("return_on_premium", "size"), predicted_mean=("emp_expected_r", "mean"),
            realised_mean=("return_on_premium", "mean"), realised_median=("return_on_premium", "median"),
            win_rate=("return_on_premium", lambda s: float((s > 0).mean()))).round(3).to_dict("index")
        out["predicted_mean"] = float(ok["emp_expected_r"].mean())
        out["realised_mean"] = float(ok["return_on_premium"].mean())
        out["predicted_positive_share"] = float((ok["emp_expected_r"] > 0).mean())
        pos = ok[ok["emp_expected_r"] > 0]
        neg = ok[ok["emp_expected_r"] <= 0]
        out["realised_when_predicted_positive"] = {"n": len(pos), "mean": float(pos["return_on_premium"].mean()) if len(pos) else None}
        out["realised_when_predicted_non_positive"] = {"n": len(neg), "mean": float(neg["return_on_premium"].mean()) if len(neg) else None}
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
