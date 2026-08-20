# AVSHUNTER Pipeline Interpreter — Session State
# Last updated: 25 May 2026
# Status: ALL SYSTEMS CLEAN — ready for live trading sessions

## Build history

### Friday 22 May 2026 — Component 9
Built by Claude Code. All files verified clean 25 May 2026.
  - lab_reconciliation.py              CREATED  — 8 functions, zero engine imports
  - thesis_registry.py                 CREATED  — 7 functions, cross-session thesis lifecycle
  - pipeline_interpreter_engine.py     MODIFIED — MA_LAB constant, lab export folder creation
  - pipeline_interpreter_commands.py   MODIFIED — cmd_lab, /lab wired, lab context in /triage and /ticker
  - pipeline_interpreter_outputs.py    MODIFIED — write_triage_outputs lab card + LAB STATUS column
  - pipeline_interpreter_system_prompt.txt MODIFIED — INTELLIGENCE LAB CONFLICT RULES appended
  - interpreter_qa.py                  MODIFIED — check_lab_reconciliation_qa added
  - MA_Inputs/lab_export/              CREATED  — folder for lab export CSVs

### Monday 25 May 2026 — Entry Timing Engine + Junior Briefing Merge
Built by Claude Code. All 8 delivery checklist items green.
  - entry_timing_engine.py             CREATED  11KB — 5 functions, zero non-stdlib imports
  - entry_timing_engine_test.py        CREATED   1KB — 4 tests, all passing
  - pipeline_interpreter_commands.py   MODIFIED  78KB — ETE injected in /triage + /ticker, /ete command added
  - pipeline_interpreter_outputs.py    MODIFIED  63KB — write_all_outputs_with_junior + _build_junior_section_cards
  - pipeline_interpreter_engine.py     MODIFIED  65KB — pre_trade_prob_block param added to 2 prompt builders
  - pipeline_interpreter_system_prompt.txt MODIFIED 47KB — PRE-TRADE PROBABILITY section appended

### Monday 25 May 2026 (session 2) — Gap Fixes + Phantom-to-Production Upgrade
Built by Claude Code. All 7 modules import clean.
  - pipeline_interpreter_engine.py     MODIFIED — call_api max_tokens override param; build_story_prompt
                                                   leads with "OUTPUT FORMAT: Produce ONLY JUNIOR_BRIEFING"
  - pipeline_interpreter_commands.py   MODIFIED — story call uses max_tokens=12000; sidecar write wired;
                                                   evening baseline save wired (EVENING session mode)
  - pipeline_interpreter_outputs.py    MODIFIED — _extract_junior_section regex \Z fix; json import;
                                                   write_interpreter_sidecar + load_interpreter_sidecar added
  - pipeline_interpreter_system_prompt.txt MODIFIED — EXCEPTION clause added for ONLY JUNIOR_BRIEFING output
  - entry_timing_engine.py             MODIFIED — GAP 2: field aliases (signal_price, underlying_price,
                                                   exit_stop_price, invalidation_price); IVP decimal fix;
                                                   GAP 3: assess_garch_availability (NOT_RUN/PROPAGATION_GAP/LIVE);
                                                   Phantom 2: compute_entry_quality added
  - lab_reconciliation.py              MODIFIED — GAP 4: load_lab_export fallback to lab_triage_view_*.csv
                                                   in MA_Inputs/pipeline_outputs/; _normalise_lab_triage_view_row
  - thesis_registry.py                 MODIFIED — Phantom 4: save_evening_baseline, load_evening_baseline,
                                                   compute_morning_delta (MINIMAL/MODERATE/SIGNIFICANT/EXCEPTION)
  - prepare_interpreter_session.py     MODIFIED — session_mode EVENING/MORNING (was eod/morning);
                                                   morning delta scan added
  - interpreter_qa.py                  MODIFIED — check_delta_qa, check_delta_qa_batch added
  - morning_thesis_validator.py        MODIFIED — load_interpreter_sidecar, apply_interpreter_overlay,
                                                   enrich_candidates_with_sidecars added
  - catalyst_conflict_engine.py        CREATED  — Phantom 3: CatalystConflict, CatalystConflictResult,
                                                   detect_catalyst_conflicts, load_and_detect,
                                                   format_conflict_block (at base dir, shared module)
  - MA_Inputs/thesis_baselines/        AUTO-CREATED by thesis_registry.py save_evening_baseline

## What /ticker TICKER now produces

One unified HTML file containing three layers:
  1. Dr. Magnus Vale deep dive
  2. PRE-TRADE PROBABILITY ASSESSMENT card (crowd stage, p_trigger, kill switch breach, GARCH status)
  3. Junior Trader 8-section briefing (MACRO, GAMMA, LIQUIDITY, THESIS, CHART, OPTIONS, RISK, VERDICT)

Output path: pipeline_interpreter/outputs/ticker_TICKER_interpreter_TS.html

In EVENING session mode (--eod), also writes:
  - data/output/runs/{run_id}/interpreter/{run_id}_{TICKER}_interpreter.json  (sidecar)
  - MA_Inputs/thesis_baselines/{TICKER}_evening_baseline.json                 (delta baseline)

## Current file inventory (all confirmed importable)

  lab_reconciliation.py
  thesis_registry.py
  entry_timing_engine.py
  entry_timing_engine_test.py
  pipeline_interpreter.py
  pipeline_interpreter_engine.py
  pipeline_interpreter_commands.py
  pipeline_interpreter_outputs.py
  pipeline_interpreter_system_prompt.txt
  interpreter_qa.py
  prepare_interpreter_session.py
  pipeline_interpreter_engine_backup_20260522.py
  MA_Inputs/lab_export/              (avshunter_signals_*.csv OR auto-fallback to lab_triage_view_*.csv)
  MA_Inputs/thesis_registry/         (auto-created by thesis_registry.py)
  MA_Inputs/thesis_baselines/        (auto-created by thesis_registry.save_evening_baseline)

Base directory (shared modules):
  catalyst_conflict_engine.py        (Phantom 3 — consumed by interpreter + EIL Phase 8)

## Daily workflow

Evening (after orchestrator run):
  python prepare_interpreter_session.py --eod
  python pipeline_interpreter.py
  /triage
  /ticker TICKER   (produces unified HTML — all three layers + sidecar JSON + evening baseline)
  /ete TICKER      (standalone probability report to terminal)

Morning (after morning_thesis_validator.py --live):
  python prepare_interpreter_session.py --morning   (also runs delta scan)
  python pipeline_interpreter.py
  /triage
  /ticker TICKER

## Key rules (non-negotiable)
- Interpreter is informative only. Never blocks or gates trades.
- Morning Validation is the ONLY output that can authorise trade review.
- EXECUTION_PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY
- CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION
- MINIMAL delta is the expected norm — SIGNIFICANT/EXCEPTION signals upstream scoring weakness
- Sidecar JSON is additive — morning validator functions without it if interpreter didn't run
- NO_BASELINE in morning mode is an exception — surface explicitly, never treat as cold start
- Catalyst override is GO→GO_LIMIT only — never BLOCKED; capital denial is trader's decision

## If starting a new build session
Read this file first, then confirm all imports pass before touching any file.
Run the verification suite:
  python -c "from lab_reconciliation import load_lab_export; print('lab_reconciliation: OK')"
  python -c "from thesis_registry import get_active_thesis, save_evening_baseline, compute_morning_delta; print('thesis_registry: OK')"
  python -c "from entry_timing_engine import build_pre_trade_probability_block, assess_garch_availability, compute_entry_quality; print('entry_timing_engine: OK')"
  python -c "from pipeline_interpreter_commands import route_command; print('commands: OK')"
  python -c "from pipeline_interpreter_outputs import write_all_outputs_with_junior, write_interpreter_sidecar; print('outputs: OK')"
  python -c "import sys; sys.path.insert(0,'..'); import catalyst_conflict_engine; print('catalyst_conflict_engine: OK')"
  python -c "from interpreter_qa import check_delta_qa; print('interpreter_qa delta: OK')"
