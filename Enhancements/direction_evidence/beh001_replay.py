"""BEH-001 acceptance §8.2/§8.5: point-in-time universe replay of the engine.

Offline; reads canonical completed daily bars read-only. Each cut runs the
engine on bars up to and including that session only. Forward outcomes are
attached for the later evaluation and never feed the engine.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dir002_replay import forward_outcomes, read_bars, reflect_bars, select_tickers, trading_calendar  # noqa: E402
from domain.structure_behaviour.engine import analyse_timeframe, handoff_thesis  # noqa: E402
from domain.structure_behaviour.policy import load_policy  # noqa: E402

KEEP = ("Signal_Type", "Direction", "Signal_State", "Structure_Scope", "Trigger_Level",
        "Invalidation_Level", "Movement_Maturity", "Wyckoff_Phase", "Controller", "Warning")


def _summary(reading: dict) -> dict:
    return {
        "status": reading["Status"], "phase": reading.get("Wyckoff_Phase"),
        "controller": reading.get("Controller"), "local_phase": reading.get("Local_Phase"),
        "local_controller": reading.get("Local_Controller"), "maturity": reading.get("Movement_Maturity"),
        "events": [(e["event"], e["state"], e.get("scope", "CAMPAIGN")) for e in reading.get("events", [])],
        "candidates": [{k: c.get(k) for k in KEEP} for c in reading.get("candidates", [])],
    }


def _worker(args):
    ticker, cuts, mirror = args
    policy = load_policy()
    frame = read_bars(ticker)
    if frame.empty:
        return []
    position = {d: i for i, d in enumerate(frame["date"].dt.strftime("%Y-%m-%d"))}
    rows = []
    for cut in cuts:
        i = position.get(cut)
        if i is None or i < 260:
            continue
        sub = frame.iloc[: i + 1].reset_index(drop=True)
        reading = analyse_timeframe(ticker, sub, "1d", policy)
        row = {"ticker": ticker, "cut_date": cut, **_summary(reading),
               "handoff": handoff_thesis({"1d": reading})["thesis__side"], **forward_outcomes(frame, i)}
        if mirror:
            m = analyse_timeframe(ticker, reflect_bars(sub), "1d", policy)
            row["m"] = _summary(m)
            row["m_handoff"] = handoff_thesis({"1d": m})["thesis__side"]
        rows.append(row)
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", type=int, default=500)
    p.add_argument("--start", default="2022-09-01")
    p.add_argument("--end", default="2026-09-29")
    p.add_argument("--step", type=int, default=10)
    p.add_argument("--mirror", action="store_true")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    cuts = [d for d in trading_calendar() if a.start <= d <= a.end][:: a.step]
    jobs = [(t, cuts, a.mirror) for t in select_tickers(a.tickers)]
    done = 0
    with ProcessPoolExecutor(max_workers=a.workers) as pool, open(a.out, "w", encoding="utf-8") as fh:
        for rows in pool.map(_worker, jobs, chunksize=2):
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
            done += 1
            if done % 50 == 0:
                print(f"tickers {done}/{len(jobs)}", flush=True)


if __name__ == "__main__":
    main()
