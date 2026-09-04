# CDS-3 Implementation Record — 24 August 2026

## Decision and safety state

CDS-2 is promoted for canonical historical-price reads. CDS-3 is now in
controlled shadow publication. Production stage-gating remains disabled via
`AVSHUNTER_STAGE_GATING_ENFORCED=0` until Discovery, Packages, Vanguard,
Options, GARCH and Morning all publish and reconcile governed worklists.

This increment does not change signal scoring, candidate selection, package
membership or trading verdicts.

## Increment 1 — enforcement primitives

Implemented:

- persisted worklist membership as an additional gateway authorisation rule;
- a blocked request remains a zero-physical-request ledger entry;
- exact `input = survivors + drops + errors` reconciliation;
- fail-closed rejection when a join introduces an absent ticker;
- sentinel regression proving a terminally dropped ticker cannot re-enter or
  create a later provider request.

Files:

- `canonical_data/gateway.py`
- `canonical_data/lifecycle.py`
- `canonical_data/worklist_gate.py`
- `canonical_data/errors.py`
- `tests/test_canonical_data_system.py`

## Increment 2 — Discovery to Packages shadow publication

Implemented:

- Discovery writes `discovery_lifecycle_<run_id>.csv` with exactly one outcome
  per universe input;
- survivors are classified `ACTIVE_CORE` for `PACKAGES`;
- missing price histories are classified `DROPPED_TERMINAL_DATA` with
  `NO_PRICE_DATA`;
- no-signal rows are classified `DROPPED_STAGE` with
  `NO_SIGNAL_AT_ANY_HORIZON`;
- Discovery summary and run manifest contain lifecycle reconciliation counts;
- the lifecycle CSV is pinned inside the immutable run directory;
- the orchestrator publishes the lifecycle events and the Packages daily-OHLCV
  worklist into `data/canonical/control_plane.sqlite`;
- each run receives
  `runs/<run_id>/canonical/cds3_discovery_publication_<run_id>.json`;
- republication is idempotent and conflicting republication fails closed;
- publication is SHADOW and does not yet filter the legacy package build.
- when `AVSHUNTER_STAGE_GATING_ENFORCED=1` is explicitly set, the orchestrator
  materialises `discovery_candidates_cds3_<run_id>.csv`, proves exact parity
  with the persisted Packages worklist and passes that governed file to the
  package builder; missing, duplicate or unexpected tickers abort the stage;
- the production default remains `0`, so this cutover seam is built and tested
  but is not yet authoritative.

Files:

- `avshunter_discovery_ULTIMATE.py`
- `intelligent_orchestrator.py`
- `canonical_data/discovery_publisher.py`
- `canonical_data/__init__.py`
- `tests/test_canonical_data_system.py`
- `tests/test_cds2_historical_prices.py`

## Tests and evidence

- AST parsing: 6 changed Python modules passed.
- Canonical/CDS-2 combined regression: 31 tests passed.
- CDS-3 focused suite after integration test: 20 tests passed.
- Temporary orchestrator smoke: 2 input tickers reconciled to 1 survivor,
  1 drop and a one-ticker Packages worklist.
- Dropped sentinel: zero physical requests.
- Direct production command self-test reports `CDS-3 stage gating: SHADOW`.

## Backup and rollback

Pre-change backup:

`backups/cds3_discovery_worklist_prechange_20260824/`

Hashes:

- `avshunter_discovery_ULTIMATE.py`:
  `54119E40F890A7E214601B13E8F4B665E06B91801BB0A56596C681A155D29319`
- `intelligent_orchestrator.py`:
  `91A11E78A87143DA1D8944E2E11D9EC6E5247958303C0056F571D106A6B836F2`

Rollback is to restore those two backed-up files and leave
`AVSHUNTER_STAGE_GATING_ENFORCED=0`. New CDS-3 metadata is additive; it is not
used as production authority at this stage.

## Next sequence

1. Run one fresh evening pipeline and verify the Discovery lifecycle report
   reconciles the real universe exactly.
2. Compare the governed Packages worklist with the actual package index and
   require zero missing/unexpected tickers.
3. After real-run parity is accepted, enable Packages governed consumption for
   a controlled run (the cutover seam is already built and tested).
4. Add Vanguard capability-specific outcomes and build the Options worklist.
5. Continue through Options, GARCH and Morning before enabling production
   stage-gating.

## Real-run validation — `20260824_220616`

Discovery reconciliation passed:

- universe inputs: 3,320;
- classified survivors: 1,626;
- classified drops: 1,694;
- errors/unclassified: 0;
- persisted Packages worklist: 1,626.

Packages parity initially failed:

- authorised Packages worklist: 1,626;
- actual package-index rows: 1,645;
- unexpected rows: 19;
- missing authorised rows: 0;
- 13 of the 19 unexpected rows had already been dropped by Discovery;
- the remaining 6 were outside the Discovery lifecycle;
- 17 unexpected rows entered Vanguard, 2 were rejected there, and none entered
  Options or GARCH.

Root cause: `apply_external_intel_review_lane.py` ran after Discovery lifecycle
finalisation and appended 19 catalyst/macro-only tickers directly into the core
Discovery CSV. This violated both the lifecycle invariant and the macro-agnostic
core boundary. The CDS-3 fail-closed Packages seam would have blocked promotion.

### Isolation repair — 25 August 2026

- Existing Discovery survivors may still receive additive external-intelligence
  annotations.
- Missing catalyst/macro-only tickers are now written to
  `external_intel_review_candidates_<run_id>.csv`.
- The core Discovery row count and ticker membership cannot change.
- The advisory artifact is pinned with the run but is not passed to Packages,
  Vanguard, Options or GARCH.
- Report fields now include `core_membership_changed=false`,
  `appended_forced_review_rows=0`, and explicit advisory row counts.
- Regression proves macro/catalyst-only tickers remain absent from the core CSV.

Post-repair tests:

- AST parse passed for the three changed modules;
- 31 CDS/CDS-2 regressions passed;
- external-intelligence isolation regression passed.

Pre-repair backup:

`backups/cds3_external_intel_isolation_prechange_20260825/`

- `apply_external_intel_review_lane.py`:
  `AD5E39777114D6BFC4FFC7C5B2AC00C120E4374E436DD0CB39DE40860CA0074E`
- `intelligent_orchestrator.py`:
  `3F75C2546EA594A5BD5C1A3648FC92AFDEDAEA40A4C0EC6C79D56F93A37CDF3B`
- `test_external_intel_review_lane.py`:
  `A8B7C790932A673562BC06F7F1A1673CFD29F917838DAA5DA467AA2A8F23828D`
