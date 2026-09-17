# P0-3 — Run Context and Release Gate: Design

| Item | Value |
|---|---|
| Version | 1.0 (16 Sep 2026) |
| Status | **APPROVED by ACK (16 Sep 2026) with Option A** (gate failure downgrades PRODUCTION to RESEARCH) — implementation authorised. Interpreter choice (§6 item 7) still open. |
| Context | C0 Run Context |
| Governed by | Specification v1.1 §4 (run identity, decision clock), §20 (orchestrator), §23 (replay), §24 (authority), Appendix B; end-to-end design v2.0 S0, rules R7, R8; `CLAUDE.md` |
| Depends on | P0-2 configuration registry |

---

## 1. Purpose

Every run starts by establishing one immutable **RunContext**: which run, which decision clock, which completed session is evidence, which release and configuration. No context reads the wall clock or decides its own session; production runs only from a clean, identified release.

## 2. Current state (verified 16 Sep 2026)

| Area | Finding | Reuse? |
|---|---|---|
| Launch paths | **ACK runs the pipelines manually from PowerShell** (confirmed 16 Sep 2026); the `.bat` files are no longer used. Existing scripts: `run_evening.bat` and `run_premarket.bat` (set CDS flags `AVSHUNTER_CANONICAL_DATA_ENABLED`, `AVSHUNTER_CANONICAL_WRITE_THROUGH`, `AVSHUNTER_CDS2_OHLCV_MODE`, validate them, call `intelligent_orchestrator.py --evening/--morning`); `run.py` → `orchestrator/main.py` (older orchestrator); `orchestrator/run-avshunter.ps1` | Retire all four as entry points; the documented PowerShell commands (§3.6) are the only entry points |
| Manual evening sequence (ACK, 16 Sep 2026) | `python scripts\build_local_gex.py --session latest-completed` → `python build_macro_json.py` → `python bond_macro_intelligence.py --verbose` → `python scripts\rapid_rotation_flag.py` → `copy dropbox\macro\macro_intelligence_latest.json pipeline_interpreter\MA_Inputs\macro\` → `python intelligent_orchestrator.py --evening --data-mode EOD`. Morning: `python intelligent_orchestrator.py --morning` (path A below; validated with `--plan-only`). | Mapped in §3.6 |
| CDS flags — **correction** | `intelligent_orchestrator.py:7200-7222` (`configure_cds_runtime_for_orchestrator`) applies `setdefault` ON for `AVSHUNTER_CANONICAL_DATA_ENABLED`, `…_WRITE_THROUGH`, `AVSHUNTER_CDS2_OHLCV_MODE=ACTIVE`, stage gating and the price DB path whenever `--evening`/`--morning` is used; `morning_gate.py` has its own `configure_cds_runtime_for_morning_gate`. Manual PowerShell runs **do** run with canonical flags ON unless the shell overrides them. (The earlier statement that they were OFF is withdrawn.) | Launcher still sets and records them explicitly |
| Dynamic dispatch (verified with `--plan-only`, 16 Sep) | Dynamic-session flags come from the governed runtime profile (`AVSHUNTER_DYNAMIC_PLAN_ENABLED` true), so `--evening` and `--morning` always go through `orchestrator/dynamic_dispatcher.py`. `--data-mode EOD` is **ignored** (logged warning; evening data mode is derived AUTO). Evening plan at 2026-09-17 01:00Z: `BUILD_THESIS`, session 2026-09-16, `NORMAL_COMPLETED_SESSION`. Morning plan at 2026-09-17 13:45Z: `VALIDATE`, `POSTOPEN_CONTRACT_REFRESH`, stages UNDERLYING_VALIDATION → SURVIVOR_OPTION_REFRESH → DEVELOPING_MARKET_PROFILE → EXECUTION_GATE → PUBLISH_VALIDATION, ≈ 4,347 credits | Launcher uses the dispatcher; stops passing `--data-mode` |
| **Stale-thesis defect (morning)** | An explicit `--morning` (VALIDATE) does not check that the accepted thesis is for the last completed session. The plan above would validate thesis `book:20260914_214012` (session 09-14) on 09-17 although the last completed session is 09-16. Only `--auto` detects this (`THESIS_REFRESH_DUE` → BUILD_THESIS). `morning_gate.py` direct CLI has the same gap (uses `latest.json`) | Pre-flight check: REVALUE refuses (or downgrades to RESEARCH) when the thesis session ≠ last completed session |
| Morning entry paths (two, diverged) | **A — `python intelligent_orchestrator.py --morning`**: dispatcher plan persisted to `run_plans.sqlite` → `premarket_workflow` (`:6819`) → catalyst truth patch → `morning_gate.run_morning_gate(spread_threshold=25.0, mode from plan)` → `finalize_morning_handoff(sync_interpreter=True)`. **B — `python morning_gate.py [--run-id] [--preopen-thesis-check \| --postopen-contract-refresh]`**: own CDS defaults and API-key check → run id from `latest.json` → mode from wall-clock session snapshot → `run_morning_gate(spread_threshold=policy reviewable max)` → finaliser without sync → **post-Lab score integrity check** (fails the run if not PASS) → verified sync to Interpreter. A has plan persistence and the catalyst patch but no post-Lab integrity check; B has the integrity check but no persisted plan, no catalyst patch, a different spread threshold and wall-clock mode selection | One morning path in the launcher: dispatcher plan + catalyst patch + gate + finaliser + post-Lab integrity check + verified sync |
| Dependency record (verified 16 Sep) | `requirements.txt` is **empty**. Production (`C:\Python314`) has 55 packages; the old test venv (3.13) has 15 that production lacks (`arch`, `statsmodels`, `patsy`, `fastparquet`, `cramjam`, `fsspec`, `narwhals`, `polygon-api-client`, `reportlab`, `watchdog` + test tools). Production code touching them: `layer3_forward_variance.py:343` optional `arch` fallback (returns None in production); `orchestrator/report_generator.py` uses `reportlab` (legacy launcher, to retire) | New venv mirrors production exactly + test tools; pinned lock files committed |
| External editable package (verified 16 Sep) | Production user site-packages has `vanguard` 1.0.0 installed **editable from `C:\Users\ACKVerissimo\vanguard`** (outside the repo; freeze reference `git+…TVautomated@0c40e42`). From the repo root, `import vanguard` resolves to the repo's `vanguard/`; a process started from another working directory would import the external checkout (which fails on `contracts` import) | Not installed in the new venv; pre-flight import-graph check records the resolved location of every imported top-level package |
| Interpreter decision (ACK, 16 Sep) | **Rebuild the repository venv on Python 3.14**; production and tests both run from it | Staging venv built and verified first; swapped in after the backfill |
| Interpreter used in production (before) | `python` resolves to **`C:\Python314\python.exe` (Python 3.14)**, which has pandas 2.3.3 / pyarrow 23.0.0; the repository venv is Python 3.13 and is where tests run. Production and tests use different interpreters | Decision §6 |
| Shell environment | No `AVSHUNTER_*` variables in the User or Machine environment or in `.env`. (A first reading concluded the CDS flags were therefore OFF; **withdrawn** — see "CDS flags — correction": the orchestrator and `morning_gate.py` default them ON.) Any other script started directly (e.g. `build_local_gex.py`, backfill tools) gets `canonical_data/feature_flags.py` defaults (OFF) unless it applies its own defaults | Launcher sets flags from configuration for every process it starts |
| Flag capture gap | `run_meta.json` records the dynamic-session flags but **not** the CDS flags or the Python interpreter, so a run cannot prove which canonical mode it used | Fixed by §3.2 / §3.6: the launcher records interpreter and every `AVSHUNTER_*` value |
| Run identity | `run_meta.json` already records `code_identity` (commit, `dirty`, `git_describe`), `config_identity` (`profile_hash`, `release_id`, `governed_constants_sha256`), `run_condition` (`TEST` when dirty), `baseline_eligible`, `session_date`, `evidence_cutoff_utc` (`intelligent_orchestrator.py:2080-2120`) | Yes — fields map to RunContext |
| Run 0914 | `dirty: true`, `release_id: null`, `profile_hash: null` | — |
| Session calendar | `canonical_data/session_clock.py`: XNYS holidays, early closes, session bounds, `session_snapshot(now)` and `evaluate_freshness(..., now)` accept an explicit instant | **Yes** — core of the decision clock |
| Run planning | `domain/run_planning.py` (`RunPlan`, `resolve_run_condition`, `OperatorMode`, stable identities), `domain/session_authority.py` (`SessionPhase`, `EvidenceState`, `resolve_session_authority`) | Yes — reuse enums and resolution logic |
| Release gate | `orchestrator/dynamic_release.py`: gate evidence with artefact sha256, `assess_release` → NOT_READY / READY_FOR_LIVE_CYCLE / READY_FOR_CONTROLLED_PROMOTION | Yes — pattern for release evidence (clock injection needed: uses `datetime.now`) |
| Wall clock | 486 `datetime.now` / `date.today` / `utcnow` calls in 195 production files (5 in `domain/`) | Legacy not rewritten (strangler); banned in new packages |
| Replay | REPLAY operator mode raises (`intelligent_orchestrator.py:7427`); no replay runner | New contexts only (§3.6) |
| Tests | No `conftest.py`; tests import via `sys.path.insert` and read live `data/` | New package gets its own isolated test root |
| Packaging | No `pyproject.toml`; `domain/` holds 32 pure modules (mixed legacy and reusable) | New package introduced (§3.1) |
| Git tags | Only historical tags (`lab-v1.*`, `pre/post-tidy-20260904`, `vanguard-baseline`); no release tagging convention | New convention (§3.3) |

## 3. Design

### 3.1 Rebuild package layout

A new importable package for all rebuild contexts, installed in editable mode in the venv, so imports never use `sys.path`:

```text
pyproject.toml                    (new; package metadata, test paths)
avshunter/
  __init__.py
  c0_run/                         RunContext, DecisionClock, ReleaseIdentity, pre-flight, launcher
  config/                         P0-2 registry resolver and loader
  c1_market_data/                 (P0-4)
  c2_universe/                    (P0-5)
  c11_ledger/                     (P0-6)
  shared/                         units, ids, errors
  cli.py                          `python -m avshunter ...`
tests_rebuild/                    isolated tests for avshunter/ only (own conftest.py)
```

- Reused legacy assets (`canonical_data/session_clock.py`, `domain/run_planning.py`, `domain/session_authority.py`, `orchestrator/dynamic_release.py`) are **wrapped or copied behind the new interfaces with provenance noted**, not modified in place, so the legacy pipeline is unaffected.
- Domain modules inside `avshunter/` are pure: no pandas, files, SQLite, HTTP or wall clock; adapters live in `*/adapters/`.

### 3.2 RunContext aggregate (spec §4)

```text
run_id                       AVS-<YYYYMMDD>-<HHMMSS>-<action>-<short hash>
action                       BUILD (evening) | REVALUE (morning) | REPLAY | RESEARCH_ANALYSIS
operator_mode                PRODUCTION | RESEARCH
decision_clock_utc           the single authoritative instant for the run
market_session               XNYS session containing / preceding the clock
evidence_session             last completed XNYS session used as evidence
session_phase                PREMARKET | REGULAR | AFTER_HOURS | CLOSED (from session_clock)
data_as_of_utc               cut-off for datasets admissible to this run
environment                  host, python version, venv path hash
pipeline_version             package version
release_id                   release tag or null
commit_hash, clean_tree      from git
untracked_imports            list (must be empty for PRODUCTION)
config_snapshot_id           from P0-2
config_file_hashes           legacy config/*.json and governed constants sha256
feature_flags                resolved AVSHUNTER_* values (from the configuration registry, applied by the launcher)
shell_environment_flags      AVSHUNTER_* values found in the operator's shell before the launcher applied configuration (recorded; conflicts reported)
python_executable            interpreter path and version actually running
authority_ceiling            highest authority any context may exercise in this run
created_at_utc               wall clock at creation (recorded, never used for decisions)
```

- Created once by the launcher, written to `data/output/runs/<run_id>/run_context.json`, registered as a dataset, and passed explicitly to every context. Immutable.
- `created_at_utc` is the only wall-clock read and is never used in logic.

### 3.3 Release identity and clean tree

- **Release**: an annotated git tag `rel-YYYYMMDD-N` on a commit, created on ACK's instruction. `release_id` = tag name.
- **Clean tree** = all of: no modified or staged tracked files; no untracked files inside production code paths (`avshunter/`, `domain/`, `contracts/`, `canonical_data/`, `orchestrator/`, `scripts/`, `vanguard/`, root `*.py`); import graph of the entry point contains no untracked module (catches `worker3/lab_contract.py`-type failures). Data, output and `Enhancements/` folders are excluded.
- Clean-tree evaluation is an adapter (git commands); the result enters RunContext as facts.

### 3.4 Pre-flight gate

| Check | PRODUCTION | RESEARCH |
|---|---|---|
| Clean tree | required | recorded |
| HEAD is a release tag | required | recorded |
| No untracked imports | required | required (a clean checkout must run) |
| Configuration registry loads, lock valid, snapshot resolves for the session | required | required |
| Required legacy config files present, hashes recorded | required | required |
| Decision clock consistent with action (BUILD after close / before next open; REVALUE in REGULAR phase) | required | recorded |
| Phantom backfill or other writer not running on shared stores | required | required |

**Failure behaviour (decision requested, §6):**
- **Option A (recommended during migration):** a PRODUCTION request that fails the gate is **downgraded to RESEARCH**, with a banner in the run output and Lab, `baseline_eligible = false`, and its records written to the ledger as research records (not production evidence). This matches today's `run_condition = TEST` behaviour and keeps the evening run usable while releases are being established.
- **Option B (after cutover):** refuse to start.
Switching from A to B is a configuration change (`run.production_gate_failure_mode`).

### 3.5 Decision clock

- `DecisionClock` value object: `decision_clock_utc`, `market_session`, `evidence_session`, `session_phase`, built with `session_clock.session_snapshot(now=decision_clock_utc)`.
- Launcher sources: live runs use the wall clock **once** at start; replay and tests pass `--as-of-utc`.
- New packages: a test (AST scan) fails on any `datetime.now`, `date.today`, `datetime.utcnow`, `time.time` in `avshunter/` outside `c0_run/adapters/clock.py`.
- Legacy pipeline: receives the clock as `AVSHUNTER_DECISION_CLOCK_UTC` and the run context path as `AVSHUNTER_RUN_CONTEXT`; legacy wall-clock calls are not rewritten (they are retired with their stages) but RunContext records that the legacy stages are not clock-pure.

### 3.6 Launcher

```text
python -m avshunter run --action BUILD   [--as-of-utc ...] [--mode PRODUCTION|RESEARCH]
python -m avshunter run --action REVALUE [--as-of-utc ...] [--mode ...]
python -m avshunter run --action REPLAY  --as-of-utc ... --run-context <stored run_context.json>
python -m avshunter preflight [--mode PRODUCTION]         (gate only, no run)
```

Flow: build RunContext → pre-flight → write and register RunContext → run new-context shadow services (as they are delivered in later workstreams) → invoke the legacy orchestrator (`--evening` / `--morning`) with the RunContext environment → record completion status.

**Manual PowerShell entry points (ACK's way of running).** The launcher is the only supported way to start a run. It must work correctly from a plain PowerShell prompt with no environment preparation:

```powershell
cd C:\Users\ACKVerissimo\AVSHUNTER-Intelligence
.\venv\Scripts\python.exe -m avshunter preflight --action BUILD            # optional check, runs nothing
.\venv\Scripts\python.exe -m avshunter run --action BUILD                  # evening (after the close, before 09:00 UK)
.\venv\Scripts\python.exe -m avshunter run --action REVALUE                # morning (~15 min after the US open)
.\venv\Scripts\python.exe -m avshunter run --action BUILD --mode RESEARCH  # explicit research run
```

**Mapping of today's manual evening sequence:**

| Today | Under the new design |
|---|---|
| 0. `build_local_gex.py --session latest-completed` | Interim: still manual, but only valid once SPY/QQQ history is current (P0-1 backfill adds them) and must report `STALE` rather than COMPLETE when the session does not match (fix in P0-4). Target: GEX computed inside the run by C3 with the required evidence session. |
| 1–3. `build_macro_json.py`, `bond_macro_intelligence.py`, `rapid_rotation_flag.py` | **Macro manual-review inputs, outside the launcher.** Macro is display-only (spec §14). They stay in a separate "macro review" section of the runbook. The legacy evening and morning runs still read `bond_macro_state.json` and the macro JSON today; the launcher records their file hashes and freshness in RunContext, and during migration their absence is reported, not silently defaulted. New contexts never read them. |
| 4. `copy … macro_intelligence_latest.json pipeline_interpreter\MA_Inputs\macro\` | Manual-review input for the interpreter (display only). Stays in the macro review section; the launcher does not copy "latest" files (spec §4). |
| 5. `intelligent_orchestrator.py --evening --data-mode EOD` | `python -m avshunter run --action BUILD` (launcher passes `--evening --data-mode EOD` to the legacy orchestrator with configured flags) |
| Morning command (to be supplied) | `python -m avshunter run --action REVALUE` |

- **Flags come from configuration, not the shell.** The launcher resolves the legacy CDS flags (`AVSHUNTER_CANONICAL_DATA_ENABLED`, `AVSHUNTER_CANONICAL_WRITE_THROUGH`, `AVSHUNTER_CDS2_OHLCV_MODE`, `AVSHUNTER_HISTORICAL_PRICE_DB`) and dynamic-session flags from the P0-2 registry and sets them for the legacy orchestrator process. A manual run therefore behaves the same as the old `.bat` runs, regardless of what is set in the shell.
- If the shell already has an `AVSHUNTER_*` value that differs from configuration, the launcher uses configuration, records both, and prints a warning.
- **Interpreter**: one approved production interpreter, recorded in configuration (`run.production_interpreter`); the launcher refuses any other in PRODUCTION mode and records the interpreter in RunContext. Today production runs on `C:\Python314\python.exe` (3.14) while tests run in the venv (3.13) — see decision §6.
- The commands are documented in `Enhancements/phase0/RUNBOOK_MANUAL_POWERSHELL.md` (delivered with this workstream) and tested: a test starts the launcher in a clean subprocess environment with no `AVSHUNTER_*` variables and asserts the resolved flags equal configuration.
- **Retired as entry points**: `run_evening.bat`, `run_premarket.bat`, `run.py`, `orchestrator/main.py`, `orchestrator/run-avshunter.ps1` — quarantined after a caller check (scheduled tasks, other scripts, docs). If ACK later wants a shortcut script, it must only call the launcher.
- **REPLAY** applies to new contexts only (they are clock-pure and read registered datasets). The legacy pipeline cannot replay; its golden runs (P0-7) serve as shadow-comparison baselines, not replay targets. *Correction to the Phase 0 exit criterion "replay reproduces golden runs": this applies to new contexts; for the legacy pipeline it means golden snapshots are captured and comparable.*

### 3.7 Test isolation

- `tests_rebuild/conftest.py` for the new package only: injected clock fixture; temporary data root; configuration registry fixture; network blocked; access to real `data/` stores blocked.
- Legacy `tests/` untouched (many read live data today); run separately as now.
- Windows: short `--basetemp` configured in `pyproject.toml` for `tests_rebuild`.

## 4. Tests

1. RunContext determinism: same inputs (clock, git facts, registry) → same `run_id` hash component and identical context.
2. Session resolution across boundaries: weekend, XNYS holiday, early close, DST change, after close vs before open.
3. Gate matrix: each failing check → PRODUCTION downgraded (Option A) or refused (Option B); RESEARCH records only.
4. Clean-tree adapter on fixtures: modified file, untracked file in production path, untracked import, data-only changes (ignored).
5. Clock purity AST scan on `avshunter/`.
6. Launcher dry run (`preflight`) produces a RunContext without running stages.
7. Legacy hand-off: environment variables set from configuration; legacy exit code propagated.
8. Manual-shell parity: launcher started in a subprocess with an empty `AVSHUNTER_*` environment resolves the same flags as configuration; a conflicting shell value is overridden, recorded and warned.
9. Interpreter guard: PRODUCTION refuses a non-venv interpreter; RESEARCH records it.

## 5. Deliverables

- `pyproject.toml`, `avshunter/` package skeleton, editable install in the venv.
- `avshunter/c0_run/`: `RunContext`, `DecisionClock`, `ReleaseIdentity`, pre-flight gate, git and clock adapters, launcher CLI.
- `tests_rebuild/` with isolated `conftest.py` and tests (§4).
- `Enhancements/phase0/RUNBOOK_MANUAL_POWERSHELL.md` with the exact commands; legacy launchers (both `.bat` files, `run.py`, `orchestrator/main.py`, PS1) quarantined after a caller check.
- Registry entries (P0-2) for the legacy CDS and dynamic-session flags so the launcher sets them.
- Release tagging procedure documented in `Enhancements/phase0/`.

## 5a. Implementation status (17 Sep 2026)

**Increment 1 — done (new package only; legacy code unchanged):**

| Deliverable | Status |
|---|---|
| `pyproject.toml` (package metadata; no pytest section — root `pytest.ini` stays the single pytest config) | Done |
| `avshunter/c0_run/`: `model`, `clock` (decision clock), `preflight` (gate with Option A), `context`, `launcher`; adapters `clock` (only wall-clock reader), `git` (clean tree, release tag, untracked imports), `environment` (interpreter, shell flags, concurrent writers), `legacy` (read-only `--plan-only` thesis resolution, run hand-off), `storage` | Done |
| `python -m avshunter preflight\|run --action BUILD\|REVALUE [--mode]` | Done |
| Checks: concurrent writers (BLOCK), untracked imports (BLOCK), action vs session phase (BLOCK), stale thesis for REVALUE (BLOCK), clean tree / release tag / interpreter (Option A downgrade) | Done |
| Legacy flags set from configuration; shell conflicts overridden and warned | Done |
| Calendar session phase added to `avshunter/shared/xnys_calendar.py`, parity-tested against legacy `session_snapshot` (DST, early closes) | Done |
| Registry: `run.production_interpreter`, `run.production_code_paths` (PROVISIONAL, approval ACK-20260916-P0-3); lock extended by addition only | Done |
| P0-2 key-reference test (orphans allowed only for P0-4 pending consumers) | Done |
| `tests_rebuild`: 61 passed (Python 3.14 venv) | Done |
| Live pre-flight on the real repository (17 Sep ~04:30 UK): BUILD and REVALUE both correctly REFUSED while the B3 backfill was running; REVALUE resolved thesis `book:20260916_223756:2026-09-16` and passed the stale-thesis check | Done |
| `Enhancements/phase0/RUNBOOK_MANUAL_POWERSHELL.md` | Done |

Design refinement made during implementation: a stale thesis for REVALUE and a concurrent data writer **refuse** the run in every mode (a downgrade cannot make either safe or meaningful).

**Increment 2 — next (touches legacy code; after the 17 Sep morning run):**
- Single morning path: add the post-Lab score integrity check and verified Interpreter sync to `premarket_workflow` (path A), retire path B as an entry point.
- Legacy run records honour `AVSHUNTER_OPERATOR_MODE=RESEARCH` (run_meta `run_condition`, baseline eligibility, ledger production records).
- Caller check and quarantine of legacy launchers.
- First release tag procedure (`rel-YYYYMMDD-N`) on ACK instruction.

## 6. Decisions requested

1. Approve the design, including the new `avshunter/` package and `tests_rebuild/` isolated tests.
2. **Gate failure mode during migration:** Option A (downgrade to RESEARCH with banner; recommended) or Option B (refuse to start).
3. Release tag convention `rel-YYYYMMDD-N`, created only on ACK instruction.
4. Confirm quarantining all legacy launchers (`run_evening.bat`, `run_premarket.bat`, `run.py`, `orchestrator/main.py`, `orchestrator/run-avshunter.ps1`) after a caller check; manual PowerShell commands via the launcher become the only entry points.
7. **One interpreter for production and tests.** Recommended: rebuild the repository venv on Python 3.14 (the interpreter production already uses) from pinned `requirements.txt` plus test dependencies, then run both pipelines and tests from it. Alternative: keep 3.13 venv for both and move production onto it. Either way the same interpreter runs tests and production.
8. ~~Canonical flags~~ — withdrawn: the orchestrator already defaults them ON; the launcher sets and records the same values.
9. **Morning path**: approve a single launcher morning path combining A and B (§2), and the stale-thesis pre-flight check.
6. **Tell me the exact PowerShell commands you use today** for the evening and morning runs (interpreter and any environment variables you set), so the launcher reproduces them faithfully and I can confirm whether canonical write-through has been on in your manual runs.
5. Accept the clarified Phase 0 exit criterion for replay (§3.6).
