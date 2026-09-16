"""D5b — EXECUTABLE_NOW truth on both runs at options-CSV grain (pre-morning) and morning grain:
missing provider timestamps, age vs run evidence cutoff, run_condition / execution_mode / refresh fields present."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d5b_quote_truth.json"


def cutoff(run):
    m = json.load(open(run_dir(run) / "run_meta.json", encoding="utf-8"))
    dp = m.get("dynamic_plan") or {}
    return {"evidence_cutoff_utc": dp.get("evidence_cutoff_utc"), "pipeline_mode": m.get("pipeline_mode"), "run_condition": m.get("run_condition"),
            "dynamic_plan_run_condition": dp.get("run_condition"), "git": m.get("git_describe")}


def grain(run, rel):
    p = art(run, rel)
    if not p.exists():
        return {"missing": rel}
    hdr = header(p)
    ts = [c for c in hdr if re.search(r"quote.*timestamp|timestamp.*quote|provider_timestamp|refresh_timestamp|quote_as_of", c)]
    refresh = [c for c in hdr if re.search(r"refresh|execution_mode|run_condition|window_state", c)]
    want = [c for c in ("ticker", "governed_direction", "liquidity_state", "executable_now", "current_quote_executable", "contract_bid", "contract_ask",
                        "live_contract_bid", "live_contract_ask", "morning_execution_permission") if c in hdr]
    df = read_csv(p, usecols=list(dict.fromkeys(want + ts + refresh)))
    df = df.drop_duplicates("ticker", keep="first")
    b = direction_bucket(df["governed_direction"]) if "governed_direction" in df else pd.Series("OTHER", index=df.index)
    ex = df["liquidity_state"].astype(str).eq("EXECUTABLE_NOW") if "liquidity_state" in df else pd.Series(False, index=df.index)
    if "executable_now" in df:
        ex_flag = df["executable_now"].astype(str).str.upper().eq("TRUE")
    else:
        ex_flag = pd.Series(False, index=df.index)
    res = {"rows": len(df), "ts_cols": ts, "refresh_cols": refresh,
           "liquidity_EXECUTABLE_NOW": {"ALL": int(ex.sum()), **{k: int((ex & (b == k)).sum()) for k in ("CALL", "PUT", "OTHER")}},
           "executable_now_true": {"ALL": int(ex_flag.sum()), **{k: int((ex_flag & (b == k)).sum()) for k in ("CALL", "PUT", "OTHER")}}}
    res["refresh_values"] = {c: dict(list(vc(df[c]).items())[:8]) for c in refresh}
    co = pd.Timestamp(cutoff(run)["evidence_cutoff_utc"])
    sel = ex | ex_flag
    for c in ts:
        t = pd.to_datetime(df.loc[sel, c], errors="coerce", utc=True)
        age = (co - t).dt.total_seconds() / 60
        res[f"ts::{c}"] = {"exec_rows": int(sel.sum()), "null": int(t.isna().sum()),
                           "age_min_vs_cutoff": None if t.isna().all() else {"min": float(age.min()), "median": float(age.median()), "max": float(age.max())},
                           "after_cutoff": int((age < 0).sum()), "older_than_15m": int((age > 15).sum()),
                           "session_dates": dict(list(vc(t.dt.strftime("%Y-%m-%d")).items())[:6])}
    return res


if __name__ == "__main__":
    out = {}
    for run in (PRIMARY, COMPARISON):
        out[run] = {"meta": cutoff(run)}
        for rel in ("options/options_intelligence_<run>.csv", "trades/execution_gated_<run>.csv", "intelligence_lab/final_opportunity_book_<run>.csv",
                    "morning_validation/morning_validated_trades_<run>.csv"):
            out[run][rel] = grain(run, rel)
    dump(out, OUT)
    print(json.dumps(out, indent=1, default=str)[:9000])
