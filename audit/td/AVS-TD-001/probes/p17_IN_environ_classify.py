"""p17 I2 / NFR-09: every os.environ / os.getenv read in tracked production .py, classified.

Production scope = tracked .py outside tests/, backups/, audit/, _attic/.  Column
in_stage0_import_graph marks modules on the Stage 0 production import graph
(audit/avs_fix_002/stage0/STAGE0_BASELINE_MANIFEST.json import_graph.nodes).
documented_in_release_profile = variable named in contracts/dynamic_session_runtime_v1.json.
Read-only.  Output: p17_IN_environ_hits.csv and p17_IN_environ_summary.json.
"""
import csv, json, re, subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
OUT = ROOT / "audit/td/AVS-TD-001/probes"
files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.py"], capture_output=True, text=True).stdout.split()
EXCL = ("tests/", "backups/", "audit/", "_attic/", ".codex")
files = [f for f in files if not f.startswith(EXCL) and "/_attic/" not in f]
man = json.load(open(ROOT / "audit/avs_fix_002/stage0/STAGE0_BASELINE_MANIFEST.json", encoding="utf-8-sig"))
graph = {(n.get("path") or n.get("module") or n.get("file") or "") if isinstance(n, dict) else n for n in man["import_graph"]["nodes"]}
profile = json.load(open(ROOT / "contracts/dynamic_session_runtime_v1.json", encoding="utf-8-sig"))
documented = set(profile["feature_flags"])
PAT = re.compile(r"\b_?os\.(environ|getenv)\b|\benv\.(get|setdefault)\(|\benviron\.get\(")
NAME = re.compile(r"[\"']([A-Z][A-Z0-9_]{2,})[\"']")

def classify(name):
    if not name:
        return "ENV_MAPPING_PASSTHROUGH"
    if re.search(r"KEY|TOKEN|PASSWORD|USERNAME|ACCOUNT_NUMBER|GMAIL|RECIPIENT|WORKSPACE_ID", name):
        return "CREDENTIAL"
    if re.search(r"RATIO|MIN_|MAX_|RFR|BUDGET|CONVICTION|DIMENSION|BIAS_MAP", name):
        return "NUMERIC_THRESHOLD"
    if re.search(r"ENABLED|ENFORCED|STRICT|REQUIRED|REQUIRE_|_MODE|POLICY|KIND|ENABLE_|DISABLE|PAPER|FLAG|WRITE_THROUGH|OFFLINE_REPLAY|REGIME_STATE|NOW_UTC", name):
        return "FEATURE_GATE"
    if re.search(r"PATH|DIR|ROOT|_DB|CACHE|RUN_ID|PYTHONPATH|CONTEXT", name):
        return "PATH_OR_IDENTITY"
    return "OTHER"

# constant indirection (e.g. STRICT_ENV = "AVSHUNTER_...")
const_map = {}
rows = []
for f in files:
    p = ROOT / f
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        continue
    for ln in lines:
        m = re.match(r"\s*([A-Z_][A-Z0-9_]*_(ENV|FLAG))\s*=\s*[\"']([A-Z0-9_]+)[\"']", ln)
        if m:
            const_map[(f, m.group(1))] = m.group(3)
    for i, ln in enumerate(lines):
        if not PAT.search(ln) or ln.lstrip().startswith("#"):
            continue
        ctx = " ".join(lines[i:i + 3])
        names = NAME.findall(ctx) or []
        if not names:
            for (ff, c), v in const_map.items():
                if ff == f and c in ctx:
                    names = [v]
        names = [n for n in names if not n.isdigit() and n not in {"PRODUCTION", "OFF", "SHADOW", "ACTIVE", "INCLUDE_LABELLED", "DUMMY", "YOUR_MARKETDATA_API_KEY"}] or [""]
        name = names[0]
        rows.append({
            "file": f, "line": i + 1, "variable": name, "class": classify(name),
            "in_stage0_import_graph": f in graph,
            "documented_in_release_profile": name in documented,
            "hardcoded_secret_default": bool(re.search(r"KEY[\"']\s*,\s*[\"'][A-Za-z0-9]{20,}[\"']", ctx)),
            "code": ln.strip()[:160] if "KEY" not in name else re.sub(r"[\"'][A-Za-z0-9]{20,}[\"']", "'<REDACTED>'", ln.strip())[:160],
        })
with open(OUT / "p17_IN_environ_hits.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
gates = [r for r in rows if r["class"] in ("FEATURE_GATE", "NUMERIC_THRESHOLD")]
summary = {
    "production_files_scanned": len(files),
    "hits_total": len(rows),
    "hits_by_class": Counter(r["class"] for r in rows),
    "hits_in_import_graph": sum(r["in_stage0_import_graph"] for r in rows),
    "hits_in_import_graph_by_class": Counter(r["class"] for r in rows if r["in_stage0_import_graph"]),
    "gating_or_threshold_variables_distinct": sorted({r["variable"] for r in gates}),
    "gating_variables_in_import_graph": sorted({r["variable"] for r in gates if r["in_stage0_import_graph"]}),
    "gating_variables_documented_in_profile": sorted({r["variable"] for r in gates if r["documented_in_release_profile"]}),
    "gating_variables_undocumented_in_import_graph": sorted({r["variable"] for r in gates if r["in_stage0_import_graph"] and not r["documented_in_release_profile"]}),
    "hardcoded_secret_default_sites": [f"{r['file']}:{r['line']}" for r in rows if r["hardcoded_secret_default"]],
}
json.dump(summary, open(OUT / "p17_IN_environ_summary.json", "w"), indent=1, default=list)
print(json.dumps(summary, indent=1, default=list))
