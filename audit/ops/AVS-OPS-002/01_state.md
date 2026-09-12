# AVS-OPS-002 — 01. Repository state before any staging

**Captured:** 2026-09-11
**Operator:** Claude Code (Opus 5)
**Working directory:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`

---

## 1.1 Position

| Fact | Value |
|---|---|
| Current branch | `avs-fix-001` |
| HEAD | `00baa2b0c4b12125a6ad4753910ea73bb6eb6a32` |
| HEAD subject | `AVS-FIX-001 Part G: claim sheet, full matrix, plan-only snapshot proof [gates: Part G 1-4]` |
| `git status --porcelain=v1 -uall` entries | 4071 |
| Detached HEAD | No |
| Merge / rebase in progress | No (`.git/MERGE_HEAD`, `.git/rebase-merge`, `.git/rebase-apply` all absent) |
| Conflict markers in status | None (no `U`, `AA`, `DD` codes present) |
| Stashes | None (`git stash list` empty) |

None of the four stop conditions in Section 1 of the prompt is met, so this operation proceeds.

## 1.2 Branches

```
avs-fix-001    00baa2b   (no upstream)
master         5e68aca   (no upstream configured)
origin/master  0340705
```

`avs-fix-001` is the checked-out branch and carries the whole AVS-FIX-001 series
(W0.2 through Part G, 20 commits visible in the last 20). It is **not** merged
into `master`, and `master` itself is 1 commit ahead of / divergent from
`origin/master`. Neither is touched by this operation.

## 1.3 Tags matching `avs-*`

| Tag | Commit | Created |
|---|---|---|
| `avs-baseline-20260906` | `c8a04ed` | 2026-09-06 |

This matches the hint in the prompt: a baseline tag on the pre-fix tree. No
`avs-committed-*` tag exists yet.

## 1.4 Last 20 commits

```
00baa2b AVS-FIX-001 Part G: claim sheet, full matrix, plan-only snapshot proof [gates: Part G 1-4]
0498df7 AVS-FIX-001 W0.4: track the test-edits register (the blanket *.csv rule was swallowing audit evidence) [gates: QT-D09]
6757893 AVS-FIX-001 W0.4: documentation truth - claim 5 corrected, 17 test edits classified, retroactive backups, P0 recertification v2 [gates: QT-D08, QT-D09, QT-D10]
5683028 AVS-FIX-001 W4.2: Worker 3 transport records the provider error, the credential used, and spends budget only on an answer [gates: RCA3-D01, D02, D03]
f8a0528 AVS-FIX-001 W3.9: outcome maturation as its own non-critical nightly stage [gates: RCA-003 §9, SD-002 §10]
fc6521b AVS-FIX-001 W3.6: IV at selection measured - the early-lane premise is not supported [gates: THS-001 §3.2]
58da85c AVS-FIX-001 W3.5: derived opportunity tier from governed columns only [gates: THS-001 §4]
1177a2b AVS-FIX-001 W3.3: per-contract rejection taxonomy on every Options row [gates: THS-001 §3.1, RCA-003 §2]
a547692 AVS-FIX-001 W3.4: monetisability_state_timevalue as a second ADVISORY_ONLY column [gates: RCA3-D05, DEC-1]
c12ce01 AVS-FIX-001 W3.1: DEC-2 shadow replay - widening recovers 128 candidates, 127 clear the monetisability floor [gates: RCA3-D06, DEC-2]
1c8429a AVS-FIX-001 W0.3: tests/msi into the acceptance matrix; c07 arbitrated for the code; 34 failures -> 24 filed [gates: QT-001 D-04]
a3f06b1 AVS-FIX-001 Part D: read-only gate and warm-rerun checkers for Workstream 2 [gates: AG/RG, DDD, MVP §6]
800c03b AVS-FIX-001 W1.6: one spread authority - per-horizon band clamped by the flat ceiling [gates: RCA3-D07, DEC-3]
d52461e AVS-FIX-001 W1.5: contract_dte in the Lab book, counted in trading sessions [gates: MVP-001 §4]
ab52833 AVS-FIX-001 W1.4: profile-stage guard counts deferrals as deferrals, and names one decision [gates: QT-D03, AVS-PRE-001 EBC]
a062ef0 AVS-FIX-001 W1.3: monetisability_authority stamped on every row including FAILED/DATA_MISSING [gates: QT-D07, 294/294 non-null]
c72f312 AVS-FIX-001 W1.2: retired EIL telemetry cannot contradict a governed stand-down [gates: QT-D06, MVP kill criterion 6]
4a774e7 AVS-FIX-001 W1.1: structural_target is null when absent, never 0.0; generalise the zero-as-price audit rule [gates: QT-D04, PRICE_FIELD_ZERO_AS_MISSING]
38232a8 AVS-FIX-001 W0.6+W0.7: warn that --data-mode is ignored on the dynamic path; separate FINALISE from BUILD_THESIS; arbitrate QT-D05 [gates: QT-D12, QT-D13, QT-D05]
5465790 AVS-FIX-001 W0.2: flag-default tests assert what production does, not the test-only branch [gates: QT-D01]
```

## 1.5 Remote

```
origin  https://github.com/vekoroni/TVautomated.git (fetch)
origin  https://github.com/vekoroni/TVautomated.git (push)
```

A remote **does** exist. Nothing will be pushed under this prompt; Section 4
requires ACK's explicit instruction before any push, and none has been given.

## 1.6 Target branch decision

**Decision: commit on `avs-fix-001`, the currently checked-out branch.**

**Reason:** Section 1 of the prompt says "if you are on `avs-fix-001` or another
`avs-*` working branch that contains the recent commits, commit there". Both
conditions hold. HEAD is `00baa2b`, which is exactly the unmerged
`avs-fix-001` tip the prompt anticipated, and the uncommitted work in the tree
continues directly from it (the W0/W1 fixes it references are already in this
branch's history). The alternative path — creating
`avs-ops-002-commit-20260911` — applies only when sitting on the default
branch, which is not the case. `master` and `origin/master` are untouched, so
ACK retains a deliberate merge decision either way.

## 1.7 `.gitignore`

`.gitignore` exists (8,543 bytes, last modified 2026-09-06). It is extensive and
annotated in a house style: each block carries a dated heading naming the
operation that added it (`AVS-OPS-001 (2026-09-04)`, `AVS-FIX-001 W0.1
(2026-09-06)`, `AVS-FIX-001 W0.4 (2026-09-06)`) and the verification performed.

It currently excludes, among others:

- Python build/cache: `__pycache__/`, `*.py[cod]`, `.venv/`, `venv/`, `dist/`, `build/`
- Data by extension: `*.parquet`, `*.csv`, `*.db`, `*.sqlite`, `*.pkl`, `*.h5`, `*.feather`
- Pipeline output trees: `data/output/`, `data/daily/`, `data/audit/`, `data/macro/`, `data/cache/`, `dropbox/`, `reports/`, `logs/`
- Backups and large trees: `backups/`, `data/canonical/`, `.codex_*/`, `vanguard/data/`, `vanguard/trades/`
- Backup files: `*.bak`, `*.bak_*`, `*_pre_*.parquet`
- Secrets: `.env`, `*.env`, `.env.txt`, `config/secrets*`, `*api_key*`, `*credentials*`, `*.pem`, `*.key`
- 14 specific source files quarantined in 2026-08-20 for containing hardcoded keys
- Root-anchored scratch: `/tmp*/`, `/pip-*/`, `.pytest_cache/`, `pytest-of-*/`
- 13 named pytest-basetemp trees under `audit/` left unreadable by Windows ACLs

Deliberate negations already present: `!tests/golden/*.csv`,
`!data/universe/polygon_liquid_universe.csv`,
`!audit/pipeline_map/AVS-IMP-FIX-001/*.csv`.

**Three gaps found**, all of which let bulk into `git status` today — see group
`G01` in `03_commit_plan.md`:

1. No `node_modules/` rule. 3,315 vendored JavaScript files sit untracked under
   `audit/outcome_comparison/20260909_071646/node_modules/`.
2. No rule for artefact-build scratch. `audit/outcome_comparison/` also holds an
   `.artifact_build/` preview directory, an `.xlsx` and an `.ndjson`.
3. No rule for `audit/doi/AVS-TST-DOI-001/scratch/`, which holds 253 run-output
   JSON files from the DOI tester engagement.

## 1.8 Reconciliation against the history the prompt expected

| Prompt expectation | Found | Note |
|---|---|---|
| Tag `avs-baseline-20260906` on the pre-fix tree | Yes, at `c8a04ed` | Confirmed |
| Branch `avs-fix-001` at `00baa2b`, never merged | Yes, exactly | Confirmed; it is HEAD |
| Large uncommitted work from 4–6 Sep (63 M / 33 ??) | Partly | Now 42 M / 105 non-audit `??`. The 4–6 Sep work appears to have been largely committed by the AVS-FIX-001 series; what remains is mostly 6–10 Sep |
| DOI build 8–10 Sep, DOI-1..DOI-11 | Yes | 8 new `domain/` modules, 9 new `canonical_data/dynamic_options_*` services, 12 DOI test files, Lab projection, orchestrator wiring |
| ~95 `.bak` copies lying around | **No** | Zero `.bak` files in `git status`. Already covered by the `*.bak` rule and/or cleaned |
| 127 untracked `.py` files | **No** | 90 untracked `.py` outside `audit/`, all classifiable |
| Unauthorised `domain/` package (QT-D11) | Yes | `domain/` is tracked (its `__init__.py` is modified); 8 new DOI modules are untracked inside it |

**Two things the prompt did not anticipate, both large:**

1. **Worker 3 is a whole untracked package.** 36 untracked files under
   `worker3/`, 10 untracked test files, 2 contract JSONs, 3 design documents and
   a Lab control script. The prompt's workstream list has no entry for it. It is
   recorded here as workstream `W3`.
2. **197 tracked files are deleted in the working tree.** Every one of them is
   archive, attic, backup or decommissioned material — no live source. See
   `02_inventory.csv` and group `G02`.

## 1.9 Test tree health

`venv/Scripts/python.exe -m pytest tests/ --collect-only -q` collected **1726
tests in 98s with zero collection errors**. The whole test tree imports,
including every untracked module. No test was run.
