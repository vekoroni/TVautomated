r"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AVSHUNTER · INTELLIGENCE LAB · LOCAL SERVER                               ║
║  Port: 5002                                                                 ║
║  Reads directly from your pipeline output folder                           ║
║                                                                             ║
║  START:                                                                     ║
║    cd C:\Users\ACKVerissimo\intelligence-lab                               ║
║    .\venv\Scripts\Activate.ps1                                              ║
║    python intelligence_lab.py                                               ║
║                                                                             ║
║  OPEN:  http://localhost:5002                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import os, csv, json, glob, sys
from pathlib import Path
from datetime import datetime

app = Flask(__name__, static_folder="static")
CORS(app)

# ─── CONFIG ────────────────────────────────────────────────────────────────────
# This app lives at:
#   C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\intelligence-lab\
# So the pipeline root is one level up from this script.
BASE_DIR = Path(__file__).resolve().parent.parent   # → AVSHUNTER-Intelligence\
RUNS_DIR = BASE_DIR / "data" / "output" / "runs"

# ─── HELPERS ───────────────────────────────────────────────────────────────────


# ─── Run cache — invalidated by /api/reload_morning ───────────────────────────
_run_cache: dict = {}   # {run_id: payload_dict}

def _read_csv(path: Path) -> list:
    """Safe CSV reader — returns [] on any error."""
    if not path or not path.exists():
        return []
    try:
        with open(path, newline='', encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        print(f"  ⚠ CSV read error [{path.name}]: {e}")
        return []


def _read_json(path: Path) -> dict | list:
    """Safe JSON reader — returns {} on any error."""
    if not path or not path.exists():
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠ JSON read error [{path.name}]: {e}")
        return {}


def _glob_first(folder: Path, pattern: str) -> Path | None:
    """Return first match for a glob pattern inside folder, or None."""
    matches = sorted(folder.glob(pattern)) if folder.exists() else []
    return matches[-1] if matches else None  # latest if multiple


def _normalise_macro(m: dict) -> dict:
    """Normalise macro dict into the fields the UI expects. Never throws."""
    if not isinstance(m, dict):
        return {}
    # Accept either contract keys or legacy UI keys
    regime_state = m.get("regime_state") or m.get("RegimeState") or m.get("regime") or ""
    risk_switch  = m.get("risk_on_off_switch") or m.get("risk_switch") or m.get("RiskOnOffSwitch") or ""
    vol_mode     = m.get("vol_mode") or m.get("VolMode") or ""
    sector_tilt  = m.get("sector_tilt") or m.get("SectorTilt") or ""
    conviction   = m.get("macro_conviction") or m.get("MacroConviction") or m.get("conviction") or ""
    drift        = m.get("regime_drift_status") or m.get("regime_drift") or m.get("RegimeDriftStatus") or ""
    return {
        "regime_state": str(regime_state) if regime_state is not None else "",
        "risk_switch": str(risk_switch) if risk_switch is not None else "",
        "vol_mode": str(vol_mode) if vol_mode is not None else "",
        "sector_tilt": str(sector_tilt) if sector_tilt is not None else "",
        "conviction": conviction,
        "regime_drift": str(drift) if drift is not None else "",
    }


def _list_runs() -> list[str]:
    """Return sorted list of run IDs (newest first)."""
    if not RUNS_DIR.exists():
        return []
    runs = [d.name for d in RUNS_DIR.iterdir() if d.is_dir()]
    return sorted(runs, reverse=True)


def _load_run(run_id: str, force_reload: bool = False) -> dict:
    """Load all pipeline outputs for a given run_id into one payload dict.
    Results are cached in memory; call with force_reload=True (or hit
    /api/reload_morning) to drop the cache and re-read from disk.
    """
    if not force_reload and run_id in _run_cache:
        return _run_cache[run_id]
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return {"error": f"Run folder not found: {run_id}"}

    result = {"run_id": run_id, "loaded_at": datetime.utcnow().isoformat()}

    # ── 1. SuperBrain enriched CSV (all signals)
    sb_path = _glob_first(run_dir / "superbrain", f"superbrain_enriched_{run_id}.csv")
    if not sb_path:
        sb_path = _glob_first(run_dir / "superbrain", "superbrain_enriched_*.csv")
    result["signals"] = _read_csv(sb_path)

    # ── 2. Options intelligence CSV
    opt_path = _glob_first(run_dir / "options", f"options_intelligence_{run_id}.csv")
    if not opt_path:
        opt_path = _glob_first(run_dir / "options", "options_intelligence_*.csv")
    opt_rows = _read_csv(opt_path)
    # Index by ticker for fast merge
    # NOTE: UI expects certain canonical option fields; upstream versions
    # may emit slightly different names. Normalise to avoid UI blanks.
    def _normalise_opt_row(r: dict) -> dict:
        if not isinstance(r, dict):
            return {}
        rr = dict(r)

        # ── Premium aliases (menu + execute card)
        premium = rr.get("premium_mid")
        if premium in (None, ""):
            premium = rr.get("contract_premium")
        if premium in (None, ""):
            premium = rr.get("premium")
        if premium not in (None, ""):
            rr.setdefault("premium_mid", premium)
            rr.setdefault("premium", premium)
            rr.setdefault("contract_premium", premium)

        # ── Trigger-day aliases (menu wants days_to_trigger)
        days = rr.get("days_to_trigger")
        if days in (None, ""):
            days = rr.get("trigger_days")
        if days in (None, ""):
            days = rr.get("days")
        if days not in (None, ""):
            rr.setdefault("days_to_trigger", days)
            rr.setdefault("trigger_days", days)

        # ── Contract fields
        if rr.get("contract_strike") in (None, "") and rr.get("strike") not in (None, ""):
            rr["contract_strike"] = rr.get("strike")
        if rr.get("contract_expiry") in (None, "") and rr.get("expiry") not in (None, ""):
            rr["contract_expiry"] = rr.get("expiry")
        if rr.get("contract_dte") in (None, ""):
            rr["contract_dte"] = rr.get("dte") if rr.get("dte") not in (None, "") else rr.get("DTE")

        return rr

    opt_map = {r.get("ticker", "").upper(): _normalise_opt_row(r) for r in opt_rows}

    # ── 3. Discovery candidates CSV
    disc_path = _glob_first(run_dir / "discovery", f"discovery_candidates_ultimate_{run_id}.csv")
    if not disc_path:
        disc_path = _glob_first(run_dir / "discovery", "discovery_candidates_*.csv")
    result["discovery"] = _read_csv(disc_path)

    # ── 4. Vanguard signals CSV
    vg_dir = run_dir / "vanguard"
    # Prefer enriched version (from options layer)
    vg_path = _glob_first(run_dir / "options", f"vanguard_signals_enriched_{run_id}.csv")
    if not vg_path:
        vg_path = _glob_first(vg_dir, "vanguard_signals.csv")
    vg_rows = _read_csv(vg_path)
    vg_map = {r.get("ticker", "").upper(): r for r in vg_rows}

    # ── 5. Core Intel dossiers JSON
    ci_path = _glob_first(run_dir / "core_intel", f"core_intel_dossiers_{run_id}.json")
    if not ci_path:
        ci_path = _glob_first(run_dir / "core_intel", "core_intel_dossiers_*.json")
    core_intel = _read_json(ci_path)
    result["macro"] = core_intel.get("macro", {}) if isinstance(core_intel, dict) else {}
    dossier_list = core_intel.get("dossiers", []) if isinstance(core_intel, dict) else []
    dossier_map = {d.get("ticker", "").upper(): d for d in dossier_list}

    # ── 6. SuperBrain summary JSON
    sum_path = _glob_first(run_dir / "superbrain", f"superbrain_summary_{run_id}.json")
    if not sum_path:
        sum_path = _glob_first(run_dir / "superbrain", "superbrain_summary_*.json")
    result["summary"] = _read_json(sum_path)

    # ── 7. Wall Break Scorer CSV
    wbs_path = _glob_first(run_dir / "superbrain", f"wall_break_scores_{run_id}.csv")
    if not wbs_path:
        wbs_path = _glob_first(run_dir / "superbrain", "wall_break_scores_*.csv")
    wbs_rows = _read_csv(wbs_path)
    wbs_map  = {r.get("ticker", "").upper(): r for r in wbs_rows}
    result["wall_break_scores"] = wbs_rows

    wbs_sum_path = _glob_first(run_dir / "superbrain", f"wall_break_summary_{run_id}.json")
    if not wbs_sum_path:
        wbs_sum_path = _glob_first(run_dir / "superbrain", "wall_break_summary_*.json")
    result["wall_break_summary"] = _read_json(wbs_sum_path)

    # ── 8. EIL enriched CSV
    eil_path = _glob_first(run_dir / "superbrain", f"eil_enriched_{run_id}.csv")
    if not eil_path:
        eil_path = _glob_first(run_dir / "superbrain", "eil_enriched_*.csv")
    eil_rows = _read_csv(eil_path)
    eil_map  = {r.get("ticker", "").upper(): r for r in eil_rows}
    result["eil_signals"] = eil_rows
    # ── 9. Morning Validation enriched CSV (live prices + drift + contract quotes)
    mv_path = _glob_first(run_dir / "superbrain", f"morning_validation_{run_id}.csv")
    mv_rows = _read_csv(mv_path) if mv_path else []
    mv_map  = {r.get("ticker", "").upper(): r for r in mv_rows}
    result["mv_signals"] = mv_rows

    # ── 10. Q-OMEGA Layer 3 — GARCH forward variance forecasts
    garch_path = _glob_first(run_dir / "qomega", f"garch_forecasts_{run_id}.csv")
    if not garch_path:
        garch_path = _glob_first(run_dir / "qomega", "garch_forecasts_*.csv")
    garch_rows = _read_csv(garch_path) if garch_path else []
    garch_map  = {r.get("ticker", "").upper(): r for r in garch_rows}
    result["garch_forecasts"] = garch_rows

    # GARCH summary stats for stat cards
    if garch_rows:
        tailwinds = [float(r.get("l3_iv_tailwind_score", 0) or 0) for r in garch_rows]
        result["garch_stats"] = {
            "count":          len(garch_rows),
            "cheap_vol":      sum(1 for t in tailwinds if t < -0.03),
            "fair_vol":       sum(1 for t in tailwinds if -0.03 <= t <= 0.05),
            "expensive_vol":  sum(1 for t in tailwinds if t > 0.05),
            "jump_risk":      sum(1 for r in garch_rows if str(r.get("l3_jump_risk_flag","")).lower() == "true"),
            "garch_count":    sum(1 for r in garch_rows if r.get("l3_method") == "GARCH"),
            "ewma_count":     sum(1 for r in garch_rows if r.get("l3_method") == "EWMA_FALLBACK"),
        }
    else:
        result["garch_stats"] = {}


    # ── 9. Run health / handshake QA (fail-closed for required artefacts)
    expected_required = [
        ("superbrain_enriched", sb_path),
        ("superbrain_summary", sum_path),
        ("discovery_candidates", disc_path),
    ]
    # Vanguard is required for the pipeline, but allow lab to render even if absent.
    expected_optional = [
        ("options_intelligence", opt_path),
        ("vanguard_signals", vg_path),
        ("core_intel_dossiers", ci_path),
        ("wall_break_scores", wbs_path),
        ("eil_enriched", eil_path),
        ("morning_validation", mv_path if mv_rows else None),
        ("garch_forecasts", garch_path if garch_rows else None),
    ]
    missing_required = [name for name, p in expected_required if not p or not Path(p).exists()]
    missing_optional = [name for name, p in expected_optional if not p or not Path(p).exists()]
    result["run_health"] = {
        "ok": len(missing_required) == 0,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
    }

    # Normalise macro for UI
    result["macro"] = _normalise_macro(result.get("macro", {}))


    # ── Merge: annotate each signal with options + vanguard + dossier + WBS + EIL fields
    for sig in result["signals"]:
        t = sig.get("ticker", "").upper()
        opt  = opt_map.get(t, {})
        vg   = vg_map.get(t, {})
        doss = dossier_map.get(t, {})
        wbs  = wbs_map.get(t, {})
        eil  = eil_map.get(t, {})
        mv   = mv_map.get(t, {})
        # Prefix opt__ fields from options CSV (avoid collision)
        for k, v in opt.items():
            if k not in sig:
                sig[f"opt__{k}"] = v
        # Prefix vg__ fields from vanguard CSV
        for k, v in vg.items():
            if k not in sig and not k.startswith("opt__"):
                sig[f"vg__{k}"] = v
        # Inject dossier fields
        for k, v in doss.items():
            if k not in sig and not k.startswith("opt__") and not k.startswith("vg__"):
                sig[f"doss__{k}"] = v
        # Prefix wbs__ fields from wall break scorer
        for k, v in wbs.items():
            if k not in sig:
                sig[f"wbs__{k}"] = v
        # Prefix eil__ fields from execution intelligence layer
        # CSV columns are already named eil_verdict, eil_composite_score etc.
        # Strip the leading eil_ so final key is eil__verdict not eil__eil_verdict.
        for k, v in eil.items():
            if k == "ticker":
                continue
            clean_key = k[4:] if k.startswith("eil_") else k
            field_key = f"eil__{clean_key}"
            if field_key not in sig:
                sig[field_key] = v
        # Prefix mv__ fields from morning validation (live prices + drift + quotes)
        # CSV columns are named mv_verdict, mv_drift_pct etc. Strip the mv_ prefix
        # so the final field is mv__verdict not mv__mv_verdict.
        mv = mv_map.get(t, {})
        for k, v in mv.items():
            if k == "ticker":
                continue
            clean_key = k[3:] if k.startswith("mv_") else k
            field_key = f"mv__{clean_key}"
            if field_key not in sig:
                sig[field_key] = v

        # Prefix garch__ fields from Q-OMEGA Layer 3 GARCH forecasts
        # CSV columns are prefixed l3_ — keep that prefix so field is garch__l3_forward_realised_vol
        garch = garch_map.get(t, {})
        for k, v in garch.items():
            if k == "ticker":
                continue
            field_key = f"garch__{k}"
            if field_key not in sig:
                sig[field_key] = v

        # ── DISPLAY FIXES ─────────────────────────────────────────────────────
        # The EIL merge above stores everything under eil__ prefix. The frontend
        # reads bare s.ev / s.current_price from the superbrain base row, which
        # carries stale v1-fallback EV (−1.2 range) and zero prices in EOD mode.
        # Overwrite the bare fields here so the frontend gets correct values
        # without needing to know about the eil__ prefix scheme.
        _eil = eil_map.get(t, {})

        # FIX-EV: ev2_ev_conf_adj is the EVEngineV2 authoritative EV field.
        # Falls back to fd_ev_used (FDE output) then eil ev_final.
        _correct_ev = (_eil.get("ev2_ev_conf_adj") or
                       _eil.get("fd_ev_used")       or
                       _eil.get("ev_final"))
        if _correct_ev not in (None, "", "nan"):
            try:
                _ev_val = float(_correct_ev)
                sig["ev"]       = round(_ev_val, 6)
                sig["ev_final"] = round(_ev_val, 6)
                sig["ev_net"]   = round(_ev_val, 6)
                _ev_s = _eil.get("ev2_ev_structural")
                if _ev_s not in (None, "", "nan"):
                    sig["ev_base"] = round(float(_ev_s), 6)
            except (TypeError, ValueError):
                pass

        # FIX-PRICE: current_price = 0 in EOD mode — alias from signal_price.
        _sp = sig.get("signal_price") or _eil.get("signal_price")
        if _sp and str(_sp) not in ("0", "0.0", "", "nan", "None"):
            try:
                _sp_f = float(_sp)
                if _sp_f > 0:
                    sig["current_price"]    = _sp_f
                    sig["spot_price"]       = _sp_f
                    sig["underlying_price"] = _sp_f
            except (TypeError, ValueError):
                pass

        # FIX-PREMIUM: flag BSM synthetic premiums so the frontend can label them.
        _prem  = sig.get("premium") or _eil.get("premium")
        _synth = str(sig.get("contract_mark_synthetic", "")).lower()
        if _synth in ("true", "1", "yes") or str(_prem) in ("1.0", "1"):
            sig["premium_label"]        = "BSM"
            sig["premium_is_synthetic"] = True
        else:
            sig.setdefault("premium_label",        "$")
            sig.setdefault("premium_is_synthetic", False)

        # FIX-WBS-SCORE: the WBS CSV field is named "wbs" not "wbs_score".
        # The server prefixes it as wbs__wbs. Alias to wbs__wbs_score so the
        # existing frontend fallback chain (wbs__wbs_score||wbs__score) resolves.
        if "wbs__wbs" in sig and "wbs__wbs_score" not in sig:
            sig["wbs__wbs_score"] = sig["wbs__wbs"]
        if "wbs__wbs_wall_price" in sig and "wbs__wall_price" not in sig:
            sig["wbs__wall_price"] = sig["wbs__wbs_wall_price"]
        if "wbs__wbs_wall_dist_pct" in sig and "wbs__distance_to_wall_pct" not in sig:
            sig["wbs__distance_to_wall_pct"] = sig["wbs__wbs_wall_dist_pct"]
    # ── PRIORITY RANKING (v2.3.0) ───────────────────────────────────────────────
    # Composite rank across 9 weighted dimensions so the UI can surface the
    # single most-actionable signal regardless of which filter tab is active.
    # Score is 0-100. Written into each signal dict as "priority_rank" and
    # "priority_score" so the frontend can sort/badge without extra computation.
    VERDICT_W  = {"EXECUTE":1.0, "EXECUTE_WITH_RISK":0.70, "ARMED":0.35}
    CAMPAIGN_W = {"CONVEXITY_INJECTION":1.0, "CORE_CAMPAIGN":0.75, "STAGED":0.45}
    EXECMODE_W = {"FULL_EXECUTE":1.0, "REDUCED_EXECUTE":0.75, "PROBE":0.50, "WAIT":0.20, "BLOCKED":0.0}
    RISK_W     = {"LOW":1.0, "MEDIUM":0.75, "HIGH":0.40, "EXTREME":0.10}
    DW_W       = {"DATA_WEAK":0.0}  # zero bonus for data-poor signals

    def _pf(sig, key, default=0.0):
        try:
            v = sig.get(key,"")
            if str(v).strip() in ("","None","nan","N/A"): return default
            return float(v)
        except: return default

    for sig in result["signals"]:
        fv   = str(sig.get("sb_final_verdict","")).upper()
        camp = str(sig.get("sb_campaign","")).upper()
        em   = str(sig.get("sb_execution_mode","")).upper()
        rl   = str(sig.get("sb_risk_label","MEDIUM")).upper()
        ev_s = str(sig.get("ev_status","")).upper()

        # Dimension weights (must sum to 1.0)
        w_verdict  = VERDICT_W.get(fv, 0.0)          * 0.22
        w_campaign = CAMPAIGN_W.get(camp, 0.0)        * 0.16
        w_execmode = EXECMODE_W.get(em, 0.20)         * 0.12
        w_risk     = RISK_W.get(rl, 0.50)             * 0.10
        w_conv     = min(_pf(sig,"sb_conv_score"),8)/8  * 0.14
        w_ev       = min(max((_pf(sig,"ev_final",_pf(sig,"ev"))+0.25)/0.50,0),1) * 0.10
        w_rr       = min(_pf(sig,"rr")/3.0,1.0)       * 0.08
        w_wbs      = min(_pf(sig,"wbs__wbs_score",_pf(sig,"wbs__wbs"))/100,1.0) * 0.05
        w_dq       = 0.0 if ev_s == "DATA_WEAK" else 0.03  # penalise data-weak

        raw_score  = (w_verdict+w_campaign+w_execmode+w_risk+w_conv+w_ev+w_rr+w_wbs+w_dq) * 100
        sig["priority_score"] = round(min(raw_score,100),1)

    # Rank within the full universe (1 = highest priority)
    for sig in result["signals"]:
        sig.setdefault("priority_score", 0.0)
    sorted_by_score = sorted(result["signals"], key=lambda x: float(x.get("priority_score",0)), reverse=True)
    for rank, sig in enumerate(sorted_by_score, 1):
        sig["priority_rank"] = rank

    signals = result["signals"]
    execute      = [s for s in signals if s.get("sb_final_verdict") == "EXECUTE"]
    execute_risk = [s for s in signals if s.get("sb_final_verdict") == "EXECUTE_WITH_RISK"]
    armed        = [s for s in signals if s.get("sb_final_verdict") in ("ARMED", "EXECUTE_WITH_RISK")]
    stand        = [s for s in signals if s.get("sb_final_verdict") == "STAND_DOWN"]
    core_sigs    = [s for s in signals if s.get("sb_campaign") == "CORE_CAMPAIGN"]
    staged_sigs  = [s for s in signals if s.get("sb_campaign") == "STAGED"]

    # WBS grade counts
    wbs_grades = {}
    for r in wbs_rows:
        g = r.get("wbs_grade", r.get("grade", ""))
        if g:
            wbs_grades[g] = wbs_grades.get(g, 0) + 1

    summary = result.get("summary", {})
    wbs_summary = result.get("wall_break_summary", {})

    # EIL verdict distribution (raw verdicts, not ADVISORY_ONLY)
    eil_verdicts = {}
    for r in eil_rows:
        v = r.get("eil_raw_verdict") or r.get("eil_verdict", "")
        if v and v != "ADVISORY_ONLY":
            eil_verdicts[v] = eil_verdicts.get(v, 0) + 1

    result["stats"] = {
        # Superbrain verdicts
        "execute_count"       : len(execute),
        "execute_risk_count"  : len(execute_risk),
        "armed_count"         : len(armed),
        "core_armed_count"    : len(core_sigs),
        "staged_armed_count"  : len(staged_sigs),
        "stand_down_count"    : len(stand),
        "total_scanned"       : len(signals),
        "discovery_count"     : len(result["discovery"]),
        "vanguard_count"      : len(vg_rows),
        "vetoes_fired"        : summary.get("vetoes_fired", 0),
        "verdicts_changed"    : summary.get("verdicts_changed", 0),
        "core_campaign_count" : len(core_sigs),
        "staged_campaign_count": len(staged_sigs),
        "top_execute"         : [s.get("ticker") for s in execute],
        "top_armed"           : summary.get("top_armed", [s.get("ticker") for s in armed[:8]]),
        # Wall Break Scorer
        "wbs_count"           : len(wbs_rows),
        "wbs_imminent"        : wbs_grades.get("IMMINENT", 0),
        "wbs_probable"        : wbs_grades.get("PROBABLE", 0),
        "wbs_possible"        : wbs_grades.get("POSSIBLE", 0),
        "wbs_unlikely"        : wbs_grades.get("UNLIKELY", 0),
        "wbs_avg_score"       : wbs_summary.get("wbs_avg", 0),
        "wbs_max_score"       : wbs_summary.get("wbs_max", 0),
        # EIL
        "eil_count"           : len(eil_rows),
        "eil_execute_now"     : eil_verdicts.get("EXECUTE_NOW", 0),
        "eil_execute_caution" : eil_verdicts.get("EXECUTE_WITH_CAUTION", 0),
        "eil_defer"           : eil_verdicts.get("EXECUTE_DEFER", 0),
        "eil_stand_down"      : eil_verdicts.get("STAND_DOWN_MICROSTRUCTURE", 0),
        "eil_advisory_mode"   : len(eil_rows) > 0 and all(
            r.get("eil_verdict") == "ADVISORY_ONLY" for r in eil_rows
        ),
        # Morning Validation
        "mv_count"            : len(mv_rows),
        "mv_valid_count"      : sum(1 for r in mv_rows if r.get("mv_verdict") in ("VALID", "TRIGGERED")),
        "mv_drifted_count"    : sum(1 for r in mv_rows if r.get("mv_verdict") == "DRIFTED"),
        "mv_invalidated_count": sum(1 for r in mv_rows if r.get("mv_verdict") in
                                    ("INVALIDATED", "SPREAD_WIDE", "DTE_STALE")),
        "mv_validated_at"     : mv_rows[0].get("mv_validated_at", "") if mv_rows else "",
        # Q-OMEGA Layer 3 GARCH
        **result.get("garch_stats", {}),
        # v2.3.0 priority ranking + data quality
        "top_priority"        : [s.get("ticker") for s in sorted(
            [x for x in signals if x.get("priority_rank",9999)<=10],
            key=lambda x: x.get("priority_rank",9999))],
        "data_weak_count"     : sum(1 for s in signals if str(s.get("ev_status","")).upper()=="DATA_WEAK"),
        "exec_mode_full"      : sum(1 for s in signals if s.get("sb_execution_mode")=="FULL_EXECUTE"),
        "exec_mode_reduced"   : sum(1 for s in signals if s.get("sb_execution_mode")=="REDUCED_EXECUTE"),
        "exec_mode_probe"     : sum(1 for s in signals if s.get("sb_execution_mode")=="PROBE"),
        "win_rate_bridge_count": sum(1 for s in signals if s.get("win_rate_source")=="DISCOVERY_BRIDGE"),
    }

    _run_cache[run_id] = result
    return result


# ─── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")



@app.route("/api/health")
def api_health():
    """Lightweight health check used by the UI loader."""
    runs = _list_runs()
    return jsonify({
        "status": "ok",
        "pipeline_dir": str(RUNS_DIR),
        "pipeline_dir_exists": RUNS_DIR.exists(),
        "run_count": len(runs),
        "latest_run": runs[0] if runs else None,
        "server_time": datetime.utcnow().isoformat()
    })


@app.route("/api/runs")
def api_runs():
    """List all available run IDs."""
    runs = _list_runs()
    return jsonify({
        "runs": runs,
        "latest": runs[0] if runs else None,
        "count": len(runs)
    })


@app.route("/api/run/<run_id>")
def api_run(run_id):
    """Full payload for a specific run."""
    return jsonify(_load_run(run_id))


@app.route("/api/run/latest")
def api_run_latest():
    """Shortcut — always returns the most recent run."""
    runs = _list_runs()
    if not runs:
        return jsonify({"error": "No runs found in " + str(RUNS_DIR)}), 404
    return jsonify(_load_run(runs[0]))


@app.route("/api/enter_trade", methods=["POST"])
def api_enter_trade():
    """
    Create a Trade Contract from an EXECUTE signal.
    POST body (JSON):
    {
        "ticker":             "KDP",
        "entry_price":        0.85,        # premium paid per share (option cost)
        "invalidation_price": 33.50,       # underlying stock stop level
        "run_id":             "20260228_163516"  # optional, defaults to latest
    }
    """
    try:
        # ── Ensure project root is on sys.path so vanguard imports work
        project_root = str(BASE_DIR)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from vanguard.trade_contract import create_contract, find_open_contract

        body = request.get_json(force=True)
        ticker            = str(body.get("ticker", "")).strip().upper()
        entry_price       = float(body.get("entry_price", 0))
        invalidation_price = float(body.get("invalidation_price", 0))
        run_id            = body.get("run_id") or _list_runs()[0]

        if not ticker:
            return jsonify({"ok": False, "error": "ticker required"}), 400
        if entry_price <= 0:
            return jsonify({"ok": False, "error": "entry_price must be > 0"}), 400
        if invalidation_price <= 0:
            return jsonify({"ok": False, "error": "invalidation_price must be > 0"}), 400

        # ── Load superbrain row for this ticker
        run_dir = RUNS_DIR / run_id
        sb_path = _glob_first(run_dir / "superbrain", f"superbrain_enriched_{run_id}.csv")
        if not sb_path:
            return jsonify({"ok": False, "error": f"superbrain CSV not found for run {run_id}"}), 404

        row = None
        with open(sb_path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("ticker", "").strip().upper() == ticker:
                    row = r
                    break

        if not row:
            return jsonify({"ok": False, "error": f"{ticker} not found in superbrain CSV"}), 404

        verdict = row.get("sb_final_verdict", "").strip().upper()
        if verdict != "EXECUTE":
            return jsonify({
                "ok": False,
                "error": f"{ticker} verdict is {verdict}, not EXECUTE — cannot enter trade"
            }), 400

        # ── Check for existing open contract
        existing = find_open_contract(ticker)
        if existing:
            return jsonify({
                "ok": False,
                "error": f"Open contract already exists for {ticker}: {existing.name}"
            }), 409

        # ── Map superbrain fields to contract fields
        def _f(key, default=0.0):
            try:
                v = row.get(key, "")
                if str(v).strip() in ("", "N/A", "nan", "None"):
                    return default
                return float(v)
            except Exception:
                return default

        direction   = row.get("direction", "PUT").strip().upper()
        instrument  = row.get("sb_instrument_now", "")
        horizon     = "20D"
        if "MID_DATED" in instrument.upper():
            horizon = "20D"   # 45-90 DTE maps to 20D actuarial horizon
        elif "STANDARD" in instrument.upper():
            horizon = "10D"
        elif "SHORT" in instrument.upper():
            horizon = "5D"

        # ── Load vanguard signals for state fields
        vg_path = _glob_first(run_dir / "vanguard", "vanguard_signals.csv")
        vg_row  = {}
        if vg_path:
            with open(vg_path, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r.get("ticker", "").strip().upper() == ticker:
                        vg_row = r
                        break

        state_hash        = vg_row.get("state_hash", "unknown")
        edge_quality      = vg_row.get("confidence_level", "MODERATE").strip().upper() or "MODERATE"
        vol_regime        = vg_row.get("layer1__vol_regime", "NORMAL").strip().upper() or "NORMAL"
        trend_direction   = vg_row.get("layer1__trend_direction", "BEARISH").strip().upper() or "BEARISH"
        trend_maturity    = vg_row.get("layer1__trend_maturity", "EARLY").strip().upper() or "EARLY"
        structure_quality = vg_row.get("layer1__structure_quality", "NEUTRAL").strip().upper() or "NEUTRAL"
        macro_regime      = row.get("regime", "TRANSITIONAL").strip().upper() or "TRANSITIONAL"
        adx               = _f("layer1__adx", 20.0)
        atr_pct           = _f("layer1__atr_percentile", 50.0)
        ev                = _f("ev", 0.0)
        win_rate          = _f("win_rate_20d", 0.5)

        # ── Create the contract
        contract = create_contract(
            ticker                   = ticker,
            entry_price              = entry_price,
            direction                = direction,
            horizon_type             = horizon,
            edge_quality             = edge_quality,
            entry_ev                 = ev,
            entry_win_rate           = win_rate,
            entry_state_hash         = state_hash,
            entry_vol_regime         = vol_regime,
            entry_trend_direction    = trend_direction,
            entry_trend_maturity     = trend_maturity,
            entry_structure_quality  = structure_quality,
            entry_macro_regime       = macro_regime,
            entry_catalyst_proximity = "UNKNOWN",
            entry_adx                = adx,
            entry_atr_percentile     = atr_pct,
            invalidation_price       = invalidation_price,
            max_expected_mae         = entry_price * 0.5,
        )

        return jsonify({
            "ok":      True,
            "ticker":  ticker,
            "message": f"Trade contract created for {ticker}",
            "contract_summary": {
                "ticker":             ticker,
                "direction":          direction,
                "horizon":            horizon,
                "entry_price":        entry_price,
                "invalidation_price": invalidation_price,
                "ev":                 ev,
                "win_rate":           win_rate,
                "campaign":           row.get("sb_campaign", ""),
                "conv_score":         row.get("sb_conv_score", ""),
                "instrument":         instrument,
            }
        })

    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500



@app.route("/api/reload_morning", methods=["POST"])
def api_reload_morning():
    """
    Called by morning_validation.py after writing its enriched CSV.
    Drops the cached run payload so the next /api/run/<run_id> request
    re-reads from disk and picks up the new morning_validation CSV.
    """
    body = request.get_json(silent=True) or {}
    run_id = body.get("run_id", "").strip()

    if run_id:
        # Invalidate specific run
        dropped = _run_cache.pop(run_id, None)
        msg = f"Cache cleared for run {run_id}" if dropped else f"Run {run_id} was not cached"
    else:
        # Invalidate all (fallback)
        count = len(_run_cache)
        _run_cache.clear()
        msg = f"All {count} cached runs cleared"

    print(f"  🔄 /api/reload_morning — {msg}")
    return jsonify({"ok": True, "message": msg})

@app.route("/api/open_contracts")
def api_open_contracts():
    """Return all open trade contracts."""
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
                    "campaign":           c.get("sb_campaign", ""),
                })
            except Exception:
                pass
        return jsonify({"ok": True, "contracts": contracts, "count": len(contracts)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



# ─── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  AVSHUNTER · INTELLIGENCE LAB")
    print("=" * 65)
    print(f"  Pipeline dir : {RUNS_DIR}")
    print(f"  Dir exists   : {RUNS_DIR.exists()}")
    runs = _list_runs()
    if runs:
        print(f"  Latest run   : {runs[0]}")
        print(f"  Total runs   : {len(runs)}")
    else:
        print("  ⚠ No runs found yet — run your pipeline first")
    print("=" * 65)
    print("  Server       : http://localhost:5002")
    print("  API health   : http://localhost:5002/api/health")
    print("=" * 65)
    print()
    app.run(host="0.0.0.0", port=5002, debug=False)
