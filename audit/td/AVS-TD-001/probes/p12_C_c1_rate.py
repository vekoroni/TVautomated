"""p12_C_c1_rate.py -- Track C / C1: MarketRateObservation resolution on stored-run macro artefacts (read-only).

Calls canonical_data.market_rate_observation.load_market_rate on the primary and comparison runs'
macro_quant_packet.json and macro_snapshot.json, reports what resolves, whether macro_rates_context
exists with t3m/sofr/fed_funds/rates_data_as_of, counts FAMILY_NOT_VALUED_RATE_UNAVAILABLE in the DOI
reports, and greps audit/avs_fix_002 for families_valued.
"""
from __future__ import annotations
import json, sys, re
from pathlib import Path

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
sys.path.insert(0, str(ROOT))
from canonical_data.market_rate_observation import load_market_rate  # noqa: E402

OUT = Path(__file__).with_suffix(".out.json")
RUNS = {"primary": "20260911_115904", "comparison": "20260910_150045"}
result: dict = {"runs": {}, "audit_families_valued": []}


def _find_nodes(obj, keys, path="$", hits=None):
    if hits is None:
        hits = []
    if isinstance(obj, dict):
        for k in keys:
            if k in obj:
                hits.append((path, k, obj[k] if not isinstance(obj[k], (dict, list)) else f"<{type(obj[k]).__name__}>"))
        for k, v in obj.items():
            _find_nodes(v, keys, f"{path}.{k}", hits)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):
            _find_nodes(v, keys, f"{path}[{i}]", hits)
    return hits


for label, run in RUNS.items():
    rd = ROOT / "data/output/runs" / run
    entry: dict = {}
    for name in ("macro_quant_packet.json", "macro_snapshot.json"):
        p = rd / name
        obs = load_market_rate(p)
        d = obs.to_dict()
        entry[name] = {"exists": p.is_file(), "observation": d}
        if p.is_file():
            payload = json.loads(p.read_text(encoding="utf-8-sig"))
            entry[name]["has_macro_rates_context"] = bool(_find_nodes(payload, ["macro_rates_context"]))
            entry[name]["rate_key_hits"] = [
                (pth, k, str(v)[:80]) for pth, k, v in
                _find_nodes(payload, ["t3m", "sofr", "fed_funds", "fed_funds_rate", "rates_data_as_of"])
            ][:20]
            entry[name]["top_level_keys"] = list(payload.keys())[:40] if isinstance(payload, dict) else str(type(payload))
    doi = rd / "options" / f"dynamic_options_intelligence_{run}.json"
    if doi.is_file():
        rep = json.loads(doi.read_text(encoding="utf-8-sig"))
        entry["doi_report"] = {
            "family_rows": rep.get("family_rows"),
            "assessed_families": rep.get("assessed_families"),
            "counts_by_state": rep.get("counts_by_state"),
        }
    else:
        entry["doi_report"] = None
    result["runs"][label] = entry

# grep audit/avs_fix_002 for families_valued
for p in (ROOT / "audit/avs_fix_002").rglob("*"):
    if p.is_file() and p.suffix.lower() in {".md", ".json", ".txt", ".csv", ".xml"}:
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"families_valued[^\n]{0,80}", txt):
            result["audit_families_valued"].append({"file": str(p.relative_to(ROOT)), "text": m.group(0)})
        for m in re.finditer(r"FAMILY_NOT_VALUED_RATE_UNAVAILABLE[^\n]{0,80}", txt):
            result["audit_families_valued"].append({"file": str(p.relative_to(ROOT)), "text": m.group(0)})

OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(json.dumps(result, indent=2, default=str))
