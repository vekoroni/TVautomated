# AVSHUNTER — Fix Implementation Specification
**Date:** 21 May 2026 | **Run:** 20260521_010742 | **Audit:** All 10 fixes FAIL
**Purpose:** Exact file-level implementation instructions for each confirmed fix.
**Do not troubleshoot daily until all 10 are deployed.**

---

## FIX 1 — EOD_DIRECTION_CONFLICT_REVIEW Must Pass to Morning Validator
**Files:** `eod_candidate_engine.py` (line ~864) + `morning_thesis_validator.py` (line ~1100)
**Evidence:** 4 of 6 candidates killed before morning validation. 0 GO signals.

### eod_candidate_engine.py — line ~864

Find the block that assigns `EOD_DIRECTION_CONFLICT_REVIEW` status. It currently
prevents the row from being passed forward. Change it to pass with a flag:

```python
# BEFORE (current — kills ticker)
if direction_conflict:
    candidate["eod_status"] = "EOD_DIRECTION_CONFLICT_REVIEW"
    candidate["pass_to_morning"] = False

# AFTER (required — passes with flag)
if direction_conflict:
    candidate["eod_status"] = "EOD_TRIGGER_READY"          # promote to passable
    candidate["direction_conflict_flag"] = True
    candidate["direction_conflict_note"] = (
        f"Conflict: {conflict_source_a} says {dir_a}, "
        f"{conflict_source_b} says {dir_b}. "
        f"Primary direction: {resolved_primary_direction}. "
        "Trader to verify at open."
    )
    candidate["pass_to_morning"] = True
```

Resolution of `resolved_primary_direction`:
Weight by horizon. If 6-10d or 11-20d: prefer Vanguard StateVector direction.
If 1-5d: prefer EIL direction. If both agree on neither: use options flow direction
from Options Intelligence `selected_contract_side` field.

### morning_thesis_validator.py — line ~1100

Find the status filter that only accepts `EOD_TRIGGER_READY`. Add acceptance of
conflict-flagged rows:

```python
# BEFORE
ACCEPTED_EOD_STATUSES = {"EOD_TRIGGER_READY"}

# AFTER
ACCEPTED_EOD_STATUSES = {"EOD_TRIGGER_READY"}
# Conflict rows now arrive as EOD_TRIGGER_READY with direction_conflict_flag=True
# Validator reads the flag and adds to morning output:
if row.get("direction_conflict_flag"):
    row["morning_note"] = row.get("direction_conflict_note", "Direction conflict — verify at open")
    row["morning_verdict"] = "PROBE"  # not GO — trader must resolve
```

**Test:** Re-run pipeline. candidate_status should show 0 `EOD_DIRECTION_CONFLICT_REVIEW`,
6 `EOD_TRIGGER_READY`. Morning validation should receive 6 candidates.

---

## FIX 2 — WATCH_FOR_REGIME_FLIP Must Route to Rolling Watch Lane, Not Shadow Book
**Files:** `eod_candidate_engine.py` + `morning_thesis_validator.py`
**Evidence:** 662 shadow rows. None reach morning validation.

### eod_candidate_engine.py

Find where `WATCH_FOR_REGIME_FLIP` label is assigned and the row is written
to the shadow book. Add a parallel write to a regime_watch output:

```python
# BEFORE
if opportunity_label == "WATCH_FOR_REGIME_FLIP":
    write_to_shadow_book(row)   # only destination — invisible to morning

# AFTER
if opportunity_label == "WATCH_FOR_REGIME_FLIP":
    write_to_shadow_book(row)   # keep for audit trail

    # Route to rolling watch lane
    row["eod_status"]        = "REGIME_WATCH"
    row["horizon"]           = assign_horizon(row)       # 6-10d or 11-20d
    row["watch_condition"]   = extract_flip_condition(row)  # what triggers upgrade
    row["watch_since"]       = today_date()
    write_to_regime_watch_csv(row)   # new output file
```

New output file path (create if not exists):
```
data/output/runs/{run_id}/morning_validation/regime_watch_{run_id}.csv
```

### morning_thesis_validator.py

Add a second input read for the regime_watch CSV. For each REGIME_WATCH ticker,
apply a daily flip check:

```python
# Add after reading morning_candidates:
regime_watch_path = run_dir / "morning_validation" / f"regime_watch_{run_id}.csv"
if regime_watch_path.exists():
    regime_watch_rows = read_csv(regime_watch_path)
    for row in regime_watch_rows:
        # Daily flip check — has the condition been met?
        flip_result = check_regime_flip(row, live_macro, live_price)
        if flip_result == "FLIPPED":
            row["morning_verdict"]    = "ARMED"
            row["morning_note"]       = "Regime flip confirmed — thesis activated"
            row["tradeable_today"]    = True
        elif flip_result == "APPROACHING":
            row["morning_verdict"]    = "WATCH"
            row["morning_note"]       = "Regime flip approaching — monitor"
            row["tradeable_today"]    = False
        else:
            row["morning_verdict"]    = "WATCH"
            row["morning_note"]       = "Regime flip not yet confirmed — carry forward"
            row["tradeable_today"]    = False
        # Add to morning output regardless of flip status
        morning_output.append(row)
```

`check_regime_flip(row, live_macro, live_price)` logic:
- Compare current `regime_state` in `macro_intelligence_latest.json` to the
  `watch_condition` field stored when the row was shadow-booked.
- If states differ → FLIPPED
- If conviction has moved >0.1 toward flip direction → APPROACHING
- Otherwise → HOLDING

**Test:** Morning output should include REGIME_WATCH rows. Some subset will
be ARMED or WATCH depending on daily macro. 662 rows → rolling watchlist
that grows each session.

---

## FIX 3 — Discovery Must Route by Horizon, Not Filter on Current Alignment
**Files:** `discovery_candidates.py` (or equivalent discovery phase script)
**Evidence:** 1,611 dropped BETWEEN_UNIVERSE_AND_DISCOVERY. 26 HIGH_FALSE_NEGATIVE_RISK.

### discovery_candidates.py

Find the primary filter condition. Current logic discards tickers without
current phase alignment. Replace with a three-horizon router:

```python
# BEFORE — binary filter
if not has_current_phase_alignment(ticker):
    dropoff_reason = "UNIVERSE_TICKER_NOT_SELECTED_BY_DISCOVERY"
    log_dropoff(ticker, dropoff_reason)
    continue   # discarded

# AFTER — three-horizon router
horizon = assign_discovery_horizon(ticker)

if horizon == "1_5d":
    # Current edge confirmed — proceed at full priority
    row["horizon_bucket"]  = "1_5d"
    row["discovery_basis"] = "CURRENT_PHASE_ALIGNMENT"

elif horizon == "6_10d":
    # Structural setup building — pass with FUTURE_EDGE tag
    row["horizon_bucket"]      = "6_10d"
    row["discovery_basis"]     = "STRUCTURAL_SETUP_BUILDING"
    row["opportunity_label"]   = "WATCH_FOR_REGIME_FLIP"  # triggers Fix 2 routing

elif horizon == "11_20d":
    # Regime transition signal — pass as long-horizon watch
    row["horizon_bucket"]      = "11_20d"
    row["discovery_basis"]     = "REGIME_TRANSITION_SIGNAL"
    row["opportunity_label"]   = "WATCH_FOR_REGIME_FLIP"

else:
    # Genuine no-signal — only legitimate discard
    dropoff_reason = "NO_SIGNAL_AT_ANY_HORIZON"
    log_dropoff(ticker, dropoff_reason)
    continue
```

`assign_discovery_horizon(ticker)` logic:
```python
def assign_discovery_horizon(ticker) -> str:
    if has_current_phase_alignment(ticker) and has_immediate_trigger(ticker):
        return "1_5d"
    if has_structural_setup(ticker) or has_actuarial_match(ticker):
        return "6_10d"
    if has_regime_transition_signal(ticker) or macro_sector_tailwind(ticker):
        return "11_20d"
    return None   # genuine no-signal
```

**Downstream requirement:** Every subsequent phase must read `horizon_bucket`
and apply horizon-appropriate thresholds. See Fix 4 for Options Intelligence.

**Test:** UNIVERSE_TICKER_NOT_SELECTED_BY_DISCOVERY count should drop significantly.
26 HIGH_FALSE_NEGATIVE_RISK tickers should now pass with 6-10d or 11-20d horizon tags.

---

## FIX 4 — Options Intelligence Must Be Horizon-Aware + Tiered Gates
**Files:** `options_intelligence.py` (or equivalent options phase script)
**Evidence:** 675 killed by "No contract passed quality gates". Binary gate confirmed.

### options_intelligence.py

**Part A — Horizon-aware DTE selection**

Find where DTE window is defined. Add horizon-aware config:

```python
# BEFORE — single fixed window (causes wrong-DTE rejection of 6-10d/11-20d tickers)
DTE_MIN = 7
DTE_MAX = 21

# AFTER — horizon-aware config
DTE_CONFIG = {
    "1_5d":   {"dte_min": 7,  "dte_max": 21, "spread_max": 0.15, "delta_min": 0.40, "delta_max": 0.60},
    "6_10d":  {"dte_min": 21, "dte_max": 35, "spread_max": 0.25, "delta_min": 0.35, "delta_max": 0.55},
    "11_20d": {"dte_min": 35, "dte_max": 60, "spread_max": 0.35, "delta_min": 0.30, "delta_max": 0.50},
}
horizon = row.get("horizon_bucket", "1_5d")
cfg     = DTE_CONFIG.get(horizon, DTE_CONFIG["1_5d"])
```

**Part B — Replace binary gate with tiered review**

Find the contract quality gate. Replace the hard discard:

```python
# BEFORE — binary discard
contracts = filter_contracts(chain, cfg)
if not contracts:
    row["options_verdict"]  = "NO_CONTRACT"
    row["dropoff_reason"]   = "No contract passed quality gates"
    continue   # ticker killed

# AFTER — tiered review
contracts_clean     = filter_contracts(chain, cfg, strict=True)
contracts_relaxed   = filter_contracts(chain, cfg, strict=False)
contracts_any       = get_any_contract(chain, cfg)

if contracts_clean:
    row["contract_tier"]    = "CLEAN"
    row["contract_flag"]    = None

elif contracts_relaxed:
    row["contract_tier"]    = "REVIEW_SPREAD"
    row["contract_flag"]    = "Spread outside threshold — verify at open before entry"
    row["spread_check"]     = True

elif contracts_any:
    row["contract_tier"]    = "REVIEW_COMPOUND"
    row["contract_flag"]    = "Multiple parameters marginal — full contract review at open"

elif chain_data_exists(ticker):
    row["contract_tier"]    = "REVIEW_NO_PASS"
    row["contract_flag"]    = "No contract passed any threshold — trader review required"

else:
    # ONLY legitimate hard discard — no chain data at all
    row["options_verdict"]  = "NO_CHAIN_DATA"
    row["dropoff_reason"]   = "No options chain data available — not an options-tradeable name"
    log_dropoff_with_reason(ticker, "NO_CHAIN_DATA")
    continue

# All non-DISCARD rows pass forward regardless of tier
row["options_verdict"] = "PASS_WITH_FLAGS" if row.get("contract_tier") != "CLEAN" else "PASS"
```

**Part C — Add contract rejection log**

After evaluating each contract, write a rejection log entry:

```python
# Write to: data/output/runs/{run_id}/options/contract_rejection_log_{run_id}.csv
rejection_log.append({
    "ticker":           ticker,
    "contract":         contract_label,
    "horizon":          horizon,
    "rejection_reason": rejection_reason,   # SPREAD_TOO_WIDE / DELTA_OUT_OF_BAND / DTE_MISMATCH / VOLUME_BELOW_MIN
    "value":            failing_value,
    "threshold":        applicable_threshold,
    "dte_scanned_min":  cfg["dte_min"],
    "dte_scanned_max":  cfg["dte_max"],
})
```

**Test:** `no_contract_quality` count should drop from 675 toward ~25 (genuine no-chain cases).
`options_verdict` distribution should show PASS + PASS_WITH_FLAGS tiers, not STAND_DOWN dominance.

---

## FIX 5 — Capital Gate Must Not Kill Tickers When PSE Is Retired
**Files:** `execution_v3_5.py` (or equivalent execution phase script)
**Evidence:** 337 ZERO_CAPITAL_PERMISSION_AFTER_EXECUTION_GATE. PSE retired but gate still fires.

### execution_v3_5.py

Find any block that sets `capital_permission = 0` or `tradeable = False`
based on PSE or Kelly sizing calculations:

```python
# SEARCH FOR these patterns and remove/replace each:
#   if kelly_size == 0:
#   if pse_permission == 0:
#   if capital_permission == 0:
#   capital_permission = 0
#   ZERO_CAPITAL_PERMISSION

# REPLACE WITH:
row["capital_permission"]  = "MANUAL"   # PSE retired — trader decides size
row["tradeable"]           = True
row["size_note"]           = (
    "Manual sizing required. "
    "PSE retired 2026-04. "
    "Apply 0.5x standard size per current macro regime. "
    "Trader must confirm size before entry."
)
```

Also find the dropoff accounting that logs `ZERO_CAPITAL_PERMISSION_AFTER_EXECUTION_GATE`.
Keep the log entry but change the behaviour:

```python
# BEFORE
if capital_permission == 0:
    log_dropoff("ZERO_CAPITAL_PERMISSION_AFTER_EXECUTION_GATE")
    continue   # kills ticker

# AFTER
if legacy_pse_capital == 0:
    log_note("PSE_LEGACY_ZERO_SIZE — PSE retired, passing with MANUAL sizing")
    row["capital_permission"] = "MANUAL"
    # Do NOT continue — row passes forward
```

**Test:** `zero_capital_dropoff` should drop from 337 to 0.
`cap` distribution should show `MANUAL` instead of `WATCH_ONLY` / `NO`.

---

## FIX 6 — Morning Validator Must Output Horizon-Aware Thesis Fields
**Files:** `morning_thesis_validator.py`
**Evidence:** Output is binary BLOCKED/CONTRACT_REPAIR. Missing thesis_still_valid,
morning_verdict, tradeable_today, feeds_interpreter.

### morning_thesis_validator.py

**Part A — Add new output fields to every row**

Find where the morning output row is assembled. Add required fields:

```python
# Add to morning output row construction:
output_row.update({
    # Thesis continuity
    "thesis_still_valid":    assess_thesis_continuity(row, live_price, live_macro),
    "thesis_delta":          describe_thesis_delta(row, live_price, live_macro),
    "horizon":               row.get("horizon_bucket", "1_5d"),

    # Verdict (replaces binary BLOCKED/GO)
    "morning_verdict":       compute_morning_verdict(row, live_price, live_macro),
    # Values: EXECUTE / ARMED / WATCH / WAIT / DEAD / PROBE

    # Tradeable
    "tradeable_today":       is_tradeable_today(row, live_price),
    "tradeable_reason":      get_tradeable_reason(row, live_price),

    # Interpreter flag
    "feeds_interpreter":     row.get("thesis_still_valid", False) and not is_dead(row),
})
```

**Part B — Macro must not be a hard gate; scope it correctly**

Find the macro filter block. Replace hard gate with weighted evidence:

```python
# BEFORE — macro kills ticker regardless of horizon
if macro_filter == "NO_GO":
    row["verdict"] = "BLOCKED"
    row["rejection_reason"] = "Macro filter is NO_GO..."
    continue   # hard block

# AFTER — macro is one weighted input
macro_score = score_macro_for_horizon(macro_data, row["horizon_bucket"])
# macro_score: 0.0 (full headwind) to 1.0 (full tailwind)
# For 6-10d / 11-20d: only block on STATE CHANGE, not conviction level
# TRANSITIONAL_BULLISH + TRANSITIONAL_BULLISH = NOT a state change = not a block

macro_state_changed = (
    macro_data.get("regime_state") != row.get("evening_regime_state")
)
if macro_state_changed and new_state in ("RISK_OFF", "CRISIS"):
    row["morning_verdict"] = "DEAD"
    row["thesis_delta"]    = f"Macro regime changed overnight: {old_state} → {new_state}"
else:
    # Macro is a flag, not a gate
    row["macro_note"]  = f"Macro: {macro_data.get('regime_state')} conviction={macro_data.get('macro_conviction')}"
    row["macro_weight"] = macro_score
    # Continue to thesis assessment
```

**Part C — Horizon-specific morning questions**

```python
def compute_morning_verdict(row, live_price, live_macro) -> str:
    horizon = row.get("horizon_bucket", "1_5d")

    if horizon == "1_5d":
        trigger_hit  = price_near_trigger(live_price, row.get("trigger_level"))
        invalid      = price_breached_invalidation(live_price, row.get("invalidation_level"))
        if invalid:           return "DEAD"
        if trigger_hit:       return "EXECUTE"
        if opening_confirmed: return "ARMED"
        return "WAIT"

    elif horizon == "6_10d":
        regime_flipped = check_regime_flip(row, live_macro)
        setup_intact   = structural_setup_intact(row, live_price)
        if not setup_intact:  return "DEAD"
        if regime_flipped:    return "ARMED"
        return "WATCH"

    elif horizon == "11_20d":
        state_changed = macro_state_changed_overnight(row, live_macro)
        if state_changed:     return "DEAD"
        return "HOLD"   # carry forward until regime develops

    return "WAIT"
```

**Test:** Morning output rows should have all new fields populated.
`feeds_interpreter` = True for ARMED/WATCH/EXECUTE rows.
Macro NO_GO alone should no longer produce BLOCKED.

---

## FIX 7 — Catalyst Overlay Must Propagate End-to-End
**Files:** `catalyst_truth.py` + `options_intelligence.py` + `eil_enriched` stage
+ `morning_thesis_validator.py`
**Evidence:** catalyst_overlay fill_rate = 0.0 across all 6 stages.
**Root cause:** catalyst_truth patch runs before morning_candidates is written.

### Step 1 — Fix patch sequence ordering

In `intelligent_orchestrator.py` (or equivalent), find where catalyst_truth
runs relative to morning_candidates write:

```python
# BEFORE (wrong order)
run_catalyst_truth()          # patches files that exist
write_morning_candidates()    # written after patch — never patched
run_morning_validator()

# AFTER (correct order)
write_morning_candidates()    # write first
run_catalyst_truth()          # now patches morning_candidates correctly
run_morning_validator()       # reads patched file
```

### Step 2 — Propagate catalyst fields at each stage

At Options Intelligence, EIL, and Execution stages, add explicit catalyst carry-forward:

```python
# At each stage that reads from previous stage output:
CATALYST_FIELDS = [
    "catalyst_overlay",
    "catalyst_truth_score",
    "event_convexity_score",
    "catalyst_trade_class",
    "catalyst_date",
    "catalyst_type",
    "cheap_convexity",
    "catalyst_reason_codes",
]

for field in CATALYST_FIELDS:
    if field not in output_row and field in input_row:
        output_row[field] = input_row[field]
```

Add this carry-forward block to:
- `options_intelligence.py` output row assembly
- `eil_enriched` output row assembly
- `execution_v3_5.py` output row assembly
- `morning_thesis_validator.py` output row assembly

### Step 3 — Add EVENT_CONVEXITY_WATCH to morning verdict logic

```python
# In morning_thesis_validator.py verdict logic:
if row.get("catalyst_trade_class") == "EVENT_CONVEXITY_WATCH":
    if row.get("cheap_convexity") == True:
        row["morning_verdict"]  = "ARMED"
        row["morning_note"]    += " EVENT_CONVEXITY_WATCH with cheap_convexity — priority review"
```

**Test:** catalyst_overlay fill_rate should be >0 at all stages.
TJX EVENT_CONVEXITY_WATCH should appear in morning output with ARMED verdict.

---

## FIX 8 — Single Macro Snapshot Source of Truth
**Files:** `intelligent_orchestrator.py` + `normalise_macro_contract.py`
**Evidence:** Run snapshot = TRANSITIONAL_BEARISH/0.38. Latest macro = TRANSITIONAL_BULLISH/0.52.
Two different macro states driving contradictory decisions in the same session.

### intelligent_orchestrator.py

At Phase 0 Preflight, after macro normalisation is complete, write the
resolved macro state to the run folder and lock it:

```python
# Add at end of Phase 0 / start of Phase 1:
RUN_MACRO_SNAPSHOT = run_dir / "macro_snapshot.json"

# Write run-locked snapshot from macro_intelligence_latest.json
shutil.copy2(MACRO_LATEST_PATH, RUN_MACRO_SNAPSHOT)

# Write a metadata record so auditing can trace which file was used
run_meta["macro_snapshot_source"]   = str(MACRO_LATEST_PATH)
run_meta["macro_snapshot_locked_at"] = utc_now()
run_meta["macro_regime_at_lock"]    = read_regime_state(MACRO_LATEST_PATH)
```

All downstream pipeline phases must read from `RUN_MACRO_SNAPSHOT`, not from
`macro_intelligence_latest.json` directly. This prevents the morning run of
the macro update from changing the regime state that the evening run was scored on.

### morning_thesis_validator.py

Morning validator is the exception — it SHOULD read the latest macro to check
for overnight state changes. Add explicit labelling:

```python
# Morning validator reads BOTH:
evening_macro = load_json(RUN_MACRO_SNAPSHOT)         # what the evening used
morning_macro = load_json(MACRO_INTELLIGENCE_LATEST)  # current state

# Label both in output:
output_row["evening_regime_state"]   = evening_macro.get("regime_state")
output_row["morning_regime_state"]   = morning_macro.get("regime_state")
output_row["macro_state_changed"]    = (
    evening_macro.get("regime_state") != morning_macro.get("regime_state")
)
```

**Test:** Run snapshot and latest macro should be clearly labelled.
`macro_state_changed` field should appear in morning output rows.
Downstream diagnostics should read `macro_snapshot.json` for EOD regime,
not `macro_intelligence_latest.json`.

---

## FIX 9 — crowd_arrival_components Must Survive to Morning Validation
**Files:** Wherever `crowd_arrival_components` is computed (likely SuperBrain/WBS stage)
+ `morning_thesis_validator.py`
**Evidence:** candidates 3/6 populated, validated 0/2. Field drops between EOD and MV.

### morning_thesis_validator.py

Find where the morning output row is assembled from the candidate row.
Add explicit preservation of crowd_arrival_components:

```python
# In morning output row assembly — add to the carry-forward block:
PRESERVE_FIELDS = [
    "crowd_arrival_components",
    "crowd_arrival_state",
    "crowd_arrival_narrative",
    "wbs_score",
    "wbs_grade",
    "wall_break_score",
]
for field in PRESERVE_FIELDS:
    if field in candidate_row and candidate_row[field]:
        morning_row[field] = candidate_row[field]
```

Also check whether `morning_thesis_validator.py` rebuilds the output row from
scratch (discarding upstream fields) rather than mutating the candidate row.
If it rebuilds from scratch, change to:

```python
# BEFORE — rebuild from scratch (loses upstream fields)
morning_row = {
    "ticker":   candidate["ticker"],
    "verdict":  compute_verdict(candidate),
    # ... only explicitly listed fields
}

# AFTER — start from candidate row, then add morning-specific fields
morning_row = dict(candidate)   # preserve ALL upstream fields
morning_row.update({
    "morning_verdict":    compute_morning_verdict(candidate, live_price, live_macro),
    "tradeable_today":    is_tradeable_today(candidate, live_price),
    "thesis_still_valid": assess_thesis_continuity(candidate, live_price, live_macro),
    # ... morning-specific additions only
})
```

**Test:** `crowd_arrival_components` fill in morning validation should be >0.
For the 3 candidates that had it in EOD, all 3 should carry it through.

---

## FIX 10 — options_hard_vetoes Must Be Populated in Handoff
**Files:** `options_intelligence.py` + `morning_thesis_validator.py`
**Evidence:** options_hard_vetoes present upstream but empty in final candidate/morning handoff.
Note: catalyst_truth confirmed earnings dates are available — use them here.

### options_intelligence.py

Add hard veto population at contract selection time:

```python
# Add to options row assembly:
hard_vetoes = []

# Earnings within DTE window
if has_earnings_within_dte(ticker, contract_dte, catalyst_data):
    hard_vetoes.append({
        "veto_type":  "EARNINGS_WITHIN_DTE",
        "event_date": get_earnings_date(ticker, catalyst_data),
        "note":       f"Earnings on {earnings_date} — inside {contract_dte} DTE window"
    })

# Binary FDA/regulatory event
if has_binary_event_within_dte(ticker, contract_dte, catalyst_data):
    hard_vetoes.append({
        "veto_type":  "BINARY_EVENT_WITHIN_DTE",
        "event_date": get_binary_event_date(ticker, catalyst_data),
        "note":       "Binary catalyst event within DTE — high premium risk"
    })

# No options market (genuine)
if not options_market_exists(ticker):
    hard_vetoes.append({
        "veto_type": "NO_OPTIONS_MARKET",
        "note":      "No listed options — equity-only name"
    })

row["options_hard_vetoes"] = json.dumps(hard_vetoes) if hard_vetoes else "[]"
row["hard_vetoes"]         = row["options_hard_vetoes"]   # alias for handoff contract
```

### morning_thesis_validator.py

Read hard_vetoes in the morning verdict logic:

```python
# In verdict computation:
hard_vetoes = json.loads(row.get("options_hard_vetoes", "[]") or "[]")
earnings_veto = any(v["veto_type"] == "EARNINGS_WITHIN_DTE" for v in hard_vetoes)

if earnings_veto:
    row["morning_note"] += " ⚠ EARNINGS WITHIN DTE WINDOW — defined-risk structures only"
    # Do NOT auto-block — inform trader, let them decide
    # Only block if the veto type is a genuine structure risk (e.g. no options market)
```

**Test:** `options_hard_vetoes` fill should be >0 in options_intelligence output.
Hard vetoes should carry through to morning_candidates and morning_validated.

---

## DEPLOYMENT ORDER

Implement all 10 fixes in a single session without stopping.
Run the audit script after each fix. Do not proceed until the current fix shows PASS.

```
PHASE 1 — Foundation (no dependencies)
  Fix 8  intelligent_orchestrator.py + morning_thesis_validator.py
         (single macro snapshot — foundational for Fix 2 and Fix 6)

PHASE 2 — Candidate flow (enables all downstream fixes)
  Fix 1  eod_candidate_engine.py + morning_thesis_validator.py
         (direction conflict pass-through)
  Fix 5  execution_v3_5.py
         (retire PSE capital gate)

PHASE 3 — Catalyst and data quality (independent, run after Phase 2)
  Fix 7  intelligent_orchestrator.py + all stage scripts
         (catalyst patch sequence reorder + carry-forward)
  Fix 10 options_intelligence.py + morning_thesis_validator.py
         (hard vetoes population)
  Fix 9  morning_thesis_validator.py
         (crowd_arrival carry-forward block)

PHASE 4 — Horizon architecture (Fix 3 must precede Fix 4)
  Fix 2  eod_candidate_engine.py + morning_thesis_validator.py
         (WATCH_FOR_REGIME_FLIP routing to watch lane)
  Fix 3  discovery_candidates.py
         (three-horizon router — horizon tags flow downstream from here)
  Fix 4  options_intelligence.py
         (horizon-aware DTE + tiered contract gates — requires Fix 3 tags)

PHASE 5 — Morning validator redesign (requires Fix 3 + Fix 8 both complete)
  Fix 6  morning_thesis_validator.py
         (full horizon-aware thesis revalidator)

FINAL — Re-run audit script
  powershell -ExecutionPolicy Bypass -File Audit_AVSHUNTER_CompleteFixList_20260521.ps1
  All 10 checks must show PASS.
```

---

## AUDIT RE-RUN TARGETS

After all fixes, the audit script should show:

| Fix | Current | Target |
|-----|---------|--------|
| Fix 1 | EOD_DIRECTION_CONFLICT_REVIEW: 4 | 0 direction conflicts killing candidates |
| Fix 2 | WATCH_FOR_REGIME_FLIP shadow: 662 | 662 routing to regime_watch lane |
| Fix 3 | universe_to_discovery: 1,611 | <500 (legitimate no-signal discards only) |
| Fix 4 | no_contract_quality: 675 | <30 (genuine no-chain-data discards only) |
| Fix 5 | zero_capital_dropoff: 337 | 0 |
| Fix 6 | rows: 2, binary verdicts | rows: 15+, thesis fields populated |
| Fix 7 | catalyst fill: 0/1354 | fill >0 at all stages, TJX ARMED |
| Fix 8 | two contradictory states | single resolved snapshot + labelled delta |
| Fix 9 | crowd_arrival MV: 0/2 | 0/2 → all candidates carry field through |
| Fix 10 | hard_vetoes: 0/6 | hard_vetoes populated where earnings within DTE |

---

*AVSHUNTER Fix Implementation Specification | 21 May 2026*
*The machine discovers. The narrative diagnoses. The market permits. The trader executes.*
