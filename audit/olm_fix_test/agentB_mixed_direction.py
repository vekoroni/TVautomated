import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pandas as pd
import scripts.avshunter_options_intelligence as oi

def row(symbol, right, delta):
    return dict(symbol=symbol, right=right, strike=102.0 if right=="C" else 98.0,
        expiration_date="2026-09-18", dte=20, bid=1.00, ask=1.05, delta=delta,
        gamma=0.02, theta=-0.03, vega=0.06, implied_vol=0.35,
        quote_timestamp_utc="2026-08-14T10:30:00Z", open_interest=500, volume=100,
        contract_multiplier=100)

mixed = pd.DataFrame([
    row("CALLROW", "C", 0.30),
    row("PUTROW", "P", -0.30),
])
ctx_call = {"direction": "CALL", "dte_window": (7,30,60), "spot": 100.0, "structural_target": 110.0, "dte_config": {}}
ctx_put = {"direction": "PUT", "dte_window": (7,30,60), "spot": 100.0, "structural_target": 90.0, "dte_config": {}}

call_result = oi.select_repair_alternative_contracts(mixed, ctx_call)
put_result = oi.select_repair_alternative_contracts(mixed, ctx_put)

print("CALL thesis symbols:", [c["symbol"] for c in call_result], "rights:", [c["right"] for c in call_result])
print("PUT thesis symbols:", [c["symbol"] for c in put_result], "rights:", [c["right"] for c in put_result])
assert [c["right"] for c in call_result] == ["C"]
assert [c["right"] for c in put_result] == ["P"]
print("PASS: mixed-chain thesis-direction alignment confirmed")
