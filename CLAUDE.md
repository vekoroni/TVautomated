# AVSHUNTER Enhancement Build — Claude Code Developer Prompt
**Version:** 1.0  
**Date:** June 2026  
**Author:** ACK Verissimo / Makeo Consulting Limited  
**Classification:** INTERNAL — PROPRIETARY PIPELINE

---

## CONTEXT: READ THIS FIRST

You are a senior Python developer working on **AVSHUNTER**, a proprietary systematic options trading pipeline running live with real capital on Tastytrade. The pipeline is built in Python and runs locally on Windows.

**Base directory:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\`

**Critical operating rules — non-negotiable:**
- The pipeline is ADVISORY only. It does not place trades autonomously.
- `tastytrade_client.py` is a non-trading placeholder — do not modify it.
- `tradeable=False` after the evening run is CORRECT by design. Do not change this.
- All sizing decisions remain with the human trader. PSE is retired.
- API keys (POLYGON_API_KEY, MARKETDATA_API_KEY, ANTHROPIC_API_KEY) are in `.env` — never hardcode, never print, never reproduce them.
- Before modifying any existing file, read it in full first. Confirm the exact insertion point. Do not rewrite files that are not in scope.
- After every change, run a null-signal regression test: GO count must remain within 10% of the pre-change baseline. If it drops further, rollback immediately.

**Pipeline phase sequence (for context):**
```
Phase 0  → Preflight
Phase 1  → Macro Normalisation
Phase 2  → Actuarial Cache
Phase 3  → Discovery (avshunter_discovery_signals.py)
Phase 4  → External Intel / Macro Enrichment
Phase 5  → Package Build / Backfill
Phase 6  → Vanguard
Phase 7  → Options Intelligence (avshunter_options_intelligence.py)
Phase 8  → SuperBrain / WBS / EIL (avshunter_superbrain_layer.py)
Phase 8.6b → Trigger Layer (trigger_layer.py)
Phase 9  → GARCH
Phase 10 → Handoff Guard / Catalyst Truth / Morning Manifest
Phase 11 → Diagnostics / Archive
```

**Evening run command:**
```powershell
cd C:\Users\ACKVerissimo\AVSHUNTER-Intelligence
python intelligent_orchestrator.py --evening --data-mode EOD
```

**Morning run command:**
```powershell
python morning_thesis_validator.py --tiers A,B,C,WATCH --max-signals 0 --live
```

---

## SPRINT 1 — EXIT DISCIPLINE ENGINE
**Priority: HIGHEST — This is the most impactful single addition to the pipeline**

### Business Problem
AVSHUNTER currently has no systematic exit signal layer. Trades that reach 100–120% gain in premium (confirmed in the live PYPL post-mortem) are held past their optimal exit point, theta decays, and winners convert to losers or full losses. The PYPL trade expired worthless after showing 120% P&L at peak. This is the primary reason realised R:R falls below the 2.5R target.

### What to Build
Create a new module: `avshunter_exit_engine.py`

This module reads the `morning_validated_trades.csv` output from `morning_thesis_validator.py` and cross-references it against open positions in the trade journal (`avshunter_trade_journal.py` / SQLite database). For each open position it produces an exit signal with a verdict and action.

**Exit verdict states:**
- `TAKE_PARTIAL` — Take 50% off now. Premium is at or above 1R gain. Locks in basis. Remaining half plays to target.
- `TAKE_FULL` — Exit entire position. Time stop breached, OR premium at 80%+ gain, OR thesis integrity failed, OR IV crush imminent.
- `TRAIL` — Position at 1R+, thesis intact, hold remainder with trailing logic active.
- `HOLD` — No action. Position within normal parameters.
- `EMERGENCY_EXIT` — Immediate exit. Wall broken against thesis, macro regime flipped adverse, or DTE < 5 with position underwater.

**Exit trigger logic (implement in this order — do not skip any):**

```
TRIGGER 1 — Time Stop (highest priority, always fires first)
  IF (DTE at entry - days held) <= 5 → TAKE_FULL regardless of P&L
  IF days_held > (DTE_at_entry * 0.75) → TAKE_PARTIAL minimum

TRIGGER 2 — Profit Capture
  IF current_premium >= entry_premium * 2.0 (i.e. 100% gain = 1R)
    → TAKE_PARTIAL (exit 50%, set trail on remainder)
  IF current_premium >= entry_premium * 3.5 (i.e. 150% gain = 2.5R target)  
    → TAKE_FULL (target achieved)
  IF current_premium >= entry_premium * 1.5 AND days_held > 10
    → TAKE_PARTIAL (front-loaded edge window closing)

TRIGGER 3 — Thesis Integrity
  IF wyckoff_phase changed from entry phase → TAKE_FULL
  IF control_state changed to ADVERSE vs entry direction → TAKE_FULL
  IF morning_gate verdict = BLOCKED or WAIT on this ticker → TAKE_FULL

TRIGGER 4 — IV Crush Warning
  IF IVP > 70 AND dte_remaining <= 10 → TAKE_FULL (IV crush imminent)
  IF iv_hv_ratio > 1.5 AND days_held > 5 → TAKE_PARTIAL

TRIGGER 5 — Wall Dynamics
  IF call_wall migrated BELOW current price (for CALL positions) → EMERGENCY_EXIT
  IF put_wall migrated ABOVE current price (for PUT positions) → EMERGENCY_EXIT
```

**Output fields per position:**
```python
{
  "ticker": str,
  "trade_id": int,
  "direction": str,           # CALL or PUT
  "entry_premium": float,
  "current_premium": float,   # from morning live data
  "gain_pct": float,          # (current - entry) / entry
  "days_held": int,
  "dte_remaining": int,
  "exit_verdict": str,        # TAKE_PARTIAL / TAKE_FULL / TRAIL / HOLD / EMERGENCY_EXIT
  "exit_trigger": str,        # which trigger fired e.g. TRIGGER_1_TIME_STOP
  "exit_size_pct": float,     # 0.5 for TAKE_PARTIAL, 1.0 for TAKE_FULL, 0.0 for HOLD
  "reason": str,              # plain English explanation
  "urgency": str,             # TODAY / THIS_WEEK / MONITOR
  "r_realised": float,        # gain expressed as R multiple
  "r_remaining": float        # remaining potential R if trailing
}
```

**Integration point:**  
Add as a post-processing step in `morning_thesis_validator.py` after the morning validated trades CSV is written. Write output to:
`data\output\runs\<run_id>\morning_exit_signals.csv`

**Journal integration:**  
When `TAKE_PARTIAL` or `TAKE_FULL` fires, the exit engine must write a suggested `log-exit` command to the console:
```
SUGGESTED EXIT COMMAND:
python avshunter_trade_journal.py log-exit --trade-id 13 --exit-premium 0.18 --exit-reason "TRIGGER_2_PROFIT_CAPTURE — 1R achieved"
```

**Constraints:**
- Read-only access to the trade journal database during morning run. Do not write to it automatically. The human confirms the exit and runs the log-exit command manually.
- If `current_premium` is not available from live data, set `exit_verdict = DATA_UNAVAILABLE` and skip that position. Never exit based on stale data.
- If the trade journal returns zero open positions, exit gracefully with a log message. Do not error.

---

## SPRINT 2 — CONVEXITY STRIKE MAP™
**Priority: HIGH**

### Business Problem
The pipeline selects options signals but does not synthesise the underlying payoff geometry into a unified per-contract recommendation. A structurally valid 3R setup can produce only 1R if the wrong contract is selected. The existing components (CCR score, delta efficiency, DTE, gamma wall runway, IV crush state) all exist in Options Intelligence but are not combined into a single ranked contract output.

### What to Build
Add a new function `build_convexity_strike_map()` to `avshunter_options_intelligence.py`.

This function runs after the existing options scoring and produces a ranked contract recommendation with the following fields:

**Output fields:**
```python
{
  "csm_best_contract": str,         # e.g. "AAPL 185C 18Jul"
  "csm_delta_sweet_spot": float,    # target delta 0.35–0.55
  "csm_dte_rank": str,              # OPTIMAL / ACCEPTABLE / MARGINAL
  "csm_premium_efficiency": float,  # gain per dollar of premium at 2.5R target
  "csm_breakeven_pct": float,       # % move required to break even
  "csm_gamma_runway": str,          # CLEAR / PARTIAL / BLOCKED
  "csm_iv_crush_risk": str,         # LOW / MEDIUM / HIGH / EXTREME
  "csm_r1_target": float,           # premium value at 1R (2× entry)
  "csm_r3_target": float,           # premium value at 3R (4× entry)
  "csm_r5_target": float,           # premium value at 5R (6× entry)
  "csm_r10_target": float,          # premium value at 10R (11× entry)
  "csm_verdict": str,               # BUYABLE / WAIT / TRAP / TOO_LATE
  "csm_verdict_reason": str         # plain English
}
```

**Verdict logic:**
```
BUYABLE  → delta 0.35–0.55, DTE 5–20, IVP < 50, gamma runway CLEAR, breakeven <= expected move
WAIT     → contract geometry valid but IVP > 50 (IV elevated — wait for compression)
TRAP     → delta > 0.70 (too expensive, lottery ticket geometry) OR IVP > 75 (buying peak vol)
TOO_LATE → underlying has already moved > 60% toward structural target (crowd has arrived)
```

**Integration point:**  
Output fields prefixed `csm_` are appended to the existing Options Intelligence output dict. They flow automatically into the SuperBrain layer and appear in the morning manifest and Intelligence Lab. No other files require modification.

**Constraints:**
- If contract data is missing or Mark_Synthetic=True, set `csm_verdict = DATA_INSUFFICIENT`. Do not produce a BUYABLE verdict on synthetic marks.
- Delta sweet spot is a soft target. If no contract exists in 0.35–0.55 range, select nearest available and flag `csm_delta_note = "NEAREST_AVAILABLE"`.
- Do not change any existing field names or remove existing output fields. Only append new `csm_` prefixed fields.

---

## SPRINT 3 — TRAP-TO-LAUNCH ENGINE™
**Priority: MEDIUM-HIGH — Architectural note required**

### Business Problem
Trap detection currently fires inside `trigger_layer.py` at Phase 8.6b — after Options Intelligence (Phase 7) has already run. This means contracts are selected before the trap is confirmed, causing early entries that decay 30–40% of premium before the underlying moves. The PYPL failure was partly driven by entering before the trap was confirmed.

### Architectural Decision Required Before Building
**Do not begin coding until you have confirmed the following with the human trader:**

The Trap-to-Launch Engine ideally runs between Phase 3 (Discovery) and Phase 7 (Options Intelligence) to sequence: detect trap → then select contract. This is a phase sequence change in `intelligent_orchestrator.py`. The risk is the same zero-signal failure mode that occurred in April 2026 when the trigger layer write path was broken.

**Proposed safe approach:** Build TLE as a standalone enrichment layer that writes a `tle_verdict` field to the package JSON files. Options Intelligence then reads this field and uses it as a gate modifier — not as a hard block. This avoids resequencing the orchestrator phases entirely.

### What to Build
Create a new module: `avshunter_trap_engine.py`

**Trap detection logic:**

For BULLISH trap (supports CALL setups):
```
Spring / Wyckoff Phase C reclaim    → weight 3
VWAP_RECLAIM trigger fired          → weight 2
VOL_COMPRESSION trigger fired       → weight 2
Failed breakdown (wick below support, close above) → weight 2
Shorts trapped below value area (control_state = SHIFTING BULLISH) → weight 2
Call wall runway clear above        → weight 1
TLE_BULLISH score = sum of weights
```

For BEARISH trap (supports PUT setups):
```
UTAD / failed breakout              → weight 3
VWAP loss confirmed                 → weight 2
Buyer trapped above value (control_state = SHIFTING BEARISH) → weight 2
Rejection at supply zone            → weight 2
Weak thrust after positive catalyst → weight 1
Put wall acceleration path clear    → weight 1
TLE_BEARISH score = sum of weights
```

**Output fields per ticker:**
```python
{
  "tle_trap_direction": str,      # BULLISH / BEARISH / NEUTRAL / CONFLICTED
  "tle_who_is_trapped": str,      # "Shorts below $X" or "Buyers above $Y" or "None confirmed"
  "tle_forced_move_level": float, # price level where trapped participants must act
  "tle_entry_trigger": str,       # what needs to happen to confirm: e.g. "VWAP_RECLAIM"
  "tle_kill_switch": float,       # price invalidation — if hit, trap thesis is wrong
  "tle_bullish_score": int,       # 0–13
  "tle_bearish_score": int,       # 0–13
  "tle_verdict": str,             # EARLY_PROBE / CONFIRMATION_ENTRY / CHASE / NO_TRADE
  "tle_crowd_arrival_target": float  # structural target where crowd buyers/sellers arrive
}
```

**Verdict logic:**
```
EARLY_PROBE         → score 4–6, trap forming but not confirmed, small size only
CONFIRMATION_ENTRY  → score 7–10, trap confirmed, full size appropriate
CHASE               → score 11–13, move already in progress, crowd has arrived — premium expensive
NO_TRADE            → score < 4, no trap detected in this direction
```

**Integration point:**  
Write `tle_` fields to the package JSON files in Phase 5. Options Intelligence reads `tle_verdict` from the package JSON and applies the following modifier:
- `EARLY_PROBE` → reduce CSM premium efficiency score by 20% (reflects early entry theta risk)
- `CONFIRMATION_ENTRY` → no modifier (optimal)
- `CHASE` → set `csm_verdict = TOO_LATE` regardless of other scores
- `NO_TRADE` → set `tle_` fields to null, no modifier to Options Intelligence

**Constraints:**
- Sparse field guard mandatory: any individual trap signal field that is absent in more than 20% of the universe must have an explicit fallback value (0 for scores, "UNAVAILABLE" for strings). No hard dependency on any single field.
- `trigger_layer.py` existing TRAP trigger remains in place and is not modified. TLE runs upstream and is additive, not a replacement.
- After deployment, verify GO count baseline within 10% of pre-change run before declaring build complete.

---

## SPRINT 4 — ML FEEDBACK LOOP REACTIVATION
**Priority: MEDIUM — Depends on clean trade data accumulation**

### Business Problem
The ML confidence engine (`ml_confidence_engine.py`) and confirmation ingester (`confirmation_ingester.py`) are currently paused due to data integrity issues identified in the 13-trade journal audit. UAT smoke test entries (DHR trades IDs 6 and 7) and a missing direction field (Trade ID 2) were distorting weight updates. Until this is resolved the pipeline cannot learn from its own outcomes.

### Pre-conditions — Do not build until confirmed
- Minimum 30 clean eligible trades in the journal (currently 13 — 10 real, 3 compromised)
- `ml_eligible` flag added to journal schema to exclude UAT, blank-direction, and EXPIRED_WORTHLESS-due-to-data-failure trades
- Confidence weights frozen at current baseline snapshot

### What to Build

**Step 1 — Add `ml_eligible` flag to trade journal schema:**
```sql
ALTER TABLE trades ADD COLUMN ml_eligible INTEGER DEFAULT 0;
```

Eligibility rules (set `ml_eligible = 1` only when ALL of the following are true):
```
outcome_class NOT IN ('LIVE_UAT_SMOKE_FLAT', 'DATA_FAILURE')
direction IS NOT NULL AND direction != ''
exit_reason NOT IN ('EXPIRED_WORTHLESS') — unless confirmed thesis failure, not data failure
entry_premium > 0
exit_premium IS NOT NULL
```

**Step 2 — Gate the confirmation ingester:**
Modify `confirmation_ingester.py` to read only rows where `ml_eligible = 1`. Add a minimum sample check: if eligible trade count < 30, log a warning and skip weight updates. Do not error — run continues normally.

**Step 3 — Regression on outcomes:**
Once 30+ eligible trades exist, add a `run_outcome_regression()` function to `ml_confidence_engine.py` that performs:
- Logistic regression: pipeline fields → binary win/loss outcome
- OLS regression: pipeline fields → realised R:R
- Feature importance ranking: which of the 55 actuarial columns most predicted winners

Output a human-readable calibration report to:
`data\output\calibration\regression_report_<date>.txt`

The report must include:
```
TOP 5 PREDICTORS OF WINNING TRADES (by coefficient magnitude):
TOP 5 PREDICTORS OF LOSING TRADES:
PREDICTED vs REALISED WIN RATE:
PREDICTED vs REALISED R:R:
FIELDS WITH ZERO PREDICTIVE VALUE (candidates for removal):
RECOMMENDED CONFIDENCE WEIGHT ADJUSTMENTS (human review required — not auto-applied):
```

**Constraints:**
- Regression results are ADVISORY. The engine must never auto-update confidence weights without explicit human confirmation via a CLI flag: `python ml_confidence_engine.py --apply-weights --run-id <id>`
- Freeze current confidence weights as `weights_baseline_<date>.json` before any update.
- sklearn is the approved regression library. If not installed: `pip install scikit-learn`

---

## FIELD CONTRACT REFERENCE
**All new fields must follow this naming convention and registration:**

| Sprint | Field Prefix | Written By | Read By | CSV / JSON |
|--------|-------------|------------|---------|------------|
| Sprint 1 | `exit_` | `avshunter_exit_engine.py` | Human trader | `morning_exit_signals.csv` |
| Sprint 2 | `csm_` | `avshunter_options_intelligence.py` | `avshunter_superbrain_layer.py` | Package JSON + signals CSV |
| Sprint 3 | `tle_` | `avshunter_trap_engine.py` | `avshunter_options_intelligence.py` | Package JSON |
| Sprint 4 | `ml_eligible` | Manual / journal | `confirmation_ingester.py` | SQLite journal DB |

---

## TESTING PROTOCOL — MANDATORY FOR EACH SPRINT

Run in this order after each sprint:

```powershell
# 1. Dry run — evening pipeline, no real data write
python intelligent_orchestrator.py --evening --data-mode EOD --dry-run

# 2. Single ticker probe — confirm new fields appear in output
python avshunter_ticker_probe.py --tickers AAPL MSFT NVDA

# 3. Handoff contract audit — confirm warn count within baseline (warn=8, fail=0)
python handoff_contract_audit.py --run-id <latest_run_id>

# 4. Signal count check — GO count within 10% of pre-change baseline
# Extract GO count from morning manifest and compare to previous run

# 5. Journal smoke test — confirm exit engine reads open positions correctly
python avshunter_exit_engine.py --test-mode
```

**If any of the following occur, rollback immediately and do not proceed:**
- GO count drops more than 10% from baseline
- `handoff_contract_audit.py` reports fail > 0 on new fields
- Any new `csm_` or `tle_` field is absent from more than 30% of signals
- Exit engine produces `TAKE_FULL` on a position with `DATA_UNAVAILABLE` current premium

---

## KNOWN RISK PATTERNS — READ BEFORE ANY IMPLEMENTATION

These are confirmed failure modes from the April 2026 zero-signal incident. Do not repeat them.

1. **Wrong directory** — Always confirm the module path is registered in `intelligent_orchestrator.py` before testing. The April incident had EDE deployed to `VANGUARD_DIR` instead of `BASE_DIR`.

2. **Field name mismatch** — The EDE was reading `expected_move_10d`; GARCH writes `l3_expected_move_6_10d`. Before reading any field from another module's output, confirm the exact field name by reading that module's output CSV or JSON.

3. **CSV write path broken** — After implementing any new module, confirm it is writing to the correct CSV with a `head` command before running the full pipeline. The April incident had trigger_layer writing to JSON only, not CSV.

4. **Sparse field hard dependency** — Any new trigger or score that reads a field present in less than 80% of signals must have an explicit fallback. `pcr_signal` was only 34% populated — the TRAP trigger had no guard for its absence.

5. **SuperBrain R:R gate conflict** — SuperBrain has its own internal R:R gate (previously at 0.5) that conflicted with the Options Intelligence A2 gate (1.5). If any new module introduces a gate, confirm it does not create a lower-floor bypass path through SuperBrain.

---

## DELIVERABLES PER SPRINT

| Sprint | New Files | Modified Files | New Output |
|--------|-----------|---------------|------------|
| 1 | `avshunter_exit_engine.py` | `morning_thesis_validator.py` (add post-processing call) | `morning_exit_signals.csv` |
| 2 | None | `avshunter_options_intelligence.py` (add `build_convexity_strike_map()`) | `csm_` fields in signals CSV |
| 3 | `avshunter_trap_engine.py` | `intelligent_orchestrator.py` (register Phase 5.5), `avshunter_options_intelligence.py` (read `tle_verdict`) | `tle_` fields in package JSON |
| 4 | None | `avshunter_trade_journal.py` (add `ml_eligible`), `confirmation_ingester.py` (eligibility gate), `ml_confidence_engine.py` (regression function) | `regression_report_<date>.txt` |

Build Sprint 1 first. Do not begin Sprint 2 until Sprint 1 passes the full testing protocol. Do not begin Sprint 3 until architectural decision on phase sequencing is confirmed with the human trader.
