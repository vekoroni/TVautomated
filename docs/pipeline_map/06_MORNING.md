# Pass G — The Morning Path

Read-only audit. No files edited, no pipeline executed. Citations against
`morning_gate.py` (1,528 lines), `intelligent_orchestrator.py`'s
`premarket_workflow()` (`:5189-5330`), `execution_gate.py` (429 lines),
`eod_candidate_engine.py`, and `contracts/lab_control.py`, all as they exist
on disk at the time of this pass.

## A note on reference-run availability — read this before the rest

The Standing Contract's designated reference runs, `20260818_041214`
(primary) and `20260816_075339` (secondary), are **evening-only artefacts**.
Direct directory search confirms neither run's `morning_validation/` folder
contains a `morning_validated_trades_*.csv` — `morning_gate.py` was never
executed against either run. This matches Pass D's and Pass F's own
"no morning-mode artefact exists among the reference runs available"
findings, independently reconfirmed here.

A repo-wide directory search *did* locate four genuine, previously-executed
morning-gate runs, under different run_ids than the two designated
references:

| run_id | evening pinned (UTC) | `gate_checked_at_utc` (actual morning-gate execution) | candidates in |
|---|---|---|---|
| `20260723_072618` | 2026-07-23 | 2026-07-23T14:18:34Z | 1,068 |
| `20260731_083130` | 2026-07-31 | 2026-07-31T14:21:16Z | 952 |
| `20260804_114554` | 2026-08-04 | 2026-08-04T17:41:00Z | 795 |
| `20260809_195823` | 2026-08-09 18:58 UTC | **2026-08-10T16:41:02Z** | 848 |

None shares a run_id with, or was executed against the same universe as,
the 08-16/08-18 evening reference runs. `20260809_195823` is the closest by
date (its evening half-run 7-9 days before the references; its actual
morning-gate execution one day after its own evening run). **This pass uses
`20260809_195823` as the primary morning-artefact source, and the
aggregate of all four as a secondary, larger sample (3,663 rows total) for
frequency questions.** Every number below states which of these two bases
it comes from. Where the brief asks a question specifically about the 08-18
run's 184 `BLOCK_SPREAD` rows, this pass answers the *general mechanism*
with certainty (from source) and supplies a *same-mechanism proxy
quantification* from `20260809_195823` — not a trace of the literal 184
rows, which were never put through `morning_gate.py`. This is flagged
explicitly at G3 and again in Closing Synthesis; it is the single largest
gap in this pass.

---

## G1 — Entry point and the flow

**The morning path is *not* the command CLAUDE.md documents.** CLAUDE.md's
"Morning run command" section states:
```
python morning_thesis_validator.py --tiers A,B,C,WATCH --max-signals 0 --live
```
`morning_thesis_validator.py` is the retired module (Standing Contract,
confirmed again this pass by its complete absence from every import in
`premarket_workflow()`, read in full). **The actual, live entry point is:**
```
python intelligent_orchestrator.py --morning
```
(or the deprecated alias `--premarket` — both dispatch to the identical
function, per Pass A §1, `intelligent_orchestrator.py:5611-5631`). This is
a documentation/reality discrepancy of the same kind Pass A catalogued for
all thirteen evening phase labels — CLAUDE.md's own stated morning command
would, if actually run, invoke a module the pipeline's own code no longer
calls.

**Full call chain, traced by direct read of `premarket_workflow()`
(`intelligent_orchestrator.py:5189-5330`):**

1. `main()` argparse dispatch (Pass A) → `premarket_workflow(run_id=args.run_id)`, `:5611-5623`.
2. Run-id resolution (`:5205-5222`): CLI `--run-id` wins; else read `cfg.OUTPUT_DIR/latest.json`'s `run_id` key. Hard-fails (`return False`) if neither resolves.
3. Path construction (`:5224-5227`):
   - `_candidates_path` = `RUNS_DIR/{run_id}/morning_validation/morning_candidates_{run_id}.csv`
   - `_output_path` = `RUNS_DIR/{run_id}/morning_validation/morning_validated_trades_{run_id}.csv`
   - `_final_book_path` = `RUNS_DIR/{run_id}/intelligence_lab/final_opportunity_book_{run_id}.csv` (fallback, **existence-check only** — see below)
4. Existence guard (`:5229-5243`): if *neither* `_candidates_path` nor `_final_book_path` exists → hard-fail. If `cfg.MORNING_VALIDATION_ENGINE` (i.e. `morning_gate.py` itself) is not found on disk → hard-fail.
5. `run_catalyst_truth_layer(_run_id, stage="pre_morning_validation")` (`:5251`) — patches `morning_candidates.csv` in place with catalyst enrichment *before* the gate reads it (in-code comment, "FIX 7": catalyst truth previously ran before `morning_candidates` was written, so catalyst fields never reached it).
6. `from morning_gate import run_morning_gate; results = run_morning_gate(run_id=_run_id, spread_threshold=25.0)` (`:5253-5258`).
7. Phase 11 — Execution Gate (`:5266-5297`), `from execution_gate import run_execution_gate`, non-critical (wrapped `try/except`, logs a warning and continues on any failure).
8. Lab/Interpreter handoff refresh (`:5300-5324`): `write_final_run_manifest(_run_id, cfg.RUNS_DIR, pipeline_mode="MORNING_VALIDATION")`, `write_final_opportunity_book(...)`, then `pipeline_interpreter.ma_inputs_sync.sync_file()` on three output paths — all non-critical.
9. Returns `True` at `:5326` if the `try` block (steps 6-8) completed without an exception reaching `:5328`.

**Critical/non-critical:** only step 6 (the morning-gate call itself) is
inside the `try` whose `except` at `:5328-5330` returns `False` — a
`morning_gate.py` exception (e.g. its own `FileNotFoundError` if
`morning_candidates_{run_id}.csv` is absent — see G3) fails the whole
workflow. Steps 7 and 8 are independently wrapped and cannot fail the
workflow once step 6 succeeds.

**Confirming `morning_thesis_validator.py` is not on this path:** direct
read of the full 141-line `premarket_workflow()` body shows exactly one
`from X import Y` for validation logic — `from morning_gate import
run_morning_gate` (`:5254`). No reference to `morning_thesis_validator`
anywhere in the function, in `intelligent_orchestrator.py`'s import block
(not separately re-checked this pass beyond the function body, which is
sufficient — Python does not call unimported functions), or in
`morning_gate.py`'s own header, which states outright: *"Morning Gate v1.2
— Five checks. Replaces morning_thesis_validator.py entirely."*
(`morning_gate.py:1-4`). This corroborates the Standing Contract's carried-in
finding without re-deriving it from scratch.

---

## G2 — The five checks

Module docstring order (`morning_gate.py:6-16`) is CHECK1 Invalidation →
CHECK2 Macro → CHECK3 Contract → CHECK4 Bond macro → CHECK5 Layer-3 model
risk. **This is not the actual verdict-priority order in code** — see the
priority-order defect noted at the end of this section.

### CHECK 1 — Invalidation intact

**Reads:** `evening_invalidation_price` / `invalidation_price` /
`invalidation_level` (first non-blank wins) and direction
(`evening_direction`/`canonical_direction`/`resolved_direction`/`direction`).
**Function:** `_check_invalidation()`, `morning_gate.py:769-797`.
**Threshold:** none numeric — a level comparison (`live_price <=
invalidation` for CALL, `>=` for PUT).

**Fails open** when the invalidation level itself is missing/≤0 — returns
`(True, "WARN - no invalidation level on record...")`, `:782-783`. This part
of the Standing Contract's characterisation is confirmed exactly.

**When `live_price` is missing, the function returns `(False,
"CANNOT_VERIFY...")`** (`:774-775`) — read alone this looks like a fail
*closed* (BLOCK), not fail *open*. But `run_gate()` intercepts this case
**before** the block/flag branching even runs: `invalidation_unverified =
live_price is None` is checked **first**, ahead of everything else
(`:1146-1168`). The resulting verdict is **`FLAG`**, `permission="WAIT"`,
`route="WAIT_LIVE_PRICE"`, `lane="LIVE_PRICE_UNAVAILABLE"`,
`entry_action="NO_TRADE"` — not a `BLOCK`, and not a false `GO` either.
**Precise characterisation: this is neither the Standing Contract's assumed
"fails open to a GO/false-positive risk" nor a hard BLOCK — it is a
distinct, always-non-tradeable FLAG/WAIT state.** The risk it does carry is
narrower than a false-GO: a naive downstream reader who treats
`verdict != "BLOCK"` as "still eligible" would see this row alongside the
528 genuine `CONTRACT_REPAIR`-type FLAGs without knowing its cause is a
totally unverified thesis, not a repairable contract — but `entry_action`
and `route` are always distinguishable if read.

**Quantified** (no data exists for the two designated reference runs — see
header note): across the four available real morning-gate executions
(3,663 rows total), `live_price` was null for **2/3,663 rows (0.05%)**,
both in `20260804_114554`. This is a very low hit rate — Polygon's snapshot
endpoint succeeded for essentially every ticker in the available sample.

**Genuine BLOCK** (live price present, invalidation breached): **97/3,663
(2.65%)** across the four runs — the module's only true hard BLOCK path.

### CHECK 2 — Macro regime unchanged

**Reads:** EOD-side regime (`morning_macro_regime_state`/`macro_regime`/
`regime_state`/`evening_regime_state`) vs. current regime, loaded fresh from
`dropbox/macro/macro_intelligence_latest.json` via `_load_macro_state()`
(`:512-541`) — **this file, not a per-row column, is the live re-fetch for
this check**; it is a single macro snapshot shared across every row in the
run, not a per-ticker live call.
**Function:** `_check_macro()`, `:804-822`. **Flip logic:**
`_regime_flipped()` (`:718-738`) only counts a *base-direction* change
(BULLISH/BEARISH/NEUTRAL); `TRANSITIONAL` variants of the same base are not
flips.
**Fails open** when the EOD regime field is missing/`UNKNOWN` — returns
`True`, `:816-817`.
**Never BLOCKs** — `run_gate()` only ever appends a `flag_reasons` entry for
a macro failure (`:1153-1154`); there is no code path from CHECK2 to
`BLOCK`.
**Quantified:** 0/3,663 fails across all four available runs — regime never
flipped in the sampled window. This says the mechanism has not been
observed to fire, not that it cannot.

### CHECK 3 — Contract liquid

**Function:** `_check_contract()`, `:829-876`. This is the richest of the
five — not a single spread test but an ordered sequence, the first
sub-condition that fails wins:
1. **Side conflict** — if `_apply_thesis_direction_guard()` (`:229-281`,
   run earlier in `run_gate()`) detected the live/repaired contract's side
   conflicts with a *locked* footprint direction, fail immediately,
   **before bid/ask are even inspected** (`:838-839`).
2. **Missing quote** — `bid is None or ask is None` → fail (`:845-846`).
3. **Invalid quote** — `bid<=0 or ask<=0` → fail (`:848-849`).
4. **Spread too wide** — `spread_pct > spread_threshold` (25.0 default,
   passed as a literal `25.0` from `premarket_workflow():5257`, not read
   from any config file) → fail (`:851-852`).
5. **Delta out of band** — `abs(delta) < 0.20` or `> 0.70` → fail
   (`:859-862`).
6. **IV invalid** — `live_iv <= 0` or `> 2.50` → fail (`:865-868`).
7. **IV compression** — `live_iv / eod_iv < 0.70` (premium deflated >30%
   since EOD) → fail (`:873-874`).
Passing all seven → `(True, "Contract liquid — bid=... ask=... spread=...")`.

**Sub-cause breakdown, empirical, 3,663 rows across all four available
runs** (bucketed by reason prefix):

| Bucket | Count | % of 3,663 |
|---|---|---|
| PASS (liquid) | 1,142 | 31.2% |
| Side conflicts with preserved thesis direction | 972 | 26.5% |
| Spread too wide (real, finite %, over threshold) | 874 | 23.9% |
| Contract quote invalid (bid=0 or ask=0) | 346 | 9.4% |
| No live contract quote at all | 278 | 7.6% |
| Delta too high (>0.70) | 44 | 1.2% |
| IV compression (>30% deflation vs EOD) | 5 | 0.1% |
| Delta too low (<0.20) | 2 | 0.1% |

Overall `check_contract_pass` fail rate: **2,521/3,663 (68.8%)**. The
single largest sub-cause is **not** liquidity in the ordinary sense — it is
the direction-guard side-conflict check, which fires *before* any bid/ask
data is examined and therefore masks the true live liquidity of ~972 rows'
contracts (see G3, the spread==2.0 trace, where several side-conflict rows
turn out to have had perfectly good live spreads that the check never
reported because it exited on the side-conflict branch first).

**Repair mechanism** (`_try_live_repair_alternatives()`, `:414-447`): when
the primary contract fails `_check_contract()`, the gate tries up to three
EOD-generated `alternative_contract_N` symbols against live MarketData
quotes, in order, stopping at the first that passes. Empirically,
`contract_repair_resolved_at_open` is `TRUE` for a subset of rows where a
repair was both attempted and successful; `morning_contract_repair_used`
totals across the four runs: `TRUE` 974, `FALSE` 1,820, not-attempted (no
primary contract or no alternatives) 869 — **a 34.9% success rate among
rows where a repair was actually attempted (974/2,794)**, 26.6% of all rows.

### CHECK 4 — Bond macro clear

**Reads:** `dropbox/macro/bond_macro_state.json` via `_load_bond_macro()`
(`:544-620`), staleness threshold `BOND_MACRO_MAX_AGE_H=26` hours (explicitly
sized to "cover overnight gap to 09:45 ET" per in-code comment, `:62`).
**Function:** `_check_bond_macro()`, `:741-762`.
**Fails open** (`True`) when the file is missing, unreadable, or stale —
`:751-752`, `:553-560`, `:572-577` — "bond check is advisory infrastructure"
per the function's own docstring.
**Never BLOCKs** — `flag_reasons` only, `:1159-1160`.
**Quantified:** 0/3,663 fails across all four available runs.

### CHECK 5 — Layer 3 model risk (docstring's fifth check, but see priority note)

**Function:** `_layer3_model_risk_guard()`, `:128-188`. Flags (any
combination): `VOL_HARDCAP` (`l3_forward_realised_vol >= 2.50`),
`LOW_CONF_HIGH_VOL` (`l3_vol_forecast_conf <= 65` AND
`l3_forward_realised_vol >= 1.50`), `THIN_HISTORY` (`l3_n_bars < 100`),
`IV_TAILWIND_EXTREME` (`|l3_iv_tailwind_score| > 1.50`).
**Not fail-open/closed in the CHECK1/4 sense** — a `None` source field
simply cannot trigger its own condition (each `if` requires the field to be
non-`None`), so missing L3 data silently produces zero flags rather than
either passing or failing explicitly; this is a soft no-op on missing data,
not a documented fallback.
**Never BLOCKs** — `flag_reasons` only, `:1157-1158`.
**Quantified:** 21/3,663 (0.57%) fail — flag composition: `IV_TAILWIND_EXTREME`
(3 of the observed flagged rows in the single-run sample), `LOW_CONF_HIGH_VOL`
(1), `VOL_HARDCAP|LOW_CONF_HIGH_VOL` combined (1), plus additional
single-flag rows in the other three runs not individually re-broken-out
this pass.

### The priority-order defect (new finding this pass)

The module docstring's numbering (CHECK1→2→3→4→5) does **not** match the
actual `elif` resolution order inside `run_gate()` (`:1146-1217`), which is:

```
0. invalidation_unverified (live_price missing)   → FLAG/WAIT/NO_TRADE
1. genuine CHECK1 failure (invalidation broken)   → BLOCK
2. CHECK3 failure (contract)                      → FLAG/CONTRACT_REPAIR
3. CHECK5 failure (Layer-3 model risk)             → FLAG/MODEL_RISK_REVIEW
4. CHECK2 failure (macro)                          → FLAG/ARMED/MACRO_REVIEW
5. CHECK4 failure (bond macro)                     → FLAG/ARMED/BOND_MACRO_REVIEW
6. any remaining flag_reasons (should be unreachable given 2-5 above)
7. else → GO
```
So contract liquidity (docstring CHECK3) outranks model risk (docstring
CHECK5), which outranks macro (docstring CHECK2) and bond (docstring
CHECK4) in what actually gets reported as `flag_reason`/`route` when a row
fails more than one check simultaneously — the compiled `flag_reason`
string (`"; ".join(flag_reasons)`) does still concatenate every failing
check's text, so no information is lost, but the single-valued
`morning_execution_route`/`morning_unlock_condition`/`execution_permission`
fields reflect only the highest-priority failure, in the code's actual
order, not the docstring's stated order. This is the same class of defect
as the Standing Contract's six known control-flow-ordering issues
(Regime Screener, Trap Engine VWAP, `_x`/`_y` merge, the two OI spread
gates, GARCH-after-EIL, two unreachable Catalyst Truth patch targets) —
documentation states one order, code implements another.

### What happens to a flagged/blocked row

No check except genuine CHECK1 (live price present, invalidation broken)
ever removes a row from the trader's view or sets an automatic action:
every other failure path terminates in `entry_action ∈
{MANUAL_REVIEW, SELECT_LIQUID_CONTRACT}` — a human decision point, not a
kill. Only genuine CHECK1 failure sets `entry_action="NO_TRADE"` with
`verdict="BLOCK"`. A row remains present in `morning_validated_trades.csv`
regardless of verdict — **no row is ever dropped by `morning_gate.py`
itself** (see Reconciliation).

---

## G3 — Does the morning path re-fetch and re-evaluate?

### Re-fetch: yes, confirmed

`_fetch_all_live()` (`:450-505`) calls, per ticker, live, at gate-run time:
Polygon's snapshot endpoint for equity price/volume/VWAP
(`_fetch_live_price`, `:332-360`), MarketData.app for the options quote
(`_fetch_live_contract`, `:363-395`, plus repair-alternative attempts), and
MarketData.app's chain endpoint for ATM call/put IV skew
(`_fetch_options_skew`, `:664-715`) — three genuinely live, synchronous API
calls per row, executed via an 8-worker `ThreadPoolExecutor` (`:493`), not
a cached/replayed snapshot.

### Which rows: only the 1,135-manifest-shaped survivor set, not the full 1,400

`run_morning_gate()` reads **exactly** `morning_candidates_{run_id}.csv`
(`:1263`, hardcoded path, `pd`-free `csv.DictReader` at `_read_csv()`) and
**raises `FileNotFoundError`** if it is absent (`:1267-1269`) — there is no
fallback to `final_opportunity_book_{run_id}.csv` inside `morning_gate.py`
itself (that fallback exists only in `premarket_workflow()`'s *existence
check*, `:5229-5239`, which lets the workflow proceed past its own guard if
either file exists — but the actual call at `:5254-5258` still only ever
passes `run_id`, and `run_morning_gate()` internally still only ever
constructs the `morning_candidates_{run_id}.csv` path. **If
`morning_candidates.csv` is absent but `final_opportunity_book.csv`
exists, the workflow passes its entry guard and then fails inside the
`try` block with an uncaught `FileNotFoundError`, landing in the
`except` at `:5328-5330` — "Morning validation failed."** This is a live
discrepancy between the two guard conditions worth flagging: the existence
check implies two valid inputs, but only one is ever actually read.

It therefore reads none of: `eil_enriched_{run_id}.csv` (the full 1,400),
`eod_dropoff_audit_{run_id}.csv` (the 15 hard-blocked rows), or
`morning_blocked_review_{run_id}.csv` (the 250 `eil_v3_verdict==BLOCKED`
rows) — confirmed by full-file read of `morning_gate.py`; none of those
three filenames appears anywhere in it.

**The 265 rows excluded at Phase 10 (15 hard-block `EOD_NO_OPTIONS_ROUTE` +
250 `eil_v3_verdict==BLOCKED`, per Pass F's exact reconciliation) never
reach the morning gate and get no second look.** This is terminal, not
recoverable within this run.

### The 184 `BLOCK_SPREAD` rows specifically — mechanism settled, exact 08-18 cohort unverified

**By source trace (certain):** `eod_candidate_engine.py`'s
`EOD_REPAIRABLE_TOKENS` set (`:163-187`) contains the literal token
`"SPREAD"`. `_eod_failure_class()` (`:445-453`) checks the row's combined
reason blob against three token sets in order — `EOD_NO_OPTIONS_ROUTE_TOKENS`,
`EOD_STRUCTURAL_BLOCK_TOKENS`, then `EOD_REPAIRABLE_TOKENS` — and a blob
containing `"SPREAD"` (Options Intelligence's own `BLOCK_SPREAD` reason
text, D3) matches only the third, returning `"REPAIRABLE_ADVISORY"`, never
`"NO_OPTIONS_ROUTE"` or `"STRUCTURAL_BLOCK"`. `_eod_candidate_status()`
(`:865-932`) only returns a hard-block status (`EOD_NO_OPTIONS_ROUTE`/
`EOD_STRUCTURAL_BLOCK`) when `_eod_failure_class()` returns one of those
two classes (`:878-883`) — a `REPAIRABLE_ADVISORY` classification falls
through to the rest of the function, which (via `contract_repair_required`,
`:902-903`, or `eil_verdict=="EXECUTE_WITH_CAUTION"`, `:918-919`) most
commonly resolves to `EOD_THESIS_READY_REPAIR_AT_OPEN` — a member of
`EOD_CARRY_FORWARD_STATUSES` (`:119-133`) and therefore included in
`manifest_mask` (Pass F). **By construction, `BLOCK_SPREAD` rows are not
hard-blocked at Phase 10; the majority reach `morning_candidates.csv`.**

**By empirical proxy (from `20260809_195823`, not the 08-18 run — see
header note):** 73/848 candidates (8.6%) in that run's
`morning_candidates.csv` carried the exact `contract_spread_pct == 2.0`
EOD arithmetic identity (D3's mechanism), confirming rows with this defect
class do generally reach the morning input. Tracing those 73 through
`morning_gate.py`'s live fetch:

| Outcome | Count | % of 73 |
|---|---|---|
| Resolved to a genuinely liquid, passing contract (`check_contract_pass=TRUE`) | 3 | 4.1% |
| — of which, only via the alternate-contract repair mechanism | 2 | |
| — of which, the *original* bid=0 contract itself now liquid | 1 | |
| Reproduced the identical `bid=0`/200%-spread identity live (real, persistent illiquidity) | 39 | 53.4% |
| Real, finite, but still-too-wide live spread (25%–176%) | remainder | — |
| Verdict=`BLOCK` (unrelated — live price breached invalidation) | 1 | 1.4% |

All 73 received *some* live quote (0 null) — MarketData.app answered every
request — but for the majority the answer was the same structural
condition (no resting bid), not fresher/better data. **Net: the evening
`BLOCK_SPREAD` verdict is architecturally recoverable (every affected row
gets a second, live look) but empirically resolves favorably only a small
minority of the time in this proxy sample (≈4%) — not "provably premature"
as a blanket claim, and not "terminal" either. The specific 184-row 08-18
cohort was never itself run through `morning_gate.py` and remains
unverified** — this is the single largest unresolved item this pass
inherits from Pass D and cannot close without either a recorded 08-18
morning-mode run (does not exist) or re-running the pipeline (out of
scope).

### `BLOCK_NO_CONTRACT` rows (~819-831/1,400, the dominant Phase-7 attrition cause)

These are the genuine hard-block class at Phase 10 — no chain, no eligible
contract exists at all for the ticker under `select_best_contract()`'s
gates. `_eod_failure_class()` would classify these as `NO_OPTIONS_ROUTE`
(the `"NO_LIVE_QUOTE" `/ absent-contract reason blob matching
`EOD_NO_OPTIONS_ROUTE_TOKENS` such as `"NO_CONTRACT_MARKET"`,
`"NO_VIABLE_OPTION_AFTER_SEARCH"`), producing `EOD_NO_OPTIONS_ROUTE` — one
of the 15 hard-blocked statuses excluded from `manifest_mask` in the 08-18
run (Pass F). **These rows never reach `morning_candidates.csv` and get no
second look — confirmed terminal**, since no artefact carrying them
(`eod_dropoff_audit_{run_id}.csv`) is read anywhere in the morning path.

---

## G4 — Does the morning path have `data_mode` awareness?

**No branch on `data_mode` exists in `morning_gate.py`** — confirmed by
full-file read: zero `argparse` parameter, zero `args.data_mode`
reference, zero conditional keyed on any mode string. This mirrors Pass
D's finding for Options Intelligence exactly.

**`morning_gate.py` does not call Options Intelligence code at all** — no
import of `avshunter_options_intelligence.py` anywhere in the file. It
implements a fully independent live-quote fetch (Polygon + MarketData.app,
directly) and its own CHECK3 liquidity logic, not a re-invocation or
data-mode-aware branch of the OI module.

**Three independently-thresholded spread/delta gates exist across the
pipeline** (not one gate applied three times — three separately-coded
implementations, confirmed by direct read of all three files):

| Stage | Spread threshold | Delta band |
|---|---|---|
| OI `derive_verdict()` (EOD, Pass D) | `MAX_SPREAD_PCT=0.25` (second gate); separate selection-time `spread_limit=0.15` for the `1_5d` horizon bucket | not directly comparable — OI's delta filtering happens inside `select_best_contract()`, not re-verified this pass |
| `morning_gate.py` CHECK3 | 25.0% (`spread_threshold` param; passed as the literal `25.0` from `premarket_workflow():5257`, not read from any config) | 0.20–0.70 hard band |
| `execution_gate.py` Phase 11 GATE-01/02 | `SPREAD_FULL=8%` (full size) / `SPREAD_MAX=15%` (else `CONTRACT_REPAIR`) | 0.20 hard-min / 0.85 hard-max; 0.30–0.60 soft band (penalty outside) |

A contract can pass morning_gate's 25% CHECK3 and still be routed to
`CONTRACT_REPAIR` by execution_gate's tighter 15% GATE-01 minutes later in
the same workflow run (`execution_gate.py:197-199`) — three sequential,
non-identical liquidity bars, not a single threshold re-checked.

**Freshness window:** neither module has an explicit "quote age" staleness
check on the market data itself. Both `morning_gate.py` and Options
Intelligence fetch "live" quotes synchronously from the same two providers
(Polygon, MarketData.app) at whatever moment each process happens to run —
Pass D already established OI always fetches live regardless of
`--data-mode`; this pass confirms `morning_gate.py` has no cache or
max-age check on its own price/contract fetch either (fetch-and-use, no
staleness gate). The only staleness windows in `morning_gate.py` govern the
macro (`MACRO_MAX_AGE_H=14h`) and bond-macro (`BOND_MACRO_MAX_AGE_H=26h`)
side-files, not the market quotes.

**Stated plainly, matching the brief's own request:** the same 25% CHECK3
spread threshold and 0.20–0.70 delta band apply no matter when in the
session the gate happens to run — there is no market-open-vs-closed branch
inside `morning_gate.py`. The module's docstring says it is meant to run
"at 09:45 ET — 15 minutes after open," but nothing in code enforces or even
checks that; `20260809_195823`'s actual `gate_checked_at_utc` (16:41 UTC ≈
12:41 ET) shows it can and does run well outside that window in practice.

---

## G5 — Which verdict does the morning act on?

**None of the five Pass-F evening verdict fields gate anything in
`morning_gate.py`.** Confirmed by full-file grep: `fd_verdict`,
`eil_v3_verdict`, `eil_signal_verdict`, `fd_advisory_verdict`, and
`thesis_decision` appear **zero times** in `morning_gate.py`'s source. The
five CHECK functions (CHECK1-5, G2) read only live-fetched fields, the EOD
invalidation/direction/regime fields, and the L3 model-risk fields —
never any of the five verdict columns.

**The five evening verdict fields are carried through unchanged as
passthrough display columns**, not consulted or recomputed. Empirically
(run `20260809_195823`, 848 rows): `fd_verdict`/`thesis_decision`
distribution is **byte-identical** before (`morning_candidates.csv`) and
after (`morning_validated_trades.csv`) — WATCHLIST 830 / EXECUTE_WITH_CAUTION
13 / EXECUTE 5 in both; `eil_v3_verdict` likewise identical — EXECUTE_WITH_CAUTION
791 / WATCHLIST 30 / EXECUTE 27 in both.

**`morning_gate.py` computes its own verdict fresh, from CHECK1-5 alone**,
in a **sixth, independent vocabulary**: `verdict ∈ {GO, FLAG, BLOCK}` and
`execution_permission`/`morning_execution_permission` ∈ {GO, WAIT,
CONTRACT_REPAIR, MODEL_RISK_REVIEW, ARMED, BLOCKED} (`:1219-1230`). Neither
matches any of Pass F's five evening vocabularies.

### Practical impact, quantified (`20260809_195823`, 848 rows)

| Eligibility rule | Eligible rows | % of 848 |
|---|---|---|
| morning_gate's own fresh `verdict == "GO"` | 300 | 35.4% |
| carried-through `eil_v3_verdict == "EXECUTE"` | 27 | 3.2% |
| carried-through `fd_verdict == "EXECUTE"` (= `thesis_decision`) | 5 | 0.6% |

A downstream reader who filters the **identical morning output artefact**
on the evening `fd_verdict` field instead of morning_gate's own fresh
`verdict` field would see **60× fewer** eligible rows (5 vs. 300). Pass
F's five-verdict evening divergence is not resolved by the morning gate —
it is compounded by a sixth, independently-computed vocabulary layered
alongside the original five, with no reconciliation between them anywhere
in `morning_gate.py`.

### A third, downstream layer: `contracts/lab_control.py`

`write_final_opportunity_book()` (called from `premarket_workflow():5307`)
invokes `resolve_lab_tradeability()`/`apply_lab_resolution()`
(`contracts/lab_control.py`), which computes a **seventh** field,
`lab_verdict`, in its **own** vocabulary: `GO / GO_LIMIT / PROBE /
CONTRACT_REPAIR / MORNING_VALIDATION_REQUIRED / ARMED / WAIT / BLOCKED`
(`:1381`, `:1540`). This reads `mv_execution_permission`, sourced (first
non-blank wins) from `mv__morning_execution_permission`,
`morning_execution_permission`, `mv__execution_permission`,
`mv_execution_permission`, `execution_permission` (`:822`) — this **does**
correctly pick up `morning_gate.py`'s real `execution_permission`/
`morning_execution_permission` field.

**This is where the brief's cited "rule of record" (verdict GO/GO_LIMIT/PROBE
+ `live_data_mode=LIVE`) actually originates — not from `morning_gate.py`
itself**, which never emits `GO_LIMIT`, `PROBE`, or any field literally
named `live_data_mode`. Specific findings:

- A legacy fallback path (`lab_control.py:827-846`, keyed on `mv__verdict`/
  `mv_verdict`, mapping values like `EXECUTE`/`CONFIRMED`/`STARTER` →
  `GO`/`GO`/`PROBE`) exists to translate `morning_thesis_validator.py`'s
  (retired) richer output vocabulary into `lab_verdict`'s inputs. Since
  `morning_gate.py` never writes `GO_LIMIT`/`PROBE`, nor the
  `mv__verdict`/`mv_verdict` field names this fallback keys on, **this
  fallback path is dead code against the current live producer.**
- `morning_present` (`lab_control.py:856`) is computed by testing
  `mv_execution_permission` against exactly `{"GO","GO_LIMIT","PROBE",
  "ARMED","CONTRACT_REPAIR","WAIT","BLOCKED"}`. `morning_gate.py`'s sixth
  real permission value, **`MODEL_RISK_REVIEW`, is not in that set** — a
  CHECK5-flagged row's `morning_present` flag evaluates `False` even though
  `morning_gate.py` did run and did produce a permission for it. Rare in
  the sample (1/848 rows in `20260809_195823` carried `MODEL_RISK_REVIEW`)
  but a real, reportable schema mismatch, same class as the `execution_mode`
  100%-empty finding Pass F flagged at the evening manifest boundary.
- `live_data_mode` is read at `lab_control.py:591` (`row.get("live_data_mode")`,
  checked against `{"PAPER","SIMULATED","REPLAY"}` to detect non-live
  morning data) but is **never written by `morning_gate.py`** — confirmed,
  zero occurrences in the 1,528-line file. This check is permanently inert
  on the current pipeline (always evaluates "not paper mode", since the key
  is always absent), not a working data-mode detector.
- **Not independently verified further this pass:** `resolve_lab_tradeability()`'s
  full body past `:864` (the `morning_present`/`legacy_mv` resolution logic)
  was not traced to its final `lab_verdict`/`tradeable` assignment in
  depth, nor was an actual `final_opportunity_book_*.csv` opened to confirm
  `lab_verdict` populates as this trace predicts. Flagged as the open item
  for whoever picks this up next.

---

## G6 — `morning_validated_trades` schema and eligibility

**Zero columns dropped between input and output.** Empirically confirmed
(`20260809_195823`): every one of the 848 candidate-file columns survives
unchanged into `morning_validated_trades.csv` — full passthrough, no
evening field is lost at this specific boundary (contrast with the
evening-side manifest boundary Pass F found, where `execution_mode` was
silently 100% empty and `campaign_verdict`/`execution_verdict` never
arrived at all — those losses happened upstream of this point, and this
pass finds nothing new is lost *at* this point).

**111 new columns added by `morning_gate.py`**, by family: `check_*`
(the five check pass/reason pairs), `live_*` (price/contract/skew fetch
results), `bond_*` (CHECK4 display fields), `macro_*` (CHECK2 display
fields), `china_*` (AG-05 exposure modifier, display-only), `earnings_*`
(AG-01 catalyst calendar, display-only), `garch_*` (AG-04 vol-regime
transition discount, display-only), `enrichment_*` (AG-08 delta bias,
display-only), `skew_*` (AG-03 options skew), plus the Lab-compatibility
aliases (`morning_gate_verdict`, `execution_permission`,
`morning_execution_permission/route/lane`, `live_validation_state`) and the
v6 actuarial display pass-through (`iv_regime`, `horizon_bucket`,
`crabel_state` — explicitly never-gating, per both the module docstring
and direct confirmation no CHECK function reads them).

**Which fields determine eligibility:** per G5, the brief's stated "rule of
record" (`verdict ∈ {GO, GO_LIMIT, PROBE}` + `live_data_mode=LIVE`) matches
**no field `morning_gate.py` actually writes**. The only fields that
actually gate anything at this stage are `morning_gate.py`'s own
`verdict`/`execution_permission` (computed fresh from CHECK1-5, G2) and,
one step further downstream, `lab_control.py`'s `lab_verdict`/`tradeable`
(sourcing logic confirmed correct at `:822`; final values not
independently re-verified this pass, per G5's open item).

**What sets `live_data_mode`, and what happens on a failed/partial live
fetch:** `live_data_mode` itself — **UNVERIFIED**; no writer for this exact
field name was located anywhere in `morning_gate.py`, and this pass did not
locate an alternate writer elsewhere in the repo within scope. What *is*
confirmed: `_fetch_live_price()`/`_fetch_live_contract()` never raise — on
any exception each returns a diagnostic-marker dict (`{"live_fetch_error":
..., "live_data_source": "POLYGON_FAILED"}` or
`{"live_options_source": "MARKETDATA_FAILED", "live_options_error": ...}`,
`:359-360`, `:393-395`) rather than dropping the row. **A row never drops
on a failed fetch — it persists with a stale/absent value plus a
`_FAILED`-suffixed marker column**, and if the failure is specifically the
equity price (`live_price` absent), the row routes through the
`invalidation_unverified` FLAG/WAIT/NO_TRADE path (G2, CHECK1) — 2/3,663
rows in the available sample.

---

## Reconciliation

**For the designated 08-18 run specifically: no reconciliation is
possible.** `morning_gate.py` was never executed against
`morning_candidates_20260818_041214.csv` (1,135 rows) — no
`morning_validated_trades_20260818_041214.csv` exists on disk.

**For the four available real executions, reconciliation is exact and
trivial: `morning_gate.py` drops no rows.** `run_gate()` iterates every
input row and appends exactly one result dict per row (`:1345-1359`) — no
per-row exclusion logic exists inside the function. Confirmed across all
four:

| run_id | candidates in | validated_trades out | shortfall |
|---|---|---|---|
| `20260723_072618` | 1,068 | 1,068 | 0 |
| `20260731_083130` | 952 | 952 | 0 |
| `20260804_114554` | 795 | 795 | 0 |
| `20260809_195823` | 848 | 848 | 0 |

Every excluded row belongs to the *evening* side (Pass F's 265-row
reconciliation at Phase 10) — the morning gate only ever relabels rows
(`GO`/`FLAG`/`BLOCK`), never removes them.

Verdict split, `20260809_195823` (used as the primary proxy this pass):
GO 300 (35.4%) / FLAG 529 (62.4%, split `execution_permission` CONTRACT_REPAIR
528 + MODEL_RISK_REVIEW 1) / BLOCK 19 (2.2%).

---

## Closing Synthesis

### The completed funnel: 3,323 → tradeable

The evening half is exact, drawn from the 08-18 reference run (Pass D-F,
re-cited not re-derived):

| Stage | Rows | % of 1,400 | % of 3,323 |
|---|---|---|---|
| Universe | 3,323 | — | 100.0% |
| → Vanguard/OI input | 1,612 | — | 48.5% |
| → OI scoring | 1,400 | 100.0% | 42.1% |
| → hard-block filter (Phase 10) | 1,385 | 98.9% | 41.7% |
| → BLOCKED-verdict filter (Phase 10, "B2 FIX") | **1,135** | **81.1%** | **34.2%** |

The morning half **cannot be chained onto this exact denominator** — no
morning-gate execution exists against the 08-18 universe. As a
same-mechanism proxy only (different day, different universe size,
**not additive to the 3,323/1,135 figures above**), `20260809_195823`'s own
internal funnel: 848 candidates → 848 validated (0 loss, per
Reconciliation) → 300 `verdict=="GO"` (35.4% of that run's 848) / 27
`eil_v3_verdict=="EXECUTE"` carried-through (3.2%) / 5
`fd_verdict=="EXECUTE"` carried-through (0.6%), depending entirely on
which of the six-now-seven verdict fields a downstream reader trusts.

### G3 answer, stated plainly

**Neither purely terminal nor purely recoverable — it depends on which
excluded population you mean.** The 15 hard-blocked
(`EOD_NO_OPTIONS_ROUTE`, mostly `BLOCK_NO_CONTRACT`-class) and 250
`eil_v3_verdict==BLOCKED` rows excluded at Phase 10 are **terminal** — the
morning path structurally cannot and does not see them (confirmed: no
artefact carrying them is read anywhere on the morning path). The 184
`BLOCK_SPREAD` (bid=0/2.0-identity) rows are **architecturally
recoverable** — by construction (the `"SPREAD"` token routes them to
`REPAIRABLE_ADVISORY`, not a hard block) most reach `morning_candidates.csv`
and do get a second, live look — but empirically, in the nearest available
proxy, only a small minority (≈4%, 3/73) actually resolve to a genuinely
tradeable contract; the majority (≈53%, 39/73) reproduce the identical
illiquidity live, meaning the underlying market condition, not stale EOD
data, is usually the true cause. **The specific 184-row 08-18 cohort was
never itself run through the live gate and remains formally unverified** —
this is the residual gap the brief specifically asked this pass to close
and could not, for lack of an artefact.

### CHECK 1's fail-open quantification

Missing-live-price (`CANNOT_VERIFY`) rows: **2/3,663 (0.05%)** across the
four available real executions — routed to `FLAG`/`WAIT`/`NO_TRADE`, never
to a false `GO`, and never to `BLOCK` either. Genuine invalidation-broken
`BLOCK`: **97/3,663 (2.65%)**.

### The G5 verdict answer, per-field eligibility (repeated for visibility)

morning_gate's fresh `verdict=="GO"`: 300/848 (35.4%). Carried-through
`eil_v3_verdict=="EXECUTE"`: 27/848 (3.2%). Carried-through
`fd_verdict=="EXECUTE"`: 5/848 (0.6%). None of the three is derived from
either of the others; morning_gate.py computes its own independently.

### Corrections to Passes A-F

1. **CLAUDE.md's own morning command is wrong**, not merely
   phase-mislabelled as Pass A found for the evening phases — it names a
   retired module (`morning_thesis_validator.py`) that the live entry point
   (`intelligent_orchestrator.py --morning` → `premarket_workflow()`) never
   imports.
2. **Pass D's/F's open question ("does a later morning invocation produce
   different, non-2.0 spreads for the same contracts?") is now partially
   answered**, not closed: the general mechanism is settled (rows are not
   hard-blocked, they do reach the morning input, they do get a live
   re-fetch), and a same-mechanism proxy quantifies the resolution rate at
   ≈4% favorable / ≈53% unchanged-illiquid / remainder partially improved.
   The literal 08-18 184-row cohort itself is still unverified.
3. No correction found to Pass F's evening-side manifest schema, verdict
   count, or reconciliation figures — all re-cited here, not re-derived,
   and nothing in this pass contradicts them.

### What this pass did not cover

- `resolve_lab_tradeability()`/`apply_lab_resolution()` in
  `contracts/lab_control.py` past `:864` — the final `lab_verdict`/
  `tradeable` assignment logic was not traced to completion, nor was an
  actual `final_opportunity_book_*.csv` opened to confirm the predicted
  field values.
- Why no `trades/` directory or `execution_gated_*.csv`/
  `execution_actionable_*.csv`/`execution_gate_summary_*.json` exists in
  **any** of the four available real morning-gate runs — Phase 11
  (Execution Gate) is wired into `premarket_workflow()` and is
  non-critical on failure, so this is consistent with either "never
  actually invoked in these four historical runs" or "silently failed
  every time" — no log artefact was located this pass to distinguish the
  two. Flagged as the second-largest open item.
- The exact content and effect of `run_catalyst_truth_layer(stage=
  "pre_morning_validation")`'s in-place patch to `morning_candidates.csv`
  immediately before the gate reads it (`intelligent_orchestrator.py:5251`)
  — confirmed to run, not traced for what it actually changes.
- `pipeline_interpreter/ma_inputs_sync.py`'s `sync_file()` consumer,
  called at the very end of `premarket_workflow()` — not opened this pass.
- Whether morning-mode runs older than `20260723_072618` exist further
  back in `data/output/runs/` that might narrow the date gap to the 08-16/
  08-18 references — not exhaustively searched past confirming the four
  listed are the only ones with populated `morning_validated_trades_*.csv`
  files as of this pass's directory listing.
- Full column-by-column audit of the 111 new morning-gate columns beyond
  the check/live/bond/macro/china/earnings/garch/enrichment/skew family
  groupings given above.
