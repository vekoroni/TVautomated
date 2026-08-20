#!/usr/bin/env python3
"""AVSHUNTER Desk Card — read-only pre-execution decision aid.

Reads the macro JSONs and the morning-gate run outputs and prints a
one-screen desk card plus per-candidate stop viability checks.

This script is READ-ONLY intelligence. It does not generate signals, does
not authorise entry, and does not modify any pipeline file. It writes at
most one CSV of its own into an existing run's morning_validation folder.
"""
import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
RUN_ID_RE = re.compile(r"^\d{8}_\d{6}$")

MACRO_FILE = "macro_intelligence_latest.json"
BOND_FILE = "bond_macro_state.json"
ENRICHMENT_FILE = "avshunter_macro_enrichment_delta.json"

CANDIDATES_PREFIX = "morning_candidates_"
VALIDATED_PREFIX = "morning_validated_trades_"

# ---------------------------------------------------------------------------
# Stop viability math (driftless barrier, reflection principle)
# ---------------------------------------------------------------------------


def normalize_iv(value):
    """IV may arrive as a decimal (0.42) or a percentage (42). Normalise to
    percentage points. Values below 3.0 are treated as decimals."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(v):
        return None
    if abs(v) < 3.0:
        v *= 100.0
    return v


def phi(x):
    """Standard normal CDF, no scipy dependency."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def p_touch_from_ratio(x):
    """P(barrier touched) given x = stop_pct / sd_move_pct."""
    return 2.0 * (1.0 - phi(x))


def stop_viability(iv, days, stop_pct):
    """Compute sd_move_pct, coinflip_pct, p_touch, verdict.

    iv: decimal (0.42) or percentage (42) implied vol
    days: horizon in calendar days
    stop_pct: stop distance as a percentage of price (e.g. 4.0 for 4%)

    Returns a dict; verdict is DATA_UNAVAILABLE if any input is missing or
    non-positive.
    """
    iv_pct = normalize_iv(iv)
    try:
        d = float(days)
        s = float(stop_pct)
    except (TypeError, ValueError):
        d = None
        s = None

    if iv_pct is None or d is None or s is None or iv_pct <= 0 or d <= 0:
        return {
            "sd_move_pct": None,
            "coinflip_pct": None,
            "p_touch": None,
            "verdict": "DATA_UNAVAILABLE",
        }

    sd_move_pct = iv_pct * math.sqrt(d / 252.0)
    coinflip_pct = 0.674 * sd_move_pct

    if sd_move_pct == 0:
        return {
            "sd_move_pct": 0.0,
            "coinflip_pct": 0.0,
            "p_touch": None,
            "verdict": "DATA_UNAVAILABLE",
        }

    x = abs(s) / sd_move_pct
    p_touch = p_touch_from_ratio(x)

    if p_touch >= 0.50:
        verdict = "INSIDE_NOISE"
    elif p_touch >= 0.35:
        verdict = "MARGINAL"
    else:
        verdict = "OK"

    return {
        "sd_move_pct": sd_move_pct,
        "coinflip_pct": coinflip_pct,
        "p_touch": p_touch,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Macro JSON loading — every file optional, corruption never crashes
# ---------------------------------------------------------------------------


def load_json_safe(path):
    """Returns (data_or_None, status_string)."""
    if not path.exists():
        return None, "ABSENT"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), "OK"
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return None, f"CORRUPT: {exc}"


def parse_iso_date(value):
    if not value:
        return None
    try:
        v = value.replace("Z", "+00:00")
        return datetime.fromisoformat(v)
    except (ValueError, TypeError):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None


def load_macro_context(macro_dir):
    """Loads the three macro JSONs. Returns a context dict. Never raises."""
    ctx = {
        "macro": None,
        "bond": None,
        "enrichment": None,
        "warnings": [],
        "degraded": False,
        "corrupt": False,
    }

    macro, status = load_json_safe(macro_dir / MACRO_FILE)
    if status == "ABSENT":
        ctx["warnings"].append(f"{MACRO_FILE} ABSENT — no regime, sector or size context")
        ctx["degraded"] = True
    elif status.startswith("CORRUPT"):
        ctx["warnings"].append(f"{MACRO_FILE} {status}")
        ctx["degraded"] = True
        ctx["corrupt"] = True
    else:
        ctx["macro"] = macro

    bond, status = load_json_safe(macro_dir / BOND_FILE)
    if status == "ABSENT":
        ctx["warnings"].append(f"{BOND_FILE} ABSENT — no auction, curve or credit context")
        ctx["degraded"] = True
    elif status.startswith("CORRUPT"):
        ctx["warnings"].append(f"{BOND_FILE} {status}")
        ctx["degraded"] = True
        ctx["corrupt"] = True
    else:
        ctx["bond"] = bond

    enrichment, status = load_json_safe(macro_dir / ENRICHMENT_FILE)
    if status == "ABSENT":
        ctx["warnings"].append(f"{ENRICHMENT_FILE} ABSENT — no news-terminal context")
        ctx["degraded"] = True
    elif status.startswith("CORRUPT"):
        ctx["warnings"].append(f"{ENRICHMENT_FILE} {status}")
        ctx["degraded"] = True
        ctx["corrupt"] = True
    else:
        ctx["enrichment"] = enrichment

    # Staleness: report_date / as_of_utc more than 2 calendar days old
    now = datetime.now(timezone.utc)
    for label, doc, field in (
        ("macro", ctx["macro"], "report_date"),
        ("bond", ctx["bond"], "as_of_date"),
        ("enrichment", ctx["enrichment"], "report_date"),
    ):
        if not doc:
            continue
        dt = parse_iso_date(doc.get(field))
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = (now - dt).days
        if age_days > 2:
            ctx["warnings"].append(f"STALE INPUT: {label}.{field} is {age_days}d old ({doc.get(field)})")

    return ctx


# ---------------------------------------------------------------------------
# Run discovery
# ---------------------------------------------------------------------------


def find_latest_run_id(runs_dir):
    if not runs_dir.exists():
        return None
    candidates = [p.name for p in runs_dir.iterdir() if p.is_dir() and RUN_ID_RE.match(p.name)]
    if not candidates:
        return None
    return sorted(candidates)[-1]


def run_id_date(run_id):
    """YYYYMMDD_HHMMSS -> datetime.date, or None."""
    try:
        return datetime.strptime(run_id[:8], "%Y%m%d").date()
    except ValueError:
        return None


def morning_validation_dir(runs_dir, run_id):
    return runs_dir / run_id / "morning_validation"


def find_candidates_csv(mv_dir, run_id):
    p = mv_dir / f"{CANDIDATES_PREFIX}{run_id}.csv"
    return p if p.exists() else None


def find_validated_csv(mv_dir, run_id):
    p = mv_dir / f"{VALIDATED_PREFIX}{run_id}.csv"
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Row-level helpers
# ---------------------------------------------------------------------------


def get_ticker_col(df):
    if "ticker" in df.columns:
        return "ticker"
    if "Ticker" in df.columns:
        return "Ticker"
    return None


def safe_get(row, col, default=None):
    if col not in row.index:
        return default
    v = row[col]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    return v


def sector_flag(row, macro):
    """LEAD / AVOID / NEUTRAL. Never blocks — a handicap, not a gate."""
    if not macro:
        return "NEUTRAL"
    lead = set(macro.get("sector_lead") or [])
    avoid = set(macro.get("sector_avoid") or [])
    if not lead and not avoid:
        return "NEUTRAL"

    checks = []
    etf = safe_get(row, "sector_etf")
    if etf:
        checks.append(str(etf).upper())
    tkr_col = "ticker" if "ticker" in row.index else ("Ticker" if "Ticker" in row.index else None)
    if tkr_col:
        tkr = safe_get(row, tkr_col)
        if tkr:
            checks.append(str(tkr).upper())

    for c in checks:
        if c in lead:
            return "LEAD"
    for c in checks:
        if c in avoid:
            return "AVOID"
    return "NEUTRAL"


def horizon_bucket_for_dte(dte):
    if dte is None:
        return None
    try:
        d = float(dte)
    except (TypeError, ValueError):
        return None
    if pd.isna(d):
        return None
    if d <= 5:
        return "1_5d"
    if d <= 10:
        return "6_10d"
    if d <= 20:
        return "11_20d"
    return None  # outside the routing table — surfaced, not guessed


def horizon_info(macro, dte):
    bucket = horizon_bucket_for_dte(dte)
    if bucket is None:
        return bucket, None
    if not macro:
        return bucket, None
    hr = macro.get("horizon_routing") or {}
    return bucket, hr.get(bucket)


def size_ambiguity_lines(macro, bucket=None):
    """Returns (replace, compound, warning_line_or_None)."""
    if not macro:
        return None, None, None
    top = macro.get("size_multiplier")
    if top is None:
        return None, None, None
    replace = top
    compound = None
    if bucket:
        hr = (macro.get("horizon_routing") or {}).get(bucket) or {}
        bucket_mult = hr.get("size_multiplier")
        if bucket_mult is not None:
            compound = top * bucket_mult
    else:
        # Mode A generic header — no specific candidate/horizon. Demo the
        # nearest-term bucket (1-5d) as the representative compound figure;
        # this is a display choice for the generic card, not a resolution
        # of the ambiguity (both figures are always shown).
        hr = (macro.get("horizon_routing") or {}).get("1_5d") or {}
        bucket_mult = hr.get("size_multiplier")
        if bucket_mult is not None:
            compound = top * bucket_mult

    warning = None
    if compound is not None and replace and compound != 0:
        ratio = max(replace, compound) / min(replace, compound) if min(replace, compound) else None
        if abs(replace - compound) > 1e-9:
            ratio_txt = f"{ratio:.2f}x" if ratio else "?"
            warning = f"⚠ SIZE_AMBIGUITY UNRESOLVED — differs by {ratio_txt}. Confirm against the writing code."
    return replace, compound, warning


def contract_iv_and_basis(row):
    """Returns (iv, price, basis) using live_contract_iv/live_price when
    present and > 0, else contract_iv/signal_price (EOD)."""
    live_iv = safe_get(row, "live_contract_iv")
    live_price = safe_get(row, "live_price")
    if live_iv is not None and live_price is not None:
        try:
            if float(live_iv) > 0:
                return float(live_iv), float(live_price), "LIVE"
        except (TypeError, ValueError):
            pass
    eod_iv = safe_get(row, "contract_iv")
    eod_price = safe_get(row, "signal_price")
    try:
        eod_iv = float(eod_iv) if eod_iv is not None else None
    except (TypeError, ValueError):
        eod_iv = None
    try:
        eod_price = float(eod_price) if eod_price is not None else None
    except (TypeError, ValueError):
        eod_price = None
    return eod_iv, eod_price, "EOD"


def row_stop_pct(row, price):
    stop_level = safe_get(row, "exit_stop_price")
    if stop_level is None or price is None:
        return None
    try:
        stop_level = float(stop_level)
        price = float(price)
    except (TypeError, ValueError):
        return None
    if price == 0:
        return None
    return abs(price - stop_level) / price * 100.0


def breakeven_flag(row, bond_ctx, price):
    """Flags rows whose expected move is within the breakeven_adjustment_pct
    cushion of their own breakeven_feasibility figure. Returns None if data
    insufficient to judge."""
    be_feas = safe_get(row, "breakeven_feasibility")
    target = safe_get(row, "target_price")
    if be_feas is None or target is None or price is None:
        return None
    try:
        be_feas = float(be_feas)
        target = float(target)
        price = float(price)
    except (TypeError, ValueError):
        return None
    if price == 0:
        return None
    expected_move_pct = abs(target - price) / price * 100.0
    adj_pct = 0.0
    if bond_ctx:
        adj_pct = (bond_ctx.get("auction") or {}).get("breakeven_adjustment_pct") or 0.0
    cushion = be_feas * (1.0 + adj_pct / 100.0)
    return expected_move_pct <= cushion


# ---------------------------------------------------------------------------
# Mode A — desk card (no arguments)
# ---------------------------------------------------------------------------


def print_authority_banner_top(lines):
    width = 64
    print("+" + "=" * width + "+")
    for line in lines:
        print(f"| {line:<{width - 2}}|")
    print("+" + "=" * width + "+")


def print_desk_card(ctx, degraded_exit_needed):
    macro = ctx["macro"]
    bond = ctx["bond"]
    enrichment = ctx["enrichment"]

    if macro is None:
        print_authority_banner_top(
            [
                "MACRO CONTEXT UNAVAILABLE",
                "No sector permission, size multiplier or breakeven adj.",
                "Stop viability analysis only.",
            ]
        )
        for w in ctx["warnings"]:
            print(f"  - {w}")
        return

    print(f"=== AVSHUNTER DESK CARD — {macro.get('report_date', '?')} ===")
    print(f"Regime: {macro.get('regime_state', 'UNKNOWN')}  "
          f"| VIX spot: {macro.get('vix_spot', 'n/a')}  "
          f"| Vol mode: {macro.get('vol_mode', 'n/a')}  "
          f"| Macro filter: {macro.get('macro_filter', 'n/a')}")
    print(f"Trigger required: {macro.get('trigger_required', 'n/a')}  "
          f"| GEX regime score: {macro.get('gex_regime_score', 'n/a')}  "
          f"| Regime probability: {macro.get('regime_probability', 'n/a')}")
    print()

    lead = macro.get("sector_lead") or []
    avoid = macro.get("sector_avoid") or []
    print(f"Sector LEAD : {', '.join(lead) if lead else 'none'}")
    print(f"Sector AVOID: {', '.join(avoid) if avoid else 'none'}")
    print()

    replace, compound, warn = size_ambiguity_lines(macro)
    if replace is not None:
        print(f"Size (replace) : {replace:.2f}x")
        if compound is not None:
            print(f"Size (compound, 1-5d bucket demo): {compound:.2f}x")
        if warn:
            print(warn)
        print()

    if bond:
        auction = bond.get("auction") or {}
        if auction.get("auction_today"):
            print(f"AUCTION TODAY: {', '.join(auction.get('tenors_today') or [])}  "
                  f"| breakeven adj: +{auction.get('breakeven_adjustment_pct', 0)}%  "
                  f"| {auction.get('note', '')}")
        curve = bond.get("yield_curve") or {}
        if curve:
            print(f"Curve: {curve.get('curve_state', 'n/a')} ({curve.get('spread_bps', 'n/a')}bps) "
                  f"— {curve.get('regime_implication', '')}")
        composite = bond.get("composite") or {}
        if composite:
            print(f"Bond composite: score {composite.get('macro_bond_score', 'n/a')}/100  "
                  f"| trade_go={composite.get('trade_go', 'n/a')}  "
                  f"| {composite.get('primary_warning', '')}")
        credit = bond.get("credit_stress") or {}
        if credit:
            print(f"Credit stress: {credit.get('stress_level', 'n/a')}  "
                  f"(z={credit.get('ratio_zscore_20d', 'n/a')})  "
                  f"warning={credit.get('credit_warning', 'n/a')}")
        print()
    else:
        print("Bond/credit context UNAVAILABLE")
        print()

    hr = macro.get("horizon_routing") or {}
    if hr:
        print("Horizon routing:")
        for bucket in ("1_5d", "6_10d", "11_20d"):
            b = hr.get(bucket)
            if not b:
                continue
            print(f"  {bucket:>6s}: bias={b.get('bias', 'n/a'):<15s} "
                  f"size={b.get('size_multiplier', 'n/a')}  action={b.get('action', 'n/a')}")
            for bc in (b.get("block_conditions") or [])[:1]:
                suffix = " [LEVELS UNVERIFIED]" if "wall" in bc.lower() or "flip" in bc.lower() or "gex" in bc.lower() else ""
                print(f"          - {bc}{suffix}")
        print()

    if enrichment:
        sf = enrichment.get("source_freshness") or {}
        print(f"News-terminal context: {sf.get('status', 'n/a')} (NONE_NEWS_TERMINAL_ONLY — display only, never acted on)")
        print()

    if ctx["warnings"]:
        print("Data-freshness / input warnings:")
        for w in ctx["warnings"]:
            print(f"  - {w}")


# ---------------------------------------------------------------------------
# Mode B — single candidate
# ---------------------------------------------------------------------------


def run_single_candidate(args, ctx):
    result = stop_viability(args.iv, args.days, args.stop)
    ticker_label = f" [{args.ticker}]" if args.ticker else ""
    print(f"--- Stop check{ticker_label} ---")
    print(f"IV: {normalize_iv(args.iv)}%  DTE: {args.days}  Stop: {args.stop}%")
    if result["verdict"] == "DATA_UNAVAILABLE":
        print("Verdict: DATA_UNAVAILABLE — insufficient inputs")
        return 2
    print(f"1SD move: {result['sd_move_pct']:.2f}%  "
          f"Coin-flip (0.674 SD): {result['coinflip_pct']:.2f}%  "
          f"P(touch): {result['p_touch'] * 100:.1f}%")
    print(f"Verdict: {result['verdict']}")
    print("(Assumes zero drift and normal tails — real touch probability runs slightly higher. Floor estimate.)")

    if args.ticker and ctx["macro"]:
        bucket, hinfo = horizon_info(ctx["macro"], args.days)
        if bucket:
            print(f"Horizon bucket: {bucket}" + (f"  action={hinfo.get('action')}" if hinfo else "  (no routing entry)"))
        lead = set(ctx["macro"].get("sector_lead") or [])
        avoid = set(ctx["macro"].get("sector_avoid") or [])
        t = args.ticker.upper()
        flag = "LEAD" if t in lead else ("AVOID" if t in avoid else "NEUTRAL")
        print(f"Sector flag: {flag}")
    return 0


# ---------------------------------------------------------------------------
# Mode C — batch
# ---------------------------------------------------------------------------


def build_row_record(row, macro, bond, basis_mode):
    """basis_mode: 'eod' (candidates) or 'auto' (validated, live/eod branch)."""
    tkr_col = "ticker" if "ticker" in row.index else "Ticker"
    ticker = safe_get(row, tkr_col, "?")

    if basis_mode == "eod":
        iv = safe_get(row, "contract_iv")
        price = safe_get(row, "signal_price")
        basis = "EOD"
    else:
        iv, price, basis = contract_iv_and_basis(row)

    dte = safe_get(row, "dte")
    stop_pct = row_stop_pct(row, price)
    result = stop_viability(iv, dte, stop_pct)
    bucket, hinfo = horizon_info(macro, dte)
    sflag = sector_flag(row, macro)
    be_flag = breakeven_flag(row, bond, price)

    return {
        "ticker": ticker,
        "sector_flag": sflag,
        "dte": dte,
        "dte_bucket": bucket or "NO_BUCKET",
        "basis": basis,
        "iv_pct": normalize_iv(iv),
        "sd_move_pct": result["sd_move_pct"],
        "coinflip_pct": result["coinflip_pct"],
        "stop_pct": stop_pct,
        "p_touch": result["p_touch"],
        "verdict": result["verdict"],
        "breakeven_flag": be_flag,
    }


def fmt_pct(v):
    return f"{v:.2f}%" if v is not None else "n/a"


def print_row(record, prefix=""):
    p_touch_txt = f"{record['p_touch'] * 100:.1f}%" if record["p_touch"] is not None else "n/a"
    be_txt = " [BREAKEVEN_RISK]" if record["breakeven_flag"] else ""
    print(f"{prefix}{record['ticker']:<8s} {record['sector_flag']:<7s} "
          f"DTE={record['dte_bucket']:<8s} {record['basis']:<4s} "
          f"IV={fmt_pct(record['iv_pct']):<8s} 1SD={fmt_pct(record['sd_move_pct']):<8s} "
          f"coin={fmt_pct(record['coinflip_pct']):<8s} stop={fmt_pct(record['stop_pct']):<8s} "
          f"P(touch)={p_touch_txt:<7s} {record['verdict']}{be_txt}")


def section_summary(records, label):
    ok = sum(1 for r in records if r["verdict"] == "OK")
    marg = sum(1 for r in records if r["verdict"] == "MARGINAL")
    inside = sum(1 for r in records if r["verdict"] == "INSIDE_NOISE")
    unavail = sum(1 for r in records if r["verdict"] == "DATA_UNAVAILABLE")
    line = f"{label} stop viability: {ok} OK, {marg} MARGINAL, {inside} INSIDE_NOISE"
    if unavail:
        line += f", {unavail} DATA_UNAVAILABLE (IV or price missing/zero — skipped)"
    print(line)


def run_candidates_mode(args, ctx, run_id, mv_dir, csv_path):
    df = pd.read_csv(csv_path, low_memory=False)
    tkr_col = get_ticker_col(df)
    if tkr_col is None:
        print("ERROR: candidates CSV has neither 'ticker' nor 'Ticker' column.")
        return 1

    records = [build_row_record(row, ctx["macro"], ctx["bond"], "eod") for _, row in df.iterrows()]

    banner = [
        f"SOURCE: {csv_path.name}   (EOD PREP)",
        "PRE-TRADE INTELLIGENCE ONLY - NOT ENTRY AUTHORISATION",
        "The morning gate has not run. No row here is authorised.",
        "Prices are EOD closes; stop distances will shift by open.",
    ]
    print_authority_banner_top(banner)

    stop_note_needed = _exit_stop_matches_invalidation(df)
    if stop_note_needed is not None:
        print(f"NOTE: exit_stop_price == invalidation_eod in {stop_note_needed[0]}/{stop_note_needed[1]} rows "
              "— stop is not independently computed from the invalidation level.")

    for rec in records:
        print_row(rec, prefix="[PREP] ")

    section_summary(records, "PREP")
    print("Stop verdicts are provisional. Re-run with --source validated after the gate.")

    validated_csv = find_validated_csv(mv_dir, run_id)
    if validated_csv:
        _print_verdict_drift(records, validated_csv, tkr_col)

    print_authority_banner_top(banner)

    if args.csv:
        out = mv_dir / f"desk_card_PREP_{run_id}.csv"
        pd.DataFrame(records).to_csv(out, index=False)
        print(f"Written: {out}")

    return 0


def run_validated_mode(args, ctx, run_id, mv_dir, csv_path):
    df = pd.read_csv(csv_path, low_memory=False)
    if "morning_gate_verdict" not in df.columns:
        print("ERROR: validated CSV missing 'morning_gate_verdict' column.")
        return 1
    tkr_col = get_ticker_col(df)
    if tkr_col is None:
        print("ERROR: validated CSV has neither 'ticker' nor 'Ticker' column.")
        return 1

    counts = df["morning_gate_verdict"].value_counts(dropna=False)
    go_n = int(counts.get("GO", 0))
    flag_n = int(counts.get("FLAG", 0))
    block_n = int(counts.get("BLOCK", 0))

    live_n = 0
    eod_n = 0

    go_df = df[df["morning_gate_verdict"] == "GO"]
    flag_df = df[df["morning_gate_verdict"] == "FLAG"]

    go_records = []
    for _, row in go_df.iterrows():
        rec = build_row_record(row, ctx["macro"], ctx["bond"], "auto")
        go_records.append(rec)
        live_n += rec["basis"] == "LIVE"
        eod_n += rec["basis"] == "EOD"

    flag_records = []
    for _, row in flag_df.iterrows():
        rec = build_row_record(row, ctx["macro"], ctx["bond"], "auto")
        flag_records.append(rec)
        live_n += rec["basis"] == "LIVE"
        eod_n += rec["basis"] == "EOD"

    banner = [
        f"SOURCE: {csv_path.name}",
        f"GO {go_n} | FLAG {flag_n} (validation required) | BLOCK {block_n}",
        f"Price basis: {live_n} LIVE, {eod_n} EOD",
    ]
    print_authority_banner_top(banner)

    stop_note_needed = _exit_stop_matches_invalidation(df)
    if stop_note_needed is not None:
        print(f"NOTE: exit_stop_price == invalidation_eod in {stop_note_needed[0]}/{stop_note_needed[1]} rows "
              "— stop is not independently computed from the invalidation level.")

    print()
    print("=== GO ===")
    for rec in go_records:
        print_row(rec)
    section_summary(go_records, "GO  ")

    inside_go = sum(1 for r in go_records if r["verdict"] == "INSIDE_NOISE")
    evaluable_go = sum(1 for r in go_records if r["verdict"] != "DATA_UNAVAILABLE")
    if evaluable_go and inside_go / evaluable_go > 0.30:
        pct = inside_go / evaluable_go * 100
        print(f"⚠ SYSTEMIC: {pct:.0f}% of evaluable GO rows are INSIDE_NOISE — check upstream stop-sizing logic.")

    print()
    print("=== FLAG - YOUR VALIDATION REQUIRED ===")

    flag_sorted = sorted(flag_records, key=lambda r: (
        0 if r["sector_flag"] == "LEAD" else 1,
        r["p_touch"] if r["p_touch"] is not None else 2.0,
    ))

    top_n = args.top
    shown = flag_sorted[:top_n]
    for rec in shown:
        print_row(rec, prefix="[FLAG] ")
    if len(flag_sorted) > top_n:
        print(f"[FLAG] ... {len(flag_sorted) - top_n} more rows not shown (--top {top_n})")
    section_summary(flag_records, "FLAG")

    candidates_csv = find_candidates_csv(mv_dir, run_id)
    if candidates_csv:
        all_records = go_records + flag_records
        _print_verdict_drift(all_records, candidates_csv, tkr_col, prep_is_current=False)

    print()
    print_authority_banner_top(banner)

    if args.csv:
        out = mv_dir / f"desk_card_{run_id}.csv"
        combined = pd.DataFrame(
            [dict(r, section="GO") for r in go_records] + [dict(r, section="FLAG") for r in flag_records]
        )
        combined.to_csv(out, index=False)
        print(f"Written: {out}")

    return 0


def _exit_stop_matches_invalidation(df):
    if "exit_stop_price" not in df.columns or "invalidation_eod" not in df.columns:
        return None
    both = df.dropna(subset=["exit_stop_price", "invalidation_eod"])
    if len(both) == 0:
        return None
    matches = int((both["exit_stop_price"] == both["invalidation_eod"]).sum())
    return matches, len(both)


def _print_verdict_drift(current_records, counterpart_csv, tkr_col, prep_is_current=True):
    """Compares current in-memory records against a previously-written
    desk_card CSV for the counterpart mode, if one exists in the same
    morning_validation folder."""
    mv_dir = counterpart_csv.parent
    run_id_match = re.search(r"(\d{8}_\d{6})", counterpart_csv.name)
    if not run_id_match:
        return
    run_id = run_id_match.group(1)

    prep_out = mv_dir / f"desk_card_PREP_{run_id}.csv"
    val_out = mv_dir / f"desk_card_{run_id}.csv"

    if prep_is_current:
        counterpart_out = val_out
    else:
        counterpart_out = prep_out

    if not counterpart_out.exists():
        return

    try:
        other = pd.read_csv(counterpart_out)
    except (OSError, pd.errors.ParserError):
        return
    if "ticker" not in other.columns or "verdict" not in other.columns:
        return

    other_map = dict(zip(other["ticker"], other["verdict"]))
    real_verdicts = {"OK", "MARGINAL", "INSIDE_NOISE"}
    drift_lines = []
    newly_evaluable = 0
    for rec in current_records:
        prev = other_map.get(rec["ticker"])
        if not prev or prev == rec["verdict"]:
            continue
        if prev in real_verdicts and rec["verdict"] in real_verdicts:
            drift_lines.append(f"{rec['ticker']} {prev} -> {rec['verdict']}")
        else:
            # one side was DATA_UNAVAILABLE — data became (un)available, not a
            # genuine stop-viability change. Counted, not enumerated.
            newly_evaluable += 1

    if drift_lines:
        shown = drift_lines[:25]
        print("VERDICT DRIFT since prep:  " + "   ".join(shown))
        if len(drift_lines) > 25:
            print(f"  ... {len(drift_lines) - 25} more verdict changes not shown")
    if newly_evaluable:
        print(f"({newly_evaluable} rows became newly evaluable/unevaluable — IV data availability changed, not a stop-viability drift)")


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def run_selftest():
    failures = []

    ref = [(0.50, 0.617), (0.674, 0.500), (1.00, 0.317), (1.50, 0.134), (2.00, 0.046)]
    for x, expected in ref:
        got = p_touch_from_ratio(x)
        if abs(got - expected) > 0.001:
            failures.append(f"p_touch_from_ratio({x}) = {got:.4f}, expected {expected}")

    a = stop_viability(0.42, 10, 4.0)
    b = stop_viability(42, 10, 4.0)
    if a["verdict"] != b["verdict"] or abs((a["p_touch"] or 0) - (b["p_touch"] or 0)) > 1e-9:
        failures.append(f"IV decimal/pct mismatch: {a} vs {b}")

    if normalize_iv(0.42) != 42.0 or normalize_iv(42) != 42.0:
        failures.append("normalize_iv decimal/pct detection failed")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST PASSED")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_arg_parser():
    p = argparse.ArgumentParser(description="AVSHUNTER Desk Card — read-only pre-execution decision aid.")
    p.add_argument("--macro-dir", default=None)
    p.add_argument("--runs-dir", default=None)
    p.add_argument("--iv", type=float)
    p.add_argument("--days", type=float)
    p.add_argument("--stop", type=float)
    p.add_argument("--ticker")
    p.add_argument("--batch", action="store_true")
    p.add_argument("--source", choices=["candidates", "validated"])
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--csv", action="store_true")
    p.add_argument("--selftest", action="store_true")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    if args.selftest:
        return run_selftest()

    macro_dir = Path(args.macro_dir) if args.macro_dir else SCRIPT_DIR / "dropbox" / "macro"
    runs_dir = Path(args.runs_dir) if args.runs_dir else SCRIPT_DIR / "data" / "output" / "runs"

    ctx = load_macro_context(macro_dir)

    single_mode_args = [args.iv, args.days, args.stop]
    if any(v is not None for v in single_mode_args):
        if not all(v is not None for v in single_mode_args):
            print("ERROR: --iv, --days and --stop must all be supplied together.")
            return 1
        rc = run_single_candidate(args, ctx)
        return rc if rc else (2 if ctx["degraded"] else 0)

    if not args.batch:
        print_desk_card(ctx, ctx["degraded"])
        return 2 if ctx["degraded"] else 0

    run_id = find_latest_run_id(runs_dir)
    if run_id is None:
        print(f"ERROR: no run directories found under {runs_dir}")
        return 1
    mv_dir = morning_validation_dir(runs_dir, run_id)

    candidates_csv = find_candidates_csv(mv_dir, run_id)
    validated_csv = find_validated_csv(mv_dir, run_id)

    source = args.source
    if source is None:
        if validated_csv is not None and run_id_date(run_id) == datetime.now().date():
            source = "validated"
            print(f"Auto-detected source: validated (validated CSV exists for today's run {run_id})")
        elif candidates_csv is not None:
            source = "candidates"
            print(f"Auto-detected source: candidates (no same-day validated CSV; run {run_id})")
        elif validated_csv is not None:
            source = "validated"
            print(f"Auto-detected source: validated (only source available; run {run_id} is not today's date)")
        else:
            print(f"ERROR: neither candidates nor validated CSV found for run {run_id} in {mv_dir}")
            return 1

    # Macro/bond report_date vs RUN_ID date staleness check
    rid_date = run_id_date(run_id)
    if ctx["macro"] and rid_date:
        m_date = parse_iso_date(ctx["macro"].get("report_date"))
        if m_date:
            m_date_only = m_date.date() if isinstance(m_date, datetime) else m_date
            if abs((m_date_only - rid_date).days) > 1:
                print(f"STALE INPUT: macro report_date {ctx['macro'].get('report_date')} "
                      f"vs run {run_id} date {rid_date} — more than 1 day apart.")

    if source == "candidates":
        if candidates_csv is None:
            print(f"ERROR: no {CANDIDATES_PREFIX}{run_id}.csv found in {mv_dir}")
            return 1
        rc = run_candidates_mode(args, ctx, run_id, mv_dir, candidates_csv)
    else:
        if validated_csv is None:
            print(f"ERROR: no {VALIDATED_PREFIX}{run_id}.csv found in {mv_dir}")
            return 1
        rc = run_validated_mode(args, ctx, run_id, mv_dir, validated_csv)

    if rc != 0:
        return rc
    return 2 if ctx["degraded"] else 0


if __name__ == "__main__":
    sys.exit(main())
