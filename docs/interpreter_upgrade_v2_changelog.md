# Interpreter Upgrade v2 — Change Log

Date: 2026-05-28
Implemented by: Claude Code (claude-sonnet-4-6)

---

## Summary

Added Money Flow Read section (5-lens chart-based flow scoring),
Footprint Verdict section (pre-crowd positioning framework),
Hunter Scenario (forward-thinking trade narrative replacing The Scenario Block),
and reframed all confirmation-seeking logic to pre-crowd positioning logic.
Extended Final Verdict with interpreter-layer states alongside existing pipeline states.
All existing pipeline workflow unchanged.

---

## Files Modified

| File | Change |
|------|--------|
| `pipeline_interpreter/pipeline_interpreter_system_prompt.txt` | All 6 changes — see breakdown below |
| `pipeline_interpreter/pipeline_interpreter_engine.py` | `extract_verdict()` extended for new states; `extract_interpreter_verdict()` added |
| `pipeline_interpreter/pipeline_interpreter_outputs.py` | `_verdict_style()` extended for 5 new interpreter verdict styles |

## Files Added

None. All changes are modifications to existing files.

## Files Backed Up

`C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\backups\interpreter_backup_20260528\`
- `pipeline_interpreter_system_prompt.txt`
- `pipeline_interpreter_engine.py`
- `pipeline_interpreter_outputs.py`

---

## Changes by ID

### CHG-001: Add Money Flow Read Section
Added `MONEY FLOW READ — 5-LENS CHART SCORING BLOCK` to system prompt.
Position: after Evidence Quality, before Trapped Participants.
Five lenses (Volume Character, Institutional Footprint, Options Flow,
Price/Volume Divergence, Relative Strength Flow) each scored +2/+1/0/-1/-2.
Arithmetic must be shown. Impaired lenses score 0 and log DATA_GAP.
Composite maps to STRONG_ACCUMULATION_FOOTPRINT through STRONG_DISTRIBUTION_FOOTPRINT.
Section header: `═══════════════════════════════════════ MONEY FLOW READ ═══════════════════════════════════════`

### CHG-002: Add Footprint Verdict Section
Added `FOOTPRINT VERDICT BLOCK` to system prompt.
Position: immediately after Money Flow Read, before Trapped Participants.
Contains: Structural Integrity, Money Flow Summary, Kill Switch, Probe Structure blocks.
Five footprint states: FOOTPRINT_VALID / FOOTPRINT_FORMING / FOOTPRINT_WATCH /
FOOTPRINT_CROWDED / FOOTPRINT_BROKEN.
FOOTPRINT_BROKEN is the only state producing no trade recommendation.
Section header: `═══════════════════════════════════════ FOOTPRINT VERDICT ═══════════════════════════════════════`

### CHG-003: Replace Scenario Section with Hunter Scenario
Replaced `THE SCENARIO BLOCK` (7-component structure with SCENARIO_BROKEN verdict)
with `HUNTER SCENARIO BLOCK` (6 components written as if already positioned).
New components: Ignorance Map, What Is Happening Now (forward-framing),
Who Will Be Wrong and When, Discovery Sequence (5 steps), Exit Architecture, Hunter Verdict.
Section header: `═══════════════════════════════════════ HUNTER SCENARIO ═══════════════════════════════════════`

### CHG-004: Remove Confirmation-Seeking Language
Added `MANDATORY OUTPUT REFRAME RULES` block to system prompt.
Modified Horizon 1 Rule 4 from "DO NOT ENTER" blocking language to diagnostic language.
Prohibited patterns: DO NOT ENTER / SCENARIO_BROKEN / VWAP_CONFIRMATION_REQUIRED /
"wait for VWAP reclaim" / "volume confirmation required" / "no catalyst visible — do not enter".
Each prohibited pattern has a mandatory replacement producing pre-crowd positioning language.

### CHG-005: Reframe FOOTPRINT_CROWDED
Added `FOOTPRINT_CROWDED — CROWD TRADE IDENTIFICATION` section within Footprint Verdict Block.
Three crowd trade types: CROWD_MOMENTUM_LONG / CROWD_EXHAUSTION_FADE / NARRATIVE_FADE.
Each produces entry zone, kill switch and exit architecture.
FOOTPRINT_CROWDED never produces PASS; only FOOTPRINT_BROKEN produces no recommendation.

### CHG-006: Extend Final Verdict States
Updated `FINAL VERDICT` in DR. MAGNUS VALE FRAMEWORK to require TWO layers:
- Pipeline Verdict (machine layer): GO / ARMED / PROBE / WAIT / BLOCKED / MISDIAGNOSED (unchanged)
- Interpreter Verdict (human layer): PROBE_NOW / PROBE_WATCH / MONITOR / CROWD_TRADE / PASS_THESIS_INVALID
Updated `extract_verdict()` in engine.py to recognise both layers (pipeline used for session tracking).
Added `extract_interpreter_verdict()` to engine.py.
Added 5 new verdict styles to `_verdict_style()` in outputs.py.
Updated OUTPUT FORMAT section list to include MONEY FLOW READ, FOOTPRINT VERDICT, HUNTER SCENARIO.

---

## Data Gaps Identified

### Lens 1 — Volume Character
**Required**: Per-session volume for last 10 sessions classified as up-day / down-day.
**Available**: Chart images (readable visually by vision model) / no structured field.
**Impact**: Lens 1 scores 0 when running `/ticker` without chart images.
**DATA_GAP flag**: `NO_PER_SESSION_VOLUME`
**Recommended fix**: Add per-session OHLCV (last 10 sessions) to pipeline row as structured field.

### Lens 2 — Institutional Footprint
**Required**: Closing cross direction and size (multi-session). Time & Sales print distribution.
**Available**: Neither field is in the pipeline CSV or passed as structured data.
**Impact**: Lens 2 scores 0 unless intraday data is manually available.
**DATA_GAP flags**: `NO_CLOSING_CROSS_DATA` / `NO_TIME_AND_SALES`
**Recommended fix**: Add closing cross imbalance field from exchange data to pipeline row.

### Lens 4 — Price / Volume Divergence
**Required**: ATR current vs 20-day average (as ratio/percentage).
**Available**: Current ATR likely in pipeline row; 20d ATR average not present as separate field.
**Impact**: Partial — lens can read from chart images if provided; structured comparison unavailable.
**DATA_GAP flag**: `NO_ATR_COMPARISON`
**Recommended fix**: Add `atr_20d_avg` field to pipeline row alongside existing ATR field.

### Lens 5 — Relative Strength Flow
**Required**: Named peer % change vs sector ETF and index same session.
**Available**: Sector is in pipeline row; peer % changes not systematically available.
**Impact**: Lens 5 can partially score using sector-level data; peer comparison limited.
**DATA_GAP flag**: `NO_PEER_COMPARISON_DATA`
**Recommended fix**: Add per-session peer performance fields for top 3 sector peers to pipeline row.

**Note**: All data gaps produce lens score = 0 and are flagged in the DATA GAPS list of the
Money Flow Read output. They do NOT block implementation. The LLM can still produce partial
scores from chart images provided via `/chart` or `/ticker` with chart files in MA_Inputs.

---

## Regression Status

The following existing behaviours are structurally preserved:

| Check | Status |
|-------|--------|
| System prompt still loads from same file | PASS |
| API call signature unchanged | PASS |
| `extract_verdict()` still returns pipeline verdicts for session tracking | PASS |
| `_verdict_style()` still handles all original verdicts | PASS |
| Evidence Quality section preserved in output format | PASS |
| Trapped Participants section preserved | PASS |
| Chess Move Tree section preserved | PASS |
| Soul of the Chart sections preserved | PASS |
| Execution Prescription preserved | PASS |
| Kill Switch section preserved | PASS |
| Monetisation section preserved | PASS |
| Risk Assessment section preserved | PASS |
| Junior Trader Briefing logic unchanged | PASS |
| Pre-Trade Probability block unchanged | PASS |
| Capital permission flags unchanged | PASS |
| Execution permission flags unchanged | PASS |
| HTML naming convention unchanged | PASS |
| ═══ section divider format preserved | PASS |
| CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION unchanged | PASS |
| NONE_PIPELINE_INTERPRETER_ONLY unchanged | PASS |

---

## Known Issues

1. **Per-session volume**: Lens 1 will produce DATA_GAP when `/ticker` runs without chart images.
   This is expected behaviour. Score = 0. Flagged in output.

2. **Closing cross / T&S**: Lens 2 will produce DATA_GAP for most tickers.
   This is expected until a closing cross data feed is integrated.
   Score = 0. Flagged in output.

3. **Section 8 Junior Briefing badge**: The Junior Briefing Section 8 uses `DO NOT ENTER` as a
   badge value (e.g. `STATUS: DO NOT ENTER`). This is the Junior Briefing layer status badge,
   not the interpreter output pattern. It is DISTINCT from the prohibited output pattern and
   has not been changed. The reframe rules apply to the main interpreter narrative, not to
   the Junior Briefing badge system.

4. **`extract_verdict()` and session tracking**: The `InterpreterSession.summary()` method
   still tracks GO/ARMED/WAIT/BLOCKED using the pipeline verdict only. The interpreter verdict
   (PROBE_NOW etc.) appears in the narrative text but is not separately tracked in the session
   summary bar. A future sprint can add interpreter verdict tracking to the summary bar.
