# Part I — `scripts/`

_38 files. Facts from `_tooling/extract_facts.py` (`facts/scripts.json`), with
targeted reads where a count flagged something. Depth is proportionate: deep on
the stages with findings, compact but template-complete on helpers. Every
section states its own confidence, and files whose bodies were not read are
marked **UNTRACED** rather than described speculatively._

---

### scripts/avshunter_superbrain_layer.py
**Classification:** ORCHESTRATED by config registration · **DEAD in execution** (2,771 lines; **124 fallback chains and 28 direction tokens — the densest file measured in this audit**)
**Real execution position:** **NOT_INVOKED.** `intelligent_orchestrator.py:466` registers `SUPERBRAIN_LAYER` with the inline comment "Logic migrated to OI 2026-04-28. File retained: run_superbrain_passthrough() copies OI→superbrain_enriched. Do NOT remove". `run_superbrain_layer()` is *defined* at `:2695` but the evening workflow calls **`run_superbrain_passthrough`** at `:4497` instead, whose own docstring states "SuperBrain script was deprecated 2026-04-28; this passthrough ensures the downstream consumers still receive a correctly shaped CSV" (`:2839`) [OBSERVED]
**Task in the process:** Would have been the SuperBrain enrichment layer between Options Intelligence and EIL. Its surviving purpose is entirely vestigial: the artefact it once produced, `superbrain_enriched_{run_id}.csv`, is now produced by a 40-line passthrough that copies the OI CSV and maps `options_verdict → sb_final_verdict`
**Entry points:** `__main__`; argparse CLI
**Imports (production):** pandas, numpy, plus `scripts/data_contract_validator.py:229` (import only) · **Imported by:** **0 modules** · **Broken/retired imports:** NONE
**Inputs** — the OI CSV and package files (historically). 124 fallback chains [OBSERVED, extractor]
**Logic and algorithms** — historical SuperBrain scoring. NOT_ESTABLISHED in detail — the body was **not read**, because the module does not execute
**Decision branches** — 28 direction tokens present [OBSERVED, extractor]; **CALL path / PUT path / other-blank path all NOT_ESTABLISHED.** Recorded as UNTRACED: reading 2,771 lines of direction logic in a module that cannot run was judged a poor use of audit budget, and the judgement is disclosed rather than hidden
**Computations and formulas (exact)** — NOT_ESTABLISHED (UNTRACED)
**Models** — NOT_ESTABLISHED
**Outputs** — historically `superbrain_enriched_{run_id}.csv`; 7 write sites [OBSERVED]. **On the evidence run this artefact was produced by the passthrough, not by this file** [MEASURED — `superbrain/superbrain_enriched_20260831_010309.csv`, 1,248 rows, 856 columns, mtime in the 02:55 rewrite cluster]
**Handoff** — the *artefact* is load-bearing (EIL, GARCH, WBS and the CT gate all require it); the *module* is not
**Missing-data handling** — NOT_ESTABLISHED
**Contradictions found here:** CON-611 — `intelligent_orchestrator.py:108` states "Evening workflow: run_superbrain_layer(eod_mode=True) explicit call". The evening workflow makes no such call; it calls `run_superbrain_passthrough` (`:4497`). Both `run_superbrain_layer()` (`:2695`) and this 2,771-line script are dead
**Gaps found here:** GAP-613
**Comment/docstring claims audited:** `intelligent_orchestrator.py:466` "Do NOT remove — EIL/GARCH/WBS/CT Gate require superbrain_enriched to exist" → **PARTIAL**: the *artefact* is required, the *file* is not; removing the file would not affect the artefact, which the passthrough writes. `:3062` "Re-run SuperBrain manually: python scripts\avshunter_superbrain_layer.py" → a live operator instruction pointing at a module deprecated 2026-04-28
**Confidence in this section:** HIGH for the DEAD classification and the passthrough substitution (call sites and both docstrings read); **LOW / UNTRACED** for the file's internal logic

---

### scripts/avshunter_universe_scanner.py
**Classification:** ORCHESTRATED by config registration · **NOT_INVOKED** (3,203 lines; 20 direction tokens, 97 fallback chains, 14 write sites)
**Real execution position:** **NOT_INVOKED.** `intelligent_orchestrator.py:414` registers `UNIVERSE_SCANNER_SCRIPT`; `:981` lists it under `optional` in the preflight *existence* map; `:591` and `:3790` only **read** `data/output/universe_scanner/scanner_manifest.json`. No `_run(...)` or `subprocess` reference to the script exists [OBSERVED — exhaustive grep of `UNIVERSE_SCANNER_SCRIPT` returns only `:412-414`, `:981`, `:4067`]
**Task in the process:** Scans a built-in Tier-1/Tier-2 universe via MarketData.app, computes IV/RV, IV Rank, term slope, skew, compression, a VMS score and a per-ticker direction vote, ranks contracts by an OLIS composite, and writes `contracts_*.csv`, `vms_scoreboard_*.csv` and `scanner_manifest.json` (`:2849-2863`, `:2983-2984`), which orchestrator Phase 0 injects as **new discovery tickers** if the manifest is under 24 h old (`:598-608`)
**Entry points:** `main()` (`:3203`); CLI `--tier1 --tier2 --tickers --top-n --dry-run --test --rebuild-iv-cache` (`:3157-3180`)
**Imports (production):** requests, pandas, numpy, sqlite3, threading (`:60-70`) · **Imported by:** **NONE** (`signal_grader.py:41` reads its manifest *file* only) · **Broken/retired imports:** NONE
**Inputs** — a SQLite IV cache; the pipeline universe file. Fallback chains include `price_data.get("momentum_20d", 0.0) or 0.0`, `.get("above_ma20", None)`, `.get("rsi_14", 50.0) or 50.0` (`:1345-1348`) — a **double** fallback turning a missing RSI into a neutral 50. External: MarketData.app OHLCV, chains and historical IV, throttled by `CALL_DELAY=0.25` (`:101`), SQLite-cached
**Logic and algorithms** — a direction-voting ballot (`:1350-1375`); an OLIS composite with component DC (`:1965`); sweep classification (`:573-577`)
**Decision branches** — **all three arms explicit and distinct**, one of the few in this batch: `call_votes > put_votes` → `"CALL"` / `side="call"` (`:1367-1369`); `put_votes > call_votes` → `"PUT"` / `side="put"` (`:1370-1372`); **tie → `"NEUTRAL"` / `side="all"`, labelled a straddle candidate (`:1373-1375`)**
**Computations and formulas (exact)** — `call_votes += 2 if momentum_20d > 0.03 else 1 if > 0.0`; `put_votes += 2 if < -0.03 else 1 if < 0.0` (`:1351-1354`) — note the ladder is `if/elif`, so a `momentum_20d` of **exactly 0.0** scores no vote either way; `±1` each for `above_ma20`, `above_ma50` (`:1355-1358`); `put_votes += 1 if rsi_14 > 70`, `call_votes += 1 if rsi_14 < 30` (`:1359-1360`); `call_votes += 1 if skew > 0.05`, `put_votes += 1 if skew < -0.05` (`:1361-1362`); `dir_mult = 1.0` aligned, `0.70` NEUTRAL, `0.25` mismatch (`:1985-1993`); sweep `"CALL_SWEEP" if cp_ratio >= 2.0 else "PUT_SWEEP" if cp_ratio <= 0.5 else "NEUTRAL"` (`:573`); score clamped `min(100.0, max(0.0, score))` (`:1962`)
**Models** — VMS scoreboard + OLIS composite; hand-set weights (DC ×0.25, `:1971`); **no calibration source claimed**; version tag "v7.0" in the docstring only
**Outputs** — `contracts_{run_id}.csv` + `contracts_latest.csv` (`:2849-2850`); `vms_scoreboard_{run_id}.csv` + `_latest.csv` (`:2862-2863`); `scanner_manifest.json` (`:2983`) carrying `go_new/go_known/probe_new/probe_known/tickers/max_age_hours`. **No atomic promotion** (direct `to_csv`/`open(...,'w')`). **No schema/version field in the manifest.** Authority claim: docstring `:38` "Pipeline NEVER blocked if scanner has not run" → **HOLDS** (`intelligent_orchestrator.py:598-601` returns an empty dict on absence)
**Handoff** — Receives nothing from the orchestrator. Hands to orchestrator Phase 0 (`load_scanner_manifest`, `:591`) and `signal_grader.py:41`. Join key: `ticker`, plus `run_id` for the scanner context
**Missing-data handling** — manifest absent → empty dict, logged "pipeline runs without scanner input" (`intelligent_orchestrator.py:598-601`); older than `max_age_hours` → empty, WARNING "stale" (`:608-610`); parse exception → empty with a WARNING (`:637-639`); missing `vms_scoreboard` path → `vms_df=None` (`:617`). §10-compliant? **N**
**Contradictions found here:** CON-612 — the docstring describes a "passive, non-blocking" handshake in which the orchestrator reads the manifest, but **nothing in the tracked tree runs the scanner**: no orchestrator call, no `.bat`, no `.ps1`, no scheduled task. The 24-hour freshness gate therefore degrades to "no scanner input" on every automated evening run unless a human ran it manually within the window
**Gaps found here:** GAP-614
**Comment/docstring claims audited:** `:34-38` manifest handshake and "Pipeline NEVER blocked" → **HOLDS**. `:22` "real 52-week weekly ATM IV … confidence ~95%" → **PARTIAL** (a numeric confidence asserted with no calibration artefact anywhere in the tree). `:53-55` "--test writes real output files and scanner_manifest.json" → **HOLDS**, and is itself a hazard: test mode writes the same manifest the orchestrator trusts, from synthetic OHLCV (`:52`)
**Confidence in this section:** MEDIUM-HIGH — invocation mapping exhaustive (HIGH); interior scoring sampled at the direction ballot and composite (MEDIUM)

---

### scripts/actuarial_enrichment_pass.py
**Classification:** ORCHESTRATED · LIVE (1,157 lines; 22 fallback chains, 7 write sites)
**Real execution position:** **Evening Phase 8.5** — `intelligent_orchestrator.py:4257-4310` loads it via `importlib.util.spec_from_file_location` and calls `mod.run_actuarial_enrichment_pass(run_id, base_dir)` (`:4269-4276`); also `resume_after_vanguard.py:57-61`. **Non-critical**: wrapped in `try/except` that logs a warning and continues (`:4308-4310`)
**Task in the process:** `build_packages_from_discovery.py` runs before Vanguard, so package `actuarial` blocks are written `DEFERRED` (`:103-110`, `:613`). This pass reads `vanguard_signals_enriched_{run_id}.csv`, derives the 9-field state key, looks it up in the actuarial cache, and patches `pkg["actuarial"]` in place so the Execution Decision Engine has edge data instead of zeros
**Entry points:** `run_actuarial_enrichment_pass()` (`:963`); `main()` (`:1117`)
**Imports (production):** pandas; actuarial registry/cache-validation helpers (`:140`); truth-packet helpers · **Imported by:** `vanguard/tests/test_phase2_baton_validation.py:1` · **Broken/retired imports:** NONE
**Inputs** — `options/vanguard_signals_enriched_{run_id}.csv` first, falling back to `vanguard/vanguard_signals.csv` (`:783-790`); the v7 parquet cache via the registry. Fallback chains via `_VANGUARD_STATE_MAP` (`:412-463`): `vol_regime ← layer2__vol_regime | vol_regime`; `trend_direction ← layer2__trend_direction | dominant_trend | trend_direction`; `structure_quality ← layer2__structure_quality | structure_quality`; `wyckoff_phase_bucket ← wyckoff_phase_bucket | current_phase | phase`; `macro_regime ← macro_regime | active_regime | regime_state | regime`; `trend_maturity ← trend_maturity | layer2__trend_maturity | trend_mat`; `catalyst_proximity ← catalyst_proximity | earnings_proximity | days_to_earnings_bucket | event_proximity`. `adx_bucket` and `atr_pct_bucket` use sentinel entries `"__adx_derived__"` / `"__atr_pct_derived__"` that are never matched, values coming from `_derive_adx_bucket()` (`:467`) and `_derive_atr_pct_bucket()` (`:507`). External calls: **none**
**Logic and algorithms** — 9-dimension state-key construction (`_derive_state_from_vanguard_row`, `:537`); graded fallback via `FALLBACK_DROP_SEQUENCE` dropping `catalyst_proximity` → `atr_pct_bucket` → `trend_maturity` before touching the core six (`:410-411`); outcome classification `EXACT_MATCH | FALLBACK_MATCH | NO_MATCH | NO_VANGUARD_ROW | ERROR` (`:841`, `:946`)
**Decision branches** — **NOT_APPLICABLE, and that is the finding.** The module is **direction-agnostic**: no `direction`, `CALL` or `PUT` token appears anywhere in the file [OBSERVED — 0 direction tokens]. The actuarial block it writes (`win_rate_5d/10d/20d`, `expected_move_*`) is therefore a single **direction-blind prior applied identically to CALL and PUT candidates**
**Computations and formulas (exact)** — `adx_bucket = STRONG if adx_14 >= 25 else MODERATE if adx_14 >= 15 else WEAK` (`:467+`, documented `:26-28`), with legacy `HIGH/MEDIUM/LOW` normalised; `_FORCE_CATALYST_NONE` forces `catalyst_proximity = "NONE"` regardless of the resolved alias value (`:453-457`); `_usable = EXACT_MATCH + FALLBACK_MATCH` (`:1052`)
**Models** — actuarial cache lookup (`_LOOKUP_FN(state, _CACHE_DF)`, `:722`); parameters are the cache itself; version tags `_SCHEMA_VERSION` / `_SCHEMA_FINGERPRINT` propagated into every block (`:713`, `:728`, `:766`, `:859`)
**Outputs** — patches `pkg["actuarial"]` in the run's `packages/*.package.json` with `available, actuarial_source, schema_version, schema_fingerprint, canonical_database_path, state_key, matched_key, fallback_depth, fallback_dims_dropped, sample_size, valid, no_match, penalty_multiplier, expected_move_5d/10d/20d, win_rate_5d/10d/20d, risk_10d, efficiency_10d, vol_10d, avg_days_to_10pct, state_used, cache_built_at, cache_state_cols, actuarial_live_blend_weight, actuarial_live_data_quality, actuarial_live_overlay_applied, enriched_by, enriched_at` (`:722-756`). Atomic promotion: **not evidenced**. Schema/version field: **present**. Authority-claim field `actuarial_source = SOURCE_V6_DB | SOURCE_MISSING` → **PARTIAL**: the constant is named `SOURCE_V6_DB` while the orchestrator's own guidance (`intelligent_orchestrator.py:4295`) and the sibling builder refer to **v7** (`actuarial_database_v7.parquet`), so the provenance label names a generation the surrounding code no longer uses
**Handoff** — Receives from Vanguard / `options_intelligence` (enriched CSV) and `build_packages_from_discovery.py` (DEFERRED blocks); hands to the Execution Decision Engine via patched packages. Join key: `ticker` within `run_id`
**Missing-data handling** — cache not loaded → `{"available": False, "actuarial_source": SOURCE_MISSING, "reason": "Cache not loaded"}` (`:709-720`); lookup raises → `available: False`, `reason: f"lookup_error: {e}"`, **logged at DEBUG only** (`:759-763`) — a swallowed error class; enriched CSV absent → falls back to `vanguard_signals.csv`, which the module's own v1.2 note says has no `layer2__` columns and produced universal no-match (`:50-54`, `:786`); no vanguard row → `NO_VANGUARD_ROW`; zero matches → the orchestrator emits a 10-line diagnostic warning (`:4285-4302`) but does **not** fail the run. §10-compliant? **N**
**Contradictions found here:** CON-613 — the file header (`:3`) declares `Version : v1.6.0` while the module docstring (`:16`) declares `Version : 1.5.0`, and the orchestrator's warning text (`:4295`) requires "v1.5.0+ (9-field `_VANGUARD_STATE_MAP`)". **Three separate version assertions and no runtime `__version__`** for any consumer to check. Separately, `:392-396` still carries a superseded comment ("Actuarial cache key is 4 fields … Old 5-field schema … is REMOVED") immediately above the live 9-field map (`:412`)
**Gaps found here:** GAP-615 — the module is direction-blind yet what it writes (`win_rate_*`, `expected_move_*`) is consumed as directional edge downstream; `_FORCE_CATALYST_NONE` (`:453-457`) permanently pins one of the nine dimensions to a constant, so the "9-field" key is effectively **8 discriminating fields plus a constant** and every state key shares the same `catalyst_proximity`
**Comment/docstring claims audited:** `:38-45` "restored to the correct 6-field schema exactly matching STATE_COLS" → **FALSE as written** (the live map is 9 fields, `:412-463`); the later `:398-407` note supersedes it but the earlier text was never removed. `:790` comment path `"optionsanguard_signals_enriched_{run_id}.csv"` → a mangled path string in a comment (**FALSE** as a path). `:107` "ORCHESTRATOR CALL" section → **HOLDS** (matches `:4269`)
**Confidence in this section:** MEDIUM-HIGH — invocation, state map, fallback chain and output block read directly; the lookup function itself lives outside this file

---

### scripts/apply_external_intel_review_lane.py
**Classification:** ORCHESTRATED · LIVE (356 lines; 4 direction tokens, **31 fallback chains**, 6 write sites)
**Real execution position:** **Evening stage 11**, between Discovery (stage 10) and quality validation — `intelligent_orchestrator.py:4125` calls the wrapper at `:1760`, which `_run(...)`s this script as a subprocess (`:1777-1793`) with `critical=False`
**Task in the process:** Stamps 17 `external_intel_*` fields onto Discovery survivors that appear in the governed catalyst calendar or the macro exposure index, and writes catalyst/macro-only tickers to a **separate advisory artefact** rather than appending them to the core CSV
**Entry points:** `apply_external_intel_review_lane()` (`:222`); `main()` (`:324`) with `--discovery-csv --macro-path --catalyst-calendar --enrichment-path --review-output --report-path`
**Imports (production):** `contracts.macro_enrichment_delta` — `candidate_macro_enrichment_audit, find_macro_enrichment_delta, load_macro_enrichment_delta, merge_macro_enrichment_delta` (`:29-34`) after a `sys.path` insert of the repo root (`:25-27`) · **Imported by:** `tests/test_external_intel_review_lane.py:14` · **Broken/retired imports:** NONE
**Inputs** — `discovery_candidates_ultimate_{run_id}.csv`; `dropbox/inputs/catalyst_calendar_latest.csv` **defaulted inside the function** when the orchestrator passes no `--catalyst-calendar` (`:232`) — **and the orchestrator does not pass one** (`:1777-1793`); `macro_intelligence_latest.json` plus the enrichment delta resolved by `find_macro_enrichment_delta` (`:163`). Fallback chains: `row.get("ticker") or row.get("symbol")` (`:137`, `:241`, `:245`); `catalyst_source_confidence or source_confidence` (`:144`); `catalyst_status or event_status` (`:150`); `catalyst_date or event_window_start` (`:152`); `date_quality or data_quality` (`:154`). All CSVs read `utf-8-sig` (`:91`) — **correct, and the counter-example to GAP-610**
**Logic and algorithms** — best-row-per-ticker selection by confidence (`:141-146`); catalyst/macro merge (`:197-219`); ticker validity screen (`:238-239`); two-pass stamping, existing rows then advisory-only rows (`:244-265`)
**Decision branches** — **all three present, and the ordering is a finding.** `_direction_from_catalyst` (`:117-126`) concatenates `catalyst_direction_bias`, `trade_bias`, `tradability_route` and `expected_impact` into one uppercased string, then tests **PUT first**: `:122` any of `PUT, BEAR, SHORT, NEGATIVE, LOSER, VULNERABLE` → `"PUT"`; `:124` any of `CALL, BULL, LONG, POSITIVE, BENEFICIARY` → `"CALL"`; `:126` else `""`. **The blank arm exists and is correct.** But because four fields are flattened into one haystack and PUT is tested first, a row whose `catalyst_direction_bias` is `LONG_CALL_WATCH` while its `expected_impact` mentions "negative for peers" resolves to **PUT**; and `"SHORT"` being a PUT token means the substring inside e.g. "shortfall" also flips the result. The 17 fields are stamped uniformly for both directions (`:302-321`) with no direction-conditional logic
**Computations and formulas (exact)** — `_safe_float` returns `0.0` on `None`, blank, `TypeError` or `ValueError` (`:81-87`) — used only for the confidence sort at `:144`, so an unparseable confidence sorts last rather than raising; `_US_TICKER_RE = ^[A-Z][A-Z0-9]{0,4}$` (`:57`); `_json_cell` serialises lists/dicts/sets with `sort_keys=True, ensure_ascii=True`, `None → ""` (`:73-78`)
**Models** — NONE
**Outputs** — rewrites `discovery_candidates_ultimate_{run_id}.csv` **in place** with the 17 `external_intel_*` columns appended (`:279`), and writes `external_intel_review_candidates_{run_id}.csv` (`:280`); the orchestrator also captures `qa/external_intel_review_lane_{run_id}.json` (`:341-344`, `:1774`). **No atomic promotion** — `_write_csv` (`:98-103`) opens the live Discovery CSV `"w"` directly, so an interrupted run truncates the core candidate file. Schema/version field: none. **Authority-claim fields:** `external_intel_stage_status ∈ {"ALREADY_IN_DISCOVERY", "ADVISORY_ONLY_NOT_DISCOVERY"}` (`:306-308`), and the returned receipt asserts `"appended_forced_review_rows": 0` and `"core_membership_changed": False` as **hardcoded literals** (`:293`, `:297`) — not computed from what happened. They **HOLD** in fact (advisory rows go only to `advisory_rows`, never to `rows`) but they are assertions, not measurements
**Handoff** — Receives from Discovery (`:4125` runs immediately after `run_discovery` returns at `:4106`); hands to stage 13 quality validation and to `apply_macro_enrichment_to_discovery` (`:4126`). Join key: uppercased `ticker`
**Reconciliation on evidence run:** the Discovery CSV retains **1,527 rows** after this stage; the advisory artefact `discovery/external_intel_review_candidates_20260831_010309.csv` exists at 01:03:11 [MEASURED] — core membership unchanged, **HOLDS**
**Missing-data handling** — missing discovery CSV → orchestrator warns and returns `False` without running (`:1762-1765`); **absent catalyst calendar → `_read_catalyst_calendar` returns `{}` (`:131-132`), so the lane runs on macro evidence alone with no signal that catalyst evidence was unavailable** — `external_intel_source` simply reads `MACRO_ENRICHMENT` instead of `CATALYST+MACRO_ENRICHMENT`; `find_macro_enrichment_delta` returning `None` → base macro used and `macro_enrichment_path = ""` (`:164-165`); non-US-format tickers collected into `invalid_external_tickers` and reported (`:238`, `:291`) — a named exclusion. §10-compliant? **N**
**Contradictions found here:** CON-614 — `_merge_info` (`:197-219`) builds each merged record as `{**m, **c, ...}` (`:208`), so **catalyst keys overwrite macro keys**, then re-asserts the six `macro_*` fields from `m` (`:212-217`) but **not** `direction_bias`. Since `_macro_external_info` always sets `"direction_bias": ""` (`:185`), a ticker present in **both** sources keeps the catalyst direction (intended), but a ticker present **only** in macro is stamped `external_intel_direction_bias = ""` while `external_intel_source = "MACRO_ENRICHMENT"` — indistinguishable in the output from a catalyst row whose direction tokens failed to match at `:126`. **Two different provenances collapse to the same empty cell**
**Gaps found here:** GAP-616 — the receipt fields `core_membership_changed` and `appended_forced_review_rows` are hardcoded (`:293`, `:297`), so a future change to the two-pass structure would leave the receipt asserting the old invariant; the in-place rewrite of the core Discovery CSV without temp-and-replace (`:98-103`, `:279`); `precor_intent` is set to the literal `"WAIT"` on advisory-only rows (`:261`), injecting a pipeline-vocabulary value into a row that never passed Discovery
**Comment/docstring claims audited:** `:3-9` "Discovery is the authority for the macro-agnostic core candidate set… catalyst or macro-only tickers are written to a separate advisory artifact. They cannot be appended to the core CSV, create Packages/Vanguard work, or reactivate a ticker that Discovery dropped." → **HOLDS**, verified structurally: `rows` (written to the core CSV at `:279`) is only ever mutated by `_stamp_row` at `:250`, never appended to; the second loop appends exclusively to `advisory_rows` (`:254-265`). `intelligent_orchestrator.py:1800` "External intel advisory lane failed; core Discovery membership is unchanged" → **HOLDS** (`critical=False`, and a failure before `:279` leaves the CSV untouched)
**Confidence in this section:** HIGH — file read end to end; orchestrator call site verified

---

### scripts/compute_greeks_bs.py
**Classification:** LIBRARY (305 lines) · **carries a UTF-8 BOM** (GAP-610)
**Real execution position:** **Not on the evening/morning critical path.** Imported by `empirical_option_ev.py:61` (`black_scholes_price`) and `scripts/phantom_compute_historical_greeks.py:20` (`compute_greeks_from_row`) — the PHANTOM historical-enrichment lane
**Task in the process:** Recovers an auditable Greek set from archived MarketData EOD option rows whose provider Greeks are null, with no external call
**Entry points:** `compute_greeks_from_row(row, risk_free_rate=0.045)` (`:200`); `black_scholes_price()` (`:48`); `solve_implied_vol()` (`:92`); `compute_greeks()` (`:139`)
**Imports (production):** `math`, `dataclasses`, `typing` only (`:10-12`) — **no numpy, no I/O, no network** · **Imported by:** `empirical_option_ev.py:61`, `scripts/phantom_compute_historical_greeks.py:20` · **Broken/retired imports:** NONE
**Inputs** — a row dict: `side`, `underlying_price` **or** `underlyingPrice` (`:203`), `strike`, `dte`, and one of `mid`/`bid`/`ask`/`last`. Config: `risk_free_rate` default `0.045` (`:200`), re-defaulted to `0.045` if unparseable (`:207-208`), divided by 100 with the flag `risk_free_rate_percent_normalized` if `> 1.0` (`:209-211`) — **a normalisation that records itself**, the correct pattern
**Logic and algorithms** — price-source selection (`:69-89`); a no-arbitrage bound check with a bounded repair (`:230-274`); bisection IV solve with an expanding upper bracket (`:112-136`); closed-form Greeks (`:139-165`)
**Decision branches** — **fully symmetric, and the reference implementation for option maths in this audit.** `black_scholes_price` `:52-56`: `call` → `S·N(d1) − K·e^{−rT}·N(d2)`; `put` → `K·e^{−rT}·N(−d2) − S·N(−d1)`; **anything else raises `ValueError(f"unsupported option side: {side!r}")` (`:56`)** — no coercion, no default. `compute_greeks` `:150-157` mirrors this exactly, raising on the third arm (`:157`). `compute_greeks_from_row` `:216-217` screens the side before computing
**Computations and formulas (exact)** — closed-form Black-Scholes with `d1`/`d2`; bisection IV solve bracketed and expanded (`:112-136`); no-arbitrage bounds with bounded repair (`:230-274`). Exact constants: `risk_free_rate` default `0.045`
**Models** — Black-Scholes analytic, not fitted. Version tag: NOT_ESTABLISHED
**Outputs** — returns a Greek dataclass; **0 write sites** [OBSERVED, extractor] — a pure computation module
**Handoff** — hands computed Greeks to the PHANTOM historical-enrichment lane and to `empirical_option_ev.py`
**Missing-data handling** — unsupported side → **raise** (`:56`, `:157`); unparseable rate → documented default with a self-recording flag (`:207-211`). §10-compliant? **N** — raises, which is stricter
**Contradictions found here:** NONE
**Gaps found here:** GAP-610 (BOM — this file is one of the 42)
**Comment/docstring claims audited:** `:1-3` "Local Black-Scholes Greek computation for PHANTOM historical option rows. MarketData historical EOD option ch[ains lack Greeks]" → **HOLDS**
**Confidence in this section:** HIGH — read at every entry point and every direction branch. **Recorded as a positive case**: the only option-maths module in the audit that refuses an unrecognised side rather than defaulting it

---

### scripts/promote_ev3_barrier_cache.py
**Classification:** LIBRARY (172 lines; 0 fallback chains, 6 write sites)
**Real execution position:** LIBRARY / CLI — imported by 1 module; `__main__` + argparse
**Task in the process:** "Validate and atomically promote an EV3 barrier sidecar to its governed path" (`:1`)
**Entry points:** `__main__`; argparse CLI
**Imports (production):** stdlib + json/pathlib · **Imported by:** 1 module · **Broken/retired imports:** NONE
**Inputs** — an EV3 barrier sidecar; the governed target path
**Logic and algorithms** — validate-then-promote. Decision branches: no direction token — CALL / PUT / other-blank **NOT_APPLICABLE**
**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NONE
**Outputs** — the promoted sidecar at its governed path; 6 write sites with **0 fallback chains** [OBSERVED, extractor]. **Atomic promotion: claimed by the docstring**; the mechanism was not read — recorded as a claim
**Handoff** — hands the promoted cache to the EV3 shadow phase (`AVSHUNTER_EV3_BARRIER_CACHE`, `intelligent_orchestrator.py:445`)
**Missing-data handling** — NOT_ESTABLISHED
**Contradictions found here:** NONE established
**Gaps found here:** GAP-617 (UNTRACED body). Noted as a **candidate positive**: the only `scripts/` file whose docstring claims atomic promotion, and one of two with zero fallback chains
**Comment/docstring claims audited:** `:1` "Validate and atomically promote" → **UNVERIFIED**
**Confidence in this section:** LOW — docstring, import graph and extractor counts only

---

### The remaining 31 `scripts/` files

Each of these now has its **own template section** in
`04_atlas_partI2_scripts_generated.md`, generated by `_tooling/gen_sections.py`
from extracted facts (real `file:line` citations for direction, fallback, write
and raise sites; verbatim docstring; import-graph fan-in) with explicit
`NOT_ESTABLISHED` for everything requiring a read. All are confidence **LOW**
and covered by the blanket UNTRACED row **GAP-618**.

Four of the 31 already carry full findings from earlier lanes despite not having
been read in this pass: `data_contract_validator.py` (CON-358..360,
GAP-340..344), `exit_rules_engine.py` (CON-352..354, GAP-333..335),
`sector_alignment.py` (CON-355..357, GAP-336..339), and
`phantom_gamma_field.py`, which was read directly here and produced **CON-610**
as a positive three-arm direction case.

**Where the risk concentrates, by extractor count:** `macro_quant_packet.py`
(39 fallbacks, 12 importers), `sector_alignment.py` (27), `go_live_uat_audit_watch.py`
(25), `apply_macro_enrichment_to_discovery.py` (25), `backfill_timeseries_into_packages.py`
(20), `core_intel_exporter.py` (19), `avshunter_monetisation_policy.py` (17),
`run_ev3_shadow_phase.py` (16). Two carry authority claims worth testing:
`core_intel_exporter.py` asserts it is **read-only** while showing 3 write sites,
and `go_live_uat_audit_watch.py` asserts it **never changes trading behaviour**
while showing 8.
