"""m11 - macro packet age/status, and final_run_manifest.json mtime versus run close.

Claims:
  s11.10: the run macro packet was approximately 39.8 hours old and labelled STALE/PARTIAL.
  s11.9:  loading the Intelligence Lab changes the completed manifest timestamp.

Read-only: os.stat and json.load only.
"""
import datetime as dt
import json
import os

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"


def local(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


pkt = json.load(open(os.path.join(RUN, "macro_quant_packet.json"), encoding="utf-8"))
print("--- macro_quant_packet.json ---")
for k in ("macro_generated_at_utc", "macro_normalised_at_utc", "macro_age_hours",
          "macro_freshness_status", "macro_data_quality", "macro_regime_label",
          "macro_execution_caution"):
    print(f"  {k} = {pkt.get(k)!r}")

snap_path = os.path.join(RUN, "macro_snapshot.json")
snap = json.load(open(snap_path, encoding="utf-8"))
print("\n--- macro_snapshot.json (top-level freshness keys) ---")
for k in sorted(snap):
    if any(w in k.lower() for w in ("age", "fresh", "quality", "generated", "asof", "as_of", "stale")):
        v = snap[k]
        print(f"  {k} = {v!r}" if not isinstance(v, (dict, list)) else f"  {k} = <{type(v).__name__}>")

print("\n--- file timestamps (local, then UTC) ---")
files = ["final_run_manifest.json", "run_meta.json", "macro_quant_packet.json",
         "pipeline_integrity_20260831_010309.json",
         os.path.join("intelligence_lab", "final_opportunity_book_20260831_010309.csv"),
         os.path.join("morning_validation", "morning_candidates_20260831_010309.csv")]
stats = {}
for f in files:
    p = os.path.join(RUN, f)
    if not os.path.exists(p):
        print(f"  {f}: MISSING")
        continue
    st = os.stat(p)
    stats[f] = st.st_mtime
    print(f"  {f}: mtime {local(st.st_mtime)}  ({utc(st.st_mtime)})")

if "final_run_manifest.json" in stats and "run_meta.json" in stats:
    d = stats["final_run_manifest.json"] - stats["run_meta.json"]
    print(f"\n  delta final_run_manifest.json - run_meta.json = {d:.0f} s = {d/3600:.4f} h")

meta = json.load(open(os.path.join(RUN, "run_meta.json"), encoding="utf-8"))
print("\n--- run_meta.json declared timestamps ---")
for k in ("pinned_at_utc", "status_updated_at_utc", "run_status", "operator_accepted_at_utc"):
    print(f"  {k} = {meta.get(k)!r}")

man = json.load(open(os.path.join(RUN, "final_run_manifest.json"), encoding="utf-8"))
print("\n--- final_run_manifest.json keys and any timestamps ---")
print(f"  keys: {sorted(man)}")
for k, v in man.items():
    if isinstance(v, str) and ("T" in v and "-" in v):
        print(f"  {k} = {v!r}")
