"""Output-trust item 3 (D2-3, 9 Oct 2026): the sample size behind each lane hit rate in config/beh001_lanes_v1.json.

Lane A: reproduces each hit exactly from the eval_v5 / eval_v5_holdout duration records (hit = EVENT / all records of
the timeframe, state and type; OUTCOME test for ACTIVATED, OUTCOME_FROM_DETECTION for DETECTED; censored = not reached)
and writes n = all records. Lane B: the R2 rule's pooled panel rows from its study (1,068 original / 1,157 held out;
AVS_INVENTED_VALUES_INVENTORY_20261003.md, Lane B study). Fails if a lane A hit does not reproduce.
Run: venv\Scripts\python.exe Enhancements\phase7\lane_hit_n.py [--write]
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "beh001_lanes_v1.json"
LANE_B_N = [1068, 1157]


def load(path):
    counts = collections.Counter()
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["test"] in ("OUTCOME", "OUTCOME_FROM_DETECTION"):
                state = "ACTIVATED" if r["test"] == "OUTCOME" else "DETECTED"
                counts[(r["timeframe"], state, r["signal_type"], r["cause"] == "EVENT")] += 1
    return counts


def main(write: bool) -> None:
    table = json.loads(CFG.read_text(encoding="utf-8"))
    panels = [load(ROOT / "Enhancements/outcomes/beh001" / p / "duration_records.jsonl") for p in ("eval_v5", "eval_v5_holdout")]
    for tf, entries in table["lane_a_trade_now"].items():
        for e in entries:
            n = []
            for counts, hit in zip(panels, e["hit"]):
                ev, miss = counts[(tf, e["state"], e["type"], True)], counts[(tf, e["state"], e["type"], False)]
                assert round(ev / (ev + miss), 3) == round(hit, 3), (tf, e["type"], ev, miss, hit)
                n.append(ev + miss)
            e["n"] = n
            print(tf, e["state"], e["type"], e["hit"], n)
    for tf, entries in table["lane_b_early_entry"].items():
        if isinstance(entries, list):
            for e in entries:
                e["n"] = list(LANE_B_N)
    table["n_basis"] = ("n = records behind each hit (original, held out). Lane A: eval_v5 duration records, reproduced "
                        "exactly (Enhancements/phase7/lane_hit_n.py). Lane B: the R2 rule's pooled panel rows (one hit "
                        "for the three types).")
    table["geometry_justification"] = {
        "approved": "ACK 9 Oct 2026 (output-trust decision 1): GEOMETRY_NOT_JUSTIFIED stays visible and ranked but cannot be GO",
        "measured_hit": "LOWER_OF_PANELS",
        "interval_confidence": 0.95,
        "interval_method": "WILSON",
    }
    if write:
        CFG.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
        print("written", CFG)


if __name__ == "__main__":
    main("--write" in sys.argv)
