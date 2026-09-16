# Review — AVSHUNTER End-to-End DDD Behavioural Specification

Reviewed document: `docs/knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md` (1,511 lines)
Reviewed against: knowledge notes 01–07 and REPLICATION_PLAN, `audit/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md`, `BUSINESS_DOMAIN_DESIGN_ADDENDUM.md`, `OBJECTIVE_ASSURANCE_ASSESSMENT.md`, and recorded business decisions (15–16 Sep 2026).
Date: 16 Sep 2026 · Reviewer: Claude Code · Status: for ACK decision

---

## 1. Overall verdict

**Aligned in architecture and principles, and it improves the design in one important way.** The specification should become the governing behavioural document, subject to the changes below.

What it gets right (and matches the existing design):
- One owner per business fact, immutable published aggregates, unknown stays unknown (Invariants A–C ↔ rules R1, R2, R5, R6).
- Orchestrator coordinates but never decides (§2, §18) ↔ S0 / C-contexts.
- Thesis decided before any instrument; instrument must fit the thesis (§8–9) ↔ DM-38 fix, rule R4.
- No invented targets; `target_state = NONE` valued on stop/timeout (§8) ↔ D3.
- Direction states SUPPORTED / OPPOSED / UNSUPPORTED / INSUFFICIENT_EVIDENCE, no auto-flip (§8) ↔ note 02.
- Common path set, path-specific exit pricing, RAEV as lower-bound EV per $ at risk (§10) ↔ note 03, addendum §4, §7.2.
- Rank not gate; `NO_POSITIVE_EDGE` stays visible; portfolio concentration reported (§12) ↔ note 05.
- Execution revalidates rather than reinvents; remaining window, no clock restart (§13).
- Decision recorded before outcome; deterministic maturation with first-touch session (§14–15) ↔ note 06, S17.
- Replay and live share one domain path; replication before authority (§21–22) ↔ gates G1–G4.
- Legitimate terminal states defined (§19–20) — a strong addition.

**The key improvement:** replacing fixed hold buckets {5, 10, 20} with a **1–20 session opportunity window** and a **time-to-resolution distribution**. This is a better model of the business (a swing thesis can resolve on any day) and removes the artificial horizon choice. It supersedes parts of the existing notes and design (see §4).

---

## 2. Changes required in the specification

Ordered by importance. Each gives the location, the issue, and the proposed change.

### C1 — Evidence needs the barrier levels, but Evidence runs before Thesis (§7, §8) — HIGH
**Issue.** First-passage probabilities (target first / stop first) only exist for specific target and invalidation distances. The spec places Evidence (Stage 3) before Thesis (Stage 4), but target and invalidation are Thesis-owned. As written, Evidence cannot compute `p_target_first_by_session` without knowing the levels.
**Change.** State explicitly that Evidence consumes the **candidate** structural target and invalidation levels from `StructureAssessment` (§6 already lists "structural target candidates" and "structural invalidation candidates"), expressed in volatility units (e.g. distance in σ), and returns packets per candidate level set. Thesis then selects among candidates and records which packet it used. When no target candidate exists, Evidence returns stop-first / timeout distributions only.

### C2 — Session-by-session probabilities need a survival (competing-risks) method (§7) — HIGH
**Issue.** Estimating 20 separate per-session probabilities per state will be very sparse and noisy; naive per-day frequencies will be unstable and overfit.
**Change.** Specify the estimator: **discrete-time competing-risks survival model** — cumulative incidence of target-first and stop-first by session (Aalen-Johansen estimator or a discrete hazard model), with smoothing / shrinkage toward pooled hazards, `n_eff` counted in independent time blocks, and uncertainty by block bootstrap. Calibration must cover both *whether* and *when* (spec §16 already asks for timing calibration).
Reference: Kalbfleisch & Prentice, *The Statistical Analysis of Failure Time Data*; Aalen & Johansen (1978) [verify].

### C3 — Minimum DTE = 20 sessions + buffer for every expression needs a business decision (§9 "DTE behaviour", §19 row "No expression covers maximum thesis window") — HIGH
**Issue.** Requiring every option to outlive the full 20-session window always excludes short-dated contracts. That can exclude the strongest expression and much of the cheap convexity when evidence says a thesis usually resolves in Days 1–5 — conflicting with the business objectives "strongest expression" and "identify cheap convexity".
**Change (options for ACK).**
- (a) **Keep the rule** (every expression covers the full window) — simplest, most conservative, higher theta cost; or
- (b) **Allow shorter expressions without shortening the thesis**: the expression carries its own `last_exit_session` (expiry minus exit buffer); Valuation exits any path unresolved by that session at that session's price. The thesis window stays 1–20; the shorter option is simply valued honestly (paths beyond its life count as forced exits). Ranking then decides.
Recommendation: **(b)** — it satisfies "the instrument must fit the thesis" (the thesis is not changed) while letting valuation, not a rule, decide whether short-dated convexity is worth it.

### C4 — Thesis versioning rules are missing (§3 Invariant C, §13) — HIGH
**Issue.** The spec says a genuine change produces a new thesis version and that execution must not restart the 20-day clock. Without explicit supersession rules, a daily re-published thesis would silently restart the clock and break outcome validation.
**Change.** Add a **Thesis identity and supersession** section:
- What counts as the same thesis (ticker, direction, invalidation level, target level within tolerance, evidence session).
- When a new version is allowed (e.g. structural invalidation or target level changes; direction state changes; previous thesis invalidated or timed out).
- Whether a new version inherits the original window clock or starts a new one — must be explicit.
- `supersedes_thesis_id` recorded; the superseded thesis still matures and is validated.

### C5 — The decision ledger must record every candidate, not only actionable decisions (§14) — HIGH
**Issue.** "Before an actionable decision leaves the pipeline" implies only actionable rows are recorded. Validating ranking and selection (assurance O5, O6; note 06) needs outcomes for what was **not** chosen: NO_POSITIVE_EDGE, lower ranks, non-selected expressions, INSUFFICIENT_EVIDENCE theses. Without them the system cannot learn whether gates, ranks or selections added value.
**Change.** Record every published thesis, every valued expression and every terminal state, with an `actioned` flag. Outcomes mature for all of them.

### C6 — Outcome maturation covers the underlying only; the expression (option / short) outcome is missing (§15) — HIGH
**Issue.** The business question is money in the option or the ticker. Underlying TARGET_FIRST / STOP_FIRST does not tell whether the chosen expression made money (IV change, spread, theta). Assurance O7 found option outcomes absent today.
**Change.** Add **expression outcome maturation**: for each valued expression, mark-to-market at bid-side prices on the underlying resolution session (or its own last exit session, see C3), realised P&L per $ at risk, MFE/MAE, and comparison with predicted EV. Actual fills from the journal linked by `expression_id` / `thesis_id` where the trade was taken.
Also specify the **outcome origin**: thesis outcomes start from the thesis evidence session; expression and decision outcomes start from the decision time (morning run).

### C7 — Universe & Eligibility stage is missing (§4–6) — MEDIUM
**Issue.** There is no stage deciding which tickers are analysed. The current pipeline's largest silent drop (1,714 tickers labelled "no signal", mostly liquidity filters) and survivorship bias sit here.
**Change.** Add a stage between Market Data and Market Structure: point-in-time universe including delisted names, eligibility features and reason codes (`PRICE_RANGE`, `ADV`, `ATR`, `MIN_BARS`, `STALE_BARS`), with integrity failures (stale or incomplete bars) as the explicit data-integrity exclusion. Matches addendum C2 and decision-tree nodes N0–N1.

### C8 — Expression scope and short-share tradeability (§9 "Generation behaviour", "Tradeability") — MEDIUM
**Issue.** Scope is left to configuration; the approved business scope is not stated, and tradeability omits borrow.
**Change.** Reference the approved scope — **long calls / long puts, debit verticals, short shares for BEAR theses** (long shares for BULL theses: open question Q1) — and add to tradeability: **borrow available and borrow fee known** for short shares (status `BORROW_DATA_UNAVAILABLE` until a borrow source is integrated). Note early-assignment risk on the short leg of verticals.

### C9 — Comparing expressions with different durations (§10 "Expected value", §12) — MEDIUM
**Issue.** With path-specific exits (and C3 option (b)), expressions tie up capital for different lengths of time. Plain EV per $ at risk favours slower expressions.
**Change.** State the comparison rule: RAEV per $ at risk **and** a time-normalised measure (expected P&L per $ at risk per expected session held, or expected log growth). Business decision on which is primary; recommendation: rank on RAEV, show the time-normalised figure and use it as the first tie-break.

### C10 — Evidence scope wording (§7 "Responsibility", line 350) — MEDIUM
**Issue.** "When AVSHUNTER observed states like this one" can be read as AVSHUNTER's own past decisions only (a small, recent sample).
**Change.** "Historically, across the point-in-time market universe, when price was in states like this one…"; AVSHUNTER's own decision outcomes are an additional calibration source, not the base sample.

### C11 — Direction symmetry and data hygiene invariants (§3, §7) — MEDIUM
**Change.** Add invariants: BEAR theses use mirrored evidence and mirrored valuation (no upside-only statistics); evidence built only from cleaned, adjusted, outlier-validated returns with matured labels (today's actuarial DB has 20-day returns up to 46.9M).

### C12 — Advisory inputs must be named so they are not reintroduced (§5, §24) — LOW
**Change.** Add to "What Must Not Happen": macro context influencing any gate, score or rank (macro is owned by the scheduled routine and is advisory/manual; today it still leaks into Vanguard gate floors); event guards used as automated gates (decided: manual review). Add a Presentation / read-model note: the Lab renders published contracts only and never re-ranks (today the Lab server recomputes rank).

### C13 — Exit policy ownership (§8, §10, §13) — LOW
**Issue.** Day 20 is the maximum window, but whether a position should be closed earlier than Day 20 when unresolved (time stop) is not owned by any context.
**Change.** State that the Thesis owns the maximum window; any earlier time-stop is an **expression exit policy** valued by Valuation as an explicit variant (e.g. exit at Day 10 vs Day 20), chosen by RAEV — never a hidden assumption.

### C14 — Minor consistency items — LOW
- §1 line 19 and §26: context numbering (C1, C3–C9) should match the addendum and include C2 Universe & Eligibility, C10 Outcome & Learning, C11 Presentation.
- §4 run identity: add `release_id` and `clean_tree` flag (rule R8).
- §12: add hysteresis for day-to-day stability of the strongest expression (note 05 §4).
- §19: "All expressions unvalued → thesis cannot enter ranked actionable set" — add "remains visible as NOT_VALUED with reasons".
- §24: add "a failure to compute is shown as a neutral or passing value" (neutral pass) as a forbidden behaviour.

---

## 3. Validation of the specification against the business objectives

| Objective | Covered by spec | Gap |
|---|---|---|
| O1 Directional thesis | §7, §8 | C1, C2, C4, C10, C11 |
| O2 Money measurement | §10 | C6 (realised expression P&L), C9 |
| O3 Expression search | §9, §12 | C3, C8 |
| O4 Cheap convexity | §11, §12 | C3 (short-dated convexity) |
| O5 Ranking | §12, §19 | C5 (record non-selected) |
| O6 Morning decision | §13 | C4 (window clock) |
| O7 Learning loop | §14–16 | C5, C6 |
| O8 Trustworthy operation | §3–4, §21 | C7, C11, C12, C14 |

---

## 4. Changes required in existing documents to align with the specification

If ACK approves the specification (with the changes above), these documents must be updated because they still use fixed hold buckets or earlier wording:

| Document | Section | Update |
|---|---|---|
| `01_evidence_and_first_passage.md` | Labels, output contract | Per-session competing-risks packet over 1–20 sessions (C2), barrier candidates from Structure (C1) |
| `02_direction_and_thesis.md` | Hold horizon; output contract | Replace `hold ∈ {5,10,20}` with trade window 1–20 + resolution distribution; thesis versioning (C4) |
| `03_option_valuation_and_ev.md` | Outcome model, payoff table, EV | Window 1–20 with path exit sessions; expression last exit session (C3); duration-normalised comparison (C9) |
| `04_volatility_and_cheap_convexity.md` | Forecast volatility | Term-aware forecasts (5/10/20 or continuous) instead of a single hold horizon |
| `05_expression_selection_and_ranking.md` | Generation, morning decision | DTE rule per C3 decision; remaining-window revaluation; record non-selected (C5) |
| `06_validation_and_backtesting.md` | Metrics, ledger | Timing calibration; record all candidates (C5); expression outcomes (C6) |
| `REPLICATION_PLAN.md` | R4 | Replace h ∈ {5,10,20} with competing-risks cumulative incidence over 1–20 sessions |
| `README.md` | Index | Add the specification as the governing behavioural document once approved |
| `BUSINESS_DOMAIN_DESIGN_ADDENDUM.md` | §2.3 Thesis invariants, §3 N5, §4.1 notation, §6.4 D7 | Hold buckets → 1–20 window and resolution distribution |
| `END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md` | S9 hold horizon, S10 selector DTE rule, D7 | Same |

---

## 5. Decisions needed from ACK

1. **C3** — Minimum DTE: every expression must cover the full 20-session window (a), or shorter expressions allowed and valued with their own last exit session (b, recommended)?
2. **C4** — Does a superseding thesis version inherit the original window clock or start a new one?
3. **C9** — Primary ranking measure: RAEV per $ at risk (recommended, with time-normalised tie-break) or time-normalised RAEV?
4. **Q1** (carried) — Long shares for BULL theses in scope?
5. Approve updating the existing notes and design documents per §4 once the specification is amended.
