"""Run the ordering fixture against ONE module (argv[1]: 'current' or 'backup')."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

which = sys.argv[1] if len(sys.argv) > 1 else "current"
if which == "current":
    target = ROOT / "scripts" / "avshunter_options_intelligence.py"
else:
    target = ROOT / "backups" / "olm_blocker_remediation_prechange_20260829_2035" / "scripts" / "avshunter_options_intelligence.py"

spec = importlib.util.spec_from_file_location("oi_mod_ord_" + which, str(target))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def ordering_fixture_rows():
    rows = []
    expiries = [("2026-09-08", 25), ("2026-09-13", 30), ("2026-09-23", 40)]
    strikes = [
        (98.0, 0.25, 0.03, 400, 50),
        (100.0, 0.35, 0.02, 900, 300),
        (100.0, 0.35, 0.02, 100, 10),
        (102.0, 0.45, 0.05, 250, 20),
        (104.0, 0.55, 0.01, 700, 80),
    ]
    for e_idx, (expiry, dte) in enumerate(expiries):
        for s_idx, (strike, delta, spread_bump, oi_val, vol_val) in enumerate(strikes):
            mid = 2.00
            half_spread = spread_bump * mid
            bid = round(mid - half_spread, 4)
            ask = round(mid + half_spread, 4)
            rows.append(dict(
                symbol=f"ORD{e_idx}{s_idx}", right="C", strike=strike,
                expiration_date=expiry, dte=dte,
                bid=bid, ask=ask, delta=delta, gamma=0.03, theta=-0.04, vega=0.10,
                implied_vol=0.40, quote_timestamp_utc="2026-08-14T10:30:00Z",
                open_interest=oi_val, volume=vol_val, contract_multiplier=100,
            ))
    return rows


CTX = {"direction": "CALL", "dte_window": (7, 30, 60), "spot": 100.0,
       "structural_target": 110.0, "dte_config": {}}

rows = ordering_fixture_rows()
candidates = mod.select_repair_alternative_contracts(pd.DataFrame(rows), CTX, limit=6)
order = [c["symbol"] for c in candidates]

out_path = Path(__file__).parent / f"agentB_ordering_{which}_output.json"
out_path.write_text(json.dumps(order, indent=2), encoding="utf-8")
print(json.dumps({"module": which, "order": order}, indent=2))
