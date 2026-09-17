"""Increment 1 (distribution) vs increment 2 (volatility-range exit-path) valuation on the SAME realised option marks (read-only).

Joins recorded evening option rows to C12 MARKED expression outcomes first, then values every joined row with:
  OLD  empirical_option_ev.py from the production tree (--old-root)
  NEW  empirical_option_ev.py from the WP1 tree (--new-root)
When a row has no recorded l3_forward_realised_vol (runs produced before the Layer 3 merge), the forecast is
supplied point-in-time: production `layer3_forward_variance.compute_forward_variance` (HAR-RV, regime '')
on price-store bars up to and including the prediction's evidence session. Forecast source is reported.
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd

MAIN = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
OUT = Path(__file__).resolve().parent / "empirical_option_ev_evaluation_v4_expression.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from empirical_option_ev_evaluation import candidate_from_row  # noqa: E402


def load(name, root):
    sys.path.insert(0, str(Path(root) / "scripts"))
    spec = importlib.util.spec_from_file_location(name, str(Path(root) / "empirical_option_ev.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summarise(frame, col):
    ok = frame.dropna(subset=[col, "return_on_premium"])
    if len(ok) < 30:
        return {"n": len(ok)}
    q = pd.qcut(ok[col].rank(method="first"), 5, labels=False)
    per_session = [g[col].rank().corr(g["return_on_premium"].rank()) for _, g in ok.groupby("evidence_session") if len(g) >= 10]
    return {
        "n": len(ok), "sessions": int(ok["evidence_session"].nunique()),
        "spearman": float(ok[col].rank().corr(ok["return_on_premium"].rank())),
        "spearman_by_session_median": float(np.nanmedian(per_session)) if per_session else None,
        "predicted_mean": float(ok[col].mean()), "realised_mean": float(ok["return_on_premium"].mean()),
        "mean_abs_error": float((ok[col] - ok["return_on_premium"]).abs().mean()),
        "quintiles": ok.assign(q=q).groupby("q").agg(predicted=(col, "mean"), realised=("return_on_premium", "mean"),
                                                        win=("return_on_premium", lambda s: float((s > 0).mean()))).round(3).to_dict("index"),
        "realised_if_predicted_positive": float(ok.loc[ok[col] > 0, "return_on_premium"].mean()) if (ok[col] > 0).any() else None,
        "n_predicted_positive": int((ok[col] > 0).sum()),
        "realised_if_predicted_non_positive": float(ok.loc[ok[col] <= 0, "return_on_premium"].mean()) if (ok[col] <= 0).any() else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-root", required=True)
    parser.add_argument("--new-root", required=True)
    args = parser.parse_args()
    logging.disable(logging.WARNING)
    old, new = load("emp_old", args.old_root), load("emp_new", args.new_root)
    calibration = json.loads((MAIN / "config" / "calibration" / "volatility_range_calibration_v1.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(MAIN))
    import layer3_forward_variance as l3   # production HAR-RV

    con = sqlite3.connect(f"file:{(MAIN / 'data/canonical/outcome_scoring.sqlite').as_posix()}?mode=ro", uri=True)
    outcomes = pd.read_sql_query(
        """SELECT s.run_id, p.ticker, p.contract_symbol, p.evidence_session, e.return_on_premium,
                  (SELECT o.r_multiple FROM latest_underlying_outcomes o WHERE o.prediction_id = p.prediction_id
                   AND o.state IN ('TARGET_FIRST','STOP_FIRST','AMBIGUOUS','TIMEOUT')) AS realised_share_r
           FROM expression_outcomes e JOIN prediction_records p USING (prediction_id)
           JOIN prediction_sightings s USING (prediction_id)
           WHERE e.expression_version = 'c12-expression-v1.1.0' AND e.state = 'MARKED'""", con)
    keys = set(zip(outcomes.run_id, outcomes.ticker, outcomes.contract_symbol))
    prices = sqlite3.connect(f"file:{(MAIN / 'data/canonical/historical_prices.sqlite').as_posix()}?mode=ro", uri=True)
    rows, cache = [], {}
    for path in sorted(glob.glob(str(MAIN / "data/output/runs/*/options/options_intelligence_*.csv"))):
        run = os.path.basename(path)[len("options_intelligence_"):-len(".csv")]
        if len(run) != 15 or not run[:8].isdigit():
            continue
        head = pd.read_csv(path, nrows=0).columns
        if "contract_occ_symbol" not in head or not any(c.startswith("layer2__outcomes__ret_pctl_") for c in head):
            continue
        frame = pd.read_csv(path, low_memory=False)
        for r in frame.to_dict("records"):
            key = (run, r.get("ticker"), r.get("contract_occ_symbol"))
            if key not in keys:
                continue
            cand = candidate_from_row(r)
            evidence = outcomes.loc[(outcomes.run_id == run) & (outcomes.ticker == key[1]) & (outcomes.contract_symbol == key[2]), "evidence_session"].iloc[0]
            source = "RECORDED_L3"
            if cand.get("forecast_vol") in (None, "") or (isinstance(cand.get("forecast_vol"), float) and np.isnan(cand["forecast_vol"])):
                ck = (key[1], evidence)
                if ck not in cache:
                    bars = pd.read_sql_query("SELECT trading_date, open, high, low, close FROM ohlcv_daily WHERE ticker = ? AND "
                                             "bar_status = 'COMPLETE' AND trading_date <= ? ORDER BY trading_date DESC LIMIT 252",
                                             prices, params=(key[1], evidence)).iloc[::-1].reset_index(drop=True)
                    res = l3.compute_forward_variance(key[1], bars, implied_vol=0.0, regime="") if len(bars) else None
                    cache[ck] = res.forward_realised_vol if res is not None and not res.error else None
                cand["forecast_vol"] = cache[ck]
                source = "POINT_IN_TIME_HAR_RV" if cache[ck] else "UNAVAILABLE"
            o = new.compute_empirical_option_ev(dict(cand))
            inputs = new.path_inputs_from_options_row(r)
            inputs.pop("forecast_source")
            if inputs["forecast_vol"] is None:
                inputs["forecast_vol"] = cand.get("forecast_vol")
            ck2 = (key[1], evidence, "spread")
            if ck2 not in cache:
                bars = pd.read_sql_query("SELECT high, low, close FROM ohlcv_daily WHERE ticker = ? AND bar_status = 'COMPLETE' "
                                         "AND trading_date <= ? ORDER BY trading_date DESC LIMIT ?", prices,
                                         params=(key[1], evidence, new.PATH_SETTINGS["share_spread_window_sessions"])).iloc[::-1]
                cache[ck2] = new.abdi_ranaldo_spread(bars.high, bars.low, bars.close)
            n = new.compute_path_expression_ev(**inputs, share_spread=cache[ck2], calibration=calibration,
                                               paths=new.PATH_SETTINGS["paths"], seed=new.PATH_SETTINGS["seed"])
            n = {"emp_quality_flag": n["emp_path_quality_flag"], "emp_expected_r": n["emp_path_r_cautious"],
                 "central": n["emp_path_r_central"], "upside": n["emp_path_r_upside"],
                 "p_stop": n["emp_path_p_stop_first_central"], "emp_vol_scale": None,
                 "share_r": n["emp_share_r_cautious"], "preference": n["emp_expression_preference"]}
            rows.append({"run_id": run, "ticker": key[1], "contract_symbol": key[2], "evidence_session": evidence,
                         "forecast_source": source, "old_flag": o["emp_quality_flag"], "new_flag": n["emp_quality_flag"],
                         "old_expected_r": o["emp_expected_r"], "new_expected_r": n["emp_expected_r"],
                         "central_r": n.get("central"), "upside_r": n.get("upside"), "p_stop": n.get("p_stop"),
                         "share_r": n.get("share_r"), "preference": n.get("preference"),
                         "vol_scale": n.get("emp_vol_scale")})
    df = pd.DataFrame(rows).drop_duplicates(subset=["run_id", "ticker", "contract_symbol"])
    df = df.merge(outcomes.drop_duplicates(subset=["run_id", "ticker", "contract_symbol"]), on=["run_id", "ticker", "contract_symbol", "evidence_session"])
    both = df[(df.old_flag == "OK") & (df.new_flag == "OK")]
    out = {"joined": len(df), "forecast_source": df.forecast_source.value_counts().to_dict(),
           "old_flags": df.old_flag.value_counts().to_dict(), "new_flags": df.new_flag.value_counts().to_dict(),
           "same_rows_both_ok": len(both), "vol_scale_median": float(both.vol_scale.median()) if len(both) else None,
           "INCREMENT_1_DISTRIBUTION": summarise(both, "old_expected_r"),
           "INCREMENT_2_PATH_CAUTIOUS": summarise(both, "new_expected_r"),
           "INCREMENT_2_PATH_CENTRAL": summarise(both.dropna(subset=["central_r"]), "central_r"),
           "mean_p_stop_first_central": float(both["p_stop"].mean()) if len(both) else None}
    sh = both.dropna(subset=["share_r", "realised_share_r"])
    out["SHARES"] = {"n": len(sh), "spearman_predicted_vs_realised_R": float(sh["share_r"].rank().corr(sh["realised_share_r"].rank())) if len(sh) > 30 else None,
                     "predicted_mean_R": float(sh["share_r"].mean()) if len(sh) else None,
                     "realised_mean_R": float(sh["realised_share_r"].mean()) if len(sh) else None}
    pref = both.dropna(subset=["realised_share_r"])
    out["PREFERENCE"] = {
        str(k): {"n": len(g), "realised_option_return_on_premium_mean": float(g["return_on_premium"].mean()),
                 "realised_share_R_mean": float(g["realised_share_r"].mean()),
                 "share_both_lost": float(((g["return_on_premium"] <= 0) & (g["realised_share_r"] <= 0)).mean()),
                 "share_option_beat_shares": float((g["return_on_premium"] > g["realised_share_r"]).mean())}
        for k, g in pref.groupby("preference")}
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
