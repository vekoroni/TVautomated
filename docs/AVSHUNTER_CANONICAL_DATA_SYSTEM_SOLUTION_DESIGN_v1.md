# AVSHUNTER Canonical Data System

## Solution Design and Build/Fix Plan

**Version:** 1.0  
**Date:** 2026-08-22  
**Status:** Approved design baseline; implementation not started  
**Scope:** Core AVSHUNTER market-data flow, stage eligibility, API reuse, EOD-to-morning handoff  
**Out of scope:** Pipeline Interpreter changes, trading-policy redesign, model replacement, macro-model redesign

---

## 1. Executive decision

AVSHUNTER will use one governed logical source of truth for market data. Every stage will obtain data through a canonical data gateway and will receive its ticker worklist from a governed ticker-lifecycle ledger.

The solution addresses two connected defects:

1. The same ticker history and option data are fetched repeatedly by independent scripts.
2. A ticker rejected in one stage can continue into later stages and cause unnecessary API calls.

Caching alone is insufficient. The data gateway must verify that a ticker is authorised for the requesting stage **before** it reads a cache or calls a provider.

The target system will:

- fetch a dataset once, validate it, version it and reuse it;
- fetch only missing dates, fields or contracts;
- use an existing superset rather than request a smaller overlapping dataset;
- prevent terminally dropped tickers from entering later worklists;
- allow route-specific continuation where a ticker is dropped from Options but remains valid for equity research;
- separate immutable completed-EOD data from time-sensitive morning/live data;
- record the reason, requesting stage and outcome of every provider request;
- preserve the current pipeline and data stores until controlled cutover is complete.

---

## 2. Verified current-state baseline

The reference run for this design is `20260821_090928`.

| Current behaviour | Verified count | Finding |
|---|---:|---|
| Discovery Polygon daily-history requests | 3,323 | One request per universe ticker because `--force-update` is always passed |
| Package-backfill Polygon history requests | 1,657 | Re-fetches histories already used by Discovery |
| GARCH Polygon history requests | 1,374 | All 1,374 tickers already belonged to the successfully backfilled Vanguard population |
| Total Polygon daily-history requests | 6,354 | 3,031 repeat requests beyond the first ticker/session retrieval |
| Options MarketData historical-close requests | 1,335 | Historical data function already available from package OHLCV |
| Options sector-ETF candle requests | 68 | Only 11 unique ETFs; 57 exact repeated requests |
| Options chain worklist | 1,374 | Each ticker launches MarketData and Polygon chain retrieval in parallel |
| Minimum Options chain requests | 2,748 | Polygon pagination and retries make the physical total higher |
| MarketData-primary chain successes | 1,335 | 39 tickers had no usable chain from either provider |
| Polygon chain fallbacks that rescued a ticker | 0 | Polygon mainly supplied metadata in this run |
| Scanner rows | 225 | Scanner ran before the main pipeline |
| Scanner/Options overlap | 161 | Same completed session, different chain scopes and computations |
| Actionable scanner context reaching Options | 104 | Only part of the scanner universe was a governed actionable handoff |
| Morning candidates | 1,129 | Separate live-validation population |
| Morning provider requests | 3,710 | 1,129 equity snapshots, 2,258 skew-chain requests and 323 contract quote/repair attempts |

### 2.1 Repetition profile

For Polygon daily OHLCV:

- 1,374 tickers were fetched three times;
- 283 tickers were fetched twice;
- 1,666 tickers were fetched once.

Discovery, package backfill and GARCH use different lookback windows, so their full payloads are not byte-identical. However, they request the same adjusted Polygon daily bars for the same ticker and completed sessions. The canonical store must hold the largest governed series and serve shorter windows as projections.

### 2.2 Current direct callers requiring remediation

| File/function | Current use | Required change |
|---|---|---|
| `avshunter_discovery_ULTIMATE.py::load_bars` | Fetches Polygon daily OHLCV and writes `data/daily` CSVs | Resolve and update canonical daily history through the gateway |
| `scripts/backfill_timeseries_into_packages.py::polygon_fetch_ohlcv_daily` | Fetches history from 2018 for every new package | Read canonical history; fetch only a missing range through the gateway |
| `garch_runner.py::_fetch_ohlcv` | Fetches a separate 252-bar Polygon history | Read the final 252 bars from the canonical series |
| `scripts/avshunter_options_intelligence.py::_fetch_hist_closes` | Fetches MarketData daily closes for HV/IV context | Read canonical closes; preserve a provider-comparison lane only for QA |
| `scripts/avshunter_options_intelligence.py::fetch_sector_regime` | Fetches the same ETF repeatedly | Read ETF history from canonical OHLCV and cache one calculation per run |
| `scripts/avshunter_universe_scanner.py::fetch_price_data` | Fetches MarketData price history | Read the canonical completed-session history |
| `scripts/avshunter_universe_scanner.py::fetch_options_chain_marketdata` | Fetches a bounded MarketData option chain | Resolve a canonical session snapshot or request the missing scope |
| `scripts/avshunter_options_intelligence.py::fetch_chain` | Fetches MarketData and Polygon full chains in parallel | Use MarketData as canonical; use Polygon reference metadata and explicit fallback only |
| `morning_gate.py` live fetch functions | Fetch live price, option quote and skew | Keep live namespace; restrict calls to the authorised morning worklist |

---

## 3. Design principles

### 3.1 Capture once, compute many times

Provider responses are captured once and stored before model-specific computation. Discovery, Vanguard, Options and GARCH may calculate different features, but they must calculate them from the same governed observations.

### 3.2 Authorisation precedes acquisition

No network request may occur until the data gateway confirms that the ticker is authorised for the requesting stage and data capability.

### 3.3 Superset reuse

If a stored dataset covers the requested dates, fields and quality level, consumers receive a projection of the stored dataset. They do not refetch a smaller subset.

### 3.4 Missing-range retrieval

If a dataset is partially complete, only missing dates or fields are fetched. The result is validated and atomically promoted as a new dataset version.

### 3.5 Immutable session snapshots

A completed EOD snapshot is immutable. Corrections create a new version with lineage; they do not silently overwrite the version used by an earlier run.

### 3.6 EOD and live separation

Morning/live observations use a separate namespace, timestamp and TTL. A live quote never overwrites the completed-EOD snapshot.

### 3.7 Route-specific drops

Dropping a ticker from one capability does not automatically remove it from all research lanes. Terminal drops and lane-specific drops must be explicit.

### 3.8 Reproducibility before optimisation

Each pipeline run pins exact dataset IDs and content hashes. The system must support a zero-network replay of a completed run.

---

## 4. Target architecture

```text
                          +----------------------+
                          | Provider APIs        |
                          | Polygon / MarketData |
                          +----------+-----------+
                                     |
                                     v
                          +----------------------+
                          | Canonical Data       |
                          | Gateway              |
                          | - authorise ticker   |
                          | - resolve dataset    |
                          | - fetch missing only |
                          | - validate/promote   |
                          +----+------------+----+
                               |            |
                     metadata  |            | payloads
                               v            v
                    +----------------+  +--------------------+
                    | Registry DB    |  | Partitioned        |
                    | - lifecycle    |  | Parquet            |
                    | - manifests    |  | - OHLCV            |
                    | - requests     |  | - option snapshots |
                    | - worklists    |  | - live snapshots   |
                    +-------+--------+  +--------------------+
                            |
                            v
              +-------------+--------------------------------+
              | Stage worklists                               |
              +-------------+--------------------------------+
                            |
       Discovery -> Packages/Vanguard -> Options -> GARCH -> Morning
```

### 4.1 Physical storage decision

Use a logical source of truth consisting of:

1. `data/canonical/registry.sqlite`
   - transactional registry and control plane;
   - SQLite WAL mode;
   - atomic lifecycle and request-ledger updates;
   - small metadata records only.

2. `data/canonical/market/`
   - partitioned Parquet daily and intraday market data.

3. `data/canonical/options/`
   - partitioned Parquet option-chain snapshots.

4. `data/canonical/live/`
   - short-retention live validation snapshots, partitioned by run and timestamp.

5. `data/output/runs/<run_id>/canonical_manifest.json`
   - immutable list of dataset IDs and hashes consumed by a pipeline run.

This avoids placing large histories inside SQLite while maintaining one governed registry and access path.

---

## 5. Canonical data contracts

### 5.1 Dataset identity

Every dataset version must include:

| Field | Purpose |
|---|---|
| `dataset_id` | Immutable identifier |
| `dataset_type` | `DAILY_OHLCV`, `OPTION_CHAIN`, `CONTRACT_REFERENCE`, `LIVE_EQUITY`, `LIVE_OPTION`, etc. |
| `instrument_id` | Canonical ticker, ETF or OCC symbol |
| `market_session_date` | Session represented by the data |
| `as_of_utc` | Provider observation timestamp |
| `provider` | Polygon, MarketData or governed derived source |
| `frequency` | Daily, minute, snapshot |
| `scope_json` | Date range, DTE range, side, fields and filters |
| `adjustment_convention` | Split/dividend handling for price histories |
| `schema_version` | Governed schema identifier |
| `content_hash` | Detects changed payloads |
| `completeness_status` | Complete, partial, invalid or unavailable |
| `quality_flags_json` | Missing fields, stale rows and provider anomalies |
| `parent_dataset_ids_json` | Lineage for merged or derived versions |
| `storage_path` | Payload location |
| `created_at_utc` | Registry timestamp |

### 5.2 Canonical provider policy

| Dataset | Primary | Fallback | Policy |
|---|---|---|---|
| Completed daily OHLCV | Polygon | Existing validated local history | One incremental update per ticker/session |
| EOD option chain | MarketData | Polygon option snapshot | Polygon full chain only on explicit primary failure |
| Contract multiplier | Polygon contract reference | Existing cached reference | Cache by OCC symbol; metadata is effectively permanent unless contract is corrected |
| Sector regime | Canonical ETF OHLCV | None required | Derive once per ETF/run |
| Morning equity snapshot | Polygon live snapshot | Fail closed to `UNVERIFIED` | TTL-governed live namespace |
| Morning option quote | MarketData quote | Repair alternative or `UNVERIFIED` | Selected contracts only |
| Macro inputs | Standalone macro system | Governed missing/degraded state | Advisory input; not stored as core price truth |

### 5.3 Freshness policies

| Data class | Freshness rule |
|---|---|
| Completed EOD daily bar | Immutable once the configured session-completion time has passed |
| Premarket use of last EOD bar | Valid as prior completed session, never labelled live |
| EOD option chain | Pinned by session date and provider `updated` timestamp |
| Scanner/Options same-session chain | Reuse if stored scope is a superset and max-age policy is satisfied |
| Morning equity/option quote | Short TTL configured in seconds; always stored separately from EOD |
| Contract reference | Reuse indefinitely unless provider correction or schema change is detected |

---

## 6. Registry schema

### 6.1 `run_registry`

```text
run_id PK
run_type                 EVENING | MORNING | REPLAY
started_at_utc
completed_at_utc
market_session_date
data_mode
status
canonical_manifest_path
parent_run_id
```

### 6.2 `ticker_lifecycle`

```text
run_id PK-part
ticker PK-part
state_version PK-part
current_state
last_completed_stage
allowed_capabilities_json
allowed_next_stages_json
drop_class
drop_reason
dropped_at_stage
reactivation_reason
updated_at_utc
```

### 6.3 `stage_worklist`

```text
run_id PK-part
stage PK-part
ticker PK-part
work_status              PENDING | IN_PROGRESS | COMPLETE | DROPPED | ERROR
required_capabilities_json
source_state_version
created_at_utc
completed_at_utc
result_reason
```

### 6.4 `dataset_registry`

Contains the data-contract fields defined in section 5.1 and indexes on:

- `(dataset_type, instrument_id, market_session_date)`;
- `(instrument_id, as_of_utc)`;
- `(content_hash)`;
- `(completeness_status)`.

### 6.5 `api_request_ledger`

```text
request_id PK
run_id
requesting_stage
ticker_or_symbol
dataset_type
provider
request_scope_hash
request_started_at_utc
request_completed_at_utc
resolution                 CACHE_HIT | SUPERSET_HIT | PARTIAL_FETCH |
                           PROVIDER_FETCH | BLOCKED_NOT_AUTHORISED |
                           PROVIDER_ERROR
http_request_count
retry_count
provider_status
dataset_id
fetch_reason
```

The ledger closes the present observability gap around pagination, retries and per-contract reference calls.

---

## 7. Ticker lifecycle and drop governance

### 7.1 Required states

| State | Meaning | Permitted future API work |
|---|---|---|
| `ACTIVE_DISCOVERY` | Universe ticker awaiting initial analysis | Daily history required to decide eligibility |
| `ACTIVE_CORE` | Passed Discovery and is eligible for core models | Canonical data reads; missing-range fetch permitted |
| `ACTIVE_OPTIONS` | Eligible for option-chain research | EOD option snapshot permitted |
| `ACTIVE_EQUITY_ONLY` | Options lane ended but equity research remains valid | Equity datasets only |
| `ACTIVE_MORNING` | Included in the governed morning manifest | Live equity and authorised contract calls |
| `DEFERRED_CURRENT_RUN` | Insufficient current data; retain for later run | No more API calls in the current run unless an explicit repair event is authorised |
| `DROPPED_STAGE` | Removed from a specific lane | Only capabilities explicitly retained in the ledger |
| `DROPPED_TERMINAL_DATA` | Invalid symbol, unavailable/stale history or failed data contract | No subsequent API calls |
| `DROPPED_TERMINAL_LOGIC` | Definitively ineligible for the current run | No subsequent API calls |
| `COMPLETED` | Finished all authorised stages | No subsequent calls for the same run |

### 7.2 Drop rules

1. Discovery may fetch initial history because it must determine whether a ticker survives.
2. Discovery writes exactly one result per input ticker: survive, deferred, stage drop, terminal data drop or terminal logic drop.
3. The orchestrator builds the package worklist only from eligible Discovery survivors.
4. Vanguard writes its own survivor/drop result and the orchestrator builds the Options worklist from that result.
5. Options distinguishes `NO_OPTION_ROUTE` from `EQUITY_RESEARCH_VALID` instead of globally dropping the ticker.
6. The morning manifest is the only authority allowed to create `ACTIVE_MORNING` rows.
7. A dropped ticker cannot be silently reintroduced through a join, stale CSV or original-universe reload.
8. Reactivation requires a new lifecycle event with a reason, source stage and new state version.

### 7.3 Authorisation check

The gateway performs this check before cache resolution or provider access:

```python
decision = lifecycle.authorise(
    run_id=run_id,
    ticker=ticker,
    requesting_stage=stage,
    required_capability=dataset_type,
)

if not decision.allowed:
    request_ledger.record_blocked(decision.reason)
    raise FetchNotAuthorised(decision.reason)
```

This protects the pipeline even if a consumer receives an incorrect ticker list.

---

## 8. Canonical resolution algorithm

```python
def get_or_fetch(request):
    authorise(request.run_id, request.stage, request.instrument, request.capability)

    exact = registry.find_exact_fresh(request)
    if exact:
        return load_and_validate(exact)

    superset = registry.find_fresh_superset(request)
    if superset:
        return project(load_and_validate(superset), request.scope)

    partial = registry.find_best_partial(request)
    missing_scope = calculate_missing_scope(partial, request)

    if not missing_scope:
        return project(load_and_validate(partial), request.scope)

    payload = provider.fetch(missing_scope)
    validated = validate_provider_payload(payload, request.contract)
    promoted = atomic_merge_and_promote(partial, validated)
    registry.register(promoted)
    request_ledger.record(promoted)
    return project(promoted, request.scope)
```

### 8.1 Failure behaviour

- No fabricated data.
- A provider failure does not overwrite an existing valid dataset.
- A stale fallback must remain explicitly marked stale.
- Missing required fields return a governed partial/unavailable state.
- Consumers decide from the governed state; they do not silently call another provider directly.

---

## 9. Target end-to-end data flow

### 9.1 Scanner

- Reads canonical daily OHLCV.
- Requests or reuses one canonical MarketData chain snapshot per ticker/session.
- Derives VMS, LSS, volatility and bounded contract views.
- Writes results and lifecycle recommendations; it does not own a private market-data truth.

### 9.2 Discovery

- Receives the initial universe worklist.
- Incrementally updates canonical daily OHLCV once per ticker.
- Calculates structure, trend, mean-reversion and other core features.
- Writes a reconciled survivor/drop ledger.

### 9.3 Packages and Vanguard

- Build packages only for the Discovery survivor worklist.
- Attach canonical dataset IDs instead of fetching market data.
- Materialise package-local OHLCV only when compatibility requires it.
- Record that the materialised data is a projection of a canonical dataset.

### 9.4 Options Intelligence

- Receives only the Options-authorised worklist.
- Reads canonical daily closes for HV/IV context.
- Resolves one canonical MarketData option snapshot.
- Derives GEX, PCR, walls, skew, IV context and contract candidates from that snapshot.
- Retrieves Polygon contract reference metadata only for missing OCC multipliers.
- Uses Polygon full-chain fallback only when the canonical MarketData request is unavailable or invalid.
- Converts `NO_CHAIN` and `NO_CONTRACT` outcomes into explicit lifecycle routes.

### 9.5 GARCH

- Receives the GARCH-authorised worklist.
- Reads the final 252 bars from canonical daily OHLCV.
- Makes no historical-data provider request during a normal run.

### 9.6 Morning Gate

- Receives only `ACTIVE_MORNING` tickers from the signed morning manifest.
- Obtains live data through the gateway's live namespace.
- Reuses the same live snapshot within the gate when multiple checks require it.
- Tests only authorised primary and repair contracts.
- Writes live dataset IDs and timestamps into the morning output.

### 9.7 Macro boundary

- The core market-data store does not treat macro conclusions as market-price truth.
- Macro remains a standalone system with its own snapshot and contract.
- Core stages may carry macro context for later advisory reconciliation, but macro does not authorise a core market-data fetch or globally reactivate a dropped ticker.

---

## 10. Build and fix plan

### Phase CDS-0 — Freeze, baseline and backup

**Objective:** Establish a recoverable baseline before new code changes.

**Build tasks:**

- Record git status, active script hashes and current configuration.
- Snapshot the reference run manifests, outputs and API-call baseline.
- Back up all scripts that will be modified.
- Preserve `data/daily`, package histories, Phantom data, actuarial data and current run outputs.
- Create a rollback manifest containing file paths, hashes and restoration instructions.
- Add no new data deletion or automatic pruning.

**Tests:**

- Verify backup hashes.
- Verify the reference run can be read without modification.
- Confirm that rollback restores the exact original script hashes.

**Exit criteria:** Complete, verified and documented backup set.

---

### Phase CDS-1 — Registry and contracts

**Objective:** Build the control plane without changing production consumers.

**New components:**

- `canonical_data/contracts.py`
- `canonical_data/registry.py`
- `canonical_data/lifecycle.py`
- `canonical_data/request_ledger.py`
- `canonical_data/storage.py`
- registry schema migration and validation tooling

**Build tasks:**

- Implement the SQLite registry schema.
- Implement dataset identity, scope and freshness types.
- Implement lifecycle states and legal transitions.
- Implement stage-worklist creation and reconciliation.
- Implement API-request-ledger writes.
- Add atomic registry transactions and Parquet promotion.
- Add feature flags with production behaviour initially disabled.

**Feature flags:**

```text
AVSHUNTER_CANONICAL_DATA_ENABLED=0
AVSHUNTER_CANONICAL_WRITE_THROUGH=0
AVSHUNTER_STAGE_GATING_ENFORCED=0
AVSHUNTER_CANONICAL_OFFLINE_REPLAY=0
```

**Tests:**

- Registry CRUD and migration tests.
- Concurrent read/single-writer tests.
- Legal and illegal lifecycle transition tests.
- Dataset exact/superset/partial resolution tests.
- Atomic-write interruption tests.

**Exit criteria:** Registry and lifecycle unit tests pass; no production output changes.

---

### Phase CDS-2 — Canonical OHLCV and lifecycle shadow

**Objective:** Remove the largest repeat data acquisition while observing lifecycle decisions in shadow mode.

**Build tasks:**

- Inventory and import existing `data/daily` histories.
- Inventory package OHLCV and identify longer valid histories.
- Resolve duplicates using provider, adjustment convention, date coverage and content hashes.
- Do not call an API during migration.
- Build the canonical Polygon daily-history adapter.
- Implement missing-tail and missing-range retrieval.
- Make Discovery read/write canonical OHLCV behind a feature flag.
- Make package backfill read canonical OHLCV.
- Make GARCH read its final 252 bars from canonical OHLCV.
- Make Options IV/HV calculations read canonical closes.
- Record lifecycle decisions and proposed downstream worklists in shadow mode.

**Regression tests:**

- Compare canonical bars against `data/daily` and package histories.
- Compare Discovery indicators using identical input bars.
- Compare Vanguard signals and actuarial lookup fields.
- Compare GARCH parameters and forecast outputs.
- Compare Options HV30/IV-context results under the selected convention.
- Run the reference run in offline replay mode.

**Performance acceptance:**

- Cold-run Polygon history calls: no more than one per initial-universe ticker.
- Same-session replay history calls: zero.
- Package-backfill Polygon calls: zero under normal conditions.
- GARCH Polygon history calls: zero.
- Options historical-close calls: zero.

**Exit criteria:** Output parity accepted and lifecycle shadow reconciles every stage.

---

### Phase CDS-3 — Enforced stage worklists and drop protection

**Objective:** Prevent rejected tickers from creating subsequent work or API calls.

**Build tasks:**

- Make Discovery publish one lifecycle result per input ticker.
- Build Packages from the governed survivor worklist only.
- Make Vanguard publish capability-specific survivor/drop results.
- Build the Options worklist from Vanguard eligibility.
- Build GARCH and morning worklists from explicit capability permissions.
- Add gateway authorisation before every provider call.
- Record blocked unauthorised requests in the request ledger.
- Reject joins that introduce a ticker absent from the authorised worklist.
- Add stage reconciliation to the final run manifest.

**Regression tests:**

- Inject a sentinel ticker dropped at Discovery and prove zero later requests.
- Drop a ticker from Options but retain `ACTIVE_EQUITY_ONLY`; prove only authorised equity computation continues.
- Prove terminally dropped tickers cannot be reintroduced from the original universe, stale CSVs or joins.
- Prove explicit reactivation creates a new state version and audit record.
- Enforce `input = survivors + drops + errors` at every stage.

**Exit criteria:** No unauthorised downstream API call in replay, shadow or controlled live test.

---

### Phase CDS-4 — Canonical option-chain and contract-reference layer

**Objective:** Remove scanner/options chain duplication and unnecessary Polygon full-chain retrieval.

**Build tasks:**

- Define a canonical MarketData option-chain schema.
- Store provider `updated` timestamps and requested scope.
- Implement scope-superset resolution for DTE, side, strikes and required fields.
- Let Scanner consume a bounded projection of the stored full snapshot.
- Let Options Intelligence consume the same governed snapshot where freshness permits.
- Add an OCC-symbol contract-reference cache.
- Replace unconditional parallel Polygon full-chain retrieval with:
  1. canonical MarketData request;
  2. cached/batched Polygon reference lookup for unresolved multipliers;
  3. explicit Polygon full-chain fallback only after primary failure.
- Preserve provider comparison as a QA lane, not a production requirement.

**Regression tests:**

- Compare chain row counts and contract identities.
- Compare selected contracts, GEX, walls, PCR, IV, Greeks and liquidity fields.
- Verify special deliverables and non-100 multipliers.
- Verify the Polygon fallback path with a controlled MarketData failure.
- Verify Scanner projection does not alter its selection logic unexpectedly.

**Performance acceptance:**

- MarketData EOD chain calls: at most one per authorised ticker/snapshot scope.
- Polygon full option-chain calls: only explicit primary failures.
- Contract-reference calls: one per previously unseen OCC symbol, then cache hit.

**Exit criteria:** Options functional parity and governed fallback tests pass.

---

### Phase CDS-4A — Selected-contract hydration and economics identity

**Objective:** Prevent the Intelligence Lab from comparing R:R calculated for
one contract with EV calculated for another contract or option structure.

This phase is a required extension of CDS-4. It was added after the
`20260824_220616` morning run proved that selected-contract identity was not
preserved across contract repair, R:R and EV3. Of 26 tradeable rows displaying
negative EV3, 24 used an EV3 contract or structure different from the contract
displayed by the Lab.

**Mandatory processing order:**

1. Resolve the governed thesis direction.
2. Select or repair the final contract/structure.
3. Hydrate the exact selected contract and every spread leg.
4. Persist one immutable quote snapshot.
5. Calculate R:R from that snapshot and structure.
6. Calculate EV3 from the same snapshot and structure.
7. Reconcile evaluation identities.
8. Publish selected-contract R:R only after its identity is reconciled. Publish
   EV3 only when it shares that identity; otherwise publish an explicit
   advisory-unavailable state without granting EV3 capital authority.

**Contract hydration requirements:**

- Resolve the exact OCC symbol, strike, expiry, option side and DTE.
- Capture bid, ask, mid/mark, provider `updated` time, volume, open interest,
  IV, Greeks, multiplier, adjusted-contract status and deliverable metadata.
- Capture the underlying price and timestamp used by the economics calculation.
- Hydrate both legs independently for vertical spreads.
- Reuse a canonical snapshot when its identity, scope and freshness satisfy the
  request; fetch MarketData only for a missing or stale required snapshot.
- Write a newly fetched snapshot through to CDS before any consumer calculates
  economics.
- If any required leg cannot be hydrated, set contract repair/data state and
  fail closed; do not reuse the previous contract's economics.

**Governed identity:**

Every selected structure, R:R result and EV3 result must carry an immutable
evaluation identity derived from:

```text
ticker + canonical direction + structure + ordered leg symbols
+ quote snapshot/version + entry debit + target + invalidation + horizon
```

Add governed fields equivalent to:

- `selected_structure_id`;
- `selected_contract_symbols`;
- `selected_quote_snapshot_id`;
- `rr_evaluation_id`;
- `ev3_evaluation_id`;
- `economics_comparable`;
- `economics_mismatch_reason`.

**Hard invariant:**

```text
selected_structure_id == rr_evaluation_id == ev3_evaluation_id
```

If the invariant fails for an evaluated EV:

- never copy the unmatched EV into `ev_predicted`;
- display `EV NOT COMPARABLE — DIFFERENT CONTRACT` rather than a red/green EV;
- add `ECONOMICS_CONTRACT_MISMATCH` to data-quality/coherence controls;
- remove tradeability when selected-contract R:R is missing or mismatched;
- when exact-contract R:R is complete but EV3 is not evaluable, suppress EV3
  and retain its agreed advisory-only role rather than creating a hidden gate;
- preserve alternative-contract economics under their own identities only.

**Morning repair behaviour:**

Any change to symbol, leg, strike, expiry, structure or quote snapshot
invalidates the previous premium, Greeks, R:R, EV3 and economics-dependent
permission. The new contract must be hydrated and both calculations rerun
before publication.

**Regression tests:**

- Long call and long put identity equality.
- Bull-call and bear-put debit-spread leg equality.
- Morning strike, expiry and structure replacement invalidates old economics.
- Quote refresh reuses identity only under the governed freshness rule.
- Missing/stale leg fails closed without provider-call duplication.
- Alternative structures remain research-only and cannot populate selected
  fields.
- FISV and CRWV fixtures reproduce the old mismatch and prove it is rejected.
- Property test: every published comparable row satisfies the hard invariant.

**Exit criteria:** Zero silent contract/economics mismatches; every displayed EV
is either calculated for the exact selected structure or explicitly marked not
evaluated/not comparable.

**Implementation checkpoint — 25 August 2026:** The application-level CDS-4A,
CDS-025 and CDS-026 path is implemented. The morning gate now hydrates the exact
selected OCC contract or both ordered vertical-debit legs, persists a quote
snapshot and ordered-leg payload in the handoff, invalidates inherited
economics, and recomputes premium R:R and EV3 from the selected structure. The
governed Lab book carries selected-contract, R:R and EV3 identities; rejects
contract-owned fields from a differently identified source; suppresses
unmatched EV; and displays hydration, R:R recomputation and EV alignment state.
The morning EV3 adapter also converts handoff expected moves from percentage
points to EV3 fractions and derives the governed 5/10/20-session cache horizon
from the routed horizon when an explicit hold is absent.

Exact-contract R:R remains the hard monetisability sanity floor. EV3 remains
advisory: a genuinely evaluated cross-contract EV is a coherence defect, while
an unavailable exact-contract EV is shown as unavailable and cannot silently
grant or deny permission. Regression coverage passed for long calls, long puts,
bull-call debits, bear-put debits, missing legs, replacement contracts, unit
conversion, advisory EV behaviour and Lab handoff identity. An in-memory replay
of the real `20260824_220616` CTVA handoff reached the governed production EV3
barrier cache after the unit adapter repair.

This does not complete the whole CDS-4 persistence phase. Canonical option
snapshot write-through/reuse, provider-call deduplication, and governed adjusted
contract/deliverable metadata remain outstanding before CDS-4 itself can be
closed. No production output file or live API was exercised by this checkpoint.

---

### Phase CDS-5 — Sector and shared derived-data cache

**Objective:** Prevent repeated calculations and requests for shared instruments.

**Build tasks:**

- Treat sector ETFs as instruments in canonical OHLCV.
- Derive each ETF's sector regime once per dataset version.
- Store derived result with its parent dataset ID and calculation version.
- Allow every mapped equity to reference the same derived sector record.
- Extend the pattern to other deterministic shared inputs where justified.

**Tests:**

- Verify 68 legacy sector calls resolve to 11 or fewer unique datasets.
- Verify identical mapped tickers receive the same sector calculation version.
- Verify sector output parity.

**Exit criteria:** Zero dedicated sector-history calls when ETF canonical history exists.

---

### Phase CDS-6 — Morning/live namespace

**Objective:** Preserve required live validation without contaminating EOD truth or fetching dropped tickers.

**Build tasks:**

- Register the signed morning worklist.
- Add live equity and option snapshot contracts with TTLs.
- Reuse one fetched live result across all morning checks.
- Consolidate call/put skew retrieval when one both-sides response is supported and cheaper.
- Authorise only primary and bounded repair-contract quote requests.
- When a repair selects a different contract or structure, hydrate its exact
  live snapshot and invalidate all economics tied to the previous identity.
- Recompute R:R and EV3 from the same repaired-contract snapshot before the Lab
  can restore tradeability.
- Mark failures as `UNVERIFIED`; never substitute an EOD quote as live.
- Retain live observations for audit under a defined retention policy.

**Tests:**

- Verify only `ACTIVE_MORNING` tickers produce live calls.
- Verify TTL hit/miss behaviour.
- Verify live data never overwrites EOD data.
- Verify contract repair attempts are bounded and recorded.
- Verify partial live failures fail safely.

**Exit criteria:** Morning functionality unchanged, with complete request lineage and worklist enforcement.

---

### Phase CDS-7 — Direct-call prohibition and production cutover

**Objective:** Make the canonical gateway the only production network path.

**Build tasks:**

- Inventory all remaining direct Polygon and MarketData calls in active scripts.
- Migrate or explicitly exempt each call.
- Add a CI/static check preventing new direct provider calls outside approved adapters.
- Enable runtime enforcement for production stages.
- Enable canonical manifests in final run contracts.
- Update pipeline-map documentation and operational runbooks.
- Keep legacy data paths read-only for the rollback window.

**Tests:**

- Static direct-call scan.
- Full EOD cold run.
- Full same-session zero-network replay.
- Controlled next-session incremental run.
- Morning live run.
- Crash/restart idempotency test.
- Backup restoration and feature-flag rollback test.

**Exit criteria:** Production sign-off gates in section 13 all pass.

---

## 11. Prioritised development backlog

| ID | Priority | Deliverable | Dependency |
|---|---|---|---|
| CDS-001 | P0 | Dataset identity and freshness contract | None |
| CDS-002 | P0 | SQLite registry schema and migrations | CDS-001 |
| CDS-003 | P0 | Ticker lifecycle and legal transition model | CDS-001 |
| CDS-004 | P0 | Stage-worklist generator and reconciliation | CDS-003 |
| CDS-005 | P0 | API request ledger with page/retry counts | CDS-002 |
| CDS-006 | P0 | Data-gateway authorisation guard | CDS-003, CDS-005 |
| CDS-007 | P0 | Canonical OHLCV storage/importer | CDS-001, CDS-002 |
| CDS-008 | P0 | Polygon incremental OHLCV adapter | CDS-007 |
| CDS-009 | P0 | Discovery canonical OHLCV integration | CDS-008 |
| CDS-010 | P0 | Backfill canonical reader | CDS-007 |
| CDS-011 | P0 | GARCH canonical reader | CDS-007 |
| CDS-012 | P0 | Options historical-close canonical reader | CDS-007 |
| CDS-013 | P0 | Drop sentinel and no-subsequent-fetch regression suite | CDS-004, CDS-006 |
| CDS-014 | P1 | Canonical option-chain schema/store | CDS-001, CDS-002 |
| CDS-015 | P1 | Scanner/Options chain resolver | CDS-014 |
| CDS-016 | P1 | Contract-reference cache | CDS-002 |
| CDS-017 | P1 | Remove unconditional Polygon full-chain call | CDS-015, CDS-016 |
| CDS-018 | P1 | Sector derived-data cache | CDS-007 |
| CDS-019 | P1 | Morning live contracts and TTL cache | CDS-001, CDS-006 |
| CDS-020 | P1 | Morning authorised-contract request bound | CDS-004, CDS-019 |
| CDS-021 | P1 | Canonical run manifest and offline replay | CDS-002, CDS-007, CDS-014 |
| CDS-022 | P2 | Static direct-provider-call enforcement | All adapter migrations |
| CDS-023 | P2 | Legacy path retirement after rollback window | Production sign-off |
| CDS-024 | P0 | Selected option-structure identity and immutable evaluation key | CDS-014, CDS-016 |
| CDS-025 | P0 | Exact selected-contract/leg hydration and write-through | CDS-015, CDS-016, CDS-019 |
| CDS-026 | P0 | Contract-aligned R:R and EV3 computation bundle | CDS-024, CDS-025 |
| CDS-027 | P0 | Fail-closed economics identity reconciliation in final opportunity book | CDS-026 |
| CDS-028 | P0 | Morning contract-change invalidation and recomputation | CDS-019, CDS-020, CDS-026 |
| CDS-029 | P0 | Intelligence Lab `NOT COMPARABLE` state; remove cross-contract EV fallback | CDS-027 |
| POST-CDS-001 | P1 deferred | Align live and historical actuarial state taxonomy; govern cumulative fallback | CDS production sign-off |

### Deferred post-CDS defect: actuarial state-equivalence mismatch

`POST-CDS-001` is deliberately parked until the CDS phases and production
sign-off are complete. It must not be folded into the CDS implementation or
used to delay the current CDS shadow/write-through validation.

Confirmed evidence from the 24 August 2026 functional run:

- 135 neutral-prior warnings represented 14 distinct state keys.
- The dominant live state family was `NORMAL|SIDEWAYS|...|MARKUP`.
- The governed v7 database contains 3,816,857 observations and 739,602
  `NORMAL + SIDEWAYS` observations, but zero `NORMAL + SIDEWAYS + MARKUP`
  observations.
- The 508-state cache therefore contains no matching reduced core state.
- The live calculator can combine a Discovery D/E `MARKUP` bucket with a
  separately calculated `SIDEWAYS` trend, while the historical producer only
  assigns `MARKUP` when its bullish EMA convention also assigns `UP`.

Required post-CDS work:

1. Select and version one historical-equivalence contract for trend direction,
   Wyckoff bucket and trend maturity.
2. Apply the same contract to live calculation and historical production, or
   define an explicit, governed live-to-historical mapping where equivalence is
   defensible.
3. Replace the current mixture of single-field and special-case fallback with
   a documented cumulative fallback hierarchy that records dropped dimensions,
   sample size, validity and confidence penalty.
4. Do not allow fallback to conceal logically impossible state combinations;
   emit a taxonomy-contract defect separately from genuine sparse coverage.
5. Regression-test all live state combinations against the cache vocabulary
   and publish exact, fallback, no-match and taxonomy-defect coverage rates.

Acceptance criteria:

- Zero ungoverned live state combinations.
- `SIDEWAYS + MARKUP` is either reproducibly represented in historical data or
  mapped/rejected under a versioned rule.
- Every actuarial lookup reports match level, sample size and dimensions
  dropped.
- Neutral priors are reserved for genuine out-of-sample states, not producer
  taxonomy disagreement.
- Reference-run signal changes are measured and approved before deployment.

---

## 12. Test and regression strategy

### 12.1 Unit tests

- Dataset key and scope normalisation.
- Exact, superset and partial resolution.
- Missing-range calculation.
- Content hashing and duplicate detection.
- Freshness policies.
- Lifecycle transitions and capability checks.
- Registry transactions and atomic promotion.

### 12.2 Integration tests

- Provider adapter to registry to Parquet round trip.
- Discovery to lifecycle to package worklist.
- Package to Vanguard to Options worklist.
- Options chain snapshot to Scanner and Options projections.
- Morning worklist to live snapshot and contract repair.

### 12.3 Functional regression

Replay `20260821_090928` using pinned input data and compare:

- ticker populations and stage reconciliation;
- daily bars and content hashes;
- Discovery features and tiers;
- Vanguard fields and sample counts;
- Options contract identity, GEX, PCR, walls, IV, Greeks and liquidity;
- GARCH parameters and forecasts;
- EOD candidate manifest;
- morning validation routes where the same live snapshots are replayed.

Exact equality is required when calculations consume identical canonical data and code. Tolerances must be explicitly documented for floating-point model outputs. A change in ticker eligibility or verdict counts requires a named, reviewed reason.

### 12.4 Failure tests

- Missing provider key.
- Provider timeout and retry.
- Pagination interruption.
- Partial Parquet write.
- Registry transaction interruption.
- Stale EOD data.
- Missing option fields.
- Invalid contract multiplier.
- Dropped ticker passed accidentally to a later consumer.
- Restart after a stage completes but before the next worklist is generated.

### 12.5 Operational regression

- Current launchers continue to work under feature flags.
- No Pipeline Interpreter changes.
- No deletion of legacy databases during migration.
- Final manifests identify canonical dataset versions.
- Same-session rerun is idempotent.

---

## 13. Production sign-off gates

The canonical system is production-ready only when all gates pass:

1. **Backup gate:** scripts, registry and baseline data are recoverable and hash-verified.
2. **Data parity gate:** canonical histories match the selected authoritative source and adjustment convention.
3. **Replay gate:** the reference EOD run completes without network access.
4. **Lifecycle gate:** every stage reconciles inputs, survivors, drops and errors.
5. **Drop-protection gate:** terminally dropped sentinels generate zero later provider calls.
6. **API-efficiency gate:** normal package, GARCH and Options historical-close stages make zero duplicate history calls.
7. **Option fallback gate:** MarketData primary and Polygon fallback paths both pass controlled tests.
8. **Morning separation gate:** EOD and live namespaces cannot overwrite or masquerade as one another.
9. **Observability gate:** every provider request has a stage, reason, page count, retry count and outcome.
10. **Regression gate:** approved output parity thresholds pass.
11. **Rollback gate:** disabling the feature flags restores the previous production path.
12. **Documentation gate:** pipeline maps, runbooks and ownership are updated.

---

## 14. Backup, rollout and rollback plan

### 14.1 Backup

- Create a timestamped backup manifest before each phase.
- Copy only files within the phase's change set.
- Record SHA-256 hashes before and after modifications.
- Preserve all existing databases and payload directories.
- Never delete old stores during development or initial production cutover.

### 14.2 Rollout

1. Registry and lifecycle shadow writes.
2. Canonical OHLCV dual-read comparison.
3. Canonical OHLCV consumer cutover one consumer at a time.
4. Stage gating in warn-only mode.
5. Stage gating enforced.
6. Canonical option-chain shadow comparison.
7. Option-chain consumer cutover.
8. Morning/live cutover.
9. Direct-call prohibition.
10. Legacy path retirement only after the agreed rollback window.

### 14.3 Rollback

- Disable the phase-specific feature flag.
- Restore the backed-up script versions if required.
- Leave canonical payloads in place for diagnosis; do not promote them into legacy paths.
- Record rollback reason and affected run IDs.
- Re-run from the last governed stage boundary, not from an ambiguous partial output.

---

## 15. Observability and operating metrics

Every run must report:

- unique datasets requested;
- cache exact hits;
- superset hits;
- partial fetches;
- provider logical requests;
- physical HTTP requests including pagination;
- retries and provider failures;
- unauthorised requests blocked;
- calls by pipeline stage;
- tickers entering, surviving and dropping at each stage;
- dataset ages and completeness;
- data reused across consumers;
- expected request budget versus actual request count.

Initial service objectives:

| Metric | Target |
|---|---:|
| Same-session historical calls on replay | 0 |
| Backfill historical provider calls in normal run | 0 |
| GARCH historical provider calls in normal run | 0 |
| Options historical-close provider calls | 0 |
| Dedicated sector-history calls with canonical ETF data | 0 |
| Unauthorised downstream calls after terminal drop | 0 |
| Unreconciled stage rows | 0 |
| Provider requests without a recorded reason | 0 |

---

## 16. Risks and controls

| Risk | Control |
|---|---|
| Reusing stale data | Dataset-class freshness policy and immutable session IDs |
| Mixing provider adjustment conventions | Explicit adjustment metadata and authoritative-source rule |
| One stage needs a longer history | Superset/missing-range resolution rather than refetching all data |
| Incorrect global ticker drop | Capability-specific states and worklists |
| Dropped ticker reintroduced by join | Worklist subset invariant and gateway authorisation guard |
| SQLite writer contention | WAL mode, short transactions and payloads outside SQLite |
| Partial payload corruption | Temporary write, validation, hash and atomic promotion |
| Option-chain scope mismatch | Scope fingerprints and superset checks |
| Morning data mistaken for EOD | Separate namespaces, schemas and TTLs |
| Migration changes signals | Frozen replay, dual-read comparison and phased cutover |
| Rollback loses new data | Feature flags and non-destructive legacy preservation |

---

## 17. Definition of done

The project is complete when:

- all active core consumers use the canonical gateway;
- Discovery updates each required ticker history at most once per completed session;
- Packages, Vanguard, Options and GARCH reuse that history;
- Scanner and Options reuse governed option snapshots where their freshness and scope contracts permit;
- Polygon option-chain calls occur only as documented fallbacks;
- sector calculations reuse canonical ETF observations;
- every stage consumes an explicit governed worklist;
- terminally dropped tickers cannot cause later provider calls;
- route-specific drops preserve only explicitly authorised capabilities;
- morning/live data remains separate and is fetched only for the morning worklist;
- a completed run can be reproduced without network access;
- API requests, data lineage and lifecycle decisions are fully auditable;
- rollback has been tested successfully;
- the legacy direct-fetch paths have completed their rollback window and are formally retired.

---

## 18. Immediate next development step

Begin **CDS-0 and CDS-1 together**:

1. Freeze and back up the current baseline.
2. Implement dataset contracts, the registry schema, the ticker lifecycle and the request ledger.
3. Add feature flags with all new behaviour disabled.
4. Add unit tests for lifecycle authorisation and dataset resolution.
5. Do not cut over a production consumer until the control plane and rollback tests pass.

The first consumer cutover after that foundation is canonical OHLCV, because it removes the largest verified duplication and supplies Discovery, Vanguard, Options volatility calculations and GARCH from one governed dataset.
