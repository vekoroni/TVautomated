r"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘  AVSHUNTER Â· INTELLIGENCE LAB v2.0                                         â•‘
â•‘  Port: 5002                                                                 â•‘
â•‘                                                                             â•‘
â•‘  ARCHITECTURE CHANGE v2.0:                                                 â•‘
â•‘  OLD: superbrain_enriched is the primary signal source (138 cols)          â•‘
â•‘  NEW: eil_enriched is the primary signal source (232 cols)                 â•‘
â•‘       superbrain_enriched retained for sb_final_verdict only               â•‘
â•‘       v5 CSV provides the 32-candidate execution layer                     â•‘
â•‘       All existing merge logic preserved: options, wbs, garch, mv, ct      â•‘
â•‘                                                                             â•‘
â•‘  DATA CONTRACT (what each file contributes):                                â•‘
â•‘    eil_enriched          â†’ signals base, 1312 rows, 232 cols               â•‘
â•‘                            verdicts, EIL scores, EV, triggers, structure   â•‘
â•‘    execution_v3_5        â†’ campaign_verdict, execution_verdict (delta only) â•‘
â•‘    options_intelligence  â†’ opt__ prefix: contract, IV, greeks, walls       â•‘
â•‘    vanguard_signals_e    â†’ vg__ prefix: actuarial, win rate, tier, phase   â•‘
â•‘    wall_break_scores     â†’ wbs__ prefix: 9 BUY_NOW tickers, entry/stop     â•‘
â•‘    eil_enriched (garch)  â†’ garch__ prefix: vol forecasts, jump risk        â•‘
â•‘    garch_forecasts       â†’ garch__ prefix: forward vol, tailwind, method   â•‘
â•‘    morning_validation    â†’ mv__ prefix: live price, drift, TCE             â•‘
â•‘    superbrain_enriched   â†’ sb_final_verdict only                           â•‘
â•‘    AVSHUNTER_SIGNALS_V5  â†’ v5__ prefix: thesis_decision, size, conflicts   â•‘
â•‘                                                                             â•‘
â•‘  PRIORITY RANKING (new pipeline fields):                                   â•‘
â•‘    options_verdict  (22%) campaign_verdict (16%) execution_verdict (12%)   â•‘
â•‘    eil_composite    (14%) ev2_ev_conf_adj  (10%) rr_options        (8%)    â•‘
â•‘    options_score    (8%)  wbs              (5%)  garch_tailwind    (5%)    â•‘
â•‘                                                                             â•‘
â•‘  START:                                                                     â•‘
â•‘    cd C:\Users\ACKVerissimo\intelligence-lab                                â•‘
â•‘    .\venv\Scripts\Activate.ps1                                              â•‘
â•‘    python intelligence_lab.py                                               â•‘
â•‘  OPEN:  http://localhost:5002                                               â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
"""

from flask import Flask, jsonify, send_from_directory, request, Response
from flask_cors import CORS
import os, csv, json, glob, sys, io
from pathlib import Path
from datetime import datetime, timezone

app = Flask(__name__, static_folder="static")
CORS(app)

# â”€â”€â”€ CONFIG â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BASE_DIR = Path(__file__).resolve().parent.parent   # â†’ AVSHUNTER-Intelligence\
RUNS_DIR = BASE_DIR / "data" / "output" / "runs"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from contracts.lab_control import (
    LAB_REQUIRED_FIELDS,
    apply_lab_resolution,
    build_final_run_manifest,
    learning_feedback_from_closed_trades,
    load_final_run_manifest,
    read_final_opportunity_book,
    resolve_lab_tradeability,
    write_final_opportunity_book,
    write_final_run_manifest,
)

_run_cache: dict = {}

PHYSICS_FIELDS = [
    "physics_state_id", "market_energy_score", "compression_energy",
    "directional_force", "force_alignment_score", "trend_inertia",
    "volatility_pressure", "entropy_score", "regime_instability_score",
    "phase_transition_probability", "shock_sensitivity",
    "liquidity_friction_score", "hidden_state_label",
    "state_transition_label", "future_state_5d", "future_state_10d",
    "future_state_20d", "transition_success_5d",
    "transition_success_10d", "transition_success_20d",
]

# â”€â”€â”€ HELPERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _read_csv(path):
    if not path or not Path(path).exists():
        return []
    try:
        with open(path, newline='', encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        print(f"  âš  CSV read error [{Path(path).name}]: {e}")
        return []

def _read_json(path):
    if not path or not Path(path).exists():
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  âš  JSON read error [{Path(path).name}]: {e}")
        return {}

def _glob_first(folder, pattern):
    folder = Path(folder)
    matches = sorted(folder.glob(pattern)) if folder.exists() else []
    return matches[-1] if matches else None

def _glob_latest(folder, pattern):
    """Return the most recently modified match."""
    folder = Path(folder)
    matches = list(folder.glob(pattern)) if folder.exists() else []
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None

def _file_signature(path):
    if not path:
        return {"path": "", "mtime_ns": 0, "size": 0}
    path = Path(path)
    if not path.exists():
        return {"path": str(path), "mtime_ns": 0, "size": 0}
    stat = path.stat()
    return {"path": str(path), "mtime_ns": int(stat.st_mtime_ns), "size": int(stat.st_size)}

def _morning_handoff_paths(run_dir, sb_dir, run_id):
    mv_dir = Path(run_dir) / "morning_validation"
    mv_path = _glob_first(mv_dir, f"morning_validated_trades_{run_id}.csv")
    if not mv_path:
        mv_path = _glob_first(mv_dir, "morning_validated_trades_*.csv")
    if not mv_path:
        mv_path = _glob_first(sb_dir, "morning_validation_*.csv")

    packet_path = _glob_first(mv_dir, f"morning_validation_packet_{run_id}.json")
    if not packet_path:
        packet_path = _glob_first(mv_dir, "morning_validation_packet_*.json")

    eod_path = _glob_first(mv_dir, f"morning_candidates_{run_id}.csv")
    if not eod_path:
        eod_path = _glob_first(mv_dir, "morning_candidates_*.csv")

    return {
        "morning_validation": mv_path,
        "morning_packet": packet_path,
        "eod_candidates": eod_path,
    }

def _lab_cache_signature(run_id):
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return {}
    sb_dir = _find_superbrain_dir(run_dir)
    paths = _morning_handoff_paths(run_dir, sb_dir, run_id)
    return {name: _file_signature(path) for name, path in paths.items()}

def _utc_iso():
    return datetime.now(timezone.utc).isoformat()

def _filter_to_handoff_signals(base_rows, handoff_maps):
    """Use the final handoff slate as the Lab queue when it exists."""
    handoff_tickers = []
    for mapping in handoff_maps:
        for ticker in mapping:
            if ticker and ticker not in handoff_tickers:
                handoff_tickers.append(ticker)
    if not handoff_tickers:
        return list(base_rows), []

    base_by_ticker = {
        str(row.get("ticker", "") or "").upper().strip(): row
        for row in base_rows
        if str(row.get("ticker", "") or "").strip()
    }
    filtered = []
    missing = []
    for ticker in handoff_tickers:
        row = base_by_ticker.get(ticker)
        if row:
            filtered.append(row)
        else:
            filtered.append({"ticker": ticker})
            missing.append(ticker)
    return filtered, missing


def _list_runs():
    if not RUNS_DIR.exists():
        return []
    runs = [d.name for d in RUNS_DIR.iterdir() if d.is_dir() and d.name.lower() != "latest"]
    runs = sorted(runs, reverse=True)
    latest_path = BASE_DIR / "data" / "output" / "latest.json"
    try:
        latest = _read_json(latest_path).get("run_id", "")
        if latest in runs:
            runs.remove(latest)
            runs.insert(0, latest)
    except Exception:
        pass
    return runs

def _latest_run_id():
    runs = _list_runs()
    return runs[0] if runs else ""

def _latest_manifest():
    run_id = _latest_run_id()
    if not run_id:
        return {}
    manifest = load_final_run_manifest(run_id, RUNS_DIR)
    return manifest or write_final_run_manifest(run_id, RUNS_DIR)

def _safe_open_journal_positions():
    try:
        if not _JOURNAL_DB.exists():
            return []
        from avshunter_trade_journal import get_open_positions
        return get_open_positions(_JOURNAL_DB)
    except Exception:
        return []

_LAB_JOURNAL_COLS = {
    "trade_idea_id": "TEXT",
    "declared_R": "REAL",
    "premium_risk_total": "REAL",
    "journal_entry_source": "TEXT",
    "journal_open_status": "TEXT",
    "lab_display_verdict": "TEXT",
    "lab_action_category": "TEXT",
    "lab_campaign": "TEXT",
    "lab_execution_mode": "TEXT",
    "lab_tradeable": "INTEGER",
    "lab_conflict_state": "TEXT",
    "execution_lock_reason": "TEXT",
    "time_horizon": "TEXT",
    "hold_period": "TEXT",
    "hold_urgency": "TEXT",
    "horizon_hold_alignment": "TEXT",
    "horizon_action": "TEXT",
    "horizon_pressure": "TEXT",
    "horizon_source": "TEXT",
    "execution_category": "TEXT",
    "effective_execution_verdict": "TEXT",
    "eod_candidate_status": "TEXT",
    "eod_candidate_reason": "TEXT",
    "morning_execution_permission": "TEXT",
    "morning_execution_route": "TEXT",
    "morning_live_validation_state": "TEXT",
    "morning_validation_score": "REAL",
    "morning_lab_alignment_status": "TEXT",
    "morning_lab_alignment_reason": "TEXT",
    "options_research_permission": "TEXT",
    "options_research_route": "TEXT",
    "options_research_score": "REAL",
    "options_hard_vetoes": "TEXT",
    "contract_snapshot_json": "TEXT",
    "trigger_primary": "TEXT",
    "trigger_quality": "TEXT",
    "trigger_score": "REAL",
    "trigger_codes": "TEXT",
    "catalyst_inside_dte": "TEXT",
    "user_confirmed_live_validation": "INTEGER",
    "priority_rank": "INTEGER",
    "priority_score": "REAL",
    "lab_verdict": "TEXT",
    "physics_state_id": "TEXT",
    "hidden_state_label": "TEXT",
    "state_transition_label": "TEXT",
    "macro_regime": "TEXT",
    "actuarial_match_method": "TEXT",
    "actuarial_match_type": "TEXT",
    "actuarial_ev_weight": "REAL",
    "behaviour_state_key": "TEXT",
    "behaviour_state_hash": "TEXT",
    "catalyst_overlay": "TEXT",
    "source_payload_json": "TEXT",
    "lab_packet_json": "TEXT",
    "competition_trade_id": "TEXT",
    "scale_plan": "TEXT",
}

_EMPTY_SIGNAL_VALUES = {"", "NONE", "N/A", "NA", "UNKNOWN", "NULL", "NAN", "UNROUTED"}

def _first_signal_value(row, keys, default=""):
    for key in keys:
        value = row.get(key) if isinstance(row, dict) else None
        cleaned = str(value).strip() if value is not None else ""
        if cleaned and cleaned.upper() not in _EMPTY_SIGNAL_VALUES:
            return cleaned
    return default

def _first_numeric_signal_value(row, keys, default=0.0, prefer_nonzero=True):
    first_valid = None
    for key in keys:
        value = row.get(key) if isinstance(row, dict) else None
        cleaned = str(value).strip() if value is not None else ""
        if not cleaned or cleaned.upper() in _EMPTY_SIGNAL_VALUES:
            continue
        try:
            number = float(cleaned)
        except Exception:
            continue
        if first_valid is None:
            first_valid = number
        if not prefer_nonzero or abs(number) > 0:
            return number
    return first_valid if first_valid is not None else default

def _safe_float(value, default=0.0):
    try:
        cleaned = str(value).strip()
        if not cleaned or cleaned.upper() in _EMPTY_SIGNAL_VALUES:
            return default
        return float(cleaned)
    except Exception:
        return default

def _safe_int(value, default=0):
    try:
        return int(float(_safe_float(value, default)))
    except Exception:
        return default

def _set_signal_value(row, key, value, overwrite_empty=True):
    cleaned = str(value).strip() if value is not None else ""
    if not cleaned or cleaned.upper() in _EMPTY_SIGNAL_VALUES:
        return
    current = row.get(key)
    current_clean = str(current).strip() if current is not None else ""
    if overwrite_empty and (not current_clean or current_clean.upper() in _EMPTY_SIGNAL_VALUES):
        row[key] = value
    elif not overwrite_empty:
        row[key] = value

def _infer_pipeline_mode(eil_rows, mv_rows):
    if mv_rows:
        return "MORNING_VALIDATION"
    modes = {
        str(row.get("eil_data_mode") or row.get("data_mode") or "").upper()
        for row in (eil_rows or [])
    }
    live_tokens = ("LIVE", "INTRADAY", "MARKET_OPEN", "REALTIME", "REAL_TIME")
    if any(any(token in mode for token in live_tokens) for mode in modes):
        return "LIVE_EOD"
    return "EOD"

def _norm_horizon_label(value):
    raw = str(value or "").strip()
    key = raw.upper().replace(" ", "_")
    if key in _EMPTY_SIGNAL_VALUES:
        return ""
    labels = {
        "1_5D": "1-5D",
        "1-5D": "1-5D",
        "1_TO_5D": "1-5D",
        "6_10D": "6-10D",
        "6-10D": "6-10D",
        "6_TO_10D": "6-10D",
        "11_20D": "11-20D",
        "11-20D": "11-20D",
        "11_TO_20D": "11-20D",
        "5D": "5D",
        "10D": "10D",
        "20D": "20D",
    }
    return labels.get(key, raw.replace("_", "-"))

def _extract_time_horizon(sig):
    routed = _norm_horizon_label(_first_signal_value(sig, [
        "eod__horizon_bucket", "horizon_bucket", "exe__horizon_bucket",
        "vg__horizon_bucket", "wbs__horizon_bucket", "opt__horizon_bucket",
    ]))
    if routed:
        return routed
    preferred = _norm_horizon_label(_first_signal_value(sig, [
        "eod__layer2__preferred_horizon", "layer2__preferred_horizon",
        "exe__layer2__preferred_horizon", "vg__layer2__preferred_horizon",
        "opt__layer2__preferred_horizon", "eod__macro_preferred_horizon",
        "macro_preferred_horizon", "exe__macro_preferred_horizon",
        "vg__macro_preferred_horizon", "opt__macro_preferred_horizon",
    ]))
    if preferred:
        return preferred
    hold = _extract_hold_period(sig)
    if hold:
        return hold.replace(" days", "d").replace(" day", "d")
    dte = _first_signal_value(sig, ["contract_dte", "opt__contract_dte", "exe__contract_dte", "dte", "opt__dte", "vg__dte"])
    try:
        dte_f = float(dte)
        if dte_f > 0:
            return f"{round(dte_f)}D DTE"
    except Exception:
        pass
    return ""

def _extract_hold_period(sig):
    return _first_signal_value(sig, ["hold_label", "opt__hold_label", "exe__hold_label", "vg__hold_label", "doss__opt__hold_label"])

def _extract_execution_category(sig):
    for key in [
        "display_morning_execution_permission", "morning_execution_permission",
        "mv__morning_execution_permission", "mv_morning_execution_permission",
        "display_eod_candidate_status",
        "lab_execution_status",
        "eod_candidate_status", "candidate_status", "effective_execution_verdict",
        "execution_verdict", "sb_execution_mode", "pse_execution_mode",
        "options_verdict", "lab_verdict", "sb_final_verdict",
    ]:
        value = str(sig.get(key, "") or "").strip().upper().replace(" ", "_")
        if value and value not in _EMPTY_SIGNAL_VALUES:
            return value
    return "UNCATEGORISED"

def _max_days(label):
    import re
    nums = [int(float(n)) for n in re.findall(r"\d+(?:\.\d+)?", str(label or ""))]
    return max(nums) if nums else None

def _horizon_hold_alignment(sig):
    horizon = _extract_time_horizon(sig)
    hold = _extract_hold_period(sig)
    h_max, hold_max = _max_days(horizon), _max_days(hold)
    if h_max is None or hold_max is None:
        return "UNKNOWN"
    if hold_max <= h_max + 3:
        return "ALIGNED"
    if hold_max > h_max + 3:
        return "HOLD_LONGER_THAN_HORIZON"
    return "HOLD_SHORTER_THAN_HORIZON"

def _contract_horizon_type(horizon):
    value = str(horizon or "").upper()
    if value.startswith("1-5") or value == "5D":
        return "5D"
    if value.startswith("6-10") or value == "10D":
        return "10D"
    if value.startswith("11-20") or value == "20D":
        return "20D"
    days = _max_days(value)
    if days is not None:
        return "5D" if days <= 5 else "10D" if days <= 10 else "20D"
    return "20D"

def _ensure_lab_journal_columns(conn):
    for table in ("trades", "closed_trades"):
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, col_type in _LAB_JOURNAL_COLS.items():
            if col not in existing:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                except Exception:
                    pass

def _update_lab_journal_row(trade_id, sig, body, premium_risk_total):
    try:
        from avshunter_trade_journal import get_db
        conn = get_db(_JOURNAL_DB)
        _ensure_lab_journal_columns(conn)
        lab_action_category = sig.get("display_execution_category") or _extract_execution_category(sig)
        eod_candidate_status = sig.get("display_eod_candidate_status") or sig.get("eod_candidate_status", "")
        morning_permission = _first_signal_value(sig, [
            "display_morning_execution_permission", "morning_execution_permission",
            "mv__morning_execution_permission", "mv_morning_execution_permission",
            "mv_execution_permission", "mv__execution_permission",
        ])
        morning_route = _first_signal_value(sig, [
            "display_morning_execution_route", "morning_execution_route",
            "mv__morning_execution_route", "mv_morning_execution_route",
            "morning_execution_lane", "mv__morning_execution_lane",
        ])
        options_route = _first_signal_value(sig, [
            "display_options_research_route", "options_research_route",
            "final_route", "eod__options_research_route", "eod__final_route",
            "opt__final_route",
        ])
        options_permission = _first_signal_value(sig, [
            "options_research_permission", "eod__options_research_permission",
            "opt__execution_permission",
        ])
        options_hard_vetoes = _first_signal_value(sig, [
            "options_hard_vetoes", "hard_vetoes", "eod__options_hard_vetoes",
            "eod__hard_vetoes", "opt__hard_vetoes",
        ])
        contract_snapshot = {
            "ticker": sig.get("ticker", ""),
            "direction": sig.get("direction", ""),
            "instrument": sig.get("sb_instrument_now") or sig.get("options_strategy") or sig.get("opt__options_strategy", ""),
            "strike": sig.get("strike") or sig.get("contract_strike") or sig.get("opt__contract_strike", ""),
            "expiry": sig.get("expiry") or sig.get("contract_expiry") or sig.get("opt__contract_expiry", ""),
            "dte": sig.get("dte") or sig.get("contract_dte") or sig.get("opt__contract_dte", ""),
            "premium_mid": sig.get("premium_mid") or sig.get("premium") or sig.get("opt__premium_mid") or sig.get("opt__premium", ""),
            "spread_pct": sig.get("spread_pct") or sig.get("contract_spread_pct") or sig.get("opt__contract_spread_pct", ""),
            "rr": sig.get("rr") or sig.get("rr_options", ""),
            "ev": sig.get("ev") or sig.get("ev2_ev_conf_adj", ""),
            "invalidation_price": sig.get("invalidation_price", ""),
            "target_price": sig.get("target_price") or sig.get("opt__structural_target", ""),
        }
        lab_packet_fields = list(dict.fromkeys(LAB_REQUIRED_FIELDS + [
            "display_execution_category", "display_final_verdict",
            "display_eod_candidate_status", "display_morning_execution_permission",
            "display_morning_execution_route", "display_options_research_route",
            "display_morning_lab_alignment_status",
            "morning_lab_alignment_status", "morning_lab_alignment_reason",
            "options_research_permission", "options_research_route",
            "options_research_score", "hard_vetoes",
            "eod_candidate_status", "morning_execution_permission",
            "morning_execution_route", "time_horizon", "hold_label",
            "trigger_primary", "trigger_quality", "trigger_score", "trigger_codes",
            "actuarial_match_type", "actuarial_ev_weight",
            "behaviour_state_key", "behaviour_state_hash", "catalyst_overlay",
            "vg__actuarial_match_type", "vg__actuarial_ev_weight",
            "vg__behaviour_state_key", "vg__behaviour_state_hash", "vg__catalyst_overlay",
        ]))
        payload = {
            "trade_idea_id": sig.get("trade_idea_id", ""),
            "declared_R": float(body.get("declared_R", premium_risk_total) or premium_risk_total),
            "premium_risk_total": premium_risk_total,
            "journal_entry_source": "INTELLIGENCE_LAB_MANUAL_ENTRY",
            "journal_open_status": "OPEN_MANUAL",
            "lab_display_verdict": sig.get("display_final_verdict") or sig.get("lab_verdict", ""),
            "lab_action_category": lab_action_category,
            "lab_campaign": sig.get("display_campaign") or sig.get("sb_campaign") or sig.get("campaign_verdict", ""),
            "lab_execution_mode": sig.get("display_execution_mode") or sig.get("sb_execution_mode") or sig.get("execution_verdict", ""),
            "lab_tradeable": 1 if (sig.get("lab_tradeable") is True or str(sig.get("lab_tradeable")).lower() == "true") else 0,
            "lab_conflict_state": sig.get("conflict_state", ""),
            "execution_lock_reason": sig.get("execution_lock_reason", ""),
            "time_horizon": _extract_time_horizon(sig),
            "hold_period": _extract_hold_period(sig),
            "hold_urgency": _first_signal_value(sig, ["hold_urgency", "opt__hold_urgency", "exe__hold_urgency", "vg__hold_urgency", "doss__opt__hold_urgency"]),
            "horizon_hold_alignment": _horizon_hold_alignment(sig),
            "horizon_action": _first_signal_value(sig, ["eod__horizon_action", "horizon_action", "exe__horizon_action", "vg__horizon_action"]),
            "horizon_pressure": _first_signal_value(sig, ["eod__horizon_pressure", "horizon_pressure", "exe__horizon_pressure", "vg__horizon_pressure", "opt__horizon_pressure"]),
            "horizon_source": _first_signal_value(sig, ["eod__horizon_source", "horizon_source", "exe__horizon_source", "vg__horizon_source"]),
            "execution_category": lab_action_category,
            "effective_execution_verdict": sig.get("effective_execution_verdict", ""),
            "eod_candidate_status": eod_candidate_status,
            "eod_candidate_reason": sig.get("eod_candidate_reason", ""),
            "morning_execution_permission": morning_permission,
            "morning_execution_route": morning_route,
            "morning_live_validation_state": _first_signal_value(sig, ["mv__live_validation_state", "live_validation_state", "mv_verdict", "mv__verdict"]),
            "morning_validation_score": _safe_float(_first_signal_value(sig, ["mv__validation_score", "validation_score", "mv_validation_score"], "0")),
            "morning_lab_alignment_status": sig.get("morning_lab_alignment_status", ""),
            "morning_lab_alignment_reason": sig.get("morning_lab_alignment_reason", ""),
            "options_research_permission": options_permission,
            "options_research_route": options_route,
            "options_research_score": _safe_float(_first_signal_value(sig, ["options_research_score", "eod__options_research_score", "opt__options_research_score"], "0")),
            "options_hard_vetoes": options_hard_vetoes,
            "contract_snapshot_json": json.dumps(contract_snapshot, ensure_ascii=True, default=str),
            "trigger_primary": _first_signal_value(sig, ["trigger_primary", "eod__trigger_primary", "vg__trigger_primary", "catalyst_type", "eod__catalyst_type"]),
            "trigger_quality": _first_signal_value(sig, ["trigger_quality", "eod__trigger_quality", "vg__trigger_quality", "catalyst_event_status", "eod__catalyst_event_status"]),
            "trigger_score": _safe_float(_first_signal_value(sig, ["trigger_score", "eod__trigger_score", "vg__trigger_score", "catalyst_truth_score", "eod__catalyst_truth_score"], "0")),
            "trigger_codes": _first_signal_value(sig, ["trigger_codes", "eod__trigger_codes", "vg__trigger_codes", "catalyst_reason_codes", "eod__catalyst_reason_codes"]),
            "catalyst_inside_dte": _first_signal_value(sig, ["catalyst_inside_dte", "eod__catalyst_inside_dte", "opt__catalyst_inside_dte", "vg__catalyst_inside_dte"]),
            "user_confirmed_live_validation": 1 if body.get("user_confirmed_live_validation") else 0,
            "priority_rank": _safe_int(sig.get("priority_rank", 0)),
            "priority_score": _safe_float(sig.get("priority_score", 0)),
            "lab_verdict": sig.get("lab_verdict", ""),
            "physics_state_id": sig.get("physics_state_id", ""),
            "hidden_state_label": sig.get("hidden_state_label", ""),
            "state_transition_label": sig.get("state_transition_label", ""),
            "macro_regime": sig.get("macro_regime_label") or sig.get("macro_regime", ""),
            "actuarial_match_method": sig.get("layer2__state_match_method") or sig.get("vg__layer2__state_match_method", ""),
            "actuarial_match_type": _first_signal_value(sig, ["actuarial_match_type", "vg__actuarial_match_type"]),
            "actuarial_ev_weight": _safe_float(_first_signal_value(sig, ["actuarial_ev_weight", "vg__actuarial_ev_weight"], "0")),
            "behaviour_state_key": _first_signal_value(sig, ["behaviour_state_key", "vg__behaviour_state_key"]),
            "behaviour_state_hash": _first_signal_value(sig, ["behaviour_state_hash", "vg__behaviour_state_hash"]),
            "catalyst_overlay": _first_signal_value(sig, ["catalyst_overlay", "vg__catalyst_overlay"]),
            "source_payload_json": json.dumps(sig, ensure_ascii=True, default=str),
            "lab_packet_json": json.dumps({k: sig.get(k) for k in lab_packet_fields}, ensure_ascii=True, default=str),
            "competition_trade_id": str(body.get("competition_trade_id", "")),
            "scale_plan": json.dumps(body.get("scale_plan", ""), ensure_ascii=True, default=str),
        }
        assignments = ", ".join(f"{k}=:{k}" for k in payload)
        conn.execute(
            f"UPDATE trades SET {assignments} WHERE trade_id=:trade_id",
            {**payload, "trade_id": int(trade_id)},
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"  journal lab metadata update failed: {exc}")

def _carry_lab_closed_metadata(trade_id, snapshot):
    if not snapshot:
        return
    try:
        from avshunter_trade_journal import get_db
        conn = get_db(_JOURNAL_DB)
        _ensure_lab_journal_columns(conn)
        payload = {k: snapshot.get(k) for k in _LAB_JOURNAL_COLS}
        assignments = ", ".join(f"{k}=:{k}" for k in payload)
        conn.execute(
            f"UPDATE closed_trades SET {assignments} WHERE trade_id=:trade_id",
            {**payload, "trade_id": int(trade_id)},
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"  closed trade lab metadata carry failed: {exc}")

def _closed_trade_rows():
    try:
        if not _JOURNAL_DB.exists():
            return []
        from avshunter_trade_journal import get_db
        conn = get_db(_JOURNAL_DB)
        _ensure_lab_journal_columns(conn)
        cur = conn.execute("SELECT * FROM closed_trades ORDER BY exit_date DESC, trade_id DESC")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if rows else []
        conn.close()
        return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []

def _find_superbrain_dir(run_dir):
    run_dir = Path(run_dir)
    if not run_dir.exists():
        return run_dir / "superbrain"
    exact = run_dir / "superbrain"
    if exact.exists() and list(exact.glob("superbrain_enriched_*.csv")):
        return exact
    candidates = sorted(
        [d for d in run_dir.iterdir()
         if d.is_dir() and d.name.startswith("superbrain")
         and list(d.glob("superbrain_enriched_*.csv"))],
        key=lambda d: d.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else exact

def _normalise_macro(m):
    if not isinstance(m, dict):
        return {}
    return {
        "regime_state": str(m.get("regime_state") or m.get("regime") or ""),
        "risk_switch":  str(m.get("risk_on_off_switch") or m.get("risk_switch") or ""),
        "vol_mode":     str(m.get("vol_mode") or ""),
        "sector_tilt":  str(m.get("sector_tilt") or ""),
        "conviction":   m.get("macro_conviction") or m.get("conviction") or "",
        "regime_drift": str(m.get("regime_drift_status") or m.get("regime_drift") or ""),
    }

# â”€â”€â”€ PRIORITY SCORING (pipeline-native fields) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _compute_priority_score(sig):
    """
    Priority score built entirely from new pipeline fields.
    Replaces the superbrain-era score that needed sb_final_verdict,
    sb_campaign, sb_execution_mode, sb_conv_score, sb_risk_label.

    Weights (sum to 1.0):
      options_verdict    0.22  â€” options layer verdict
      campaign_verdict   0.16  â€” campaign readiness
      execution_verdict  0.12  â€” execution gate
      eil_composite      0.14  â€” EIL execution quality
      ev2_ev_conf_adj    0.10  â€” EV engine (post-fix: 0.003â€“0.625)
      rr_options         0.08  â€” risk/reward
      options_score      0.08  â€” options contract quality
      wbs                0.05  â€” wall break score (icing)
      garch_tailwind     0.05  â€” vol state from GARCH
    """
    def _f(key, default=0.0):
        try:
            v = sig.get(key, "") or ""
            s = str(v).strip()
            if s in ("", "None", "nan", "N/A"):
                return default
            return float(s)
        except:
            return default

    def _s(key):
        return str(sig.get(key, "") or "").upper().strip()

    ov     = _s("options_verdict") or _s("opt__options_verdict")
    cv     = _s("campaign_verdict") or _s("eil__campaign_verdict")
    ev     = _s("execution_verdict") or _s("eil__execution_verdict")
    eil_c  = _f("eil_composite_score") or _f("eil__composite_score")
    ev_adj = _f("ev2_ev_conf_adj") or _f("eil__ev2_ev_conf_adj")
    rr     = _f("rr_options") or _f("opt__rr_options")
    opt_s  = _f("options_score") or _f("opt__options_score")
    wbs_g  = _s("wbs__wbs_grade") or _s("wbs__grade")
    wbs_s  = _f("wbs__wbs") or _f("wbs__wbs_score")
    tail   = _f("garch__l3_iv_tailwind_score")

    # Verdict dimension
    w_ov = {"EXECUTE": 1.0, "ARMED": 0.35, "STAND_DOWN": 0.0,
            "EXECUTE_WITH_CAUTION": 0.70, "WATCHLIST": 0.10}.get(ov, 0.0) * 0.22

    # Campaign dimension
    w_cv = {"READY_EXECUTE": 1.0, "READY_PROBE": 0.50}.get(cv, 0.0) * 0.16

    # Execution gate
    w_ev = {"BUY_NOW": 1.0, "WAIT_RETEST": 0.20}.get(ev, 0.0) * 0.12

    # EIL composite
    w_eil = min(eil_c / 100, 1.0) * 0.14

    # EV engine â€” range is 0.002â€“0.025 pre-fix, 0.003â€“0.625 post-fix
    w_ev2 = min(max((ev_adj + 0.25) / 0.50, 0), 1) * 0.10

    # RR
    w_rr = (min(rr / 3.0, 1.0) if rr > 0 else 0) * 0.08

    # Options score
    w_opt = min(opt_s / 100, 1.0) * 0.08

    # WBS â€” icing, not gate
    wbs_mult = {"PROBABLE": 1.0, "POSSIBLE": 0.6, "UNLIKELY": 0.2}.get(wbs_g, 0)
    w_wbs = (wbs_s / 100) * wbs_mult * 0.05

    # GARCH vol state â€” cheap vol = buying edge
    w_gar = (1.0 if tail < -0.03 else 0.5 if abs(tail) <= 0.03 else 0.1) * 0.05

    raw = (w_ov + w_cv + w_ev + w_eil + w_ev2 + w_rr + w_opt + w_wbs + w_gar) * 100
    return round(min(raw, 100), 1)

def _lab_token(value):
    text = str(value or "").strip()
    if not text:
        return ""
    token = text.upper().replace(" ", "_").replace("-", "_")
    if token in {"NONE", "N/A", "NA", "UNKNOWN", "NULL", "NAN", "UNROUTED"}:
        return ""
    return token

def _first_lab_value(sig, *keys):
    for key in keys:
        value = sig.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and _lab_token(text):
            return text
    return ""

def _first_lab_token(sig, *keys):
    return _lab_token(_first_lab_value(sig, *keys))

def _is_lab_audit_only(sig):
    """Rows rejected by morning validation should remain visible for audit, not in the action queue."""
    verdict = _first_lab_token(sig, "lab_verdict", "display_final_verdict", "sb_final_verdict")
    permission = _first_lab_token(
        sig,
        "display_morning_execution_permission",
        "morning_execution_permission",
        "mv__morning_execution_permission",
        "mv_morning_execution_permission",
        "mv_execution_permission",
        "mv__execution_permission",
    )
    route = _first_lab_token(
        sig,
        "display_morning_execution_route",
        "morning_execution_route",
        "mv__morning_execution_route",
        "mv_morning_execution_route",
        "morning_execution_lane",
        "mv__morning_execution_lane",
    )
    live_state = _first_lab_token(
        sig,
        "live_validation_state",
        "mv__live_validation_state",
        "mv_live_validation_state",
        "validation_state",
        "mv__validation_state",
    )
    thesis_state = _first_lab_token(
        sig,
        "thesis_validity_state",
        "mv__thesis_validity_state",
        "mv_thesis_validity_state",
    )
    conflict_state = _first_lab_token(sig, "conflict_state")
    veto_text = _first_lab_value(sig, "veto_flags", "conflict_flags", "execution_lock_reason")
    veto_token = _lab_token(veto_text)

    return (
        verdict == "BLOCKED"
        or permission == "BLOCKED"
        or route in {"STAND_DOWN", "BLOCKED"}
        or live_state in {"REJECTED", "BLOCKED"}
        or thesis_state in {"BROKEN", "INVALIDATED", "THESIS_BROKEN"}
        or (conflict_state == "HARD_CONFLICT" and "MORNING_VALIDATION_BLOCKED" in veto_token)
    )

def _lab_priority_bucket(sig):
    if _is_lab_audit_only(sig):
        return 90, "BLOCKED_AUDIT"

    verdict = _first_lab_token(sig, "lab_verdict", "display_final_verdict", "sb_final_verdict")
    permission = _first_lab_token(
        sig,
        "display_morning_execution_permission",
        "morning_execution_permission",
        "mv__morning_execution_permission",
        "mv_morning_execution_permission",
        "mv_execution_permission",
        "mv__execution_permission",
    )
    route = _first_lab_token(
        sig,
        "display_morning_execution_route",
        "morning_execution_route",
        "mv__morning_execution_route",
        "mv_morning_execution_route",
        "morning_execution_lane",
        "mv__morning_execution_lane",
    )
    eod_status = _first_lab_token(sig, "display_eod_candidate_status", "eod_candidate_status", "candidate_status")

    if verdict in {"GO", "GO_LIMIT"} or permission in {"GO", "GO_LIMIT"}:
        return 0, "ACTIONABLE"
    if verdict in {"PROBE", "EOD_EXEC"} or permission == "PROBE":
        return 1, "PROBE"
    if verdict == "CONTRACT_REPAIR" or permission == "CONTRACT_REPAIR":
        return 2, "CONTRACT_REPAIR"
    if verdict == "ARMED" or permission == "ARMED":
        return 3, "ARMED"
    if verdict == "WAIT" or permission == "WAIT" or route.startswith("WAIT"):
        return 4, "WAIT"
    if verdict == "EOD_CAUTION" or "CAUTION" in verdict:
        return 5, "EOD_CAUTION"
    if eod_status:
        return 6, "EOD_REVIEW"
    return 7, "RESEARCH_REVIEW"

def _finalise_lab_priority_ranking(signals):
    for sig in signals:
        raw = sig.get("research_priority_score", sig.get("priority_score", 0))
        try:
            raw_score = float(raw)
        except Exception:
            raw_score = float(_compute_priority_score(sig))

        bucket, label = _lab_priority_bucket(sig)
        sig["research_priority_score"] = round(raw_score, 1)
        sig["lab_action_bucket"] = bucket
        sig["lab_action_bucket_label"] = label
        sig["lab_hidden_by_default"] = bucket >= 90
        sig["priority_score"] = 0.0 if bucket >= 90 else round(raw_score, 1)

        if bucket >= 90:
            sig["lab_actionability_reason"] = _first_lab_value(
                sig,
                "rejection_reason",
                "mv__rejection_reason",
                "execution_lock_reason",
                "morning_lab_alignment_reason",
                "negative_factors",
            ) or "Blocked by morning validation."

    ranked = sorted(
        signals,
        key=lambda row: (
            int(row.get("lab_action_bucket", 99)),
            -float(row.get("research_priority_score", 0) or 0),
            str(row.get("ticker", "")),
        ),
    )
    for rank, sig in enumerate(ranked, 1):
        sig["priority_rank"] = rank

# â”€â”€â”€ CONVEXITY CHECKS (pipeline-native) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _compute_conv_checks(sig):
    """
    Replaces sb_c_compression/energy/underpriced_vol/gamma_proximity/runway
    with pipeline-native equivalents.
    """
    def _f(key, d=0.0):
        try:
            v = sig.get(key) or d
            return float(str(v).strip()) if str(v).strip() not in ("","None","nan") else d
        except: return d
    def _s(key):
        return str(sig.get(key,"") or "").upper().strip()

    # 1. Compression: Crabel state is COILING or CRABEL_READY
    crabel = _s("crabel_state") or _s("eil__crabel_state")
    c_compression = "Y" if crabel in ("COILING", "CRABEL_READY") else "N"

    # 2. Energy: PCR signal or OBI score
    pcr = _s("pcr_signal") or _s("opt__pcr_signal")
    obi = _f("eil_obi_score") or _f("eil__obi_score")
    c_energy = "Y" if pcr in ("BULLISH","NEUTRAL") and obi >= 65 else "N"

    # 3. Underpriced vol: iv_rank < 30 or garch tailwind negative (cheap vol)
    iv_r = _f("iv_rank") or _f("opt__iv_rank")
    tail = _f("garch__l3_iv_tailwind_score")
    c_vol = "Y" if (0 < iv_r < 30) or tail < -0.03 else "N"

    # 4. Gamma proximity: within 7% of call/put wall
    price = _f("underlying_price") or _f("current_price") or _f("signal_price")
    cw = _f("call_wall") or _f("opt__call_wall") or _f("wbs__call_wall")
    pw = _f("put_wall")  or _f("opt__put_wall")  or _f("wbs__put_wall")
    near_wall = False
    if price > 0:
        if cw > 0 and abs(price - cw) / price <= 0.07: near_wall = True
        if pw > 0 and abs(price - pw) / price <= 0.07: near_wall = True
    c_gamma = "Y" if near_wall else "N"

    # 5. Runway: runway_to_wall_pct > 10 (AT&T principle: wall is icing)
    #    OR structural_target exists and is meaningfully different from price
    runway = _f("runway_to_wall_pct") or _f("wbs__runway_to_wall_pct")
    target = _f("structural_target") or _f("opt__structural_target")
    has_runway = runway > 10 if runway > 0 else (target > 0 and price > 0 and abs(target - price) / price > 0.05)
    c_runway = "Y" if has_runway else "N"

    # Conviction score: count Y checks + quality bonus
    checks = [c_compression, c_energy, c_vol, c_gamma, c_runway]
    score = sum(1 for c in checks if c == "Y")

    # Bonus pts from EIL composite (max 3)
    eil_c = _f("eil_composite_score") or _f("eil__composite_score")
    bonus = 3 if eil_c >= 80 else 2 if eil_c >= 65 else 1 if eil_c >= 50 else 0
    conv_score = score + bonus

    return {
        "c_compression": c_compression,
        "c_energy":      c_energy,
        "c_vol":         c_vol,
        "c_gamma":       c_gamma,
        "c_runway":      c_runway,
        "conv_score":    conv_score,
    }

# â”€â”€â”€ STAGE LADDER (execution readiness) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _compute_stage_ladder(sig):
    """
    Repurposes Stage Ladder as Execution Readiness across 4 intelligent layers.
    Stage 1: Signal triggered (trigger_go_eligible)
    Stage 2: Campaign ready (campaign_verdict == READY_EXECUTE/READY_PROBE)
    Stage 3: EIL cleared (eil_v3_verdict contains EXECUTE)
    Stage 4: Execution gate open (execution_verdict == BUY_NOW)
    """
    def _s(key):
        return str(sig.get(key,"") or "").upper().strip()
    def _bool(key):
        v = str(sig.get(key,"") or "").upper().strip()
        return v in ("TRUE","1","YES","Y")

    s1 = _bool("trigger_go_eligible") or _bool("eil__trigger_go_eligible")
    cv = _s("campaign_verdict") or _s("eil__campaign_verdict")
    s2 = cv in ("READY_EXECUTE","READY_PROBE")
    ev_v = _s("eil_v3_verdict") or _s("eil__v3_verdict") or _s("eil__eil_v3_verdict")
    s3 = "EXECUTE" in ev_v and "BLOCKED" not in ev_v
    ex_v = _s("execution_verdict") or _s("eil__execution_verdict")
    s4 = ex_v == "BUY_NOW"

    current = 4 if s4 else 3 if s3 else 2 if s2 else 1 if s1 else 0
    enter_now = "4" if s4 else ""
    alert = "3" if s3 and not s4 else "2" if s2 and not s3 else ""

    summary = (
        "All 4 layers aligned â€” ENTER NOW" if s4 else
        f"EIL cleared Â· waiting on execution gate" if s3 else
        f"Campaign ready Â· EIL checking microstructure" if s2 else
        f"Signal triggered Â· campaign building" if s1 else
        "Signal not yet triggered"
    )

    return {
        "current_stage":   current,
        "enter_now_stages": enter_now,
        "alert_stages":    alert,
        "ladder_summary":  summary,
        "stages_passed":   current,
    }

# â”€â”€â”€ MAIN LOAD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _load_run(run_id, force_reload=False):
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return {"error": f"Run folder not found: {run_id}"}
    current_cache_signature = _lab_cache_signature(run_id)
    cached = _run_cache.get(run_id)
    if not force_reload and cached and cached.get("_cache_signature") == current_cache_signature:
        return cached
    if not force_reload and cached:
        print(f"  â†» Lab cache refresh: Morning handoff changed for run {run_id}")

    result = {"run_id": run_id, "loaded_at": _utc_iso()}
    sb_dir = _find_superbrain_dir(run_dir)

    # â”€â”€ 1. PRIMARY SIGNAL SOURCE: eil_enriched (232 cols, 1312 rows) â”€â”€â”€â”€â”€â”€â”€â”€
    # This replaces superbrain_enriched as the base signal table.
    eil_path = _glob_first(sb_dir, f"eil_enriched_{run_id}.csv")
    if not eil_path:
        eil_path = _glob_first(sb_dir, "eil_enriched_*.csv")
    eil_rows = _read_csv(eil_path)
    result["signals"] = eil_rows
    eil_map = {r.get("ticker","").upper(): r for r in eil_rows}
    print(f"  âœ“ EIL (primary): {len(eil_rows)} signals")

    # â”€â”€ 2. SUPERBRAIN: sb_final_verdict only â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    sb_path = _glob_first(sb_dir, f"superbrain_enriched_{run_id}.csv")
    if not sb_path:
        sb_path = _glob_first(sb_dir, "superbrain_enriched_*.csv")
    sb_rows = _read_csv(sb_path)
    sb_map = {r.get("ticker","").upper(): r for r in sb_rows}
    print(f"  âœ“ SuperBrain (verdict only): {len(sb_rows)} rows")

    # â”€â”€ 3. EXECUTION VERDICTS: campaign_verdict, execution_verdict â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    exe_path = _glob_first(run_dir / "execution", f"execution_v3_5_{run_id}.csv")
    if not exe_path:
        exe_path = _glob_first(run_dir / "execution", "execution_v3_5_*.csv")
    if not exe_path:
        exe_path = _glob_first(sb_dir, f"execution_v3_5_{run_id}.csv")
    if not exe_path:
        exe_path = _glob_first(sb_dir, "execution_v3_5_*.csv")
    exe_rows = _read_csv(exe_path)
    exe_map = {r.get("ticker","").upper(): r for r in exe_rows}
    result["execution_signals"] = exe_rows
    print(f"  âœ“ Execution verdicts: {len(exe_rows)} rows")

    # â”€â”€ 4. OPTIONS INTELLIGENCE (opt__ prefix) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    opt_path = _glob_first(run_dir / "options", f"options_intelligence_{run_id}.csv")
    if not opt_path:
        opt_path = _glob_first(run_dir / "options", "options_intelligence_*.csv")
    opt_rows = _read_csv(opt_path)

    def _norm_opt(r):
        if not r: return {}
        rr = dict(r)
        for alias_key, sources in [
            ("premium_mid",    ["contract_premium","premium"]),
            ("contract_strike",["strike"]),
            ("contract_expiry",["expiry"]),
            ("contract_dte",   ["dte","DTE"]),
        ]:
            if not rr.get(alias_key):
                for s in sources:
                    if rr.get(s): rr.setdefault(alias_key, rr[s]); break
        return rr

    opt_map = {r.get("ticker","").upper(): _norm_opt(r) for r in opt_rows}
    result["options_intelligence"] = opt_rows
    print(f"  âœ“ Options intel: {len(opt_rows)} rows")

    # â”€â”€ 5. VANGUARD (vg__ prefix) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    vg_path = _glob_first(run_dir / "options", f"vanguard_signals_enriched_{run_id}.csv")
    if not vg_path:
        vg_path = _glob_first(run_dir / "vanguard", "vanguard_signals_enriched_*.csv")
    if not vg_path:
        vg_path = _glob_first(run_dir / "vanguard", "vanguard_signals.csv")
    vg_rows = _read_csv(vg_path)
    vg_map = {r.get("ticker","").upper(): r for r in vg_rows}
    result["vanguard_signals"] = vg_rows
    print(f"  âœ“ Vanguard: {len(vg_rows)} rows")

    # â”€â”€ 6. WBS (wbs__ prefix) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    wbs_path = _glob_first(sb_dir, f"wall_break_scores_{run_id}.csv")
    if not wbs_path:
        wbs_path = _glob_first(sb_dir, "wall_break_scores_*.csv")
    wbs_rows = _read_csv(wbs_path)
    wbs_map = {r.get("ticker","").upper(): r for r in wbs_rows}
    result["wall_break_scores"] = wbs_rows
    print(f"  âœ“ WBS: {len(wbs_rows)} rows")

    wbs_sum_path = _glob_first(sb_dir, "wall_break_summary_*.json")
    result["wall_break_summary"] = _read_json(wbs_sum_path)

    # â”€â”€ 7. GARCH (garch__ prefix) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    garch_path = _glob_first(run_dir / "qomega", f"garch_forecasts_{run_id}.csv")
    if not garch_path:
        garch_path = _glob_first(run_dir / "qomega", "garch_forecasts_*.csv")
    if not garch_path:
        garch_path = _glob_first(sb_dir, "garch_forecasts_*.csv")
    garch_rows = _read_csv(garch_path)
    garch_map = {r.get("ticker","").upper(): r for r in garch_rows}
    result["garch_forecasts"] = garch_rows
    print(f"  âœ“ GARCH: {len(garch_rows)} rows")

    if garch_rows:
        tailwinds = [float(r.get("l3_iv_tailwind_score",0) or 0) for r in garch_rows]
        result["garch_stats"] = {
            "count":         len(garch_rows),
            "cheap_vol":     sum(1 for t in tailwinds if t < -0.03),
            "fair_vol":      sum(1 for t in tailwinds if -0.03 <= t <= 0.05),
            "expensive_vol": sum(1 for t in tailwinds if t > 0.05),
            "jump_risk":     sum(1 for r in garch_rows if str(r.get("l3_jump_risk_flag","")).lower()=="true"),
            "garch_count":   sum(1 for r in garch_rows if r.get("l3_method","")=="GARCH"),
            "ewma_count":    sum(1 for r in garch_rows if r.get("l3_method","")=="EWMA_FALLBACK"),
        }
    else:
        result["garch_stats"] = {}

    # â”€â”€ 8. MACRO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ci_path = _glob_first(run_dir / "core_intel", f"core_intel_dossiers_{run_id}.json")
    if not ci_path:
        ci_path = _glob_first(run_dir / "core_intel", "core_intel_dossiers_*.json")
    core_intel = _read_json(ci_path)
    raw_macro = core_intel.get("macro", {}) if isinstance(core_intel, dict) else {}
    dossier_list = core_intel.get("dossiers", []) if isinstance(core_intel, dict) else []
    dossier_map = {d.get("ticker","").upper(): d for d in dossier_list}
    result["macro"] = _normalise_macro(raw_macro)

    # â”€â”€ 9. MORNING VALIDATION (mv__ prefix) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    handoff_paths = _morning_handoff_paths(run_dir, sb_dir, run_id)
    mv_path = handoff_paths["morning_validation"]
    mv_rows = _read_csv(mv_path) if mv_path else []
    mv_map = {r.get("ticker","").upper(): r for r in mv_rows}
    result["mv_signals"] = mv_rows
    print(f"  âœ“ Morning validation: {len(mv_rows)} rows")

    eod_path = handoff_paths["eod_candidates"]
    eod_candidate_rows = _read_csv(eod_path) if eod_path else []
    eod_candidate_map = {r.get("ticker","").upper(): r for r in eod_candidate_rows}
    result["eod_candidates"] = eod_candidate_rows
    print(f"  âœ“ EOD candidates: {len(eod_candidate_rows)} rows")

    # Lab lifecycle:
    #   1) After EOD run: show morning_candidates as the prep queue.
    #   2) After morning validator: show morning_validated_trades.
    #   3) If neither exists: fall back to full EIL universe for diagnostics.
    if mv_map:
        handoff_mode = "MORNING_VALIDATION"
        handoff_source = "morning_validated_trades"
        handoff_maps = [mv_map]
    elif eod_candidate_map:
        handoff_mode = "EOD_PREP"
        handoff_source = "morning_candidates"
        handoff_maps = [eod_candidate_map]
    else:
        handoff_mode = "EIL_FULL"
        handoff_source = "eil_enriched"
        handoff_maps = []

    pre_filter_count = len(result["signals"])
    result["signals"], missing_handoff_tickers = _filter_to_handoff_signals(result["signals"], handoff_maps)
    result["lab_handoff_mode"] = handoff_mode
    result["lab_handoff_source"] = handoff_source
    result["lab_handoff_count"] = len(result["signals"])
    result["lab_handoff_missing_from_eil"] = missing_handoff_tickers
    if handoff_mode == "EOD_PREP":
        result["lab_data_notice"] = (
            "EOD prep mode: showing morning_candidates only. "
            "Morning validation is still required before trade execution."
        )
    elif handoff_mode == "MORNING_VALIDATION":
        result["lab_data_notice"] = "Morning validation mode: showing validated morning handoff rows."
    else:
        result["lab_data_notice"] = "Full EIL review mode: no final handoff slate found."
    print(f"  Lab handoff: {handoff_mode} via {handoff_source} | {len(result['signals'])}/{pre_filter_count} rows")


    # â”€â”€ 10. DISCOVERY â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    disc_path = _glob_first(run_dir / "discovery", "discovery_candidates_*.csv")
    result["discovery"] = _read_csv(disc_path)

    # â”€â”€ 11. V5 SIGNALS (v5__ prefix) â€” 32 candidate execution layer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Load from superbrain dir or runs dir. Placed there manually or by pipeline.
    v5_path = _glob_latest(sb_dir, "AVSHUNTER_SIGNALS_V5_*.csv")
    if not v5_path:
        v5_path = _glob_latest(run_dir, "AVSHUNTER_SIGNALS_V5_*.csv")
    if not v5_path:
        v5_path = _glob_latest(RUNS_DIR.parent, "AVSHUNTER_SIGNALS_V5_*.csv")
    v5_rows = _read_csv(v5_path) if v5_path else []
    v5_map = {r.get("ticker","").upper(): r for r in v5_rows}
    result["v5_signals"] = v5_rows
    print(f"  âœ“ V5 signals: {len(v5_rows)} rows ({v5_path.name if v5_path else 'not found'})")

    # â”€â”€ SUMMARY JSON â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    sum_path = _glob_first(sb_dir, "superbrain_summary_*.json")
    result["summary"] = _read_json(sum_path)

    # â”€â”€ RUN HEALTH â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    required = [("eil_enriched", eil_path)]
    optional = [
        ("superbrain_enriched", sb_path),
        ("execution_v3_5",      exe_path),
        ("options_intelligence", opt_path),
        ("vanguard_signals",    vg_path),
        ("wall_break_scores",   wbs_path),
        ("garch_forecasts",     garch_path),
        ("morning_validation",  mv_path if mv_rows else None),
        ("eod_candidates",      eod_path if eod_candidate_rows else None),
        ("v5_signals",          v5_path),
    ]
    missing_req = [n for n,p in required if not p or not Path(p).exists()]
    missing_opt = [n for n,p in optional if not p or not Path(p).exists()]
    result["run_health"] = {
        "ok": len(missing_req) == 0,
        "missing_required": missing_req,
        "missing_optional": missing_opt,
    }

    # â”€â”€ MERGE: annotate each signal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _first_nonempty(*values):
        for val in values:
            if val is None:
                continue
            text = str(val).strip()
            if text and text.lower() not in ("nan", "none", "null"):
                return val
        return ""

    def _side_from_value(raw):
        text = str(raw or "").upper().strip()
        strategy = str(_first_nonempty(
            raw,
        ) or "").upper()

        if "PUT" in text or "SHORT" in text or text in ("BEARISH", "SELL", "DOWN"):
            return "PUT"
        if "CALL" in text or text in ("BULLISH", "BUY", "UP"):
            return "CALL"
        if "PUT" in strategy or "BEAR" in strategy:
            return "PUT"
        if "CALL" in strategy or "BULL" in strategy:
            return "CALL"
        return "" if text in ("", "NONE", "NEUTRAL", "STRANGLE", "UNKNOWN") else text

    def _intent_side(sig):
        intent = _first_nonempty(
            sig.get("intent"),
            sig.get("precor_intent"),
            sig.get("vg__precor_intent"),
            sig.get("eod__intent"),
        )
        text = str(intent or "").upper()
        if "SELL" in text or "PUT" in text or "BEAR" in text:
            return "PUT"
        if "BUY" in text or "CALL" in text or "BULL" in text:
            return "CALL"
        return ""

    def _factor_side(sig):
        text = " ".join(str(sig.get(k, "") or "") for k in ("positive_factors", "negative_factors", "opt__positive_factors", "opt__negative_factors")).upper()
        put_score = sum(token in text for token in ("PUT CONFIRMED", "AGAINST PUT", "SELL_SETUP"))
        call_score = sum(token in text for token in ("CALL CONFIRMED", "AGAINST CALL", "BUY_SETUP"))
        if put_score > call_score:
            return "PUT"
        if call_score > put_score:
            return "CALL"
        return ""

    def _normalise_direction_value(sig):
        # Direction is thesis authority. Prefer canonical/resolved footprint
        # direction before legacy primary/options/contract expression fields.
        candidates = [
            sig.get("canonical_direction"),
            sig.get("resolved_direction"),
            sig.get("footprint_direction"),
            sig.get("eod__canonical_direction"),
            sig.get("eod__resolved_direction"),
            sig.get("eod__footprint_direction"),
            sig.get("direction"),
            sig.get("primary_direction"),
            sig.get("eod__primary_direction"),
            sig.get("options_direction"),
            sig.get("opt__options_direction"),
            _intent_side(sig),
            _factor_side(sig),
            sig.get("layer2__edge_direction"),
            sig.get("options_strategy"),
            sig.get("opt__options_strategy"),
            sig.get("instrument"),
            sig.get("dominant_trend"),
            sig.get("catalyst_direction_bias"),
            sig.get("selected_contract_side"),
            sig.get("contract_side"),
        ]
        for value in candidates:
            side = _side_from_value(value)
            if side in ("CALL", "PUT"):
                return side
        return ""

    def _direction_coherence(sig, canonical):
        flags = []
        for label, value in (
            ("direction", sig.get("direction")),
            ("intent", _intent_side(sig)),
            ("selected_contract_side", sig.get("selected_contract_side") or sig.get("contract_side")),
            ("catalyst_direction_bias", sig.get("catalyst_direction_bias")),
        ):
            side = _side_from_value(value)
            if side in ("CALL", "PUT") and canonical in ("CALL", "PUT") and side != canonical:
                flags.append(f"{label}:{side}->{canonical}")
        if not flags:
            return "CLEAN", []
        if any(flag.startswith("selected_contract_side:") for flag in flags):
            return "CONTRACT_SIDE_CONFLICT", flags
        return "CONFLICT_REPAIRED", flags

    def _instrument_for_direction(direction, current=""):
        side = _side_from_value(direction)
        current_text = str(current or "").upper().replace("-", "_").replace(" ", "_")
        if side not in ("CALL", "PUT"):
            return str(current or "")
        opposite = "PUT" if side == "CALL" else "CALL"
        if "DEBIT_SPREAD" in current_text:
            return current_text.replace(opposite, side)
        if "CREDIT_SPREAD" in current_text:
            return current_text.replace(opposite, side)
        if "VERTICAL" in current_text:
            return current_text.replace(opposite, side)
        return f"LONG_{side}"

    def _display_execution_mode_for(verdict, sig):
        entry_action = str(_first_nonempty(sig.get("morning_entry_action"), sig.get("mv__morning_entry_action")) or "").upper()
        if entry_action and entry_action not in _EMPTY_SIGNAL_VALUES:
            return entry_action
        return {
            "GO": "BUY_NOW",
            "EOD_EXEC": "EOD_READY",
            "GO_LIMIT": "LIMIT_ENTRY",
            "PROBE": "PROBE_ENTRY",
            "EOD_CAUTION": "MANUAL_REVIEW",
            "ARMED": "WAIT_TRIGGER",
            "CONTRACT_REPAIR": "REPAIR_CONTRACT",
            "WAIT": "WAIT",
            "WATCHLIST": "WATCH_ONLY",
            "BLOCKED": "NO_TRADE",
        }.get(verdict, verdict or "WAIT")

    def _display_campaign_for(verdict, sig):
        return {
            "GO": "READY_EXECUTE",
            "EOD_EXEC": "READY_EXECUTE",
            "GO_LIMIT": "READY_LIMIT",
            "PROBE": "READY_PROBE",
            "EOD_CAUTION": "EXECUTE_WITH_CAUTION",
            "ARMED": "ARMED",
            "CONTRACT_REPAIR": "CONTRACT_REPAIR",
            "WAIT": "WATCHLIST",
            "WATCHLIST": "WATCHLIST",
            "BLOCKED": "BLOCKED",
        }.get(verdict, str(_first_nonempty(sig.get("sb_campaign"), sig.get("campaign_verdict")) or "WATCHLIST").upper())

    def _sync_lab_display_fields(sig):
        canonical = _normalise_direction_value(sig)
        if canonical:
            status, flags = _direction_coherence(sig, canonical)
            sig["canonical_direction"] = canonical
            sig["direction"] = canonical
            sig.setdefault("primary_direction", canonical)
            sig.setdefault("options_direction", canonical)
            # Do not fabricate selected_contract_side; it is contract expression, not thesis authority.
            expected_instrument = _instrument_for_direction(
                canonical,
                _first_nonempty(sig.get("sb_instrument_now"), sig.get("instrument"), sig.get("options_strategy")),
            )
            existing_instrument = str(_first_nonempty(sig.get("sb_instrument_now"), sig.get("instrument"), sig.get("options_strategy")) or "")
            if expected_instrument:
                if existing_instrument and _side_from_value(existing_instrument) not in ("", canonical):
                    flags.append(f"instrument:{_side_from_value(existing_instrument)}->{canonical}")
                    sig.setdefault("instrument_original", existing_instrument)
                    sig.setdefault("options_strategy_original", sig.get("options_strategy", ""))
                    sig.setdefault("sb_instrument_now_original", sig.get("sb_instrument_now", ""))
                sig["instrument"] = expected_instrument
                sig["options_strategy"] = expected_instrument
                sig["sb_instrument_now"] = expected_instrument
            sig["lab_coherence_status"] = status if not any(f.startswith("instrument:") for f in flags) else "INSTRUMENT_DISPLAY_REPAIRED"
            sig["lab_coherence_flags"] = "|".join(flags)
            if flags:
                existing = str(sig.get("direction_conflict_reason", "") or "")
                sig["direction_conflict_reason"] = " | ".join(x for x in (existing, "DISPLAY_SYNC:" + ",".join(flags)) if x)
                sig.setdefault("direction_conflict_status", status)

        verdict = str(sig.get("lab_verdict") or sig.get("lab_status") or "WAIT").upper().strip()
        if not verdict or verdict in _EMPTY_SIGNAL_VALUES:
            verdict = "WAIT"
        sig.setdefault("legacy_sb_final_verdict", sig.get("sb_final_verdict", ""))
        sig.setdefault("legacy_sb_campaign", sig.get("sb_campaign", ""))
        sig.setdefault("legacy_sb_execution_mode", sig.get("sb_execution_mode", ""))
        sig["display_final_verdict"] = verdict
        sig["sb_final_verdict"] = verdict
        sig["display_campaign"] = _display_campaign_for(verdict, sig)
        sig["sb_campaign"] = sig["display_campaign"]
        sig["display_execution_mode"] = _display_execution_mode_for(verdict, sig)
        sig["sb_execution_mode"] = sig["display_execution_mode"]
        options_route = str(_first_nonempty(
            sig.get("options_research_route"),
            sig.get("final_route"),
            sig.get("eod__options_research_route"),
            sig.get("eod__final_route"),
            sig.get("opt__final_route"),
        ) or "").upper().replace(" ", "_")
        if sig.get("has_eod_candidate_manifest_row"):
            eod_status = str(_first_nonempty(
                sig.get("eod_candidate_status"),
                sig.get("candidate_status"),
                sig.get("eod__eod_candidate_status"),
                sig.get("eod__candidate_status"),
                sig.get("effective_execution_verdict"),
            ) or "").upper().replace(" ", "_")
        else:
            eod_status = ""
        morning_permission = str(_first_nonempty(
            sig.get("morning_execution_permission"),
            sig.get("mv__morning_execution_permission"),
            sig.get("mv_morning_execution_permission"),
            sig.get("mv_execution_permission"),
            sig.get("mv__execution_permission"),
        ) or "").upper().replace(" ", "_")
        morning_route = str(_first_nonempty(
            sig.get("morning_execution_route"),
            sig.get("mv__morning_execution_route"),
            sig.get("mv_morning_execution_route"),
            sig.get("morning_execution_lane"),
            sig.get("mv__morning_execution_lane"),
        ) or "").upper().replace(" ", "_")
        sig["display_options_research_route"] = options_route
        sig["display_eod_candidate_status"] = eod_status
        sig["display_morning_execution_permission"] = morning_permission
        sig["display_morning_execution_route"] = morning_route
        alignment_status = str(sig.get("morning_lab_alignment_status") or "").upper().replace(" ", "_")
        if not alignment_status and morning_permission:
            alignment_status = "ALIGNMENT_NOT_AUDITED"
            sig["morning_lab_alignment_reason"] = "Morning baton present but Lab resolver did not attach an alignment audit."
        elif not alignment_status:
            alignment_status = "NO_MORNING_BATON"
        sig["morning_lab_alignment_status"] = alignment_status
        sig["display_morning_lab_alignment_status"] = alignment_status
        if morning_permission:
            sig["morning_execution_permission"] = morning_permission
        if morning_route:
            sig["morning_execution_route"] = morning_route
        sig["execution_category"] = str(_first_nonempty(morning_permission, eod_status, verdict) or verdict).upper()
        sig["display_execution_category"] = sig["execution_category"]

        tradeable = sig.get("lab_tradeable") is True or str(sig.get("lab_tradeable")).lower() == "true"
        if tradeable:
            if verdict == "GO_LIMIT":
                size_display = "LIMIT / MANUAL"
            elif verdict == "PROBE":
                size_display = "PROBE / MANUAL"
            else:
                size_display = "MANUAL"
        elif verdict == "CONTRACT_REPAIR":
            size_display = "0% - repair contract"
            sig["sb_position_size_pct"] = 0
        elif verdict in ("ARMED", "WAIT", "WATCHLIST", "EOD_CAUTION"):
            size_display = "0% - waiting"
            sig["sb_position_size_pct"] = 0
        elif verdict == "BLOCKED":
            size_display = "0% - blocked"
            sig["sb_position_size_pct"] = 0
        else:
            size_display = "0% - review"
            sig["sb_position_size_pct"] = 0
        sig["position_size_display"] = size_display
        sig["sb_position_size_display"] = size_display

    for sig in result["signals"]:
        t = sig.get("ticker","").upper()

        # sb_final_verdict (the only thing superbrain still owns)
        sb = sb_map.get(t, {})
        sig.setdefault("sb_final_verdict", sb.get("sb_final_verdict",""))

        # Execution verdicts from execution_v3_5
        exe = exe_map.get(t, {})
        for k, v in exe.items():
            if k == "ticker":
                continue
            sig.setdefault(f"exe__{k}", v)
            if not sig.get(k) and v not in (None, "", "nan"):
                sig[k] = v
        sig.setdefault("campaign_verdict",  exe.get("campaign_verdict",""))
        sig.setdefault("execution_verdict", exe.get("execution_verdict",""))

        # â”€â”€ FIELD ALIASES: map new pipeline fields to lab's old names â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # The UI reads these bare names â€” set them from eil fields
        sig.setdefault("rr",                sig.get("rr_options",""))
        sig.setdefault("ev",                sig.get("ev2_ev_conf_adj","") or sig.get("eil_ev_net",""))
        sig.setdefault("ev_final",          sig.get("ev2_ev_conf_adj",""))
        sig.setdefault("ev_net",            sig.get("ev2_ev_conf_adj",""))
        sig.setdefault("ev_status",         sig.get("ev2_ev_status",""))
        sig.setdefault("ev2_decision_hint", sig.get("ev2_ev_status",""))
        sig.setdefault("phase",             sig.get("wyckoff_phase_bucket",""))
        sig.setdefault("intent",            sig.get("precor_intent",""))
        sig.setdefault("regime",            sig.get("macro_regime",""))
        sig.setdefault("current_price",     sig.get("underlying_price",""))
        sig.setdefault("signal_price",      sig.get("underlying_price",""))
        sig.setdefault("composite",         sig.get("eil_composite_score",""))
        sig.setdefault("win_rate_source",   "ACTUARIAL" if float(sig.get("ev2_p_win_blended",0) or 0) > 0 else "STRUCTURAL")

        # map verdict aliases so filter buttons work
        sig.setdefault("sb_campaign",      sig.get("campaign_verdict",""))
        sig.setdefault("sb_execution_mode",sig.get("execution_verdict",""))
        sig.setdefault("sb_conv_score",    sig.get("options_score",""))
        sig.setdefault("sb_risk_label",    sig.get("direction_confidence","MEDIUM"))
        sig.setdefault("sb_instrument_now",sig.get("options_strategy",""))
        _sync_lab_display_fields(sig)
        sig.setdefault("sb_verdict_reason",sig.get("reason",""))

        # Sizing from v5 if available, else derive from eil_composite
        v5 = v5_map.get(t, {})
        if v5.get("size_mult"):
            sig.setdefault("sb_position_size_pct", float(v5.get("size_mult",0) or 0) * 100)
        else:
            eil_c = float(sig.get("eil_composite_score",50) or 50)
            sig.setdefault("sb_position_size_pct",
                           100 if eil_c >= 85 else 75 if eil_c >= 70 else 55 if eil_c >= 55 else 35)

        # Contract validity â†’ veto display
        cv_flags = sig.get("contract_validity","")
        bad_flags = [f for f in cv_flags.split("|") if f and f != "CONTRACT_OK"]
        sig.setdefault("sb_vetoes",       "|".join(bad_flags) if bad_flags else "")
        sig.setdefault("sb_vetoes_count", len(bad_flags))

        # v5 fields
        if v5:
            sig.setdefault("thesis_decision",            v5.get("thesis_decision",""))
            sig.setdefault("v5_execution_mode",          v5.get("execution_mode",""))
            sig.setdefault("v5_layer_score",             v5.get("layer_score_val",""))
            sig.setdefault("v5_size_mult",               v5.get("size_mult",""))
            sig.setdefault("direction_conflict",         v5.get("direction_conflict","FALSE"))
            sig.setdefault("strategy_direction_conflict",v5.get("strategy_direction_conflict","FALSE"))
            sig.setdefault("occ_direction",              v5.get("occ_direction",""))
            sig.setdefault("final_option_spread_pct",    v5.get("final_option_spread_pct",""))

        # Options (opt__ prefix)
        opt = opt_map.get(t, {})
        for k, v in opt.items():
            if k != "ticker":
                sig.setdefault(f"opt__{k}", v)

        # Vanguard (vg__ prefix)
        vg = vg_map.get(t, {})
        for k, v in vg.items():
            if k != "ticker":
                sig.setdefault(f"vg__{k}", v)
        for k in PHYSICS_FIELDS:
            sig.setdefault(k, sig.get(k) or vg.get(k, ""))
        sig.setdefault("win_rate_20d", vg.get("layer2__win_rate_20d",""))
        sig.setdefault("tier",         vg.get("tier_label",""))

        # WBS (wbs__ prefix)
        wbs = wbs_map.get(t, {})
        for k, v in wbs.items():
            if k != "ticker":
                sig.setdefault(f"wbs__{k}", v)
        if "wbs__wbs" in sig and "wbs__wbs_score" not in sig:
            sig["wbs__wbs_score"] = sig["wbs__wbs"]
        if "wbs__wbs_wall_price" in sig and "wbs__wall_price" not in sig:
            sig["wbs__wall_price"] = sig["wbs__wbs_wall_price"]

        # Dossier (doss__ prefix)
        doss = dossier_map.get(t, {})
        for k, v in doss.items():
            if k != "ticker":
                sig.setdefault(f"doss__{k}", v)

        # GARCH (garch__ prefix)
        garch = garch_map.get(t, {})
        for k, v in garch.items():
            if k != "ticker":
                sig.setdefault(f"garch__{k}", v)

        # Morning validation (mv__ prefix)
        mv = mv_map.get(t, {})
        for k, v in mv.items():
            if k == "ticker": continue
            clean_key = k[3:] if k.startswith("mv_") else k
            sig.setdefault(f"mv__{clean_key}", v)
        # FIX-IVP: overwrite IV fields from live morning data
        _live_iv = mv.get("live_iv") or mv.get("mv_live_iv")
        if _live_iv and str(_live_iv) not in ("","None","nan","0","0.0"):
            try:
                _iv_f = float(_live_iv)
                _iv_pct = _iv_f * 100 if _iv_f < 1 else _iv_f
                sig["opt__iv_rank"]   = round(_iv_pct, 1)
                sig["opt__ivp_label"] = "CHEAP" if _iv_pct < 20 else "FAIR" if _iv_pct < 50 else "RICH"
                sig["iv_rank"]        = round(_iv_pct, 1)
                sig["ivp_label"]      = sig["opt__ivp_label"]
            except: pass
        # TCE field aliases
        for bare_key, (pfx_key, raw_key) in {
            "tce_trigger_state":  ("mv__tce_trigger_state",  "mv_tce_trigger_state"),
            "tce_trigger_score":  ("mv__tce_trigger_score",  "mv_tce_trigger_score"),
            "tce_entry_type":     ("mv__tce_entry_type",     "mv_tce_entry_type"),
            "tce_trigger_reason": ("mv__tce_trigger_reason", "mv_tce_trigger_reason"),
            "mv_verdict":         ("mv__verdict",            "mv_verdict"),
            "mv_execution_permission": ("mv__execution_permission", "execution_permission"),
            "morning_execution_permission": ("mv__morning_execution_permission", "morning_execution_permission"),
            "morning_execution_route": ("mv__morning_execution_route", "morning_execution_route"),
            "mv_morning_execution_permission": ("mv__morning_execution_permission", "morning_execution_permission"),
            "mv_morning_execution_route": ("mv__morning_execution_route", "morning_execution_route"),
            "mv_live_validation_state": ("mv__live_validation_state", "live_validation_state"),
            "mv_validation_score": ("mv__validation_score", "validation_score"),
            "mv_validation_confidence": ("mv__validation_confidence", "validation_confidence"),
            "live_price":         ("mv__live_price",         "mv_live_price"),
        }.items():
            if not sig.get(bare_key):
                val = sig.get(pfx_key) or mv.get(raw_key) or mv.get(bare_key)
                if val not in (None,"","nan"):
                    sig[bare_key] = val

        # EOD candidate slate (eod__ prefix). These rows are the final EOD
        # candidate manifest, so selected fields should override advisory
        # defaults when present.
        eod = eod_candidate_map.get(t, {})
        sig["has_eod_candidate_manifest_row"] = bool(eod)
        if handoff_mode == "EOD_PREP" and eod:
            sig["lab_eod_prep_mode"] = True
            sig.setdefault("live_validation_state", "PENDING_MARKET_OPEN")
            sig.setdefault("morning_execution_route", "EOD_PREP_PENDING_VALIDATION")
        for k, v in eod.items():
            if k == "ticker":
                continue
            sig.setdefault(f"eod__{k}", v)
        for bare_key in (
            "candidate_status", "eod_candidate_status", "eod_candidate_reason",
            "eod_live_capital_permission", "live_capital_permission",
            "eod_candidate_permission", "candidate_size", "sizing_policy",
            "effective_execution_verdict", "execution_authority_reason",
            "signal_authority_reason", "primary_direction", "direction",
            "direction_reroute_status", "direction_decision_reason",
            "shadow_opportunity_score", "shadow_opportunity_label",
            "shadow_opportunity_reason",
            "options_research_permission", "options_research_route",
            "options_research_score", "final_route", "hard_vetoes",
            "options_hard_vetoes",
            "trigger_primary", "trigger_quality", "trigger_score", "trigger_codes",
            "trigger_go_eligible", "days_to_trigger", "trigger_days",
            "horizon_bucket", "layer2__preferred_horizon", "macro_preferred_horizon",
            "horizon_action", "horizon_pressure", "horizon_source",
            "hold_label", "hold_urgency",
        ):
            val = eod.get(bare_key)
            _set_signal_value(sig, bare_key, val, overwrite_empty=True)
        sig["lab_execution_status"] = _extract_execution_category(sig)

        # EV display fix
        _ev = _first_numeric_signal_value(sig, [
            "ev2_ev_conf_adj", "fd_ev_used", "eil_ev_net",
            "eod__ev2_ev_conf_adj", "eod__fd_ev_used", "eod__eil_ev_net",
            "ev_final", "ev_net", "ev",
        ], default=None)
        if _ev is not None:
            sig["ev"] = round(float(_ev), 6)
            sig["ev_final"] = sig["ev"]
            sig["ev_net"]   = sig["ev"]

        # Price fix
        _sp = sig.get("underlying_price") or sig.get("signal_price")
        if _sp and str(_sp) not in ("0","0.0","","nan","None"):
            try:
                _sp_f = float(_sp)
                if _sp_f > 0:
                    sig["current_price"]    = _sp_f
                    sig["spot_price"]       = _sp_f
                    sig["underlying_price"] = _sp_f
            except: pass

        # Premium synthetic flag
        _synth = str(sig.get("contract_mark_synthetic","")).lower()
        if _synth in ("true","1","yes"):
            sig["premium_label"] = "BSM"
            sig["premium_is_synthetic"] = True
        else:
            sig.setdefault("premium_label", "$")
            sig.setdefault("premium_is_synthetic", False)

        # UI contract: Intelligence Lab reads a simple CALL/PUT direction.
        # The pipeline can hand it over as options_direction, primary_direction,
        # strategy text, or catalyst bias, so normalise it after all merges.
        display_direction = _normalise_direction_value(sig)
        if display_direction:
            sig["direction"] = display_direction
            sig.setdefault("primary_direction", display_direction)
            sig.setdefault("options_direction", display_direction)
        _sync_lab_display_fields(sig)

        # CONVEXITY CHECKS (pipeline-native)
        conv = _compute_conv_checks(sig)
        sig["sb_c_compression"]     = conv["c_compression"]
        sig["sb_c_energy"]          = conv["c_energy"]
        sig["sb_c_underpriced_vol"] = conv["c_vol"]
        sig["sb_c_gamma_proximity"] = conv["c_gamma"]
        sig["sb_c_runway"]          = conv["c_runway"]
        sig["sb_conv_score"]        = conv["conv_score"]

        # STAGE LADDER (execution readiness)
        ladder = _compute_stage_ladder(sig)
        sig["sb_current_stage"]    = ladder["current_stage"]
        sig["sb_enter_now_stages"] = ladder["enter_now_stages"]
        sig["sb_alert_stages"]     = ladder["alert_stages"]
        sig["sb_ladder_summary"]   = ladder["ladder_summary"]
        sig["sb_stages_passed"]    = ladder["stages_passed"]
        sig["sb_time_stop_date"]   = sig.get("opt__contract_expiry","")
        sig["sb_checkpoint_rule"]  = sig.get("wbs__wbs_wall_stall_rule","")

    # â”€â”€ RESEARCH PRIORITY SCORE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Final action ranking is recomputed after morning validation/Lab control.
    for sig in result["signals"]:
        score = _compute_priority_score(sig)
        sig["research_priority_score"] = score
        sig["priority_score"] = score
    sorted_sigs = sorted(result["signals"],
                         key=lambda x: float(x.get("research_priority_score",0)), reverse=True)
    for rank, sig in enumerate(sorted_sigs, 1):
        sig["research_priority_rank"] = rank

    # Final Lab control layer: resolve tradeability after all enrichment is merged.
    # This is validation/normalisation only; it does not create signals.
    run_manifest = write_final_run_manifest(run_id, RUNS_DIR, _infer_pipeline_mode(eil_rows, mv_rows))
    open_trades = _safe_open_journal_positions()
    for sig in result["signals"]:
        apply_lab_resolution(sig, run_manifest, open_trades)
        if handoff_mode == "EOD_PREP" and sig.get("has_eod_candidate_manifest_row") and sig.get("lab_verdict") != "BLOCKED":
            sig["lab_verdict"] = "MORNING_VALIDATION_REQUIRED"
            sig["lab_status"] = "MORNING_VALIDATION_REQUIRED"
            sig["lab_tradeable"] = False
            sig["prep_permission"] = sig.get("prep_permission") or "MANUAL_REVIEW_MORNING_VALIDATION"
            sig["requires_live_validation"] = True
            sig["execution_lock_reason"] = sig.get("execution_lock_reason") or "EOD_PREP_PENDING_MORNING_VALIDATION"
        _sync_lab_display_fields(sig)
        if not sig.get("trade_idea_id"):
            strike = sig.get("strike") or sig.get("contract_strike") or sig.get("opt__contract_strike") or "NA"
            expiry = sig.get("expiry") or sig.get("contract_expiry") or sig.get("opt__contract_expiry") or "NA"
            direction = sig.get("canonical_direction") or sig.get("resolved_direction") or sig.get("footprint_direction") or sig.get("direction") or sig.get("primary_direction") or sig.get("options_direction") or "UNKNOWN"
            sig["trade_idea_id"] = f"{run_id}:{sig.get('ticker','UNKNOWN')}:{direction}:{strike}:{expiry}"
    _finalise_lab_priority_ranking(result["signals"])
    result["final_run_manifest"] = run_manifest
    result["run_health"] = {
        "ok": run_manifest.get("run_tradeable", False),
        "score": run_manifest.get("run_health_score", 0),
        "next_action": run_manifest.get("next_action", "UNKNOWN"),
        "fatal_flags": run_manifest.get("fatal_flags", []),
        "stale_flags": run_manifest.get("stale_flags", []),
        "conflict_flags": run_manifest.get("conflict_flags", []),
    }
    _opportunity_book_path = RUNS_DIR / run_id / "intelligence_lab" / f"final_opportunity_book_{run_id}.json"
    if not _opportunity_book_path.exists():
        write_final_opportunity_book(run_id, result["signals"], run_manifest, RUNS_DIR)
    _verdict_counts = {}
    for _sig in result["signals"]:
        _v = str(_sig.get("lab_verdict") or _sig.get("sb_final_verdict") or "UNKNOWN").upper()
        _verdict_counts[_v] = _verdict_counts.get(_v, 0) + 1
    result["opportunity_book"] = {
        "run_id": run_id,
        "available": _opportunity_book_path.exists(),
        "path": str(_opportunity_book_path),
        "candidate_count": len(result["signals"]),
        "verdict_counts": _verdict_counts,
    }

    # â”€â”€ STATS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    signals  = result["signals"]
    execute  = [s for s in signals if s.get("options_verdict","").upper()=="EXECUTE"
                or str(s.get("lab_verdict","")).upper() in ("GO", "GO_LIMIT", "PROBE", "EOD_EXEC")
                or str(s.get("sb_final_verdict","")).upper()=="EXECUTE"]
    armed    = [s for s in signals if s.get("options_verdict","").upper()=="ARMED"
                or s.get("sb_final_verdict","").upper()=="ARMED"]
    stand    = [s for s in signals if s.get("sb_final_verdict","").upper()=="STAND_DOWN"]

    # V5 decision counts
    v5_go    = [s for s in signals if s.get("thesis_decision","")=="GO"]
    v5_probe = [s for s in signals if s.get("thesis_decision","")=="PROBE"]

    wbs_grades = {}
    for r in wbs_rows:
        g = r.get("wbs_grade","")
        if g: wbs_grades[g] = wbs_grades.get(g,0)+1

    eil_verdicts = {}
    for r in eil_rows:
        v = r.get("eil_raw_verdict") or r.get("eil_v3_verdict","")
        if v: eil_verdicts[v] = eil_verdicts.get(v,0)+1

    mv_lane_counts = {}
    mv_permission_counts = {}
    mv_state_counts = {}
    for r in mv_rows:
        lane = str(r.get("morning_execution_route") or r.get("morning_execution_lane") or r.get("execution_permission") or "UNKNOWN").upper()
        perm = str(r.get("morning_execution_permission") or r.get("execution_permission") or r.get("morning_execution_lane") or "UNKNOWN").upper()
        state = str(r.get("live_validation_state") or r.get("mv_verdict") or "UNKNOWN").upper()
        mv_lane_counts[lane] = mv_lane_counts.get(lane, 0) + 1
        mv_permission_counts[perm] = mv_permission_counts.get(perm, 0) + 1
        mv_state_counts[state] = mv_state_counts.get(state, 0) + 1
    mv_lab_alignment_counts = {}
    for s in signals:
        status = str(s.get("morning_lab_alignment_status") or "NO_MORNING_BATON").upper()
        mv_lab_alignment_counts[status] = mv_lab_alignment_counts.get(status, 0) + 1

    summary_j = result.get("summary",{})
    result["stats"] = {
        # Core verdicts (from new pipeline fields)
        "execute_count":       len(execute),
        "armed_count":         len(armed),
        "stand_down_count":    len(stand),
        "total_scanned":       len(signals),
        "lab_go_count":        sum(1 for s in signals if s.get("lab_verdict") == "GO"),
        "lab_go_limit_count":  sum(1 for s in signals if s.get("lab_verdict") == "GO_LIMIT"),
        "lab_probe_count":     sum(1 for s in signals if s.get("lab_verdict") == "PROBE"),
        "lab_eod_exec_count":  sum(1 for s in signals if s.get("lab_verdict") == "EOD_EXEC"),
        "lab_eod_caution_count": sum(1 for s in signals if s.get("lab_verdict") == "EOD_CAUTION"),
        "lab_armed_count":     sum(1 for s in signals if s.get("lab_verdict") == "ARMED"),
        "lab_contract_repair_count": sum(1 for s in signals if s.get("lab_verdict") == "CONTRACT_REPAIR"),
        "lab_wait_count":      sum(1 for s in signals if s.get("lab_verdict") == "WAIT"),
        "lab_blocked_count":   sum(1 for s in signals if s.get("lab_verdict") == "BLOCKED"),
        "lab_tradeable_count": sum(1 for s in signals if bool(s.get("lab_tradeable"))),
        "execute_risk_count":  sum(1 for s in signals if "CAUTION" in s.get("eil_v3_verdict","").upper()),
        # V5 execution layer
        "v5_go_count":         len(v5_go),
        "v5_probe_count":      len(v5_probe),
        "v5_total":            len(v5_rows),
        # Campaigns
        "core_campaign_count": sum(1 for s in signals if "READY_EXECUTE" in s.get("campaign_verdict","")),
        "staged_campaign_count":sum(1 for s in signals if "READY_PROBE" in s.get("campaign_verdict","")),
        "core_armed_count":    sum(1 for s in signals if s.get("options_verdict","")=="EXECUTE"),
        "staged_armed_count":  sum(1 for s in signals if "PROBE" in s.get("campaign_verdict","")),
        # Discovery
        "discovery_count":     len(result.get("discovery",[])),
        "vanguard_count":      len(vg_rows),
        # Superbrain pipeline metadata
        "vetoes_fired":        summary_j.get("vetoes_fired",0),
        "verdicts_changed":    summary_j.get("verdicts_changed",0),
        "top_execute":         [s.get("ticker") for s in execute],
        "top_armed":           summary_j.get("top_armed",[s.get("ticker") for s in armed[:8]]),
        # WBS
        "wbs_count":           len(wbs_rows),
        "wbs_probable":        wbs_grades.get("PROBABLE",0),
        "wbs_possible":        wbs_grades.get("POSSIBLE",0),
        "wbs_unlikely":        wbs_grades.get("UNLIKELY",0),
        "wbs_imminent":        wbs_grades.get("IMMINENT",0),
        "wbs_avg_score":       result.get("wall_break_summary",{}).get("wbs_avg",0),
        "wbs_max_score":       result.get("wall_break_summary",{}).get("wbs_max",0),
        # EIL
        "eil_count":           len(eil_rows),
        "eil_execute_now":     eil_verdicts.get("EXECUTE",0) + eil_verdicts.get("EXECUTE_NOW",0),
        "eil_execute_caution": eil_verdicts.get("EXECUTE_WITH_CAUTION",0),
        "eil_defer":           eil_verdicts.get("WATCHLIST",0),
        "eil_stand_down":      eil_verdicts.get("BLOCKED",0) + eil_verdicts.get("STAND_DOWN_MICROSTRUCTURE",0),
        "eil_advisory_mode":   len(eil_rows)>0 and all(
            r.get("eil_v3_verdict","")=="ADVISORY_ONLY" for r in eil_rows),
        # Morning validation
        "mv_count":            len(mv_rows),
        "mv_valid_count":      sum(1 for r in mv_rows if r.get("mv_verdict") in ("VALID","TRIGGERED")),
        "mv_drifted_count":    sum(1 for r in mv_rows if r.get("mv_verdict")=="DRIFTED"),
        "mv_invalidated_count":sum(1 for r in mv_rows if r.get("mv_verdict") in
                                   ("INVALIDATED","SPREAD_WIDE","DTE_STALE")),
        "mv_lane_counts":      mv_lane_counts,
        "mv_permission_counts": mv_permission_counts,
        "mv_state_counts":     mv_state_counts,
        "mv_lab_alignment_counts": mv_lab_alignment_counts,
        "mv_lab_alignment_conflict_count": mv_lab_alignment_counts.get("CONFLICT", 0),
        "mv_go_now_count":     max(mv_lane_counts.get("GO_NOW", 0), mv_permission_counts.get("GO", 0)),
        "mv_go_limit_count":   max(mv_lane_counts.get("GO_LIMIT", 0), mv_permission_counts.get("GO_LIMIT", 0)),
        "mv_probe_count":      max(mv_lane_counts.get("PROBE", 0), mv_permission_counts.get("PROBE", 0)),
        "mv_contract_repair_count": max(mv_lane_counts.get("CONTRACT_REPAIR", 0), mv_permission_counts.get("CONTRACT_REPAIR", 0)),
        "mv_blocked_count":    max(mv_lane_counts.get("STAND_DOWN", 0), mv_permission_counts.get("BLOCKED", 0)),
        "mv_confirmed_count":  mv_state_counts.get("CONFIRMED", 0),
        "mv_validated_at":     mv_rows[0].get("mv_validated_at","") if mv_rows else "",
        # EOD candidate slate
        "eod_candidate_count":  len(eod_candidate_rows),
        "eod_execute_count":    sum(
            1 for r in eod_candidate_rows
            if "EXECUTE" in str(r.get("eod_candidate_status") or r.get("candidate_status") or "").upper()
        ),
        # GARCH
        **result.get("garch_stats",{}),
        # Priority ranking
        "top_priority":        [s.get("ticker") for s in sorted(
            [x for x in signals if x.get("priority_rank",9999)<=10],
            key=lambda x: x.get("priority_rank",9999))],
        "data_weak_count":     sum(1 for s in signals if str(s.get("ev_status","")).upper()=="DATA_WEAK"),
        "exec_mode_full":      sum(1 for s in signals if s.get("thesis_decision","")=="GO"),
        "exec_mode_reduced":   sum(1 for s in signals if "REDUCED" in s.get("v5_execution_mode","")),
        "exec_mode_probe":     sum(1 for s in signals if s.get("thesis_decision","")=="PROBE"),
        "win_rate_bridge_count":0,
    }

    result["_cache_signature"] = current_cache_signature
    result["cache_refresh"] = {
        "mode": "FILE_SIGNATURE",
        "watched_files": current_cache_signature,
    }
    _run_cache[run_id] = result
    return result

# â”€â”€â”€ ROUTES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€



# Lightweight API response helpers.
# The lab still builds the full in-memory run for ranking and governance, but
# the browser receives a compact payload so large EIL/Options runs do not stall.
_LAB_COMPACT_BASE_FIELDS = {
    "ticker", "tier", "phase", "intent", "regime", "direction",
    "canonical_direction", "resolved_direction", "footprint_direction", "primary_direction",
    "candidate_status", "eod_candidate_status", "has_eod_candidate_manifest_row",
    "lab_status", "lab_verdict", "lab_tradeable", "lab_hidden_by_default", "lab_execution_status",
    "lab_conflict_state", "conflict_state", "execution_lock_reason", "requires_live_validation",
    "execution_mode", "execution_verdict", "execution_category", "campaign_verdict",
    "options_verdict", "effective_execution_verdict",
    "display_campaign", "display_eod_candidate_status", "display_execution_category",
    "display_execution_mode", "display_final_verdict",
    "position_size_display", "pse_execution_mode", "priority_rank", "priority_score", "trade_idea_id",
    "sb_schema_ok", "sb_final_verdict", "sb_campaign", "sb_execution_mode",
    "sb_position_size_display", "sb_position_size_pct", "sb_vetoes", "sb_vetoes_count",
    "sb_conv_score", "sb_conv_detail", "sb_current_stage", "sb_enter_now_stages",
    "sb_alert_stages", "sb_stages_missed", "sb_time_stop_date", "sb_checkpoint_rule",
    "sb_ladder_summary", "sb_instrument_now", "sb_verdict_reason",
    "rr", "ev", "ev_final", "ev_net", "ev_status", "ev2_decision_hint",
    "ev2_ev_conf_adj", "ev2_quality_score", "fd_ev_used", "win_rate", "win_rate_20d",
    "win_rate_source", "composite", "current_price", "signal_price", "spot_price",
    "underlying_price", "live_vwap", "strike", "premium", "premium_mid", "premium_label",
    "premium_is_synthetic", "ivp", "ivp_label", "qomega_gate", "qomega_gate_reason",
    "tce_entry_type", "tce_trigger_reason", "tce_trigger_score", "tce_trigger_state",
    "physics_state_id", "hidden_state_label", "state_transition_label", "phase_transition_probability",
    "precor_intent", "sector", "sector_short", "gics_sector", "sector_name", "sector_etf", "sector_proxy", "industry", "macro_regime", "macro_regime_label",
    "regime_drift_status", "time_horizon", "horizon_bucket", "hold_label", "hold_urgency",
}
_LAB_COMPACT_PREFIXES = (
    "opt__", "wbs__", "garch__", "mv__", "doss__", "display_", "lab_", "sb_",
    "ev2_", "mv_", "tce_", "qomega_", "eil_",
)
_LAB_COMPACT_VG_FIELDS = {
    "vg__physics_state_id", "vg__hidden_state_label", "vg__state_transition_label",
    "vg__phase_transition_probability", "vg__precor_intent", "vg__actuarial_match_type",
    "vg__actuarial_ev_weight", "vg__behaviour_state_key", "vg__behaviour_state_hash",
    "vg__catalyst_overlay",
}
_LAB_COMPACT_DISCOVERY_FIELDS = {
    "ticker", "tier", "tier_label", "phase", "wyckoff_phase", "composite_score",
    "composite", "wyckoff_score", "win_prob", "win_probability", "entry_price",
    "support", "stop_loss", "stop", "control", "trend",
}
_LAB_DROP_TOPLEVEL = {
    "execution_signals", "options_intelligence", "vanguard_signals", "wall_break_scores",
    "garch_forecasts", "v5_signals",
}

def _compact_lab_signal(sig):
    if not isinstance(sig, dict):
        return sig
    out = {}
    for k, v in sig.items():
        if (
            k in _LAB_COMPACT_BASE_FIELDS
            or k in _LAB_COMPACT_VG_FIELDS
            or k.startswith(_LAB_COMPACT_PREFIXES)
        ):
            out[k] = v
    return out

def _compact_discovery_row(row):
    if not isinstance(row, dict):
        return row
    return {k: v for k, v in row.items() if k in _LAB_COMPACT_DISCOVERY_FIELDS}

def _opportunity_book_summary(run_id, book):
    if not isinstance(book, dict):
        return {"run_id": run_id, "available": False}
    return {
        "run_id": book.get("run_id") or run_id,
        "available": True,
        "candidate_count": book.get("candidate_count", 0),
        "created_at_utc": book.get("created_at_utc", ""),
        "verdict_counts": book.get("verdict_counts", {}),
    }

def _slim_lab_payload(payload):
    if str(request.args.get("full", "")).lower() in ("1", "true", "yes"):
        return payload
    out = {}
    for k, v in (payload or {}).items():
        if k in _LAB_DROP_TOPLEVEL:
            continue
        if k == "signals":
            out[k] = [_compact_lab_signal(s) for s in (v or [])]
        elif k == "discovery":
            out[k] = [_compact_discovery_row(r) for r in (v or [])]
        elif k == "opportunity_book":
            out[k] = _opportunity_book_summary(payload.get("run_id", ""), v)
        else:
            out[k] = v
    out["payload_mode"] = "SLIM"
    return out

def _cached_run_payload(run_id=None):
    rid = run_id or _latest_run_id()
    return rid, _run_cache.get(rid)

def _sector_summary_from_cached_run(run_id=None):
    rid, payload = _cached_run_payload(run_id)
    if not payload:
        return {"ok": False, "run_id": rid, "reason": "run_not_loaded"}
    sectors = {}
    total_execute = 0
    for sig in payload.get("signals", []) or []:
        sector = sig.get("sector") or sig.get("sector_short") or "N/A"
        short = sig.get("sector_short") or sector
        key = str(short or "N/A").upper()
        row = sectors.setdefault(key, {
            "sector_short": key,
            "sector": sector,
            "execute_count": 0,
            "ewr_count": 0,
            "put_count": 0,
            "call_count": 0,
            "ev_sum": 0.0,
            "ev_n": 0,
            "sector_etf": "",
        })
        verdict = str(sig.get("lab_verdict") or sig.get("sb_final_verdict") or sig.get("options_verdict") or "").upper()
        if verdict in ("GO", "GO_LIMIT", "PROBE", "EXECUTE", "EOD_EXEC", "EXECUTE_WITH_CAUTION"):
            row["execute_count"] += 1
            total_execute += 1
        if verdict in ("EXECUTE_WITH_CAUTION", "EOD_CAUTION"):
            row["ewr_count"] += 1
        direction = str(sig.get("direction") or sig.get("primary_direction") or "").upper()
        if "PUT" in direction:
            row["put_count"] += 1
        elif "CALL" in direction:
            row["call_count"] += 1
        try:
            ev = float(sig.get("ev") or sig.get("ev_final") or sig.get("ev2_ev_conf_adj") or 0)
            row["ev_sum"] += ev
            row["ev_n"] += 1
        except Exception:
            pass
    rows = []
    for row in sectors.values():
        n = row.pop("ev_n", 0)
        ev_sum = row.pop("ev_sum", 0.0)
        row["avg_ev"] = round(ev_sum / n, 4) if n else 0.0
        row["concentration_pct"] = round((row["execute_count"] / total_execute * 100.0), 1) if total_execute else 0.0
        row["concentration_flag"] = "HIGH" if row["concentration_pct"] >= 35 else "MEDIUM" if row["concentration_pct"] >= 20 else "NORMAL"
        rows.append(row)
    rows.sort(key=lambda r: r.get("execute_count", 0), reverse=True)
    return {
        "ok": True,
        "run_id": rid,
        "total_execute": total_execute,
        "sectors_represented": len([r for r in rows if r.get("execute_count", 0) > 0]),
        "sector_summary": rows,
    }

def _regime_alerts_from_cached_run(run_id=None):
    rid, payload = _cached_run_payload(run_id)
    macro = (payload or {}).get("macro", {}) if payload else {}
    current_regime = macro.get("regime_state") or macro.get("regime") or "UNKNOWN"
    return {
        "ok": True,
        "run_id": rid,
        "current_regime": current_regime,
        "alert_count": 0,
        "alerts": [],
    }

@app.route("/")
def index():
    return send_from_directory("static","index.html")

@app.route("/api/health")
def api_health():
    runs = _list_runs()
    return jsonify({
        "status": "ok",
        "pipeline_dir": str(RUNS_DIR),
        "pipeline_dir_exists": RUNS_DIR.exists(),
        "run_count": len(runs),
        "latest_run": runs[0] if runs else None,
        "server_time": _utc_iso(),
        "version": "2.0 â€” EIL-primary architecture"
    })

@app.route("/api/runs")
def api_runs():
    runs = _list_runs()
    return jsonify({"runs": runs, "latest": runs[0] if runs else None, "count": len(runs)})

@app.route("/api/run/<run_id>")
def api_run(run_id):
    return jsonify(_slim_lab_payload(_load_run(run_id)))

@app.route("/api/run/latest")
def api_run_latest():
    runs = _list_runs()
    if not runs:
        return jsonify({"error": "No runs found in " + str(RUNS_DIR)}), 404
    return jsonify(_slim_lab_payload(_load_run(runs[0])))

@app.route("/api/sector_summary")
def api_sector_summary():
    return jsonify(_sector_summary_from_cached_run())

@app.route("/api/regime_alerts")
def api_regime_alerts():
    return jsonify(_regime_alerts_from_cached_run())

@app.route("/api/orchestrator/status")
def api_orchestrator_status():
    manifest = _latest_manifest()
    if not manifest:
        return jsonify({"ok": False, "error": "No runs found"}), 404
    return jsonify({
        "ok": True,
        "run_id": manifest.get("run_id"),
        "run_health_score": manifest.get("run_health_score", 0),
        "run_tradeable": manifest.get("run_tradeable", False),
        "run_tradeable_label": manifest.get("run_tradeable_label", ""),
        "run_execution_permission": manifest.get("run_execution_permission", ""),
        "run_prep_permission": manifest.get("run_prep_permission", ""),
        "manual_review_enabled": manifest.get("manual_review_enabled", False),
        "pipeline_interpreter_prep_enabled": manifest.get("pipeline_interpreter_prep_enabled", False),
        "phase_status": manifest.get("phase_status", {}),
        "missing_files": [
            k for k, v in (manifest.get("output_files") or {}).items()
            if not v and k != "morning_validation"
        ],
        "stale_flags": manifest.get("stale_flags", []),
        "conflict_flags": manifest.get("conflict_flags", []),
        "fatal_flags": manifest.get("fatal_flags", []),
        "next_action": manifest.get("next_action", "UNKNOWN"),
    })

@app.route("/api/orchestrator/manifest/latest")
def api_orchestrator_manifest_latest():
    manifest = _latest_manifest()
    if not manifest:
        return jsonify({"ok": False, "error": "No runs found"}), 404
    return jsonify({"ok": True, "manifest": manifest})

@app.route("/api/orchestrator/manifest/<run_id>")
def api_orchestrator_manifest(run_id):
    manifest = load_final_run_manifest(run_id, RUNS_DIR) or write_final_run_manifest(run_id, RUNS_DIR)
    return jsonify({"ok": True, "manifest": manifest})

@app.route("/api/opportunity_book/latest")
def api_opportunity_book_latest():
    run_id = _latest_run_id()
    if not run_id:
        return jsonify({"ok": False, "error": "No runs found"}), 404
    return api_opportunity_book(run_id)

@app.route("/api/opportunity_book/<run_id>")
def api_opportunity_book(run_id):
    if str(request.args.get("full", "")).lower() in ("1", "true", "yes"):
        book = read_final_opportunity_book(run_id, RUNS_DIR)
        return jsonify({"ok": True, "payload_mode": "FULL", "opportunity_book": book})
    path = RUNS_DIR / run_id / "intelligence_lab" / f"final_opportunity_book_{run_id}.json"
    payload = _run_cache.get(run_id) or {}
    book = payload.get("opportunity_book") or {
        "run_id": run_id,
        "available": path.exists(),
        "path": str(path),
    }
    return jsonify({"ok": True, "payload_mode": "SUMMARY", "opportunity_book": book})

@app.route("/api/reload_morning", methods=["POST"])
def api_reload_morning():
    body = request.get_json(silent=True) or {}
    run_id = body.get("run_id","").strip()
    if run_id:
        dropped = _run_cache.pop(run_id, None)
        msg = f"Cache cleared for run {run_id}" if dropped else f"Run {run_id} was not cached"
    else:
        count = len(_run_cache)
        _run_cache.clear()
        msg = f"All {count} cached runs cleared"
    print(f"  ðŸ”„ /api/reload_morning â€” {msg}")
    return jsonify({"ok": True, "message": msg})

@app.route("/api/enter_trade", methods=["POST"])
def api_enter_trade():
    """Enter a Lab-approved trade and write the trade journal baton."""
    try:
        project_root = str(BASE_DIR)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from vanguard.trade_contract import create_contract, find_open_contract
        from avshunter_trade_journal import log_entry

        body = request.get_json(force=True)
        ticker            = str(body.get("ticker","")).strip().upper()
        entry_premium     = float(body.get("entry_premium", body.get("entry_price", 0)) or 0)
        entry_price       = float(body.get("underlying_entry_price", body.get("underlying_price", 0)) or 0)
        invalidation_price = float(body.get("invalidation_price",0) or 0)
        contracts         = int(float(body.get("contracts", 1) or 1))
        declared_R        = float(body.get("declared_R", 0) or 0)
        notes             = str(body.get("trade_notes", body.get("notes", "Logged via Intelligence Lab"))).strip()
        run_id            = body.get("run_id") or _list_runs()[0]

        if not ticker:
            return jsonify({"ok":False,"error":"ticker required"}), 400
        if entry_premium <= 0:
            return jsonify({"ok":False,"error":"entry_premium must be > 0"}), 400
        if contracts < 1:
            return jsonify({"ok":False,"error":"contracts must be >= 1"}), 400
        premium_risk_total = round(entry_premium * contracts * 100, 2)
        if declared_R <= 0:
            declared_R = premium_risk_total
        if invalidation_price <= 0:
            return jsonify({"ok":False,"error":"invalidation_price must be > 0"}), 400

        # Load signal
        payload = _load_run(run_id)
        sig = next((s for s in payload.get("signals",[])
                    if s.get("ticker","").upper() == ticker), None)
        if not sig:
            return jsonify({"ok":False,"error":f"{ticker} not in signals"}), 404

        manifest = payload.get("final_run_manifest") or write_final_run_manifest(run_id, RUNS_DIR)
        resolved = resolve_lab_tradeability(sig, manifest, _safe_open_journal_positions())
        sig.update({
            "lab_verdict": resolved["lab_verdict"],
            "lab_tradeable": resolved["lab_tradeable"],
            "conflict_state": resolved["conflict_state"],
            "conflict_flags": json.dumps(resolved["conflict_flags"], ensure_ascii=True),
            "veto_flags": json.dumps(resolved["veto_flags"], ensure_ascii=True),
            "execution_lock_reason": resolved["execution_lock_reason"],
            "requires_live_validation": resolved["requires_live_validation"],
            "morning_lab_alignment_status": resolved["morning_lab_alignment_status"],
            "morning_lab_alignment_reason": resolved["morning_lab_alignment_reason"],
            "source_verdicts_json": json.dumps(resolved["source_verdicts"], ensure_ascii=True),
        })
        user_confirmed_live_validation = bool(body.get("user_confirmed_live_validation"))
        if resolved["requires_live_validation"] and not user_confirmed_live_validation:
            return jsonify({
                "ok": False,
                "error": f"{ticker}: live validation confirmation required before entry",
                "lab_verdict": resolved["lab_verdict"],
                "execution_lock_reason": resolved["execution_lock_reason"],
                "morning_lab_alignment_status": resolved["morning_lab_alignment_status"],
                "morning_lab_alignment_reason": resolved["morning_lab_alignment_reason"],
            }), 400
        manual_entry_verdicts = {"GO", "GO_LIMIT", "PROBE"}
        entry_allowed = bool(resolved["lab_tradeable"]) and resolved["lab_verdict"] in manual_entry_verdicts
        if resolved["conflict_state"] == "HARD_CONFLICT" or not entry_allowed:
            return jsonify({
                "ok": False,
                "error": f"{ticker}: not Lab-tradeable",
                "lab_verdict": resolved["lab_verdict"],
                "lab_tradeable": resolved["lab_tradeable"],
                "manual_entry_allowed_verdicts": sorted(manual_entry_verdicts),
                "conflict_state": resolved["conflict_state"],
                "conflict_flags": resolved["conflict_flags"],
                "veto_flags": resolved["veto_flags"],
                "execution_lock_reason": resolved["execution_lock_reason"],
                "morning_lab_alignment_status": resolved["morning_lab_alignment_status"],
                "morning_lab_alignment_reason": resolved["morning_lab_alignment_reason"],
            }), 400

        def _f_new(key, default=0.0):
            try:
                v = sig.get(key,"")
                if str(v).strip() in ("","N/A","nan","None"): return default
                return float(v)
            except Exception:
                return default

        direction  = sig.get("direction","PUT").upper()
        instrument = sig.get("sb_instrument_now","") or sig.get("options_strategy","")
        strike     = sig.get("strike") or sig.get("contract_strike") or sig.get("opt__contract_strike")
        expiry     = sig.get("expiry") or sig.get("contract_expiry") or sig.get("opt__contract_expiry")
        dte        = sig.get("dte") or sig.get("contract_dte") or sig.get("opt__contract_dte")
        entry_underlying = entry_price or _f_new("current_price") or _f_new("underlying_price") or entry_premium
        horizon    = _extract_time_horizon(sig) or "20D"
        contract_horizon = _contract_horizon_type(horizon)
        hold_period = _extract_hold_period(sig)
        hold_urgency = _first_signal_value(sig, ["hold_urgency", "opt__hold_urgency", "exe__hold_urgency", "vg__hold_urgency", "doss__opt__hold_urgency"])
        horizon_hold_alignment = _horizon_hold_alignment(sig)
        execution_category = _extract_execution_category(sig)

        ev       = _f_new("ev2_ev_conf_adj") or _f_new("ev")
        win_rate = _f_new("ev2_p_win_blended") or 0.5
        edge_q   = "HIGH" if float(sig.get("eil_composite_score",0) or 0) >= 80 else "MODERATE"
        vanguard_contract_status = "skipped_existing"
        existing = find_open_contract(ticker)
        if not existing:
            create_contract(
                ticker=ticker, entry_price=entry_underlying, direction=direction,
                horizon_type=contract_horizon, edge_quality=edge_q,
                entry_ev=ev, entry_win_rate=win_rate,
                entry_state_hash=sig.get("state_v2_key") or sig.get("vg__state_v2_key") or "eil_v2",
                entry_vol_regime=sig.get("macro_regime_label") or sig.get("macro_regime","TRANSITIONAL"),
                entry_trend_direction=sig.get("dominant_trend","NEUTRAL"),
                entry_trend_maturity="EARLY",
                entry_structure_quality=sig.get("eil_v3_verdict","NEUTRAL"),
                entry_macro_regime=sig.get("macro_regime_label") or sig.get("macro_regime","TRANSITIONAL"),
                entry_catalyst_proximity="UNKNOWN",
                entry_adx=_f_new("adx",20), entry_atr_percentile=_f_new("atr_pct",50),
                invalidation_price=invalidation_price,
                max_expected_mae=entry_underlying * 0.5,
            )
            vanguard_contract_status = "created"

        trade_id = log_entry(
            db_path=_JOURNAL_DB,
            runs_dir=RUNS_DIR,
            ticker=ticker,
            run_id=run_id,
            entry_premium=entry_premium,
            contracts=contracts,
            notes=notes,
            options_direction=direction,
            strike=float(strike) if str(strike).strip() not in ("", "None", "nan") else None,
            expiry=str(expiry or ""),
            dte_at_entry=int(float(dte)) if str(dte).strip() not in ("", "None", "nan") else None,
            rr_predicted=_f_new("rr_options") or _f_new("rr"),
            ev_predicted=ev,
            structural_target=_f_new("target_price") or _f_new("opt__structural_target"),
            sb_verdict=sig.get("lab_verdict", ""),
            sb_campaign=sig.get("campaign_verdict", ""),
            underlying_price_at_entry=entry_underlying,
        )
        _update_lab_journal_row(trade_id, sig, {**body, "declared_R": declared_R}, premium_risk_total)
        return jsonify({
            "ok": True,
            "ticker": ticker,
            "message": f"Trade journal row opened for {ticker}",
            "trade_id": trade_id,
            "trade_idea_id": sig.get("trade_idea_id"),
            "premium_risk_total": premium_risk_total,
            "declared_R": declared_R,
            "journal_status": "OPEN",
            "vanguard_contract_status": vanguard_contract_status,
            "contract_summary": {
                "ticker": ticker,
                "direction": direction,
                "horizon": horizon,
                "contract_horizon_type": contract_horizon,
                "hold_period": hold_period,
                "hold_urgency": hold_urgency,
                "horizon_hold_alignment": horizon_hold_alignment,
                "execution_category": execution_category,
                "entry_price": entry_underlying,
                "entry_premium": entry_premium,
                "contracts": contracts,
                "strike": strike,
                "expiry": expiry,
                "invalidation_price": invalidation_price,
                "ev": ev,
                "win_rate": win_rate,
                "eil_composite": sig.get("eil_composite_score",""),
                "lab_verdict": sig.get("lab_verdict"),
                "conflict_state": sig.get("conflict_state"),
            }
        })

        # NEW GATE: accept EXECUTE verdict OR v5 GO decision
        opt_v     = sig.get("options_verdict","").upper()
        camp_v    = sig.get("campaign_verdict","").upper()
        thesis    = sig.get("thesis_decision","").upper()
        sb_v      = sig.get("sb_final_verdict","").upper()

        tradeable = (
            (opt_v == "EXECUTE" and camp_v in ("READY_EXECUTE","READY_PROBE")) or
            (thesis == "GO") or
            (sb_v == "EXECUTE")
        )
        if not tradeable:
            return jsonify({
                "ok": False,
                "error": f"{ticker}: options_verdict={opt_v}, campaign={camp_v}, thesis={thesis} â€” not tradeable"
            }), 400

        existing = find_open_contract(ticker)
        if existing:
            return jsonify({"ok":False,"error":f"Open contract already exists for {ticker}: {existing.name}"}), 409

        def _f(key, default=0.0):
            try:
                v = sig.get(key,"")
                if str(v).strip() in ("","N/A","nan","None"): return default
                return float(v)
            except: return default

        direction  = sig.get("direction","PUT").upper()
        instrument = sig.get("sb_instrument_now","") or sig.get("options_strategy","")
        horizon    = "20D"
        if "SHORT" in instrument.upper():  horizon = "5D"
        elif "STANDARD" in instrument.upper(): horizon = "10D"

        ev       = _f("ev2_ev_conf_adj") or _f("ev")
        win_rate = _f("ev2_p_win_blended") or 0.5
        edge_q   = "HIGH" if float(sig.get("eil_composite_score",0) or 0) >= 80 else "MODERATE"
        contract = create_contract(
            ticker=ticker, entry_price=entry_price, direction=direction,
            horizon_type=horizon, edge_quality=edge_q,
            entry_ev=ev, entry_win_rate=win_rate,
            entry_state_hash=sig.get("state_v2_key") or sig.get("vg__state_v2_key") or "eil_v2",
            entry_vol_regime=sig.get("macro_regime","TRANSITIONAL"),
            entry_trend_direction=sig.get("dominant_trend","NEUTRAL"),
            entry_trend_maturity="EARLY",
            entry_structure_quality=sig.get("eil_v3_verdict","NEUTRAL"),
            entry_macro_regime=sig.get("macro_regime","TRANSITIONAL"),
            entry_catalyst_proximity="UNKNOWN",
            entry_adx=_f("adx",20), entry_atr_percentile=_f("atr_pct",50),
            invalidation_price=invalidation_price,
            max_expected_mae=entry_price * 0.5,
        )
        return jsonify({
            "ok": True, "ticker": ticker,
            "message": f"Trade contract created for {ticker}",
            "contract_summary": {
                "ticker": ticker, "direction": direction, "horizon": horizon,
                "entry_price": entry_price, "invalidation_price": invalidation_price,
                "ev": ev, "win_rate": win_rate,
                "eil_composite": sig.get("eil_composite_score",""),
                "options_verdict": opt_v, "thesis_decision": thesis,
            }
        })
    except Exception as e:
        import traceback
        return jsonify({"ok":False,"error":str(e),"trace":traceback.format_exc()}), 500

@app.route("/api/open_contracts")
def api_open_contracts():
    try:
        project_root = str(BASE_DIR)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from vanguard.trade_contract import list_open_contracts, load_contract
        contracts = []
        for path in list_open_contracts():
            try:
                c = load_contract(path)
                contracts.append({
                    "ticker":             c.get("ticker"),
                    "entry_date":         c.get("entry_date"),
                    "direction":          c.get("direction"),
                    "horizon_type":       c.get("horizon_type"),
                    "entry_price":        c.get("entry_price"),
                    "invalidation_price": c.get("invalidation_price"),
                    "status":             c.get("status"),
                    "days_in_trade":      c.get("days_in_trade"),
                    "entry_ev":           c.get("entry_ev"),
                    "edge_quality":       c.get("edge_quality"),
                })
            except: pass
        return jsonify({"ok":True,"contracts":contracts,"count":len(contracts)})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 500

@app.route("/api/export_csv")
def api_export_csv():
    try:
        runs = _list_runs()
        run_id = request.args.get("run_id","").strip() or (runs[0] if runs else "")
        if not run_id:
            return jsonify({"ok":False,"error":"No runs available"}), 404
        payload = _load_run(run_id)
        signals = payload.get("signals",[])
        verdicts = [v.strip().upper() for v in
                    request.args.get("verdict","EXECUTE,ARMED").split(",") if v.strip()]
        rr_min = request.args.get("rr_min")
        ev_min = request.args.get("ev_min")
        match_types = {v.strip().upper() for v in request.args.get("actuarial_match_type", "").split(",") if v.strip()}
        catalyst_overlays = {v.strip().upper() for v in request.args.get("catalyst_overlay", "").split(",") if v.strip()}
        behaviour_hashes = {v.strip().lower() for v in request.args.get("behaviour_state_hash", "").split(",") if v.strip()}
        filtered = []
        for s in signals:
            ov = (s.get("lab_verdict","") or s.get("options_verdict","") or s.get("sb_final_verdict","")).upper()
            if verdicts and ov not in verdicts: continue
            if rr_min:
                try:
                    if float(s.get("rr_options",0) or s.get("rr",0) or 0) < float(rr_min): continue
                except: pass
            if ev_min:
                try:
                    ev_val = float(s.get("ev2_ev_conf_adj") or s.get("ev") or 0)
                    if ev_val < float(ev_min): continue
                except: pass
            if match_types:
                mt = _first_signal_value(s, ["actuarial_match_type", "vg__actuarial_match_type"]).upper()
                if mt not in match_types: continue
            if catalyst_overlays:
                co = _first_signal_value(s, ["catalyst_overlay", "vg__catalyst_overlay"]).upper()
                if co not in catalyst_overlays: continue
            if behaviour_hashes:
                bh = _first_signal_value(s, ["behaviour_state_hash", "vg__behaviour_state_hash"]).lower()
                if bh not in behaviour_hashes: continue
            filtered.append(s)
        if not filtered:
            return jsonify({"ok":False,"error":"No signals match filters"}), 404
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(filtered[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(filtered)
        return Response(
            buf.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="avshunter_{run_id}.csv"'}
        )
    except Exception as e:
        import traceback
        return jsonify({"ok":False,"error":str(e),"trace":traceback.format_exc()}), 500


# â”€â”€â”€ SPRINT 3: KPI SCOREBOARD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.route("/api/kpi")
def api_kpi():
    """
    KPI scoreboard â€” computes pipeline health metrics across the last N runs.

    Business model alignment:
      Pattern  â†’ candidate_ratio (discovery finding setups)
      Profile  â†’ actuarial_match_rate (edge database coverage)
      Players  â†’ call_put_ratio (direction balance)
      Gamma    â†’ avg_iv_rank (options premium quality)
      Contract â†’ avg_spread_pct (executability)
      Trigger  â†’ morning_pass_rate (live confirmation rate)
      Kill     â†’ stale_data_rate (data integrity)
      Monetise â†’ execute_rate, avg_trust_score (pipeline confidence)

    Returns targets alongside actuals so the operator can see progress.
    """
    try:
        n = int(request.args.get("n", 10))
        run_ids = _list_runs()[:n]

        kpi_rows = []
        for rid in run_ids:
            try:
                payload = _load_run(rid)
                sigs    = payload.get("signals", [])
                if not sigs:
                    continue

                total   = len(sigs)
                execute = sum(1 for s in sigs if str(s.get("mv_verdict","")).upper() == "EXECUTE")
                probe   = sum(1 for s in sigs if str(s.get("mv_verdict","")).upper() == "PROBE")
                calls   = sum(1 for s in sigs if str(s.get("direction","")).upper() == "CALL")
                puts    = sum(1 for s in sigs if str(s.get("direction","")).upper() == "PUT")
                fresh   = sum(1 for s in sigs if str(s.get("data_quality_state","")).upper() == "FRESH")
                stale   = sum(1 for s in sigs if str(s.get("data_quality_state","")).upper() in ("STALE","BLOCKED"))
                no_match= sum(1 for s in sigs if str(s.get("no_match","")).lower() in ("true","1","yes"))

                trust_scores = [float(s["signal_trust_score"]) for s in sigs
                                if s.get("signal_trust_score") not in (None, "", "nan")]
                avg_trust = round(sum(trust_scores) / len(trust_scores), 1) if trust_scores else 0.0

                spreads = []
                for s in sigs:
                    bd = s.get("mv_breakdown", "")
                    try:
                        bd_dict = json.loads(bd) if isinstance(bd, str) else bd or {}
                        sp = bd_dict.get("spread", "")
                        pct = float(str(sp).split("(")[1].split("%")[0]) if "(" in str(sp) else None
                        if pct is not None:
                            spreads.append(pct)
                    except Exception:
                        pass
                avg_spread = round(sum(spreads) / len(spreads), 1) if spreads else None

                kpi_rows.append({
                    "run_id":            rid,
                    "total_signals":     total,
                    "execute_count":     execute,
                    "probe_count":       probe,
                    "execute_rate":      round(execute / total, 3) if total else 0,
                    "call_count":        calls,
                    "put_count":         puts,
                    "call_put_ratio":    round(calls / puts, 2) if puts else None,
                    "fresh_count":       fresh,
                    "stale_count":       stale,
                    "stale_rate":        round(stale / total, 3) if total else 0,
                    "no_match_count":    no_match,
                    "no_match_rate":     round(no_match / total, 3) if total else 0,
                    "avg_trust_score":   avg_trust,
                    "avg_spread_pct":    avg_spread,
                })
            except Exception:
                continue

        # KPI targets (Sprint 3 â€” business model alignment)
        targets = {
            "execute_rate":    {"target": 0.10, "label": "â‰¥10% of signals EXECUTE"},
            "call_put_ratio":  {"target": "market_dependent", "label": "Not 100/0 without explanation"},
            "stale_rate":      {"target": 0.02, "label": "<2% stale data"},
            "no_match_rate":   {"target": 0.20, "label": "<20% actuarial no-match"},
            "avg_trust_score": {"target": 80.0, "label": "â‰¥80 avg signal trust"},
            "avg_spread_pct":  {"target": 8.0,  "label": "â‰¤8% avg options spread"},
        }

        # Summary across all runs
        if kpi_rows:
            summary = {
                "runs_analysed":       len(kpi_rows),
                "avg_execute_rate":    round(sum(r["execute_rate"] for r in kpi_rows) / len(kpi_rows), 3),
                "avg_stale_rate":      round(sum(r["stale_rate"] for r in kpi_rows) / len(kpi_rows), 3),
                "avg_trust_score":     round(sum(r["avg_trust_score"] for r in kpi_rows) / len(kpi_rows), 1),
                "direction_balanced":  any(
                    r["call_count"] > 0 and r["put_count"] > 0 for r in kpi_rows
                ),
            }
        else:
            summary = {"runs_analysed": 0, "message": "No runs with signals found"}

        return jsonify({"ok": True, "kpi": kpi_rows, "targets": targets, "summary": summary})

    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# â”€â”€â”€ ITEM 3: OUTCOME CAPTURE â€” same principle as trade entry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Three endpoints mirror the trade entry flow:
#   /api/monitor_positions  â€” see open positions with current marks (read-only)
#   /api/log_exit           â€” record an exit and classify the outcome
#   /api/outcomes           â€” view closed trade performance vs predicted edge

_JOURNAL_DB = BASE_DIR / "data" / "journal" / "trade_journal.db"


@app.route("/api/monitor_positions")
def api_monitor_positions():
    """
    Read-only view of all open positions with current marks and unrealised P&L.
    Calls outcome_capture.run_monitor in dry_run=True mode â€” no writes.

    Returns each open position with:
      - current mark from Tastytrade or Polygon
      - unrealised P&L %
      - whether any exit condition is triggered (time stop, invalidation, expiry)
      - action recommendation: HOLD / REVIEW / EXIT
    """
    try:
        import sys as _sys
        if str(BASE_DIR) not in _sys.path:
            _sys.path.insert(0, str(BASE_DIR))
        from outcome_capture import run_monitor, fetch_current_mark, classify_exit_reason
        from avshunter_trade_journal import get_open_positions

        if not _JOURNAL_DB.exists():
            return jsonify({
                "ok": True,
                "open_positions": [],
                "message": "No trade journal found â€” no positions to monitor",
                "journal_path": str(_JOURNAL_DB),
            })

        journal_positions = get_open_positions(_JOURNAL_DB)
        monitor_message = ""
        try:
            result = run_monitor(db_path=_JOURNAL_DB, dry_run=True)
        except Exception as exc:
            result = {
                "success": False,
                "open": len(journal_positions),
                "exits_detected": 0,
                "manual_needed": len(journal_positions),
                "still_open": len(journal_positions),
            }
            monitor_message = f"Live monitor unavailable; showing open journal rows. {exc}"

        # Enrich with unrealised P&L for display
        raw_open = result.get("still_open", [])
        if isinstance(raw_open, list):
            open_pos = raw_open if raw_open else journal_positions
        else:
            # outcome_capture.run_monitor returns counts for still_open; the Lab
            # needs the actual journal rows so open trades remain visible.
            open_pos = journal_positions

        enriched = []
        for pos in open_pos:
            entry   = float(pos.get("entry_premium") or 0)
            mark    = pos.get("current_mark")
            if mark is None:
                try:
                    mark = fetch_current_mark(pos)
                except Exception:
                    mark = None
            pnl_pct = round((mark - entry) / entry * 100, 1) if (mark and entry) else None
            action  = "HOLD"
            exit_reason = None
            try:
                exit_reason = classify_exit_reason(pos, mark)
            except Exception:
                exit_reason = None
            if pos.get("exit_triggered") or exit_reason:
                action = "EXIT"
            elif pnl_pct is not None and pnl_pct < -40:
                action = "REVIEW"
            elif mark is None:
                action = "REVIEW"
            enriched.append({
                **pos,
                "current_mark": mark,
                "unrealised_pnl_pct": pnl_pct,
                "action":             action,
                "exit_reason":        exit_reason,
            })

        manual_needed_raw = result.get("manual_needed", [])
        if isinstance(manual_needed_raw, list):
            manual_needed_list = manual_needed_raw
            manual_needed_count = len(manual_needed_raw)
        else:
            manual_needed_count = int(manual_needed_raw or 0)
            manual_needed_list = [p for p in enriched if p.get("action") == "REVIEW"]

        return jsonify({
            "ok":              True,
            "open_count":      len(enriched),
            "exits_triggered": result.get("exits_detected", 0),
            "manual_needed":   max(manual_needed_count, len(manual_needed_list)),
            "open_positions":  enriched,
            "manual_needed_list": manual_needed_list,
            "message": monitor_message,
        })

    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/log_exit", methods=["POST"])
def api_log_exit():
    """
    Log an exit for an open position.
    Same principle as /api/enter_trade â€” single action, immediate feedback.

    Body (JSON):
      ticker        â€” required
      exit_premium  â€” required (actual exit price per contract)
      exit_reason   â€” optional: TIME_STOP | INVALIDATION | TARGET_HIT | EXPIRY | MANUAL
      trade_id      â€” optional (auto-detected from journal if omitted)
      notes         â€” optional

    Returns outcome classification and P&L immediately.
    """
    try:
        import sys as _sys
        if str(BASE_DIR) not in _sys.path:
            _sys.path.insert(0, str(BASE_DIR))
        from outcome_capture import classify_outcome
        from avshunter_trade_journal import get_open_positions, log_exit, get_db

        body          = request.get_json(force=True)
        ticker        = str(body.get("ticker", "")).strip().upper()
        exit_premium  = body.get("exit_premium")
        exit_reason   = str(body.get("exit_reason", "MANUAL")).strip().upper()
        trade_id      = body.get("trade_id")
        notes         = str(body.get("notes", "Logged via Intelligence Lab")).strip()

        if not ticker:
            return jsonify({"ok": False, "error": "ticker required"}), 400
        if exit_premium is None:
            return jsonify({"ok": False, "error": "exit_premium required"}), 400

        exit_premium = float(exit_premium)
        if exit_premium < 0:
            return jsonify({"ok": False, "error": "exit_premium must be >= 0"}), 400

        if not _JOURNAL_DB.exists():
            return jsonify({"ok": False, "error": f"Journal not found: {_JOURNAL_DB}"}), 404

        lab_snapshot = {}
        # Auto-detect trade_id if not supplied
        if not trade_id:
            positions = get_open_positions(_JOURNAL_DB)
            match = next(
                (p for p in positions if str(p.get("ticker", "")).upper() == ticker),
                None
            )
            if not match:
                return jsonify({
                    "ok": False,
                    "error": f"{ticker} not found in open positions. "
                             "Check /api/monitor_positions or supply trade_id."
                }), 404
            trade_id      = int(match.get("trade_id", 0) or 0)
            entry_premium = float(match.get("entry_premium") or 0)
            rr_predicted  = float(match.get("rr_predicted") or 0)
            lab_snapshot  = match
        else:
            trade_id      = int(trade_id)
            entry_premium = float(body.get("entry_premium", 0) or 0)
            rr_predicted  = float(body.get("rr_predicted", 0) or 0)
            try:
                positions = get_open_positions(_JOURNAL_DB)
                lab_snapshot = next((p for p in positions if int(p.get("trade_id", 0) or 0) == trade_id), {})
                entry_premium = entry_premium or float(lab_snapshot.get("entry_premium") or 0)
                rr_predicted = rr_predicted or float(lab_snapshot.get("rr_predicted") or 0)
            except Exception:
                lab_snapshot = {}

        # Compute P&L and outcome
        contracts    = int(float(lab_snapshot.get("contracts") or body.get("contracts", 1) or 1))
        declared_R   = float(lab_snapshot.get("declared_R") or body.get("declared_R", 0) or 0)
        premium_risk = declared_R if declared_R > 0 else round(entry_premium * contracts * 100, 2)
        pnl_pct      = round((exit_premium - entry_premium) / entry_premium * 100, 2) \
                       if entry_premium else 0.0
        pnl_usd      = round((exit_premium - entry_premium) * contracts * 100, 2)
        outcome_cls  = classify_outcome(pnl_pct, rr_predicted)
        rr_realised  = round(pnl_usd / premium_risk, 3) if premium_risk else (
            round(pnl_pct / 100 / rr_predicted, 3) if rr_predicted and rr_predicted > 0 else None
        )

        if trade_id > 0:
            log_exit(
                db_path       = _JOURNAL_DB,
                trade_id      = trade_id,
                exit_premium  = exit_premium,
                exit_reason   = exit_reason,
                exit_date     = __import__("datetime").date.today().isoformat(),
                wall_breached = 0,
                outcome_class = outcome_cls,
                notes         = notes,
            )
            _carry_lab_closed_metadata(trade_id, lab_snapshot)

        return jsonify({
            "ok":            True,
            "ticker":        ticker,
            "trade_id":      trade_id,
            "entry_premium": entry_premium,
            "exit_premium":  exit_premium,
            "exit_reason":   exit_reason,
            "pnl_pct":       pnl_pct,
            "pnl_usd":       pnl_usd,
            "rr_realised":   rr_realised,
            "outcome_class": outcome_cls,
            "message":       f"{ticker} exit logged â€” {outcome_cls} ({pnl_pct:+.1f}%)",
        })

    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/capture_outcomes", methods=["POST"])
def api_capture_outcomes():
    """
    Run outcome capture in monitor-only mode.
    Exits are always manual: this endpoint can flag possible exit conditions,
    but only /api/log_exit closes a journal row.

    Body (JSON, all optional):
      dry_run  â€” accepted for compatibility; forced true

    What it does:
      1. Reads all open positions from trade journal
      2. Fetches current marks from Tastytrade / Polygon
      3. Detects possible exits: expiry, time stop, stop loss, wall breach
      4. Returns the monitor summary without writing an exit

    Use the Intelligence Lab exit ticket to manually close trades.
    """
    try:
        import sys as _sys
        if str(BASE_DIR) not in _sys.path:
            _sys.path.insert(0, str(BASE_DIR))
        from outcome_capture import run_monitor

        body    = request.get_json(force=True) if request.data else {}
        dry_run = True

        if not _JOURNAL_DB.exists():
            return jsonify({
                "ok":      True,
                "exits_detected": 0,
                "message": "No trade journal found â€” no positions to capture",
            })

        result = run_monitor(db_path=_JOURNAL_DB, dry_run=dry_run)

        return jsonify({
            "ok":             result.get("success", False),
            "dry_run":        dry_run,
            "manual_exit_only": True,
            "open_scanned":   result.get("open", 0),
            "exits_detected": result.get("exits_detected", 0),
            "still_open":     result.get("still_open", 0),
            "manual_needed":  result.get("manual_needed", 0),
            "message": (
                f"[MONITOR ONLY] {result.get('exits_detected', 0)} exit condition(s) detected "
                f"from {result.get('open', 0)} open position(s). "
                f"{result.get('manual_needed', 0)} need manual review. "
                "No journal row is closed until the exit ticket is logged manually."
            ),
        })

    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/outcomes")
def api_outcomes():
    """
    Closed trade performance summary â€” predicted edge vs realised outcomes.
    This is the feedback loop view: are the pipeline's predictions accurate?

    Returns:
      - win rate (actual vs actuarial predicted)
      - avg R:R predicted vs realised
      - outcome breakdown: TRUE_WINNER / PROCESS_WIN / OUTCOME_LOSS / TRUE_LOSER
      - recent closed trades (last 20)
      - accuracy score: how close predicted R:R is to realised R:R
    """
    try:
        import sys as _sys
        if str(BASE_DIR) not in _sys.path:
            _sys.path.insert(0, str(BASE_DIR))
        from outcome_capture import build_pattern_validation_report
        from avshunter_trade_journal import get_db

        if not _JOURNAL_DB.exists():
            return jsonify({
                "ok":      True,
                "summary": [],
                "recent_trades": [],
                "message": "No journal found â€” start logging trades via /api/enter_trade",
            })

        # Pattern validation summary
        summary = build_pattern_validation_report(_JOURNAL_DB)

        # Recent closed trades for display
        recent = []
        try:
            conn = get_db(_JOURNAL_DB)
            _ensure_lab_journal_columns(conn)
            rows = conn.execute("""
                SELECT ticker, options_direction, exit_reason, rr_predicted,
                       rr_realised, pnl_usd, pnl_pct_premium, hold_days,
                       outcome_class, exit_date, time_horizon, hold_period,
                       horizon_hold_alignment, execution_category,
                       lab_action_category, eod_candidate_status,
                       morning_execution_permission, options_research_route
                FROM closed_trades
                ORDER BY exit_date DESC
                LIMIT 20
            """).fetchall()
            conn.close()
            cols = ["ticker", "direction", "exit_reason", "rr_predicted",
                    "rr_realised", "pnl_usd", "pnl_pct", "hold_days",
                    "outcome_class", "exit_date", "time_horizon", "hold_period",
                    "horizon_hold_alignment", "execution_category",
                    "lab_action_category", "eod_candidate_status",
                    "morning_execution_permission", "options_research_route"]
            recent = [dict(zip(cols, r)) for r in rows]
        except Exception:
            pass

        # Calibration score â€” how well predicted R:R matches realised
        calibration = None
        if summary:
            s = summary[0]
            pred = s.get("avg_rr_predicted", 0)
            real = s.get("avg_rr_realised", 0)
            if pred and pred > 0:
                calibration = round(1.0 - min(abs(pred - real) / pred, 1.0), 3)

        return jsonify({
            "ok":              True,
            "summary":         summary,
            "recent_trades":   recent,
            "learning_feedback": learning_feedback_from_closed_trades(_closed_trade_rows()),
            "calibration_score": calibration,
            "message": (
                f"{summary[0]['n_trades']} closed trades | "
                f"WR {summary[0]['win_rate']:.0%} | "
                f"RR pred:{summary[0]['avg_rr_predicted']:.2f} "
                f"real:{summary[0]['avg_rr_realised']:.2f}"
            ) if summary and summary[0].get("n_trades") else "No closed trades yet",
        })

    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# â”€â”€â”€ ENTRY POINT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.route("/api/learning_feedback")
def api_learning_feedback():
    try:
        rows = _closed_trade_rows()
        feedback = learning_feedback_from_closed_trades(rows)
        return jsonify({"ok": True, "feedback": feedback, "closed_trade_count": len(rows)})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


if __name__ == "__main__":
    print("=" * 65)
    print("  AVSHUNTER Â· INTELLIGENCE LAB v2.0")
    print("  EIL-primary architecture")
    print("=" * 65)
    print(f"  Pipeline dir : {RUNS_DIR}")
    print(f"  Dir exists   : {RUNS_DIR.exists()}")
    runs = _list_runs()
    if runs:
        print(f"  Latest run   : {runs[0]}")
        sb = _find_superbrain_dir(RUNS_DIR / runs[0])
        print(f"  SB folder    : {sb.name} ({'exists' if sb.exists() else 'MISSING'})")
    print("=" * 65)
    print("  Server       : http://localhost:5002")
    print("=" * 65)
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True, use_reloader=False)
