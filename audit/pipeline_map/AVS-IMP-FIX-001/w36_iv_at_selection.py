"""AVS-FIX-001 W3.6 — IV at selection vs earlier sessions. Measurement only.

    python audit/pipeline_map/AVS-IMP-FIX-001/w36_iv_at_selection.py <run_id>

THS-001 §3.2 hypothesises an "early lane": that the pipeline systematically
buys options after volatility has already been bid up, and would do better
entering earlier. That is a hypothesis about a number nobody has measured.

For every MONETISABLE row of a completed run, this reads the IV of **the same
OCC contract** from the stored chains of earlier sessions and reports the
distribution of the change. No provider call, no code change, nothing written
back into the run.

Decision rule, fixed before the measurement (AVS-IMP-FIX-001 W3.6): if the
median row is buying IV **>= 20% above** its five-session-earlier level,
recommend the early-lane design. Otherwise recommend against it.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CONTROL_PLANE = REPO / "data" / "canonical" / "control_plane.sqlite"
RUNS = REPO / "data" / "output" / "runs"

#: The lookbacks THS-001 §3.2 asks about, in trading sessions.
LOOKBACKS = (3, 5)
#: The threshold that decides the recommendation. Fixed in advance.
EARLY_LANE_MEDIAN_THRESHOLD_PCT = 20.0


def chain_sessions() -> list[str]:
    connection = sqlite3.connect(f"file:{CONTROL_PLANE}?mode=ro", uri=True)
    rows = connection.execute(
        "SELECT DISTINCT session_date FROM dataset_registry "
        "WHERE dataset_type='OPTION_CHAIN' ORDER BY session_date"
    ).fetchall()
    connection.close()
    return [str(value[0]) for value in rows]


def chain_index(session: str) -> dict[str, Path]:
    connection = sqlite3.connect(f"file:{CONTROL_PLANE}?mode=ro", uri=True)
    rows = connection.execute(
        "SELECT instrument_id, storage_uri FROM dataset_registry "
        "WHERE dataset_type='OPTION_CHAIN' AND session_date=?", (session,)
    ).fetchall()
    connection.close()
    return {str(instrument).upper(): Path(uri) for instrument, uri in rows}


def contract_iv_from_chain(path: Path, symbol: str) -> float | None:
    """IV of one exact OCC symbol in a stored chain payload."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    for entry in payload:
        if str(entry.get("symbol") or "").upper() == symbol:
            value = entry.get("implied_vol")
            try:
                number = float(value)
            except (TypeError, ValueError):
                return None
            if number != number or number <= 0:
                return None
            return number / 100.0 if number > 5.0 else number
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_id")
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args(argv)

    options_path = RUNS / args.run_id / "options" / f"options_intelligence_{args.run_id}.csv"
    if not options_path.exists():
        print(f"options artefact not found: {options_path}", file=sys.stderr)
        return 1
    options = pd.read_csv(options_path, low_memory=False)

    lab_path = (
        RUNS / args.run_id / "intelligence_lab"
        / f"final_opportunity_book_{args.run_id}.csv"
    )
    monetisable_tickers: set[str] = set()
    if lab_path.exists():
        lab = pd.read_csv(lab_path, low_memory=False)
        monetisable_tickers = set(
            lab.loc[
                lab.get("monetisability_state", pd.Series(dtype=str)).eq("MONETISABLE"),
                "ticker",
            ].astype(str).str.upper()
        )

    rows = options[
        options["ticker"].astype(str).str.upper().isin(monetisable_tickers)
        & options.get("recommended_contract", pd.Series(dtype=str)).notna()
        & options.get("contract_iv", pd.Series(dtype=float)).notna()
    ].copy() if monetisable_tickers else pd.DataFrame()

    sessions = chain_sessions()
    run_session: str | None = None
    if "evidence_session_date" in options.columns:
        values = options["evidence_session_date"].dropna().astype(str).str.slice(0, 10)
        if len(values):
            run_session = values.iloc[0]
    if run_session is None and sessions:
        run_session = sessions[-1]

    earlier = [s for s in sessions if s < (run_session or "")]
    # Session N back = the Nth stored chain session before the run's.
    lookback_sessions: dict[int, str | None] = {}
    for back in LOOKBACKS:
        lookback_sessions[back] = earlier[-back] if len(earlier) >= back else None

    indexes = {
        back: (chain_index(session) if session else {})
        for back, session in lookback_sessions.items()
    }

    comparisons: dict[int, list[float]] = {back: [] for back in LOOKBACKS}
    records: list[dict[str, Any]] = []
    unmatched = {back: 0 for back in LOOKBACKS}

    for _, row in rows.iterrows():
        ticker = str(row["ticker"]).upper()
        symbol = str(row["recommended_contract"]).upper().replace("O:", "")
        try:
            iv_now = float(row["contract_iv"])
        except (TypeError, ValueError):
            continue
        if iv_now <= 0:
            continue
        if iv_now > 5.0:
            iv_now = iv_now / 100.0

        record: dict[str, Any] = {
            "ticker": ticker, "symbol": symbol, "iv_at_selection": iv_now,
            "direction": str(row.get("final_direction") or row.get("direction") or ""),
        }
        for back in LOOKBACKS:
            path = indexes[back].get(ticker)
            iv_then = contract_iv_from_chain(path, symbol) if path else None
            if iv_then is None or iv_then <= 0:
                unmatched[back] += 1
                record[f"iv_{back}_sessions_earlier"] = None
                record[f"iv_change_pct_{back}"] = None
                continue
            change = (iv_now - iv_then) / iv_then * 100.0
            comparisons[back].append(change)
            record[f"iv_{back}_sessions_earlier"] = iv_then
            record[f"iv_change_pct_{back}"] = round(change, 4)
        records.append(record)

    def describe(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"n": 0}
        ordered = sorted(values)
        # The mean is reported but never decides: an IV that rose from near
        # zero produces an unbounded percentage change, and a handful of those
        # dominate it. The median is the statistic the rule uses.
        return {
            "n": len(ordered),
            "median_pct": round(statistics.median(ordered), 3),
            "mean_pct": round(statistics.fmean(ordered), 3),
            "mean_is_outlier_sensitive": True,
            "p25_pct": round(ordered[len(ordered) // 4], 3),
            "p75_pct": round(ordered[(3 * len(ordered)) // 4], 3),
            "min_pct": round(ordered[0], 3),
            "max_pct": round(ordered[-1], 3),
            "share_above_20pct": round(
                sum(1 for value in ordered if value >= 20.0) / len(ordered), 4
            ),
        }

    distribution = {back: describe(comparisons[back]) for back in LOOKBACKS}

    five = distribution.get(5, {})
    three = distribution.get(3, {})
    if five.get("n", 0) == 0 and three.get("n", 0) == 0:
        recommendation = "UNDECIDED_INSUFFICIENT_CHAIN_HISTORY"
        rationale = (
            "No selected contract could be matched in any earlier stored "
            "chain. The early-lane question cannot be answered from this "
            "run's stored chains."
        )
    elif five.get("n", 0) == 0:
        # The five-session chain is not stored yet. The three-session lookback
        # is the longest available, and it answers the same question in the
        # same direction; reported as such rather than as "undecided", which
        # would discard a real measurement.
        if three["median_pct"] >= EARLY_LANE_MEDIAN_THRESHOLD_PCT:
            recommendation = "PROVISIONAL_BUILD_EARLY_LANE_CONFIRM_AT_5_SESSIONS"
            rationale = (
                f"No chain is stored five sessions back, so the threshold could "
                f"not be applied as specified. On the longest lookback that does "
                f"exist ({lookback_sessions[3]}, three sessions), the median "
                f"monetisable row is buying IV {three['median_pct']:+.1f}% above "
                f"its earlier level, at or above the "
                f"{EARLY_LANE_MEDIAN_THRESHOLD_PCT:.0f}% threshold. Confirm once "
                "five sessions of chains are stored."
            )
        else:
            recommendation = "DO_NOT_BUILD_EARLY_LANE_ON_AVAILABLE_EVIDENCE"
            rationale = (
                f"No chain is stored five sessions back, so the threshold could "
                f"not be applied as specified. On the longest lookback that does "
                f"exist ({lookback_sessions[3]}, three sessions, n={three['n']}), "
                f"the median monetisable row is buying IV {three['median_pct']:+.1f}% "
                f"against its earlier level and only "
                f"{three['share_above_20pct']:.1%} of rows are {EARLY_LANE_MEDIAN_THRESHOLD_PCT:.0f}% "
                "or more above it. That does not support the premise that the "
                "pipeline systematically buys elevated volatility, and a shorter "
                "lookback biases toward finding a rise, not against it. Recommend "
                "against building the early lane; re-run once five sessions of "
                "chains exist."
            )
    elif five["median_pct"] >= EARLY_LANE_MEDIAN_THRESHOLD_PCT:
        recommendation = "BUILD_EARLY_LANE"
        rationale = (
            f"The median monetisable row is buying IV {five['median_pct']:.1f}% "
            f"above its five-session-earlier level, at or above the "
            f"{EARLY_LANE_MEDIAN_THRESHOLD_PCT:.0f}% threshold fixed in advance."
        )
    else:
        recommendation = "DO_NOT_BUILD_EARLY_LANE"
        rationale = (
            f"The median monetisable row is buying IV {five['median_pct']:.1f}% "
            f"against its five-session-earlier level, below the "
            f"{EARLY_LANE_MEDIAN_THRESHOLD_PCT:.0f}% threshold fixed in advance. "
            "The measurement does not support the premise that the pipeline is "
            "systematically buying elevated volatility."
        )

    report = {
        "run_id": args.run_id,
        "run_session": run_session,
        "chain_sessions_available": sessions,
        "lookback_sessions_used": lookback_sessions,
        "monetisable_rows": len(monetisable_tickers),
        "rows_with_contract_and_iv": len(rows),
        "unmatched_in_earlier_chain": unmatched,
        "distribution": distribution,
        "threshold_pct": EARLY_LANE_MEDIAN_THRESHOLD_PCT,
        "recommendation": recommendation,
        "rationale": rationale,
        "rows": records,
    }

    print("=" * 92)
    print(f"AVS-FIX-001 W3.6 IV at selection - run {args.run_id} "
          f"(session {run_session})")
    print("=" * 92)
    print(f"  chain sessions stored      : {', '.join(sessions)}")
    for back in LOOKBACKS:
        print(f"  {back} sessions earlier         : "
              f"{lookback_sessions[back] or 'NO STORED CHAIN'}")
    print(f"  MONETISABLE rows           : {len(monetisable_tickers)}")
    print(f"  with a contract and an IV  : {len(rows)}")
    for back in LOOKBACKS:
        stats = distribution[back]
        if not stats.get("n"):
            print(f"  vs {back} sessions earlier     : no comparable contract "
                  f"(unmatched {unmatched[back]})")
            continue
        print(f"  vs {back} sessions earlier     : n={stats['n']} "
              f"median={stats['median_pct']:+.1f}% mean={stats['mean_pct']:+.1f}% "
              f"p25={stats['p25_pct']:+.1f}% p75={stats['p75_pct']:+.1f}% "
              f"share>=+20%={stats['share_above_20pct']:.1%}")
    print(f"  threshold                  : median >= "
          f"+{EARLY_LANE_MEDIAN_THRESHOLD_PCT:.0f}% -> build")
    print(f"  RECOMMENDATION             : {recommendation}")
    print(f"  {rationale}")

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        print(f"  json: {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
