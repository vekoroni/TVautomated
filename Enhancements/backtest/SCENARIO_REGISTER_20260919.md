# Backtest scenario register — why the pipeline is not yet monetisable, and what to test

19 September 2026 · v2 · ACK instructions: backtest the pipeline **as is**; evaluate alternative scenarios **inside
the backtest only** until a way forward is agreed; the plan must address **every reservation** about why the
pipeline is not monetisable. Nothing here is implemented in the pipeline. Definitions, populations, measures and
pass criteria are fixed here **before** any scenario result is read. Every run is a ledger trial
(`Enhancements/backtest/ledger/run_ledger.py`) and counts toward the multiple-testing controls.

Sources of the reservations: `Enhancements/assessment/MONETISATION_BLOCKERS_20260918.md` (M1–M11),
`SIGNAL_TICKET_BACKTEST_20260917.md`, `EXIT_RULE_STUDY_20260917.md`, the 18–19 Sep fix work and the anticipatory
design thesis (M12–M24).

---

## 1. Populations

| Id | Population | Source | Judges |
|---|---|---|---|
| H | Recorded evening books 31 Aug–16 Sep 2026 (**pre-fix pipeline**), today's ticket rules and calibrated valuation | `signal_ticket_backtest_rows.csv` (frozen, sha-checked) | Rules applied to the old candidates only |
| H+ | H plus the 1,786 legacy recommendations re-scored after the weekend Phantom backfill | backfill + `legacy_signal_scoring.py` | Larger sample for exits, eligibility, spread |
| U | Recorded Discovery books, underlying only (price store since Aug 2021; books where recorded) | canonical price store | Direction, lead time, anticipation — no option data needed |
| N | Evening runs on the **fixed** pipeline, from the next run; outcomes mature over the following sessions | run outputs + outcome ledger + open-record marks | Everything this week's fixes changed |

Results from H never judge the fixed pipeline; N does. A scenario is only proposed for build when it passes on the
historical population **and** keeps its sign on N.

## 2. Standard measures and pass criteria (apply to every scenario unless stated)

- Option layer: mean, median, share profitable, share ≥ +100%, mean issue-day portfolio return, max drawdown, under
  three fill models (quoted / timed / mid).
- Signal layer: forward underlying return in the thesis direction at 1 / 5 / 20 sessions, hit rate, expansion-event
  rate, each against a matched base rate.
- Ranking: Spearman correlation with realised return; rank-bucket means (1–5, 6–10, 11–25, 26–50, 51–100, 101+);
  monotonicity.
- **Pass criterion (pre-registered):** paired difference versus the "as is" baseline on the same trades with
  t ≥ 2.0 on the historical population, **and** the same sign on N once N has ≥ 40 closed results. Anything else is
  "no evidence", never "fail forward".
- Every trial is counted; Probability of Backtest Overfitting and the deflated Sharpe ratio are reported once ≥ 10
  trials exist in a family.

## 3. Reservation map — every reason the pipeline is not monetisable

| # | Reservation | Evidence | Status after 17–19 Sep fixes | Tested by |
|---|---|---|---|---|
| M1 | **No demonstrated direction skill** (~51%) — the root cause | Direction studies 2022–2026; H9; O1–O5 | Open | S-DIR-1…5, S-EXP-1 |
| M2 | Issuing gate rejected every large winner | 20 of 2,992 kept, all big winners rejected | **Fixed** (rank, not gate; daily cap) | Baseline on N |
| M3 | Stop at ~0.6 expected moves — noise stops trades in 2 sessions | 20/21 tickets stopped; no-stop +2.9 pts, t = 3.21 | **Open** (plan_exit still uses the underlying stop) | S-EXIT-2, S-EXIT-3 |
| M4 | Contract expires before the planned hold | Median 0.54 of hold covered; expiry cap the most common exit | **Fixed 19 Sep** (runway floor = planned hold, 40 days) | S-RUN-1, S-RUN-2 |
| M5 | Execution cost — spread consumes the premium | Legacy ~35% round trip; OTM 73–120% of mid | **Partly fixed** (single 25% selection limit; 10% ticket limit) | S-COST-1…3 |
| M6 | The convex tail is not in the instruments bought | 2.24% ≥ +100%; chains only 8–45 DTE historically | Partly (selector now buys 64–92 DTE; chains to 110 DTE) | S-CONV-1, S-CONV-2 |
| M7 | Missing data (delayed quotes, flow, long chains, event calendar, half the universe) | Provider entitlements | Open; some capture started | S-TIME-1 (quote delay); others not testable yet |
| M8 | Data integrity (GEX algorithm and invented GEX map, corporate actions, money index) | GEX investigation | Open (GEX still reaches size and exit) | S-ABL-3 |
| M9 | Gate architecture produced empty days | 0 actionable on 17 Sep | **Partly fixed** (daily tickets); 430 FINAL_ACTION_BLOCKED remain, allowed if understood (CI) | S-ELIG-1…3 |
| M10 | Nothing validated forward | Forward gate 40 tickets / 15 sessions | Running | Forward record (N) |
| M11 | Product framing — expectancy vs "alerts with winners" | 2.24% ≥ +100% | Open (strategic) | S-PORT-1, S-PORT-2 |
| M12 | Ranking key favours capped losses, not asymmetry | Cautious rank 0.518 vs central 0.429; XLP-type tickets | Kept (evidence) | S-RANK-1…5 |
| M13 | Valuation shows negative value almost everywhere | Central negative on most rows | Open — **the path model has no drift: it is a cost model and cannot show value without a measured edge input** | S-VAL-1, S-VAL-2 |
| M14 | Direction contradicts Wyckoff structure (163 rows unvaluable) | 18 Sep | Labelled 19 Sep | S-ELIG-2, S-DIR-3 |
| M15 | Stop too distant for a target (42 PUTs) | 18 Sep | Labelled 19 Sep | S-ELIG-3 |
| M16 | Features never enter the ranking | Deep dive | Open | S-RANK-4, S-ABL-1, S-ABL-2 |
| M17 | Entry timing — evening signal, morning entry on a 15-minute delayed quote, overnight gap | Quote-feed evidence | Open | S-TIME-1, S-TIME-2 |
| M18 | Book direction vs market regime (64% CALL in a falling tape) | Exit study window | Open (macro informs, never scores) | S-REG-1, S-REG-2 |
| M19 | Hold length — 20 sessions of theta vs the anticipated move | D2 decision | Open | S-EXIT-1, S-EXIT-4 |
| M20 | Buying expensive implied volatility | True IV percentile (F2) available from N | Open | S-IV-1, S-IV-2 |
| M21 | Event convexity untested (earnings) | Blockers item 4 | Open | S-CONV-2 |
| M22 | Flat features hid the edge (volume, sector, regime, physics, IV) | 18–19 Sep | **Fixed** (F1–F8 minus F4/F7) | S-ABL-1 on N |
| M23 | Entering early may mean false starts | Anticipatory thesis | Open | S-ANT-1…3 |
| M24 | Concentration (same sector / root cause) | Ticket lists | Open | S-RANK-3 |

## 3a. Family IA — Intelligence Audit (runs first; ACK 19 Sep 2026)

Question before any strategy: **what does AVSHUNTER know that the market does not yet price, and where along the
chain is that information kept or lost?** Temporarily ignore GO/WAIT/BLOCK, tickets, cap, stop, contract and exit;
measure the information content of the pipeline's own evidence, then how much survives each transformation.

| Id | Test | Population |
|---|---|---|
| IA-1 | Information per feature: rank correlation of the **raw continuous** value with forward return at 1 / 2 / 3 / 5 / 10 / 20 sessions | U (bar-derived features, ~5 years); weekly chains (options-state features, ~1 year) |
| IA-2 | Decay: IA-1 by horizon for each feature — the signal half-life that contract expiry should follow | U |
| IA-3 | Magnitude vs direction: forward absolute move **÷ implied move at entry** (realised ÷ priced), then direction conditional on large moves. Raw magnitude is never the outcome: the option price already charges for it | U + weekly chains |
| IA-4 | Conditional information by regime (volatility regime, trend, sector state) | U |
| IA-5 | Incremental information: does a feature add anything once the others are known (partial correlation; model with and without it on the holdout) | U |
| IA-6 | **Transformation loss**: information surviving each step — universe → Discovery candidates → ranking → tickets → option expression → after stop → after spread → net | H now; N later |
| IA-7 | Discretisation loss: continuous value vs its label, same holdout | U |
| IA-8 | Calibration: stated probabilities (Layer 2 target-hit probability) vs realised; outcome monotonicity by confidence bucket | H+, N |
| IA-9 | Interactions: a short list fixed before looking (compression × relative strength, structure × IV state, early pressure × regime); any wider search only inside the exploration period | U |

Governance for IA: exploration 2021–2024, confirmation holdout 2025–2026 (untouched until exploration findings are
frozen), purging between train and test, every test logged, PBO / deflated Sharpe reported for the family.
Features are used only where they exist point-in-time: bar-derived over ~5 years, options-state over ~1 year of
weekly chains, full-pipeline features (physics verdict, geometry, value fields, macro) only where runs are recorded.

The scientifically accurate statement until IA reports: "we have not yet identified where AVSHUNTER's information
becomes economic edge, or where the decision chain destroys it."

## 4. Scenario catalogue

Format: **hypothesis** · variant against "as is" · population · what a pass would lead to (a design proposal, never
an automatic build).

### Direction (M1, M14)
- **S-DIR-1 Direction hit rate by evidence group.** Is direction skill concentrated anywhere? Hit rate at 1/5/20
  sessions by physics verdict, geometry label, volatility regime, relative strength, IV direction. · U, N ·
  → restrict or reweight direction where skill exists.
- **S-DIR-2 Cross-sectional tilts as direction.** 5-session reversal and distance from the 52-week low (the two
  robust findings, IC +0.02) used to rank CALL vs PUT candidates. · U · → a cross-sectional score (blockers item 5).
- **S-DIR-3 Structure wins vs governed direction wins.** For DIRECTION_CONTRADICTS_STRUCTURE rows, measure the
  underlying move in both directions. · U, N · → the direction-conflict decision.
- **S-DIR-4 Relative strength as direction.** Direction = sign of rs_vs_sector_20d_pct. · U · → RS input to
  direction governance (research only).
- **S-DIR-5 Market-neutral pairing.** Long the top CALL and top PUT per session together. · H, N · → removes market
  direction from the book's result.

### Expansion without direction (M1 alternative)
- **S-EXP-1 Buy expansion, not direction.** On COMPRESSION regime or EARLY_PRESSURE_BUILDING names, a long
  straddle / strangle (same runway and spread rules). Today the pipeline excludes non-directional expressions. ·
  N (and H where chains allow) · → a non-directional expression for names where direction is unproven but
  expansion is expected. **This is the scenario most aligned with "enter before the crowd" if direction skill stays
  at 51%.**

### Ranking — the de facto gate (M12, M16, M24)
- **S-RANK-1** central return · **S-RANK-2** upside ÷ |cautious| · **S-RANK-3** cautious with one ticket per sector
  and per root cause · **S-RANK-4** cautious plus a feature tilt (physics verdict, true IV percentile, relative
  strength, volatility regime, reversal, 52-week-low distance), weights fixed before the run · **S-RANK-5** cap 10
  and cap 20 instead of 5. · H, N · → the D3 ranking decision.

### Exits (M3, M19)
- **S-EXIT-1** fixed 1 / 3 / 5 / 10 / 20 sessions (signal quality without exit logic).
- **S-EXIT-2** no underlying stop inside the planned hold (premium is the maximum loss) — replicate +2.9 pts on H+.
- **S-EXIT-3** stop at 1.5 expected moves.
- **S-EXIT-4** exit at the anticipated move horizon (anticipated_move_sessions) instead of the 20-session hold.
- **S-EXIT-5** sell into the first expansion event after entry ("sell into the herd", P6).
- **S-EXIT-6** option-value exit that compares holding against the **bid** (the fair version of the degenerate
  re-value rule).
- **S-EXIT-7** roll at the last exit session (ledger trial 18 Sep).
- · H, H+, N · → the exit policy decision (D4).

### Runway and contract (M4, M6)
- **S-RUN-1** nearest expiry covering the hold vs longest eligible expiry (premium vs runway).
- **S-RUN-2** share of exits at the last usable session, before vs after the 19 Sep runway fix.
- **S-CONV-1** long-dated convexity: 60–120 DTE, ~0.25 delta on COMPRESSION / EARLY_PRESSURE names. · N (chains now
  reach 110 DTE) · → a convex expression.
- **S-CONV-2** earnings convexity: cheap volatility bought before dated catalysts. · H+ where event dates exist, N ·
  → blockers item 4.
- **S-VALSEL-1/2** contract chosen by value (central / cautious) among contracts covering the hold (the SHADOW
  fields) vs score choice. · N · → ACTIVE value selection.

### Costs and timing (M5, M7, M17)
- **S-COST-1** ticket spread limit 5% / 10% / 15%.
- **S-COST-2** limit order at mid vs the ask (fill-model sensitivity already in the harness).
- **S-COST-3** delta band 0.35–0.55 vs 0.20–0.75 (tighter moneyness, lower spread).
- **S-TIME-1** return by quote age at entry (15-minute delayed feed).
- **S-TIME-2** entry at the evening close ask vs morning (open + 15 min) vs open + 60 min, using the open-record
  marks. · N · → entry timing rule.

### Valuation (M13)
- **S-VAL-1** calibration by bucket: predicted vs realised return, per decile of central and cautious value. · H+, N ·
  → trust in the cost model.
- **S-VAL-2** conditional drift: value with a drift equal to the measured forward return of the candidate's evidence
  group (from S-DIR-1), research only. · N · → whether any measured edge makes value positive after costs.

### Eligibility (M9, M14, M15)
- **S-ELIG-1** C0 plus rows removed by FINAL_ACTION_BLOCKED, split by block reason (first: the fact / threshold /
  forecast mix, and whether a blocked row can still become a ticket). Blocks are allowed when understood; this
  prioritises the continuous-improvement list.
- **S-ELIG-2** DIRECTION_CONTRADICTS_STRUCTURE rows, underlying both ways (with S-DIR-3).
- **S-ELIG-3** STOP_TOO_DISTANT_NO_TARGET rows with a nearer structural stop (most recent swing high), underlying.

### Volatility price (M20)
- **S-IV-1** outcome by true IV percentile bucket at entry. · **S-IV-2** IV direction (rising / falling) at entry. ·
  N (true IV percentile exists from N; history restored) · → an IV tilt in ranking.

### Regime (M18)
- **S-REG-1** outcome by volatility regime (F3) and macro regime (recorded, display-only).
- **S-REG-2** CALL/PUT mix vs market direction per session. · H, N · → a regime-aware mix (never a macro score
  without evidence).

### Anticipation (M23, the thesis)
- **S-ANT-1 Lead time.** T0 = first session in a Discovery book; TC = first governed expansion event (P2 definition
  registered before the run). · U
- **S-ANT-2 Confirmation tax on the underlying** (move T0→TC) and on the option where daily chains exist (same and
  equivalent contract). · U, N (indicative)
- **S-ANT-3 False-start rate and cost** (no event within 20 sessions; adverse excursion; stop hits). · U
- Net anticipation value = confirmation tax saved − false-start cost − extra execution cost.

### Component ablation (M8, M16, M22)
- **S-ABL-1** remove one feature at a time from the S-RANK-4 tilt (physics, IV, RS, regime, Crabel/Wyckoff detail).
- **S-ABL-2** leading-only vs leading+context vs all (roles assigned **by measured lead time** from S-ANT-1, not by
  opinion).
- **S-ABL-3** outcomes with and without GEX influence on size and exit.

### Portfolio and product (M11)
- **S-PORT-1** breadth: top 20 per session at equal small premium — distribution of ≥ +100% winners vs the average.
- **S-PORT-2** barbell: top 5 by cautious plus 5 convex (S-CONV-1) per session.

## 5. Order and dependencies

| Step | Scenarios | Needs |
|---|---|---|
| 1 | Baseline "as is" on H; S-RANK-1…5, S-EXIT-1…3/6/7, S-COST-1…3, S-VAL-1, S-REG-2 | IV catch-up finished (Phantom free) |
| 2 | S-ELIG-1 (understanding first), S-EXIT on H+ | Weekend backfill, legacy re-score |
| 3 | P2 expansion-event definition registered (ACK) → S-ANT-1…3, S-DIR-1…4, S-EXIT-4/5 on U | ACK approves the event definition |
| 4 | Everything on N: S-VALSEL, S-RUN, S-IV, S-EXP-1, S-CONV-1, S-TIME, S-ABL, S-PORT | First evening runs on the fixed pipeline; results as outcomes mature |

## 6. Rules

- Definitions are frozen; a changed definition is a new scenario id, never an edit of this one.
- Every run is a ledger trial; results are compared with the baseline on the same dataset hash only.
- No scenario changes the pipeline. A scenario that passes becomes a written design proposal for ACK with its
  evidence; nothing is built without that decision.
- Blocks are allowed when their reason is understood (ACK 19 Sep); S-ELIG results feed the continuous-improvement
  list, not a removal programme.
- Pipeline behaviour observed during the backtest is recorded in `PIPELINE_AS_IS_NOTES_20260919.md`.
