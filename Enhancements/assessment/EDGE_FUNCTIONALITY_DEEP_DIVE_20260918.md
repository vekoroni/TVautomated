# Deep dive: the functionality needed for AVSHUNTER's edge

18 September 2026 · prepared by Claude Code for ACK · evidence: run 20260918_112522 (1,499 candidates), code
inventory (read-only), backtest ledger trial 8. **This is a proposal; nothing here is approved or built.**

## 1. The edge, and what the functionality has to do

ACK's definition (18 Sep 2026): **enter early and exit into demand, delivered by the whole pipeline working
together.** The edge is the combination of everything: the features, the algorithms and the decision logic (thesis,
trigger, contract selection, valuation, ranking, exits). No single part is the edge on its own. Entries and exits
are both decided by rule. "Pre-herd" is the philosophy, not the
only selection rule. Selection combines structure, direction, contract, liquidity and value.

Three layers, kept separate:

| Layer | Question | Measured by |
|---|---|---|
| Edge mechanism | The whole pipeline (features, algorithms and logic combined) enters early and exits into demand, by rule | The design below |
| Signal quality | Do the pipeline's features see expansion **before** it happens, more often than chance, and how early? | Lead and lift over a matched base rate at 1 / 5 / 20 sessions (available now from stored data) |
| Monetisation | Do long options turn that lead into net returns? | Ticket outcomes over time (later; the 40-ticket test belongs here) |

To deliver the mechanism, the pipeline must do four things:

1. **Detect** a pre-expansion state.
2. **Enter** early, at a sensible price and runway.
3. **Recognise** the herd arriving.
4. **Exit** into it.

## 2. Where the pipeline stands today

| Stage | What exists | State on 18 Sep |
|---|---|---|
| 1 Detect | Crabel/NR7 compression, ATR percentile, Wyckoff phase and events, trigger layer, HAR-RV forecast, IV rank, convexity score, put/call OI, GEX walls, sector rotation, actuarial probabilities, physics "energy" | **Computed, but mostly flat, defaulted or lost before the ticket stage** (§3). **None of it affects ticket rank.** |
| 2 Enter | Morning live re-quote, ticket valued at today's premium (now calibrated to the market), runway floor, 25% / 10% spread limits, daily top 5 + watchlist | **Working** (fixed 17–18 Sep) |
| 3 Recognise the herd | Morning volume anomaly (NO_DATA on every row), a separate exit engine with four non-volume rules (not wired in) | **Missing** |
| 4 Exit into it | Tickets exit on stop, target, 20 sessions or last usable session | **Missing:** no expansion-driven exit |

**The ranking key works against the mechanism.**

- Tickets rank by cautious value alone. Once the dividend error was fixed (22761ee), no candidate had a positive
  cautious value, and the top places went to contracts that lose little.
- XLP ranks 4th with a stop 0.3% away and even its best case at −5.9%. That rewards capped losses, not early
  entries with upside when the crowd arrives.

## 3. Defects that hide the features we already have (verified on the 18 Sep run)

| # | Defect | Evidence | Effect |
|---|---|---|---|
| F1 | **Volume hand-off broken** | Discovery computes `volume_ratio`; options intelligence replaces it with 1.0 on all 1,499 rows (`options_intelligence.py:4128`) | Volume confirmation is "AVERAGE" on every row; the convexity score is 2.0 on every row (it reads the defaulted volume and sector); the morning volume anomaly is "NO_DATA" everywhere |
| F2 | **IV history dead or mislabelled** | `iv_direction` is STABLE and `iv_accel_detected` False on every row (it reads `runs/<run>/iv_history.json`, which is never written). "IVP" places today's IV inside the *realised*-vol range, so it is not an IV percentile. `iv_surface_history` stops at 4 Sep | No real "IV cheap / IV rising" signal |
| F3 | **Actuarial compression probabilities empty** | `layer2__outcomes__prob_breakout_if_compressed` (and the buyers/sellers-control probabilities) NaN on all rows; `layer2__vol_regime` NORMAL on all rows | The statistical layer never sees compression |
| F4 | **Trigger timing synthetic** | `days_to_trigger` is a fixed bucket (3/5/8/10) taken from the Crabel state; `trigger_score` takes two values (55/0); no distance-to-breakout field; freshness UNKNOWN | "How close is the move" is not measured |
| F5 | **Relative strength and sector rotation missing** | `sector_rotation_state` MIXED on every row; `sector_5d_return` filled on 69 of 1,499; no per-ticker RS vs SPY or sector | Leadership emerging, the classic pre-herd tell, is invisible |
| F6 | **Rich detail stops at discovery** | Crabel reaches the morning file only; Wyckoff events (spring, SOS, absorption) and transition probabilities never reach the book, options or morning files | Structure detail is unavailable downstream |
| F7 | **Options flow half-built** | Volume put/call "unavailable" although `chain_snapshots.volume` is populated (~50% of contracts have volume); O2 (call–put IV spread) hard-coded UNAVAILABLE | Flow-based early signals are missing |
| F8 | **Physics state on defaults (to verify)** | Inventory reports `physics_data_quality = DEGRADED_DEFAULTS` upstream | "Energy / entropy" states may be placeholders |

These are data-plumbing fixes, each small, and each a prerequisite: measuring a feature that is constant tells us
nothing.

**Known and accepted (ACK, 18 Sep 2026):** the column `dte` means two different facts. In the Discovery and
Vanguard files it is the target runway in days (30/38/45 on 18 Sep); in the options output and everything
downstream it is the chosen contract's days to expiry (29/64/92). ACK accepts this in production as long as it is
known. Read `contract_dte` when the contract's expiry is meant.

## 4. Components needed

| # | Component | Purpose | Reuses | Type |
|---|---|---|---|---|
| **P1** | **Point-in-time feature set:** compression (NR7/NR4, ATR and Bollinger-width percentile), relative volume and volume dry-up, RS vs SPY and sector, a true IV percentile, IV vs HAR forecast, option volume and OI change, call–put IV spread, distance to trigger level | One owner computes the stage-1 facts from stored data with the evidence-session cut-off | Price store (daily OHLCV since Aug 2021), `chain_snapshots` (volume, OI, IV), existing discovery / Crabel / Wyckoff code | Fix-in-place first (F1–F7), then a feature table |
| **P2** | **Expansion-event labeller** | A governed, pre-registered definition of "the herd arrived" at 1, 5 and 20 sessions (range, volume, IV and move vs the name's own normal) | C12 outcome context (`passage.py`) | Config plus C12 extension |
| **P3** | **Lead and lift measurement** | For every feature and the selection as a whole: expansion rate vs a matched base rate, lead time, direction given expansion; a standing daily report | C12 `base_rate.py`, backtest ledger (trial counter) | C12 extension, research status |
| **P4** | **Scenario detectors → one ranking** | Structural, compression, cheap-volatility and flow scenarios propose candidates with tags; one ranking; a scenario earns weight only through P3 lift | `compute_convexity_score_oi`, trigger layer, O2/O4 | Design (multi-scenario, agreed 18 Sep) |
| **P5** | **Ranking key redesign (D3)** | Rank on upside when the crowd arrives, adjusted for risk; not cautious value alone. Candidates to test: central value, upside-to-loss ratio, value per $ at risk, P3 lift | Value model (now market-calibrated), backtest ledger | Decision D3 + ledger trials |
| **P6** | **Herd-arrival monitor and exit** | For each open ticket, daily: relative volume, range expansion, IV jump; an exit rule of "sell into expansion" | P0-4 daily marks (merged), price store, `plan_exit` | Exit-policy variant on the ledger, then a decision |
| **P8** | **Macro context record (informs, never scores)** | Macro and regime state recorded point-in-time on every candidate in the ledger, shown on tickets and in the Lab, and used to measure results by regime. It never adjusts a score, rank or gate (rule 6). The AVSHunter Transmission Board plugs in here when connected. The two unmeasured score effects (options score −3, EV v2 regime factor) are removed only on separate ACK approval; the data flow stays | Macro packet archive, decision ledger, Lab | Design (ACK 18 Sep) |
| **P7** | **Lab display of state** | Each candidate and open ticket shown as pre-expansion, crowd arriving or crowd arrived, with the features behind it | Lab tickets tab (f057ba5) | Display only |

## 5. Rules that keep this honest

- **Rank, don't gate.** No feature, scenario or exit rule gains a say until P3 shows stable lift over the base rate.
  Until then it is displayed, labelled research.
- **Fixed before looking.** Event definitions and pass rules sit in the governed registry before results are read;
  every test increments the trial count.
- **Point-in-time only.** Features use data up to the evidence session; intraday (4 sessions stored) waits until
  history exists.
- **Horizon.** The product stays on the 1–20 session window (D2). Intraday and 6-month trading are a later
  enhancement.

## 6. Build order

| Step | Item | Depends on | Needs ACK |
|---|---|---|---|
| 1 | Plumbing fixes F1–F7 (test-first, one at a time), F8 verified | — | Root cause per item (evidence above) |
| 2 | P2 expansion events (governed) + P3 lead/lift report on stored history | 1 | Event definitions |
| 3 | P5 ranking-key trials on the backtest ledger (central, upside/loss, value per $ at risk) | Calibration fix (done) | Decision D3 |
| 4 | P6 herd-arrival exit variant on the ledger, compared with stop/target/time | P0-4 (done), 2 | Decision D4 and an exit-policy decision |
| 5 | P4 scenarios feeding the ranking, only those with lift | 2, 3 | Adoption per scenario |
| 6 | P7 Lab state display | 2, 4 | Display design |

Steps 1–2 give the first real answer to "does our functionality see the move before the crowd?" from data we
already hold. They can run alongside the weekend backfill.

## 7. Unchanged

- Tickets, the watchlist and the ledger.
- P0-4 capture.
- The calibrated valuation.
- Macro stays display-only.
- No capital authority.
