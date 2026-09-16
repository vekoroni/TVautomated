"""p21_M1_ledger.py -- read-only. Census of usmi_* fields in decision_outcome_ledger copy
(ledger_events.payload_json) per run_id / event_type. Writes p21_M1_ledger_usmi.csv beside itself.
"""
import os, json, sqlite3, collections
import pandas as pd
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
PROBES = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
DB = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "db_copies", "decision_outcome_ledger.sqlite")
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
df = pd.read_sql("select event_id, event_type, occurred_at_utc, run_id, ticker, thesis_id, payload_json from ledger_events", con)
con.close()
print("ledger rows", len(df)); print(df["event_type"].value_counts().to_dict()); print(df["run_id"].value_counts().to_dict())
recs = []
for r in df.itertuples(index=False):
    try:
        p = json.loads(r.payload_json) if r.payload_json else {}
    except Exception:
        p = {}
    def dig(d, key):
        # search top-level and one nested level for key
        if key in d: return d[key]
        for v in d.values():
            if isinstance(v, dict) and key in v: return v[key]
        return None
    recs.append({"event_id": r.event_id, "event_type": r.event_type, "occurred_at_utc": r.occurred_at_utc, "run_id": r.run_id, "ticker": r.ticker,
                 "usmi_sector_alignment": dig(p, "usmi_sector_alignment"), "usmi_scenario": dig(p, "usmi_scenario"), "usmi_state": dig(p, "usmi_state"),
                 "usmi_packet_id": dig(p, "usmi_packet_id"), "direction": dig(p, "final_direction") or dig(p, "direction") or dig(p, "governed_direction"),
                 "payload_top_keys_n": len(p)})
L = pd.DataFrame(recs)
L.to_csv(os.path.join(PROBES, "p21_M1_ledger_usmi.csv"), index=False)
print("usmi_sector_alignment:", L["usmi_sector_alignment"].value_counts(dropna=False).to_dict())
print("usmi_state:", L["usmi_state"].value_counts(dropna=False).to_dict())
print("usmi_scenario:", L["usmi_scenario"].value_counts(dropna=False).to_dict())
print("usmi_packet_id:", L["usmi_packet_id"].value_counts(dropna=False).to_dict())
print("direction:", L["direction"].value_counts(dropna=False).to_dict())
print(pd.crosstab([L["run_id"], L["event_type"]], L["usmi_sector_alignment"].fillna("NULL")))
# sample payload keys of one event with usmi field
s = df[df["payload_json"].str.contains("usmi_sector_alignment", na=False)].head(1)
if len(s):
    p = json.loads(s.iloc[0]["payload_json"]); print("sample top keys:", list(p.keys())[:60])
    for k, v in p.items():
        if isinstance(v, dict) and any("usmi" in kk for kk in v): print("  nested", k, {kk: vv for kk, vv in v.items() if "usmi" in kk or "direction" in kk})
