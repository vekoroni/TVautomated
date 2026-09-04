"""AVS-OPS-001 - enumerate Tier A/B/C candidates and run both reference checks."""
import csv, json, os, pathlib, re, subprocess, sys
sys.path.insert(0, str(pathlib.Path("audit/ops/AVS-OPS-001/scripts").resolve()))
from refcheck import check  # noqa: E402

ROOT = pathlib.Path(".").resolve()

def tracked(p):
    return subprocess.run(["git", "ls-files", "--error-unmatch", p],
                          capture_output=True).returncode == 0
def ignored(p):
    return subprocess.run(["git", "check-ignore", "-q", p],
                          capture_output=True).returncode == 0

root_files = sorted(f for f in os.listdir(".") if os.path.isfile(f))
root_dirs = sorted(d for d in os.listdir(".") if os.path.isdir(d))

# ---------------- Tier A ----------------
BAK = re.compile(r"(\.bak$|\.bak_|\.rr_cap\.bak$|bak_)", re.I)
OLDTOK = re.compile(r"(^|[^a-z])(old|dnu)([^a-z]|\d|$)", re.I)
# prompt s4 Tier A lists *old0908.py explicitly; the token regex above misses it
# because the char before "old" is a letter (…intelligence|old0908.py).
OLD_SUFFIX = re.compile(r"(old|dnu)\d*\.py$", re.I)
NAMED_A = {
 "cmd_lines_debug.txt","menu_debug.txt","docx_extracted.txt","comp9_spec.txt",
 "hash_diag_20260421.json","hash_diag_fixed.json","build_packages_from_discovery.txt",
 "dropbox - Shortcut.lnk","dropbox - Shortcut (2).lnk","pipeline_interpreter - Shortcut.lnk",
 "Audit_AVSHUNTER_CompleteFixList_20260521.ps1","stability_run_template.ps1",
 "stability_run_template0.ps1","setup_config.ps1","check_pipeline.ps1",
 "run_evening.bat","run_premarket.bat","run_shadow_automation.bat","run_daily_orchestration.sh",
}
# ACK decision 2026-09-04: both requirements files stay put.
DEFER_BY_ACK = {"requirements..txt", "requirements.txt", "AVSHUNTER-Intelligence"}

tierA = []
for f in root_files:
    if f in DEFER_BY_ACK or f == ".env.txt":
        continue
    if (BAK.search(f) or f in NAMED_A or f.endswith(".lnk")
            or (f.endswith(".py") and (OLDTOK.search(f) or OLD_SUFFIX.search(f)))):
        tierA.append(f)

# ---------------- Tier B ----------------
TIER_B = ["morning_validation.py","morning_validation_engine.py","kelly_sizer.py",
 "position_sizing_engine.py","catastrophe_gate.py","execution_decision_engine.py",
 "premarket_intelligence_ULTIMATE.py","step4_test.py","step5_graceful_test.py","step6_test.py",
 "step6_test_v2.py","step6_test_v3.py","step7_test.py","step7_test_v2.py","step8_test.py",
 "step9_verify.py","step10_test.py","section11_tests.py","section11_tests_v2.py",
 "final_verify_c9.py","check7_prompt.py","lab_recon_selftest.py","macro_sector_propagation_test.py",
 "md_api_diagnostic.py","polygon_options_validation.py","actuarial_hash_diagnostic.py",
 "add_state_hash.py","scenario_builder.py","refresh_daily_data.py","run.py",
 "resume_after_vanguard.py","audit_latest_run.py","uat_audit_report.py",
 "WyckoffEngine_3101_v2.py","wyckoff_crabel_precor_logic_v2.py","wyckoff_phase_validator.py",
 "avshunter_options_intelligence.py","avshunter_monetisation_policy.py"]

rows = []
def add(path, tier, note=""):
    r = check(path) if path.endswith((".py",)) or True else None
    tr, ig = tracked(path), ignored(path)
    decision, reason = "MOVE", ""
    if not os.path.exists(path):
        decision, reason = "SKIP", "ABSENT"
    elif path == "avshunter_monetisation_policy.py":
        decision, reason = "DEFER", "DUPLICATE_BOTH_REACHABLE (prompt s4 Tier B: do not move)"
    elif ig and not tr:
        why = subprocess.run(["git", "check-ignore", "-v", path],
                             capture_output=True, text=True).stdout.strip()
        rule = why.split("	")[0] if why else ".gitignore"
        decision = "DEFER"
        reason = f"UNTRACKED_AND_GITIGNORED by {rule} - not a git object, git mv impossible"
    elif r["graph_inbound_n"] > 0:
        decision, reason = "DEFER", f"GRAPH_INBOUND={r['graph_inbound_n']}: " + ",".join(r["graph_inbound"][:3])
    elif r["grep_hits_n"] > 0:
        decision, reason = "DEFER", f"GREP_HITS={r['grep_hits_n']}: " + (r["grep_hits"][0][:120] if r["grep_hits"] else "")
    elif r["graph_reachable"]:
        decision, reason = "DEFER", "REACHABLE_FROM_ENTRY_POINT"
    rows.append({
        "path": path, "tier": tier, "tracked": tr, "gitignored": ig,
        "graph_in_nodes": r["in_graph"], "graph_reachable": r["graph_reachable"],
        "graph_inbound": r["graph_inbound_n"],
        "graph_inbound_refs": ";".join(r["graph_inbound"][:5]),
        "grep_hits": r["grep_hits_n"],
        "grep_hits_strict": r["grep_strict_n"],
        "grep_first_referrer": (r["grep_hits"][0].split(":", 1)[0] if r["grep_hits"] else ""),
        "grep_strict_referrers": ";".join(sorted({h.split(":", 1)[0] for h in r["grep_strict"]})[:5]),
        "substring_artefact": (r["grep_hits_n"] > 0 and r["grep_strict_n"] == 0),
        "decision": decision, "reason": reason or note,
    })

print("--- Tier A ---", flush=True)
for f in tierA:
    add(f, "A")
print("--- Tier B ---", flush=True)
for f in TIER_B:
    add(f, "B")

out = pathlib.Path("audit/ops/AVS-OPS-001/03_candidates.csv")
with out.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

mv = [r for r in rows if r["decision"] == "MOVE"]
df = [r for r in rows if r["decision"] == "DEFER"]
sk = [r for r in rows if r["decision"] == "SKIP"]
print(f"\ncandidates={len(rows)} MOVE={len(mv)} DEFER={len(df)} SKIP={len(sk)}")
print("\nDEFERRED:")
for r in df:
    print(f"  {r['path']:44s} [{r['tier']}] {r['reason'][:110]}")
print(f"\nMOVE by tier: A={sum(1 for r in mv if r['tier']=='A')} B={sum(1 for r in mv if r['tier']=='B')}")
