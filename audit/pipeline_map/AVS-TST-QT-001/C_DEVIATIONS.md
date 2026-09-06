# AVS-TST-QT-001 Track C — Deviation register

Every place where the implemented state departs from an accepted design or a binding instruction. Confirmed or refuted from the tree, not from claim sheets.

---

## D-01 — The production path is now the dynamic dispatcher — **CONFIRMED**

`AVS-SD-003 §C2` recommended Option 1: unflag the *protections*, keep *new acquisition* flag-gated, and carry the MVP on the legacy `--evening` path. `AVS-MVP-001 §2` assumes the same. Neither holds.

**Evidence.** `intelligent_orchestrator.py:6632` — `if dynamic_requested or runtime_flags.plan_engine:`. `runtime_flags` comes from `DynamicSessionFeatureFlags.from_environment()` with no argument, which loads `contracts/dynamic_session_runtime_v1.json` where `AVSHUNTER_DYNAMIC_PLAN_ENABLED: true`. **`--evening` therefore always enters the dispatcher, and the legacy `elif args.evening` branch at `:6733` is unreachable.**

**Which capabilities are enabled:** 8 of 9 — plan engine, thesis builder, validation gate, profile lifecycle, Lab dynamic view, Interpreter dynamic resolver, decision ledger, completed-profile stage. Only `AUTO` is withheld.

**Does any of them write to a decision-critical field?** Yes, and this is the material part:
- `COMPLETED_PROFILE_STAGE` writes `market_profile_evidence` and `market_profile_contract_required` into every package — the input Vanguard's entire verdict rests on.
- `DYNAMIC_VALIDATION` owns the Morning validation events that carry `execution_viability_state` into the Lab.
- `DECISION_LEDGER` writes an append-only record but grants no authority.
- `LAB_DYNAMIC_VIEW` / `INTERPRETER_DYNAMIC_RESOLVER` are presentation-side.

**Are the §4 MVP filter fields still produced with the same names and semantics?** **Yes — verified on run `20260905_151448`.** All twelve named fields are present and populated at the rates in `D_MVP_READINESS.md` §2, with one exception: `contract_dte` does not appear in the Lab book under that name, so the §4 clause "DTE ≥ 2 × planned hold" cannot be evaluated from the book as written.

**Risk.** Moderate and mitigated. The dispatcher path demonstrably produces a *better* book than the legacy path did (Track B). But the MVP was scoped against a path that no longer runs, and the rollback (`AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1`) has itself never been exercised in production.

---

## D-02 — Coverage gate 95% → 90% — **REFUTED as described; the claim misstates its own change**

DDD-closure claim 5 says the coverage gate was lowered from 95 % to 90 % after a run produced 77/78 frames.

**Evidence.** Diffing `scripts/build_completed_market_profiles.py` against `backups/ddd_closure_prechange_20260905/`:

| Constant | Pre-closure | Live |
|---|---|---|
| per-profile `coverage >=` (`:151`) | **0.95** | **0.95** — unchanged |
| `first_region and last_region` (`:152-153`) | present | present |
| `min_usable_ratio` (`:171`) | **absent** | **0.90 — new** |

The per-profile gate was never lowered. The `0.90` is a **new stage-level gate on the fraction of tickers** yielding usable profiles — a different quantity, and a *stricter* posture.

**And the stated rationale does not hold either.** Test `PROF-COV-04` (`A_logic_tests/test_a1_profile_coverage.py`) shows a 77/78 frame fails under **both** a 0.95 and a 0.90 coverage gate, because `last_region` is a hard `and` and 15:55 is the missing bar. At 98.7 % coverage no coverage threshold could have rescued it. The real fix was the exclusive-`to` `+1 interval` in the same release.

**Confirmed on real data:** the 1,491 persisted `INTRADAY_BAR` payloads from run `20260905_151448` run **09:30 → 15:50** (AAPL: 77 bars, step exactly 300 s), i.e. the 15:55 bar is absent — exactly the off-by-one predicted from the code.

**Risk.** Low as implemented, high as documented. The code is now more conservative than before; the claim sheet describes a weakening that did not occur, which would mislead anyone auditing from documents. → **QT-D08**.

---

## D-03 — Runtime-profile hash drift — **REFUTED (explained supersession)**

The integration manifest pins `2b416bbe…`; the closure manifest pins `054a76be…`. **The live file is `054a76be…`, v1.0.1, `release_id: AVS-DDD-CLOSURE-20260905`.**

The closure manifest matches the live tree on **13 of 13** pinned files. The integration manifest mismatches on 2 of 9 — `dynamic_session_runtime_v1.json` (v1.0.0 → v1.0.1) and `intelligent_orchestrator.py` — both superseded by the closure. `2b416bbe…` appears nowhere except the integration manifest and the tester prompt. **This is stale documentation, not drift.**

Note the one place it matters: run `20260905_151448` records `ddd_runtime_profile.sha256 = 2b416bbe…`, correctly identifying that it ran under the *integration* release. That mechanism works and is the only reliable code-identity signal in the artefacts (see D-08).

---

## D-04 — `tests\msi\` excluded from every acceptance count — **CONFIRMED, and it hides real failures**

`tests/msi/` holds 5 files: `test_computation.py`, `test_flow.py`, `test_functionality.py`, `test_logic.py`, `test_regression.py`. They are excluded by every acceptance count cited this week — **including my own AVS-OPS-001 130-file matrix**, which globbed `tests/test_*.py`, `tests/qa/` and `tests/rca/` only. I am reporting a gap in my own prior work.

**What the pack asserts** — precisely the Market Profile arithmetic that nothing else covers:
`test_hand_computed_atr14_two_tick_sizes`, `test_round_to_tick_rounds_to_nearest_not_floor`, `test_c05_tpo_participation_counts_one_per_period_per_bin`, `test_c06_value_area_expands_from_poc_to_next_higher_adjacent_count`, `test_c07_one_minute_volume_uniformly_allocated_and_labelled`, plus quote-mid and VWAP contracts.

**Running it (isolated process):** `test_computation.py` → **2 failed, 27 passed, 3 subtests passed**.

| Failure | Reading |
|---|---|
| `test_quote_change_computation_is_not_implemented_anywhere_NOT_IMPLEMENTED` | an "assert the absence" test that now fails because the capability *was* implemented — the test is stale, not the code |
| `test_c07_one_minute_volume_uniformly_allocated_and_labelled` | a genuine Market Profile volume-allocation assertion failing |

`test_logic.py` exceeded my time budget — **BLOCKED — budget**.

**Verdict:** not a deliberate way to keep a green number — several tests are self-documenting `*_FINDING` markers, which is a legitimate if unusual pattern — but the effect is the same. **The Market Profile arithmetic has been unverified in every acceptance count this week, and the pack contains a live failure.** It should be in the matrix.

**One useful side-effect:** `test_c06_value_area_expands_from_poc_to_next_higher_adjacent_count` **passes**, which arbitrates my own QT-D05 disagreement in production's favour — the value area expands to the higher adjacent count, which is exactly `if above >= below: high += 1`. QT-D05 is therefore most likely a defect in *my* independent implementation, and is recorded at P3 for arbitration rather than asserted against production.

---

## D-05 — Test edits — **CONFIRMED, 16 undocumented**

**17 existing test files were modified** since `pre-tidy-20260904`. `AVS-IMP-SD-003-004` admits **one** fixture edit. Seven changed with no pre-change backup manifest.

Classified per `AVS-TST-SD-002-001 §T2`:

| File | Class | Note |
|---|---|---|
| `test_dynamic_session_phase0.py` | **PROTECTION_WEAKENED** | see below — the most serious edit of the week |
| `test_dynamic_session_phase3.py` | OBSOLETE_ASSERTION_CORRECTED | adapter contract changed by the D1 fix |
| `test_dynamic_session_phase4.py` | OBSOLETE_ASSERTION_CORRECTED | `required=True` default flip |
| `test_dynamic_session_phase6.py` | OBSOLETE_ASSERTION_CORRECTED | flag-name assertion |
| `test_handoff_contract_audit.py` | OBSOLETE_ASSERTION_CORRECTED | new semantic rules |
| `test_lab_governed_handoff.py`, `test_msi_handoff_materializer.py`, `test_msi_quote_and_size_lineage.py` | FIXTURE_CORRECTED | lineage fields now populated |
| `test_olm_execution_authority.py` | FIXTURE_CORRECTED | the 5 failures I found in AVS-OPS-001 |
| remaining 8 | UNRELATED / FIXTURE_CORRECTED | not individually re-verified — **BLOCKED — budget** |

### The one that matters: `test_dynamic_session_phase0.py`

```diff
     def test_all_new_features_are_disabled_by_default(self) -> None:
         flags = DynamicSessionFeatureFlags.from_environment({})
         self.assertFalse(any(getattr(flags, field) for field in flags.__slots__))
-        self.assertEqual(len(FEATURE_FLAG_ENV_VARS), 8)
+        self.assertEqual(len(FEATURE_FLAG_ENV_VARS), 9)
```

The test still passes and is still named *"all new features are disabled by default"*. It passes because `from_environment({})` takes the explicit-mapping branch that hard-codes all-`False` (`contracts/dynamic_session_contract.py:132-134`). **Production calls `from_environment()` with no argument and gets 8 of 9 enabled.**

This is the **third** instance this week of a test passing while the property it names is false in production — after the Phase 3 adapter tests against mocks and the Phase 4 Vanguard test with `required=True`. It is the most consequential of the three because the property is the MVP trust boundary itself. → **QT-D01, P0 (test integrity)**.

The *code* change is defensible: a governed, hash-pinned, single-file runtime profile with a documented one-variable rollback is a better mechanism than nine loose environment variables. The defect is that a green count containing this test is cited as evidence that flags are off.

---

## D-06 — "CLOSED OFFLINE" used as a status — **CONFIRMED, but materially improved**

`AVS-SD-003 §C8` and the 4 Sep policy require a run-artefact count before `CLOSED`. IMP-002/003 use `CLOSED OFFLINE`.

**Which have since acquired a run artefact** (Track B, run `20260905_151448`): AG-01, AG-02, AG-03, AG-05, AG-07, AG-08, AG-09, AG-10, AG-11 (viability + sizes), RG-02, RG-05, RG-07 — **twelve gates are now VERIFIED by run artefact**, not offline.

**Still offline-only:**
- everything introduced by the DDD closure — `min_usable_ratio`, exclusive-`to`, `DATA_REPAIR_REQUIRED`, single `pipeline_run_id`, immutable build receipt, telemetry split (**QT-D14**);
- AG-13 `monetisability_authority` — 0/294, so it is neither closed nor closable (**QT-D07**);
- the warm-cache gate G19/AG-20 from AVS-SD-003 — no same-session rerun exists.

---

## D-07 — Worker 3 built against an unlocatable design — **CONFIRMED, no production reach**

`AVS-W3-SD-001` **does not exist as a file** in either the repository or the staging package. Searched both trees for `*W3-SD*` / `*AVS-W3*` — no match. It exists only as a Codex task response, per the brief.

**Isolation is real and I verified it in both directions:**
- No module under `worker3_foundation/worker3/` imports any repository module (`domain.py:1` states the property; a scan for `AVSHUNTER|intelligent_orchestrator|canonical_data|market_structure|vanguard|contracts.|morning_gate|sys.path` finds nothing).
- **0 tracked repository files reference `worker3`.**
- Its suite runs entirely inside its own directory: **263 passed + 183 subtests in 21.98 s**, reproduced by me.
- Its output carries `authority: ADVISORY_ONLY`, `calibrated: False`, `phase: NOT_ASSIGNED`, and its own limitations list disclaims Wyckoff phase labels.

**Would the README's "next slice" cross the AR-003 §7.14 Interpreter authority boundary?** §7.14 requires the production Interpreter to consume the handoff only — no provider calls, no direction or contract changes, no capital grant. `SLICE13_OFFLINE_INTEGRATION.md` and `SLICE10_LIVE_AI.md` describe live-AI and offline-integration slices. **A live-AI slice that reached the Interpreter surface would cross that boundary**, because it would introduce a provider call behind a read-only presentation layer. Today it does not — the package cannot publish and is unreferenced. Flagged for the design decision, not as a current defect.

**Live transport:** not attempted, per the brief. The prior 401 is a credentials matter for the operator.

---

## D-08 — `.venv` points to a removed interpreter — **REFUTED as stated; a different, milder issue exists**

There is **no `.venv` directory**. The repository has `venv/`, which works — every test in this report ran through `venv/Scripts/python.exe` (Python 3.13.14, pytest 9.1.1).

`venv/pyvenv.cfg` reports `version = 3.13.9` and `home = …WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0`, i.e. a Windows Store Python, while the venv actually runs 3.13.14. A Store-app base interpreter is a genuine reproducibility weakness against P0-01 — it is user-scoped, auto-updating, and not pinnable — but it is not "removed", and nothing is broken.

**Related and more serious: QT-D02.** The real P0-01 regression is that **nothing is committed**. Two runs record the same `baseline_commit_hash` while being produced by different code; only the runtime-profile hash distinguishes them, and only for DDD-era runs.

---

## D-09 — An unauthorised architectural layer — **CONFIRMED (new)**

A new top-level `domain/` package of 10 modules (`session_authority`, `run_planning`, `thesis_direction`, `market_evidence`, `market_structure_evidence`, `option_contract_liquidity`, `option_liquidity_execution_guard`, `long_option_execution`, `execution_authority`, `decision_outcome`) plus `canonical_data/outcome_maturation.py`, `canonical_data/run_plan_store.py` and `orchestrator/session_authority_adapter.py`.

None appears in the `AVS-SD-003 §C1` gap register or `§C3` per-gap specifications. `AVS-SD-003` authorises bounded changes to named modules to close eleven gaps; this is a domain-driven-design refactor of a different order, bundled into the same uncommitted working tree.

**Risk:** the gap fixes and the refactor cannot be reverted independently, because neither is committed. → **QT-D11**, and it compounds **QT-D02**.
