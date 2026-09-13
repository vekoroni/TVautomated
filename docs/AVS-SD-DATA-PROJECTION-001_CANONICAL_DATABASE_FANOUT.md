# AVS-SD-DATA-PROJECTION-001 — Canonical database fan-out

**Status:** Implemented offline v1.0; controlled completed-session acceptance pending  
**Authority:** Data movement and lineage only  
**Trading authority:** None  
**Capital authority:** None

## 1. Business outcome

Every successful governed API acquisition must become reusable pipeline memory
without allowing independent writers to create conflicting versions of market
truth.  Current evidence must reach the live run, Phantom history, daily GEX
and the learning ledger with one immutable identity and an observable delivery
state.

The design must improve data availability and learning.  It must never remove
an opportunity, change CALL/PUT direction, select a contract, grant execution
permission or perform capital allocation.

## 2. Confirmed as-is gaps

1. Canonical option-chain services persist current MarketData observations, but
   Phantom is subsequently opened read-only and is not automatically updated.
2. Local GEX chooses the latest SPY/QQQ session available in Phantom rather
   than proving that it is the required completed session.
3. The macro builder treats a numeric GEX value as confirmed without proving
   session alignment.
4. The historical backfill utility has a seven-day safety lag.  That is valid
   for bulk research backfills but cannot determine daily production GEX.
5. Actuarial v7 is a separately built Parquet release.  Current point-in-time
   features and matured outcomes are not a direct projection of every canonical
   acquisition.
6. Projection failures are not represented as first-class pipeline-health
   states.

## 3. Target bounded contexts

### 3.1 Market Data

Owns provider acquisition, normalisation, finality, immutable payload storage
and canonical dataset registration.  It emits `CANONICAL_DATASET_COMMITTED`
events transactionally with registration.

### 3.2 Projection Delivery

Owns the durable outbox, idempotency, retry state and reconciliation.  It does
not calculate trading signals.

### 3.3 Phantom History

Projects completed option-chain datasets into append-only historical revisions
and maintains the legacy current-session compatibility table.  The canonical
dataset remains the raw-data authority.

### 3.4 Gamma Exposure

Subscribes to final SPY and QQQ completed-session projections.  It calculates
daily swing-horizon GEX only when both instruments prove the same required
session and quality thresholds pass.

### 3.5 Outcome Learning / Actuarial

Captures point-in-time feature observations immediately, matures labels only
after their horizons and builds an actuarial candidate release without future
leakage.  Promotion remains separately governed and validated.

## 4. Canonical event contract

One event is created for each requested projection of an immutable dataset.
Its identity is the SHA-256 of projection name, projection version and dataset
ID.  Re-registering or replaying the same dataset cannot create another event.

Required fields:

- event and projection version;
- projection name;
- canonical dataset ID and type;
- instrument and market session;
- content hash and storage URI;
- provider `as_of` timestamp;
- source run ID;
- event creation timestamp.

The event contains references, not duplicated market payloads.

## 5. Transaction and failure rules

Dataset registration and event insertion occur in the same SQLite transaction.
No API caller writes directly to Phantom, GEX or actuarial storage.

Projection delivery is at-least-once.  Every consumer is idempotent.  States
are `PENDING`, `PROCESSING`, `COMPLETED` and `FAILED_RETRYABLE`.  A projection
failure preserves the canonical dataset and becomes visible in Pipeline Health.

The core opportunity survives a Phantom, GEX or learning projection failure.
Only the affected advisory/history capability becomes pending or unavailable.

## 6. Phantom projection

Completed option chains are appended with their canonical dataset ID.  Exact
replay is a no-op.  A legitimate provider revision is retained as a new
revision and may supersede the compatibility view; it does not rewrite the
canonical source.

Full-chain storage is once per governed completed-session dataset.  Current
selected-contract observations remain in the option-liquidity lifecycle store
and are not expanded into repeated full-chain copies.

## 7. Daily GEX

The normal completed-session pipeline preflight must acquire or resolve SPY and
QQQ independently of the candidate universe.  After both Phantom projections
complete, the GEX service requires:

- the pipeline's required completed session;
- identical SPY and QQQ sessions;
- provider-finality eligibility;
- at least 25 usable 7–56 DTE contracts per instrument;
- at least 80% gamma coverage;
- immutable parent dataset IDs.

Successful calculation publishes canonical GEX, compatibility CSVs and a
hashed manifest before the macro packet is finalised.  Missing or failed GEX is
advisory-only and cannot block the core pipeline.  Forced/intraday behaviour is
out of scope by business decision.

## 8. Actuarial learning

Canonical acquisition triggers point-in-time feature capture, not immediate
model mutation.  Outcome maturation appends 1, 2, 3, 5, 10 and 20-session
labels to the Decision and Outcome Ledger.  A candidate actuarial release is
built only from leakage-safe matured observations.  Promotion requires the
existing coverage, calibration and held-out acceptance gates.

## 9. Source cadence

Freshness is relative to each publisher's legitimate cadence.  Daily market
data, weekly option-history maintenance and monthly/lagged economic releases
must not share one TTL.  Every component records observation time, expected
release/session, fetch time, age, quality and usability.  A newly written file
does not change the age of its source observation.

## 10. Implementation sequence

1. Add the pure canonical event contract and durable transactional outbox.
2. Emit Phantom events from both production option-chain persistence paths.
3. Add the idempotent Phantom projector and historical reconciliation command.
4. Add required-session SPY/QQQ acquisition and the daily GEX subscriber.
5. Enforce GEX session/finality in the macro assembler and expose freshness.
6. Project frozen features and matured outcomes into an actuarial candidate
   dataset; retain governed promotion.
7. Add projection-health diagnostics, retry tooling and release evidence.
8. Run unit, property, duplicate/restart, integration and stored-run replay
   tests before the controlled completed-session pipeline cycle.

## 11. Acceptance criteria

- One provider fetch creates one canonical dataset identity.
- The requested projection event is atomically present with that identity.
- Replay produces no duplicate events or Phantom observations.
- Projection failure cannot corrupt or delete canonical evidence.
- Daily GEX parent sessions equal the required completed session.
- Stale GEX remains visible but cannot contribute a current score.
- Actuarial labels contain no evidence after their recorded cutoff.
- No component introduced by this design has execution or capital authority.
