# CLAUDE_CODE_AVSHUNTER_SECTOR_MASTER_v1.md
# AVSHUNTER Sector Master — Build Sprint
# Makeo Consulting Limited · ACK Verissimo · May 2026
# ─────────────────────────────────────────────────────────────────────────────
# TRIGGER: Read this file and execute all steps in order.
#          Begin with Step 0 audit and report findings before making any changes.
# ─────────────────────────────────────────────────────────────────────────────

## CONTEXT — WHY THIS SPRINT EXISTS

The pipeline currently resolves sector for 95.1% of tickers as UNKNOWN.
This means macro_bias, sector_etf, and macro_abstain fields are empty or
wrong for 1,040 of 1,094 tickers scored by EIL.

The EIL enrichment modifiers (CALL_TAILWIND +modifier, PUT_HEADWIND -modifier,
MACRO_ABSTAIN bypass) already exist in execution_intelligence.py — but they
produce zero effect because the input fields are UNKNOWN for 95% of tickers.

The sector master resolves this at the source — before discovery runs —
so every downstream layer (Discovery, Options Intelligence, EIL, Morning
Validation) receives correct sector context for every ticker.

Three ticker routes enter the pipeline:
  ROUTE 1: polygon_liquid_universe.csv — 1,998 tickers, ticker only, no sector
  ROUTE 2: Options Scanner output — supplementary tickers, may have no sector
  ROUTE 3: premarket_candidates_{date}.csv — MA Cockpit + News Room merged,
            has descriptive sector labels (not GICS standard)

The sector master resolves all three routes into one authoritative lookup.

## GOVERNING RULES

1. Show exact code before saving any file.
2. After each step confirm: which files changed, which lines changed.
3. Never modify: intelligent_orchestrator.py macro routing,
   macro_horizon_router.py, final_decision_engine.py, execution_intelligence.py
   (beyond what is explicitly instructed in Step 4).
4. If a mapping file referenced in Step 0 does not exist — log it and
   use the next priority source. Never fail hard on a missing mapping file.
5. The sector master must be NON-CRITICAL — if it fails the pipeline
   continues with UNKNOWN sector, not a hard stop.

---

## STEP 0 — AUDIT (NO CHANGES)

Report findings on all of the following before touching anything.

**0.1 Confirm which sector mapping files exist and their row counts:**
- `master_ticker_list2026_WITH_SECTORS.csv` (any location)
- `data/universe/Archive/hybrid_universe_enhanced__with_sector.csv`
- `Sector_Mapping_2211.xlsx`
- `Sector_Mapping_2_2211.xlsx`
- `sector_mapping_3_2211.xlsx`
- `Sector_Mapping_4_2211.xlsx`
- `XLK_MASTER_TICKERS.csv`
- `XLE_MASTER_TICKERS.csv`
- `XLF_MASTER_TICKERS.csv`
- `XLI_MASTER_TICKERS.csv`
- `XLV_MASTER_TICKERS.csv`
- `XLY_MASTER_TICKERS.csv`
- `XLP_MASTER_TICKERS.csv`
- `XLU_MASTER_TICKERS.csv`
- `XLB_MASTER_TICKERS.csv`

For each file that exists report:
  - Full path
  - Number of rows
  - Column names
  - Whether VST, NEE, CEG appear and what sector they show

**0.2 Check the universe file:**
- `polygon_liquid_universe.csv` — confirm it is ticker-only (no sector column)
- Count rows

**0.3 Check the orchestrator for where sector master would be called:**
- Search intelligent_orchestrator.py for any existing sector resolution
  calls, sector_master references, or build_sector_master references
- Report what exists and what line numbers

**0.4 Check scripts/ directory:**
- List all .py files in scripts/
- Confirm whether build_sector_master.py or resolve_sector.py already exist

**0.5 Check the premarket candidates file:**
- Look in dropbox/inputs/ for premarket_candidates_{today}.csv or latest
- If found: report column names and sample sector field values
  (to understand Route 3 descriptive labels that need normalising)

**0.6 Check apply_macro_enrichment_to_discovery.py:**
- Confirm MACRO_ABSTAIN_TICKERS = {"VST", "NEE", "CEG"} exists
- Confirm _extract_bias_maps() and _resolve_macro_bias() functions exist
- Report line numbers

Report all findings. Do not change any file. Proceed to Step 1 only
after audit is complete.

---

## STEP 1 — BUILD scripts/build_sector_master.py

**File:** NEW FILE — `scripts/build_sector_master.py`
**Risk:** SAFE — standalone script, no existing file modified
**Do not touch any other file in this step**

**What it does:**
Reads all available sector mapping sources in priority order.
Resolves every ticker in the universe to:
  - gics_sector (GICS standard sector name)
  - sector_etf  (the ETF that represents this sector for macro bias)
  - macro_bias  (CALL_TAILWIND / PUT_HEADWIND / NEUTRAL — from macro JSON)
  - macro_abstain (True for power generation exception tickers)

Writes the result to:
  `data/sector_master_{run_id}.csv`  (run-specific)
  `data/sector_master_latest.csv`    (always overwritten — latest run)

**Create the file:**

```python
#!/usr/bin/env python3
"""
build_sector_master.py
======================
Builds a single authoritative sector lookup for all pipeline tickers.
Resolves ticker -> gics_sector -> sector_etf -> macro_bias -> macro_abstain.

Reads sector mapping files in priority order:
  1. Hardcoded exceptions (VST, NEE, CEG -> Power Generation)
  2. master_ticker_list2026_WITH_SECTORS.csv
  3. hybrid_universe_enhanced__with_sector.csv
  4. Sector_Mapping_2211.xlsx (and variants)
  5. ETF master ticker files (XLK, XLE, XLF, XLI, XLV, XLY, XLP, XLU, XLB)
  6. UNKNOWN (small penalty, not a block)

NON-CRITICAL: if this script fails, pipeline continues with UNKNOWN sector.
Called by intelligent_orchestrator.py before discovery phase.

Usage:
  python scripts/build_sector_master.py
      --macro-path dropbox/macro/macro_intelligence_latest.json
      --run-id 20260516_120000
      --output-dir data
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

# ── Repo root ─────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parents[1]

# ── Hardcoded exceptions — power generation, not rate-sensitive utilities ─────
HARDCODED_SECTOR_OVERRIDES: Dict[str, str] = {
    "VST": "Power Generation",
    "NEE": "Power Generation",
    "CEG": "Power Generation",
}
MACRO_ABSTAIN_TICKERS = set(HARDCODED_SECTOR_OVERRIDES.keys())

# ── GICS sector -> Sector ETF mapping (permanent, never changes) ──────────────
SECTOR_ETF_MAP: Dict[str, str] = {
    "Energy":                   "XLE",
    "Information Technology":   "XLK",
    "Financials":               "XLF",
    "Financial Services":       "XLF",
    "Health Care":              "XLV",
    "Healthcare":               "XLV",
    "Consumer Discretionary":   "XLY",
    "Consumer Staples":         "XLP",
    "Industrials":              "XLI",
    "Materials":                "XLB",
    "Real Estate":              "XLRE",
    "Utilities":                "XLU",
    "Communication Services":   "XLC",
    "Power Generation":         "XLE",   # VST/NEE/CEG exception -> energy ETF
    "Technology":               "XLK",   # alias
    "Finance":                  "XLF",   # alias
}

# ── Route 3 descriptive label normalisation -> GICS ──────────────────────────
SECTOR_NORMALISE: Dict[str, str] = {
    "Oil Services":             "Energy",
    "Integrated Oil":           "Energy",
    "Oil & Gas":                "Energy",
    "Energy Services":          "Energy",
    "Defence":                  "Industrials",
    "Defense":                  "Industrials",
    "Aerospace & Defence":      "Industrials",
    "Aerospace & Defense":      "Industrials",
    "Semiconductors":           "Information Technology",
    "Semiconductor":            "Information Technology",
    "Software":                 "Information Technology",
    "Tech":                     "Information Technology",
    "Mega-cap Growth":          "Information Technology",
    "AI Infrastructure":        "Information Technology",
    "Regional Banks":           "Financials",
    "Banks":                    "Financials",
    "Insurance":                "Financials",
    "Airlines":                 "Consumer Discretionary",
    "Cruise Lines":             "Consumer Discretionary",
    "Retail":                   "Consumer Discretionary",
    "Autos":                    "Consumer Discretionary",
    "Homebuilders":             "Real Estate",
    "REITs":                    "Real Estate",
    "REIT":                     "Real Estate",
    "Logistics":                "Industrials",
    "Transport":                "Industrials",
    "Telecom":                  "Communication Services",
    "Media":                    "Communication Services",
    "Biotech":                  "Health Care",
    "Pharma":                   "Health Care",
    "Mining":                   "Materials",
    "Miners":                   "Materials",
    "Chemicals":                "Materials",
    "Gold":                     "Materials",
    "Silver":                   "Materials",
    "Staples":                  "Consumer Staples",
    "Food & Beverage":          "Consumer Staples",
    "Tobacco":                  "Consumer Staples",
    "Power Generation":         "Power Generation",
    "Nuclear":                  "Power Generation",
    "Renewable":                "Power Generation",
}

# ── ETF membership -> GICS sector fallback ───────────────────────────────────
ETF_TO_SECTOR: Dict[str, str] = {
    "XLE": "Energy",
    "XLK": "Information Technology",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLRE":"Real Estate",
    "XLU": "Utilities",
    "XLC": "Communication Services",
}

# ── Macro bias from sector ETF (reads from macro JSON sector_rotation block) ──
DEFAULT_MACRO_BIAS: Dict[str, str] = {
    "XLE":  "NEUTRAL",
    "XLK":  "NEUTRAL",
    "XLF":  "NEUTRAL",
    "XLV":  "NEUTRAL",
    "XLY":  "NEUTRAL",
    "XLP":  "NEUTRAL",
    "XLI":  "NEUTRAL",
    "XLB":  "NEUTRAL",
    "XLRE": "NEUTRAL",
    "XLU":  "NEUTRAL",
    "XLC":  "NEUTRAL",
}

OUTPUT_COLS = ["ticker", "gics_sector", "sector_etf", "macro_bias", "macro_abstain"]

# ── Validation guard ──────────────────────────────────────────────────────────
MAX_SECTOR_PCT = 0.35   # if any single sector > 35% of universe, raise an error


def normalise_sector(raw: str) -> str:
    """Normalise a raw sector label to GICS standard."""
    if not raw or str(raw).strip() in ("", "nan", "None"):
        return ""
    raw = str(raw).strip()
    # Direct match first
    if raw in SECTOR_NORMALISE:
        return SECTOR_NORMALISE[raw]
    # Case-insensitive match
    raw_lower = raw.lower()
    for key, val in SECTOR_NORMALISE.items():
        if key.lower() == raw_lower:
            return val
    # Already a valid GICS sector
    if raw in SECTOR_ETF_MAP:
        return raw
    return raw   # return as-is — may still match ETF map


def load_macro_bias_from_json(macro_path: Path) -> Dict[str, str]:
    """
    Read macro_intelligence_latest.json sector_rotation block.
    Returns dict of sector_etf -> macro_bias (CALL_TAILWIND/PUT_HEADWIND/NEUTRAL).
    Falls back to DEFAULT_MACRO_BIAS if block is missing.
    """
    bias_map = dict(DEFAULT_MACRO_BIAS)
    try:
        with macro_path.open("r", encoding="utf-8") as fh:
            macro = json.load(fh)

        # Try sector_rotation block first
        sr = macro.get("sector_rotation") or {}
        sbm = sr.get("sector_bias_map") or {}
        for sector_name, bias in sbm.items():
            etf = SECTOR_ETF_MAP.get(sector_name, "")
            if etf:
                bias_map[etf] = str(bias).upper()

        # Also try extras.macro_enrichment_delta.macro_json_merge_block.sector_rotation_map
        extras = macro.get("extras") or {}
        delta  = extras.get("macro_enrichment_delta") or {}
        merge  = delta.get("macro_json_merge_block") or {}
        rot    = merge.get("sector_rotation_map") or {}
        favoured   = rot.get("favoured") or []
        vulnerable = rot.get("vulnerable") or []
        for label in favoured:
            sector = normalise_sector(label)
            etf = SECTOR_ETF_MAP.get(sector, "")
            if etf and bias_map.get(etf) == "NEUTRAL":
                bias_map[etf] = "CALL_TAILWIND"
        for label in vulnerable:
            sector = normalise_sector(label)
            etf = SECTOR_ETF_MAP.get(sector, "")
            if etf and bias_map.get(etf) == "NEUTRAL":
                bias_map[etf] = "PUT_HEADWIND"

        print(f"  [SECTOR_MASTER] Macro bias loaded from {macro_path.name}")
        print(f"    TAILWIND ETFs: {[k for k,v in bias_map.items() if v=='CALL_TAILWIND']}")
        print(f"    HEADWIND ETFs: {[k for k,v in bias_map.items() if v=='PUT_HEADWIND']}")
    except Exception as e:
        print(f"  [WARN] Could not read macro bias from JSON: {e} — using neutral defaults")
    return bias_map


def build_sector_lookup(repo: Path) -> Dict[str, str]:
    """
    Build ticker -> gics_sector lookup from all available sources.
    Priority: hardcoded > master CSV > hybrid CSV > Excel files > ETF membership.
    Returns dict of ticker -> gics_sector (normalised).
    """
    lookup: Dict[str, str] = {}

    # Priority 1 — hardcoded overrides
    for ticker, sector in HARDCODED_SECTOR_OVERRIDES.items():
        lookup[ticker.upper()] = sector
    print(f"  [P1] Hardcoded overrides: {len(HARDCODED_SECTOR_OVERRIDES)} tickers")

    # Priority 2 — master_ticker_list2026_WITH_SECTORS.csv
    for candidate in [
        repo / "master_ticker_list2026_WITH_SECTORS.csv",
        repo / "data" / "master_ticker_list2026_WITH_SECTORS.csv",
        repo / "data" / "universe" / "master_ticker_list2026_WITH_SECTORS.csv",
    ]:
        if candidate.exists():
            try:
                df = pd.read_csv(candidate, low_memory=False)
                t_col = next((c for c in df.columns if c.lower() in ("ticker","symbol")), None)
                s_col = next((c for c in df.columns if c.lower() == "sector"), None)
                if t_col and s_col:
                    for _, row in df.iterrows():
                        t = str(row[t_col]).strip().upper()
                        s = normalise_sector(str(row[s_col]))
                        if t and s and t not in lookup:
                            lookup[t] = s
                    print(f"  [P2] master CSV: {len(df)} rows | path: {candidate.name}")
                    break
            except Exception as e:
                print(f"  [WARN] master CSV read failed: {e}")

    # Priority 3 — hybrid_universe_enhanced__with_sector.csv
    for candidate in [
        repo / "data" / "universe" / "Archive" / "hybrid_universe_enhanced__with_sector.csv",
        repo / "data" / "universe" / "hybrid_universe_enhanced__with_sector.csv",
    ]:
        if candidate.exists():
            try:
                df = pd.read_csv(candidate, low_memory=False)
                t_col = next((c for c in df.columns if c.lower() in ("ticker","symbol")), None)
                s_col = next((c for c in df.columns if c.lower() in ("sector","gics_sector")), None)
                if t_col and s_col:
                    added = 0
                    for _, row in df.iterrows():
                        t = str(row[t_col]).strip().upper()
                        s = normalise_sector(str(row[s_col]))
                        if t and s and t not in lookup:
                            lookup[t] = s
                            added += 1
                    print(f"  [P3] hybrid CSV: {len(df)} rows | added {added} new tickers")
                    break
            except Exception as e:
                print(f"  [WARN] hybrid CSV read failed: {e}")

    # Priority 4 — Excel sector mapping files
    for fname in [
        "Sector_Mapping_2211.xlsx",
        "Sector_Mapping_2_2211.xlsx",
        "sector_mapping_3_2211.xlsx",
        "Sector_Mapping_4_2211.xlsx",
    ]:
        for base in [repo, repo / "data", repo / "data" / "universe"]:
            fp = base / fname
            if fp.exists():
                try:
                    df = pd.read_excel(fp)
                    t_col = next((c for c in df.columns if "ticker" in c.lower()), None)
                    s_col = next((c for c in df.columns if "sector" in c.lower()), None)
                    if t_col and s_col:
                        added = 0
                        for _, row in df.iterrows():
                            t = str(row[t_col]).strip().upper()
                            s = normalise_sector(str(row[s_col]))
                            if t and s and t not in lookup:
                                lookup[t] = s
                                added += 1
                        print(f"  [P4] {fname}: added {added} new tickers")
                except Exception as e:
                    print(f"  [WARN] {fname} read failed: {e}")
                break

    # Priority 5 — ETF master ticker files
    etf_files = {
        "XLK": ["XLK_MASTER_TICKERS.csv"],
        "XLE": ["XLE_MASTER_TICKERS.csv"],
        "XLF": ["XLF_MASTER_TICKERS.csv"],
        "XLI": ["XLI_MASTER_TICKERS.csv"],
        "XLV": ["XLV_MASTER_TICKERS.csv"],
        "XLY": ["XLY_MASTER_TICKERS.csv"],
        "XLP": ["XLP_MASTER_TICKERS.csv"],
        "XLB": ["XLB_MASTER_TICKERS.csv"],
        "XLU": ["XLU_MASTER_TICKERS.csv"],
    }
    for etf, fnames in etf_files.items():
        sector = ETF_TO_SECTOR.get(etf, "")
        if not sector:
            continue
        for fname in fnames:
            for base in [repo, repo / "data", repo / "data" / "universe"]:
                fp = base / fname
                if fp.exists():
                    try:
                        df = pd.read_csv(fp, low_memory=False)
                        t_col = next((c for c in df.columns if c.lower() in ("ticker","symbol")), None)
                        if t_col:
                            added = 0
                            for t in df[t_col].dropna():
                                t = str(t).strip().upper()
                                if t and t not in lookup:
                                    lookup[t] = sector
                                    added += 1
                            if added:
                                print(f"  [P5] {fname} ({etf}): added {added} new tickers")
                    except Exception as e:
                        print(f"  [WARN] {fname} read failed: {e}")
                    break

    print(f"  [SECTOR_MASTER] Total resolved: {len(lookup)} tickers")
    return lookup


def validate_distribution(df: pd.DataFrame) -> bool:
    """
    Guard against bulk assignment errors.
    If any single sector contains more than MAX_SECTOR_PCT of the universe,
    raise a warning and return False.
    """
    sector_counts = df[df["gics_sector"] != "UNKNOWN"]["gics_sector"].value_counts()
    total_known = len(df[df["gics_sector"] != "UNKNOWN"])
    if total_known == 0:
        print("  [WARN] VALIDATION: zero tickers resolved — sector master may be empty")
        return False
    for sector, count in sector_counts.items():
        pct = count / total_known
        if pct > MAX_SECTOR_PCT:
            print(f"  [ERROR] VALIDATION FAILED: {sector} = {count} tickers ({pct:.1%} of known)")
            print(f"          Threshold: {MAX_SECTOR_PCT:.0%}. Possible bulk assignment error.")
            return False
    print(f"  [SECTOR_MASTER] Distribution validation PASS")
    return True


def build_sector_master(
    macro_path: Path,
    run_id: str,
    output_dir: Path,
    universe_csv: Optional[Path] = None,
) -> Path:
    """
    Main function. Builds the sector master CSV.
    Returns path to the written file.
    """
    print(f"\n[SECTOR_MASTER] Building sector master — run_id={run_id}")

    # Load macro bias
    macro_bias_map = load_macro_bias_from_json(macro_path)

    # Build sector lookup from all sources
    sector_lookup = build_sector_lookup(REPO)

    # Determine universe — use provided CSV or polygon_liquid_universe.csv
    if universe_csv is None:
        for candidate in [
            REPO / "polygon_liquid_universe.csv",
            REPO / "data" / "universe" / "polygon_liquid_universe.csv",
            REPO / "data" / "polygon_liquid_universe.csv",
        ]:
            if candidate.exists():
                universe_csv = candidate
                break

    if universe_csv is None or not universe_csv.exists():
        print("  [WARN] No universe CSV found — using tickers from sector lookup only")
        tickers = list(sector_lookup.keys())
    else:
        df_univ = pd.read_csv(universe_csv, low_memory=False)
        t_col = next((c for c in df_univ.columns if c.lower() in ("ticker","symbol")), None)
        if t_col:
            tickers = [str(t).strip().upper() for t in df_univ[t_col].dropna() if str(t).strip()]
        else:
            tickers = list(sector_lookup.keys())
        print(f"  [SECTOR_MASTER] Universe: {len(tickers)} tickers from {universe_csv.name}")

    # Build output rows
    rows = []
    unknown_count = 0
    for ticker in tickers:
        t = ticker.upper().strip()
        gics_sector = sector_lookup.get(t, "UNKNOWN")
        if gics_sector == "UNKNOWN":
            unknown_count += 1
        gics_sector_norm = normalise_sector(gics_sector) or gics_sector
        sector_etf  = SECTOR_ETF_MAP.get(gics_sector_norm, "UNKNOWN")
        macro_bias  = macro_bias_map.get(sector_etf, "NEUTRAL") if sector_etf != "UNKNOWN" else "UNKNOWN"
        macro_abstain = t in MACRO_ABSTAIN_TICKERS
        rows.append({
            "ticker":        t,
            "gics_sector":   gics_sector_norm,
            "sector_etf":    sector_etf,
            "macro_bias":    macro_bias,
            "macro_abstain": macro_abstain,
        })

    df_out = pd.DataFrame(rows, columns=OUTPUT_COLS)

    # Validate distribution
    valid = validate_distribution(df_out)
    if not valid:
        print("  [WARN] Distribution validation failed — sector master written with warning flag")

    # Write run-specific and latest
    output_dir.mkdir(parents=True, exist_ok=True)
    run_path    = output_dir / f"sector_master_{run_id}.csv"
    latest_path = output_dir / "sector_master_latest.csv"

    df_out.to_csv(run_path,    index=False)
    df_out.to_csv(latest_path, index=False)

    resolved = len(df_out[df_out["gics_sector"] != "UNKNOWN"])
    unknown  = len(df_out[df_out["gics_sector"] == "UNKNOWN"])
    tailwind = len(df_out[df_out["macro_bias"] == "CALL_TAILWIND"])
    headwind = len(df_out[df_out["macro_bias"] == "PUT_HEADWIND"])
    abstain  = len(df_out[df_out["macro_abstain"] == True])

    print(f"\n[SECTOR_MASTER] Complete")
    print(f"  Total tickers : {len(df_out)}")
    print(f"  Resolved      : {resolved} ({resolved/len(df_out)*100:.1f}%)")
    print(f"  UNKNOWN       : {unknown}  ({unknown/len(df_out)*100:.1f}%)")
    print(f"  CALL_TAILWIND : {tailwind}")
    print(f"  PUT_HEADWIND  : {headwind}")
    print(f"  MACRO_ABSTAIN : {abstain} ({list(MACRO_ABSTAIN_TICKERS)})")
    print(f"  Written to    : {run_path.name}")
    print(f"  Latest copy   : {latest_path.name}\n")

    return latest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="AVSHUNTER Sector Master Builder")
    parser.add_argument("--macro-path",   required=True, help="Path to macro_intelligence_latest.json")
    parser.add_argument("--run-id",       required=True, help="Pipeline run ID e.g. 20260516_120000")
    parser.add_argument("--output-dir",   default="data", help="Output directory for sector_master CSV")
    parser.add_argument("--universe-csv", default="",    help="Optional path to universe CSV")
    args = parser.parse_args()

    macro_path   = Path(args.macro_path)
    output_dir   = Path(args.output_dir)
    universe_csv = Path(args.universe_csv) if args.universe_csv else None

    if not macro_path.exists():
        print(f"[ERROR] Macro path not found: {macro_path}")
        return 1

    build_sector_master(
        macro_path=macro_path,
        run_id=args.run_id,
        output_dir=output_dir,
        universe_csv=universe_csv,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**After creating confirm:**
- `scripts/build_sector_master.py` exists
- Syntax valid: `python -m py_compile scripts/build_sector_master.py`
- No other files modified

---

## STEP 2 — WIRE sector master into intelligent_orchestrator.py

**File:** `intelligent_orchestrator.py`
**Risk:** LOW — additive call only. NON-CRITICAL flag means pipeline
          continues if script fails.
**Show diff before saving**

**What to add:**

Find the section in `evening_workflow()` that calls
`merge_macro_enrichment_into_macro_latest()` at approximately line 3252.
The sector master must run AFTER the macro merge (so it has the enriched
macro JSON to read macro bias from) and BEFORE discovery runs
(so tickers enter discovery with sector context).

Add a new function call immediately after the macro enrichment merge:

```python
# ── PHASE 4.7: Sector Master Build ───────────────────────────────────────────
# Resolves all universe tickers to gics_sector, sector_etf, macro_bias,
# macro_abstain. NON-CRITICAL: pipeline continues if this fails.
# Writes: data/sector_master_{run_id}.csv + data/sector_master_latest.csv
_sector_master_script = cfg.SCRIPTS_DIR / "build_sector_master.py"
if _sector_master_script.exists():
    try:
        _sm_result = subprocess.run(
            [
                sys.executable,
                str(_sector_master_script),
                "--macro-path", str(macro_path),
                "--run-id",     canonical_run_id,
                "--output-dir", str(cfg.BASE_DIR / "data"),
            ],
            capture_output=True, text=True, timeout=120
        )
        if _sm_result.returncode == 0:
            logger.info("✅ Phase 4.7 (Sector Master) — complete")
            if _sm_result.stdout:
                for _line in _sm_result.stdout.strip().splitlines():
                    logger.info("   | %s", _line)
        else:
            logger.warning("⚠️  Phase 4.7 (Sector Master) failed — pipeline continues with UNKNOWN sector")
            logger.warning("   | %s", _sm_result.stderr[:500] if _sm_result.stderr else "no stderr")
    except Exception as _sm_err:
        logger.warning("⚠️  Phase 4.7 (Sector Master) error: %s — continuing", _sm_err)
else:
    logger.info("Phase 4.7 (Sector Master) — script not deployed, skipping")
```

**Adapt the call to match how other subprocess calls are made in the
orchestrator. Use the same pattern as other Phase calls above it —
do not invent a new pattern if one exists.**

**Show diff before saving. After saving confirm:**
- Only `intelligent_orchestrator.py` was modified
- The call is in the correct position (after macro merge, before discovery)
- Syntax valid

---

## STEP 3 — WIRE sector master into apply_macro_enrichment_to_discovery.py

**File:** `scripts/apply_macro_enrichment_to_discovery.py`
**Risk:** SAFE — additive read only. If sector master file is missing,
          script falls back to existing bias map extraction from macro JSON.
**Show diff before saving**

**What to add:**

The existing `_extract_bias_maps()` reads from the macro JSON.
Add a higher-priority path: if `data/sector_master_latest.csv` exists,
read `macro_bias` and `macro_abstain` from it instead.

Find the `enrich_discovery_csv()` function.
Before the existing Phase B bias stamping block, add:

```python
# ── Phase B0: Load sector master if available (higher priority than JSON) ──
_sector_master_path = Path(__file__).resolve().parents[1] / "data" / "sector_master_latest.csv"
_sector_master: Dict[str, dict] = {}
if _sector_master_path.exists():
    try:
        _sm_df = pd.read_csv(_sector_master_path, low_memory=False)
        for _, _sm_row in _sm_df.iterrows():
            _t = str(_sm_row.get("ticker", "")).strip().upper()
            if _t:
                _sector_master[_t] = {
                    "gics_sector":   str(_sm_row.get("gics_sector",  "UNKNOWN")),
                    "sector_etf":    str(_sm_row.get("sector_etf",   "UNKNOWN")),
                    "macro_bias":    str(_sm_row.get("macro_bias",   "NEUTRAL")).upper(),
                    "macro_abstain": str(_sm_row.get("macro_abstain","False")).upper() == "TRUE",
                }
        print(f"  [ENRICHMENT] Sector master loaded: {len(_sector_master)} tickers")
    except Exception as _sm_err:
        print(f"  [WARN] Sector master read failed: {_sm_err} — falling back to JSON bias map")
        _sector_master = {}
```

Then modify `_resolve_macro_bias()` to check the sector master first:

```python
def _resolve_macro_bias(
    ticker: str,
    call_tickers: set,
    put_tickers: set,
    context_tickers: set,
    sector_master: dict = None,
) -> tuple:
    t = str(ticker).strip().upper()

    # Priority 1: sector master (from build_sector_master.py)
    if sector_master and t in sector_master:
        sm = sector_master[t]
        bias    = sm.get("macro_bias", "NEUTRAL")
        abstain = sm.get("macro_abstain", False)
        source  = "SECTOR_MASTER"
        return bias, "true" if abstain else "false", source

    # Priority 2: hardcoded exception (VST/NEE/CEG)
    if t in MACRO_ABSTAIN_TICKERS:
        return "NEUTRAL", "true", "POWER_GEN_EXCEPTION"

    # Priority 3: enrichment JSON bias map
    if t in call_tickers:
        return "CALL_TAILWIND", "false", "ENRICHMENT_DELTA"
    if t in put_tickers:
        return "PUT_HEADWIND", "false", "ENRICHMENT_DELTA"
    if t in context_tickers:
        return "CONTEXT_ONLY", "false", "ENRICHMENT_DELTA"

    return "NEUTRAL", "false", "NO_ENRICHMENT_MATCH"
```

Pass `_sector_master` into each `_resolve_macro_bias()` call in Phase B.

**Show diff before saving. After saving confirm:**
- Only `apply_macro_enrichment_to_discovery.py` was modified
- Sector master path is correct relative to scripts/ directory
- Syntax valid

---

## STEP 4 — TEST the sector master standalone

**Before wiring into a full run, test the script standalone:**

```powershell
cd C:\Users\ACKVerissimo\AVSHUNTER-Intelligence

python scripts\build_sector_master.py `
  --macro-path dropbox\macro\macro_intelligence_latest.json `
  --run-id TEST_20260516 `
  --output-dir data
```

**Report:**
- Exit code (must be 0)
- Total tickers resolved
- UNKNOWN percentage (target: below 30% on first run, below 5% after mapping files confirmed)
- CALL_TAILWIND count
- PUT_HEADWIND count
- MACRO_ABSTAIN tickers listed
- Distribution validation result (PASS or FAIL)
- Confirm `data/sector_master_latest.csv` exists and has correct columns

**If UNKNOWN > 60%:**
Report which mapping files were found and which were missing.
This tells us which Priority sources need to be located and added.

**If distribution validation FAILS:**
Report which sector triggered the > 35% threshold and why.
Do not deploy to orchestrator until validation passes.

---

## COMPLETION REPORT

After all steps produce a summary:

```
SECTOR MASTER SPRINT COMPLETION
=================================
Step 0  — AUDIT:                    [COMPLETE]
Step 1  — build_sector_master.py:   [COMPLETE / FAILED]
Step 2  — orchestrator wiring:      [COMPLETE / FAILED]
Step 3  — enrichment script update: [COMPLETE / FAILED]
Step 4  — standalone test:          [COMPLETE / FAILED]

Sector master results (from Step 4):
  Total tickers:    ___
  Resolved:         ___ (___%)
  UNKNOWN:          ___ (___%)
  CALL_TAILWIND:    ___
  PUT_HEADWIND:     ___
  MACRO_ABSTAIN:    ___
  Validation:       PASS / FAIL

Files created:
  scripts/build_sector_master.py
  data/sector_master_latest.csv

Files modified:
  intelligent_orchestrator.py (Phase 4.7 call added)
  scripts/apply_macro_enrichment_to_discovery.py (sector master priority added)

Files NOT modified (confirm unchanged):
  execution_intelligence.py
  macro_horizon_router.py
  final_decision_engine.py
  execution_intelligence_runner.py

Next action:
  Run full evening pipeline:
  python intelligent_orchestrator.py --evening
  Confirm log shows:
    "✅ Phase 4.7 (Sector Master) — complete"
    "Macro enrichment discovery stamp complete"
  Check discovery CSV has gics_sector, sector_etf, macro_bias, macro_abstain columns
  Check EIL log shows ENRICHMENT_MOD lines for CALL_TAILWIND/PUT_HEADWIND tickers
```
