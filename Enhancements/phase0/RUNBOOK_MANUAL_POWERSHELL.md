# Runbook — manual PowerShell runs

Status: P0-3 increment 1 (17 Sep 2026). Run from the repository root:

```powershell
cd C:\Users\ACKVerissimo\AVSHUNTER-Intelligence
```

## Transition period

Until ACK switches over, the existing commands remain valid:

```powershell
python intelligent_orchestrator.py --evening            # evening, after the macro/GEX steps
python intelligent_orchestrator.py --morning --plan-only # check existing_thesis_id = last completed session
python intelligent_orchestrator.py --morning            # ~15 minutes after the US open
```

## New launcher (increment 1)

The launcher runs the same legacy orchestrator, but first establishes a run context, sets the legacy flags from configuration, and applies the pre-flight gate.

```powershell
# Check only — runs nothing, writes a run context record
.\venv\Scripts\python.exe -m avshunter preflight --action BUILD
.\venv\Scripts\python.exe -m avshunter preflight --action REVALUE

# Evening (after the US close, before 09:00 UK)
.\venv\Scripts\python.exe -m avshunter run --action BUILD

# Morning (~15 minutes after the US open)
.\venv\Scripts\python.exe -m avshunter run --action REVALUE

# Explicit research run
.\venv\Scripts\python.exe -m avshunter run --action BUILD --mode RESEARCH
```

### What the pre-flight gate does

| Check | Effect when it fails |
|---|---|
| No other pipeline or backfill process running | **Refused** (any mode) |
| No untracked module imported by production code | **Refused** (any mode) |
| Action matches the session phase (BUILD outside regular hours; REVALUE premarket or regular) | **Refused** |
| REVALUE: the thesis to validate is for the last completed session | **Refused** (prevents validating a stale thesis) |
| Clean tree | PRODUCTION runs as **RESEARCH** (Option A) |
| HEAD has a `rel-YYYYMMDD-N` release tag | PRODUCTION runs as **RESEARCH** (Option A) |
| Interpreter is the repository venv | PRODUCTION runs as **RESEARCH** (Option A) |

Exit codes: `0` success / preflight passed, `2` configuration error, `3` refused, otherwise the legacy orchestrator's exit code.

Records: `data\output\run_contexts\<run_context_id>\run_context.json`, `config_snapshot.json`, and `run_completion.json` after a run.

### Known limits of increment 1

- A RESEARCH (downgraded) run is marked RESEARCH in the run context and completion record, but legacy run records (`run_meta.json`, ledger) are not yet marked — increment 2.
- The morning path is still legacy path A (`--morning`); the merged path with the post-Lab score integrity check is increment 2.
- No release tag exists yet: every PRODUCTION request currently runs as RESEARCH until ACK creates the first `rel-YYYYMMDD-N` tag.

## Macro manual-review inputs (outside the launcher, display only)

```powershell
python scripts\build_local_gex.py --session latest-completed
python build_macro_json.py
python bond_macro_intelligence.py --verbose
python scripts\rapid_rotation_flag.py
copy dropbox\macro\macro_intelligence_latest.json pipeline_interpreter\MA_Inputs\macro\
```
