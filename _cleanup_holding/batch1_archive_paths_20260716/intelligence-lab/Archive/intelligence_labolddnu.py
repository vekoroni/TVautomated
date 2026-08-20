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

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import os, csv, json, glob
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


@app.route("/api/health")
def api_health():
    runs = _list_runs()
    return jsonify({
        "status": "ok",
        "pipeline_dir": str(RUNS_DIR),
        "pipeline_dir_exists": RUNS_DIR.exists(),
        "run_count": len(runs),
        "latest_run": runs[0] if runs else None,
        "server_time": datetime.utcnow().isoformat()
    })


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
