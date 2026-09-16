# AVSHUNTER — Objective Assurance Assessment

Status: **DRAFT — assurance review, no code changed.** Prepared 16 Sep 2026.
Evidence base: `DECISION_PATH_MAP_20260914_214012.md` (DM-xx), `END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md` (S-xx), `BUSINESS_DOMAIN_DESIGN_ADDENDUM.md`, signal-accuracy audit of run `20260914_214012`, and the project's own research records (`audit/td/AVS-TD-001/findings.md`, `outcome_census.md`).

---

## 1. The question this assessment answers

Code review and tests answer **verification**: *was the code built the way it was written?*
This assessment answers **validation**: *was the right logic written — can it achieve what the pipeline is for?*

A stage can be perfectly coded and still be the wrong logic. When that is true, no number of patches produces a working product, because every patch makes the wrong thing more reliable.

Each stage is assessed on four questions:

| # | Question | Type |
|---|---|---|
| A | Is the stage's business objective stated and traceable to the pipeline objective? | Requirement |
| B | **If coded perfectly, could this logic achieve that objective?** | Design adequacy |
| C | Does real output show it does? | Empirical validity |
| D | Is it coded as designed? | Verification (secondary) |

Verdicts for B: **FIT** (logic can meet the objective), **PARTIAL** (right idea, missing or wrong element), **NOT FIT** (logic measures something else), **ABSENT** (capability required by the objective does not exist).

---

## 2. Pipeline objective (from the business requirements, 15 Sep 2026)

> For every ticker, every session: determine whether there is money in the ticker or its options, find the strongest expression of the thesis, identify cheap convexity, value it with a correct EV, and rank all opportunities by risk-adjusted EV — excluding only what is invalid or untradeable — so the trader acts on the best opportunities and the system learns from outcomes.

Decomposed into required capabilities:

| ID | Capability | What "achieved" means |
|---|---|---|
| O1 | Directional thesis | Direction, invalidation and hold period that are right more often than chance, with measured confidence |
| O2 | Money measurement | Expected profit after costs and uncertainty, per $ at risk |
| O3 | Expression search | All admissible expressions (long options, debit verticals, short shares for PUT) generated and compared on the same basis |
| O4 | Cheap convexity | Options priced below the volatility the evidence/forecast expects, with convex payoff in the thesis direction |
| O5 | Ranking | Every valid, tradeable opportunity ordered by risk-adjusted EV; nothing silently excluded |
| O6 | Actionable morning decision | Live revaluation of the ranked expression, one decision, no later overrides |
| O7 | Learning loop | Every decision recorded with inputs; outcomes matured; evidence and valuation calibrated |
| O8 | Trustworthy operation | Reproducible, point-in-time, missing data never disguised as signal |

---

## 3. Assurance matrix

### O1 — Directional thesis

| Stage logic | B: design adequacy | Why | C: empirical evidence |
|---|---|---|---|
| Discovery structural direction (Wyckoff / Precor / Fusion table) | **PARTIAL** | Produces a structural hypothesis; the objective needs a direction *measured against outcomes* — the table has no evidence input and no confidence | Research reconstruction: terminal direction correct CALL 44.3%, PUT 52.8% (AVS-TD-001 findings) — at or below chance |
| Direction governance (`resolve_governed_direction`) | **NOT FIT** | By design keeps the Discovery direction whenever it is CALL/PUT and labels it CONFIRMED; evidence can never change or qualify it (DM-01) | 65% of directional rows oppose their own evidence scores, stable 63–68% across runs since 6 Sep |
| Evidence family ACTUARIAL (`_determine_direction`) | **NOT FIT** | Driven by auction controller/migration; neutral defaults to CALL; ignores its own up/down probabilities (DM-02) | 480 of 569 PUT edges have P(up) > P(down) |
| Evidence family PRICE_FLOW (`directional_force`) | **NOT FIT** | Returns inputs never produced, so it is a trend label + VWAP flag counted as independent evidence (DM-03) | Only values ±15 / ±45 |
| Actuarial statistics behind all probabilities | **NOT FIT (data)** | Uncleaned outliers (20d return max 46.9M, mean 72 vs median 0.0004); overlapping windows treated as independent; confidence 1.0 on every row; labels ~10 weeks stale (S7) | Any mean-based statistic is invalid |
| Invalidation (governed Wyckoff validation level) | **FIT** | Structural stop on the correct side, missing stays missing | Correct side 100% in audit; 169 missing correctly blocked |
| Hold horizon | **NOT FIT** | No stage decides the thesis hold; it is read back from the selected contract's DTE (DM-38) — the contract defines the thesis it was chosen for | 100% of routed rows `DTE_FALLBACK_LOW_CONFIDENCE` |
| Target | **NOT FIT** | 95% have no structural target; Options substitutes 3R with no bound — a formula, not a market level (DM-06/07) | 35 negative PUT targets; NE/WTTR targets 32–36% away vs 3–4% expected move |

**O1 verdict: NOT ACHIEVED BY DESIGN.** The logic can produce a direction label, but nothing in it measures whether the direction is right, and the hold and target are not thesis properties.

### O2 — Money measurement

| Stage logic | B | Why | C |
|---|---|---|---|
| `ev_engine_v2.py` — the EV that feeds verdicts | **NOT FIT** | "Probability" is a heuristic blend; PUT uses upside statistics and a stop below entry; multipliers < 1 move negative EV toward 0, so worse spreads and weaker data *raise* the score; move double-counted | Drives `final_decision_engine`, EIL, Lab EV warning, EOD |
| EV3 barrier engine | **PARTIAL** | Right structure (first-passage probabilities, ask entry, lower-bound ranking, verticals) but timeout valued at unchanged spot (drops drift and convexity), grid snapping biases per candidate, exit spread modelled as a fraction, no commissions | Evaluates 245 of 1,449; authority off; 0 matched outcomes for calibration |
| Monetisability (intrinsic at target vs ask) | **NOT FIT** | Treats the target as certain — answers "profit if the target is hit", not "expected profit"; with 3R targets it measures the formula, not the market | NE 446%, WTTR 480% from 3R targets; drives tier/BLOCK routing despite "advisory" comment |
| `rr_underlying` / R:R | **NOT FIT** | With 3R fallback, R:R = 3.0 by construction | 97% null upstream, published as 0.0 downstream |
| `win_probability` / `win_prob_predicted` | **NOT FIT** | Linear rescale of composite score (40 + 0.25 × composite) or a pooled win rate, labelled probability | 33 distinct values around 0.50 |
| Contract economics v2 / DOI valuation | **PARTIAL** | Good pricing mechanics (timing, IV shocks, ask/bid) but no probabilities — scenario returns treated as certain, favouring low-delta contracts | Picks contracts within families; DOI probability fields blank on all rows |

**O2 verdict: NOT ACHIEVED BY DESIGN.** The number that currently decides is not an expected value; the one that is closest to an EV does not decide.

### O3 — Expression search

| Stage logic | B | Why | C |
|---|---|---|---|
| Contract selector | **PARTIAL** | Chooses one long option by a weighted score of delta/DTE/theta/vega/liquidity; not by money; liquidity judged after selection; spread limit computed but not applied (S10) | EV3 later rejects 525 for liquidity, 213 no evaluable contract |
| Debit verticals | **PARTIAL** | Valued in EV3 only; production policy allows long single-leg only; monetisability never values verticals | Not an expression the trader sees |
| Short shares (PUT) | **ABSENT** | No expression, no valuation, no borrow data | — |
| Comparison across expressions on the same basis | **ABSENT** | Six definitions of "value at target", three pricers, four cost conventions — no common path set | — |

**O3 verdict: ABSENT.** The pipeline picks *a* contract; it does not search for the strongest expression or answer "option or ticker".

### O4 — Cheap convexity

| Stage logic | B | Why | C |
|---|---|---|---|
| `convexity_score` / campaign | **NOT FIT** | Counts conditions; missing data counts as a pass; called with empty inputs — measures data absence, not cheapness | 2 / STAGED on 100% of contract rows, 3 of 3 runs; feeds tier and priority |
| `ivp_252d` / `iv_rank` | **NOT FIT** | Compares today's IV with the realised-vol range, not with IV history; rank = max of two windows | 26.5% of rows exactly 100 |
| `garch_iv_tailwind_score` | **PARTIAL** | IV − forecast vol is the right idea, but forecast horizon not tied to hold/DTE and missing IV becomes 0 | 137 rows 0 where IV missing |
| Heston greeks overwrite | **NOT FIT** | Calibration unreachable on Windows; a flat-vol delta replaces the provider delta | 58 contracts delta off > 0.10 |
| Event awareness | **ABSENT (broken input)** | Earnings read from a Polygon field that does not exist | Earnings always UNKNOWN |

**O4 verdict: NOT ACHIEVED.** Nothing currently measures whether convexity is cheap.

### O5 — Ranking

| Stage logic | B | Why | C |
|---|---|---|---|
| Architecture | **NOT FIT** | Serial gates (Vanguard regime floors, EIL liquidity at EOD, EOD status rules, tier thresholds, morning ladder) decide inclusion; rank applied afterwards within survivors | Opportunities removed before valuation |
| Vanguard gates | **NOT FIT** | EV/win-rate floors chosen by macro regime (macro removed by business decision); confidence gate never fires | 465 `REGIME_MINIMUM_EV`, 774 `has_edge=False` |
| EIL verdict at EOD | **NOT FIT** | Measures end-of-day spread against a threshold, labelled execution intelligence | 73% BLOCKED = exactly the liquidity-gate failures |
| EOD status (TRIGGER_READY etc.) | **NOT FIT** | Reads trigger, conflict, catalyst and EIL; reads no money, no target plausibility, no spread; conflict can promote a row | 150 TRIGGER_READY decided without economics |
| Tier | **NOT FIT** | Thresholds on `options_score` and composite; campaign clue satisfied by constant convexity | Two incompatible tier vocabularies |
| Priority score | **NOT FIT** | Weighted verdict labels and constant inputs; recomputed by the UI server with fields the book strips | Rank overwritten after publication |
| Research evidence on filters | — | — | Gates remove CALL rows that hit targets *more often* than survivors (11.4% vs 8.1%); PUT priority score IC −0.32; |IC| ≤ 0.09 for CALL scores (AVS-TD-001) |

**O5 verdict: NOT ACHIEVED BY DESIGN.** The pipeline gates on labels and ranks on labels; neither is money.

### O6 — Actionable morning decision

| Stage logic | B | Why | C |
|---|---|---|---|
| Morning gate ladder | **PARTIAL** | Right checks (thesis invalidated, quote, spread, contract) but rule order lets a broken thesis become FLAG; missing stop reported as price invalidation | Code-level [V]; morning not yet run for 0914 |
| Execution gate | **NOT FIT** | Invents `READY_EXECUTE/BUY_NOW` from a morning GO when the upstream verdict is missing | — |
| Post-decision steps | **NOT FIT** | ≥ 7 later steps can downgrade/relabel; UI re-ranks | Final decision not owned by one place |
| Revaluation | **ABSENT** | Morning does not re-run valuation with live quotes; it applies thresholds | — |

**O6 verdict: PARTIAL.** Checks exist; one owned, value-based decision does not.

### O7 — Learning loop

| Stage logic | B | Why | C |
|---|---|---|---|
| Decision ledger | **PARTIAL** | Right concept (append-only, causal links) but required fields not enforced | `planned_hold_sessions` null on all 7,531 candidates; `completed_session` null for 4,931 |
| Outcome maturation | **PARTIAL** | Underlying first-passage labels; wall-clock as-of; re-appends | 1,078 complete outcomes, **0 fit-eligible** |
| Option outcome leg | **ABSENT** | No option P&L labels | `doi_outcome_labels` 0 rows |
| Trade journal | **NOT FIT** | Trades not linked to decisions | 0 of 14 trades with `thesis_id`; smoke and duplicate trades included |
| Calibration of any probability or EV | **ABSENT** | Never fitted | — |

**O7 verdict: NOT ACHIEVED.** The system cannot currently learn whether any of its logic makes money.

### O8 — Trustworthy operation

| Area | B | Evidence |
|---|---|---|
| Missing data handling | **NOT FIT** | Missing → neutral in every stage (defaults, neutral passes, zeros, fallbacks) |
| Reproducibility | **NOT FIT** | Wall-clock decay and EIL mode, overwritten inputs, dirty-tree runs, untracked imported code, actuarial data outside the repo |
| Data correctness | **FIT (base data)** | Prices, indicators, quotes, strikes, expiries, spreads recompute exactly from raw data |

---

## 4. Summary of verdicts

| Capability | Verdict | Can patches fix it? |
|---|---|---|
| O1 Directional thesis | NOT ACHIEVED BY DESIGN | No — needs evidence-based direction state, thesis-owned hold, target policy |
| O2 Money measurement | NOT ACHIEVED BY DESIGN | No — needs one correct valuation core replacing the deciding EV |
| O3 Expression search | ABSENT | No — capability must be built |
| O4 Cheap convexity | NOT ACHIEVED | No — metrics must be redefined and new data sourced |
| O5 Ranking | NOT ACHIEVED BY DESIGN | No — gate architecture must become rank architecture |
| O6 Morning decision | PARTIAL | Partly — rule order and ownership fixable; revaluation must be built |
| O7 Learning loop | NOT ACHIEVED | Partly — recording contract fixable; option leg and calibration must be built |
| O8 Trustworthy operation | NOT FIT (logic) / FIT (base data) | Yes with discipline — rules R1–R10 |

**Conclusion.** The base market data is right, and several building blocks are well designed (invalidation logic, first-passage idea in EV3, pricing mechanics in contract economics v2, the pure `domain/` layer, the append-only ledger concept). But the logic that turns data into the business answer — *is there money, where, in which expression, and how does it rank* — is either absent or measures something else. That is why fix programmes have not produced a working product: they verified and hardened logic that was never capable of meeting the objective.

---

## 5. Why this happened (process root cause)

1. **No executable statement of the objective.** Stages were specified by field contracts and governance rules, not by the business question each must answer and the evidence that proves it.
2. **Acceptance was verification-only.** Fix programmes closed when code matched its specification and tests passed; no acceptance criterion asked whether outputs predict money.
3. **Authority was withdrawn instead of earned.** When logic could not be trusted, it was made "advisory" and another layer was added, rather than validating or replacing it — producing many layers, none accountable for money.
4. **No outcome feedback.** Without matured, linked outcomes, wrong logic could not be detected by results.

---

## 6. Assurance framework for the rebuild

Every stage in the new design must pass all four gates before it gains authority:

| Gate | Requirement | Evidence required |
|---|---|---|
| **G1 Objective** | The stage's question is written in business terms and traced to O1–O8 | Requirement traceability entry |
| **G2 Design adequacy** | Independent review confirms the logic, if perfect, answers that question (no proxies, no circular inputs, no neutral defaults) | Design review record against rules R1–R10 |
| **G3 Verification** | Code implements the design | Decision tables, reference algorithm tests, golden replay |
| **G4 Validation** | Real outputs demonstrate the objective, walk-forward and point-in-time | Outcome evidence (below) |

### Validation criteria (G4) by capability

| Capability | Validation test | Pass condition (to agree) |
|---|---|---|
| O1 Direction | Hit rate of `direction_state=SUPPORTED` vs UNSUPPORTED/OPPOSED on matured outcomes | SUPPORTED significantly above chance and above OPPOSED |
| O1 Hold | Realised first-passage timing vs chosen hold | Chosen hold captures more EV than alternative holds |
| O2 EV | Calibration: realised P&L per $ by predicted EV decile | Monotonic increase; predicted within CI of realised |
| O3 Expression | Realised return of chosen strongest expression vs other valued expressions of the same thesis | Strongest expression outperforms alternatives on average |
| O4 Cheap convexity | Realised option return by cheap-convexity quintile, same thesis quality | Top quintile outperforms bottom |
| O5 Ranking | Realised P&L per $ by RAEV decile; top-decile vs universe | Monotonic; top decile positive after costs |
| O6 Morning | Realised outcome of acted vs revalued-but-not-acted | Actions not worse than their revaluation predicted |
| O7 Learning | Share of decisions with complete recorded inputs and matured outcomes | ≥ 99% complete |
| O8 Reproducibility | Replay of stored runs | Identical decision fields |

Until G4 evidence exists, outputs are presented as **ranked research** with their uncertainty, not as validated signals — consistent with manual review.

### Practical consequence for sequencing

- Start the **learning loop (O7) recording contract immediately** so validation evidence accumulates while the logic is rebuilt; without it no stage can ever pass G4.
- Rebuild **evidence (actuarial) and valuation (O2)** before tuning any ranking or convexity weights — ranking a wrong EV more precisely does not help.
- Treat every existing score, gate and label as **unvalidated** until it passes G1–G4 in the new design; do not port them by default.
