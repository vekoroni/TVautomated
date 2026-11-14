"""Saved-data benchmark and preview for the crossing scenario (AVS-TRADE-001 design v4 section 12).

Replays the selected contract of every row in a saved Lane B hand-off through domain.crossing_scenario. Offline:
no providers, no pipeline, no database; the hand-off is read only and its hash is recorded. This measures the
ROW-LEVEL scenario (the selected contract, all 12 records). It does not measure the 17-contract shadow set, because
the saved run did not keep candidate quotes and scores; that gap is stated in the output, never filled.

Run:  venv\\Scripts\\python.exe Enhancements\\tradeability\\crossing_scenario_saved_benchmark.py
"""
from __future__ import annotations

import collections
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from domain import crossing_scenario as cs  # noqa: E402
from domain.option_contract_liquidity import quote_tier  # noqa: E402

HANDOFF = ROOT / "data" / "scratch" / "workaround" / "handoff" / "lab_2026-11-12" / "handoff.csv"
OUT = Path(__file__).with_name("CROSSING_SCENARIO_SAVED_BENCHMARK_20261114.json")
MEMORY_SAMPLE_START, MEMORY_SAMPLE_ROWS = 100, 100
ASSESSMENT = "2026-11-11T21:00:00+00:00"            # the close of the evidence session of run 20261111_231951


def strike_of(symbol: str):
    match = re.fullmatch(r".+?\d{6}[CP](\d{8})", str(symbol or "").replace(" ", ""))
    return int(match[1]) / 1000.0 if match else None


def main() -> int:
    raw = HANDOFF.read_bytes()
    rows = pd.read_csv(HANDOFF, keep_default_na=False, dtype=str)
    cfg = cs.crossing_config()
    states, coverage, limits = collections.Counter(), collections.Counter(), collections.Counter()
    tiers = collections.Counter()
    n30, n20, by_frame, timings = [], [], collections.defaultdict(list), []
    arrival_dist = collections.Counter()
    compare = collections.Counter()
    started = time.perf_counter()
    for index, row in enumerate(rows.to_dict("records")):
        if index == MEMORY_SAMPLE_START:                 # memory is traced on a sample only: tracing slows pricing
            tracemalloc.start()
        if index == MEMORY_SAMPLE_START + MEMORY_SAMPLE_ROWS:
            peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
        traced = MEMORY_SAMPLE_START <= index < MEMORY_SAMPLE_START + MEMORY_SAMPLE_ROWS
        t0 = time.perf_counter()
        out = cs.scenario_crossing(
            side=row.get("direction"), mode="EVENING_AT_EVIDENCE", thesis_id=row.get("thesis_id"),
            contract_symbol=row.get("contract_symbol"), thesis_origin_date=row.get("bar_data_asof"),
            origin_spot=row.get("signal_price"), frozen_target_level=row.get("anticipated_level_q50"),
            arrival_sessions_median=row.get("anticipated_sessions_q50") or None,
            arrival_sessions_slow=row.get("anticipated_sessions_q80") or None,
            assessment_instant_utc=ASSESSMENT, quote_timestamp_utc=row.get("selected_quote_timestamp_utc"),
            quote_spot=row.get("signal_price"), strike=strike_of(row.get("contract_symbol")),
            expiry=row.get("expiry") or None, bid=row.get("contract_bid") or None, ask=row.get("contract_ask") or None,
            iv=row.get("contract_iv") or None,
            # The hand-off does not carry thesis_state; every row in it is a published, active thesis.
            thesis_active=True, underlying=row.get("ticker"), rate=row.get("valuation_rate_annual") or None,
            rate_basis="SAVED_HANDOFF", dividend_yield=row.get("valuation_dividend_yield_annual") or None,
            dividend_basis="SAVED_HANDOFF")
        if not traced:
            timings.append(time.perf_counter() - t0)
        states[out["crossing_state"]] += 1
        coverage[out["crossing_covers_slow30_base"]] += 1
        limits[str(out["crossing_search_limit"])] += 1
        tier = quote_tier(row.get("contract_bid") or None, row.get("contract_ask") or None, row.get("contract_oi") or None)
        tiers[tier["tier"] or tier["validity"]] += 1
        slow = pd.to_numeric(row.get("anticipated_sessions_q80"), errors="coerce")
        arrival_dist["no arrival time" if pd.isna(slow) else "1-20" if slow <= 20 else "21-60" if slow <= 60 else "over 60"] += 1
        if out["crossing_n_slow_pace_30"] is not None:
            n30.append(out["crossing_n_slow_pace_30"])
            frame = str(row.get("trade_lane_setup") or "").split("|")[0].strip() or "unknown"
            by_frame[frame].append(out["crossing_n_slow_pace_30"])
            q80 = pd.to_numeric(row.get("anticipated_sessions_q80"), errors="coerce")
            if not pd.isna(q80):
                compare["crossing earlier than q80 arrival" if out["crossing_n_slow_pace_30"] < q80
                        else "crossing at q80 arrival"] += 1
        if out["crossing_n_slow_pace_20"] is not None:
            n20.append(out["crossing_n_slow_pace_20"])
    elapsed = time.perf_counter() - started

    def dist(values):
        s = pd.Series(values)
        return None if s.empty else {"n": int(len(s)), "q25": float(s.quantile(.25)), "median": float(s.median()),
                                     "q75": float(s.quantile(.75)), "max": float(s.max())}

    ts = pd.Series(timings)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    result = {
        "what": "ROW_LEVEL crossing scenario for the selected contract of every saved hand-off row (offline replay)",
        "not_measured": "The 17-contract shadow set: the saved run kept no candidate quotes or scores "
                        "(options/contracts_tested_*.jsonl holds symbol, dte, delta, spread and mid only). "
                        "BENCHMARK_INPUT_GAP, not synthesised.",
        "caveats": ["Hand-off quotes are the Morning's (selected_quote_timestamp_utc); the path is anchored at the "
                    "Evening evidence close. This is a timing benchmark and a preview of states, not run evidence.",
                    "thesis_active is taken as true for every hand-off row (the hand-off carries no thesis_state)."],
        "input": {"file": str(HANDOFF.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest(), "rows": int(len(rows))},
        "source_commit": commit, "config_version": cfg["version"], "search_cap_sessions": cfg["search_cap_sessions"],
        "machine": {"platform": platform.platform(), "python": platform.python_version(), "processor": platform.processor()},
        "timing": {"rows": int(len(rows)), "rows_timed": int(len(ts)), "wall_seconds": round(elapsed, 1),
                   "timing_basis": "untraced rows only; memory traced on a 100-row sample", "seconds_per_row_mean": round(float(ts.mean()), 4),
                   "seconds_per_row_p95": round(float(ts.quantile(.95)), 4), "seconds_per_row_max": round(float(ts.max()), 4),
                   "projected_minutes_for_2800_rows": round(float(ts.mean()) * 2800 / 60, 1),
                   "peak_memory_mb_sample": round(peak / 1e6, 1)},
        "rows_by_slow_arrival_sessions": dict(arrival_dist),
        "state_slow30_base": dict(states.most_common()), "covers_slow30_base": dict(coverage),
        "search_limit": dict(limits), "selected_quote_tier": dict(tiers),
        "crossing_session_slow30": dist(n30), "crossing_session_slow20": dist(n20),
        "crossing_session_slow30_by_timeframe": {k: dist(v) for k, v in sorted(by_frame.items())},
        "crossing_vs_q80_arrival": dict(compare),
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
