"""Item 10.1: build config/setup_rates_v1.json from the eval_v5 / eval_v5_holdout duration records (the evidence
behind the lane table) and compare with the lane table's pooled rates. Writes the config table and a JSON receipt."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from domain.setup_calibration import build_setup_rates  # noqa: E402

E = ROOT / "Enhancements/outcomes/beh001"


def load(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("test") in ("OUTCOME", "OUTCOME_FROM_DETECTION"):
                yield r


table = build_setup_rates(list(load(E / "eval_v5/duration_records.jsonl")), list(load(E / "eval_v5_holdout/duration_records.jsonl")))
table.update(version="setup_rates_v1", authority="DISPLAY_AND_REPORT_ONLY until ACK switches lane / geometry rates",
             evidence="Enhancements/outcomes/beh001/eval_v5 (original) and eval_v5_holdout (held out) duration records",
             builder="Enhancements/phase7/ot10_setup_rates.py (domain/setup_calibration.py)")
(ROOT / "config/setup_rates_v1.json").write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
lanes = json.loads((ROOT / "config/beh001_lanes_v1.json").read_text(encoding="utf-8"))
by = {(s["timeframe"], s["state"], s["signal_type"]): s for s in table["setups"] if s["direction"] in ("BULL", "BEAR")}
compare = []
for lane in ("lane_a_trade_now", "lane_b_early_entry"):
    for tf, entries in lanes[lane].items():
        if not isinstance(entries, list):
            continue
        for e in entries:
            sides = [s for (t, st, ty), s in by.items() if t == tf and st == e["state"] and ty == e["type"]]
            for s in sides:
                compare.append({"lane": lane[5].upper(), "setup": f"{tf}|{e['type']}|{e['state']}|{s['direction']}",
                                "lane_hit_holdout": e["hit"][1], "within_hold_holdout": s["rate_holdout"],
                                "shrunk_original": s["rate_shrunk"], "n_holdout": s["n_holdout"],
                                "hold_bars": s["hold_bars"], "below_50pct_line": (s["rate_holdout"] or 0) < 0.5})
out = {"calibration": table["calibration"], "setups": len(table["setups"]), "lane_setups_compared": len(compare),
       "lane_setups_below_50pct_within_hold": sum(c["below_50pct_line"] for c in compare), "compare": compare}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k != "compare"}, indent=1))
for c in compare[:40]:
    print(c["lane"], c["setup"], "lane", c["lane_hit_holdout"], "-> within hold", c["within_hold_holdout"], "shrunk", c["shrunk_original"], "n", c["n_holdout"], "hold", c["hold_bars"])
