# Specification map (spec v1.1, governing)

Source: `Enhancements/knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md`.
Read the actual section before touching any context — this is a map, not a
substitute.

## Bounded contexts (C0–C14) — the only correct stage numbering

| # | Context | Aggregate / output | Business question | Method note |
|---|---|---|---|---|
| C0 | Run Context | `RunContext` | Which run, which clock, which release, which data? | — |
| C1 | Market Data | `MarketSnapshot` | What was genuinely observable at the decision time, and is it fresh? | 07 |
| C2 | Universe & Eligibility | `UniverseSnapshot`, `EligibilityAssessment` | May this ticker be analysed, and if not, why? | 07 |
| C3 | Market Structure | `StructureAssessment` + `CandidateGeometry` | What does structure look like, which target/invalidation geometries does it propose? | 02 |
| C4 | Evidence | `EvidencePacket` per geometry | Historically, what happened from states like this, and when? | 01 |
| C5 | Thesis | `Thesis` (aggregate root) | What exactly do we believe, over which window, and when is it wrong? | 02 |
| C6 | Expression | `CandidateExpressionSet` | All tradeable ways to express this thesis | 05 |
| C7 | Volatility & Convexity | `VolatilityAssessment`, `CheapConvexityProfile` | Expected vol, what's charged, is convexity cheap? | 04 |
| C8 | Valuation | `ExpressionValuation` | How much money is in each expression? (sole owner of EV/RAEV) | 03 |
| C9 | Ranking | `OpportunityBook` | Strongest expression per thesis; how everything orders | 05 |
| C10 | Execution Readiness | `ExecutionDecision` | With live quotes now, is the ranked expression still valid/executable? | 05 |
| C11 | Decision Ledger | `LedgerRecord` | What was decided, and what was not, before the outcome was known | 06 |
| C12 | Outcome | `UnderlyingOutcome`, `ExpressionOutcome` | What actually happened, to underlying and to each expression | 06 |
| C13 | Validation & Learning | `ValidationReport`, model versions | Were probabilities/timing/valuation/selection/rank right? | 06 |
| C14 | Presentation | `LabReadModel` | What the trader sees (read-only) | — |

`avshunter/c12_outcome/` in code is the C12 Outcome context — signal_ledger.py,
service.py, hypotheses.py, base_rate.py etc. It is the outcome-scoring engine
CLAUDE.md refers to; a fix is only "accepted" once this shows the targeted
metric moving on real history and forward sessions.

## Business flow (the one-way dependency)

```
RUN CONTEXT → MARKET DATA → UNIVERSE & ELIGIBILITY → MARKET STRUCTURE (candidate
geometries) → EVIDENCE (per geometry) → THESIS (selects geometry, frozen) →
EXPRESSION GENERATION + TRADEABILITY → VOLATILITY & CONVEXITY → VALUATION
(all tradeable expressions, common path set) → RANKING (RAEV; strongest wins)
→ LIVE EXECUTION REVALUATION → DECISION → UNDERLYING + EXPRESSION OUTCOMES →
VALIDATION / LEARNING
```

Critical point: **there is no "contract selector" stage.** No context picks a
single contract before valuation — selection is the *result* of valuing every
tradeable expression and ranking them (RAEV descending). If you find code that
picks one contract early, that's a spec violation, not a design choice to
preserve.

The Decision Ledger (C11) is not a step at the end — every context from
Universe & Eligibility onward writes its published output to the ledger as
produced.

## The seven invariants (apply to every context, no exceptions)

- **A — one owner per business fact.** Eligibility→C2, geometry→C3,
  probability/timing→C4, direction/window/target/invalidation→C5,
  expression eligibility→C6, vol forecast→C7, EV/RAEV→C8, rank→C9,
  execution action→C10, outcome→C12. A downstream context may reject an
  upstream object as unusable; it may never rewrite its meaning.
- **B — unknown means unknown.** Never substitute a neutral/default value
  (0.5 regime score, constant convexity score, a silent PASS) for a failed
  computation. Return an explicit `InsufficientEvidence`/similar instead.
- **C — published aggregates are immutable.** Once a Thesis is published,
  its direction/target/invalidation/window/evidence ref/structure
  ref/selected geometry cannot be altered downstream. A real change in
  conditions produces a new thesis version (supersession, §9), never a
  mutation.
- **D — direction symmetry.** BEAR theses use mirrored evidence/barriers/
  valuation. No statistic computed upside-only may be reused downside.
- **E — data hygiene.** Evidence/validation built only from cleaned,
  split/dividend-adjusted, outlier-validated, point-in-time-labelled
  returns. Nothing after the evidence session is used. Failed-validation
  returns are excluded with a recorded reason, never capped silently.
- **F — freshness is explicit.** Every consumer declares the session it
  requires; older data is `STALE`, never silently treated as current.
- **G — authority is earned.** No model/score/signal influences a gate,
  valuation or rank until it has passed the validation progression
  (referenced in spec as §24 / CLAUDE.md gates G1–G4 — the exact gate
  definitions live in `Enhancements/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md`,
  read that file rather than assuming). Until then, display only, clearly
  labelled advisory/legacy.

## Ranking (C9) — rank, don't gate

- RAEV = lower-bound EV per dollar at risk. It is the ranking measure;
  time-normalised return is published alongside it and is the first
  tie-break.
- Strongest expression per thesis = highest RAEV. Direction state
  (`SUPPORTED`/`UNSUPPORTED`/`OPPOSED`) is **descriptive, not a gate** — a
  complete thesis with usable evidence always flows to expression
  generation and valuation; weak/opposing evidence shows up as lower
  EV/RAEV/rank or `NO_POSITIVE_EDGE`, never as a dropped thesis.
- Hysteresis prevents day-to-day flip-flopping (keep previous run's leader
  unless the new leader's RAEV exceeds it by more than switching cost plus
  a noise margin) but never keeps an expression with RAEV ≤ 0 or that is
  no longer tradeable.
- This is the design authority behind ACK's "rank, don't gate" position —
  it is not just ACK's opinion, it is what the signed-off spec requires.

## Valuation (C8) — sole owner of EV

- Sole owner of trade economics. No legacy engine output (including EV v2)
  may be presented as, substituted for, or combined with Valuation's EV.
  **EV3 is non-authoritative until this context passes the validation
  gates** — this is a standing spec rule, not a one-off finding from an
  earlier audit.

## Macro / event guards

Spec appendix explicitly confirms: macro and event guards are **display-only
for manual review** — they never influence a gate, score, or rank (this is
also CLAUDE.md rule 6). Any design that has USMI, GEX, or macro routing
sizing or gating a trade is a spec violation regardless of how well it
performs in a backtest.
