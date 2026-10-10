"""Output-trust item 4 execution check: the engine's entry value (spot, the contract's own IV, the rate, dividend as
held) against the quoted bid/ask on the live 8 Oct EOD candidates. Read-only; JSON receipt beside."""
import json
import statistics
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_data.dividend_history import dividend_inputs  # noqa: E402
from domain.option_valuation import exercise_style, option_value, resolve_dividend, resolve_rate  # noqa: E402

RUN = "20261008_220129"
df = pd.read_csv(ROOT / "data/output/runs" / RUN / "morning_validation" / f"morning_candidates_{RUN}.csv",
                 low_memory=False)
rate, _ = resolve_rate(None, None)
rel, inside, n = [], 0, 0
for _, r in df.iterrows():
    try:
        side = str(r.get("direction")).upper(); s = float(r["signal_price"]); k = float(r["strike"])
        bid, ask, iv = float(r["contract_bid"]), float(r["contract_ask"]), float(r["contract_iv"])
        days = (date.fromisoformat(str(r["expiry"])[:10]) - date.fromisoformat(str(r["bar_data_asof"])[:10])).days
    except (TypeError, ValueError, KeyError):
        continue
    if side not in ("CALL", "PUT") or not (ask > 0 and bid >= 0 and iv > 0 and days > 0) or bid > ask:
        continue
    div = dividend_inputs(r["ticker"], as_of=r["bar_data_asof"], spot=s)
    q, _ = resolve_dividend(div["dividend_yield"], div["dividend_basis"])
    v = option_value(side, s, k, days / 365.0, iv, rate=rate, dividend_yield=q, style=exercise_style(r["ticker"]))["value"]
    mid = (bid + ask) / 2.0
    n += 1
    rel.append(abs(v - mid) / mid if mid > 0 else 0.0)
    inside += int(bid - 0.005 <= v <= ask + 0.005)
out = {"run": RUN, "contracts": n, "model_inside_bid_ask": inside, "share_inside": round(inside / n, 4) if n else None,
       "abs_error_vs_mid": {"median": round(statistics.median(rel), 4), "p90": round(statistics.quantiles(rel, n=10)[8], 4)}
       if len(rel) > 10 else None,
       "note": "contract IV is the provider's quote-implied IV; agreement tests the engine and its inputs (rate, days, "
               "dividend basis), not a forecast"}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=1))
