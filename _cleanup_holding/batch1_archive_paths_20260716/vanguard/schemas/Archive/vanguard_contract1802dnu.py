# vanguard_contract.py
"""
Vanguard Contract + Validator (v2.0) — FAIL-CLOSED
==================================================

Purpose
- Enforce a strict schema between Orchestrator and Vanguard.
- Reject malformed universes, insufficient history (EMA200 integrity), and stale/missing regime snapshots.
- Provide deterministic validation errors (no silent degradation).

Design principles
- Fail-closed: unknown/missing == STOP.
- Deterministic: same input => same verdict.
- Auditable: structured error codes + JSONL logs.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import json
import re

import pandas as pd


# ----------------------------- VERSIONING -----------------------------

CONTRACT_VERSION = "2.0"


# ------------------------------ ERROR CODES ---------------------------

class ContractErrorCode:
    # Contract / schema
    MISSING_FIELD = "MISSING_FIELD"
    WRONG_TYPE = "WRONG_TYPE"
    CONTRACT_VERSION_MISMATCH = "CONTRACT_VERSION_MISMATCH"

    # Universe / symbol
    TICKER_INVALID_FORMAT = "TICKER_INVALID_FORMAT"
    TICKER_NON_US_SUFFIX = "TICKER_NON_US_SUFFIX"
    TICKER_CONTAINS_DISALLOWED_CHAR = "TICKER_CONTAINS_DISALLOWED_CHAR"

    # Regime snapshot
    REGIME_MISSING = "REGIME_MISSING"
    REGIME_STALE = "REGIME_STALE"
    REGIME_FIELD_MISSING = "REGIME_FIELD_MISSING"

    # Data integrity
    DAILY_DF_EMPTY = "DAILY_DF_EMPTY"
    DAILY_DF_TOO_SHORT = "DAILY_DF_TOO_SHORT"
    DAILY_DF_MISSING_COLUMNS = "DAILY_DF_MISSING_COLUMNS"
    DAILY_DF_NOT_SORTED = "DAILY_DF_NOT_SORTED"
    DAILY_DF_DUPLICATE_INDEX = "DAILY_DF_DUPLICATE_INDEX"
    DAILY_DF_NANS_IN_CRITICAL_WINDOW = "DAILY_DF_NANS_IN_CRITICAL_WINDOW"
    DAILY_DF_GAPPY_RECENT = "DAILY_DF_GAPPY_RECENT"
    DAILY_DF_ZERO_VOLUME_RECENT = "DAILY_DF_ZERO_VOLUME_RECENT"


# ------------------------------ DATA MODELS ---------------------------

@dataclass(frozen=True)
class RegimeSnapshot:
    """
    Minimal regime contract required to gate discovery.
    Keep it strict: if you need more fields later, version-bump.
    """
    as_of_utc: str                 # ISO8601, e.g. "2026-02-11T15:00:00Z"
    regime_state: str              # e.g. "Transitional"
    dir_bias: str                  # e.g. "Selective Risk-On"
    vol_mode: str                  # e.g. "Rising but contained"
    regime_drift_status: str       # e.g. "Stable/Drifting/Flipped"
    macro_conviction: str          # e.g. "Low/Medium/High"


@dataclass(frozen=True)
class VanguardInput:
    """
    Strict Orchestrator → Vanguard input contract (v2.0).
    """
    contract_version: str
    ticker: str
    daily_df: pd.DataFrame
    intraday_df: Optional[pd.DataFrame]
    regime: RegimeSnapshot
    metadata: Dict[str, Any]       # source, run_id, refresh_status, etc.


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    field: str
    details: Dict[str, Any]


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    score: int                     # 0–100 integrity score (deterministic)
    issues: List[ValidationIssue]

    def raise_if_failed(self) -> None:
        if not self.ok:
            msgs = [f"{i.code} [{i.field}]: {i.message} | {i.details}" for i in self.issues]
            raise ValueError("Vanguard contract validation failed:\n" + "\n".join(msgs))


# ------------------------------ VALIDATION ----------------------------

_US_TICKER_REGEX = re.compile(r"^[A-Z]{1,5}$")  # strict US common stock style tickers
_DISALLOWED_CHARS = set(".-/\\:;,@#$%^&*()+=[]{}|<>?`~")
_NON_US_SUFFIXES = (".V", ".TO", ".L", ".AX", ".HK", ".SW", ".DE", ".PA", ".MI", ".SS", ".SZ", ".KS", ".KQ")

REQUIRED_DAILY_COLS = ("open", "high", "low", "close", "volume")
CRITICAL_COLS = ("close", "volume")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso8601_utc(s: str) -> datetime:
    # Accept "Z" suffix.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        # fail-closed: timezone is required
        raise ValueError("RegimeSnapshot.as_of_utc must be timezone-aware (UTC).")
    return dt.astimezone(timezone.utc)


def validate_ticker_us_only(ticker: str) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    t = (ticker or "").strip().upper()

    if any(ch in _DISALLOWED_CHARS for ch in t):
        issues.append(ValidationIssue(
            code=ContractErrorCode.TICKER_CONTAINS_DISALLOWED_CHAR,
            message="Ticker contains disallowed character(s).",
            field="ticker",
            details={"ticker": ticker}
        ))
        return issues  # deterministic early exit

    for suf in _NON_US_SUFFIXES:
        if t.endswith(suf):
            issues.append(ValidationIssue(
                code=ContractErrorCode.TICKER_NON_US_SUFFIX,
                message="Ticker appears to be non-US listed (suffix blocked).",
                field="ticker",
                details={"ticker": ticker, "suffix": suf}
            ))
            return issues

    if not _US_TICKER_REGEX.match(t):
        issues.append(ValidationIssue(
            code=ContractErrorCode.TICKER_INVALID_FORMAT,
            message="Ticker format invalid for strict US-equity universe.",
            field="ticker",
            details={"ticker": ticker, "expected": "^[A-Z]{1,5}$"}
        ))

    return issues


def validate_regime_snapshot(regime: RegimeSnapshot, max_age_hours: int = 36) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    if regime is None:
        return [ValidationIssue(
            code=ContractErrorCode.REGIME_MISSING,
            message="Regime snapshot is required to gate discovery.",
            field="regime",
            details={}
        )]

    # Field presence checks (fail-closed)
    required_fields = ("as_of_utc", "regime_state", "dir_bias", "vol_mode", "regime_drift_status", "macro_conviction")
    for f in required_fields:
        if not getattr(regime, f, None):
            issues.append(ValidationIssue(
                code=ContractErrorCode.REGIME_FIELD_MISSING,
                message="Regime snapshot missing required field.",
                field=f"regime.{f}",
                details={}
            ))

    # Staleness check
    try:
        as_of = _parse_iso8601_utc(regime.as_of_utc)
        age = _utcnow() - as_of
        if age > timedelta(hours=max_age_hours):
            issues.append(ValidationIssue(
                code=ContractErrorCode.REGIME_STALE,
                message="Regime snapshot is stale; discovery is blocked.",
                field="regime.as_of_utc",
                details={"as_of_utc": regime.as_of_utc, "age_hours": round(age.total_seconds() / 3600, 2),
                         "max_age_hours": max_age_hours}
            ))
    except Exception as e:
        issues.append(ValidationIssue(
            code=ContractErrorCode.REGIME_FIELD_MISSING,
            message="Regime snapshot time cannot be parsed as ISO8601 UTC.",
            field="regime.as_of_utc",
            details={"as_of_utc": getattr(regime, "as_of_utc", None), "error": str(e)}
        ))

    return issues


def _is_strictly_sorted_index(df: pd.DataFrame) -> bool:
    if df.index is None or len(df.index) < 2:
        return True
    return df.index.is_monotonic_increasing


def validate_daily_df_integrity(
    daily_df: pd.DataFrame,
    min_rows: int = 900,
    ema_window: int = 200,
    recent_window_days: int = 250,
    max_missing_ratio_recent: float = 0.03,   # 3%
    critical_nan_window: int = 200
) -> Tuple[int, List[ValidationIssue]]:
    """
    Returns (score, issues).
    Score is deterministic. Issues are fail conditions.
    """
    issues: List[ValidationIssue] = []
    score = 100

    if daily_df is None or not isinstance(daily_df, pd.DataFrame):
        return 0, [ValidationIssue(
            code=ContractErrorCode.WRONG_TYPE,
            message="daily_df must be a pandas DataFrame.",
            field="daily_df",
            details={"type": str(type(daily_df))}
        )]

    if daily_df.empty:
        return 0, [ValidationIssue(
            code=ContractErrorCode.DAILY_DF_EMPTY,
            message="daily_df is empty.",
            field="daily_df",
            details={}
        )]

    # Column normalisation: validate using lower-case canonical names.
    df = daily_df.copy()
    df.columns = [str(c).lower() for c in df.columns]

    missing_cols = [c for c in REQUIRED_DAILY_COLS if c not in df.columns]
    if missing_cols:
        return 0, [ValidationIssue(
            code=ContractErrorCode.DAILY_DF_MISSING_COLUMNS,
            message="daily_df missing required columns.",
            field="daily_df",
            details={"missing_cols": missing_cols, "required": list(REQUIRED_DAILY_COLS)}
        )]

    # Index sanity (time axis)
    if df.index.duplicated().any():
        issues.append(ValidationIssue(
            code=ContractErrorCode.DAILY_DF_DUPLICATE_INDEX,
            message="daily_df has duplicate timestamps in index.",
            field="daily_df.index",
            details={"duplicate_count": int(df.index.duplicated().sum())}
        ))
        score -= 40

    if not _is_strictly_sorted_index(df):
        issues.append(ValidationIssue(
            code=ContractErrorCode.DAILY_DF_NOT_SORTED,
            message="daily_df index is not sorted ascending; deterministic indicators cannot be trusted.",
            field="daily_df.index",
            details={}
        ))
        score -= 30

    # Length sufficiency (EMA200 + stability buffer)
    if len(df) < min_rows:
        issues.append(ValidationIssue(
            code=ContractErrorCode.DAILY_DF_TOO_SHORT,
            message="daily_df insufficient history; EMA200 integrity and long-rail indicators are not reliable.",
            field="daily_df",
            details={"rows": int(len(df)), "min_rows": min_rows}
        ))
        score -= 50

    # Critical NaNs in last critical_nan_window bars
    tail = df.tail(critical_nan_window)
    critical_nans = {c: int(tail[c].isna().sum()) for c in CRITICAL_COLS}
    if any(v > 0 for v in critical_nans.values()):
        issues.append(ValidationIssue(
            code=ContractErrorCode.DAILY_DF_NANS_IN_CRITICAL_WINDOW,
            message="NaNs present in critical columns in the recent window; fail-closed.",
            field="daily_df",
            details={"window": critical_nan_window, "critical_nans": critical_nans}
        ))
        score -= 60

    # Recent gappiness proxy: missing business days in last recent_window_days
    # We only run this if index looks like datetime.
    try:
        idx = pd.to_datetime(df.index, utc=True)
        recent = idx[-recent_window_days:] if len(idx) >= recent_window_days else idx
        start, end = recent.min(), recent.max()
        expected = pd.bdate_range(start=start, end=end, tz="UTC")
        expected_n = len(expected)
        actual_n = len(pd.DatetimeIndex(recent).unique())
        missing_ratio = 1.0 - (actual_n / expected_n) if expected_n > 0 else 0.0

        if missing_ratio > max_missing_ratio_recent:
            issues.append(ValidationIssue(
                code=ContractErrorCode.DAILY_DF_GAPPY_RECENT,
                message="Too many missing business days in recent window; data continuity compromised.",
                field="daily_df.index",
                details={"recent_window_days": recent_window_days,
                         "missing_ratio": round(missing_ratio, 4),
                         "max_missing_ratio": max_missing_ratio_recent,
                         "expected_bdays": expected_n,
                         "actual_days": actual_n}
            ))
            score -= 40
        else:
            score -= int(max(0, missing_ratio * 100))
    except Exception:
        # Not all feeds use datetime index; penalise lightly.
        score -= 5

    # Zero volume check (recent)
    vol_tail = df["volume"].tail(ema_window)
    if (vol_tail <= 0).any():
        issues.append(ValidationIssue(
            code=ContractErrorCode.DAILY_DF_ZERO_VOLUME_RECENT,
            message="Zero/negative volume detected in recent window; feed likely corrupt.",
            field="daily_df.volume",
            details={"window": ema_window, "count": int((vol_tail <= 0).sum())}
        ))
        score -= 50

    score = max(0, min(100, score))
    return score, issues


def validate_vanguard_input(vin: VanguardInput) -> ValidationResult:
    issues: List[ValidationIssue] = []
    score = 100

    # Contract version
    if not hasattr(vin, "contract_version") or not vin.contract_version:
        issues.append(ValidationIssue(
            code=ContractErrorCode.MISSING_FIELD,
            message="contract_version is required.",
            field="contract_version",
            details={}
        ))
        score = 0
    elif vin.contract_version != CONTRACT_VERSION:
        issues.append(ValidationIssue(
            code=ContractErrorCode.CONTRACT_VERSION_MISMATCH,
            message="Contract version mismatch; fail-closed to prevent schema drift.",
            field="contract_version",
            details={"expected": CONTRACT_VERSION, "got": vin.contract_version}
        ))
        score = 0

    # Ticker
    if not getattr(vin, "ticker", None):
        issues.append(ValidationIssue(
            code=ContractErrorCode.MISSING_FIELD,
            message="ticker is required.",
            field="ticker",
            details={}
        ))
        score = 0
    else:
        issues.extend(validate_ticker_us_only(vin.ticker))

    # Regime
    issues.extend(validate_regime_snapshot(vin.regime))

    # daily_df
    df_score, df_issues = validate_daily_df_integrity(vin.daily_df)
    score = min(score, df_score)
    issues.extend(df_issues)

    ok = (len(issues) == 0) and (score >= 90)  # hard fail threshold
    return ValidationResult(ok=ok, score=score, issues=issues)


# ------------------------------- LOGGING ------------------------------

def write_validation_log(
    result: ValidationResult,
    vin: VanguardInput,
    log_path: str
) -> None:
    """
    Deterministic JSONL audit log. No secrets. No raw data dumps.
    """
    payload = {
        "ts_utc": _utcnow().isoformat().replace("+00:00", "Z"),
        "contract_version_expected": CONTRACT_VERSION,
        "contract_version_got": vin.contract_version,
        "ticker": vin.ticker,
        "ok": result.ok,
        "score": result.score,
        "issue_count": len(result.issues),
        "issues": [asdict(i) for i in result.issues],
        "regime": asdict(vin.regime) if vin.regime else None,
        "metadata": vin.metadata,
        "daily_df_shape": list(vin.daily_df.shape) if isinstance(vin.daily_df, pd.DataFrame) else None,
        "intraday_df_shape": list(vin.intraday_df.shape) if isinstance(vin.intraday_df, pd.DataFrame) else None,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
