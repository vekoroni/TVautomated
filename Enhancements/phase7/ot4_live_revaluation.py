"""Output-trust item 4 acceptance on the live 8 Oct EOD candidates (run 20261008_220129): re-value every row through
the one engine (domain.anticipated_move -> domain.option_valuation) with the same inputs the EOD engine used, and
compare with the published (European, r = q = 0, gross) value multiple and pays state. Read-only; JSON receipt beside.
Dividend yield: the tastytrade metrics cache as it stands (ASSUMED_ZERO where not fetched).
"""
import collections
import json
import statistics
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_data.dividend_history import dividend_inputs  # noqa: E402
from domain.anticipated_move import anticipated_move_fields  # noqa: E402

RUN = "20261008_220129"
df = pd.read_csv(ROOT / "data/output/runs" / RUN / "morning_validation" / f"morning_candidates_{RUN}.csv",
                 low_memory=False, dtype=str).fillna("")
pays_change, n_valued, ratio, examples, models, divs = collections.Counter(), 0, [], [], collections.Counter(), collections.Counter()
scen = collections.defaultdict(list)
for _, r in df.iterrows():
    direction = (r.get("direction") or r.get("final_direction") or "").upper()
    new = anticipated_move_fields(
        direction=direction, spot=r.get("signal_price"), outcome_level=r.get("thesis_outcome_level"),
        outcome_definition=r.get("thesis_outcome_definition"), timeframe=r.get("thesis_event_timeframe"),
        duration={"test": r.get("thesis_duration_test"), "status": r.get("thesis_duration_status"),
                  "n": r.get("thesis_duration_n"), "q50_bars": r.get("thesis_duration_q50_bars"),
                  "q80_bars": r.get("thesis_duration_q80_bars"), "p_event": r.get("thesis_p_outcome_by_limit"),
                  "p_invalidation": r.get("thesis_p_invalidation_by_limit")},
        vol_annual=r.get("target_reachable_vol_annual"),
        contract={"strike": r.get("strike"), "ask": r.get("contract_ask"), "bid": r.get("contract_bid"),
                  "underlying": r.get("ticker"), "iv": r.get("contract_iv"), "expiry": r.get("expiry"),
                  "as_of": r.get("bar_data_asof")},
        governed_window_sessions=r.get("planned_hold_sessions"),
        earnings={"earnings_state": r.get("earnings_state"), "earnings_sessions_to_event": r.get("earnings_sessions_to_event")},
        trade_side_event=(r.get("thesis_structure_alignment") or "").upper() == "ALIGNED",
        invalidation_level=r.get("invalidation_price") or r.get("invalidation_eod") or None,
        **dividend_inputs(r.get("ticker"), as_of=r.get("bar_data_asof"), spot=r.get("signal_price")))
    old_state, new_state = r.get("anticipated_pays_state") or "", new["anticipated_pays_state"]
    pays_change[f"{old_state} -> {new_state}"] += 1
    try:
        old_m = float(r.get("anticipated_value_multiple_q50"))
    except ValueError:
        old_m = None
    if new["anticipated_value_multiple_q50"] is not None:
        n_valued += 1
        models[new["valuation_model"]] += 1
        divs[str(new["valuation_dividend_basis"]).split(":")[0]] += 1
        for k in ("scenario_target_return_on_premium", "scenario_invalidation_return_on_premium", "scenario_stall_return_on_premium"):
            if new[k] is not None:
                scen[k].append(new[k])
        if old_m:
            ratio.append(new["anticipated_value_multiple_q50"] / old_m)
    if r.get("ticker") in ("SMCI", "NEO", "HAFN", "COHR", "HPE"):
        examples.append({"ticker": r.get("ticker"), "old_multiple_gross_european": old_m, "old_pays": old_state,
                         **{k: new[k] for k in ("anticipated_value_multiple_q50", "anticipated_pays_state", "valuation_model",
                                                "scenario_exit_sessions", "scenario_target_exit_spot",
                                                "scenario_target_return_on_premium", "scenario_invalidation_return_on_premium",
                                                "scenario_stall_return_on_premium", "valuation_cost_basis")}})
q = lambda xs: {"n": len(xs), "q25": round(statistics.quantiles(xs, n=4)[0], 4), "median": round(statistics.median(xs), 4),
                "q75": round(statistics.quantiles(xs, n=4)[2], 4)} if len(xs) > 3 else {"n": len(xs)}
out = {"run": RUN, "rows": len(df), "valued_rows": n_valued, "models": dict(models), "dividend_basis": dict(divs),
       "pays_transitions": dict(pays_change.most_common()), "new_over_old_multiple": q(ratio),
       "scenarios": {k: q(v) for k, v in scen.items()}, "examples": examples}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k != "examples"}, indent=1, default=str))
for e in examples:
    print(e)
