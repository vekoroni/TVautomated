"""p17 I3 / NFR-08: Annex A config keys vs config/governed_constants_v1.json, plus literal grep.

Part 1: for each Annex A "Config keys introduced" key, locate a matching key in the
governed file (exact or documented rename), and whether the enclosing block carries
an owner field and a version field.  Output p17_IN_governed_constants.csv.
Part 2: grep decision-path modules for assignments/defaults of the governed literal
values next to the governed names.  Output p17_IN_governed_literals.csv.
Read-only.
"""
import csv, json, re
from pathlib import Path

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
OUT = ROOT / "audit/td/AVS-TD-001/probes"
g = json.load(open(ROOT / "config/governed_constants_v1.json", encoding="utf-8-sig"))

def flat(d, p=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from flat(v, p + k + ".")
        else:
            yield p + k, v
F = dict(flat(g))

# annex key -> (annex value, candidate governed path or None)
ANNEX = [
    ("sigma_multiple", "1.5", "contract_economics.sigma_multiple"),
    ("bias_multiplier", "1.0", "volatility_budget.bias_multiplier"),
    ("friction.s_cap", "0.15", "contract_economics.friction_spread_cap"),
    ("friction.model", "friction_model_v1", None),
    ("profit_floor", "0.25", "contract_economics.profit_floor"),
    ("utility.w_flat", "0.5", "contract_economics.utility_flat_weight"),
    ("iv_stress", "[0.8,1.0,1.2]", "contract_economics.iv_stress"),
    ("hysteresis.margin_abs", "0.05", "preferred_contract.margin_abs"),
    ("hysteresis.margin_rel", "0.10", "preferred_contract.margin_relative"),
    ("freshness_minutes", "15", None),
    ("clock_skew_tolerance_minutes", "5", None),
    ("spread_executable_limit", "0.18", None),
    ("calibration.kappa", "50", None),
    ("calibration.n_min", "200", "outcome_learning.minimum_fit_outcomes"),
    ("calibration.embargo_sessions", "20", "outcome_learning.purge_embargo_sessions"),
    ("calibration.gate.coverage", "0.60", "outcome_learning.minimum_coverage"),
    ("calibration.gate.ece", "0.10", "outcome_learning.maximum_overall_ece"),
    ("calibration.gate.ece_stratum", "0.15", "outcome_learning.maximum_stratum_ece"),
    ("calibration.gate.n_stratum", "100", "outcome_learning.minimum_stratum_outcomes"),
    ("calibration.gate.brier_skill_min_exclusive", "0.0", "outcome_learning.require_positive_brier_skill"),
    ("calibration.gate.roc_auc_min_exclusive", "0.50", "outcome_learning.require_target_roc_auc_above"),
    ("calibration.gate.top_quintile_lift_min_exclusive", "1.0", "outcome_learning.require_top_quintile_lift_above"),
    ("vol_validation.minimum_validation_n", "200", None),
    ("vol_validation.pass.ratio", "[0.90,1.10]", None),
    ("vol_validation.pass.coverage", "[0.60,0.76]", None),
    ("provider_completeness.normal_chain_fraction", "0.95", "provider_completeness.normal_chain_fraction"),
    ("provider_completeness.official_close_fraction", "0.99", "provider_completeness.official_close_fraction"),
    ("provider_completeness.per_chain_thresholds", "replay-approved", "provider_completeness.minimum_session_date_coverage"),
    ("refresh_window", "09:35-09:45 ET", None),
]
OWNER = re.compile(r"owner", re.I)
rows = []
for key, aval, gpath in ANNEX:
    present = gpath in F if gpath else False
    block = gpath.split(".")[0] if gpath else ""
    bkeys = [k for k in F if k.startswith(block + ".")] if block else []
    owner_keys = [k for k in bkeys if OWNER.search(k)]
    ver_keys = [k for k in bkeys if k.endswith("version")]
    rows.append({
        "annex_key": key, "annex_value": aval, "governed_path": gpath or "", "present": present,
        "exact_name": bool(gpath) and gpath.split(".")[-1] == key.split(".")[-1],
        "governed_value": json.dumps(F.get(gpath)) if present else "",
        "value_matches": present and str(F.get(gpath)).replace(" ", "") in (aval, aval.rstrip("0"), str(float(aval)) if re.fullmatch(r"[0-9.]+", aval) else aval),
        "block_owner_fields": ";".join(f"{k}={F[k]}" for k in owner_keys),
        "key_specific_owner": any(k.split(".")[-1].startswith(key.split(".")[-1]) for k in owner_keys),
        "block_version": ";".join(f"{k}={F[k]}" for k in ver_keys),
    })
with open(OUT / "p17_IN_governed_constants.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

# Part 2 — literal grep in decision paths
DECISION = [
    "domain/contract_economics_v2.py", "domain/volatility_budget.py", "domain/reachability.py",
    "domain/preferred_contract.py", "domain/provider_finality.py", "canonical_data/provider_finality.py",
    "domain/option_contract_liquidity.py", "domain/option_liquidity_execution_guard.py",
    "domain/outcome_learning.py", "canonical_data/outcome_learning.py", "domain/calibration.py",
    "contracts/selected_contract_economics.py", "morning_gate.py", "execution_gate.py",
    "canonical_data/dynamic_options_production.py", "canonical_data/dynamic_options_valuation.py",
    "canonical_data/dynamic_options_ranking.py", "domain/dynamic_options_ranking.py",
    "domain/deterministic_option_valuation.py", "vanguard/ev_engine_v3.py", "eod_candidate_engine.py",
    "contracts/options_liquidity_execution_guard.py", "domain/long_option_execution.py",
]
extra = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "domain").glob("*.py")
         if re.search(r"preferred|hysteresis|friction|calibrat|scenario", p.name)]
DECISION = sorted(set(DECISION + extra))
NAMES = r"sigma_multiple|SIGMA_MULTIPLE|profit_floor|PROFIT_FLOOR|s_cap|spread_cap|SPREAD_CAP|max_model_spread|w_flat|flat_weight|margin_abs|margin_rel|MARGIN|iv_stress|IV_STRESS|normal_chain_fraction|official_close_fraction|fresh|FRESH|clock_skew|spread_executable|SPREAD_LIMIT|max_spread|MAX_SPREAD|kappa|n_min|embargo|min_coverage|ece|hysteresis|HYSTERESIS|refresh_window|bias_multiplier"
LIT = r"(?<![\w.])(1\.5|0\.15|0\.18|0\.25|0\.30?|0\.5|0\.05|0\.10?|0\.95|0\.99|0\.8|1\.2|15|50|200|20|0\.60?)(?![\w.])"
pat = re.compile(rf"({NAMES})\w*\s*(:\s*\w+\s*)?=\s*[^=]*?{LIT}|{LIT}\s*(#.*)?$" )
pat_named = re.compile(rf"\b\w*({NAMES})\w*\b[^\n]*?[=:(,]\s*{LIT}")
hits = []
for f in DECISION:
    p = ROOT / f
    if not p.exists():
        hits.append({"file": f, "line": "", "match": "", "code": "FILE_ABSENT"}); continue
    for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        s = ln.strip()
        if s.startswith("#") or not s:
            continue
        m = pat_named.search(ln)
        if m:
            hits.append({"file": f, "line": i, "match": m.group(0)[:80], "code": s[:160]})
with open(OUT / "p17_IN_governed_literals.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["file", "line", "match", "code"]); w.writeheader(); w.writerows(hits)
summary = {
    "annex_keys": len(rows), "present": sum(r["present"] for r in rows),
    "present_exact_name": sum(r["present"] and r["exact_name"] for r in rows),
    "absent": [r["annex_key"] for r in rows if not r["present"]],
    "present_with_key_specific_owner": [r["annex_key"] for r in rows if r["present"] and r["key_specific_owner"]],
    "present_with_any_block_owner": sum(bool(r["block_owner_fields"]) for r in rows if r["present"]),
    "present_with_block_version": sum(bool(r["block_version"]) for r in rows if r["present"]),
    "decision_path_files": DECISION,
    "literal_hits": len([h for h in hits if h["line"]]),
    "literal_hit_files": sorted({h["file"] for h in hits if h["line"]}),
    "absent_files": [h["file"] for h in hits if h["code"] == "FILE_ABSENT"],
}
json.dump(summary, open(OUT / "p17_IN_governed_constants_summary.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
for r in rows: print(r["annex_key"], r["present"], r["governed_value"], r["block_owner_fields"][:60], r["block_version"])
