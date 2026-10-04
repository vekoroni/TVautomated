"""BEH-001 corrected evaluation, stage A: candidates at each replay cut (A2-1, Part 4).

Fixed before results are read:
- Engine: analyse_ticker on completed daily bars up to each cut (monthly, weekly and
  daily readings; no intraday history exists for these dates). Forward bars never enter it.
- Every directed candidate (BULL/BEAR, DETECTED or ACTIVATED at the cut) is written with
  its levels, outcome definition, age and parent, plus the ticker's own-timeframe ATR(14)
  at the cut (simple mean true range, the C12 convention).
- Population split: Discovery's option-motivated eligibility at the cut is replicated
  from avshunter_discovery_ULTIMATE.py (price 5-500, 20-bar volume >= 500k, ADV >= $2.5M,
  ATR(14) >= $0.40, ATR >= 1% of price, >= 30 bars). ELIGIBLE rows are the original
  population; INELIGIBLE rows are newly admitted by R-01. Tier and horizon drops need the
  full Discovery scan and are not replicated here.
Stage B (beh001_eval_v2.py) scores these rows with the C12 outcome scorer.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dir002_replay import read_bars, select_tickers, trading_calendar  # noqa: E402
from domain.structure_behaviour.engine import analyse_ticker, resample_daily  # noqa: E402
from domain.structure_behaviour.policy import load_policy  # noqa: E402

ELIGIBILITY = {"min_bars": 30, "min_price": 5.0, "max_price": 500.0, "min_avg_vol20": 500_000,
               "min_adv_dollars": 2_500_000, "min_atr_dollars": 0.40, "min_atr_pct": 1.0}
TIMEFRAMES = {"1d": None, "1w": "W-FRI", "1mo": "ME"}


def _atr(frame: pd.DataFrame, period: int = 14) -> float | None:
    if frame is None or len(frame) <= period:
        return None
    high, low, close = (frame[c].to_numpy(float) for c in ("high", "low", "close"))
    tr = np.maximum.reduce([high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])])
    value = float(tr[-period:].mean())
    return value if value > 0 else None


def eligibility(frame: pd.DataFrame) -> str:
    e = ELIGIBILITY
    if len(frame) < e["min_bars"]:
        return "ELIG_INSUFFICIENT_BARS"
    px = float(frame["close"].iloc[-1])
    if not (e["min_price"] <= px <= e["max_price"]):
        return "ELIG_PRICE_RANGE"
    vol20 = float(frame["volume"].tail(20).mean())
    if vol20 < e["min_avg_vol20"]:
        return "ELIG_AVG_VOLUME"
    atr = _atr(frame) or 0.0
    if px * vol20 < e["min_adv_dollars"]:
        return "ELIG_ADV_DOLLARS_OPTION_PROXY"
    if atr < e["min_atr_dollars"]:
        return "ELIG_ATR_DOLLARS_OPTION_PROXY"
    if atr / px * 100 < e["min_atr_pct"]:
        return "ELIG_ATR_PCT_OPTION_PROXY"
    return "ELIGIBLE"


def _worker(args):
    ticker, cuts = args
    policy = load_policy()
    try:
        frame = read_bars(ticker)
    except Exception:
        return []
    if frame.empty:
        return []
    position = {d: i for i, d in enumerate(frame["date"].dt.strftime("%Y-%m-%d"))}
    out = []
    for cut in cuts:
        i = position.get(cut)
        if i is None or i < 260:
            continue
        history = frame.iloc[: i + 1].reset_index(drop=True)
        try:
            result = analyse_ticker(ticker, history, None, policy, intraday_status="HISTORICAL_REPLAY")
        except Exception as exc:  # the engine never raises; record if it ever does
            out.append({"ticker": ticker, "cut": cut, "engine_error": type(exc).__name__})
            continue
        elig = eligibility(history)
        atr = {}
        for tf, rule in TIMEFRAMES.items():
            atr[tf] = _atr(history if rule is None else resample_daily(history, rule))
        close = float(history["close"].iloc[-1])
        for c in result["candidates"]:
            if c["Direction"] not in {"BULL", "BEAR"} or c["Signal_State"] not in {"DETECTED", "ACTIVATED"}:
                continue
            if c["Timeframe"] not in TIMEFRAMES or c["Trigger_Level"] is None:
                continue
            out.append({"ticker": ticker, "cut": cut, "close": close, "eligibility": elig,
                        "tf": c["Timeframe"], "scope": c["Structure_Scope"], "type": c["Signal_Type"],
                        "dir": c["Direction"], "state": c["Signal_State"], "id": c["Candidate_ID"],
                        "trigger": c["Trigger_Level"], "invalidation": c["Invalidation_Level"],
                        "outcome": c["Outcome_Level"], "outcome_definition": c["Outcome_Definition"],
                        "age_bars": c["Age_Bars"], "parent": c["Parent_Candidate_ID"],
                        "atr_tf": atr.get(c["Timeframe"])})
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", type=int, default=500)
    p.add_argument("--offset", type=int, default=0, help="skip the first N panel tickers (holdout panel)")
    p.add_argument("--start", default="2022-09-01")
    p.add_argument("--end", default="2026-09-29")
    p.add_argument("--step", type=int, default=10)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    cuts = [d for d in trading_calendar() if a.start <= d <= a.end][:: a.step]
    with ProcessPoolExecutor(max_workers=a.workers) as pool, open(a.out, "w", encoding="utf-8") as fh:
        for n, rows in enumerate(pool.map(_worker, [(t, cuts) for t in select_tickers(a.offset + a.tickers)[a.offset:]], chunksize=2), 1):
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            if n % 50 == 0:
                print(f"tickers {n}", flush=True)
                fh.flush()


if __name__ == "__main__":
    main()
