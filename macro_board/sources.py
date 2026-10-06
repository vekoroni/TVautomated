"""Read-only loaders for the board. Every external file comes back with its as-of time,
age and a freshness status (FRESH / STALE / MISSING) so the page never shows stale or
absent data as if it were current."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import glob
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _connect_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


# --- prices -------------------------------------------------------------------------------

def load_prices(db: Path, tickers: Sequence[str], start: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(opens, closes, volumes) wide frames for ``tickers``, complete bars only."""
    placeholders = ",".join("?" for _ in tickers)
    with _connect_read_only(db) as connection:
        frame = pd.read_sql_query(
            f"SELECT ticker, trading_date, open, close, volume FROM ohlcv_daily "
            f"WHERE bar_status='COMPLETE' AND trading_date >= ? AND ticker IN ({placeholders})",
            connection, params=[start, *tickers], parse_dates=["trading_date"])
    wide = frame.pivot_table(index="trading_date", columns="ticker", values=["open", "close", "volume"])
    return wide["open"], wide["close"], wide["volume"]


def _store_fingerprint(db: Path) -> str:
    """Cheap change detector: any write to the store (or its WAL) changes size or mtime."""
    parts = []
    for path in (db, db.with_name(db.name + "-wal")):
        if path.exists():
            stat = path.stat()
            parts.append(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}")
    return "|".join(parts)


def load_breadth_panel(db: Path, start: str, sessions: pd.DatetimeIndex, cache_dir: Path | None = None) -> np.ndarray:
    """Session x ticker closes for every ticker in the store (outcome-scorer breadth universe).

    Cached under ``cache_dir`` keyed on the store's row count and latest fetch, so any ingest
    or revision invalidates it."""
    key = f"{_store_fingerprint(db)}|{start}"
    with _connect_read_only(db) as connection:
        if cache_dir is not None:
            meta, data = cache_dir / "breadth_panel.json", cache_dir / "breadth_panel.npy"
            if meta.exists() and data.exists():
                stored = json.loads(meta.read_text(encoding="utf-8"))
                if stored.get("key") == key:
                    index = pd.DatetimeIndex(pd.to_datetime(stored["sessions"]))
                    frame = pd.DataFrame(np.load(data), index=index)
                    return frame.reindex(sessions).to_numpy(dtype=float)
        frame = pd.read_sql_query(
            "SELECT ticker, trading_date, close FROM ohlcv_daily WHERE bar_status='COMPLETE' AND trading_date >= ?",
            connection, params=[start], parse_dates=["trading_date"])
    wide = frame.pivot(index="trading_date", columns="ticker", values="close").sort_index()
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(cache_dir / "breadth_panel.npy", wide.to_numpy(dtype=float))
        (cache_dir / "breadth_panel.json").write_text(json.dumps(
            {"key": key, "sessions": [str(d.date()) for d in wide.index], "tickers": list(wide.columns)}), encoding="utf-8")
    return wide.reindex(sessions).to_numpy(dtype=float)


def load_fred(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    return frame.apply(pd.to_numeric, errors="coerce").sort_index()


def load_c12_settings(registry_dir: Path, session: pd.Timestamp):
    """Reuse the outcome scorer's condition settings (one owner of trend/vol/breadth)."""
    from avshunter.config.adapters import load_registry
    from avshunter.c12_outcome.service import condition_settings
    from avshunter.shared.xnys_calendar import is_xnys_session, previous_xnys_session
    day = session.date()
    if not is_xnys_session(day):
        day = previous_xnys_session(day)
    return condition_settings(load_registry(registry_dir).resolve(day))


# --- external macro files ----------------------------------------------------------------

@dataclass
class SourceRead:
    name: str
    path: str
    status: str                      # FRESH | STALE | MISSING | UNREADABLE
    as_of: str | None = None
    age_hours: float | None = None
    data: Any = None
    note: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def file(self) -> Path | None:
        candidate = Path(self.path) if self.path and self.path != "None" else None
        if candidate is not None and not candidate.is_absolute():
            candidate = ROOT / candidate
        return candidate if candidate is not None and candidate.exists() else None

    def public(self) -> dict:
        return {"name": self.name, "path": self.path, "status": self.status, "as_of": self.as_of,
                "age_hours": None if self.age_hours is None else round(self.age_hours, 1), "note": self.note}


def _age_hours(stamp: str | None, now: datetime, fallback_path: Path) -> tuple[str | None, float | None]:
    when = None
    if stamp:
        try:
            parsed = pd.Timestamp(stamp)
            when = parsed.tz_localize("UTC") if parsed.tzinfo is None else parsed.tz_convert("UTC")
        except (ValueError, TypeError):
            when = None
    if when is None and fallback_path.exists():
        when = pd.Timestamp(fallback_path.stat().st_mtime, unit="s", tz="UTC")
    if when is None:
        return None, None
    return when.isoformat(), (pd.Timestamp(now) - when).total_seconds() / 3600.0


def latest_glob(pattern: str) -> Path | None:
    matches = sorted(glob.glob(str(resolve(pattern))))
    return Path(matches[-1]) if matches else None


def read_json(name: str, path: Path | None, stamp_keys: Sequence[str], max_age_hours: float, now: datetime) -> SourceRead:
    if path is None or not path.exists():
        return SourceRead(name, str(path), "MISSING", note="file not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return SourceRead(name, str(path), "UNREADABLE", note=type(exc).__name__)
    stamp = None
    for key in stamp_keys:
        node: Any = data
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node:
            stamp = str(node)
            break
    as_of, age = _age_hours(stamp, now, path)
    status = "FRESH" if age is not None and age <= max_age_hours else "STALE"
    note = "" if stamp else "as-of taken from file time"
    return SourceRead(name, str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path), status, as_of, age, data, note)


def read_csv(name: str, path: Path | None, date_column: str | None, max_age_hours: float, now: datetime) -> SourceRead:
    if path is None or not path.exists():
        return SourceRead(name, str(path), "MISSING", note="file not found")
    try:
        frame = pd.read_csv(path)
    except (OSError, ValueError) as exc:
        return SourceRead(name, str(path), "UNREADABLE", note=type(exc).__name__)
    stamp = None
    if date_column and date_column in frame.columns and not frame.empty:
        stamp = str(frame[date_column].dropna().astype(str).max())
    # A date-only stamp means "data for that session"; age is measured from file time so a
    # pre-market build on D+1 of D-dated data is not marked stale. Missing column -> file time.
    as_of, age = _age_hours(None, now, path)
    status = "FRESH" if age is not None and age <= max_age_hours else "STALE"
    rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    return SourceRead(name, rel, status, stamp or as_of, age, frame, "" if stamp else "as-of taken from file time")


def records(frame: pd.DataFrame | None) -> list[dict]:
    if frame is None or frame.empty:
        return []
    clean = frame.replace({np.nan: None})
    return clean.to_dict(orient="records")


def load_external(config: Mapping, now: datetime) -> dict[str, SourceRead]:
    src, fresh = config["sources"], config["freshness"]
    file_age = float(fresh["external_file_max_age_hours"])
    reads = {
        "macro_packet": read_json("LLM macro packet (macro_intelligence_latest)", resolve(src["macro_packet"]),
                                  ["as_of_utc", "_builder_metadata.built_at"], float(fresh["macro_packet_max_age_hours"]), now),
        "us_money_index": read_json("US Money Index (transmission score)", resolve(src["us_money_index"]),
                                    ["analysis_window.as_of_utc", "analysis_window.generated_utc"],
                                    float(fresh["us_money_index_max_age_hours"]), now),
        "enrichment": read_json("News enrichment delta", resolve(src["enrichment_delta"]), ["as_of_utc"], file_age, now),
        "event_payload": read_json("US economic event payload", latest_glob(src["event_payload_glob"]),
                                   ["run_context.generated_utc", "generated_from_report_date"], 48.0, now),
        "bond_state": read_json("Bond macro state", resolve(src["bond_state"]), ["generated_at"], file_age, now),
        "vix_engine": read_csv("VIX engine v3", resolve(src["vix_engine"]), "Date", file_age, now),
        "gex": read_csv("Dealer gamma (GEX) SPY/QQQ", resolve(src["gex_proxy"]), "Date", file_age, now),
        "liquidity_monitor": read_csv("Liquidity monitor", resolve(src["liquidity_monitor"]), "Date", file_age, now),
        "macro_filter": read_csv("Fung-Hsieh macro filter", resolve(src["macro_filter_summary"]), "Week", 24 * 8, now),
        "regime_model": read_csv("Colab daily regime model", resolve(src["daily_regime_model"]), "Date", file_age, now),
        "breadth_rsp_spy": read_csv("RSP vs SPY breadth", resolve(src["breadth_rsp_spy"]), "as_of", file_age, now),
        "forward_bias": read_csv("Colab forward bias", latest_glob(src["forward_bias_glob"]), None, file_age, now),
        "economic_prints": read_csv("FRED economic prints", latest_glob(src["economic_prints_glob"]), "date", file_age, now),
        "threshold_flags": read_csv("Series threshold flags", resolve(src["threshold_flags"]), "as_of", file_age, now),
    }
    return reads


# --- pipeline proposals (read-only display; the board never re-ranks or gates) -------------

def load_pipeline_proposals(runs_dir: Path, relative_file: str, columns: Sequence[str],
                            tickers: Sequence[str]) -> dict:
    """Rows for ``tickers`` from the newest run that produced ``relative_file``."""
    if not runs_dir.exists():
        return {"status": "MISSING", "rows": {}}
    candidates = sorted((p for p in runs_dir.iterdir() if p.is_dir() and (p / relative_file).exists()),
                        key=lambda p: p.name, reverse=True)
    if not candidates:
        return {"status": "MISSING", "rows": {}}
    run = candidates[0]
    path = run / relative_file
    frame = pd.read_csv(path, low_memory=False)
    key = "ticker" if "ticker" in frame.columns else frame.columns[0]
    keep = [c for c in columns if c in frame.columns]
    subset = frame[frame[key].isin(tickers)].drop_duplicates(subset=[key], keep="first")
    rows = {row[key]: {c: row[c] for c in keep} for row in records(subset[[key, *keep]])}
    modified = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC")
    return {"status": "OK", "run_id": run.name, "file": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "written_utc": modified.isoformat(timespec="seconds"), "rows": rows}


# --- input archive (reproducible board decisions, R7) -------------------------------------

def archive_inputs(paths: Mapping[str, Path | None], target_dir: Path) -> dict:
    """Content-addressed copy of every input file read this build; returns the manifest."""
    import hashlib
    import shutil
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, path in paths.items():
        if path is None or not Path(path).exists():
            manifest[name] = {"path": None if path is None else str(path), "sha256": None}
            continue
        data = Path(path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        stored = target_dir / f"{digest[:16]}_{Path(path).name}"
        if not stored.exists():
            shutil.copyfile(path, stored)
        manifest[name] = {"path": str(Path(path).relative_to(ROOT)) if Path(path).is_relative_to(ROOT) else str(path),
                          "sha256": digest, "archived_as": stored.name}
    return manifest
