"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AVSHUNTER · ATHEORETIC SIGNAL LAYER                                       ║
║  Enhancements: E9 (AtheoreticScanner), E11 (Theory-Stats Convergence),     ║
║                E12 (IV Surface Frequency Analyser)                          ║
║                                                                             ║
║  Deploy to: C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/                  ║
║  Runs in:   evening orchestrator (after superbrain, before EIL)            ║
║  Output:    atheoretic_signals_{run_id}.csv in superbrain folder            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
import warnings as _warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

log = logging.getLogger("avshunter.atheoretic")
_warnings.filterwarnings("ignore", category=RuntimeWarning)

# ─── THRESHOLDS ───────────────────────────────────────────────────────────────

ZSCORE_REVERSION_THRESHOLD = 2.0     # |z| > this → mean reversion signal
VOL_COMPRESSION_RATIO      = 0.70    # ATR(fast)/ATR(slow) < this → compressed
MOMENTUM_AUTOCORR_THRESHOLD= 0.30    # autocorrelation > this → momentum signal
IV_SKEW_ZSCORE_THRESHOLD   = 1.75    # |z| > this → IV skew anomaly

REVERSION_WINDOW    = 20
VOL_FAST_WINDOW     = 5
VOL_SLOW_WINDOW     = 20
MOMENTUM_LAGS       = [1, 2, 3]
IV_SKEW_WINDOW      = 20    # rolling window for IV skew z-score


# ─── E9: ATHEORETIC SCANNER ───────────────────────────────────────────────────

@dataclass
class AtheoreticResult:
    ticker:              str
    ath_score:           float      # 0–100 composite atheoretic score
    direction:           str        # LONG | SHORT | NEUTRAL
    zscore_signal:       str        # LONG | SHORT | NONE
    zscore_value:        float
    vol_compressed:      bool
    compression_ratio:   float
    momentum_signal:     str        # LONG | SHORT | NONE
    autocorr_value:      float
    signals_fired:       list[str]  # which sub-signals triggered
    notes:               str

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_line(self) -> str:
        return (
            f"[ATH] {self.ticker:<6} score={self.ath_score:.0f} "
            f"dir={self.direction:<7} "
            f"z={self.zscore_value:+.2f} "
            f"comp={self.compression_ratio:.2f} "
            f"signals={self.signals_fired}"
        )


class AtheoreticScanner:
    """
    Pure statistical signal generation — no Wyckoff theory, no regime bias.
    Finds: mean-reversion edges, volatility compression, momentum persistence.

    Operates on the actuarial parquet DB or any OHLCV dataframe.

    E9 Implementation: runs in parallel to Wyckoff-gated pipeline.
    The ath_score is combined with wbs_score in E11 (theory-stats convergence).
    """

    def __init__(
        self,
        data_source: Optional[Path | pd.DataFrame] = None,
        lookback: int = 252,
    ):
        self.lookback = lookback
        self._df: Optional[pd.DataFrame] = None

        if data_source is not None:
            if isinstance(data_source, (str, Path)):
                self._load_parquet(Path(data_source))
            elif isinstance(data_source, pd.DataFrame):
                self._df = data_source

    def _load_parquet(self, path: Path) -> None:
        try:
            self._df = pd.read_parquet(path)
            log.info(f"Loaded atheoretic DB: {len(self._df):,} rows from {path}")
        except Exception as e:
            log.error(f"Failed to load parquet: {e}")
            self._df = pd.DataFrame()

    def _get_ticker_data(self, ticker: str) -> pd.DataFrame:
        """Extract ticker slice from main DataFrame."""
        if self._df is None or self._df.empty:
            return pd.DataFrame()

        # Handle both 'ticker' and 'symbol' column names
        col = next((c for c in ["ticker", "symbol", "Ticker"] if c in self._df.columns), None)
        if col is None:
            log.warning("No ticker column found in DataFrame")
            return pd.DataFrame()

        df = self._df[self._df[col] == ticker].copy()
        df = df.sort_values("date") if "date" in df.columns else df
        return df.tail(self.lookback)

    # ── Signal 1: Z-score Mean Reversion ──────────────────────────────────────

    def zscore_reversion(
        self, ticker: str, data: Optional[pd.DataFrame] = None, window: int = REVERSION_WINDOW
    ) -> dict:
        """
        Z-score mean reversion.
        Signal when |z| > ZSCORE_REVERSION_THRESHOLD.
        """
        df = data if data is not None else self._get_ticker_data(ticker)
        if df.empty or "close" not in df.columns or len(df) < window + 5:
            return {"signal": "NONE", "zscore": 0.0, "error": "insufficient_data"}

        px     = df["close"].astype(float)
        roll_m = px.rolling(window).mean()
        roll_s = px.rolling(window).std()
        z      = ((px - roll_m) / roll_s).iloc[-1]

        if np.isnan(z):
            return {"signal": "NONE", "zscore": 0.0}

        if z < -ZSCORE_REVERSION_THRESHOLD:
            signal = "LONG"    # Oversold — expect reversion up
        elif z > ZSCORE_REVERSION_THRESHOLD:
            signal = "SHORT"   # Overbought — expect reversion down
        else:
            signal = "NONE"

        return {"signal": signal, "zscore": round(float(z), 4)}

    # ── Signal 2: Volatility Compression ──────────────────────────────────────

    def vol_compression(
        self, ticker: str, data: Optional[pd.DataFrame] = None,
        fast: int = VOL_FAST_WINDOW, slow: int = VOL_SLOW_WINDOW
    ) -> dict:
        """
        Volatility compression: ATR contraction before expansion.
        compression_ratio < VOL_COMPRESSION_RATIO → coiling for a move.
        Direction is undetermined — needs zscore or momentum to confirm.
        """
        df = data if data is not None else self._get_ticker_data(ticker)
        if df.empty or len(df) < slow + 5:
            return {"compressed": False, "compression_ratio": 1.0, "error": "insufficient_data"}

        # True range
        hi = df["high"].astype(float) if "high" in df.columns else df["close"].astype(float)
        lo = df["low"].astype(float)  if "low"  in df.columns else df["close"].astype(float)
        tr = (hi - lo)

        atr_fast = tr.rolling(fast).mean().iloc[-1]
        atr_slow = tr.rolling(slow).mean().iloc[-1]

        if atr_slow == 0 or np.isnan(atr_slow):
            return {"compressed": False, "compression_ratio": 1.0}

        ratio = round(float(atr_fast / atr_slow), 4)
        return {
            "compressed":        ratio < VOL_COMPRESSION_RATIO,
            "compression_ratio": ratio,
        }

    # ── Signal 3: Momentum Persistence ────────────────────────────────────────

    def momentum_signal(
        self, ticker: str, data: Optional[pd.DataFrame] = None,
        lags: list[int] = MOMENTUM_LAGS
    ) -> dict:
        """
        Autocorrelation-based momentum persistence.
        Positive autocorr → momentum signal (trend continuation).
        Negative autocorr → mean-reversion signal (confirms zscore_reversion).
        """
        df = data if data is not None else self._get_ticker_data(ticker)
        if df.empty or "close" not in df.columns or len(df) < 30:
            return {"signal": "NONE", "autocorr": 0.0, "error": "insufficient_data"}

        returns = df["close"].astype(float).pct_change().dropna()
        if len(returns) < 10:
            return {"signal": "NONE", "autocorr": 0.0}

        # Average autocorrelation across specified lags
        autocorrs = []
        for lag in lags:
            try:
                ac = returns.autocorr(lag=lag)
                if not np.isnan(ac):
                    autocorrs.append(ac)
            except Exception:
                pass

        if not autocorrs:
            return {"signal": "NONE", "autocorr": 0.0}

        mean_ac = float(np.mean(autocorrs))

        # Positive autocorr: recent direction likely continues
        if mean_ac > MOMENTUM_AUTOCORR_THRESHOLD:
            recent_ret = float(returns.iloc[-3:].mean())
            signal = "LONG" if recent_ret > 0 else "SHORT"
        else:
            signal = "NONE"

        return {"signal": signal, "autocorr": round(mean_ac, 4)}

    # ── Composite Scorer ───────────────────────────────────────────────────────

    def score_ticker(
        self, ticker: str, data: Optional[pd.DataFrame] = None
    ) -> AtheoreticResult:
        """Compute composite atheoretic score for one ticker."""
        df = data if data is not None else self._get_ticker_data(ticker)

        zr  = self.zscore_reversion(ticker, df)
        vc  = self.vol_compression(ticker, df)
        mom = self.momentum_signal(ticker, df)

        signals_fired = []
        score         = 0
        votes_long    = 0
        votes_short   = 0

        # Zscore: 40 points
        if zr.get("signal") == "LONG":
            score += 40; votes_long += 1; signals_fired.append("ZSCORE_LONG")
        elif zr.get("signal") == "SHORT":
            score += 40; votes_short += 1; signals_fired.append("ZSCORE_SHORT")

        # Vol compression: 30 points (direction-agnostic — add regardless)
        if vc.get("compressed"):
            score += 30; signals_fired.append("VOL_COMPRESSED")

        # Momentum: 30 points
        if mom.get("signal") == "LONG":
            score += 30; votes_long += 1; signals_fired.append("MOMENTUM_LONG")
        elif mom.get("signal") == "SHORT":
            score += 30; votes_short += 1; signals_fired.append("MOMENTUM_SHORT")

        # Direction vote
        if votes_long > votes_short:
            direction = "LONG"
        elif votes_short > votes_long:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        notes = []
        if "error" in zr:
            notes.append(f"zscore: {zr['error']}")

        return AtheoreticResult(
            ticker=ticker,
            ath_score=float(score),
            direction=direction,
            zscore_signal=zr.get("signal", "NONE"),
            zscore_value=zr.get("zscore", 0.0),
            vol_compressed=vc.get("compressed", False),
            compression_ratio=vc.get("compression_ratio", 1.0),
            momentum_signal=mom.get("signal", "NONE"),
            autocorr_value=mom.get("autocorr", 0.0),
            signals_fired=signals_fired,
            notes="; ".join(notes),
        )

    def scan_universe(self, tickers: list[str]) -> pd.DataFrame:
        """Scan all tickers. Returns DataFrame sorted by ath_score descending."""
        rows = []
        for ticker in tickers:
            try:
                result = self.score_ticker(ticker)
                rows.append(result.to_dict())
                log.debug(result.summary_line())
            except Exception as e:
                log.warning(f"Atheoretic scan failed for {ticker}: {e}")
                rows.append({"ticker": ticker, "ath_score": 0, "direction": "NEUTRAL",
                             "notes": str(e)})

        df = pd.DataFrame(rows)
        if not df.empty and "ath_score" in df.columns:
            df = df.sort_values("ath_score", ascending=False)
        return df

    def enrich_signals(self, signals: list[dict]) -> list[dict]:
        """
        Add ath_* fields to existing signal dicts.
        Used in evening orchestrator to enrich superbrain CSV.
        """
        out = []
        for sig in signals:
            ticker = sig.get("ticker", "UNKNOWN")
            result = self.score_ticker(ticker)
            enriched = dict(sig)
            enriched.update({
                "ath_score":          result.ath_score,
                "ath_direction":      result.direction,
                "ath_zscore":         result.zscore_value,
                "ath_zscore_signal":  result.zscore_signal,
                "ath_vol_compressed": result.vol_compressed,
                "ath_compression":    result.compression_ratio,
                "ath_momentum":       result.momentum_signal,
                "ath_autocorr":       result.autocorr_value,
                "ath_signals":        ",".join(result.signals_fired),
                "ath_notes":          result.notes,
            })
            out.append(enriched)
        return out


# ─── E11: THEORY-STATISTICS CONVERGENCE ───────────────────────────────────────

@dataclass
class TSConvergenceResult:
    ticker:            str
    wbs_score:         float     # Wyckoff/theory score
    ath_score:         float     # Atheoretic score
    ts_convergence:    float     # (wbs + ath) / 2
    wbs_direction:     str       # LONG | SHORT | NEUTRAL
    ath_direction:     str       # LONG | SHORT | NEUTRAL
    alignment:         str       # BOTH_LONG | BOTH_SHORT | THEORY_ONLY | STATS_ONLY | CONFLICTING
    kelly_ts_fraction: float     # Kelly modifier: 1.0 (both) / 0.65 (one) / 0.0 (conflicting)
    is_miss_candidate: bool      # ath>60 AND wbs<50 — theory may be filtering a real edge
    notes:             str

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_line(self) -> str:
        return (
            f"[TS] {self.ticker:<6} WBS={self.wbs_score:.0f} ATH={self.ath_score:.0f} "
            f"→ {self.alignment:<15} conv={self.ts_convergence:.0f} "
            f"kelly_ts={self.kelly_ts_fraction:.2f}"
            + (" ⚠MISS_CANDIDATE" if self.is_miss_candidate else "")
        )


def compute_ts_convergence(
    ticker:        str,
    wbs_score:     float,
    wbs_direction: str,
    ath_score:     float,
    ath_direction: str,
) -> TSConvergenceResult:
    """
    Compute theory-statistics convergence for one ticker.

    Alignment rules:
      BOTH_LONG/SHORT  → both agree: full Kelly fraction (1.0)
      THEORY_ONLY      → only Wyckoff fires: reduced fraction (0.65)
      STATS_ONLY       → only atheoretic fires: reduced fraction (0.65)
      CONFLICTING      → they disagree on direction: block (0.0)
    """
    ts_conv = round((wbs_score + ath_score) / 2, 2)

    wbs_dir = wbs_direction.upper().strip()
    ath_dir = ath_direction.upper().strip()

    # Normalise direction vocabulary
    def _norm(d: str) -> str:
        if d in ("LONG", "CALL", "BULLISH", "BUY"):   return "LONG"
        if d in ("SHORT", "PUT", "BEARISH", "SELL"):   return "SHORT"
        return "NEUTRAL"

    w = _norm(wbs_dir)
    a = _norm(ath_dir)

    wbs_active = wbs_score >= 50
    ath_active = ath_score >= 50

    if wbs_active and ath_active:
        if w == a and w != "NEUTRAL":
            alignment = f"BOTH_{w}"
            kelly_ts  = 1.0
        elif w == "NEUTRAL" or a == "NEUTRAL":
            alignment = "BOTH_ACTIVE_ONE_NEUTRAL"
            kelly_ts  = 0.75
        else:
            alignment = "CONFLICTING"
            kelly_ts  = 0.0
    elif wbs_active and not ath_active:
        alignment = "THEORY_ONLY"
        kelly_ts  = 0.65
    elif ath_active and not wbs_active:
        alignment = "STATS_ONLY"
        kelly_ts  = 0.65
    else:
        alignment = "NEITHER_ACTIVE"
        kelly_ts  = 0.0

    # Miss candidate: atheoretic sees it but theory filters it
    is_miss = (ath_score > 60) and (wbs_score < 50)

    notes = []
    if alignment == "CONFLICTING":
        notes.append(f"Theory says {w}, stats say {a} — do not trade")
    if is_miss:
        notes.append("Miss candidate — log for theory-anchor analysis")

    return TSConvergenceResult(
        ticker=ticker,
        wbs_score=wbs_score,
        ath_score=ath_score,
        ts_convergence=ts_conv,
        wbs_direction=w,
        ath_direction=a,
        alignment=alignment,
        kelly_ts_fraction=kelly_ts,
        is_miss_candidate=is_miss,
        notes="; ".join(notes),
    )


def enrich_with_ts_convergence(signals: list[dict]) -> list[dict]:
    """
    Add ts_* fields to signal dicts.
    Expects: wbs_score, ath_score, wbs_direction (or direction), ath_direction.
    """
    out = []
    for sig in signals:
        ticker     = sig.get("ticker", "UNKNOWN")
        wbs_score  = float(sig.get("wbs_score", 0))
        ath_score  = float(sig.get("ath_score", 0))
        wbs_dir    = sig.get("wbs_direction") or sig.get("direction", "NEUTRAL")
        ath_dir    = sig.get("ath_direction", "NEUTRAL")

        result = compute_ts_convergence(ticker, wbs_score, wbs_dir, ath_score, ath_dir)
        log.info(result.summary_line())

        enriched = dict(sig)
        enriched.update({
            "ts_convergence":    result.ts_convergence,
            "ts_alignment":      result.alignment,
            "ts_kelly_fraction": result.kelly_ts_fraction,
            "ts_miss_candidate": result.is_miss_candidate,
            "ts_wbs_direction":  result.wbs_direction,
            "ts_ath_direction":  result.ath_direction,
            "ts_notes":          result.notes,
        })
        out.append(enriched)
    return out


# ─── E12: IV SURFACE FREQUENCY ANALYSER ───────────────────────────────────────

@dataclass
class IVSkewResult:
    ticker:           str
    put_iv_zscore:    float        # z-score of put IV vs rolling mean
    call_iv_zscore:   float        # z-score of call IV vs rolling mean
    skew_zscore:      float        # z-score of (put_iv - call_iv) spread
    iv_signal:        str          # LONG_PUT | LONG_CALL | NEUTRAL
    anomaly_strength: str          # STRONG | MODERATE | WEAK | NONE
    kelly_iv_fraction:float        # IV signal modifier for Kelly (0.5–1.0)
    notes:            str

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_line(self) -> str:
        return (
            f"[IVFREQ] {self.ticker:<6} "
            f"put_z={self.put_iv_zscore:+.2f} "
            f"call_z={self.call_iv_zscore:+.2f} "
            f"skew_z={self.skew_zscore:+.2f} "
            f"→ {self.iv_signal:<12} ({self.anomaly_strength})"
        )


class IVSurfaceFrequencyAnalyser:
    """
    Detects IV skew anomalies using z-score frequency analysis.
    This is the options market equivalent of NSA frequency analysis —
    deviations from the expected distribution are the signal.

    E12: Direct instrument-selection signal for long calls vs long puts.
    """

    def __init__(self, window: int = IV_SKEW_WINDOW):
        self.window = window
        self._history: dict[str, list[dict]] = {}   # ticker → rolling IV history

    def update_history(self, ticker: str, put_iv: float, call_iv: float) -> None:
        """Add today's IV reading to rolling history."""
        if ticker not in self._history:
            self._history[ticker] = []
        self._history[ticker].append({
            "put_iv":  put_iv,
            "call_iv": call_iv,
            "skew":    put_iv - call_iv,
        })
        # Trim to window
        self._history[ticker] = self._history[ticker][-self.window:]

    def analyse(
        self,
        ticker:   str,
        put_iv:   Optional[float],
        call_iv:  Optional[float],
    ) -> IVSkewResult:
        """
        Analyse IV skew for instrument selection.

        put_iv / call_iv: current ATM implied volatility for puts and calls.
        Pulls rolling history from self._history (update_history() first).
        """
        notes = []

        if put_iv is None or call_iv is None:
            return IVSkewResult(
                ticker=ticker, put_iv_zscore=0.0, call_iv_zscore=0.0,
                skew_zscore=0.0, iv_signal="NEUTRAL", anomaly_strength="NONE",
                kelly_iv_fraction=0.75,
                notes="Insufficient IV data"
            )

        hist = self._history.get(ticker, [])

        if len(hist) < 5:
            # Not enough history — use raw skew direction
            raw_skew = put_iv - call_iv
            if raw_skew > 2.0:
                signal = "LONG_PUT"
            elif raw_skew < -2.0:
                signal = "LONG_CALL"
            else:
                signal = "NEUTRAL"
            return IVSkewResult(
                ticker=ticker, put_iv_zscore=0.0, call_iv_zscore=0.0,
                skew_zscore=0.0, iv_signal=signal, anomaly_strength="WEAK",
                kelly_iv_fraction=0.6,
                notes=f"Limited history ({len(hist)} obs) — raw skew={raw_skew:.2f}"
            )

        # Z-score each component vs rolling history
        put_ivs   = [h["put_iv"]  for h in hist]
        call_ivs  = [h["call_iv"] for h in hist]
        skews     = [h["skew"]    for h in hist]

        def _zscore(series: list, current: float) -> float:
            arr = np.array(series)
            mu, sigma = arr.mean(), arr.std()
            if sigma == 0:
                return 0.0
            return round(float((current - mu) / sigma), 4)

        put_z  = _zscore(put_ivs,  put_iv)
        call_z = _zscore(call_ivs, call_iv)
        skew_z = _zscore(skews,    put_iv - call_iv)

        # Signal logic:
        # Put IV spiking (z > threshold): informed put-buying → LONG_PUT
        # Call IV spiking (z > threshold) relative to put: unusual call demand → LONG_CALL
        # Skew z confirms direction

        if put_z > IV_SKEW_ZSCORE_THRESHOLD and skew_z > IV_SKEW_ZSCORE_THRESHOLD:
            signal   = "LONG_PUT"
            strength_val = min(put_z, skew_z)
        elif call_z > IV_SKEW_ZSCORE_THRESHOLD and skew_z < -IV_SKEW_ZSCORE_THRESHOLD:
            signal   = "LONG_CALL"
            strength_val = min(call_z, abs(skew_z))
        elif abs(skew_z) > IV_SKEW_ZSCORE_THRESHOLD:
            # Skew anomaly but call/put z-scores ambiguous — use skew direction
            signal       = "LONG_PUT" if skew_z > 0 else "LONG_CALL"
            strength_val = abs(skew_z)
            notes.append("Skew-only signal — monitor confirmation")
        else:
            signal       = "NEUTRAL"
            strength_val = 0.0

        # Anomaly strength
        if strength_val >= 3.0:
            strength  = "STRONG";   kelly_iv = 1.0
        elif strength_val >= 2.0:
            strength  = "MODERATE"; kelly_iv = 0.85
        elif strength_val >= IV_SKEW_ZSCORE_THRESHOLD:
            strength  = "WEAK";     kelly_iv = 0.65
        else:
            strength  = "NONE";     kelly_iv = 0.75

        return IVSkewResult(
            ticker=ticker,
            put_iv_zscore=put_z,
            call_iv_zscore=call_z,
            skew_zscore=skew_z,
            iv_signal=signal,
            anomaly_strength=strength,
            kelly_iv_fraction=kelly_iv,
            notes="; ".join(notes),
        )

    def enrich_signals(self, signals: list[dict]) -> list[dict]:
        """
        Enrich signal dicts with IV frequency analysis.
        Expects: put_iv / call_iv fields (from MarketData.app Greeks pull).
        """
        out = []
        for sig in signals:
            ticker  = sig.get("ticker", "UNKNOWN")
            put_iv  = sig.get("put_iv")  or sig.get("atm_put_iv")
            call_iv = sig.get("call_iv") or sig.get("atm_call_iv")

            # Update rolling history from current signal data
            if put_iv and call_iv:
                self.update_history(ticker, float(put_iv), float(call_iv))

            result = self.analyse(ticker, put_iv, call_iv)
            log.info(result.summary_line())

            enriched = dict(sig)
            enriched.update({
                "iv_put_zscore":    result.put_iv_zscore,
                "iv_call_zscore":   result.call_iv_zscore,
                "iv_skew_zscore":   result.skew_zscore,
                "iv_signal":        result.iv_signal,
                "iv_anomaly":       result.anomaly_strength,
                "iv_kelly_fraction":result.kelly_iv_fraction,
                "iv_notes":         result.notes,
            })
            out.append(enriched)
        return out
