# CLAUDE CODE — AVSHUNTER Full Integration Sprint v3
# Run from: C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\
# Read this file completely. Audit first. Build second. Verify last.

---

## WHAT WE ARE BUILDING — END TO END

```
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│  NEWS TERMINAL (Sonnet)          │  │  MA COCKPIT (Sonnet)             │
│  Runs independently              │  │  Runs independently              │
│                                  │  │                                  │
│  Produces:                       │  │  Produces:                       │
│  • Market Narrative Brief        │  │  • M&A Intelligence Report       │
│  • avshunter_catalyst_csv_       │  │  • ma_candidates_YYYYMMDD.csv    │
│    YYYYMMDD.csv                  │  │                                  │
│  • macro_intelligence_latest.json│  │  MA Cockpit role ends here.      │
│  • macro_enrichment_delta_.json  │  │  No direct link to interpreter.  │
└─────────────────┬────────────────┘  └─────────────────┬────────────────┘
                  │  CSVs only                           │
                  └────────────────┬─────────────────────┘
                                   ↓
                   COMBINER (build_premarket_candidates.py)
                   Merges: catalyst_csv + ma_candidates
                   Produces:
                   → premarket_candidates_YYYYMMDD.csv (downloadable)

                   DEPLOY (auto)
                   Copies macro JSON to:
                   → dropbox\macro\
                   → pipeline_interpreter\MA_Inputs\macro\

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ⚠  HUMAN REVIEW GATE
     ACK reviews premarket_candidates_YYYYMMDD.csv
     Approves tickers — uploads manually to pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                                   ↓
                   AVSHUNTER PIPELINE
                   Reads: scanner universe + manually approved tickers
                   Reads: macro_intelligence_latest.json
                   Processes: Discovery → Vanguard → OI → SuperBrain
                              → EIL → PSE → Morning Validation
                   Produces:
                   → morning_validated_trades_YYYYMMDD_HHMMSS.csv
                     → copied to pipeline_interpreter\MA_Inputs\pipeline_outputs\
                                   ↓
                   PIPELINE INTERPRETER (Opus)
                   Mode 1 /triage — reads THREE sources only:
                     • morning_validated_trades (pipeline)
                     • macro_intelligence_latest.json (newsroom)
                     • premarket_candidates (merged, if uploaded by ACK)
                   Produces: triage HTML — ranked ticker cards
                                   ↓
                   ACK selects shortlist for deep dive
                                   ↓
                   Mode 2 /ticker — full v11.1
                     • All three sources above
                     • Chart screenshot (dropped manually into MA_Inputs\charts\)
                   Produces: HTML brief + trade brief CSV per ticker
```

**MA Cockpit has no direct connection to the pipeline interpreter.
Its data reaches the interpreter only via the merged premarket_candidates CSV,
after ACK has reviewed and chosen to upload it.**

---

## STEP 0 — AUDIT BEFORE TOUCHING ANYTHING

Run and report full output:

```
dir C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\news_terminal /s /b
dir C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\ma_cockpit /s /b
dir C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\dropbox /s /b
dir C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter /s /b
```

Identify and report:
- Exact name and path of news terminal main runner script
- Exact name and path of MA cockpit main runner script
- Where news terminal currently writes output files
- Where MA cockpit currently writes output files
- Whether any deploy/copy scripts already exist
- Current state of `pipeline_interpreter\MA_Inputs\pipeline_outputs\` directory
- All existing model strings in all three systems (grep for "claude-")

Use real paths from audit throughout. Do not assume.

---

## STEP 1 — CREATE REQUIRED DIRECTORIES

```python
from pathlib import Path
dirs = [
    r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter\MA_Inputs\macro",
    r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter\MA_Inputs\pipeline_outputs",
    r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\dropbox\macro",
    r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\dropbox\inputs",
    r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\news_terminal\outputs",
    r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\ma_cockpit\outputs",
]
for d in dirs:
    Path(d).mkdir(parents=True, exist_ok=True)
    print(f"[DIR OK] {d}")
```

---

## STEP 2 — NEWS TERMINAL: WHAT IT MUST PRODUCE

The news terminal GPT session already produces a Market Narrative Intelligence Brief
(the human-readable report). It must now also produce two structured files automatically
from the same session data.

### 2a — Catalyst CSV

**Filename:** `avshunter_catalyst_csv_YYYYMMDD.csv`
**Written to:** `news_terminal\outputs\`

**Exact 32-column schema — column names and order are fixed:**

```
ticker
catalyst_type
catalyst_status
catalyst_date
event_window_start
event_window_end
catalyst_direction_bias
catalyst_source_confidence
catalyst_binary_score
source_tier
source_url
ticker_role
event_status
tradability_route
failure_risk
missing_data
execution_permission        ← ALWAYS "NONE_NEWS_TERMINAL_ONLY"
capital_grade               ← ALWAYS "NO"
date_quality
source_count
already_priced_risk
needs_manual_confirmation
company
sector
key_catalyst
transmission_channel
expected_impact
confirmation_signals
invalidation_signals
anis_score
fips_score
manual_validation_notes
```

**Allowed enum values:**

```python
CATALYST_TYPES = [
    "MERGER_ACQUISITION", "PRIVATE_EQUITY_INTEREST", "ACTIVIST_PRESSURE",
    "SPINOFF", "EARNINGS_CATALYST", "MACRO_SECTOR", "GEOPOLITICAL",
    "REGULATORY", "OTHER"
]

CATALYST_STATUS = ["CONFIRMED", "REPORTED", "RUMOURED", "WATCH"]

DIRECTION_BIAS = [
    "LONG_CALL_WATCH", "LONG_PUT_WATCH", "NEUTRAL_WATCH",
    "WATCH_ONLY", "DO_NOT_RUN"
]

SOURCE_CONFIDENCE = ["HIGH", "MEDIUM_HIGH", "MEDIUM", "LOW"]

SOURCE_TIER = ["TIER_1", "TIER_2", "TIER_3"]

TICKER_ROLE = ["TARGET", "ACQUIRER", "PEER", "SECTOR_ETF", "INDEX_ETF", "UNKNOWN"]

EVENT_STATUS = ["CONFIRMED", "REPORTED", "RUMOURED", "WATCH", "CLOSED", "DENIED"]

TRADABILITY_ROUTE = [
    "FULL_PIPELINE", "DISCOVERY_ONLY", "MANUAL_VALIDATE_THEN_PIPELINE",
    "WATCHLIST_ONLY", "NEWS_WATCH_ONLY", "DO_NOT_RUN"
]

CAPITAL_GRADE = ["NO"]   # always NO from news terminal

EXECUTION_PERMISSION = ["NONE_NEWS_TERMINAL_ONLY"]   # always locked

DATE_QUALITY = ["CONFIRMED_DATE", "ESTIMATED_DATE", "ROLLING_WINDOW"]

ALREADY_PRICED_RISK = ["HIGH", "MEDIUM", "LOW"]
```

**Example row (from actual output):**
```
CSCO,OTHER,CONFIRMED,2026-05-14,2026-05-14,2026-05-22,LONG_CALL_WATCH,HIGH,1,TIER_2,
https://www.reuters.com/...,UNKNOWN,CONFIRMED,FULL_PIPELINE,
"Already-priced gap risk; IV crush","Real-time options volume, IV change",
NONE_NEWS_TERMINAL_ONLY,NO,CONFIRMED_DATE,1,HIGH,TRUE,Cisco Systems,Technology,
"Cisco jumps after strong revenue forecast","Confirmed guidance raise; 1-20 day repricing",
"BULLISH; HIGH","Price confirmation score: 95; Options confirmation: MISSING",
"IV crush; failed gap-and-hold",85,88,"Corporate event; Original event_id: 2026-05-15-CSCO"
```

### 2b — Macro Enrichment Delta JSON

**Filename:** `avshunter_macro_enrichment_delta_YYYYMMDD.json`
Also copy to: `macro_intelligence_latest.json` (the pipeline's live read target)
**Written to:** `news_terminal\outputs\`

**Required top-level structure (must match exactly — pipeline will fail otherwise):**

```json
{
  "contract_version": "macro_enrichment_delta_v1_2",
  "target_macro_contract_version": "macro_contract_v1_0",
  "packet_type": "MACRO_ENRICHMENT_DELTA",
  "merge_mode": "AUGMENT_ONLY_DO_NOT_REPLACE",
  "batch_id": "YYYY-MM-DD-SESSION-DESCRIPTOR",
  "source": "AVSHUNTER_NEWS_TERMINAL_GPT",
  "as_of_utc": "YYYY-MM-DDT00:00:00Z",
  "report_date": "YYYY-MM-DD",
  "source_freshness": { ... },
  "ticker_handoff_policy": { ... },
  "protected_macro_fields_do_not_override": [ ... ],
  "merge_controls": { ... },
  "narrative_overlay": { ... },
  "macro_json_merge_block": { ... },
  "theme_deltas": [ ... ],
  "event_guards": [ ... ],
  "macro_exposure_index": { ... },
  "validation_rules": [ ... ],
  "audit": { ... },
  "binary_options_analysis_policy": { ... }
}
```

**Fields that MUST NOT be present or overridden in the delta (pipeline-protected):**
```
contract_version, regime_state, dir_bias, trend_energy, usd_state,
rates_impulse, liquidity_pulse, regime_drift_status, macro_conviction,
vol_mode, risk_on_off_switch, sector_tilt, net_liquidity_score,
vix_regime_score, gex_regime_score, macro_momentum_score, regime_label,
regime_probability, vix_spot, macro_filter, sector_lead, sector_avoid,
size_multiplier, trigger_required, horizon_routing, sector_rotation,
put_gate, macro_quant_packet
```

**merge_controls that must always be false:**
```json
"can_override_macro_filter": false,
"can_change_size_multiplier": false,
"can_change_trigger_required": false,
"can_change_horizon_routing": false,
"can_unblock_put_gate": false,
"can_override_sector_lead_or_sector_avoid": false
```

### 2c — Tickers-Only Handoff File

**Filename:** `news_terminal_tickers_YYYYMMDD.txt`
**Written to:** `news_terminal\outputs\`

Plain text, one ticker per line. Used as the supplementary universe input to the pipeline.
No metadata — tickers only. The pipeline looks up its own data for each ticker.

Example:
```
CSCO
DXCM
XOM
CVX
DAL
QQQ
IWM
```

### 2d — News Terminal GPT Prompt Template

Create or update the news terminal GPT prompt at:
`news_terminal\prompts\newsroom_session_prompt.txt`

The prompt must instruct the GPT to produce all three outputs in sequence
after reading the global session brief. Template:

```
You are the AVSHUNTER News Terminal. Your role is market narrative intelligence —
identify consequences, not headlines. Separate confirmed / assumption / missing.
Never grant execution permission.

After producing the Market Narrative Intelligence Brief, you must produce:

OUTPUT 1 — CATALYST CSV
Produce a CSV with this exact header (32 columns):
ticker,catalyst_type,catalyst_status,catalyst_date,event_window_start,event_window_end,
catalyst_direction_bias,catalyst_source_confidence,catalyst_binary_score,source_tier,
source_url,ticker_role,event_status,tradability_route,failure_risk,missing_data,
execution_permission,capital_grade,date_quality,source_count,already_priced_risk,
needs_manual_confirmation,company,sector,key_catalyst,transmission_channel,
expected_impact,confirmation_signals,invalidation_signals,anis_score,fips_score,
manual_validation_notes

Rules:
- execution_permission MUST be NONE_NEWS_TERMINAL_ONLY on every row
- capital_grade MUST be NO on every row
- Include every ticker mentioned in the brief as a candidate
- Score ANIS (current impact strength 0-100) and FIPS (forward clarity 0-100)
- Use only allowed enum values for catalyst_type, catalyst_status, direction_bias,
  source_tier, ticker_role, event_status, tradability_route

OUTPUT 2 — MACRO ENRICHMENT DELTA JSON
Produce a macro_enrichment_delta JSON matching contract_version macro_enrichment_delta_v1_2.
merge_mode must be AUGMENT_ONLY_DO_NOT_REPLACE.
Do not include or override any protected macro fields.
execution_permission must be NONE_NEWS_TERMINAL_ONLY.

OUTPUT 3 — TICKERS LIST
Produce a plain text list of all candidate tickers, one per line.
```

---

## STEP 3 — MA COCKPIT: WHAT IT MUST PRODUCE

MA Cockpit produces one file per session:

**Filename:** `ma_candidates_YYYYMMDD.csv`
**Written to:** `ma_cockpit\outputs\`

**Same 32-column schema as the catalyst CSV above.**

Allowed `catalyst_type` values for MA cockpit:
```
MERGER_ACQUISITION, PRIVATE_EQUITY_INTEREST, ACTIVIST_PRESSURE, SPINOFF
```

All rows must have:
```
execution_permission = NONE_NEWS_TERMINAL_ONLY
capital_grade = NO
```

### MA Cockpit GPT Prompt Template

Create or update at: `ma_cockpit\prompts\ma_session_prompt.txt`

```
You are the AVSHUNTER M&A Cockpit. Your role is to track confirmed and reported
corporate events: mergers, acquisitions, PE bids, activist campaigns, spin-offs.

Separate confirmed / reported / rumoured. Never invent deals. Never grant execution.

Produce a CSV with this exact header (32 columns):
[same 32-column header as above]

Rules:
- catalyst_type must be one of: MERGER_ACQUISITION, PRIVATE_EQUITY_INTEREST,
  ACTIVIST_PRESSURE, SPINOFF
- execution_permission MUST be NONE_NEWS_TERMINAL_ONLY on every row
- capital_grade MUST be NO on every row
- ticker_role must correctly reflect TARGET, ACQUIRER, or PEER
- tradability_route: use FULL_PIPELINE only for confirmed deals with options liquidity;
  use DISCOVERY_ONLY or WATCHLIST_ONLY for reported/rumoured
- Score ANIS and FIPS based on deal confirmation strength and timeline clarity
```

---

## STEP 4 — BUILD build_premarket_candidates.py

**Location:** `news_terminal\build_premarket_candidates.py`

This script merges news terminal + MA cockpit CSV outputs into a single daily file
that the pipeline reads as its supplementary universe.

```python
"""
build_premarket_candidates.py
Combines News Terminal catalyst CSV + MA Cockpit candidate CSV into a single
pre-market candidate file at dropbox\inputs\.

Called automatically at the end of the news terminal run.
Output feeds AVSHUNTER pipeline as supplementary universe input.
execution_permission and capital_grade are LOCKED — source values discarded.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import sys

BASE  = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
TODAY = datetime.now().strftime("%Y%m%d")

# ── Adjust these to real output dirs found in audit ───────────────────────
NEWS_TERMINAL_OUTPUT = BASE / "news_terminal" / "outputs"
MA_COCKPIT_OUTPUT    = BASE / "ma_cockpit" / "outputs"
# ─────────────────────────────────────────────────────────────────────────

DROPBOX_INPUTS = BASE / "dropbox" / "inputs"

# Exact 32-column output schema
OUTPUT_COLS = [
    "ticker", "catalyst_type", "catalyst_status", "catalyst_date",
    "event_window_start", "event_window_end", "catalyst_direction_bias",
    "catalyst_source_confidence", "catalyst_binary_score", "source_tier",
    "source_url", "ticker_role", "event_status", "tradability_route",
    "failure_risk", "missing_data", "execution_permission", "capital_grade",
    "date_quality", "source_count", "already_priced_risk",
    "needs_manual_confirmation", "company", "sector", "key_catalyst",
    "transmission_channel", "expected_impact", "confirmation_signals",
    "invalidation_signals", "anis_score", "fips_score", "manual_validation_notes"
]

# These are locked — source data values are always discarded and replaced
LOCKED_FIELDS = {
    "execution_permission": "NONE_NEWS_TERMINAL_ONLY",
    "capital_grade":        "NO",
}


def load_latest(directory: Path, pattern: str, label: str) -> pd.DataFrame:
    """Load most recently modified file matching pattern in directory."""
    files = sorted(
        directory.glob(pattern),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    if not files:
        print(f"  [WARN] {label}: no files matching '{pattern}' in {directory}")
        return pd.DataFrame()
    latest = files[0]
    print(f"  [LOAD] {label}: {latest.name} ({latest.stat().st_size:,} bytes)")
    try:
        df = pd.read_csv(latest, low_memory=False)
        print(f"         {len(df)} rows")
        return df
    except Exception as e:
        print(f"  [ERROR] {label}: {e}")
        return pd.DataFrame()


def build_tickers_file(combined: pd.DataFrame):
    """Write plain tickers list for pipeline universe injection."""
    tickers = combined["ticker"].dropna().unique().tolist()
    outfile = DROPBOX_INPUTS / f"news_terminal_tickers_{TODAY}.txt"
    with open(outfile, "w") as f:
        f.write("\n".join(sorted(tickers)))
    print(f"  [TICKERS] {len(tickers)} tickers → {outfile.name}")


def build_combined():
    DROPBOX_INPUTS.mkdir(parents=True, exist_ok=True)

    print(f"\n[BUILD] build_premarket_candidates.py — {TODAY}")

    # Load news terminal catalyst CSV
    nt_df = load_latest(
        NEWS_TERMINAL_OUTPUT,
        f"avshunter_catalyst_csv_{TODAY}.csv",
        "News Terminal"
    )
    # Fallback to latest if today's not found
    if nt_df.empty:
        nt_df = load_latest(
            NEWS_TERMINAL_OUTPUT,
            "avshunter_catalyst_csv_*.csv",
            "News Terminal (latest)"
        )

    # Load MA cockpit CSV
    ma_df = load_latest(
        MA_COCKPIT_OUTPUT,
        f"ma_candidates_{TODAY}.csv",
        "MA Cockpit"
    )
    if ma_df.empty:
        ma_df = load_latest(
            MA_COCKPIT_OUTPUT,
            "ma_candidates_*.csv",
            "MA Cockpit (latest)"
        )

    frames = [df for df in [nt_df, ma_df] if not df.empty]
    if not frames:
        print("[ERROR] No source data found. Aborting.")
        print("        Ensure news terminal and MA cockpit have run first.")
        sys.exit(1)

    combined = pd.concat(frames, ignore_index=True)
    print(f"\n[BUILD] Raw combined: {len(combined)} rows")

    # Lock protected fields — discard any source values
    for field, value in LOCKED_FIELDS.items():
        combined[field] = value

    # Add missing output columns as empty strings
    for col in OUTPUT_COLS:
        if col not in combined.columns:
            combined[col] = ""

    # Deduplicate on ticker + catalyst_date + catalyst_type
    before = len(combined)
    combined = combined.drop_duplicates(
        subset=["ticker", "catalyst_date", "catalyst_type"],
        keep="first"
    )
    if before > len(combined):
        print(f"  [DEDUP] {before - len(combined)} duplicate rows removed")

    # Sort: highest binary_score first, then anis_score
    combined["catalyst_binary_score"] = pd.to_numeric(
        combined["catalyst_binary_score"], errors="coerce"
    ).fillna(0)
    combined["anis_score"] = pd.to_numeric(
        combined["anis_score"], errors="coerce"
    ).fillna(0)
    combined = combined.sort_values(
        ["catalyst_binary_score", "anis_score"],
        ascending=[False, False]
    )

    # Write combined CSV
    outfile = DROPBOX_INPUTS / f"premarket_candidates_{TODAY}.csv"
    combined[OUTPUT_COLS].to_csv(outfile, index=False)
    print(f"\n[BUILD] ✓ premarket_candidates_{TODAY}.csv")
    print(f"         {len(combined)} rows | {len(OUTPUT_COLS)} cols")
    print(f"         execution_permission: NONE_NEWS_TERMINAL_ONLY (locked)")
    print(f"         capital_grade: NO (locked)")

    # Write tickers-only file for pipeline universe injection
    build_tickers_file(combined)

    return combined


if __name__ == "__main__":
    build_combined()
```

---

## STEP 5 — DEPLOY FUNCTION

Add to the news terminal main runner, called AFTER outputs are written:

```python
def deploy_news_terminal_outputs():
    """
    Copy news terminal macro outputs to all pipeline-readable locations.
    Called at the end of every news terminal run, after files are written.
    """
    import shutil
    from pathlib import Path
    from datetime import datetime

    BASE    = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
    TODAY   = datetime.now().strftime("%Y%m%d")
    src_dir = BASE / "news_terminal" / "outputs"  # adjust from audit

    targets = [
        BASE / "pipeline_interpreter" / "MA_Inputs" / "macro",
        BASE / "dropbox" / "macro",
    ]

    # Files to deploy to macro locations
    macro_files = [
        "macro_intelligence_latest.json",
        f"avshunter_macro_enrichment_delta_{TODAY}.json",
    ]
    # Also deploy premarket candidates to dropbox\inputs
    candidate_files = [
        f"premarket_candidates_{TODAY}.csv",
        f"news_terminal_tickers_{TODAY}.txt",
    ]

    # Deploy macro files
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
        for fname in macro_files:
            src = src_dir / fname
            if src.exists():
                shutil.copy2(src, target / fname)
                print(f"  [DEPLOY] {fname} → {target.name}")

    # Deploy candidate files to dropbox\inputs
    inputs_dir = BASE / "dropbox" / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    for fname in candidate_files:
        src = BASE / "news_terminal" / "outputs" / fname
        if src.exists():
            shutil.copy2(src, inputs_dir / fname)
            print(f"  [DEPLOY] {fname} → dropbox\\inputs")

    print(f"[DEPLOY] Complete")
```

Then call in sequence at end of news terminal run:

```python
# End of news terminal run
deploy_news_terminal_outputs()

# Build combined pre-market CSV
import subprocess, sys
subprocess.run([sys.executable,
    str(Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\news_terminal\build_premarket_candidates.py"))
])
```

---


## STEP 6 — PIPELINE WRITES TO INTERPRETER AUTO-LOAD LOCATION

The pipeline already writes `morning_validated_trades_YYYYMMDD_HHMMSS.csv`.
Ensure it also writes (or copies) to the interpreter's watched location:

```python
INTERPRETER_OUTPUT_DIR = Path(
    r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter\MA_Inputs\pipeline_outputs"
)
INTERPRETER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# After morning validation writes its CSV, copy to interpreter location
import shutil
shutil.copy2(morning_validated_path, INTERPRETER_OUTPUT_DIR / morning_validated_path.name)
print(f"[HANDOFF] Morning validated trades → interpreter pipeline_outputs")
```

---

## STEP 7 — PIPELINE INTERPRETER: TWO-MODE ARCHITECTURE

The interpreter operates in two distinct modes. Both are triggered differently
and produce different outputs. Build both into the interpreter.

---

### THE THREE-ENGINE FILE CONTRACT

The interpreter is the convergence point for all three engines.
Communication between engines happens through shared files — not API calls.

```
Engine          Writes                                    Interpreter reads
──────────────────────────────────────────────────────────────────────────
News Terminal → premarket_candidates_YYYYMMDD.csv     → catalyst context
              → macro_intelligence_latest.json        → regime alignment
MA Cockpit    → ma_candidates_YYYYMMDD.csv  (merged into premarket_candidates by combiner)
                                                    MA Cockpit does NOT feed interpreter directly
Pipeline      → morning_validated_trades_YYYYMMDD.csv → quantitative scores
```

All four files must be present and dated TODAY for full convergence triage.
The session check (below) enforces this on every startup.

---

### SESSION CHECK — runs at every interpreter startup

In `pipeline_interpreter_commands.py`, add `run_session_check()` called at startup:

```python
def run_session_check():
    """
    Verify all three engine outputs are present and dated today.
    This is the communication check between engines.
    Runs automatically at interpreter startup before any command is accepted.
    """
    from pathlib import Path
    from datetime import datetime

    BASE  = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
    TODAY = datetime.now().strftime("%Y%m%d")

    # THREE engines only — MA Cockpit data arrives via premarket_candidates after ACK review
    checks = {
        "Pipeline output": {
            "dir":     BASE / "pipeline_interpreter" / "MA_Inputs" / "pipeline_outputs",
            "pattern": f"morning_validated_trades_{TODAY}_*.csv",
            "fallback": "morning_validated_trades_*.csv",
            "key":     "pipeline_csv",
        },
        "Macro JSON": {
            "dir":     BASE / "pipeline_interpreter" / "MA_Inputs" / "macro",
            "pattern": "macro_intelligence_latest.json",
            "fallback": None,
            "key":     "macro_json",
        },
        "Merged candidates": {
            "dir":     BASE / "dropbox" / "inputs",
            "pattern": f"premarket_candidates_{TODAY}.csv",
            "fallback": "premarket_candidates_*.csv",
            "key":     "catalyst_csv",
            "note":    "newsroom + MA cockpit merged — present only if ACK uploaded",
        },
    }

    print("\n" + "═" * 60)
    print("  SESSION CHECK — ENGINE COMMUNICATION STATUS")
    print("═" * 60)

    all_ok = True
    for label, cfg in checks.items():
        files = sorted(cfg["dir"].glob(cfg["pattern"]),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        if files:
            f = files[0]
            dated = TODAY in f.name
            status = "✓" if dated else "⚠ (STALE)"
            if not dated:
                all_ok = False
            print(f"  {label:<22} {status}  {f.name}")
            SESSION[cfg["key"]] = str(f)
        else:
            # Try fallback
            if cfg["fallback"]:
                fb = sorted(cfg["dir"].glob(cfg["fallback"]),
                            key=lambda f: f.stat().st_mtime, reverse=True)
                if fb:
                    print(f"  {label:<22} ⚠ YESTERDAY  {fb[0].name}")
                    SESSION[cfg["key"]] = str(fb[0])
                    all_ok = False
                else:
                    print(f"  {label:<22} ✗ NOT FOUND")
                    SESSION[cfg["key"]] = None
                    all_ok = False
            else:
                print(f"  {label:<22} ✗ NOT FOUND")
                SESSION[cfg["key"]] = None
                all_ok = False

    print("═" * 60)
    if all_ok:
        print("  STATUS: ALL THREE SOURCES PRESENT — full convergence triage available")
    else:
        print("  STATUS: WARNING — one or more sources missing or stale")
        print("          Pipeline output and Macro JSON are required.")
        print("          Merged candidates optional — present only if ACK uploaded today.")
        print("          Triage will proceed on available sources.")
    print("═" * 60 + "\n")
```

---

### MODE 1 — /triage (NO screenshots — runs on all pipeline-validated tickers)

**Purpose:** Enrich every pipeline-validated ticker with everything all three
engines know about it. Rank by convergence. Produce HTML output.
This replaces the manual /triage step — it now runs the full enrichment automatically.

**What triage reads for each ticker — THREE sources:**
```
1. Pipeline CSV         → EIL verdict, PSE mode, SCS score, momentum tier,
                          wyckoff phase bucket, GARCH jump risk, IVP label,
                          EV, capital permission, FD verdict, signal type

2. Macro JSON           → regime state, sector tilt, sector lead/avoid,
                          vol mode, put gate — is this ticker's sector
                          favoured, vulnerable, or neutral today?

3. Merged candidates    → premarket_candidates_YYYYMMDD.csv
   (if uploaded by ACK)   contains newsroom catalyst data AND MA cockpit data
                          already merged by combiner.
                          catalyst type, direction bias, ANIS, FIPS,
                          tradability route, confirmation signals,
                          missing data, ticker role, deal status.
                          OPTIONAL — triage proceeds without it if not uploaded.

4. Live news (always)   → web search for "[TICKER] news today" to surface
                          any breaking narrative not in structured files.
```

**Convergence scoring per ticker:**

```python
def score_convergence(pipeline_row, macro_data, catalyst_row, ma_row, news_hits):
    """
    Score 0-100 across four signal sources.
    Higher = more engines agree, more context available.
    """
    score = 0

    # Pipeline score (40 points max)
    if pipeline_row.get("eil_v3_verdict") == "EXECUTE":          score += 20
    if pipeline_row.get("pse_execution_mode") in ("PROBE","STRUCTURAL_WATCH"): score += 10
    scs = float(pipeline_row.get("scs_score", 0) or 0)
    score += min(10, int(scs / 10))

    # Macro alignment (20 points max)
    sector = pipeline_row.get("sector", "")
    sector_lead = macro_data.get("sector_lead", [])
    sector_avoid = macro_data.get("sector_avoid", [])
    if any(s in sector for s in sector_lead):                     score += 20
    elif any(s in sector for s in sector_avoid):                  score -= 10

    # Newsroom catalyst (25 points max)
    if catalyst_row is not None:
        anis = float(catalyst_row.get("anis_score", 0) or 0)
        score += min(15, int(anis / 7))
        if catalyst_row.get("catalyst_status") == "CONFIRMED":    score += 10

    # Note: MA cockpit data arrives via catalyst_row (merged premarket_candidates)
    # not as a separate source. catalyst_binary_score already reflects MA events
    # if ACK uploaded the merged CSV.

    return max(0, min(100, score))
```

**Triage HTML output — one card per ticker, ranked by convergence score:**

Build `generate_triage_html()` that produces a single HTML file:
`pipeline_interpreter\MA_Inputs\triage_output_YYYYMMDD_HHMMSS.html`

Each ticker card must contain:

```html
<!-- TICKER CARD STRUCTURE -->
<div class="ticker-card {convergence-class}">
  <div class="card-header">
    <span class="ticker">MA</span>
    <span class="company">Mastercard Inc.</span>
    <span class="convergence-badge HIGH">CONVERGENCE: HIGH (78)</span>
    <span class="pipeline-verdict EXECUTE">EXECUTE</span>
  </div>

  <div class="pipeline-row">
    <span>SCS: 61.4</span>
    <span>PSE: PROBE</span>
    <span>Momentum: TIER_2_SUSTAINING</span>
    <span>Wyckoff: MARKUP</span>
    <span>GARCH: LOW</span>
    <span>IVP: FAIR</span>
    <span>EV: +8.2%</span>
  </div>

  <div class="macro-row">
    <span>Regime: TRANSITIONAL_BULLISH</span>
    <span>Sector: Financials — FAVOURED ✓</span>
    <span>Vol Mode: VOL_EXPANSION</span>
    <span>Put Gate: OPEN</span>
  </div>

  <div class="catalyst-row">
    <!-- Present if ticker in premarket_candidates -->
    <span>Catalyst: EARNINGS_CATALYST (CONFIRMED)</span>
    <span>Bias: LONG_CALL_WATCH</span>
    <span>ANIS: 82 | FIPS: 76</span>
    <span>Route: FULL_PIPELINE</span>
    <span class="missing">Missing: Live options flow</span>
    <!-- OR if not in newsroom: -->
    <span class="none">No newsroom catalyst today</span>
  </div>

  <div class="news-row">
    <!-- Live news narrative pulled during triage -->
    <p>[Live news summary for ticker — pulled at triage time]</p>
  </div>

  <div class="card-footer">
    <span class="deep-dive-flag">→ DEEP DIVE CANDIDATE</span>
    <!-- OR: -->
    <span class="watch-flag">→ WATCH — pipeline weak</span>
  </div>
</div>
```

**HTML page structure:**
```
TRIAGE REPORT — AVSHUNTER — 2026-05-15 09:35
═══════════════════════════════════════════
SESSION CHECK SUMMARY (engine status at top)
═══════════════════════════════════════════
SECTION 1: CONVERGENT (pipeline + newsroom both present)
  → Ranked by convergence score descending

SECTION 2: PIPELINE ONLY (no newsroom match)
  → Ranked by SCS score descending

═══════════════════════════════════════════
SHORTLIST FOR DEEP DIVE
  Tickers scoring convergence ≥ 60 OR manually flagged:
  → MA, D, SYY
  Run: /ticker MA | /ticker D | /ticker SYY
═══════════════════════════════════════════
```

---

### MODE 2 — /ticker <TICKER> (screenshots REQUIRED — runs on shortlisted tickers only)

**Purpose:** Full qualitative deep dive on a single ticker selected from triage.
This is the complete v11.1 analysis — Dr. Magnus Vale, NEIL, Soul of the Chart,
THE SCENARIO, ZETA Final Verdict.

**What /ticker reads:**
```
1. Pipeline CSV row for this ticker  (quantitative foundation)
2. Macro JSON                        (regime context)
3. Merged candidates row if present  (newsroom + MA cockpit context,
                                      if ACK uploaded premarket_candidates)
4. Chart screenshot(s)               ← REQUIRED — drop in MA_Inputs\charts\
                                       before running /ticker
```

**Chart input:** place chart screenshot(s) in:
`pipeline_interpreter\MA_Inputs\charts\<TICKER>_<YYYYMMDD>.*`

The interpreter reads the chart visually as the primary source of truth for:
- Bar structure and volume narrative
- Wyckoff event mapping (Springs, UPTHRUSTs, SOS/SOW)
- Trapped participant identification
- NEIL behavioural tape read
- Soul of the Chart synthesis

**Output sections (exact headers, in order):**
```
[TRADE_NARRATIVE_{TICKER}]
MACRO ALIGNMENT
NEWS NARRATIVE OVERLAY
DR. MAGNUS VALE — DIAGNOSIS
DR. MAGNUS VALE — EVIDENCE QUALITY
DR. MAGNUS VALE — TRAPPED PARTICIPANTS
DR. MAGNUS VALE — CHESS MOVE TREE
SOUL OF THE CHART
SOUL OF THE CHART — BULLISH CASE
SOUL OF THE CHART — BEARISH CASE
SOUL OF THE CHART — BEHAVIOURAL VERDICT
THE SCENARIO
EXECUTION PRESCRIPTION
KILL SWITCH
MONETISATION
FINAL VERDICT
```

**Output files:**
- `ticker_<TICKER>_interpreter_YYYYMMDD_HHMM.html`  (full narrative)
- `ticker_<TICKER>_trade_brief_YYYYMMDD_HHMM.csv`   (structured brief)

---

### FIXES TO EXISTING INTERPRETER CODE

**Fix A — Session persistence after /triage**

After triage completes, store pipeline CSV in session:
```python
SESSION["last_pipeline_csv"] = str(loaded_csv_path)
SESSION["last_triage_run"]   = datetime.now().isoformat()
print(f"  [SESSION] CSV locked: {Path(loaded_csv_path).name}")
print(f"  [SESSION] /ticker <TICKER> ready")
```

In `/ticker` handler:
```python
def handle_ticker_command(ticker: str, csv_path: str = None):
    if not csv_path:
        csv_path = SESSION.get("last_pipeline_csv")
        if not csv_path:
            print("[ERROR] No CSV loaded. Run /triage first.")
            return
        print(f"  [AUTO] {Path(csv_path).name}")
    # continue with existing logic
```

**Fix B — Path-with-spaces (shlex)**
```python
import shlex
try:
    parts = shlex.split(raw_input.lstrip("/"))
except ValueError:
    parts = raw_input.lstrip("/").split(None, 2)
```

**Fix C — Remove execution_permission BLOCK gate**

Find and remove any gate that blocks analysis on
`execution_permission=NONE_NEWS_TERMINAL_ONLY`. Replace with:
```python
permission = row.get("execution_permission", "UNKNOWN")
NON_LIVE = {"NONE_NEWS_TERMINAL_ONLY", "WATCHLIST_ONLY", "PIPELINE_BLOCKED"}
if permission in NON_LIVE:
    print(f"  [NOTE] execution_permission={permission} — analysis proceeds")
# Do NOT return — continue with full analysis
```

---

## STEP 8 — MODEL ROUTING

Search:
```
findstr /s /i "claude-" C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\news_terminal\*.py
findstr /s /i "claude-" C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\ma_cockpit\*.py
findstr /s /i "claude-" C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter\*.py
```

**News Terminal — Sonnet (fast, cost-efficient for intelligence gathering):**
```python
MODEL = "claude-sonnet-4-20250514"
```

**MA Cockpit — Sonnet:**
```python
MODEL = "claude-sonnet-4-20250514"
```

**Pipeline Interpreter — Opus (deep analysis, narrative quality):**
```python
MODEL = "claude-opus-4-5-20251101"
```

Set as module-level constants at top of each file. Replace all inline model strings.

---

## STEP 9 — VERIFICATION

Run each check and report pass/fail:

**1. Directory structure**
```
dir "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\dropbox\inputs"
dir "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\dropbox\macro"
dir "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter\MA_Inputs\macro"
dir "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter\MA_Inputs\pipeline_outputs"
```

**2. Combiner dry run**
```
python news_terminal\build_premarket_candidates.py
```
Check: file written to `dropbox\inputs\premarket_candidates_YYYYMMDD.csv`
Check: `execution_permission` = `NONE_NEWS_TERMINAL_ONLY` for ALL rows
Check: `capital_grade` = `NO` for ALL rows
Check: tickers file written to `dropbox\inputs\news_terminal_tickers_YYYYMMDD.txt`

**3. Interpreter auto-load**
Start interpreter. Confirm it prints `[INTERPRETER] Auto-loaded: morning_validated_trades_...`
without requiring `/triage`.

**4. Interpreter BLOCK fix**
Run `/ticker` on a ticker with `execution_permission=NONE_NEWS_TERMINAL_ONLY`.
Expected: `[NOTE]` lines printed, full analysis proceeds.
Not expected: `BLOCKED:` line, early return.

**5. Model strings**
```
findstr /s "MODEL" C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\news_terminal\*.py
findstr /s "MODEL" C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\ma_cockpit\*.py
findstr /s "MODEL" C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter\*.py
```
Expected: Sonnet in news_terminal + ma_cockpit, Opus in pipeline_interpreter.

**6. End-to-end flow simulation**
Simulate one full cycle:
- Place a sample `avshunter_catalyst_csv_YYYYMMDD.csv` in `news_terminal\outputs\`
- Place a sample `ma_candidates_YYYYMMDD.csv` in `ma_cockpit\outputs\`
- Run `build_premarket_candidates.py`
- Confirm `premarket_candidates_YYYYMMDD.csv` appears in `dropbox\inputs\`
- Confirm `news_terminal_tickers_YYYYMMDD.txt` appears in `dropbox\inputs\`

---

---

## STEP 10 — INTERPRETER QA: ANALYSIS QUALITY CHECKS

Build `pipeline_interpreter\interpreter_qa.py`.

This runs automatically after every `/triage` and every `/ticker` command.
It validates three things: correct data was ingested, output sections are complete,
and the interpreter's conclusion is consistent with the pipeline verdict.

**This is not a data pipeline tool. It is an analysis quality tool.**
It checks whether the interpreter reasoned correctly given what the pipeline said.

```python
"""
interpreter_qa.py
Runs after every /triage and /ticker command.
Checks: data ingestion completeness, output section integrity,
        pipeline-vs-interpreter verdict consistency.
Writes: QA block to console + appends to interpreter_qa_log_YYYYMMDD.csv
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import json

BASE    = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
TODAY   = datetime.now().strftime("%Y%m%d")
QA_LOG  = BASE / "pipeline_interpreter" / "MA_Inputs" / f"interpreter_qa_log_{TODAY}.csv"

# Required output sections for Mode 2 /ticker deep dive
REQUIRED_SECTIONS = [
    "MACRO ALIGNMENT",
    "NEWS NARRATIVE OVERLAY",
    "DR. MAGNUS VALE — DIAGNOSIS",
    "DR. MAGNUS VALE — EVIDENCE QUALITY",
    "DR. MAGNUS VALE — TRAPPED PARTICIPANTS",
    "DR. MAGNUS VALE — CHESS MOVE TREE",
    "SOUL OF THE CHART",
    "SOUL OF THE CHART — BULLISH CASE",
    "SOUL OF THE CHART — BEARISH CASE",
    "SOUL OF THE CHART — BEHAVIOURAL VERDICT",
    "THE SCENARIO",
    "EXECUTION PRESCRIPTION",
    "KILL SWITCH",
    "MONETISATION",
    "FINAL VERDICT",
]

# Pipeline fields expected to be populated for a valid deep dive
REQUIRED_PIPELINE_FIELDS = [
    "ticker", "eil_v3_verdict", "pse_execution_mode", "scs_score",
    "momentum_tier", "wyckoff_phase_bucket", "signal_type",
    "ivp_label", "capital_permission", "fd_verdict",
]

# Direction keywords for consistency check
BULLISH_KEYWORDS = {"LONG_CALL", "BULLISH", "CALL", "UPSIDE", "BUY"}
BEARISH_KEYWORDS = {"LONG_PUT", "BEARISH", "PUT", "DOWNSIDE", "SELL", "SHORT"}


def check_triage_qa(pipeline_csv: str, macro_json: str, candidates_csv: str = None) -> dict:
    """
    QA check after /triage.
    Validates all three source files loaded correctly and are dated today.
    """
    results = {
        "mode": "TRIAGE",
        "timestamp": datetime.now().isoformat(),
        "checks": {}
    }

    # Check pipeline CSV
    try:
        df = pd.read_csv(pipeline_csv, low_memory=False)
        dated = TODAY in Path(pipeline_csv).name
        results["checks"]["pipeline_csv"] = {
            "status": "PASS" if dated else "WARN",
            "rows": len(df),
            "dated_today": dated,
            "file": Path(pipeline_csv).name,
        }
    except Exception as e:
        results["checks"]["pipeline_csv"] = {"status": "FAIL", "error": str(e)}

    # Check macro JSON
    try:
        with open(macro_json) as f:
            macro = json.load(f)
        report_date = macro.get("report_date", "UNKNOWN")
        dated = report_date == datetime.now().strftime("%Y-%m-%d")
        results["checks"]["macro_json"] = {
            "status": "PASS" if dated else "WARN",
            "report_date": report_date,
            "dated_today": dated,
            "batch_id": macro.get("batch_id", "MISSING"),
        }
    except Exception as e:
        results["checks"]["macro_json"] = {"status": "FAIL", "error": str(e)}

    # Check merged candidates (optional)
    if candidates_csv and Path(candidates_csv).exists():
        try:
            cdf = pd.read_csv(candidates_csv, low_memory=False)
            dated = TODAY in Path(candidates_csv).name
            # Verify locked fields
            perm_ok = (cdf["execution_permission"] == "NONE_NEWS_TERMINAL_ONLY").all()
            grade_ok = (cdf["capital_grade"] == "NO").all()
            results["checks"]["merged_candidates"] = {
                "status": "PASS" if (dated and perm_ok and grade_ok) else "WARN",
                "rows": len(cdf),
                "dated_today": dated,
                "execution_permission_locked": perm_ok,
                "capital_grade_locked": grade_ok,
            }
        except Exception as e:
            results["checks"]["merged_candidates"] = {"status": "FAIL", "error": str(e)}
    else:
        results["checks"]["merged_candidates"] = {
            "status": "INFO",
            "note": "Not uploaded — triage ran on pipeline + macro only"
        }

    return results


def check_ticker_qa(
    ticker: str,
    pipeline_row: dict,
    html_output_path: str,
    trade_brief_path: str,
    macro_data: dict,
) -> dict:
    """
    QA check after /ticker deep dive.
    Checks: pipeline field completeness, output section presence,
            pipeline-vs-interpreter verdict consistency.
    """
    results = {
        "mode": "DEEP_DIVE",
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "checks": {}
    }

    # 1 — Pipeline field completeness
    missing_fields = [f for f in REQUIRED_PIPELINE_FIELDS
                      if not pipeline_row.get(f) or str(pipeline_row.get(f)).strip() in ("", "nan", "None")]
    populated = len(REQUIRED_PIPELINE_FIELDS) - len(missing_fields)
    completeness_pct = round(100 * populated / len(REQUIRED_PIPELINE_FIELDS))
    results["checks"]["pipeline_fields"] = {
        "status": "PASS" if completeness_pct >= 80 else "WARN",
        "completeness_pct": completeness_pct,
        "populated": populated,
        "total_expected": len(REQUIRED_PIPELINE_FIELDS),
        "missing": missing_fields,
    }

    # 2 — HTML output section integrity
    if Path(html_output_path).exists():
        html = Path(html_output_path).read_text(encoding="utf-8", errors="ignore")
        missing_sections = [s for s in REQUIRED_SECTIONS if s not in html]
        results["checks"]["output_sections"] = {
            "status": "PASS" if not missing_sections else "FAIL",
            "sections_present": len(REQUIRED_SECTIONS) - len(missing_sections),
            "sections_total": len(REQUIRED_SECTIONS),
            "missing_sections": missing_sections,
        }
    else:
        results["checks"]["output_sections"] = {
            "status": "FAIL",
            "error": f"HTML output not found: {html_output_path}"
        }

    # 3 — Verdict consistency: pipeline direction vs interpreter conclusion
    pipeline_verdict  = str(pipeline_row.get("eil_v3_verdict", "")).upper()
    pipeline_bias     = str(pipeline_row.get("catalyst_direction_bias", "")).upper()
    pipeline_is_bull  = any(k in pipeline_verdict or k in pipeline_bias for k in BULLISH_KEYWORDS)
    pipeline_is_bear  = any(k in pipeline_verdict or k in pipeline_bias for k in BEARISH_KEYWORDS)

    if Path(html_output_path).exists():
        html_upper = html.upper()
        # Read FINAL VERDICT section
        fv_idx = html_upper.find("FINAL VERDICT")
        fv_text = html_upper[fv_idx:fv_idx + 500] if fv_idx > -1 else ""
        interp_is_bull = any(k in fv_text for k in BULLISH_KEYWORDS)
        interp_is_bear = any(k in fv_text for k in BEARISH_KEYWORDS)

        if pipeline_is_bull and interp_is_bear:
            consistent = False
            note = "INVERSION: pipeline BULLISH but interpreter BEARISH — review required"
        elif pipeline_is_bear and interp_is_bull:
            consistent = False
            note = "INVERSION: pipeline BEARISH but interpreter BULLISH — review required"
        else:
            consistent = True
            note = "Direction consistent"

        results["checks"]["verdict_consistency"] = {
            "status": "PASS" if consistent else "WARN",
            "pipeline_direction": "BULLISH" if pipeline_is_bull else ("BEARISH" if pipeline_is_bear else "UNKNOWN"),
            "interpreter_direction": "BULLISH" if interp_is_bull else ("BEARISH" if interp_is_bear else "UNKNOWN"),
            "consistent": consistent,
            "note": note,
        }

    # 4 — Date alignment: pipeline and macro from same session
    pipeline_date = pipeline_row.get("run_date", pipeline_row.get("date", "UNKNOWN"))
    macro_date    = macro_data.get("report_date", "UNKNOWN")
    date_match    = str(pipeline_date)[:10] == str(macro_date)[:10]
    results["checks"]["date_alignment"] = {
        "status": "PASS" if date_match else "WARN",
        "pipeline_date": pipeline_date,
        "macro_date": macro_date,
        "match": date_match,
        "note": "" if date_match else "Pipeline and macro are from different sessions — stale data risk",
    }

    return results


def print_qa_report(results: dict):
    """Print QA report to console in a readable format."""
    ticker = results.get("ticker", "TRIAGE")
    mode   = results.get("mode", "")
    print("\n" + "═" * 60)
    print(f"  QA REPORT — {ticker} — {mode}")
    print("═" * 60)

    overall = "PASS"
    for name, check in results.get("checks", {}).items():
        status = check.get("status", "UNKNOWN")
        if status == "FAIL":
            overall = "FAIL"
        elif status == "WARN" and overall == "PASS":
            overall = "WARN"

        icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗", "INFO": "ℹ"}.get(status, "?")
        print(f"  {icon} {name:<28} {status}")

        # Print key details
        if status in ("WARN", "FAIL"):
            for k, v in check.items():
                if k != "status" and v:
                    print(f"      {k}: {v}")

    print("─" * 60)
    print(f"  QA VERDICT: {overall}")
    if overall == "WARN":
        print("  Review flagged items before execution decision.")
    elif overall == "FAIL":
        print("  Do not proceed — critical QA failure.")
    print("═" * 60 + "\n")

    return overall


def append_qa_log(results: dict):
    """Append QA result to daily log CSV."""
    row = {
        "timestamp":  results.get("timestamp"),
        "mode":       results.get("mode"),
        "ticker":     results.get("ticker", "TRIAGE"),
        "overall":    "PASS",
    }
    for name, check in results.get("checks", {}).items():
        row[f"{name}_status"] = check.get("status", "")

    df = pd.DataFrame([row])
    if QA_LOG.exists():
        existing = pd.read_csv(QA_LOG)
        df = pd.concat([existing, df], ignore_index=True)
    df.to_csv(QA_LOG, index=False)
```

**Wire into the interpreter:**

In `pipeline_interpreter_commands.py`, import and call after each command:

```python
from interpreter_qa import check_triage_qa, check_ticker_qa, print_qa_report, append_qa_log

# After /triage completes:
qa = check_triage_qa(
    pipeline_csv   = SESSION.get("pipeline_csv"),
    macro_json     = SESSION.get("macro_json"),
    candidates_csv = SESSION.get("catalyst_csv"),
)
overall = print_qa_report(qa)
append_qa_log(qa)

# After /ticker completes:
qa = check_ticker_qa(
    ticker            = ticker,
    pipeline_row      = ticker_pipeline_row,
    html_output_path  = str(html_output_file),
    trade_brief_path  = str(brief_csv_file),
    macro_data        = loaded_macro_dict,
)
overall = print_qa_report(qa)
append_qa_log(qa)
```

**QA log location:** `pipeline_interpreter\MA_Inputs\interpreter_qa_log_YYYYMMDD.csv`

Accumulates across the session. At end of day shows every ticker analysed,
QA verdict, and any flags raised. Gives you a daily quality audit trail.

---


## HARD CONSTRAINTS — NEVER VIOLATE

1. `execution_permission` in ALL news terminal and MA cockpit output = `NONE_NEWS_TERMINAL_ONLY`
2. `capital_grade` in ALL news terminal and MA cockpit output = `NO`
3. Never override protected macro fields in the enrichment delta
4. News terminal tickers SUPPLEMENT the pipeline universe — never replace it
5. Pipeline interpreter is research-only — never block analysis on any ticker
6. Mode 1 (/triage) — NO screenshots. Structured data only. All 3 engine files.
7. Mode 2 (/ticker) — screenshots REQUIRED. Drop chart in MA_Inputs\\charts\\ first.
8. Session check runs at every startup — enforces three-engine communication contract
9. Model constants must be set at module level, not inline

---

## HOW TO RUN IN CLAUDE CODE

```
cd C:\Users\ACKVerissimo\AVSHUNTER-Intelligence
claude
```

In Claude Code:
```
Read CLAUDE_CODE_AVSHUNTER_INTEGRATION_v3.md and execute all steps in order.
Begin with Step 0 audit and report findings before making any changes.
```

---

*v3.3 — MA Cockpit correctly scoped as standalone (report + CSV only); removed from interpreter reads; three-engine session check; MA data reaches interpreter only via merged premarket_candidates after ACK review
Generated: 2026-05-15 | AVSHUNTER-Intelligence integration sprint
macro delta structure, MA cockpit integration, pipeline universe injection, interpreter
auto-load, screenshot removal, and model routing*
*Generated: 2026-05-15 | AVSHUNTER-Intelligence integration sprint*
