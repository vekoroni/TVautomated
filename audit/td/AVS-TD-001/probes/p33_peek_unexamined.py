"""p33 - brief content peek of artefacts touched only by M9's generic census (read-only)."""
import json, os, pandas as pd
RD = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260911_115904"
df = pd.read_csv(os.path.join(os.path.dirname(__file__), "p33_artefact_inventory_pass1.csv"), dtype=str).fillna("")
only = df[df.tracks_using.isin(["M9", "M9(probe)"])]
def short(v, n=90):
    s = json.dumps(v, default=str) if not isinstance(v, str) else v
    return s[:n]
for _, r in only.iterrows():
    p = os.path.join(RD, r.relative_path); print("\n#####", r.relative_path, r.record_count, "rows")
    try:
        if r.type == "csv":
            d = pd.read_csv(p, nrows=300, low_memory=False)
            print("cols:", ", ".join(list(d.columns)[:45]))
            if len(d): print("row0:", {k: short(v, 30) for k, v in list(d.iloc[0].items())[:14]})
        elif r.type == "parquet":
            d = pd.read_parquet(p); print("cols:", ", ".join(list(d.columns)[:45])); print("row0:", {k: short(v, 30) for k, v in list(d.iloc[0].items())[:14]})
        elif r.type == "json":
            d = json.load(open(p, encoding="utf-8"))
            if isinstance(d, dict):
                for k, v in list(d.items())[:25]: print(" ", k, "=", short(v))
            else: print("list len", len(d), short(d[0], 300))
        else:
            print(open(p, encoding="utf-8", errors="ignore").read()[:600])
    except Exception as e: print("ERR", e)
