"""
AVSHUNTER ML Bridge — run_ml_on_vanguard_output.py
====================================================
Reads VANGUARD's vanguard_signals.csv output, runs every TRADE verdict
through the XGBoost+LSTM ML Confidence Engine, and writes a scored output.

Run AFTER run_vanguard_from_packages.py:

    python scripts\\run_ml_on_vanguard_output.py

Output:
    data\\output\\ml_scored_trades_<TIMESTAMP>.csv
    data\\output\\ml_scored_trades_latest.csv   (always overwrites)

Does NOT modify VANGUARD files. Read-only integration.
"""

import sys
import json
import logging
import pandas as pd
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent  # AVSHUNTER-Intelligence root
sys.path.insert(0, str(ROOT))

from ml_confidence_layer.ml_confidence_engine import (
    MLConfidenceEngine, VanguardSignal, MLEdgeResult
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ML-BRIDGE] %(message)s")
logger = logging.getLogger("ml_bridge")

# ── File paths ────────────────────────────────────────────────────────────────
VANGUARD_OUTPUT  = ROOT / "data" / "output" / "vanguard_signals.csv"
OUTPUT_DIR       = ROOT / "data" / "output"
MACRO_JSON       = ROOT / "macro_context.json"


def load_macro_regime() -> str:
    """Read macro regime from the live macro JSON context"""
    if MACRO_JSON.exists():
        with open(MACRO_JSON) as f:
            macro = json.load(f)
        return macro.get("regime", "NEUTRAL").upper()
    return "NEUTRAL"


def map_vanguard_row(row: pd.Series, macro_regime: str) -> VanguardSignal:
    """
    Map a VANGUARD CSV row to VanguardSignal.
    Column names are mapped defensively — missing columns default gracefully.
    """
    def get(col, default):
        return row[col] if col in row.index and pd.notna(row[col]) else default

    return VanguardSignal(
        ticker             = str(get("ticker", "UNKNOWN")),
        verdict            = str(get("verdict", "OBSERVE")),
        win_rate           = float(get("win_rate", 0.5)),
        expected_value     = float(get("expected_value", 1.0)),
        wyckoff_phase      = str(get("wyckoff_phase", "unknown")),
        control_state      = str(get("control_state", "NEUTRAL")),
        compression_state  = str(get("compression_state", "NORMAL")),
        macro_regime       = macro_regime,
        options_flow_score = float(get("options_flow_score", 50.0)),
        price              = float(get("price", 100.0)),
        volume_ratio       = float(get("volume_ratio", 1.0)),
        atr_pct            = float(get("atr_pct", 0.02)),
    )


def format_output(v_input: VanguardSignal, result: MLEdgeResult) -> dict:
    return {
        "ticker":             result.ticker,
        "verdict":            result.verdict,
        "ml_ensemble_score":  result.ensemble_score,
        "ml_xgb_score":       result.xgb_score,
        "ml_lstm_score":      result.lstm_score,
        "confidence_tier":    result.confidence_tier,
        "size_multiplier":    result.size_multiplier,
        "base_risk_usd":      result.base_risk_usd,
        "adjusted_risk_usd":  result.adjusted_risk_usd,
        "max_contracts":      result.max_contracts,
        "ml_note":            result.ml_note,
        # pass-through context
        "win_rate":           v_input.win_rate,
        "expected_value":     v_input.expected_value,
        "wyckoff_phase":      v_input.wyckoff_phase,
        "control_state":      v_input.control_state,
        "compression_state":  v_input.compression_state,
        "macro_regime":       v_input.macro_regime,
        "options_flow_score": v_input.options_flow_score,
        "price":              v_input.price,
        "scored_at":          result.timestamp,
    }


def main():
    logger.info("="*60)
    logger.info("AVSHUNTER ML Confidence Layer — Post-VANGUARD Scoring")
    logger.info("="*60)

    # ── Load VANGUARD output ──────────────────────────────────────────────────
    if not VANGUARD_OUTPUT.exists():
        logger.error(f"VANGUARD output not found: {VANGUARD_OUTPUT}")
        logger.error("Run: python scripts\\run_vanguard_from_packages.py first")
        sys.exit(1)

    df = pd.read_csv(VANGUARD_OUTPUT)
    logger.info(f"Loaded {len(df)} VANGUARD verdicts from {VANGUARD_OUTPUT.name}")

    # ── Filter TRADE verdicts ─────────────────────────────────────────────────
    trade_df = df[df["verdict"].str.upper() == "TRADE"].copy() if "verdict" in df.columns else df
    logger.info(f"TRADE verdicts to score: {len(trade_df)}")

    if len(trade_df) == 0:
        logger.info("No TRADE verdicts today. Exiting cleanly.")
        return

    # ── Load macro regime ─────────────────────────────────────────────────────
    macro_regime = load_macro_regime()
    logger.info(f"Macro regime: {macro_regime}")

    # ── Initialise ML engine ──────────────────────────────────────────────────
    engine = MLConfidenceEngine()

    # ── Score each TRADE ──────────────────────────────────────────────────────
    results = []
    for _, row in trade_df.iterrows():
        try:
            v_input = map_vanguard_row(row, macro_regime)
            result  = engine.score(v_input)
            results.append(format_output(v_input, result))
        except Exception as e:
            logger.warning(f"Failed to score {row.get('ticker', '?')}: {e}")

    if not results:
        logger.warning("No results produced.")
        return

    # ── Sort by ML score descending ───────────────────────────────────────────
    out_df = pd.DataFrame(results).sort_values("ml_ensemble_score", ascending=False)

    # ── Save output ───────────────────────────────────────────────────────────
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    timestamped_path = OUTPUT_DIR / f"ml_scored_trades_{ts}.csv"
    latest_path      = OUTPUT_DIR / "ml_scored_trades_latest.csv"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(timestamped_path, index=False)
    out_df.to_csv(latest_path,      index=False)

    logger.info(f"Saved: {timestamped_path.name}")
    logger.info(f"Latest: {latest_path.name}")

    # ── Console summary ───────────────────────────────────────────────────────
    print("\n" + "═"*65)
    print("   ML CONFIDENCE SCORES — TODAY'S TRADE VERDICTS")
    print("═"*65)
    print(f"  {'TICKER':<8} {'TIER':<10} {'ML SCORE':>8} {'RISK $':>8} {'CONTRACTS':>10}  NOTE")
    print("─"*65)
    for _, r in out_df.iterrows():
        print(f"  {r['ticker']:<8} {r['confidence_tier']:<10} "
              f"{r['ml_ensemble_score']:>7.1f}  "
              f"${r['adjusted_risk_usd']:>6.2f}  "
              f"{int(r['max_contracts']):>9}x  "
              f"{str(r['ml_note'])[:35]}")
    print("═"*65)
    print(f"\n  Total TRADE signals scored: {len(out_df)}")
    print(f"  HIGH conviction trades:     "
          f"{len(out_df[out_df['confidence_tier']=='HIGH'])}")
    print(f"  STANDARD conviction:        "
          f"{len(out_df[out_df['confidence_tier']=='STANDARD'])}")
    print(f"  Below STANDARD (review):    "
          f"{len(out_df[~out_df['confidence_tier'].isin(['HIGH','STANDARD'])])}")
    print(f"\n  Output: {latest_path}\n")


if __name__ == "__main__":
    main()
