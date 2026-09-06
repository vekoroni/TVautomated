# AVS-SD-003 — Gap elimination for the legacy Evening path

**Issued:** 2026-09-04
**Supersedes nothing.** Extends AVS-SD-002 v1.0 + Rev 1.1 and AVS-AR-003. The accepted architecture is not re-opened.
**Evidence base:** `audit\pipeline_map\AVS-RCA-002\` — `A_run_validation.md`, `A_counts.csv`, `B_executed_path_review.md`, `B_flag_topology.csv`, `environment.json`.
**Implementation refinement:** `audit\pipeline_map\AVS-IMP-SD-003-001_CYCLE1_AND_ADAPTER_FIX_20260904.md` and `audit\preflight\AVS-PRE-001_20260904_075820\AVS-PRE-001_RESULT.md`, accepted with the controlling amendments in §C9.
**Run under remediation:** `20260904_004338`
**Build model:** maximum two active implementers — one integration lead and one bounded specialist. File ownership and independent boundary verification are mandatory (§C9.8).

Every gap below is `CONFIRMED` in `A_counts.csv` with an artefact citation. Two §3 claims were `REFUTED` in Part A and are **excluded** from this design: `AVSHUNTER_COMPLETED_PROFILE_ENABLED` as a flag (A1-07) and undisclosed monetisability (A4-02).

---

## 1. Executive decision

**The build is sound. It was never switched on. Switch on the protections, keep the capabilities flagged, and change the closure standard so this cannot recur.**

Run `20260904_004338` reproduced the pre-build behaviour exactly: 1,551 fabricated Market Profiles, 1,068 daily-only `ALIGNED`, 1,551 POC values published as `0.0` — the same as `20260902_232526` scaled to a larger population (A0). The fixes exist and are correct. `_governed_profile_verdict` and `_not_evaluated` (`auction_synthesizer.py:147-227`) do exactly what P0-02 requires. They are unreachable in production because five independent `False` defaults stand between them and the executed path (A1-08).

Three decisions follow.

**D1 — Protections are unflagged; capabilities stay flagged.** A fail-closed protection whose default is "unprotected" is not a protection. AVS-SD-002 §21 already ordered this — *"the first production change must be the Vanguard fail-open protection"* — and the build inverted it by making the protection conditional on the acquisition stage. Restore the order. (§C2)

**D2 — Fail closed on authority, not on existence.** When profile evidence is unusable, Vanguard emits `NOT_EVALUATED`, `ready_to_trade=False`, null levels and **zero** score contribution — but does not delete the row. Hard-dropping would empty the book on the first night, which is not a safety improvement, it is an outage. The row survives as research with an explicit absence state and no profile-derived authority. (§C2.4)

**D3 — Nothing is done until run N+1 shows it firing.** The recertification closed seven P0s on 1,141 passing tests and not one row of production output. Every gate in §C4 is expressed as a count over a run artefact. (§C8)

**Cost of not acting.** 68.0% of the delivered 256-row book (174 rows: 118 CALL / 56 PUT) carries a +25 Layer-2 score contribution derived from a profile whose POC is `0.0` (A1-14). Forty-three Options rows were `ARMED` with no invalidation geometry; 15 reached the Lab as `EXECUTABLE_SUBJECT_TO_GATES` (A2-02). The only thing that stopped the PUT side doing the same was an unhandled `TypeError`.

---

## 2. Goals and non-goals

### Goals

1. Tomorrow's Evening run fails closed on unusable Market Profiles — no `ALIGNED`, no readiness, no uplift, no zero-as-price.
2. No directional row is armed, promoted or granted capital permission without an invalidation price, in any direction.
3. No unhandled exception in economics, in any direction; every stood-down row carries a governed reason code.
4. Quote, viability and macro lineage survive to the Lab book or are explicitly named absent.
5. The audit layer detects gaps 1–4, and stops failing runs for correct behaviour.
6. Cache identity is stable enough that a same-session rerun performs zero physical option-chain requests.
7. Completed-session MarketData stock candles are requested using the provider's verified Eastern wall-clock semantics, classified for completeness, and never promoted as a usable Market Profile when the session is partial.

### Non-goals

- Re-opening the accepted architecture. `MarketProfileEvidence`, the governed direction record, `DataExceptionReason`, the promotion staging in `orchestrator\dynamic_release.py:218-237` and the four-agent model all stand.
- Enabling `AVSHUNTER_DYNAMIC_PLAN_ENABLED`, `_VALIDATION_`, `_LAB_DYNAMIC_VIEW_`, `_INTERPRETER_DYNAMIC_RESOLVER_`, `_DECISION_LEDGER_` or `_AUTO_`. Those remain on the AVS-SD-002 Rev 1.1 promotion path unchanged.
- Correcting the AR-003 §5.1 stage-ordering defects (Horizon after Options, GARCH patched retroactively). Real, documented, and out of scope — they did not cause any gap here.
- Any change to Discovery's selection logic, the actuarial layer, EV3 or GARCH.
- Building the current-session (RTH developing) profile. AVS-SD-002 §21 forbids it until the MarketData entitlement preflight proves delivered session and delay.

---

## 3. Current-state evidence

Condensed from Part A. Every row is `CONFIRMED` with a filter in `A_counts.csv`.

| Property | Value | Three-direction split | Source |
|---|---|---|---|
| Vanguard rows | 1,551 | 793 C / 482 P / 276 O | A1-02 |
| `profile_type = INSUFFICIENT_DATA` | 1,551 (100%) | 793 / 482 / 276 | A1-02 |
| POC, VAH, VAL `== 0.0` (isna = 0) | 1,551 each | 793 / 482 / 276 | A1-03 |
| `INSUFFICIENT_DATA` **and** `ALIGNED` | 1,068 | 547 / 319 / 202 | A1-05 |
| `ready_to_trade = True` | 1,068 | 547 / 319 / 202 | A1-05 |
| `layer1__profile__timeframe = intraday` | 1,551 (proves legacy branch ran) | — | A1-09 |
| Rows receiving the Layer-2 `+25` | 1,068 | 547 / 319 / 202 | A1-13 |
| Lab rows sourced from an `ALIGNED` ticker | **174 of 256 (68.0%)** | 118 / 56 / 0 | A1-14 |
| Directional rows, `invalidation_state = MISSING` | 173 | 137 / 36 / 0 | A2-01 |
| **`ARMED` with `invalidation_state = MISSING`** | **43** | **43 / 0 / 0** | A2-02 |
| Lab rows, blank `invalidation_price` | 24 | 24 / 0 / 0 | A2-03 |
| …of which `capital_permission = EOD_CANDIDATE_ONLY` | 13 | 13 / 0 / 0 | A2-04 |
| Unhandled `TypeError` in economics | 36 | 0 / 36 / 0 | A2-05 |
| Blank `structural_target` | 244 | 12 / 42 / 190 | A2-07 |
| `contract_bid_size` / `_ask_size` Options → Lab | 241 → **0** | — | A3-01 |
| `execution_viability_state` Morning → Lab | 256 → **0** | — | A3-03 |
| `macro_*` Lab columns at 0/256 | **19 of 24** | — | A7-06 |
| `monetisability_authority` non-null | **0 / 256** | 0 / 0 / 0 | A4-03 |
| Option-chain physical requests | 1,264 (ledger reconciles exactly) | — | A5-01 |
| Option-chain cache hits | 0 — **correct**, no same-session dataset existed | — | A5-03 |
| `expires_at` NULL in `dataset_registry` | 11,248 / 11,248 (100%) | — | A5-04 |
| Handoff audit `fail_count` | 2 — **both spurious** (empty shadow book) | — | A6-01 |
| Audit rules detecting any of the above | **0** | — | A6-03 |

**Protected regression baseline** (A7): discovery reconciles 3,320 = 1,601 + 1,719; Options direction 792/472/141/49; Lab 164 CALL / 92 PUT; hold periods 194 `1_5d` / 62 `6_10d`; 256 in → 256 out, zero duplicate trade IDs; `morning_execution_permission` withheld 256/256; **`governed_direction_record_sha256` matches Options↔Lab on 256/256 rows**; all 190 STRANGLE/UNRESOLVED rows `STAND_DOWN` with `invalidation_state = NOT_APPLICABLE` and zero in the Lab.

---

## C1. Gap register

Severity: **P0** blocks the next Evening run from being trustworthy; **P1** material correctness or operational risk; **P2** disclosure or maintainability.

| ID | Gap | Root cause (file:line) | Class (Part A) | Design ref violated | Sev | Closes in one cycle? |
|---|---|---|---|---|---|---|
| **G-01** | Completed-profile acquisition stage did not execute | `intelligent_orchestrator.py:2417` gated by `:440-442` (`AVSHUNTER_DYNAMIC_THESIS_ENABLED`, read at import in a class body) | `FLAG_OFF` | AVS-SD-002 §21; AR-003 Wave 3 | P0 | No — needs the stage live (§C6 W2) |
| **G-02** | Vanguard fail-open still live: 1,068 daily-only `ALIGNED`, `ready_to_trade=True` | `auction_synthesizer.py:59` + five `False` defaults: `run_vanguard_from_packages.py:761`, `orchestrator_adapter.py:180`, `input_schema.py:211`, `auction_synthesizer.py:59`, producer only at `build_completed_market_profiles.py:159`/`:166` | `NEW_CODE_DEFECT` (structural) | AR-003 line 673, Wave 3 exit gate; SD-002 §21 | **P0** | **Yes — this is item 1** |
| **G-02b** | Missing POC/VAH/VAL published as the number `0.0` | `auction_synthesizer.py` legacy branch `:66-97` via `MarketProfileCalculator`; contrast `:208` which correctly emits `None` | `LEGACY_UNTOUCHED` | AR-003 §6.3 *"never a fabricated zero"*; Wave 3 *"no missing-as-zero"* | **P0** | **Yes** |
| **G-02c** | Layer-2 grants +25 for `ALIGNED` with no profile-usability guard | `vanguard/layer2_statistical/edge_detector.py:552-554` | `LEGACY_UNTOUCHED` | AR-003 §6.3 *"never a neutral score that looks observed"* | **P0** | **Yes** |
| **G-03** | 173 directional rows with `invalidation_state = MISSING`; **43 of them `ARMED`**; 15 reach the Lab as `EXECUTABLE_SUBJECT_TO_GATES` | No invalidation-presence precondition on arming anywhere in `scripts\avshunter_options_intelligence.py`; the P0-07 explicit defer sits behind `AVSHUNTER_DYNAMIC_VALIDATION_ENABLED` | `LEGACY_UNTOUCHED` + `FLAG_OFF` | AR-003 P0-07; Rev 1.1 §19.11 | **P0** | **Yes** |
| **G-04** | 24 Lab rows without invalidation carry a candidate status; 13 carry `capital_permission = EOD_CANDIDATE_ONLY` and `eod_candidate_authorized = True` | `eod_candidate_engine.py` — no `EOD_*` status assignment or capital-permission grant tests invalidation presence | `LEGACY_UNTOUCHED` | AR-003 P0-07; Rev 1.1 §19.11 | **P0** | **Yes** |
| **G-05** | Unguarded `target` subtraction kills 36 PUT rows; the CALL branch carries the identical exposure | `scripts\avshunter_options_intelligence.py:5464` (CALL) and `:5467` (PUT); `target` from `:5435`, `None` via the ladder at `:4138-4158` when `stop_dist` is `None` (`:4041`, `:4045`, `:4048`) | `LEGACY_UNTOUCHED` | AR-003 §6.3 `UNRESOLVED_EXCEPTION`; P0-04 | **P0** | **Yes** |
| **G-06** | Quote lineage lost before the Lab — three distinct shapes | (a) allow-list omission Options→Morning; (b) rename with no mapping at `contracts\lab_control.py:2065` + orphaned value at `eod_candidate_engine.py:879`; (c) **allow-listed but unmapped**: `execution_viability_*` declared at `lab_control.py:256-265` with no `first(sig,…)` assignment | (a),(b) `LEGACY_UNTOUCHED`; (c) `NEW_CODE_DEFECT` | AR-003 P1-03/P1-04; Rev 1.1 §19.14 | **P1** | **Yes** |
| **G-07** | `monetisability_authority` null on 256/256 rows, including all 110 `MONETISABLE` | `contracts\selected_contract_economics.py` — the advisory-authority stamp is never written; `monetisability_calculation_version` also NaN on the 22 `DATA_MISSING` rows | `NEW_CODE_DEFECT` | AR-003 §7.10 (evaluation is advisory) | P2 | **Yes** |
| **G-08** | Cache identity not stable enough to guarantee warm reuse; no TTL | `scope_fingerprint` constant per run and different across runs of the same session (`9a6428e8…`, `ce80bb29…`, `f6680964…` all for 2026-08-28); `expires_at` NULL on 11,248/11,248 registry rows | `NEW_CODE_DEFECT` | Rev 1.1 §19.15; AR-003 §6.3 `REUSED_CANONICAL` | P1 | Partly — gate is `AWAITING_RUN` |
| **G-09** | Handoff audit scores a correctly-empty artefact as `FAIL` | `handoff_contract_audit.py:479` — the `PRESENT_BUT_EMPTY` branch is guarded by `row_count > 0`, so a 0-row frame falls through to `LOW_FILL_RATE` at `:482-483` (severity `FAIL`). Inverted severity: a *missing* shadow book is `WARN` at `:455` | `AUDIT_DEFECT` | AR-003 §6.3 (`DEFERRED_NOT_YET_OBSERVABLE` vs missing) | P1 | **Yes** |
| **G-10** | 36 stood-down rows publish a raw CPython message into trader-facing `stand_down_reason` and `trigger_status_reason` | `scripts\avshunter_options_intelligence.py` exception handler — swallowed exception with a default status; no `UNRESOLVED_EXCEPTION` state | `LEGACY_UNTOUCHED` | AR-003 §6.3 state 6 | P1 | **Yes** |
| **G-11** | **19 of 24 `macro_*` Lab columns are 0/256**, including `macro_plain_language_advisory` and every macro lineage identity field (`macro_packet_id`, `macro_packet_sha256`, `macro_source_fingerprint`, `macro_as_of_utc`, `macro_session_date`) | Columns declared in the Lab schema with no producer at Options or Morning (`ABSENT`, not blank) | `NEW_CODE_DEFECT` | Rev 1.1 §19.10; AR-003 P1-03 | P1 | **Yes** |
| **G-12** | **The audit layer contains no rule that detects G-01…G-06.** Correcting G-09 alone would turn this run green | `handoff_contract_audit.py` `FIELD_CONTRACTS` + `_semantic_contract_audit`; `uat_audit_report.py` | `AUDIT_DEFECT` | AR-003 §12 product acceptance gates | **P0** | **Yes** |
| **G-13** | Unledgered provider paths and silent stale-bar substitution: all 2,528 ledger rows are `stage=OPTIONS`; Discovery calls Polygon directly; **39 tickers (1.2%) silently used stale cached bars** | `avshunter_discovery_ULTIMATE.py` direct Polygon path; no row-level fallback state | `LEGACY_UNTOUCHED` | AR-003 §6.2, §6.3 (`APPROVED_FALLBACK`) | P1 | Partly — ledger coverage is a cycle-2 item |
| **G-14** | `AVS-SD-002_PHASE4_CLOSURE_20260903.md` "Rollout control" names `AVSHUNTER_COMPLETED_PROFILE_ENABLED`, **which does not exist**. This is the origin of the operator's and the prompt's flag confusion | closure document; contrast `tests\test_dynamic_session_phase6.py:178` which *asserts the string is absent from the source* | documentation | AVS-SD-002 §17.1 (lead owns promotion) | P2 | **Yes** |

**Withdrawn after Part A.** The prompt's provisional *"G-07 monetisability non-evaluation undisclosed"* is **REFUTED** (A4-02): the seven rows carry `monetisability_status=FAILED`, `state=DATA_MISSING`, `reason=EOD_ASK_STRIKE_OR_TARGET_MISSING`, `eligible=False`, and the real population is 22, not 7. G-07 above is the narrower, genuine residue. The prompt's *"G-08 zero cache reuse"* as a defect is **REFUTED** (A5-03, `EXPECTED_COLD`); G-08 above is the identity-stability gap that remains.

---

## C2. Flag policy — the first design decision

### C2.1 Recommendation: **Option 1, preceded by the minimal part of Option 3**

Adopt **Option 1 — unflag the protections** — with one structural correction borrowed from Option 3.

**Reject Option 2** (`AVSHUNTER_DYNAMIC_THESIS_ENABLED` + `AVSHUNTER_COMPLETED_PROFILE_ENABLED`, protections behind them) on two grounds. First, **it is unbuildable as written**: `AVSHUNTER_COMPLETED_PROFILE_ENABLED` does not exist (A1-07); the Phase 4 closure that named it was wrong and `tests\test_dynamic_session_phase6.py:178` actively asserts its absence from the source. Second, and decisively, it keeps a fail-closed protection behind a flag, which is the defect. It would also make tomorrow's run depend on a stage that runs `critical=True` (`intelligent_orchestrator.py:2427`) — a stage failure would abort the entire Evening run, converting a data-quality problem into an outage.

**Reject full Option 3** as the primary answer because splitting `AVSHUNTER_DYNAMIC_THESIS_ENABLED` is *necessary but not sufficient*: after the split the protection would still be flagged, just by a smaller flag. Take the split, then apply Option 1 to what remains.

### C2.2 What that means concretely

| Behaviour | Today | Under this design |
|---|---|---|
| Vanguard fail-closed on unusable profile (`NOT_EVALUATED`, `ready_to_trade=False`, uplift 0, null levels) | behind `AVSHUNTER_DYNAMIC_THESIS_ENABLED` (transitively, via five `False` defaults) | **unconditional** |
| Missing-invalidation defer / arming block | absent on `--evening`; recertified version behind `AVSHUNTER_DYNAMIC_VALIDATION_ENABLED` | **unconditional** |
| PUT **and** CALL null-target guard → `UNRESOLVED_EXCEPTION` | absent | **unconditional** |
| Lineage allow-list (quote, viability, macro) | partially wired | **unconditional** |
| Monetisability authority stamp | absent | **unconditional** |
| Audit rules for the above | absent | **unconditional** |
| Completed-profile **acquisition** stage | `AVSHUNTER_DYNAMIC_THESIS_ENABLED` | **`AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED`** (new, default off) |
| Dynamic thesis-builder rewrite, plan engine, validation, dispatcher, ledger, dynamic views | flagged | **flagged, unchanged** |

**The Option-3 split, precisely.** Introduce one new flag, `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED`, added to `FEATURE_FLAG_ENV_VARS` and to `dynamic_session_authority_v1.json` as a ninth member, default `False`. `intelligent_orchestrator.py:440-442` reads *that* variable instead of `AVSHUNTER_DYNAMIC_THESIS_ENABLED`, and is moved out of the class body into a function so it is no longer frozen at import (A1.2a). `AVSHUNTER_DYNAMIC_THESIS_ENABLED` retains only its `BUILD_THESIS` meaning at `:6392-6393` and `:6399`. This separates *profile acquisition* (a data capability, safe to promote early) from *the thesis-builder rewrite* (a control-flow change, promote later), which is what the two things always were.

**The Option-1 unflagging, precisely.** `market_profile_contract_required` stops being an opt-in and becomes an always-true assertion of the governed contract. All five `False` defaults (`run_vanguard_from_packages.py:761`, `orchestrator_adapter.py:180`, `input_schema.py:211`, `auction_synthesizer.py:59`, and the producer's absence) are removed. Vanguard **always** takes `_governed_profile_verdict`. When no profile evidence exists — which is the state on the first night, with the acquisition flag still off — the evidence is `None`, `MarketProfileEvidence.from_mapping({})` yields `usable = False`, and `_not_evaluated` fires (`auction_synthesizer.py:154-157`). The legacy fabrication branch at `:66-144` becomes unreachable and is deleted in cycle 2 (§C6 W2-4), not cycle 1 — deleting it and changing the default in the same change would leave no rollback path.

### C2.3 AVS-SD-002 §21 — honoured, not overruled

> §21, line 854: *"The first production change must be the Vanguard fail-open protection."*

This design makes it literally the first item in the implementation sequence (§C6 W1-1). No ACK sign-off for an overrule is required, because there is no overrule. What the build did was invert the order; this restores it.

### C2.4 Consequence for tomorrow's run — stated precisely

With `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED=0` (recommended for the first remediated run) and the protections unconditional:

**Vanguard emits, for all 1,551 rows and in all three directions:**

| Field | Value | Mechanism |
|---|---|---|
| `layer1__auction_state` | `NOT_EVALUATED` (1,551) | `auction_synthesizer.py:206` |
| `layer1__ready_to_trade` | `False` (1,551) | `:204` |
| `layer1__profile__profile_type` | `INSUFFICIENT_DATA` (1,551) | `:209` |
| `layer1__profile__poc` / `value_area_high` / `value_area_low` | **`None`, not `0.0`** (1,551) | `:208` |
| `layer1__profile__timeframe` | `GOVERNED` (1,551) | `:211` |
| Layer-2 alignment uplift | **`0` on every row** (was +25 on 1,068) | no row is `ALIGNED` |
| `auction_state = ALIGNED` | **0** (was 1,068) | — |

**What happens to the 256-row Lab book — and the honest limit of this prediction.**

Nothing is hard-dropped. I verified the three places that could drop a row and none of them does:

- `scripts\run_vanguard_from_packages.py` rejects only on missing OHLCV or `regime_snapshot` (`:1399-1403`, `:1451-1456`) — never on `ready_to_trade` or `auction_state`. In this run 483 rows already had `ready_to_trade=False` and all 483 flowed on to Options.
- `edge_detector.py:207-211` GATE 1 drops only `CONFLICTED`. `NOT_EVALUATED` is not `CONFLICTED`.
- `trigger_layer.py:512-519` uses `auction_state == "TRANSITIONING"` inside an `or`; `NOT_EVALUATED` simply contributes nothing.

So the population survives Vanguard and reaches the EOD Candidate Engine intact. The 174 Lab rows sourced from `ALIGNED` tickers lose 25 points of `right_side_score`; the 82 from `TRANSITIONING` lose 15. Because the uplift is removed nearly uniformly, relative order is largely preserved.

**The book size, however, is not protected by a cap.** `max_candidates` defaults to `0` — *"0 means no cap"* (`eod_candidate_engine.py:1889`, `:3027`) — so the 256 rows are the *output of the candidate filter*, not a ceiling it happened to reach. If any part of that filter is threshold-based on a score that includes the alignment uplift, the count moves. I cannot determine the resulting number without executing the pipeline.

**This is a prediction from code reading, not a measurement, and the design treats it as such.** Both the surviving population and the book size depend on threshold and ranking interactions I cannot evaluate without executing the pipeline, which is forbidden. **AG-18 therefore reports book size and composition; it does not assert them**, and §C7 makes a fall below 128 rows an escalation trigger rather than an automatic rollback. If the book does shrink materially, that is *information*, not a regression: it would mean the book was resting on the fabricated uplift, which is precisely the thing under investigation. The first remediated run is partly a measurement exercise, and saying so is more useful than asserting a number I cannot derive.

**With `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED=1` (the second run, §C7):** tickers with usable completed-session evidence get `PROFILE_CONTEXT_ONLY` with real POC/VAH/VAL and `ready_to_trade=False` (`:186-199`); tickers without get `NOT_EVALUATED`. Zero rows can be `ALIGNED` on a fabricated profile in either case (A1-12).

---

## C3. Per-gap change specification

Three-direction behaviour is stated for every rule. `OTHER` = STRANGLE / UNRESOLVED / null.

### G-02 / G-02b / G-02c — Vanguard fail-closed, unconditional

**Modules.** `vanguard\layer1_auction\auction_synthesizer.py`, `vanguard\schemas\input_schema.py`, `vanguard\integration\orchestrator_adapter.py`, `scripts\run_vanguard_from_packages.py`, `vanguard\layer2_statistical\edge_detector.py`.

**Contract.** AR-003 line 673: *"No daily-only or unusable profile can yield `ALIGNED` or readiness."* AR-003 Wave 3 exit gate (line 595): *"No daily-only `ALIGNED`; no missing-as-zero."* AR-003 §6.3: a required field must never become *"a fabricated zero"* or *"a neutral score that looks observed."*

**Changes.**

1. `input_schema.py:211` — `market_profile_contract_required: bool = **True**`.
2. `orchestrator_adapter.py:180` and `run_vanguard_from_packages.py:761` — default `True`, and raise `VanguardInputError` if a package explicitly sets `False` (no silent opt-out).
3. `auction_synthesizer.py:59` — `getattr(..., "market_profile_contract_required", **True**)`.
4. `auction_synthesizer.py:66-144` (legacy branch) — leave in place for cycle 1, unreachable; **delete in cycle 2** (§C6 W2-4).
5. `edge_detector.py:552-554` — the uplift becomes evidence-conditional:
   ```
   if auction.auction_state == "ALIGNED" and auction.profile.poc is not None:   score += 25
   elif auction.auction_state == "TRANSITIONING" and auction.profile.poc is not None: score += 15
   elif auction.auction_state == "SEARCHING" and auction.profile.poc is not None:     score += 5
   # NOT_EVALUATED / PROFILE_CONTEXT_ONLY, or any null POC -> +0
   ```
   Belt and braces: even if a fabricated `ALIGNED` reappeared, a null POC would deny the uplift.

**Three-direction behaviour.** Identical for CALL, PUT and OTHER. Profile evidence is direction-agnostic; nothing in `_not_evaluated` or `_governed_profile_verdict` branches on direction, and nothing should.

**Failure mode replaced.** 1,068 rows scored as if a real auction had been observed → 0 rows.

**Tests.** §C5 T-02a…T-02e.

### G-01 — Completed-profile stage, split flag

**Modules.** `intelligent_orchestrator.py`, `contracts\dynamic_session_contract.py`, `contracts\dynamic_session_authority_v1.json`, `orchestrator\dynamic_release.py`.

**Changes.**

1. Add `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED` (default `False`) to `FEATURE_FLAG_ENV_VARS` (`dynamic_session_contract.py:144-153`), to `DynamicSessionFeatureFlags` as `completed_profile_stage`, and to `dynamic_session_authority_v1.json:17-24`.
2. `intelligent_orchestrator.py:440-442` — replace the class-body constant with a **function** `completed_profile_stage_enabled()` reading the new variable at call time, so it is togglable per invocation and visible to `DynamicSessionFeatureFlags` (removes the defect at A1.2a). Update the two call sites `:973` and `:2417`.
3. `intelligent_orchestrator.py:2427` — change `critical=True` to a **governed degradation**: on stage failure, log `PROFILE_STAGE_FAILED`, write a `profile_stage_status` marker into the run directory, and continue. Vanguard then sees no evidence and fails closed on its own — which is the correct outcome and no longer an outage (this is why D2 matters).
4. Add the flag to `_PROMOTION_FLAGS[PromotionStage.EXPLICIT_COMMANDS]` (`dynamic_release.py:220-226`).

**Three-direction behaviour.** Not applicable; the stage is per-ticker and direction-agnostic.

### G-03 / G-04 — Invalidation is a precondition for arming and for capital permission

**Modules.** `scripts\avshunter_options_intelligence.py` (arming), `eod_candidate_engine.py` (status and capital permission), `contracts\lab_control.py` (Lab permission).

**Contract.** AR-003 P0-07 — *"Frozen direction/horizon/entry/target/invalidation contract … explicit defer on missing decision-critical data."* Rev 1.1 §19.11 — *"direction/horizon/geometry remain frozen through validation."*

**Rule (single, three-direction, applied at three boundaries).**

| Direction | `invalidation_state` required | If absent |
|---|---|---|
| CALL | `AVAILABLE` | `options_verdict = STAND_DOWN`, `stand_down_reason_code = INVALIDATION_MISSING`; **never `ARMED`** |
| PUT | `AVAILABLE` | identical |
| OTHER (STRANGLE / UNRESOLVED / null) | `NOT_APPLICABLE` — arming is already denied by direction governance | unchanged; **this is the behaviour that already works (A7-10) and must not regress** |

At the EOD boundary: a row with no invalidation price may take a *research* status but must not take `capital_permission = EOD_CANDIDATE_ONLY`, `capital_authorization_state = EOD_CANDIDATE_ONLY`, or `eod_candidate_authorized = True`. It takes `capital_permission = NO`, `capital_authorization_state = NOT_AUTHORIZED`, and `eod_candidate_reason` gains `INVALIDATION_MISSING`.

At the Lab boundary: `options_research_permission` becomes `NOT_EXECUTABLE` with `research_route_reason = INVALIDATION_MISSING` — never `EXECUTABLE_SUBJECT_TO_GATES`.

**Failure modes replaced.** 43 `ARMED`-without-stop → 0. 13 `EOD_CANDIDATE_ONLY`-without-invalidation → 0. 23 Lab rows presenting as `EXECUTABLE_SUBJECT_TO_GATES` without a stop → 0.

**Tests.** §C5 T-03a…T-03d, T-04a…T-04b.

### G-05 / G-10 — Governed null-target guard, both directions

**Module.** `scripts\avshunter_options_intelligence.py`, `compute_trade_economics` at `:5428`.

**Contract.** AR-003 §6.3 state 6: `UNRESOLVED_EXCEPTION` — *"required evidence could not be obtained or calculated."*

**Change.** Guard **before** the direction branch at `:5462`, not inside it:

```python
target = ctx['structural_target']                                  # :5435
...
if target is None or not math.isfinite(target):                    # NEW, before :5463
    return _unresolved_exception_economics(
        reason_code="STRUCTURAL_TARGET_UNRESOLVED",
        detail=f"direction={direction} stop_state={ctx.get('stop_state')}",
    )
```

The returned record sets, on **CALL, PUT and OTHER identically**:

```
economics_state              = UNRESOLVED_EXCEPTION
economics_reason_code        = STRUCTURAL_TARGET_UNRESOLVED
options_verdict              = STAND_DOWN
stand_down_reason_code       = STRUCTURAL_TARGET_UNRESOLVED
stand_down_reason            = "Structural target unresolved; economics not computable"
invalidation_state           = MISSING | AVAILABLE | NOT_APPLICABLE   (unchanged, computed upstream)
```

**Explicitly required by the prompt and adopted:** a governed exception record, *not* a stand-down default. The distinction is that `economics_state` is a first-class enum value that gates and metrics can count, whereas today the only evidence is a stringified `TypeError` in a free-text field.

**Three-direction note — this is the point of the fix.** Today CALL (`:5464`) carries the identical unguarded subtraction and was saved only because its 12 exposed rows failed unrelated contract-quality gates first (A2-07). A guard placed inside the PUT branch would fix the symptom and leave the defect. The guard goes before the branch.

**Second change (root cause).** At `:4156-4158`, when the ladder cannot resolve a target, set `structural_target_state = UNRESOLVED` alongside `structural_target = None`, so the absence is a state rather than an inference from a null.

**Third change.** No raw exception text may reach `stand_down_reason` or `trigger_status_reason`. The handler stores the interpreter message in a diagnostics-only column (`internal_exception_detail`) and publishes only the governed reason code.

**Failure mode replaced.** 36 rows with `Unhandled exception: unsupported operand type(s) for -: 'float' and 'NoneType'` → 36 rows with `STRUCTURAL_TARGET_UNRESOLVED`, plus the 12 CALL rows now explicitly guarded instead of accidentally spared.

### G-06 — Quote lineage: the allow-listed field set at each boundary

Three shapes, three fixes. **Modules:** `scripts\avshunter_options_intelligence.py` (producer), `eod_candidate_engine.py` (projection), `contracts\lab_control.py` (mapper), `contracts\lab_evidence_overlay.py`, `contracts\interpreter_handoff_materializer.py`.

| Field (Lab canonical) | Producer (Options column) | Options→Morning | Morning→Lab | Boundary that fails today | Rename needed | Fix |
|---|---|---|---|---|---|---|
| `contract_bid_size` | `contract_bid_size` (241/256) | **not projected** | mapped `lab_control.py:2070` | Options→Morning | no | add to the EOD projection list |
| `contract_ask_size` | `contract_ask_size` (241/256) | **not projected** | mapped `:2070`-adjacent | Options→Morning | no | add to the EOD projection list |
| `contract_quote_quality` | `contract_quote_quality` (241/256) | **not projected** | mapped | Options→Morning | no | add to the EOD projection list |
| `selected_quote_timestamp_utc` | `contract_quote_timestamp_utc` \| `quote_timestamp_utc` \| `l2_quote_timestamp_utc` (241/256) | computed at `eod_candidate_engine.py:879` into a **dict that is never projected** | mapper accepts only `selected_quote_timestamp_utc` \| `contract_quote_timestamp` (`:2065`) | both | **yes** | project the computed key **and** widen the mapper alias list to the three producer names |
| `execution_viability_state` | — (produced by `contracts\long_option_policy.py:177-234` at the Morning boundary) | n/a | **allow-listed at `:257`, no `first(sig,…)` assignment** | Morning→Lab | no | add the assignment |
| `execution_viability_reason` \| `_eligible` \| `_reviewable` | as above (256/256) | n/a | allow-listed `:258-260`, unmapped | Morning→Lab | no | add assignments |
| `execution_viability_bid` \| `_ask` \| `_spread_pct` \| `_spread_denominator` \| `_policy_version` \| `_contract_symbol` | as above (234/256) | n/a | allow-listed `:256`,`:261-265`, unmapped | Morning→Lab | no | add assignments |
| `underlying_nbbo_bid_size` \| `_ask_size` | **no producer anywhere** | — | — | orphan column | **yes** | either map to `l2_bid_size`/`l2_ask_size` or remove the columns; do not ship a column no stage can fill |
| *(control — must not regress)* `quote_as_of` | `quote_as_of` (241) | 241 | 241 | — | — | regression assertion only |
| *(control)* `contract_bid` \| `contract_ask` | (241) | 241 | 241 | — | — | regression assertion only |
| *(control)* `selected_quote_dataset_id` | (211) | 211 | 211 | — | — | regression assertion only |

**Named-absence rule.** Where a field is genuinely unavailable (15 of 256 rows have no selected contract), the Lab must carry the existing `contract_data_state = NOT_APPLICABLE_NO_SELECTED_CONTRACT` (`lab_control.py:2060`) rather than a bare null, so the gate at §C4 AG-06 can distinguish *absent because unavailable* from *absent because dropped*.

**Three-direction behaviour.** Identical for CALL and PUT. For OTHER the fields are `NOT_APPLICABLE` — the 190 STRANGLE/UNRESOLVED rows never reach the Lab (A7-10) and this must not change.

**Structural fix, and the reason this recurred.** The Phase 5 closure fixed exactly this shape for `ms_*` (F29) and left it in place for three other field families (§B2). The generic defence is §C5 T-06d: a boundary test that walks the `lab_control.py` allow-list and **fails on any allow-listed field that is 0/N populated while its declared source is >0/N**. That test would have caught `execution_viability_*`, `contract_bid_size` and the `macro_*` family (G-11) in one assertion.

### G-11 — Macro lineage

**Modules.** `eod_candidate_engine.py` (projection), `contracts\lab_control.py` (mapper), `contracts\interpreter_handoff_materializer.py`.

Nineteen `macro_*` columns are declared in the Lab schema and produced by nobody (`ABSENT` in both the Options and Morning files, not merely blank). Two sub-classes, treated differently:

- **Lineage identity — must be populated.** `macro_packet_id`, `macro_packet_sha256`, `macro_source_fingerprint`, `macro_as_of_utc`, `macro_session_date`. All five are available in `macro_quant_packet.json` and `run_meta.json` (`msi_config_hash`, `contract_version`, `macro_source_path`). Without them a Lab row cannot be tied to the macro packet that advised it, which breaks Rev 1.1 §19.10.
- **Advisory content — populate or remove.** `macro_plain_language_advisory`, the seven `macro_*_context` fields, `macro_directional_pressure`, `macro_conflicts`, `macro_event_guards`, `macro_active_themes`, `macro_sector_alignment`, `macro_ticker_alignment`. Each is either wired to its producer or deleted from the schema. **A column that no stage can fill must not appear in a governed book** — it is indistinguishable from a dropped field, which is exactly how it presented in Part A.

**Preserve:** `macro_authority = MACRO_ADVISORY_ONLY` and `macro_data_role = ADVISORY_ONLY` on 256/256 are correct and are a regression assertion.

### G-07 — Monetisability authority stamp

**Module.** `contracts\selected_contract_economics.py`.

**Contract.** AR-003 §7.10 — the evaluation is advisory.

Write `monetisability_authority = "ADVISORY_SCENARIO_ONLY"` on **every** row in all three directions, including the 110 `MONETISABLE` and the 22 `DATA_MISSING`; and `monetisability_calculation_version` on every row including the `FAILED` ones, so a failed evaluation is still attributable to a version. Phase 2 closure already states the intended value: *"Scenario monetisability is explicitly `ADVISORY_SCENARIO_ONLY`"* — the string exists in the design and not in the data.

The seven `EOD_ASK_STRIKE_OR_TARGET_MISSING` rows are expected to fall to zero as a *side-effect* of G-05, since all seven are PUT rows whose `monetisability_structural_target_spot` is NaN for the same reason (A4-01). That is a consequence to observe, not a separate change.

### G-08 — Cache identity and the warm-rerun gate

**Modules.** `canonical_data\` option-chain resolver, dataset registry.

**Cache identity the resolver must match on:**

```
(instrument_id, dataset_type, session_date, normalised_scope_hash, adjustment_convention, schema_version)
```

where `normalised_scope_hash` is computed from a scope in which **relative quantities are resolved to absolute ones before hashing**: `dte_min`/`dte_max` become concrete expiry-date bounds. Today they are stored relative and hashed as-is, which is why session 2026-08-28 carries three different `scope_fingerprint` values across six runs (A5-04). `min_open_interest`, `sides` and `fields` are already absolute and stay.

**Superset rule.** A cached dataset whose expiry bounds *contain* the requested bounds resolves as `REUSED_CANONICAL` with zero physical calls (AR-003 §6.3 state 2), not as a miss.

**TTL.** `expires_at` is NULL on 11,248/11,248 rows. Set it at registration: for `OPTION_CHAIN`, expiry = the end of the session following `session_date`, so a completed session's chain never expires within that session and never silently serves a stale session.

**Expected counts on a same-session rerun:** physical `OPTION_CHAIN` requests = **0** for unchanged identities; ledger rows = 2 per request (one `no fresh canonical coverage`→`exact fresh dataset` resolution, one skipped fetch); `sum(physical_request_count) = 0`.

**Ledger reconciliation.** `physical = ledger PROVIDER_FETCH rows`. **Scoped to `dataset_type = OPTION_CHAIN`** in cycle 1, because Options is the only stage commuted through the gateway — all 2,528 ledger rows for this run are `stage = OPTIONS` (B4-02). Widening the reconciliation to the whole run requires G-13 first. Stating it run-wide today would make it unverifiable, not stricter.

**This gate is `AWAITING_RUN`** — see §C4.2.

### G-09 / G-12 — The audit layer

**Modules.** `handoff_contract_audit.py`, `uat_audit_report.py`.

**G-09 — `EMPTY_BY_DESIGN`.** Replace `handoff_contract_audit.py:477-484` with:

```python
if not present:                                        status = "MISSING_COLUMN"
elif row_count == 0:                                                        # NEW
    status = ("EMPTY_BY_DESIGN" if stage in EMPTY_PERMITTED_STAGES
              else "EMPTY_UNEXPECTED")
elif filled == 0:                                      status = "PRESENT_BUT_EMPTY"
elif rate < 0.05 and contract["severity"] == "FAIL":   status = "LOW_FILL_RATE"
else:                                                  status = "OK"
```

with `EMPTY_PERMITTED_STAGES = {"shadow_book"}`. `EMPTY_BY_DESIGN` carries severity `INFO` and is excluded from `fail_count`/`warn_count`. Also correct the inverted severity at `:455`: a *missing* `shadow_book` artefact is `WARN` today while a present-and-empty one is `FAIL`; both should be `WARN`/`INFO` respectively.

**G-09 corroboration rule.** `EMPTY_BY_DESIGN` is only granted when the emptiness is *explained*: the audit reads `eod_dropoff_audit_{run_id}.csv` and confirms that no row satisfies the shadow mask (`shadow_opportunity_score >= 40` and status not in `EOD_CARRY_FORWARD_STATUSES`). If rows do satisfy it and the book is still empty, the status is `EMPTY_UNEXPECTED` at severity `FAIL`. This preserves the audit's real purpose. For this run the check passes: all 81 rows scoring ≥ 40 carry a carry-forward status (A6-02).

**G-12 — the rules that were missing.** Add to `_semantic_contract_audit` (this is the P0 half; G-09 alone would turn a defective run green — A6-03):

| Rule | Assertion | Severity |
|---|---|---|
| `PROFILE_FAIL_OPEN` | count(`profile_type=INSUFFICIENT_DATA` **and** `auction_state=ALIGNED`) == 0 | FAIL |
| `PROFILE_ZERO_AS_PRICE` | count(`poc == 0.0` or `value_area_high == 0.0` or `value_area_low == 0.0`) == 0 | FAIL |
| `READY_WITHOUT_PROFILE` | count(`ready_to_trade=True` **and** `poc is null`) == 0 | FAIL |
| `ARMED_WITHOUT_INVALIDATION` | count(`options_verdict=ARMED` **and** `invalidation_state=MISSING`) == 0 | FAIL |
| `CAPITAL_WITHOUT_INVALIDATION` | count(`capital_permission=EOD_CANDIDATE_ONLY` **and** `invalidation_spot` blank) == 0 | FAIL |
| `UNGOVERNED_EXCEPTION_TEXT` | count(`stand_down_reason` matching `unsupported operand|Traceback|Unhandled exception`) == 0 | FAIL |
| `LINEAGE_DROP` | for each allow-listed Lab field: **not** (Lab populated == 0 **and** declared source populated > 0) | FAIL |
| `DIRECTION_LINEAGE` (regression) | Lab↔Options `governed_direction_record_sha256` match == row count | FAIL |

Every rule is a count over a run artefact, computable offline, and each maps to a gate in §C4.

### G-13 — Ledger coverage and named fallbacks

**Cycle 1 (small, high value).** Any ticker served from stale cached bars gets `bar_evidence_state = APPROVED_FALLBACK` and `bar_evidence_reason = PROVIDER_FETCH_FAILED_STALE_CACHE` on its row (AR-003 §6.3 state 4), and the count is published in `pipeline_integrity`. Today the only trace is a log line nobody gates on: *"39 tickers (1.2%) used stale cached bar data"* (B4-01).

**Cycle 2.** Route Discovery and package-backfill acquisition through the canonical gateway so their requests appear in `api_request_ledger`, enabling the run-wide reconciliation G-08 currently cannot make.

### G-14 — Closure documentation

Correct the "Rollout control" section of `AVS-SD-002_PHASE4_CLOSURE_20260903.md` to name `AVSHUNTER_DYNAMIC_THESIS_ENABLED` (as-built) and then `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED` (post-change). Add to the closure template a mandatory field: **"Exact environment variable name, verified present in `FEATURE_FLAG_ENV_VARS`."** A closure that names a non-existent flag is worse than one that names none, because it is actionable and wrong.

---

## C4. Replayable acceptance gates against run 20260904_004338

Each gate: an artefact, a filter, a required value, this run's value, and the Rev 1.1 §19 gate it serves. `AG-nn` are this design's gates.

### C4.1 Offline-replayable gates

These are checkable by re-running the affected stage against this run's pinned inputs, without any provider call.

| Gate | Assertion | This run | Required | Rev 1.1 §19 | Direction split required |
|---|---|---|---|---|---|
| **AG-01** | Vanguard rows with `profile_type=INSUFFICIENT_DATA` **and** `auction_state=ALIGNED` | **1,068** | **0** | 1, 3 | yes — 547/319/202 → 0/0/0 |
| **AG-02** | Rows with a missing POC represented as `0.0` (null only) | **1,551** | **0** | 1, 3 | yes — 793/482/276 → 0/0/0 |
| **AG-03** | Rows with `ready_to_trade=True` and null POC | **1,068** | **0** | 1 | yes |
| **AG-04** | Layer-2 alignment uplift granted where POC is null | **1,068** | **0** | 1 | yes |
| **AG-05** | Options rows `options_verdict=ARMED` and `invalidation_state=MISSING` | **43** (43/0/0) | **0** | 11 | yes; OTHER stays `NOT_APPLICABLE` |
| **AG-06** | Directional Options rows with `invalidation_state=MISSING` that are not `STAND_DOWN` with reason code `INVALIDATION_MISSING` | **43** | **0** | 11 | yes |
| **AG-07** | Morning rows with `capital_permission=EOD_CANDIDATE_ONLY` and blank `invalidation_spot` | **13** (13/0/0) | **0** | 11 | yes |
| **AG-08** | Lab rows with blank `invalidation_price` and `options_research_permission=EXECUTABLE_SUBJECT_TO_GATES` | **23** | **0** | 11, 14 | yes |
| **AG-09** | Unhandled `TypeError` in economics; free-text fields containing `unsupported operand`, `Traceback` or `Unhandled exception` | **36** (0/36/0) | **0** | 17 | yes — the CALL branch must be guarded too |
| **AG-10** | Rows stood down for an unresolved target carrying `economics_state=UNRESOLVED_EXCEPTION` and `economics_reason_code=STRUCTURAL_TARGET_UNRESOLVED` | **0 of 36** | **all** | 17 | yes |
| **AG-11** | Lab rows with `contract_bid_size`, `contract_ask_size`, `selected_quote_timestamp_utc`, `execution_viability_state` populated **or** an explicit named absence state | **0 / 256** | **256 / 256** | 14 | yes for CALL/PUT; OTHER absent from the book |
| **AG-12** | Lab `macro_*` lineage identity fields (`macro_packet_id`, `macro_packet_sha256`, `macro_source_fingerprint`, `macro_as_of_utc`, `macro_session_date`) populated | **0 / 256** each | **256 / 256** | 10 | n/a |
| **AG-13** | Lab rows with `monetisability_authority` populated | **0 / 256** | **256 / 256** | — (AR-003 §7.10) | yes |
| **AG-14** | Any allow-listed Lab field 0/N-populated while its declared source is >0/N | **≥ 22 fields** | **0** | 14 | n/a |
| **AG-15** | Handoff audit scores a correctly-empty shadow book as `EMPTY_BY_DESIGN`, not `LOW_FILL_RATE` | `LOW_FILL_RATE` ×2, `fail_count=2` | `EMPTY_BY_DESIGN` ×2, contributing 0 to `fail_count` | 17 | n/a |
| **AG-16** | Handoff audit `fail_count` **> 0** when replayed against this run's *unremediated* artefacts, driven by the G-12 rules | **2 (both spurious)** | **≥ 6 genuine**, 0 spurious | 17 | n/a |
| **AG-17** | Tickers served from stale cached bars carry `bar_evidence_state=APPROVED_FALLBACK` | 39 unnamed | 39 named | 15 | n/a |

**AG-16 is the gate that stops G-09 from doing harm.** It requires the corrected audit, replayed against the *original* artefacts of this run, to fail for the right reasons — a fail-count driven by AG-01, AG-02, AG-05, AG-07, AG-08, AG-09 and zero shadow-book noise. Without it, "fix the empty-shadow-book rule" is a change that makes a defective run look green (A6-03).

### C4.2 Gates requiring a live run — `AWAITING_RUN`

**AG-18 — Fail-closed Evening run (closes Rev 1.1 G18A for the completed-session state).**

```
python intelligent_orchestrator.py --evening
```
Environment: **all nine dynamic flags off**, including the new `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED`. This proves the protections fire with no new acquisition.

Expected deltas against `20260904_004338`: `ALIGNED` 1,068 → **0**; `NOT_EVALUATED` 0 → **1,551**; POC `0.0` 1,551 → **0**, null 0 → **1,551**; `timeframe` `intraday` → `GOVERNED`; `ARMED`-with-`MISSING` 43 → **0**; `EOD_CANDIDATE_ONLY`-without-invalidation 13 → **0**; economics `TypeError` 36 → **0** with 36 `UNRESOLVED_EXCEPTION`; Lab lineage 0/256 → **256/256**. Book composition reported, not asserted (see §C2.4).

**AG-19 — Profile-live Evening run (closes Rev 1.1 G18A fully).**

```
set AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED=1
python intelligent_orchestrator.py --evening
```
Expected: `market_profile\completed_profile_summary` artefact exists; rows split between `PROFILE_CONTEXT_ONLY` (usable evidence, real POC/VAH/VAL, `ready_to_trade=False`) and `NOT_EVALUATED`; **`ALIGNED` remains 0**; systemic-failure ratio below the `AVSHUNTER_PROFILE_MAX_FAILURE_RATIO` threshold (default 0.05, `build_completed_market_profiles.py:200`); on stage failure the run **continues** and Vanguard fails closed (§C3 G-01 change 3).

**AG-20 — Warm-cache rerun (closes Rev 1.1 G19). This is the run ACK must produce; it is specified here, not executed.**

```
REM Same session date as the immediately preceding Evening run. Run within the same session window.
python intelligent_orchestrator.py --evening
```
All flags off. Preconditions: the preceding run registered ≥ 1,200 `OPTION_CHAIN` datasets for the same `session_date`, and the G-08 identity change is deployed.

Expected ledger deltas for the new `run_id`:

| Measure | Preceding (cold) | Warm rerun required |
|---|---|---|
| `sum(physical_request_count)` where `dataset_type='OPTION_CHAIN'` | 1,264 | **0** |
| rows with `reason='exact fresh dataset'` | 0 | **≥ 1,200** |
| rows with `reason='no fresh canonical coverage'` | 1,264 | **0** |
| new rows in `dataset_registry` for `OPTION_CHAIN` | 1,261 | **0** |
| `physical == count(PROVIDER_FETCH rows)` scoped to `OPTION_CHAIN` | 1,264 == 1,264 ✔ | **0 == 0** |
| Options stage wall time | 70m 57s | materially lower — record, do not assert |

**Status: `AWAITING_RUN`.** Until it exists, G-08 stays open. Note the run's zero reuse was **correct** (A5-03) — different chain sessions — so this gate must be a *same-session* rerun, not a comparison against the previous night. Comparing against `20260902_232526` can never show reuse and would be a false gate.

### C4.3 Regression gates — the positives that must not move

| Gate | Assertion | Value to preserve | §19 |
|---|---|---|---|
| **RG-01** | Discovery reconciliation | 3,320 = selected + excluded, exact | 15 |
| **RG-02** | Options direction population | CALL/PUT/STRANGLE/UNRESOLVED sums to the Options row count; no direction silently reclassified | 11 |
| **RG-03** | Lab direction lineage | `governed_direction_record_sha256` matches Options↔Lab on **N/N** rows | 11, 14 |
| **RG-04** | Governed hold periods | 100% of Lab rows carry a non-null `hold_period` **and** `hold_window`, and they agree row-for-row | 11 |
| **RG-05** | Lab population reconciliation | rows in == rows out; `nunique(trade_idea_id) == nunique(ticker) == row count` | 15 |
| **RG-06** | Morning permission withheld | `morning_execution_permission` null 100%; `prep_permission = MANUAL_REVIEW_MORNING_VALIDATION` 100% | 13 |
| **RG-07** | **OTHER-direction handling** | 100% of STRANGLE/UNRESOLVED rows `STAND_DOWN` with `invalidation_state = NOT_APPLICABLE`; **0** reach the Lab | 11 |
| **RG-08** | Macro authority | `macro_authority=MACRO_ADVISORY_ONLY` and `macro_data_role=ADVISORY_ONLY` 100% | 10 |
| **RG-09** | No Polygon option-chain fallback | `POLYGON` rows in `api_request_ledger` for `OPTION_CHAIN` == 0 | 15 |

RG-07 deserves emphasis: the OTHER direction is the one part of the invalidation contract that already works, and the G-03/G-04 changes touch the same code. It is the most likely accidental casualty of this build.

### C4.4 Gate-to-§19 map

| Rev 1.1 §19 gate | Served by | Closes when |
|---|---|---|
| 1 — P0 blockers closed | AG-01…AG-10 | AG-18 passes |
| 3 — separate immutable identities | AG-01, AG-02 | AG-19 passes |
| 10 — macro advisory and separately refreshable | AG-12, RG-08 | AG-18 |
| 11 — direction/horizon/geometry frozen | AG-05…AG-08, RG-02, RG-03, RG-07 | AG-18 |
| 13 — exact quote only for immediate execution authority | RG-06 | AG-18 |
| 14 — Lab and Interpreter show the same accepted evidence | AG-11, AG-14 | AG-18 |
| 15 — populations and physical requests reconcile | AG-17, AG-20, RG-01, RG-05, RG-09 | **AG-20 (`AWAITING_RUN`)** |
| 17 — zero unexplained P0/P1 failures | AG-09, AG-10, AG-15, AG-16 | AG-18 |
| 18 (**G18A**) — live completed-session cycle | AG-18, AG-19 | AG-19 passes |
| 19 (**G19**) — runtime, API cost, disk budget | **AG-20** | **`AWAITING_RUN`** |
| 20 — backup restoration verified | §C7 | per-change |

**The next Evening run can close G18A (completed-session state) via AG-18 and AG-19.** It cannot close G19; that needs the same-session warm rerun AG-20. Gates 2, 4–9, 12, 16 belong to the dynamic path and are untouched by this design.

---

## C5. Test additions

For each gate, the file and case. Where an existing test passed while the defect was live, what it asserted instead of the real property, and how it must change.

### C5.1 Tests that passed while the defect was live

**`tests\test_dynamic_session_phase4.py::test_vanguard_fails_safe_without_governed_profile` (`:159`) — the P0-02 case.**

```python
def vanguard_input(evidence=None, *, required=True) -> VanguardInput:   # :65
    ...
verdict = AuctionStateSynthesizer().synthesize(vanguard_input(None))     # :160
```

The helper defaults `required=True`. **No test in the repository ever constructs `required=False`** — the production configuration — and asserts anything about it.

*What it asserted:* "given the governed contract is required, an absent profile fails safe."
*What it should have asserted:* "an absent profile fails safe **on the input the production adapter actually builds**."
*Change:* flip the helper default to `required=True` **as the schema default** (per §C3 G-02), and add `test_vanguard_fails_safe_when_contract_flag_absent_from_package()`, which builds the input through `orchestrator_adapter.build_input()` from a package dict with **no** `market_profile_contract_required` key at all — the exact shape of all 1,601 packages in this run — and asserts `auction_state == "NOT_EVALUATED"`, `ready_to_trade is False`, `profile.poc is None`.

**`tests\test_dynamic_session_phase6.py::test_completed_profile_stage_uses_frozen_thesis_flag` (`:173-179`).**

```python
source = (Path(__file__).parents[1] / "intelligent_orchestrator.py").read_text(...)
assert "AVSHUNTER_COMPLETED_PROFILE_ENABLED" not in source
assert 'COMPLETED_PROFILE_ENABLED = os.environ.get(\n        "AVSHUNTER_DYNAMIC_THESIS_ENABLED"' in source
```

*What it asserted:* a source-code string, including its exact indentation and line break.
*Why that is wrong:* it verifies *text*, not behaviour. It passes whether or not the stage executes, and it breaks on any reformatting. It is also the sharpest illustration of G-14 — the codebase asserts `AVSHUNTER_COMPLETED_PROFILE_ENABLED` is absent from the source while the Phase 4 closure tells operators that is the flag to set.
*Change:* replace with a behavioural test that calls `completed_profile_stage_enabled()` under a monkeypatched environment and asserts the resolved boolean for `{"1","true","on","0","",unset,"garbage"}`.

**`tests\test_selected_contract_economics.py` and the P0-04 pack.**
*What they asserted:* that viability is separated from EV/R:R, and that Execution Gate reads `execution_viability_state`. Both true; both silent on whether the Lab ever receives it.
*Change:* add T-06c below.

### C5.2 New tests

| ID | File | Case | Gate |
|---|---|---|---|
| T-02a | `tests\test_vanguard_fail_closed.py` (new) | `test_absent_contract_key_still_fails_closed` — package dict with no `market_profile_contract_required`, built through the real adapter | AG-01 |
| T-02b | same | `test_unusable_profile_emits_null_levels_not_zero` — asserts `poc is None`, **not** `poc == 0` | AG-02 |
| T-02c | same | `test_not_evaluated_denies_readiness` — `ready_to_trade is False` for CALL, PUT and OTHER | AG-03 |
| T-02d | same | `test_layer2_uplift_requires_non_null_poc` — `_calculate_right_side_score` grants 0 for `ALIGNED` with null POC | AG-04 |
| T-02e | same | `test_explicit_false_contract_flag_is_rejected` — a package setting `False` raises rather than silently opting out | AG-01 |
| T-03a | `tests\test_invalidation_precondition.py` (new) | `test_call_without_invalidation_cannot_arm` | AG-05 |
| T-03b | same | `test_put_without_invalidation_cannot_arm` | AG-05 |
| T-03c | same | `test_other_direction_remains_not_applicable` — **regression**: STRANGLE/UNRESOLVED unchanged | RG-07 |
| T-03d | same | `test_stand_down_carries_invalidation_missing_reason_code` | AG-06 |
| T-04a | `tests\test_eod_candidate_authority.py` (new) | `test_capital_permission_denied_without_invalidation` — all three directions | AG-07 |
| T-04b | same | `test_lab_permission_not_executable_without_invalidation` | AG-08 |
| T-05a | `tests\test_trade_economics_guard.py` (new) | `test_none_target_call_returns_unresolved_exception` — **the CALL case, which has never been tested** | AG-09, AG-10 |
| T-05b | same | `test_none_target_put_returns_unresolved_exception` | AG-09, AG-10 |
| T-05c | same | `test_no_raw_exception_text_in_published_reason` — regex over `stand_down_reason` and `trigger_status_reason` for `unsupported operand\|Traceback\|Unhandled exception` | AG-09 |
| T-05d | same | `test_non_finite_target_also_guarded` — NaN and inf, not just `None` | AG-09 |
| T-06a | `tests\test_lab_quote_lineage.py` (new) | `test_bid_ask_sizes_survive_options_to_morning_to_lab` | AG-11 |
| T-06b | same | `test_selected_quote_timestamp_accepts_all_three_producer_names` | AG-11 |
| T-06c | same | `test_execution_viability_family_is_mapped_not_merely_allow_listed` — asserts a `first(sig,…)` assignment exists for every `execution_viability_*` name in the allow-list | AG-11 |
| **T-06d** | same | **`test_no_allow_listed_field_is_universally_null_while_its_source_is_populated`** — walks the whole `lab_control.py` allow-list against a production-shaped fixture. **This is the generic defence: it catches `execution_viability_*`, `contract_bid_size` and the `macro_*` family in one assertion, and would have caught the F29 recurrence** | AG-14 |
| T-07a | `tests\test_selected_contract_economics.py` | `test_monetisability_authority_stamped_on_every_row` including `FAILED` rows | AG-13 |
| T-08a | `tests\test_option_chain_cache_identity.py` (new) | `test_scope_fingerprint_stable_across_run_dates_for_same_session` — same session, two run dates, one fingerprint | AG-20 |
| T-08b | same | `test_superset_expiry_window_resolves_as_reuse_with_zero_physical` | AG-20 |
| T-08c | same | `test_option_chain_registration_sets_expires_at` | AG-20 |
| T-09a | `tests\test_handoff_contract_audit.py` | `test_zero_row_shadow_book_scores_empty_by_design` | AG-15 |
| T-09b | same | `test_empty_by_design_requires_corroboration_from_dropoff_audit` — rows satisfying the shadow mask but an empty book ⇒ `EMPTY_UNEXPECTED`/`FAIL` | AG-15 |
| T-09c | same | `test_missing_shadow_book_artifact_is_not_more_lenient_than_empty_one` | AG-15 |
| **T-12a** | `tests\test_semantic_audit_rules.py` (new) | **`test_audit_fails_on_unremediated_run_20260904_004338_fixtures`** — the eight G-12 rules against fixtures derived from this run's actual artefacts; asserts `fail_count ≥ 6` with **zero** shadow-book contribution | **AG-16** |
| T-12b | same | `test_audit_passes_on_remediated_fixtures` | AG-16 |
| T-13a | `tests\test_bar_fallback_state.py` (new) | `test_stale_cached_bars_carry_approved_fallback_state` | AG-17 |

**T-12a is the second-level closure the build skipped.** It pins the corrected audit against the real, unremediated artefacts of a run that is known to be defective, and requires it to fail. An audit that cannot fail on a known-bad run is not an audit — which is exactly the condition A6-03 found.

---

## C6. Implementation sequence and ownership

Four agents per AVS-SD-002 §17. Ownership rules `§17.1` apply unchanged: **the integration lead alone edits `intelligent_orchestrator.py`, `morning_gate.py`, `contracts\lab_control.py` and shared schemas**, and no two agents edit them concurrently. Workers return patches and evidence; the lead promotes. Each agent independently tests a boundary they did not implement.

### Cycle 1 — closes without the profile stage being live

**Item 1 is the change that makes tomorrow's Evening run fail closed on unusable profiles**, as AVS-SD-002 §21 requires.

| # | Item | Owner | Files (exclusive) | Gate |
|---|---|---|---|---|
| **W1-1** | **Vanguard fail-closed unconditional** — flip all five defaults; guard the Layer-2 uplift on non-null POC | **Agent 2** | `vanguard\layer1_auction\auction_synthesizer.py`, `vanguard\schemas\input_schema.py`, `vanguard\integration\orchestrator_adapter.py`, `vanguard\layer2_statistical\edge_detector.py` | AG-01…AG-04 |
| W1-2 | Vanguard input plumbing default | **Lead** | `scripts\run_vanguard_from_packages.py` | AG-01 |
| W1-3 | Invalidation precondition at arming | **Agent 1** | `scripts\avshunter_options_intelligence.py` (arming block only) | AG-05, AG-06 |
| W1-4 | Null/non-finite target guard → `UNRESOLVED_EXCEPTION`; no raw exception text | **Agent 1** | `scripts\avshunter_options_intelligence.py` (`:4138-4158`, `:5428-5475`, exception handler) | AG-09, AG-10 |
| W1-5 | Invalidation precondition on candidate status and capital permission | **Agent 1** | `eod_candidate_engine.py` | AG-07 |
| W1-6 | EOD projection: add quote-size, quote-quality and `selected_quote_timestamp_utc`; add macro lineage identity | **Agent 1** | `eod_candidate_engine.py` (projection lists) | AG-11, AG-12 |
| W1-7 | Lab mapper: `execution_viability_*` assignments; widen quote-timestamp aliases; resolve or remove orphan columns | **Lead** (owns `lab_control.py` per §17.1) | `contracts\lab_control.py`, `contracts\lab_evidence_overlay.py` | AG-08, AG-11, AG-14 |
| W1-8 | Monetisability authority stamp | **Agent 2** | `contracts\selected_contract_economics.py` | AG-13 |
| W1-9 | Audit: `EMPTY_BY_DESIGN` + corroboration + severity correction | **Agent 3** | `handoff_contract_audit.py` | AG-15 |
| **W1-10** | **Audit: the eight G-12 semantic rules** — must ship **with** W1-9, never after | **Agent 3** | `handoff_contract_audit.py` (`_semantic_contract_audit`), `uat_audit_report.py` | **AG-16** |
| W1-11 | Stale-bar `APPROVED_FALLBACK` state | **Agent 2** | `avshunter_discovery_ULTIMATE.py` (state stamp only) | AG-17 |
| W1-12 | Test suites T-02…T-13 | **Agent 3** | `tests\` (new files only) | all |
| W1-13 | Correct the Phase 4 closure flag name; add the closure-template field | **Lead** | `audit\pipeline_map\` | G-14 |
| **W1-14** | **AG-18 fail-closed Evening run + evidence capture** | **Lead** | — | **G18A (partial)** |

**W1-9 and W1-10 are a single promotion unit.** Shipping W1-9 alone would remove the run's only `FAIL` and add no replacement, turning a defective run green (A6-03). The lead must not promote them separately.

**Concurrency check.** `scripts\avshunter_options_intelligence.py` is touched by W1-3, W1-4 (both Agent 1) — same owner, sequential. `eod_candidate_engine.py` by W1-5, W1-6 (both Agent 1). `handoff_contract_audit.py` by W1-9, W1-10 (both Agent 3). `contracts\lab_control.py` by the lead alone. `intelligent_orchestrator.py` is **not touched in cycle 1** — the fail-closed change needs no orchestrator edit, which is what makes item 1 safe to ship first.

### Cycle 2 — needs the profile stage live

| # | Item | Owner | Files | Gate |
|---|---|---|---|---|
| W2-1 | Split the flag: add `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED`; move the read out of the class body into a function | **Lead** | `intelligent_orchestrator.py:440-442,973,2417`, `contracts\dynamic_session_contract.py`, `contracts\dynamic_session_authority_v1.json`, `orchestrator\dynamic_release.py` | AG-19 |
| W2-2 | Replace `critical=True` with governed degradation | **Lead** | `intelligent_orchestrator.py:2427` | AG-19 |
| W2-3 | Cache identity: absolute expiry bounds in the scope hash; superset resolution; `expires_at` on registration | **Agent 1** | `canonical_data\` resolver + registry | AG-20 |
| W2-4 | Delete the legacy fabrication branch `auction_synthesizer.py:66-144` once AG-18 has passed twice | **Agent 2** | `vanguard\layer1_auction\auction_synthesizer.py` | AG-01 |
| W2-5 | Macro advisory content: wire or remove the 14 non-identity `macro_*` columns | **Agent 2** | `eod_candidate_engine.py`, `contracts\lab_control.py` (lead merges) | AG-12 |
| W2-6 | Ledger coverage for Discovery and package backfill | **Agent 1** | `avshunter_discovery_ULTIMATE.py`, backfill, `canonical_data\` gateway | G-13, AG-20 run-wide |
| W2-7 | **AG-19** profile-live Evening run | **Lead** | — | **G18A** |
| W2-8 | **AG-20** same-session warm rerun | **Lead / ACK** | — | **G19** |

### Which gaps close when

| Closes in cycle 1 | Needs the profile stage live (cycle 2) |
|---|---|
| G-02, G-02b, G-02c (**the headline**) | G-01 (stage execution itself) |
| G-03, G-04, G-05, G-10 | G-08 / AG-20 (`AWAITING_RUN`) |
| G-06, G-07, G-09, G-11 (identity half), G-12, G-14 | G-11 (advisory-content half) |
| G-13 (fallback naming half) | G-13 (ledger-coverage half) |

**G-02 closes in cycle 1 without the profile stage.** That is the point of D2 and of Option 1: the protection does not depend on the acquisition. Tomorrow's run fails closed whether or not a profile exists.

---

## C7. Backup, rollback and promotion

### Backups — Phase 0 pattern

Per-change, before any edit, following the existing convention (`backups\avs_sd_002_rev1_1_phase4_prechange_20260903_151506`):

```
backups\avs_sd_003_<item>_prechange_<YYYYMMDD_HHMMSS>\
```

containing the pre-change copy of every file the item touches plus a `MANIFEST.json` of SHA-256 hashes. Databases (`control_plane.sqlite`, `historical_prices.sqlite`, `run_plans.sqlite`) are backed up before W2-3 only, which is the sole item that writes registry semantics. Restoration is verified by the Phase 0 three-database restore procedure before W2-3 is promoted (Rev 1.1 §19.20).

The run artefacts of `20260904_004338` and `20260902_232526` are the remediation baseline and are **read-only for the duration of this work**. Nothing in this design writes to `data\output\runs\`.

### Rollback triggers

| Item | Trigger | Action |
|---|---|---|
| W1-1 / W1-2 | Vanguard rows drop below 1,500 (population loss, not score change) | restore backup; investigate — fail-closed must not delete rows (D2) |
| W1-1 | **Lab book collapses below 128 rows** | **do not roll back automatically.** Capture the book, compare composition to `20260904_004338`, escalate to ACK. A collapse means the book was resting on the fabricated uplift — that is the finding, not a regression. ACK decides whether to proceed or revert |
| W1-3 / W1-5 | `ARMED` count drops below 150 (was 242) | investigate: the precondition should remove ~43, not ~90 |
| W1-3 / W1-5 | **RG-07 breaks** — any STRANGLE/UNRESOLVED row changes state | immediate rollback; OTHER-direction handling is a protected positive |
| W1-4 | Any direction's `STAND_DOWN` count rises by more than 50 | investigate the guard's reach |
| W1-7 | **RG-03 breaks** — direction lineage hash match < 100% | **immediate rollback.** This is the run's strongest positive |
| W1-9 / W1-10 | AG-16 fails (audit does not fail on unremediated fixtures) | block promotion — never promote W1-9 without W1-10 |
| W2-1 / W2-2 | Evening run aborts at the profile stage | governed degradation should prevent this; if it aborts, revert to `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED=0` — the cycle-1 protections still hold |
| W2-3 | Warm rerun physical requests > 0 for unchanged identities, or any dataset resolves to the wrong session | restore `control_plane.sqlite`; a wrong-session hit is far worse than a miss |
| W2-4 | AG-01 regresses | restore the legacy branch |

### Promotion sequence and required observation

Each step is promoted only after the observation named. **No step enables a flag that gates a protection, because after cycle 1 no flag does.**

| Step | Change | Flags after | Observation required before the next step |
|---|---|---|---|
| 1 | W1-1…W1-13 | all off (nine, incl. the new one) | Full offline replay: AG-01…AG-17 pass on replayed artefacts; RG-01…RG-09 unchanged |
| 2 | **AG-18** — fail-closed Evening run | all off | `ALIGNED=0`, `NOT_EVALUATED=1,551`, POC null not zero, `ARMED`-without-stop `=0`, Lab lineage 256/256, book composition reported. **Closes G18A partially** |
| 3 | W2-1…W2-2 (flag split, governed degradation) | all off | Unit + contract evidence; no behaviour change with the flag off |
| 4 | **AG-19** — `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED=1` | 1 of 9 on | Profile artefact exists; `ALIGNED` still 0; failure ratio under threshold; a forced stage failure degrades rather than aborting. **Closes G18A** |
| 5 | W2-3 (cache identity) | 1 of 9 on | Registry rows carry `expires_at`; fingerprint stable across run dates in unit tests |
| 6 | **AG-20** — same-session warm rerun | 1 of 9 on | Physical `OPTION_CHAIN` requests `= 0`; `exact fresh dataset ≥ 1,200`; ledger reconciles `0 == 0`. **Closes G19** |
| 7 | W2-4…W2-6 | 1 of 9 on | AG-01 still passes with the legacy branch deleted |
| 8 | Resume the AVS-SD-002 Rev 1.1 promotion path | per `dynamic_release.py:218-237` | out of scope for AVS-SD-003 |

---

## C8. Definition of done

Restated in run-artefact terms. **No item is done because a test passed. Every item is done when run `N+1` shows it firing and the release assessor records a hash-bound artefact for it.**

An item is done when **all four** hold:

1. **The gate's count is met on a real run artefact**, with the artefact path, the exact filter and the three-direction split recorded — the standard used throughout `A_counts.csv`.
2. **The Phase 8 release assessor has recorded a hash-bound artefact** for the run that demonstrates it, in the pattern of `AVS-SD-002_PHASE8_EVIDENCE_20260903.json`.
3. **Its test exists and fails against the unremediated fixture.** A test that cannot fail on the known-bad state of run `20260904_004338` does not close anything — this is what `test_vanguard_fails_safe_without_governed_profile` did not do (§C5.1).
4. **The regression gates RG-01…RG-09 are unchanged** on the same run.

**AVS-SD-003 is complete when:**

- AG-01…AG-17 pass on run `N+1` with their three-direction splits recorded;
- RG-01…RG-09 are unchanged from `20260904_004338`;
- AG-18 and AG-19 have executed and closed Rev 1.1 gate 18 for the completed-session state (**G18A**);
- AG-20 has executed and closed Rev 1.1 gate 19 (**G19**) — until then G-08 remains open and is marked **`AWAITING_RUN`**;
- every closure document for this work names the exact environment variable and cites a run artefact, not a test count (G-14);
- the P0 recertification is re-issued with a **run-artefact evidence column** replacing the test-pack column.

**The explicit closure-standard change.** `AVS-AR-003_P0_RECERTIFICATION_20260903.md` closed P0-01…P0-07 "at the offline/code-contract level" on 1,141 passing tests and no production rows. Every one of those tests was correct and the run reproduced every defect anyway (§B2). From this design forward, a P0 may be recorded `CLOSED OFFLINE` — but **`CLOSED` requires a row count from a run artefact**, and the two states must never be reported in the same column again.

---

## C9. Approved Cycle 1 and MarketData adapter refinement

### C9.1 Architecture decision

`AVS-IMP-SD-003-001_CYCLE1_AND_ADAPTER_FIX_20260904.md` is **APPROVED WITH CHANGES** and is incorporated into this design through this section. Its verified diagnosis is accepted:

- the completed-session candle adapter sends UTC `Z` timestamps even though the MarketData endpoint interprets the request as Eastern wall-clock time;
- the same session returns the full expected 78 regular-session five-minute bars when expressed as naked Eastern wall-clock bounds, but only 30 bars through the present adapter request;
- the current transport discards HTTP status and rate-limit headers, does not classify `404/no_data`, and stamps one request-level session segment onto every returned bar;
- the profile builder lacks a completed-session coverage gate and counts per-ticker absence as a systemic provider failure;
- the Cycle 1 authority, lineage and audit repairs remain necessary before the profile capability is enabled.

The preflight proves that this is a request-contract defect, not a general MarketData entitlement failure. A `203` response is evidence to record; it is not, without additional provider evidence, a reason to reject otherwise valid bars.

### C9.2 Accepted, amended and deferred content

| Proposal | Decision | Controlling amendment |
|---|---|---|
| Protections unconditional; capabilities flagged | **Accept** | No environment flag may restore fabricated POC/VAH/VAL, profile uplift, invalid economics or missing-invalidation capital authority. |
| Unusable profile retains the ticker but contributes no authority | **Accept** | Emit null levels, `ready_to_trade=False`, zero profile uplift/confidence and an explicit evidence/reason pair. Never turn absence into numeric zero. |
| Cycle 1 invalidation, target, EOD projection, Lab mapping and audit repairs | **Accept** | Use the canonical mappings in §C9.3 and the two-level evidence bar in §C9.7. |
| W2-0 MarketData stock-candle adapter repair moves ahead of profile activation | **Accept** | The adapter may be built and fixture-tested before activation; no completed profile is authoritative until §C9.5 passes. |
| Raw `UNRESOLVED_EXCEPTION`, `INVALIDATION_MISSING` or `STRUCTURAL_TARGET_UNRESOLVED` string literals | **Reject as written** | Output states must use the central enum contract. Reason vocabulary may be extended once, centrally, and then imported everywhere. |
| All cached replays must issue zero provider requests | **Amend** | Protection replay and fixture replay must issue zero requests. A first profile-live run is a governed cold acquisition and will make recorded requests. Only a same-session warm replay must issue zero physical requests for already-covered identities. |
| Commit the present working tree as-is | **Reject** | `pre-tidy-20260904` is the immutable reference. Create a scoped release branch/manifest and include only sanctioned files; do not absorb unrelated dirty or untracked artefacts. |
| Per-change full backup directories | **Amend** | Create one immutable phase baseline plus SHA-256 manifest and database backups before the phase. Add an item-level delta backup only for a shared authority file or schema/database mutation. This preserves rollback without unnecessary disk duplication. |
| W1-8 monetisability stamp, W1-11 stale-bar fallback and W1-13 documentation deferred | **Accept for this repair unit** | Record them in the open register. They do not block adapter correctness, but none may be silently reported as closed. |

### C9.3 Canonical state and reason contract

The implementation must not create a second lifecycle vocabulary. The following mapping governs all Cycle 1 producers and consumers:

| Condition | Public evidence state | Governed reason/evaluation | Required authority result |
|---|---|---|---|
| Profile absent or below completed-session quality | `EvidenceState.NOT_EVALUATED` | existing `INSUFFICIENT_BARS` or `INCOMPLETE_SESSION` | retain row; null POC/VAH/VAL; no readiness or uplift |
| Directional thesis has no authoritative invalidation | `EvidenceState.DATA_DEFECT` | central reason `INVALIDATION_MISSING`; lifecycle evaluation `MISSING_AUTHORITATIVE_STOP` | `STAND_DOWN`; no capital permission |
| Directional thesis has null/non-finite structural target | `EvidenceState.DATA_DEFECT` | central reason `STRUCTURAL_TARGET_UNRESOLVED` | economics not evaluated; governed stand-down; no raw exception text |
| Non-directional thesis | `EvidenceState.NOT_EVALUATED` | existing non-directional lifecycle state | no forced CALL/PUT geometry; no capital permission |
| Future session requested | `EvidenceState.NOT_EVALUATED` | `NOT_YET_OBSERVABLE` | defer ticker; no systemic provider failure |
| Known inactive ticker | `EvidenceState.NOT_APPLICABLE` | `TICKER_INACTIVE` | exception-list disclosure; continue run |
| Provider transport or entitlement failure | `UNAVAILABLE_PROVIDER` or `DATA_DEFECT` as defined by the central contract | `PROVIDER_UNAVAILABLE`, `ENTITLEMENT_DENIED` or `RATE_LIMITED` | per-ticker continuation; systemic threshold evaluates only comparable provider failures |

`INVALIDATION_MISSING` and `STRUCTURAL_TARGET_UNRESOLVED` are approved as **reason codes**, not new top-level states. They must be added to the single `DataExceptionReason` owner before use. Raw copies in Options, EOD, Lab or audit code are forbidden. Existing persisted enum values remain readable.

### C9.4 MarketData response and request contract

The stock-candle transport must return a typed response envelope rather than an unqualified JSON mapping:

```text
MarketDataCandleResponse
  payload
  http_status
  acquired_at_utc
  rate_limit_limit
  rate_limit_remaining
  rate_limit_reset
  provider_status
```

Header fields are nullable because recorded fixtures and injected test transports may not carry them. Existing injected transports may be supported through one explicit compatibility adapter; production code must not infer a successful status from an exception path.

For intraday completed-session requests:

1. Obtain the exchange session bounds from the governed session calendar, including holidays, early closes and daylight-saving transitions.
2. Convert those bounds to `America/New_York`.
3. Serialize provider query bounds as naked Eastern wall-clock timestamps, without `Z` or an offset, because that is the behaviour proven by the preflight.
4. Convert returned epoch-second bar opens back to timezone-aware UTC internally.
5. Derive `PREMARKET`, `REGULAR` or `AFTER_HOURS` for each bar from its timestamp and the governed session bounds. Never stamp the request's segment onto every bar.
6. Preserve response status and rate-limit evidence in the request ledger. A successful call consumes the provider-reported amount when available, otherwise a conservative cost of one credit. `404/no_data` consumes the reported amount, which the preflight observed as zero.

The production adapter must never use a bare date as a substitute for exact intraday bounds. Exact exchange-session bounds prevent accidental extended-hours inclusion and make the coverage denominator deterministic.

### C9.5 Completed-session coverage and quality contract

The expected regular-session grid is derived from the governed session calendar and requested interval; it is not hard-coded to 78 bars. A completed-session profile is usable only when all of the following hold:

- session is closed and matches the requested exchange session;
- unique regular-session bars / expected regular-session bars is at least `0.95`;
- the first and last expected regular-session regions are represented, so a contiguous missing open or close is not hidden by the ratio;
- timestamps are ordered and unique after deterministic deduplication;
- OHLC values are finite and geometrically valid, and volume is non-negative;
- no bar belongs to another trading session;
- acquisition identity, provider, response status and coverage diagnostics are persisted.

If any condition fails, publish `PARTIAL_SESSION` diagnostics and the canonical `NOT_EVALUATED`/`INCOMPLETE_SESSION` result. Do not calculate or publish authoritative POC, VAH, VAL, auction alignment, readiness, confidence or Layer-2 uplift from that set. The ticker remains in the pipeline for research and exception review.

The builder's systemic stop ratio includes only comparable transport, authentication, entitlement and rate-limit failures. A per-ticker `no_data`, inactive ticker or future-session deferral is recorded in the exception list and does not stop unrelated tickers. A provider-wide pattern of `no_data` remains observable and can be escalated by a separate threshold; it is not silently ignored.

### C9.6 Cache-first data flow

The completed-profile stage follows this order:

```text
governed ticker worklist
  -> resolve exact completed-session candle identity in CDS
     -> covered and quality-valid: reuse canonical bars
     -> missing/partial/expired: call MarketData adapter
        -> validate and register immutable raw response
        -> normalize bars and publish quality evidence
  -> build MarketProfileEvidence only from quality-valid regular-session bars
  -> Vanguard consumes the governed evidence or explicit NOT_EVALUATED state
  -> Options/EOD/Lab preserve evidence identity and absence reason
```

Dropped tickers are excluded before cache resolution or provider acquisition. A ticker dropped at an earlier governed stage must not generate a later stock-candle request merely because it existed in the original universe.

### C9.7 Testing and production acceptance

The implementation has four distinct proof modes; they must not be conflated:

| Proof mode | Provider calls | Purpose | Passing evidence |
|---|---:|---|---|
| Unit/fixture adapter tests | 0 | Eastern bounds, `404/no_data`, `203`, headers, segment classification, early close, malformed bars | deterministic assertions and real sanitized preflight fixtures |
| Cached Vanguard-onward protection replay | 0 | Cycle 1 authority, target/invalidation, projection, Lab mapping and semantic audit | AG-01…AG-17 plus unchanged RG-01…RG-09 |
| First profile-live Evening run | expected and ledgered | Cold acquisition and end-to-end completed-profile production | request count reconciles; coverage states published; no fabricated levels/uplift; run promotable |
| Same-session warm replay | 0 physical requests for covered identities | CDS reuse and identity correctness | cache-hit ledger reconciles; output identity and material fields are deterministic |

A **representative acquisition-only activation probe** must precede the first profile-authoritative run because the preflight's 1/10 `no_data` observation is statistically inconclusive. The probe samples at least the greater of 100 tickers or 10% of the governed profile worklist, stratified across sector and observed liquidity. It may populate the canonical candle cache and request ledger, but it must not publish Market Profile authority into Vanguard. Transport/authentication/entitlement failures are evaluated against the systemic threshold; valid per-ticker `no_data` exceptions are reported separately by reason and do not enter that ratio. AG-19 may proceed only when the request ledger reconciles, full-session coverage is demonstrated on successful responses, and no provider-wide failure pattern is present.

A no-capital Morning rehearsal may verify unconditional protections and EOD-to-Morning compatibility. It cannot close developing-profile or live quote gates while the market is closed. Production closure requires a subsequent market-session Morning Gate that shows the previous completed profile retained, current price used to validate the thesis, and no mutation of the original EOD thesis.

At both offline and artefact levels, tests must cover CALL, PUT and non-directional rows. The known-bad `20260904_004338` fixtures must fail the semantic audit; remediated fixtures must pass. A test edited to permit missing authority evidence is not an acceptable regression repair.

### C9.8 Two-agent implementation topology

No more than two agents may be active on this repair unit.

| Agent | Exclusive ownership | Independent verification duty |
|---|---|---|
| Integration lead | shared contracts/enums, `scripts\avshunter_options_intelligence.py`, `eod_candidate_engine.py`, Lab mapping, release manifest and final promotion | verify adapter/profile artefacts and audit results not authored by the lead |
| Bounded specialist | `canonical_data\marketdata_stock_candles.py`, `scripts\build_completed_market_profiles.py`, Vanguard fail-closed files and new isolated tests | reproduce CALL/PUT/non-directional authority tests and inspect downstream lineage without editing lead-owned files |

If a file crosses both scopes, the specialist supplies a patch or finding and the lead alone applies it. Neither agent edits a shared file concurrently. Tests run in isolated pytest processes, followed by one clean aggregate suite.

### C9.9 Revised implementation sequence

1. Freeze the `pre-tidy-20260904` reference, create the scoped phase backup/database backup and hash manifest, and record the exact sanctioned file list.
2. Centralize the two reason codes and add backward-compatible contract tests.
3. Implement Cycle 1 unconditional Vanguard protection and invalidation/target preconditions.
4. Implement EOD quote-size/quality/timestamp and macro identity projection, then Lab mapping and the eight semantic audit rules.
5. Correct the MarketData response envelope, Eastern request serialization, HTTP/no-data classification, per-bar session segments and rate-limit ledger capture.
6. Add session-aware coverage validation, per-ticker exception handling and cache-first resolution to the completed-profile builder.
7. Run focused CALL/PUT/non-directional tests, real sanitized adapter fixtures, known-bad audit fixtures and the complete regression suite.
8. Perform the zero-provider cached protection replay and publish the claim sheet with counts, hashes and regression comparisons.
9. Run the representative acquisition-only activation probe in §C9.7; populate only canonical candles/ledger evidence and keep profile authority disabled.
10. Enable only the completed-profile capability for a controlled cold Evening run; reconcile every physical call and profile state.
11. Repeat the same session to prove zero physical calls for covered candle identities.
12. Run the next market-session Morning Gate in no-capital validation mode, verify thesis continuity and record gaps/moves separately from the immutable EOD thesis.
13. Promote only if every acceptance gate passes; otherwise restore the phase backup or disable the profile capability while retaining the unconditional protections.

This refinement does not authorize a build by itself. It defines the approved implementation contract and replaces conflicting Cycle 1/adapter instructions in earlier drafts.
