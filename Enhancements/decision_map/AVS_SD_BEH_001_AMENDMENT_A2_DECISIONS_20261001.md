# BEH-001 Amendment A2 — decisions (Part 4 of the constraint register, 1 Oct 2026)

Companion to `AVS_SD_BEH_001_AMENDMENT_A2_SCOPE_AND_CONSTRAINT_REGISTER_20261001.md`. That file was locked when these decisions were recorded.

ACK delegated these decisions to Claude: "assess against the build then make the best decisions that will give me a working product". The decisions take into account the independent review ACK supplied.

| ID | Decision | Amendment adopted |
|---|---|---|
| C-01 | APPROVED WITH AMENDMENT | Option-motivated thresholds leave behavioural admission and travel as measured attributes. Options assesses real contracts, quotes, spreads and liquidity against the expected move. The same thresholds are not transplanted automatically. |
| C-02 | APPROVED WITH AMENDMENT | Directed candidates and monitoring observations are both kept, with separate statuses. Monitoring observations do not trigger contract searches. Scores are kept for prioritisation only. |
| C-03 | APPROVED, FIRST | A persistent candidate identity and life cycle (an append-only ledger with state, age, parent and relationships) is built before the handoff changes. Portfolio and execution rules decide competing exposures. |
| C-04 | APPROVED WITH AMENDMENT | No fixed window in behavioural classification. Separate estimates are published for time to activation, time to the favourable outcome and time to invalidation. Any holding-period limit stays with Execution. |
| C-05 | APPROVED WITH AMENDMENT | Event-based (first-passage) statistics are added, and the 5/10/20 views are kept as supplementary. Each statistic carries unresolved counts, sample size, uncertainty and validation status, conditioned on behaviour, timeframe and context. |
| C-06 | REJECTED AS WRITTEN; REPLACED | Remaining time to the favourable outcome becomes one input to expiry selection. Options evaluates expiries, premium, Greeks, IV, liquidity, event exposure and the instrument mandate. Percentiles and buffers need validation before use. |
| C-07 | APPROVED AS A CONSEQUENCE | Handoff by candidate status and each receiving stage's contract. Monitoring observations and rejected expression attempts are kept. Resource deferral is recorded separately from behavioural rejection. |

## Requirements added
- **RQ-1 Activation ≠ outcome.** Every signal type has a measurable outcome definition (`Outcome_Level` plus a rule), evaluated separately from trigger activation.
- **RQ-2 Failure leads to the next logic.** Invalidation closes the candidate and links any successor candidate to it as its parent. The successor needs its own evidence and trigger.
- **RQ-3 Remaining duration depends on age.** Duration estimates are conditioned on the candidate's current age and state, never re-issued at full length.

## A2-1 clarified
- Each candidate is evaluated on its own timeframe's confirmation rule. Where the order of events cannot be established, the result is AMBIGUOUS.
- Unresolved at the research limit means censored, measured with cumulative incidence over time, never success or failure.
- The 50% reference applies only to the symmetric ±1R test. Other geometries use a matched reference.

## Build phases
No stage is left half-built. Production stays on `legacy_rollback` until phase 2 is accepted.

1. **Phase 1 (BEH-001 completion):**
   - outcome definitions (RQ-1);
   - the candidate ledger with life cycle, age and parent links (C-03 core, RQ-2);
   - the corrected evaluation (A2-1);
   - a population replay reporting original versus newly admitted rows separately.
2. **Phase 2:**
   - candidate-level handoff (C-03 handoff, C-01, C-02, C-07);
   - duration evidence (C-04, C-05, RQ-3).
3. **Phase 3:** the option-selection replacement (C-06).
