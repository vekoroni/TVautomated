# DATA-PROJECTION-001 implementation report

**Status:** Offline implementation complete; controlled completed-session run pending  
**Design:** `docs/AVS-SD-DATA-PROJECTION-001_CANONICAL_DATABASE_FANOUT.md`  
**Authority:** Data movement and advisory macro evidence only  
**Execution authority:** None  
**Capital authority:** None

## Scope delivered

1. Canonical dataset registration and projection-event publication share one
   SQLite transaction.
2. Both production option-chain persistence paths request the Phantom
   projection.
3. Phantom stores immutable canonical revisions, maintains the existing
   session/contract read model and records idempotent projection receipts.
4. Interrupted projection deliveries are requeued; failures remain retryable
   and cannot delete or invalidate canonical evidence.
5. A normal completed-session run independently resolves SPY and QQQ chains
   for the exact required session, projects them to Phantom and verifies their
   receipts before calculating GEX.
6. GEX updates only the advisory macro block. If exact-session GEX cannot be
   produced, any prior numeric GEX is cleared and marked unavailable rather
   than masquerading as current evidence.
7. Point-in-time Actuarial features are frozen into each candidate decision and
   carried into the existing leakage-safe outcome-learning snapshot. Model
   promotion remains governed and disabled until its acceptance gates pass.
8. Projection health and retry diagnostics are available from the orchestrator
   log and `tools/reconcile_data_projections.py`.

Forced or partial-session GEX behavior was intentionally not added. The
production target is the normal completed-session pipeline.

## Verification

- Python compilation: PASS.
- Focused data-projection and Stage 6 pack: 36 PASS, 0 FAIL.
- Consolidated affected pack: 111 PASS, 0 FAIL.
- `git diff --check`: PASS; line-ending notices only.
- Read-only production queue inspection: schema not yet installed, zero queued
  events. This is expected because no production option-chain write has run
  since this additive code was installed.

The consolidated pack covers provider finality, dynamic session authority,
canonical registry behavior, both option-chain persistence paths, Phantom
idempotency and revisions, retry/restart behavior, exact-session GEX, stale-GEX
invalidation, macro behavior and Actuarial outcome-learning lineage.

## Production acceptance still required

Run one normal completed-session pipeline cycle. Acceptance requires:

- exact-session SPY and QQQ canonical dataset IDs;
- matching Phantom projection receipts;
- a GEX manifest whose session equals the run's completed session;
- a macro GEX block with the same session and `ADVISORY_ONLY` authority;
- zero stranded `PROCESSING` events;
- no unexplained `FAILED_RETRYABLE` events;
- successful candidate option-chain fan-out to Phantom without changing the
  opportunity population, direction or capital state.

The controlled run is production evidence, not an additional code dependency.
