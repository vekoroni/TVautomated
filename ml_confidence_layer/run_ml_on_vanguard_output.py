"""
AVSHUNTER ML Bridge — run_ml_on_vanguard_output.py
====================================================
Reads VANGUARD's vanguard_signals_enriched CSV, joins discovery context,
runs every verdict through the XGBoost+LSTM ML Confidence Engine, and
outputs adjusted EV scores.

Run AFTER run_vanguard_from_packages.py:
    python scripts\\run_ml_on_vanguard_output.py

Changes from previous version (2026-04-16):
    FIX-1  Macro path: reads dropbox/macro/macro_intelligence_latest.json
    FIX-2  wyckoff_phase: reads actual phase/wyckoff_phase_bucket from discovery
    FIX-3  atr_pct: reads actual atr_pct from discovery (was hardcoded to 0.02)
    FIX-4  Sub-regime awareness: TRANSITIONAL_BULLISH/BEARISH/NEUTRAL from macro JSON
    FIX-5  Sector alignment: macro sector tilt adjusts options_flow_score
    FIX-6  Forward bias: macro bullish_prob_pct included in output context note
    FIX-7  CompoundingTracker feedback: closed outcome history surfaced in output
"""

import sys, json, logging, re
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from ml_confidence_layer.ml_confidence_engine import (
    MLConfidenceEngine, VanguardSignal, MLEdgeResult
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ML] %(message)s")
logger = logging.getLogger("ml_bridge")

OUTPUT_DIR = ROOT / "data" / "output"
# FIX-1: Correct macro path
MACRO_JSON = ROOT / "dropbox" / "macro" / "macro_intelligence_latest.json"


# ── File discovery ─────────────────────────────────────────────────────────────

def find_vanguard_output() -> Tuple[Optional[Path], str]:
    runs_dir = OUTPUT_DIR / "runs"
    if runs_dir.exists():
        for folder in sorted(runs_dir.iterdir(), reverse=True):
            run_id = folder.name
            for pattern in [
                f"vanguard/vanguard_signals_enriched_{run_id}.csv",
                f"vanguard/vanguard_signals_{run_id}.csv",
                "vanguard/vanguard_signals_enriched.csv",
                "vanguard/vanguard_signals.csv",
            ]:
                c = folder / pattern
                if c.exists():
                    return c, run_id
    for name in ["vanguard_signals_enriched.csv", "vanguard_signals.csv"]:
        flat = OUTPUT_DIR / name
        if flat.exists():
            return flat, "latest"
    return None, ""


def find_discovery_csv(run_id: str) -> pd.DataFrame:
    candidates = []
    if run_id and run_id != "latest":
        candidates.append(
            OUTPUT_DIR / "runs" / run_id / "discovery"
            / f"discovery_candidates_ultimate_{run_id}.csv"
        )
    candidates.append(OUTPUT_DIR / "discovery_candidates_ultimate_latest.csv")
    for p in candidates:
        if p.exists():
            try:
                df = pd.read_csv(p, low_memory=False)
                logger.info(f"Discovery CSV: {p.name} ({len(df)} rows)")
                return df
            except Exception as e:
                logger.warning(f"Discovery CSV unreadable: {e}")
    logger.warning("Discovery CSV not found — Vanguard-only fields used")
    return pd.DataFrame()


def find_outcome_history() -> Dict[str, dict]:
    """FIX-7: Load closed trade outcomes from CompoundingTracker."""
    trade_log = ROOT / "ml_confidence_layer" / "trade_log" / "trades.json"
    outcomes: Dict[str, dict] = {}
    if not trade_log.exists():
        return outcomes
    try:
        with open(trade_log) as f:
            trades = json.load(f)
        for t in trades:
            if t.get("status") != "CLOSED":
                continue
            ticker = t.get("ticker", "")
            if not ticker:
                continue
            if ticker not in outcomes:
                outcomes[ticker] = {"wins": 0, "losses": 0, "last_outcome": ""}
            if t.get("outcome") == "WIN":
                outcomes[ticker]["wins"] += 1
            else:
                outcomes[ticker]["losses"] += 1
            outcomes[ticker]["last_outcome"] = t.get("outcome", "")
        logger.info(f"Outcome history: {len(outcomes)} tickers with closed trades")
    except Exception as e:
        logger.warning(f"Could not load trade outcomes: {e}")
    return outcomes


# ── Macro intelligence ─────────────────────────────────────────────────────────

def load_macro_intelligence() -> dict:
    """FIX-1+4+5+6: Load macro JSON and extract sub-regime, sector signals, forward bias."""
    result = {
        "sub_regime":       "TRANSITIONAL_NEUTRAL",
        "sector_signals":   {},
        "forward_short":    0.50,
        "forward_medium":   0.50,
        "macro_conviction": 0.50,
    }
    if not MACRO_JSON.exists():
        logger.warning(f"Macro JSON not found at {MACRO_JSON} — using TRANSITIONAL_NEUTRAL")
        return result
    try:
        with open(MACRO_JSON, encoding="utf-8") as f:
            macro = json.load(f)
        extras = macro.get("extras", {})
        while "extras" in extras and isinstance(extras.get("extras"), dict):
            extras = extras["extras"]

        # FIX-4: Sub-regime
        regime_state = str(macro.get("regime_state", "TRANSITIONAL")).upper()
        if "RISK_ON" in regime_state:
            sub_regime = "RISK_ON"
        elif "RISK_OFF" in regime_state or "BEAR" in regime_state:
            sub_regime = "RISK_OFF"
        else:
            vol  = extras.get("volatility", {})
            vix  = float(vol.get("vix_spot",   20.0))
            vix5 = float(vol.get("vix_5d_avg", 20.0))
            spy_w = float(extras.get("indices_etf", {}).get("SPY", {}).get("weekly_pct", 0.0))
            if spy_w > 0 and vix < vix5:
                sub_regime = "TRANSITIONAL_BULLISH"
            elif spy_w <= 0 or (vix >= vix5 and vix > 20):
                sub_regime = "TRANSITIONAL_BEARISH"
            else:
                sub_regime = "TRANSITIONAL_NEUTRAL"

        result["sub_regime"] = sub_regime

        # FIX-5: Sector signals
        result["sector_signals"] = {
            etf: info.get("signal", "NEUTRAL")
            for etf, info in extras.get("sectors", {}).items()
            if isinstance(info, dict)
        }

        # FIX-6: Forward bias
        fwd = extras.get("forward_bias", {})
        result["forward_short"]  = float(fwd.get("short_1_5d",   {}).get("bullish_prob_pct", 50.0)) / 100.0
        result["forward_medium"] = float(fwd.get("medium_6_10d", {}).get("bullish_prob_pct", 50.0)) / 100.0
        result["macro_conviction"] = float(
            extras.get("conviction_score", macro.get("macro_conviction", 0.50))
        )

        logger.info(
            f"Macro: sub_regime={sub_regime} | "
            f"fwd_short={result['forward_short']:.0%} | "
            f"fwd_mid={result['forward_medium']:.0%} | "
            f"conviction={result['macro_conviction']:.2f} | "
            f"sectors={len(result['sector_signals'])}"
        )
    except Exception as e:
        logger.warning(f"Macro parse error: {e}")
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

_SECTOR_ETF_MAP = {
    "Technology": "XLK", "Industrials": "XLI", "Financials": "XLF",
    "Materials": "XLB", "Consumer Discretionary": "XLY", "Healthcare": "XLV",
    "Utilities": "XLU", "Consumer Staples": "XLP", "Real Estate": "XLRE",
    "Energy": "XLE", "Communication Services": "XLC",
}
_ETF_SIGNAL_SCORE = {
    "LEAD_LONG": 1.0, "LONG": 0.5, "NEUTRAL": 0.0,
    "NEUTRAL_DEFENSIVE": 0.0, "REDUCE_TACTICAL": -0.5, "AVOID": -1.0,
}


def _f(row, col, default):
    if col in row.index and pd.notna(row[col]):
        try: return float(row[col])
        except: pass
    return default

def _s(row, col, default=""):
    if col in row.index and pd.notna(row[col]):
        return str(row[col]).strip()
    return default

def extract_controller(s: str) -> str:
    m = re.search(r"controller='(\w+)'", str(s))
    if m:
        v = m.group(1).upper()
        return "BUYERS" if v == "BUYERS" else "SELLERS" if v == "SELLERS" else "NEUTRAL"
    u = str(s).upper()
    if "BUYER" in u: return "BUYERS"
    if "SELLER" in u: return "SELLERS"
    return "NEUTRAL"


# ── Signal mapping ─────────────────────────────────────────────────────────────

def map_row(
    vs_row:   pd.Series,
    disc_row: Optional[pd.Series],
    macro:    dict,
    outcomes: Dict[str, dict],
) -> Tuple[VanguardSignal, dict]:

    ticker = _s(vs_row, "ticker", "UNKNOWN")
    has_disc = disc_row is not None and not (
        isinstance(disc_row, pd.DataFrame) and disc_row.empty
    )

    # FIX-2: Real Wyckoff phase
    phase_raw    = _s(disc_row, "phase", "")    if has_disc else ""
    phase_bucket = _s(disc_row, "wyckoff_phase_bucket", "") if has_disc else ""
    _letter_map  = {"A": "accumulation", "B": "accumulation", "C": "accumulation",
                    "D": "markup", "E": "markup"}
    if phase_raw in _letter_map:
        wyckoff_phase = _letter_map[phase_raw]
    elif "ACCUM"   in phase_bucket.upper(): wyckoff_phase = "accumulation"
    elif "DISTRIB" in phase_bucket.upper(): wyckoff_phase = "distribution"
    elif "MARKUP"  in phase_bucket.upper(): wyckoff_phase = "markup"
    elif "MARKDOW" in phase_bucket.upper(): wyckoff_phase = "markdown"
    else:
        trend = _s(vs_row, "layer2__trend_direction", "unknown").upper()
        wyckoff_phase = {"UP": "markup", "DOWN": "markdown",
                         "SIDEWAYS": "accumulation"}.get(trend, "unknown")

    # FIX-3: Real atr_pct
    atr_pct = (_f(disc_row, "atr_pct", None) / 100.0
               if has_disc and _f(disc_row, "atr_pct", None) is not None
               else 0.02)

    # Control state — prefer discovery plain string
    if has_disc:
        dc = _s(disc_row, "control_state", "")
        if dc and dc not in ("UNKNOWN", ""):
            u = dc.upper()
            control = "BUYERS" if "BUYER" in u else "SELLERS" if "SELLER" in u else "NEUTRAL"
        else:
            control = extract_controller(_s(vs_row, "layer1__control", "NEUTRAL"))
    else:
        control = extract_controller(_s(vs_row, "layer1__control", "NEUTRAL"))

    # Compression
    vr = _s(vs_row, "layer2__vol_regime", "NORMAL").upper()
    compression = ("COMPRESSED" if "CONTRAC" in vr or vr == "LOW"
                   else "EXPANDED" if "EXPAN" in vr or vr == "HIGH"
                   else "NORMAL")

    # FIX-4: Sub-regime
    sub_regime = macro["sub_regime"]

    # FIX-5: Sector-adjusted flow score
    sharpe     = _f(vs_row, "layer2__sharpe_ratio", 0.0)
    base_flow  = min(max(50.0 + sharpe * 500, 0.0), 100.0)
    sector     = _s(disc_row, "sector", "") if has_disc else ""
    etf        = _SECTOR_ETF_MAP.get(sector, "")
    sig_str    = macro["sector_signals"].get(etf, "NEUTRAL")
    sig_val    = _ETF_SIGNAL_SCORE.get(sig_str.upper(), 0.0)
    options_flow_score = float(min(max(base_flow + sig_val * 10.0, 0.0), 100.0))

    # Volume ratio
    vol_ratio = (_f(disc_row, "volume_ratio", None) if has_disc else None)
    if vol_ratio is None:
        mat = _s(vs_row, "layer2__trend_maturity", "EARLY").upper()
        vol_ratio = {"EARLY": 0.8, "DEVELOPING": 1.0, "MATURE": 1.4, "EXTENDED": 1.8}.get(mat, 1.0)

    # EV
    ev_raw        = _f(vs_row, "layer2__expected_value_20d", 0.0)
    win_rate      = _f(vs_row, "layer2__win_rate_20d", 0.5)
    ev_normalised = min(max(ev_raw / 0.20, 0.0), 1.0)

    # FIX-6+7: Context note
    hist       = outcomes.get(ticker, {})
    hist_str   = (f" | {hist['wins']}W/{hist['losses']}L last={hist['last_outcome']}"
                  if hist else "")
    ctx_note   = (
        f"fwd1-5d={macro['forward_short']:.0%} "
        f"fwd6-10d={macro['forward_medium']:.0%} "
        f"conviction={macro['macro_conviction']:.2f} "
        f"regime={sub_regime}"
        + (f" {etf}:{sig_str}" if etf else "")
        + hist_str
    )

    signal = VanguardSignal(
        ticker=ticker, verdict=_s(vs_row, "verdict", "OBSERVE"),
        ev=ev_raw, win_rate=win_rate,
        wyckoff_phase=wyckoff_phase, control_state=control,
        compression_state=compression, macro_regime=sub_regime,
        options_flow_score=options_flow_score, volume_ratio=vol_ratio,
        atr_pct=atr_pct, ev_normalised=ev_normalised,
    )
    extra = {
        "phase_raw": phase_raw, "phase_bucket": phase_bucket,
        "sector": sector, "sector_etf": etf, "sector_signal": sig_str,
        "sub_regime": sub_regime,
        "forward_short": macro["forward_short"], "forward_medium": macro["forward_medium"],
        "conviction": macro["macro_conviction"],
        "atr_pct_pct": atr_pct * 100.0,
        "n_observations": _f(vs_row, "layer2__n_observations", 0),
        "context_note": ctx_note,
        "hist_wins": hist.get("wins", 0), "hist_losses": hist.get("losses", 0),
    }
    return signal, extra


# ── Output ─────────────────────────────────────────────────────────────────────

def format_output(signal: VanguardSignal, result: MLEdgeResult, extra: dict) -> dict:
    return {
        "ticker":           result.ticker,
        "verdict":          result.verdict,
        "raw_ev":           round(result.raw_ev, 4),
        "ml_multiplier":    round(result.multiplier, 3),
        "adjusted_ev":      round(result.adjusted_ev, 4),
        "xgb_score":        round(result.xgb_score, 1),
        "lstm_score":       round(result.lstm_score, 1),
        "ensemble_score":   round(result.ensemble_score, 1),
        "wyckoff_phase":    signal.wyckoff_phase,
        "phase_raw":        extra["phase_raw"],
        "phase_bucket":     extra["phase_bucket"],
        "control_state":    signal.control_state,
        "compression":      signal.compression_state,
        "sub_regime":       extra["sub_regime"],
        "forward_short":    f"{extra['forward_short']:.0%}",
        "forward_medium":   f"{extra['forward_medium']:.0%}",
        "conviction":       round(extra["conviction"], 2),
        "sector":           extra["sector"],
        "sector_etf":       extra["sector_etf"],
        "sector_signal":    extra["sector_signal"],
        "win_rate":         round(signal.win_rate, 3),
        "n_observations":   int(extra["n_observations"]),
        "atr_pct":          round(extra["atr_pct_pct"], 2),
        "options_flow":     round(signal.options_flow_score, 1),
        "hist_wins":        extra["hist_wins"],
        "hist_losses":      extra["hist_losses"],
        "ml_note":          result.note,
        "context_note":     extra["context_note"],
        "scored_at":        result.scored_at,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("AVSHUNTER ML Confidence Layer — Post-VANGUARD Scoring")
    logger.info("=" * 60)

    vanguard_path, run_id = find_vanguard_output()
    if vanguard_path is None:
        logger.error("Vanguard output not found. Run run_vanguard_from_packages.py first.")
        sys.exit(1)

    logger.info(f"Vanguard output : {vanguard_path}")
    logger.info(f"Run ID          : {run_id}")
    vs_df    = pd.read_csv(vanguard_path, low_memory=False)
    logger.info(f"Loaded {len(vs_df)} Vanguard rows")

    disc_df  = find_discovery_csv(run_id)
    macro    = load_macro_intelligence()
    outcomes = find_outcome_history()

    disc_index = (disc_df.set_index("ticker")
                  if not disc_df.empty and "ticker" in disc_df.columns
                  else pd.DataFrame())

    engine  = MLConfidenceEngine()
    results = []

    for _, vs_row in vs_df.iterrows():
        ticker = str(vs_row.get("ticker", "?"))
        try:
            disc_row = None
            if not disc_index.empty and ticker in disc_index.index:
                disc_row = disc_index.loc[ticker]
                if isinstance(disc_row, pd.DataFrame):
                    disc_row = disc_row.iloc[0]
            signal, extra = map_row(vs_row, disc_row, macro, outcomes)
            result        = engine.score(signal)
            results.append(format_output(signal, result, extra))
        except Exception as e:
            logger.warning(f"Failed to score {ticker}: {e}")

    if not results:
        logger.warning("No results produced.")
        return

    out_df = pd.DataFrame(results).sort_values("adjusted_ev", ascending=False)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = OUTPUT_DIR / "ml_scored_trades_latest.csv"

    if run_id and run_id != "latest":
        run_out = OUTPUT_DIR / "runs" / run_id / f"ml_scored_trades_{run_id}.csv"
        run_out.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_csv(run_out, index=False)
        logger.info(f"Run output      : {run_out}")

    out_df.to_csv(latest_path, index=False)
    logger.info(f"Latest output   : {latest_path}")

    print("\n" + "=" * 75)
    print("   ML CONFIDENCE SCORES — ADJUSTED EV")
    print(f"   {macro['sub_regime']} | "
          f"Fwd 1-5d: {macro['forward_short']:.0%} | "
          f"Fwd 6-10d: {macro['forward_medium']:.0%} | "
          f"Conviction: {macro['macro_conviction']:.2f}")
    print("=" * 75)
    print(f"  {'TICKER':<8} {'VERDICT':<10} {'RAW_EV':>7} {'MULT':>6} "
          f"{'ADJ_EV':>8} {'PHASE':<14} {'CTRL':<8} {'SECTOR':>14}  NOTE")
    print("-" * 75)

    for _, r in out_df.head(25).iterrows():
        hist_tag = (f" [{r['hist_wins']}W/{r['hist_losses']}L]"
                    if r["hist_wins"] + r["hist_losses"] > 0 else "")
        sect = f"{r['sector_etf']}:{r['sector_signal'][:8]}" if r["sector_etf"] else ""
        phase_label = f"{r['phase_raw']}:{r['phase_bucket'][:8]}" if r["phase_raw"] else r["wyckoff_phase"][:12]
        print(
            f"  {r['ticker']:<8} {r['verdict']:<10} "
            f"{r['raw_ev']:>6.3f}  {r['ml_multiplier']:>5.2f}x "
            f"{r['adjusted_ev']:>7.3f}  {phase_label:<14} "
            f"{r['control_state']:<8} {sect:>14}  "
            f"{str(r['ml_note'])[:22]}{hist_tag}"
        )

    print("=" * 75)
    print(f"\n  Total scored : {len(out_df)}")
    print(f"  EV boosted   : {len(out_df[out_df['ml_multiplier'] > 1.0])}")
    print(f"  EV reduced   : {len(out_df[out_df['ml_multiplier'] < 1.0])}")
    print(f"  With history : {len(out_df[(out_df['hist_wins']+out_df['hist_losses'])>0])}")

    top = out_df[out_df["adjusted_ev"] > 0].head(5)
    if len(top):
        print("\n  Top signals by adjusted EV:")
        for _, r in top.iterrows():
            print(f"    {r['ticker']:<8} adj_ev={r['adjusted_ev']:.3f}  "
                  f"phase={r['phase_raw']} ctrl={r['control_state']}  "
                  f"regime={r['sub_regime']}  {r['sector_etf']}:{r['sector_signal']}")
    print()


if __name__ == "__main__":
    main()
