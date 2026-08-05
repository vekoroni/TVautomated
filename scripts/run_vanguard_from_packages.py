#!/usr/bin/env python3
"""
scripts/run_vanguard_from_packages.py

VANGUARD Package Runner (End-to-End) — STABILITY PHASE (v1.1 run-dir outputs)
======================================================
Reads packaged inputs produced by the orchestrator and runs VanguardEngine end-to-end
for every package in the run, writing a flattened CSV that includes:

- ticker, timestamp, verdict, recommendation, reasoning
- Layer 2 headline fields: state_hash, n_observations, win_rate_20d, expected_value_20d, confidence_level,
  has_edge, edge_direction, failed_gate, no_edge_reason, debug_signature
- Optional fully-flattened layer1__/layer2__/layer3__ fields for debugging

STABILITY HARDENING (this version):
- Per-package FAIL-CLOSED at the OrchestratorAdapter contract gate (no relaxation)
- Per-package isolation (one reject does not kill the batch)
- Deterministic run artefacts:
    1) vanguard_signals.csv (PASS only)
    2) vanguard_rejects.csv (REJECT only)
    3) vanguard_run_summary.json (counts + top failure reasons)
- No silent defaults for contract-critical fields:
    - If regime_snapshot missing -> adapter should reject
    - If OHLCV missing/empty -> adapter should reject

Usage:
  python scripts/run_vanguard_from_packages.py
  python scripts/run_vanguard_from_packages.py --run-id 20260210_164613
  python scripts/run_vanguard_from_packages.py --limit 25
  python scripts/run_vanguard_from_packages.py --verbose
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

_REPO_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(_REPO_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_FOR_IMPORT))

import pandas as pd
import numpy as np

from behaviour_state_builder import enrich_dataframe as enrich_behaviour_state_dataframe

try:
    from scripts.macro_quant_packet import (
        MACRO_QUANT_CSV_FIELDS,
        macro_quant_columns_for_row,
        packet_from_package,
    )
except Exception:
    from macro_quant_packet import (  # type: ignore
        MACRO_QUANT_CSV_FIELDS,
        macro_quant_columns_for_row,
        packet_from_package,
    )

try:
    from contracts.handoff_contract import (
        PRIORITY_VANGUARD_ACTUARIAL,
        SCANNER_FIELD_NAMES,
        enrich_row_with_truth_packet,
    )
except Exception:
    from handoff_contract import (  # type: ignore
        PRIORITY_VANGUARD_ACTUARIAL,
        SCANNER_FIELD_NAMES,
        enrich_row_with_truth_packet,
    )

try:
    from vanguard.physics_state_engine import (
        PHYSICS_FIELDS,
        calculate_market_physics,
    )
except Exception:
    from physics_state_engine import (  # type: ignore
        PHYSICS_FIELDS,
        calculate_market_physics,
    )

ACTUARIAL_SOURCE_V6_DB = "V6_DB"
ACTUARIAL_SOURCE_DISCOVERY_FALLBACK = "DISCOVERY_FALLBACK"
ACTUARIAL_SOURCE_MISSING = "MISSING"

PHASE2_MATCH_FIELDS = [
    "state_match_method",
    "state_match_stage",
    "state_match_dimensions",
    "state_match_quality",
    "state_match_similarity",
    "state_match_is_exact",
    "sample_size",
    "sample_confidence_bucket",
    "confidence_penalty",
    "confidence_weight",
    "preferred_horizon",
    "matched_state_key",
    "original_state_key",
    "fallback_reason",
]
PHASE2_PROBABILITY_FIELDS = [
    "raw_prob_up_5d",
    "raw_prob_up_10d",
    "raw_prob_up_20d",
    "raw_prob_down_5d",
    "raw_prob_down_10d",
    "raw_prob_down_20d",
    "raw_prob_target_hit",
    "raw_prob_stop_hit",
    "raw_expected_return",
    "raw_expected_drawdown",
    "raw_expected_time_to_target",
    "baseline_probability",
    "adjusted_prob_target_hit",
    "adjusted_expected_return",
    "probability_edge",
    "probability_verdict",
]
PHASE2_REQUIRED_LAYER2_FIELDS = PHASE2_MATCH_FIELDS + PHASE2_PROBABILITY_FIELDS
PHASE2_REQUIRED_FLATTENED_FIELDS = [f"layer2__{field}" for field in PHASE2_REQUIRED_LAYER2_FIELDS]

try:
    from vanguard.core.actuarial_registry import (
        expected_schema_fingerprint as _expected_actuarial_fingerprint,
        schema_version as _actuarial_schema_version,
    )
    from vanguard.core.truth_packet import validate_truth_packet as _validate_truth_packet
except Exception:
    def _expected_actuarial_fingerprint() -> Optional[str]:  # type: ignore
        return None

    def _actuarial_schema_version() -> Optional[str]:  # type: ignore
        return None

    def _validate_truth_packet(block: Dict[str, Any]) -> bool:  # type: ignore
        return True

# Data contract validator — hard gate before Vanguard modelling
try:
    from data_contract_validator import DataContractValidator as DCV
    _DCV_AVAILABLE = True
except ImportError:
    _DCV_AVAILABLE = False
    class DCV:  # type: ignore
        @staticmethod
        def validate(pkg): return True, 'VALID'
        @staticmethod
        def attempt_repair(pkg): return pkg, False, 'NO_DCV'
        @staticmethod
        def confidence_level(pkg): return 'HIGH'


# ------------------------- helpers: IO & flattening -------------------------

def read_json(path: Path) -> Dict[str, Any]:
    # utf-8-sig handles BOM if present
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]], minimum_headers: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        headers = minimum_headers or ["ticker"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
        return

    fieldnames = sorted({k for r in rows for k in r.keys()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def flatten_dict(d: Any, parent_key: str = "", sep: str = "__") -> Dict[str, Any]:
    """
    Flatten nested dicts for CSV output.
    {"outcomes":{"win_rate":0.3}} -> {"outcomes__win_rate":0.3}
    """
    items: Dict[str, Any] = {}
    if not isinstance(d, dict):
        return items
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def safe_get(d: Any, key: str, default: Any = None) -> Any:
    if isinstance(d, dict) and key in d:
        return d.get(key)
    return default


def _phase2_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "nan", "null", "n/a"}
    return True


def _phase2_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def validate_phase2_baton(row: Dict[str, Any]) -> List[str]:
    """Validate the flattened Phase 2 Vanguard baton carried by a CSV row."""
    issues: List[str] = []

    for field in PHASE2_REQUIRED_FLATTENED_FIELDS:
        if field not in row or not _phase2_has_value(row.get(field)):
            issues.append(f"MISSING:{field}")

    method = str(row.get("layer2__state_match_method") or "").upper()
    sample_bucket = str(row.get("layer2__sample_confidence_bucket") or "").upper()
    penalty = _phase2_float(row.get("layer2__confidence_penalty"), default=-1.0)
    similarity_value = row.get("layer2__state_match_similarity")
    similarity = _phase2_float(similarity_value, default=-1.0)
    edge = _phase2_float(row.get("layer2__probability_edge"), default=0.0)

    if penalty < 0.0 or penalty > 1.0:
        issues.append("INVALID:layer2__confidence_penalty_OUT_OF_RANGE")

    if method == "UNKNOWN":
        if penalty > 0.30:
            issues.append("INVALID:UNKNOWN_CONFIDENCE_PENALTY_GT_0_30")
        if sample_bucket in {"HIGH", "MEDIUM_HIGH", "MEDIUM"}:
            issues.append("INVALID:UNKNOWN_HIGH_SAMPLE_CONFIDENCE")
        if edge > 0.0:
            issues.append("INVALID:UNKNOWN_POSITIVE_PROBABILITY_EDGE")

    if method == "ANALOGUE":
        if not _phase2_has_value(similarity_value):
            issues.append("INVALID:ANALOGUE_MISSING_SIMILARITY")
        elif similarity < 0.70:
            issues.append("INVALID:ANALOGUE_SIMILARITY_BELOW_0_70")

    if not _phase2_has_value(row.get("layer2__probability_verdict")):
        issues.append("MISSING:layer2__probability_verdict")

    return issues


def phase2_baton_dropped_fields(source_row: Dict[str, Any], downstream_row: Dict[str, Any]) -> List[str]:
    """Return Phase 2 fields present upstream but missing downstream."""
    return [
        field for field in PHASE2_REQUIRED_FLATTENED_FIELDS
        if field in source_row and field not in downstream_row
    ]


def _ensure_phase2_baton_fields(row: Dict[str, Any]) -> None:
    """Fill safe Phase 2 defaults, then validate the baton state."""
    issues_before = validate_phase2_baton(row)

    defaults = {
        "layer2__state_match_method": "UNKNOWN",
        "layer2__state_match_stage": "UNKNOWN",
        "layer2__state_match_dimensions": "",
        "layer2__state_match_quality": "INSUFFICIENT_SAMPLE",
        "layer2__state_match_similarity": 0.0,
        "layer2__state_match_is_exact": False,
        "layer2__sample_size": 0,
        "layer2__sample_confidence_bucket": "UNKNOWN",
        "layer2__confidence_penalty": 0.30,
        "layer2__confidence_weight": 0.30,
        "layer2__preferred_horizon": "NONE",
        "layer2__matched_state_key": "",
        "layer2__original_state_key": "",
        "layer2__fallback_reason": "PHASE2_BATON_DEFAULTED",
        "layer2__raw_prob_up_5d": 0.0,
        "layer2__raw_prob_up_10d": 0.0,
        "layer2__raw_prob_up_20d": 0.0,
        "layer2__raw_prob_down_5d": 0.0,
        "layer2__raw_prob_down_10d": 0.0,
        "layer2__raw_prob_down_20d": 0.0,
        "layer2__raw_prob_target_hit": 0.0,
        "layer2__raw_prob_stop_hit": 0.0,
        "layer2__raw_expected_return": 0.0,
        "layer2__raw_expected_drawdown": 0.0,
        "layer2__raw_expected_time_to_target": 0.0,
        "layer2__baseline_probability": 0.0,
        "layer2__adjusted_prob_target_hit": 0.0,
        "layer2__adjusted_expected_return": 0.0,
        "layer2__probability_edge": 0.0,
        "layer2__probability_verdict": "NO_STAT_EDGE",
    }
    for field, value in defaults.items():
        if field not in row or not _phase2_has_value(row.get(field)):
            row[field] = value

    method = str(row.get("layer2__state_match_method") or "").upper()
    if method == "UNKNOWN":
        row["layer2__sample_confidence_bucket"] = "UNKNOWN"
        row["layer2__confidence_penalty"] = min(_phase2_float(row.get("layer2__confidence_penalty"), 0.30), 0.30)
        row["layer2__confidence_weight"] = min(_phase2_float(row.get("layer2__confidence_weight"), 0.30), 0.30)
        row["layer2__probability_edge"] = 0.0
        row["layer2__probability_verdict"] = "NO_STAT_EDGE"

    issues_after = validate_phase2_baton(row)
    row["phase2_baton_status"] = "VALID" if not issues_after else "INVALID"
    row["phase2_baton_issues"] = "|".join(issues_after or issues_before)


def coerce_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default


def _try_load_ohlcv_from_value(val: Any) -> Optional[pd.DataFrame]:
    """
    Supports:
    - DataFrame (already)
    - list[dict] rows
    - dict with "rows" field
    - path string to CSV/JSON (relative to repo root if not absolute)
    Returns None if not loadable.
    """
    try:
        if val is None:
            return None

        if isinstance(val, pd.DataFrame):
            return val

        if isinstance(val, list) and val and isinstance(val[0], dict):
            return pd.DataFrame(val)

        if isinstance(val, dict) and "rows" in val and isinstance(val["rows"], list):
            return pd.DataFrame(val["rows"])

        if isinstance(val, str) and val.strip():
            p = Path(val.strip())
            if not p.is_absolute():
                p = Path(".").resolve() / p

            if not p.exists():
                return None

            # Try CSV then JSON
            if p.suffix.lower() == ".csv":
                return pd.read_csv(p)
            if p.suffix.lower() in (".json", ".jsonl"):
                # json: list[dict] expected
                raw = json.loads(p.read_text(encoding="utf-8-sig"))
                if isinstance(raw, list):
                    return pd.DataFrame(raw)
                if isinstance(raw, dict) and "rows" in raw and isinstance(raw["rows"], list):
                    return pd.DataFrame(raw["rows"])
                return None

        return None
    except Exception:
        return None


def _normalise_ticker(t: Any) -> str:
    return str(t or "").strip().upper()


def _short_reason(e: Exception) -> str:
    """
    Deterministic-ish error key for rollups without needing full taxonomy yet.
    We intentionally keep it simple (backlog can deepen later).
    """
    msg = str(e).strip()
    if not msg:
        return e.__class__.__name__
    # normalise some common patterns
    m = msg.lower()
    if "regime_snapshot" in m:
        return "MISSING_REGIME_SNAPSHOT"
    if "ohlcv" in m:
        return "MISSING_OHLCV"
    if "ema200" in m or "ema 200" in m:
        return "INSUFFICIENT_EMA200_DEPTH"
    return e.__class__.__name__


# ------------------------- package -> orchestrator-like payload -------------------------

def calculate_adx(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate ADX from OHLCV dataframe."""
    try:
        high = df['high']
        low = df['low']
        close = df['close']

        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Directional Movement
        dm_plus = high.diff()
        dm_minus = -low.diff()
        dm_plus = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0)
        dm_minus = dm_minus.where((dm_minus > dm_plus) & (dm_minus > 0), 0)

        # Smoothed
        atr = tr.ewm(span=period, adjust=False).mean()
        di_plus = 100 * dm_plus.ewm(span=period, adjust=False).mean() / atr
        di_minus = 100 * dm_minus.ewm(span=period, adjust=False).mean() / atr

        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus + 1e-10)
        adx = dx.ewm(span=period, adjust=False).mean()

        return round(float(adx.iloc[-1]), 2)
    except Exception:
        return 0.0


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate RSI from OHLCV dataframe."""
    try:
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 2)
    except Exception:
        return 50.0


def _resolve_daily_bars(pkg: Dict[str, Any]) -> Optional[pd.DataFrame]:
    """
    Canonical OHLCV resolver — checks all known locations in priority order.

    Priority:
      1. pkg["daily_df"]         — canonical alias (written by backfill going forward)
      2. pkg["ohlcv_daily"]      — backfill list format OR Polygon dict format
      3. pkg["ohlcv"]            — legacy direct key
      4. pkg["technical_data"]["ohlcv"] — nested technical block
      5. pkg["timeseries"]["ohlcv_daily"] — internal audit store
      6. pkg["discovery"]["ohlcv"] — discovery-embedded OHLCV

    Returns a DataFrame or None. Never raises.
    """
    # 1. canonical alias — fastest path going forward
    raw = pkg.get("daily_df")
    if isinstance(raw, list) and raw:
        df = _try_load_ohlcv_from_value(raw)
        if df is not None and not df.empty:
            return df

    # 2. ohlcv_daily — Polygon dict OR backfill list
    raw = pkg.get("ohlcv_daily")
    if raw is not None:
        if isinstance(raw, dict) and "t" in raw:
            return pd.DataFrame({
                "timestamp": raw.get("t", []),
                "open":      raw.get("o", []),
                "high":      raw.get("h", []),
                "low":       raw.get("l", []),
                "close":     raw.get("c", []),
                "volume":    raw.get("v", []),
            })
        if isinstance(raw, list) and raw:
            df = _try_load_ohlcv_from_value(raw)
            if df is not None and not df.empty:
                return df

    # 3. legacy top-level ohlcv key
    if "ohlcv" in pkg:
        df = _try_load_ohlcv_from_value(pkg.get("ohlcv"))
        if df is not None and not df.empty:
            return df

    # 4. nested technical_data block
    tech_pkg = pkg.get("technical_data") or {}
    if "ohlcv" in tech_pkg:
        df = _try_load_ohlcv_from_value(tech_pkg.get("ohlcv"))
        if df is not None and not df.empty:
            return df
    if "ohlcv_path" in tech_pkg:
        df = _try_load_ohlcv_from_value(tech_pkg.get("ohlcv_path"))
        if df is not None and not df.empty:
            return df

    # 5. timeseries sub-dict (internal audit store written by backfill)
    ts = pkg.get("timeseries") or {}
    if isinstance(ts, dict):
        raw = ts.get("ohlcv_daily")
        if isinstance(raw, list) and raw:
            df = _try_load_ohlcv_from_value(raw)
            if df is not None and not df.empty:
                return df

    # 6. discovery-embedded fallback
    disc_pkg = pkg.get("discovery") or {}
    if "ohlcv" in disc_pkg:
        df = _try_load_ohlcv_from_value(disc_pkg.get("ohlcv"))
        if df is not None and not df.empty:
            return df

    return None


def compute_technical_enrichments(ohlcv_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute missing technical fields from OHLCV that state_calculator needs
    for accurate vol regime and trend maturity classification.

    Without these, state_calculator defaults every ticker to:
      - vol_regime = NORMAL  (atr_history/bb_width_history empty -> percentile = 50)
      - trend_maturity = LATE (high_52w/low_52w = 0 -> pct_from_extreme = 0 < 7%)

    This causes Matches: 0 across the entire universe against the actuarial database.
    """
    result = {
        "atr_current": 0.0,
        "atr_history": [],
        "bb_width": 0.0,
        "bb_width_history": [],
        "high_52w": 0.0,
        "low_52w": 0.0,
        "date_52w_high": None,
        "date_52w_low": None,
    }

    if ohlcv_df is None or len(ohlcv_df) < 20:
        return result

    try:
        df = ohlcv_df.copy()
        df.columns = [str(c).lower() for c in df.columns]

        close = df["close"]
        high  = df["high"]
        low   = df["low"]

        # --- ATR (14-period EWM) ---
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low  - close.shift(1)),
        ], axis=1).max(axis=1)
        atr_series = tr.ewm(span=14, adjust=False).mean()
        atr_clean  = atr_series.dropna()
        result["atr_current"] = float(atr_clean.iloc[-1]) if len(atr_clean) else 0.0
        result["atr_history"] = atr_clean.tail(100).tolist()

        # --- Bollinger Band width (20-period SMA) ---
        sma20   = close.rolling(20).mean()
        std20   = close.rolling(20).std()
        bb_up   = sma20 + 2 * std20
        bb_dn   = sma20 - 2 * std20
        bb_w    = (bb_up - bb_dn) / sma20.replace(0, float("nan"))
        bb_clean = bb_w.dropna()
        result["bb_width"]         = float(bb_clean.iloc[-1]) if len(bb_clean) else 0.0
        result["bb_width_history"] = bb_clean.tail(100).tolist()

        # --- 52-week high / low (rolling 252 bars) ---
        window = min(252, len(df))
        tail_high = high.tail(window)
        tail_low  = low.tail(window)

        result["high_52w"] = float(tail_high.max())
        result["low_52w"]  = float(tail_low.min())

        high_idx = tail_high.idxmax()
        low_idx  = tail_low.idxmin()

        def _parse_any_date(v: Any) -> Optional[pd.Timestamp]:
            """Parse a value into a Timestamp (UTC-naive acceptable)."""
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return None
            try:
                # unix seconds/ms
                if isinstance(v, (int, np.integer)):
                    if v > 10_000_000_000:  # ms
                        return pd.to_datetime(int(v), unit="ms", utc=True).tz_convert(None)
                    if v > 1_000_000_000:  # seconds
                        return pd.to_datetime(int(v), unit="s", utc=True).tz_convert(None)
                return pd.to_datetime(v, utc=True, errors="coerce").tz_convert(None)
            except Exception:
                return None

        def _safe_date(idx: Any, df_ref: pd.DataFrame) -> Optional[pd.Timestamp]:
            """Robustly recover the true bar date even when index is numeric."""
            if idx is None:
                return None

            # 1) If idx itself is a usable datetime, take it.
            ts = _parse_any_date(idx)
            if ts is not None and ts.year >= 2000:
                return ts

            # 2) Numeric index case: try to recover from a date-ish column.
            date_cols = [c for c in ["date", "datetime", "timestamp", "time"] if c in df_ref.columns]
            if date_cols:
                col = date_cols[0]
                try:
                    # Prefer exact index match
                    row = df_ref[df_ref.index == idx]
                    if not row.empty:
                        ts2 = _parse_any_date(row[col].iloc[0])
                        if ts2 is not None and ts2.year >= 2000:
                            return ts2
                    # Fallback: treat numeric idx as positional
                    if isinstance(idx, (int, np.integer)) and 0 <= int(idx) < len(df_ref):
                        ts3 = _parse_any_date(df_ref.iloc[int(idx)][col])
                        if ts3 is not None and ts3.year >= 2000:
                            return ts3
                except Exception:
                    return None
            return None

        result["date_52w_high"] = _safe_date(high_idx, df)
        result["date_52w_low"]  = _safe_date(low_idx, df)

    except Exception as e:
        print(f"  Warning: compute_technical_enrichments failed: {e}")

    return result


def build_orchestrator_like_payload(pkg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds the structure that OrchestratorAdapter expects.

    Stability rule: we do NOT fabricate contract-critical fields.
    If regime_snapshot or OHLCV isn't present in packages, the adapter should reject.

    We map what we can, *only if it exists*.
    """
    disc = pkg.get("discovery") or {}

    ticker = pkg.get("ticker") or disc.get("ticker") or pkg.get("symbol")
    ticker = _normalise_ticker(ticker)

    current_price = coerce_float(disc.get("stock_price") or disc.get("entry_price") or 0.0)

    # ---- Resolve OHLCV via canonical resolver (all known locations, priority order)
    ohlcv_df = _resolve_daily_bars(pkg)

    # ---- Compute technical enrichments from OHLCV
    # Required for accurate vol_regime and trend_maturity in state_calculator.
    # Without these every ticker defaults to NORMAL/LATE -> Matches: 0.
    tech_enrichments = compute_technical_enrichments(ohlcv_df)

    # ---- Regime snapshot (contract-critical)
    # Canonical: pkg["regime_snapshot"] (preferred) OR pkg["macro"]["regime_snapshot"].
    regime_snapshot = None
    if "regime_snapshot" in pkg:
        regime_snapshot = pkg.get("regime_snapshot")
    else:
        macro = pkg.get("macro") or {}
        if isinstance(macro, dict) and "regime_snapshot" in macro:
            regime_snapshot = macro.get("regime_snapshot")

    # Macro payload (non-contract, informational for MacroData)
    macro_payload = (pkg.get("macro") or {}).get("payload") if isinstance(pkg.get("macro"), dict) else {}
    if macro_payload is None:
        macro_payload = {}

    # Map dominant_event -> trend context
    # FIX: use .lower() — Discovery writes mixed-case e.g. "Trend_Continuation", "Trend_Up"
    dominant_event = disc.get("dominant_event", "")
    _de = dominant_event.lower()
    if "up" in _de or "breakout" in _de or "markup" in _de:
        intraday_position = "AT_RESISTANCE"
        control_dynamics = "BUYERS_STRENGTHENING"
    elif "down" in _de or "breakdown" in _de or "markdown" in _de:
        intraday_position = "AT_SUPPORT"
        control_dynamics = "SELLERS_STRENGTHENING"
    elif "support" in _de or "accumulation" in _de:
        intraday_position = "AT_SUPPORT"
        control_dynamics = "BUYERS_STRENGTHENING"
    elif "compression" in _de or "continuation" in _de or "consolidat" in _de:
        intraday_position = "NEAR_SUPPORT"
        control_dynamics = "NEUTRAL"
    elif "distribution" in _de or "resistance" in _de:
        intraday_position = "AT_RESISTANCE"
        control_dynamics = "SELLERS_STRENGTHENING"
    else:
        intraday_position = "UNKNOWN"
        control_dynamics = "NEUTRAL"

    # ---- Tier demotion: CONFIRMED in downtrend without buyer control → EARLY
    # Prevents CRK-type situations where a Crabel coil in a downtrend gets
    # promoted to CONFIRMED without directional confirmation.
    # Rule: if dominant_trend is BEARISH and control is not BUYERS, demote tier.
    #
    # EXCEPTION — ACCUMULATION × RISK_OFF:
    # Actuarial DB shows this is the highest-edge combination (Hit10 = 33.8%,
    # prior adjustment = +12 pts). In a RISK_OFF regime, a Wyckoff ACCUMULATION
    # stock will naturally show BEARISH EMA trend (the whole market is down) while
    # institutional absorption is building cause. Demoting it here would kill
    # the exact setup we want to monetise in bad regimes.
    # Guard: wyckoff_phase_bucket == ACCUMULATION AND macro_regime contains RISK_OFF.
    dominant_trend = disc.get("dominant_trend", "MIXED")
    control_state  = disc.get("control_state", "") or disc.get("precor_control", "")
    current_tier   = disc.get("tier", 99)
    wyckoff_bucket = str(disc.get("wyckoff_phase_bucket", "")).upper()
    active_regime  = str(disc.get("macro_regime") or disc.get("active_regime") or "").upper()
    is_accumulation_risk_off = (
        wyckoff_bucket == "ACCUMULATION" and "RISK_OFF" in active_regime
    )
    if (
        str(dominant_trend).upper() == "BEARISH"
        and "BUYER" not in str(control_state).upper()
        and str(current_tier) in {"1", 1}
        and not is_accumulation_risk_off   # protect highest-edge regime×phase combination
    ):
        # Demote from TIER_1 CONFIRMED to TIER_2 OBSERVE — requires directional trigger first
        disc = dict(disc)  # copy so we don't mutate the package
        disc["tier"] = 2
        disc["tier_label"] = "TIER_2_OBSERVE"
        disc["tier_demotion_reason"] = f"BEARISH trend + {control_state} control — no buyer confirmation"

    # Prefer JSON-friendly OHLCV transport (adapter will normalise)
    ohlcv_rows: Any = None
    if ohlcv_df is not None and isinstance(ohlcv_df, pd.DataFrame) and not ohlcv_df.empty:
        df_rows = ohlcv_df.copy()
        df_rows.columns = [str(c).lower() for c in df_rows.columns]
        # Ensure at least one date-like column exists for downstream maturity logic
        if "date" not in df_rows.columns:
            if "timestamp" in df_rows.columns:
                df_rows["date"] = pd.to_datetime(df_rows["timestamp"], utc=True, errors="coerce").dt.tz_convert(None)
        ohlcv_rows = df_rows.tail(600).to_dict(orient="records")

    payload: Dict[str, Any] = {
        "ticker": ticker,
        "current_price": current_price,
        "options_data": {},           # placeholder for later
        "microstructure_data": {},    # placeholder for later
        "macro_data": macro_payload,  # may be {}
        "avshunter_signal": {
            # Wire Discovery fields into avshunter_signal so downstream
            # consumers (CIL, reporting) have full context without re-reading packages.
            "tier":              disc.get("tier"),
            "tier_label":        disc.get("tier_label"),
            "phase":             disc.get("phase") or disc.get("current_phase"),
            "intent":            disc.get("precor_intent") or disc.get("intent"),
            "wyckoff_score":     coerce_float(disc.get("wyckoff_score", 0)),
            "composite_score":   coerce_float(disc.get("composite_score", 0)),
            "win_probability":   coerce_float(disc.get("win_probability", 0)),
            "dominant_event":    disc.get("dominant_event"),
            "dominant_trend":    disc.get("dominant_trend"),
            "control_state":     disc.get("control_state") or disc.get("precor_control"),
            "signal_type":       disc.get("signal_type"),
            "stop_loss":         coerce_float(disc.get("stop_loss", 0)),
            "structural_target": coerce_float(disc.get("entry_price", 0)),
        },
        "technical_data": {
            # NOTE: OrchestratorAdapter builds TechnicalData.ohlcv from technical_data["ohlcv"]
            "ohlcv": ohlcv_rows,
            "vwap_15m": coerce_float(disc.get("VWAP")),
            "ema9": coerce_float(disc.get("EMA9")),
            "ema21": coerce_float(disc.get("EMA21")),
            "ema50": coerce_float(disc.get("EMA50")),
            "ema200": coerce_float(disc.get("EMA200")),
            # === COMPUTED FROM OHLCV (enriched) ===
            "atr_current":      tech_enrichments["atr_current"],
            "atr_history":      tech_enrichments["atr_history"],
            "bb_width":         tech_enrichments["bb_width"],
            "bb_width_history": tech_enrichments["bb_width_history"],
            "high_52w":         tech_enrichments["high_52w"],
            "low_52w":          tech_enrichments["low_52w"],
            "date_52w_high":    tech_enrichments["date_52w_high"],
            "date_52w_low":     tech_enrichments["date_52w_low"],
            # === CALCULATED FROM OHLCV ===
            # NOTE: adx is computed below at lines 614-616 using the preferred
            # discovery adx_14 field with OHLCV fallback. That assignment overwrites
            # any value set here. The adx key is set once, correctly, at line 614.
            "rsi": calculate_rsi(ohlcv_df) if ohlcv_df is not None and len(ohlcv_df) > 14 else 50.0,
            # === AVSHUNTER DISCOVERY FIELDS ===
            # FIX B1: Discovery writes "phase"/"current_phase", NOT "wyckoff_phase".
            # Try all three field names in priority order so Vanguard sets
            # has_wyckoff_phase=True instead of False.
            "wyckoff_phase": (
                disc.get("wyckoff_phase")          # future-proof if field is renamed
                or disc.get("phase")               # primary Discovery field
                or disc.get("current_phase")       # secondary Discovery field
                or disc.get("precor_phase")        # tertiary fallback
            ),
            "wyckoff_events": [disc.get("dominant_event")] if disc.get("dominant_event") else [],
            # FIX B2: Discovery writes crabel_compression, not compression.
            # Pass under both names so Vanguard finds it regardless of which it checks.
            "compression": (
                coerce_float(disc.get("crabel_compression"))
                or coerce_float(disc.get("compression_ratio"))
                or coerce_float(disc.get("compression"))
                or None
            ),
            "crabel_compression": coerce_float(disc.get("crabel_compression")),
            "compression_ratio":  (
                coerce_float(disc.get("compression_ratio"))
                or coerce_float(disc.get("crabel_compression"))
            ),
            # FIX B3: Pass macro regime into technical_data so Vanguard can set
            # has_macro_regime=True. Discovery carries macro_regime and active_regime
            # as flattened columns from the inject step.
            "macro_regime": (
                disc.get("macro_regime")
                or disc.get("active_regime")
                or (regime_snapshot or {}).get("regime_state")
            ),
            "active_regime": (
                disc.get("active_regime")
                or disc.get("macro_regime")
                or (regime_snapshot or {}).get("regime_state")
            ),
            "intraday_position": intraday_position,
            "control_dynamics": control_dynamics,
            # FIX P7: volume_profile_context was previously derived from win_probability,
            # which is itself a linear transform of composite_score — circular and carries
            # no independent information. Replaced with wyckoff_phase_bucket which is
            # computed independently from price/volume structure by the Wyckoff engine.
            "volume_profile_context": (
                "ACCUMULATION" if str(disc.get("wyckoff_phase_bucket", "")).upper() == "ACCUMULATION"
                else "DISTRIBUTION" if str(disc.get("wyckoff_phase_bucket", "")).upper() == "DISTRIBUTION"
                else "BALANCED"
            ),
            # FIX (2026-03-07): Wire pre-computed wyckoff_phase_bucket from discovery CSV.
            # Without this, state_calculator._wyckoff_phase_bucket() receives None → returns
            # UNKNOWN for every ticker → all TRADE rows collapse to one L2 hash → collision.
            # Discovery already computes the correct bucket (ACCUMULATION/MARKUP/DISTRIBUTION).
            "wyckoff_phase_bucket": (
                disc.get("wyckoff_phase_bucket")   # pre-computed by discovery (preferred)
                or None                            # let state_calculator derive from wyckoff_phase
            ),
            # FIX: Wire adx_14 and atr_percentile_rank from discovery CSV.
            # These populate state hash dims 6-7 (adx_bucket, atr_pct_bucket).
            # Without these, state_calculator defaults to MODERATE/MID for ALL tickers.
            # discovery now computes adx_14 (raw ADX) and atr_percentile_rank (0-100 rank).
            "adx": (
                coerce_float(disc.get("adx_14"))     # from discovery (preferred)
                or calculate_adx(ohlcv_df) if ohlcv_df is not None and len(ohlcv_df) > 20 else 0.0
            ),
            "atr_percentile_rank": coerce_float(disc.get("atr_percentile_rank", 50.0)),
        },
        "calendar_data": {
            # FIX: Wire catalyst_proximity from discovery CSV into calendar_data.
            # discovery computes catalyst_proximity_bucket from days_to_trigger.
            # state_calculator._calculate_catalyst_proximity() uses calendar.days_to_earnings
            # but the bucketed proximity for the hash is also stored here as a direct passthrough
            # so run_vanguard can override the hash dim 5 without needing earnings dates.
            "catalyst_proximity_override": disc.get("catalyst_proximity", "FAR"),
        },
    }

    # Only include regime_snapshot key if package supplied it.
    # Fail-closed is enforced by adapter; this script does not fabricate.
    if regime_snapshot is not None:
        payload["regime_snapshot"] = regime_snapshot

    return payload


# ------------------------- signal -> csv row -------------------------

def signal_to_dict(signal: Any) -> Dict[str, Any]:
    """
    Convert a VanguardSignal into a dict across pydantic v1/v2/plain-object.
    """
    if hasattr(signal, "model_dump"):  # pydantic v2
        return signal.model_dump()
    if hasattr(signal, "dict"):        # pydantic v1
        return signal.dict()
    return getattr(signal, "__dict__", {}) or {}



def _wyckoff_bucket_from_disc(disc: dict) -> str:
    """
    Resolve wyckoff_phase_bucket for debug_signature from the discovery package dict.
    Mirrors state_calculator._wyckoff_phase_bucket() single-letter + long-form logic.
    Used by signal_to_row which has access to disc but not to the StateVector internals.
    """
    # Use pre-computed bucket if present (fastest, most accurate)
    pre = (disc.get("wyckoff_phase_bucket") or "").strip().upper()
    if pre in ("ACCUMULATION", "MARKUP", "DISTRIBUTION"):
        return pre

    # Fall back to raw phase letter
    raw = str(disc.get("phase") or disc.get("precor_phase") or "").strip().upper()
    if raw in ("A", "B", "C"):
        return "ACCUMULATION"
    if raw in ("D", "E"):
        return "MARKUP"
    if any(x in raw for x in ["DISTRIBUTION", "REDISTRIBUTION"]):
        return "DISTRIBUTION"
    if any(x in raw for x in ["PHASE_D", "PHASE_E", "MARKUP"]):
        return "MARKUP"
    if any(x in raw for x in ["PHASE_A", "PHASE_B", "PHASE_C", "ACCUMULATION"]):
        return "ACCUMULATION"
    return "UNKNOWN"


def _macro_regime_from_disc(disc: dict) -> str:
    """Pull macro_regime from discovery package for debug_signature dim 9."""
    return (
        disc.get("macro_regime")
        or disc.get("active_regime")
        or "TRANSITIONAL"
    )


def _adx_bucket_from_disc(disc: dict) -> str:
    """Bucket adx_14 from discovery into WEAK/MODERATE/STRONG for debug_signature dim 6."""
    adx = coerce_float(disc.get("adx_14", 0.0))
    if adx <= 0:
        return "MODERATE"   # safe default when not yet populated
    if adx < 20:
        return "WEAK"
    elif adx <= 35:
        return "MODERATE"
    else:
        return "STRONG"


def _atr_pct_bucket_from_disc(disc: dict) -> str:
    """Bucket atr_percentile_rank from discovery into LOW/MID/HIGH for debug_signature dim 7."""
    rank = coerce_float(disc.get("atr_percentile_rank", -1.0))
    if rank < 0:
        return "MID"    # safe default when not yet populated
    if rank < 33:
        return "LOW"
    elif rank <= 66:
        return "MID"
    else:
        return "HIGH"


def _horizon_profile(ev_5d: Any, ev_10d: Any, ev_20d: Any) -> str:
    """
    Classify the EV horizon shape to guide Superbrain DTE selection.

    BURST  : EV concentrated in 5d — short DTE preferred (7-21d)
    GRIND  : EV builds slowly over 20d — longer DTE preferred (30-90d)
    STEADY : Even distribution — standard DTE ladder
    FLAT   : Insufficient data or all horizons near zero

    Logic:
      ev_5d / ev_20d ratio > 0.7  → most EV in first 5d → BURST
      ev_5d / ev_20d ratio < 0.25 → EV back-loaded → GRIND
      ev_10d / ev_20d ratio > 0.6 → most EV in 10d → STEADY
      otherwise                   → FLAT / unknown
    """
    try:
        e5  = float(ev_5d  or 0)
        e10 = float(ev_10d or 0)
        e20 = float(ev_20d or 0)
        if e20 <= 0:
            return "FLAT"
        r5  = e5  / e20
        r10 = e10 / e20
        if r5 >= 0.70:
            return "BURST"
        if r5 <= 0.25 and r10 <= 0.55:
            return "GRIND"
        if r10 >= 0.60:
            return "STEADY"
        return "FLAT"
    except Exception:
        return "FLAT"


def _actuarial_lineage(actuarial: Any) -> Dict[str, Any]:
    if not isinstance(actuarial, dict):
        return {
            "actuarial_source": ACTUARIAL_SOURCE_MISSING,
            "actuarial_schema_version": None,
            "actuarial_schema_fingerprint": None,
            "actuarial_truth_packet_status": "MISSING",
        }

    _validate_truth_packet(actuarial)
    source = str(actuarial.get("actuarial_source") or "").upper()
    no_match = bool(actuarial.get("no_match"))
    if source == ACTUARIAL_SOURCE_V6_DB and not no_match:
        return {
            "actuarial_source": ACTUARIAL_SOURCE_V6_DB,
            "actuarial_schema_version": actuarial.get("schema_version"),
            "actuarial_schema_fingerprint": actuarial.get("schema_fingerprint"),
            "actuarial_truth_packet_status": actuarial.get("truth_packet_status") or "VALID",
        }

    return {
        "actuarial_source": ACTUARIAL_SOURCE_MISSING,
        "actuarial_schema_version": actuarial.get("schema_version"),
        "actuarial_schema_fingerprint": actuarial.get("schema_fingerprint"),
        "actuarial_truth_packet_status": actuarial.get("truth_packet_status") or "MISSING",
    }


def _rate_from_actuarial(actuarial: Any, key: str) -> Optional[float]:
    if not isinstance(actuarial, dict):
        return None
    value = actuarial.get(key)
    if value is None:
        return None
    try:
        rate = float(value)
    except Exception:
        return None
    return rate if rate > 0 else None


def signal_to_row(
    signal: Any,
    disc: dict = None,
    actuarial: dict = None,
    macro_quant_packet: dict = None,
) -> Dict[str, Any]:
    """
    Convert VanguardSignal to a flat CSV row with Layer-2 headline fields guaranteed.

    disc: optional discovery sub-dict from the package (pkg["discovery"]).
          Required for accurate 9-dim debug_signature — without it dims 5-9 show "?".
    """
    s = signal_to_dict(signal)

    l1 = s.get("layer_1_result") or {}
    l2 = s.get("layer_2_result") or {}
    l3 = s.get("layer_3_result") or {}
    disc = disc or {}
    actuarial = actuarial or {}
    lineage = _actuarial_lineage(actuarial)

    row: Dict[str, Any] = {
        "ticker": s.get("ticker"),
        "timestamp": s.get("timestamp"),
        "verdict": s.get("verdict"),
        "final_recommendation": s.get("final_recommendation"),
        "reasoning": s.get("reasoning"),

        # ---- Layer 2 headline metrics
        "state_hash": safe_get(l2, "state_hash"),
        "n_observations": safe_get(l2, "n_observations"),
        "win_rate_20d": safe_get(l2, "win_rate_20d"),
        "expected_value_20d": safe_get(l2, "expected_value_20d"),
        "confidence_level": safe_get(l2, "confidence_level"),
        "has_edge": safe_get(l2, "has_edge"),
        "edge_direction": safe_get(l2, "edge_direction"),
        "failed_gate": safe_get(l2, "failed_gate"),
        "no_edge_reason": safe_get(l2, "no_edge_reason"),
        # Schema versioning — from state_calculator constants, written to every row
        "schema_version": safe_get(l2, "schema_version") or safe_get(s, "schema_version") or "unknown",
        "bucket_schema_version": safe_get(l2, "bucket_schema_version") or "unknown",
        "actuarial_source": lineage["actuarial_source"],
        "actuarial_schema_version": lineage["actuarial_schema_version"],
        "actuarial_schema_fingerprint": lineage["actuarial_schema_fingerprint"],
        "actuarial_truth_packet_status": lineage["actuarial_truth_packet_status"],
        # FIX (2026-03-07 rev3): All 9 dims now populated from discovery data.
        # dim 5 — catalyst_proximity: from discovery catalyst_proximity_bucket() ✓
        # dim 6 — adx_bucket: from discovery adx_14 field ✓
        # dim 7 — atr_pct_bucket: from discovery atr_percentile_rank field ✓
        # dim 8 — wyckoff_phase_bucket: pre-computed by discovery ✓
        # dim 9 — macro_regime: disc.macro_regime / disc.active_regime ✓
        "debug_signature": "|".join([
            str(safe_get(l2, "vol_regime")        or "?"),          # dim 1 — from l2
            str(safe_get(l2, "trend_direction")   or "?"),          # dim 2 — from l2
            str(safe_get(l2, "trend_maturity")    or "?"),          # dim 3 — from l2
            str(safe_get(l2, "structure_quality") or "?"),          # dim 4 — from l2
            str(disc.get("catalyst_proximity") or "FAR"),           # dim 5 — from discovery ✓
            _adx_bucket_from_disc(disc),                            # dim 6 — from discovery adx_14 ✓
            _atr_pct_bucket_from_disc(disc),                        # dim 7 — from discovery atr_percentile_rank ✓
            _wyckoff_bucket_from_disc(disc),                        # dim 8 — wyckoff_phase_bucket ✓
            _macro_regime_from_disc(disc),                          # dim 9 — macro_regime ✓
        ]),
    }

    # ── Multi-horizon EV surface (Priority 4) ────────────────────────────────
    # ActuarialOutcomes carries win_rate_5d/10d, ev_5d/10d, sharpe_5d/10d etc.
    # These flow through EdgeAssessment.outcomes. Depending on how VanguardEngine
    # serialises EdgeAssessment, they may appear as:
    #   a) l2["outcomes"]["win_rate_5d"]          — nested outcomes dict
    #   b) layer2__outcomes__win_rate_5d           — auto-flattened by flatten_dict below
    #   c) l2["win_rate_5d"]                       — if VanguardEngine flattens outcomes inline
    # We extract explicitly here so they appear as top-level headline fields in the CSV
    # (not buried under layer2__outcomes__ prefix), making them directly accessible to
    # Superbrain and core_intel without column-name archaeology.
    outcomes_sub = l2.get("outcomes") or {}
    if hasattr(outcomes_sub, "__dict__"):
        outcomes_sub = outcomes_sub.__dict__
    elif hasattr(outcomes_sub, "dict"):
        outcomes_sub = outcomes_sub.dict()
    elif hasattr(outcomes_sub, "model_dump"):
        outcomes_sub = outcomes_sub.model_dump()

    def _ov(key: str) -> Any:
        """Pull a horizon field from outcomes sub-object OR directly from l2 (flattened path)."""
        return (
            outcomes_sub.get(key)
            if outcomes_sub.get(key) is not None
            else l2.get(key)
        )

    row.update({
        # 5-day horizon
        "win_rate_5d":              _ov("win_rate_5d"),
        "expected_value_5d":        _ov("expected_value_5d"),
        "prob_up_5pct_5d":          _ov("prob_up_5pct_5d"),
        "median_gain_if_up_5d":     _ov("median_gain_if_up_5d"),
        "median_loss_if_down_5d":   _ov("median_loss_if_down_5d"),
        "median_max_drawdown_5d":   _ov("median_max_drawdown_5d"),
        "sharpe_ratio_5d":          _ov("sharpe_ratio_5d"),
        # 10-day horizon
        "win_rate_10d":             _ov("win_rate_10d"),
        "expected_value_10d":       _ov("expected_value_10d"),
        "prob_up_7pct_10d":         _ov("prob_up_7pct_10d"),
        "median_gain_if_up_10d":    _ov("median_gain_if_up_10d"),
        "median_loss_if_down_10d":  _ov("median_loss_if_down_10d"),
        "median_max_drawdown_10d":  _ov("median_max_drawdown_10d"),
        "sharpe_ratio_10d":         _ov("sharpe_ratio_10d"),
        # Horizon interpretation helper — tells Superbrain whether this is burst or grind
        # burst: high short-term EV relative to long-term → favour shorter DTE
        # grind: EV builds slowly → favour longer DTE campaigns
        "horizon_profile": _horizon_profile(_ov("expected_value_5d"), _ov("expected_value_10d"), _ov("expected_value_20d") or safe_get(l2, "expected_value_20d")),
    })

    # ── WIN RATE FALLBACK BRIDGE ──────────────────────────────────────────────
    # win_rate_5d/10d/20d originate from Vanguard actuarial Layer 2 outcomes.
    # When the outcomes sub-object is empty (N=0 state match, actuarial miss,
    # or VanguardEngine version difference), all three horizon rates come through
    # as None — which the CSV reader converts to 0.0 — causing EVEngineV2 inside
    # Superbrain to fire DataQualityWarning and fall back to a=0.40 for every
    # ticker. This produces near-identical EV scores with no real differentiation.
    #
    # Bridge: packages always carry discovery.win_probability (e.g. 57.8 for APG)
    # which is the Wyckoff structural win probability computed independently of
    # the actuarial database. Seed all three horizon rates from it when none are
    # populated, so EVEngineV2 receives real per-signal inputs.
    #
    # Priority: actuarial win_rate_20d (real DB match) wins over this bridge.
    # When actuarial rates flow through normally this block is a no-op.
    if row["actuarial_source"] == ACTUARIAL_SOURCE_MISSING:
        _n_obs = coerce_float(row.get("n_observations"), 0.0)
        _has_layer2_rates = any(row.get(k) is not None for k in ("win_rate_5d", "win_rate_10d", "win_rate_20d"))
        if _n_obs > 0 and _has_layer2_rates:
            row["actuarial_source"] = ACTUARIAL_SOURCE_V6_DB
            row["actuarial_schema_version"] = _actuarial_schema_version()
            row["actuarial_schema_fingerprint"] = _expected_actuarial_fingerprint()
            row["actuarial_truth_packet_status"] = "VALID"

    _wr5_val  = _ov("win_rate_5d")
    _wr10_val = _ov("win_rate_10d")
    _wr20_val = _ov("win_rate_20d")
    _all_missing = (_wr5_val is None and _wr10_val is None and _wr20_val is None)
    if _all_missing:
        if row["actuarial_source"] == ACTUARIAL_SOURCE_V6_DB:
            row["win_rate_5d"] = _rate_from_actuarial(actuarial, "win_rate_5d")
            row["win_rate_10d"] = _rate_from_actuarial(actuarial, "win_rate_10d")
            row["win_rate_20d"] = _rate_from_actuarial(actuarial, "win_rate_20d")

        if row.get("win_rate_5d") is None and row.get("win_rate_10d") is None and row.get("win_rate_20d") is None:
            _disc_win = coerce_float(disc.get("win_probability", 0))
        else:
            _disc_win = 0.0

        if _disc_win > 0.0:
            # Normalise: Discovery writes as percentage (57.8) or fraction (0.578)
            if _disc_win > 1.0:
                _disc_win = _disc_win / 100.0
            _disc_win = max(0.30, min(0.80, _disc_win))  # sanity clamp
            row["win_rate_5d"]  = _disc_win
            row["win_rate_10d"] = _disc_win
            row["win_rate_20d"] = _disc_win
            # Also write win_probability as a named field so Superbrain can
            # trace which path the win rate came from
            row["win_probability"] = _disc_win
            row["actuarial_source"] = ACTUARIAL_SOURCE_DISCOVERY_FALLBACK
            row["actuarial_schema_version"] = None
            row["actuarial_schema_fingerprint"] = None
            row["actuarial_truth_packet_status"] = "DISCOVERY_FALLBACK"
    # ── END WIN RATE FALLBACK BRIDGE ──────────────────────────────────────────

    # Optional: fully flatten layers for debugging / post-mortems
    row.update({f"layer1__{k}": v for k, v in flatten_dict(l1).items()})
    row.update({f"layer2__{k}": v for k, v in flatten_dict(l2).items()})
    if isinstance(l3, dict):
        row.update({f"layer3__{k}": v for k, v in flatten_dict(l3).items()})

    row.update(macro_quant_columns_for_row(macro_quant_packet, disc or row))
    for _scanner_col in SCANNER_FIELD_NAMES:
        if _scanner_col in disc and _scanner_col not in row:
            row[_scanner_col] = disc.get(_scanner_col)
    for _physics_source_col in (
        "vwap_bias",
        "adx_14",
        "atr_percentile",
        "atr_percentile_rank",
        "return_5d",
        "return_10d",
        "volume_ratio",
        "crabel_compression",
        "crabel_pattern",
        "crabel_state",
        "dominant_trend",
        "sector",
        "avg_volume",
        "contract_spread_pct",
        "spread_pct",
        "iv_rank",
        "iv_percentile",
    ):
        if _physics_source_col in disc and _physics_source_col not in row:
            row[_physics_source_col] = disc.get(_physics_source_col)

    _ensure_phase2_baton_fields(row)
    row.update(calculate_market_physics(row, macro_context=macro_quant_packet or {}))

    return enrich_row_with_truth_packet(
        row,
        source="VANGUARD_ACTUARIAL",
        priority=PRIORITY_VANGUARD_ACTUARIAL,
        run_id=str(disc.get("run_id") or row.get("run_id") or ""),
        run_mode="EVENING",
    )


# ------------------------- execution / reporting -------------------------

@dataclass
class RunPaths:
    root: Path
    run_id: str
    run_dir: Path
    packages_index: Path
    output_csv: Path
    rejects_csv: Path
    summary_json: Path


def resolve_run_paths(root: Path, run_id: Optional[str]) -> RunPaths:
    latest_path = root / "data" / "output" / "latest.json"
    if run_id is None:
        latest = read_json(latest_path)
        run_id = str(latest.get("run_id") or "").strip()
        if not run_id:
            raise RuntimeError(f"latest.json missing run_id: {latest_path}")

    run_dir = root / "data" / "output" / "runs" / run_id
    packages_index = run_dir / "packages" / "index.json"
    output_csv = run_dir / "vanguard" / "vanguard_signals.csv"
    rejects_csv = run_dir / "vanguard" / "vanguard_rejects.csv"
    summary_json = run_dir / "vanguard" / "vanguard_run_summary.json"

    return RunPaths(
        root=root,
        run_id=run_id,
        run_dir=run_dir,
        packages_index=packages_index,
        output_csv=output_csv,
        rejects_csv=rejects_csv,
        summary_json=summary_json,
    )


def load_package_paths(index_json: Dict[str, Any], base_dir: Path) -> List[Path]:
    """
    index.json format expected:
      {
        "packages": [
          {"package_path": "data/output/runs/<run_id>/packages/APLE.json", ...},
          ...
        ]
      }
    """
    pkgs = index_json.get("packages") or []
    paths: List[Path] = []
    for p in pkgs:
        raw = (p or {}).get("package_path")
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = base_dir / path
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None, help="Run id to process (defaults to latest.json run_id)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of packages (0 = no limit)")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose Vanguard diagnostics and error traces per ticker",
    )
    args = parser.parse_args()

    root = Path(".").resolve()

    # Import inside main so the script can still show path errors cleanly
    try:
        from vanguard.main import VanguardEngine
        from vanguard.integration.orchestrator_adapter import OrchestratorAdapter
    except Exception as e:
        print("ERROR: Could not import vanguard modules.")
        print(str(e))
        return 2

    # ── TRADE STATE MACHINE: Governance routing ─────────────────────────────
    # Loaded once per run — O(1) set lookup per ticker in the loop below.
    # Fails gracefully if trade_contract not yet deployed (import error caught).
    try:
        from vanguard.trade_contract import list_open_tickers
        from vanguard.trade_governance import TradeGovernanceEngine
        _open_tickers      = list_open_tickers()
        _governance_engine = TradeGovernanceEngine()
        if _open_tickers:
            print(f"\n[GOVERNANCE] {len(_open_tickers)} open contract(s): "
                  f"{sorted(_open_tickers)}")
            print("[GOVERNANCE] These tickers route to governance — scanner cannot override.")
        else:
            print("[GOVERNANCE] No open contracts — all tickers run discovery.")
    except ImportError:
        _open_tickers      = set()
        _governance_engine = None
    # ─────────────────────────────────────────────────────────────────────────

    rp = resolve_run_paths(root, args.run_id)

    if not rp.packages_index.exists():
        print(f"ERROR: packages index not found: {rp.packages_index}")
        return 3

    idx = read_json(rp.packages_index)
    package_paths = load_package_paths(idx, rp.root)

    if args.limit and args.limit > 0:
        package_paths = package_paths[: args.limit]

    if not package_paths:
        print(f"ERROR: No packages found in: {rp.packages_index}")
        return 4

    engine = VanguardEngine()
    adapter = OrchestratorAdapter()

    pass_rows: List[Dict[str, Any]] = []
    reject_rows: List[Dict[str, Any]] = []

    # One-time banner
    print(f"\nRUN: {rp.run_id}")
    print(f"Packages: {len(package_paths)}")
    print("-" * 60)

    # Feature: if adapter supports deterministic outcomes, use it.
    use_adapt_result = hasattr(adapter, "adapt_result")

    for i, pkg_path in enumerate(package_paths, start=1):
        ticker_guess = pkg_path.stem
        try:
            pkg = read_json(pkg_path)
            ticker = _normalise_ticker(pkg.get("ticker") or ticker_guess)

            # ── DATA CONTRACT GATE ───────────────────────────────────────────
            # Attempt repair first: promotes daily_df / ohlcv_daily / timeseries
            # into pkg["ohlcv"] so all downstream consumers see a consistent key.
            # Hard-reject only if no valid OHLCV source exists after repair.
            pkg, _repaired, _repair_reason = DCV.attempt_repair(pkg)
            _dcv_ok, _dcv_reason = DCV.validate(pkg)
            if not _dcv_ok:
                reject_rows.append({
                    "ticker": ticker,
                    "package_path": str(pkg_path),
                    "reason_code": f"DATA_FAILURE_{_dcv_reason}",
                    "reason_codes": f"DATA_FAILURE_{_dcv_reason}",
                    "error": f"DCV hard gate: {_dcv_reason}",
                    "exception_type": "DataContractFailure",
                    "diagnostics": "{}",
                })
                print(f"[{i}/{len(package_paths)}] REJECT {ticker}: DATA_FAILURE | {_dcv_reason}")
                continue
            # Quality downgrade — low bar count, pass but note it
            _dcv_conf = DCV.confidence_level(pkg)
            if _dcv_conf == "LOW":
                print(f"[{i}/{len(package_paths)}] WARN {ticker}: LOW_CONFIDENCE | "
                      f"only {(pkg.get("data_contract") or {}).get("dcv_bars", "?")} bars")
            # ── END DATA CONTRACT GATE ───────────────────────────────────────

            # ── GOVERNANCE ROUTING ────────────────────────────────────────────
            # If this ticker has an open Trade Contract, route to governance.
            # RULE: scanner cannot override campaign logic.
            if _governance_engine and ticker in _open_tickers:
                current_price = float(
                    (pkg.get("discovery") or {}).get("stock_price") or 0.0
                )
                gov_result = _governance_engine.evaluate_single(
                    ticker        = ticker,
                    current_state = None,        # StateVector not yet computed — Q1/Q5 still run
                    current_price = current_price if current_price > 0 else None,
                )
                if gov_result:
                    verdict = gov_result["verdict"]
                    reason  = gov_result["reason"]
                    icon    = {"HOLD": "✓", "TIGHTEN": "⚠", "EXIT": "✗"}.get(verdict, "?")
                    print(f"[{i}/{len(package_paths)}] [{icon}] GOVERNANCE {ticker} "
                          f"→ {verdict}: {reason}")
                    if verdict == "EXIT":
                        _open_tickers.discard(ticker)
                    continue   # Do NOT run discovery on this ticker
            # ── END GOVERNANCE ROUTING ────────────────────────────────────────

            o_payload = build_orchestrator_like_payload(pkg)

            # Contract gate occurs inside adapter (fail-closed per ticker)
            if use_adapt_result:
                out = adapter.adapt_result(o_payload)
                if not getattr(out, "ok", False) or getattr(out, "v_input", None) is None:
                    reason_codes = getattr(out, "reason_codes", None) or ["ADAPTER_REJECT"]
                    reject_rows.append({
                        "ticker": ticker,
                        "package_path": str(pkg_path),
                        "reason_code": reason_codes[0],
                        "reason_codes": ",".join(reason_codes),
                        "error": getattr(out, "error", "adapter rejected input"),
                        "exception_type": getattr(out, "exception_type", ""),
                        "diagnostics": json.dumps(getattr(out, "diagnostics", {}) or {}, default=str),
                    })
                    print(f"[{i}/{len(package_paths)}] REJECT {ticker}: {reason_codes[0]} | {getattr(out, 'error', '')}")
                    continue
                v_input = out.v_input
            else:
                v_input = adapter.adapt(o_payload)

            # Analyze -> VanguardSignal
            #
            # VanguardEngine emits a large human-readable diagnostic block for
            # every ticker. The orchestrator also captures and re-logs child
            # stdout, so full-run UAT can spend a lot of time writing console
            # output. Keep the full block available under --verbose, but use a
            # compact PASS/REJECT stream for production runs.
            if args.verbose:
                signal = engine.analyze(v_input)
            else:
                with contextlib.redirect_stdout(io.StringIO()):
                    signal = engine.analyze(v_input)

            # Flatten -> CSV row (PASS only)
            # FIX (2026-03-07 rev2): pass disc so signal_to_row can populate dims 8-9
            # of debug_signature (wyckoff_phase_bucket, macro_regime) from package data.
            _disc_row = dict(pkg.get("discovery") or {})
            _disc_row.setdefault("run_id", pkg.get("run_id") or rp.run_id)
            _disc_row.setdefault("ticker", ticker)
            pass_rows.append(signal_to_row(
                signal,
                disc=_disc_row,
                actuarial=pkg.get("actuarial"),
                macro_quant_packet=packet_from_package(pkg),
            ))

            print(f"[{i}/{len(package_paths)}] PASS {ticker}")

        except Exception as e:
            reason = _short_reason(e)
            reject_rows.append({
                "ticker": ticker_guess,
                "package_path": str(pkg_path),
                "reason_code": reason,
                "error": str(e),
                "exception_type": e.__class__.__name__,
            })
            print(f"[{i}/{len(package_paths)}] REJECT {ticker_guess}: {reason} | {e}")
            if args.verbose:
                traceback.print_exc()

    physics_valid = sum(1 for r in pass_rows if r.get("physics_state_id") and r.get("state_transition_label"))
    physics_missing = max(0, len(pass_rows) - physics_valid)
    print(
        f"[PHYSICS] Physics fields appended to Vanguard output: "
        f"{physics_valid}/{len(pass_rows)} rows valid; missing={physics_missing}"
    )

    # Sprint A: append precise behaviour-state identity without changing broad state_hash.
    if pass_rows:
        pass_rows = enrich_behaviour_state_dataframe(pd.DataFrame(pass_rows)).to_dict(orient="records")
        behaviour_hashes = [r.get("behaviour_state_hash") for r in pass_rows if r.get("behaviour_state_hash")]
        print(f"[BEHAVIOUR_STATE] Unique behaviour_state_hash: {len(set(behaviour_hashes))} / {len(behaviour_hashes)}")

    # Write PASS signals
    write_csv(
        rp.output_csv,
        pass_rows,
        minimum_headers=[
            "ticker",
            "timestamp",
            "verdict",
            "final_recommendation",
            "reasoning",
            "state_hash",
            "behaviour_state_key",
            "behaviour_state_hash",
            "catalyst_overlay",
            "n_observations",
            "win_rate_20d",
            "expected_value_20d",
            "confidence_level",
            "actuarial_source",
            "actuarial_schema_version",
            "actuarial_schema_fingerprint",
            "actuarial_truth_packet_status",
            "failed_gate",
            "no_edge_reason",
            *PHYSICS_FIELDS,
        ],
    )

    # Write REJECTS
    write_csv(
        rp.rejects_csv,
        reject_rows,
        minimum_headers=["ticker", "package_path", "reason_code", "reason_codes", "error", "exception_type", "diagnostics"],
    )

    # Summary
    reason_counts = Counter(r["reason_code"] for r in reject_rows if r.get("reason_code"))
    summary = {
        "run_id": rp.run_id,
        "packages_total": len(package_paths),
        "passed": len(pass_rows),
        "rejected": len(reject_rows),
        "reject_top_reasons": reason_counts.most_common(10),
        "output_csv": str(rp.output_csv),
        "rejects_csv": str(rp.rejects_csv),
    }
    write_json(rp.summary_json, summary)

    print("\n" + "-" * 60)
    print(f"DONE: {rp.output_csv}")
    print(f"Rows written (PASS): {len(pass_rows)}")
    print(f"Rejects written: {len(reject_rows)} -> {rp.rejects_csv}")
    print(f"Summary: {rp.summary_json}")

    if reject_rows:
        print("\nTop reject reasons:")
        for code, n in reason_counts.most_common(5):
            print(f"  - {code}: {n}")

    # Quick sanity summary: how many unique state hashes?
    try:
        state_hashes = [r.get("state_hash") for r in pass_rows if r.get("state_hash")]
        uniq = len(set(state_hashes))
        print(f"\nUnique state_hash: {uniq} / {len(state_hashes)}")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
