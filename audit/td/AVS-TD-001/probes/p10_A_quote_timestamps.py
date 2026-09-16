"""p10_A_quote_timestamps.py -- Track A / A3 + A4 (REQ-WP0-03/04/05, ALG-12) on run 20260911_115904.
Read-only. Histograms of provider quote timestamps by session date and hour in the morning artefacts
and options_intelligence; missing-timestamp counts; fetch==provider to-the-second counts; FLAG/QUOTE_STALE
counts; EXECUTABLE_NOW-like counts; all split CALL/PUT/OTHER.
Output: probes/p10_A_quote_timestamps_out.json (and stdout)
"""
import json, os, re
from datetime import datetime, timezone
from collections import Counter
import pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
RUN = "20260911_115904"
BASE = os.path.join(ROOT, "data", "output", "runs", RUN)
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_quote_timestamps_out.json")
GATE_TS = datetime(2026, 9, 11, 17, 8, 56, tzinfo=timezone.utc)  # morning_gate_summary.validated_at_utc
SESSION_PRIOR = "2026-09-10"
SESSION_RUN = "2026-09-11"
EXEC_NOW = re.compile(r"EXECUTABLE_NOW|EXECUTABLE|GO_LIMIT|GO_MARKET|^GO$", re.I)


def pts(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).strip().replace("Z", "+00:00")
    if not s or s.lower() in ("nan", "none", "null", "nat"):
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        try:
            d = pd.Timestamp(s).to_pydatetime()
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def direction_of(df):
    for c in ["final_direction", "governed_direction", "canonical_direction", "resolved_direction", "direction", "options_direction", "option_type", "contract_type", "side"]:
        if c in df.columns:
            d = df[c].astype(str).str.upper().str.strip()
            out = d.where(d.isin(["CALL", "PUT"]), "OTHER")
            return out, c
    return pd.Series(["OTHER"] * len(df), index=df.index), "NONE"


def split(series_mask, dirs):
    return {k: int(series_mask[dirs == k].sum()) for k in ["CALL", "PUT", "OTHER"]}


def analyse(path, ts_cols, fetch_cols, label):
    res = {"path": os.path.relpath(path, BASE), "rows": None}
    if not os.path.exists(path):
        res["status"] = "ABSENT"
        return res
    df = pd.read_csv(path, low_memory=False)
    res["rows"] = int(len(df))
    dirs, dcol = direction_of(df)
    res["direction_col"] = dcol
    res["direction_counts"] = dirs.value_counts().to_dict()
    res["ts_cols_present"] = [c for c in ts_cols if c in df.columns]
    res["fetch_cols_present"] = [c for c in fetch_cols if c in df.columns]
    per_col = {}
    for c in res["ts_cols_present"]:
        ts = pd.Series([pts(v) for v in df[c]], index=df.index, dtype=object)
        has = ts.map(lambda v: v is not None)
        hist = Counter(v.strftime("%Y-%m-%d %Hh") for v in ts.dropna())
        dates = Counter(v.strftime("%Y-%m-%d") for v in ts.dropna())
        same_run_session = ts.map(lambda v: v is not None and v.strftime("%Y-%m-%d") == SESSION_RUN)
        prior_session = ts.map(lambda v: v is not None and v.strftime("%Y-%m-%d") == SESSION_PRIOR)
        entry = {
            "n_present": int(has.sum()), "n_missing": int((~has).sum()),
            "by_date": dict(sorted(dates.items())), "by_date_hour": dict(sorted(hist.items())),
            "same_session_2026-09-11_frac_of_present": round(float(same_run_session.sum() / has.sum()), 4) if has.sum() else None,
            "prior_session_2026-09-10": split(prior_session, dirs), "same_session_2026-09-11": split(same_run_session, dirs),
            "missing_split": split(~has, dirs), "present_split": split(has, dirs),
        }
        # fetch == provider to the second
        eqs = {}
        for fc in res["fetch_cols_present"]:
            ft = pd.Series([pts(v) for v in df[fc]], index=df.index, dtype=object)
            eq = pd.Series([(a is not None and b is not None and a.replace(microsecond=0) == b.replace(microsecond=0)) for a, b in zip(ts, ft)], index=df.index)
            eqs[fc] = split(eq, dirs)
        # equal to gate validated_at to the second
        eq_gate = ts.map(lambda v: v is not None and v.replace(microsecond=0) == GATE_TS)
        entry["eq_fetch_cols_to_second"] = eqs
        entry["eq_gate_validated_at_to_second"] = split(eq_gate, dirs)
        # sequence tell-tale: all quotes within +/- 5 min of each other AND on the run date (fetch-time-like)
        per_col[c] = entry
    res["per_ts_col"] = per_col
    # execution-state-like columns
    ex = {}
    for c in [c for c in df.columns if re.search(r"execution_state|execution_permission|olm_state|contract_execution_state|execution_verdict|morning_gate_verdict|^verdict$", c)]:
        vc = df[c].astype(str).value_counts().to_dict()
        ex[c] = {"value_counts": {k: int(v) for k, v in list(vc.items())[:20]},
                 "executable_now_like": split(df[c].astype(str).str.contains(EXEC_NOW), dirs)}
    res["execution_cols"] = ex
    # FLAG / QUOTE_STALE
    fl = {}
    vcol = "morning_gate_verdict" if "morning_gate_verdict" in df.columns else ("verdict" if "verdict" in df.columns else None)
    if vcol:
        v = df[vcol].astype(str).str.upper()
        fl["verdict_col"] = vcol
        fl["verdict_counts"] = {k: int(x) for k, x in v.value_counts().items()}
        flag = v == "FLAG"
        fl["FLAG_split"] = split(flag, dirs)
        for rc in [c for c in df.columns if re.search(r"flag_reason|block_reason|gate_reason|reason", c)]:
            rs = df[rc].astype(str)
            stale = rs.str.contains("QUOTE_STALE", case=False)
            if stale.any() or rc == "flag_reason":
                fl[rc] = {"QUOTE_STALE_in_FLAG_rows": split(stale & flag, dirs), "QUOTE_STALE_total": split(stale, dirs),
                          "top_values_in_FLAG": {k: int(x) for k, x in rs[flag].value_counts().head(12).items()}}
    for c in ["quote_freshness", "is_stale"]:
        if c in df.columns:
            fl[c] = {k: int(x) for k, x in df[c].astype(str).value_counts().items()}
            if vcol:
                fl[c + "_in_FLAG"] = {k: int(x) for k, x in df.loc[v == "FLAG", c].astype(str).value_counts().items()}
    res["flag_stale"] = fl
    # stale-in-text anywhere: columns whose values contain QUOTE_STALE
    cols_with_stale = []
    for c in df.columns:
        if df[c].dtype == object and df[c].astype(str).str.contains("QUOTE_STALE", case=False).any():
            cols_with_stale.append((c, int(df[c].astype(str).str.contains("QUOTE_STALE", case=False).sum())))
    res["columns_containing_QUOTE_STALE"] = cols_with_stale
    print("==", label, json.dumps({k: v for k, v in res.items() if k in ("rows", "direction_col", "direction_counts", "ts_cols_present", "fetch_cols_present", "columns_containing_QUOTE_STALE")}, default=str))
    for c, e in per_col.items():
        print("   ", c, "present", e["n_present"], "missing", e["n_missing"], "dates", e["by_date"], "eq_fetch", e["eq_fetch_cols_to_second"], "eq_gate", e["eq_gate_validated_at_to_second"])
    print("   exec:", json.dumps(ex, default=str)[:1500])
    print("   flag:", json.dumps(fl, default=str)[:2500])
    return res


def main():
    out = {"run": RUN, "gate_validated_at_utc": GATE_TS.isoformat()}
    ts_cols = ["quote_as_of", "selected_quote_timestamp_utc", "morning_quote_timestamp_utc", "current_quote_timestamp_utc",
               "contract_quote_timestamp", "live_contract_quote_timestamp", "monetisability_quote_timestamp_utc",
               "contract_quote_timestamp_utc", "quote_timestamp_utc", "l2_quote_timestamp_utc", "execution_quote_timestamp_utc",
               "quote_provider_timestamp_utc"]
    fetch_cols = ["gate_checked_at_utc", "quote_fetch_timestamp_utc", "contract_refresh_timestamp_utc", "morning_validated_at_utc", "observed_at", "fetched_at_utc", "refresh_timestamp_utc"]
    out["morning_validated_trades"] = analyse(os.path.join(BASE, "morning_validation", f"morning_validated_trades_{RUN}.csv"), ts_cols, fetch_cols, "morning_validated_trades")
    out["morning_candidates"] = analyse(os.path.join(BASE, "morning_validation", f"morning_candidates_{RUN}.csv"), ts_cols, fetch_cols, "morning_candidates")
    out["final_opportunity_book"] = analyse(os.path.join(BASE, "intelligence_lab", f"final_opportunity_book_{RUN}.csv"), ts_cols, fetch_cols, "final_opportunity_book")
    out["execution_gated"] = analyse(os.path.join(BASE, "trades", f"execution_gated_{RUN}.csv"), ts_cols, fetch_cols, "execution_gated")
    out["options_intelligence"] = analyse(os.path.join(BASE, "options", f"options_intelligence_{RUN}.csv"), ts_cols, fetch_cols + ["contract_quote_timestamp_source"], "options_intelligence")
    # options_intelligence: contract_quote_timestamp_source vocabulary
    oi = os.path.join(BASE, "options", f"options_intelligence_{RUN}.csv")
    if os.path.exists(oi):
        d = pd.read_csv(oi, usecols=lambda c: c in ("contract_quote_timestamp_source", "quote_freshness", "execution_permission", "ticker"), low_memory=False)
        out["options_intelligence_extra"] = {c: {k: int(v) for k, v in d[c].astype(str).value_counts().head(15).items()} for c in d.columns if c != "ticker"}
        print("OI extra:", out["options_intelligence_extra"])
    # cross-tab on morning_validated_trades: quote_as_of date x quote_freshness x ev3 QUOTE_STALE x selected ts present, by direction
    mvt = pd.read_csv(os.path.join(BASE, "morning_validation", f"morning_validated_trades_{RUN}.csv"), low_memory=False)
    dirs, _ = direction_of(mvt)
    qd = pd.Series([pts(v) for v in mvt["quote_as_of"]], index=mvt.index, dtype=object).map(lambda v: v.strftime("%Y-%m-%d") if v else "MISSING")
    gate = pd.Series([pts(v) for v in mvt["gate_checked_at_utc"]], index=mvt.index, dtype=object)
    qraw = pd.Series([pts(v) for v in mvt["quote_as_of"]], index=mvt.index, dtype=object)
    eq_gate = pd.Series([(a is not None and b is not None and a.replace(microsecond=0) == b.replace(microsecond=0)) for a, b in zip(qraw, gate)], index=mvt.index)
    sel_missing = mvt["selected_quote_timestamp_utc"].isna()
    stale = mvt["ev3_reason_code"].astype(str).str.contains("QUOTE_STALE")
    fresh = mvt["quote_freshness"].astype(str)
    xt = {}
    xt["quote_as_of_eq_gate_checked_at__vs__selected_ts_missing"] = pd.crosstab(eq_gate, sel_missing).to_dict()
    xt["quote_as_of_date_x_quote_freshness"] = pd.crosstab(qd, fresh).to_dict()
    xt["quote_as_of_date_x_ev3_QUOTE_STALE"] = pd.crosstab(qd, stale).to_dict()
    xt["FLAG_rows_quote_freshness_x_ev3_QUOTE_STALE"] = pd.crosstab(fresh[mvt["morning_gate_verdict"] == "FLAG"], stale[mvt["morning_gate_verdict"] == "FLAG"]).to_dict()
    xt["liquidity_state_counts"] = {k: int(v) for k, v in mvt["liquidity_state"].astype(str).value_counts().items()}
    xt["prior_session_rows_by_direction"] = {k: int(((qd == SESSION_PRIOR) & (dirs == k)).sum()) for k in ["CALL", "PUT", "OTHER"]}
    xt["eq_gate_rows_by_direction"] = {k: int((eq_gate & (dirs == k)).sum()) for k in ["CALL", "PUT", "OTHER"]}
    xt["eq_gate_rows_liquidity_state"] = {k: int(v) for k, v in mvt.loc[eq_gate, "liquidity_state"].astype(str).value_counts().items()}
    xt["eq_gate_rows_morning_execution_permission"] = {k: int(v) for k, v in mvt.loc[eq_gate, "morning_execution_permission"].astype(str).value_counts().items()}
    xt["GO_rows_quote_as_of_date_by_direction"] = pd.crosstab(qd[mvt["morning_gate_verdict"] == "GO"], dirs[mvt["morning_gate_verdict"] == "GO"]).to_dict()
    out["crosstabs"] = json.loads(json.dumps(xt, default=str))
    print("CROSSTABS:", json.dumps(out["crosstabs"], indent=1, default=str)[:4000])
    # desk_gate overlay (source of the 453 / 391-of-409 figures)
    dg_path = os.path.join(ROOT, "dropbox", "macro", "coaching", "desk_gate", f"desk_gate_{RUN}_evening.csv")
    dg = {"path": os.path.relpath(dg_path, ROOT), "exists": os.path.exists(dg_path)}
    if dg["exists"]:
        d = pd.read_csv(dg_path, low_memory=False)
        dg["rows"] = int(len(d)); dg["cols"] = int(d.shape[1])
        dd = d["direction"].astype(str).str.upper() if "direction" in d.columns else pd.Series(["OTHER"] * len(d))
        dd = dd.where(dd.isin(["CALL", "PUT"]), "OTHER")
        dg["direction_counts"] = {k: int(v) for k, v in dd.value_counts().items()}
        stale_cols = [c for c in d.columns if d[c].dtype == object and d[c].astype(str).str.contains("QUOTE_STALE", case=False).any()]
        dg["columns_containing_QUOTE_STALE"] = {c: int(d[c].astype(str).str.contains("QUOTE_STALE", case=False).sum()) for c in stale_cols}
        for c in stale_cols:
            m = d[c].astype(str).str.contains("QUOTE_STALE", case=False)
            dg[f"{c}_QUOTE_STALE_by_direction"] = {k: int((m & (dd == k)).sum()) for k in ["CALL", "PUT", "OTHER"]}
        if "lab_verdict" in d.columns:
            dg["lab_verdict_counts"] = {k: int(v) for k, v in d["lab_verdict"].astype(str).value_counts().items()}
        if "monetisability_state" in d.columns:
            dg["monetisability_state_counts"] = {k: int(v) for k, v in d["monetisability_state"].astype(str).value_counts().items()}
        ts_like = [c for c in d.columns if re.search(r"quote|timestamp|as_of|fetched|observed", c, re.I)]
        dg["timestamp_like_columns"] = ts_like
    out["desk_gate_overlay"] = dg
    print("DESK_GATE:", json.dumps(dg, indent=1, default=str)[:3000])
    # morning gate summary: does it carry a quote-timestamp histogram? (REQ-WP0-05)
    mg = json.load(open(os.path.join(BASE, "morning_validation", f"morning_gate_summary_{RUN}.json"), encoding="utf-8"))
    keys = list(mg.keys())
    out["morning_gate_summary_keys"] = keys
    out["morning_gate_summary_quote_hist_keys"] = [k for k in keys if re.search(r"quote|timestamp|provider|histogram|missing|fetch", k, re.I)]
    out["morning_gate_summary_counts"] = {k: mg[k] for k in ("input_candidates", "go_count", "flag_count", "block_count") if k in mg}
    # DOI physical fetch
    doi = json.load(open(os.path.join(BASE, "options", f"dynamic_options_intelligence_{RUN}.json"), encoding="utf-8"))
    out["doi"] = {k: doi.get(k) for k in ("physical_fetch_count", "canonical_reuse", "family_rows", "assessed_families", "counts_by_state", "exception_count")}
    print("MG summary quote-hist keys:", out["morning_gate_summary_quote_hist_keys"], out["morning_gate_summary_counts"])
    print("DOI:", out["doi"])
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, default=str)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
