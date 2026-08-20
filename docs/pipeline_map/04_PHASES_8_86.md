# Pass E — SuperBrain / WBS / EIL and Trigger Layer

Read-only audit. No files edited, no pipeline phase executed. All citations against
`intelligent_orchestrator.py`, `scripts/avshunter_superbrain_layer.py`,
`execution_intelligence.py`, `execution_intelligence_runner.py`, `trigger_layer.py`,
`avshunter_trap_engine.py`, and `eod_candidate_engine.py` as they exist on disk at
time of pass (all uncommitted/working-tree, same caveat as Passes A-D). Builds on
`00_SPINE.md` (Pass A), `01_PHASES_0_3.md` (Pass B), `02_PHASES_4_6.md` (Pass C),
`03_PHASE_7_OPTIONS.md` (Pass D) — cited, not re-derived, except where a correction
is stated explicitly.

**Denominators, stated on every percentage below:** 3,323 (augmented universe) and
1,400 (rows entering this span, per Pass D's boundary — the full Options Intelligence
scoring-loop population, not just EXECUTE/ARMED). Both given, each labelled.

**Reference runs, read directly:** `data/output/runs/20260818_041214/` (1,400 rows)
primary; `data/output/runs/20260816_075339/` (1,347 rows) secondary. Every count below
not explicitly marked otherwise came from `pandas.read_csv` + `value_counts`/`crosstab`
against the actual artefacts in these two directories — not inferred from source alone.

---

## E0 — Span map (corrected ordering, with direct line citations)

Pass A's dispatch table (items 17-31) is the base map; this pass verified the
call sites directly and adds detail Pass A did not go inside. **Execution order,
confirmed by direct read:**

| # | Stage | Function | Call site | Critical? |
|---|---|---|---|---|
| — | Trap Engine (Phase 5.5) | `avshunter_trap_engine.run_trap_layer()` | `intelligent_orchestrator.py:2026-2044`, invoked **inside** `run_vanguard_pipeline()`, immediately after Backfill and before the packages `index.json` check (`:2047`) | Non-critical, try/except |
| 17 | Options Intelligence (Phase 8a) | `run_options_intelligence` | `:3765-3769` | Non-critical at this call site |
| 21 | Trigger Layer — **package JSON** (Phase 8.6) | `trigger_layer.patch_run_packages()` | imported `:3956`, called `:3956-4025` | Non-critical |
| 22 | SuperBrain **passthrough** (Phase 8d) | `run_superbrain_passthrough()` | defined `intelligent_orchestrator.py:2402-2501`, called `:4032` | Non-critical (return value unchecked) |
| 23 | Horizon patch 8d-B | `patch_horizon_fields_into_csv(..., label="superbrain_enriched")` | `:4043-4053` | Non-critical |
| 24 | Catastrophe Gate (Phase 8b) | `run_catastrophe_gate()` | defined `:2546-2556`, called `:4054` | **No-op stub** — see E1.5 |
| 25 | Wall Break Scorer (Phase 8e, "Layer 4b") | `run_wall_break_scorer()` | defined `:2559-2592`, called `:4055` | Non-critical, subprocess |
| 26 | FIX-ACTUARIAL-SEQ | inline pandas patch of `superbrain_enriched_{run_id}.csv` | `:4072-4222` | Non-critical (soft-gates manifest) |
| 27 | EIL (Phase 9) | `run_execution_intelligence_layer()` | defined `:2597-2711`, called `:4225` | Fail-open at workflow level, but items 28/29/30/31 are nested inside its success branch (Pass A) |
| 28 | Actuarial safety net | `inject_actuarial_into_eil_csv()` | `:4229` | Non-critical |
| 29 | GARCH (Phase 10a/10b) | `run_garch_layer()`, `merge_garch_into_enriched()` | defined `:2719+`, `:2752-2850`, called `:4235-4236` | Non-critical — **writes back into `superbrain_enriched` AND `eil_enriched`, in place, after EIL has already run** — see E2.5 |
| 30 | Trigger Layer — **CSV** (Phase 8.6b) | `trigger_layer.enrich_csv()` | imported `:4245`, called `:4244-4335` | Non-critical |
| 31 | Handoff Conflict Guard | `enforce_handoff_conflict_guard()` | `:4340` | Critical, but conditional on EIL success |

**Correction to Pass A §6 (artefact chain table):** Pass A lists
`superbrain_enriched_{run_id}.csv`'s downstream readers as "FIX-ACTUARIAL-SEQ patch
... `run_execution_intelligence_layer`" only. This is incomplete: **GARCH
(`merge_garch_into_enriched`, item 29) also writes into `superbrain_enriched_{run_id}.csv`
in place**, after EIL has already consumed it (`intelligent_orchestrator.py:2811-2812`).
The file is mutated three separate times across one evening run (8d write → 26
actuarial patch → 29 GARCH merge) under the same filename. An auditor reading the
file from disk post-run sees only the final state — not what EIL itself read at its
own execution time. This matters directly for E2.5 below.

---

## E1 — The SuperBrain passthrough

**Module / function:** `run_superbrain_passthrough()`, `intelligent_orchestrator.py:2402-2501`
**Invoked by:** `evening_workflow()` item 22, `:4032`
**Conditional on:** `oi_csv.exists()` (else early-return `False`, `:2424-2426`); otherwise unconditional
**Output non-empty in ref runs:** Yes — `superbrain_enriched_20260818_041214.csv`
(1,400 rows × 708 cols), `superbrain_enriched_20260816_075339.csv` (1,347 × 710)

### What it does, exactly

1. **Source selection**: prefers `options_intelligence_phantom_{run_id}.csv` over
   the plain `options_intelligence_{run_id}.csv` if the phantom file exists
   (`:2417-2420`). **Confirmed live this run**: phantom CSV exists (665 cols = 627
   OI cols + 38 `phantom_*` cols from Phase 7.5) and is the actual passthrough
   source, not the 627-col file Pass D profiled directly. Column-diff confirms all
   38 `phantom_*` columns and all 627 OI columns survive into `superbrain_enriched`
   unchanged.
2. **Full copy, nothing dropped**: `df = pd.read_csv(oi_csv); ... df.to_csv(sb_csv)`
   (`:2430`, `:2492`) — every column the source CSV carries survives. This is a
   straight copy, not a curated subset.
3. **One field added**: `sb_final_verdict`. If `options_verdict` is present and
   `sb_final_verdict` is not, `df["sb_final_verdict"] = df["options_verdict"]`
   (`:2444-2447`) — a **direct, untransformed copy**, no mapping table, no score
   recomputation. If `options_verdict` is absent, defaults to the literal string
   `"STAND_DOWN"` (`:2449-2451`) — not observed this run (`options_verdict` was
   always present).
4. **Six NaN-placeholder columns**, inserted only `if col not in df.columns`
   (`:2464-2476`): `contract_spread_pct`, `contract_premium`, `options_bid`,
   `options_ask`, `contract_iv`, `contract_delta`.

### Which of the three-way verdict field it reads — settled

Given Pass D's finding that `options_verdict` / `options_verdict_tier` /
`final_route` disagree on hundreds of rows, this pass establishes precisely: **the
passthrough reads the bare `options_verdict` column, not `options_verdict_tier` and
not `final_route`.** Confirmed both by direct source read (`:2444`) and empirically —
`sb_final_verdict` and `options_verdict` are **byte-identical** in both reference
runs:

| `sb_final_verdict` (= `options_verdict`) | 08-18 (n=1,400) | % of 1,400 | % of 3,323 |
|---|---|---|---|
| STAND_DOWN | 1,030 | 73.6% | 31.0% |
| ARMED | 247 | 17.6% | 7.4% |
| EXECUTE | 123 | 8.8% | 3.7% |

This means the real SuperBrain's own risk-escalation layer, had it run, would have
received the same input Pass D already characterised as internally inconsistent
with `options_verdict_tier`/`final_route` (183-184 rows STAND_DOWN-but-PROBE-tiered,
36 EXECUTE-but-ARMED_HALF, etc.) — the bypass does not fix or launder that
inconsistency, it just picks one of the three fields (the legacy, most conservative
one) and propagates it forward untouched.

### The NaN-placeholder mechanism — confirmed empirically dead in both reference runs

The `_missing_spread` guard (`:2472-2476`) fires only when a **column name** is
absent from the source CSV — not when its **values** are null. Direct check on both
phantom-OI-sourced runs: all six named columns (`contract_spread_pct`,
`contract_premium`, `options_bid`, `options_ask`, `contract_iv`, `contract_delta`)
are **already present as columns** in the phantom OI CSV (confirmed by direct read),
so `_missing_spread` is empty and the log line is always
`"✅ Phase 8d: all spread/contract columns present"` — the NaN-insertion branch
never executes in either reference run. The **null values** that do exist for these
columns (846/1,400 = 60.4% of 1,400 / 25.5% of 3,323 rows — exactly the sum of
Pass D's `BLOCK_NO_CONTRACT` (831) + `BLOCK_NO_CHAIN` (15) populations) come
pre-existing from Options Intelligence itself, not from this passthrough's own
insertion logic. The passthrough's defensive code is real, correctly written, and
untested by either reference run — a genuine gap between the *column-absence*
scenario the code defends against and the *value-null* scenario that is the one
that actually occurs.

### Every capability of the real SuperBrain lost by the bypass

Read directly from `scripts/avshunter_superbrain_layer.py`'s own self-documented
deprecation header (`:1-25`) and `assemble_execution_plan()` (`:1328-1750+`), none
of which executes on the current orchestrator path (confirmed: zero call sites of
`run_superbrain()`, `process_signal()`, or `assemble_execution_plan()` in
`intelligent_orchestrator.py`):

- **Layer 1 — Behavioural Vetoes** (V1-V6/V8, 6-8 conditions: late entry, no
  runway/at-wall, high-IV-no-edge, unclear state, no time-stop, PCR contradiction,
  event-IV, directional-weight contradiction).
- **Layer 2 — Convexity Score** (5-condition skyrocket-profile check, drives
  campaign classification CONVEXITY_INJECTION/CORE_CAMPAIGN/STAGED/AVOID).
- **Layer 3 — Instrument Ladder** (5-stage DTE ladder with alert prices).
- **Layer 4 — Time-Stop** (date-based exit rule generation).
- **Layer 5 — Final verdict assembly**, `assemble_execution_plan()`, containing:
  - **HARD GATE 0a — `ev_status=='DATA_WEAK'` risk-escalation** (`:1370-1388`):
    surfaces zero-actuarial-hit-rate signals as a WARNING that elevates risk to
    `EXECUTE_WITH_RISK`, not silently as EXECUTE. This is the specific gate the
    Standing Contract names as fully-built-but-bypassed — confirmed present,
    confirmed unreachable on the current path.
  - HARD GATE 0 — negative structural EV (`ev_final < -0.10`) → `EXECUTE_WITH_RISK`.
  - HARD GATE 0b — sub-threshold R:R (`< 0.5`) → `EXECUTE_WITH_RISK`.
  - GATE 0b2 — R:R below EXECUTE floor (1.5x live / warn-only EOD).
  - HARD GATE 0b3 — OIS below EXECUTE threshold (55, live-mode hard cap).
  - HARD GATE 0b5 — GARCH vol tailwind >0.15 → `EXECUTE_WITH_RISK` (this gate, in
    the retired file, explicitly depends on GARCH data being present *before*
    verdict assembly — see E2.5 for the live EIL's own version of this ordering
    problem).
  - Hard block 1 — zero runway (veto STAND_DOWN) → `STAND_DOWN`.
  - Hard block 2 — AVOID campaign (0/8 convexity) → `DATA_FAILURE`.
  - A1 gate — STAGED campaign demoted from EXECUTE→ARMED outside EOD mode.
  - Continuous conviction-based sizing (conv_score-driven, 0-100%, replacing flat
    campaign-tier sizing).
  - Weighted risk-label system (CRITICAL/STANDARD/MINOR warning weights, regime
    discount, flow-warning exemption) — a materially more nuanced sizing signal
    than anything downstream now produces.

**None of this runs.** The passthrough substitutes a single untransformed field
copy (`sb_final_verdict = options_verdict`) for all of the above.

---

## E1.5 — Catastrophe Gate and Wall Break Scorer

### Catastrophe Gate (Phase 8b)

**Module / function:** `run_catastrophe_gate()`, `intelligent_orchestrator.py:2546-2556`
**Invoked by:** item 24, `:4054`
**Conditional on:** Unconditional
**Output non-empty in ref runs:** N/A — **pure no-op stub.** Docstring states
plainly: *"Sprint 2: Catastrophe Gate removed from live decision chain. Was running
in shadow mode with no measured outcome contribution. Function retained as a no-op
stub so call sites require no changes."* Logs one line and `return True`. No file
read, no file written, no computation. Retained purely so the call site doesn't
need editing — this is intentional, documented dead weight, not a bug.

### Wall Break Scorer (Phase 8e, "Layer 4b")

**Module / function:** `run_wall_break_scorer()`, `intelligent_orchestrator.py:2559-2592`;
scoring itself in `wall_break_scorer.py` (external subprocess, not read this pass
beyond its I/O contract)
**Invoked by:** item 25, `:4055`
**Conditional on:** `wall_break_scorer.py` exists, `superbrain_enriched` and
`options_intelligence` CSVs both exist (else skip with `return True`, `:2566-2580`)
**Output non-empty in ref runs:** Yes — `wall_break_scores_20260818_041214.csv`,
**123 rows** × 686 columns.

**Row-scope finding, confirmed empirically:** WBS does not score the full 1,400-row
book. Its 123 output rows match **exactly, 1:1 by ticker**, the 123 rows where
`options_verdict == 'EXECUTE'` (Pass D's EXECUTE terminal path). WBS is silently
scoped to the EXECUTE tier only — **8.8% of 1,400 (3.7% of 3,323)** — despite
being handed the full `options_intelligence` CSV as an input argument; the
narrowing happens inside `wall_break_scorer.py` itself, not read this pass.

**Field-drop finding, confirmed empirically:** `wbs_grade` and `wbs_score` are
**absent as columns from both `superbrain_enriched_{run_id}.csv` and
`eil_enriched_{run_id}.csv`** in the reference run — `wall_break_scores_{run_id}.csv`
is never merged back into the main artefact chain. Grep of
`intelligent_orchestrator.py` finds no merge/join call reading
`wall_break_scores_{run_id}.csv` back into either enriched CSV anywhere in the
evening path.

**Consequence for EIL, and why it turns out to be inert:**
`build_execution_context_from_row()` reads `ctx.wbs_grade = _s(row, "wbs_grade",
"POSSIBLE")` and `ctx.wbs_score = _f(row, "wbs_score", 0.0) or _f(row, "wbs", 0.0)`
(`execution_intelligence.py:682-683`). Since neither column exists in the row EIL
actually reads, **every one of the 1,400 rows gets the hardcoded defaults**
(`"POSSIBLE"` / `0.0`) — including the 123 rows WBS did score, because the merge-back
never happens. However, grep across all five S1-S5 strategy files
(`vanguard/execution/strategies/*.py`) finds **zero references to `wbs_grade` or
`wbs_score`** — the composite score (`S1×0.50 + S2×0.40 + S3×0.05 + S4×0.03 +
S5×0.02`, `execution_intelligence.py:70-74`) never reads them. **Net effect: a
genuine field-scoping and merge-back gap exists, but it has no observable
consequence on any EIL output field in either reference run** — `ctx.wbs_grade`/
`ctx.wbs_score` are vestigial context fields, populated with defaults and then
never consumed, structurally identical in kind to Pass D's max-pain/charm
"computed but scoreless" finding.

---

## E2 — EIL (`execution_intelligence.py` / `execution_intelligence_runner.py`)

### The composite engine — ordering, confirmed exactly as the brief expected

**Module / function:** `evaluate(ctx)`, `execution_intelligence.py:330-490`
**Invoked by:** `_eil_evaluate(eil_ctx)`, `execution_intelligence_runner.py:1337`,
inside the per-row decision function (starts `:1139`), itself run once per row
inside the EIL runner's Pass 2 loop. **The runner is invoked as a separate
subprocess** (`intelligent_orchestrator.py:2644`, `cmd = [sys.executable,
str(cfg.EIL_RUNNER), "--run_id", run_id]`) — not an in-process call.
**Conditional on:** `_EIL_AVAILABLE` (import succeeded, `:355`); the v4.1 horizon
gate (`:1180-1227`) short-circuits before EIL scoring for `horizon_action ==
MONITOR_ONLY` or `horizon_bucket == "blocked"` rows — confirmed **structurally
dormant**: the code's own comment (`:1189-1196`) states the router "never emits
MONITOR_ONLY as an action... it no longer does (router now always emits
GO_SELECTIVE)"; the guard is retained defensively but does not fire on the current
router.
**Output non-empty in ref runs:** Yes, 1,400/1,347 rows, `eil_v3_verdict` populated
for every row.

**Ordering, confirmed by direct read of `evaluate()`:**
```
:344-348  s1-s5 = five strategies run
:351      hard_block = any(r.block for r in [s1..s5])          <- BEFORE composite
:354-360  composite = weighted sum of s1..s5 scores
:362-381  macro enrichment modifier applied to composite
:384      raw_verdict = _composite_verdict(composite, hard_block)
:385-398  final_verdict fixed (BLOCKED if hard gate failed, else raw_verdict)
:400-404  size_mult computed
:419-429  EV fields (ev_raw, ev_net, ev_score, ev_confidence) computed  <- AFTER verdict
:437-490  ExecutionVerdict returned, final_verdict never reassigned after :393
```
**Confirmed exactly as the Standing Contract states**: composite/hard-block/
raw-verdict/final-verdict are fixed by line 393; EV fields are computed afterward
(`:419-429`) purely as informational output — they cannot and do not influence
`eil_verdict`. Nothing later in `evaluate()` reassigns the verdict.

### A confirmed field-naming collision: `eil_raw_verdict` does not hold the raw verdict

`ExecutionVerdict` (the dataclass `evaluate()` returns) carries **two distinct
verdict fields**: `eil_verdict` (the final, hard-gated value — `"BLOCKED"` if any
S1-S5 hard gate fired, else `raw_verdict`) and `eil_raw_verdict` (the true
pre-hard-gate, score-threshold-only value — can genuinely be
`"STAND_DOWN_MICROSTRUCTURE"` if composite < 40 with **no** hard block).

The runner (`execution_intelligence_runner.py:1339-1342`) does:
```python
raw_eil_token = eil_result.eil_verdict        # the FINAL, hard-gated field
row["eil_v3_verdict"]  = _EIL_TOKEN_NORMALISE.get(raw_eil_token, "BLOCKED")
row["eil_raw_verdict"] = raw_eil_token        # <- also the FINAL field, not eil_result.eil_raw_verdict
```
**The CSV column named `eil_raw_verdict` is populated from the engine's *final*
verdict, not its genuinely-raw pre-hard-gate verdict.** The dataclass's actual
`eil_raw_verdict` field (which can be `"STAND_DOWN_MICROSTRUCTURE"`) is computed,
returned, and then **silently discarded** — never written to any CSV. Confirmed
empirically: in both reference runs, the CSV's `eil_raw_verdict` column contains
only `{EXECUTE_WITH_CAUTION, BLOCKED, EXECUTE_NOW, EXECUTE_DEFER}` — **the literal
string `STAND_DOWN_MICROSTRUCTURE` never appears in either run's output**, even
though it is a real, reachable value inside `_composite_verdict()`. This means
**every observed `BLOCKED` verdict in both reference runs came from a hard S1
liquidity-gate failure ("no executable market"), never from the composite-score
threshold alone** — a fact this pass can state with confidence precisely because
of the empirical absence, but which the mislabeled column would hide from any
downstream reader who trusted its name.

### The 4-token vocabulary EIL actually produces (both runs)

| Token | 08-18 (n=1,400) | % of 1,400 | % of 3,323 | 08-16 (n=1,347) |
|---|---|---|---|---|
| `EXECUTE_WITH_CAUTION` | 1,072 | 76.6% | 32.3% | 1,052 |
| `BLOCKED` | 250 | 17.9% | 7.5% | 213 |
| `EXECUTE` (raw: `EXECUTE_NOW`) | 54 | 3.9% | 1.6% | 51 |
| `WATCHLIST` (raw: `EXECUTE_DEFER`) | 24 | 1.7% | 0.7% | 31 |

`_EIL_TOKEN_NORMALISE` (`:365-372`) also maps a fifth token, `"HIGH_CONVICTION"` →
`"EXECUTE"` — this token is never produced by `execution_intelligence.py`'s
`evaluate()` (whose only possible final-verdict strings are `EXECUTE_NOW`,
`EXECUTE_WITH_CAUTION`, `EXECUTE_DEFER`, `STAND_DOWN_MICROSTRUCTURE`, `BLOCKED`) —
**dead vocabulary in the normalisation table, a leftover from an earlier/different
verdict producer.** UNVERIFIED which prior version emitted it; not chased further.

### Campaign/Execution gate — the dominant verdict authority, not EIL

`_campaign_verdict()` / `_execution_verdict()` (`execution_intelligence_runner.py:764-836`)
derive from `sb_final_verdict` (i.e., from `options_verdict`, per E1) via a fallback
chain, called inside `_enrich_truth_fields()` (`:1235-1237`), **before** the EIL
call. If `campaign == "REJECT"` or `execution == "SKIP"` (`:1424`), the function
**returns early at `:1527`**, writing `fd_verdict` directly (`:1509`,
`"BLOCK"` if the row's `_exe_mode == "FATAL_BLOCK"` else `"WATCHLIST"`) — **before
EIL's own verdict is even consulted for `fd_verdict` purposes.** `eil_v3_verdict`
is still computed earlier in the function and is still written to the row (the
early return is after the EIL call, not before it — EIL always runs), but
`fd_verdict` for these rows never passes through `eil_v3_verdict` at all.

Only rows that do **not** hit this early return reach
`_apply_retired_sizing_overlay()` (`:2073-2109`), which sets `fd_verdict =
eil_v3_verdict` directly (`:2102`, using the spelling `"BLOCKED"`, not `"BLOCK"`)
for the four normalised tokens.

**Empirically, 1,369/1,400 (97.8% of 1,400 / 41.2% of 3,323) rows hit the
REJECT/SKIP early return** — confirmed by the exact match between `fd_verdict ==
"WATCHLIST"` (1,369) and the sum of `pse_execution_mode` values that are
diagnostic-only, non-EIL-sourced labels (`FUTURE_WATCH` 579 + `STRUCTURAL_WATCH`
500 + `EOD_PROBE_CANDIDATE` 127 + `WATCHLIST` 125 + `CURRENT_EDGE_REVIEW` 32 +
`TRANSITION_REVIEW` 5 + `SKIP` 1 = 1,369, exact). **Only 31/1,400 (2.2%) rows ever
reach the code path where `fd_verdict` is a direct function of `eil_v3_verdict`.**
08-16 confirms the same pattern: `fd_verdict == "WATCHLIST"` for 1,315/1,347
(97.6%).

**Consequence: the five-strategy EIL composite scoring that runs for all 1,400
rows is, for 97.8% of them, computed and then discarded at the `fd_verdict`
layer** — overridden by a campaign/execution classification computed from
`options_verdict` before EIL ever ran. See E4 for the quantified verdict-flip
table this produces.

### `fd_verdict` spelling divergence — a confirmed but currently zero-impact defect

Two producers write `fd_verdict` with **different spellings for the same concept**:
- `:1509` (REJECT/SKIP branch): `"BLOCK"` (no trailing D) when `_exe_mode ==
  "FATAL_BLOCK"`.
- `:2102` (`_apply_retired_sizing_overlay`, non-REJECT/SKIP branch): `"BLOCKED"`
  (with D) when `eil_v3_verdict == "BLOCKED"`.

`eod_candidate_engine._true_fatal_block()` (`:555-598`) checks `fd_verdict ==
"BLOCK"` exactly (`:564`, `:598`) — it does **not** match `"BLOCKED"`. **Empirically
confirmed dead in both reference runs**: `pse_execution_mode` never equals
`"FATAL_BLOCK"`, `effective_execution_verdict` never equals `"FATAL_BLOCK"`, and
`fd_verdict` never equals `"BLOCK"` for any of the 1,400 (08-18) or 1,347 (08-16)
rows — `has_fatal_label` is `False` for every row in both runs, meaning
**`_true_fatal_block()` returns `False` unconditionally for the entire book in
both reference runs, regardless of what EIL or the campaign gate concluded.**
This is a real, source-confirmed spelling mismatch between the writer and the
reader, but its observed impact in these two runs is **zero** — the gate simply
never fires either way, so no row is misclassified as a *result* of the spelling
bug specifically (the gate is dead for a broader reason: none of its three OR-conditions
is ever populated with a matching value by the current code, spelling aside).
Reported because it is a genuine, verifiable defect of the same "near-duplicate
logic, one path correct, one not" class as Pass D's two-spread-gate finding — not
because it changed an outcome in the sampled data.

### `_percentile_overrides` — confirmed zero downstream readers, repo-wide

`_percentile_overrides()` (`:949-965`) computes a top-30%-of-`ev_conf_adj` boolean
per row. Its output feeds two fields: `row["_percentile_override_active"] = True`
(`:1241`, written only when the override applies and EV ≥ -0.05) and
`row["fd_percentile_override"] = percentile_override` (`:2107`, always written).
**Grep of the entire repository (`*.py`) for both field names finds exactly one
file: `execution_intelligence_runner.py` itself — the two write sites and nothing
else.** Zero downstream readers, in-process or in any other module. Confirms and
extends a prior audit's finding with a repo-wide (not just in-file) check.

### `_apply_retired_sizing_overlay` — confirmed real reader downstream

`fd_verdict`, `fd_size` (hardcoded `0.0`, `:2103`), and `fd_ev_used`
(`:2106`) **are** read downstream — `eod_candidate_engine.py` reads `fd_verdict`
at `:563-564` (`_true_fatal_block`), `:767` (three-way verdict fallback chain:
`options_verdict` → `eil_v3_verdict` → `fd_verdict`), `:1682`, `:2081-2090`, and
`:2256`. `fd_size` is always `0.0` (PSE retired) — any consumer reading it for a
sizing decision gets a hardcoded zero, consistent with the Standing Contract's
`_pse_compute = None` finding at `execution_intelligence_runner.py:220-222`.
`fd_ev_used` mirrors `ev_result.ev_conf_adj` and is genuinely informational.

### Field drop: `campaign_verdict` / `execution_verdict` — computed, decisive, never written

`campaign_verdict` and `execution_verdict` are the **two fields that gate which
code path a row takes** (the REJECT/SKIP early return at `:1424`, which determines
97.8% of `fd_verdict` outcomes per above). Both are computed and attached to `row`
inside `_enrich_truth_fields()` (`:840-841`). **Confirmed by direct query of both
reference-run `eil_enriched_{run_id}.csv` files: neither column exists in the
output CSV at all** (`KeyError` on direct read). Checked against the explicit
`EIL_COLS` write-list (`execution_intelligence_runner.py:3297-3383`, ~140 named
columns) — `campaign_verdict` and `execution_verdict` are absent from that list.
**A field-drop that specifically removes the two most decision-relevant fields in
this entire span** — a downstream reader of `eil_enriched.csv` can see the
*outcome* (`fd_verdict`, `pse_execution_mode`) but not the *classification that
produced it*.

Notably, the orchestrator **does** defend against a structurally similar problem
for a different field set: a dedicated "sector column preservation guard"
(`intelligent_orchestrator.py:2672-2709`) patches nine `sector_*`/`macro_sector_bias`
columns back into `eil_enriched.csv` from `superbrain_enriched.csv` if the EIL
runner is found to have dropped them, with an explicit in-code contract comment
(`D-MACRO-SEC-002`) requiring `out_row = dict(input_row); out_row.update(eil_fields)`.
No equivalent guard exists for `campaign_verdict`/`execution_verdict` — the
orchestrator's authors were demonstrably aware fields could be silently dropped by
this runner, and built infrastructure to catch it for one field family but not
this one.

---

## E2.5 — GARCH runs after EIL: a fifth ordering defect, confirmed

**This is the headline finding of this pass.** `merge_garch_into_enriched()`'s own
docstring (`intelligent_orchestrator.py:2752-2777`) states the problem directly:

> *"run_garch_layer() writes garch_forecasts_{run_id}.csv to the qomega/ directory
> and stops. Nothing downstream consumed those fields — EVEngineV2 therefore ran
> without GARCH forward vol or iv_tailwind_score for every signal in the run."*

Per E0's confirmed ordering, GARCH (item 29, `:4235-4236`) runs **after** EIL
(item 27, `:4225`) has already executed as a completed subprocess and written its
final `eil_enriched_{run_id}.csv`. `merge_garch_into_enriched()` then:
1. Drops any pre-existing `l3_*` columns from `superbrain_enriched.csv` and
   left-joins in the real GARCH `l3_*` columns, overwriting the file in place
   (`:2804-2812`).
2. Does the same to `eil_enriched.csv` (`:2826-2839`) — the very file that already
   carries `eil_v3_verdict`, `eil_composite_score`, etc., computed earlier.

**Confirmed by column-diff evidence, not just the docstring**: `l3_*` columns
(`l3_expected_move_1_5d`, `l3_expected_move_6_10d`, `l3_iv_tailwind_score`, etc.)
are **absent from every artefact upstream of this merge** — absent from the
627-col plain OI CSV, absent from the 665-col phantom OI CSV, and therefore
necessarily absent from `superbrain_enriched.csv` at the moment EIL's subprocess
(item 27) reads it. `build_execution_context_from_row()`'s `expected_move_pct`
field (`execution_intelligence.py:649-655`) reads `l3_expected_move_1_5d` /
`l3_expected_move_6_10d` first, falling back to `expected_move_10d` only if both
are absent — **at EIL's actual evaluation time, both are guaranteed absent**, so
every row's `expected_move_pct` came from the non-GARCH fallback (or `None`) for
this run, never from GARCH.

**Net effect**: `eil_v3_verdict`, `eil_composite_score`, `eil_size_multiplier`, and
every S1-S5 sub-score for **all 1,400 (08-18) / 1,347 (08-16) rows** were computed
without GARCH forward-vol or IV-tailwind data, full stop — not for a subset, for
every row, in both reference runs, by construction of the ordering. The `l3_*`
columns that later appear in the same `eil_enriched.csv` file (16 columns,
confirmed present with 0 nulls on `l3_iv_tailwind_score` in the final artefact)
are patched in **retroactively, after the verdict that a reader might assume they
informed was already final**. A downstream consumer reading the finished CSV and
seeing both `eil_v3_verdict` and `l3_iv_tailwind_score` populated in the same row
has no way to tell from the file alone that the two were computed at different
times with no causal link between them.

This also resolves an internal inconsistency in the retired SuperBrain file: its
own HARD GATE 0b5 comment (`avshunter_superbrain_layer.py:1524-1525`) claims
*"GARCH now runs in Phase 8c.5 (before SuperBrain) so l3_iv_tailwind_score is
populated in the signal dict at verdict time"* — **this is stale relative to the
current orchestrator**, where GARCH runs at item 29, well after both the SuperBrain
passthrough (item 22) and EIL (item 27). Moot for the retired file (it never runs),
but it demonstrates the ordering has drifted from what at least one prior version
of the codebase's own documentation asserted.

**This is the fifth confirmed control-flow-ordering defect** in this codebase
(after Regime Screener, Trap Engine VWAP signals, the discovery/vanguard `_x`/`_y`
merge, and the two-spread-gate asymmetry) — ordering continues to be a systemic
property, exactly as the Standing Contract predicted.

---

## E3 — Trigger Layer

`trigger_layer.py` runs **twice** in the evening path, at two different points,
against two different artefact shapes:

| Invocation | Phase | Call site | Target |
|---|---|---|---|
| `patch_run_packages()` | 8.6 | `intelligent_orchestrator.py:3956-4025` (item 21) | Package JSONs, **before** SuperBrain passthrough / EIL |
| `enrich_csv()` | 8.6b | `:4244-4335` (item 30) | `eil_enriched_{run_id}.csv`, **after** EIL and GARCH |

### The trigger computation itself

**Module / function:** `evaluate_triggers(row)`, `trigger_layer.py:492-519`
**Computes four candidate triggers** directly from row fields (T1
`_t1_vol_compression`, T2 `_t2_vwap_reclaim`, T3 `_t3_range_break`, T4 `_t4_trap`),
gated first by a staleness check (`_is_stale(row)`, `:498-499` — stale signals get
an empty trigger list unconditionally). This function is **self-contained** — it
does not read `pkg["triggers"]`; it is the function that *produces* the values that
eventually populate `pkg["triggers"]`.

`build_trigger_block(row)` (`:527-552`) wraps `evaluate_triggers()` and adds
`trigger_quality` (`:452-463`, weighted-sum thresholds: STRONG ≥3.5, SINGLE ≥1.5,
else NONE), `trigger_primary` (`:466-473`, highest-weight trigger), `go_eligible`
(`is_go_eligible()`, `:476-485` — requires the *primary* trigger to be one of
`VOL_COMPRESSION`/`RANGE_BREAK_EARLY`/`RANGE_BREAK`/`TRAP`; `VWAP_RECLAIM` alone is
explicitly documented as insufficient, `:478-479`), and EV context.

`pkg["triggers"] = build_trigger_block(src)` at `:779` — **`patch_run_packages()`
(Phase 8.6) is the sole writer of `pkg["triggers"]`.** The CSV path
(`enrich_csv()`/`_trigger_block_from_package()`, `:615-651`) tries to reuse the
package's block when present (best-effort bridge, `:576-583`), falling back to
recomputing from flat row fields if not — so `trigger_quality`/`trigger_go_eligible`
as written to the CSV are **not** solely dependent on the package JSON having been
populated correctly; they can be, and in the reference runs are, populated
directly from `evaluate_triggers()` against the CSV row regardless of package-JSON
state.

### The VWAP ordering defect — confirmed, and its blast radius precisely scoped

**Trap Engine reads `pkg.get("triggers", {})`** (`avshunter_trap_engine.py:97`) to
source `trigger_primary`/`trigger_codes` for its own VWAP_RECLAIM (bullish, weight
2, `:162-166`) and VWAP_LOSS (bearish, weight 2, `:219-225`) signal checks. Per
E0's confirmed ordering, **Trap Engine (Phase 5.5) runs inside `run_vanguard_pipeline()`,
before Options Intelligence (`:3765`) and long before `patch_run_packages()`
(Phase 8.6, `:3956`) ever executes** — `pkg["triggers"]` does not exist in any
package JSON at Trap Engine's read time, so `pkg.get("triggers", {})` returns `{}`
every time, and `trigger_primary`/`trigger_codes` are always empty at that point.
**Confirmed with both writer and reader line numbers on both sides** — VWAP_RECLAIM
and VWAP_LOSS are structurally guaranteed unreachable inside Trap Engine's own
scoring, exactly as the Standing Contract states, now with the precise mechanism
traced end to end.

**Scope of the blast radius, precisely**: this ordering defect is local to Trap
Engine's *own* consumption of `pkg["triggers"]`. It does **not** affect
`trigger_quality`/`trigger_go_eligible` as read by `classify_tier()` downstream
(see below) — those are computed by `trigger_layer.py`'s own, later,
independent call to `evaluate_triggers()` against the row directly, not through
`pkg["triggers"]`, and that call happens at Phase 8.6/8.6b, correctly after the
row exists. Two different consumers share the string "VWAP_RECLAIM" as a concept;
only Trap Engine's own bull/bear trap-scoring is blinded by the ordering bug.

**No other live consumer reads `pkg["triggers"]` before it is populated.** Grep of
the full repository for `pkg.get("triggers"` / `pkg["triggers"]` finds five files:
`intelligent_orchestrator.py` (the patch call sites themselves), `trigger_layer.py`
(writer), `avshunter_trap_engine.py` (the confirmed-broken reader), and
`execution_decision_engine.py` — the latter is confirmed entirely dead code by
Pass A (Phase 9.5, every invocation line commented out). **No second instance of
this specific ordering-defect pattern was found in this span.**

### `classify_tier()` — field lineage, confirmed

**Module / function:** `classify_tier(row)`, `eod_candidate_engine.py:1669-1731`
(Phase 10 — one stage beyond this pass's nominal OI→GARCH boundary, documented here
because it is the direct, first consumer of this span's `trigger_quality`/
`trigger_go_eligible`/`eil_v3_verdict`/`fd_verdict` output fields).

Fields read directly (`:1670-1682`): `options_score`, `rr_underlying`/`rr` (fallback
chain — **confirmed absent from `eil_enriched.csv` entirely**; populated later
inside `build_candidate_manifest()` from a merge against the discovery/vanguard CSV,
not from this span — verified present and non-null in the final
`morning_candidates_{run_id}.csv`, so this is a field-lineage note, not a defect),
`sb_conv_score` (same — absent from `eil_enriched.csv`, merged in later),
`composite`, `eil_v3_verdict`, `trigger_quality`, `trigger_go_eligible`,
`catalyst_trade_class`, `catalyst_data_quality`, `pse_execution_mode`,
`effective_execution_verdict`, `fd_verdict` (via `_true_fatal_block()`, which — per
E2 — is confirmed dead/always-`False` in both reference runs, so the
`if _true_fatal_block(row): return "WATCH"` branch at `:1695-1696` never fires
empirically). `trigger_quality`/`trigger_go_eligible` are both fully populated
(0 nulls / 1,400) in the reference run — this span's trigger computation reaches
`classify_tier()` cleanly, unaffected by the Trap-Engine-specific ordering bug
documented above.

---

## E4 — Attrition and verdict divergence

### Row attrition — none, confirmed in both reference runs

| Stage | 08-18 rows | 08-16 rows |
|---|---|---|
| Options Intelligence output (Pass D boundary) | 1,400 | 1,347 |
| `superbrain_enriched_{run_id}.csv` | 1,400 | 1,347 |
| `eil_enriched_{run_id}.csv` | 1,400 | 1,347 |
| `garch_forecasts_{run_id}.csv` | 1,400 | 1,347 |

**Zero rows dropped anywhere in this span, in either reference run.** Every stage
from Options Intelligence output through GARCH is a 1:1 row-preserving transform —
confirmed by direct row-count comparison of every artefact, not inferred. This
contrasts sharply with Options Intelligence itself (Pass D: ~74% terminal
STAND_DOWN via genuine elimination) — this span never eliminates a row; it only
re-labels and re-scores the same 1,400/1,347 rows repeatedly. All attrition in this
document is about **verdict divergence and field loss**, not row loss.

### Verdict-field divergence table (08-18, n=1,400; all four span-relevant fields)

| `options_verdict`\* | `eil_v3_verdict` | count | % of 1,400 | % of 3,323 |
|---|---|---|---|---|
| STAND_DOWN (1,030) | EXECUTE_WITH_CAUTION | 936 | 66.9% | 28.2% |
| STAND_DOWN | EXECUTE | 8 | 0.6% | 0.2% |
| STAND_DOWN | BLOCKED | 84 | 6.0% | 2.5% |
| STAND_DOWN | WATCHLIST | 2 | 0.1% | 0.1% |
| ARMED (247) | BLOCKED | 119 | 8.5% | 3.6% |
| ARMED | EXECUTE_WITH_CAUTION | 85 | 6.1% | 2.6% |
| ARMED | EXECUTE | 27 | 1.9% | 0.8% |
| ARMED | WATCHLIST | 16 | 1.1% | 0.5% |
| EXECUTE (123) | BLOCKED | 47 | 3.4% | 1.4% |
| EXECUTE | EXECUTE_WITH_CAUTION | 51 | 3.6% | 1.5% |
| EXECUTE | EXECUTE | 19 | 1.4% | 0.6% |
| EXECUTE | WATCHLIST | 6 | 0.4% | 0.2% |

\* = `sb_final_verdict`, byte-identical per E1.

**Two headline numbers**:
- **944/1,400 (67.4% of 1,400 / 28.4% of 3,323) rows the Options layer rejected
  outright (`STAND_DOWN`) score `EXECUTE` or `EXECUTE_WITH_CAUTION` at the EIL
  microstructure layer** — the majority of the book. EIL's composite score is
  computed independently of `options_verdict`/`sb_final_verdict` (the latter feeds
  `ctx.superbrain_verdict`, used only as a fallback default in
  `build_execution_context_from_row()`, `:680` — not read anywhere inside
  `evaluate()`'s scoring path).
- **47/1,400 (3.4% / 1.4%) rows the Options layer said EXECUTE, EIL says BLOCKED
  outright** — a full reversal, driven by the S1 liquidity hard gate.

Then, per E2, `fd_verdict` mostly discards EIL's own verdict and reverts to a
campaign classification sourced from `options_verdict`: **45/54 (83.3%) of EIL's
own `EXECUTE`-scored rows are flattened to `fd_verdict == WATCHLIST`.** The net
shape of this span is: OI verdict → (mostly ignored) independent EIL
microstructure re-score → (mostly reverted back to OI-verdict-driven campaign
classification) `fd_verdict`. **A row's terminal `fd_verdict` can and does differ
from what a full, independently-computed five-strategy microstructure scoring pass
concluded about the same row, with no new market information entering between the
two computations** — this is exactly the "verdict changes without new information"
pattern the brief asks this pass to establish. It happens on the majority of the
book (97.8% of rows never let `eil_v3_verdict` reach `fd_verdict` at all, per E2).

### Reconciliation

At every branch point traced in this span (E1 passthrough, E1.5 WBS/Catastrophe
Gate, E2 EIL, E2.5 GARCH merge, E3 Trigger Layer), rows-in equals rows-out exactly
— no shortfall anywhere. The only "loss" in this span is field-level (E5) and
verdict-authority-level (above), never row-count-level.

---

## E5 — Field drop at the boundaries

### Boundary 1: Options Intelligence → this span

- **No loss of OI's own columns** — the SuperBrain passthrough (E1) is a full,
  unfiltered copy; all 627 (or 665, phantom-inclusive) OI columns survive into
  `superbrain_enriched.csv` unchanged.
- **One field added**: `sb_final_verdict` (= `options_verdict`, E1).
- **`_x`/`_y` suffix check, requested by the brief**: direct column-name check of
  `eil_enriched_{run_id}.csv` finds **zero** columns ending in `_x` or `_y` — the
  Pass D/C merge-boundary artefact does not survive (or does not recur) this far
  downstream. Confirmed by direct grep of the column list, not inferred.
- **`wbs_grade`/`wbs_score`** are written by WBS (E1.5) but never merged back —
  effectively a field that is *produced* within this span and then *dropped*
  before it reaches the row EIL and downstream consumers actually read, though —
  per E1.5 — this has no observable consequence since nothing consumes those
  context fields inside EIL's scoring math either.

### Boundary 2: this span → GARCH / handoff

- **`l3_*` GARCH fields**: written by `merge_garch_into_enriched()` (E2.5) into
  both `superbrain_enriched.csv` and `eil_enriched.csv`, in place, **after** EIL
  has already run — not a field drop in the conventional sense (the fields do
  arrive), but a field that arrives **too late to have informed the verdict fields
  sitting in the same row**. This is the single most consequential finding in this
  boundary — see E2.5.
- **`campaign_verdict`/`execution_verdict`** (E2): computed, decisive for control
  flow, absent from the `EIL_COLS` write-list — genuinely dropped before
  `eil_enriched.csv` is written. Not recoverable from that artefact; a reader would
  need the runner's own row dict at the moment of computation, which is not
  persisted anywhere.
- **The genuinely-raw EIL verdict** (`eil_result.eil_raw_verdict`, distinct from
  `eil_result.eil_verdict`) is computed inside `evaluate()` and then discarded —
  the CSV column sharing its name (`eil_raw_verdict`) actually holds a copy of the
  *other* field (E2). This is a naming collision, not a field drop per se, but it
  has the same practical effect: the true raw-verdict value never reaches disk.
- **`_percentile_override_active`/`fd_percentile_override`**: written, zero
  readers anywhere in the repository (E2) — not dropped, but functionally
  equivalent to being dropped, since nothing downstream can ever act on them.

---

## The funnel, updated (this span adds no attrition — restated with span context)

| Stage | Rows | % of 1,400 | % of 3,323 |
|---|---|---|---|
| Enter OI scoring loop (Pass C boundary) | 1,400 | 100.0% | 42.1% |
| OI terminal STAND_DOWN (Pass D) | 1,030 | 73.6% | 31.0% |
| OI terminal ARMED | 247 | 17.6% | 7.4% |
| OI terminal EXECUTE | 123 | 8.8% | 3.7% |
| → SuperBrain passthrough (E1) | 1,400 (no change) | 100.0% | 42.1% |
| → EIL scored (E2) | 1,400 (no change) | 100.0% | 42.1% |
| → GARCH merged (E2.5) | 1,400 (no change) | 100.0% | 42.1% |
| → enters Phase 10 candidate manifest | 1,135\* | 81.1% | 34.2% |

\* = `morning_candidates_{run_id}.csv` row count, read directly this pass as
context for E3's `classify_tier()` discussion — the 1,400→1,135 narrowing happens
inside `build_candidate_manifest()` (Phase 10), **outside this pass's assigned
span**; not traced further here. Flagged for whoever picks up Phase 10.

## The verdict-field divergence table (E4, restated as the close-out deliverable)

See E4 above for the full crosstab. Summary: **67.4%** of 1,400 OI-rejected rows
score EIL-tradeable; **3.4%** of OI-accepted rows are EIL-blocked outright;
**83.3%** of EIL's own EXECUTE-scored rows are reverted to WATCHLIST by the
campaign gate before reaching `fd_verdict`; **97.8%** of all rows never let
`eil_v3_verdict` reach `fd_verdict` at all, because the campaign/execution
REJECT-or-SKIP short-circuit (sourced from `options_verdict`, computed before EIL
runs) decides `fd_verdict` directly instead.

## What the SuperBrain bypass costs, itemised

1. The `ev_status=='DATA_WEAK'` risk-escalation gate (Standing Contract's named
   item) — confirmed present, confirmed unreachable (E1).
2. Six behavioural vetoes (V1-V6/V8).
3. The 5-condition convexity score and its campaign classification
   (CONVEXITY_INJECTION/CORE_CAMPAIGN/STAGED/AVOID), replaced by nothing — no
   downstream module recomputes an equivalent campaign tier from first principles;
   `_campaign_verdict()` in the EIL runner derives its own, structurally simpler,
   4-branch mapping directly off `sb_final_verdict` instead (E2).
4. The 5-stage DTE instrument ladder with alert prices.
5. Date-based time-stop rule generation.
6. Eight structured hard/soft verdict gates in `assemble_execution_plan()`
   (negative EV, low R:R, R:R floor, OIS floor, GARCH-tailwind, zero-runway,
   no-edge, STAGED-demotion) — collapsed to the single `options_verdict` copy plus
   whatever EIL and the campaign gate separately reconstruct (a materially
   different, less structured decision surface, per E4's divergence numbers).
7. Continuous conviction-based position sizing (0-100%, granular) — replaced
   pipeline-wide by hardcoded `fd_size = 0.0` (PSE retired) everywhere in this
   span.
8. The weighted, regime-aware risk-label system — replaced by nothing structurally
   equivalent; `eil_v3_verdict`'s four-token vocabulary is coarser.

## Corrections to Passes A-D

1. **Pass A §6, artefact chain table** — `superbrain_enriched_{run_id}.csv`'s
   reader list is incomplete: GARCH (`merge_garch_into_enriched`, item 29) also
   writes back into it in place, after EIL has already consumed it. See E0, E2.5.
2. **Sharpened, not contradicted**: the Standing Contract's "Trap Engine fires on
   148/1,400 rows, two of twelve signals can never fire — ordering" finding is
   confirmed with exact writer/reader line citations on both sides (E3), and its
   blast radius is now precisely scoped to Trap Engine's own consumption — it does
   not propagate to `classify_tier()`'s `trigger_quality`/`trigger_go_eligible`
   inputs, which are computed independently and correctly.
3. No correction found to Pass D's material; this pass's E1/E4 findings are
   consistent with and quantify further Pass D's three-way verdict-inconsistency
   finding (`options_verdict`/`options_verdict_tier`/`final_route`) by showing
   what happens to `options_verdict` specifically as it propagates through
   SuperBrain→EIL→`fd_verdict`.

## What this pass did not cover

- **Deep internals of the five S1-S5 microstructure strategies**
  (`liquidity_gate.py`, `iv_distortion.py`, `gex_flipper.py`, `obi_predictor.py`,
  `poc_timing.py`) — read only for field-reference purposes (confirming
  `wbs_grade`/`wbs_score` are unread there); their own internal thresholds and
  synthesis logic (e.g. `_synthesise_gex_map()`'s $500K-band assumptions) were not
  audited for correctness.
- **`wall_break_scorer.py`'s own internal EXECUTE-only filtering logic** — the
  123-row scope was confirmed empirically (exact ticker match), but the
  mechanism inside that script that produces the narrowing was not read.
- **The DEFANG / FATAL_BLOCK-reclassification pass**
  (`execution_intelligence_runner.py:2962-3170`, referenced in grep output) — a
  substantial block that appears to retroactively reclassify generic
  `CAMPAIGN_OR_EXECUTION_INVALID` FATAL_BLOCKs; not traced this pass beyond
  confirming (via the empirical `has_fatal_label` check in E2) that no row in
  either reference run reaches a state this pass would touch.
- **`inject_actuarial_into_eil_csv()`** (item 28, `:4229`) — call site confirmed,
  internals not read.
- **Full column-by-column consumption census of `eil_enriched.csv`'s ~897-899
  columns** — only the fields directly relevant to E1-E5's questions were traced;
  a Pass-D-style exhaustive census was out of scope for this pass's time budget.
- **`build_candidate_manifest()` / Phase 10 / `classify_tier()`'s full body** —
  read only as far as needed to confirm this span's fields (`trigger_quality`,
  `trigger_go_eligible`, `eil_v3_verdict`, `fd_verdict`) are consumed correctly;
  the 1,400→1,135 narrowing into `morning_candidates_{run_id}.csv` is flagged but
  not traced — that belongs to whoever audits Phase 10 next.
- **McMillan advisory layer** (Pass A item 33, runs after this span's Handoff
  Conflict Guard) — out of scope, confirmed later in sequence than GARCH.
- Did not re-verify `enforce_handoff_conflict_guard()`'s internals (item 31) —
  Pass A already flagged this as unread; still unread after this pass.

Pass E is otherwise complete against its brief: E1-E5 delivered in full, the
funnel restated with this span's (zero) attrition, the verdict-divergence table
quantified on real data from both reference runs, the SuperBrain-bypass cost
itemised, one correction filed against Pass A, and a fifth systemic
control-flow-ordering defect (GARCH-after-EIL) identified and evidenced to the
same standard as the four carried in from prior passes.
