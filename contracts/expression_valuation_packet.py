"""Immutable C8 disposition for every C6 expression in the current run.

This production adapter cannot invent a physical-measure path set. Until a
held-out validated C4 packet is available, every exact contract is explicitly
not valued and no legacy EV is copied into the new namespace.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from canonical_data.session_clock import xnys_sessions_between
from contracts.descriptive_forecast_packet import load_descriptive_packet
from domain.option_path_valuation import value_long_option_paths
from domain.vectorized_research_ev import value_research_contract
from domain.research_path_baseline import (
    build_nonoverlapping_relative_paths, open_research_price_database,
    read_current_known_bars,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _research_interval(values: list[float], *, seed: int) -> dict[str, float]:
    sample = np.asarray(values, dtype=np.float64)
    draws = np.random.default_rng(seed).integers(0, len(sample), size=(200, len(sample)))
    means = np.sort(sample[draws].mean(axis=1))
    return {"lower_95": float(means[4]), "upper_95": float(means[195])}


def _research_value(
    claim: dict, candidate: dict, historical_paths: tuple,
    *, evidence_session: str,
) -> dict[str, Any]:
    iv = candidate.get("implied_vol")
    multiplier = candidate.get("contract_multiplier")
    if (iv is None or not isinstance(iv, (int, float)) or not math.isfinite(iv) or iv <= 0
            or not isinstance(multiplier, int) or multiplier <= 0):
        return {"state": "RESEARCH_INPUT_MISSING", "reason": "IV_OR_MULTIPLIER_MISSING"}
    if len(historical_paths) < 12:
        return {"state": "RESEARCH_HISTORY_THIN", "independent_20_session_paths": len(historical_paths)}
    spot = claim["forecast_reference_spot"]
    target = claim["forecast_target_spot"]
    stop = claim["forecast_invalidation_spot"]
    direction = claim["forecast_direction"]
    last_exit = xnys_sessions_between(date.fromisoformat(evidence_session),
                                      date.fromisoformat(candidate["last_exit_date"]))
    expiry_sessions = xnys_sessions_between(date.fromisoformat(evidence_session),
                                            date.fromisoformat(candidate["expiry_date"]))
    if not 1 <= last_exit <= min(20, expiry_sessions):
        return {"state": "RESEARCH_EXIT_CLOCK_INVALID"}
    path_id = hashlib.sha256("|".join(path.path_id for path in historical_paths).encode()).hexdigest()

    common = dict(paths=historical_paths, spot=spot, target=target, stop=stop,
                  right=candidate["option_right"], strike=float(candidate["strike"]),
                  ask=float(candidate["ask"]), bid=float(candidate["bid"]),
                  implied_vol=iv, multiplier=multiplier,
                  expiry_sessions=expiry_sessions, last_exit_session=last_exit)
    try:
        base = value_research_contract(**common)
        adverse = value_research_contract(
            **common, iv_multiplier=0.8, commission_usd_round_trip=2.0,
            extra_slippage_fraction_of_spread_each_side=0.25)
    except ValueError as error:
        return {"state": "RESEARCH_INPUT_INVALID", "reason": str(error)}
    base_returns = base.pop("per_path_return_fraction")
    adverse_returns = adverse.pop("per_path_return_fraction")
    seed = int(path_id[:8], 16)
    return {"state": "RESEARCH_EV_UNCALIBRATED", "ev_fraction": base["ev_fraction"],
            "ev_usd": base["ev_usd"], "base_mean_95_interval": _research_interval(base_returns, seed=seed),
            "adverse_ev_fraction": adverse["ev_fraction"],
            "adverse_mean_95_interval": _research_interval(adverse_returns, seed=seed),
            "event_weights": base["event_weights"],
            "independent_20_session_paths": len(historical_paths),
            "path_source_id": path_id, "exit_policy": base["exit_policy"],
            "assumptions": {"source": "CURRENT_KNOWN_UNCONDITIONAL_TICKER_HISTORY",
                            "direction_conditioned": False, "wyckoff_conditioned": False,
                            "held_out_calibrated": False,
                            "base_rate": 0.0, "base_dividend_yield": 0.0,
                            "base_commission_usd": 0.0, "base_extra_slippage": 0.0,
                            "adverse_iv_multiplier": 0.8,
                            "adverse_commission_usd": 2.0,
                            "adverse_extra_slippage_fraction_of_spread_each_side": 0.25},
            "authority": "RESEARCH_ONLY"}


def publish_expression_valuations(
    run_root: Path | str, *, price_database_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(run_root)
    frozen = load_descriptive_packet(root)
    candidates_path = root / "forecast" / "expression_candidates_v1" / "packet.json"
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    frozen_path = root / "forecast" / "ticker_forecast_descriptive_v1" / "packet.json"
    if (candidates.get("run_id") != root.name
            or candidates.get("frozen_forecast_sha256") != _sha(frozen_path)
            or candidates.get("row_count") != len(candidates.get("rows", []))):
        raise ValueError("C6 packet and frozen C5 identity do not reconcile")
    by_ticker = {row["ticker"]: row for row in candidates["rows"]}
    if len(by_ticker) != len(frozen["rows"]) or set(by_ticker) != {row["ticker"] for row in frozen["rows"]}:
        raise ValueError("C6/C5 ticker population mismatch")
    rows: list[dict[str, Any]] = []
    research_count = 0
    price_connection = (open_research_price_database(price_database_path)
                        if price_database_path is not None else None)
    try:
      for claim in frozen["rows"]:
        source = by_ticker[claim["ticker"]]
        if source.get("forecast_thesis_id") != claim.get("forecast_thesis_id"):
            raise ValueError("C6/C5 thesis identity mismatch")
        historical_paths = ()
        if price_connection is not None and source["candidates"]:
            bars = read_current_known_bars(
                price_connection, ticker=claim["ticker"],
                evidence_session=frozen["evidence_session"],
                decision_cutoff_utc=frozen["as_of_utc"],
            )
            historical_paths = build_nonoverlapping_relative_paths(claim["ticker"], bars)
        seen: set[str] = set()
        expressions = []
        for candidate in source["candidates"]:
            symbol = candidate["option_symbol"]
            if symbol in seen or candidate.get("thesis_id") != claim["forecast_thesis_id"]:
                raise ValueError("C6 candidate identity missing or duplicate")
            seen.add(symbol)
            # C4 has no qualified, held-out path set on this descriptive lane.
            disposition = value_long_option_paths(None, None)
            research = (_research_value(claim, candidate, historical_paths,
                                        evidence_session=frozen["evidence_session"])
                        if price_connection is not None else {"state": "RESEARCH_SOURCE_UNAVAILABLE"})
            if research["state"] == "RESEARCH_EV_UNCALIBRATED":
                research_count += 1
            expressions.append({"option_symbol": symbol,
                                "last_exit_date": candidate["last_exit_date"],
                                "valuation_state": disposition["state"],
                                "ev_usd": None, "ev_fraction": None,
                                "research_ev": research,
                                "authority": "RESEARCH_ONLY"})
        rows.append({"ticker": claim["ticker"],
                     "forecast_thesis_id": claim["forecast_thesis_id"],
                     "expression_state": source["expression_state"],
                     "candidate_count": len(expressions),
                     "valuation_state": ("NOT_VALUED_STATISTICAL_SUPPORT" if expressions
                                         else "NO_CANDIDATE_TO_VALUE"),
                     "expressions": expressions,
                     "best_expression": None,
                     "numeric_ev": None})
    finally:
        if price_connection is not None:
            price_connection.close()
    packet = {"schema_version": "expression_valuation_v1", "run_id": root.name,
              "frozen_forecast_sha256": _sha(frozen_path),
              "candidate_packet_sha256": _sha(candidates_path),
              "row_count": len(rows), "authority": "ADVISORY_ONLY",
              "numeric_valuation_count": 0,
              "research_ev_count": research_count,
              "research_ev_policy": "unconditional_same_ticker_20_session_blocks_v1",
              "rows": rows}
    output = root / "forecast" / "expression_valuation_v1" / "packet.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(packet, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != packet:
            raise ValueError("C8 disposition packet is immutable")
        return existing
    fd, temporary_name = tempfile.mkstemp(prefix=".c8_", suffix=".json", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
        if output.exists():
            raise ValueError("C8 packet was published concurrently")
        temporary.rename(output)
    finally:
        temporary.unlink(missing_ok=True)
    return packet
