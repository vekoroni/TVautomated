r"""Calibrate the volatility runway fallback (B) on recorded outcomes (ACK 7 Oct 2026: "build the calibrated B").

B as first built - the sessions a k-sigma move (k = contract_economics.sigma_multiple = 1.5) needs to reach the setup's
level - covered only 30% of real level hits on the held-out panel (actual time: median 2x, q80 5.9x B). A runway must
work like the evidence q80 (own evidence covers 82-88%). This script learns, per timeframe, the multiplier m such that
B x m is the q80 of actual/B time on the ORIGINAL panel (eval_v4), then measures coverage on the HOLDOUT
(eval_v4_holdout). Daily sigma proxy = ATR(timeframe) / close / 1.25 per own-timeframe bar. Read-only; prints JSON.

    venv\Scripts\python.exe Enhancements\assessment\AVS_LAB_SOURCE_OF_TRUTH_20261006\s2_batch1\calibrate_runway_volatility.py
"""
import json
import math

K = 1.5
BASE = "Enhancements/outcomes/beh001"


def pairs(folder, tf):
    cands = {}
    for line in open(f"{BASE}/{folder}/candidates.jsonl", encoding="utf-8"):
        c = json.loads(line)
        if c.get("tf") == tf and c.get("outcome") and c.get("atr_tf") and c.get("close"):
            cands[(c["ticker"], c["cut"], c["tf"], c["scope"], c["type"], c["dir"])] = c
    out = []
    for line in open(f"{BASE}/{folder}/duration_records.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["test"] not in ("OUTCOME", "OUTCOME_FROM_DETECTION") or r["cause"] != "EVENT":
            continue
        c = cands.get((r["ticker"], r["cut"], r["timeframe"], r["scope"], r["signal_type"], r["direction"]))
        if c is None:
            continue
        move = (1 if r["direction"] == "BULL" else -1) * (c["outcome"] / c["close"] - 1)
        if move > 0:
            out.append((int(r["time_bars"]), max(1, math.ceil((move / (K * c["atr_tf"] / c["close"] / 1.25)) ** 2))))
    return out


result = {}
for tf in ("1d", "1w", "1mo"):
    orig, hold = pairs("eval_v4", tf), pairs("eval_v4_holdout", tf)
    ratios = sorted(t / b for t, b in orig)
    m80 = round(ratios[int(0.8 * (len(ratios) - 1))], 2)
    result[tf] = {"q80_multiplier": m80, "original_events": len(orig), "holdout_events": len(hold),
                  "holdout_coverage": round(sum(t <= math.ceil(b * m80) for t, b in hold) / len(hold), 3)}
print(json.dumps(result, indent=1))
