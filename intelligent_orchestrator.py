# ============================================================
# AVSHUNTER — intelligent_orchestrator.py
# Version   : v3.2.1
# Built     : 2026-05-03
# Session   : May 2026 pipeline build
# SHA256    : e3ecf6e1e0dee6da
# Changes   : v3.2.1 FIX-WEEKEND-01 — market hours guard now skips block on Saturday/Sunday
# ============================================================
#!/usr/bin/env python3
"""
AVSHUNTER INTELLIGENT ORCHESTRATOR v3.1
======================================

Change (2026-04-29 v2.9 — Trigger Layer Wiring Gap Fix):
- Phase 8.6b added: Trigger Layer CSV enrichment.
  Runs AFTER EIL (Phase 9) so eil_enriched_{run_id}.csv exists.
  Calls trigger_layer.enrich_csv() to write trigger_codes, trigger_count,
  trigger_primary, trigger_quality, trigger_score, trigger_go_eligible,
  trigger_stale, trigger_ev_10d, trigger_ev_sign as flat columns into the
  EIL CSV. EDE now reads these columns directly — fixes the wiring gap
  where EDE saw ede_trigger_count=0 for all signals and sovereign gate
  fired WAIT universally (1470 WAIT, 0 GO, 0 ARMED).
- EDE_ENGINE path corrected: was VANGUARD_DIR/execution_decision_engine.py,
  now BASE_DIR/execution_decision_engine.py. The fixed v4.1.1 is deployed
  to AVSHUNTER-Intelligence root, not the vanguard subdirectory.
- Phase 8.6 (package JSON patching) retained alongside 8.6b — both run.
  Package JSONs still needed by morning validation and EOD candidate engine.
- Phase 1B crash fixed: 'NoneType object has no attribute __dict__'
  Root cause: run_horizon_router() tried to access _sig._raw on a RoutedSignal
  dataclass — _raw was in the input signal dict but never a field on RoutedSignal.
  Fix: build _ticker_to_raw lookup from _signals list before the write loop.
  RoutedSignal fields (ticker, action, size_multiplier, block_reason) accessed
  directly as dataclass attributes — no _raw access anywhere in the write loop.
  Phase 1B now executes correctly and writes horizon CSVs + summary JSON.

Change (2026-04 v2.8 — Downstream Horizon Awareness + MONITOR_ONLY Enforcement):
- All 7 downstream files updated to consume horizon_bucket from Phase 1B router:
    SuperBrain v1.2:        horizon gate before V7 veto — 11-20D → MONITOR_ONLY immediately
                            V4 TRANSITIONAL veto exempt for 1-5D/6-10D chart-confirmed signals
    EIL Runner v4.1:        horizon gate in _process_row — short-circuits 11-20D/blocked
                            horizon_size_multiplier applied to pse_final_size (6-10D=0.70x)
    Enhancement v4.1:       MONITOR_ONLY filtered before Kelly/PSE — not sized
                            horizon_size_multiplier applied to kelly_dollar_risk_adj
    Trade Book Builder:     _is_eligible() horizon safety gate — MONITOR_ONLY never in trades
    EOD Candidate Engine:   build_candidate_manifest() accepts horizon kwargs
                            stamps horizon_bucket/action/size_multiplier onto every candidate
    Morning Validation:     horizon gate skips 11-20D live scoring (MONITOR_ONLY output)
                            horizon_size_multiplier applied to position_size at execution time
    EDE v1.1:               main loop short-circuits 11-20D/blocked before 4-question scoring
                            size_fraction scaled by horizon_size_multiplier for 6-10D
- Orchestrator logging updated: SuperBrain MONITOR_ONLY count, EDE horizon counts,
  Enhancement monitor_only_count, Phase 9B horizon breakdown in run summary
- Phase 9C warning now distinguishes horizon exclusions from genuine no-trade conditions
- generate_report() reads horizon_summary for session-level horizon routing stats

Change (2026-04 v2.7 — Macro Horizon Router + Three-Bucket Signal Routing):
- Phase 1B added: Macro Horizon Router
  Runs after discovery, before Vanguard pipeline.
  Routes each candidate signal to 1-5D / 6-10D / 11-20D bucket based on
  the forward bias stack in the macro contract.
  Business outcome:
    1-5D  (DTE<=5):  GO_SELECTIVE when bullish_prob>=63% — long calls, chart confirmed
    6-10D (DTE6-10): GO_REDUCED when prob>=58% — continuation only, 0.70x size
    11-20D (DTE11+): MONITOR_ONLY when prob<56% — no proactive entries
    PUTS:  blocked unless VIX>22 AND phase D breakdown confirmed
  Writes horizon_1_5d / horizon_6_10d / horizon_11_20d CSVs per run.
  Patches horizon_bucket into superbrain_enriched so EIL + EDE consume it.
  EOD Candidate Engine receives horizon summary for tiered morning validation.
  Requires: macro_horizon_router.py deployed to BASE_DIR.
  NON-CRITICAL: falls back to legacy single-bucket mode if not deployed.
- Config additions: HORIZON_ROUTER, DTE_BUCKET_*, HORIZON_SIZE, PUT_PERMISSION_VIX_THRESHOLD
- orchestrator.py line 1873 fix: BASE_DIR → cfg.BASE_DIR (regime screener)

Change (2026-04 v2.6 — Path Corrections + Phase 4.6):
- VANGUARD_DIR added to OrchestratorConfig as absolute path:
    C:/Users/ACKVerissimo/vanguard/
  This is a separate directory from AVSHUNTER-Intelligence/ — it is the
  standalone actuarial/database layer and must NOT use BASE_DIR.
- ACTUARIAL_CACHE_BUILDER = VANGUARD_DIR / "actuarial_cache_builder.py"
- ACTUARIAL_CACHE_PATH    = VANGUARD_DIR / "data" / "actuarial_cache.parquet"
- EDE_ENGINE corrected from BASE_DIR to VANGUARD_DIR / "execution_decision_engine.py"
- Phase 4.6 wired into evening_workflow: runs after macro normalisation,
  before discovery. Uses incremental mode. NON-CRITICAL.
- Actuarial Cache Builder added to optional scripts preflight check.

Change (2026-04 v2.5 — Execution Decision Engine):
- Phase 9.5 added: Execution Decision Engine (EDE)
  Sits between EIL (Phase 9) and Enhancement Layer (Phase 9B).
  Answers four mandatory questions per signal:
    Q1 Is there edge?               → Actuarial composite score
    Q2 Is timing acceptable?        → EIL score gate
    Q3 Is the instrument tradeable? → Options hard gates (spread, delta, breakeven)
    Q4 Is risk acceptable?          → Actuarial confidence + penalty_multiplier
  Outputs per signal: GO / ARMED / ARMED_HALF / BLOCKED + size_fraction for PSE.
  Emits ede_decisions_{run_id}.csv, ede_top_trades_{run_id}.csv, ede_summary.json.
  NON-CRITICAL: enhancement layer runs regardless.
  Config: cfg.EDE_ENGINE  |  Deploy: execution_decision_engine.py to BASE_DIR
  Entry point: run_ede_from_orchestrator()

Change (2026-04-23 v2.4):
- run_superbrain_layer() redesigned for reliable EOD operation:
    • eod_mode=True parameter (default) — evening runs always use EOD mode
    • --eod flag passed to SuperBrain v2.2.0 activating paralysis-fix bypass gates
    • Vanguard fallback: if options_intelligence CSV absent, uses vanguard_signals.csv
    • SuperBrain NEVER skipped due to missing options layer in EOD mode
    • Output validation: logs enriched signal count, warns on 0-signal output
- run_options_intelligence() failure messaging updated to document fallback path
- Evening workflow: run_superbrain_layer(eod_mode=True) explicit call

Change (2026-04-23):
- Phase 11 added: Execution Gate (execution_gate.py)
  Runs inside premarket_workflow() after morning_validation_engine.
  Non-critical — morning workflow continues unaffected if gate errors.
  Applies live-market discipline: spread, delta range, IV ceiling,
  runway feasibility, gamma flip state, breakeven vs runway check.
  Maps campaign/execution verdicts to final_action (BUY_NOW/BUY_SMALL/WAIT/SKIP).
  Output: execution_gated_{run_id}.csv + execution_actionable_{run_id}.csv
          in data/output/runs/{run_id}/trades/

Change (2026-03-08):
- Phase 9 added: Execution Intelligence Layer (EIL)
  Runs after Wall Break Scorer (Phase 8e) in both evening and premarket workflows.
  Non-critical — pipeline continues unaffected if EIL errors.
  Output: eil_enriched_{run_id}.csv in data/output/runs/{run_id}/superbrain/
  Advisory mode by default (set EIL_ADVISORY_ONLY=false env var to enable live gating).
  Deploy execution_intelligence_runner.py + vanguard/execution/ alongside this file.

Change (2026-03-02):
- Universe preflight gate is now DYNAMIC (min/target/mode), so the pipeline
  does not fail simply because the validated universe shrank (e.g. 1940 tickers).
- Behaviour:
    AUTO (default): FAIL if n < min_universe; WARN (but proceed) if n < target_universe
    SOFT          : FAIL if n < min_universe (ignore target)
    HARD          : FAIL if n < target_universe

Usage examples:
    python intelligent_orchestrator_v2_1.py --evening
    python intelligent_orchestrator_v2_1.py --evening --min_universe 800 --target_universe 2500 --universe_gate_mode AUTO
    python intelligent_orchestrator_v2_1.py --evening --universe_gate_mode HARD --target_universe 3000
    python intelligent_orchestrator_v2_1.py --premarket
"""

import argparse
import csv
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, time as dtime
from pathlib import Path
from typing import List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from scripts.macro_quant_packet import (
        build_macro_quant_packet,
        missing_macro_quant_packet,
        write_json,
    )
except Exception:
    from macro_quant_packet import (  # type: ignore
        build_macro_quant_packet,
        missing_macro_quant_packet,
        write_json,
    )

try:
    from contracts.handoff_contract import (
        PRIORITY_MACRO_QUANT,
        build_truth_packet_from_row,
    )
except Exception:
    from handoff_contract import (  # type: ignore
        PRIORITY_MACRO_QUANT,
        build_truth_packet_from_row,
    )

try:
    from contracts.macro_enrichment_delta import (
        find_macro_enrichment_delta,
        load_macro_enrichment_delta,
        merge_macro_enrichment_delta,
    )
except Exception:
    from macro_enrichment_delta import (  # type: ignore
        find_macro_enrichment_delta,
        load_macro_enrichment_delta,
        merge_macro_enrichment_delta,
    )


def _strict_actuarial_v6_enabled() -> bool:
    return os.environ.get("AVSHUNTER_STRICT_ACTUARIAL_V6", "").strip() == "1"


PHASE2_LAYER2_FIELDS = [
    "layer2__state_match_method",
    "layer2__state_match_stage",
    "layer2__state_match_dimensions",
    "layer2__state_match_quality",
    "layer2__state_match_similarity",
    "layer2__state_match_is_exact",
    "layer2__sample_size",
    "layer2__sample_confidence_bucket",
    "layer2__confidence_penalty",
    "layer2__confidence_weight",
    "layer2__preferred_horizon",
    "layer2__matched_state_key",
    "layer2__original_state_key",
    "layer2__fallback_reason",
    "layer2__raw_prob_up_5d",
    "layer2__raw_prob_up_10d",
    "layer2__raw_prob_up_20d",
    "layer2__raw_prob_down_5d",
    "layer2__raw_prob_down_10d",
    "layer2__raw_prob_down_20d",
    "layer2__raw_prob_target_hit",
    "layer2__raw_prob_stop_hit",
    "layer2__raw_expected_return",
    "layer2__raw_expected_drawdown",
    "layer2__raw_expected_time_to_target",
    "layer2__baseline_probability",
    "layer2__adjusted_prob_target_hit",
    "layer2__adjusted_expected_return",
    "layer2__probability_edge",
    "layer2__probability_verdict",
]

# ── Load .env FIRST — before any module reads os.environ ─────────────────────
# All child subprocesses inherit os.environ, so loading here propagates
# POLYGON_API_KEY and MARKETDATA_API_KEY to Discovery, OI, EIL, and Vanguard.
def _load_dotenv_safe() -> None:
    """Load .env from BASE_DIR (repo root). Silent if file absent or dotenv not installed."""
    try:
        from dotenv import load_dotenv
        _env = Path(__file__).resolve().parent / ".env"
        if _env.exists():
            load_dotenv(_env, override=False)  # override=False: real env vars win
            print(f"[ENV] Loaded .env from {_env}")
            # Validate critical keys
            for key in ("POLYGON_API_KEY", "MARKETDATA_API_KEY"):
                if os.environ.get(key):
                    print(f"[ENV] ✅ {key}: set ({len(os.environ[key])} chars)")
                else:
                    print(f"[ENV] ⚠️  {key}: NOT SET — options intelligence and data fetch will fail")
        else:
            print(f"[ENV] .env not found at {_env} — relying on shell environment")
    except ImportError:
        print("[ENV] python-dotenv not installed — relying on shell environment")
        print("[ENV] Install with: pip install python-dotenv")

_load_dotenv_safe()


# ============================================================ LOGGING ========

def setup_logger() -> logging.Logger:
    logger = logging.getLogger("ORCHESTRATOR")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        # Console handler — always present
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        # File handler — creates logs\ directory if needed
        try:
            _log_dir = Path(__file__).resolve().parent / "logs"
            _log_dir.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(
                _log_dir / "orchestrator.log",
                mode="a",
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError:
            pass   # log dir not writable — console only, do not abort

    return logger


logger = setup_logger()

# ── v1.1: Module-level sector state — populated after macro JSON load ─────────
# _run() reads these to propagate via env vars to all subprocesses.
# Declared here so _run() can reference them before the main flow sets them.
_sector_bias_map: dict  = {}
_macro_conviction: float = 0.60
_macro_quant_packet: dict = {}
_macro_regime_state: str = ""


# ============================================================ CONFIG =========

class OrchestratorConfig:
    """All paths and thresholds in one place."""

    # Script-relative — correct regardless of which directory the user launches from
    BASE_DIR    = Path(__file__).resolve().parent
    DATA_DIR    = BASE_DIR / "data"
    OUTPUT_DIR  = DATA_DIR / "output"
    RUNS_DIR    = OUTPUT_DIR / "runs"          # per-run subdirectories live here
    ARCHIVE_DIR = DATA_DIR / "archive"
    SCRIPTS_DIR = BASE_DIR / "scripts"
    MACRO_DIR   = BASE_DIR / "dropbox" / "macro"
    MACRO_FILE  = MACRO_DIR / "macro_intelligence_latest.json"  # fixed drop location

    UNIVERSE_FILE = DATA_DIR / "universe" / "polygon_liquid_universe.csv"

    # ── Universe Scanner (Phase 0) ───────────────────────────────────────────
    UNIVERSE_SCANNER_DIR      = OUTPUT_DIR / "universe_scanner"
    UNIVERSE_SCANNER_MANIFEST = OUTPUT_DIR / "universe_scanner" / "scanner_manifest.json"
    UNIVERSE_SCANNER_SCRIPT   = SCRIPTS_DIR / "avshunter_universe_scanner.py"
    SCANNER_MAX_AGE_HOURS     = 24
    # Retired 2026-05-10: raw manual ticker upload is no longer part of
    # normal UAT intake. Catalyst/context rows must enter through
    # dropbox/inputs/catalyst_calendar_latest.csv so the pipeline receives
    # source, date/window, direction, route, and risk context together.
    MANUAL_TICKER_UPLOAD_FILE = BASE_DIR / "dropbox" / "inputs" / "manual_ticker_upload_latest.csv"
    MANUAL_TICKER_MAX_AGE_HOURS = 24

    # Root-level scripts
    DISCOVERY_ULTIMATE = BASE_DIR / "avshunter_discovery_ULTIMATE.py"
    POSITION_TRACKER   = BASE_DIR / "position_lifecycle_tracker.py"
    PREMARKET_INTEL    = BASE_DIR / "premarket_intelligence_ULTIMATE.py"

    # scripts\ subfolder — VANGUARD pipeline
    BUILD_PACKAGES      = SCRIPTS_DIR / "build_packages_from_discovery.py"
    INJECT_MACRO        = SCRIPTS_DIR / "inject_macro_into_packages.py"
    APPLY_MACRO_ENRICHMENT_DISCOVERY = SCRIPTS_DIR / "apply_macro_enrichment_to_discovery.py"
    APPLY_EXTERNAL_INTEL_REVIEW_LANE = SCRIPTS_DIR / "apply_external_intel_review_lane.py"
    BACKFILL_TIMESERIES = SCRIPTS_DIR / "backfill_timeseries_into_packages.py"
    RUN_VANGUARD        = SCRIPTS_DIR / "run_vanguard_from_packages.py"

    # scripts\ subfolder — Options Intelligence Layer (Phase 8b)
    OPTIONS_INTEL       = SCRIPTS_DIR / "avshunter_options_intelligence.py"
    PHANTOM_RUNNER      = SCRIPTS_DIR / "run_phantom.py"
    PHANTOM_DB_PATH     = BASE_DIR / "data" / "phantom" / "phantom_history.db"

    # scripts\ subfolder — CORE INTEL Exporter (Phase 8c)
    CORE_INTEL_EXPORTER = SCRIPTS_DIR / "core_intel_exporter.py"

    # scripts\ subfolder — Super Brain Layer (Phase 8d)
    SUPERBRAIN_LAYER = SCRIPTS_DIR / "avshunter_superbrain_layer.py"  # Logic migrated to OI 2026-04-28. File retained: run_superbrain_passthrough() copies OI→superbrain_enriched. Do NOT remove — EIL/GARCH/WBS/CT Gate require superbrain_enriched to exist.

    # scripts\ subfolder — Monetisation Policy Engine (driver for all post-SB decisions)
    MONETISATION_POLICY = SCRIPTS_DIR / "avshunter_monetisation_policy.py"

    # Root-level — Execution Intelligence Layer (Phase 9)
    EIL_RUNNER = BASE_DIR / "execution_intelligence_runner.py"

    # Root-level — Execution Gate (Phase 11 — live execution discipline)
    EXECUTION_GATE = BASE_DIR / "execution_gate.py"

    # ── Separate vanguard directory — actuarial database layer ───────────────
    # C:/Users/ACKVerissimo/vanguard/ is NOT part of AVSHUNTER-Intelligence/.
    # It is a standalone actuarial/database layer. Absolute paths required.
    VANGUARD_DIR            = Path(r"C:\Users\ACKVerissimo\vanguard")

    # Phase 4.6 — Actuarial Cache Builder
    # Runs in evening_workflow after macro normalisation, before packages are built.
    # Reads:  VANGUARD_DIR/data/actuarial_database_v6.parquet  (Sprint 3 — v6 adds future_momentum_bucket)
    # Writes: VANGUARD_DIR/data/actuarial_cache.parquet  (consumed by build_packages)
    # IMPORTANT: actuarial_cache_builder.py must be told to read _v6 — check its DB_PATH constant.
    ACTUARIAL_CACHE_BUILDER = VANGUARD_DIR / "actuarial_cache_builder.py"
    ACTUARIAL_CACHE_PATH    = VANGUARD_DIR / "data" / "actuarial_cache.parquet"
    ACTUARIAL_DB_PATH       = VANGUARD_DIR / "data" / "actuarial_database_v6.parquet"  # Sprint 3
    ACTUARIAL_TRANSITION_MATRIX_BUILDER = SCRIPTS_DIR / "build_phase_transition_matrix.py"
    ACTUARIAL_TRANSITION_MATRIX_DIR     = VANGUARD_DIR / "data" / "transition_matrix"
    ACTUARIAL_TRANSITION_MATRIX_LATEST  = ACTUARIAL_TRANSITION_MATRIX_DIR / "actuarial_phase_transition_matrix_latest.csv"

    # Phase 8.5 — Actuarial Enrichment Pass (in scripts\ — part of AVSHUNTER-Intelligence)
    # Runs AFTER run_vanguard_from_packages.py, BEFORE options_intelligence.
    # Patches pkg["actuarial"] using layer2__ state columns written by Vanguard.
    ACTUARIAL_ENRICHMENT_PASS = SCRIPTS_DIR / "actuarial_enrichment_pass.py"

    # Phase 9.5 — Execution Decision Engine
    # FIX-EDE-PATH (2026-04-29 v2.9): EDE_ENGINE was pointing to VANGUARD_DIR
    # (C:/Users/ACKVerissimo/vanguard/execution_decision_engine.py) but the
    # fixed v4.1.1 is deployed to BASE_DIR (AVSHUNTER-Intelligence/).
    # Corrected to BASE_DIR so the orchestrator imports the right version.
    EDE_ENGINE = BASE_DIR / "execution_decision_engine.py"

    # scripts/ — Sector Alignment Utility (v1.1 — sector_rotation handshake)
    SECTOR_ALIGNMENT_UTIL = SCRIPTS_DIR / "sector_alignment.py"

    # Root-level — Two-Phase Intelligence System (Phase 10 + Morning Validation)
    EOD_CANDIDATE_ENGINE           = BASE_DIR / "eod_candidate_engine.py"
    MORNING_VALIDATION_ENGINE      = BASE_DIR / "morning_validation_engine.py"
    MORNING_VALIDATION_MAX_CANDIDATES = 0    # 0 = no cap on EOD manifest size
    MORNING_VALIDATION_TIERS       = "A,B,C,WATCH" # tiers processed at market open
    MORNING_VALIDATION_MAX_SIGNALS = 0       # 0 = live-score the full EOD slate

    # Quality thresholds (ratios relative to summary["universe_size"])
    EXPECTED_CANDIDATE_RATIO_MIN = 0.15   # 15% of universe
    EXPECTED_CANDIDATE_RATIO_MAX = 0.25   # 25% of universe
    EXPECTED_EARLY_RATIO_MIN     = 0.015  # 1.5% of universe
    EXPECTED_EARLY_RATIO_MAX     = 0.05   # 5% of universe

    # Macro staleness warning threshold (hours)
    # Set to 20h: tight enough to catch a genuinely stale file before the next
    # evening run, while still covering a valid overnight hold from the prior close.
    MACRO_STALE_HOURS = 20

    # ── HORIZON ROUTING ───────────────────────────────────────────────────────
    # Horizon router module — reads macro contract and routes signals to the
    # correct trading horizon bucket before any execution gate runs.
    # DTE thresholds: 1-5D (<=5 DTE), 6-10D (6-10 DTE), 11-20D (11-20 DTE).
    HORIZON_ROUTER = BASE_DIR / "macro_horizon_router.py"

    # DTE bucket definitions — used by router and EOD candidate engine
    DTE_BUCKET_1_5D   = (1,  5)    # short-term — GO_SELECTIVE when bullish_prob>=63%
    DTE_BUCKET_6_10D  = (6,  10)   # medium-term — GO_REDUCED, requires 1-5D confirmation
    DTE_BUCKET_11_20D = (11, 20)   # long-term — MONITOR_ONLY when prob<56%

    # Horizon size multipliers (applied on top of PSE sizing)
    HORIZON_SIZE = {"1_5d": 1.0, "6_10d": 1.0, "11_20d": 1.0}  # Informational only — sizing owned by PSE/router

    # SPRINT 1 — DIRECTION-AGNOSTIC DOCTRINE:
    # Macro regime is a SIZING MULTIPLIER ONLY. It must never block a direction.
    # A CALL candidate in a TRANSITIONAL_BEARISH regime gets smaller size.
    # A PUT candidate in a RISK_ON regime gets smaller size.
    # Neither is ever blocked purely by regime.
    # This table is consumed by run_horizon_router() and PSE.
    #
    # Format: {regime: {direction: size_multiplier}}
    # multiplier 1.0 = full PSE size. 0.5 = half. 0.25 = probe size.
    MACRO_DIRECTION_SIZING = {
        "BULL":                {"CALL": 1.00, "PUT": 0.25},
        "RISK_ON":             {"CALL": 1.00, "PUT": 0.25},
        "TRANSITIONAL":        {"CALL": 0.75, "PUT": 0.75},
        "TRANSITIONAL_BEARISH":{"CALL": 0.50, "PUT": 1.00},
        "RISK_OFF":            {"CALL": 0.25, "PUT": 1.00},
        "BEAR":                {"CALL": 0.25, "PUT": 1.00},
    }
    MACRO_DIRECTION_SIZING_DEFAULT = {"CALL": 0.75, "PUT": 0.75}  # unknown regime

    # SPRINT 2 — FIXED FRACTIONAL SIZING TABLE
    # Replaces Kelly sizing for current pipeline maturity.
    # EV values are too small (0.0002-0.0098) for Kelly fractions to produce
    # meaningful sizes. Kelly remains the long-term target once EV is calibrated.
    # These values are consumed by MVE execution_decision_with_trigger().
    FIXED_FRACTIONAL_SIZE = {
        "EXECUTE": 1.0,    # full R — confirmed structure + live tape
        "PROBE":   0.5,    # half R — partial confirmation or no_match neutral prior
        "WATCH":   0.0,    # no position — awaiting trigger
        "BLOCK":   0.0,    # no position — hard reject
    }

    # Put permission VIX threshold — DEPRECATED Sprint 1.
    # Retained as 0.0 so legacy code reading it does not block PUTs.
    PUT_PERMISSION_VIX_THRESHOLD = 0.0

    # Phase 9C — Trade Book Builder
    # Must match account_size passed to run_enhancement_layer() in Phase 9B.
    ACCOUNT_SIZE   = 50_000   # Live Tastytrade account (matches Phase 9B: account_size=50000)
    MAX_POSITIONS  = 5        # Maximum trades selected per cycle
    MAX_PROBE_POS  = 3        # Maximum PROBE / pse_miss_flag trades within MAX_POSITIONS

    # Retention: number of evening runs to keep in data/output/runs/
    RUNS_RETENTION_DAYS = 90


cfg = OrchestratorConfig()


# ============================================================ PHASE 0: UNIVERSE SCANNER CONSUMER

def load_scanner_manifest() -> dict:
    """Phase 0 — Read universe scanner manifest if present and fresh."""
    empty = {
        "available": False, "go_new": [], "go_known": [],
        "probe_new": [], "probe_known": [], "all_new": [],
        "vms_df": None, "run_id": None, "timestamp_utc": None,
        "age_hrs": None, "tiers_run": [],
    }
    if not cfg.UNIVERSE_SCANNER_MANIFEST.exists():
        logger.info("Phase 0: No scanner manifest — pipeline runs without scanner input")
        return empty
    try:
        with open(cfg.UNIVERSE_SCANNER_MANIFEST, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        ts      = datetime.fromisoformat(manifest["timestamp"])
        age_hrs = (datetime.now(timezone.utc).replace(tzinfo=None) - ts.replace(tzinfo=None)).total_seconds() / 3600
        max_age = manifest.get("max_age_hours", cfg.SCANNER_MAX_AGE_HOURS)
        if age_hrs > max_age:
            logger.warning("Phase 0: Scanner manifest %.1fh old (max=%dh) — stale", age_hrs, max_age)
            return empty
        go_new      = manifest.get("go_new", [])
        go_known    = manifest.get("go_known", [])
        probe_new   = manifest.get("probe_new", [])
        probe_known = manifest.get("probe_known", [])
        all_new     = list(dict.fromkeys(go_new + probe_new))
        import pandas as _pd
        vms_path = Path(manifest.get("files", {}).get("vms_scoreboard", ""))
        vms_df   = _pd.read_csv(vms_path) if vms_path.exists() else None
        logger.info("=" * 70)
        logger.info("PHASE 0: UNIVERSE SCANNER CONSUMER")
        logger.info("=" * 70)
        logger.info("   Manifest age: %.1fh | tiers=%s | run_id=%s",
                    age_hrs, manifest.get("tiers_run", []), manifest.get("run_id", "?"))
        logger.info("   GO new=%d known=%d | PROBE new=%d known=%d",
                    len(go_new), len(go_known), len(probe_new), len(probe_known))
        logger.info("   %d NEW tickers injected into discovery", len(all_new))
        logger.info("\u2705 Phase 0: Scanner output loaded\n")
        return {
            "available": True, "go_new": go_new, "go_known": go_known,
            "probe_new": probe_new, "probe_known": probe_known, "all_new": all_new,
            "vms_df": vms_df, "run_id": manifest.get("run_id"),
            "timestamp_utc": manifest.get("timestamp"),
            "age_hrs": round(age_hrs, 1), "tiers_run": manifest.get("tiers_run", []),
        }
    except Exception as e:
        logger.warning("Phase 0: Failed to load scanner manifest — %s", e)
        return empty


def _scanner_empty() -> dict:
    return {
        "available": False, "go_new": [], "go_known": [],
        "probe_new": [], "probe_known": [], "all_new": [],
        "vms_df": None, "run_id": None, "timestamp_utc": None,
        "age_hrs": None, "tiers_run": [],
    }


def _ordered_unique_strings(values) -> list:
    seen = set()
    out = []
    for value in values or []:
        ticker = str(value or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def _pipeline_universe_set() -> set:
    try:
        import pandas as _pd
        if not cfg.UNIVERSE_FILE.exists():
            logger.warning("Phase 0: Pipeline universe missing for manual upload duplicate check: %s", cfg.UNIVERSE_FILE)
            return set()
        df = _pd.read_csv(cfg.UNIVERSE_FILE)
        if df.empty:
            return set()
        return {
            str(t).strip().upper()
            for t in df.iloc[:, 0].dropna().tolist()
            if str(t).strip()
        }
    except Exception as e:
        logger.warning("Phase 0: Manual upload duplicate check failed - %s", e)
        return set()


def load_manual_ticker_upload() -> dict:
    """
    Retired raw ticker-only upload.

    Catalyst calendar is now the governed manual/GPT intake contract. Keep this
    function as a no-op for compatibility with older orchestration flow/tests.
    """
    path = cfg.MANUAL_TICKER_UPLOAD_FILE
    if path.exists():
        logger.info(
            "Phase 0: Manual ticker upload retired and ignored: %s. "
            "Use dropbox/inputs/catalyst_calendar_latest.csv for manual/GPT intake.",
            path,
        )
    return _scanner_empty()


def merge_scanner_inputs(scanner: dict, manual: dict) -> dict:
    """Merge scanner output with manual raw-ticker upload without changing scanner scores."""
    if not manual.get("available"):
        return scanner
    if not scanner.get("available"):
        return manual

    merged = dict(scanner)
    for key in ("go_new", "go_known", "probe_new", "probe_known"):
        merged[key] = _ordered_unique_strings((scanner.get(key) or []) + (manual.get(key) or []))
    merged["all_new"] = _ordered_unique_strings((scanner.get("all_new") or []) + (manual.get("all_new") or []))
    merged["tiers_run"] = _ordered_unique_strings((scanner.get("tiers_run") or []) + (manual.get("tiers_run") or []))
    merged["run_id"] = f"{scanner.get('run_id') or 'scanner'}+manual_upload"
    ages = [x for x in [scanner.get("age_hrs"), manual.get("age_hrs")] if x is not None]
    merged["age_hrs"] = min(ages) if ages else None

    try:
        import pandas as _pd
        frames = [df for df in [scanner.get("vms_df"), manual.get("vms_df")] if df is not None]
        if frames:
            merged["vms_df"] = (
                _pd.concat(frames, ignore_index=True)
                .drop_duplicates(subset=["ticker"], keep="first")
                .reset_index(drop=True)
            )
    except Exception as e:
        logger.warning("Phase 0: Scanner/manual context merge degraded - %s", e)

    logger.info(
        "Phase 0: Scanner + manual upload merged | scanner_new=%d manual_new=%d total_new=%d",
        len(scanner.get("all_new") or []),
        len(manual.get("all_new") or []),
        len(merged.get("all_new") or []),
    )
    return merged


def build_augmented_universe(scanner: dict, pipeline_run_id: str) -> Optional[Path]:
    """Phase 0 — Prepend NEW scanner tickers to pipeline universe for this run only."""
    if not scanner["available"] or not scanner["all_new"]:
        return None
    try:
        import pandas as _pd
        if not cfg.UNIVERSE_FILE.exists():
            return None
        existing     = _pd.read_csv(cfg.UNIVERSE_FILE)
        existing_set = set(existing.iloc[:, 0].dropna().str.strip().tolist())
        truly_new    = [t for t in scanner["all_new"] if t not in existing_set]
        if not truly_new:
            return None
        new_rows  = _pd.DataFrame({existing.columns[0]: truly_new})
        augmented = _pd.concat([new_rows, existing], ignore_index=True)
        aug_dir   = cfg.RUNS_DIR / pipeline_run_id / "universe"
        aug_dir.mkdir(parents=True, exist_ok=True)
        aug_path  = aug_dir / f"scanner_augmented_universe_{pipeline_run_id}.csv"
        augmented.to_csv(aug_path, index=False)
        logger.info("Phase 0: Augmented universe — %d NEW tickers | total=%d", len(truly_new), len(augmented))
        return aug_path
    except Exception as e:
        logger.warning("Phase 0: Universe augmentation failed — %s", e)
        return None


def write_scanner_context(scanner: dict, pipeline_run_id: str) -> None:
    """Phase 0 — Write scanner_context_{run_id}.json for downstream VMS field access."""
    if not scanner["available"] or scanner["vms_df"] is None:
        return
    try:
        ctx_dir  = cfg.RUNS_DIR / pipeline_run_id
        ctx_dir.mkdir(parents=True, exist_ok=True)
        vms_df   = scanner["vms_df"]
        qualified = vms_df[vms_df["decision"].isin(["GO", "PROBE"])]
        context  = {
            "scanner_run_id": scanner.get("run_id"),
            "scanner_source": "UNIVERSE_SCANNER",
            "scanner_timestamp_utc": scanner.get("timestamp_utc"),
            "scanner_age_hrs": scanner.get("age_hrs"),
            "tiers_run": scanner.get("tiers_run", []),
            "tickers": {}
        }
        for _, row in qualified.iterrows():
            ticker = str(row.get("ticker", "")).strip()
            if ticker:
                # FIX-04A (2026-05-02): Capture ALL VMS fields.
                # Design principle: capture once in scanner, flow through pipeline.
                # options_intelligence reads these from signal_row — no re-fetch.
                def _fv(k, d=0.0):
                    v = row.get(k, d)
                    try: return float(v) if v is not None else d
                    except: return d
                context["tickers"][ticker] = {
                    "scanner_source":      "UNIVERSE_SCANNER",
                    "scanner_run_id":      scanner.get("run_id"),
                    "scanner_timestamp_utc": scanner.get("timestamp_utc"),
                    "scanner_age_hrs":     scanner.get("age_hrs"),
                    "scanner_signal_type": str(row.get("decision", "UNKNOWN")),
                    "scanner_decision":    str(row.get("decision", "UNKNOWN")),
                    "scanner_direction":   str(row.get("direction", "")),
                    "scanner_direction_reason": str(row.get("direction_reason", "")),
                    "scanner_score":       int(row.get("score", 0)),
                    "scanner_confidence":  round(max(0.0, min(1.0, _fv("score") / 100.0)), 4),
                    "scanner_data_quality": "CONFIRMED",
                    "scanner_reason_codes": str(row.get("reason_codes", "")),
                    "scanner_pattern_tags": str(row.get("pattern_tags", "")),
                    "scanner_sector":      str(row.get("sector", "")),
                    "scanner_price":       _fv("price"),
                    "scanner_volume":      _fv("volume"),
                    "scanner_rvol":        _fv("rvol"),
                    "scanner_watchlist_lane": str(row.get("pipeline_tag", "UNKNOWN")),
                    "vms_score":          int(row.get("score", 0)),
                    "vms_decision":       str(row.get("decision", "")),
                    "vol_spread":         _fv("vol_spread"),
                    "iv_rank":            _fv("iv_rank"),
                    "iv_rank_source":     str(row.get("iv_rank_source", "UNKNOWN")),
                    "iv_rank_confidence": _fv("iv_rank_confidence", 0.65),
                    "iv_current":         _fv("iv"),        # ATM IV from scanner
                    "rv":                 _fv("rv"),         # realised vol
                    "hv_30d":             _fv("rv"),         # alias: rv = hv_30d
                    "term_slope":         _fv("term_slope"), # front vs back IV slope
                    "skew":               _fv("skew"),       # put - call IV
                    "pipeline_tag":       str(row.get("pipeline_tag", "UNKNOWN")),
                }
        with open(ctx_dir / f"scanner_context_{pipeline_run_id}.json", "w", encoding="utf-8") as f:
            json.dump(context, f, indent=2)
        logger.info("Phase 0: Scanner context written — %d GO/PROBE tickers", len(context["tickers"]))
    except Exception as e:
        logger.warning("Phase 0: Could not write scanner context (non-critical): %s", e)


# ============================================================ PRE-FLIGHT =====

def check_universe(min_universe: int, target_universe: int, mode: str) -> Tuple[bool, int, str]:
    """
    Verify universe file exists and has viable size.

    Modes:
      HARD:  fail if n < target_universe
      SOFT:  fail if n < min_universe (ignore target)
      AUTO:  fail if n < min_universe; warn if n < target_universe (recommended)

    Returns (ok, n, message). In AUTO mode, WARN returns ok=True.
    """
    if not cfg.UNIVERSE_FILE.exists():
        return False, 0, f"Universe file not found: {cfg.UNIVERSE_FILE}"

    try:
        with open(cfg.UNIVERSE_FILE, "r", encoding="utf-8-sig", newline="") as f:
            n = sum(1 for _ in csv.DictReader(f))

        if n <= 0:
            return False, 0, "Universe empty: 0 tickers"

        mode = (mode or "AUTO").strip().upper()

        if mode == "HARD":
            if n < target_universe:
                return False, n, f"Universe too small: {n} tickers (expected ≥ {target_universe})"
            return True, n, f"Universe OK: {n} tickers (≥ {target_universe})"

        if mode == "SOFT":
            if n < min_universe:
                return False, n, f"Universe too small: {n} tickers (minimum ≥ {min_universe})"
            return True, n, f"Universe OK: {n} tickers (minimum ≥ {min_universe})"

        # AUTO (default): min is fail gate; target is warning gate
        if n < min_universe:
            return False, n, f"Universe too small: {n} tickers (minimum ≥ {min_universe})"

        if n < target_universe:
            return True, n, f"Universe smaller than target: {n} tickers (target ≥ {target_universe}) — proceeding"

        return True, n, f"Universe OK: {n} tickers (≥ {target_universe})"

    except Exception as e:
        return False, 0, f"Error reading universe: {e}"


def check_scripts() -> Tuple[bool, List[str]]:
    """Verify every required script exists.

    VANGUARD pipeline scripts are hard-required — preflight aborts if any are missing.
    POSITION_TRACKER and PREMARKET_INTEL are optional — their run functions handle
    absence gracefully, so they must NOT block preflight.
    """
    required = {
        "Discovery ULTIMATE":  cfg.DISCOVERY_ULTIMATE,
        "Build Packages":      cfg.BUILD_PACKAGES,
        "Inject Macro":        cfg.INJECT_MACRO,
        "Backfill Timeseries": cfg.BACKFILL_TIMESERIES,
        "Run VANGUARD":        cfg.RUN_VANGUARD,
    }
    optional = {
        "Position Tracker":          cfg.POSITION_TRACKER,
        "Premarket Intel":           cfg.PREMARKET_INTEL,
        "Options Intel":             cfg.OPTIONS_INTEL,
        "External Intel Review Lane": cfg.APPLY_EXTERNAL_INTEL_REVIEW_LANE,
        "Macro Enrichment Discovery": cfg.APPLY_MACRO_ENRICHMENT_DISCOVERY,
        "Core Intel Exporter":       cfg.CORE_INTEL_EXPORTER,
        # "Super Brain Layer": removed 2026-04-28 (migrated to OI)
        "Monetisation Policy":       cfg.MONETISATION_POLICY,
        "EIL Runner":                cfg.EIL_RUNNER,
        "Execution Gate":            cfg.EXECUTION_GATE,
        "EOD Candidate Engine":      cfg.EOD_CANDIDATE_ENGINE,
        "Morning Validation":        cfg.MORNING_VALIDATION_ENGINE,
        "Execution Decision Engine": cfg.EDE_ENGINE,
        "Actuarial Cache Builder":   cfg.ACTUARIAL_CACHE_BUILDER,
        "Actuarial Enrichment Pass": cfg.ACTUARIAL_ENRICHMENT_PASS,
        "Universe Scanner":          cfg.UNIVERSE_SCANNER_SCRIPT,
    }

    missing = [f"{name}: {path}" for name, path in required.items() if not path.exists()]

    # Log found/missing for every optional script so preflight shows the full picture.
    logger.info("  Optional scripts:")
    for name, path in optional.items():
        if path.exists():
            logger.info(f"   ✅ {name}: found")
        else:
            logger.warning(f"   ⚠️  {name}: NOT FOUND (will skip at runtime) — deploy {path.name}")

    # Log required script status too
    logger.info("  Required scripts:")
    for name, path in required.items():
        if path.exists():
            logger.info(f"   ✅ {name}: found")
        else:
            logger.error(f"   ❌ {name}: MISSING — {path}")

    return len(missing) == 0, missing


def _flatten_macro(data: dict) -> dict:
    """
    Resolve required fields from the macro JSON regardless of nesting depth.
    Canonical keys win over alias keys; deepest occurrence wins.
    """
    ALIASES = {
        "risk_on_off_switch": "risk_on_switch",
        "vol_mode":           "volatility_mode",
        "liquidity_pulse":    "liquidity_status",
    }
    canonical_vals: dict = {}
    alias_vals: dict = {}

    def _walk(node: dict) -> None:
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if k in ALIASES:
                alias_vals[ALIASES[k]] = v
            else:
                canonical_vals[k] = v
            if isinstance(v, dict):
                _walk(v)

    _walk(data)
    merged = {**alias_vals, **canonical_vals}
    return merged


def _derive_regime_distribution(regime_state: str, regime_drift_status: str = "") -> dict:
    """Derive a bull/neutral/bear distribution when regime_distribution is absent."""
    try:
        from contracts.macro_regime_safety import derive_regime_distribution

        return derive_regime_distribution(regime_state, regime_drift_status)
    except Exception:
        rs = str(regime_state).strip().upper()
        drift = str(regime_drift_status).strip().upper()
        if rs in {"TRANSITIONAL", "UNKNOWN", "MIXED", "CHOPPY_NEUTRAL", "NEUTRAL"} and drift:
            if drift == "DRIFTING_NEUTRAL" or ("NEUTRAL" in drift and "BEAR" not in drift and "BULL" not in drift):
                return {"bull": 0.30, "neutral": 0.40, "bear": 0.30}
            if any(d in drift for d in ("BULL", "IMPROVING", "RISK_ON", "ACCELERATING_UP")):
                return {"bull": 0.45, "neutral": 0.35, "bear": 0.20}
            if any(d in drift for d in ("BEAR", "DETERIORATING", "RISK_OFF")):
                return {"bull": 0.20, "neutral": 0.35, "bear": 0.45}
            if any(d in drift for d in ("STABLE", "SIDEWAYS", "BALANCED")):
                return {"bull": 0.30, "neutral": 0.40, "bear": 0.30}
        return {
            "TRENDING_BULL": {"bull": 0.75, "neutral": 0.20, "bear": 0.05},
            "RISK_ON": {"bull": 0.65, "neutral": 0.25, "bear": 0.10},
            "TRENDING_BEAR": {"bull": 0.05, "neutral": 0.20, "bear": 0.75},
            "RISK_OFF": {"bull": 0.10, "neutral": 0.25, "bear": 0.65},
            "TRANSITIONAL_NEUTRAL": {"bull": 0.30, "neutral": 0.40, "bear": 0.30},
            "TRANSITIONAL_BULLISH": {"bull": 0.45, "neutral": 0.35, "bear": 0.20},
            "TRANSITIONAL_BEARISH": {"bull": 0.20, "neutral": 0.35, "bear": 0.45},
        }.get(rs, {"bull": 0.33, "neutral": 0.34, "bear": 0.33})


def check_macro_json() -> Tuple[bool, str, Optional[Path]]:
    """Verify macro_intelligence_latest.json exists, is valid, and contains required fields."""
    if not cfg.MACRO_DIR.exists():
        return (
            False,
            f"Macro drop folder not found: {cfg.MACRO_DIR}\n"
            f"   Create the folder and drop macro_intelligence_latest.json into it.",
            None,
        )

    macro_file = cfg.MACRO_FILE
    if not macro_file.exists():
        return (
            False,
            f"Macro file not found: {macro_file}\n"
            f"   Drop your latest macro JSON as:\n"
            f"   {macro_file}",
            None,
        )

    try:
        with open(macro_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error in {macro_file.name}: {e}", None

    flat = _flatten_macro(data)

    required_fields = [
        "risk_on_switch", "regime_state", "dir_bias", "regime_drift_status",
        "conviction_score", "macro_conviction", "liquidity_status",
        "volatility_mode", "vix_contango", "report_date", "as_of_utc",
    ]
    missing_fields = [f for f in required_fields if f not in flat]
    if missing_fields:
        return False, (
            f"Macro JSON missing required fields: {missing_fields}\n"
            f"   Checked top-level and all nested dicts (including extras.extras.extras).\n"
            f"   File: {macro_file}"
        ), None

    # Staleness warning (non-blocking)
    # SPRINT 1: Validate INTERNAL generated_at/as_of_utc timestamp, not file mtime.
    # A file can be re-saved without content change and still pass an mtime check.
    # We read the timestamp from inside the JSON — this is the only reliable source.
    try:
        # Prefer generated_at if present (more explicit than as_of_utc)
        _ts_field = flat.get("generated_at") or flat.get("as_of_utc")
        as_of = datetime.fromisoformat(str(_ts_field).replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - as_of).total_seconds() / 3600
        if age_h > cfg.MACRO_STALE_HOURS:
            return (
                True,
                f"WARNING -- macro is {age_h:.0f}h old ({macro_file.name}). Consider updating before running.",
                macro_file,
            )
    except Exception:
        pass

    # Derive regime distribution if absent (logging only)
    try:
        regime_val = flat.get("regime_state", "TRANSITIONAL")
        drift_val = flat.get("regime_drift_status", "")
        regime_distribution = flat.get("regime_distribution", None)

        if regime_distribution is None:
            regime_distribution = _derive_regime_distribution(regime_val, drift_val)
            logger.info(
                "   Regime dist   : derived from regime_state+drift  bull=%.0f%%  neutral=%.0f%%  bear=%.0f%%",
                regime_distribution["bull"] * 100,
                regime_distribution["neutral"] * 100,
                regime_distribution["bear"] * 100,
            )
        else:
            logger.info(
                "   Regime dist   : from JSON  bull=%.0f%%  neutral=%.0f%%  bear=%.0f%%",
                regime_distribution.get("bull", 0) * 100,
                regime_distribution.get("neutral", 0) * 100,
                regime_distribution.get("bear", 0) * 100,
            )
    except Exception:
        pass

    return True, f"Macro JSON OK: {macro_file.name}", macro_file


def run_preflight_checks(min_universe: int, target_universe: int, universe_gate_mode: str) -> Tuple[bool, Optional[Path]]:
    """Run all pre-flight checks. Returns (all_ok, macro_path)."""
    logger.info("🔍 Running pre-flight checks...")
    all_ok = True
    macro_path: Optional[Path] = None

    # Universe (dynamic gate)
    universe_ok, _, msg = check_universe(
        min_universe=min_universe,
        target_universe=target_universe,
        mode=universe_gate_mode,
    )
    if "proceeding" in msg.lower() or "smaller than target" in msg.lower():
        logger.warning(f"   Universe      : {msg}")
    else:
        logger.info(f"   Universe      : {msg}")
    if not universe_ok:
        all_ok = False

    # Scripts
    scripts_ok, missing_scripts = check_scripts()
    if not scripts_ok:
        for m in missing_scripts:
            logger.error(f"   ❌ Missing     : {m}")
        all_ok = False
    else:
        logger.info("   Scripts       : All present")

    # Macro JSON
    macro_ok, macro_msg, macro_path = check_macro_json()
    if not macro_ok:
        logger.error(f"   ❌ Macro JSON  : {macro_msg}")
        all_ok = False
    else:
        logger.info(f"   Macro JSON    : {macro_msg}")

    if not all_ok:
        logger.error("❌ Pre-flight FAILED — fix issues above then re-run\n")
        return False, None

    # Ensure output directories exist
    cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    cfg.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("   Directories   : OK")
    logger.info("✅ Pre-flight checks PASSED\n")
    return True, macro_path


# ============================================================ HELPERS ========

def _run(label: str, cmd: List[str], critical: bool = True) -> bool:
    """Run a subprocess and stream output line-by-line (deadlock-proof on Windows)."""
    logger.info(f"▶  {label}")
    logger.info(f"   CMD: {' '.join(str(c) for c in cmd)}")
    try:
        import os as _os
        import re as _re
        _child_env = _os.environ.copy()
        _child_env["PYTHONUTF8"] = "1"
        _child_env["PYTHONIOENCODING"] = "utf-8"
        _child_env["PYTHONUNBUFFERED"] = "1"
        # Ensure API keys propagate even if shell didn't export them
        for _key in ("POLYGON_API_KEY", "MARKETDATA_API_KEY"):
            if _key in _os.environ and _key not in _child_env:
                _child_env[_key] = _os.environ[_key]
        # v1.1: propagate sector_bias_map as JSON env var so all subprocesses
        # can read it without re-parsing the macro JSON
        if _sector_bias_map:
            _child_env["AVSHUNTER_SECTOR_BIAS_MAP"]    = json.dumps(_sector_bias_map)
            _child_env["AVSHUNTER_MACRO_CONVICTION"]   = str(_macro_conviction)
            _child_env["AVSHUNTER_MACRO_REGIME_STATE"] = _macro_regime_state
        if _macro_quant_packet:
            _child_env["AVSHUNTER_MACRO_QUANT_PACKET"] = json.dumps(_macro_quant_packet, default=str)
            _child_env["AVSHUNTER_MACRO_FRESHNESS_STATUS"] = str(
                _macro_quant_packet.get("macro_freshness_status", "UNKNOWN")
            )

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cfg.BASE_DIR),
            env=_child_env,
        )

        def _dedupe_key(text: str) -> str:
            cleaned = "".join(ch for ch in text if ch.isprintable()).strip()
            cleaned = _re.sub(
                r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d{3})?\s+-\s+\w+\s+-\s+",
                "",
                cleaned,
            )
            cleaned = _re.sub(r"^\d{2}:\d{2}:\d{2}\s+\[[^\]]+\]\s+", "", cleaned)
            return _re.sub(r"\s+", " ", cleaned)

        last_child_key = None
        for line in proc.stdout:
            child_line = line.rstrip()
            child_key = _dedupe_key(child_line)
            if child_key == last_child_key:
                continue
            last_child_key = child_key
            logger.info(f"   | {child_line}")

        proc.wait()

        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)

        logger.info(f"✅ {label} — DONE\n")
        return True

    except subprocess.CalledProcessError as e:
        if critical:
            logger.error(f"❌ {label} — FAILED (exit {e.returncode})\n")
        else:
            logger.warning(f"⚠️  {label} — FAILED (non-critical, exit {e.returncode})\n")
        return False


# ============================================================ PHASE 1B: HORIZON ROUTER

def run_horizon_router(macro_path: Path, run_id: str) -> dict:
    """
    Phase 1B — Macro Horizon Router.

    Reads the macro contract and stamps every candidate signal with a horizon
    bucket: 1_5d / 6_10d / 11_20d. Writes three filtered CSVs so downstream
    phases (EIL, EDE, EOD Candidate Engine) can apply the correct macro bias,
    size multiplier, and confirmation gates per horizon.

    Inputs:
        macro_path  — cfg.MACRO_FILE (already normalised by Phase FIX-04)
        run_id      — canonical run ID from discovery

    Outputs (written to data/output/runs/{run_id}/horizon/):
        horizon_1_5d_{run_id}.csv    — 1-5D signals: GO_SELECTIVE, size=1.0×PSE
        horizon_6_10d_{run_id}.csv   — 6-10D signals: GO_REDUCED,  size=0.70×PSE
        horizon_11_20d_{run_id}.csv  — 11-20D signals: MONITOR_ONLY, size=0
        horizon_blocked_{run_id}.csv — signals blocked by macro router
        horizon_summary_{run_id}.json — counts + macro bias snapshot

    The function is NON-CRITICAL — if the router module is not deployed or
    fails, the pipeline continues using the legacy single-bucket behaviour.
    The horizon_bucket column is patched into superbrain_enriched.csv so the
    EIL and EDE can read it without any schema changes.
    """
    logger.info("=" * 80)
    logger.info("PHASE 1B: MACRO HORIZON ROUTER")
    logger.info("=" * 80)

    if not cfg.HORIZON_ROUTER.exists():
        logger.warning(
            "⏭️  Horizon Router skipped — macro_horizon_router.py not deployed at: %s\n"
            "   Deploy macro_horizon_router.py to BASE_DIR to enable horizon-bucketed routing.\n"
            "   Pipeline continues in legacy single-bucket mode.",
            cfg.HORIZON_ROUTER,
        )
        return {"success": False, "reason": "router_not_deployed", "legacy_mode": True}

    try:
        import importlib.util as _ilu
        _hr_spec = _ilu.spec_from_file_location("macro_horizon_router", str(cfg.HORIZON_ROUTER))
        _hr_mod  = _ilu.module_from_spec(_hr_spec)
        # FIX-IMPORT-01: register module in sys.modules BEFORE exec_module.
        # Python 3.12 dataclasses._process_class() calls:
        #   sys.modules.get(cls.__module__).__dict__
        # to resolve forward-referenced type hints on Enum-typed fields.
        # If the module is not yet in sys.modules when exec_module runs,
        # that lookup returns None → AttributeError: 'NoneType' object has
        # no attribute '__dict__'. This is the actual root cause of the
        # Phase 1B crash — not the _raw field access fixed earlier.
        import sys as _sys
        _sys.modules["macro_horizon_router"] = _hr_mod
        _hr_spec.loader.exec_module(_hr_mod)

        # ── Load macro to extract horizon biases for logging ──────────────────
        with open(macro_path, "r", encoding="utf-8") as _f:
            _macro = json.load(_f)

        _biases = _hr_mod.extract_horizon_biases(_macro)
        for _hkey, _bias in _biases.items():
            logger.info(
                "   Horizon %-8s: %-15s  prob=%.1f%%  size=%.2f  action=%s",
                _hkey, _bias.direction, _bias.bullish_prob_pct,
                _bias.size_multiplier, _bias.action.value,
            )

        # ── Load discovery candidates ─────────────────────────────────────────
        import csv as _csv
        # FIX-HORIZON-INPUT: Router must read OI-enriched CSV (has real contract_dte).
        # Discovery CSV has no DTE — every signal blocks as INVALID_DTE.
        # OI runs before Phase 1B so vanguard_signals_enriched already exists.
        # Fallback chain: OI-enriched → options_intelligence → discovery (last resort).
        _oi_enriched_csv   = cfg.RUNS_DIR / run_id / "options" / f"vanguard_signals_enriched_{run_id}.csv"
        _oi_csv            = cfg.RUNS_DIR / run_id / "options" / f"options_intelligence_{run_id}.csv"
        _disc_csv_fallback = cfg.OUTPUT_DIR / f"discovery_candidates_ultimate_{run_id}.csv"

        if _oi_enriched_csv.exists() and _oi_enriched_csv.stat().st_size > 200:
            _disc_csv = _oi_enriched_csv
            logger.info("   Horizon Router input: OI-enriched CSV (real DTE available)")
        elif _oi_csv.exists() and _oi_csv.stat().st_size > 200:
            _disc_csv = _oi_csv
            logger.info("   Horizon Router input: options_intelligence CSV (fallback)")
        else:
            _disc_csv = _disc_csv_fallback
            logger.warning("   Horizon Router input: discovery CSV — no DTE, signals will block")
            if not _disc_csv.exists():
                _matches = list(cfg.OUTPUT_DIR.glob(f"discovery_candidates*{run_id}*.csv"))
                _disc_csv = _matches[0] if _matches else None

        if _disc_csv is None or not _disc_csv.exists():
            logger.warning(
                "⚠️  Horizon Router: discovery CSV not found for run %s — "
                "router will log biases only, no horizon CSVs written.",
                run_id,
            )
            return {
                "success": True,
                "reason": "no_discovery_csv",
                "biases": {k: v.action.value for k, v in _biases.items()},
                "legacy_mode": True,
            }

        with open(_disc_csv, "r", encoding="utf-8-sig", newline="") as _f:
            _reader = _csv.DictReader(_f)
            _candidates = list(_reader)
            _fieldnames = _reader.fieldnames or []

        if not _candidates:
            logger.warning("⚠️  Horizon Router: discovery CSV is empty — no signals to route")
            return {"success": True, "reason": "empty_discovery", "legacy_mode": True}

        # Phase 1B should only route option-scoped candidates. The OI-enriched
        # Vanguard file intentionally carries NOT_SCOPED names for audit
        # continuity, but those rows have no selected contract, no option
        # direction, and therefore no real DTE to validate. Sending them through
        # the router creates false INVALID_DTE blocks for names that were never
        # eligible for options routing.
        _excluded_not_scoped = 0
        if "options_verdict" in _fieldnames:
            _routeable_candidates = []
            for _row in _candidates:
                _ov = str(_row.get("options_verdict", "") or "").strip().upper()
                if _ov == "NOT_SCOPED":
                    _excluded_not_scoped += 1
                    continue
                _routeable_candidates.append(_row)

            if _excluded_not_scoped:
                logger.info(
                    "   Horizon Router excluded %d NOT_SCOPED rows (no option contract/DTE)",
                    _excluded_not_scoped,
                )
            _candidates = _routeable_candidates

        if not _candidates:
            logger.warning(
                "âš ï¸  Horizon Router: no option-scoped candidates after NOT_SCOPED filter"
            )
            return {"success": True, "reason": "no_option_scoped_candidates", "legacy_mode": True}

        # ── Route each candidate ──────────────────────────────────────────────
        # PATCH 3: Do NOT invent DTE defaults here. The router owns DTE validation.
        # Old code: int(float(_row.get("dte", 0) or _row.get("days_to_expiry", 7)))
        # laundered missing DTE into 7 before the router saw it, defeating the
        # BLOCK_INVALID_DTE gate added to the router. Pass raw values and let the
        # router decide.
        # PATCH 4: _first_present() helper avoids silent string coercion.
        _signals = []

        def _first_present(_row: dict, _keys: list, _default=None):
            for _k in _keys:
                _v = _row.get(_k)
                if _v not in (None, "", "nan", "NaN", "N/A", "NONE", "None"):
                    return _v
            return _default

        for _row in _candidates:
            _ticker = str(_row.get("ticker", "")).strip().upper()

            _instrument = _first_present(
                _row,
                ["instrument", "options_direction", "strategy_type", "direction"],
                "CALL",
            )

            # PATCH 3: pass raw DTE — None means missing → router blocks cleanly
            _dte_raw = _first_present(
                _row,
                ["contract_dte", "dte", "days_to_expiry", "DTE"],
                None,
            )

            _hold_raw = _first_present(
                _row,
                ["expected_holding_days", "hold_days", "horizon_days"],
                None,
            )

            _ltr_raw = _first_present(
                _row,
                ["ltr_result", "ltr_verdict", "trigger_go_eligible", "llr_result", "llr_true", "ltr_true"],
                False,
            )

            _phase_raw = _first_present(
                _row,
                ["phase_best", "wyckoff_phase", "wyckoff_phase_bucket", "phase_d_confirmed", "trigger_quality"],
                "",
            )
            _phase_str = str(_phase_raw).strip().upper()
            _phase_d_confirmed = _phase_str in (
                "D", "E", "PHASE_D", "PHASE_E", "STRONG", "SINGLE", "MARKDOWN", "DISTRIBUTION"
            )

            _vix_raw = _first_present(
                _row,
                ["vix_current", "vix_spot", "vix"],
                _macro.get("extras", {}).get("vix_spot", 18.0),
            )

            _signals.append({
                "ticker":                _ticker,
                "instrument":            _instrument,
                "dte":                   _dte_raw,          # PATCH 3: raw, not defaulted
                "expected_holding_days": _hold_raw,
                "ltr_true":              _ltr_raw,
                "phase_d_confirmed":     _phase_d_confirmed,
                "iv_regime":             _row.get("iv_regime", "UNKNOWN"),
                "vix_current":           _vix_raw,
                "_raw":                  _row,
            })

        _routed = _hr_mod.route_signals_by_horizon(macro_path, _signals)

        # ── Write horizon CSVs ────────────────────────────────────────────────
        _out_dir = cfg.RUNS_DIR / run_id / "horizon"
        _out_dir.mkdir(parents=True, exist_ok=True)
        _horizon_regime_state = str(_macro.get("regime_state", "") or "")
        _horizon_macro_conviction = float(_macro.get("macro_conviction", 0) or 0)
        _horizon_macro_momentum = float(_macro.get("macro_momentum_score", 0) or 0)

        _counts = {}
        _extra_horizon_fields = [
            "signal_id", "horizon_bucket", "horizon_action",
            "horizon_size_multiplier", "horizon_block_reason",
            "horizon_source", "router_version", "horizon_regime_state",
            "horizon_macro_conviction", "horizon_macro_momentum_score",
        ]
        _all_fieldnames = list(dict.fromkeys(list(_fieldnames) + _extra_horizon_fields))

        # PATCH 4: ticker→raw dict is collision-unsafe when same ticker has CALL + PUT.
        # This lookup is best-effort — downstream merge uses signal_id for exact matching.
        _ticker_to_raw = {s["ticker"]: s["_raw"] for s in _signals if s.get("ticker")}

        for _bucket, _bucket_signals in _routed.items():
            _out_path = _out_dir / f"horizon_{_bucket}_{run_id}.csv"
            with open(_out_path, "w", newline="", encoding="utf-8") as _f:
                _writer = _csv.DictWriter(_f, fieldnames=_all_fieldnames, extrasaction="ignore")
                _writer.writeheader()
                for _sig in _bucket_signals:
                    # Get original discovery row via ticker lookup (safe — no _raw on RoutedSignal)
                    _orig = _ticker_to_raw.get(_sig.ticker, {})
                    _out_row = dict(_orig)
                    _out_row["signal_id"]                = getattr(_sig, "signal_id", "")
                    _out_row["horizon_bucket"]           = _bucket
                    _out_row["horizon_action"]           = _sig.action.value
                    _out_row["horizon_size_multiplier"]  = _sig.size_multiplier
                    _out_row["horizon_block_reason"]     = _sig.block_reason
                    _out_row["horizon_source"]           = getattr(_sig, "horizon_source", "")
                    _out_row["router_version"]           = getattr(_sig, "router_version", "")
                    _out_row["horizon_regime_state"]     = _horizon_regime_state
                    _out_row["horizon_macro_conviction"] = _horizon_macro_conviction
                    _out_row["horizon_macro_momentum_score"] = _horizon_macro_momentum
                    _writer.writerow(_out_row)
            _counts[_bucket] = len(_bucket_signals)

        # ── Patch horizon_bucket into superbrain_enriched (if it already exists) ─
        _sb_path = cfg.RUNS_DIR / run_id / "superbrain" / f"superbrain_enriched_{run_id}.csv"
        if _sb_path.exists():
            try:
                import pandas as _pd
                _sb = _pd.read_csv(_sb_path)
                # Build lookup: ticker -> (bucket, size_multiplier)
                _lookup = {}
                for _bucket, _bucket_signals in _routed.items():
                    if _bucket == "blocked":
                        continue
                    for _sig in _bucket_signals:
                        # _sig is a RoutedSignal dataclass — access fields directly
                        _lookup[_sig.ticker] = {
                            "horizon_bucket":          _bucket,
                            "horizon_action":          _sig.action.value,
                            "horizon_size_multiplier": float(_sig.size_multiplier),
                            "horizon_regime_state":    _horizon_regime_state,
                            "horizon_macro_conviction": _horizon_macro_conviction,
                            "horizon_macro_momentum_score": _horizon_macro_momentum,
                        }
                if _lookup:
                    _sb["horizon_bucket"]          = _sb["ticker"].map(lambda t: _lookup.get(t, {}).get("horizon_bucket", "unrouted"))
                    _sb["horizon_action"]          = _sb["ticker"].map(lambda t: _lookup.get(t, {}).get("horizon_action", "UNKNOWN"))
                    _sb["horizon_size_multiplier"] = _sb["ticker"].map(lambda t: _lookup.get(t, {}).get("horizon_size_multiplier", 0.0))
                    _sb["horizon_regime_state"]    = _sb["ticker"].map(lambda t: _lookup.get(t, {}).get("horizon_regime_state", _horizon_regime_state))
                    _sb["horizon_macro_conviction"] = _sb["ticker"].map(lambda t: _lookup.get(t, {}).get("horizon_macro_conviction", _horizon_macro_conviction))
                    _sb["horizon_macro_momentum_score"] = _sb["ticker"].map(lambda t: _lookup.get(t, {}).get("horizon_macro_momentum_score", _horizon_macro_momentum))
                    # SPRINT 1: Stamp macro trust fields into every row so MVE can compute signal_trust_score
                    _sb["macro_age_hours"]    = _macro_age_h
                    _sb["macro_generated_at"] = _macro_ts
                    _sb.to_csv(_sb_path, index=False)
                    logger.info("   Patched horizon_bucket into superbrain_enriched (%d rows)", len(_sb))
            except Exception as _patch_err:
                logger.warning("⚠️  Could not patch horizon into superbrain: %s", _patch_err)

        # ── Write summary JSON ────────────────────────────────────────────────
        # SPRINT 1: Compute macro_age_hours and macro_generated_at for trust scoring.
        _macro_ts = str(_macro.get("generated_at") or _macro.get("as_of_utc") or "")
        _macro_age_h = -1.0
        try:
            _macro_dt = datetime.fromisoformat(_macro_ts.replace("Z", "+00:00"))
            _macro_age_h = round((datetime.now(timezone.utc) - _macro_dt).total_seconds() / 3600, 1)
        except Exception:
            pass

        _summary = {
            "run_id":      run_id,
            "as_of_utc":   str(_macro.get("as_of_utc", "")),
            "macro_generated_at":  _macro_ts,
            "macro_age_hours":     _macro_age_h,
            "regime_state": str(_macro.get("regime_state", "")),
            "macro_conviction": float(_macro.get("macro_conviction", 0)),
            "macro_momentum_score": float(_macro.get("macro_momentum_score", 0)),
            "horizon_counts": _counts,
            "horizon_biases": {
                k: {
                    "direction":        v.direction,
                    "bullish_prob_pct": v.bullish_prob_pct,
                    "action":           v.action.value,
                    "size_multiplier":  v.size_multiplier,
                }
                for k, v in _biases.items()
            },
            "put_vix_threshold": cfg.PUT_PERMISSION_VIX_THRESHOLD,
            # SPRINT 2 — Direction-agnostic sizing table.
            # The external macro_horizon_router.py reads this to apply
            # sizing multipliers per direction rather than blocking.
            # CALL and PUT are both surfaced in all regimes.
            "macro_direction_sizing": cfg.MACRO_DIRECTION_SIZING,
            "macro_direction_sizing_default": cfg.MACRO_DIRECTION_SIZING_DEFAULT,
        }
        _summary_path = _out_dir / f"horizon_summary_{run_id}.json"
        with open(_summary_path, "w", encoding="utf-8") as _f:
            json.dump(_summary, _f, indent=2)

        logger.info(
            "✅ Phase 1B (Horizon Router) — 1_5d=%d | 6_10d=%d | 11_20d=%d | blocked=%d",
            _counts.get("1_5d", 0),
            _counts.get("6_10d", 0),
            _counts.get("11_20d", 0),
            _counts.get("blocked", 0),
        )
        _hr_mod.log_routing_summary(_routed)
        return {"success": True, "counts": _counts, "biases": {k: v.action.value for k, v in _biases.items()}}

    except Exception as _hr_err:
        logger.warning(
            "⚠️  Phase 1B (Horizon Router) failed — pipeline continues in legacy mode. Error: %s",
            _hr_err,
        )
        return {"success": False, "reason": str(_hr_err), "legacy_mode": True}


# ============================================================ PHASE 1: DISCOVERY

def run_discovery(
    augmented_universe_path: Optional[Path] = None,
    scanner_context_path: Optional[Path] = None,
) -> Tuple[bool, Optional[dict], Optional[str]]:
    """Run ULTIMATE discovery script. Returns (ok, summary, discovery_run_id)."""
    logger.info("=" * 80)
    logger.info("PHASE 1: DISCOVERY")
    logger.info("=" * 80)

    universe_to_use = (augmented_universe_path
                       if augmented_universe_path and augmented_universe_path.exists()
                       else cfg.UNIVERSE_FILE)
    if augmented_universe_path and augmented_universe_path.exists():
        logger.info("   Universe: AUGMENTED (scanner tickers injected) → %s", universe_to_use.name)
    cmd = [
        sys.executable,
        str(cfg.DISCOVERY_ULTIMATE),
        "--universe", str(universe_to_use),
        "--progress-every", "100",
        "--force-update",
    ]

    # DISC-02: Pass scanner context so discovery can inject VMS scores into composite scoring.
    if scanner_context_path and scanner_context_path.exists():
        cmd += ["--scanner-context", str(scanner_context_path)]
        logger.info("   Scanner context: %s", scanner_context_path.name)

    ok = _run("Discovery ULTIMATE", cmd, critical=True)
    if not ok:
        return False, None, None

    summaries = sorted(cfg.OUTPUT_DIR.glob("discovery_summary_ultimate_*.json"))
    if not summaries:
        logger.error("❌ No discovery summary file found after run\n")
        return False, None, None

    latest_summary = summaries[-1]
    with open(latest_summary, "r", encoding="utf-8") as f:
        summary = json.load(f)

    stem = latest_summary.stem
    parts = stem.split("_")
    discovery_run_id = "_".join(parts[-2:])
    logger.info(f"📁 Discovery output timestamp: {discovery_run_id}")

    return True, summary, discovery_run_id


def apply_macro_enrichment_to_discovery(run_id: str, macro_path: Path) -> bool:
    """Stamp additive macro-enrichment context onto discovery for Options scoring."""
    discovery_csv = cfg.OUTPUT_DIR / f"discovery_candidates_ultimate_{run_id}.csv"
    if not discovery_csv.exists():
        logger.warning("Macro enrichment discovery stamp skipped: missing discovery CSV: %s", discovery_csv)
        return False
    if not cfg.APPLY_MACRO_ENRICHMENT_DISCOVERY.exists():
        logger.warning(
            "Macro enrichment discovery stamp skipped: script not deployed: %s",
            cfg.APPLY_MACRO_ENRICHMENT_DISCOVERY,
        )
        return True

    report_path = cfg.OUTPUT_DIR / "qa" / f"macro_enrichment_discovery_{run_id}.json"
    ok = _run(
        "Macro Enrichment -> Discovery",
        [
            sys.executable,
            str(cfg.APPLY_MACRO_ENRICHMENT_DISCOVERY),
            "--discovery-csv",
            str(discovery_csv),
            "--macro-path",
            str(macro_path),
            "--report-path",
            str(report_path),
        ],
        critical=False,
    )
    if ok:
        logger.info("Macro enrichment discovery stamp complete -> %s", report_path)
    else:
        logger.warning("Macro enrichment discovery stamp failed; Options will run without narrative bonus")
    return ok


def merge_macro_enrichment_into_macro_latest(macro_path: Path) -> bool:
    """
    Attach the GPT macro enrichment delta to macro_intelligence_latest.json before
    discovery. The merge is augment-only and cannot replace protected macro gates.
    """
    try:
        selected = find_macro_enrichment_delta(macro_path)
        if selected is None:
            logger.info("Macro enrichment pre-discovery merge skipped: no enrichment delta found")
            return True
        with open(macro_path, "r", encoding="utf-8") as fh:
            macro = json.load(fh)
        enrichment = load_macro_enrichment_delta(selected)
        merged = merge_macro_enrichment_delta(macro, enrichment)
        merged["macro_quant_packet"] = build_macro_quant_packet(merged, macro_path)
        write_json(macro_path, merged)
        exposure_count = len(
            ((merged.get("extras") or {}).get("macro_exposure_index") or {})
            if isinstance(merged.get("extras"), dict)
            else {}
        )
        logger.info(
            "✅ Macro enrichment merged before discovery: %s | exposure_tickers=%d",
            selected.name,
            exposure_count,
        )
        return True
    except Exception as exc:
        logger.error(
            "🔴 Macro enrichment pre-discovery merge failed. "
            "Discovery would run without GPT macro context: %s",
            exc,
        )
        return False


def apply_external_intel_review_lane(run_id: str, macro_path: Path) -> bool:
    """Append governed catalyst/macro tickers to discovery for downstream review."""
    discovery_csv = cfg.OUTPUT_DIR / f"discovery_candidates_ultimate_{run_id}.csv"
    if not discovery_csv.exists():
        logger.warning("External intel review lane skipped: missing discovery CSV: %s", discovery_csv)
        return False
    if not cfg.APPLY_EXTERNAL_INTEL_REVIEW_LANE.exists():
        logger.warning(
            "External intel review lane skipped: script not deployed: %s",
            cfg.APPLY_EXTERNAL_INTEL_REVIEW_LANE,
        )
        return False

    report_path = cfg.OUTPUT_DIR / "qa" / f"external_intel_review_lane_{run_id}.json"
    ok = _run(
        "External Intel -> Discovery Review Lane",
        [
            sys.executable,
            str(cfg.APPLY_EXTERNAL_INTEL_REVIEW_LANE),
            "--discovery-csv",
            str(discovery_csv),
            "--macro-path",
            str(macro_path),
            "--report-path",
            str(report_path),
        ],
        critical=False,
    )
    if ok:
        logger.info("External intel review lane complete -> %s", report_path)
    else:
        logger.warning(
            "External intel review lane failed; catalyst/macro-only tickers may not reach package review"
        )
    return ok


# ============================================================ PHASE 2: QUALITY

def validate_quality(summary: dict) -> Tuple[bool, List[str]]:
    """Validate discovery output ratios and tier distribution."""
    logger.info("=" * 80)
    logger.info("PHASE 2: QUALITY VALIDATION")
    logger.info("=" * 80)

    issues: List[str] = []
    warnings: List[str] = []

    universe_size = summary.get("universe_size", 0)
    total_candidates = summary.get("total_candidates", 0)
    tier_0_early = summary.get("tier_0_early", 0)

    if universe_size == 0:
        issues.append("Universe size is 0 — summary file may be corrupt")
        return False, issues

    candidate_ratio = total_candidates / universe_size
    early_ratio = tier_0_early / universe_size

    logger.info(f"   Universe        : {universe_size} tickers")
    logger.info(f"   Total Candidates: {total_candidates} ({candidate_ratio*100:.1f}%)")
    logger.info(f"   Early Positions : {tier_0_early} ({early_ratio*100:.1f}%)")

    if candidate_ratio < cfg.EXPECTED_CANDIDATE_RATIO_MIN:
        issues.append(
            f"Too few candidates: {total_candidates} ({candidate_ratio*100:.1f}%) "
            f"— expected {cfg.EXPECTED_CANDIDATE_RATIO_MIN*100:.0f}–"
            f"{cfg.EXPECTED_CANDIDATE_RATIO_MAX*100:.0f}%. "
            f"Loosen compression threshold or lower tier minimums."
        )
    elif candidate_ratio > cfg.EXPECTED_CANDIDATE_RATIO_MAX:
        warnings.append(
            f"High candidate count: {total_candidates} ({candidate_ratio*100:.1f}%) "
            f"— consider tightening filters."
        )

    if early_ratio < cfg.EXPECTED_EARLY_RATIO_MIN:
        issues.append(
            f"Too few early positions: {tier_0_early} ({early_ratio*100:.1f}%) "
            f"— expected {cfg.EXPECTED_EARLY_RATIO_MIN*100:.1f}–"
            f"{cfg.EXPECTED_EARLY_RATIO_MAX*100:.1f}%. "
            f"Review early position thresholds in ULTIMATE script."
        )
    elif early_ratio > cfg.EXPECTED_EARLY_RATIO_MAX:
        warnings.append(f"High early position count: {tier_0_early} ({early_ratio*100:.1f}%)")

    tier_1 = summary.get("tier_1_confirmed", 0)
    tier_2 = summary.get("tier_2_observe", 0)
    if tier_1 == 0 and tier_2 == 0:
        issues.append("No Tier 1 or Tier 2 signals — logic may be broken")

    # Data freshness check — confirm discovery ran today, not on stale outputs.
    # summary["timestamp"] is the run execution time (format: YYYYMMDD_HHMMSS).
    # This catches cases where discovery CSV was read from a prior run.
    try:
        ts_str = summary.get("timestamp", "")
        if ts_str:
            run_date = ts_str[:8]  # YYYYMMDD
            today = datetime.now().strftime("%Y%m%d")
            if run_date != today:
                warnings.append(
                    f"Discovery timestamp {ts_str} is not today ({today}) — "
                    f"pipeline may be using stale discovery outputs."
                )
    except Exception:
        pass

    # Stale ticker count — populated by Discovery when Polygon fallback to cache fires.
    stale_count = summary.get("stale_ticker_count", 0)
    if stale_count > 0:
        stale_pct = stale_count / universe_size * 100 if universe_size > 0 else 0
        msg = (
            f"{stale_count} tickers ({stale_pct:.1f}%) used stale cached bar data "
            f"(Polygon fetch failed — prices may not be EOD)."
        )
        if stale_count > 50:
            warnings.append(msg)
        else:
            logger.info(f"   ℹ️  {msg}")

    for w in warnings:
        logger.warning(f"   ⚠️  {w}")

    if issues:
        logger.error("❌ QUALITY VALIDATION FAILED:")
        for iss in issues:
            logger.error(f"   - {iss}")
        return False, issues

    logger.info("✅ Quality validation PASSED\n")
    return True, []


# ============================================================ PHASE 3: REGRESSION

def detect_regression(summary: dict) -> None:
    """Compare to previous run. Logs warning on large swing — never blocks."""
    summaries = sorted(cfg.OUTPUT_DIR.glob("discovery_summary_ultimate_*.json"))
    if len(summaries) < 2:
        logger.info("⏭️  Regression check skipped (no previous run)\n")
        return
    try:
        with open(summaries[-2], "r", encoding="utf-8") as f:
            prev = json.load(f)
        prev_n = prev.get("total_candidates", 0)
        curr_n = summary.get("total_candidates", 0)
        if prev_n == 0:
            return
        change_pct = ((curr_n - prev_n) / prev_n) * 100
        logger.info(f"📊 Regression check: {prev_n} → {curr_n} candidates ({change_pct:+.1f}%)")
        if abs(change_pct) > 50:
            logger.warning(f"⚠️  Large change detected ({change_pct:+.1f}%) — review logic/market shift\n")
        else:
            logger.info("✅ Regression check OK\n")
    except Exception as e:
        logger.warning(f"⚠️  Regression check failed: {e}\n")


# ============================================================ PHASE 4: POSITION TRACKING

def run_position_tracking() -> bool:
    """Run position lifecycle tracker (non-critical)."""
    logger.info("=" * 80)
    logger.info("PHASE 4: POSITION TRACKING")
    logger.info("=" * 80)

    if not cfg.POSITION_TRACKER.exists():
        logger.warning("⏭️  Position tracker not found — skipping\n")
        return True

    return _run("Position Tracker", [sys.executable, str(cfg.POSITION_TRACKER)], critical=False)


# ============================================================ PHASE 4.5: PIN RUN DIRECTORY

def pin_run_directory(discovery_run_id: str, macro_path: Path) -> bool:
    """Create per-run structure and stage macro_snapshot + discovery CSV."""
    logger.info("=" * 80)
    logger.info("PHASE 4.5: PIN RUN DIRECTORY")
    logger.info("=" * 80)

    run_dir = cfg.RUNS_DIR / discovery_run_id
    discovery_dir = run_dir / "discovery"
    snapshot_path = run_dir / "macro_snapshot.json"
    macro_quant_path = run_dir / "macro_quant_packet.json"
    truth_packet_path = run_dir / "truth_packet_run.json"
    meta_path = run_dir / "run_meta.json"

    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        discovery_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"   Run dir       : {run_dir}")
    except Exception as e:
        logger.error(f"❌ Cannot create run directory {run_dir}: {e}\n")
        return False

    # Copy macro snapshot (fail-closed)
    try:
        shutil.copy2(macro_path, snapshot_path)
        logger.info(f"   Macro snapshot: {snapshot_path.name}  ✔")
    except Exception as e:
        logger.error(f"❌ Cannot write macro_snapshot.json: {e}\n")
        return False

    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            macro_data = json.load(f)
    except Exception as e:
        logger.error(f"❌ macro_snapshot.json failed JSON validation: {e}\n")
        snapshot_path.unlink(missing_ok=True)
        return False

    contract = macro_data.get("contract_version", "")
    if contract != "macro_contract_v1_0":
        logger.error(
            "❌ macro_snapshot.json contract_version mismatch.\n"
            f"   Found   : '{contract}'\n"
            "   Expected: 'macro_contract_v1_0'\n"
            f"   File: {macro_path}\n"
        )
        snapshot_path.unlink(missing_ok=True)
        return False

    try:
        macro_quant_packet = build_macro_quant_packet(macro_data, macro_path)
        macro_data["macro_quant_packet"] = macro_quant_packet
        truth_seed = {
            **macro_quant_packet,
            "run_id": discovery_run_id,
            "run_mode": "EVENING",
        }
        truth_packet = build_truth_packet_from_row(
            truth_seed,
            source="ORCHESTRATOR_MACRO",
            priority=PRIORITY_MACRO_QUANT,
            run_id=discovery_run_id,
            run_mode="EVENING",
        )
        macro_data["truth_packet"] = truth_packet.to_json_dict()
        write_json(snapshot_path, macro_data)
        write_json(macro_quant_path, macro_quant_packet)
        write_json(truth_packet_path, truth_packet.to_json_dict())
        logger.info(
            "   Macro quant   : %s  freshness=%s quality=%s",
            macro_quant_path.name,
            macro_quant_packet.get("macro_freshness_status", "UNKNOWN"),
            macro_quant_packet.get("macro_data_quality", "UNKNOWN"),
        )
    except Exception as e:
        logger.error(f"❌ Cannot write macro_quant_packet.json: {e}\n")
        return False

    flat_csv = cfg.OUTPUT_DIR / f"discovery_candidates_ultimate_{discovery_run_id}.csv"
    if flat_csv.exists():
        dest_csv = discovery_dir / flat_csv.name
        try:
            shutil.copy2(flat_csv, dest_csv)
            logger.info(f"   Discovery CSV : {dest_csv.name}  ✔")
        except Exception as e:
            logger.warning(f"⚠️  Could not stage discovery CSV (non-fatal, fallback active): {e}")
    else:
        logger.warning(f"⚠️  Flat discovery CSV not found — fallback may be used. Expected: {flat_csv}")

    meta = {
        "canonical_run_id": discovery_run_id,
        "discovery_run_id": discovery_run_id,
        "macro_source_path": str(macro_path),
        "macro_snapshot_path": str(snapshot_path),
        "macro_quant_packet_path": str(macro_quant_path),
        "truth_packet_path": str(truth_packet_path),
        "macro_freshness_status": macro_quant_packet.get("macro_freshness_status", "UNKNOWN"),
        "macro_data_quality": macro_quant_packet.get("macro_data_quality", "UNKNOWN"),
        "macro_regime_label": macro_quant_packet.get("macro_regime_label", "UNKNOWN"),
        "contract_version": contract,
        "pinned_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        logger.info(f"   Run meta      : {meta_path.name}  ✔")
    except Exception as e:
        logger.warning(f"⚠️  Could not write run_meta.json (non-fatal): {e}")

    logger.info("✅ Run directory pinned\n")
    try:
        run_dropoff_audit_checkpoint(discovery_run_id, "post_discovery_pin")
    except NameError:
        # Helper is defined later in this module; protects direct partial imports only.
        pass
    return True



# ============================================================ PHASES 5–8: VANGUARD PIPELINE

def run_dropoff_audit_checkpoint(run_id: str, label: str) -> None:
    """Write the drop-off audit at intermediate checkpoints without stopping the run."""
    try:
        from dropoff_audit import build_dropoff_audit

        df = build_dropoff_audit(run_id, runs_dir=cfg.RUNS_DIR)
        counts = df["dropoff_stage"].value_counts().to_dict() if "dropoff_stage" in df.columns else {}
        logger.info(
            "✅ DROP-OFF AUDIT CHECKPOINT (%s): dropoff_audit_%s.csv | rows=%d | stages=%s",
            label,
            run_id,
            len(df),
            counts,
        )
    except Exception as err:
        logger.warning("⚠️  Drop-off audit checkpoint failed (%s): %s", label, err)


def run_vanguard_pipeline(run_id: str, macro_path: Path, data_mode: str = "EOD") -> bool:
    """Build packages, inject macro, backfill bars, run Vanguard."""
    logger.info("=" * 80)
    logger.info("PHASES 5–8: VANGUARD PIPELINE")
    logger.info("=" * 80)
    logger.info(f"   Using discovery run ID: {run_id}")
    logger.info(f"   Using macro path      : {macro_path}")

    if not pin_run_directory(run_id, macro_path):
        logger.error("❌ VANGUARD pipeline aborted — could not pin run directory\n")
        return False

    for label, script, extra_args in [
        ("Build Packages from Discovery", cfg.BUILD_PACKAGES, ["--run-id", run_id]),
        ("Inject Macro into Packages", cfg.INJECT_MACRO, ["--run-id", run_id, "--macro-path", str(macro_path)]),
    ]:
        ok = _run(label, [sys.executable, str(script)] + extra_args, critical=True)
        if not ok:
            logger.error(
                f"❌ VANGUARD pipeline aborted at: {label}\n"
                f"   Re-run manually:\n"
                f"   python scripts\\{script.name} {' '.join(extra_args)}\n"
            )
            return False
        if label == "Build Packages from Discovery":
            run_dropoff_audit_checkpoint(run_id, "post_package_build")

    # Backfill (allows partial)
    backfill_label = "Backfill Timeseries into Packages"
    backfill_args = ["--run-id", run_id, "--allow-polygon",
                     "--allow-marketdata", "--intraday-provider", "auto",
                     "--data-mode", data_mode]  # pass through LATEST/EOD
    logger.info(f"▶  {backfill_label} (data-mode={data_mode})")
    logger.info(f"   CMD: {sys.executable} {cfg.BACKFILL_TIMESERIES} {' '.join(backfill_args)}")
    _backfill_proc = subprocess.run(
        [sys.executable, str(cfg.BACKFILL_TIMESERIES)] + backfill_args,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        cwd=str(cfg.BASE_DIR),
    )
    if _backfill_proc.stdout:
        for line in _backfill_proc.stdout.splitlines():
            logger.info(f"   | {line}")

    if _backfill_proc.returncode == 0:
        logger.info(f"✅ {backfill_label} — DONE\n")
    elif _backfill_proc.returncode == 2:
        logger.warning(
            "⚠️  Backfill had partial failures (TOO_SHORT tickers). Excluding them; continuing.\n"
        )
    else:
        logger.error(
            f"❌ VANGUARD pipeline aborted at: {backfill_label}\n"
            f"   Exit code: {_backfill_proc.returncode}\n"
            f"   Re-run manually:\n"
            f"   python scripts\\{cfg.BACKFILL_TIMESERIES.name} {' '.join(backfill_args)}\n"
        )
        return False

    # Defence-in-depth
    index_path = cfg.RUNS_DIR / run_id / "packages" / "index.json"
    if not index_path.exists():
        logger.error(
            f"❌ VANGUARD ABORTED — RUN_INVALID: packages/index.json missing.\n"
            f"   Expected: {index_path}\n"
        )
        return False

    ok = _run("Run VANGUARD", [sys.executable, str(cfg.RUN_VANGUARD), "--run-id", run_id], critical=True)
    if not ok:
        logger.error(
            "❌ VANGUARD pipeline aborted at: Run VANGUARD\n"
            f"   Re-run manually:\n   python scripts\\{cfg.RUN_VANGUARD.name} --run-id {run_id}\n"
        )
        return False

    logger.info("✅ VANGUARD pipeline complete\n")
    run_dropoff_audit_checkpoint(run_id, "post_vanguard")
    return True


# ============================================================ PHASE 8b: OPTIONS INTELLIGENCE

def run_options_intelligence(run_id: str, premarket_mode: bool = False) -> bool:
    """Options Intelligence Layer (non-critical)."""
    logger.info("=" * 80)
    logger.info("PHASE 8b: OPTIONS INTELLIGENCE LAYER")
    if premarket_mode:
        logger.info("   Mode: PREMARKET (scoped to EXECUTE + ARMED tickers only)")
    logger.info("=" * 80)

    run_dir = cfg.RUNS_DIR / run_id
    disc_dir = run_dir / "discovery"
    vanguard_csv = run_dir / "vanguard" / "vanguard_signals.csv"
    output_dir = run_dir / "options"

    disc_candidates = list(disc_dir.glob(f"discovery_candidates_ultimate_{run_id}.csv"))
    if not disc_candidates:
        disc_candidates = list(cfg.OUTPUT_DIR.glob(f"discovery_candidates_ultimate_{run_id}.csv"))
    if not disc_candidates:
        logger.warning(
            "Options Intelligence skipped — discovery CSV not found for run %s. "
            "SuperBrain will use vanguard_signals.csv (EOD mode fallback).",
            run_id,
        )
        return False
    discovery_csv = disc_candidates[0]

    if not vanguard_csv.exists():
        logger.warning(
            "Options Intelligence skipped — vanguard_signals.csv not found: %s. "
            "SuperBrain will use vanguard_signals.csv (EOD mode fallback).",
            vanguard_csv,
        )
        return False

    if not cfg.OPTIONS_INTEL.exists():
        logger.warning("⏭️  Options Intelligence skipped — script not deployed: %s", cfg.OPTIONS_INTEL)
        return True

    # Premarket scope
    if premarket_mode:
        import csv as _csv
        options_csv_path = output_dir / f"options_intelligence_{run_id}.csv"
        if options_csv_path.exists():
            try:
                actionable = set()
                with open(options_csv_path, "r", encoding="utf-8-sig", newline="") as f:
                    reader = _csv.DictReader(f)
                    for row in reader:
                        verdict = str(row.get("options_verdict", "")).strip().upper()
                        ticker = str(row.get("ticker", "")).strip().upper()
                        if verdict in {"EXECUTE", "ARMED"} and ticker:
                            actionable.add(ticker)
                if actionable:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    scoped_csv = output_dir / "premarket_scope.csv"
                    rows_written = 0
                    with open(discovery_csv, "r", encoding="utf-8-sig", newline="") as fin, \
                         open(scoped_csv, "w", encoding="utf-8", newline="") as fout:
                        reader = _csv.DictReader(fin)
                        writer = _csv.DictWriter(fout, fieldnames=reader.fieldnames)
                        writer.writeheader()
                        for row in reader:
                            if str(row.get("ticker", "")).strip().upper() in actionable:
                                writer.writerow(row)
                                rows_written += 1
                    logger.info(f"   Premarket scope : {rows_written} tickers → {scoped_csv.name}")
                    discovery_csv = scoped_csv
            except Exception as e:
                logger.warning("⚠️  Premarket scope failed (%s) — using full discovery CSV", e)

    logger.info(f"   Discovery CSV : {discovery_csv.name}")
    logger.info(f"   Vanguard CSV  : {vanguard_csv.name}")
    logger.info(f"   Output dir    : {output_dir}")

    ok = _run(
        "Options Intelligence Layer",
        [sys.executable, str(cfg.OPTIONS_INTEL), str(discovery_csv), str(vanguard_csv), run_id, str(output_dir)],
        critical=False,
    )

    if not ok:
        logger.warning("⚠️  Options Intelligence failed — pipeline continues without options layer.")
    else:
        # Warn (not abort) if the output CSV is empty — SuperBrain needs it
        _oi_csv = output_dir / f"options_intelligence_{run_id}.csv"
        if not _oi_csv.exists() or _oi_csv.stat().st_size < 100:
            logger.warning(
                "⚠️  Options Intelligence produced no output (empty or missing CSV).\n"
                "   SuperBrain and policy engine will have no signals to process.\n"
                "   Check options_intelligence log above for BLOCK_WRONG_STRIKE or API errors.\n"
                "   Pipeline continues — morning validation will show 0 actionable signals."
            )
    run_dropoff_audit_checkpoint(run_id, "post_options")
    return ok


# ============================================================ PHASE 8c: CORE INTEL EXPORTER


# ============================================================ PHASE 8c-P: PHANTOM EDGE MODEL

def run_phantom_layer(run_id: str) -> bool:
    """PHANTOM production edge model (non-critical fail-open)."""
    logger.info("=" * 80)
    logger.info("PHASE 8c-P: PHANTOM EDGE MODEL")
    logger.info("=" * 80)

    if not cfg.PHANTOM_RUNNER.exists():
        logger.warning("PHANTOM skipped - script not deployed: %s", cfg.PHANTOM_RUNNER)
        return True

    input_csv = cfg.RUNS_DIR / run_id / "options" / f"options_intelligence_{run_id}.csv"
    output_csv = cfg.RUNS_DIR / run_id / "options" / f"options_intelligence_phantom_{run_id}.csv"
    if not input_csv.exists():
        logger.warning("PHANTOM skipped - options CSV not found: %s", input_csv)
        return True

    cmd = [
        sys.executable,
        str(cfg.PHANTOM_RUNNER),
        "--run-id", run_id,
        "--repo-root", str(cfg.BASE_DIR),
        "--input-csv", str(input_csv),
        "--output-csv", str(output_csv),
        "--db-path", str(cfg.PHANTOM_DB_PATH),
    ]
    ok = _run("PHANTOM Edge Model", cmd, critical=False)
    if not ok:
        logger.warning("PHANTOM failed open - downstream will use original Options Intelligence output.")
        return True
    if output_csv.exists():
        logger.info("PHANTOM output ready for downstream handoff: %s", output_csv.name)
    return True


def run_core_intel_exporter(run_id: str, strict: bool = False) -> bool:
    """CORE INTEL Exporter (non-critical)."""
    logger.info("=" * 80)
    logger.info("PHASE 8c: CORE INTEL EXPORTER")
    logger.info("=" * 80)

    if not cfg.CORE_INTEL_EXPORTER.exists():
        logger.warning("⏭️  Core Intel Exporter skipped — script not deployed: %s", cfg.CORE_INTEL_EXPORTER)
        return True

    vanguard_csv = cfg.RUNS_DIR / run_id / "vanguard" / "vanguard_signals.csv"
    if not vanguard_csv.exists():
        logger.warning("⚠️  Core Intel Exporter skipped — vanguard_signals.csv not found: %s", vanguard_csv)
        return False

    options_dir = cfg.RUNS_DIR / run_id / "options"
    options_csv: Optional[Path] = None
    if options_dir.exists():
        candidates = sorted(
            list(options_dir.glob(f"options_intelligence_phantom_{run_id}.csv")) +
            list(options_dir.glob(f"options_intelligence_{run_id}.csv")),
            # PHANTOM-CORE-EXPORTER-HOTFIX 2026-05-22:
            # Path.stat().st_mtime is already a float timestamp on Windows/Python.
            key=lambda p: (0 if "phantom" in p.name else 1, -float(p.stat().st_mtime)),
        )
        if candidates:
            options_csv = candidates[0]

    cmd = [sys.executable, str(cfg.CORE_INTEL_EXPORTER), "--run-id", run_id]
    if options_csv:
        cmd += ["--options-csv", str(options_csv)]
    if strict:
        cmd.append("--strict")

    logger.info(f"   Run ID       : {run_id}")
    logger.info(f"   Vanguard CSV : {vanguard_csv.name}")
    logger.info(f"   Options CSV  : {options_csv.name if options_csv else 'not available'}")
    logger.info(f"   Strict mode  : {strict}")

    ok = _run("Core Intel Exporter", cmd, critical=False)
    if not ok:
        logger.warning("⚠️  Core Intel Exporter failed — pipeline continues.")
    return ok


# ============================================================ PHASE 8d: SUPER BRAIN LAYER

def run_superbrain_layer(run_id: str, premarket_mode: bool = False, eod_mode: bool = True) -> bool:
    """
    Phase 8d — delegates to run_superbrain_passthrough().
    SuperBrain scoring deprecated 2026-04-28. Passthrough retained because
    EIL, GARCH, WBS require superbrain_enriched CSV to exist.
    Sprint 2: wrapper collapsed — no intermediate logic here.
    """
    return run_superbrain_passthrough(run_id)


# ============================================================ PATCH 1: HORIZON PROPAGATION HELPER

def patch_horizon_fields_into_csv(run_id: str, target_csv: Path, label: str) -> bool:
    """
    PATCH 1 (MUST): Stamp Phase 1B horizon routing fields into a downstream CSV.

    Why this exists:
    Phase 1B writes horizon_*.csv files before superbrain_enriched exists.
    run_superbrain_passthrough() copies OI → superbrain. Unless OI already has
    horizon fields, superbrain will be missing them and EIL horizon gates
    (11_20d → MONITOR_ONLY, 6_10d → 0.70x) will never fire.

    This function is called twice:
      1. After Phase 1B, targeting the OI CSV  (PATCH 2a)
      2. After Phase 8d, targeting superbrain   (PATCH 2b, defence-in-depth)

    Merge strategy:
      - Prefer signal_id if both files carry it (avoids ticker collision for
        tickers with both CALL and PUT candidates)
      - Fall back to ticker if signal_id absent
    """
    try:
        import pandas as _pd_hp

        if not target_csv.exists():
            logger.warning(
                "Horizon patch skipped for %s — target CSV not found: %s", label, target_csv
            )
            return False

        horizon_dir = cfg.RUNS_DIR / run_id / "horizon"
        if not horizon_dir.exists():
            logger.warning(
                "Horizon patch skipped for %s — horizon dir not found: %s", label, horizon_dir
            )
            return False

        horizon_frames = []
        for _bucket in ("1_5d", "6_10d", "11_20d", "blocked"):
            _hp = horizon_dir / f"horizon_{_bucket}_{run_id}.csv"
            if not _hp.exists():
                continue
            _hdf = _pd_hp.read_csv(_hp, low_memory=False)
            if _hdf.empty or "ticker" not in _hdf.columns:
                continue
            _hdf["ticker"] = _hdf["ticker"].astype(str).str.strip().str.upper()
            _hdf["horizon_bucket"] = _bucket
            _keep = [
                c for c in [
                    "ticker", "signal_id", "instrument",
                    "horizon_bucket", "horizon_action",
                    "horizon_size_multiplier", "horizon_block_reason",
                    "horizon_source", "router_version",
                ]
                if c in _hdf.columns
            ]
            horizon_frames.append(_hdf[_keep].copy())

        if not horizon_frames:
            logger.warning("Horizon patch skipped for %s — no horizon CSVs found", label)
            return False

        route_df = _pd_hp.concat(horizon_frames, ignore_index=True)
        target_df = _pd_hp.read_csv(target_csv, low_memory=False)

        if target_df.empty or "ticker" not in target_df.columns:
            logger.warning("Horizon patch skipped for %s — target has no ticker rows", label)
            return False

        target_df["ticker"] = target_df["ticker"].astype(str).str.strip().str.upper()

        _horizon_cols = [
            "horizon_bucket", "horizon_action",
            "horizon_size_multiplier", "horizon_block_reason",
            "horizon_source", "router_version",
        ]
        # Drop stale horizon columns before merge
        target_df = target_df.drop(
            columns=[c for c in _horizon_cols if c in target_df.columns], errors="ignore"
        )

        if "signal_id" in target_df.columns and "signal_id" in route_df.columns:
            route_df = route_df.drop_duplicates(subset=["signal_id"], keep="first")
            _merge_cols = [c for c in ["signal_id"] + _horizon_cols if c in route_df.columns]
            patched = target_df.merge(route_df[_merge_cols], on="signal_id", how="left")
            _merge_key = "signal_id"
        else:
            route_df = route_df.drop_duplicates(subset=["ticker"], keep="first")
            _merge_cols = [c for c in ["ticker"] + _horizon_cols if c in route_df.columns]
            patched = target_df.merge(route_df[_merge_cols], on="ticker", how="left")
            _merge_key = "ticker"

        patched["horizon_bucket"] = patched["horizon_bucket"].fillna("unrouted")
        patched["horizon_action"] = patched["horizon_action"].fillna("UNKNOWN")
        patched["horizon_size_multiplier"] = patched["horizon_size_multiplier"].fillna(0.0)
        patched["horizon_block_reason"] = patched["horizon_block_reason"].fillna("")

        patched.to_csv(target_csv, index=False)

        _matched = int((patched["horizon_bucket"] != "unrouted").sum())
        logger.info(
            "✅ Horizon patch → %s | matched=%d/%d via %s | file=%s",
            label, _matched, len(patched), _merge_key, target_csv.name,
        )
        return True

    except Exception as _hp_err:
        logger.warning("⚠️  Horizon patch failed for %s — %s", label, _hp_err)
        return False


def run_superbrain_passthrough(run_id: str) -> bool:
    """
    Phase 8d passthrough (FIX-2026-04-30): copies OI-enriched CSV →
    superbrain_enriched_{run_id}.csv and maps options_verdict → sb_final_verdict.

    EIL, GARCH, WBS, and CT Gate all require superbrain_enriched to exist.
    SuperBrain script was deprecated 2026-04-28; this passthrough ensures the
    downstream consumers still receive a correctly shaped CSV.
    """
    import pandas as _pd
    logger.info("=" * 80)
    logger.info("PHASE 8d: SUPERBRAIN PASSTHROUGH")
    logger.info("=" * 80)

    oi_csv_original = cfg.RUNS_DIR / run_id / "options" / f"options_intelligence_{run_id}.csv"
    oi_csv_phantom  = cfg.RUNS_DIR / run_id / "options" / f"options_intelligence_phantom_{run_id}.csv"
    oi_csv = oi_csv_phantom if oi_csv_phantom.exists() else oi_csv_original
    if oi_csv == oi_csv_phantom:
        logger.info("PHANTOM handoff active: using %s", oi_csv.name)
    sb_dir = cfg.RUNS_DIR / run_id / "superbrain"
    sb_csv = sb_dir / f"superbrain_enriched_{run_id}.csv"

    if not oi_csv.exists():
        logger.warning("⚠️  Phase 8d passthrough skipped — OI CSV not found: %s", oi_csv)
        return False

    try:
        sb_dir.mkdir(parents=True, exist_ok=True)
        df = _pd.read_csv(oi_csv, low_memory=False)

        # Horizon governance audit — if horizon_bucket is absent here, the
        # EIL horizon gate (11-20D MONITOR_ONLY, 6-10D 0.70x) will not fire.
        # patch_horizon_fields_into_csv() is called after this passthrough
        # to ensure EIL receives the correct fields.
        if "horizon_bucket" not in df.columns:
            logger.warning(
                "⚠️  SuperBrain passthrough: horizon_bucket missing from OI CSV. "
                "EIL horizon gates may not activate unless patched after passthrough. "
                "patch_horizon_fields_into_csv() will attempt remediation."
            )

        # Map options_verdict → sb_final_verdict (required by EIL guard)
        if "options_verdict" in df.columns:
            if "sb_final_verdict" not in df.columns:
                df["sb_final_verdict"] = df["options_verdict"]
                logger.info("   Mapped options_verdict → sb_final_verdict")
        else:
            if "sb_final_verdict" not in df.columns:
                df["sb_final_verdict"] = "STAND_DOWN"
                logger.warning("   options_verdict column absent — sb_final_verdict defaulted to STAND_DOWN")

        # ITEM 2 — EIL spread column guarantee.
        # EIL S1 liquidity gate reads contract_spread_pct, contract_premium,
        # options_bid, options_ask from the superbrain row. If any are absent
        # EIL falls back to hardcoded 0.04 for every ticker → all rows get
        # identical spread → SANITY_WARN_SPREAD → block rate distorted.
        #
        # These columns originate in avshunter_options_intelligence.py.
        # If OI wrote them they survive the passthrough unchanged.
        # If OI did not write them (API failure, EOD synthetic path) we
        # insert NaN placeholders so EIL knows data is absent rather than
        # silently using a wrong default.
        _SPREAD_COLS = {
            "contract_spread_pct": float("nan"),  # decimal fraction e.g. 0.157
            "contract_premium":    float("nan"),  # mid price of selected contract
            "options_bid":         float("nan"),  # bid of selected contract
            "options_ask":         float("nan"),  # ask of selected contract
            "contract_iv":         float("nan"),  # implied volatility decimal
            "contract_delta":      float("nan"),  # delta of selected contract
        }
        _missing_spread = []
        for col, default in _SPREAD_COLS.items():
            if col not in df.columns:
                df[col] = default
                _missing_spread.append(col)

        if _missing_spread:
            logger.warning(
                "⚠️  Phase 8d: %d spread/contract columns absent from OI CSV — "
                "inserted as NaN so EIL uses synthesis path not hardcoded default. "
                "Missing: %s. "
                "Check avshunter_options_intelligence.py output for these fields.",
                len(_missing_spread), ", ".join(_missing_spread),
            )
        else:
            logger.info(
                "✅ Phase 8d: all spread/contract columns present "
                "(contract_spread_pct, premium, bid, ask, iv, delta)"
            )

        df.to_csv(sb_csv, index=False)
        logger.info(
            "✅ Phase 8d passthrough: superbrain_enriched written (%d rows) → %s",
            len(df), sb_csv,
        )
        return True

    except Exception as e:
        logger.error("❌ Phase 8d passthrough failed: %s", e)
        return False


def run_position_lock_check(run_id: str) -> bool:
    """
    Read open positions from trade journal. Write locked_tickers_{run_id}.txt
    so SuperBrain can suppress re-signalling of live trades.
    Non-critical — if journal not present, pipeline runs normally.
    """
    try:
        journal_script = cfg.BASE_DIR / "avshunter_trade_journal.py"
        if not journal_script.exists():
            return True

        # Import journal directly to read open tickers
        import importlib.util, sys as _sys
        spec = importlib.util.spec_from_file_location("trade_journal", str(journal_script))
        jmod = importlib.util.module_from_spec(spec)
        _sys.modules["trade_journal"] = jmod  # FIX-IMPORT-01
        spec.loader.exec_module(jmod)

        db_path = jmod.DEFAULT_DB_PATH
        open_tickers = jmod.get_open_tickers(db_path)

        if not open_tickers:
            logger.info("Position lock: no open positions — all tickers eligible")
            return True

        # Write lock file to run dir so downstream modules can read it
        run_dir  = cfg.RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        lock_file = run_dir / f"locked_tickers_{run_id}.txt"
        lock_file.write_text("\n".join(sorted(open_tickers)), encoding="utf-8")

        logger.info(f"Position lock: {len(open_tickers)} ticker(s) locked — "
                    f"{', '.join(sorted(open_tickers))}")
        logger.info(f"   Lock file: {lock_file}")
        logger.info(f"   These tickers will NOT be re-signalled until journal exit is logged.")
        return True

    except Exception as e:
        logger.warning(f"Position lock check failed (non-critical): {e}")
        return True


def run_catastrophe_gate(run_id: str) -> bool:
    """
    Sprint 2: Catastrophe Gate removed from live decision chain.
    Was running in shadow mode with no measured outcome contribution.
    Function retained as a no-op stub so call sites require no changes.
    Returns True so pipeline continues normally.
    """
    logger.info("=" * 80)
    logger.info("PHASE 8b: CATASTROPHE GATE — removed Sprint 2 (was shadow mode, no contribution)")
    logger.info("=" * 80)
    return True


def run_wall_break_scorer(run_id: str) -> bool:
    """Layer 4b: Wall Break Scorer -- runs after SuperBrain."""
    logger.info("=" * 80)
    logger.info("PHASE 8e: WALL BREAK SCORER")
    logger.info("=" * 80)

    wbs_script = cfg.BASE_DIR / "wall_break_scorer.py"
    if not wbs_script.exists():
        logger.warning("WBS skipped -- wall_break_scorer.py not deployed: %s", wbs_script)
        return True

    run_dir    = cfg.RUNS_DIR / run_id
    sb_csv     = run_dir / "superbrain" / f"superbrain_enriched_{run_id}.csv"
    oi_csv     = run_dir / "options"    / f"options_intelligence_{run_id}.csv"
    output_dir = run_dir / "superbrain"

    if not sb_csv.exists():
        logger.warning("WBS skipped -- superbrain_enriched CSV not found: %s", sb_csv)
        return True
    if not oi_csv.exists():
        logger.warning("WBS skipped -- options_intelligence CSV not found: %s", oi_csv)
        return True

    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(wbs_script),
        str(sb_csv), str(oi_csv),
        run_id, str(output_dir),
    ]
    ok = _run("Wall Break Scorer", cmd, critical=False)
    if not ok:
        logger.warning("WBS failed -- pipeline continues unaffected")
    return True


# ============================================================ PHASE 9: EXECUTION INTELLIGENCE LAYER

def run_execution_intelligence_layer(run_id: str) -> bool:
    """
    Phase 9: Execution Intelligence Layer (EIL).
    Runs after Wall Break Scorer. Enriches actionable signals with
    microstructure analysis: liquidity gating, IV distortion, GEX flip,
    OBI, and POC timing. Non-critical — pipeline continues if EIL fails.

    Advisory mode is active by default (EIL_ADVISORY_ONLY env var).
    Output: eil_enriched_{run_id}.csv alongside superbrain_enriched CSV.
    """
    logger.info("=" * 80)
    logger.info("PHASE 9: EXECUTION INTELLIGENCE LAYER (EIL)")
    logger.info("=" * 80)

    if not cfg.EIL_RUNNER.exists():
        logger.warning("⏭️  EIL skipped — execution_intelligence_runner.py not deployed: %s", cfg.EIL_RUNNER)
        return False

    sb_csv = cfg.RUNS_DIR / run_id / "superbrain" / f"superbrain_enriched_{run_id}.csv"
    if not sb_csv.exists():
        logger.warning("⚠️  EIL skipped — superbrain_enriched CSV not found: %s", sb_csv)
        return False

    # Guard: verify sb_final_verdict column exists before EIL fires.
    # EIL reads this column to filter actionable signals. If SuperBrain failed
    # to write it (schema mismatch or early crash), EIL would silently process
    # zero signals. Warn and skip rather than produce a misleading empty output.
    try:
        import csv as _csv_mod
        with open(sb_csv, "r", encoding="utf-8-sig", newline="") as _f:
            _headers = next(_csv_mod.reader(_f), [])
        if "sb_final_verdict" not in _headers:
            logger.warning(
                "⚠️  EIL skipped — 'sb_final_verdict' column missing from superbrain_enriched CSV.\n"
                "   SuperBrain may have failed silently or written an older schema.\n"
                "   Re-run SuperBrain manually: python scripts\\avshunter_superbrain_layer.py\n"
                "   Then re-run EIL: python execution_intelligence_runner.py --run_id %s", run_id
            )
            return False
    except Exception as _guard_err:
        logger.warning("⚠️  EIL column guard check failed (%s) — proceeding anyway.", _guard_err)

    import os as _os
    advisory_only = _os.environ.get("EIL_ADVISORY_ONLY", "true").lower() != "false"
    logger.info("   Advisory mode : %s", advisory_only)
    logger.info("   Input CSV     : %s", sb_csv.name)

    cmd = [sys.executable, str(cfg.EIL_RUNNER), "--run_id", run_id]
    if not advisory_only:
        cmd.append("--live")

    ok = _run("Execution Intelligence Layer", cmd, critical=False)
    if not ok:
        logger.error("EIL failed - downstream EIL handoff stages cannot run for this cycle.")
        return False

    # EIL is a required handoff artifact for GARCH->EIL merge, trigger 8.6b,
    # handoff guard, and execution export. Treat a missing or malformed file as
    # failed, rather than letting later stages skip silently.
    try:
        import pandas as _pd_eil_contract
        _eil_contract_path = cfg.RUNS_DIR / run_id / "superbrain" / f"eil_enriched_{run_id}.csv"
        if not _eil_contract_path.exists():
            logger.error("EIL output missing after runner completed: %s", _eil_contract_path)
            return False
        _eil_contract_df = _pd_eil_contract.read_csv(_eil_contract_path, nrows=5, low_memory=False)
        _eil_required = {"ticker", "eil_v3_verdict"}
        _eil_missing = sorted(_eil_required - set(_eil_contract_df.columns))
        if _eil_missing:
            logger.error("EIL output malformed; missing required columns: %s", _eil_missing)
            return False
    except Exception as _eil_contract_err:
        logger.error("EIL output validation failed: %s", _eil_contract_err)
        return False

    # ── Patch 3: EIL sector field preservation guard ─────────────────────────
    # PRODUCTION CONTRACT (D-MACRO-SEC-002):
    #   execution_intelligence_runner.py MUST build output rows as:
    #       out_row = dict(input_row)   # preserve ALL input fields
    #       out_row.update(eil_fields)  # then overlay EIL fields
    #   NOT as: out_row = eil_fields   (loses sector alignment columns)
    #
    # This guard detects if the runner lost sector alignment columns and patches
    # them back from superbrain_enriched before downstream modules read eil_enriched.
    # ─────────────────────────────────────────────────────────────────────────
    _SECTOR_COLS = [
        "macro_sector_bias", "sector_alignment_label", "sector_alignment_score",
        "sector_alignment_flag", "sector_etf_mapped", "gics_sector_norm",
        "sector_bias_source", "sector_conviction_context", "sector_alignment_note",
    ]
    try:
        import pandas as _pd_eil
        _eil_csv = cfg.RUNS_DIR / run_id / "superbrain" / f"eil_enriched_{run_id}.csv"
        _sb_csv2 = cfg.RUNS_DIR / run_id / "superbrain" / f"superbrain_enriched_{run_id}.csv"
        if _eil_csv.exists() and _sb_csv2.exists():
            _eil_df = _pd_eil.read_csv(_eil_csv, low_memory=False)
            _missing_sector = [c for c in _SECTOR_COLS if c not in _eil_df.columns]
            if _missing_sector:
                logger.warning(
                    "⚠️  EIL runner dropped sector alignment columns: %s — patching from superbrain_enriched",
                    _missing_sector
                )
                _sb_df = _pd_eil.read_csv(_sb_csv2, low_memory=False)
                _avail = [c for c in _missing_sector if c in _sb_df.columns]
                if _avail and "ticker" in _sb_df.columns and "ticker" in _eil_df.columns:
                    _patch = _sb_df[["ticker"] + _avail].drop_duplicates("ticker")
                    _eil_df = _eil_df.merge(_patch, on="ticker", how="left")
                    _eil_df.to_csv(_eil_csv, index=False)
                    logger.info("✅ Sector columns patched into eil_enriched: %s", _avail)
            else:
                logger.info("✅ EIL sector column check: all %d sector fields present", len(_SECTOR_COLS))
    except Exception as _eil_sc_err:
        logger.warning("⚠️  EIL sector column guard failed (non-critical): %s", _eil_sc_err)

    return True


def _eil_post_actuarial_inject(run_id: str) -> None:
    """Called by evening_workflow and validate_workflow after EIL completes."""
    inject_actuarial_into_eil_csv(run_id)


def run_garch_layer(run_id: str) -> bool:
    """
    Phase 10a: Q-OMEGA Layer 3 — GARCH Forward Variance Batch.
    Runs garch_runner.py for all tickers in superbrain_enriched CSV.
    Non-critical — pipeline continues unaffected if GARCH errors.
    Output: data/output/runs/{run_id}/qomega/garch_forecasts_{run_id}.csv
    """
    logger.info("=" * 80)
    logger.info("PHASE 10a: Q-OMEGA LAYER 3 — GARCH FORWARD VARIANCE")
    logger.info("=" * 80)

    garch_script = cfg.BASE_DIR / "garch_runner.py"
    if not garch_script.exists():
        logger.warning("⏭️  GARCH runner skipped — garch_runner.py not deployed: %s", garch_script)
        return True

    sb_csv = cfg.RUNS_DIR / run_id / "superbrain" / f"superbrain_enriched_{run_id}.csv"
    if not sb_csv.exists():
        logger.warning("⚠️  GARCH skipped — superbrain_enriched CSV not found: %s", sb_csv)
        return True

    out_dir = cfg.RUNS_DIR / run_id / "qomega"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, str(garch_script), run_id,
           "--superbrain_csv", str(sb_csv),
           "--output_dir",     str(out_dir)]
    ok = _run("Q-OMEGA GARCH Runner", cmd, critical=False)
    if not ok:
        logger.warning("⚠️  GARCH Layer 3 failed — pipeline continues. Q-OMEGA mispricing will be skipped.")
    return True


def merge_garch_into_enriched(run_id: str) -> bool:
    """
    Phase 10b — FIX-05: Merge GARCH l3_ forecast fields into superbrain_enriched CSV.

    run_garch_layer() writes garch_forecasts_{run_id}.csv to the qomega/ directory
    and stops. Nothing downstream consumed those fields — EVEngineV2 therefore ran
    without GARCH forward vol or iv_tailwind_score for every signal in the run.

    This function joins on ticker (left join — signals without GARCH coverage keep
    their existing values) and overwrites superbrain_enriched in place.

    Fields merged (all l3_ prefixed):
        l3_forward_realised_vol     — GARCH forward vol estimate
        l3_vol_forecast_conf        — model confidence 0-1
        l3_expected_move_1_5d       — expected move pct, 1-5 day horizon
        l3_expected_move_6_10d      — expected move pct, 6-10 day horizon
        l3_expected_move_11_20d     — expected move pct, 11-20 day horizon
        l3_iv_tailwind_score        — IV tailwind/headwind score (-100 to +100)
        l3_jump_risk_flag           — True if jump risk detected
        l3_method                   — computation method (GARCH / FALLBACK)
        l3_error                    — error message if GARCH failed for this ticker

    After this runs, enrich_vanguard_inputs() in edge_detector.py will read
    l3_expected_move_6_10d as the expected_move_10d input to EVEngineV2, and
    l3_iv_tailwind_score feeds the vega adjustment layer.
    """
    import pandas as pd

    logger.info("=" * 80)
    logger.info("PHASE 10b: GARCH → SUPERBRAIN MERGE")
    logger.info("=" * 80)

    garch_path = cfg.RUNS_DIR / run_id / "qomega" / f"garch_forecasts_{run_id}.csv"
    sb_path    = cfg.RUNS_DIR / run_id / "superbrain" / f"superbrain_enriched_{run_id}.csv"

    if not garch_path.exists():
        logger.warning("⏭️  GARCH merge skipped — garch_forecasts CSV not found: %s", garch_path)
        return True
    if not sb_path.exists():
        logger.warning("⏭️  GARCH merge skipped — superbrain_enriched CSV not found: %s", sb_path)
        return True

    try:
        garch = pd.read_csv(garch_path)
        sb    = pd.read_csv(sb_path)

        # Keep only l3_ columns plus the join key
        l3_cols = [c for c in garch.columns if c.startswith("l3_")]
        if not l3_cols:
            logger.warning("⚠️  GARCH CSV has no l3_ columns — merge skipped")
            return True

        garch_slim = garch[["ticker"] + l3_cols].copy()

        # Drop any l3_ columns already in superbrain (avoid _x/_y suffix collision)
        existing_l3 = [c for c in sb.columns if c.startswith("l3_")]
        if existing_l3:
            sb = sb.drop(columns=existing_l3)

        merged = sb.merge(garch_slim, on="ticker", how="left")
        merged.to_csv(sb_path, index=False)

        n_matched = merged["l3_method"].notna().sum() if "l3_method" in merged.columns else "?"
        logger.info(
            "✅  GARCH merge complete (superbrain): %d l3_ fields added | %s/%d tickers matched",
            len(l3_cols), n_matched, len(merged)
        )

        # ── EIL ENRICHED MERGE (Phase 10b-EIL) ───────────────────────────────
        # ev_engine_v2_fixed.py reads l3_iv_tailwind_score from eil_enriched to
        # compute iv_adjustment. Without this merge the field is missing and
        # iv_adjustment = 0.0 for all tickers — the fix is inert.
        # This is the downstream consequence of l3_ fields living only in
        # superbrain_enriched but EIL being the authoritative signal source.
        eil_path = cfg.RUNS_DIR / run_id / "superbrain" / f"eil_enriched_{run_id}.csv"
        if eil_path.exists():
            try:
                eil = pd.read_csv(eil_path)
                existing_l3_eil = [c for c in eil.columns if c.startswith("l3_")]
                if existing_l3_eil:
                    eil = eil.drop(columns=existing_l3_eil)
                eil_merged = eil.merge(garch_slim, on="ticker", how="left")
                eil_merged.to_csv(eil_path, index=False)
                n_eil = eil_merged["l3_method"].notna().sum() if "l3_method" in eil_merged.columns else "?"
                logger.info(
                    "✅  GARCH merge complete (eil_enriched): %d l3_ fields added | %s/%d tickers",
                    len(l3_cols), n_eil, len(eil_merged)
                )
            except Exception as _eil_garch_err:
                logger.warning(
                    "⚠️  GARCH → eil_enriched merge failed (non-critical): %s", _eil_garch_err
                )
        else:
            logger.info(
                "⏭️  GARCH → eil_enriched skipped — eil_enriched CSV not yet written "
                "(EIL runs after this). l3_ fields will be absent from EIL for this run. "
                "Ensure Phase 10b runs AFTER Phase 9 (EIL) for full GARCH enrichment."
            )
        execution_path = cfg.RUNS_DIR / run_id / "execution" / f"execution_v3_5_{run_id}.csv"
        if execution_path.exists():
            try:
                execution = pd.read_csv(execution_path)
                existing_l3_execution = [c for c in execution.columns if c.startswith("l3_")]
                if existing_l3_execution:
                    execution = execution.drop(columns=existing_l3_execution)
                execution_merged = execution.merge(garch_slim, on="ticker", how="left")
                execution_merged.to_csv(execution_path, index=False)
                n_execution = (
                    execution_merged["l3_method"].notna().sum()
                    if "l3_method" in execution_merged.columns
                    else "?"
                )
                logger.info(
                    "✅  GARCH merge complete (execution): %d l3_ fields added | %s/%d tickers",
                    len(l3_cols), n_execution, len(execution_merged)
                )
            except Exception as _execution_garch_err:
                logger.warning(
                    "⚠️  GARCH → execution merge failed (non-critical): %s",
                    _execution_garch_err,
                )
        else:
            logger.info("⏭️  GARCH → execution skipped — execution CSV not yet written.")

        # ─────────────────────────────────────────────────────────────────────

        return True

    except Exception as e:
        logger.error("❌  GARCH merge failed: %s — superbrain_enriched unchanged", e)
        return True  # non-critical — pipeline continues


def run_catalyst_truth_layer(run_id: str, stage: str = "") -> bool:
    """
    Shadow catalyst lens for already-identified tickers.

    This does not authorize capital. It stamps catalyst truth, event convexity,
    cheap-convexity, and liquidity context into the artifacts that later UAT
    stages read.
    """
    logger.info("=" * 80)
    logger.info("CATALYST TRUTH ENGINE%s", f" ({stage})" if stage else "")
    logger.info("=" * 80)
    try:
        from catalyst_truth_engine import enrich_run

        summary = enrich_run(run_id=run_id, base_dir=cfg.BASE_DIR, patch_existing=True)
        patched = [
            item for item in summary.get("patch_results", [])
            if item.get("status") == "patched"
        ]
        logger.info(
            "Catalyst Truth complete%s: rows=%d detected=%d dated=%d inside_dte=%d "
            "event_convexity=%d manual=%d/%d patched=%d",
            f" ({stage})" if stage else "",
            summary.get("rows", 0),
            summary.get("catalyst_detected", 0),
            summary.get("dated_catalysts", 0),
            summary.get("inside_dte", 0),
            summary.get("event_convexity_watch", 0),
            summary.get("manual_with_dated_catalyst", 0),
            summary.get("manual_tickers", 0),
            len(patched),
        )
        if summary.get("manual_tickers", 0) and not summary.get("manual_with_dated_catalyst", 0):
            logger.warning(
                "Catalyst Truth: manual/new tickers were processed, but none have "
                "a dated catalyst packet. They remain advisory until confirmed."
            )
        return True
    except ImportError as exc:
        logger.warning("Catalyst Truth skipped: catalyst_truth_engine.py not available (%s)", exc)
        return True
    except Exception as exc:
        logger.warning("Catalyst Truth failed non-critically: %s", exc)
        return True


def run_market_context_read_only_diagnostics(run_id: str, data_mode: str = "EOD") -> bool:
    """
    P10/P11 read-only diagnostics.

    P10 emits market breadth context for the candidate slate.
    P11 emits an intraday regime watchdog message for LATEST mode.

    This layer is deliberately advisory only: it does not mutate candidates,
    rankings, EIL verdicts, sizing, or capital permission.
    """
    logger.info("=" * 80)
    logger.info("P10/P11 READ-ONLY MARKET CONTEXT DIAGNOSTICS")
    logger.info("=" * 80)
    try:
        from market_context_diagnostics import run_read_only_market_context_diagnostics

        result = run_read_only_market_context_diagnostics(
            run_id=run_id,
            base_dir=cfg.BASE_DIR,
            data_mode=data_mode,
        )
        summary = result.get("summary", {})
        logger.info("P10 Market Breadth: %s", summary.get("market_breadth_message", "No message"))
        logger.info("P11 Intraday Watch: %s", summary.get("intraday_watchdog_message", "No message"))
        logger.info(
            "P10/P11 diagnostics written under run diagnostics folder | advisory_only=%s | mutates_outputs=%s",
            summary.get("advisory_only", True),
            summary.get("mutates_pipeline_outputs", False),
        )
        return True
    except ImportError as exc:
        logger.warning("P10/P11 diagnostics skipped: market_context_diagnostics.py not available (%s)", exc)
        return True
    except Exception as exc:
        logger.warning("P10/P11 diagnostics failed non-critically: %s", exc)
        return True


# ============================================================ PHASE 10: PREMARKET INTEL

def run_premarket_intelligence() -> bool:
    """Run premarket intelligence — reads discovery outputs."""
    logger.info("=" * 80)
    logger.info("PHASE 10: PREMARKET INTELLIGENCE")
    logger.info("=" * 80)

    ultimate_files = list(cfg.OUTPUT_DIR.glob("early_positions_ultimate_*.csv"))
    v3_files = list(cfg.OUTPUT_DIR.glob("early_position_candidates_*.csv"))

    if not ultimate_files and not v3_files:
        logger.warning("⚠️  No signal files found — run evening workflow first\n")
        return False

    if ultimate_files:
        latest = sorted(ultimate_files)[-1]
        logger.info(f"📊 Using ULTIMATE files — latest: {latest.name}")
    else:
        latest = sorted(v3_files)[-1]
        logger.info(f"📊 Using v3 HYBRID files — latest: {latest.name}")

    if not cfg.PREMARKET_INTEL.exists():
        logger.warning("⏭️  Premarket intel script not found — skipping\n")
        return True

    return _run("Premarket Intelligence", [sys.executable, str(cfg.PREMARKET_INTEL), "--top", "20"], critical=False)


# ============================================================ PHASE 10: ARCHIVE + PRUNE + REPORT

def archive_outputs(run_id: str) -> bool:
    """Archive current run outputs (never deletes originals)."""
    logger.info("=" * 80)
    logger.info("PHASE 10: ARCHIVE")
    logger.info("=" * 80)

    current_run_dir = cfg.RUNS_DIR / run_id
    if not current_run_dir.exists():
        logger.error(f"❌ ARCHIVE ABORTED — run directory does not exist: {current_run_dir}\n")
        return False

    archive_session = cfg.ARCHIVE_DIR / run_id
    archive_session.mkdir(parents=True, exist_ok=True)

    copied = 0
    for f in cfg.OUTPUT_DIR.glob("*.*"):
        if f.is_file():
            shutil.copy2(f, archive_session / f.name)
            copied += 1

    dest_run = archive_session / "runs" / run_id
    if dest_run.exists():
        shutil.rmtree(dest_run)
    shutil.copytree(current_run_dir, dest_run)
    copied += sum(1 for _ in dest_run.rglob("*") if _.is_file())

    logger.info(f"✅ Archived {copied} files → {archive_session}\n")
    return True


def prune_old_runs() -> None:
    """Prune old run directories from data/output/runs/ (after archive)."""
    logger.info("=" * 80)
    logger.info("PHASE 10c: PRUNE OLD RUNS")
    logger.info("=" * 80)

    if not cfg.RUNS_DIR.exists():
        logger.info("⏭️  Runs directory does not exist — nothing to prune\n")
        return

    all_runs = sorted([d for d in cfg.RUNS_DIR.iterdir() if d.is_dir()], key=lambda d: d.name)
    keep = cfg.RUNS_RETENTION_DAYS
    to_prune = all_runs[:-keep] if len(all_runs) > keep else []

    if not to_prune:
        logger.info(f"✅ No pruning needed — {len(all_runs)} runs present ({keep} retention limit)\n")
        return

    logger.info(f"   Total runs    : {len(all_runs)}")
    logger.info(f"   Keeping       : {keep} most recent")
    logger.info(f"   Pruning       : {len(to_prune)} old runs")

    pruned = 0
    errors = 0
    for old_run in to_prune:
        try:
            shutil.rmtree(old_run)
            logger.info(f"   🗑️  Pruned: {old_run.name}")
            pruned += 1
        except Exception as e:
            logger.warning(f"   ⚠️  Could not prune {old_run.name}: {e}")
            errors += 1

    logger.info(f"✅ Pruned {pruned} old runs" + (f" ({errors} errors)" if errors else "") + "\n")


def write_latest_json(discovery_run_id: str, workflow_run_id: str) -> None:
    """Write data/output/latest.json (points to canonical run_id)."""
    index_path = cfg.RUNS_DIR / discovery_run_id / "packages" / "index.json"
    if not index_path.exists():
        logger.warning(
            f"⚠️  latest.json NOT written — packages/index.json missing for run {discovery_run_id}.\n"
            f"   Expected: {index_path}"
        )
        return

    latest = {
        "run_id": discovery_run_id,
        "workflow_run_id": workflow_run_id,
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    target = cfg.OUTPUT_DIR / "latest.json"
    try:
        with open(target, "w", encoding="utf-8") as f:
            json.dump(latest, f, indent=2)
        logger.info(f"📌 latest.json updated → run_id: {discovery_run_id}")
    except Exception as e:
        logger.warning(f"⚠️  Could not write latest.json (non-fatal): {e}")


def generate_report(summary: dict, canonical_run_id: str, session_id: str) -> None:
    """Print final orchestration summary."""
    logger.info("=" * 80)
    logger.info("📊 ORCHESTRATION SUMMARY")
    logger.info("=" * 80)

    universe_size = summary.get("universe_size", 0)
    total_candidates = summary.get("total_candidates", 0)
    tier_0_early = summary.get("tier_0_early", 0)

    candidate_ratio_pct = (total_candidates / universe_size * 100) if universe_size > 0 else 0.0
    early_ratio_pct = (tier_0_early / universe_size * 100) if universe_size > 0 else 0.0

    logger.info(f"  Canonical Run ID: {canonical_run_id}  ← artefact folder + packages")
    logger.info(f"  Session ID      : {session_id}  ← orchestrator start (audit only)")
    logger.info(f"  Timestamp       : {summary.get('timestamp', 'N/A')}")
    logger.info(f"  Universe        : {universe_size} tickers")
    logger.info(f"  Scanned         : {summary.get('tickers_scanned', 0)} tickers\n")

    logger.info("  SIGNALS:")
    logger.info(f"    🎯 Tier 0 Early    : {tier_0_early}")
    logger.info(f"    🚨 Tier 1 Confirmed: {summary.get('tier_1_confirmed', 0)}")
    logger.info(f"    📊 Tier 2 Observe  : {summary.get('tier_2_observe', 0)}")
    logger.info(f"    👀 Tier 3 Watch    : {summary.get('tier_3_watch', 0)}")
    logger.info(f"    📈 TOTAL           : {total_candidates}\n")

    logger.info(f"  Candidate ratio : {candidate_ratio_pct:.1f}%")
    logger.info(f"  Early ratio     : {early_ratio_pct:.1f}%\n")

    vanguard_summary_path = cfg.RUNS_DIR / canonical_run_id / "vanguard" / "vanguard_run_summary.json"
    if vanguard_summary_path.exists():
        try:
            with open(vanguard_summary_path, "r", encoding="utf-8") as f:
                vs = json.load(f)
            pkgs_total = vs.get("packages_total", "?")
            passed = vs.get("passed", "?")
            rejected = vs.get("rejected", "?")
            pass_rate = f"{passed / pkgs_total * 100:.1f}%" if isinstance(pkgs_total, int) and pkgs_total > 0 else "?"
            logger.info("  VANGUARD:")
            logger.info(f"    📦 Packages processed: {pkgs_total}")
            logger.info(f"    ✅ Passed             : {passed}  ({pass_rate})")
            logger.info(f"    ❌ Rejected           : {rejected}")
            top_reasons = vs.get("reject_top_reasons", [])
            if top_reasons:
                logger.info("    Top reject reasons:")
                for code, n in top_reasons[:5]:
                    logger.info(f"      - {code}: {n}")
            logger.info("")
        except Exception as e:
            logger.warning(f"⚠️  Could not read vanguard_run_summary.json (non-fatal): {e}")
    else:
        logger.info("  VANGUARD: summary not found (check run folder)\n")

    # ── Horizon Routing Summary (v2.8) ──────────────────────────────────────────
    # Read horizon_summary_{run_id}.json written by Phase 1B router to give
    # the operator a clear picture of how signals were distributed across the
    # three trading horizons for this session.
    _hr_summary_path = cfg.RUNS_DIR / canonical_run_id / "horizon" / f"horizon_summary_{canonical_run_id}.json"
    if _hr_summary_path.exists():
        try:
            with open(_hr_summary_path, "r", encoding="utf-8") as _hrf:
                _hrs = json.load(_hrf)
            _hcounts = _hrs.get("horizon_counts", {})
            _hbiases = _hrs.get("horizon_biases", {})
            logger.info("  HORIZON ROUTING (Phase 1B — Macro Router):")
            logger.info(f"    Regime          : {_hrs.get('regime_state','?')}")
            logger.info(f"    Conviction      : {_hrs.get('macro_conviction',0):.2f}  |  Momentum: {_hrs.get('macro_momentum_score',0):.2f}")
            for _hk in ("1_5d", "6_10d", "11_20d", "blocked"):
                _hb_info = _hbiases.get(_hk, {})
                _hb_dir  = _hb_info.get("direction", "?")
                _hb_prob = _hb_info.get("bullish_prob_pct", 0)
                _hb_act  = _hb_info.get("action", "?")
                _hb_size = _hb_info.get("size_multiplier", 0)
                _hb_cnt  = _hcounts.get(_hk, 0)
                if _hk != "blocked":
                    logger.info(
                        f"    {_hk:8s}        : {_hb_cnt:4d} signals | {_hb_prob:.1f}% {_hb_dir} | "
                        f"{_hb_act} | size={_hb_size:.2f}x"
                    )
                else:
                    logger.info(f"    blocked         : {_hb_cnt:4d} signals (sector AVOID / LLR / VIX gate)")
            logger.info("")
        except Exception as _hr_err:
            logger.debug(f"Could not read horizon summary (non-fatal): {_hr_err}")
    else:
        logger.info("  HORIZON ROUTING: summary not found (Phase 1B may not have run)\n")

    # ── Monetisation Policy summary (from SuperBrain JSON) ────────────────────
    sb_summary_dir = cfg.RUNS_DIR / canonical_run_id / "superbrain"
    sb_json_candidates = sorted(sb_summary_dir.glob("superbrain_summary_*.json"),
                                 key=lambda p: p.stat().st_mtime, reverse=True) if sb_summary_dir.exists() else []
    if sb_json_candidates:
        try:
            with open(sb_json_candidates[0], "r", encoding="utf-8") as f:
                sb_sum = json.load(f)
            mp = sb_sum.get("monetisation_policy", {})
            if mp:
                logger.info("  MONETISATION POLICY (advisory Phase 1):")
                logger.info(f"    Engine available : {mp.get('engine_available', False)}")
                logger.info(f"    GO               : {mp.get('go_count', 0)}")
                logger.info(f"    GO_SMALL         : {mp.get('go_small_count', 0)}")
                logger.info(f"    GO_LATE          : {mp.get('go_late_count', 0)}")
                logger.info(f"    WAIT             : {mp.get('wait_count', 0)}")
                logger.info(f"    BLOCK_*          : {mp.get('block_count', 0)}")
                logger.info(f"    Avg final size   : {mp.get('avg_final_size', 0):.1%}")
                logger.info(f"    ⚠️  15-min delay: All quote data delayed — verify on Tastytrade before entry")
                logger.info("")
            fv = sb_sum.get("final_verdicts", {})
            if fv:
                logger.info("  SUPERBRAIN VERDICTS:")
                logger.info(f"    EXECUTE          : {fv.get('EXECUTE', 0)}")
                logger.info(f"    EXECUTE_WITH_RISK: {fv.get('EXECUTE_WITH_RISK', 0)}")
                logger.info(f"    ARMED            : {fv.get('ARMED', 0)}")
                logger.info(f"    STAND_DOWN       : {fv.get('STAND_DOWN', 0)}")
                logger.info(f"    DATA_FAILURE     : {fv.get('DATA_FAILURE', 0)}")
                logger.info("")
        except Exception as e:
            logger.warning(f"⚠️  Could not read superbrain summary (non-fatal): {e}")


# ============================================================ PHASE 9C =======

def run_phase_9c(cfg: OrchestratorConfig, run_id: str) -> dict:
    """
    Phase 9C: Trade Book Builder — converts enhanced_{run_id}.csv into
    final_trades_{run_id}.csv and trade_book_summary_{run_id}.json.

    This is THE MISSING PIECE: enhancement_integration.py (Phase 9B) writes
    a fully scored and sized enhanced CSV — pse_final_size, kelly_dollar_risk_adj,
    conv_score, eil_v3_verdict etc. all populated — but nothing reads that file
    and commits to a ranked trade list. Phase 9C closes that gap.

    Input:  data/output/runs/{run_id}/superbrain/enhanced_{run_id}.csv
    Output: data/output/runs/{run_id}/trades/final_trades_{run_id}.csv
            data/output/runs/{run_id}/trades/trade_book_summary_{run_id}.json

    Non-critical: pipeline continues unaffected if this fails.
    """
    try:
        from trade_book_builder import build_and_write
    except ImportError as e:
        logger.warning("⚠️  Phase 9C: trade_book_builder not found — phase skipped. Error: %s", e)
        return {"trade_count": 0, "status": "SKIPPED_NO_MODULE"}

    sb_dir       = cfg.RUNS_DIR / run_id / "superbrain"
    enhanced_csv = sb_dir / f"enhanced_{run_id}.csv"

    if not enhanced_csv.exists():
        logger.warning("⚠️  Phase 9C: enhanced CSV not found at %s — phase skipped", enhanced_csv)
        return {"trade_count": 0, "status": "SKIPPED_NO_INPUT"}

    trades_dir = cfg.RUNS_DIR / run_id / "trades"

    logger.info("=" * 70)
    logger.info("PHASE 9C: TRADE BOOK BUILDER")
    logger.info("=" * 70)

    result = build_and_write(
        enhanced_csv  = enhanced_csv,
        output_dir    = trades_dir,
        run_id        = run_id,
        account_size  = cfg.ACCOUNT_SIZE,
        max_positions = cfg.MAX_POSITIONS,
        max_probe_pos = cfg.MAX_PROBE_POS,
    )

    trade_count      = result.get("trade_count", 0)
    deployment_pct   = result.get("total_deployment_pct", 0.0)
    output_csv       = result.get("output_csv", "unknown")

    if trade_count > 0:
        logger.info(
            "🎯 Phase 9C complete — %d trades | %.2f%% capital deployed | %s",
            trade_count, deployment_pct, output_csv,
        )
    else:
        logger.warning(
            "⚠️  Phase 9C — 0 trades selected. "
            "Check enhanced CSV for pse_final_size > 0, kelly_verdict != NO_TRADE, "
            "conv_trade_gate == PASS. Status: %s",
            result.get("status", "?"),
        )

    return result


# ============================================================ WORKFLOWS ======

def evening_workflow(
    run_id: Optional[str] = None,
    min_universe: int = 1000,
    target_universe: int = 6500,
    universe_gate_mode: str = "AUTO",
    force: bool = False,
    universe_override: Optional[Path] = None,
    data_mode: str = "EOD",
) -> bool:
    """
    Evening workflow: preflight → discovery → validate → vanguard → post-process → archive.

    data_mode controls how bar data is sourced:
      EOD    — uses yesterday's completed daily bars (default, requires post-16:15 ET)
      LATEST — uses the most recent Polygon snapshot bars (safe to run at any time)
               Intraday bars will be incomplete if run during market hours.
               TCE confirmation will use whatever bars are available.
               All output rows are stamped data_mode=LATEST so MVE applies
               EOD thresholds (lower MVS requirement, PARTIAL trigger accepted).
    """
    session_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    _data_mode = str(data_mode).upper().strip()
    if _data_mode not in ("EOD", "LATEST"):
        logger.warning("⚠️  Unknown data_mode '%s' — defaulting to EOD", _data_mode)
        _data_mode = "EOD"

    # ── MARKET HOURS GUARD ────────────────────────────────────────────────────
    # EOD mode: pipeline must run after market close (16:15 ET) to ensure
    # complete daily bars and valid TCE confirmation.
    # LATEST mode: pipeline runs at any time using the most recent snapshot.
    # TCE will apply PARTIAL trigger logic (same as EOD synthetic mode).
    from datetime import time as dtime
    _now_utc = datetime.now(timezone.utc)
    _et_offset = -4  # EDT (UTC-4); change to -5 in winter (EST)
    _now_et_hour = (_now_utc.hour + _et_offset) % 24
    _now_et_min  = _now_utc.minute
    _now_et_time = _now_et_hour * 60 + _now_et_min
    _market_open  = 9 * 60 + 30
    _market_close = 16 * 60 + 15
    _et_date     = (_now_utc + __import__('datetime').timedelta(hours=_et_offset)).date()
    _is_weekend  = _et_date.weekday() >= 5
    _in_market_hours = (_market_open <= _now_et_time < _market_close) and not _is_weekend

    if _data_mode == "LATEST":
        # LATEST mode: always allowed regardless of time
        if _in_market_hours:
            logger.info("=" * 70)
            logger.info("📊  EVENING PIPELINE — DATA MODE: LATEST (intraday)")
            logger.info(f"   Running at {_now_et_hour:02d}:{_now_et_min:02d} ET — market is OPEN.")
            logger.info("   Polygon snapshot bars will be used (may be incomplete).")
            logger.info("   All signals stamped data_mode=LATEST → MVE uses EOD thresholds.")
            logger.info("   Output is valid for review. Trade decisions should confirm")
            logger.info("   at morning validation once market closes.")
            logger.info("=" * 70)
        else:
            logger.info("📊  DATA MODE: LATEST — post-close snapshot bars")
    elif _in_market_hours and not force:
        _et_str = f"{_now_et_hour:02d}:{_now_et_min:02d} ET"
        logger.error("=" * 70)
        logger.error("⛔  MARKET HOURS GUARD — EVENING PIPELINE BLOCKED")
        logger.error(f"    Current time : {_et_str} (market open 09:30–16:15 ET)")
        logger.error("    EOD mode requires completed daily bars after 16:15 ET.")
        logger.error("    Options:")
        logger.error("      1. Wait until 16:15 ET then run normally")
        logger.error("      2. Run now with latest snapshot: --data-mode LATEST")
        logger.error("      3. Override (research only): --force")
        logger.error("=" * 70)
        return False
    elif _in_market_hours and force:
        logger.warning("=" * 70)
        logger.warning("⚠️  MARKET HOURS GUARD BYPASSED (--force)")
        logger.warning(f"   Running at {_now_et_hour:02d}:{_now_et_min:02d} ET — market is OPEN.")
        logger.warning("   EOD candidates will use incomplete intraday bars.")
        logger.warning("   Use --data-mode LATEST instead for a cleaner run.")
        logger.warning("=" * 70)
    # ── END MARKET HOURS GUARD ────────────────────────────────────────────────

    logger.info("\n" + "=" * 80)
    logger.info("🌆  EVENING WORKFLOW — DISCOVERY & VANGUARD")
    logger.info(f"    Session ID : {session_id}  (orchestrator start — logging only)")
    logger.info("=" * 80 + "\n")

    # ── PHASE 0: Universe Scanner Consumer ───────────────────────────────────
    _scanner = merge_scanner_inputs(load_scanner_manifest(), load_manual_ticker_upload())
    _augmented_universe_path = build_augmented_universe(_scanner, session_id)
    try:
        # UAT-AUDIT: capture the raw Phase 0 scanner/catalyst/manual intake state
        # before discovery or downstream scoring can hide a root cause.
        (cfg.RUNS_DIR / session_id).mkdir(parents=True, exist_ok=True)
        write_scanner_context(_scanner, session_id)
    except Exception as _phase0_ctx_err:
        logger.warning("Phase 0 audit context write failed: %s", _phase0_ctx_err)
    run_dropoff_audit_checkpoint(session_id, "phase0_intake")
    # ─────────────────────────────────────────────────────────────────────────

    preflight_ok, macro_path = run_preflight_checks(
        min_universe=min_universe,
        target_universe=target_universe,
        universe_gate_mode=universe_gate_mode,
    )
    if not preflight_ok or macro_path is None:
        return False

    # ── SECTOR BIAS MAP — built once, passed to all downstream modules ────────
    # v1.1: load sector_rotation block from macro JSON into memory so all
    # modules (superbrain, options intelligence, EIL, FDE, monetisation policy)
    # can call classify_sector_alignment() without re-reading the macro file.
    global _sector_bias_map, _macro_conviction, _macro_quant_packet, _macro_regime_state
    _sector_bias_map   = {}
    _macro_conviction  = 0.60
    _macro_quant_packet = {}
    _macro_regime_state = ""
    try:
        with open(macro_path, "r", encoding="utf-8") as _mf:
            _macro_raw = json.load(_mf)
        _macro_quant_packet = build_macro_quant_packet(_macro_raw, macro_path)
        logger.info(
            "✅ Macro quant packet loaded: regime=%s freshness=%s quality=%s",
            _macro_quant_packet.get("macro_regime_label", "UNKNOWN"),
            _macro_quant_packet.get("macro_freshness_status", "UNKNOWN"),
            _macro_quant_packet.get("macro_data_quality", "UNKNOWN"),
        )
        # Inline import — sector_alignment.py may live in scripts/
        import importlib.util as _ilu
        _sa_path = cfg.SECTOR_ALIGNMENT_UTIL
        if _sa_path.exists():
            _sa_spec = _ilu.spec_from_file_location("sector_alignment", str(_sa_path))
            _sa_mod  = _ilu.module_from_spec(_sa_spec)
            _sa_spec.loader.exec_module(_sa_mod)
            _sector_bias_map   = _sa_mod.load_sector_bias_map(_macro_raw)
            _macro_conviction  = _sa_mod.load_macro_conviction(_macro_raw)
            _macro_regime_state = str(_macro_raw.get("regime_state", "") or "")
            logger.info(
                "✅ Sector bias map loaded: %d sectors | macro_conviction=%.2f | "
                "rotation_signal=%s",
                len(_sector_bias_map),
                _macro_conviction,
                _macro_raw.get("sector_rotation", {}).get("rotation_signal", "N/A"),
            )
            # Log top tailwinds and headwinds for operator visibility
            _tw = [s for s, b in _sector_bias_map.items() if b == "TAILWIND"]
            _hw = [s for s, b in _sector_bias_map.items() if b == "HEADWIND"]
            if _tw: logger.info("   TAILWIND sectors : %s", ", ".join(_tw))
            if _hw: logger.info("   HEADWIND sectors : %s", ", ".join(_hw))
        else:
            # Patch 2 — production guard: sector alignment is mandatory for live capital
            # AVSHUNTER_REQUIRE_SECTOR_ALIGNMENT=false to disable (research/dry-run only)
            _require_sa = os.environ.get("AVSHUNTER_REQUIRE_SECTOR_ALIGNMENT", "true").lower() == "true"
            _sa_msg = (
                f"sector_alignment.py not found at {_sa_path}. "
                "Macro sector alignment cannot be applied — HEADWIND tickers will be sized identically to TAILWIND. "
                "Deploy scripts/sector_alignment.py before running live capital. "
                "Set AVSHUNTER_REQUIRE_SECTOR_ALIGNMENT=false to bypass (research mode only)."
            )
            if _require_sa:
                logger.error("🔴 %s", _sa_msg)
                return False   # abort pipeline — live capital cannot run without sector alignment
            else:
                logger.warning("⚠️  %s", _sa_msg)
    except Exception as _sa_err:
        _macro_quant_packet = missing_macro_quant_packet(macro_path)
        logger.error("🔴 Sector bias map load failed: %s — continuing without sector alignment", _sa_err)
    # ─────────────────────────────────────────────────────────────────────────

    # ── FIX-04/07: Normalise macro contract before pipeline runs ──────────────
    # Adds 4 structured score fields (net_liquidity_score, vix_regime_score,
    # gex_regime_score, macro_momentum_score) that RegimeConsensus needs to
    # run in "structured" mode. Also checks macro freshness.
    _macro_normalised_ok = True   # default: assume OK until proven otherwise
    _normalise_script = cfg.SCRIPTS_DIR / "normalise_macro_contract.py"
    # DEFECT 4 FIX: Macro is not decoration. Macro determines regime, horizon
    # routing, risk drawer, and put/call permission. Track normalisation outcome
    # and degrade the manifest permission if it fails — do not silently continue.
    _macro_normalised_ok = False
    if _normalise_script.exists():
        logger.info("── FIX-04: Normalising macro contract (adding structured scores)...")
        _nm_ok = _run(
            "Macro Normaliser",
            [sys.executable, str(_normalise_script), "--macro-path", str(macro_path)],
            critical=False,
        )
        if _nm_ok:
            _macro_normalised_ok = True
            logger.info("✅ Macro normaliser completed successfully")
        else:
            _macro_normalised_ok = False
            logger.error(
                "🔴 MACRO NORMALISER FAILED — regime, horizon routing, and risk "
                "drawer will operate on unnormalised macro data. "
                "Manifest will be set to REVIEW_ONLY_MACRO_DEGRADED. "
                "Check scripts/normalise_macro_contract.py"
            )
    else:
        _macro_normalised_ok = False
        logger.error(
            "🔴 normalise_macro_contract.py NOT FOUND at %s — "
            "macro regime scores will be absent. "
            "Manifest will be set to REVIEW_ONLY_MACRO_DEGRADED. "
            "Deploy scripts/normalise_macro_contract.py before running live capital.",
            _normalise_script,
        )
    # ─────────────────────────────────────────────────────────────────────────

    try:
        with open(macro_path, "r", encoding="utf-8") as _mf:
            _macro_refreshed = json.load(_mf)
        _macro_quant_packet = build_macro_quant_packet(_macro_refreshed, macro_path)
        _macro_refreshed["macro_quant_packet"] = _macro_quant_packet
        write_json(macro_path, _macro_refreshed)
        logger.info(
            "✅ Macro quant packet refreshed after normalisation: freshness=%s quality=%s",
            _macro_quant_packet.get("macro_freshness_status", "UNKNOWN"),
            _macro_quant_packet.get("macro_data_quality", "UNKNOWN"),
        )
    except Exception as _mq_err:
        if not _macro_quant_packet:
            _macro_quant_packet = missing_macro_quant_packet(macro_path)
        logger.warning("⚠️  Macro quant packet refresh failed: %s", _mq_err)

    # ── BOND MACRO SIDECAR: Merge bond_macro_state.json ─────────────────────
    # Written by bond_macro_intelligence.py to dropbox/macro/ before the
    # evening run. Non-critical — pipeline continues if file is absent.
    _bond_macro_path = cfg.MACRO_DIR / "bond_macro_state.json"
    if _bond_macro_path.exists():
        try:
            with open(_bond_macro_path, "r", encoding="utf-8") as _bf:
                _bond_state = json.load(_bf)
            with open(macro_path, "r", encoding="utf-8") as _mf:
                _macro_live = json.load(_mf)
            # Inject bond macro fields into extras — augment only, never replace
            _extras = _macro_live.setdefault("extras", {})
            _extras["bond_macro"] = {
                "curve_state":            _bond_state.get("yield_curve", {}).get("curve_state", "UNKNOWN"),
                "yield_2y":               _bond_state.get("yield_curve", {}).get("yield_2y"),
                "yield_10y":              _bond_state.get("yield_curve", {}).get("yield_10y"),
                "spread_bps":             _bond_state.get("yield_curve", {}).get("spread_bps"),
                "russell_tailwind":       _bond_state.get("yield_curve", {}).get("russell_tailwind", False),
                "zn_direction":           _bond_state.get("zn_direction", {}).get("rate_regime_signal", "UNKNOWN"),
                "credit_stress_flag":     _bond_state.get("credit_stress", {}).get("stress_flag", "UNKNOWN"),
                "credit_z_score":         _bond_state.get("credit_stress", {}).get("z_score"),
                "auction_spread_risk":    _bond_state.get("auction_calendar", {}).get("auction_today", False),
                "bond_macro_flag":        _bond_state.get("composite", {}).get("flag", "UNKNOWN"),
                "bond_macro_score":       _bond_state.get("composite", {}).get("score"),
                "breakeven_adjustment_pct": _bond_state.get("composite", {}).get("breakeven_adjustment_pct", 0),
                "trade_go":               _bond_state.get("composite", {}).get("trade_go", True),
                "summary":                _bond_state.get("composite", {}).get("summary", ""),
                "as_of_date":             _bond_state.get("as_of_date", ""),
                "data_source":            _bond_state.get("yield_curve", {}).get("data_source", "UNKNOWN"),
            }
            write_json(macro_path, _macro_live)
            logger.info(
                "✅ Bond macro sidecar merged: flag=%s score=%s curve=%s breakeven_adj=+%s%%",
                _extras["bond_macro"]["bond_macro_flag"],
                _extras["bond_macro"]["bond_macro_score"],
                _extras["bond_macro"]["curve_state"],
                _extras["bond_macro"]["breakeven_adjustment_pct"],
            )
        except Exception as _bm_err:
            logger.warning("⚠️  Bond macro sidecar merge failed: %s — continuing without bond context", _bm_err)
    else:
        logger.info("ℹ️  bond_macro_state.json not found — run bond_macro_intelligence.py before evening run for bond context")
    # ─────────────────────────────────────────────────────────────────────────

    # ── PHASE 4.6: Actuarial Cache Build ─────────────────────────────────────
    # MACRO REDESIGN: enrichment delta is context-only narrative overlay.
    # Its failure must never abort the pipeline — degrade gracefully with base macro.
    _enrichment_merge_degraded = False
    try:
        _enrichment_ok = merge_macro_enrichment_into_macro_latest(macro_path)
        if not _enrichment_ok:
            logger.warning(
                "[MACRO] Enrichment merge returned False. "
                "Continuing with base macro. Pipeline will not abort."
            )
            _enrichment_merge_degraded = True
    except Exception as _e_enrich:
        logger.warning(
            "[MACRO] Enrichment delta merge failed: %s. "
            "Continuing with base macro only. _enrichment_merge_degraded=True.",
            _e_enrich,
        )
        _enrichment_merge_degraded = True

    # Must run AFTER macro normalisation (macro_regime labels are now clean)
    # and BEFORE build_packages_from_discovery.py (which injects pkg["actuarial"]
    # into every package using the cache).
    # Location: C:/Users/ACKVerissimo/vanguard/actuarial_cache_builder.py
    # NON-CRITICAL: if the builder fails or is not deployed, packages build
    # normally without actuarial enrichment. A warning is logged for review.
    if cfg.ACTUARIAL_CACHE_BUILDER.exists():
        try:
            import importlib.util as _ilu
            _act_spec = _ilu.spec_from_file_location(
                "actuarial_cache_builder", str(cfg.ACTUARIAL_CACHE_BUILDER)
            )
            _act_mod = _ilu.module_from_spec(_act_spec)
            _act_spec.loader.exec_module(_act_mod)
            _act_result = _act_mod.run_from_orchestrator(incremental=True)
            if _act_result.get("success"):
                logger.info(
                    "✅ Phase 4.6 (Actuarial Cache) — %s states | %s valid | %s rows processed",
                    _act_result.get("states_built", "?"),
                    _act_result.get("valid_states", "?"),
                    _act_result.get("rows_processed", "?"),
                )
                if cfg.ACTUARIAL_CACHE_PATH.exists():
                    logger.info(
                        "   Cache ready: %s (%.1f KB)",
                        cfg.ACTUARIAL_CACHE_PATH.name,
                        cfg.ACTUARIAL_CACHE_PATH.stat().st_size / 1024,
                    )
                else:
                    logger.warning(
                        "⚠️  Actuarial cache reported success but file not found: %s",
                        cfg.ACTUARIAL_CACHE_PATH,
                    )
            else:
                logger.warning(
                    "⚠️  Phase 4.6 (Actuarial Cache) failed — pipeline continues without "
                    "actuarial enrichment. Error: %s",
                    _act_result.get("error", "unknown"),
                )
        except Exception as _act_err:
            logger.warning(
                "⚠️  Phase 4.6 (Actuarial Cache) exception — pipeline continues. Error: %s",
                _act_err,
            )
    else:
        logger.warning(
            "⏭️  Phase 4.6 (Actuarial Cache) skipped — not deployed at: %s\n"
            "   Packages will build without actuarial enrichment.",
            cfg.ACTUARIAL_CACHE_BUILDER,
        )
    # ─────────────────────────────────────────────────────────────────────────


    # PHASE 4.7: Actuarial Transition Matrix
    # Derived artifact only. Non-critical: if this fails, the EOD pipeline continues.
    # Reads the latest actuarial DB and writes phase-to-phase transition probabilities
    # for research/Lab/interpreter consumption.
    if cfg.ACTUARIAL_TRANSITION_MATRIX_BUILDER.exists():
        _tm_cmd = [
            sys.executable,
            str(cfg.ACTUARIAL_TRANSITION_MATRIX_BUILDER),
            "--actuarial-db",
            str(cfg.ACTUARIAL_DB_PATH),
            "--output-dir",
            str(cfg.ACTUARIAL_TRANSITION_MATRIX_DIR),
            "--phase-column",
            "phase_v2",
        ]
        _tm_ok = _run("Phase 4.7 Actuarial Transition Matrix", _tm_cmd, critical=False)
        if _tm_ok and cfg.ACTUARIAL_TRANSITION_MATRIX_LATEST.exists():
            logger.info(
                "   Transition matrix ready: %s (%.1f KB)",
                cfg.ACTUARIAL_TRANSITION_MATRIX_LATEST,
                cfg.ACTUARIAL_TRANSITION_MATRIX_LATEST.stat().st_size / 1024,
            )
        elif _tm_ok:
            logger.warning(
                "Phase 4.7 transition matrix reported success but latest file not found: %s",
                cfg.ACTUARIAL_TRANSITION_MATRIX_LATEST,
            )
    else:
        logger.warning(
            "Phase 4.7 transition matrix skipped â€” builder not found at: %s",
            cfg.ACTUARIAL_TRANSITION_MATRIX_BUILDER,
        )

    # DISC-02: Write stable scanner_context_latest.json BEFORE discovery runs
    # so discovery can inject VMS scores into composite scoring.
    # write_scanner_context() uses run_id (unknown until after discovery) —
    # so we write a separate "latest" copy here using session_id as a stable key.
    _scanner_ctx_latest: Optional[Path] = None
    if _scanner.get("available") and _scanner.get("vms_df") is not None:
        try:
            _ctx_latest_dir  = cfg.OUTPUT_DIR / "universe_scanner"
            _ctx_latest_dir.mkdir(parents=True, exist_ok=True)
            _scanner_ctx_latest = _ctx_latest_dir / "scanner_context_latest.json"
            write_scanner_context(_scanner, "latest")
            # write_scanner_context writes to RUNS_DIR/{run_id}/scanner_context_{run_id}.json
            # but we need the latest path — so write a second copy here
            import json as _jsc
            _vms_df = _scanner["vms_df"]
            _ctx_data = {
                "scanner_run_id":  _scanner.get("run_id"),
                "scanner_source": "UNIVERSE_SCANNER",
                "scanner_timestamp_utc": _scanner.get("timestamp_utc"),
                "scanner_age_hrs": _scanner.get("age_hrs"),
                "tickers": {
                    str(row.get("ticker", "")).strip(): {
                        "scanner_source":      "UNIVERSE_SCANNER",
                        "scanner_run_id":      _scanner.get("run_id"),
                        "scanner_timestamp_utc": _scanner.get("timestamp_utc"),
                        "scanner_age_hrs":     _scanner.get("age_hrs"),
                        "scanner_signal_type": str(row.get("decision", "") or ""),
                        "scanner_decision":    str(row.get("decision", "") or ""),
                        "scanner_direction":   str(row.get("direction", "") or ""),
                        "scanner_direction_reason": str(row.get("direction_reason", "") or ""),
                        "scanner_score":       int(row.get("score", 0) or 0),
                        "scanner_data_quality": "CONFIRMED",
                        "scanner_confidence":  round(max(0.0, min(1.0, float(row.get("score", 0) or 0) / 100.0)), 4),
                        "vms_score":          int(row.get("score", 0) or 0),
                        "vms_decision":       str(row.get("decision", "") or ""),
                        "iv_rank":            float(row.get("iv_rank", 0) or 0),
                        "vol_spread":         float(row.get("vol_spread", 0) or 0),
                    }
                    for _, row in _vms_df[_vms_df["decision"].isin(["GO", "PROBE"])].iterrows()
                    if str(row.get("ticker", "")).strip()
                }
            }
            with open(_scanner_ctx_latest, "w", encoding="utf-8") as _f:
                _jsc.dump(_ctx_data, _f, indent=2)
            logger.info("📡 Scanner context latest → %s (%d tickers)",
                        _scanner_ctx_latest.name, len(_ctx_data["tickers"]))
        except Exception as _sc_err:
            logger.warning("⚠️  Scanner context latest write failed (non-critical): %s", _sc_err)
            _scanner_ctx_latest = None

    # --universe override: bypass augmented universe and use the supplied test file.
    # This prevents the 3,000-ticker Polygon scan when running a 50-ticker test.
    _effective_universe = universe_override if universe_override and universe_override.exists() else _augmented_universe_path
    if universe_override:
        logger.info("🧪  TEST MODE: universe override active → %s", universe_override.name)
    success, summary, discovery_run_id = run_discovery(
        augmented_universe_path = _effective_universe,
        scanner_context_path    = _scanner_ctx_latest,
    )
    if not success or not summary or not discovery_run_id:
        return False

    canonical_run_id = discovery_run_id
    logger.info(f"✅ Canonical Run ID (artefacts): {canonical_run_id}\n")
    write_scanner_context(_scanner, canonical_run_id)
    apply_external_intel_review_lane(canonical_run_id, macro_path)
    apply_macro_enrichment_to_discovery(canonical_run_id, macro_path)

    valid, _ = validate_quality(summary)
    if not valid:
        logger.error("❌ EVENING WORKFLOW ABORTED — fix quality issues above\n")
        return False

    detect_regression(summary)     # non-blocking
    run_position_tracking()        # non-blocking

    # ── PHASE 1B: Macro Horizon Router ───────────────────────────────────────
    # Routes each discovery candidate to the correct trading horizon bucket
    # (1-5D / 6-10D / 11-20D) based on the forward bias stack in the macro
    # contract. This runs BEFORE Vanguard so the horizon_bucket column is
    # available to EIL, EDE, and EOD Candidate Engine.
    #
    # SPRINT 1 — DIRECTION-AGNOSTIC DOCTRINE:
    # Macro is a SIZING MULTIPLIER only. Both CALL and PUT candidates are
    # surfaced in ALL regimes. The multiplier from cfg.MACRO_DIRECTION_SIZING
    # is applied at sizing time — not at discovery time.
    #   TRANSITIONAL_BEARISH: CALL size = 0.50×PSE, PUT size = 1.00×PSE
    #   RISK_ON:              CALL size = 1.00×PSE, PUT size = 0.25×PSE
    #   Neither direction is ever blocked by regime alone.
    #
    # NON-CRITICAL: legacy single-bucket mode if router not deployed.
    # Phase 1B: Macro Horizon Router — moved to after Phase 8a (DEF-002 FIX)

    # ── PHASE 4.7: Regime-Adaptive Screener ──────────────────────────────────
    # Supplements main discovery with three additional signal types that
    # work in ALL regimes — not just directional momentum:
    #   TYPE 1: Mean Reversion   — overextended names at gamma walls
    #   TYPE 2: Vol Expansion    — compressed IV before catalyst (TRANSITIONAL)
    #   TYPE 3: Structural Breakout — Phase D/E with volume confirmation
    # Output: data/output/runs/{run_id}/regime_screener/regime_signals_{run_id}.csv
    # NON-CRITICAL: pipeline continues if screener fails.
    _regime_script = cfg.BASE_DIR / "avshunter_regime_screener.py"
    if _regime_script.exists():
        try:
            import importlib.util as _ilu
            import sys as _sys  # FIX-IMPORT-01: _sys must be local — not inherited from run_horizon_router()
            _rs_spec = _ilu.spec_from_file_location("avshunter_regime_screener", str(_regime_script))
            _rs_mod  = _ilu.module_from_spec(_rs_spec)
            _sys.modules["avshunter_regime_screener"] = _rs_mod  # FIX-IMPORT-01
            _rs_spec.loader.exec_module(_rs_mod)
            _rs_result = _rs_mod.run_regime_screener(run_id=canonical_run_id, base_dir=cfg.BASE_DIR)
            if _rs_result.get("success"):
                logger.info(
                    "✅ Phase 4.7 (Regime Screener) — MR=%d VE=%d SB=%d total=%d",
                    _rs_result.get("mean_reversion", 0),
                    _rs_result.get("vol_expansion", 0),
                    _rs_result.get("structural_breakout", 0),
                    _rs_result.get("total_signals", 0),
                )
        except Exception as _rs_err:
            logger.warning("⚠️  Phase 4.7 (Regime Screener) failed — pipeline continues. Error: %s", _rs_err)
    # ─────────────────────────────────────────────────────────────────────────

    if not run_vanguard_pipeline(canonical_run_id, macro_path, data_mode=_data_mode):
        logger.error("❌ EVENING WORKFLOW ABORTED — VANGUARD pipeline failed\n")
        return False

    # ── PHASE 8a: Options Intelligence ──────────────────────────────────────
    # DEF-001 FIX (v3.0): MUST run BEFORE Phase 8.5.
    # Catalyst Truth must run before Options Intelligence as well as after it.
    # The post-options pass enriches later artifacts, but it is too late to
    # widen the Options scope for high-truth catalyst names that Vanguard marks
    # WEAK/NEGATIVE. This pre-options pass patches discovery/vanguard artifacts
    # so the options layer can give those names a monetisation review lane.
    run_catalyst_truth_layer(canonical_run_id, stage="pre_options")

    run_position_lock_check(canonical_run_id)
    run_options_intelligence(canonical_run_id)     # MUST precede Phase 8.5

    # ── PHASE 1B: Macro Horizon Router ───────────────────────────────────────
    # NoneType.__dict__ crash (26-Apr) was caused by run_horizon_router()
    # accessing _sig._raw directly on a RoutedSignal dataclass. Fixed by
    # _ticker_to_raw lookup pattern already present in run_horizon_router().
    # Phase 1B is fully operational — do NOT disable again.
    _hr_result = run_horizon_router(cfg.MACRO_FILE, canonical_run_id)

    # ── PATCH-HORIZON Phase 1B-B: Stamp horizon fields into OI CSV ────────────
    # SuperBrain passthrough copies OI → superbrain_enriched. If OI carries
    # horizon_bucket/action/size_multiplier, superbrain gets them for free.
    # This is the primary injection point — before Phase 8d passthrough runs.
    _oi_horizon_target = (
        cfg.RUNS_DIR / canonical_run_id / "options" /
        f"vanguard_signals_enriched_{canonical_run_id}.csv"
    )
    patch_horizon_fields_into_csv(
        run_id     = canonical_run_id,
        target_csv = _oi_horizon_target,
        label      = "options_intelligence_OI",
    )
    run_catalyst_truth_layer(canonical_run_id, stage="post_options")

    # ── PATCH 2a: Duplicate removed ───────────────────────────────────────────
    # The patch above (label="options_intelligence_OI") already handles this.
    # Removing the redundant second call to the same target file.

    # ── PHASE 8.5: Actuarial Enrichment Pass ─────────────────────────────────
    # Runs AFTER Phase 8a so vanguard_signals_enriched is available.
    # ACB-01 (May 2026): enrichment pass now sends 9-field state keys:
    #   vol_regime | trend_direction | structure_quality | adx_bucket |
    #   wyckoff_phase_bucket | macro_regime |
    #   trend_maturity | catalyst_proximity | atr_pct_bucket
    # Requires: backfill_actuarial_db_acb01.py run ONCE, then cache rebuilt.
    # NON-CRITICAL: pipeline continues if pass fails.
    if cfg.ACTUARIAL_ENRICHMENT_PASS.exists():
        try:
            import importlib.util as _ilu
            _aep_spec = _ilu.spec_from_file_location(
                "actuarial_enrichment_pass", str(cfg.ACTUARIAL_ENRICHMENT_PASS)
            )
            _aep_mod = _ilu.module_from_spec(_aep_spec)
            _aep_spec.loader.exec_module(_aep_mod)
            _aep_result = _aep_mod.run_actuarial_enrichment_pass(
                run_id   = canonical_run_id,
                base_dir = cfg.BASE_DIR,
            )
            if _aep_result.get("success"):
                o = _aep_result.get("outcomes", {})
                logger.info(
                    "✅ Phase 8.5 (Actuarial Enrichment) — %d packages patched | "
                    "exact=%d fallback=%d no_match=%d no_vanguard=%d",
                    _aep_result.get("packages_patched", 0),
                    o.get("EXACT_MATCH", 0),
                    o.get("FALLBACK_MATCH", 0),
                    o.get("NO_MATCH", 0),
                    o.get("NO_VANGUARD_ROW", 0),
                )
                if o.get("EXACT_MATCH", 0) + o.get("FALLBACK_MATCH", 0) == 0:
                    logger.warning(
                        "⚠️  Phase 8.5: 0 actuarial matches — check:\n"
                        "   1. backfill_actuarial_db_acb01.py has been run (adds trend_maturity,\n"
                        "      catalyst_proximity, atr_pct_bucket to actuarial_database_v6.parquet)\n"
                        "   2. actuarial_cache_builder.py reads actuarial_database_v6.parquet (not v5)\n"
                        "      (cache must have 9-dim keys — 871 states = old 6-dim cache)\n"
                        "   3. actuarial_enrichment_pass.py is v1.5.0+ (9-field _VANGUARD_STATE_MAP)\n"
                        "   4. Sprint 3 V2 fields present in cache: phase_v2, momentum_bucket,\n"
                        "      location_bucket, future_momentum_bucket, signal_type, momentum_tier\n"
                        "   Required vanguard CSV columns: layer2__vol_regime, layer2__trend_direction,\n"
                        "   layer2__structure_quality, wyckoff_phase_bucket, macro_regime,\n"
                        "   trend_maturity, catalyst_proximity, atr_pct"
                    )
            else:
                logger.warning(
                    "⚠️  Phase 8.5 (Actuarial Enrichment) failed — EDE will score "
                    "with zero edge. Reason: %s",
                    _aep_result.get("reason", "unknown"),
                )
        except Exception as _aep_err:
            logger.warning(
                "⚠️  Phase 8.5 (Actuarial Enrichment) exception — pipeline continues. "
                "Error: %s", _aep_err,
            )
    else:
        logger.warning(
            "⏭️  Phase 8.5 (Actuarial Enrichment) skipped — not found at: %s",
            cfg.ACTUARIAL_ENRICHMENT_PASS,
        )
    # ─────────────────────────────────────────────────────────────────────────

    try:
        run_phantom_layer(canonical_run_id)            # non-critical | Phase 8c-P PHANTOM
    except Exception as _phantom_err:
        logger.warning("PHANTOM Edge Model exception -- pipeline continues. Error: %s", _phantom_err)

    try:
        run_core_intel_exporter(canonical_run_id)      # non-critical | Phase 8c
    except Exception as _core_export_err:
        logger.warning("Core Intel Exporter exception -- pipeline continues. Error: %s", _core_export_err)
    # ── Phase 8.6: Trigger Layer ─────────────────────────────────────────────
    # Injects trigger analysis into every package JSON before EDE runs.
    # Answers: "Is the move starting NOW?" for each signal.
    # 4 triggers: VOL_COMPRESSION, VWAP_RECLAIM, RANGE_BREAK, TRAP
    # Also computes ev_10d = win_rate * expected_move at runtime (never stored in DB).
    #
    # FIX-WIRING-GAP (2026-04-29 v2.9): trigger_layer v2.0 only patched package
    # JSONs. EDE reads the EIL CSV — trigger columns were never present there,
    # causing ede_trigger_count=0 for all 1470 signals and sovereign gate WAIT.
    # Fix: enrich_csv() now writes trigger columns into eil_enriched CSV after
    # EIL completes. patch_run_packages still runs for package JSON compat.
    # POSITION FIX: Phase 8.6 now runs AFTER EIL (Phase 9) so eil_enriched
    # CSV exists when enrich_csv() is called. See ordering below.
    # NON-CRITICAL: EDE falls back gracefully if trigger module absent.
    try:
        from trigger_layer import patch_run_packages as _tl_patch, enrich_csv as _tl_enrich_csv
        _oi_enriched = (
            cfg.RUNS_DIR / canonical_run_id / "options" /
            f"vanguard_signals_enriched_{canonical_run_id}.csv"
        )
        _tl_stats = _tl_patch(
            run_id            = canonical_run_id,
            base_dir          = cfg.BASE_DIR,
            vanguard_csv_path = str(_oi_enriched) if _oi_enriched.exists() else None,
        )
        _triggered    = _tl_stats.get("trigger_strong", 0) + _tl_stats.get("trigger_single", 0)
        _total_pkg    = _tl_stats.get("patched", 0)

        # Set eligible_for_trade=False on zero-trigger packages (belt-and-braces).
        _no_trig_flagged = 0
        try:
            import json as _json
            _pkg_dir2 = cfg.RUNS_DIR / canonical_run_id / "packages"
            if _pkg_dir2.exists():
                for _pp in _pkg_dir2.glob("*.package.json"):
                    try:
                        with open(_pp, encoding="utf-8") as _pf2:
                            _p2 = _json.load(_pf2)
                        _tc = int((_p2.get("triggers") or {}).get("count", 0))
                        _p2["eligible_for_trade"] = (_tc > 0)
                        if _tc == 0:
                            _no_trig_flagged += 1
                        with open(_pp, "w", encoding="utf-8") as _pf2:
                            _json.dump(_p2, _pf2, indent=2)
                    except Exception:
                        pass
        except Exception as _ef:
            logger.warning("⚠️  Phase 8.6 eligible_for_trade flagging: %s", _ef)

        _go_eligible = _tl_stats.get("go_eligible", 0)
        _stale       = _tl_stats.get("stale_filtered", 0)
        logger.info(
            "✅ Phase 8.6 (Trigger Layer — package JSON) — %d packages patched | "
            "STRONG=%d SINGLE=%d NONE=%d | GO_ELIGIBLE=%d | stale=%d | EV+=%d EV-=%d",
            _total_pkg,
            _tl_stats.get("trigger_strong", 0),
            _tl_stats.get("trigger_single", 0),
            _tl_stats.get("trigger_none",   0),
            _go_eligible,
            _stale,
            _tl_stats.get("ev_positive",    0),
            _tl_stats.get("ev_negative",    0),
        )
        if _total_pkg > 0:
            _pct     = _triggered / _total_pkg * 100
            _ev_pct  = _tl_stats.get("ev_positive", 0) / _total_pkg * 100
            _no_trig_pct = _tl_stats.get("trigger_none", 0) / _total_pkg * 100
            logger.info(
                "   Triggered: %.1f%% | EV+: %.1f%% | "
                "No-trigger (WAIT in EDE): %.1f%% | Stale filtered: %d",
                _pct, _ev_pct, _no_trig_pct, _stale,
            )
            if _no_trig_flagged > 0:
                logger.info(
                    "   %d packages flagged eligible_for_trade=False (no trigger) "
                    "→ EDE assigns WAIT verdict",
                    _no_trig_flagged,
                )
    except ImportError:
        logger.warning(
            "⚠️  Phase 8.6 (Trigger Layer) skipped — trigger_layer.py not found. "
            "Deploy trigger_layer.py to AVSHUNTER-Intelligence root."
        )
    except Exception as _tl_err:
        logger.warning("⚠️  Phase 8.6 (Trigger Layer — packages) exception: %s", _tl_err)
    # ─────────────────────────────────────────────────────────────────────────

    # ── Phase 8d: SuperBrain passthrough (FIX-2026-04-30) ───────────────────
    # Copies OI-enriched CSV → superbrain_enriched and maps
    # options_verdict → sb_final_verdict so EIL, GARCH, WBS, CT Gate run.
    # ─────────────────────────────────────────────────────────────────────────
    run_superbrain_passthrough(canonical_run_id)           # Phase 8d  — creates superbrain_enriched

    # ── PATCH-HORIZON Phase 8d-B: Defence-in-depth horizon patch ─────────────
    # Even if the OI patch missed rows (e.g. OI ran before horizon router),
    # EIL reads superbrain_enriched directly — so patch it here too.
    # Without this, 11-20D signals reach EIL/PSE with horizon_bucket="" and
    # the MONITOR_ONLY gate never fires.
    _sb_horizon_target = (
        cfg.RUNS_DIR / canonical_run_id / "superbrain" /
        f"superbrain_enriched_{canonical_run_id}.csv"
    )
    _sb_horizon_patched = patch_horizon_fields_into_csv(
        run_id     = canonical_run_id,
        target_csv = _sb_horizon_target,
        label      = "superbrain_enriched",
    )
    if not _sb_horizon_patched:
        logger.warning(
            "⚠️  HORIZON GOVERNANCE: superbrain_enriched not patched — "
            "EIL horizon gates (11-20D MONITOR_ONLY, 6-10D 0.70x) may not activate. "
            "Check horizon CSVs in runs/%s/horizon/", canonical_run_id,
        )
    run_catastrophe_gate(canonical_run_id)                 # Phase 8b  — DEF-003 FIX: after 8d
    run_wall_break_scorer(canonical_run_id)        # non-critical | Layer 4b
    # GARCH moved to AFTER EIL (see below) — l3_ fields must reach eil_enriched

    # ── FIX-ACTUARIAL-SEQ (v3.3): Inject actuarial into superbrain BEFORE EIL ──
    # ROOT CAUSE: EIL subprocess reads superbrain_enriched CSV for scoring.
    # Phase 8.5 patches package JSONs only — the subprocess cannot reliably
    # read them (timing/encoding in subprocess context, per inject_actuarial docstring).
    # inject_actuarial_into_eil_csv() is a POST-HOC patch that arrives after EIL
    # has already scored with hit_rate=0.0 on every row → 0% block rate.
    #
    # THE FIX: patch actuarial cols (win_rate_10d, expected_move_10d, etc.)
    # directly into superbrain_enriched CSV HERE, before EIL subprocess fires.
    # EIL ev_engine_v2 ev_inputs_from_row() reads win_rate_10d directly — if
    # the column is present in the CSV, actuarial edge flows through correctly.
    # ──────────────────────────────────────────────────────────────────────────
    _actuarial_loaded_before_eil = False
    _actuarial_fill_rate         = 0.0
    try:
        import glob as _glob_seq
        import pandas as _pd_seq

        _sb_path_seq  = cfg.RUNS_DIR / canonical_run_id / "superbrain" / f"superbrain_enriched_{canonical_run_id}.csv"
        _pkg_dir_seq  = cfg.RUNS_DIR / canonical_run_id / "packages"

        if _sb_path_seq.exists() and _pkg_dir_seq.exists():
            # Build actuarial map from package JSONs (already enriched by Phase 8.5)
            _act_map_seq: dict = {}
            for _pf_seq in _glob_seq.glob(str(_pkg_dir_seq / "*.package.json")):
                try:
                    with open(_pf_seq, "r", encoding="utf-8") as _pfh:
                        _pkg_seq = json.load(_pfh)
                    _tk_seq  = str(_pkg_seq.get("ticker", "")).strip().upper()
                    _act_seq = _pkg_seq.get("actuarial", {})
                    if _tk_seq and isinstance(_act_seq, dict) and _act_seq.get("enriched_by"):
                        _act_map_seq[_tk_seq] = _act_seq
                except Exception:
                    pass

            if _act_map_seq:
                _sb_df_seq = _pd_seq.read_csv(_sb_path_seq)
                _sb_df_seq["ticker_upper"] = _sb_df_seq["ticker"].str.strip().str.upper()

                # Columns EIL ev_engine_v2 ev_inputs_from_row() reads directly.
                # MUST use these exact names — ev_inputs_from_row() tries
                # win_rate_10d first (no scaling), then layer2__win_rate_10d (/100).
                _SB_ACT_MAP = [
                    ("win_rate_5d",        "win_rate_5d"),
                    ("win_rate_10d",       "win_rate_10d"),
                    ("win_rate_20d",       "win_rate_20d"),
                    ("expected_move_5d",   "expected_move_5d"),
                    ("expected_move_10d",  "expected_move_10d"),
                    ("expected_move_20d",  "expected_move_20d"),
                    ("efficiency_10d",     "efficiency_10d"),
                    ("penalty_multiplier", "penalty_multiplier"),
                    # Prefixed aliases for audit trail
                    ("actuarial_win_rate_10d",      "win_rate_10d"),
                    ("actuarial_expected_move_10d", "expected_move_10d"),
                    ("actuarial_efficiency_10d",    "efficiency_10d"),
                    ("actuarial_penalty",           "penalty_multiplier"),
                    ("actuarial_enriched_by",       "enriched_by"),
                    # ── V2 Signal Intelligence (Sprint 3) ──────────────────
                    ("actuarial_signal_type",           "signal_type"),
                    ("actuarial_momentum_tier",         "momentum_tier"),
                    ("actuarial_forward_momentum_conf", "forward_momentum_confidence"),
                    ("actuarial_phase_v2",              "phase_v2"),
                    ("actuarial_momentum_bucket",       "momentum_bucket"),
                    # ── 9-dim match dimensions (2026-05-20) ──────────────────
                    ("actuarial_wyckoff_phase_bucket",  "wyckoff_phase_bucket"),
                    ("actuarial_trend_maturity",        "trend_maturity"),
                    ("actuarial_iv_regime",             "iv_regime"),
                    ("actuarial_crabel_state",          "crabel_state"),
                    ("actuarial_horizon_bucket",        "horizon_bucket"),
                    ("actuarial_volume_bucket",         "volume_bucket"),
                ] + [(field, field) for field in PHASE2_LAYER2_FIELDS]

                for _col, _ in _SB_ACT_MAP:
                    if _col not in _sb_df_seq.columns:
                        _sb_df_seq[_col] = None
                _SB_ACT_TEXT_COLS = {
                    "actuarial_enriched_by",
                    "actuarial_signal_type",
                    "actuarial_momentum_tier",
                    "actuarial_phase_v2",
                    "actuarial_momentum_bucket",
                    "layer2__sample_confidence_bucket",
                    "layer2__preferred_horizon",
                    "layer2__state_match_method",
                    "layer2__state_match_stage",
                    "layer2__state_match_dimensions",
                    "layer2__state_match_quality",
                }
                for _text_col in _SB_ACT_TEXT_COLS:
                    if _text_col in _sb_df_seq.columns:
                        _sb_df_seq[_text_col] = _sb_df_seq[_text_col].astype(object)

                _patched_seq = 0
                for _idx_seq, _row_seq in _sb_df_seq.iterrows():
                    _tk = _row_seq.get("ticker_upper", "")
                    if _tk in _act_map_seq:
                        _act_data = _act_map_seq[_tk]
                        _phase2_baton = _act_data.get("phase2_baton")
                        if isinstance(_phase2_baton, dict):
                            _act_data = {**_phase2_baton, **_act_data}
                        for _col, _act_key in _SB_ACT_MAP:
                            _v = _act_data.get(_act_key)
                            if _v is not None:
                                try:
                                    _expected_dtype = _sb_df_seq[_col].dtype
                                    if _expected_dtype == "float64":
                                        _sb_df_seq.at[_idx_seq, _col] = float(_v)
                                    elif _expected_dtype == "int64":
                                        _sb_df_seq.at[_idx_seq, _col] = int(_v)
                                    elif _expected_dtype == "bool":
                                        _sb_df_seq.at[_idx_seq, _col] = str(_v).strip().lower() in {"1", "true", "yes", "y"}
                                    else:
                                        _sb_df_seq.at[_idx_seq, _col] = str(_v)
                                except (ValueError, TypeError):
                                    _sb_df_seq[_col] = _sb_df_seq[_col].astype(object)
                                    _sb_df_seq.at[_idx_seq, _col] = str(_v)
                        _patched_seq += 1

                # Stamp injection timestamp and rescore marker for audit trail
                from datetime import datetime as _dt_seq, timezone as _tz_seq
                _sb_df_seq["actuarial_injected_ts"]  = _dt_seq.now(_tz_seq.utc).isoformat()
                _sb_df_seq["actuarial_loaded_pre_eil"] = True

                _sb_df_seq = _sb_df_seq.drop(columns=["ticker_upper"], errors="ignore")
                _sb_df_seq.to_csv(_sb_path_seq, index=False)

                _filled_seq = _sb_df_seq["actuarial_win_rate_10d"].notna().sum() if "actuarial_win_rate_10d" in _sb_df_seq.columns else 0
                _total_seq  = len(_sb_df_seq)
                _actuarial_fill_rate = round(_filled_seq / _total_seq, 4) if _total_seq > 0 else 0.0

                logger.info(
                    "✅ FIX-ACTUARIAL-SEQ: %d rows patched into superbrain_enriched BEFORE EIL | "
                    "fill_rate=%.1f%% (%d/%d)",
                    _patched_seq, _actuarial_fill_rate * 100, _filled_seq, _total_seq,
                )

                # ── SOFT GATE: warn loudly if fill rate is too low ──────────
                # We do NOT raise RuntimeError — that would kill the evening run.
                # Instead: log CRITICAL, set flag, manifest will inherit DEGRADED state.
                if _actuarial_fill_rate < 0.80:
                    logger.critical(
                        "⛔ ACTUARIAL GATE: fill_rate=%.1f%% below 80%% threshold. "
                        "EIL will score with partial actuarial edge. "
                        "Candidate manifest will be marked ACTUARIAL_DEGRADED. "
                        "Check: (1) actuarial_cache_builder.py run after backfill, "
                        "(2) 9-dim cache has correct STATE_COLS, "
                        "(3) SIDEWAYS_RANGING added to actuarial_database.parquet.",
                        _actuarial_fill_rate * 100,
                    )
                    _actuarial_loaded_before_eil = False   # degraded = not trusted
                else:
                    _actuarial_loaded_before_eil = True
            else:
                logger.warning(
                    "⚠️  FIX-ACTUARIAL-SEQ: No enriched packages found — "
                    "Phase 8.5 may not have run or produced 0 matches. "
                    "EIL will score with zero actuarial edge."
                )
        else:
            logger.warning(
                "⚠️  FIX-ACTUARIAL-SEQ: superbrain_enriched or packages dir missing — "
                "skipping pre-EIL injection. EIL proceeds without actuarial edge."
            )
    except Exception as _seq_err:
        logger.warning("⚠️  FIX-ACTUARIAL-SEQ: pre-EIL injection failed — pipeline continues. Error: %s", _seq_err)
    # ──────────────────────────────────────────────────────────────────────────

    _eil_ok = run_execution_intelligence_layer(canonical_run_id)  # Phase 9 EIL
    if not _eil_ok:
        logger.error("EIL failed - skipping EIL-dependent post-processing for this run.")
    else:
        inject_actuarial_into_eil_csv(canonical_run_id)     # Safety net: stamp actuarial into eil_enriched too

        # ── PHASE 10a/10b: GARCH (moved here so l3_ fields reach eil_enriched) ──
        # Must run AFTER EIL so eil_enriched_{run_id}.csv exists for the merge.
        # merge_garch_into_enriched() patches both superbrain_enriched AND
        # eil_enriched — EVEngineV2 then reads l3_iv_tailwind_score correctly.
        run_garch_layer(canonical_run_id)              # Phase 10a
        merge_garch_into_enriched(canonical_run_id)   # Phase 10b — now patches eil_enriched too

        # ── Phase 8.6b: Trigger Layer → EIL CSV enrichment ───────────────────────
        # v3.1 FIX: enrich_csv() evaluates triggers against eil_enriched rows.
        # superbrain_enriched (EIL input) has 138 cols — ZERO trigger input cols.
        # All 18 trigger input cols live in vanguard_signals_enriched.
        # Without injection: every trigger evaluates [] → trigger_quality=NONE=1343.
        # FIX: merge vanguard trigger cols into eil_enriched BEFORE enrich_csv runs.
        try:
            from trigger_layer import enrich_csv as _tl_enrich_csv
            import pandas as _pd86b
            _eil_csv_path = (
                cfg.RUNS_DIR / canonical_run_id / "superbrain" /
                f"eil_enriched_{canonical_run_id}.csv"
            )
            _vg_enriched_path = (
                cfg.RUNS_DIR / canonical_run_id / "options" /
                f"vanguard_signals_enriched_{canonical_run_id}.csv"
            )
            _TRIGGER_INPUT_COLS = [
                "crabel_state", "crabel_compression", "atr_percentile_rank",
                "vwap_bias", "control_state", "wyckoff_phase_bucket",
                "catalyst_proximity", "days_in_range", "adx_14", "ema_stack",
                "dominant_trend", "volume_ratio_x",
                "layer1__control__controller", "layer1__auction_state", "precor_intent",
            ]

            # Vanguard actuarial governance fields — must survive into EIL/PSE.
            # These distinguish sample size from sample quality.
            _VANGUARD_GOVERNANCE_COLS = [
                "layer2__sample_confidence_bucket",
                "layer2__preferred_horizon",
                "layer2__state_match_method",
                "layer2__state_match_stage",
                "layer2__state_match_dimensions",
                "layer2__state_match_quality",
                "layer2__state_match_is_exact",
            ]

            _TRIGGER_INPUT_COLS = list(dict.fromkeys(_TRIGGER_INPUT_COLS + _VANGUARD_GOVERNANCE_COLS))
            if _eil_csv_path.exists():
                # Step 1: inject vanguard trigger cols into eil_enriched
                if _vg_enriched_path.exists():
                    try:
                        _eil_df = _pd86b.read_csv(_eil_csv_path)
                        _vg_df  = _pd86b.read_csv(_vg_enriched_path)
                        _cols_to_inject = [
                            c for c in _TRIGGER_INPUT_COLS
                            if c in _vg_df.columns and (
                                c not in _eil_df.columns or _eil_df[c].isna().all()
                            )
                        ]
                        if _cols_to_inject:
                            _vg_sub = _vg_df[["ticker"] + _cols_to_inject].copy()
                            _vg_sub["ticker"] = _vg_sub["ticker"].str.strip().str.upper()
                            _eil_df["ticker"] = _eil_df["ticker"].str.strip().str.upper()
                            _eil_df = _eil_df.drop(columns=[c for c in _cols_to_inject if c in _eil_df.columns], errors="ignore")
                            _eil_df = _eil_df.merge(_vg_sub, on="ticker", how="left")
                            _eil_df.to_csv(_eil_csv_path, index=False)
                            logger.info(
                                "Phase 8.6b: Injected %d vanguard trigger cols into eil_enriched",
                                len(_cols_to_inject)
                            )
                    except Exception as _inj_err:
                        logger.warning("Phase 8.6b: Vanguard trigger injection failed: %s", _inj_err)
                else:
                    logger.warning("Phase 8.6b: vanguard_signals_enriched not found — trigger cols absent")

                # Step 2: run enrich_csv — now has trigger input cols
                _tl_csv_stats = _tl_enrich_csv(_eil_csv_path, inplace=True)
                _go_elig  = _tl_csv_stats.get("go_eligible", 0)
                _strong   = _tl_csv_stats.get("trigger_strong", 0)
                _single   = _tl_csv_stats.get("trigger_single", 0)
                _stale_c  = _tl_csv_stats.get("stale_filtered", 0)
                _ev_pos   = _tl_csv_stats.get("ev_positive", 0)
                _wait_est = max(0, _ev_pos - _go_elig)
                logger.info(
                    "✅ Phase 8.6b (Trigger Layer — EIL CSV) — %d rows enriched | "
                    "GO_ELIGIBLE=%d | STRONG=%d SINGLE=%d | stale=%d | EV+=%d | ~%d WAIT→GO at open",
                    _tl_csv_stats.get("patched", 0),
                    _go_elig, _strong, _single, _stale_c, _ev_pos, _wait_est,
                )
                if _strong + _single == 0:
                    logger.warning(
                        "⚠️  Phase 8.6b: STILL zero triggers after vanguard injection — "
                        "check catalyst_proximity (FAR blocks all triggers) and "
                        "crabel_compression/atr_percentile_rank thresholds"
                    )
            else:
                logger.warning(
                    "⚠️  Phase 8.6b: eil_enriched CSV not found — "
                    "trigger columns not written. Expected: %s", _eil_csv_path,
                )
        except ImportError:
            logger.warning(
                "⚠️  Phase 8.6b skipped — trigger_layer.py not found or missing enrich_csv. "
                "Deploy trigger_layer.py v2.1+ to AVSHUNTER-Intelligence root."
            )
        except Exception as _tl_csv_err:
            logger.warning("⚠️  Phase 8.6b exception: %s", _tl_csv_err)
        # ─────────────────────────────────────────────────────────────────────────

        # ╔══ Phase 9.5 EDE: SUPERSEDED — PSE inside EIL runner is the replacement ══╗
        # ── V5 Colab decommissioned (May 2026). EDE functionality now delivered by
        if not enforce_handoff_conflict_guard(canonical_run_id):
            logger.error("EVENING WORKFLOW ABORTED -- handoff conflict guard blocked downstream export")
            return False

    #    Position Sizing Engine (PSE) inside execution_intelligence_runner.py v4.1.
    #    PSE answers the same 4 questions EDE did:
    #      Q1 Edge?      → actuarial composite via ev_engine_v2
    #      Q2 Timing?    → EIL composite score gate
    #      Q3 Tradeable? → options hard gates (spread, delta, breakeven)
    #      Q4 Risk?      → penalty multiplier chain → pse_final_size
    #    Output: pse_execution_mode, pse_final_size, fd_verdict per row in eil_enriched.
    #    DO NOT re-enable this block — it would double-gate signals already
    #    decided by PSE. If execution_decision_engine.py is needed as a separate
    #    audit layer, wire it to READ eil_enriched rather than re-score it.
    # ╚══ end Phase 9.5 note ══╝
    # # ── PHASE 9.5: Execution Decision Engine ──────────────────────────────────
    # # Converts Actuarial + EIL + Options into GO / ARMED / ARMED_HALF / BLOCKED.
    # # Sits between EIL output and the Enhancement / PSE sizing layer so that
    # # only signals with confirmed edge enter the sizing pipeline.
    # # NON-CRITICAL: enhancement layer runs regardless of EDE outcome.
    # # Output: decisions/ede_decisions_{run_id}.csv
    # #         decisions/ede_top_trades_{run_id}.csv
    # #         decisions/ede_summary_{run_id}.json
    # try:
    # from execution_decision_engine import run_ede_from_orchestrator
    # _ede = run_ede_from_orchestrator(
    # run_id   = canonical_run_id,
    # base_dir = cfg.BASE_DIR,
    # mode     = "EOD",
    # )
    # if _ede.get("success"):
    # _wait_n = _ede.get("verdict_breakdown", {}).get("WAIT", 0)
    # logger.info(
    # "✅ Phase 9.5 (EDE v4) — GO=%d | ARMED=%d | ARMED_HALF=%d | "
    # "WAIT=%d | BLOCKED=%d | top=%s",
    # _ede.get("go_count", 0),
    # _ede.get("armed_count", 0),
    # _ede.get("armed_half_count", 0),
    # _wait_n,
    # _ede.get("blocked_count", 0),
    # _ede.get("top_trades", []),
    # )
    # if _wait_n > 0:
    # logger.info(
    # "   WAIT=%d: EV positive, no trigger yet — "
    # "these are morning watchlist candidates (trigger → GO at open)",
    # _wait_n,
    # )
    # # v2.8: Log horizon short-circuit counts from EDE v1.1
    # _ede_mon = _ede.get("monitor_only_count", 0)
    # _ede_hbl = _ede.get("horizon_blocked_count", 0)
    # if _ede_mon > 0 or _ede_hbl > 0:
    # logger.info(
    # "   EDE horizon gates: MONITOR_ONLY=%d | BLOCKED=%d "
    # "(correctly excluded from GO/ARMED — expected behaviour)",
    # _ede_mon, _ede_hbl,
    # )
    # if _ede.get("go_count", 0) + _ede.get("armed_count", 0) == 0:
    # # v2.8: Check if zero GO/ARMED is because all signals are MONITOR_ONLY
    # # (expected) vs genuine no-edge condition (problem)
    # _total = _ede.get("total_signals", 0)
    # _horizon_excl = _ede_mon + _ede_hbl
    # if _horizon_excl >= _total and _total > 0:
    # logger.info(
    # "   EDE: 0 GO/ARMED — all %d signals are 11-20D MONITOR_ONLY "
    # "or horizon-blocked. This is correct macro-driven behaviour. "
    # "Horizon routing is working as designed.",
    # _total,
    # )
    # else:
    # logger.warning(
    # "⚠️  EDE: 0 GO/ARMED signals — check actuarial cache (Phase 4.6), "
    # "EIL output (Phase 9), and options contract data. "
    # "Breakdown: %s",
    # _ede.get("reason_breakdown", {}),
    # )
    # else:
    # logger.warning(
    # "⚠️  Phase 9.5 (EDE) failed — pipeline continues. Error: %s",
    # _ede.get("error") or _ede.get("reason", "unknown"),
    # )
    # except Exception as _ede_err:
    # logger.warning(
    # "⚠️  Phase 9.5 (EDE) exception — pipeline continues. Error: %s", _ede_err
    # )
    # # ─────────────────────────────────────────────────────────────────────────
    # ╚══ end Phase 9.5 EDE ══╝

    # ╔══ Phase 9B Enhancement: PENDING CONFIRMATION ══╗
    # ── V5 Colab decommissioned (May 2026). Enhancement Layer functionality
    #    (Kelly sizing, Signal Funnel, Regime Consensus Score) was replaced
    #    by PSE inside the EIL runner. Phase 9B can be re-enabled IF
    #    enhancement_integration.py exists on disk AND Phase 9C is also re-enabled.
    #    DO NOT re-enable this block alone — Phase 9C depends on its output.
    #    ACTION: confirm enhancement_integration.py on disk, then uncomment both.
    # ╚══ end Phase 9B note ══╝
    # # ── PHASE 9B: Enhancement Layer ───────────────────────────────────────────
    # # Kelly sizing, Signal Funnel, Regime Consensus Score, Atheoretic Scanner,
    # # IV Surface Frequency, Theory-Stats Convergence, EIL Convergence Score.
    # # Non-critical — pipeline continues unaffected if this fails.
    # # Output: enhanced_{run_id}.csv in superbrain folder.
    # try:
    # from enhancement_integration import run_enhancement_layer
    # _enh = run_enhancement_layer(
    # run_id       = canonical_run_id,
    # base_dir     = cfg.BASE_DIR,
    # account_size = 50000,
    # )
    # logger.info(
    # "Phase 9B complete — %d tradeable signals | discard rate %.1f%% | regime %s (RCS=%.1f)",
    # _enh.get("signals_out", 0),
    # _enh.get("discard_rate", 0) * 100,
    # _enh.get("rcs_label", "UNKNOWN"),
    # _enh.get("rcs_score", 0.0),
    # )
    # # v2.8: Log monitor-only exclusions from Enhancement v4.1
    # _enh_mon = _enh.get("monitor_only_count", 0)
    # if _enh_mon > 0:
    # logger.info(
    # "   Enhancement MONITOR_ONLY excluded: %d signals "
    # "(11-20D horizon — not entering Kelly/PSE sizing — correct)",
    # _enh_mon,
    # )
    # except Exception as _enh_err:
    # logger.warning("⚠️  Phase 9B (Enhancement Layer) failed — pipeline continues. Error: %s", _enh_err)
    # # ─────────────────────────────────────────────────────────────────────────
    # ╚══ end Phase 9B Enhancement ══╝

    # ╔══ Phase 9C Trade Book Builder: PENDING CONFIRMATION ══╗
    # ── V5 Colab decommissioned (May 2026). Trade Book Builder reads
    #    enhanced_{run_id}.csv which is written by Phase 9B.
    #    Cannot re-enable standalone — Phase 9B must run first.
    #    ACTION: re-enable Phase 9B and Phase 9C together once
    #    enhancement_integration.py is confirmed on disk.
    # ╚══ end Phase 9C note ══╝
    # # ── PHASE 9C: Trade Book Builder ──────────────────────────────────────────
    # # Reads enhanced_{run_id}.csv, ranks signals by pse_final_size × EV ×
    # # conv_score × wbs_score, selects top MAX_POSITIONS, writes final_trades.csv.
    # # Non-critical — write_latest_json runs regardless of outcome.
    # try:
    # _p9c = run_phase_9c(cfg, run_id=canonical_run_id)
    # if _p9c.get("trade_count", 0) > 0:
    # logger.info(
    # "Phase 9C complete — %d trades | %.2f%% capital deployed",
    # _p9c["trade_count"], _p9c.get("total_deployment_pct", 0.0),
    # )
    # else:
    # # v2.8: 0 trades may be correct if all signals are MONITOR_ONLY (11-20D horizon)
    # # Read horizon summary to determine whether this is expected behaviour
    # _h_summary_path = cfg.RUNS_DIR / canonical_run_id / "horizon" / f"horizon_summary_{canonical_run_id}.json"
    # _all_monitor = False
    # if _h_summary_path.exists():
    # try:
    # with open(_h_summary_path) as _hsp:
    # _hs = json.load(_hsp)
    # _hc = _hs.get("horizon_counts", {})
    # _total_routed = sum(_hc.values())
    # _monitor_routed = _hc.get("11_20d", 0) + _hc.get("blocked", 0)
    # if _total_routed > 0 and _monitor_routed >= _total_routed * 0.90:
    # _all_monitor = True
    # logger.info(
    # "   Phase 9C: 0 trades — %.0f%% of signals are 11-20D MONITOR_ONLY "
    # "or horizon-blocked. Macro forward bias is neutral/weak — "
    # "no proactive entries is the correct outcome today.",
    # _monitor_routed / _total_routed * 100,
    # )
    # except Exception:
    # pass
    # if not _all_monitor:
    # logger.warning(
    # "⚠️  Phase 9C — 0 trades. Check PSE, Kelly, convergence gate in enhanced CSV. "
    # "Also verify horizon_bucket is correctly stamped (Phase 1B router)."
    # )
    # except Exception as _p9c_err:
    # logger.warning("⚠️  Phase 9C (Trade Book Builder) failed — pipeline continues. Error: %s", _p9c_err)
    # # ─────────────────────────────────────────────────────────────────────────
    # ╚══ end Phase 9C Trade Book Builder ══╝

    run_catalyst_truth_layer(canonical_run_id, stage="post_eil")

    # Phase 9D: McMillan advisory context. This enriches the EIL handoff with
    # IV/GEX, move-vs-theta, and crowd-arrival context only; no gating or sizing.
    try:
        from mcmillan_advisory_layer import enrich_csv as _mcmillan_enrich_csv

        _mcm_eil_csv = (
            cfg.RUNS_DIR
            / canonical_run_id
            / "superbrain"
            / f"eil_enriched_{canonical_run_id}.csv"
        )
        if _mcm_eil_csv.exists():
            _mcm_stats = _mcmillan_enrich_csv(
                _mcm_eil_csv,
                run_id=canonical_run_id,
                base_dir=cfg.BASE_DIR,
                inplace=True,
                write_state=True,
            )
            logger.info(
                "McMillan advisory layer: %d rows enriched | IV/GEX=%s | move/theta=%s | crowd=%s",
                _mcm_stats.get("rows", 0),
                _mcm_stats.get("iv_gex_labels", {}),
                _mcm_stats.get("move_theta_labels", {}),
                _mcm_stats.get("crowd_arrival_states", {}),
            )
            _mcm_execution_csv = (
                cfg.RUNS_DIR
                / canonical_run_id
                / "execution"
                / f"execution_v3_5_{canonical_run_id}.csv"
            )
            if _mcm_execution_csv.exists():
                _mcm_exec_stats = _mcmillan_enrich_csv(
                    _mcm_execution_csv,
                    run_id=canonical_run_id,
                    base_dir=cfg.BASE_DIR,
                    inplace=True,
                    write_state=False,
                )
                logger.info(
                    "McMillan advisory layer: execution CSV enriched | rows=%d",
                    _mcm_exec_stats.get("rows", 0),
                )
        else:
            logger.warning(
                "McMillan advisory layer skipped -- eil_enriched not found: %s",
                _mcm_eil_csv,
            )
    except Exception as _mcm_err:
        logger.warning(
            "McMillan advisory layer failed non-critically -- EOD candidate build continues: %s",
            _mcm_err,
        )

    # ── PHASE 10: EOD Candidate Engine ────────────────────────────────────────
    # Converts the fully-enriched EIL+WBS+PSE output into a clean, structured
    # morning_candidates_{run_id}.csv. This is the ONLY file that morning
    # validation reads. Phase separation is enforced here — no live data,
    # no execution gating, pure structural classification.
    # Non-critical — archive runs regardless.
    try:
        from eod_candidate_engine import build_candidate_manifest
        _mv_dir = cfg.RUNS_DIR / canonical_run_id / "morning_validation"
        _mv_dir.mkdir(parents=True, exist_ok=True)
        _eil_csv = cfg.RUNS_DIR / canonical_run_id / "superbrain" / f"eil_enriched_{canonical_run_id}.csv"
        _wbs_csv = cfg.RUNS_DIR / canonical_run_id / "superbrain" / f"wall_break_scores_{canonical_run_id}.csv"
        _disc_csv = cfg.OUTPUT_DIR / f"discovery_candidates_ultimate_{canonical_run_id}.csv"
        if not _eil_csv.exists():
            # Fallback: superbrain_enriched if EIL output absent
            _eil_csv = cfg.RUNS_DIR / canonical_run_id / "superbrain" / f"superbrain_enriched_{canonical_run_id}.csv"
        if _eil_csv.exists():
            # ── Horizon context: pass horizon summary so morning manifest knows
            # which signals are 1-5D entries vs 6-10D continuations vs monitors.
            _horizon_summary = cfg.RUNS_DIR / canonical_run_id / "horizon" / f"horizon_summary_{canonical_run_id}.json"
            _horizon_kwargs = {}
            if _horizon_summary.exists():
                try:
                    with open(_horizon_summary) as _hf:
                        _horizon_kwargs["horizon_summary"] = json.load(_hf)
                except Exception:
                    pass
            # ── Horizon CSVs: pass 1-5D and 6-10D separately for tiered morning validation
            _h1_csv = cfg.RUNS_DIR / canonical_run_id / "horizon" / f"horizon_1_5d_{canonical_run_id}.csv"
            _h2_csv = cfg.RUNS_DIR / canonical_run_id / "horizon" / f"horizon_6_10d_{canonical_run_id}.csv"
            if _h1_csv.exists():
                _horizon_kwargs["horizon_1_5d_path"] = _h1_csv
            if _h2_csv.exists():
                _horizon_kwargs["horizon_6_10d_path"] = _h2_csv

            # PIPELINE-01 (2026-05-03): Pass vanguard_signals_enriched so EOD engine
            # can backfill rr_underlying and actuarial state fields that are written
            # by discovery/vanguard but not propagated through eil_enriched.
            _van_enriched = cfg.RUNS_DIR / canonical_run_id / "options" / f"vanguard_signals_enriched_{canonical_run_id}.csv"
            if not _van_enriched.exists():
                _van_enriched = cfg.RUNS_DIR / canonical_run_id / "vanguard" / "vanguard_signals.csv"

            _morning_csv_path = _mv_dir / f"morning_candidates_{canonical_run_id}.csv"
            build_candidate_manifest(
                eil_path       = _eil_csv,
                wbs_path       = _wbs_csv if _wbs_csv.exists() else None,
                discovery_path = _disc_csv if _disc_csv.exists() else None,
                vanguard_path  = _van_enriched if _van_enriched.exists() else None,
                output_path    = _morning_csv_path,
                run_id         = canonical_run_id,
                max_candidates = cfg.MORNING_VALIDATION_MAX_CANDIDATES,
                **_horizon_kwargs,
            )
            # B1 FIX: Join missing live contract fields from OI CSV into morning manifest.
            # The builder is the source of truth, but this safety net must coalesce
            # into the canonical columns. A plain merge with suffixes creates
            # contract_gamma_oi / contract_iv_oi and leaves the real fields blank.
            try:
                import pandas as _pd_b1
                _oi_b1_path = cfg.RUNS_DIR / canonical_run_id / "options" / f"options_intelligence_{canonical_run_id}.csv"
                if _oi_b1_path.exists() and _morning_csv_path.exists():
                    _contract_cols = [
                        "contract_delta", "contract_gamma", "contract_theta", "contract_iv",
                        "contract_bid", "contract_ask", "contract_mid", "contract_spread_pct",
                        "contract_oi", "contract_volume",
                    ]
                    _oi_b1 = _pd_b1.read_csv(_oi_b1_path, low_memory=False)
                    _contract_present = [c for c in _contract_cols if c in _oi_b1.columns]
                    if _contract_present and "ticker" in _oi_b1.columns:
                        _morning_b1 = _pd_b1.read_csv(_morning_csv_path, low_memory=False)
                        for _col in _contract_cols:
                            if _col not in _morning_b1.columns:
                                _morning_b1[_col] = _pd_b1.NA
                        _morning_b1 = _morning_b1.merge(
                            _oi_b1[["ticker"] + _contract_present].drop_duplicates("ticker"),
                            on="ticker", how="left", suffixes=("", "__oi"),
                        )
                        _filled_counts = {}
                        for _col in _contract_present:
                            _oi_col = f"{_col}__oi"
                            if _oi_col not in _morning_b1.columns:
                                continue
                            _target = _morning_b1[_col]
                            _source = _morning_b1[_oi_col]
                            _target_missing = (
                                _target.isna()
                                | _target.astype(str).str.strip().isin(
                                    {"", "nan", "NaN", "None", "NONE", "<NA>", "0", "0.0"}
                                )
                            )
                            _source_present = ~(
                                _source.isna()
                                | _source.astype(str).str.strip().isin({"", "nan", "NaN", "None", "NONE", "<NA>"})
                            )
                            _fill_mask = _target_missing & _source_present
                            if _fill_mask.any():
                                _morning_b1.loc[_fill_mask, _col] = _morning_b1.loc[_fill_mask, _oi_col]
                            _filled_counts[_col] = int(_fill_mask.sum())
                            _morning_b1.drop(columns=[_oi_col], inplace=True)
                        _morning_b1.to_csv(_morning_csv_path, index=False)
                        _visible_counts = {
                            _col: int(
                                (
                                    ~(
                                        _morning_b1[_col].isna()
                                        | _morning_b1[_col].astype(str).str.strip().isin(
                                            {"", "nan", "NaN", "None", "NONE", "<NA>"}
                                        )
                                    )
                                ).sum()
                            )
                            for _col in _contract_cols if _col in _morning_b1.columns
                        }
                        logger.info(
                            "B1 FIX: Coalesced contract handoff fields into morning manifest | filled=%s | visible=%s",
                            _filled_counts,
                            _visible_counts,
                        )
            except Exception as _b1_err:
                logger.warning("B1 FIX: Contract Greek join failed — manifest unchanged: %s", _b1_err)
            # B4 FIX: Include all l3_ GARCH fields in morning manifest export
            # l3_jump_risk_flag is critical — 22 EOD_CANDIDATE_ONLY tickers carry jump risk
            try:
                import pandas as _pd_b4
                if _eil_csv.exists() and _morning_csv_path.exists():
                    _eil_b4 = _pd_b4.read_csv(_eil_csv, low_memory=False)
                    _l3_cols = [c for c in _eil_b4.columns if c.startswith("l3_")]
                    if _l3_cols and "ticker" in _eil_b4.columns:
                        _morning_b4 = _pd_b4.read_csv(_morning_csv_path, low_memory=False)
                        _l3_missing = [c for c in _l3_cols if c not in _morning_b4.columns]
                        if _l3_missing:
                            _morning_b4 = _morning_b4.merge(
                                _eil_b4[["ticker"] + _l3_missing].drop_duplicates("ticker"),
                                on="ticker", how="left",
                            )
                            _morning_b4.to_csv(_morning_csv_path, index=False)
                            logger.info(
                                "B4 FIX: Including %d l3_ GARCH fields in morning manifest: %s",
                                len(_l3_missing), _l3_missing,
                            )
                        else:
                            logger.info(
                                "B4 FIX: All %d l3_ GARCH fields already present in morning manifest",
                                len(_l3_cols),
                            )
            except Exception as _b4_err:
                logger.warning("B4 FIX: l3_ field join failed — manifest unchanged: %s", _b4_err)
            # McMillan safety net: builder should export these directly, but keep
            # EIL as the source of truth if an older candidate path drops columns.
            try:
                import pandas as _pd_mcm
                from mcmillan_advisory_layer import MCMILLAN_FIELDS as _MCMILLAN_FIELDS
                # MCMILLAN_FIELDS covers 11 core fields. The gamma_island detail fields
                # (label, level, distance_pct, source, note) are written by the enricher
                # but absent from MCMILLAN_FIELDS. Include them here so the rescue join
                # covers all 16 McMillan handoff fields without touching the layer module.
                _ALL_MCM_FIELDS = list(_MCMILLAN_FIELDS) + [
                    f for f in [
                        "gamma_island_label", "gamma_island_level",
                        "gamma_island_distance_pct", "gamma_island_source",
                        "gamma_island_note",
                    ] if f not in _MCMILLAN_FIELDS
                ]

                if _eil_csv.exists() and _morning_csv_path.exists():
                    _eil_mcm = _pd_mcm.read_csv(_eil_csv, low_memory=False)
                    _mcm_present = [c for c in _ALL_MCM_FIELDS if c in _eil_mcm.columns]
                    if _mcm_present and "ticker" in _eil_mcm.columns:
                        _morning_mcm = _pd_mcm.read_csv(_morning_csv_path, low_memory=False)
                        for _col in _mcm_present:
                            if _col not in _morning_mcm.columns:
                                _morning_mcm[_col] = _pd_mcm.NA
                        _morning_mcm = _morning_mcm.merge(
                            _eil_mcm[["ticker"] + _mcm_present].drop_duplicates("ticker"),
                            on="ticker",
                            how="left",
                            suffixes=("", "__mcm"),
                        )
                        _mcm_filled = {}
                        for _col in _mcm_present:
                            _src_col = f"{_col}__mcm"
                            if _src_col not in _morning_mcm.columns:
                                continue
                            _target = _morning_mcm[_col]
                            _source = _morning_mcm[_src_col]
                            _target_missing = (
                                _target.isna()
                                | _target.astype(str).str.strip().isin({"", "nan", "NaN", "None", "NONE", "<NA>"})
                            )
                            _source_present = ~(
                                _source.isna()
                                | _source.astype(str).str.strip().isin({"", "nan", "NaN", "None", "NONE", "<NA>"})
                            )
                            _fill_mask = _target_missing & _source_present
                            if _fill_mask.any():
                                _morning_mcm.loc[_fill_mask, _col] = _morning_mcm.loc[_fill_mask, _src_col]
                            _mcm_filled[_col] = int(_fill_mask.sum())
                            _morning_mcm.drop(columns=[_src_col], inplace=True)
                        _morning_mcm.to_csv(_morning_csv_path, index=False)
                        logger.info(
                            "McMillan handoff fields visible in morning manifest | filled=%s",
                            _mcm_filled,
                        )
            except Exception as _mcm_join_err:
                logger.warning(
                    "McMillan handoff join failed -- manifest unchanged: %s",
                    _mcm_join_err,
                )
            # MACRO REDESIGN: Stamp macro_exposure_role and macro_exposure_reason
            # DISPLAY ONLY — these columns must NEVER be read by scoring or execution code
            try:
                import pandas as _pd_exp
                import importlib.util as _exp_ilu
                _exp_script = cfg.SCRIPTS_DIR / "macro_exposure_resolver.py"
                if _exp_script.exists() and _morning_csv_path.exists():
                    _exp_spec = _exp_ilu.spec_from_file_location("macro_exposure_resolver", str(_exp_script))
                    _exp_mod  = _exp_ilu.module_from_spec(_exp_spec)
                    _exp_spec.loader.exec_module(_exp_mod)
                    _exp_df = _pd_exp.read_csv(_morning_csv_path, low_memory=False)
                    _exp_df = _exp_mod.enrich_dataframe(
                        _exp_df,
                        macro_path=macro_path,
                        enrichment_path=cfg.MACRO_DIR / "avshunter_macro_enrichment_delta.json",
                    )
                    _exp_df.to_csv(_morning_csv_path, index=False)
                    _ben = (_exp_df.get("macro_exposure_role") == "BENEFICIARY").sum() if "macro_exposure_role" in _exp_df.columns else 0
                    _vul = (_exp_df.get("macro_exposure_role") == "VULNERABLE").sum() if "macro_exposure_role" in _exp_df.columns else 0
                    logger.info(
                        "MACRO EXPOSURE: stamped role/reason into morning manifest | BENEFICIARY=%d VULNERABLE=%d",
                        _ben, _vul,
                    )
            except Exception as _exp_err:
                logger.warning("MACRO EXPOSURE: resolver failed (non-critical): %s", _exp_err)

            # B3 — Exit Rules Engine
            try:
                import pandas as _pd_exit
                import importlib.util as _exit_ilu
                _exit_script = cfg.SCRIPTS_DIR / "exit_rules_engine.py"
                if _exit_script.exists() and _morning_csv_path.exists():
                    _exit_spec = _exit_ilu.spec_from_file_location("exit_rules_engine", str(_exit_script))
                    _exit_mod  = _exit_ilu.module_from_spec(_exit_spec)
                    _exit_spec.loader.exec_module(_exit_mod)
                    _exit_df = _pd_exit.read_csv(_morning_csv_path, low_memory=False)
                    _exit_df = _exit_mod.enrich_dataframe(_exit_df)
                    _exit_df.to_csv(_morning_csv_path, index=False)
                    _exit_count = int(_exit_df["exit_rule_summary"].notna().sum())
                    logger.info("[EXIT_RULES] %d tickers enriched with exit rules", _exit_count)
            except Exception as _e_exit:
                logger.warning("[EXIT_RULES] enrichment skipped: %s", _e_exit)

            logger.info(
                "✅ Phase 10: EOD candidate manifest written -> morning_candidates_%s.csv",
                canonical_run_id,
            )
        else:
            logger.warning("⚠️  Phase 10: EIL/superbrain CSV not found — morning manifest skipped")
    except Exception as _eod_err:
        logger.warning("⚠️  Phase 10 (EOD Candidate Engine) failed — pipeline continues. Error: %s", _eod_err)
    # ─────────────────────────────────────────────────────────────────────────

    # ── Write latest.json ─────────────────────────────────────────────────────
    run_market_context_read_only_diagnostics(canonical_run_id, data_mode=_data_mode)

    # Must run after Phase 10 so morning_validation.py auto-resolves to today's
    # run without needing --run_id passed manually. Uses no-BOM UTF-8 write so
    # both Python utf-8-sig and standard utf-8 readers can parse it cleanly.
    try:
        _latest_out = cfg.OUTPUT_DIR / "latest.json"
        _latest_out.parent.mkdir(parents=True, exist_ok=True)
        with open(_latest_out, "w", encoding="utf-8") as _lf:
            json.dump({"run_id": canonical_run_id}, _lf)
        logger.info("✅ latest.json updated → run_id: %s", canonical_run_id)
    except Exception as _lj_err:
        logger.warning("⚠️  Could not write latest.json: %s", _lj_err)
    # ─────────────────────────────────────────────────────────────────────────

    # ── FIX-INTEGRITY (v3.3): Pipeline Integrity Report ───────────────────────
    # One-file run truth. Read this before trusting any candidate output.
    # Written AFTER Phase 10 (manifest) so all counts are final.
    # EIL block rate read from eil_enriched CSV: ratio of BLOCKED verdicts.
    # Manifest permission: REVIEW_ONLY unless actuarial loaded + horizon present.
    # ──────────────────────────────────────────────────────────────────────────
    try:
        import pandas as _pd_int

        # Collect EIL stats from eil_enriched CSV
        _eil_int_path = cfg.RUNS_DIR / canonical_run_id / "superbrain" / f"eil_enriched_{canonical_run_id}.csv"
        _eil_block_rate = None
        _eil_total      = 0
        _eil_mode       = "UNKNOWN"
        if _eil_int_path.exists():
            try:
                _eil_int_df  = _pd_int.read_csv(_eil_int_path)
                _eil_total   = len(_eil_int_df)
                # PATCH 5: EIL runner writes eil_v3_verdict — old list never matched it
                _verdict_col = next(
                    (c for c in [
                        "eil_v3_verdict", "eil_raw_verdict",
                        "eil_verdict", "verdict", "eil_decision",
                    ] if c in _eil_int_df.columns),
                    None,
                )
                if _verdict_col and _eil_total > 0:
                    _blocked_n = (
                        _eil_int_df[_verdict_col]
                        .fillna("").astype(str).str.upper()
                        .eq("BLOCKED").sum()
                    )
                    _eil_block_rate = round(_blocked_n / _eil_total, 4)
                # PATCH 6: derive eil_eod_mode from the actual EIL output column,
                # not from weekday(). weekday() returns LIVE on a Tuesday EOD run.
                if "eil_data_mode" in _eil_int_df.columns:
                    _mode_counts = (
                        _eil_int_df["eil_data_mode"]
                        .fillna("UNKNOWN").astype(str)
                        .value_counts().to_dict()
                    )
                    _eil_mode = max(_mode_counts, key=_mode_counts.get) if _mode_counts else "UNKNOWN"
            except Exception:
                pass

        # Collect manifest counts from morning_candidates CSV
        _mv_int_path = cfg.RUNS_DIR / canonical_run_id / "morning_validation" / f"morning_candidates_{canonical_run_id}.csv"
        _tier_a = _tier_b = _tier_c = _exec_ready = 0
        if _mv_int_path.exists():
            try:
                _mv_int_df  = _pd_int.read_csv(_mv_int_path)
                _tier_a     = int((_mv_int_df.get("structural_tier", _pd_int.Series()) == "A").sum())
                _tier_b     = int((_mv_int_df.get("structural_tier", _pd_int.Series()) == "B").sum())
                _tier_c     = int((_mv_int_df.get("structural_tier", _pd_int.Series()) == "C").sum())
                _exec_col   = next((c for c in ["eod_candidate_status", "execution_permission", "morning_status"] if c in _mv_int_df.columns), None)
                if _exec_col:
                    _exec_ready = int((_mv_int_df[_exec_col].astype(str).str.contains("EXECUTE|GO|TRIGGER_READY", na=False)).sum())
                if _exec_ready == 0 and "eil_v3_verdict" in _mv_int_df.columns:
                    _exec_ready = int(
                        _mv_int_df["eil_v3_verdict"].astype(str).str.contains("EXECUTE", na=False).sum()
                    )
            except Exception:
                pass

        # Horizon routing present
        _hz_summary_int = cfg.RUNS_DIR / canonical_run_id / "horizon" / f"horizon_summary_{canonical_run_id}.json"
        _horizon_present = _hz_summary_int.exists()

        # Determine manifest permission and final pipeline state
        if not _actuarial_loaded_before_eil and not _horizon_present:
            _manifest_permission = "BLOCKED_ACTUARIAL_AND_HORIZON_MISSING"
            _final_state         = "DEGRADED_DO_NOT_TRADE"
        elif not _macro_normalised_ok:
            _manifest_permission = "REVIEW_ONLY_MACRO_DEGRADED"
            _final_state         = "PREP_DEGRADED_MACRO_MISSING"
        elif not _actuarial_loaded_before_eil:
            _manifest_permission = "REVIEW_ONLY_ACTUARIAL_DEGRADED"
            _final_state         = "PREP_DEGRADED_ACTUARIAL_MISSING"
        elif not _horizon_present:
            _manifest_permission = "REVIEW_ONLY_HORIZON_MISSING"
            _final_state         = "PREP_VALID_HORIZON_MISSING"
        elif _tier_a + _tier_b == 0 and _exec_ready == 0:
            _manifest_permission = "REVIEW_ONLY"
            _final_state         = "PREP_VALID_EXECUTION_PENDING_MORNING"
        elif _exec_ready > 0 and _tier_a + _tier_b == 0:
            _manifest_permission = "MORNING_VALIDATION_REQUIRED"
            _final_state         = "PREP_VALID_EOD_SLATE_PRESENT"
        else:
            _manifest_permission = "MORNING_VALIDATION_REQUIRED"
            _final_state         = "PREP_VALID_TIER_AB_PRESENT"

        _integrity = {
            "run_id":                       canonical_run_id,
            "generated_utc":                datetime.now(timezone.utc).isoformat(),
            "actuarial_loaded_before_eil":  _actuarial_loaded_before_eil,
            "actuarial_fill_rate":          _actuarial_fill_rate,
            "horizon_routing_present":      _horizon_present,
            "eil_total_rows":               _eil_total,
            "eil_block_rate":               _eil_block_rate,
            "tier_a_count":                 _tier_a,
            "tier_b_count":                 _tier_b,
            "tier_c_count":                 _tier_c,
            "execution_ready_count":        _exec_ready,
            "manifest_permission":          _manifest_permission,
            "macro_normalised_ok":          _macro_normalised_ok,
            "enrichment_merge_degraded":    _enrichment_merge_degraded,
            "final_pipeline_state":         _final_state,
            # EDE equivalent is ACTIVE inside EIL runner v4.1 via PSE chain.
            # V5 Colab decommissioned — all decision logic is now internal.
            # Phase 9.5 (separate EDE script) was superseded by PSE in EIL runner.
            # Phase 9B (Enhancement Layer) — confirm enhancement_integration.py on disk before re-enabling.
            # Phase 9C (Trade Book Builder) — depends on Phase 9B output; re-enable together.
            "pse_active":                   True,    # PSE inside EIL runner is the EDE replacement
            "v5_colab_decommissioned":      True,    # All scoring now internal — no external Colab dependency
            "eil_eod_mode":                 _eil_mode,       # PATCH 6: from actual eil_data_mode column
            "morning_validation_command":   "python morning_thesis_validator.py --tiers A,B,C,WATCH --max-signals 0 --live",
            "action_items": {
                "sideways_ranging_gap":         "ACTION — run backfill_actuarial_db to add SIDEWAYS_RANGING as valid actuarial state.",
                "enhancement_layer_9b":         "CONFIRM — check if enhancement_integration.py exists on disk before re-enabling Phase 9B.",
                "trade_book_9c":                "CONFIRM — Phase 9C depends on Phase 9B output. Re-enable both together or neither.",
                "eil_pattern_align":            "ACTIVE — fd_pattern_direction_align now written per row via final_decision_engine.py v1.1.",
            },
        }

        _int_path = cfg.RUNS_DIR / canonical_run_id / f"pipeline_integrity_{canonical_run_id}.json"
        with open(_int_path, "w", encoding="utf-8") as _int_f:
            json.dump(_integrity, _int_f, indent=2)

        logger.info(
            "✅ INTEGRITY REPORT: %s | actuarial_before_eil=%s | fill=%.1f%% | "
            "horizon=%s | block_rate=%s | tiers=A:%d B:%d C:%d | state=%s",
            _int_path.name,
            _actuarial_loaded_before_eil,
            _actuarial_fill_rate * 100,
            _horizon_present,
            f"{_eil_block_rate:.1%}" if _eil_block_rate is not None else "N/A",
            _tier_a, _tier_b, _tier_c,
            _final_state,
        )
        if _manifest_permission.startswith("BLOCKED") or "DEGRADED" in _manifest_permission:
            logger.critical(
                "⛔ MANIFEST PERMISSION: %s — do not treat candidate output as execution-grade.",
                _manifest_permission,
            )
    except Exception as _int_err:
        logger.warning("⚠️  Integrity report failed (non-critical): %s", _int_err)
    # ─────────────────────────────────────────────────────────────────────────

    try:
        from dropoff_audit import build_dropoff_audit

        _dropoff_df = build_dropoff_audit(canonical_run_id, runs_dir=cfg.RUNS_DIR)
        _dropoff_counts = _dropoff_df["dropoff_stage"].value_counts().to_dict() if "dropoff_stage" in _dropoff_df.columns else {}
        logger.info(
            "✅ DROP-OFF AUDIT: dropoff_audit_%s.csv | rows=%d | stages=%s",
            canonical_run_id,
            len(_dropoff_df),
            _dropoff_counts,
        )
    except Exception as _dropoff_err:
        logger.warning("⚠️  Drop-off audit failed (non-critical): %s", _dropoff_err)

    try:
        from handoff_contract_audit import audit_run as _audit_handoff_contract

        _handoff_audit = _audit_handoff_contract(canonical_run_id, runs_dir=cfg.RUNS_DIR)
        logger.info(
            "HANDOFF CONTRACT AUDIT: handoff_contract_audit_%s.csv | status=%s | fail=%d | warn=%d",
            canonical_run_id,
            _handoff_audit.get("overall_status"),
            _handoff_audit.get("fail_count", 0),
            _handoff_audit.get("warn_count", 0),
        )
    except Exception as _handoff_audit_err:
        logger.warning("Handoff contract audit failed (non-critical): %s", _handoff_audit_err)

    try:
        from uat_audit_report import write_uat_audit_report

        _uat_report = write_uat_audit_report(canonical_run_id, runs_dir=cfg.RUNS_DIR)
        logger.info(
            "UAT AUDIT REPORT: %s",
            _uat_report.get("output_markdown") or _uat_report.get("output_json"),
        )
    except Exception as _uat_report_err:
        logger.warning("UAT audit report failed (non-critical): %s", _uat_report_err)

    try:
        from contracts.lab_control import write_final_run_manifest, write_final_opportunity_book
        _manifest = write_final_run_manifest(canonical_run_id, cfg.RUNS_DIR, pipeline_mode="EOD")
        logger.info(
            "Final run manifest: health=%s next_action=%s tradeable=%s",
            _manifest.get("run_health_score"),
            _manifest.get("next_action"),
            _manifest.get("run_tradeable"),
        )
        try:
            import pandas as _pd_lab_sync
            _mv_dir = cfg.RUNS_DIR / canonical_run_id / "morning_validation"
            _lab_source = _mv_dir / f"morning_candidates_{canonical_run_id}.csv"
            if not _lab_source.exists():
                _lab_source = cfg.RUNS_DIR / canonical_run_id / "superbrain" / f"eil_enriched_{canonical_run_id}.csv"
            if _lab_source.exists():
                _lab_rows = _pd_lab_sync.read_csv(_lab_source, low_memory=False).to_dict("records")
                _lab_book = write_final_opportunity_book(canonical_run_id, _lab_rows, _manifest, cfg.RUNS_DIR)
                logger.info(
                    "Lab/Interpreter shared triage view written -> %s",
                    _lab_book.get("triage_csv_path"),
                )
        except Exception as _lab_sync_err:
            logger.warning("Lab/Interpreter shared triage view failed (non-critical): %s", _lab_sync_err)
    except Exception as _manifest_err:
        logger.warning("Final run manifest failed (non-critical): %s", _manifest_err)

    archive_outputs(canonical_run_id)
    prune_old_runs()
    generate_report(summary, canonical_run_id, session_id)

    # ── STAGE 9: Outcome Capture ──────────────────────────────────────────────
    # Scans open positions for auto-detectable exits (expiry, time stop, 80% loss).
    # Fetches current marks from Tastytrade → Polygon → manual CSV fallback.
    # Non-critical — pipeline completes regardless.
    try:
        from outcome_capture import run_outcome_capture
        _oc = run_outcome_capture(dry_run=False)
        logger.info(
            "✅ Stage 9 (Outcome Capture): exits=%d still_open=%d manual_needed=%d",
            _oc.get("exits_detected", 0),
            _oc.get("still_open",     0),
            _oc.get("manual_needed",  0),
        )
    except ImportError:
        logger.debug("outcome_capture not deployed — Stage 9 skipped")
    except Exception as _oc_err:
        logger.warning("⚠️  Stage 9 (Outcome Capture) failed (non-critical): %s", _oc_err)

    # ── STAGE 10: Weekly Intelligence Report (Sundays only) ──────────────────
    # Aggregates closed trades, compares realised vs predicted win rates,
    # and produces prior_adjustment_review.json for STATE_PRIOR_ADJUSTMENTS review.
    # Runs on Sunday evening only — non-critical on other days.
    import datetime as _dt
    if _dt.date.today().weekday() == 6:  # 6 = Sunday
        try:
            from weekly_intelligence_report import run_weekly_report
            _wr = run_weekly_report()
            logger.info(
                "✅ Stage 10 (Weekly Report): week=%s trades=%d win_rate=%.1f%% "
                "buckets_to_review=%d",
                _wr.get("week",            "?"),
                _wr.get("n_trades",        0),
                _wr.get("win_rate",        0) * 100,
                _wr.get("buckets_to_review", 0),
            )
            if _wr.get("buckets_to_review", 0) > 0:
                logger.info(
                    "   ⚠️  %d actuarial bucket(s) diverge >10%% from realised win rate. "
                    "Review prior_adjustment_review.json in data/output/weekly_reports/",
                    _wr["buckets_to_review"],
                )
        except ImportError:
            logger.debug("weekly_intelligence_report not deployed — Stage 10 skipped")
        except Exception as _wr_err:
            logger.warning("⚠️  Stage 10 (Weekly Report) failed (non-critical): %s", _wr_err)

    logger.info("=" * 80)
    logger.info("✅ EVENING WORKFLOW COMPLETE")
    logger.info("=" * 80)
    logger.info("Next: Run morning validation at 09:45 ET after market open")
    logger.info("      python morning_thesis_validator.py --tiers A,B,C,WATCH --max-signals 0 --live\n")
    return True


def premarket_workflow(run_id: Optional[str] = None) -> bool:
    """
    Morning validation workflow — runs at 09:45 ET after market open.

    Reads morning_candidates_{run_id}.csv written by the previous evening's
    Phase 10 (EOD Candidate Engine) and scores each candidate against live
    market data (price, VWAP, options quote, IV, volume).

    DESIGN PRINCIPLE: Morning does NOT re-run the full pipeline.
    EOD = structural truth  |  Morning = live execution decision
    """
    logger.info("\n" + "=" * 80)
    logger.info("🌅  MORNING VALIDATION — EXECUTION DECISION ENGINE")
    logger.info("    Run at 09:45 ET — 15 minutes after open")
    logger.info("=" * 80 + "\n")

    # PATCH 7: Resolve run_id — CLI run_id wins; latest.json is the fallback.
    # Old code always read latest.json and ignored the supplied run_id parameter.
    if run_id:
        _run_id = str(run_id).strip()
        logger.info("   Using run_id from CLI argument: %s", _run_id)
    else:
        _latest_path = cfg.OUTPUT_DIR / "latest.json"
        try:
            with open(_latest_path, "r", encoding="utf-8-sig") as _f:
                _latest = json.load(_f)
            _run_id = str(_latest.get("run_id", "")).strip()
            if not _run_id:
                logger.error("❌ latest.json has no run_id — run evening workflow first")
                return False
            logger.info("   Using run_id from latest.json: %s", _run_id)
        except Exception as _e:
            logger.error("❌ Cannot read latest.json: %s — run evening workflow first", _e)
            return False

    _mv_dir           = cfg.RUNS_DIR / _run_id / "morning_validation"
    _candidates_path  = _mv_dir / f"morning_candidates_{_run_id}.csv"
    _output_path      = _mv_dir / f"morning_validated_trades_{_run_id}.csv"
    _final_book_path  = cfg.RUNS_DIR / _run_id / "intelligence_lab" / f"final_opportunity_book_{_run_id}.csv"

    if not _candidates_path.exists() and not _final_book_path.exists():
        logger.error(
            "❌ Morning validation input not found.\n"
            "   Expected final opportunity book: %s\n"
            "   Fallback morning candidates: %s\n"
            "   Run the evening workflow to generate it:\n"
            "   python intelligent_orchestrator.py --evening",
            _final_book_path,
            _candidates_path,
        )
        return False

    if not cfg.MORNING_VALIDATION_ENGINE.exists():
        logger.warning(
            "⏭️  Morning validation engine not found: %s\n"
            "   Deploy morning_validation_engine.py to root directory.",
            cfg.MORNING_VALIDATION_ENGINE,
        )
        return False

    _mv_dir.mkdir(parents=True, exist_ok=True)

    # FIX 7: Run catalyst truth patch on morning_candidates BEFORE validation.
    # Root cause: catalyst_truth ran before morning_candidates was written (evening),
    # so morning_candidates never received catalyst enrichment. Correct order:
    # write_morning_candidates → run_catalyst_truth → run_morning_validator.
    run_catalyst_truth_layer(_run_id, stage="pre_morning_validation")

    try:
        from morning_thesis_validator import run_morning_validation
        results = run_morning_validation(
            candidates_path = _candidates_path,
            output_path     = _output_path,
            run_id          = _run_id,
            max_signals     = cfg.MORNING_VALIDATION_MAX_SIGNALS,
            tier_filter     = cfg.MORNING_VALIDATION_TIERS,
            live_mode       = True,
            runs_dir        = cfg.RUNS_DIR,
            pipeline_mode   = "MORNING_VALIDATION",
        )
        go_count      = sum(1 for r in results if r.get("execution_permission") == "GO")
        armed_count   = sum(1 for r in results if r.get("execution_permission") == "ARMED")
        wait_count    = sum(1 for r in results if r.get("execution_permission") == "WAIT")
        blocked_count = sum(1 for r in results if r.get("execution_permission") == "BLOCKED")
        logger.info(
            "✅ Morning validation complete — %d GO | %d ARMED | %d WAIT | %d BLOCKED | output: %s",
            go_count, armed_count, wait_count, blocked_count, _output_path.name,
        )
        # ── PHASE 11: Execution Gate ──────────────────────────────────────────
        # Apply live-market feasibility checks to morning-validated signals.
        # Checks: spread ≤ 8%, delta 0.30–0.60, IV ≤ 60%, runway ≥ 1.5%,
        # gamma flip positioning, breakeven vs runway feasibility.
        # Maps campaign/execution verdicts to final_action for trade dispatch.
        # Non-critical — morning workflow completes regardless.
        try:
            from execution_gate import run_execution_gate
            _gate_dir = cfg.RUNS_DIR / _run_id / "trades"
            gated_signals, gate_summary = run_execution_gate(
                signals    = results,
                run_id     = _run_id,
                output_dir = _gate_dir,
            )
            _actionable = [s for s in gated_signals
                           if s.get("final_action") in ("BUY_NOW", "BUY_SMALL")]
            logger.info(
                "✅ Phase 11 (Execution Gate) — %d actionable | actions: %s | "                "reasons: %s | output: %s",
                len(_actionable),
                gate_summary.get("action_counts", {}),
                gate_summary.get("reason_counts", {}),
                gate_summary.get("gated_csv", "?"),
            )
            if not _actionable:
                logger.warning(
                    "⚠️  Phase 11 — 0 actionable signals after execution gate. "                    "Check spread, delta, IV, runway, and campaign/execution verdicts "                    "in execution_gated_%s.csv",
                    _run_id,
                )
        except Exception as _gate_err:
            logger.warning(
                "⚠️  Phase 11 (Execution Gate) failed — morning workflow continues. "                "Error: %s", _gate_err
            )
        # ─────────────────────────────────────────────────────────────────────

        return True

    except Exception as _mv_err:
        logger.error("❌ Morning validation failed: %s", _mv_err, exc_info=True)
        return False



def enforce_handoff_conflict_guard(run_id: str) -> bool:
    """Downgrade rows where downstream labels contradict committed baton fields."""
    try:
        import pandas as _pd_guard

        _eil_path = cfg.RUNS_DIR / run_id / "superbrain" / f"eil_enriched_{run_id}.csv"
        if not _eil_path.exists():
            logger.warning("handoff_guard: eil_enriched not found -- skipping")
            return not _strict_actuarial_v6_enabled()

        df = _pd_guard.read_csv(_eil_path, low_memory=False)
        if df.empty:
            logger.warning("handoff_guard: eil_enriched is empty -- skipping")
            return not _strict_actuarial_v6_enabled()

        execution_like = {"PROBE", "REDUCED", "EXECUTE", "FULL_EXECUTE", "BUY_NOW", "BUY_SMALL", "GO"}

        def _series(name: str, default=""):
            return df[name] if name in df.columns else _pd_guard.Series(default, index=df.index)

        mode = _series("pse_execution_mode").fillna("").astype(str).str.upper()
        fd = _series("fd_verdict").fillna("").astype(str).str.upper()
        final = _series("thesis_decision").fillna("").astype(str).str.upper()
        exec_mask = mode.isin(execution_like) | fd.isin({"EXECUTE", "EXECUTE_WITH_CAUTION", "GO"}) | final.eq("GO")

        eil_blocked = _series("eil_v3_verdict").fillna("").astype(str).str.upper().isin({"BLOCKED", "BLOCK"})
        trigger_primary = _series("trigger_primary").fillna("").astype(str).str.upper()
        trigger_quality = _series("trigger_quality").fillna("").astype(str).str.upper()
        trigger_stale = _series("trigger_stale", False).fillna(False).astype(str).str.upper().isin({"TRUE", "1", "YES"})
        trigger_missing = trigger_primary.isin({"", "NONE", "NAN"}) | trigger_quality.isin({"", "NONE", "NAN"})

        missing_phase2_fields = [field for field in PHASE2_LAYER2_FIELDS if field not in df.columns]
        phase2_missing = _pd_guard.Series(False, index=df.index)
        if missing_phase2_fields:
            phase2_missing = _pd_guard.Series(True, index=df.index)
            for field in missing_phase2_fields:
                df[field] = None
        else:
            critical_phase2 = [
                "layer2__state_match_method",
                "layer2__sample_size",
                "layer2__sample_confidence_bucket",
                "layer2__confidence_penalty",
                "layer2__probability_verdict",
            ]
            for field in critical_phase2:
                phase2_missing = phase2_missing | df[field].isna() | df[field].astype(str).str.strip().isin({"", "nan", "None"})

        conflict_reasons = []
        for idx in df.index:
            reasons = []
            if bool(exec_mask.loc[idx] and eil_blocked.loc[idx]):
                reasons.append("EIL_BLOCKED_WITH_EXECUTION_MODE")
            if bool(exec_mask.loc[idx] and trigger_stale.loc[idx]):
                reasons.append("TRIGGER_STALE_WITH_EXECUTION_MODE")
            if bool(exec_mask.loc[idx] and trigger_missing.loc[idx]):
                reasons.append("TRIGGER_MISSING_WITH_EXECUTION_MODE")
            if bool(exec_mask.loc[idx] and phase2_missing.loc[idx]):
                reasons.append("PHASE2_BATON_MISSING_WITH_EXECUTION_MODE")
            conflict_reasons.append("|".join(reasons))

        df["handoff_conflict_flags"] = conflict_reasons
        conflict_mask = df["handoff_conflict_flags"].astype(str).str.len() > 0

        if conflict_mask.any():
            df.loc[conflict_mask, "handoff_status"] = "CONFLICT_DETECTED"
            df.loc[conflict_mask, "capital_permission"] = "NO"
            df.loc[conflict_mask, "pse_execution_mode"] = "WATCHLIST"
            df.loc[conflict_mask, "pse_final_size"] = 0.0
            df.loc[conflict_mask, "fd_verdict"] = "WATCHLIST"
            df.loc[conflict_mask, "fd_size"] = 0.0
            logger.warning(
                "handoff_guard: downgraded %d conflicting execution-like rows before downstream export",
                int(conflict_mask.sum()),
            )
        else:
            if "handoff_status" not in df.columns:
                df["handoff_status"] = "PASS"
            logger.info("handoff_guard: no execution/baton contradictions detected")

        if missing_phase2_fields:
            logger.warning("handoff_guard: missing Phase 2 fields: %s", missing_phase2_fields)

        df.to_csv(_eil_path, index=False)
        if _strict_actuarial_v6_enabled() and (conflict_mask.any() or missing_phase2_fields):
            logger.error("STRICT ACTUARIAL V6: handoff guard blocked downstream execution.")
            return False
        return True
    except Exception as _guard_err:
        logger.warning("handoff_guard failed -- %s", _guard_err)
        return not _strict_actuarial_v6_enabled()


def inject_actuarial_into_eil_csv(run_id: str) -> None:
    """
    Post-EIL actuarial injection (v3.1 FIX).

    EIL subprocess builds actuarial_map from package JSONs at runtime.
    Guard condition: pkg["actuarial"].get("enriched_by") must be truthy.
    Phase 8.5 writes enriched_by on exact/fallback match — this should work.

    However, the subprocess log shows "Actuarial map empty" despite Phase 8.5
    confirming 1296 exact + 168 fallback matches. Root cause: the subprocess
    reads packages but actuarial_map stays empty — possible timing, path, or
    encoding issue in the subprocess context.

    This function runs AFTER EIL completes in the orchestrator process (not subprocess),
    reads packages directly, and stamps actuarial_* columns into eil_enriched.
    This is authoritative — it runs in the same process as Phase 8.5 and uses
    the same base_dir, so package paths are guaranteed correct.

    Idempotent: if actuarial cols already present and non-null, skips.
    """
    try:
        import glob as _glob
        import pandas as _pd_act

        _pkg_dir     = cfg.RUNS_DIR / run_id / "packages"
        _eil_path    = cfg.RUNS_DIR / run_id / "superbrain" / f"eil_enriched_{run_id}.csv"

        if not _eil_path.exists():
            logger.warning("inject_actuarial: eil_enriched not found — skipping")
            return
        if not _pkg_dir.exists():
            logger.warning("inject_actuarial: packages dir not found — skipping")
            return

        # Build actuarial map from packages
        actuarial_map = {}
        for _pf in _glob.glob(str(_pkg_dir / "*.package.json")):
            try:
                with open(_pf, "r", encoding="utf-8") as f:
                    _pkg = json.load(f)
                _ticker = str(_pkg.get("ticker", "")).strip().upper()
                _act    = _pkg.get("actuarial", {})
                if _ticker and isinstance(_act, dict) and _act.get("enriched_by"):
                    actuarial_map[_ticker] = _act
            except Exception:
                pass

        if not actuarial_map:
            logger.warning(
                "inject_actuarial: no packages with enriched_by found — "
                "Phase 8.5 may not have run or packages are unreadable"
            )
            return

        logger.info("inject_actuarial: loaded %d packages with actuarial data", len(actuarial_map))

        # Load eil_enriched
        _eil_df = _pd_act.read_csv(_eil_path, low_memory=False)

        # Check if already injected and non-null
        _act_col = "actuarial_win_rate_10d"
        if _act_col in _eil_df.columns and _eil_df[_act_col].notna().sum() > len(_eil_df) * 0.5:
            logger.info("inject_actuarial: actuarial cols already populated — skipping")
            return

        # Map of output_col → actuarial dict key
        _ACT_MAP = [
            ("actuarial_win_rate_10d",      "win_rate_10d"),
            ("actuarial_efficiency_10d",    "efficiency_10d"),
            ("actuarial_expected_move_10d", "expected_move_10d"),
            ("actuarial_risk_10d",          "risk_10d"),
            ("actuarial_penalty",           "penalty_multiplier"),
            ("actuarial_valid",             "valid"),
            ("actuarial_depth",             "fallback_depth"),
            ("actuarial_sample",            "sample_size"),
            ("actuarial_no_match",          "no_match"),
            # Flat aliases for EDE secondary lookup
            ("win_rate_10d",                "win_rate_10d"),
            ("efficiency_10d",              "efficiency_10d"),
            ("expected_move_10d",           "expected_move_10d"),
            # ── V2 Signal Intelligence fields (Sprint 3) ──────────────────────
            # These flow from actuarial_query Stage 0 → ActuarialOutcomes
            # → Vanguard packages → actuarial_map → eil_enriched CSV
            # → _enrich_row_for_ev() → ev_inputs_from_row() → EVEngineV2
            # → PSE _regime_multiplier() → pse_signal_type in output row
            ("actuarial_signal_type",           "signal_type"),
            ("actuarial_momentum_tier",         "momentum_tier"),
            ("actuarial_forward_momentum_conf", "forward_momentum_confidence"),
            ("actuarial_phase_v2",              "phase_v2"),
            ("actuarial_momentum_bucket",       "momentum_bucket"),
            ("actuarial_location_bucket",       "location_bucket"),
            # ── 9-dim match dimension pass-through (2026-05-20) ──────────────
            # These fields are used by actuarial_query MATCH_EXACT_DIMS for
            # higher-precision historical matching. Promoting them into
            # eil_enriched lets downstream audit tools verify which dim
            # values drove the match.
            ("actuarial_wyckoff_phase_bucket",  "wyckoff_phase_bucket"),
            ("actuarial_trend_maturity",        "trend_maturity"),
            ("actuarial_iv_regime",             "iv_regime"),
            ("actuarial_crabel_state",          "crabel_state"),
            ("actuarial_horizon_bucket",        "horizon_bucket"),
            ("actuarial_volume_bucket",         "volume_bucket"),
        ] + [(field, field) for field in PHASE2_LAYER2_FIELDS]

        _eil_df["ticker_upper"] = _eil_df["ticker"].str.strip().str.upper()
        _patched = 0

        for _out_col, _act_key in _ACT_MAP:
            if _out_col not in _eil_df.columns:
                _eil_df[_out_col] = None

        for _idx, _row in _eil_df.iterrows():
            _t = _row.get("ticker_upper", "")
            if _t in actuarial_map:
                _act = actuarial_map[_t]
                _phase2_baton = _act.get("phase2_baton")
                if isinstance(_phase2_baton, dict):
                    _act = {**_phase2_baton, **_act}
                for _out_col, _act_key in _ACT_MAP:
                    _val = _act.get(_act_key)
                    if _val is not None:
                        _eil_df.at[_idx, _out_col] = _val
                _patched += 1

        _eil_df = _eil_df.drop(columns=["ticker_upper"], errors="ignore")
        _eil_df.to_csv(_eil_path, index=False)

        _filled = _eil_df["actuarial_win_rate_10d"].notna().sum()
        logger.info(
            "✅ inject_actuarial: %d rows patched | actuarial_win_rate_10d filled=%d/%d → %s",
            _patched, _filled, len(_eil_df), _eil_path.name
        )

    except Exception as e:
        logger.warning("inject_actuarial: failed (non-critical) — %s", e)

# ============================================================ CLI =============

def main() -> None:
    parser = argparse.ArgumentParser(description="AVSHUNTER Intelligent Orchestrator v3.1")

    parser.add_argument(
        "--run-id",
        dest="run_id",
        default=None,
        help="Optional run identifier e.g. 20260215_120000. Auto-generated if omitted.",
    )
    parser.add_argument("--evening",   action="store_true", help="Run evening workflow (discovery → VANGUARD → EIL → Kelly → EOD candidate manifest)")
    parser.add_argument("--morning",   action="store_true", help="Run morning validation at 09:45 ET (live data scoring against EOD candidates)")
    parser.add_argument("--premarket", action="store_true", help="[DEPRECATED] Use --morning instead")
    parser.add_argument("--force",     action="store_true", help="Bypass market hours guard -- allow --evening during market hours (CAUTION: intraday data produces corrupted EOD candidates)")
    parser.add_argument(
        "--data-mode",
        choices=["EOD", "LATEST"],
        default="EOD",
        help=(
            "Bar data source for the evening pipeline. "
            "EOD (default): uses completed daily bars — requires running after 16:15 ET. "
            "LATEST: uses the most recent Polygon snapshot — safe to run at any time. "
            "In LATEST mode all signals are stamped data_mode=LATEST and MVE applies "
            "EOD thresholds (lower MVS, PARTIAL trigger accepted for EXECUTE). "
            "Use LATEST when you need to run the pipeline mid-session or for research."
        ),
    )

    # NEW: Dynamic universe gates
    parser.add_argument("--min_universe", type=int, default=1000,
                        help="Hard minimum tickers required (FAIL below this). Default: 1000")
    parser.add_argument("--target_universe", type=int, default=6500,
                        help="Soft target ticker count (WARN below this in AUTO). Default: 6500")
    parser.add_argument("--universe_gate_mode", choices=["HARD", "SOFT", "AUTO"], default="AUTO",
                        help="HARD=enforce target; SOFT=enforce min only; AUTO=min fails, target warns (recommended)")
    parser.add_argument(
        "--universe",
        default=None,
        help=(
            "Override universe file for test/research runs. "
            "Provide a CSV with a 'ticker' header column. "
            "Example: data\\\\universe\\\\test_universe_50.csv"
        ),
    )

    args = parser.parse_args()

    if args.evening:
        success = evening_workflow(
            run_id=args.run_id,
            min_universe=args.min_universe,
            target_universe=args.target_universe,
            universe_gate_mode=args.universe_gate_mode,
            force=args.force,
            universe_override=Path(args.universe).resolve() if args.universe else None,
            data_mode=args.data_mode,
        )
    elif args.morning or args.premarket:
        if args.premarket:
            logger.warning("⚠️  --premarket is deprecated. Use --morning instead.")
        success = premarket_workflow(run_id=args.run_id)
    else:
        logger.error("Must specify --evening or --morning")
        logger.error("  python intelligent_orchestrator.py --evening")
        logger.error("  python intelligent_orchestrator.py --morning")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
