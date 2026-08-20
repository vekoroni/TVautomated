# ============================================================
# AVSHUNTER — weekly_intelligence_report.py
# Version   : v1.0.0
# Built     : 2026-05-03
# Session   : May 2026 pipeline build
# SHA256    : 2102969a5c22a593
# Changes   : NEW-04 — Sunday prior adjustment review, STATE_PRIOR_ADJUSTMENTS drift detection
# ============================================================
"""
weekly_intelligence_report.py
==============================
AVSHUNTER — Weekly Intelligence Report (Foundation Stage 10)
Version : 1.0.0
Date    : 2026-05-03

Deploys to: C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\weekly_intelligence_report.py

PURPOSE
-------
Aggregates one week of closed trades and compares realised outcomes against
the actuarial predictions that were made at entry. Produces:

  1. weekly_report_{YYYYWW}.json  — machine-readable for orchestrator
  2. weekly_report_{YYYYWW}.txt   — human-readable for review
  3. prior_adjustment_review.json — suggested STATE_PRIOR_ADJUSTMENTS updates

The prior adjustment review is the critical output: it tells you where
the actuarial model's predicted win rates diverge from realised outcomes
by more than 10 percentage points, and what the adjustment should be.

USAGE
-----
    python weekly_intelligence_report.py              # current week
    python weekly_intelligence_report.py --week 2026-W18
    python weekly_intelligence_report.py --full       # all closed trades

CALLED BY
---------
    intelligent_orchestrator.py — run_weekly_report() — Sunday after close
    or manually at any time.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
DATA_DIR    = BASE_DIR / "data"
OUTPUT_DIR  = DATA_DIR / "output"
JOURNAL_DB  = DATA_DIR / "journal" / "trade_journal.db"
REPORT_DIR  = OUTPUT_DIR / "weekly_reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WEEKLY] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("weekly_report")

# ─────────────────────────────────────────────────────────────────────────────
# ACTUARIAL BASELINE — current STATE_PRIOR_ADJUSTMENTS
# Kept in sync with avshunter_discovery_ULTIMATE.py manually.
# ─────────────────────────────────────────────────────────────────────────────
CURRENT_PRIOR_ADJUSTMENTS = {
    ('MARKUP',       'RISK_ON'):       +2.0,
    ('MARKUP',       'RISK_OFF'):     +10.0,
    ('MARKUP',       'TRANSITIONAL'):  +1.0,
    ('ACCUMULATION', 'RISK_ON'):       -5.0,
    ('ACCUMULATION', 'RISK_OFF'):     +12.0,
    ('ACCUMULATION', 'TRANSITIONAL'): +3.0,
    ('DISTRIBUTION', 'RISK_ON'):      -15.0,
    ('DISTRIBUTION', 'RISK_OFF'):     -12.0,
    ('DISTRIBUTION', 'TRANSITIONAL'):-12.0,
}

# Divergence threshold: if |realised_win_rate - predicted_win_rate| > this,
# flag the bucket for prior adjustment review.
DIVERGENCE_THRESHOLD = 0.10   # 10 percentage points


# ─────────────────────────────────────────────────────────────────────────────
# LOAD CLOSED TRADES
# ─────────────────────────────────────────────────────────────────────────────

def _load_closed_trades(db_path: Path, since_date: Optional[str] = None) -> List[Dict]:
    """Load closed trades from journal, optionally filtered to a date window."""
    try:
        sys.path.insert(0, str(BASE_DIR))
        from avshunter_trade_journal import get_db
    except ImportError as e:
        log.error(f"Cannot import trade journal: {e}")
        return []

    try:
        conn  = get_db(db_path)
        query = "SELECT * FROM closed_trades"
        params: list = []
        if since_date:
            query  += " WHERE exit_date >= ?"
            params  = [since_date]
        rows = conn.execute(query, params).fetchall()
        cols = [d[0] for d in conn.execute(query, params).description] if rows else []
        conn.close()

        # Re-query for column names
        conn  = get_db(db_path)
        cur   = conn.execute(query, params)
        cols  = [d[0] for d in cur.description]
        rows  = cur.fetchall()
        conn.close()
        return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        log.warning(f"Could not load closed trades: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# WEEKLY STATS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def compute_weekly_stats(trades: List[Dict]) -> Dict:
    """Compute summary statistics for a set of closed trades."""
    if not trades:
        return {"n_trades": 0}

    n = len(trades)
    winners   = [t for t in trades if t.get('outcome_class') in ('TRUE_WINNER', 'PROCESS_WIN')]
    win_rate  = len(winners) / n

    pnl_vals  = [_safe_float(t.get('pnl_usd'))          for t in trades]
    rr_r_vals = [_safe_float(t.get('rr_realised'))       for t in trades if t.get('rr_realised')]
    rr_p_vals = [_safe_float(t.get('rr_predicted'))      for t in trades if t.get('rr_predicted')]
    hold_vals = [_safe_float(t.get('hold_days'))         for t in trades if t.get('hold_days')]
    wr_10d    = [_safe_float(t.get('win_rate_10d'))      for t in trades if t.get('win_rate_10d')]

    avg_pnl     = round(sum(pnl_vals) / n, 2)          if pnl_vals  else 0.0
    total_pnl   = round(sum(pnl_vals), 2)               if pnl_vals  else 0.0
    avg_rr_real = round(sum(rr_r_vals) / len(rr_r_vals), 3) if rr_r_vals else 0.0
    avg_rr_pred = round(sum(rr_p_vals) / len(rr_p_vals), 3) if rr_p_vals else 0.0
    avg_hold    = round(sum(hold_vals) / len(hold_vals), 1)  if hold_vals else 0.0
    avg_wr_pred = round(sum(wr_10d)    / len(wr_10d),    3)  if wr_10d    else 0.0

    outcomes    = {}
    for cls in ('TRUE_WINNER', 'PROCESS_WIN', 'OUTCOME_LOSS', 'TRUE_LOSER'):
        outcomes[cls] = len([t for t in trades if t.get('outcome_class') == cls])

    wall_count    = sum(1 for t in trades if t.get('wall_breached') == 1)
    target_count  = sum(1 for t in trades if t.get('target_reached') == 1)
    stop_exits    = sum(1 for t in trades if 'STOP' in str(t.get('exit_reason', '')).upper())
    time_exits    = sum(1 for t in trades if 'TIME'    in str(t.get('exit_reason', '')).upper())
    expired_exits = sum(1 for t in trades if 'EXPIRE' in str(t.get('exit_reason', '')).upper())

    return {
        "n_trades":             n,
        "win_rate":             round(win_rate, 3),
        "win_rate_predicted":   avg_wr_pred,
        "win_rate_divergence":  round(win_rate - avg_wr_pred, 3),
        "total_pnl_usd":        total_pnl,
        "avg_pnl_usd":          avg_pnl,
        "avg_rr_realised":      avg_rr_real,
        "avg_rr_predicted":     avg_rr_pred,
        "rr_accuracy":          round(abs(avg_rr_real - avg_rr_pred), 3),
        "avg_hold_days":        avg_hold,
        "outcomes":             outcomes,
        "wall_breached_count":  wall_count,
        "target_reached_count": target_count,
        "exit_reasons": {
            "stop_loss":   stop_exits,
            "time_stop":   time_exits,
            "expired":     expired_exits,
            "other":       n - stop_exits - time_exits - expired_exits,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# PRIOR ADJUSTMENT REVIEW
# ─────────────────────────────────────────────────────────────────────────────

def compute_prior_adjustment_review(trades: List[Dict]) -> List[Dict]:
    """
    Compare realised win rate vs predicted win rate per Wyckoff phase × regime bucket.
    Flag buckets where divergence > DIVERGENCE_THRESHOLD and suggest prior adjustments.

    Suggested adjustment = current_prior + (realised_win_rate - predicted_win_rate) × 100 × 0.5
    (half-step update — avoids over-fitting to small samples)

    Requires at least 5 trades per bucket for a valid suggestion.
    """
    if not trades:
        return []

    # Group by phase_bucket × macro_regime
    # These fields are not currently stored in closed_trades — they come from
    # the signal row. A future schema migration will add them. For now we
    # infer phase_bucket from sb_verdict and macro_regime from active_regime.
    # When those fields are present they are used directly.
    buckets: Dict[tuple, List[Dict]] = {}
    for t in trades:
        # Try to get phase_bucket and macro_regime from stored fields
        phase_bucket = (
            str(t.get('wyckoff_phase_bucket') or '').upper() or
            'UNKNOWN'
        )
        macro_regime = (
            str(t.get('macro_regime') or t.get('active_regime') or '').upper() or
            'TRANSITIONAL'
        )
        key = (phase_bucket, macro_regime)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(t)

    review = []
    for (phase_bucket, macro_regime), bucket_trades in sorted(buckets.items()):
        n = len(bucket_trades)
        winners = [t for t in bucket_trades
                   if t.get('outcome_class') in ('TRUE_WINNER', 'PROCESS_WIN')]
        realised_wr = len(winners) / n if n else 0.0

        # Predicted win rate for this bucket
        wr_10d_vals = [_safe_float(t.get('win_rate_10d')) for t in bucket_trades
                       if t.get('win_rate_10d')]
        predicted_wr = sum(wr_10d_vals) / len(wr_10d_vals) if wr_10d_vals else 0.0

        divergence = realised_wr - predicted_wr

        # Current prior adjustment from the hard-coded table
        current_prior = CURRENT_PRIOR_ADJUSTMENTS.get(
            (phase_bucket, macro_regime),
            CURRENT_PRIOR_ADJUSTMENTS.get((phase_bucket, 'TRANSITIONAL'), 0.0)
        )

        # Suggested update — only if we have enough data
        flag       = abs(divergence) > DIVERGENCE_THRESHOLD
        suggestion = None
        if n >= 5 and flag:
            # Half-step: move current prior halfway toward what realised data suggests
            suggested_prior = round(current_prior + divergence * 100 * 0.5, 1)
            # Clamp to bounded range
            suggested_prior = max(-20.0, min(+15.0, suggested_prior))
            suggestion = suggested_prior

        review.append({
            "phase_bucket":           phase_bucket,
            "macro_regime":           macro_regime,
            "n_trades":               n,
            "realised_win_rate":      round(realised_wr,  3),
            "predicted_win_rate":     round(predicted_wr, 3),
            "divergence":             round(divergence,   3),
            "flag_for_review":        flag,
            "current_prior_adj":      current_prior,
            "suggested_prior_adj":    suggestion,
            "sufficient_sample":      n >= 5,
        })

    return sorted(review, key=lambda x: abs(x['divergence']), reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# REPORT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _week_label(dt: date) -> str:
    return f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"


def _week_start(week_label: str) -> date:
    """Return Monday of the given ISO week string e.g. '2026-W18'."""
    try:
        parts = week_label.split("-W")
        year, week = int(parts[0]), int(parts[1])
        jan4 = date(year, 1, 4)
        start = jan4 + timedelta(weeks=week - 1, days=-(jan4.isoweekday() - 1))
        return start
    except Exception:
        return date.today() - timedelta(days=7)


def build_weekly_report(
    db_path: Path,
    week_label: Optional[str] = None,
    full: bool = False,
) -> Dict:
    """
    Build and write the weekly intelligence report.
    Returns report dict.
    """
    if week_label is None:
        week_label = _week_label(date.today())

    log.info(f"Building weekly report: {week_label} (full={full})")

    since_date = None if full else _week_start(week_label).isoformat()
    trades     = _load_closed_trades(db_path, since_date=since_date)

    stats      = compute_weekly_stats(trades)
    prior_rev  = compute_prior_adjustment_review(trades)

    report = {
        "week":                 week_label,
        "generated_at":         datetime.now(timezone.utc).isoformat() + "Z",
        "period_start":         since_date or "all-time",
        "period_end":           date.today().isoformat(),
        "summary":              stats,
        "prior_adjustment_review": prior_rev,
        "flags": {
            "win_rate_divergence_flag": abs(stats.get("win_rate_divergence", 0)) > DIVERGENCE_THRESHOLD,
            "buckets_needing_review":   len([r for r in prior_rev if r["flag_for_review"]]),
            "no_trade_data":            stats.get("n_trades", 0) == 0,
        },
    }

    # Write JSON
    out_json = REPORT_DIR / f"weekly_report_{week_label.replace('-', '_')}.json"
    try:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        log.info(f"Weekly report JSON → {out_json}")
    except Exception as e:
        log.warning(f"Could not write report JSON: {e}")

    # Write human-readable text
    out_txt = REPORT_DIR / f"weekly_report_{week_label.replace('-', '_')}.txt"
    try:
        _write_text_report(out_txt, report, week_label)
        log.info(f"Weekly report TXT  → {out_txt}")
    except Exception as e:
        log.warning(f"Could not write text report: {e}")

    # Write prior adjustment review separately for easy reference
    out_prior = REPORT_DIR / "prior_adjustment_review.json"
    try:
        with open(out_prior, "w", encoding="utf-8") as f:
            json.dump(prior_rev, f, indent=2, default=str)
        log.info(f"Prior adjustment review → {out_prior}")
    except Exception as e:
        log.warning(f"Could not write prior adjustment review: {e}")

    return report


def _write_text_report(path: Path, report: Dict, week_label: str) -> None:
    s    = report.get("summary", {})
    prev = report.get("prior_adjustment_review", [])
    flags = report.get("flags", {})

    lines = [
        f"AVSHUNTER WEEKLY INTELLIGENCE REPORT — {week_label}",
        f"Generated: {report.get('generated_at', '')}",
        f"Period: {report.get('period_start', '')} → {report.get('period_end', '')}",
        "",
        "─" * 60,
        "TRADE SUMMARY",
        "─" * 60,
        f"  Trades closed:       {s.get('n_trades', 0)}",
        f"  Win rate (realised): {s.get('win_rate', 0):.1%}",
        f"  Win rate (predicted):{s.get('win_rate_predicted', 0):.1%}",
        f"  Win rate divergence: {s.get('win_rate_divergence', 0):+.1%}",
        f"  Total P&L:           ${s.get('total_pnl_usd', 0):,.2f}",
        f"  Avg P&L per trade:   ${s.get('avg_pnl_usd', 0):,.2f}",
        f"  Avg realised R:R:    {s.get('avg_rr_realised', 0):.2f}",
        f"  Avg predicted R:R:   {s.get('avg_rr_predicted', 0):.2f}",
        f"  Avg hold (days):     {s.get('avg_hold_days', 0):.1f}",
        "",
        "OUTCOME BREAKDOWN",
    ]
    for cls, cnt in (s.get("outcomes") or {}).items():
        lines.append(f"  {cls:<20} {cnt}")

    exit_r = s.get("exit_reasons") or {}
    lines += [
        "",
        "EXIT REASONS",
        f"  Stop loss:   {exit_r.get('stop_loss', 0)}",
        f"  Time stop:   {exit_r.get('time_stop', 0)}",
        f"  Expired:     {exit_r.get('expired', 0)}",
        f"  Other:       {exit_r.get('other', 0)}",
        "",
        "─" * 60,
        "PRIOR ADJUSTMENT REVIEW",
        "─" * 60,
    ]

    if not prev:
        lines.append("  No closed trade data — prior adjustments unchanged.")
    else:
        for r in prev:
            flag_str = "  *** REVIEW ***" if r.get("flag_for_review") else ""
            sug      = r.get("suggested_prior_adj")
            sug_str  = f"  → suggest {sug:+.1f}" if sug is not None else "  → insufficient data"
            lines.append(
                f"  {r['phase_bucket']:<14} × {r['macro_regime']:<14} "
                f"n={r['n_trades']:>3}  "
                f"realised={r['realised_win_rate']:.1%}  "
                f"predicted={r['predicted_win_rate']:.1%}  "
                f"div={r['divergence']:+.1%}  "
                f"current_prior={r['current_prior_adj']:+.1f}{sug_str}{flag_str}"
            )

    lines += [
        "",
        "─" * 60,
        "FLAGS",
        "─" * 60,
        f"  Win rate divergence flag:    {flags.get('win_rate_divergence_flag', False)}",
        f"  Buckets needing review:      {flags.get('buckets_needing_review', 0)}",
        f"  No trade data:               {flags.get('no_trade_data', False)}",
        "",
        "─" * 60,
        "ACTION ITEMS",
        "─" * 60,
    ]

    actions = []
    if flags.get("no_trade_data"):
        actions.append("  - No trades closed this period. Verify outcome_capture.py is running.")
    if flags.get("win_rate_divergence_flag"):
        actions.append(
            f"  - Overall win rate divergence {s.get('win_rate_divergence', 0):+.1%} "
            f"exceeds {DIVERGENCE_THRESHOLD:.0%} threshold. Review signal quality."
        )
    for r in prev:
        if r.get("flag_for_review") and r.get("suggested_prior_adj") is not None:
            bucket = f"{r['phase_bucket']} × {r['macro_regime']}"
            actions.append(
                f"  - Update STATE_PRIOR_ADJUSTMENTS[({r['phase_bucket']!r}, "
                f"{r['macro_regime']!r})] from {r['current_prior_adj']:+.1f} "
                f"to {r['suggested_prior_adj']:+.1f} "
                f"(based on {r['n_trades']} trades, divergence {r['divergence']:+.1%})"
            )

    if not actions:
        lines.append("  No action items — model performing within tolerance.")
    else:
        lines.extend(actions)

    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR CALLABLE
# ─────────────────────────────────────────────────────────────────────────────

def run_weekly_report(week_label: Optional[str] = None, full: bool = False) -> dict:
    """
    Called by intelligent_orchestrator.py on Sunday after market close.
    Returns status dict with flag counts for health check.
    """
    report = build_weekly_report(JOURNAL_DB, week_label=week_label, full=full)
    flags  = report.get("flags", {})
    return {
        "success":               True,
        "week":                  report.get("week"),
        "n_trades":              report.get("summary", {}).get("n_trades", 0),
        "win_rate":              report.get("summary", {}).get("win_rate", 0),
        "buckets_to_review":     flags.get("buckets_needing_review", 0),
        "win_rate_divergence":   report.get("summary", {}).get("win_rate_divergence", 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AVSHUNTER Weekly Intelligence Report")
    ap.add_argument("--week", default="",
                    help="ISO week e.g. 2026-W18 (default: current week)")
    ap.add_argument("--full", action="store_true",
                    help="Include all closed trades, not just current week")
    ap.add_argument("--db",   default="",
                    help="Path to trade_journal.db")
    args = ap.parse_args()

    db_path    = Path(args.db) if args.db else JOURNAL_DB
    week_label = args.week or None

    report = build_weekly_report(db_path, week_label=week_label, full=args.full)
    flags  = report.get("flags", {})
    log.info(
        f"Report complete: {report.get('week')} | "
        f"trades={report.get('summary', {}).get('n_trades', 0)} | "
        f"win_rate={report.get('summary', {}).get('win_rate', 0):.1%} | "
        f"buckets_to_review={flags.get('buckets_needing_review', 0)}"
    )
    sys.exit(0)
