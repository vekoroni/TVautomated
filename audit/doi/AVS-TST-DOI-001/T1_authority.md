# T1 — Authority leakage and non-discard (DOI-1; invariants 1–7, 13, 15)

**Objective.** Prove or refute that no automated layer can delete, hide,
permanently invalidate or close a governed opportunity, and that the governed
population is invariant under permutation of EIL, entry, exit, timing, spread,
OI and volume values (the DOI-1 exit criterion).

**Interpreters.** `venv\Scripts\python.exe` (3.13.14) for all execution;
`C:\Python314\python.exe` (3.14.0) for unittest reconciliation only.

---

## T1.1 — Static classification of every authority consumer

`eil_v3_verdict` appears **166 times across 40 files**. Excluding tests,
`audit/`, `backups/`, `_attic/`, `Archive/` and superseded Lab variants
(`intelligence_lab0505.py`, `intelligence_labold.py`,
`intelligence_labolddnu0605am.py`), the live production consumers are:

| Consumer | Hits | Class | Verdict |
|---|---|---|---|
| `eod_candidate_engine.py` | 11 | advisory + **caps population** | see below |
| `execution_intelligence_runner.py` | 22 | producer / advisory | OK |
| `position_sizing_engine.py` | 9 | **sets capital or size field** | **defect** |
| `final_decision_engine.py` | 8 | advisory verdict passthrough | OK |
| `contracts/lab_control.py` | 9 | display / telemetry | OK |
| `trade_book_builder.py` | 2 | **deletes row** (actionable projection) | see below |
| `intelligence-lab/intelligence_lab.py` | 7 | display | T10 |
| `intelligent_orchestrator.py` | 6 | orchestration / telemetry | OK |
| `pipeline_interpreter/*` (3 files) | 6 | projection | T10 |
| `enhancement_integration.py` | 3 | advisory bypass | OK |
| `dropoff_audit.py` | 7 | audit only | OK |
| `morning_validation_engine.py` | 2 | advisory | OK |
| `contracts/handoff_contract.py` | 2 | projection | T10 |

### Positive evidence — the DOI-1 change is real

`eod_candidate_engine.py:3101–3107` carries an explicit DOI-1 comment and
preserves the population:

```python
# DOI-1: EIL is advisory.  Preserve its evidence without altering the
# candidate population.
if "eil_v3_verdict" in out_df.columns:
    _blocked_mask = out_df["eil_v3_verdict"].fillna("").str.upper() == "BLOCKED"
    _blocked_count = int(_blocked_mask.sum())
    if _blocked_count > 0:
        log.info(...)
```

`eod_candidate_engine.py:1696–1698` reduces EIL to a reason string
(`EIL_ADVISORY_{verdict}`) that does **not** touch the score.

`_eod_candidate_status` (`eod_candidate_engine.py:1206`) never returns any of
the three hard-block statuses. Structural and options-route failures are
downgraded to `EOD_DATA_INSUFFICIENT_REVIEW`, and that status **is** a member
of `EOD_CARRY_FORWARD_STATUSES` (`eod_candidate_engine.py:158–172`). A
liquidity state other than `EXECUTABLE_NOW` yields
`EOD_THESIS_READY_REPAIR_AT_OPEN` — a state, not a removal.

### Defect — EIL still reaches a capital field

DOI-1 step 3 required: *"Remove indirect EIL influence from structural tiers,
candidate caps, ranking and capital fields."* This was **not** done for the
position sizing engine.

`position_sizing_engine.py:380–390` converts the EIL verdict into a size
multiplier (docstring: *"Blocked/failed EIL = 0.60x (EOD mode) (not 0.0x).
Unavailable EIL = 0.70x"*), and that multiplier is a term in the multiplicative
sizing chain at `position_sizing_engine.py:673–683`.

`position_sizing_engine.py:283–303` (`_binding_eil_block_reason`) is stronger
still: an `eil_v3_verdict == "BLOCKED"` combined with a failed EIL liquidity
gate returns `FATAL_EIL_BINDING_LIQUIDITY`, and `position_sizing_engine.py:661–671`
turns that into `pse_final_size = 0.0`, `pse_execution_mode = "FATAL_BLOCK"`.
That is an option-liquidity condition setting a capital field to zero —
precisely what invariants 4 and 6 forbid.

**Mitigation, established by me and material to severity.** The binding branch
is gated on `eil_advisory_only` being explicitly false:

```python
if not _is_false(row.get("eil_advisory_only", True)):
    return ""                      # position_sizing_engine.py:287
```

Production sets that flag `True` unconditionally at
`execution_intelligence_runner.py:1345` and `:1814`, and the schema default is
`True` (`execution_schema.py:193`). The binding path is therefore
**unreachable in the current production configuration**. It is a latent
mechanism, not a live one.

**Inconsistent default — the reason this stays P1 rather than P3.**
`trade_book_builder.py:301` reads the same flag with the **opposite** default:

```python
_is_advisory = _b(row, "eil_advisory_only", False)
```

`position_sizing_engine.py` defaults to advisory (safe); `trade_book_builder.py`
defaults to binding (unsafe). Any path that drops the column re-arms EIL as a
gate in one module and not the other. Raised as **DOI-D04** (`AUTH`, P1).

### `trade_book_builder.py` — a projection, not the book

`trade_book_builder.py:289–323` returns `False` for `EXECUTION_SKIP`,
`PSE_FATAL`, `PSE_BELOW_MIN_EXECUTABLE`, `CONV_INSUFFICIENT` and
`DEEPLY_NEGATIVE_EV`. This is row exclusion, but from the **actionable trade
book**, which the design explicitly permits as an actionable-only projection
(DOI-10 acceptance: *"The accepted Interpreter handoff remains
actionable-only"*). It is a defect only if the governed book itself shrinks;
T1.2 and T10 test that. Classified **advisory projection**, no defect.

### Phase 10 — population cap

`eod_candidate_engine.py:3096–3098`:

```python
manifest_df = full_out_df[manifest_mask].copy()
out_df = manifest_df.head(max_candidates).reset_index(drop=True)
```

`full_out_df` retains **every** row with a `phase10_manifest_include` flag and
a `phase10_manifest_exclusion_reason` (`:2867`, `:2882–2886`), and the full
audit CSV is written from `full_out_df` (`:2984`). The `.head(max_candidates)`
cap applies to the morning manifest projection only. Classified **caps
population (projection)** — acceptable under §14 provided the governed book and
Lab retain every row, which T1.2 and T10 test.

---

## T1.2 — Permutation test (the DOI-1 exit criterion)

**Probe:** `audit/doi/AVS-TST-DOI-001/tests/probe_t1_permutation.py`

```
venv\Scripts\python.exe audit\doi\AVS-TST-DOI-001\tests\probe_t1_permutation.py
```

**Input:** the real governed opportunity book from run `20260909_071646`:
`data/output/runs/20260909_071646/intelligence_lab/final_opportunity_book_20260909_071646.csv`,
235 rows × 451 columns.

**Baseline population: 235 — CALL 151 / PUT 84 / OTHER 0.**

### A weak first attempt, recorded because it matters

Version 1 of this probe reported `PASS` with zero rows dropped across 63,450
evaluations. It was **worthless**. All 63,450 evaluations returned a single
status, because the Lab book renames engine fields (`invalidation_price`
against the engine's `invalidation_spot`), so every row exited on the first
early-return branch of `_eod_candidate_status` and the permutation never
reached the EIL, timing or liquidity branches. It was a test that could not
fail — the QT-D01 pattern, committed by me.

Version 2 adds **harness validation before permutation**: field aliases are
mapped, and the recomputed status is checked against the status persisted in
the book. Only reproduced rows are permuted.

```
persisted  eod_candidate_status: EOD_TRIGGER_READY 56, EOD_THESIS_READY_REPAIR_AT_OPEN 179
recomputed eod_candidate_status: EOD_TRIGGER_READY 54, EOD_THESIS_READY_REPAIR_AT_OPEN 181
harness reproduces persisted status for 231 / 235 rows (98.3%)
reproduced CALL/PUT/OTHER: 149 / 82 / 0
```

### Permutation space

Per row: 10 EIL verdicts (including `BLOCKED`, `BLOCK`,
`STAND_DOWN_MICROSTRUCTURE`) × 5 entry/exit/timing states (including
`HORIZON_ELAPSED`, `INVALIDATION_LEVEL_BREACHED`, `TARGET_TOUCHED`,
`ENTRY_CONDITION_MOVED`, applied to 7 timing fields) × 3 liquidity triples
(pristine; wide spread + zero OI + zero volume; all-missing) × 2 advisory-flag
pairs = **300 permutations per row, 69,300 evaluations**.

### Result

| Rows dropped (`phase10_manifest_include` TRUE → FALSE) | CALL | PUT | OTHER |
|---|---|---|---|
| | **0** | **0** | **0** |

Four distinct statuses were reached, **all** in the carry-forward set:

| Status reached | Count | carry_forward |
|---|---|---|
| `EOD_THESIS_READY_REPAIR_AT_OPEN` | 53,130 | True |
| `EOD_TRIGGER_READY` | 15,900 | True |
| `EOD_WATCHLIST_MONETISABLE` | 240 | True |
| `EOD_THESIS_READY` | 30 | True |

Branch coverage **ADEQUATE** (4 statuses, not 1). Invariance **PASS**.

**Result: DOI-1 exit criterion `VERIFIED` at the Phase 10 gate.** This uses a
real run artefact plus source evidence. It does **not** extend to the Lab
projection (T10) or to the sizing/trade-book path (T1.1 above); those are
scoped separately.

### Three-direction asymmetry worth recording

CALL rows reached 4 distinct statuses; PUT rows reached only 2
(`EOD_THESIS_READY_REPAIR_AT_OPEN`, `EOD_TRIGGER_READY`). The two
catalyst-dependent statuses were unreachable for every PUT row in this run.
This is a **coverage** asymmetry in the run's data, not proof of a code
asymmetry, but it means the PUT side of two branches is untested by this
artefact. Raised as **DOI-D05** (`SYM`, P3). Confidence **MEDIUM** — would be
raised by a run containing PUT rows with `DATED_CATALYST_CONFIRMED`.

---

## T1.3 — The four `decision_authority` fields (§6)

§6 requires **every** DOI and Phantom output to carry all four of
`decision_authority`, `can_change_direction`, `can_invalidate_thesis`,
`can_grant_capital`.

Coverage across the eight DOI domain modules:

| Module | `decision_authority` | `can_change_direction` | `can_invalidate_thesis` | `can_grant_capital` |
|---|---|---|---|---|
| `dynamic_options_intelligence.py` | yes | yes | yes | yes |
| `dynamic_options_probability.py` | yes | yes | yes | yes |
| `dynamic_options_ranking.py` | yes | yes | yes | yes |
| `dynamic_options_lifecycle.py` | yes | yes | **missing** | yes |
| `dynamic_options_outcomes.py` | yes | yes | **missing** | yes |
| `contract_family_generation.py` | yes | **missing** | **missing** | **missing** |
| `deterministic_option_valuation.py` | yes | **missing** | **missing** | **missing** |
| `dynamic_options_projection.py` | yes | **missing** | **missing** | **missing** |

No inheritance supplies the gap: each class declares its own fields
(`contract_family_generation.py:68`, `deterministic_option_valuation.py:91,129`,
`dynamic_options_projection.py:48`).

**Strong mitigation.** The persistence layer enforces all four in **SQL**:

```sql
decision_authority    TEXT    NOT NULL CHECK(decision_authority = 'NONE'),
can_change_direction  INTEGER NOT NULL CHECK(can_change_direction = 0),
can_invalidate_thesis INTEGER NOT NULL CHECK(can_invalidate_thesis = 0),
can_grant_capital     INTEGER NOT NULL CHECK(can_grant_capital = 0),
```
`canonical_data/option_liquidity_lifecycle.py:445–448` (`doi_contract_families`)
and the equivalent block on `doi_contract_assessments` (`:457–496`). Database
`CHECK` constraints cannot be bypassed by application code — this is stronger
than a dataclass default.

Where classes do carry the booleans, `__post_init__` raises on any true value
(`dynamic_options_ranking.py:277`, `dynamic_options_probability.py:283,358`,
`dynamic_options_outcomes.py:283`).

The residual gap is the **in-memory Lab/Interpreter payload**:
`domain/dynamic_options_projection.py:89` emits only `doi_decision_authority`,
so a trader reading the projection sees one of the four declarations, not four.
Raised as **DOI-D06** (`AUTH`, P3 — declaration completeness, not live
authority). Confidence **HIGH**.

**Downstream reads.** No consumer branches on these fields to grant authority;
the only reader is the release assessor, which uses them as a violation counter
(`tools/doi11_production_readiness.py:123–132`). Telemetry only, as required.

---

## T1.4 — Macro cannot approve, block or reverse (invariant 2)

Grep for `macro`, `regime`, `risk_off`, `headwind` across all eight DOI domain
modules and all nine DOI `canonical_data` modules returns **exactly one hit**:

```
canonical_data/dynamic_options_probability.py:328:
    "regime": "UNAVAILABLE_NOT_IN_DOI_FEATURE_CONTRACT",
```

Macro is not a feature, not a gate, and not an input anywhere in the DOI path.
Invariant 2 cannot be violated by DOI because macro does not reach it.

Per prompt §7 this is a **positive deviation**: §11.1 *permits* macro as an
advisory explanatory feature, and the code is more conservative than the design
by excluding it entirely. Recorded, not raised as a defect.

**Result: invariant 2 `VERIFIED OFFLINE`.** Confidence **HIGH**. Raised to
`VERIFIED` by a run artefact showing a DOI assessment with no macro field.

---

## T1.5 — No automated exit closes a human-held trade (invariant 15)

- DOI declares the prohibition: `domain/dynamic_options_outcomes.py:211`
  (`can_close_position: bool = False`) with a raising guard at `:283`.
- DOI **never writes to the Decision and Outcome Ledger**: grep for
  `decision_outcome_ledger` across all seventeen DOI modules returns nothing.
- `canonical_data/decision_outcome_ledger.py` exposes only `append` (`:91`) and
  `append_many` (`:135`). There is no update or delete path and no
  `CLOSED` / `close_position` / `auto_close` token in the module.
- The ledger carries `execution_requires_human_approval` (`:334`).

**Result: invariant 15 `VERIFIED OFFLINE`.** Confidence **MEDIUM** — I proved
DOI cannot close a position and the ledger is append-only, but I did not trace
every Exit Discipline Engine output to the ledger, which is outside the DOI
package. Raised to HIGH by a full exit-engine → ledger trace.

**Design/code divergence recorded.** §5.6 makes the Decision and Outcome Ledger
the outcome authority and §17.4 requires that it "receives every candidate
assessment". The implementation places outcome labels in the option-liquidity
control plane instead and writes nothing to the ledger. The DOI-7 acceptance
paragraph describes this openly, so it is a knowing divergence, but it is a
divergence from §17.4. Raised as **DOI-D07** (`DOC`, P3).

---

## T1.6 — Dormant/breached/elapsed acquisition suppression (invariant 13)

`domain/dynamic_options_intelligence.py:81–126` (`decide_observation_acquisition`)
is exactly the design's rule:

| Condition | Decision | Reason |
|---|---|---|
| state `EXPIRED` | no fetch | `CONTRACT_EXPIRED_NO_FETCH` |
| `manual_refresh` | **fetch** | `MANUAL_NEWER_OBSERVATION_REQUESTED` |
| canonical evidence available | no fetch | `REUSE_CANONICAL_EVIDENCE` |
| state `ACTIVE`, evidence missing | fetch | `CANONICAL_EVIDENCE_MISSING` |
| `underlying_reactivated` | **fetch** | `UNDERLYING_PRICE_REACTIVATED` |
| otherwise (dormant/breached/elapsed) | no fetch | `<STATE>_ACQUISITION_SUPPRESSED` |

Suppression is an **acquisition** state and cannot become a removal:
`ObservationAcquisitionDecision.__post_init__` raises
`"observation acquisition cannot remove an opportunity"` if
`retain_opportunity` is false (`:75–76`). The field cannot be set false without
an exception.

### Defect — the reactivation half has no production caller

`underlying_reactivated=True` and `manual_refresh=True` appear **only in
tests** (`tests/test_dynamic_options_observation_bridge.py:156, 162, 244, 289`).
The evening production service calls the bridge with neither, and with
`acquire_missing=None` (`canonical_data/dynamic_options_production.py:202–206`),
so both reactivation branches are unreachable in the live path and there is no
operator entry point for a manual refresh.

Invariant 13's *suppression* half is implemented and live. Its *reactivation*
half exists in code but is dead in production — a dormant or breached ticker
will never re-acquire an option chain, and no operator command can force it.
Raised as **DOI-D08** (`AUTH`, P2). Confidence **HIGH**.

**Result: invariant 13 `PARTIAL`.** Suppression verified offline; reactivation
present in code but production-unreachable.

---

## Track summary

| Claim / invariant | Result | Confidence |
|---|---|---|
| DOI-1 exit: population invariant under permutation (Phase 10 gate) | **VERIFIED** | HIGH |
| Inv. 1 — DOI cannot change direction/target/invalidation | VERIFIED OFFLINE | MEDIUM |
| Inv. 2 — macro cannot approve/block/reverse | VERIFIED OFFLINE | HIGH |
| Inv. 3 — `BLOCKED` cannot delete candidate rows | **VERIFIED** | HIGH |
| Inv. 4 — contract conditions cannot grant capital or discard | **PARTIAL** (DOI-D04) | HIGH |
| Inv. 6 — OI/volume/PCR/entry/exit/timing never deletion gates | **VERIFIED** | HIGH |
| Inv. 13 — dormant visible, suppressed acquisition, reactivation | **PARTIAL** (DOI-D08) | HIGH |
| Inv. 15 — no automated exit closes a human-held trade | VERIFIED OFFLINE | MEDIUM |
| §6 four authority fields on every output | **PARTIAL** (DOI-D06) | HIGH |

Defects raised in this track: **DOI-D04** (`AUTH`, P1), **DOI-D05** (`SYM`, P3),
**DOI-D06** (`AUTH`, P3), **DOI-D07** (`DOC`, P3), **DOI-D08** (`AUTH`, P2).

**No P0 was found in this track.** No path was demonstrated by which an
automated layer deletes, hides, permanently invalidates or closes a governed
opportunity in the current production configuration.
