"""
AVSHUNTER - Data Contract Validator
====================================
Single source of truth for package data integrity.
Called by: backfill, build_packages, run_vanguard_from_packages, superbrain.

Design principles
-----------------
- Fail-closed: missing or insufficient data returns (False, reason) never raises
- Consistent thresholds in one place: change MIN_BARS here, all callers benefit
- Repair path: attempt_repair() promotes timeseries -> ohlcv without fabricating
- Transparent: every result carries a human-readable reason code

Usage
-----
    from data_contract_validator import DataContractValidator as DCV

    ok, reason = DCV.validate(package)
    if not ok:
        log.warning(f"{ticker} -> {reason}")
        continue

    # Optional: attempt repair before rejecting
    package, repaired, reason = DCV.attempt_repair(package)
    ok2, reason2 = DCV.validate(package)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("DCV")

# Single source of truth for thresholds used everywhere in the pipeline
MIN_BARS_HARD      = 50    # absolute floor: below this = DATA_FAILURE (reject)
MIN_BARS_PREFERRED = 200   # preferred: below this = LOW_CONFIDENCE (downgrade, not reject)
MAX_STALENESS_DAYS = 5     # last bar may not be older than this (weekends + US holidays)


class DataContractValidator:
    """
    Static validator for AVSHUNTER package dicts.
    All methods are class-methods -- no instantiation needed.
    """

    MIN_BARS           = MIN_BARS_HARD
    MIN_BARS_PREFERRED = MIN_BARS_PREFERRED
    MAX_STALENESS_DAYS = MAX_STALENESS_DAYS

    @classmethod
    def validate(cls, package: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Hard validation gate.
        Returns (True, "VALID") or (False, reason_code).

        Reason codes:
          NO_OHLCV                  no resolvable OHLCV data in any location
          INSUFFICIENT_HISTORY      fewer than MIN_BARS rows
          NULLS_IN_CRITICAL_COLS    NaN/None in open/high/low/close in last 10 bars
          STALE_DATA                last bar older than MAX_STALENESS_DAYS
          MISSING_REGIME            regime_snapshot absent or empty
        """
        ohlcv = cls._resolve_ohlcv(package)

        if not ohlcv:
            return False, "NO_OHLCV"

        if len(ohlcv) < cls.MIN_BARS:
            return False, f"INSUFFICIENT_HISTORY ({len(ohlcv)}<{cls.MIN_BARS})"

        null_col = cls._check_nulls(ohlcv)
        if null_col:
            return False, f"NULLS_IN_CRITICAL_COLS ({null_col})"

        stale, stale_reason = cls._check_staleness(ohlcv)
        if stale:
            return False, stale_reason

        if not cls._has_regime(package):
            return False, "MISSING_REGIME"

        return True, "VALID"

    @classmethod
    def confidence_level(cls, package: Dict[str, Any]) -> str:
        """
        Soft quality signal. Does not reject but lets engines apply a lower prior.
        Returns: HIGH / MEDIUM / LOW / NONE
        """
        ohlcv = cls._resolve_ohlcv(package)
        if not ohlcv:
            return "NONE"
        if len(ohlcv) >= cls.MIN_BARS_PREFERRED:
            return "HIGH"
        if len(ohlcv) >= cls.MIN_BARS:
            return "LOW"
        return "NONE"

    @classmethod
    def attempt_repair(cls, package: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, str]:
        """
        Promote data from fallback locations to ohlcv if present and sufficient.
        NEVER fabricates data. Returns (package, repaired, reason).
        """
        existing = package.get("ohlcv")
        if cls._is_usable(existing) and len(existing) >= cls.MIN_BARS:
            return package, False, "ALREADY_PRESENT"

        # Priority 1: daily_df (canonical alias, written by backfill)
        src = package.get("daily_df")
        if cls._is_usable(src) and len(src) >= cls.MIN_BARS:
            package["ohlcv"] = src
            package["data_repaired"] = True
            package.setdefault("data_contract", {})["ohlcv_repair_source"] = "daily_df"
            return package, True, "REPAIRED_FROM_DAILY_DF"

        # Priority 2: top-level ohlcv_daily
        src = package.get("ohlcv_daily")
        if cls._is_usable(src) and len(src) >= cls.MIN_BARS:
            package["ohlcv"] = src
            package["daily_df"] = src
            package["data_repaired"] = True
            package.setdefault("data_contract", {})["ohlcv_repair_source"] = "ohlcv_daily"
            return package, True, "REPAIRED_FROM_OHLCV_DAILY"

        # Priority 3: timeseries.ohlcv_daily
        src = (package.get("timeseries") or {}).get("ohlcv_daily")
        if cls._is_usable(src) and len(src) >= cls.MIN_BARS:
            package["ohlcv"] = src
            package["ohlcv_daily"] = src
            package["daily_df"] = src
            package["data_repaired"] = True
            package.setdefault("data_contract", {})["ohlcv_repair_source"] = "timeseries.ohlcv_daily"
            return package, True, "REPAIRED_FROM_TIMESERIES"

        package["data_failure"] = True
        package.setdefault("data_contract", {})["ohlcv_repair_source"] = "NONE"
        return package, False, "NO_REPAIRABLE_SOURCE"

    @classmethod
    def annotate(cls, package: Dict[str, Any]) -> Dict[str, Any]:
        """
        Annotate package with DCV metadata for observability.
        Safe to call at any pipeline stage -- never blocks.
        Adds package["data_contract"]["dcv_*"] fields.
        """
        ohlcv = cls._resolve_ohlcv(package)
        ok, reason = cls.validate(package)
        conf = cls.confidence_level(package)
        dc = package.setdefault("data_contract", {})
        dc["dcv_valid"]      = ok
        dc["dcv_reason"]     = reason
        dc["dcv_confidence"] = conf
        dc["dcv_bars"]       = len(ohlcv) if ohlcv else 0
        dc["dcv_last_bar"]   = (ohlcv[-1].get("date") if ohlcv else None)
        return package

    # ── Internal helpers ───────────────────────────────────────────────────

    @classmethod
    def _resolve_ohlcv(cls, package: Dict[str, Any]) -> Optional[List[Dict]]:
        """Return the first non-empty list found across all known OHLCV locations."""
        for key in ("ohlcv", "daily_df", "ohlcv_daily"):
            v = package.get(key)
            if cls._is_usable(v):
                return v
        ts_v = (package.get("timeseries") or {}).get("ohlcv_daily")
        if cls._is_usable(ts_v):
            return ts_v
        return None

    @staticmethod
    def _is_usable(val: Any) -> bool:
        return isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict)

    @staticmethod
    def _check_nulls(ohlcv: List[Dict]) -> Optional[str]:
        tail = ohlcv[-min(10, len(ohlcv)):]
        for col in ("open", "high", "low", "close"):
            if any(r.get(col) is None for r in tail):
                return col
        return None

    @staticmethod
    def _check_staleness(ohlcv: List[Dict]) -> Tuple[bool, str]:
        try:
            last_date_str = ohlcv[-1].get("date", "")
            if not last_date_str:
                return False, ""
            last_dt = datetime.strptime(last_date_str, "%Y-%m-%d").date()
            days_old = (datetime.now(timezone.utc).date() - last_dt).days
            if days_old > MAX_STALENESS_DAYS:
                return True, f"STALE_DATA ({last_date_str}, {days_old}d old)"
        except Exception:
            pass
        return False, ""

    @staticmethod
    def _has_regime(package: Dict[str, Any]) -> bool:
        rs = package.get("regime_snapshot")
        if isinstance(rs, dict) and rs:
            return True
        macro = package.get("macro") or {}
        if isinstance(macro, dict):
            rs2 = macro.get("regime_snapshot")
            if isinstance(rs2, dict) and rs2:
                return True
        return False
