"""C6 accepts the two canonical chain encodings without guessing format."""

import hashlib
import json
import sqlite3

import pandas as pd

from contracts.expression_candidate_packet import _linked_chain


def _registry(tmp_path, dataset_id, path, schema):
    connection = sqlite3.connect(tmp_path / "registry.sqlite")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE dataset_registry (
             dataset_id TEXT, dataset_type TEXT, instrument_id TEXT,
             session_date TEXT, completeness_status TEXT, schema_version TEXT,
             as_of TEXT, storage_uri TEXT, content_hash TEXT, source_run_id TEXT
           )"""
    )
    connection.execute(
        "INSERT INTO dataset_registry VALUES (?,?,?,?,?,?,?,?,?,?)",
        (dataset_id, "OPTION_CHAIN", "XYZ", "2026-09-25", "COMPLETE", schema,
         "2026-09-25T20:00:00Z", str(path), hashlib.sha256(path.read_bytes()).hexdigest(),
         "source_run"),
    )
    connection.commit()
    return connection


def _row():
    return {"symbol": "XYZ261120C00100000", "bid": 3.8, "ask": 4.0,
            "implied_vol": 0.35, "quote_timestamp_utc": "2026-09-25T20:00:00Z"}


def test_v2_json_chain_is_verified_and_loaded(tmp_path):
    path = tmp_path / "chain.json"
    path.write_text(json.dumps([_row()]), encoding="utf-8")
    connection = _registry(tmp_path, "v2", path, "option_chain_v2")
    rows, source = _linked_chain(connection, "v2", ticker="XYZ", session="2026-09-25",
                                 cutoff="2026-09-26T17:37:30Z")
    assert source["schema_version"] == "option_chain_v2"
    assert rows[0]["option_symbol"] == _row()["symbol"]
    connection.close()


def test_v1_parquet_chain_is_verified_and_loaded(tmp_path):
    path = tmp_path / "chain.parquet"
    pd.DataFrame([_row()]).to_parquet(path, index=False)
    connection = _registry(tmp_path, "v1", path, "option_chain_v1")
    rows, source = _linked_chain(connection, "v1", ticker="XYZ", session="2026-09-25",
                                 cutoff="2026-09-26T17:37:30Z")
    assert source["schema_version"] == "option_chain_v1"
    assert rows[0]["option_symbol"] == _row()["symbol"]
    connection.close()
