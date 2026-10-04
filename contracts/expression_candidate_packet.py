"""Read-only, run-linked C6 candidate enumeration from canonical option chains.

This is a bounded advisory comparison set, never a selected contract or EV.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from canonical_data.option_chain_store import CHAIN_SCHEMA_VERSION
from canonical_data.session_clock import advance_xnys_sessions
from contracts.descriptive_forecast_packet import load_descriptive_packet
from domain.candidate_expression import enumerate_long_expressions
from domain.ticker_forecast import ForecastDirection, ForecastState, TickerForecast


def _linked_chain(connection: sqlite3.Connection, dataset_id: str, *, ticker: str, session: str, cutoff: str) -> tuple[list[dict], dict]:
    record = connection.execute("SELECT * FROM dataset_registry WHERE dataset_id=?", (dataset_id,)).fetchone()
    if record is None:
        raise ValueError("canonical chain dataset id not registered")
    if (record["dataset_type"] != "OPTION_CHAIN" or record["instrument_id"] != ticker
            or record["session_date"] != session or record["completeness_status"] != "COMPLETE"
            or record["schema_version"] not in {CHAIN_SCHEMA_VERSION, "option_chain_v2"}):
        raise ValueError("canonical chain identity, session or finality mismatch")
    if datetime.fromisoformat(str(record["as_of"]).replace("Z", "+00:00")) > datetime.fromisoformat(cutoff.replace("Z", "+00:00")):
        raise ValueError("canonical chain is future to forecast cutoff")
    path = Path(record["storage_uri"])
    encoded = path.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != record["content_hash"]:
        raise ValueError("canonical chain content hash mismatch")
    if record["schema_version"] == CHAIN_SCHEMA_VERSION:
        if path.suffix.lower() != ".parquet":
            raise ValueError("v1 canonical chain storage format mismatch")
        frame = pd.read_parquet(path)
        payload = frame.to_dict(orient="records")
    else:
        if path.suffix.lower() != ".json":
            raise ValueError("v2 canonical chain storage format mismatch")
        payload = json.loads(encoded)
    if (not isinstance(payload, list) or not payload
            or any(not isinstance(item, dict) for item in payload)
            or not any(item.get("symbol") for item in payload)):
        raise ValueError("canonical chain has no usable contract identities")
    rows = [
        {**item, "option_symbol": item.get("symbol"), "quote_as_of_utc": item.get("quote_timestamp_utc"),
         "source_run_id": record["source_run_id"]}
        for item in payload
    ]
    return rows, {"dataset_id": dataset_id, "original_source_run_id": record["source_run_id"],
                  "schema_version": record["schema_version"],
                  "content_hash": record["content_hash"]}


def publish_expression_candidates(
    run_root: Path | str,
    *,
    registry_path: Path | str,
    max_candidates: int = 20,
    expiry_buffer_days: int = 1,
) -> dict[str, Any]:
    root = Path(run_root)
    frozen = load_descriptive_packet(root)
    options_csv = root / "options" / f"options_intelligence_{root.name}.csv"
    with options_csv.open(newline="", encoding="utf-8-sig") as handle:
        options = list(csv.DictReader(handle))
    by_ticker = {}
    for row in options:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker in by_ticker:
            raise ValueError("Options population contains missing or duplicate ticker")
        by_ticker[ticker] = row
    registry = Path(registry_path)
    if not registry.is_file():
        raise ValueError("canonical registry unavailable")
    connection = sqlite3.connect(f"file:{registry.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    records: list[dict] = []
    try:
        for claim in frozen["rows"]:
            ticker = claim["ticker"]
            linked = by_ticker.get(ticker)
            dataset_id = str((linked or {}).get("option_chain_dataset_id") or "").strip()
            result = {"ticker": ticker, "forecast_thesis_id": claim["forecast_thesis_id"],
                      "forecast_state": claim["forecast_state"], "chain_dataset_id": dataset_id or None,
                      "expression_state": "NO_VERIFIED_CHAIN", "c8_valuation_state": "NOT_VALUED_STATISTICAL_SUPPORT",
                      "c8_numeric_ev": None, "candidates": [], "rejection_counts": {}}
            if claim["forecast_state"] != "DESCRIPTIVE_ONLY":
                result["expression_state"] = "NOT_APPLICABLE_NO_GOVERNED_FORECAST"
            elif not dataset_id:
                result["expression_state"] = "NO_VERIFIED_CHAIN"
            else:
                try:
                    chain, source = _linked_chain(connection, dataset_id, ticker=ticker,
                                                  session=frozen["evidence_session"], cutoff=frozen["as_of_utc"])
                except (OSError, ValueError, sqlite3.Error, ImportError) as error:
                    result["expression_state"] = "CHAIN_INVALID"
                    result["chain_error"] = f"{type(error).__name__}:{error}"
                    records.append(result)
                    continue
                # A cached same-session acquisition can originate in an earlier
                # run. Current-run linkage is the Options row's dataset ID.
                for item in chain:
                    item["source_run_id"] = root.name
                    if item.get("contract_multiplier") in {None, ""}:
                        inherited = str((linked or {}).get("contract_multiplier") or "").strip()
                        source_kind = str((linked or {}).get("contract_multiplier_source") or "").strip()
                        if inherited == "100.0" or inherited == "100":
                            if source_kind in {"OCC_STANDARD_100_INFERRED", "OCC_STANDARD_100_OBSERVED"}:
                                item["contract_multiplier"] = 100
                                item["contract_multiplier_source"] = source_kind
                forecast = TickerForecast(
                    root.name, claim["forecast_thesis_id"], ticker,
                    frozen["evidence_session"], frozen["as_of_utc"],
                    ForecastDirection(claim["forecast_direction"]),
                    ForecastState.DESCRIPTIVE_ONLY,
                    claim["forecast_reference_spot"], claim["forecast_target_spot"],
                    claim["forecast_invalidation_spot"],
                )
                candidate_set = enumerate_long_expressions(
                    forecast, chain,
                    last_exit_date=advance_xnys_sessions(date.fromisoformat(frozen["evidence_session"]), 20).isoformat(),
                    expiry_buffer_days=expiry_buffer_days, max_candidates=max_candidates,
                    quote_cutoff_utc=frozen["as_of_utc"],
                )
                result.update({"expression_state": candidate_set.expression_state,
                               "chain_source": source,
                               "rows_seen": candidate_set.rows_seen,
                               "search_policy": candidate_set.search_policy,
                               "candidates": [asdict(candidate) for candidate in candidate_set.candidates],
                               "rejection_counts": candidate_set.rejection_counts})
            records.append(result)
    finally:
        connection.close()
    packet = {"schema_version": "expression_candidates_v1", "run_id": root.name,
              "frozen_forecast_sha256": hashlib.sha256(
                  (root / "forecast" / "ticker_forecast_descriptive_v1" / "packet.json").read_bytes()
              ).hexdigest(), "options_csv_sha256": hashlib.sha256(options_csv.read_bytes()).hexdigest(),
              "row_count": len(records), "authority": "ADVISORY_ONLY", "rows": records}
    output = root / "forecast" / "expression_candidates_v1" / "packet.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(packet, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != packet:
            raise ValueError("C6 expression packet is immutable")
        return existing
    fd, temporary_name = tempfile.mkstemp(prefix=".c6_", suffix=".json", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
        if output.exists():
            raise ValueError("C6 expression packet was published concurrently")
        temporary.rename(output)
    finally:
        temporary.unlink(missing_ok=True)
    return packet
