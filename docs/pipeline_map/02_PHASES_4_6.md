# Pass C — External Intel / Macro Enrichment, Package Build, Vanguard

Read-only audit. No files edited, no pipeline phase executed. All citations against
`intelligent_orchestrator.py` (working tree, uncommitted relative to git HEAD — same
caveat as Pass A/B: line numbers are tied to the *current* on-disk content) unless
another file is named. Builds on `data/scratch/pipeline_map/00_SPINE.md` (Pass A) and
`data/scratch/pipeline_map/01_PHASES_0_3.md` (Pass B) — neither re-derived except where
this pass's direct source reads required a correction (§0 below).

**Reference runs:** `20260818_041214` (primary), `20260816_075339` (secondary). Every row
count, field name, and JSON value below is read directly from an artefact — package JSON
files, `vanguard_run_summary.json`, `vanguard_signals.csv`, `vanguard_rejects.csv`,
`packages/index.json`, `options_intelligence_{run_id}.csv` — with the reading method
stated per number. **Denominator for every percentage: 3,323**, per Pass B §0's
established convention (the augmented universe Discovery actually consumed), stated
explicitly wherever used.

---

## §0. Correction to Pass A — the true execution order of items 14–17

Pass A's dispatch table (`00_SPINE.md` §2.2) lists, in this row order:

```
14  PHASE 1B (Macro Horizon Router)            run_horizon_router(...)          :3776
15  PATCH-HORIZON Phase 1B-B                   patch_horizon_fields_into_csv    :3786-3790
16  Vanguard pipeline                          run_vanguard_pipeline(...)       :3754-3756
17  PHASE 8a (Options Intelligence)            run_options_intelligence(...)    :3765-3769
```

Direct read of `intelligent_orchestrator.py:3680-3860` this pass (no branching between
these calls — a straight-line function body, execution order matches line order exactly,
same verification method Pass B used to correct the Regime-Screener-vs-Discovery
ordering) shows the row order above is **backwards for items 14–17**. The actual order,
confirmed by line position and by the code's own inline comments, is:

```
Vanguard pipeline (Build Packages → Inject Macro → Backfill → TLE → Run VANGUARD)  :3754-3756
run_catalyst_truth_layer(stage="pre_options")                                      :3765
run_position_lock_check                                                            :3767
run_options_intelligence  ("MUST precede Phase 8.5" — code's own comment)          :3768
run_ev3_governed_shadow                                                            :3769
run_horizon_router  (Phase 1B — the ACTUAL call; a dead comment block reading
  "Phase 1B: Macro Horizon Router — moved to after Phase 8a (DEF-002 FIX)" sits at
  the stale former call site, :3707-3722, and is never executed)                   :3776
patch_horizon_fields_into_csv (Phase 1B-B)                                         :3786-3790
run_catalyst_truth_layer(stage="post_options")                                     :3791
Phase 8.5 — Actuarial Enrichment Pass                                              :3805-3857
Phase 7.5 — Phantom Scoring Engine                                                 :3861-3935+
```

This is corroborated independently by `run_horizon_router()`'s own body
(`intelligent_orchestrator.py:1252-1268`): it reads
`options/vanguard_signals_enriched_{run_id}.csv` first, falling back to
`options/options_intelligence_{run_id}.csv`, falling back to the discovery CSV only as
"last resort" with an explicit warning ("no DTE, signals will block") — i.e. the
function is *written* assuming Options Intelligence has already run, which only makes
sense if it is in fact called after Options Intelligence. Pass A's own item ordering
(14 before 16) would have had the Horizon Router run before Vanguard/OI ever produced
those files, which contradicts the function's own fallback-chain design. **Net
correction: Vanguard pipeline and Options Intelligence run first; the Horizon Router and
its CSV patch run after, not before.** Pass A's items 14–17 should be read in the order
16, [pre_options catalyst truth, position lock], 17, [ev3 shadow], 14, 15, [post_options
catalyst truth]. Everything else in Pass A's table (items 1–13, 18+) is unaffected by
this correction and is not re-derived here.

---

## Stage: Post-Discovery Enrichment (recap — full detail is Pass B §10)

Not re-derived. Pass B established: External Intel Review Lane appends 4 forced-review
rows (1,649→1,653) from `dropbox/inputs/catalyst_calendar_latest.csv`; Macro Enrichment
to Discovery stamps `macro_bias`/`macro_bias_source` only (`status: "BIAS_ONLY"` per
`qa/macro_enrichment_discovery_20260818_041214.json`); both patch the **pinned run-dir
copy** of the discovery CSV, which is what everything downstream in this pass reads.

**New this pass — downstream-reader check.** `macro_bias`/`macro_bias_source` (the two
fields this stage adds) are **not** among the 111 discovery↔vanguard overlapping column
names found in §"Field-drop at the OI boundary" below, and a targeted grep of
`scripts/avshunter_options_intelligence.py` for `macro_bias` returns zero matches. The
field is carried forward unchanged into every package (`pkg["discovery"]` is a verbatim
copy of the discovery row — see Package Build below) and into the Vanguard payload
builder's `disc` dict, but `build_orchestrator_like_payload()`
(`scripts/run_vanguard_from_packages.py:659-890`) never reads `macro_bias` by name
either. **`macro_bias`/`macro_bias_source` are write-only past this point in every
artefact checked this pass** — the same "written, never read" pattern Pass B found for
24+ discovery fields, now confirmed to extend at least this far downstream. Not
re-verified beyond Options Intelligence's own `.py` source (no notebook/frontend check,
consistent with Pass B's stated scope limit).

---

## Stage: Package Build (`scripts/build_packages_from_discovery.py`, "Phase 5")

**Module:** `scripts/build_packages_from_discovery.py` (617 lines)
**Invoked by:** `run_vanguard_pipeline():1981`, subprocess via `_run(..., critical=True)`
**Critical:** True — `intelligent_orchestrator.py:1984-1991`; non-zero exit aborts the
entire Vanguard pipeline (`return False`), which is itself critical at the
`evening_workflow()` level (Pass A item 16). This is a hard-abort point not previously
enumerated by number in Pass A's ~5-7-condition count — Pass A's count already included
"Vanguard pipeline failed" as one bucket; Build Packages failing is one of the ways that
bucket fires, not a new independent abort point.
**Conditional on:** Unconditional given Vanguard pipeline was reached; discovery CSV
auto-located via `auto_discover_discovery_csv()` (`:157-173`), which globs the **run
directory itself** (`run_dir.rglob(...)`, explicitly excluding anything under a
`packages/` subfolder) — not the flat `OUTPUT_DIR` copy. Since `pin_run_directory()`
(called immediately before this, `run_vanguard_pipeline():1976`) has already copied the
flat discovery CSV into `run_dir/discovery/`, this auto-discovery reads the **pinned**
copy — which at this exact moment in the run has **not yet** been patched by
`catalyst_truth_engine` (those patches happen at `pre_options`/`post_options`/`post_eil`,
all of which run *after* the Vanguard pipeline per §0's correction). So Package Build
sees the 285-field discovery row (External Intel + macro-bias enrichment only, no
`catalyst_*` columns yet) — confirmed by field count arithmetic, not independently
re-verified via a second field census this pass.
**Number claimed:** module docstring says nothing about a phase number; code comment in
the orchestrator labels the tuple `"Build Packages from Discovery"` with no number
(`:1981`); CLAUDE.md's "Phase 5 → Package Build / Backfill" is the nearest match, already
flagged by Pass A §5 as not a sibling of Vanguard in the code (it is a subprocess *inside*
`run_vanguard_pipeline()`).
**Output exists and is non-empty in ref runs:** Yes — 1,651 package files + `index.json`,
confirmed by direct directory listing and JSON read, both reference runs.

**Inputs**
| Artefact | Path | Rows (ref run, 08-18) | Key fields consumed |
|---|---|---|---|
| Pinned discovery CSV | `run_dir/discovery/discovery_candidates_ultimate_{run_id}.csv` | 1,653 | Every discovery column — `pkg["discovery"]` is a **verbatim copy of the full row dict** (`build_package():412`, `discovery_row: Dict[str, Any]` parameter passed through unfiltered), not a curated subset |
| Macro snapshot | `run_dir/macro_snapshot.json` (first candidate in `locate_macro_snapshot()`'s priority list, `:251-259`) | 1 file | Full raw dict, `macro_state`/`as_of_utc`/`contract_version` per `normalise_macro_snapshot()` (`:179-219`) |

**Outputs**
| Artefact | Path | Rows (ref run, 08-18) | Key fields produced |
|---|---|---|---|
| `<TICKER>.package.json` | `run_dir/packages/` | 1,651 files | `package_version`, `ticker`, `as_of_utc`, `run_id`, `macro.*`, `regime_snapshot` (= raw macro_snapshot at this stage, superseded later), `discovery` (verbatim), `ohlcv_daily=None`, `ohlcv=None`, `options_contract.*` (17 fields, all from discovery's option-selection columns), `timeseries.*` (all `None` placeholders), `data_contract.*` (all-False placeholders), `actuarial` (= `_ACTUARIAL_DEFERRED_BLOCK`, 8-field placeholder, `:107-117`) |
| `packages/index.json` | `run_dir/packages/index.json` | 1,653 entries in `packages[]` (1,651 `"status":"BUILT"` + 2 `"status":"BLOCKED"`) | `packages_built: 1651`, `packages_blocked: 2`, per-ticker `{ticker, package_path, status, reason}` |

**Attrition**
Rows in: **1,653 → Rows out: 1,651** (loss: 2, **0.06% of 3,323**)

| Cause | Count | Fail-open or fail-closed | path:line |
|---|---|---|---|
| Ticker contains a `.` (`ensure_us_ticker_sane()`) | 2 (**BF.B, BRK.B**, both runs — confirmed by direct read of both reference runs' discovery CSVs) | Fail-closed for that ticker only (rest of the batch continues) | `:333-336` (check), `:563-573` (call site + index-entry write) |
| Duplicate ticker in discovery CSV | 0 (this run; mechanism exists, `dedupe_discovery_rows_by_ticker()`, `:317-330`) | Fail-closed (later occurrence dropped, first kept) | `:317-330`, folded into `blocked` count at `:555` |
| Empty ticker string | 0 (this run) | Fail-closed | `:558-561` |

**Reconciliation:** 1,653 − 2 = 1,651. Exact, no shortfall. Confirmed stable across both
reference runs: 08-16 discovery CSV had exactly one dotted ticker (`BF.B`; `BRK.B` was
not itself a discovery candidate that day), and `packages_blocked: 1` in that run's
`index.json` — the mechanism, not just the count, reproduces identically.

**Field lineage**
- Created: `_ACTUARIAL_DEFERRED_BLOCK` (`:107-117`) — every package gets an identical
  8-key placeholder (`available: False, deferred: True, win_rate_10d: 0.0, ...`), stamped
  verbatim, not computed per-ticker at this stage. Module docstring (`:10-19`) is explicit
  about why: the six actuarial state-lookup columns (`vol_regime`, `trend_direction`,
  `structure_quality`, `adx_bucket`, `wyckoff_phase`, `macro_regime`) are Vanguard
  Layer-2 outputs that don't exist until *after* Vanguard runs — Phase 8.5
  (`actuarial_enrichment_pass.py`) patches every package afterward (see Handoff
  confirmation below).
- Created: `options_contract.ev_final` / `ev_status` (`:455-456`) — confirmed by an
  in-code comment (2026-08-19, EV audit Stage 0, already flagged in CLAUDE.md's Known
  Risk Patterns) to be **structurally always `None`** at this stage: no upstream module
  writes either field onto the discovery CSV before Phase 5, and EV Engine v2 (the only
  live producer of a field literally named `ev_status`) does not run until Phase 9. Not
  re-verified independently this pass (the comment is itself dated one day before this
  pass and cites its own prior full census of 1,651 packages) — carried forward as
  established, not re-derived.
- Consumed then dropped (partial): `regime_snapshot` is set here to the **full raw
  macro_snapshot dict** (`:406`, `pkg["regime_snapshot"] = macro_snapshot`) — this value
  is **unconditionally overwritten** two subprocess steps later by Inject Macro into
  Packages with a clean 6-field flat dict (see next stage's Field lineage) before
  Vanguard ever reads it. The Package-Build-stage value of `regime_snapshot` is never
  read by anything; only Inject Macro's replacement value survives to Vanguard's
  fail-closed gate.

**Failure behaviour**
Any per-ticker exception during `build_package()`/`write_json()` is **not individually
caught** — the `for row in discovery_rows:` loop (`:557-591`) has no try/except around
`build_package()`/`write_json()` themselves (only `ensure_us_ticker_sane()` is wrapped).
An exception there would propagate and crash the whole subprocess (non-zero exit →
critical abort of Vanguard pipeline). Not observed in either reference run (both
completed with clean per-ticker BUILT/BLOCKED counts) — flagged as a theoretical
fail-closed path, not empirically exercised this pass.

**Dead code on this path:** none identified in this module itself.

**Open questions**
- `ensure_us_ticker_sane()`'s check (any `.` in ticker) is broader than the "contaminated
  foreign-exchange suffix" framing its own docstring implies (`:333-336`, "Block tickers
  that look contaminated (.V, .L, etc.)") — it also blocks legitimate US dual-class
  tickers (`BF.B`, `BRK.B`). Reporting the rate and mechanism only, per the Standing
  Contract's "do not propose changes" instruction; not characterising it as miscalibrated.

---

## Stage: Inject Macro into Packages (`scripts/inject_macro_into_packages.py`)

**Module:** `scripts/inject_macro_into_packages.py` (260 lines)
**Invoked by:** `run_vanguard_pipeline():1982`, subprocess via `_run(..., critical=True)`
**Critical:** True (same abort chain as Package Build above)
**Conditional on:** `pkg_dir.exists()` and `macro_path.exists()` — both fail-closed
(`return 2`) if missing (`:158-163`); per-package JSON load failures are individually
skipped, not fatal to the run (`:199-204`)
**Number claimed:** unnumbered at the orchestrator call site (`:1982`); CLAUDE.md's
"Phase 5" bundles this with Package Build, which the code also does structurally (both
are sub-steps of the same `for label, script, extra_args in [...]` loop,
`:1980-1993`) but they are two separate subprocess invocations, not one script.

**Inputs**
| Artefact | Path | Rows (ref run) | Key fields consumed |
|---|---|---|---|
| Packages built in the previous step | `run_dir/packages/*.package.json` | 1,651 | Whole package dict (read, mutated, atomically rewritten) |
| Macro JSON | `--macro-path` = `macro_path` (same object handed through the whole evening run — post-normalisation) | 1 file | Same recursive `_flatten_macro()` walk as `normalise_macro_contract.py` uses (`:77-104`), for `regime_state`, `dir_bias`, `volatility_mode`/`vol_mode`, `regime_drift_status`, `macro_conviction` |

**Outputs**
| Artefact | Path | Rows (ref run) | Key fields produced |
|---|---|---|---|
| Same package files, rewritten atomically (`save_json()`: write to `.tmp`, then `Path.replace()`, `:65-70` — a real crash-safety guarantee, not just a comment) | `run_dir/packages/*.package.json` | 1,651 updated (0 skipped, this run — no `WARN: skipping` lines expected given clean package JSON) | `pkg["macro"]` (fully replaced dict: `source_path`, `enrichment_delta_path`, `ingested_utc`, `payload`, `quant_packet`), `pkg["macro_quant_packet"]`, `pkg["regime_snapshot"]` (fully replaced with the clean 6+2-field flat dict from `build_regime_snapshot()`), `pkg["truth_packet"]` (rebuilt) |

**Attrition:** Not a row-filtering stage; per-package JSON-load failures would be
"skipped" (counted, logged) rather than dropped from the package count, but 0 occurred
this run.

**Field lineage — the "overwrite vs. augment" pattern recurs here, in a different and
more benign form than Pass B's `regime_distribution` finding**

`pkg["macro"]` and `pkg["regime_snapshot"]` are **unconditionally replaced** every run
(`pkg["macro"] = {...}` / `pkg["regime_snapshot"] = build_regime_snapshot(...)`,
`:209-218` — direct assignment, no existence/validity guard on the prior value). This is
structurally the same *shape* of finding as Pass B's `normalise_macro_regime_fields()`
overwrite — but here the value being replaced is Package Build's own **placeholder**
(the raw, unprocessed `macro_snapshot` dict written one subprocess step earlier, never
read by anything in between). This two-stage build→inject contract is the *intended*
handoff, not a case of one producer's independent computation being silently discarded
by another — flagged for completeness per the brief's instruction to check whether the
pattern recurs, not flagged as a defect.

**Freshness handling — a genuine trap for any future reader of `regime_snapshot`**

`build_regime_snapshot()`'s docstring (`:107-116`) states explicitly: *"`as_of_utc` is
always stamped with the injection time... NOT the timestamp in the macro JSON... the
Vanguard staleness gate therefore always sees a fresh timestamp."* Confirmed by direct
read: `"as_of_utc": injected_at` (`:119`) is the wall-clock time this script ran, while
the macro JSON's own real timestamp is preserved separately as `source_as_of_utc`
(`:120`). **Any code that reads `pkg["regime_snapshot"]["as_of_utc"]` to judge macro
data freshness will always see "fresh," regardless of how stale the underlying macro
JSON actually is** — true staleness is only visible via `macro_freshness_status`/
`macro_data_quality` (computed by `build_macro_quant_packet()`, itself gated by
`MACRO_STALE_HOURS`=20h per Pass B §2, fail-open/warn-only). This is a documented,
deliberate design choice (the module comment calls it "STALENESS FIX"), not a bug — but
it means the field named `as_of_utc` on this object does not mean what its name implies,
and nothing downstream is fail-closed on macro staleness at this stage. A stale macro
source degrades quietly (via `macro_data_quality`, read by nothing in this pass's scope
so far) rather than blocking anything.

**Failure behaviour**
Whole-run fail-closed only on missing packages dir or missing/unparseable macro JSON
(`return 2` → subprocess non-zero → critical abort of Vanguard pipeline). Per-package
JSON-load failure: skipped, logged, run continues (`:199-204`) — fail-open at the
per-ticker level, fail-closed at the run level for the two structural preconditions.

**Dead code on this path:** none. The optional `--macro-enrichment-delta` CLI argument
is **never passed** by the orchestrator's call site (`:1982`, only `--run-id` and
`--macro-path`) — its own docstring explains why: *"Production narrative macro
enrichment is stamped onto discovery, not auto-injected into packages before Vanguard"*
(`:144-147`). `find_macro_enrichment_delta(macro_path, None)` may still auto-discover a
delta file by convention-based path lookup (not traced this pass — its internals live in
`contracts/macro_enrichment_delta.py`, out of scope) — flagged as an open question, not
resolved.

**Open questions**
- Whether `find_macro_enrichment_delta()`'s auto-discovery (when no explicit path is
  passed) ever finds and merges a delta at this stage in a normal evening run — not
  traced; would require reading `contracts/macro_enrichment_delta.py`.

---

## Stage: Backfill Timeseries into Packages (`scripts/backfill_timeseries_into_packages.py`)

**Module:** `scripts/backfill_timeseries_into_packages.py` (753 lines)
**Invoked by:** `run_vanguard_pipeline():2002-2006`, **direct `subprocess.run()`**, not
via the `_run()` helper used everywhere else in this function
**Critical:** **Explicitly downgraded** — return code 0 → success; return code 2 →
warning only, pipeline continues ("Backfill had partial failures... Excluding them");
any other code → `return False`, aborts the Vanguard pipeline (`:2011-2024`). This is a
three-way outcome, not the binary critical/non-critical split used elsewhere.
**Conditional on:** `POLYGON_API_KEY`/`MARKETDATA_API_KEY` present in environment or
`.env` (`:660-693`); `--allow-polygon --allow-marketdata --intraday-provider auto
--data-mode EOD` are the exact flags the orchestrator passes (`:1997-1999`)
**Number claimed:** unnumbered anywhere; not named as a distinct phase in CLAUDE.md at
all (folded into its "Phase 5 → Package Build / Backfill" line).

**Inputs**
| Artefact | Path | Rows (ref run) | Key fields consumed |
|---|---|---|---|
| `packages/index.json` | `run_dir/packages/index.json` | 1,653 entries, filtered to `status=="BUILT"` → 1,651 processed (the 2 BLOCKED entries are silently `continue`d, `:708-709`, never counted in `ok_count`/`fail_count`/`stats`) | Polygon/MarketData daily+intraday OHLCV per ticker |

**Outputs**
| Artefact | Path | Rows (ref run) | Key fields produced |
|---|---|---|---|
| Same 1,651 package files, patched in place | `run_dir/packages/*.package.json` | 1,612 with populated `ohlcv_daily`; **39 with `ohlcv_daily: null`** (confirmed by direct read of every package file: `has_ohlcv_daily: 1612`, `None: 39`, `empty-list: 0`) | `pkg["ohlcv_daily"]` (canonical, read first by Vanguard), `pkg["timeseries"]["ohlcv_daily"]` (audit copy), `intraday_partial` flag when LATEST mode appends a partial session bar (not applicable this run — EOD mode) |

**Attrition (within this sub-stage)**
Rows in: 1,651 → **39 packages end this stage with no OHLCV** (2.36% of 3,323; 2.42% of
the 1,612 that ultimately pass Vanguard). Stable across reference runs: 08-16 shows 40 of
1,660 (2.41%) — same order of magnitude, same failure signature (100% attributed to
`DATA_FAILURE_NO_OHLCV` at the next stage).

| Cause | Count | Fail-open or fail-closed | path:line |
|---|---|---|---|
| `validate_series()` rejects the fetched bar series — `EMPTY`, `TOO_SHORT (<120 bars)`, `NULLS_IN_LAST_10`, or `STALE_LAST_BAR (>5 days old)` | 39 (exact reason-code breakdown not captured — `backfill_timeseries_into_packages.py`'s own stdout, which prints a per-reason count via `stats[reason]`, is piped into the orchestrator's log and not persisted as a separate artefact; not re-derivable from package JSON alone since a failed package simply has `ohlcv_daily: None` regardless of which of the four sub-reasons fired) | Fail-open at the package level (package survives, just without OHLCV; Vanguard rejects it downstream, does not crash the run) | `validate_series():353-386`, called from `backfill_package()` |

**Reconciliation:** 1,651 processed − 39 no-OHLCV = 1,612 with usable OHLCV — this is
the exact number Vanguard later reports as `passed`. No shortfall.

**Field lineage**
- Preserved by design: "ACTUARIAL CONTRACT" comment (`:416-418`) — the actuarial
  placeholder block written by Package Build is explicitly extracted before this script
  writes the package and re-injected after, so Backfill never clobbers it. Confirmed
  present in every sampled package this pass (all still carry the 8-key
  `_ACTUARIAL_DEFERRED_BLOCK` shape at this point in the pipeline).
- Created: `data_contract.actuarial_data_quality` stamped `"OHLCV_OK"`/`"OHLCV_FAIL"` per
  package (`:419` comment; exact write site not required for this pass's purposes).

**Failure behaviour**
`main()` returns `0 if fail_count == 0 else 2` (`:749`) — **exit code 2 fires on *any*
non-zero `fail_count`, regardless of which of the four `validate_series()` reasons
caused it**, not only `TOO_SHORT`. The orchestrator's own log message at the call site
(`intelligent_orchestrator.py:2014-2016`) says *"partial failures (TOO_SHORT tickers)"* —
this is an inaccurate label carried in a log string only; the actual gate
(`_backfill_proc.returncode == 2`) is reason-agnostic and behaves correctly (warn +
continue) regardless of which reason produced the failures. Flagged as a cosmetic
log-message imprecision, not a functional defect — the pipeline's actual behaviour
(warn, exclude, continue) is correct for all four reasons, just mislabelled in the one
place a human would read it.

**Dead code on this path:** none identified.

**Open questions**
- Per-reason breakdown of the 39 (08-18) / 40 (08-16) failures among `EMPTY`/`TOO_SHORT`/
  `NULLS_IN_LAST_10`/`STALE_LAST_BAR` — not recoverable from artefacts alone; would
  require re-running with `--verbose` or capturing the orchestrator's own child-process
  stdout (neither done this pass, per the "do not run the pipeline" rule).

---

## Stage: Trap-to-Launch Engine — "Phase 5.5" (`avshunter_trap_engine.py`)

**Module:** `avshunter_trap_engine.py` (423 lines), dynamic-imported in-process (not a
subprocess)
**Invoked by:** `run_vanguard_pipeline():2028-2044`, between Backfill and the
`packages/index.json` defence-in-depth check, **before** the "Run VANGUARD" subprocess
**Critical:** False — wrapped in try/except; `run_trap_layer()` itself also returns
`True` on any per-package exception (only returns `False` if `packages_dir` itself is
missing, `:327-329`)
**Conditional on:** `(cfg.BASE_DIR / "avshunter_trap_engine.py").exists()` — confirmed
present (this is the file `git status` at session start showed as `M`, i.e. modified
in the working tree, consistent with Pass B's finding that it is live and tracked, not
new)
**Number claimed:** code comment "Phase 5.5" (`:2026`, `avshunter_trap_engine.py:4`) /
CLAUDE.md's Sprint 3 (**"Architectural Decision Required Before Building... Do not begin
coding until you have confirmed..."**) frames this entire module as **not yet built**.
This is directly contradicted by the live call site, git tracking, and (new this pass)
by a fully-implemented, exactly-matching downstream consumer — see below.
**Output exists and is non-empty in ref runs:** Yes — every one of the 1,651 packages in
the reference run carries a populated `pkg["tle"]` block (confirmed by direct read of
all 1,651 files: `has tle block: 1651/1651`, zero errors).

**Inputs**
| Artefact | Path | Rows (ref run) | Key fields consumed |
|---|---|---|---|
| Packages after Backfill | `run_dir/packages/*.package.json` | 1,651 | `discovery.*` (direction, phase, wyckoff_mode, wyckoff_phase_granular, dominant_event, control_state/precor_control, vwap_bias, dominant_trend, gamma_risk_flag, event_evidence_bucket, repricing_direction/state, crabel_state/crabel_bucket [documented in-code as ~25% populated, guarded], days_in_range, stock_price/entry_price, structural_stop/stop_loss, structural_target, VWAP); `triggers.*` (`primary`, `codes`) — **see defect below**; `macro.payload.gex.*` (score, regime, stress) |

**Outputs**
| Artefact | Path | Rows (ref run) | Key fields produced |
|---|---|---|---|
| Same package files, `pkg["tle"]` sub-dict added | `run_dir/packages/*.package.json` | 1,651 | `tle_trap_direction`, `tle_who_is_trapped`, `tle_forced_move_level`, `tle_entry_trigger`, `tle_kill_switch`, `tle_bullish_score`, `tle_bearish_score`, `tle_verdict`, `tle_crowd_arrival_target`, plus two debug-only fields `_tle_bull_signals`/`_tle_bear_signals` (list of fired signal names) |

**Attrition:** Not a row-filtering stage. **Verdict distribution, reference run (08-18),
counted directly from all 1,651 package files:**

| `tle_verdict` | Count | % of 1,651 processed | % of 3,323 |
|---|---|---|---|
| `CONFIRMATION_ENTRY` | 925 | 56.0% | 27.8% |
| `EARLY_PROBE` | 542 | 32.8% | 16.3% |
| `NO_TRADE` | 184 | 11.1% | 5.5% |
| `CHASE` | 0 | 0.0% | 0.0% |

**Field lineage**
- Created: `active_score` (internal, not written to output) — **direction-aligned, not a
  simple max of the two scores**: if `discovery.direction` resolves to `CALL`, only
  `tle_bullish_score` gates the verdict; if `PUT`, only `tle_bearish_score` gates it;
  only when direction is unset does it fall back to `max(bull_score, bear_score)`
  (`:268-274`). CLAUDE.md's spec does not state this nuance — it just says each score is
  "sum of weights" without specifying which one a given signal's verdict is judged
  against.
- Note: CLAUDE.md's field contract states `tle_bullish_score`/`tle_bearish_score` range
  "0–13"; the six weights actually coded per direction (`3+2+2+2+2+1`) sum to a maximum
  of **12**, not 13. Harmless (13 is simply unreachable, not a bug — the verdict
  thresholds 4/7/11 all sit comfortably inside the achievable 0–12 range), noted for
  completeness.

**A confirmed control-flow-ordering defect — two of twelve weighted signal channels are
structurally dead in every run**

`_compute_tle_inner()` reads `trig = pkg.get("triggers", {})` (`:97`) and uses
`trig.get("primary")`/`trig.get("codes")` for two signals: bullish T2 (`VWAP_RECLAIM`
trigger, weight 2, `:162-166`) and bearish T2 (`VWAP_LOSS` trigger, weight 2,
`:217-225`). **`pkg["triggers"]` does not exist at the moment Trap Engine runs.** The
only writer of that key anywhere in the repo is `trigger_layer.py:779`
(`pkg["triggers"] = build_trigger_block(src)`, inside `patch_run_packages()`), whose sole
call site is `intelligent_orchestrator.py:3956` — **Phase 8.6**, which per §0's
correction runs after Vanguard, Options Intelligence, the Horizon Router, and Actuarial
Enrichment, i.e., hundreds of lines and several phases later in the same
`evening_workflow()` than Trap Engine's call at `:2028` (itself nested inside the
Vanguard-pipeline call at `:3754`, *before* "Run VANGUARD" even executes). Trap Engine
never re-runs later in the same evening run to pick up the now-populated triggers block.

Confirmed empirically that the packages on disk *do* carry a populated `triggers` key
(sample: ticker A → `{"codes": "VOL_COMPRESSION", "primary": "VOL_COMPRESSION", ...}`)
— but this is the **post-run, end-state** file content, after Phase 8.6 has already run
and patched it in. It says nothing about what `pkg.get("triggers", {})` returned at the
moment Trap Engine actually executed. This is exactly the trap the Standing Contract
warns about ("filename is not authority... prove execution by tracing call sites") —
applied here to an *input*, not an output.

- **Mechanism class:** control-flow ordering.
- **Counterfactual:** these two signal channels would fire correctly only if Trap Engine
  ran after `trigger_layer.patch_run_packages()`, or if it read triggers from a source
  already available at Phase 5.5 (e.g. recomputing from raw discovery fields, the way its
  own T3 bullish signal already has a non-trigger fallback via `crabel_bucket`/
  `crabel_state`).
- **Recoverability:** Terminal for the run — Trap Engine is not re-invoked later.
- **Blast radius:** 2 of the 12 maximum weighted points (bullish T2, bearish T2; weight 2
  each) are unconditionally unreachable in *every* package, *every* run — this is a
  structural property of the call-site ordering, not data-dependent, so it is stable by
  construction across both reference runs (not merely "observed to be" stable). Whether
  any package's verdict tier boundary (4/7/11) would have flipped had these 2 points been
  live was not computed — that would require re-running the scoring logic with corrected
  inputs, which is out of this pass's read-only scope.
- Note (partial mitigation): bearish T2's OR-clause has a third branch —
  `(vwap_reclaim_trigger_hit) and vwap_bias == "BELOW"` — but that branch also depends on
  the same always-empty `trigger_primary`/`trigger_codes`, so it is equally dead; there is
  **no working fallback** for either T2 signal, unlike bullish T3 (`VOL_COMPRESSION`),
  which survives via its `crabel_bucket`/`crabel_state` OR-branches.

**Sprint 3's downstream integration is fully live and firing — a second correction to
the framing in CLAUDE.md**

`scripts/avshunter_options_intelligence.py:408-432` (`load_package_tle_contexts()`)
reads `pkg.get("tle")` from every package JSON in `run_dir/packages/` and returns a
`{ticker: tle_dict}` map, keyed only on packages where `tle_block.get("tle_verdict")` is
truthy. This is passed into `process_ticker(..., tle_context=...)` (`:7138`) and applied
inside `build_convexity_strike_map()` (`:6759-6778`) **exactly per CLAUDE.md's Sprint 3
integration-point spec**: `CHASE` → `csm_verdict` forced to `"TOO_LATE"` regardless of
prior CSM geometry (`:6762-6768`); `EARLY_PROBE` → `csm_premium_efficiency *= 0.80`
(`:6769-6775`, the literal 20% reduction CLAUDE.md specifies); `CONFIRMATION_ENTRY`/
`NO_TRADE` → no modifier (`:6776-6777`, matching comments). **Confirmed firing in the
reference run**: 148 of the 1,400 rows in `options_intelligence_20260818_041214.csv`
carry a `[TLE:...]` trace inside their `csm_verdict_reason` text. The raw `tle_*` fields
themselves are **not** propagated as their own columns into the OI output CSV (confirmed
— zero `tle_`-prefixed columns among that file's 627 columns); only their *effect* on the
`csm_*` fields survives past Options Intelligence's in-memory processing — a "consumed
then dropped" field-lineage pattern, not a bug (the modifier is applied and the outcome
is recorded via `csm_verdict`/`csm_verdict_reason`; the raw trap score is discarded
after use).

**Failure behaviour**
Per-package: any exception inside `_compute_tle_inner()` is caught and replaced with
`_neutral_tle()` (`tle_verdict="NO_TRADE"`, both scores 0) — fail-open, never propagates
(`:69-73`). Whole-stage: only a missing `packages_dir` returns `False`; every other
failure mode (empty package list, per-package errors) returns `True` (`:320-366`).

**Dead code on this path:** none — every branch of the scoring logic is reachable except
the two trigger-dependent OR-clauses documented above, which are reachable in principle
but structurally never true given current call-site ordering (not "dead code" in the
unreachable-statement sense; "dead input," a distinct but related failure class).

**Open questions**
- Exact effect of the two dead trigger-signals on the verdict distribution had they been
  live — not computed (would require re-scoring, out of scope).
- Whether the tier-demotion side-effect inside `build_orchestrator_like_payload()`
  (BEARISH trend + non-buyer control demotes Tier 1→2 unless ACCUMULATION×RISK_OFF,
  `run_vanguard_from_packages.py:721-751`) is visible to `signal_to_row()`'s own
  `disc` argument: `main()`'s loop builds `_disc_row = dict(pkg.get("discovery") or {})`
  fresh from the **original, undemoted** package discovery block (`:1480`), separately
  from the demoted copy used only inside `build_orchestrator_like_payload()`'s local
  `disc` variable. Whether this produces a visible inconsistency between the tier Vanguard
  actually scored against and the tier value later fields (e.g. `debug_signature`) are
  computed from was not traced fully — flagged, not resolved.

---

## Stage: Run VANGUARD (`scripts/run_vanguard_from_packages.py` + `vanguard/` engine)

**Module:** `scripts/run_vanguard_from_packages.py` (1,590 lines), subprocess
**Invoked by:** `run_vanguard_pipeline():2055`, subprocess via `_run(..., critical=True)`,
gated by a defence-in-depth check that `packages/index.json` exists (`:2047-2053`)
**Critical:** True — non-zero exit aborts the Vanguard pipeline
**Conditional on:** Unconditional given the index exists
**Number claimed:** CLAUDE.md's "Phase 6 → Vanguard" — code comment block above the
function labels this "PHASES 5–8: VANGUARD PIPELINE" (`:1948`, `:1970-1971`), i.e. the
code's own framing treats Build/Inject/Backfill/TLE/Run-VANGUARD as one compound unit
spanning what CLAUDE.md calls Phases 5 and 6, not two cleanly separated phases.
**Output exists and is non-empty in ref runs:** Yes — `vanguard_signals.csv` (1,612
logical rows, 509 columns), `vanguard_rejects.csv` (39 rows), `vanguard_run_summary.json`
— all three confirmed via direct `csv.DictReader`/JSON read, not `wc -l` (the file
contains embedded newlines inside multi-line `reasoning` text fields, which makes raw
`wc -l` a **false 86,605** for what is actually a 1,612-row CSV — a specific trap for
anyone estimating row counts from this file with a line-counting tool instead of a CSV
parser).

### The editable-install shadowing hazard — resolved

The brief's specific concern: a second, independent `vanguard` Python package exists at
`C:\Users\ACKVerissimo\vanguard\vanguard\` (a subdirectory of the external
actuarial-tooling tree at `C:\Users\ACKVerissimo\vanguard\`), and it is **also**
pip-installed as an editable package (`pip show vanguard` → `Version: 1.0.0`, `Editable
project location: C:\Users\ACKVerissimo\vanguard`, registered via
`__editable__.vanguard-1.0.0.pth` in
`C:\Users\ACKVerissimo\AppData\Roaming\Python\Python314\site-packages`, the **user**
site-packages directory — not the interpreter's own `C:\Python314\Lib\site-packages`).

**Resolution mechanism, confirmed by reading the actual finder file** and by an empirical
import test:

1. The editable install uses the modern setuptools PEP-660 mechanism: its `.pth` file
   runs `__editable___vanguard_1_0_0_finder.install()`, which does
   `sys.meta_path.append(_EditableFinder)` — **appended**, not inserted at the front.
2. `run_vanguard_from_packages.py` itself inserts the repo root at `sys.path[0]`
   (`:47-49`, `_REPO_FOR_IMPORT = Path(__file__).resolve().parents[1]`) **before** its
   own `from vanguard.physics_state_engine import ...` (`:83`), `from
   vanguard.core.actuarial_registry import ...` (`:135`), and other `vanguard.*` imports.
   The repo root (`C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`) itself contains a real
   `vanguard/__init__.py` (confirmed: `from .main import VanguardEngine, analyze_ticker`).
3. Python's standard `PathFinder` (already registered in `sys.meta_path` at interpreter
   startup, ahead of the appended `_EditableFinder`) resolves `import vanguard` against
   `sys.path` in order — finding the **repo's own copy** at `sys.path[0]` before the
   appended editable finder is ever consulted.
4. **Empirically verified**: running `sys.path.insert(0, r'C:\Users\ACKVerissimo\AVSHUNTER-Intelligence'); import vanguard; print(vanguard.__file__)` resolves to
   `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\vanguard\__init__.py` — the repo copy,
   not the external editable-installed one.
5. `actuarial_cache_builder.py` (Phase 4.6, an *externally*-located script at
   `C:\Users\ACKVerissimo\vanguard\actuarial_cache_builder.py`, dynamic-imported
   **in-process** into the orchestrator, not as a subprocess — Pass B §6) also imports
   `from vanguard.core.actuarial_registry import ...` etc. (`:45,50-51`) with **no
   sys.path manipulation of its own** (confirmed: zero `sys.path`/`sys.modules` matches
   in that file). Since `intelligent_orchestrator.py` is launched as `python
   intelligent_orchestrator.py ...`, Python auto-prepends the script's own directory
   (repo root, since the orchestrator lives at `BASE_DIR`) to `sys.path[0]` before any
   code runs — so this externally-located script, too, resolves `vanguard.*` against the
   **repo's** copy, not its own physical sibling directory, when it executes inside the
   orchestrator's process.

**Net finding: the repo's own `vanguard/` package wins in every call site checked this
pass**, by the mechanism above (sys.path[0] precedence over an appended meta_path
finder), not by any explicit conflict-avoidance code — it is an emergent property of
where each entry point happens to put the repo root on `sys.path`.

**Currently no observed divergence.** Byte-for-byte `sha256` comparison this pass of
every file the shadowing question could affect —
`vanguard/core/actuarial_registry.py`, `cache_integrity.py`, `schema_guard.py`,
`actuarial_core_v7.py`, `schema_contract_v6.py`, `truth_packet.py`,
`vanguard/physics_state_engine.py`, and `vanguard/main.py` — shows the repo copy and the
external copy are **byte-identical** for all eight files checked. So the hazard is real
and latent (nothing enforces the two trees staying in sync; a future edit to only one
copy would silently diverge, and the resolution mechanism means the *externally-located*
`actuarial_cache_builder.py` would in that case run against the *repo's* `vanguard/core/`
code, not its own physically-adjacent sibling — the more surprising direction for a
maintainer editing the external tree to expect) — but it is not, at the time of this
audit, producing any actual behavioural difference between the two trees.

**Inputs**
| Artefact | Path | Rows (ref run) | Key fields consumed |
|---|---|---|---|
| `packages/index.json` | `run_dir/packages/index.json` | 1,653 entries → `load_package_paths()` builds 1,651 paths (the 2 BLOCKED entries have `package_path: None`, silently skipped by `if not raw: continue`, `:1306-1313`) | `packages[].package_path` |
| Every `.package.json` | `run_dir/packages/*.package.json` | 1,651 | `discovery.*`, `regime_snapshot`/`macro.regime_snapshot`, `macro.payload`, `ohlcv_daily`/`ohlcv`/`technical_data.ohlcv`/`timeseries.ohlcv_daily`/`discovery.ohlcv` (six-location canonical resolver, `_resolve_daily_bars():466-537`), `actuarial` (still the Phase-5 DEFERRED placeholder — Vanguard runs *before* Phase 8.5) |

**Outputs**
| Artefact | Path | Rows (ref run) | Key fields produced |
|---|---|---|---|
| `vanguard_signals.csv` | `run_dir/vanguard/vanguard_signals.csv` | **1,612** (verified via `csv.DictReader`, not `wc -l` — see trap noted above) | 509 columns: `ticker`, `verdict`, `final_recommendation`, `reasoning`, Layer-2 headline metrics (`state_hash`, `n_observations`, `win_rate_20d`, `expected_value_20d`, `confidence_level`, `has_edge`, `edge_direction`, `failed_gate`, `no_edge_reason`), multi-horizon EV surface (`win_rate_5d/10d`, `expected_value_5d/10d`, `horizon_profile`), Phase-2 baton fields (`layer2__*`, 30 fields with explicit validation + safe defaults, `validate_phase2_baton()`/`_ensure_phase2_baton_fields()`, `:234-330`), fully-flattened `layer1__*`/`layer2__*`/`layer3__*` debug columns, `macro_quant_columns_for_row()` output, scanner passthrough columns, physics-state columns (`PHYSICS_FIELDS`, from `calculate_market_physics()`), `behaviour_state_hash`/`behaviour_state_key` (Sprint A enrichment, `enrich_behaviour_state_dataframe()`), truth-packet fields |
| `vanguard_rejects.csv` | `run_dir/vanguard/vanguard_rejects.csv` | 39 | `ticker`, `package_path`, `reason_code` (100% `DATA_FAILURE_NO_OHLCV`), `reason_codes`, `error`, `exception_type`, `diagnostics` |
| `vanguard_run_summary.json` | `run_dir/vanguard/vanguard_run_summary.json` | 1 record | `packages_total: 1651`, `passed: 1612`, `rejected: 39`, `reject_top_reasons` |

**Attrition**
Rows in: 1,651 → Rows out (PASS): **1,612** (loss: 39, **1.17% of 3,323**; 2.36% of the
1,651 processed)

| Cause | Count | Fail-open or fail-closed | path:line |
|---|---|---|---|
| Data Contract Validator hard gate — `DCV.validate(pkg)` fails, `_dcv_reason` becomes `DATA_FAILURE_{reason}` | 39, all `DATA_FAILURE_NO_OHLCV` (confirmed: the exact same 39 tickers as the Backfill stage's no-OHLCV set — set-equality checked directly, not just count-equality) | Fail-closed per ticker (one reject does not kill the batch — explicit "per-package isolation" design goal, module docstring `:16-17`) | `:1394-1411` |

**Reconciliation:** 1,651 − 39 = 1,612. Exact. The causal chain is fully traceable
end-to-end: `validate_series()` (Backfill) rejects a bar series → `ohlcv_daily: None` in
the package → `_resolve_daily_bars()` (Vanguard) finds nothing in any of its six
candidate locations → `DCV.validate()` fails with `NO_OHLCV` → reject row written. No gap
at any link in this chain for either reference run (08-16: 40/1,660, same signature).

**Field lineage**
- Created: `debug_signature` — a 9-dimension `|`-joined string used for state-hash
  audit; dims 5–9 are sourced from `disc` (discovery fields passed explicitly into
  `signal_to_row()`), dims 1–4 from Vanguard's own Layer-2 output. An explicit in-code
  comment (`:1088-1093`) documents that a March 2026 fix wired dims 5–9 from discovery
  because, before that fix, an unpopulated `disc` argument caused every ticker to
  collapse to one state hash — a previously-fixed instance of exactly the class of bug
  this Standing Contract is auditing for; carried here as historical context, not
  re-verified as still-fixed (the fix is dated and the code path matches its own
  description, so treated as settled, not re-derived).
- Created: "WIN RATE FALLBACK BRIDGE" (`:1156-1210`) — when actuarial win-rate fields are
  entirely absent (which is **always true at this stage**, since `actuarial` is still the
  Phase-5 DEFERRED placeholder when Vanguard runs), the code seeds `win_rate_5d/10d/20d`
  from `disc.get("win_probability")` (Wyckoff structural probability, clamped to
  [0.30, 0.80]) and stamps `actuarial_source = "DISCOVERY_FALLBACK"`. This means **every
  row in `vanguard_signals.csv` for this reference run has `actuarial_source` set either
  to `MISSING` (if `win_probability` was also unavailable) or `DISCOVERY_FALLBACK`, never
  the "real" `V6_DB` value** — because the real actuarial match only happens two phases
  later, at Phase 8.5, and is written to the **package JSON**, not back into
  `vanguard_signals.csv`. Any downstream reader of `vanguard_signals.csv`'s
  `actuarial_source`/`win_rate_*` columns (rather than the package JSON's post-Phase-8.5
  `actuarial` block) is reading pre-actuarial-enrichment values by construction — not a
  bug, but a real "which copy has the current data" trap matching the Standing Contract's
  known-risk-pattern class (field name collision/staleness across producers), now
  documented for these specific fields. **Not independently re-verified this run by
  reading the actual `actuarial_source` column values** — flagged as a structural
  conclusion from the code's own logic and the confirmed Phase-8.5 timing, not a direct
  count.
- Governance routing (`:1339-1440`) — tickers with an open Trade Contract
  (`list_open_tickers()`) are routed to `TradeGovernanceEngine` instead of fresh
  discovery scoring; a verdict of `EXIT` removes the ticker from the open set for the
  rest of the run. Not traced further (no open contracts implied by this reference run's
  summary; not independently confirmed empirically this pass).

**Failure behaviour**
Per-package: any exception during `build_orchestrator_like_payload()`/`adapter.adapt*()`/
`engine.analyze()` is caught (`:1492-1503`), classified via `_short_reason()` (pattern
match on `regime_snapshot`/`ohlcv`/`ema200` substrings, else the exception class name),
and written as a reject row — fail-closed per ticker, fail-open for the batch. Whole-run:
`vanguard.main`/`vanguard.integration.orchestrator_adapter` import failure → `return 2`
immediately (`:1330-1337`), before any package is processed — fail-closed at the run
level only for this one precondition.

**Dead code on this path:** none identified in this module.

**Open questions**
- Exact reason-code distribution for `_short_reason()`'s generic exception-class-name
  fallback bucket — not applicable this run (all 39 rejects were the specific
  `DATA_FAILURE_NO_OHLCV` DCV-gate reason, which is produced before `_short_reason()` is
  ever reached for those rows).
- Whether the tier-demotion inconsistency noted in the Trap Engine section above
  (undemoted `disc` reaching `signal_to_row()`) has any measurable effect on
  `debug_signature` dim 8/9 or `win_probability`-derived fields — not traced further.

---

## Handoff confirmation — the `_ACTUARIAL_DEFERRED_BLOCK` placeholder

The Standing Contract asks specifically whether the later stage (Phase 8.5,
`actuarial_enrichment_pass.py`) finds and populates *every* package, or only some.
**Answer, from `packages/index.json`'s own `actuarial_enrichment_pass` metadata block
(written by Phase 8.5 itself into the same index file after it runs — read directly,
not re-derived):**

```
run_at: 2026-08-18T06:08:25Z
vanguard_tickers: 1612
packages_expected: 1651
packages_patched: 1651
missing_package_files: 0
outcomes: EXACT_MATCH=1414, FALLBACK_MATCH=0, NO_MATCH=198, NO_VANGUARD_ROW=39,
          LOOKUP_FAILED=0, ERROR_READ=0, ERROR_WRITE=0
match_rate: 0.8565  (1414/1651)
```

**Every one of the 1,651 built packages is found and touched (`missing_package_files: 0`,
`packages_patched == packages_expected`)** — the handoff itself does not lose any
package. But only **85.65%** get a real actuarial match (`EXACT_MATCH`); 198 (12.0%) get
`NO_MATCH` (a cache miss — package found, patched, but with no matching actuarial state)
and the remaining 39 (2.4%) are exactly the Vanguard-rejected no-OHLCV set
(`NO_VANGUARD_ROW` — there was no Layer-2 state hash to look up against, since these
packages never got a Vanguard signal row at all). This reconciles exactly: 1,414 + 198 +
39 = 1,651. **What Phase 8.5 actually writes for `NO_MATCH`/`NO_VANGUARD_ROW` packages
(is the placeholder left as-is, or replaced with a different neutral value?) was not
traced this pass** — `actuarial_enrichment_pass.py`'s own internals belong to whichever
pass covers Phase 8.5/Options Intelligence in depth (this pass's scope ends at Options
Intelligence's *input*, and this file's own logic runs *after* Options Intelligence
per §0's correction, so its internals are out of scope here by construction, not by
oversight).

---

## The funnel, updated

Universe fed to Discovery (augmented, Pass B's established denominator): **3,323 = 100.0%**

| Stage | Rows out | % of 3,323 | Loss this stage | % of 3,323 |
|---|---|---|---|---|
| Discovery final CSV (Pass B) | 1,653 | 49.7% | — | — |
| Package Build | 1,651 | 49.7% | 2 (dotted tickers) | 0.06% |
| Backfill Timeseries (packages with OHLCV) | 1,612 | 48.5% | 39 (no usable bar series) | 1.17% |
| Run VANGUARD (`vanguard_signals.csv` PASS rows) | 1,612 | 48.5% | 0 (Vanguard's own reject count exactly equals Backfill's OHLCV-failure count — same 39 tickers, not an independent additional loss) | 0.0% |
| Options Intelligence input (`pd.merge(discovery, vanguard, on='ticker', how='inner')`) | **1,612** | 48.5% | 0 (inner join loses nothing beyond what Backfill/Vanguard already excluded — every Vanguard-PASS ticker is, by construction, also a Discovery/Package-Build survivor) | 0.0% |
| Options Intelligence "eligible" (tier filter ∪ Vanguard-support override, minus WAIT-intent exclusion) | 1,400 | 42.1% | 212 | 6.4% |

Two important clarifications on this table:
1. **Vanguard's 39-row reject count and Backfill's 39-package OHLCV-failure count are the
   same 39 tickers**, confirmed by exact set comparison — this is one attrition event
   surfacing at two measurement points, not two independent losses. Reporting it once (at
   Backfill, where the underlying cause originates) avoids double-counting in the funnel.
2. **The inner join at the OI boundary drops nothing beyond Backfill/Vanguard's own
   losses** in this run, because every ticker that reaches `vanguard_signals.csv` is
   provably a subset of the discovery CSV's own tickers (packages are built from
   discovery rows one-to-one, minus the 2 blocked at Package Build). This is a
   **run-specific empirical fact**, not a structural guarantee of the join itself — see
   the field-drop analysis below for why the *field*-level effect of this same merge is a
   real (if partially mitigated) hazard even though the *row*-level effect happens to be
   loss-free this run.

**1,400 of the 3,323-ticker universe reach Options Intelligence's actual scoring loop —
42.1%.** Options Intelligence's own internal tier/WAIT-intent filtering (1,612 → 1,400,
-212 rows, -6.4% of 3,323) is the boundary this pass stops at per the Standing
Contract's scope ("between Discovery output and Options Intelligence input"); the
mechanics of `ELIGIBLE_TIERS = {0,1,2}` (`avshunter_options_intelligence.py:613`) and the
Vanguard-support-override logic (`:7078-7103`) are visible in the source but their
internals belong to whichever pass covers Options Intelligence itself.

---

## Field-drop comparison at the Options Intelligence boundary

Per the Standing Contract, this boundary is "a prime candidate for the field-mismatch
failure class that historically collapsed 1,470 signals to zero." Two distinct hazards
were found; the row-level one (§ above) turned out loss-free this run, but the
**field**-level one is real, evidenced, and not run-dependent — it is a property of the
merge code itself.

**Mechanism**: `run_options_layer()` does `merged = pd.merge(disc, vanguard, on='ticker',
how='inner')` (`avshunter_options_intelligence.py:7061`). Discovery's pinned CSV has 311
columns; `vanguard_signals.csv` has 509. **111 column names (excluding `ticker`) are
identical between the two** (confirmed by direct set-intersection of both CSVs' headers,
this reference run). `pandas.merge()`'s default behaviour appends `_x`/`_y` suffixes to
every overlapping non-key column — so unless something explicitly reconciles each one,
the bare column name disappears from `merged` and any code reading it by its unsuffixed
name gets nothing.

**What is reconciled, and by what:**
- `timestamp` — explicitly handled inline (`:7068-7071`): `timestamp_y` (Vanguard's,
  "the correct signal date for SB time-stop anchoring" per the code's own comment)
  renamed back to `timestamp`, `timestamp_x` dropped.
- `adx_14`, `atr_percentile_rank` — reconciled by `_coalesce_ev3_merge_inputs()`
  (`:4049-4070`), preferring the Vanguard-suffixed (`_y`) value with Discovery (`_x`) as
  fallback.
- 52 of the 111 overlapping names — reconciled by `resolve_macro_suffix_columns()`
  (`scripts/macro_quant_packet.py:844-876`), which is driven by the fixed
  `MACRO_QUANT_CSV_FIELDS` list (`:24-80`, 55 entries) and coalesces `field`/`field_x`/
  `field_y`/`field__vg`/`field__opt` variants, preferring an existing non-missing value
  and falling back across variants otherwise.

**What is NOT reconciled by either helper — ~56 overlapping field names left to silently
split into `_x`/`_y`:** all 26 `catalyst_*` columns, all 16 `scanner_*` columns,
`crabel_compression`, `crabel_pattern`, `crabel_state`, `cheap_convexity_flag`,
`days_to_catalyst`, `dominant_trend`, `event_convexity_score`, `iv_rank`, bare `sector`,
`vms_decision`, `vms_score`, `vol_spread`, `volume_ratio`, `vwap_bias`.

**Confirmed exemplar — `iv_rank`:** `_flt_conv(signal, 'iv_rank')` is read directly at
`avshunter_options_intelligence.py:819` (one of several fallback sources for a
compression-detection check, `:818-842`). After the merge, no bare `iv_rank` column
exists in `merged` — only `iv_rank_x`/`iv_rank_y` — so this specific read returns
whatever `_flt_conv`'s own missing-key handling produces (not traced to its exact
default), **silently losing access to both Discovery's and Vanguard's `iv_rank` value at
this one call site**, even though the value exists in both source files. This is
partially mitigated in practice because the surrounding code tries `iv_rank_252d` first
(a non-overlapping column name, unaffected by the merge) — so the net effect on this
specific check's output was not independently confirmed to be a live functional gap this
run, only confirmed to be a **structurally real, reproducible field-access failure at
this exact line for the bare `iv_rank` key**.

**Checked and confirmed NOT affected (three of the ~56 at-risk names):** `dominant_trend`,
`crabel_state`, `vwap_bias` — grepped across the full options-intelligence module for
both bare and `_x`/`_y`-suffixed access patterns; zero matches for any form. These three
fields are simply never read by name in this module, so the merge-suffix hazard is moot
for them specifically (an inert extra pair of columns, not a functional loss).

**Not exhaustively checked**: the remaining ~53 of the ~56 at-risk field names (all
`catalyst_*` and `scanner_*` columns in particular) were not individually grepped for
consumption patterns this pass — flagged as unfinished, consistent with Pass B's own
stated caveat on its discovery-field census. Given `catalyst_*` fields are known (Pass B
§8.6) to be actively read downstream by `catalyst_truth_engine.py` and are the subject of
CLAUDE.md's catalyst-based options review-lane logic, and `scanner_*` fields feed VMS
scoring per Pass B §1, these are the highest-priority candidates for a follow-up
per-field consumption audit at this exact merge boundary.

**Fields Options Intelligence reads that nothing in this span produces:** not
systematically checked in the reverse direction (i.e., column names process_ticker()
expects that are absent from both CSVs' 311+509 headers) — this would require a full
enumeration of every `row.get(...)`/`signal.get(...)` call site in a 7,000+-line module,
which is Options Intelligence's own pass's job, not this one's.

---

## Reconciliation — every stage checked this pass

| Stage | In | Out | Loss | Attributed | Shortfall |
|---|---|---|---|---|---|
| Package Build | 1,653 | 1,651 | 2 | 2 (dotted tickers) | **None** |
| Backfill | 1,651 | 1,612 (with OHLCV) | 39 | 39 (`validate_series()` rejection, reason breakdown unrecoverable but total count exact) | **None** |
| Run VANGUARD | 1,651 | 1,612 | 39 | 39 (same 39 tickers as Backfill — set-verified identical) | **None** |
| OI inner-join (this run) | 1,612 (Vanguard) × 1,653 (Discovery) → | 1,612 | 0 | n/a — loss-free this run, by construction | **None** |
| Actuarial Enrichment handoff (Phase 8.5, package-file discovery) | 1,651 expected | 1,651 patched | 0 | 0 missing files | **None** |

**No unexplained gap of the "365-row" precedent class was found anywhere in this span.**
Every subtraction in this pass was checked against a directly-read artefact (package JSON
census, CSV row counts via `csv.DictReader`, JSON summary files), not derived from what
the code should produce.

---

## Corrections to Pass A / Pass B

1. **Pass A's dispatch-table ordering for items 14–17 is backwards** — see §0 above.
   Vanguard pipeline and Options Intelligence run first; the Macro Horizon Router and its
   CSV patch run after, not before. Verified independently by `run_horizon_router()`'s
   own fallback-chain design, which only makes sense running after OI.
2. **Pass B's finding that `avshunter_trap_engine.py` is "live and wired into the
   Vanguard phase" is confirmed and extended**: not only is it wired in, its full
   downstream consumer (`avshunter_options_intelligence.py`'s Sprint 3 CSM-modifier
   logic) is *also* fully implemented and empirically firing (148/1,400 rows this run) —
   directly contradicting CLAUDE.md's framing of Sprint 3 as requiring an architectural
   decision before any coding begins.
3. No corrections found to Pass B's Phase 0–3 material itself (universe denominator,
   discovery funnel, quality-gate thresholds) — not re-examined beyond what this pass's
   own boundary work required.

---

## What this pass did not cover

- Full per-field consumption audit of the ~56 unreconciled discovery/vanguard overlap
  columns at the OI merge boundary (only `iv_rank`, `dominant_trend`, `crabel_state`,
  `vwap_bias` individually checked) — flagged as the top follow-up item, especially the
  26 `catalyst_*` and 16 `scanner_*` names given their known downstream importance.
- `actuarial_enrichment_pass.py`'s own internals (what it writes for `NO_MATCH`/
  `NO_VANGUARD_ROW` packages, its exact matching algorithm against the 508-state cache) —
  out of scope by the §0 ordering correction (it runs after Options Intelligence).
- Options Intelligence's own internal tier-filter/WAIT-exclusion logic
  (1,612 → 1,400) beyond the top-level counts reported in the funnel table — belongs to
  the pass that covers Options Intelligence itself.
- `vanguard.main.VanguardEngine`'s internal Layer 1/2/3 scoring logic (auction structure,
  actuarial state matching, execution layer) — only its I/O contract with
  `run_vanguard_from_packages.py` was traced, not its own internals.
- `contracts/macro_enrichment_delta.py`'s auto-discovery behaviour (whether
  Inject-Macro-into-Packages ever picks up a delta file without an explicit CLI flag).
- Reason-code breakdown for the 39/40 Backfill OHLCV failures among
  `EMPTY`/`TOO_SHORT`/`NULLS_IN_LAST_10`/`STALE_LAST_BAR` — not recoverable from
  artefacts alone without re-running with `--verbose`.
- `vanguard.trade_contract`/`vanguard.trade_governance`'s open-contract governance
  routing — mentioned (code exists, call site confirmed) but not traced into its own
  logic; no open contracts were evident from this reference run's summary counts.
- A second-run (08-16) deep dive parallel to everything done for 08-18 — only used for
  stability spot-checks (package/reject counts, blocked-ticker mechanism) at the specific
  points this pass's own findings needed corroboration, not independently re-derived
  stage by stage.

This pass is otherwise complete for its stated scope: the corrected execution order for
items 14–17, full per-stage schema for Package Build / Inject Macro / Backfill / Trap
Engine / Run VANGUARD, the editable-install shadowing resolution with byte-level
divergence check, the Trap-Engine trigger-ordering defect with full mechanism/
counterfactual/recoverability/blast-radius analysis, the Sprint 3 downstream-consumption
proof, the updated funnel, the field-drop comparison at the OI boundary, and a full
reconciliation table showing no unexplained gaps.
