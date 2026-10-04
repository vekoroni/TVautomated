# Historical replay study — pre-registration (29 Sep 2026)

Approved by ACK, 28 Sep 2026: "approved, start the historical replay study". Parent: TEV-001 design
(`Enhancements/decision_map/AVS_SD_TICKER_FORECAST_TO_OPTION_VALUATION_20260927.md`) slice C / register item 4;
findings that motivated it: `AVS_TICKER_EDGE_AND_HOLD_STUDY_20260928.md`. Read-only research: no pipeline code
changes, no provider calls, nothing written into runs or canonical stores. This file is written **before** any
replay result is seen and is not edited afterwards except to append the results section.

## Question

For each price-derived signal attribute the live pipeline computes, does a ticker carrying it move in the implied
direction more than the same-session market universe, by how much, and over which hold (same day to 40 sessions)?
Does any attribute, alone or in a pre-listed combination, move tickers far enough to clear the long-option breakeven?

## Assumptions (ACK's open build-plan questions, until answered)

- Macro does not enter the ticker forecast (spec §26, CLAUDE.md rule 6).
- Base sample = the market universe in the canonical price database, not the pipeline's own runs.
- Only the underlying is measured here; shares and options are judged afterwards on the same paths.

## Data

`data/canonical/historical_prices.sqlite` (`ohlcv_daily`, Polygon split-adjusted, 23 Aug 2021 – 25 Sep 2026,
3,618 tickers). Known limitations: survivorship (today's universe; delisted names absent); 95 extreme overnight
gaps across 70 tickers (reported with and without them).

## Design (fixed now)

- **Point in time:** each attribute is computed for session *t* from bars up to and including *t* only, using the
  live pipeline's own functions wherever they are pure functions of the bar history (owners named in the results).
  Attributes that need intraday data, option chains, GEX or IV history are out of scope for this replay and listed.
- **Sampling:** every 5th trading session per ticker (reduces overlap and cost); a ticker needs 252 prior bars.
- **Entry and outcome:** entry at session *t*+1 open; signed return at the close of hold day 1…40; first-passage
  labels for the pre-listed target/stop pairs (same-bar double touch = stop).
- **Edge:** signed return minus the mean return of taking the same side on every eligible ticker that session.
- **Chronological split, fixed now:** discovery = sessions to 31 Dec 2024; validation = 2025; untouched test =
  1 Jan 2026 to the last session with a matured 40-session outcome. Attributes and holds are chosen on discovery,
  confirmed on validation, and reported once on test. Nothing is re-chosen after seeing test.
- **Uncertainty:** bootstrap over non-overlapping 20-session calendar blocks (market dependence), 90 % intervals.
- **Success criterion for an attribute (pre-registered):** in discovery AND validation, lift at its chosen hold is
  positive with the 90 % interval above zero; on test the lift keeps its sign; and the share of its signals clearing
  the option breakeven at that hold exceeds the universe's share by at least 5 percentage points.
- **Option breakeven:** as measured on 28 Sep (ATM 45-day / ITM 90-day, 6 % round-trip spread), recomputed per hold
  with realised volatility where historical IV is unavailable; stated as an approximation.

## Addendum before results (29 Sep 2026, written while the replay was running, no result seen)

**Replay source.** Search-before-building found `Enhancements/direction_evidence/discovery_replay_2022_2026.py`
(17 Sep), which already runs the production Discovery scan point in time; its saved output predates the 27 Sep
SOR-001 changes. The study extends a copy (`ticker_edge_replay_20260929.py`): current code, the whole eligible
universe, a global every-5th-session calendar, 40-session paths, past-only data-quality skip.

**Attributes in scope (price-derived, replayable):** Wyckoff phase, precor intent, phase bucket, mode, setup
quality, execution bias, validation status; Crabel state/pattern/compression; control state, dominant trend, EMA
stack, VWAP bias; tier, composite, Discovery horizon; ADX, ATR percentile, volume ratio; the live trigger layer
(`trigger_layer.evaluate_triggers`) and physics layer (`vanguard/physics_state_engine.calculate_market_physics`)
applied to the replayed rows, with their price inputs computed from the same bars and macro left empty.
**Out of scope (need historical option chains):** WBS score/grade, the options IV regime, the EIL verdict. Macro
fields the scan fills from today's file are excluded (look-ahead).

**Signal and baseline.** A signal is a replayed row whose Discovery preliminary direction is CALL or PUT. The
universe baseline is every replayed row that session (all tickers passing Discovery's own filters), same side.

**Pre-listed combinations (the only combinations tested):**
1. trigger RANGE_BREAK, by direction; 2. trigger RANGE_BREAK_EARLY, by direction; 3. Wyckoff phase D with a
CALL/PUT direction; 4. precor BUY_SETUP with CALL and SELL_SETUP with PUT, each with the dominant trend aligned;
5. Crabel READY or COILING with trigger VOL_COMPRESSION; 6. each tier label; 7. physics directional force in the
top third aligned with the direction.

**Option step (approximation, stated).** Historical IV is not available for 2022–2025, so each signal's option is
priced with Black–Scholes at its 20-session realised volatility × 1.10 (a typical implied-over-realised premium),
ITM 5 % 90-calendar-day contract, 6 % round-trip spread, decay per session. The option EV of a segment is the mean
of those path returns; the "share clearing breakeven" is the share with a positive option return.

## Not claimed

No attribute gains any authority, rank or gate from this study (spec rule 5, G1–G4). Results are research evidence
for ACK's decision on what the ticker forecast (C4/C5) should condition on.

## Results (appended 29 Sep 2026 after the run; the design above was not changed)

**Run.** `Enhancements/direction_evidence/ticker_edge_replay_20260929.py`: 263,842 replayed rows, 1,888 tickers, 204
evaluation sessions (2 Sep 2022 – 22 Sep 2026), 10,841 s on 7 workers. Signals (Discovery preliminary CALL/PUT):
about 215,000. Analysis `ticker_edge_replay_analysis_20260929.py`; data in `.claude_scratch/int001/replay_20260929/`
(`segment_results.csv`, `population_by_hold.csv`). Trigger primaries replayed: NONE 166,637, VOL_COMPRESSION 50,052,
RANGE_BREAK_EARLY 36,142, RANGE_BREAK 11,011.

**Pre-registered result: no attribute passes (0 of 97 segments).**

- The Discovery direction has no edge over the same-session market at any hold 1–40 in any period (lift between
  −0.3 % and +0.2 %). The modelled ITM 90-day option loses at every hold for the population (−6 % day 1, about −2 %
  at 40 sessions).
- Discovery-period leaders mostly reverse (e.g. Wyckoff phase A +1.34 % in 2022–24, −1.22 % in 2025).
- 20 of 97 segments have a positive edge in all three periods; all are small (+0.3 % to +3 %), their discovery
  intervals cross zero, and all at holds of 30–40 sessions (bullish Wyckoff structures: spring, buyers in control,
  bias BULLISH, "LONG CONFIRMED phase C", RANGE_BREAK_EARLY & CALL).

**Exploratory (not pre-registered; `ticker_edge_replay_exploratory_20260929.py`).** Option return minus the mean
option return of every signal on the same side and session:

- The bullish Wyckoff structures' option excess is not robust (negative in 2022 and 2024; every interval spans zero).
- Volatility compression is the one consistent effect: low ATR percentile (bottom third) +4.5 % / +4.9 % / +6.0 %,
  compression energy (top third) +4.0 % / +4.6 % / +5.2 %, market energy (top third) +2.8 % / +2.3 % / +3.5 %
  (2022–24 / 2025 / 2026, intervals above zero, positive every calendar year, survives removing extreme gaps). It
  appears for calls and puts alike with ticker lift ≈ 0, so it is a volatility effect, not a directional one. It may
  be partly an artefact of pricing options at 1.1 × realised volatility (real IV on calm stocks usually carries a
  larger premium); it must be checked against real historical option prices before it is believed.
- Absolute option EV is positive only for calls (e.g. +9 % to +10 % for calm stocks at ~39 sessions) because every
  call gained in a rising 2022–26 market (all calls +3 % to +6 %); survivorship bias also favours longs. Puts lose in
  every period.

**Hold.** No attribute shows any edge at 1–10 sessions; the effects that exist build slowly over 30–40 sessions.
Short holds pay the spread without an edge.

**Not tested (need historical option chains):** WBS score/grade, the options IV regime, the EIL verdict — the three
that looked promising in the 28 Sep 18-session study. Phantom chain snapshots exist weekly from about Aug 2025.
