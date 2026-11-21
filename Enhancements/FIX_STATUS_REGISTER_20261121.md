# AVSHUNTER fix status register — 21 November 2026

Read-only audit. Branch `laneb/lab-first-handoff`, HEAD `ff24d41`. No code, data, schedule or provider call was changed or made. No tests or pipelines were run.

## How to read this

Every fix identified in the repo's registers, designs, receipts and briefs was checked against the code, git history and the 19 Nov evening run (`20261119_234734`), not against what the documents claim.

| Status | Meaning |
|---|---|
| **1. Outstanding** | Identified, designed or approved, but no working code exists. |
| **2. Fixed but not implemented** | Fix code exists but is not properly live: uncommitted, on another branch, not called by the run, switched off, producing nothing in real runs, closed by a label only, or waiting on a manual step or real-session acceptance. |
| **3. Fixed and implemented** | Committed on this branch and wired into the running path. |

Three facts apply to every row:

- **Live runs execute the uncommitted working tree.** The 19 Nov run recorded `dirty: True` with a 426 KB code patch. About 220 files are modified or untracked. Items marked "uncommitted" in list 2 are running on this PC but are in no commit.
- **Almost no fix has forward acceptance.** "Fixed and implemented" items have replay receipts at best. I found no outcome-scorer acceptance on forward sessions for any of them.
- **Committed tests were taken as evidence that code exists, not that it passes.**

Sources audited: end-to-end fix design and addendum (Sep), decision path map DM-01..38, Phase 0–8 documents, 25 Sep change register, DIR-002, BEH-001, TEV-001, SOR-001, XLU register, 7 Oct redesign, output-trust items 1–11, trade-quality register (D2…T2), lessons L1–L8 / R1–R10, Lab-004 and source-of-truth validation, options valuation G1–G9 and UAT-01..07, Phantom change list 1–11, tradeability AVS-TRADE-001, ETF reliability E1–E24, Lane B Fix B and `needs_codex`, macro delivery/board/triage documents, and the two Codex plans of 21 Nov (section 4).

---

## 0. The gaps that matter most

These are the items where the paperwork says one thing and the code or the live run says another.

| # | Gap | Evidence |
|---|---|---|
| 1 | **Shadow contract value selection (B1) produces nothing.** Every selected row is `VALUE_INPUTS_UNAVAILABLE`, forecast source `UNAVAILABLE`. | 2,032 of 2,032 rows on 19 Nov; same on 14 and 18 Nov. Cause is the stage order in Codex VOL-02 (section 4). |
| 2 | **Scenario payoffs (C1) are empty on every row.** | `scenario_state = NOT_ASSESSED`, `DOI_SCENARIOS_ABSENT`, 2,038 of 2,038. |
| 3 | **Monetisation clock (A12) is merged but never fed.** | `monetisation_clock_state = UNASSESSED_NOT_PUBLISHED` on 2,746 of 2,746; only an offline CLI supplies the packet. |
| 4 | **Crossing scenario (AVS-TRADE-001 v4) fails on a real session.** | `crossing_state = THESIS_NOT_ACTIVE` on 2,036 rows, 1,952 of which have an ACTIVE Morning thesis. Root cause not traced. |
| 5 | **Sector/USMI alignment (XLU-D03, E2) is dead.** | `UNAVAILABLE` on all 2,746 rows in four runs; the receipt claimed 219 ALIGNED. |
| 6 | **"CONFIRMED" direction with zero evidence (D2) was closed by a display rename only.** | `contracts/direction_governance.py:773-774` still writes `DIRECTION_CONFIRMED`. |
| 7 | **Decisions marked RESOLVED in September that were never built:** no EOD synthetic verdicts (D9), actuarial builder into the repo (D11), catalyst and RS20 direction evidence retired (D2 of the design). | `execution_intelligence_runner.py:346`; no builder tracked; `direction_governance.py:636-672`. |
| 8 | **Advisory publishers can still abort the Evening** (TEV-001 P0a, approved). | `intelligent_orchestrator.py` ~6316–6330 and ~6365–6384 `return False`. |
| 9 | **Missing direction still defaults to CALL in one path** (H2). | `intelligent_orchestrator.py:1761-1765`. |
| 10 | **Universe option chains are missing for 12, 16 and 20 Nov** (SPY and QQQ only), and nothing fails when that happens. | `phantom_pair_health`; readiness is a warning only. |
| 11 | **Phantom score can never reach HIGH or CONVICTION.** Maximum possible score is 67.5 against thresholds of 70 and 85. | `scripts/phantom_engine.py:106-131`; formula confirmed in this audit. New finding from Codex. |
| 12 | **All macro work since 14 Nov is uncommitted** (controlled scheduler, freshness gate, cost cap, triage integration T1–T7). | `Run-MacroSchedule.ps1`, `scripts/scheduled_macro_builds.py`, 9 `contracts/macro_*.py` files untracked. |
| 13 | **Two fixes exist only on other branches.** Lab timing publication (`b48db74`) and the production eligibility gate (`eb50549`). | Not ancestors of HEAD. |
| 14 | **Documents that are stale the other way** (say "not committed" or "open" but are done): G4 and G5 receipts, P0-8 §13, board gap G15, artifact-retention receipt, `pending_us_money_index_fix` folder, the weekend quote-age memory note. | Commits `666f09c`, `c175576`, `23ad527`, `1f37f1c`. |

---

## 1. Outstanding

### 1.1 Run control, reproducibility, hygiene

| ID | Fix | Evidence |
|---|---|---|
| S0.4 | Injected clock in legacy code; no `date.today()` | `avshunter_discovery_ULTIMATE.py:815`, `garch_runner.py:99`, `phantom_engine.py` `score_date` |
| S0.5 / R7 | Replay runner | `intelligent_orchestrator.py:8676` raises on REPLAY |
| S0.7a/b | Config-driven paths; package imports | 60 files hold the hardcoded user path; 108 use `sys.path.insert` |
| P0-3 2a–2c | Single morning path integrity check; research operator mode; quarantine legacy launchers | Not built; launchers and `.bat` files tracked |
| S18.3 / S18.4 / SA-5 | Golden replay of frozen runs; real-run gate after every run; signal-accuracy audit as a recurring check | Audit script last run 14 Sep; not called by the orchestrator |
| R1, R3, R6 | Lint for missing-as-zero; units-in-names check; calibration check on anything called a probability | None found |
| P0-5 / S1.1 / ADD-N6 | Point-in-time universe with delisted names | No code |
| P0-6 / S17.1 | Ledger record contract (C11) | No `c11_ledger` |
| S17.7 | Validation and calibration context (C13) | No module |
| P0-10 | Stale and unservable universe symbols; mixed-date crash | Not fixed |
| P0-11 / S7.1 / D11 | Actuarial builder in the repo, reading the same history store; outliers excluded | No builder tracked; 310 rows over 1,000% not remediated |
| S7.5 / S7.7 | Actuarial staleness gate; retire `actuarial_live_updater.py` and empty sqlite | Refresh still manual |
| PKG-002 P5 / S6 | Delete package mode and its scripts | `packages` mode still at `intelligent_orchestrator.py:653, 3753` |
| F7-skipped | 58 tickers skipped in the daily history backfill | No follow-up |
| TR-022/023, AVS-CHANGELOG-001 (rule) | Shared change log rule in agent instructions; register kept current | Log stops 18 Nov; rule not in `CLAUDE.md` |
| RETENTION-BACKUPS | 710 backup files, none proven redundant | Receipt: 0 deleted |

### 1.2 Discovery, Vanguard, direction

| ID | Fix | Evidence |
|---|---|---|
| D3 / D6 / D19 / OT-11 stations 2–5 / A-step 3 | Legacy Wyckoff phase, trigger category and composite tier out of options score, trap engine, trigger T3, EOD tier | `avshunter_trap_engine.py:114`, `trigger_layer.py:468`, `compute_ois` reads `ctx['phase']`, `eod_candidate_engine.py:2084` |
| DV-6b | Vanguard/EV3 key labelled `LEGACY_STATE_KEY` | Zero hits |
| Redesign Phase 6 | Scenario rules and contributors measured; legacy `assign_tier`, `calculate_win_probability` removed | Still called (`avshunter_discovery_ULTIMATE.py:1550, 1978`) |
| S5.4 / DSC-16 | Wall-clock composite decay and tiers | `date.today()` decay at `:815, 910` |
| D2 (design) / DM-04 | Retire catalyst and RS20 direction evidence | `direction_governance.py:636-672` |
| S4.2 / DM-35 / VNG-10 | Vanguard regime floors and match key still use `macro_regime` | `edge_detector.py:174, 356, 421`; `actuarial_query.py:74, 227` |
| Phase 4 `min_price` | Remove Vanguard `min_price: 10.0` (ACK 4 Oct: no price gate) | `vanguard/config.py:213`; effect not traced |
| S1.3 | `scanner_data_quality=CONFIRMED` hardcoded | `intelligent_orchestrator.py:955, 6306` |
| S2.1 | One bar reader; no stale-cache fallback | `STALE_CACHE` fallback at discovery `:1110` |
| S5.2 | One Wyckoff engine | Dead copy still tracked |
| H2 | Missing direction defaults to CALL | `intelligent_orchestrator.py:1761-1765` |
| DWN-03, DWN-14, VNG-15, DSC-25 | EIL tests `edge_dir in {CALL, PUT}`; enrichment trend vocabulary; `win_probability` seeding; literals in domain code | Still present; some inert |
| VNG-04 / VNG-09 / C-05 | v8 mirrored first-passage labels; per-candidate first-passage statistics | No v8 builder |
| DIR-002 R-1…R-9 | Integrated acceptance of the direction cut-over | Only R-5 run (BEAR failed by 0.002); cut-over made under the 4 Oct waiver |
| DV-1, DV-2, DV-7, A-steps 4–8 | Same-timeframe conflict keeps counter-side; both conditional triggers on the card; contributors as zero-weight fields; nesting; enhancers; Vanguard re-key | Designed 12 Oct; not built |
| N3, N4, B1 (stage design), N1, N5–N10, N12 | Entry-policy registry; entry availability; three state dimensions; reading evidence fields | Modules do not exist |
| T2 | Assessment id | Not found |
| D4a, D5 | Lane C geometry not measured; "pooled probability" (never defined) | Identified only |
| BEH evidence refresh | Duration-evidence builder inside the pipeline | Still offline |
| R5/L4, R7/L8, L6/R9 | Weekend-carry line; next-leg targets; one slot per cluster | Not found. All 18 lessons are still OPEN in `trade_journal.db` |

### 1.3 Options valuation and contract selection

| ID | Fix | Evidence |
|---|---|---|
| G1 | Exit IV from the stored surface, not held flat | `domain/anticipated_move.py:253` `IV_HELD` |
| G2 | Spread model from recorded quotes; exit on the bid | `domain/option_valuation.py:153` |
| G3 / G8 | Fill probability; predicted option price per session, scored against closes | No code |
| G7 | Event-variance split instead of flat IV × 0.8 | `anticipated_move.py:242-258` |
| D2 (valuation) | IV re-implied from the mid (approved 17 Oct, due 24 Oct) | No function |
| M3–M9, G9-extra, G5 switch | Seven remaining Black-Scholes copies onto the one pricer; European/American switch | No owner imports; guard test only stops new copies |
| G6 | DOI dividend basis; exit rule for ITM puts and ex-dividend | Unchanged |
| G4-open a–c | Missing-Greek defaults (θ −0.01, vega 0.05, Δ 0.35); 2,172 unverifiable rows; deep-ITM puts with 300–700% IV | `avshunter_options_intelligence.py:7222, 5753` |
| OT-4b/4c, OT-7a/7b | Callers pass the observed rate everywhere; discrete dividends; wall thresholds calibrated; Morning recomputes walls | Not found |
| S10.1b / DM-18 | Quote freshness measured, not assumed `SESSION_ALIGNED` | `:6519` |
| XLU-D05 | Selection rewards vega regardless of IV level | `:5785` |
| B2 (delta bands), B3, B4, C2 | Delta band pre-selection; long shares as an expression; duplicate hold band; asymmetry constants | Not built |
| OA slices 3–5 | Move-to-return table; implied vs forecast move ratio; slippage and P&L attribution | No code |
| A1 | Selected contract outlasts the hold | Measured only: 1,124 contracts expire before the median move |
| W3, W4 | Pipeline `trade_window_state` and `premium_cap_state` flags (approved 12–13 Nov) | No code; Lane B proxies only |
| E9, E12 | Both index-ETF contract alternatives; ETF review view (approved D-14.3, D-14.4) | No code |
| TR-020 | PUT base rates | `ev_engine_v2.py:92-94` unchanged |
| DM-10, DM-13 / S15.5, S13.4, S13.6 / DM-11, H4, H5, S1-3, S1-5b | Vanguard target = entry price; Morning replaces thesis entry with live price; invented exit targets (1.03/0.97); zero or −1 for missing; target precedence; bid/ask fallbacks; router no-op; DTE buffer units | Lines cited in the foundation audit; all unchanged |
| S12.2 / D9 | No EOD synthetic EIL verdicts | `execution_intelligence_runner.py:346` |
| S12.4, S11.6, ADD §7.1, TEV "cut" items | Retire WBS scoring, monetisation policy copies, SuperBrain passthrough, legacy EV engines, duplicate estimator modules | All tracked. Note ACK's "repair, don't delete" rule |
| TEV P0(a) | Advisory publishers never abort the Evening | Not built |
| TEV Slices C, E, G | C4 base-rate packet; C8 valuation; release proof | `NOT_ESTIMABLE` hard-coded; C8 never valued |
| D-14.7 | Codex code review of the crossing build before commit | Review file absent; `fc5faee` committed anyway |
| Design 15.10 | Measured clock by historical replay | No note |

### 1.4 GEX

| ID | Fix | Evidence |
|---|---|---|
| GEX-D2, D3, D8 | Correct units and net GEX per ticker; replace ad-hoc flip confidence; proximity units | `compute_gex:3257`; `execution_intelligence.py:178` |
| S3.4 / GEX-D10 | Missing GEX never becomes neutral 0.50 | `regime_consensus.py:241-243` |
| S3.6 / GEX-D7, S3.1 / GEX-L4 | Retire the EIL synthetic GEX map; one engine per ticker | `execution_intelligence.py:254, 648` |
| S3.3 | GEX freshness: STALE, not COMPLETE | `build_local_gex.py:203, 219` |

### 1.5 Phantom and options data

| ID | Fix | Evidence |
|---|---|---|
| PH-gap / BF-12Nov | Universe chains missing for 12, 16, 20 Nov (and 28 Sep, 30 Sep, 5 Oct on samples) | SPY and QQQ only on those sessions |
| DF-5 / S2.4 / PF-3 | Run fails loudly, or flags consumers, when capture coverage drops | Warning only |
| S2.3 / ADD-N1 | Fixed nightly capture panel independent of candidates | Not built as an owned job |
| UAT-04, UAT-05 | Weekly maintenance on a legacy-schema database; readiness says FRESH with incomplete Greeks | Unchanged since `7effc2b` |
| PH-6 (cause) | About 1,300 rows per night arrive with no underlying price | Labelled, cause not investigated |
| BF-old, PH-9b | Old backfill runners still unsafe; rehydrate scripts mislabelled | Unchanged |
| D16 / ADD-N2 | IV history depth; daily constant-maturity IV series for 252 sessions | Label only; see Codex VOL-04 |
| F7 (19 Sep) | Options flow half-built (`NO_PCR_DATA`) | `:9875` |

### 1.6 Lane B, ledger, Lab

| ID | Fix | Evidence |
|---|---|---|
| needs_codex 1.1 | Lab publishes the monetisation fields Lane B reads | Names differ; `NOT_PUBLISHED` on 2,593 rows |
| needs_codex 1.3 / A4 | One repair state per row | `lb_repair_conflict` on 459 rows |
| needs_codex 1.5, 1.6 | Publication stage in the manifest; cluster field on the card | Absent |
| B8, B9 | Deep dive starts from the Lab card; fallback contract from Lab alternatives | Launcher unchanged since 20 Oct |
| TR-041 | Option closes carry a session-close flag | No column |
| A11, C1 | Projection issue flag (`NAN:EVENT_MISSING_FROM_PROJECTION`); Lab macro context degraded | Still in the manifest |
| AVS-LEDGER-001 L2–L5 | `card_outcomes.py`, backfill, daily run, summary | Script absent |
| Lab CORS/auth | Open CORS and no authentication (bind is now 127.0.0.1) | `intelligence_lab.py:124` |
| Lab-004 acceptance | Real-run cold-load acceptance, manual proving, ACK release | No receipt |
| ARCH-LB fix list (21 Nov) | Lane B to intelligence-mining list, about 50 items | Marked "nothing to be built yet" |

### 1.7 Macro

| ID | Fix | Evidence |
|---|---|---|
| TRIAGE-T7-DISPLAY | Board template shows the T7 intelligence items | No template code |
| USMI-SCORE-EMPTY | Money Index has no score or components since the 10 Nov rebaseline | ChatGPT side |
| GATE-DIRECT-BUILDER | Direct `build_macro_json.py` call bypasses the freshness gate | Documented limitation |
| STALE-RSP-BREADTH, STALE-DEPTH | RSP breadth not labelled stale on as-of builds; 37 ETFs lack 200-day depth | `macro_board/opportunity.py:40` |
| G10, G16, G17 | Yield split into real/breakeven/term premium on the board; shared-event flag; SPY/QQQ intraday | Series collected, not used |
| REPLAY-HOLDOUT | "✓ holdout" still shown as a positive chip | Template 242–243 |
| MDI-14 | Retire or rebuild `macro_module_contract.json` | Still written |
| XLU-D16, NF-1 | USMI age check; finaliser re-reads macro from the live folder | Not found |

### 1.8 Waiting on an ACK decision

| ID | Decision needed |
|---|---|
| STALE-A / B / C, STALE-BITO | Which fix for the 39 ETFs with no stored prices, and the BITO split (+98% shown on 19 Nov) |
| TRIAGE-11-UNIVERSE | Add 11 ETFs to the board universe |
| FUNDFLOW-SOURCE | A verified ETF net-flow source |
| COST-CAP | Decided by ACK on 21 Nov: USD 4 a day. Tests now read the cap from config; runbook corrected |
| RECOV-FUNDING | API credit shortfall for FULL builds |
| MDI-12 | MOVE, dispersion and correlation measures |
| Dec 4, 5, 7, 8, 9 (AVS-TRADE-001) | Value selection SHADOW→ACTIVE; rank by return per premium dollar; tastytrade live quotes on cards; in-window names first; success tests as expectancy |
| TR-005 | Delayed feed (72–76 min) fails the freshness rule and gives DO_NOT_TRADE on 14, 18, 19 Nov |
| TR-013, needs_codex §4 | Retire the 25% spread test and old-layout scripts |
| BF-A | Wider backfill chains |
| OT-4d | Fee schedule |
| Dev plan v0.2 (AR22, R0–R3, BG01–BG10), Decision Register docx decisions 1–10 | Whole plan is "proposed"; none approved |
| Codex plans (section 4) | Approval of root cause and design before any build |

---

## 2. Fixed but not implemented

### 2.1 Built and wired, but producing nothing in real runs

| ID | Fix | What the run shows |
|---|---|---|
| B1 / `675b5e3` | Shadow contract value selection | 100% `VALUE_INPUTS_UNAVAILABLE` |
| F1 | Legacy vs shadow selection pair | Shadow half empty because B1 is dead |
| C1 | Scenario payoffs on every row | 100% `NOT_ASSESSED` |
| XLU-D03 / E2 | Sector and USMI alignment overlay | 100% `UNAVAILABLE` |
| A12 / W1 | Monetisation clock per row | 100% `UNASSESSED_NOT_PUBLISHED`; run never supplies the packet |
| Design v4 scenario | Per-contract crossing scenario at EOD and Morning | `THESIS_NOT_ACTIVE` on 2,036 rows; 2 assessed |
| A3 | Hold counts down | Remaining = planned on 2,032 of 2,032 |
| A8 / needs_codex 1.2 | Contract alternatives | Published on 2,032 rows; no consumer reads that field name |
| AVS-LEDGER-001 L1 | Stock outcomes on every ledger | Lapsed after 12 Nov |

### 2.2 Label-only or display-only closures

| ID | Fix | What was actually done |
|---|---|---|
| D2 / OT-1 | Stop CONFIRMED direction with zero evidence | Display rename; source still writes `DIRECTION_CONFIRMED` |
| R6 / "expires before the median move" | Contract family by thesis timing | Flag `CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME` only |
| OT-10.1 | Per-setup within-hold rates | Display only; lane and geometry not switched (ACK decision held) |
| R12 / S2.4 / DF-3 | Freshness gate | Report only, never blocks (ACK 19 Sep) |
| S11.5 / O2 / Item 2 | One valuation core | Shadow valuers only, no authority (by rule 5) |
| E11, R3 | Quote provenance | Evening shadow only; Morning unwired |

### 2.3 Built but not the running path, or switched off

| ID | Fix | Evidence |
|---|---|---|
| S0.1–S0.3 / P0-3 inc. 1 / R8 | One launcher, RunContext, pre-flight gate | `avshunter/c0_run/` (`198598a`); runs start with `python intelligent_orchestrator.py` |
| OT-10x | Exact-option outcome capture | Env switch default "0" |
| F2, POB 1, POB 1B | Broker-side quote check; tastytrade read-only bridge | Scripts exist; nothing calls them |
| USMI-VALIDATE-STEP | Validate each USMI packet before the Evening | Script exists; no runner step |
| SOR feature reader, mode/phase key | As-of feature window; `wyckoff_mode_phase_key` | No production importer |
| DSC-01/02/03/07/10/11/12/19/24, VNG-03, `side_assign_v1` | DIR-002 symmetric evidence on the legacy stack | Shadow; stack retired from authority on 7 Oct |
| TEV Slice D, register 9 | C6 in one owner; Morning revision service | Two modules remain |

### 2.4 Only on another branch

| ID | Fix | Evidence |
|---|---|---|
| LAB-TIMING | Timing stage skipped on the trusted-receipt path | `b48db74` on `fix/lab-timing-publication-20261116`; also uncommitted in the working tree |
| TR-016 | Production eligibility gate | `eb50549` on `fix/production-eligibility-20261112` |
| G1 note | IV-surface root-cause note and characterisation test | Untracked in worktree `nice-wozniak-f2ce1d` |
| Phantom findings doc | Change list 1–11 | Untracked in worktree `affectionate-brattain-10941c`; in no branch |

### 2.5 Running locally but uncommitted (macro, 14–20 Nov)

| ID | Fix |
|---|---|
| TRIAGE-T1, T2, T3, T5, T6, T7a–d, PEER, RETENTION | Board per-ETF intelligence file, join to the hand-off, `avs_day` and runner wiring, `check_triage` macro check, Day story names, T7 intelligence, `EW_SECTORS` peer, 10-session clean-up |
| SCHED-CONTROLLED, PREOPEN-1200, POSTCLOSE, EARLYCLOSE | One controlled scheduler, 12:00 UK pre-open, +30 min post-close, exchange-calendar guard. The scheduler is firing from untracked files |
| GATE-FRESHNESS, BUDGET-PAID-SLOT, BUDGET-AXJO, BUDGET-MISSING-CLOCK | FULL build stops on a stale refresh; preflight stops cost nothing; ^AXJO dropped; missing bar clock handled |
| COST-CAP, COST-PROMPT, CASHIDX, FUNDFLOW-CONTRACT | Daily API cap; prompt compaction; cash index collector; fund-flow file contract (no source file yet) |
| RECOV-USMI-PARTIAL, RECOV-CHAT-ALIASES, RECOV-PICKUP | USMI PARTIAL label accepted; producer chat aliases; 10-minute pickup window |
| BOARD-DISPLAY-1117, FRED-TEST | Absolute returns first and stale banner; corrected FRED test |
| IVH-3 | 30-day constant-maturity ATM IV (`_layer3_atm_iv_fields`, `garch_runner._layer3_iv_observation`) |
| avs_verify v1.4 | Phase contract and R24 rule (reports already stamped v1.4) |
| B7 `_b1` path fix | `today_context` paths blank on 20 Nov although the files exist |

### 2.6 Waiting on a manual step or real-session acceptance

| ID | What is owed |
|---|---|
| TRIAGE-T4, USMI-TEXTFLAG-PROMPT | ACK pastes the prompt text into the chat automations; no evidence it was done |
| TRIAGE-E2E | T3–T5 acceptance on one real session (20 Nov context was written after the triage ran) |
| UAT-01/02/03 | Close-capture rules live only in the retired local script; the post-close monitor prompt has not adopted them |
| DELIV-CLOUD, RECOV-PICKUP | Unattended cloud-to-local export not yet observed |
| SCHED-PREOPEN-1200 | First scheduled 12:00 UK run is Mon 23 Nov |
| MPW / Dec 6 | Morning gate any time in market hours: five-session forward acceptance owed |
| E1 (remainder) | Instrument identity first increment is live, but 2,206 of 2,746 rows are `UNASSESSED_CLASSIFICATION_DATES` |
| Open 5 (17 Sep) | Acceptance against reality on forward sessions for the September fixes |

---

## 3. Fixed and implemented

Committed on this branch and wired. Replay evidence only unless stated.

### 3.1 Contract and options

| ID | Fix | Commit |
|---|---|---|
| E1/E2 (Sep), S10.4, DM-16 | Only two-sided contracts within the spread limit | `7210a50` |
| E3/E4, E5, E7, L1–L3, DM-22, S10.6 | Missing prices stay missing; wrong-side contract removed; invalidation side-checked; fields describe the written contract | `45bcd7d`, `ff2c035`, `e0fa763` |
| E6, D3, S9.5, DM-06, XLU-D01 | No invented 3R target; reachable target published | `7210a50`, `d1ee309` |
| R:R removal, XLU-D13 | R:R out of every score and gate | `d1ee309` |
| G4 / D4a / DM-14 / OA 1e | Provider Greeks published; Heston display-only; source labelled | `666f09c` (live: `PROVIDER_EOD_CHAIN` on 2,032 rows) |
| G5 items 1–2, UAT-06/07 | Card and Lane B priced American with the run's live rate; owned CRR tree; `--as-of` | `c175576`, `5b4fc6a`, `245e87c` |
| G9-GUARD | Test blocks any new pricer | `c175576` |
| S10.1c, DM-20, DI Fix 2, XLU-NF-2 | True IV percentile, one owner | `61c16b9`, `f368d47` |
| DI Fix 1b, 3, 4, D5; GEX-D1 | `rr_options` state; side-constrained walls; gamma flip from signed gamma; sizing reads IV percentile | `f9a7985`, `f368d47` |
| OT-3, OT-4, OT-5, OT-6, OT-7 | Geometry block; one card valuation engine; SPY gamma alias removed; IV labels; gamma-weighted walls | `1f37f1c` |
| OA 1a–1d, Slice 2 | Vega risk units; put "too late" check; signed breakeven; EV v2 off display; contract analytics block | `d1ee309` |
| Anticipated move steps 1–5 | Earnings as disclosure; anticipated fields; runway on the anticipated level; "does the move pay" flag | `d1ee309` |
| EV3-OPT3 D1/D2, MEM-swap, MEM-weekend | EV3 at hold plus move window; Morning swap writes new strike/expiry/DTE; quote age is a label | `d1ee309` |
| GARCH-D1 / D13 / TR-008 | Cumulative expected moves at 5, 10, 20 sessions | `3bd7ecf` |
| L3-a/b, V5–V7, DQ-12 | Forecast fallback chain; governed bounds; structural-break history | `202836b`, `db2d807`, `e1ce260` |
| Design v4 shadow, R1, Design 15.7 | Crossing shadow comparison; unrounded return; crossed quote graded C | `fc5faee` |
| Dec 6 / MPW | Morning gate runs any time in market hours | `d1c770c` |
| XLU-D04, D10, D11 | Compression flags rich IV; phase/event categorise only; confirmation needs a material move | `d1ee309` |

### 3.2 Discovery, Vanguard, thesis

| ID | Fix | Commit |
|---|---|---|
| P0-01, 03, 04, 06, 07, 09; redesign Phases 1–5 | One story per thesis; thesis owns side; event triggers; Vanguard as context; no 2,000 cap; drop-off audit | `1f37f1c`, `2efec78` |
| E11b / R11 / O5 | One rank owner `domain/opportunity_rank.py` | `1f37f1c` |
| OT-11 station 1 | Discovery tier, order and horizon from the thesis | `1f37f1c`, `08c5a26` |
| VNG-01, 02, 05, 06, 11, 12, 17; DM-02 | Thesis context into Vanguard; no CALL default; point-in-time query; typed empty samples | `d1ee309`, `1f37f1c` |
| DWN-01, 02, 04, 05, 06, 08, 12, 13, 16 | Options and C5 read the thesis side; retired vote families | `d1ee309` |
| BEH-001 A2-2, R-01..05, C-01..04, C-07, RQ-1/2 | Weekly and monthly timeframes; candidate ledger; no fixed 20-session hold; no price gate | `d1ee309`, `f8dd20a` |
| DSC-13, 15, 20, 21 | Tier-0 never overwrites; typed eligibility codes; scan errors as rows; macro to advisory fields | `d1ee309` |
| `308c166`, `43356a8` / DM-38, `2c224e9`, `dc0e5af`, `2102fd8` / DM-03, DM-27, `39f1ca8` | Field ownership; Discovery owns horizon; sector/momentum inputs; physics on measured inputs; vol regime rule | as listed |
| M-REVIEW-01 | Morning authority from the thesis | `1f37f1c` |
| Phase 8 F1–F5, A-step 2, B4.2 / R1, R3 / L7 | Intraday coverage states and catch-up; OBSERVED/INFERRED labels; event clocks; opportunity ledger | `2efec78` |
| A2, D2, D3 (25 Sep), INT-001 H1/H2 | No-quote label; manifest grain; book-stability diagnostic | `34c0fef`, `8ecb831`, `bb4cf50` |
| OT-8, OT-9, OT-10.2/10.3/10.4, TR-015 | Disposition journal; earnings tiers; station inspections and quarantine; scorecard; forward calibration report | `1f37f1c`, `ff694d7` |

### 3.3 Measurement, data, Phantom

| ID | Fix | Commit / evidence |
|---|---|---|
| P0-2 | Configuration registry (all values PROVISIONAL) | `8635ca1` |
| P0-8, S17.2–4, C4 labels, R10 | Outcome scorer runs after every Evening | `1912f75` … `6d73429` |
| P0-4 slice 1, S2.2, GEX-D9 | Open tickets keep daily marks; chain adapter date rule | `8a4b011`, `5f23e40` |
| P0-1, F7 data, IVH-1 | History backfills (data) | Receipts |
| S2.6, `cdedf20` | IV history every evening; readiness report | `cdedf20` |
| PH-1, 3 (6/7/14 Oct), 4, 5, 7, 8, 10; MEM-backfill | Missing Greeks computed (5.5M rows); provenance labels; every write path completes Greeks and IV; open-interest policy recorded | `7effc2b`, `79c5983`; 0 `PENDING_IV` live |
| IVH-2 / DF-1 | Evening captures about 2,650 tickers on run nights | Since 19 Oct |
| BF-safe, BF-B, BF-path, MR-1111 | Guarded backfill for 20 Oct and 9 Nov; named-contract and path supplements; 11 Nov repair | `79c5983`; receipts |
| GEX fallback | Chain session roll with labelled sentinel | `gamma_exposure_store.py:174` |
| PKG-002 P1–P4c | Manifest mode, package-free Evening | `1a06988`, `913b8ce` |
| Artifact retention | Artifact-level retention | `23ad527` |
| S0.7c, S16.2 | Untracked production import committed; old UI copies quarantined | `d1a1a09`, `43136b1` |

### 3.4 Lab, Lane B

| ID | Fix | Commit |
|---|---|---|
| LAB-004 S1–S3, accuracy 1–6, H1 | Review projection and UI; accuracy fixes; execution-gate columns | `5864ff1` |
| Lab bind | Served on 127.0.0.1 at the root page | `2efec78` |
| B0–B7, B10, TR-012, focus list, X17 tiers (TR-004) | Hand-off built from the Lab; packs; decision records; focus list; 11 Nov tiers | `1e43e6b` … `208e1d2` |
| E1/E17 increment 1, E16 | Instrument identity fields; leveraged/inverse labelled research-only | `4010d4d` |
| AVS-TRACE-001, usmi duplicates | Traceability review; duplicate book columns | `3d460c9`, `4f56bc8` |
| S1-2a/2b | Dead Phantom layer removed; Phantom writes only its own fields | 7 Oct |

### 3.5 Macro

| ID | Fix | Commit |
|---|---|---|
| DELIV-INTAKE, DELIV-USMI-V2, USMI-TEXTFLAG-CONTRACT | Manifest intake and receipts; USMI v2 schema; text flags through a fixed vocabulary | `ca060b7`, `1f37f1c` |
| FRED-TERMPREM, FRED-USSLIND | FRED latest-public-release policy | `ca060b7` |
| Board gaps G1–G9, G11–G15, G18 | Dates, labels, archive, implied move, intervals, holdings, desk card | `46d28f7`, `c086806`, `1789870` |
| REPLAY-H10 | Dollar condition respects its release day | `278d8b8` |
| MDI-P0, MDI-09, MDI-11 | Input manifest and hashes; breadth input; events through the delivery ledger | committed |
| OWN-PER-ETF, OWN-CANDIDATE-MAP, OWN-LOCAL-SPLIT, OWN-LATEST-WINS | Plan and Money Index per ETF with measured correlation; candidates mapped to their ETF; measured sheet local; newest packet wins | `bad3355`, `ca060b7` |
| E1 (25 Sep), D6/D7, Scenario M8 | Unsourced convexity hidden; GEX no longer scales size | `ad04778` |

---

## 4. Codex plans of 21 November (reviewed as requested)

Files: `Documents\Codex\2026-11-21\re\outputs\GARCH_ordering_and_IV_benchmark_fix_plan.txt` (with Appendix VOL-1) and its companion `PHANTOM_root_causes_and_fix_plan.txt`. Both are design proposals. **Every item is Outstanding — designed, awaiting ACK approval.**

### 4.1 What I confirmed against the code

| Claim | Check |
|---|---|
| Forecast runs after Options Intelligence and after EIL; an EIL failure skips it | Confirmed: `intelligent_orchestrator.py:6880-6892` |
| The runner takes its ticker list from the post-OI SuperBrain file and uses `date.today()` | Confirmed: `garch_runner.py:27, 99, 365` |
| The 30-day IV benchmark is computed at one place only, after the early returns | Confirmed: single call at `avshunter_options_intelligence.py:9223` |
| The prior-forecast lookup has no maximum age | Confirmed: `_l3_forecast_on_disk` `:5949` |
| Selector forecast source is UNAVAILABLE on 2,032 rows | Confirmed independently by the change-register audit (B1 dead) |
| Phantom score cannot exceed about 67.5 | Confirmed: `_composite` at `phantom_engine.py:125`; 1 − (0.78 × 0.76 × 0.75 × 0.87 × 0.84) = 0.675 |
| 20 Nov has SPY and QQQ chains only | Confirmed by the Phantom audit (also 12 and 16 Nov) |
| 1,075 missing benchmarks; 426 recoverable from stored chains | **Not re-verified.** Codex's replay figures |

### 4.2 Items and how they map to this register

| ID | Fix | Existing register items it closes or overlaps |
|---|---|---|
| VOL-01 | Freeze contracts, cutoffs, fixtures | S0.2 RunContext (built, not wired) |
| VOL-02 | Price-only forecast before Options Intelligence; current forecast injected into the valuer | **B1, F1** (dead shadow selection); B1 RCA of 25 Sep already named this as the long-term shape; S0.4 clock |
| VOL-03 | Typed IV result at the chain boundary, on every return path | IVH-3 (uncommitted); gap 1 |
| VOL-04 | 1/5/20-session measures; daily IV30 history; IV percentile with honest coverage | D16, ADD-N2, OT-6, DI Fix 2 (existing IV-percentile owner must be reused) |
| VOL-05 | Better ATM estimator (fixed ±5% band fails on 498 names) | New |
| VOL-06 | Horizon-specific forecast challengers; HAR fit-window audit | C3 (validate the forecast), GARCH-D1, Phase 6 IV/HAR-RV finding |
| VOL-07 | One assessment id consumed by OI, C7/C8, DOI, learning | TEV Slice E, O2, C1 |
| VOL-08 | Release and monitoring | Rule 5 gates |
| PHANTOM-A | Normalise the score in shadow; versioned thresholds | New |
| PHANTOM-B1 | Truthful coverage health per session and scope | DF-5, UAT-05, S2.4 |
| PHANTOM-B2 | Bounded, credit-capped recovery of missing sessions; generalise the guarded runner | PH-gap, BF-12Nov, BF-old |
| PHANTOM-B3 | Owned recurring fixed-panel acquisition | S2.3, ADD-N1 |

### 4.3 Review comments before assigning to Codex

1. **The diagnosis is sound and explains a live gap.** VOL-02 is the root cause of B1 producing nothing since at least 14 Nov. That makes VOL-02 and VOL-03 repairs of existing functionality, not new features.
2. **The files it must edit have uncommitted changes.** `garch_runner.py`, `intelligent_orchestrator.py` and `scripts/avshunter_options_intelligence.py` are all modified in the working tree, and the benchmark function itself is uncommitted. Commit a baseline first, or Codex and this checkout will overwrite each other.
3. **Split the package.** VOL-01 to VOL-03 are plumbing with the method unchanged (about one to two weeks by Codex's own estimate). VOL-04 to VOL-06 are method changes and research; they need pre-registered hypotheses and overlap earlier work (7 Oct direction research, Phase 6, branch `claude/ivs-001-iv-surface`, the G1 note). Check those before the brief goes out.
4. **Two points conflict with standing decisions.** The plan gates quote inputs on freshness and adds a maximum-age policy; ACK's rule is to flag quote age, never gate on it. The IV solver fallback must go through the one pricer (`domain/option_valuation.py`), which today has no implied-vol function (D2 valuation, outstanding), and the guard test will reject a new solver elsewhere.
5. **Authority is respected.** Both plans keep selection SHADOW and Phantom evidence-only, and require rule 5 gates before any decision change.
6. **Credits.** PHANTOM-B2 and B3 need an explicit credit cap from ACK; nothing recurring is authorised today. PHANTOM-A and B1 cost no credits.
7. **Rules that apply to Codex too.** Failing test first, characterisation test for the legacy stage order, no pipeline edits while a run is in progress, acceptance against a real session.

---

## 5. Closed by decision or superseded (not counted as outstanding)

| Items | Closed by |
|---|---|
| Strangler contexts C2–C10, C14, RAEV/EV_LB, OpportunityBook, Phases 1–5 of the September design, S18.1–2 | D1 (17 Sep), then TEV-001, DIR-002, BEH-001 and the 7 Oct redesign |
| D4b physics retired | Reversed: physics repaired (`dc0e5af`) |
| D7 hold, A2 planned-hold rule, 5b0d826 | ACK 28 Sep, 4 Oct, 12–13 Nov (hold stays as thesis runway) |
| S4.1, D10/D11 (addendum), E5, DM-34, REPLAY-VERDICT | Rule 6 amendment 20 Nov; "latest macro wins" |
| DM-25 EV3 coverage, D3 (valuation) | EV3 authority stays retired and frozen |
| ADD-N4 borrow data, B3 short side | No short shares |
| F3 sizing, Design 15.8 adoption, PH6 exits | Out of scope or tested with no benefit |
| DSC-04/05/06/08/09/14/17/18/22/23, D1 (25 Sep), SOR S3–S8, WP1 ENV/RAEV | 7 Oct redesign |
| X17-02 25% spread gate, G5 item 4 local close capture | 11 Nov tiers; post-close monitor is the one writer |
| H6, G4-open-d, OT-4a, N11 | Recorded as accepted or deferred |

---

## 6. Not determined in this audit

- **Root causes of the dead outputs** in 2.1 (C1, XLU-D03, crossing scenario, A3). B1 is explained by VOL-02; the others were observed in data only.
- **Items outside the repo:** chat automation prompts, the claude.ai post-close monitor, scheduled-task registration, ChatGPT producers, the research package for the outcome ledger.
- **ACK's original trade-quality register** (pasted 11 Oct) is not a file in the repo. N2, D17 and D5 "pooled probability" have no definition here.
- **Not traced line by line:** S0.6, S15/O6 (one morning service), DM-17/19/21/28, P0-02/05/08, recall losses a–c, VNG-07/14/16, DWN-07/15, GEX-D4/D5/D6, PH-2, PH-9, PH-11, MDI-13/15/16/17/20, E4/E8/E14/E19–E21, ILA-RC-01..08, Decision Register E01–E34.
- **Scheduler deferrals:** 122–185 "DEFERRED: writer active" lines a day on 18–20 Nov; normal contention or a defect is not established.
- **Whether legacy tier and ladder code still reaches the card** after the 9 Oct "legacy classifiers inactive" decision.
- **Uncommitted diffs inside files that also carry committed fixes** were not read, so a cited line may come from the working tree rather than the commit named.
