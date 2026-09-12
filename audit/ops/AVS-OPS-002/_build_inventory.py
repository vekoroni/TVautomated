"""AVS-OPS-002 Section 2 inventory generator. Read-only over the working tree."""
import csv, datetime, os, re, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(os.path.dirname(__file__), "02_inventory.csv")

# ---------------------------------------------------------------- status read
raw = subprocess.run(["git", "status", "--porcelain=v1", "-uall", "-z"],
                     cwd=ROOT, capture_output=True)
entries = []
parts = raw.stdout.split(b"\x00")
i = 0
while i < len(parts):
    p = parts[i]
    if not p:
        i += 1
        continue
    code = p[:2].decode("utf-8", "replace")
    path = p[3:].decode("utf-8", "replace")
    if code.startswith("R"):
        i += 1  # rename: next record is the source path
    entries.append((code, path))
    i += 1

# ---------------------------------------------------------------- group rules
EXACT = {}
def put(group, ws, paths):
    for p in paths:
        EXACT[p] = (ws, group)

put("G03", "MSI-QUOTE", [
    "contracts/quote_change_evidence.py", "contracts/lab_evidence_overlay.py",
    "contracts/interpreter_handoff_materializer.py", "tools/msi_production_readiness.py",
    "tests/test_msi_quote_and_size_lineage.py", "tests/test_msi_interpreter_handoff.py",
    "tests/test_msi_handoff_materializer.py"])
put("G04", "EIL", [
    "contracts/handoff_contract.py", "trade_book_builder.py", "position_sizing_engine.py",
    "tests/test_handoff_contract.py", "tests/test_big_bang_phase_6_7.py",
    "tests/test_eil_advisory_authority.py"])
put("G05", "IDENTITY", [
    "canonical_data/session_clock.py", "contracts/selected_contract_economics.py",
    "morning_gate.py", "tests/test_selected_contract_economics.py",
    "tests/test_morning_gate_contract_repair.py",
    "tests/test_avs_fix_001_w34_timevalue_monetisability.py"])
put("G06", "DTE", [
    "scripts/avshunter_options_intelligence.py", "tests/test_governed_dte_policy_alignment.py"])
put("G07", "MACRO-GEX", [
    "macro_domain/__init__.py", "macro_domain/gamma_exposure.py",
    "canonical_data/gamma_exposure_store.py", "canonical_data/contracts.py",
    "contracts/macro_file_contract.py", "scripts/build_local_gex.py",
    "scripts/refresh_macro_context.py", "docs/MACRO_DOMAIN.md",
    "tests/test_macro_domain_enhancements.py"])
put("G08", "ANTHROPIC-RT", [
    "anthropic_runtime_config.py", "config/anthropic_runtime.json",
    "config/ANTHROPIC_RUNTIME.md", "tests/test_anthropic_runtime_config.py"])
put("G09", "MI", [
    "build_macro_json.py", "macro_domain/us_money_index.py",
    "contracts/us_money_index_contract.py", "scripts/validate_us_money_index.py",
    "contracts/interpreter_macro_context.py", "canonical_data/decision_outcome_ledger.py",
    "scripts/macro_quant_packet.py", "scripts/inject_macro_into_packages.py",
    "pipeline_interpreter/prepare_interpreter_session.py",
    "tests/test_interpreter_macro_advisory_handoff.py",
    "tests/test_build_macro_json_anthropic_workspace.py",
    "tests/test_build_macro_json_response_repair.py"])
put("G10", "DOI-domain", [
    "domain/__init__.py", "contracts/dynamic_options_policy.py", "config/doi_runtime.json"])
put("G12", "DOI-tests", [
    "tools/doi11_production_readiness.py"])
put("G13", "DOI-wiring", [
    "intelligent_orchestrator.py", "eod_candidate_engine.py",
    "execution_intelligence_runner.py", "contracts/lab_control.py",
    "contracts/interpreter_handoff.py",
    "pipeline_interpreter/pipeline_interpreter_commands.py",
    "tests/test_eod_options_research_handoff.py",
    "canonical_data/__init__.py", "canonical_data/option_liquidity_lifecycle.py"])
put("G14", "LAB-UI", [
    "intelligence-lab/intelligence_lab.py", "intelligence-lab/static/index.html",
    "intelligence-lab/static/worker3-controls.js"])
put("G15", "W3", [
    "contracts/worker3_integration_v1.json", "contracts/worker3_provider_release_v1.json",
    "docs/AVS-W3-SD-001.md", "docs/AVS-W3-SD-002.md", "docs/AVS-W3-SD-003.md"])
put("G17", "EVIDENCE", ["pipeline_interpreter/evidence_resolver.py"])
put("G18", "HYGIENE", [
    "avshunter_discovery_ULTIMATE.py", "tests/test_discovery_scope_and_macro_timestamp.py"])
put("G-DDD", "DDD", ["tests/test_dynamic_session_phase6.py"])
put("G-UNK", "UNKNOWN", [
    "worker3/adapters/claude_refresh.py", "worker3/integration/provider_runner.py"])

DOC_DOI = "docs/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md"
EXACT[DOC_DOI] = ("DOI-domain", "G10")

# excluded audit bulk
EXCL_PREFIX = [
    ("audit/outcome_comparison/", "data/artefact",
     "vendored node_modules, artefact-build previews, xlsx and ndjson run output"),
    ("audit/doi/AVS-TST-DOI-001/scratch/", "data/artefact",
     "DOI tester run-output scratch (253 JSON files)"),
]

def classify(path):
    if path in EXACT:
        ws, g = EXACT[path]
        return ws, g
    for pre, _, _ in EXCL_PREFIX:
        if path.startswith(pre):
            return "ARTEFACT", "EXCLUDE"
    if path.startswith("audit/worker3_current_state_canary/"):
        return "AUDIT-W3-EVIDENCE", "G20"
    if path.startswith("audit/"):
        return "AUDIT", "G19"
    if path.startswith("worker3/"):
        return "W3", "G15"
    if re.match(r"tests/test_worker3_", path):
        return "W3", "G16"
    if re.match(r"tests/test_(dynamic_options_|doi)", path):
        return "DOI-tests", "G12"
    if path.startswith("domain/"):
        return "DOI-domain", "G10"
    if re.match(r"canonical_data/dynamic_options_", path):
        return "DOI-canonical", "G11"
    return "UNKNOWN", "G-UNK"

ARCHIVE_ROOTS = ("_cleanup_holding", "_attic", "Archive", "backups",
                 "decommissioned", "vanguard", "pipeline_interpreter/Archive")

rows = []
for code, path in entries:
    st = code.strip() or code
    st = st.replace(" ", "") or "?"
    full = os.path.join(ROOT, path.replace("/", os.sep))
    try:
        size = os.path.getsize(full)
        mtime = datetime.datetime.fromtimestamp(
            os.path.getmtime(full)).strftime("%Y-%m-%d %H:%M")
    except OSError:
        size, mtime = "", ""  # deleted in the working tree
    ext = os.path.splitext(path)[1].lstrip(".")
    is_test = "Y" if ("/test" in path or path.startswith("tests/")
                      or "_test" in os.path.basename(path)) else "N"
    is_artifact = "N"
    if ("node_modules/" in path or "/scratch/" in path or "/.artifact_build/" in path
            or ext in {"xlsx", "parquet", "db", "sqlite", "pkl", "log", "ndjson",
                       "wasm", "bcmap", "pfb", "map", "bmp", "ttf"}):
        is_artifact = "Y"
    is_backup = "Y" if (path.split("/")[0] in ARCHIVE_ROOTS
                        or ".bak" in path or "_backup" in path) else "N"

    if st == "D":
        ws, grp, inc = "CLEANUP", "G02", "Y"
        reason = "tracked archive/attic/backup snapshot already deleted in the working tree; content remains recoverable at 00baa2b and tag avs-baseline-20260906"
    else:
        ws, grp = classify(path)
        if grp == "EXCLUDE":
            inc = "N"
            reason = next(r for p, _, r in EXCL_PREFIX if path.startswith(p))
        elif grp == "G-UNK":
            inc = "N"
            reason = "UNKNOWN - module is referenced by no other file and has no test; needs ACK"
        else:
            inc = "Y"
            reason = "code, test, contract or audit document belonging to workstream " + ws
    rows.append([path, st, size, mtime, ext, is_test, is_artifact, is_backup,
                 "N", ws, grp, inc, reason])

rows.sort(key=lambda r: (r[10], r[0]))
with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["path", "status", "size_bytes", "last_modified", "extension",
                "is_test", "is_data_or_artifact", "is_backup", "is_secret_risk",
                "workstream_guess", "commit_group", "include", "reason"])
    w.writerows(rows)

# ------------------------------------------------------------------- summary
from collections import Counter
g = Counter(r[10] for r in rows)
inc = Counter(r[11] for r in rows)
print("rows:", len(rows))
print("include Y/N:", dict(inc))
for k in sorted(g):
    print(f"  {k:8s} {g[k]:5d}")
