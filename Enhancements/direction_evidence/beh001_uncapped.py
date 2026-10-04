"""BEH-001 uncapped evaluation (rule EVALUATION, no fixed holding window).

Fixed before results are read:
- Engine: analyse_ticker on bars up to each cut (monthly, weekly, daily; no
  intraday history exists for these dates). Forward bars never enter it.
- DETECTED directed candidates: follow daily closes after the cut until a close
  beyond the trigger level (TRIGGER_FIRST) or beyond the invalidation level
  (INVALIDATION_FIRST); research limit 250 sessions, else UNRESOLVED.
  Random-walk baseline per candidate = d_invalidation / (d_trigger + d_invalidation).
- ACTIVATED directed candidates: risk unit R = log distance from the cut close to
  the invalidation level. Success = a close one R beyond the cut close in the
  candidate direction before a close beyond invalidation (baseline 0.5 for a
  driftless walk). The opposite-direction version with the same R is also
  recorded to expose drift.
- Time to resolution (sessions) recorded for every resolved candidate.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dir002_replay import read_bars, select_tickers, trading_calendar  # noqa: E402
from domain.structure_behaviour.engine import analyse_ticker  # noqa: E402
from domain.structure_behaviour.policy import load_policy  # noqa: E402

LIMIT = 250


def race(close, start, up, first_level, second_level):
    """First close beyond first_level (in direction) vs beyond second_level (against)."""
    for j in range(start + 1, min(len(close), start + 1 + LIMIT)):
        c = close[j]
        if (c < second_level) if up else (c > second_level):
            return "SECOND", j - start
        if (c > first_level) if up else (c < first_level):
            return "FIRST", j - start
    return ("UNRESOLVED" if len(close) - 1 - start >= LIMIT else "CENSORED"), None


def _worker(args):
    ticker, cuts = args
    policy = load_policy()
    frame = read_bars(ticker)
    if frame.empty:
        return []
    close = frame["close"].to_numpy()
    position = {d: i for i, d in enumerate(frame["date"].dt.strftime("%Y-%m-%d"))}
    out = []
    for cut in cuts:
        i = position.get(cut)
        if i is None or i < 260:
            continue
        result = analyse_ticker(ticker, frame.iloc[: i + 1].reset_index(drop=True), None, policy,
                                intraday_status="HISTORICAL_REPLAY")
        c0 = close[i]
        for cand in result["candidates"]:
            if cand["Direction"] not in {"BULL", "BEAR"} or cand["Trigger_Level"] is None:
                continue
            up = cand["Direction"] == "BULL"
            trig, inv = cand["Trigger_Level"], cand["Invalidation_Level"]
            row = {"ticker": ticker, "cut": cut, "tf": cand["Timeframe"], "scope": cand["Structure_Scope"],
                   "type": cand["Signal_Type"], "dir": cand["Direction"], "state": cand["Signal_State"]}
            if cand["Signal_State"] == "DETECTED":
                dt = math.log(trig / c0) if up else math.log(c0 / trig)
                di = math.log(c0 / inv) if up else math.log(inv / c0)
                if dt <= 0 or di <= 0:
                    continue
                res, t = race(close, i, up, trig, inv)
                row.update(kind="DETECTED", result=res, sessions=t, baseline=di / (dt + di))
            elif cand["Signal_State"] == "ACTIVATED":
                r = math.log(c0 / inv) if up else math.log(inv / c0)
                if r <= 0:
                    continue
                target = c0 * math.exp(r) if up else c0 * math.exp(-r)
                res, t = race(close, i, up, target, inv)
                opp_target = c0 * math.exp(-r) if up else c0 * math.exp(r)
                opp_inv = c0 * math.exp(r) if up else c0 * math.exp(-r)
                ores, _ = race(close, i, not up, opp_target, opp_inv)
                row.update(kind="ACTIVATED", result=res, sessions=t, risk_log=r, opposite=ores)
            else:
                continue
            out.append(row)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", type=int, default=500)
    p.add_argument("--start", default="2022-09-01")
    p.add_argument("--end", default="2026-09-29")
    p.add_argument("--step", type=int, default=10)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    cuts = [d for d in trading_calendar() if a.start <= d <= a.end][:: a.step]
    with ProcessPoolExecutor(max_workers=a.workers) as pool, open(a.out, "w", encoding="utf-8") as fh:
        for n, rows in enumerate(pool.map(_worker, [(t, cuts) for t in select_tickers(a.tickers)], chunksize=2), 1):
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            if n % 100 == 0:
                print(f"tickers {n}", flush=True)


if __name__ == "__main__":
    main()
