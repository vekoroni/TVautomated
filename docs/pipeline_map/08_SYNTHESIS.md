# Pass I — Synthesis

Read-only synthesis. No files edited, no pipeline phase executed, no new investigation performed.
Every claim below is drawn from one of the eight prior pass files and carries its source (pass
letter + file) and the path:line that pass itself cited. Where two passes disagree, both claims
are given with their sources and the disagreement is left unresolved, per the Standing Contract.
Where a finding rests on a proxy run, an incomplete census, or a single pass's unverified claim,
that is stated at the point the finding appears, not only in §I9.

**Source files** (Pass A–H): `00_SPINE.md`, `01_PHASES_0_3.md`, `02_PHASES_4_6.md`,
`03_PHASE_7_OPTIONS.md`, `04_PHASES_8_86.md`, `05_PHASES_9_11.md`, `06_MORNING.md`,
`07_FILE_CENSUS.md`, all in `data/scratch/pipeline_map/`.

**Provenance caveats carried into every relevant section below:**
- Pass A's dispatch ordering was corrected twice — by Pass B (Regime Screener actually runs
  *after* Discovery, not before) and by Pass C (Vanguard/Options Intelligence run before the
  Macro Horizon Router, not after). Where the spine and a later pass disagree on sequence, the
  later pass's ordering is used throughout this synthesis.
- Pass G used a proxy run (`20260809_195823`) for nearly all morning-path quantification, plus
  the aggregate of four available real morning-gate executions (3,663 rows total: `20260723_072618`,
  `20260731_083130`, `20260804_114554`, `20260809_195823`) for frequency-only questions. **No
  morning-gate artefact exists for either designated reference run** (`20260818_041214`,
  `20260816_075339`) — the morning path was never executed against either. Every morning-path
  number in this document is labelled proxy at the point it appears.
- Pass H left roughly 90 files UNCERTAIN after reaching a time/session limit. That gap is not
  re-resolved here.
- Reference runs: `20260818_041214` (primary), `20260816_075339` (secondary).

---

## I1 — The end-to-end funnel

**Primary reference run `20260818_041214`. Denominator for every percentage below is 3,323 — the
augmented universe Discovery actually consumed (base file 3,320 + 3 scanner-injected new tickers:
GOOG, TQQQ, SQQQ), established as the correct denominator by Pass B §0** (the un-augmented static
file, 3,320, and `dropoff_audit`'s `UNIVERSE` tracking-table count, 1,647, are both *not* usable
universe denominators — Pass B §0.1–0.2 traces why each is a different thing).

| Stage | Rows | % of 3,323 | Loss this stage | Source |
|---|---|---|---|---|
| Universe fed to Discovery (augmented) | 3,323 | 100.0% | — | Pass B §0, §1 |
| → tickers with usable bar data | 3,295 | 99.2% | 28 (no `load_bars()` result) | Pass B §8.1 |
| → Discovery organic candidates (post filters 1–7) | 1,649 | 49.6% | 1,646 (no signal / below tier floor) | Pass B §8.1–8.2 |
| → + External Intel Review Lane forced-review rows | +4 | +0.1% | (addition, not loss) | Pass B §8.1, §10 |
| **= Discovery final CSV** | **1,653** | **49.7%** | — | Pass B §8.1, §8.6 |
| → Package Build output | 1,651 | 49.7% | 2 (dotted tickers: BF.B, BRK.B) | Pass C |
| → Backfill Timeseries (packages with usable OHLCV) | 1,612 | 48.5% | 39 (`validate_series()` rejection) | Pass C |
| → Run VANGUARD PASS rows | 1,612 | 48.5% | 0 additional (same 39 tickers as Backfill, set-verified identical) | Pass C |
| → Options Intelligence input (inner join discovery×vanguard on ticker) | 1,612 | 48.5% | 0 this run (loss-free by construction this run, not a guarantee of the join itself) | Pass C |
| → OI eligible / enters scoring loop | 1,400 | 42.1% | 212 (tier filter ∪ Vanguard-support override, minus WAIT-intent exclusion) | Pass C→D boundary |
| OI terminal verdict split (same 1,400 rows, not a further row loss — see note) | STAND_DOWN 1,030 / ARMED 247 / EXECUTE 123 | 31.0% / 7.4% / 3.7% | verdict labels only | Pass D |
| → SuperBrain passthrough / EIL scored / GARCH merged | 1,400 (unchanged) | 42.1% | 0 — zero rows dropped anywhere across this entire span, both reference runs | Pass E E4 |
| → Phase 10 hard-block filter (`EOD_NO_OPTIONS_ROUTE`) | 1,385 | 41.7% | 15 | Pass F F5a |
| → Phase 10 "B2 FIX" filter (`eil_v3_verdict=="BLOCKED"`) | **1,135** | **34.2%** | 250 | Pass F F5a |
| **= `morning_candidates_{run_id}.csv`** — the artefact a human trader opens | **1,135** | **34.2%** | — | Pass F, Pass G (re-cited) |

**Important note on the OI terminal split:** Options Intelligence does **not** shrink the row
count of its own output CSV. All 1,400 rows (STAND_DOWN, ARMED, and EXECUTE alike) remain
present, with `options_verdict` as a column value, and flow unchanged in row-count terms through
SuperBrain, EIL, and GARCH (Pass E E4: "zero rows dropped anywhere in this span, in either
reference run"). The STAND_DOWN population is therefore a *verdict-level* exclusion from
tradeability, not a *physical* funnel narrowing — it is listed here for completeness but is not
subtracted from the row count carried to the next funnel stage. This distinction matters for §I2.

### Morning path — proxy-derived, not chainable onto the figures above

**No morning-gate execution exists for the 08-18 or 08-16 reference run** (Pass G, header note;
re-confirmed independently by Pass D and Pass F). Pass G's numbers below come from run
`20260809_195823` (evening pinned 2026-08-09, morning-gate actually executed 2026-08-10T16:41:02Z)
as the nearest available substitute, explicitly **not additive** to the 3,323/1,135 figures above
(different day, different universe size):

| Stage (proxy run `20260809_195823`) | Rows | % of that run's own 848 | Source |
|---|---|---|---|
| `morning_candidates.csv` input | 848 | 100.0% | Pass G |
| → `morning_validated_trades.csv` (morning_gate.py drops zero rows) | 848 | 100.0% | Pass G, Reconciliation §, confirmed across all 4 available real executions |
| morning_gate's own fresh `verdict=="GO"` | 300 | 35.4% | Pass G G5 |
| carried-through `eil_v3_verdict=="EXECUTE"` | 27 | 3.2% | Pass G G5 |
| carried-through `fd_verdict=="EXECUTE"` (=`thesis_decision`) | 5 | 0.6% | Pass G G5 |

### Secondary reference run (08-16) — stability check, not independently reconciled end-to-end

Universe 3,320 (100%) → 3,292 tickers with data (99.2%) → 1,649 discovery candidates (49.7%)
[Pass B §13] → OI scoring-loop entry 1,347 rows [Pass D] → OI terminal: STAND_DOWN 1,003 (74.5%
of 1,347) / ARMED 239 / EXECUTE 105 / BLOCK_PIPELINE_ERROR 18 [Pass D]. **No pass produced a
complete Phase-10 (1,347→final-manifest) reconciliation for 08-16** — Pass F's exact 1,400→1,135
attribution is 08-18-only; the 08-16 equivalent was not independently derived by any pass. This
gap is stated, not interpolated.

A separate, unreconciled arithmetic note for 08-16: Pass B reports 1,649 discovery candidates with
"no External Intel Review Lane report... located for that run — flagged UNVERIFIED," while Pass C
separately states Backfill processed "40 of 1,660" packages for 08-16 — an ~11-row gap between the
two passes' stated 08-16 denominators that neither pass reconciles. See §I9.

---

## I2 — The attrition ranking

Ordered by rows lost, largest first (primary reference run, denominator 3,323 unless noted). Each
row states whether the loss is a **physical row-count drop** (the row disappears from the next
stage's population) or a **verdict-level exclusion** (the row persists physically but is
functionally excluded from tradeability) — this distinction, drawn out in §I1, determines whether
a drop point appears once or is double-counted against a later physical filter.

| Rank | Drop point | Rows lost (% of 3,323) | Stable across both ref. runs? | Mechanism class | Market judgment or defect? | Recoverable? | Counterfactual | Auditable? |
|---|---|---|---|---|---|---|---|---|
| 1 | Discovery "no signal / below tier floor" (filters 1–7) | 1,646 (49.5%) — **physical** | Yes: 08-16 shows the same order of magnitude (Pass B §13) | threshold (7 sequential filters inside `scan_ticker_ultimate()`) | Mixed — filters 1–6 are liquidity/price screens (data-availability-adjacent); filter 7 is a tier-floor score threshold (market judgment, but regime-adaptive floor logic is itself unverified this run) | Terminal — no re-evaluation later in the same run | A different regime-driven tier floor, or a bypass via `detect_early_position()`, would change some outcomes | **No** — the module records **no per-ticker reason code** for any of the three silent-drop paths (no bar data / no signal / horizon-assignment None); all collapse to identical or absent log lines (Pass B §8.3) |
| 2 | OI `select_best_contract()` → `BLOCK_NO_CONTRACT` | 831 (25.0%) — **verdict-level** (row persists in every downstream artefact, `options_verdict=STAND_DOWN`) | Yes: 819/1,347 (60.8%) on 08-16, same order of magnitude | compound — six sequential hard/soft filters (right, DTE, OTM/ATM side, delta cap, liquidity+spread, target-reachability) | Mixed, quantified: 93.1% of these tickers have no real, complete quote anywhere in the chain for the eligible right even under a looser secondary search (data availability); 6.9% had real alternatives excluded specifically by the primary selector's tighter delta band / target-reachability / horizon-specific spread cap (defect/threshold, not market absence) | Terminal for the run — `select_best_contract()` runs once per ticker, no retry | A fresher/different chain snapshot would resolve the 93.1%; a different selection threshold would resolve the 6.9% | **No** — confirmed unauditable: the function returns `None` uniformly with no per-filter attribution; the diagnostic dict built to record this (`_rejection_entry`) is built and never used; the artefact that should capture it (`contract_rejection_log_*.csv`) captures **zero** of these 831 rows, only the unrelated `BLOCK_NO_CHAIN` case (Pass D D2) |
| 3 | Phase 10 "B2 FIX" — `eil_v3_verdict=="BLOCKED"` filter | 250 (7.5%) — **physical** | Not independently re-derived for 08-16 (F5a is 08-18-only) | threshold (single-field verdict filter) | Genuine disagreement between scoring systems, not data absence — see §I3 | Terminal — routed to `morning_blocked_review_{run_id}.csv`, no artefact carrying it is read anywhere on the morning path (Pass G G3) | A row with a different `eil_v3_verdict` (any of the other 3 tokens) would survive | Partially — the excluded rows are visible in `morning_blocked_review_{run_id}.csv`, but *why* `eil_v3_verdict` reached BLOCKED for that row is not separately recorded beyond the S1–S5 composite score itself |
| 4 | OI `derive_verdict()` gate 2 — `BLOCK_SPREAD` | 184 (5.5%) — **verdict-level** | Yes: 147/1,347 (10.9%) on 08-16, same mechanism, ~99% carrying the exact 2.0 value both runs | arithmetic identity (`bid=0`→`spread_pct=(ask-0)/(ask/2)=2.0` always) + control-flow ordering (two spread gates, one exempts synthetic marks, one does not) | Mixed, proxy-quantified via Pass G: of 73 same-defect rows in the `20260809_195823` proxy sample, only 3 (4.1%) resolved to a genuinely liquid contract live; 39 (53.4%) reproduced the identical illiquidity live — majority is real market condition, minority is a recoverable EOD-staleness artefact | Architecturally recoverable (the "SPREAD" token routes to `REPAIRABLE_ADVISORY`, not a hard block, at Phase 10 — Pass G G3), but the literal 08-18 184-row cohort was never itself run through the morning gate and remains formally unverified | A real two-sided quote (not `bid=0`) at the same strike, or extending the first gate's synthetic-mark exemption to the second gate, would move these rows out of STAND_DOWN | Auditable as to mechanism (fully traced, Pass D D3) but not flagged distinctly from a "real" wide spread in the output row itself beyond `mark_synthetic=True` |
| 5 | Backfill/Vanguard `DATA_FAILURE_NO_OHLCV` | 39 (1.17%) — **physical** | Yes: 40/1,660(ish) on 08-16, same signature | threshold (`validate_series()`: EMPTY / TOO_SHORT<120 bars / NULLS_IN_LAST_10 / STALE_LAST_BAR>5d) | Data availability (upstream Polygon/MarketData fetch failure or genuinely insufficient history) | Terminal — no retry within the run | Fresher/complete price history for that ticker | Partially — the aggregate 39-count and its 100% attribution to `DATA_FAILURE_NO_OHLCV` is confirmed, but the **per-reason breakdown** among the four `validate_series()` causes is not recoverable from any artefact on disk (Pass C) |
| 6 | Discovery "no usable bar data" (`load_bars()` None/empty, pre-scoring) | 28 (0.84%) — **physical** | Not independently re-derived for 08-16 | data availability (bare `continue`, before any scoring runs) | Data availability | Terminal | Fresher/present price data | **No** — no log line at all, not even DEBUG (Pass B §8.3) |
| 7 | Phase 10 hard-block filter (`EOD_NO_OPTIONS_ROUTE`) | 15 (0.45%) — **physical** | Not independently re-derived for 08-16 | threshold/status classification | Data availability (no chain/no eligible contract at all) | Terminal — no artefact carrying these rows is read anywhere on the morning path (Pass G G3) | A viable contract existing at all for the ticker | Visible only in `eod_dropoff_audit_{run_id}.csv` |
| 8 | OI `BLOCK_NO_CHAIN` | 15 (0.45%) — **verdict-level**, count coincides with row 7 above but identity between the two populations is **not independently confirmed by any pass** | Not independently re-derived for 08-16 | data availability (chain fetch returned nothing) | Data availability | Terminal | Chain data existing at fetch time | Fully auditable — the one case genuinely captured by `contract_rejection_log_*.csv` (Pass D D2) |
| 9 | Package Build dotted-ticker rejection | 2 (0.06%) — **physical** | Yes: exactly 1 (`BF.B`) on 08-16, same mechanism | threshold (`.` in ticker) | Defect-adjacent (the check is broader than its own docstring's "contaminated foreign-exchange suffix" framing — it also blocks legitimate US dual-class tickers) — reported per the Standing Contract's "do not propose changes" instruction | Terminal | A narrower "foreign-suffix-only" check | Fully auditable (`packages/index.json`'s `status:"BLOCKED"` entries) |
| 10 | OI other STAND_DOWN causes (`BLOCK_INVALID_INPUT`/`NO_DIRECTION`/`CHAIN_ERROR`/`PIPELINE_ERROR`) | 0/1,400 on 08-18, but **18/1,347 (1.3%) on 08-16** | **No — unstable.** An entire failure class invisible in the primary reference run, only surfaced by checking the secondary one | exception handler (`run_options_layer()`'s outer per-row `except`) | Ambiguous — not traced to a specific cause this pass | Terminal | Unknown — no stdout/log capture preserved for the 08-16 run to trace root cause | Partially — classified via `_classify_block()` into `BLOCK_PIPELINE_ERROR`, but the underlying exception text is not preserved as a separate artefact |
| — | ARMED-but-block-code-carrying rows (**not attrition**, listed for the register's completeness) | 247/1,400 (7.4%) | Consistent (239/1,347 on 08-16) | field-contract inconsistency (SOFT block codes stamped on never-blocked rows) | n/a — these rows are live/tradeable | n/a | n/a | A naive `block_code != 'NONE'` filter would wrongly count these as blocked (Pass D D1) |
| — | Regime-Adaptive Screener | 100% of its own intended output, **every one of 9 runs sampled including both references** — not a funnel-gating loss (its output is a supplementary signal layer, not a filter on the main candidate pool) | Yes — stable across all 9 | control-flow ordering (called before Vanguard produces its own required inputs) | Defect | Terminal for the run | Correct call-site ordering (after `run_vanguard_pipeline()`) | Fully auditable — the failure returns a structured dict, but the orchestrator only logs success conditionally, no failure log (Pass B §9) |

---

## I3 — The verdict divergence register

The pipeline produces at least eight distinct verdict-shaped vocabularies (the prompt's "at least
seven" is a floor; this synthesis counts eight distinct producers, several with byte-identical
aliases at the manifest).

| # | Field | Producer (path:line) | Read by |
|---|---|---|---|
| 1 | `options_verdict` (STAND_DOWN/ARMED/EXECUTE) | `derive_verdict()`, `avshunter_options_intelligence.py:5154-5384` [Pass D D5] | `sb_final_verdict` (byte-identical copy), campaign/execution-gate fallback chain |
| 2 | `options_verdict_tier` (STAND_DOWN/READY_PROBE/READY_EXECUTE/WATCHLIST/…) | `_options_verdict_tier_oi()`, `:310-339` [Pass D D6] | Not traced downstream beyond OI's own output |
| 3 | `final_route`/`options_route_verdict` (OPTIONS_GO_REVIEW/ARMED_HALF/PROBE_ONLY/BLOCKED) | `build_options_research_contract()`, `:5512-5744`, an independently-thresholded 0–100 research score [Pass D D6] | Forces `options_verdict='STAND_DOWN'` at exactly one point (`:6258-6264`) when `BLOCKED`; otherwise independent |
| 4 | `sb_final_verdict` | `run_superbrain_passthrough()`, `intelligent_orchestrator.py:2444-2451` — direct, untransformed copy of `options_verdict` [Pass E E1] | Feeds `ctx.superbrain_verdict` inside EIL, used only as a fallback default, never inside `evaluate()`'s scoring path |
| 5 | `eil_v3_verdict` | `execution_intelligence_runner.py:1339-1342`, normalised from `eil_result.eil_verdict` (the engine's **final**, hard-gated field) via `evaluate()`, `execution_intelligence.py:330-490` [Pass E E2] | `classify_tier()`, Handoff Guard, manifest passthrough |
| 6 | `eil_raw_verdict` (CSV column) | Same runner line, `:1339-1342` — **populated from `eil_result.eil_verdict` (final), not `eil_result.eil_raw_verdict` (true raw)** — a naming collision, not a distinct computation [Pass E E2] | Nothing reads the true raw value; it is computed and discarded |
| 7 | `campaign_verdict`/`execution_verdict` | `_enrich_truth_fields()`, `:840-841` [Pass E E2] | Gates the REJECT/SKIP early return at `:1424` that decides `fd_verdict` for 97.8% of rows — then **dropped**, absent from `EIL_COLS` (`:3297-3383`), never written to any CSV |
| 8 | `fd_verdict` (two spellings: `"BLOCK"` at `:1509`, `"BLOCKED"` at `:2102`) | Either the REJECT/SKIP branch (`:1509`, sourced from `options_verdict` via `sb_final_verdict`) for 97.8% of rows, or `_apply_retired_sizing_overlay()` (`:2102`, `= eil_v3_verdict`) for the remaining 2.2% [Pass E E2] | `eod_candidate_engine.py:563-564,767,1682,2081-2090,2256`; overwritten in place for 125/1,400 rows by the Handoff Guard (Pass F F2a) |
| 9 | `fd_advisory_verdict`/`final_decision_advisory_verdict` | `eod_candidate_engine.py`, a **third** distinct vocabulary at the manifest (byte-identical to each other) [Pass F F5a] | Manifest display column |
| 10 | `eil_signal_verdict`/`thesis_decision` | Byte-identical aliases of `eil_v3_verdict` / `fd_verdict` respectively at the manifest [Pass F F5a] | Manifest display columns |
| 11 | morning_gate.py's own `verdict` (GO/FLAG/BLOCK) + `execution_permission`/`morning_execution_permission` (GO/WAIT/CONTRACT_REPAIR/MODEL_RISK_REVIEW/ARMED/BLOCKED) | `run_gate()`, `morning_gate.py:1146-1230`, computed **fresh from CHECK1-5 alone** — consults **none** of fields 1–10 (confirmed by full-file grep, zero occurrences) [Pass G G5] | `contracts/lab_control.py`'s `mv_execution_permission` fallback chain |
| 12 | `lab_verdict` | `resolve_lab_tradeability()`/`apply_lab_resolution()`, `contracts/lab_control.py:1381,1540` — a **seventh** vocabulary (GO/GO_LIMIT/PROBE/CONTRACT_REPAIR/MORNING_VALIDATION_REQUIRED/ARMED/WAIT/BLOCKED) [Pass G G5] | Terminal Lab-facing field; sourcing logic confirmed correct at `:822` but final assignment not independently re-verified (Pass G, open item) |

### Measured disagreements (all named in the brief, sourced)

| Disagreement | Value | Source |
|---|---|---|
| `fd_verdict` vs `eil_v3_verdict` agreement at the manifest | **4.8%** (55/1,135) | Pass F F5a |
| OI-rejected (STAND_DOWN) rows scoring EIL-tradeable (EXECUTE/EXECUTE_WITH_CAUTION) | **67.4%** (944/1,400) | Pass E E4 |
| EIL's own EXECUTE-scored rows reverting to WATCHLIST at `fd_verdict` | **83.3%** (45/54) | Pass E E4 |
| Rows where `eil_v3_verdict` never reaches `fd_verdict` at all (REJECT/SKIP short-circuit fires first) | **97.8%** (1,369/1,400) | Pass E E2 |
| Eligibility spread on the same 848-row proxy artefact — morning_gate `verdict=="GO"` vs carried-through `eil_v3_verdict=="EXECUTE"` vs carried-through `fd_verdict=="EXECUTE"` | **300 vs 27 vs 5** (35.4% / 3.2% / 0.6%) — **proxy-derived, run `20260809_195823`, not the 08-18/08-16 reference runs** | Pass G G5 |
| OI's own internal three-way disagreement (`options_verdict` / `options_verdict_tier` / `final_route`), reconciled at only one point (`:6258-6264`) | STAND_DOWN-but-READY_PROBE-tiered: 183-184 rows; EXECUTE-but-ARMED_HALF: 36 rows; ARMED-but-PROBE_ONLY: 106 rows; ARMED-but-GO_REVIEW: 8 rows | Pass D D6 |

### Which field ultimately determines what reaches the trading plan?

**No single field.** At the manifest (`morning_candidates.csv`), five materially diverging
verdict columns are simultaneously present (Pass F F5a), and morning_gate.py then computes a
**sixth**, wholly independent vocabulary that consults none of the five (Pass G G5), and
`lab_control.py` computes a **seventh** downstream of that. Which field a human trader or
downstream script chooses to trust changes the same 1,135-row (or, proxy-derived, 848-row) slate
from ~93% "execute-tradeable" to ~97% "watchlist-only" depending purely on column choice (Pass F
F5a). **Neither Pass F nor Pass G traced which field `morning_gate.py`'s own human/script consumer
actually treats as authoritative** — this is an explicitly open question in both passes.

### Ordering vs field-name-mismatch vs genuine disagreement

- **Ordering-caused:** the 97.8% `fd_verdict`-bypasses-`eil_v3_verdict` figure is a direct
  consequence of the campaign/execution REJECT/SKIP branch being computed *before* `fd_verdict`
  consults EIL's own verdict (Pass E E2).
- **Field-name-mismatch:** `eil_raw_verdict`'s CSV column holding the final, not the raw,
  verdict (Pass E E2); the `fd_verdict` "BLOCK" vs "BLOCKED" spelling split (Pass E E2).
- **Genuine disagreement (independent scoring systems, not ordering or naming):** `options_verdict`
  vs `eil_v3_verdict` (two independently-thresholded systems — OIS-based vs S1–S5 composite, Pass
  E E2/E4); the three-way OI-internal disagreement (`options_verdict`/`options_verdict_tier`/
  `final_route`, Pass D D6); morning_gate's own verdict vs all evening fields (a sixth,
  independently-computed vocabulary that never consults the other five, Pass G G5).

---

## I4 — The field-drop register

### Written and never read by anything

| Field(s) | Producer | Evidence | Source |
|---|---|---|---|
| `wyckoff_validation_*` (21 fields) | `wyckoff_phase_validator.py` | Repo-wide grep: matches only in the producer file | Pass B §8.6 |
| `final_discovery_route` | `avshunter_discovery_ULTIMATE.py:2026` | Repo-wide grep, no other reference | Pass B §8.6 |
| `precor_intent_raw` | `wyckoff_crabel_precor_logic_v2.py:220` — self-labelled "explicit audit label" | Repo-wide grep | Pass B §8.6 |
| `activist_priority_boost` | `avshunter_discovery_ULTIMATE.py:2205` | Repo-wide grep | Pass B §8.6 |
| `macro_bias`/`macro_bias_source` | Macro Enrichment to Discovery (`intelligent_orchestrator.py:3696-3697`) | Zero matches in `avshunter_options_intelligence.py`; confirmed carried unread through Package Build and Vanguard's payload builder | Pass C |
| `campaign_verdict`/`execution_verdict` | `execution_intelligence_runner.py:840-841` | Absent from `EIL_COLS` (`:3297-3383`); `KeyError` on direct query of both reference-run CSVs — **decisive for control flow but itself dropped**, ranks highest by consequence (see below) | Pass E E2, E5 |
| `eil_result.eil_raw_verdict` (true dataclass field) | `execution_intelligence.py`'s `evaluate()` | Computed, returned, then never written to any CSV (the CSV column of the same name holds a different field) | Pass E E2 |
| `_percentile_override_active`/`fd_percentile_override` | `execution_intelligence_runner.py:1241,2107` | Repo-wide grep: only the two write sites, zero readers anywhere | Pass E E2 |
| `wbs_grade`/`wbs_score` | `wall_break_scorer.py`, for 123 EXECUTE-tier tickers | Never merged back into `eil_enriched.csv`; **may** be partially recovered via a separate `WBS_MERGE_COLS` side-load in `build_candidate_manifest()` — flagged as an open, uncross-checked question by both Pass E and Pass F | Pass E E1.5, Pass F Closing Synthesis |
| `execution_mode` | Unclear upstream source | 100% empty string across all 1,135 manifest rows; not traced to a specific drop point | Pass F F5a |
| `l3_iv_percentile`/`l3_iv_rank`/`l3_expected_move_pct` | Dead fallback names referenced by `mcmillan_advisory_layer.py` | No producer writes these exact strings anywhere; harmless because an earlier fallback candidate resolves first in ~99% of rows | Pass F F4 |
| `HIGH_CONVICTION` token | Dead entry in `_EIL_TOKEN_NORMALISE`'s mapping table | Never produced by `evaluate()`'s only 5 possible final-verdict strings | Pass E E2 |

### Read under a name its producer does not emit

| Consumer / field | Issue | Source |
|---|---|---|
| Bare `iv_rank` at `avshunter_options_intelligence.py:819` | After the discovery/vanguard merge, only `iv_rank_x`/`iv_rank_y` exist — bare `iv_rank` returns nothing at this call site; partially mitigated by an earlier-checked, non-overlapping fallback field (`iv_rank_252d`) | Pass C, "Field-drop at the OI boundary" |
| `l3_iv_percentile`/`l3_iv_rank`/`l3_expected_move_pct` (McMillan) | No producer anywhere emits these — see above | Pass F F4 |
| `live_data_mode` at `contracts/lab_control.py:591` | Never written by `morning_gate.py` — the check is permanently inert (always evaluates "not paper mode") | Pass G G5 |
| `morning_present` set membership at `lab_control.py:856` | Tests against `{GO,GO_LIMIT,PROBE,ARMED,CONTRACT_REPAIR,WAIT,BLOCKED}` — excludes `MODEL_RISK_REVIEW`, one of morning_gate.py's real 6 permission values | Pass G G5 |
| `eod_candidate_engine._true_fatal_block()` checks `fd_verdict=="BLOCK"` exactly | Never matches the `"BLOCKED"` spelling used at `execution_intelligence_runner.py:2102` — confirmed dead in both reference runs (zero observed impact, since the gate is dead for a broader reason too) | Pass E E2 |

### Handoffs where a consumer expects a field the producer does not supply

Same list as above (McMillan's three dead `l3_*` fallback names, `live_data_mode`), plus:
**`ctx.wbs_grade`/`ctx.wbs_score`** (`execution_intelligence.py:682-683`) default to `"POSSIBLE"`/`0.0`
for all 1,400 rows because the column never exists in the row EIL reads — confirmed zero
consequence since no S1–S5 strategy reads them either (Pass E E1.5).

### The `_x`/`_y` split — 56 unreconciled column names at the OI merge boundary

`pd.merge(disc, vanguard, on='ticker', how='inner')`, `avshunter_options_intelligence.py:7061`.
111 of 311 discovery columns overlap with 509 vanguard columns; 3 reconciled explicitly (`timestamp`,
`adx_14`, `atr_percentile_rank`), 52 via `resolve_macro_suffix_columns()`. **56 left unreconciled**:
all 26 `catalyst_*`, all 16 `scanner_*`, plus `crabel_compression`, `crabel_pattern`, `crabel_state`,
`cheap_convexity_flag`, `days_to_catalyst`, `dominant_trend`, `event_convexity_score`, `iv_rank`,
bare `sector`, `vms_decision`, `vms_score`, `vol_spread`, `volume_ratio`, `vwap_bias` (Pass C).

- **Confirmed live impact:** bare `iv_rank` (above).
- **Confirmed NOT affected** (checked, zero access): `dominant_trend`, `crabel_state`, `vwap_bias`
  (Pass C).
- **Not exhaustively checked:** ~53 of the 56 — flagged by Pass C as the top follow-up item,
  **never completed by any later pass** (Passes D–H do not revisit this).
- **Confirmed NOT recurring elsewhere:** Catalyst Truth's own patch mechanism explicitly drops
  pre-existing `catalyst_*` columns before merging (Pass F F3); GARCH's merge does the same for
  `l3_*` (Pass F F1); zero `_x`/`_y`-suffixed columns exist in `eil_enriched.csv` (Pass E E5).

### Silently coerced or defaulted rather than failing

- **McMillan's `move_theta_ratio`: the brief's named `"UNAVAILABLE"`→`0.0` case.** `move_theta_ratio`
  returns an explicit `""` sentinel (not a real zero) for 861/1,400 rows where `contract_theta` is
  unresolvable (only 554/1,400, 39.6%, have a selected contract at all — the same population Pass
  D's contract-selection funnel already characterises). CSV round-trip turns `""` into `NaN`;
  `eod_candidate_engine._flt()`'s default argument turns `NaN` into `0.0`. Confirmed at the manifest:
  **836/1,135 rows (73.7%)** show a literal `0.0`, exactly matching (crosstab-confirmed, zero
  off-diagonal) rows where `move_theta_margin_label=="UNAVAILABLE"` — the label is the only
  surviving way to distinguish a true data gap from a real near-zero ratio, three stages removed
  from where the sentinel was created (Pass F F4, F5a).
- **The 2.0 spread value** is not a coercion/default but an *emergent arithmetic identity*
  (`bid=0` + midpoint-based spread formula → exactly `2.0` for any ask value) that a later gate
  then treats as an informative spread reading, distinguishable downstream only via
  `mark_synthetic=True` (Pass D D3).
- **Likely-systemic, not individually verified:** "the same NaN→0.0 default mechanism almost
  certainly affects other sparsely-populated `_flt()` fields... not individually re-verified this
  pass beyond `move_theta_ratio`" (Pass F F5a) — e.g. `contract_theta`, `contract_gamma` for the
  same 846/1,400 no-contract rows.
- **Actuarial cache-miss** returns a deliberate neutral prior (win_rate≈0.52, `penalty_multiplier=1.0`)
  rather than a hard zero — an intentional fail-open substitution, not a coercion bug (Pass B §6).

### Ranked by consequence (feeds a verdict > feeds a display column)

1. `campaign_verdict`/`execution_verdict` — decisive for 97.8% of `fd_verdict` outcomes, then dropped.
2. `eil_result.eil_raw_verdict` naming collision — obscures whether an observed `BLOCKED` came from a hard gate or a score threshold.
3. `move_theta_ratio`'s `UNAVAILABLE`→`0.0` (836/1,135, 73.7%) — a manifest field a trader could misread as a real ratio.
4. The 56 unreconciled `_x`/`_y` fields (catalyst_*/scanner_* impact unquantified, flagged not resolved).
5. `wyckoff_validation_*` / other write-only discovery fields — feed nothing.
6. `wbs_grade`/`wbs_score` — confirmed zero consequence inside EIL.
7. `execution_mode` (100% empty) — display only.
8. McMillan's three dead `l3_*` fallback names — zero observed consequence.

---

## I5 — The fail-open register

Ranked by how far downstream the degraded value travels before reaching a human or a terminal
artefact.

| # | Fail-open point | Downstream effect | Distinguishable from genuine data? | Source |
|---|---|---|---|---|
| 1 | Handoff Conflict Guard's default (`AVSHUNTER_STRICT_ACTUARIAL_V6` unset) | 125/1,400 (8.9%) rows have `fd_verdict`/`pse_execution_mode` **overwritten in place** to `"WATCHLIST"`/`0.0`; the strict-abort branch never fires under the observed configuration, propagates all the way to `morning_candidates.csv` | Pre-downgrade value not recoverable from disk except by cross-referencing the untouched `eil_v3_verdict` on the same row | Pass F F2a |
| 2 | Campaign/execution REJECT/SKIP branch (sourced from `options_verdict`, computed before EIL is consulted for `fd_verdict` purposes) | Determines `fd_verdict` for 97.8% of rows independent of EIL's own composite score | Not distinguishable from the manifest alone — requires comparing `fd_verdict` against `eil_v3_verdict` | Pass E E2 |
| 3 | The ~5–7 hard-abort conditions across 43 evening dispatch items | Everything else (EIL itself, GARCH, McMillan, Catastrophe Gate [no-op], Wall Break Scorer, Trigger Layer, Catalyst Truth, actuarial enrichment) is non-critical / fail-open; a run completes and is reported `True` even if most enrichment stages silently failed | Only visible via `pipeline_integrity_{run_id}.json`'s `manifest_permission` degradation flags, which no confirmed reader consumes beyond existence/mtime (Pass F F6) | Pass A §2.2 note after item 43 |
| 4 | Discovery's per-ticker silent drops (no bar data / no signal / horizon-assignment None) | No per-ticker reason code persisted anywhere; three structurally distinct failure paths collapse to identical or absent log lines | Not distinguishable per-ticker; only the aggregate 3-way split (28/1,646/1,649) is reconstructable | Pass B §8.3 |
| 5 | CHECK 1 (`morning_gate.py`) missing `live_price` | Routes to a distinct `FLAG`/`WAIT`/`NO_TRADE` state (not a false GO, not a BLOCK) — **quantified 2/3,663 (0.05%), proxy-derived across the four available real morning-gate executions, not the reference runs** | Distinguishable if `entry_action`/`route` fields are read, not distinguishable from a genuine `CONTRACT_REPAIR` flag by verdict alone | Pass G G2 |
| 6 | OI's synthetic-mark spread-gate asymmetry (first gate exempts `mark_synthetic`, second does not) | Converts a data-completeness artefact into a hard `STAND_DOWN` for 184/1,400 (5.5% of 3,323) rows | `mark_synthetic=True` flag survives on the row, but the verdict itself does not distinguish "real wide spread" from "arithmetic artefact" | Pass D D3 |
| 7 | Sector Bias Map — present-but-broken `sector_alignment.py` | Any exception degrades silently to `missing_macro_quant_packet()`; only the file-*missing* case is (conditionally) fail-closed | Not distinguishable from a genuinely-clean run without checking logs | Pass B §3 |
| 8 | Macro Contract Normalisation failure | Degrades `manifest_permission` to `REVIEW_ONLY_MACRO_DEGRADED` rather than aborting | Visible only in the same under-read `pipeline_integrity_*.json` | Pass B §4 |
| 9 | Actuarial Cache Build cache-miss | Neutral prior (win_rate≈0.52, `penalty_multiplier=1.0`), deliberate, not zero | Distinguishable via `valid=False`/`no_match=True` on the cache row | Pass B §6 |
| 10 | Regime-Adaptive Screener | 100% output loss, 9/9 sampled runs; orchestrator logs success conditionally, **no failure log exists** | Not distinguishable without directly inspecting the (always-empty) output directory | Pass B §9 |
| 11 | Backfill Timeseries three-way outcome (rc=2 → warn+continue) | Failed tickers excluded, run continues; the orchestrator's own log message mislabels the cause ("TOO_SHORT tickers") when the actual gate is reason-agnostic | Cosmetic log imprecision only; the underlying fail-open behaviour is correct for all 4 reasons | Pass C |
| 12 | Trap Engine per-package exception | Replaced with `_neutral_tle()` (`tle_verdict="NO_TRADE"`, both scores 0) | Indistinguishable from a genuine "no trap detected" outcome without a stack trace | Pass C |
| 13 | GARCH runner/merge (missing script/input, or per-target merge exception) | Silently skipped; per-target merges independently caught so one failure doesn't block others | `l3_method` null for unmatched rows is the only trace | Pass F F1 |
| 14 | Catalyst Truth Engine (`ImportError`/any `enrich_run()` exception) | Caught and logged; per-target patch failures don't stop other targets | `patch_results` JSON records per-target status if the summary itself survives (it is overwritten across the 3 call times — see §I6) | Pass F F3 |
| 15 | McMillan advisory layer (`ImportError`/exception) | Caught non-critically | n/a | Pass F F4 |
| 16 | `handoff_contract_audit.py` (the read-only auditor) | Non-critical; a failure would be logged and swallowed, not exercised in either reference run | n/a | Pass F F2b |
| 17 | EIL itself at the workflow level | `if not eil_ok: log error` — does **not** `return False`; but everything nested in its success branch (actuarial safety net, GARCH, Trigger Layer CSV, Handoff Guard) is **skipped entirely** if EIL fails — a fail-open wrapper hiding a fail-closed cascade for four downstream items | n/a | Pass A item 27 |
| 18 | `morning_gate.py`'s live-fetch failures | `_fetch_live_price()`/`_fetch_live_contract()` never raise; return a diagnostic-marker dict (`_FAILED` suffix) rather than dropping the row | Marker column present, distinguishable if read | Pass G G6 |
| 19 | CHECK 2 (macro regime), CHECK 4 (bond macro) | Both fail open when their source file is missing/stale/`UNKNOWN`; neither ever produces a `BLOCK` | n/a | Pass G G2 |
| 20 | CHECK 5 (L3 model risk) | A `None` source field produces zero flags — a soft no-op, not a documented fallback | Indistinguishable from "checked and clean" | Pass G G2 |
| 21 | `pipeline_integrity_{run_id}.json`'s `fatal_flags` computation | Checks only row-level verdict self-consistency (3 hardcoded contradiction checks), not field timing/provenance — would not have caught the GARCH-after-EIL ordering defect even if fully read | n/a | Pass F F6 |

**Exception to the fail-open pattern, noted for completeness:** Package Build's per-ticker loop
has **no** try/except around `build_package()`/`write_json()` themselves — an exception there would
crash the whole subprocess (fail-**closed** at the run level). Not observed in either reference run
— a theoretical path, not an empirically exercised one (Pass C).

---

## I6 — The ordering-defect register

Seven confirmed control-flow-ordering defects, in the order Pass B–G established them, plus each
instance's specific mechanics.

| # | Stage that runs too early | Data it needed | When that data actually arrives | Blast radius | Source |
|---|---|---|---|---|---|
| 1 | Regime-Adaptive Screener ("Phase 4.7") | `vanguard_signals*.csv` or `superbrain_enriched*.csv` | Produced by `run_vanguard_pipeline()` (Vanguard) and SuperBrain passthrough — both run **after** the Screener's call site | 100% of its own intended output (mean_reversion/vol_expansion/structural_breakout signals), every one of 9 runs sampled including both references | Pass B §9 |
| 2 | Trap Engine's VWAP_RECLAIM/VWAP_LOSS signals (bullish/bearish T2, weight 2 each) | `pkg["triggers"]` | Written by `trigger_layer.patch_run_packages()` at Phase 8.6 — hundreds of lines and several phases after Trap Engine's own call site inside `run_vanguard_pipeline()` | 2 of 12 max weighted points structurally unreachable in every package, every run — **scoped precisely**: does not affect `trigger_quality`/`trigger_go_eligible` as later read by `classify_tier()`, which is computed independently and correctly | Pass C, Pass E E3 |
| 3 | Discovery/Vanguard `_x`/`_y` merge (56 of 111 overlapping column names unreconciled) | A merge-key-aware reconciliation step for every overlapping field | Only 55 of 111 are explicitly reconciled (`timestamp`, `adx_14`, `atr_percentile_rank`, and 52 via `resolve_macro_suffix_columns()`); the rest are never revisited | 1 confirmed live impact (`iv_rank`, partially mitigated); ~53 of 56 fields never checked for consumption impact | Pass C |
| 4 | OI's second spread gate (`derive_verdict():5248-5260`) | The `mark_synthetic` exemption the *first* spread gate (`:5236-5247`) already applies | Never arrives — the second gate has no equivalent exemption, by omission not by later timing | 184/1,400 (5.5% of 3,323) rows STAND_DOWN via `BLOCK_SPREAD` | Pass D D3 |
| 5 | GARCH (item 29) | EIL's `evaluate()` reads `l3_expected_move_1_5d`/`l3_expected_move_6_10d` first-priority | GARCH runs strictly after EIL has completed as a separate subprocess and written its final `eil_enriched.csv`; patched retroactively into **three** targets (`superbrain_enriched.csv`, `eil_enriched.csv`, **and `execution_v3_5.csv`** — Pass F corrects Pass E's count of two) | 100% of rows in both reference runs (1,400/1,347) had their EIL composite score computed with zero GARCH forward-vol/IV-tailwind input; the `l3_*` fields **do** reach a real, later, non-verdict consumer (exit-planning/informational fields in the candidate manifest) — the verdict itself never sees them | Pass E E2.5, Pass F F1 |
| 6 | Catalyst Truth's `_patch_targets()` list (9 targets, all 3 call times) | `morning_candidates.csv` and `final_opportunity_book.csv` to exist | Neither exists yet even at the **latest** call (`post_eil`) — the candidate manifest is built at item 34, after `post_eil`'s call at item 32; the opportunity book is written near the very end of the run | 2 of 9 patch targets are structurally dead-on-arrival at every one of the 3 call times, not merely unlucky this run — **mitigated**: `eod_candidate_engine.py` independently carries `catalyst_*` fields forward via its own passthrough loop from the (successfully-patched) `eil_enriched` row, so `morning_candidates.csv` ends up populated, just not via this mechanism | Pass F F3 |
| 7 | `morning_gate.py`'s priority-order (`run_gate()`'s actual `elif` chain vs. its own module docstring's CHECK1→2→3→4→5 numbering) | n/a — not a data-timing defect, a documentation-vs-implementation ordering mismatch | The actual resolution order is: `invalidation_unverified` → genuine CHECK1 → CHECK3(contract) → CHECK5(model risk) → CHECK2(macro) → CHECK4(bond) → else GO | The single-valued `morning_execution_route`/`morning_unlock_condition`/`execution_permission` fields reflect only the **highest-priority failure in the code's actual order**, not the docstring's stated order, when a row fails more than one check simultaneously (the concatenated `flag_reason` string does still capture every failing check's text) | Pass G G2 |

---

## I7 — The documentation-vs-code register

| # | What the documentation claims | What the code does | Authoritative |
|---|---|---|---|
| 1 | CLAUDE.md's 13-line evening phase list (Phase 0→Preflight … Phase 11→Diagnostics/Archive) | Every one of the 13 lines conflicts with the code in some way — duplicate phase numbers ("4.7" used twice for unrelated stages), a stale "Phase 1B" comment left at its old call site after the real call moved, "Phase 7.5" running numerically after "Phase 8.5," three different numbering vocabularies ("PHASE"/"STAGE"/unlabelled) in one function, wrong module name for Discovery, and "Phase 8" (SuperBrain/WBS/EIL) actually spanning code labels "8d," "Layer 4b," and "PHASE 9" for three unrelated things | Code (full discrepancy table given in Pass A §5) |
| 2 | CLAUDE.md Sprint 3: Trap-to-Launch Engine framed as **not yet built** — "Do not begin coding until you have confirmed [an architectural decision] with the human trader" | `avshunter_trap_engine.py` is live, tracked in git, fully wired into `run_vanguard_pipeline():2026-2044`, and its downstream CSM-modifier integration in `build_convexity_strike_map()` is also fully implemented and empirically firing (148/1,400 rows, 08-18) | Code (Pass B §15 first flags the contradiction; Pass C independently confirms and extends it) |
| 3 | `derive_verdict()`'s framing (carried in from a prior audit as "six hard gates") | Direct count of `return 'STAND_DOWN'` statements is **seven**, not six; the two spread checks are not equivalent in practice (one exempts synthetic-mark contracts, one does not) — a prior audit likely counted them as one logical gate, which Pass D's own D3 finding shows is not a safe simplification | Code, with the caveat that Pass D itself is not certain why the prior count was six (self-flagged, not fully resolved) — **note: this synthesis found no reference in Passes A–H to a specific "derive_verdict() docstring's three phantom hard blocks" claim; the closest documented analog is the retired SuperBrain's `assemble_execution_plan()`, which carries 8 fully-documented, fully-implemented hard/soft gates that are architecturally unreachable because the file is never called (Pass E E1)** — this gap is carried into §I9 rather than resolved by inference |
| 4 | Actuarial cache builder's own module docstring: consumed by `build_packages_from_discovery.py` ("Step 2, before Package Builder") and by `position_sizing_engine.py` | `build_packages_from_discovery.py` contains zero references to `actuarial_cache`; `position_sizing_engine.py` is confirmed dead code (`_pse_compute = None`); the only in-repo reader is `actuarial_enrichment_pass.py` (Phase 8.5), which runs **after** Options Intelligence — several stages later than "before Package Builder" | Code | Pass B §6 |
| 5 | CLAUDE.md's testing protocol: `handoff_contract_audit.py` baseline "warn=8, fail=0" | Both reference runs, read directly, show `warn_count=12, fail_count=0`, identically | **Unresolved** — whether 8 was ever the true baseline (no older run available) or CLAUDE.md's number is simply stale is an open question, not settled by any pass | Pass F F2b |
| 6 | The runner's own field name (`eil_raw_verdict`) implies it holds the raw, pre-hard-gate verdict | It holds a copy of the engine's **final** verdict; the true raw value is computed and discarded | Code (this is a code-internal naming/behaviour mismatch, not a CLAUDE.md claim, but included per the brief's explicit instruction) | Pass E E2 |
| 7 | CLAUDE.md's own morning run command: `python morning_thesis_validator.py --tiers A,B,C,WATCH --max-signals 0 --live` | The live entry point is `python intelligent_orchestrator.py --morning` → `premarket_workflow()` → `morning_gate.py`, whose own header states outright: "Replaces morning_thesis_validator.py entirely." Full-file grep of `premarket_workflow()` finds zero references to `morning_thesis_validator` | Code | Pass G G1 |
| 8 | CLAUDE.md Sprint 1: `avshunter_exit_engine.py` framed as "the most impactful single addition to the pipeline... Priority: HIGHEST" | Its sole importer anywhere in the repo is `morning_thesis_validator.py:2962` — itself confirmed superseded. `morning_gate.py` (the live module) has zero references to `exit_engine`/`exit_rules`. A **different** module, `scripts/exit_rules_engine.py` ("B3 — Exit Rules Engine"), is the one actually live in `eod_candidate_engine.py`'s manifest-build safety nets | Code | Pass H §6 |
| 9 | `normalise_macro_contract.py`'s own docstring: "This script ADDS fields to the existing JSON — it does NOT replace it. All existing fields are preserved" | True for the four guarded score fields (existence/validity-checked before write); **not true** for `normalise_macro_regime_fields()`, which unconditionally overwrites 5 regime fields on every single normalisation run, no guard | Code, scoped precisely (the augment-only claim holds for one part of the module, not the whole) | Pass B §4 |
| 10 | The retired SuperBrain file's own comment: HARD GATE 0b5 requires "GARCH now runs in Phase 8c.5 (before SuperBrain) so `l3_iv_tailwind_score` is populated at verdict time" | Stale relative to the current orchestrator — GARCH runs at item 29, after both the SuperBrain passthrough (item 22) and EIL (item 27); moot since the file never executes, but demonstrates doc drift compounding across versions | Code (moot, since the referencing file is itself dead) | Pass E E2.5 |
| 11 | GARCH merge's own docstring lists 9 `l3_` fields | Actual output is 16 fields — stale, harmless documentation drift | Code | Pass F F1 |
| 12 | `intelligent_orchestrator.py:375`/`scripts/avshunter_superbrain_layer.py:7,17`: "Do NOT remove — EIL/GARCH/WBS/CT Gate require `superbrain_enriched` to exist" | Read literally this protects the *file*; its real intent (confirmed by tracing what actually produces the artefact) is that the **output artefact** `superbrain_enriched_{run_id}.csv` must exist — which is produced by an inline orchestrator function, `run_superbrain_passthrough()`, not by the commented file at all. The file itself (per §2 above) is confirmed BYPASSED — nothing calls it | The comment is misleading about what needs protecting, though its underlying caution (a past incident) is real | Pass H §13 |

---

## I8 — The remediation table

Sorted by rows affected where quantified; structural (non-row-quantified) findings follow.
**Untracked-in-git** status is per Pass H's direct `git status`/tracked-file checks; "UNVERIFIED"
where no pass stated it explicitly.

| Finding | Rows affected | Mechanism class | Live path? | Recoverable? | Evidence (pass + path:line) | Untracked file? |
|---|---|---|---|---|---|---|
| Discovery tier-floor rejection | 1,646/3,323 (49.5%) | threshold, compound (7 sequential filters) | Yes | Terminal | Pass B §8.1-8.2; `avshunter_discovery_ULTIMATE.py:1192-2123` | No (tracked) |
| OI `select_best_contract()` unaudited 6-stage filter → `BLOCK_NO_CONTRACT` | 831/1,400 (25.0% of 3,323) | compound threshold, unauditable (no per-filter attribution recorded anywhere) | Yes | Terminal | Pass D D2; `scripts/avshunter_options_intelligence.py:4122-4318` | Yes (untracked) |
| `_rejection_entry` dead diagnostic code — built, never used | n/a (diagnostic gap, not a row loss itself) | dead code | Surrounding code live | n/a | Pass D D2; `:5984-5991` | Yes |
| `contract_rejection_log_*.csv` misleadingly named — captures only `BLOCK_NO_CHAIN` (15), zero of the 831 `BLOCK_NO_CONTRACT` rows | 831 rows invisible to this artefact | auditability gap | Yes | n/a | Pass D D2; `run_options_layer():7290-7308` | Yes |
| Phase 10 "B2 FIX" — `eil_v3_verdict=="BLOCKED"` filter | 250/1,385 (7.5% of 3,323) | threshold, genuine cross-system disagreement | Yes | Terminal | Pass F F5a | No |
| bid=0 / spread=2.0 arithmetic identity + gate asymmetry (`BLOCK_SPREAD`) | 184/1,400 (5.5% of 3,323) | arithmetic identity + control-flow ordering | Yes | Architecturally recoverable but empirically resolves favorably only ≈4% of the time in a proxy sample; the literal 08-18 cohort unverified | Pass D D3, `fetch_chain_md():2408-2410`, `derive_verdict():5236-5260`; proxy quantification Pass G G3 | Yes |
| `NameError` at `avshunter_options_intelligence.py:6069-6070`, silently swallowed | Every row, every run — OBI runs on GEX synthesis only, unconditionally | exception handler swallowing a real bug | Yes (the surrounding code runs; this specific enrichment silently no-ops) | Currently always-firing | Pass D D1; `:6057-6072` | Yes |
| Two independently-thresholded OI verdict systems reconciled at one point only | 183-184 / 36 / 106 / 8 rows (four distinct disagreement patterns) | genuine disagreement (two independent scoring systems) | Yes | n/a — both compute correctly | Pass D D6; `:6258-6264` | Yes |
| `campaign_verdict`/`execution_verdict` computed-then-dropped | Decisive for 1,369/1,400 (97.8%) `fd_verdict` outcomes | field-drop at the write-list boundary | Yes | Not recoverable from any artefact | Pass E E2/E5; `execution_intelligence_runner.py:840-841,1424`, `EIL_COLS :3297-3383` | Yes |
| `eil_raw_verdict` naming collision | All rows (obscures which mechanism produced any observed `BLOCKED`) | field-name collision | Yes | Not recoverable — true raw verdict never written anywhere | Pass E E2; `:1339-1342` | Yes |
| `fd_verdict` spelling divergence ("BLOCK" vs "BLOCKED") | 0 observed impact in either reference run (the gate is dead for a separate, broader reason too) | field-name/spelling mismatch | Live code path, currently inert | n/a | Pass E E2; `:1509` vs `:2102`; `eod_candidate_engine.py:564,598` | Runner: Yes; `eod_candidate_engine.py`: No |
| GARCH-after-EIL ordering defect | 1,400/1,400 (100%) rows, both reference runs, EIL verdict computed with zero GARCH input | control-flow ordering | Yes | Terminal for the verdict; GARCH data does reach a later, non-verdict, informational/exit-planning consumer | Pass E E2.5, Pass F F1; `intelligent_orchestrator.py:4225` vs `:4235-4236` | No (`intelligent_orchestrator.py` tracked, though uncommitted/modified) |
| Regime-Adaptive Screener — 100% output loss | 0 of unknown intended output, 9/9 sampled runs | control-flow ordering | Technically invoked every run; functionally dead output | Terminal, no re-evaluation | Pass B §9; `avshunter_regime_screener.py:401-417` | Yes |
| Trap Engine VWAP signals dead input | 2 of 12 max weighted points, every package, every run | control-flow ordering | Yes (rest of scoring works) | Terminal | Pass C, Pass E E3; `avshunter_trap_engine.py:97,162-166,219-225` | No |
| Discovery/Vanguard `_x`/`_y` merge | 56/111 overlapping names unreconciled; ~53 never individually checked | merge-mechanics / ordering-adjacent | Yes | n/a — structural, recurs every run | Pass C; `:7061` | Yes |
| Catalyst Truth's two unreachable patch targets | Structurally dead at every one of 3 call times | control-flow ordering | Live code, guaranteed-null outcome | Mitigated by a separate passthrough in `eod_candidate_engine.py` | Pass F F3; `catalyst_truth_engine.py:699-712` | Yes |
| Morning gate priority-order defect (docstring vs actual `elif` chain) | All rows failing more than one CHECK simultaneously | control-flow / documentation ordering | Yes | n/a | Pass G G2; `morning_gate.py:1146-1217` | No |
| Handoff Conflict Guard fail-open-by-default | 125/1,400 (8.9%) downgraded in place | fail-open default (env var unset) | Yes | Pre-downgrade values not recoverable from disk | Pass F F2a; `intelligent_orchestrator.py:5334-5424` | No |
| `catastrophe_gate.py` — live no-op stub shadows the real 638-line module of the identical function name | n/a (the real module never runs at all) | name collision / dead module | The **stub** is live; the real module is not on any live path | The real module has a working standalone CLI | Pass H §5; `catastrophe_gate.py:456` vs `intelligent_orchestrator.py:2546-2556` | Real module: Yes (untracked). Stub: No |
| `avshunter_exit_engine.py` orphaned — CLAUDE.md's Sprint 1 "HIGHEST priority" module | n/a (never executes on the live path at all) | orphaned behind a dead caller | Not on live path | Recoverable only via its own `--test-mode` CLI, manually | Pass H §6; sole importer `morning_thesis_validator.py:2962` | No (tracked) |
| Phase 10 hard-block filter (`EOD_NO_OPTIONS_ROUTE`) | 15/1,400 (0.45% of 3,323) | threshold/status classification | Yes | Terminal | Pass F F5a | No |
| `move_theta_ratio` `UNAVAILABLE`→`0.0` | 836/1,135 (73.7%) | silent numeric coercion (NaN→default) | Yes | Recoverable only via co-located `move_theta_margin_label` | Pass F F4/F5a; `eod_candidate_engine.py:323-330`; `mcmillan_advisory_layer.py:258-263` | `eod_candidate_engine.py`: No. `mcmillan_advisory_layer.py`: Yes |
| `execution_mode` 100% empty at manifest | 1,135/1,135 | missing/null field, upstream source untraced | Yes | Not recoverable, no co-located label | Pass F F5a | No |
| Five-plus diverging verdict fields simultaneously present at the manifest with no field named authoritative | 1,135 rows; 4.8% agreement between the two most-relevant fields | genuine disagreement + control-flow ordering combined | Yes | n/a | Pass F F5a, Pass G G5 | No |
| SuperBrain bypass — 8 items of lost decision infrastructure (behavioural vetoes, convexity/campaign classification, DTE ladder, time-stop rules, 8 structured hard/soft gates incl. `ev_status==DATA_WEAK` escalation, conviction-based sizing, weighted risk-label system) | Applies to all 1,400 rows in principle | bypassed module (not deleted, not called) | Real module not on live path; substituted by a single untransformed field copy | Recoverable only by re-wiring (not proposed here) | Pass E E1; `scripts/avshunter_superbrain_layer.py` vs `intelligent_orchestrator.py:2402-2501` | Bypassed module: Yes. Substitute: No |
| PSE (position sizing) retired — `fd_size` hardcoded `0.0` everywhere downstream of the EIL span | All rows reading `fd_size` | hardcoded default | Yes | n/a | Pass E E2; `execution_intelligence_runner.py:220-222,2103` | Yes |
| `run.py`/`orchestrator/` — a second, entirely separate orchestration system, no shared invocation path with `intelligent_orchestrator.py` | Unknown — operational status undetermined | UNCERTAIN (config/entry-point ambiguity) | Cannot be determined from the repo alone | n/a | Pass H §4 | Yes (all 7 core files) |
| `premarket_intelligence_ULTIMATE.py` / `avshunter_monetisation_policy.py` — fully-implemented, only existence-checked, never invoked | n/a | orphan (config-referenced, never called) | Not on live path | n/a | Pass H §3 | UNVERIFIED (not stated explicitly by Pass H for either file) |

---

## I9 — Contradictions and gaps

### Unresolved contradictions between passes

1. **The fate of the 831 `BLOCK_NO_CONTRACT` rows — a genuine, unresolved disagreement.** Pass
   G's G3 section states these rows are "the genuine hard block class at Phase 10... producing
   `EOD_NO_OPTIONS_ROUTE` — one of the 15 hard-blocked statuses excluded from `manifest_mask`...
   confirmed terminal." But Pass F's own F5a establishes that the *entire* `hard_block_mask`
   population is exactly 15/1,400 rows (all `EOD_NO_OPTIONS_ROUTE`), while the dominant carry-forward
   status is `EOD_THESIS_READY_REPAIR_AT_OPEN` (1,019/1,400). Pass D's `BLOCK_NO_CONTRACT` population
   is 831/1,400 — more than 50× larger than the 15-row hard-block class Pass G describes it as
   feeding into. **Neither pass supplies an explanation reconciling 831 against 15; this synthesis
   does not resolve it.** [Pass F F5a vs Pass G G3]
2. **08-16 discovery/backfill denominator gap.** Pass B reports 1,649 discovery candidates for
   08-16, with "no External Intel Review Lane report... located for that run — flagged UNVERIFIED."
   Pass C separately states Backfill processed "40 of 1,660" packages for the same run, implying a
   denominator of 1,660 at that stage — an ~11-row gap neither pass reconciles. [Pass B §8.1 vs
   Pass C, Backfill section]
3. **CLAUDE.md's "warn=8" testing-protocol baseline vs both reference runs' `warn=12`.** Pass F
   states explicitly this is "UNVERIFIED whether 8 was ever the true baseline... or whether
   CLAUDE.md's number is simply stale" — an open question, not settled. [Pass F F2b]
4. **The "six hard gates" framing (carried in from a prior audit) vs Pass D's own direct count of
   seven `return 'STAND_DOWN'` statements** in `derive_verdict()`. Pass D offers a plausible but
   unconfirmed explanation (the two spread checks likely counted as one gate previously). [Pass D D5]
5. **Pass A's original ordering claims, corrected by later passes** — not contradictions in the
   "unresolved" sense (the Standing Contract's rule that the later pass wins applies cleanly here),
   but noted for completeness: item 9-vs-10 ordering (Regime Screener vs Discovery) corrected by
   Pass B; items 14–17 ordering (Horizon Router vs Vanguard/OI) corrected by Pass C; the
   "Handoff Conflict Guard: Critical" characterization refined (not contradicted) by Pass F, which
   found the abort branch dormant under the observed default configuration; the `superbrain_enriched.csv`
   reader/writer list, incomplete in Pass A, extended first by Pass E (GARCH also writes it) and
   again by Pass F (a third target, `execution_v3_5.csv`, also patched — Pass E only found two).

### Open questions the passes could not answer, with what would settle each

| Question | What would settle it |
|---|---|
| Which of the 21 `wyckoff_validation_*` fields (if any) are consumed outside the `.py` tree (Lab frontend, notebooks)? | Grep the Lab's frontend assets and any notebooks for these field names — Pass B searched `*.py` only |
| Exact per-filter breakdown of the 831 `BLOCK_NO_CONTRACT` rows across `select_best_contract()`'s six elimination points | Re-run `select_best_contract()` against the historical chain — explicitly out of every pass's read-only scope |
| Per-reason breakdown of the 39/40 Backfill OHLCV failures (`EMPTY`/`TOO_SHORT`/`NULLS_IN_LAST_10`/`STALE_LAST_BAR`) | Re-run with `--verbose` or capture subprocess stdout — not preserved as an artefact |
| The morning-mode counterfactual for the specific 184-row **08-18** `BLOCK_SPREAD` cohort | A recorded 08-18 morning-mode run (does not exist) or re-running the pipeline (out of scope). The proxy answer (≈4% favorable / ≈53% unchanged-illiquid, from a *different* run) is the closest available evidence, not a substitute |
| Whether Phase 11 (Execution Gate) has ever produced real output in any of the four available real morning-gate runs | No `execution_gated_*.csv`/`execution_actionable_*.csv`/`execution_gate_summary_*.json` was found in any of them; Pass G could not distinguish "never invoked" from "silently failed every time" without operator logs |
| Whether `build_candidate_manifest()`'s `WBS_MERGE_COLS` side-load recovers any of the "`wbs_grade` never merged into `eil_enriched.csv`" finding | Direct comparison of `wbs_grade` in `morning_candidates.csv` against `wall_break_scores_{run_id}.csv` for the 123 EXECUTE-tier tickers — flagged by both Pass E and Pass F, never cross-checked |
| Which verdict field a human trader (or any downstream script) actually treats as authoritative among the 5+ diverging fields at the manifest | Never traced by any pass — explicitly named "the natural next question" by both Pass F and Pass G |
| `resolve_lab_tradeability()`'s final `lab_verdict`/`tradeable` assignment past line 864 | Trace to completion and open an actual `final_opportunity_book_*.csv` to confirm predicted values — not done by Pass G |
| Whether `dropoff_audit.py` already contains an equivalent reconciliation to Pass F's manually-built 1,400→1,135 attribution | Read `dropoff_audit.py`'s own internals — explicitly deferred by Pass F |
| The three-way `scenario_builder.py` ambiguity (root vs `vanguard/layer2_statistical/` vs `vanguard/layer3_execution/`, all 9 basename hits) | Grep each importer's exact `from ... import` statement — not done by Pass H due to time |
| Whether `run.py`/`orchestrator/` is still in active operator use | Ask the operator directly; check for `config/settings.json`; check shell history for `python run.py` invocations |

### Everything the audit did not cover, stated plainly

- **The morning path's proxy-run limitation applies to every single morning-path number in this
  synthesis.** Pass G used run `20260809_195823` (plus, for frequency-only questions, the
  aggregate of four available real morning-gate executions, 3,663 rows total) because neither
  designated reference run has ever had `morning_gate.py` executed against it.
- **~90 files remain UNCERTAIN in Pass H's file census** (basename hit but call site not
  individually traced), concentrated in root-level utility/engine files with generic 1–9-hit
  basenames.
- **No stage received a complete column-by-column consumption census.** Discovery: ≈35 of 311
  fields individually checked (Pass B). Options Intelligence: targeted checks only, of 627 columns
  (Pass D D6). EIL: only the fields directly relevant to E1–E5's questions, of ~897–899 columns
  (Pass E). The full 627-column (and larger) census the Standing Contract's own scope named is not
  complete anywhere in this audit sequence.
- Universe Scanner subsystem internals (how `go_new`/`probe_new` are decided upstream of
  `scanner_manifest.json`) — a separate subsystem, out of scope for every pass.
- `vanguard.main.VanguardEngine`'s own Layer 1/2/3 scoring internals — only the I/O contract was
  traced (Pass C), not the internals.
- The five S1–S5 EIL microstructure strategies' own internal thresholds/synthesis logic — read
  only for field-reference purposes (Pass E).
- `wall_break_scorer.py`'s own internal EXECUTE-only filtering mechanism — the 123-row scope was
  confirmed empirically; the mechanism itself was not read (Pass E).
- The DEFANG/FATAL_BLOCK-reclassification pass (`execution_intelligence_runner.py:2962-3170`) —
  referenced in grep output, not traced (Pass E).
- `dropoff_audit.py` and `uat_audit_report.py`'s own internals beyond their call sites and output
  presence (Pass F).
- `handoff_contract_audit.py`'s full ~167-check field table beyond the specific fields needed for
  F2b (Pass F).
- Regression-detection's actual behaviour on either reference run — not executed (Pass B).
- `regime_threshold_injector.py` internals; `cfg.active_regime`'s exact resolved value for the
  reference run (assumed `"TRANSITIONAL"`, not independently confirmed) (Pass B).
- Full downstream-consumer tracing for the ~53 not-yet-checked `catalyst_*`/`scanner_*` fields at
  the discovery/vanguard merge boundary — flagged by Pass C as the top follow-up item, never
  completed by any later pass.
- Whether `find_macro_enrichment_delta()`'s auto-discovery ever finds/merges a delta file in a
  normal evening run without an explicit CLI flag (Pass C).
- Full value-level diff between the two independent McMillan passes (`eil_enriched.csv` vs
  `execution_v3_5.csv`) — column coverage compared, values not diffed row-by-row (Pass F).
- `final_run_manifest.json`'s actual computed values for either reference run — schema confirmed
  from source, values never read (Pass F).
- `pipeline_interpreter/`'s relationship to the live orchestrator path — never established in any
  pass; treated throughout as its own island by analogy to `intelligence-lab/`, never confirmed by
  tracing an entry point (Pass H).
- Whether any files remain reachable via fully dynamic invocation (a filename built via string
  formatting/concatenation at runtime, never appearing as a literal) — only checked for the four
  already-known EV3 exception files and the Discovery/`cfg.DISCOVERY_ULTIMATE` case; not searched
  whole-repo (Pass H).
- `pytest-of-ACKVerissimo/` could not be enumerated (OS permission denied) — assumed non-source,
  not independently verified (Pass H).
- External scheduling (Windows Task Scheduler, cron-like mechanisms, shell history) cannot be
  ruled out by any in-repo search; one `schtasks` snapshot found nothing but is a single
  point-in-time check of one machine only (Pass H).
- The full 627+-column census across every stage's output, as distinct from the targeted samples
  actually completed — stated here as the single largest structural gap in the audit sequence as
  a whole, cutting across Passes B, C, D, and E.

---

## Confidence rating for this synthesis

**Medium-high** for the core evening-path funnel (§I1 excluding the morning-path proxy rows), the
attrition ranking (§I2), and the ordering-defect register (§I6) — every figure in these sections
rests on a direct artefact read (CSV/JSON row counts, `value_counts`/crosstab against real files),
cross-checked against both reference runs where a pass did so, with exact reconciliation
arithmetic shown at each stage.

**Medium** for the verdict-divergence register (§I3) and field-drop register (§I4) — well-evidenced
on the specific fields each pass chose to trace, but built from explicitly non-exhaustive column
censuses at every stage (see "Everything the audit did not cover" above); a fuller census could
surface additional divergences or drops not captured here.

**Low-medium** for anything touching the morning path (§I1's morning-path rows, the 300/27/5
figure in §I3, CHECK-fail-rate quantifications in §I5, §I6 item 7) — every one of these is
proxy-derived from a run other than the designated references, explicitly flagged at each point of
use, per the Standing Contract's requirement.

**Low** for the file-census material touching operational status (§I8's `run.py`/`orchestrator/`
row, `premarket_intelligence_ULTIMATE.py`/`avshunter_monetisation_policy.py` rows) — these are
genuine unknowns requiring operator input, not gaps this synthesis or further reading could close.

**Named unknowns, restated for visibility:**
- The true fate of the 831 `BLOCK_NO_CONTRACT` rows at Phase 10 (Pass F vs Pass G, unresolved).
- The true historical origin of CLAUDE.md's "warn=8" baseline.
- The 08-16 discovery/backfill ~11-row denominator gap.
- Which of five-plus verdict fields (six-plus once `morning_gate.py`'s own vocabulary is included)
  a human trader is actually meant to treat as authoritative.
- The 184-row 08-18 `BLOCK_SPREAD` cohort's actual morning-path fate (proxy-answered only).
- `run.py`'s current operational status.
- Whether Phase 11 (Execution Gate) has ever produced real output in any observed run.
