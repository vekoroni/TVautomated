#!/usr/bin/env python3
"""
Sprint 4 — Confirmation Ingester
Reads ml_eligible=1 closed trades from the trade journal for ML training.

Gating rule: if fewer than MIN_ELIGIBLE_TRADES eligible trades exist, logs
a warning and returns None. The pipeline continues normally — no error raised.

Usage:
    from confirmation_ingester import get_eligible_trades
    df = get_eligible_trades(db_path)
    if df is None:
        # below threshold — skip ML update
        pass

CLI (for inspection):
    python confirmation_ingester.py
    python confirmation_ingester.py --db path/to/trade_journal.db
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("avshunter.confirmation_ingester")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [INGESTER] %(levelname)s — %(message)s",
        datefmt="%H:%M:%S",
    )

MIN_ELIGIBLE_TRADES = 30
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "journal" / "trade_journal.db"

# Numeric feature columns available in closed_trades for regression
REGRESSION_FEATURES = [
    "dte_at_entry",
    "sb_conv_score",
    "rr_predicted",
    "ev_predicted",
    "win_rate_5d",
    "expected_value_5d",
    "win_rate_10d",
    "expected_value_10d",
    "win_rate_20d",
    "expected_value_20d",
    "ct_bifurcation_proximity",
    "ct_divergence_set_flag",
    "ct_stability_coeff",
    "ct_data_quality_score",
    "wbs",
    "regime_sensitivity_score",
    "vanna_at_entry",
]

# Target variables
TARGET_WIN   = "win"        # binary: pnl_usd > 0
TARGET_RR    = "rr_realised"


def get_eligible_trades(
    db_path: Optional[Path] = None,
    min_count: int = MIN_ELIGIBLE_TRADES,
    verbose: bool = True,
) -> Optional[object]:
    """
    Return a dict with:
      - 'df': pandas DataFrame of ml_eligible=1 closed trades (all columns)
      - 'features': REGRESSION_FEATURES columns (numeric, NaN-filled with 0)
      - 'target_win': binary Series (1=winner, 0=loser)
      - 'target_rr': rr_realised Series

    Returns None if eligible trade count < min_count.
    Never raises — caller continues normally on None.
    """
    db_path = Path(db_path or DEFAULT_DB_PATH)
    if not db_path.exists():
        if verbose:
            logger.warning("INGESTER: journal DB not found at %s", db_path)
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Check ml_eligible column exists (may be missing on old DBs before migration)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(closed_trades)")]
        if "ml_eligible" not in cols:
            if verbose:
                logger.warning(
                    "INGESTER: ml_eligible column not found — run update_ml_eligibility() first"
                )
            conn.close()
            return None

        rows = conn.execute(
            "SELECT * FROM closed_trades WHERE ml_eligible = 1"
        ).fetchall()
        conn.close()

    except Exception as exc:
        logger.warning("INGESTER: DB read failed: %s", exc)
        return None

    eligible_count = len(rows)
    if verbose:
        logger.info("INGESTER: %d eligible trades found (threshold=%d)", eligible_count, min_count)

    if eligible_count < min_count:
        if verbose:
            logger.warning(
                "INGESTER: %d eligible trades — minimum %d required for weight update. "
                "Skipping ML training. Pipeline continues normally.",
                eligible_count,
                min_count,
            )
        return None

    try:
        import pandas as pd
    except ImportError:
        logger.warning("INGESTER: pandas not available — returning raw rows only")
        return {"rows": [dict(r) for r in rows], "df": None, "features": None,
                "target_win": None, "target_rr": None}

    df = pd.DataFrame([dict(r) for r in rows])

    # Build feature matrix — fill missing with 0 (safe for sparse actuarial fields)
    feat_cols = [c for c in REGRESSION_FEATURES if c in df.columns]
    X = df[feat_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    # Build targets
    y_win = (df["pnl_usd"].fillna(0) > 0).astype(int)
    y_rr  = pd.to_numeric(df.get("rr_realised"), errors="coerce")

    if verbose:
        win_count = int(y_win.sum())
        logger.info(
            "INGESTER: %d eligible trades ready — %d winners / %d losers",
            eligible_count,
            win_count,
            eligible_count - win_count,
        )

    return {
        "df":         df,
        "features":   X,
        "feature_cols": feat_cols,
        "target_win": y_win,
        "target_rr":  y_rr,
        "count":      eligible_count,
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="AVSHUNTER Confirmation Ingester — inspect ML-eligible trades"
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="Path to trade_journal.db",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=MIN_ELIGIBLE_TRADES,
        help=f"Minimum eligible trades for ML update (default {MIN_ELIGIBLE_TRADES})",
    )
    args = parser.parse_args()

    result = get_eligible_trades(db_path=Path(args.db), min_count=args.min_count, verbose=True)
    if result is None:
        print(f"\nStatus: BELOW THRESHOLD — ML weight update will be skipped until {args.min_count}+ eligible trades exist.")
        sys.exit(0)

    df = result["df"]
    print(f"\nStatus: {result['count']} eligible trades ready for ML training")
    print(f"Features available: {result['feature_cols']}")
    print(f"Win/loss split: {int(result['target_win'].sum())} wins / {result['count'] - int(result['target_win'].sum())} losses")
    print(f"\nEligible trades:")
    for _, row in df.iterrows():
        print(
            f"  ID={row.get('trade_id'):3.0f} {row.get('ticker','?'):6s} "
            f"{str(row.get('options_direction','?')):4s} "
            f"outcome={str(row.get('outcome_class','?')):15s} "
            f"rr={row.get('rr_realised','N/A')}"
        )


if __name__ == "__main__":
    _cli()
