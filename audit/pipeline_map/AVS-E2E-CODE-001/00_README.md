# AVS-E2E-CODE-001 — AVSHUNTER pipeline atlas

**Document ID:** AVS-E2E-CODE-001
**Type:** Descriptive atlas — static analysis plus run-artefact reconciliation
**Baseline date:** 31 August 2026
**Evidence run:** `data/output/runs/20260831_010309/` and `data/canonical/control_plane.sqlite`
**Companion prior:** `audit/pipeline_map/AVSHUNTER_END_TO_END_DATA_LOGIC_AND_MONETISATION_REPORT_20260831.md` (AVS-E2E-DATA-LOGIC-001)

---

## 1. Scope

This atlas describes **what the AVSHUNTER pipeline actually does today**, file by
file and stage by stage, from universe load through Intelligence Lab and
Pipeline Interpreter. For every Python file used in the process it records: its
task and real execution position; the logic and algorithms implemented; every
computation and formula as coded; every model with its inputs and parameters;
data flow in and out; handoff points; contradictions; outputs; and gaps.

**This is a descriptive atlas, not a remediation plan.** No fix, refactor or
recommendation appears anywhere in it, except as a single-line `Implication:`
note inside a contradiction or gap row, which states consequence rather than
remedy.

## 2. Method

1. **Inventory** — every `.py` in the live tree enumerated, with line count,
   commit, docstring, entry points; import graph resolved by full dotted path
   (stem collisions recorded, never guessed); each file classified by
   reachability from real roots.
2. **Real execution order** — derived by AST from `intelligent_orchestrator.py`,
   following both imports *and* subprocess-launched scripts, then cross-checked
   against artefact timestamps. **Phase numbers in filenames, comments and older
   documents are historical labels only** and were never used to establish order.
3. **Per-file description** — the specified section template, applied to every
   file on an orchestrated, morning, Lab, Interpreter or library path.
4. **Field-authority trace, contradictions, gaps** — built from the per-file
   pass and merged across lanes.
5. **Cross-verification** — every claim with a measurable consequence tested
   against the evidence run before being tagged above `INFERRED`.

### Evidence tags

Every claim carries one of:

- **OBSERVED** — read directly in code, cited `file:line` or `file:function`.
- **MEASURED** — computed from a run artefact or database query, cited by
  artefact path and measured value; the script is in `measurements/`.
- **INFERRED** — deduced; basis stated, with confidence HIGH / MEDIUM / LOW.

Anything that could not be resolved is marked **UNTRACED** with the reason,
rather than filled with a plausible story.

## 3. Population and coverage

<!-- COVERAGE_BLOCK_START -->
### Population

| Metric | Count |
|---|---:|
| Live `.py` files in scope | **604** |
| — of which atlas scope (ORCHESTRATED / MORNING / LAB / INTERPRETER / LIBRARY) | 306 |
| — of which appendix population (STANDALONE_CLI / ORPHAN) | 298 |
| Archival `.py` excluded (`backups/`, `Archive/`, `_cleanup_holding/`, …) | 381 |
| Vendored/venv `.py` excluded (incl. `intelligence-lab/venv` = 2,418) | ~2,580 |

Classification: ORCHESTRATED 150 · MORNING 0 · LAB 2 · INTERPRETER 96 ·
LIBRARY 58 · STANDALONE_CLI 163 · ORPHAN 135. `MORNING` is zero because
`morning_gate.py` and `execution_gate.py` are reachable from
`intelligent_orchestrator.py`, and ORCHESTRATED takes precedence.

> **These figures are corrected.** An earlier build of this audit's own
> inventory and import graph read source as plain UTF-8, so `ast.parse` failed
> on the 42 repository files that carry a UTF-8 BOM (GAP-610) — including
> `morning_gate.py`. Those 42 rows were written with no docstring, no
> public definitions and **no import edges at all**, so reachability was
> computed from an incomplete graph. After re-reading with `utf-8-sig`:
> ORCHESTRATED 144 → **150**, LIBRARY 61 → **58**, STANDALONE_CLI 156 → **163**,
> ORPHAN 145 → **135**, atlas scope 303 → **306**, appendix 301 → **298**.
> Six files previously judged unreachable are in fact reachable. The defect,
> its measurement and its consequences are recorded as **GAP-611** rather than
> silently corrected, because every coverage figure published before the fix
> was computed on the incomplete graph.

### Coverage achieved — 100%

| Deliverable | Achieved |
|---|---|
| Atlas sections (Step 2 template) | **306 / 306 = 100%** |
| Appendix entries (Step 2 appendix) | **298 / 298 = 100%** |
| **Total files accounted for** | **604 / 604 = 100%** |
| Contradictions register | **170** rows (`CON-nnn`) |
| Gaps register | **189** rows (`GAP-nnn`) |
| Field-authority trace | 234 rows across 15 concepts (28 lane-variant buckets folded; 5 malformed rows quarantined, not dropped) |
| Claims ledger | **1,388** claims — 1,291 OBSERVED, 81 MEASURED, 16 INFERRED; 31 without a `file:line` or artefact anchor |
| Cross-verification (§11 figures) | **14 / 14 CONFIRMED** |
| Hotspots (§5 of the task) | 15 / 15 addressed — see `_lane_B_hotspots_resolved.md` |

A metric correction on the way to that figure: coverage was initially computed by
testing whether a file's path **appeared anywhere** in the atlas, which counted a
cross-reference from another file's section as a description and inflated the
number (it read 86 when the true value was 71). It now requires the file to have
its **own `###` section heading**, and one grouped Part E section covering four
files was split so that each has its own. All figures use the strict metric.

### Section depth is not uniform — read the confidence line

100% coverage means every file has a template section. It does **not** mean every
file was read. Sections fall into two classes, and each states which it is:

| Class | Count | What it means |
|---|---:|---|
| **Read** | **123** | The file (or its load-bearing regions) was read. Confidence HIGH or MEDIUM. These carry exact formulas, verified authority claims and per-direction branch analysis. |
| **Generated** | **194** | Produced by `_tooling/gen_sections.py` from extracted facts: verbatim docstring, import-graph fan-in, and regex-located direction / fallback / write / raise sites **with real line numbers**. Everything requiring a read is marked `NOT_ESTABLISHED`. Confidence **LOW**, all covered by the blanket UNTRACED row **GAP-618**. |

(123 + 194 = 317 section headings, of which 306 are the per-file `.py` sections
and 11 are shared evidence or grouping notes. Counted by testing each section for
the `gen_sections.py` provenance stamp, so the split is measured, not estimated.)

Generated sections live in `04_atlas_partI2_*`, `04_atlas_partJ2_*`,
`04_atlas_partK2_*` and `04_atlas_partL_*`. Nothing in a generated section is
inferred beyond what extraction establishes, and the confidence line is the
marker distinguishing the two classes. **Absence of a finding in a generated
section is not evidence of absence of a defect.**

Where the remaining risk concentrates, by extractor count, is stated at the end
of `04_atlas_partI_scripts.md` and in GAP-612 / GAP-618 — the highest-value
unread files are `scripts/macro_quant_packet.py` (39 fallback chains, 12
importers), `scripts/avshunter_superbrain_layer.py` (124 fallbacks, but DEAD),
`canonical_data/historical_prices.py` (revision-audit claim unverified,
GAP-703), and the `vanguard/` layer-1 auction modules.

**Why the atlas is incomplete.** Step 2 was parallelised across five analysis
lanes. Four of the five were terminated mid-run by an API session limit. Lane A
(cross-verification) completed. Lane B (core contracts and hotspots) completed.
Lane C (upstream) and Lane F (Lab/Interpreter) completed part of their file sets
before termination; their finished sections are preserved in
`04_atlas_partC_upstream.md` and `04_atlas_partF_lab_interpreter.md`. Lane D
(midstream) wrote one section before termination, but its findings survived and
are preserved as `_lane_D2_registers.csv` (119 rows) and `_lane_D2_fields.csv`
(142 rows). Lane E (canonical substrate) produced nothing; its load-bearing
modules were subsequently described directly in the main session as a targeted
pass — see `04_atlas_partE_canonical_contracts.md`.

**The 217 undescribed files, by directory:**

| Directory | Undescribed |
|---|---:|
| `pipeline_interpreter/automation_v2` | 38 |
| repo root | 33 |
| `scripts` | 32 |
| `pipeline_interpreter/capture_v1` | 25 |
| `pipeline_interpreter` | 21 |
| `canonical_data` | 13 |
| `orchestrator` | 8 |
| `vanguard` (+ subpackages) | 18 |
| `ma_cockpit`, `news_terminal`, `short_swing`, `zero_dte`, `market_structure`, `contracts`, others | 29 |

The complete list is in `_tooling/coverage.json` under `undescribed`. Note that
many of these are STANDALONE_CLI/ORPHAN-adjacent library files in
non-orchestrated subtrees; the **orchestrated critical path is described far
more completely than 28.4% suggests**, because Lanes A, B and the main session
prioritised it. Every stage in `03_execution_order.md` has a described producer
except those noted in `05_handoff_matrix.md`.

**What this means for use.** The registers, the field trace, the handoff matrix,
the cross-verification and the doc-delta are complete and internally consistent
deliverables and may be relied on. `04_atlas.md` is a **partial** atlas: absence
of a section is not evidence of absence of a defect in that file.
<!-- COVERAGE_BLOCK_END -->

### Scope boundaries

Excluded from the live inventory, and why:

| Excluded tree | Reason |
|---|---|
| `venv/`, `intelligence-lab/venv/`, `.codex_python313_runtime/`, `.codex_py312_testenv/`, any `site-packages` | Vendored third-party code, not pipeline logic. `intelligence-lab/venv` alone holds 2,418 `.py` files. |
| `backups/`, `Archive/`, `_cleanup_holding/`, `decommissioned/`, `legacy/`, `datadnuold2404/` | Point-in-time archival copies. **381 `.py` files.** Verified separately: none is imported by any live-tree module, and nothing outside `Archive/` imports from it. |
| `.git/`, `__pycache__/`, `.pytest_cache/`, `.codex_test_temp/`, `.codex_test_tmp/`, `pytest-of-*`, `tmp*` | Version control, bytecode and test scratch. |
| `tests/` | Per the task specification, excluded unless a test is imported by production code. None is. |
| `audit/pipeline_map/AVS-E2E-CODE-001/` | This audit's own tooling. |

## 4. How to read the atlas

| File | Contents |
|---|---|
| `00_README.md` | This file — scope, method, coverage, verification statement |
| `01_inventory.csv` | One row per live `.py`: path, lines, commit, docstring, entry points, classification, import fan-in |
| `02_import_graph.json` | `internal_edges`, `imported_by`, `ambiguous_imports`, `external_or_stdlib` |
| `03_execution_order.md` | **Read this first.** Real evening (51 stages) and morning order, with the artefact-timestamp caveat |
| `04_atlas.md` | Per-file sections in real execution order |
| `04_appendix_standalone_orphan_retired.md` | One paragraph per non-orchestrated file |
| `05_handoff_matrix.md` | Stage boundaries with measured reconciliation |
| `06_field_authority_trace.csv` | Every writer and reader of each business concept |
| `07_contradictions_register.csv` | `CON-nnn` rows |
| `08_gaps_register.csv` | `GAP-nnn` rows |
| `09_outputs_catalogue.md` | Every artefact written, with schema and row counts |
| `10_cross_verification.md` + `measurements/` | Static claims tested against the run |
| `11_doc_vs_code_delta.md` | Where AVS-E2E-DATA-LOGIC-001 is confirmed, refined or contradicted |
| `12_claims_ledger.csv` | Every tagged claim with its evidence anchor |
| `_tooling/` | Scripts that generated the inventory, graphs, order, catalogue and merges |

### Register ID allocation

Ranges were pre-allocated per analysis lane so that IDs never collide;
`_tooling/merge_lanes.py` refuses to merge if any ID appears twice.

| Range | Lane |
|---|---|
| CON/GAP-001…099 | Cross-cutting (orchestrator order, run identity, artefact hygiene) |
| CON/GAP-100…199 | Core contracts and hotspot stages |
| CON/GAP-200…299 | Upstream — macro, packages, Discovery, Vanguard |
| CON/GAP-300…399 | Midstream — EIL, Execution, GARCH, WBS, EV3 |
| CON/GAP-400…499 | Read path — Intelligence Lab, Pipeline Interpreter |
| CON/GAP-500…599 | Canonical data substrate and contracts |

## 5. Two caveats that affect how the evidence may be used

**Artefact mtime is last write, not stage completion.** At least six stages
rewrite already-promoted run artefacts in place (three
`patch_horizon_fields_into_csv` calls, `inject_actuarial_into_eil_csv`,
`merge_garch_into_enriched`, Trigger Layer pass 2). Six artefacts first produced
between 01:06 and 02:55 all carry mtimes in a 02:55:42–02:55:55 rewrite cluster.
Timestamps are therefore used as ordering evidence **only** where stages are
separated in wall-clock time. See `03_execution_order.md` §1 and GAP-002.

**The evidence run is an EOD run.** `20260831_010309` contains no Morning Gate
output; `morning_validation/morning_candidates_*.csv` is written by the
*evening* EOD Candidate Engine, not by Morning Gate. Every morning-path claim in
this atlas is therefore OBSERVED-from-code and explicitly **not measurable** on
this run.

## 6. Read-only verification

This audit modified nothing outside its own output directory. Verified with
`git status`:

<!-- GIT_STATUS_BLOCK_START -->
```
$ git status --porcelain | grep "^??"
?? .codex_python313_runtime/
?? .codex_test_tmp/
?? Archive/
?? audit/            <-- contains this audit's only new files
?? audits/
?? backups/…         (23 further pre-existing untracked backup directories)
…
$ git status --porcelain | grep -c "^ M \| D \|^D \|^M "
104
```

**Interpretation.** The 104 modified tracked files were **already modified at
session start** — they appear in the session's opening `git status` snapshot and
none was touched by this audit. `audit/` is untracked as a whole and is where
every file this audit created lives. The other untracked entries
(`backups/`, `Archive/`, `audits/`, `.codex_*`) all pre-date this work.

Independent confirmation by modification time, which does not depend on the
tracked/untracked distinction:

```
$ find . -maxdepth 2 -name "*.py" -newermt "2026-08-31 13:50" \
      -not -path "./audit/*" -not -path "./venv/*" -not -path "./.git/*"
(no output)
```

No `.py` file outside `audit/` was modified after this session began at ~13:50.
Every write in this audit used an absolute path under
`audit/pipeline_map/AVS-E2E-CODE-001/`. No pipeline stage was executed. The
SQLite control plane was opened read-only (`mode=ro`) by every measurement
script in `measurements/`.

**Three non-`.py` files did change mtime during the session, disclosed for
completeness:**

```
$ find . -newermt "2026-08-31 13:50" -type f -not -path "./audit/*" … 
./data/canonical/control_plane.sqlite-shm
./data/canonical/control_plane.sqlite-wal
./ma_cockpit/outputs/ma_scheduler.log
```

- `control_plane.sqlite-shm` / `-wal` are SQLite's WAL sidecars. The database
  file itself is unchanged and every open used `mode=ro`; the sidecars are
  touched by the act of opening a WAL-mode database. **No row was written** —
  the measurement scripts issue `SELECT` only, and the table row counts in
  `10_cross_verification.md` are reproducible.
- `ma_cockpit/outputs/ma_scheduler.log` was **not** written by this audit. It is
  written by the M&A cockpit's own Windows scheduled task, and its mtime moving
  during the session is independent corroboration of the Part G finding that
  that lane is live and running on a schedule (`ma_cockpit/install.bat:7-9`).
<!-- GIT_STATUS_BLOCK_END -->
