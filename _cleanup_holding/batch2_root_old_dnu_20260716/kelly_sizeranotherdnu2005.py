"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AVSHUNTER · KELLY POSITION SIZER                                          ║
║  Enhancements: E1 (Fractional-Kelly), E3 (Actuarial Calibration),          ║
║                E4 (Options b Auto-Calculator)                               ║
║                                                                             ║
║  Deploy to: C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/                  ║
║  Imports in: morning_validation.py, execution_intelligence_runner.py        ║
║                                                                             ║
║  Usage:                                                                     ║
║    from kelly_sizer import KellySizer                                       ║
║    sizer = KellySizer(account_size=50000)                                  ║
║    result = sizer.size_trade(wbs_score=75, max_profit=200, max_loss=300)   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

log = logging.getLogger("avshunter.kelly_sizer")

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

KELLY_FRACTION   = 0.5          # Half-Kelly — accounts for model uncertainty
MAX_RISK_PCT     = 0.02         # Hard cap: never risk more than 2% per trade
MIN_KELLY_PCT    = 0.0025       # Floor: ignore trades below 0.25% sizing
MIN_CONVERGENCE  = 40           # Minimum WBS score to size any position

# ─── WIN RATE TABLE ───────────────────────────────────────────────────────────
# Starting assumptions — overridden automatically by empirical calibration (E3)
# when actuarial_calibration.json exists.
# Format: (wbs_lo_inclusive, wbs_hi_exclusive): win_rate

DEFAULT_WIN_RATE_MAP: dict[tuple[int,int], float] = {
    (80, 101): 0.65,   # Strong signal
    (65,  80): 0.58,   # Moderate signal
    (50,  65): 0.52,   # Weak — minimum tradeable
    ( 0,  50): 0.00,   # Below threshold — NO TRADE
}


# ─── RESULT DATACLASS ─────────────────────────────────────────────────────────

@dataclass
class KellyResult:
    ticker:             str
    wbs_score:          float
    win_rate_p:         float       # empirical or assumed p(win)
    win_rate_source:    str         # "empirical" | "default"
    b_ratio:            float       # net odds (max_profit / max_loss)
    f_star:             float       # raw Kelly fraction
    f_kelly:            float       # half-Kelly fraction
    f_final:            float       # after hard cap
    dollar_risk:        float       # $ to risk on this trade
    max_contracts:      int         # estimated contracts (if options_premium given)
    regime_multiplier:  float       # from RCS gate (1.0 / 0.7 / 0.4)
    dollar_risk_adj:    float       # dollar_risk × regime_multiplier
    verdict:            str         # SIZE | REDUCE | NO_TRADE
    notes:              str

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_line(self) -> str:
        return (
            f"[KELLY] {self.ticker:<6} WBS={self.wbs_score:.0f} "
            f"p={self.win_rate_p:.2f}({self.win_rate_source[0].upper()}) "
            f"b={self.b_ratio:.2f} f*={self.f_final:.4f} "
            f"risk=${self.dollar_risk_adj:,.0f} → {self.verdict}"
        )


# ─── MAIN CLASS ───────────────────────────────────────────────────────────────

class KellySizer:
    """
    Fractional-Kelly position sizer for AVSHUNTER.

    Integrates:
      E1 — Half-Kelly formula with 2% hard cap
      E3 — Empirical win rate calibration from actuarial DB
      E4 — Options risk/reward b parameter from max_profit / max_loss
    """

    def __init__(
        self,
        account_size: float,
        kelly_fraction: float = KELLY_FRACTION,
        max_risk_pct:  float  = MAX_RISK_PCT,
        calibration_path: Optional[Path] = None,
        base_dir: Optional[Path] = None,
    ):
        self.account_size    = account_size
        self.kelly_fraction  = kelly_fraction
        self.max_risk_pct    = max_risk_pct
        self.win_rate_map    = dict(DEFAULT_WIN_RATE_MAP)
        self._calibration_ts = None

        # Resolve calibration file path
        if calibration_path:
            self.calibration_path = Path(calibration_path)
        elif base_dir:
            self.calibration_path = Path(base_dir) / "data" / "actuarial_calibration.json"
        else:
            self.calibration_path = Path(__file__).parent / "data" / "actuarial_calibration.json"

        self._load_calibration()

    # ── CALIBRATION (E3) ──────────────────────────────────────────────────────

    def _load_calibration(self) -> None:
        """Load empirical win rates from actuarial_calibration.json if present."""
        if not self.calibration_path.exists():
            log.info("No calibration file found — using default win rate map.")
            return

        try:
            with open(self.calibration_path) as f:
                cal = json.load(f)

            buckets = cal.get("wbs_win_rates", {})
            loaded = 0
            for key, rate in buckets.items():
                lo, hi = map(int, key.split("-"))
                self.win_rate_map[(lo, hi)] = float(rate)
                loaded += 1

            self._calibration_ts = cal.get("calibrated_at", "unknown")
            log.info(f"Loaded {loaded} empirical win rate buckets (calibrated: {self._calibration_ts})")

        except Exception as e:
            log.warning(f"Calibration load failed — using defaults. Error: {e}")

    def get_win_rate(self, wbs_score: float) -> tuple[float, str]:
        """Return (win_rate, source) for a given WBS score."""
        for (lo, hi), rate in self.win_rate_map.items():
            if lo <= wbs_score < hi:
                source = "empirical" if self._calibration_ts else "default"
                return rate, source
        return 0.0, "default"

    # ── OPTIONS b CALCULATOR (E4) ─────────────────────────────────────────────

    @staticmethod
    def compute_b(
        max_profit: Optional[float],
        max_loss:   Optional[float],
        bid:        Optional[float] = None,
        ask:        Optional[float] = None,
        strike_width: Optional[float] = None,
    ) -> float:
        """
        Compute net odds ratio b = max_profit / max_loss.

        Priority:
          1. Explicit max_profit / max_loss (from options intelligence CSV)
          2. Spread structure: bid/ask mid vs strike width
          3. Fallback: 1.0 (even odds — conservative)
        """
        # Method 1: direct values
        # FIX-TRUTHINESS (2026-04-23): Use explicit None checks — 0.0 is falsy
        # but could be a valid value passed as a string from a CSV row.
        if max_profit is not None and max_loss is not None and max_loss > 0:
            return round(max_profit / max_loss, 4)

        # Method 2: mid price vs strike width
        if bid is not None and ask is not None and strike_width:
            mid      = (bid + ask) / 2
            max_p    = (strike_width * 100) - (mid * 100)   # per contract
            max_l    = mid * 100
            if max_l > 0:
                return round(max_p / max_l, 4)

        # Fallback
        log.debug("b fallback to 1.0 — insufficient options data")
        return 1.0

    # ── CORE SIZING (E1) ──────────────────────────────────────────────────────

    def size_trade(
        self,
        ticker:            str,
        wbs_score:         float,
        max_profit:        Optional[float] = None,
        max_loss:          Optional[float] = None,
        bid:               Optional[float] = None,
        ask:               Optional[float] = None,
        strike_width:      Optional[float] = None,
        options_premium:   Optional[float] = None,   # per-contract cost for # contracts calc
        regime_multiplier: float = 1.0,              # from RCS gate: 1.0/0.7/0.4
        pse_size_override: Optional[float] = None,   # PSE-GAP2: pse_final_size anchor
    ) -> KellyResult:
        """
        Calculate fractional-Kelly position size.

        PSE integration (pse_size_override):
          If provided and > 0, pse_final_size becomes the dollar_risk anchor.
          PSE has already applied EV × MP × EIL × options × regime × confidence
          multipliers. Kelly's job is to refine with conviction signals
          (regime consensus × convergence × ts × iv fractions).
          WBS gate still fires: if wbs_score < MIN_CONVERGENCE the signal is
          genuinely too weak and pse_size_override is ignored — NO_TRADE returned.

        Returns KellyResult with full sizing breakdown.
        """
        notes = []

        # ── Step 1: Win rate ──────────────────────────────────────────────────
        p, source = self.get_win_rate(wbs_score)

        if p == 0.0:
            return KellyResult(
                ticker=ticker, wbs_score=wbs_score,
                win_rate_p=0.0, win_rate_source=source,
                b_ratio=0.0, f_star=0.0, f_kelly=0.0, f_final=0.0,
                dollar_risk=0.0, max_contracts=0,
                regime_multiplier=regime_multiplier, dollar_risk_adj=0.0,
                verdict="NO_TRADE",
                notes=f"WBS {wbs_score:.0f} below minimum threshold ({MIN_CONVERGENCE})"
            )

        q = 1.0 - p

        # ── Step 2: Net odds b ────────────────────────────────────────────────
        b = self.compute_b(max_profit, max_loss, bid, ask, strike_width)
        if b == 1.0:
            notes.append("b=1.0 fallback (no spread data)")

        # ── Step 3: Raw Kelly formula ─────────────────────────────────────────
        # FIX-B-GUARD (2026-04-23): Guard b <= 0 before division.
        # compute_b returns 0.0 when max_profit=0 (zero reward possible).
        # b=0 means no upside whatsoever — return NO_TRADE immediately.
        if b <= 0:
            return KellyResult(
                ticker=ticker, wbs_score=wbs_score,
                win_rate_p=p, win_rate_source=source,
                b_ratio=b, f_star=0.0, f_kelly=0.0, f_final=0.0,
                dollar_risk=0.0, max_contracts=0,
                regime_multiplier=regime_multiplier, dollar_risk_adj=0.0,
                verdict="NO_TRADE",
                notes=f"b={b:.4f} — zero or negative reward ratio, no edge to size"
            )

        # f* = (b*p - q) / b
        f_star = (b * p - q) / b

        if f_star <= 0:
            return KellyResult(
                ticker=ticker, wbs_score=wbs_score,
                win_rate_p=p, win_rate_source=source,
                b_ratio=b, f_star=f_star, f_kelly=0.0, f_final=0.0,
                dollar_risk=0.0, max_contracts=0,
                regime_multiplier=regime_multiplier, dollar_risk_adj=0.0,
                verdict="NO_TRADE",
                notes=f"Negative Kelly edge (f*={f_star:.4f}) — unfavourable odds at this win rate"
            )

        # ── Step 4: Half-Kelly + hard cap ─────────────────────────────────────
        f_kelly = f_star * self.kelly_fraction
        f_final = min(f_kelly, self.max_risk_pct)

        if f_kelly > self.max_risk_pct:
            notes.append(f"Capped at {self.max_risk_pct*100:.1f}% (raw Kelly would be {f_kelly*100:.2f}%)")

        if f_final < MIN_KELLY_PCT:
            return KellyResult(
                ticker=ticker, wbs_score=wbs_score,
                win_rate_p=p, win_rate_source=source,
                b_ratio=b, f_star=f_star, f_kelly=f_kelly, f_final=f_final,
                dollar_risk=0.0, max_contracts=0,
                regime_multiplier=regime_multiplier, dollar_risk_adj=0.0,
                verdict="NO_TRADE",
                notes=f"Kelly fraction {f_final*100:.3f}% below floor — edge too small to trade"
            )

        # ── Step 5: Dollar risk ───────────────────────────────────────────────
        # PSE-GAP2: if pse_size_override is present, use it as the base dollar risk.
        # pse_size_override is a fraction of portfolio (e.g. 0.008 = 0.8%).
        # Multiply by account_size to get dollar amount, then apply Kelly's
        # conviction multiplier (regime_multiplier already baked into PSE;
        # here it represents RCS × convergence × ts × iv refinement only).
        if pse_size_override and pse_size_override > 0:
            dollar_risk = round(self.account_size * pse_size_override, 2)
            notes.append(f"PSE anchor: {pse_size_override:.5f} × ${self.account_size:,.0f} = ${dollar_risk:,.0f}")
        else:
            dollar_risk = round(self.account_size * f_final, 2)

        # ── Step 6: Conviction multiplier (regime consensus × convergence fracs) ──
        # When PSE-anchored, regime_multiplier = RCS × conv × ts × iv (not pure regime).
        # When legacy, regime_multiplier = RCS gate only.
        dollar_risk_adj = round(dollar_risk * regime_multiplier, 2)

        # ── Step 7: Contract estimate ─────────────────────────────────────────
        max_contracts = 0
        if options_premium and options_premium > 0 and dollar_risk_adj > 0:
            cost_per_contract = options_premium * 100
            max_contracts = max(1, int(dollar_risk_adj / cost_per_contract))

        # ── Verdict ───────────────────────────────────────────────────────────
        if regime_multiplier < 0.5:
            verdict = "REDUCE"
            notes.append(f"Regime multiplier {regime_multiplier:.1f}× — reduced sizing")
        else:
            verdict = "SIZE"

        return KellyResult(
            ticker=ticker, wbs_score=wbs_score,
            win_rate_p=p, win_rate_source=source,
            b_ratio=b, f_star=round(f_star, 6),
            f_kelly=round(f_kelly, 6), f_final=round(f_final, 6),
            dollar_risk=dollar_risk, max_contracts=max_contracts,
            regime_multiplier=regime_multiplier,
            dollar_risk_adj=dollar_risk_adj,
            verdict=verdict,
            notes="; ".join(notes) if notes else ""
        )

    def size_batch(self, signals: list[dict], regime_multiplier: float = 1.0) -> list[dict]:
        """
        Size a list of signal dicts from morning_validation / EIL output.

        Expects each dict to have: ticker, wbs_score.
        Optionally: max_profit, max_loss, bid, ask, strike_width, options_premium.

        Returns enriched list with kelly_* fields added.
        """
        results = []
        for sig in signals:
            _pse_size = sig.get("pse_final_size")
            try:
                _pse_size = float(_pse_size) if _pse_size else None
            except (TypeError, ValueError):
                _pse_size = None

            # FIX-WBS-COL (2026-04-23): WBS scorer writes column "wbs" not "wbs_score".
            # size_batch() was silently reading 0 for every signal → NO_TRADE on all.
            # Fallback chain: wbs_score (legacy) → wbs (current WBS output) → 0.
            _wbs_raw = sig.get("wbs_score")
            if _wbs_raw is None or _wbs_raw == "":
                _wbs_raw = sig.get("wbs", 0)
            try:
                _wbs_val = float(_wbs_raw) if _wbs_raw is not None else 0.0
            except (TypeError, ValueError):
                _wbs_val = 0.0

            # FIX-PREMIUM-CHAIN (2026-04-23): Use explicit None checks.
            # The old `sig.get("options_premium") or sig.get("mid")` chain silently
            # drops 0.0 premium values because 0.0 is falsy — passing None to
            # size_trade and zeroing max_contracts even when a real premium exists.
            _prem = sig.get("options_premium")
            if _prem is None:
                _prem = sig.get("mid")
            try:
                _act_ev_weight = float(sig.get("actuarial_ev_weight", 1.0) or 1.0)
            except (TypeError, ValueError):
                _act_ev_weight = 1.0
            _act_ev_weight = max(0.0, min(1.0, _act_ev_weight))

            # ── TRF: Transition Risk Factor from Markov matrix ────────────────
            # Reduces regime_multiplier when the current phase is statistically
            # likely to transition to an unfavourable state.
            # trf=0.0 → no adjustment; trf=1.0 → full block.
            # Fails silently (trf=0.0) if matrix file is absent.
            try:
                from transition_matrix_consumer import get_consumer as _get_tmc
                _tmc = _get_tmc()
                _phase_val  = str(sig.get("phase_v2") or sig.get("wyckoff_phase_bucket") or "").strip().upper()
                _regime_val = str(sig.get("macro_regime") or sig.get("regime_state") or "ALL").strip().upper()
                _tier_val   = str(sig.get("future_momentum_bucket") or sig.get("tier") or "ALL").strip().upper()
                _trf_result = _tmc.adjust_kelly_multiplier(
                    regime_multiplier=regime_multiplier * _act_ev_weight,
                    phase=_phase_val,
                    regime=_regime_val,
                    tier=_tier_val,
                )
                _effective_regime_multiplier = _trf_result["adjusted_multiplier"]
                _trf_val    = _trf_result["trf"]
                _trf_source = _trf_result["trf_source"]
                _trf_sparse = _trf_result["sparse"]
            except Exception as _trf_exc:
                log.debug("TRF lookup failed — neutral fallback: %s", _trf_exc)
                _effective_regime_multiplier = regime_multiplier * _act_ev_weight
                _trf_val    = 0.0
                _trf_source = "NEUTRAL_FALLBACK"
                _trf_sparse = False

            result = self.size_trade(
                ticker             = sig.get("ticker", "UNKNOWN"),
                wbs_score          = _wbs_val,
                max_profit         = sig.get("max_profit"),
                max_loss           = sig.get("max_loss"),
                bid                = sig.get("bid"),
                ask                = sig.get("ask"),
                strike_width       = sig.get("strike_width"),
                options_premium    = _prem,
                regime_multiplier  = _effective_regime_multiplier,
                pse_size_override  = _pse_size,
            )
            enriched = dict(sig)
            enriched.update({
                "kelly_win_rate_p":     result.win_rate_p,
                "kelly_win_rate_source":result.win_rate_source,
                "kelly_b_ratio":        result.b_ratio,
                "kelly_f_star":         result.f_star,
                "kelly_f_final":        result.f_final,
                "kelly_dollar_risk":    result.dollar_risk,
                "kelly_dollar_risk_adj":result.dollar_risk_adj,
                "kelly_max_contracts":  result.max_contracts,
                "kelly_regime_mult":    result.regime_multiplier,
                "kelly_actuarial_ev_weight": _act_ev_weight,
                "kelly_trf":            _trf_val,
                "kelly_trf_source":     _trf_source,
                "kelly_trf_sparse":     _trf_sparse,
                "kelly_verdict":        result.verdict,
                "kelly_notes":          result.notes,
            })
            log.info(result.summary_line())
            results.append(enriched)
        return results


# ─── CALIBRATION BUILDER (E3) ─────────────────────────────────────────────────

class ActuarialCalibrator:
    """
    Builds actuarial_calibration.json from the 1.28M-observation parquet DB.
    Run manually or on a schedule — NOT in the live trading loop.

    Usage:
        cal = ActuarialCalibrator(parquet_path="path/to/actuarial.parquet")
        cal.calibrate(output_path="data/actuarial_calibration.json")
    """

    WBS_BUCKETS = [(0,50), (50,65), (65,80), (80,101)]

    def __init__(self, parquet_path: str | Path, min_trades: int = 30):
        self.parquet_path = Path(parquet_path)
        self.min_trades   = min_trades

    def calibrate(self, output_path: str | Path = "data/actuarial_calibration.json") -> dict:
        """
        Slice actuarial DB by WBS score bucket and compute empirical win rates.
        Writes actuarial_calibration.json.

        Requires columns in parquet: wbs_score, trade_outcome (1=win, 0=loss)
        """
        log.info(f"Loading actuarial DB from {self.parquet_path}...")

        try:
            df = pd.read_parquet(self.parquet_path)
        except Exception as e:
            raise RuntimeError(f"Could not load actuarial parquet: {e}")

        # Flexible column name handling
        wbs_col     = next((c for c in df.columns if "wbs" in c.lower()), None)
        outcome_col = next((c for c in df.columns if "outcome" in c.lower() or "win" in c.lower()), None)

        if not wbs_col or not outcome_col:
            raise ValueError(
                f"Cannot find wbs/outcome columns. Found: {list(df.columns)}\n"
                "Needs: wbs_score, trade_outcome (1=win, 0=loss)"
            )

        log.info(f"Using columns: wbs={wbs_col}, outcome={outcome_col}")
        log.info(f"Total observations: {len(df):,}")

        results = {}
        stats   = {}

        for (lo, hi) in self.WBS_BUCKETS:
            bucket = df[(df[wbs_col] >= lo) & (df[wbs_col] < hi)]
            n      = len(bucket)

            if n < self.min_trades:
                log.warning(f"WBS {lo}-{hi}: only {n} trades — keeping default rate")
                continue

            win_rate = bucket[outcome_col].mean()
            ci_95    = 1.96 * math.sqrt(win_rate * (1 - win_rate) / n)

            key = f"{lo}-{hi}"
            results[key] = round(win_rate, 4)
            stats[key]   = {
                "n_trades":  n,
                "win_rate":  round(win_rate, 4),
                "ci_95":     round(ci_95, 4),
                "ci_low":    round(max(0, win_rate - ci_95), 4),
                "ci_high":   round(min(1, win_rate + ci_95), 4),
            }
            log.info(f"WBS {key}: n={n:,} win_rate={win_rate:.3f} ±{ci_95:.3f}")

        output = {
            "calibrated_at":  datetime.utcnow().isoformat(),
            "n_total_trades": len(df),
            "min_trades_threshold": self.min_trades,
            "wbs_win_rates":  results,
            "bucket_stats":   stats,
        }

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2)

        log.info(f"Calibration written to {out_path}")
        return output


# ─── CLI ENTRY POINT ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AVSHUNTER Kelly Sizer — calibration tool")
    parser.add_argument("--calibrate", action="store_true",
                        help="Run actuarial calibration from parquet DB")
    parser.add_argument("--parquet",   type=str, help="Path to actuarial parquet file")
    parser.add_argument("--output",    type=str, default="data/actuarial_calibration.json")
    parser.add_argument("--account",   type=float, default=50000, help="Account size in $")
    parser.add_argument("--demo",      action="store_true", help="Run demo sizing examples")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if args.calibrate:
        if not args.parquet:
            print("ERROR: --parquet required for calibration")
        else:
            cal = ActuarialCalibrator(args.parquet)
            cal.calibrate(args.output)

    if args.demo:
        sizer = KellySizer(account_size=args.account)
        print(f"\n{'='*60}")
        print(f"AVSHUNTER Kelly Sizer — Demo (account=${args.account:,.0f})")
        print(f"{'='*60}")

        examples = [
            dict(ticker="SPY",  wbs_score=85, max_profit=200, max_loss=300, options_premium=3.00),
            dict(ticker="QQQ",  wbs_score=72, max_profit=150, max_loss=200, options_premium=2.50),
            dict(ticker="NVDA", wbs_score=60, max_profit=100, max_loss=150, options_premium=1.80),
            dict(ticker="AAPL", wbs_score=45, max_profit=80,  max_loss=120, options_premium=1.20),
        ]

        for regime_label, mult in [("RISK_ON", 1.0), ("NEUTRAL", 0.7), ("RISK_OFF", 0.4)]:
            print(f"\n  Regime: {regime_label} ({mult}×)")
            for ex in examples:
                r = sizer.size_trade(**ex, regime_multiplier=mult)
                print(f"    {r.summary_line()}")
