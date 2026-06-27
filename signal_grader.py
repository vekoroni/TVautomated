"""
signal_grader.py
AVSHUNTER — Signal timestamp grader.

Compares scanner signal_detected_at vs enrichment delta generated_at.
Assigns A/B/C/D grade to each candidate signal.

A-grade: signal > 24h before public news  → FULL_PIPELINE eligible
B-grade: signal 4–24h before news         → DISCOVERY_ONLY
C-grade: signal and news same session     → WATCHLIST_ONLY
D-grade: news arrived first (< 4h lead)  → CONTEXT_ONLY
Reject:  news > 4h before signal          → EXCLUDED
NO_NEWS: scanner found it; no news yet   → DISCOVERY_ONLY (not crowded)

This answers the core question: is AVSHUNTER arriving before the crowd?

Run after enrichment delta is produced:
  python signal_grader.py --run-id <run_id>

Run weekly performance audit:
  python signal_grader.py --audit --lookback 30
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SIGNAL_GRADER] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("signal_grader")

ROOT            = Path(__file__).resolve().parent
MANIFEST_PATH   = ROOT / "data" / "output" / "universe_scanner" / "scanner_manifest.json"
DELTA_PATH      = ROOT / "dropbox" / "macro" / "avshunter_macro_enrichment_delta.json"
HISTORY_PATH    = ROOT / "data" / "cache" / "signal_history.json"
RUNS_DIR        = ROOT / "data" / "output" / "runs"
GRADE_PERF_DIR  = ROOT / "data" / "output"


def grade_signal(
    ticker: str,
    signal_detected_at: str,
    news_confirmed_at: Optional[str],
) -> dict:
    """
    Grade a signal based on timing vs public news.

    signal_detected_at: UTC ISO string from scanner (signal_history.json or manifest)
    news_confirmed_at:  UTC ISO string from enrichment delta generated_at
                        (None if ticker not mentioned in delta)

    Returns: grade (A/B/C/D/NO_NEWS/REJECT/UNKNOWN), grade_label, hours_lead, route.
    """
    if not news_confirmed_at:
        return {
            "grade":       "NO_NEWS",
            "grade_label": "Signal with no news confirmation — pure microstructure",
            "hours_lead":  None,
            "route":       "DISCOVERY_ONLY",   # no news = not crowded, keep going
        }

    try:
        sig_dt  = datetime.fromisoformat(signal_detected_at.replace("Z", "+00:00"))
        news_dt = datetime.fromisoformat(news_confirmed_at.replace("Z", "+00:00"))
        hours_lead = (news_dt - sig_dt).total_seconds() / 3600
    except Exception as exc:
        log.debug("Timestamp parse failed for %s: %s", ticker, exc)
        return {
            "grade":       "UNKNOWN",
            "grade_label": "Timestamp parse error",
            "hours_lead":  None,
            "route":       "WATCHLIST_ONLY",
        }

    if hours_lead > 24:
        grade = "A"
        label = f"Signal {hours_lead:.1f}h before news — strong pre-crowd edge"
        route = "FULL_PIPELINE"
    elif hours_lead > 4:
        grade = "B"
        label = f"Signal {hours_lead:.1f}h before news — pre-crowd edge"
        route = "DISCOVERY_ONLY"
    elif hours_lead >= 0:
        grade = "C"
        label = f"Signal and news same session ({hours_lead:.1f}h lead)"
        route = "WATCHLIST_ONLY"
    elif hours_lead >= -4:
        grade = "D"
        label = f"News {abs(hours_lead):.1f}h before signal — crowd likely ahead"
        route = "CONTEXT_ONLY"
    else:
        grade  = "REJECT"
        label  = f"News {abs(hours_lead):.1f}h before signal — confirmed crowd trade"
        route  = "EXCLUDED"

    return {
        "grade":       grade,
        "grade_label": label,
        "hours_lead":  round(hours_lead, 2),
        "route":       route,
    }


def _extract_delta_tickers(delta: dict) -> set:
    """
    Extract all tickers mentioned in the enrichment delta.
    Checks macro_exposure_index_build sections (lists of tickers).
    """
    tickers: set = set()
    # Primary: macro_exposure_index_build
    mib = delta.get("macro_exposure_index_build", {})
    if isinstance(mib, dict):
        for section in mib.values():
            if isinstance(section, list):
                tickers.update(str(t).upper() for t in section)
    # Fallback: binary_options_analysis_policy bias maps
    try:
        policy   = delta.get("extras", {}).get("macro_enrichment_delta", {}) \
                        .get("binary_options_analysis_policy", {})
        bias_map = policy.get("current_macro_bias_map", {})
        for ticker_list in bias_map.values():
            if isinstance(ticker_list, list):
                tickers.update(str(t).upper() for t in ticker_list)
    except Exception:
        pass
    return tickers


def run_grader(run_id: str) -> dict:
    """
    Grade all signals for a given scanner run_id.

    Reads:
      - scanner_manifest.json → per-ticker signal_detected_at
      - avshunter_macro_enrichment_delta.json → news timestamp + ticker mentions
      - signal_history.json → update grades back into history

    Writes:
      - data/output/runs/{run_id}/signal_grades_{run_id}.json
      - Updates signal_history.json with grade + news_confirmed_at

    Returns grades dict {ticker: grade_result}.
    """
    manifest = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {}
    delta    = json.loads(DELTA_PATH.read_text())    if DELTA_PATH.exists() else {}
    history: dict = {}
    if HISTORY_PATH.exists():
        try:
            history = json.loads(HISTORY_PATH.read_text())
        except Exception:
            history = {}

    # News timestamp: when the enrichment delta was generated
    news_timestamp = delta.get("generated_at") or delta.get("as_of_utc") or ""

    # Which tickers appear in the delta (= have public news coverage)
    delta_tickers = _extract_delta_tickers(delta)
    log.info(
        "run_id=%s | news_timestamp=%s | delta_tickers=%d",
        run_id, news_timestamp[:19], len(delta_tickers),
    )

    # Per-ticker data from manifest
    manifest_tickers: dict = manifest.get("tickers", {})

    grades: dict = {}
    graded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    for ticker, ticker_data in manifest_tickers.items():
        ticker_upper = str(ticker).upper()
        signal_at    = ticker_data.get("signal_detected_at", "")
        if not signal_at:
            continue
        news_at = news_timestamp if ticker_upper in delta_tickers else None

        result = grade_signal(ticker_upper, signal_at, news_at)
        grades[ticker_upper] = {
            **result,
            "lss_score":          ticker_data.get("lss_score"),
            "lss_decision":       ticker_data.get("lss_decision"),
            "signal_detected_at": signal_at,
            "signal_run_id":      run_id,
            "news_confirmed_at":  news_at or "",
        }

        # Update history entry for this run
        if ticker_upper in history:
            for entry in history[ticker_upper]:
                if entry.get("signal_run_id") == run_id:
                    entry.update({
                        "news_confirmed_at": news_at or "",
                        "signal_grade":      result["grade"],
                        "signal_graded_at":  graded_at,
                    })
                    break

    # Apply grade route override — downgrade routes where news arrived first
    _GRADE_ROUTE_OVERRIDE: Dict[str, Optional[str]] = {
        "A":       None,              # keep lss_route (strong pre-crowd)
        "B":       None,              # keep lss_route (pre-crowd)
        "C":       "WATCHLIST_ONLY",  # same session — cap at watchlist
        "D":       "CONTEXT_ONLY",    # news beat us — demote
        "NO_NEWS": None,              # no news = not crowded — keep route
        "REJECT":  "EXCLUDED",        # hard exclude
        "UNKNOWN": None,              # parse error — don't penalise
    }
    for ticker_upper, gd in grades.items():
        override = _GRADE_ROUTE_OVERRIDE.get(gd.get("grade"))
        if override:
            gd["final_route"] = override
        else:
            # Keep whatever the scanner assigned
            t_data = manifest_tickers.get(ticker_upper, {})
            gd["final_route"] = t_data.get("lss_route") or gd.get("route") or "DISCOVERY_ONLY"

    # Write grade report
    grade_report_path = RUNS_DIR / run_id / f"signal_grades_{run_id}.json"
    grade_report_path.parent.mkdir(parents=True, exist_ok=True)
    grade_report_path.write_text(
        json.dumps(
            {
                "run_id":         run_id,
                "graded_at":      graded_at,
                "news_timestamp": news_timestamp,
                "grade_counts": {
                    g: sum(1 for v in grades.values() if v.get("grade") == g)
                    for g in ["A", "B", "C", "D", "NO_NEWS", "REJECT", "UNKNOWN"]
                },
                "grades": grades,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Write updated history
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")

    # Print summary
    print("\n=== SIGNAL GRADE REPORT ===")
    print(f"  run_id:         {run_id}")
    print(f"  news_timestamp: {news_timestamp[:19]}")
    for grade in ["A", "B", "C", "D", "NO_NEWS", "REJECT", "UNKNOWN"]:
        count           = sum(1 for v in grades.values() if v.get("grade") == grade)
        tickers_in_grade = [t for t, v in grades.items() if v.get("grade") == grade]
        if count:
            print(f"  Grade {grade:7}: {count:3d} tickers — {tickers_in_grade[:8]}")
    print(f"  Report: {grade_report_path}")
    print()

    log.info("Signal grading complete: %d tickers graded", len(grades))
    return grades


def audit_grade_performance(lookback_days: int = 30) -> None:
    """
    Read signal_history.json and produce a grade performance report.

    For each grade (A/B/C/D/NO_NEWS), shows:
      - How many signals in the period
      - Average LSS score per grade
      - Grade distribution as %
      - Most common tickers per grade

    This is the ground truth question: are pre-crowd signals (A/B) producing
    better outcomes than same-session (C/D)?

    Output: data/output/grade_performance_{YYYYMMDD}.json
    Run:    python signal_grader.py --audit --lookback 30
    """
    if not HISTORY_PATH.exists():
        log.warning("No signal_history.json found — run --run-id first to build history")
        return

    try:
        history: dict = json.loads(HISTORY_PATH.read_text())
    except Exception as exc:
        log.error("History load failed: %s", exc)
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

    # Collect all graded entries within lookback window
    all_entries: List[dict] = []
    for ticker, entries in history.items():
        for entry in entries:
            detected = entry.get("signal_detected_at", "")
            grade    = entry.get("signal_grade", "")
            if detected >= cutoff and grade:
                all_entries.append({
                    "ticker":           ticker,
                    "signal_grade":     grade,
                    "lss_score":        float(entry.get("lss_score") or 0),
                    "lss_decision":     entry.get("lss_decision", ""),
                    "signal_detected_at": detected,
                    "signal_run_id":    entry.get("signal_run_id", ""),
                })

    total = len(all_entries)
    if total == 0:
        log.info("No graded signals in last %d days — need more data", lookback_days)
        print(f"\nNo graded signals found in last {lookback_days} days.")
        print("Run 'python signal_grader.py --run-id <id>' after each pipeline run.")
        return

    grade_stats: dict = {}
    for grade in ["A", "B", "C", "D", "NO_NEWS", "REJECT", "UNKNOWN"]:
        grade_entries  = [e for e in all_entries if e["signal_grade"] == grade]
        count          = len(grade_entries)
        avg_lss        = round(sum(e["lss_score"] for e in grade_entries) / count, 1) if count else 0.0
        top_tickers    = list(dict.fromkeys(e["ticker"] for e in grade_entries))[:10]
        grade_stats[grade] = {
            "count":       count,
            "pct":         round(count / total * 100, 1) if total else 0.0,
            "avg_lss":     avg_lss,
            "top_tickers": top_tickers,
        }

    # Run distribution by lss_decision
    decision_dist: dict = {}
    for entry in all_entries:
        d = entry.get("lss_decision", "UNKNOWN")
        decision_dist[d] = decision_dist.get(d, 0) + 1

    report: dict = {
        "generated_at":   datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "lookback_days":  lookback_days,
        "total_signals":  total,
        "grade_stats":    grade_stats,
        "decision_dist":  decision_dist,
        "interpretation": {
            "pre_crowd_pct":     round((grade_stats["A"]["count"] + grade_stats["B"]["count"]) / total * 100, 1),
            "same_session_pct":  round(grade_stats["C"]["count"] / total * 100, 1),
            "crowd_arrived_pct": round((grade_stats["D"]["count"] + grade_stats["REJECT"]["count"]) / total * 100, 1),
            "no_news_pct":       round(grade_stats["NO_NEWS"]["count"] / total * 100, 1),
        },
    }

    # Write report
    today_str      = datetime.now(timezone.utc).strftime("%Y%m%d")
    report_path    = GRADE_PERF_DIR / f"grade_performance_{today_str}.json"
    GRADE_PERF_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Print summary
    print(f"\n=== GRADE PERFORMANCE REPORT — last {lookback_days} days ===")
    print(f"  Total signals: {total}")
    print()
    for grade, stats in grade_stats.items():
        if stats["count"] == 0:
            continue
        print(
            f"  Grade {grade:7}: {stats['count']:3d} ({stats['pct']:4.1f}%) "
            f"avg_lss={stats['avg_lss']:.1f} — "
            f"{stats['top_tickers'][:5]}"
        )
    print()
    interp = report["interpretation"]
    print(f"  Pre-crowd (A+B):    {interp['pre_crowd_pct']:.1f}%  ← target: majority")
    print(f"  Same-session (C):   {interp['same_session_pct']:.1f}%")
    print(f"  Crowd ahead (D+R):  {interp['crowd_arrived_pct']:.1f}%  ← target: < 20%")
    print(f"  No news (scanner only): {interp['no_news_pct']:.1f}%  ← ideal state")
    print(f"\n  Report: {report_path}")

    log.info("Grade performance audit complete: %d signals over %dd", total, lookback_days)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AVSHUNTER Signal Grader — timestamp discipline audit"
    )
    parser.add_argument(
        "--run-id", type=str, default="",
        help="Scanner run_id to grade (e.g. 20260628_2130). Reads from scanner_manifest.json.",
    )
    parser.add_argument(
        "--audit", action="store_true",
        help="Run weekly grade performance audit on signal_history.json",
    )
    parser.add_argument(
        "--lookback", type=int, default=30,
        help="Lookback days for --audit (default 30)",
    )
    args = parser.parse_args()

    if args.audit:
        audit_grade_performance(args.lookback)
        return 0

    if not args.run_id:
        # Default: use run_id from manifest
        if MANIFEST_PATH.exists():
            try:
                m = json.loads(MANIFEST_PATH.read_text())
                args.run_id = m.get("run_id", "")
            except Exception:
                pass

    if not args.run_id:
        parser.error("Specify --run-id <id> or ensure scanner_manifest.json exists")

    run_grader(args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
