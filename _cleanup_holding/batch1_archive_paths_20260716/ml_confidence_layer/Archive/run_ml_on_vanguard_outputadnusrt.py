"""
AVSHUNTER ML Bridge — run_ml_on_vanguard_output.py
====================================================
Reads VANGUARD's vanguard_signals.csv, runs every verdict through
the XGBoost+LSTM ML Confidence Engine, outputs adjusted EV scores.

Run AFTER run_vanguard_from_packages.py:
    python scripts\\run_ml_on_vanguard_output.py

Output:
    data\\output\\ml_scored_trades_latest.csv
"""

import sys
import json
import logging
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from ml_confidence_layer.ml_confidence_engine import (
    MLConfidenceEngine, VanguardSignal, MLEdgeResult
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ML] %(message)s")
logger = logging.getLogger("ml_bridge")

OUTPUT_DIR = ROOT / "data" / "output"
MACRO_JSON = ROOT / "macro_context.json"


def find_vanguard_output() -> Optional[Path]:
    """Find vanguard_signals.csv — handles flat and timestamped run folders."""
    # Flat structure
    flat = OUTPUT_DIR / "vanguard_signals.csv"
    if flat.exists():
        return flat
    # Timestamped run folders — pick latest
    runs_dir = OUTPUT_DIR / "runs"
    if runs_dir.exists():
        for folder in sorted(runs_dir.iterdir(), reverse=True):
            candidate = folder / "vanguard" / "vanguard_signals.csv"
            if candidate.exists():
                return candidate
    return None


def load_macro_regime() -> str:
    if MACRO_JSON.exists():
        with open(MACRO_JSON) as f:
            macro = json.load(f)
        return macro.get("regime", "NEUTRAL").upper()
    return "NEUTRAL"


def map_row(row: pd.Series, macro_regime: str) -> VanguardSignal:
    def get(col, default):
        return row[col] if col in row.index and pd.notna(row[col]) else default

    return VanguardSignal(
        ticker             = str(get("ticker", "UNKNOWN")),
        verdict            = str(get("verdict", "OBSERVE")),
        ev                 = float(get("expected_value", get("ev", 1.0))),
        win_rate           = float(get("win_rate", 0.5)),
        wyckoff_phase      = str(get("wyckoff_phase", "unknown")),
        control_state      = str(get("control_state", "NEUTRAL")),
        compression_state  = str(get("compression_state", "NORMAL")),
        macro_regime       = macro_regime,
        options_flow_score = float(get("options_flow_score", 50.0)),
        volume_ratio       = float(get("volume_ratio", 1.0)),
        atr_pct            = float(get("atr_pct", 0.02)),
    )


def format_output(signal: VanguardSignal, result: MLEdgeResult) -> dict:
    return {
        "ticker":          result.ticker,
        "verdict":         result.verdict,
        "raw_ev":          result.raw_ev,
        "ml_multiplier":   result.multiplier,
        "adjusted_ev":     result.adjusted_ev,
        "xgb_score":       result.xgb_score,
        "lstm_score":      result.lstm_score,
        "ensemble_score":  result.ensemble_score,
        "wyckoff_phase":   signal.wyckoff_phase,
        "control_state":   signal.control_state,
        "compression":     signal.compression_state,
        "macro_regime":    signal.macro_regime,
        "win_rate":        signal.win_rate,
        "note":            result.note,
        "scored_at":       result.scored_at,
    }


def main():
    logger.info("="*60)
    logger.info("AVSHUNTER ML Confidence Layer — Post-VANGUARD Scoring")
    logger.info("="*60)

    # ── Find VANGUARD output ──────────────────────────────────
    vanguard_path = find_vanguard_output()
    if not vanguard_path:
        logger.error("VANGUARD output not found in data\\output\\ or data\\output\\runs\\")
        logger.error("Run: python scripts\\run_vanguard_from_packages.py first")
        sys.exit(1)

    logger.info(f"Loading VANGUARD output: {vanguard_path}")
    df = pd.read_csv(vanguard_path)
    logger.info(f"Loaded {len(df)} verdicts")

    macro_regime = load_macro_regime()
    logger.info(f"Macro regime: {macro_regime}")

    engine  = MLConfidenceEngine()
    results = []

    for _, row in df.iterrows():
        try:
            signal = map_row(row, macro_regime)
            result = engine.score(signal)
            results.append(format_output(signal, result))
        except Exception as e:
            logger.warning(f"Failed to score {row.get('ticker', '?')}: {e}")

    if not results:
        logger.warning("No results produced.")
        return

    out_df = pd.DataFrame(results).sort_values("adjusted_ev", ascending=False)

    # ── Save ──────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts           = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    latest_path  = OUTPUT_DIR / "ml_scored_trades_latest.csv"
    archive_path = OUTPUT_DIR / f"ml_scored_trades_{ts}.csv"

    out_df.to_csv(latest_path,  index=False)
    out_df.to_csv(archive_path, index=False)

    # ── Console summary ───────────────────────────────────────
    print("\n" + "="*65)
    print("   ML CONFIDENCE SCORES — ADJUSTED EV")
    print("="*65)
    print(f"  {'TICKER':<8} {'VERDICT':<12} {'RAW EV':>7} {'MULT':>6} {'ADJ EV':>8}  NOTE")
    print("-"*65)
    for _, r in out_df.head(20).iterrows():
        print(f"  {r['ticker']:<8} {r['verdict']:<12} "
              f"{r['raw_ev']:>6.2f}  "
              f"{r['ml_multiplier']:>5.2f}x "
              f"{r['adjusted_ev']:>7.2f}  "
              f"{str(r['note'])[:30]}")
    print("="*65)
    print(f"\n  Total scored: {len(out_df)}")
    print(f"  EV boosted (>1.0x): {len(out_df[out_df['ml_multiplier'] > 1.0])}")
    print(f"  EV reduced (<1.0x): {len(out_df[out_df['ml_multiplier'] < 1.0])}")
    print(f"\n  Output: {latest_path}\n")


if __name__ == "__main__":
    main()
