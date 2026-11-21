"""Read-only stored-run C5/C6/research-EV canary; writes no run artefacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

from canonical_data.session_clock import advance_xnys_sessions
from contracts.expression_candidate_packet import _linked_chain
from contracts.expression_valuation_packet import _research_value
from domain.candidate_expression import enumerate_long_expressions
from domain.descriptive_forecast_handoff import build_descriptive_packet
from domain.research_path_baseline import (
    build_nonoverlapping_relative_paths, open_research_price_database,
    read_current_known_bars,
)
from domain.ticker_forecast import ForecastDirection, ForecastState, TickerForecast


def audit(root: Path, repository: Path, *, limit: int) -> dict:
    run_id = root.name
    meta = json.loads((root / "run_meta.json").read_text(encoding="utf-8-sig"))
    session = meta["dynamic_plan"]["last_completed_session"]
    cutoff = meta["dynamic_plan"]["evidence_cutoff_utc"]
    discovery = root / "discovery" / f"discovery_candidates_ultimate_{run_id}.csv"
    with discovery.open(newline="", encoding="utf-8-sig") as handle:
        source = list(csv.DictReader(handle))
    c5 = build_descriptive_packet(run_id, session, cutoff, source,
                                  discovery_sha256=hashlib.sha256(discovery.read_bytes()).hexdigest())
    options = root / "options" / f"options_intelligence_{run_id}.csv"
    with options.open(newline="", encoding="utf-8-sig") as handle:
        by_ticker = {row["ticker"]: row for row in csv.DictReader(handle)}
    registry = sqlite3.connect(
        f"file:{(repository / 'data/canonical/control_plane.sqlite').as_posix()}?mode=ro", uri=True,
    )
    registry.row_factory = sqlite3.Row
    registry.execute("PRAGMA query_only=ON")
    prices = open_research_price_database(repository / "data/canonical/historical_prices.sqlite")
    states: Counter[str] = Counter()
    examples: dict[str, str] = {}
    checked = 0
    try:
        for claim in c5["rows"]:
            if claim["forecast_state"] != "DESCRIPTIVE_ONLY":
                continue
            if limit and checked >= limit:
                break
            checked += 1
            ticker = claim["ticker"]
            linked = by_ticker.get(ticker)
            if not linked or not linked.get("option_chain_dataset_id"):
                state = "NO_CHAIN_DATASET"
            else:
                try:
                    chain, _ = _linked_chain(
                        registry, linked["option_chain_dataset_id"],
                        ticker=ticker, session=session, cutoff=cutoff,
                    )
                    for item in chain:
                        item["source_run_id"] = run_id
                        if item.get("contract_multiplier") in {None, ""} and str(linked.get("contract_multiplier")) in {"100", "100.0"}:
                            if linked.get("contract_multiplier_source") in {"OCC_STANDARD_100_INFERRED", "OCC_STANDARD_100_OBSERVED"}:
                                item["contract_multiplier"] = 100
                                item["contract_multiplier_source"] = linked["contract_multiplier_source"]
                    forecast = TickerForecast(
                        run_id, claim["forecast_thesis_id"], ticker, session, cutoff,
                        ForecastDirection(claim["forecast_direction"]),
                        ForecastState.DESCRIPTIVE_ONLY, claim["forecast_reference_spot"],
                        claim["forecast_target_spot"], claim["forecast_invalidation_spot"],
                    )
                    candidates = enumerate_long_expressions(
                        forecast, chain,
                        last_exit_date=advance_xnys_sessions(date.fromisoformat(session), 20).isoformat(),
                        expiry_buffer_days=1, max_candidates=20, quote_cutoff_utc=cutoff,
                    )
                    if not candidates.candidates:
                        state = candidates.expression_state
                    else:
                        bars = read_current_known_bars(prices, ticker=ticker,
                                                       evidence_session=session,
                                                       decision_cutoff_utc=cutoff)
                        paths = build_nonoverlapping_relative_paths(ticker, bars)
                        state = _research_value(claim, asdict(candidates.candidates[0]), paths,
                                                evidence_session=session)["state"]
                except Exception as error:
                    state = f"ERROR:{type(error).__name__}:{error}"
            states[state] += 1
            examples.setdefault(state, ticker)
    finally:
        prices.close()
        registry.close()
    return {"run_id": run_id, "checked_descriptive_tickers": checked,
            "source_discovery_rows": len(source), "states": dict(states),
            "first_example_by_state": examples, "authority": "READ_ONLY_RESEARCH_CANARY"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    result = audit(repository / "data" / "output" / "runs" / args.run_id,
                   repository, limit=args.limit)
    print(json.dumps(result, indent=2, sort_keys=True))
