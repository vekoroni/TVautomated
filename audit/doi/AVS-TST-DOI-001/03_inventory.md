# 03 — Inventory and baseline (Track T0)

## T0.1 Git baseline

| Item | Value |
|---|---|
| `git rev-parse HEAD` (start) | `00baa2b0c4b12125a6ad4753910ea73bb6eb6a32` |
| Branch | `avs-fix-001` |
| Main branch | `master` |
| Tags matching `avs-` | `avs-baseline-20260906` (one only) |
| `git status --porcelain` line count (start) | **306** |
| Untracked files excluding `audit/`, `backups/`, `__pycache__` (`-uall`) | **103** |
| Modified tracked files | **34** |

### Is the DOI work committed?

**No. Not one line of the DOI implementation is committed.** `git ls-files`
matched against `doi` or `dynamic_options` returns nothing outside
`backups/`, `_attic/` and `_cleanup_holding/`. Every DOI source module,
every DOI test, the design document itself and the runtime config are
untracked (`??`).

This is a direct recurrence of **QT-D02** (runs that cannot identify their
code). Tonight's evening run, if it executes DOI, will produce artefacts whose
code cannot be identified by any commit, tag or content hash recorded in git.
The DOI-11 claim that a "release manifest" and "rollback point" are recorded is
true only for the database file; the *code* has no version identity.

Raised as **DOI-D01** (`LIN`, P1).

### Modified tracked production files (34)

DOI touched these existing files. Of interest for later tracks:

```
canonical_data/__init__.py                     canonical_data/contracts.py
canonical_data/decision_outcome_ledger.py      canonical_data/option_liquidity_lifecycle.py
contracts/handoff_contract.py                  contracts/interpreter_handoff.py
contracts/interpreter_handoff_materializer.py  contracts/lab_control.py
contracts/lab_evidence_overlay.py              domain/__init__.py
eod_candidate_engine.py                        execution_intelligence_runner.py
intelligence-lab/intelligence_lab.py           intelligence-lab/static/index.html
intelligent_orchestrator.py                    pipeline_interpreter/evidence_resolver.py
pipeline_interpreter/pipeline_interpreter_commands.py
pipeline_interpreter/prepare_interpreter_session.py
scripts/avshunter_options_intelligence.py      tools/msi_production_readiness.py
```

Plus 9 modified tracked **test** files, examined in T12.3. Note that several of
these modifications belong to the earlier AVS-FIX-001 / MSI / macro work rather
than to DOI; attribution is done in T12.3.

## T0.2 Module → phase map

All DOI source is untracked. 7,682 lines across 19 files.

| Phase | Module | Lines | Role |
|---|---|---|---|
| DOI-1 | `contracts/dynamic_options_policy.py` | 50 | Authority policy constants |
| DOI-1 | `tests/test_dynamic_options_non_discard_policy.py` | — | Non-discard policy tests |
| DOI-2 | `domain/dynamic_options_intelligence.py` | 618 | Core domain objects, vocabularies, authority block |
| DOI-2 | `canonical_data/dynamic_options_lifecycle.py` | 453 | Append-only persistence, DOI table DDL |
| DOI-3 | `canonical_data/dynamic_options_bridge.py` | 710 | Canonical observation bridge, reuse-first, PCR scoping |
| DOI-4 | `domain/contract_family_generation.py` | 184 | Structural exclusions, family generation |
| DOI-4 | `canonical_data/dynamic_options_family.py` | 492 | Family persistence / taxonomy |
| DOI-5 | `domain/deterministic_option_valuation.py` | 401 | Dividend-adjusted BS, Greeks, scenario grid |
| DOI-5 | `canonical_data/dynamic_options_valuation.py` | 417 | Assessment persistence |
| DOI-6 | `domain/dynamic_options_lifecycle.py` | 572 | States, transitions, hysteresis, supersession |
| DOI-7 | `domain/dynamic_options_outcomes.py` | 607 | Outcome labels, no-lookahead, cohorts |
| DOI-7 | `canonical_data/dynamic_options_outcomes.py` | 272 | Label persistence |
| DOI-8 | `domain/dynamic_options_probability.py` | 420 | Logistic baseline, Platt calibration, gates |
| DOI-8 | `canonical_data/dynamic_options_probability.py` | 759 | Model/inference persistence |
| DOI-9 | `domain/dynamic_options_ranking.py` | 658 | Ranker, policy, fallback |
| DOI-9 | `canonical_data/dynamic_options_ranking.py` | 312 | Ranking/policy persistence |
| DOI-10 | `domain/dynamic_options_projection.py` | 134 | Lab/Interpreter projection domain |
| DOI-10 | `canonical_data/dynamic_options_projection.py` | 115 | Projection resolver |
| DOI-11 | `canonical_data/dynamic_options_production.py` | 282 | Evening orchestration service |
| DOI-11 | `tools/doi11_production_readiness.py` | 226 | Read-only release assessor |
| DOI-11 | `config/doi_runtime.json` | — | Runtime switches |

### `domain/` package and QT-D11

QT-D11 previously flagged `domain/` as an unauthorised package. **DOI extended
that pattern substantially**: eight new modules totalling 3,594 lines were added
to `domain/`, and `domain/__init__.py` was modified. DOI did not create the
pattern but it is now the largest single occupant of the package. Raised as
**DOI-D02** (`DOC`, P3) — a governance/ownership observation, not a functional
defect.

## T0.3 Regression pack count — the 115 / 120 claim

**Selector used:**

```
venv/Scripts/python.exe -m pytest --collect-only -q \
  tests/test_doi10_projection_integration.py \
  tests/test_doi11_production_integration.py \
  tests/test_doi_phase_quality_assurance.py \
  tests/test_dynamic_options_contract_family.py \
  tests/test_dynamic_options_deterministic_valuation.py \
  tests/test_dynamic_options_domain_persistence.py \
  tests/test_dynamic_options_lifecycle.py \
  tests/test_dynamic_options_non_discard_policy.py \
  tests/test_dynamic_options_observation_bridge.py \
  tests/test_dynamic_options_outcomes.py \
  tests/test_dynamic_options_probability.py \
  tests/test_dynamic_options_ranking.py
```

**Result: 124 tests collected. 124 passed in 56.56s.**

| File | pytest |
|---|---|
| `test_doi10_projection_integration.py` | 8 |
| `test_doi11_production_integration.py` | 5 |
| `test_doi_phase_quality_assurance.py` | 3 |
| `test_dynamic_options_contract_family.py` | 7 |
| `test_dynamic_options_deterministic_valuation.py` | 14 |
| `test_dynamic_options_domain_persistence.py` | 11 |
| `test_dynamic_options_lifecycle.py` | 16 |
| `test_dynamic_options_non_discard_policy.py` | **4** |
| `test_dynamic_options_observation_bridge.py` | 14 |
| `test_dynamic_options_outcomes.py` | 16 |
| `test_dynamic_options_probability.py` | 13 |
| `test_dynamic_options_ranking.py` | 13 |
| **Total** | **124** |

### Reconciliation to the claimed 120

I reproduced the claimed 120 exactly, and in doing so found what it excludes.

`audit/doi/DOI_PHASE10_IMPLEMENTATION_20260910.md:60` states "the active Python
has no `pytest`". I confirmed this: `C:\Python314\python.exe -m pytest` →
*No module named pytest*. The pack was therefore run with `unittest`:

```
C:\Python314\python.exe -m unittest discover -s tests -p "test_dynamic_options_*.py"   -> Ran 104 tests, OK
C:\Python314\python.exe -m unittest discover -s tests -p "test_doi*.py"                -> Ran  16 tests, OK
                                                                                          104 + 16 = 120
```

The claimed 120 is exactly this union. The 4-test gap between 124 and 120 is
**not** rounding and is **not** spread across files. It is one whole file:

`tests/test_dynamic_options_non_discard_policy.py` contains four **module-level
pytest-style functions**, not `unittest.TestCase` methods:

```
tests/test_dynamic_options_non_discard_policy.py:29  def test_policy_assigns_human_only_execution_authority()
tests/test_dynamic_options_non_discard_policy.py:38  def test_eil_block_is_disclosure_not_veto()
tests/test_dynamic_options_non_discard_policy.py:49  def test_handoff_preserves_go_with_eil_advisory_block()
tests/test_dynamic_options_non_discard_policy.py:62  def test_eil_verdict_does_not_change_eod_tier_or_score()
```

`unittest` cannot see them:

```
C:\Python314\python.exe -m unittest tests.test_dynamic_options_non_discard_policy
   -> Ran 0 tests in 0.000s / NO TESTS RAN
```

So the "120 passed / 0 failed" evidence on which DOI-11 acceptance rests
**silently executed zero of the four tests that guard the non-discard principle
(§1.1) and invariants 3, 4 and 6** — the single most important behaviour in the
design and the reason the design exists.

Mitigating fact, established by me: all four **do pass** under pytest (part of
the 124/124). So this is a defect in the acceptance *evidence*, not a hidden
functional failure. It is nonetheless the QT-D01 pattern again — an acceptance
number that reads stronger than what was actually executed.

Raised as **DOI-D03** (`TEST`, P2).

The 115 figure at DOI-10 is consistent with the same runner before the DOI-11
tests were added (120 − 5 focused DOI-11 tests = 115).

## T0.4 Databases and DOI tables

**Control plane:** `data/canonical/control_plane.sqlite` (129,794,048 bytes).

Copied read-only to
`audit/doi/AVS-TST-DOI-001/scratch/control_plane.copy.sqlite`. All inspection
below is on that copy. Nothing was written to `data/`.

### Rollback-point hashes

```
sha256  0f725c01208a427818ebf49c6f964de12610ed3a21010ddde4081d564629cfdc  data/canonical/control_plane.sqlite
sha256  0f725c01208a427818ebf49c6f964de12610ed3a21010ddde4081d564629cfdc  backups/doi_phase11_20260910/control_plane.pre_doi11.sqlite
sha256  0f725c01208a427818ebf49c6f964de12610ed3a21010ddde4081d564629cfdc  backups/doi_phase1_20260910/control_plane.pre_doi2.sqlite
```

All three are **byte-identical**. Two consequences, both favourable:

1. DOI has written **nothing** to the live control plane across the entire
   eleven-phase build. The "isolated database copy" discipline held.
2. The rollback point is real and is currently a no-op.

### Live control-plane contents (on the copy)

Eleven objects total. **Zero DOI tables exist.**

| Table | Rows |
|---|---|
| `api_request_ledger` | 36,718 |
| `dataset_registry` | 23,304 |
| `option_contract_observations` | 7,969 |
| `option_contract_selection_events` | 8,102 |
| `option_thesis_events` | 10,667 |
| `run_registry` | 22 |
| `schema_metadata` | 4 |
| `schema_migration_log` | 1 |
| `sqlite_sequence` | 1 |
| `stage_worklist` | 70,915 |
| `ticker_lifecycle` | 179,459 |

Three-direction split of the existing option-liquidity lifecycle tables:

| Table | CALL | PUT | OTHER |
|---|---|---|---|
| `option_contract_observations` (`option_side`) | 5,092 | 2,877 | 0 |
| `option_thesis_events` (`direction`) | 6,170 | 4,497 | 0 |
| `option_contract_selection_events` | no side column | — | — |

### DOI tables the code would create

Nine, all via `CREATE TABLE IF NOT EXISTS` inside `canonical_data/dynamic_options_*.py`,
all in the **same** control-plane database — no second raw-data store:

```
doi_contract_families            doi_contract_assessments
doi_preferred_contract_decisions doi_family_rankings
doi_lifecycle_events             doi_outcome_labels
doi_probability_inferences       doi_probability_models
doi_ranking_policies
```

### Verdict on the DOI-8 / DOI-9 / DOI-11 emptiness claims

> "The live control plane currently has zero persisted DOI-7 labels."
> "The live control plane contains no real DOI assessments, outcome labels,
> accepted probability models or accepted ranking policies."

**CONFIRMED, in the strongest possible form.** The claims are not merely true
by row count — the tables do not exist. `doi_outcome_labels`,
`doi_probability_models` and `doi_ranking_policies` are absent from
`sqlite_master`. DOI-8 and DOI-9 unavailability is therefore structural, not
incidental. CALL 0 / PUT 0 / OTHER 0.

Confidence **HIGH**. Raised to HIGH by the byte-identical hash across live and
both backups, which independently confirms no write occurred.

## T0.5 Runtime flags

**`config/doi_runtime.json`** (untracked, new):

```json
{
  "schema_version": "doi_runtime_v1",
  "enabled": true,
  "mode": "ACTIVE_ADVISORY",
  "canonical_reuse_only": true,
  "provider_fetch_allowed": false,
  "decision_authority": "NONE",
  "execution_authority": "HUMAN_ONLY",
  "failure_policy": "TICKER_EXCEPTION_RETAIN_PIPELINE"
}
```

Eight switches. `enabled` defaults **true** — DOI is live-wired for tonight.
The remaining seven all default to the conservative setting
(`provider_fetch_allowed: false`, `decision_authority: NONE`,
`execution_authority: HUMAN_ONLY`, retain-on-failure).

The pre-existing checked-in profile `contracts/dynamic_session_runtime_v1.json`
also exists and is separate. Who reads `doi_runtime.json`, and whether the
conservative defaults are enforced in code or merely declared in JSON, is
resolved in T11.

## T0.6 Interpreter deviation (recorded, pre-registered in `02_expectations.md`)

The prompt mandates `C:\Python314\python.exe`. That interpreter has **no
pytest** module, so it cannot run the pack as a pytest selector and cannot run
the four non-discard tests at all.

Actions taken:

- `C:\Python314\python.exe` (3.14.0) used for `unittest` reconciliation of the
  claimed 120, because that is the interpreter the implementer used.
- `venv\Scripts\python.exe` (3.13.14) used for all pytest work, because it is
  the only interpreter in the repository with pytest (9.1.1).

Both are recorded on every command in this report. This is Deviation 1 in
`06_verdict.md` §5.
