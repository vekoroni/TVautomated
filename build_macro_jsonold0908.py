#!/usr/bin/env python3
"""
AVSHUNTER — Automated Macro JSON Builder
=========================================
Replaces the 3-prompt manual GPT copy-paste workflow.

Reads Colab output CSVs from dropbox/market_data/ and calls the
Anthropic API with the exact 3-prompt sequence from the April sessions.
Writes macro_intelligence_latest.json directly to dropbox/macro/.

USAGE
-----
  # Run after moving Colab CSVs to dropbox/market_data/
  python build_macro_json.py

  # Force rebuild even if JSON is fresh
  python build_macro_json.py --force

  # Dry run — shows what would be sent, does not call API
  python build_macro_json.py --dry-run

WHAT IT DOES
------------
1. Scans dropbox/market_data/ for the latest Colab CSVs
2. Builds a structured data payload from those files
3. Calls Claude claude-sonnet-4-6 with the 3-prompt sequence:
   - Message 1: system identity + data contract rules
   - Message 2: full analysis pass (Blocks 0-8)
   - Message 3: MACRO COMPLETE → strict JSON finalisation
4. Validates the JSON against macro_contract_v1_0 required fields
5. Writes macro_intelligence_latest.json to dropbox/macro/
6. Copies to data/macro/ for immediate pipeline use

DEPLOY
------
  Copy to: C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\
  Run from: AVSHUNTER-Intelligence venv
"""

import os
import sys
import json
import glob
import csv
import argparse
import shutil
import logging
from pathlib import Path
from datetime import datetime, timezone

import anthropic

# ============================================================
# CONFIG
# ============================================================
BASE_DIR    = Path(__file__).resolve().parent
DROPBOX_DIR = BASE_DIR / "dropbox"
MARKET_DIR  = DROPBOX_DIR / "market_data"
MACRO_DIR   = DROPBOX_DIR / "macro"
PIPELINE_MACRO_DIR = BASE_DIR / "data" / "macro"

OUTPUT_FILENAME = "macro_intelligence_latest.json"
MODEL           = "claude-sonnet-4-6"

MSG1_TOKENS = 2000
MSG2_TOKENS = 4000
MSG3_TOKENS = 8000

FRESH_HOURS = 6  # skip rebuild if JSON is less than N hours old

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("MACRO-BUILDER")

# ============================================================
# REQUIRED FIELDS — macro_contract_v1_0
# ============================================================
REQUIRED_FIELDS = [
    # Top-level required fields
    "contract_version",
    "regime_state",
    "dir_bias",
    "vol_mode",
    "risk_on_off_switch",
    "liquidity_pulse",
    "regime_drift_status",
    "macro_conviction",
    "as_of_utc",
    "report_date",
    "net_liquidity_score",
    "vix_regime_score",
    "macro_momentum_score",
    "regime_label",
    "vix_spot",
    "size_multiplier",
    "horizon_routing",
    # extras fields — pipeline _flatten_macro walks all nested dicts
    "conviction_score",    # extras.conviction_score — same as macro_conviction
    "vix_contango",        # extras.vix_contango — VIX3M minus VIX9D
    "volatility_mode",     # extras.volatility_mode — alias for vol_mode
    "liquidity_status",    # extras.liquidity_status — alias for liquidity_pulse
    "predictability_score",# extras.predictability_score
    # removed: "execution_bias"  — dead field, no pipeline consumer
    # removed: "risk_on_switch"  — duplicate of top-level risk_on_off_switch
    # removed: "sector_tilt" (top-level string) — redundant with sector_rotation.sector_bias_map
    # ── SECTOR ROTATION (v1.1 contract extension) ─────────────────────────
    # sector_rotation block — required for per-ticker sector alignment
    # pipeline reads sector_rotation.sector_bias_map keyed by GICS sector
]

# Required keys within the sector_rotation block
SECTOR_ROTATION_REQUIRED_KEYS = [
    "strongest_sectors",
    "weakest_sectors",
    "sector_bias_map",
    "rotation_signal",
]

PIPELINE_ALIASES = {
    "risk_on_off_switch": "risk_on_switch",
    "vol_mode":           "volatility_mode",
    "liquidity_pulse":    "liquidity_status",
}

# ============================================================
# DATA LOADER
# ============================================================

FILE_SPECS = [
    ("report_json",        "report_*.json",                      True),
    ("macro_csv",          "macro_*.csv",                        True),
    ("forward_bias_csv",   "forward_bias_*.csv",                 True),
    ("liquidity_csv",      "avshunter_liquidity_monitor.csv",    False),
    ("fung_hsieh_csv",     "avshunter_macro_filter_summary.csv", False),
    ("regime_model_csv",   "avshunter_daily_macro_regime.csv",   False),
    ("vix_engine_csv",     "avshunter_vix_engine*.csv",          False),
    ("macro_master_csv",   "avsh_macro_master.csv",              False),
    ("fred_master_csv",    "avshunter_fred_master.csv",          False),
    ("gex_proxy_csv",      "avshunter_gex_proxy.csv",            False),
    ("gex_by_strike_csv",  "avshunter_gex_by_strike.csv",        False),
    ("threshold_flags_csv","macro_series_threshold_flags.csv",   False),
    ("regime_json",        "avshunter_regime.json",              False),
    ("us_indices_csv",     "us_indices_cash_*.csv",              False),
    ("global_indices_csv", "global_indices_*.csv",               False),
    ("sectors_csv",        "sectors_*.csv",                      False),
    ("vol_dollar_csv",     "vol_dollar_*.csv",                   False),
    ("fx_csv",             "fx_spot_*.csv",                      False),
    ("bonds_csv",          "bonds_etf_*.csv",                    False),
    ("metals_csv",         "metals_etf_*.csv",                   False),
    ("energy_csv",         "energy_etf_*.csv",                   False),
    ("equity_csv",         "equity_etf_*.csv",                   False),
    ("agriculture_csv",    "agriculture_etf_*.csv",              False),
]

FILE_SPEC_KEYS = [key for key, _, _ in FILE_SPECS]


def find_latest_file(directory: Path, pattern: str):
    matches = sorted(
        directory.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    return matches[0] if matches else None


def _load_existing_macro(output_path: Path) -> dict:
    if not output_path.exists():
        return {}
    try:
        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning("Existing macro JSON could not be read for update mode: %s", e)
        return {}


def _load_input_file(path: Path):
    if path.suffix == ".json":
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    with open(path, encoding="utf-8") as f:
        return f.read()


def check_date_consistency(payload: dict) -> None:
    dates = {}
    for key, text in payload.get("data", {}).items():
        if not isinstance(text, str):
            continue
        try:
            rows = list(csv.DictReader(text.splitlines()))
        except Exception:
            continue
        if rows and "Date" in rows[-1] and rows[-1].get("Date"):
            dates[key] = rows[-1]["Date"]

    if len(set(dates.values())) > 1:
        sorted_dates = sorted(set(dates.values()), reverse=True)
        newest = sorted_dates[0]
        oldest = sorted_dates[-1]
        log.warning("DATE MISMATCH across input files:")
        for key, date in sorted(dates.items(), key=lambda x: x[1], reverse=True):
            marker = "<- NEWEST" if date == newest else ("<- OLDEST" if date == oldest else "")
            log.warning("  %-30s %s %s", key, date, marker)
        log.warning("Proceeding with newest date. Verify stale files are intentional.")
    else:
        log.info(
            "Date consistency: all files agree on %s",
            next(iter(dates.values())) if dates else "unknown",
        )


def load_data_payload(market_dir: Path, update_keys=None, prior_macro: dict | None = None) -> dict:
    update_key_set = set(update_keys or [])
    partial_mode = bool(update_key_set)
    prior_macro = prior_macro or {}
    payload = {
        "loaded_at":    datetime.now(timezone.utc).isoformat(),
        "files_found":  [],
        "files_missing":[],
        "files_found_by_key": {},
        "update_mode":  "PARTIAL" if partial_mode else "FULL",
        "update_keys":  sorted(update_key_set),
        "data":         {}
    }

    if partial_mode:
        if not prior_macro:
            raise RuntimeError("--update requires an existing macro_intelligence_latest.json prior")
        payload["data"]["prior_macro_json"] = prior_macro
        log.info("Partial update mode: prior macro JSON loaded; disk refresh keys=%s", ",".join(sorted(update_key_set)))

    for key, pattern, required in FILE_SPECS:
        if partial_mode and key not in update_key_set:
            payload["files_missing"].append(f"{key}:using_prior_macro_json")
            continue
        path = find_latest_file(market_dir, pattern)
        if path:
            try:
                payload["data"][key] = _load_input_file(path)
                payload["files_found"].append(path.name)
                payload["files_found_by_key"][key] = str(path)
                log.info("  Loaded: %s", path.name)
            except Exception as e:
                log.warning("  Failed to load %s: %s", path.name, e)
                if required and not partial_mode:
                    raise RuntimeError(f"Required file {pattern} failed: {e}")
        else:
            if required and not partial_mode:
                raise RuntimeError(
                    f"Required file not found: {pattern}\n"
                    f"  Ensure Colab v5.3 has run and CSVs are in: {market_dir}"
                )
            payload["files_missing"].append(pattern)

    check_date_consistency(payload)
    log.info("Payload: %d files loaded, %d optional missing",
             len(payload["files_found"]), len(payload["files_missing"]))
    return payload


def format_data_for_prompt(payload: dict) -> str:
    parts = []
    data  = payload["data"]

    if "prior_macro_json" in data:
        parts.append("=== PRIOR MACRO JSON (baseline for partial update) ===")
        parts.append(json.dumps(data["prior_macro_json"], indent=2)[:6000])
        parts.append(
            "PARTIAL UPDATE INSTRUCTION: Preserve prior macro fields unless the newly loaded update files "
            "provide fresher contradictory evidence. Recompute affected fields and keep contract completeness."
        )

    if "report_json" in data:
        report = data["report_json"]
        parts.append("=== MARKET INTELLIGENCE REPORT (v5.3) ===")
        for field in ["timestamp","risk_assessment","macro_regime","inflation",
                      "momentum","liquidity","yield_curve","vix_term_structure",
                      "risk_signals"]:
            if field in report:
                parts.append(f"[{field.upper()}]")
                parts.append(json.dumps(report[field], indent=2)[:2000])
        if "forward_bias" in report:
            parts.append("[FORWARD_BIAS]")
            parts.append(json.dumps(report["forward_bias"], indent=2))
        if "fred_indicators" in report:
            parts.append("[FRED_INDICATORS — key series]")
            key_fred = {k: v for k, v in report["fred_indicators"].items()
                        if k in ("UNRATE","CPIAUCSL","FEDFUNDS","DGS10","DGS2",
                                 "T10Y2Y","WALCL","SOFR","BAMLH0A0HYM2",
                                 "USSLIND","UMCSENT","ICSA","M2SL","INDPRO")}
            parts.append(json.dumps(key_fred, indent=2))

    if "macro_csv" in data:
        parts.append("\n=== MACRO CSV (FRED indicators) ===")
        lines = data["macro_csv"].split("\n")
        parts.append("\n".join(lines[:50]))

    if "forward_bias_csv" in data:
        parts.append("\n=== FORWARD BIAS CSV ===")
        parts.append(data["forward_bias_csv"][:1000])

    if "liquidity_csv" in data:
        parts.append("\n=== LIQUIDITY MONITOR (Repo + WALCL) ===")
        parts.append(data["liquidity_csv"][:1500])

    if "vix_engine_csv" in data:
        parts.append("\n=== VIX ENGINE V2 (VIX9D / VIX3M / VVIX PRIMARY) ===")
        parts.append(data["vix_engine_csv"][:1500])

    if "macro_master_csv" in data:
        parts.append("\n=== MACRO MASTER (RATES / CREDIT / LEI / XLC PRIMARY) ===")
        parts.append(data["macro_master_csv"][:1500])

    if "fred_master_csv" in data:
        parts.append("\n=== FRED MASTER WIDE TABLE (RAW MACRO SERIES) ===")
        lines = data["fred_master_csv"].split("\n")
        parts.append("\n".join(lines[-8:])[:2500])

    if "gex_proxy_csv" in data:
        parts.append("\n=== DEALER GAMMA PROXY (GEX PRIMARY) ===")
        parts.append(data["gex_proxy_csv"][:1500])

    if "gex_by_strike_csv" in data:
        parts.append("\n=== GEX BY STRIKE (KEY LEVELS) ===")
        parts.append(data["gex_by_strike_csv"][:1500])

    if "threshold_flags_csv" in data:
        parts.append("\n=== MACRO SERIES THRESHOLD FLAGS ===")
        parts.append(data["threshold_flags_csv"][:1500])

    if "regime_json" in data:
        parts.append("\n=== AVSHUNTER REGIME JSON ===")
        parts.append(json.dumps(data["regime_json"], indent=2)[:1500])

    if "fung_hsieh_csv" in data:
        parts.append("\n=== FUNG-HSIEH FACTOR DASHBOARD (size modifier only) ===")
        parts.append(data["fung_hsieh_csv"][:500])

    if "sectors_csv" in data:
        parts.append("\n=== SECTOR ETF PERFORMANCE ===")
        parts.append(data["sectors_csv"][:1000])

    if "vol_dollar_csv" in data:
        parts.append("\n=== VIX / VOLATILITY / DOLLAR ===")
        parts.append(data["vol_dollar_csv"][:500])

    return "\n".join(parts)


# ============================================================
# PROMPTS — exact 3-prompt sequence from April 2026 sessions
# ============================================================

PROMPT_1_SYSTEM = """AVSHUNTER MACRO MODULE — SESSION INITIALISATION
Version: macro_contract_v1_0 | Mode: Ultra-Conservative, Verified-Data

You are AVSHUNTER MACRO MODULE v2.7 operating as a structured data extraction engine. Your sole purpose in this session is to read the attached data and produce a macro analysis that terminates in a strict JSON object matching the schema provided.

OPERATING RULES — READ BEFORE ANYTHING ELSE:
1. Work ONLY from data provided in this session. Do NOT assume, hallucinate, or infer external values.
2. Every derived metric must be labelled: CONFIRMED (from data), ASSUMPTION (inferred from related data), or MISSING (not present — do not fabricate).
3. Each label carries a confidence score 0–100.
4. If regime or directional bias is genuinely unclear, output WAIT / REDUCED_SIZE rather than forcing a narrative.
5. When CSV data and JSON report conflict, CSV is primary. Call out every conflict explicitly.
6. Focus exclusively on US macro and US-listed equities/options.
7. Use precise British English throughout.

DATA SOURCES IN THIS SESSION:
- PRIMARY: Colab-exported report JSON (Market Intelligence v5.3) and CSV files — treat as ground truth for all numeric series.
- All FRED indicators, VIX term structure, sector ETFs, forward bias, and liquidity data are from these sources.

Acknowledge receipt of these rules and confirm you are ready for the data pass."""


def build_prompt_2(data_str: str) -> str:
    return f"""DATA PASS — Full macro analysis

The following data has been extracted from today's Colab run:

{data_str}

---

Perform the full macro analysis across these blocks:

BLOCK 0 — DATA INTEGRITY AUDIT
List every CONFIRMED, ASSUMPTION, and MISSING field. Flag any conflicts between sources.

BLOCK 1 — VOLATILITY REGIME
VIX spot, VIX9D, VIX3M, VVIX. Term structure shape (CONTANGO/BACKWARDATION/FLAT).
vol_mode: COMPRESSED_CONTANGO_LOW_VOL | SHALLOW_CONTANGO | ELEVATED_CAUTION | HIGH_STRESS | FEAR_MODE

BLOCK 2 — REGIME STATE
Overall: RISK_ON | RISK_OFF | TRANSITIONAL | NEUTRAL | CRISIS
Sub-classify TRANSITIONAL as: TRANSITIONAL_BULLISH | TRANSITIONAL_BEARISH | TRANSITIONAL_NEUTRAL
Growth, inflation, policy assessment.

BLOCK 3 — DIRECTIONAL BIAS
dir_bias for 1-5D and 6-10D horizons from forward_bias data.
BULLISH | MILDLY_BULLISH | NEUTRAL | MILDLY_BEARISH | BEARISH

BLOCK 4 — LIQUIDITY CONDITIONS
WALCL regime, RRP level, SOFR-FF spread, TGA direction.
liquidity_pulse: EXPANDING | STABLE | CONTRACTING | STRESS | FLAT

BLOCK 5 — RATES AND CREDIT
2Y/10Y spread, yield curve signal, credit spreads (HY OAS, IG OAS).
rates_impulse: EASY | NEUTRAL | RESTRICTIVE_HOLD | TIGHTENING

BLOCK 6 — SECTOR TILT AND ROTATION
Best and worst performing sectors by 30d change. Which sectors have macro permission.
sector_tilt field value.

Additionally, produce a structured sector_rotation block with EXACTLY these fields:
- strongest_sectors: array of GICS sector names receiving macro tailwind (e.g. ["Energy", "Materials"])
- weakest_sectors: array of GICS sector names facing macro headwind (e.g. ["Information Technology"])
- sector_bias_map: object keyed by GICS sector name (full name, not ETF ticker) with values:
  TAILWIND | NEUTRAL | HEADWIND | MIXED
  Cover ALL 11 GICS sectors: Information Technology, Health Care, Financials, Consumer Discretionary,
  Consumer Staples, Industrials, Energy, Materials, Real Estate, Communication Services, Utilities
- rotation_signal: enum string describing the rotation theme e.g.:
  RISK_OFF_GROWTH_TO_VALUE | RISK_ON_GROWTH_MOMENTUM | DEFENSIVE_ROTATION | COMMODITY_ROTATION |
  SECTOR_NEUTRAL | MIXED_SIGNALS

BLOCK 7 — RISK SIGNALS AND CONVICTION
Gold, credit, treasury, VIX, dollar, copper, crude signals.
Fung-Hsieh factor dashboard accuracy (sets macro_filter: GO or NO_GO).
IMPORTANT: macro_filter=NO_GO is a SIZE MODIFIER only (effective_size = size_multiplier * 0.7x).
It is NOT a hard execution gate. Direction ABSTAINS. Individual ticker verdicts are NOT blocked.
macro_conviction score 0.0-1.0.

BLOCK 8 — POSITION SIZING AND HORIZON ROUTING
position_size_multiplier for 1-5D and 6-10D based on regime and conviction.
horizon_routing block with action, size_multiplier, bias per bucket.
Put permissions based on VIX threshold.

BLOCK 9 - PIPELINE DATA QUALITY AND SOURCE AUTHORITY
State which fields are CONFIRMED from CSV/JSON source data, which are ASSUMPTION, and which remain MISSING.
CSV source data is primary when it conflicts with report JSON. Specifically validate VIX9D, VIX3M, VVIX,
HY/IG credit spreads, GEX, LEI/USSLIND quarantine state, XLC sector ETF coverage, and yield-curve dates.
Resolved conflicts must be labelled RESOLVED with the CSV source named. Active gaps must be labelled ACTIVE.

After completing all 9 blocks, confirm MACRO ANALYSIS COMPLETE and await finalisation instruction."""


PROMPT_3 = """MACRO COMPLETE

Produce the final macro_intelligence_latest.json. Output ONLY the raw JSON object — no markdown fences, no preamble, no explanation. The JSON must:

1. Match macro_contract_v1_0 schema exactly
2. Include ALL of these required top-level fields — this is the exact
   schema the pipeline expects. Missing fields will cause pre-flight to fail:
   - contract_version: "macro_contract_v1_0"
   - regime_state
   - dir_bias
   - trend_energy
   - usd_state
   - rates_impulse
   - liquidity_pulse
   - regime_drift_status
   - macro_conviction (float 0.0-1.0)
   - vol_mode
   - risk_on_off_switch
   - notes (rationale string)
   - as_of_utc (ISO format)
   - report_date (YYYY-MM-DD)
   - source: "avshunter_macro_module_v2_7"
   - net_liquidity_score (float 0.0-1.0 — WALCL+RRP+TGA combined score)
   - vix_regime_score (float 0.0-1.0 — derived from VIX term structure)
   - gex_regime_score (float 0.0-1.0 — gamma exposure regime, default 0.5 if unavailable)
   - macro_momentum_score (float 0.0-1.0)
   - regime_label (string — same as regime_state)
   - regime_probability (float 0.0-1.0)
   - vix_spot (float)
   - macro_filter (string — from Fung-Hsieh: GO or NO_GO. When NO_GO: SIZE MODIFIER only — effective_size = size_multiplier * 0.7x. Direction ABSTAINS. NOT a hard execution gate. Individual ticker verdicts are NOT blocked.)
   - sector_lead (JSON array of strings e.g. ["XLK","QQQ","XLY"])
   - sector_avoid (JSON array of strings e.g. ["XLE","XLV"])
   - size_multiplier (float — overall position size multiplier e.g. 0.75)
   - trigger_required (boolean — true when conviction < 0.70)
   - horizon_routing (object — REQUIRED buckets: 1_5d, 6_10d, 11_20d. Each bucket must include bias, bullish_prob_pct, engine_mode, action, size_multiplier, block_conditions)
   - sector_rotation (object — REQUIRED for per-ticker sector alignment. Must contain:
       strongest_sectors: array e.g. ["Energy", "Materials"]
       weakest_sectors:   array e.g. ["Information Technology"]
       rotation_signal:   string e.g. "RISK_OFF_GROWTH_TO_VALUE"
       sector_bias_map:   object — FULL GICS sector names as keys, TAILWIND|NEUTRAL|HEADWIND|MIXED as values.
                          Must cover ALL 11 GICS sectors: Information Technology, Health Care,
                          Financials, Consumer Discretionary, Consumer Staples, Industrials,
                          Energy, Materials, Real Estate, Communication Services, Utilities)

3. Include an extras block containing ALL of these fields — the pipeline validator
   walks extras and will REJECT the JSON if any are missing:
   - generated_by: "AVSHUNTER_MACRO_MODULE_V2_7"
   - report_date (YYYY-MM-DD)
   - as_of_utc (ISO format)
   - conviction_score (float — MUST equal macro_conviction exactly e.g. 0.63)
   - liquidity_status (string — e.g. NEUTRAL_FLAT, EXPANDING, CONTRACTING)
   - volatility_mode (string — same as top-level vol_mode)
   - vix_contango (float — VIX3M minus VIX9D spread e.g. 0.128. Negative = backwardation)
   - vix_term_regime (string — SHALLOW_CONTANGO, CONTANGO, BACKWARDATION)
   - vix_spot (float)
   - vix_5d_avg (float)
   - vvix (float — vol of vol)
   - sector_bias (string — e.g. "XLK_LEAD_LONG_QQQ_LEAD_LONG_XLY_LONG_XLE_AVOID")
   - macro_notes (string — concise regime summary)
   - predictability_score (integer 0-100 — same as macro_conviction × 100)
   - forward_bias_layers (object with layer scores: tech, vix_term, cross_asset, vol_regime, mean_rev, trend, macro — each with score, direction, note)
   - conflict_flags (array of strings — data conflicts and warnings)
   - execution_rules (object — per horizon execution guidance)
   - rates (object with fed_funds, sofr, t10y, t2y, curve_2y10y, spread_signal)
   - volatility (object with regime, signal, vix_spot, vix9d, vix3m, spread)
   - liquidity (object with regime, signal, level, trend, walcl_change, rrp_level)
   - inflation (object with regime, cpi_mom, ppi_mom, pce_trend)
   - growth (object with regime, industrial_production_change_pct, jobless_claims_change_pct)
   - yield_curve (object with 2y10y value, state, recession_probability)
   - macro_regime (object with regime_state, growth, inflation, policy, confidence)
   - risk_assessment (object with market_risk, macro_risk, curve_risk, signal_risk, combined_score, recommendation)
   - risk_signals (object with gold_signal, credit_signal, treasury_signal, vix_signal, dollar_signal, copper_signal, crude_signal)
   - futures_bias (object — per-instrument directional bias for ES/SPY, NQ/QQQ, RTY/IWM)
   - put_gate (object with current_permission, unblock_conditions, recommended_structure)
   - horizon_routing (object with REQUIRED buckets 1_5d, 6_10d, 11_20d — each with bias, bullish_prob_pct, engine_mode, action, size_multiplier, block_conditions)

4. Use pipeline-compatible vocabulary:
   regime_state:       RISK_ON | RISK_OFF | TRANSITIONAL | TRANSITIONAL_BULLISH | TRANSITIONAL_BEARISH | NEUTRAL | CRISIS
   dir_bias:           BULLISH | MILDLY_BULLISH | NEUTRAL | MILDLY_BEARISH | BEARISH | SELECTIVE_BULLISH_*
   vol_mode:           COMPRESSED_CONTANGO_LOW_VOL | SHALLOW_CONTANGO | ELEVATED_CAUTION | HIGH_STRESS | FEAR_MODE
   risk_on_off_switch: RISK_ON | SELECTIVE_RISK_ON | SELECTIVE_RISK_ON_REDUCED_SIZE | RISK_OFF | RISK_OFF_NEAR_TERM
   liquidity_pulse:    EXPANDING | STABLE | CONTRACTING | STRESS | FLAT

Output the JSON now. Raw object only."""


# ============================================================
# API CALLER — 3-prompt sequence
# ============================================================

def call_macro_api(data_str: str, dry_run: bool = False) -> dict:
    if dry_run:
        log.info("[DRY RUN] 3-prompt sequence would be called")
        log.info("[DRY RUN] Prompt 1: %d chars", len(PROMPT_1_SYSTEM))
        log.info("[DRY RUN] Prompt 2: %d chars", len(build_prompt_2(data_str)))
        log.info("[DRY RUN] Prompt 3: %d chars", len(PROMPT_3))
        return {}

    client       = anthropic.Anthropic()
    conversation = []

    # Message 1
    log.info("Message 1: system identity...")
    conversation.append({"role": "user", "content": PROMPT_1_SYSTEM})
    r1 = client.messages.create(model=MODEL, max_tokens=MSG1_TOKENS, messages=conversation)
    reply1 = r1.content[0].text
    log.info("  Response: %d chars", len(reply1))
    conversation.append({"role": "assistant", "content": reply1})

    # Message 2
    log.info("Message 2: full analysis (Blocks 0-8)...")
    conversation.append({"role": "user", "content": build_prompt_2(data_str)})
    r2 = client.messages.create(model=MODEL, max_tokens=MSG2_TOKENS, messages=conversation)
    reply2 = r2.content[0].text
    log.info("  Response: %d chars", len(reply2))
    conversation.append({"role": "assistant", "content": reply2})

    # Message 3
    log.info("Message 3: JSON finalisation...")
    conversation.append({"role": "user", "content": PROMPT_3})
    r3 = client.messages.create(model=MODEL, max_tokens=MSG3_TOKENS, messages=conversation)
    raw_json = r3.content[0].text
    log.info("  Response: %d chars", len(raw_json))

    # Parse — strip markdown fences if model added them
    cleaned = raw_json.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            l for l in cleaned.split("\n")
            if not l.strip().startswith("```")
        ).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.error("JSON parse failed: %s", e)
        log.error("Raw (first 500): %s", raw_json[:500])
        raise RuntimeError(f"API returned invalid JSON: {e}")


# ============================================================
# DETERMINISTIC MARKET DATA OVERRIDES
# ============================================================

def _csv_rows(text: str) -> list[dict]:
    if not text:
        return []
    try:
        return [dict(r) for r in csv.DictReader(text.splitlines())]
    except Exception:
        return []


def _latest_row(text: str) -> dict:
    rows = [r for r in _csv_rows(text) if any(str(v or "").strip() for v in r.values())]
    return rows[-1] if rows else {}


def _safe_float(value, default=None):
    try:
        text = str(value).strip()
        if text == "" or text.lower() in {"none", "nan", "null"}:
            return default
        return float(text)
    except Exception:
        return default


def _set_nested(target: dict, path: tuple[str, ...], value):
    node = target
    for key in path[:-1]:
        existing = node.get(key)
        if not isinstance(existing, dict):
            existing = {}
            node[key] = existing
        node = existing
    node[path[-1]] = value


def _append_unique_flag(macro_json: dict, flag: str):
    extras = macro_json.setdefault("extras", {})
    flags = extras.setdefault("conflict_flags", [])
    if not isinstance(flags, list):
        flags = [str(flags)]
        extras["conflict_flags"] = flags
    if flag not in flags:
        flags.append(flag)


def _clean_resolved_market_flags(macro_json: dict, overrides: dict):
    extras = macro_json.setdefault("extras", {})
    flags = extras.get("conflict_flags", [])
    if not isinstance(flags, list):
        flags = [str(flags)] if flags else []
    cleaned = []
    removed = 0

    def resolved_by_override(flag: str) -> bool:
        text = str(flag or "").upper()
        if ("VIX9D" in text or "VIX3M" in text or "TERM STRUCTURE" in text) and overrides.get("vix9d") is not None and overrides.get("vix3m") is not None:
            return True
        if "VVIX" in text and overrides.get("vvix") is not None:
            return True
        if ("HY" in text or "IG" in text or "CREDIT SPREAD" in text or "CREDIT" in text) and (
            overrides.get("hy_oas") is not None or overrides.get("ig_oas") is not None
        ):
            return True
        if "GEX" in text and overrides.get("gex_net_bn") is not None:
            return True
        if ("XLC" in text or "COMMUNICATION SERVICES" in text) and overrides.get("xlc_present"):
            return True
        if ("USSLIND" in text or "LEI" in text) and not overrides.get("usslind_quarantined"):
            return True
        if ("YIELD CURVE" in text or "T10Y2Y" in text or "2Y10Y" in text) and overrides.get("curve_2y10y") is not None:
            return True
        return False

    for flag in flags:
        if resolved_by_override(flag):
            removed += 1
            continue
        cleaned.append(flag)

    extras["conflict_flags"] = cleaned
    if removed:
        _append_unique_flag(
            macro_json,
            f"RESOLVED: {removed} stale macro data gap flag(s) cleared by confirmed market_data overrides; CSV primary applied",
        )


def _vix_term_regime(vix9d, vix3m) -> str:
    if vix9d is None or vix3m is None:
        return "MISSING"
    spread = vix3m - vix9d
    if spread > 0.25:
        return "CONTANGO"
    if spread < -0.25:
        return "BACKWARDATION"
    return "FLAT"


def _vol_mode_from_vix(vix, term_regime, vvix=None) -> str:
    if vix is None:
        return "UNKNOWN"
    if vix >= 30:
        return "FEAR_MODE"
    if vix >= 24:
        return "HIGH_STRESS"
    if vix >= 20 or (vvix is not None and vvix >= 135):
        return "ELEVATED_CAUTION"
    if term_regime == "CONTANGO":
        return "COMPRESSED_CONTANGO_LOW_VOL"
    return "SHALLOW_CONTANGO"


def _credit_state_from_spreads(hy_oas, ig_oas) -> tuple[str, float]:
    if hy_oas is None and ig_oas is None:
        return "UNKNOWN", 50.0
    hy = hy_oas if hy_oas is not None else 3.5
    ig = ig_oas if ig_oas is not None else 1.25
    if hy >= 5.0 or ig >= 1.75:
        return "TIGHTENING", 75.0
    if hy <= 3.25 and ig <= 1.15:
        return "BENIGN", 25.0
    return "NEUTRAL", 50.0


def _gex_score(regime: str, net_gex_bn) -> float:
    reg = str(regime or "").upper()
    if "NEGATIVE" in reg:
        return 0.25
    if "POSITIVE" in reg:
        return 0.75
    if net_gex_bn is None:
        return 0.50
    if net_gex_bn > 0:
        return 0.70
    if net_gex_bn < 0:
        return 0.30
    return 0.50


def extract_market_data_overrides(payload: dict) -> dict:
    data = payload.get("data", {})
    vix_row = _latest_row(data.get("vix_engine_csv", ""))
    macro_master = _latest_row(data.get("macro_master_csv", ""))
    gex_rows = _csv_rows(data.get("gex_proxy_csv", ""))
    sectors_rows = _csv_rows(data.get("sectors_csv", ""))
    report = data.get("report_json", {}) if isinstance(data.get("report_json"), dict) else {}

    gex_primary = next((r for r in gex_rows if str(r.get("Ticker", "")).upper() == "SPY"), gex_rows[0] if gex_rows else {})
    sector_tickers = {str(r.get("ticker", "")).upper(): r for r in sectors_rows}

    vix = _safe_float(vix_row.get("VIX"))
    vix9d = _safe_float(vix_row.get("VIX9D"))
    vix3m = _safe_float(vix_row.get("VIX3M"))
    vvix = _safe_float(vix_row.get("VVIX"))
    term_regime = _vix_term_regime(vix9d, vix3m)
    vix_spread = None if vix9d is None or vix3m is None else round(vix3m - vix9d, 4)

    dgs10 = _safe_float(macro_master.get("DGS10"))
    dgs2 = _safe_float(macro_master.get("DGS2"))
    curve = _safe_float(macro_master.get("Spread_2Y10Y"))
    hy_oas = _safe_float(macro_master.get("HY_OAS"))
    ig_oas = _safe_float(macro_master.get("IG_BBB_OAS"))
    sofr = _safe_float(macro_master.get("SOFR"))
    credit_state, credit_risk_score = _credit_state_from_spreads(hy_oas, ig_oas)

    net_gex_bn = _safe_float(gex_primary.get("Net_GEX_Bn"))
    gex_regime = str(gex_primary.get("Regime", "") or "")
    gex_score = _gex_score(gex_regime, net_gex_bn)

    usslind_quarantined = str(macro_master.get("USSLIND_Quarantined", "")).strip().upper() in {"TRUE", "1", "YES"}
    xlc_30d = _safe_float(macro_master.get("XLC_30d"))
    xlc_present = "XLC" in sector_tickers or xlc_30d is not None

    return {
        "as_of_date": vix_row.get("Date") or macro_master.get("Date") or "",
        "vix": vix,
        "vix9d": vix9d,
        "vix3m": vix3m,
        "vvix": vvix,
        "vvix_stress": vix_row.get("VVIX_Stress", ""),
        "vix_data_quality": vix_row.get("VIX_Data_Quality", ""),
        "vix_term_regime": term_regime,
        "vix_spread": vix_spread,
        "vol_mode": _vol_mode_from_vix(vix, term_regime, vvix),
        "dgs10": dgs10,
        "dgs2": dgs2,
        "curve_2y10y": curve,
        "sofr": sofr,
        "hy_oas": hy_oas,
        "ig_oas": ig_oas,
        "credit_state": credit_state,
        "credit_risk_score": credit_risk_score,
        "gex_regime": gex_regime,
        "gex_net_bn": net_gex_bn,
        "gex_score": gex_score,
        "gex_flip": _safe_float(gex_primary.get("Gamma_Flip")),
        "gex_stress": gex_primary.get("GEX_Stress", ""),
        "gex_contracts_used": _safe_float(gex_primary.get("Contracts_Used")),
        "usslind_status": macro_master.get("USSLIND_Status", ""),
        "usslind_quarantined": usslind_quarantined,
        "xlc_present": xlc_present,
        "xlc_30d": xlc_30d,
        "report_vix9d_missing": report.get("vix_term_structure", {}).get("vix9d") is None,
        "report_vix3m_missing": report.get("vix_term_structure", {}).get("vix3m") is None,
        "report_yield_curve_slope": _safe_float(report.get("yield_curve", {}).get("slope")),
    }


def apply_market_data_overrides(macro_json: dict, payload: dict) -> dict:
    """Apply confirmed Colab market_data fields after model synthesis."""
    overrides = extract_market_data_overrides(payload)
    extras = macro_json.setdefault("extras", {})

    if overrides["vix"] is not None:
        macro_json["vix_spot"] = overrides["vix"]
        extras["vix_spot"] = overrides["vix"]
        extras.setdefault("vix_5d_avg", overrides["vix"])

    if overrides["vix9d"] is not None and overrides["vix3m"] is not None:
        _clean_resolved_market_flags(macro_json, overrides)
        extras["vix_contango"] = overrides["vix_spread"]
        extras["vix_term_regime"] = overrides["vix_term_regime"]
        volatility = extras.setdefault("volatility", {})
        volatility.update({
            "regime": overrides["vix_term_regime"],
            "signal": overrides["vix_data_quality"] or "CONFIRMED",
            "vix_spot": overrides["vix"],
            "vix9d": overrides["vix9d"],
            "vix3m": overrides["vix3m"],
            "vvix": overrides["vvix"],
            "vvix_stress": overrides["vvix_stress"],
            "spread": overrides["vix_spread"],
        })
        if overrides["report_vix9d_missing"]:
            _append_unique_flag(macro_json, "RESOLVED: report_json VIX9D missing; vix_engine_csv primary applied")
        if overrides["report_vix3m_missing"]:
            _append_unique_flag(macro_json, "RESOLVED: report_json VIX3M missing; vix_engine_csv primary applied")
    else:
        _append_unique_flag(macro_json, "ACTIVE: VIX9D/VIX3M missing from vix_engine_csv; term structure inferred")

    if overrides["vvix"] is not None:
        extras["vvix"] = overrides["vvix"]
    else:
        _append_unique_flag(macro_json, "ACTIVE: VVIX missing; vol-of-vol stress cannot validate option premium stress")

    if overrides["vol_mode"] != "UNKNOWN":
        macro_json["vol_mode"] = overrides["vol_mode"]
        extras["volatility_mode"] = overrides["vol_mode"]

    if overrides["curve_2y10y"] is not None:
        rates = extras.setdefault("rates", {})
        rates.update({
            "sofr": overrides["sofr"],
            "t10y": overrides["dgs10"],
            "t2y": overrides["dgs2"],
            "curve_2y10y": overrides["curve_2y10y"],
            "spread_signal": "NORMAL" if overrides["curve_2y10y"] >= 0 else "INVERTED",
            "hy_oas": overrides["hy_oas"],
            "ig_bbb_oas": overrides["ig_oas"],
        })
        extras["yield_curve"] = {
            "2y10y_value": overrides["curve_2y10y"],
            "state": "NORMAL" if overrides["curve_2y10y"] >= 0 else "INVERTED",
            "recession_probability": 0.10 if overrides["curve_2y10y"] >= 0 else 0.35,
        }
        if (
            overrides["report_yield_curve_slope"] is not None
            and abs(overrides["report_yield_curve_slope"] - overrides["curve_2y10y"]) > 0.03
        ):
            _append_unique_flag(macro_json, "ACTIVE: yield curve date/value mismatch exceeds tolerance")
        elif overrides["report_yield_curve_slope"] is not None:
            _append_unique_flag(macro_json, "RESOLVED: minor yield curve rounding/date mismatch immaterial; macro_master CSV primary applied")

    if overrides["hy_oas"] is not None or overrides["ig_oas"] is not None:
        macro_json["credit_state"] = overrides["credit_state"]
        macro_json["credit_risk_score"] = overrides["credit_risk_score"]
        extras["credit"] = {
            "state": overrides["credit_state"],
            "risk_score": overrides["credit_risk_score"],
            "hy_oas": overrides["hy_oas"],
            "ig_bbb_oas": overrides["ig_oas"],
            "source": "avsh_macro_master.csv",
        }
    else:
        _append_unique_flag(macro_json, "ACTIVE: HY/IG credit spreads missing; credit risk carried neutral")

    if overrides["gex_net_bn"] is not None:
        macro_json["gex_regime_score"] = overrides["gex_score"]
        extras["gex"] = {
            "regime": overrides["gex_regime"],
            "net_gex_bn": overrides["gex_net_bn"],
            "gamma_flip": overrides["gex_flip"],
            "stress": overrides["gex_stress"],
            "contracts_used": overrides["gex_contracts_used"],
            "score": overrides["gex_score"],
            "source": "avshunter_gex_proxy.csv",
        }
    else:
        macro_json.setdefault("gex_regime_score", 0.5)
        _append_unique_flag(macro_json, "ACTIVE: GEX missing; dealer gamma defaulted neutral")

    extras["lei_usslind"] = {
        "status": overrides["usslind_status"],
        "quarantined": overrides["usslind_quarantined"],
        "source": "avsh_macro_master.csv",
    }
    if overrides["usslind_quarantined"]:
        _append_unique_flag(macro_json, "ACTIVE: LEI/USSLIND anomaly quarantined; excluded from calculations")

    extras["sector_etf_coverage"] = {
        "xlc_present": overrides["xlc_present"],
        "xlc_30d": overrides["xlc_30d"],
        "source": "sectors_csv|avsh_macro_master.csv",
    }
    if not overrides["xlc_present"]:
        _append_unique_flag(macro_json, "ACTIVE: XLC sector ETF missing; Communication Services bias inferred neutral")

    extras["macro_market_data_quality"] = {
        "vix_term_structure": "CONFIRMED" if overrides["vix9d"] is not None and overrides["vix3m"] is not None else "INFERRED",
        "vvix": "CONFIRMED" if overrides["vvix"] is not None else "MISSING",
        "credit_spreads": "CONFIRMED" if overrides["hy_oas"] is not None or overrides["ig_oas"] is not None else "MISSING",
        "gex": "CONFIRMED" if overrides["gex_net_bn"] is not None else "MISSING",
        "lei_usslind": "QUARANTINED" if overrides["usslind_quarantined"] else "CONFIRMED",
        "xlc_sector": "CONFIRMED" if overrides["xlc_present"] else "MISSING",
        "yield_curve": "CONFIRMED" if overrides["curve_2y10y"] is not None else "MISSING",
    }
    return macro_json


# ============================================================
# VALIDATOR
# ============================================================


def normalise_horizon_routing(macro_json: dict) -> dict:
    """
    Ensures top-level and extras.horizon_routing contain the full production
    horizon contract required by macro_horizon_router.py.

    Required buckets: 1_5d, 6_10d, 11_20d
    """
    required_buckets = ("1_5d", "6_10d", "11_20d")

    def _safe_float(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _get_forward_bias_bucket(extras: dict, bucket: str) -> dict:
        fb = extras.get("forward_bias", {})
        if not isinstance(fb, dict):
            return {}
        mapping = {
            "1_5d":   "short_1_5d",
            "6_10d":  "medium_6_10d",
            "11_20d": "long_11_20d",
        }
        return fb.get(mapping[bucket], {}) if isinstance(fb.get(mapping[bucket], {}), dict) else {}

    def _default_bucket(bucket: str, extras: dict) -> dict:
        fb_bucket = _get_forward_bias_bucket(extras, bucket)
        bias = (
            fb_bucket.get("direction")
            or fb_bucket.get("bias")
            or macro_json.get("dir_bias")
            or "NEUTRAL"
        )
        bullish_prob_pct = _safe_float(
            fb_bucket.get("bullish_prob_pct"),
            {"1_5d": 50.0, "6_10d": 50.0, "11_20d": 50.0}[bucket],
        )
        base_size = _safe_float(macro_json.get("size_multiplier"), 0.5)
        fb_size   = _safe_float(fb_bucket.get("size_multiplier"), base_size)

        if bucket == "11_20d":
            size_multiplier  = min(fb_size, 0.60)
            action           = "MONITOR_ONLY_TRIGGER_REQUIRED"
            block_conditions = [
                "Extended horizon requires stronger sector confirmation",
                "LLR_TRUE required before execution",
                "Avoid if macro conviction remains below 0.50",
            ]
        elif bucket == "6_10d":
            size_multiplier  = min(fb_size, 0.55)
            action           = "REDUCED_SIZE_LONG_LEADERSHIP_ONLY"
            block_conditions = [
                "Fung-Hsieh NO-GO active",
                "Forward bias score below 0.10",
                "Inflation data worsens without policy response",
            ]
        else:
            size_multiplier  = min(fb_size, 0.50)
            action           = "REDUCED_SIZE_LONG_LEADERSHIP_ONLY"
            block_conditions = [
                "Fung-Hsieh NO-GO active",
                "Conviction below 0.50",
                "No trigger confirmation on entry",
            ]

        return {
            "bias":             str(bias).upper(),
            "bullish_prob_pct": bullish_prob_pct,
            "engine_mode":      "WAIT_FOR_TRIGGER",
            "action":           action,
            "size_multiplier":  size_multiplier,
            "block_conditions": block_conditions,
        }

    extras = macro_json.setdefault("extras", {})

    # Top-level horizon_routing
    top_hr = macro_json.get("horizon_routing")
    if not isinstance(top_hr, dict):
        top_hr = {}
        macro_json["horizon_routing"] = top_hr

    for bucket in required_buckets:
        if bucket not in top_hr or not isinstance(top_hr.get(bucket), dict):
            top_hr[bucket] = _default_bucket(bucket, extras)

    # extras.horizon_routing
    extras_hr = extras.get("horizon_routing")
    if not isinstance(extras_hr, dict):
        extras_hr = {}
        extras["horizon_routing"] = extras_hr

    for bucket in required_buckets:
        if bucket not in extras_hr or not isinstance(extras_hr.get(bucket), dict):
            extras_hr[bucket] = dict(top_hr[bucket])

    macro_json["horizon_routing_complete"]          = True
    macro_json["horizon_routing_required_buckets"]  = list(required_buckets)
    return macro_json


def validate_macro_json(macro: dict) -> tuple:
    flat = {}

    def _walk(node):
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            canonical = PIPELINE_ALIASES.get(k, k)
            if canonical not in flat:
                flat[canonical] = v
            if isinstance(v, dict):
                _walk(v)

    _walk(macro)

    missing = [
        f for f in REQUIRED_FIELDS
        if f not in macro and PIPELINE_ALIASES.get(f, f) not in flat
    ]

    required_horizon_buckets = ["1_5d", "6_10d", "11_20d"]

    top_hr = macro.get("horizon_routing")
    if not isinstance(top_hr, dict):
        missing.append("horizon_routing_not_dict")
    else:
        for bucket in required_horizon_buckets:
            if bucket not in top_hr:
                missing.append(f"horizon_routing.{bucket}")

    extras    = macro.get("extras", {})
    extras_hr = extras.get("horizon_routing") if isinstance(extras, dict) else None

    if not isinstance(extras_hr, dict):
        missing.append("extras.horizon_routing_not_dict")
    else:
        for bucket in required_horizon_buckets:
            if bucket not in extras_hr:
                missing.append(f"extras.horizon_routing.{bucket}")

    # ── Sector rotation validation (v1.1) ─────────────────────────────────────
    _sr = macro.get("sector_rotation")
    if not isinstance(_sr, dict):
        missing.append("sector_rotation_block_missing")
    else:
        for _key in SECTOR_ROTATION_REQUIRED_KEYS:
            if _key not in _sr:
                missing.append(f"sector_rotation.{_key}")
        _sbm = _sr.get("sector_bias_map", {})
        if not isinstance(_sbm, dict) or len(_sbm) == 0:
            missing.append("sector_rotation.sector_bias_map_empty")

    return len(missing) == 0, missing


# ============================================================
# FRESHNESS CHECK
# ============================================================

def is_fresh(output_path: Path, max_hours: int) -> bool:
    if not output_path.exists():
        return False
    age = (datetime.now().timestamp() - output_path.stat().st_mtime) / 3600
    return age < max_hours


def any_input_newer_than_output(market_dir: Path, output_path: Path) -> bool:
    if not output_path.exists():
        return True
    output_mtime = output_path.stat().st_mtime
    if not market_dir.exists():
        return False
    for path in market_dir.iterdir():
        if path.is_file() and path.stat().st_mtime > output_mtime:
            return True
    return False


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="AVSHUNTER Automated Macro JSON Builder")
    parser.add_argument("--dropbox",  default=str(DROPBOX_DIR))
    parser.add_argument("--force",   action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--update",
        default="",
        help="Partial update mode. Comma-separated file keys to refresh from disk, e.g. vix_engine_csv,sectors_csv.",
    )
    parser.add_argument(
        "--update-all",
        action="store_true",
        help="Explicit full refresh using all known file keys.",
    )
    args = parser.parse_args()

    dropbox_path = Path(args.dropbox)
    market_path  = dropbox_path / "market_data"
    macro_path   = dropbox_path / "macro"
    output_path  = macro_path / OUTPUT_FILENAME
    macro_path.mkdir(parents=True, exist_ok=True)
    update_keys = []
    if args.update_all:
        update_keys = list(FILE_SPEC_KEYS)
    elif args.update.strip():
        update_keys = [key.strip() for key in args.update.split(",") if key.strip()]
        unknown = sorted(set(update_keys) - set(FILE_SPEC_KEYS))
        if unknown:
            log.error("Unknown --update file key(s): %s", ", ".join(unknown))
            log.error("Known keys: %s", ", ".join(FILE_SPEC_KEYS))
            sys.exit(1)

    print(f"""
    ==========================================================
       AVSHUNTER - AUTOMATED MACRO JSON BUILDER
       Replaces 3-prompt manual GPT copy-paste workflow
    ==========================================================
    market_data : {market_path}
    output      : {output_path}
    dry_run     : {args.dry_run}
    update_keys : {','.join(update_keys) if update_keys else 'FULL'}
    """)

    # Freshness check
    if not args.force and not args.dry_run and not update_keys and is_fresh(output_path, FRESH_HOURS):
        age = (datetime.now().timestamp() - output_path.stat().st_mtime) / 3600
        if any_input_newer_than_output(market_path, output_path):
            log.info("Input files updated since last build - triggering rebuild.")
        else:
            log.info("JSON is %.1fh old (< %dh) and no newer inputs. Use --force to rebuild.", age, FRESH_HOURS)
            return

    # Load data
    log.info("Loading Colab outputs from: %s", market_path)
    try:
        prior_macro = _load_existing_macro(output_path) if update_keys and not args.update_all else {}
        payload  = load_data_payload(market_path, update_keys=update_keys if not args.update_all else None, prior_macro=prior_macro)
        data_str = format_data_for_prompt(payload)
        log.info("Formatted data payload: %d chars", len(data_str))
    except RuntimeError as e:
        log.error("%s", e)
        sys.exit(1)

    # API call
    log.info("Calling Anthropic API (3-prompt sequence)...")
    try:
        macro_json = call_macro_api(data_str, dry_run=args.dry_run)
    except RuntimeError as e:
        log.error("%s", e)
        sys.exit(1)

    if args.dry_run:
        log.info("[DRY RUN] Done. No files written.")
        return

    # POST-PROCESSING SAFETY NET v2
    # Ensure all required top-level and extras fields are present.
    # Claude sometimes omits fields — this guarantees pipeline compatibility
    # by deriving values from what IS present.
    _extras = macro_json.setdefault("extras", {})

    # ── Top-level fields that pipeline expects ────────────────────────────────
    if "net_liquidity_score" not in macro_json:
        macro_json["net_liquidity_score"] = 0.5  # neutral default
    if "vix_regime_score" not in macro_json:
        _vm = str(macro_json.get("vol_mode","")).upper()
        macro_json["vix_regime_score"] = (
            0.785 if "CONTANGO" in _vm and "LOW" in _vm else
            0.6   if "SHALLOW" in _vm else
            0.35  if "BACKWARDATION" in _vm else
            0.5
        )
    if "gex_regime_score" not in macro_json:
        macro_json["gex_regime_score"] = 0.5
    if "macro_momentum_score" not in macro_json:
        macro_json["macro_momentum_score"] = macro_json.get("macro_conviction", 0.5)
    if "regime_label" not in macro_json:
        macro_json["regime_label"] = macro_json.get("regime_state", "TRANSITIONAL")
    if "regime_probability" not in macro_json:
        macro_json["regime_probability"] = macro_json.get("macro_conviction", 0.55)
    if "vix_spot" not in macro_json:
        _report = payload["data"].get("report_json", {})
        _vts = _report.get("vix_term_structure", {})
        macro_json["vix_spot"] = _vts.get("vix_spot") or _vts.get("vix9d") or 18.0
    if "macro_filter" not in macro_json:
        _fh = payload["data"].get("fung_hsieh_csv", "")
        macro_json["macro_filter"] = "GO" if "GO" in str(_fh).upper() and "NO_GO" not in str(_fh).upper() else "NO_GO"
    if "sector_lead" not in macro_json:
        macro_json["sector_lead"] = []
    if "sector_avoid" not in macro_json:
        macro_json["sector_avoid"] = []
    if "size_multiplier" not in macro_json:
        macro_json["size_multiplier"] = 0.75
    if "trigger_required" not in macro_json:
        macro_json["trigger_required"] = macro_json.get("macro_conviction", 0.6) < 0.70

    # ── SECTOR ROTATION safety net (v1.1) ────────────────────────────────────
    # If GPT did not produce sector_rotation block, derive from sector_lead/avoid
    if "sector_rotation" not in macro_json or not isinstance(macro_json.get("sector_rotation"), dict):
        _sector_lead  = macro_json.get("sector_lead",  []) or []
        _sector_avoid = macro_json.get("sector_avoid", []) or []
        _ETF_TO_GICS  = {
            "XLK": "Information Technology", "XLV": "Health Care",
            "XLF": "Financials",             "XLY": "Consumer Discretionary",
            "XLP": "Consumer Staples",       "XLI": "Industrials",
            "XLE": "Energy",                 "XLB": "Materials",
            "XLRE": "Real Estate",           "XLC": "Communication Services",
            "XLU": "Utilities",
        }
        _ALL_GICS = list(_ETF_TO_GICS.values())
        _bias_map = {}
        for _etf in _sector_lead:
            _g = _ETF_TO_GICS.get(str(_etf).upper(), str(_etf))
            _bias_map[_g] = "TAILWIND"
        for _etf in _sector_avoid:
            _g = _ETF_TO_GICS.get(str(_etf).upper(), str(_etf))
            if _g not in _bias_map:
                _bias_map[_g] = "HEADWIND"
        for _g in _ALL_GICS:
            if _g not in _bias_map:
                _bias_map[_g] = "NEUTRAL"
        macro_json["sector_rotation"] = {
            "strongest_sectors": [_ETF_TO_GICS.get(str(e).upper(), str(e)) for e in _sector_lead],
            "weakest_sectors":   [_ETF_TO_GICS.get(str(e).upper(), str(e)) for e in _sector_avoid],
            "rotation_signal":   "MIXED_SIGNALS",
            "sector_bias_map":   _bias_map,
        }
        log.info("POST-PROCESS: sector_rotation derived from sector_lead/avoid fallback")
    else:
        # Ensure all 11 GICS sectors present in sector_bias_map — fill missing with NEUTRAL
        _sr = macro_json["sector_rotation"]
        _sbm = _sr.setdefault("sector_bias_map", {})
        _REQUIRED_GICS = [
            "Information Technology", "Health Care", "Financials",
            "Consumer Discretionary", "Consumer Staples", "Industrials",
            "Energy", "Materials", "Real Estate", "Communication Services", "Utilities",
        ]
        for _g in _REQUIRED_GICS:
            if _g not in _sbm:
                _sbm[_g] = "NEUTRAL"
        log.info("POST-PROCESS: sector_rotation block validated — %d sectors covered", len(_sbm))
    if "horizon_routing" not in macro_json:
        macro_json["horizon_routing"] = {
            "1_5d": {
                "bias":             macro_json.get("dir_bias", "NEUTRAL"),
                "bullish_prob_pct": 50.0,
                "engine_mode":      "WAIT_FOR_TRIGGER",
                "action":           "REDUCED_SIZE_LONG_LEADERSHIP_ONLY",
                "size_multiplier":  min(float(macro_json.get("size_multiplier", 0.75)), 0.50),
                "block_conditions": [
                    "No trigger confirmation on entry",
                    "Macro conviction below full-size threshold",
                ],
            },
            "6_10d": {
                "bias":             macro_json.get("dir_bias", "NEUTRAL"),
                "bullish_prob_pct": 50.0,
                "engine_mode":      "WAIT_FOR_TRIGGER",
                "action":           "REDUCED_SIZE_LONG_LEADERSHIP_ONLY",
                "size_multiplier":  min(float(macro_json.get("size_multiplier", 0.75)), 0.55),
                "block_conditions": [
                    "Forward bias insufficient for full-size entry",
                    "Trigger confirmation required",
                ],
            },
            "11_20d": {
                "bias":             macro_json.get("dir_bias", "NEUTRAL"),
                "bullish_prob_pct": 50.0,
                "engine_mode":      "WAIT_FOR_TRIGGER",
                "action":           "MONITOR_ONLY_TRIGGER_REQUIRED",
                "size_multiplier":  min(float(macro_json.get("size_multiplier", 0.75)), 0.60),
                "block_conditions": [
                    "Extended horizon requires stronger confirmation",
                    "LLR_TRUE required before execution",
                    "Avoid if sector leadership weakens",
                ],
            },
        }
    # ─────────────────────────────────────────────────────────────────────────

    _extras = macro_json.setdefault("extras", {})

    # conviction_score: must equal macro_conviction
    if "conviction_score" not in _extras:
        _cv = macro_json.get("macro_conviction", 0.60)
        try:
            _extras["conviction_score"] = float(_cv)
        except (TypeError, ValueError):
            _extras["conviction_score"] = 0.60
        log.info("POST-PROCESS: injected conviction_score = %s", _extras["conviction_score"])

    # vix_contango: VIX3M - VIX9D spread from report JSON if available
    if "vix_contango" not in _extras:
        _vix_contango = None
        _report = payload["data"].get("report_json", {})
        _vts = _report.get("vix_term_structure", {})
        _v3m = _vts.get("vix3m")
        _v9d = _vts.get("vix9d")
        if _v3m and _v9d:
            try:
                _vix_contango = round(float(_v3m) - float(_v9d), 4)
            except (TypeError, ValueError):
                pass
        # Fallback: check extras.vix_term sub-block Claude may have written
        if _vix_contango is None:
            _vt = _extras.get("vix_term", {})
            _sp = _vt.get("spread")
            if _sp is not None:
                try:
                    _vix_contango = round(float(_sp), 4)
                except (TypeError, ValueError):
                    pass
        # Final fallback: derive from vol_mode — CONTANGO = positive, BACKWARDATION = negative
        if _vix_contango is None:
            _vm = str(macro_json.get("vol_mode", "")).upper()
            _vix_contango = 0.128 if "CONTANGO" in _vm else -0.5 if "BACKWARDATION" in _vm else 0.05
        _extras["vix_contango"] = _vix_contango
        log.info("POST-PROCESS: injected vix_contango = %s", _vix_contango)

    # Also inject aliased fields that pipeline _flatten_macro walks for
    # Note: risk_on_switch removed — duplicate of top-level risk_on_off_switch
    if "volatility_mode" not in _extras:
        _extras["volatility_mode"] = macro_json.get("vol_mode", "")
    if "liquidity_status" not in _extras:
        _extras["liquidity_status"] = macro_json.get("liquidity_pulse", "")

    # Confirmed Colab market_data overrides.
    # This prevents fresh VIX9D/VIX3M/VVIX/credit/GEX/sector data from being
    # lost when the model omits a field or the report JSON used a proxy.
    macro_json = apply_market_data_overrides(macro_json, payload)

    # Normalise horizon routing before validation (ensures 11_20d always present)
    macro_json = normalise_horizon_routing(macro_json)

    # Validate
    all_pass, missing = validate_macro_json(macro_json)
    if not all_pass:
        log.warning("VALIDATION: %d fields missing: %s", len(missing), missing)
    else:
        log.info("VALIDATION: All required fields present ✅")

    # Add builder metadata
    macro_json["_builder_metadata"] = {
        "built_at":      datetime.now(timezone.utc).isoformat(),
        "built_by":      "build_macro_json.py",
        "model":         MODEL,
        "files_used":    payload["files_found"],
        "files_used_by_key": payload.get("files_found_by_key", {}),
        "files_missing": payload["files_missing"],
        "update_mode":   payload.get("update_mode", "FULL"),
        "update_keys":   payload.get("update_keys", []),
        "validation":    "PASS" if all_pass else f"FAIL - missing: {missing}",
    }

    # Write dropbox output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(macro_json, f, indent=2)
    log.info("Written: %s (%.1f KB)", output_path, output_path.stat().st_size / 1024)

    # Copy to pipeline data/macro/
    try:
        PIPELINE_MACRO_DIR.mkdir(parents=True, exist_ok=True)
        pipeline_out = PIPELINE_MACRO_DIR / OUTPUT_FILENAME
        shutil.copy2(output_path, pipeline_out)
        log.info("Copied to pipeline: %s", pipeline_out)
    except Exception as e:
        log.warning("Could not copy to pipeline: %s", e)

    # Summary
    print()
    print("=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    print(f"  Output     : {output_path}")
    print(f"  Validation : {'✅ PASS' if all_pass else '❌ FAIL'}")
    print()
    print("  Key fields:")
    for f in ["regime_state","dir_bias","vol_mode",
              "risk_on_off_switch","macro_conviction","macro_filter"]:
        print(f"    {f:<25s}: {macro_json.get(f,'MISSING')}")
    print()
    print("  Next steps:")
    print("  1. Verify key fields above look correct for today")
    print("  2. python rapid_rotation_flag.py")
    print("  3. python intelligent_orchestrator.py --evening")
    print("=" * 60)


if __name__ == "__main__":
    main()
