# AVSHUNTER feature map · 14 Nov 2026

Written by Claude Code for ACK after validating and committing the uncommitted work (tip `3d460c9` on `laneb/lab-first-handoff`).
Each feature: what it does, why it exists, and where it stands today. Functions are taken from each module's own description and from the 14 Nov review (`audit\trace\AVS-TRACE-001\`); they were not each re-tested here.

State words: **Running** = in the code a run uses now. **Committed today** = was uncommitted until 14 Nov, now on the line, not yet proven on a run. **Branch only** = built, not on the line. **Not built** = decided or proposed only.

Nothing in this map is proven on a run since the 14 Nov commits. The last completed run is `20261111_231951`.

## 1. Run control and safety

| Feature | What it does | Purpose | State |
|---|---|---|---|
| Orchestrator (`intelligent_orchestrator.py`) | Runs the Evening stages in order (scanner intake, Discovery, validation, Vanguard, PHANTOM scoring, Options, Execution layer, trade book, GARCH, EOD candidates) and the Morning workflow; pins one run folder per run | One command per run; every output tied to a run ID | Running |
| Plan-only mode (`--plan-only`) | Shows what a run would do, with no provider calls and no file changes | Check before spending credits | Running |
| Station inspection and quarantine (`domain\station_inspection.py`) | Checks each stage's output (prices positive, quotes sane, identity, lineage, timestamps). One bad row is set aside with a receipt; a systemic fault stops the run | A single bad ticker no longer costs the whole book (12 Nov run stopped on RBOT) | Committed today (`ff694d7`) |
| Drop-off audit (`dropoff_audit.py`) | Follows every ticker from the universe to the Morning result and records where it stopped and why | Nothing disappears silently | Running |
| Run verifier (`tools\avs_verify\avs_verify.py`) | Reads one finished run, applies fixed rules (timing, row counts, quote age, verdict conflicts), writes TRUST / CAVEATS / DO_NOT_TRADE | An independent check that does not import pipeline code | Running; separate start and completion clocks committed today |
| Production eligibility | Refuses a standard production run on uncommitted code | A run always cites a known commit | Branch only (`eb50549`) |
| Governed constants (`config\governed_constants_v1.json`) | Holds thresholds, bands and approvals with their evidence | One owner per number; no literals in logic | Running |

## 2. Finding candidates

| Feature | What it does | Purpose | State |
|---|---|---|---|
| Universe and scanner intake (Phase 0) | Loads the liquid universe (about 3,300 tickers) and adds scanner tickers even when outside it | Wide coverage; scanned names always run | Running |
| Discovery (`avshunter_discovery_ULTIMATE.py`) | Scores every ticker for early positioning, tiers them, runs the Wyckoff/Crabel state reading, writes candidates and a lifecycle record | Find names before the crowd | Running |
| Macro horizon router (Phase 1B) | Tags each candidate with a horizon context from the macro packet | Context only; macro never gates, scores or ranks | Running |
| Quality validation (Phase 2) | Checks Discovery output for completeness and consistency | Bad inputs stopped early | Running |
| Vanguard thesis and structure | Builds the thesis per ticker: structure phase and event, trigger, anticipated level, direction governance, actuarial history match | Turn a candidate into a stated thesis with a level and a side | Running; PUT base rates and dropped match dimensions are open defects |
| Trade lane and thesis category (`domain\structure_behaviour\`) | Labels each trade by Wyckoff phase and behavioural event on its own side | Says what kind of trade it is; no "observe" bucket | Running |

## 3. Timing and size of the move

| Feature | What it does | Purpose | State |
|---|---|---|---|
| Anticipated move (`domain\anticipated_move.py`) | States side, level, median and q80 arrival time, path and payoff against premium; replaces stop-based R:R | One owner for "how far, how fast, does it pay" | Running; display only |
| Forward variance, GARCH (`layer3_forward_variance.py`) | Forecasts realised volatility per ticker and publishes expected moves for 5, 10 and 20 sessions as cumulative windows | Size targets to what the stock can actually do | Committed today (`3bd7ecf`): the 10- and 20-session figures were differences between windows until now |
| Exact session clocks (`domain\trade_timing.py`) | Counts hold, expiry and exits in exact NYSE sessions from the row's saved evidence date; the hold counts down; no date invented from the run day | Runway and exits are right across holidays and stale rows | Committed today (`ffcdbbe`) |
| Monetisation clock (A12) | Measures how many sessions the exact contract took to first show +20% and +30%, on saved quotes | Choose the contract from when it pays, not from when the thesis completes | Branch only (`b709669`); gives a figure for 39 of 2,800 rows |
| Trading-window flag (1–20 sessions) | Marks each row in or out of the window | Day and swing focus without dropping rows | Lane B only, on a proxy; pipeline flag not built |

## 4. Choosing and valuing the contract

| Feature | What it does | Purpose | State |
|---|---|---|---|
| Options intelligence (`scripts\avshunter_options_intelligence.py`) | Fetches the chain (MarketData), selects one long call or put per thesis, records runway, spread, Greeks and liquidity facts | The expression of the thesis | Running. Selection by value is in SHADOW; the horizon informs choice, it does not gate |
| Options candidate lane (`scripts\options_candidate_lane.py`) | Prices the other theses for the same ticker, each with its own context | Alternatives, without leaking one thesis into another | Running; isolation fix committed today |
| One valuation engine (`domain\option_valuation.py`) | American pricing with dividends and the run's observed rate, for both lanes; a guard test fails on any new pricer | One answer to "what is it worth" | Running. `strategy_layer.py` (Lane B, uncommitted) breaks the guard |
| Liquidity lifecycle (`domain\option_contract_liquidity.py`) | Separates three questions: is the thesis valid, is this contract executable now, will it mature into a tradable one; adds exact runway check | Stops "illiquid now" being read as "bad idea" | Running; runway check committed today |
| Option walls (`domain\option_walls.py`) | Gamma-weighted call and put walls by expiry basket, separated from dealer influence | Shows where price may stall | Running; display |
| EV engines (EV v2, EV3 shadow) | Expected-value estimates from actuarial history and barrier outcomes | Research evidence only | Running without authority (CLAUDE.md rule 5) |
| Liquidity tiers (A/B/C, 11 Nov) | Grades a quote by spread, open interest and width | One standard for "can I trade it" | Lane B only; six other limits still in pipeline config |
| Contract alternatives on the card | Two or three other contracts with quote and fit | A fallback when the pick is untradeable | Not built (fields prepared) |

## 5. Ranking, book and Morning

| Feature | What it does | Purpose | State |
|---|---|---|---|
| One rank owner (`domain\opportunity_rank.py`) | Orders the book by lane, readiness and expectancy; blocked rows sink | One ranking, never a gate | Running |
| EOD candidate engine and trade book | Turns the enriched output into the Morning candidate manifest and the final opportunity book | The frozen evening book | Running |
| Exit rules (`scripts\exit_rules_engine.py`) | Writes target, stop, theta date and time stop per row, from the saved evidence date | Every idea has an exit before entry | Running; clock fix committed today |
| Morning gate (`morning_gate.py`) | Re-quotes the selected contract after the open, re-checks thesis, liquidity and runway, gives GO / FLAG / block | Confirm the evening idea is still buyable at today's price | Running. **From today it runs at any time in market hours** (`d1c770c`); 09:35–09:45 ET is a label, not a limit |
| Morning hand-off finaliser | Builds the downstream files from the Morning rows and reconciles counts; no provider calls | One consistent hand-off | Running |

## 6. Intelligence Lab (the screen ACK reads)

| Feature | What it does | Purpose | State |
|---|---|---|---|
| Lab control and publication (`contracts\lab_control.py`, `lab_review_projection.py`) | Validates the book and publishes an immutable, revision-pinned review; a page view never calculates | What you see is what the run decided | Running |
| Trade card | Thesis, level, hold, contract, evidence status, earnings disclosure, reliability fields | One card per idea | Running; contract details, short-horizon and trade-timing sections committed today (`c213a92`) |
| Convexity watchlist | Saved-data list of high-payoff setups; research only | Surface asymmetric payoffs without changing decisions | Running |
| Lab macro desk and Market Mentality | Shows macro context beside the book; Worker 3 is retired and kept | Context for manual review only | Running |

## 7. Data

| Feature | What it does | Purpose | State |
|---|---|---|---|
| Price store and canonical data system | Holds daily bars and run-bound data with identity and lineage; providers load lazily | Reproducible inputs | Running |
| PHANTOM options store (`scripts\phantom_*.py`) | Stores historical chain snapshots, IV surface and scores; guarded backfill with a credit budget; "path complete" needs usable quotes | The history that outcome and monetisation measurement depend on | Committed today (`79c5983`). 13 Nov backfill: 466,193 rows, 6,205 credits; 12 Nov still missing |
| Actuarial history (v7) | Daily state and forward outcomes per ticker since Nov 2021 | Base rates for theses | Running |

## 8. Macro (display only)

| Feature | What it does | Purpose | State |
|---|---|---|---|
| Macro inputs runner (`Run-MacroInputs.ps1`) | Runs the producers (FRED, liquidity, VIX, GEX, bonds, rotation) on schedule and on demand | Fresh measured inputs | Running; delivery and publication guards committed today (`ca060b7`) |
| Macro packet builder (`build_macro_json.py`) | Builds the macro packet from measured files plus the advisory research files | One macro record per run | Running |
| US Money Index | Reads the advisory money-flow file, routes sectors, handles missing values explicitly | Money-flow context | Running |
| ETF macro board (`macro_board\`) | Stand-alone board: conditions, per-ETF analog odds, next-session plan, events in source-time order | Read the market before the session | Running; event ordering and session plan committed today |
| Source health | Separates "fetched recently" from "the observation is old"; records recovery | Know when macro is stale | Committed today; two of its tests fail and are left uncommitted |

## 9. Lane B: from the book to a trade (ACK's desk)

| Feature | What it does | Purpose | State |
|---|---|---|---|
| Lab-first hand-off (`build_lab_handoff.py`) | Copies the Lab's publication and adds flags (window, time fit, liquidity tier, cap, stock tier), an order and batches | Triage starts from what the pipeline decided | Built and tested; live flow still on the old chain |
| Ticker packs | Bars, card and evidence per ticker for a deep dive | Everything needed to mine one name | Running |
| Triage check (`check_triage.py`) | Checks the unattended triage output before any deep dive | Catch a bad triage early | Running |
| Deep-dive cards and decision records (`collect_decisions.py`) | One card per mined name; one decision record per card; order-ticket sheet | A trade exists only with a card and a recorded decision | Running; a record for every card built 12 Nov |
| Pre-close scan and monitors | Which theses confirm on today's close; open, pre-close and post-close checks; daily option closes | Act inside the trigger session; record what happened | Running; exits and "criteria met, no order" keep being reported |
| Strategy layer (`strategy_layer.py`) | Scores each hand-off thesis S1–S6 | Extra context per name | Uncommitted: it carries its own pricer and fails the pricer guard |

## 10. Measurement

| Feature | What it does | Purpose | State |
|---|---|---|---|
| Outcome scoring C12 (`avshunter\c12_outcome\`) | Scores recorded predictions against what the market did | Fixes are accepted on outcomes, not on code | Running |
| Stock outcome tracker (`track_outcomes.py`) | Tracks every ledger row, traded or not | No selection bias | Last run on the 14 Oct ledger; six ledgers unscored |
| Card outcome ledger (AVS-LEDGER-001) | What the option on every card did over the hold | Know which cards pay | Not built |
| Model research package (AVS-MODEL-001) | Pre-registered tests of whether held data predicts direction or tradeable moves | Evidence before any model gets authority | Research only; step 3 done, no edge in baselines |

## What is still not on the line

- Monetisation clock (A12) and production eligibility remain on their branches.
- Not committed, with reasons: `data\scratch\workaround\strategy_layer.py` (own pricer), `tests\test_macro_completion.py` and `tests\test_macro_refresh_reliability.py` (one failure each), `tools\auction_mining.py`, `export_card_bars.py`, `journal_real_fill.py` (no tests), research and evidence folders, data.
