#!/usr/bin/env python3
"""
AVSHUNTER - Build Packages From Discovery (hardened)

Purpose
- Reads discovery candidates for a run (CSV)
- Pins/loads a macro snapshot (macro_snapshot.json OR macro_intelligence_latest.json)
- Emits per-ticker "package" JSON files + packages/index.json for Vanguard / Light Core handoff

ACTUARIAL NOTE (2026-04 fix)
- Actuarial enrichment is NOT performed here. This script runs BEFORE Vanguard,
  so the six STATE_COLS required for lookup do not yet exist:
    vol_regime, trend_direction, structure_quality → written by Vanguard (layer2__ cols)
    adx_bucket                                     → derived from adx_14 (Vanguard)
    wyckoff_phase                                  → wyckoff_phase_bucket (Vanguard)
    macro_regime                                   → available here but insufficient alone
  pkg["actuarial"] is set to a deferred placeholder.
  Phase 8.5 (actuarial_enrichment_pass.py) runs AFTER Vanguard and patches
  every package with the real actuarial block using layer2__ columns.

Design principles
- Fail-closed: missing critical inputs => explicit error (no silent fabrication)
- Robust path resolution: works whether you are running from repo root or /scripts
- Macro snapshot locator: supports your pinned macro_snapshot.json and the Dropbox latest file

Usage (typical)
  python scripts/build_packages_from_discovery.py --run-id 20260215_020505

Common overrides
  python scripts/build_packages_from_discovery.py --run-dir data/output/runs/20260215_020505
  python scripts/build_packages_from_discovery.py --discovery-csv data/output/runs/X/discovery_candidates.csv
  python scripts/build_packages_from_discovery.py --macro-snapshot dropbox/macro/macro_intelligence_latest.json
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(_REPO_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_FOR_IMPORT))

try:
    from scripts.macro_quant_packet import build_macro_quant_packet
except Exception:
    from macro_quant_packet import build_macro_quant_packet  # type: ignore

try:
    from contracts.handoff_contract import (
        PRIORITY_DISCOVERY,
        PRIORITY_MACRO_QUANT,
        build_truth_packet_from_row,
    )
except Exception:
    from handoff_contract import (  # type: ignore
        PRIORITY_DISCOVERY,
        PRIORITY_MACRO_QUANT,
        build_truth_packet_from_row,
    )

# Data contract validator — enforces package integrity at build time
try:
    from data_contract_validator import DataContractValidator as DCV
    _DCV_AVAILABLE = True
except ImportError:
    _DCV_AVAILABLE = False

log = logging.getLogger("build_packages")


# ── Package-level safe converters (FIX-OPTIONS-01) ────────────────────────────
def _safe_float_pkg(v) -> Optional[float]:
    """Return float or None — never 0.0 for missing data."""
    if v is None or str(v).strip() in ("", "nan", "None", "N/A"):
        return None
    try:
        f = float(v)
        return None if f == 0.0 else f
    except (TypeError, ValueError):
        return None

def _safe_int(v) -> Optional[int]:
    """Return int or None."""
    if v is None or str(v).strip() in ("", "nan", "None", "N/A"):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ACTUARIAL PLACEHOLDER
# ─────────────────────────────────────────────────────────────────────────────
# pkg["actuarial"] is set to DEFERRED here. Phase 8.5 (actuarial_enrichment_pass.py)
# patches this after Vanguard runs and layer2__ state columns are available.
# Do NOT attempt actuarial lookup here — the required columns do not exist yet.

_ACTUARIAL_DEFERRED_BLOCK = {
    "available":          False,
    "deferred":           True,
    "reason":             "Awaiting Phase 8.5 actuarial_enrichment_pass",
    "no_match":           False,
    "penalty_multiplier": 1.0,
    "win_rate_10d":       0.0,
    "efficiency_10d":     0.0,
    "expected_move_10d":  0.0,
    "risk_10d":           0.0,
}


# -----------------------------
# Repo paths (robust)
# -----------------------------
HERE = Path(__file__).resolve()
REPO = HERE.parents[1]  # .../AVSHUNTER-Intelligence
RUNS_ROOT = REPO / "data" / "output" / "runs"
LATEST_RUN_PTR = REPO / "data" / "output" / "latest.json"

DEFAULT_MACRO_CANDIDATES = [
    REPO / "data" / "output" / "runs" / "TEST_PIN" / "macro_snapshot.json",
    REPO / "dropbox" / "macro" / "macro_intelligence_latest.json",
]


# -----------------------------
# IO helpers
# -----------------------------
def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# -----------------------------
# Discovery CSV auto-locate
# -----------------------------
def auto_discover_discovery_csv(run_dir: Path) -> Optional[Path]:
    patterns = ["discovery_candidates*.csv", "*discovery*.csv"]
    hits: List[Path] = []
    for pat in patterns:
        hits.extend([p for p in run_dir.rglob(pat) if p.is_file()])

    uniq: Dict[str, Path] = {}
    for p in hits:
        if any(part.lower() == "packages" for part in p.parts):
            continue
        uniq[str(p.resolve())] = p

    hits = list(uniq.values())
    if not hits:
        return None
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0]


# -----------------------------
# Macro snapshot normalisation
# -----------------------------
def normalise_macro_snapshot(raw: Dict[str, Any], source_path: Path) -> Dict[str, Any]:
    if isinstance(raw.get("macro_state"), dict) and raw.get("as_of_utc"):
        raw.setdefault("contract_version", "macro_contract_v1_0")
        return raw

    macro_state_keys = {
        "RegimeState", "DirBias", "VolMode", "TrendEnergy", "USD_State",
        "RatesImpulse", "LiquidityPulse", "SectorTilt", "RegimeDriftStatus",
        "RiskOnOffSwitch", "MacroConviction", "Notes",
    }
    if any(k in raw for k in macro_state_keys):
        as_of = raw.get("as_of_utc") or raw.get("as_of") or raw.get("timestamp_utc") or utc_now_iso()
        return {
            "contract_version": raw.get("contract_version") or "macro_contract_v1_0",
            "as_of_utc": as_of,
            "macro_state": {k: raw[k] for k in macro_state_keys if k in raw},
            "source_path": str(source_path),
            "normalised_by": "build_packages_from_discovery.py",
        }

    for candidate_key in ("macro", "macro_snapshot", "state", "macroState"):
        v = raw.get(candidate_key)
        if isinstance(v, dict) and any(k in v for k in macro_state_keys):
            as_of = raw.get("as_of_utc") or v.get("as_of_utc") or utc_now_iso()
            return {
                "contract_version": raw.get("contract_version") or "macro_contract_v1_0",
                "as_of_utc": as_of,
                "macro_state": {k: v[k] for k in macro_state_keys if k in v},
                "source_path": str(source_path),
                "normalised_by": "build_packages_from_discovery.py",
            }

    if raw.get("contract_version") and (raw.get("as_of_utc") or raw.get("normalised_at_utc")):
        raw.setdefault("as_of_utc", raw.get("normalised_at_utc") or utc_now_iso())
        return raw

    raise ValueError(
        "Macro snapshot shape not recognised. "
        "Expected macro_snapshot.json (with macro_state + as_of_utc) "
        f"or a Dropbox macro_intelligence file. Source: {source_path}"
    )


# -----------------------------
# Run/path resolution
# -----------------------------
def find_latest_run_id() -> str:
    if not LATEST_RUN_PTR.exists():
        raise FileNotFoundError(f"Missing latest run pointer: {LATEST_RUN_PTR}")
    latest = read_json(LATEST_RUN_PTR)
    run_id = (latest.get("run_id") or "").strip()
    if not run_id:
        raise ValueError(f"{LATEST_RUN_PTR} does not contain run_id")
    return run_id


def resolve_run_dir(run_id: str, run_dir_arg: Optional[str]) -> Path:
    if run_dir_arg:
        p = Path(run_dir_arg)
        p = (REPO / p).resolve() if not p.is_absolute() else p.resolve()
        if not p.exists():
            raise FileNotFoundError(f"--run-dir not found: {p}")
        return p

    if not run_id:
        run_id = find_latest_run_id()
    p = RUNS_ROOT / run_id
    if not p.exists():
        raise FileNotFoundError(f"Run directory not found: {p}")
    return p


def locate_macro_snapshot(explicit_path: Optional[str], run_dir: Path) -> Tuple[Path, Dict[str, Any]]:
    candidates: List[Path] = []

    if explicit_path:
        p = Path(explicit_path)
        candidates.append((REPO / p).resolve() if not p.is_absolute() else p.resolve())

    candidates.append(run_dir / "macro_snapshot.json")
    candidates.extend(DEFAULT_MACRO_CANDIDATES)

    archive_dir = REPO / "dropbox" / "macro" / "archive"
    if archive_dir.exists():
        archive_files = sorted(
            archive_dir.glob("macro_intelligence_normalised_*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        candidates.extend(archive_files[:5])

    tried: List[str] = []
    last_err: Optional[Exception] = None

    for c in candidates:
        tried.append(str(c))
        try:
            if c.exists():
                raw = read_json(c)
                norm = normalise_macro_snapshot(raw, c)
                return c, norm
        except Exception as e:
            last_err = e
            continue

    msg = "Unable to locate a usable macro snapshot.\nTried:\n- " + "\n- ".join(tried)
    if last_err:
        msg += f"\nLast error: {last_err}"
    raise FileNotFoundError(msg)


# -----------------------------
# Discovery CSV loading
# -----------------------------
def read_discovery_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Discovery CSV not found: {path}\n"
            f"Auto-search patterns: discovery_candidates*.csv, *discovery*.csv under: {path.parent}"
        )
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()})
    if not rows:
        raise ValueError(f"Discovery CSV is empty: {path}")
    return rows


def get_ticker(row: Dict[str, Any]) -> str:
    for k in ("ticker", "Ticker", "symbol", "Symbol"):
        v = (row.get(k) or "").strip().upper()
        if v:
            return v
    return ""


def dedupe_discovery_rows_by_ticker(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Preserve first ticker occurrence and skip later duplicates."""
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    skipped = 0
    for row in rows:
        ticker = get_ticker(row)
        if ticker and ticker in seen:
            skipped += 1
            continue
        if ticker:
            seen.add(ticker)
        deduped.append(row)
    return deduped, skipped


def ensure_us_ticker_sane(ticker: str) -> None:
    """Allow governed US share classes while blocking foreign dot suffixes."""
    if "." not in ticker:
        return

    parts = ticker.split(".")
    is_us_share_class = (
        len(parts) == 2
        and 1 <= len(parts[0]) <= 6
        and parts[0].isalpha()
        and parts[1] in {"A", "B", "C"}
    )
    if is_us_share_class:
        return

    raise ValueError(f"Universe contamination: ticker has suffix: {ticker}")


# -----------------------------
# Package builder
# -----------------------------
@dataclass
class PackageMeta:
    run_id: str
    as_of_utc: str
    macro_source: str
    discovery_csv: str


def build_package(
    ticker: str,
    discovery_row: Dict[str, Any],
    macro_snapshot: Dict[str, Any],
    meta: PackageMeta,
) -> Dict[str, Any]:
    """
    Build a single package dict.

    Key contract (all required by run_vanguard_from_packages.py):
      pkg["discovery"]           - discovery row data  (vanguard: pkg.get("discovery"))
      pkg["regime_snapshot"]     - macro regime dict   (vanguard: fail-closed gate line 175-176)
      pkg["macro"]["payload"]    - full macro snapshot (vanguard: pkg["macro"]["payload"])
      pkg["ohlcv_daily"]         - top-level OHLCV     (vanguard: checks "ohlcv_daily" in pkg first)
      pkg["actuarial"]           - actuarial state block (ev_engine + position_sizing_engine)
    """
    macro_quant_packet = build_macro_quant_packet(macro_snapshot, meta.macro_source)
    macro_snapshot.setdefault("macro_quant_packet", macro_quant_packet)
    truth_packet = build_truth_packet_from_row(
        {
            **(discovery_row or {}),
            "ticker": ticker,
            "run_id": meta.run_id,
            "run_mode": "EVENING",
        },
        source="DISCOVERY_PACKAGE",
        priority=PRIORITY_DISCOVERY,
        run_id=meta.run_id,
        run_mode="EVENING",
    )
    for _k, _v in macro_quant_packet.items():
        truth_packet.add_field(
            _k,
            _v,
            source="MACRO_QUANT",
            status="MISSING" if _v in (None, "", "UNKNOWN", "MISSING") else "CONFIRMED",
            priority=PRIORITY_MACRO_QUANT,
        )
    truth_packet.finalise()

    pkg = {
        "package_version": "v1",
        "ticker": ticker,
        "as_of_utc": meta.as_of_utc,
        "run_id": meta.run_id,
        "source": {
            "macro_snapshot": meta.macro_source,
            "discovery_csv": meta.discovery_csv,
        },

        # --- VANGUARD CONTRACT: macro keys ---
        "macro": {
            "source_path": meta.macro_source,
            "payload": macro_snapshot,
            "quant_packet": macro_quant_packet,
        },
        "regime_snapshot": macro_snapshot,
        "macro_snapshot": macro_snapshot,
        "macro_quant_packet": macro_quant_packet,
        "truth_packet": truth_packet.to_json_dict(),

        # --- VANGUARD CONTRACT: discovery key ---
        "discovery": discovery_row,

        # --- VANGUARD CONTRACT: OHLCV ---
        "ohlcv_daily": None,
        "ohlcv": None,

        # ── Data provenance ───────────────────────────────────────────────────
        "bar_data_as_of": discovery_row.get("data_as_of", None),
        "data_source":    discovery_row.get("data_source", "UNKNOWN"),

        # ── OPTIONS CONTRACT BLOCK (FIX-OPTIONS-01) ───────────────────────────
        "options_contract": {
            "dte":           _safe_int(discovery_row.get("dte")),
            "expiry":        discovery_row.get("expiry") or None,
            "strike":        _safe_float_pkg(discovery_row.get("strike")),
            "contract_type": discovery_row.get("contract_type") or discovery_row.get("direction") or None,
            "instrument":    discovery_row.get("instrument") or None,
            "bid":           _safe_float_pkg(discovery_row.get("bid")),
            "ask":           _safe_float_pkg(discovery_row.get("ask")),
            "mid":           _safe_float_pkg(discovery_row.get("mid")),
            "premium":       _safe_float_pkg(discovery_row.get("premium")),
            "spread_pct":    _safe_float_pkg(discovery_row.get("spread_pct")),
            "iv":            _safe_float_pkg(discovery_row.get("iv")),
            "ivp":           _safe_float_pkg(discovery_row.get("ivp")),
            "iv_rank":       _safe_float_pkg(discovery_row.get("iv_rank")),
            "delta":         _safe_float_pkg(discovery_row.get("delta")),
            "theta":         _safe_float_pkg(discovery_row.get("theta")),
            "gamma":         _safe_float_pkg(discovery_row.get("gamma")),
            "rr":            _safe_float_pkg(discovery_row.get("rr")),
            "max_profit":    _safe_float_pkg(discovery_row.get("max_profit")),
            "max_loss":      _safe_float_pkg(discovery_row.get("max_loss")),
            "breakeven":     _safe_float_pkg(discovery_row.get("breakeven")),
            "options_score": _safe_float_pkg(discovery_row.get("options_score")),
            "composite":     _safe_float_pkg(discovery_row.get("composite")),
            # STATUS (2026-08-19, EV audit Stage 0): structurally unpopulated at
            # package-build time. Confirmed by full census of 1,651 packages in
            # run 20260818_041214 — ev_final and ev_status are always present as
            # keys and always None. No module before this phase (Phase 5) writes
            # either field onto the discovery CSV, and that CSV's header carries
            # no ev_ column at all; EV Engine v2 (the only live producer of a
            # field named ev_status) does not run until Phase 9. Any non-null
            # value observed here in a future run indicates a new upstream
            # writer and should be investigated, not assumed correct.
            "ev_final":      _safe_float_pkg(discovery_row.get("ev_final")),
            "ev_status":     discovery_row.get("ev_status") or None,
            "options_enriched": False,
        },

        # Flat option fields at package top level for backward compat
        "dte":           _safe_int(discovery_row.get("dte")),
        "expiry":        discovery_row.get("expiry") or None,
        "strike":        _safe_float_pkg(discovery_row.get("strike")),
        "contract_type": discovery_row.get("contract_type") or discovery_row.get("direction") or None,
        "bid":           _safe_float_pkg(discovery_row.get("bid")),
        "ask":           _safe_float_pkg(discovery_row.get("ask")),
        "premium":       _safe_float_pkg(discovery_row.get("premium")),
        "iv":            _safe_float_pkg(discovery_row.get("iv")),
        "ivp":           _safe_float_pkg(discovery_row.get("ivp")),
        "rr":            _safe_float_pkg(discovery_row.get("rr")),

        # Internal timeseries store
        "timeseries": {
            "ohlcv_daily": None,
            "returns_daily": None,
            "source": None,
        },
        "data_contract": {
            "has_ohlcv_daily": False,
            "has_returns_daily": False,
            "timeseries_source": "NONE",
        },

        # ── ACTUARIAL BLOCK — set to DEFERRED ────────────────────────────────
        # Phase 8.5 (actuarial_enrichment_pass.py) patches this after Vanguard.
        # Do not attempt lookup here — layer2__ state cols do not exist yet.
        "actuarial": dict(_ACTUARIAL_DEFERRED_BLOCK),
    }

    return pkg


def enforce_data_contract(package: Dict[str, Any]) -> Dict[str, Any]:
    if _DCV_AVAILABLE:
        package, repaired, reason = DCV.attempt_repair(package)
        if repaired:
            package.setdefault("data_contract", {})["build_repair"] = reason
        package = DCV.annotate(package)
    else:
        if package.get("ohlcv") is None:
            ts = (package.get("timeseries") or {}).get("ohlcv_daily")
            if ts and len(ts) > 0:
                package["ohlcv"] = ts
                package["daily_df"] = ts
                package["data_repaired"] = True
            else:
                package["data_failure"] = True
    return package


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", type=str, default="",
                    help="Run id like 20260215_020505. Default: uses data/output/latest.json")
    ap.add_argument("--run-dir", type=str, default="",
                    help="Explicit run dir path (overrides --run-id)")
    ap.add_argument("--discovery-csv", type=str, default="",
                    help="Override discovery CSV path")
    ap.add_argument("--macro-snapshot", type=str, default="",
                    help="Override macro snapshot path")
    ap.add_argument("--out-dir", type=str, default="",
                    help="Override packages output dir (defaults to <run_dir>/packages)")
    args = ap.parse_args()

    run_dir = resolve_run_dir(args.run_id.strip(), args.run_dir.strip() or None)
    run_id = run_dir.name

    discovery_path = (
        Path(args.discovery_csv).resolve()
        if args.discovery_csv
        else (auto_discover_discovery_csv(run_dir) or (run_dir / "discovery_candidates.csv"))
    )
    discovery_rows = read_discovery_csv(discovery_path)
    discovery_rows, duplicate_rows_skipped = dedupe_discovery_rows_by_ticker(discovery_rows)

    macro_path, macro_snapshot = locate_macro_snapshot(args.macro_snapshot.strip() or None, run_dir)

    as_of_utc = macro_snapshot.get("as_of_utc") or utc_now_iso()
    pkg_dir = Path(args.out_dir).resolve() if args.out_dir else (run_dir / "packages")
    pkg_dir.mkdir(parents=True, exist_ok=True)

    meta = PackageMeta(
        run_id=run_id,
        as_of_utc=as_of_utc,
        macro_source=str(macro_path),
        discovery_csv=str(discovery_path),
    )

    # Log build start
    print(f"[BUILD_PACKAGES] Building packages for run: {run_id}")
    print(f"[BUILD_PACKAGES] Actuarial: DEFERRED to Phase 8.5")

    packages_index: List[Dict[str, Any]] = []
    built = 0
    blocked = duplicate_rows_skipped

    for row in discovery_rows:
        ticker = get_ticker(row)
        if not ticker:
            blocked += 1
            continue

        try:
            ensure_us_ticker_sane(ticker)
        except Exception as e:
            blocked += 1
            packages_index.append({
                "ticker": ticker,
                "package_path": None,
                "status": "BLOCKED",
                "reason": str(e),
            })
            continue

        pkg = build_package(ticker, row, macro_snapshot, meta)
        pkg_path = pkg_dir / f"{ticker}.package.json"

        if not pkg.get("as_of_utc"):
            pkg["as_of_utc"] = macro_snapshot.get("as_of_utc") or utc_now_iso()

        pkg = enforce_data_contract(pkg)
        write_json(pkg_path, pkg)

        packages_index.append({
            "ticker":       ticker,
            "package_path": str(pkg_path.relative_to(REPO)),
            "status":       "BUILT",
            "reason":       "",
            "actuarial":    "DEFERRED",  # patched by Phase 8.5
        })
        built += 1

    index = {
        "index_version":    "v1",
        "run_id":           run_id,
        "as_of_utc":        as_of_utc,
        "macro_source":     str(macro_path),
        "discovery_csv":    str(discovery_path),
        "packages_built":   built,
        "packages_blocked": blocked,
        "actuarial_note":   "Enrichment deferred to Phase 8.5 (actuarial_enrichment_pass.py)",
        "packages":         packages_index,
    }
    write_json(pkg_dir / "index.json", index)

    print(f"[OK] Built {built} packages, blocked {blocked}.")
    if duplicate_rows_skipped:
        print(f"     Duplicate tickers skipped: {duplicate_rows_skipped}")
    print(f"     Packages dir : {pkg_dir}")
    print(f"     Index        : {pkg_dir / 'index.json'}")
    print(f"     Macro        : {macro_path}")
    print(f"     Actuarial    : DEFERRED — Phase 8.5 will enrich after Vanguard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
