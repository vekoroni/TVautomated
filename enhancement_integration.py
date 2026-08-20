"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AVSHUNTER · ENHANCEMENT INTEGRATION LAYER                                 ║
║  Wires E1–E12 into the existing pipeline sequence.                         ║
║                                                                             ║
║  Deploy to: C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/                  ║
║                                                                             ║
║  Called from intelligent_orchestrator.py as Phase 9B                       ║
║  (after EIL Phase 9, before morning_validation Phase 10)                   ║
║                                                                             ║
║  Integration points:                                                        ║
║    1. run_enhancement_layer(run_id, base_dir, account_size)                ║
║       — call from orchestrator after Phase 9 (EIL)                        ║
║    2. apply_kelly_to_morning_validation(mv_signals, sizer, rcs)            ║
║       — call from morning_validation.py after signal validation            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("avshunter.enhancement_layer")

# ─── PATH SETUP ───────────────────────────────────────────────────────────────
# Ensures enhancement modules resolve regardless of working directory

_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from kelly_sizer       import KellySizer, ActuarialCalibrator
from signal_funnel     import SignalFunnel, load_funnel_for_run
from regime_consensus  import RegimeConsensus, RegimeGate
from convergence_engine import ConvergenceEngine
from atheoretic_signals import AtheoreticScanner, enrich_with_ts_convergence, IVSurfaceFrequencyAnalyser


# ─── TRUTH MODEL HELPERS (vNext — safe, no regression) ───────────────────────
# Mirrors _enrich_truth_fields() in execution_intelligence_runner.py.
# Provides canonical campaign/execution verdicts and provenance defaults for
# every signal dict that passes through the enhancement layer.

def _truth_str(sig: dict, key: str, default: str) -> str:
    v = sig.get(key)
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


def _boolish(v, default=False):
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return str(v).upper() in {"TRUE", "1", "YES", "Y"}


def _campaign_verdict(sig: dict) -> str:
    # FIX-TRUTH-CAMPAIGN (2026-04-24): campaign_verdict=WATCH was written as
    # default by superbrain, causing enhancement layer to block 100% of signals.
    # Now reads sb_campaign (authoritative SuperBrain field) as primary fallback.
    cv = str(sig.get("campaign_verdict", "")).upper().strip()
    if cv and cv not in ("WATCH", ""):
        return cv
    sb_camp = str(sig.get("sb_campaign", "")).upper().strip()
    if sb_camp in ("CORE_CAMPAIGN", "CONVEXITY_INJECTION"):
        return "READY_EXECUTE"
    if sb_camp == "STAGED":
        return "READY_PROBE"
    if sb_camp == "AVOID":
        return "REJECT"
    sbv = str(sig.get("sb_final_verdict", "")).upper().strip()
    # FIX 2026-04-28: STAND_DOWN = difficult execution, not no trade.
    # Options never block. STAND_DOWN → READY_PROBE (probe size) not REJECT.
    sb_map = {"EXECUTE": "READY_EXECUTE", "EXECUTE_WITH_RISK": "READY_PROBE",
              "ARMED": "READY_PROBE", "STAND_DOWN": "READY_PROBE",
              "DATA_FAILURE": "REJECT"}
    if sbv in sb_map:
        return sb_map[sbv]
    mv = str(sig.get("mv_verdict", "")).upper().strip()
    return {"EXECUTE": "READY_EXECUTE", "PROBE": "READY_PROBE",
            "WATCH": "WATCH", "REJECT": "REJECT"}.get(mv, "WATCH")


def _execution_verdict(sig: dict) -> str:
    # FIX-EDE-AUTHORITY (2026-04-28): EDE is the final judge.
    # Enhancement layer is executor only — it maps EDE verdicts, never overrides them.
    # EDE=GO must always produce BUY_NOW. EDE=ARMED must always produce BUY_SMALL.
    # No downstream fallback chain (DATA_FAILURE->SKIP, default->SKIP) may override this.
    ede = str(sig.get("ede_verdict", "")).upper().strip()
    if ede == "GO":
        return "BUY_NOW"
    if ede == "ARMED":
        return "BUY_SMALL"
    if ede == "ARMED_HALF":
        return "BUY_SMALL"
    if ede == "BLOCKED":
        return "SKIP"
    # ede == "WAIT" or absent: fall through to legacy chain below (pre-EDE signals only)

    # LEGACY FALLBACK — only reached when ede_verdict is absent or WAIT.
    # Preserved for backward compat with pre-EDE pipeline runs.
    # FIX-TRUTH-EXECUTION (2026-04-24): execution_verdict=SKIP was written as
    # default by superbrain, causing all Kelly sizing to return NO_TRADE.
    ev = str(sig.get("execution_verdict", "")).upper().strip()
    if ev and ev not in ("SKIP", ""):
        return ev
    sb_exec = str(sig.get("sb_execution_mode", "")).upper().strip()
    exec_map = {"FULL_EXECUTE": "BUY_NOW", "REDUCED_EXECUTE": "BUY_NOW",
                "PROBE": "BUY_SMALL", "WAIT": "WAIT_RETEST", "BLOCKED": "SKIP"}
    if sb_exec in exec_map:
        return exec_map[sb_exec]
    sbv = str(sig.get("sb_final_verdict", "")).upper().strip()
    # FIX 2026-04-28: STAND_DOWN -> BUY_SMALL (probe size) not SKIP.
    # Authority hierarchy: Trigger+EV decide trade. Options reduce size only.
    sbv_map = {"EXECUTE": "BUY_NOW", "EXECUTE_WITH_RISK": "BUY_SMALL",
               "ARMED": "WAIT_RETEST", "STAND_DOWN": "BUY_SMALL",
               "DATA_FAILURE": "SKIP"}
    if sbv in sbv_map:
        return sbv_map[sbv]
    mv = str(sig.get("mv_verdict", "")).upper().strip()
    return {"EXECUTE": "BUY_NOW", "PROBE": "BUY_SMALL",
            "WATCH": "WAIT_RETEST", "REJECT": "SKIP"}.get(mv, "WAIT_RETEST")


def _enrich_truth_fields(sig: dict) -> dict:
    sig["campaign_verdict"]          = _campaign_verdict(sig)
    sig["execution_verdict"]         = _execution_verdict(sig)
    sig["trigger_source"]            = _truth_str(sig, "trigger_source",            "POLYGON_DELAYED_15M")
    sig["stock_data_source"]         = _truth_str(sig, "stock_data_source",         "POLYGON_DELAYED_15M")
    sig["options_data_source"]       = _truth_str(sig, "options_data_source",       "MARKETDATA_LIVE")
    sig["trigger_confidence_mode"]   = _truth_str(sig, "trigger_confidence_mode",   "DELAYED_STRUCTURAL")
    sig["execution_confidence_mode"] = _truth_str(sig, "execution_confidence_mode", "LIVE_OPTIONS")
    sig["live_execution_required"]   = _boolish(sig.get("live_execution_required"),  True)
    return sig


# ─── PIPELINE PATHS ───────────────────────────────────────────────────────────

def _run_dir(base_dir: Path, run_id: str) -> Path:
    return base_dir / "data" / "output" / "runs" / run_id

def _sb_dir(base_dir: Path, run_id: str) -> Path:
    return _run_dir(base_dir, run_id) / "superbrain"

def _macro_path(base_dir: Path) -> Path:
    return base_dir / "dropbox" / "macro" / "macro_intelligence_latest.json"

def _eil_csv(base_dir: Path, run_id: str) -> Path:
    sb = _sb_dir(base_dir, run_id)
    # Try eil_enriched first, then superbrain_enriched
    for pattern in [f"eil_enriched_{run_id}.csv", f"superbrain_enriched_{run_id}.csv"]:
        p = sb / pattern
        if p.exists():
            return p
    return sb / f"superbrain_enriched_{run_id}.csv"

def _cal_path(base_dir: Path) -> Path:
    return base_dir / "data" / "actuarial_calibration.json"


# ─── CSV HELPERS ──────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        log.warning(f"CSV not found: {path}")
        return []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception as e:
        log.error(f"Failed to read {path}: {e}")
        return []

def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        log.warning(f"No rows to write to {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        log.info(f"Written {len(rows)} rows → {path}")
    except Exception as e:
        log.error(f"Failed to write {path}: {e}")


# ─── MAIN INTEGRATION RUNNER ──────────────────────────────────────────────────

def run_enhancement_layer(
    run_id:       str,
    base_dir:     Path,
    account_size: float = 50_000,
    parquet_path: Optional[Path] = None,
) -> dict:
    """
    Main entry point. Called from intelligent_orchestrator.py as Phase 9B.

    Sequence:
      1. Signal Funnel (E2) — measure filter efficiency
      2. Regime Consensus Score (E5/E6/E7) — unified macro read
      3. Atheoretic Scanner (E9) — parallel statistical signals
      4. IV Surface Frequency (E12) — options skew anomaly detection
      5. Theory-Stats Convergence (E11) — dual-stream alignment
      6. EIL Convergence Score (E8) — cross-strategy agreement
      7. Kelly Sizer (E1/E3/E4) — final position sizing
      8. Write enhanced CSV — ready for morning_validation

    Returns summary dict for orchestrator reporting.
    """
    log.info(f"{'='*60}")
    log.info(f"AVSHUNTER ENHANCEMENT LAYER — Run: {run_id}")
    log.info(f"{'='*60}")

    summary = {
        "run_id":         run_id,
        "started_at":     datetime.utcnow().isoformat(),
        "phases":         {},
        "signals_in":     0,
        "signals_out":    0,
        "signals_blocked":0,
        "rcs_label":      "UNKNOWN",
        "rcs_score":      0.0,
        "kelly_mult":     1.0,
    }

    # ── Load EIL-enriched signals ─────────────────────────────────────────────
    input_csv = _eil_csv(base_dir, run_id)
    signals   = _read_csv(input_csv)

    if not signals:
        log.error(f"No signals found at {input_csv} — aborting enhancement layer")
        summary["error"] = f"No input signals: {input_csv}"
        return summary

    summary["signals_in"] = len(signals)
    log.info(f"Loaded {len(signals)} signals from {input_csv.name}")

    # ── Phase E1: Signal Funnel (E2) ──────────────────────────────────────────
    log.info("Phase E1: Signal Funnel tracking...")
    funnel = SignalFunnel(run_id=run_id, base_dir=base_dir)

    # Record universe count (all signals before EIL)
    funnel.record("universe_loaded", len(signals))

    # PSE-GAP1 FIX: Use pse_execution_mode (PSE output) instead of raw eil_verdict.
    # Old filter re-blocked signals that PSE had already converted to PROBE/REDUCED
    # via its penalty chain. Now only genuine FATAL_BLOCK is discarded here.
    #
    # FIX-PSE-PASS (2026-04-24): Three bugs in original implementation:
    #   1. "SKIP" was treated as fatal — PSE uses FATAL_BLOCK exclusively for hard
    #      blocks; SKIP is a downstream recommendation, not a gate condition.
    #   2. Fallback used "eil_verdict" (field doesn't exist) — runner writes
    #      "eil_v3_verdict". Blank lookup -> "" -> failed the not-in check -> blocked.
    #   3. No advisory_only bypass — EOD runs where runner set eil_advisory_only=True
    #      on all rows were still gated out, defeating the advisory pass-through.
    def _pse_passes(sig: dict) -> bool:
        pse_mode = str(sig.get("pse_execution_mode", "")).upper().strip()
        if pse_mode:
            # Only FATAL_BLOCK is a genuine hard block from PSE.
            return pse_mode != "FATAL_BLOCK"
        # Advisory bypass: runner sets this when EIL scores are frozen (EOD mode).
        # Convergence gate already handles advisory signals — don't double-gate here.
        if str(sig.get("eil_advisory_only", "")).lower() in ("true", "1"):
            return True
        # Fallback: pre-PSE row — check eil_v3_verdict (correct field name).
        # eil_verdict (old name) is never written by the runner — was always blank.
        eil_v3 = str(sig.get("eil_v3_verdict", "")).upper().strip()
        if eil_v3:
            return eil_v3 != "BLOCKED"
        # No verdict present at all -> pass through; downstream phases will gate.
        return True

    eil_passed = [s for s in signals if _pse_passes(s)]
    funnel.record("after_eil_filter", eil_passed)
    log.info(f"  PSE-passing signals: {len(eil_passed)}/{len(signals)} "
             f"({len(signals)-len(eil_passed)} fatal-blocked or skipped)")

    # Count how many were PSE-sized vs old-style EIL survivors
    _pse_sized = sum(1 for s in eil_passed if s.get("pse_execution_mode"))
    _pse_modes = {}
    for s in eil_passed:
        m = s.get("pse_execution_mode", "LEGACY")
        _pse_modes[m] = _pse_modes.get(m, 0) + 1
    if _pse_sized:
        log.info(f"  PSE mode breakdown: {_pse_modes}")

    summary["phases"]["signal_funnel"] = {
        "universe":        len(signals),
        "eil_passed":      len(eil_passed),
        "pse_sized":       _pse_sized,
        "pse_mode_counts": _pse_modes,
    }

    # ── Phase E2: Regime Consensus Score (E5/E6/E7) ───────────────────────────
    log.info("Phase E2: Computing Regime Consensus Score...")
    macro_path = _macro_path(base_dir)
    rcs_engine = RegimeConsensus(macro_path)
    rcs_result = rcs_engine.compute()
    rcs_engine.save_to_run(run_id, base_dir)

    summary["rcs_label"] = rcs_result.label
    summary["rcs_score"] = rcs_result.rcs
    summary["kelly_mult"] = rcs_result.kelly_multiplier
    summary["phases"]["rcs"] = rcs_result.to_dict()

    log.info(f"  {rcs_result.summary_line()}")

    # Apply regime gate to signals
    gate   = RegimeGate(rcs_result)
    signals = gate.apply(signals)

    # ── Phase E3: Atheoretic Scanner (E9) ─────────────────────────────────────
    log.info("Phase E3: Atheoretic Scanner...")
    ath_scanner = AtheoreticScanner(
        data_source=parquet_path,  # None is fine — will score with limited data
    )
    signals = ath_scanner.enrich_signals(signals)

    ath_fired = sum(1 for s in signals if float(s.get("ath_score", 0)) >= 50)
    log.info(f"  Atheoretic signals fired: {ath_fired}/{len(signals)}")
    summary["phases"]["atheoretic"] = {"signals_fired": ath_fired}

    # ── Phase E4: IV Surface Frequency (E12) ──────────────────────────────────
    log.info("Phase E4: IV Surface Frequency Analysis...")

    # FIX-IVFREQ (2026-04-19): IVSurfaceFrequencyAnalyser uses in-memory rolling
    # history seeded from put_iv / call_iv fields on each signal dict.
    # These fields were never populated because the options CSV was not joined into
    # the signal dicts — so all runs returned z-score=0 and signal=NEUTRAL for
    # all 545 tickers.
    # Fix: join put_25d_iv and call_25d_iv from the options intelligence CSV
    # into each signal dict before calling iv_analyser.enrich_signals().
    try:
        import pandas as pd
        _oi_path = (_run_dir(base_dir, run_id) / "options" /
                    f"options_intelligence_{run_id}.csv")
        if _oi_path.exists():
            _oi_df = pd.read_csv(_oi_path, usecols=lambda c: c in
                                 ["ticker", "put_25d_iv", "call_25d_iv",
                                  "atm_iv", "iv_rank"])
            _iv_map: dict = {}
            for _, _r in _oi_df.iterrows():
                _t = str(_r.get("ticker", "")).strip().upper()
                if not _t:
                    continue
                _put = _r.get("put_25d_iv")
                _call = _r.get("call_25d_iv")
                # Fallback: synthesise from ATM IV when 25d skew not available
                if (_put is None or str(_put) in ("nan", "None", "")) and _r.get("atm_iv"):
                    _atm = float(_r["atm_iv"])
                    _put  = _atm * 1.05   # put skew proxy
                    _call = _atm * 0.97   # call skew proxy
                if _put is not None and _call is not None:
                    try:
                        _iv_map[_t] = (float(_put), float(_call))
                    except (TypeError, ValueError):
                        pass
            # Inject into signal dicts
            for sig in signals:
                _tk = str(sig.get("ticker", "")).strip().upper()
                if _tk in _iv_map:
                    sig["put_iv"], sig["call_iv"] = _iv_map[_tk]
            log.info(f"  IV map loaded: {len(_iv_map)} tickers from options CSV")
        else:
            log.warning(f"  IV map skipped — options CSV not found: {_oi_path}")
    except Exception as _iv_err:
        log.warning(f"  IV map injection failed (non-critical): {_iv_err}")

    iv_analyser = IVSurfaceFrequencyAnalyser()
    signals     = iv_analyser.enrich_signals(signals)

    iv_signals = sum(1 for s in signals if s.get("iv_signal", "NEUTRAL") != "NEUTRAL")
    log.info(f"  IV anomaly signals: {iv_signals}/{len(signals)}")
    summary["phases"]["iv_frequency"] = {"iv_signals": iv_signals}

    # ── Phase E5: Theory-Stats Convergence (E11) ──────────────────────────────
    log.info("Phase E5: Theory-Statistics Convergence...")
    signals = enrich_with_ts_convergence(signals)

    both_aligned    = sum(1 for s in signals if "BOTH_" in s.get("ts_alignment", ""))
    conflicting     = sum(1 for s in signals if s.get("ts_alignment") == "CONFLICTING")
    miss_candidates = sum(1 for s in signals if s.get("ts_miss_candidate") == "True" or
                          s.get("ts_miss_candidate") is True)
    log.info(f"  Both aligned: {both_aligned}  Conflicting: {conflicting}  Miss candidates: {miss_candidates}")
    summary["phases"]["ts_convergence"] = {
        "both_aligned": both_aligned, "conflicting": conflicting,
        "miss_candidates": miss_candidates,
    }

    # ── Phase E6: EIL Convergence Score (E8) ──────────────────────────────────
    log.info("Phase E6: EIL Convergence Score...")

    # FIX-CONV-PRECHECK (2026-04-24): Detect EOD/advisory mode BEFORE calling
    # enrich_batch(). When all five EIL strategy score columns are absent or
    # uniformly zero (std < 0.01 across the batch), the convergence engine has
    # nothing to vote on and correctly returns BLOCK_INSUFFICIENT for every row.
    # The post-hoc advisory override (setting conv_trade_gate="PASS" after the
    # vote) was too late — filter_tradeable() reads the blocked state written by
    # enrich_batch() and ignores the override.
    #
    # Fix: inject neutral stub scores (50.0) for any missing EIL score column
    # before enrich_batch() runs. This allows the convergence engine to vote
    # NEUTRAL (abstain) rather than INSUFFICIENT (block). The advisory flag is
    # preserved so downstream phases know scores are synthetic.
    #
    # Condition: if eil_advisory_only=True on ANY row OR if all five EIL score
    # cols are missing/zero across the batch, inject stubs universally.
    _EIL_SCORE_COLS = [
        "eil_liquidity_score", "eil_iv_score",
        "eil_gex_score", "eil_obi_score", "eil_poc_score",
    ]
    _has_advisory = any(
        str(s.get("eil_advisory_only", "")).lower() in ("true", "1")
        for s in signals
    )
    _all_zero = all(
        all(
            not s.get(c) or str(s.get(c, "0")) in ("0", "0.0", "", "None", "nan")
            for c in _EIL_SCORE_COLS
        )
        for s in signals
    ) if signals else True

    _need_stub = _has_advisory or _all_zero
    _stub_injected = 0
    if _need_stub:
        log.warning(
            "  [FIX-CONV-PRECHECK] EIL scores absent/frozen — injecting neutral stubs (50.0) "
            "so convergence votes NEUTRAL not INSUFFICIENT. advisory=%s all_zero=%s",
            _has_advisory, _all_zero,
        )
        for sig in signals:
            for col in _EIL_SCORE_COLS:
                if not sig.get(col) or str(sig.get(col, "0")) in ("0", "0.0", "", "None", "nan"):
                    sig[col] = 50.0
                    _stub_injected += 1
            sig["eil_advisory_only"] = True   # mark all as advisory when stubs injected
        log.info("  [FIX-CONV-PRECHECK] Injected %d stub score values across %d signals",
                 _stub_injected, len(signals))

    conv_engine = ConvergenceEngine()
    signals     = conv_engine.enrich_batch(signals)

    # Post-vote advisory override: belt-and-braces — if convergence still blocked
    # an advisory row, force PASS. Also handles ts_miss_candidate promotion.
    _advisory_override = 0
    _miss_promoted = 0
    for sig in signals:
        if str(sig.get("eil_advisory_only", "")).lower() in ("true", "1"):
            if sig.get("conv_trade_gate", "PASS") != "PASS":
                sig["conv_trade_gate"] = "PASS"
                sig["conv_notes"] = (
                    str(sig.get("conv_notes", "")) +
                    " | EIL_ADVISORY: convergence gate bypassed — EIL scores are stubs"
                ).strip(" |")
                _advisory_override += 1

        # ts_miss_candidate promotion: atheoretic sees edge, Wyckoff doesn't
        _is_miss = (sig.get("ts_miss_candidate") == "True" or
                    sig.get("ts_miss_candidate") is True)
        if _is_miss and sig.get("conv_trade_gate", "PASS") != "PASS":
            sig["conv_trade_gate"] = "PASS"
            sig["pse_miss_flag"]   = True
            sig["conv_notes"] = (
                str(sig.get("conv_notes", "")) +
                " | PSE_MISS_CANDIDATE: ath_score>60 wbs<50 — promoted for human review"
            ).strip(" |")
            _miss_promoted += 1

    if _advisory_override:
        log.warning(
            "  [FIX-01] conv_trade_gate overridden to PASS for %d advisory_only signals",
            _advisory_override,
        )
    if _miss_promoted:
        log.info(
            "  [PSE-MISS] %d ts_miss_candidate signals promoted through convergence gate "
            "(ath_score>60 wbs<50) — flagged pse_miss_flag=True for review",
            _miss_promoted,
        )

    tradeable, blocked_conv = conv_engine.filter_tradeable(signals)
    log.info(f"  Convergence: {len(tradeable)} tradeable, {len(blocked_conv)} blocked")
    summary["phases"]["convergence"] = {
        "tradeable": len(tradeable), "blocked": len(blocked_conv),
    }

    # Update funnel after convergence filter
    funnel.record("after_eil_filter", tradeable)
    funnel.record("after_superbrain_veto", [s for s in tradeable
                   if s.get("ts_alignment") != "CONFLICTING"])

    # ── Phase E7: Kelly Sizer (E1/E3/E4) ──────────────────────────────────────
    log.info("Phase E7: Kelly Position Sizing...")
    sizer = KellySizer(
        account_size    = account_size,
        calibration_path= _cal_path(base_dir),
    )

    # PSE-GAP2 FIX: Kelly now reads pse_final_size as the sizing anchor.
    # Old behaviour: Kelly computed f_star from WBS win rate alone, then applied
    # regime × convergence fractions. PSE's penalty chain (EV, MP, EIL, options,
    # regime, confidence) was ignored — Kelly started fresh.
    # New behaviour: if pse_final_size is present and non-zero, it becomes the
    # dollar_risk anchor. Kelly's regime × convergence fractions refine it rather
    # than replacing it. WBS win rate still gates NO_TRADE for very weak signals.
    # Fallback: if pse_final_size absent (pre-PSE row), old Kelly logic runs unchanged.
    sized_signals = []
    for sig in signals:
        conv_frac = float(sig.get("conv_kelly_fraction", 0.75))
        ts_frac   = float(sig.get("ts_kelly_fraction", 0.75))
        iv_frac   = float(sig.get("iv_kelly_fraction", 0.75))

        # Combined conviction multiplier (regime × convergence × ts × iv)
        base_mult  = rcs_result.kelly_multiplier
        final_mult = base_mult * conv_frac * ts_frac * iv_frac
        final_mult = round(max(0.0, min(1.0, final_mult)), 4)

        # PSE anchor: use pse_final_size if available
        pse_size = _safe_float(sig.get("pse_final_size"))

        result = sizer.size_trade(
            ticker             = sig.get("ticker", "UNKNOWN"),
            wbs_score          = float(sig.get("wbs_score") or sig.get("wbs") or 0),  # WBS writes "wbs" not "wbs_score"
            max_profit         = _safe_float(sig.get("max_profit")),
            max_loss           = _safe_float(sig.get("max_loss")),
            bid                = _safe_float(sig.get("bid")),
            ask                = _safe_float(sig.get("ask")),
            strike_width       = _safe_float(sig.get("strike_width")),
            options_premium    = _safe_float(sig.get("mid") or sig.get("options_premium")),
            regime_multiplier  = final_mult,
            pse_size_override  = pse_size,   # PSE-GAP2: anchor Kelly to PSE output
        )

        enriched = _enrich_truth_fields(dict(sig))
        enriched.update({
            "kelly_combined_mult":   final_mult,
            "kelly_win_rate_p":      result.win_rate_p,
            "kelly_win_rate_source": result.win_rate_source,
            "kelly_b_ratio":         result.b_ratio,
            "kelly_f_star":          result.f_star,
            "kelly_f_final":         result.f_final,
            "kelly_dollar_risk":     result.dollar_risk,
            "kelly_dollar_risk_adj": result.dollar_risk_adj,
            "kelly_max_contracts":   result.max_contracts,
            "kelly_verdict":         result.verdict,
            "kelly_notes":           result.notes,
            "kelly_pse_anchored":    bool(pse_size),   # audit: was PSE anchor used?
        })
        sized_signals.append(enriched)
        log.debug(result.summary_line())

    # ── Phase E8: Final Funnel Record ─────────────────────────────────────────
    # PATCH C — campaign/execution-aware tradeable filter (vNext upgrade)
    # Replaces the old kelly_verdict-only gate with full discipline-layer logic.
    # PSE miss candidates (atheoretic edges suppressed by Wyckoff) are preserved.
    tradeable_final = []
    for s in sized_signals:
        s        = _enrich_truth_fields(s)
        campaign  = _campaign_verdict(s)
        execution = _execution_verdict(s)
        kelly_ok  = s.get("kelly_verdict") != "NO_TRADE"
        conv_ok   = s.get("conv_trade_gate", "PASS") == "PASS"
        miss_flag = _boolish(s.get("pse_miss_flag"))
        # FIX-KELLY-ADVISORY (2026-04-24): In EOD/overnight mode the Kelly sizer
        # has no live options pricing, so it returns NO_TRADE for every signal.
        # This caused 0 signals out even after convergence passed all 814.
        # Advisory bypass: when eil_advisory_only=True (set by EIL runner when
        # all microstructure scores are frozen) AND convergence passed, we allow
        # the signal through regardless of kelly_verdict. These signals are sized
        # at probe level by PSE already — Kelly's NO_TRADE is a data-gap artefact.
        advisory = str(s.get("eil_advisory_only", "")).lower() in ("true", "1")

        eligible = False
        if miss_flag:
            eligible = True
        elif advisory and conv_ok:
            # EOD advisory: bypass Kelly NO_TRADE gate — data gap, not bad signal
            eligible = True
        elif campaign == "READY_EXECUTE" and execution in {"BUY_NOW", "BUY_SMALL"} and kelly_ok and conv_ok:
            eligible = True
        elif campaign == "READY_PROBE" and execution in {"BUY_SMALL", "WAIT_RETEST"} and kelly_ok and conv_ok:
            eligible = True

        s["tradeable_final"] = eligible
        if eligible:
            tradeable_final.append(s)

    funnel.record("traded", tradeable_final)
    funnel.save()

    # PATCH D — campaign/execution verdict distribution in summary
    summary["campaign_counts"]  = {}
    summary["execution_counts"] = {}
    for s in sized_signals:
        cv = _campaign_verdict(s)
        ev = _execution_verdict(s)
        summary["campaign_counts"][cv]  = summary["campaign_counts"].get(cv,  0) + 1
        summary["execution_counts"][ev] = summary["execution_counts"].get(ev, 0) + 1

    summary["signals_out"]     = len(tradeable_final)
    summary["signals_blocked"] = len(signals) - len(tradeable_final)
    summary["discard_rate"]    = funnel.discard_rate()
    summary["completed_at"]    = datetime.utcnow().isoformat()

    # ── Write enhanced output CSV ─────────────────────────────────────────────
    out_path = _sb_dir(base_dir, run_id) / f"enhanced_{run_id}.csv"
    _write_csv(out_path, sized_signals)
    summary["output_csv"] = str(out_path)

    # ── Write summary JSON ────────────────────────────────────────────────────
    summary_path = _sb_dir(base_dir, run_id) / f"enhancement_summary_{run_id}.json"
    try:
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        log.info(f"Enhancement summary: {summary_path}")
    except Exception as e:
        log.warning(f"Failed to write summary JSON: {e}")

    # ── Final report ──────────────────────────────────────────────────────────
    log.info(f"{'='*60}")
    log.info(f"ENHANCEMENT LAYER COMPLETE")
    log.info(f"  Signals in:      {summary['signals_in']}")
    log.info(f"  Signals out:     {summary['signals_out']}")
    log.info(f"  Discard rate:    {summary.get('discard_rate', 0)*100:.1f}%")
    log.info(f"  Regime:          {summary['rcs_label']} (RCS={summary['rcs_score']:.1f})")
    log.info(f"  Kelly mult:      {summary['kelly_mult']:.1f}×")
    log.info(f"{'='*60}")

    return summary


def _safe_float(val) -> Optional[float]:
    """Safely convert to float, return None on failure."""
    try:
        return float(val) if val is not None and str(val).strip() not in ("", "None", "nan") else None
    except (ValueError, TypeError):
        return None


# ─── MORNING VALIDATION INTEGRATION ───────────────────────────────────────────

def apply_kelly_to_morning_validation(
    mv_signals:   list[dict],
    base_dir:     Path,
    run_id:       str,
    account_size: float = 50_000,
) -> list[dict]:
    """
    Lightweight Kelly application for morning_validation.py.
    Reads existing RCS from run folder (already computed by evening orchestrator).
    Adds kelly_* columns to morning validation output.

    Add to morning_validation.py:
        from enhancement_integration import apply_kelly_to_morning_validation
        mv_signals = apply_kelly_to_morning_validation(
            mv_signals, BASE_DIR, run_id, account_size=ACCOUNT_SIZE
        )
    """
    # Load pre-computed RCS
    rcs_path = _sb_dir(base_dir, run_id) / f"rcs_{run_id}.json"
    kelly_mult = 1.0
    rcs_label  = "UNKNOWN"

    if rcs_path.exists():
        try:
            with open(rcs_path) as f:
                rcs_data    = json.load(f)
            kelly_mult  = rcs_data.get("kelly_multiplier", 1.0)
            rcs_label   = rcs_data.get("label", "UNKNOWN")
            log.info(f"MV Kelly: loaded RCS {rcs_label} mult={kelly_mult:.1f}×")
        except Exception as e:
            log.warning(f"Could not load RCS for MV: {e}")
    else:
        log.warning(f"No RCS file for {run_id} — using full Kelly (mult=1.0)")

    sizer = KellySizer(
        account_size     = account_size,
        calibration_path = _cal_path(base_dir),
    )

    sized = sizer.size_batch(mv_signals, regime_multiplier=kelly_mult)
    out = []
    for sig in sized:
        sig = _enrich_truth_fields(sig)
        out.append(sig)
    return out


# ─── ORCHESTRATOR HOOK ────────────────────────────────────────────────────────
# Add this to intelligent_orchestrator.py Phase 9B:
#
# ─── PHASE 9B: Enhancement Layer ─────────────────────────────────────────────
# log.info("Phase 9B: Running Enhancement Layer (Kelly, RCS, Atheoretic, Convergence)...")
# try:
#     from enhancement_integration import run_enhancement_layer
#     enh_summary = run_enhancement_layer(
#         run_id       = canonical_run_id,
#         base_dir     = BASE_DIR,
#         account_size = cfg.ACCOUNT_SIZE,   # add to OrchestratorConfig
#         parquet_path = cfg.ACTUARIAL_PARQUET,  # optional — Path or None
#     )
#     log.info(f"Enhancement Layer: {enh_summary['signals_out']} tradeable signals")
#     log.info(f"Discard rate: {enh_summary.get('discard_rate',0)*100:.1f}%")
# except Exception as e:
#     log.error(f"Enhancement Layer failed: {e}", exc_info=True)
# ─────────────────────────────────────────────────────────────────────────────


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run AVSHUNTER Enhancement Layer")
    parser.add_argument("--run_id",      required=True, help="Pipeline run ID")
    parser.add_argument("--base_dir",    required=True, help="AVSHUNTER-Intelligence base path")
    parser.add_argument("--account",     type=float, default=50000, help="Account size $")
    parser.add_argument("--parquet",     type=str, default=None, help="Actuarial parquet path")
    parser.add_argument("--calibrate",   action="store_true", help="Run actuarial calibration first")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    base = Path(args.base_dir)

    if args.calibrate and args.parquet:
        log.info("Running actuarial calibration...")
        from kelly_sizer import ActuarialCalibrator
        cal = ActuarialCalibrator(args.parquet)
        cal.calibrate(base / "data" / "actuarial_calibration.json")

    summary = run_enhancement_layer(
        run_id       = args.run_id,
        base_dir     = base,
        account_size = args.account,
        parquet_path = Path(args.parquet) if args.parquet else None,
    )

    print(f"\n{'='*50}")
    print(f"Enhancement Layer Complete")
    print(f"  Signals in:   {summary.get('signals_in', 0)}")
    print(f"  Signals out:  {summary.get('signals_out', 0)}")
    print(f"  Discard rate: {summary.get('discard_rate', 0)*100:.1f}%")
    print(f"  Regime:       {summary.get('rcs_label')} ({summary.get('rcs_score', 0):.1f})")
    print(f"  Output:       {summary.get('output_csv', 'N/A')}")
