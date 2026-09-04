"""m00 - dump headers of every artefact CSV used by the cross-verification.

Read-only. Writes nothing outside measurements/.
"""
import csv
import json
import os
import sys

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"

FILES = {
    "discovery": os.path.join(RUN, "discovery", f"discovery_candidates_ultimate_{RID}.csv"),
    "vanguard": os.path.join(RUN, "vanguard", "vanguard_signals.csv"),
    "options": os.path.join(RUN, "options", f"options_intelligence_{RID}.csv"),
    "execution": os.path.join(RUN, "execution", f"execution_v3_5_{RID}.csv"),
    "eil": os.path.join(RUN, "superbrain", f"eil_enriched_{RID}.csv"),
    "wbs": os.path.join(RUN, "superbrain", f"wall_break_scores_{RID}.csv"),
    "morning": os.path.join(RUN, "morning_validation", f"morning_candidates_{RID}.csv"),
    "book": os.path.join(RUN, "intelligence_lab", f"final_opportunity_book_{RID}.csv"),
}

out = {}
for name, path in FILES.items():
    if not os.path.exists(path):
        out[name] = {"exists": False}
        continue
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    with open(path, "r", encoding="utf-8", newline="") as fh:
        hdr = next(csv.reader(fh))
    out[name] = {"exists": True, "n_cols": len(hdr), "columns": hdr}

dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "m00_headers.json")
with open(dest, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1)

for name, info in out.items():
    print(name, info.get("n_cols"))
print("written", dest)
