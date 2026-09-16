"""p11_B_b5_silent_defaults: REQ-WP1-04 / NFR-03. Read-only.
(1) random.seed(20260912) -> choose 5 of the 9 sites in audit/silent_defaults_inventory.md (table row order).
(2) For every site print file:line quotes of the disposition tokens so the 5 chosen can be verified.
(3) Grep the named REQ-WP1-04 sites and the monetisability/rate/dividend/volatility/spread/target/probability paths for
    `or 0.0`, `default=0`, `fillna(0)`, `.get(..., 0)` patterns; list per file counts (what the inventory omits).
Output: p11_B_b5_silent_defaults.txt, p11_B_b5_silent_defaults_grep.csv"""
import os, re, sys, random
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
lines = []


def say(s):
    print(s); lines.append(s)


SITES = [
    ("S1", "canonical_data/dynamic_options_production.py rate", "canonical_data/dynamic_options_production.py", [r"MarketRateObservation", r"RATE_UNAVAILABLE", r"ev3_rate_used"]),
    ("S2", "canonical_data/dynamic_options_production.py dividend", "canonical_data/dynamic_options_production.py", [r"dividend_yield_available", r"dividend = dividend_raw"]),
    ("S3", "layer3_forward_variance.py failed forecast", "layer3_forward_variance.py", [r"checkpoint_fields", r"legacy_deprecated", r"None if self\.error"]),
    ("S4", "trigger_layer.py expected move", "trigger_layer.py", [r"expected_move_10d_fraction", r"l3_expected_move_6_10d\"\)", r"/ 100\.0"]),
    ("S5", "contracts/opportunity_tier.py spread", "contracts/opportunity_tier.py", [r"resolve_spread", r"FRACTION_OF_MID"]),
    ("S6", "canonical_data/dynamic_options_valuation.py quote time", "canonical_data/dynamic_options_valuation.py", [r"MISSING_PROVIDER_QUOTE_TIMESTAMP"]),
    ("S7", "domain/contract_economics_v2.py target/IV/quote", "domain/contract_economics_v2.py", [r"NOT_EVALUATED_DATA_MISSING", r"DATA_DEFECT"]),
    ("S8", "domain/capacity_suggestion.py multiplier/budget", "domain/capacity_suggestion.py", [r"CONFIG_UNAVAILABLE", r"100"]),
    ("S9", "DOI probability outputs", "canonical_data/dynamic_options_production.py|domain/dynamic_options_probability.py|canonical_data/dynamic_options_valuation.py", [r"DETERMINISTIC_UTILITY", r"ranking_score_kind"]),
]
random.seed(20260912)
chosen = sorted(random.sample(range(len(SITES)), 5))
say(f"random.seed(20260912); random.sample(range(9), 5) -> indices {chosen} -> sites {[SITES[i][0] for i in chosen]}: {[SITES[i][1] for i in chosen]}")
for idx, (sid, label, files, pats) in enumerate(SITES):
    mark = "CHOSEN" if idx in chosen else "not chosen"
    say(f"--- {sid} [{mark}] {label}")
    for f in files.split("|"):
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            say(f"    {f}: FILE ABSENT"); continue
        src = open(p, encoding="utf-8", errors="replace").read().splitlines()
        for pat in pats:
            hits = [(i + 1, l.strip()) for i, l in enumerate(src) if re.search(pat, l)]
            say(f"    {f} /{pat}/ hits={len(hits)}: " + " | ".join(f"L{n}: {t[:110]}" for n, t in hits[:4]))

say("=== named REQ-WP1-04 sites")
for f, a, b in (("eod_candidate_engine.py", 353, 360), ("eod_candidate_engine.py", 2693, 2698), ("vanguard/ev_engine_v3.py", 443, 446), ("vanguard/ev_engine_v3.py", 638, 641), ("vanguard/ev_engine_v3.py", 571, 572), ("canonical_data/dynamic_options_production.py", 284, 295)):
    src = open(os.path.join(ROOT, f), encoding="utf-8", errors="replace").read().splitlines()
    for n in range(a, b + 1):
        say(f"    {f}:{n}: {src[n-1].rstrip()[:150]}")

say("=== silent-default pattern grep on the named paths (production modules; tests/backups/audit excluded)")
PATS = {"or 0.0": r"\bor 0\.0\b", "or 0)": r"\bor 0\)", "default=0": r"default\s*=\s*0(\.0)?\b", "fillna(0)": r"fillna\(0(\.0)?\)", ".get(x, 0)": r"\.get\([^)]*,\s*0(\.0)?\)", "_flt default 0.0": r"default: float = 0\.0"}
PATH_HINT = re.compile(r"monetis|rate|dividend|vol|spread|target|prob|econom|valuation|budget|tier|ev_engine|ev3|trigger|eod_candidate|execution_gate|morning_gate|lab_control|selected_contract|reachab|layer3|options", re.I)
EXCL = {"tests", "backups", "backup", "audit", "docs", "data", ".git", "__pycache__", "archive", "_archive", "dropbox", "scripts_archive", ".venv", "venv", ".testdeps", "intelligence-lab"}
rows = []
for dp, dn, fn in os.walk(ROOT):
    dn[:] = [d for d in dn if d not in EXCL and not d.startswith(".pytest")]
    for f in fn:
        if not f.endswith(".py"):
            continue
        rel = os.path.relpath(os.path.join(dp, f), ROOT).replace("\\", "/")
        if not PATH_HINT.search(rel):
            continue
        try:
            src = open(os.path.join(dp, f), encoding="utf-8", errors="replace").read().splitlines()
        except Exception:
            continue
        for i, l in enumerate(src):
            s = l.strip()
            if s.startswith("#"):
                continue
            for name, pat in PATS.items():
                if re.search(pat, l):
                    rows.append({"file": rel, "line": i + 1, "pattern": name, "text": s[:140]})
import pandas as pd
df = pd.DataFrame(rows); df.to_csv(os.path.join(ROOT, "audit/td/AVS-TD-001/probes/p11_B_b5_silent_defaults_grep.csv"), index=False)
say(f"  total hits={len(df)} files={df['file'].nunique() if len(df) else 0}")
if len(df):
    say("  per-file counts (top 40):")
    for f, n in df.groupby("file").size().sort_values(ascending=False).head(40).items():
        say(f"    {n:4d}  {f}")
    say("  hits in domain/ and contracts/ (the v2 authority path):")
    for _, r in df[df.file.str.startswith(("domain/", "contracts/"))].iterrows():
        say(f"    {r.file}:{r.line} [{r.pattern}] {r.text}")
open(os.path.join(ROOT, "audit/td/AVS-TD-001/probes/p11_B_b5_silent_defaults.txt"), "w", encoding="utf-8").write("\n".join(lines))
