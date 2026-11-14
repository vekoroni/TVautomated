# AVS-TRADE-001: Codex v3 crossing-scenario review

Date: 14 November 2026. Reviewer: the separate Codex review chat. Builder: Claude Code. Decision authority: ACK.

**Status: targeted revisions required before build.** V3 resolves most v2 concerns in design. The remaining items below are specific contract/wiring gaps, not a request to redesign the experiment. Section 15 remains proposed, not approved. Design acceptance is distinct from implementation verification and release evidence.

Reviewed: the v3 request and revised design in this folder, the saved v2 review, and current local selector, timing/calendar, valuation and liquidity interfaces. No tests, benchmark, providers, pipeline or trading actions were run. No implementation files were edited by this review chat. The branch/tip in the request are reported baseline information, not independently reverified here.

## Disposition of every v2 review point

Resolved means resolved in the design; tests and run evidence are still required after approval.

| V2 point | V3 disposition |
|---|---|
| F1: no operational monetisation names, including aliases/default lists | Resolved: sections 1, 4, 11 and 12 explicitly exclude them and pin handoff behaviour. |
| F2: Evening/Morning anchor conflict | Resolved in intent: section 5 gives one conditional formula and freezes the thesis origin/target. The session-offset-to-date mapping still needs the clarification below. |
| F2: unsupported post-arrival decay claim | Resolved: search truncation at arrival is declared as an experiment boundary. Its non-crossing state still overclaims when a different boundary ends the search first. |
| F3: eligibility, deduplication, ties, expiry ordering, best-liquidity addition, upstream filters | Substantially resolved: section 7 defines a deterministic bounded scored-pool comparison and upstream counts. Correct the pool description to include core-delta preference narrowing and the spread-above-limit fallback, both present in the current selector. This does not require widening scope. |
| F4: optional API inputs, anchors, early returns, callers | Resolved in design: sections 10 and 14 name inputs and three callers. Keep thesis identity, exact OCC, quote time and frozen target/pace provenance together in the result; date alone is not a thesis identity. |
| F4: completed sessions, missing/future origin, independent pace exhaustion | Resolved in intent, subject to the date-mapping fixture below. |
| F4: reached/wrong-side target, inactive thesis, no overwrite of hold fields | Resolved in scope; define state precedence. A price beyond a frozen valid target can also look “wrong side” relative to current spot. |
| F5: zero/missing/nonfinite quotes, provisional eligibility, per-variant states | Mostly resolved: explicit policies and 12 records. Reconcile the invalid/unassessed naming between sections 5 and 8; correct the provenance-owner reference below. |
| F5: shared exit-spread multiplier | Resolved in interface direction: default 1.0 preserves callers and no synthetic bid is used. Add the unrounded-return interface below. |
| F6: objective versus tier-first ordering | Resolved: earliest crossing first; tier is eligibility/tie-break. |
| F6: usable/search/coverage deadlines | Resolved arithmetically: search through E−5, cover only if j+3<=E−5. Non-crossing states and zero/negative U remain incomplete. |
| F6: headline pace/threshold/variant identity | Resolved: crossing_covers_slow30_base, with separate records. |
| F7: zero bid, low-premium B fallback, provisional handling | Zero-bid and low-premium rules resolved. Provenance exclusion is correct in intent but its actual owner/input contract is not yet identified. |
| F7: Lane B adapter and downstream behaviour | Resolved in scope: retain shape, explicitly allow only crossed-quote correction, pin consumers. Preserve the existing boundary tolerance and supplied settings, not merely the nominal percentages. |
| Keep legacy value outputs unchanged | Resolved: separate scenario set with field-for-field regression. |
| Existing scenario_* name collisions | Resolved: crossing_* prefix for new scenario fields. Check the remaining contract_liquidity_* names against current publication fields before adding them. |
| Projection/card integration owner | Resolved: named renderer and trade-card call. Include loading/export wiring appropriate to the existing renderer architecture. |
| Runtime workload, budget, scope reduction and reporting | Resolved as a proposed release plan, not measured acceptance. State initial search cap and full-workload Morning benchmark population before executing the benchmark. |
| IV-down not universally monotonic | Resolved: controlled fixtures plus truthful American-pricing counterexample. |
| Unrounded threshold comparisons | Not yet implementable through the specified existing return interface; see R1. |
| File collision and one-writer handoff | Correct precondition in section 2. Owner confirmation is recorded separately below; this review does not grant a writing interval. |

## Required corrections before build

### R1. Specify a backward-compatible unrounded return interface

Section 5 requires unrounded threshold comparisons, but domain/option_valuation.py:return_on_premium currently returns round(..., 4). Section 9 only adds exit_spread_multiple. Passing that multiplier through the existing helper still rounds away information before the crossing comparison.

Specify a shared raw-return owner, or an optional precision/rounding argument whose default exactly preserves existing callers. The crossing helper must request raw values; display fields may round later. Do not introduce a second cost formula in the crossing module. Validate the new multiplier as finite and nonnegative (and specify the allowed stress range in configuration).

Acceptance: raw return just below 0.30 that rounds to 0.3000 does not cross +30%; exact threshold does. Existing callers, default costs and published old values remain identical. This is a concrete wiring gap, not just a missing test.

### R2. Report the boundary actually searched

J=min(R,U,cap) is coherent, and CROSSES_NOT_COVERING is meaningful for U−3<j<=U. However, NO_CROSSING_BY_ARRIVAL is defined as “not crossed by J”. When U<R, arrival was not searched. A cap that exceeds U but is below R did not cause truncation either. Those cases must not be labelled as evidence of no crossing by arrival or as cap exhaustion.

Record search_end_session/date and the limiting boundary (arrival, usable deadline, config cap, including deterministic ties). Use a usable-deadline-specific non-crossing state when U ends the search first. NO_CROSSING_BY_ARRIVAL is valid only when arrival was actually reached. When U<=0, report no usable window explicitly; do not manufacture a crossing or feed a negative offset to date arithmetic. Headline coverage must distinguish a genuine assessed failure from unassessed/incomplete search according to a written rule.

Acceptance: no hit with R=20,U=5,cap=30; no hit with R=20,U=30,cap=5; no hit with R=5,U=30,cap=30; tied boundaries; U=0 and U<0. Excluded/truncated candidates must not be treated as proved incapable. Preserve the bounded-set label and display the cap because an unsearched candidate could cross earlier than the displayed shadow.

### R3. Name the actual quote-provenance owner and evidence inputs

Section 8 cites domain/option_contract_liquidity.py:403–460 as the existing freshness/session owner. The inspected function is classify_current_executability: it consumes quote_age_seconds, DTE and spread inputs. It does not take a quote timestamp, assessment timestamp or session-close tolerance and cannot itself establish “session-aligned Evening close quote”. label_eod_quote_state below it only distinguishes presence of a timestamp; it does not validate session alignment.

Identify the existing canonical timestamp/session assessment service or saved assessment fields that supply this decision, with the policy/version and required per-candidate inputs. If an adapter is needed, list it explicitly and reuse the calendar/config owners. Do not interpret SESSION_ALIGNED text or timestamp presence alone as proof of fresh, matching evidence. Match quote, spot, IV, exact OCC and evidence date; unknown alignment must remain provisional.

Keep Morning quote assessment time separate from the frozen thesis origin. For Evening, state what happens when the actual saved quote is not at the evidence close used as A: reject/provisionalise or explicitly label the mismatch; never restamp the quote. Tests should prove aligned close, early close, stale/different-session quote, unknown timestamp and genuine Morning freshness using the named service.

## Additional concrete clarifications

1. **Morning offsets and dates.** remaining_hold excludes today's not-yet-completed session, whereas sessions_between and after_sessions exclude their start date. At a Tuesday Morning quote following a Monday-origin thesis, e=0. If j=1 means Wednesday under after_sessions(Tuesday,1), the remaining pace and exit-date grid differ from a convention where Tuesday close is the first future observation. Choose and publish the intended convention; do not mix them accidentally. A fixture must assert actual j=1 date, R-th date, E, U and coverage, before/after close and across a holiday. This review does not prescribe intraday sampling; it asks the design to fix its sampling grid explicitly.

2. **Pool description.** select_best_contract also narrows eligible rows to the preferred core-delta band whenever any such rows exist, and retains two-sided above-limit quotes when no within-limit quote exists. Describe both and include them in sequential exclusion accounting. Counts must reconcile without double-counting overlapping failures. Do not change selector behaviour to make the descriptive sentence true.

3. **State precedence and provenance.** Section 5 calls negative/nonfinite quotes invalid, while section 8 groups nonpositive/nonfinite inputs under unassessed NO_ASK/NO_BID for Lane B compatibility. These can be distinct crossing versus compatibility states, but document that mapping and precedence, including reached target versus wrong-side target. Also distinguish missing/invalid spot, strike, active-thesis status and pricing numeric failure from a genuine no-crossing result. Unknown active status must not be assumed true solely to obtain coverage.

4. **Lane B compatibility.** The current tier function accepts caller settings and applies 1e-9 tolerance at spread/width boundaries. Preserve both in the adapter so the promise of exactly one changed case is testable. Check contract_liquidity_* publication names for semantic collisions. No scalar or string should be replaced with a richer object under an existing name.

5. **Benchmarks and reproducibility.** Proposed +2/+20 minute limits remain ACK decisions. Define the initial cap and parameter bounds before benchmark; record saved run file hashes, source/config versions and full Morning row population. A workload containing only selected rows does not benchmark the 17-contract shadow set unless saved candidate chains/scores are available. Missing candidates are a benchmark-input gap, not permission to synthesize them. Record quote/spot/IV source identity and thesis identity along with existing anchor fields for reproducible results.

## ETF owner handoff confirmation

The ETF chat **Identify actuarial database gaps** has now explicitly confirmed that all five shared files are **parked now**, with no further edits until ownership is coordinated:

| File | ETF additions to preserve |
|---|---|
| contracts/lab_control.py | Identity-field import/export and disclosure attachment after canonical ranking |
| contracts/lab_review_projection.py | Identity fields in home/card publication |
| intelligence-lab/static/review-app.js | Identity disclosure renderer call |
| intelligence-lab/static/review.html | Identity script inclusion and cache version |
| intelligence-lab/static/trade-card.js | Instrument identity/research-policy display |

The owner states: nothing is committed, there is no commit authorization or scheduled commit, and none of these five files remains actively owned for editing by that chat. Claude may take over after ACK's confirmation; later ETF wiring must be coordinated with him. Preserve canonical_data/instrument_identity.py, config/instrument_identity_v1.json, instrument-identity.js, the inventory script, tests and audit receipts as dependencies. Integrate around the existing additions; do not reset or replace whole files.

This is the owner's explicit parked-state confirmation, not a reviewer certification of an exclusive filesystem lock. The owner's latest Git diff recheck was permission-blocked, so it cannot certify that no other writer has changed the files since its last successful check. Section 2's reread and ACK-confirmed writing interval remain outstanding. No commit is needed merely to satisfy the parked alternative.

## Approval and completion boundary

Correct R1–R3 and the listed state/calendar contract details in the design before build. Most other v2 findings are resolved in design and need evidence, not another architecture. Obtain ACK's section 15 decisions and shared-file writing interval after the owner handoff is settled. Preserve all ETF identity edits. No build, operational adoption, commit, provider call or pipeline run is authorized by this review.

Only this review document is saved by this task.
