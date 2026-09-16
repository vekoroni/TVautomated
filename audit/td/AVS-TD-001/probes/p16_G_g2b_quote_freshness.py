"""p16_G_g2b_quote_freshness.py -- Track G / G2 supplement: executable-while-stale.  READ-ONLY.

The v3 book (19 GO_LIMIT rows) and the final opportunity book (1,444 rows) disagree on quote_freshness for
the same 19 rows.  This probe joins the two books on ticker+contract_symbol and reports quote_freshness,
quote_as_of, is_stale, execution_quote_status, morning_quote_timestamp_utc, morning_execution_permission,
lab_verdict for the 19 rows, by direction; and cross-tabs morning_quote_timestamp_utc DATE x quote_freshness
x eil_v3_verdict on the final book (are prior-session quotes labelled FRESH?).
Outputs p16_G_g2b_quote_freshness.json and .csv beside this file.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
RUN = "20260911_115904"
R = ROOT / "data/output/runs" / RUN / "intelligence_lab"
OUT = Path(__file__).with_suffix(".json")
v3 = pd.read_csv(R / "lab_signal_book_v3.csv", dtype=str, keep_default_na=False)
fb = pd.read_csv(R / f"final_opportunity_book_{RUN}.csv", dtype=str, keep_default_na=False)
Q = [c for c in ("quote_freshness", "quote_as_of", "is_stale", "execution_quote_status", "morning_quote_timestamp_utc",
                 "selected_quote_timestamp_utc", "current_quote_timestamp_utc", "quote_provider_timestamp_utc",
                 "morning_execution_permission", "lab_verdict", "executable_now", "execution_viability_state",
                 "morning_transition_state", "opportunity_tier", "eil_v3_verdict", "final_direction") if c in v3.columns or c in fb.columns]
res = {"run": RUN, "quote_cols_present_v3": [c for c in Q if c in v3.columns], "quote_cols_present_final": [c for c in Q if c in fb.columns]}
key = ["ticker", "contract_symbol"]
j = v3[key + [c for c in Q if c in v3.columns]].merge(fb[key + [c for c in Q if c in fb.columns]], on=key, how="left", suffixes=("_v3", "_fb"))
j.to_csv(Path(__file__).with_suffix(".csv"), index=False)
res["joined_rows"] = len(j)
res["v3_quote_freshness"] = v3["quote_freshness"].value_counts().to_dict()
res["fb_quote_freshness_for_same_19"] = j["quote_freshness_fb"].value_counts().to_dict()
res["v3_quote_as_of_sample"] = v3["quote_as_of"].head(5).tolist() if "quote_as_of" in v3.columns else None
res["fb_quote_as_of_same19_sample"] = j["quote_as_of_fb"].head(5).tolist() if "quote_as_of_fb" in j.columns else None
d = v3["final_direction"].str.upper().map(lambda x: x if x in ("CALL", "PUT") else "OTHER")
res["v3_executable_permission_while_quote_freshness_STALE_by_dir"] = v3[(v3["quote_freshness"] == "STALE") & (v3["morning_execution_permission"] == "GO_LIMIT")].assign(_d=d).groupby("_d").size().to_dict()
res["v3_is_stale_vs_quote_freshness"] = v3.groupby(["is_stale", "quote_freshness", "execution_quote_status"]).size().to_dict()
res["v3_is_stale_vs_quote_freshness"] = {"|".join(k): int(v) for k, v in res["v3_is_stale_vs_quote_freshness"].items()}
res["v3_executable_now_values"] = v3["executable_now"].value_counts().to_dict() if "executable_now" in v3.columns else "COLUMN ABSENT"
res["fb_executable_now_values"] = fb["executable_now"].value_counts().to_dict() if "executable_now" in fb.columns else "COLUMN ABSENT"
# prior-session quote timestamps labelled FRESH on the final book
fb["_mq_date"] = fb["morning_quote_timestamp_utc"].str[:10]
fb["_qa_date"] = fb["quote_as_of"].str[:10] if "quote_as_of" in fb.columns else ""
fb["_dir"] = fb["final_direction"].str.upper().map(lambda x: x if x in ("CALL", "PUT") else "OTHER")
res["fb_morning_quote_date_x_quote_freshness"] = {"|".join(k): int(v) for k, v in fb.groupby(["_mq_date", "quote_freshness"]).size().items()}
res["fb_quote_as_of_date_x_quote_freshness"] = {"|".join(k): int(v) for k, v in fb.groupby(["_qa_date", "quote_freshness"]).size().items()}
res["fb_eil_EXECUTE_by_morning_quote_date_dir"] = {"|".join(k): int(v) for k, v in fb[fb["eil_v3_verdict"] == "EXECUTE"].groupby(["_mq_date", "quote_freshness", "_dir"]).size().items()}
res["fb_GO_LIMIT_by_quote_as_of_date_dir"] = {"|".join(k): int(v) for k, v in fb[fb["morning_execution_permission"] == "GO_LIMIT"].groupby(["_qa_date", "quote_freshness", "_dir"]).size().items()}
res["fb_transition_EXECUTABLE_NOW_by_quote_as_of_date_dir"] = {"|".join(k): int(v) for k, v in fb[fb["morning_transition_state"] == "EXECUTABLE_NOW"].groupby(["_qa_date", "quote_freshness", "_dir"]).size().items()}
OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
print(json.dumps(res, indent=1, default=str))
show = [c for c in ("ticker", "final_direction_v3", "quote_freshness_v3", "quote_freshness_fb", "quote_as_of_v3", "quote_as_of_fb", "morning_quote_timestamp_utc_v3", "is_stale_v3", "execution_quote_status", "morning_execution_permission_v3") if c in j.columns]
print(j[show].to_string())
