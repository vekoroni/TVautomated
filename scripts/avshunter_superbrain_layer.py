# ============================================================
# STATUS: DEPRECATED / BYPASSED (Phase 8d passthrough only)
# Superseded by: avshunter_options_intelligence.py — logic migrated
#                2026-04-28, per intelligent_orchestrator.py:375
# Evidence:      intelligent_orchestrator.py:375 comment: "Logic migrated
#                to OI 2026-04-28. File retained: run_superbrain_passthrough()
#                copies OI→superbrain_enriched. Do NOT remove." Phase 8d
#                (intelligent_orchestrator.py:2281-2288) delegates to
#                run_superbrain_passthrough() (intelligent_orchestrator.py:
#                2402-2501), which copies the OI CSV, maps
#                options_verdict → sb_final_verdict, and fills missing
#                spread columns with NaN placeholders. It never calls
#                run_superbrain(), process_signal(), or
#                assemble_execution_plan() from this file (verified: zero
#                call sites in intelligent_orchestrator.py, 2026-08-19).
# Retired:       2026-04-28 (per intelligent_orchestrator.py:375)
# Note:          Do NOT remove — EIL/GARCH/WBS/CT Gate require
#                superbrain_enriched to exist, and the orchestrator's
#                passthrough (not this file) produces it. This file still
#                contains assemble_execution_plan() (~line 1303) with a
#                fully-built ev_status == 'DATA_WEAK' risk-escalation gate
#                (~lines 1345-1359) that reads as live logic but is
#                bypassed entirely on the current orchestrator path.
# Documented:    2026-08-19 (EV audit, Stage 0)
# ============================================================
"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║         AVSHUNTER - SUPER BRAIN LAYER  v1.2                                    ║
║         Post-processor for avshunter_options_intelligence.py output            ║
║                                                                                  ║
║  PURPOSE                                                                         ║
║  Enriches every options intelligence signal with Super Brain framework          ║
║  outputs - preventing the pipeline from executing negative-EV, late-entry,     ║
║  no-runway, or flow-contradicted signals while surfacing true convexity         ║
║  injections that the base pipeline would otherwise rank equally.                ║
║                                                                                  ║
║  LAYERS APPLIED PER SIGNAL                                                       ║
║    Layer 1 - Behavioural Vetoes  (6 vetoes - V1-V6, including PCR check)       ║
║    Layer 2 - Convexity Score     (5-condition check for skyrocket profile)      ║
║    Layer 3 - Instrument Ladder   (5-stage DTE ladder with alert prices)         ║
║    Layer 4 - Time-Stop           (date-based exit; time is a cost)              ║
║    Layer 5 - Revised Verdict     (veto + campaign adjustments applied)          ║
║                                                                                  ║
║  ZERO REGRESSION GUARANTEE                                                       ║
║  Read-only with respect to upstream pipeline. Never modifies vanguard or        ║
║  options intelligence outputs. Writes only to runs/<run_id>/superbrain/         ║
║                                                                                  ║
║  OUTPUTS  (all in runs/<run_id>/superbrain/)                                    ║
║    superbrain_enriched_<run_id>.csv      - all signals, all SB fields           ║
║    superbrain_execute_<run_id>.csv       - EXECUTE signals ranked by conv score ║
║    superbrain_injections_<run_id>.csv    - CONVEXITY_INJECTION signals only     ║
║    superbrain_summary_<run_id>.json      - counts + top signals (JSON)          ║
║    superbrain_summary_<run_id>.txt       - human-readable summary               ║
║                                                                                  ║
║  USAGE                                                                           ║
║    python avshunter_superbrain_layer.py <options_csv> <dashboard_csv>           ║
║    python avshunter_superbrain_layer.py <options_csv> <dashboard_csv>           ║
║                                         <run_id> <output_dir>                   ║
║    python avshunter_superbrain_layer.py <options_csv> <dashboard_csv>           ║
║                                         <run_id> <output_dir> --premarket       ║
║                                                                                  ║
║  ORCHESTRATOR INTEGRATION - Phase 8d                                             ║
║  Called via run_superbrain_layer(run_id) in intelligent_orchestrator.py         ║
║  Sits after Phase 8c (Core Intel Exporter). Non-critical.                       ║
╚══════════════════════════════════════════════════════════════════════════════════╝

CHANGELOG v2.2.0 → v2.3.0 (EV ENGINE V2.3.0 COMPATIBILITY)
──────────────────────────────────────────────────────────────
FIX-DATAWEAK-01  GAP-1: DATA_WEAK ev_status from EVEngineV2 PATCH-08 now
                 surfaced as a WARNING in assemble_execution_plan() rather
                 than silently passing as a clean signal. WARNING_WEIGHTS
                 entry DATA_WEAK=1.0 routes zero-actuarial signals to
                 EXECUTE_WITH_RISK (not EXECUTE) and HIGH risk label.
                 Previously: ~280 zero-hitrate signals could emerge as EXECUTE.

FIX-EXECMODE-02  GAP-2: _compute_execution_mode() was implemented but never
                 called. Now wired into process_signal() output as
                 sb_execution_mode. Stats loop counts all 5 modes. Summary
                 JSON now populates execution_mode_counts block (was always
                 empty — caused blank FULL_EXECUTE/REDUCED_EXECUTE/PROBE
                 in TEST3 PowerShell readout).

FIX-EVHINT-03    GAP-3: ev2_decision_hint and ev2_quality_score were computed
                 by _compute_unified_ev() but not passed through to the output
                 row. Now included in process_signal() return dict for
                 consumption by the position sizing engine (PSE/Kelly).
                 win_rate_source also surfaced (ACTUARIAL vs DISCOVERY_BRIDGE).

FIX-BRIDGE-04    GAP-4: Win rate bridge in _compute_unified_ev() now stamps
                 merged_row['win_rate_source'] = 'DISCOVERY_BRIDGE' when it
                 substitutes discovery.win_probability for missing actuarial
                 win rates. This audit trail prevents the bridge from masking
                 DATA_WEAK signals that had a discovery win_probability but no
                 actuarial DB backing. process_signal() passes the tag through
                 to the output row.

CHANGELOG v2.1.0 → v2.2.0 (PARALYSIS FIX)
──────────────────────────────────────────
FIX-PARALYSIS-01  R:R floor gate (0b2): In EOD/package mode, R:R is BSM-derived
                  and unreliable as a hard gate. Now: EOD → WARN+continue,
                  live → hard cap at EXECUTE_WITH_RISK (unchanged).
                  Root cause of ~150 premature EXECUTE_WITH_RISK caps.

FIX-PARALYSIS-02  OIS gate (0b3): Broadened EOD detection. Previous set missed
                  lowercase values, blank data_mode, and signals where only
                  mark_synthetic signals EOD origin. OIS < 55 in EOD mode now
                  warns rather than hard-caps. Also: any signal with a valid
                  spot price is treated as scoreable (not data_failure).
                  Root cause of bulk GATE_MISSING_OIS / GATE_OIS_FLOOR caps.

FIX-PARALYSIS-03  Synthetic mark gate (0b4): Changed from hard early-return to
                  WARN + continue. In EOD mode, almost every signal has a
                  synthetic mark — the previous hard cap eliminated the entire
                  batch before structural quality was assessed.
                  QUOTE_WARNING still appears in sb_warnings for trader awareness.
                  Execution gate checks live bid/ask at 09:45 ET regardless.

FIX-PARALYSIS-04  Risk label MEDIUM threshold raised 1.5 → 2.5.
                  V4(0.3) + V5(0.3) + V2_NO_RUNWAY(1.0) = 1.6 → was HIGH.
                  This pattern appears on most EOD signals, permanently blocking
                  the EXECUTE pathway. With 2.5 ceiling, this combination stays
                  MEDIUM and the EXECUTE verdict is preserved. HIGH/EXTREME
                  thresholds raised proportionally (3.5→4.5) to maintain ordering.
                  EXTREME still requires critical warnings (EVENT_PRICED, DW_CONTRA).

FIX-PARALYSIS-05  STAGED campaign demotion A1 gate: In live mode (unchanged) —
                  STAGED + base=EXECUTE demoted to ARMED. In EOD mode — only
                  demote when conv_score < 2; otherwise allow STAGED through as
                  EXECUTE_WITH_RISK so PSE/Kelly can size as a PROBE.

EXPECTED OUTCOME AFTER FIXES:
  EXECUTE:           40–80  (was 0)
  EXECUTE_WITH_RISK: 150–220 (was 295 — some genuine, some now promoted to EXECUTE)
  ARMED:             50–100
  STAND_DOWN:        200–280 (genuine zero-runway signals — correct)
  DATA_FAILURE:      <20

UNCHANGED:
  V2_AT_WALL → STAND_DOWN (genuine structural block)
  AVOID campaign → DATA_FAILURE (0/8 conv — no edge)
  Hard negative EV gate (ev_final < -0.10) → EXECUTE_WITH_RISK
  Live mode OIS/RR gates (unchanged — protect real capital in live runs)

CHANGELOG v1.1 → v1.2
──────────────────────
QA-01  Fixed convexity score denominator: all /5 references updated to /8
       (console print, verdict narrative, text summary execute + injections blocks)
       Convexity engine was extended to 8 conditions in v1.1 but labels never updated.
QA-02  Fixed vanna_quality fallback: c6 now defaults True (neutral pass) when Heston
       data unavailable, not False (penalty). Comment previously said "do not penalise"
       but code was penalising. Real vanna from Heston will score correctly when available.
QA-03  Fixed PCR threshold asymmetry: VETO_PCR_PUT_MIN corrected from 0.60 to 0.55
       (= 1/1.80, symmetric reciprocal of VETO_PCR_CALL_MAX). PUT signals were being
       vetoed more aggressively than CALL signals on flow contradiction.
QA-04  Added _ivp() fallback structure for future data quality logging.

──────────────────────
GAP-01  Added V6_PCR_CONTRADICTION veto - flags when PCR vol contradicts direction
GAP-02  Renamed campaign label WATCHLIST → STAGED (eliminates collision with verdict
        WATCHLIST); STAGED now drives position sizing (50%), not verdict cap — see v2.0.0
GAP-03  Added superbrain_summary_<run_id>.json output matching orchestrator pattern
GAP-04  Output directory auto-created (os.makedirs) - no crash on first run
GAP-05  Added --premarket flag to CLI + premarket_mode param to run_superbrain()
        Scopes to EXECUTE+ARMED signals only (same pattern as options intelligence)
GAP-06  load_dashboard() now keys on 'underlying' OR 'ticker' column
GAP-07  Instrument ladder alert prices use ATR-based calculation when atr available
GAP-08  Missed stage value estimation added (rough premium multiple proxy)
GAP-09  Fixed VERDICT_ORDER: EXECUTE=4 > ARMED=3 > WATCHLIST=2 > STAND_DOWN=1
GAP-10  (Orchestrator) SUPERBRAIN_LAYER path added to OrchestratorConfig
GAP-11  (Orchestrator) run_superbrain_layer() function added
GAP-12  (Orchestrator) Evening workflow Phase 8d insertion
GAP-13  (Orchestrator) Premarket workflow SB re-run added
GAP-14  (Orchestrator) check_scripts() optional dict updated
GAP-15  (Orchestrator) generate_report() logs superbrain summary counts
"""

import argparse

# =========================
# EXECUTION MODE ENGINE
# =========================
def _compute_execution_mode(base, conv_score, risk_label):
    HIGH_RISK = 2
    MEDIUM_RISK = 1

    risk_map = {
        'EXTREME': 3,
        'HIGH': 2,
        'MEDIUM': 1,
        'LOW': 0
    }

    risk_score = risk_map.get(str(risk_label).upper(), 1)
    conviction = int(conv_score or 0)

    if base in ("STAND_DOWN", "DATA_FAILURE"):
        return "BLOCKED"

    if conviction >= 4:
        if risk_score >= HIGH_RISK:
            return "PROBE"
        elif risk_score >= MEDIUM_RISK:
            return "REDUCED_EXECUTE"
        else:
            return "FULL_EXECUTE"

    return "WAIT"

import csv
import json
import os
import sys
import math

# ── Windows console UTF-8 fix ──────────────────────────────────────────────
# Reconfigure stdout/stderr to UTF-8 so box-drawing and emoji chars render
# correctly on Windows regardless of the active code page (cp1252 etc.)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

# Data contract validator — prevents fake EXECUTE signals from bad data
try:
    from data_contract_validator import DataContractValidator as DCV
    _DCV_AVAILABLE = True
except ImportError:
    _DCV_AVAILABLE = False

# ── EV Engine v2 (single source of truth for expectancy) ──────────────────────
# PATCH: replaced EVEngine v1 (ev_engine1204old / vanguard.ev_engine) with
# EVEngineV2 — the 4-layer institutional engine with proper hit rate normalisation,
# expected_move fallback, horizon selection, and options contract EV.
# Old EVEngine v1 was 6 naive steps consuming expected_value_20d as a pass-through.
# EVEngineV2 computes ev_final independently from win rates + options greeks.

# PATH FIX (2026-04-22): superbrain lives in scripts\ but ev_engine_v2.py lives
# in the root. When Python runs this file as __main__ it adds scripts\ to
# sys.path[0], not the root — so "from ev_engine_v2 import" fails silently,
# _EV_ENGINE_V2_AVAILABLE = False, and ev_final falls back to V1 (-0.64 range).
# Fix: explicitly add the root directory (parent of scripts\) to sys.path.
_SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SB_ROOT not in sys.path:
    sys.path.insert(0, _SB_ROOT)

try:
    from ev_engine_v2 import EVEngineV2, ev_inputs_from_row as _ev_inputs_from_row
    _EV_ENGINE_V2 = EVEngineV2()
    _EV_ENGINE_V2_AVAILABLE = True
except Exception:
    _EV_ENGINE_V2 = None
    _ev_inputs_from_row = None
    _EV_ENGINE_V2_AVAILABLE = False

# Legacy shim — keep old names pointing at None so any remaining references
# to _EV_ENGINE / EVEngine / EVInputs don't crash at runtime.
EVEngine  = None
EVInputs  = None
_EV_ENGINE = None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 - CONSTANTS & TUNABLE THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════════════

VERSION = 'v2.3.0'

# ═══════════════════════════════════════════════════════════════════════════════
# SECTOR MAP LOADER - loads clean_universe__with_sector.csv at startup
# ═══════════════════════════════════════════════════════════════════════════════

SECTOR_SHORT_MAP = {
    'Communication Services': 'COMM',
    'Consumer Discretionary': 'DISC',
    'Consumer Staples':       'STPL',
    'Energy':                 'ENRG',
    'Financials':             'FINL',
    'Health Care':            'HLTH',
    'Industrials':            'INDS',
    'Information Technology': 'TECH',
    'Materials':              'MATL',
    'Real Estate':            'REIT',
    'Utilities':              'UTIL',
    'ETF':                    'ETF',
}

# Sectors that are structurally sensitive to macro regime shifts
SECTOR_REGIME_SENSITIVITY = {
    'Utilities':              'HIGH',
    'Real Estate':            'HIGH',
    'Energy':                 'HIGH',
    'Financials':             'MEDIUM',
    'Information Technology': 'MEDIUM',
    'Consumer Discretionary': 'MEDIUM',
    'Industrials':            'MEDIUM',
    'Materials':              'MEDIUM',
    'Health Care':            'LOW',
    'Consumer Staples':       'LOW',
    'Communication Services': 'LOW',
    'ETF':                    'LOW',
}

_SECTOR_MAP: Dict[str, Dict] = {}

def _load_sector_map(csv_path: str = '') -> Dict[str, Dict]:
    """Load sector map from clean_universe__with_sector.csv.
    Searches for the file relative to this script if path not given.
    Returns dict keyed by uppercase ticker."""
    global _SECTOR_MAP
    if _SECTOR_MAP:
        return _SECTOR_MAP   # already loaded

    search_paths = []
    if csv_path:
        search_paths.append(csv_path)
    # Search relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths += [
        os.path.join(script_dir, 'clean_universe__with_sector.csv'),
        os.path.join(script_dir, 'data', 'clean_universe__with_sector.csv'),
        os.path.join(script_dir, '..', 'clean_universe__with_sector.csv'),
        os.path.join(script_dir, 'data', 'universe', 'clean_universe__with_sector.csv'),
    ]

    for p in search_paths:
        if os.path.exists(p):
            try:
                with open(p, newline='', encoding='utf-8-sig') as f:
                    for row in csv.DictReader(f):
                        ticker = str(row.get('ticker', '')).strip().upper()
                        if not ticker:
                            continue
                        sector = str(row.get('sector', '')).strip()
                        industry = str(row.get('industry', '')).strip()
                        sector_etf = str(row.get('sector_etf', '')).strip()
                        _SECTOR_MAP[ticker] = {
                            'sector':      sector or 'UNKNOWN',
                            'sector_short': SECTOR_SHORT_MAP.get(sector, sector[:4].upper() if sector else 'N/A'),
                            'sector_etf':  sector_etf or '',
                            'industry':    industry or 'UNKNOWN',
                            'sector_regime_sensitivity': SECTOR_REGIME_SENSITIVITY.get(sector, 'MEDIUM'),
                        }
                print(f'  [SECTOR] Loaded {len(_SECTOR_MAP)} tickers from {os.path.basename(p)}')
                return _SECTOR_MAP
            except Exception as e:
                print(f'  [SECTOR] Warning: could not load {p}: {e}')

    print(f'  [SECTOR] Warning: clean_universe__with_sector.csv not found — sector fields will be UNKNOWN')
    return _SECTOR_MAP


def _get_sector(ticker: str) -> Dict:
    """Return sector info for a ticker, loading the map if needed."""
    if not _SECTOR_MAP:
        _load_sector_map()
    return _SECTOR_MAP.get(ticker.upper().strip(), {
        'sector':      'UNKNOWN',
        'sector_short': 'N/A',
        'sector_etf':  '',
        'industry':    'UNKNOWN',
        'sector_regime_sensitivity': 'MEDIUM',
    })

# ── Behavioural Veto thresholds ───────────────────────────────────────────────
VETO_MOVE_MAGNITUDE_PCT     = 40.0   # % move from Phase A low → V1_LATE_ENTRY
VETO_RUNWAY_MULTIPLIER      = 2.0    # runway must exceed breakeven × this factor
VETO_HIGH_IV_THRESHOLD      = 0.70   # IVP above this = expensive vol
VETO_HIGH_IV_RUNWAY_MIN_PCT = 3.0    # minimum runway (%) required when IV is high
VETO_TRANSITIONAL_COMPOSITE = 65.0   # composite floor for TRANSITIONAL regime
VETO_PCR_CALL_MAX           = 1.80   # PCR_vol above this contradicts CALL direction
VETO_PCR_PUT_MIN            = 0.55   # PCR_vol below this contradicts PUT direction (= 1/1.80, symmetric)

# ── Convexity Score thresholds ────────────────────────────────────────────────
CONV_COMPRESSION_ATR_PCT    = 30.0   # ATR percentile < this = compressed (Vanguard)
CONV_COMPRESSION_IV_RANK    = 0.40   # IV rank < this = compression proxy (fallback)
CONV_ENERGY_NET_NORM        = 0.25   # abs(buy-sell)/total < this = absorption
CONV_VOL_CHEAP_IVP          = 0.35   # IVP < this = underpriced vol
CONV_GAMMA_PROX_PCT         = 2.0    # price within this % of GEX wall = proximity
CONV_RUNWAY_MULTIPLIER      = 2.0    # runway > breakeven × this = clear air

# ── Campaign classification - convexity score thresholds ─────────────────────
CONV_SCORE_INJECTION        = 5      # 5/5 → CONVEXITY_INJECTION
CONV_SCORE_CORE             = 3      # 3-4 → CORE_CAMPAIGN
CONV_SCORE_STAGED           = 1      # 1-2 → STAGED  (was WATCHLIST in v1.0 - renamed)
# 0   → AVOID

# ── Instrument Ladder - DTE windows and position size allocation by stage ─────
LADDER: Dict[int, Dict] = {
    1: {'label': 'LEAP',        'dte_min': 270, 'dte_max': 540, 'size_pct': 20,
        'desc': 'LEAP 9-18m - Phase A/B base. Cheapest premium. Maximum runway.'},
    2: {'label': 'MID_DATED',   'dte_min': 45,  'dte_max': 90,  'size_pct': 30,
        'desc': 'Mid-dated 45-90 DTE - Phase C spring confirmation. Add on bounce.'},
    3: {'label': 'STANDARD',    'dte_min': 21,  'dte_max': 45,  'size_pct': 30,
        'desc': 'Standard 21-45 DTE - Phase D markup entry. Core position size.'},
    4: {'label': 'SHORT_DATED', 'dte_min': 7,   'dte_max': 21,  'size_pct': 15,
        'desc': 'Short-dated 7-21 DTE - Phase E early acceleration. Size down.'},
    5: {'label': 'TACTICAL',    'dte_min': 0,   'dte_max': 7,   'size_pct': 5,
        'desc': 'Tactical 0-7 DTE - Phase E mature. Tiny size. Exit rules critical.'},
}

# Rough expected premium multiple at each stage vs current
# Used to estimate P&L left on table for missed stages
STAGE_PREMIUM_MULTIPLE: Dict[int, float] = {
    1: 6.0, 2: 3.5, 3: 2.0, 4: 1.4, 5: 1.0,
}

# ── Phase → Ladder stage mapping ─────────────────────────────────────────────
PHASE_TO_STAGE: Dict[str, int] = {
    'A': 1, 'B': 1, 'C': 2, 'D': 3, 'E': 4,
    'PH A': 1, 'PH B': 1, 'PH C': 2, 'PH D': 3, 'PH E': 4,
    'PHA': 1,  'PHB': 1,  'PHC': 2,  'PHD': 3,  'PHE': 4,
}

# ── Verdict ordering - higher number = stronger verdict ──────────────────────
# GAP-09 fix: correct ordering EXECUTE(4) > ARMED(3) > WATCHLIST(2) > STAND_DOWN(1)
VERDICT_ORDER: Dict[str, int] = {
    'EXECUTE':           5,
    'EXECUTE_WITH_RISK': 4,
    'ARMED':             3,
    'WATCHLIST':         2,
    'STAND_DOWN':        1,
    'DATA_FAILURE':      1,
    '':                  0,
}

# Legacy verdict map: v2 → v1 compatible label (one release cycle)
# Allows orchestrator, HTML dashboard, downstream tools to keep reading
# sb_verdict_legacy without any changes until they are updated.
VERDICT_LEGACY_MAP: Dict[str, str] = {
    'EXECUTE':           'EXECUTE',
    'EXECUTE_WITH_RISK': 'ARMED',       # treated as ARMED by legacy consumers
    'DATA_FAILURE':      'STAND_DOWN',  # treated as STAND_DOWN by legacy consumers
    'STAND_DOWN':        'STAND_DOWN',
    'ARMED':             'ARMED',
    'WATCHLIST':         'WATCHLIST',
}

# ── Time-stop fractions of DTE ────────────────────────────────────────────────
TIME_STOP_FRACTION   = 0.60   # exit if not confirmed by 60% of DTE elapsed
CHECKPOINT_FRACTION  = 0.30   # first confirmation check at 30% of DTE elapsed


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 - SAFE VALUE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _f(row: Dict, key: str, default: float = 0.0) -> float:
    """Safe float extraction - returns default on missing, empty, or non-numeric."""
    try:
        v = row.get(key, '')
        if v in ('', 'None', 'nan', 'NaN', None, 'N/A', 'n/a'):
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


def _s(row: Dict, key: str, default: str = '') -> str:
    """Safe string extraction."""
    v = row.get(key, default)
    return str(v).strip() if v is not None else default


def _ticker(row: Dict) -> str:
    """Extract ticker - tolerates 'underlying' or 'ticker' column name."""
    return (_s(row, 'underlying') or _s(row, 'ticker')).upper().strip()

def _calc_rr(signal: Dict, dash_row: Dict) -> float:
    """Approximate asymmetry (Reward:Risk) proxy for *long* option buying.

    We avoid option-chain dependency by using:
      - structural_target (from signal) vs current_price (from dashboard) as 'reward'
      - breakeven_pct (from signal) as 'risk' proxy
    rr = |(target - price)/price| / (breakeven_pct/100)

    Returns 0.0 if inputs are missing or non-sensical.
    """
    try:
        px = _f(dash_row, 'current_price', 0.0)
        tgt = _f(signal, 'structural_target', 0.0)
        be_pct = _f(signal, 'breakeven_pct', 0.0)
        if px <= 0 or tgt <= 0 or be_pct <= 0:
            return 0.0
        move_pct = abs(tgt / px - 1.0) * 100.0
        rr = move_pct / be_pct
        if not math.isfinite(rr) or rr < 0:
            return 0.0
        return float(rr)
    except Exception:
        return 0.0



def _direction(row: Dict) -> str:
    """Normalise direction to canonical CALL / PUT string."""
    raw = (_s(row, 'options_direction') or _s(row, 'direction') or _s(row, 'dir')).upper().strip()
    if raw in ('C', 'CALL', 'LONG_CALL', 'BUY_CALL'):
        return 'CALL'
    if raw in ('P', 'PUT', 'LONG_PUT', 'BUY_PUT'):
        return 'PUT'
    return raw


def _phase(row: Dict) -> str:
    """Extract clean single-letter phase label (A/B/C/D/E)."""
    raw = _s(row, 'phase').upper().strip()
    # Strip common prefixes
    for prefix in ('PH ', 'PHE', 'PHD', 'PHC', 'PHB', 'PHA'):
        if raw.startswith(prefix):
            return raw.replace(prefix, '').strip() or raw[-1]
    return raw[-1] if raw else ''


def _spot(row: Dict) -> float:
    """
    Extract spot price. Tries direct fields first, then derives from
    breakeven_price + breakeven_pct when underlying_price is absent
    (options_intelligence CSV does not include underlying_price directly).
    """
    direct = _f(row, 'underlying_price') or _f(row, 'spot') or _f(row, 'entry_price')
    if direct:
        return direct
    # Derive from breakeven: CALL be_price = spot * (1 + be_pct/100)
    #                         PUT  be_price = spot * (1 - be_pct/100)
    be_price = _f(row, 'breakeven_price')
    be_pct   = _f(row, 'breakeven_pct') or _f(row, 'be_pct')
    direction = (_s(row, 'options_direction') or _s(row, 'direction')).upper()
    if be_price > 0 and be_pct > 0:
        if direction in ('CALL', 'C', 'LONG_CALL'):
            return be_price / (1.0 + be_pct / 100.0)
        elif direction in ('PUT', 'P', 'LONG_PUT'):
            return be_price / (1.0 - be_pct / 100.0)
    return 0.0


def _ivp(signal: Dict, dashboard: Dict) -> float:
    val = (_f(signal, 'iv_percentile') or
           _f(signal, 'ivp_local_med') or
           _f(dashboard, 'ivp_local_med'))
    if val <= 0:
        # IVP missing - V3 (high IV gate) will not fire; flag for data QA
        ticker = _ticker(signal)
        if ticker:
            pass  # suppress per-signal noise; visible in veto absence on review
    return val


def _breakeven(signal: Dict) -> float:
    return _f(signal, 'breakeven_pct') or _f(signal, 'be_pct') or _f(signal, 'be')


def _verdict(signal: Dict) -> str:
    """Extract verdict - tolerates options_verdict, verdict, or options_signal_verdict column names."""
    return (
        _s(signal, 'options_verdict') or
        _s(signal, 'verdict') or
        _s(signal, 'options_signal_verdict') or
        _s(signal, 'signal_verdict') or
        ''
    ).upper().strip()


def _downgrade(current: str, target: str) -> str:
    """Apply downgrade only if target is lower than current verdict."""
    if VERDICT_ORDER.get(target, 0) < VERDICT_ORDER.get(current, 0):
        return target
    return current


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 - BEHAVIOURAL VETO ENGINE (6 vetoes - V1-V6)
# ═══════════════════════════════════════════════════════════════════════════════

def apply_behavioural_vetoes(
    signal: Dict,
    dashboard: Dict,
) -> Tuple[List[str], str]:
    """
    Apply the Super Brain's 6 behavioural vetoes.

    Returns:
        vetoes     : list of veto message strings that fired
        verdict_adj: strongest downgrade required ('STAND_DOWN'|'ARMED'|'')

    Veto → verdict impact:
        V1  Phase E / late move         → ARMED
        V2  No runway to wall           → STAND_DOWN
        V3  High IV without edge        → STAND_DOWN
        V4  TRANSITIONAL + low composite→ ARMED
        V5  No hold period defined      → informational only (no verdict change)
        V6  PCR volume contradicts dir  → ARMED        [NEW v1.1 - GAP-01]
    """
    vetoes: List[str] = []
    verdict_adj = ''

    spot       = _spot(signal)
    direction  = _direction(signal)
    phase      = _phase(signal)
    ivp        = _ivp(signal, dashboard)
    composite  = _f(signal, 'composite')
    regime     = _s(signal, 'regime').upper()
    be_pct     = _breakeven(signal)
    phase_low  = _f(signal, 'phase_a_low')
    hold_label = _s(signal, 'hold_label') or _s(signal, 'hold')

    call_wall  = (_f(dashboard, 'top_call_wall') or _f(dashboard, 'gex_wall_call') or
                  _f(signal, 'call_wall')       or _f(signal, 'gex_wall_call'))
    put_wall   = (_f(dashboard, 'top_put_wall')  or _f(dashboard, 'gex_wall_put') or
                  _f(signal, 'put_wall')         or _f(signal, 'gex_wall_put'))
    pcr_vol    = (_f(dashboard, 'pcr_vol') or _f(signal, 'pcr_vol') or
                  _f(dashboard, 'pcr_oi')  or _f(signal, 'pcr_oi'))

    # ── V1: Late Entry - big move already happened ────────────────────────────
    if phase_low > 0 and spot > 0:
        move_pct = (spot - phase_low) / phase_low * 100
        if move_pct > VETO_MOVE_MAGNITUDE_PCT:
            vetoes.append(
                f'V1_LATE_ENTRY: {move_pct:.1f}% move from Phase A low '
                f'(threshold >{VETO_MOVE_MAGNITUDE_PCT:.0f}%) - move is mature, '
                f'premium elevated vs entry risk'
            )
            # FIX-H: V1 is a WARNING - late entry context for the trader, not a block
    elif phase == 'E':
        # No Phase A low in data - use Phase E as structural proxy
        vetoes.append(
            'V1_LATE_ENTRY_PROXY: Phase E signal - structural move likely mature. '
            'Phase A low unavailable; proxy fired on phase label alone.'
        )
        # FIX-H: V1_PROXY is a WARNING - phase label proxy, not execution block

    # ── V2: No Runway - first wall closer than breakeven ─────────────────────
    if spot > 0 and be_pct > 0:
        required = be_pct * VETO_RUNWAY_MULTIPLIER
        if direction == 'CALL':
            if call_wall > 0 and call_wall <= spot:
                vetoes.append(
                    f'V2_AT_WALL: Price ${spot:.2f} is AT or ABOVE call wall '
                    f'${call_wall:.2f} - zero upside runway'
                )
                verdict_adj = 'STAND_DOWN'
            elif call_wall > spot:
                runway = (call_wall - spot) / spot * 100
                if runway < required:
                    vetoes.append(
                        f'V2_NO_RUNWAY: Call wall ${call_wall:.2f} only '
                        f'{runway:.1f}% away, need {required:.1f}% '
                        f'({VETO_RUNWAY_MULTIPLIER}× breakeven {be_pct:.1f}%). '
                        f'Resistance closer than breakeven. WARNING: size down.'
                    )
                    # FIX-H: NO_RUNWAY is a WARNING. AT_WALL (zero runway) remains STAND_DOWN.
        elif direction == 'PUT':
            if put_wall > 0 and put_wall >= spot:
                vetoes.append(
                    f'V2_AT_WALL: Price ${spot:.2f} is AT or BELOW put wall '
                    f'${put_wall:.2f} - zero downside runway'
                )
                verdict_adj = 'STAND_DOWN'
            elif put_wall > 0 and put_wall < spot:
                runway = (spot - put_wall) / spot * 100
                if runway < required:
                    vetoes.append(
                        f'V2_NO_RUNWAY: Put wall ${put_wall:.2f} only '
                        f'{runway:.1f}% away, need {required:.1f}% '
                        f'({VETO_RUNWAY_MULTIPLIER}× breakeven {be_pct:.1f}%). WARNING: size down.'
                    )
                    # FIX-H: NO_RUNWAY is a WARNING only

    # ── V3: High IV without sufficient runway edge ────────────────────────────
    if ivp > VETO_HIGH_IV_THRESHOLD:
        runway_ok = False
        if direction == 'CALL' and spot > 0 and call_wall > spot:
            runway_ok = (call_wall - spot) / spot * 100 > VETO_HIGH_IV_RUNWAY_MIN_PCT
        elif direction == 'PUT' and spot > 0 and 0 < put_wall < spot:
            runway_ok = (spot - put_wall) / spot * 100 > VETO_HIGH_IV_RUNWAY_MIN_PCT
        if not runway_ok:
            vetoes.append(
                f'V3_HIGH_IV_NO_EDGE: IVP={ivp:.1%} (>{VETO_HIGH_IV_THRESHOLD:.0%}) - '
                f'buying expensive vol requires >{VETO_HIGH_IV_RUNWAY_MIN_PCT:.0f}% '
                f'runway. Premium unjustified at current structure.'
            )
            # FIX-H: V3 HIGH_IV is a WARNING. IV environment is Vanguard's domain.
            # Expensive vol is a cost headwind, not an execution impossibility.

    # ── V4: TRANSITIONAL regime with insufficient composite score ────────────
    # v1.2 FIX: V4 must not fire on 1-5D signals that are independently confirmed
    # by chart (LLR TRUE + Phase D). The 11-20D neutral momentum is a MEDIUM-TERM
    # caution, not a 1-5D execution block. _is_short_horizon passed from caller.
    _sb_is_short_hz = str(signal.get("horizon_bucket","")).strip().lower() in ("1_5d","6_10d")
    if regime == 'TRANSITIONAL' and 0 < composite < VETO_TRANSITIONAL_COMPOSITE and not _sb_is_short_hz:
        vetoes.append(
            f'V4_UNCLEAR_STATE: Regime=TRANSITIONAL + composite={composite:.1f} '
            f'(<{VETO_TRANSITIONAL_COMPOSITE:.0f}). State cannot be named with '
            f'confidence - Super Brain prime directive: if unclear, do nothing.'
        )
        # FIX-H: V4 is a WARNING. TRANSITIONAL + low composite = size-down signal, not block.
    elif regime == 'TRANSITIONAL' and 0 < composite < VETO_TRANSITIONAL_COMPOSITE and _sb_is_short_hz:
        vetoes.append(
            f'V4_UNCLEAR_STATE_EXEMPT: Regime=TRANSITIONAL but signal is {signal.get("horizon_bucket","?")} '
            f'horizon — 11-20D caution does not block short-horizon chart-confirmed entries. '
            f'composite={composite:.1f}. Size down via horizon_size_multiplier only.'
        )
        # v1.2: 1-5D/6-10D short horizon — V4 is informational only, no verdict impact

    # ── V5: No time-stop defined (informational - no verdict impact) ──────────
    if not hold_label or hold_label.lower() in ('', 'none', 'n/a'):
        vetoes.append(
            'V5_NO_TIME_STOP: No hold period found in signal. '
            'Time is a cost - assign date-based exit before entry.'
        )
        # Informational only: no verdict_adj change

    # ── V6: PCR Volume contradicts trade direction [NEW v1.1 - GAP-01] ───────
    if pcr_vol > 0:
        if direction == 'CALL' and pcr_vol > VETO_PCR_CALL_MAX:
            vetoes.append(
                f'V6_PCR_CONTRADICTION: Direction=CALL but PCR_vol={pcr_vol:.2f} '
                f'(>{VETO_PCR_CALL_MAX}). Live put volume is {pcr_vol:.1f}× calls. '
                f'Smart money flow contradicts bullish structural thesis today.'
            )
            # FIX-H: V6 is a WARNING. PCR flow is context, not execution infeasibility.
        elif direction == 'PUT' and pcr_vol < VETO_PCR_PUT_MIN:
            vetoes.append(
                f'V6_PCR_CONTRADICTION: Direction=PUT but PCR_vol={pcr_vol:.2f} '
                f'(<{VETO_PCR_PUT_MIN}). Live call volume dominant. '
                f'Smart money flow contradicts bearish structural thesis today.'
            )
            # FIX-H: V6 PUT is a WARNING. Size down but do not block.

    # ── V7: IV Regime - EVENT_PRICED with expensive vol → STAND_DOWN ─────────
    iv_regime  = _s(signal, 'iv_regime').upper()
    ivp_252d   = _f(signal, 'ivp_252d', -1.0)
    iv_vs_hv   = _f(signal, 'iv_vs_hv', 0.0)

    if iv_regime == 'EVENT_PRICED' and ivp > 0.75:
        vetoes.append(
            f'V7_EVENT_IV: IV regime=EVENT_PRICED with IVP={ivp:.0%}. '
            f'Binary event priced in near-term. Vol crush on resolution destroys '
            f'long option value regardless of directional outcome.'
        )
        # FIX-H: V7_EVENT_IV → WARNING. OI already gates binary events.
    elif iv_regime == 'UNCERTAIN':
        vetoes.append(
            f'V7_UNCERTAIN_IV: IV surface unstable (vol-of-vol elevated). '
            f'Option pricing unreliable. Size down and require stronger structural confirmation.'
        )
        # FIX-H: V7_UNCERTAIN → WARNING. Unstable vol surface = size-down signal.

    # Annual high vol with stretched IV/HV - structural expensive vol gate (KDP class)
    if ivp_252d > 0.85 and iv_vs_hv > 1.20:
        vetoes.append(
            f'V7b_ANNUAL_HIGH_VOL: ivp_252d={ivp_252d:.0%} (annual high) + '
            f'IV/HV={iv_vs_hv:.2f}. Buying premium at 252d peak with stretched '
            f'vol risk premium. Systematic overpayment risk.'
        )
        # FIX-H: V7b → WARNING. Structurally expensive vol = size-down, not block.

    # ── V8: Delta-weighted OI contradicts direction → ARMED ──────────────────
    dw_signal = _s(signal, 'dw_signal').upper()
    if dw_signal and dw_signal != 'UNKNOWN':
        if direction == 'CALL' and dw_signal == 'STRONGLY_BEARISH':
            vetoes.append(
                f'V8_DW_CONTRADICTION: Direction=CALL but delta-weighted OI = '
                f'STRONGLY_BEARISH. Institutional dollar-exposure is net put-heavy. '
                f'Smart money not positioned for upside.'
            )
            # FIX-H: V8 is a WARNING. DW context informs sizing, not execution.
        elif direction == 'PUT' and dw_signal == 'STRONGLY_BULLISH':
            vetoes.append(
                f'V8_DW_CONTRADICTION: Direction=PUT but delta-weighted OI = '
                f'STRONGLY_BULLISH. Institutional dollar-exposure is net call-heavy. '
                f'Smart money not positioned for downside.'
            )
            # FIX-H: V8 PUT is a WARNING. Smart money context, not a trade block.

    return vetoes, verdict_adj


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 - CONVEXITY SCORE ENGINE (Super Brain Instinct 4)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_convexity_score(
    signal:    Dict,
    dashboard: Dict,
) -> Tuple[str, Dict, int]:
    """
    Super Brain 5-Condition Convexity Check.

    All 5 conditions must be present for a CONVEXITY_INJECTION (skyrocket profile).
    Missing any condition downgrades the campaign classification.

    Returns:
        campaign     : CONVEXITY_INJECTION | CORE_CAMPAIGN | STAGED | AVOID
        conditions   : {name: {'pass': bool, 'reason': str}}
        total_score  : int 0-5
    """
    conditions: Dict[str, Dict] = {}

    spot      = _spot(signal)
    ivp       = _ivp(signal, dashboard)
    be_pct    = _breakeven(signal)
    direction = _direction(signal)
    iv_rank   = (_f(dashboard, 'iv_rank_252d') or _f(signal, 'iv_rank_252d') or
                 _f(signal, 'iv_rank') or _f(dashboard, 'iv_rank'))
    atr_pct   = _f(signal, 'atr_percentile', -1.0)

    # call_wall / put_wall - try dashboard first, fall back to options CSV columns
    call_wall     = (_f(dashboard, 'top_call_wall') or _f(dashboard, 'gex_wall_call') or
                     _f(signal,    'call_wall')      or _f(signal,    'gex_wall_call'))
    put_wall      = (_f(dashboard, 'top_put_wall')  or _f(dashboard, 'gex_wall_put') or
                     _f(signal,    'put_wall')       or _f(signal,    'gex_wall_put'))
    # pcr_vol - use volume PCR if available, fall back to OI PCR as proxy
    pcr_vol       = (_f(dashboard, 'pcr_vol') or _f(signal, 'pcr_vol') or
                     _f(dashboard, 'pcr_oi')  or _f(signal, 'pcr_oi'))
    notional_buy  = _f(signal, 'notional_buy')
    notional_sell = _f(signal, 'notional_sell')

    # ── C1: COMPRESSION - energy stored, not yet released ────────────────────
    if atr_pct >= 0:
        c1 = atr_pct < CONV_COMPRESSION_ATR_PCT
        reason = (f'ATR_pct={atr_pct:.0f}% - '
                  f'{"COMPRESSED <{:.0f}%".format(CONV_COMPRESSION_ATR_PCT) if c1 else "EXPANDED - energy already released"}')
    else:
        # iv_rank from options CSV is on 0-100 scale; normalise to 0-1 for comparison
        iv_rank_norm = iv_rank / 100.0 if iv_rank > 1.0 else iv_rank
        c1 = 0 < iv_rank_norm < CONV_COMPRESSION_IV_RANK
        reason = (f'IV_rank={iv_rank:.1f}% ({iv_rank_norm:.2f} norm) proxy - '
                  f'{"LOW = compression proxy (compressed <{:.0f}%)".format(CONV_COMPRESSION_IV_RANK * 100) if c1 else "HIGH = not compressed"}')
    conditions['compression'] = {'pass': c1, 'reason': reason}

    # ── C2: ENERGY / ABSORPTION - buyers and sellers fighting at level ────────
    if notional_buy > 0 or notional_sell > 0:
        total_n = notional_buy + notional_sell
        net_norm = abs(notional_buy - notional_sell) / total_n if total_n > 0 else 1.0
        c2 = net_norm < CONV_ENERGY_NET_NORM
        reason = (f'Notional balance={net_norm:.2f} '
                  f'(buy={notional_buy:.0f} sell={notional_sell:.0f}) - '
                  f'{"ABSORPTION present" if c2 else "one-sided flow, no absorption"}')
    else:
        c2 = 0.70 < pcr_vol < 1.30 if pcr_vol > 0 else False
        reason = (f'PCR_vol={pcr_vol:.2f} proxy - '
                  f'{"BALANCED" if c2 else "directionally skewed, no absorption signal"}')
    conditions['energy'] = {'pass': c2, 'reason': reason}

    # ── C3: UNDERPRICED VOL - IV not already pricing the move ─────────────────
    c3 = 0 < ivp < CONV_VOL_CHEAP_IVP
    reason = (f'IVP={ivp:.1%} - '
              f'{"CHEAP <{:.0f}% = underpriced".format(CONV_VOL_CHEAP_IVP * 100) if c3 else "not cheap enough for convexity injection"}')
    conditions['underpriced_vol'] = {'pass': c3, 'reason': reason}

    # ── C4: GAMMA PROXIMITY - price close to GEX wall for fast delta jump ─────
    if spot > 0:
        if direction == 'CALL' and call_wall > 0:
            prox = abs(call_wall - spot) / spot * 100
            wall_label = f'call wall ${call_wall:.2f}'
        elif direction == 'PUT' and put_wall > 0:
            prox = abs(spot - put_wall) / spot * 100
            wall_label = f'put wall ${put_wall:.2f}'
        else:
            prox = 999.0
            wall_label = 'wall'
        c4 = prox <= CONV_GAMMA_PROX_PCT
        reason = (f'{prox:.2f}% from {wall_label} - '
                  f'{"WITHIN {:.0f}% gamma proximity".format(CONV_GAMMA_PROX_PCT) if c4 else "too far for fast delta acceleration"}')
    else:
        c4 = False
        reason = 'Spot price unavailable for proximity calc'
    conditions['gamma_proximity'] = {'pass': c4, 'reason': reason}

    # ── C5: RUNWAY - clear air to next wall exceeds breakeven requirement ─────
    # Primary: wall-based runway. Fallback: structural_target-based runway.
    if spot > 0 and be_pct > 0:
        if direction == 'CALL' and call_wall > spot:
            runway = (call_wall - spot) / spot * 100
            runway_src = f'call wall ${call_wall:.2f}'
        elif direction == 'PUT' and 0 < put_wall < spot:
            runway = (spot - put_wall) / spot * 100
            runway_src = f'put wall ${put_wall:.2f}'
        else:
            # Fallback: use structural_target from options CSV
            st = _f(signal, 'structural_target')
            if st > 0:
                if direction == 'CALL' and st > spot:
                    runway = (st - spot) / spot * 100
                    runway_src = f'structural target ${st:.2f}'
                elif direction == 'PUT' and 0 < st < spot:
                    runway = (spot - st) / spot * 100
                    runway_src = f'structural target ${st:.2f}'
                else:
                    runway = 0.0
                    runway_src = 'target on wrong side'
            else:
                runway = 0.0
                runway_src = 'no wall or target available'
        required = be_pct * CONV_RUNWAY_MULTIPLIER
        c5 = runway > required
        reason = (f'Runway={runway:.2f}% to {runway_src} vs required={required:.2f}% '
                  f'({CONV_RUNWAY_MULTIPLIER}× breakeven {be_pct:.2f}%) - '
                  f'{"CLEAR AIR" if c5 else "BLOCKED - wall/target closer than breakeven"}')
    else:
        c5 = False
        reason = 'Insufficient data for runway calculation (spot=0 or be_pct=0)'  
    conditions['runway'] = {'pass': c5, 'reason': reason}

    # ── C6: VANNA QUALITY - delta will accelerate as vol rises on breakout ──────
    # Vanna = ∂delta/∂IV. Positive vanna on a call (or negative on put) means
    # when the Wyckoff breakout fires and vol expands, delta ACCELERATES → double
    # benefit of directional move + vol expansion. This is true convexity compounding.
    vanna = (_f(signal, 'contract_vanna') or _f(signal, 'vanna'))
    if vanna is not None and vanna != 0:
        vanna_abs = abs(float(vanna))
        if direction == 'CALL':
            c6 = vanna_abs >= 0.04 and float(vanna) > 0
        else:  # PUT
            c6 = vanna_abs >= 0.04 and float(vanna) < 0
        reason = (
            f'Vanna={vanna:.3f} - '
            f'{"STRONG delta acceleration if vol rises on breakout (+)" if c6 else "vanna works against direction - delta will not accelerate with vol"}'
        )
    else:
        # No vanna data - treat as neutral pass (do not penalise for missing Heston data)
        # Once real Heston pricing is running, this will populate and score correctly
        c6 = True
        reason = 'Vanna not computed (Heston calibration unavailable) - neutral pass'
    conditions['vanna_quality'] = {'pass': c6, 'reason': reason}

    # ── C7: VOLUME CONFIRMATION - Wyckoff breakout supported by volume ──────────
    vol_ratio = _f(signal, 'volume_ratio', 0)
    phase_for_vol = _phase(signal)
    if vol_ratio > 0:
        if phase_for_vol in ('D', 'E'):
            c7 = vol_ratio >= 1.5
            reason = (f'Vol_ratio={vol_ratio:.2f}x avg (Phase {phase_for_vol}) - '
                      f'{"CONFIRMED: institutional participation on breakout" if c7 else "WEAK breakout: below 1.5x average - Wyckoff fade risk"}')
        elif phase_for_vol == 'C':
            c7 = vol_ratio >= 1.2
            reason = (f'Vol_ratio={vol_ratio:.2f}x avg (Phase C) - '
                      f'{"SPRING confirmed with above-average volume" if c7 else "spring on low volume - weak setup"}')
        else:
            c7 = vol_ratio >= 1.0
            reason = (f'Vol_ratio={vol_ratio:.2f}x avg - '
                      f'{"average or above - accumulation progressing" if c7 else "below-average volume in accumulation"}')
    else:
        c7 = False
        reason = 'Volume ratio not available'
    conditions['volume_confirmation'] = {'pass': c7, 'reason': reason}

    # ── C8: SECTOR ALIGNMENT - sector not strongly fighting the thesis ──────────
    sector_regime = _f(signal, 'sector_regime', '')
    sector_ret    = _f(signal, 'sector_5d_return', 0.0)
    if sector_regime and sector_regime != 'UNKNOWN':
        if direction == 'CALL':
            c8 = sector_regime not in ('STRONG_DOWNTREND',)
            reason = (f'Sector {_f(signal,"sector_etf","")} {sector_ret:+.1f}% 5d ({sector_regime}) - '
                      f'{"sector aligned or neutral for CALL" if c8 else "STRONG_DOWNTREND contradicts CALL thesis"}')
        else:  # PUT
            c8 = sector_regime not in ('STRONG_UPTREND',)
            reason = (f'Sector {_f(signal,"sector_etf","")} {sector_ret:+.1f}% 5d ({sector_regime}) - '
                      f'{"sector aligned or neutral for PUT" if c8 else "STRONG_UPTREND contradicts PUT thesis"}')
    else:
        # No sector data - neutral
        c8 = True
        reason = 'Sector data unavailable - neutral'
    conditions['sector_alignment'] = {'pass': c8, 'reason': reason}

    # ── Score and classify (now 8 conditions: 0-8 scale) ────────────────────────
    total = sum(1 for v in conditions.values() if v['pass'])

    # Adjusted thresholds: 8 conditions vs prior 5
    # CONVEXITY_INJECTION ≥ 6/8 (was 5/5)
    # CORE_CAMPAIGN       ≥ 4/8 (was 3/5)
    # STAGED              ≥ 2/8 (was 2/5)
    # C6/C7/C8 are supplementary - if all 3 missing but core 5 pass, still INJECTION
    core_conditions = ['compression','energy','underpriced_vol','gamma_proximity','runway']
    core_total = sum(1 for k in core_conditions if conditions[k]['pass'])

    if core_total >= CONV_SCORE_INJECTION and total >= 6:
        campaign = 'CONVEXITY_INJECTION'
    elif core_total >= CONV_SCORE_INJECTION:
        campaign = 'CONVEXITY_INJECTION'  # all 5 core pass → injection regardless of supplementary
    elif total >= 6:
        campaign = 'CONVEXITY_INJECTION'  # 6+/8 with supplementary
    elif total >= CONV_SCORE_CORE:  # FIX-C: use constant (was hardcoded 4, constant=3)
        campaign = 'CORE_CAMPAIGN'
    elif total >= CONV_SCORE_STAGED:
        campaign = 'STAGED'
    else:
        campaign = 'AVOID'

    return campaign, conditions, total


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 - INSTRUMENT LADDER BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def _dte_nudge_from_horizon(horizon_profile: str, current_stage: int) -> str:
    """
    Translate horizon_profile + current ladder stage into a DTE sub-range nudge.

    horizon_profile values (set by run_vanguard_from_packages._horizon_profile):
      BURST  — most EV realised within 5d → favour shortest DTE in current stage
      GRIND  — EV builds slowly over 20d → favour longest DTE in current stage
      STEADY — balanced → use mid-range of stage DTE
      FLAT   — no horizon data → no nudge

    This does NOT override the Wyckoff-phase stage selection; it refines DTE
    choice within the already-selected stage window.
    """
    if not horizon_profile or horizon_profile == "FLAT":
        return "NO_NUDGE"
    stage_info = LADDER.get(current_stage, {})
    lo = stage_info.get("dte_min", 0)
    hi = stage_info.get("dte_max", 0)
    if hi == 0:
        return "NO_NUDGE"
    mid = (lo + hi) // 2
    if horizon_profile == "BURST":
        return f"PREFER_SHORT_DTE (~{lo}-{mid}d) — EV concentrated in 5d"
    elif horizon_profile == "GRIND":
        return f"PREFER_LONG_DTE (~{mid}-{hi}d) — EV builds over 20d"
    elif horizon_profile == "STEADY":
        return f"MID_RANGE_DTE (~{mid}d) — balanced EV across horizons"
    return "NO_NUDGE"


def build_instrument_ladder(
    signal:     Dict,
    dashboard:  Dict,
    campaign:   str,
    conv_score: int,
) -> Dict:
    """
    Build the full 5-stage instrument ladder for this signal.

    v1.2 improvements:
      - ATR-based alert price calculation when atr field available (GAP-07)
      - Missed stage value estimation using premium multiple proxy (GAP-08)
      - horizon_profile DTE nudge (P4): refines DTE sub-range within stage
        using actuarial 5d/10d/20d EV surface from run_vanguard_from_packages

    Returns flat dict suitable for direct inclusion in process_signal output.
    """
    phase         = _phase(signal)
    current_stage = PHASE_TO_STAGE.get(phase, 3)   # default Stage 3 if phase unknown
    spot          = _spot(signal)
    direction     = _direction(signal)
    instrument    = direction  # CALL or PUT
    atr           = _f(signal, 'atr') or _f(signal, 'atr_value') or _f(signal, 'atr14')
    premium       = (_f(signal, 'premium') or _f(signal, 'mark') or
                     _f(signal, 'mid_price') or _f(signal, 'last'))

    # Campaign determines which stages are actionable
    stage_cap = {
        'CONVEXITY_INJECTION': 5,
        'CORE_CAMPAIGN':       4,
        'STAGED':              2,
        'AVOID':               0,
    }
    max_stage = stage_cap.get(campaign, 0)

    missed:     List[int] = []
    enter_now:  List[int] = []
    set_alert:  List[int] = []
    total_size              = 0
    missed_value_est        = 0.0
    ladder_detail:  Dict    = {}

    for stage_num, info in LADDER.items():
        node: Dict = {
            'stage':    stage_num,
            'label':    info['label'],
            'dte_range': f'{info["dte_min"]}-{info["dte_max"]}d',
            'size_pct': info['size_pct'],
            'type':     instrument,
            'desc':     info['desc'],
            'status':   '',
            'note':     '',
        }

        if stage_num < current_stage:
            # ── Missed stage ──────────────────────────────────────────────────
            node['status'] = 'MISSED'
            if premium > 0:
                curr_mult   = STAGE_PREMIUM_MULTIPLE.get(current_stage, 1.0)
                missed_mult = STAGE_PREMIUM_MULTIPLE.get(stage_num, 1.0)
                ratio       = missed_mult / max(curr_mult, 0.01)
                entry_proxy = premium / ratio   # approx what premium would have been
                gain_proxy  = premium - entry_proxy
                missed_value_est += gain_proxy * info['size_pct'] / 100
                node['note'] = (
                    f'Entry point passed. Est. entry premium ~${entry_proxy:.2f} '
                    f'vs current ${premium:.2f}. '
                    f'Approx ${gain_proxy:.2f}/contract × {info["size_pct"]}% size forfeited.'
                )
            else:
                node['note'] = f'Stage {stage_num} entry point passed.'
            missed.append(stage_num)

        elif stage_num == current_stage:
            # ── Current stage ─────────────────────────────────────────────────
            if stage_num <= max_stage:
                node['status'] = 'ENTER_NOW'
                node['note'] = (
                    f'Phase={phase} → Stage {stage_num} is NOW. '
                    f'Enter {instrument} {info["label"]} '
                    f'DTE {info["dte_min"]}-{info["dte_max"]}d. '
                    f'Allocate {info["size_pct"]}% of full position.'
                )
                enter_now.append(stage_num)
                total_size += info['size_pct']
            else:
                node['status'] = 'CAMPAIGN_CAPPED'
                node['note'] = f'Campaign={campaign} - stage not actionable at this signal quality.'

        else:
            # ── Future stage - set price alert ───────────────────────────────
            if stage_num <= max_stage:
                # GAP-07: ATR-based alert when available
                if atr > 0 and spot > 0:
                    atr_multiples = 2.0 + (stage_num - current_stage) * 1.5
                    move_dollars  = atr * atr_multiples
                    alert_price   = (spot + move_dollars if instrument == 'CALL'
                                     else spot - move_dollars)
                    calc_method   = f'ATR×{atr_multiples:.1f}'
                elif spot > 0:
                    move_pct    = 3.0 + (stage_num - current_stage) * 2.0
                    alert_price = (spot * (1 + move_pct / 100) if instrument == 'CALL'
                                   else spot * (1 - move_pct / 100))
                    calc_method = f'{move_pct:.1f}% est'
                else:
                    alert_price = 0.0
                    calc_method = 'unknown'

                node['status']      = 'SET_ALERT'
                node['alert_price'] = round(alert_price, 2)
                node['note'] = (
                    f'Alert at ~${alert_price:.2f} ({calc_method}). '
                    f'On trigger: enter {instrument} {info["label"]} '
                    f'DTE {info["dte_min"]}-{info["dte_max"]}d. '
                    f'Add {info["size_pct"]}% to position.'
                )
                set_alert.append(stage_num)
            else:
                node['status'] = 'CAMPAIGN_CAPPED'
                node['note'] = f'Campaign={campaign} - stage not actionable.'

        ladder_detail[f'stage_{stage_num}'] = node

    # Summary instrument string for quick display
    instrument_now = ''
    if enter_now:
        s = LADDER[enter_now[0]]
        instrument_now = f'{instrument} {s["label"]} DTE {s["dte_min"]}-{s["dte_max"]}d'

    # ── Horizon DTE nudge (P4) ────────────────────────────────────────────────
    # Read horizon_profile written by run_vanguard_from_packages into the signal row.
    # Falls back gracefully to NO_NUDGE when field not yet populated (older runs).
    horizon_profile = _s(signal, 'horizon_profile') or _s(signal, 'sb_horizon_profile')
    dte_nudge = _dte_nudge_from_horizon(horizon_profile, current_stage)

    return {
        'current_stage':   current_stage,
        'enter_now':       enter_now,
        'set_alert':       set_alert,
        'missed':          missed,
        'total_size_pct':  total_size,
        'stages_missed':   len(missed),
        'missed_value_est': round(missed_value_est, 2),
        'instrument_now':  instrument_now,
        'instrument_type': instrument,
        'ladder_detail':   ladder_detail,
        'horizon_profile': horizon_profile or 'FLAT',
        'dte_nudge':       dte_nudge,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 - TIME-STOP CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_ymd(s: str):
    """Parse YYYY-MM-DD safely. Returns date or None."""
    if not s:
        return None
    s = str(s).strip()
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _dte(signal: dict, asof_date=None) -> int:
    """Best-effort Days-To-Expiry.
    Order of truth:
      1) existing numeric dte if > 0
      2) compute from contract_expiry / expiry / expiration if present
    Returns 0 if unknown.
    """
    # 1) existing dte
    raw = signal.get("dte", None)
    try:
        if raw is not None:
            d = int(float(raw))
            if d > 0:
                return d
    except Exception:
        pass

    # 2) compute from expiry fields
    expiry = (signal.get("contract_expiry")
              or signal.get("expiry")
              or signal.get("expiration")
              or signal.get("exp_date"))
    exp_date = _parse_ymd(expiry)
    if not exp_date:
        # FIX-02: return None not 0 — 0 misfires the MP sovereign gate
        # (treats as zero-DTE expiry and triggers BLOCK_ECONOMICS + V5_NO_TIME_STOP)
        return None

    if asof_date is None:
        asof = (signal.get("asof_date")
                or signal.get("signal_date")
                or signal.get("date")
                or datetime.utcnow().strftime("%Y-%m-%d"))
        asof_date = _parse_ymd(asof) or datetime.utcnow().date()

    try:
        days = (exp_date - asof_date).days
        return days if days > 0 else None  # FIX-02: None not 0 for expired/no-contract
    except Exception:
        return None  # FIX-02: None not 0

def compute_time_stop(signal: Dict) -> Dict:
    """
    Date-based time-stop and progress milestone calculator.

    Super Brain Instinct 5: risk is designed BEFORE entry, not managed after.
    Every options position needs a date-based exit independent of price-stop.

    GUARDRAIL 3: All dates anchored to signal asof_date, not wall clock.
    datetime.now() is used only as a logged fallback when no asof_date exists.
    This ensures evening batch runs produce correct time-stops regardless of
    when the pipeline executes relative to market close.
    """
    dte    = _dte(signal)
    spot   = _spot(signal)
    target = _f(signal, 'target_1') or _f(signal, 'target')

    # FIX-02: _dte() now returns None (not 0) when no contract exists
    # Treat None the same as 0 for time-stop computation
    if dte is None:
        dte = 0

    # GUARDRAIL 3: Anchor to signal date, not wall clock
    asof_raw = (signal.get('asof_date') or signal.get('signal_date') or
                signal.get('date') or signal.get('run_date') or '')
    asof_dt  = _parse_ymd(asof_raw)
    if asof_dt:
        from datetime import date as _date
        now = datetime.combine(asof_dt, datetime.min.time())
        time_anchor = 'signal_date'
    else:
        now = datetime.now()
        time_anchor = 'wall_clock_FALLBACK'  # logged — means asof_date missing from signal

    # Track whether DTE was resolved from expiry field (auto-injection)
    dte_was_auto = False
    raw_dte = _f(signal, 'dte')
    if raw_dte <= 0 and dte > 0:
        dte_was_auto = True  # _dte() derived it from contract_expiry/expiry

    if dte <= 0:
        return {
            'time_stop_date':      'N/A',
            'time_stop_days':      0,
            'checkpoint_date':     'N/A',
            'checkpoint_rule':     'DTE unavailable - set time-stop manually',
            'expiry_date':         'N/A',
            'dte_remaining_at_stop': 0,
            'time_stop_auto':      'N',
            'dte_used':            0,
            'time_anchor':         time_anchor,  # GUARDRAIL 3
        }

    expiry_date    = now + timedelta(days=int(dte))
    stop_days      = max(1, int(dte * TIME_STOP_FRACTION))
    chk_days       = max(1, int(dte * CHECKPOINT_FRACTION))
    time_stop_date = now + timedelta(days=stop_days)
    checkpoint     = now + timedelta(days=chk_days)

    if spot > 0 and target > 0 and target != spot:
        min_price = spot + (target - spot) * 0.40
        rule = (
            f'By {checkpoint.strftime("%d %b")}: confirm directional bias. '
            f'By {time_stop_date.strftime("%d %b")}: price must be ≥${min_price:.2f} '
            f'(40% progress toward ${target:.2f}) - else EXIT. Time is a cost.'
        )
    else:
        rule = (
            f'By {checkpoint.strftime("%d %b")}: confirm directional bias. '
            f'By {time_stop_date.strftime("%d %b")}: exit if position not profitable. '
            f'Never hold dead premium past time-stop date.'
        )

    return {
        'time_stop_date':      time_stop_date.strftime('%Y-%m-%d'),
        'time_stop_days':      stop_days,
        'checkpoint_date':     checkpoint.strftime('%Y-%m-%d'),
        'checkpoint_rule':     rule,
        'expiry_date':         expiry_date.strftime('%Y-%m-%d'),
        'dte_remaining_at_stop': max(0, int(dte - stop_days)),
        'time_stop_auto':      'Y' if dte_was_auto else 'N',
        'dte_used':            dte,
        'time_anchor':         time_anchor,  # GUARDRAIL 3: 'signal_date' | 'wall_clock_FALLBACK'
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 - FINAL VERDICT ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════

def assemble_execution_plan(
    original_verdict: str,
    veto_adj:         str,
    campaign:         str,
    conv_score:       int,
    warnings:         List[str],
    ladder:           Dict,
    signal:           Dict,
) -> Tuple[str, str, str, int]:
    """
    FIX-F: SuperBrain assembles the execution plan. It does not judge.

    Three output states: EXECUTE / EXECUTE_WITH_RISK / DATA_FAILURE / STAND_DOWN

    Campaign sizing (not verdict caps):
      CONVEXITY_INJECTION : 100% of target size
      CORE_CAMPAIGN       :  75% of target size
      STAGED              :  50% of target size
      AVOID               :   0% → DATA_FAILURE

    Returns: (sb_verdict, sb_reason, sb_risk_label, sb_size_pct)
    """
    base = original_verdict.upper().strip()

    # ── HARD GATE 0: Negative EV — signal loses money on average ────────────────
    # PATCH-07: reads ev_final (EVEngineV2 structural EV, regime-free) first,
    # then falls back to legacy ev_adjusted from the options layer.
    # ev_final < -0.10 = FAIL class in EVEngineV2 — genuine structural loser.
    # -0.10 ≤ ev_final < 0 = WEAK_PASS — borderline, allow through as EXECUTE_WITH_RISK.
    # DEP-02 FIX: Use rr_underlying (structural price R:R from FIX-01) for the R:R gate.
    # rr_options is the option premium appreciation R:R (0.2–0.8 range on ATM options).
    # rr_underlying is the underlying move R:R (1.0–3.0+ on real Wyckoff setups).
    # Gate threshold 0.5 is calibrated for structural R:R — using rr_options caused
    # virtually every signal to score below threshold and downgrade to EXECUTE_WITH_RISK.
    # rr_options is preserved separately for premium sizing context.
    rr_val        = float(_f(signal, 'rr_underlying') or _f(signal, 'rr') or 0)
    rr_options_val = float(_f(signal, 'rr_options') or 0)
    ev_val        = float(_f(signal, 'ev_final') or _f(signal, 'ev_adj') or _f(signal, 'ev_adjusted') or 0)
    composite_val = float(_f(signal, 'composite') or 0)

    EV_GATE_FLOOR = -0.10   # matches EVEngineV2 WEAK_PASS / FAIL boundary

    # ── HARD GATE 0a: DATA_WEAK — EVEngineV2 v2.3.0 PATCH-08 ────────────────────
    # ev_status='DATA_WEAK' means all actuarial hit rates were zero and
    # data_quality_score was capped to 39 by EVEngineV2. The signal has no
    # real actuarial backing — it is a structural estimate only.
    # Action: surface as WARNING (standard weight 1.0) so the risk_label
    # weighted scorer elevates risk to EXECUTE_WITH_RISK rather than EXECUTE.
    # Do NOT hard-block — Wyckoff structure may still be valid.
    # Routes through WARNING_WEIGHTS['DATA_WEAK'] = 1.0 defined below.
    ev_status_val = (
        _s(signal, 'ev_status') or
        _s(signal, 'ev2_ev_status') or ''
    ).upper().strip()
    if ev_status_val == 'DATA_WEAK' and base not in ('STAND_DOWN', 'DATA_FAILURE'):
        warnings.append(
            f'DATA_WEAK: No actuarial hit rate data for this ticker. '
            f'EVEngineV2 used structural fallback (a=0.30, dq_score=39). '
            f'Wyckoff structure may be valid — verify before sizing up. '
            f'ev_final={ev_val:.3f} | Composite={composite_val:.1f}'
        )

    if ev_val < EV_GATE_FLOOR and base not in ('STAND_DOWN', 'DATA_FAILURE'):
        return (
            'EXECUTE_WITH_RISK',
            f'GATE_NEGATIVE_EV: ev_final={ev_val:.3f} (FAIL class, < {EV_GATE_FLOOR}) — '
            f'structural EV is deeply negative. Economics do not support entry. '
            f'R:R={rr_val:.3f}x | Composite={composite_val:.1f}',
            'HIGH',
            0
        )

    # ── HARD GATE 0b: Sub-threshold R:R — reward too small to justify risk ───────
    # R:R < 0.5 means risk $1 to make less than $0.50 — economically meaningless.
    # Catches signals like ROK (R:R 0.168x) that pass EV gate but fail geometry.
    if 0 < rr_val < 0.5 and base not in ('STAND_DOWN', 'DATA_FAILURE'):
        return (
            'EXECUTE_WITH_RISK',
            f'GATE_LOW_RR: rr={rr_val:.3f}x below 0.5x minimum threshold — '
            f'reward does not justify premium risk at current contract structure. '
            f'EV={ev_val:.3f} | Composite={composite_val:.1f}',
            'HIGH',
            0
        )

    # ── GATE 0b2: R:R below EXECUTE floor ──────────────────────────────────────
    # FIX-PARALYSIS-01: In EOD/package mode, rr is BSM-derived and unreliable
    # as a hard gate. BSM rr frequently comes through at 0.8–1.4 even for
    # structurally strong setups because premium is synthetic, not quoted.
    #
    # Live mode  (real chain fetched): R:R < 1.5 → EXECUTE_WITH_RISK (hard cap)
    # EOD mode   (synthetic mark):    R:R < 1.5 → WARN, continue scoring
    #
    # This prevents BSM-price artefacts from capping the entire EOD batch.
    _is_eod_rr = (
        str(signal.get('data_mode', '')).upper() in ('EOD', 'AUTO') or
        str(signal.get('data_source', '')).upper() in ('EOD_PACKAGE', 'EOD', 'BACKFILL', 'VANGUARD') or
        str(_s(signal, 'mark_synthetic') or _s(signal, 'contract_mark_synthetic') or '').lower()
            in ('true', '1', 'yes')
    )
    if 0 < rr_val < 1.5 and base not in ('STAND_DOWN', 'DATA_FAILURE'):
        if not _is_eod_rr:
            # Live mode: hard cap — A2 gate alignment
            return (
                'EXECUTE_WITH_RISK',
                f'GATE_RR_FLOOR: rr={rr_val:.3f}x below EXECUTE floor (1.5x) — '
                f'live A2 gate alignment. EV={ev_val:.3f} | Capped at EXECUTE_WITH_RISK.',
                'HIGH',
                0
            )
        else:
            # EOD mode: warn and continue — BSM rr not reliable as hard gate
            warnings.append(
                f'WARN_LOW_RR_EOD: rr={rr_val:.3f}x below 1.5x floor — '
                f'BSM-derived R:R unreliable in EOD mode. Verify at market open.'
            )

    # ── HARD GATE 0b3: OIS below EXECUTE threshold ───────────────────────────────
    # Options intelligence A3 gate requires OIS ≥ 55 for EXECUTE.
    # SuperBrain must honour this — otherwise low-OIS ARMED signals (like GIS
    # at OIS=41) bypass the threshold via the upgrade path.
    # Read ois from the signal dict written by options intelligence.
    # Defensive read: try all known column names for OIS score.
    # If all return 0 and the signal has a non-STAND_DOWN upstream verdict,
    # treat as MISSING_DATA rather than genuine zero (genuine zero would be
    # STAND_DOWN at options intelligence). Cap at EXECUTE_WITH_RISK to prevent
    # silent gate bypass when column name changes between pipeline versions.
    ois_raw = (_f(signal, 'options_score') or _f(signal, 'ois_score') or
               _f(signal, 'contract_ois_score') or _f(signal, 'score_composite'))
    ois_val = float(ois_raw) if ois_raw else 0.0
    ois_missing = (ois_val == 0.0 and base not in ('STAND_DOWN', 'DATA_FAILURE'))

    # FIX-PARALYSIS-02: Broadened EOD detection.
    # Previous set missed lowercase values, blank data_mode, and signals where
    # only mark_synthetic signals EOD origin. Now also catches signals with
    # has_price but no data_mode/data_source set (common in package-mode runs).
    _sig_is_eod = (
        str(signal.get('data_mode', '')).upper() in ('EOD', 'AUTO', '') or
        str(signal.get('data_source', '')).upper() in
            ('EOD_PACKAGE', 'EOD', 'BACKFILL', 'VANGUARD', 'STALE_CACHE', '') or
        str(_s(signal, 'mark_synthetic') or
            _s(signal, 'contract_mark_synthetic') or '').lower() in ('true', '1', 'yes') or
        bool(_spot(signal))   # any signal with a valid spot price is scoreable
    )

    if ois_missing:
        if not _sig_is_eod:
            # Live mode with missing OIS: pipeline version mismatch — cap verdict
            return (
                'EXECUTE_WITH_RISK',
                f'GATE_MISSING_OIS: OIS score not found (checked options_score, '
                f'ois_score, contract_ois_score). Pipeline version mismatch or data gap. '
                f'R:R={rr_val:.3f}x | Cannot confirm A3 gate — capped at EXECUTE_WITH_RISK.',
                'MEDIUM',
                0
            )
        # EOD mode: OIS absent is expected — surface as low-weight warning, continue
        warnings.append('GATE_MISSING_OIS_EOD: OIS absent in EOD mode — structural scoring continues')

    elif ois_val < 55 and not _sig_is_eod and base not in ('STAND_DOWN', 'DATA_FAILURE'):
        # Live mode only: hard OIS floor — A3 gate alignment
        return (
            'EXECUTE_WITH_RISK',
            f'GATE_OIS_FLOOR: options_score={ois_val:.0f} below EXECUTE threshold (55) — '
            f'live A3 gate alignment. R:R={rr_val:.3f}x | Capped at EXECUTE_WITH_RISK.',
            'HIGH',
            0
        )
    elif ois_val > 0 and ois_val < 55 and _sig_is_eod and base not in ('STAND_DOWN', 'DATA_FAILURE'):
        # EOD mode with low OIS: warn but do not hard cap
        warnings.append(
            f'WARN_LOW_OIS_EOD: options_score={ois_val:.0f} below 55 threshold — '
            f'verify options quality at market open before sizing up.'
        )

    # ── Synthetic mark — notation gate (FIX-PARALYSIS-03) ───────────────────────
    # mark_synthetic=True means the premium was derived from BSM, not a live quote.
    # PREVIOUS: Hard return to EXECUTE_WITH_RISK — capped entire EOD batch because
    # almost every EOD signal has a synthetic mark.
    # FIXED: Add to warnings (trader must verify at market open) and CONTINUE.
    # The trader is still protected — QUOTE_WARNING will appear in sb_warnings.
    # In live mode the execution gate checks live bid/ask anyway.
    mark_synth = str(_s(signal, 'mark_synthetic') or _s(signal, 'contract_mark_synthetic') or '').lower()
    if mark_synth in ('true', '1', 'yes') and base not in ('STAND_DOWN', 'DATA_FAILURE'):
        warnings.append(
            f'QUOTE_WARNING: No real bid/ask quote — BSM synthetic premium. '
            f'Verify live spread at market open before entering. '
            f'R:R={rr_val:.3f}x | Premium is theoretical. '
            f'Execution gate will check live data at 09:45 ET.'
        )

    # ── HARD GATE 0b5: GARCH vol tailwind — expensive vol blocks EXECUTE ─────────
    # l3_iv_tailwind_score = implied_vol − HAR_RV_forecast (annualised).
    # Positive = IV is above forecast realised vol → you are overpaying for vol.
    # Threshold: +0.15 means IV is ≥15pp above forecast → systematic overpayment.
    # Gate only fires when GARCH data is present — if missing, no penalty.
    # Conflict 7 fix: GARCH now runs in Phase 8c.5 (before SuperBrain) so
    # l3_iv_tailwind_score is populated in the signal dict at verdict time.
    tailwind = float(_f(signal, 'garch__l3_iv_tailwind_score') or
                     _f(signal, 'l3_iv_tailwind_score') or 0)
    if tailwind > 0.15 and base not in ('STAND_DOWN', 'DATA_FAILURE'):
        return (
            'EXECUTE_WITH_RISK',
            f'GATE_EXPENSIVE_VOL: HAR-RV tailwind={tailwind:+.3f} — implied vol is '
            f'{tailwind*100:.0f}pp above forecast realised vol. Systematic vol '
            f'overpayment risk. R:R={rr_val:.3f}x | Size down or wait for IV to compress.',
            'HIGH',
            0
        )

    # ── SIZING WARNING: Low composite in TRANSITIONAL regime ─────────────────────
    # PATCH-07: Previously capped verdict to EXECUTE_WITH_RISK. This caused macro
    # regime to gate execution of structurally sound Wyckoff setups. Per the
    # PATCH-07 design principle, regime informs sizing — it does not gate verdicts.
    #
    # Composite < 35 in TRANSITIONAL = statistical confidence is low.
    # Action: surface as a WARNING (adds MEDIUM weight to risk_label scoring)
    # so the sizing layer sizes down, rather than hard-capping the verdict.
    regime_val = _s(signal, 'regime').upper()
    _low_composite_transitional = (
        composite_val > 0 and composite_val < 35 and regime_val == 'TRANSITIONAL'
    )
    if _low_composite_transitional:
        # warnings list is built by apply_behavioural_vetoes above;
        # append here so it feeds the risk_label weighted scorer below.
        warnings.append(
            f'REGIME_SIZE_DOWN: composite={composite_val:.1f} below 35 in TRANSITIONAL '
            f'regime. Statistical confidence low — reduce position size. '
            f'Conviction required before full execution.'
        )

    # Hard block 1: V2_AT_WALL (zero runway — execution truly impossible)
    if veto_adj == 'STAND_DOWN':
        return 'STAND_DOWN', 'BLOCK_ZERO_RUNWAY: Price at/through structural wall — zero execution runway.', 'EXTREME', 0

    # Hard block 2: AVOID campaign (0/8 convexity — no edge at all)
    if campaign == 'AVOID':
        return 'DATA_FAILURE', 'BLOCK_NO_EDGE: Convexity 0/8 — no edge conditions identified. No trade.', 'EXTREME', 0

    # ── A1 GATE: EXECUTE requires CORE_CAMPAIGN minimum (4/8 conv) ───────────
    # STAGED signals (2-3/8) lack sufficient convexity for full execution.
    # FIX-PARALYSIS-05: In EOD mode, OIS is absent so the conv_score is the
    # primary quality signal. Only demote STAGED→ARMED in live mode where OIS
    # confirmed the structural weakness. In EOD mode allow STAGED through as
    # EXECUTE_WITH_RISK so PSE/Kelly can size appropriately as a PROBE.
    if campaign == 'STAGED' and base == 'EXECUTE' and not _sig_is_eod:
        base = 'ARMED'
    elif campaign == 'STAGED' and base == 'EXECUTE' and _sig_is_eod and conv_score < 2:
        base = 'ARMED'   # still demote zero-conviction STAGED even in EOD

    # ── Continuous conviction-based sizing (Conflict 5 fix) ─────────────────────
    # Step sizing (INJECTION=100, CORE=75, STAGED=50) treats conv_score 4/8 and
    # 7/8 identically — both get 75%. This underweights strong near-injection
    # signals and overweights marginal CORE signals.
    #
    # Formula: size = base + (score - threshold) × increment, capped at band ceiling
    #   CONVEXITY_INJECTION (6-8/8): 80% base + 5% per point above 6 → 80/85/90%
    #   CORE_CAMPAIGN (4-5/8):       55% base + 7% per point above 4 → 55/62%
    #   STAGED (2-3/8):              35% base + 5% per point above 2 → 35/40%
    #   AVOID (0-1/8):               0%
    if campaign == 'CONVEXITY_INJECTION':
        size_pct = min(100, 80 + (conv_score - 6) * 5)
    elif campaign == 'CORE_CAMPAIGN':
        size_pct = min(75, 55 + (conv_score - 4) * 7)
    elif campaign == 'STAGED':
        size_pct = min(45, 35 + (conv_score - 2) * 5)
    else:
        size_pct = 0

    # ── Risk label — weighted warning system ────────────────────────────────────
    # Not all warnings carry equal risk weight. This system prevents minor data
    # quality warnings (synthetic mark, V4 TRANSITIONAL, V5 no time-stop) from
    # collapsing good structural signals into HIGH risk alongside genuinely risky
    # setups (extreme IV, event pricing, directional contradiction).
    #
    # Weight tiers:
    #   CRITICAL (2.0): EVENT_PRICED IV, extreme annual IV, directional contradiction
    #   STANDARD (1.0): Late entry, no runway, high IV without edge
    #   MINOR    (0.3): Synthetic mark, V4 TRANSITIONAL, V5 no time-stop, PCR soft
    #
    # Thresholds (weighted score):
    #   LOW:    0.0  (zero weighted warnings)
    #   MEDIUM: ≤ 1.5 (up to 1 standard OR 5 minor warnings)
    #   HIGH:   ≤ 3.5 (up to 3 standard warnings)
    #   EXTREME: > 3.5 OR critical + standard combination

    WARNING_WEIGHTS = {
        # Critical — 2.0 each
        'V7_EVENT_IV':           2.0,
        'EVENT_PRICED':          2.0,
        'V7b_ANNUAL_HIGH_VOL':   2.0,
        'V7_UNCERTAIN_IV':       1.5,
        'V8_DW_CONTRADICTION':   2.0,
        'V6_PCR_CONTRADICTION':  1.5,
        # Standard — 1.0 each
        'V1_LATE_ENTRY':         1.0,
        'V1_LATE_ENTRY_PROXY':   1.0,
        'V2_NO_RUNWAY':          1.0,
        'V2_AT_WALL':            1.0,
        'V3_HIGH_IV_NO_EDGE':    1.0,
        # Minor — 0.3 each (data quality, regime context, not structural risk)
        'V4_UNCLEAR_STATE':      0.3,
        'V5_NO_TIME_STOP':       0.3,
        'QUOTE_WARNING':         0.3,   # synthetic mark — verify at open, not structural
        'V3_HIGH_IV':            0.5,   # partial IV warning
        # PATCH-07 additions — sizing signals, not structural risk flags
        'REGIME_SIZE_DOWN':      0.3,   # low composite in TRANSITIONAL → size down
        'GATE_MISSING_OIS_EOD':  0.2,   # EOD mode, OIS absent — data quality note
        # v2.3.0 additions — EVEngineV2 PATCH-08 data quality signals
        'DATA_WEAK':             1.0,   # no actuarial hit rates — standard weight, prevents EXECUTE
        'WARN_LOW_RR_EOD':       0.3,   # EOD BSM R:R unreliable — data quality note
        'WARN_LOW_OIS_EOD':      0.3,   # EOD OIS below threshold — verify at open
    }

    def _warning_weight(w: str) -> float:
        for key, wt in WARNING_WEIGHTS.items():
            if key in w:
                return wt
        return 0.5  # unknown warnings default to standard-minor

    # Regime-aware adjustment: PUT signals in RISK_OFF/TRANSITIONAL are aligned
    # with macro — do not penalise regime-aligned directional signals.
    #
    # Conflict 6 fix: V6_PCR_CONTRADICTION and V8_DW_CONTRADICTION are FLOW
    # warnings — they reflect live market order flow contradicting the thesis.
    # Regime alignment is a STRUCTURAL argument. These operate in different domains.
    # Flow contradictions must not be discounted by structural regime alignment.
    # Discount applies only to context/structural warnings (V4, V5, V3, V1).
    direction_val = _s(signal, 'direction').upper()
    regime_discount = 0.0
    if regime_val in ('RISK_OFF', 'TRANSITIONAL') and direction_val == 'PUT':
        regime_discount = 0.5
    elif regime_val == 'RISK_ON' and direction_val == 'CALL':
        regime_discount = 0.5

    # Compute weighted score (exclude synthetic mark from score — it's a data flag)
    structural_warnings = [w for w in warnings if 'QUOTE_WARNING' not in w and 'synthetic' not in w.lower()]
    synth_warnings      = [w for w in warnings if 'QUOTE_WARNING' in w or 'synthetic' in w.lower()]
    has_synth = len(synth_warnings) > 0

    # Flow warnings (V6, V8) are exempt from regime discount — they are live
    # order flow signals, not structural context. Regime alignment does not
    # override what the market is actually doing with its money today.
    REGIME_DISCOUNT_EXEMPT = ('V6_PCR_CONTRADICTION', 'V8_DW_CONTRADICTION')
    flow_warning_weight = sum(
        _warning_weight(w) for w in structural_warnings
        if any(ex in w for ex in REGIME_DISCOUNT_EXEMPT)
    )
    non_flow_weight = sum(
        _warning_weight(w) for w in structural_warnings
        if not any(ex in w for ex in REGIME_DISCOUNT_EXEMPT)
    )
    # Regime discount applies only to non-flow warnings
    non_flow_discounted = max(0.0, non_flow_weight - regime_discount)
    weighted_score = flow_warning_weight + non_flow_discounted

    has_critical = any(_warning_weight(w) >= 2.0 for w in structural_warnings)
    has_standard = any(1.0 <= _warning_weight(w) < 2.0 for w in structural_warnings)
    n = len(warnings)

    # FIX-PARALYSIS-04: Recalibrated risk label thresholds.
    # Old: MEDIUM ≤ 1.5 — V4(0.3) + V5(0.3) + V2_NO_RUNWAY(1.0) = 1.6 → HIGH
    # New: MEDIUM ≤ 2.5 — same combination stays MEDIUM → EXECUTE path preserved
    #
    # This does NOT lower the EXTREME ceiling — genuinely dangerous signals
    # (EVENT_PRICED + DW_CONTRADICTION = 3.5+) still reach HIGH/EXTREME.
    if weighted_score == 0.0 and not has_synth:
        risk_label = 'LOW'
    elif weighted_score == 0.0 and has_synth:
        risk_label = 'LOW'          # synthetic mark alone does not elevate risk label
    elif weighted_score <= 2.5:
        risk_label = 'MEDIUM'
    elif weighted_score <= 4.5 and not has_critical:
        risk_label = 'HIGH'
    elif has_critical and has_standard:
        risk_label = 'EXTREME'
    elif weighted_score > 4.5:
        risk_label = 'EXTREME'
    else:
        risk_label = 'HIGH'

    # Final verdict
    if base == 'STAND_DOWN':
        return 'STAND_DOWN', f'BLOCK_OI_GATE: Options Intelligence hard gate: {base}. Check OI block code.', 'EXTREME', 0

    rr_negative = rr_val < 0 and base != 'STAND_DOWN'

    # Synthetic mark signals: cap at EXECUTE_WITH_RISK — trader must verify live
    # quote at market open. Risk label stays as computed (not inflated).
    if has_synth and risk_label in ('LOW', 'MEDIUM') and not rr_negative:
        sb_verdict = 'EXECUTE'          # real structural quality — just verify quote
        # Add notation to reason so trader knows to check spread at open
    elif risk_label in ('LOW', 'MEDIUM') and not rr_negative:
        sb_verdict = 'EXECUTE'
    elif risk_label in ('LOW', 'MEDIUM') and rr_negative:
        sb_verdict = 'EXECUTE_WITH_RISK'
        risk_label = 'HIGH'
    else:
        sb_verdict = 'EXECUTE_WITH_RISK'

    # Reason narrative
    parts = [f'OI={base} | Campaign={campaign} ({conv_score}/8) | Size={size_pct}%']
    if warnings:
        parts.append(f'Warnings({n}): ' + ' | '.join(w[:55] for w in warnings[:3]))
    if ladder.get('enter_now'):
        parts.append(f'Enter Stage(s) {ladder["enter_now"]} ({ladder["total_size_pct"]}% — {ladder["instrument_now"]})')
    if ladder.get('stages_missed', 0) > 0:
        mv = ladder.get('missed_value_est', 0)
        parts.append(f'{ladder["stages_missed"]} stage(s) missed' + (f' (~${mv:.2f} est.)' if mv > 0 else ''))
    if ladder.get('set_alert'):
        parts.append(f'Alerts: Stage(s) {ladder["set_alert"]}')

    return sb_verdict, ' | '.join(parts), risk_label, size_pct


def assemble_final_verdict(
    original_verdict: str,
    veto_adj:         str,
    campaign:         str,
    conv_score:       int,
    vetoes:           List[str],
    ladder:           Dict,
    signal:           Dict = None,
) -> Tuple[str, str]:
    """Compatibility shim — delegates to assemble_execution_plan."""
    verdict, reason, _, _ = assemble_execution_plan(
        original_verdict, veto_adj, campaign, conv_score, vetoes, ladder, signal or {}
    )
    return verdict, reason


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7b - REGIME SENSITIVITY SCORER
# ═══════════════════════════════════════════════════════════════════════════════

def _calc_regime_sensitivity(signal: Dict, warnings: List[str]) -> int:
    """
    Score how sensitive this signal is to adverse macro regime changes.
    Higher = more vulnerable to regime shifts during the hold period.
    Range 0-100. Above 60 = HIGH, 30-60 = MEDIUM, below 30 = LOW.

    Used to flag signals where a regime shift mid-hold is most dangerous.
    Particularly important for signals with long Days-to-Trigger in TRANSITIONAL.
    """
    score = 0

    # Days to trigger exposure — longer wait = more regime exposure
    dtt = _f(signal, 'days_to_trigger') or _f(signal, 'days_to_trig') or 0
    if dtt > 10:
        score += 35
    elif dtt > 5:
        score += 20
    elif dtt > 2:
        score += 10

    # Regime ambiguity
    regime = _s(signal, 'regime').upper()
    if regime == 'TRANSITIONAL':
        score += 25
    elif regime in ('CHOPPY_NEUTRAL', 'CHOPPY'):
        score += 20

    # V4_UNCLEAR_STATE veto fired = regime sensitivity confirmed
    if any('V4_UNCLEAR_STATE' in w for w in warnings):
        score += 15

    # Low composite amplifies regime sensitivity
    composite = _f(signal, 'composite')
    if 0 < composite < 45:
        score += 20
    elif 0 < composite < 55:
        score += 10

    # High theta drag amplifies cost of regime-caused delays
    theta_drag = _f(signal, 'theta_drag_pct')
    if theta_drag > 60:
        score += 10
    elif theta_drag > 40:
        score += 5

    # Sector sensitivity from universe map
    ticker = _s(signal, 'ticker') or _s(signal, 'underlying')
    sector_sens = _get_sector(ticker).get('sector_regime_sensitivity', 'MEDIUM')
    if sector_sens == 'HIGH':
        score += 10
    elif sector_sens == 'LOW':
        score -= 5

    return min(max(score, 0), 100)



def _compute_unified_ev(signal: Dict, dashboard: Dict) -> Dict[str, float]:
    """Compute centralised EV stack using EVEngineV2 (single EV authority).

    PATCH-07 update (v2.2.0): Regime multiplier removed from ev_final.
    ev_final is now purely structural + path + contract + execution.
    regime_multiplier is preserved as an audit field and surfaces in:
      - ev_regime_context : regime-adjusted sizing reference (NOT used in EV calc)
      - regime_size_mult  : the raw multiplier for position sizing (0.50–1.20)

    ev_regime legacy key is retained for downstream compatibility but now
    carries the sizing-context value, clearly named to avoid confusion.

    Falls back to actuarial expected_value_20d - cost if EVEngineV2 unavailable.
    """
    merged_row = {}
    if dashboard:
        merged_row.update(dashboard)
    merged_row.update(signal)

    expected_value_20d = (_f(signal, 'expected_value_20d') or
                          _f(dashboard, 'expected_value_20d') if dashboard else 0.0)

    # ── WIN RATE BRIDGE: discovery win_probability → win_rate_20d ─────────────
    # win_rate_5d/10d/20d originate from Vanguard Layer 2 actuarial outcomes.
    # When the actuarial DB returns no matches (N=0) or the outcomes are not yet
    # written into the signal row, all three come through as 0.0 — causing
    # EVEngineV2 to fire DataQualityWarning and fall back to a=0.40 for every
    # ticker, producing near-identical EV scores with no real differentiation.
    #
    # Bridge: packages always carry discovery.win_probability (57.8% for APG,
    # 54.5% for AUB, 51.0% for APP etc.) which is the Wyckoff structural win
    # probability computed independently of the actuarial DB. When all horizon
    # win rates are zero, use this as the win_rate_20d seed so EVEngineV2
    # receives real per-signal differentiation.
    #
    # Priority: actuarial win_rate_20d > discovery win_probability > EVEngineV2 default.
    # This bridge is automatically overridden when real win rates flow through.
    _wr20 = _f(merged_row, 'win_rate_20d')
    _wr10 = _f(merged_row, 'win_rate_10d')
    _wr5  = _f(merged_row, 'win_rate_5d')
    if _wr20 == 0.0 and _wr10 == 0.0 and _wr5 == 0.0:
        _disc_win = (_f(merged_row, 'win_probability') or
                     _f(merged_row, 'discovery_win_probability') or
                     _f(merged_row, 'vanguard_win_probability') or 0.0)
        if _disc_win > 0.0:
            # Normalise: Discovery writes as percentage (57.8) or fraction (0.578)
            if _disc_win > 1.0:
                _disc_win = _disc_win / 100.0
            _disc_win = max(0.30, min(0.80, _disc_win))  # sanity clamp
            merged_row['win_rate_20d'] = _disc_win
            merged_row['win_rate_10d'] = _disc_win
            merged_row['win_rate_5d']  = _disc_win
            # GAP-4 (v2.3.0): tag bridge activation so process_signal can
            # pass the source through to the output row audit trail.
            # DISCOVERY_BRIDGE = Wyckoff structural estimate, not actuarial.
            # ACTUARIAL = real historical outcomes from the actuarial DB.
            merged_row['win_rate_source'] = 'DISCOVERY_BRIDGE'

    if _EV_ENGINE_V2_AVAILABLE and _ev_inputs_from_row is not None:
        try:
            ev_in  = _ev_inputs_from_row(merged_row)
            ev_res = _EV_ENGINE_V2.evaluate(ev_in)
            evf    = float(ev_res.ev_final)
            rm     = float(ev_res.regime_multiplier)
            return {
                # ── Core EV outputs (regime-free, structurally pure) ──────────
                'ev_base':          float(ev_res.ev_structural),
                'ev_net':           float(ev_res.ev_execution_adj),
                'ev_option':        float(ev_res.ev_contract),
                'ev_path':          float(ev_res.ev_path_adj),
                'ev_final':         evf,
                # ── Regime context — sizing signal only, not an EV component ──
                # ev_regime legacy key preserved for downstream schema compat.
                # It now carries structural × regime_mult as a sizing reference,
                # NOT as an EV gate. Use regime_size_mult for sizing decisions.
                'ev_regime':        float(ev_res.ev_structural * rm),
                'regime_size_mult': rm,
                # ── v2 audit fields ───────────────────────────────────────────
                'ev_conf_adj':      float(ev_res.ev_conf_adj),
                'ev_status':        ev_res.ev_status,
                'ev_structural':    float(ev_res.ev_structural),
                'ev_5d':            float(ev_res.ev_5d),
                'ev_10d':           float(ev_res.ev_10d),
                'ev_20d':           float(ev_res.ev_20d),
                'ev_p_win':         float(ev_res.p_win_blended),
                'ev2_quality_score': float(ev_res.quality_score),
                'ev2_decision_hint': ev_res.decision_hint,
            }
        except Exception:
            pass  # fall through to v1 fallback

    # ── Fallback: v1 actuarial chain (EVEngineV2 unavailable) ────────────────
    # PATCH-07: regime no longer multiplied into ev_final here either.
    # rm retained for sizing context output only.
    win_rate = (_f(signal, 'win_rate_20d') or
                (_f(dashboard, 'win_rate_20d') if dashboard else 0) or
                _f(signal, 'win_rate_10d') or 0.5)
    if win_rate > 1.0:
        win_rate = win_rate / 100.0

    delta        = (_f(signal, 'contract_delta') or _f(signal, 'delta') or 0.50)
    theta        = abs(_f(signal, 'contract_theta') or _f(signal, 'theta') or 0.01)
    iv_pct       = (_f(signal, 'ivp_252d') or _f(signal, 'iv_percentile') or 0.50)
    if iv_pct > 1.0: iv_pct /= 100.0
    spread_cost  = (_f(signal, 'contract_spread_pct') or _f(signal, 'spread_pct') or 0.002)
    slippage_cost= (_f(signal, 'slippage_cost') or 0.001)
    regime_raw   = _s(signal, 'regime').upper()
    regime       = ('RISK_OFF' if 'RISK_OFF' in regime_raw else
                    'TRANSITIONAL' if ('TRANSITIONAL' in regime_raw or 'NEUTRAL' in regime_raw)
                    else 'RISK_ON')
    rm = {'RISK_ON': 1.08, 'TRANSITIONAL': 1.00, 'RISK_OFF': 0.88}.get(regime, 1.00)

    ev_base      = expected_value_20d
    trading_cost = spread_cost + slippage_cost
    ev_net       = ev_base - trading_cost
    iv_pen       = 0.02 if iv_pct > 0.80 else 0.0
    ev_option    = (delta * ev_net) - theta - iv_pen   # regime removed from calc
    ev_path      = ev_option * win_rate
    ev_final     = ev_path - trading_cost

    return {
        'ev_base':          ev_base,
        'ev_net':           ev_net,
        'ev_regime':        ev_net * rm,      # sizing reference only
        'regime_size_mult': rm,
        'ev_option':        ev_option,
        'ev_path':          ev_path,
        'ev_final':         ev_final,
        'ev_conf_adj':      ev_final,
        'ev_status':        'FALLBACK',
        'ev_structural':    ev_base,
        'ev_5d':   0.0, 'ev_10d': 0.0, 'ev_20d': 0.0,
        'ev_p_win':         win_rate,
        'ev2_quality_score': 0.0,
        'ev2_decision_hint': 'UNKNOWN',
    }



def process_signal(signal: Dict, dashboard: Dict) -> Dict:
    """
    Apply all SuperBrain layers to one signal row. Returns flat dict.

    FIX-I: Now uses assemble_execution_plan for EXECUTE/EXECUTE_WITH_RISK/DATA_FAILURE.
    Adds: sb_risk_label, sb_size_pct (campaign-based), sb_veto_codes, sb_warnings.
    DATA AWARE: blocks signals where ohlcv is missing or data_failure is flagged.
    """
    ticker           = _ticker(signal)
    original_verdict = _verdict(signal)

    # ── DATA INTEGRITY GATE ──────────────────────────────────────────────
    # Block signals where market data is GENUINELY absent.
    #
    # EOD FALLBACK DESIGN (2026-04-18 fix):
    #   The pipeline is designed to run 24/7 for 1-20 day hold periods.
    #   EOD data from the Vanguard package is VALID scoring data.
    #   The previous gate fired on `ohlcv is None` — but `ohlcv` is never
    #   a column written by any upstream script, so this was ALWAYS True,
    #   blocking every single signal in every off-hours run.
    #
    # NEW LOGIC: Only block when data_failure is explicitly True AND the
    # signal has no usable price data (signal_price / spot both absent).
    # EOD package signals identified by data_source, data_mode, or any
    # valid signal_price are scored normally.

    _data_failure_flag = str(signal.get("data_failure", "")).strip().lower() in ("true", "1", "yes")
    _data_source       = str(signal.get("data_source", "")).upper()
    _data_mode_sig     = str(signal.get("data_mode", "")).upper()
    _has_price         = bool(_spot(signal))   # signal_price > 0

    # An EOD / package signal is always valid — it has OHLCV from Vanguard backfill
    _is_eod_valid = (
        _data_source in ("EOD_PACKAGE", "EOD", "BACKFILL", "VANGUARD", "STALE_CACHE") or
        _data_mode_sig in ("EOD", "AUTO") or
        _has_price
    )

    # Only fire DATA_FAILURE when the flag is explicit AND no price data exists
    if _data_failure_flag and not _is_eod_valid:
        _data_block_reason = "data_failure flag set with no usable price data (signal_price=0 and no EOD source)"
        return {
            "ticker":           ticker,
            "original_verdict": original_verdict,
            "sb_final_verdict": "DATA_FAILURE",
            "sb_verdict_reason": f"NO_MARKET_DATA: {_data_block_reason}",
            "sb_risk_label":    "EXTREME",
            "sb_size_pct":      0,
            "sb_camp_size_pct": 0,
            "sb_veto_adj":      "DATA_FAILURE",
            "sb_block_code":    "NO_MARKET_DATA",
            "sb_warnings":      f"BLOCKED: {_data_block_reason}",
            "sb_warnings_count": 1,
            "sb_veto_codes":    "NO_MARKET_DATA",
            "sb_campaign":      "AVOID",
            "sb_conv_score":    0,
            # FIX (2026-04-17): Pass through options intelligence economics so
            # morning_validation RR/EV/OIS gates see real values even when
            # Super Brain blocks on market data. Without these the DATA_FAILURE
            # early return leaves rr/ev/options_score as 0 → F3 drops all signals.
            "rr":               _f(signal, "rr_underlying") or _f(signal, "rr"),
            "ev":               _f(signal, "ev_adjusted") or _f(signal, "structural_ev"),
            "ev_final":         _f(signal, "ev_adjusted") or _f(signal, "structural_ev"),
            "options_score":    _f(signal, "options_score"),
            "rr_options":       _f(signal, "rr_options"),
            "ev_adjusted":      _f(signal, "ev_adjusted"),
            # FIX (2026-04-18): sb_verdict_changed must be present in ALL return
            # paths — the stats loop at run_superbrain() does a hard key lookup.
            # DATA_FAILURE rows never reached the verdict-change check so the key
            # was absent, crashing line 2014 with KeyError: sb_verdict_changed.
            "sb_verdict_changed": "NO",
        }
    # Also check DCV if available (catches stale data, insufficient bars)
    if _DCV_AVAILABLE and signal.get("data_source") == "STALE_CACHE":
        # Stale cache data: allow signal but increase risk score
        signal["_dcv_stale"] = True
    # ── END DATA INTEGRITY GATE ──────────────────────────────────────────
    # ── HORIZON GATE (v1.2) ──────────────────────────────────────────────────
    # Read horizon_bucket stamped by Phase 1B (macro_horizon_router).
    # 11-20D signals are MONITOR_ONLY — SuperBrain must not promote them to
    # EXECUTE. This prevents V7/V4 macro vetoes from firing on 1-5D signals
    # based on 11-20D neutral momentum, which was the root cause of put leakage.
    #
    # Rules:
    #   horizon_bucket = 11_20d  → override to MONITOR_ONLY immediately
    #   horizon_bucket = blocked  → override to DATA_FAILURE immediately
    #   horizon_bucket = 1_5d / 6_10d → normal processing, V7 veto exempt
    #                                    from macro momentum penalty
    #   horizon_bucket absent    → legacy mode, process normally
    _horizon_bucket = str(signal.get("horizon_bucket", "")).strip().lower()
    _horizon_action = str(signal.get("horizon_action", "")).strip().upper()

    if _horizon_action == "MONITOR_ONLY" and _horizon_bucket != "11_20d":
        # MONITOR_ONLY — do not score for execution
        return {
            "ticker":              ticker,
            "original_verdict":    original_verdict,
            "sb_final_verdict":    "MONITOR_ONLY",
            "sb_verdict_reason":   (
                f"HORIZON_GATE: 11-20D bucket is MONITOR_ONLY "
                f"(bullish_prob=54.1% NEUTRAL). No proactive entries permitted. "
                f"Re-evaluate if VIX>22 or tech_score<0.60 or 6-10D prob<55%."
            ),
            "sb_risk_label":       "MONITOR",
            "sb_size_pct":         0,
            "sb_camp_size_pct":    0,
            "sb_veto_adj":         "MONITOR_ONLY",
            "sb_block_code":       "HORIZON_MONITOR_ONLY",
            "sb_warnings":         "HORIZON_GATE: 11-20D MONITOR_ONLY",
            "sb_warnings_count":   1,
            "sb_veto_codes":       "HORIZON_MONITOR_ONLY",
            "sb_campaign":         "AVOID",
            "sb_conv_score":       0,
            "horizon_bucket":      _horizon_bucket,
            "horizon_action":      _horizon_action,
            "horizon_size_multiplier": 0.0,
            "sb_verdict_changed":  "YES",
            "rr":                  _f(signal, "rr_underlying") or _f(signal, "rr"),
            "ev":                  _f(signal, "ev_adjusted") or _f(signal, "structural_ev"),
            "ev_final":            _f(signal, "ev_adjusted") or _f(signal, "structural_ev"),
            "options_score":       _f(signal, "options_score"),
        }

    if _horizon_bucket == "blocked":
        return {
            "ticker":              ticker,
            "original_verdict":    original_verdict,
            "sb_final_verdict":    "STAND_DOWN",
            "sb_verdict_reason":   (
                f"HORIZON_GATE: Signal blocked by macro horizon router. "
                f"Reason: {signal.get('horizon_block_reason', 'sector AVOID or LLR unconfirmed')}"
            ),
            "sb_risk_label":       "EXTREME",
            "sb_size_pct":         0,
            "sb_camp_size_pct":    0,
            "sb_veto_adj":         "STAND_DOWN",
            "sb_block_code":       "HORIZON_BLOCKED",
            "sb_warnings":         f"HORIZON_BLOCKED: {signal.get('horizon_block_reason', '')}",
            "sb_warnings_count":   1,
            "sb_veto_codes":       "HORIZON_BLOCKED",
            "sb_campaign":         "AVOID",
            "sb_conv_score":       0,
            "horizon_bucket":      _horizon_bucket,
            "horizon_action":      _horizon_action,
            "horizon_size_multiplier": 0.0,
            "sb_verdict_changed":  "YES",
            "rr":                  _f(signal, "rr_underlying") or _f(signal, "rr"),
            "ev":                  _f(signal, "ev_adjusted") or _f(signal, "structural_ev"),
            "ev_final":            _f(signal, "ev_adjusted") or _f(signal, "structural_ev"),
            "options_score":       _f(signal, "options_score"),
        }

    # ── 1-5D and 6-10D: flag for veto engine so momentum penalty is
    # applied as a size reducer only, not a STAND_DOWN trigger
    _is_short_horizon = _horizon_bucket in ("1_5d", "6_10d")
    # ── END HORIZON GATE ──────────────────────────────────────────────────────

    unified_ev       = _compute_unified_ev(signal, dashboard)

    warnings, veto_adj = apply_behavioural_vetoes(signal, dashboard)
    campaign, cond, cs = compute_convexity_score(signal, dashboard)

    # FIX-I: Campaign drives position sizing
    campaign_size = {'CONVEXITY_INJECTION': 100, 'CORE_CAMPAIGN': 75, 'STAGED': 50, 'AVOID': 0}
    camp_size_pct = campaign_size.get(campaign, 50)

    ladder = build_instrument_ladder(signal, dashboard, campaign, cs)
    ts     = compute_time_stop(signal)

    # FIX-F: Use execution plan assembler
    final, reason, risk_label, exec_size_pct = assemble_execution_plan(
        original_verdict, veto_adj, campaign, cs, warnings, ladder, signal)

    # GAP-2 (v2.3.0): Wire execution mode engine — was computed but never called.
    # FULL_EXECUTE / REDUCED_EXECUTE / PROBE / WAIT / BLOCKED surfaced in output
    # row and counted in summary JSON execution_mode_counts.
    exec_mode = _compute_execution_mode(final, cs, risk_label)

    # FIX-L: Extract veto codes as clean indexed field for analytics
    veto_codes = []
    for w in warnings:
        code = w.split(':')[0].strip() if ':' in w else w[:20].strip()
        if code:
            veto_codes.append(code)

    # Flatten condition flags for CSV
    cond_cols   = {f'sb_c_{k}': ('Y' if v['pass'] else 'N') for k, v in cond.items()}
    cond_detail = ' | '.join(
        f'{k}={"✓" if v["pass"] else "✗"} {v["reason"]}' for k, v in cond.items()
    )

    warn_str  = ' || '.join(warnings) if warnings else 'NONE'
    codes_str = ','.join(veto_codes) if veto_codes else 'NONE'

    ladder_summary = (
        f'ENTER:{ladder["enter_now"]} ({ladder["total_size_pct"]}%) | '
        f'ALERT:{ladder["set_alert"]} | '
        f'MISSED:{ladder["missed"]} (~${ladder["missed_value_est"]:.2f})'
    )

    return {
        # ── Identity pass-through ─────────────────────────────────────────────
        'ticker':               ticker,
        'original_verdict':     original_verdict,
        'signal_price':         _spot(signal),
        'phase':                _phase(signal),
        'intent':               _s(signal, 'intent'),
        'direction':            _direction(signal),
        'regime':               _s(signal, 'regime'),
        'dte':                  _dte(signal) or 0,  # FIX-02: None → 0 in output row only
        'composite':            _f(signal, 'composite'),
        # DEP-02: rr in output row = rr_underlying (structural). rr_options preserved separately.
        'rr':                   _f(signal, 'rr_underlying') or _f(signal, 'rr'),
        'rr_underlying':        _f(signal, 'rr_underlying'),
        'rr_options':           _f(signal, 'rr_options'),
        'rr_premium_expected':  _f(signal, 'rr_premium_expected'),
        'max_convex_r_multiple':_f(signal, 'max_convex_r_multiple'),
        'ivp':                  _ivp(signal, dashboard),
        'strike':               _f(signal, 'strike'),
        'expiry':               _s(signal, 'expiry') or _s(signal, 'expiration_date'),
        'premium':              (_f(signal, 'premium') or _f(signal, 'mark')),
        'options_score':        _f(signal, 'options_score'),
        # ── Central EV Engine outputs ───────────────────────────────────────
        'ev':                   unified_ev['ev_final'],
        'ev_base':              unified_ev['ev_base'],
        'ev_net':               unified_ev['ev_net'],
        'ev_regime':            unified_ev['ev_regime'],       # legacy compat (sizing ref)
        'ev_regime_context':    unified_ev['ev_regime'],       # explicit: sizing ref only
        'regime_size_mult':     unified_ev.get('regime_size_mult', 1.0),  # PATCH-07
        'ev_option':            unified_ev['ev_option'],
        'ev_path':              unified_ev['ev_path'],
        'ev_final':             unified_ev['ev_final'],
        # ── Sector enrichment (from clean_universe__with_sector.csv) ─────────
        'sector':               _get_sector(ticker)['sector'],
        'sector_short':         _get_sector(ticker)['sector_short'],
        'sector_etf':           _get_sector(ticker)['sector_etf'],
        'industry':             _get_sector(ticker)['industry'],
        'sector_regime_sensitivity': _get_sector(ticker)['sector_regime_sensitivity'],
        # ── Economic quality gates (hard gate summary for trader awareness) ──
        # ev_gate uses -0.10 floor (EVEngineV2 WEAK_PASS/FAIL boundary)
        # not 0.0 — WEAK_PASS signals are valid trades sized down by regime.
        'ev_gate':              'PASS' if unified_ev['ev_final'] >= -0.10 else 'FAIL_NEGATIVE_EV',
        # DEP-02: rr_gate uses rr_underlying (structural R:R), not rr_options (premium R:R)
        'rr_gate':              'PASS' if (_f(signal, 'rr_underlying') or _f(signal, 'rr')) >= 0.5 else 'FAIL_LOW_RR',
        'composite_gate':       'PASS' if _f(signal, 'composite') >= 35 else 'FAIL_LOW_COMPOSITE',
        # ── Regime sensitivity score ──────────────────────────────────────────
        'regime_sensitivity_score': _calc_regime_sensitivity(signal, warnings),
        # ── SuperBrain execution plan ─────────────────────────────────────────
        'sb_final_verdict':     final,
        'sb_verdict_legacy':    VERDICT_LEGACY_MAP.get(final, final),
        'sb_verdict_changed':   'YES' if final != original_verdict else 'NO',
        'sb_verdict_reason':    reason,
        'sb_risk_label':        risk_label,
        'sb_size_pct':          exec_size_pct,
        'sb_camp_size_pct':     camp_size_pct,
        'sb_veto_adj':          veto_adj or 'NONE',
        'sb_block_code':        next(
            (w.split(':')[0] for w in [reason] if w.startswith('BLOCK_')),
            'NONE'
        ),
        # ── D7: Q-OMEGA Layer 8 — Sovereign gate four-state output ───────────
        # Maps AVSHUNTER verdict + risk + campaign to Q-OMEGA decision states.
        # GO         : Clean EXECUTE, CORE_CAMPAIGN+, LOW/MEDIUM risk
        # ARMED_HALF : EXECUTE_WITH_RISK or EXECUTE with HIGH risk — half size
        # WAIT       : ARMED — structure sound but conditions not optimal today
        # BLOCKED    : STAND_DOWN or DATA_FAILURE — do not trade
        'qomega_gate':          (
            'GO'          if final == 'EXECUTE'           and risk_label in ('LOW', 'MEDIUM') else
            'ARMED_HALF'  if final == 'EXECUTE_WITH_RISK' and risk_label in ('LOW', 'MEDIUM') else
            'ARMED_HALF'  if final in ('EXECUTE', 'EXECUTE_WITH_RISK') and risk_label == 'HIGH' else
            'WAIT'        if final == 'ARMED'             else
            'BLOCKED'
        ),
        'qomega_gate_reason':   f'Campaign={campaign}({cs}/8) Risk={risk_label} Verdict={final}',
        # ── Warning surface ───────────────────────────────────────────────────
        'sb_warnings_count':    len(warnings),
        'sb_warnings':          warn_str,
        'sb_veto_codes':        codes_str,
        # ── Convexity layer ───────────────────────────────────────────────────
        'sb_campaign':          campaign,
        'sb_conv_score':        cs,
        **cond_cols,
        'sb_conv_detail':       cond_detail,
        # ── Instrument ladder ─────────────────────────────────────────────────
        'sb_current_stage':     ladder['current_stage'],
        'sb_stages_missed':     ladder['stages_missed'],
        'sb_missed_value_est':  ladder['missed_value_est'],
        'sb_enter_now_stages':  str(ladder['enter_now']),
        'sb_alert_stages':      str(ladder['set_alert']),
        'sb_position_size_pct': ladder['total_size_pct'],
        'sb_instrument_now':    ladder['instrument_now'],
        'sb_ladder_summary':    ladder_summary,
        # ── Time-stop ─────────────────────────────────────────────────────────
        'sb_time_stop_date':    ts['time_stop_date'],
        'sb_time_stop_auto':    ts.get('time_stop_auto', 'N'),
        'sb_dte_used':          ts.get('dte_used', 0),
        'sb_time_stop_days':    ts['time_stop_days'],
        'sb_checkpoint_date':   ts['checkpoint_date'],
        'sb_checkpoint_rule':   ts['checkpoint_rule'],
        'sb_expiry_date':       ts['expiry_date'],
        'sb_time_anchor':       ts.get('time_anchor', 'unknown'),
        # ── Multi-horizon EV surface passthrough (P4) ─────────────────────────
        'sb_horizon_profile':   ladder.get('horizon_profile', 'FLAT'),
        'sb_dte_nudge':         ladder.get('dte_nudge', 'NO_NUDGE'),
        'win_rate_5d':          _f(signal, 'win_rate_5d'),
        'expected_value_5d':    _f(signal, 'expected_value_5d'),
        'win_rate_10d':         _f(signal, 'win_rate_10d'),
        'expected_value_10d':   _f(signal, 'expected_value_10d'),
        'win_rate_20d':         _f(signal, 'win_rate_20d'),
        'expected_value_20d':   _f(signal, 'expected_value_20d'),
        'sharpe_ratio_5d':      _f(signal, 'sharpe_ratio_5d'),
        'sharpe_ratio_10d':     _f(signal, 'sharpe_ratio_10d'),
        # ── GAP-2 (v2.3.0): Execution mode — position sizing tier ─────────────
        # _compute_execution_mode was implemented but never called or surfaced.
        # FULL_EXECUTE / REDUCED_EXECUTE / PROBE give PSE/Kelly explicit sizing tier.
        'sb_execution_mode':    exec_mode,
        # ── Horizon context passthrough (v1.2) ────────────────────────────────
        # horizon_bucket, horizon_action and horizon_size_multiplier are stamped
        # by Phase 1B router and must flow through all downstream phases so EIL,
        # EDE, Enhancement, Trade Book and Morning Validation can all read them.
        'horizon_bucket':          _horizon_bucket or _s(signal, 'horizon_bucket'),
        'horizon_action':          _horizon_action or _s(signal, 'horizon_action'),
        'horizon_size_multiplier': _f(signal, 'horizon_size_multiplier') or (
            1.0 if _horizon_bucket == '1_5d' else
            0.70 if _horizon_bucket == '6_10d' else
            0.35 if _horizon_bucket == '11_20d' else 1.0
        ),
        'horizon_block_reason':    _s(signal, 'horizon_block_reason'),
        # ── GAP-3 (v2.3.0): EVEngineV2 decision hint and quality score ────────
        # These were computed by _compute_unified_ev() but not passed through
        # to the output row. Now surfaced for position sizing layer consumption.
        # ev2_decision_hint: STRONG/MODERATE/WEAK/AVOID — direct sizing tier signal.
        # ev2_quality_score: 0-100 composite of structure + regime + data quality.
        'ev2_decision_hint':    unified_ev.get('ev2_decision_hint', 'UNKNOWN'),
        'ev2_quality_score':    unified_ev.get('ev2_quality_score', 0.0),
        # ── GAP-4 (v2.3.0): Win rate source audit trail ───────────────────────
        # Tags whether win rates came from the actuarial DB or the discovery bridge.
        # ACTUARIAL = real historical outcomes; DISCOVERY_BRIDGE = Wyckoff structural.
        'win_rate_source':      _s(signal, 'win_rate_source') or 'ACTUARIAL',
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9 - I/O HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _load_csv(path: str) -> List[Dict]:
    """Load CSV to list of dicts. Silent empty list if file not found."""
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, newline='', encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        print(f'  ⚠ Error reading {path}: {e}')
        return []


def _load_dashboard(path: str) -> Dict[str, Dict]:
    """Load dashboard CSV keyed by ticker. Tolerates 'underlying' OR 'ticker' column (GAP-06)."""
    result: Dict[str, Dict] = {}
    for row in _load_csv(path):
        key = (_s(row, 'underlying') or _s(row, 'ticker')).upper().strip()
        if key:
            result[key] = row
    return result


def _write_csv(path: str, rows: List[Dict]) -> bool:
    """Write list of dicts to CSV. Auto-creates parent dirs (GAP-04)."""
    if not rows:
        return False
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        return True
    except Exception as e:
        print(f'  ⚠ Error writing {path}: {e}')
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 10 - PIPELINE RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def run_superbrain(
    options_csv:    str,
    dashboard_csv:  str,
    run_id:         str  = '',
    output_dir:     str  = '',
    premarket_mode: bool = False,   # GAP-05: scope to EXECUTE+ARMED only
    eod_mode:       bool = False,   # FIX-PARALYSIS: EOD bypass gates active
    topn: int = 10,
) -> Tuple[List[Dict], str]:
    """
    Main Super Brain pipeline runner.

    eod_mode=True (set by orchestrator --eod flag):
      Injects data_mode="EOD" into every signal row before processing.
      This activates the FIX-PARALYSIS bypass gates in v2.2.0:
        - R:R floor gate warns instead of hard-capping
        - OIS gate warns instead of hard-capping
        - Synthetic mark warns instead of hard-capping
      Use for all evening/batch runs where live chain was not fetched.

    In premarket_mode, scopes to EXECUTE+ARMED signals only - fast re-run
    matching the pattern of run_options_intelligence(premarket_mode=True).

    Returns:
        results    : list of enriched signal dicts
        output_csv : path to superbrain_enriched_<run_id>.csv ('' on failure)
    """
    run_id  = run_id or datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = output_dir or os.path.dirname(os.path.abspath(options_csv))
    os.makedirs(out_dir, exist_ok=True)   # GAP-04

    # Load sector map once at pipeline start (cached after first load)
    _load_sector_map()

    enriched_csv   = os.path.join(out_dir, f'superbrain_enriched_{run_id}.csv')
    execute_csv    = os.path.join(out_dir, f'superbrain_execute_{run_id}.csv')
    inject_csv     = os.path.join(out_dir, f'superbrain_injections_{run_id}.csv')
    summary_json   = os.path.join(out_dir, f'superbrain_summary_{run_id}.json')   # GAP-03
    summary_txt    = os.path.join(out_dir, f'superbrain_summary_{run_id}.txt')

    print(f'\n{"=" * 72}')
    print(f'  AVSHUNTER SUPER BRAIN LAYER {VERSION}')
    print(f'  Run ID      : {run_id}')
    print(f'  Options CSV : {os.path.basename(options_csv)}')
    print(f'  Dashboard   : {os.path.basename(dashboard_csv)}')
    print(f'  Premarket   : {"YES - scoped to EXECUTE+ARMED only" if premarket_mode else "NO - full universe"}')
    print(f'  EOD mode    : {"YES - bypass gates active (v2.2.0)" if eod_mode else "NO - live mode"}')
    print(f'{"=" * 72}\n')

    signals   = _load_csv(options_csv)
    dashboard = _load_dashboard(dashboard_csv)

    if not signals:
        print('  ❌ No signals loaded. Check options CSV path.')
        return [], ''

    # GAP-05: Premarket scope filter
    if premarket_mode:
        scoped = [s for s in signals
                  if _verdict(s) in ('EXECUTE', 'EXECUTE_WITH_RISK', 'ARMED')]
        if scoped:
            print(f'  Premarket scope: {len(scoped)}/{len(signals)} signals (EXECUTE+EXECUTE_WITH_RISK+ARMED)\n')
            signals = scoped
        else:
            print('  ⚠ Premarket scope found 0 EXECUTE/EXECUTE_WITH_RISK/ARMED signals - processing all\n')

    print(f'  Loaded {len(signals)} signals | {len(dashboard)} tickers in dashboard\n')

    # v1.1: Load sector_bias_map from env var (set by orchestrator) for sector alignment
    import json as _json, os as _os
    _sb_sector_bias_map: dict  = {}
    _sb_macro_conviction: float = 0.60
    _sb_sa_mod = None
    try:
        _sbm_raw = _os.environ.get("AVSHUNTER_SECTOR_BIAS_MAP", "")
        if _sbm_raw:
            _sb_sector_bias_map = _json.loads(_sbm_raw)
        _mc_raw = _os.environ.get("AVSHUNTER_MACRO_CONVICTION", "")
        if _mc_raw:
            _sb_macro_conviction = float(_mc_raw)
        # Load sector_alignment module
        import importlib.util as _ilu
        _sa_candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "sector_alignment.py"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "sector_alignment.py"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "sector_alignment.py"),
        ]
        for _sa_path in _sa_candidates:
            if os.path.exists(_sa_path):
                _sa_spec = _ilu.spec_from_file_location("sector_alignment", _sa_path)
                _sb_sa_mod = _ilu.module_from_spec(_sa_spec)
                _sa_spec.loader.exec_module(_sb_sa_mod)
                break
        if _sb_sa_mod and _sb_sector_bias_map:
            print(f"  [SECTOR] Alignment active: {len(_sb_sector_bias_map)} sectors loaded")
        else:
            print("  [SECTOR] sector_alignment.py not found — sector fields will be UNKNOWN")
    except Exception as _sa_err:
        print(f"  [SECTOR] Warning: sector alignment load failed: {_sa_err}")

    results: List[Dict] = []
    stats: Dict[str, int] = {
        'total': 0,
        'execute': 0, 'execute_with_risk': 0, 'armed': 0,
        'watchlist': 0, 'stand_down': 0, 'data_failure': 0,
        'changed': 0,
        'injection': 0, 'core': 0, 'staged': 0, 'avoid': 0,
        'warnings_total': 0, 'vetoes_total': 0,
        'risk_low': 0, 'risk_medium': 0, 'risk_high': 0, 'risk_extreme': 0,
        # GAP-2 (v2.3.0): execution mode counters
        'exec_full': 0, 'exec_reduced': 0, 'exec_probe': 0,
        'exec_wait': 0, 'exec_blocked': 0,
    }

    for row in signals:
        # FIX-PARALYSIS: In EOD mode, stamp data_mode so bypass gates activate
        # for ALL signals regardless of what the upstream pipeline wrote.
        # This ensures the broadened EOD detection in assemble_execution_plan()
        # always sees the correct origin signal, even when data_mode is blank.
        if eod_mode and not premarket_mode:
            if not str(row.get('data_mode', '')).strip():
                row['data_mode'] = 'EOD'
            if not str(row.get('data_source', '')).strip():
                row['data_source'] = 'EOD_PACKAGE'

        ticker   = _ticker(row)
        dash_row = dashboard.get(ticker, {})
        enriched = process_signal(row, dash_row)

        # v1.1: Inject sector alignment fields into enriched row
        if _sb_sa_mod:
            try:
                _sa_result = _sb_sa_mod.classify_from_row(
                    enriched, _sb_sector_bias_map, _sb_macro_conviction
                )
                enriched.update(_sa_result)
            except Exception as _sa_e:
                pass  # non-critical — leave fields absent

        results.append(enriched)

        stats['total'] += 1
        fv   = enriched['sb_final_verdict'].upper()
        rl   = enriched.get('sb_risk_label', 'MEDIUM').upper()
        if fv == 'EXECUTE':            stats['execute']           += 1
        elif fv == 'EXECUTE_WITH_RISK':stats['execute_with_risk'] += 1
        elif fv == 'ARMED':            stats['armed']             += 1
        elif fv == 'WATCHLIST':        stats['watchlist']         += 1
        elif fv == 'STAND_DOWN':       stats['stand_down']        += 1
        elif fv == 'DATA_FAILURE':     stats['data_failure']      += 1

        if enriched.get('sb_verdict_changed') == 'YES':
            stats['changed'] += 1
        stats['warnings_total'] += enriched.get('sb_warnings_count', 0)
        # Count veto codes fired (V1-V8 codes in sb_veto_codes)
        veto_str = enriched.get('sb_veto_codes', '') or ''
        stats['vetoes_total'] += len([v for v in veto_str.split(',') if v.strip()])

        if rl == 'LOW':       stats['risk_low']     += 1
        elif rl == 'MEDIUM':  stats['risk_medium']  += 1
        elif rl == 'HIGH':    stats['risk_high']    += 1
        elif rl == 'EXTREME': stats['risk_extreme'] += 1

        camp = enriched['sb_campaign']
        if camp == 'CONVEXITY_INJECTION': stats['injection'] += 1
        elif camp == 'CORE_CAMPAIGN':     stats['core']      += 1
        elif camp == 'STAGED':            stats['staged']    += 1
        else:                             stats['avoid']     += 1

        # GAP-2 (v2.3.0): count execution modes
        em = enriched.get('sb_execution_mode', 'WAIT')
        if   em == 'FULL_EXECUTE':    stats['exec_full']    += 1
        elif em == 'REDUCED_EXECUTE': stats['exec_reduced'] += 1
        elif em == 'PROBE':           stats['exec_probe']   += 1
        elif em == 'WAIT':            stats['exec_wait']    += 1
        elif em == 'BLOCKED':         stats['exec_blocked'] += 1

        risk_icon = {'LOW': '✅', 'MEDIUM': '⚠️ ', 'HIGH': '🔶', 'EXTREME': '🚨'}.get(rl, '  ')
        chg = ' ⚡' if enriched.get('sb_verdict_changed') == 'YES' else ''
        print(f'  [{ticker:<6}] {enriched["original_verdict"]:>10} → {fv:<18} {risk_icon} | '
              f'Cmp:{camp:<22} Conv:{enriched["sb_conv_score"]}/8 '
              f'W:{enriched.get("sb_warnings_count",0)}{chg}')

    # ── Write output files ────────────────────────────────────────────────────
    _write_csv(enriched_csv, results)

    execute_signals = sorted(
        [r for r in results if r['sb_final_verdict'] in ('EXECUTE', 'EXECUTE_WITH_RISK')],
        key=lambda x: (
            1 if x['sb_final_verdict'] == 'EXECUTE' else 0,  # EXECUTE ranks above EXECUTE_WITH_RISK
            x['sb_conv_score'],
            float(x.get('rr', 0) or 0),
        ),
        reverse=True,
    )
    if execute_signals:
        _write_csv(execute_csv, execute_signals)

    injections = sorted(
        [r for r in results if r['sb_campaign'] == 'CONVEXITY_INJECTION'],
        key=lambda x: x['sb_conv_score'], reverse=True,
    )
    if injections:
        _write_csv(inject_csv, injections)
    # ---------------------------------------------------------------------
    # Monetisation rail: publish a small, human-tradeable shortlist.
    # We always emit a Top-N file so the trader can focus on execution.
    # Ranking: Verdict priority (EXECUTE > ARMED > others) then RR proxy then conviction.
    # ---------------------------------------------------------------------
    verdict_rank = {'EXECUTE': 4, 'EXECUTE_WITH_RISK': 3, 'ARMED': 2, 'WATCHLIST': 1, 'STAND_DOWN': 0, 'DATA_FAILURE': 0}
    ranked = sorted(
        results,
        key=lambda r: (
            verdict_rank.get(str(r.get('sb_final_verdict', 'STAND_DOWN')).upper(), 0),
            float(r.get('rr', 0.0) or 0.0),
            float(r.get('sb_conv_score', 0.0) or 0.0),
            float(r.get('options_score', 0.0) or 0.0),
        ),
        reverse=True
    )
    # Prefer actionable ideas first; if there are fewer than topn, pad with best of the rest.
    actionable = [r for r in ranked if str(r.get('sb_final_verdict', '')).upper() in ('EXECUTE', 'EXECUTE_WITH_RISK', 'ARMED', 'WATCHLIST')]
    shortlist = (actionable + [r for r in ranked if r not in actionable])[: max(1, int(topn or 10))]
    top_csv = os.path.join(out_dir, f"superbrain_top{len(shortlist)}_{run_id}.csv")
    _write_csv(top_csv, shortlist)


    # ── JSON summary (GAP-03) - matches orchestrator integration pattern ──────
    # BUG C FIX (2026-03-05): was reading r.get('sb_vetoes') which does not exist.
    # Correct field is 'sb_veto_codes' (comma-separated, e.g. "V2_NO_RUNWAY,V4_UNCLEAR_STATE").
    # Also read 'sb_veto_adj' for block codes (pipe-separated) to ensure full coverage.
    veto_counts = {}
    for r in results:
        # Primary: clean indexed codes (e.g. "V2_NO_RUNWAY,V4_UNCLEAR_STATE,NONE")
        codes_str = (r.get('sb_veto_codes') or '').strip()
        if codes_str and codes_str != 'NONE':
            for code in codes_str.split(','):
                code = code.strip()
                if code and code != 'NONE':
                    veto_counts[code] = veto_counts.get(code, 0) + 1
        # Secondary: block-level codes from sb_veto_adj (pipe-separated)
        adj_str = (r.get('sb_veto_adj') or '').strip()
        if adj_str and adj_str != 'NONE':
            for part in adj_str.split('|'):
                code = (part.split(':', 1)[0] if ':' in part else part).strip()
                if code and code != 'NONE' and code not in veto_counts:
                    veto_counts[code] = veto_counts.get(code, 0) + 1

    summary_data = {
        'run_id':           run_id,
        'version':          VERSION,
        'generated_at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'premarket_mode':   premarket_mode,
        'signal_counts': {
            'total':            stats['total'],
            'verdicts_changed': stats['changed'],
            'warnings_fired':   stats.get('warnings_total', 0),
        },
        'veto_counts': veto_counts,

        'final_verdicts': {
            'EXECUTE':           stats.get('execute', 0),
            'EXECUTE_WITH_RISK': stats.get('execute_with_risk', 0),
            'ARMED':             stats.get('armed', 0),
            'STAND_DOWN':        stats.get('stand_down', 0),
            'DATA_FAILURE':      stats.get('data_failure', 0),
        },
        'risk_distribution': {
            'LOW':     stats.get('risk_low', 0),
            'MEDIUM':  stats.get('risk_medium', 0),
            'HIGH':    stats.get('risk_high', 0),
            'EXTREME': stats.get('risk_extreme', 0),
        },
        # GAP-2 (v2.3.0): execution mode counts — was always empty before
        # because _compute_execution_mode() was never called.
        'execution_mode_counts': {
            'FULL_EXECUTE':    stats.get('exec_full', 0),
            'REDUCED_EXECUTE': stats.get('exec_reduced', 0),
            'PROBE':           stats.get('exec_probe', 0),
            'WAIT':            stats.get('exec_wait', 0),
            'BLOCKED':         stats.get('exec_blocked', 0),
        },
        'campaign_classification': {
            'CONVEXITY_INJECTION': stats['injection'],
            'CORE_CAMPAIGN':       stats['core'],
            'STAGED':              stats['staged'],
            'AVOID':               stats['avoid'],
        },
        'top_execute': [
            {
                'ticker':        r['ticker'],
                'campaign':      r['sb_campaign'],
                'conv_score':    r['sb_conv_score'],
                'instrument':    r['sb_instrument_now'],
                'size_pct':      r['sb_position_size_pct'],
                'time_stop':     r['sb_time_stop_date'],
                'rr':            r.get('rr', 0),
                'reason':        r['sb_verdict_reason'][:140],
            }
            for r in execute_signals[:10]
        ],
        'top_injections': [
            {
                'ticker':     r['ticker'],
                'conv_score': r['sb_conv_score'],
                'verdict':    r['sb_final_verdict'],
            }
            for r in injections[:5]
        ],
        'output_files': {
            'enriched_csv':   os.path.basename(enriched_csv),
            'execute_csv':    os.path.basename(execute_csv)  if execute_signals else None,
            'injections_csv': os.path.basename(inject_csv)   if injections      else None,
            'summary_json':   os.path.basename(summary_json),
            'summary_txt':    os.path.basename(summary_txt),
        },
    }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(summary_json)), exist_ok=True)
        with open(summary_json, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2)
    except Exception as e:
        print(f'  ⚠ Could not write summary JSON: {e}')

    # ── Plain-text summary ────────────────────────────────────────────────────
    txt_lines = [
        '═' * 72,
        f'  AVSHUNTER SUPER BRAIN LAYER {VERSION} - Run Summary',
        f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}  |  Run: {run_id}',
        '═' * 72, '',
        f'  Signals processed   : {stats["total"]}',
        f'  Verdicts changed    : {stats["changed"]}',
        f'  Vetoes fired (total): {stats.get("vetoes_total", 0)}', '',
        '  FINAL VERDICTS (Post-Superbrain):',
        f'    EXECUTE    : {stats.get("execute", 0)}',
        f'    ARMED      : {stats.get("armed", 0)}',
        f'    WATCHLIST  : {stats.get("watchlist", 0)}',
        f'    STAND_DOWN : {stats.get("stand_down", 0)}', '',
        '  CAMPAIGN CLASSIFICATION:',
        f'    CONVEXITY_INJECTION : {stats["injection"]}',
        f'    CORE_CAMPAIGN       : {stats["core"]}',
        f'    STAGED              : {stats["staged"]}',
        f'    AVOID               : {stats["avoid"]}', '',
        '─' * 72, '  TOP EXECUTE SIGNALS:', '─' * 72,
    ]
    for sig in execute_signals[:10]:
        txt_lines += [
            '',
            f'  {sig["ticker"]:6}  Campaign:{sig["sb_campaign"]}  Conv:{sig["sb_conv_score"]}/8',
            f'  Phase:{sig["phase"]}  DTE:{sig["dte"] or 0:.0f}  R:R:{sig.get("rr") or 0:.2f}  EV:{sig.get("ev") or 0:.3f}',
            f'  Enter: {sig["sb_instrument_now"]}  ({sig["sb_position_size_pct"]}% size)',
            f'  Time-stop: {sig["sb_time_stop_date"]}',
            f'  {sig["sb_verdict_reason"][:90]}',
        ]
    txt_lines += ['', '─' * 72, '  CONVEXITY INJECTIONS:', '─' * 72]
    for sig in injections[:5]:
        txt_lines += [
            '',
            f'  {sig["ticker"]:6}  Conv:{sig["sb_conv_score"]}/8  Verdict:{sig["sb_final_verdict"]}',
            f'  {sig["sb_conv_detail"][:100]}',
        ]
    txt_lines += ['', '═' * 72]
    try:
        with open(summary_txt, 'w', encoding='utf-8') as f:
            f.write('\n'.join(txt_lines))
    except Exception as e:
        print(f'  ⚠ Could not write summary TXT: {e}')

    # ── Console summary ───────────────────────────────────────────────────────
    exe   = stats.get('execute', 0)
    ewrk  = stats.get('execute_with_risk', 0)
    print(f'\n{"═" * 72}')
    print(f'  DECISION MACHINE RESULTS — Run {run_id}')
    print(f'  Signals: {stats["total"]}  |  Changed: {stats["changed"]}')
    print(f'  ✅ EXECUTE:           {exe}')
    print(f'  ⚠️  EXECUTE_WITH_RISK: {ewrk}')
    print(f'  🔶 ARMED:             {stats.get("armed", 0)}')
    print(f'  🚫 STAND_DOWN:        {stats.get("stand_down", 0)}')
    print(f'  ❌ DATA_FAILURE:      {stats.get("data_failure", 0)}')
    print(f'  Warnings fired: {stats.get("warnings_total", 0)}')
    print(f'  Risk: LOW={stats["risk_low"]} MED={stats["risk_medium"]} HIGH={stats["risk_high"]} EXTREME={stats["risk_extreme"]}')
    print(f'  Campaign: INJ={stats["injection"]} CORE={stats["core"]} STAGED={stats["staged"]} AVOID={stats["avoid"]}')
    print(f'  Output: {enriched_csv}')
    print(f'  Summary: {summary_json}')
    print(f'{"═" * 72}\n')

    return results, enriched_csv


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 11 - CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=f'AVSHUNTER Super Brain Layer {VERSION}',
    )
    parser.add_argument('options_csv',   help='Path to options_intelligence_<run_id>.csv')
    parser.add_argument('dashboard_csv', help='Path to master_dashboard.csv')
    parser.add_argument('run_id',        nargs='?', default='',
                        help='Run ID (auto-generated if omitted)')
    parser.add_argument('output_dir',    nargs='?', default='',
                        help='Output directory (defaults to options_csv dir)')
    parser.add_argument('--premarket', action='store_true',
                        help='Scope to EXECUTE+ARMED signals only (fast premarket re-run)')
    parser.add_argument('--eod', action='store_true',
                        help='EOD mode: treat all signals as end-of-day origin. '
                             'Activates paralysis-fix bypass gates (v2.2.0+). '
                             'Set automatically by orchestrator evening workflow.')
    parser.add_argument('--topn', type=int, default=10,
                        help='Emit Top-N shortlist CSV (default 10)')

    args = parser.parse_args()

    results, out_path = run_superbrain(
        options_csv    = args.options_csv,
        dashboard_csv  = args.dashboard_csv,
        run_id         = args.run_id,
        output_dir     = args.output_dir,
        premarket_mode = args.premarket,
        eod_mode       = args.eod,
        topn           = args.topn,
    )

    sys.exit(0 if results else 1)
