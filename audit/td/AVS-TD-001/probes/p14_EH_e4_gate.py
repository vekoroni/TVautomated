"""p14_EH_e4_gate: (1) check tools/build_outcome_learning_snapshot.py is read-only
(source lines + hash of the DB copies before/after), run it against the COPIES with
output under probes/, (2) apply the REQ-WP4-04 / outcome_learning gate conditions to
audit/avs_fix_002/stage6/CURRENT_LEARNING_READINESS.json and to the fresh snapshot,
(3) search stored runs and audit/ for any artefact claiming CALIBRATED.
Output: p14_EH_e4_gate_out.json, p14_EH_e4_snapshot_from_copies.json
"""
import json, os, sys, subprocess, hashlib, glob
ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", "..", "..", ".."))
COPIES = os.path.abspath(os.path.join(ROOT, "..", "db_copies"))
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""): h.update(chunk)
    return h.hexdigest()
ledger = os.path.join(COPIES, "decision_outcome_ledger.sqlite"); cp = os.path.join(COPIES, "control_plane.sqlite")
before = {"ledger": sha(ledger), "ledger_mtime": os.path.getmtime(ledger), "control_plane_mtime": os.path.getmtime(cp)}
outp = os.path.join(ROOT, "p14_EH_e4_snapshot_from_copies.json")
cmd = [sys.executable, os.path.join(REPO, "tools", "build_outcome_learning_snapshot.py"), "--ledger", ledger, "--control-plane", cp,
       "--config", os.path.join(REPO, "config", "governed_constants_v1.json"), "--output", outp]
proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, timeout=600)
after = {"ledger": sha(ledger), "ledger_mtime": os.path.getmtime(ledger), "control_plane_mtime": os.path.getmtime(cp)}
snap = json.load(open(outp)) if os.path.exists(outp) else {}
readiness = json.load(open(os.path.join(REPO, "audit", "avs_fix_002", "stage6", "CURRENT_LEARNING_READINESS.json")))
cfg = json.load(open(os.path.join(REPO, "config", "governed_constants_v1.json"), encoding="utf-8-sig"))["outcome_learning"]
def gate(doc):
    ma = doc["model_activation"]; s = doc["summary"]
    checks = {
        "fit_eligible_records>=minimum_fit_outcomes": (ma["fit_eligible_records"], cfg["minimum_fit_outcomes"], ma["fit_eligible_records"] >= cfg["minimum_fit_outcomes"]),
        "coverage>=minimum_coverage": (ma["coverage_fraction"], cfg["minimum_coverage"], ma["coverage_fraction"] >= cfg["minimum_coverage"]),
        "every_stratum>=minimum_stratum_outcomes": (ma["stratum_counts"], cfg["minimum_stratum_outcomes"], not ma["deficient_strata"]),
        "held_out_metrics_present": (ma["metrics_present"], True, bool(ma["metrics_present"])),
        "model_activation_enabled": (cfg["model_activation_enabled"], True, bool(cfg["model_activation_enabled"])),
        "complete_outcomes": s["complete_outcomes"], "presented_candidates": s["presented_candidates"],
        "population_reconciled": s["population_reconciled"],
    }
    return {"state": ma["state"], "can_activate": ma["can_activate"], "reason_codes": ma["reason_codes"], "checks": checks,
            "my_verdict": "PASS" if all(v[2] for k, v in checks.items() if isinstance(v, tuple)) else "FAIL (INSUFFICIENT_OUTCOMES)"}
# search for CALIBRATED claims
hits = []
for pat in ("data/output/runs/20260911_115904/**/*.json", "data/output/runs/20260910_150045/**/*.json", "audit/avs_fix_002/**/*.json", "audit/avs_fix_002/**/*.md"):
    for f in glob.glob(os.path.join(REPO, pat), recursive=True):
        if "packages" in f or os.path.getsize(f) > 30_000_000: continue
        try: txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception: continue
        for tok in ("CALIBRATED_EXPECTED_UTILITY", '"probabilities_calibrated": true', "probabilities_calibrated=True", "calibration_table"):
            if tok in txt: hits.append((os.path.relpath(f, REPO), tok))
out = {"cmd": cmd, "returncode": proc.returncode, "stdout_head": proc.stdout[:1500], "stderr_tail": proc.stderr[-1500:],
       "copies_unchanged": before == after, "before": before, "after": after,
       "tool_source_read_only_evidence": "tools/build_outcome_learning_snapshot.py:43 DecisionOutcomeLedger(arguments.ledger, read_only=True); canonical_data/decision_outcome_ledger.py:44-50 mode=ro URI; :114-115 append raises when read_only; control plane read via canonical_data/outcome_learning.py:183 sqlite3.connect(path) SELECT-only",
       "gate_on_CURRENT_LEARNING_READINESS": gate(readiness), "gate_on_fresh_snapshot_from_copies": gate(snap) if snap else None,
       "readiness_equals_fresh_snapshot": (readiness == snap) if snap else None,
       "calibrated_claim_hits": hits}
json.dump(out, open(os.path.join(ROOT, "p14_EH_e4_gate_out.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
