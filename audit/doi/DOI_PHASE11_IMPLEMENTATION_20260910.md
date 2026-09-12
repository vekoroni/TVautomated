# DOI-11 — Controlled production integration and acceptance

**Date:** 2026-09-10  
**Status:** IMPLEMENTED — OFFLINE ACCEPTED; LIVE CYCLE PENDING  
**Authority:** advisory only; human execution remains mandatory

## Delivered

- A governed runtime configuration enables DOI in production while fixing
  provider acquisition to `false`, decision authority to `NONE`, execution
  authority to `HUMAN_ONLY`, and ticker failures to retain-and-report.
- The evening orchestrator invokes DOI after final horizon propagation. DOI
  therefore receives the governed 1–20 session hold, not the provisional
  Options Intelligence horizon.
- The production coordinator reuses canonical completed-session option chains,
  preserves every input ticker and emits an atomic aggregate report.
- Existing OLM thesis events are reused. DOI no longer attempts to append a
  duplicate upstream thesis event, which the real-data rehearsal proved would
  create optimistic-concurrency conflicts.
- The complete structurally valid family and its exclusion taxonomy are stored.
  Production valuation and ranking operate on the deterministic diversified
  12-contract display set, bounding runtime without using OI, volume, spread,
  entry or exit timing as a ticker-level discard rule.
- Aggregate diagnostics include full/bounded candidate counts, low-OI and
  zero-volume retention, canonical reuse, physical fetch count, family stages,
  exception count and state distribution.
- A read-only acceptance assessor distinguishes offline completion, evening
  acceptance, pending Morning Gate and complete production acceptance.
- A byte-identical pre-DOI control-plane database is preserved at
  `backups/doi_phase11_20260910/control_plane.pre_doi11.sqlite`.

## Verification

- DOI-1 through DOI-11 regression: **120 passed / 0 failed**.
- Focused DOI-11 tests: **5 passed / 0 failed**.
- Python compilation: PASS.
- Git diff whitespace check: PASS.
- Same-run immutable restart: PASS.
- CALL and PUT symmetry: PASS.
- Missing-data/non-directional exception retention: PASS.
- Wide-family bound: 20 structurally valid / 12 valued, with all 20 retained in
  the family taxonomy.
- Real production-data rehearsal on an isolated control-plane copy:
  - tickers: **20/20 retained**;
  - directions: **10 CALL / 10 PUT**;
  - full family candidates audited: **6,740**;
  - bounded candidates valued/ranked: **240**;
  - canonical chain reuses: **20**;
  - physical provider calls: **0**;
  - exceptions: **0**;
  - elapsed time: **48.268 seconds**.

## Acceptance boundary

The latest stored run (`20260909_071646`) predates DOI-11 and cannot be used to
claim production acceptance. It correctly lacks a DOI run report, DOI tables
and projected DOI fields. One fresh evening run must create those artefacts.
The next valid Morning Gate must then be assessed against that same run ID.

Run after the new evening cycle:

```powershell
python tools\doi11_production_readiness.py --run-id <RUN_ID>
```

Run after Morning Gate:

```powershell
python tools\doi11_production_readiness.py --run-id <RUN_ID> --require-morning
```

No calibrated probability is claimed until real DOI-7 cohorts independently
pass the DOI-8 temporal calibration gates.
