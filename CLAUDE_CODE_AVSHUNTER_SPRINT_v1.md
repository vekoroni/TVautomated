# CLAUDE_CODE_AVSHUNTER_SPRINT_v1.md
# AVSHUNTER Pipeline Sprint — All Fixes
# Makeo Consulting Limited · ACK Verissimo · May 2026
# ─────────────────────────────────────────────────────────────────────────────
# TRIGGER: Read this file and execute all steps in order.
#          Begin with Step 0 audit and report findings before making any changes.
# ─────────────────────────────────────────────────────────────────────────────

## GOVERNING RULES — READ BEFORE ANY CHANGE

1. Show the exact lines you plan to change BEFORE saving any file.
2. After each fix confirm: which file changed, which lines changed, all other files unchanged.
3. Never modify these files unless explicitly instructed in a step below:
   - macro_horizon_router.py
   - final_decision_engine.py
   - Any schema definition file not named in a step
4. If a step says DO NOT IMPLEMENT — skip it entirely and log that it was skipped.
5. If a file referenced in a step does not exist — log it, skip the step, continue.
6. Run one fix at a time. Confirm each before proceeding to the next.

---

## STEP 0 — AUDIT (NO CHANGES)

Before making any change, audit the following and report findings:

**0.1 Confirm these files exist:**
- `run_vanguard_from_packages.py`
- `execution_intelligence_runner.py`
- `execution_intelligence.py`
- `intelligent_orchestrator.py`
- `master_ticker_list2026_WITH_SECTORS.csv` or any CSV containing sector mappings
- `news_terminal/news_terminal_scheduler.py`
- `scripts/apply_macro_enrichment_to_discovery.py` (expect: MISSING)
- `eil_eod_resolver.py` (check root and archive folders)

**0.2 Confirm these audit files exist from run 20260515_235947:**
- `data/output/runs/20260515_235947/diagnostics/handoff_contract_audit_20260515_235947.csv`
- `data/output/runs/20260515_235947/morning_validation/eod_dropoff_audit_20260515_235947.csv`

**0.3 In run_vanguard_from_packages.py:**
- Find the `signal_to_row()` function
- Report whether `win_rate_5d`, `win_rate_10d`, `win_rate_20d` fields exist in the output dict
- Report the exact line numbers where layer2__ fields are written

**0.4 In execution_intelligence_runner.py:**
- Find where the final DECISION DISTRIBUTION log block is written
- Report whether the block hardcodes WATCHLIST for all rows when PSE is retired
- Report the exact line numbers

**0.5 In execution_intelligence.py:**
- Find the per-ticker scoring function (_process_row or equivalent)
- Report whether `macro_bias` or `macro_abstain` fields are read anywhere
- Report the exact line numbers where sector headwind penalty is applied

**0.6 In intelligent_orchestrator.py:**
- Report lines 3734 and 4684 — confirm the DtypeWarning source code
- Confirm line 3374 calls `apply_macro_enrichment_to_discovery()`
- Confirm `scripts/apply_macro_enrichment_to_discovery.py` path in cfg

**0.7 In news_terminal/news_terminal_scheduler.py:**
- Report the first 20 lines
- Confirm whether `import sys; sys.exit(0)` is already present

**Report all findings. Do not change any file. Proceed to Step 1 only after audit is complete.**

---

## STEP 1 — FIX G7: Bridge Vanguard win rates to signal CSV

**File:** `run_vanguard_from_packages.py`
**Risk:** SAFE — data bridge only, no scoring logic changed
**Do not touch any other file**

**What is broken:**
`win_rate_5d`, `win_rate_10d`, `win_rate_20d` arrive as 0.0 in every signal row.
EVEngineV2 falls back to `a=0.40` for every ticker.
EV clusters at three discrete bands with no signal differentiation.

**Instructions:**
1. Open `run_vanguard_from_packages.py`
2. Find the `signal_to_row()` function
3. Find where `layer2__` actuarial fields are written into the row dict
4. After those existing `layer2__` field writes, add exactly these three lines:

```python
row["win_rate_5d"]  = safe_get(l2, "win_rate_5d")  or safe_get(l2, "win_rate") or 0.0
row["win_rate_10d"] = safe_get(l2, "win_rate_10d") or safe_get(l2, "win_rate") or 0.0
row["win_rate_20d"] = safe_get(l2, "win_rate_20d") or safe_get(l2, "win_rate") or 0.0
```

5. If `safe_get` is not the correct helper function name in this file, use whatever
   field accessor pattern is already used for other `l2` field reads.
6. Validate syntax. Do not change any other logic.

**Show diff before saving. After saving confirm:**
- Only `run_vanguard_from_packages.py` was modified
- Syntax is valid (run `python -m py_compile run_vanguard_from_packages.py`)

**Validation on next run:**
EV distribution mean spreads from +0.0032 to +0.008–0.015 range.
No EV clustering at 0.0105/0.0202/0.0227 bands.

---

## STEP 2 — FIX EIL-PSE: Fix EIL distribution summary when PSE is retired

**File:** `execution_intelligence_runner.py`
**Risk:** SAFE — logging change only, no verdict or sizing logic changed
**Do not touch any other file**

**What is broken:**
Per-ticker rows show genuine EXECUTE verdicts (~30 tickers).
Final distribution summary overrides all to WATCHLIST: 1279 (100%), Execute rate: 0.0%.
This contradicts the per-ticker data and causes valid signals to be missed in downstream reads.

**Instructions:**
1. Open `execution_intelligence_runner.py`
2. Find the section that writes the final DECISION DISTRIBUTION log block
   (look for log lines containing: WATCHLIST, Block rate, Execute rate)
3. Find where PSE retired status is determined
   (look for: `pse_retired`, `advisory_mode`, `PSE status: RETIRED`, or similar)
4. Add a check: if PSE is retired, count actual EIL verdicts from per-ticker results
   instead of using the hardcoded WATCHLIST aggregation:

```python
if pse_retired:
    execute_count   = sum(1 for r in results if r.get("eil_verdict") == "EXECUTE")
    ewc_count       = sum(1 for r in results if r.get("eil_verdict") == "EXECUTE_WITH_CAUTION")
    watchlist_count = sum(1 for r in results if r.get("eil_verdict") == "WATCHLIST")
    blocked_count   = sum(1 for r in results if r.get("eil_verdict") == "BLOCKED")
    logger.info("PSE RETIRED — distribution reflects EIL advisory verdicts (not PSE sizing)")
    logger.info(f"  EXECUTE:              {execute_count}")
    logger.info(f"  EXECUTE_WITH_CAUTION: {ewc_count}")
    logger.info(f"  WATCHLIST:            {watchlist_count}")
    logger.info(f"  BLOCKED:              {blocked_count}")
    logger.info(f"  Size: MANUAL — no PSE authority")
```

5. Adapt field names to match what is actually used in the file.
   The key: per-ticker EIL verdicts must appear in the summary, not 100% WATCHLIST.
6. Size column remains 0.00000 — do not change sizing logic anywhere.

**Show diff before saving. After saving confirm:**
- Only `execution_intelligence_runner.py` was modified
- Syntax is valid

**Validation on next run:**
Distribution shows ~30 EXECUTE, ~65 EXECUTE_WITH_CAUTION — not 1279 WATCHLIST.
Size column remains 0.00000 throughout.

---

## STEP 3 — FIX VST-SECTOR: Reclassify VST, NEE, CEG from XLU

**File:** `master_ticker_list2026_WITH_SECTORS.csv` (or equivalent sector mapping file found in Step 0)
**Risk:** SAFE — CSV edit only, no code changes
**Do not touch any other file**

**What is broken:**
VST, NEE and CEG are nuclear/renewable power generation companies classified under XLU (Utilities).
XLU carries HEADWIND macro bias from 10Y yield pressure.
These three have no rate-sensitive dividend exposure and have AI data centre demand.
The macro headwind does not apply to them.
Last run: VST had EV=+0.0037, STRUCTURAL_MATCH, EIL=EXECUTE but was suppressed by XLU HEADWIND tag.

**Instructions:**
1. Open the sector mapping CSV found in Step 0
2. Find rows for tickers: VST, NEE, CEG
3. Change their Sector field from `Utilities` to `Power Generation`
4. If a `sector_etf_override` column exists: set it to `XLE` for these three tickers
   If the column does not exist: add it with value `XLE` for VST, NEE, CEG and empty for all others
5. Save the file

**Show the three changed rows before saving. After saving confirm:**
- The sector mapping file was modified
- VST, NEE, CEG now show `Power Generation` in Sector column
- No other rows were changed

**Validation on next run:**
VST, NEE, CEG show `macro_sector_bias=TAILWIND` or `NEUTRAL` (not HEADWIND).
They appear in candidate pool without suppression.

---

## STEP 4 — FIX DTYPE: Fix pandas DtypeWarning mixed-type columns

**File:** `intelligent_orchestrator.py`
**Risk:** SAFE — dtype declarations only, no logic changes
**Do not touch any other file**

**What is broken:**
Multiple `FutureWarning: Setting an item of incompatible dtype` at lines 3734 and 4684.
Currently warnings — will become hard errors in a future pandas version.
Risk of silent numeric field coercion to string causing NaN in a future run.

**Instructions:**
1. Open `intelligent_orchestrator.py`
2. Go to line 3734: `_sb_df_seq.at[_idx_seq, _col] = _v`
   Wrap the assignment with explicit type handling:

```python
try:
    _expected_dtype = _sb_df_seq[_col].dtype
    if _expected_dtype == "float64":
        _sb_df_seq.at[_idx_seq, _col] = float(_v)
    elif _expected_dtype == "int64":
        _sb_df_seq.at[_idx_seq, _col] = int(_v)
    elif _expected_dtype == "bool":
        _sb_df_seq.at[_idx_seq, _col] = bool(_v)
    else:
        _sb_df_seq.at[_idx_seq, _col] = str(_v)
except (ValueError, TypeError):
    _sb_df_seq.at[_idx_seq, _col] = str(_v)
```

3. Go to line 4684: `_eil_df = _pd_act.read_csv(_eil_path)`
   Add `low_memory=False` parameter:

```python
_eil_df = _pd_act.read_csv(_eil_path, low_memory=False)
```

4. Search for any other `read_csv` calls in the file that have DtypeWarning
   in the last run log (columns 38, 65, 103, 110, 130, 131, 627) and add
   `low_memory=False` to those calls only.
5. Do not change any surrounding logic.

**Show diff before saving. After saving confirm:**
- Only `intelligent_orchestrator.py` was modified
- Syntax is valid (run `python -m py_compile intelligent_orchestrator.py`)

**Validation on next run:**
Zero `FutureWarning: Setting an item of incompatible dtype` lines in the log.

---

## STEP 5 — NEW-1: CREATE scripts/apply_macro_enrichment_to_discovery.py

**File:** NEW FILE — `scripts/apply_macro_enrichment_to_discovery.py`
**Risk:** LOW — additive only. Orchestrator already calls this path at line 3374.
          If the script fails, orchestrator logs a warning and continues.
**Do not touch any other file**

**What is missing:**
The orchestrator calls `scripts/apply_macro_enrichment_to_discovery.py` at line 3374
with these arguments:
  `--discovery-csv`   path to discovery_candidates_ultimate_{run_id}.csv
  `--macro-path`      path to macro_intelligence_latest.json (already merged with enrichment)
  `--report-path`     path to write QA report JSON

The script does not exist. All enrichment intelligence in `avshunter_macro_enrichment.json`
(CALL_CONTEXT_OR_TAILWIND, PUT_CONTEXT_OR_HEADWIND, sector_rotation_map, macro_alignment_states)
is currently merged into the macro JSON at Phase 4.6 but never stamped onto discovery candidates.

**Create the file with this logic:**

```python
"""
apply_macro_enrichment_to_discovery.py
Stamps macro enrichment intelligence onto discovery candidates CSV.
Called by intelligent_orchestrator.py Phase post-discovery at line 3374.
Reads merged macro_intelligence_latest.json and adds macro_bias,
macro_abstain, macro_bias_source columns to the discovery CSV.
AUGMENT ONLY — never overwrites existing columns or protected macro fields.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


# Tickers that abstain from sector headwind — power generation exception list
MACRO_ABSTAIN_TICKERS = {"VST", "NEE", "CEG"}


def load_macro_json(macro_path: Path) -> dict:
    with open(macro_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def extract_bias_maps(macro: dict) -> tuple:
    """
    Navigate extras > macro_enrichment_delta > binary_options_analysis_policy
    > current_macro_bias_map to get call/put/context ticker lists.
    Returns (call_tickers, put_tickers, context_tickers) as sets.
    """
    try:
        extras = macro.get("extras") or {}
        delta  = extras.get("macro_enrichment_delta") or {}
        policy = delta.get("binary_options_analysis_policy") or {}
        bias_map = policy.get("current_macro_bias_map") or {}

        call_tickers    = set(t.upper() for t in (bias_map.get("CALL_CONTEXT_OR_TAILWIND") or []))
        put_tickers     = set(t.upper() for t in (bias_map.get("PUT_CONTEXT_OR_HEADWIND") or []))
        context_tickers = set(t.upper() for t in (bias_map.get("CONTEXT_ONLY_OR_REASSESSMENT") or []))

        print(f"  [ENRICHMENT] call_tickers={len(call_tickers)} put_tickers={len(put_tickers)} context_tickers={len(context_tickers)}")
        return call_tickers, put_tickers, context_tickers

    except Exception as e:
        print(f"  [WARN] Could not extract bias map from macro JSON: {e}")
        return set(), set(), set()


def resolve_macro_bias(ticker: str, call_tickers: set, put_tickers: set, context_tickers: set) -> tuple:
    """
    Returns (macro_bias, macro_abstain, macro_bias_source) for a ticker.
    """
    t = str(ticker).strip().upper()

    if t in MACRO_ABSTAIN_TICKERS:
        return "NEUTRAL", True, "POWER_GEN_EXCEPTION"

    if t in call_tickers:
        return "CALL_TAILWIND", False, "ENRICHMENT_DELTA"

    if t in put_tickers:
        return "PUT_HEADWIND", False, "ENRICHMENT_DELTA"

    if t in context_tickers:
        return "CONTEXT_ONLY", False, "ENRICHMENT_DELTA"

    return "NEUTRAL", False, "NO_ENRICHMENT_MATCH"


def stamp_discovery_csv(discovery_csv: Path, macro_path: Path, report_path: Path) -> bool:
    print(f"\n[MACRO_ENRICHMENT_STAMP] {discovery_csv.name}")

    if not discovery_csv.exists():
        print(f"  [ERROR] Discovery CSV not found: {discovery_csv}")
        return False

    # Load macro JSON
    try:
        macro = load_macro_json(macro_path)
    except Exception as e:
        print(f"  [ERROR] Cannot load macro JSON: {e}")
        return False

    # Extract bias maps
    call_tickers, put_tickers, context_tickers = extract_bias_maps(macro)

    # Load discovery CSV
    try:
        df = pd.read_csv(discovery_csv, low_memory=False)
        print(f"  [LOAD] {len(df)} rows")
    except Exception as e:
        print(f"  [ERROR] Cannot load discovery CSV: {e}")
        return False

    # Stamp columns — additive only
    macro_bias_list    = []
    macro_abstain_list = []
    macro_source_list  = []
    counts = {"CALL_TAILWIND": 0, "PUT_HEADWIND": 0, "CONTEXT_ONLY": 0, "NEUTRAL": 0, "ABSTAIN": 0}

    for _, row in df.iterrows():
        ticker = str(row.get("ticker", "")).strip().upper()
        bias, abstain, source = resolve_macro_bias(ticker, call_tickers, put_tickers, context_tickers)
        macro_bias_list.append(bias)
        macro_abstain_list.append(abstain)
        macro_source_list.append(source)
        counts[bias] = counts.get(bias, 0) + 1
        if abstain:
            counts["ABSTAIN"] += 1

    # Only add columns if they do not already exist (augment only)
    if "macro_bias" not in df.columns:
        df["macro_bias"] = macro_bias_list
    if "macro_abstain" not in df.columns:
        df["macro_abstain"] = macro_abstain_list
    if "macro_bias_source" not in df.columns:
        df["macro_bias_source"] = macro_source_list

    # Save back to same path
    df.to_csv(discovery_csv, index=False)
    print(f"  [STAMP] CALL_TAILWIND={counts['CALL_TAILWIND']} PUT_HEADWIND={counts['PUT_HEADWIND']} "
          f"CONTEXT_ONLY={counts['CONTEXT_ONLY']} NEUTRAL={counts['NEUTRAL']} ABSTAIN={counts['ABSTAIN']}")

    # Write QA report
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "discovery_csv":       str(discovery_csv),
            "macro_path":          str(macro_path),
            "rows_stamped":        len(df),
            "call_tailwind_count": counts["CALL_TAILWIND"],
            "put_headwind_count":  counts["PUT_HEADWIND"],
            "context_only_count":  counts["CONTEXT_ONLY"],
            "neutral_count":       counts["NEUTRAL"],
            "abstain_count":       counts["ABSTAIN"],
            "status":              "OK",
        }
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"  [QA] Report written: {report_path.name}")
    except Exception as e:
        print(f"  [WARN] QA report write failed: {e}")

    print(f"[MACRO_ENRICHMENT_STAMP] Complete\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Stamp macro enrichment onto discovery CSV")
    parser.add_argument("--discovery-csv", required=True)
    parser.add_argument("--macro-path",    required=True)
    parser.add_argument("--report-path",   required=True)
    args = parser.parse_args()

    ok = stamp_discovery_csv(
        discovery_csv=Path(args.discovery_csv),
        macro_path=Path(args.macro_path),
        report_path=Path(args.report_path),
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

**After creating the file confirm:**
- `scripts/apply_macro_enrichment_to_discovery.py` exists
- Syntax is valid: `python -m py_compile scripts/apply_macro_enrichment_to_discovery.py`
- No other files were modified

**Validation on next run:**
Log shows: `Macro enrichment discovery stamp complete -> macro_enrichment_discovery_{run_id}.json`
Discovery CSV has `macro_bias`, `macro_abstain`, `macro_bias_source` columns.

---

## STEP 6 — NEW-2: MODIFY execution_intelligence.py — read macro_bias and macro_abstain

**File:** `execution_intelligence.py`
**Risk:** LOW — additive modifier only. Never overrides BLOCKED verdicts.
          Never changes size_multiplier. Falls back to neutral if field missing.
**Dependency:** STEP 5 (NEW-1) must be complete and validated first.
**Do not touch any other file**

**What is missing:**
EIL does not read `macro_bias` or `macro_abstain` from the discovery row.
Sector headwind is applied uniformly including to VST (nuclear/power) which has no rate sensitivity.
The enrichment file's MACRO_NOT_APPLICABLE abstain logic is never executed.

**Instructions:**
1. Open `execution_intelligence.py`
2. Find the per-ticker scoring function — likely `_process_row()` or the main
   function that processes each ticker through EIL scoring
3. Find where each ticker row is loaded/read at the start of processing
4. Add this block AFTER the row is loaded but BEFORE sector headwind is applied:

```python
# ── Macro enrichment modifier (from apply_macro_enrichment_to_discovery.py) ──
_macro_bias    = str(row.get("macro_bias", "NEUTRAL")).upper().strip()
_macro_abstain = str(row.get("macro_abstain", "False")).upper().strip() == "TRUE"

_enrichment_score_modifier = 0.0
if _macro_bias == "CALL_TAILWIND":
    _enrichment_score_modifier = +0.10
elif _macro_bias == "PUT_HEADWIND":
    _enrichment_score_modifier = -0.15
# CONTEXT_ONLY and NEUTRAL: no modifier

if _macro_abstain:
    # Power generation exception — bypass sector headwind for VST, NEE, CEG etc
    _sector_headwind_applies = False
    logger.info(f"MACRO_ABSTAIN: {ticker} — sector headwind bypassed, scoring on structure only")
else:
    _sector_headwind_applies = True  # existing behaviour unchanged
# ── End macro enrichment modifier ────────────────────────────────────────────
```

5. Find where sector headwind penalty is applied in the scoring logic.
   Add a guard so it only fires when `_sector_headwind_applies` is True:

```python
if _sector_headwind_applies:
    # existing sector headwind penalty code here — unchanged
    pass
```

6. Find where composite_score is calculated or assembled.
   Apply the enrichment modifier only if non-zero:

```python
if _enrichment_score_modifier != 0.0:
    composite_score = composite_score + _enrichment_score_modifier
    logger.info(f"ENRICHMENT_MOD: {ticker} bias={_macro_bias} modifier={_enrichment_score_modifier:+.2f}")
```

7. Adapt variable names to match what is actually used in the file.
   The key behaviour:
   - `macro_abstain=True` → sector headwind does not apply to this ticker
   - `CALL_TAILWIND`      → +0.10 to composite score
   - `PUT_HEADWIND`       → -0.15 to composite score
   - Missing fields       → treat as NEUTRAL, no change

**HARD RULES — these must not be violated:**
- Never override EIL=BLOCKED verdicts from liquidity or spread gates
- Never change `size_multiplier` — that is horizon router authority only
- If `macro_bias` field is missing from the row: treat as NEUTRAL, continue normally
- If `macro_abstain` field is missing: treat as False, continue normally

**Show diff before saving. After saving confirm:**
- Only `execution_intelligence.py` was modified
- Syntax is valid: `python -m py_compile execution_intelligence.py`

**Validation on next run:**
VST, NEE, CEG log shows: `MACRO_ABSTAIN — sector headwind bypassed`
XOM, CVX, LMT etc show: `ENRICHMENT_MOD: CALL_TAILWIND modifier=+0.10`
QQQ, SMH etc show: `ENRICHMENT_MOD: PUT_HEADWIND modifier=-0.15`

---

## STEP 7 — SCHEDULER: Disable news terminal automatic runs

**File:** `news_terminal/news_terminal_scheduler.py`
**Risk:** ZERO — one line added. Pipeline Interpreter is NOT affected.
**Do not touch any other file**

**What to do:**
The news terminal is called automatically by Windows Task Scheduler.
Each run calls Claude API (claude-sonnet-4-6 with web search) consuming credits.
Pipeline is in manual operation mode. Disable automatic runs until monetisation begins.
The news terminal still works when run manually — only scheduled runs are paused.

**Instructions:**
1. Open `news_terminal/news_terminal_scheduler.py`
2. Find the closing triple-quote of the module docstring (the `"""` at the end)
3. Immediately after the docstring, before the first `import` statement, insert:

```python
# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER PAUSED — automatic runs disabled to preserve API credits.
# Pipeline is in manual operation mode.
# Reactivate when monetisation begins: remove or comment the two lines below.
# ─────────────────────────────────────────────────────────────────────────────
import sys as _sys
_sys.exit(0)
```

4. Save the file
5. Test: run `python news_terminal/news_terminal_scheduler.py morning`
   Expected result: exits immediately, no output, no API call, no log entry written
6. Print the first 30 lines of the modified file to confirm placement

**Also provide this PowerShell command for the user to run manually:**
```powershell
schtasks /query /fo LIST | findstr /i "avshunter news_terminal python scheduler"
# Then with the task name found above:
schtasks /change /tn "TASK_NAME_FROM_ABOVE" /disable
```

**Validation:**
`python news_terminal/news_terminal_scheduler.py morning` exits immediately.
No scheduler.log entry written. No API call made.

---

## STEP 8 — HOFF: Resolve handoff contract failures (CAUTION — READ FIRST)

**File:** Multiple — determined by reading audit CSV
**Risk:** LOW for field-level fixes. Do NOT touch schema definition files.

**Before any code change:**
1. Read: `data/output/runs/20260515_235947/diagnostics/handoff_contract_audit_20260515_235947.csv`
2. Report the 5 FAIL rows — what field, what stage, what ticker
3. Classify each failure:
   - TYPE A: missing field in output schema — fix the writer
   - TYPE B: field present but wrong type — fix type coercion
   - TYPE C: schema version mismatch — DO NOT fix this sprint
4. Fix only TYPE A and TYPE B failures
5. Do not fix TYPE C schema version mismatches
6. Do not change any schema definition files

**Validation on next run:**
`HANDOFF CONTRACT AUDIT: status=PASS | fail=0`

---

## STEP 9 — OI-DROP: Investigate 622 Options Intelligence drop-offs (CAUTION — READ FIRST)

**File:** `avshunter_options_intelligence.py` — after reading drop-off audit
**Risk:** MEDIUM if thresholds changed blindly. Read data first.

**Before any code change:**
1. Read: `data/output/runs/20260515_235947/morning_validation/eod_dropoff_audit_20260515_235947.csv`
2. Filter to rows where stage = `OPTIONS_INTELLIGENCE`
3. Count and group by `drop_reason`
4. Report the distribution

**Fix only these drop reason types:**
- `SPREAD_TOO_WIDE` where spread is 15–25%: raise hard block threshold from 15% to 25%
- `OI_BELOW_FLOOR` where OI is 50–100: lower hard block from 100 to 50
- `FETCH_TIMEOUT`: add retry with 2-second backoff, max 2 retries

**Do NOT fix:**
- `NO_OPTIONS_CHAIN`: ticker has no listed options — correct to drop
- `LIQUIDITY_FAIL` where OI < 50: correct to drop

**Validation on next run:**
OPTIONS_INTELLIGENCE drop count falls below 400 (from 622).

---

## STEP 10 — EIL-EOD: Deploy eil_eod_resolver.py (CAUTION — CHECK ARCHIVE FIRST)

**File:** `eil_eod_resolver.py` — deploy to AVSHUNTER-Intelligence root
**Risk:** LOW — EIL falls back gracefully if resolver errors

**Before any action:**
1. Search for `eil_eod_resolver.py` in:
   - AVSHUNTER-Intelligence root
   - `data/archive/` (all subdirectories)
   - Any backup or output folders
2. If found: copy to `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\eil_eod_resolver.py`
3. If NOT found: report `EIL-EOD: file not found in archive — skip this sprint`
   Do not build from scratch.

**Validation if deployed:**
Log no longer shows: `eil_eod_resolver.py not found in root`

---

## STEP 11 — MACRO-GATE: DO NOT IMPLEMENT

**This step is explicitly skipped this sprint.**

The macro scenario mapping has been superseded by:
- The existing `avshunter_macro_enrichment.json` (contains the scenario intelligence)
- STEP 5 NEW-1: `apply_macro_enrichment_to_discovery.py` (stamps enrichment onto discovery)
- STEP 6 NEW-2: `execution_intelligence.py` modifier (consumes macro_bias and macro_abstain)

Do not modify:
- `intelligent_orchestrator.py` macro routing logic
- `execution_intelligence.py` beyond the NEW-2 changes above
- `final_decision_engine.py`

Log: `MACRO-GATE: skipped — superseded by NEW-1 and NEW-2. Queue for Sprint 2 after 30+ closed trades.`

---

## COMPLETION REPORT

After all steps, produce a summary report:

```
AVSHUNTER SPRINT COMPLETION REPORT
====================================
Step 0  — AUDIT:         [COMPLETE]
Step 1  — G7:            [COMPLETE / SKIPPED / FAILED] — reason if not complete
Step 2  — EIL-PSE:       [COMPLETE / SKIPPED / FAILED]
Step 3  — VST-SECTOR:    [COMPLETE / SKIPPED / FAILED]
Step 4  — DTYPE:         [COMPLETE / SKIPPED / FAILED]
Step 5  — NEW-1:         [COMPLETE / SKIPPED / FAILED]
Step 6  — NEW-2:         [COMPLETE / SKIPPED / FAILED]
Step 7  — SCHEDULER:     [COMPLETE / SKIPPED / FAILED]
Step 8  — HOFF:          [COMPLETE / SKIPPED / FAILED]
Step 9  — OI-DROP:       [COMPLETE / SKIPPED / FAILED]
Step 10 — EIL-EOD:       [COMPLETE / SKIPPED / FAILED]
Step 11 — MACRO-GATE:    [SKIPPED — by design]

Files modified:
  [list every file that was changed]

Files created:
  [list every new file that was created]

Files NOT modified (confirm unchanged):
  - intelligent_orchestrator.py macro routing
  - macro_horizon_router.py
  - final_decision_engine.py
  - news_terminal_engine.py
  - news_terminal_commands.py
  - pipeline_interpreter.py

Next action:
  Run python intelligent_orchestrator.py --evening
  Validate each fix using the validation tests above.
```
