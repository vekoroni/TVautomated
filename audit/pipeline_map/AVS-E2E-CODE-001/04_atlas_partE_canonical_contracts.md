# Part E — Canonical data substrate and contracts

_Lane E was terminated by a session limit before producing output. These sections
were written directly in the main session as a **targeted pass** over the
load-bearing identity modules, not a complete pass over all 31 files in the lane.
The files still undescribed are listed in `00_README.md` §3._

Claim tags: **OBSERVED** (read in code), **MEASURED** (from a run artefact or DB
query), **INFERRED** (basis and confidence stated).

---

### canonical_data/registry.py
**Classification:** LIBRARY (ORCHESTRATED — reached from `intelligent_orchestrator.py` and from `scripts/avshunter_options_intelligence.py`)
**Real execution position:** LIBRARY — constructed at evening stage 18 (`scripts/avshunter_options_intelligence.py:8088-8092`) and stage 3 of the morning path (`morning_gate.py:2808-2811`), plus every canonical service
**Task in the process:** Owns `data/canonical/control_plane.sqlite`. It is the single registrar of dataset identity: every canonical data object (option chain, live option quote, equity bars, market-structure evidence) is recorded here with a content hash, a scope fingerprint, a provider and a session date, so that later stages can reuse an existing object instead of re-fetching it and can prove which object a calculation consumed.
**Entry points:** `class CanonicalRegistry` — `initialise()`, `connection()`, `register_run()`, `register_dataset()`, `get_dataset()`
**Imports (production):** `.contracts`, `.errors` · **Imported by:** 16 modules (`02_import_graph.json`) including `option_liquidity_lifecycle.py`, `option_chain_store.py`, `market_observation_resolver.py`, `discovery_publisher.py`, `market_structure/service.py` · **Broken/retired imports:** NONE

**Inputs**
- Files/tables read: `data/canonical/control_plane.sqlite` — tables `dataset_registry`, `run_registry`, and (via the OLM module) `option_thesis_events`, `option_contract_observations`, `option_contract_selection_events`
- Upstream fields consumed: a `DatasetRecord` supplied by the caller; no field defaulting inside the registry
- External calls: SQLite only. No provider is ever called from this module [OBSERVED]
- Config/policy read: NONE — the database path is a constructor argument

**Logic and algorithms**
- **Content-addressed immutability with provenance tolerance**, `canonical_data/registry.py:228-244`. On a repeat `register_dataset` for an existing `dataset_id`: exact equality returns idempotently (`:232-233`); equality *modulo* `source_run_id` also returns idempotently, preserving the original registering run (`:241-242`); anything else raises `DatasetValidationError(f"dataset_id {…} is immutable and already registered")` (`:243-244`).
- Decision branches: no direction branch. CALL path / PUT path / other-blank path: **NOT_APPLICABLE** — the registry is direction-agnostic and stores no direction field.

**Computations and formulas (exact)**
- `content_hash` = `hashlib.sha256(encoded).hexdigest()` over the canonical encoding (`canonical_data/contracts.py:136`) — hex, 64 chars, no rounding
- `dataset_id` is supplied by the caller, not computed here; callers derive it by SHA-256 over an identity string (e.g. `morning_gate.py:2674-2676` `LIVE_OPTION|{ticker}|{contract}|{quote_as_of}|{content_hash}`; `market_structure/service.py:87` `MARKET_STRUCTURE|ticker|session|content_hash`)

**Models** — NONE

**Outputs**
- Files/tables written: `dataset_registry`, `run_registry` rows in `control_plane.sqlite`. Atomic promotion: **N/A** (SQLite transaction per `connection()` context). Schema/version field: **yes** — `schema_version` is a column on `dataset_registry`
- Fields carrying authority claims: `dataset_id` as a content identity — **HOLDS**, enforced by the raise at `:243`; `source_run_id` as first-registrar provenance — **HOLDS**, explicitly preserved at `:241`

**Handoff**
- Receives from: every canonical writer (option chain store, live-quote writers, market-structure service, discovery publisher)
- Hands to: every canonical reader, by `dataset_id`
- Reconciliation on evidence run: **UNDETERMINED** for the registry itself; the OLM tables it hosts were measured — 1,507 / 1,021 / 1,021 rows [MEASURED, `10_cross_verification.md` id 13]

**Missing-data handling**
- Unknown `dataset_id` on read → `get_dataset` returns `None`, and each caller decides (e.g. `option_liquidity_lifecycle.py:748-749` raises `unknown source_dataset_id`) [OBSERVED]. §10-compliant? **N** — `None` is returned rather than a typed missing-data state

**Contradictions found here:** CON-500
**Gaps found here:** NONE in this file
**Comment/docstring claims audited:** `:234-240` "Dataset IDs are content identities, while `source_run_id` records the run that first registered that immutable object. A later run may legitimately observe and reuse the identical dataset." → **HOLDS**, and it is the reason the observed production error is meaningful rather than benign — see CON-500
**Confidence in this section:** HIGH — immutability block read directly; fan-in from the import graph

---

### canonical_data/feature_flags.py
**Classification:** LIBRARY (ORCHESTRATED)
**Real execution position:** LIBRARY — read at evening stage 18 and by `morning_gate.py:2805`; defaults are forced by `intelligent_orchestrator.py::configure_cds_runtime_for_orchestrator` (`:6109-6131`) for **both** `--evening` and `--morning`
**Task in the process:** Decides whether the canonical data system is active at all, whether it writes through, and whether a stage failure is fatal.
**Entry points:** `CanonicalFeatureFlags.from_environment()`
**Imports (production):** stdlib only · **Imported by:** 8 modules · **Broken/retired imports:** NONE

**Inputs**
- Config/policy read: five environment variables, every one defaulting **off** in code (`canonical_data/feature_flags.py:25-29`, `:39-47`): `AVSHUNTER_CANONICAL_DATA_ENABLED`, `AVSHUNTER_CANONICAL_WRITE_THROUGH`, `AVSHUNTER_STAGE_GATING_ENFORCED`, `AVSHUNTER_CANONICAL_OFFLINE_REPLAY`, `AVSHUNTER_CDS2_OHLCV_MODE` (validated to `OFF|SHADOW|ACTIVE`, invalid → `OFF`, `:36-38`)

**Logic and algorithms**
- `_as_bool` accepts `{1,true,yes,on}` as true and `{0,false,no,off,""}` as false; **any other string returns the default** (`:10-18`) [OBSERVED]
- Decision branches: no direction branch — **NOT_APPLICABLE**

**Computations and formulas (exact)** — NONE beyond the boolean parse

**Models** — NONE

**Outputs** — a frozen dataclass; writes nothing. Authority-claim field: the docstring `:23` "Controls CDS activation. Every switch defaults to off." — **HOLDS for the code**, and is **misleading in production**: the orchestrator sets `AVSHUNTER_CANONICAL_DATA_ENABLED=1`, `AVSHUNTER_CANONICAL_WRITE_THROUGH=1`, `AVSHUNTER_CDS2_OHLCV_MODE=ACTIVE` and `AVSHUNTER_STAGE_GATING_ENFORCED=1` via `setdefault` for every production run (`intelligent_orchestrator.py:6119-6127`) [OBSERVED]. See GAP-500.

**Handoff** — receives the process environment; hands flags to the registry constructors and to the fail-closed branches in `scripts/avshunter_options_intelligence.py:8109`, `:8167` and `morning_gate.py:2975`
**Missing-data handling** — unset variable → documented default. §10-compliant? **NOT_APPLICABLE** (configuration, not data)
**Contradictions found here:** NONE
**Gaps found here:** GAP-500
**Comment/docstring claims audited:** as above → **PARTIAL**
**Confidence in this section:** HIGH — file read end to end

---

### canonical_data/worklist_gate.py
**Classification:** LIBRARY (ORCHESTRATED)
**Real execution position:** LIBRARY — `reconcile_stage_outcomes` called from `canonical_data/discovery_publisher.py:83` (evening stage 9 publication); `filter_rows_to_worklist` called from `intelligent_orchestrator.py:2209` in `prepare_cds3_governed_package_input` (evening stage 9)
**Task in the process:** Enforces the dropped-ticker rule at the Discovery→Packages boundary: a ticker that Discovery dropped must not generate downstream work or API cost, and the stage must account for every input ticker exactly once.
**Entry points:** `reconcile_stage_outcomes()`, `filter_rows_to_worklist()`, `StageOutcomeReconciliation`
**Imports (production):** `.errors` · **Imported by:** `discovery_publisher.py`, `canonical_data/__init__.py`, `intelligent_orchestrator.py` · **Broken/retired imports:** NONE

**Inputs**
- Upstream fields consumed: `ticker` only, normalised by `_ticker()` = `str(value or "").strip().upper()` (`:14-15`)
- External calls: NONE

**Logic and algorithms**
- `_unique` raises `WorklistViolation` on a blank ticker (`:21`) and on duplicate outcomes (`:23`) [OBSERVED]
- `StageOutcomeReconciliation.reconciled` = `set(survived) | set(dropped) | set(failed) == set(input_tickers)` (`:35-37`) — this is the §14.5 invariant expressed in code
- `reconcile_stage_outcomes` raises `WorklistViolation` when the reconciliation fails (`:76`)
- `filter_rows_to_worklist` raises when a row is outside the authorised worklist (`:102`)
- Decision branches: no direction branch — **NOT_APPLICABLE**

**Computations and formulas (exact)** — set algebra only; `counts()` (`:40-41`) returns the four cardinalities

**Models** — NONE

**Outputs** — returns `StageOutcomeReconciliation`; writes nothing. Authority-claim: the module is the enforcement point for §8's dropped-ticker rule — **HOLDS at the Discovery→Packages boundary**, and is the mechanism behind a measured result: **zero tickers appear at any downstream stage that were not present upstream, across all eight measured boundaries** [MEASURED, `05_handoff_matrix.md`]

**Handoff** — receives Discovery lifecycle rows; hands an authorised worklist to package construction. Join key: `ticker`
**Reconciliation on evidence run:** Discovery 1,527 → Vanguard 1,481 (46 dropped, 0 arrivals); Vanguard → Options 1,248 (233 dropped, 0 arrivals) [MEASURED] — **HOLDS**
**Missing-data handling** — blank ticker → raise (`:21`), i.e. fail-closed. §10-compliant? **N** — raises rather than emitting a typed state, which is the stricter behaviour
**Contradictions found here:** NONE
**Gaps found here:** GAP-501
**Comment/docstring claims audited:** NONE asserted
**Confidence in this section:** HIGH — file read end to end; both call sites verified; corroborated by measurement

---

### canonical_data/lifecycle.py
**Classification:** LIBRARY (ORCHESTRATED)
**Real execution position:** LIBRARY — `LifecycleManager` used by `gateway.py:8`, `intraday_bars.py:18`, `market_observation_resolver.py:23`, `option_chain_store.py:26`, `discovery_publisher.py:13`
**Task in the process:** Owns the **ticker** lifecycle — whether a ticker is still active for a given stage — and is consulted to suppress fetches for tickers that have been dropped. This is a different concept from the **option thesis** lifecycle in `canonical_data/option_liquidity_lifecycle.py`.
**Entry points:** `class LifecycleManager`, `class LifecycleState`
**Imports (production):** `.contracts`, `.errors` (`IllegalLifecycleTransition`, `LifecycleConcurrencyError`), `.registry` · **Imported by:** 5 canonical modules · **Broken/retired imports:** NONE

**Inputs**
- Files/tables read: the lifecycle table in `control_plane.sqlite`
- External calls: SQLite only

**Logic and algorithms**
- `LifecycleState` enum: `ACTIVE_DISCOVERY`, `ACTIVE_CORE`, `ACTIVE_OPTIONS`, `DEFERRED_CURRENT_RUN`, `DROPPED_STAGE`, `DROPPED_TERMINAL_DATA`, `DROPPED_TERMINAL_LOGIC` (`:17-` and the consumer at `discovery_publisher.py:101-120`) [OBSERVED]
- Illegal transitions raise `IllegalLifecycleTransition`; stale-version writes raise `LifecycleConcurrencyError` — a versioned state machine, unlike the option thesis lifecycle which has **no** supersession path [MEASURED absent, `10_cross_verification.md` id 14]
- Decision branches: no direction branch — **NOT_APPLICABLE**

**Computations and formulas (exact)** — state-transition table; no arithmetic

**Models** — NONE

**Outputs** — lifecycle rows in `control_plane.sqlite`. Schema/version field: a `version` column participates in the concurrency check. Authority-claim: docstring `:1` "Ticker lifecycle and stage-worklist authority for fetch suppression" — **HOLDS**; it is consulted by the option chain store and the market-observation resolver before any provider call

**Handoff** — receives stage outcomes from `discovery_publisher.py`; hands fetch-suppression decisions to the acquisition modules. Join key: `ticker` (+ run)
**Missing-data handling** — no prior state → the publisher sets an initial state (`discovery_publisher.py:101-112`); an unexpected `lifecycle_state` string raises via the `LifecycleState(...)` constructor (`discovery_publisher.py:112`). §10-compliant? **N** — a private vocabulary, but every state is named
**Contradictions found here:** CON-501
**Gaps found here:** NONE
**Comment/docstring claims audited:** as above → **HOLDS**
**Confidence in this section:** MEDIUM-HIGH — enum, docstring and all five consumer call sites read; the transition table itself sampled rather than read exhaustively

---

### canonical_data/discovery_publisher.py
**Classification:** ORCHESTRATED
**Real execution position:** Evening stage 9 area — invoked from `intelligent_orchestrator.py::publish_cds3_discovery_worklist` (`:2140`)
**Task in the process:** Publishes the Discovery outcome as the governed worklist: it validates that every Discovery row has a unique non-blank ticker, reconciles survived/dropped/failed against the input, and writes each ticker's lifecycle state so that downstream stages inherit an authorised population.
**Entry points:** the publish function called at `intelligent_orchestrator.py:2140`
**Imports (production):** `.errors` (`WorklistViolation`), `.lifecycle`, `.registry`, `.worklist_gate` · **Imported by:** `intelligent_orchestrator.py` · **Broken/retired imports:** NONE

**Inputs**
- Files/tables read: the Discovery lifecycle CSV; `control_plane.sqlite`
- Upstream fields consumed: `ticker`, `lifecycle_state`

**Logic and algorithms**
- Five distinct `WorklistViolation` raise sites (`:49`, `:51`, `:114`, `:122`, `:144`, `:172`) — blank ticker, duplicate ticker, illegal target state, disallowed drop state, wrong prior state
- `reconcile_stage_outcomes(...)` at `:83` applies the §14.5 invariant
- `:143` `elif latest.state is not LifecycleState.ACTIVE_DISCOVERY:` — a ticker may only be published from the expected prior state
- Decision branches: no direction branch — **NOT_APPLICABLE**

**Computations and formulas (exact)** — NONE (validation and state assignment only)

**Models** — NONE

**Outputs** — lifecycle rows + `canonical/cds3_discovery_publication_{run_id}.json` (present in the evidence run at 01:06:42) [MEASURED]. Atomic promotion: **not established** for the JSON. Schema/version field: **not established**
**Handoff** — receives Discovery (stage 10); hands the authorised worklist to package construction. Join key: `ticker`
**Missing-data handling** — every failure is a raise, not a default: this is the most fail-closed module in the audit set alongside `worklist_gate.py`. §10-compliant? **N** — raises instead
**Contradictions found here:** NONE
**Gaps found here:** NONE
**Comment/docstring claims audited:** NOT_APPLICABLE
**Confidence in this section:** MEDIUM — raise sites and the reconciliation call read; the body between them sampled

---

### canonical_data/option_identity.py
**Classification:** LIBRARY (ORCHESTRATED — evening stage 18)
**Real execution position:** LIBRARY — OCC identity helper used by the chain services and by the OLM store
**Task in the process:** Parses and builds OCC option symbols as a typed identity, so that contract identity is a checked object rather than a string.
**Entry points:** `parse_occ_symbol()` (`:52`), `build_occ_symbol()` (`:65`), `normalise_occ_symbol()`, `class OptionIdentity`
**Imports (production):** stdlib (`re`, `datetime`) · **Imported by:** `option_chain_store.py`, `market_observation_resolver.py`, `canonical_data/__init__.py` · **Broken/retired imports:** NONE
**Inputs** — an OCC symbol string, or root/expiry/side/strike components. No I/O, no external calls
**Logic and algorithms** — regex `_OCC` fullmatch with named groups `root`, `expiry`, `side`, `strike`; `parse_occ_symbol` **asserts** the match succeeded (`:55`)
**Decision branches** — `:60` `side = "CALL" if match.group("side") == "C" else "PUT"`. **CALL path:** `C` → CALL. **PUT path:** `P` → PUT. **Other/blank path: unreachable** — the regex constrains the side group to `[CP]`, and a non-matching symbol fails the assertion at `:55` first. **This is the one direction branch in the audit where a two-way collapse is sound, because the input domain is closed by the regex.**
**Computations and formulas (exact)** — `strike = int(match.group("strike")) / 1000.0` (`:61`) — OCC 8-digit thousandths; `strike_code = int(round(float(strike) * 1000.0))` formatted `:08d` (`:72`); `expiry = datetime.strptime(match.group("expiry"), "%y%m%d").date()` (`:59`)
**Models** — NONE
**Outputs** — a frozen `OptionIdentity`; writes nothing. Authority-claim fields: NONE asserted
**Handoff** — hands parsed identity to the chain services and to `record_contract_observation`'s `contract_symbol` normalisation
**Missing-data handling** — missing root or side → `ValueError` (`:70-71`); malformed symbol → assertion failure (`:55`). §10-compliant? **N** — raises, which is stricter
**Contradictions found here:** CON-502 — `contracts/selected_contract_economics.py:73-86` implements the same OCC parse but returns a **dict** and raises `ValueError` on non-match (`:74-75`). Two parsers, two return types, two failure modes; `morning_gate.py:62` imports the dict-returning one
**Gaps found here:** NONE
**Comment/docstring claims audited:** NONE asserted
**Confidence in this section:** HIGH — file read end to end

---

### canonical_data/option_chain_store.py
**Classification:** LIBRARY (ORCHESTRATED — evening stage 18)
**Real execution position:** Constructed at `scripts/avshunter_options_intelligence.py:8079-8087` as `CanonicalOptionChainService` when `msi_flags.v2_capture` is **off**
**Task in the process:** Acquires the completed-session MarketData option chain once per ticker/session/scope, registers its identity and exposes it for contract selection, alternatives, GEX/IV/Greeks and lifecycle calculations.
**Entry points:** `class CanonicalOptionChainService`
**Imports (production):** `.lifecycle` (`:26`), `.registry`, `.contracts`, `.errors`, `.option_identity` · **Imported by:** `scripts/avshunter_options_intelligence.py`, `canonical_data/__init__.py` · **Broken/retired imports:** NONE
**Inputs** — ticker, session date, scope, DTE bounds and `min_open_interest` from the caller (`scripts/avshunter_options_intelligence.py:8079-8086`); the registry; MarketData via the governed adapter
**Logic and algorithms** — the reuse ladder: consult `LifecycleManager` for fetch suppression (`:26`) → consult the registry → reuse a compatible chain → otherwise fetch once → normalise → write through → register → expose the `dataset_id`
**Decision branches** — no CALL/PUT branch; the chain is acquired for both sides. CALL / PUT / other-blank: **NOT_APPLICABLE**
**Computations and formulas (exact)** — NOT_ESTABLISHED in detail; the scope fingerprint and `dataset_id` derivation are the registry's (`registry.py`, `contracts.py:136`)
**Models** — NONE
**Outputs** — canonical chain payloads under `data/canonical/options/`, registered in `dataset_registry`. Authority-claim: **Polygon options disabled** → **HOLDS** (see the shared evidence note below)
**Handoff** — hands `option_chain_dataset_id` to Options Intelligence, which passes it into `record_contract_observation` as `source_dataset_id`
**Missing-data handling** — a dropped ticker is suppressed before any provider call via `LifecycleManager` (`:26`); unknown dataset downstream → the OLM store raises (`option_liquidity_lifecycle.py:748-749`). §10-compliant? **N** — raises
**Contradictions found here:** NONE established
**Gaps found here:** NONE established
**Comment/docstring claims audited:** the Polygon-disabled policy → **HOLDS**
**Confidence in this section:** MEDIUM — traced at its lifecycle and registry seams; the body was not read in full

---

### canonical_data/market_observation_resolver.py
**Classification:** LIBRARY (ORCHESTRATED — evening stage 18)
**Real execution position:** Constructed at `scripts/avshunter_options_intelligence.py:8067-8073` as `CanonicalMarketObservationResolver` when `msi_flags.v2_capture` is **on**; the orchestrator prints `[MSI-1] option_chain_v2 capture/resolution enabled` (`:8075`)
**Task in the process:** The v2 replacement for the chain store — resolves a market observation (chain plus context) for a ticker/session and registers it as a canonical payload under `data/canonical/market_observations/`.
**Entry points:** `class CanonicalMarketObservationResolver`
**Imports (production):** `.lifecycle` (`:23`), `.registry`, `.contracts`, `.errors`, `.marketdata_response` · **Imported by:** `scripts/avshunter_options_intelligence.py`, `canonical_data/__init__.py` · **Broken/retired imports:** NONE
**Inputs** — `registry_path`, `payload_root`, `run_id`, `flags` (`scripts/avshunter_options_intelligence.py:8068-8072`)
**Logic and algorithms** — same reuse ladder as the chain store, consulting `LifecycleManager` for fetch suppression before any provider call (`:23`)
**Decision branches** — no CALL/PUT branch. CALL / PUT / other-blank: **NOT_APPLICABLE**
**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NONE
**Outputs** — market-observation payloads registered in `dataset_registry`. Authority-claim: **Polygon options disabled** → **HOLDS**
**Handoff** — same as the chain store; the two are mutually exclusive, selected by `msi_flags.v2_capture` (`scripts/avshunter_options_intelligence.py:8066`)
**Missing-data handling** — fetch suppression via lifecycle; NOT_ESTABLISHED beyond that. §10-compliant? NOT_ESTABLISHED
**Contradictions found here:** NONE established. Note that **two chain-acquisition implementations coexist**, gated by a feature flag whose production default is on (`msi_runtime` ships seven of eight flags true) — so the v1 `option_chain_store.py` path is present but not the one taken
**Gaps found here:** NONE established
**Comment/docstring claims audited:** the Polygon-disabled policy → **HOLDS**
**Confidence in this section:** MEDIUM — traced at its construction site and lifecycle seam; the body was not read in full

---

### canonical_data/marketdata_response.py
**Classification:** LIBRARY (ORCHESTRATED — evening stage 18)
**Real execution position:** LIBRARY — normalisation helper for MarketData payloads, used by the resolver
**Task in the process:** Normalises a raw MarketData response into the canonical shape (OCC symbols, bid/ask, Greeks, IV, OI, volume, timestamps) before it is hashed and registered.
**Entry points:** module-level normalisation functions
**Imports (production):** `.contracts`, `.errors`, `.option_identity` · **Imported by:** `market_observation_resolver.py`, `canonical_data/__init__.py` · **Broken/retired imports:** NONE
**Inputs** — a raw provider response
**Logic and algorithms** — field normalisation and provider assertion. Decision branches: no CALL/PUT branch beyond the OCC side parse delegated to `option_identity.py`. CALL / PUT / other-blank: **NOT_APPLICABLE** (delegated)
**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NONE
**Outputs** — a normalised in-memory structure; persistence is the resolver's. Authority-claim: MarketData provenance — **HOLDS**, and is independently hard-enforced downstream at `canonical_data/option_liquidity_lifecycle.py:678-679` (`options provenance must be MARKETDATA`) and `:752-753` (`source option-chain dataset is not MARKETDATA`)
**Handoff** — hands the normalised payload to the resolver for hashing and registration
**Missing-data handling** — NOT_ESTABLISHED
**Contradictions found here:** NONE established
**Gaps found here:** NONE established
**Comment/docstring claims audited:** the Polygon-disabled policy → **HOLDS**
**Confidence in this section:** MEDIUM — role established from imports and consumers; the body was not read in full

---

### Shared evidence note for the four option-acquisition modules above

**"Polygon options disabled; canonical production options data is MarketData"**
(AVS-E2E-DATA-LOGIC-001 §3) → **HOLDS**, on three independent grounds:

1. An exhaustive grep of `canonical_data/` for `polygon` intersected with
   option/chain/contract terms returns **zero matches** [OBSERVED].
2. The OLM store hard-rejects a non-MarketData provider at two separate points:
   `canonical_data/option_liquidity_lifecycle.py:678-679` and `:752-753`
   [OBSERVED].
3. The evidence run recorded **zero Polygon options fallbacks** [MEASURED, §11.2].

`polygon_data_fetcher.py` remains live but is **equity-only** — it fetches daily
and intraday bars and last prices, never an option chain (Part G).

---

### _superseded grouped section (retained for provenance)_
The four modules above were originally described in one grouped section, which
was not template-compliant. The grouping is superseded by the four sections
above; the shared Polygon evidence is preserved in the note.

**Classification:** LIBRARY / ORCHESTRATED (all four reached from evening stage 18)
**Real execution position:** Constructed at `scripts/avshunter_options_intelligence.py:8067-8087` — `CanonicalMarketObservationResolver` when `msi_flags.v2_capture` is on, otherwise `CanonicalOptionChainService`
**Task in the process:** Acquire the completed-session MarketData option chain once per ticker/session/scope, normalise it, register its identity and expose it for contract selection, alternatives, GEX/IV/Greeks and lifecycle calculations.
**Imports (production):** `.lifecycle` (fetch suppression), `.registry`, `.contracts`, `.errors` · **Imported by:** `scripts/avshunter_options_intelligence.py`, `canonical_data/__init__.py`

**Logic and algorithms**
- Both services consult `LifecycleManager` before any provider call (`option_chain_store.py:26`, `market_observation_resolver.py:23`) [OBSERVED] — this is where the dropped-ticker rule prevents downstream API cost
- `option_identity.parse_occ_symbol` (`canonical_data/option_identity.py:52-62`) returns a typed `OptionIdentity` and **asserts** the regex matched (`:55`); `build_occ_symbol` (`:65-75`) raises `ValueError` when root or side is missing (`:70-71`)
- Decision branches — `option_identity.py:60`: `side = "CALL" if match.group("side") == "C" else "PUT"`. **CALL path**: `C` → CALL. **PUT path**: `P` → PUT. **Other/blank path**: unreachable — the regex `_OCC` constrains the side group to `[CP]`, and a non-matching symbol fails the assertion at `:55` before this line. This is the one direction branch in the audit set where the two-way collapse is **sound**, because the input domain is closed by the regex. Contrast `contracts/selected_contract_economics.py:79`, which implements the same mapping but returns a dict and raises on non-match (`:74-75`) — two parsers for one concept (CON-502).

**Computations and formulas (exact)**
- `option_identity.py:61`: `strike = int(match.group("strike")) / 1000.0` — OCC 8-digit strike, thousandths
- `option_identity.py:72`: `strike_code = int(round(float(strike) * 1000.0))`, formatted `:08d`

**Models** — NONE

**Outputs** — canonical chain payloads under `data/canonical/options/` or `market_observations/`, registered in `dataset_registry`. Authority-claim: **"Polygon options disabled; canonical production options data is MarketData"** (AVS-E2E-DATA-LOGIC-001 §3) → **HOLDS**: an exhaustive grep of `canonical_data/` for `polygon` intersected with option/chain/contract terms returns **zero matches** [OBSERVED], and the OLM store hard-rejects a non-MarketData provider at `canonical_data/option_liquidity_lifecycle.py:678-679` and `:752-753`. Measured corroboration: zero Polygon options fallbacks on the evidence run [MEASURED, §11.2].

**Handoff** — hands `option_chain_dataset_id` to `scripts/avshunter_options_intelligence.py`, which passes it into `record_contract_observation` as `source_dataset_id`
**Missing-data handling** — unknown dataset → the OLM store raises `unknown source_dataset_id` (`option_liquidity_lifecycle.py:748-749`); wrong dataset type → raises (`:750-751`); ticker mismatch → raises (`:754-755`). §10-compliant? **N** — raises, which is stricter
**Contradictions found here:** CON-502
**Gaps found here:** NONE established
**Comment/docstring claims audited:** the Polygon-disabled policy → **HOLDS** (see Outputs)
**Confidence in this section:** MEDIUM — grouped section; `option_identity.py` read end to end, the two service modules traced at their lifecycle/registry seams rather than read in full. The Polygon finding is HIGH confidence (exhaustive grep plus two independent hard rejections plus measurement)

---

### Undescribed in this lane

The following Lane E files carry no section in this atlas and are recorded as
**UNTRACED** for this pass: `contracts.py`, `errors.py`, `storage.py`,
`gateway.py`, `stage_publisher.py`, `historical_prices.py`, `history_bridge.py`,
`daily_adapter.py`, `intraday_bars.py`, `bundle_freshness.py`,
`request_ledger.py`, `narrow_refresh.py`, `contract_reference.py`,
`__init__.py`, and in `contracts/`: `bond_macro_contract.py`,
`macro_enrichment_delta.py`, `macro_regime_safety.py`,
`quote_change_evidence.py`, `interpreter_macro_context.py`,
`lab_evidence_overlay.py`.

**`macro_regime_safety.py` was settled and is therefore not in that list.**
Its load-bearing policy question — can it block a ticker or decide a ticker's
direction? — resolves to **no, the documented policy HOLDS**:

- The file is 138 lines and contains **no `BLOCK` token and no ticker-level
  gate** [OBSERVED, `contracts/macro_regime_safety.py`].
- Its three public functions all return labels or distributions, never a
  verdict: `derive_regime_sub_state` returns a regime string (`:71-101`),
  `derive_regime_distribution` returns a probability dict from
  `REGIME_DISTRIBUTION_MAP` falling back to `BALANCED_DISTRIBUTION` (`:104-111`),
  and `normalise_macro_regime_fields` normalises macro fields (`:114-138`).
- The only direction-shaped construct is a **macro-level label** fallback chain
  at `:118`: `dir_bias or direction_bias or macro_direction_bias or ""`. This
  normalises the macro packet's own bias field; it is not applied to a ticker.
- Its two production callers consume exactly that: `intelligent_orchestrator.py:1037`
  imports `derive_regime_distribution`, and `scripts/normalise_macro_contract.py:54`
  imports `normalise_macro_regime_fields` (with a bare-name fallback import at
  `:56`). Neither result reaches a per-ticker gate from this module.

Verdict on AVS-E2E-DATA-LOGIC-001 §3 and §7.9 for *this* module: **HOLDS**.
Note that this is a narrower finding than the pipeline-wide macro question —
macro *does* exert a 4:1 directional size asymmetry elsewhere, via
`MACRO_DIRECTION_SIZING` in the orchestrator (CON-006), which is a different
code path from this one.

The remaining twenty files are recorded as GAP-502.
