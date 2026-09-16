"""p14_EH_e5_backoff: Track E5. Build 10 LearningStratum keys, call backoff_chain(),
check which ALG-09 lineage fields are present (match_level, exact_n, parent_n,
shrinkage_weight, match_dims_used) and whether any production function computes the
shrunk estimate p = (n_exact*p_exact + kappa*p_parent)/(n_exact+kappa). Also searches
config and source for a kappa. Output: p14_EH_e5_backoff_out.json
"""
import json, os, sys, re, inspect
ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", "..", "..", ".."))
sys.path.insert(0, REPO)
import domain.outcome_learning as dol
from domain.outcome_learning import LearningStratum
KAPPA = 50
keys = [
    ("ACCUMULATION", "EARLY", "LOW", "CALL", "1-5", 10, 0.40, 0.30), ("ACCUMULATION", "EARLY", "MID", "CALL", "6-10", 120, 0.45, 0.33),
    ("MARKUP", "LATE", "HIGH", "CALL", "11-20", 0, 0.0, 0.31), ("DISTRIBUTION", "EARLY", "LOW", "PUT", "1-5", 250, 0.36, 0.30),
    ("DISTRIBUTION", "MID", "MID", "PUT", "6-10", 50, 0.50, 0.32), ("MARKDOWN", "LATE", "HIGH", "PUT", "11-20", 5, 0.80, 0.29),
    ("", "", "", "CALL", "1-5", 30, 0.20, 0.30), ("REACCUMULATION", "", "LOW", "PUT", "6-10", 199, 0.34, 0.30),
    ("MARKUP", "MID", "", "CALL", "6-10", 1000, 0.41, 0.33), ("MARKDOWN", "EARLY", "MID", "PUT", "11-20", 75, 0.28, 0.29),
]
REQUIRED = ("match_level", "exact_n", "parent_n", "shrinkage_weight", "match_dims_used")
rows = []
for h, ph, cb, d, hb, n_exact, p_exact, p_parent in keys:
    st = LearningStratum(hidden_state_label=h, phase=ph, compression_bucket=cb, direction=d, hold_bucket=hb)
    chain = st.backoff_chain()
    level0 = dict(chain[0])
    p_hat = (n_exact * p_exact + KAPPA * p_parent) / (n_exact + KAPPA)
    w = KAPPA / (n_exact + KAPPA)
    rows.append({"key": f"{h or 'UNAVAILABLE'}|{ph or 'UNAVAILABLE'}|{cb or 'UNAVAILABLE'}|{d}|{hb}", "chain_len": len(chain),
                 "match_levels": [c["match_level"] for c in chain], "level0_keys": sorted(level0),
                 "fields_present": {f: f in level0 for f in REQUIRED},
                 "chain_dims": [sorted(k for k in c if k != "match_level") for c in chain],
                 "synthetic": {"n_exact": n_exact, "p_exact": p_exact, "p_parent": p_parent},
                 "my_shrunk_p_hat_kappa50": round(p_hat, 6), "my_shrinkage_weight_kappa50": round(w, 6),
                 "production_p_hat": None})
src = inspect.getsource(dol)
cfg = json.load(open(os.path.join(REPO, "config", "governed_constants_v1.json"), encoding="utf-8-sig"))
def find_keys(obj, pat, path=""):
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if re.search(pat, k, re.I): found.append(path + "/" + k)
            found += find_keys(v, pat, path + "/" + k)
    return found
out = {
    "kappa_in_domain_outcome_learning_source": bool(re.search(r"kappa|shrink", src, re.I)),
    "functions_in_domain_outcome_learning": [n for n, o in inspect.getmembers(dol, inspect.isfunction) if o.__module__ == dol.__name__],
    "config_keys_matching_kappa_or_n_min_or_calibration": find_keys(cfg, r"kappa|n_min|calibration"),
    "backoff_chain_order_matches_annex": all(r["chain_dims"] == [
        ["compression_bucket", "direction", "hidden_state_label", "hold_bucket", "phase"],
        ["direction", "hidden_state_label", "hold_bucket", "phase"],
        ["direction", "hidden_state_label", "hold_bucket"],
        ["direction", "hold_bucket"], ["direction"]] for r in rows),
    "match_level_type": type(rows[0]["match_levels"][0]).__name__,
    "fields_present_on_all_10": {f: all(r["fields_present"][f] for r in rows) for f in REQUIRED},
    "unavailable_retained_not_dropped": all("UNAVAILABLE" in json.dumps(LearningStratum("", "", "", "CALL", "1-5").backoff_chain()[0]) for _ in [0]),
    "rows": rows,
}
json.dump(out, open(os.path.join(ROOT, "p14_EH_e5_backoff_out.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1)); print(json.dumps(rows[:2], indent=1))
