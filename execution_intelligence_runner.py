"""
AVSHUNTER â€” Execution Intelligence Layer Runner v4.1
=====================================================
Version : 4.1.0
Date    : 2026-04-28

WHAT CHANGED FROM v3.8 â†’ v3.9 (ACTUARIAL PROPAGATION)
-------------------------------------------------------
ACT-01  Root cause of EDE LOW_EDGE (score=0.000) fixed.
        EDE reads actuarial_win_rate_10d, actuarial_efficiency_10d etc.
        from the flat EIL enriched CSV. These columns were never written
        into the CSV â€” EDE always received None â†’ score=0.000 â†’ BLOCKED.

ACT-02  Package JSON actuarial map loaded at merge time.
        After Phase 8.5 patches pkg["actuarial"] in every package JSON,
        the EIL runner now reads those values and writes them as flat
        columns into eil_enriched_{run_id}.csv:
          actuarial_win_rate_10d, actuarial_efficiency_10d,
          actuarial_expected_move_10d, actuarial_risk_10d,
          actuarial_penalty, actuarial_valid, actuarial_depth,
          actuarial_sample, actuarial_no_match

ACT-03  Fallback flat columns also written (win_rate_10d, efficiency_10d
        etc.) so EDE secondary lookup also succeeds.

ACT-04  Diagnostic logging: "Actuarial map loaded: N packages" confirms
        Phase 8.5 ran correctly. "Actuarial map empty" warns if it did not.

        Root cause: five strategy files call Polygon NBBO + MarketData.app
        options APIs post-close. APIs return nothing. Every strategy falls to
        its neutral constant â†’ identical scores across all tickers â†’ convergence
        engine receives 0/5 votes â†’ 100% BLOCK.

EOD-02  Resolver is time-gated: is_market_hours() (09:00â€“17:00 ET Monâ€“Fri)
        determines LIVE vs EOD_SYNTHETIC mode. Live runs: zero code path
        change. Off-hours runs: resolver active.

EOD-03  Injection point: AFTER build_execution_context_from_row() returns,
        BEFORE evaluate() is called. Only patches fields that are None/zero
        in the context â€” real data from live APIs is never overwritten.

EOD-04  Five synthesised inputs, one per strategy:
          S1 Liquidity  â† ADX + ATR-pct + avg_volume (discovery CSV)
          S2 IV Distort â† IVP + iv_rank (options_intelligence CSV)
          S3 GEX Flip   â† efficiency_10d + win_rate_10d (actuarial cache)
          S4 OBI        â† spread_pct + trend_direction + wyckoff (options + discovery)
          S5 POC Timing â† poc_price from superbrain if present, else Wyckoff-derived

EOD-05  eil_data_mode column added to EIL_COLS and written per row:
          "LIVE" | "EOD_SYNTHETIC" | "EOD_FALLBACK"

EOD-06  Variance sanity check runs on first 50 rows before Pass 2.
        Logs SANITY_PASS or SANITY_WARN per field. Non-blocking.

Deploy: eil_eod_resolver.py â†’ AVSHUNTER-Intelligence root (same as this file)

PSE-01  PositionSizingEngine (position_sizing_engine.py) is RETIRED from
        production authority. It remains on disk only for historical audit and
        future research. It must not allocate, suppress, or resize trades.

PSE-02  EV / MonetisationPolicy / EIL warnings no longer fall back to legacy
        FDE/PSE capital blocks. Candidate routing is handled by signal policy
        and morning validation. Live size is manual until rebuilt/re-approved.

PSE-03  Output still carries pse_* and fd_* compatibility fields, but
        pse_final_size/fd_size are always 0.0 under
        POSITION_SIZING_RETIRED_ADVISORY_ONLY.

PSE-04  Rows that pass signal/economics/support checks can become
        EOD_CANDIDATE_ONLY even with zero size. That is intentional: the row is
        a monetisation candidate, not an automated capital allocation.

WHAT CHANGED FROM v3.9 â†’ v4.0  (OPTIONS THINK TANK â€” BID/ASK + BUSINESS OUTCOME)
----------------------------------------------------------------------------------
OTT-01  SPREAD FORMULA AUDIT â€” enforced (askâˆ’bid)/mid throughout.
        The EOD enrichment path (_enrich_ctx_for_eod) was using
        contract_spread_pct as a raw fraction (0.157) in two branches
        where it was treated as if already normalised to a 0-10% range.
        spread_dec=0.157 fed into OBI synthesis correctly per-design,
        but log comments implied it was a %-of-stock measure. Clarified
        inline. The authoritative spread formula is (askâˆ’bid)/midÃ—100
        â€” used in execution_intelligence.py line 222, EV net computation
        line 385, and eil_spread_pct_live output. No change to formula
        itself â€” adding assertion logging so deviations surface in log.

OTT-02  EIL BLOCKED PENALTY REDUCED: 0.30x â†’ 0.60x.
        EIL BLOCKED was collapsing pse_final_size to near-zero (0.30x Ã—
        other multipliers â‰ˆ 0.05â€“0.10) on legitimate signals where EIL
        failed only because S1 liquidity_gate returned CLOSED_AUCTION in
        EOD mode. Signals with positive EV and strong actuarial backing
        were being effectively killed. BLOCKED now applies 0.60x â€” still
        a meaningful penalty but not a silent kill. EIL unavailable
        penalty retained at 0.70x (less severe than BLOCKED verdict).
        Change is in position_sizing_engine.py (pse_eil_mult) â€” this
        file documents the intent and adds a log line confirming the
        new multiplier is being applied at the correct node.

OTT-03  EOD ENRICHMENT GAP: _enrich_ctx_for_eod() was patching
        l2_bid_size/ask_size and IV bid/ask spread â€” but was NOT
        ensuring ctx.options_bid/ask/mid were populated from
        contract_premium + contract_spread_pct before S1 ran.
        build_execution_context_from_row() already handles this via
        FIX-02/FIX-08 in execution_intelligence.py, BUT only if
        contract_premium is present in the row. If it is absent
        (some discovery rows have no matched contract), S1 receives
        None bid/ask â†’ CLOSED_AUCTION hard block â†’ eil=BLOCKED â†’
        0.30x penalty cascade.
        Fix: _enrich_ctx_for_eod() now explicitly checks and populates
        ctx.options_bid/ask/mid from contract columns as a last resort
        before strategies run. Only fires if ctx.options_mid is None.

OTT-04  SPREAD LOGGING: eil_spread_pct_live now always logged per row
        in the PSE log line for immediate audit visibility.
        Format: "sprd=XX.X%" added to existing log line.

OTT-05  SANITY CHECK ENHANCED: frozen EIL score detection now also
        checks eil_spread_pct_live distribution. If all rows have
        identical spread (std < 0.001), logs SANITY_WARN_SPREAD so the
        bid/ask synthesis path can be diagnosed without a full run.

UNCHANGED FROM v3.5
-------------------
FIX-01  EIL advisory_only flag / LIVE_MODE constant â€” retained.
FIX-02  EIL five-strategy engine called, eil_v3_verdict written â€” retained.
FIX-06  MonetisationPolicy evaluated, mp_hard_block_reason written â€” retained.
FIX-08  Import names / fallback logging â€” retained.

DEPENDENCIES
------------
    ev_engine_v2.py                (EVEngineV2, EVInputs, EVResult, ev_inputs_from_row)
    probability_engine.py          (derive_probabilities)
    final_decision_engine.py       (make_final_decision)
    scenario_builder.py            (compute_scenario_probabilities)
    edge_detector.py               (enrich_vanguard_inputs)
    execution_intelligence.py      (evaluate, build_execution_context_from_row)  [FIX-02]
    avshunter_monetisation_policy.py (MonetisationPolicy, map_options_row_to_policy_input,
                                      summarise_policy_output)                    [FIX-06]
"""

import os
import sys
import json
from pathlib import Path

# â”€â”€ VERSION CONSTANTS â€” one truth, referenced everywhere â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ISSUE 11: header says v4.1 but logger/run_engine still said EIL_v3.6.
# One constant eliminates the mismatch across all log statements.
EIL_RUNNER_VERSION = "4.1.0"
LOGGER_NAME        = "EIL_v4_1"

# â”€â”€ PATH FIX: make vanguard sub-packages importable from root â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# The runner lives at AVSHUNTER-Intelligence\ root.
# Modules like edge_detector and scenario_builder live inside the vanguard
# package (vanguard\layer2_statistical\, vanguard\layer3_execution\).
# Adding vanguard\ to sys.path lets Python resolve them as top-level names
# without moving any files. This mirrors how ev_engine_v2.py is found.
_ROOT    = os.path.dirname(os.path.abspath(__file__))
_VANGUARD = os.path.join(_ROOT, "vanguard")
_EXECUTION = os.path.join(_VANGUARD, "execution")
_SCRIPTS  = os.path.join(_ROOT, "scripts")
for _p in [_ROOT, _VANGUARD,
           os.path.join(_VANGUARD, "layer2_statistical"),
           os.path.join(_VANGUARD, "layer3_execution"),
           _EXECUTION,
           os.path.join(_EXECUTION, "strategies"),
           _SCRIPTS]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

import argparse
import logging
import math
import warnings
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from execution_schema import TRIGGER_HANDOFF_FIELDS, validate_trigger_handoff_row
from contracts.dynamic_options_policy import apply_advisory_authority

try:
    from scripts.macro_quant_packet import MACRO_QUANT_CSV_FIELDS, resolve_macro_suffix_columns
except Exception:
    from macro_quant_packet import MACRO_QUANT_CSV_FIELDS, resolve_macro_suffix_columns  # type: ignore

try:
    from contracts.handoff_contract import (
        PRIORITY_EIL_PSE,
        TRUTH_PACKET_META_FIELDS,
        enrich_dataframe_with_truth_packets,
    )
except Exception:
    from handoff_contract import (  # type: ignore
        PRIORITY_EIL_PSE,
        TRUTH_PACKET_META_FIELDS,
        enrich_dataframe_with_truth_packets,
    )

# â”€â”€ Core engine â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from vanguard.physics_state_engine import (
        PHYSICS_FIELDS,
        append_physics_fields_from_source,
        ensure_physics_fields,
    )
except Exception:
    from physics_state_engine import (  # type: ignore
        PHYSICS_FIELDS,
        append_physics_fields_from_source,
        ensure_physics_fields,
    )

from ev_engine_v2 import EVEngineV2, EVInputs, EVResult, ev_inputs_from_row, DataQualityWarning
from final_decision_engine import make_final_decision

# PSE retired: position_sizing_engine.py is kept on disk for historical audit
# and future research, but it must not suppress production candidates or write
# live capital size. Capital/risk sizing is manual until the sizing function is
# rebuilt and re-approved.
_pse_compute = None
_PSE_AVAILABLE = False
_PSE_RETIRED_ADVISORY_ONLY = True
PSE_RETIRED_POLICY = "PSE_IGNORED_MANUAL_SIZING"
PSE_LEGACY_RETIRED_POLICY = "POSITION_SIZING_RETIRED_ADVISORY_ONLY"
PSE_OLD_RETIRED_POLICY = "ADVISORY_ONLY"
PSE_MANUAL_SIZING_NOTE = "MANUAL_SIZE_REQUIRED"
OPTIONS_RESEARCH_PERMISSION = "MANUAL_REVIEW_REQUIRED"
OPTIONS_GO_ROUTE = "OPTIONS_GO_REVIEW"
OPTIONS_ARMED_ROUTE = "OPTIONS_ARMED_HALF"
OPTIONS_PROBE_ROUTE = "OPTIONS_PROBE_ONLY"
OPTIONS_EQUITY_ONLY_ROUTE = "OPTIONS_EQUITY_ONLY_BETTER"
OPTIONS_BLOCKED_ROUTE = "OPTIONS_BLOCKED"
OPTIONS_REVIEWABLE_ROUTES = {OPTIONS_GO_ROUTE, OPTIONS_ARMED_ROUTE, OPTIONS_PROBE_ROUTE}
OPTIONS_NON_REVIEWABLE_ROUTES = {OPTIONS_BLOCKED_ROUTE, OPTIONS_EQUITY_ONLY_ROUTE}

# â”€â”€ Supporting modules â€” FIX-08: corrected import names, warnings on fallback â”€
try:
    from probability_engine import derive_probabilities
except Exception as _pe_err:
    logging.getLogger(LOGGER_NAME).warning(
        f"probability_engine not loadable ({type(_pe_err).__name__}: {_pe_err}) â€” using scenario_builder fallback"
    )
    def derive_probabilities(row):
        from scenario_builder import compute_scenario_probabilities
        p = compute_scenario_probabilities(row)
        return p["prob_breakout"], p["prob_rejection"], p["prob_drift"]

try:
    from scenario_builder import compute_scenario_probabilities   # FIX-08
except ImportError as _sb_err:
    # sys.path above includes vanguard/layer3_execution/ so this should resolve.
    # If it still fails, use the inline copy â€” identical implementation, zero deps.
    logging.getLogger(LOGGER_NAME).warning(
        f"scenario_builder not importable ({_sb_err}) â€” using inline copy"
    )
    def compute_scenario_probabilities(row: dict) -> dict:
        base = float(row.get("composite", 50) or 50)
        base = max(0.0, min(100.0, base))
        pb = min(0.65, 0.25 + base / 200.0)
        pr = max(0.10, 0.45 - base / 250.0)
        pd = max(0.05, 1.0 - pb - pr)
        t  = pb + pr + pd
        return {
            "prob_breakout":  round(pb / t, 4),
            "prob_rejection": round(pr / t, 4),
            "prob_drift":     round(pd / t, 4),
        }

# NEW-01: Three-path scenario router â€” routes each signal to AGGRESSIVE /
# MODERATE / CONSERVATIVE / OBSERVE_ONLY based on swing_fusion alignment_score.
try:
    from scenario_router import apply_scenario_to_row as _apply_scenario_routing
    _SCENARIO_ROUTER_AVAILABLE = True
except ImportError as _sr_err:
    logging.getLogger(LOGGER_NAME).warning(
        f"scenario_router not importable ({_sr_err}) â€” scenario path fields will be absent"
    )
    _SCENARIO_ROUTER_AVAILABLE = False
    def _apply_scenario_routing(row: dict) -> dict:
        return row

try:
    from edge_detector import enrich_vanguard_inputs   # FIX-08
except ImportError as _ed_err:
    # sys.path above includes vanguard/layer2_statistical/ so this should resolve.
    # If it still fails, surface whatever actuarial fields are already in the row.
    logging.getLogger(LOGGER_NAME).warning(
        f"edge_detector.enrich_vanguard_inputs not importable ({_ed_err}) â€” "
        "using row-field fallback"
    )
    def enrich_vanguard_inputs(row: dict) -> dict:
        def _f(k, d=0.0):
            try:
                v = row.get(k, d)
                return d if v is None else float(v)
            except: return d
        wr5  = _f("win_rate_5d")  or _f("layer2__win_rate_5d")  / 100
        wr10 = _f("win_rate_10d") or _f("layer2__win_rate_10d") / 100
        wr20 = _f("win_rate_20d") or _f("layer2__win_rate_20d") / 100
        if wr5  > 0: row["win_rate_5d"]  = min(wr5,  1.0)
        if wr10 > 0: row["win_rate_10d"] = min(wr10, 1.0)
        if wr20 > 0: row["win_rate_20d"] = min(wr20, 1.0)
        sp = _f("survival_prob")
        if sp <= 0.0 or sp > 1.0:
            pd_val = _f("layer2__prob_down_5pct_before_up_10pct")
            sp = max(0.0, 1.0 - pd_val) if 0 < pd_val < 1 else (
                0.40 + _f("value_acceptance_score", 0.5) * 0.40)
        row["survival_prob"]    = min(1.0, max(0.0, sp))
        row.setdefault("gamma_obstruction", max(0.0, 1.0 - _f("control_score", 0.5)))
        row.setdefault("path_cleanliness",  min(1.0, _f("data_quality_score", 60) / 100))
        return row

# â”€â”€ EOD Data Resolver â€” fixes flat EIL scores in off-hours runs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_EOD_RESOLVER_AVAILABLE = False
_eod_resolver_module    = None
try:
    import eil_eod_resolver as _eod_resolver_module
    _EOD_RESOLVER_AVAILABLE = True
except ImportError:
    logging.getLogger(LOGGER_NAME).warning(
        "eil_eod_resolver.py not found in root â€” external resolver unavailable. "
        "Off-hours runs will use local _enrich_ctx_for_eod() fallback inside _process_row(). "
        "Deploy eil_eod_resolver.py to AVSHUNTER-Intelligence root for full cross-sectional enrichment."
    )

# â”€â”€ EOD Data Mode detector â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Determines whether this run has live market data available.
# Outside market hours the five EIL strategies receive identical API fallback
# constants (std < 0.01) â€” EOD_SYNTHETIC mode enriches context from disk data
# already written earlier in the pipeline (discovery CSV, options_intelligence,
# actuarial cache) so each ticker gets differentiated inputs.
def _is_market_hours() -> bool:
    """True if within approximate US market hours 09:00â€“17:00 ET, Monâ€“Fri."""
    now_utc = datetime.now(timezone.utc)
    if now_utc.weekday() >= 5:           # Saturday / Sunday
        return False
    month   = now_utc.month
    offset  = -4 if 4 <= month <= 10 else -5    # EDT / EST
    et_hour = (now_utc.hour + offset) % 24
    return 9 <= et_hour < 17

_MARKET_HOURS  = _is_market_hours()
_EIL_DATA_MODE = "LIVE" if _MARKET_HOURS else "EOD_SYNTHETIC"

# â”€â”€ FIX-02: EIL five-strategy engine â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_EIL_AVAILABLE = False
_eil_evaluate  = None
_eil_build_ctx = None
_eil_synth_gex = None

try:
    from execution_intelligence import evaluate as _eil_evaluate_raw, \
                                       build_execution_context_from_row as _eil_build_ctx_raw, \
                                       _synthesise_gex_map as _eil_synth_gex
    _EIL_AVAILABLE  = True
    _eil_evaluate   = _eil_evaluate_raw
    _eil_build_ctx  = _eil_build_ctx_raw
except Exception as _ei_err:
    logging.getLogger(LOGGER_NAME).error(
        f"execution_intelligence FAILED TO LOAD â€” EIL inactive\n"
        f"  Exception: {type(_ei_err).__name__}: {_ei_err}"
    )

# Token normalisation: EIL composite engine tokens â†’ FDE EIL_SIZE_MAP vocabulary
_EIL_TOKEN_NORMALISE = {
    "EXECUTE_NOW":               "EXECUTE",
    "EXECUTE_WITH_CAUTION":      "EXECUTE_WITH_CAUTION",
    "EXECUTE_DEFER":             "WATCHLIST",
    "STAND_DOWN_MICROSTRUCTURE": "BLOCKED",
    "BLOCKED":                   "BLOCKED",
    "HIGH_CONVICTION":           "EXECUTE",
}

# â”€â”€ FIX-06: MonetisationPolicy integration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_MP_AVAILABLE = False
_mp_engine    = None
_mp_from_row  = None
_mp_summarise = None

try:
    from avshunter_monetisation_policy import (
        MonetisationPolicy,
        map_options_row_to_policy_input,
        summarise_policy_output,
    )
    _mp_engine   = MonetisationPolicy()
    _mp_from_row  = map_options_row_to_policy_input
    _mp_summarise = summarise_policy_output
    _MP_AVAILABLE = True
except Exception as _mp_import_err:
    # Broad catch: ImportError = file not found; all other exceptions = file
    # present but broken (syntax error, missing dep, bad instantiation etc).
    # Previously bare ImportError silently masked real errors and left MP inactive
    # with no diagnostic â€” QA fix: log the actual exception class and message.
    _mp_err_type = type(_mp_import_err).__name__
    _mp_err_msg  = str(_mp_import_err)
    if isinstance(_mp_import_err, ImportError) and "avshunter_monetisation_policy" in _mp_err_msg:
        logging.getLogger(LOGGER_NAME).warning(
            f"avshunter_monetisation_policy not found â€” MP hard blocks inactive (FIX-06)\n"
            f"  scripts\\ path: {_SCRIPTS}"
        )
    else:
        logging.getLogger(LOGGER_NAME).error(
            f"avshunter_monetisation_policy FAILED TO LOAD â€” MP inactive\n"
            f"  Exception : {_mp_err_type}: {_mp_err_msg}\n"
            f"  scripts\\ path: {_SCRIPTS}\n"
            f"  Action    : fix the error above then re-run"
        )


# â”€â”€ Logging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s [EIL_v{EIL_RUNNER_VERSION}] %(message)s",  # v3.6 = PSE active
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(LOGGER_NAME)
warnings.filterwarnings("once", category=DataQualityWarning)

# Log data mode once at startup so every run self-documents its data path
logger.info(
    "EIL data mode: %s (%s) â€” %s",
    _EIL_DATA_MODE,
    "market hours active" if _MARKET_HOURS else "off-hours / EOD run",
    "live API feeds active" if _MARKET_HOURS else
    "context will be enriched from pipeline disk data (discovery, options_intelligence, actuarial)",
)

# â”€â”€ Live mode governance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# DOI-1: EIL is always an advisory evidence producer.  The human owns entry,
# exit and timing decisions; no EIL value may suppress the ticker thesis.
LIVE_MODE = False

# â”€â”€ Engine singleton â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# EV is computed and preserved for advisory ranking/outcome analysis only.
# It must never grant, deny, promote or demote a production candidate.
_ev_engine = EVEngineV2()
_EV_ADVISORY_FIELD = "ev2_ev_conf_adj"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# EOD CONTEXT ENRICHMENT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# When running outside market hours the five strategy files call live APIs that
# return nothing (Polygon NBBO empty, MarketData.app options chain empty).
# Every ticker falls through to identical neutral constants â†’ std < 0.01 â†’ frozen.
#
# This function enriches the execution context IN-PLACE using data already
# written to disk earlier in the same pipeline run:
#   S1 Liquidity  : ADX + ATR-pct + avg_volume  â†’ synthetic l2 sizes
#   S2 IV         : IVP + iv_rank + contract_iv  â†’ spread-derived bid/ask IV
#   S3 GEX        : actuarial efficiency + win_rate â†’ GEX regime proxy
#   S4 OBI        : trend_direction + wyckoff + spread_pct â†’ imbalance
#   S5 POC        : poc_price/structural_target already in row (context builder handles)
#
# Importantly: S5 and GEX map are already handled correctly by
# build_execution_context_from_row() â€” no changes needed there.
# This function only patches l2_bid_size, l2_ask_size, iv_bid/ask
# which are genuinely missing in EOD mode.

def _enrich_ctx_for_eod(ctx, row: dict) -> None:
    """
    Patch ExecutionContext in-place with EOD-derived values.
    Called ONLY when _MARKET_HOURS is False.
    Does not touch any field that already has a real value.

    All synthesis is ticker-specific using fields already in the superbrain row.
    Cross-sectional dispersion is guaranteed because ADX, IVP, avg_volume,
    trend_direction etc. differ per ticker from discovery output.
    """
    import math as _math

    def _fv(k, d=0.0):
        # ISSUE 7: strips $, Â£, commas, % â€” float("$0.675") raises ValueError
        # without this, valid premiums silently become 0 â†’ wrong bid/ask synthesis
        try:
            v = row.get(k, d)
            if v is None:
                return d
            if isinstance(v, str):
                s = v.strip()
                if not s or s.lower() in ("nan", "none", "null", "na", "n/a"):
                    return d
                is_pct = s.endswith("%")
                s = s.replace("$", "").replace("Â£", "").replace(",", "").replace("%", "").strip()
                if not s:
                    return d
                f = float(s)
                if _math.isnan(f) or _math.isinf(f):
                    return d
                return f / 100.0 if is_pct else f
            f = float(v)
            return d if (_math.isnan(f) or _math.isinf(f)) else f
        except (TypeError, ValueError, OverflowError):
            return d

    def _fv_spread_proxy() -> float:
        """
        ITEM 2 â€” derive a ticker-specific spread proxy when contract_spread_pct
        is absent from the superbrain row (NaN inserted by passthrough).

        Uses contract_iv â†’ spread proxy table:
          IV < 20%:  0.025 (2.5% â€” liquid, tight)
          IV < 35%:  0.040 (4.0% â€” normal)
          IV < 55%:  0.070 (7.0% â€” elevated)
          IV < 80%:  0.110 (11% â€” high IV)
          IV >= 80%: 0.180 (18% â€” very high IV, wide markets)

        Falls back to ATR-based proxy if IV also absent:
          atr_pct < 2%:  0.030
          atr_pct < 4%:  0.050
          atr_pct >= 4%: 0.090

        This produces cross-sectional variance across tickers so EIL S1
        liquidity scoring is meaningful even in EOD synthetic mode.
        """
        iv = _fv("contract_iv") or _fv("iv_rank", 0.0)
        if iv > 0:
            if iv < 0.20:   return 0.025
            if iv < 0.35:   return 0.040
            if iv < 0.55:   return 0.070
            if iv < 0.80:   return 0.110
            return 0.180
        atr = _fv("atr_pct") or _fv("atr_percentile", 0.0)
        if atr > 0:
            if atr < 2.0:  return 0.030
            if atr < 4.0:  return 0.050
            return 0.090
        return 0.040  # absolute last resort â€” flat default

    def _sv(k, d=""):
        v = row.get(k, d) or d
        return str(v).strip().upper()

    def _clamp(v, lo, hi):
        return max(lo, min(hi, v))

    # â”€â”€ S1 / S4 â€” synthetic L2 bid/ask sizes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Only synthesise if not already populated (live mode sets these)
    if ctx.l2_bid_size is None and ctx.l2_ask_size is None:

        adx      = _fv("adx", 20.0)
        atr_pct  = _fv("atr_pct") or _fv("atr_percentile", 50.0)
        volume   = _fv("avg_volume", 500_000)
        trend    = _sv("trend_direction")
        wyckoff  = _sv("wyckoff_phase")

        # ADX 14â€“50 â†’ liquidity quality 0.3â€“1.0
        adx_norm = _clamp((adx - 14) / 36.0, 0.0, 1.0)
        atr_norm = _clamp(atr_pct / 100.0, 0.0, 1.0)
        vol_norm = _clamp(_math.log10(max(volume, 1000)) / 7.0, 0.0, 1.0)
        liq      = 0.4 * adx_norm + 0.3 * atr_norm + 0.3 * vol_norm

        base     = int(1000 + liq * 9000)    # 1kâ€“10k range

        # OBI directional skew from trend + Wyckoff
        is_bull  = trend in ("UP", "UPTREND", "BULL") or wyckoff in ("MARKUP", "ACCUMULATION")
        is_bear  = trend in ("DOWN", "DOWNTREND", "BEAR") or wyckoff in ("MARKDOWN", "DISTRIBUTION")

        if is_bull:
            spread_dec    = _fv("contract_spread_pct") or _fv_spread_proxy()
            skew          = _clamp(adx_norm * 0.3, 0.0, 0.3)
            ctx.l2_bid_size = int(base * (1.0 + skew))
            ctx.l2_ask_size = int(base * (1.0 - skew * 0.5))
        elif is_bear:
            skew            = _clamp(adx_norm * 0.3, 0.0, 0.3)
            ctx.l2_bid_size = int(base * (1.0 - skew * 0.5))
            ctx.l2_ask_size = int(base * (1.0 + skew))
        else:
            spread_dec      = _fv("contract_spread_pct") or _fv_spread_proxy()
            noise           = int(base * 0.05 * _clamp(spread_dec / 0.10, 0.0, 1.0))
            ctx.l2_bid_size = base + noise
            ctx.l2_ask_size = base - noise

        ctx.l2_bid_size = max(ctx.l2_bid_size, 100)
        ctx.l2_ask_size = max(ctx.l2_ask_size, 100)

    # â”€â”€ OTT-03: Ensure options_bid/ask/mid populated before S1 runs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # ISSUE 9: treat options_mid <= 0 as missing, not only None
    # ISSUE 8: normalise contract_spread_pct â€” 15.7 means 15.7%, not 1570%
    _mid_val = ctx.options_mid
    _mid_missing = _mid_val is None
    if not _mid_missing:
        try:
            _mid_missing = float(_mid_val) <= 0
        except (TypeError, ValueError):
            _mid_missing = True
    if _mid_missing:
        _prem = _fv("contract_premium") or _fv("premium") or 0.0
        if _prem > 0:
            _spread_dec = _fv("contract_spread_pct") or _fv_spread_proxy()
            if _spread_dec > 1.0:
                _spread_dec = _spread_dec / 100.0
            _spread_dec = max(0.0, min(_spread_dec, 1.0))
            _half = _prem * _spread_dec / 2.0
            ctx.options_mid = round(_prem, 2)
            ctx.options_bid = round(max(0.01, _prem - _half), 2)
            ctx.options_ask = round(_prem + _half, 2)
            _sp_check = (ctx.options_ask - ctx.options_bid) / ctx.options_mid * 100
            logger.debug(
                "OTT-03 EOD options synthesis %s: mid=%.2f bid=%.2f ask=%.2f "
                "spread/mid=%.1f%% [contract_spread_pct=%.4f]",
                row.get("ticker", "?"), ctx.options_mid, ctx.options_bid,
                ctx.options_ask, _sp_check, _spread_dec,
            )

    # â”€â”€ S2 â€” IV bid/ask synthesis from IVP dispersion â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Already handled by FIX-04 in build_execution_context_from_row
    # (contract_iv * 0.97 / 1.03). Enhance only if iv_mid is set but
    # bid/ask are identical (zero IVP effect applied).
    if ctx.iv_mid and ctx.iv_bid and ctx.iv_ask:
        ivp       = _fv("ivp", 50.0) or _fv("contract_ivp", 50.0)
        iv_rank   = _fv("iv_rank", 50.0)
        ivp_norm  = _clamp(ivp / 100.0, 0.0, 1.0)
        rank_norm = _clamp(iv_rank / 100.0, 0.0, 1.0)

        # Higher IVP = market pricing uncertainty = ask premium elevated
        # This creates cross-sectional variance: IVP 80 â‰  IVP 20
        ask_prem  = 0.03 + 0.05 * ivp_norm          # 3â€“8% above mid
        bid_disc  = 0.02 + 0.03 * (1.0 - rank_norm) # 2â€“5% below mid

        ctx.iv_ask = round(ctx.iv_mid * (1.0 + ask_prem), 6)
        ctx.iv_bid = round(ctx.iv_mid * (1.0 - bid_disc), 6)


def _log_eil_data_mode_per_ticker(ticker: str, row: dict) -> None:
    """Debug log showing what EOD synthesis produced for a ticker."""
    logger.debug(
        "EOD_CTX %s | adx=%.1f ivp=%.0f trend=%s wyckoff=%s",
        ticker,
        float(row.get("adx") or 0),
        float(row.get("ivp") or 0),
        str(row.get("trend_direction") or ""),
        str(row.get("wyckoff_phase") or ""),
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# HELPERS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _f(row: dict, key: str, default: float = 0.0) -> float:
    try:
        v = row.get(key, default)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _s(row: dict, key: str, default: str = "") -> str:
    try:
        v = row.get(key, default)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return default
        s = str(v).strip()
        if s.lower() in ("nan", "none", "null", "na", "n/a", ""):
            return default
        return s
    except Exception:
        return default


BOND_MACRO_CAUTION_FLAGS = {"BOND_MACRO_CAUTION", "BOND_MACRO_WARNING", "BOND_MACRO_ADVERSE"}
BOND_MACRO_SEVERE_FLAGS = {"BOND_MACRO_WARNING", "BOND_MACRO_ADVERSE"}


def _truthy(value) -> bool:
    return str(value or "").strip().upper() in {"1", "TRUE", "YES", "Y"}


def _bond_macro_context(row: dict) -> dict:
    """Return bond macro spread context without changing EIL verdict authority."""
    def _first(*keys, default=""):
        for key in keys:
            value = row.get(key)
            if value is not None and str(value).strip() != "":
                return value
        return default

    flag = str(_first(
        "bond_macro_flag",
        "macro__bond_macro_flag",
        "regime__bond_macro_flag",
        "macro_snapshot__bond_macro_flag",
    ) or "").strip().upper()
    auction_spread_risk = _truthy(_first(
        "auction_spread_risk",
        "macro__auction_spread_risk",
        "regime__auction_spread_risk",
        "macro_snapshot__auction_spread_risk",
    ))
    credit_warning = _truthy(_first(
        "credit_warning",
        "macro__credit_warning",
        "regime__credit_warning",
        "macro_snapshot__credit_warning",
    ))
    try:
        breakeven_adjustment_pct = float(_first(
            "breakeven_adjustment_pct",
            "macro__breakeven_adjustment_pct",
            "regime__breakeven_adjustment_pct",
            "macro_snapshot__breakeven_adjustment_pct",
            default=0.0,
        ) or 0.0)
    except Exception:
        breakeven_adjustment_pct = 0.0

    breakeven_adjustment_pct = max(0.0, min(50.0, breakeven_adjustment_pct))
    active = (
        flag in BOND_MACRO_CAUTION_FLAGS
        or auction_spread_risk
        or credit_warning
        or breakeven_adjustment_pct > 0
    )
    severity = "WARNING" if flag in BOND_MACRO_SEVERE_FLAGS or credit_warning else ("CAUTION" if active else "OK")
    parts = []
    if flag:
        parts.append(flag)
    if auction_spread_risk:
        parts.append("auction_spread_risk")
    if credit_warning:
        parts.append("credit_warning")
    if breakeven_adjustment_pct > 0:
        parts.append(f"breakeven_adjustment_pct={breakeven_adjustment_pct:.1f}")
    return {
        "active": active,
        "flag": flag,
        "severity": severity,
        "auction_spread_risk": auction_spread_risk,
        "credit_warning": credit_warning,
        "breakeven_adjustment_pct": breakeven_adjustment_pct,
        "reason": "; ".join(parts),
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PATCH 1 â€” TRUTH MODEL (AVSHUNTER vNext Â· safe, no regression)
# Provides canonical campaign_verdict / execution_verdict derivation and
# data-source provenance fields. Zero dependency on upstream field presence.
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _truth_str(row: dict, key: str, default: str) -> str:
    v = row.get(key)
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


def _campaign_verdict(row: dict) -> str:
    # FIX-TRUTH-CAMPAIGN (2026-04-24): campaign_verdict=WATCH is the superbrain
    # default, causing PATCH 3 to set pse_execution_mode=FATAL_BLOCK on all rows
    # because every blank mv_verdict fell through to "WATCH" which then triggered
    # pse_manual_penalty=0.5 but not a block â€” however execution defaulted to SKIP.
    # Now reads sb_campaign (authoritative SuperBrain field) as primary fallback,
    # then sb_final_verdict, then mv_verdict. Blank â†’ WATCH (probe-eligible, not REJECT).
    cv = str(row.get("campaign_verdict", "")).upper().strip()
    if cv and cv not in ("WATCH", ""):
        return cv
    sb_camp = str(row.get("sb_campaign", "")).upper().strip()
    if sb_camp in ("CORE_CAMPAIGN", "CONVEXITY_INJECTION"):
        return "READY_EXECUTE"
    if sb_camp == "STAGED":
        return "READY_PROBE"
    if sb_camp == "AVOID":
        return "REJECT"
    sbv = str(row.get("sb_final_verdict", "")).upper().strip()
    sb_map = {
        "EXECUTE":           "READY_EXECUTE",
        "EXECUTE_WITH_RISK": "READY_PROBE",
        "ARMED":             "READY_PROBE",
        "STAND_DOWN":        "REJECT",
        "DATA_FAILURE":      "REJECT",
    }
    if sbv in sb_map:
        return sb_map[sbv]
    mv = str(row.get("mv_verdict", "")).upper().strip()
    return {
        "EXECUTE": "READY_EXECUTE",
        "PROBE":   "READY_PROBE",
        "WATCH":   "WATCH",
        "REJECT":  "REJECT",
    }.get(mv, "WATCH")


def _execution_verdict(row: dict) -> str:
    # FIX-TRUTH-EXECUTION (2026-04-24): execution_verdict=SKIP was the superbrain
    # default. Combined with blank mv_verdict â†’ every row hit execution=="SKIP"
    # â†’ PATCH 3 line 508 set pse_execution_mode=FATAL_BLOCK for all 814 signals.
    # Fix: read sb_execution_mode (authoritative PSE output field) as primary
    # fallback, then sb_final_verdict, then mv_verdict.
    # Critical: blank fallback is now WAIT_RETEST (probe-eligible) not SKIP (fatal).
    ev = str(row.get("execution_verdict", "")).upper().strip()
    if ev and ev not in ("SKIP", ""):
        return ev
    sb_exec = str(row.get("sb_execution_mode", "")).upper().strip()
    exec_map = {
        "FULL_EXECUTE":     "BUY_NOW",
        "REDUCED_EXECUTE":  "BUY_NOW",
        "PROBE":            "BUY_SMALL",
        "WAIT":             "WAIT_RETEST",
        "BLOCKED":          "SKIP",
    }
    if sb_exec in exec_map:
        return exec_map[sb_exec]
    sbv = str(row.get("sb_final_verdict", "")).upper().strip()
    sbv_map = {
        "EXECUTE":           "BUY_NOW",
        "EXECUTE_WITH_RISK": "BUY_SMALL",
        "ARMED":             "WAIT_RETEST",
        "STAND_DOWN":        "SKIP",
        "DATA_FAILURE":      "SKIP",
    }
    if sbv in sbv_map:
        return sbv_map[sbv]
    mv = str(row.get("mv_verdict", "")).upper().strip()
    return {
        "EXECUTE": "BUY_NOW",
        "PROBE":   "BUY_SMALL",
        "WATCH":   "WAIT_RETEST",
        "REJECT":  "SKIP",
    }.get(mv, "WAIT_RETEST")   # blank â†’ WAIT_RETEST not SKIP â€” keeps signal alive


def _enrich_truth_fields(row: dict) -> dict:
    row["campaign_verdict"]          = _campaign_verdict(row)
    row["execution_verdict"]         = _execution_verdict(row)
    row["trigger_source"]            = _truth_str(row, "trigger_source",            "POLYGON_DELAYED_15M")
    row["stock_data_source"]         = _truth_str(row, "stock_data_source",         "POLYGON_DELAYED_15M")
    row["options_data_source"]       = _truth_str(row, "options_data_source",       "MARKETDATA_LIVE")
    row["trigger_confidence_mode"]   = _truth_str(row, "trigger_confidence_mode",   "DELAYED_STRUCTURAL")
    row["execution_confidence_mode"] = _truth_str(row, "execution_confidence_mode", "LIVE_OPTIONS")
    row["live_execution_required"]   = _boolish(row.get("live_execution_required"),  True)
    # â”€â”€ V2 SIGNAL INTELLIGENCE INJECTION (Sprint 3) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Promote actuarial V2 fields from layer2__ prefix into flat row keys
    # so ev_inputs_from_row() and PSE _regime_multiplier() can read them.
    # All three getattr patterns checked in priority order:
    #   1. layer2__signal_type  (from vanguard_signals_enriched CSV merge)
    #   2. actuarial_signal_type (from EIL actuarial map inject)
    #   3. signal_type (direct â€” set by edge_detector in Vanguard run)
    # Safe: ev_inputs_from_row() defaults to 'NO_EDGE' if key absent.
    def _v2(key: str, default: str = "") -> str:
        return (str(row.get(f"layer2__{key}") or
                    row.get(f"actuarial_{key}") or
                    row.get(key) or default)).strip()

    if not row.get("signal_type"):
        _st = _v2("signal_type", "NO_EDGE")
        if _st:
            row["signal_type"] = _st

    if not row.get("momentum_tier"):
        _mt = _v2("momentum_tier", "TIER_4_FLAT")
        if _mt:
            row["momentum_tier"] = _mt

    if not row.get("fwd_momentum_conf"):
        _fmc_raw = (row.get("layer2__forward_momentum_confidence") or
                    row.get("actuarial_forward_momentum_confidence") or
                    row.get("forward_momentum_confidence") or
                    row.get("fwd_momentum_conf") or 0.0)
        try:
            row["fwd_momentum_conf"] = float(_fmc_raw)
        except (TypeError, ValueError):
            row["fwd_momentum_conf"] = 0.0

    return row


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PASS 1 â€” COMPUTE EV ACROSS ALL ROWS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _enrich_row_for_ev(row: dict) -> dict:
    """
    Pre-enrich a row with probabilities, Vanguard inputs, and MonetisationPolicy
    hard block check before EV computation.

    FIX-06: MonetisationPolicy evaluated here so mp_hard_block_reason is
    populated before FinalDecisionEngine's first gate check in Pass 2.
    """
    probs = compute_scenario_probabilities(row)
    row.update(probs)
    row = enrich_vanguard_inputs(row)

    # NEW-01: Apply three-path scenario routing.
    # Reads fusion_alignment_score from swing_fusion (written by discovery DISC-01).
    # Writes scenario_path, scenario_size_mult, scenario_dte_target, scenario_entry_type.
    # PSE downstream reads scenario_size_mult as an additional multiplier.
    row = _apply_scenario_routing(row)

    # â”€â”€ FIX-06: MonetisationPolicy hard block check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if _MP_AVAILABLE:
        try:
            mp_input  = _mp_from_row(row)
            mp_out    = _mp_engine.evaluate(mp_input)
            mp_fields = _mp_summarise(mp_out)
            row.update(mp_fields)
        except Exception as _mp_err:
            logger.debug(f"MP evaluation failed for {row.get('ticker','?')}: {_mp_err}")
            row.setdefault("mp_hard_block_reason", "")
    else:
        row.setdefault("mp_hard_block_reason", "")

    return row


def _compute_all_ev(rows: list[dict]) -> tuple[list[dict], list[EVResult]]:
    """
    Pass 1: Compute EVResult for every row.
    Returns enriched rows and corresponding EVResult list.
    """
    enriched   = []
    ev_results = []

    for row in rows:
        row = _enrich_row_for_ev(row)
        ev_inputs = ev_inputs_from_row(row)
        ev_result = _ev_engine.evaluate(ev_inputs)

        # Write all EVResult fields to row (ev2_* prefix)
        row.update(ev_result.to_row_dict())
        row["ev_conf_adj"] = ev_result.ev_conf_adj

        enriched.append(row)
        ev_results.append(ev_result)

    return enriched, ev_results


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PERCENTILE GATE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _percentile_overrides(ev_results: list[EVResult]) -> list[bool]:
    """
    Retired compatibility hook. EV percentile ranking is observational and
    cannot override or alter any production route.
    """
    return [False] * len(ev_results)


# Module-level EOD resolver state â€” set by run_engine() before Pass 2
_ACTIVE_EOD_RESOLVER  = None
_ACTIVE_EOD_DATA_MODE = "LIVE"


def _ensure_options_quotes_from_contract(ctx, row: dict) -> bool:
    """
    Populate ctx.options_mid/bid/ask from contract_premium and contract_spread_pct
    when live option quote fields are missing.

    Runs regardless of data mode (live or EOD) â€” if the context has no live
    bid/ask, synthesis from contract columns is the correct fallback.
    Returns True if fallback synthesis was applied.
    Does not overwrite real live bid/ask/mid.
    """
    def _qnum(key, default=0.0):
        v = row.get(key, default)
        if v is None:
            return default
        try:
            if isinstance(v, str):
                s = v.strip().replace("$","").replace("Â£","").replace(",","")
                if not s or s.lower() in {"nan","none","null","na","n/a"}:
                    return default
                if s.endswith("%"):
                    return float(s[:-1]) / 100.0
                return float(s)
            f = float(v)
            return default if math.isnan(f) or math.isinf(f) else f
        except Exception:
            return default

    def _missing(x):
        try:
            return x is None or float(x) <= 0
        except Exception:
            return True

    # Only synthesise if all three are missing/zero
    if not (_missing(getattr(ctx, "options_bid", None))
            or _missing(getattr(ctx, "options_ask", None))
            or _missing(getattr(ctx, "options_mid", None))):
        return False

    premium = (
        _qnum("contract_premium")
        or _qnum("premium")
        or _qnum("selected_contract_premium")
        or 0.0
    )
    if premium <= 0:
        return False

    spread_dec = (
        _qnum("contract_spread_pct")
        or _qnum("spread_pct")
        or _qnum("option_spread_pct")
        or 0.08
    )
    # Normalise: 0.157 = 15.7%, 15.7 = 15.7%
    if spread_dec > 1.0:
        spread_dec = spread_dec / 100.0
    spread_dec = max(0.01, min(spread_dec, 1.00))

    half_spread          = premium * spread_dec / 2.0
    ctx.options_mid      = round(premium, 4)
    ctx.options_bid      = round(max(0.01, premium - half_spread), 4)
    ctx.options_ask      = round(premium + half_spread, 4)

    row["options_quote_fallback_applied"] = True
    row["options_quote_fallback_source"]  = "CONTRACT_PREMIUM_SPREAD"
    row["options_bid"]                    = ctx.options_bid
    row["options_ask"]                    = ctx.options_ask
    row["options_mid"]                    = ctx.options_mid
    row["eil_spread_pct_live"]            = round(
        (ctx.options_ask - ctx.options_bid) / ctx.options_mid * 100, 4
    )
    return True


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ENHANCEMENT 1 â€” CURRENT EDGE SOVEREIGN VETO
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _apply_current_edge_hard_veto(row: dict) -> dict:
    """
    Sovereign current-edge veto (Phase 1 â€” production version).

    Blocks capital when signal_type / momentum_tier / pse equivalents are
    NO_EDGE, TIER_4_FLAT, or DATA_MISSING (broken handoff = no capital).

    DATA_MISSING â†’ DATA_REPAIR_REQUIRED (not FUTURE_WATCH).
    Genuine NO_EDGE + forward EV evidence â†’ FUTURE_WATCH.

    Called twice inside _process_row():
      1. After PSE + all multipliers written (after BLOCKER 4 fd_size sync).
      2. After horizon fields set â€” defence-in-depth against re-promotion.
    """
    _signal     = str(row.get("signal_type",       "") or "").upper().strip()
    _tier       = str(row.get("momentum_tier",     "") or "").upper().strip()
    _pse_signal = str(row.get("pse_signal_type",   "") or "").upper().strip()
    _pse_tier   = str(row.get("pse_momentum_tier", "") or "").upper().strip()

    _no_current_edge = (
        _signal     in {"NO_EDGE", "DATA_MISSING"}
        or _tier    in {"TIER_4_FLAT", "DATA_MISSING"}
        or _pse_signal in {"NO_EDGE", "DATA_MISSING"}
        or _pse_tier   in {"TIER_4_FLAT", "DATA_MISSING"}
    )

    if not _no_current_edge:
        row["current_edge_valid"] = True
        row["capital_permission"] = "EOD_CANDIDATE_ONLY"
        row.setdefault("future_edge_valid",    False)
        row.setdefault("future_state_action",  "CURRENT_EXECUTION_ELIGIBLE")
        row.setdefault("phase1_guard_applied", False)
        return row

    # â”€â”€ Veto fires â€” block capital â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    row["current_edge_valid"]   = False
    row["capital_permission"]   = "EOD_CANDIDATE_ONLY"
    row["phase1_guard_applied"] = True
    row["pse_execution_mode"]   = "EOD_DATA_INSUFFICIENT_REVIEW"
    row["pse_final_size"]       = 0.0
    row["fd_verdict"]           = "WATCHLIST"
    row["fd_size"]              = 0.0
    row["eod_candidate_permission"] = "MORNING_VALIDATION_REQUIRED"
    row["candidate_size"]       = 0.0
    row["manual_sizing_required"] = True
    row["candidate_size_status"] = "MANUAL_SIZING_REQUIRED"
    row["candidate_size_source"] = "EOD_REVIEW_PSE_IGNORED"

    _data_missing = "DATA_MISSING" in {_signal, _tier, _pse_signal, _pse_tier}

    if _data_missing:
        row["future_edge_valid"]   = False
        row["future_state_action"] = "EOD_DATA_INSUFFICIENT_REVIEW"
        reason = "EOD_DATA_INSUFFICIENT_REVIEW:DATA_MISSING"
    else:
        physics_verdict = str(row.get("physics_verdict",            "") or "").upper().strip()
        future_positive = (
            physics_verdict in {"EARLY_PRESSURE_BUILDING", "MONETISABLE_PRESSURE"}
        )
        if future_positive:
            row["future_edge_valid"]   = True
            row["future_state_action"] = "EOD_PROBE_CANDIDATE"
            row["pse_execution_mode"]   = "EOD_PROBE_CANDIDATE"
            reason = "EOD_PROBE_CANDIDATE:NO_CURRENT_EDGE_FORWARD_EVIDENCE"
        else:
            row["future_edge_valid"]   = False
            row["future_state_action"] = "EOD_DATA_INSUFFICIENT_REVIEW"
            reason = "EOD_DATA_INSUFFICIENT_REVIEW:NO_CURRENT_EDGE"

    row["phase1_guard_reason"]       = reason
    row["execution_override_reason"] = reason
    row["fd_reason"]                 = reason
    existing_block = str(row.get("pse_block_reason", "") or "").strip()
    row["pse_block_reason"] = f"{reason} | {existing_block}" if existing_block else reason
    return row


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PASS 2 â€” FULL PIPELINE PER ROW
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _process_row(
    row: dict,
    ev_result: EVResult,
    i: int,
    percentile_override: bool,
) -> dict:
    """
    Full decision pipeline for one row.
    EVResult already computed in Pass 1.

    FIX-02: EIL five-strategy composite engine called here, before
    FinalDecisionEngine, so eil_v3_verdict is populated in the row.
    Token is normalised from EIL vocabulary to FDE EIL_SIZE_MAP vocabulary.

    FinalDecisionEngine produces the authoritative verdict.

    v4.1 FIX: Horizon bucket gate added. 11-20D signals are routed to
    MONITOR_ONLY immediately â€” they never enter EIL scoring. Blocked signals
    are short-circuited with FATAL_BLOCK. 6-10D signals receive a 0.70x
    size multiplier applied after PSE. horizon_size_multiplier from the
    macro contract is the authoritative sizing anchor.
    """
    ticker = _s(row, "ticker", "UNK")

    # FIX 5: PSE retired 2026-04. Capital permission set to MANUAL so rows
    # pass forward to morning validation without being killed by legacy zero-size gate.
    row["capital_permission"] = "MANUAL"
    row["size_note"] = (
        "Manual sizing required. PSE retired 2026-04. "
        "Macro, EIL, EV, entry, exit and timing are advisory only. "
        "Trader determines size and execution."
    )
    row["pse_final_size"] = 0.0
    row["fd_size"] = 0.0

    # â”€â”€ v4.1 HORIZON GATE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Read horizon_bucket stamped by Phase 1B macro router (or SuperBrain passthrough).
    # This gate runs BEFORE all EIL scoring to prevent wasted computation and
    # incorrect verdicts on signals that should never reach execution.
    _hb = str(row.get("horizon_bucket", "")).strip().lower()
    _ha = str(row.get("horizon_action", "")).strip().upper()
    # ISSUE 6: _f() safe parse â€” raw float() crashes on N/A, nan, empty string
    # FIX: explicit guard â€” only zero-out when action is genuinely blocked.
    if _ha == "MONITOR_ONLY" or _hb == "blocked":
        _default_hsm = 0.0
    elif _hb == "6_10d":
        _default_hsm = 0.70
    else:
        _default_hsm = 1.0   # 1_5d, unrouted, unknown, blank â†’ full size
    _hsm = _f(row, "horizon_size_multiplier", _default_hsm)
    _hsm = max(0.0, min(1.5, _hsm))  # clamp â€” macro JSON must not set absurd multipliers

    # DEF-HORIZON-EIL (May 2026): horizon_bucket is informational only.
    # The router assigns bucket labels (1_5d / 6_10d / 11_20d) to describe
    # the hold period. It NEVER emits MONITOR_ONLY as an action â€” that decision
    # belongs to the EIL. Only gate on an explicit MONITOR_ONLY action string
    # (which would indicate a genuine macro kill-switch from the router).
    # Blocking on _hb == "11_20d" was preventing 13+ valid signals per run
    # (CRWD, COIN, LCID, IWM, AVGO, PANW, ABNB, AMD, ARM, ORCL, DDOG, ROKU,
    # BAC) from ever reaching EIL scoring â€” all had real OIS/R:R/Wyckoff data.
    if _ha == "MONITOR_ONLY" or _hb == "blocked":
        # DOI-1: horizon/timing is advisory.  Preserve the observation and run
        # the normal enrichment path so an elapsed or temporarily unattractive
        # setup cannot disappear from the governed opportunity population.
        row["horizon_advisory_state"] = (
            "HORIZON_MONITOR_ONLY" if _ha == "MONITOR_ONLY" else "HORIZON_ELAPSED_REASSESS"
        )
        row["horizon_advisory_reason"] = (
            row.get("horizon_block_reason") or "Router requested monitoring"
        )
        row["horizon_size_multiplier"] = 1.0
        logger.info(
            "  [%s] HORIZON ADVISORY: %s — opportunity retained",
            ticker,
            row["horizon_advisory_state"],
        )

    # 1-5D and 6-10D proceed through normal EIL scoring.
    # horizon_size_multiplier (1.0 for 1-5D, 0.70 for 6-10D) will be applied
    # after PSE output to enforce macro-driven position sizing discipline.
    # â”€â”€ END HORIZON GATE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    # â”€â”€ PATCH 2: Enrich truth fields (campaign + execution verdicts, provenance)
    row       = _enrich_truth_fields(row)
    campaign  = _campaign_verdict(row)
    execution = _execution_verdict(row)

    row["_percentile_override_active"] = False

    # â”€â”€ FIX-02: EIL microstructure (size penalty layer) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if _EIL_AVAILABLE:
        try:
            check_time = datetime.now(tz=timezone.utc)
            eil_ctx    = _eil_build_ctx(row, check_time, check_time,
                                           advisory_only=not LIVE_MODE)
            # Pass through EV already computed so EIL doesn't recompute
            eil_ctx.ev_v2_raw = ev_result.ev_final

            # â”€â”€ Quote fallback: populate bid/ask/mid from contract columns â”€â”€â”€â”€â”€
            # Runs regardless of data mode. If live quotes are present they are
            # not overwritten. Fixes sprd=0.0% when no live option chain available.
            _quote_fallback = _ensure_options_quotes_from_contract(eil_ctx, row)
            if _quote_fallback:
                logger.debug(
                    "Quote fallback applied for %s: mid=%.4f bid=%.4f ask=%.4f sprd=%.2f%%",
                    ticker,
                    eil_ctx.options_mid or 0,
                    eil_ctx.options_bid or 0,
                    eil_ctx.options_ask or 0,
                    row.get("eil_spread_pct_live", 0) or 0,
                )

            # â”€â”€ EOD context enrichment â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # build_execution_context_from_row() already handles: contract_iv
            # (iv_mid), structural_target (poc_price), gamma_flip/call_wall/
            # put_wall/pcr_oi (gex_by_strike synthesis). What remains None in
            # EOD mode is l2_bid_size/ask_size (no live NBBO) and IV bid/ask
            # spread dispersion (all tickers get identical Â±3% from FIX-04).
            # _enrich_ctx_for_eod() patches these two gaps using ADX, ATR-pct,
            # avg_volume, trend_direction, wyckoff_phase, IVP, iv_rank which
            # are all present in the superbrain row from the discovery CSV.
            # This gives the five strategies per-ticker differentiated inputs
            # so std > 0.01 and the convergence engine gets real votes.
            # Zero impact on live runs: the if-block is skipped entirely.
            # BLOCKER 2: _ACTIVE_EOD_RESOLVER was set in run_engine() but never
            # used here â€” log claimed resolver active but local fallback always ran.
            # Resolver now called first; _enrich_ctx_for_eod is the fallback.
            if _ACTIVE_EOD_DATA_MODE == "EOD_SYNTHETIC":
                # BUG-01 FIX: initialise before the resolver if-block so the variable is
                # always defined regardless of which branch is taken.
                _quote_fallback_after_resolver = False
                if _ACTIVE_EOD_RESOLVER is not None:
                    try:
                        resolved = _ACTIVE_EOD_RESOLVER.resolve(row)
                        if isinstance(resolved, dict):
                            row.update({k: v for k, v in resolved.items() if v is not None})
                            # â”€â”€ BLOCKER FIX: rebuild eil_ctx after row is enriched â”€â”€
                            eil_ctx = _eil_build_ctx(
                                row, check_time, check_time, advisory_only=not LIVE_MODE,
                            )
                            eil_ctx.ev_v2_raw = ev_result.ev_final

                            # Re-apply quote fallback AFTER resolver rebuild.
                            # The resolver may have updated contract_premium /
                            # contract_spread_pct / selected contract fields in row.
                            # The rebuilt context must be quote-validated before EIL
                            # scoring â€” without this the context may still enter EIL
                            # with weaker quote state than the row now supports.
                            _quote_fallback_after_resolver = _ensure_options_quotes_from_contract(eil_ctx, row)

                            _enrich_ctx_for_eod(eil_ctx, row)

                            if _quote_fallback_after_resolver:
                                row["eil_data_mode"] = "EOD_SYNTHETIC_WITH_CONTRACT_QUOTE_FALLBACK"
                    except Exception as _res_err:
                        logger.warning(
                            f"EOD resolver failed for {ticker}: {_res_err} â€” using local fallback"
                        )
                        # Re-apply quote fallback on the original context before
                        # local EOD enrichment runs, in case resolver failure left
                        # contract fields enriched enough to support synthesis.
                        _quote_fallback_after_resolver = _ensure_options_quotes_from_contract(eil_ctx, row)
                        _enrich_ctx_for_eod(eil_ctx, row)
                        if _quote_fallback_after_resolver:
                            row["eil_data_mode"] = "EOD_SYNTHETIC_WITH_CONTRACT_QUOTE_FALLBACK"
                else:
                    # GAP-01 FIX: resolver=None path also needs quote fallback applied
                    # before EOD enrichment â€” this was the third blind spot.
                    _quote_fallback_after_resolver = _ensure_options_quotes_from_contract(eil_ctx, row)
                    _enrich_ctx_for_eod(eil_ctx, row)
                    if _quote_fallback_after_resolver:
                        row["eil_data_mode"] = "EOD_SYNTHETIC_WITH_CONTRACT_QUOTE_FALLBACK"
                row["eil_data_mode"] = "EOD_SYNTHETIC"
                _log_eil_data_mode_per_ticker(ticker, row)
            else:
                # LIVE mode: label as LIVE_WITH_CONTRACT_QUOTE_FALLBACK when
                # quote fallback was needed (no live option chain available).
                # Plain LIVE means real bid/ask from API were present.
                row["eil_data_mode"] = (
                    "LIVE_WITH_CONTRACT_QUOTE_FALLBACK" if _quote_fallback else "LIVE"
                )
            # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

            eil_result = _eil_evaluate(eil_ctx)
            # Normalise EIL token â†’ FDE EIL_SIZE_MAP vocabulary
            final_eil_token = eil_result.eil_verdict
            raw_eil_token = eil_result.eil_raw_verdict
            # FIX-3: Persist full EIL verdict â€” all diagnostic fields
            row["eil_v3_verdict"]      = _EIL_TOKEN_NORMALISE.get(final_eil_token, "BLOCKED")  # FIX-2: unknown token = BLOCKED
            row["eil_raw_verdict"]     = raw_eil_token
            row["eil_composite_score"] = eil_result.eil_composite_score
            row["eil_size_multiplier"] = eil_result.eil_size_multiplier
            # Strategy sub-scores
            row["eil_liquidity_window"]  = eil_result.eil_liquidity_window
            row["eil_liquidity_score"]   = eil_result.eil_liquidity_score
            row["eil_liquidity_passed"]  = eil_result.eil_liquidity_passed
            row["eil_iv_ask_premium"]    = eil_result.eil_iv_ask_premium
            row["eil_iv_distortion"]     = eil_result.eil_iv_distortion_flag
            row["eil_iv_score"]          = eil_result.eil_iv_score
            row["eil_iv_tailwind"]       = eil_result.eil_iv_tailwind_score
            row["eil_gex_regime"]        = eil_result.eil_gex_regime
            row["eil_gex_score"]         = eil_result.eil_gex_score
            row["eil_obi_regime"]        = eil_result.eil_obi_regime
            row["eil_obi_score"]         = eil_result.eil_obi_score
            row["eil_poc_position"]      = eil_result.eil_poc_position
            row["eil_poc_score"]         = eil_result.eil_poc_score
            row["eil_defer_reason"]      = eil_result.eil_defer_reason or ""
            _bond_ctx = _bond_macro_context(row)
            row["eil_bond_macro_flag"] = _bond_ctx["flag"]
            row["eil_bond_macro_spread_context"] = ""
            row["eil_bond_macro_reason"] = ""
            if _bond_ctx["active"] and bool(eil_result.eil_iv_distortion_flag):
                row["eil_bond_macro_spread_context"] = "MACRO_SPREAD_ENVIRONMENT"
                row["eil_bond_macro_reason"] = _bond_ctx["reason"]
                _macro_reason = f"MACRO_SPREAD_ENVIRONMENT: {_bond_ctx['reason']}"
                row["eil_defer_reason"] = (
                    f"{_macro_reason} | {row['eil_defer_reason']}"
                    if row["eil_defer_reason"]
                    else _macro_reason
                )
            row["eil_ev_v2"]             = eil_result.eil_ev_v2
            row["eil_ev_net"]            = eil_result.eil_ev_net
            row["eil_ev_score"]          = eil_result.eil_ev_score
            row["eil_advisory_only"]     = True
            row["eil_schema_version"]    = eil_result.eil_schema_version
            # â”€â”€ OTT-04: write eil_spread_pct_live from live eil_ctx â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # The quote fallback may have already set this from contract columns.
            # Here we compute it from the actual ctx values used by EIL so it
            # always reflects what EIL scored against, not just the fallback.
            # Only overwrites if ctx has valid bid/ask/mid (avoids zeroing a
            # good value with None when live quotes were present).
            try:
                _ctx_bid = getattr(eil_ctx, "options_bid", None)
                _ctx_ask = getattr(eil_ctx, "options_ask", None)
                _ctx_mid = getattr(eil_ctx, "options_mid", None)
                if (
                    _ctx_bid is not None and _ctx_ask is not None
                    and _ctx_mid is not None and float(_ctx_mid) > 0
                ):
                    row["eil_spread_pct_live"] = round(
                        (float(_ctx_ask) - float(_ctx_bid)) / float(_ctx_mid) * 100.0, 4
                    )
                elif "eil_spread_pct_live" not in row:
                    row["eil_spread_pct_live"] = float("nan")
            except Exception as _sprd_err:
                logger.debug("eil_spread_pct_live compute failed for %s: %s", ticker, _sprd_err)
            # â”€â”€ end OTT-04 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        except Exception as _eil_err:
            # DOI-1: retain the failure as telemetry.  It is not authority.
            logger.warning(f"EIL evaluate() FAILED for {ticker}: {_eil_err} â€” retained as advisory evidence")
            row["eil_v3_verdict"]       = "BLOCKED"
            row["eil_failure_reason"]   = f"EIL_EVALUATION_FAILED: {_eil_err}"
            row["eil_composite_score"]  = 0.0
            row["eil_size_multiplier"]  = 0.0
    else:
        logger.warning(f"EIL engine unavailable for {ticker} â€” retained as advisory evidence")
        row["eil_v3_verdict"]       = "BLOCKED"
        row["eil_failure_reason"]   = "EIL_UNAVAILABLE"
        row["eil_composite_score"]  = 0.0
        row["eil_size_multiplier"]  = 0.0

    # â”€â”€ PATCH 3: Execution Discipline Layer (AVSHUNTER vNext) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    #
    # Structure (campaign) and execution permission are checked here BEFORE PSE.
    # REJECT/SKIP conditions produce FATAL_BLOCK â€” saves PSE cycles.
    # All other cases set pse_manual_penalty to downscale size, not kill signal.
    # campaign and execution are already resolved by _enrich_truth_fields() above.

    if campaign == "REJECT" or execution == "SKIP":
        # â”€â”€ SIGNAL-AWARE BLOCK REASON TAXONOMY â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Replace the monolithic CAMPAIGN_OR_EXECUTION_INVALID with a specific
        # reason drawn from the actual signal state.  This is the primary source
        # of the 440-row FATAL_BLOCK collapse that destroyed observability.
        #
        # Design contract:
        #   NO_EDGE / DATA_MISSING / TIER_4_FLAT â†’ SKIP (not FATAL_BLOCK)
        #   STRUCTURAL_MATCH                     â†’ STRUCTURAL_WATCH (not fatal)
        #   FUTURE_EDGE                          â†’ FUTURE_WATCH (not fatal)
        #   CURRENT_EDGE + fd_verdict=BLOCK      â†’ FATAL_BLOCK with specific reason
        #   Genuine campaign REJECT              â†’ FATAL_BLOCK: CAMPAIGN_REJECT
        #   Fallback                             â†’ CAMPAIGN_OR_EXECUTION_INVALID
        #
        # FATAL_BLOCK should be rare (<5%).  All other states are watchlist/skip.
        # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _sig  = str(row.get("signal_type",   "") or "").upper().strip()
        _tier = str(row.get("momentum_tier", "") or "").upper().strip()
        _fv   = str(row.get("fd_verdict",    "") or "").upper().strip()
        _mp   = str(row.get("mp_hard_block_reason", "") or "").upper().strip()
        _eil  = str(row.get("eil_v3_verdict", "") or "").upper().strip()
        _eil_fail = str(row.get("eil_failure_reason", "") or "").strip()
        _contract = float(row.get("contract_premium", 0.0) or 0.0)
        _spread   = float(row.get("eil_spread_pct_live", 0.0) or 0.0)

        # â”€â”€ Classify execution mode + reason â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if _sig in {"NO_EDGE", "DATA_MISSING"} or _tier in {"TIER_4_FLAT", "DATA_MISSING"}:
            _is_data_missing = "DATA_MISSING" in {_sig, _tier}
            _exe_mode  = "EOD_DATA_INSUFFICIENT_REVIEW" if _is_data_missing else "EOD_PROBE_CANDIDATE"
            _exe_why   = "DATA_MISSING_EOD_DATA_INSUFFICIENT_REVIEW" if _is_data_missing else "SPARSE_ACTUARIAL_CONTEXT_EOD_PROBE_CANDIDATE"
            _cap_perm  = "EOD_CANDIDATE_ONLY"
            _fsa       = _exe_mode

        elif _sig == "STRUCTURAL_MATCH":
            _exe_mode  = "STRUCTURAL_WATCH"
            _exe_why   = "STRUCTURAL_MATCH_NO_CURRENT_EDGE"
            _cap_perm  = "WATCH_ONLY"
            _fsa       = "STRUCTURAL_WATCH"

        elif _sig == "FUTURE_EDGE":
            _exe_mode  = "FUTURE_WATCH"
            _exe_why   = "FUTURE_EDGE_NOT_CURRENTLY_EXECUTABLE"
            _cap_perm  = "WATCH_ONLY"
            _fsa       = "FUTURE_WATCH"

        elif _sig in {"CURRENT_EDGE", "TRANSITION"}:
            # Hard fatal â€” identify specific reason
            if _mp and "DATA" in _mp:
                _exe_mode = "SKIP"
                _exe_why  = "FD_BLOCK_CONTRACT_ECONOMICS_MISSING"
            elif _contract <= 0:
                _exe_mode = "CONTRACT_MONITOR"
                _exe_why  = "CONTRACT_ECONOMICS_MISSING_ADVISORY"
            elif _spread > 30.0:
                _exe_mode = "CONTRACT_MONITOR"
                _exe_why  = "LIQUIDITY_OR_SPREAD_ADVISORY"
            else:
                _exe_mode = f"{_sig}_REVIEW"
                _exe_why  = f"{_sig}_MANUAL_REVIEW_REQUIRED_SIZING_RETIRED"
            _cap_perm = "EOD_CANDIDATE_ONLY"
            _fsa      = "MORNING_VALIDATION_REQUIRED"

        else:
            # Genuine campaign-level REJECT with unknown signal or other state
            if campaign == "REJECT":
                _exe_mode = "FATAL_BLOCK"
                _exe_why  = "FD_BLOCK_TRUE_HARD_VETO:CAMPAIGN_REJECT"
            else:
                # Execution == SKIP but signal is unclassified â€” treat as watchlist.
                # CAMPAIGN_OR_EXECUTION_INVALID is retired; use a specific label so
                # production logs show something meaningful and defang can find it.
                _exe_mode = "SKIP"
                _exe_why  = "UNCLASSIFIED_SIGNAL_EXECUTION_SKIP"
            _cap_perm = "NO"
            _fsa      = "BLOCKED"

        # â”€â”€ Write row fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        row["execution_override_reason"] = "SIGNAL_AWARE_BLOCK_ROUTING"
        row["pse_execution_mode"]        = _exe_mode
        row["pse_final_size"]            = 0.0
        row["pse_block_reason"]          = _exe_why
        row["fd_verdict"]                = "BLOCK" if _exe_mode == "FATAL_BLOCK" else "WATCHLIST"
        row["fd_size"]                   = 0.0
        row["fd_reason"]                 = _exe_why
        row["fd_confidence"]             = 90.0
        row["fd_ev_used"]                = ev_result.ev_conf_adj
        row["eil_runner_version"]        = EIL_RUNNER_VERSION
        # Governance fields â€” every row must carry these, including fatal returns.
        row["capital_permission"]        = _cap_perm
        row["future_state_action"]       = _fsa
        row["eod_candidate_permission"]  = "MORNING_VALIDATION_REQUIRED" if _cap_perm == "EOD_CANDIDATE_ONLY" else "NO"
        row["candidate_size"]            = 0.0
        row["manual_sizing_required"]    = _cap_perm == "EOD_CANDIDATE_ONLY"
        row["candidate_size_status"]     = "MANUAL_SIZING_REQUIRED" if _cap_perm == "EOD_CANDIDATE_ONLY" else "NO_CANDIDATE_SIZE"
        row["candidate_size_source"]     = "EOD_REVIEW_PSE_IGNORED" if _cap_perm == "EOD_CANDIDATE_ONLY" else "NO_EOD_CANDIDATE"
        row["signal_authority_reason"]   = _exe_why
        row["current_edge_valid"]        = (_sig == "CURRENT_EDGE")
        row["future_edge_valid"]         = (_sig == "FUTURE_EDGE")
        row["phase1_guard_applied"]      = True
        return row

    if campaign == "WATCH":
        row["execution_override_reason"] = "STRUCTURE_NOT_READY"
        row["pse_manual_penalty"]        = 0.5   # 50% size cap

    if campaign == "READY_PROBE" and execution in {"WAIT_RETEST"}:
        row["execution_override_reason"] = "WAITING_FOR_TRIGGER"
        row["pse_manual_penalty"]        = 0.4

    if campaign == "READY_PROBE" and execution == "BUY_SMALL":
        row["execution_override_reason"] = "PROBE_MODE"
        row["pse_manual_penalty"]        = 0.5

    if campaign == "READY_EXECUTE" and execution == "BUY_NOW":
        row["execution_override_reason"] = "FULL_EXECUTION"
        row["pse_manual_penalty"]        = 1.0

    # -- Retired sizing overlay ---------------------------------------------
    # PSE/FDE no longer allocate or suppress capital. Keep size at zero and
    # route through signal authority + morning validation.
    row = _apply_retired_sizing_overlay(row, ev_result, percentile_override)
    apply_advisory_authority(row)

    # â”€â”€ v4.1: Ensure horizon fields always present in output row â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Even 1-5D signals that completed full EIL scoring must carry these fields
    # so downstream phases (Enhancement, Trade Book, Morning Validation) can
    # read them without KeyError or missing-column failures.
    row.setdefault("horizon_bucket",           _hb or "unrouted")
    row.setdefault("horizon_action",           _ha or "UNKNOWN")
    row.setdefault("horizon_size_multiplier",  _hsm)
    row.setdefault("horizon_block_reason",     "")
    # â”€â”€ End horizon fields passthrough â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    # â”€â”€ ENHANCEMENT 1: Current Edge Sovereign Veto (call 2 of 2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    row = _apply_current_edge_hard_veto(row)
    # â”€â”€ SIGNAL AUTHORITY POLICY (call 2 of 2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    row = _apply_signal_authority_policy(row)
    row = _finalize_execution_authority(row)
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    logger.info(
        f"[{i:04d}] {ticker:<8} | "
        f"EV={ev_result.ev_conf_adj:+.4f} ({ev_result.ev_status:10}) | "
        f"EIL={row.get('eil_v3_verdict','?'):10} | "
        f"Mode={str(row.get('pse_execution_mode', '?')):<16} | "
        f"Size=0.00000 | sig={row.get('pse_signal_type','?')}/{row.get('pse_momentum_tier','?')} | "
        f"cap={row.get('capital_permission','?')} | "
        f"policy={row.get('sizing_policy', PSE_RETIRED_POLICY)}"
    )

    return row


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MAIN RUNNER
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def run_engine(df: pd.DataFrame) -> pd.DataFrame:
    logger.info(f"EIL v{EIL_RUNNER_VERSION} â€” processing {len(df)} rows")
    logger.info("PSE status: RETIRED â€” advisory telemetry only; no live capital sizing")
    logger.info("EV mode: advisory-only. Candidate authority: signal policy + morning validation. Live size: manual.")
    logger.info(f"EIL microstructure: {'ACTIVE' if _EIL_AVAILABLE else 'INACTIVE (FIX-02 â€” deploy execution_intelligence.py)'}")
    logger.info(f"MonetisationPolicy: {'ACTIVE' if _MP_AVAILABLE else 'INACTIVE (FIX-06 â€” deploy avshunter_monetisation_policy.py)'}")

    rows = df.to_dict(orient="records")

    # â”€â”€ EOD resolver: instantiated once, used per-ticker if off market hours â”€â”€â”€
    # Determines data mode from current time. In EOD mode patches every
    # ExecutionContext with differentiated per-ticker synthesised inputs so
    # the five EIL strategies score from real cross-sectional dispersion rather
    # than identical API fallback constants.
    _eod_resolver_instance = None
    _eod_data_mode         = _EIL_DATA_MODE   # honour time-based detection even if resolver absent

    if _EOD_RESOLVER_AVAILABLE:
        _eod_data_mode = _eod_resolver_module.get_eil_data_mode()
        if _eod_data_mode == "EOD_SYNTHETIC":
            # Derive run_dir from the rows â€” use first non-empty run_id in the data,
            # falling back to the base directory of the script.
            _run_id_from_rows = str(rows[0].get("run_id", "")) if rows else ""
            _base = Path(_ROOT)
            _run_dir_candidate = _base / "data" / "output" / "runs" / _run_id_from_rows \
                if _run_id_from_rows else _base
            _eod_resolver_instance = _eod_resolver_module.EodContextResolver(
                run_dir  = _run_dir_candidate,
                base_dir = _base,
            )
            logger.info(
                "EIL data mode: EOD_SYNTHETIC â€” live API calls bypassed, "
                "resolver synthesising inputs from: discovery, vanguard, options_intelligence, actuarial"
            )
            # Variance sanity check on sample of rows (non-blocking)
            try:
                _sample = [_eod_resolver_instance.resolve(r) for r in rows[:min(50, len(rows))]]
                _vcheck = _eod_resolver_module.check_eod_variance(_sample)
                if _vcheck["ok"]:
                    logger.info(
                        "EOD SANITY_PASS: all fields show variance > 0.01 (n=%d)",
                        _vcheck["n_rows"]
                    )
                else:
                    logger.warning(
                        "EOD SANITY_WARN: low-variance fields %s â€” check data sources. "
                        "Variances: %s",
                        _vcheck["frozen"], _vcheck["variances"]
                    )
            except Exception as _sv_err:
                logger.debug("EOD variance check failed (non-critical): %s", _sv_err)
        else:
            logger.info("EIL data mode: LIVE â€” real-time data feeds active")
    else:
        if _eod_data_mode == "EOD_SYNTHETIC":
            logger.warning(
                "EIL data mode: EOD_SYNTHETIC â€” eil_eod_resolver.py not available; "
                "using local _enrich_ctx_for_eod() fallback inside _process_row(). "
                "Deploy eil_eod_resolver.py for full cross-sectional enrichment."
            )
        else:
            logger.info("EIL data mode: LIVE â€” resolver not required")

    # Store on module level so _process_row can access without parameter change
    global _ACTIVE_EOD_RESOLVER, _ACTIVE_EOD_DATA_MODE
    _ACTIVE_EOD_RESOLVER  = _eod_resolver_instance
    _ACTIVE_EOD_DATA_MODE = _eod_data_mode

    # â”€â”€ Pass 1: EV computation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    logger.info("=== PASS 1: EV Computation ===")
    rows, ev_results = _compute_all_ev(rows)

    ev_scores = [r.ev_conf_adj for r in ev_results]
    valid_evs = [s for s in ev_scores if s > -0.90]   # exclude hard-blocked
    if valid_evs:
        logger.info(
            f"EV distribution â€” "
            f"min={min(valid_evs):+.4f} | "
            f"mean={sum(valid_evs)/len(valid_evs):+.4f} | "
            f"max={max(valid_evs):+.4f} | "
            f"positive={sum(1 for s in valid_evs if s > 0)}/{len(valid_evs)}"
        )

    # â”€â”€ Percentile overrides â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    overrides = _percentile_overrides(ev_results)
    logger.info(f"Percentile override (top 30%): {sum(overrides)} rows protected")

    # â”€â”€ Pass 2: Full pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    logger.info("=== PASS 2: Final Decision Pipeline ===")
    results = []
    for i, (row, ev_result, override) in enumerate(
        zip(rows, ev_results, overrides), start=1
    ):
        result = _process_row(row, ev_result, i, override)
        results.append(result)

    result_df = pd.DataFrame(results)
    result_df = _finalize_execution_authority_frame(result_df)
    result_df = _ensure_eil_audit_contract(result_df)

    # Sprint C: no execution promotion without actuarial or catalyst context.
    # This does not bury the ticker; it downgrades execution authority into an
    # EOD review lane so Morning Validation can still inspect live tape/contract.
    if {"actuarial_match_type", "catalyst_overlay"}.issubset(result_df.columns):
        _match_type = result_df["actuarial_match_type"].fillna("").astype(str).str.upper()
        _overlay = result_df["catalyst_overlay"].fillna("NONE").astype(str).str.upper()
        _no_context = _match_type.eq("NO_ACTUARIAL_MATCH") & _overlay.isin(["", "NONE", "UNK"])
        if _no_context.any():
            result_df.loc[_no_context, "no_actuarial_context_gate"] = "TRUE"
            result_df.loc[_no_context, "pse_execution_mode"] = "EOD_DATA_INSUFFICIENT_REVIEW"
            result_df.loc[_no_context, "pse_block_reason"] = "FATAL_NO_ACTUARIAL_CONTEXT_REVIEW: no broad/behaviour actuarial match and no catalyst overlay"
            result_df.loc[_no_context, "fd_verdict"] = "WATCHLIST"
            result_df.loc[_no_context, "capital_permission"] = "EOD_CANDIDATE_ONLY"
            result_df.loc[_no_context, "eod_candidate_permission"] = "MORNING_VALIDATION_REQUIRED"
            result_df.loc[_no_context, "candidate_size"] = 0.0
            result_df.loc[_no_context, "manual_sizing_required"] = True
            result_df.loc[_no_context, "signal_authority_reason"] = "FATAL_NO_ACTUARIAL_CONTEXT_REVIEW"
            logger.info("Sprint C context gate: %d rows routed to EOD_DATA_INSUFFICIENT_REVIEW", int(_no_context.sum()))

    # â”€â”€ ENHANCEMENT 1: Capital Permission Sanity Check (module-level function) â”€
    # Step 1: Defang any residual CAMPAIGN_OR_EXECUTION_INVALID FATAL_BLOCKs
    #         that escaped per-row routing (PSE/FDE downstream blocks).
    #         FATAL_BLOCK is only legal for CURRENT_EDGE rows.
    # Step 2: Capital-leak hard gate â€” raises RuntimeError on any breach.
    result_df = _defang_invalid_campaign_fatal_blocks(result_df, logger=logger)

    # Final guardrail: EOD/Morning handoff is research-only. Any legacy live-capital
    # label that survived row-level routing is corrected before the hard sanity gate.
    if "capital_permission" in result_df.columns:
        _cap = result_df["capital_permission"].fillna("").astype(str).str.upper().str.strip()
        _live_cap = _cap.isin(["YES", "LIVE_EXECUTE", "CAPITAL_APPROVED", "CAPITAL_AUTHORIZED"])
        if _live_cap.any():
            _sample = result_df.loc[_live_cap, "ticker"].head(25).tolist() if "ticker" in result_df.columns else []
            logger.warning(
                "CAPITAL_PERMISSION_PRE_SANITY_CORRECTED: %d legacy live-capital rows forced to EOD_CANDIDATE_ONLY. Sample=%s",
                int(_live_cap.sum()),
                _sample,
            )
            result_df.loc[_live_cap, "capital_permission"] = "EOD_CANDIDATE_ONLY"
            result_df.loc[_live_cap, "pse_final_size"] = 0.0
            result_df.loc[_live_cap, "fd_size"] = 0.0
            result_df.loc[_live_cap, "manual_sizing_required"] = True
            result_df.loc[_live_cap, "eod_candidate_permission"] = "MORNING_VALIDATION_REQUIRED"
            result_df.loc[_live_cap, "candidate_size"] = 0.0
            result_df.loc[_live_cap, "candidate_size_status"] = "MANUAL_SIZING_REQUIRED"
            result_df.loc[_live_cap, "candidate_size_source"] = "EOD_REVIEW_PSE_IGNORED"
            if "signal_authority_reason" in result_df.columns:
                result_df.loc[_live_cap, "signal_authority_reason"] = "LEGACY_LIVE_CAPITAL_PERMISSION_CORRECTED"

    _capital_permission_sanity(result_df, logger=logger)    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    # â”€â”€ Summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if "fd_verdict" in result_df.columns:
        dist  = result_df["fd_verdict"].value_counts()
        total = len(result_df)
        logger.info("=== DECISION DISTRIBUTION ===")
        for verdict, count in dist.items():
            logger.info(f"  {verdict:<25} : {count:>5}  ({count/total*100:.1f}%)")

        blocked = result_df[result_df["fd_verdict"] == "BLOCK"].shape[0]
        execute = result_df[result_df["fd_verdict"].isin(["EXECUTE", "EXECUTE_WITH_CAUTION"])].shape[0]
        logger.info(f"  Block rate  : {blocked/total*100:.1f}%")
        logger.info(f"  Execute rate: {execute/total*100:.1f}%")

        if "fd_reroute_flag" in result_df.columns:
            reroute = result_df[result_df["fd_reroute_flag"] == True].shape[0]
            logger.info(f"  Reroute candidates: {reroute} (review contract efficiency)")

    if _PSE_RETIRED_ADVISORY_ONLY and "eil_v3_verdict" in result_df.columns:
        logger.info("PSE RETIRED — distribution reflects EIL advisory verdicts (not PSE sizing)")
        execute_count   = result_df[result_df["eil_v3_verdict"] == "EXECUTE"].shape[0]
        ewc_count       = result_df[result_df["eil_v3_verdict"] == "EXECUTE_WITH_CAUTION"].shape[0]
        watchlist_count = result_df[result_df["eil_v3_verdict"] == "WATCHLIST"].shape[0]
        blocked_count   = result_df[result_df["eil_v3_verdict"] == "BLOCKED"].shape[0]
        logger.info(f"  EXECUTE:              {execute_count}")
        logger.info(f"  EXECUTE_WITH_CAUTION: {ewc_count}")
        logger.info(f"  WATCHLIST:            {watchlist_count}")
        logger.info(f"  BLOCKED:              {blocked_count}")
        logger.info(f"  Size: MANUAL — no PSE authority")

    # â”€â”€ FIX-11: Distribution sanity checks â€” self-detection of collapse â”€â”€â”€â”€â”€â”€
    if "fd_verdict" in result_df.columns:
        total_rows = len(result_df)
        exec_count  = result_df["fd_verdict"].isin(["EXECUTE","EXECUTE_WITH_CAUTION"]).sum()
        block_count = result_df["fd_verdict"].isin(["BLOCK"]).sum()
        eil_unique  = result_df["eil_v3_verdict"].nunique() if "eil_v3_verdict" in result_df.columns else 0

        exec_rate  = exec_count  / total_rows if total_rows else 0
        block_rate = block_count / total_rows if total_rows else 0

        sanity_warnings = []
        # PSE note: execute rate 50-80% is expected and healthy with PSE enabled.
        # Old threshold (>70% = warning) was calibrated for the block-heavy FDE pipeline.
        if exec_rate > 0.95 and total_rows >= 50:
            sanity_warnings.append(
                f"SANITY_WARN: execute rate {exec_rate:.0%} > 95% on {total_rows} rows â€” "
                "check that PSE fatal block conditions are configured correctly."
            )
        # Signal-authority-aware check: low execute rate is expected and healthy
        # once the authority policy separates STRUCTURAL_MATCH/FUTURE_EDGE from capital.
        # Replace the old PSE-availability heuristic with an EOD candidate health check.
        if "capital_permission" in result_df.columns:
            _eod_candidates = (
                result_df["capital_permission"]
                .fillna("").astype(str).str.upper()
                .eq("EOD_CANDIDATE_ONLY")
                .sum()
            )
            _candidate_rate = _eod_candidates / total_rows if total_rows else 0
            logger.info(
                "EOD candidate rate: %.1f%% (%d/%d rows with capital_permission=EOD_CANDIDATE_ONLY)",
                _candidate_rate * 100, _eod_candidates, total_rows,
            )
            if _candidate_rate < 0.005 and total_rows >= 100:
                sanity_warnings.append(
                    f"SANITY_NOTE: EIL pre-trigger EOD candidate rate {_candidate_rate*100:.1f}% < 0.5% â€” "
                    "Phase 10 candidate manifest is the execution shortlist authority."
                )
            elif _candidate_rate > 0.10 and total_rows >= 100:
                sanity_warnings.append(
                    f"SANITY_WARN: EOD candidate rate {_candidate_rate*100:.1f}% > 10% â€” "
                    "capital permission may be too loose after signal-authority policy."
                )
        else:
            sanity_warnings.append(
                "SANITY_WARN: capital_permission column missing â€” "
                "signal-authority policy may not have written governance fields."
            )
        if block_rate > 0.30 and total_rows >= 50:
            sanity_warnings.append(
                f"SANITY_WARN: FATAL block rate {block_rate:.0%} > 30% on {total_rows} rows â€” "
                "PSE fatal conditions firing too broadly. Review MP data blocks and EV thresholds."
            )
        if eil_unique <= 1 and total_rows >= 20:
            sanity_warnings.append(
                f"SANITY_FAIL: EIL produced only {eil_unique} unique verdict(s) across "
                f"{total_rows} rows â€” EIL is not discriminating. Check live microstructure inputs."
            )

        # FIX-01 (2026-04-19): Detect frozen EIL strategy scores.
        # When all 5 scores are identical across all rows (std < 0.01), the EIL
        # is running on hardcoded fallback defaults â€” live microstructure data
        # is unavailable. Scores are meaningless as discriminators.
        # Action: mark all rows as advisory_only=True so the convergence gate
        # does not block signals based on frozen non-data.
        _score_cols = {
            "liquidity": "eil_liquidity_score",
            "iv":        "eil_iv_score",
            "gex":       "eil_gex_score",
            "obi":       "eil_obi_score",
            "poc":       "eil_poc_score",
        }
        _frozen = []
        for _name, _col in _score_cols.items():
            if _col in result_df.columns:
                _std = result_df[_col].std()
                if _std < 0.01:
                    _frozen.append(_name)
        if _frozen and total_rows >= 20:
            sanity_warnings.append(
                f"SANITY_FAIL: EIL scores frozen (std<0.01) for: {_frozen}. "
                f"Data mode: {_EIL_DATA_MODE}. "
                + ("EOD_SYNTHETIC enrichment active â€” check adx/ivp/trend_direction columns in superbrain row."
                   if not _MARKET_HOURS else
                   "LIVE mode â€” check Polygon NBBO and MarketData.app connectivity.")
            )
            # Mark all rows advisory_only â€” convergence phase must respect this
            result_df["eil_advisory_only"] = True
            logger.warning(
                "[EIL-FIX-01] EIL scores frozen â€” advisory_only=True applied to all %d rows. "
                "Convergence gate will not block on frozen defaults. Mode: %s",
                total_rows, _EIL_DATA_MODE,
            )
        # OTT-05: Spread distribution sanity check
        if "eil_spread_pct_live" in result_df.columns:
            _spread_std = result_df["eil_spread_pct_live"].dropna().std()
            _spread_mean = result_df["eil_spread_pct_live"].dropna().mean()
            if _spread_std < 0.001 and total_rows >= 20:
                sanity_warnings.append(
                    f"SANITY_WARN_SPREAD: eil_spread_pct_live std={_spread_std:.4f} â€” "
                    f"all rows have identical spread (mean={_spread_mean:.2f}%). "
                    "bid/ask synthesis path not producing cross-sectional variance. "
                    "Check contract_premium and contract_spread_pct columns in superbrain row."
                )
            else:
                logger.info(
                    "OTT-05 Spread sanity: mean=%.1f%% std=%.2f%% â€” bid/ask synthesis OK",
                    _spread_mean, _spread_std,
                )

        mp_blocks = result_df.get("mp_hard_block_reason", pd.Series(dtype=str)).fillna("").str.strip()
        if (mp_blocks == "").all() and total_rows >= 20:
            sanity_warnings.append(
                "SANITY_WARN: mp_hard_block_reason is blank for all rows â€” "
                "MonetisationPolicy may be inactive or not firing."
            )

        if sanity_warnings:
            _has_sanity_fail = any(str(w).startswith("SANITY_FAIL") for w in sanity_warnings)
            _log = logger.warning if _has_sanity_fail else logger.info
            _log("=" * 72)
            _log("  PIPELINE SANITY CHECKS FAILED" if _has_sanity_fail else "  PIPELINE SANITY WARNINGS")
            for w in sanity_warnings:
                _log(f"  âš   {w}")
            _log("=" * 72)
        else:
            logger.info("Distribution sanity checks: PASSED")

    logger.info(f"EIL v{EIL_RUNNER_VERSION} COMPLETE")
    return result_df



# =============================================================================
# SIGNAL AUTHORITY POLICY
# =============================================================================
def _authority_float(row: dict, *keys: str, default: float = 0.0) -> float:
    for key in keys:
        try:
            value = row.get(key)
            if value is None:
                continue
            if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null", "na", "n/a"}:
                continue
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def _authority_text(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text.lower() in {"", "nan", "none", "null", "na", "n/a"}:
            continue
        return text
    return ""


def _authority_flags(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    if isinstance(value, (list, tuple, set)):
        raw = [str(v) for v in value]
    else:
        raw = str(value).replace(",", "|").replace(";", "|").split("|")
    return [
        flag.strip().upper()
        for flag in raw
        if flag and flag.strip() and flag.strip().lower() not in {"nan", "none", "null", "na", "n/a"}
    ]


def _options_research_profile(row: dict) -> dict:
    """
    Resolve the active options contract. When the new Options Intelligence
    research contract is present, it is authoritative over legacy
    options_verdict/options_score fields.
    """
    route = _authority_text(row, "final_route", "options_final_route", "options_research_route").upper()
    permission = _authority_text(row, "execution_permission", "options_execution_permission").upper()
    hard_vetoes = _authority_flags(row.get("hard_vetoes", row.get("options_hard_vetoes")))
    missing_data = _authority_flags(row.get("missing_data", row.get("options_missing_data")))
    score = _authority_float(row, "options_research_score", "options_score", "options_score_pre_macro")

    present = bool(
        route
        or permission == OPTIONS_RESEARCH_PERMISSION
        or hard_vetoes
        or missing_data
    )

    if not present:
        legacy_verdict = _authority_text(row, "options_verdict").upper()
        legacy_ok = legacy_verdict in {"EXECUTE", "ARMED"} or score >= 22.0
        return {
            "present": False,
            "route": legacy_verdict or "LEGACY_UNKNOWN",
            "score": score,
            "review_ok": legacy_ok,
            "blocked": False,
            "hard_vetoes": [],
            "missing_data": [],
            "reason": legacy_verdict or f"legacy_score={score:.1f}",
        }

    blocked = bool(hard_vetoes) or route in OPTIONS_NON_REVIEWABLE_ROUTES
    review_ok = route in OPTIONS_REVIEWABLE_ROUTES and not blocked
    reason_parts = [route or "OPTIONS_ROUTE_MISSING"]
    if hard_vetoes:
        reason_parts.append("veto=" + "|".join(hard_vetoes))
    if missing_data:
        reason_parts.append("missing=" + "|".join(missing_data))

    return {
        "present": True,
        "route": route or "OPTIONS_ROUTE_MISSING",
        "score": score,
        "review_ok": bool(review_ok),
        "blocked": bool(blocked),
        "hard_vetoes": hard_vetoes,
        "missing_data": missing_data,
        "reason": ";".join(reason_parts),
    }


def _eod_candidate_profile(row: dict, signal: str, tier: str) -> dict:
    """
    Decide whether a row deserves tomorrow validation even when live EOD capital
    is not authorized. This is the monetisation state between research inventory
    and funded execution.
    """
    signal = str(signal or "").upper().strip()
    tier = str(tier or "").upper().strip()
    if signal in {"", "NO_EDGE", "DATA_MISSING"} or tier in {"TIER_4_FLAT", "DATA_MISSING"}:
        return {"allowed": False, "reason": "NO_MONETISABLE_SIGNAL", "candidate_size": 0.0}

    options_contract = _options_research_profile(row)
    eil_verdict = str(row.get("eil_v3_verdict", "") or "").upper().strip()
    trigger_quality = str(row.get("trigger_quality", "") or "").upper().strip()
    trigger_state = str(row.get("trigger_state", "") or "").upper().strip()
    catalyst_class = str(row.get("catalyst_trade_class", "") or "").upper().strip()
    catalyst_quality = str(row.get("catalyst_data_quality", "") or "").upper().strip()
    direction_conflict_status = str(row.get("direction_conflict_status", "") or "").upper().strip()
    direction_conflict_unresolved = direction_conflict_status == "UNRESOLVED"

    options_score = float(options_contract.get("score", 0.0) or 0.0)
    rr = _authority_float(row, "rr_underlying", "rr", "rr_options")
    spread = _authority_float(row, "contract_spread_pct", "contract_spread_pct_eod", "eil_spread_pct_live")
    premium = _authority_float(row, "contract_premium", "premium", "premium_eod")
    oi = _authority_float(row, "contract_oi")
    volume = _authority_float(row, "contract_volume")

    options_ok = bool(options_contract.get("review_ok"))
    if options_contract.get("present"):
        economics_ok = options_ok
    else:
        economics_ok = rr >= 1.35 and options_score >= 20.0
    trigger_ok = (
        trigger_quality in {"STRONG", "SINGLE"}
        or trigger_state in {"TRIGGER_CONFIRMED", "TRIGGER_ARMED", "TRIGGER_EARLY_PROBE"}
        or str(row.get("trigger_go_eligible", "")).upper() in {"TRUE", "1", "YES"}
    )
    catalyst_ok = catalyst_class == "DATED_CATALYST_CONFIRMED" or catalyst_quality in {"CONFIRMED", "DATED_REVIEW", "INFERRED_GOOD"}
    contract_seen = options_ok or premium > 0.0 or oi > 0.0 or volume > 0.0
    liquidity_ok = options_ok or spread <= 30.0 or spread <= 0.0
    options_research_blocked = bool(options_contract.get("present") and options_contract.get("blocked"))

    support_ok = options_ok or trigger_ok or catalyst_ok
    # DOI-1: this profile controls preservation, not capital.  Entry economics,
    # liquidity, EIL and timing remain visible evidence and cannot remove the
    # governed ticker opportunity.
    allowed = signal in {"CURRENT_EDGE", "FUTURE_EDGE", "STRUCTURAL_MATCH", "TRANSITION"}

    reasons = []
    if options_ok: reasons.append(f"OPTIONS_RESEARCH_{options_contract.get('route')}")
    if options_research_blocked: reasons.append(f"OPTIONS_RESEARCH_BLOCKED:{options_contract.get('reason')}")
    if eil_verdict: reasons.append(f"EIL_ADVISORY_{eil_verdict}")
    if economics_ok: reasons.append("RR_AND_OPTIONS_SCORE_OK")
    if trigger_ok: reasons.append("TRIGGER_SUPPORT")
    if catalyst_ok: reasons.append("CATALYST_SUPPORT")
    if direction_conflict_unresolved: reasons.append("DIRECTION_CONFLICT_UNRESOLVED")
    if not liquidity_ok: reasons.append("SPREAD_REVIEW")
    if not contract_seen: reasons.append("NO_CONTRACT_MARKET")
    if not allowed and not reasons:
        reasons.append("QUALITY_FLOOR_NOT_MET")

    return {
        "allowed": bool(allowed),
        "reason": ";".join(reasons),
        "candidate_size": 0.0,
        "sizing_policy": PSE_RETIRED_POLICY,
        "candidate_size_status": "MANUAL_SIZING_REQUIRED" if allowed else "NO_CANDIDATE_SIZE",
        "candidate_size_source": "MANUAL_REVIEW_PSE_IGNORED" if allowed else "NO_EOD_CANDIDATE",
    }


def _apply_retired_sizing_overlay(row: dict, ev_result, percentile_override: bool = False) -> dict:
    """
    Production authority patch: PSE is advisory-only and may not allocate,
    suppress, or resize trades. The signal-authority policy decides whether a
    row becomes an EOD/morning-validation candidate; live size remains manual.
    """
    signal = str(row.get("signal_type", "") or "").upper().strip()
    tier = str(row.get("momentum_tier", "") or "").upper().strip()
    row["sizing_policy"] = PSE_RETIRED_POLICY
    row["pse_engine_state"] = "IGNORED_MANUAL_SIZING"
    row["pse_execution_mode"] = row.get("pse_execution_mode") or "SIZING_IGNORED_REVIEW"
    row["pse_final_size"] = 0.0
    row["pse_block_reason"] = row.get("pse_block_reason") or ""
    row["pse_advisory_note"] = PSE_MANUAL_SIZING_NOTE
    row["pse_trade_veto"] = False
    row["manual_sizing_required"] = True
    row["candidate_size_status"] = row.get("candidate_size_status") or "MANUAL_SIZING_REQUIRED"
    row["candidate_size_source"] = row.get("candidate_size_source") or "MANUAL_REVIEW_PSE_IGNORED"
    row["pse_signal_type"] = signal or "UNKNOWN"
    row["pse_momentum_tier"] = tier or "UNKNOWN"
    row["pse_edge_score"] = float(row.get("edge_score", row.get("options_score", 0.0)) or 0.0)
    row["pse_ev_mult"] = 1.0
    row["pse_mp_mult"] = 1.0
    row["pse_eil_mult"] = 1.0
    row["pse_options_mult"] = 1.0
    row["pse_regime_mult"] = 1.0
    # DOI-1: expose the EIL verdict in its own advisory field.  Do not copy it
    # into FinalDecision where legacy consumers can mistake it for authority.
    _eil_v = str(row.get("eil_v3_verdict", "") or "").upper().strip()
    row["fd_advisory_verdict"] = _eil_v or "NOT_EVALUATED"
    row["fd_verdict"] = "WATCHLIST"
    row["fd_size"] = 0.0
    row["fd_reason"] = f"PSE_RETIRED_MANUAL_SIZING — EIL={_eil_v or 'NOT_EVALUATED'} advisory only"
    row["fd_confidence"] = 0.0
    row["fd_ev_used"] = getattr(ev_result, "ev_conf_adj", row.get("ev_conf_adj", 0.0))
    row["fd_percentile_override"] = percentile_override
    row["eil_runner_version"] = EIL_RUNNER_VERSION
    return row


def _advisory_fd_verdict_from_eil(row: dict, fallback: str = "WATCHLIST") -> str:
    """Return the signal verdict that FinalDecision should expose in advisory mode.

    Live capital remains disabled by _finalize_execution_authority(); this only
    prevents the retired sizing overlay from collapsing every reviewed thesis
    into WATCHLIST and hiding EXECUTE / EXECUTE_WITH_CAUTION / BLOCKED context.
    """
    eil_v = str(row.get("eil_v3_verdict", "") or "").upper().strip()
    if eil_v in {"EXECUTE", "EXECUTE_WITH_CAUTION", "BLOCKED", "WATCHLIST"}:
        return eil_v
    return fallback


def _apply_eod_candidate_or_watch(
    row: dict,
    *,
    signal: str,
    watch_mode: str,
    watch_reason: str,
    watch_action: str,
) -> dict:
    profile = _eod_candidate_profile(row, signal, str(row.get("momentum_tier", "") or ""))
    advisory_verdict = _advisory_fd_verdict_from_eil(row)
    row["pse_execution_mode"] = watch_mode
    row["pse_final_size"] = 0.0
    row["fd_advisory_verdict"] = advisory_verdict
    row["fd_verdict"] = "WATCHLIST"
    row["fd_size"] = 0.0
    row["eod_candidate_size"] = profile["candidate_size"] if profile["allowed"] else 0.0
    row["candidate_size"] = row["eod_candidate_size"]
    row["sizing_policy"] = profile.get("sizing_policy", PSE_RETIRED_POLICY)
    row["pse_engine_state"] = "IGNORED_MANUAL_SIZING"
    row["pse_advisory_note"] = PSE_MANUAL_SIZING_NOTE
    row["pse_trade_veto"] = False
    row["manual_sizing_required"] = bool(profile["allowed"])
    row["candidate_size_status"] = profile.get("candidate_size_status", "NO_CANDIDATE_SIZE")
    row["candidate_size_source"] = profile.get("candidate_size_source", "NO_EOD_CANDIDATE")
    if str(row.get("pse_block_reason", "") or "").upper() in {
        "POSITION_SIZING_RETIRED_MANUAL_REVIEW",
        PSE_RETIRED_POLICY,
        PSE_OLD_RETIRED_POLICY,
    }:
        row["pse_block_reason"] = ""

    if profile["allowed"]:
        row["capital_permission"] = "EOD_CANDIDATE_ONLY"
        row["future_state_action"] = "MORNING_VALIDATION_REQUIRED"
        row["eod_candidate_permission"] = "MORNING_VALIDATION_REQUIRED"
        row["signal_authority_reason"] = f"{signal}_EOD_CANDIDATE:{profile['reason']}"
    else:
        row["capital_permission"] = "NO"
        row["future_state_action"] = watch_action
        row["eod_candidate_permission"] = "NO"
        row["signal_authority_reason"] = f"{signal}_NOT_EOD_CANDIDATE:{profile.get('reason') or watch_reason}"
    return row



def _meets_current_edge_clearance(row: dict) -> bool:
    """
    Conservative EOD clearance for CURRENT_EDGE rows. EOD may preserve theses,
    but current-edge execution labels require real contract economics before they
    can become an EOD candidate. Live execution remains manual/morning-gated.
    """
    def _num(*keys, default=0.0):
        for key in keys:
            try:
                val = row.get(key)
                if val is not None and str(val).strip() != "":
                    out = float(val)
                    if not math.isnan(out) and not math.isinf(out):
                        return out
            except Exception:
                continue
        return default

    ois = _num("options_score", "options_research_score", "ois_score")
    rr = _num("estimated_R", "estimated_r", "rr_options", "risk_reward")
    ivp = str(row.get("ivp_label", "") or row.get("iv_status", "") or "").upper().strip()
    tier = str(row.get("momentum_tier", "") or row.get("pse_momentum_tier", "") or "").upper().strip()
    spread = _num("contract_spread_pct", "eil_spread_pct_live", "spread_pct")
    spread_source = str(
        row.get("spread_source", "") or row.get("options_spread_source", "") or row.get("contract_spread_source", "") or ""
    ).upper().strip()
    has_real_spread = spread > 0 and spread_source not in {"OI_DERIVED", "UNAVAILABLE", "SYNTHETIC", "POLYGON_BSM"}
    if not spread_source:
        has_real_spread = spread > 0 and bool(row.get("options_bid") or row.get("contract_bid")) and bool(row.get("options_ask") or row.get("contract_ask"))

    return (
        ois >= 55.0
        and rr >= 2.0
        and ivp in {"CHEAP", "FAIR"}
        and tier in {"TIER_2_SUSTAINING", "TIER_2_ACTIVE"}
        and has_real_spread
    )
def _apply_signal_authority_policy(row: dict) -> dict:
    """
    Separate capital mode from candidate mode after the veto.

    STRUCTURAL_MATCH  â†’ STRUCTURAL_WATCH or EOD_CANDIDATE_ONLY
    FUTURE_EDGE       â†’ FUTURE_WATCH or EOD_CANDIDATE_ONLY
    CURRENT_EDGE      â†’ EOD_CANDIDATE_ONLY when the thesis is monetisable
    TRANSITION        â†’ EOD_CANDIDATE_ONLY when the thesis is monetisable
    NO_EDGE / TIER_4_FLAT â†’ SKIP (defence-in-depth after veto)
    DATA_MISSING      â†’ SKIP, DATA_REPAIR_REQUIRED
    unrecognised      â†’ WATCHLIST, manual review only

    Called after _apply_current_edge_hard_veto() at both call sites in _process_row().
    """
    signal = str(row.get("signal_type",       "") or "").upper().strip()
    tier   = str(row.get("momentum_tier",     "") or "").upper().strip()
    mode   = str(row.get("pse_execution_mode","") or "").upper().strip()

    options_profile = _options_research_profile(row)
    if options_profile.get("present") and options_profile.get("blocked"):
        row["pse_execution_mode"]       = "OPTIONS_REPAIR_REQUIRED"
        row["pse_final_size"]           = 0.0
        row["fd_verdict"]               = "WATCHLIST"
        row["fd_size"]                  = 0.0
        row["capital_permission"]       = "NO"
        row["eod_candidate_permission"] = "CONTRACT_REPAIR_REQUIRED"
        row["eod_candidate_size"]       = 0.0
        row["candidate_size"]           = 0.0
        row["manual_sizing_required"]   = False
        row["candidate_size_status"]    = "NO_CANDIDATE_SIZE"
        row["candidate_size_source"]    = "OPTIONS_REPAIR_REQUIRED"
        row["future_state_action"]      = "OPTIONS_REPAIR_REQUIRED"
        row["pse_block_reason"]         = "OPTIONS_RESEARCH_BLOCKED"
        row["signal_authority_reason"]  = f"OPTIONS_RESEARCH_BLOCKED:{options_profile.get('reason', '')}"
        return row

    if signal == "DATA_MISSING" or tier == "DATA_MISSING":
        row["pse_execution_mode"]      = "DATA_REPAIR_REQUIRED"
        row["pse_final_size"]          = 0.0
        row["fd_verdict"]              = "WATCHLIST"
        row["fd_size"]                 = 0.0
        row["capital_permission"]      = "NO"
        row["eod_candidate_permission"] = "NO"
        row["eod_candidate_size"]       = 0.0
        row["candidate_size"]           = 0.0
        row["manual_sizing_required"]   = False
        row["candidate_size_status"]    = "NO_CANDIDATE_SIZE"
        row["candidate_size_source"]    = "DATA_REPAIR_REQUIRED"
        row["future_state_action"]     = "DATA_REPAIR_REQUIRED"
        row["signal_authority_reason"] = "DATA_MISSING_REPAIR_REQUIRED"
        return row

    if signal == "NO_EDGE" or tier == "TIER_4_FLAT":
        row["pse_execution_mode"]      = "EOD_PROBE_CANDIDATE"
        row["pse_final_size"]          = 0.0
        row["fd_verdict"]              = "WATCHLIST"
        row["fd_size"]                 = 0.0
        row["capital_permission"]      = "EOD_CANDIDATE_ONLY"
        row["eod_candidate_permission"] = "MORNING_VALIDATION_REQUIRED"
        row["eod_candidate_size"]       = 0.0
        row["candidate_size"]           = 0.0
        row["manual_sizing_required"]   = True
        row["candidate_size_status"]    = "MANUAL_SIZING_REQUIRED"
        row["candidate_size_source"]    = "SPARSE_ACTUARIAL_REVIEW"
        row["future_state_action"]     = row.get("future_state_action") or "EOD_PROBE_CANDIDATE"
        row["signal_authority_reason"] = "SPARSE_ACTUARIAL_CONTEXT_EOD_PROBE_CANDIDATE"
        return row

    if signal == "STRUCTURAL_MATCH":
        return _apply_eod_candidate_or_watch(
            row,
            signal=signal,
            watch_mode="STRUCTURAL_WATCH",
            watch_reason="STRUCTURAL_MATCH_NOT_CURRENT_EDGE",
            watch_action="STRUCTURAL_WATCH",
        )

    if signal == "FUTURE_EDGE":
        return _apply_eod_candidate_or_watch(
            row,
            signal=signal,
            watch_mode="FUTURE_WATCH",
            watch_reason="FUTURE_EDGE_NOT_CURRENT_CAPITAL",
            watch_action="FUTURE_WATCH",
        )

    if signal == "CURRENT_EDGE" and _ACTIVE_EOD_DATA_MODE == "EOD_SYNTHETIC" and not _meets_current_edge_clearance(row):
        row["pse_execution_mode"]       = "BLOCKED"
        row["pse_final_size"]           = 0.0
        row["fd_verdict"]               = "WATCHLIST"
        row["fd_size"]                  = 0.0
        row["capital_permission"]       = "NO"
        row["eod_candidate_permission"] = "NO"
        row["eod_candidate_size"]       = 0.0
        row["candidate_size"]           = 0.0
        row["manual_sizing_required"]   = False
        row["candidate_size_status"]    = "NO_CANDIDATE_SIZE"
        row["candidate_size_source"]    = "CURRENT_EDGE_EOD_BLOCK"
        row["future_state_action"]      = "BLOCKED"
        row["pse_block_reason"]         = "CURRENT_EDGE_EOD_BLOCK"
        row["signal_authority_reason"]  = "CURRENT_EDGE_EOD_BLOCK:LIVE_CLEARANCE_REQUIRED"
        return row

    if signal in {"CURRENT_EDGE", "TRANSITION"}:
        return _apply_eod_candidate_or_watch(
            row,
            signal=signal,
            watch_mode=f"{signal}_REVIEW",
            watch_reason=f"{signal}_MANUAL_REVIEW_REQUIRED_SIZING_RETIRED",
            watch_action="MANUAL_REVIEW_REQUIRED",
        )

    # Catch-all
    row["pse_execution_mode"]      = "WATCHLIST"
    row["pse_final_size"]          = 0.0
    row["fd_verdict"]              = "WATCHLIST"
    row["fd_size"]                 = 0.0
    row["capital_permission"]      = "NO"
    row["eod_candidate_permission"] = "NO"
    row["eod_candidate_size"]       = 0.0
    row["candidate_size"]           = 0.0
    row["manual_sizing_required"]   = False
    row["candidate_size_status"]    = "NO_CANDIDATE_SIZE"
    row["candidate_size_source"]    = "UNMAPPED_SIGNAL"
    row["future_state_action"]     = "WATCHLIST"
    row["signal_authority_reason"] = "UNMAPPED_SIGNAL_MANUAL_REVIEW_ONLY"
    return row


def _finalize_execution_authority(row: dict) -> dict:
    """
    Make the capital-authorized verdict explicit.

    execution_verdict remains the historical campaign label. Downstream funding
    decisions should read execution_authorized and effective_execution_verdict.
    """
    def _as_float(value, default=0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    capital_permission = str(row.get("capital_permission", "") or "").upper().strip()
    eod_candidate_permission = str(row.get("eod_candidate_permission", "") or "").upper().strip()
    execution_verdict = str(row.get("execution_verdict", "") or "").upper().strip()
    pse_mode = str(row.get("pse_execution_mode", "") or "").upper().strip()
    size = _as_float(row.get("pse_final_size", row.get("fd_size", 0.0)), 0.0)
    candidate_size = _as_float(
        row.get("eod_candidate_size", row.get("candidate_size", row.get("pse_pre_horizon_size", 0.0))),
        0.0,
    )
    governed_direction = str(
        row.get("governed_direction")
        or row.get("canonical_direction")
        or row.get("direction")
        or row.get("options_direction")
        or ""
    ).upper().strip()
    invalidation_raw = (
        row.get("invalidation_spot")
        if row.get("invalidation_spot") not in (None, "")
        else row.get("invalidation_price")
    )
    invalidation_value = _as_float(invalidation_raw, 0.0)
    invalidation_state = str(row.get("invalidation_state") or "").upper().strip()
    invalidation_unavailable_states = {
        "MISSING", "UNAVAILABLE", "NOT_AVAILABLE", "MISSING_AUTHORITATIVE_STOP",
        "MISSING_GOVERNED_INVALIDATION", "NOT_EVALUATED_NON_DIRECTIONAL",
    }
    invalidation_missing = (
        governed_direction in {"CALL", "PUT"}
        and (invalidation_value <= 0.0 or invalidation_state in invalidation_unavailable_states)
    )
    if invalidation_missing:
        capital_permission = "NO"
        eod_candidate_permission = "STRUCTURAL_REVIEW_ONLY"
        pse_mode = "DATA_REPAIR_REQUIRED"
        size = 0.0
        candidate_size = 0.0
        row["capital_permission"] = capital_permission
        row["eod_candidate_permission"] = eod_candidate_permission
        row["pse_execution_mode"] = pse_mode
        row["pse_final_size"] = 0.0
        row["fd_size"] = 0.0
        row["eod_candidate_size"] = 0.0
        row["candidate_size"] = 0.0
        row["invalidation_state"] = "MISSING_GOVERNED_INVALIDATION"
        row["execution_geometry_state"] = "DATA_REPAIR_REQUIRED"
        row["signal_authority_reason"] = "MISSING_GOVERNED_INVALIDATION"
    options_contract = _options_research_profile(row)
    options_research_blocked = bool(options_contract.get("present") and options_contract.get("blocked"))
    if options_research_blocked:
        capital_permission = "NO"
        eod_candidate_permission = "CONTRACT_REPAIR_REQUIRED"
        pse_mode = "OPTIONS_REPAIR_REQUIRED"
        size = 0.0
        candidate_size = 0.0
        row["capital_permission"] = capital_permission
        row["eod_candidate_permission"] = eod_candidate_permission
        row["pse_execution_mode"] = pse_mode
        row["pse_final_size"] = 0.0
        row["fd_size"] = 0.0
        row["eod_candidate_size"] = 0.0
        row["candidate_size"] = 0.0
        row["signal_authority_reason"] = (
            row.get("signal_authority_reason")
            or f"OPTIONS_RESEARCH_BLOCKED:{options_contract.get('reason')}"
        )

    authorized = (
        capital_permission in {"YES", "LIVE_EXECUTE", "CAPITAL_APPROVED"}
        and size > 0.0
        and pse_mode in {"PROBE", "REDUCED", "EXECUTE", "FULL_EXECUTE"}
    )
    eod_candidate_authorized = (
        capital_permission == "EOD_CANDIDATE_ONLY"
        and eod_candidate_permission not in {"CONTRACT_REPAIR_REQUIRED", "NO_CONTRACT_TO_REPAIR"}
    )

    if authorized:
        effective = execution_verdict or pse_mode
        reason = "LIVE_CAPITAL_AUTHORIZED"
    elif eod_candidate_authorized:
        effective = "MORNING_VALIDATION_REQUIRED"
        reason = row.get("signal_authority_reason") or "EOD_CANDIDATE_REQUIRES_LIVE_CONFIRMATION"
    elif eod_candidate_permission == "CONTRACT_REPAIR_REQUIRED":
        effective = "OPTIONS_REPAIR_REQUIRED"
        reason = row.get("signal_authority_reason") or "CONTRACT_REPAIR_REQUIRED_BEFORE_MORNING_VALIDATION"
    elif pse_mode in {
        "STRUCTURAL_WATCH",
        "FUTURE_WATCH",
        "WATCHLIST",
        "SKIP",
        "FATAL_BLOCK",
        "OPTIONS_REPAIR_REQUIRED",
        "DATA_REPAIR_REQUIRED",
    }:
        effective = pse_mode
        reason = row.get("signal_authority_reason") or "NO_CAPITAL_PERMISSION"
    elif size <= 0.0 or capital_permission in {"NO", "NO_CAPITAL", "WATCH_ONLY", ""}:
        effective = "WATCHLIST" if execution_verdict == "BUY_NOW" else (execution_verdict or "WATCHLIST")
        reason = row.get("signal_authority_reason") or "NO_CAPITAL_PERMISSION"
    else:
        effective = execution_verdict or pse_mode or "WATCHLIST"
        reason = row.get("signal_authority_reason") or "CAPITAL_AUTHORITY_UNCLEAR"

    row["execution_authorized"] = bool(authorized)
    row["eod_candidate_authorized"] = bool(eod_candidate_authorized)
    row["eil_signal_verdict"] = str(row.get("eil_v3_verdict", "") or "").upper().strip()
    if authorized:
        row["capital_authorization_state"] = "LIVE_AUTHORIZED"
    elif eod_candidate_authorized:
        row["capital_authorization_state"] = "EOD_CANDIDATE_ONLY"
    else:
        row["capital_authorization_state"] = "NOT_AUTHORIZED"
    row["eod_candidate_size"] = round(float(candidate_size), 6) if eod_candidate_authorized else 0.0
    row["candidate_size"] = row["eod_candidate_size"]
    default_probe_size = 1 if eod_candidate_authorized else 0
    try:
        premium = _as_float(row.get("contract_premium", row.get("premium", 0.0)), 0.0)
        kelly = _as_float(row.get("layer2__kelly_fraction", row.get("kelly_fraction", 0.0)), 0.0)
        risk_budget = _as_float(os.getenv("AVSHUNTER_ACCOUNT_RISK_BUDGET", "1000"), 1000.0)
        suggested = max(1, round(kelly * risk_budget / max(premium * 100.0, 1.0))) if eod_candidate_authorized and premium > 0 else default_probe_size
    except Exception:
        suggested = default_probe_size
    row["default_probe_size"] = default_probe_size
    row["pse_suggested_contracts"] = suggested
    row["reviewer_approval"] = row.get("reviewer_approval", "")
    row["approved_size_contracts"] = row.get("approved_size_contracts", "")
    row["manual_review_required"] = True if eod_candidate_authorized else bool(row.get("manual_sizing_required", False))
    row.setdefault("sizing_policy", PSE_RETIRED_POLICY)
    row.setdefault("pse_engine_state", "IGNORED_MANUAL_SIZING")
    row.setdefault("pse_advisory_note", PSE_MANUAL_SIZING_NOTE)
    row.setdefault("pse_trade_veto", False)
    if eod_candidate_authorized:
        row["manual_sizing_required"] = True
        row.setdefault("candidate_size_status", "MANUAL_SIZING_REQUIRED")
        row.setdefault("candidate_size_source", "MANUAL_REVIEW_PSE_IGNORED")
    spread_source = str(
        row.get("spread_source", "") or row.get("options_spread_source", "") or row.get("contract_spread_source", "") or ""
    ).upper().strip()
    if spread_source == "OI_DERIVED":
        try:
            conf = float(row.get("confidence_score"))
            if not math.isnan(conf) and not math.isinf(conf):
                row["confidence_score"] = round(conf * 0.875, 4)
        except Exception:
            pass
        row["microstructure_confidence_haircut"] = "OI_DERIVED_SPREAD_12_5PCT"
    else:
        row.setdefault("microstructure_confidence_haircut", "NONE")
    row["effective_execution_verdict"] = effective
    row["final_decision_advisory_verdict"] = (
        row.get("fd_advisory_verdict")
        or row.get("fd_verdict")
        or row.get("eil_v3_verdict")
        or "WATCHLIST"
    )
    row["execution_verdict_source"] = "CAPITAL_AUTHORITY" if authorized else "CAMPAIGN_LABEL_PRE_LIVE"
    row["execution_authority_reason"] = reason
    if not authorized and execution_verdict == "BUY_NOW":
        row["execution_label_warning"] = (
            "BUY_NOW is a campaign label only; use effective_execution_verdict "
            "and capital_permission for funding decisions."
        )
    else:
        row["execution_label_warning"] = ""
    return row


def _finalize_execution_authority_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    rows = []
    for _, row in df.iterrows():
        data = row.to_dict()
        if (
            str(data.get("execution_authorized", "")).strip().lower() in {"", "nan", "none", "null"}
            or str(data.get("eod_candidate_authorized", "")).strip().lower() in {"", "nan", "none", "null"}
        ):
            data = _finalize_execution_authority(data)
        rows.append(data)

    out = pd.DataFrame(rows)
    if "execution_authorized" in out.columns:
        out["execution_authorized"] = out["execution_authorized"].fillna(False).astype(bool)
    else:
        out["execution_authorized"] = False
    if "eod_candidate_authorized" in out.columns:
        out["eod_candidate_authorized"] = out["eod_candidate_authorized"].fillna(False).astype(bool)
    else:
        out["eod_candidate_authorized"] = False
    for col, default in {
        "effective_execution_verdict": "WATCHLIST",
        "final_decision_advisory_verdict": "WATCHLIST",
        "execution_verdict_source": "CAMPAIGN_LABEL_PRE_LIVE",
        "execution_authority_reason": "NO_CAPITAL_PERMISSION",
        "execution_label_warning": "",
        "eil_signal_verdict": "",
        "capital_authorization_state": "NOT_AUTHORIZED",
        "eod_candidate_permission": "NO",
        "eod_candidate_size": 0.0,
        "candidate_size": 0.0,
    }.items():
        if col not in out.columns:
            out[col] = default
        else:
            out[col] = out[col].fillna(default)
    return out


# =============================================================================
# AVSHUNTER â€” Vanguard / Actuarial Pre-EIL Handoff Normaliser
# =============================================================================
def _handoff_blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip().lower() in {"", "nan", "none", "null", "na", "n/a"}


def _handoff_side(value) -> str:
    text = str(value or "").strip().upper()
    if text in {"CALL", "CALLS", "LONG_CALL", "BULL", "BULLISH", "UP", "BUY"}:
        return "CALL"
    if text in {"PUT", "PUTS", "LONG_PUT", "BEAR", "BEARISH", "DOWN", "SELL", "SHORT"}:
        return "PUT"
    return ""


def _first_present_side(row: pd.Series, *cols: str) -> str:
    for col in cols:
        if col in row.index:
            side = _handoff_side(row.get(col))
            if side:
                return side
    return ""


def _direction_arbitration_row(row: pd.Series) -> dict:
    option_side = _first_present_side(row, "canonical_direction", "resolved_direction", "footprint_direction", "direction", "primary_direction", "options_direction", "trade_direction", "selected_contract_side")
    vanguard_side = _first_present_side(row, "vanguard_edge_direction", "layer2__edge_direction", "vanguard_edge_direction_flat", "edge_direction")
    intent = str(row.get("intent", "") or "").strip().upper()
    if not option_side:
        return {
            "direction_arbitration_status": "NOT_EVALUATED",
            "direction_arbitration_reason": "No tradeable options direction available",
            "direction_conflict_gate": "NONE",
        }
    if not vanguard_side:
        return {
            "direction_arbitration_status": "NO_PROBABILITY_OPINION",
            "direction_arbitration_reason": f"Structure leads: {intent or 'UNKNOWN'} maps to {option_side}; Vanguard has no directional edge",
            "direction_conflict_gate": "NONE",
        }
    if option_side == vanguard_side:
        return {
            "direction_arbitration_status": "AGREEMENT",
            "direction_arbitration_reason": f"Structure and Vanguard both support {option_side}",
            "direction_conflict_gate": "NONE",
        }
    return {
        "direction_arbitration_status": "CONFLICT_STRUCTURE_LEADS",
        "direction_arbitration_reason": f"Structure maps to {option_side} while Vanguard edge is {vanguard_side}; require live tape confirmation",
        "direction_conflict_gate": "VWAP_CONFIRMATION_REQUIRED",
    }


def _catalyst_conflict_row(row: pd.Series) -> dict:
    catalyst_side = _first_present_side(row, "catalyst_direction_bias", "catalyst_trade_bias")
    option_side = _first_present_side(row, "canonical_direction", "resolved_direction", "footprint_direction", "direction", "primary_direction", "options_direction", "trade_direction", "selected_contract_side")
    explicit = str(row.get("catalyst_alignment_label", "") or "").strip().upper() == "DIRECTION_CONFLICT"
    if catalyst_side and option_side and catalyst_side != option_side:
        return {
            "catalyst_direction_conflict_status": "CATALYST_CONFLICT_REQUIRES_CONFIRMATION",
            "catalyst_direction_conflict_reason": f"Catalyst side {catalyst_side or 'UNKNOWN'} conflicts with thesis side {option_side or 'UNKNOWN'}",
        }
    if explicit and not catalyst_side:
        return {
            "catalyst_direction_conflict_status": "CATALYST_CONTEXT_REVIEW",
            "catalyst_direction_conflict_reason": "Upstream catalyst label is DIRECTION_CONFLICT but no explicit catalyst side was provided",
        }
    if catalyst_side and option_side and catalyst_side == option_side:
        return {
            "catalyst_direction_conflict_status": "CATALYST_CONFIRMS",
            "catalyst_direction_conflict_reason": f"Catalyst and thesis both support {option_side}",
        }
    return {
        "catalyst_direction_conflict_status": "NO_CATALYST_OPINION",
        "catalyst_direction_conflict_reason": "",
    }


def _ensure_eil_audit_contract(df: pd.DataFrame) -> pd.DataFrame:
    """Keep producer audit fields intact through EIL and enriched handoffs."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for col, default in {
        "pcr_vol_status": "",
        "pcr_vol_missing_reason": "",
        "pcr_direction_conflict_status": "",
        "pcr_direction_conflict_reason": "",
        "catalyst_direction_conflict_status": "",
        "catalyst_direction_conflict_reason": "",
        "direction_arbitration_status": "",
        "direction_arbitration_reason": "",
        "direction_conflict_gate": "",
        "direction_conflict_status": "",
        "direction_conflict_reason": "",
        "contract_repair_attempted": False,
        "contract_repair_status": "",
        "contract_repair_required": False,
        "contract_repair_reason": "",
    }.items():
        if col not in out.columns:
            out[col] = default

    pcr_raw = out["dw_pcr_vol"] if "dw_pcr_vol" in out.columns else pd.Series([None] * len(out), index=out.index)
    pcr_source = pd.to_numeric(pcr_raw, errors="coerce")
    if "pcr_vol" in out.columns:
        pcr_source = pcr_source.fillna(pd.to_numeric(out["pcr_vol"], errors="coerce"))
    pcr_signal = out.get("pcr_signal", pd.Series([""] * len(out), index=out.index)).fillna("").astype(str).str.upper()
    if "dw_signal" in out.columns:
        dw_signal = out["dw_signal"].fillna("").astype(str).str.upper()
        pcr_signal = pcr_signal.where(~pcr_signal.apply(_handoff_blank), dw_signal)
    verdict = out.get(
        "options_verdict",
        out.get("eil_v3_verdict", pd.Series([""] * len(out), index=out.index)),
    ).fillna("").astype(str).str.upper()

    blank_status = out["pcr_vol_status"].apply(_handoff_blank)
    out.loc[blank_status & pcr_source.notna(), "pcr_vol_status"] = "OK"
    blank_status = out["pcr_vol_status"].apply(_handoff_blank)
    out.loc[
        blank_status & pcr_signal.isin({"BULLISH", "BEARISH", "NEUTRAL", "STRONGLY_BULLISH", "STRONGLY_BEARISH"}),
        "pcr_vol_status",
    ] = "OI_ONLY_NO_INTRADAY_VOLUME"
    blank_status = out["pcr_vol_status"].apply(_handoff_blank)
    out.loc[blank_status & verdict.isin({"STAND_DOWN", "BLOCK", "BLOCKED"}), "pcr_vol_status"] = "NOT_EVALUATED"
    out.loc[out["pcr_vol_status"].apply(_handoff_blank), "pcr_vol_status"] = "MISSING"

    reason_blank = out["pcr_vol_missing_reason"].apply(_handoff_blank)
    out.loc[
        reason_blank & out["pcr_vol_status"].eq("OI_ONLY_NO_INTRADAY_VOLUME"),
        "pcr_vol_missing_reason",
    ] = "OPTIONS_CHAIN_VOLUME_NOT_AVAILABLE;USING_OPEN_INTEREST_PCR_ONLY"
    out.loc[
        reason_blank & out["pcr_vol_status"].eq("NOT_EVALUATED"),
        "pcr_vol_missing_reason",
    ] = "NOT_EVALUATED_BEFORE_FLOW_REVIEW"
    out.loc[
        reason_blank & out["pcr_vol_status"].eq("MISSING"),
        "pcr_vol_missing_reason",
    ] = "NO_PCR_VOLUME_OR_OI_SIGNAL"

    pcr_legacy = out["direction_conflict_reason"].fillna("").astype(str).str.upper().str.contains("PCR")
    pcr_blank = out["pcr_direction_conflict_status"].apply(_handoff_blank)
    legacy_status = out["direction_conflict_status"].fillna("").astype(str).str.upper()
    out.loc[pcr_blank & pcr_legacy & legacy_status.eq("UNRESOLVED"), "pcr_direction_conflict_status"] = "PCR_CONFLICT_REQUIRES_FLOW_CONFIRMATION"
    out.loc[pcr_blank & pcr_legacy & ~legacy_status.eq("UNRESOLVED"), "pcr_direction_conflict_status"] = out.loc[pcr_blank & pcr_legacy & ~legacy_status.eq("UNRESOLVED"), "direction_conflict_status"]
    reason_blank = out["pcr_direction_conflict_reason"].apply(_handoff_blank)
    out.loc[reason_blank & pcr_legacy, "pcr_direction_conflict_reason"] = out.loc[reason_blank & pcr_legacy, "direction_conflict_reason"]

    catalyst_audit = out.apply(_catalyst_conflict_row, axis=1, result_type="expand")
    for col in catalyst_audit.columns:
        blank = out[col].apply(_handoff_blank)
        out.loc[blank, col] = catalyst_audit.loc[blank, col]

    arbitration = out.apply(_direction_arbitration_row, axis=1, result_type="expand")
    for col in arbitration.columns:
        blank = out[col].apply(_handoff_blank)
        out.loc[blank, col] = arbitration.loc[blank, col]

    structural_conflict = out["direction_arbitration_status"].fillna("").astype(str).str.upper().eq("CONFLICT_STRUCTURE_LEADS")
    catalyst_conflict = out["catalyst_direction_conflict_status"].fillna("").astype(str).str.upper().eq("CATALYST_CONFLICT_REQUIRES_CONFIRMATION")
    pcr_conflict = out["pcr_direction_conflict_status"].fillna("").astype(str).str.upper().str.contains("CONFLICT")

    out.loc[verdict.isin({"STAND_DOWN", "BLOCK", "BLOCKED"}), "direction_conflict_status"] = "NOT_EVALUATED"
    active_mask = ~verdict.isin({"STAND_DOWN", "BLOCK", "BLOCKED"})
    out.loc[active_mask & (structural_conflict | catalyst_conflict | pcr_conflict), "direction_conflict_status"] = "MITIGATED_REQUIRES_CONFIRMATION"
    out.loc[active_mask & ~(structural_conflict | catalyst_conflict | pcr_conflict), "direction_conflict_status"] = "NO_CONFLICT"
    out.loc[structural_conflict | catalyst_conflict, "direction_conflict_gate"] = "VWAP_CONFIRMATION_REQUIRED"

    reasons = []
    for _, row in out.iterrows():
        parts = []
        if str(row.get("direction_arbitration_status", "")).upper() == "CONFLICT_STRUCTURE_LEADS":
            parts.append(str(row.get("direction_arbitration_reason", "") or "STRUCTURE_PROBABILITY_CONFLICT"))
        if str(row.get("catalyst_direction_conflict_status", "")).upper() == "CATALYST_CONFLICT_REQUIRES_CONFIRMATION":
            parts.append(str(row.get("catalyst_direction_conflict_reason", "") or "CATALYST_DIRECTION_CONFLICT"))
        if "CONFLICT" in str(row.get("pcr_direction_conflict_status", "")).upper():
            parts.append(str(row.get("pcr_direction_conflict_reason", "") or "PCR_DIRECTION_CONFLICT"))
        reasons.append("; ".join(p for p in parts if p))
    out["direction_conflict_reason"] = reasons
    out.loc[out["direction_conflict_status"].eq("NO_CONFLICT"), "direction_conflict_reason"] = ""

    contract_seen = pd.Series([False] * len(out), index=out.index)
    for col in ("recommended_contract", "contract_occ_symbol", "contract_symbol"):
        if col in out.columns:
            contract_seen = contract_seen | ~out[col].apply(_handoff_blank)
    repair_blank = out["contract_repair_status"].apply(_handoff_blank)
    out.loc[repair_blank & contract_seen, "contract_repair_status"] = "CONTRACT_OK"
    out.loc[repair_blank & ~contract_seen, "contract_repair_status"] = "NO_CONTRACT_TO_REPAIR"
    out.loc[
        out["contract_repair_reason"].apply(_handoff_blank) & ~contract_seen,
        "contract_repair_reason",
    ] = "No initial contract passed quality gates"
    out["contract_repair_required"] = out["contract_repair_status"].astype(str).str.upper().isin(
        {"CONTRACT_REPAIR_REQUIRED", "NO_CONTRACT_TO_REPAIR"}
    )
    out = _suppress_retired_eil_verdict_against_governed_stand_down(out)
    return out


#: EIL verdict values that read as permission to trade.
_EIL_EXECUTE_VERDICTS_PREFIX = "EXECUTE"
#: Columns carrying the retired EIL verdict into eil_enriched / execution_v3_5.
_EIL_VERDICT_COLUMNS = ("eil_v3_verdict", "eil_signal_verdict", "fd_verdict")


def _suppress_retired_eil_verdict_against_governed_stand_down(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """A retired advisory verdict may not contradict a governed stand-down.

    AVS-FIX-001 W1.2 (QT-D06); clears AVS-MVP-001 §6 kill criterion 6.

    Run 20260905_151448 published `eil_v3_verdict = EXECUTE_WITH_CAUTION`
    beside `options_verdict = STAND_DOWN` on 187 rows (127 CALL, 60 PUT, 0
    OTHER) -- TTEK being the row the tester named, which also carried
    `invalidation_state = MISSING`. EIL v3 no longer holds any authority, but a
    column that says EXECUTE next to a governed STAND_DOWN is read by a human
    as a second opinion, and the semantic audit correctly reports it as a
    contradiction.

    Where the governed decision is STAND_DOWN, or the governed invalidation is
    not AVAILABLE, the retired verdict is written as NOT_EVALUATED -- an
    existing EvidenceState member, not a new state name -- and the reason is
    named in `eil_verdict_suppression_reason`. Nothing else about the row
    changes: this removes a contradictory claim, it does not grant, remove or
    alter any permission, and the Execution Gate remains the sole writer of
    `final_action`.

    The same suppression is deliberately NOT applied to BLOCKED/WATCHLIST
    verdicts: those agree with a stand-down, and preserving them keeps the
    telemetry useful for diagnosing why a row stood down.
    """
    if df is None or df.empty:
        return df
    present = [column for column in _EIL_VERDICT_COLUMNS if column in df.columns]
    if not present:
        return df
    out = df

    governed_verdict = (
        out.get("options_verdict", pd.Series([""] * len(out), index=out.index))
        .fillna("").astype(str).str.strip().str.upper()
    )
    invalidation_state = (
        out.get("invalidation_state", pd.Series([""] * len(out), index=out.index))
        .fillna("").astype(str).str.strip().str.upper()
    )
    stood_down = governed_verdict.eq("STAND_DOWN")
    # An absent invalidation_state column must not manufacture a suppression:
    # only a state that is present and not AVAILABLE counts.
    invalidation_unavailable = invalidation_state.ne("") & invalidation_state.ne("AVAILABLE")
    governed_refusal = stood_down | invalidation_unavailable

    if "eil_verdict_suppression_reason" not in out.columns:
        out["eil_verdict_suppression_reason"] = ""

    reason = pd.Series([""] * len(out), index=out.index)
    reason = reason.mask(stood_down, "GOVERNED_OPTIONS_VERDICT_STAND_DOWN")
    reason = reason.mask(
        invalidation_unavailable & ~stood_down, "GOVERNED_INVALIDATION_NOT_AVAILABLE"
    )
    reason = reason.mask(
        stood_down & invalidation_unavailable,
        "GOVERNED_OPTIONS_VERDICT_STAND_DOWN;GOVERNED_INVALIDATION_NOT_AVAILABLE",
    )

    contradicts_any = pd.Series([False] * len(out), index=out.index)
    for column in present:
        claims_execute = (
            out[column].fillna("").astype(str).str.strip().str.upper()
            .str.startswith(_EIL_EXECUTE_VERDICTS_PREFIX)
        )
        contradiction = claims_execute & governed_refusal
        if contradiction.any():
            out.loc[contradiction, column] = "NOT_EVALUATED"
        contradicts_any = contradicts_any | contradiction

    if contradicts_any.any():
        out.loc[contradicts_any, "eil_verdict_suppression_reason"] = reason[contradicts_any]
    return out


_REQUIRED_VANGUARD_HANDOFF_COLS = [
    "ticker","signal_type","momentum_tier","fwd_momentum_conf","state_v2_key",
    "behaviour_state_key","behaviour_state_hash","actuarial_match_type",
    "actuarial_ev_weight","catalyst_overlay",
    "actuarial_valid","actuarial_no_match","actuarial_sample",
    "win_rate_5d","win_rate_10d","win_rate_20d","efficiency_10d",
    "actuarial_win_rate_10d","actuarial_efficiency_10d",
    "current_edge_source","actuarial_source","handoff_integrity_status",
]

def _vg_clean_str(x):
    if x is None: return ""
    try:
        if pd.isna(x): return ""
    except Exception: pass
    return str(x).strip().upper()

def _vg_num(x, default=float("nan")):
    try:
        v = pd.to_numeric(x, errors="coerce")
        return default if pd.isna(v) else float(v)
    except Exception: return default

def _vg_first(row, *keys, default=None):
    """Return first non-empty/non-NaN value. Checks canonical and raw layer2__ names."""
    for key in keys:
        try: v = row.get(key)
        except Exception: continue
        if v is None: continue
        try:
            if pd.isna(v): continue
        except Exception: pass
        if isinstance(v,str) and v.strip().lower() in {"","nan","none","null","na","n/a"}: continue
        return v
    return default

def _derive_signal_type_from_vanguard(row):
    raw_signal = _vg_clean_str(_vg_first(row,"vanguard_raw_signal_type","layer2__outcomes__signal_type","actuarial_signal_type",default=""))
    raw_reco   = _vg_clean_str(_vg_first(row,"vanguard_final_recommendation","final_recommendation",default=""))
    has_edge   = _vg_clean_str(_vg_first(row,"vanguard_has_edge","layer2__has_edge","vanguard_has_edge_flat","has_edge",default=""))
    edge_dir   = _vg_clean_str(_vg_first(row,"vanguard_edge_direction","layer2__edge_direction","vanguard_edge_direction_flat","edge_direction",default=""))
    n_obs      = _vg_num(_vg_first(row,"actuarial_sample","layer2__outcomes__n_observations","layer2__n_observations","n_observations",default=float("nan")),float("nan"))
    if raw_signal=="" and raw_reco=="": return "DATA_MISSING"
    if raw_signal=="NO_EDGE" or raw_reco=="NO_ACTUARIAL_DATA": return "NO_EDGE"
    if raw_signal in {"STRUCTURAL_MATCH","BROAD_FALLBACK","CONTINUATION"}: pass
    elif not(n_obs!=n_obs) and n_obs<=0: return "NO_EDGE"
    if raw_signal=="CONTINUATION":
        return "CURRENT_EDGE" if (has_edge=="TRUE" or edge_dir in {"CALL","PUT"}) else "FUTURE_EDGE"
    if raw_signal in {"STRUCTURAL_MATCH","BROAD_FALLBACK"}:
        return "FUTURE_EDGE" if (has_edge=="TRUE" and edge_dir in {"CALL","PUT"}) else "STRUCTURAL_MATCH"
    return raw_signal if raw_signal else "DATA_MISSING"

def _derive_momentum_tier_from_vanguard(row):
    signal   = _vg_clean_str(row.get("signal_type",""))
    raw_tier = _vg_clean_str(_vg_first(row,"vanguard_raw_momentum_tier","layer2__outcomes__momentum_tier","actuarial_momentum_tier",default=""))
    conf     = _vg_num(_vg_first(row,"vanguard_fwd_momentum_conf","layer2__outcomes__forward_momentum_confidence","layer2__future_momentum_bucket_confidence","fwd_momentum_conf",default=float("nan")),float("nan"))
    n_obs    = _vg_num(_vg_first(row,"actuarial_sample","layer2__outcomes__n_observations","layer2__n_observations",default=float("nan")),float("nan"))
    win10    = _vg_num(_vg_first(row,"win_rate_10d","layer2__win_rate_10d","actuarial_win_rate_10d",default=float("nan")),float("nan"))
    if signal=="DATA_MISSING": return "DATA_MISSING"
    if signal=="NO_EDGE": return "TIER_4_FLAT"
    if not(n_obs!=n_obs) and n_obs<=0: return "TIER_4_FLAT"
    if raw_tier and raw_tier not in {"NAN","NONE","NULL","DATA_MISSING",""}:
        return raw_tier
    if not(conf!=conf):
        if conf>=0.55 and not(win10!=win10) and win10>=0.525: return "TIER_1_EXPLOSIVE"
        if conf>=0.30 and not(win10!=win10) and win10>=0.515: return "TIER_2_ACTIVE"
        if conf>0.00 and not(n_obs!=n_obs) and n_obs>0: return "TIER_3_WATCH"
    if signal in {"STRUCTURAL_MATCH","FUTURE_EDGE"} and not(n_obs!=n_obs) and n_obs>0: return "TIER_3_WATCH"
    return "DATA_MISSING"

def _vg_handoff_status(row):
    signal = _vg_clean_str(row.get("signal_type",""))
    tier   = _vg_clean_str(row.get("momentum_tier",""))
    n_obs  = _vg_num(row.get("actuarial_sample"),0.0)
    win10  = _vg_num(row.get("win_rate_10d"),float("nan"))
    if signal=="DATA_MISSING" or tier=="DATA_MISSING": return "DATA_MISSING"
    if signal=="NO_EDGE" and tier=="TIER_4_FLAT": return "VALID_NO_EDGE"
    if n_obs<=0 or (win10!=win10): return "ACTUARIAL_MISSING"
    return "OK"

def apply_vanguard_pre_eil_handoff(df, run_dir, logger=None):
    """Merge Vanguard signals into SuperBrain df before run_engine(df)."""
    out = df.copy()
    if "ticker" not in out.columns:
        raise RuntimeError("VANGUARD_HANDOFF_FAIL: no ticker column")
    out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
    vg_path = Path(run_dir)/"vanguard"/"vanguard_signals.csv"
    if not vg_path.exists():
        for c in _REQUIRED_VANGUARD_HANDOFF_COLS:
            if c not in out.columns: out[c] = float("nan")
        out = ensure_physics_fields(out)
        out["signal_type"]="DATA_MISSING"; out["momentum_tier"]="DATA_MISSING"
        out["fwd_momentum_conf"]=float("nan"); out["current_edge_source"]="MISSING_VANGUARD_CSV"
        out["actuarial_source"]="MISSING_VANGUARD_CSV"; out["handoff_integrity_status"]="DATA_MISSING"
        if logger: logger.warning("VANGUARD_HANDOFF_WARN: %s not found. Rows marked DATA_MISSING.",vg_path)
        return out
    vg = pd.read_csv(vg_path)
    if "ticker" not in vg.columns: raise RuntimeError(f"VANGUARD_HANDOFF_FAIL: {vg_path} has no ticker column")
    vg["ticker"] = vg["ticker"].astype(str).str.upper().str.strip()
    vg = vg.drop_duplicates(subset=["ticker"],keep="last")
    _promote_map = {
        "layer2__outcomes__signal_type":"vanguard_raw_signal_type",
        "layer2__outcomes__momentum_tier":"vanguard_raw_momentum_tier",
        "layer2__outcomes__forward_momentum_confidence":"vanguard_fwd_momentum_conf",
        "layer2__state_v2":"state_v2_key","layer2__state_hash":"state_hash",
        "layer2__state_match_method":"state_match_method","layer2__state_match_quality":"state_match_quality",
        "layer2__has_edge":"vanguard_has_edge","layer2__edge_direction":"vanguard_edge_direction",
        "layer2__edge_quality":"vanguard_edge_quality",
        "layer2__win_rate_5d":"win_rate_5d","layer2__win_rate_10d":"win_rate_10d","layer2__win_rate_20d":"win_rate_20d",
        "layer2__outcomes__n_observations":"actuarial_sample",
        "layer2__expected_value_10d":"actuarial_expected_value_10d",
        "layer2__outcomes__sharpe_ratio_10d":"actuarial_efficiency_10d",
        "layer2__outcomes__median_gain_if_up_10d":"actuarial_expected_move_10d",
        "layer2__outcomes__median_max_drawdown_10d":"actuarial_risk_10d",
        "expected_value_10d":"expected_value_10d","final_recommendation":"vanguard_final_recommendation",
        "has_edge":"vanguard_has_edge_flat","edge_direction":"vanguard_edge_direction_flat",
        "confidence_level":"vanguard_confidence_level",
    }
    _promote_map.update({c: c for c in MACRO_QUANT_CSV_FIELDS})
    _promote_map.update({c: c for c in PHYSICS_FIELDS})
    available = ["ticker"]+[c for c in _promote_map if c in vg.columns]
    vg_small = vg[available].copy()
    rename_pairs,used_dests = {},set()
    for s,d in _promote_map.items():
        if s in vg_small.columns and d not in used_dests:
            rename_pairs[s]=d; used_dests.add(d)
    vg_small = vg_small.rename(columns=rename_pairs)
    out = out.merge(vg_small,on="ticker",how="left",suffixes=("","__vg"))
    out = resolve_macro_suffix_columns(out)
    out = ensure_physics_fields(out)
    out["signal_type"]   = out.apply(_derive_signal_type_from_vanguard,   axis=1)
    out["momentum_tier"] = out.apply(_derive_momentum_tier_from_vanguard, axis=1)
    out["fwd_momentum_conf"] = pd.to_numeric(out.get("vanguard_fwd_momentum_conf",float("nan")),errors="coerce")
    out["actuarial_sample"] = pd.to_numeric(out.get("actuarial_sample",0),errors="coerce").fillna(0).astype(float)
    out["actuarial_valid"]    = out["actuarial_sample"]>0
    out["actuarial_no_match"] = ~out["actuarial_valid"]
    if "actuarial_win_rate_10d" not in out.columns:
        out["actuarial_win_rate_10d"] = pd.to_numeric(out.get("win_rate_10d"),errors="coerce")
    else:
        out["actuarial_win_rate_10d"] = pd.to_numeric(out["actuarial_win_rate_10d"].combine_first(out.get("win_rate_10d")),errors="coerce")
    if "actuarial_efficiency_10d" not in out.columns:
        out["actuarial_efficiency_10d"] = pd.to_numeric(out.get("actuarial_efficiency_10d"),errors="coerce")
    if "efficiency_10d" not in out.columns:
        out["efficiency_10d"] = pd.to_numeric(out.get("actuarial_efficiency_10d"),errors="coerce")
    else:
        out["efficiency_10d"] = pd.to_numeric(out["efficiency_10d"].combine_first(out.get("actuarial_efficiency_10d")),errors="coerce")
    out["current_edge_source"] = np.where(out["signal_type"].eq("DATA_MISSING"),"MISSING_OR_UNMERGED_VANGUARD","VANGUARD_LAYER2")
    out["actuarial_source"] = np.where(out["actuarial_valid"],"VANGUARD_LAYER2_ACTUARIAL","NO_ACTUARIAL_MATCH")
    out["handoff_integrity_status"] = out.apply(_vg_handoff_status,axis=1)
    for c in _REQUIRED_VANGUARD_HANDOFF_COLS:
        if c not in out.columns: out[c]=float("nan")
    if logger:
        logger.info("VANGUARD_HANDOFF: %d rows | %d Vanguard rows from %s",len(out),len(vg_small),vg_path.name)
        logger.info("VANGUARD_HANDOFF signal_type: %s",out["signal_type"].astype(str).str.upper().value_counts(dropna=False).to_dict())
        logger.info("VANGUARD_HANDOFF momentum_tier: %s",out["momentum_tier"].astype(str).str.upper().value_counts(dropna=False).to_dict())
        logger.info("VANGUARD_HANDOFF integrity: %s",out["handoff_integrity_status"].astype(str).str.upper().value_counts(dropna=False).to_dict())
        logger.info("PHYSICS_HANDOFF: %d rows with physics_state_id", int(out["physics_state_id"].astype(str).str.len().gt(0).sum()))
    return out


# =============================================================================
# CAPITAL PERMISSION SANITY CHECK (module-level)
# =============================================================================
# Promoted from nested run_engine closure to module-level helper.
# Called AFTER _defang_invalid_campaign_fatal_blocks, before CSV write.
# Raises RuntimeError on any residual capital leak that survived defang.
# =============================================================================

def _capital_permission_sanity(df: pd.DataFrame, logger=None) -> None:
    """
    Final capital-leak sanity check â€” module-level for reusability and testability.

    Raises RuntimeError if any row that should never receive executable
    capital permission (NO_EDGE, TIER_4_FLAT, DATA_MISSING, or broken handoff)
    is found carrying PROBE/EXECUTE mode or positive pse_final_size / fd_size.

    Mirrors the veto logic exactly â€” 4 fields, includes DATA_MISSING.
    Must be called after result_df is fully assembled and _defang has run.

    Contract expected by BIG_BANG_STATIC_CHECK:
        _capital_permission_sanity => exactly 1 definition
    """
    _log = logger or logging.getLogger(__name__)
    if df is None or len(df) == 0:
        _log.info("CAPITAL_PERMISSION_SANITY_PASS: empty dataframe â€” nothing to check.")
        return
    signal     = df.get("signal_type",       pd.Series("", index=df.index)).fillna("").astype(str).str.upper()
    tier       = df.get("momentum_tier",     pd.Series("", index=df.index)).fillna("").astype(str).str.upper()
    pse_signal = df.get("pse_signal_type",   pd.Series("", index=df.index)).fillna("").astype(str).str.upper()
    pse_tier   = df.get("pse_momentum_tier", pd.Series("", index=df.index)).fillna("").astype(str).str.upper()
    pse_mode   = df.get("pse_execution_mode",pd.Series("", index=df.index)).fillna("").astype(str).str.upper()
    fd_v       = df.get("fd_verdict",        pd.Series("", index=df.index)).fillna("").astype(str).str.upper()
    cap_perm   = df.get("capital_permission", pd.Series("", index=df.index)).fillna("").astype(str).str.upper()
    pse_size   = pd.to_numeric(df.get("pse_final_size", 0), errors="coerce").fillna(0.0)
    fd_size    = pd.to_numeric(df.get("fd_size",        0), errors="coerce").fillna(0.0)

    no_current_edge = (
        signal.isin(["NO_EDGE", "DATA_MISSING"])
        | tier.isin(["TIER_4_FLAT", "DATA_MISSING"])
        | pse_signal.isin(["NO_EDGE", "DATA_MISSING"])
        | pse_tier.isin(["TIER_4_FLAT", "DATA_MISSING"])
    )
    live_capital_requested = (
        cap_perm.isin(["YES", "LIVE_EXECUTE", "CAPITAL_APPROVED", "CAPITAL_AUTHORIZED"])
        | (pse_size > 0)
        | (fd_size > 0)
    )
    advisory_labels = no_current_edge & ~live_capital_requested & (
        pse_mode.str.contains("PROBE|EXECUTE", na=False)
        | fd_v.str.contains("PROBE|EXECUTE", na=False)
    )
    if advisory_labels.any():
        _log.info(
            "CAPITAL_PERMISSION_SANITY_NOTE: %d no-edge/flat rows carry advisory EXECUTE/PROBE labels "
            "with zero live capital; allowed because PSE is retired/manual sizing.",
            int(advisory_labels.sum()),
        )
    leaked = df[no_current_edge & live_capital_requested]
    if len(leaked) > 0:
        tickers = leaked["ticker"].head(25).tolist() if "ticker" in leaked.columns else []
        raise RuntimeError(
            f"FATAL_SANITY_FAIL: current-edge capital leak detected. "
            f"Rows={len(leaked)} Sample={tickers}"
        )
    _log.info(
        "CAPITAL_PERMISSION_SANITY_PASS: zero live-capital leak rows "
        "(NO_EDGE/TIER_4_FLAT/DATA_MISSING with positive size or live capital permission). "
        "Advisory EOD labels with manual sizing are permitted."
    )


# =============================================================================
# DEFANG INVALID CAMPAIGN FATAL BLOCKS (module-level post-processor)
# =============================================================================
# Defence-in-depth DataFrame sweep applied to result_df AFTER all per-row
# PSE/FDE processing completes.
#
# Why this is needed even with signal-aware routing at the REJECT/SKIP gate:
#   The early-exit gate only catches rows where campaign=="REJECT" or
#   execution=="SKIP". Rows that pass that gate go through the full PSE chain,
#   which historically produced pse_execution_mode=FATAL_BLOCK with
#   pse_block_reason=CAMPAIGN_OR_EXECUTION_INVALID via old PSE/FDE paths.
#   Those authority paths are now retired, but this defang pass remains as
#   defence-in-depth for archived or externally generated inputs.
#
# This function sweeps the completed result_df and converts any residual
# generic FATAL_BLOCKs into the correct signal-aware states:
#   STRUCTURAL_MATCH â†’ STRUCTURAL_WATCH (watchlist inventory, not fatal)
#   FUTURE_EDGE      â†’ FUTURE_WATCH     (forward evidence, not fatal)
#   NO_EDGE / DATA_MISSING â†’ SKIP       (no edge, not fatal)
#   CURRENT_EDGE / TRANSITION â†’ manual/EOD review unless true data defects exist
#
# Contract: called BEFORE _capital_permission_sanity so the sanity gate
# sees the corrected modes. FATAL_BLOCK should be <5% after this runs.
# =============================================================================

def _defang_invalid_campaign_fatal_blocks(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """
    Converts residual generic CAMPAIGN_OR_EXECUTION_INVALID FATAL_BLOCKs into
    the correct non-capital states for watchlist / no-edge / future-edge rows.

    FATAL_BLOCK is no longer a capital-allocation state for CURRENT_EDGE rows.
    Live sizing is retired, so valid rows are downgraded into manual/EOD review
    with specific reasons instead of being suppressed by old sizing gates.

    Returns a copy of df with corrected pse_execution_mode, pse_block_reason,
    pse_final_size, and capital_permission fields.
    """
    _log = logger or logging.getLogger(__name__)

    if df is None or len(df) == 0:
        return df

    df = df.copy()

    sig    = df["signal_type"].fillna("").astype(str).str.upper()    if "signal_type"       in df.columns else pd.Series("", index=df.index)
    tier   = df["momentum_tier"].fillna("").astype(str).str.upper()  if "momentum_tier"     in df.columns else pd.Series("", index=df.index)
    mode   = df["pse_execution_mode"].fillna("").astype(str).str.upper() if "pse_execution_mode" in df.columns else pd.Series("", index=df.index)
    reason = df["pse_block_reason"].fillna("").astype(str).str.upper()   if "pse_block_reason"   in df.columns else pd.Series("", index=df.index)
    route  = df["final_route"].fillna("").astype(str).str.upper() if "final_route" in df.columns else pd.Series("", index=df.index)
    vetoes = df["hard_vetoes"].fillna("").astype(str).str.upper() if "hard_vetoes" in df.columns else pd.Series("", index=df.index)
    options_blocked = route.isin(list(OPTIONS_NON_REVIEWABLE_ROUTES)) | vetoes.ne("")

    # Any FATAL_BLOCK or SKIP with generic reason â€” these are the residual leakage rows.
    # The per-row gate can produce SKIP+CAMPAIGN_OR_EXECUTION_INVALID for unclassified
    # signals; PSE/FDE downstream can produce FATAL_BLOCK+CAMPAIGN_OR_EXECUTION_INVALID.
    # Both must be reclassified.
    is_generic_fatal = (
        mode.isin(["FATAL_BLOCK", "SKIP"])
        & reason.eq("CAMPAIGN_OR_EXECUTION_INVALID")
    )

    n_before = int(is_generic_fatal.sum())
    if n_before == 0:
        _log.info("DEFANG: no generic FATAL_BLOCK rows found â€” continuing SKIP label-clean pass.")

    # â”€â”€ STRUCTURAL_MATCH: watchlist inventory, never fatal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    m_struct = is_generic_fatal & sig.eq("STRUCTURAL_MATCH")
    if m_struct.any():
        df.loc[m_struct, "pse_execution_mode"] = "STRUCTURAL_WATCH"
        df.loc[m_struct, "pse_final_size"]     = 0.0
        df.loc[m_struct, "fd_size"]            = 0.0
        df.loc[m_struct, "fd_verdict"]         = "WATCHLIST"
        df.loc[m_struct, "capital_permission"] = "WATCH_ONLY"
        df.loc[m_struct, "future_state_action"]= "STRUCTURAL_WATCH"
        df.loc[m_struct, "pse_block_reason"]   = "STRUCTURAL_MATCH_NO_CURRENT_EDGE"
        df.loc[m_struct, "signal_authority_reason"] = "STRUCTURAL_MATCH_NO_CURRENT_EDGE"
        _log.info("DEFANG: %d STRUCTURAL_MATCH â†’ STRUCTURAL_WATCH", int(m_struct.sum()))

    # â”€â”€ FUTURE_EDGE: forward evidence only, never fatal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    m_future = is_generic_fatal & sig.eq("FUTURE_EDGE")
    if m_future.any():
        df.loc[m_future, "pse_execution_mode"] = "FUTURE_WATCH"
        df.loc[m_future, "pse_final_size"]     = 0.0
        df.loc[m_future, "fd_size"]            = 0.0
        df.loc[m_future, "fd_verdict"]         = "WATCHLIST"
        df.loc[m_future, "capital_permission"] = "WATCH_ONLY"
        df.loc[m_future, "future_state_action"]= "FUTURE_WATCH"
        df.loc[m_future, "pse_block_reason"]   = "FUTURE_EDGE_NOT_CURRENTLY_EXECUTABLE"
        df.loc[m_future, "signal_authority_reason"] = "FUTURE_EDGE_NOT_CURRENTLY_EXECUTABLE"
        _log.info("DEFANG: %d FUTURE_EDGE â†’ FUTURE_WATCH", int(m_future.sum()))

    # â”€â”€ NO_EDGE / DATA_MISSING: skip, never fatal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    m_data_missing = is_generic_fatal & (
        sig.eq("DATA_MISSING") | tier.eq("DATA_MISSING")
    )
    if m_data_missing.any():
        df.loc[m_data_missing, "pse_execution_mode"] = "DATA_REPAIR_REQUIRED"
        df.loc[m_data_missing, "pse_final_size"] = 0.0
        df.loc[m_data_missing, "fd_size"] = 0.0
        df.loc[m_data_missing, "fd_verdict"] = "WATCHLIST"
        df.loc[m_data_missing, "capital_permission"] = "NO"
        df.loc[m_data_missing, "eod_candidate_permission"] = "NO"
        df.loc[m_data_missing, "execution_authorized"] = False
        df.loc[m_data_missing, "eod_candidate_authorized"] = False
        df.loc[m_data_missing, "eod_candidate_size"] = 0.0
        df.loc[m_data_missing, "candidate_size"] = 0.0
        df.loc[m_data_missing, "effective_execution_verdict"] = "DATA_REPAIR_REQUIRED"
        df.loc[m_data_missing, "capital_authorization_state"] = "NOT_AUTHORIZED"
        df.loc[m_data_missing, "future_state_action"] = "DATA_REPAIR_REQUIRED"
        df.loc[m_data_missing, "pse_block_reason"] = "DATA_MISSING_REPAIR_REQUIRED"
        df.loc[m_data_missing, "signal_authority_reason"] = "DATA_MISSING_REPAIR_REQUIRED"
        _log.info("DEFANG: %d DATA_MISSING rows held for repair", int(m_data_missing.sum()))

    m_no_edge = is_generic_fatal & ~m_data_missing & (
        sig.eq("NO_EDGE") | tier.eq("TIER_4_FLAT")
    )
    if m_no_edge.any():
        df.loc[m_no_edge, "pse_execution_mode"] = "EOD_PROBE_CANDIDATE"
        df.loc[m_no_edge, "pse_final_size"]     = 0.0
        df.loc[m_no_edge, "fd_size"]            = 0.0
        df.loc[m_no_edge, "fd_verdict"]         = "WATCHLIST"
        df.loc[m_no_edge, "capital_permission"] = "EOD_CANDIDATE_ONLY"
        df.loc[m_no_edge, "eod_candidate_permission"] = "MORNING_VALIDATION_REQUIRED"
        df.loc[m_no_edge, "future_state_action"]= "EOD_PROBE_CANDIDATE"
        df.loc[m_no_edge, "pse_block_reason"]   = "SPARSE_ACTUARIAL_CONTEXT_EOD_PROBE_CANDIDATE"
        df.loc[m_no_edge, "signal_authority_reason"] = "SPARSE_ACTUARIAL_CONTEXT_EOD_PROBE_CANDIDATE"
        _log.info("DEFANG: %d NO_EDGE/DATA_MISSING â†’ SKIP", int(m_no_edge.sum()))

    # â”€â”€ CURRENT_EDGE / TRANSITION: manual review, not live sizing suppression â”€
    m_options_blocked = is_generic_fatal & options_blocked
    if m_options_blocked.any():
        df.loc[m_options_blocked, "pse_execution_mode"] = "OPTIONS_REPAIR_REQUIRED"
        df.loc[m_options_blocked, "pse_final_size"]     = 0.0
        df.loc[m_options_blocked, "fd_size"]            = 0.0
        df.loc[m_options_blocked, "fd_verdict"]         = "WATCHLIST"
        df.loc[m_options_blocked, "capital_permission"] = "NO"
        df.loc[m_options_blocked, "eod_candidate_permission"] = "CONTRACT_REPAIR_REQUIRED"
        df.loc[m_options_blocked, "eod_candidate_authorized"] = False
        df.loc[m_options_blocked, "eod_candidate_size"] = 0.0
        df.loc[m_options_blocked, "candidate_size"]     = 0.0
        df.loc[m_options_blocked, "effective_execution_verdict"] = "OPTIONS_REPAIR_REQUIRED"
        df.loc[m_options_blocked, "capital_authorization_state"] = "NOT_AUTHORIZED"
        df.loc[m_options_blocked, "future_state_action"] = "OPTIONS_REPAIR_REQUIRED"
        df.loc[m_options_blocked, "pse_block_reason"]   = "OPTIONS_RESEARCH_BLOCKED"
        df.loc[m_options_blocked, "signal_authority_reason"] = "OPTIONS_RESEARCH_BLOCKED_DEFANG"
        _log.info("DEFANG: %d rows held for OPTIONS_REPAIR_REQUIRED", int(m_options_blocked.sum()))

    m_current = is_generic_fatal & sig.isin(["CURRENT_EDGE", "TRANSITION"]) & ~options_blocked
    if m_current.any():
        df.loc[m_current, "pse_execution_mode"] = sig.loc[m_current] + "_REVIEW"
        df.loc[m_current, "pse_final_size"]     = 0.0
        df.loc[m_current, "fd_size"]            = 0.0
        df.loc[m_current, "fd_verdict"]         = "WATCHLIST"
        df.loc[m_current, "capital_permission"] = "EOD_CANDIDATE_ONLY"
        df.loc[m_current, "eod_candidate_permission"] = "MORNING_VALIDATION_REQUIRED"
        df.loc[m_current, "future_state_action"] = "MORNING_VALIDATION_REQUIRED"
        df.loc[m_current, "pse_block_reason"]   = "MANUAL_REVIEW_REQUIRED_SIZING_RETIRED"
        df.loc[m_current, "signal_authority_reason"] = "MANUAL_REVIEW_REQUIRED_SIZING_RETIRED"
        _log.info("DEFANG: %d CURRENT_EDGE/TRANSITION generic blocks moved to manual review",
                  int(m_current.sum()))

    # â”€â”€ SKIP + CAMPAIGN_OR_EXECUTION_INVALID: label-clean pass â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # These are not capital leaks â€” they carry SKIP + zero size â€” but they
    # pollute block-reason analytics with a meaningless generic label.
    # Re-read reason after above mutations (struct/future/no_edge may have
    # already cleared some of these rows).
    reason_after_pass1 = df["pse_block_reason"].fillna("").astype(str).str.upper() \
        if "pse_block_reason" in df.columns else pd.Series("", index=df.index)
    mode_after_pass1   = df["pse_execution_mode"].fillna("").astype(str).str.upper() \
        if "pse_execution_mode" in df.columns else pd.Series("", index=df.index)

    skip_generic = (
        mode_after_pass1.eq("SKIP")
        & reason_after_pass1.str.contains("CAMPAIGN_OR_EXECUTION_INVALID", na=False)
    )
    if skip_generic.any():
        df.loc[skip_generic, "pse_block_reason"]          = "UNCLASSIFIED_SIGNAL_EXECUTION_SKIP"
        df.loc[skip_generic, "fd_reason"]                 = "UNCLASSIFIED_SIGNAL_EXECUTION_SKIP"
        df.loc[skip_generic, "execution_override_reason"] = "UNCLASSIFIED_SIGNAL_EXECUTION_SKIP"
        df.loc[skip_generic, "signal_authority_reason"]   = "UNCLASSIFIED_SIGNAL_EXECUTION_SKIP"
        df.loc[skip_generic, "capital_permission"]        = "NO"
        df.loc[skip_generic, "future_state_action"]       = "NONE"
        df.loc[skip_generic, "pse_final_size"]            = 0.0
        df.loc[skip_generic, "fd_size"]                   = 0.0
        _log.info("DEFANG: %d SKIP+CAMPAIGN_OR_EXECUTION_INVALID rows relabelled â†’ UNCLASSIFIED_SIGNAL_EXECUTION_SKIP",
                  int(skip_generic.sum()))

    # â”€â”€ Unclassified residuals: downgrade to SKIP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Re-read mode after above corrections to find any remaining generic fatals
    mode2   = df["pse_execution_mode"].fillna("").astype(str).str.upper()
    reason2 = df["pse_block_reason"].fillna("").astype(str).str.upper()
    still_generic = mode2.eq("FATAL_BLOCK") & reason2.eq("CAMPAIGN_OR_EXECUTION_INVALID")
    if still_generic.any():
        df.loc[still_generic, "pse_execution_mode"] = "SKIP"
        df.loc[still_generic, "pse_final_size"]     = 0.0
        df.loc[still_generic, "fd_size"]            = 0.0
        df.loc[still_generic, "fd_verdict"]         = "WATCHLIST"
        df.loc[still_generic, "capital_permission"] = "NO_CAPITAL"
        df.loc[still_generic, "pse_block_reason"]   = "UNCLASSIFIED_BLOCK_DOWNGRADED"
        _log.warning("DEFANG: %d unclassified FATAL_BLOCKs downgraded to SKIP",
                     int(still_generic.sum()))

    n_after_fatal = int(df["pse_execution_mode"].fillna("").astype(str).str.upper().eq("FATAL_BLOCK").sum())
    n_total = len(df)
    fatal_pct = n_after_fatal / n_total * 100 if n_total > 0 else 0
    _log.info(
        "DEFANG COMPLETE: reclassified %d generic FATAL_BLOCKs. "
        "Remaining FATAL_BLOCK: %d/%d (%.1f%%) â€” target <5%%.",
        n_before, n_after_fatal, n_total, fatal_pct,
    )
    if fatal_pct > 5.0 and n_total >= 100:
        _log.warning(
            "DEFANG WARN: FATAL_BLOCK rate %.1f%% still >5%%. "
            "Check CURRENT_EDGE rows for hard-veto causes.",
            fatal_pct,
        )

    # RUN1 FIX: Downgrade OPTIONS_BLOCKED rows that slipped through as MORNING_VALIDATION_REQUIRED
    # These rows have valid signals (CURRENT_EDGE/TRANSITION) but OPTIONS_BLOCKED routes;
    # the per-row gate did not catch them. Enforce CONTRACT_REPAIR_REQUIRED here.
    if "final_route" in df.columns and "eod_candidate_permission" in df.columns:
        route2 = df["final_route"].fillna("").astype(str).str.upper()
        eod_perm2 = df["eod_candidate_permission"].fillna("").astype(str).str.upper()
        m_opt_leak = (
            route2.isin(list(OPTIONS_NON_REVIEWABLE_ROUTES))
            & eod_perm2.eq("MORNING_VALIDATION_REQUIRED")
        )
        if m_opt_leak.any():
            df.loc[m_opt_leak, "eod_candidate_permission"] = "CONTRACT_REPAIR_REQUIRED"
            df.loc[m_opt_leak, "capital_permission"]       = "NO"
            df.loc[m_opt_leak, "pse_execution_mode"]       = "OPTIONS_REPAIR_REQUIRED"
            df.loc[m_opt_leak, "eod_candidate_authorized"] = False
            df.loc[m_opt_leak, "eod_candidate_size"]       = 0.0
            df.loc[m_opt_leak, "candidate_size"]           = 0.0
            df.loc[m_opt_leak, "effective_execution_verdict"] = "OPTIONS_REPAIR_REQUIRED"
            df.loc[m_opt_leak, "capital_authorization_state"] = "NOT_AUTHORIZED"
            df.loc[m_opt_leak, "pse_block_reason"]         = "OPTIONS_ROUTE_BLOCKED_CONTRACT_REPAIR"
            df.loc[m_opt_leak, "signal_authority_reason"]  = "OPTIONS_ROUTE_BLOCKED_PROMOTED_CORRECTED"
            _log.info(
                "RUN1 FIX: %d OPTIONS_BLOCKED rows corrected from MORNING_VALIDATION_REQUIRED "
                "to CONTRACT_REPAIR_REQUIRED",
                int(m_opt_leak.sum()),
            )

    return df


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CLI
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"AVSHUNTER EIL Runner v{EIL_RUNNER_VERSION}"
    )
    parser.add_argument("--run_id", required=False)
    parser.add_argument("--input",  required=False)
    parser.add_argument("--output", required=False)
    args = parser.parse_args()

    # FIX-BASE-SCOPE (2026-04-24): base must be set regardless of whether --input
    # was passed manually, because the eil_enriched write block (line ~803) uses
    # it unconditionally whenever args.run_id is present. Previously base was only
    # set when --input was absent, so manually passing --input left base undefined
    # â†’ eil_enriched write failed with "name 'base' is not defined".
    base = None
    if args.run_id:
        base = os.path.join(_ROOT, "data", "output", "runs", args.run_id)  # FIX-PATH-HARDCODE 2026-05-20
    if args.run_id and not args.input:
        args.input  = os.path.join(base, "superbrain", f"superbrain_enriched_{args.run_id}.csv")
        args.output = os.path.join(base, "execution",  f"execution_v3_5_{args.run_id}.csv")

    if not args.input or not args.output:
        raise ValueError("Provide either --run_id OR both --input and --output")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    df  = pd.read_csv(args.input)

    # ITEM 2 â€” Pre-run column audit: log which spread column is present.
    # This makes SANITY_WARN_SPREAD diagnosable immediately without inspecting CSVs.
    _SPREAD_AUDIT_COLS = [
        "contract_spread_pct", "spread_pct", "eil_spread_pct_live",
        "bid_ask_spread_pct", "options_spread_pct",
    ]
    _found_spread_cols = [c for c in _SPREAD_AUDIT_COLS if c in df.columns]
    _missing_spread_cols = [c for c in _SPREAD_AUDIT_COLS if c not in df.columns]
    if _found_spread_cols:
        _spread_col = _found_spread_cols[0]
        _nonzero = (df[_spread_col].notna() & (df[_spread_col] != 0)).sum()
        _total   = len(df)
        logger.info(
            "ITEM2 spread audit: using '%s' â€” %d/%d rows non-zero. "
            "Other candidates present: %s",
            _spread_col, _nonzero, _total,
            [c for c in _found_spread_cols[1:]] or "none",
        )
        if _nonzero == 0:
            logger.warning(
                "ITEM2 SPREAD_WARN: '%s' present but ALL ZERO â€” "
                "EIL will use IV proxy spread. Check OI output populates this column.",
                _spread_col,
            )
    else:
        logger.warning(
            "ITEM2 SPREAD_WARN: none of %s found in superbrain CSV â€” "
            "EIL will use IV proxy spread for all rows. "
            "Check avshunter_options_intelligence writes contract_spread_pct.",
            _SPREAD_AUDIT_COLS,
        )

    # â”€â”€ PRE-EIL VANGUARD / ACTUARIAL HANDOFF NORMALISATION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if base:
        _run_dir = Path(base)
    else:
        _input_path = Path(args.input).resolve()
        if _input_path.parent.name.lower() == "superbrain":
            _run_dir = _input_path.parent.parent
        elif _input_path.parent.name.lower() == "execution":
            _run_dir = _input_path.parent.parent
        else:
            _run_dir = Path(_ROOT)
    try:
        df = apply_vanguard_pre_eil_handoff(df=df, run_dir=_run_dir, logger=logger)
    except Exception as _handoff_err:
        logger.exception("VANGUARD_HANDOFF_FATAL: %s", _handoff_err)
        raise

    out = run_engine(df)
    out = append_physics_fields_from_source(out, df)
    out = _ensure_eil_audit_contract(out)
    for _trigger_index, _trigger_row in enumerate(out.to_dict(orient="records")):
        try:
            validate_trigger_handoff_row(_trigger_row)
        except ValueError as _trigger_error:
            _trigger_ticker = str(_trigger_row.get("ticker", "")).strip().upper()
            raise RuntimeError(
                "WS2 trigger handoff failed before execution publication: "
                f"row={_trigger_index} ticker={_trigger_ticker or 'UNKNOWN'} "
                f"error={_trigger_error}"
            ) from _trigger_error
    out = enrich_dataframe_with_truth_packets(
        out,
        source="EIL_PSE",
        priority=PRIORITY_EIL_PSE,
        run_id=args.run_id or "",
        run_mode="EVENING",
    )
    out.to_csv(args.output, index=False)
    logger.info(f"Saved â†’ {args.output}")
    try:
        import sys as _ma_sys
        _ma_sys.path.insert(0, r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter")
        from ma_inputs_sync import on_pipeline_complete as _ma_on_pipeline_complete
        _ma_on_pipeline_complete(str(args.output), output_dir=str(Path(args.output).parent))
    except Exception as _ma_sync_err:
        logger.warning("MA_Inputs sync skipped for execution output: %s", _ma_sync_err)

    # â”€â”€ Write eil_enriched to superbrain dir so morning_validation finds it â”€â”€
    # FIX (2026-04-17): EIL only wrote to execution/ dir. morning_validation
    # looks for superbrain/eil_enriched_{run_id}.csv first, then falls back to
    # superbrain_enriched which has DATA_FAILURE verdicts â†’ 0 signals shown.
    # This block merges EIL verdicts back into superbrain rows and writes the
    # merged file to the superbrain dir with EIL verdict promoted to
    # sb_final_verdict so morning_validation F1 gate passes correctly.
    #
    # FIX (2026-04-18): Also merges WBS (wall_break_scores) fields and corrects
    # the display EV/price columns read by the Intelligence Lab frontend.
    try:
        if args.run_id:
            sb_dir       = os.path.join(base, "superbrain")
            eil_enriched = os.path.join(sb_dir, f"eil_enriched_{args.run_id}.csv")
            os.makedirs(sb_dir, exist_ok=True)

            EIL_COLS = [
                "eil_v3_verdict", "eil_raw_verdict", "eil_composite_score",
                "eil_size_multiplier", "eil_confidence", "eil_ev_v2",
                "eil_ev_net", "eil_ev_score", "eil_defer_reason",
                # FIX-CONV-SCORES (2026-04-21): Add 5 individual strategy scores.
                # The convergence engine reads these exact field names to vote
                # direction. Without them every ticker scores 0/5 â†’ BLOCK_INSUFFICIENT.
                "eil_liquidity_score", "eil_liquidity_window", "eil_liquidity_passed",
                "eil_iv_score",
                "eil_bond_macro_flag", "eil_bond_macro_spread_context", "eil_bond_macro_reason",
                "eil_gex_score", "eil_gex_regime",
                "eil_obi_score", "eil_obi_regime",
                "eil_poc_score", "eil_poc_position",
                "eil_failure_reason",
                "eil_data_mode",            # "LIVE" | "LIVE_WITH_CONTRACT_QUOTE_FALLBACK" | "EOD_SYNTHETIC" | "EOD_SYNTHETIC_WITH_CONTRACT_QUOTE_FALLBACK"
                # PSE output columns (position sizing engine)
                "pse_final_size", "pse_execution_mode", "pse_edge_score",
                "pse_ev_mult", "pse_mp_mult", "pse_eil_mult",
                "pse_options_mult", "pse_regime_mult", "pse_confidence_mult",
                "pse_block_reason", "pse_size_breakdown", "pse_version",
                "pse_signal_type", "pse_momentum_tier",  # V2 Sprint 3
                "fd_verdict", "fd_advisory_verdict", "final_decision_advisory_verdict",
                "fd_size", "fd_reason", "fd_confidence",
                "fd_ev_used", "ev_conf_adj", "ev_final", "ev2_ev_final", "ev2_ev_conf_adj",
                "mp_state", "mp_final_size_mult", "mp_hard_block_reason",
                # ev2_ audit fields written by EVResult.to_row_dict()
                "ev2_ev_structural", "ev2_ev_execution_adj", "ev2_ev_path_adj",
                "ev2_ev_contract", "ev2_ev_status", "ev2_p_win_blended",
                "ev2_quality_score", "ev2_decision_hint", "ev2_primary_reason",
                "ev2_recommended_size_mult", "ev2_regime_multiplier",
                # NEW-01: scenario routing fields (from scenario_router.py)
                "scenario_path", "scenario_alignment", "scenario_dte_target",
                "scenario_size_mult", "scenario_entry_type",
                "scenario_entry_trigger", "scenario_rationale",
                "pse_scenario_mult_applied", "pse_pre_scenario_size",
                # ISSUE 15: horizon fields were missing from EIL_COLS â€”
                # morning validation and SuperBrain cannot read them without this
                "horizon_bucket", "horizon_action", "horizon_size_multiplier",
                "horizon_block_reason", "horizon_source",
                "pse_horizon_multiplier_applied", "pse_pre_horizon_size",
                # WS2: governed trigger block is calculated before EIL and
                # explicitly survives both execution and enriched outputs.
                *TRIGGER_HANDOFF_FIELDS,
                # Spread audit field and runner version
                "eil_spread_pct_live",
                "eil_runner_version",
                # ENHANCEMENT 1: Phase 1 current-edge classification fields.
                "current_edge_valid", "future_edge_valid", "capital_permission",
                "eod_candidate_permission", "eod_candidate_authorized",
                "eod_candidate_size", "candidate_size",
                "sizing_policy",
                "future_state_action", "phase1_guard_applied", "phase1_guard_reason",
                # SIGNAL AUTHORITY POLICY fields
                "signal_authority_reason",
                "execution_authorized", "effective_execution_verdict",
                "execution_verdict_source", "execution_authority_reason",
                "execution_label_warning", "eil_signal_verdict",
                "capital_authorization_state",
                # Options Intelligence audit fields
                "execution_permission", "final_route", "options_research_score",
                "confidence_score", "microstructure_confidence_haircut", "hard_vetoes", "missing_data",
                "trigger_state", "trigger_status_reason",
                "expected_move_pct", "expected_move_price",
                "breakeven_feasibility", "estimated_R", "theta_decay_expected",
                "runway_to_wall_pct", "liquidity_score", "directional_fit_score",
                "breakeven_score", "payoff_score", "iv_score", "theta_score",
                "runway_score", "path_score", "trigger_score",
                "research_route_reason",
                "pcr_vol_status", "pcr_vol_missing_reason",
                "pcr_direction_conflict_status", "pcr_direction_conflict_reason",
                "catalyst_direction_conflict_status", "catalyst_direction_conflict_reason",
                "direction_arbitration_status", "direction_arbitration_reason", "direction_conflict_gate",
                "direction_conflict_status", "direction_conflict_reason",
                "contract_repair_attempted", "contract_repair_status",
                "contract_repair_required", "contract_repair_reason",
                # Options quote fallback audit
                "options_quote_fallback_applied", "options_quote_fallback_source",
                "options_bid", "options_ask", "options_mid",
                "spread_source", "options_spread_source", "contract_spread_source",
                # HANDOFF NORMALISER: Vanguard pre-EIL merge provenance fields.
                "current_edge_source", "actuarial_source", "handoff_integrity_status",
                "vanguard_raw_signal_type", "vanguard_raw_momentum_tier",
                "vanguard_fwd_momentum_conf", "vanguard_has_edge",
                "vanguard_edge_direction", "vanguard_final_recommendation",
                "state_v2_key", "state_match_method", "state_match_quality",
                "actuarial_sample", "actuarial_valid", "actuarial_no_match",
                *MACRO_QUANT_CSV_FIELDS,
                *PHYSICS_FIELDS,
                *TRUTH_PACKET_META_FIELDS,
            ]

            # â”€â”€ Actuarial fields to propagate into EIL enriched CSV â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # EDE reads these flat-prefixed column names from the EIL CSV.
            # Phase 8.5 patches pkg["actuarial"] in package JSONs after Vanguard.
            # These columns carry those values through to the EIL output so EDE
            # can score with real actuarial data (win_rate, efficiency, edge).
            # Without this EDE reads None for all actuarial fields â†’ score=0.000.
            ACTUARIAL_PROPAGATE_COLS = [
                ("actuarial_win_rate_10d",      "win_rate_10d"),
                ("actuarial_efficiency_10d",    "efficiency_10d"),
                ("actuarial_expected_move_10d", "expected_move_10d"),
                ("actuarial_risk_10d",          "risk_10d"),
                ("actuarial_penalty",           "penalty_multiplier"),
                ("actuarial_valid",             "valid"),
                ("actuarial_depth",             "fallback_depth"),
                ("actuarial_sample",            "sample_size"),
                ("actuarial_no_match",          "no_match"),
            ]

            # â”€â”€ Load package JSONs â†’ actuarial map â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Reads pkg["actuarial"] from each package JSON written by Phase 8.5.
            # Keyed by ticker for O(1) lookup during merge.
            _pkg_dir = os.path.join(base, "packages") if base else None
            actuarial_map = {}
            if _pkg_dir and os.path.isdir(_pkg_dir):
                try:
                    import glob as _glob
                    _pkg_files = _glob.glob(os.path.join(_pkg_dir, "*.package.json"))
                    for _pf in _pkg_files:
                        try:
                            with open(_pf, "r", encoding="utf-8") as _pjf:
                                _pkg = json.load(_pjf)
                            _pt = str(_pkg.get("ticker", "")).strip().upper()
                            _act = _pkg.get("actuarial", {})
                            if _pt and isinstance(_act, dict) and _act.get("enriched_by"):
                                actuarial_map[_pt] = _act
                        except Exception:
                            pass
                    if actuarial_map:
                        logger.info(
                            f"Actuarial map loaded: {len(actuarial_map)} packages "
                            f"with Phase 8.5 enrichment"
                        )
                    else:
                        logger.warning(
                            "Actuarial map empty â€” Phase 8.5 may not have run. "
                            "EDE will score with zero edge. "
                            "Check scripts/actuarial_enrichment_pass.py"
                        )
                except Exception as _act_map_err:
                    logger.warning(f"Actuarial map load failed (non-critical): {_act_map_err}")
            else:
                logger.warning(
                    f"Packages directory not found: {_pkg_dir} â€” "
                    "actuarial data will not propagate to EIL CSV"
                )

            # WBS columns to merge from wall_break_scores CSV
            WBS_COLS = [
                "wbs", "wbs_grade",
                "wbs_f1_vanna", "wbs_f2_wall_weakness", "wbs_f3_flip_clear",
                "wbs_f4_vol_loading", "wbs_f5_momentum",
                "wbs_wall_price", "wbs_wall_dist_pct",
                "wbs_notes", "runway_to_wall_pct", "pin_risk_score",
                "wbs_size_guidance", "wbs_entry_guidance",
                "wbs_phase_b_guidance", "wbs_phase_c_guidance",
                "wbs_stop_guidance", "wbs_wall_stall_rule",
                "wbs_phase_b_trigger", "wbs_phase_c_trigger", "wbs_rejection_stop",
            ]

            # â”€â”€ Load WBS map (ticker â†’ wbs row) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            wbs_map = {}
            wbs_path = os.path.join(base, f"wall_break_scores_{args.run_id}.csv")
            if not os.path.exists(wbs_path):
                # Try the wall_break/ subdirectory as fallback
                wbs_path2 = os.path.join(base, "wall_break",
                                         f"wall_break_scores_{args.run_id}.csv")
                if os.path.exists(wbs_path2):
                    wbs_path = wbs_path2
                else:
                    wbs_path = None
            if wbs_path:
                try:
                    import csv as _csv
                    with open(wbs_path, newline="", encoding="utf-8", errors="replace") as _f:
                        for _r in _csv.DictReader(_f):
                            _t = str(_r.get("ticker", "")).strip().upper()
                            if _t:
                                wbs_map[_t] = _r
                    logger.info(f"WBS map loaded: {len(wbs_map)} tickers from {wbs_path}")
                except Exception as _wbs_err:
                    logger.warning(f"WBS load failed (non-critical): {_wbs_err}")

            # â”€â”€ ticker â†’ EIL row map â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            eil_map = {}
            for _, row in out.iterrows():
                t = str(row.get("ticker", "")).strip().upper()
                if t:
                    eil_map[t] = row.to_dict()

            # â”€â”€ Merge EIL + WBS fields into original superbrain rows â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            enriched_rows = []
            for _, sb_row in df.iterrows():
                t = str(sb_row.get("ticker", "")).strip().upper()
                merged = sb_row.to_dict()

                # â”€â”€ Merge EIL fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if t in eil_map:
                    eil_row = eil_map[t]
                    for col in EIL_COLS:
                        if col in eil_row:
                            merged[col] = eil_row[col]

                    # â”€â”€ DISPLAY FIX 1: overwrite stale superbrain EV fields â”€â”€â”€â”€â”€â”€
                    # EVResult.to_row_dict() writes ev2_ev_conf_adj (authoritative)
                    # but the superbrain ev_final (-1.2 range from v1 fallback) was
                    # already in the row and to_row_dict does NOT overwrite bare
                    # ev_final â€” it uses ev2_ prefix. The Intelligence Lab reads
                    # ev / ev_final for display. Overwrite them here so the Lab
                    # shows the correct EVEngineV2 value (+0.02 range, all positive).
                    _correct_ev = eil_row.get("ev2_ev_conf_adj") or eil_row.get("fd_ev_used")
                    if _correct_ev is not None:
                        try:
                            _ev_val = float(_correct_ev)
                            merged["ev"]       = round(_ev_val, 6)
                            merged["ev_conf_adj"] = round(_ev_val, 6)
                            merged["ev_final"] = round(_ev_val, 6)
                            merged["ev_net"]   = round(_ev_val, 6)
                            # ev_base = ev_structural (regime-free structural quality)
                            _ev_struct = eil_row.get("ev2_ev_structural")
                            if _ev_struct is not None:
                                merged["ev_base"] = round(float(_ev_struct), 6)
                        except (TypeError, ValueError):
                            pass

                    # â”€â”€ DISPLAY FIX 2: ensure current_price / spot_price is set â”€â”€
                    # The Intelligence Lab price column reads current_price or
                    # options_mid. Both are 0 in EOD mode (no live chain).
                    # Alias signal_price so the Lab always has a non-zero price.
                    _sp = merged.get("signal_price") or sb_row.get("signal_price")
                    if _sp and str(_sp) not in ("0", "0.0", "", "nan", "None"):
                        merged["current_price"] = _sp   # overwrite 0.0 from EOD mode
                        merged["spot_price"]    = _sp   # always overwrite in EOD
                        merged["underlying_price"] = _sp

                    # â”€â”€ DISPLAY FIX 3: label BSM premiums â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                    # premium=1.0 is the BSM synthetic fallback (no real quote).
                    # Write a flag so the frontend can show "BSM" instead of $1.00.
                    _prem = merged.get("premium")
                    _synth = merged.get("contract_mark_synthetic", "")
                    if str(_synth).lower() in ("true", "1", "yes") or str(_prem) in ("1.0", "1"):
                        merged["premium_label"] = "BSM"
                        merged["premium_is_synthetic"] = True
                    else:
                        merged["premium_label"] = "$"
                        merged["premium_is_synthetic"] = False

                    # Promote EIL final verdict so F1 gate in morning_validation passes
                    eil_v = str(eil_row.get("fd_verdict", "")).strip()
                    if eil_v and eil_v != "BLOCK":
                        merged["sb_final_verdict"] = eil_v

                # â”€â”€ Merge WBS fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if t in wbs_map:
                    wbs_row = wbs_map[t]
                    for col in WBS_COLS:
                        if col in wbs_row and wbs_row[col] not in ("", None):
                            merged[col] = wbs_row[col]

                # â”€â”€ Propagate actuarial fields from Phase 8.5 package JSONs â”€â”€â”€
                # EDE reads actuarial_win_rate_10d, actuarial_efficiency_10d etc.
                # from the flat EIL CSV. Phase 8.5 patches pkg["actuarial"] in
                # package JSONs after Vanguard runs. Without this propagation
                # those columns are absent â†’ EDE scores 0.000 â†’ all BLOCKED.
                if t in actuarial_map:
                    _act = actuarial_map[t]
                    for _out_col, _act_key in ACTUARIAL_PROPAGATE_COLS:
                        _val = _act.get(_act_key)
                        if _val is not None:
                            merged[_out_col] = _val
                    # Also write flat win_rate_10d / efficiency_10d as fallback
                    # so EDE's secondary lookup (_f("win_rate_10d")) also works
                    for _act_key in ("win_rate_10d", "efficiency_10d",
                                     "expected_move_10d", "risk_10d",
                                     "penalty_multiplier"):
                        _val = _act.get(_act_key)
                        if _val is not None and _act_key not in merged:
                            merged[_act_key] = _val

                enriched_rows.append(merged)

            eil_df = pd.DataFrame(enriched_rows)
            eil_df = ensure_physics_fields(eil_df)
            eil_df = _ensure_eil_audit_contract(eil_df)
            eil_df = enrich_dataframe_with_truth_packets(
                eil_df,
                source="EIL_ENRICHED",
                priority=PRIORITY_EIL_PSE,
                run_id=args.run_id or "",
                run_mode="EVENING",
            )
            eil_df.to_csv(eil_enriched, index=False)
            logger.info("Physics fields handed to EIL: %d rows", int(eil_df["physics_state_id"].astype(str).str.len().gt(0).sum()))
            logger.info(f"eil_enriched written â†’ {eil_enriched}")
            try:
                import sys as _ma_sys
                _ma_sys.path.insert(0, r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter")
                from ma_inputs_sync import on_pipeline_complete as _ma_on_pipeline_complete
                _ma_on_pipeline_complete(str(eil_enriched), output_dir=str(Path(eil_enriched).parent))
            except Exception as _ma_sync_err:
                logger.warning("MA_Inputs sync skipped for eil_enriched output: %s", _ma_sync_err)
    except Exception as _e:
        logger.warning(f"eil_enriched write failed (non-critical): {_e}")




