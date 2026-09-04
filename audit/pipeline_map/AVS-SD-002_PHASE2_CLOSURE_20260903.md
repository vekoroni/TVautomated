# AVS-SD-002 Rev 1.1 — Phase 2 Closure

Status: **PASS — authority boundaries implemented; dynamic dispatcher still disabled**  
Date: 2026-09-03

## Design review

Before implementation and again before acceptance, Phase 2 was checked against
Rev 1.1 §§4, 9–12, 14–16 and the AVS-AR-003 Wave 1/acceptance requirements.
The governing result is:

- external macro is advisory only;
- direction and completed-thesis geometry are frozen downstream;
- EV and R:R remain labelled research evidence and have no capital authority;
- immediate execution viability is separated from expiry-scenario profitability;
- production Lab and Interpreter paths consume governed evidence or fail closed.

## Implemented

- Discovery thresholds, state priors, tiers and sector lift are invariant to the
  external macro payload. Macro sector/regime fields remain visible as advisory
  context with an explicit zero core delta.
- Vanguard receives a deterministic core-regime compatibility payload while the
  real macro payload is retained separately as advisory context.
- Vanguard trade-governance macro transitions are advisory and cannot invalidate
  a thesis or grant/deny capital.
- Horizon routing works when macro is absent; macro cannot block, resize or choose
  a CALL/PUT route.
- Options verdict scoring no longer promotes or demotes from legacy R:R/EV.
- EOD tier and candidate authority no longer depend on R:R. Research scores remain
  labelled advisory values.
- One long-option quote policy owns spread denominator, thresholds and quote age.
- Morning Gate recomputes current execution viability from the current bid/ask;
  it cannot reuse an EOD viability label as current evidence.
- Scenario monetisability is explicitly `ADVISORY_SCENARIO_ONLY` and does not
  determine Morning or final execution permission.
- The final Execution Gate consumes the execution-viability state and verifies
  its exact contract identity.
- Frozen thesis fields are checked at the Morning handoff boundary.
- The Intelligence Lab withholds actionable rows when a governed book is absent.
- Interpreter production resolution remains manifest/evidence based; retired
  acquisition and alternative-selection paths remain unavailable.

## Safety and rollback

- Phase-specific pre-change backup:
  `backups/avs_sd_002_rev1_1_phase2_prechange_20260903_145500`.
- The Phase 0 whole-release snapshot at
  `backups/avs_sd_002_rev1_1_phase0_prechange_20260903_133546` is the authoritative
  rollback source for `vanguard/layer2_statistical/state_calculator.py` and
  `contracts/lab_control.py`, whose Phase 2 copies were not taken before editing.
- No production dispatcher flag was enabled.
- No Evening, Morning, Lab or Interpreter production artefact was executed or
  promoted in this phase.

## Verification

- Python compilation of every changed Python module: passed.
- Phase 2 focused authority tests: 14 passed, 0 failed.
- Macro Horizon Router embedded verification: 38 checks passed, 0 failed.
- Cross-stage Phase 0/1/2 and authority regression selection: 86 passed, 0 failed.
- `git diff --check`: no whitespace errors.
- Static acceptance checks: no R:R tier floor, no Morning fabricated zero quote
  age, no final Execution Gate monetisability authority, and no Lab legacy
  actionable fallback.

The repository-wide single-process pytest collection remains unsuitable as a
release result: existing tests mutate `sys.path`, causing `vanguard/scripts` to
replace the repository `scripts` package and producing collection errors. The
phase and cross-stage suites were run in isolated processes and are clean. The
full isolated-file regression matrix remains an end-to-end promotion activity.

## Exit decision

Phase 2 exit gate is satisfied. Authority separation is implemented, but this is
not yet a production-ready dynamic pipeline. Phases 3–8 and live-cycle evidence
remain required. All dynamic release flags remain disabled.
