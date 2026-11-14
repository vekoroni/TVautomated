# AVS-TRADE-001: Codex review of v2 contract scenario

Date: 14 November 2026. Reviewer: Codex, in the separate review chat.

Status: **REVISIONS REQUIRED BEFORE BUILD.** This is a design and local-code review, not implementation acceptance or ACK approval. Section 14 remains proposed. No provider, pipeline, broker, implementation or commit action was performed by this reviewer.

Reviewed: the v2 design, review request and first review beside this file; current local valuation, timing, selector and Morning callers; repository guidance; the active ETF chat's visible changes and build note. The design's stated baseline is 23ad527; I could not independently verify current Git status because the Git command failed with a cwd permission error. Current files may contain concurrent ETF work. No tests or benchmarks were run for this review.

## F1–F7 disposition

“Resolved” below means resolved in the written design, with implementation evidence still outstanding.

| Finding | Disposition | Assessment |
|---|---|---|
| F1: operational field collision | Resolved in design | Separate scenario names and the saved-handoff regression address the original issue. Never populate monetisation_n_q50/q80 through aliases, merges or default field lists. Preserve existing observed A12 fields. |
| F2: scenario versus empirical quantile | Partly resolved | Renaming, explicit path, invalidation limitation and both thresholds are good. Sections 4 and 9 specify different spot/date anchors; choose explicit mode-specific semantics. The claim that value can only decay after target arrival is not guaranteed by the reused American/dividend-aware pricer. Either define the search as truncated at arrival and label that limitation, or search through the contractual deadline. |
| F3: discarded strikes | Resolved in principle; construction incomplete | The bounded set and limitation label address the original concern. Define eligibility before the top-M step, deduplication by OCC, deterministic ties, expiry ordering, and best-liquidity ordering. Confirm the input pool has not already discarded strikes or shorter usable expiries upstream. |
| F4: Morning anchors | Partly resolved | Fresh-entry-only and remaining pace are the right distinction. The API and caller changes do not yet carry frozen thesis identity/date and quote time explicitly. Resolve section 4 versus 9, invalid/missing dates, partial-session counting and independent exhaustion of median/slow paces. |
| F5: costs and stress | Partly resolved | Missing-bid rejection, IV-down and wide-exit variants address the core defect. Specify missing/zero ask, zero bid, nonfinite inputs, provisional provenance and per-variant missing states. The current cost helper has no exit-spread multiplier; extending it must preserve entry ask and existing callers. |
| F6: coverage and objective | Partly resolved | Explicit blank reasons and deadlines are good. The stated earliest-crossing objective conflicts with tier-first ordering. Coverage and search use different buffer cutoffs; define one exact convention and which pace/threshold/variant coverage describes. |
| F7: quote validity and tier | Partly resolved | Rejecting crossed quotes fixes the confirmed defect. Complete the zero-bid policy, low-premium B fallback and provisional eligibility. Changing Lane B's shared-tier adapter can change downstream handling even if window_flag is untouched; pin intended changes and preserve other behaviour. |

## Required clarifications before build

### 1. Selection objective and candidate universe

Section 6 ranks tier before crossing time. An A contract crossing at session 10 therefore beats a B contract crossing at session 2. That is “best tier, then earliest crossing”, not “earliest crossing among tradeable contracts”. Choose one and make the prose, sort key and fixture agree; do not silently resolve this business choice in code.

The proposed maximum is correct: 4 × (3 + 1) + 1 = 17 distinct contracts. It is an upper bound after OCC deduplication. Specify eligibility, ties, provenance, valid OI and low-premium rules before selecting the best-liquidity addition. Explain what happens when a nearest expiry has fewer than M valid candidates. Publish exclusions from the actual available input chain, including upstream filters; counts cannot imply the whole chain was assessed if only prefiltered scores were received.

Keep the existing value shortlist and value outputs unchanged. Enlarging its input list directly would alter contract_value_best_symbol and alternatives even in SHADOW. Construct the scenario set within the existing owner but independently of the legacy value comparison. Cache repeated scenario requests by exact contract, anchors, assumptions and configuration version.

### 2. Morning mode and frozen deadlines

Define the fresh-entry formula explicitly: for future offset j from the quote, use the quote spot and the frozen target with T_remaining, while retaining the frozen thesis origin for elapsed-time calculation. This is a new conditional scenario at each quote, not continuation of the original smooth path. Section 4 must say when this exception applies. Do not recompute the target from a shorter volatility reach without explicitly specifying that change.

domain/trade_timing.py:65 counts completed XNYS sessions and treats a timestamp before today's close differently from a date-only input. Pass a timezone-aware assessment timestamp to that owner; a Morning date alone spends a full session prematurely. Missing/future thesis origins must stay unassessed, never fall back to today's date. Repaired OCC identity must not reset the thesis origin.

Handle median pace exhausted while slow pace remains separately: no forced positive median time and no removal of an otherwise assessable slow result. Handle already-reached/wrong-side target and resolved/invalidated thesis explicitly. The new scenario must not overwrite existing hold or anticipated-value fields while adding countdown behaviour.

### 3. scenario_crossing integration

Calling a pure helper from anticipated_move_fields is reasonable, but is not specified adequately yet. Its current signature at domain/anticipated_move.py:79 lacks frozen thesis origin/identity, quote timestamp and scenario mode. Its early returns can omit precise scenario states. morning_gate.py:1280 passes today's contract date with original duration bars and attaches quote time only after the call. Merely adding a nested call preserves the restart defect.

Specify the new optional inputs, both Evening and Morning caller changes, explicit state propagation through early returns, and how candidates use the same frozen target/pace. Add morning_gate.py to section 13's change list. Extend the scenario output field lists deliberately; do not replace existing scenario_exit_sessions, scenario_exit_date, scenario_iv_basis or existing payoff values accidentally. Projection and card integration require an explicit owning renderer/file as well as export lists.

### 4. Search, deadlines and states

Section 4 searches to expiry minus 5 exit sessions, whereas section 5 requires crossing plus 3 monitoring plus 5 exit sessions. Distinguish a calculated but non-covering crossing from a covering result, or use one common usable deadline. For the primary coverage flag state explicitly whether it means slow-pace +30% base; other thresholds/stresses need their own coverage or an unambiguous narrower label. Publish the assessment origin for session offsets, and monitor/exit dates as well as offsets.

Stopping at T is permissible as a declared experiment boundary, but does not prove no later crossing exists. Calendar mapping and integer rounding must be explicit for fractional duration, expiry day and non-session expiry. A missing or exhausted input is never zero profit time. Preserve states separately per pace, threshold and stress; a single scenario_state cannot explain mixed success and missingness.

### 5. Quote provenance, cost interface and operational boundary

Define valid two-sided quotes as a concrete numeric policy, including zero bid/ask. Current Lane B treats bid <= 0 as NO_BID; v2 only explicitly rejects negative values. Preserve the 11 Nov rule in full: a narrow-percent quote that fails the low-premium width condition currently falls to B. Section 7's “B = 10 to 20%” leaves that case undefined.

PROVISIONAL must survive into every candidate record and shadow result. A tier A provisional quote must not be described as tradeable solely because it has tier A. Either exclude provisional candidates from the tradeable shadow or explicitly label a separate provisional research comparison. Reuse the existing freshness/session policy; do not introduce an unstated threshold.

For wide exit, multiply only the exit spread deduction, not entry ask, entry fee or closing fee. The present return_on_premium helper accepts only bid/ask. Add a backward-compatible explicit spread-stress input in the shared cost owner and list domain/option_valuation.py among changed files if this is the chosen implementation. Changing bid to simulate a wider spread risks negative synthetic bids and misleading quote validity. Record model/config version and resolved rate/dividend assumptions; a disclosed fallback remains an assumption, not supplied market evidence.

The design currently says nothing operational changes while intentionally correcting Lane B classification. Qualify this promise: only documented invalid/missing-quote corrections may alter liquidity outputs, with no new scenario authority. Check all consumers of the tier return shape and eligibility; keep window flags and existing ordering/gates/verdicts unchanged except for separately specified defect consequences. If those promises conflict, resolve the scope before build.

### 6. Run-time budget

Run check 8 is an appropriate release condition but not yet a budget. Record a saved representative workload, baseline hardware/configuration, row and horizon distribution, wall time and peak memory, valuation-call count, agreed absolute/incremental limits, and long-horizon worst cases before release. No live run is authorized by this review.

The shared American CRR pricer loops over its tree for each value, so 17 contracts × sessions × variants can be substantial. Compute the thresholds from each valuation once rather than price separately per threshold; cache/vectorize through existing owners where appropriate. Benchmark both selected-contract publication and shadow evaluation so nesting does not duplicate work. Reduce N/M only by versioned configuration with the resulting candidate scope reported; never silently skip long horizons or safety checks to fit a timer. A truncated computation needs an explicit state.

The test that IV-down can only delay/remove crossing is not universally valid for the American pricer: reduced volatility can increase value in early-exercise-sensitive cases. Use controlled fixtures where the monotonic result holds, and allow truthful counterexamples rather than clamping outputs. For either pace/stress, compare unrounded net returns to thresholds and round only for display to avoid premature crossings.

## File collisions: observed work, not an assurance of exclusivity

This review chat has no implementation work open in either scripts/avshunter_options_intelligence.py or contracts/lab_control.py and will edit neither.

The separate active chat **Identify actuarial database gaps** has already changed contracts/lab_control.py and contracts/lab_review_projection.py for ETF identity publication, plus new canonical_data/instrument_identity.py, config/instrument_identity_v1.json and tests/test_etf_identity_reliability.py. Its visible status says it will pause further lab_control.py edits after receiving the coordination message. This is an actual shared-file collision, not merely a planned one. Preserve its additive identity changes; do not restore the design baseline over them.

No edit to scripts/avshunter_options_intelligence.py was shown in the inspected ETF turn. That is bounded observation, not proof that no other editor has it open. The ETF roadmap also includes later quote/dividend/publication work, so check domain/option_valuation.py, domain/option_contract_liquidity.py and the projection interface before extending those owners.

The mistakenly forwarded review request has been withdrawn from the busy chat; this separate chat owns this review. Before build, establish a concrete shared-file handoff with the ETF writer: identify the current edits, finish/park them, then let Claude be the one writer for the agreed interval. Do not treat this snapshot or a chat pause as a filesystem lock. Current Git cleanliness, branch and tip were not independently established here.

## Closure and approval boundary

V2 is substantially improved and fits a display-only scenario experiment. Amend the objective, mode-specific anchors/API, deadline semantics, quote eligibility and cost-stress interface before build. Then obtain ACK's section 14 decisions. Saved-data correctness, candidate reconciliation and operational non-interference evidence remain required; the benchmark and later normal-run evidence are separate release checks. The historical empirical clock remains a separate design/replay task.

Only this review document is saved by this review task. Nothing here approves section 14, starts a scenario build, changes the operational Lane B clock, authorizes providers/pipeline runs, or commits files.
