from __future__ import annotations

"""
AVSHUNTER · TRADE BOOK BUILDER v2.0
===================================

Purpose
-------
Convert enhanced_{run_id}.csv into a committed trade list, but with the updated
AVSHUNTER state model that separates:

1. Campaign readiness   -> structural / delayed-stock confirmation
2. Execution readiness  -> live options execution permission

Why this version exists
-----------------------
The prior trade book builder assumed older fields such as:
- pse_execution_mode
- kelly_verdict
- conv_trade_gate

Those fields remain useful, but they are no longer sufficient on their own.
Under the current operating model:
- delayed stock data validates the campaign,
- live options data controls the purchase.

Therefore this builder now prioritises these fields when present:
- campaign_verdict
- execution_verdict
- trigger_source
- stock_data_source
- options_data_source
- trigger_confidence_mode
- execution_confidence_mode
- live_execution_required

Backward compatibility
----------------------
If the new fields are absent, the builder falls back to the legacy fields.
That means this file can still run on partially migrated pipeline outputs.
"""

import csv
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("avshunter.trade_book_builder")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [TBB_v2] %(message)s", datefmt="%H:%M:%S")


# =============================================================================
# CONSTANTS
# =============================================================================

TBB_VERSION = "2.0.0"
MAX_POSITIONS = 5
MAX_PROBE_POS = 3
MAX_DEPLOYMENT = 0.30
MIN_PSE_SIZE = 0.002

CAMPAIGN_EXECUTE_STATES = {"READY_EXECUTE"}
CAMPAIGN_PROBE_STATES = {"READY_PROBE"}
CAMPAIGN_WATCH_STATES = {"WATCH"}
CAMPAIGN_REJECT_STATES = {"REJECT"}

LIVE_EXEC_STATES = {"BUY_NOW", "BUY_SMALL", "WAIT_RETEST", "SKIP"}
LIVE_EXEC_BUY = {"BUY_NOW", "BUY_SMALL"}
LIVE_EXEC_WAIT = {"WAIT_RETEST"}
LIVE_EXEC_SKIP = {"SKIP"}

LEGACY_EXECUTE_MODES = {"FULL_EXECUTE", "EXECUTE", "REDUCED", "PROBE"}
LEGACY_FATAL_MODES = {"SKIP", "FATAL_BLOCK"}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TradeBookEntry:
    ticker: str
    rank_score: float
    campaign_verdict: str
    execution_verdict: str
    execution_mode: str
    pse_final_size: float
    capital_alloc_pct: float
    capital_alloc_usd: float
    kelly_dollar_risk: float
    wbs_score: float
    wbs_grade: str
    conv_score: int
    conv_gate: str
    eil_composite_score: float
    eil_verdict: str
    ev_v2: float
    ev_net: float
    mp_state: str
    signal_direction: str
    signal_price: float
    trigger_source: str
    stock_data_source: str
    options_data_source: str
    trigger_confidence_mode: str
    execution_confidence_mode: str
    live_execution_required: bool
    is_pse_miss: bool
    decision_trace: str
    tbb_version: str = TBB_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def log_line(self) -> str:
        miss = " ★MISS" if self.is_pse_miss else ""
        return (
            f"  {self.ticker:<8} {self.campaign_verdict:<13} {self.execution_verdict:<11} "
            f"size={self.capital_alloc_pct*100:.2f}% ${self.capital_alloc_usd:,.0f} "
            f"rank={self.rank_score:.4f} conv={self.conv_score}/5 ev={self.ev_v2:.4f}{miss}"
        )


# =============================================================================
# HELPERS
# =============================================================================

def _f(row: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "nan", "NaN", "N/A"):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return default


def _s(row: dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "nan", "NaN"):
            return str(v).strip()
    return default


def _b(row: dict[str, Any], key: str, default: bool = False) -> bool:
    v = row.get(key)
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return str(v).strip().upper() in {"TRUE", "1", "YES", "Y"}


def _campaign_verdict(row: dict[str, Any]) -> str:
    val = _s(row, "campaign_verdict").upper()
    if val:
        return val

    # Backward compatibility from old morning validation / legacy stack
    mv = _s(row, "mv_verdict").upper()
    if mv == "EXECUTE":
        return "READY_EXECUTE"
    if mv == "PROBE":
        return "READY_PROBE"
    if mv == "WATCH":
        return "WATCH"
    if mv == "REJECT":
        return "REJECT"

    mode = _s(row, "pse_execution_mode").upper()
    if mode in {"FULL_EXECUTE", "EXECUTE", "REDUCED"}:
        return "READY_EXECUTE"
    if mode == "PROBE":
        return "READY_PROBE"
    if mode in LEGACY_FATAL_MODES:
        return "REJECT"
    return "WATCH"


def _execution_verdict(row: dict[str, Any]) -> str:
    val = _s(row, "execution_verdict").upper()
    if val:
        return val

    # Backward compatibility: infer from current fields
    mv = _s(row, "mv_verdict").upper()
    if mv == "EXECUTE":
        return "BUY_NOW"
    if mv == "PROBE":
        return "BUY_SMALL"
    if mv == "WATCH":
        return "WAIT_RETEST"
    if mv == "REJECT":
        return "SKIP"

    mode = _s(row, "pse_execution_mode").upper()
    if mode in {"FULL_EXECUTE", "EXECUTE"}:
        return "BUY_NOW"
    if mode in {"REDUCED", "PROBE"}:
        return "BUY_SMALL"
    return "SKIP"


def _truth_field(row: dict[str, Any], key: str, default: str) -> str:
    val = _s(row, key)
    return val if val else default


# =============================================================================
# RANK SCORE
# =============================================================================

def _rank_score(row: dict[str, Any]) -> float:
    ev = _f(row, "eil_ev_v2", "eil_ev_net", "ev_v2", default=0.0)
    pse_size = _f(row, "pse_final_size", "mv_position_size", default=0.0)
    wbs = _f(row, "wbs_score", "wbs", default=0.0)
    conv = _f(row, "conv_score", default=0.0)
    f_star = _f(row, "kelly_f_star", default=0.0)
    mp_mult = _f(row, "mp_final_size_mult", default=1.0)

    campaign = _campaign_verdict(row)
    execution = _execution_verdict(row)

    campaign_bonus = {
        "READY_EXECUTE": 0.06,
        "READY_PROBE": 0.02,
        "WATCH": 0.00,
        "REJECT": -0.10,
    }.get(campaign, 0.0)

    execution_bonus = {
        "BUY_NOW": 0.05,
        "BUY_SMALL": 0.02,
        "WAIT_RETEST": 0.00,
        "SKIP": -0.10,
    }.get(execution, 0.0)

    score = (
        ev * 30.0 +
        pse_size * 10.0 +
        wbs * 0.002 +
        conv * 0.03 +
        f_star * 5.0 +
        mp_mult * 0.02 +
        campaign_bonus +
        execution_bonus
    )
    return round(score, 6)


# =============================================================================
# ELIGIBILITY
# =============================================================================

def _is_eligible(row: dict[str, Any]) -> tuple[bool, str]:
    campaign = _campaign_verdict(row)
    execution = _execution_verdict(row)
    kelly_v = _s(row, "kelly_verdict").upper()
    conv_gate = _s(row, "conv_trade_gate", default="PASS").upper()
    pse_size = _f(row, "pse_final_size", "mv_position_size", default=0.0)
    block_rsn = _s(row, "pse_block_reason")
    is_miss = _b(row, "pse_miss_flag")
    ev = _f(row, "eil_ev_v2", "eil_ev_net", default=0.0)

    # ── v4.1 HORIZON SAFETY GATE ─────────────────────────────────────────────
    # MONITOR_ONLY signals must NEVER appear in the final trade book.
    # This is a belt-and-braces gate — EIL and Enhancement already exclude them,
    # but if any slip through (e.g. legacy rows without horizon_bucket), this
    # catches them here as the last line of defence before real capital.
    _hb = str(row.get("horizon_bucket", "")).strip().lower()
    _ha = str(row.get("horizon_action", "")).strip().upper()
    _pse_mode = str(row.get("pse_execution_mode", "")).strip().upper()
    if _ha == "MONITOR_ONLY" or _pse_mode == "MONITOR_ONLY":
        return False, f"HORIZON_MONITOR_ONLY:{_hb}:{_ha}"
    if _hb == "blocked":
        return False, f"HORIZON_BLOCKED:{row.get('horizon_block_reason','')}"
    # ── End horizon safety gate ───────────────────────────────────────────────

    # Atheoretic miss-flag bypass
    if is_miss:
        if pse_size <= 0:
            return False, "PSE_MISS_ZERO_SIZE"
        return True, "PSE_MISS_FLAG"

    if campaign in CAMPAIGN_REJECT_STATES:
        return False, f"CAMPAIGN_REJECT:{campaign}"

    if execution in LIVE_EXEC_SKIP:
        return False, f"EXECUTION_SKIP:{execution}"

    if kelly_v == "NO_TRADE":
        # FIX-09: In EOD/advisory mode Kelly has no live options pricing — NO_TRADE is a
        # data-gap artefact, not a genuine no-edge signal. PSE has already sized down.
        # Only apply the Kelly gate in live mode with real options data.
        # EIL is governed advisory telemetry. Missing legacy disclosure must
        # fail to advisory, never re-arm EIL as a trade-book gate.
        _is_advisory = _b(row, "eil_advisory_only", True)
        _is_eod = _s(row, "data_source").upper() in ("EOD_PACKAGE", "EOD", "VANGUARD", "BACKFILL") \
                  or _s(row, "eil_data_mode").upper() in ("EOD_SYNTHETIC", "EOD_FALLBACK")
        if _is_advisory or _is_eod:
            pass   # allow through — Kelly sizing was advisory only
        else:
            return False, f"KELLY_NO_TRADE:{_s(row, 'kelly_notes')}"

    if conv_gate == "BLOCK_INSUFFICIENT":
        return False, f"CONV_INSUFFICIENT:{_s(row, 'conv_notes')}"

    if _s(row, "pse_execution_mode").upper() in LEGACY_FATAL_MODES:
        return False, f"PSE_FATAL:{block_rsn or _s(row, 'pse_execution_mode')}"

    if pse_size < MIN_PSE_SIZE and execution not in LIVE_EXEC_WAIT:
        return False, f"PSE_BELOW_MIN_EXECUTABLE:{pse_size:.5f}<{MIN_PSE_SIZE}"

    if ev < -0.10:
        return False, f"DEEPLY_NEGATIVE_EV:{ev:.4f}"

    if campaign in CAMPAIGN_WATCH_STATES and execution not in LIVE_EXEC_WAIT:
        return False, f"WATCH_WITHOUT_WAIT_EXEC:{execution}"

    return True, "ELIGIBLE"


# =============================================================================
# MAIN BUILDER
# =============================================================================

def build_trade_book(
    signals: list[dict[str, Any]],
    account_size: float = 50_000,
    max_positions: int = MAX_POSITIONS,
    max_probe_pos: int = MAX_PROBE_POS,
) -> list[TradeBookEntry]:
    if not signals:
        log.warning("[TradeBook] Empty signal list — no trades possible")
        return []

    eligible: list[tuple[dict[str, Any], str]] = []
    ineligible: list[tuple[dict[str, Any], str]] = []

    for row in signals:
        ok, reason = _is_eligible(row)
        if ok:
            eligible.append((row, reason))
        else:
            ineligible.append((row, reason))

    if ineligible:
        from collections import Counter
        reasons = Counter(r for _, r in ineligible)
        log.info("[TradeBook] Excluded %d ineligible signals:", len(ineligible))
        for reason, count in reasons.most_common():
            log.info("  %-55s %d", reason, count)

    if not eligible:
        log.warning("[TradeBook] 0 eligible signals after eligibility check")
        return []

    ranked = sorted(eligible, key=lambda x: _rank_score(x[0]), reverse=True)

    execute_tier = [
        (row, rsn) for row, rsn in ranked
        if _campaign_verdict(row) == "READY_EXECUTE"
        and _execution_verdict(row) in LIVE_EXEC_BUY
        and not _b(row, "pse_miss_flag")
    ]

    probe_tier = [
        (row, rsn) for row, rsn in ranked
        if (
            _campaign_verdict(row) == "READY_PROBE"
            or _execution_verdict(row) in LIVE_EXEC_WAIT
            or _b(row, "pse_miss_flag")
        )
    ]

    selected_exec = execute_tier[:max_positions]
    selected_probe = probe_tier[:max_probe_pos]

    if not selected_exec:
        log.info("[TradeBook] No READY_EXECUTE/BUY tier — promoting probe/wait names")
        selected_probe = probe_tier[:max_positions]

    selected_rows = [row for row, _ in (selected_exec + selected_probe)]
    if not selected_rows:
        log.warning("[TradeBook] Selection returned empty")
        return []

    raw_sizes = [_f(row, "pse_final_size", "mv_position_size", default=MIN_PSE_SIZE) for row in selected_rows]
    total_raw = sum(raw_sizes)
    scale = 1.0
    if total_raw > MAX_DEPLOYMENT:
        scale = MAX_DEPLOYMENT / total_raw
        log.info("[TradeBook] Normalising raw=%.1f%% → cap=%.0f%% (scale=%.3f)", total_raw * 100, MAX_DEPLOYMENT * 100, scale)

    entries: list[TradeBookEntry] = []
    for row, raw_size in zip(selected_rows, raw_sizes):
        alloc_pct = raw_size * scale
        alloc_usd = round(alloc_pct * account_size, 2)

        campaign = _campaign_verdict(row)
        execution = _execution_verdict(row)
        trace = (
            f"CAMPAIGN={campaign} | EXEC={execution} | "
            f"PSE={_s(row, 'pse_execution_mode')} | EV={_f(row, 'eil_ev_v2'):.4f} | "
            f"MP={_s(row, 'mp_state')} | EIL={_s(row, 'eil_v3_verdict')} | "
            f"CONV={_s(row, 'conv_score', default='?')}/5 | WBS={_f(row, 'wbs_score', 'wbs'):.0f} | "
            f"KELLY={_s(row, 'kelly_verdict')} | RANK={_rank_score(row):.5f} | "
            f"HORIZON={row.get('horizon_bucket','unrouted')}({row.get('horizon_size_multiplier',1.0):.2f}x)"
        )

        entry = TradeBookEntry(
            ticker=_s(row, "ticker"),
            rank_score=_rank_score(row),
            campaign_verdict=campaign,
            execution_verdict=execution,
            execution_mode=_s(row, "pse_execution_mode", default=execution),
            pse_final_size=_f(row, "pse_final_size", "mv_position_size"),
            capital_alloc_pct=round(alloc_pct, 5),
            capital_alloc_usd=alloc_usd,
            kelly_dollar_risk=_f(row, "kelly_dollar_risk_adj", "kelly_dollar_risk"),
            wbs_score=_f(row, "wbs_score", "wbs"),
            wbs_grade=_s(row, "wbs_grade"),
            conv_score=int(_f(row, "conv_score")),
            conv_gate=_s(row, "conv_trade_gate", default="PASS"),
            eil_composite_score=_f(row, "eil_composite_score"),
            eil_verdict=_s(row, "eil_v3_verdict"),
            ev_v2=_f(row, "eil_ev_v2"),
            ev_net=_f(row, "eil_ev_net"),
            mp_state=_s(row, "mp_state"),
            signal_direction=_s(row, "signal_direction", "direction"),
            signal_price=_f(row, "signal_price", "live_price"),
            trigger_source=_truth_field(row, "trigger_source", "POLYGON_DELAYED_15M"),
            stock_data_source=_truth_field(row, "stock_data_source", "POLYGON_DELAYED_15M"),
            options_data_source=_truth_field(row, "options_data_source", "MARKETDATA_LIVE"),
            trigger_confidence_mode=_truth_field(row, "trigger_confidence_mode", "DELAYED_STRUCTURAL"),
            execution_confidence_mode=_truth_field(row, "execution_confidence_mode", "LIVE_OPTIONS"),
            live_execution_required=_b(row, "live_execution_required", default=True),
            is_pse_miss=_b(row, "pse_miss_flag"),
            decision_trace=trace,
        )
        entries.append(entry)

    entries = sorted(entries, key=lambda e: e.rank_score, reverse=True)
    log.info("[TradeBook] Final trade book: %d entries", len(entries))
    for e in entries:
        log.info(e.log_line())
    return entries


# =============================================================================
# IO WRAPPERS
# =============================================================================

def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        log.warning("[TradeBook] Input CSV missing: %s", path)
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_and_write(
    enhanced_csv: str | Path,
    output_dir: str | Path,
    run_id: str,
    account_size: float = 50_000,
    max_positions: int = MAX_POSITIONS,
    max_probe_pos: int = MAX_PROBE_POS,
) -> dict[str, Any]:
    enhanced_csv = Path(enhanced_csv)
    output_dir = Path(output_dir)
    rows = _read_csv(enhanced_csv)

    entries = build_trade_book(
        rows,
        account_size=account_size,
        max_positions=max_positions,
        max_probe_pos=max_probe_pos,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_csv = output_dir / f"final_trades_{run_id}.csv"
    out_json = output_dir / f"trade_book_summary_{run_id}.json"

    if entries:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(entries[0].to_dict().keys()))
            writer.writeheader()
            writer.writerows([e.to_dict() for e in entries])

    total_deployment_pct = round(sum(e.capital_alloc_pct for e in entries), 5)
    summary = {
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "trade_count": len(entries),
        "total_deployment_pct": total_deployment_pct,
        "output_csv": str(out_csv),
        "output_json": str(out_json),
        "campaign_counts": {},
        "execution_counts": {},
        "tbb_version": TBB_VERSION,
    }

    for e in entries:
        summary["campaign_counts"][e.campaign_verdict] = summary["campaign_counts"].get(e.campaign_verdict, 0) + 1
        summary["execution_counts"][e.execution_verdict] = summary["execution_counts"].get(e.execution_verdict, 0) + 1

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AVSHUNTER Trade Book Builder v2.0")
    parser.add_argument("enhanced_csv")
    parser.add_argument("output_dir")
    parser.add_argument("run_id")
    parser.add_argument("--account_size", type=float, default=50_000)
    parser.add_argument("--max_positions", type=int, default=MAX_POSITIONS)
    parser.add_argument("--max_probe_pos", type=int, default=MAX_PROBE_POS)
    args = parser.parse_args()

    result = build_and_write(
        enhanced_csv=args.enhanced_csv,
        output_dir=args.output_dir,
        run_id=args.run_id,
        account_size=args.account_size,
        max_positions=args.max_positions,
        max_probe_pos=args.max_probe_pos,
    )
    print(json.dumps(result, indent=2))
