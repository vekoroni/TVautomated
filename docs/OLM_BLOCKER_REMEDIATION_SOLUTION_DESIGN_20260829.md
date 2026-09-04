# AVSHUNTER OLM Blocker Remediation — End-to-End Solution Design

**Document ID:** AVS-OLM-SD-002  
**Date:** 2026-08-29  
**Status:** Design complete; no production-code implementation performed by this document  
**Scope:** Long CALL and long PUT production path only  
**Primary findings addressed:** TC-07 execution-authority bypass and TC-08 repair-selector OI/volume hard gate  
**Reference evidence:** `audit/olm_test/OLM_VALIDATION_TEST_REPORT_20260829.md`

## 1. Executive decision

OLM must not be promoted until TC-07 and TC-08 are fixed and their exact reproductions pass. The core lifecycle calculations are retained. This remediation does not redesign OLM, make maturation scores authoritative, activate macro authority, reintroduce R:R authority, or expand production trading beyond governed long calls and long puts.

The design establishes these rules:

1. OLM may block, defer, or require repair. It never grants capital.
2. `execution_gate.py` remains the only positive `BUY_NOW` / `BUY_SMALL` capital authority.
3. An execution action can be granted only after the OLM constraint permits the row to continue and every existing execution check passes.
4. Open interest and volume remain ranking evidence. They cannot delete an otherwise valid repair candidate.
5. Bid/ask validity, spread, exact-contract identity, DTE, delta, strategy, current economics, direction integrity and thesis validity retain their existing authority.
6. The Intelligence Lab consumes the final Execution Gate action and must independently fail closed if an impossible OLM/action combination reaches it.
7. Promotion is direct to production after offline regression and acceptance testing; there is no permanent shadow-only deployment.

## 2. Objectives

### 2.1 Required outcomes

- A thesis marked `THESIS_INVALIDATED` can never result in `BUY_NOW` or `BUY_SMALL`.
- A move marked `MOVE_ALREADY_REALIZED` can never result in `BUY_NOW` or `BUY_SMALL`.
- A replacement contract requiring new economics routes to `CONTRACT_REPAIR`.
- Pullback, extension and pending-liquidity states remain visible but carry zero capital permission.
- Only an internally coherent `EXECUTABLE_NOW` or `GAP_CONFIRMATION_WITH_RUNWAY` lifecycle may continue into the existing execution checks.
- A valid, tightly quoted low-OI or zero-current-volume contract remains eligible for repair-candidate ranking.
- Zero-bid, invalid, stale where prohibited, excessively wide, wrong-direction, wrong-DTE or incomplete contracts remain non-executable under the existing rules.
- The currently passing formula, persistence, direction, contract-identity, Morning Gate and Lab functionality remains intact.

### 2.2 Non-goals

- Do not change OLM formulas or maturation-score thresholds.
- Do not convert maturation scores into probabilities.
- Do not allow OLM to issue GO, `BUY_NOW`, `BUY_SMALL`, or position size.
- Do not change macro/bond authority or EV/R:R policy.
- Do not add spreads, strangles or other structures to the production mandate.
- Do not change canonical MarketData acquisition, CDS write-through or Polygon prohibition.
- Do not remove the existing exact-contract repricing requirement.
- Do not refactor the two different DTE formulas in this change; record that as a separate design review.
- Do not require all technical OLM fields to be displayed in the Lab.

## 3. Current-state failure path

```text
Options Intelligence
    -> OLM lifecycle calculation is correct
    -> EOD handoff preserves lifecycle evidence
    -> Morning Gate calculates THESIS_INVALIDATED correctly
    -> execution_gate.py ignores OLM fields
    -> clean quote + upstream GO can become BUY_NOW        [TC-07]
    -> Lab trusts final_action and displays GO
```

Separately:

```text
Canonical option chain
    -> primary lifecycle permits low OI / zero volume
    -> select_repair_alternative_contracts()
    -> OI < 50 or volume < 1 causes continue               [TC-08]
    -> potentially usable neighbouring contract disappears
```

## 4. Target architecture

```text
CDS-authorised ticker worklist
    -> canonical MarketData chain
    -> long CALL/PUT selector
    -> OLM lifecycle evidence
    -> EOD candidate handoff
    -> Morning exact-contract refresh / replacement repricing
    -> Morning lifecycle transition
    -> shared OLM execution guard (veto/defer/repair only)
    -> existing Execution Gate checks (sole positive authority)
    -> final_action
    -> Lab defence-in-depth invariant
    -> governed opportunity book
    -> Intelligence Lab trader display
```

The shared OLM execution guard is a precondition used by the Execution Gate, Lab control and final handoff validator. It is not a second execution engine, and its `CONTINUE` disposition never means permission to trade.

## 5. Canonical authority model

### 5.1 Three separated authorities

| Concern | Owner | May grant capital? |
|---|---|---:|
| Thesis and lifecycle constraint | OLM/Morning transition | No |
| Contract quote/economics/direction and final action | Execution Gate | Yes |
| Presentation and impossible-state fail-close | Lab control | No |

### 5.2 Positive-authority invariant

For every row where `final_action in {BUY_NOW, BUY_SMALL}`, all of the following must be true:

- direction integrity passes;
- production structure is a governed long single CALL or PUT;
- `morning_transition_state in {EXECUTABLE_NOW, GAP_CONFIRMATION_WITH_RUNWAY}`;
- `thesis_state == ACTIVE`;
- `liquidity_state == EXECUTABLE_NOW`;
- `executable_now` is boolean true;
- exact selected contract identity is present;
- selected-contract economics are complete and correspond to that exact contract;
- quote, spread, delta and existing execution checks pass;
- Morning permission is eligible under the existing authority contract;
- maturation score has not been used as an authority.

Violation of any required predicate results in zero capital permission.

## 6. Lifecycle-to-action constraint

The constraint runs immediately after direction-integrity validation and before monetisability checks, live-quote retrieval, spread scoring or any positive-action derivation.

| Morning lifecycle transition | Constraint result | Execution Gate action | Monitoring state |
|---|---|---|---|
| `THESIS_INVALIDATED` | Terminal veto | `BLOCK` | Terminal |
| `MOVE_ALREADY_REALIZED` | Terminal no-chase veto | `BLOCK` | Terminal |
| `CONTRACT_REPRICE_REQUIRED` | Economics incomplete | `CONTRACT_REPAIR` | Active until repriced |
| `WAIT_FOR_PULLBACK` | Defer | `MANUAL_REVIEW` | Active |
| `GAP_CONFIRMATION_EXTENDED` | Defer/no chase | `MANUAL_REVIEW` | Active |
| `LIQUIDITY_STILL_PENDING` | Defer | `MANUAL_REVIEW` | Active |
| `EOD_PENDING_MORNING_REQUOTE` | Morning evidence absent | `MANUAL_REVIEW` | Active |
| `EXECUTABLE_NOW` | May continue | No action granted by OLM | Not required |
| `GAP_CONFIRMATION_WITH_RUNWAY` | May continue | No action granted by OLM | Not required |
| Missing/unknown on an OLM-required production row | Data-contract failure | `MANUAL_REVIEW` | Investigation required |
| Explicit archived legacy fixture | Compatibility policy | Existing legacy evaluation only | Not promoted as OLM evidence |

An allowed transition must also have `thesis_state=ACTIVE`, `liquidity_state=EXECUTABLE_NOW` and `executable_now=true`. A contradictory combination fails closed to `MANUAL_REVIEW` with an explicit integrity reason.

### 6.1 Applicability and legacy compatibility

Silent inference is prohibited.

- `execution_gate(row)` keeps a compatibility mode for direct archived/unit fixtures that carry no lifecycle fields.
- `run_execution_gate(...)`, the production batch entry point, requires OLM for every governed morning options row.
- Presence of any OLM field makes the row OLM-applicable; missing companion fields then fail closed.
- `LEGACY_LIFECYCLE_NOT_EVALUATED` is readable for replay but is not sufficient for new production capital permission.
- Production enforcement is an explicit function argument or run contract, not an environment-variable default that can drift silently.

This preserves historical evidence while preventing a stripped lifecycle payload from bypassing production controls.

## 7. TC-07 component changes

### 7.1 Shared policy: `contracts/options_liquidity_execution_guard.py`

Create one side-effect-free policy module exposing a typed decision such as:

```text
evaluate_olm_execution_guard(row, require_olm) ->
    disposition: CONTINUE | BLOCK | CONTRACT_REPAIR | MANUAL_REVIEW
    reason_code
    display_reason
    state_consistent
    execution_eligible
    guard_version
```

This is the only lifecycle-to-disposition mapping. Execution Gate and Lab control must consume it rather than maintain separate state lists.

Terminal evidence in `thesis_state` or `remaining_runway_state` takes precedence over a contradictory executable transition. `maturation_execution_authority=true` is an integrity failure; the score value itself is never read as evidence for permission.

### 7.2 `execution_gate.py`

Call the shared guard after direction validation and before the current monetisability and live-quote branches. Do not duplicate quote, spread, delta or monetisability calculations inside the guard.

Update `GATE_VERSION`. Preserve all existing actions and scoring for rows that receive `CONTINUE`.

Production `run_execution_gate()` must invoke the row function with OLM required and publish lifecycle/action counts in its summary. Include additive execution-output lineage fields `olm_guard_version`, `olm_guard_disposition`, `olm_guard_reason` and `olm_guard_pass`. No maturation score is consulted.

Recommended reason codes:

- `OLM_THESIS_INVALIDATED`
- `OLM_MOVE_ALREADY_REALIZED`
- `OLM_CONTRACT_REPRICE_REQUIRED`
- `OLM_WAIT_FOR_PULLBACK`
- `OLM_GAP_CONFIRMATION_EXTENDED`
- `OLM_LIQUIDITY_STILL_PENDING`
- `OLM_MORNING_REQUOTE_REQUIRED`
- `OLM_CONTRACT_INCOHERENT`
- `OLM_STATE_MISSING_OR_UNKNOWN`

### 7.3 `contracts/lab_control.py`

Generalise the present `CONTRACT_REPRICE_REQUIRED` override by consuming the shared lifecycle/action guard.

- The Lab does not recalculate OLM.
- It verifies that a received `BUY_NOW`/`BUY_SMALL` is compatible with the canonical lifecycle predicates.
- Terminal states become `BLOCKED`, zero size and non-tradeable.
- Repair states become `CONTRACT_REPAIR`, zero size and non-tradeable.
- Defer/pending states become `MANUAL_REVIEW`, zero size and non-tradeable.
- Allowed lifecycle states do not create tradeability; they only permit the already-governed `final_action` mapping.

This is defence in depth for malformed imports, stale exports and partial reruns. It must not create a second positive authority.

### 7.4 `morning_handoff_finalizer.py` invariant

Before the governed opportunity book is published, reconcile:

```text
actionable rows
= rows where final_action is BUY_NOW or BUY_SMALL
= rows where Lab is tradeable
= rows satisfying the positive-authority invariant
```

Any mismatch blocks publication of the affected rows, emits a concise reconciliation report and prevents Pipeline Interpreter synchronisation. Strict production publication retains the previous verified Lab book instead of publishing a partially contradictory replacement. Diagnostic output for the failed run is preserved.

## 8. TC-08 contract-repair selector changes

### 8.1 Required algorithm

In `select_repair_alternative_contracts()` remove only this deletion policy:

```text
OI below minimum OR volume below minimum -> discard
```

Retain the current hard requirements for:

- CALL/PUT direction;
- valid OCC/contract symbol;
- valid expiry and DTE window;
- minimum DTE buffer;
- signed delta and configured delta band;
- current bid/ask and calculable mark;
- non-crossed quote;
- required Greeks/IV used by the downstream candidate contract;
- configured spread maximum;
- moneyness and target-reach rules;
- exact-contract exclusion where appropriate.

OI and volume remain in:

- `liq_score`;
- deterministic tie-breaking;
- returned candidate evidence;
- human-readable candidate reason.

Missing OI or volume is normalised to zero as ranking evidence, not fabricated as activity. Candidate evidence must distinguish `REPORTED` from `MISSING_ASSUMED_ZERO` so a reported zero is not confused with absent vendor data.

Increment `EV3_CANDIDATE_POLICY_VERSION` from `ev3-long-single-candidates-v0.2.0` to `v0.3.0`. If the additive observation-status fields are serialized, increment `alternative_contracts_schema_version` from `ev3-contract-candidates-v3` to `v4`; existing readers must continue to ignore unknown JSON attributes.

### 8.2 Ranking invariants

- A tight, complete quote with OI=0 and volume=0 may be retained.
- Higher OI/volume may improve rank when stronger execution evidence is otherwise comparable.
- Higher OI/volume cannot rescue a zero bid, invalid quote or excessive spread.
- Contract geometry, DTE, delta and spread continue to dominate eligibility.
- Existing two-expiry/three-strike bounding and deterministic ordering remain unchanged.
- The change does not make verticals or exotic structures production-authorised; existing long-single Lab policy remains authoritative.

### 8.3 Observability

Add summary diagnostics without changing selection authority:

- retained candidates with OI below 50;
- retained candidates with zero current volume;
- rejected invalid/missing quote count;
- rejected spread count;
- rejected DTE/delta/geometry count;
- final bounded-candidate count.

These counts show whether the recovery mechanism is working without treating OI or volume as permission.

## 9. Intelligence Lab presentation

The Lab should remain concise. It does not need all 12 undisplayed technical fields.

Required trader-facing information:

- `Morning Transition`;
- thesis/lifecycle status;
- exact selected contract and whether it changed;
- current quote timestamp/freshness and canonical lineage;
- executable/pending/repair/terminal status;
- existing `morning_unlock_condition` or `execution_lock_reason` in plain language;
- a fixed disclosure beside maturation scores: **“Monitoring estimate only — not a probability and does not authorize entry.”**

Reuse existing governed reason fields rather than adding another verdict. Raw technical fields remain available in the governed book for audit.

The Enter Trade control is enabled only from the final Execution Gate baton and the lifecycle/action coherence guard.

## 10. Schema and data-contract policy

The remediation is additive and should avoid another schema expansion unless an audit field is essential.

- Preserve existing field names and order.
- Reuse `morning_transition_state`, `thesis_state`, `liquidity_state`, `executable_now`, `gate_reason`, `execution_lock_reason`, `morning_unlock_condition`, `maturation_score_is_probability` and `maturation_execution_authority`.
- Preserve the exact contract and quote lineage fields.
- Do not rename the 32 OLM fields already in the governed book.
- Guard lineage may be added to execution output and the governed audit record, but need not occupy primary trader UI space.
- Add run-summary diagnostics; no new database table or migration is required.
- Append-only CDS lifecycle evidence remains unchanged.

## 11. Regression-protection strategy

### 11.1 Frozen functional baselines

Before code changes:

1. Record the current passing test list and results.
2. Preserve representative CALL and PUT fixtures for each lifecycle state.
3. Freeze a recent saved Morning payload for deterministic before/after replay.
4. Record the current alternative-candidate ordering for normal OI/volume contracts.

After changes, differences are allowed only for:

- rows whose OLM state should veto, defer or repair execution;
- low-OI/zero-volume repair candidates newly retained;
- gate version, governed reason and new summary telemetry;
- the trader-facing non-authority explanation.

All other business fields and decisions must remain identical after volatile timestamps are excluded.

### 11.2 Required unit tests — execution authority

- `THESIS_INVALIDATED` + perfect quote + GO -> `BLOCK`.
- `MOVE_ALREADY_REALIZED` + perfect quote + GO -> `BLOCK`.
- `CONTRACT_REPRICE_REQUIRED` + otherwise complete row -> `CONTRACT_REPAIR`.
- Each wait/pending state -> `MANUAL_REVIEW` and zero capital.
- `EXECUTABLE_NOW` coherent row can still reach the existing `BUY_NOW` result.
- `GAP_CONFIRMATION_WITH_RUNWAY` coherent row can continue but does not itself grant capital.
- Allowed transition with `executable_now=false` -> no capital.
- Allowed transition with non-active thesis or non-executable liquidity -> no capital.
- Unknown/missing state in production-required mode -> no capital.
- Direct explicit legacy fixture preserves the intended replay behavior.
- A high maturation score never converts a blocked/pending row to an actionable result.
- Mirror all critical tests for CALL and PUT.

### 11.3 Required unit tests — repair selector

- OI=0, volume=0, tight complete CALL quote is retained.
- OI=0, volume=0, tight complete PUT quote is retained.
- Low OI with a zero bid is rejected by quote/spread governance, not by OI.
- Low OI with excessive spread is rejected by spread governance.
- High OI cannot rescue missing delta, Greeks, timestamp or invalid bid/ask.
- Normal high-OI fixture ordering is unchanged.
- Comparable candidates use OI/volume as deterministic ranking evidence.
- Two-expiry/three-strike cap remains unchanged.
- Long CALL and PUT alternatives remain correctly signed and thesis aligned.
- Vertical research tests continue to pass, while production Lab policy remains long-single only.

### 11.4 Cross-stage integration tests

- Morning Gate `THESIS_INVALIDATED` -> Execution Gate `BLOCK` -> Lab `BLOCKED` and non-tradeable.
- Morning Gate `MOVE_ALREADY_REALIZED` -> Execution Gate `BLOCK` -> Lab `BLOCKED`.
- Morning Gate pending liquidity -> Execution Gate `MANUAL_REVIEW` -> Lab non-tradeable and monitoring-visible.
- Replacement OCC symbol without recomputed economics -> repair through all stages.
- Fully repriced replacement with coherent lifecycle -> existing gates decide normally.
- A deliberately malformed `BUY_NOW + THESIS_INVALIDATED` import is caught by Lab defence in depth.
- Final opportunity book retains exact contract and quote lineage.
- Pipeline Interpreter handoff contains no actionable lifecycle contradiction.

### 11.5 Existing suites that must remain green

- lifecycle formula/classification suites;
- Morning/CDS append-only persistence suite;
- EOD lifecycle handoff suite;
- direction-governance suite;
- selected-contract economics and identity suites;
- execution monetisability suite;
- Lab monetisation and governed-handoff suites;
- Morning handoff finalizer suite;
- Options Intelligence/EV3 handoff suite;
- Intelligence Lab compact projection and UI label suite.

## 12. Production acceptance criteria

### 12.1 Offline acceptance

- TC-07 exact reproduction changes from `BUY_NOW` to `BLOCK`.
- TC-08 exact reproduction retains the low-OI/zero-volume contract.
- All previously passing OLM tests remain passing.
- All targeted execution, selector, direction, economics, handoff and Lab suites pass.
- Differential replay contains only approved changes.
- Syntax/import checks pass for every changed production module.

### 12.2 Fresh evening run

- OLM lifecycle fields are populated, not legacy, for all governed option candidates.
- CDS worklist and stopped-ticker suppression reconcile.
- MarketData/CDS remains the only options-chain path; no Polygon options fallback occurs.
- Selector telemetry reports retained low-OI/zero-volume candidates where present.
- No incomplete quote is marked executable.
- EOD output remains research/preparation data and does not gain capital authority.

### 12.3 Following Morning Gate run

- Exact-contract refresh and quote lineage populate.
- Every actionable row satisfies the positive-authority invariant.
- Zero `BUY_NOW`/`BUY_SMALL` rows are terminal, pending, deferred, unknown or awaiting repricing.
- Zero Lab-tradeable rows contradict the final Execution Gate action.
- Replacement symbols are fully repriced or remain `CONTRACT_REPAIR`.
- Pending opportunities remain visible for later sessions.
- Lifecycle/action reconciliation count is exactly zero.

The EXECUTE rate is reported but is not a pass/fail target. Correctness is determined by false-authority prevention, retention of valid developing theses, and coherent state transitions.

## 13. Failure handling and rollback

Before implementation, create a timestamped backup containing only files to be changed.

Rollback triggers:

- any previously passing critical suite fails;
- actionable lifecycle contradiction is non-zero;
- exact-contract identity or repricing regression occurs;
- non-OLM rows change outside the approved compatibility policy;
- provider governance or CDS persistence changes unexpectedly;
- Lab displays an actionable row that the Execution Gate did not authorize.

Rollback procedure:

1. Stop before Pipeline Interpreter sync or publication.
2. Preserve the failed run and test artifacts for diagnosis.
3. Restore only the changed files from the timestamped backup.
4. Do not delete append-only CDS evidence; retain it under the failed run ID.
5. Re-run the last known-good targeted regression pack.

No database migration is introduced by this design, so rollback is code-only.

## 14. Two-agent implementation model

Use no more than two implementation agents. Their file ownership is deliberately separated.

### Agent 1 — authority and handoff safety

Owns:

- `execution_gate.py`;
- `contracts/lab_control.py`;
- `contracts/options_liquidity_execution_guard.py`;
- `morning_handoff_finalizer.py`;
- execution-authority and Lab coherence tests.

Delivers:

- pure OLM execution constraint;
- production-required applicability rule;
- lifecycle/action state matrix;
- Lab defence-in-depth;
- final-handoff/Interpreter-sync invariant;
- TC-07 reproduction and full authority regression pack.

### Agent 2 — contract repair and trader disclosure

Owns:

- `scripts/avshunter_options_intelligence.py`;
- repair-selector tests;
- `intelligence-lab/static/index.html` and its UI test only if the disclosure is implemented in this release.

Delivers:

- OI/volume ranking-only repair selector;
- selector telemetry;
- CALL/PUT and negative-liquidity tests;
- TC-08 reproduction;
- concise Lab non-authority disclosure.

The primary integrator creates no third code workstream. It reviews both diffs, runs the combined suites, performs deterministic replay and controls production acceptance.

## 15. Build and implementation sequence

### Phase 0 — baseline and backup

1. Confirm no pipeline process is running.
2. Capture git/worktree status without changing unrelated files.
3. Back up only the proposed production files.
4. Run and record the current passing targeted suites.
5. Save the exact TC-07 and TC-08 failing reproductions.

**Exit:** reproducible baseline, recoverable files and explicit allowed-difference list.

### Phase 1 — parallel implementation

**Agent 1:** implement the Execution Gate constraint, production applicability and Lab defence-in-depth.  
**Agent 2:** remove the repair-selector OI/volume hard gate, retain ranking evidence, add telemetry and update the concise UI disclosure.

Agents edit only their assigned files.

**Exit:** both blocker reproductions pass independently; syntax checks pass.

### Phase 2 — focused regression

1. Run TC-07/TC-08 exact reproductions.
2. Run complete authority-state matrix tests for CALL and PUT.
3. Run selector positive and negative cases.
4. Run Lab coherence and UI tests.
5. Run existing formula and persistence suites unchanged.

**Exit:** zero targeted failures and no weakening of hard quote/economics controls.

### Phase 3 — integration regression

1. Run Morning -> Execution Gate -> Lab end-to-end fixtures.
2. Run exact-contract replacement and repricing tests.
3. Run direction, monetisability, handoff and finalizer suites.
4. Run deterministic before/after replay and inspect every changed row.
5. Run the broader repository regression pack appropriate to the changed modules.

**Exit:** only approved behavioral deltas; no unrelated regression.

### Phase 4 — production deployment

1. Promote the tested code directly; do not leave a parallel shadow authority.
2. Run `python intelligent_orchestrator.py --evening` at the scheduled time.
3. Validate evening acceptance criteria and preserve the run ID.
4. Run the normal Morning Gate against that governed evening run.
5. Validate lifecycle/action reconciliation and Lab display before treating any signal as executable.

**Exit:** one OLM-active evening/morning production cycle with zero authority contradictions.

### Phase 5 — acceptance record

1. Publish before/after counts by lifecycle transition and final action.
2. Record TC-07/TC-08 evidence, regression results, run IDs and schema fingerprints.
3. Record any pending opportunities retained for subsequent sessions.
4. Mark the two blockers closed only after production evidence passes.

**Exit:** auditable production acceptance and rollback reference.

## 16. Final recommendation

Proceed with the two-agent build only in the sequence above. TC-07 must be fixed before production authority is accepted. TC-08 should be fixed in the same release because it restores the intended maturation recovery mechanism without weakening executable-quote controls. The remainder of the existing OLM implementation should be preserved rather than rebuilt.
