"""Saved-input kernel replay, not a stage or pipeline runner.

Blocks network, live SQLite writes and filesystem writes outside --output.
The caller snapshots original sources into --baseline before editing. Each
comparison runs both implementations on identical frozen inputs and requires
exact equality. No hypothetical provider latency is counted as time saved.
"""
from __future__ import annotations

import argparse
import ast
import copy
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import sqlite3
import sys
import time
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd


def definitions(path, names, env=None):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names]
    assert len(nodes) == len(names), (path, names)
    namespace = dict(pd=pd, np=np, Path=Path, date=date, datetime=datetime, timezone=timezone,
                     timedelta=timedelta, lru_cache=lru_cache, copy=copy, os=os, logging=logging, math=math)
    namespace.update(env or {})
    unit = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(unit), str(path), "exec"), namespace)
    return namespace


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def guard(output):
    counts = {"network_attempts": 0, "live_write_attempts": 0, "blocked_local_bind_probes": 0, "blocked_network_stacks": []}
    def allowed(value):
        if isinstance(value, int) or str(value).lower() in {os.devnull.lower(), "nul", r"\\.\nul"}:
            return True
        path_text = str(value)
        if path_text.startswith("\\\\?\\"):
            path_text = path_text[4:]
        return Path(path_text).resolve().is_relative_to(output)
    def audit(event, args):
        if event == "socket.bind":
            # urllib3 probes IPv6 by binding ::1 during import. Deny this too,
            # but distinguish a local capability probe from outbound traffic.
            counts["blocked_local_bind_probes"] += 1
            raise OSError("OFFLINE_LOCAL_BIND_DISABLED")
        if event in {"socket.connect", "socket.getaddrinfo"}:
            counts["network_attempts"] += 1
            import traceback
            counts["blocked_network_stacks"].append(traceback.format_stack(limit=12))
            raise RuntimeError("NETWORK_FORBIDDEN")
        if event == "sqlite3.connect":
            value = str(args[0])
            if "mode=ro" not in value and value != ":memory:" and not allowed(value):
                counts["live_write_attempts"] += 1
                raise RuntimeError("LIVE_SQLITE_WRITE_FORBIDDEN")
        if event == "open":
            path, mode, flags = args
            writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not allowed(path):
                counts["live_write_attempts"] += 1
                raise RuntimeError(f"LIVE_WRITE_FORBIDDEN:{path}")
        if event in {"os.remove", "os.rmdir", "os.mkdir", "os.rename"}:
            paths = args[:2] if event == "os.rename" else args[:1]
            if any(not allowed(p) for p in paths):
                counts["live_write_attempts"] += 1
                raise RuntimeError(f"LIVE_MUTATION_FORBIDDEN:{event}:{paths}")
    sys.addaudithook(audit)
    return counts


def ro(path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    deadline = time.monotonic() + 20
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    connection.row_factory = sqlite3.Row
    return connection


def history(ticker):
    with ro(ROOT / "data/canonical/historical_prices.sqlite") as connection:
        rows = connection.execute("SELECT trading_date AS date,open,high,low,close,volume FROM ohlcv_daily WHERE ticker=? AND adjustment_convention='POLYGON_SPLIT_ADJUSTED' AND bar_status='COMPLETE' AND trading_date<=? ORDER BY trading_date", (ticker, "2026-11-10")).fetchall()
    connection.close()
    frame = pd.DataFrame([dict(r) for r in rows])
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def timings(old, new, values, digest):
    outputs = []
    seconds = []
    for implementation in (old, new):
        start = time.perf_counter()
        h = hashlib.sha256()
        for i, value in enumerate(values):
            result = implementation(value)
            h.update(digest(result))
            if i and i % 250 == 0:
                print(f"replayed {i}/{len(values)} in {time.perf_counter()-start:.1f}s", flush=True)
        seconds.append(time.perf_counter() - start)
        outputs.append(h.hexdigest())
    assert outputs[0] == outputs[1], outputs
    return {"cases": len(values), "baseline_seconds": seconds[0], "optimised_seconds": seconds[1],
            "saved_seconds": seconds[0] - seconds[1], "exact_parity_sha256": outputs[0]}


def packed(value):
    return json.dumps(value, sort_keys=True, default=str, allow_nan=True, separators=(",", ":")).encode()


def discovery(args, run):
    # Real saved prices, real ingest code, isolated SQLite. No fetcher HTTP code runs.
    from canonical_data.historical_prices import HistoricalPriceDatabase
    frames = [(t, history(t)) for t in ["AAPL", "BILI", "BRK.B", "NAN", "SYM", "SPY", "QQQ", "MSFT", "NVDA", "TSLA"]]
    frames = [(t, f) for t, f in frames if not f.empty]
    reports = []
    hashes = []
    for label, source in [("baseline", args.baseline / "avshunter_discovery_ULTIMATE.py"), ("optimised", ROOT / "avshunter_discovery_ULTIMATE.py")]:
        db = HistoricalPriceDatabase(args.output / (label + "_prices.sqlite"))
        db.initialise()
        bridge = types.ModuleType("canonical_data.history_bridge")
        bridge.DEFAULT_HISTORY_MAX_STALENESS_DAYS = 5
        bridge.canonical_history_is_fresh = lambda f: True
        bridge.read_canonical_history = lambda ticker, **kw: db.read(ticker) if db.coverage(ticker).row_count else None
        bridge.observe_shadow_history = lambda *a, **kw: None
        writes = []
        def commit(ticker, frame, **kwargs):
            writes.append((ticker, kwargs["source_kind"]))
            return db.ingest(ticker, frame, fetched_at=datetime(2026, 11, 10, 23, tzinfo=timezone.utc), **kwargs)
        bridge.write_through_fetched_history = commit
        sys.modules["canonical_data.history_bridge"] = bridge
        saved = dict(frames)
        class SavedFetcher:
            def fetch_daily_bars(self, ticker, start, end, *, persist_history=True):
                frame = saved[ticker].copy()
                if persist_history:
                    commit(ticker, frame, provider="POLYGON", source_kind="POLYGON_DATA_FETCHER", source_run_id=os.getenv("AVSHUNTER_RUN_ID"))
                return frame
        env = definitions(source, ["load_bars"], {"PolygonDataFetcher": SavedFetcher,
                          "REQUIRED_COLS": {"date", "open", "high", "low", "close", "volume"}})
        start = time.perf_counter(); h = hashlib.sha256()
        for ticker, _ in frames:
            frame = env["load_bars"](args.output / label, ticker, SavedFetcher(), True, 2000)
            h.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
            h.update(packed(frame.attrs))
        with ro(db.database_path) as connection:
            provenance = [tuple(r) for r in connection.execute(
                "SELECT ticker,trading_date,adjustment_convention,provider,source_kind,source_run_id,row_hash FROM ohlcv_daily ORDER BY ticker,trading_date")]
        connection.close()
        h.update(packed(provenance))
        reports.append({"seconds": time.perf_counter()-start, "ingest_calls": len(writes)})
        hashes.append(h.hexdigest())
    assert hashes[0] == hashes[1], hashes
    return {"cases": len(frames), "baseline": reports[0], "optimised": reports[1], "exact_parity_sha256": hashes[0],
            "saved_seconds": reports[0]["seconds"]-reports[1]["seconds"], "scope": "saved prices, actual isolated ingestion and Discovery load; not signal scanning"}


def profiles(args, run):
    from canonical_data import expected_intraday_timestamps, session_bounds
    old = definitions(args.baseline / "build_completed_market_profiles.py", ["_quality_diagnostics", "_atr14"], {"expected_intraday_timestamps": expected_intraday_timestamps})
    path = ROOT / "scripts/build_completed_market_profiles.py"
    names = ["_quality_diagnostics", "_atr14"]
    if "def _session_grid(" in path.read_text(encoding="utf-8"):
        names.insert(0, "_session_grid")
    new = definitions(path, names, {"expected_intraday_timestamps": expected_intraday_timestamps})
    entries = [json.loads(line) for line in (run / "enrichment" / f"market_profile_{args.run}.jsonl").read_text(encoding="utf-8").splitlines()]
    ids = sorted({ds for r in entries for ds in r["payload"].get("market_profile_quality", {}).get("dataset_ids", [])})
    frames = []
    with ro(ROOT / "data/canonical/control_plane.sqlite") as connection:
        records = [connection.execute("SELECT storage_uri,content_hash FROM dataset_registry WHERE dataset_id=?", (ds,)).fetchone() for ds in ids]
    connection.close()
    for record in records:
        assert record is not None
        path = Path(record["storage_uri"])
        assert sha(path) == record["content_hash"]
        frames.append(pd.read_parquet(path))
    assert frames, "No frozen profile inputs"
    session = date(2026, 11, 10); start, end = session_bounds(session)
    kwargs = dict(session_date=session, open_utc=start, close_utc=end, interval_minutes=5)
    result = timings(lambda f: old["_quality_diagnostics"](f, **kwargs), lambda f: new["_quality_diagnostics"](f, **kwargs), frames, packed)
    tickers = [str(r["ticker"]) for r in entries]
    values = [history(ticker) for ticker in tickers]
    values = [f for f in values if not f.empty]
    # Baseline includes the production DataFrame -> records -> DataFrame round trip.
    result["atr"] = timings(lambda f: old["_atr14"]({"daily_df": f.to_dict("records")}),
                             lambda f: new["_atr14"]({"daily_df": f}), values, packed)
    result["scope"] = "all saved profile frames and stored eligible daily histories; no resolver or publication"
    return result


def options(args, run):
    from scripts import avshunter_options_intelligence as oi
    import contracts.direction_governance as direction_governance
    # The baseline creates a new GDR audit timestamp on every parse when the
    # saved row lacks a scanner timestamp. Pin the replay clock, not the data
    # or compared fields; the derived JSON and SHA remain in the exact check.
    class ReplayClock(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime(2026, 11, 10, 23, 16, 48, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    direction_governance.datetime = ReplayClock
    names = ["_plain", "_number", "_rank", "_expressions", "evaluate_candidate_expressions"]
    constants = {"SIDE_TO_RIGHT": {"BULL": "CALL", "BEAR": "PUT"},
                 "_RECORD_FIELDS": __import__("scripts.options_candidate_lane", fromlist=["_RECORD_FIELDS"])._RECORD_FIELDS}
    old = definitions(args.baseline / "options_candidate_lane.py", names, constants)
    new = definitions(ROOT / "scripts/options_candidate_lane.py", names, constants)
    packet = json.loads((run / "forecast/behavioural_candidate_packet_v1/packet.json").read_text(encoding="utf-8"))
    # Match production CSV numeric/null parsing while retaining literal NAN ticker identity.
    def production_csv(path):
        frame = pd.read_csv(path, low_memory=False)
        ids = pd.read_csv(path, usecols=["ticker"], keep_default_na=False)
        frame["ticker"] = ids["ticker"]
        return frame
    disc = production_csv(run / "discovery" / f"discovery_candidates_ultimate_{args.run}.csv")
    vg = production_csv(run / "vanguard/vanguard_signals.csv")
    merged = oi.merge_discovery_vanguard(disc, vg)
    rows = {str(r["ticker"]).upper(): r for _, r in merged.iterrows()}
    saved = pd.read_csv(run / "options/options_intelligence_latest.csv", keep_default_na=False,
                        usecols=["ticker", "option_chain_dataset_id", "stand_down_reason", "options_verdict"])
    results = {str(r["ticker"]).upper(): r.to_dict() for _, r in saved.iterrows()}
    seconds = []; hashes = []; call_counts = []; counts = []
    for label, env in (("baseline", old), ("optimised", new)):
        h = hashlib.sha256(); calls = [0]; parsed = [0]
        def parse(row):
            parsed[0] += 1
            return oi.parse_structural_context(row)
        def select(chain, ctx):
            calls[0] += 1
            if calls[0] % 1000 == 0:
                print(f"{label}: {calls[0]} selector inputs in {time.perf_counter()-start:.1f}s", flush=True)
            # Exact selector-input parity proves the unchanged selector gets identical inputs.
            h.update(packed(ctx))
            return {"symbol": "PARITY_INPUT_ONLY"}
        start = time.perf_counter()
        lane = env["evaluate_candidate_expressions"](packet["records"], rows, results,
                fetch_chain=lambda ticker: ticker, parse_context=parse, select_contract=select)
        seconds.append(time.perf_counter()-start)
        h.update(packed(lane)); hashes.append(h.hexdigest())
        call_counts.append({"selector_inputs": calls[0], "context_parses": parsed[0]})
        counts.append(len(lane))
        print(label, seconds[-1], call_counts[-1], flush=True)
    assert hashes[0] == hashes[1], hashes
    return {"expressions": counts, "baseline_seconds": seconds[0], "optimised_seconds": seconds[1], "saved_seconds": seconds[0]-seconds[1],
            "calls": call_counts, "exact_parity_sha256": hashes[0],
            "replay_clock_utc": "2026-11-10T23:16:48Z", "excluded_context_fields": [],
            "scope": "all saved candidate rows and exact real selector contexts; contract pricing/selection itself is not rerun"}


def vanguard(args, run):
    import vanguard.layer2_statistical.actuarial_query as aq
    old = definitions(args.baseline / "actuarial_query.py", ["ActuarialQueryEngine"], vars(aq))["ActuarialQueryEngine"]
    new = aq.ActuarialQueryEngine
    # Only match columns, no live model changes or engine constructors.
    import pyarrow.parquet as pq
    schema = pq.read_schema(aq.ACTUARIAL_DATABASE_PATH)
    dims = [c for c in aq.MATCH_EXACT_DIMS if c in schema.names]
    frame = pd.read_parquet(aq.ACTUARIAL_DATABASE_PATH, columns=dims)
    for column in aq.ACTUARIAL_CATEGORY_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].astype("category")
    saved = pd.read_csv(run / "vanguard/vanguard_signals.csv", usecols=["ticker", "layer2__original_state_key"], keep_default_na=False)
    values = []
    for key in saved["layer2__original_state_key"]:
        state = dict(part.split("=", 1) for part in str(key).split("|") if "=" in part)
        values.append({d: aq.ActuarialQueryEngine._normalise_match_value(d, state.get(d))
                       if state.get(d) != "*" else None for d in dims})
    engines = []
    for cls in (old, new):
        engine = cls.__new__(cls); engine.df = frame; engine._match_norm_cache = {}
        # Warm normalisation equally: measure the changed filtering, not one-off load order.
        for dim in dims:
            engine._normalised_match_series(dim)
        engines.append(engine)
    def apply(engine, values):
        h = hashlib.sha256()
        for requested in (aq.MATCH_EXACT_DIMS, aq.MATCH_RELAXED_DIMS):
            use = engine._available_match_dims(frame, values, requested)
            sample = engine._filter_by_dims(frame, values, use)
            h.update(np.asarray(sample.index, dtype=np.int64).tobytes())
        return h.digest()
    report = timings(lambda v: apply(engines[0], v), lambda v: apply(engines[1], v), values, lambda b: b)
    report.update(model_rows=len(frame), scope="all saved Vanguard rows, exact and relaxed cohort membership in original order; downstream outcome maths unchanged")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["discovery", "profiles", "options", "vanguard"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--run", default="20261110_231648")
    args = parser.parse_args(); args.output = args.output.resolve()
    if args.run != "20261110_231648":
        parser.error("This acceptance replay is pinned to saved run 20261110_231648")
    os.environ["AVSHUNTER_RUN_ID"] = args.run
    os.environ["AVSHUNTER_CANONICAL_OFFLINE_REPLAY"] = "1"
    args.output.mkdir(parents=True, exist_ok=True)
    run = ROOT / "data/output/runs" / args.run
    protected = [ROOT / "config/macro_delivery_v1.json", ROOT / "Run-MacroInputs.ps1",
                 run / "vanguard/vanguard_signals.csv", run / "options/options_intelligence_latest.csv",
                 run / "options" / f"options_candidate_expressions_{args.run}.csv"]
    before = {str(p): sha(p) for p in protected}
    counts = guard(args.output)
    sources = ["avshunter_discovery_ULTIMATE.py", "polygon_data_fetcher.py", "scripts/build_completed_market_profiles.py",
               "scripts/options_candidate_lane.py", "vanguard/layer2_statistical/actuarial_query.py"]
    source_hashes = {name: {"baseline": sha(args.baseline / Path(name).name), "optimised": sha(ROOT / name)} for name in sources}
    report = {"phase": args.phase, "run": args.run, "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "isolated kernel benchmark, not a pipeline or stage rerun", "source_hashes": source_hashes}
    try:
        report["result"] = globals()[args.phase](args, run)
        assert counts["network_attempts"] == counts["live_write_attempts"] == 0, counts
        report["status"] = "PASS"
    except Exception as exc:
        report.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        report["guards"] = counts
        report["protected_files_unchanged"] = before == {str(p): sha(p) for p in protected}
        report["protected_hashes"] = before
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (args.output / (args.phase + "_report.json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
