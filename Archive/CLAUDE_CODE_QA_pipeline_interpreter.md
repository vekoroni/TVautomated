# Claude Code QA brief — Pipeline Interpreter Automation v2

**Handover date:** 26 July 2026 · **Target operational run:** 27 July 2026
**Repo root:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`

## Your role

You are the **QA engineer, not the author**. Your job is to try to break this and to
report honestly what you find. A clean pass you cannot evidence is worse than a failure
you can.

Three rules:

1. **Do not fix anything unless asked.** Report the defect, its severity, and the
   evidence. Fixing hides the failure rate.
2. **Do not modify production assets.** No writes outside a QA output directory.
   No publication. No brokerage calls.
3. **Report what you could not test** as prominently as what you did. An untested
   sovereign control is an open risk, not a silent pass.

---

## Phase 0 — Establish the baseline before running anything

Record and report, so later results can be attributed:

- Git commit hash / working-tree dirty state
- Python version, OS, and whether the shell is PowerShell or another
- Whether `pipeline_interpreter\MA_Inputs\pipeline_outputs\` contains a **fresh**
  `lab_triage_view_*.csv` — report its timestamp and `run_id`
- Whether `capture_staging` is writable by the current process
  (see Known Limitation: Windows ACLs may block the Codex process but allow the
  operator's own PowerShell session — **test and report which**)
- Whether Webull is running (it will not be, in an unattended session — say so)

**Do not proceed to Phase 3 or 4 if the Lab export is stale.** A stale export must not be
treated as tomorrow's production universe. Say so and stop.

---

## Phase 1 — Run the declared test suites

The handover claims 11 tests run, 11 passed, 0 failed. **Verify that independently.**

```powershell
cd C:\Users\ACKVerissimo\AVSHUNTER-Intelligence

python -m unittest `
  tests.test_pipeline_interpreter_automation_v2 `
  tests.test_pipeline_interpreter_automation_v2_lab_structured `
  tests.test_pipeline_interpreter_automation_v2_lab_batch `
  tests.test_pipeline_interpreter_automation_v2_evidence_package `
  tests.test_pipeline_interpreter_automation_v2_package_publisher `
  tests.test_pipeline_interpreter_automation_v2_package_shadow `
  tests.test_pipeline_interpreter_automation_v2_e2e_orchestrator `
  tests.test_pipeline_interpreter_automation_v2_production_deploy
```

Then the capture suite:

```powershell
python -m unittest discover -s tests -p "test_pipeline_interpreter_capture_v1*.py"
```

Report: **total collected, passed, failed, errored, skipped.** Name every skip and say
why it skipped — a skipped test is not a passing test, and a suite that silently skips
its hard cases will look green while covering nothing.

Report the **actual count**. If it is not 11, say so and reconcile against the claim.

---

## Phase 2 — Sovereign control regression (HIGHEST PRIORITY)

These are the capital-safety controls. The handover states they "must be explicitly
regression-tested". For **each** control below, report one of:

- `COVERED` — name the test file and test method that exercises it
- `NOT COVERED` — no test exercises this
- `PARTIAL` — exercised incidentally but not asserted directly

| # | Control | Expected behaviour |
|---|---|---|
| S1 | Negative option R:R | produces `NEGATIVE_RR` |
| S2 | `NEGATIVE_RR` | produces effective `STOP` |
| S3 | Negative R:R | can never become `GO`, `EXEC` or `READY_EXECUTE` |
| S4 | EIL action on negative R:R | remains `STOP` |
| S5 | Upstream `BLOCKED`/`STOP`/`NO_TRADE` | excluded from candidates |
| S6 | Missing or invalid evidence | **fails closed** |
| S7 | Ticker mismatch | stops the workflow |
| S8 | Screen-type mismatch | stops the workflow |
| S9 | Provider interpretation | cannot promote upstream permission |
| S10 | Any path | never places trades or allocates capital |

### Adversarial probes — write these as new tests under `tests\qa\`

Do not modify existing tests. Add new ones. For each, the expected result is that the
control **holds**:

- **P1** R:R exactly `0.0` — boundary. Is zero treated as negative, or does it slip
  through? Report which, and whether that is intentional.
- **P2** R:R as a string (`"-1.5"`) rather than a float — does the comparison still fire,
  or does it raise, or silently pass?
- **P3** R:R field absent entirely — fail closed, or default to permissive?
- **P4** R:R is `NaN` — `NaN < 0` is `False` in Python. **This is the classic bypass.**
  Does a NaN R:R become GO?
- **P5** Effective verdict `STOP` with an EIL action of `EXECUTE` in the source — does
  STOP survive, per "STOP remains STOP through every layer"?
- **P6** Upstream `BLOCKED` candidate with otherwise perfect metrics — excluded?
- **P7** Evidence package with 11 of 12 required assets — refuses to publish?
- **P8** Evidence package with 12 assets but one SHA-256 mismatch — refuses?
- **P9** Screenshot named `AAPL_daily.png` whose content is a different ticker — the
  automation cannot see image content, so **what actually enforces this?** Report the
  mechanism, or report that it relies solely on operator confirmation.
- **P10** Two candidates where one is STOP — does the batch continue for the other, or
  fail the whole batch? Report the designed behaviour and whether it is tested.

**P4 is the one to check first.** A `NaN` comparison returning `False` is the most common
way a "negative value" guard is bypassed, and this codebase has prior history of guards
that exist and do not fire.

---

## Phase 3 — Lab-driven planning test (no capture)

Run discovery and candidate selection **without** `--execute-shadow-batch`.

```powershell
$runId = Get-Date -Format "yyyyMMdd-HHmmss"

python -m pipeline_interpreter.automation_v2.lab_batch_cli `
  --pipeline-outputs pipeline_interpreter\MA_Inputs\pipeline_outputs `
  --staging-root pipeline_interpreter\MA_Inputs\capture_staging `
  --output-directory "pipeline_interpreter\automation_v2\deployments\qa-plan-$runId" `
  --invocation-id "qa-plan-$runId" `
  --max-candidates 10
```

Verify and report:

- Which `lab_triage_view_*.csv` was selected, and **that it is the latest**
- The `run_id` is consistent across every selected record
- Candidate ranking **matches the Lab source order** — do not accept "looks right";
  compare against the CSV directly and show the comparison
- Every stopped/excluded candidate is listed with a reason code
- Negative R:R candidates appear in the stopped list as `NEGATIVE_RR`
- No stopped candidate appears in the executable set
- `eil_enriched_*.csv` fills **missing fields only** and never overrides
  `lab_triage_view` — construct a case where the two disagree and show which wins

### Structured Lab field completeness

Confirm every declared field is present and populated in the structured output, not just
present as a key:

verdict, execution classification, direction, instrument, strike, expiry, premium,
breakeven, predicted R:R, EV, call wall, put wall, gamma flip, max pain, WBS value,
WBS grade, trigger price, trigger quality, trigger score, trigger codes, volatility
fields, Q-Omega fields, sovereign veto codes, effective verdict, EIL action.

Report any field that is present-but-null, and any that is missing entirely.

**Note on gamma fields:** gamma flip, call wall, put wall and max pain have a known
history in this codebase of defaulting to chain boundaries when no true crossing exists.
Report the **value** of gamma flip for each candidate alongside the min and max strike of
its chain. If gamma flip equals the minimum strike, flag it — that is the signature of a
`min(strike)` fallback rather than a computed level.

---

## Phase 4 — Single-ticker E2E shadow (only if staged evidence exists)

The handover reports NFLX passing with 12 assets, `sovereign preserved: true`,
`effective verdict: STOP`, `published: false`, `production_charts_touched: false`.

**Reproduce it.** Then verify the negative cases:

- Remove one staged asset → expect `status: incomplete`,
  `go_no_go: NO_GO_BATCH_INCOMPLETE`. Confirm this is treated as a **valid fail-closed
  result**, not an error and not an authorisation.
- Corrupt one asset's bytes after hashing → expect refusal.
- Rename one asset off-canonical → expect refusal.

Report `published` and `production_charts_touched` for **every** run. Both must be
`false` throughout QA. If either is ever `true`, stop immediately and report it as
CRITICAL.

If no staged evidence exists, **say so and skip** — do not fabricate assets to make the
phase pass.

---

## Phase 5 — Things the handover does not claim to test

Probe these and report. They are the gaps most likely to bite in production:

- **Concurrency:** two batches with the same `--invocation-id` — collision handled?
- **Resume identity:** interrupt a batch and resume — does it resume the same run or
  silently start a new one?
- **Disk full / write failure** mid-publication — does atomic publication actually roll
  back, or leave a partial state?
- **Rollback:** exercise backup and rollback. Verify the deployment receipt's
  before-and-after hashes are real, not placeholders.
- **Stale Lab guard:** point it at a Lab export from `20260604` and confirm it either
  refuses or warns loudly. Known Limitation says a stale export "must not be treated as
  tomorrow's production universe" — is that enforced in code, or only in the document?
- **Empty Lab export** (headers, zero rows) — graceful, or traceback?
- **`--max-candidates 0`** and a value exceeding available rows.

---

## Deliverable

Write `QA_REPORT_pipeline_interpreter_20260726.md` to the repo root.

Structure:

1. **Verdict** — one of `APPROVE`, `APPROVE WITH CONDITIONS`, `DO NOT APPROVE`,
   measured against the 14 acceptance criteria in section 11 of the handover. State
   each criterion and whether it is met, not met, or untestable.
2. **Environment baseline** from Phase 0.
3. **Test results** — collected/passed/failed/errored/skipped, with every skip named.
4. **Sovereign control matrix** — S1–S10, each `COVERED` / `PARTIAL` / `NOT COVERED`
   with the test that covers it.
5. **Adversarial probe results** — P1–P10, each with the actual observed behaviour.
6. **Defects** — severity, reproduction steps, evidence. Do not fix them.
7. **Untested** — what you could not test and why. Be explicit; this section is a risk
   register, not an apology.
8. **Confidence** — a percentage on your own verdict, with what would raise it.

### Severity definitions

- **CRITICAL** — a sovereign control can be bypassed, or production assets can be
  touched, or capital could be allocated
- **HIGH** — fail-closed does not fail closed; STOP does not survive a layer
- **MEDIUM** — incorrect data in output, missing field, wrong ranking
- **LOW** — cosmetic, logging, ergonomics

---

## Constraints

- Read-only against production. All QA output under
  `pipeline_interpreter\automation_v2\deployments\qa-*`
- Never pass `--execute-shadow-batch` in Phase 3
- Never publish, never touch production charts
- No brokerage or network calls
- New tests go in `tests\qa\` — do not modify existing tests
- If any step would write outside the QA output directory, **stop and ask**

---

## Reporting standard

For each finding, state: what you ran, what you observed, what you expected, and your
confidence. Where you are inferring rather than observing, say so.

Two specific honesty requirements:

- If a control is untested, write `NOT COVERED`. Do not write "appears correct" on the
  basis of reading the code — reading is not testing, and say which you did.
- If a test passes for a reason you cannot explain, report it as a finding. A green
  result you do not understand is not evidence.

Begin with Phase 0 and report before proceeding.
