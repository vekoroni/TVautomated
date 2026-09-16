"""Read-only run inventory: run_meta fields, manifests, key row counts per run."""
import json, os, glob, csv, sys, subprocess
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
RUNS = os.path.join(ROOT, "data", "output", "runs")
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001")
def linecount(p):
    try:
        with open(p, "rb") as f:
            return sum(1 for _ in f) - 1
    except Exception:
        return None
def jload(p):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e)}
rows = []
for rid in sorted(os.listdir(RUNS)):
    rd = os.path.join(RUNS, rid)
    if not os.path.isdir(rd):
        continue
    nfiles = sum(len(fs) for _, _, fs in os.walk(rd))
    metas = glob.glob(os.path.join(rd, "run_meta*.json"))
    meta = jload(metas[0]) if metas else {}
    man = jload(os.path.join(rd, "final_run_manifest.json")) if os.path.exists(os.path.join(rd, "final_run_manifest.json")) else {}
    def g(d, *keys):
        for k in keys:
            if isinstance(d, dict) and k in d:
                return d[k]
        return None
    disc = glob.glob(os.path.join(rd, "discovery", "discovery_candidates_ultimate_*.csv"))
    lab3 = os.path.join(rd, "intelligence_lab", "lab_signal_book_v3.csv")
    fob = glob.glob(os.path.join(rd, "intelligence_lab", "final_opportunity_book_*.csv"))
    triage = glob.glob(os.path.join(rd, "intelligence_lab", "lab_triage_view_*.csv"))
    opts = glob.glob(os.path.join(rd, "options", "options_intelligence_" + rid + ".csv"))
    mgs = glob.glob(os.path.join(rd, "morning_validation", "morning_gate_summary_*.json"))
    rows.append({
        "run_id": rid,
        "n_files": nfiles,
        "has_run_meta": bool(metas),
        "run_meta_file": os.path.basename(metas[0]) if metas else "",
        "run_meta_keys": "|".join(sorted(meta.keys()))[:400] if isinstance(meta, dict) else "",
        "run_condition": g(meta, "run_condition"),
        "baseline_eligible": g(meta, "baseline_eligible"),
        "code_identity": json.dumps(g(meta, "code_identity", "git_commit", "commit"))[:80],
        "config_identity": json.dumps(g(meta, "config_identity", "config_hash", "profile_hash"))[:80],
        "session_date": g(meta, "session_date", "as_of_date", "trading_date"),
        "evidence_cutoff_utc": g(meta, "evidence_cutoff_utc", "evidence_cutoff", "cutoff_utc"),
        "provider_completeness_evidence": "present" if g(meta, "provider_completeness_evidence") is not None else "absent",
        "operator_mode": g(meta, "operator_mode"),
        "macro_packet_id": g(meta, "macro_packet_id", "packet_id"),
        "manifest_keys": "|".join(sorted(man.keys()))[:300] if isinstance(man, dict) else "",
        "rows_discovery_ultimate": linecount(disc[0]) if disc else None,
        "rows_options_intelligence": linecount(opts[0]) if opts else None,
        "rows_lab_signal_book_v3": linecount(lab3) if os.path.exists(lab3) else None,
        "rows_final_opportunity_book": linecount(fob[0]) if fob else None,
        "rows_lab_triage_view": linecount(triage[0]) if triage else None,
        "has_morning_gate_summary": bool(mgs),
        "has_packages": os.path.isdir(os.path.join(rd, "packages")),
        "n_packages": len(os.listdir(os.path.join(rd, "packages"))) if os.path.isdir(os.path.join(rd, "packages")) else 0,
    })
with open(os.path.join(OUT, "probes", "p01_run_inventory_raw.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
for r in rows:
    print(r["run_id"], r["n_files"], r["run_meta_file"], "cond=", r["run_condition"], "sess=", r["session_date"], "cut=", r["evidence_cutoff_utc"], "disc=", r["rows_discovery_ultimate"], "opt=", r["rows_options_intelligence"], "lab3=", r["rows_lab_signal_book_v3"], "fob=", r["rows_final_opportunity_book"], "pce=", r["provider_completeness_evidence"], "mgs=", r["has_morning_gate_summary"], "pkg=", r["n_packages"])
print("META KEYS (primary):", rows[[i for i,r in enumerate(rows) if r["run_id"]=="20260911_115904"][0]]["run_meta_keys"])
