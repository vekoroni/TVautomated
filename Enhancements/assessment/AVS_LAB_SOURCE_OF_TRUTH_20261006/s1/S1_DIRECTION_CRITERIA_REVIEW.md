# Direction criteria review (7 Oct 2026, ACK: "revisit the direction criteria … ensure the logic is applied correctly and the directions identified are correct")

Read-only. No code changed.

## 1. The criteria as built (production `beh001_v1`)
1. **Readings.** BEH-001 reads 1mo, 1w and 1d bars (plus stored intraday) into **setups** ("candidates"). Each setup has a side (BULL / BEAR / none), a state, a trigger, an invalidation and an outcome level.
   - **States:**
     - `DETECTED`: the setup has formed, but its trigger has not been accepted yet;
     - `ACTIVATED`: the trigger has been accepted;
     - `FAILED`: the invalidation has been accepted;
     - `OUTCOME_REACHED`: the level was reached after activation;
     - `MONITOR`: no direction.
   - State changes need **acceptance** (`signals._state_detail` with `acceptance(...)`), so a state can lag the price.
2. **Trade side: only the daily reading decides** (`engine.handoff_thesis`). "Live" means a directional setup in DETECTED, ACTIVATED or CONFIRMED.
   - **No daily live setup:** `UNASSIGNED / NO_DIRECTIONAL_CANDIDATE`. Higher timeframes are *not* used; that rule failed its holdout test on 2 Oct.
   - **All daily live setups on one side:** that side. The "primary" setup is ACTIVATED before DETECTED, then alphabetical ID.
   - **Both sides live on daily:** walk the higher timeframes. The first timeframe with live setups decides, if it is one-sided. Otherwise `UNASSIGNED / CONFLICTING_DAILY_CANDIDATES`, or `RANGE_EDGES_TWO_SIDED`.
   - **What does not count:** setups are not weighed (count, age, state or evidence), nothing is checked against the current price (a setup already past its invalidation still counts), and trend context (moving average, ADX, ROC, distance to highs and lows) plays no part.
3. **Downstream.** `legacy_direction_adapter_v1` maps BULL → CALL and BEAR → PUT and builds the geometry. Direction governance freezes it; later stages can challenge it but never flip it. Vanguard and the other legacy inputs have no vote (DIR-002, measured: no evidence).

## 2. Is the logic applied correctly?
**Yes.** On run `20261006_060401` the production rule was recomputed from the stored setups for **1,814 of 1,814 tickers, with 0 mismatches** against the published `thesis__side`. The code does what the criteria say.

## 3. Are the directions it identifies correct? What the record already shows
| Evidence (existing studies) | Result |
|---|---|
| DIR-002 replay: 376 direction inputs, 2022–26 (`direction_replay_evidence.json`) | 374 show NO_EVIDENCE. The old Discovery direction label had a 50.9% hit rate. Robust: only `baseline_past_return_5` (negative, i.e. 1-day reversal) and `pct_from_52w_low` (positive) |
| Activated BEH-001 setups, signed forward move at 5, 10 and 20 sessions (`analysis_v2.json`) | Mean ≈ 0, with the 95% CI including 0; favourable touch ≈ 30% |
| Two-sided → higher-timeframe rule (in production since 1 Oct) | +2.1 pt in sample, **+0.5 [−1.0, +2.0] on the holdout: not replicated** |
| Empty daily → higher timeframe | +0.0 on the holdout; rejected, not built |
| Lane A "level before invalidation" (`beh001_lanes_v1.json`) | 55–65% on both panels. This is a geometry outcome (level vs invalidation distance), **not a direction test** |

**Conclusion.** No study has yet shown that the assigned side beats same-day drift at "which way does price go first". The edge that is measured is per setup and conditional (lane A level-before-invalidation). The direction itself is not validated.

## 4. Why a chart reading "finds" a direction the pipeline does not (MSFT, 6 Oct)
The reading of ACK's screenshots used four things the rule does not:
1. **Current price against each setup.** The only bearish setup (Upthrust, invalidation 522.85) was already beyond its invalidation at 525.18, and both bullish SOS → LPS triggers (517.78) were already crossed. The states lag because of acceptance.
2. **Weight of the evidence:** three bullish setups against one stale bearish setup.
3. **Trend context:** price above a rising MA5, rising ADX (daily 39, weekly 30), ROC above its average, fresh highs, contracting ATR.
4. **Location:** near the 535.69 / 550.01 highs.

**But the chart reading is also unvalidated.** Of these, only distance from the 52-week low (location) has measured support, and short-term past return points the *other* way (reversal).

On run 20261006, removing setups already past their invalidation or level resolves only **16 of 249** two-sided tickers (MSFT among them). The other 232 are genuinely two-sided.

## 5. Proposed next step: one pre-registered direction study before any build
**Design** (rules fixed before results are read; same method as the 1–2 Oct studies):
- **Population:** eval_v4 (fit) and eval_v4_holdout (test) ticker-cuts.
- **Outcome:** first touch of ±2 daily ATR within 60 sessions, compared with same-cut drift; date-block bootstrap; also k = 1 and k = 3.

**Rules tested, each as a side picker:**
- **R0 (today):** the production rule. This is the first ever accuracy measurement of the assigned side itself.
- **R1:** R0 on a *price-checked* live set. Setups past their invalidation or level are dropped, and setups past their trigger count as activated.
- **R2:** R1 plus evidence-weighted tie-break: the side with the stronger best setup by lane hit rate, then state, then distance; abstain on small margins.
- **R3:** trend context alone: price against the 20-day MA and its slope, 20-day ROC against its average, distance to the 52-week high and low.
- **R4:** R1 or R2, using R3 only to break ties.

**Adopt only if** the holdout excess at k = 2 has a 95% lower bound above 0, and the point estimate is positive in both periods on both panels (the same bar the 2 Oct rules faced).

**Output:** whether *any* side rule is better than drift, which one, and its coverage. Only then is a build designed.
