# AVSHUNTER End-to-End DDD Behavioural Specification

## Document control

| Item | Value |
|---|---|
| Version | **1.1 — reconciled and signed off** (16 Sep 2026) |
| Previous version | 1.0 (ACK, 16 Sep 2026), preserved in git history |
| Status | **GOVERNING behavioural specification.** Signed off by ACK with sign-off corrections S1–S5 incorporated (Appendix A.5–A.6). |
| Incorporates | Review changes C1–C14 (`REVIEW_DDD_BEHAVIOURAL_SPECIFICATION_20260916.md`), ACK decisions C3 / C4 / C9 / Q1 (review §6), agreed refinements R-A to R-H, sign-off corrections S1–S5 (Appendix A), configuration governance (Appendix B), investigation findings on EV, GEX, IV history and data freshness (`Enhancements/`) |

### Document authority

```text
BUSINESS DECISIONS (ACK)
        ↓
THIS SPECIFICATION              governs behaviour, ownership, contracts, states
        ↓
DOMAIN METHOD NOTES 01–07       govern statistical and financial method correctness
        ↓
BUSINESS DOMAIN DESIGN ADDENDUM
        ↓
END-TO-END IMPLEMENTATION / MIGRATION DESIGN
        ↓
CODE
```

Rules:

- A lower document may add detail. It may not contradict a higher document.
- Where this specification and a method note disagree on **method correctness** (for example, which estimator is statistically sound), the conflict is escalated to ACK. It is not resolved silently in either direction.
- Older documents (decision-path map, end-to-end fix design, addendum) are subordinate. Any section that contradicts this specification is **superseded** and must be marked as such.
- The existing Python pipeline is **not** a design reference. It is an asset mine: selected components are reused behind the contracts defined here (strangler migration).

---

## 1. Purpose

This specification defines how AVSHUNTER must behave from raw market observations through eligibility, evidence, thesis formation, trade-expression valuation, ranking, live execution readiness, decision recording and eventual outcome validation.

The business objective is to find, for every supportable directional thesis, **the strongest way to express it** and whether **the money is in the option or in the ticker**, ranked by risk-adjusted expected value rather than filtered by gates.

The objective is not to create one central decision engine.

The objective is to create a continuous business flow in which:

- every domain concept has one authoritative owner;
- bounded contexts exchange immutable contracts;
- downstream contexts consume upstream decisions rather than silently recreating them;
- missing evidence remains missing;
- historical decisions remain reproducible;
- live trading and historical replay use the same domain behaviour;
- every decision, and every alternative that was not chosen, can ultimately be compared with its realised outcome.

The existing knowledge base already separates Evidence, Thesis, Expression, Valuation, Ranking, Execution Readiness and Validation into distinct capabilities and contexts. This specification adds Universe & Eligibility, Volatility & Convexity, the Decision Ledger and Presentation as explicit contexts.

### Bounded contexts (governing numbering)

| # | Context | Aggregate / output | Business question |
|---|---|---|---|
| C0 | Run Context | `RunContext` | Which run, which clock, which release, which data? |
| C1 | Market Data | `MarketSnapshot` | What was genuinely observable at the decision time, and is it fresh? |
| C2 | Universe & Eligibility | `UniverseSnapshot`, `EligibilityAssessment` | May this ticker be analysed, and if not, why? |
| C3 | Market Structure | `StructureAssessment` with `CandidateGeometry` | What does structure look like, and which target/invalidation geometries does it propose? |
| C4 | Evidence | `EvidencePacket` per geometry | Historically, across the market, what happened from states like this, and when? |
| C5 | Thesis | `Thesis` (aggregate root) | What exactly do we believe, over which window, and when is it wrong? |
| C6 | Expression | `CandidateExpressionSet` | What are all the tradeable ways to express this thesis? |
| C7 | Volatility & Convexity | `VolatilityAssessment`, `CheapConvexityProfile` | What volatility is expected, what is being charged, and is the convexity cheap? |
| C8 | Valuation | `ExpressionValuation` | How much money is in each expression? |
| C9 | Ranking | `OpportunityBook` | Which expression is strongest per thesis, and how do all opportunities order? |
| C10 | Execution Readiness | `ExecutionDecision` | With live quotes now, is the ranked expression still valid and executable? |
| C11 | Decision Ledger | `LedgerRecord` | What was decided, and what was not, before the outcome was known? |
| C12 | Outcome | `UnderlyingOutcome`, `ExpressionOutcome` | What actually happened to the underlying and to each expression? |
| C13 | Validation & Learning | `ValidationReport`, model versions | Were probabilities, timing, valuations, selections and ranks right? |
| C14 | Presentation | `LabReadModel` | What does the trader see? (read-only) |

Stage numbers in this document equal context numbers.

---

# 2. Fundamental Architecture Principle

AVSHUNTER has two different concepts that must not be confused.

## Business flow

There is an ordered business dependency:

```text
RUN CONTEXT
    ↓
MARKET DATA
    ↓
UNIVERSE & ELIGIBILITY
    ↓
MARKET STRUCTURE  (candidate geometries)
    ↓
EVIDENCE          (per candidate geometry)
    ↓
THESIS            (selects geometry, frozen)
    ↓
EXPRESSION GENERATION + TRADEABILITY   (all eligible expressions)
    ↓
VOLATILITY & CONVEXITY
    ↓
VALUATION         (all tradeable expressions, common path set)
    ↓
RANKING           (RAEV; strongest expression wins)
    ↓
LIVE EXECUTION REVALUATION
    ↓
DECISION
    ↓
UNDERLYING + EXPRESSION OUTCOMES
    ↓
VALIDATION / LEARNING
```

The Decision Ledger is **not a step at the end**. Every context from Universe & Eligibility onwards writes its published output to the ledger as it is produced (§15).

There is no "contract selector" stage. No context chooses a single contract before valuation. Selection is the result of valuing all tradeable expressions and ranking them.

## Software architecture

Those stages are not one application or one giant Python engine.

They are separate bounded contexts:

```text
┌────────────────────┐
│ Run Context        │
└─────────┬──────────┘
          │ RunContext
          ▼
┌────────────────────┐
│ Market Data        │
└─────────┬──────────┘
          │ MarketSnapshot
          ▼
┌────────────────────┐
│ Universe &         │
│ Eligibility        │
└─────────┬──────────┘
          │ EligibilityAssessment
          ▼
┌────────────────────┐
│ Market Structure   │
└─────────┬──────────┘
          │ StructureAssessment + CandidateGeometries
          ▼
┌────────────────────┐
│ Evidence           │
└─────────┬──────────┘
          │ EvidencePacket (per geometry)
          ▼
┌────────────────────┐
│ Thesis             │
└─────────┬──────────┘
          │ Thesis (frozen)
          ▼
┌────────────────────┐        ┌────────────────────┐
│ Expression         │        │ Volatility &       │
│                    │        │ Convexity          │
└─────────┬──────────┘        └─────────┬──────────┘
          │ CandidateExpressionSet      │ VolatilityAssessment
          ▼                             ▼
┌───────────────────────────────────────────────────┐
│ Valuation                                         │
└─────────────────────────┬─────────────────────────┘
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
          │ ExecutionDecision
          ▼
┌────────────────────┐
│ Outcome            │
└─────────┬──────────┘
          ▼
┌────────────────────┐
│ Validation /       │
│ Learning           │
└────────────────────┘

Cross-cutting:  Decision Ledger (written by every context)
Read-only:      Presentation (Lab)
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
Eligibility             Universe & Eligibility Context
Candidate geometry      Market Structure Context
Probability / timing    Evidence Context
Direction               Thesis Context
Trade Window            Thesis Context
Target                  Thesis Context
Invalidation            Thesis Context
Expression eligibility  Expression Context
Volatility forecast     Volatility & Convexity Context
EV                      Valuation Context
RAEV                    Valuation Context
Rank                    Ranking Context
Execution action        Execution Context
Outcome                 Outcome Context
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

A failure to compute must never be shown as a neutral or passing value (for example a default score, a 0.5 regime value, a constant convexity score, or a status of PASS).

### Invariant C — published aggregates are immutable

Once a Thesis is published:

```text
direction
target
invalidation
trade window and window clock
evidence reference
structure reference
selected candidate geometry
```

cannot subsequently be altered by valuation, expression generation, ranking or execution.

A genuine change in market conditions produces a **new thesis version** under the supersession rules in §9, not a mutation of the previous thesis.

### Invariant D — direction symmetry

BEAR theses use mirrored evidence, mirrored barriers and mirrored valuation. No statistic, threshold or payoff may be computed upside-only and reused for the downside.

### Invariant E — data hygiene

Evidence and validation are built only from cleaned, split/dividend-adjusted, outlier-validated returns with **point-in-time labels**: only what was observable by the evidence session is used. A path that has already reached its target or invalidation is a fully observed event at its touch session; a path that has not yet resolved contributes as right-censored at its current age ("still open after *k* sessions"). Nothing after the evidence session is ever used. A return that fails validation is excluded with a recorded reason, never capped silently and never kept.

### Invariant F — freshness is explicit

Every consumer declares the session it requires. Data older than that session is `STALE`, never `COMPLETE`, and is never used silently as if it were current.

### Invariant G — authority is earned

No model, score or signal influences a gate, a valuation or a rank until it has passed the validation progression in §24. Until then it may only be displayed, clearly labelled as advisory or legacy.

---

# 4. Stage 0 — Run Identity and Point-in-Time Clock

Every pipeline run begins by establishing a deterministic run identity.

Required:

```text
run_id
decision_clock
market_session
evidence_session            last completed session used as evidence
data_as_of
environment
pipeline_version
release_id
clean_tree                  true only if the release was built from a clean, tagged tree
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

> What market information was genuinely available at the decision time, and is it current for the session being decided?

It owns ingestion, normalisation, timestamping, vendor translation, adjustments, data lineage, capture completeness and freshness.

It does not decide whether a stock is bullish or bearish.

## Inputs

Examples:

```text
OHLCV
corporate actions
option chains
option quotes
open interest (with its own as-of date; normally prior session)
option volume
provider Greeks
interest-rate inputs
dividend information
earnings calendar
short interest
short volume
borrow availability and fee
sector metadata
```

## Capture behaviour

- The evening run captures a **fixed capture panel**: the eligible universe plus benchmark instruments (at minimum SPY and QQQ). It does not capture only the day's candidates, because candidate-only capture produces selection-biased history.
- Captured data is written to canonical storage and projected to history **in the same run**, with a receipt per ticker and session.
- Provider requests for a completed current session and for historical sessions are distinguished explicitly (a historical-only parameter must not be sent for the current session).
- Capture coverage is measured. Coverage below the approved threshold is a visible run-health failure, not a log warning.

## Output

```text
MarketSnapshot
```

containing immutable references to canonical datasets, a coverage report and a freshness state per dataset.

## Failure behaviour

Missing input is recorded as missing (`DATA_UNAVAILABLE`).

History older than the required session is recorded as `STALE_HISTORY`.

Neither is ever silently back-filled using future observations or replaced by the latest available value.

---

# 6. Stage 2 — Universe & Eligibility Context

## Responsibility

Answer:

> Which tickers may be analysed for this session, and for every ticker that may not, exactly why?

This stage exists so that data-quality and eligibility exclusions are never reported as "no signal".

## Behaviour

- Maintains a **point-in-time universe**, including names later delisted, so that replay and validation are free of survivorship bias.
- Computes eligibility features from the `MarketSnapshot` (price range, average daily dollar volume, ATR, minimum bar history, bar freshness).
- Emits one `EligibilityAssessment` per ticker with state `ELIGIBLE` or `NOT_ELIGIBLE` and explicit reason codes, for example:

```text
PRICE_RANGE
ADV
ATR
MIN_BARS
STALE_BARS
INCOMPLETE_BARS
DATA_UNAVAILABLE
```

- Stale or incomplete bars are **data-integrity** exclusions and are labelled as such.
- Eligibility decides whether the **underlying** can be analysed. It does not decide which instruments exist. Instrument availability is recorded as **capabilities** on an eligible ticker, never as a ticker-level exclusion:

```text
options_available        true | false   (false → OPTIONS_DATA_UNAVAILABLE)
long_shares_available    true | false
short_shares_available   true | false | BORROW_DATA_UNAVAILABLE
```

A ticker without an option chain remains `ELIGIBLE` and can still be expressed through shares. The Expression Context generates only the instrument families its capabilities allow.

Hard exclusions anywhere in AVSHUNTER are limited to **integrity** and **tradeability**. Eligibility thresholds are integrity/tradeability thresholds, versioned in configuration, and every exclusion is counted and recorded.

## Output

```text
UniverseSnapshot
EligibilityAssessment (per ticker)
```

It must not contain direction, probability, EV or rank.

---

# 7. Stage 3 — Market Structure Context

## Responsibility

Answer:

> What does price structure objectively look like at this point in time, and which target/invalidation geometries does it propose?

It may produce observations such as:

```text
trend state
range state
structural high
structural low
Wyckoff phase hypothesis
support/resistance
volatility regime
dealer positioning (net GEX, gamma flip, GEX call/put walls)
structural target candidates
structural invalidation candidates
```

A structural pattern remains a **hypothesis generator**, not evidence that a trade works.

## Candidate geometries

Market Structure proposes one or more **candidate geometries** for each candidate direction. Each geometry is a structurally derived pair of levels:

```text
geometry_id
direction                      BULL | BEAR
reference_price
target_state                   LEVEL | NONE
target_price                   NULL when target_state = NONE
invalidation_price             required; correct side of reference price
target_distance_sigma
invalidation_distance_sigma
derivation_rule                e.g. prior structural high, range boundary
formula_version
```

Rules:

- Levels come only from identifiable structural rules. No artificial target (such as a fixed R-multiple) may be created to make evidence or valuation possible.
- A geometry without a valid invalidation level is not proposed.
- Distances are expressed in volatility units so that Evidence can compare like with like across tickers.

Market Structure proposes geometries. It does not choose between them — the Thesis does (§9).

## Dealer positioning

Where option data allows, Market Structure computes dealer gamma exposure with one engine for every ticker (dollar gamma per 1% move; flip from re-pricing gamma across a spot grid; GEX walls on the correct side of spot). Missing or insufficient data gives `GEX_UNAVAILABLE`, never a neutral value.

Dealer positioning is a structural **observation**. It gains authority over thesis support, valuation or rank only after validation shows it adds value (Invariant G).

## Output aggregate

```text
StructureAssessment
```

Example:

```text
structure_assessment_id
ticker
as_of
candidate_directions
candidate_geometries[]
structural_levels
phase
trend_state
volatility_state
dealer_positioning (with availability state)
feature_vector
formula_version
source_dataset_ids
```

It must not contain:

```text
final trade direction
selected geometry
contract
EV
rank
BUY/SELL action
macro regime or macro score
```

---

# 8. Stage 4 — Evidence Context

## Responsibility

Answer:

> Historically, across the point-in-time market universe, when price was in states like this one and a geometry like this one applied, what happened within the 1–20 trading-session opportunity window — and when?

The base sample is the historical point-in-time market universe. AVSHUNTER's own recorded decision outcomes are an **additional calibration source**, not the base sample.

This context owns the empirical probability and timing model.

The core outcome model remains:

```text
TARGET FIRST
STOP FIRST
TIMEOUT
```

but the Evidence Context must preserve **time-to-event**, because a thesis may resolve on Day 1, Day 4, Day 11 or any other session through Day 20.

## Core behaviour

For **each candidate geometry** supplied by Market Structure, Evidence calculates first-passage evidence across the **1–20 session window** using the geometry's target and invalidation distances. When a geometry has `target_state = NONE`, Evidence returns stop-first and timeout distributions only.

Evidence does not own, move or invent the levels. It evaluates the levels it is given.

## Estimation method

Session-by-session outcomes are three competing states through time: target reached first, stop reached first, still unresolved. Evidence must therefore use a **discrete-time competing-risks survival formulation**, not 20 separate raw per-session frequencies:

- cumulative incidence of target-first and stop-first by session 1..20 (Aalen-Johansen estimator or an equivalent discrete-hazard model);
- smoothing and shrinkage of hazards towards pooled (less specific) states when the specific state is sparse;
- `n_eff` counted in independent time blocks, because overlapping observations are not independent;
- uncertainty by block bootstrap;
- touches measured on intraday high/low; when both barriers are touched in the same session the order is unknown → `AMBIGUOUS`, counted conservatively as stop-first for estimation and the count recorded;
- point-in-time labels per Invariant E: resolved paths as events at their touch session, unresolved recent paths right-censored at their current age, so evidence stays current to the last completed session; returns cleaned per Invariant E; BEAR mirrored per Invariant D.

Method detail and references belong to knowledge note 01.

## Evidence packet

The evidence packet should preserve, per geometry:

```text
evidence_packet_id
geometry_id
cumulative_incidence_target_by_session[1..20]
cumulative_incidence_stop_by_session[1..20]
survival_unresolved_by_session[1..20]
p_target_first_by_day20
p_stop_first_by_day20
p_timeout_day20
timeout_return_distribution
time_to_target_distribution
time_to_stop_distribution
n_rows
n_eff
uncertainty intervals (block bootstrap)
prior / shrinkage information
ambiguous_count
calibration statistics (whether and when)
sample_definition and data_version
```

This allows AVSHUNTER to distinguish:

```text
Trade A:
70% of successful historical paths resolve by Day 3

Trade B:
70% of successful historical paths resolve between Day 12 and Day 20
```

even if both ultimately have a similar target-hit probability.

That difference materially affects expression choice, theta exposure and each expression's last exit session.

## Output aggregate

```text
EvidencePacket (one per candidate geometry)
```

Each packet is immutable.

## Failure state

If reliable evidence cannot be generated for a geometry:

```text
EvidencePacket = NULL
EvidenceStatus = INSUFFICIENT_EVIDENCE
Reason = ...
```

No fabricated probability.

---

# 9. Stage 5 — Thesis Context

## Responsibility

Answer:

> Given the structure and historical evidence, what precisely is the market thesis, which geometry does it adopt, and during what 1–20 trading-session window is it expected to resolve?

The thesis must be constructed **before any expression is generated**.

## Inputs

```text
StructureAssessment (with candidate geometries)
EvidencePackets (one per geometry)
1–20 session trading-window policy
Existing live theses for the ticker (for supersession)
```

## Direction behaviour

The Thesis Context assesses evidence support for each candidate geometry.

Possible states:

```text
SUPPORTED
OPPOSED
UNSUPPORTED
INSUFFICIENT_EVIDENCE
```

Evidence opposing the proposed structural direction must not automatically flip the direction.

It changes the assessment of the proposed thesis.

**Direction state is descriptive, not a gate.** A complete thesis with usable evidence flows to expression generation and valuation whether its state is `SUPPORTED`, `UNSUPPORTED` or `OPPOSED`. Weak or opposing evidence is expressed through the evidence probabilities and their uncertainty, which produce lower EV and RAEV, a lower rank or `NO_POSITIVE_EDGE`. It is never expressed by dropping the thesis.

The one legitimate exception is `INSUFFICIENT_EVIDENCE`: when probabilities cannot be estimated defensibly, EV cannot be calculated honestly. Such a thesis is published, recorded in the ledger as `NOT_VALUED` (reason `INSUFFICIENT_EVIDENCE`), not sent to expression generation, and its underlying outcome still matures for learning.

## Geometry selection

The Thesis selects **one** geometry among those with usable evidence (any state except `INSUFFICIENT_EVIDENCE`) and records the `evidence_packet_id` that justified it. If every geometry has insufficient evidence, the thesis is `NOT_VALUED` as above.

Default selection rule (versioned; to be confirmed by replication R4):

```text
select the geometry with the highest lower-bound underlying expectancy
in volatility units, evaluated at the lower uncertainty bound:

IF target_state = LEVEL:
    expectancy = P_target_first × target_distance_sigma
               − P_stop_first   × invalidation_distance_sigma
               + E[timeout return in sigma] × P_timeout

IF target_state = NONE:
    expectancy = − P_stop_first × invalidation_distance_sigma
               + E[return in sigma over the full timeout distribution] × P_timeout
      (no reference or synthetic target is used)

tie-break: structural priority of derivation_rule, then geometry_id
```

The rule uses underlying evidence only. It does not use option prices, EV or rank. Choosing by probability alone is forbidden because it biases towards the closest target. Geometries with and without a target are compared on the same expectancy basis.

Authority state of this rule:

```text
IMPLEMENTED_FOR_REPLICATION
NOT_YET_VALIDATED_FOR_PRODUCTION_AUTHORITY
```

until replication R4 and the validation gates in §24 confirm it.

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
1–20 trading-session opportunity window
```

The thesis is therefore **not predicting that the move happens specifically on Day 20**.

It is asserting:

> The anticipated move may begin and/or complete on any trading session from Day 1 through Day 20.

Day 1 is the first session after the thesis evidence session.

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

There is **no fixed holding bucket** (no 5 / 10 / 20 choice) and no single `hold_sessions` value as a fundamental thesis variable. The expected holding duration is derived from the distribution of historical first-passage times.

Therefore the Thesis aggregate distinguishes:

```text
trade_window_min_sessions = 1
trade_window_max_sessions = 20

expected_resolution_session
median_resolution_session
resolution_session_quantiles (e.g. q25, q75)
```

where evidence quality permits. These describe the distribution. They do not redefine the outer 20-session window.

The thesis may say:

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

The expected resolution range informs valuation and expression generation, while the maximum 20-session window preserves the original thesis opportunity.

## Exit-policy ownership

The Thesis owns the **maximum** window (Day 20). It does not own earlier time stops.

Any exit earlier than target, invalidation or Day 20 while the thesis is unresolved (for example "exit at Day 10 if unresolved") is an **expression exit policy**. It is generated as an explicit expression variant (§10) and valued by Valuation (§12), and it wins only through ranking. It is never a hidden assumption.

## Thesis identity and supersession

A thesis is the **same thesis** while all of the following hold:

```text
ticker unchanged
direction unchanged
invalidation level unchanged within tolerance
target level unchanged within tolerance (or target_state unchanged)
thesis not resolved (target, stop, invalidation or timeout)
```

A **new version** may be published only when a genuine change occurs, for example:

```text
structural invalidation or target level changes beyond tolerance
direction state changes (e.g. SUPPORTED → OPPOSED)
a better-supported geometry replaces the selected one
```

Supersession rules (ACK decision C4):

- A superseding version **inherits the original window clock**. It cannot restart the 1–20 session window.
- `supersedes_thesis_id` is recorded on the new version.
- The superseded version remains in the ledger, still matures and is still validated.
- A new window clock starts only after the previous thesis for that ticker and direction has **resolved** (target, stop, invalidation or timeout).
- Re-publishing an unchanged thesis in a later run creates no new version.

## Output aggregate

```text
Thesis
```

Example:

```text
thesis_id
thesis_version
supersedes_thesis_id
ticker
evidence_session
window_start_session            Day 1 of the original clock
reference_price
direction
direction_state
geometry_id
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

# 10. Stage 6 — Expression Context

## Responsibility

Answer:

> What are **all** the tradeable instruments capable of expressing this already-defined 1–20 session thesis?

This stage does not choose the thesis.

It does not choose the strongest expression either. It generates every eligible expression, applies tradeability, and hands the complete set to Valuation.

## Approved expression scope (ACK decisions)

```text
BULL thesis                         BEAR thesis
─────────────────────────────       ─────────────────────────────
long call                           long put
debit call vertical                 debit put vertical
long shares                         short shares (subject to borrow)
```

Long shares and short shares are both expressions and the benchmark that answers whether the money is in the option or in the ticker.

Scope changes are business decisions, versioned in configuration.

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

Which instruments can express this thesis,
and until which session can each one be held?
```

Incorrect:

```text
Found option with 7 DTE
therefore shorten thesis to 7 days.
```

The instrument must fit the thesis.

The thesis must never be shortened because an expression expires earlier.

## Expression life: last exit session (ACK decision C3)

Shorter-dated options are allowed. Each expression carries its own:

```text
last_exit_session = min(
    Day 20 of the thesis window,
    last session before expiry minus the approved exit buffer
)
```

- `last_exit_session` is an **absolute trading session (a date)**, fixed when the expression is generated. It is immutable. No later run moves or recomputes it.
- Later runs derive `remaining_sessions_to_last_exit = sessions_between(current_session, last_exit_session)`; they never shift the original value.
- If a later run generates a different candidate (for example a new expiry), that is a **new expression with a new `expression_id`**. An existing expression is never mutated.
- Shares have `last_exit_session` = Day 20 of the thesis window as an absolute session (or the time-stop session of an exit-policy variant).
- The thesis window stays 1–20 sessions. A shorter-dated expression is not a shorter thesis.
- Valuation exits any path still unresolved at an expression's `last_exit_session` at that session's bid-side price (§12). Whether short-dated convexity is worth it is decided by valuation and ranking, not by a DTE rule.

## Generation behaviour (bounded)

Candidate expressions are generated after the thesis is frozen and before valuation.

"All" means a **defined, bounded set derived from the frozen thesis**, not every listed contract. Only instrument families allowed by the ticker's capabilities (§6) are generated. Generation rules (versioned in configuration):

```text
expiries        listed expiries whose last_exit_session falls inside the useful part of the
                window (at least the approved minimum sessions after entry), up to the
                approved maximum DTE
long options    strikes within an approved band around reference price and target
                (or around reference price and invalidation when target_state = NONE)
debit verticals target_state = LEVEL:
                  long leg from the long-option strike set; short leg at or beyond the
                  target level; widths limited to the approved set
                target_state = NONE:
                  only explicitly approved fixed-width variants; if none are approved,
                  verticals are unavailable (VERTICALS_NOT_APPLICABLE_NO_TARGET).
                  The short strike caps payoff only; it is never used as a target or barrier.
shares          one long-shares (BULL) or short-shares (BEAR) expression
exit policies   base policy (target / invalidation / last_exit_session) plus approved
                time-stop variants (e.g. exit at Day N if unresolved)
```

When `options_available = false`, only share expressions are generated and the set records `OPTIONS_DATA_UNAVAILABLE`.

No weighted score of Greeks, delta bands or "closest to expected resolution" may be used to pre-select contracts. Those are valuation questions.

The context records how many expressions were generated, how many were excluded, and why.

## Tradeability

An expression can be excluded before valuation only for objective **integrity or execution** constraints:

```text
missing or one-sided quote
stale quote
spread over approved limit
insufficient market size / open interest
expiry before the approved minimum usable session
short shares: borrow not available
short shares: borrow fee unknown  → BORROW_DATA_UNAVAILABLE
```

Ordinary liquidity costs inside approved limits belong in valuation.

Note for valuation and execution: the short leg of a debit vertical carries early-assignment risk (for example around ex-dividend dates), which must be disclosed.

## Output

```text
CandidateExpressionSet
```

Each expression carries `expression_id`, `thesis_id`, instrument definition, exit policy and `last_exit_session`. Each excluded candidate remains auditable with a reason code and is written to the ledger.

---

# 11. Stage 7 — Volatility & Convexity Context

This is a supporting bounded context whose outputs are consumed by Valuation, Ranking (for display) and Presentation. It runs **before** Valuation, because path-specific exit pricing needs its forecasts.

Its responsibility is:

> What volatility is realised, what volatility is expected over the relevant part of the 1–20 session window, what volatility is being charged, and how attractive is the convexity?

## Behaviour

- Forecast volatility as a **term structure over sessions 1–20** (for example a HAR-type realised-volatility model). Values at 5, 10 and 20 sessions may be published as **forecast checkpoints**. They are not thesis holding buckets.
- Provide an **implied-volatility dynamics** assumption for exit repricing on each path (how IV is expected to move with spot and time), versioned.
- IV percentile and IV rank require a genuine **daily constant-maturity implied-volatility series** (for example 30-day ATM IV) built from recorded option chains. Comparing IV with a realised-volatility range is not an IV percentile.
- Placeholder IVs, zero gamma and missing open interest are quality states, never neutral values.

## Cheap convexity

`CheapConvexityProfile` describes whether convexity is cheap for an expression, for example:

```text
model cheapness vs forecast volatility
variance risk premium
IV percentile (from daily IV history)
breakeven vs expected move
convexity at target
gamma per premium
theta burden over the expected resolution range
term slope
skew
```

Cheap convexity is an **explanatory characteristic**. The monetary effect of cheap or expensive volatility is already inside EV through the forecast used in valuation. It is therefore **not a ranking key** unless validation shows incremental value beyond RAEV (Invariant G).

## Output

```text
VolatilityAssessment
CheapConvexityProfile
```

These do not change the Thesis.

---

# 12. Stage 8 — Valuation Context

## Responsibility

Answer:

> Given the same thesis and possible market paths over Days 1–20, what is each expression economically worth?

This is the sole owner of trade economics.

No legacy engine output (including EV v2) may be presented as, substituted for, or combined with Valuation's EV. EV3 remains non-authoritative until this context has passed §24.

## Required inputs

```text
Frozen Thesis
EvidencePacket (of the selected geometry)
CandidateExpressionSet (tradeable expressions only)
VolatilityAssessment
option quotes (bid / ask)
rate
dividend assumptions
borrow fee (short shares)
cost model
pricing model
```

## Common-path rule

Every expression for the same thesis must be valued against the **same underlying path set**.

The path set has its own `path_set_id`. It is conditioned on the thesis state and scaled by the volatility forecast, and it must reconcile with the EvidencePacket: the path set's target-first, stop-first and timeout frequencies by session must match the packet's cumulative incidence within tolerance. A path set that does not reconcile is `NOT_VALUED` for the whole thesis.

## Time-to-event valuation

This is crucial for the 1–20 session design.

The expression must be repriced on the session where the underlying path actually resolves, or on its own `last_exit_session`, whichever comes first.

Example:

```text
Path A
Target hit Day 2
→ expression valued/exited Day 2

Path B
Stop hit Day 5
→ expression valued/exited Day 5

Path C
Target hit Day 13, option last_exit_session Day 9
→ forced exit Day 9 at that session's bid

Path D
No barrier by Day 20
→ timeout valuation Day 20 (or at the expression's time-stop variant)
```

The pipeline must not assume:

```text
all winners exit Day 20
```

or:

```text
all trades use one fixed holding period
```

or:

```text
timeout exits at an unchanged spot
```

Time decay, remaining DTE, spot and IV behaviour must therefore vary by path.

When `target_state = NONE`, paths resolve only by stop, `last_exit_session`, time-stop variant or Day 20. No reference or synthetic target is introduced as a barrier.

## Exit pricing and costs

- Entry at the ask; exit at the bid.
- Exit spreads modelled as `max(absolute floor, proportional share of value)`; a proportional-only spread overstates exit bids on low-priced options.
- Commissions per contract / share.
- Borrow fee for short shares over the path's holding sessions.
- Barrier levels are used exactly; no snapping to a coarse grid.

## Expected value

Conceptually:

```text
EV = Σ path_weight × path_P&L
```

where each path contains its own:

```text
exit session
exit reason (target / stop / timeout / last_exit_session / time-stop)
exit spot
remaining DTE
exit IV
exit expression value
transaction costs
```

Then:

```text
EV/R = EV / capital_at_risk
```

uncertainty and stress produce:

```text
RAEV = lower-bound EV per dollar at risk
```

and, for comparing expressions that tie up capital for different lengths of time (ACK decision C9):

```text
expected_sessions_held    = Σ path_weight × sessions held on the path
time_normalised_return    = EV/R per expected session held
```

RAEV is the ranking measure. The time-normalised return is published alongside it and is the first ranking tie-break.

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
path_set_id
entry_cost
capital_at_risk
expected_pnl
ev_per_risk
raev
time_normalised_return
expected_sessions_held

last_exit_session
forced_exit_share               share of paths exited at last_exit_session
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

# 13. Stage 9 — Ranking Context

## Responsibility

Answer:

> Across all already-valued expressions, which is strongest for each thesis, and in what order should the trader consider the opportunities?

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
strongest expression = highest RAEV
tie-breaks:
  1. time_normalised_return descending
  2. liquidity cost ascending
  3. expression_id (deterministic)
```

This is where "is the money in the option or the ticker" is answered: shares are valued and ranked alongside options on the same paths.

## Across-thesis ranking

```text
RAEV descending
time_normalised_return descending
liquidity cost ascending
deterministic tie-break
```

Cheap-convexity quality, dealer positioning and other characteristics are displayed but are not ranking keys unless validated (§11, Invariant G).

## Stability (hysteresis)

To prevent day-to-day flip-flopping between near-equal expressions, Ranking may keep the previous run's strongest expression for the same thesis unless the new leader's RAEV exceeds it by more than the switching cost plus a noise margin derived from the valuation uncertainty intervals.

- The threshold is versioned and must be justified by validation.
- Every application of hysteresis is recorded.
- Hysteresis never keeps an expression whose RAEV is ≤ 0 or which is no longer tradeable.

## Negative edge and unvalued theses

A candidate with:

```text
RAEV <= 0
```

remains visible as:

```text
NO_POSITIVE_EDGE
```

rather than disappearing through an unexplained gate.

A thesis whose expressions are all `NOT_VALUED` remains visible as `NOT_VALUED` with reasons.

## Portfolio awareness

Ranking may additionally report:

```text
sector concentration
cluster concentration
correlation concentration
```

without changing underlying valuation or rank.

## Output aggregate

```text
OpportunityBook
```

The book contains every valued expression with its rank, not only the leaders.

---

# 14. Stage 10 — Execution Readiness Context

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
Has thesis invalidated or resolved since the evidence session?
   YES → INVALIDATED / RESOLVED
   NO
        ↓
How much of the original 1–20 session window remains?
        ↓
Refresh expression quotes
        ↓
Re-run tradeability
        ↓
Re-run canonical valuation over the remaining window
(remaining_sessions_to_last_exit from today to each expression's
 immutable last_exit_session; last_exit_session itself never moves)
        ↓
Re-run canonical ranking (including hysteresis rule)
        ↓
Apply execution policy
```

The remaining opportunity window matters.

Example:

A thesis created with its evidence session on Day 0 may still be valid on Day 4.

Its remaining thesis window becomes approximately:

```text
Day 5 through Day 20
```

relative to the original thesis clock.

AVSHUNTER must not restart a fresh 20-session clock every morning, nor on supersession (§9).

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

Macro context and event information (earnings, economic releases) may be **displayed** to the trader for manual review. They are not automated gates, scores or rank inputs (ACK decisions).

---

# 15. Stage 11 — Decision Ledger

The ledger is append-only and cross-cutting. Every context writes its published output **when it is produced**, not only when a decision is actionable.

Recorded:

```text
every EligibilityAssessment (including NOT_ELIGIBLE with reasons)
every StructureAssessment and CandidateGeometry
every EvidencePacket (including INSUFFICIENT_EVIDENCE)
every Thesis version (including OPPOSED / UNSUPPORTED / INCOMPLETE and superseded versions)
every generated expression (including tradeability exclusions with reasons)
every ExpressionValuation (including NOT_VALUED and NO_POSITIVE_EDGE)
every OpportunityBook with every rank
every ExecutionDecision
```

Each record carries an `actioned` flag (true only for expressions the trader actually took, linked to journal fills by `expression_id` / `thesis_id`).

Required lineage includes:

```text
record_id
record_type
run_id
release_id
decision_clock
ticker
thesis_id
thesis_version
structure_assessment_id
geometry_id
evidence_packet_id
expression_id
valuation_id
path_set_id
ranking_book_id
rank
execution_action
actioned

trade_window_min_sessions
trade_window_max_sessions
window_start_session
thesis_age_sessions
remaining_window_sessions
last_exit_session

input_dataset_ids
formula_versions
configuration_versions
as_of timestamps
```

Every record must be written before the outcome is known.

Without non-selected and non-actioned records, AVSHUNTER could validate the trades it took but never the ranking, selection or rejection decisions.

---

# 16. Stage 12 — Outcome Maturation

Outcome generation is deterministic. There are two outcome domains.

## Underlying outcome (per thesis)

Origin: the thesis evidence session. The outcome engine monitors the thesis path through a maximum of 20 trading sessions.

A thesis may mature early.

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
AMBIGUOUS      both barriers touched in the same session
```

The system must record:

```text
first_touch_session
days_to_resolution
```

not just the final outcome. Superseded thesis versions mature as well.

## Expression outcome (per valued expression)

A thesis can be right while its expression loses money (IV collapse, theta, spread). Expression outcomes are therefore measured separately, for **every valued expression**, selected or not, actioned or not.

Origin: the decision time (the morning run in which the expression was ranked).

Maturation: at the earlier of the underlying resolution session, the expression's `last_exit_session`, or its exit-policy time stop.

Recorded:

```text
exit_session and exit_reason
exit price at bid (mark-to-market)
realised P&L
realised P&L per $ at risk
MFE / MAE
IV change entry → exit
spread cost paid
sessions held
predicted EV / RAEV at decision
EV prediction error
actual fills from the journal when actioned
```

This timing and economic evidence becomes critical input for future valuation and expression generation.

---

# 17. Stage 13 — Validation and Learning Context

## Responsibility

Answer:

> Did AVSHUNTER's claimed probabilities, timing expectations, valuations, selections and rankings correspond with reality?

Validation must assess both **directional correctness** and **time-to-resolution correctness**, and both **thesis** and **expression** economics.

For example:

```text
Did target occur within Day 1–20?
Did stop occur first?
When did resolution occur?
Was the cumulative-incidence distribution calibrated (whether and when)?
Was predicted EV calibrated against realised expression P&L?
Did higher-ranked expressions outperform lower-ranked and non-selected ones?
Did shorter-dated expressions with forced exits perform as valued?
Was theta burden estimated correctly?
Did exclusions and NO_POSITIVE_EDGE decisions avoid losses?
Does cheap convexity or dealer positioning add value beyond RAEV?
```

Historical validation must use:

```text
point-in-time inputs and point-in-time universe
no look-ahead
purging
embargo
walk-forward testing
realistic costs
same production domain services
```

Validation does not modify old decisions.

It produces evidence for future model versions and for granting or withholding authority (§24).

---

# 18. Stage 14 — Presentation Context

The Lab is a **read model**.

- It renders published contracts only.
- It never re-ranks, re-scores, re-values or combines fields into a new priority.
- Every economic figure is labelled with its source and authority state. A legacy or advisory figure (for example EV v2 or EV3) must never be displayed as, or in place of, Valuation's EV.
- Unavailable, stale and not-valued states are displayed as such.

---

# 19. Domain Events and Contracts

Recommended domain events:

```text
RunContextEstablished
        ↓
MarketSnapshotPublished
        ↓
UniverseSnapshotPublished / EligibilityAssessed
        ↓
StructureAssessmentPublished (with CandidateGeometries)
        ↓
EvidencePacketPublished (per geometry)
        ↓
ThesisPublished / ThesisSuperseded
        ↓
ExpressionSetGenerated
        ↓
VolatilityAssessmentPublished
        ↓
ExpressionValuationPublished
        ↓
OpportunityBookPublished
        ↓
ExecutionDecisionRecorded
        ↓
UnderlyingOutcomeMatured / ExpressionOutcomeMatured
        ↓
ValidationCompleted

Every event → LedgerRecordAppended
```

Every event carries references rather than duplicated mutable state.

---

# 20. Application Orchestrator Behaviour

Conceptually:

```python
run_context = run.establish(clock, release)

snapshot = market_data.capture(run_context)          # fixed capture panel, freshness states
ledger.record(snapshot.coverage_report)

universe = eligibility.assess(snapshot, run_context)
ledger.record(universe)

for ticker in universe.eligible:

    structure = market_structure.assess(snapshot, ticker, run_context)
    ledger.record(structure)

    packets = evidence_context.evaluate(
        geometries=structure.candidate_geometries,
        window_min=1,
        window_max=20,
        run_context=run_context,
    )
    ledger.record(packets)

    thesis = thesis_context.build(
        structure=structure,
        evidence=packets,
        existing_theses=ledger.live_theses(ticker),   # supersession, inherited clock
        trade_window=(1, 20),
        run_context=run_context,
    )
    ledger.record(thesis)

    if thesis.is_incomplete or thesis.evidence_insufficient:
        ledger.record(thesis.not_valued())             # SUPPORTED / UNSUPPORTED / OPPOSED all continue
        continue

    expressions = expression_context.generate(thesis=thesis, snapshot=snapshot)
    ledger.record(expressions)                          # includes exclusions

    volatility = volatility_context.assess(thesis=thesis, snapshot=snapshot)

    valuations = valuation_context.value_all(
        thesis=thesis,
        evidence=packets.selected(thesis),
        expressions=expressions.tradeable,
        volatility=volatility,
        snapshot=snapshot,
    )
    ledger.record(valuations)

book = ranking_context.rank(valuations=all_valuations, previous_book=ledger.last_book())
ledger.record(book)

# Morning run
decisions = execution_context.evaluate(
    opportunity_book=book,
    current_market_snapshot=live_snapshot,
)
ledger.record(decisions)
```

The orchestrator coordinates.

It does not own domain decisions.

---

# 21. Broken-Flow Prevention Rules

| Condition | Required behaviour |
|---|---|
| Market data missing | mark affected data `DATA_UNAVAILABLE` |
| History older than required session | `STALE_HISTORY`; never COMPLETE; consumers treat as unavailable |
| Capture coverage below threshold | visible run-health failure |
| Ticker fails eligibility | `NOT_ELIGIBLE` with reason codes; never "no signal" |
| No option chain for an eligible ticker | ticker stays `ELIGIBLE`; `OPTIONS_DATA_UNAVAILABLE`; share expressions only |
| State cannot be derived | no Evidence request for that state |
| No candidate geometry with valid invalidation | Thesis incomplete |
| Evidence insufficient for a geometry | `INSUFFICIENT_EVIDENCE` for that geometry; geometry not selectable |
| Evidence insufficient for every geometry | thesis `NOT_VALUED` (reason `INSUFFICIENT_EVIDENCE`); recorded; underlying outcome matures |
| Selected geometry UNSUPPORTED or OPPOSED | thesis flows to expressions and valuation; weak evidence lowers RAEV and rank |
| No target and no approved fixed-width verticals | verticals `VERTICALS_NOT_APPLICABLE_NO_TARGET`; other families still generated |
| Later run finds a better contract | new expression with new `expression_id`; existing `last_exit_session` unchanged |
| Required target missing | `target_state=NONE`; use supported stop/timeout valuation |
| Valid 1–20 session window cannot be established | Thesis incomplete |
| Genuine change to a live thesis | new version; inherits window clock; old version still matures |
| No expression passes tradeability | `NO_TRADEABLE_EXPRESSION` (visible, recorded) |
| Option expires before Day 20 | valid; valued with its own `last_exit_session` and forced exit |
| Short shares without borrow data | `BORROW_DATA_UNAVAILABLE` |
| Pricing input missing | expression=`NOT_VALUED` |
| Path set does not reconcile with evidence | all expressions for the thesis `NOT_VALUED` |
| All expressions unvalued | thesis visible as `NOT_VALUED` with reasons; not in actionable set |
| RAEV ≤ 0 | retain as `NO_POSITIVE_EDGE` |
| GEX data insufficient | `GEX_UNAVAILABLE`; never neutral |
| Thesis invalidated before Day 20 | `INVALIDATED` |
| Thesis reaches Day 20 unresolved | `TIMEOUT` |
| Quote changes | revalue; do not change Thesis |
| Outcome already resolves before Day 20 | mature immediately |
| Historical replay data missing | record missing; never substitute future or latest data |

A pipeline does not remain unbroken by forcing every ticker through to BUY/SELL.

It remains unbroken when every valid state has a defined next state.

---

# 22. State Machine

At candidate level:

```text
OBSERVED
   ↓
ELIGIBILITY_ASSESSED
   ↓
STRUCTURE_ASSESSED (candidate geometries)
   ↓
EVIDENCE_ASSESSED (per geometry)
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
OUTCOME_MATURED (underlying + every valued expression)
   ↓
VALIDATED
```

Legitimate terminal branches include:

```text
DATA_UNAVAILABLE
STALE_HISTORY
NOT_ELIGIBLE
INSUFFICIENT_EVIDENCE      (thesis NOT_VALUED)
INCOMPLETE_THESIS
SUPERSEDED                 (still matures and validates)
NO_TRADEABLE_EXPRESSION
BORROW_DATA_UNAVAILABLE
NOT_VALUED
NO_POSITIVE_EDGE
INVALIDATED
```

These are valid domain outcomes, not system failures. Every one is recorded in the ledger and every published thesis and valued expression still matures.

`SUPPORTED`, `UNSUPPORTED` and `OPPOSED` are **not** terminal branches. They are descriptive thesis states that continue to valuation and ranking. `OPTIONS_DATA_UNAVAILABLE` and `VERTICALS_NOT_APPLICABLE_NO_TARGET` are instrument-family states, not ticker or thesis terminations.

---

# 23. Replay and Live Trading Must Share the Same Domain Path

Historical replay must run:

```text
HistoricalSnapshot (point-in-time universe)
        ↓
same Universe & Eligibility domain
        ↓
same Market Structure domain
        ↓
same Evidence domain
        ↓
same Thesis domain
        ↓
same Expression domain
        ↓
same Volatility & Convexity domain
        ↓
same Valuation domain
        ↓
same Ranking domain
```

with the historical clock injected.

The 1–20 session outcome path is then replayed exactly as production would experience it.

---

# 24. Replication Comes Before Decision Authority

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

Replications R1 (volatility forecasting) and R4 (structural state and geometry vs base rate, as cumulative incidence over 1–20 sessions) must run on complete, fresh, point-in-time data.

Build order:

```text
BUILD (production-grade domain services)
   ↓
SHADOW / NON-AUTHORITATIVE
   ↓
REPLICATION (R1, R4 run through those same services)
   ↓
WALK-FORWARD AND FORWARD SHADOW VALIDATION
   ↓
AUTHORITY
```

The Evidence, Volatility & Convexity, Thesis, Valuation and Ranking contexts **may be implemented** in non-authoritative shadow form so that the replications exercise the same domain services production will use. They must not receive production decision authority until R1/R4 and the subsequent validation gates pass.

A lightweight research replication may also be run earlier to de-risk a method before its context is built. It does not replace replication through the production domain services.

Every rule and model carries an explicit authority state, for example:

```text
IMPLEMENTED_FOR_REPLICATION
NOT_YET_VALIDATED_FOR_PRODUCTION_AUTHORITY
SHADOW
AUTHORITATIVE
```

---

# 25. Domain Ownership Matrix

| Domain concept | Authoritative owner | Downstream mutation |
|---|---|---|
| Run identity, decision clock, release | Run Context | Forbidden |
| Market observation | Market Data | Forbidden |
| Capture coverage and freshness state | Market Data | Forbidden |
| Universe membership (point-in-time) | Universe & Eligibility | Forbidden |
| Eligibility state and reasons | Universe & Eligibility | Forbidden |
| Instrument capabilities (options, long/short shares) | Universe & Eligibility | Forbidden |
| Structural state | Market Structure | Forbidden |
| Candidate geometry | Market Structure | Forbidden |
| Dealer positioning (GEX) | Market Structure | Forbidden |
| Historical probability / cumulative incidence | Evidence | Forbidden |
| Time-to-resolution distribution | Evidence | Forbidden |
| Evidence uncertainty | Evidence | Forbidden |
| Direction | Thesis | Forbidden |
| Selected geometry | Thesis | Forbidden |
| Target | Thesis | Forbidden |
| Invalidation | Thesis | Forbidden |
| 1–20 session trade window and window clock | Thesis | Forbidden |
| Thesis version and supersession | Thesis | Forbidden |
| Expression definition | Expression | Forbidden |
| Last exit session (absolute, immutable) | Expression | Forbidden; later runs derive remaining sessions only |
| Expression exit policy | Expression (defined) / Valuation (valued) | Forbidden |
| Tradeability status | Expression | Rechecked, not historically overwritten |
| Volatility forecast and IV dynamics | Volatility & Convexity | Versioned |
| Cheap convexity profile | Volatility & Convexity | Versioned |
| Path set | Valuation | Forbidden |
| Entry/exit economics | Valuation | Forbidden |
| EV | Valuation | Forbidden |
| EV/R | Valuation | Forbidden |
| RAEV | Valuation | Forbidden |
| Time-normalised return | Valuation | Forbidden |
| Strongest expression per thesis | Ranking | New book/version only |
| Rank | Ranking | New book/version only |
| Execution action | Execution | New decision only |
| Ledger record | Decision Ledger | Forbidden (append-only) |
| Underlying outcome | Outcome | Forbidden |
| Expression outcome | Outcome | Forbidden |
| Days to resolution | Outcome | Forbidden |
| Calibration result | Validation | New model/version only |
| Displayed view | Presentation | Read-only |

---

# 26. What Must Not Happen

Forbidden behaviours include:

```text
Evidence returns no match
→ downstream substitutes 52%

Missing data
→ neutral score, 0.5 regime value, constant score or PASS status

Ticker fails liquidity or data checks
→ reported as "no signal"

Ticker has no option chain
→ excluded, although shares could express the thesis

Evidence OPPOSED or UNSUPPORTED
→ thesis dropped instead of valued and ranked

target_state = NONE
→ a reference or synthetic target used as a barrier or vertical anchor

Morning run
→ moves an expression's last_exit_session, or mutates an expression instead of creating a new one

Replication gates "must pass before build"
→ production services cannot be exercised; or services built and given authority before gates pass

Thesis allows Day 1–20
→ option finder sees 7 DTE
→ thesis shortened to 7 days

Thesis frozen
→ a contract selector picks one contract by weighted Greeks
→ only that contract is valued

Evidence expects resolution around Day 8
→ pipeline assumes every trade exits Day 8

Thesis uses a fixed 5 / 10 / 20 holding bucket

Target is hit Day 3
→ valuation still models exit on Day 20

Timeout valued at unchanged spot

Trade remains open Day 6
→ execution restarts a new 20-session window

Thesis superseded
→ new version restarts the window clock

Thesis says BULL
→ execution silently converts it to PUT

Valuation computes negative EV
→ heuristic score makes it positive

Legacy EV v2 (or advisory EV3) shown or used as EV

Cheap convexity, GEX or any unvalidated score
→ used as a gate or ranking key

Macro context
→ influences any gate, score, floor or rank

Event guards (earnings, releases)
→ used as automated gates

Lab
→ recomputes rank or priority

Only actioned trades recorded
→ ranking and rejections cannot be validated

History 12 days old
→ reported as COMPLETE

Historical replay lacks original input
→ today's latest value is substituted

Published thesis changes
→ old thesis row overwritten
```

Every one breaks domain ownership, temporal integrity or economic consistency.

---

# 27. Correct End-to-End Behaviour in One Sentence

AVSHUNTER should behave as a chain of autonomous bounded contexts in which **fresh point-in-time market facts determine which tickers are eligible, structure proposes candidate geometries, historical evidence measures when during a 1–20 trading-session window each geometry's target, stop or timeout is likely to occur, the thesis adopts the geometry with the best lower-bound evidence and freezes it — supported or not, because weak evidence lowers RAEV rather than dropping the thesis — without ever restarting its clock, expression generation produces every tradeable way to express it — options, verticals and shares, each with its own last exit session — valuation reprices all of them on the same path-specific exits, ranking selects the strongest by risk-adjusted EV so that the money is found in the option or the ticker, execution revalidates rather than reinvents the thesis, and every decision and every alternative is recorded before its outcome is known so the entire chain can learn whether direction, timing and economics were right.**

---

# 28. Target Architecture

```text
                     ┌─────────────────────────┐
                     │ C0 RUN CONTEXT          │
                     │ clock / IDs / release   │
                     └───────────┬─────────────┘
                                 │ RunContext
                                 ▼
                     ┌─────────────────────────┐
                     │ C1 MARKET DATA          │
                     │ capture panel/freshness │
                     └───────────┬─────────────┘
                                 │ MarketSnapshot
                                 ▼
                     ┌─────────────────────────┐
                     │ C2 UNIVERSE &           │
                     │    ELIGIBILITY          │
                     └───────────┬─────────────┘
                                 │ EligibilityAssessment
                                 ▼
                     ┌─────────────────────────┐
                     │ C3 MARKET STRUCTURE     │
                     │ candidate geometries    │
                     └───────────┬─────────────┘
                                 │ StructureAssessment
                                 ▼
                     ┌─────────────────────────┐
                     │ C4 EVIDENCE             │
                     │ competing risks D1→D20  │
                     └───────────┬─────────────┘
                                 │ EvidencePacket per geometry
                                 ▼
                     ┌─────────────────────────┐
                     │ C5 THESIS               │
                     │ geometry, window clock  │
                     └───────────┬─────────────┘
                                 │ Frozen Thesis
                  ┌──────────────┴──────────────┐
                  ▼                             ▼
     ┌─────────────────────────┐   ┌─────────────────────────┐
     │ C6 EXPRESSION           │   │ C7 VOLATILITY &         │
     │ all eligible + trade-   │   │    CONVEXITY            │
     │ ability, last exit      │   │ term forecast, IV dyn.  │
     └───────────┬─────────────┘   └───────────┬─────────────┘
                 │ CandidateExpressionSet      │ VolatilityAssessment
                 └──────────────┬──────────────┘
                                ▼
        ┌───────────────────────────────────────────────┐
        │ C8 VALUATION                                  │
        │ common path set; path-specific exits;         │
        │ EV, EV/R, RAEV, time-normalised return        │
        └───────────────────────┬───────────────────────┘
                                │ ExpressionValuations
                                ▼
                     ┌─────────────────────────┐
                     │ C9 RANKING              │
                     │ RAEV; strongest wins    │
                     └───────────┬─────────────┘
                                 │ OpportunityBook
                                 ▼
                     ┌─────────────────────────┐
                     │ C10 EXECUTION READINESS │
                     │ remaining window        │
                     └───────────┬─────────────┘
                                 │ ExecutionDecision
                                 ▼
                     ┌─────────────────────────┐
                     │ C12 OUTCOME             │
                     │ underlying + expression │
                     └───────────┬─────────────┘
                                 ▼
                     ┌─────────────────────────┐
                     │ C13 VALIDATION /        │
                     │     LEARNING            │
                     └───────────┬─────────────┘
                                 │
                      future model versions / authority
                                 │
                                 └──────► future runs

  C11 DECISION LEDGER ◄── written by every context from C1 to C13 (append-only)
  C14 PRESENTATION    ◄── reads published contracts only
```

This closes the loop without forcing AVSHUNTER into artificial 5-, 10- or 20-session holding buckets.

The **20-session value is the outer boundary of the thesis opportunity window**. The actual trade can resolve on any session from Day 1 through Day 20, and each expression can be held only until its own last exit session.

---

# Appendix A — Change log from version 1.0

Section numbers in the "v1.0 location" column refer to version 1.0.

## A.1 Review changes C1–C14

| Change | v1.0 location | What changed in v1.1 |
|---|---|---|
| C1 Evidence needs barrier levels | §6, §7, §8 | Market Structure proposes candidate geometries; Evidence produces a packet per geometry; Thesis selects the geometry and records the packet (§7, §8, §9) |
| C2 Competing-risks estimation | §7 | Discrete-time competing-risks survival, shrinkage, block `n_eff`, block bootstrap; packet fields renamed to cumulative incidence (§8) |
| C3 Minimum DTE | §9, §19 | ACK decision (b): expression `last_exit_session`; forced exit; minimum-DTE exclusion removed (§10, §12, §21) |
| C4 Thesis versioning | §3, §13 | Thesis identity and supersession section; inherited clock (§9, §14) |
| C5 Ledger records every candidate | §14 | Ledger cross-cutting, every published output, `actioned` flag (§15) |
| C6 Expression outcomes | §15 | Separate underlying and expression outcome domains, origins and maturation (§16) |
| C7 Universe & Eligibility | §4–6 | New Stage 2 / C2 (§6) |
| C8 Expression scope and borrow | §9 | Approved scope incl. long shares (Q1) and short shares with borrow; early-assignment note (§10) |
| C9 Different durations | §10, §12 | RAEV primary; time-normalised return published and first tie-break (§12, §13) |
| C10 Evidence scope wording | §7 | Point-in-time market universe as base sample; own outcomes as calibration (§8) |
| C11 Symmetry and data hygiene | §3, §7 | Invariants D and E (§3) |
| C12 Advisory inputs named | §5, §24 | Macro and event guards display-only; Lab read-only (§14, §18, §26) |
| C13 Exit-policy ownership | §8, §10, §13 | Thesis owns maximum window; time stops are expression exit-policy variants (§9, §10) |
| C14 Minor consistency | §1, §4, §12, §19, §24 | Context numbering C0–C14; `release_id`, `clean_tree`; hysteresis; NOT_VALUED visible; neutral-pass forbidden (§1, §4, §13, §21, §3, §26) |

## A.2 ACK decisions (16 Sep 2026)

| Decision | Incorporated in |
|---|---|
| C3 (b) shorter-dated expressions with own last exit session | §10, §12, §16, §21 |
| C4 superseding thesis inherits window clock | §9, §14 |
| C9 rank on RAEV; time-normalised return first tie-break | §12, §13 |
| Q1 long shares for BULL theses in scope | §10 |
| Earlier: rank not gate; hard exclusions integrity and tradeability only | §1, §6, §10, §13 |
| Earlier: macro removed from decisions; reviewed manually; event guards manual | §7, §14, §26 |
| Earlier: catalyst direction evidence and relative_strength_20d retired | Not inputs to any context |
| Earlier: EV3 authority retired until correct EV logic is built and validated | §12, §18, §24 |

## A.3 Agreed refinements

| Ref | Refinement | Incorporated in |
|---|---|---|
| R-A | Document authority: specification governs behaviour; method notes govern method correctness; conflicts escalated | Document control |
| R-B | "All expressions" is a bounded, thesis-derived generation set; no pre-valuation selector | §2, §10, §26 |
| R-C | Volatility & Convexity runs before Valuation; cheap convexity is explanatory, not a ranking key unless validated | §2, §11, §13 |
| R-D | Ledger written by every context as outputs are produced, not a final step | §2, §15, §20, §28 |
| R-E | Morning revaluation re-checks invalidation/resolution since the close | §14 |
| R-F | Hysteresis constrained: validated threshold, recorded, never keeps RAEV ≤ 0 | §13 |
| R-G | 5/10/20 retained only as volatility forecast checkpoints | §9, §11 |
| R-H | Thesis geometry selection by lower-bound underlying expectancy in σ units, not probability alone (to be confirmed by R4) | §9 |

## A.4 Investigation findings incorporated

| Finding | Report | Incorporated in |
|---|---|---|
| Legacy EV v2 acted as EV after EV3 retirement | `forensic_mapping/…` §8 | §12, §18, §26 |
| GEX: wrong flip algorithm, OI walls, synthetic EIL map, benchmark acquisition failure, neutral 0.5 default | `gex/GEX_INVESTIGATION_20260914_214012.md` | §7, §21, §26 |
| IV percentile not built from IV history; no daily constant-maturity IV series | `iv_history/IV_HISTORY_INVENTORY_20260916.md` | §11 |
| Phantom history 12 days stale; candidate-only capture; no freshness gate | `data_freshness/PHANTOM_DATA_FRESHNESS_20260916.md` | §3 (Invariant F), §5, §21, §26 |
| EV3 defects: timeout at unchanged spot, grid snapping, proportional exit spread | `forensic_mapping/…` | §12 |

## A.5 Sign-off record (ACK, 16 Sep 2026)

| Item | Decision |
|---|---|
| Architecture and behavioural model | **Approved** |
| Version 1.1 as governing behavioural specification | **Approved**, subject to S1–S5 (incorporated, A.6) |
| R-H default geometry selection rule | **Approved as provisional policy**; authority state `IMPLEMENTED_FOR_REPLICATION` / `NOT_YET_VALIDATED_FOR_PRODUCTION_AUTHORITY` until R4 and validation gates pass |
| Configuration items (exit buffer, generation bands, strike limits, vertical widths, maximum DTE, time-stop variants, spread limits, size/OI limits, capture coverage threshold, hysteresis margin, supersession tolerances) | **Approved** as version-controlled configuration outside domain code (Appendix B) |
| Implementation commencement | Foundation / Data Truth phase may begin. Evidence, Volatility & Convexity, Thesis, Valuation and Ranking are built non-authoritative until their replication and validation gates pass. |

## A.6 Sign-off corrections S1–S5

| Ref | Finding (validated true against v1.1 text) | Correction | Location |
|---|---|---|---|
| S1 | `SUPPORTED` had become a routing gate ("selects among SUPPORTED"; "not routed to expression generation"), contradicting rank-not-gate | Direction state is descriptive; SUPPORTED / UNSUPPORTED / OPPOSED all flow to valuation; only `INSUFFICIENT_EVIDENCE` → `NOT_VALUED` (recorded, underlying matures). Geometry selected among all geometries with usable evidence. | §9, §20, §21, §22, §26 |
| S2 | `NO_OPTION_CHAIN` excluded the ticker although shares are valid expressions | Removed as eligibility reason; instrument capabilities recorded on eligible tickers; `OPTIONS_DATA_UNAVAILABLE`; Expression generates only available families | §6, §10, §21, §25, §26 |
| S3 | No-target path undefined in geometry selection and vertical generation | Expectancy formula for `target_state = NONE`; verticals only from approved fixed-width variants or `VERTICALS_NOT_APPLICABLE_NO_TARGET`; no synthetic target or barrier. (Also corrected: timeout term weighted by `P_timeout`.) | §9, §10, §12, §21, §26 |
| S4 | Replication wording required R1/R4 before contexts are "built", blocking replication through production services | Build → shadow → replication → validation → authority; optional earlier research replication; explicit authority states | §24, §26 |
| S5 | "last_exit_session relative to today" could be implemented as a moving expiry window | `last_exit_session` absolute and immutable; later runs derive `remaining_sessions_to_last_exit`; new candidates get new `expression_id` | §10, §14, §21, §25, §26 |

---

## A.7 Amendments after sign-off

| Ref | Date | ACK decision | Change | Location |
|---|---|---|---|---|
| AM-1 | 17 Sep 2026 | Evidence stays current to the last completed session | "Fully matured labels" replaced by point-in-time labels: resolved paths are events at their touch session; unresolved recent paths are right-censored at their current age; no information after the evidence session. Removes the ~20-session lag of fixed-horizon maturity. | Invariant E (§3), §8 estimation method |
| AM-2 | 17 Sep 2026 | No option-chain data | Confirmed S2 unchanged: ticker stays eligible, `OPTIONS_DATA_UNAVAILABLE`, share expressions still generated; recorded, never silent. `NO_DATA` for a session is final (no re-request). | §6 (no text change) |

---

# Appendix B — Configuration governance

The behavioural contract in this specification does not set parameter values. Every threshold, band, limit and tolerance it references is version-controlled configuration, never a literal in domain code.

Each configuration item carries:

```text
config_key
value
unit
effective_from
version
business_owner
validation_state        e.g. PROVISIONAL | VALIDATED | RETIRED
rationale / evidence reference
```

Rules:

- A published aggregate records the configuration versions it used (§4, §15), so a later change never alters the meaning of historical decisions.
- Changing a value creates a new version with a new `effective_from`; old versions are retained.
- Replay uses the configuration versions effective at the replayed decision clock.
- A value whose `validation_state` is not `VALIDATED` may drive shadow behaviour only, consistent with §24.

Initial configuration register (values to be set during design):

```text
exit_buffer_sessions
expression.expiry.min_usable_sessions
expression.expiry.max_dte
expression.long_option.strike_band
expression.vertical.widths
expression.vertical.fixed_width_variants_no_target
expression.exit_policy.time_stop_variants
tradeability.spread_limit
tradeability.min_size
tradeability.min_open_interest
tradeability.quote_max_age
eligibility.price_range
eligibility.min_adv
eligibility.atr_bounds
eligibility.min_bars
market_data.capture_coverage_threshold
ranking.hysteresis_margin
thesis.supersession.invalidation_tolerance
thesis.supersession.target_tolerance
valuation.exit_spread_absolute_floor
valuation.commission_schedule
```
