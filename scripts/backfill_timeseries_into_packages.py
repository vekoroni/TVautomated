#!/usr/bin/env python3
"""
AVSHUNTER - Backfill Daily Timeseries Into Packages (hardened)

Purpose
- For each <TICKER>.package.json in a packages dir, backfill:
    ohlcv_daily       (top-level, read directly by run_vanguard_from_packages.py)
    timeseries.ohlcv_daily  (internal store for audit)
    timeseries.returns_daily
- Sources:
    1) Local cache (if you have one)
    2) Polygon (optional; guarded by --allow-polygon flag)
    3) MarketData intraday candles for LATEST mode (optional)

Change (2026-04 — Actuarial Integration):
- Actuarial block preserved across backfill writes (never overwritten)
- data_contract actuarial_data_quality flag added: "OHLCV_OK" / "OHLCV_FAIL"
- Actuarial penalty is logged per-ticker at DEBUG level for diagnostics
- data_contract block updated with actuarial_penalty_at_build field

Design principles
- Fail-closed: if we cannot fetch a valid series, we mark flags and move on.
  We DO NOT fabricate data.
- Robust packages-dir resolution: accepts run dir OR packages dir.
- Clear diagnostics: prints closest valid candidates if path is wrong.

Usage (recommended)
  python scripts/backfill_timeseries_into_packages.py --run-id 20260215_020505 --allow-polygon

Or directly:
  python scripts/backfill_timeseries_into_packages.py --packages-dir data/output/runs/20260215_020505/packages --allow-polygon

Environment
  POLYGON_API_KEY env var must be set if --allow-polygon is used.
  MARKETDATA_API_KEY env var enables MarketData intraday candles in LATEST mode.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
import pandas as pd

# Data contract validator — single source of truth for data integrity
try:
    from data_contract_validator import DataContractValidator as DCV
    _DCV_AVAILABLE = True
except ImportError:
    _DCV_AVAILABLE = False

log = logging.getLogger("backfill_timeseries")

HERE = Path(__file__).resolve()
REPO = HERE.parents[1]
# Direct execution sets sys.path[0] to ``scripts``.  Add the repository root
# before the lazy CDS imports used by backfill_package, without changing the
# pre-existing optional-validator import behavior above.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from canonical_data.history_bridge import DEFAULT_HISTORY_MAX_STALENESS_DAYS

RUNS_ROOT = REPO / "data" / "output" / "runs"
LATEST_RUN_PTR = REPO / "data" / "output" / "latest.json"


# -----------------------------
# IO helpers
# -----------------------------
def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        canonical_history_short = False
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# -----------------------------
# Path resolution
# -----------------------------
def find_latest_run_id() -> str:
    if not LATEST_RUN_PTR.exists():
        raise FileNotFoundError(f"Missing {LATEST_RUN_PTR}")
    latest = read_json(LATEST_RUN_PTR)
    run_id = (latest.get("run_id") or "").strip()
    if not run_id:
        raise ValueError(f"{LATEST_RUN_PTR} missing run_id")
    return run_id


def list_candidate_packages_dirs(limit: int = 10) -> List[Path]:
    if not RUNS_ROOT.exists():
        return []
    dirs = []
    for d in RUNS_ROOT.iterdir():
        if d.is_dir() and (d / "packages" / "index.json").exists():
            dirs.append(d / "packages")
    dirs.sort(key=lambda x: (x.parent.stat().st_mtime if x.parent.exists() else 0), reverse=True)
    return dirs[:limit]


def resolve_packages_dir(run_id: str, run_dir: str, packages_dir: str) -> Path:
    """Resolve packages dir from any of: --packages-dir, --run-dir, --run-id, or latest.json."""
    if packages_dir:
        p = Path(packages_dir)
        p = (REPO / p).resolve() if not p.is_absolute() else p.resolve()
        if p.is_dir() and (p / "index.json").exists():
            return p
        if p.is_dir() and (p / "packages" / "index.json").exists():
            return p / "packages"
        candidates = list_candidate_packages_dirs()
        msg = f"--packages-dir not found or missing index.json: {p}\nClosest candidates:"
        for c in candidates:
            msg += f"\n- {c}"
        raise FileNotFoundError(msg)

    if run_dir:
        rd = Path(run_dir)
        rd = (REPO / rd).resolve() if not rd.is_absolute() else rd.resolve()
        p = rd / "packages"
        if (p / "index.json").exists():
            return p
        raise FileNotFoundError(f"--run-dir does not contain packages/index.json: {rd}")

    if not run_id:
        run_id = find_latest_run_id()
    p = RUNS_ROOT / run_id / "packages"
    if (p / "index.json").exists():
        return p

    candidates = list_candidate_packages_dirs()
    msg = f"Run packages dir not found: {p}\nClosest candidates:"
    for c in candidates:
        msg += f"\n- {c}"
    raise FileNotFoundError(msg)


# -----------------------------
# Actuarial block helpers
# -----------------------------
def _preserve_actuarial_block(pkg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract the actuarial block before any write so it is never lost.
    Returns the block or None if absent.
    """
    act = pkg.get("actuarial")
    if isinstance(act, dict):
        return json.loads(json.dumps(act, default=str))
    return None


def _stamp_actuarial_data_quality(pkg: Dict[str, Any], ohlcv_ok: bool) -> Dict[str, Any]:
    """
    Stamp actuarial data quality into data_contract only.

    Phase 1 locks the actuarial block as truth metadata, so this function must
    not mutate pkg["actuarial"] or compound actuarial penalties.
    """
    quality_flag = "OHLCV_OK" if ohlcv_ok else "OHLCV_FAIL"

    act = pkg.get("actuarial")

    # Mirror into data_contract for downstream consumers that read that block
    dc = pkg.setdefault("data_contract", {})
    dc["actuarial_data_quality"] = quality_flag
    if isinstance(act, dict) and act.get("penalty_multiplier") is not None:
        dc["actuarial_penalty_at_build"] = act["penalty_multiplier"]

    return pkg


# -----------------------------
# Polygon fetch
# -----------------------------
def polygon_fetch_ohlcv_daily(ticker: str, start: str, api_key: str) -> List[Dict[str, Any]]:
    """Fetch adjusted daily OHLCV bars from Polygon.io."""
    today = datetime.now(timezone.utc).date().isoformat()
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{today}"
        f"?adjusted=true&sort=asc&limit=50000&apiKey={api_key}"
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    out = []
    for r in data.get("results") or []:
        ts = int(r.get("t"))
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
        out.append({
            "date": dt,
            "open": r.get("o"),
            "high": r.get("h"),
            "low": r.get("l"),
            "close": r.get("c"),
            "volume": r.get("v"),
        })
    return out


def polygon_fetch_intraday_session(ticker: str, api_key: str,
                                   multiplier: int = 5) -> Optional[Dict[str, Any]]:
    """
    Fetch today's intraday session bars from Polygon minute aggregates
    (Stocks Starter plan — 15-minute delayed).

    Synthesises a single composite bar representing the current session:
      open   = first bar open
      high   = session high
      low    = session low
      close  = most recent bar close
      volume = cumulative session volume

    Returns None if no intraday data is available (pre-market, weekend,
    Polygon returned empty results).

    This bar is appended to the daily series so Vanguard sees today's
    partial session alongside the historical EOD series.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{multiplier}"
        f"/minute/{today}/{today}"
        f"?adjusted=true&sort=asc&limit=1000&apiKey={api_key}"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    bars = data.get("results") or []
    if not bars:
        return None

    opens  = [b.get("o") for b in bars if b.get("o") is not None]
    highs  = [b.get("h") for b in bars if b.get("h") is not None]
    lows   = [b.get("l") for b in bars if b.get("l") is not None]
    closes = [b.get("c") for b in bars if b.get("c") is not None]
    vols   = [b.get("v") for b in bars if b.get("v") is not None]

    if not closes:
        return None

    return {
        "date":             today,
        "open":             opens[0]       if opens  else closes[-1],
        "high":             max(highs)     if highs  else closes[-1],
        "low":              min(lows)      if lows   else closes[-1],
        "close":            closes[-1],
        "volume":           sum(vols)      if vols   else 0,
        "intraday_partial": True,          # flags partial session bar for downstream
        "intraday_source":  "POLYGON",
        "bar_count":        len(bars),     # number of minute bars in composite
    }


def marketdata_fetch_intraday_session(
    ticker: str,
    api_key: str,
    resolution: int = 5,
) -> Optional[Dict[str, Any]]:
    """
    Fetch today's intraday session candles from MarketData.app and synthesize
    one partial-session OHLCV bar.

    This is used only in LATEST mode. It does not replace EOD bars or create a
    hard gate; it gives downstream review layers current-session context.
    """
    if not api_key:
        return None

    today = datetime.now(timezone.utc).date().isoformat()
    params = urllib.parse.urlencode({
        "from": today,
        "to": today,
        "extended": "false",
        "adjustsplits": "true",
    })
    url = f"https://api.marketdata.app/v1/stocks/candles/{resolution}/{ticker}/?{params}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Token {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    if str(data.get("s", "")).lower() != "ok":
        return None

    opens = data.get("o") or []
    highs = data.get("h") or []
    lows = data.get("l") or []
    closes = data.get("c") or []
    vols = data.get("v") or []
    if not closes:
        return None

    clean_opens = [x for x in opens if x is not None]
    clean_highs = [x for x in highs if x is not None]
    clean_lows = [x for x in lows if x is not None]
    clean_closes = [x for x in closes if x is not None]
    clean_vols = [x for x in vols if x is not None]
    if not clean_closes:
        return None

    return {
        "date": today,
        "open": clean_opens[0] if clean_opens else clean_closes[-1],
        "high": max(clean_highs) if clean_highs else clean_closes[-1],
        "low": min(clean_lows) if clean_lows else clean_closes[-1],
        "close": clean_closes[-1],
        "volume": sum(clean_vols) if clean_vols else 0,
        "intraday_partial": True,
        "intraday_source": "MARKETDATA",
        "bar_count": len(clean_closes),
    }


# -----------------------------
# Series validation + returns
# -----------------------------
def compute_returns(closes: List[float]) -> List[Optional[float]]:
    rets: List[Optional[float]] = []
    prev = None
    for c in closes:
        if prev is None or prev == 0:
            rets.append(None)
        else:
            rets.append((c / prev) - 1.0)
        prev = c
    return rets


def validate_series(rows: List[Dict[str, Any]], min_bars: int,
                    max_staleness_days: int = DEFAULT_HISTORY_MAX_STALENESS_DAYS,
                    data_mode: str = "EOD") -> Tuple[bool, str]:
    """
    Validate that a fetched OHLCV series is usable.

    Checks:
      1. Not empty
      2. Has at least min_bars rows
      3. No nulls in critical OHLCV fields in the last 10 bars
      4. Last bar date is within max_staleness_days of today

    In LATEST mode: max_staleness_days is ignored for the last bar if it is
    flagged intraday_partial=True (today's partial session is always acceptable).
    """
    if not rows:
        return False, "EMPTY"
    if len(rows) < min_bars:
        return False, f"TOO_SHORT ({len(rows)}<{min_bars})"
    for k in ("open", "high", "low", "close", "volume"):
        if any(r.get(k) is None for r in rows[-min(10, len(rows)):]):
            return False, f"NULLS_IN_LAST_10 ({k})"
    try:
        last_bar = rows[-1]
        # In LATEST mode, a partial intraday bar is always fresh — skip staleness check
        if data_mode == "LATEST" and last_bar.get("intraday_partial"):
            return True, "OK"
        last_date = datetime.strptime(last_bar["date"], "%Y-%m-%d").date()
        days_old = (datetime.now(timezone.utc).date() - last_date).days
        if days_old > max_staleness_days:
            return False, f"STALE_LAST_BAR ({last_bar['date']}, {days_old}d old)"
    except Exception:
        pass
    return True, "OK"


# -----------------------------
# Main backfill per package
# -----------------------------
def backfill_package(
    pkg_path: Path,
    min_bars: int,
    start: str,
    allow_polygon: bool,
    api_key: str,
    allow_marketdata: bool = False,
    marketdata_api_key: str = "",
    intraday_provider: str = "auto",
    data_mode: str = "EOD",
) -> Tuple[bool, str]:
    """
    Backfill OHLCV into a single package file.

    OHLCV is written to TWO locations so both consumers work:
      pkg["ohlcv_daily"]                — top-level, read first by run_vanguard (line 258)
      pkg["timeseries"]["ohlcv_daily"]  — internal store / audit

    data_mode controls bar source:
      EOD    — daily bars only, requires post-close data (default)
      LATEST — daily bars + today's intraday session bar appended.
               The intraday bar is flagged intraday_partial=True so
               downstream modules apply EOD thresholds correctly.

    ACTUARIAL CONTRACT:
      - The actuarial block written by build_packages_from_discovery.py is NEVER
        overwritten — it is extracted before write and re-injected after.
      - data_contract actuarial_data_quality is stamped: "OHLCV_OK" or "OHLCV_FAIL"
      - pkg["actuarial"] is preserved exactly; no actuarial fields are recomputed
    """
    pkg = read_json(pkg_path)
    ticker = (pkg.get("ticker") or "").strip().upper()
    if not ticker:
        return False, "MISSING_TICKER"

    # ── Preserve actuarial block before any write ─────────────────────────────
    actuarial_snapshot = _preserve_actuarial_block(pkg)
    if actuarial_snapshot:
        log.debug(
            "%s  actuarial: penalty=%.3f depth=%d valid=%s",
            ticker,
            actuarial_snapshot.get("penalty_multiplier", 1.0),
            actuarial_snapshot.get("fallback_depth", 0),
            actuarial_snapshot.get("valid", False),
        )

    pkg.setdefault("timeseries", {})
    pkg.setdefault("data_contract", {})

    dc = pkg["data_contract"]
    ts = pkg["timeseries"]

    # CDS-2 ACTIVE: a canonical hit may short-circuit only when its final bar
    # satisfies the same freshness contract enforced by Vanguard.
    canonical = None
    _canonical_reader = None
    try:
        from canonical_data.history_bridge import (
            canonical_history_is_fresh,
            history_staleness_days,
            observe_shadow_history,
            read_canonical_history,
        )
        _canonical_reader = read_canonical_history
        canonical = read_canonical_history(ticker, max_staleness_days=None)
        canonical_history_short = canonical is not None and len(canonical) < min_bars
        canonical_fresh = canonical_history_is_fresh(canonical)
        if canonical is not None and len(canonical) >= min_bars and canonical_fresh:
            canonical = canonical.copy()
            canonical["date"] = pd.to_datetime(canonical["date"]).dt.strftime("%Y-%m-%d")
            rows = canonical.to_dict(orient="records")
            closes = [float(row["close"]) for row in rows]
            returns = compute_returns(closes)
            returns_rows = [
                {"date": rows[index]["date"], "ret": returns[index]}
                for index in range(len(rows))
            ]
            last_bar_date = rows[-1]["date"]
            as_of = last_bar_date + "T00:00:00Z"
            ts.update({
                "ohlcv_daily": rows,
                "returns_daily": returns_rows,
                "source": "CANONICAL_HISTORICAL_PRICE_DB",
                "as_of_utc": as_of,
                "last_bar_utc": as_of,
            })
            pkg["ohlcv_daily"] = rows
            pkg["daily_df"] = rows
            pkg["ohlcv"] = rows
            pkg["as_of_utc"] = as_of
            pkg["bar_data_as_of"] = last_bar_date
            pkg["bar_data_source"] = "CANONICAL_HISTORICAL_PRICE_DB"
            pkg["intraday_partial"] = False
            pkg["intraday_source"] = ""
            dc.update({
                "has_ohlcv_daily": True,
                "has_returns_daily": True,
                "timeseries_source": "CANONICAL_HISTORICAL_PRICE_DB",
                "canonical_freshness_status": "FRESH_REUSED",
                "intraday_partial": False,
                "intraday_source": "",
            })
            try:
                last_date = datetime.strptime(last_bar_date, "%Y-%m-%d").date()
                pkg["bar_data_days_old"] = (
                    datetime.now(timezone.utc).date() - last_date
                ).days
            except Exception:
                pkg["bar_data_days_old"] = -1
            if actuarial_snapshot is not None:
                pkg["actuarial"] = actuarial_snapshot
            pkg = _stamp_actuarial_data_quality(pkg, ohlcv_ok=True)
            write_json(pkg_path, pkg)
            return True, "CANONICAL_HISTORICAL_PRICE_DB"

        if canonical is not None and not canonical.empty:
            canonical_last = pd.to_datetime(
                canonical["date"], errors="coerce"
            ).max()
            dc.update({
                "canonical_freshness_status": "STALE_REFRESH_REQUIRED",
                "canonical_stale_as_of": (
                    canonical_last.date().isoformat()
                    if pd.notna(canonical_last) else "UNKNOWN"
                ),
                "canonical_staleness_days": (
                    history_staleness_days(canonical_last)
                    if pd.notna(canonical_last) else None
                ),
            })

        existing_for_shadow = pkg.get("ohlcv_daily")
        if isinstance(existing_for_shadow, list) and existing_for_shadow:
            observe_shadow_history(
                ticker, pd.DataFrame(existing_for_shadow), consumer="PACKAGE_BACKFILL"
            )
    except Exception as error:
        log.debug("%s CDS-2 canonical bridge unavailable: %s", ticker, error)

    # ── Already present and fresh — skip, but stamp actuarial quality ─────────
    existing = pkg.get("ohlcv_daily")
    if isinstance(existing, list) and len(existing) >= min_bars:
        data_is_fresh = False
        try:
            last_date_str = existing[-1].get("date", "")
            if last_date_str:
                last_dt = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                days_old = (datetime.now(timezone.utc).date() - last_dt).days
                data_is_fresh = days_old <= 1
        except Exception:
            data_is_fresh = True
        if data_is_fresh:
            dc.update({"has_ohlcv_daily": True, "timeseries_source": ts.get("source") or "CACHED"})
            # SPRINT 1: stamp staleness fields even on cached-fresh path
            try:
                _last_dt = datetime.strptime(last_date_str[:10], "%Y-%m-%d").date()
                pkg["bar_data_days_old"] = (datetime.now(timezone.utc).date() - _last_dt).days
                pkg["bar_data_as_of"]    = last_date_str[:10]
            except Exception:
                pkg["bar_data_days_old"] = -1
            # Re-inject actuarial with quality stamp
            if actuarial_snapshot is not None:
                pkg["actuarial"] = actuarial_snapshot
            pkg = _stamp_actuarial_data_quality(pkg, ohlcv_ok=True)
            write_json(pkg_path, pkg)
            return True, "ALREADY_PRESENT"

    # ── Promote from timeseries sub-dict ─────────────────────────────────────
    existing_ts = ts.get("ohlcv_daily")
    if isinstance(existing_ts, list) and len(existing_ts) >= min_bars:
        pkg["ohlcv_daily"] = existing_ts
        pkg["daily_df"]    = existing_ts
        pkg["ohlcv"]       = existing_ts
        pkg["as_of_utc"]   = ts.get("as_of_utc") or pkg.get("as_of_utc") or utc_now_iso()
        dc.update({"has_ohlcv_daily": True, "timeseries_source": ts.get("source") or "CACHED"})
        if actuarial_snapshot is not None:
            pkg["actuarial"] = actuarial_snapshot
        pkg = _stamp_actuarial_data_quality(pkg, ohlcv_ok=True)
        write_json(pkg_path, pkg)
        return True, "PROMOTED_FROM_TIMESERIES"

    if not allow_polygon:
        dc.update({"has_ohlcv_daily": False, "has_returns_daily": False, "timeseries_source": "NONE"})
        ts.update({"ohlcv_daily": None, "returns_daily": None, "source": None, "as_of_utc": utc_now_iso()})
        pkg["ohlcv_daily"] = None
        if actuarial_snapshot is not None:
            pkg["actuarial"] = actuarial_snapshot
        pkg = _stamp_actuarial_data_quality(pkg, ohlcv_ok=False)
        write_json(pkg_path, pkg)
        return False, "NO_SOURCE_ALLOWED"

    if not api_key:
        return False, "POLYGON_API_KEY_MISSING"

    try:
        provider_start = start
        if (
            canonical is not None
            and not canonical.empty
            and "date" in canonical.columns
            and not canonical_history_short
        ):
            canonical_last = pd.to_datetime(
                canonical["date"], errors="coerce"
            ).max()
            if pd.notna(canonical_last):
                provider_start = (
                    canonical_last.date() + timedelta(days=1)
                ).isoformat()
        rows = polygon_fetch_ohlcv_daily(
            ticker, start=provider_start, api_key=api_key
        )

        # Persist the completed daily series before adding any intraday partial
        # bar to the package. This is a no-op unless CDS write-through is on.
        if rows:
            from canonical_data.history_bridge import write_through_fetched_history
            write_through_fetched_history(
                ticker,
                rows,
                provider="POLYGON",
                source_kind="PACKAGE_BACKFILL",
                source_run_id=str(pkg.get("run_id") or "") or None,
                partial_current_session=(data_mode == "LATEST"),
            )

            # Re-read the governed full series after the missing tail commits.
            # Validating the delta alone would incorrectly fail MIN_BARS.
            if _canonical_reader is not None:
                refreshed = _canonical_reader(ticker)
                if refreshed is not None and not refreshed.empty:
                    refreshed = refreshed.copy()
                    refreshed["date"] = pd.to_datetime(
                        refreshed["date"], errors="coerce"
                    ).dt.strftime("%Y-%m-%d")
                    rows = refreshed.to_dict(orient="records")
                    dc["canonical_freshness_status"] = (
                        "REFRESHED_FROM_PROVIDER_FULL_HISTORY"
                        if canonical_history_short
                        else "REFRESHED_FROM_PROVIDER_TAIL"
                    )

        # LATEST mode: append today's intraday session bar if available.
        # This gives Vanguard a partial view of today's session alongside the
        # historical EOD series. Bar is flagged intraday_partial=True so
        # downstream modules (MVE, TCE) apply EOD thresholds appropriately.
        _intraday_appended = False
        _intraday_source = ""
        if data_mode == "LATEST":
            _provider = str(intraday_provider or "auto").lower().strip()
            _intraday_bar = None
            if allow_marketdata and _provider in {"auto", "marketdata"}:
                _intraday_bar = marketdata_fetch_intraday_session(
                    ticker,
                    api_key=marketdata_api_key,
                )
            if _intraday_bar is None and allow_polygon and _provider in {"auto", "polygon"}:
                _intraday_bar = polygon_fetch_intraday_session(ticker, api_key=api_key)
            if _intraday_bar:
                # Only append if today's bar is not already the last daily bar
                _today = datetime.now(timezone.utc).date().isoformat()
                if not rows or rows[-1].get("date") != _today:
                    rows.append(_intraday_bar)
                    _intraday_appended = True
                    _intraday_source = str(_intraday_bar.get("intraday_source") or "UNKNOWN")

        ok, reason = validate_series(rows, min_bars=min_bars, data_mode=data_mode)
        if not ok:
            dc.update({"has_ohlcv_daily": False, "has_returns_daily": False, "timeseries_source": "POLYGON_BAD"})
            ts.update({"ohlcv_daily": None, "returns_daily": None, "source": "POLYGON_BAD",
                       "as_of_utc": utc_now_iso(), "error": reason})
            pkg["ohlcv_daily"] = None
            if actuarial_snapshot is not None:
                pkg["actuarial"] = actuarial_snapshot
            pkg = _stamp_actuarial_data_quality(pkg, ohlcv_ok=False)
            write_json(pkg_path, pkg)
            return False, reason

        closes = [float(r["close"]) for r in rows]
        returns = compute_returns(closes)
        returns_rows = [{"date": rows[i]["date"], "ret": returns[i]} for i in range(len(rows))]

        last_bar_date = rows[-1]["date"] if rows else None
        as_of = (last_bar_date + "T00:00:00Z") if last_bar_date else utc_now_iso()

        # Source label reflects whether intraday was appended
        _source = f"{_intraday_source}_INTRADAY" if _intraday_appended and _intraday_source else "POLYGON"

        ts.update({
            "ohlcv_daily":    rows,
            "returns_daily":  returns_rows,
            "source":         _source,
            "as_of_utc":      as_of,
            "last_bar_utc":   as_of,
        })
        pkg["ohlcv_daily"]        = rows
        pkg["daily_df"]           = rows
        pkg["ohlcv"]              = rows if len(rows) >= 20 else None
        pkg["as_of_utc"]          = as_of
        pkg["bar_data_as_of"]     = last_bar_date or as_of
        pkg["bar_data_source"]    = _source
        pkg["intraday_partial"]   = _intraday_appended
        pkg["intraday_source"]    = _intraday_source if _intraday_appended else ""

        # SPRINT 1: Stamp bar_data_days_old
        try:
            _last_dt = datetime.strptime(last_bar_date[:10], "%Y-%m-%d").date() if last_bar_date else None
            pkg["bar_data_days_old"] = (datetime.now(timezone.utc).date() - _last_dt).days if _last_dt else -1
        except Exception:
            pkg["bar_data_days_old"] = -1

        dc.update({
            "has_ohlcv_daily":    True,
            "has_returns_daily":  True,
            "timeseries_source":  _source,
            "intraday_partial":   _intraday_appended,
            "intraday_source":    _intraday_source if _intraday_appended else "",
        })

        if _DCV_AVAILABLE:
            pkg = DCV.annotate(pkg)
            ok_dcv, dcv_reason = DCV.validate(pkg)
            if not ok_dcv:
                dc.update({"has_ohlcv_daily": False, "timeseries_source": "POLYGON_DCV_FAIL",
                           "dcv_fail_reason": dcv_reason})
                if actuarial_snapshot is not None:
                    pkg["actuarial"] = actuarial_snapshot
                pkg = _stamp_actuarial_data_quality(pkg, ohlcv_ok=False)
                write_json(pkg_path, pkg)
                return False, f"DCV_FAIL:{dcv_reason}"

        # Re-inject actuarial block and stamp quality before final write
        if actuarial_snapshot is not None:
            pkg["actuarial"] = actuarial_snapshot
        pkg = _stamp_actuarial_data_quality(pkg, ohlcv_ok=True)

        write_json(pkg_path, pkg)
        return True, _source

    except Exception as e:
        dc.update({"has_ohlcv_daily": False, "has_returns_daily": False, "timeseries_source": "POLYGON_ERROR"})
        ts.update({"ohlcv_daily": None, "returns_daily": None, "source": "POLYGON_ERROR",
                   "as_of_utc": utc_now_iso(), "error": str(e)})
        pkg["ohlcv_daily"] = None
        if actuarial_snapshot is not None:
            pkg["actuarial"] = actuarial_snapshot
        pkg = _stamp_actuarial_data_quality(pkg, ohlcv_ok=False)
        write_json(pkg_path, pkg)
        return False, "POLYGON_ERROR"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", type=str, default="",
                    help="Run id like 20260215_020505 (optional if --packages-dir given).")
    ap.add_argument("--run-dir", type=str, default="",
                    help="Run directory path (optional). Uses <run-dir>/packages.")
    ap.add_argument("--packages-dir", type=str, default="",
                    help="Packages directory path (must contain index.json).")
    ap.add_argument("--min-bars", type=int, default=120,
                    help="Minimum daily bars required.")
    ap.add_argument("--start", type=str, default="2018-01-01",
                    help="Start date (YYYY-MM-DD) for Polygon history fetch.")
    ap.add_argument("--allow-polygon", action="store_true",
                    help="Allow Polygon API fetch.")
    ap.add_argument("--allow-marketdata", action="store_true",
                    help="Allow MarketData.app intraday candles in LATEST mode.")
    ap.add_argument("--intraday-provider", choices=["auto", "marketdata", "polygon"],
                    default="auto",
                    help="Intraday source for LATEST mode. auto tries MarketData then Polygon.")
    ap.add_argument(
        "--data-mode",
        choices=["EOD", "LATEST"],
        default="EOD",
        help=(
            "Bar data mode. "
            "EOD (default): daily bars only — use after 16:15 ET for complete bars. "
            "LATEST: daily bars + today's intraday session bar from minute aggregates "
            "(Polygon Stocks Starter). Safe to run at any time. Partial session bar "
            "is appended and flagged intraday_partial=True for downstream modules."
        ),
    )
    ap.add_argument("--limit", type=int, default=0,
                    help="Limit packages processed (0=all).")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="Seconds to sleep between Polygon calls (rate-limit safety).")
    args = ap.parse_args()

    pkg_dir = resolve_packages_dir(
        args.run_id.strip(), args.run_dir.strip(), args.packages_dir.strip()
    )
    index_path = pkg_dir / "index.json"
    idx = read_json(index_path)
    pkgs = idx.get("packages") or []
    if not pkgs:
        raise SystemExit(f"index.json has no packages: {index_path}")

    if args.limit and args.limit > 0:
        pkgs = pkgs[:args.limit]

    api_key = os.environ.get("POLYGON_API_KEY", "").strip()
    marketdata_api_key = os.environ.get("MARKETDATA_API_KEY", "").strip()
    if not api_key:
        env_path = REPO / ".env"
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("POLYGON_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except Exception:
                pass
    if not marketdata_api_key:
        env_path = REPO / ".env"
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("MARKETDATA_API_KEY="):
                        marketdata_api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except Exception:
                pass

    if not api_key and args.allow_polygon:
        raise SystemExit(
            "ERROR: POLYGON_API_KEY not set.\n"
            "Add it to your environment or create a .env file at the repo root:\n"
            "  POLYGON_API_KEY=your_key_here\n"
            "Then re-run with --allow-polygon."
        )
    if args.allow_marketdata and not marketdata_api_key:
        log.warning("MARKETDATA_API_KEY not set; MarketData intraday unavailable.")

    ok_count = 0
    fail_count = 0
    # Actuarial quality counters
    act_ohlcv_ok = 0
    act_ohlcv_fail = 0
    stats: Dict[str, int] = {}
    total = len(pkgs)

    for i, rec in enumerate(pkgs, start=1):
        status = rec.get("status")
        pkg_path_raw = rec.get("package_path")
        ticker = rec.get("ticker") or "UNKNOWN"

        if status != "BUILT" or not pkg_path_raw:
            continue

        pkg_path = Path(pkg_path_raw)
        if not pkg_path.is_absolute():
            pkg_path = (REPO / pkg_path).resolve()

        success, reason = backfill_package(
            pkg_path=pkg_path,
            min_bars=args.min_bars,
            start=args.start,
            allow_polygon=args.allow_polygon,
            api_key=api_key,
            allow_marketdata=args.allow_marketdata,
            marketdata_api_key=marketdata_api_key,
            intraday_provider=args.intraday_provider,
            data_mode=args.data_mode,
        )

        stats[reason] = stats.get(reason, 0) + 1
        if success:
            ok_count += 1
            act_ohlcv_ok += 1
        else:
            fail_count += 1
            act_ohlcv_fail += 1

        if args.sleep and args.sleep > 0:
            time.sleep(args.sleep)

        if i % 25 == 0:
            print(f"[PROGRESS] {i}/{total} processed  ok={ok_count} fail={fail_count}", flush=True)

    print("[DONE]", flush=True)
    print(f"Packages dir    : {pkg_dir}", flush=True)
    print(f"Backfilled OK   : {ok_count}", flush=True)
    print(f"Failed          : {fail_count}", flush=True)
    print(f"Actuarial stamp : OHLCV_OK={act_ohlcv_ok} | OHLCV_FAIL={act_ohlcv_fail}", flush=True)
    print("Reasons:", flush=True)
    for k in sorted(stats.keys()):
        print(f"  - {k}: {stats[k]}", flush=True)
    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
