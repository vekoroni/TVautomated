# AVS-TST-QT-001 §1 — System model at HEAD (2026-09-06)

Built from the tree (§0A), using the documents to explain intent. Every claim cites `file:line`.
Written **before** any test was run. Pre-registered cases are in `03_PREREGISTERED_EXPECTATIONS.csv`.

---

## 1. The executed path at HEAD

### 1.1 `--evening` no longer runs the legacy path

```
intelligent_orchestrator.py:6570   runtime_profile = governed_runtime_profile_summary()
                          :6571   runtime_flags  = DynamicSessionFeatureFlags.from_environment()   # no arg
                          :6580   dynamic_requested = auto|finalise|replay|plan_only        -> False for --evening
                          :6632   if dynamic_requested or runtime_flags.plan_engine:        -> TRUE
                          :6733   elif args.evening:   <-- LEGACY BRANCH, UNREACHABLE
```

`runtime_flags.plan_engine` resolves from `contracts/dynamic_session_runtime_v1.json`, where
`AVSHUNTER_DYNAMIC_PLAN_ENABLED` is **`true`**. Therefore **`--evening` unconditionally enters the dynamic dispatcher**, and the legacy `elif args.evening:` branch at `:6733` is dead code in production.

**The DDD integration claim is TRUE.** AVS-SD-003 §C2 and AVS-MVP-001 §2 both assume the legacy path carries the MVP with dynamic flags off. That assumption no longer holds. → `C_DEVIATIONS.md` D-01.

### 1.2 The five-line executed path

```
1. CLI --evening  ->  requested_action_from_cli(evening=True) = BUILD_THESIS      (dynamic_dispatcher.py:235)
2. resolve_dispatch_plan(as_of_utc, output_dir)  ->  RunPlan{plan_hash, pipeline_run_id,
                                                     resolved_action, session_state,
                                                     last_completed_session}      (:158-221)
3. flag gates: plan_engine required; BUILD_THESIS requires completed_thesis_builder
   (both true in the profile)                                                     (orchestrator:6674+)
4. callbacks{BUILD_THESIS: _build, FINALISE: _build, VALIDATE: premarket_workflow}
   -> evening_workflow(run_id=plan.pipeline_run_id, data_mode="AUTO",
                       evidence_session_date=plan.last_completed_session,
                       run_plan=planned)                                          (orchestrator:6700-6727)
5. inside evening_workflow: Discovery -> packages -> completed-profile stage
   (COMPLETED_PROFILE_STAGE_ENABLED=true) -> Vanguard (governed verdict, unconditional)
   -> Options -> Horizon -> EIL -> EOD candidates -> Lab book; then
   _record_dynamic_thesis_receipt(planned) on BUILD_THESIS only.
```

Two behavioural differences the dispatcher introduces that no claim sheet notes:

- **`data_mode` is hard-coded `"AUTO"`** on the dynamic path (`:6706`), whereas the legacy branch passed `args.data_mode` (`:6742`). `--data-mode` is silently ignored for `--evening`.
- **`FINALISE` and `BUILD_THESIS` share the same callback** (`_build`). Rev 1.1 §8.3 treats them as distinct actions with different authority ceilings. Pre-registered as `DISP-03`.

### 1.3 What the runtime profile enables, and the rollback

Live file `054a76be…`, v1.0.1, `AVS-DDD-CLOSURE-20260905`, `status: CONTROLLED_LIVE_CYCLE`. Eight of nine flags `true`; only `AVSHUNTER_DYNAMIC_AUTO_ENABLED` is `false` (§0A.4.1).

`AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1` (`dynamic_session_contract.py:135-143`) forces all nine to `False`, restoring the legacy path — `plan_engine` becomes `False`, so `:6632` is False and `:6733` executes. **This is the operator's one-switch rollback to the MVP-assumed path.** An env var may disable a governed capability but cannot promote one the profile withholds (`:154-157` raises `RuntimeError`), so `AUTO` cannot be reached from the environment.

---

## 2. Authority matrix as implemented

| Decision | Sole writer (file:function) | Readers that could override | Override reachable? |
|---|---|---|---|
| direction | `contracts/direction_governance.py` → governed record + `governed_direction_record_sha256` | Options re-resolves at its stage; Lab copies | **No** — hash match verified 256/256 in RCA-002; new audit rule `options_to_lab_direction_hash` (`handoff_contract_audit.py`) makes divergence a FAIL |
| hold | `macro_horizon_router` | Options reads | No |
| invalidation | Vanguard geometry → `invalidation_spot`; `invalidation_state ∈ {AVAILABLE, MISSING, NOT_APPLICABLE}` | Options arming, EOD status, Lab permission | **No, now** — arming, EOD capital permission and Lab permission all gate on it (§3.5) |
| contract | `scripts/avshunter_options_intelligence.py` selection | Morning re-selects on repair | Yes, by design (repair lane) |
| viability | `contracts/long_option_policy.py` | Morning Gate recomputes from live quote; Execution Gate verifies contract identity | Yes, by design |
| monetisability | `contracts/selected_contract_economics.py` | — | advisory only |
| profile | `scripts/build_completed_market_profiles.py` → `MarketProfileEvidence` | Vanguard consumes; **no other writer** | **No** — `market_profile_contract_required` can no longer be disabled (raises) |
| macro | `scripts/macro_quant_packet.py` | advisory stamps only | No |
| final action | `execution_gate.py` | — | — |

Against AR-003 §8 this is materially closer to "one authority per decision" than the RCA-002 state. The remaining divergence is that **`session_segment` is now derived** (`marketdata_stock_candles.py:_segment_for_timestamp`) rather than asserted — a fix, not a divergence.

---

## 3. Algorithms changed this week, as specifications

For each: inputs → rule → outputs, and **the wrong answer a subtle bug would give**.

### 3.1 Vanguard fail-closed verdict

`auction_synthesizer.py:59` — `if not getattr(input, "market_profile_contract_required", True): raise VanguardInputError`. The governed verdict is then **unconditional**.
- Unusable/absent evidence → `_not_evaluated`: `auction_state="NOT_EVALUATED"`, `ready_to_trade=False`, `poc=None`, `profile_type="INSUFFICIENT_DATA"`, `timeframe="GOVERNED"`.
- Usable evidence → `PROFILE_CONTEXT_ONLY`, `ready_to_trade=False`, real POC/VAH/VAL.
- **Wrong-implementation signature:** POC emitted as `0.0` instead of `None` (the RCA-002 defect), or `ready_to_trade=True` on `PROFILE_CONTEXT_ONLY`.

### 3.2 Layer-2 score

`edge_detector.py`: `profile_usable = poc is not None and float(poc) > 0`.
- `_calculate_right_side_score`: `+25 ALIGNED / +15 TRANSITIONING / +5 SEARCHING`, **each now gated on `profile_usable`**.
- confidence: `state.confidence*0.25 + outcomes.confidence_level*0.35 + auction_conf*0.40`, where `auction_conf = auction.confidence*(0.60 if no_intraday else 1.0) if profile_usable else **0.0**`.
- **Consequence not stated in any claim sheet:** with zero usable profiles, the confidence ceiling falls from 1.00 to **0.60**, and every row loses the same 25/15/5. Ranking is preserved only if the lost component was uniform — it was not (1,068 rows got +25 and 483 got +15 in run 20260904_004338). Pre-registered `L2-03`.
- **Wrong-implementation signature:** gating only the score and not `auction_conf`, or using `poc is not None` without `> 0` (a fabricated `0.0` would then count as usable).

### 3.3 Completed-profile coverage and the two gates

`build_completed_market_profiles.py:99-160`:
```
expected = expected_intraday_timestamps(session, open, close, interval, "REGULAR")   # RTH, bar-OPEN grid,
                                                                                     # inclusive_end = close - interval
coverage = |observed ∩ expected| / |expected|
usable = coverage >= 0.95 AND first_region AND last_region AND duplicates==0
         AND ordered AND wrong_session==0 AND numeric_valid AND provider_status 2xx
```
`first_region = expected[0] in observed` (09:30), `last_region = expected[-1] in observed` (15:55).
Stage-level, **new at closure**: `min_usable_ratio = 0.90` (`:171`) on the fraction of tickers yielding usable profiles.

Expected RTH bars: **390 / 78 / 26 / 13** for 1 / 5 / 15 / 30-minute.

**Exclusive-`to` boundary** (`marketdata_stock_candles.py:286`): `provider_end_utc = end_utc + interval`. The resolver passes `end_utc` = last expected bar open (15:55); MarketData's `to` is exclusive; so without the `+interval` the 15:55 bar is never returned → 77/78 and `last_region=False`.

- **Wrong-implementation signature (and the one I expect to find in the claim sheet, not the code):** believing coverage was the binding constraint. At 77/78 = 98.7 % coverage passes both 95 % and 90 %; the failure was `last_region`. Pre-registered `PROF-COV-04`.

### 3.4 Market Profile arithmetic — `market_structure/profile.py`

- bin width `:32-34`: `round_to_tick(max(exchange_tick, atr14 / 40.0), exchange_tick)`; **raises `ValueError("positive finite ATR14 required")`** when ATR14 is null, non-finite or ≤ 0. This is the source of the 50 `DATA_DEFECT` rows in run 20260905_151448 — correct fail-closed behaviour.
- TPO period `:91`: 30-minute buckets from the regular open.
- POC `:96`: `int(np.flatnonzero(counts == counts.max())[-1])` — **ties resolve to the HIGHEST-price bin**.
- Value area `:37-43`: expand from POC, taking the larger neighbour, **ties expand upward** (`if above >= below: high += 1`), until `accumulated >= total * 0.70`.
- **Wrong-implementation signature:** `argmax` (first/lowest bin) for POC; expanding downward on ties; or terminating at `> target` rather than `>= target`, which under-fills the value area by one bin.

### 3.5 Structural-target ladder, null guard, invalidation precondition

- Ladder (`avshunter_options_intelligence.py:4138-4158`): discovery target (direction-gated) → `l1_far` (direction-gated) → CALL `target_3r = entry + 3·stop_dist` / PUT `entry − 3·stop_dist` → `None`. `stop_dist = abs(entry − stop) if stop is not None else None`, so **a missing stop propagates to a null target in both directions**.
- Guard: null/non-finite target → governed record with `economics_reason = STRUCTURAL_TARGET_UNRESOLVED`, `options_verdict = STAND_DOWN`. Must be **before** the direction branch, or the CALL path at `:5464` retains the identical exposure.
- Invalidation precondition: `invalidation_state = MISSING` ⇒ never `ARMED`; EOD ⇒ `NOT_AUTHORIZED_INVALIDATION_MISSING`; Lab ⇒ not `EXECUTABLE_SUBJECT_TO_GATES`. OTHER (STRANGLE/UNRESOLVED/null) ⇒ `NOT_APPLICABLE` end-to-end (RG-07).
- **Wrong-implementation signature:** guarding inside the PUT branch only (fixes the observed symptom, leaves CALL exposed); or treating `NOT_APPLICABLE` as `MISSING` and standing down the 190 non-directional rows.

### 3.6 Handoff / semantic audit

`handoff_contract_audit.py` (+378 lines): nine categories including `ARMED_WITHOUT_GOVERNED_INVALIDATION`, `PROFILE_FAIL_OPEN`, `READY_WITHOUT_PROFILE`, `CAPITAL_WITHOUT_INVALIDATION`, `UNGOVERNED_EXCEPTION_TEXT`, `LINEAGE_DROP`, `options_to_lab_direction_hash`, and a three-way empty-artefact classification `EMPTY_BY_DESIGN` / `EMPTY_UNEXPECTED` / `EMPTY_UNCORROBORATED`.
- **Wrong-implementation signature:** an audit that fails everything is as useless as one that passes everything — hence the `A6` minimal-healthy-fixture probe.

### 3.7 Dispatcher and identity

`requested_action_from_cli`: `evening → BUILD_THESIS`, `morning|premarket → VALIDATE`, `finalise → FINALISE`, `replay → REPLAY`. `RunPlan` carries `plan_hash`, `pipeline_run_id`, `resolved_action`, `session_state`, `last_completed_session`.
- **Wrong-implementation signature:** `plan_hash` varying with wall-clock rather than only with governed inputs; or `--evening` resolving to `FINALISE` because both share the `_build` callback.

### 3.8 Worker 3 behavioural engine (staging, isolated)

v1 rules: control proxy over 3×4-session windows with ≥25 % displacement; contraction ≤70 %; effort/reward ≥120 % volume with ≤50 % move; exhaustion; failed follow-through; campaign origin. v2: bound-slot assessment validator (unbound numeric literal → reject; valid citation → accept; "Phase C accumulation" → semantic-lint block).
- **Wrong-implementation signature:** returning a neutral score instead of `INSUFFICIENT_DATA` for <12 bars; boundary comparisons using `>` where the spec says `≥`.

---

## 4. Five-line checkpoint (as required before continuing)

1. `--evening` → `runtime_flags.plan_engine` is **true** from the checked-in runtime profile, so control enters the **dynamic dispatcher** at `intelligent_orchestrator.py:6632`; the legacy `elif args.evening` branch at `:6733` is unreachable in production.
2. The dispatcher resolves `BUILD_THESIS`, mints a `RunPlan{plan_hash, pipeline_run_id}`, and calls `evening_workflow` with `data_mode` hard-coded to `"AUTO"` and `evidence_session_date = plan.last_completed_session`.
3. Inside the workflow the **completed-profile stage now runs** (`COMPLETED_PROFILE_STAGE_ENABLED=true`) and Vanguard consumes its evidence through an **unconditional** governed verdict — the five fail-open defaults are gone and an explicit opt-out raises.
4. With no usable profile the book still forms, but every row is `NOT_EVALUATED` / `ready_to_trade=False` / `poc=None`, and the Layer-2 auction component — score **and** the `×0.40` confidence term — is zeroed.
5. The rollback to the MVP-assumed legacy path is a single environment variable, `AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1`.
