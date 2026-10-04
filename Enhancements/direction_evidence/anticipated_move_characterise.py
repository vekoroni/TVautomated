"""Characterise the anticipated move on real data (ACK 3 Oct 2026, design §9 step 2 acceptance).

For Morning GO tickers of run 20261001_211641: BEH-001 on canonical bars to 2026-10-01, the trade-side event
(thesis_category), annualised 20-session realised vol (the reachable-target owner's input), the Morning
contract quote, the MarketData earnings date (session cache) -> anticipated_move_fields. Read-only.
"""
import json, math, os, sys
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).parent))
from dir002_replay import read_bars
from domain.structure_behaviour.engine import analyse_ticker
from domain.structure_behaviour.policy import load_policy
from domain.structure_behaviour.thesis_category import thesis_category
from domain.anticipated_move import anticipated_move_fields
from canonical_data.marketdata_earnings import fetch_marketdata_earnings
from earnings_calendar_enricher import earnings_disclosure

AS_OF = "2026-10-01"
m = pd.read_csv(ROOT / "data/output/runs/20261001_211641/morning_validation/morning_validated_trades_20261001_211641.csv", low_memory=False)
go = m[m.verdict.eq("GO")]
tickers = sys.argv[1].split(",") if len(sys.argv) > 1 else list(go.ticker.head(25))
policy = load_policy()
earn = fetch_marketdata_earnings(tickers, as_of=date(2026, 10, 2), cache_dir=Path(os.environ["TEMP"]) / "md_earn_cache")
rows = []
for t in tickers:
    r = m[m.ticker.eq(t)].iloc[0]
    bars = read_bars(t, AS_OF)
    beh = analyse_ticker(t, bars, None, policy, intraday_status="HISTORICAL_REPLAY")
    tc = thesis_category(beh["readings"], r.resolved_direction)
    lr = np.log(bars.close).diff().tail(20)
    vol = float(lr.std() * math.sqrt(252))
    e = earnings_disclosure(earn.get(t, {}), as_of=date(2026, 10, 2), hold_sessions=20, expiry=r.selected_contract_expiry)
    am = anticipated_move_fields(
        direction=r.resolved_direction, spot=r.live_price, outcome_level=tc["thesis_outcome_level"],
        outcome_definition=tc["thesis_outcome_definition"], timeframe=tc["thesis_event_timeframe"],
        duration={"test": tc["thesis_duration_test"], "status": tc["thesis_duration_status"], "n": tc["thesis_duration_n"],
                  "q50_bars": tc["thesis_duration_q50_bars"], "q80_bars": tc["thesis_duration_q80_bars"],
                  "p_event": tc["thesis_p_outcome_by_limit"], "p_invalidation": tc["thesis_p_invalidation_by_limit"]},
        vol_annual=vol, contract={"strike": r.selected_contract_strike, "ask": r.live_contract_ask, "iv": r.live_contract_iv,
                                  "expiry": r.selected_contract_expiry, "as_of": "2026-10-02"},
        governed_window_sessions=20, earnings=e, trade_side_event=tc["thesis_structure_alignment"] == "ALIGNED")
    rows.append({"ticker": t, "side": r.resolved_direction, "spot": r.live_price, "event": tc["thesis_category"],
                 "struct": am["anticipated_structural_level"], "level": am["anticipated_level"], "basis": am["anticipated_level_basis"],
                 "move%": am["anticipated_move_pct"], "q50/q80": f'{am["anticipated_sessions_q50"]}/{am["anticipated_sessions_q80"]}',
                 "p_out": am["anticipated_p_outcome_by_limit"], "n": am["anticipated_evidence_n"], "be%": am["anticipated_breakeven_move_pct"],
                 "cover": am["anticipated_move_coverage"], "x_q50": am["anticipated_value_multiple_q50"], "x_q80": am["anticipated_value_multiple_q80"],
                 "x_earn": am["anticipated_value_multiple_earnings_stress"], "fit": am["anticipated_time_fit"], "state": am["anticipated_move_state"], "old_3R": r.get("target_price") if "target_price" in r else None,
                 "earnings": e["earnings_date"]})
df = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 46)
print(df.to_string(index=False))
print("\nbasis:", df.basis.value_counts(dropna=False).to_dict(), "| time estimated:", int(df["q50/q80"].ne("None/None").sum()), "of", len(df))
print("states:", df.state.value_counts(dropna=False).to_dict()); print("time fit:", df.fit.value_counts(dropna=False).to_dict())
print("coverage >= 1:", int((df.cover >= 1).sum()), "| coverage < 1:", int((df.cover < 1).sum()), "| not computed:", int(df.cover.isna().sum()))
