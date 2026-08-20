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
    opt_map = {r.get("ticker", "").upper(): r for r in opt_rows}

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

    # ── 7. Run health / handshake QA (fail-closed for required artefacts)
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


    # ── Merge: annotate each signal with options + vanguard + dossier fields
    for sig in result["signals"]:
        t = sig.get("ticker", "").upper()
        opt = opt_map.get(t, {})
        vg  = vg_map.get(t, {})
        doss = dossier_map.get(t, {})
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

    # ── Stat card data
    signals = result["signals"]
    execute  = [s for s in signals if s.get("sb_final_verdict") == "EXECUTE"]
    armed    = [s for s in signals if s.get("sb_final_verdict") == "ARMED"]
    stand    = [s for s in signals if s.get("sb_final_verdict") == "STAND_DOWN"]
    core_sigs = [s for s in armed if s.get("sb_campaign") == "CORE_CAMPAIGN"]
    staged_sigs = [s for s in armed if s.get("sb_campaign") == "STAGED"]

    summary = result.get("summary", {})
    result["stats"] = {
        "execute_count"    : len(execute),
        "armed_count"      : len(armed),
        "core_armed_count" : len(core_sigs),
        "staged_armed_count": len(staged_sigs),
        "stand_down_count" : len(stand),
        "total_scanned"    : len(signals),
        "discovery_count"  : len(result["discovery"]),
        "vanguard_count"   : len(vg_rows),
        "vetoes_fired"     : summary.get("vetoes_fired", 0),
        "verdicts_changed" : summary.get("verdicts_changed", 0),
        "core_campaign_count": len([s for s in signals if s.get("sb_campaign") == "CORE_CAMPAIGN"]),
        "top_execute"      : [s.get("ticker") for s in execute],
        "top_armed"        : summary.get("top_armed", [s.get("ticker") for s in armed[:8]]),
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
