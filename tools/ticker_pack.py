#!/usr/bin/env python3
"""Ticker intelligence pack: read-only extraction of everything AVSHUNTER holds on a ticker.

Outside the pipeline. Reads the canonical price store, the newest pipeline run, the
Intelligence Lab outputs and the macro board snapshot, all read-only. Its only writes go to
data/scratch/ticker_packs/, which no pipeline module reads.

Usage (from the repo root, PowerShell):
    venv\\Scripts\\python.exe tools\\ticker_pack.py MU
    venv\\Scripts\\python.exe tools\\ticker_pack.py MU NVDA --run 20261008_220129 --since 2023-01-01
    venv\\Scripts\\python.exe tools\\ticker_pack.py HSBC CPNG --run 20261111_231951 --session 2026-11-12

Output: data/scratch/ticker_packs/<session>/<TICKER>_pack.zip (one file per ticker, small enough
to hand to Claude), plus the unzipped folder beside it. One folder per session: a later batch adds
or replaces tickers in the same folder (Lane B Fix B6, 12 Nov 2026). Every pack carries manifest.json:
source path, modification time, age in hours and row count for each file, so stale or
missing inputs are visible rather than silently absent (R1: missing is never neutral).

The first file of every pack is lab_card.json: the ticker's row in the Intelligence Lab review
projection (card values by name, the structure / option_risk / context / morning evidence families),
with the Lab revision and database sha256. The pack is refused when the Lab publication is not
COMPLETE or is older than the run's Morning completion: packs are built after the Lab publishes.
"""

from __future__ import annotations

import argparse
import csv
import json
import hashlib
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRICE_DB = ROOT / "data" / "canonical" / "historical_prices.sqlite"
RUNS_DIR = ROOT / "data" / "output" / "runs"
BOARD_SNAPSHOTS = ROOT / "macro_board" / "output" / "snapshots"
OUT_ROOT = ROOT / "data" / "scratch" / "ticker_packs"

sys.path.insert(0, str(ROOT / "data" / "scratch" / "workaround"))
import lab_reader  # noqa: E402  (the one read-only reader of the Lab review projection)

BENCHMARKS = ["SPY", "QQQ", "IWM", "SMH", "XLK"]
TICKER_COLUMNS = ("ticker", "symbol", "underlying", "underlying_symbol", "root", "underlying_ticker")

# Per-ticker rows filtered out of large run files ({run} is replaced by the run id).
RUN_TABLES = [
    "intelligence_lab/lab_triage_view_{run}.csv",
    "intelligence_lab/final_opportunity_book_{run}.csv",
    "options/options_intelligence_{run}.csv",
    "options/options_candidates_ranked.csv",
    "options/options_candidate_expressions_{run}.csv",
    "options/options_blocked_review.csv",
    "options/contract_rejection_log_{run}.csv",
    "options/vanguard_signals_enriched_{run}.csv",
    "superbrain/superbrain_enriched_{run}.csv",
    "superbrain/eil_enriched_{run}.csv",
    "superbrain/wall_break_scores_{run}.csv",
    "horizon/horizon_1_5d_{run}.csv",
    "horizon/horizon_6_10d_{run}.csv",
    "horizon/horizon_11_20d_{run}.csv",
    "horizon/horizon_blocked_{run}.csv",
    "catalysts/catalyst_truth_{run}.csv",
    "qomega/garch_forecasts_{run}.csv",
    "discovery/discovery_candidates_ultimate_{run}.csv",
    "morning_validation/morning_candidates_{run}.csv",
    "execution/execution_v3_5_{run}.csv",
    "trigger_layer_summary_{run}.csv",
    "diagnostics/dropoff_audit_{run}.csv",
]
RUN_JSONL = [
    "enrichment/actuarial_{run}.jsonl",
    "enrichment/market_profile_{run}.jsonl",
    "enrichment/trap_{run}.jsonl",
    "enrichment/trigger_{run}.jsonl",
    "options/governed_direction_records_{run}.jsonl",
]
# Ticker-keyed JSON documents: the ticker's own entry is extracted.
RUN_JSON_KEYED = [
    "core_intel/core_intel_dossiers_{run}.json",
    "interpreter/interpreter_macro_context.json",
    "options/dynamic_options_intelligence_{run}.json",
]
# Whole-run context copied as-is (small).
RUN_CONTEXT = [
    "macro_quant_packet.json",
    "truth_packet_run.json",
    "final_run_manifest.json",
    "pipeline_integrity_{run}.json",
    "diagnostics/uat_audit_report_{run}.md",
    "diagnostics/market_breadth_diagnostic_{run}.json",
    "diagnostics/intraday_regime_watchdog_{run}.json",
    "horizon/horizon_summary_{run}.json",
    "catalysts/catalyst_truth_summary_{run}.json",
    "options/options_intelligence_summary_{run}.json",
    "macro/completed_session_gex_refresh_{run}.json",
    "macro/gex_source/avshunter_gex_proxy.csv",
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def describe(path: Path) -> dict:
    if not path.exists():
        return {"source": str(path), "status": "MISSING"}
    mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return {"source": str(path), "status": "PRESENT", "modified_utc": mtime.isoformat(timespec="seconds"),
            "age_hours": round((now_utc() - mtime).total_seconds() / 3600, 1), "bytes": path.stat().st_size}


def newest_run(explicit: str | None) -> Path:
    if explicit:
        run = RUNS_DIR / explicit
        if not run.is_dir():
            sys.exit(f"Run folder not found: {run}")
        return run
    runs = sorted(p for p in RUNS_DIR.iterdir() if p.is_dir() and p.name[:8].isdigit()
                  and any((p / "intelligence_lab").glob("lab_triage_view_*.csv")))
    if not runs:
        sys.exit(f"No completed runs (with an Intelligence Lab triage view) under {RUNS_DIR}")
    return runs[-1]


def ticker_column(columns) -> str | None:
    lower = {c.lower(): c for c in columns}
    for name in TICKER_COLUMNS:
        if name in lower:
            return lower[name]
    return None


# --- prices -------------------------------------------------------------------------------

def export_prices(tickers: list[str], since: str, out: dict[str, Path], manifest: dict) -> None:
    info = describe(PRICE_DB)
    if info["status"] == "MISSING":
        for t in tickers:
            manifest[t]["files"]["prices_ohlcv_daily.csv"] = info
        return
    wanted = sorted(set(tickers) | set(BENCHMARKS))
    marks = ",".join("?" for _ in wanted)
    with sqlite3.connect(f"file:{PRICE_DB.as_posix()}?mode=ro", uri=True) as con:
        frame = pd.read_sql_query(
            f"SELECT * FROM ohlcv_daily WHERE bar_status='COMPLETE' AND trading_date >= ? "
            f"AND ticker IN ({marks}) ORDER BY ticker, trading_date", con, params=[since, *wanted])
    for t in tickers:
        own = frame[frame["ticker"] == t]
        own.to_csv(out[t] / "prices_ohlcv_daily.csv", index=False)
        bench = frame[frame["ticker"].isin([b for b in BENCHMARKS if b != t])]
        bench[["ticker", "trading_date", "open", "close", "volume"]].to_csv(
            out[t] / "prices_benchmarks.csv", index=False)
        manifest[t]["files"]["prices_ohlcv_daily.csv"] = {
            **info, "rows": len(own), "first": own["trading_date"].min() if len(own) else None,
            "last": own["trading_date"].max() if len(own) else None,
            "status": info["status"] if len(own) else "NO_ROWS"}
        manifest[t]["files"]["prices_benchmarks.csv"] = {**info, "rows": len(bench)}


# --- run files ----------------------------------------------------------------------------

def filter_csv(src: Path, tickers: set[str]) -> tuple[dict[str, pd.DataFrame], str | None]:
    found: dict[str, list[pd.DataFrame]] = {t: [] for t in tickers}
    col = None
    # keep_default_na=False: the tickers NAN and NA are real tickers, not missing values
    for chunk in pd.read_csv(src, dtype=str, chunksize=200_000, low_memory=False, keep_default_na=False):
        col = col or ticker_column(chunk.columns)
        if col is None:
            return {}, "NO_TICKER_COLUMN"
        keys = chunk[col].str.upper().str.strip()
        hit = chunk[keys.isin(tickers)]
        for t, part in hit.groupby(keys[hit.index]):
            found[t].append(part)
    return {t: pd.concat(p) for t, p in found.items() if p}, None


def filter_jsonl(src: Path, tickers: set[str]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {t: [] for t in tickers}
    with src.open(encoding="utf-8") as handle:
        for line in handle:
            if not any(f'"{t}"' in line for t in tickers):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            col = ticker_column(record.keys()) if isinstance(record, dict) else None
            key = str(record.get(col, "")).upper() if col else ""
            if key in found:
                found[key].append(record)
    return found


def extract_keyed(doc, ticker: str, depth: int = 0):
    """The ticker's entry in a ticker-keyed JSON document (dict key or list item), if any."""
    if depth > 3:
        return None
    if isinstance(doc, dict):
        for key in (ticker, ticker.lower()):
            if key in doc:
                return doc[key]
        col = ticker_column(doc.keys())
        if col and str(doc.get(col, "")).upper() == ticker:
            return doc
        hits = {k: v for k, v in ((k, extract_keyed(v, ticker, depth + 1)) for k, v in doc.items()) if v is not None}
        return hits or None
    if isinstance(doc, list):
        hits = [h for h in (extract_keyed(v, ticker, depth + 1) for v in doc) if h is not None]
        return hits or None
    return None


def export_run(run: Path, tickers: list[str], out: dict[str, Path], manifest: dict) -> None:
    rid = run.name
    wanted = set(tickers)
    for pattern in RUN_TABLES:
        src = run / pattern.format(run=rid)
        name = "run__" + src.name
        info = describe(src)
        if info["status"] == "MISSING":
            for t in tickers:
                manifest[t]["files"][name] = info
            continue
        hits, problem = filter_csv(src, wanted)
        for t in tickers:
            rows = hits.get(t)
            if rows is not None:
                rows.to_csv(out[t] / name, index=False)
            manifest[t]["files"][name] = {**info, "rows": 0 if rows is None else len(rows),
                                          "status": problem or ("PRESENT" if rows is not None else "TICKER_ABSENT")}
    for pattern in RUN_JSONL:
        src = run / pattern.format(run=rid)
        name = "run__" + src.name
        info = describe(src)
        hits = filter_jsonl(src, wanted) if info["status"] == "PRESENT" else {}
        for t in tickers:
            records = hits.get(t, [])
            if records:
                (out[t] / name).write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
            manifest[t]["files"][name] = {**info, "rows": len(records),
                                          "status": info["status"] if info["status"] == "MISSING"
                                          else ("PRESENT" if records else "TICKER_ABSENT")}
    for pattern in RUN_JSON_KEYED:
        src = run / pattern.format(run=rid)
        name = "run__" + src.stem + "__ticker.json"
        info = describe(src)
        doc = json.loads(src.read_text(encoding="utf-8")) if info["status"] == "PRESENT" else None
        for t in tickers:
            entry = extract_keyed(doc, t) if doc is not None else None
            if entry is not None:
                (out[t] / name).write_text(json.dumps(entry, indent=1, default=str), encoding="utf-8")
            manifest[t]["files"][name] = {**info, "status": info["status"] if doc is None
                                          else ("PRESENT" if entry is not None else "TICKER_ABSENT")}
    for pattern in RUN_CONTEXT:
        src = run / pattern.format(run=rid)
        name = "context__" + src.name
        info = describe(src)
        for t in tickers:
            if info["status"] == "PRESENT":
                (out[t] / name).write_bytes(src.read_bytes())
            manifest[t]["files"][name] = info


# --- macro board --------------------------------------------------------------------------

def export_board(tickers: list[str], out: dict[str, Path], manifest: dict) -> None:
    snaps = sorted(BOARD_SNAPSHOTS.glob("board_*.json")) if BOARD_SNAPSHOTS.exists() else []
    evening = [p for p in snaps if p.stem.count("_") == 1]  # board_<session>.json = scored evening build
    for label, path in (("macro_board_evening.json", evening[-1] if evening else None),
                        ("macro_board_latest.json", snaps[-1] if snaps else None)):
        info = describe(path) if path else {"source": str(BOARD_SNAPSHOTS), "status": "MISSING"}
        for t in tickers:
            if path:
                (out[t] / label).write_bytes(path.read_bytes())
            manifest[t]["files"][label] = info


# --- Intelligence Lab card (B6) -----------------------------------------------------------

def open_lab_for_packs(run: Path):
    """The run's Lab publication, verified. Exits with the reason when packs must not be built from it."""
    try:
        lab = lab_reader.open_lab(run.name, RUNS_DIR)
    except lab_reader.LabUnavailable as error:
        sys.exit(f"REFUSED: {error}. Packs are built after the Lab publishes a COMPLETE review projection.")
    morning = sorted((run / "morning_validation").glob("morning_validated_trades_*.csv")) if (run / "morning_validation").exists() else []
    stage = "EVENING_PUBLICATION"
    if morning:
        stage = "MORNING_PUBLICATION"
        finished = datetime.fromtimestamp(max(p.stat().st_mtime for p in morning), timezone.utc)
        try:
            published = datetime.fromisoformat(str(lab.manifest.get("created_at_utc")).replace("Z", "+00:00"))
        except ValueError:
            lab.close()
            sys.exit(f"REFUSED: the Lab manifest for run {run.name} has no readable created_at_utc, so it cannot be shown to be newer than the Morning run.")
        if published < finished:
            lab.close()
            sys.exit(f"REFUSED: the Lab publication for run {run.name} (revision {lab.revision}, published {published.isoformat(timespec='seconds')}) "
                     f"is older than the run's Morning completion ({finished.isoformat(timespec='seconds')}). Republish the Lab, then build the packs.")
    return lab, stage


def session_for(run_id: str, lab) -> str:
    """The decision session: the Lab hand-off receipt for this run when one exists, else the first XNYS session after the Lab's bar date."""
    for receipt in sorted((ROOT / "data" / "scratch" / "workaround" / "handoff").glob("lab_*/receipt.json"), reverse=True):
        try:
            j = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if j.get("run_id") == run_id and j.get("session"):
            return str(j["session"])
    import build_lab_handoff
    return build_lab_handoff.decision_session(list(lab.rows()))[0]


def export_lab(lab, stage: str, tickers: list[str], out: dict[str, Path], manifest: dict) -> None:
    info = describe(lab.manifest_file)
    for t in tickers:
        manifest[t].update({"lab_revision": lab.revision, "lab_database_sha256": lab.sha256,
                            "lab_publication_created_at_utc": lab.manifest.get("created_at_utc"), "lab_publication_stage": stage})
        row = lab.row_for_ticker(t)
        if row is None:
            manifest[t]["files"]["lab_card.json"] = {**info, "status": "TICKER_ABSENT_FROM_LAB"}
            continue
        card = {"ticker": t, "run_id": lab.run_id, "lab_revision": lab.revision, "lab_database_sha256": lab.sha256,
                "lab_publication_created_at_utc": lab.manifest.get("created_at_utc"), "lab_publication_stage": stage,
                "row_key": row["row_key"], "card": row["values"], "card_missing_fields": row["missing"],
                "card_extra": row["extra"], "evidence": lab.evidence(row["row_key"]),
                "evidence_families_not_included": ["audit"]}
        text = json.dumps(card, indent=1, ensure_ascii=False)
        (out[t] / "lab_card.json").write_text(text, encoding="utf-8")
        manifest[t]["files"]["lab_card.json"] = {**info, "status": "PRESENT", "row_key": row["row_key"],
                                                 "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                                                 "lab_verdict": row["values"].get("lab_verdict"), "lab_rank": row["values"].get("lab_rank")}


# --- main ---------------------------------------------------------------------------------

def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="+", help="tickers in scope, e.g. MU NVDA")
    parser.add_argument("--run", help="run id under data/output/runs (default: newest completed run)")
    parser.add_argument("--since", default="2021-01-01", help="first trading date for price history")
    parser.add_argument("--session", help="decision session YYYY-MM-DD = the pack folder (default: the run's Lab hand-off session)")
    args = parser.parse_args(argv)

    tickers = sorted({t.upper().strip() for t in args.tickers})
    run = newest_run(args.run)
    lab, stage = open_lab_for_packs(run)
    session = args.session or session_for(run.name, lab)
    base = OUT_ROOT / session   # one folder per session: a later batch adds or replaces tickers here
    out = {t: base / t for t in tickers}
    for t, folder in out.items():
        if folder.exists():
            shutil.rmtree(folder)   # replace this ticker's pack; other tickers in the session folder are not touched
        folder.mkdir(parents=True, exist_ok=True)
    manifest = {t: {"ticker": t, "pack_built_utc": now_utc().isoformat(timespec="seconds"), "session": session,
                    "run_id": run.name, "price_since": args.since, "files": {}} for t in tickers}

    print(f"Run {run.name} | session {session} | Lab revision {lab.revision} ({stage}) | tickers {' '.join(tickers)}")
    print("  lab card ..."); export_lab(lab, stage, tickers, out, manifest)
    lab_revision, lab_created = lab.revision, lab.manifest.get("created_at_utc")
    lab.close()
    print("  prices ..."); export_prices(tickers, args.since, out, manifest)
    print("  run files ..."); export_run(run, tickers, out, manifest)
    print("  macro board ..."); export_board(tickers, out, manifest)

    for t in tickers:
        (out[t] / "manifest.json").write_text(json.dumps(manifest[t], indent=1, default=str), encoding="utf-8")
        archive = base / f"{t}_pack.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(out[t].iterdir(), key=lambda p: (p.name != "lab_card.json", p.name)):   # the Lab card first
                zf.write(f, f"{t}/{f.name}")
        files = manifest[t]["files"]
        missing = [k for k, v in files.items() if v.get("status") not in ("PRESENT",)]
        print(f"{t}: {archive} ({archive.stat().st_size / 1e6:.1f} MB); "
              f"{len(files) - len(missing)} sources present, {len(missing)} missing/absent")
    index_file = base / "packs_index.json"   # which tickers this session folder holds, and from which Lab revision
    index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else {"session": session, "tickers": {}}
    index.update({"session": session, "run_id": run.name, "lab_revision": lab_revision, "lab_publication_created_at_utc": lab_created,
                  "updated_utc": now_utc().isoformat(timespec="seconds")})
    for t in tickers:
        index["tickers"][t] = {"built_utc": manifest[t]["pack_built_utc"], "lab_revision": lab_revision,
                               "lab_card": manifest[t]["files"]["lab_card.json"]["status"]}
    index_file.write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"Pack folder: {base}")


if __name__ == "__main__":
    main()
