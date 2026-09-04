# AVS-RCA-002 Part A — Validation of run 20260904_004338

**Issued:** 2026-09-04
**Run under review:** `data\output\runs\20260904_004338\` (EVENING, session 2026-09-03, `run_status=COMPLETED`)
**Baseline:** `data\output\runs\20260902_232526\` (pre-build)
**Discipline:** read-only. No pipeline execution, no flag set, no production file touched. Every count below was recomputed from artefacts by the scripts in `A_scripts\`; hashes in `environment.json`.
**Machine-readable companion:** `A_counts.csv` (52 claims — 42 CONFIRMED, 6 REFUTED, 4 PARTIAL).

---

## A0. Headline

The build did not fail. **It never ran.**

Every P0 defect the operator observed is a *pre-existing* defect on a code path the build did not modify, protected by fixes that exist but sit behind a flag that was off. The single most important number in this report is this one:

| | 20260902_232526 (pre-build) | 20260904_004338 (post-build) |
|---|---|---|
| Vanguard rows | 1,449 | 1,551 |
| `profile_type=INSUFFICIENT_DATA` | 1,449 (100%) | 1,551 (100%) |
| POC represented as `0.0` | 1,449 (100%) | 1,551 (100%) |
| `auction_state=ALIGNED` on an unusable profile | 995 | 1,068 |
| `layer1__profile__timeframe` | `intraday` ×1,449 | `intraday` ×1,551 |

The post-build run is byte-for-byte the same behaviour as the pre-build run, scaled to a larger discovery population. AVS-SD-002 §21 ("the first production change must be the Vanguard fail-open protection") was not merely delayed — **it was inverted**: the protection was made conditional on the acquisition stage, and the acquisition stage was flagged off.

Three of the operator's specific attributions are wrong and are corrected below (§A1.2, §A2.3, §A4, §A5.2). One prompt expectation is contradicted (§A6.3). Four findings are added that the operator assessment does not contain (§A2.2, §A3.4, §A4.3, §A7.2).

**Classification summary of the confirmed failures**

| Classification | Count | What it means here |
|---|---|---|
| `LEGACY_UNTOUCHED` | 19 | The build did not change this path at all |
| `NEW_CODE_DEFECT` | 6 | New code ran (or was declared) and produced the wrong result |
| `FLAG_OFF` | 4 | The preventing code exists but was not on the executed path |
| `AUDIT_DEFECT` | 2 | The pipeline is right and the report is wrong |
| `EXPECTED_COLD` | 2 | Correct behaviour for a first run against an empty cache |

---

## A1. Market Profile

### A1.1 The artefact and the counts — CONFIRMED

No `market_profile/` directory and no `completed_profile_summary` artefact exist anywhere under the run root; a recursive `-iname "*profile*"` returns zero matches (A1-01). The orchestrator says so itself:

> `2026-09-04 01:13:29,948 - INFO - Phase 4 completed Market Profile integration is built but not yet promoted`

That line is `intelligent_orchestrator.py:2429`, the `else` arm of the `if cfg.COMPLETED_PROFILE_ENABLED:` branch at `:2417`.

From `options\vanguard_signals_enriched_20260904_004338.csv` (1,551 rows), split three ways on `direction`:

| Measure | Total | CALL | PUT | OTHER |
|---|---|---|---|---|
| `layer1__profile__profile_type = INSUFFICIENT_DATA` | **1,551** | 793 | 482 | 141 STRANGLE + 135 UNRESOLVED |
| `layer1__profile__poc == 0.0` (isna = 0) | **1,551** | 793 | 482 | 276 |
| `value_area_high == 0.0`, `value_area_low == 0.0` | **1,551** each | 793 | 482 | 276 |
| `layer1__migration__direction = SIDEWAYS` | **1,551** | 793 | 482 | 276 |
| `INSUFFICIENT_DATA` **and** `auction_state = ALIGNED` | **1,068** | 547 | 319 | 112 + 90 |
| `layer1__ready_to_trade = True` | **1,068** | 547 | 319 | 112 + 90 |

`ready_to_trade=True` falls on exactly the 1,068 `ALIGNED` rows. Both AR-003 Wave 3 exit-gate clauses are breached simultaneously: *"No daily-only `ALIGNED`"* (1,068 violations) and *"no missing-as-zero"* (1,551 violations — a missing POC is published as the number `0.0`, which is a price).

**Independent proof that the governed code never executed.** `layer1__profile__timeframe` is `intraday` on 1,551/1,551 rows. That string is written only at `auction_synthesizer.py:82`, inside the legacy multi-session fabrication branch. The governed branch writes `f"{interval_minutes}min_{evidence_state}"` (`:166`) or the literal `"GOVERNED"` (`:211`). Neither appears once. This is stronger evidence than any log line: the new code left no fingerprint in the output.

### A1.2 The three questions the operator's diagnosis conflates

**(a) Which flag gates the completed-profile *acquisition stage*? — `AVSHUNTER_DYNAMIC_THESIS_ENABLED`. Operator CONFIRMED.**

```
intelligent_orchestrator.py:440-442
    COMPLETED_PROFILE_ENABLED = os.environ.get(
        "AVSHUNTER_DYNAMIC_THESIS_ENABLED", "0"
    ).strip().lower() in {"1", "true", "yes", "on"}
```

Read at `:973` (preflight requires the script only when enabled) and at `:2417` (the `--evening` VANGUARD pipeline). The comment above it states the intent explicitly — *"Do not introduce a second, orphaned switch for the same capability"* — so this coupling is deliberate, not accidental.

Two structural notes. First, it is read **in a class body at import time**, so it cannot be toggled per invocation and is invisible to `DynamicSessionFeatureFlags`; this matches the finding at `AVS-TST-SD-002-001\T0_evidence_integrity.md:171`. Second, `AVSHUNTER_PROFILE_LIFECYCLE_ENABLED` — the flag whose *name* suggests it owns this — does not gate it. Its only read in the entire repository is `intelligent_orchestrator.py:6399`, inside a block guarded by `AVSHUNTER_DYNAMIC_PLAN_ENABLED` at `:6346`. Setting it alone changes nothing on the `--evening` path (A1-11).

**(b) Which flag gates the Vanguard fail-open protection? — None. REFUTED, and this is the central architectural finding.**

The protection is not flag-gated at all. It is gated by a **data-plane boolean**:

```
vanguard/layer1_auction/auction_synthesizer.py:59-64
    if getattr(vanguard_input, "market_profile_contract_required", False):
        return self._governed_profile_verdict(...)
    #  ... otherwise fall through to the legacy fabrication branch at :66-144
```

Trace the boolean end to end:

| Step | File:line | Behaviour |
|---|---|---|
| Only producer of `True` | `scripts\build_completed_market_profiles.py:159`, `:166` | Stamps `market_profile_contract_required: True` on every package — with evidence at `:159-160`, with `None` evidence at `:166-167` |
| That script only runs when | `intelligent_orchestrator.py:2417` | `cfg.COMPLETED_PROFILE_ENABLED` (i.e. `AVSHUNTER_DYNAMIC_THESIS_ENABLED`) |
| Package → Vanguard input | `scripts\run_vanguard_from_packages.py:761` | `bool(pkg.get("market_profile_contract_required", **False**))` |
| Adapter | `vanguard\integration\orchestrator_adapter.py:180` | `bool(payload.get("market_profile_contract_required", **False**))` |
| Schema | `vanguard\schemas\input_schema.py:211` | `market_profile_contract_required: bool = **False**` |
| Consumer | `auction_synthesizer.py:59` | `getattr(..., **False**)` |

**Five independent defaults, all `False`, all fail-open.** With the flag off, the fail-closed verdict `_not_evaluated()` at `:201-227` — which correctly emits `auction_state="NOT_EVALUATED"`, `ready_to_trade=False`, `poc=None` — is *unreachable*. It is dead code in production.

This is a category error in the design, not a bug in the code. A protection whose default is "unprotected" is not a protection; it is a capability. AVS-SD-002 §21 asked for the protection **first**; the build delivered it **last and conditionally**.

**(c) Were §21 and the Wave 3 exit gate satisfied by a flag-gated implementation? — No. REFUTED.**

- AVS-SD-002 §21 (line 854): *"The first production change must be the Vanguard fail-open protection."* The first production change was in fact nothing: the run's Vanguard output is identical in kind to the pre-build baseline.
- AR-003 Wave 3 exit gate (line 595): *"No daily-only `ALIGNED`; no missing-as-zero; population reconciliation exact."* Two of three clauses fail (1,068 and 1,551 violations). Only population reconciliation passes.
- AR-003 line 673: *"No daily-only or unusable profile can yield `ALIGNED` or readiness."* 1,068 unusable profiles yielded both.

`AVS-AR-003_P0_RECERTIFICATION_20260903.md:13` records P0-02 as `CLOSED OFFLINE` with the rationale *"unavailable profiles remain null/`NOT_EVALUATED`; no profile-derived readiness."* That statement is true of `_governed_profile_verdict`/`_not_evaluated` and false of the production run. See §B2.

### A1.3 The full flag set — eight, and two were never named

`contracts\dynamic_session_contract.py:144-153` and `contracts\dynamic_session_authority_v1.json:17-24` agree on exactly eight, all defaulting to `False`. The full mapping is `B_flag_topology.csv`; the correction here is:

- **`AVSHUNTER_COMPLETED_PROFILE_ENABLED` does not exist** (A1-07). It appears in the prompt's §7 Option 2 and in the operator's shorthand, but nowhere in the repository. Any design that names it is unbuildable. The two flags actually in play are `AVSHUNTER_DYNAMIC_THESIS_ENABLED` (acquisition, and transitively the protection) and `AVSHUNTER_PROFILE_LIFECYCLE_ENABLED` (dynamic-plan path only).
- The prompt's premise that `AVSHUNTER_DYNAMIC_THESIS_ENABLED` is "the eighth the closures never named" is correct, and `AVS-TST-SD-002-001\T0_evidence_integrity.md:159` reached the same conclusion first, adding that `AVSHUNTER_PROFILE_LIFECYCLE_ENABLED` is *also* undocumented in the closures. Two of eight, not one.

### A1.4 Counterfactuals

| Flag set | What happens on the `--evening` path |
|---|---|
| `AVSHUNTER_PROFILE_LIFECYCLE_ENABLED=1` only | **Nothing changes.** Not read on this path. Vanguard still emits 1,551 `INSUFFICIENT_DATA` / 1,068 `ALIGNED` (A1-11). |
| `AVSHUNTER_DYNAMIC_THESIS_ENABLED=1` only | The profile stage runs at `:2417`. It stamps `market_profile_contract_required=True` on **every** package (`:159` when evidence is usable, `:166` when it is not), so `auction_synthesizer.py:59` takes the governed branch for **all** rows. Tickers with usable evidence get `PROFILE_CONTEXT_ONLY` (`ready_to_trade=False`, real POC/VAH/VAL); tickers without get `NOT_EVALUATED` (`ready_to_trade=False`, POC `None`). Zero rows can be `ALIGNED` on a fabricated profile. **This is the desired end-state** (A1-12). |

One material warning attaches to the second row: `_run("Build Completed Market Profiles", ..., critical=True)` at `:2427` means a stage failure **aborts the whole Evening run**. Turning this flag on without a degradation policy converts a data-quality problem into a total-outage problem. C2 and C7 must address this.

### A1.5 Layer 2's contribution — quantified

```
vanguard/layer2_statistical/edge_detector.py:552-554
    def _calculate_right_side_score(self, state, outcomes, auction):
        score = 50.0
        if auction.auction_state == "ALIGNED":
            score += 25
```

Unconditional. No profile-usability guard. So **all 1,068** rows received the +25 (547 CALL / 319 PUT / 112 STRANGLE / 90 UNRESOLVED), every point of it derived from a profile whose POC is `0.0` (A1-13).

Reach into the delivered book (A1-14):

| Vanguard `auction_state` of the source ticker | Lab rows | CALL | PUT |
|---|---|---|---|
| `ALIGNED` (carried the fabricated +25) | **174** | 118 | 56 |
| `TRANSITIONING` (+15) | 82 | 46 | 36 |
| **Total** | **256** | 164 | 92 |

**68.0% of the 256-row book carries a score contribution sourced from a fabricated profile.** This is the quantified blast radius of P0-02 and the reason G-01/G-02 rank above everything else in Part C.

---

## A2. Invalidation geometry

All four of the operator's numbers are **CONFIRMED** — 173 / 24 / 13 / 36 — though one required correcting the field the operator named. A fifth number, not in the assessment, is worse than any of them.

### A2.1 The four numbers

**173 directional Options rows with a missing stop (A2-01).** Two independent filters agree exactly. `final_direction ∈ {CALL,PUT}` and `invalidation_spot` blank = 173. And the pipeline's own state column, `invalidation_state == "MISSING"`, = 173. Three-direction split:

| `invalidation_state` | CALL | PUT | STRANGLE | UNRESOLVED |
|---|---|---|---|---|
| `AVAILABLE` | 655 | 436 | 0 | 0 |
| `MISSING` | **137** | **36** | 0 | 0 |
| `NOT_APPLICABLE` | 0 | 0 | 141 | 49 |

The `OTHER` direction handling is correct and should be protected as a regression baseline: all 190 non-directional rows are `NOT_APPLICABLE`, not `MISSING`.

**24 of 256 Lab candidates without an invalidation price (A2-03).** `invalidation_price` blank = 24, **all CALL**, 0 PUT, 0 OTHER. The same 24 tickers are blank on `invalidation_spot` in the Morning candidate file. Their disposition:

| `eod_candidate_status` | with invalidation | without |
|---|---|---|
| `EOD_THESIS_READY_REPAIR_AT_OPEN` | 142 | **20** |
| `EOD_TRIGGER_READY` | 88 | **4** |
| `EOD_THESIS_READY` | 2 | 0 |

**23 of the 24 carry `options_research_permission = EXECUTABLE_SUBJECT_TO_GATES`.**

**13 still granted `EOD_CANDIDATE_ONLY` (A2-04) — CONFIRMED after a field correction.** `EOD_CANDIDATE_ONLY` is *not* a value of `eod_candidate_status`; that column takes only the three values above, in both the Lab and Morning files. It is a value of `capital_permission`, `capital_authorization_state` and `live_capital_permission` in `morning_candidates_20260904_004338.csv`. On that column the operator's number is exact:

| `capital_permission` | with invalidation | without |
|---|---|---|
| `EOD_CANDIDATE_ONLY` | 118 | **13** |
| `WATCH_ONLY` | 98 | 8 |
| `NO` | 16 | 3 |

The same 13 rows carry `eod_candidate_authorized = True`. All 13 are CALL.

**36 PUT rows raised `float - NoneType` (A2-05).** `stand_down_reason` contains `unsupported operand type` on exactly 36 rows, **all PUT**. Every one has `structural_target` NaN and `invalidation_spot` NaN.

### A2.2 The finding the assessment missed — 43 rows ARMED with no stop

`options_verdict == "ARMED"` **and** `invalidation_state == "MISSING"` = **43 rows, all CALL** (A2-02). Of the 242 ARMED rows in the run, 199 have invalidation and 43 do not.

**15 of those 43 reach the Lab book**, all with `invalidation_price` blank and all with `options_research_permission = EXECUTABLE_SUBJECT_TO_GATES`.

This is more serious than the 36 crashes, and it inverts the usual reading of the run. The PUT crash was not a failure of safety — *it was the only thing that stopped a PUT row from being armed without a stop.* All 36 PUT missing-invalidation rows are `STAND_DOWN` **because** the exception fired. The 137 CALL missing-invalidation rows had no such accident, so 43 of them were armed. The system has no invalidation-presence precondition on arming at all; it has a `TypeError` that happens to fire on one side.

### A2.3 The `float - NoneType` expression, and why it is not a PUT problem

```
scripts/avshunter_options_intelligence.py:5433-5471
    target = ctx['structural_target']                      # :5435  — may be None
    ...
    if direction == 'CALL':
        target_gain_underlying = max(target - entry, 0)     # :5464
        option_value_at_target = max(target - strike, 0)    # :5465
    elif direction == 'PUT':
        target_gain_underlying = max(entry - target, 0)     # :5467  ← the observed crash
        option_value_at_target = max(strike - target, 0)    # :5468
```

**Three-direction analysis (A2-07).** The exposure is *identical* in both branches — neither guards `target` for `None`. Only the operand order differs, and therefore only the message differs:

- CALL `:5464` → `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'`
- PUT `:5467` → `TypeError: unsupported operand type(s) for -: 'float' and 'NoneType'`

The observed message is the **PUT** operand order, which is why the failure looks PUT-specific. It is not. Blank `structural_target` by direction: **CALL 12, PUT 42, STRANGLE 141, UNRESOLVED 49**. The 12 blank-target CALL rows simply never reached `compute_trade_economics` — 11 were stood down at `"No contract passed quality gates"` and one at a chain-fetch failure. **The CALL crash was masked by chance, not prevented by a guard.** A future run whose contract-quality gates pass for one of those 12 will crash on the CALL side.

**Why `structural_target` is `None` (A2-08).** The fallback ladder at `:4138-4158`:

1. `discovery_target` — accepted only if `> entry` for CALL, `< entry` for PUT
2. `l1_far` — same direction gate
3. CALL: `target_3r`  |  PUT: `entry - 3*stop_dist`
4. else `None`

And at `:4041-4051`:

```
stop_dist = abs(entry - stop) if stop is not None else None    # :4041
target_3r = entry + 3 * stop_dist if stop_dist is not None else None   # :4045 (CALL)
target_3r = entry - 3 * stop_dist if stop_dist is not None else None   # :4048 (PUT)
```

**The root cause is the missing stop, not the direction.** `stop is None` → `stop_dist is None` → rung 3 yields `None` → rung 4 yields `None` → the unguarded subtraction. G-05 is a *symptom* of G-03, which is why Part C sequences them together.

The direction asymmetry is in rungs 1–2, not in the arithmetic: discovery targets and L1 far triggers are upside levels, so they satisfy the CALL gate (`> entry`) far more often than the PUT gate (`< entry`). PUT therefore falls through to the stop-dependent rung 42 times against CALL's 12. Fix the stop and both counts go to zero; guard the subtraction and neither can crash.

### A2.4 "Safely stood down" — PARTIAL (A2-06)

The 36 rows are stood down and they *are* labelled. They carry `invalidation_state = MISSING`, `options_verdict = STAND_DOWN`, `trigger_state = NO_TRIGGER`, `contract_repair_status = CONTRACT_REPAIR_REQUIRED`. To that extent the operator is right.

But this is **a swallowed exception with a default status, not a governed exception record**. Both `stand_down_reason` and `trigger_status_reason` contain, verbatim, on all 36 rows:

> `Unhandled exception: unsupported operand type(s) for -: 'float' and 'NoneType'`

A raw CPython interpreter message is published into a trader-facing field. There is no `UNRESOLVED_EXCEPTION` state and no reason code drawn from `DataExceptionReason` (`contracts\dynamic_session_contract.py:70-86`), which already contains suitable members. The distinction matters operationally: a governed defer is countable, alertable and gate-able; a stringified `TypeError` is none of those.

### A2.5 Which guard was on the executed path — neither (A2-09)

No invalidation-presence precondition exists on any `EOD_*` status assignment in `eod_candidate_engine.py`; the 24 blank-invalidation rows were graded on `eod_candidate_status` alone. The Phase 5 *"explicit defer on missing decision-critical data"* recertified against P0-07 sits behind `AVSHUNTER_DYNAMIC_VALIDATION_ENABLED` (`AVS-SD-002_PHASE5_CLAIM_20260903.json:8`), which was off. Classification: `FLAG_OFF`. The recertified behaviour is real; it is simply unreachable from `--evening`.

---

## A3. Quote lineage — CONFIRMED, with the boundary identified for each field

The precondition first (A3-04): the fields **do** exist upstream with real values for the Lab tickers, so this is a handoff-contract defect and not a data-availability one. Restricting the Options file to the 256 Lab tickers gives `contract_bid_size` 241/256, `contract_ask_size` 241/256, `contract_quote_timestamp_utc` 241/256, `l2_bid_size`/`l2_ask_size` 241/256. And the transport demonstrably works: `quote_as_of` (241), `contract_bid`/`contract_ask` (241) and `selected_quote_dataset_id` (211) survive all three boundaries intact. Specific fields are omitted; the pipe is not broken.

**Boundary map (non-blank counts; `—` = the column does not exist at that stage):**

| Field | Options (of 256) | Morning (of 256) | Lab (of 256) | Boundary that drops it | Defect shape |
|---|---|---|---|---|---|
| `contract_bid_size` | 241 | — | **0** | Options → Morning | allow-list omission |
| `contract_ask_size` | 241 | — | **0** | Options → Morning | allow-list omission |
| `contract_quote_quality` | 241 | — | **0** | Options → Morning | allow-list omission |
| `selected_quote_timestamp_utc` | — | — | **0** | no producer emits this name | **rename** |
| `execution_viability_state` | — | **256** | **0** | Morning → Lab | **allow-listed but unmapped** |
| `execution_viability_reason` | — | 256 | 0 | Morning → Lab | allow-listed but unmapped |
| `execution_viability_eligible` | — | 256 | 0 | Morning → Lab | allow-listed but unmapped |
| `execution_viability_bid/ask/spread_pct/policy_version` | — | 234 | 0 | Morning → Lab | allow-listed but unmapped |
| `underlying_nbbo_bid_size` / `_ask_size` | — | — | 0 | no producer | rename / orphan column |
| *(control)* `quote_as_of` | 241 | 241 | **241** | — | survives |
| *(control)* `contract_bid` / `contract_ask` | 241 | 241 | **241** | — | survives |
| *(control)* `selected_quote_dataset_id` | 211 | 211 | **211** | — | survives |

**Three distinct defect shapes, requiring three distinct fixes.**

1. **Bid/ask sizes — allow-list omission at Options → Morning (A3-01).** Options writes the values; the EOD candidate projection never emits the columns; so `contracts\lab_control.py:2070` — `first(sig, "contract_bid_size", "live_contract_bid_size")` — is asked to read from a row that has neither name and correctly resolves to empty. The Lab mapper is innocent; the producer's projection is at fault.

2. **`selected_quote_timestamp_utc` — a rename with no mapping (A3-02).** `contracts\lab_control.py:2065` accepts only `selected_quote_timestamp_utc` or `contract_quote_timestamp`. Options actually writes three other names: `contract_quote_timestamp_utc`, `quote_timestamp_utc`, `l2_quote_timestamp_utc` (241/256 each). Note that `eod_candidate_engine.py:879` *does* construct `"selected_quote_timestamp_utc": quote_timestamp` — into a dict that is never projected into the candidate CSV. The value is computed and thrown away.

3. **`execution_viability_*` — allow-listed but unmapped at Morning → Lab (A3-03). `NEW_CODE_DEFECT`.** This one is the clearest. The whole family is present and complete in `morning_candidates_20260904_004338.csv` (256/256 for `state`, `reason`, `eligible`; 234/256 for the price fields) and 0/256 in the Lab. The names are declared in the `lab_control.py` allow-list at `:256-265` — but there is **no corresponding `first(sig, ...)` assignment** in the row builder. The schema promises the column, the writer never fills it, and the reader sees a fully-populated column of nulls. This is the F29 `live_map`-only shape the prompt anticipated, in its purest form: the contract was tested, the writer that populates it was not.

---

## A4. Monetisability — the seven are real; "undisclosed" is REFUTED

**The seven are confirmed (A4-01).** `BAND, AMAT, WDC, CRDO, KLAC, NVTS, KTOS` carry `monetisability_reason = EOD_ASK_STRIKE_OR_TARGET_MISSING`; every numeric `monetisability_*` field is `NaN`. **All seven are PUT**, and all seven have `monetisability_structural_target_spot` NaN — *the same root cause as §A2.3*. The monetisability gap and the economics crash are the same defect wearing two faces.

**The disclosure claim is REFUTED (A4-02).** The rows do not present as if evaluated. Each carries a correctly named absence state:

```
monetisability_status  = FAILED
monetisability_state   = DATA_MISSING
monetisability_reason  = EOD_ASK_STRIKE_OR_TARGET_MISSING
monetisability_eligible = False
```

Per AR-003 §7.10 the evaluation is advisory and the defect would be disclosure — but disclosure is present. What the operator identified as seven undisclosed rows is in fact **22 correctly disclosed rows**:

| `monetisability_state` | rows | reason |
|---|---|---|
| `MONETISABLE` | 110 | `TARGET_CLEARS_BREAKEVEN_AND_PROFIT_FLOOR` |
| `NOT_MONETISABLE` | 105 | `STRUCTURAL_TARGET_DOES_NOT_CLEAR_BREAKEVEN` |
| `DATA_MISSING` | **22** | 15 `SELECTED_CONTRACT_MISSING` + **7** `EOD_ASK_STRIKE_OR_TARGET_MISSING` |
| `LIMITED` | 19 | `POSITIVE_TARGET_PROFIT_BELOW_MINIMUM` |

Per the prompt's own instruction — *"If a §3 claim is `REFUTED`, say so in Part A and omit it from the design"* — the "undisclosed monetisability" gap is **withdrawn**. The prompt's provisional G-07 does not survive Part A in the form stated.

**A residual disclosure gap does survive, and it is different (A4-03).** `monetisability_authority` is **null on 256/256 rows** — including all 110 `MONETISABLE` ones. AR-003 §7.10 makes this evaluation advisory; the field that would say so is empty on every row in the book. `monetisability_calculation_version` is likewise NaN on the 22 `DATA_MISSING` rows. This is the real, narrower G-07 that Part C carries forward.

---

## A5. Performance and cache

### A5.1 Ledger reconciliation — exact

For `run_id = 20260904_004338`, `api_request_ledger` contains **2,528 rows, all `stage = OPTIONS`, all `dataset_type = OPTION_CHAIN`**:

| Reason | Rows | `physical_request_count` |
|---|---|---|
| `no fresh canonical coverage` | 1,264 | 0 |
| *(blank — successful fetch)* | 1,261 | 1,261 |
| `ValueError:MarketData option chain unavailable for {AEBI, DEC, NLST}` | 3 | 3 |
| **Total** | **2,528** | **1,264** |

Provider: `MARKETDATA` on 1,264 rows, `NULL` on the 1,264 resolution rows. **Zero Polygon rows.** `dataset_registry` holds 1,261 `OPTION_CHAIN` datasets for the run.

So the reconciliation the design wants — *physical = ledger `PROVIDER_FETCH` rows* — **already holds exactly** for option chains: 1,264 = 1,264. The operator's 1,261 is the count of *successfully registered* datasets; physical calls were 1,264 (A5-01, PARTIAL).

### A5.2 Zero cache hits is correct — REFUTED as a defect (A5-02, A5-03)

The cache is not broken. It demonstrably works for this very dataset type:

| Run | Session | exact fresh dataset | partial coverage | physical |
|---|---|---|---|---|
| 20260828_094349 | 2026-08-28 | **941** | 0 | 86 |
| 20260829_222259 | 2026-08-28 | **1,971** | 963 | 984 |
| 20260831_010309 | 2026-08-28 | 86 | 0 | 853 |
| **20260904_004338** | **2026-09-03** | **0** | 0 | 1,264 |

The difference is the chain session, and it is dispositive. `scope_json` pins `start_date = end_date = 2026-09-03`; `dataset_registry` records `session_date = 2026-09-03` for this run and `2026-09-02` for `20260902_232526`. **The number of instruments registered for session 2026-09-03 by any other run is zero.** No identical dataset existed. A chain for a different session is a different dataset, not a cache miss.

Classification: **`EXPECTED_COLD`**. The operator's suspicion that identical datasets already existed is **REFUTED**. G19 remains the right gate, but it must be a *same-session* rerun, not a comparison against the previous night.

### A5.3 A real cache-identity defect does exist (A5-04)

While zero reuse was correct here, the identity key is not stable enough to guarantee reuse when it *should* occur:

- `scope_fingerprint` for `OPTION_CHAIN` is **one constant per run** (1 distinct value across 1,261 rows), and it **changes between runs of the same session**: session 2026-08-28 carries `9a6428e8…` (2 runs), `ce80bb29…` (1 run) and `f6680964…` (3 runs). The likely cause is `dte_min`/`dte_max` in `scope_json` being *relative* quantities frozen into an *absolute* fingerprint, so the same logical scope hashes differently on a different calendar day.
- **`expires_at` is `NULL` for 100% of 11,248 `dataset_registry` rows.** There is no TTL anywhere in the registry.

Both must be specified before G19 can be a meaningful gate. See G-08.

### A5.4 Runtime and size

**Runtime (A5-05): 4h 03m 44s** from run pin (`00:43:48`) to `EVENING WORKFLOW COMPLETE` (`04:47:22`); 4h 30m 37s from orchestrator entry. "~4 hours" CONFIRMED. Two stages consume 55% of it:

| Stage | Window | Duration |
|---|---|---|
| Actuarial cache + transition matrix | 00:16:45 → 00:20:08 | 3m 23s |
| Discovery ULTIMATE | 00:20:08 → 00:43:40 | 23m 32s |
| Build Packages | 00:50:46 → 00:56:42 | 5m 56s |
| Inject Macro | 00:56:45 → 01:01:13 | 4m 28s |
| Backfill Timeseries | 01:01:13 → 01:13:29 | 12m 16s |
| *(completed-profile stage — SKIPPED, flag off)* | 01:13:29 | 0s |
| Trap-to-Launch | 01:13:29 → 01:24:49 | 11m 20s |
| **VANGUARD** | 01:24:49 → 02:36:17 | **71m 28s** |
| **Options Intelligence** (1,264 chain fetches) | 02:36:28 → 03:47:25 | **70m 57s** |
| EV-1.5 + EV-3 | 03:47:42 → 03:50:27 | 2m 45s |
| Actuarial Enrichment | 03:50:27 → 04:02:42 | 12m 15s |
| Phantom scoring | 04:02:42 → 04:12:09 | 9m 27s |
| Trigger Layer | 04:12:17 → 04:34:14 | 21m 58s |
| Superbrain / Wall Break / WS2 | 04:34:14 → 04:37:19 | 3m 05s |
| EIL | 04:37:19 → 04:39:54 | 2m 35s |
| Q-Omega GARCH | 04:41:24 → 04:43:53 | 2m 29s |
| EOD candidates → Lab → finalisation | 04:43:53 → 04:47:22 | 3m 29s |

**Size (A5-06, A5-07): 2.846 GB (2.651 GiB) across 1,675 files**, against the baseline's 2.648 GB (2.466 GiB) across 1,569 files. The operator quoted GiB; both figures agree once the unit is reconciled. Growth is **+0.198 GB / +106 files**, of which **87.5% is `packages\`** (2,322.7 → 2,495.8 MB, 1,496 → 1,602 files). Every other directory moves by less than 11 MB.

**Attribution: the growth is the discovery population, not new output.** Packages scale one-per-candidate and discovery selected 1,601 against 1,496. The build produced no measurable new artefact — which is the size-domain restatement of §A0.

---

## A6. The audit defect

### A6.1 The rule — CONFIRMED (A6-01)

The run's `FAIL` comes from exactly one place. `handoff_contract_audit_20260904_004338.json` records `overall_status: FAIL`, `fail_count: 2`, and both failures are the shadow book:

```
stage: shadow_book, field_contract: ticker,                   row_count: 0, fill_rate: 0.0, severity: FAIL, status: LOW_FILL_RATE
stage: shadow_book, field_contract: shadow_opportunity_score, row_count: 0, fill_rate: 0.0, severity: FAIL, status: LOW_FILL_RATE
```

The rule is `handoff_contract_audit.py:476-484`:

```python
present, filled, rate = _fill_rate(df, list(contract["aliases"]))
if not present:                                        status = "MISSING_COLUMN"
elif row_count > 0 and filled == 0:                    status = "PRESENT_BUT_EMPTY"
elif rate < 0.05 and contract["severity"] == "FAIL":   status = "LOW_FILL_RATE"
else:                                                  status = "OK"
```

The `row_count > 0` guard on line 479 was evidently added to stop empty frames being flagged — but it routes them into the *harsher* branch instead. A zero-row artefact can never reach `PRESENT_BUT_EMPTY`; it falls through to `LOW_FILL_RATE`, which is `FAIL` severity, which sets `overall = "FAIL"` at `:504-506`. There is no `EMPTY_BY_DESIGN` state anywhere in the module.

The severity is also **inverted**: a shadow book that is *entirely missing* scores `WARN` (`:455`, which explicitly softens `morning_validation` and `shadow_book`), while one that is present and correctly empty scores `FAIL`.

### A6.2 The emptiness was intentional — CONFIRMED (A6-02)

`eod_candidate_engine.py:2827-2833`:

```python
shadow_mask = (
    (score_series >= 40)
    & (~status_series.isin(execute_statuses_for_shadow)
       | (cap_applies & (rank_series > max_candidates)))
)
```

From `eod_dropoff_audit_20260904_004338.csv` (the full 1,454-row frame the mask is applied to): **81 rows score ≥ 40** (max 57). Every one of the 81 carries a carry-forward status — 41 `EOD_THESIS_READY_REPAIR_AT_OPEN` and 40 `EOD_TRIGGER_READY` — so `~status_series.isin(...)` is `False` for all of them.

The second disjunct cannot rescue them either: `max_candidates` defaults to `0` and the docstring at `:1908` reads *"0 means no cap"*, so `cap_applies = bool(max_candidates and max_candidates > 0)` at `:2826` is `False` and the `rank > max` clause is dead. The mask therefore selects nothing. **Nothing was missed, which is precisely why the book is empty.** (This also establishes that the 256-row book is the output of the candidate filter, not a cap.)

Two corroborations. The 78 `WATCH_FOR_REGIME_FLIP` rows were correctly diverted to `regime_watch_20260904_004338.csv` (78 rows, exact match). And the three `REVIEW_FALSE_NEGATIVE` rows — KMPR, OXY, QCOM, all at score 57 — were all carried forward as candidates rather than dropped. The shadow book is `EMPTY_BY_DESIGN` in the strict sense: the population it exists to catch was empty.

### A6.3 Re-scoring — and a material disagreement with the prompt (A6-03)

`status_counts` for the run: `{OK: 158, PRESENT_BUT_EMPTY: 1, LOW_FILL_RATE: 2, EXPECTED_NOT_RUN_EOD: 1}`.

Reclassify the two `LOW_FILL_RATE` rows as `EMPTY_BY_DESIGN` and `fail_count` becomes **0**. The only remaining non-OK finding is one `WARN` (`options_hard_vetoes` `PRESENT_BUT_EMPTY` on the candidate file). By `:504-506`, `overall` becomes **`WARN`**.

The prompt states: *"state whether `FAIL` still stands on the genuine findings alone (it will, if A1–A3 confirm)."* **It will not, and this is the most important thing Part A has to say about the audit layer.**

A1, A2 and A3 all confirm. And the handoff audit **does not contain a single rule that detects any of them**. It has no rule for `INSUFFICIENT_DATA` coexisting with `ALIGNED`; none for a missing POC published as `0.0`; none for `ARMED` with `invalidation_state = MISSING`; none for a candidate status granted without an invalidation price; none for an allow-listed Lab column that is 0/256 while its Morning source is 256/256. Fixing A6-01 in isolation would take a run carrying three P0-class defects and **turn it green**.

The run's genuine degradation was in fact recorded elsewhere and by a different mechanism — `final_run_manifest.json` sets `pipeline_semantic_health: "DEGRADED"`, `semantic_defect_count: 136`, `stale_flags: ["SEMANTIC_HANDOFF_DEFECTS:136"]` — but `pipeline_technical_health: "PASS"` and `run_health_score: 91`. Two audit systems, neither of which sees the actual P0s.

Therefore the `EMPTY_BY_DESIGN` fix **must not ship alone**. It ships with the A1–A3 detection rules, or the audit layer regresses. This is G-09 plus a new G-12 in Part C, and it is why C6 sequences them together.

---

## A7. The positives — the regression baseline

These are confirmed with the same rigour and are the properties C4 must protect. Five hold outright; two need qualification.

**Confirmed without qualification**

- **Discovery reconciles exactly (A7-01).** 3,320 = 1,601 selected + 1,719 excluded. `dropoff_audit_20260904_004338.json` `dropoff_stage_counts` sums to 3,320 (241 + 245 + 968 + 97 + 50 + 1,719); the discovery CSV has 1,601 rows; the orchestrator's `post_discovery_pin` checkpoint at 00:43:50 records the same split.
- **Direction populations (A7-03, A7-04).** Options 792 CALL / 472 PUT / 141 STRANGLE / 49 UNRESOLVED — identical across `final_direction`, `governed_direction` and `canonical_direction`. Lab 164 CALL / 92 PUT. (Note: the Vanguard-stage `direction` column reads 793 / 482 / 141 / 135; direction is legitimately re-governed at the Options stage, so the two need not match.)
- **Governed hold periods (A7-05).** 194 at `1_5d`, 62 at `6_10d`, zero null; `hold_period` and `hold_window` agree row-for-row.
- **Lab population reconciles (A7-07).** 256 in, 256 out, 256 unique `trade_idea_id`, 256 unique tickers, and `set(Lab.ticker) == set(Morning.ticker)`.
- **Morning execution permission withheld (A7-08).** `morning_execution_permission` null 256/256; `prep_permission = MANUAL_REVIEW_MORNING_VALIDATION` 256/256; manifest `run_execution_permission = MORNING_VALIDATION_REQUIRED`. Correct pre-Morning-Gate behaviour.

**Direction lineage — the strongest positive in the run (A7-09).** Joining the Options and Lab files on ticker (256 rows): `final_direction` matches **256/256**, and `governed_direction_record_sha256` matches **256/256**, with both sides non-null on every row. `governed_direction_records_20260904_004338.jsonl` carries 1,454 records, one per Options row. Every Lab row's direction is traceable to a governed decision with a matching hash. This is the property the whole book rests on and it is intact.

**Where the non-directional rows went (A7-10).** All 190 STRANGLE/UNRESOLVED rows are `options_verdict = STAND_DOWN` with `invalidation_state = NOT_APPLICABLE`, and **zero** reach the Lab. Correct on both counts — `NOT_APPLICABLE` is the right invalidation state for a non-directional thesis, and the OTHER direction is properly excluded from a long-single-leg book.

**Needing qualification**

- **MarketData usage (A7-02) — PARTIAL.** "Zero Polygon fallbacks" is true **for option chains only**. Polygon remains the primary bar provider for Discovery: `2026-09-04 00:20:12 — Polygon API initialized (UNLIMITED)`. And at 00:43:44: *"39 tickers (1.2%) used stale cached bar data (Polygon fetch failed — prices may not be EOD)."* Those Discovery calls do not appear in the ledger at all (see §B4).
- **Macro advisory (A7-06) — PARTIAL, and it conceals a defect of the same shape as A3.** Only **5 of 24** `macro_*` columns are populated on the Lab book: `macro_authority` (`MACRO_ADVISORY_ONLY`), `macro_data_role` (`ADVISORY_ONLY`), `macro_regime` (`TRANSITIONAL`), `macro_freshness`, `macro_data_quality` — each 256/256. The other **19 are 0/256**, including `macro_plain_language_advisory`, every `macro_*_context` field, `macro_directional_pressure`, `macro_conflicts`, `macro_event_guards`, and — most seriously — the macro lineage identity fields `macro_packet_id`, `macro_packet_sha256`, `macro_source_fingerprint`, `macro_as_of_utc`, `macro_session_date`.

  This differs in kind from A3: these are not fields dropped in transit but **columns declared in the Lab schema that no upstream stage ever produces** (they are `ABSENT` in both the Options and Morning files, not merely blank). The authority stamps are genuine; the advisory content and its provenance are not there. Carried into Part C as **G-11**.

---

## A8. Findings added beyond the operator assessment

| # | Finding | Evidence | Gap |
|---|---|---|---|
| 1 | **43 Options rows `ARMED` with `invalidation_state = MISSING`** (all CALL); 15 reach the Lab as `EXECUTABLE_SUBJECT_TO_GATES` | A2-02 | G-03 (raises severity to P0) |
| 2 | **The CALL branch carries the identical `None`-target exposure**; the 12 exposed rows were saved by unrelated quality gates, not by a guard | A2-07, `avshunter_options_intelligence.py:5464` | G-05 |
| 3 | **`monetisability_authority` null 256/256** — the advisory-only stamp AR-003 §7.10 requires is missing on every row | A4-03 | G-07 (restated) |
| 4 | **19 of 24 `macro_*` Lab columns are 0/256**, including all macro lineage identity fields | A7-06 | **G-11 (new)** |
| 5 | **The handoff audit has no rule that detects A1, A2 or A3**; correcting A6-01 alone turns the run green | A6-03 | **G-12 (new)** |
| 6 | **`scope_fingerprint` is unstable across runs of the same session**; `expires_at` NULL on 100% of the registry | A5-04 | G-08 |
| 7 | **The completed-profile stage runs `critical=True`** — enabling it converts a data-quality failure into a total Evening outage | A1-12, `intelligent_orchestrator.py:2427` | C2 / C7 constraint |
| 8 | **Discovery's provider calls are unledgered**; 39 tickers silently substituted stale bars | B4-01, B4-02 | G-13 (new) |

---

## A9. Verdict

The technical `PASS` is accurate and irrelevant. The semantic `FAIL` is correct by accident — it fires on the one thing that was working (§A6) and is blind to the three things that were not (§A1, §A2, §A3).

Nothing in Part A supports re-opening the accepted architecture. `_governed_profile_verdict`, `_not_evaluated`, the typed evidence contract, the governed direction record and the `DataExceptionReason` vocabulary are all present and correct. The distance to close is not design distance. It is the distance between **implemented behind a flag** and **firing in production** — and, in the case of the Vanguard fail-open, between a protection and a capability.

Parts B and C proceed on the confirmed gaps only. The two `REFUTED` claims — `AVSHUNTER_COMPLETED_PROFILE_ENABLED` as a flag (A1-07), and undisclosed monetisability (A4-02) — are excluded from the design, and the `EXPECTED_COLD` cache result (A5-03) is designed against as a *gate specification*, not as a defect.
