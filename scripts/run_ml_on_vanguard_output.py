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
import re
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


def extract_controller(control_str: str) -> str:
    """Extract controller value from serialised ControlState object string."""
    match = re.search(r"controller='(\w+)'", str(control_str))
    if match:
        val = match.group(1).upper()
        if val == "BUYERS":  return "BUYERS"
        if val == "SELLERS": return "SELLERS"
    return "NEUTRAL"


def map_row(row: pd.Series, macro_regime: str) -> VanguardSignal:
    def get(col, default):
        return row[col] if col in row.index and pd.notna(row[col]) else default

    # vol_regime -> compression_state
    # VANGUARD values: CONTRACTION, NORMAL, EXPANSION
    vol_regime = str(get("layer2__vol_regime", "NORMAL")).upper()
    if "CONTRAC" in vol_regime or vol_regime == "LOW":
        compression = "COMPRESSED"
    elif "EXPAN" in vol_regime or vol_regime == "HIGH":
        compression = "EXPANDED"
    else:
        compression = "NORMAL"

    # trend_direction -> wyckoff_phase proxy
    trend = str(get("layer2__trend_direction", "unknown")).upper()
    if trend == "UP":
        phase = "markup"
    elif trend == "DOWN":
        phase = "markdown"
    elif trend == "SIDEWAYS":
        phase = "accumulation"
    else:
        phase = "unknown"

    # layer1__control is a serialised ControlState object — extract controller field
    control = extract_controller(str(get("layer1__control", "NEUTRAL")))

    # sharpe_ratio -> options_flow proxy (normalised 0-100)
    # Sharpe values are small decimals (0.005-0.08), scale to 0-100
    sharpe     = float(get("layer2__sharpe_ratio", 0.0))
    flow_proxy = min(max(50.0 + sharpe * 500, 0), 100)

    # win_rate directly available — use as-is (0.0-1.0)
    win_rate = float(get("layer2__win_rate_20d", 0.5))

    # EV is a decimal fraction (0.03 = 3% expected gain)
    # Rescale to multiplier-style (0.03 -> 1.03 equivalent context for ML)
    ev_raw = float(get("layer2__expected_value_20d", 0.0))
    # Normalise to 0-1 range for ML (cap at 20% = very strong)
    ev_normalised = min(max(ev_raw / 0.20, 0), 1.0)

    # trend_maturity -> volume_ratio proxy
    maturity_raw = str(get("layer2__trend_maturity", "EARLY")).upper()
    vol_ratio = {"EARLY": 0.8, "DEVELOPING": 1.0, "MATURE": 1.4, "EXTENDED": 1.8}.get(maturity_raw, 1.0)

    return VanguardSignal(
        ticker             = str(get("ticker", "UNKNOWN")),
        verdict            = str(get("verdict", "OBSERVE")),
        ev                 = ev_raw,
        win_rate           = win_rate,
        wyckoff_phase      = phase,
        control_state      = control,
        compression_state  = compression,
        macro_regime       = macro_regime,
        options_flow_score = flow_proxy,
        volume_ratio       = vol_ratio,
        atr_pct            = 0.02,             # neutral default — not in VANGUARD output
        ev_normalised      = ev_normalised,    # dedicated field — EV scaled 0-1
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
