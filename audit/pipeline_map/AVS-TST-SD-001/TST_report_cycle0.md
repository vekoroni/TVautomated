# AVS-TST-SD-001 — Cycle 0 (intake)

**Role:** independent tester. I did not write the code under test and have fixed nothing.
**Mode:** production code and baseline run data READ-ONLY. All writes under `audit/pipeline_map/AVS-TST-SD-001/`.
**Date:** 2026-08-31

---

## 1. Cycle inputs, as required before any testing

The prompt requires me to restate the claim sheet, the candidate run IDs, and
the workstreams I will therefore test. All three inputs are **absent**.

| Required input | Status | Evidence |
|---|---|---|
| **Specification under test** — `audit/pipeline_map/AVS-SD-001_solution_design.md` (v0.2) | **MISSING** | `ls` returns "No such file or directory". The folder contains the E2E report, the 20260829 map, `confidence_lineage.md`, `efficiency_gaps_register.md`, `interface_gaps_register.md`, `stage_interface_manifest.json` — and no `AVS-SD-001*`. |
| **Implementer's claim sheet** (WS0–WS9 + self-reported measurements) | **NOT SUPPLIED** | No claim-sheet file in `audit/pipeline_map/`; none provided in the briefing. |
| **Candidate run ID(s)** (`CANDIDATE_EVENING`, `CANDIDATE_MORNING`) | **NOT SUPPLIED, AND NONE EXIST** | Newest run under `data/output/runs/` is `20260831_010309` — the **baseline itself** (closed 02:56:41). Every other run predates it. There is no morning run at all. |
| Baseline run + control plane | **PRESENT, INTACT** | `20260831_010309` present; `control_plane.sqlite` mtime 02:31:17, unchanged. Part A reproduces 45/45 baseline values. |

**Consequence, per the prompt's own rule** — *"If no candidate run is supplied
for a workstream that claims completion, the workstream is BLOCKED — NOT
TESTABLE, not passed"* — **every workstream WS0–WS9 is BLOCKED.** No gate can
close this cycle. I have substituted no inference for any measurement.

Because the specification is missing I also cannot resolve the design decisions
the acceptance tests depend on: **D1** (WS2 reorder vs join), **D2** (WS3 —
populate `11_20d` or retire it and narrow the lifecycle domain to `{5,10}`), and
**D3** (WS5 — A/B no size-by-direction vs C publish multiplier+key). Those three
tests cannot even be written, let alone run.

---

## 2. Production code HAS changed — with no candidate run to test it

This is the material finding of the intake. The implementer has been working:
**20 `.py` files** were modified after the baseline run closed at 02:56:41,
six of them this evening between 20:30 and 20:49 — *after* the AVS-E2E-CODE-001
atlas was completed.

| File | mtime |
|---|---|
| `eod_candidate_engine.py` | 2026-08-31 20:49:57 |
| `intelligence-lab/intelligence_lab.py` | 2026-08-31 20:45:43 |
| `morning_gate.py` | 2026-08-31 20:34:18 |
| `intelligent_orchestrator.py` | 2026-08-31 20:33:55 |
| `scripts/avshunter_options_intelligence.py` | 2026-08-31 20:31:13 |
| `contracts/options_liquidity_lifecycle.py` | 2026-08-31 20:30:06 |

plus `contracts/{lab_control, options_liquidity_execution_guard, interpreter_handoff_materializer, interpreter_macro_context}.py`,
`morning_handoff_finalizer.py`, `pipeline_interpreter/{evidence_resolver, macro_context}.py`
and seven `tests/test_*.py`.

**The testing consequence is decisive: the baseline run artefacts no longer
correspond to the code on disk.** Every artefact-level measurement available to
me describes the output of *pre-change* code. Artefact-level acceptance testing
of any workstream is impossible until an evening run is executed against the
current tree. This is filed as **TST-DEF-003 (TEST_BLOCKED)**, and as
**UNTRACKED_CHANGE** because no claim sheet attributes these edits to a workstream.

I have not run the pipeline to produce a candidate myself: the prompt forbids
modifying run data, and generating a candidate is the implementer's step, not
the tester's.

---

## 3. What I could measure without a candidate run

### 3.1 WS0 repo-state gates — all three FAIL

WS0's gates are repository-state properties, not run-artefact properties, so
they are testable now. All three are still at their AVS-E2E-CODE-001 baseline
values, i.e. unchanged:

| WS0 gate | Expected | Actual | Verdict |
|---|---|---|---|
| `git status` clean; 127 previously-untracked files now tracked | clean, 0 untracked `.py` | **130 untracked entries (70 `.py`), 72 modified, 32 deleted** | **FAIL** |
| `bom_files.txt` set normalised, or tooling proven `utf-8-sig`-safe | 0 BOM files (or documented tooling proof) | **42 BOM files — unchanged** | **FAIL** |
| `scenario_builder` import binding deterministic (proved by graph re-resolution) | one resolvable module | **3 copies; the two `vanguard/` copies byte-identical (`a106e23c…`), root differs (`ae69f0cb…`)** | **FAIL** |

### 3.2 Part A regression harness — built and validated

`measurements/t_regression.py` is the parametrised suite required by Part A
(run id is an argument; three-direction census on every direction column). Run
against the baseline it reproduces **45/45 expected values exactly**, which
establishes it as a trustworthy Level-2 instrument for cycle 1:

- population census and zero-duplicate-tickers across all eight artefacts;
- zero downstream arrivals at all six measured boundaries;
- contract coverage 191/201, two-sided quotes 175/201;
- WBS 31 scored / 14 intersection / 17 excluded;
- A3 pre-fix defects all still reproduce: **442** invalidated (**437 PUT / 5 CALL / 0 OTHER**), **657** `DTE_UNSUITABLE`, **292** horizon-unaccounted, `selected_quote_timestamp_utc` blank **201/201**, `governed_direction` carrying **20 STRANGLE**.

Full output: `TST_partA_20260831_010309.csv`.

---

## 4. A gate-wording defect found while building the harness

**TST-DEF-007 — the WS2 gate as written would pass the baseline defect.**

The WS2 gate says `trigger_quality` must be *"populated 201/201 in the final
book"*. I built that test, and it **failed against the baseline in the wrong
direction** — which turned out to be my harness trusting the atlas's §11.5
wording without checking which artefact it referred to. Measuring all three:

| Artefact | `trigger_quality` |
|---|---|
| `eil_enriched` (1,248 rows) | Correct categoricals — SINGLE 650, NONE 304, STRONG 294 |
| `morning_candidates` (201, the EOD candidate file) | **blank 201/201** (also `trigger_primary` and `trigger_codes` blank 201/201) |
| `final_opportunity_book` (201) | **`'55.0'` ×191, `'0.0'` ×10 — numerically identical to `trigger_score`** |

So in the governed book the column is **not empty, it is type-poisoned**: the
§10-forbidden `trigger_quality ← trigger_score` bridge, caught in the artefact.
**A populated-ness test scores 201/201 populated and passes the defect.**

The gate must be tested on **domain membership** (`{STRONG, SINGLE, NONE}`) and
**ticker-wise equality with EIL**. My harness now does both. Measured on the
baseline: `numeric=201, categorical=0`, and `0/201` agreement with EIL — the
correct pre-fix signature.

This also refines the atlas: §11.5 says the value is *null* in the candidate
rows, which is true of `morning_candidates` but **not** of the final book, and
the book is what WS2's gate names. `trigger_primary` behaves differently again —
blank 201/201 in `morning_candidates` but only 48/201 blank in the book, so the
book sources it from somewhere other than the EOD candidate file.

---

## 5. Verdict table

| WS | Gate | Expected | Actual | Verdict |
|---|---|---|---|---|
| WS0 | git clean, 127 tracked | 0 untracked `.py` | 70 untracked `.py`, 72 M, 32 D | **FAIL** |
| WS0 | BOM set normalised | 0 | 42 | **FAIL** |
| WS0 | `scenario_builder` deterministic | 1 module | 3 copies, 2 identical | **FAIL** |
| WS0 | parametrised regression tooling | exists | **built by tester**, 45/45 on baseline | n/a (tester deliverable) |
| WS0 | morning baseline run exists | present | **none exists** | **BLOCKED** |
| WS1 | invalidation false-positives → 0 | 0 | no candidate run | **BLOCKED** |
| WS2 | trigger block carried to book | 201/201 categorical, = EIL | no candidate run | **BLOCKED** |
| WS3 | Horizon reconciles exactly | 0 unaccounted | no candidate run; D2 undecided | **BLOCKED** |
| WS4 | one direction field, 4-value domain | — | no candidate run | **BLOCKED** |
| WS5 | Discovery macro-invariant | — | no candidate run; D3 undecided | **BLOCKED** |
| WS6 | EOD monetisability, 0 blank | — | no candidate run | **BLOCKED** |
| WS7 | rerun identity + supersession | — | no candidate run | **BLOCKED** |
| WS8 | semantic-bridge lint | — | no candidate run; spec missing | **BLOCKED** |
| WS9 | no DEAD module reachable | — | no candidate run | **BLOCKED** |
| CT1 | research-lane isolation | — | no Market Profile work claimed | **NOT APPLICABLE** |

---

## 6. Unblock conditions (precise)

1. Supply `audit/pipeline_map/AVS-SD-001_solution_design.md` v0.2. Without it there is no acceptance contract and D1/D2/D3 are unresolvable.
2. Supply the claim sheet: which of WS0–WS9 are asserted complete, with the implementer's own measured numbers (Level 1).
3. Execute an evening run against the current tree and supply its run ID as `CANDIDATE_EVENING`. Until this exists, no artefact-level gate is testable.
4. For WS0 and WS7, execute and supply a morning run (`CANDIDATE_MORNING`); for WS7 additionally a **second** evening run on the same completed session, and for WS5 the three Discovery runs (macro present / absent / stale).

---

**Regression: GREEN. Gates closed this cycle: [none]. Gates failed: [WS0 git-clean, WS0 BOM-normalisation, WS0 scenario_builder-determinism]. Gates blocked: [WS0 morning-baseline, WS1, WS2, WS3, WS4, WS5, WS6, WS7, WS8, WS9].**

_Regression is GREEN in the sense that the baseline reproduces 45/45 — it is not
a statement about the candidate, because there is no candidate._
