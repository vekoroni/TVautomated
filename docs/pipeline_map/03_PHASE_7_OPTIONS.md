# Pass D — Options Intelligence

Read-only audit. No files edited, no pipeline phase executed. All citations against
`scripts/avshunter_options_intelligence.py` (7,504 lines, working tree, uncommitted
relative to git HEAD — same caveat as Passes A-C) unless another file is named. Builds
on `00_SPINE.md` (Pass A), `01_PHASES_0_3.md` (Pass B), `02_PHASES_4_6.md` (Pass C), and
`data/scratch/ev3_reconstruction/STAGE_1_BASELINE_RECORD.md` (EV3 baseline) — none
re-derived except where noted.

**Denominators, stated on every percentage below:** 3,323 (augmented universe consumed
by Discovery) and 1,400 (rows entering this stage's scoring loop, per Pass C's funnel).
Both given, each labelled.

**Reference runs, read directly, not simulated:**
`data/output/runs/20260818_041214/options/options_intelligence_20260818_041214.csv`
(1,400 rows × 627 columns) primary; `data/output/runs/20260816_075339/options/options_intelligence_20260816_075339.csv`
(1,347 rows × columns, same schema) secondary. Every count in this document that is not
explicitly marked otherwise was obtained by `pandas.read_csv` + `value_counts`/`crosstab`
against these two files — not by reading source and inferring what "should" happen.

---

## D1 — `process_ticker()` control flow

**Module / function:** `process_ticker()`, `scripts/avshunter_options_intelligence.py:5815-6576`
**Invoked by:** `run_options_layer()` main loop, `:7138` (one call per eligible row; a
second call path exists only conceptually — the `except` block at `:7153` does not call
`process_ticker` again, it calls `_stand_down` directly)
**Conditional on:** Unconditional given the row survived Pass C's 1,612→1,400 eligibility
filter (tier ∈ {0,1,2} ∪ Vanguard-support override, minus WAIT-intent exclusion — not
re-derived here, see Pass C)
**Output non-empty in ref runs:** Yes, 1,400/1,347 rows respectively, 627 columns.

### The decision tree, in source order

```
process_ticker(signal_row, macro_context, tle_context)
│
├─ ctx = parse_structural_context(signal_row)                          :5825
│
├─[1]─ if not ticker or spot <= 0                                      :5830-5831
│        → _stand_down('Invalid ticker or spot price from pipeline')   → BLOCK_INVALID_INPUT
│        Empirical count: 0/1400 (08-18), 0/1347 (08-16) — reachable, not observed.
│
├─[2]─ if ctx['direction'] == 'NONE'                                   :5835-5836
│        → _stand_down('No tradeable CALL/PUT direction after '
│                       'Vanguard support repair')                     → BLOCK_NO_DIRECTION
│        Empirical count: 0/1400, 0/1347 — reachable, not observed. (Consistent with
│        Pass C: rows reaching this stage already passed a WAIT/direction filter
│        upstream, and derive_verdict's own Gate 2 for the same condition is therefore
│        also unreachable in practice — see D5.)
│
├─ chain = fetch_chain(ticker)                                         :5870
│
├─[3]─ except Exception as e                                           :5871-5873
│        → _stand_down(f'Chain fetch failed: {e}')                     → BLOCK_CHAIN_ERROR
│        Empirical count: 0/1400, 0/1347 among rows with a captured block_code of
│        BLOCK_CHAIN_ERROR — not present in either run's `block_code` value_counts.
│        (fetch_chain() itself has internal Polygon/MD fallback layers not audited in
│        this pass; an exception escaping all of them was not observed.)
│
├─[4]─ if chain.empty                                                  :5875-5876
│        → _stand_down('No options chain data available')              → BLOCK_NO_CHAIN
│        Empirical count: **15/1400 (08-18), 19/1347 (08-16)**. Confirmed via
│        `block_code=='BLOCK_NO_CHAIN'`. This is the ONLY case where
│        `contract_rejection_log_{run_id}.csv` is actually populated at the per-ticker
│        level from real process_ticker output — see D2 for why (the writer keys on
│        `final_route==OPTIONS_BLOCKED_ROUTE`, and this is the one no-contract path that
│        reaches `_empty_options_research_contract()`, which sets
│        `final_route=OPTIONS_BLOCKED_ROUTE`, `:5750`).
│
├─ GEX, walls, PCR, delta-weighted OI, IV context, sector regime, contract
│  selection — no further early returns until contract selection.
│
├─ contract = select_best_contract(chain, ctx)                         :5975  (full D2 below)
│
├─[5]─ if not contract:                                                :5995-6047
│        _base_no_contract = {**_stand_down('No contract passed quality gates'), ...}
│        → block_code = BLOCK_NO_CONTRACT (via _classify_block matching
│          'NO CONTRACT PASSED', :6857-6858)
│        Then `.update()` at :6026-6043 overwrites execution_permission/final_route/
│        options_route_verdict/options_research_score/etc to a "soft review" shape
│        (final_route=OPTIONS_PROBE_ROUTE, NOT OPTIONS_BLOCKED_ROUTE) — but does NOT
│        overwrite `options_verdict`, which stays 'STAND_DOWN' from _stand_down()'s
│        base dict. Net effect: options_verdict='STAND_DOWN', block_code=
│        'BLOCK_NO_CONTRACT', but final_route='OPTIONS_PROBE_ONLY' (not BLOCKED) — the
│        row is simultaneously "stood down" by the legacy verdict and "probe-routed" by
│        the research-contract system. Confirmed by direct crosstab (D6 below).
│        Empirical count: **831/1400 (08-18, 59.4% of 1400 / 25.0% of 3,323),
│        819/1347 (08-16, 60.8% of 1347 / 24.6% of 3,323)**. **This is the single
│        largest attrition point in the entire Options Intelligence stage — see D2.**
│
├─ (contract exists past this point)
├─ enrich_contract_with_real_quotes(contract)                          :6051
├─ NBBO top-of-book enrichment attempt                                 :6057-6072
│    **CONFIRMED DEAD CODE / SILENT NameError.** Lines :6069-6070 write to
│    `result['l2_bid_size']`/`result['l2_ask_size']` — but `result` is never assigned
│    anywhere in `process_ticker()`'s own local scope (grep-confirmed: the only local
│    variable named `result` in this file belongs to `run_options_layer()`, a different
│    function, `:7138`). Every execution of this block raises `NameError: name 'result'
│    is not defined`, caught by the bare `except Exception: pass` at :6071-6072. The
│    comment above this block ("Wire to result so EIL ctx.l2_bid_size/l2_ask_size are
│    populated. Without this OBI runs on GEX synthesis only") describes an intended
│    fix that was never actually wired — confirmed by grep, `l2_bid_size`/`l2_ask_size`
│    do not appear anywhere in `process_ticker()`'s final return dict (:6277-6576)
│    either. **OBI runs on GEX synthesis only on every row, unconditionally** — the
│    exact failure state the comment says this code exists to avoid.
│
├─ iv_engine wiring, Heston enrichment, gamma velocity, volume confirmation,
│  compute_trade_economics(), compute_ois() + macro bonus, derive_verdict()   (D5 below)
├─ build_options_research_contract()                                    :6222  (D2/D6)
├─ direction_arbitration, alternatives, repair_alt_fields
│
├─[6]─ if authoritative_route == OPTIONS_BLOCKED_ROUTE:                :6258-6264
│        resolved_options_verdict = 'STAND_DOWN'
│        (only place inside the "contract exists" branch that can force STAND_DOWN
│        after derive_verdict already ran)
│
└─ return { ... 200+ fields including build_convexity_strike_map() output ... }  :6277-6576
```

**Sixth `_stand_down()` call site — outside `process_ticker()`:**
`run_options_layer()`'s per-row `except Exception` handler, `:7145-7153`:
```python
except Exception as e:
    ...
    result = _stand_down(ctx, f"Unhandled exception: {e}")
```
This is the prior audit's "six `_stand_down()` call sites" — **confirmed, count is
exactly 6** (`:5831, :5836, :5873, :5876, :5997, :7153`), but **only 5 are inside
`process_ticker()` itself**; the sixth is the outer per-row exception wrapper in
`run_options_layer()`, classified via `_classify_block()` matching `'UNHANDLED
EXCEPTION'` → `BLOCK_PIPELINE_ERROR` (`:6859-6860`). **This one is empirically live**:
0/1400 on 08-18, but **18/1347 (1.3%) on 08-16** — an entire class of failure invisible
in the primary reference run and only surfaced by checking the secondary one, exactly
the kind of run-to-run instability the Standing Contract asks to watch for. Not traced
further this pass (would require the 08-16 run's own stdout/log capture, which was not
preserved as a separate artefact — same limitation Pass C hit for Backfill's per-reason
breakdown).

### Terminal-path row counts (both reference runs)

| Terminal path | Call site | block_code | 08-18 (n=1400) | % of 1,400 | % of 3,323 | 08-16 (n=1347) |
|---|---|---|---|---|---|---|
| Invalid ticker/spot | `:5831` | BLOCK_INVALID_INPUT | 0 | 0.0% | 0.0% | 0 |
| No direction | `:5836` | BLOCK_NO_DIRECTION | 0 | 0.0% | 0.0% | 0 |
| Chain fetch exception | `:5873` | BLOCK_CHAIN_ERROR | 0 | 0.0% | 0.0% | 0 |
| Chain empty | `:5876` | BLOCK_NO_CHAIN | 15 | 1.1% | 0.45% | 19 |
| No contract (select_best_contract→None) | `:5997` | BLOCK_NO_CONTRACT | **831** | **59.4%** | **25.0%** | **819** |
| Spread hard gate (derive_verdict) | inside `derive_verdict`, surfaces as STAND_DOWN | BLOCK_SPREAD | 184 | 13.1% | 5.5% | 147 |
| Unhandled exception (outer) | `:7153` | BLOCK_PIPELINE_ERROR | 0 | 0.0% | 0.0% | 18 |
| ARMED (soft-blocked but not stood down) | n/a — `derive_verdict` default path | BLOCK_RR_FAIL/LOW_SCORE/EXPENSIVE_VOL/REGIME_VOL/EVENT_PRICED/IV_STRUCTURE/UNKNOWN | 247 | 17.6% | 7.4% | 239 |
| EXECUTE | n/a | NONE | 123 | 8.8% | 3.7% | 105 |
| **STAND_DOWN total** | | | **1,030** | **73.6%** | **31.0%** | **1,003 (74.5%)** |

Reconciliation: 15+831+184+0+247+123 = 1,400 exact (08-18). 19+819+147+18+239+105 = 1,347
exact (08-16). No shortfall at this level in either run.

**A field-contract inconsistency, not previously documented, found empirically this
pass:** every one of the 247 ARMED rows (08-18) carries a non-`NONE` `block_code`
(`:6305-6306`'s `'NONE' if resolved_options_verdict == 'EXECUTE' else
(block_taxonomy['block_code'] if resolved_stand_down_reason else 'NONE')` — ARMED rows
always have a non-empty `resolved_stand_down_reason`, the descriptive string
`derive_verdict()` returns even for its non-blocking ARMED branches, so they always
classify into a `block_code`). **`block_code` therefore means two different things
depending on `options_verdict`**: for STAND_DOWN rows it names the gate that actually
killed the trade; for ARMED rows it names whatever `_classify_block()` pattern-matched
against the *descriptive* reason text of a row that was never blocked at all (e.g. a row
demoted from EXECUTE to ARMED for R:R<1.0 carries `block_code='BLOCK_RR_FAIL'` despite
being live/tradeable). A consumer filtering `block_code != 'NONE'` to find "blocked"
rows would incorrectly sweep in all 247 ARMED rows alongside the 1,030 genuine
STAND_DOWNs. Not present in `_classify_block()`'s own docstring, which describes
`block_severity` as HARD/SOFT without noting that SOFT block codes are stamped on rows
that were never blocked in the first place.

---

## D2 — `select_best_contract()` in depth

**Module / function:** `select_best_contract()`, `:4122-4318`. Inner scoring closure
`_score_leg()`, `:4139-4304`.
**Invoked by:** `process_ticker():5975`, once per ticker (direction already resolved by
`parse_structural_context()`).
**This function accounts for 831/1,400 (59.4% of 1,400; 25.0% of 3,323) rows this
run, 819/1,347 (60.8%/24.6%) the other — the single largest attrition point in the
pipeline**, larger than every other Options Intelligence terminal path combined.

### The full filter funnel, in evaluation order, with path:line and mechanism

| # | Filter | path:line | Threshold | Returns `None` (hard elimination) if empty after this step? |
|---|---|---|---|---|
| 0 | Chain empty guard | `:4128` | `df.empty` | Yes — pre-leg |
| 0b | Direction resolved | `:4130-4131` | `direction != 'NONE'` | Yes — pre-leg |
| 1 | Right filter | `:4134-4137` | `right.upper() == 'C'` or `'P'` | Yes, at `:4140` (leg_df.empty) |
| 2 | DTE window | `:4150-4158` | Strict `[dte_min, dte_max]` from `ctx['dte_window']` (horizon-specific, `DTE_CONFIG`); if empty, relaxed to `[dte_min-15, dte_max+15]` | Yes, at `:4158` |
| 3 | OTM/ATM side filter | `:4162-4168` | CALL: `strike >= spot`; PUT: `strike <= spot` (no ITM contracts — "expensive premium collapses the intended 1R-to-open-ended payoff") | Yes, at `:4168` |
| 4 | Hard delta cap | `:4173-4174` | `\|delta\| <= max(0.65, delta_max + 0.10)` | Yes, at `:4174` |
| 5 | Liquidity + spread gate | `:4176-4189` | `open_interest >= MIN_OI (50)`, `volume >= MIN_LIQUIDITY_VOLUME (0 — a no-op floor)`, `spread_pct <= spread_limit` (**bypassed entirely** — `spread_ok = True` for every row — **if every candidate on this leg is `mark_synthetic`**, `:4176-4182`), `mark > 0` | Yes, at `:4189` (`liquid_df.empty`) |
| 6 | Delta-band soft filter | `:4191-4198` | `\|delta\|` between `[delta_min, delta_max]` (horizon-specific target zone, e.g. 0.40-0.60 for `1_5d`). **Soft**: if empty, falls back to the full liquid set with `best_available_suboptimal=True` flag — does not eliminate the ticker. | No — soft fallback only |
| 7 | Target-reachability filter | `:4209-4232` | CALL: keep `strike <= structural_target`; if none, fallback to `strike <= spot*1.05` closest-to-target. PUT: mirror. **Soft-with-fallback**: if the fallback set is also empty, the code proceeds with whatever survived step 6 unchanged (comment: "BLOCK_WRONG_STRIKE will fire at scoring time as last resort — better than no contract"). | Yes, only at the final `:4234` check (`leg_df.empty` after all of the above) |
| 8 | Scoring | `:4236-4304` | Composite = 30% delta-alignment + 20% DTE-fit + 20% theta-efficiency + 15% vega-quality + 15% liquidity; `max()` by `contract_score` | n/a — always returns something if any candidate survived step 7 |

**Six hard elimination points** (`:4140, :4158, :4168, :4174, :4189, :4234`), two of them
(steps 6 and 7) *soft* with fallbacks that only convert to hard elimination if their own
fallback also comes up empty. **The function returns `None` uniformly for all of these —
it does not record which of the six eliminated a given ticker.** No log entry, no
counter, no field on the returned (`None`) result distinguishes "no chain had this
right at all" from "liquidity gate killed everything" from "target-reachability killed
everything." This confirms, and sharpens, the prior audit's finding: **an unauditable
filter is responsible for the single largest loss in the pipeline.**

### What can and cannot be reconstructed from artefacts

**Cannot be reconstructed:** the exact per-filter attrition breakdown (how many of the
831 died at step 2 vs. step 5 vs. step 7) is not recoverable from any artefact on disk.
No raw per-strike chain snapshot is persisted anywhere under
`data/output/runs/20260818_041214/` (confirmed by directory listing — `options/` holds
only post-selection, per-ticker-row outputs: `options_intelligence_*.csv`,
`options_candidates_ranked.csv` (a re-sort of the *same* 1,400 output rows, not raw
chain data), `options_blocked_review.csv` (15 rows, the `OPTIONS_BLOCKED_ROUTE`/
`OPTIONS_EQUITY_ONLY_ROUTE` subset of the same output), `contract_rejection_log_*.csv`).
Reconstructing the six-way split would require re-running `select_best_contract()`
against the historical chain, which this pass is not permitted to do.

**A confirmed, concrete instance of dead diagnostic code, discovered this pass:**
`process_ticker()` builds a `_rejection_entry` dict describing exactly this situation
(`:5984-5991`, comment: *"Log the rejection for the contract_rejection_log"*) —
`{'ticker', 'horizon', 'rejection_reason': 'NO_CONTRACT_PASSED_QUALITY_GATES',
'dte_scanned_min', 'dte_scanned_max'}` — but **this variable is built and never used
again**. Grep-confirmed: `_rejection_entry` appears exactly once in the entire file,
at its own assignment. It is not appended to any list, not returned, not written. **The
`contract_rejection_log_{run_id}.csv` file that actually lands on disk is written by
a completely different, later, post-hoc computation** — `run_options_layer():7290-7308`
— which filters the *finished* output DataFrame for `final_route ==
'OPTIONS_BLOCKED_ROUTE'` and writes one row per match. Because the 831 `BLOCK_NO_CONTRACT`
rows have `final_route == 'OPTIONS_PROBE_ONLY'` (not `BLOCKED` — see D1's terminal-path
table and D6's field-consistency finding), **none of the 831 rows appear in
`contract_rejection_log_20260818_041214.csv` at all** — that file's 15 rows are
*exclusively* the `BLOCK_NO_CHAIN` case ("No options chain data available"), confirmed by
direct read: every row's `rejection_reason` is that literal string. **A file whose name
and in-code comment both claim to record "why contracts failed quality gates" contains
zero rows for the failure mode responsible for 96%+ of all rejections
(831 of 831+15=846 chain-having-or-not rejections).** This is itself a headline finding,
not merely the absence of one.

**What partially can be reconstructed — the repair-alternative signal.**
`select_repair_alternative_contracts()` (`:4368-4558`) is called for every
`BLOCK_NO_CONTRACT` row (`:6013-6015`) as a *looser*, independent second search over the
same chain, and its outcome is written to `contract_repair_action` /
`alternative_contracts_count`. Empirically, across the 831 rows:

| `contract_repair_action` | Count | % of 831 |
|---|---|---|
| `NO_ALTERNATIVE_FOUND` (0 candidates even under the looser search) | 774 | 93.1% |
| `ALTERNATIVES_AVAILABLE` (1-6 candidates found) | 57 | 6.9% |

`select_repair_alternative_contracts()`'s own filter (`:4438-4467`) is looser than
`select_best_contract()` on several axes — no hard delta-cap-then-band two-stage
filter (just direct `delta_min≤|delta|` is *not* required, only the DTE window,
strike-vs-spot 10%/90% band, and OI/volume/spread checks), and its OI/volume floor uses
`EV3_MIN_OPEN_INTEREST`/`EV3_MIN_VOLUME` (env-overridable, default 50/1) rather than
`select_best_contract`'s `MIN_OI=50` — but it has **no synthetic-mark bypass**: it
requires real, non-null `bid`, `ask` (`bid>=0, ask>0, bid<=ask`), `delta`, `gamma`,
`theta`, `vega`, `implied_vol`, and `quote_timestamp` for every candidate (`:4438-4444`)
— it cannot select a BSM-synthetic contract at all, unlike `select_best_contract`'s
`all_synthetic` bypass (D2 table, step 5). **This is the load-bearing distinction**:
93.1% of the 831 no-contract tickers have *no real, complete quote anywhere in the
chain for the eligible right* — not merely a chain that misses the tight primary
delta/DTE/target window. Only 6.9% had at least one real-quoted candidate available
under looser criteria while still failing the primary selector — for these, the
primary selector's tighter delta band, target-reachability requirement, or
horizon-specific `spread_max` (see below) is the specific, identifiable cause.
**This is the best reconstruction available from artefacts alone; it is a strong signal,
not a precise per-filter count, and is reported as such.**

### `spread_limit` — resolved

`select_best_contract._score_leg()`'s liquidity-gate spread threshold (`:4147`):
```python
spread_limit = float(_dte_cfg.get('spread_max', MAX_SPREAD_PCT))
```
`_dte_cfg` is `ctx.get('dte_config')`, sourced from the module-level `DTE_CONFIG` dict
(`:1048-1052`), keyed by horizon bucket:

| Horizon bucket | `dte_min` | `dte_max` | `spread_max` (selection-time) | `delta_min` | `delta_max` |
|---|---|---|---|---|---|
| `1_5d` | 7 | 21 | **0.15** | 0.40 | 0.60 |
| `6_10d` | 21 | 35 | **0.25** | 0.35 | 0.55 |
| `11_20d` | 35 | 60 | **0.35** | 0.30 | 0.50 |

This is a **materially different, tighter value than `derive_verdict()`'s fixed
`MAX_SPREAD_PCT = 0.25` hard gate** (`:1022`, checked at `:5243` and `:5255`) for the
majority-horizon `1_5d` bucket (0.15 vs 0.25) and identical for `6_10d`, looser for
`11_20d`. **Consequence**: a `1_5d`-horizon ticker whose only available contracts carry
a real spread between 15% and 25% is excluded at *selection time* (step 5 of the D2
funnel) — it never reaches `derive_verdict()`'s spread gate at all, and is counted as
`BLOCK_NO_CONTRACT`, not `BLOCK_SPREAD`. The two gates are not the same threshold and
are not applied to the same population of tickers; `BLOCK_SPREAD`'s 184 rows are only
the contracts that *did* clear selection (via the `all_synthetic` bypass, see D3) and
then failed the separate, later, fixed-0.25 gate.

---

## D3 — The 2.0 spread value: producer identified

**Confirmed root cause, traced through the exact arithmetic, with the empirical data
matching to six decimal places:**

Empirical pattern (both runs): every affected row has `contract_bid == 0.0` exactly (not
missing, not NaN — a real zero), a positive `contract_ask`, `contract_mark_synthetic ==
True`, `spread_source == 'MD_REAL'`, `contract_quote_source ==
'marketdata.app_incomplete'`, and `contract_premium == contract_ask / 2` **exactly**
(e.g. ticker BANC: bid=0.0, ask=1.15, premium=0.575=1.15/2; ticker LNTH: bid=0.0,
ask=2.35, premium=1.175=2.35/2 — checked across the full 182/184 (08-18) and 145/147
(08-16) affected rows, no exceptions found).

**Mechanism, traced end to end:**

1. `fetch_chain_md()` (`:2238-2470`) builds each chain row from MarketData.app's chain
   response. `bid_val`/`ask_val`/`mid_val` are taken directly from the API arrays
   (`:2385-2387`). MarketData.app can and does legitimately return `bid=0` for a
   real, quoted, OTM contract with no resting bid (illiquid strike, genuinely no buyers)
   — this is not a missing/null value, it is a valid top-of-book state.
2. `quote_fields_complete` (`:2411-2415`) requires `bid_val > 0` (not merely
   `is not None`) — so `bid=0` makes `quote_fields_complete = False`, and
   `mark_synthetic = not quote_fields_complete = True` (`:2436`),
   `md_quote_source = 'marketdata.app_incomplete'` (`:2438`) — **even though every
   field involved is a real, non-missing API value.** "Synthetic" here does not mean
   "BSM-modelled" for these rows; it means "top-of-book incomplete by the `bid>0`
   convention."
3. `mark`/`mid` for this same row (`:2407-2410`) is computed by MarketData.app's own
   `mid` field, which for a real `bid=0`, `ask=X` quote is itself `(0+X)/2 = X/2` — this
   is where `contract_premium == ask/2` originates, and it is **MarketData.app's own
   midpoint convention**, not a fallback this codebase invented.
4. `fetch_chain_md()` then computes, still at the chain-fetch stage:
   `spread_pct = (ask_val - bid_val) / mid_val` (`:2408-2410`), gated only on
   `bid_val is not None and ask_val is not None and mid_val and mid_val > 0` — all
   true here. Substituting: `spread_pct = (X - 0) / (X/2) = 2.0`, **for every possible
   value of X**. This is an algebraic identity of the spread-percentage formula whenever
   the bid leg is exactly zero and the midpoint is computed as the simple bid/ask
   average — it holds regardless of strike, ticker, or day.
5. This `spread_pct = 2.0` value survives unchanged through `select_best_contract`
   (`:4246`, `spread = row['spread_pct'] or 0.15` — `2.0` is truthy, so the `or 0.15`
   fallback never fires) into the scored-and-selected contract dict (`:4290`), and
   through `process_ticker()`'s later re-derivation logic (`:6201-6221`) — which only
   recomputes `spread_pct` when the existing value is blank (`_oi_float(...) is None`,
   `:6218`), and it is not blank here, so the `2.0` is carried straight to the output
   column `contract_spread_pct` unchanged.
6. This same `all_synthetic`-flagged contract is still *selectable* at step 5 of the D2
   funnel, because when **every** candidate on a ticker's leg is `mark_synthetic=True`,
   `select_best_contract` sets `spread_ok = True` unconditionally for the whole leg
   (`:4176-4182`, the "all_synthetic" bypass) — the OI/volume/`mark>0` checks still
   apply, but spread is not filtered at selection time. A `spread=2.0` contract can
   therefore still win the leg's scoring competition if it is the only (or best-scoring)
   candidate meeting the OI/volume floor.
7. **The block then fires at `derive_verdict()`'s *second* spread check**
   (`:5248-5260`), not its first. The first check (`:5236-5247`) explicitly exempts
   synthetic-mark contracts: `if spread_pct_val is not None and not
   bool(contract.get('mark_synthetic', False))` — since `mark_synthetic=True` here,
   `not True = False`, and this gate is skipped, matching the design intent documented
   elsewhere in this file (compute_ois's own "BUG B FIX" comment, `:6137-6141`: BSM/
   incomplete-quote contracts should not be penalised as if they were bad trades). But
   the **second** check, immediately below (`:5248-5260`), has no such exemption — it
   fires whenever `bid is not None, ask is not None, bid>=0, ask>0, mark>0`, all true
   here, and computes `spread_pct = (ask-bid)/mark = 2.0 > MAX_SPREAD_PCT(0.25)` →
   `STAND_DOWN, 'BLOCK_SPREAD: ...'`.

**Verdict: the 2.0 is not a hardcoded sentinel, default, or `fillna` anywhere in the
repo** — a static grep for a literal `2.0`/`2\.0` tied to any spread variable correctly
finds nothing, because none exists. It is an **emergent arithmetic identity**: whenever
MarketData.app returns a real `bid=0` alongside a positive `ask`, every downstream
midpoint-based spread calculation in this codebase, chain-level or contract-level,
necessarily produces exactly `2.0`, no matter which of the several call sites happens to
compute it first. Repo-wide grep for `spread_pct` outside this file (macro/vanguard/
eod_candidate_engine) found no other independent producer of this exact value — the two
computations inside `avshunter_options_intelligence.py` (`fetch_chain_md`'s chain-level
one at `:2408-2410`, and `enrich_contract_with_real_quotes`'s per-contract one at
`:1444-1445`, which uses the identical formula and would produce the identical `2.0` if
it ever ran to completion for a `bid=0` contract, though for the 831/184 sampled rows
the chain-level value already existed and was never blank, so the `:6218` guard skipped
recomputation and the per-contract path's own value was never the one that landed in the
output) are the only two places in the entire pipeline that can produce it, and they
share the same root input condition (`bid=0`, real `ask`) and the same formula.

**The second-gate/first-gate asymmetry is itself a genuine, reportable control-flow
defect**, structurally identical in kind to the three already-known ordering defects
(Regime Screener, Trap Engine VWAP signals, discovery/vanguard `_x`/`_y` merge): two
near-duplicate spread checks exist in the same function, one carries a synthetic-mark
exemption and one does not, and the exemption's absence on the second check is exactly
what converts a data-completeness artefact (MD's own bid=0 midpoint convention) into a
hard STAND_DOWN for 184/1,400 (13.1% of 1,400; 5.5% of 3,323) rows.

**Real-vs-synthetic distinguished, per the brief's specific question:** affected
contracts are **not** wholly empty — `contract_bid`, `contract_ask`, `contract_premium`,
`contract_volume`, `contract_oi` are all populated (0 NaNs across all 9 checked columns,
184/184 rows). This is squarely the "quote existed but spread computation failed [to
represent a meaningful liquidity number]" case, not "no quote existed."

**Whether the same `contract_occ_symbol`s resolve to real spreads in any morning-mode
artefact:** **UNVERIFIED — no morning-mode run directory exists among the artefacts
available to this pass.** Both reference run directories
(`20260818_041214`, `20260816_075339`) are evening/EOD runs only (confirmed by directory
listing — no `morning_validation` content beyond the standard evening-produced
placeholder files, and no second, later-timestamped run sharing either run's canonical
`run_id` was found under `data/output/runs/`). Settling this would require either a
recorded morning-mode run against the same session's tickers, or re-running the morning
path live — out of this pass's read-only, no-execution scope. This is flagged as the
single most actionable open item from this pass: if morning-mode quotes for these same
OCC symbols show real (non-2.0) spreads, the evening BLOCK_SPREAD verdict for these 184
rows is provably premature, exactly the counterfactual the brief asks to look for.

---

## D4 — Does anything branch on `data_mode`?

**No. Confirmed by exhaustive grep: `avshunter_options_intelligence.py` has zero
`argparse`/CLI awareness of `data_mode` at all** — no `add_argument` call, no
`args.data_mode` reference, no `--data-mode` string anywhere in the file. The module's
own entry point, `run_options_layer(discovery_csv, vanguard_csv, run_id, output_dir,
max_signals)` (`:7016-7021`), takes no `data_mode` parameter whatsoever — the
orchestrator's `--data-mode EOD/LATEST` flag (Pass A, `intelligent_orchestrator.py`
argparse) is never threaded into this module's call signature at all.

The only two occurrences of the string `data_mode` in the entire file (`:6567`, `:7006`)
are both **unconditional literal assignments**, `'data_mode': 'EOD'`, written into every
output row — the success path (`:6567`, inside `process_ticker()`'s main return dict)
and the no-chain-data stand-down path (`:7006`, inside `_empty_options_research_contract()`
via `_stand_down()`). Both are annotated with nearly identical comments: *"EOD mode
markers — allow superbrain's OIS-bypass gate and morning_validation's `_is_eod`
detection to fire correctly... Written on ALL rows... so the downstream column is
always present regardless of options outcome."*

**This is a pure output label for downstream consumers (SuperBrain, `morning_validation`),
not a record of how this module itself behaved.** `fetch_chain()`/`fetch_chain_md()` are
called unconditionally in `process_ticker()` (`:5870`) regardless of what mode the
orchestrator actually requested — this module always attempts a live chain fetch from
MarketData.app/Polygon (subject to those APIs' own EOD-vs-realtime plan limitations, not
audited this pass), and always stamps its output `'EOD'` regardless of whether that
fetch happened to run during market hours (`--force`, Pass A §2.1) or after close.

**Stated plainly, as the brief requests:** the same selection thresholds, the same
liquidity gates, the same spread checks apply in Options Intelligence whether the
orchestrator was invoked with `--data-mode EOD` or `--data-mode LATEST` — this module has
no code path that distinguishes them. Contracts killed here at `BLOCK_NO_CONTRACT` or
`BLOCK_SPREAD` under an EOD-timed run never get a second, live-market chance within this
same run; the only mechanism that could re-evaluate them is a separate, later
`premarket_workflow()`/morning invocation of the *entire* pipeline (Pass A), which is a
different process launch with its own independent chain fetch, not a data-mode-aware
branch inside this module. This directly substantiates D3's open question: whether such
a later morning invocation actually produces different (non-2.0) spreads for the same
contracts is unverified, but the code confirms there is no *architectural* reason it
could not — this module would apply exactly the same gates to fresher data if asked.

---

## D5 — `derive_verdict()` and the OIS score

Not re-deriving the prior audit's six hard gates or the "score tier defaults to ARMED,
no low-score STAND_DOWN path" finding — both independently reconfirmed by direct read
this pass (`derive_verdict():5154-5384`; the else-branch at `:5364-5368` unconditionally
sets `final_verdict = 'ARMED'` for any OIS below `_arm_min`, never `'STAND_DOWN'`).
**Correction/refinement to "six hard gates":** direct count of `return 'STAND_DOWN', ...`
statements inside `derive_verdict()` is **seven**, not six: `:5190` (WAIT intent),
`:5194` (no direction), `:5220` (event-priced binary), `:5232` (no expiry/DTE), `:5244`
(spread gate #1, `mark_synthetic`-gated), `:5256` (spread gate #2, ungated — see D3),
`:5286` (wrong-strike with `mark<=0`). The prior audit's "six gates" framing likely
counted the two spread checks (`:5244`/`:5256`) as one logical gate, which is reasonable
given they guard the same `MAX_SPREAD_PCT` threshold — but D3 shows they are not
equivalent in practice (one is exempted for synthetic marks, one is not), so this pass
treats them as two.

### `compute_ois()` — every sub-component, weight, and path:line

`compute_ois()`, `:4816-5146`. Nominal dimension budget is A+B+C+D+E = 22+22+22+22+12 =
100, but the function is **not a strict per-dimension cap** — several components can
push the running total beyond a dimension's nominal ceiling (e.g. dimension A alone can
contribute up to +22 IVP +5 IV/HV +4 regime +3 direction +5 skew +2 term = +41 before any
penalty), and one component (`[0]`, actuarial sample size) and one flag-only component
(`[F]`, quote quality) sit **outside** the five labelled dimensions entirely. The score
is only clamped globally to `[0, 100]` at the very end (`:5145`), not per-dimension — the
"22/22/22/22/12" labels in the docstring are a nominal target, not an enforced budget.

| Component | Range | path:line | Notes |
|---|---|---|---|
| `[0]` Actuarial sample size (`l2_n_obs`) | −15 to 0 (no positive score, only a `pos.append` note when N≥200) | `:4847-4856` | Applied before all labelled dimensions; only ever subtracts or is neutral |
| `[A]` IVP (dual-window) | +2 to +22 | `:4871-4881` | Largest single swing in the function |
| `[A]` IV/HV ratio | −3 to +5 | `:4884-4892` | |
| `[A]` IV regime | −4 to +4 | `:4895-4902` | |
| `[A]` IV direction | +1 to +3 (or 0/neg via `neg.append` with no point change on one branch) | `:4905-4910` | |
| `[A]` Skew | −5 to +5 | `:4913-4920` | |
| `[A]` Term structure | −2 to +2 | `:4923-4926` | |
| `[A]` Hard 252d-IVP-expensive penalty | −8 or 0 | `:4929-4930` | Fires only when `ivp_252>0.85` AND `iv_vs_hv>1.20` |
| `[B]` Intent/direction match | 0 to +10 | `:4933-4942` | |
| `[B]` Trend/direction match | −2 to +7 | `:4944-4959` | Contra-trend penalty reduced from −5→−2 by a 2026-05-02 amendment (in-code comment) |
| `[B]` Phase | +1 to +7 | `:4961-4965` | `{'C':7,'D':7,'E':5,'B':3,'A':1}` |
| `[B]` Regime/vol dual-headwind | −3 or 0 | `:4967-4968` | |
| `[C]` R:R | 0 to +9 (never negative — "AMENDMENT: R:R scoring decoupled from gating", `:4986-4995`) | `:4990-4995` | |
| `[C]` EV/premium (`ev_adj_final`) | 0 to +7 (never negative points, only a `neg.append` note) | `:4997-5000` | **`ev_adj_final = econ.get('ev_ratio', 0) * iv_factor` at `:4984`** — confirms the prior audit's citation exactly. `iv_factor` here is a *second*, independently-computed IV multiplier (1.15/0.75/1.0, `:4977-4983`), distinct from `compute_trade_economics()`'s own `iv_factor` (`:4784-4789`) used to build `econ['ev_adjusted']` — two different `iv_factor` values, computed from the same `ivp`/`IVP_CHEAP_MAX`/`IVP_EXPENSIVE` thresholds but in two different functions, feeding two differently-named EV fields (`ev_adj_final` here, local-only; `econ['ev_adjusted']`, output column) that are never reconciled against each other. |
| `[D]` Delta-weighted OI / PCR fallback | −4 to +8 | `:5017-5048` | |
| `[D]` Gamma velocity | −3 to +7 | `:5050-5061` | |
| `[D]` Wall vs. target | 0 to +5 | `:5063-5078` | |
| `[D]` Max-pain pinning | flag-only (`neg.append`, no score change) | `:5080-5084` | Computed but contributes **nothing** to the numeric score — pure warning text |
| `[E]` Wyckoff volume confirmation | −4 to +7 | `:5088-5095` | |
| `[E]` Vanna | 0 to +3 (or `neg.append` with no negative points) | `:5097-5105` | |
| `[E]` Charm | flag-only (`neg.append`, no score change) | `:5107-5112` | Computed but contributes **nothing** to score, same as max-pain |
| `[E]` Sector alignment | −3 to +2 | `:5114-5125` | |
| `[F]` Quote quality | −8 or 0 | `:5133-5143` | Outside the five labelled dimensions; only ever subtracts (2026-03-05 "BUG B FIX" comment explicitly removed an earlier, harsher −10/zero-score penalty) |

**Largest empirical swings**: IVP (±20-point range within dimension A alone) and the
`[0]` actuarial-sample-size penalty (a flat −15 for any row with a thin-N actuarial
match, applied before anything else) are the two components most capable of moving a
borderline row across a tier threshold. **Computed but structurally unable to move the
score at all**: max-pain pinning (`:5080-5084`) and charm (`:5107-5112`) are both
fully computed, both feed the printed `negative_factors` narrative, and both are
completely inert with respect to the numeric OIS — a consumer reading `options_score`
alone will never see their effect; only a consumer reading `negative_factors` text will.

**`ev_adj` check at `:5307` — confirmed no-op, exactly as the prior audit found:**
```python
if ivp is not None and ivp > IVP_EXPENSIVE and ev_adj < 0:
    pass  # Handled in score-based verdict below via negative EV penalty
```
(`derive_verdict():5304-5309`, condition variable is `ev_adj = econ.get('ev_adjusted',
0)`, `:5180` — note this is `econ['ev_adjusted']`, the `compute_trade_economics()`
output field, a third distinct "EV" value from the two `ev_adj_final`/`iv_factor` pairs
inside `compute_ois()` above). The condition is evaluated, matched, and then does
literally nothing — `pass` — the comment's claim that it is "handled...below" is true
only in the sense that the *general* score-based verdict logic runs regardless of
whether this `if` block exists at all; this specific block has no distinguishable effect
on any output. Confirmed by direct read, not merely re-cited.

---

## D6 — Output field census

**Full column-by-column consumption audit of all 627 columns was not completed this
pass** — infeasible within scope without reading every downstream consumer module
(`avshunter_superbrain_layer.py`'s passthrough logic, `trigger_layer.py`, McMillan
advisory layer, `eod_candidate_engine.py`) line by line, which belongs to whichever pass
covers those modules directly. What follows is what this pass could establish with
targeted checks.

**Confirmed-consumed field groups, with consumer and path:line:**
- `csm_*` (Sprint 2, Convexity Strike Map) — produced by `build_convexity_strike_map()`,
  spread into the return dict at `:6575`; consumed by the Trap Engine integration (Pass
  C already confirmed `tle_verdict` modifies `csm_verdict`/`csm_premium_efficiency`
  in-process, `:6759-6778`) and flows to downstream CSVs/Lab per Pass C.
- `tle_*` raw fields — **not** propagated as their own output columns (Pass C already
  confirmed zero `tle_`-prefixed columns among the 627; only their *effect* via
  `csm_verdict`/`csm_verdict_reason` text survives).
- `layer2__*` baton columns — explicitly forwarded via `result.setdefault(_baton_col,
  row.get(_baton_col))` in `run_options_layer()`'s loop (`:7139-7140, :7154-7155`) for
  every row, success or exception — this is a deliberate passthrough, not an accident.
- `options_fields` list (`:7311-7334+`) — a curated ~50-column subset explicitly written
  back into the enriched Vanguard CSV (`vanguard_signals_enriched_{run_id}.csv`,
  confirmed present on disk, 24.7MB, both reference runs) — this is the mechanism by
  which Options Intelligence's own output re-enters the Vanguard-shaped artefact chain
  that SuperBrain/EIL read from downstream (Pass A/C).

**Confirmed field-consistency defect, not previously documented — three-way verdict
disagreement:**

| Field | Values | Source |
|---|---|---|
| `options_verdict` | STAND_DOWN / ARMED / EXECUTE | `derive_verdict()`, legacy OIS-based |
| `options_verdict_tier` | STAND_DOWN / READY_PROBE / READY_EXECUTE (also WATCHLIST / STRUCTURE_CONFIRMED_CONTRACT_BLOCKED, unobserved this run) | `_options_verdict_tier_oi()`, `:310-339`, driven by `final_route` first, `options_verdict`/`edge_quality`/`composite` only as fallback |
| `final_route` / `options_route_verdict` | OPTIONS_GO_REVIEW / OPTIONS_ARMED_HALF / OPTIONS_PROBE_ONLY / OPTIONS_BLOCKED | `build_options_research_contract()`, `:5512-5744`, an **entirely independent scoring system** (`options_research_score`, its own 0-100 composite of 8 differently-weighted sub-scores, `:5669-5679`) with its own thresholds (≥75 GO, ≥60 ARMED, ≥45 PROBE) that share no code path with `compute_ois()`/`derive_verdict()` |

These three fields are reconciled at exactly **one** point in `process_ticker()`
(`:6258-6264`: `final_route==OPTIONS_BLOCKED_ROUTE` forces `options_verdict='STAND_DOWN'`)
— everywhere else they are independent and can, and empirically do, disagree. Measured
directly on the 08-18 reference run (1,400 rows):

- **183-184 rows** carry `options_verdict='STAND_DOWN'` (via `BLOCK_SPREAD`, the D3
  mechanism) but `options_verdict_tier='READY_PROBE'` and `final_route='OPTIONS_PROBE_ONLY'`
  or `'OPTIONS_ARMED_HALF'` — a row the legacy verdict calls dead is simultaneously
  tiered as "ready to probe" by the research-contract system.
- **36 rows** carry `options_verdict='EXECUTE'` but `final_route='OPTIONS_ARMED_HALF'`
  (not `GO_REVIEW`) — the legacy system says "trade this," the research-contract system
  says "half-size, not full go."
- **106 rows** carry `options_verdict='ARMED'` but `final_route='OPTIONS_PROBE_ONLY'`.
- **8 rows** carry `options_verdict='ARMED'` but `final_route='OPTIONS_GO_REVIEW'` — the
  reverse disagreement, research contract says "go," legacy says "not quite."

None of this is a data-quality bug in the sense of a missing or malformed value — every
field is populated, every computation completed successfully. It is a **structural
consequence of running two independently-thresholded, independently-weighted verdict
systems over the same row and reconciling them at only one narrow point.** Any
downstream consumer that reads only one of these three fields (and Pass A/C's artefact
chain shows different downstream modules do read different ones — SuperBrain reads
`options_verdict` via `legacy_options_verdict`/passthrough, per Pass A §6's artefact
table) will see a materially different picture of the same 1,400 rows than a consumer
reading `final_route`.

**Not checked this pass:** whether OI's own 627-column output contains any *internal*
`_x`/`_y` suffix artefacts of its own (distinct from the discovery/vanguard merge
boundary Pass C already covered, which produces `_x`/`_y` in the *input* `merged`
DataFrame, not necessarily in OI's own hand-built output dict) — a quick column-name
grep for `_x$`/`_y$` patterns was not performed this pass; flagged as a fast follow-up
for whoever picks up the remaining D6 census. Full downstream-consumer tracing for the
~53 not-yet-checked `catalyst_*`/`scanner_*` overlap fields Pass C flagged is also still
open, unchanged from Pass C's own stated gap.

---

## The funnel, updated

| Stage | Rows | % of 1,400 | % of 3,323 |
|---|---|---|---|
| Enter OI scoring loop (Pass C boundary) | 1,400 | 100.0% | 42.1% |
| → BLOCK_NO_CHAIN (`:5876`) | 15 | 1.1% | 0.45% |
| → BLOCK_NO_CONTRACT (`select_best_contract` returns None, `:5975/:5997`) | **831** | **59.4%** | **25.0%** |
| → BLOCK_SPREAD (`derive_verdict` gate 2, ungated variant, `:5256`) | 184 | 13.1% | 5.5% |
| → other STAND_DOWN (BLOCK_INVALID_INPUT/NO_DIRECTION/CHAIN_ERROR/PIPELINE_ERROR) | 0 (08-18); 18 (08-16, all BLOCK_PIPELINE_ERROR) | 0.0-1.3% | 0.0-0.5% |
| → ARMED (tradeable-adjacent, soft-blocked) | 247 | 17.6% | 7.4% |
| → EXECUTE | 123 | 8.8% | 3.7% |
| **STAND_DOWN total** | **1,030 (08-18) / 1,003 (08-16)** | **73.6% / 74.5%** | **31.0% / 30.2%** |

Reconciliation, both runs, exact: 15+831+184+0+247+123 = 1,400 (08-18);
19+819+147+18+239+105 = 1,347 (08-16). No shortfall.

## Attrition ranking within this stage, largest first

1. **BLOCK_NO_CONTRACT — 831/1,400 (59.4% / 25.0% of 3,323).** Mechanism class:
   compound — a six-stage hard/soft filter funnel inside `select_best_contract()`
   (liquidity, delta band, DTE, target-reachability, spread) with no per-filter
   attribution recorded anywhere, backed by a **confirmed-dead diagnostic path**
   (`_rejection_entry`, `:5985`, built and discarded) and a **misleadingly-named,
   near-empty artefact** (`contract_rejection_log_*.csv`, captures only the unrelated
   `BLOCK_NO_CHAIN` case). Counterfactual: 93.1% of these tickers have no real, complete
   quote anywhere in the chain for the eligible option right, even under a looser
   secondary search — for these, only a different/fresher chain snapshot would change
   the outcome. The remaining 6.9% had real alternatives excluded specifically by the
   primary selector's delta band, target-reachability requirement, or horizon-specific
   `spread_max` (0.15 for the majority `1_5d` bucket) — for these, a different selection
   threshold (not a different market) would change the outcome. Recoverability: terminal
   for the run; `select_best_contract()` is called exactly once per ticker, no retry.
   Blast radius: stable across both reference runs (819/1,347 vs. 831/1,400, same order
   of magnitude, same mechanism).

2. **BLOCK_SPREAD — 184/1,400 (13.1% / 5.5% of 3,323).** Mechanism class: arithmetic
   identity (`bid=0` + midpoint-based spread formula → exactly 2.0) combined with a
   control-flow asymmetry (derive_verdict's two spread gates, one synthetic-exempt, one
   not). Counterfactual: a contract with a real, complete two-sided quote (not `bid=0`)
   at the same strike would never enter this failure mode; alternatively, extending the
   first spread gate's `mark_synthetic` exemption to the second gate would move these
   184 rows out of STAND_DOWN entirely (not proposing this change, per the Standing
   Contract — reporting the counterfactual only). Recoverability: terminal for the run.
   Blast radius: stable, ~13% both runs (184/1,400, 147/1,347), ~99% of affected rows
   carrying the exact 2.0 value in both.

3. **ARMED-but-block-code-carrying rows — 247/1,400 (17.6% / 7.4% of 3,323), not a
   loss but a labelling ambiguity.** These rows are not attrition — they are live,
   scored, ARMED signals — but every one of them carries a non-`NONE` `block_code`
   (dominated by `BLOCK_RR_FAIL`, 130/247), making `block_code != 'NONE'` an unreliable
   filter for "this row was blocked." Listed here because it is the second-largest
   `block_code`-bearing bucket after the two genuine STAND_DOWN causes above, and a
   naive downstream count of "blocked signals" using `block_code` alone would overstate
   attrition by adding these 247 to the 1,030 genuine STAND_DOWNs.

4. **BLOCK_NO_CHAIN — 15/1,400 (1.1% / 0.45% of 3,323).** Mechanism class: upstream
   data availability (chain fetch returned nothing) — the one case genuinely and fully
   captured by `contract_rejection_log_*.csv`. Recoverability: terminal for the run.

## The 2.0 verdict (summary)

**Producer identified, not merely ruled out.** `fetch_chain_md():2408-2410` (chain-level)
and `enrich_contract_with_real_quotes():1444-1445` (per-contract level, same formula,
not the one that actually fired for the sampled rows but capable of producing the
identical value) both compute `spread_pct = (ask-bid)/mid`. Whenever MarketData.app
returns a real `bid=0` for an OTM contract with no resting bid, and its own `mid` field
is consequently `ask/2`, this formula evaluates to exactly `2.0` for any `ask` value —
an algebraic certainty, not a sentinel, default, or `fillna`. It survives unmodified
through selection and re-derivation (no code path zeroes or re-derives an already-present
non-blank `spread_pct`) and is blocked by `derive_verdict()`'s second, synthetic-mark-
unaware spread gate at `:5248-5260`. The morning-mode counterfactual (do these same OCC
symbols carry a real, non-2.0 spread when the market is open) is **UNVERIFIED** — no
morning-mode artefact exists among the reference runs available to this pass.

## The `data_mode` answer (summary)

**Nothing branches on `data_mode` anywhere in this module.** It has no CLI parameter for
it, no `args.data_mode`, no conditional logic keyed on it. The literal string `'EOD'` is
written unconditionally to every output row (`:6567`, `:7006`) purely as a downstream
compatibility marker for SuperBrain's OIS-bypass gate and `morning_validation`'s `_is_eod`
detection — it does not reflect, and cannot reflect, whether this specific run was
actually invoked in EOD or LATEST mode. The same liquidity, delta, DTE, target-
reachability, and spread gates apply identically regardless of market-open state; a
contract that fails `select_best_contract()` or `derive_verdict()`'s spread gate during
an after-hours EOD run has no architectural mechanism within this module to be
re-evaluated against fresher, live-market data within the same run.

## Corrections to Passes A, B, C

1. **Six `_stand_down()` call sites, confirmed — but only 5 are inside `process_ticker()`
   itself.** The sixth (`:7153`) is `run_options_layer()`'s own per-row exception
   wrapper, classified via `_classify_block()` as `BLOCK_PIPELINE_ERROR`, and it is
   empirically live: 0/1,400 on 08-18 but 18/1,347 (1.3%) on 08-16 — a failure mode
   invisible in the primary reference run, only surfaced by checking the secondary one.
2. **`spread_limit` (selection-time) is confirmed distinct from `derive_verdict()`'s
   `MAX_SPREAD_PCT`** — not merely different in principle but different in value for the
   majority `1_5d` horizon bucket specifically (0.15 vs. 0.25), meaning the two gates
   filter different, non-overlapping populations of tickers, not the same threshold
   applied twice.
3. **No correction found to Pass A/B/C's own material** beyond what this pass's D1-D6
   scope required (the funnel boundary Pass C established, 1,612→1,400, is consumed
   here as given, not re-derived).

## What this pass did not cover

- Full column-by-column consumption audit of all 627 output columns (D6) — only
  targeted checks completed (verdict/tier/route three-way check, `csm_`/`tle_`/`layer2__`
  passthrough groups, the `options_fields` re-export list). The ~53 not-yet-checked
  `catalyst_*`/`scanner_*` overlap fields Pass C flagged remain open.
- Whether OI's own output contains internal `_x`/`_y` suffix artefacts distinct from the
  Pass C merge-boundary ones — not grepped this pass.
- Per-filter attrition breakdown within the six-stage `select_best_contract()` funnel
  for the 831 `BLOCK_NO_CONTRACT` rows — not recoverable from any artefact on disk
  without re-running the pipeline against historical chain data (explicitly out of
  scope); the 93.1%/6.9% repair-alternative split is the closest available proxy,
  reported as a proxy, not a precise count.
- The morning-mode counterfactual for the 2.0-spread contracts (D3's central open
  question) — no morning-mode artefact exists among the reference runs available.
- Deep trace of `fetch_chain()`'s own Polygon/MD fallback and retry logic
  (`:2238-2630`) beyond what was needed to establish the `bid=0`/`mid` mechanism — the
  BLOCK_CHAIN_ERROR path (0 observed in both runs) was not stress-tested against that
  logic's internals.
- `select_ev3_vertical_debit_candidates()` (`:4584-4650`) — the vertical-spread sibling
  of `select_repair_alternative_contracts()` — was not read in the same depth; it
  contributes to the `alternative_contracts_count` figures reported in D2 but its own
  internal filter logic was not separately audited.
- Reconciling this pass's `ev_adj_final`/`iv_factor` (inside `compute_ois`) against
  `compute_trade_economics()`'s differently-scoped `ev_adjusted`/`iv_factor` beyond
  noting they are distinct, independently-computed values sharing a name pattern — full
  tracing of every downstream reader of each was not performed.
