# RCA: "cannot observe a terminal thesis" — defect class, not instance

Scope note per the tasking: this is root-cause analysis only. No production code was
modified. A failing reproduction test was added at
`tests/rca/test_morning_gate_terminal_thesis_ordering.py` (does not touch production
code; it drives the existing, unmodified `morning_gate.py`). This document does not
mark anything CLOSED.

## 0. One correction to the tasking's premise, established from evidence

The tasking states the fault "recurred despite" the 2026-08-30 reordering fix in
`scripts/avshunter_options_intelligence.py`. The only concrete occurrence found in
this repository (`logs/orchestrator.log`, run `20260830_182402`, ticker FLYW,
2026-08-30 20:18:04 local / 19:18:03Z) **predates that fix**, not postdates it:

- `scripts/avshunter_options_intelligence.py` mtime is **2026-08-30 21:25:46** (the
  fix's write time — confirmed by diffing it against
  `backups/terminal_lifecycle_persistence_prechange_20260830/avshunter_options_intelligence.py`,
  mtime 2026-08-30 13:48:35, which is the pre-fix content and matches what the
  traceback's line numbers/behaviour imply was running).
- The FLYW traceback (`logs/orchestrator.log:1769801-1769828`) shows
  `_persist_options_lifecycle_result` calling `record_contract_observation` and
  failing *without* the guard/staging block that the current file has at lines
  7668-7789 — i.e. the pre-fix code path (unconditional
  `record_thesis_event(terminal)` immediately followed by
  `record_contract_observation`, no staging, no early-return reuse guard).
- `logs/orchestrator.log` has no entries after 2026-08-30 20:18:12 — no pipeline run
  has been logged since, so there is **no logged occurrence on the post-fix code**.

So the FLYW failure is best read as *the incident that prompted the fix*, not a
recurrence of it. That does not make the underlying defect class any less real —
see §3 — but the specific claim "the fix passed 87/87 tests and then this exact run
failed on the fixed code" is not supported by file timestamps and log coverage
available in this repo. (`tests/test_option_liquidity_lifecycle.py` currently has 10
tests, all passing; "87/87" likely refers to a broader suite run not further
identified from repo evidence alone.)

A second occurrence was found in the database only (no matching log line — see the
logging-gap note in §5): `CART:PUT:2026-08-29`, version 1, `INVALIDATED`,
`DTE_UNSUITABLE`, `event_key=EOD:20260829_222259`, `recorded_at=2026-08-30T00:48:39Z`.
This run (`20260829_222259`) completed and archived successfully per the log
(`logs/orchestrator.log:1765201-1765259`), which is only possible if
`AVSHUNTER_STAGE_GATING_ENFORCED` was **not** enforced at that point in the run (the
same exception, caught, downgraded to `results[-1]['liquidity_persistence_status'] =
"ERROR:DatasetValidationError"` and a non-fatal warning print — see
`scripts/avshunter_options_intelligence.py:8162-8171`). This is also pre-fix (same
file, same defect, same call site as FLYW), and it is the same defect firing
silently rather than fatally, purely as a function of the `AVSHUNTER_STAGE_GATING_ENFORCED`
flag's value at that moment.

## 1. Occurrence table

| # | thesis_id | ticker | run_id | recorded_at (UTC) | phase / caller | fatal? | source | pre/post 2026-08-30 21:25:46 fix |
|---|---|---|---|---|---|---|---|---|
| 1 | `FLYW:PUT:2026-08-30` | FLYW | `20260830_182402` | 2026-08-30T19:18:03.96Z | EOD, `scripts/avshunter_options_intelligence.py::_persist_options_lifecycle_result` → `record_contract_observation` (old, unstaged code) | Yes — `AVSHUNTER_STAGE_GATING_ENFORCED=1` (orchestrator default, `intelligent_orchestrator.py:6127`), evening run aborted | `logs/orchestrator.log:1769801-1769833` (full traceback) + `data/canonical/control_plane.sqlite` (thesis stuck v1 terminal, 0 observations) | **Pre-fix** |
| 2 | `CART:PUT:2026-08-29` | CART | `20260829_222259` | 2026-08-30T00:48:39.22Z | EOD, same call site/defect as #1 | No — enforcement flag apparently off at that point; caught, logged as a warning, run continued and archived | `data/canonical/control_plane.sqlite` only (thesis stuck v1 terminal, 0 observations); no matching `CDS lifecycle warning` line found in `logs/orchestrator.log` despite that print statement existing in the code — **logging gap**, see §5 | **Pre-fix** |
| 3 | *(reproduced, not observed live)* `FLYW-PUT-2026-08-30` | FLYW | synthetic | n/a | Morning, `morning_gate.py::_persist_morning_liquidity_result` → `record_contract_observation`, current (never-fixed) code | Would be fatal under the same default-`1` enforcement flag (`intelligent_orchestrator.py:6127`, applies to both `--evening` and `--morning` per its own docstring) | `tests/rca/test_morning_gate_terminal_thesis_ordering.py` (passes today against unmodified `morning_gate.py`, proving the code still contains this exact defect) | **Structurally present in code currently on disk; not yet observed in a real run's logs or database** |

Only 16 distinct `thesis_id`s exist in `data/canonical/control_plane.sqlite` today; a
sweep of all of them for "terminal state with zero observations" (the data
fingerprint this bug leaves behind) found exactly the two rows above (#1, #2) and no
others — i.e. this defect class, while structurally present in two call sites, has
concretely fired twice in the data currently on disk.

A broader background sweep of every log/artifact directory in the repo (`audit/`,
`audit_baseline/`, `audits/`, `reports/`, `.pytest_cache/`, `.codex_test_temp/`,
`.codex_test_tmp/`, `tmpmvmp0agl/`, `tmpujgjsk2n/`, `data/output/**` including all
`runs/*/packages/` subtrees, `data/canonical/*.sqlite`) was run independently in
parallel with this analysis and returned before this document was finalized. It
found no occurrences beyond #1 and #2 above, and confirmed:

- The full database sweep: 17 rows in `option_thesis_events`, 12 in
  `option_contract_observations`, 12 in `option_contract_selection_events`, across
  16 distinct `thesis_id`s. **No `thesis_id` anywhere in the data has a terminal-state
  row followed by a later, higher-version non-terminal row** — i.e. no evidence of
  the store's own reactivation guard (`option_liquidity_lifecycle.py:592-593`) ever
  actually being needed/hit in this data. The only anomaly pattern (terminal thesis,
  zero matching observations) is exactly, and only, `FLYW:PUT:2026-08-30` and
  `CART:PUT:2026-08-29`.
- A repo-wide grep for `morning_liquidity_persistence_status`/`ERROR:DatasetValidationError`
  in `data/output/**` and for `"Morning liquidity lifecycle"` in `logs/` returned
  **zero matches anywhere** — independently confirming occurrence #3 (the
  `morning_gate.py` path) is a code-reading/reproduction-test finding only, never an
  observed production failure.
- **`canonical_data/option_liquidity_lifecycle.py` has no commit history at all**
  (`git log --all -- canonical_data/option_liquidity_lifecycle.py` returns nothing),
  and HEAD's (`5d886f0`) version of `scripts/avshunter_options_intelligence.py` has
  zero references to `record_contract_observation`/`record_thesis_event`. The entire
  OLM (option-liquidity-monitoring) feature — store, both writer call sites, and the
  2026-08-30 fix alike — is working-tree-only and has never been committed. There is
  no earlier committed revision of the guard to diff against.
- One additional, superficially similar but **distinct** error was found and should
  not be counted as an occurrence of this family: `logs/orchestrator.log:1767494-1767496`,
  ticker HST, run `20260830_071747`, 2026-08-30 08:20:08 local — `RuntimeError:
  Options liquidity lifecycle persistence failed for HST: dataset_id ... is
  immutable and already registered`, raised from `canonical_data/registry.py:233
  register_dataset`. Same wrapper text ("...persistence failed for {ticker}: ..."),
  but a different underlying invariant (dataset content-hash immutability, not
  thesis terminality) — unrelated to this RCA's scope.

## 2. Writer enumeration (Step 2)

The schema is owned by exactly one module, `canonical_data/option_liquidity_lifecycle.py`
(`class OptionLiquidityLifecycleStore`), and only three public methods ever write to
its three tables. A repo-wide search for direct SQL against
`option_thesis_events` / `option_contract_observations` / `option_contract_selection_events`
(excluding `backups/`, `Archive/`) found **no** call site outside this module — there
is no bypass of the store itself.

### 2a. Closers — transition a thesis to a terminal state

All closers ultimately call `OptionLiquidityLifecycleStore.record_thesis_event`
(`canonical_data/option_liquidity_lifecycle.py:518-633`), which is the sole INSERT
path for `option_thesis_events`. It enforces two things and only two things:

- `canonical_data/option_liquidity_lifecycle.py:546-549` — a terminal `thesis_state`
  must pair with `monitor_state=TERMINAL` and vice versa (payload-shape check only).
- `canonical_data/option_liquidity_lifecycle.py:592-593` — `if latest.thesis_state in
  TERMINAL_THESIS_STATES: raise OptionLifecycleConflict("terminal thesis cannot be
  reactivated")` — this stops a *second* closer call from reopening/re-closing an
  already-terminal thesis. It does **not** check whether any observation is
  pending/in-flight, and it runs on the version chain, not on any lock spanning
  multiple method calls.

Call sites that invoke it with a terminal `thesis_state`:

| Call site | file:function:line | Trigger | Context |
|---|---|---|---|
| C1 | `scripts/avshunter_options_intelligence.py:7745-7751` (`_persist_options_lifecycle_result`, `_record_eod_thesis_event` helper) | Contract provenance incomplete (`THESIS_ONLY_CONTRACT_PROVENANCE_INCOMPLETE`) and `thesis_state` happens to be terminal | Inside the per-ticker `for` loop at `scripts/avshunter_options_intelligence.py:8163`; returns immediately after, no observation attempted in this call |
| C2 | `scripts/avshunter_options_intelligence.py:7760-7767` (same function) | Liquidity state unsupported (`THESIS_ONLY_LIQUIDITY_STATE_UNSUPPORTED`) | Same loop; returns immediately, no observation attempted in this call |
| C3 | `scripts/avshunter_options_intelligence.py:7774-7789` then `~7893` (staged ACTIVE, then TERMINAL after observation+selection) | Full contract data present, terminal transition | Same loop. **This is the reordered/fixed sequence** — closer deferred to *after* the observer (C-obs-1 below) |
| C4 | `morning_gate.py:2627` (`_persist_morning_liquidity_result`) | Unconditional — first statement of substance in the function, runs for every ticker regardless of transition | Inside the per-ticker `for row in candidates:` loop at `morning_gate.py:2953`, itself inside a `try/except Exception` (`morning_gate.py:2966-2984`) that re-raises as `RuntimeError` when `liquidity_enforced` and otherwise logs a warning and continues to the next ticker |

C4 is the only closer call that is **not** deferred past its function's own
observation call — see §2c.

### 2b. Observers — write a contract observation

`OptionLiquidityLifecycleStore.record_contract_observation`
(`canonical_data/option_liquidity_lifecycle.py:635-842`) is the sole INSERT path for
`option_contract_observations`. Its only terminal-state defence is
`canonical_data/option_liquidity_lifecycle.py:744-745`:
`if latest_thesis.thesis_state in TERMINAL_THESIS_STATES: raise
DatasetValidationError("cannot observe a terminal thesis")` — evaluated against a
**fresh** `self.latest_thesis(thesis)` read at the top of this same call
(`canonical_data/option_liquidity_lifecycle.py:739`), so it always sees whatever the
most recent closer call already committed.

| Call site | file:function:line | Context |
|---|---|---|
| O1 | `scripts/avshunter_options_intelligence.py:7853` (`_persist_options_lifecycle_result`) | Runs after C3's staged ACTIVE write; the terminal close (end of C3) happens *after* this, so this read sees ACTIVE — safe by construction, post-fix |
| O2 | `morning_gate.py:2716` (`_persist_morning_liquidity_result`) | Runs after C4, no staging — if C4 just wrote a terminal state, this read sees it terminal and raises |

### 2c. Selection writer — no terminal guard at all

`OptionLiquidityLifecycleStore.record_selection_event`
(`canonical_data/option_liquidity_lifecycle.py:844-968`) never reads
`latest_thesis` and never checks `TERMINAL_THESIS_STATES`. It validates the
selection against the *observation* it references, not against the thesis. Both
production call sites (`scripts/avshunter_options_intelligence.py:7884`,
`morning_gate.py:2754`) run immediately after their respective observation call, so
today a selection event can only be reached once an observation has already
succeeded — but that is incidental (caller ordering), not enforced. **If any future
caller ever records a selection against an observation that predates a thesis's
closure without re-observing, the store will accept it silently.** This is a second,
narrower gap in the same family, not yet the cause of an observed failure.

### 2d. (closer, observer) pairing table

| Pair | Closer | Observer | Same call/run? | Ordering guaranteed? | Status |
|---|---|---|---|---|---|
| A | C1 or C2 (`scripts/avshunter_options_intelligence.py`) | O1 (same function, same call) | Same call | N/A — these closer branches `return` immediately; O1 is never reached in that same call | Safe (not because ordering is enforced, but because the branches are mutually exclusive with reaching the observer) |
| B | C3 (`scripts/avshunter_options_intelligence.py`, staged form) | O1 (same function, same call) | Same call | **Yes, by construction** (2026-08-30 fix: stage ACTIVE → observe → select → close terminal last) | Fixed for this call site |
| C | **C4 (`morning_gate.py:2627`)** | **O2 (`morning_gate.py:2716`, same function, same call)** | Same call | **No — closer runs first, unconditionally, with no staging** | **Confirmed broken.** Reproduced in `tests/rca/test_morning_gate_terminal_thesis_ordering.py`. This is occurrence-class #3 above |
| D | Any closer on day N (either script) | O2 on a later run for the same `thesis_id` | Different runs | Only indirectly: `record_thesis_event`'s own reactivation guard (`option_liquidity_lifecycle.py:592-593`) fires first and raises `OptionLifecycleConflict("terminal thesis cannot be reactivated")` inside C4 itself, before O2 is even reached | Fails closed, but with a *different* message than the one this RCA was scoped to, and morning_gate.py has no early "already terminal, reuse idempotently" short-circuit (unlike the EOD path's guard at `scripts/avshunter_options_intelligence.py:7668-7695`) to avoid hitting it at all |
| E | C1-C4 on day N | O1 on a later EOD run for the same `thesis_id` | Different runs | Protected — the reuse guard at `scripts/avshunter_options_intelligence.py:7668-7695` returns `TERMINAL_THESIS_ALREADY_RECORDED` before reaching O1 | Safe, but see §5 on masking |

`Archive/` was checked separately per the tasking's instruction: it contains no
reference to `option_liquidity_lifecycle` / `OptionLiquidityLifecycleStore`, and
nothing outside `Archive/` imports from it — it is not importable from any
production entrypoint and is excluded from the writer surface with no further
action needed.

No batch/retry loop was found that invokes either persist function more than once
per ticker within a single run (`_persist_options_lifecycle_result` and
`_persist_morning_liquidity_result` each have exactly one production call site, both
confirmed by a repo-wide grep for their names). The `audit/olm_test/_agent2_tc_runner.py`
script also calls all three store methods directly, but it is not imported by any
production entrypoint (`morning_gate.py`, `scripts/avshunter_options_intelligence.py`,
`intelligent_orchestrator.py`) — it is an ad-hoc validation harness, not a production
writer, and is out of scope for the writer surface.

## 3. Root cause, stated as a defect class

**"A terminal thesis accepts no further observations" is an invariant that spans two
independent writes (`record_thesis_event` and `record_contract_observation`) against
the same row, but it is enforced only inside the second write
(`canonical_data/option_liquidity_lifecycle.py:744-745`), by reading whatever the
first write already committed. There is no atomic unit of work, no lock, and no
check at close time for pending/in-flight observations. Every caller is individually
responsible for sequencing its own close-then-observe (or, correctly,
observe-then-close) — and the codebase currently has two independent production
callers of this store (`scripts/avshunter_options_intelligence.py` and
`morning_gate.py`), each with its own separately-written sequencing.** The
2026-08-30 fix corrected the sequencing in one caller (C3, above). It could not have
corrected C4 because C4 lives in a different file, is a separately-authored code
path, and nothing in the store or in the fix's own tests constrains callers in
general — only the one function that was edited.

The hypothesis given in the tasking is confirmed: multiple independent code paths
can both close a thesis and observe it, and any pairing of those paths in the wrong
order reproduces the fault. Pair C (§2d) is a live, currently-unfixed instance of
exactly that pairing, and it is armed under the same default enforcement flag
(`AVSHUNTER_STAGE_GATING_ENFORCED`, defaulted to `"1"` for both `--evening` and
`--morning` by `intelligent_orchestrator.py:6109-6127`) that made the FLYW EOD
failure fatal.

### Why the fix's 87 tests could not have caught this

The only test in the repository that exercises `morning_gate._persist_morning_liquidity_result`
is `tests/test_option_liquidity_lifecycle.py::test_morning_marketdata_quotes_append_without_a_second_database`
(`tests/test_option_liquidity_lifecycle.py:521-588`), and it only ever sets
`morning_transition_state` to `"EXECUTABLE_NOW"` — never `"THESIS_INVALIDATED"` or
`"MOVE_ALREADY_REALIZED"`. A repo-wide grep confirms no other test file calls this
function at all. The EOD-path regression test added alongside the 2026-08-30 fix,
`tests/test_option_liquidity_lifecycle.py::test_eod_terminal_result_persists_observation_before_closure_and_replays`
(line 155, thesis_id literally `"FLYW:PUT:2026-08-28"`), only drives
`scripts/avshunter_options_intelligence.py::_persist_options_lifecycle_result` — it
cannot exercise `morning_gate.py` because it patches
`options_intelligence._CDS_LIQUIDITY_STORE`, a module-level global private to that
file. **The fix's test coverage is scoped to exactly the one function it edited; the
sibling function with the identical defect was never in its blast radius.**

## 4. Recommended enforcement point (assessed, not implemented)

Two candidates, per the tasking:

**(a) Make close-with-final-observation one atomic unit of work, owned by one
function every caller must use.** Concretely: add something like
`OptionLiquidityLifecycleStore.close_thesis(thesis_id, *, final_observation=...,
final_selection=..., ...)` that internally does exactly what C3 now does by hand
(stage/observe/select, then close last) inside one method, and make
`record_thesis_event` reject being called directly with a terminal `thesis_state`
from outside the store (e.g. a private `_close_terminal` used only by this new
method, with the public `record_thesis_event` restricted to non-terminal states, or
an assertion inside it that a terminal `thesis_state` may only come from the new
method). **Migration cost:** both C3 (already correctly sequenced, would just call
the new method instead of hand-rolling it) and C4 (`morning_gate.py:2577-2766`,
currently has no staging at all) would need to change; C1/C2 (thesis-only closes
with no accompanying observation in the same call) would call it with no
observation args. This directly removes the defect class: there is no longer a
window between "closed" and "observed" that a second call site can violate, because
there is only one call site.

**(b) Make the close call itself refuse to close while an observation for that run
is pending/unflushed**, failing at `record_thesis_event` instead of later at
`record_contract_observation`. This is weaker for this specific bug: the failure
mode here is not "an observation was queued and the close jumped ahead of it" — it's
"the caller decided to close *before it had even tried* to record the final
observation." There is no observation "pending" at the time C4 calls
`record_thesis_event`; the violation is purely about call order within one Python
function, not about a race the store could detect from its own state. (b) would
mostly reduce to re-deriving something like `terminal_transition` on the store side
and refusing thesis-state terminal writes unless a same-transaction observation
accompanies them — which is really (a) with the atomicity requirement pushed into
the close call's signature rather than a new method name.

**Recommendation: (a).** It is the only option that removes the "caller must
remember the right order" property entirely, and the migration surface is small and
enumerable (exactly the four call sites in §2a plus the two in §2b/§2c). (b) alone
would still require every caller to be rewritten to pass its observation/selection
data into the close call to be useful, which is the same migration cost as (a)
without (a)'s benefit of a single, reusable, tested function.

## 5. Contributing findings

- **Logging gap:** `scripts/avshunter_options_intelligence.py:8171`'s
  `print(f"         → CDS lifecycle warning: {_lifecycle_error}")` for the
  non-enforced case does not appear to reach `logs/orchestrator.log` (occurrence #2,
  CART, has no corresponding line despite the DB proving the exception fired). This
  print is a bare `print()`, not routed through the `logging` module that the rest
  of the file uses (`log.warning(...)` in `morning_gate.py:2980`, by contrast, *is*
  routed through `logging` and would presumably reach a log file if
  `morning_liquidity_persistence_status` ever recorded `ERROR:DatasetValidationError`
  in production). Recommend routing this print through the same logger so silent
  (non-enforced) occurrences are traceable without a database sweep.
- **Test-coverage gap by path:** confirmed in §3 — `morning_gate.py`'s terminal
  transition + live-quote combination has zero test coverage anywhere in the repo
  before this RCA's `tests/rca/` addition.
- **The "reuse an already-terminal thesis" idempotency (pair E, §2d) can and does
  mask a genuine ordering violation.** Both FLYW:PUT:2026-08-30 and
  CART:PUT:2026-08-29 are now permanently `INVALIDATED`/terminal with **zero**
  observations recorded against them, in the live `data/canonical/control_plane.sqlite`.
  Any future EOD (or Morning) run that revisits either `thesis_id` will hit the
  reuse guard at `scripts/avshunter_options_intelligence.py:7668-7695`
  (`"TERMINAL_THESIS_ALREADY_RECORDED"`) and silently accept the terminal state as
  correct — there is no signal anywhere downstream that these two theses were closed
  without ever recording the observation that justified the closure. This is exactly
  the risk the tasking asked to be called out explicitly: idempotent reuse, as
  currently written, does not distinguish "correctly closed" from "closed by a race
  that dropped its own evidence."

## Evidence index

- `logs/orchestrator.log:1769760-1769833` — FLYW traceback and run abort, pre-fix.
- `data/canonical/control_plane.sqlite` — `option_thesis_events` /
  `option_contract_observations` tables; queried read-only via `sqlite3` (Python
  stdlib) for this document; 16 distinct `thesis_id`s total, 2 flagged (terminal +
  zero observations).
- `backups/terminal_lifecycle_persistence_prechange_20260830/avshunter_options_intelligence.py`
  vs `scripts/avshunter_options_intelligence.py` — diff establishes the fix's exact
  shape and its 21:25:46 write time.
- `tests/rca/test_morning_gate_terminal_thesis_ordering.py` — reproduction, passes
  against the unmodified repository as of this writing (`python -m unittest
  tests.rca.test_morning_gate_terminal_thesis_ordering -v` → 2 passed).
- `tests/test_option_liquidity_lifecycle.py:155-230` — the EOD-path regression test
  added with the fix (`test_eod_terminal_result_persists_observation_before_closure_and_replays`).
- `tests/test_option_liquidity_lifecycle.py:521-588` — the only test that exercises
  `morning_gate._persist_morning_liquidity_result`, and only for a non-terminal
  transition.
