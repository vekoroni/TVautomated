# Ticker edge, hold and option breakeven — read-only study (28 Sep 2026)

Requested by ACK, 28 Sep 2026: "the first EV has to be done on the ticker, not the option … once we are sure the
ticker has a high advantage of moving, the option comes into play" and "every hold can be anything from intraday to
20 sessions or longer; the analysis should determine this". Governing design: `Enhancements/decision_map/
AVS_SD_TICKER_FORECAST_TO_OPTION_VALUATION_20260927.md` (TEV-001, signed off 27 Sep) and its build plan. No
pipeline code changed; scripts in `.claude_scratch/int001/` (`ticker_edge_study.py`, `ticker_edge_analysis.py`,
`ticker_hold_option_study.py`, `ticker_hold_option_analysis.py`).

## Method

- **Signals:** every stored run's candidate file, 15 Aug – 27 Sep 2026: the pipeline's direction for each scanned
  ticker on its evidence session, latest run per session. 17,716 ticker-session signals, 18 sessions.
- **Ticker outcome:** canonical daily bars; entry at the next session's open; signed return at the close of hold day
  1…20 (day 1 = open-to-close of the entry day, the shortest hold daily bars allow; no intraday history exists
  beyond the last two sessions). First-passage labels for target/stop pairs, same-bar double touch = stop.
- **Edge:** the signal's return minus the return of taking the same side on every ticker in that session's universe
  (removes market drift). Sessions are the independent unit (session-clustered bootstrap, 90 % intervals).
- **Option on the same paths:** Black–Scholes at the signal's own IV (`contract_iv`, else `hv_30d`), ATM 45-day and
  5 %-ITM 90-day, bought at the ask and sold at the bid (6 % round trip), decay per session, −15 % IV stress variant.
- **Selection honesty:** segments chosen on sessions before 9 Sep, judged on sessions from 10 Sep.

## Findings

1. **EV3 negative is not a formula error.** At base-rate probabilities no target/stop/hold choice makes a long option
   positive (tested 168 geometries on real contracts; best −15 %). Small moves lose to the spread, time decay costs
   ~30–50 % over 20 sessions, and base-rate probabilities carry none of the signal's attributes.
2. **The move the ticker must make for the option to break even:**

| Hold (sessions) | ATM 45-day | ITM 90-day | Signals that moved that far |
|---|---|---|---|
| 1 | 1.0 % | 1.3 % | 20–25 % |
| 5 | 1.7 % | 1.7 % | 31 % |
| 10 | 2.7 % | 2.3 % | 28–30 % |
| 20 | 4.9 % | 3.5 % | 20–24 % |

3. **The pipeline's direction, taken as a whole, has almost no edge over the market** in this window: lift ≤ 0.5 %
   at every hold (e.g. +0.09 % at 10 sessions, interval spanning zero). The option on every signal loses at every
   hold (−7 % day 1, −23 % to −35 % at day 20). PUT signals "won" because the market fell — beta, not edge.
4. **Some attributes look promising but cannot yet be confirmed:** range-break trigger (+3.95 % over the universe at 10
   sessions, n = 108), WBS score top third (+0.86 %), EIL `EXECUTE` (+0.73 %), `STRUCTURAL_BUILD` IV regime (+0.66 %),
   Wyckoff phase D (+0.56 %); "strong" trigger quality, `CRABEL_READY` and volatility-compression triggers
   underperform the market. On discovery sessions the best hold for most segments was 17–20 sessions, but only four
   August sessions have that much history and the holdout has at most 11 sessions of outcome, so **no hold choice and
   no attribute edge survives an out-of-sample test on this data.**
5. **What is missing:** a point-in-time history of the signal attributes long enough to span several market regimes.
   18 correlated sessions from one falling market cannot measure attribute edge or the right hold per attribute.

## What would make positive EV measurable (proposal, needs ACK approval)

1. **Replay the price-derived attributes on canonical history (Aug 2021 – Sep 2026, 3,618 tickers):** Wyckoff
   phase, compression, directional force, WBS, trigger family — the features the live pipeline computes from daily
   bars. This is TEV-001 slice C / register item 4 ("point-in-time research panel"), using the existing C12 owners
   (`avshunter/c12_outcome` base rate, estimators, passage). Option-derived features (IV regime, GEX) enter later,
   only where history exists (Phantom greeks history).
2. **Ticker EV per attribute and per hold day 1…20+:** walk-forward (train earlier years, judge later ones), edge over
   the geometry-matched universe base rate, the hold chosen by the data per attribute, intervals by independent
   20-session blocks.
3. **Option EV on those same paths** (TEV-001 C8): only for ticker states whose measured move clears the breakeven in
   the table above for a specific contract; otherwise the ticker stays a forecast with `NO_POSITIVE_EDGE` for options
   (shares remain a permitted expression).

## Decisions for ACK

- **Hold:** ACK 28 Sep: the hold is determined by the analysis per signal, intraday to 20+ sessions. This supersedes
  the fixed 20-session governed hold of 18 Sep (D2) once a measured replacement exists.
- **EV3 option 3 (built today, uncommitted):** it values at the fixed 20-session hold and EV3's 5/10/20 table;
  design §5.4 says not to invest in a second EV3 track. Recommendation: do not commit the EV3 change; keep the
  Morning contract-identity fix (independent, a genuine data defect).
- **Build plan decisions still open before slice C:** macro inside the ticker forecast (spec forbids today), shares
  in scope, the market-universe base sample.
