"""Run the exact TC-08 fixture against ONE module (passed as argv[1]: 'current' or 'backup').
Avoids loading both modules in-process (their stdout-wrapping at import time
conflicts when done twice in one interpreter)."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

which = sys.argv[1] if len(sys.argv) > 1 else "current"
if which == "current":
    target = ROOT / "scripts" / "avshunter_options_intelligence.py"
else:
    target = ROOT / "backups" / "olm_blocker_remediation_prechange_20260829_2035" / "scripts" / "avshunter_options_intelligence.py"

spec = importlib.util.spec_from_file_location("oi_mod_" + which, str(target))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NOW = datetime.now(timezone.utc).isoformat()


def run(oi, volume, label):
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


low = run(5, 2, "LOW")
at = run(mod.EV3_MIN_OPEN_INTEREST, 2, "AT")
zero = run(0, 0, "ZERO")

result = {
    "module": which,
    "target_path": str(target),
    "EV3_MIN_OPEN_INTEREST": mod.EV3_MIN_OPEN_INTEREST,
    "EV3_MIN_VOLUME": mod.EV3_MIN_VOLUME,
    "oi5_vol2_candidate_count": len(low),
    "oi5_vol2_retained": len(low) > 0,
    "oi_at_threshold_candidate_count": len(at),
    "oi0_vol0_candidate_count": len(zero),
    "oi0_vol0_retained": len(zero) > 0,
    "oi5_vol2_record": low[0] if low else None,
}

out_path = Path(__file__).parent / f"agentB_tc08_{which}_output.json"
out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(json.dumps(result, indent=2, default=str))
