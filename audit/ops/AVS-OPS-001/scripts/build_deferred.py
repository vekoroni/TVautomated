"""AVS-OPS-001 - deferred.csv: everything that stayed, with the reason."""
import csv, os, pathlib, subprocess

OUT = pathlib.Path("audit/ops/AVS-OPS-001")
rows = list(csv.DictReader(open(OUT / "03_candidates.csv", encoding="utf-8")))
tierc = list(csv.DictReader(open(OUT / "04_tier_c_candidates.csv", encoding="utf-8")))

def cls(r):
    why = r["reason"]
    if "UNTRACKED_AND_GITIGNORED" in why:  return "UNTRACKED_GITIGNORED_NOT_A_GIT_OBJECT"
    if "DUPLICATE_BOTH_REACHABLE" in why:  return "DUPLICATE_BOTH_REACHABLE"
    if why.startswith("GRAPH_INBOUND"):    return "REFERENCED_GRAPH_INBOUND"
    if why.startswith("GREP_HITS"):
        return ("REFERENCED_GREP_SUBSTRING_ARTEFACT"
                if r.get("substring_artefact") == "True" else "REFERENCED_GREP_FILENAME")
    if why == "REACHABLE_FROM_ENTRY_POINT":return "REACHABLE_FROM_ENTRY_POINT"
    if why == "ABSENT":                    return "ABSENT"
    return "OTHER"

out = []
for r in rows:
    if r["decision"] == "MOVE":
        continue
    out.append({
        "path": r["path"], "tier": r["tier"], "class": cls(r),
        "tracked": r["tracked"], "gitignored": r["gitignored"],
        "graph_reachable": r["graph_reachable"], "graph_inbound": r["graph_inbound"],
        "grep_loose": r["grep_hits"], "grep_strict": r["grep_hits_strict"],
        "referrer": (r["graph_inbound_refs"] or r["grep_strict_referrers"]
                     or r["grep_first_referrer"]),
        "reason": r["reason"],
    })

# ACK decisions taken in-session
for p, why in [
    ("requirements..txt",
     "ACK 2026-09-04: leave both requirements files; the 6-package list is a partial "
     "dependency set (no numpy/scipy/pyarrow) and must not be promoted to requirements.txt"),
    ("requirements.txt", "ACK 2026-09-04: left empty and tracked; see requirements..txt"),
    ("AVSHUNTER-Intelligence/reports/vanguard_contract_audit.jsonl",
     "ACK 2026-09-04: nested dir holds one UNIQUE untracked 143.5 MB artefact "
     "(gitignored via reports/); git mv impossible, so left in place"),
]:
    out.append({"path": p, "tier": "A", "class": "ACK_DECISION_DEFER",
                "tracked": subprocess.run(["git","ls-files","--error-unmatch",p],
                                          capture_output=True).returncode == 0,
                "gitignored": subprocess.run(["git","check-ignore","-q",p],
                                             capture_output=True).returncode == 0,
                "graph_reachable": "", "graph_inbound": "", "grep_loose": "",
                "grep_strict": "", "referrer": "", "reason": why})

# empty scratch directories: git cannot track or move an empty directory
for d in sorted(x for x in os.listdir(".") if os.path.isdir(x)):
    if d.startswith((".codex_",)) or (d.startswith(("tmp","pip-","avs_macro_check_"))
                                      or d in ("datadnuold2404",)):
        n = sum(len(f) for _, _, f in os.walk(d))
        out.append({"path": d + "/", "tier": "A",
                    "class": ("GITIGNORED_BY_ACK_DECISION" if d.startswith(".codex_")
                              else ("EMPTY_DIR_NOT_A_GIT_OBJECT" if n == 0
                                    else "UNTRACKED_DIR")),
                    "tracked": False, "gitignored":
                        subprocess.run(["git","check-ignore","-q",d+"/"],
                                       capture_output=True).returncode == 0,
                    "graph_reachable": "", "graph_inbound": "", "grep_loose": "",
                    "grep_strict": "", "referrer": "",
                    "reason": (f"{n} files; " + (
                        "ACK 2026-09-04: .codex_*/ gitignored pre-commit-1 rather than "
                        "committed-then-attic'd, so the vendored runtime never enters history"
                        if d.startswith(".codex_") else
                        "empty directory - git stores no empty directories, so there is "
                        "nothing to git mv; commit 3 .gitignore hides it"))})

for r in tierc:
    out.append({"path": r["path"], "tier": "C", "class": "TIER_C_" + r["tier_c_status"],
                "tracked": r["tracked"], "gitignored": r["gitignored"],
                "graph_reachable": r["graph_reachable"], "graph_inbound": r["graph_inbound"],
                "grep_loose": "", "grep_strict": "", "referrer": r["graph_inbound_refs"],
                "reason": "Tier C: out of scope for AVS-OPS-001, list only "
                          "(post-MVP quarantine under AVS-INV-001)"})

dest = OUT / "deferred.csv"
with dest.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)

from collections import Counter
c = Counter(r["class"] for r in out)
print(f"deferred.csv: {len(out)} rows")
for k, v in c.most_common():
    print(f"   {v:4d}  {k}")
