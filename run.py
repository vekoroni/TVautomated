# -*- coding: utf-8 -*-
r"""
AVSHUNTER run.py v4 — Production Governance Wrapper (stabilised)

Adds:
- Macro normaliser auto-run before macro gate when require_macro_valid=true.
- Monitor-by-default with explicit override:
    --override immediate
- Discovery + stale data gates unchanged from v3.
"""

from __future__ import annotations

import argparse
import os
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

from dotenv import load_dotenv

from orchestrator.main import AVSHUNTEROrchestrator


def repo_root() -> Path:
    return Path(__file__).resolve().parent

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def latest_dir_by_mtime(glob_pat: str) -> Optional[Path]:
    candidates = [Path(p) for p in repo_root().glob(glob_pat)]
    candidates = [p for p in candidates if p.exists()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


REQUIRED_MACRO_KEYS = [
    "regime_state",
    "dir_bias",
    "vol_mode",
    "trend_energy",
    "usd_state",
    "rates_impulse",
    "liquidity_pulse",
    "sector_tilt",
    "regime_drift_status",
    "risk_on_off_switch",
    "macro_conviction",
    "notes",
]

@dataclass
class GateResult:
    ok: bool
    reason: str = ""
    detail: Dict[str, Any] = None

def gate_macro_valid(macro_path: Path) -> GateResult:
    if not macro_path.exists():
        return GateResult(False, f"Macro file missing: {macro_path}", {})
    try:
        data = read_json(macro_path)
    except Exception as e:
        return GateResult(False, f"Macro JSON unreadable: {e}", {})

    missing = [k for k in REQUIRED_MACRO_KEYS if k not in data or data.get(k) in (None, "")]
    if missing:
        return GateResult(False, "Missing macro keys: " + ", ".join(missing), {"missing": missing})
    return GateResult(True, "", {"macro": str(macro_path)})

def gate_discovery_complete(packages_dir: Optional[Path]) -> GateResult:
    if packages_dir is None:
        latest_run = latest_dir_by_mtime("data/output/runs/*")
        if latest_run:
            packages_dir = latest_run / "packages"

    if packages_dir is None:
        return GateResult(False, "No packages_dir supplied and no runs found under data/output/runs/*", {})

    if not packages_dir.exists():
        return GateResult(False, f"Packages dir missing: {packages_dir}", {})

    json_files = list(packages_dir.glob("*.json"))
    if len(json_files) == 0:
        return GateResult(False, f"Packages dir has 0 json files: {packages_dir}", {})

    return GateResult(True, "", {"packages_dir": str(packages_dir), "json_count": len(json_files)})

def gate_refresh_not_stale(cfg: Dict[str, Any], refresh_report_latest: Path) -> GateResult:
    if not refresh_report_latest.exists():
        return GateResult(False, f"Refresh audit missing: {refresh_report_latest}", {})

    try:
        rep = read_json(refresh_report_latest)
    except Exception as e:
        return GateResult(False, f"Refresh audit unreadable: {e}", {})

    pct = rep.get("pct", {}) or {}
    stale_pct = float(pct.get("stale_pct", 0.0))
    fail_pct = float(pct.get("fail_pct", 0.0))

    g = cfg.get("governance", {}) or {}
    max_stale_pct = float(g.get("max_stale_pct", 5.0))
    max_fail_pct = float(g.get("max_fail_pct", 5.0))

    if stale_pct > max_stale_pct:
        return GateResult(False, f"stale_pct {stale_pct:.2f}% > max_stale_pct {max_stale_pct:.2f}%", {"stale_pct": stale_pct})
    if fail_pct > max_fail_pct:
        return GateResult(False, f"fail_pct {fail_pct:.2f}% > max_fail_pct {max_fail_pct:.2f}%", {"fail_pct": fail_pct})

    return GateResult(True, "", {"stale_pct": stale_pct, "fail_pct": fail_pct, "report": str(refresh_report_latest)})


def load_settings(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise RuntimeError(f"Config missing: {config_path}")
    return read_json(config_path)

def maybe_apply_override(cfg: Dict[str, Any], override: Optional[str]) -> Tuple[Dict[str, Any], Optional[str], bool]:
    if not override:
        return cfg, None, False

    override = override.strip().lower()
    if override != "immediate":
        raise RuntimeError("Unknown override. Only supported: immediate")

    orch = cfg.get("orchestrator", {}) or {}
    orch["mode"] = "immediate"
    orch["immediate_allow_incomplete"] = True
    cfg["orchestrator"] = orch

    return cfg, "OVERRIDE ACTIVE: IMMEDIATE MODE (allow_incomplete=true)", True


def run_macro_normaliser(py_exe: Path, input_macro: Optional[Path], output_macro: Path) -> Tuple[bool, str]:
    script = repo_root() / "scripts" / "normalise_macro_contract.py"
    if not script.exists():
        return False, f"Normaliser missing: {script}"

    cmd = [str(py_exe), str(script), "--out", str(output_macro), "--fail_on_missing"]
    if input_macro:
        cmd += ["--in", str(input_macro)]

    try:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root()))
    except Exception as e:
        return False, f"Normaliser failed to start: {e}"

    if p.returncode != 0:
        msg = (p.stdout or "") + "\n" + (p.stderr or "")
        return False, msg.strip()

    return True, (p.stdout or "").strip()


def resolve_python_exe() -> Path:
    import sys
    return Path(sys.executable)

def resolve_macro_latest_path() -> Path:
    return repo_root() / "dropbox" / "macro" / "macro_intelligence_latest.json"

def resolve_refresh_audit_path() -> Path:
    return repo_root() / "data" / "audit" / "refresh_report_latest.json"


def main() -> int:
    load_dotenv()

    ap = argparse.ArgumentParser(description="AVSHUNTER run.py v4 — governance wrapper (with macro normaliser)")
    ap.add_argument("--config", default="config/settings.json", help="Path to settings.json")
    ap.add_argument("--session", default="", help="Session name (premarket, midmarket, etc.)")
    ap.add_argument("--mode", choices=["prep", "ops"], default="ops", help="prep = governance preflight only; ops = run orchestrator after gates")
    ap.add_argument("--macro", default=None, help="Explicit macro JSON input (raw). Normalised output is written to macro_intelligence_latest.json")
    ap.add_argument("--packages_dir", default=None, help="Packages dir for discovery-complete gate (optional)")
    ap.add_argument("--override", default=None, help="Override (supported: immediate)")
    ap.add_argument("--context_dir", default=None, help="Pinned context directory (exported as AVSHUNTER_CONTEXT_DIR). Optional.")
    args = ap.parse_args()

    config_path = repo_root() / args.config
    cfg = load_settings(config_path)

    if args.context_dir:
        os.environ["AVSHUNTER_CONTEXT_DIR"] = str(Path(args.context_dir))

    cfg2, banner, overridden = maybe_apply_override(cfg, args.override)

    orch_cfg = cfg2.get("orchestrator", {}) or {}
    require_macro_valid = bool(orch_cfg.get("require_macro_valid", False))
    require_discovery_complete = bool(orch_cfg.get("require_discovery_complete", False))
    block_on_stale_data = bool(orch_cfg.get("block_on_stale_data", False))

    # Macro: always write latest contract-correct file
    macro_out = resolve_macro_latest_path()
    macro_in = Path(args.macro) if args.macro else None

    normaliser_log = ""
    if require_macro_valid:
        ok, log = run_macro_normaliser(resolve_python_exe(), macro_in, macro_out)
        normaliser_log = log
        if not ok:
            print("=" * 72)
            print("AVSHUNTER RUNNER v4 — Macro normaliser BLOCKED")
            print(log)
            print("=" * 72)
            return 2

    packages_dir = Path(args.packages_dir) if args.packages_dir else None
    refresh_audit = resolve_refresh_audit_path()

    print("=" * 72)
    print("AVSHUNTER RUNNER v4 — Monitor-by-default + explicit override + macro normaliser")
    print(f"UTC: {utc_now_iso()}")
    if banner:
        print(f"⚠️  {banner}")
    print(f"Mode: {args.mode} | Session: {args.session or '(none)'}")
    print(f"Config: {config_path}")
    print(f"Macro(latest): {macro_out}")
    if args.macro:
        print(f"Macro(input):  {macro_in}")
    if packages_dir:
        print(f"Packages: {packages_dir}")
    if normaliser_log:
        print("-" * 72)
        print(normaliser_log)
    print("=" * 72)

    results: List[Tuple[str, GateResult]] = []
    if require_macro_valid:
        results.append(("require_macro_valid", gate_macro_valid(macro_out)))
    if require_discovery_complete:
        results.append(("require_discovery_complete", gate_discovery_complete(packages_dir)))
    if block_on_stale_data:
        results.append(("block_on_stale_data", gate_refresh_not_stale(cfg2, refresh_audit)))

    for name, gr in results:
        if gr.ok:
            print(f"✅ GATE PASS: {name}")
        else:
            print(f"⛔ GATE FAIL: {name} — {gr.reason}")

    if any((not gr.ok) for _, gr in results):
        return 2

    if args.mode == "prep":
        print("PREP COMPLETE: all enabled gates passed.")
        return 0

    cfg_path_to_use = config_path
    if overridden:
        tmp_dir = repo_root() / "data" / "output" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"settings_override_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        write_json(tmp_path, cfg2)
        cfg_path_to_use = tmp_path

    try:
        orchestrator = AVSHUNTEROrchestrator(config_path=str(cfg_path_to_use), session=args.session)
        orchestrator.run()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
