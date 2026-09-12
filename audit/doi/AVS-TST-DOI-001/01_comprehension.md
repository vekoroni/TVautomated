# 01 — Comprehension gate (AVS-TST-DOI-001)

**Written:** 2026-09-10, before any production source file was opened.
**Source:** `docs/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md` v1.1 (805 lines), read in full.
**Tester:** Claude Code, independent Quality Advisor / Test Analyst.

Evidence that this gate preceded code reading: at the time of writing, the only
files opened in this session were the test prompt
(`audit/doi/AVS-TST-DOI-001_CLAUDE_CODE_TEST_PROMPT.md`), the design document
above, and `git rev-parse` / `git tag` output. No module under `domain/`,
`application/`, `infrastructure/`, `tests/` or `contracts/` had been read.

---

## 1. The three independent questions (§1) and the domain that owns each

The design's central assertion is that AVSHUNTER had committed a category
error: it collapsed three questions that live on three different time scales
into one binary verdict. DOI exists to keep them apart.

| # | Question | Time scale | Owning domain |
|---|---|---|---|
| 1 | Is the underlying thesis still valid? | Multi-session underlying hypothesis (1–20 trading sessions) | Thesis domain — Discovery/Vanguard originates it, Morning Gate revalidates it (§5.1) |
| 2 | Which option contract currently expresses that thesis most effectively? | Time-specific instrument observation | Contract-family domain — Dynamic Options Intelligence (§5.3) |
| 3 | Should the trader enter, wait, repair, roll or exit? | Momentary execution condition | Execution domain — the **human trader** is sole authority; the Execution Gate is reduced to a deterministic evidence-and-warning service (§5.5) |

The failure mode the design names explicitly (§2): treating a poor contract
observation (question 2) as a failed ticker thesis (question 1) removes
developing opportunities; treating a good thesis as proof any option will pay
creates the mirror-image false positive. Question 3 was additionally being
answered automatically, when it is reserved to the human.

Two supporting domains sit alongside: the Option observation domain (owner:
Canonical Data System, §5.2) is the single source of truth for raw
observations, Phantom (§5.4) is a **read-optimised projection** over those
observations and must never become a competing raw authority, and the Learning
domain (§5.6) is the Decision and Outcome Ledger, which is the outcome
authority.

## 2. The non-discard principle (§1.1) as a testable invariant

**Design text:** AVSHUNTER shall not discard, hide, permanently invalidate or
automatically close an opportunity because of entry quality, exit timing,
elapsed horizon, spread, liquidity, premium, IV, current price, or a model
score. The pipeline may state observable facts and risks, but the row remains
in the governed opportunity history and visible in the Intelligence Lab.

**Testable invariant (my formulation):**

> Let `B` be the set of governed opportunity rows (keyed by run_id + ticker +
> thesis_id + trade_idea identity) produced by the governed pipeline before any
> DOI/EIL/entry/exit/timing/liquidity evaluation. Let `B'` be the set present
> after every such evaluation, overlay, projection and Lab view resolution.
> Then `B' ⊇ B` must hold **elementwise and per direction**: for every row in
> `B` there is a row in `B'` with the same identity. Only *advisory attribute
> values* and *ordering* may differ. Cardinality must satisfy
> `|B'_CALL| = |B_CALL|`, `|B'_PUT| = |B_PUT|`, `|B'_OTHER| = |B_OTHER|`.

**What observable in a run artefact would prove it violated** — any one of:

1. A governed opportunity count in a post-DOI artefact (final opportunity
   book, Lab payload, Interpreter handoff, morning manifest) that is **lower**
   than the pre-DOI governed count for the same run, in any of the three
   direction buckets.
2. A row present in the governed book whose identity is absent from the
   unfiltered `ALL OPPORTUNITIES` Lab view for the same run.
3. A row whose `tradeable` / `final_action` / availability field was flipped to
   a terminal, non-recoverable value by an automated entry/exit/timing/liquidity
   state — i.e. a state that no human action or later observation can reverse.
4. A row deleted from a persisted table (DELETE or destructive UPDATE) rather
   than superseded by an appended row, where the deletion is triggered by any
   of: `eil_v3_verdict`, spread, OI, volume, missing quote, `HORIZON_ELAPSED`,
   `INVALIDATION_LEVEL_BREACHED`, `TARGET_TOUCHED`.
5. A position/ledger transition to closed that was not initiated by a human
   actor field.

Note the asymmetry the design permits: `B' ⊃ B` (rows *added*, e.g. overlay
rows) is not a violation. Shrinkage in any direction bucket is.

## 3. The two vocabularies (§8.1–8.2) and the no-folding rule

**Thesis states (§8.1) — eight:**

```
THESIS_DEVELOPING
THESIS_ACTIVE
THESIS_VALIDATED
THESIS_CONDITION_BREACHED
THESIS_RECOVERING
TARGET_TOUCHED
HORIZON_ELAPSED_REASSESS
THESIS_DATA_INSUFFICIENT
```

**Contract-entry states (§8.2) — nine:**

```
CONTRACT_MONITOR
CONTRACT_LIQUIDITY_DEVELOPING
CONTRACT_ENTRY_ACCEPTABLE
CONTRACT_LIMIT_PRICE_REQUIRED
CONTRACT_REPAIR_REQUIRED
CONTRACT_DATA_INSUFFICIENT
CONTRACT_DEGRADED
CONTRACT_SUPERSEDED
CONTRACT_EXPIRED
```

**The rule:** these are a *new bounded-domain vocabulary*. They "must not be
added as new meanings of the overloaded legacy `eil_v3_verdict` enum" (§8.2).
The reason is that `eil_v3_verdict` already carries execution authority
semantics in legacy consumers; folding a monitoring state into it would let a
monitoring state inherit deletion power from code that reads the legacy enum.

Transition rules that matter for testing (§8.3): a contract state cannot
invalidate a thesis; `CONTRACT_DATA_INSUFFICIENT` is neither economic zero nor
a negative forecast; no state deletes or hides an opportunity; entry/exit
conditions are advisory observations, not terminal verdicts; breach may
transition to recovering; `HORIZON_ELAPSED_REASSESS` requests human
reassessment and is not automatic rejection; expired contracts stay historical
and are never reused; supersession is append-only and only within the same
governed thesis family unless a new reassessment/thesis version exists.

## 4. The authority matrix (§6) and the four `decision_authority` fields

| Decision | Owner | DOI/Phantom role |
|---|---|---|
| Governed CALL/PUT direction | Thesis domain | Consume only |
| Target / invalidation / hold | Thesis domain | Consume only |
| Morning thesis condition | Morning Gate | Consume only; result remains visible even when breached |
| Candidate contract family | DOI | **Own** |
| Current preferred contract | DOI | **Own**, advisory to execution |
| Contract liquidity state | DOI | **Own** |
| Contract monetisation estimate | DOI | **Own**, advisory |
| Macro / sector context | Macro domain | Advisory **feature only** |
| Entry / exit warning | Execution Gate | Consume only; no automatic discard |
| Capital and final order / fill | Human / broker workflow | **No authority** |

DOI owns exactly four things, all of them about *contracts*, never about the
thesis, the direction, the capital or the fill.

**The four fields every DOI and Phantom output must carry (§6):**

```text
decision_authority   = NONE
can_change_direction = false
can_invalidate_thesis= false
can_grant_capital    = false
```

My reading of the intent: these are self-declarations, and their presence is
necessary but not sufficient. The stronger test is that no downstream consumer
*branches* on them as anything other than telemetry — a consumer that reads
`decision_authority` and grants authority when it is set differently would mean
the field is a live switch rather than a constant assertion.

## 5. The six structural hard exclusions (§10) — and what is explicitly not one

Hard exclusions from **preferred-contract eligibility** are limited to
structural impossibility. Exactly six:

1. wrong option side (not the governed direction);
2. expired contract;
3. invalid OCC identity;
4. DTE unable to outlive the governed hold plus buffer;
5. negative or crossed quote observation;
6. impossible strike/expiry fields.

Two qualifications the design attaches: these apply "to the unusable contract
observation, not to the ticker opportunity"; and the excluded observation plus
its reason remain in the family audit, with the ticker still visible even when
no currently eligible contract exists.

**Explicitly NOT exclusions** — the design names these as "ranking/confidence
evidence, not thesis-deletion gates":

- open interest (any floor);
- volume (including zero current volume);
- put/call ratio;
- IV percentile;
- ordinary spread (a wide spread is a warning, not a gate);
- entry conditions;
- exit conditions;
- timing / elapsed horizon.

Additionally called out separately: one-sided or incomplete quotes "may remain
monitorable but cannot be classified as presently executable" — so a one-sided
quote is *not* an exclusion either; it is a state cap.

And the specific reversal this design exists to perform (§10): "a fixed narrow
delta band must not preselect the answer." A broad governed safety boundary may
prevent extreme contracts; a narrow band may not. Delta is a family feature and
a model output at future scenarios, not a filter.

## 6. What "calibrated probability" requires before the word may appear (§11.6, §17.3)

The word *probability* may only appear on an output that is a calibrated model
output. Before a value is labelled a probability, §17.3 requires the following
to be **reported** (measured, not asserted):

- Brier score and log loss;
- reliability / calibration plots and expected calibration error (ECE);
- sample size by CALL/PUT, DTE, delta, liquidity and regime bucket;
- temporal stability;
- out-of-distribution rate;
- confidence intervals;
- comparison against simple baselines.

And a policy constraint: "Thresholds must be set from the measured baseline and
release objective, not invented before measurement." DOI-8's acceptance
paragraph sharpens this into a rejection gate: a model is rejected unless it
beats the **constant-prevalence baseline on both Brier and log loss**, remains
stable in each eligible temporal holdout window, and passes the calibration
policy.

§11.6: "No arbitrary weighted score may be labelled a probability. Until models
are calibrated, the system will publish deterministic scenario measures and an
explicitly named **`ranking_score_uncalibrated`**."

Non-goal 5 (§4) restates it: the release will not "describe an uncalibrated
score as a probability."

So the required name for uncalibrated ranking is exactly
`ranking_score_uncalibrated`, and any deterministic value wearing a name
containing `prob`, `probability`, `p_`, `likelihood` or `confidence` without an
applicable accepted DOI-8 model behind it is a defect.

## 7. Hysteresis (§12.3) and "no carried-forward economics" (invariant 10)

**Hysteresis rule:** to avoid contract thrashing, the *current preferred
contract is retained* unless a challenger satisfies **all four** conditions:

1. exceeds it by a **versioned minimum utility margin**;
2. has adequate observation quality;
3. remains preferable under stress;
4. is consistent with the same thesis direction and horizon.

The retention is the default. Non-supersession when the margin is not met is as
much a required behaviour as supersession when it is — a test that only proves
switching happens does not prove hysteresis.

**No carried-forward economics:** "All economics are recomputed for the
replacement contract. Premium, Greeks, payoff, IV and liquidity from the
previous contract must never be carried forward." Invariant 10 states it as:
"A contract switch forces exact-contract quote and economics refresh."

The testable form: construct a replacement whose own observation differs in
*every* contract-specific field from the incumbent's, force supersession, and
assert that **no** incumbent value survives anywhere in the new assessment.
Any surviving value is a carry-forward defect. §8.3 adds that supersession is
append-only and restricted to members of the same governed thesis family
unless a new reassessment/thesis version was created.

## 8. Trading sessions vs calendar DTE (§9.4, invariant 9)

Planned hold is governed in **trading sessions**. Option expiry is **calendar
time**. All valuation must convert through the **exchange calendar and exact
timestamps**. Direct subtraction of a session count from a calendar DTE is
**prohibited**.

Invariant 9: "Trading sessions are never treated as calendar days."

Where this bites concretely: the structural exclusion "DTE unable to outlive
the governed hold plus buffer" (§10, exclusion 4) is a comparison between a
session-denominated hold and a calendar-denominated expiry. Computing it as
`dte - planned_hold_sessions` is exactly the prohibited operation, and it is
*non-conservative over holidays*: 10 trading sessions spanning a holiday weekend
consume more than 10 calendar days, so naive subtraction would admit contracts
that expire before the hold completes. The correct computation walks the
exchange calendar forward `planned_hold_sessions` sessions from the evaluation
timestamp and compares the resulting **calendar date** to the expiry.

## 9. The fifteen regression invariants (§16), numbered as the design numbers them

1. Discovery/Vanguard direction, target and invalidation cannot be changed by DOI.
2. Macro cannot approve, block or reverse a thesis or contract.
3. EIL/DOI `BLOCKED` compatibility values cannot delete candidate rows.
4. Contract conditions cannot grant capital or discard an opportunity.
5. Morning Gate records confirmation, breach, recovery or elapsed state without requiring a new option quote and without deleting the row.
6. OI, volume, PCR, entry, exit and timing conditions are never row-deletion gates.
7. Missing data is never coerced to economic zero.
8. CALL and PUT paths have equivalent governance coverage and side-correct formulas.
9. Trading sessions are never treated as calendar days.
10. A contract switch forces exact-contract quote and economics refresh.
11. All computations bind to immutable dataset IDs and evidence cutoffs.
12. Restarts are idempotent and append-only histories are not overwritten.
13. A dormant/breached/elapsed ticker remains visible and triggers a new option call only after underlying-price reactivation or manual request.
14. Only long single-leg CALL/PUT structures enter the production contract family.
15. No automated exit condition closes or removes a human-held trade.

## 10. What each "Implementation acceptance" paragraph claims as numbers

### DOI-7 acceptance (§19, DOI-7)

Qualitative, no counts. Claims: provider-free append-only outcome domain and
application service inside the **existing** option lifecycle control plane;
every assessment/horizon represented as one of **five** label states
(completed, option-path-partial, option-return-unavailable, deferred,
data-exception); labels retain exact contract and dataset lineage; record
two-sided/spread liquidity maturation, option and underlying MFE/MAE, horizon
return and target/invalidation passage; prohibit realised fills, thesis/capital
authority and automated closure; chronological cohort construction excludes
labels whose future outcome window crosses a split boundary; offline unit,
authority, persistence, restart and frozen-canonical-chain rehearsals passed.

### DOI-8 acceptance

Claims: interpretable logistic baseline with later-period **Platt**
calibration; CALL and PUT are **independent cohorts**; chronological splits
that purge outcome windows crossing boundaries; model cards include **nine+
named diagnostics** (Brier, log loss, ECE, calibration-bin uncertainty,
temporal holdout windows, OOD rate, feature ranges, missingness, DTE/delta/
spread cohort diagnostics); rejection unless the model beats constant
prevalence on **both** Brier and log loss and is stable in **each** eligible
holdout window; missing support / cohort mismatch / OOD publish no calibrated
probability and leave DOI-5 in place.

**Numbers:** the live control plane has **zero** persisted DOI-7 labels;
therefore **no** real production model has been trained or activated; frozen/
synthetic test data is **never** promoted as production evidence.

### DOI-9 acceptance

Claims: provider-free append-only ranking domain; **full family always
retained**; calibrated combination only when **every** comparable candidate has
an unambiguous applicable probability set, otherwise **the entire family**
falls back to DOI-5 deterministic ordering with incomplete candidates still
visible; policy weights and contract-switch margin learned on chronological
replay, accepted only when later validation and holdout cohorts improve reward
**without reducing coverage** and **every** eligible holdout window is
non-inferior; append-only ranking identity/lineage; CALL and PUT symmetric.

**Numbers:** the live control plane contains **no** real DOI assessments,
**no** outcome labels, **no** accepted probability models and **no** accepted
ranking policies; calibrated ranking is therefore correctly unavailable; **no**
synthetic policy has been promoted.

### DOI-10 acceptance

Claims: additive read-only projection over the existing final opportunity book;
preserves the complete governed v2 population; overlays accepted v3 actionable
evidence only after run/ticker/thesis/trade-idea identity reconciliation;
accepted Interpreter handoff remains **actionable-only**; a separate advisory
resolver exposes non-actionable rows for EOD review/trajectory only and
**explicitly rejects executable-session requests**; UI defaults to
`ALL OPPORTUNITIES`; governed contract separated from DOI-preferred contract
with alignment, probability applicability, uncertainty, evidence cutoff, model
identity and alternatives displayed; legacy EIL output relabelled as
non-authoritative entry telemetry; missing/inactive DOI tables produce explicit
`DATA_UNAVAILABLE` / `NOT_EVALUATED`, never removing a row or creating
zero-valued evidence; DOI-10 changes **no** direction, thesis, lifecycle,
action, size or capital field.

**Numbers:**

| Claim | Value |
|---|---|
| DOI regression pack passing at DOI-10 | **115 tests** |
| Rehearsal run id | **`20260909_071646`** |
| Opportunities preserved | **235** (all) |
| Accepted actionable rows overlaid | **exactly 4** |
| Canonical database hash | **unchanged** |

### DOI-11 implementation status

Claims: evening orchestrator runs DOI **after governed horizon propagation and
before downstream overlays**; uses only canonical completed-session MarketData
chains; reuses existing OLM thesis lifecycle; persists append-only DOI
families/assessments/rankings; retains ticker-level data exceptions **without
stopping or reducing the population**; complete structural family taxonomy
stored while a deterministic diversified bounded subset is valued/ranked; no
DOI component may call a provider, change direction, invalidate a thesis, grant
capital or remove an opportunity; governed runtime configuration active;
pre-DOI control-plane database retained as rollback point; formal acceptance
**pending one new evening artefact and the next valid Morning Gate**; the
read-only assessor reports this honestly and **cannot promote an old pre-DOI
run**.

**Numbers:**

| Claim | Value |
|---|---|
| DOI regression pack | **120 tests** pass |
| Tickers retained in production-data rehearsal | **20 / 20**, balanced CALL/PUT |
| Structurally valid contracts audited | **6,740** |
| Bounded contracts valued / ranked | **240** |
| Canonical chains reused | **20** |
| Provider calls | **0** |
| Exceptions raised | **0** |
| Live-path bound | **at most 12 contracts per family** |
| Persisted DOI-7 labels in live control plane | **0** |
| Accepted probability models | **none** |
| Accepted ranking policies | **none** |

Arithmetic note taken before testing: 20 tickers × 12 contracts = 240, which is
consistent with the "240 bounded contracts" claim only if **every** one of the
20 families hit the bound exactly. 6,740 / 20 = 337 structurally valid
contracts per family on average — comfortably above 12, so every family
plausibly saturates the bound. I will check whether 240 is a saturation
artefact or a coincidence, and whether any family fell short.
