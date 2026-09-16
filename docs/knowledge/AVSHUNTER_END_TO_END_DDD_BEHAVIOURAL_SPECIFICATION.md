# AVSHUNTER End-to-End DDD Behavioural Specification

## 1. Purpose

This specification defines how AVSHUNTER must behave from raw market observations through evidence, thesis formation, trade-expression valuation, ranking, live execution readiness, decision recording and eventual outcome validation.

The objective is not to create one central decision engine.

The objective is to create a continuous business flow in which:

- every domain concept has one authoritative owner;
- bounded contexts exchange immutable contracts;
- downstream contexts consume upstream decisions rather than silently recreating them;
- missing evidence remains missing;
- historical decisions remain reproducible;
- live trading and historical replay use the same domain behaviour;
- every decision can ultimately be compared with its realised outcome.

The existing knowledge base already separates Evidence, Thesis, Expression, Valuation, Ranking, Execution Readiness and Validation into distinct capabilities and contexts.

---

# 2. Fundamental Architecture Principle

AVSHUNTER has two different concepts that must not be confused.

## Business flow

There is an ordered business dependency:

```text
MARKET DATA
    ↓
MARKET STATE / STRUCTURE
    ↓
EVIDENCE
    ↓
THESIS
    ↓
EXPRESSION GENERATION
    ↓
VALUATION
    ↓
RANKING
    ↓
LIVE EXECUTION REVALUATION
    ↓
DECISION
    ↓
OUTCOME
    ↓
VALIDATION / LEARNING
```

## Software architecture

Those stages are not one application or one giant Python engine.

They are separate bounded contexts:

```text
┌────────────────────┐
│ Market Data        │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ Market Structure   │
└─────────┬──────────┘
          │ StructureAssessment
          ▼
┌────────────────────┐
│ Evidence           │
└─────────┬──────────┘
          │ EvidencePacket
          ▼
┌────────────────────┐
│ Thesis             │
└─────────┬──────────┘
          │ Thesis
          ▼
┌────────────────────┐
│ Expression         │
└─────────┬──────────┘
          │ CandidateExpressions
          ▼
┌────────────────────┐
│ Valuation          │
└─────────┬──────────┘
          │ ExpressionValuations
          ▼
┌────────────────────┐
│ Ranking            │
└─────────┬──────────┘
          │ OpportunityBook
          ▼
┌────────────────────┐
│ Execution          │
└─────────┬──────────┘
          │ Decision
          ▼
┌────────────────────┐
│ Outcome / Learning │
└────────────────────┘
```

Each context owns its own business language, rules, models and invariants.

The orchestrator coordinates them.

It does **not** make their domain decisions.

---

# 3. Non-Negotiable Domain Rules

The existing knowledge base already proposes rules including:

- missing is never neutral;
- one producer per field;
- units must be explicit;
- decide before depending upon a decision;
- authority must be explicit;
- labels must describe what was genuinely measured;
- inputs must be reproducible;
- releases must be clean;
- ownership should be concentrated rather than duplicated;
- logic must ultimately be measured against reality.

These rules become system invariants.

### Invariant A — one owner per business fact

For example:

```text
Probability             Evidence Context
Direction               Thesis Context
Trade Window            Thesis Context
Target                  Thesis Context
Invalidation            Thesis Context
Expression eligibility  Expression Context
EV                      Valuation Context
RAEV                    Valuation Context
Rank                    Ranking Context
Execution action        Execution Context
Outcome                 Outcome/Learning Context
```

A downstream context may reject an upstream object because it is unusable.

It may not rewrite the upstream object's meaning.

### Invariant B — unknown means unknown

This is forbidden:

```python
if evidence_missing:
    probability = 0.52
```

Required behaviour:

```python
if evidence_missing:
    return InsufficientEvidence(reason=...)
```

### Invariant C — published aggregates are immutable

Once a Thesis is published:

```text
direction
target
invalidation
trade window
evidence reference
structure reference
```

cannot subsequently be altered by valuation, contract selection, ranking or execution.

A genuine change in market conditions produces a **new thesis version**, not a mutation of the previous thesis.

---

# 4. Stage 0 — Run Identity and Point-in-Time Clock

Every pipeline run begins by establishing a deterministic run identity.

Required:

```text
run_id
decision_clock
market_session
data_as_of
environment
pipeline_version
configuration_version
```

The decision clock becomes authoritative for the entire run.

No context may independently call the current wall clock to determine historical or live state.

Every dataset must carry:

```text
observed_at
as_of
provider
request parameters
content hash
dataset_id
```

Historical values are append-only.

A `"latest"` file may be a user-facing convenience but must never become an authoritative decision input.

This allows:

```text
Live run:
decision_clock = 2026-09-16 09:45 ET

Historical replay:
decision_clock = 2025-05-14 09:45 ET
```

while using identical domain code.

---

# 5. Stage 1 — Market Data Context

## Responsibility

Answer:

> What market information was genuinely available at the decision time?

It owns ingestion, normalisation, timestamping, vendor translation, adjustments and data lineage.

It does not decide whether a stock is bullish or bearish.

## Inputs

Examples:

```text
OHLCV
corporate actions
option chains
option quotes
open interest
option volume
Greeks
interest-rate inputs
dividend information
earnings information
short interest
short volume
sector metadata
```

## Output

```text
MarketSnapshot
```

containing immutable references to canonical datasets.

## Failure behaviour

Missing input is recorded as missing.

It is never silently back-filled using future observations.

---

# 6. Stage 2 — Market Structure Context

## Responsibility

Answer:

> What does price structure objectively look like at this point in time?

It may produce observations such as:

```text
trend state
range state
structural high
structural low
Wyckoff phase hypothesis
support/resistance
volatility regime
structural target candidates
structural invalidation candidates
```

A structural pattern remains a **hypothesis generator**, not evidence that a trade works.

## Output aggregate

```text
StructureAssessment
```

Example:

```text
structure_assessment_id
ticker
as_of
candidate_direction
structural_levels
phase
trend_state
volatility_state
feature_vector
formula_version
source_dataset_ids
```

It must not contain:

```text
final trade direction
contract
EV
rank
BUY/SELL action
```

---

# 7. Stage 3 — Evidence Context

## Responsibility

Answer:

> Historically, when AVSHUNTER observed states like this one, what happened within the 1–20 trading-day opportunity window?

This context owns the empirical probability model.

The core outcome model remains:

```text
TARGET FIRST
STOP FIRST
TIMEOUT
```

but the Evidence Context must preserve **time-to-event**, because a thesis may succeed on Day 1, Day 4, Day 11 or any other session through Day 20.

## Core behaviour

For each candidate thesis, calculate evidence across the **1–20 session window** rather than reducing the thesis to a single arbitrary fixed holding day.

The evidence packet should preserve:

```text
p_target_first_by_session[1..20]
p_stop_first_by_session[1..20]
cumulative_p_target_by_session[1..20]
cumulative_p_stop_by_session[1..20]
p_still_open_by_session[1..20]
p_timeout_day20
timeout_return_distribution
time_to_target_distribution
time_to_stop_distribution
n_rows
n_eff
uncertainty interval
prior/shrinkage information
calibration statistics
```

This allows AVSHUNTER to distinguish:

```text
Trade A:
70% of successful historical paths resolve by Day 3

Trade B:
70% of successful historical paths resolve between Day 12 and Day 20
```

even if both ultimately have a similar target-hit probability.

That difference materially affects option selection, theta exposure and DTE requirements.

Overlapping observations must not be treated as independent observations.

## Output aggregate

```text
EvidencePacket
```

The packet is immutable.

## Failure state

If reliable evidence cannot be generated:

```text
EvidencePacket = NULL
EvidenceStatus = INSUFFICIENT_EVIDENCE
Reason = ...
```

No fabricated probability.

---

# 8. Stage 4 — Thesis Context

## Responsibility

Answer:

> Given the structure and historical evidence, what precisely is the market thesis, and during what 1–20 trading-day window is it expected to resolve?

The thesis must be constructed **before an option contract is selected**.

## Inputs

```text
StructureAssessment
EvidencePacket
1–20 day trading-window policy
```

## Direction behaviour

The Thesis Context assesses evidence support.

Possible states:

```text
SUPPORTED
OPPOSED
UNSUPPORTED
INSUFFICIENT_EVIDENCE
```

Evidence opposing the proposed structural direction must not automatically flip the direction.

It changes the assessment of the proposed thesis.

## Invalidation behaviour

Invalidation must be structural and must sit on the correct side of the reference price.

Missing invalidation means the thesis is incomplete.

## Target behaviour

Targets must originate from identifiable structural or approved statistical rules.

No artificial target may be created merely to make valuation possible.

If no valid target exists:

```text
target_state = NONE
target_price = NULL
```

and the Valuation Context must value stop/timeout behaviour accordingly.

## Trade-window behaviour

AVSHUNTER operates within a:

```text
1–20 trading-day opportunity window
```

The thesis is therefore **not predicting that the move happens specifically on Day 20**.

It is asserting:

> The anticipated move may begin and/or complete on any trading day from Day 1 through Day 20.

Accordingly, the evidence must model the probability and timing of resolution throughout the complete window.

Example:

```text
Day 1    trade may resolve
Day 2    trade may resolve
Day 3    trade may resolve
...
Day 10   trade may resolve
...
Day 20   final permitted thesis window
```

Day 20 is the **maximum planned opportunity horizon**, not the expected exit day.

The expected holding duration should be derived from the distribution of historical first-passage times.

Therefore the Thesis aggregate should distinguish:

```text
trade_window_min_sessions = 1
trade_window_max_sessions = 20

expected_resolution_session
median_resolution_session
resolution_session_quantiles
```

where evidence quality permits.

This is preferable to setting a single artificial fixed hold and pretending the trade must conform to that specific date.

The thesis may instead say:

```text
Expected resolution:
Days 3–8

Permitted thesis window:
Days 1–20
```

or:

```text
Expected resolution:
Days 8–15

Permitted thesis window:
Days 1–20
```

The expected resolution range helps valuation and expression selection, while the maximum 20-day window preserves the original thesis opportunity.

## Output aggregate

```text
Thesis
```

Example:

```text
thesis_id
ticker
evidence_session
reference_price
direction
direction_state
edge
edge_ci
invalidation_price
stop_distance_sigma
target_state
target_price
target_distance_sigma

trade_window_min_sessions = 1
trade_window_max_sessions = 20

expected_resolution_session
median_resolution_session
resolution_session_quantiles

evidence_packet_id
structure_assessment_id
formula_version
```

Once published, it is frozen.

---

# 9. Stage 5 — Expression Context

## Responsibility

Answer:

> What tradeable instruments are capable of expressing this already-defined 1–20 day thesis?

This stage does not choose the thesis.

It searches ways to express it.

## Dependency direction

Correct:

```text
Thesis says:

BULL

Opportunity can resolve:
Day 1 through Day 20

Evidence suggests:
highest probability of resolution Days 4–9

Expression Context asks:

Which options can safely express
that complete thesis window?
```

Incorrect:

```text
Found option with 7 DTE
therefore shorten thesis to 7 days.
```

The instrument must fit the thesis.

The thesis must never be shortened merely because an attractive contract expires earlier.

## DTE behaviour

A candidate option must have enough remaining life to cover:

```text
maximum thesis window
+
approved exit/safety buffer
```

Therefore, conceptually:

```text
minimum_required_DTE
    =
20 trading sessions
+
exit buffer
```

converted appropriately into listed-option calendar DTE.

AVSHUNTER may also compare contracts with more DTE where the additional time reduces theta risk or improves valuation.

The Expression Context should therefore search a DTE range rather than force one expiry.

The selected contract is determined **after valuation**, not simply because it sits closest to the expected resolution day.

## Generation behaviour

Candidate expressions are generated after the thesis is frozen and before valuation.

Expression scope remains a business/governance configuration.

## Tradeability

An expression can be rejected only for objective execution constraints such as:

```text
missing/two-sided quote failure
spread over approved limit
insufficient market size/OI
stale quote
DTE insufficient to cover the thesis window
```

Ordinary liquidity costs inside approved limits belong in valuation.

## Output

```text
CandidateExpressionSet
```

Each rejected candidate remains auditable with a reason code.

---

# 10. Stage 6 — Valuation Context

## Responsibility

Answer:

> Given the same thesis and possible market paths over Days 1–20, what is each expression economically worth?

This is the sole owner of trade economics.

## Required inputs

```text
Frozen Thesis
EvidencePacket
CandidateExpression
option quote
volatility inputs
rate
dividend assumptions
cost model
pricing model
```

## Common-path rule

Every expression for the same thesis must be valued against the **same underlying path set**.

## Time-to-event valuation

This is crucial for the 1–20 day design.

The option must be repriced on the session where the underlying path actually resolves.

Example:

```text
Path A
Target hit Day 2
→ option valued/exited Day 2

Path B
Stop hit Day 5
→ option valued/exited Day 5

Path C
Target hit Day 13
→ option valued/exited Day 13

Path D
No barrier by Day 20
→ timeout valuation Day 20
```

The pipeline must not assume:

```text
all winners exit Day 20
```

or:

```text
all trades use one fixed holding period.
```

Time decay, remaining DTE and IV behaviour must therefore vary by path.

## Expected value

Conceptually:

```text
EV = Σ path_weight × path_P&L
```

where each path contains its own:

```text
exit session
exit spot
remaining DTE
exit IV
exit option value
transaction costs
```

Then:

```text
EV/R = EV / capital_at_risk
```

and uncertainty/stress produces:

```text
RAEV = lower-bound EV per dollar at risk
```

## Missing-data rule

Missing critical inputs produce:

```text
NOT_VALUED
reason_code
```

not substituted defaults.

## Output aggregate

```text
ExpressionValuation
```

Example:

```text
valuation_id
expression_id
thesis_id
evidence_packet_id
entry_cost
capital_at_risk
expected_pnl
ev_per_risk
raev

expected_exit_session
exit_session_distribution

confidence_interval
stress_results
cost_assumptions
volatility_assumptions
pricing_model_version
valuation_as_of
```

---

# 11. Stage 7 — Volatility / Convexity Domain

This can exist as a supporting bounded context or domain service consumed by Valuation.

Its responsibility is:

> What volatility is realised, what volatility is expected over the relevant part of the 1–20 day window, what volatility is being charged, and how attractive is the convexity?

Rather than producing only one forecast horizon, the volatility service should support the thesis timing distribution where practical.

For example:

```text
sigma_forecast_5d
sigma_forecast_10d
sigma_forecast_20d
```

or an equivalent term-aware representation.

Valuation can then use the forecast appropriate to each simulated exit path.

IV percentile requires genuine historical daily IV observations.

Cheap convexity remains an explanatory/ranking characteristic.

It is not the ultimate monetary decision.

Output:

```text
VolatilityAssessment
CheapConvexityProfile
```

These become inputs to Valuation and Ranking.

They do not change the Thesis.

---

# 12. Stage 8 — Ranking Context

## Responsibility

Answer:

> Across all already-valued opportunities, what order should the trader consider them?

The Ranking Context does not recreate:

```text
direction
probability
target
EV
RAEV
```

It consumes those authoritative values.

## Within-thesis selection

For each Thesis:

```text
strongest expression =
highest RAEV
```

with approved deterministic tie-breaks.

## Across-thesis ranking

Primary principle:

```text
RAEV descending
cheap-convexity quality descending
liquidity cost ascending
deterministic tie-break
```

## Negative edge

A candidate with:

```text
RAEV <= 0
```

remains visible as:

```text
NO_POSITIVE_EDGE
```

rather than disappearing through an unexplained gate.

## Portfolio awareness

Ranking may additionally report:

```text
sector concentration
cluster concentration
correlation concentration
```

without changing underlying valuation.

## Output aggregate

```text
OpportunityBook
```

---

# 13. Stage 9 — Execution Readiness Context

## Responsibility

Answer:

> Is the previously ranked opportunity still economically valid and executable now?

Execution does not recreate Discovery.

Execution is live revalidation.

## Correct behaviour

```text
Existing Frozen Thesis
        ↓
Current market price
        ↓
Has thesis invalidated?
   YES → INVALIDATED
   NO
        ↓
How much of the 1–20 day window remains?
        ↓
Refresh expression quotes
        ↓
Re-run tradeability
        ↓
Re-run canonical valuation
        ↓
Re-run canonical ranking
        ↓
Apply execution policy
```

The remaining opportunity window matters.

Example:

A thesis created on Day 0 may still be valid on Day 4.

Its remaining thesis window becomes approximately:

```text
Day 5 through Day 20
```

relative to the original thesis clock.

AVSHUNTER should therefore not restart a fresh 20-day clock every morning unless a genuinely new thesis is published.

Execution owns approved actions such as:

```text
BUY_NOW
BUY_SMALL
MONITOR
NO_EDGE
INVALIDATED
```

It does not own:

```text
direction
target
maximum thesis window
probability model
RAEV formula
```

---

# 14. Stage 10 — Decision Ledger

Before an actionable decision leaves the pipeline, AVSHUNTER writes one immutable decision record.

Required lineage includes:

```text
decision_id
run_id
decision_clock
ticker
thesis_id
structure_assessment_id
evidence_packet_id
expression_id
valuation_id
ranking_book_id
rank
execution_action

trade_window_min_sessions
trade_window_max_sessions
thesis_age_sessions
remaining_window_sessions

input_dataset_ids
formula_versions
configuration_versions
as_of timestamps
```

The decision record must be written before the outcome is known.

---

# 15. Stage 11 — Outcome Maturation

Outcome generation is deterministic.

The outcome engine monitors the thesis path from the decision/session origin through a maximum of 20 trading sessions.

A trade may mature early.

Examples:

```text
Day 1 target hit
→ TARGET_FIRST
→ mature immediately

Day 4 stop hit
→ STOP_FIRST
→ mature immediately

Day 13 target hit
→ TARGET_FIRST
→ mature immediately

Day 20 neither touched
→ TIMEOUT
→ mature at Day 20
```

Possible underlying outcomes:

```text
TARGET_FIRST
STOP_FIRST
TIMEOUT
AMBIGUOUS
```

The system must record:

```text
first_touch_session
days_to_resolution
```

not just final outcome.

This timing becomes critical evidence for future contract selection and valuation.

---

# 16. Stage 12 — Validation and Learning Context

## Responsibility

Answer:

> Did AVSHUNTER's claimed probabilities, timing expectations, valuations, selections and rankings correspond with reality?

Validation must assess both **directional correctness** and **time-to-resolution correctness**.

For example:

```text
Did target occur within Day 1–20?
Did stop occur first?
When did resolution occur?
Was the expected resolution distribution calibrated?
Did contracts with sufficient DTE outperform shorter expressions?
Was theta burden estimated correctly?
```

Historical validation must use:

```text
point-in-time inputs
no look-ahead
purging
embargo
walk-forward testing
realistic costs
same production domain services
```

Validation does not modify old decisions.

It produces evidence for future model versions.

---

# 17. Domain Events and Contracts

Recommended domain events:

```text
MarketSnapshotPublished
        ↓
StructureAssessmentPublished
        ↓
EvidencePacketPublished
        ↓
ThesisPublished
        ↓
ExpressionSetGenerated
        ↓
ExpressionValuationPublished
        ↓
OpportunityBookPublished
        ↓
ExecutionDecisionRecorded
        ↓
OutcomeMatured
        ↓
ValidationCompleted
```

Every event carries references rather than duplicated mutable state.

---

# 18. Application Orchestrator Behaviour

Conceptually:

```python
snapshot = market_data.capture(run_context)

structure = market_structure.assess(
    snapshot=snapshot,
    run_context=run_context,
)

evidence = evidence_context.evaluate(
    structure=structure,
    window_min=1,
    window_max=20,
    run_context=run_context,
)

thesis = thesis_context.build(
    structure=structure,
    evidence=evidence,
    trade_window=(1, 20),
    run_context=run_context,
)

if thesis.is_incomplete:
    record_non_actionable(thesis)
    stop_processing_thesis()

expressions = expression_context.generate(
    thesis=thesis,
    snapshot=snapshot,
)

valuations = valuation_context.value_all(
    thesis=thesis,
    evidence=evidence,
    expressions=expressions,
    market_snapshot=snapshot,
)

book = ranking_context.rank(
    valuations=valuations,
)

decision = execution_context.evaluate(
    opportunity_book=book,
    current_market_snapshot=live_snapshot,
)

decision_ledger.record(decision)
```

The orchestrator coordinates.

It does not own domain decisions.

---

# 19. Broken-Flow Prevention Rules

| Condition | Required behaviour |
|---|---|
| Market data missing | mark affected data unavailable |
| State cannot be derived | no Evidence request for that state |
| Evidence insufficient | `INSUFFICIENT_EVIDENCE` |
| Invalidation missing | Thesis incomplete |
| Required target missing | `target_state=NONE`; use supported stop/timeout valuation |
| Valid 1–20 day window cannot be established | Thesis incomplete |
| No expression covers maximum thesis window + exit buffer | `NO_TRADEABLE_EXPRESSION` |
| Pricing input missing | expression=`NOT_VALUED` |
| All expressions unvalued | thesis cannot enter ranked actionable set |
| RAEV ≤ 0 | retain as `NO_POSITIVE_EDGE` |
| Thesis invalidated before Day 20 | `INVALIDATED` |
| Thesis reaches Day 20 unresolved | `TIMEOUT` |
| Quote changes | revalue; do not change Thesis |
| Outcome already resolves before Day 20 | mature immediately |
| Historical replay data missing | record missing; never substitute future data |

A pipeline does not remain unbroken by forcing every ticker through to BUY/SELL.

It remains unbroken when every valid state has a defined next state.

---

# 20. State Machine

At candidate level:

```text
OBSERVED
   ↓
STRUCTURE_ASSESSED
   ↓
EVIDENCE_ASSESSED
   ↓
THESIS_PUBLISHED
   ↓
EXPRESSIONS_GENERATED
   ↓
EXPRESSIONS_VALUED
   ↓
RANKED
   ↓
LIVE_REVALUED
   ↓
DECISION_RECORDED
   ↓
OUTCOME_PENDING
   │
   ├── Day 1 resolution
   ├── Day 2 resolution
   ├── ...
   ├── Day 19 resolution
   └── Day 20 resolution/timeout
   ↓
OUTCOME_MATURED
   ↓
VALIDATED
```

Legitimate terminal branches include:

```text
INSUFFICIENT_EVIDENCE
INCOMPLETE_THESIS
NO_TRADEABLE_EXPRESSION
NOT_VALUED
NO_POSITIVE_EDGE
INVALIDATED
DATA_UNAVAILABLE
```

These are valid domain outcomes, not system failures.

---

# 21. Replay and Live Trading Must Share the Same Domain Path

Historical replay must run:

```text
HistoricalSnapshot
        ↓
same Market Structure domain
        ↓
same Evidence domain
        ↓
same Thesis domain
        ↓
same Expression domain
        ↓
same Valuation domain
        ↓
same Ranking domain
```

with the historical clock injected.

The 1–20 day outcome path is then replayed exactly as production would experience it.

---

# 22. Replication Comes Before Decision Authority

The target progression remains:

```text
Logic implemented
      ↓
technical/design verification
      ↓
historical replication
      ↓
walk-forward validation
      ↓
forward shadow validation
      ↓
decision authority
```

A Python module being implemented correctly does not by itself mean its trading conclusion is correct.

---

# 23. Domain Ownership Matrix

| Domain concept | Authoritative owner | Downstream mutation |
|---|---|---|
| Market observation | Market Data | Forbidden |
| Structural state | Market Structure | Forbidden |
| Historical probability | Evidence | Forbidden |
| Time-to-resolution distribution | Evidence | Forbidden |
| Evidence uncertainty | Evidence | Forbidden |
| Direction | Thesis | Forbidden |
| Target | Thesis | Forbidden |
| Invalidation | Thesis | Forbidden |
| 1–20 day trade window | Thesis | Forbidden |
| Expression definition | Expression | Forbidden |
| Tradeability status | Expression | Rechecked, not historically overwritten |
| Volatility forecast | Volatility domain | Versioned |
| Entry/exit economics | Valuation | Forbidden |
| EV | Valuation | Forbidden |
| EV/R | Valuation | Forbidden |
| RAEV | Valuation | Forbidden |
| Rank | Ranking | New book/version only |
| Execution action | Execution | New decision only |
| Realised outcome | Outcome | Forbidden |
| Days to resolution | Outcome | Forbidden |
| Calibration result | Validation | New model/version only |

---

# 24. What Must Not Happen

Forbidden behaviours include:

```text
Evidence returns no match
→ downstream substitutes 52%

Thesis allows Day 1–20
→ option selector finds 7 DTE
→ thesis shortened to 7 days

Evidence expects resolution around Day 8
→ pipeline assumes every trade exits Day 8

Target is hit Day 3
→ valuation still models exit on Day 20

Trade remains open Day 6
→ execution restarts a new 20-day window

Thesis says BULL
→ execution silently converts it to PUT

Valuation computes negative EV
→ heuristic score makes it positive

Historical replay lacks original input
→ today's latest value is substituted

Published thesis changes
→ old thesis row overwritten
```

Every one breaks domain ownership, temporal integrity or economic consistency.

---

# 25. Correct End-to-End Behaviour in One Sentence

AVSHUNTER should behave as a chain of autonomous bounded contexts in which **market facts create structure, structure plus historical evidence create an immutable directional thesis with a 1–20 trading-day opportunity window, evidence models when during that window the target, stop or timeout is likely to occur, expression generation finds instruments capable of surviving the complete thesis window, valuation reprices each expression on the actual path-specific exit day, ranking orders those economically comparable opportunities, execution revalidates rather than reinvents the thesis, and every decision is recorded before its realised outcome is known so the entire chain can ultimately learn whether both the direction and timing assumptions were correct.**

---

# 26. Target Architecture

```text
                     ┌─────────────────────────┐
                     │     RUN CONTEXT         │
                     │ clock / IDs / versions  │
                     └───────────┬─────────────┘
                                 │
                                 ▼
                     ┌─────────────────────────┐
                     │ C1 MARKET DATA          │
                     └───────────┬─────────────┘
                                 │ MarketSnapshot
                                 ▼
                     ┌─────────────────────────┐
                     │ C3 MARKET STRUCTURE     │
                     └───────────┬─────────────┘
                                 │ StructureAssessment
                                 ▼
                     ┌─────────────────────────┐
                     │ C4 EVIDENCE             │
                     │ Day 1 → Day 20          │
                     └───────────┬─────────────┘
                                 │ EvidencePacket
                                 ▼
                     ┌─────────────────────────┐
                     │ C5 THESIS               │
                     │ 1–20 day opportunity    │
                     └───────────┬─────────────┘
                                 │ Frozen Thesis
                                 ▼
                     ┌─────────────────────────┐
                     │ C6 EXPRESSION           │
                     │ DTE must fit thesis     │
                     └───────────┬─────────────┘
                                 │ CandidateExpressions
                                 ▼
        ┌───────────────────────────────────────────────┐
        │ C7 VALUATION                                 │
        │ path-specific Day 1 → Day 20 exits           │
        └───────────────────────┬───────────────────────┘
                                │ ExpressionValuations
                                ▼
                     ┌─────────────────────────┐
                     │ C8 RANKING              │
                     └───────────┬─────────────┘
                                 │ OpportunityBook
                                 ▼
                     ┌─────────────────────────┐
                     │ C9 EXECUTION READINESS  │
                     │ remaining window        │
                     └───────────┬─────────────┘
                                 │ Decision
                                 ▼
                     ┌─────────────────────────┐
                     │ DECISION LEDGER         │
                     └───────────┬─────────────┘
                                 │
                      target / stop / timeout
                         on Day 1 → Day 20
                                 │
                                 ▼
                     ┌─────────────────────────┐
                     │ VALIDATION / LEARNING   │
                     └───────────┬─────────────┘
                                 │
                      future model versions
                                 │
                                 └──────► future runs
```

This closes the loop without forcing AVSHUNTER into artificial 5-, 10- or 20-day holding buckets.

The **20-day value is the outer boundary of the thesis opportunity window**. The actual trade can resolve on any session from Day 1 through Day 20.
