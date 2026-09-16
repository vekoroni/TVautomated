"""p17 I4: release manifests — production_files sha256 vs the file at HEAD (cc509cb), key presence.

Read-only.  Output p17_IN_manifest_hashes.csv, p17_IN_manifest_summary.json.
"""
import csv, hashlib, json, subprocess
from pathlib import Path

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
OUT = ROOT / "audit/td/AVS-TD-001/probes"
MANS = {
    "STAGE0": "audit/avs_fix_002/stage0/STAGE0_BASELINE_MANIFEST.json",
    "STAGE1": "audit/avs_fix_002/stage1/STAGE1_RELEASE_MANIFEST.json",
    "STAGES2_5": "audit/avs_fix_002/stage2_5/STAGES2_5_RELEASE_MANIFEST.json",
    "STAGE6": "audit/avs_fix_002/stage6/STAGE6_RELEASE_MANIFEST.json",
    "POLICY": "audit/avs_fix_002/policy/POLICY_RELEASE_MANIFEST_20260912.json",
}
def git_blob_sha256(path):
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{path}"], capture_output=True)
    return hashlib.sha256(r.stdout).hexdigest() if r.returncode == 0 else None
def work_sha256(path):
    p = ROOT / path
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
rows, summary = [], {}
for stage, m in MANS.items():
    d = json.load(open(ROOT / m, encoding="utf-8-sig"))
    files = []
    for key in ("production_files", "test_and_tool_files", "governance_files"):
        v = d.get(key) or []
        if isinstance(v, dict):
            v = [{"path": k, "sha256": s} for k, s in v.items()]
        for e in v:
            if isinstance(e, dict) and "sha256" in e:
                head = git_blob_sha256(e["path"])
                work = work_sha256(e["path"])
                rows.append({"stage": stage, "list": key, "path": e["path"], "manifest_sha256": e["sha256"],
                             "head_blob_sha256": head, "worktree_sha256": work,
                             "matches_head": e["sha256"] == head, "matches_worktree": e["sha256"] == work})
                files.append(rows[-1])
    txt = json.dumps(d).lower()
    summary[stage] = {
        "file_entries_with_hash": len(files),
        "match_head": sum(r["matches_head"] for r in files),
        "match_worktree": sum(r["matches_worktree"] for r in files),
        "has_rollback_key": "rollback" in d,
        "rollback": d.get("rollback"),
        "mentions_migration": "migration" in txt,
        "mentions_backup_or_snapshot": ("backup" in txt) or ("snapshot" in txt),
        "mentions_restore": "restore" in txt,
        "mentions_expected_diff": "expected_diff" in txt or "expected-difference" in txt or "expected_difference" in txt,
        "base_commit": d.get("base_commit") or d.get("baseline_commit") or d.get("git_head"),
    }
with open(OUT / "p17_IN_manifest_hashes.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
json.dump(summary, open(OUT / "p17_IN_manifest_summary.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
for r in rows:
    if not r["matches_head"]:
        print("MISMATCH", r["stage"], r["path"])
