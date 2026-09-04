# Part H — Canonical data remainder and macro contracts

_14 files: the eleven `canonical_data/` modules not covered in Part E, plus three
`contracts/` macro modules. Facts from `_tooling/extract_facts.py`
(`facts/canonical_data_contracts_vanguard.json`) with targeted reads on the
atomicity, ledger and refresh-governance seams._

---

### canonical_data/errors.py
**Classification:** ORCHESTRATED (33 lines) · **the most widely imported module in the substrate**
**Real execution position:** LIBRARY — imported by 12 modules [OBSERVED, extractor]; present on every canonical path in both workflows
**Task in the process:** Declares the domain exception vocabulary for the canonical control plane, so that every canonical failure is a named type rather than a bare `Exception`.
**Entry points:** exception classes only
**Imports (production):** stdlib · **Imported by:** 12 modules incl. `registry.py`, `worklist_gate.py`, `lifecycle.py`, `option_liquidity_lifecycle.py`, `discovery_publisher.py` · **Broken/retired imports:** NONE
**Inputs** — NONE. Files read: NONE. External calls: NONE. Config: NONE
**Logic and algorithms** — a class hierarchy rooted at `CanonicalDataError`, with `DatasetValidationError`, `WorklistViolation` (`:28`), `IllegalLifecycleTransition`, `LifecycleConcurrencyError` among the members [OBSERVED]. Decision branches: NONE — CALL / PUT / other-blank all **NOT_APPLICABLE**
**Computations and formulas (exact)** — NONE
**Models** — NONE
**Outputs** — no files. Authority-claim fields: NONE asserted
**Handoff** — the exception types are the contract between the canonical layer and its callers; `scripts/avshunter_options_intelligence.py:8164` and `morning_gate.py:2971` both catch broadly and downgrade or re-raise based on the stage-gating flag rather than on the exception type
**Missing-data handling** — NOT_APPLICABLE. §10-compliant? NOT_APPLICABLE
**Contradictions found here:** NONE
**Gaps found here:** GAP-700 — the module provides a typed exception vocabulary, but the two principal production call sites catch `Exception` broadly (`scripts/avshunter_options_intelligence.py:8164`, `morning_gate.py:2971`) and branch on a feature flag instead of on the type, so the distinction between a validation error, a worklist violation and a concurrency error is discarded at the boundary
**Comment/docstring claims audited:** `:1` "Domain exceptions for the AVSHUNTER canonical data control plane" → **HOLDS**
**Confidence in this section:** HIGH — small file, read in full; fan-in from the import graph

---

### canonical_data/storage.py
**Classification:** ORCHESTRATED (110 lines) · **the atomicity primitive**
**Real execution position:** LIBRARY — imported by 3 modules incl. `market_structure/service.py:13`
**Task in the process:** Content-hashed, atomic filesystem payload storage: every canonical payload is written to a temporary file beside its target and promoted with a single rename, so a partial payload is never visible.
**Entry points:** `class AtomicPayloadStore` — `resolve_path()` (`:29`), `hash_bytes()` (`:38`), `write_bytes()` (`:41`), `write_json()` (`:77`), `promote_parquet()` (`:89`), `verify()` (`:108`)
**Imports (production):** hashlib, os, tempfile, json, pathlib · **Imported by:** 3 modules · **Broken/retired imports:** NONE
**Inputs** — a root directory (`:25`), a relative path and bytes. External calls: filesystem only
**Logic and algorithms** — **the atomic write**: `tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)` (`:60-61`) then `os.replace(temporary, target)` (`:71`) — same-directory temp guarantees the rename is atomic on one filesystem. `verify()` (`:108`) re-hashes a stored payload against an expected hash. Decision branches: NONE — CALL / PUT / other-blank **NOT_APPLICABLE**
**Computations and formulas (exact)** — `hash_bytes = hashlib.sha256(payload).hexdigest()` (`:38-39`) — hex, 64 chars
**Models** — NONE
**Outputs** — payload files under the store root; 6 write sites [OBSERVED, extractor]. **Atomic promotion: YES** (`:60-71`) — this is the one module in the audit that implements the §14.6 write-temp/promote discipline as a reusable primitive. Schema/version field: NOT_APPLICABLE (stores opaque bytes)
**Handoff** — `market_structure/service.py:85` writes content-addressed evidence through it; the option-chain payload writers use it for canonical payloads. Join key: the content hash in the path
**Missing-data handling** — `verify()` returns False on a hash mismatch rather than raising (`:108`). §10-compliant? **N** — boolean, not a typed state
**Contradictions found here:** NONE
**Gaps found here:** GAP-701 — the primitive exists and is correct, but **is not used by the six in-place rewrite sites recorded in GAP-002** (`patch_horizon_fields_into_csv` ×3, `inject_actuarial_into_eil_csv`, `merge_garch_into_enriched`, Trigger Layer pass 2), nor by the non-atomic writers in Parts F and G. The atomicity failure across the pipeline is not a missing capability but an unused one
**Comment/docstring claims audited:** `:1` "Content-hashed, atomic filesystem payload storage" → **HOLDS**, verified at `:60-71`
**Confidence in this section:** HIGH — file read at every entry point

---

### canonical_data/request_ledger.py
**Classification:** ORCHESTRATED (121 lines)
**Real execution position:** LIBRARY — imported by 7 modules
**Task in the process:** Separates **logical** requests (what a stage asked for) from **physical** requests (what actually hit a provider), so that reuse can be demonstrated and API cost attributed. This is the observability counterpart to the dropped-ticker rule.
**Entry points:** `start()` (`:30`), `finish()` (`:60`), `record_blocked()` (`:94`)
**Imports (production):** `.registry`, `.contracts` · **Imported by:** 7 modules · **Broken/retired imports:** NONE
**Inputs** — a `DatasetRequest`; the registry connection
**Logic and algorithms** — a three-state ledger: `start` opens a logical request, `finish` closes it with a `resolution`, `dataset_id`, `physical_request_count` and `retry_count` (`:60-84`), `record_blocked` closes it with `physical_request_count=0` and a reason (`:94-99`). Decision branches: NONE — CALL / PUT / other-blank **NOT_APPLICABLE**
**Computations and formulas (exact)** — validation: `if physical_request_count < 0 or retry_count < 0: raise` (`:71`) — a genuine domain check, not a clamp
**Models** — NONE
**Outputs** — ledger rows in `control_plane.sqlite`. Atomic promotion: N/A (SQLite). Schema/version field: NOT_ESTABLISHED
**Handoff** — records the provider-call accounting that makes "zero Polygon options fallbacks" and "canonical cache hits" measurable claims rather than assertions
**Missing-data handling** — a blocked request is recorded explicitly with a reason (`:94`) rather than omitted — **the correct pattern**: an unserved request is distinguishable from one that never happened. §10-compliant? **N** in vocabulary, correct in substance
**Contradictions found here:** NONE
**Gaps found here:** GAP-702 — the ledger records `physical_request_count`, but no deliverable in the evidence run surfaces it: `09_outputs_catalogue.md` shows no artefact carrying request-count telemetry, so the reuse discipline it measures is recorded in the database and never reported. **NEEDS_MEASUREMENT:** `SELECT resolution, SUM(physical_request_count), COUNT(*) FROM <ledger table> GROUP BY resolution` would quantify actual reuse on the evidence run
**Comment/docstring claims audited:** `:1` "Logical and physical request accounting for CDS observability" → **HOLDS**
**Confidence in this section:** HIGH — all three entry points read

---

### canonical_data/narrow_refresh.py
**Classification:** LIBRARY (62 lines) · **directly answers the read-path governance question**
**Real execution position:** LIBRARY — imported by 1 module
**Task in the process:** Performs a pipeline-owned, single-call refresh of one governed Interpreter bundle. The docstring states the governance rule explicitly: "The Interpreter can request this operation but cannot supply or import a" [provider or fetch path] (`:1-3`).
**Entry points:** `execute_narrow_refresh()` (`:23`), `NarrowRefreshError`
**Imports (production):** canonical contracts/registry · **Imported by:** 1 module · **Broken/retired imports:** NONE
**Inputs** — a bundle identity; 8 fallback chains in 62 lines [OBSERVED, extractor] — dense for its size
**Logic and algorithms** — identity completeness check then a single governed refresh. Decision branches: no direction branch — CALL / PUT / other-blank **NOT_APPLICABLE**
**Computations and formulas (exact)** — NONE
**Models** — NONE
**Outputs** — a refreshed bundle; 0 write sites detected in this module [OBSERVED, extractor], so persistence is the caller's
**Handoff** — the Interpreter requests; the pipeline executes. **This is the correct inversion** of the pattern that Part F found broken elsewhere: the read path may *ask* for fresh data but cannot *fetch* it
**Missing-data handling** — incomplete identity → `NarrowRefreshError("NARROW_REFRESH_IDENTITY_INCOMPLETE")` (`:34`); empty provider response → `NarrowRefreshError("NARROW_REFRESH_EMPTY_RESPONSE")` (`:37`). **Both named and fail-closed.** §10-compliant? **N** in vocabulary, complete in substance
**Contradictions found here:** NONE
**Gaps found here:** NONE. Recorded as a **positive case**: the module enforces the boundary that §7.20 requires of the Interpreter
**Comment/docstring claims audited:** `:1-3` "Pipeline-owned, single-call refresh… The Interpreter can request this operation but cannot supply or import a [fetch path]" → **HOLDS** — the module exposes one function taking an identity, with no provider or callback parameter
**Confidence in this section:** HIGH — small file, read at its raise sites and signature

---

### canonical_data/historical_prices.py
**Classification:** ORCHESTRATED (525 lines)
**Real execution position:** LIBRARY — imported by 3 modules; the canonical equity OHLCV store behind Discovery, packages, Vanguard and GARCH
**Task in the process:** "Canonical, revision-audited daily OHLCV database for CDS-2" (`:1`) — stores daily bars with revision auditing so a later provider correction is recorded rather than silently overwriting history.
**Entry points:** module-level store class and read/write functions
**Imports (production):** sqlite3, `.contracts`, `.errors` · **Imported by:** 3 modules incl. `history_bridge.py` · **Broken/retired imports:** NONE
**Inputs** — daily bars from the fetch path; the historical-price SQLite database (`AVSHUNTER_HISTORICAL_PRICE_DB`, set by `intelligent_orchestrator.py:6128-6131`). 6 fallback chains, 4 write sites [OBSERVED, extractor]
**Logic and algorithms** — revision-audited upsert: a changed bar for an existing date is recorded as a revision rather than an overwrite [INFERRED from the docstring's "revision-audited" and the 4 write sites; **basis: docstring + write-site count, not a full read**; confidence MEDIUM]. Decision branches: no direction branch — **NOT_APPLICABLE**
**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NONE
**Outputs** — rows in the historical-price database. Atomic promotion: N/A (SQLite). Schema/version field: NOT_ESTABLISHED
**Handoff** — receives write-through from `polygon_data_fetcher.py:178-185` (`provider="POLYGON"`, `source_kind="POLYGON_DATA_FETCHER"`); hands bars to Discovery, packages, Vanguard, GARCH
**Missing-data handling** — NOT_ESTABLISHED in detail; `DEFAULT_HISTORY_MAX_STALENESS_DAYS` is exported from `history_bridge.py` and consumed by `scripts/data_contract_validator.py:39-42`
**Contradictions found here:** NONE established
**Gaps found here:** GAP-703 (UNTRACED — the revision-audit mechanism is asserted by the docstring and not verified here); this is the module most likely to hold further IDENTITY findings per GAP-502
**Comment/docstring claims audited:** `:1` "revision-audited" → **UNVERIFIED** — recorded as a claim, not a verdict
**Confidence in this section:** LOW-MEDIUM — docstring, imports, consumers and write-site count established; the revision logic was not read

---

### canonical_data/history_bridge.py
**Classification:** ORCHESTRATED (207 lines)
**Real execution position:** LIBRARY — imported by 7 modules; called from `polygon_data_fetcher.py:178` inside the fetch path
**Task in the process:** "Disabled-by-default bridge between legacy consumers and CDS-2 prices" (`:1`) — lets a legacy fetcher write through into the canonical store without the legacy caller knowing about CDS.
**Entry points:** `write_through_fetched_history()` (`:121`), `DEFAULT_HISTORY_MAX_STALENESS_DAYS`
**Imports (production):** `.historical_prices`, `.feature_flags`, `.contracts` · **Imported by:** 7 modules incl. `polygon_data_fetcher.py` (function-local import at `:178`), `scripts/data_contract_validator.py:39` · **Broken/retired imports:** NONE
**Inputs** — a fetched DataFrame plus provider/source/run identity; the feature flags
**Logic and algorithms** — **the disabled-by-default gate**: `if not flags.enabled or not flags.write_through: return` (`:133`) — a no-op unless both canonical flags are on. Decision branches: no direction branch — **NOT_APPLICABLE**
**Computations and formulas (exact)** — `DEFAULT_HISTORY_MAX_STALENESS_DAYS` — the freshness constant that `scripts/data_contract_validator.py:39-43` imports and silently replaces with the literal `5` when this module is unimportable (GAP-342)
**Models** — NONE
**Outputs** — writes through into `historical_prices`; 2 write sites [OBSERVED, extractor]
**Handoff** — receives from `polygon_data_fetcher.py:178-185`; hands to `historical_prices.py`. **Note the ordering guarantee**: the bridge call precedes `return df` at `polygon_data_fetcher.py:187`, so the canonical write happens before any caller consumes the data
**Missing-data handling** — both flags off → silent no-op (`:133`), which is the documented behaviour. **However**, `polygon_data_fetcher.py:178-185` does **not** wrap the bridge call, so a bridge failure propagates into that file's outer `except Exception` at `:192` and is reported as a *fetch* error — a successful API call can be recorded as `failed` (Part G). §10-compliant? **N**
**Contradictions found here:** NONE
**Gaps found here:** GAP-704 — the staleness constant this module owns has a silent literal fallback in its consumer (`scripts/data_contract_validator.py:39-42`), so the freshness rule has two possible values with no output marker recording which applied. Cross-referenced to GAP-342
**Comment/docstring claims audited:** `:1` "Disabled-by-default bridge" → **HOLDS** (`:133`). `polygon_data_fetcher.py:174-177` "The bridge is a no-op unless both canonical data and write-through flags are explicitly enabled" → **HOLDS**, though in production `intelligent_orchestrator.py:6119-6120` sets both, so the no-op never applies on an orchestrated run
**Confidence in this section:** MEDIUM-HIGH — the gate and the call-site ordering read directly

---

### canonical_data/intraday_bars.py
**Classification:** ORCHESTRATED (169 lines)
**Real execution position:** LIBRARY — imported by 3 modules; consults `LifecycleManager` (`:18`)
**Task in the process:** "Immutable canonical one-minute bars and missing-interval resolver" (`:1`) — supplies the minute bars that `market_structure/` consumes on the morning path, fetching only intervals not already stored.
**Entry points:** module-level resolver class/functions
**Imports (production):** `.lifecycle` (`:18`), `.registry`, `.storage`, `.contracts` · **Imported by:** 3 modules · **Broken/retired imports:** NONE
**Inputs** — ticker, session, interval range. 1 fallback chain, 4 write sites [OBSERVED, extractor]
**Logic and algorithms** — missing-interval resolution: compute which intervals are absent and fetch only those; fetch suppression via `LifecycleManager` (`:18`). Decision branches: no direction branch — **NOT_APPLICABLE**
**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NONE
**Outputs** — canonical minute-bar payloads. Atomic promotion: **inherited** from `storage.py` if written through it — NOT_ESTABLISHED which of the 4 write sites use the atomic store. Schema/version field: NOT_ESTABLISHED
**Handoff** — hands bars to `market_structure/service.calculate_market_structure_evidence` via `morning_gate.py:3291`; that consumer requires `{timestamp_utc, high, low, close, volume}` and optionally `session_segment` (`market_structure/profile.py:45-49`)
**Missing-data handling** — the "missing-interval" design means a partial session is representable; `market_structure/profile.py` then labels an inadequate profile `INSUFFICIENT_DATA`. §10-compliant? NOT_ESTABLISHED here
**Contradictions found here:** NONE established
**Gaps found here:** GAP-705 — the docstring claims the bars are **immutable**; whether the 4 write sites enforce that (append-only vs overwrite) was **not verified**. Relevant because `market_structure/profile.py:67` stamps `ONE_MINUTE_ESTIMATED` without checking the interval it was given (GAP-602), so the two modules jointly assert a minute-bar provenance neither validates
**Comment/docstring claims audited:** `:1` "Immutable canonical one-minute bars" → **UNVERIFIED**
**Confidence in this section:** LOW-MEDIUM — role, imports, consumer contract established; write semantics not read

---

### canonical_data/daily_adapter.py
**Classification:** ORCHESTRATED (107 lines)
**Real execution position:** LIBRARY — imported by 1 module
**Task in the process:** "Incremental Polygon boundary-range adapter for canonical daily history" (`:1`) — computes the boundary range still missing from the canonical daily store so only that range is fetched.
**Entry points:** module-level adapter functions
**Imports (production):** `.historical_prices`, `.contracts` · **Imported by:** 1 module · **Broken/retired imports:** NONE
**Inputs** — a requested date range and the store's existing coverage. 0 fallback chains, 0 write sites [OBSERVED, extractor] — a pure computation module
**Logic and algorithms** — boundary-range arithmetic: given requested `[start, end]` and stored coverage, emit the missing prefix/suffix. Decision branches: no direction branch — **NOT_APPLICABLE**
**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NONE
**Outputs** — returns ranges; **writes nothing** (0 write sites, confirming the pure-function role)
**Handoff** — hands a fetch range to the equity acquisition path; implements §7.2's "fetch only missing ranges"
**Missing-data handling** — NOT_ESTABLISHED
**Contradictions found here:** NONE established
**Gaps found here:** GAP-706 (UNTRACED body)
**Comment/docstring claims audited:** `:1` "Incremental… boundary-range adapter" → **PARTIAL** — consistent with 0 write sites and a single importer, but the arithmetic was not read
**Confidence in this section:** LOW — docstring, import graph and write-site count only

---

### canonical_data/gateway.py
**Classification:** ORCHESTRATED (70 lines)
**Real execution position:** LIBRARY — imported by 4 modules; consults `LifecycleManager` (`:8`)
**Task in the process:** "Resolver-only CDS gateway skeleton; provider adapters arrive after CDS-1" (`:1`) — a deliberately incomplete façade that resolves from canonical storage and does **not** itself call a provider.
**Entry points:** gateway class
**Imports (production):** `.lifecycle` (`:8`), `.feature_flags`, `.registry` · **Imported by:** 4 modules · **Broken/retired imports:** NONE
**Inputs** — a dataset request; the flags. `:40` reads `self.flags.stage_gating_enforced` [OBSERVED]
**Logic and algorithms** — resolve-or-refuse. Decision branches: no direction branch — **NOT_APPLICABLE**
**Computations and formulas (exact)** — NONE
**Models** — NONE
**Outputs** — 0 write sites [OBSERVED, extractor] — consistent with "resolver-only"
**Handoff** — hands resolved datasets to callers; refuses rather than fetching
**Missing-data handling** — branches on `stage_gating_enforced` (`:40`), so an unresolvable request either raises or degrades depending on the flag — which `intelligent_orchestrator.py:6127` sets to `1` in production, making it fail-closed on an orchestrated run
**Contradictions found here:** NONE
**Gaps found here:** NONE. Recorded as a **positive case**: the docstring declares the module a skeleton and the 0 write sites confirm it has not silently grown a fetch path
**Comment/docstring claims audited:** `:1` "Resolver-only… provider adapters arrive after CDS-1" → **HOLDS** — no provider call and no write site
**Confidence in this section:** MEDIUM-HIGH

---

### canonical_data/stage_publisher.py
**Classification:** ORCHESTRATED (303 lines)
**Real execution position:** LIBRARY — imported by 1 module
**Task in the process:** "Production stage-worklist publication helpers. CDS-3 requires the worklist to be persisted before a stage can [run]" (`:1-3`) — the persistence half of the worklist discipline that `worklist_gate.py` validates.
**Entry points:** publication helper functions
**Imports (production):** `.registry`, `.errors`, `.contracts` · **Imported by:** 1 module · **Broken/retired imports:** NONE
**Inputs** — a stage worklist. 1 fallback chain, 2 write sites [OBSERVED, extractor]
**Logic and algorithms** — persist-then-authorise: the worklist must exist in the control plane before the stage is permitted to consume it. Decision branches: no direction branch — **NOT_APPLICABLE**
**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NONE
**Outputs** — worklist rows in `control_plane.sqlite`. Atomic promotion: N/A (SQLite). Schema/version field: NOT_ESTABLISHED
**Handoff** — pairs with `worklist_gate.filter_rows_to_worklist`, called at `intelligent_orchestrator.py:2209`, which raises `WorklistViolation("Packages worklist is empty or was not published")` (`:2228`) — **the enforcement that makes this module load-bearing**
**Missing-data handling** — an unpublished worklist causes the consumer to raise (`intelligent_orchestrator.py:2228`), i.e. fail-closed. §10-compliant? **N** — raises
**Contradictions found here:** NONE
**Gaps found here:** NONE established
**Comment/docstring claims audited:** `:1-3` "CDS-3 requires the worklist to be persisted before a stage can run" → **HOLDS**, enforced at `intelligent_orchestrator.py:2228`
**Confidence in this section:** MEDIUM — role and enforcement pairing established; body not read in full

---

### canonical_data/contract_reference.py
**Classification:** ORCHESTRATED (42 lines)
**Real execution position:** LIBRARY — imported by 2 modules
**Task in the process:** "Provider-independent option contract reference rules. MarketData chains normally carry `contractMultiplier`…" (`:1-3`) — supplies the multiplier and reference conventions so contract economics do not depend on a provider field being present.
**Entry points:** module-level reference functions/constants
**Imports (production):** stdlib · **Imported by:** 2 modules · **Broken/retired imports:** NONE
**Inputs** — a contract record. 0 fallback chains, 1 write site [OBSERVED, extractor]
**Logic and algorithms** — reference-rule lookup with a provider-independent default for the multiplier. Decision branches: no direction branch — **NOT_APPLICABLE**
**Computations and formulas (exact)** — NOT_ESTABLISHED; the standard equity-option multiplier of 100 is the expected constant but was **not read**
**Models** — NONE
**Outputs** — reference values consumed by contract economics
**Handoff** — feeds the multiplier into premium and monetisability arithmetic, which §7.13 requires to carry `multiplier` as part of contract identity
**Missing-data handling** — the module exists precisely to supply a default when `contractMultiplier` is absent — i.e. a **deliberate, documented** default rather than a silent one. §10-compliant? NOT_ESTABLISHED
**Contradictions found here:** NONE established
**Gaps found here:** GAP-707 (UNTRACED — the multiplier default value and its application were not read; relevant because a wrong multiplier scales every premium and monetisability figure)
**Comment/docstring claims audited:** `:1` "Provider-independent option contract reference rules" → **PARTIAL** (plausible from the docstring and 2 importers; unverified)
**Confidence in this section:** LOW

---

### contracts/bond_macro_contract.py
**Classification:** ORCHESTRATED (89 lines) · **26 fallback chains in 89 lines — the highest fallback density in the audit**
**Real execution position:** LIBRARY — imported by 2 modules
**Task in the process:** "Forward-compatible adapter for `bond_macro_state.json` sidecars" (`:1`) — reads the bond/macro sidecar tolerantly so a schema change upstream degrades rather than breaks.
**Entry points:** adapter functions
**Imports (production):** stdlib/json · **Imported by:** 2 modules · **Broken/retired imports:** NONE
**Inputs** — `bond_macro_state.json`. **26 fallback chains** [OBSERVED, extractor] — the "forward-compatible" design expressed as `.get(x, default)` and `a or b` throughout
**Logic and algorithms** — tolerant field extraction. Decision branches: **no direction token anywhere** (0 hits) — CALL / PUT / other-blank all **NOT_APPLICABLE**, which is the correct posture for a macro sidecar under §3
**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NONE
**Outputs** — 0 write sites [OBSERVED, extractor] — a pure reader
**Handoff** — hands bond/macro context to its two importers as advisory input
**Missing-data handling** — 26 fallback chains means nearly every field has a default. **This is the design intent ("forward-compatible") and simultaneously the §10 risk**: with that density, a wholly-absent sidecar and a fully-populated one can produce structurally identical outputs. §10-compliant? **N**
**Contradictions found here:** NONE established
**Gaps found here:** GAP-708 — 26 fallbacks in 89 lines with 0 write sites and no data-state output field: nothing downstream can distinguish "sidecar read successfully" from "sidecar absent, all defaults applied". Relevant to the morning-gate question of whether any macro read can block a ticker — **it cannot, but neither can a consumer tell that the macro context is empty**
**Comment/docstring claims audited:** `:1` "Forward-compatible adapter" → **HOLDS** as a description of the fallback density; the cost is recorded as GAP-708
**Confidence in this section:** MEDIUM — docstring, fallback density, write-site count and direction-token absence all established by extraction; individual fields not read

---

### contracts/macro_enrichment_delta.py
**Classification:** ORCHESTRATED (808 lines)
**Real execution position:** Evening — `find_macro_enrichment_delta` / `load_macro_enrichment_delta` / `merge_macro_enrichment_delta` / `candidate_macro_enrichment_audit` imported by `scripts/apply_external_intel_review_lane.py:29-34`; the merge runs in the Discovery-enrichment window (evening stages 11–12)
**Task in the process:** "Additive macro enrichment delta support. The enrichment packet is a narrative/event overlay for an existing m[acro contract]" (`:1-4`) — locates the newest enrichment delta, validates it and merges it additively into the macro contract without replacing the base.
**Entry points:** `find_macro_enrichment_delta()`, `load_macro_enrichment_delta()`, `merge_macro_enrichment_delta()`, `candidate_macro_enrichment_audit()`
**Imports (production):** json, pathlib, datetime · **Imported by:** `scripts/apply_external_intel_review_lane.py`, `intelligent_orchestrator.py` (via the enrichment stage) · **Broken/retired imports:** NONE
**Inputs** — `avshunter_macro_enrichment_delta*.json` matched by the glob at `:97` [OBSERVED]. **This is the glob that the news-terminal lane's output satisfies** (Part G): `news_terminal/news_terminal_outputs.py:668-692` writes exactly that filename pattern
**Logic and algorithms** — newest-delta discovery by the `:97` glob, then an additive merge. Decision branches: NOT_ESTABLISHED in detail; the module is macro-level and should carry no per-ticker direction decision
**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NONE
**Outputs** — a merged macro contract plus an audit structure; consumed by the external-intel lane and the Discovery enrichment
**Handoff** — receives the delta file; hands the merged contract to `scripts/apply_macro_enrichment_to_discovery.py` (evening stage 12). Join key: filename date
**Missing-data handling** — `find_macro_enrichment_delta` returning `None` → the caller uses the base macro and sets `macro_enrichment_path = ""` (`scripts/apply_external_intel_review_lane.py:164-165`), which **collapses two provenances into one empty cell** (recorded in that file's own section)
**Contradictions found here:** the `:97` glob is the ingestion point for a file written by a lane that stamps every row `execution_permission = NONE_NEWS_TERMINAL_ONLY` and `capital_grade = NO`. Neither key is checked here or by any orchestrator reader — cross-referenced to the Part G finding on `news_terminal_outputs.py`
**Gaps found here:** GAP-709 — the module ingests an externally-written file by glob with no provenance or permission check on the writer
**Comment/docstring claims audited:** `:1-4` "Additive… overlay for an existing macro contract" → **PARTIAL** — additive per the docstring and the function name `merge_…`, but the merge semantics were not read
**Confidence in this section:** MEDIUM — the glob, the importers and the news-terminal ingestion path established; the 808-line body not read

---

### contracts/lab_evidence_overlay.py
**Classification:** LAB (203 lines)
**Real execution position:** Read path — imported by 6 modules; part of the Lab's display layer
**Task in the process:** "Allow-listed, non-authoritative Intelligence Lab MSI overlays" (`:1`) — supplies additional MSI display fields to the Lab through an explicit allow-list, so an overlay cannot introduce a new authority.
**Entry points:** overlay functions
**Imports (production):** canonical/contract helpers · **Imported by:** 6 modules · **Broken/retired imports:** NONE
**Inputs** — a governed book row plus MSI evidence overlays. 3 fallback chains [OBSERVED, extractor]
**Logic and algorithms** — a **two-set allow/protect design**, `contracts/lab_evidence_overlay.py:33-64`:
- `OVERLAY_ALLOWED_FIELDS` (`:51-53`) — the union of `CURRENT_QUOTE_FIELDS`, `UNDERLYING_FIELDS`, `STRUCTURE_FIELDS`, `ASSESSMENT_FIELDS`: **69 fields** an overlay may set
- `PROTECTED_AUTHORITY_FIELDS` (`:55-64`) — **25 fields** an overlay may never set, including `governed_direction`, `final_direction`, `direction`, `dir_calc_version`, `governed_direction_record_sha256`, `thesis_state`, `liquidity_state`, `morning_transition_state`, `olm_guard_disposition`, `final_action`, `capital_permission`, `lab_verdict`
- `validate_overlay` (`:82-103`) rejects any unknown field with `OverlayValidationError("OVERLAY_FIELD_NOT_ALLOWED:" + …)` (`:103`)
- `apply_latest_compatible_overlays` (`:156-196`) applies a field **only** if `field in OVERLAY_ALLOWED_FIELDS` (`:189`)

**Decision branches** — the direction tokens flagged by the extractor are the **protection list, not a decision**. **CALL path / PUT path / other-blank path: NOT_APPLICABLE** — this module makes no directional decision; it forbids overlays from touching direction at all. The single direction-adjacent field in the allowed set is `ms_direction_relationship` (`:33`), which is the market-structure *relationship* label (`ALIGNED` / `CONFLICTING` / `NEUTRAL` / `INSUFFICIENT_DATA`) produced by `market_structure/lifecycle.py:19-25` — itself the reference implementation with all three arms named
**Computations and formulas (exact)** — latest-overlay selection by `created_utc` within `(run_id, ticker, bundle_id)` (`:165-170`), then `max(compatible, key=lambda item: item["created_utc"])` (`:188`)
**Models** — NONE
**Outputs** — overlay fields merged into the row, plus lineage stamps `applied_overlay_id` and `applied_overlay_bundle_id` (`:191-192`). Authority-claim: docstring `:1` "Allow-listed, non-authoritative" → **HOLDS**, verified two ways:
1. The two sets are **disjoint** — `OVERLAY_ALLOWED_FIELDS & PROTECTED_AUTHORITY_FIELDS` is empty (69 allowed, 25 protected, zero overlap) [MEASURED, by importing both frozensets], so the protection cannot be defeated by a field appearing in both.
2. The application loop filters on the allowed set (`:189`), so a protected field cannot be written even if an overlay smuggled one past validation.
**Handoff** — receives the governed book and the overlay file; hands display fields to the Lab. Join key: **`(run_id, ticker, bundle_id)`** — and note `:183-188`: **"An overlay without exact bundle continuity is not compatible. Never fall back to run+ticker because contract identity can change within a run while the ticker remains the same."** An overlay with no `bundle_id` match is dropped rather than approximated
**Missing-data handling** — missing `bundle_id` on the row → `compatible = []`, no overlay applied (`:183-184`); no matching overlay → row passes through unchanged; unknown field → raise (`:103`). §10-compliant? **N** in vocabulary, but every path is explicit
**Contradictions found here:** NONE
**Gaps found here:** NONE
**Comment/docstring claims audited:** `:1` "Allow-listed, non-authoritative Intelligence Lab MSI overlays" → **HOLDS**. `:160` "Apply only compatible observation fields; book authority always wins" → **HOLDS** (`:189`). `:184-186` the stated reason for refusing a run+ticker fallback → **HOLDS**, and is the correct treatment of the identity problem that GAP-352 found unhandled in `tools/msi_reconcile.py:70-71`
**Confidence in this section:** HIGH — allow/protect sets, validation, application loop and join-key discipline all read; disjointness measured

> **Recorded as a positive case.** This is the strongest read-path module in the
> audit: it is the only place where the field-authority problem quantified in
> `06_field_authority_summary.md` §1 is solved structurally, by naming the 25
> fields no display layer may write and enforcing that with a disjoint
> allow-list. Contrast the confirmed `trigger_quality ← trigger_score` bridge
> elsewhere on the same read path (§11.5).
