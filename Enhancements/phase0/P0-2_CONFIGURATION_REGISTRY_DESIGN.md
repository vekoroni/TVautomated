# P0-2 — Configuration Registry: Design

| Item | Value |
|---|---|
| Version | 1.0 (16 Sep 2026) |
| Status | **APPROVED by ACK (16 Sep 2026)** — implementation authorised. |
| Context | C0 Run Context (cross-cutting: every context reads configuration through it) |
| Governed by | Specification v1.1 Appendix B (configuration governance), §4 (configuration versions in run identity), §15 (lineage), §24 (authority); end-to-end design v2.0 S0, rules R5, R7; `CLAUDE.md` |

---

## 1. Purpose

Every threshold, band, limit and tolerance the rebuild uses is a **versioned configuration item**, never a literal in domain code, so that:

- changing a value never silently changes the meaning of historical decisions;
- replay resolves the values that were in force at the replayed decision clock;
- every published aggregate can state exactly which configuration it used;
- a value that has not been validated can only drive shadow behaviour.

## 2. Current state (verified 16 Sep 2026)

| Source | What it is | Governance today |
|---|---|---|
| `config/*.json` (15 files) | Mixed settings: discovery, options, universe, runtimes, actuarial field registers, prompts | Unversioned; overwritten in place |
| `config/governed_constants_v1.json` | Provider completeness thresholds, volatility budget, contract economics, preferred-contract hysteresis, outcome learning | **Closest existing asset**: per-block `version`, `approved`, `approval_id` (e.g. `ACK-20260912-AVS-FIX-002`), owner, `validation_state`; its sha256 is recorded in `run_meta.config_identity.governed_constants_sha256`. No `effective_from`, no per-key history, no units vocabulary |
| `OrchestratorConfig` (`intelligent_orchestrator.py`, `cfg`) | Paths, stage switches, constants, environment overrides | Code literals |
| Environment variables | 57 distinct `AVSHUNTER_*` variables in production code and launchers (feature flags default OFF; set by `run_evening.bat` / `run_premarket.bat`) | Captured partly in `run_meta.resolved_feature_flags` |
| `contracts/dynamic_session_contract.py` `governed_runtime_profile_summary()` | Runtime profile with `release_id` and `sha256` | Recorded in `run_meta.ddd_runtime_profile` |
| Legacy module literals | Spread caps, delta bands, DTE windows, score weights across options, EOD, EIL, EV engines | None |

Decision: the registry is built for the **new contexts only** (strangler). Legacy configuration stays where it is until its consumer is retired; its file hashes continue to be recorded in run identity. A legacy value moves into the registry only when a new context needs it, with its provenance recorded.

## 3. Design

### 3.1 Configuration item (immutable entry)

```text
config_key           dotted, context-scoped, e.g. market_data.capture_coverage_threshold
version              integer, starts at 1, strictly increasing per key
value                JSON value (number, string, bool, list, object)
value_type           NUMBER | INTEGER | STRING | BOOLEAN | LIST | OBJECT
unit                 from the unit vocabulary (§3.4); "none" only for dimensionless enums/flags
effective_from       XNYS session date (inclusive) from which this version applies
validation_state     PROVISIONAL | VALIDATED | RETIRED
business_owner       e.g. ACK
approval_id          e.g. ACK-20260916-P0-2 (required for every entry)
rationale            why this value
evidence_ref         path/report id supporting the value (required when VALIDATED)
provenance           NEW | MIGRATED_FROM:<legacy source and key>
recorded_at_utc      when the entry was added
```

Rules:

1. Entries are **append-only**. A change is a new version with a later `effective_from`; existing entries are never edited or deleted. `RETIRED` is a new version.
2. `effective_from` of a new version must be **after** the latest completed session at the time of approval (no retroactive changes).
3. A key without an entry effective at the requested session is **unresolvable** → error. There are no defaults (spec Invariant B).
4. `VALIDATED` requires `evidence_ref`; only validation reports (C13 / replications) can justify it.

### 3.2 Storage

- **Repository-tracked JSON documents**, one per context: `config/registry/c0_run.json`, `c1_market_data.json`, `c2_universe.json`, … `c10_execution.json`.
- **Lock file** `config/registry/LOCK.json`: sha256 of every existing entry (key + version). A test fails if any locked entry changed or disappeared (enforces append-only).
- Why files rather than a database: changes are reviewable diffs, bound to a release commit, and available to replay at any commit because old versions stay in the file.
- JSON (stdlib) rather than YAML to avoid a new dependency.

### 3.3 Resolution and API (pure domain, no I/O in the resolver)

```python
registry = ConfigRegistry.from_documents(documents)            # loader validates schema, lock and units
snapshot = registry.resolve(session=date(2026, 9, 17))         # all keys effective at that session
value    = snapshot.get("market_data.capture_coverage_threshold")   # -> ConfigValue(value, unit, version, validation_state)
value    = snapshot.require_validated("ranking.hysteresis_margin") # raises unless VALIDATED
snapshot.snapshot_id                                           # sha256 over sorted (key, version, value)
```

- `ConfigSnapshot` is immutable and carries `snapshot_id`, `resolved_for_session`, and `(key, version)` pairs.
- **Authority coupling**: a context running with authority `AUTHORITATIVE` may only read `VALIDATED` values (`require_validated`); in `SHADOW` / `IMPLEMENTED_FOR_REPLICATION` it may read `PROVISIONAL` values. Reading a `RETIRED` value is an error.
- Resolution uses the run's decision clock (P0-3), never the wall clock.

### 3.4 Unit vocabulary (initial)

`sessions`, `calendar_days`, `fraction` (0–1), `percent` (0–100), `usd`, `usd_per_share`, `usd_per_contract`, `sigma`, `contracts`, `shares`, `credits`, `seconds`, `count`, `none`. Adding a unit is a registry change reviewed like any other.

### 3.5 Recording (lineage)

- `RunContext` records the `config_snapshot_id` resolved for the run (P0-3).
- Every published aggregate and ledger record carries `config_snapshot_id` (spec §15 "configuration versions").
- The snapshot itself (resolved key/version/value list) is written once per run to the run's artefacts and registered as a dataset, so a record can be interpreted without the repository.

### 3.6 Change process

1. Propose new version (value, unit, effective_from, rationale, evidence_ref if any).
2. ACK approval → `approval_id`.
3. Commit entry; lock file regenerated to include the new entry (old hashes unchanged).
4. Tests (§5) pass; release built (P0-3).

### 3.7 No literals in domain code

- New-context packages read thresholds only via a `ConfigSnapshot` passed in.
- Enforcement: (a) review checklist; (b) a test that every `config_key` referenced in code exists in the registry and every registry key is referenced (no orphans); (c) an AST check on new packages flagging numeric literals in comparisons, excluding an allow-list (0, 1, −1, mathematical constants, array indices).

## 4. Initial register (Phase 0 keys)

Values marked **PROPOSED** need ACK approval; all start `PROVISIONAL`. Keys for later phases (exit buffer, generation bands, hysteresis margin, supersession tolerances, EV_LB quantile, …) are registered when those contexts are designed, not now.

| config_key | Proposed value | Unit | Source / rationale |
|---|---|---|---|
| `run.production_requires_clean_tree` | true | none | Spec §4, rule R8 |
| `market_data.capture_panel_source` | `UNIVERSE_SNAPSHOT_PLUS_BENCHMARKS` | none | Spec §5 fixed capture panel |
| `market_data.benchmark_tickers` | ["SPY", "QQQ"] | none | Spec §5 |
| `market_data.capture_coverage_threshold` | 0.95 | fraction | Migrated from `governed_constants_v1.provider_completeness.normal_chain_fraction` |
| `market_data.history_max_staleness` | 0 | sessions | Invariant F: history must match the required session |
| `market_data.chain.from_offset` | 7 | calendar_days | Consistency with existing Phantom history request shape |
| `market_data.chain.to_offset` | 60 | calendar_days | As above |
| `market_data.chain.strike_limit` | 40 | count | As above (panel); full chain for benchmarks set separately in P0-4 |
| `market_data.chain.min_open_interest` | 1 | contracts | As above |
| `market_data.daily_credit_budget` | 100000 | credits | Paid tier, validated by ACK 16 Sep 2026 |
| `market_data.backfill_daily_credit_cap` | 30000 | credits | Phase 0 backfill design |
| `market_data.provider_settlement_delay` | 15 | minutes → stored as 900 `seconds` | Migrated from `governed_constants_v1.provider_completeness.provider_settlement_delay_minutes` |
| `eligibility.min_bars` | PROPOSED at P0-5 design | sessions | Set with C2 design |
| `legacy.flags.canonical_data_enabled` | true | none | Launcher sets `AVSHUNTER_CANONICAL_DATA_ENABLED` for the legacy orchestrator (was set only by the retired `.bat` files) |
| `legacy.flags.canonical_write_through` | true | none | As above, `AVSHUNTER_CANONICAL_WRITE_THROUGH` |
| `legacy.flags.cds2_ohlcv_mode` | `ACTIVE` | none | As above, `AVSHUNTER_CDS2_OHLCV_MODE` |
| `legacy.flags.dynamic_session` | current resolved values from run 0914 `run_meta.resolved_feature_flags` | none | Launcher sets them explicitly instead of relying on defaults or the shell |

## 5. Tests

1. Schema: every entry has all required fields; units in vocabulary; `VALIDATED` has `evidence_ref`.
2. Append-only: lock hashes unchanged; versions strictly increasing; `effective_from` non-decreasing by version.
3. Resolution: correct version per session boundary; unresolvable key raises; `RETIRED` raises; `require_validated` raises on `PROVISIONAL`.
4. Determinism: same registry + session → same `snapshot_id`.
5. Replay: resolving an earlier session after adding a new version returns the old value.
6. Coverage: no referenced-but-missing keys; no orphan keys.
7. Literal scan on new packages (§3.7).

## 6. Deliverables

- `config/registry/` documents, `LOCK.json`, unit vocabulary.
- Pure resolver module and loader in the new rebuild package (layout in P0-3 §3.1).
- Tests (§5).
- Snapshot artefact writer used by the P0-3 launcher.

## 6a. Implementation status (16 Sep 2026)

| Deliverable | Status |
|---|---|
| `avshunter/config/` (model, pure resolver, file adapters, CLI `python -m avshunter.config check\|lock\|resolve`) | Done |
| `avshunter/shared/xnys_calendar.py` (provenance copy of the legacy calendar; parity test 2021–2030) | Done |
| `config/registry/c0_run.json`, `c1_market_data.json`, `LOCK.json` — 17 Phase 0 entries, all `PROVISIONAL`, effective 2026-09-17 | Done |
| `tests_rebuild/` (isolated, network blocked): schema, history, resolution, authority coupling, lock, snapshot writer, committed-registry check, wall-clock / literal / `sys.path` purity scans | Done — 33 passed (venv, Python 3.13); registry CLI also verified on `C:\Python314` (3.14 has no pytest installed) |
| §5 test 6 (every referenced key exists, no orphan keys) | Deferred to P0-3: the first consumers of these keys are the launcher and capture services |
| Snapshot recorded in RunContext | Deferred to P0-3 |

## 7. Decisions requested

1. Approve the design (append-only JSON registry per context, lock file, authority coupling, no defaults).
2. Approve the Phase 0 initial register values in §4 (all `PROVISIONAL`).
3. Confirm the scope rule: new contexts only; legacy configuration migrates key-by-key when a new context needs it.
