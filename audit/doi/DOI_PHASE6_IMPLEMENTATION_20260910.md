# DOI-6 Dynamic Lifecycle and Re-ranking — Implementation Report

**Date:** 2026-09-10  
**Design:** AVS-SD-DOI-001 v1.1  
**Result:** OFFLINE ACCEPTED  
**Next phase:** DOI-7 outcome-label capture

## Delivered

- A provider- and persistence-agnostic lifecycle domain with explicit
  completed-session, Morning Gate, intraday-material and manual-refresh
  evaluation points.
- Versioned material-change detection for spot/proximity, spread, volume, IV,
  DTE boundary, contract identity and governed thesis-version changes.
- Advisory thesis-condition observations for developing, confirmed, breached,
  recovering, target-touched, elapsed-reassess and data-insufficient states.
- CALL/PUT-symmetric breach and recovery calculations. These observations do
  not invalidate, remove or reverse the governed thesis.
- Contract maturation, degradation and expiry transitions that retain the
  ticker and its history.
- Deterministic hysteresis: a replacement must clear a disclosed utility
  margin, have adequate exact observation quality and remain no worse under
  the adverse stress measure. The margin is explicitly an uncalibrated
  operational policy, not a probability or fitted threshold.
- Exact-contract supersession linked to the previous preferred decision.
  Replacement requires a current assessment, exact OCC identity and complete
  DOI-5 valuation metadata. Economics from the old contract cannot carry over.
- Append-only `doi_lifecycle_events` persistence inside the existing canonical
  control plane, with immutable update/delete triggers and a distinct schema
  version marker.
- Restart-safe event and preferred-decision readers, including replay of an
  older event after a newer supersession has already been appended.
- Completed-session evaluation with re-ranking, plus Morning Gate condition
  evaluation that works without a new option quote. Without refreshed option
  evidence, Morning Gate records the thesis condition but does not fabricate a
  new preferred-contract decision.
- Aggregate lifecycle diagnostics for material observations, maturation,
  degradation, expiry, supersession, hysteresis, switches, provider calls and
  row reconciliation.

## Authority and non-discard boundary

DOI-6 has `decision_authority=NONE` and `execution_authority=HUMAN_ONLY`. It
cannot change CALL to PUT, change target/invalidation, grant or deny capital,
execute a trade, close a position, or delete an opportunity. A gap, missed
entry, breached thesis condition, elapsed horizon, missing quote or expired
contract remains visible as evidence for human review.

## Persistence and rollback

The schema is additive. It extends the existing CDS control plane rather than
creating a competing raw-data store. Production data was not migrated or
written during offline tests or the frozen-chain rehearsal. The live database
file hash changed while existing Intelligence Lab processes were running, so
file hash was not used as a false proof of immutability. Read-only logical
comparison against the online backup confirmed identical relevant table
populations and schema versions, and confirmed that neither database yet
contained the DOI-6 table.

Rollback snapshot:

- `backups/doi_phase6_20260910/control_plane.sqlite`
- `backups/doi_phase6_20260910/option_liquidity_lifecycle.py`
- `backups/doi_phase6_20260910/canonical_data__init__.py`
- `backups/doi_phase6_20260910/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md`

## Verification

| Check | Result |
|---|---:|
| DOI-6 focused tests | 16/16 PASS |
| DOI-1 through DOI-6 selected regression | 65/65 PASS |
| Existing option lifecycle + Morning authority | 16/16 PASS |
| Compilation | PASS |
| Frozen canonical-chain rehearsal | PASS |
| Provider calls in DOI-6 | 0 |
| Production database writes by DOI-6 verification | 0 |

Two additional pytest-based authority modules remain unavailable under the
active Python 3.14 test runtime because `pytest` is not installed. This is the
same disclosed environment gap as DOI-5 and is not represented as a pass.

## Real canonical-chain rehearsal

Frozen canonical MarketData chain:

- ticker: **A**;
- completed session: **2026-09-08**;
- dataset: `778fe0d37a39194098d0039a0aab3deae7f3a9a5e1a8b41a3b0b5ad18a50b05e`;
- source rows: **242**;
- governed CALL family candidates: **89**;
- assessed contracts: **89**;
- initial lifecycle transitions: **89**;
- preferred contract: `A261016C00170000`;
- event replay reused: **true**;
- decision replay reused: **true**;
- Morning condition at 139.50 without option refresh:
  `THESIS_CONDITION_BREACHED`;
- opportunity retained: **true**;
- new Morning preferred decision without fresh option evidence: **false**;
- authority violations: **0**;
- provider calls: **0**.

The rehearsal's market assumptions are the fixed DOI-5 test assumptions. It
does not claim that the selected contract is a live recommendation.

## Files

- `domain/dynamic_options_lifecycle.py`
- `canonical_data/dynamic_options_lifecycle.py`
- `canonical_data/option_liquidity_lifecycle.py`
- `canonical_data/__init__.py`
- `tests/test_dynamic_options_lifecycle.py`
- `audit/doi/doi6_real_chain_rehearsal.py`
- `docs/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md`

## Promotion boundary

DOI-6 is deployed as importable production-domain and canonical application
code and is offline accepted. The completed-session and Morning Gate methods
are implemented, but DOI still does not replace the live legacy selector or
publish to the Intelligence Lab. This is intentional phase isolation: DOI-7
must capture outcome labels; DOI-8/9 must validate probability/ranking models;
DOI-10 owns live Lab/Interpreter projection; DOI-11 owns controlled production
acceptance.
