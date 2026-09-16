"""D5 — EXECUTABLE_NOW-like rows on the 11 Sep morning artefacts: bid>0, ask>bid, provider ts within 15 min, spread<=18%."""
from __future__ import annotations
import json, sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d5_executable_now.json"
EXEC_LIMIT_PCT = 18.0   # domain/long_option_execution.py:16 LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT
FRESH_MIN = 15          # domain/option_contract_liquidity.py:142 DEFAULT_QUOTE_FRESHNESS_MAX_SECONDS = 15*60


def analyse(run: str, rel: str) -> dict:
    p = art(run, rel)
    if not p.exists():
        return {"missing": str(p)}
    hdr = header(p)
    state_cols = [c for c in hdr if re.search(r"(^|_)(liquidity_state|executable_now|current_quote_executable|morning_transition_state|execution_quote_status|olm_guard_disposition|olm_guard_state|effective_execution_verdict|morning_permission|morning_state|execution_eligibility_state|lab_execution_status|execution_state|contract_data_state|morning_execution_permission|morning_execution_lane|spread_policy_state)$", c)]
    quote_cols = [c for c in hdr if re.search(r"(live_contract_(bid|ask|spread_pct|mid)|^contract_(bid|ask|mid|spread_pct)$|current_contract_(bid|ask|spread_pct)|morning_contract_(bid|ask|spread_pct)|quote_timestamp|quote_fetch|quote_as_of|quote_age|provider_timestamp|contract_quote_timestamp|execution_quote_timestamp|live_quote|refresh_timestamp|refresh_window|postopen)", c)]
    dcol = next((c for c in ("governed_direction", "final_direction", "direction") if c in hdr), None)
    cols = list(dict.fromkeys(["ticker"] + ([dcol] if dcol else []) + state_cols + quote_cols))
    df = read_csv(p, usecols=cols)
    b = direction_bucket(df[dcol]) if dcol else pd.Series("OTHER", index=df.index)
    res = {"file": str(p), "rows": len(df), "state_cols": state_cols, "quote_cols": quote_cols}
    res["state_values"] = {c: vc(df[c]) for c in state_cols if df[c].nunique() <= 30}
    # rows with any EXECUTABLE_NOW / EXECUTE-like state
    pat = re.compile(r"EXECUTABLE_NOW|^EXECUTE$|EXECUTE_NOW|^GO$|EXECUTION_EXECUTABLE", re.I)
    mask = pd.Series(False, index=df.index); which = {}
    for c in state_cols:
        m = df[c].astype(str).str.contains(pat, na=False) | (df[c].astype(str).str.upper().eq("TRUE") & c.endswith(("executable_now", "current_quote_executable")))
        if m.any():
            which[c] = {"n": int(m.sum()), "values": vc(df.loc[m, c])}
        mask |= m
    res["exec_like_columns"] = which
    res["exec_like_rows"] = {"ALL": int(mask.sum()), **{k: int((mask & (b == k)).sum()) for k in ("CALL", "PUT", "OTHER")}}
    sub = df[mask].copy()
    if len(sub):
        bid_c = next((c for c in ("live_contract_bid", "current_contract_bid", "contract_bid", "morning_contract_bid") if c in sub), None)
        ask_c = next((c for c in ("live_contract_ask", "current_contract_ask", "contract_ask", "morning_contract_ask") if c in sub), None)
        ts_cols = [c for c in sub.columns if re.search(r"timestamp|quote_as_of|quote_fetch", c)]
        res["chosen"] = {"bid": bid_c, "ask": ask_c, "ts_cols": ts_cols}
        bid = pd.to_numeric(sub[bid_c], errors="coerce") if bid_c else pd.Series(float("nan"), index=sub.index)
        ask = pd.to_numeric(sub[ask_c], errors="coerce") if ask_c else pd.Series(float("nan"), index=sub.index)
        sub["chk_bid_gt_0"] = bid > 0
        sub["chk_ask_gt_bid"] = ask > bid
        mid = (ask + bid) / 2
        sub["spread_frac_mid"] = (ask - bid) / mid
        sub["chk_spread_le_limit"] = sub["spread_frac_mid"] <= EXEC_LIMIT_PCT / 100
        gate = pd.Timestamp(json.load(open(art(run, "morning_validation/morning_gate_summary_<run>.json")))["validated_at_utc"])
        res["gate_time"] = str(gate)
        ts_res = {}
        for c in ts_cols:
            t = pd.to_datetime(sub[c], errors="coerce", utc=True)
            age_min = (gate - t).dt.total_seconds() / 60
            ts_res[c] = {"nonnull": int(t.notna().sum()), "min_age_min": None if t.isna().all() else float(age_min.min()), "median_age_min": None if t.isna().all() else float(age_min.median()), "max_age_min": None if t.isna().all() else float(age_min.max()), "within_15_min": int(((age_min >= -5) & (age_min <= FRESH_MIN)).sum())}
        res["timestamp_checks"] = ts_res
        # choose provider ts column: prefer names with 'quote_timestamp'/'quote_as_of', else any
        prov = next((c for c in ts_cols if re.search(r"contract_quote_timestamp|execution_quote_timestamp|quote_as_of|selected_quote_timestamp|live_quote", c)), ts_cols[0] if ts_cols else None)
        res["provider_ts_col"] = prov
        if prov:
            t = pd.to_datetime(sub[prov], errors="coerce", utc=True)
            age = (gate - t).dt.total_seconds() / 60
            sub["chk_fresh_15m"] = (age >= -5) & (age <= FRESH_MIN)
        else:
            sub["chk_fresh_15m"] = False
        sub["all_pass"] = sub[["chk_bid_gt_0", "chk_ask_gt_bid", "chk_spread_le_limit", "chk_fresh_15m"]].all(axis=1)
        sb = direction_bucket(sub[dcol]) if dcol else pd.Series("OTHER", index=sub.index)
        summ = {}
        for k in ("ALL", "CALL", "PUT", "OTHER"):
            m = pd.Series(True, index=sub.index) if k == "ALL" else (sb == k)
            n = int(m.sum())
            summ[k] = {"n": n, **{c: int((sub[c] & m).sum()) for c in ("chk_bid_gt_0", "chk_ask_gt_bid", "chk_spread_le_limit", "chk_fresh_15m", "all_pass")}}
            if n:
                summ[k]["spread_frac_median"] = float(sub.loc[m, "spread_frac_mid"].median())
        res["checks"] = summ
        res["examples_fail"] = sub.loc[~sub["all_pass"], ["ticker"] + [c for c in (bid_c, ask_c, prov) if c] + ["spread_frac_mid", "chk_bid_gt_0", "chk_ask_gt_bid", "chk_spread_le_limit", "chk_fresh_15m"]].head(12).to_dict("records")
    return res


if __name__ == "__main__":
    out = {}
    for rel in ("morning_validation/morning_validated_trades_<run>.csv", "intelligence_lab/final_opportunity_book_<run>.csv", "intelligence_lab/lab_signal_book_v3.csv", "trades/execution_gated_<run>.csv", "trades/execution_actionable_<run>.csv"):
        out[rel] = analyse(PRIMARY, rel)
    # pre-open / post-open run existence
    metas = []
    for d in sorted(RUNS.iterdir()):
        m = d / "run_meta.json"
        if m.exists():
            try:
                j = json.load(open(m))
                metas.append({"run": d.name, "pipeline_mode": j.get("pipeline_mode"), "run_condition": j.get("run_condition"), "git": j.get("git_describe")})
            except Exception as e:
                metas.append({"run": d.name, "error": str(e)})
    out["run_conditions"] = metas
    out["run_condition_values"] = sorted({str(m.get("run_condition")) for m in metas})
    out["pipeline_mode_values"] = sorted({str(m.get("pipeline_mode")) for m in metas})
    dump(out, OUT)
    for k, v in out.items():
        if isinstance(v, dict) and "exec_like_rows" in v:
            print(k, v["exec_like_rows"], v.get("exec_like_columns", {}).keys(), v.get("checks", {}).get("ALL"))
    print(out["run_condition_values"], out["pipeline_mode_values"])
