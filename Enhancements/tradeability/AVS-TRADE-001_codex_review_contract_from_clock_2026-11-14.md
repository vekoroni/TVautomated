# AVS-TRADE-001: Codex review of contract-from-clock design

Date: 14 November 2026.
Design reviewed: [Claude's design note](AVS-TRADE-001_design_contract_from_clock_2026-11-14.md), snapshot referencing checkout `23ad527`.
Implementation owner: Claude Code, including Lane B.
Reviewer: Codex.
Status: **REVISIONS REQUIRED BEFORE BUILD. Review only; no implementation approval.**

## Conclusion

The architecture is sensible, but the design needs revision before approval. It can support a labelled scenario experiment, not yet the historical monetisation clock ACK requested. Publishing more scenario values does not by itself establish realistic, achievable option returns.

ACK requested this review be saved alongside the design so Claude can address all seven findings before building. Codex is not building a parallel selector, changing Lane B or implementing this design. Codex's role here is design/evidence review. This document changes no trading policy and authorizes no provider calls or pipeline run.

Line references below refer to the reviewed design snapshot. Supporting code was inspected using saved local files; the original review did not run new tests, backtests, providers or the pipeline.

## Seven findings for Claude to address

### 1. Shadow publication would change Lane B behaviour

Design reference: line 113; also lines 14 and 165.

Publishing `monetisation_n_q50` automatically changes Lane B's window classification. Adding a scenario label does not remove that operational effect. This conflicts with the claim that the work has no authority and changes no gating or prioritisation behaviour.

Supporting code: `data/scratch/workaround/build_lab_handoff.py:195` uses a numeric `monetisation_n_q50` in preference to the arrival-time proxy, without checking scenario validation/authority.

Required revision: publish separate scenario fields, and keep the operational window flag unchanged until separately approved. Claude owns any subsequent Lane B adoption.

Acceptance evidence: a saved hand-off regression showing that publishing unvalidated scenario fields changes neither existing window flags nor ordering, selection, gates or verdicts. Any later adoption must have an explicit approval and authority contract.

### 2. Scenario crossing times are not measured monetisation quantiles

Design reference: lines 46-53.

The proposed numbers are first-profit crossings on two assumed smooth paths. A square-root volatility envelope is not evidence that a stock follows that trajectory. Reusing `reach_by` therefore adds a path assumption, contrary to line 51's claim that no new speed assumption is added. Arrival-time q50/q80 do not automatically become q50/q80 of option first-profit time.

Supporting code: `domain/anticipated_move.py` uses `reach_by` as a volatility-based reach/cap and combines it with structural levels; it is not a replay of historical intermediate price paths. Observed A12 explicitly has a different descriptive measurement basis in `contracts/monetisation_clock.py:16`.

Required revision: use unambiguous names such as `scenario_n_median_pace` and `scenario_n_slow_pace`, separate from observed A12 quantiles. Specify the mathematical path, its anchor, whether it stops at the target or extrapolates beyond it, and how invalidation, resolution and the permitted exit deadline are handled. Show both +20% and +30%; do not silently replace one with the other.

Acceptance evidence: deterministic path/valuation fixtures and clear scenario labels. Historical replay with failures, censoring and invalidation remains necessary before claiming empirical n quantiles. Scenario coverage must not be compared with observed A12 coverage as if the two methods measured the same thing.

### 3. Existing shortlist may discard the better clock-based contract

Design reference: lines 77-85.

The existing selector keeps only the highest-scoring contract per expiry before the proposed clock comparison. Another strike in that expiry could have better timing or liquidity but never reach that comparison.

Supporting code: `scripts/avshunter_options_intelligence.py:6011`, `apply_contract_value_selection`, builds the shortlist from `contract_score`, keyed by expiry, plus the chosen contract.

Required revision: either evaluate a bounded, explicit candidate set appropriate to this research objective or describe the result as **best within the existing score shortlist**. Do not call it the best contract from n without that limitation. Do not alter active selection as part of a shadow experiment.

Acceptance evidence: a saved fixture with two strikes in the same expiry where the lower legacy-score contract has the better clock/liquidity result; prove it is assessed or explicitly excluded by the documented research scope. Record candidate counts and reasons.

### 4. Morning recomputation needs explicit clock and cost anchors

Design reference: line 119.

Calling the common function does not establish correct countdown behaviour. The current Morning caller supplies today's spot/quote and the original duration evidence; a naive extension could restart the scenario runway each morning.

Supporting code: `morning_gate.py:1280`, within `_recompute_for_morning_contract`, passes the original duration q50/q80 and today's contract reference date. `domain/trade_timing.py:65` separately owns remaining-hold calculations.

Required revision: distinguish a fresh-entry scenario at today's ask from management of an existing trade against its original entry cost and remaining deadline. Preserve the relevant frozen thesis/reference dates; do not reset an existing trade's monetisation deadline on each quote refresh. Record exact OCC, thesis/entry identity, reference/as-of date and quote timestamp.

Acceptance evidence: saved consecutive-session fixtures, including a holiday and a repaired contract. Revaluation must use the intended remaining window; a genuinely new entry/expression must be distinguishable from an existing one. No claim that shared-function wiring alone proves the behaviour.

### 5. Execution gaps and IV stress must be visible in timing

Design reference: lines 44-45, 63 and 162-164.

A calculated model profit must not appear to be achievable, cost-complete profit when execution inputs are missing. The current valuation helper deducts no spread when bid is absent. A separate earnings valuation at another horizon is not a stressed first-profit clock.

Supporting code: `domain/option_valuation.py:142`, `exit_proceeds_usd_per_share`, uses zero spread deduction when bid is missing; `cost_basis` discloses that omission.

Required revision: require valid quote provenance and distinguish unassessed execution costs from an executable-looking n. Include IV-down and wider-spread timing scenarios alongside flat IV, using the shared pricer/cost owner. Record rate/dividend assumptions and missingness; do not introduce an optimistic fallback to improve coverage.

Acceptance evidence: fixtures for missing bid/ask/IV, stale and crossed quotes, costs and fee units, IV reduction and wider exit spreads. Stress can delay the crossing or remove it entirely; report both, not just later numeric n. Model marks remain scenario estimates, not observed fills.

### 6. Coverage and selection fallback are incomplete

Design reference: lines 69-88.

The note explains the no-n case, but not the case where contracts have n and none covers n plus buffers. It also equates nearest expiry with least time paid for; that does not establish cheapest premium or best value.

Required revision: recommend a blank covering shadow choice with an explicit `NO_COVERING_CANDIDATE` reason, rather than an implicit fallback. If non-covering contracts are displayed for research, identify them separately. Publish monitoring and exit deadlines explicitly, with exact session conventions and configured buffers; distinguish them from thesis runway. Document the selection objective rather than implying that earliest n or shortest expiry proves superior economic value.

Acceptance evidence: all candidates have n but fail coverage; only illiquid candidates cover; selected contract covers n but not thesis q80; zero/one-session and expiry/holiday boundaries. Existing active selection and planned hold must remain unchanged.

### 7. Liquidity parity must not preserve invalid quote classifications

Design reference: line 90 and test 11 at line 142.

Centralising thresholds is appropriate, but exact parity with the current Lane B function is not sufficient. That function does not reject a crossed quote before calculating spread width; a negative width can receive a favourable tier if the other tests pass.

Supporting code: `data/scratch/workaround/build_lab_handoff.py:172`, `liquidity_tier`, computes `ask - bid` without a crossed-quote rejection. Codex reviewed this code only; Claude owns its correction.

Required revision: define validity/provenance independently of the tier thresholds. Invalid, missing, stale or post-close data must not become an apparently executable tier A quote. Keep an explanatory distinction between invalid/unassessed data and valid but low-liquidity contracts. Preserve existing safety checks.

Acceptance evidence: crossed, missing, zero-bid, stale and post-close quotes; unknown OI; exact spread/OI boundaries; low-premium width rule. Update parity expectations for confirmed defects rather than requiring their reproduction.

## Architecture accepted in principle

- Reuse the existing selection and valuation owners; no second pricer or parallel active selector.
- Assess each alternative's exact contract separately.
- Preserve the active selected contract and planned hold while researching the shadow comparison.
- Keep observed A12 fields and scenario timing separate, with their own identities, evidence and limitations.
- Test with saved data before implementation/release, and distinguish offline correctness from operational closure.

## Recommended revised scope and approval boundary

The proposed build should be described as **a display-only, saved-data scenario comparison of when each exact contract would cross +20% and +30% under explicitly assumed paths and stresses**, plus expiry coverage and a clearly bounded shadow alternative comparison.

It must not automatically replace the Lane B window clock, claim empirical n quantiles, imply a probability of monetisation or activate selection. Historical setup replay remains a separate necessary step for the empirical clock: include non-hits, invalidation, incomplete paths, censoring, costs and point-in-time inputs. Compare scenario and observed results only when entry identity, cost anchor, observation cadence and deadline match.

ACK decisions after Claude's revision: whether to approve the explicit scenario-path assumption; the bounded candidate set and shadow objective; buffer/deadline semantics; and any later operational adoption. +30% may be the nominated display default, but both +20% and +30% remain required for comparison. No current approval to switch SHADOW to ACTIVE is implied.

## Handoff to Claude

Please address F1-F7 in the design before building, recording the revised decision, owning function/interface and acceptance fixture for each. Keep Claude as the implementation writer and Lane B owner. Codex can review the revised design and subsequent saved-data evidence when requested; no parallel Codex implementation is being started.

Actions taken: saved this review only. No implementation, configuration, database, Lane B, provider state or pipeline output was changed. No providers, tests or pipeline were run to save this document.
