"""
actuarial_hash_diagnostic.py
AVSHUNTER Diagnostic — Actuarial Database Hash Drift Analysis
============================================================
NOT IN ENHANCEMENT DOCUMENT — Added because run data reveals a critical issue.

CONFIRMED PROBLEM (from run 20260421_211944):
  150+ tickers including JPM, BAC, GOOG, UBER, DIS show:
    DataQualityWarning: [TICKER] All hit rates zero → a=0.40 fallback

  These are the most liquid, well-traded tickers in the universe.
  They DEFINITELY have actuarial history. Zero hit rates means the
  state hash computed at runtime doesn't match the hash used to build
  the 1.28M observation database.

  Impact: EV calculations for 150+ tickers use a=0.40 (generic fallback)
  instead of real actuarial hit rates. This degrades all downstream EV,
  Kelly sizing, and convergence scores.

WHAT THIS SCRIPT DOES:
  1. Loads the actuarial parquet database
  2. Loads the latest superbrain_enriched CSV
  3. Computes state hashes using the CURRENT hash logic
  4. Checks which tickers have matches in the database
  5. Reports the hit rate and identifies hash drift

RUN:
  cd C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence
  python actuarial_hash_diagnostic.py --run-id 20260421_211944
"""

import argparse
import logging
import sys
from pathlib import Path
import json

logger = logging.getLogger("AVSHUNTER.ActuarialDiag")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)


def run_diagnostic(run_id: str,
                   base_dir: str = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence",
                   sample_tickers: list = None) -> dict:
    """
    Main diagnostic function.
    
    Checks whether current state hashes match actuarial database.
    Returns diagnostic report dict.
    """
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        logger.error("pandas/numpy not available. Run in AVSHUNTER venv.")
        sys.exit(1)

    base = Path(base_dir)
    report = {
        "run_id": run_id,
        "status": "RUNNING",
        "actuarial_db_found": False,
        "superbrain_csv_found": False,
        "tickers_checked": 0,
        "tickers_with_matches": 0,
        "tickers_zero_hitrate": 0,
        "match_rate": 0.0,
        "likely_cause": None,
        "recommendations": []
    }

    # ── Load actuarial database ──────────────────────────────────────────────
    actuarial_paths = [
    base / "data" / "actuarial" / "actuarial_database.parquet",
    base / "vanguard" / "actuarial" / "database.parquet",
    base / "actuarial_database.parquet",

    # ✅ YOUR ACTUAL PATHS
    base / "vanguard" / "data" / "actuarial_database.parquet",
    base / "vanguard_backup" / "data" / "actuarial_database.parquet",
]

    actuarial_db = None
    for path in actuarial_paths:
        if path.exists():
            logger.info(f"Loading actuarial DB: {path}")
            try:
                actuarial_db = pd.read_parquet(path)
                report["actuarial_db_found"] = True
                report["actuarial_db_path"] = str(path)
                report["actuarial_db_rows"] = len(actuarial_db)
                report["actuarial_db_columns"] = list(actuarial_db.columns)
                logger.info(f"Actuarial DB: {len(actuarial_db):,} rows, "
                           f"columns: {list(actuarial_db.columns)[:10]}")
                break
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")

    if actuarial_db is None:
        logger.error("Could not find actuarial database. Check path.")
        report["status"] = "FAILED_NO_DB"
        report["likely_cause"] = "Actuarial database not found at expected paths"
        return report

    # ── Load superbrain CSV ──────────────────────────────────────────────────
    sb_paths = [
        base / "data" / "output" / "runs" / run_id / "superbrain" / f"superbrain_enriched_{run_id}.csv",
        base / "data" / "output" / "runs" / run_id / "superbrain" / f"eil_enriched_{run_id}.csv",
    ]

    superbrain_df = None
    for path in sb_paths:
        if path.exists():
            logger.info(f"Loading superbrain CSV: {path}")
            superbrain_df = pd.read_csv(path)
            report["superbrain_csv_found"] = True
            report["superbrain_csv_path"] = str(path)
            logger.info(f"Superbrain CSV: {len(superbrain_df)} rows")
            break

    if superbrain_df is None:
        logger.error(f"Could not find superbrain CSV for run {run_id}")
        report["status"] = "FAILED_NO_CSV"
        return report

    # ── Check hash columns ───────────────────────────────────────────────────
    hash_col = None
    for col in ["state_hash", "hash", "actuarial_hash", "vanguard_hash"]:
        if col in superbrain_df.columns:
            hash_col = col
            break

    if hash_col is None:
        logger.error("No hash column found in superbrain CSV. "
                    "Hash drift cannot be diagnosed directly.")
        report["status"] = "FAILED_NO_HASH_COLUMN"
        report["available_columns"] = list(superbrain_df.columns)[:30]
        report["likely_cause"] = (
            "Superbrain CSV does not contain state_hash column. "
            "This means EV engine never wrote hash to output. "
            "Check ev_engine_v2.py hash_state() function."
        )
        return report

    logger.info(f"Hash column found: {hash_col}")

    # ── Check which hashes match the database ────────────────────────────────
    db_hash_col = None
    for col in ["state_hash", "hash", "index"]:
        if col in actuarial_db.columns:
            db_hash_col = col
            break

    if db_hash_col is None and actuarial_db.index.name in ("state_hash", "hash"):
        db_hash_set = set(actuarial_db.index.astype(str))
        logger.info(f"Using index as hash key: {actuarial_db.index.name}")
    elif db_hash_col:
        db_hash_set = set(actuarial_db[db_hash_col].astype(str))
        logger.info(f"Database hash column: {db_hash_col}")
    else:
        logger.error("Cannot identify hash key in actuarial database.")
        report["status"] = "FAILED_HASH_NOT_IN_DB"
        return report

    # Sample or all tickers
    if sample_tickers:
        check_df = superbrain_df[superbrain_df["ticker"].isin(sample_tickers)]
    else:
        check_df = superbrain_df

    results = []
    for _, row in check_df.iterrows():
        ticker = row.get("ticker", "UNKNOWN")
        hash_val = str(row.get(hash_col, ""))
        has_match = hash_val in db_hash_set and hash_val != "nan" and hash_val != ""

        # Check actuarial columns for zero hit rates
        hit_rate_val = None
        for col in ["a", "hit_rate", "win_rate", "actuarial_hit_rate"]:
            if col in row and row[col] is not None:
                try:
                    hit_rate_val = float(row[col])
                    break
                except (ValueError, TypeError):
                    pass

        is_fallback = (hit_rate_val is not None and abs(hit_rate_val - 0.40) < 0.001)

        results.append({
            "ticker": ticker,
            "hash": hash_val[:16] + "..." if len(hash_val) > 16 else hash_val,
            "hash_in_db": has_match,
            "hit_rate": hit_rate_val,
            "is_fallback": is_fallback
        })

    results_df = pd.DataFrame(results)
    tickers_checked = len(results_df)
    tickers_with_matches = results_df["hash_in_db"].sum()
    tickers_fallback = results_df["is_fallback"].sum() if "is_fallback" in results_df else 0

    match_rate = tickers_with_matches / max(tickers_checked, 1)

    report["tickers_checked"] = tickers_checked
    report["tickers_with_matches"] = int(tickers_with_matches)
    report["tickers_zero_hitrate"] = int(tickers_fallback)
    report["match_rate"] = round(match_rate, 3)

    # Sample of failed tickers
    no_match = results_df[~results_df["hash_in_db"]].head(20)
    report["sample_no_match"] = no_match["ticker"].tolist()

    # ── Diagnosis ────────────────────────────────────────────────────────────
    if match_rate < 0.05:
        report["likely_cause"] = (
            "HASH DRIFT: State hash computation algorithm has changed since "
            "actuarial database was built. All hashes are mismatched. "
            "The database is effectively unusable in current state."
        )
        report["severity"] = "CRITICAL"
        report["recommendations"] = [
            "1. Check ev_engine_v2.py hash_state() function for recent changes",
            "2. Check if Vanguard layer columns have changed (add/remove fields in hash)",
            "3. Consider rebuilding actuarial database with current hash logic",
            "4. Temporary: use a=0.50 fallback instead of 0.40 (less conservative)",
        ]
    elif match_rate < 0.50:
        report["likely_cause"] = (
            "PARTIAL DRIFT: Some state hashes match but many don't. "
            "May be universe expansion (new tickers not in DB) or "
            "conditional hash logic change for certain states."
        )
        report["severity"] = "HIGH"
        report["recommendations"] = [
            "1. Compare tickers with matches vs without — any pattern?",
            "2. Check if new tickers were added to universe after DB was built",
            "3. Check if hash uses state/vol_regime — these change frequently",
        ]
    elif match_rate < 0.80:
        report["likely_cause"] = (
            "MODERATE DRIFT: Majority match but ~20-50% don't. "
            "Likely new tickers in universe or recent market state "
            "combinations not seen when DB was built."
        )
        report["severity"] = "MEDIUM"
        report["recommendations"] = [
            "1. Expand actuarial DB with recent market data",
            "2. Accept a=0.40 fallback for unmatched tickers (acceptable at this rate)",
        ]
    else:
        report["likely_cause"] = "Hash matching is healthy. Look elsewhere for the zero hit rate issue."
        report["severity"] = "LOW"

    report["status"] = "COMPLETE"

    # ── Output ───────────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("ACTUARIAL HASH DIAGNOSTIC REPORT")
    logger.info("=" * 60)
    logger.info(f"Run ID:           {run_id}")
    logger.info(f"Tickers checked:  {tickers_checked}")
    logger.info(f"Hash matches:     {tickers_with_matches} ({match_rate*100:.1f}%)")
    logger.info(f"Fallback a=0.40:  {tickers_fallback}")
    logger.info(f"Severity:         {report.get('severity', 'UNKNOWN')}")
    logger.info(f"Likely cause:     {report['likely_cause']}")
    logger.info("\nRecommendations:")
    for rec in report.get("recommendations", []):
        logger.info(f"  {rec}")
    if report["sample_no_match"]:
        logger.info(f"\nSample unmatched: {report['sample_no_match'][:10]}")
    logger.info("=" * 60)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AVSHUNTER Actuarial Hash Diagnostic")
    parser.add_argument("--run-id", required=True, help="Run ID (e.g. 20260421_211944)")
    parser.add_argument("--base-dir",
                        default=r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence",
                        help="AVSHUNTER base directory")
    parser.add_argument("--tickers", nargs="*",
                        help="Specific tickers to check (default: all)")
    parser.add_argument("--output-json",
                        help="Save report to JSON file")
    args = parser.parse_args()

    report = run_diagnostic(
        run_id=args.run_id,
        base_dir=args.base_dir,
        sample_tickers=args.tickers
    )

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info(f"Report saved: {args.output_json}")

    sys.exit(0 if report["status"] == "COMPLETE" else 1)
