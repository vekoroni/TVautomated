"""p10_A_source_grep.py -- Track A / A5 (REQ-WP0-04 `_utc_now` on quote-timestamp paths) and
REQ-WP0-01/03/05 source vocabulary. Read-only regex walk over production .py files
(excludes tests/, audit/, quarantine/, .testdeps/, data/, dropbox/, venv-like dirs).
Output: probes/p10_A_source_grep_out.json (and stdout)
"""
import os, re, json, subprocess

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_source_grep_out.json")
# backups/ holds dated pre-change copies (REQ-WP0-07 litter); it is NOT production and is scanned separately below
EXCLUDE_DIRS = {"tests", "test", "audit", "quarantine", ".testdeps", "data", "dropbox", ".git", "__pycache__", "venv", ".venv", "env", "node_modules", "site-packages", "backups"}
NOW_RE = re.compile(r"_utc_now\s*\(|datetime\.now\s*\(|utcnow\s*\(|_now_utc\s*\(|now_utc\s*\(|Timestamp\.now\s*\(|Timestamp\.utcnow\s*\(")
QUOTE_TS_RE = re.compile(r"quote_as_of|quote_provider_timestamp_utc|quote_timestamp|provider_timestamp|quote_fetch_timestamp|observed_at|contract_quote_timestamp|selected_quote_timestamp|live_contract_quote_timestamp|monetisability_quote_timestamp|current_quote_timestamp|morning_quote_timestamp", re.I)
VOCAB_RE = re.compile(r"PREOPEN_THESIS_CHECK|POSTOPEN_CONTRACT_REFRESH|NORMAL_COMPLETED_SESSION|FORCED_INTRASESSION|run_condition|baseline_eligible|provider_completeness_evidence|code_identity|config_identity|operator_mode|macro_packet_id|quote_provider_timestamp_utc|quote_fetch_timestamp_utc|quote_source_dataset_id|CONTRACT_QUOTE_UNAVAILABLE|EXECUTION_QUOTE_UNAVAILABLE|missing_provider_timestamp|quote_timestamp_histogram|by_session_date|by_hour")
KEY_FILES = ["morning_gate.py", "domain/option_contract_liquidity.py", "canonical_data/dynamic_options_bridge.py", "canonical_data/dynamic_options_valuation.py",
             "domain/run_planning.py", "orchestrator/dynamic_dispatcher.py", "intelligent_orchestrator.py", "domain/provider_finality.py",
             "canonical_data/option_liquidity_lifecycle.py", "canonical_data/dynamic_options_production.py", "contracts/lab_control.py", "execution_gate.py"]


def prod_files():
    for dp, dns, fns in os.walk(ROOT):
        rel = os.path.relpath(dp, ROOT)
        parts = set(rel.split(os.sep)) if rel != "." else set()
        if parts & EXCLUDE_DIRS or any(p.startswith(".pytest") or p.startswith("pip-") or p.startswith("tmp") for p in parts):
            dns[:] = []
            continue
        dns[:] = [d for d in dns if d not in EXCLUDE_DIRS and not d.startswith(".pytest") and not d.startswith("pip-") and not d.startswith("tmp")]
        for f in fns:
            if f.endswith(".py") and not f.startswith("test_") and not f.endswith(".bak"):
                yield os.path.join(dp, f)


def main():
    now_hits = []       # every now-call in production code
    now_quote_hits = [] # now-call within +/-3 lines of a quote-timestamp token, or same line
    vocab_hits = {}
    files = list(prod_files())
    for path in files:
        try:
            lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        except Exception:
            continue
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for i, ln in enumerate(lines, 1):
            if NOW_RE.search(ln):
                now_hits.append((rel, i, ln.strip()[:160]))
                ctx = "\n".join(lines[max(0, i - 4):i + 3])
                same_line = bool(QUOTE_TS_RE.search(ln))
                near = bool(QUOTE_TS_RE.search(ctx))
                if same_line or near:
                    now_quote_hits.append({"file": rel, "line": i, "text": ln.strip()[:200], "same_line": same_line,
                                           "context": [f"{j}: {lines[j-1].rstrip()[:180]}" for j in range(max(1, i - 3), min(len(lines), i + 3) + 1)]})
            if VOCAB_RE.search(ln) and (rel in KEY_FILES or any(rel.endswith(k) for k in KEY_FILES) or rel.startswith(("domain/", "orchestrator/", "canonical_data/", "scripts/release", "contracts/"))):
                for m in VOCAB_RE.findall(ln):
                    vocab_hits.setdefault(m, []).append(f"{rel}:{i}: {ln.strip()[:140]}")
    key_status = {k: ("PRESENT" if os.path.exists(os.path.join(ROOT, k)) else "ABSENT") for k in KEY_FILES}
    # separate scan of backups/ for the legacy `quote_as_of ... or _utc_now()` fallback (litter evidence only)
    backups_fallback = []
    bdir = os.path.join(ROOT, "backups")
    if os.path.isdir(bdir):
        for dp, dns, fns in os.walk(bdir):
            for f in fns:
                if f.endswith(".py"):
                    p = os.path.join(dp, f)
                    try:
                        for i, ln in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
                            if "quote_as_of" in ln and re.search(r"\bor\s+_utc_now\(", ln):
                                backups_fallback.append(f"{os.path.relpath(p, ROOT).replace(os.sep, '/')}:{i}")
                    except Exception:
                        pass
    backups_tracked = subprocess.run(["git", "ls-files", "backups"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    # specific: morning_gate.py:1891 region and the `or _utc_now()` pattern anywhere
    or_now = [(f, i, t) for f, i, t in now_hits if re.search(r"\bor\s+_utc_now\(|\bor\s+datetime\.now\(|\bor\s+utcnow\(", t)]
    out = {"n_prod_files_scanned": len(files), "n_now_hits_total": len(now_hits),
           "now_hits_by_file": {}, "now_hits_near_quote_timestamp": now_quote_hits,
           "or_now_fallback_pattern": or_now, "vocab_hits": {k: v[:40] for k, v in vocab_hits.items()}, "vocab_counts": {k: len(v) for k, v in vocab_hits.items()},
           "key_files": key_status,
           "backups_quote_as_of_or_utc_now_hits": backups_fallback, "backups_git_tracked_files": len(backups_tracked)}
    for f, i, t in now_hits:
        out["now_hits_by_file"].setdefault(f, []).append(f"{i}: {t}")
    print("files scanned", len(files), "now-hits", len(now_hits), "near-quote-ts", len(now_quote_hits), "or-now fallback", len(or_now))
    for h in now_quote_hits:
        print("--", h["file"], h["line"], "same_line=", h["same_line"]); print("   " + "\n   ".join(h["context"]))
    print("OR-NOW:", or_now)
    print("BACKUPS quote_as_of-or-_utc_now hits:", len(backups_fallback), backups_fallback[:20], "backups tracked files:", len(backups_tracked))
    print("KEY FILES:", key_status)
    print("VOCAB COUNTS:", out["vocab_counts"])
    for k, v in vocab_hits.items():
        print("##", k); [print("   ", x) for x in v[:25]]
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
