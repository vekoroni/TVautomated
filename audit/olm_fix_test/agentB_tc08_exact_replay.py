"""Agent B (OLM fix validation) - exact TC-08 replay, before vs after.

Reconstructs the literal TC-08 fixture from
audit/olm_test/_agent2_tc_runner.py::tc_08() and runs it against:
  (a) the pre-change backup module (must reproduce "0 candidates" for OI=5)
  (b) the current, post-remediation module (must now retain the contract)
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CURRENT_PATH = ROOT / "scripts" / "avshunter_options_intelligence.py"
BACKUP_PATH = ROOT / "backups" / "olm_blocker_remediation_prechange_20260829_2035" / "scripts" / "avshunter_options_intelligence.py"

current_mod = load_module(CURRENT_PATH, "oi_current")
backup_mod = load_module(BACKUP_PATH, "oi_backup")

NOW = datetime.now(timezone.utc).isoformat()


def run(mod, oi, volume, label):
    rows = [dict(
        right="C", strike=102, dte=20, expiration_date="2026-09-18",
        bid=1.00, ask=1.05, delta=0.30, gamma=0.02, theta=-0.03, vega=0.06,
        implied_vol=0.35, quote_timestamp_utc=NOW, open_interest=oi, volume=volume,
        symbol=f"TEST08{label}260918C00102000",
    )]
    df = pd.DataFrame(rows)
    ctx = {"direction": "CALL", "dte_window": (7, 30, 60), "spot": 100.0,
           "structural_target": 110.0, "dte_config": {}}
    return mod.select_repair_alternative_contracts(df, ctx, selected_contract=None, limit=5)


results = {}
for tag, mod in (("BEFORE(backup)", backup_mod), ("AFTER(current)", current_mod)):
    low = run(mod, 5, 2, "LOW")
    at = run(mod, mod.EV3_MIN_OPEN_INTEREST, 2, "AT")
    zero = run(mod, 0, 0, "ZERO")
    results[tag] = {
        "EV3_MIN_OPEN_INTEREST": mod.EV3_MIN_OPEN_INTEREST,
        "EV3_MIN_VOLUME": mod.EV3_MIN_VOLUME,
        "oi5_vol2_candidate_count": len(low),
        "oi5_vol2_retained": len(low) > 0,
        "oi_at_threshold_candidate_count": len(at),
        "oi0_vol0_candidate_count": len(zero),
        "oi0_vol0_retained": len(zero) > 0,
    }
    if low:
        results[tag]["oi5_vol2_symbol"] = low[0]["symbol"]
        results[tag]["oi5_vol2_full_record"] = low[0]

print(json.dumps(results, indent=2, default=str))

out_path = Path(__file__).parent / "agentB_tc08_exact_replay_output.json"
out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
print(f"\nWrote {out_path}")
