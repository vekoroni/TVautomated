# Setup (§2.2)

**No `NORMAL_COMPLETED_SESSION` run exists.** Every stored run is TEST condition (see §4); nothing tested on them can be `CLOSED`.

## Resolved runs (head record, §2.2 step 4)

| Item | Value |
|---|---|
| Primary run (latest run_id timestamp) | `20260911_115904` — resolved 2026-09-12 ≈ 20:45 local (Europe/London); no run was written after resolution |
| Comparison runs | `20260910_150045` (stored reference, TEST) plus every other run with full artefacts (25 more); 24 run_ids are 2–4-file stubs (discovery-only or aborted) |
| Total entries in `data\output\runs\` | 49 = 47 timestamped run_ids + `TEST_OLM_REGRESSION_20260829` + empty `latest` |
| Runs with `run_meta.json` | 27; runs with a `final_opportunity_book` | 22 |
| Known reference runs | `20260910_150045`, `20260911_115904` — both forced intra-session, both `git_describe = avs-baseline-20260906-21-g00baa2b-dirty` → TEST by SD §0 rule 2 |

## 1. Git state

| Item | Value |
|---|---|
| HEAD | `cc509cbe7fa60a3fb2f7a37a164a66f27588251d` — 2026-09-12 20:09:10 +0100 `fix(avs-fix-002): govern runtime numeric adapters` |
| `git describe --tags --dirty` | `avs-baseline-20260906-44-gcc509cb` (not dirty) |
| `git status --porcelain` | 5 untracked entries only (`.testdeps/`, `audit/avs_fix_002/policy/.temporary_governance_index`, `audit/avs_fix_002/policy/.temporary_governance_objects/`, `audit/stage6_consolidated.xml`, `audit/worker3_current_state_canary/`); no tracked modifications |
| Baseline tag | `avs-baseline-20260906` = `5e68aca` (2026-09-06 14:43 +0100). 44 commits since; all AVS-FIX-002 commits are dated 2026-09-12 (e6d71df docs 14:36 → 63537f3 provider finality 15:24 → 3e660bd stage 1 16:40 → 9e9604c stages 2–6 19:40 → cc509cb adapters 20:09) |
| Consequence | Both stored reference runs (10 and 11 Sep, commit `00baa2b`) predate every remediation commit. Run-level evidence of any AVS-FIX-002 behaviour cannot exist in stored artefacts; the claim sheets' "stored-run replays" were offline, no-write replays. |

Dirty-tree rule: the stored runs were produced on a dirty tree (`-dirty` in `git_describe`); the current tree at test time is clean.

## 2. `git ls-files --error-unmatch contracts/us_money_index_contract.py macro_domain worker3`

Exit 0. Tracked: `contracts/us_money_index_contract.py` (1), `macro_domain/` (3 files), `worker3/` (37 files). Verification item R4 settled: tracked.

## 3. pytest (full governed matrix including `tests/msi`)

Command: `python tools/run_governed_pytest.py -q tests -p no:cacheprovider --junitxml=audit/td/AVS-TD-001/pytest/junit_full.xml` (Python 3.14 native packages + venv pytest 9.1.1, as the Stage 0 claim sheet prescribes). Started 2026-09-12 19:41:34Z, finished 20:47:41Z (3,961 s).

| Result | Count |
|---|---|
| passed | 1,881 |
| failed | 44 |
| skipped | 4 |
| subtests passed | 285 |
| junit cases (incl. subtests) | 2,214 |

Failures by file (`pytest/failures_list.txt`): `tests/test_lab_strangle_direction.py` 9 · `tests/msi/test_flow.py` 3 · `tests/test_cds2_historical_prices.py` 3 · `tests/msi/test_logic.py` 5 (L01 ×2, L02, L07, L09) · `tests/msi/test_functionality.py` 4 (F04, F05, F08, F10) · `tests/msi/test_regression.py` 3 (R05, R06, R07) · `tests/test_lab_cache_signature.py` 2 · `tests/test_big_bang_phase_6_7.py` 1 · `tests/test_ev3_orchestrator_order.py` 1 · `tests/test_lab_journal_handoff.py` 1 · `tests/test_options_liquidity_morning_lab.py` 1 · others per list.

**Claim-sheet comparison (finding):** Stage 0 claims 1,756 passed / 29 failed / 4 skipped; Stage 1 claims 1,783 / 39 / 4; Stage 6 claims a 425-test consolidated pack with 0 failures. This run: 1,881 / 44 / 4. The passed count is higher (new tests added in stages 2–6) and the failed count is higher than either claim. Track I reconciles the 44 against `BASELINE_DEFECT_REGISTER.md` and states which failures are new since the claims. Recorded in `deviations.md`.

## 4. `run_meta` per run (§2.2 step 5)

REQ-WP0-01 fields required in `run_meta_v2`: `run_condition`, `baseline_eligible`, `code_identity`, `config_identity`, `session_date`, `evidence_cutoff_utc`, `operator_mode`, `provider_completeness_evidence`, `macro_packet_id`. **None of the 27 `run_meta.json` files carries any of these nine fields at top level.** What exists: `run_meta_schema_version = run_meta_v2` (from 20260830_182402 on), `baseline_commit_hash`, `git_describe` (from 20260906_213931 on), `pipeline_mode`, `dynamic_plan.{evidence_cutoff_utc, last_completed_session, plan_hash}` (from 20260906_213931 on), `ddd_runtime_profile.sha256` (a profile hash), `msi_config_hash`, `macro_*` paths, `resolved_feature_flags`.

| run_id | git_describe / commit | pipeline_mode | dynamic_plan.evidence_cutoff_utc | last_completed_session | schema |
|---|---|---|---|---|---|
| 20260723_072618 … 20260830_071747 (14 runs) | ABSENT | (absent) | ABSENT | ABSENT | (none) |
| 20260830_182402 | 5d886f07c1d2 | EOD | ABSENT | ABSENT | run_meta_v2 |
| 20260830_225643 | 5d886f07c1d2 | EOD | ABSENT | ABSENT | run_meta_v2 |
| 20260831_010309 | 5d886f07c1d2 | EOD | ABSENT | ABSENT | run_meta_v2 |
| 20260901_064425 | 5d886f07c1d2 | EOD | ABSENT | ABSENT | run_meta_v2 |
| 20260901_082437 | 5d886f07c1d2 | MORNING_VALIDATION | ABSENT | ABSENT | run_meta_v2 |
| 20260902_232526 | 5d886f07c1d2 | EOD | ABSENT | ABSENT | run_meta_v2 |
| 20260904_004338 | 5d886f07c1d2 | EOD | ABSENT | ABSENT | run_meta_v2 |
| 20260904_122358 | 6e834b838d35 | EOD | ABSENT | ABSENT | run_meta_v2 |
| 20260905_151448 | 6e834b838d35 | EOD | ABSENT | ABSENT | run_meta_v2 |
| 20260906_213931 | avs-baseline-20260906-21-g00baa2b-dirty | EOD | 2026-09-06T21:39:31Z (Sunday) | 2026-09-04 | run_meta_v2 |
| 20260909_071646 | avs-baseline-20260906-21-g00baa2b-dirty | MORNING_VALIDATION | 2026-09-09T07:16:46Z (pre-open) | 2026-09-08 | run_meta_v2 |
| 20260910_150045 | avs-baseline-20260906-21-g00baa2b-dirty | EOD | 2026-09-10T15:00:45Z (intra-session) | 2026-09-09 | run_meta_v2 |
| 20260911_115904 | avs-baseline-20260906-21-g00baa2b-dirty | MORNING_VALIDATION | 2026-09-11T11:59:04Z (pre-open; morning gate ran 17:08Z intra-session) | 2026-09-10 | run_meta_v2 |

Per REQ-WP0-01, every run claimed as normal that lacks these fields fails REQ-WP0-01 before anything else is tested. No run claims to be normal (no `run_condition` field exists), so the verdict is `NOT IMPLEMENTED` at run level; Track A gives the source-level verdict and the inferred condition per run (`run_inventory.csv`).

## 5. Run and artefact inventories (§2.2 steps 6–7)

- `run_inventory.csv` — one row per run with dispatcher anchor, evidence cutoff, session state at cutoff, provider completeness, quote-timestamp distribution, row counts at Discovery / governed book / Lab, recorded and inferred run condition (built by Track A from `probes/p01_run_inventory_raw.csv` and `probes/p10_A_*`).
- `artefact_inventory.csv` — every file the primary run wrote (packages ×1,573 and validation_events ×1,444 collapsed as families), with type, size, record and column counts, production modules mentioning the artefact stem, and the `WRITTEN_UNREAD` / `UNEXAMINED_BY_TEST` flags (finalised in Phase 4 from `probes/p03_artefact_inventory_raw.csv` and the track reports). The same walk was repeated for `20260910_150045` (78 artefacts) so always-written vs conditionally-written artefacts are distinguished: 17 artefacts appear only on the primary run (morning-gate summaries, handoff manifest, interpreter bundles, lab_signal_book_v3 + manifest, execution_actionable/gated, msi diagnostics, score_integrity, validation_events).

## 6. Databases copied (§2.2 step 8)

| Database | Source | Copy | Size |
|---|---|---|---|
| control_plane.sqlite | data/canonical | db_copies/ | 762 MB |
| decision_outcome_ledger.sqlite | data/canonical | db_copies/ | 17.5 MB |
| historical_prices.sqlite | data/canonical | db_copies/ | 1.01 GB |
| run_plans.sqlite | data/canonical | db_copies/ | 57 KB |
| iv_history_cache.db | data/cache | db_copies/ | 2.1 MB |
| trade_journal.db | data/journal | db_copies/ | 1.6 MB |
| phantom_history.db | data/phantom | db_copies/ | 16.8 GB |
| **actuarial DB** | `data/actuarial_db.sqlite` | copied | **0 bytes — ABSENT in effect** (no actuarial database exists; the v7 actuarial cache lives elsewhere as JSON/CSV under `config/`/`data/universe/`) |

All probes open the copies with `?mode=ro`. Schemas and row counts: `probes/p02_db_schema.json`.

## 7. Test files changed since the baseline tag (§2.2 / Rule 7)

`git diff --name-status avs-baseline-20260906..HEAD -- tests/`: 50 added, 25 modified, 0 deleted under `tests/` (14 `_attic/*test*.py` files deleted, out of scope). Modified files:

`tests/fixtures/marketdata/option_chain_list_sizes.json`, `option_quote_crossed.json`, `option_quote_missing_fields.json`, `option_quote_negative_size.json`, `option_quote_scalar_ok.json` (2 lines each); `tests/msi/test_computation.py` (+76), `tests/msi/test_flow.py` (12), `tests/msi/test_functionality.py` (21), `tests/test_avs_sd003_blocker_closure.py` (5), `tests/test_big_bang_phase_6_7.py` (+112), `tests/test_ddd_decision_outcome.py` (9), `tests/test_dynamic_session_phase0.py` (+79), `tests/test_dynamic_session_phase1.py` (12), `tests/test_dynamic_session_phase6.py` (+81), `tests/test_eod_options_research_handoff.py` (17), `tests/test_handoff_contract.py` (14), `tests/test_interpreter_macro_advisory_handoff.py` (48), `tests/test_lab_governed_handoff.py` (51), `tests/test_morning_gate_contract_repair.py` (+5), `tests/test_msi_handoff_materializer.py` (15), `tests/test_msi_interpreter_handoff.py` (9), `tests/test_msi_morning_capture.py` (+1), `tests/test_msi_orchestrator_run_meta.py` (+122), `tests/test_msi_quote_and_size_lineage.py` (17), `tests/test_selected_contract_economics.py` (+3). Totals: 651 insertions, 68 deletions.

The strengthened / neutral / weakened judgement per file, with the specific assertion changed, is in `track_I.md` §"Test edits" and `probes/p17_test_edits.csv`; any weakened assertion is filed as a P1 in `defects.md`.

## 8. Claim sheet resolution

`dropbox\macro\coaching\desk_gate\` contains no claim sheet (`NO_CLAIM_SHEET` at the designated location). Four implementer claim sheets exist under `audit\avs_fix_002\` (stage0, stage1 slice, stages2_5, stage6) and are used as the claim sheets; the location difference is recorded in `deviations.md`. The three design/requirement pointers in desk_gate name v1.1 in the test prompt but point to governed v1.2 copies under `docs\`; v1.2 was used throughout (also in `deviations.md`).

## 9. Environment

Python 3.14.0 (native pandas 2.3.3, numpy 2.3.4, scipy 1.17.0, pyarrow 23.0.0); pytest 9.1.1 via `venv` appended to the path by `tools/run_governed_pytest.py`. 84 GB free on C: at start; 19 GB of database copies written to the output folder.

## 10. Interruptions

The run was interrupted twice by the session usage limit (2026-09-12 ≈ 23:50 and 2026-09-13 ≈ 01:15 local) while track workers were executing; partial track files and probe outputs written before each interruption were retained and the workers were resumed in place. `state_log.csv` records both interruptions.
