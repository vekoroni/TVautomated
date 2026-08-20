# CLAUDE_CODE_AVSHUNTER_UNIVERSE_ENRICHMENT_v1.md
# AVSHUNTER Universe Enrichment — Discovery Pipeline Integration
# Makeo Consulting Limited · ACK Verissimo · May 2026
# ─────────────────────────────────────────────────────────────────────────────
# TRIGGER: Read this file and execute all steps in order.
#          Begin with Step 0 audit and report findings before making any changes.
# ─────────────────────────────────────────────────────────────────────────────

## CONTEXT — WHAT THIS SPRINT DOES

The universe file is being replaced with an enriched version that carries
sector, sector_etf, industry and macro_abstain alongside the ticker.

This means:
- Discovery reads sector context from the universe file directly
- Sector data flows through the existing baton mechanism automatically
- No separate sector lookup needed at EIL or Options Intelligence
- New tickers from Routes 2/3 get resolved via Polygon API and written
  back to the universe file (self-healing — gets cheaper every run)

The enriched universe file has already been built:
  avshunter_sector_master_merged.csv
  3,649 tickers | 97.9% sector coverage
  Columns: ticker, sector, sector_etf, industry, macro_abstain

Target universe file location (pipeline canonical path):
  C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\universe\polygon_liquid_universe.csv

## GOVERNING RULES

1. Show exact diff before saving any file.
2. After each step confirm which files changed and which lines changed.
3. The universe file replacement is the foundation — do Steps 1-2 first.
4. Discovery changes must be backward compatible — if sector columns are
   missing from the universe file, discovery continues with empty sector
   fields rather than failing.
5. Never modify: macro_horizon_router.py, final_decision_engine.py,
   execution_intelligence_runner.py (beyond what is explicitly instructed).
6. Every change must be NON-CRITICAL — pipeline continues if it fails.

---

## STEP 0 — AUDIT (NO CHANGES)

Report findings before touching anything.

**0.1 Universe file current state:**
- Read: data/universe/polygon_liquid_universe.csv
- Report: row count, column names
- Confirm it is currently ticker-only (single column)

**0.2 Discovery script — find how it reads the universe file:**
- Search avshunter_discovery_ULTIMATE.py for:
  - Where it reads polygon_liquid_universe.csv or cfg.UNIVERSE_FILE
  - What columns it reads (just ticker, or more?)
  - Where it writes discovery_candidates_ultimate_{run_id}.csv
  - What columns are in the discovery output
- Report exact line numbers for each finding

**0.3 Discovery output columns:**
- Find the most recent discovery_candidates_ultimate_*.csv in
  data/output/runs/ (any recent run)
- Report its column names
- Confirm whether sector, sector_etf, industry, macro_abstain
  are currently present or absent

**0.4 Baton mechanism — how columns flow downstream:**
- Search intelligent_orchestrator.py for how discovery output
  columns are passed into Vanguard packages
- Confirm: do all columns in the discovery CSV automatically flow
  into the package JSON, or is there an explicit column whitelist?
- Report line numbers

**0.5 apply_macro_enrichment_to_discovery.py current state:**
- Confirm the file exists at scripts/apply_macro_enrichment_to_discovery.py
- Confirm it reads macro_bias from:
  (a) sector_master_latest.csv if available, OR
  (b) macro JSON bias map as fallback
- Report which path is currently active

**0.6 Check build_sector_master.py:**
- Confirm it exists at scripts/build_sector_master.py
- Confirm its --output-dir writes to data/ not data/universe/

**0.7 GARCH runner worker count:**
- Search garch_runner.py for: workers, n_jobs, processes, pool,
  ThreadPool, ProcessPool, multiprocessing
- Report current worker count and line number

Report all findings. Do not change any file.

---

## STEP 1 — DEPLOY ENRICHED UNIVERSE FILE

**Action:** Copy avshunter_sector_master_merged.csv to the canonical path.

**File to deploy:**
  Source: avshunter_sector_master_merged.csv
  (3,649 tickers | sector, sector_etf, industry, macro_abstain columns)

**Target path:**
  C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\universe\polygon_liquid_universe.csv

**Before copying:**
1. Read the current polygon_liquid_universe.csv and report its row count
2. Read avshunter_sector_master_merged.csv and confirm its structure:
   - ticker column exists
   - sector column exists and is populated
   - sector_etf column exists
   - industry column exists
   - macro_abstain column exists
   - VST shows: sector=Power Generation, sector_etf=XLE, macro_abstain=True
   - NEE shows: sector=Power Generation, sector_etf=XLE, macro_abstain=True
   - CEG shows: sector=Power Generation, sector_etf=XLE, macro_abstain=True

**After copying:**
3. Confirm the file is at the target path
4. Confirm row count matches source (3,649)
5. Run the universe gate check:
   python -c "
   import csv
   with open('data/universe/polygon_liquid_universe.csv') as f:
       n = sum(1 for _ in csv.DictReader(f))
   print(f'Universe gate: {n} tickers')
   "
6. Confirm the pipeline universe gate passes:
   (n > 1000 = min gate passes, n > 3000 = target gate passes)

---

## STEP 2 — UPDATE target_universe DEFAULT TO 6500

**Files:** intelligent_orchestrator.py (two locations)
**Risk:** SAFE — only changes the default threshold, not any logic

**Change 1 — function signature (line ~3036):**
Find:
```python
target_universe: int = 3000,
```
Change to:
```python
target_universe: int = 6500,
```

**Change 2 — argparse default (line ~4795):**
Find:
```python
parser.add_argument("--target_universe", type=int, default=3000,
```
Change to:
```python
parser.add_argument("--target_universe", type=int, default=6500,
```

**Why 6500:** Universe is currently 3,649. Target is 6,000. Setting to 6,500
gives headroom so the AUTO gate does not warn as the universe grows toward
the target. The quality ratio gates (15-25% candidates) are percentages —
they scale automatically and need no change.

Show diff before saving. Confirm syntax valid.

---

## STEP 3 — UPDATE DISCOVERY TO READ AND CARRY SECTOR COLUMNS

**File:** avshunter_discovery_ULTIMATE.py
**Risk:** LOW — additive. If sector columns missing from universe file,
          discovery continues normally with empty sector fields.
**Dependency:** Step 0 audit must confirm exactly where universe is read
               and how discovery output is built.

**Based on Step 0 findings, make these changes:**

**3A — Where discovery reads the universe file:**
Find the line(s) where polygon_liquid_universe.csv or cfg.UNIVERSE_FILE
is read into a DataFrame.

Currently it likely reads only the ticker column:
```python
df = pd.read_csv(universe_path)
tickers = df['ticker'].tolist()
```

Change to read all columns and store sector data:
```python
df_universe = pd.read_csv(universe_path, low_memory=False)
tickers = df_universe['ticker'].dropna().str.strip().str.upper().tolist()

# Build sector lookup from universe file
# Falls back gracefully if sector columns are absent
_SECTOR_COLS = ['sector', 'sector_etf', 'industry', 'macro_abstain']
_universe_sector_lookup = {}
if all(c in df_universe.columns for c in ['ticker', 'sector']):
    for _, row in df_universe.iterrows():
        t = str(row.get('ticker', '')).strip().upper()
        if t:
            _universe_sector_lookup[t] = {
                'sector':        str(row.get('sector',        '') or ''),
                'sector_etf':    str(row.get('sector_etf',    '') or ''),
                'industry':      str(row.get('industry',      '') or ''),
                'macro_abstain': str(row.get('macro_abstain', 'False')),
            }
```

**3B — Where discovery builds each candidate row:**
Find where each candidate dict/row is assembled before writing to CSV.

Add sector fields to each candidate row:
```python
# Sector context from universe file (augment only — never overwrite)
_ticker_upper = str(candidate.get('ticker', '')).strip().upper()
_sector_data  = _universe_sector_lookup.get(_ticker_upper, {})
if _sector_data:
    candidate.setdefault('sector',        _sector_data.get('sector',        ''))
    candidate.setdefault('sector_etf',    _sector_data.get('sector_etf',    ''))
    candidate.setdefault('industry',      _sector_data.get('industry',      ''))
    candidate.setdefault('macro_abstain', _sector_data.get('macro_abstain', 'False'))
```

Use `.setdefault()` — if the candidate already has a sector field
(e.g. from Route 3 catalyst data), it is not overwritten.

**3C — Where discovery writes the output CSV:**
Find where discovery_candidates_ultimate_{run_id}.csv is written.
Confirm the new columns (sector, sector_etf, industry, macro_abstain)
are included in the output fieldnames if not already present.

**RULES for Step 3:**
- Adapt the exact variable names and patterns to match what the file
  actually uses — do not force the code pattern above verbatim
- The key behaviour: sector data from universe file flows into
  every discovery candidate row
- If a ticker is not in the universe sector lookup (new Route 2/3 ticker):
  leave sector fields empty — the enrichment script handles these
- Do not change any scoring, filtering, or ranking logic
- Do not change how discovery reads or processes OHLCV or price data

Show diff before saving. Validate syntax.
Confirm: discovery output CSV now has sector, sector_etf, industry,
macro_abstain columns.

---

## STEP 4 — UPDATE apply_macro_enrichment_to_discovery.py

**File:** scripts/apply_macro_enrichment_to_discovery.py
**Risk:** SAFE — additive priority only

**What to change:**
The script currently resolves macro_bias by:
  Priority 1: sector_master_latest.csv (if exists)
  Priority 2: macro JSON bias map

Add a higher priority path — read sector from the discovery row itself,
since discovery now carries sector_etf directly from the enriched universe:

Find the Phase B bias stamping section.
Add Priority 0 before all existing logic:

```python
# ── Phase B0: Read sector_etf directly from discovery row ─────────────────
# Discovery now carries sector_etf from the enriched universe file.
# If present, use it to derive macro_bias directly.
# This is the highest priority — sector master and JSON are fallbacks.

def _bias_from_sector_etf(sector_etf: str, macro_bias_map: dict) -> str:
    """Map sector_etf directly to macro_bias using loaded macro bias map."""
    etf = str(sector_etf).strip().upper()
    if not etf or etf in ('', 'NAN', 'NONE', 'UNKNOWN'):
        return ''
    return macro_bias_map.get(etf, 'NEUTRAL')
```

Then in the per-row bias resolution loop, check discovery row first:
```python
for row in rows:
    ticker = str(row.get('ticker') or '').strip().upper()

    # Priority 0: sector_etf already in discovery row (from enriched universe)
    _disc_sector_etf = str(row.get('sector_etf', '') or '').strip().upper()
    _disc_abstain    = str(row.get('macro_abstain', 'False')).upper() == 'TRUE'

    if _disc_sector_etf and _disc_sector_etf not in ('', 'NAN', 'NONE', 'UNKNOWN'):
        _bias   = _bias_from_sector_etf(_disc_sector_etf, macro_bias_map)
        _source = 'UNIVERSE_SECTOR_ETF'
        _abstain_str = 'true' if _disc_abstain else 'false'
        # Set fields (augment only)
        if not row.get('macro_bias'):
            row['macro_bias']       = _bias
        if not row.get('macro_abstain'):
            row['macro_abstain']    = _abstain_str
        if not row.get('macro_bias_source'):
            row['macro_bias_source'] = _source
        continue  # skip lower-priority resolution

    # Priority 1+: existing sector master / JSON logic runs as fallback
    # [existing code unchanged below this point]
```

Also load the macro_bias_map at the start of enrich_discovery_csv():
```python
# Load macro bias from sector ETF map (for Phase B0)
macro_bias_map = _load_macro_bias_from_macro_json(macro)
# Where _load_macro_bias_from_macro_json reads sector_rotation block
# and returns dict of sector_etf -> macro_bias
# This function may already exist — check and reuse if so
```

Show diff before saving. Validate syntax.

---

## STEP 5 — UPDATE build_sector_master.py OUTPUT PATH

**File:** scripts/build_sector_master.py
**Risk:** SAFE — output path change only

**What to change:**
The script currently writes to data/sector_master_latest.csv.
Change the self-healing write-back to update the universe file directly:

Find where the script writes its output CSV.
Add a second write that updates the canonical universe file:

```python
# Write run-specific output (unchanged)
df_out.to_csv(run_path, index=False)

# Write to sector_master_latest (unchanged)  
df_out.to_csv(latest_path, index=False)

# Self-healing: update the canonical universe file with newly resolved tickers
# Only adds NEW tickers — never overwrites existing rows
_universe_path = REPO / "data" / "universe" / "polygon_liquid_universe.csv"
if _universe_path.exists():
    try:
        _existing = pd.read_csv(_universe_path, low_memory=False)
        _existing_tickers = set(_existing['ticker'].str.upper())
        _new_rows = df_out[~df_out['ticker'].isin(_existing_tickers)]
        if len(_new_rows) > 0:
            _updated = pd.concat([_existing, _new_rows], ignore_index=True)
            _updated.to_csv(_universe_path, index=False)
            print(f"  [SECTOR_MASTER] Self-heal: added {len(_new_rows)} new tickers to universe file")
        else:
            print(f"  [SECTOR_MASTER] Self-heal: no new tickers to add")
    except Exception as _sh_err:
        print(f"  [WARN] Self-heal write failed: {_sh_err} — universe file unchanged")
```

Show diff before saving. Validate syntax.

---

## STEP 6 — SET GARCH TO 2 WORKERS

**File:** garch_runner.py
**Risk:** SAFE — performance only, no logic change
**Dependency:** Step 0 must report current worker/loop structure first

**Why only GARCH:**
The pipeline runs all phases sequentially as subprocesses — there is no
orchestrator-level parallelism. Discovery, Vanguard, EIL and Options
Intelligence are I/O and DB bound — adding workers there adds overhead
without speed gain. GARCH is the only phase with an internal ticker
processing loop that is CPU bound and directly benefits from workers.

**At last run:** GARCH processed 1,279 tickers in ~29 minutes (sequential).
**At 3,649 tickers, 1 worker:** estimated ~82 minutes.
**At 3,649 tickers, 2 workers:** estimated ~41 minutes. Saves 40 minutes.
**Total evening run with this fix:** ~2 hours 5 minutes.

**Instructions based on Step 0 findings:**

If GARCH currently has a worker/n_jobs parameter:
  Set it to 2.

If GARCH processes tickers in a sequential for loop with no pool:
  Wrap the per-ticker processing function with:
```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=2) as executor:
    results = list(executor.map(_process_ticker, ticker_list))
```
  Where _process_ticker is the existing single-ticker function.
  Adapt to match the actual code structure — do not force this pattern
  if the existing structure does not fit cleanly.

If GARCH already uses 2+ workers: report and skip — no change needed.

**Do NOT add parallelism to:**
  Discovery, Vanguard, EIL, Options Intelligence, EIL runner.
  These are I/O and database bound — workers add overhead not speed.

Show diff before saving. Validate syntax after change.

---

## STEP 7 — STANDALONE TEST

**Test the full chain before running the evening pipeline:**

**7.1 Test universe file:**
```powershell
python -c "
import pandas as pd
df = pd.read_csv('data/universe/polygon_liquid_universe.csv')
print(f'Rows: {len(df)}')
print(f'Cols: {list(df.columns)}')
sector_filled = df['sector'].notna() & (df['sector'] != '')
print(f'Sector filled: {sector_filled.sum()} ({sector_filled.mean()*100:.1f}%)')
for t in ['VST','NEE','CEG','XOM','NVDA','JPM']:
    row = df[df.ticker==t]
    if not row.empty:
        print(f'{t}: {row.sector.values[0]} / {row.sector_etf.values[0]} / abstain={row.macro_abstain.values[0]}')
"
```
Expected: 3,649 rows, sector 97.9% filled, VST/NEE/CEG show Power Generation/XLE/True

**7.2 Test sector master script:**
```powershell
python scripts\build_sector_master.py `
  --macro-path dropbox\macro\macro_intelligence_latest.json `
  --run-id TEST_20260516 `
  --output-dir data
```
Expected: completes without error, reports UNKNOWN < 5%

**7.3 Test discovery reads sector (dry run on small sample):**
```powershell
python -c "
import pandas as pd
# Simulate what discovery will now carry
df = pd.read_csv('data/universe/polygon_liquid_universe.csv')
print('Columns discovery will carry:')
print([c for c in df.columns])
print(f'Sample:')
print(df[['ticker','sector','sector_etf','macro_abstain']].head(5))
"
```

**7.4 Confirm target_universe gate passes:**
```powershell
python -c "
import csv
with open('data/universe/polygon_liquid_universe.csv') as f:
    n = sum(1 for _ in csv.DictReader(f))
print(f'Universe gate check: {n} tickers')
print(f'Min gate (1000): PASS' if n >= 1000 else 'Min gate: FAIL')
print(f'Target gate (6500): PASS' if n >= 6500 else f'Target gate: WARN at {n} — AUTO mode proceeds')
"
```

**7.5 Timing benchmark — GARCH on a small sample:**
After GARCH workers are set, run a quick benchmark to confirm speed:
```powershell
python -c "
import time
# This just confirms the worker setting took effect — not a full run
import garch_runner
print('GARCH worker setting confirmed — run full pipeline to benchmark')
"
```
Expected total evening run with 2 GARCH workers at 3,649 tickers: ~2hr 5min.

---

## COMPLETION REPORT

```
UNIVERSE ENRICHMENT SPRINT COMPLETION
=======================================
Step 0  — AUDIT:                         [COMPLETE]
Step 1  — Deploy enriched universe file: [COMPLETE / FAILED]
Step 2  — Update target_universe=6500:   [COMPLETE / FAILED]
Step 3  — Discovery reads sector cols:   [COMPLETE / FAILED]
Step 4  — Enrichment script priority 0:  [COMPLETE / FAILED]
Step 5  — Sector master self-heal path:  [COMPLETE / FAILED]
Step 6  — GARCH worker count:            [COMPLETE / SKIPPED / FAILED]
Step 7  — Standalone tests:              [COMPLETE / FAILED]

Universe file: data/universe/polygon_liquid_universe.csv
  Tickers:       3,649
  Sector filled: ___% (target: >97%)
  VST/NEE/CEG:   Power Generation / XLE / macro_abstain=True ✅

Files modified:
  data/universe/polygon_liquid_universe.csv (replaced with enriched master)
  intelligent_orchestrator.py (target_universe=6500)
  avshunter_discovery_ULTIMATE.py (reads and carries sector columns)
  scripts/apply_macro_enrichment_to_discovery.py (priority 0 from discovery row)
  scripts/build_sector_master.py (self-heal write-back to universe file)
  garch_runner.py (worker count increase if applicable)

Files NOT modified (confirm unchanged):
  macro_horizon_router.py
  final_decision_engine.py
  execution_intelligence_runner.py
  execution_intelligence.py

Expected pipeline behaviour on next evening run:
  Phase 0:    Universe gate: 3,649 tickers — PASS
  Phase 1:    Discovery carries sector, sector_etf, industry, macro_abstain
              per ticker from row 1
  Phase post-disc: apply_macro_enrichment_to_discovery.py reads sector_etf
              directly from discovery rows — Priority 0 path active
              macro_bias resolved for ~97% of tickers (vs 5% before)
  Phase EIL:  macro_bias and macro_abstain fields populated for 97% of tickers
              CALL_TAILWIND modifiers fire for XLE/energy tickers
              PUT_HEADWIND modifiers fire for XLU/rate-sensitive tickers
              VST/NEE/CEG sector headwind bypassed via macro_abstain=True
  Morning:    Tier A candidates increase from 14 to estimated 18-24
              GO candidates increase from 2 to estimated 4-6

Next action after this sprint:
  Run: python intelligent_orchestrator.py --evening
  Check log for:
    "Universe OK: 3649 tickers"
    "Macro enrichment discovery stamp complete"
    "ENRICHMENT_MOD: bias=CALL_TAILWIND"
    "MACRO_ABSTAIN: sector headwind bypassed" (for VST/NEE/CEG)
  Check discovery CSV has sector, sector_etf, macro_bias, macro_abstain columns
```
