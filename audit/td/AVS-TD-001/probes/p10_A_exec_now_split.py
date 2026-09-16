"""p10_A_exec_now_split.py -- Track A / ALG-12: split liquidity_state=EXECUTABLE_NOW on run 20260911_115904
final_opportunity_book by governed_direction (CALL/PUT/OTHER=STRANGLE+UNRESOLVED), crossed with morning permission,
verdict and quote date. Read-only. Output: probes/p10_A_exec_now_split_out.json"""
import json, os
import pandas as pd
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; RUN = "20260911_115904"
B = os.path.join(ROOT, "data", "output", "runs", RUN)
fob = pd.read_csv(os.path.join(B, "intelligence_lab", f"final_opportunity_book_{RUN}.csv"), low_memory=False)
mvt = pd.read_csv(os.path.join(B, "morning_validation", f"morning_validated_trades_{RUN}.csv"), low_memory=False)
out = {"rows": len(fob)}
g = fob["governed_direction"].astype(str).str.upper().str.strip()
d = g.where(g.isin(["CALL", "PUT"]), "OTHER")
m = fob["liquidity_state"].astype(str).str.upper().eq("EXECUTABLE_NOW")
out["governed_direction_counts"] = g.value_counts().to_dict()
out["exec_now_total"] = int(m.sum())
out["exec_now_by_governed_direction"] = {k: int((m & d.eq(k)).sum()) for k in ["CALL", "PUT", "OTHER"]}
out["exec_now_by_raw_governed_direction"] = g[m].value_counts().to_dict()
out["fob_has_morning_cols"] = [c for c in fob.columns if c in ("morning_execution_permission", "verdict", "quote_as_of", "morning_execution_mode")]
key = "ticker" if "ticker" in fob.columns and "ticker" in mvt.columns and fob["ticker"].is_unique and mvt["ticker"].is_unique else None
out["join_key"] = key
if key:
    j = fob[[key, "governed_direction", "liquidity_state"]].merge(mvt[[key, "morning_execution_permission", "verdict", "quote_as_of", "gate_checked_at_utc"]], on=key, how="left")
    jm = j["liquidity_state"].astype(str).str.upper().eq("EXECUTABLE_NOW")
    jd = j["governed_direction"].astype(str).str.upper().where(j["governed_direction"].astype(str).str.upper().isin(["CALL", "PUT"]), "OTHER")
    out["exec_now_x_morning_permission"] = pd.crosstab(j.loc[jm, "morning_execution_permission"].astype(str), jd[jm]).to_dict()
    out["exec_now_x_verdict"] = pd.crosstab(j.loc[jm, "verdict"].astype(str), jd[jm]).to_dict()
    out["exec_now_quote_as_of_date"] = j.loc[jm, "quote_as_of"].astype(str).str[:10].value_counts().to_dict()
    q = pd.to_datetime(j["quote_as_of"], utc=True, errors="coerce"); gc = pd.to_datetime(j["gate_checked_at_utc"], utc=True, errors="coerce")
    out["exec_now_quote_age_minutes_at_gate"] = {"min": float(((gc - q)[jm].dt.total_seconds() / 60).min()), "max": float(((gc - q)[jm].dt.total_seconds() / 60).max())}
    go = j["morning_execution_permission"].astype(str).eq("GO_LIMIT")
    out["go_limit_by_direction"] = {k: int((go & jd.eq(k)).sum()) for k in ["CALL", "PUT", "OTHER"]}
    out["go_limit_and_exec_now_by_direction"] = {k: int((go & jm & jd.eq(k)).sum()) for k in ["CALL", "PUT", "OTHER"]}
    # age of EXECUTABLE_NOW / GO_LIMIT quotes (quote_as_of) at the write time of downstream artefacts vs ALG-12 F=15 min
    stamps = {"final_opportunity_book_mtime": pd.Timestamp(os.path.getmtime(os.path.join(B, "intelligence_lab", f"final_opportunity_book_{RUN}.csv")), unit="s", tz="UTC"),
              "lab_signal_book_v3_mtime": pd.Timestamp(os.path.getmtime(os.path.join(B, "intelligence_lab", "lab_signal_book_v3.csv")), unit="s", tz="UTC"),
              "final_run_manifest_created_at_utc": pd.Timestamp(json.load(open(os.path.join(B, "final_run_manifest.json"), encoding="utf-8-sig"))["created_at_utc"])}
    out["quote_as_of_range_exec_now"] = [str(q[jm].min()), str(q[jm].max())]
    out["age_gt_15min_at"] = {}
    for name, t in stamps.items():
        old = (t - q) > pd.Timedelta(minutes=15)
        out["age_gt_15min_at"][name] = {"at": str(t), "exec_now": {k: int((jm & old & jd.eq(k)).sum()) for k in ["CALL", "PUT", "OTHER"]},
                                        "go_limit": {k: int((go & old & jd.eq(k)).sum()) for k in ["CALL", "PUT", "OTHER"]}}
# run condition vocabulary anywhere in run_meta
rm = json.load(open(os.path.join(B, "run_meta.json"), encoding="utf-8-sig"))
out["run_meta_has_postopen_or_condition"] = [k for k in json.dumps(rm).split('"') if k in ("POSTOPEN_CONTRACT_REFRESH", "run_condition", "morning_execution_mode")]
json.dump(out, open(os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_exec_now_split_out.json"), "w", encoding="utf-8"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
