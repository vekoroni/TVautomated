# AVS-TST-QT-001 §0A — Build archaeology

**Reconstructed:** 2026-09-06 from the tree, git, backup manifests, release manifests and run artefacts — independently of any claim sheet.
**Reference points:** tag `pre-tidy-20260904` → commit `e183d60` (Fri 08:13 BST); tag `post-tidy-20260904` → commit `6e834b8` (Fri 08:36 BST).
**Machine-readable companion:** `00_changed_files.csv` (299 rows).

---

## 1. The finding that frames everything else

**`HEAD` is `6e834b838d35b6a061df12d44cafff6f72bf0dcb` — the AVS-OPS-001 `.gitignore` commit from Friday 08:36. There have been ZERO commits since.**

```
$ git log --oneline pre-tidy-20260904..HEAD
6e834b8 AVS-OPS-001: ignore scratch, cache and backup patterns
4c33c1c AVS-OPS-001 tidy: move unreferenced root backups ... to _attic/
$ git rev-list --count pre-tidy-20260904..HEAD   ->  2
$ git stash list                                  ->  (empty)
```

Both commits are the Friday-morning root tidy. **Every line of AVS-SD-003 cycle 1, the adapter fix, the five blockers, the integration repair, the DDD production integration and the DDD closure exists only as an uncommitted working-tree modification.** 63 tracked files are modified and 33 paths are untracked.

Three consequences the claim sheets do not state:

1. **No claim sheet's "baseline commit `6e834b8`" distinguishes anything.** Runs `20260904_122358` (IMP-002 code) and `20260905_151448` (DDD-integration code) both record `baseline_commit_hash: 6e834b8`, yet were produced by materially different code. The commit hash cannot identify the code that produced a run — a direct regression against AR-003 P0-01 (reproducible release).
2. **There is no rollback point for the week's work.** `git revert` and `git checkout` cannot reach any intermediate state. The only recovery is the `backups/` directories.
3. **The DDD closure code — the code that would run on Tuesday — has never been committed and has never produced a run** (§5).

The one identity mechanism that *does* work is the runtime-profile hash recorded in `run_meta.json.ddd_runtime_profile.sha256`, which correctly distinguishes the code states (§4).

---

## 2. Change ledger

`00_changed_files.csv`. Excludes `_attic/`, `backups/`, `venv/`, `data/` (except the two phantom staging files), `__pycache__`, `.pytest_cache`.

| Class | All | Production (non-`audit/`) | Tests |
|---|---|---|---|
| MODIFIED | 63 | 63 | 17 |
| ADDED (untracked) | 33 | 30 | 13 |
| MOVED_TO_ATTIC | 34 | 34 | 0 |
| **Total changed** | **299 rows** | **127** | **30** |

### 2.1 Entirely new architectural layer: `domain/`

Ten modules under a new top-level `domain/` package, none of which existed at the tag and none of which appears in any AVS-SD-003 gap register or per-gap specification:

```
domain/decision_outcome.py            domain/market_evidence.py
domain/execution_authority.py         domain/market_structure_evidence.py
domain/long_option_execution.py       domain/option_contract_liquidity.py
domain/option_liquidity_execution_guard.py
domain/run_planning.py                domain/session_authority.py
domain/thesis_direction.py
```

Plus `canonical_data/outcome_maturation.py`, `canonical_data/run_plan_store.py`, `orchestrator/session_authority_adapter.py`, and `contracts/dynamic_session_runtime_v1.json`.

This is the "DDD" (domain-driven design) refactor the 5 Sep documents describe. **It is a structural change of a different order from the AVS-SD-003 gap fixes it was bundled with**, and AVS-SD-003 does not authorise it. Carried to `C_DEVIATIONS.md`.

### 2.2 Changes without a pre-change backup

AVS-SD-002 §16 and the IMP-001 working rules require a pre-change backup. Matching each changed path against every 4–6 Sep backup directory by both relative path and basename:

- **62 production `.py`/`.json` files MODIFIED; 53 have a backup.**
- **9 modified without one — 7 are test files** (§2.3) **and 2 are production:**

| File | Change | Severity |
|---|---|---|
| `contracts/dynamic_session_authority_v1.json` | adds the 9th flag `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED: false` | **LOW** — one line, consistent with the flag contract |
| `canonical_data/request_ledger.py` | 1 insertion | **LOW** |

Both are one-line additions. This is a real but minor process deviation; I am not inflating it. The 25 *new* files without a backup are not violations — a new file has no pre-image to preserve.

### 2.3 Test edits — the number that matters

**17 existing test files were modified.** `AVS-IMP-SD-003-004` admits **one** fixture edit. The remaining 16 are undocumented in the claim sheets.

| Test file | Backup manifest |
|---|---|
| `test_dynamic_session_phase0.py` | ddd_production_integration |
| `test_dynamic_session_phase3.py` | **NONE** |
| `test_dynamic_session_phase4.py` | ddd_closure_prechange |
| `test_dynamic_session_phase6.py` | ddd_closure_prechange |
| `test_cds2_historical_prices.py` | ddd_session_authority |
| `test_eod_options_research_handoff.py` | avs_sd_003_integration |
| `test_ev3_options_handoff.py` | **NONE** |
| `test_execution_monetisability_gate.py` | **NONE** |
| `test_handoff_contract_audit.py` | avs_sd_003_integration |
| `test_lab_governed_handoff.py` | ddd_closure_prechange |
| `test_lab_monetisation_gate.py` | **NONE** |
| `test_msi_handoff_materializer.py` | ddd_production_integration |
| `test_msi_quote_and_size_lineage.py` | ddd_production_integration |
| `test_olm_execution_authority.py` | **NONE** |
| `test_options_liquidity_morning_lab.py` | **NONE** |
| `test_pse_retired_authority.py` | **NONE** |
| `test_ws2_trigger_spine.py` | avs_sd_003_integration |

Classification of each edit is Track C item 5. **One is already confirmed as a weakened protection — §3 below.**

Plus 13 entirely new test files (`test_ddd_*.py` ×9, `test_avs_sd003_*.py` ×3, `test_ddd_production_integration.py`).

---

## 3. The test edit that matters most

`tests/test_dynamic_session_phase0.py`:

```diff
     def test_all_new_features_are_disabled_by_default(self) -> None:
         flags = DynamicSessionFeatureFlags.from_environment({})
         self.assertFalse(any(getattr(flags, field) for field in flags.__slots__))
-        self.assertEqual(len(FEATURE_FLAG_ENV_VARS), 8)
+        self.assertEqual(len(FEATURE_FLAG_ENV_VARS), 9)
```

The test is still named **`test_all_new_features_are_disabled_by_default`** and still passes. It passes because it calls `from_environment({})` — and `contracts/dynamic_session_contract.py:130-134` now branches on exactly that:

```python
configured = (
    load_governed_runtime_profile()["feature_flags"]   # production: no argument
    if environment is None
    else {name: False for name in FEATURE_FLAG_ENV_VARS}   # tests: explicit mapping
)
```

**Production calls `from_environment()` with no argument and gets 8 of 9 flags `true`.** The test exercises the branch that can never run in production and asserts the opposite of production behaviour, under a name that says otherwise.

This is the **third** instance this week of the pattern the brief names — after the Phase 3 adapter tests against mocks and the Phase 4 Vanguard test with `required=True`. It is the most consequential of the three, because the property it falsely certifies is the one the MVP trust boundary rests on.

Filed as **QT-D01, severity P0 (test integrity)**. The code change itself may well be correct and deliberate; the defect is that a test named "disabled by default" is cited in a green count while production defaults are enabled.

---

## 4. Release manifests as drift detectors — and the runtime-profile hash resolved

| Manifest | Pinned files | Match | Mismatch |
|---|---|---|---|
| `AVS-DDD-PRODUCTION-INTEGRATION-20260905/RELEASE_MANIFEST.json` | 9 | 7 | **2** |
| `ddd_closure_20260905/AVS_DDD_CLOSURE_RELEASE_MANIFEST_20260905.json` | 13 | **13** | **0** |

**The live tree matches the DDD-closure release exactly (13/13).**

The two integration mismatches are both explained by closure superseding integration, not by unexplained drift:

| File | Integration pin | Live | Explanation |
|---|---|---|---|
| `contracts/dynamic_session_runtime_v1.json` | `2b416bbe…` | `054a76be…` | v1.0.0 → v1.0.1 at closure |
| `intelligent_orchestrator.py` | `164ec618…` | `e5e1d133…` | changed by the closure |

**Runtime-profile hash question — resolved.** The live file is **`054a76be89b071140911e977ad911432ad46d49433724f52000224b37876bb9d`**, version **1.0.1**, `release_id: AVS-DDD-CLOSURE-20260905`. It is the hash pinned by the **closure** manifest. `2b416bbe…` is the superseded v1.0.0 recorded by the integration manifest, and appears nowhere else in the repository. The integration manifest is stale, not wrong.

### 4.1 What the live runtime profile actually enables

`contracts/dynamic_session_runtime_v1.json`, `status: CONTROLLED_LIVE_CYCLE`:

| Flag | Live value |
|---|---|
| `AVSHUNTER_DYNAMIC_PLAN_ENABLED` | **true** |
| `AVSHUNTER_DYNAMIC_THESIS_ENABLED` | **true** |
| `AVSHUNTER_DYNAMIC_VALIDATION_ENABLED` | **true** |
| `AVSHUNTER_PROFILE_LIFECYCLE_ENABLED` | **true** |
| `AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED` | **true** |
| `AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED` | **true** |
| `AVSHUNTER_DECISION_LEDGER_ENABLED` | **true** |
| `AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED` | **true** |
| `AVSHUNTER_DYNAMIC_AUTO_ENABLED` | false |

**Eight of nine capabilities are enabled in production.** `AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1` forces all nine to `False` (`dynamic_session_contract.py:135-143`) and is the documented rollback. An environment variable may *disable* a governed capability but cannot *promote* one the profile withholds — `:154-157` raises `RuntimeError` — so `AUTO` cannot be switched on by environment alone. That guard is well built.

---

## 5. Run-to-code-state table

| Run | Pinned (UTC) | `baseline_commit_hash` | Runtime profile recorded | Code state | What it can prove |
|---|---|---|---|---|---|
| `20260904_004338` | 09-03 23:43 | `5d886f0` | *(absent)* | pre-build | the original defects (RCA-002) |
| `20260904_122358` | 09-04 11:24 | `6e834b8` | *(absent)* | after IMP-002 | AG-01…AG-10 on the legacy path |
| `20260905_151448` | 09-05 14:15 | `6e834b8` | **`2b416bbe…` v1.0.0 `AVS-DDD-PRODUCTION-INTEGRATION-20260905`** | after DDD integration, **before closure** | the dynamic path's only real output |
| *(after 09-05 22:00)* | — | — | — | **DDD closure** | **DOES NOT EXIST** |

`20260904_001644`, `20260904_115847` and `20260905_135123` have no `run_meta.json` — aborted starts, not runs.

**There is no run under the current code.** Every DDD-closure change — the exclusive-`to` boundary fix, `min_usable_ratio`, `DATA_REPAIR_REQUIRED`, the single `pipeline_run_id`, the immutable build receipt, telemetry split — is `VERIFIED_OFFLINE` at best. The closure's own manifest agrees: it carries a `live_acceptance_remaining` key.

---

## 6. Function-level diff of the decision-bearing modules

Read from the code, not from any note. Full diffs in `00_changed_files.csv`; the decision-critical ones:

### 6.1 The fail-open fix — implemented as designed, and better

| File | Change | Effect |
|---|---|---|
| `vanguard/schemas/input_schema.py` | `market_profile_contract_required: bool = False` → **`True`**; new `VanguardInputError` | default flipped |
| `vanguard/integration/orchestrator_adapter.py:180` | default `True`; explicit `False`/`"0"`/`"no"`/`"off"` now **raises** `VanguardInputError` | opt-out removed, not just re-defaulted |
| `scripts/run_vanguard_from_packages.py:761` | hard-coded `True` with a comment that the contract is a protection, not a capability | — |
| `vanguard/layer1_auction/auction_synthesizer.py:59` | inverted: `if not getattr(..., True): raise`; the governed verdict is now **unconditional** | the legacy fabrication branch is unreachable |
| `vanguard/layer2_statistical/edge_detector.py` | `profile_usable = poc is not None and float(poc) > 0`; gates **both** the `+25/+15/+5` alignment score **and** `auction_conf` (the `×0.40` term) | fabricated profiles score zero |

All five `False` defaults from AVS-RCA-002 §A1.2(b) are gone. This is a complete and correct implementation of AVS-SD-003 §C3 G-02, and it is **verified by run artefact** (§7).

### 6.2 The adapter fixes (AVS-PRE-001 D1–D5)

`canonical_data/marketdata_stock_candles.py` (+187/−11):

- **D1 fixed** `:288-289` — `start_utc.astimezone(NEW_YORK).replace(tzinfo=None).isoformat(timespec="seconds")`. Naked New York wall-clock, exactly what AVS-PRE-001 R2 proved the provider parses.
- **D2 fixed** — `MarketDataCandleNoData` / `MarketDataCandleTransportError` raised from the transport, so the 404 `no_data` shape is now classifiable rather than an unhandled `HTTPError`.
- **D3 fixed** `_segment_for_timestamp(...)` — `session_segment` is now *derived per bar* from the session bounds rather than asserted from the request.
- **D4 fixed** `_header_value(...)` — rate-limit/credit headers are captured.
- **D5** — `provider_http_status` is now carried into the frame and gated on 200–299 by the profile stage.

### 6.3 Governed reason codes

- `scripts/avshunter_options_intelligence.py` (+110/−28): `STRUCTURAL_TARGET_UNRESOLVED`, `INVALIDATION_MISSING` from `DataExceptionReason`.
- `eod_candidate_engine.py` (+90/−11): `NOT_AUTHORIZED_INVALIDATION_MISSING`; new `_eod_dropoff_reason`.
- `contracts/dynamic_session_contract.py`: `DataExceptionReason` gains `INVALIDATION_MISSING`, `STRUCTURAL_TARGET_UNRESOLVED`, `STALE_SOURCE_FALLBACK`; `EvidenceState` gains `APPROVED_FALLBACK`.
- `handoff_contract_audit.py` (**+378/−2**): the semantic rules, including `ARMED_WITHOUT_GOVERNED_INVALIDATION`, `options_to_lab_direction_hash`, and a three-way `EMPTY_BY_DESIGN` / `EMPTY_UNEXPECTED` / `EMPTY_UNCORROBORATED`.

### 6.4 The boundary/threshold change — the closure claim is misdescribed

Diffing the live stage against `backups/ddd_closure_prechange_20260905/scripts/build_completed_market_profiles.py`:

| Constant | Pre-closure | Live | Claimed by closure |
|---|---|---|---|
| per-profile `coverage >=` (`:151`) | **0.95** | **0.95** | "coverage gate 95% → 90%" |
| `first_region and last_region` (`:152-153`) | present | present | — |
| `max_failure_ratio` | 0.05 | 0.05 | — |
| `min_usable_ratio` (`:171`) | **absent** | **0.90 (new)** | — |

**The per-profile coverage gate was not lowered. It is `>= 0.95` before and after.** The `0.90` is a **newly added, stage-level** gate on the *fraction of tickers* yielding usable profiles — a different quantity, and a *stricter* posture, not a weaker one.

The adapter change in the same release is the real fix:

```python
# pre-closure:  "to": end_utc  (naked ET)
# live:         provider_end_utc = end_utc + timedelta(minutes=interval_minutes)
```

**Why 1,491 profiles were PARTIAL, established from the code:** the canonical resolver's range contract is inclusive of both bar *opens*, so it passes `end_utc` = the last expected bar open = **15:55**. MarketData's `to` is exclusive (AVS-PRE-001 R2: `to=16:00` returned exactly the 78 bars 09:30–15:55). Exclusive `to=15:55` therefore returns 09:30–15:50 = **77 bars**, and **`last_region` is `False`** because 15:55 is absent.

`last_region` is a hard `and` in the usability expression. So the profiles failed on the **session-edge test, not on coverage** — at 77/78 = 98.7% they were already far above both 95% and 90%. **Lowering a coverage threshold could not have fixed a single one of them.** The claim sheet's stated rationale for its own change does not hold.

This is pre-registered as expectation `PROF-COV-04` and tested in Track A1.

---

## 7. What the run artefacts already confirm

Run `20260905_151448`, `vanguard_signals_enriched` (1,537 rows), against AVS-RCA-002's baseline of run `20260904_004338` (1,551 rows):

| Property | 20260904_004338 (before) | 20260905_151448 (after) | Gate |
|---|---|---|---|
| `layer1__auction_state = ALIGNED` | **1,068** | **0** | AG-01 **PASS** |
| `layer1__auction_state = NOT_EVALUATED` | 0 | **1,537** | — |
| `layer1__ready_to_trade = True` | 1,068 | **0** | AG-03 **PASS** |
| `layer1__profile__poc == 0.0` | **1,551** | **0** | AG-02 **PASS** |
| `layer1__profile__poc` null | 0 | **1,537** | AG-02 **PASS** |
| `layer1__profile__timeframe` | `intraday` ×1,551 | **`GOVERNED` ×1,537** | governed branch executed |

The Vanguard fail-closed protection is **VERIFIED by run artefact**, not merely offline. This is the single most important thing that went right this week.

### 7.1 But the profile stage produced nothing usable, and said it was fine

`market_profile/completed_profile_summary_20260905_151448.json`:

```
input_count 1587 | completed 0 | deferred 1537 | partial_session_count 1491
provider_no_data 46 | hard_exception 50 | physical_provider_requests 1537
failure_ratio 0.0 | max_failure_ratio 0.05 | systemic_failure false | reconciled true
```

**Zero usable profiles out of 1,587, and the stage reports `systemic_failure: false` with `failure_ratio: 0.0`.** The ratio counts only hard provider failures; the 1,491 partial sessions that made every profile unusable are not in its numerator. The guard cannot fire on a 100 %-unusable outcome. The closure's new `min_usable_ratio=0.90` is precisely the missing gate — but it has never run.

The 50 `DATA_DEFECT` rows carry `ValueError: ATR14 unavailable for governed profile binning`, which is direct evidence for the Track A2 bin-width question.

---

## 8. Worker 3 staging package

`C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\worker3_foundation\` — swept in §1 of Track A8. Isolation confirmed there; no repository file references it and it references no repository module.

---

## 9. §0A required print-out

- **Commits since `pre-tidy-20260904`: 2** — both the Friday root tidy. **Zero commits carry any of the 4–6 Sep build.**
- **Files changed by class (production):** MODIFIED 63, ADDED 30, MOVED_TO_ATTIC 34.
- **Changed without a backup manifest:** 9 modified files — 7 tests, **2 production** (`contracts/dynamic_session_authority_v1.json`, `canonical_data/request_ledger.py`), both one-line additions, severity LOW.
- **Pinned-hash mismatches:** integration manifest 2 of 9 (both superseded by closure); **closure manifest 0 of 13**. Live runtime profile = `054a76be…` v1.0.1.
- **Undocumented production changes:** the entire `domain/` package (10 modules) plus `canonical_data/outcome_maturation.py`, `canonical_data/run_plan_store.py`, `orchestrator/session_authority_adapter.py`; and **16 of 17 test-file edits**.
- **Run-to-code-state:** three real runs; the newest (`20260905_151448`) predates the closure. **No run exists under the current code.**
