# AVS-SD-MACRO-INPUT-GOVERNANCE v1

## Purpose

Rebuild the Macro bounded context so that complete, lineaged market evidence is
converted into one coherent advisory packet. Macro never owns candidate
membership, ticker direction, contract selection, capital allocation or
execution permission.

## Business outcome

The Intelligence pipeline receives a point-in-time macro explanation whose
numbers, narrative and coverage state refer to the same source evidence. A
missing domain remains explicit. It is never silently converted to a neutral
observation.

## DDD boundaries

### Market-data producers

Own provider calls and raw observations. They publish files but do not decide
macro meaning.

### Macro input governance domain

`domain/macro_input_governance.py` owns:

- immutable evidence identity;
- required capture-batch coherence;
- GEX publication invariants;
- cadence-aware FRED semantics;
- domain coverage states;
- schema-aware prompt projection;
- advisory authority policy.

It performs no provider calls and writes no files.

### Macro input repository

`canonical_data/macro_input_manifest.py` archives manifests by SHA-256 and
atomically advances the latest-manifest pointer. It owns persistence, not
business meaning.

### Macro synthesis

`build_macro_json.py` loads governed evidence, calls the configured model,
applies canonical deterministic observations, reconciles conflicts, checks
coherence and atomically publishes the result.

### Pipeline consumption

`intelligent_orchestrator.py` verifies embedded source lineage before accepting
the packet. Invalid or superseded macro evidence is unavailable advisory input;
it does not stop the independent core thesis pipeline.

`scripts/macro_quant_packet.py` carries the input-manifest identity and always
sets `macro_authority=ADVISORY_ONLY`.

### Completed-session GEX synchronisation

`orchestrator/completed_session_gex.py` owns the daily/evening reconciliation:

- a hash-valid daily GEX publication for the required XNYS session is reused;
- reuse performs no provider request and does not rewrite the daily files;
- a stale, missing or invalid daily publication is refreshed from the exact
  required session into the run directory;
- the refreshed observation is applied to a run-scoped macro view;
- the governed base macro and its input evidence remain immutable;
- only the three GEX input keys may be explicitly superseded by a validated
  exact-session runtime overlay; changes to every other input still fail
  lineage verification.

## Data flow

```text
producers / canonical databases
          |
          v
dropbox/market_data
          |
          v
MacroInputManifest (hashes, sessions, dataset ids, coverage)
          |
          +--> GEX atomic validation
          +--> cadence-aware FRED observations
          +--> complete threshold/sector/cross-asset records
          +--> semantic GEX walls/flip/top exposures
          |
          v
model synthesis
          |
          v
deterministic reconciliation + coherence gate
          |
          v
atomic macro_intelligence_latest.json
          |
          +--> daily GEX current: reuse unchanged
          |
          +--> daily GEX stale: exact-session run-scoped refresh
          |
          v
run-scoped GEX-synchronised advisory macro quant packet
```

## Implemented invariants

1. Required inputs form a bounded capture cohort rather than pretending that
   independent Colab producers share one run ID or IP address. Runtime identity
   and IP are non-evidentiary. `report`, `macro` and `forward_bias` may retain
   distinct producer IDs when their filename capture date/times all fall inside
   the governed 15-minute cohort window. Original filenames, capture times and
   hashes remain immutable and visible; wider or cross-cycle mixtures fail
   closed.
2. A GEX publication claiming `COMPLETE` requires proxy, by-strike and
   manifest together; partial presence, hash disagreement or session
   disagreement fails closed. A collector failure with explicit per-ticker
   failure states is a different observation: its published components must
   match their failure-receipt hashes, but the entire GEX domain becomes
   `SOURCE_UNAVAILABLE`. Its diagnostic bytes remain in the evidence archive;
   no GEX row, numeric value or old futures/GEX narrative reaches synthesis.
   Other valid macro domains may still publish as advisory.
3. Builder inputs are recorded with SHA-256, size, path, capture batch and
   observation dates.
4. Prompt inputs consist of complete JSON/CSV records. Character slicing is
   prohibited.
5. Every loaded source must appear in the consumption ledger as full records,
   an approved semantic projection, a bounded advisory or a replay baseline.
   Any `UNCONSUMED` source fails the build.
6. FRED is represented by the latest real observation for every series with
   inferred cadence and explicit source status.
7. USSLIND older than the governed limit remains quarantined.
8. Breadth, collection validation, direct volatility and VIX/DXY packets are
   registered instead of silently ignored.
9. The GEX prompt uses validated proxy values plus the ten largest absolute
   strike exposures for each ticker.
10. Existing GEX narratives are regenerated from the same rows used for the
   numeric override.
11. Every source byte is retained in a content-addressed evidence archive for
    replay even when the mutable drop folder is refreshed later.
12. Output and embedded input manifest identities must match before publication.
13. A later change to any non-GEX source byte makes the existing macro advisory
    unavailable until rebuilt. GEX may be superseded only by a separately
    validated, exact-session, run-scoped overlay.
14. Missing event, MOVE, correlation and dispersion domains are labelled
    `NOT_CONFIGURED`; no values are fabricated.
15. Macro authority is explicitly `ADVISORY_ONLY`, with candidate, direction,
    contract and capital authority all `NONE`.

## TDD acceptance criteria

- Tampering with a GEX component fails its manifest check.
- A hash-valid failed GEX publication cannot supply GEX numbers or halt
  unrelated macro domains; a claimed-complete partial publication still fails.
- Changing any input after synthesis fails consumer lineage verification.
- All 23 threshold rows and 11 sector rows survive prompt construction.
- Every manifest entry has a `CONSUMED` ledger record and exact archived bytes.
- FRED latest observations preserve their individual source dates.
- Semantic GEX context contains both SPY and QQQ and ranks strikes by absolute
  exposure rather than file order.
- The resulting macro quant packet carries the manifest identity.
- The orchestrator accepts a verified advisory packet and rejects a tampered
  packet without granting macro trade authority.
- Current daily GEX is reused without provider calls or source mutation.
- Stale daily GEX is refreshed only in the run scope and cannot rewrite the
  governed daily macro or its evidence files.
- GEX-only supersession is accepted when its overlay is exact-session and
  validated; unrelated source changes remain rejected.
- Existing Macro, US Money Index, completed-session and Interpreter handoff
  regression suites remain green.

## Deployment and rollback

The implementation is additive. Rollback consists of reverting the governed
builder, domain, repository and consumer changes. Immutable input manifests are
evidence artifacts and need not be deleted. The mutable latest macro pointer is
advanced only after manifest publication and output coherence pass.

## Deferred inputs

Event calendar, MOVE, correlation and dispersion remain explicit coverage gaps.
They require approved sources and must be introduced as separate domain
contracts; they are not blockers to publishing a partial advisory packet.
