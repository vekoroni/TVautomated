"""
vanguard/integration/orchestrator_adapter.py
============================================
Converts the orchestrator's per-ticker package JSON into a VanguardInput
object that VanguardEngine can process.

Two public methods required by run_vanguard_from_packages.py:

    adapter.adapt_result(payload) -> AdaptResult
        Preferred — returns typed result with .ok, .v_input, .reason_codes,
        .error, .diagnostics. Caller logs rejection without catching exceptions.

    adapter.adapt(payload) -> VanguardInput
        Legacy — raises on failure.

The two standalone functions from the original stub are preserved:
    validate_ohlcv(df)   — direct validation helper
    adapt(dict)          — module-level alias (not the method)

ROOT CAUSE FIX (2026-04-17):
    The original file contained only two standalone functions and NO class.
    run_vanguard_from_packages.py imports OrchestratorAdapter as a class
    and calls adapter.adapt_result() and adapter.adapt().
    ImportError: cannot import name 'OrchestratorAdapter'.
    This file adds the complete class implementation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

log = logging.getLogger("orchestrator_adapter")

# ── Vanguard schema imports ───────────────────────────────────────────────────
try:
    from ..schemas.input_schema import (
        VanguardInput, TechnicalData, MacroData,
        OptionsData, CalendarData, MicrostructureData,
    )
    _SCHEMAS_OK = True
except ImportError:
    try:
        from vanguard.schemas.input_schema import (
            VanguardInput, TechnicalData, MacroData,
            OptionsData, CalendarData, MicrostructureData,
        )
        _SCHEMAS_OK = True
    except ImportError:
        _SCHEMAS_OK = False
        log.warning("orchestrator_adapter: vanguard schemas not importable")


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE FUNCTIONS (preserved from original stub)
# ─────────────────────────────────────────────────────────────────────────────

def validate_ohlcv(df) -> tuple:
    """Validate a DataFrame as OHLCV-compatible. Returns (ok: bool, reason: str)."""
    required_cols = {"open", "high", "low", "close", "volume"}
    if not isinstance(df, pd.DataFrame):
        return False, "BAD_TYPE"
    if df.empty:
        return False, "EMPTY"
    cols_lower = {c.lower() for c in df.columns}
    if not required_cols.issubset(cols_lower):
        return False, f"MISSING_COLUMNS:{','.join(sorted(required_cols - cols_lower))}"
    if len(df) < 20:
        return False, f"TOO_SHORT:{len(df)}"
    return True, "OK"


def adapt(orchestrator_output: dict) -> dict:
    """Module-level lightweight adapter (legacy interface)."""
    ticker = orchestrator_output.get("ticker", "")
    ohlcv_raw = orchestrator_output.get("ohlcv")
    df = _to_ohlcv_df(ohlcv_raw, ticker)
    valid, reason = validate_ohlcv(df)
    if not valid:
        return {"ok": False, "ticker": ticker, "reason": reason}
    return {"ok": True, "ticker": ticker, "rows": len(df)}


# ─────────────────────────────────────────────────────────────────────────────
# TYPED RESULT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AdaptResult:
    ok:             bool
    v_input:        Optional[Any]   = None
    reason_codes:   List[str]       = field(default_factory=list)
    error:          str             = ""
    exception_type: str             = ""
    diagnostics:    Dict[str, Any]  = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR ADAPTER CLASS
# ─────────────────────────────────────────────────────────────────────────────

class OrchestratorAdapter:
    """
    Converts an orchestrator package payload into a VanguardInput.

    Payload structure (built by build_orchestrator_like_payload()):
        ticker, current_price, as_of_utc
        technical_data  : {ohlcv, wyckoff_phase, wyckoff_phase_bucket,
                           compression_ratio, macro_regime, atr_current,
                           adx, high_52w, low_52w}
        macro_data      : {vix, vix_history, spy_price, spy_trend}
        calendar_data   : {days_to_earnings, sector}
        regime_snapshot : {vix, ...}
        ohlcv_daily     : list[dict]  (top-level fallback)
        timeseries      : {ohlcv_daily: list[dict]}
    """

    def adapt_result(self, payload: dict) -> AdaptResult:
        """Preferred path — never raises, returns AdaptResult."""
        try:
            v_input = self._build(payload)
            return AdaptResult(ok=True, v_input=v_input)
        except _Reject as e:
            return AdaptResult(ok=False, reason_codes=e.codes,
                               error=str(e), exception_type="AdapterReject",
                               diagnostics=e.diag)
        except Exception as e:
            return AdaptResult(ok=False, reason_codes=["ADAPTER_EXCEPTION"],
                               error=str(e), exception_type=type(e).__name__)

    def adapt(self, payload: dict):
        """Legacy path — raises on failure, returns VanguardInput."""
        return self._build(payload)

    # ── internal ──────────────────────────────────────────────────────────────

    def _build(self, payload: dict):
        if not _SCHEMAS_OK:
            raise _Reject(["SCHEMA_IMPORT_FAILED"],
                          "Cannot import vanguard schemas — check PYTHONPATH / package install")

        ticker = str(payload.get("ticker") or "").strip().upper()
        if not ticker:
            raise _Reject(["MISSING_TICKER"], "payload.ticker is empty")

        price = _f(payload.get("current_price"), 0.0)
        if price <= 0:
            disc  = payload.get("discovery") or {}
            price = _f(disc.get("stock_price") or disc.get("price"), 0.0)

        ts_raw = payload.get("as_of_utc") or payload.get("analysis_timestamp")
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")) \
                 if ts_raw else datetime.now(timezone.utc)
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)

        tech     = self._tech(payload, ticker)
        macro    = self._macro(payload)
        calendar = self._cal(payload)

        return VanguardInput(
            ticker              = ticker,
            analysis_timestamp  = ts,
            current_price       = price,
            technical           = tech,
            macro               = macro,
            calendar            = calendar,
            options             = OptionsData(),
            microstructure      = MicrostructureData(),
            data_quality_score  = _f(payload.get("data_quality_score"), 1.0),
            macro_regime        = tech.macro_regime,
            compression_ratio   = tech.compression_ratio,
            wyckoff_phase       = tech.wyckoff_phase,
        )

    def _tech(self, payload: dict, ticker: str) -> "TechnicalData":
        tp = payload.get("technical_data") or {}

        # OHLCV: check all known source paths in preference order
        raw = (tp.get("ohlcv")
               or payload.get("ohlcv_daily")
               or (payload.get("timeseries") or {}).get("ohlcv_daily")
               or payload.get("ohlcv"))
        df = _to_ohlcv_df(raw, ticker)

        if df.empty:
            raise _Reject(["NO_OHLCV_DATA"],
                          f"No valid OHLCV for {ticker} in any source field",
                          diag={"tried": ["technical_data.ohlcv",
                                          "ohlcv_daily", "timeseries.ohlcv_daily", "ohlcv"]})

        # 52-week high/low
        hi52 = _f(tp.get("high_52w"), 0.0)
        lo52 = _f(tp.get("low_52w"),  0.0)
        if (hi52 == 0.0 or lo52 == 0.0) and not df.empty:
            cl = df.get("close", df.get("Close", pd.Series()))
            if len(cl):
                tail = cl.tail(252)
                hi52 = hi52 or float(tail.max())
                lo52 = lo52 or float(tail.min())

        # ATR history for percentile scoring
        atr_hist = []
        try:
            hi = df.get("high", df.get("High", pd.Series()))
            lo = df.get("low",  df.get("Low",  pd.Series()))
            cl = df.get("close",df.get("Close",pd.Series()))
            if len(hi) >= 14 and len(lo) >= 14 and len(cl) >= 14:
                atr_hist = (hi - lo).abs().rolling(14).mean().dropna().tail(90).tolist()
        except Exception:
            pass

        # wyckoff_phase_bucket — inject only if TechnicalData accepts it
        bucket = tp.get("wyckoff_phase_bucket") or None
        extra  = {}
        if bucket:
            try:
                import inspect
                if "wyckoff_phase_bucket" in inspect.signature(TechnicalData.__init__).parameters:
                    extra["wyckoff_phase_bucket"] = bucket
            except Exception:
                pass

        return TechnicalData(
            ohlcv             = df,
            atr_current       = _f(tp.get("atr_current"),   0.0),
            atr_history       = atr_hist,
            adx               = _f(tp.get("adx"),            0.0),
            rsi               = _f(tp.get("rsi"),            50.0),
            high_52w          = hi52,
            low_52w           = lo52,
            wyckoff_phase     = tp.get("wyckoff_phase")  or None,
            compression_ratio = _fn(tp.get("compression_ratio")),
            macro_regime      = tp.get("macro_regime")   or None,
            **extra,
        )

    def _macro(self, payload: dict) -> "MacroData":
        mp  = payload.get("macro_data") or {}
        reg = payload.get("regime_snapshot") or {}
        vix = _f(mp.get("vix") or reg.get("vix") or 20.0, 20.0)
        raw_hist = mp.get("vix_history") or []
        vix_hist = [float(v) for v in (raw_hist if isinstance(raw_hist, list) else [])
                    if _isnumeric(v)]
        return MacroData(
            vix         = vix,
            vix_history = vix_hist,
            spy_price   = _f(mp.get("spy_price"), 0.0),
            spy_trend   = str(mp.get("spy_trend") or "UNKNOWN").upper(),
        )

    def _cal(self, payload: dict) -> "CalendarData":
        cp  = payload.get("calendar_data") or {}
        dte = cp.get("days_to_earnings")
        try:
            dte = int(dte) if dte is not None else None
        except (TypeError, ValueError):
            dte = None
        return CalendarData(
            days_to_earnings = dte,
            sector           = cp.get("sector") or None,
        )


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

class _Reject(Exception):
    def __init__(self, codes: list, msg: str = "", diag: dict = None):
        super().__init__(msg or codes[0])
        self.codes = codes
        self.diag  = diag or {}


def _f(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        r = float(v)
        return r if r == r else default
    except (TypeError, ValueError):
        return default


def _fn(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        r = float(v)
        return r if r == r else None
    except (TypeError, ValueError):
        return None


def _isnumeric(v: Any) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _to_ohlcv_df(raw: Any, ticker: str = "?") -> pd.DataFrame:
    """Normalise any OHLCV source to a clean lowercase-columns DataFrame."""
    if raw is None:
        return pd.DataFrame()
    if isinstance(raw, pd.DataFrame):
        df = raw.copy()
    elif isinstance(raw, list):
        if not raw:
            return pd.DataFrame()
        try:
            df = pd.DataFrame(raw)
        except Exception as e:
            log.debug(f"[{ticker}] OHLCV list->df failed: {e}")
            return pd.DataFrame()
    elif isinstance(raw, dict):
        try:
            df = pd.DataFrame(raw)
        except Exception as e:
            log.debug(f"[{ticker}] OHLCV dict->df failed: {e}")
            return pd.DataFrame()
    else:
        return pd.DataFrame()

    df.columns = [str(c).lower() for c in df.columns]

    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(set(df.columns)):
        log.debug(f"[{ticker}] OHLCV missing: {required - set(df.columns)}")
        return pd.DataFrame()

    # Sort oldest-first
    for date_col in ("timestamp", "date", "t"):
        if date_col in df.columns:
            try:
                if date_col == "timestamp" and df[date_col].dtype in (int, "int64", "float64"):
                    df[date_col] = pd.to_datetime(df[date_col], unit="ms", errors="coerce")
                else:
                    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df = df.sort_values(date_col).reset_index(drop=True)
            except Exception:
                pass
            break

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close", "volume"]).reset_index(drop=True)
    return df
