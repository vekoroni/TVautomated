# OLM Live Series Repair — Solution Design

Date: 2026-08-30  
Status: Implemented and replay-validated; fresh production cycle pending  
Affected run: `20260829_222259`

## 1. Problem statement

The first complete OLM-active evening run fetched 982 authorised MarketData option chains successfully, then converted every one of those ticker results into a pipeline-error row. The production context stores the originating signal as a pandas `Series` under `ctx["_signal_row"]`. Several OLM handoff expressions used:

```python
ctx.get("_signal_row") or {}
```

Python therefore attempted to reduce the entire Series to one Boolean. Pandas rejects that operation with `ValueError: The truth value of a Series is ambiguous`.

The pipeline failed closed: all 1,316 Options Intelligence rows were blocked and capital permission remained `NO`. This prevented false execution, but it also removed all valid contract and lifecycle output, produced no EOD candidate manifest, and made TC-07, TC-08 and §8.3 impossible to validate on live data.

## 2. Scope

This repair is limited to safe retrieval of the already-captured signal row and production-shaped regression coverage. It must not change:

- direction governance;
- chain acquisition authority;
- contract selection, ranking or bounding;
- OI/volume ranking policy;
- lifecycle formulas or transition precedence;
- execution/capital authority;
- macro authority;
- database schemas or canonical payloads.

## 3. Design

### 3.1 One safe adapter

Add one side-effect-free helper that returns the context signal row only when it is mapping-like (`.get` is available). It must use explicit `None`/type handling and must never test a pandas object for truthiness.

Accepted inputs:

- pandas `Series` — returned unchanged;
- dictionary/mapping-like object — returned unchanged;
- missing, `None`, scalar or malformed value — replaced with an empty dictionary.

### 3.2 Replace every ambiguous access

Use the adapter in both live branches:

1. selected-contract lifecycle construction, including as-of date and GARCH forecast lookup;
2. no-primary-contract repair handoff, including deterministic thesis ID construction.

An invariant test will scan the module to prevent the unsafe `ctx.get("_signal_row") or {}` pattern from returning.

### 3.3 Failure policy

Missing signal-row fields remain explicit lifecycle data gaps and route to contract repair/manual review under existing rules. The adapter cannot create defaults that grant execution permission.

### 3.4 Cache-only replay control

The already-defined `AVSHUNTER_CANONICAL_OFFLINE_REPLAY` control must be enforced by the canonical option-chain service and Options Intelligence runner. In replay mode, a cache miss or invalid cached payload returns an explicit `OFFLINE_CACHE_MISS` result and never invokes MarketData. Authentication probes, exact-contract enrichment, sector lookups, history fallbacks and NBBO lookups are also disabled; stored inputs and canonical data are the only permitted evidence. Lifecycle fields are computed into the replay output, but historical thesis/observation tables are immutable when write-through is off. Normal evening runs retain their existing write-through/provider behaviour because the control defaults to off.

## 4. Test design

1. Unit-test the adapter with Series, dict, `None` and invalid scalar inputs.
2. Pass a real pandas Series through `_options_liquidity_lifecycle_fields()` and confirm a versioned EOD lifecycle baton is produced.
3. Exercise `process_ticker()` with a real pandas Series, a governed direction, a cached-shaped chain and no selected primary contract. Confirm it returns `CONTRACT_REPRICE_REQUIRED` rather than a pipeline exception and publishes repair-selector diagnostics.
4. Assert the unsafe truthiness pattern is absent.
5. Re-run the complete OLM regression pack.
6. Prove that an offline cache miss cannot invoke the provider callback.
7. Prove that auxiliary quote, sector and NBBO paths are provider-free in replay mode.
8. Prove that replay mode cannot persist or revise historical lifecycle state.

## 5. Replay and acceptance

The failed run already persisted 982 canonical chain payloads for completed session `2026-08-28`. Replay must use a separate validation output/run identifier or a controlled stage replay so the failed historical evidence remains intact.

Acceptance requires:

- canonical cache/superset resolutions rather than new provider fetches for the 982 stored chains;
- zero pandas-Series ambiguity errors;
- non-zero repair-selector invocation coverage where governed chains exist;
- exact reconciliation between per-row §8.3 counters and the run summary;
- populated lifecycle contract, thesis, liquidity and transition fields;
- zero lifecycle/action contradictions;
- valid EOD candidate manifest and clean handoff audit;
- Morning Gate remains blocked until the repaired evening evidence passes.

## 6. Rollback

Pre-change files are stored under:

`backups/olm_live_series_repair_prechange_20260830_012331`

Rollback restores only the Options Intelligence script and the affected test files. Canonical option-chain payloads and the failed run directory are evidence and must not be deleted or overwritten.

## 7. Implementation and acceptance record

The repair was implemented on 2026-08-30 with the following controls:

- one mapping-safe `_context_signal_row()` adapter now owns access to the captured pandas Series;
- both selected-contract and repair/stand-down paths use the adapter;
- the successful selected-contract handoff now publishes the same governed-direction record, version and hashes as the stand-down path;
- canonical offline replay returns `OFFLINE_CACHE_MISS` without invoking a provider;
- provider authentication, auxiliary quote, sector, history and NBBO lookups are disabled during offline replay;
- lifecycle fields are calculated for replay evidence, but write-through to historical lifecycle tables is disabled.

Executed evidence:

- protected regression pack: 212 tests, 0 failures, 0 errors, 0 skipped;
- controlled Options Intelligence replay: 1,316/1,316 rows completed with zero Series ambiguity errors;
- canonical request-ledger delta for the replay: +982 cache hits, +2 cache misses and +0 physical requests;
- 972/972 selected-contract rows contain governed direction, policy version/hash and governed-direction record/hash;
- execution-gate replay: 0 actionable rows; all 1,316 records were governed by lifecycle or direction state;
- EOD replay manifest: 982 rows and 475 columns, with 0 rows ready for capital before a real morning requote.

Replay evidence is isolated under:

`data/output/runs/20260829_222259/options_replay_seriesfix_20260830`

The original `final_run_manifest.json` remains unchanged and failed because its EOD candidate manifest was missing. The replay proves the code repair and downstream fail-closed behavior; it does not rewrite that historical run into a successful production run. Final operational acceptance requires one fresh normal evening cycle followed by its Morning Gate. Morning Gate must not be run against the failed original manifest.
