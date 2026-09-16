"""Artefact inventory for primary and comparison run. Read-only."""
import os, sys, json, csv, re, subprocess
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001")
RUNS = {"20260911_115904": "PRIMARY", "20260910_150045": "COMPARISON"}
PROD_EXCL = ("backups", "_attic", "Archive", "audit", "venv", ".git", "tests", "__pycache__", ".testdeps", "_cleanup_holding", "decommissioned", "legacy", "logs", "data", "dropbox\macro\Archive")
# load production python sources once
prod = {}
for dp, dn, fn in os.walk(ROOT):
    rel = os.path.relpath(dp, ROOT)
    if any(rel == e or rel.startswith(e + os.sep) for e in PROD_EXCL):
        dn[:] = []; continue
    for f in fn:
        if f.endswith(".py"):
            p = os.path.join(dp, f)
            try:
                prod[os.path.relpath(p, ROOT)] = open(p, "r", encoding="utf-8", errors="ignore").read()
            except Exception:
                pass
print("production py files loaded:", len(prod))
def stem_of(name, rid):
    s = name.replace(rid, "").replace("__", "_")
    s = re.sub(r"_+\.", ".", s)
    s = os.path.splitext(s)[0].rstrip("_")
    return s
def readers(stem):
    hits = []
    if len(stem) < 4:
        return hits
    for f, src in prod.items():
        if stem in src:
            # classify read vs write crudely
            hits.append(f)
    return hits
def count_rows(p, ext):
    try:
        if ext in (".csv", ".jsonl", ".txt", ".md"):
            with open(p, "rb") as f:
                n = sum(1 for _ in f)
            if ext == ".csv":
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    hdr = f.readline()
                return max(n - 1, 0), len(next(csv.reader([hdr])))
            return n, None
        if ext == ".json":
            if os.path.getsize(p) > 300_000_000:
                return None, None
            d = json.load(open(p, "r", encoding="utf-8"))
            if isinstance(d, list):
                return len(d), (len(d[0]) if d and isinstance(d[0], dict) else None)
            if isinstance(d, dict):
                return None, len(d)
        if ext == ".parquet":
            import pyarrow.parquet as pq
            t = pq.read_metadata(p)
            return t.num_rows, t.num_columns
    except Exception as e:
        return f"ERR:{type(e).__name__}", None
    return None, None
rows = []
for rid, role in RUNS.items():
    rd = os.path.join(ROOT, "data", "output", "runs", rid)
    fam_seen = {}
    for dp, dn, fn in os.walk(rd):
        for f in sorted(fn):
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, rd).replace("\\", "/")
            ext = os.path.splitext(f)[1].lower()
            size = os.path.getsize(p)
            family = None
            if rel.startswith("packages/"):
                family = "packages/<TICKER>.package.json"
            elif rel.startswith("morning_validation/validation_events/"):
                family = "morning_validation/validation_events/validation_<id>.json"
            if family:
                fam_seen.setdefault(family, {"n": 0, "bytes": 0, "example": rel})
                fam_seen[family]["n"] += 1; fam_seen[family]["bytes"] += size
                continue
            nrec, ncol = count_rows(p, ext)
            stem = stem_of(f, rid)
            rd_hits = readers(stem)
            rows.append({"run_id": rid, "role": role, "path": rel, "type": ext.lstrip("."), "size_bytes": size,
                         "records": nrec, "columns_or_keys": ncol, "stem": stem,
                         "production_modules_mentioning_stem": ";".join(rd_hits[:12]), "n_prod_mentions": len(rd_hits)})
    for fam, d in fam_seen.items():
        ex = os.path.join(rd, d["example"])
        nrec, ncol = count_rows(ex, os.path.splitext(ex)[1])
        stem = "package" if "packages" in fam else "validation_events"
        rd_hits = readers(".package.json" if "packages" in fam else "validation_events")
        rows.append({"run_id": rid, "role": role, "path": fam, "type": "json(family)", "size_bytes": d["bytes"],
                     "records": f"{d['n']} files; example keys={ncol}", "columns_or_keys": ncol, "stem": stem,
                     "production_modules_mentioning_stem": ";".join(rd_hits[:12]), "n_prod_mentions": len(rd_hits)})
with open(os.path.join(OUT, "probes", "p03_artefact_inventory_raw.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
prim = [r for r in rows if r["role"] == "PRIMARY"]; comp = {r["stem"] + r["type"] for r in rows if r["role"] == "COMPARISON"}
print("PRIMARY artefacts (families collapsed):", len(prim), " COMPARISON:", len(rows) - len(prim))
for r in prim:
    print(f'{r["path"]:75s} {r["type"]:12s} {r["size_bytes"]:>11} rec={str(r["records"]):>12} cols={str(r["columns_or_keys"]):>6} prod_mentions={r["n_prod_mentions"]:>3} in_comparison={"Y" if (r["stem"]+r["type"]) in comp else "N"}')
