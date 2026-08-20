r"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AVSHUNTER · INTELLIGENCE LAB v2.0                                         ║
║  Port: 5002                                                                 ║
║                                                                             ║
║  ARCHITECTURE CHANGE v2.0:                                                 ║
║  OLD: superbrain_enriched is the primary signal source (138 cols)          ║
║  NEW: eil_enriched is the primary signal source (232 cols)                 ║
║       superbrain_enriched retained for sb_final_verdict only               ║
║       v5 CSV provides the 32-candidate execution layer                     ║
║       All existing merge logic preserved: options, wbs, garch, mv, ct      ║
║                                                                             ║
║  DATA CONTRACT (what each file contributes):                                ║
║    eil_enriched          → signals base, 1312 rows, 232 cols               ║
║                            verdicts, EIL scores, EV, triggers, structure   ║
║    execution_v3_5        → campaign_verdict, execution_verdict (delta only) ║
║    options_intelligence  → opt__ prefix: contract, IV, greeks, walls       ║
║    vanguard_signals_e    → vg__ prefix: actuarial, win rate, tier, phase   ║
║    wall_break_scores     → wbs__ prefix: 9 BUY_NOW tickers, entry/stop     ║
║    eil_enriched (garch)  → garch__ prefix: vol forecasts, jump risk        ║
║    garch_forecasts       → garch__ prefix: forward vol, tailwind, method   ║
║    morning_validation    → mv__ prefix: live price, drift, TCE             ║
║    superbrain_enriched   → sb_final_verdict only                           ║
║    AVSHUNTER_SIGNALS_V5  → v5__ prefix: thesis_decision, size, conflicts   ║
║                                                                             ║
║  PRIORITY RANKING (new pipeline fields):                                   ║
║    options_verdict  (22%) campaign_verdict (16%) execution_verdict (12%)   ║
║    eil_composite    (14%) ev2_ev_conf_adj  (10%) rr_options        (8%)    ║
║    options_score    (8%)  wbs              (5%)  garch_tailwind    (5%)    ║
║                                                                             ║
║  START:                                                                     ║
║    cd C:\Users\ACKVerissimo\intelligence-lab                                ║
║    .\venv\Scripts\Activate.ps1                                              ║
║    python intelligence_lab.py                                               ║
║  OPEN:  http://localhost:5002                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from flask import Flask, jsonify, send_from_directory, request, Response
from flask_cors import CORS
import os, csv, json, glob, sys, io
from pathlib import Path
from datetime import datetime

app = Flask(__name__, static_folder="static")
CORS(app)

# ─── CONFIG ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent   # → AVSHUNTER-Intelligence\
RUNS_DIR = BASE_DIR / "data" / "output" / "runs"

_run_cache: dict = {}

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def _read_csv(path):
    if not path or not Path(path).exists():
        return []
    try:
        with open(path, newline='', encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        print(f"  ⚠ CSV read error [{Path(path).name}]: {e}")
        return []

def _read_json(path):
    if not path or not Path(path).exists():
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠ JSON read error [{Path(path).name}]: {e}")
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

def _list_runs():
    if not RUNS_DIR.exists():
        return []
    runs = [d.name for d in RUNS_DIR.iterdir() if d.is_dir()]
    return sorted(runs, reverse=True)

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

# ─── PRIORITY SCORING (pipeline-native fields) ──────────────────────────────
def _compute_priority_score(sig):
    """
    Priority score built entirely from new pipeline fields.
    Replaces the superbrain-era score that needed sb_final_verdict,
    sb_campaign, sb_execution_mode, sb_conv_score, sb_risk_label.

    Weights (sum to 1.0):
      options_verdict    0.22  — options layer verdict
      campaign_verdict   0.16  — campaign readiness
      execution_verdict  0.12  — execution gate
      eil_composite      0.14  — EIL execution quality
      ev2_ev_conf_adj    0.10  — EV engine (post-fix: 0.003–0.625)
      rr_options         0.08  — risk/reward
      options_score      0.08  — options contract quality
      wbs                0.05  — wall break score (icing)
      garch_tailwind     0.05  — vol state from GARCH
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

    # EV engine — range is 0.002–0.025 pre-fix, 0.003–0.625 post-fix
    w_ev2 = min(max((ev_adj + 0.25) / 0.50, 0), 1) * 0.10

    # RR
    w_rr = (min(rr / 3.0, 1.0) if rr > 0 else 0) * 0.08

    # Options score
    w_opt = min(opt_s / 100, 1.0) * 0.08

    # WBS — icing, not gate
    wbs_mult = {"PROBABLE": 1.0, "POSSIBLE": 0.6, "UNLIKELY": 0.2}.get(wbs_g, 0)
    w_wbs = (wbs_s / 100) * wbs_mult * 0.05

    # GARCH vol state — cheap vol = buying edge
    w_gar = (1.0 if tail < -0.03 else 0.5 if abs(tail) <= 0.03 else 0.1) * 0.05

    raw = (w_ov + w_cv + w_ev + w_eil + w_ev2 + w_rr + w_opt + w_wbs + w_gar) * 100
    return round(min(raw, 100), 1)

# ─── CONVEXITY CHECKS (pipeline-native) ─────────────────────────────────────
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

# ─── STAGE LADDER (execution readiness) ─────────────────────────────────────
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
        "All 4 layers aligned — ENTER NOW" if s4 else
        f"EIL cleared · waiting on execution gate" if s3 else
        f"Campaign ready · EIL checking microstructure" if s2 else
        f"Signal triggered · campaign building" if s1 else
        "Signal not yet triggered"
    )

    return {
        "current_stage":   current,
        "enter_now_stages": enter_now,
        "alert_stages":    alert,
        "ladder_summary":  summary,
        "stages_passed":   current,
    }

# ─── MAIN LOAD ──────────────────────────────────────────────────────────────
def _load_run(run_id, force_reload=False):
    if not force_reload and run_id in _run_cache:
        return _run_cache[run_id]

    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return {"error": f"Run folder not found: {run_id}"}

    result = {"run_id": run_id, "loaded_at": datetime.utcnow().isoformat()}
    sb_dir = _find_superbrain_dir(run_dir)

    # ── 1. PRIMARY SIGNAL SOURCE: eil_enriched (232 cols, 1312 rows) ────────
    # This replaces superbrain_enriched as the base signal table.
    eil_path = _glob_first(sb_dir, f"eil_enriched_{run_id}.csv")
    if not eil_path:
        eil_path = _glob_first(sb_dir, "eil_enriched_*.csv")
    eil_rows = _read_csv(eil_path)
    result["signals"] = eil_rows
    eil_map = {r.get("ticker","").upper(): r for r in eil_rows}
    print(f"  ✓ EIL (primary): {len(eil_rows)} signals")

    # ── 2. SUPERBRAIN: sb_final_verdict only ────────────────────────────────
    sb_path = _glob_first(sb_dir, f"superbrain_enriched_{run_id}.csv")
    if not sb_path:
        sb_path = _glob_first(sb_dir, "superbrain_enriched_*.csv")
    sb_rows = _read_csv(sb_path)
    sb_map = {r.get("ticker","").upper(): r for r in sb_rows}
    print(f"  ✓ SuperBrain (verdict only): {len(sb_rows)} rows")

    # ── 3. EXECUTION VERDICTS: campaign_verdict, execution_verdict ───────────
    exe_path = _glob_first(sb_dir, f"execution_v3_5_{run_id}.csv")
    if not exe_path:
        exe_path = _glob_first(sb_dir, "execution_v3_5_*.csv")
    exe_rows = _read_csv(exe_path)
    exe_map = {r.get("ticker","").upper(): r for r in exe_rows}
    print(f"  ✓ Execution verdicts: {len(exe_rows)} rows")

    # ── 4. OPTIONS INTELLIGENCE (opt__ prefix) ───────────────────────────────
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
    print(f"  ✓ Options intel: {len(opt_rows)} rows")

    # ── 5. VANGUARD (vg__ prefix) ────────────────────────────────────────────
    vg_path = _glob_first(run_dir / "options", f"vanguard_signals_enriched_{run_id}.csv")
    if not vg_path:
        vg_path = _glob_first(run_dir / "vanguard", "vanguard_signals_enriched_*.csv")
    if not vg_path:
        vg_path = _glob_first(run_dir / "vanguard", "vanguard_signals.csv")
    vg_rows = _read_csv(vg_path)
    vg_map = {r.get("ticker","").upper(): r for r in vg_rows}
    print(f"  ✓ Vanguard: {len(vg_rows)} rows")

    # ── 6. WBS (wbs__ prefix) ────────────────────────────────────────────────
    wbs_path = _glob_first(sb_dir, f"wall_break_scores_{run_id}.csv")
    if not wbs_path:
        wbs_path = _glob_first(sb_dir, "wall_break_scores_*.csv")
    wbs_rows = _read_csv(wbs_path)
    wbs_map = {r.get("ticker","").upper(): r for r in wbs_rows}
    result["wall_break_scores"] = wbs_rows
    print(f"  ✓ WBS: {len(wbs_rows)} rows")

    wbs_sum_path = _glob_first(sb_dir, "wall_break_summary_*.json")
    result["wall_break_summary"] = _read_json(wbs_sum_path)

    # ── 7. GARCH (garch__ prefix) ────────────────────────────────────────────
    garch_path = _glob_first(run_dir / "qomega", f"garch_forecasts_{run_id}.csv")
    if not garch_path:
        garch_path = _glob_first(run_dir / "qomega", "garch_forecasts_*.csv")
    if not garch_path:
        garch_path = _glob_first(sb_dir, "garch_forecasts_*.csv")
    garch_rows = _read_csv(garch_path)
    garch_map = {r.get("ticker","").upper(): r for r in garch_rows}
    result["garch_forecasts"] = garch_rows
    print(f"  ✓ GARCH: {len(garch_rows)} rows")

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

    # ── 8. MACRO ─────────────────────────────────────────────────────────────
    ci_path = _glob_first(run_dir / "core_intel", f"core_intel_dossiers_{run_id}.json")
    if not ci_path:
        ci_path = _glob_first(run_dir / "core_intel", "core_intel_dossiers_*.json")
    core_intel = _read_json(ci_path)
    raw_macro = core_intel.get("macro", {}) if isinstance(core_intel, dict) else {}
    dossier_list = core_intel.get("dossiers", []) if isinstance(core_intel, dict) else []
    dossier_map = {d.get("ticker","").upper(): d for d in dossier_list}
    result["macro"] = _normalise_macro(raw_macro)

    # ── 9. MORNING VALIDATION (mv__ prefix) ──────────────────────────────────
    mv_dir = run_dir / "morning_validation"
    mv_path = _glob_first(mv_dir, f"morning_validated_trades_{run_id}.csv")
    if not mv_path:
        mv_path = _glob_first(mv_dir, "morning_validated_trades_*.csv")
    if not mv_path:
        mv_path = _glob_first(sb_dir, "morning_validation_*.csv")
    mv_rows = _read_csv(mv_path) if mv_path else []
    mv_map = {r.get("ticker","").upper(): r for r in mv_rows}
    result["mv_signals"] = mv_rows
    print(f"  ✓ Morning validation: {len(mv_rows)} rows")

    # ── 10. DISCOVERY ─────────────────────────────────────────────────────────
    disc_path = _glob_first(run_dir / "discovery", "discovery_candidates_*.csv")
    result["discovery"] = _read_csv(disc_path)

    # ── 11. V5 SIGNALS (v5__ prefix) — 32 candidate execution layer ──────────
    # Load from superbrain dir or runs dir. Placed there manually or by pipeline.
    v5_path = _glob_latest(sb_dir, "AVSHUNTER_SIGNALS_V5_*.csv")
    if not v5_path:
        v5_path = _glob_latest(run_dir, "AVSHUNTER_SIGNALS_V5_*.csv")
    if not v5_path:
        v5_path = _glob_latest(RUNS_DIR.parent, "AVSHUNTER_SIGNALS_V5_*.csv")
    v5_rows = _read_csv(v5_path) if v5_path else []
    v5_map = {r.get("ticker","").upper(): r for r in v5_rows}
    result["v5_signals"] = v5_rows
    print(f"  ✓ V5 signals: {len(v5_rows)} rows ({v5_path.name if v5_path else 'not found'})")

    # ── SUMMARY JSON ──────────────────────────────────────────────────────────
    sum_path = _glob_first(sb_dir, "superbrain_summary_*.json")
    result["summary"] = _read_json(sum_path)

    # ── RUN HEALTH ────────────────────────────────────────────────────────────
    required = [("eil_enriched", eil_path)]
    optional = [
        ("superbrain_enriched", sb_path),
        ("execution_v3_5",      exe_path),
        ("options_intelligence", opt_path),
        ("vanguard_signals",    vg_path),
        ("wall_break_scores",   wbs_path),
        ("garch_forecasts",     garch_path),
        ("morning_validation",  mv_path if mv_rows else None),
        ("v5_signals",          v5_path),
    ]
    missing_req = [n for n,p in required if not p or not Path(p).exists()]
    missing_opt = [n for n,p in optional if not p or not Path(p).exists()]
    result["run_health"] = {
        "ok": len(missing_req) == 0,
        "missing_required": missing_req,
        "missing_optional": missing_opt,
    }

    # ── MERGE: annotate each signal ───────────────────────────────────────────
    for sig in result["signals"]:
        t = sig.get("ticker","").upper()

        # sb_final_verdict (the only thing superbrain still owns)
        sb = sb_map.get(t, {})
        sig.setdefault("sb_final_verdict", sb.get("sb_final_verdict",""))

        # Execution verdicts from execution_v3_5
        exe = exe_map.get(t, {})
        sig.setdefault("campaign_verdict",  exe.get("campaign_verdict",""))
        sig.setdefault("execution_verdict", exe.get("execution_verdict",""))

        # ── FIELD ALIASES: map new pipeline fields to lab's old names ─────────
        # The UI reads these bare names — set them from eil fields
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
        sig.setdefault("sb_verdict_reason",sig.get("reason",""))

        # Sizing from v5 if available, else derive from eil_composite
        v5 = v5_map.get(t, {})
        if v5.get("size_mult"):
            sig.setdefault("sb_position_size_pct", float(v5.get("size_mult",0) or 0) * 100)
        else:
            eil_c = float(sig.get("eil_composite_score",50) or 50)
            sig.setdefault("sb_position_size_pct",
                           100 if eil_c >= 85 else 75 if eil_c >= 70 else 55 if eil_c >= 55 else 35)

        # Contract validity → veto display
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
            "live_price":         ("mv__live_price",         "mv_live_price"),
        }.items():
            if not sig.get(bare_key):
                val = sig.get(pfx_key) or mv.get(raw_key) or mv.get(bare_key)
                if val not in (None,"","nan"):
                    sig[bare_key] = val

        # EV display fix
        _ev = (sig.get("ev2_ev_conf_adj") or sig.get("fd_ev_used") or
               sig.get("eil_ev_net"))
        if _ev not in (None,"","nan"):
            try:
                sig["ev"] = round(float(_ev), 6)
                sig["ev_final"] = sig["ev"]
                sig["ev_net"]   = sig["ev"]
            except: pass

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

    # ── PRIORITY RANKING ──────────────────────────────────────────────────────
    for sig in result["signals"]:
        sig["priority_score"] = _compute_priority_score(sig)
    sorted_sigs = sorted(result["signals"],
                         key=lambda x: float(x.get("priority_score",0)), reverse=True)
    for rank, sig in enumerate(sorted_sigs, 1):
        sig["priority_rank"] = rank

    # ── STATS ─────────────────────────────────────────────────────────────────
    signals  = result["signals"]
    execute  = [s for s in signals if s.get("options_verdict","").upper()=="EXECUTE"
                or s.get("sb_final_verdict","").upper()=="EXECUTE"]
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

    summary_j = result.get("summary",{})
    result["stats"] = {
        # Core verdicts (from new pipeline fields)
        "execute_count":       len(execute),
        "armed_count":         len(armed),
        "stand_down_count":    len(stand),
        "total_scanned":       len(signals),
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
        "mv_validated_at":     mv_rows[0].get("mv_validated_at","") if mv_rows else "",
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

    _run_cache[run_id] = result
    return result

# ─── ROUTES ────────────────────────────────────────────────────────────────────

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
        "server_time": datetime.utcnow().isoformat(),
        "version": "2.0 — EIL-primary architecture"
    })

@app.route("/api/runs")
def api_runs():
    runs = _list_runs()
    return jsonify({"runs": runs, "latest": runs[0] if runs else None, "count": len(runs)})

@app.route("/api/run/<run_id>")
def api_run(run_id):
    return jsonify(_load_run(run_id))

@app.route("/api/run/latest")
def api_run_latest():
    runs = _list_runs()
    if not runs:
        return jsonify({"error": "No runs found in " + str(RUNS_DIR)}), 404
    return jsonify(_load_run(runs[0]))

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
    print(f"  🔄 /api/reload_morning — {msg}")
    return jsonify({"ok": True, "message": msg})

@app.route("/api/enter_trade", methods=["POST"])
def api_enter_trade():
    """
    Enter trade gate updated for new pipeline fields.
    OLD gate: sb_final_verdict == EXECUTE
    NEW gate: options_verdict == EXECUTE AND campaign_verdict in (READY_EXECUTE, READY_PROBE)
              OR thesis_decision == GO (v5 decision)
    """
    try:
        project_root = str(BASE_DIR)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from vanguard.trade_contract import create_contract, find_open_contract

        body = request.get_json(force=True)
        ticker            = str(body.get("ticker","")).strip().upper()
        entry_price       = float(body.get("entry_price",0))
        invalidation_price = float(body.get("invalidation_price",0))
        run_id            = body.get("run_id") or _list_runs()[0]

        if not ticker:
            return jsonify({"ok":False,"error":"ticker required"}), 400
        if entry_price <= 0:
            return jsonify({"ok":False,"error":"entry_price must be > 0"}), 400
        if invalidation_price <= 0:
            return jsonify({"ok":False,"error":"invalidation_price must be > 0"}), 400

        # Load signal
        payload = _load_run(run_id)
        sig = next((s for s in payload.get("signals",[])
                    if s.get("ticker","").upper() == ticker), None)
        if not sig:
            return jsonify({"ok":False,"error":f"{ticker} not in signals"}), 404

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
                "error": f"{ticker}: options_verdict={opt_v}, campaign={camp_v}, thesis={thesis} — not tradeable"
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
            entry_state_hash="eil_v2",
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
        filtered = []
        for s in signals:
            ov = (s.get("options_verdict","") or s.get("sb_final_verdict","")).upper()
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

# ─── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  AVSHUNTER · INTELLIGENCE LAB v2.0")
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
    app.run(host="0.0.0.0", port=5002, debug=False)
