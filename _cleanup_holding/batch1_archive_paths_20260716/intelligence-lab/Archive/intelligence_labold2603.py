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

# ─── SECTOR MAP ────────────────────────────────────────────────────────────────
# Load clean_universe__with_sector.csv once at startup for sector enrichment.
# Searched relative to BASE_DIR and its parent directories.

SECTOR_SHORT_MAP = {
    'Communication Services': 'COMM', 'Consumer Discretionary': 'DISC',
    'Consumer Staples': 'STPL',       'Energy': 'ENRG',
    'Financials': 'FINL',             'Health Care': 'HLTH',
    'Industrials': 'INDS',            'Information Technology': 'TECH',
    'Materials': 'MATL',              'Real Estate': 'REIT',
    'Utilities': 'UTIL',              'ETF': 'ETF',
}

SECTOR_REGIME_SENSITIVITY = {
    'Utilities': 'HIGH', 'Real Estate': 'HIGH', 'Energy': 'HIGH',
    'Financials': 'MEDIUM', 'Information Technology': 'MEDIUM',
    'Consumer Discretionary': 'MEDIUM', 'Industrials': 'MEDIUM',
    'Materials': 'MEDIUM', 'Health Care': 'LOW',
    'Consumer Staples': 'LOW', 'Communication Services': 'LOW', 'ETF': 'LOW',
}

_SECTOR_MAP: dict = {}

def _load_sector_map() -> dict:
    """Load sector universe CSV. Returns dict keyed by uppercase ticker."""
    global _SECTOR_MAP
    if _SECTOR_MAP:
        return _SECTOR_MAP
    search = [
        BASE_DIR / "clean_universe__with_sector.csv",
        BASE_DIR / "data" / "clean_universe__with_sector.csv",
        BASE_DIR / "data" / "universe" / "clean_universe__with_sector.csv",
        BASE_DIR.parent / "clean_universe__with_sector.csv",
        Path(__file__).resolve().parent / "clean_universe__with_sector.csv",
    ]
    for p in search:
        if p.exists():
            try:
                import csv as _csv
                with open(p, newline='', encoding='utf-8-sig') as f:
                    for row in _csv.DictReader(f):
                        t = str(row.get('ticker', '')).strip().upper()
                        if not t:
                            continue
                        sector = str(row.get('sector', '')).strip()
                        _SECTOR_MAP[t] = {
                            'sector':      sector or 'UNKNOWN',
                            'sector_short': SECTOR_SHORT_MAP.get(sector, sector[:4].upper() if sector else 'N/A'),
                            'sector_etf':  str(row.get('sector_etf', '')).strip(),
                            'industry':    str(row.get('industry', '')).strip() or 'UNKNOWN',
                            'sector_regime_sensitivity': SECTOR_REGIME_SENSITIVITY.get(sector, 'MEDIUM'),
                        }
                print(f"  [SECTOR] Loaded {len(_SECTOR_MAP)} tickers from {p.name}")
                return _SECTOR_MAP
            except Exception as e:
                print(f"  [SECTOR] Warning: could not load {p}: {e}")
    print("  [SECTOR] Warning: clean_universe__with_sector.csv not found")
    return _SECTOR_MAP

def _get_sector(ticker: str) -> dict:
    if not _SECTOR_MAP:
        _load_sector_map()
    return _SECTOR_MAP.get(str(ticker).upper().strip(), {
        'sector': 'UNKNOWN', 'sector_short': 'N/A',
        'sector_etf': '', 'industry': 'UNKNOWN',
        'sector_regime_sensitivity': 'MEDIUM',
    })

# ─── HELPERS ───────────────────────────────────────────────────────────────────

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


def _load_run(run_id: str) -> dict:
    """Load all pipeline outputs for a given run_id into one payload dict."""
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


    # ── Merge: annotate each signal with options + vanguard + dossier + WBS + EIL + SECTOR
    for sig in result["signals"]:
        t = sig.get("ticker", "").upper()
        opt  = opt_map.get(t, {})
        vg   = vg_map.get(t, {})
        doss = dossier_map.get(t, {})
        wbs  = wbs_map.get(t, {})
        eil  = eil_map.get(t, {})
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
        for k, v in eil.items():
            if k not in sig:
                sig[f"eil__{k}"] = v
        # ── Sector enrichment (injected directly — no prefix, top-level fields)
        # Only inject if superbrain did not already populate (sb v2.1+ does this)
        if not sig.get("sector") or sig.get("sector") == "UNKNOWN":
            sector_info = _get_sector(t)
            sig["sector"]                    = sector_info["sector"]
            sig["sector_short"]              = sector_info["sector_short"]
            sig["sector_etf"]                = sector_info["sector_etf"]
            sig["industry"]                  = sector_info["industry"]
            sig["sector_regime_sensitivity"] = sector_info["sector_regime_sensitivity"]

    # ── Stat card data
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

    # Sector distribution across EXECUTE signals
    sector_dist = {}
    for s in execute:
        sec = s.get("sector", "UNKNOWN") or "UNKNOWN"
        sector_dist[sec] = sector_dist.get(sec, 0) + 1

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
        # Sector
        "sector_distribution" : sector_dist,
        "sector_count"        : len(sector_dist),
    }

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

        # ── HARD GATE: Negative EV — must be positive before entry ────────────
        def _fv(key, default=0.0):
            try:
                v = row.get(key, "")
                if str(v).strip() in ("", "N/A", "nan", "None"):
                    return default
                return float(v)
            except Exception:
                return default

        ev_val = _fv("ev") or _fv("ev_adjusted") or _fv("ev_adj")
        rr_val = _fv("rr") or _fv("rr_options")

        if ev_val < 0:
            return jsonify({
                "ok": False,
                "error": (
                    f"GATE_NEGATIVE_EV: {ticker} EV={ev_val:.3f} is negative. "
                    f"The actuarial database says this setup loses money on average. "
                    f"Cannot lock a negative-EV trade. Review signal economics."
                )
            }), 400

        if 0 < rr_val < 0.5:
            return jsonify({
                "ok": False,
                "error": (
                    f"GATE_LOW_RR: {ticker} R:R={rr_val:.3f}x is below the 0.5x "
                    f"minimum threshold. Risk $1 to make ${rr_val:.2f} is not viable. "
                    f"Cannot lock a sub-threshold R:R trade."
                )
            }), 400

        # ── Check for existing open contract
        existing = find_open_contract(ticker)
        if existing:
            return jsonify({
                "ok": False,
                "error": f"Open contract already exists for {ticker}: {existing.name}"
            }), 409

        # ── Map superbrain fields to contract fields
        def _frow(key, default=0.0):
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
            horizon = "20D"
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
        adx               = _frow("layer1__adx", 20.0)
        atr_pct           = _frow("layer1__atr_percentile", 50.0)
        ev                = _frow("ev", 0.0)
        win_rate          = _frow("win_rate_20d", 0.5)

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



@app.route("/api/sector_summary")
def api_sector_summary():
    """
    Sector breakdown of EXECUTE and EXECUTE_WITH_RISK signals for the latest run.
    Returns concentration risk flags, average EV per sector, PUT/CALL split.
    Enables concentration monitoring — alerts when >25% of signals are in one sector.
    """
    try:
        runs = _list_runs()
        if not runs:
            return jsonify({"ok": False, "error": "No runs found"}), 404
        payload = _load_run(runs[0])
        signals = payload.get("signals", [])

        execute_sigs = [s for s in signals
                        if s.get("sb_final_verdict") in ("EXECUTE", "EXECUTE_WITH_RISK")]
        total = len(execute_sigs)
        if total == 0:
            return jsonify({"ok": True, "sector_summary": [], "total_execute": 0,
                            "sectors_represented": 0})

        # Aggregate by sector
        from collections import defaultdict
        buckets: dict = defaultdict(lambda: {
            "execute_count": 0, "ewr_count": 0,
            "put_count": 0, "call_count": 0,
            "ev_sum": 0.0, "rr_sum": 0.0, "conv_sum": 0.0, "n": 0
        })

        for s in execute_sigs:
            sec   = s.get("sector") or "UNKNOWN"
            short = s.get("sector_short") or SECTOR_SHORT_MAP.get(sec, "N/A")
            etf   = s.get("sector_etf") or ""
            sens  = s.get("sector_regime_sensitivity") or "MEDIUM"

            b = buckets[sec]
            b["sector_short"] = short
            b["sector_etf"]   = etf
            b["sector_regime_sensitivity"] = sens

            if s.get("sb_final_verdict") == "EXECUTE":
                b["execute_count"] += 1
            else:
                b["ewr_count"] += 1

            direction = str(s.get("direction", "") or s.get("options_direction", "")).upper()
            if "PUT" in direction:
                b["put_count"] += 1
            elif "CALL" in direction:
                b["call_count"] += 1

            try:
                b["ev_sum"] += float(s.get("ev") or s.get("ev_adjusted") or 0)
            except Exception:
                pass
            try:
                b["rr_sum"] += float(s.get("rr") or s.get("rr_options") or 0)
            except Exception:
                pass
            try:
                b["conv_sum"] += float(s.get("sb_conv_score") or 0)
            except Exception:
                pass
            b["n"] += 1

        result = []
        for sec, b in sorted(buckets.items(), key=lambda x: -x[1]["execute_count"]):
            n = b["n"]
            conc = round(b["execute_count"] / total * 100, 1)
            result.append({
                "sector":            sec,
                "sector_short":      b.get("sector_short", "N/A"),
                "sector_etf":        b.get("sector_etf", ""),
                "sector_regime_sensitivity": b.get("sector_regime_sensitivity", "MEDIUM"),
                "execute_count":     b["execute_count"],
                "ewr_count":         b["ewr_count"],
                "put_count":         b["put_count"],
                "call_count":        b["call_count"],
                "avg_ev":            round(b["ev_sum"] / n, 3) if n else 0,
                "avg_rr":            round(b["rr_sum"] / n, 3) if n else 0,
                "avg_conviction":    round(b["conv_sum"] / n, 1) if n else 0,
                "concentration_pct": conc,
                "concentration_flag": "HIGH" if conc > 25 else "MEDIUM" if conc > 15 else "NORMAL",
            })

        highest = result[0]["sector"] if result else "N/A"
        return jsonify({
            "ok":                  True,
            "sector_summary":      result,
            "total_execute":       total,
            "sectors_represented": len(result),
            "highest_concentration": highest,
            "run_id":              runs[0],
        })
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e),
                        "trace": traceback.format_exc()}), 500


@app.route("/api/regime_alerts")
def api_regime_alerts():
    """
    Check all open contracts against the current regime.
    Returns alerts when regime has shifted adversely vs the entry regime.
    Runs against the latest pipeline run's macro header.
    """
    try:
        project_root = str(BASE_DIR)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from vanguard.trade_contract import list_open_contracts, load_contract

        runs = _list_runs()
        if not runs:
            return jsonify({"ok": True, "alerts": [], "current_regime": "UNKNOWN"})

        payload = _load_run(runs[0])
        macro   = payload.get("macro", {})
        current_regime = str(macro.get("regime_state", "UNKNOWN")).upper()
        current_risk   = str(macro.get("risk_switch", "UNKNOWN")).upper()

        PUT_FRIENDLY  = {"RISK_OFF", "STRONG_DOWNTREND", "DEFENSIVE", "RISK_OFF_TILT"}
        CALL_FRIENDLY = {"RISK_ON", "STRONG_UPTREND", "GROWTH", "RISK_ON_TILT"}

        alerts = []
        for path in list_open_contracts():
            try:
                c = load_contract(path)
                ticker    = c.get("ticker", "UNKNOWN")
                direction = str(c.get("direction", "")).upper()
                entry_regime = str(c.get("entry_macro_regime", "")).upper()

                regime_changed = (current_regime != entry_regime and
                                  entry_regime not in ("", "UNKNOWN"))

                if direction == "PUT":
                    currently_aligned = current_regime in PUT_FRIENDLY
                elif direction == "CALL":
                    currently_aligned = current_regime in CALL_FRIENDLY
                else:
                    currently_aligned = True   # strangle/unknown — no alignment check

                alert_type = None
                if regime_changed and not currently_aligned:
                    alert_type = "REGIME_ADVERSE_SHIFT"
                    severity   = "HIGH"
                    message    = (f"Regime shifted {entry_regime} → {current_regime}. "
                                  f"Original actuarial EV may no longer apply. "
                                  f"Review before next session.")
                    action     = "Run full dossier review. Consider reducing to 50% size."
                elif regime_changed and currently_aligned:
                    alert_type = "REGIME_FAVOURABLE_SHIFT"
                    severity   = "INFO"
                    message    = (f"Regime shifted to {current_regime}. "
                                  f"Macro now aligned with {direction} thesis.")
                    action     = "Review Stage 4 add conditions."
                elif not currently_aligned and not regime_changed:
                    alert_type = "PERSISTENT_REGIME_HEADWIND"
                    severity   = "MEDIUM"
                    message    = (f"Regime {current_regime} continues to work "
                                  f"against {direction} position.")
                    action     = "Apply dynamic hold compression. Monitor theta."

                if alert_type:
                    alerts.append({
                        "ticker":         ticker,
                        "direction":      direction,
                        "alert_type":     alert_type,
                        "severity":       severity,
                        "entry_regime":   entry_regime,
                        "current_regime": current_regime,
                        "message":        message,
                        "recommended_action": action,
                        "days_in_trade":  c.get("days_in_trade", 0),
                    })
            except Exception:
                pass

        return jsonify({
            "ok":             True,
            "alerts":         alerts,
            "current_regime": current_regime,
            "current_risk":   current_risk,
            "run_id":         runs[0],
            "alert_count":    len(alerts),
            "high_severity":  sum(1 for a in alerts if a["severity"] == "HIGH"),
        })

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
