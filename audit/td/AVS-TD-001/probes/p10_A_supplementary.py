"""p10_A_supplementary.py -- Track A supplementary splits on run 20260911_115904 (read-only).
(1) EXECUTABLE_NOW-like rows (liquidity_state, executable_now column if present) by direction and by quote_as_of date;
(2) morning_execution_mode / morning_quote_evidence_state column presence in morning artefacts;
(3) second run_plans row (16:59Z) session_state for 20260911_115904;
(4) hour histogram of quote_as_of and selected_quote_timestamp_utc by direction;
(5) intelligent_orchestrator.py caller of _integrate_provider_completeness_into_run_meta (exception handling).
Output: probes/p10_A_supplementary_out.json
"""
import json, os, re, sqlite3
from datetime import datetime, timezone
import pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
RUN = "20260911_115904"
BASE = os.path.join(ROOT, "data", "output", "runs", RUN)
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_supplementary_out.json")


def pts(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).strip().replace("Z", "+00:00")
    if not s or s.lower() in ("nan", "none", "nat"):
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def dirs_of(df):
    d = df["final_direction"].astype(str).str.upper().str.strip() if "final_direction" in df.columns else df["governed_direction"].astype(str).str.upper().str.strip()
    return d.where(d.isin(["CALL", "PUT"]), "OTHER")


def main():
    out = {}
    for label, path in [("morning_validated_trades", os.path.join(BASE, "morning_validation", f"morning_validated_trades_{RUN}.csv")),
                        ("final_opportunity_book", os.path.join(BASE, "intelligence_lab", f"final_opportunity_book_{RUN}.csv"))]:
        df = pd.read_csv(path, low_memory=False)
        dirs = dirs_of(df)
        qdate = pd.Series([pts(v) for v in df["quote_as_of"]], index=df.index, dtype=object).map(lambda v: v.strftime("%Y-%m-%d") if v else "MISSING")
        rec = {"rows": int(len(df)), "governed_direction_present": "governed_direction" in df.columns,
               "governed_direction_counts": ({k: int(v) for k, v in df["governed_direction"].astype(str).value_counts().items()} if "governed_direction" in df.columns else None),
               "mode_cols": [c for c in df.columns if re.search(r"morning_execution_mode|morning_quote_evidence_state|refresh_window|execution_state$", c)]}
        for c in rec["mode_cols"]:
            rec[c + "_counts"] = {k: int(v) for k, v in df[c].astype(str).value_counts().head(10).items()}
        for col, val in [("liquidity_state", "EXECUTABLE_NOW"), ("executable_now", None), ("execution_state", "EXECUTABLE_NOW")]:
            if col not in df.columns:
                rec[col] = "COLUMN_ABSENT"
                continue
            s = df[col].astype(str).str.upper()
            m = (s == val) if val else s.isin(["TRUE", "1", "YES", "EXECUTABLE_NOW"])
            rec[col] = {"value_counts": {k: int(v) for k, v in df[col].astype(str).value_counts().head(12).items()},
                        "hits_by_direction": {k: int((m & (dirs == k)).sum()) for k in ["CALL", "PUT", "OTHER"]},
                        "hits_by_quote_as_of_date": {k: int(v) for k, v in qdate[m].value_counts().items()},
                        "hits_by_direction_x_date": pd.crosstab(dirs[m], qdate[m]).to_dict()}
        # hour histograms by direction
        for tc in ["quote_as_of", "selected_quote_timestamp_utc"]:
            if tc in df.columns:
                ts = pd.Series([pts(v) for v in df[tc]], index=df.index, dtype=object)
                key = ts.map(lambda v: v.strftime("%Y-%m-%d %Hh") if v else "MISSING")
                rec[tc + "_hour_hist_by_direction"] = pd.crosstab(key, dirs).to_dict()
        out[label] = json.loads(json.dumps(rec, default=str))
        print("==", label, json.dumps(out[label], indent=1)[:5000])
    # run_plans second row
    p = sqlite3.connect(f"file:{os.path.join(ROOT, 'audit', 'td', 'AVS-TD-001', 'db_copies', 'run_plans.sqlite')}?mode=ro", uri=True)
    plans = []
    for run_id, cutoff, persisted, payload in p.execute("select pipeline_run_id, evidence_cutoff_utc, persisted_at_utc, payload_json from run_plans order by persisted_at_utc"):
        j = json.loads(payload)
        plans.append({"run": run_id, "cutoff": cutoff, "persisted": persisted, "session_state": j.get("session_state"), "operational_context": j.get("operational_context"),
                      "requested_action": j.get("requested_action"), "resolved_action": j.get("resolved_action"), "stages_to_run": j.get("stages_to_run"),
                      "keys_with_condition": [k for k in j if re.search(r"condition|operator|baseline|dirty", k)]})
    out["run_plans"] = plans
    print("run_plans:", json.dumps(plans, indent=1))
    # orchestrator caller context
    src = open(os.path.join(ROOT, "intelligent_orchestrator.py"), encoding="utf-8-sig").read().splitlines()
    out["orchestrator_caller_3195_3235"] = [f"{i}: {src[i-1].rstrip()}" for i in range(3195, 3236)]
    print("\n".join(out["orchestrator_caller_3195_3235"]))
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
