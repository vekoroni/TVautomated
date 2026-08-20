# CLAUDE_CODE_AVSHUNTER_PIPELINE_FIXES_v1.md
# AVSHUNTER Pipeline Fix Sprint — Issue Register B1 / B2 / B3 / B4 / RUN1 / RUN3 / RUN4 / UX1
# Makeo Consulting Limited · ACK Verissimo · May 2026
# ─────────────────────────────────────────────────────────────────────────────
# TRIGGER: Read this file and execute all steps in order.
#          Begin with Step 0 audit and report findings before making any changes.
# ─────────────────────────────────────────────────────────────────────────────

## CONTEXT — WHAT THIS SPRINT DOES

This sprint resolves the confirmed open issues from the backend audit of run
20260516_142652 and the UAT stress test of run 20260509_171946.

The four CRITICAL hard blockers preventing live capital deployment are:

  B1 — Live contract Greeks (gamma, theta, iv, bid, ask, mid, spread_pct)
       not flowing from Options Intelligence into morning_candidates CSV
  B2 — EIL BLOCKED verdicts not filtered from morning_candidates — 50 blocked
       tickers are reaching the candidate manifest and the /triage command
  B3 — FinalDecision layer overwriting all EIL verdicts to WATCHLIST —
       fd_verdict=WATCHLIST for all 1317 rows, signal hierarchy invisible
  B4 — GARCH jump risk flag (l3_jump_risk_flag) not propagating from
       eil_enriched into morning_candidates — 22 actionable tickers carry
       invisible jump risk

Additional issues addressed:

  RUN1 — Handoff contract audit failing (5 FAIL, 12 WARN) — identify and fix
          the specific breaking stage-to-stage contracts
  RUN3 — macro_quant_packet.py:812 FutureWarning — string assigned to float64
          column — will become a hard error in future pandas
  RUN4 — eil_eod_resolver.py not deployed — EOD cross-sectional enrichment
          degraded to single-row fallback on every evening run
  UX1  — Capital-lock language (NO_LIVE_CAPITAL_EOD, PSE_IGNORED_MANUAL_SIZING)
          displayed to trader as a system block rather than a human review prompt

## GOVERNING RULES

1. Show exact diff before saving any file.
2. After each step confirm which files changed and which lines changed.
3. Never rewrite surrounding logic — apply targeted patches only.
4. Validate Python syntax (ast.parse) after every change to a .py file.
5. If a fix requires a design decision not covered here, stop and ask.
6. Never modify: garch_runner.py, vanguard core files, actuarial_cache_builder.py,
   macro_horizon_router.py, avshunter_discovery_ULTIMATE.py,
   avshunter_options_intelligence.py (unless explicitly instructed below).
7. Every change must be backward compatible — pipeline continues if a fix
   partially fails rather than crashing the run.

---

## STEP 0 — AUDIT (NO CHANGES)

Report findings before touching anything.

**0.1 Morning manifest builder — locate the Phase 10 candidate export:**
- Search intelligent_orchestrator.py for where morning_candidates_{run_id}.csv
  is written
- Report the exact line numbers
- Report which columns are included in the export at that point
- Confirm whether contract_gamma, contract_theta, contract_iv, contract_bid,
  contract_ask, contract_mid, contract_spread_pct are in the export or absent
- Confirm whether l3_jump_risk_flag and other l3_ fields are in the export
  or absent
- Confirm whether eil_v3_verdict is in the export

**0.2 EIL BLOCKED filter — confirm gap:**
- Search intelligent_orchestrator.py for where the morning candidates manifest
  is assembled from eil_enriched data
- Confirm whether any filter on eil_v3_verdict is applied before writing
- Report the exact line numbers of the assembly and write step

**0.3 FinalDecision engine — locate the verdict assignment:**
- Read final_decision_engine.py in full
- Report: what inputs does it consume?
- Report: what field does it write fd_verdict from?
- Confirm whether it reads eil_v3_verdict or ignores it
- Report the exact line where fd_verdict is assigned

**0.4 EIL output schema — confirm what fields execution_intelligence_runner.py writes:**
- Search execution_intelligence_runner.py for where fd_verdict is written
  to the output row
- Confirm whether fd_verdict is written as a copy of eil_v3_verdict or
  assigned independently
- Report line numbers

**0.5 Pipeline Interpreter /triage — confirm BLOCKED filter gap:**
- Read pipeline_interpreter/pipeline_interpreter_commands.py
- Find the /triage command handler
- Confirm whether it filters on eil_v3_verdict before ranking candidates
- Report line numbers

**0.6 macro_quant_packet.py line 812 — confirm the dtype warning:**
- Read scripts/macro_quant_packet.py around line 812
- Report the exact assignment that triggers the FutureWarning
- Confirm the column name and the type being assigned

**0.7 eil_eod_resolver.py — confirm it is absent:**
- Confirm the file does not exist at:
  C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\eil_eod_resolver.py
- Report whether a partial or template version exists anywhere in the project

**0.8 Handoff contract audit — identify failing contracts:**
- Find the most recent handoff_contract_audit_*.csv in data/output/runs/
- Read it and report all rows where status=FAIL
- Report the stage_from, stage_to, field_name, and failure_reason for each
  of the 5 failing contracts

**0.9 Intelligence Lab frontend — locate display label strings:**
- Search for the Intelligence Lab frontend files:
  data/intelligence_lab/ OR pipeline_interpreter/ OR any .html/.js file
  containing NO_LIVE_CAPITAL_EOD or fd_verdict
- Report the file paths and line numbers where these strings appear

Report all findings. Do not change any file.

---

## STEP 1 — B2: FILTER EIL BLOCKED FROM MORNING CANDIDATES MANIFEST

**File:** intelligent_orchestrator.py
**Risk:** LOW — additive filter. Removes BLOCKED tickers from candidate manifest.
          BLOCKED tickers are written to a separate audit CSV, not discarded.
**Dependency:** Step 0.1 and 0.2 must confirm the exact assembly location first.

**Based on Step 0 findings, apply this change at the manifest assembly step:**

Find where the morning_candidates DataFrame is assembled from eil_enriched.
Before the manifest is written to CSV, add the BLOCKED filter:

```python
# B2 FIX: Remove EIL BLOCKED rows from morning candidates manifest
# BLOCKED tickers are written to a separate audit file for review
_blocked_mask = morning_df['eil_v3_verdict'] == 'BLOCKED'
_blocked_count = _blocked_mask.sum()
if _blocked_count > 0:
    _blocked_df = morning_df[_blocked_mask].copy()
    _blocked_path = output_dir / f"morning_blocked_review_{run_id}.csv"
    _blocked_df.to_csv(_blocked_path, index=False)
    logger.info(f"B2 FILTER: {_blocked_count} BLOCKED tickers removed from candidates "
                f"-> morning_blocked_review_{run_id}.csv")
morning_df = morning_df[~_blocked_mask].copy()
```

Replace `morning_df` with the actual DataFrame variable name found in Step 0.2.
Replace `output_dir` and `run_id` with the actual variable names in scope.

Show diff before saving. Confirm syntax valid after change.

---

## STEP 2 — B2: FILTER EIL BLOCKED IN /TRIAGE COMMAND

**File:** pipeline_interpreter/pipeline_interpreter_commands.py
**Risk:** LOW — additive filter on load. Does not affect the CSV on disk.
**Dependency:** Step 0.5 must confirm the exact /triage load location first.

**Based on Step 0 findings, add the filter in the /triage command handler
immediately after the morning_candidates CSV is loaded:**

```python
# B2 FIX: Filter BLOCKED tickers from triage session
# These should not have reached morning_candidates but filter defensively
if 'eil_v3_verdict' in _triage_df.columns:
    _blocked_in_triage = (_triage_df['eil_v3_verdict'] == 'BLOCKED').sum()
    if _blocked_in_triage > 0:
        print(f"  ⚠  B2 GUARD: {_blocked_in_triage} BLOCKED tickers excluded from triage ranking")
        _triage_df = _triage_df[_triage_df['eil_v3_verdict'] != 'BLOCKED'].copy()
```

Replace `_triage_df` with the actual DataFrame variable name in the /triage handler.

Show diff before saving. Confirm syntax valid after change.

---

## STEP 3 — B3: RE-WIRE FINALDECISION TO CONSUME EIL VERDICT DISTRIBUTION

**File:** final_decision_engine.py
**Risk:** MEDIUM — changes the verdict arbitration logic. Read the full file
          before applying. If the existing structure does not fit cleanly,
          stop and report rather than forcing the pattern.
**Dependency:** Step 0.3 and 0.4 must confirm the exact verdict assignment
               location first.

**The problem:** fd_verdict is being set to WATCHLIST for all rows regardless
of eil_v3_verdict. FinalDecision should pass eil_v3_verdict through as fd_verdict
when PSE is retired (manual sizing mode).

**Based on Step 0 findings, find the fd_verdict assignment and apply:**

If fd_verdict is being set to a hardcoded value or a default that ignores
eil_v3_verdict, change it to:

```python
# B3 FIX: FinalDecision passes eil_v3_verdict through when PSE is retired
# PSE retirement means manual sizing only — it does not mean collapsing
# all verdicts to WATCHLIST
_eil_verdict = row.get('eil_v3_verdict', 'WATCHLIST')
fd_verdict = _eil_verdict if _eil_verdict in (
    'EXECUTE', 'EXECUTE_WITH_CAUTION', 'BLOCKED', 'WATCHLIST'
) else 'WATCHLIST'

# fd_size remains 0.0 in manual sizing mode — PSE is retired
fd_size = 0.0
fd_reason = f"PSE_RETIRED_MANUAL_SIZING — eil_v3_verdict={_eil_verdict} passed through"
```

Replace `row` with the actual row/dict variable name in the FinalDecision loop.

If the FinalDecision engine is not iterating rows at all (e.g. it is only
called once and writes a summary), report this and propose an alternative
approach rather than applying the patch blindly.

Show diff before saving. Confirm syntax valid after change.

---

## STEP 4 — B1: ADD MISSING CONTRACT FIELDS TO MORNING MANIFEST EXPORT

**File:** intelligent_orchestrator.py
**Risk:** LOW — additive schema change. If fields are absent from eil_enriched,
          they are written as empty strings rather than causing a crash.
**Dependency:** Step 0.1 must confirm the exact export column list first.

**The seven missing fields to add to the morning manifest export schema:**
  contract_gamma, contract_theta, contract_iv,
  contract_bid, contract_ask, contract_mid, contract_spread_pct

**Based on Step 0 findings, find where the morning_candidates export column
list is defined. Add the seven fields to that list:**

If the export uses an explicit column list like:
```python
EXPORT_COLS = ['ticker', 'eil_v3_verdict', 'contract_delta', ...]
```

Add to that list:
```python
# B1 FIX: Add live contract Greeks to morning manifest export
'contract_gamma', 'contract_theta', 'contract_iv',
'contract_bid', 'contract_ask', 'contract_mid', 'contract_spread_pct',
```

If the export uses df.to_csv() with all columns, confirm the source DataFrame
already contains these fields from the eil_enriched join. If not, add an
explicit join from options_intelligence_latest.csv at the manifest build step:

```python
# B1 FIX: Join missing contract Greeks from OI CSV into morning manifest
_oi_path = (output_dir / "options" /
            f"options_intelligence_{run_id}.csv")
if _oi_path.exists():
    _oi_df = pd.read_csv(_oi_path, low_memory=False)
    _greek_cols = ['ticker', 'contract_gamma', 'contract_theta', 'contract_iv',
                   'contract_bid', 'contract_ask', 'contract_mid',
                   'contract_spread_pct']
    _greek_cols_present = [c for c in _greek_cols if c in _oi_df.columns]
    if len(_greek_cols_present) > 1:
        morning_df = morning_df.merge(
            _oi_df[_greek_cols_present].drop_duplicates('ticker'),
            on='ticker', how='left', suffixes=('', '_oi')
        )
        logger.info(f"B1 FIX: Joined {len(_greek_cols_present)-1} contract Greek "
                    f"fields into morning manifest")
```

Replace variable names to match actual code. Show diff before saving.
Confirm syntax valid after change.

---

## STEP 5 — B4: ADD L3_ JUMP RISK FIELDS TO MORNING MANIFEST EXPORT

**File:** intelligent_orchestrator.py
**Risk:** LOW — additive schema change. Same pattern as Step 4.
**Dependency:** Step 0.1 must confirm l3_ fields are present in eil_enriched.

**The l3_ fields to add to the morning manifest export:**
  l3_jump_risk_flag, l3_garch_vol_forecast, l3_vol_regime_label
  (add all l3_ fields present in eil_enriched — do not hardcode a subset)

**Based on Step 0 findings, find where morning_candidates is assembled from
eil_enriched. Add the l3_ fields to the export:**

If eil_enriched already contains l3_ fields (confirmed in audit: 12 l3_ fields
merged at 1317/1317), they just need to be included in the export.

Add to the export column list or confirm all columns are passed through:
```python
# B4 FIX: Include all l3_ GARCH fields in morning manifest export
# l3_jump_risk_flag is critical — 22 EOD_CANDIDATE_ONLY tickers carry jump risk
_l3_cols = [c for c in eil_df.columns if c.startswith('l3_')]
if _l3_cols:
    logger.info(f"B4 FIX: Including {len(_l3_cols)} l3_ GARCH fields in "
                f"morning manifest: {_l3_cols}")
```

Replace `eil_df` with the actual eil_enriched DataFrame variable name.
Show diff before saving. Confirm syntax valid after change.

---

## STEP 6 — RUN3: FIX DTYPE FUTUREWARNING IN macro_quant_packet.py

**File:** scripts/macro_quant_packet.py
**Risk:** SAFE — dtype cast only, no logic change
**Dependency:** Step 0.6 must confirm the exact line and column name first.

**The problem:** String values (macro JSON path, timestamps) are being assigned
into float64 columns via df.loc[mask, field] = df.loc[mask, alt].
This fires a FutureWarning on line 812 and will become a hard error in a
future pandas version.

**Based on Step 0 findings, find the assignment at line ~812 and apply:**

```python
# RUN3 FIX: Cast column to object dtype before string assignment
# Prevents FutureWarning: Setting an item of incompatible dtype
df[field] = df[field].astype(object)
df.loc[mask, field] = df.loc[mask, alt]
```

If the same pattern appears multiple times on or near line 812, apply the
fix to all instances. Report each line changed.

Show diff before saving. Confirm syntax valid after change.

---

## STEP 7 — RUN4: DEPLOY eil_eod_resolver.py STUB

**File:** eil_eod_resolver.py (new file — create at AVSHUNTER-Intelligence root)
**Risk:** SAFE — new file. Existing fallback remains active until this file
          is fully implemented. The stub below is enough to stop the
          "not found" warning and establish the interface.
**Dependency:** Step 0.7 must confirm the file is absent first.

**Create this file at the AVSHUNTER-Intelligence root:**

```python
"""
eil_eod_resolver.py
AVSHUNTER Execution Intelligence Layer — EOD Cross-Sectional Resolver
Makeo Consulting Limited · May 2026

Provides cross-sectional enrichment for EOD runs.
When deployed, EIL uses this instead of the local _enrich_ctx_for_eod()
fallback inside _process_row().

Current status: STUB — interface established, cross-sectional logic pending.
The stub returns the row unchanged so the pipeline continues without error.
Full implementation: Phase 2 of the fix sprint.
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


def resolve_eod_context(
    row: dict[str, Any],
    discovery_df=None,
    options_df=None,
    actuarial_df=None,
    run_id: str = "",
) -> dict[str, Any]:
    """
    Enrich a single EIL row with cross-sectional EOD context.

    Parameters
    ----------
    row          : The current signal row dict from eil_enriched
    discovery_df : Full discovery candidates DataFrame for this run
    options_df   : Full options intelligence DataFrame for this run
    actuarial_df : Actuarial cache DataFrame
    run_id       : Current canonical run ID

    Returns
    -------
    Enriched row dict. Stub returns row unchanged.
    """
    # STUB: cross-sectional enrichment logic to be implemented in Phase 2
    # When implemented this will add:
    #   - Sector clustering context (how many tickers in same sector/direction)
    #   - Correlated regime moves (macro regime consistency check)
    #   - Cross-sectional IV rank (ticker IV vs sector IV distribution)
    logger.debug(f"eil_eod_resolver: stub pass-through for {row.get('ticker','?')}")
    return row


def resolve_eod_context_batch(
    rows: list[dict[str, Any]],
    discovery_df=None,
    options_df=None,
    actuarial_df=None,
    run_id: str = "",
) -> list[dict[str, Any]]:
    """
    Batch version of resolve_eod_context.
    Processes all rows for a run at once for cross-sectional analysis.

    Stub: delegates to single-row resolver.
    """
    return [
        resolve_eod_context(row, discovery_df, options_df, actuarial_df, run_id)
        for row in rows
    ]
```

After creating the file:
- Confirm it exists at the AVSHUNTER-Intelligence root
- Confirm Python syntax is valid
- Confirm the EIL runner will find it on next run (search execution_intelligence_runner.py
  for where it checks for eil_eod_resolver.py and confirm the path matches)

---

## STEP 8 — RUN1: FIX HANDOFF CONTRACT AUDIT FAILURES

**Files:** intelligent_orchestrator.py (and any stage files identified in Step 0.8)
**Risk:** MEDIUM — depends on which contracts are failing. Apply fixes one at
          a time and report after each.
**Dependency:** Step 0.8 must identify the 5 failing contracts first.

**Based on Step 0.8 findings, for each FAIL row in the handoff audit:**

1. Read the audit row: stage_from, stage_to, field_name, failure_reason
2. Find where stage_from writes field_name in its output CSV
3. Find where stage_to reads field_name from its input CSV
4. Identify the mismatch: missing field, wrong dtype, null values, renamed field
5. Apply the minimum fix to close the gap
6. Report the exact change made

Common patterns to look for:
- Field written by stage A under one name, read by stage B under a different name
- Field present in source DataFrame but not included in the to_csv() export
- Field arriving as NaN/null because a join is left-joining on a key with no match
- Field dtype mismatch (int vs float, string vs bool)

Apply each fix individually. Show diff before saving each one.
Confirm syntax valid after each change. Do not batch all 5 into one edit.

---

## STEP 9 — UX1: RELABEL CAPITAL-LOCK DISPLAY STRINGS

**Files:** Intelligence Lab frontend file(s) and pipeline_interpreter_engine.py
          (exact paths confirmed by Step 0.9)
**Risk:** SAFE — display label strings only, no logic change

**Based on Step 0.9 findings, replace these display strings:**

| Find | Replace with |
|------|-------------|
| NO_LIVE_CAPITAL_EOD | PENDING HUMAN REVIEW |
| PSE_IGNORED_MANUAL_SIZING | MANUAL SIZING MODE |
| candidate_size = 0.0 (displayed as label) | SIZE: MANUAL — SET AT OPEN |
| NO LIVE CAPITAL (any variant) | PENDING HUMAN REVIEW |

Apply as simple string replacements in the display layer only.
Do not change the underlying data field values — only the labels shown to the trader.

Show diff before saving. Confirm no logic paths were affected.

---

## STEP 10 — STANDALONE VALIDATION

**Run these checks after all steps are complete:**

**10.1 Syntax check all modified Python files:**
```powershell
python -c "
import ast, pathlib
files = [
    'intelligent_orchestrator.py',
    'final_decision_engine.py',
    'pipeline_interpreter/pipeline_interpreter_commands.py',
    'scripts/macro_quant_packet.py',
    'eil_eod_resolver.py',
]
for f in files:
    p = pathlib.Path(f)
    if p.exists():
        try:
            ast.parse(p.read_text(encoding='utf-8'))
            print(f'  OK  {f}')
        except SyntaxError as e:
            print(f'  FAIL {f}: {e}')
    else:
        print(f'  SKIP {f} (not found)')
"
```
Expected: OK for all files that were modified.

**10.2 Confirm eil_eod_resolver.py is importable:**
```powershell
python -c "import eil_eod_resolver; print('eil_eod_resolver: OK')"
```
Expected: eil_eod_resolver: OK

**10.3 Confirm FinalDecision change compiles:**
```powershell
python -c "import final_decision_engine; print('final_decision_engine: OK')"
```
Expected: OK without import errors.

**10.4 Run the evening pipeline:**
```powershell
python intelligent_orchestrator.py --evening
```

**10.5 Check the pipeline log for these confirmation strings:**
```
B2 FILTER: N BLOCKED tickers removed from candidates
B1 FIX: Joined N contract Greek fields into morning manifest
B4 FIX: Including N l3_ GARCH fields in morning manifest
eil_eod_resolver — external resolver available
```

**10.6 Check morning_candidates CSV after the run:**
```powershell
python -c "
import pandas as pd, glob, os
runs = sorted(glob.glob('data/output/runs/*/morning_validation/morning_candidates_*.csv'))
if not runs:
    print('No morning candidates found')
else:
    df = pd.read_csv(runs[-1])
    print(f'Rows: {len(df)}')
    print(f'Columns: {len(df.columns)}')
    blocked = (df.get('eil_v3_verdict','') == 'BLOCKED').sum() if 'eil_v3_verdict' in df.columns else 'col absent'
    jump    = df['l3_jump_risk_flag'].sum() if 'l3_jump_risk_flag' in df.columns else 'col absent'
    gamma   = df['contract_gamma'].notna().sum() if 'contract_gamma' in df.columns else 'col absent'
    print(f'BLOCKED in candidates:   {blocked}  (target: 0)')
    print(f'Jump risk visible:       {jump}    (target: >0 if any flagged)')
    print(f'contract_gamma present:  {gamma}  (target: >0)')
"
```
Expected:
- BLOCKED in candidates: 0
- Jump risk visible: non-zero if any tickers carry l3_jump_risk_flag=True
- contract_gamma present: non-zero

**10.7 Check fd_verdict distribution:**
```powershell
python -c "
import pandas as pd, glob
runs = sorted(glob.glob('data/output/runs/*/execution/execution_v3_5_*.csv'))
if runs:
    df = pd.read_csv(runs[-1], low_memory=False)
    if 'fd_verdict' in df.columns:
        print('fd_verdict distribution:')
        print(df['fd_verdict'].value_counts().to_string())
    else:
        print('fd_verdict column not found')
"
```
Expected: fd_verdict shows distribution of EXECUTE / EXECUTE_WITH_CAUTION /
          BLOCKED / WATCHLIST — NOT all WATCHLIST.

---

## COMPLETION REPORT

```
PIPELINE FIX SPRINT COMPLETION
================================
Step 0  — AUDIT:                                     [COMPLETE]
Step 1  — B2 BLOCKED filter in manifest builder:     [COMPLETE / FAILED]
Step 2  — B2 BLOCKED filter in /triage command:      [COMPLETE / FAILED]
Step 3  — B3 FinalDecision re-wired to eil_v3:       [COMPLETE / FAILED]
Step 4  — B1 Contract Greeks in morning manifest:    [COMPLETE / FAILED]
Step 5  — B4 l3_ jump risk in morning manifest:      [COMPLETE / FAILED]
Step 6  — RUN3 dtype FutureWarning fix:              [COMPLETE / FAILED]
Step 7  — RUN4 eil_eod_resolver.py stub deployed:    [COMPLETE / FAILED]
Step 8  — RUN1 Handoff contract failures fixed:      [COMPLETE / PARTIAL / FAILED]
Step 9  — UX1 Capital-lock display relabelled:       [COMPLETE / FAILED]
Step 10 — Standalone validation:                     [COMPLETE / FAILED]

Files modified:
  intelligent_orchestrator.py      (B2 filter, B1 Greeks, B4 l3_ fields)
  final_decision_engine.py         (B3 eil_v3_verdict pass-through)
  pipeline_interpreter/pipeline_interpreter_commands.py  (B2 /triage filter)
  scripts/macro_quant_packet.py    (RUN3 dtype cast)
  eil_eod_resolver.py              (RUN4 new stub file)
  [handoff contract files TBD]     (RUN1 — depends on Step 0.8 findings)
  [intelligence lab frontend TBD]  (UX1 — depends on Step 0.9 findings)

Files NOT modified (confirm unchanged):
  garch_runner.py
  avshunter_discovery_ULTIMATE.py
  avshunter_options_intelligence.py
  macro_horizon_router.py
  actuarial_cache_builder.py
  execution_intelligence_runner.py (unless Step 0.4 found fd_verdict written here)

Expected pipeline behaviour on next evening run:
  morning_candidates: 0 BLOCKED rows (B2 resolved)
  morning_candidates: contract_gamma/theta/iv/bid/ask/mid/spread_pct present (B1 resolved)
  morning_candidates: l3_jump_risk_flag visible for all flagged tickers (B4 resolved)
  fd_verdict distribution: EXECUTE / EXECUTE_WITH_CAUTION / BLOCKED / WATCHLIST (B3 resolved)
  eil_eod_resolver: external resolver available — no fallback warning (RUN4 resolved)
  macro_quant_packet: no FutureWarning on dtype assignment (RUN3 resolved)
  Handoff audit: PASS or reduced FAIL count (RUN1 partially resolved)
  Display labels: PENDING HUMAN REVIEW instead of NO_LIVE_CAPITAL_EOD (UX1 resolved)

Next action after this sprint:
  Run: python intelligent_orchestrator.py --evening
  Check log for:
    "B2 FILTER: N BLOCKED tickers removed from candidates"
    "B1 FIX: Joined N contract Greek fields into morning manifest"
    "B4 FIX: Including N l3_ GARCH fields in morning manifest"
    "eil_eod_resolver — external resolver available"
  Check morning_candidates CSV:
    BLOCKED in candidates = 0
    contract_gamma present
    l3_jump_risk_flag visible
  Check execution CSV:
    fd_verdict distribution not all WATCHLIST
  Check handoff_contract_audit CSV:
    status = PASS (or fewer failures than prior run)
```
