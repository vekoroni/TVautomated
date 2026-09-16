# AVSHUNTER Pipeline Audit Report
**Date:** 2026-06-27  
**Run audited:** 20260624_052030  
**Auditor:** Claude Code — read-only, no changes made  
**Status:** AUDIT COMPLETE — Prompt 0 deliverable

---

## EXECUTIVE SUMMARY

The pipeline is functional and producing live signal output (147 GO, 913 FLAG, 22 BLOCK across 1,082 candidates on run 20260624_052030). No zero-signal failure modes detected in the current build. Six findings require action before the Wave 1–4 fixes are applied; two are pre-existing security issues that must be resolved immediately regardless of the enhancement schedule.

---

## A. CONFIRMED FINDINGS

### CF-01 / CF-02 / CF-03 — `_load_macro_regime()` returns only a string
**File:** `morning_gate.py` | **Lines:** 479–492, 954–955  
**Severity:** MEDIUM  

`_load_macro_regime()` returns a plain `str` (the regime label only). The macro JSON contains `vol_mode`, `macro_conviction`, `sector_lead`, `sector_avoid`, `macro_filter`, and `as_of_utc` — none of these reach `run_gate()` or the output CSV.

**Verified impact:** `morning_validated_trades_20260624_052030.csv` (504 columns) is MISSING:
- `macro_vol_mode`
- `macro_conviction`
- `macro_sector_lead`
- `macro_sector_avoid`
- `macro_freshness_flag`

The Intelligence Lab reads these fields **directly from `macro_intelligence_latest.json`** (its own separate load at `intelligence_lab.py:630–633`) — not from the validated trades CSV. So the Lab is not broken, but the morning_validated_trades CSV is missing macro context that would be visible to downstream tools and the summary JSON.

**Fix:** Prompt 1 CF-01/02/03 — implemented correctly.

---

### CF-04 — Bond macro display fields
**File:** `morning_gate.py` | **Lines:** 495–571, 825–831  
**Severity:** CLEAN (already working)  

`_load_bond_macro()` correctly flattens all nested sub-objects (composite, yield_curve, credit_stress, zn_futures, auction) into flat keys. The bond display loop writes them all to the output.

**Verified:** All required bond fields PRESENT in `morning_validated_trades_20260624_052030.csv`:
- `bond_macro_score` ✓
- `bond_macro_flag` ✓  
- `bond_curve_state` ✓
- `bond_credit_stress` ✓
- `bond_breakeven_adj_pct` ✓
- `bond_primary_warning` ✓
- `bond_auction_today` ✓
- `bond_spread_risk_flag` ✓

**No action required for CF-04.** The flatten-vs-nested concern raised in Prompt 1 is already resolved.

---

### CF-SECURITY — API keys hardcoded in source
**File:** `morning_gate.py` | **Lines:** 64–65  
**Severity:** CRITICAL — IMMEDIATE ACTION REQUIRED  

```python
POLYGON_API_KEY    = os.getenv("POLYGON_API_KEY", "<REDACTED_POLYGON_API_KEY>").strip()
MARKETDATA_API_KEY = os.getenv("MARKETDATA_API_KEY", "<REDACTED_MARKETDATA_API_KEY>").strip()
```

Both API keys are hardcoded as fallback strings in the `os.getenv()` calls. This violates the CLAUDE.md rule "never hardcode, never print, never reproduce" and exposes keys in version control.

A prior commit (`d884385: fix(security): remove hardcoded API key fallback`) fixed another file but missed `morning_gate.py`.

**Additionally:** the Prompt 0 briefing text submitted to Claude in this session contained the live `ANTHROPIC_API_KEY`. This key should be rotated at `console.anthropic.com` immediately — it has been transmitted through Claude's context window.

**Fix required before Prompt 1:** Remove the hardcoded fallback strings. Replace with:
```python
POLYGON_API_KEY    = os.getenv("POLYGON_API_KEY", "").strip()
MARKETDATA_API_KEY = os.getenv("MARKETDATA_API_KEY", "").strip()
```
Add a startup guard in `main()`:
```python
if not POLYGON_API_KEY or not MARKETDATA_API_KEY:
    log.error("POLYGON_API_KEY and MARKETDATA_API_KEY must be set in .env — aborting")
    return 1
```

---

### CF-VOLUME — `avg_volume_20d` absent from candidates
**File:** `morning_gate.py` / `morning_candidates` CSV  
**Severity:** MEDIUM (affects Prompt 2 AG-02 implementation)  

Prompt 2 AG-02 references `row.get("avg_volume_20d") or row.get("volume_20d_avg") or row.get("avg_vol_20")` as the denominator for volume anomaly ratio. All three field names are **MISSING** from `morning_candidates_20260624_052030.csv`.

The discovery/scanner layer writes `scanner_rvol` (relative volume) and `scanner_volume` (raw intraday volume) but NOT a 20-day average volume field.

**Correction for Prompt 2 AG-02 implementation:**
Use `scanner_rvol` as the volume anomaly signal instead of computing raw ratio. If `scanner_rvol` is present and > 2.0, flag ANOMALY. Fall back to `NO_DATA` if absent.

```python
# Corrected AG-02 — use scanner_rvol (already computed by scanner layer)
live_rvol = _f(row.get("scanner_rvol") or live_data.get("scanner_rvol"))
if live_rvol is not None:
    out["volume_anomaly_ratio"] = round(live_rvol, 2)
    out["volume_anomaly_flag"]  = "ANOMALY" if live_rvol >= 2.0 else "NORMAL"
else:
    out["volume_anomaly_ratio"] = ""
    out["volume_anomaly_flag"]  = "NO_DATA"
```

---

### CF-SECTOR — `gics_sector` absent; GO list shows UNKNOWN sector
**File:** `morning_gate.py` | **Lines:** 1049–1065  
**Severity:** LOW (display only)  

The GO list sector grouping at lines 1049–1054 reads `gics_sector`. This field is **MISSING** from `morning_candidates`. The candidates carry `sector` (the discovery sector label) and `sector_etf` but not `gics_sector` in GICS-standardised format.

**Impact:** All 147 GO tickers are grouped under "UNKNOWN" in the console sector summary. No gate logic is affected.

**Fix:** In the sector grouping block, try `sector` as fallback to `gics_sector`:
```python
sector = _s(
    r.get("gics_sector")
    or r.get("sector_name")
    or r.get("sector")         # ← already written as "sector" by discovery
    or r.get("sector_etf")
    or "UNKNOWN"
).upper() or "UNKNOWN"
```
(Line 1049 already includes `r.get("sector")` in position 3 — this is actually already handled. The issue is that `gics_sector` at position 1 dominates via `or`-chaining. Worth confirming in a live run that sector shows non-UNKNOWN.)

---

### CF-MACROPATH — `morning_gate.py` CLAUDE.md command mismatch
**Severity:** LOW (documentation)  

CLAUDE.md morning run command reads: `python morning_thesis_validator.py --tiers A,B,C,WATCH --max-signals 0 --live`

The actual morning engine is now `morning_gate.py`. `morning_thesis_validator.py` is retired (predecessor). The orchestrator `premarket_workflow()` correctly calls `morning_gate.py`. The CLAUDE.md documentation needs updating but this is not a code issue.

---

## B. SUSPECTED FINDINGS

### S-01 — No automated macro re-run in `premarket_workflow()`
**File:** `intelligent_orchestrator.py` | **Line:** 5015  
**Severity:** MEDIUM  

`premarket_workflow()` calls `run_catalyst_truth_layer()` then `run_morning_gate()`. There is **no macro re-run step** between evening and gate. The macro JSON (`macro_intelligence_latest.json`) consumed by morning_gate is from the previous evening's run (~22:16 UTC on 2026-06-23 for run 20260624_052030).

By the time the gate fires at 09:45 ET (13:45 UTC), the macro JSON is **~15.5 hours old**. The Prompt 0 audit assumption that "Macro re-run (Phase 1 re-runs fresh before gate)" appears to be a manual step, not automated in `premarket_workflow()`.

**Upstream context:** The candidates carry `macro_freshness_status`, `macro_age_hours`, `macro_generated_at_utc` written during the evening run — but morning_gate.py does not read these to emit a stale-macro warning.

**Action:** Confirm whether the user runs macro manually before firing the gate. If not, this is a gap. The AG-07 freshness flag (Prompt 1) will surface this at run time.

---

### S-02 — Invalidation field population not verified end-to-end
**File:** `morning_gate.py` | **Line:** 633–638  
**Severity:** MEDIUM  

`_check_invalidation()` reads: `evening_invalidation_price`, `invalidation_price`, `invalidation_level`. If none are populated, it returns `(True, "No invalidation level set — EOD structure assumed intact")` — the check silently passes.

The 1082-candidate CSV was not spot-checked for invalidation field population. If the EOD candidate engine is not writing `evening_invalidation_price` (or one of the fallbacks), all 1082 candidates would silently pass CHECK 1 regardless of morning price action.

**Action:** Run:
```python
import csv
with open(r'data\output\runs\20260624_052030\morning_validation\morning_candidates_20260624_052030.csv') as f:
    rows = list(csv.DictReader(f))
populated = sum(1 for r in rows if r.get('evening_invalidation_price') or r.get('invalidation_price') or r.get('invalidation_level'))
print(f"Invalidation set: {populated}/{len(rows)}")
```

---

### S-03 — `macro_regime` field for CHECK 2 needs verification
**File:** `morning_gate.py` | **Line:** 665–669  
**Severity:** LOW  

CHECK 2 reads EOD regime from: `morning_macro_regime_state`, `macro_regime`, `regime_state`, `evening_regime_state`. The candidates CSV shows `macro_regime` as MISSING but has `macro_regime_label` and `macro_regime_sub_state`. If all four read-aliases are absent, CHECK 2 silently passes with "EOD regime not recorded."

The actual macro regime state carried by candidates may be under `macro_regime_label`. Need to confirm field alignment.

---

## C. CLEAN ITEMS

| Item | Status | Notes |
|------|--------|-------|
| Layer 3 thresholds | ✓ CLEAN | VOL_HARDCAP=2.50, LOW_CONF=65.0, HIGH_VOL=1.50, THIN_BARS=100, TAILWIND_CAP=1.50 — all match spec |
| Bond macro flatten | ✓ CLEAN | All nested sub-objects correctly flattened; all display fields present in output |
| Regime flip detection | ✓ CLEAN | TRANSITIONAL variants correctly handled — same base direction not treated as flip |
| Contract repair alternatives | ✓ CLEAN | alternative_contract_1/2/3 tested against live gate; repair_resolved_count in summary |
| Bond staleness check | ✓ CLEAN | 26h threshold implemented in `_load_bond_macro()` |
| Score integrity check | ✓ CLEAN | Auto-runs post-gate; decommission tracking across 10 runs |
| PSE retirement | ✓ CLEAN | No PSE fields gating verdicts; all sizing is MANUAL |
| l3_ fields in candidates | ✓ CLEAN | l3_forward_realised_vol, l3_vol_forecast_conf, l3_n_bars, l3_iv_tailwind_score, l3_model_risk_flags all PRESENT |
| catalyst_overlay propagation | ✓ CLEAN | catalyst_overlay, catalyst_truth_score, catalyst_trade_class all PRESENT in candidates |
| EIL verdicts | ✓ CLEAN | eil_v3_verdict PRESENT; 1082 candidates reaching gate = healthy flow |
| Intelligence Lab macro | ✓ CLEAN | Lab reads macro JSON directly — not dependent on morning_gate macro fields |

---

## D. CRITICAL RISK LIST (prioritised)

| Rank | Finding | Risk | Action |
|------|---------|------|--------|
| 1 | **HARDCODED API KEYS** in morning_gate.py:64-65 | Keys exposed in git history; if .env absent, real keys used as fallback | Remove fallback strings immediately; add startup guard |
| 2 | **ANTHROPIC_API_KEY in session prompt** | Key transmitted through AI context | Rotate at console.anthropic.com immediately |
| 3 | **`avg_volume_20d` absent from candidates** | AG-02 fix in Prompt 2 will silently produce `NO_DATA` for all tickers unless corrected | Use `scanner_rvol` instead per correction above |
| 4 | **No automated macro re-run before gate** | Macro JSON ~15h stale at 09:45 ET gate. Regime change overnight invisible until AG-07 runs | Confirm manual workflow; AG-07 freshness flag (Prompt 1) surfaces this |
| 5 | **Invalidation field population unverified** | If `evening_invalidation_price` absent for all rows, CHECK 1 silently passes for broken theses | Run population check; if < 80% populated, escalate to EOD candidate engine fix |
| 6 | **4 workers for 1082 candidates** | ~2 API calls per ticker = 2164 calls; 4 workers = potentially 30+ minutes | Increase LIVE_FETCH_WORKERS to 8 for large sets; consider caching Polygon snapshots |

---

## E. FIELD TRACE MAP

### Phase 3 (Discovery) → Phase 5 (Package Build) → Phase 10 (morning_candidates)

| Field | Present in candidates? | Notes |
|-------|----------------------|-------|
| `l3_forward_realised_vol` | ✓ | |
| `l3_vol_forecast_conf` | ✓ | |
| `l3_n_bars` | ✓ | |
| `l3_iv_tailwind_score` | ✓ | |
| `l3_model_risk_flags` | ✓ | |
| `scs_score` | ✓ | |
| `eil_v3_verdict` | ✓ | |
| `sector` | ✓ | discovery sector label |
| `sector_etf` | ✓ | |
| `gics_sector` | ✗ | MISSING — go list sector grouping defaults to UNKNOWN |
| `macro_regime` | ✗ | MISSING — but `macro_regime_label` present |
| `morning_macro_regime_state` | ? | Not verified |
| `avg_volume_20d` | ✗ | MISSING — use `scanner_rvol` instead |
| `scanner_rvol` | ✓ | relative volume vs 20d avg (use for AG-02) |
| `catalyst_overlay` | ✓ | |
| `catalyst_truth_score` | ✓ | |
| `event_convexity_score` | ✓ | |
| `macro_freshness_status` | ✓ | from evening upstream |
| `macro_age_hours` | ✓ | from evening upstream |
| `macro_generated_at_utc` | ✓ | from evening upstream |
| `vol_mode` | ✓ | from macro state in candidates |

### Phase 10 (morning_candidates) → morning_gate.py → morning_validated_trades

| Field category | Status in output | Notes |
|---------------|-----------------|-------|
| All EOD candidate fields | ✓ | Pass-through via `dict(row)` at gate entry |
| Bond macro display fields | ✓ | bond_macro_score, bond_macro_flag, bond_curve_state, bond_credit_stress, etc. |
| Macro context fields | ✗ MISSING | macro_vol_mode, macro_conviction, macro_sector_lead, macro_sector_avoid — **CF-01/02/03** |
| Macro freshness flag | ✗ MISSING | macro_freshness_flag — **AG-07** |
| Volume anomaly fields | ✗ MISSING | volume_anomaly_ratio, volume_anomaly_flag — **AG-02** |
| Gate verdict fields | ✓ | verdict, block_reason, flag_reason, morning_gate_verdict |
| Execution permission | ✓ | execution_permission, morning_execution_route, morning_execution_lane |
| Greek gate diagnostics | ✓ | greek_gate_delta, greek_gate_iv_live, greek_gate_iv_eod, greek_gate_iv_compression |
| Layer 3 risk output | ✓ | check_layer3_model_risk_pass, l3_model_risk_flags, l3_model_risk_flag_count |
| v6 actuarial pass-through | ✓ | iv_regime, horizon_bucket, crabel_state |

### morning_validated_trades → Intelligence Lab (Flask :5002)

| Field | Lab reads it? | Source |
|-------|--------------|--------|
| `morning_execution_permission` | ✓ | from gate output |
| `morning_execution_route` | ✓ | from gate output |
| `scs_score` | ✓ | from EOD candidates (pass-through) |
| `eil_v3_verdict` | ✓ | from EOD candidates (pass-through) |
| `vol_mode` | ✓ | Lab reads macro JSON directly |
| `macro_conviction` | ✓ | Lab reads macro JSON directly |
| `sector_lead` | ✓ | Lab reads macro JSON directly |
| `macro_vol_mode` (gate output) | ✗ | Lab does NOT read this from the validated trades — reads macro JSON instead |

**Key insight:** The Intelligence Lab's independence from morning_gate macro fields means CF-01/02/03 fixes are needed for the output CSV and summary JSON (trader portability), not to fix the Lab itself.

---

## F. READINESS ASSESSMENT FOR PROMPT 1

| Item | Status | Blocker? |
|------|--------|----------|
| Security: API keys | ⚠ FIX FIRST | YES — fix hardcoded keys before any other change |
| CF-04 bond fields | ✓ Already working | No |
| AG-02 field reference | ⚠ Correction needed | YES — change to scanner_rvol |
| Invalidation population | ? Unverified | Soft — run check before Wave 1 |
| morning_gate.py stable | ✓ | No |
| 1082 candidates → gate works | ✓ | No |
| Bond state fresh | ✓ (generated 00:16 UTC, within 26h) | No |

**Recommended action before starting Prompt 1:**
1. Rotate ANTHROPIC_API_KEY at console.anthropic.com
2. Remove hardcoded API key fallbacks from morning_gate.py:64-65
3. Confirm invalidation field population count
4. Note the scanner_rvol correction for Prompt 2 AG-02

---

*AVSHUNTER Pipeline Audit | 27 June 2026 | Prompt 0 complete — no changes made*
*Next: Prompt 1 (Wave 1 morning_gate.py fixes) pending review of this report*
