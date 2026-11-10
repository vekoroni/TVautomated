# Macro delivery and publication ownership

The `macro_delivery_v1` configuration remains `FULL`. Exact-byte intake receives
the three existing advisory producers (US Money Index, News and Events), validates
contracts, retains source identity and hashes, and preserves unknown values and
disabled execution authority. It does not generate research or call a model.

## FULL publication

The export monitor delivers accepted files and stops. Only the scheduled Windows
PreOpen/PostClose runner owns the fresh AI analysis and board build. Afterwards,
verify accepted hashes against `extras.research_source_manifest`; a successful
delivery receipt alone is not evidence of model consumption.

Events is a materialised, merged view: its `sha256` identifies that view and
`accepted_source_sha256` identifies the current accepted raw export. The event
ledger and immutable raw archive retain the underlying versions; these identities
must not be confused when verifying consumption.

The data-only publisher returns SKIPPED without reading a recovery seed, taking a
publication lock or writing under FULL. Direct publication and recovery entry
points enforce the same guard. DATA_ONLY publication is permitted only when that
mode is explicitly configured; unknown modes fail closed.

## Delivery contention

Only research-delivery writer contention (`DELIVERY_WRITER_BUSY`, `writer already
locked`, or its exit code 3) is DEFERRED. The runner continues with accepted files;
other failures remain failures. A deferred delivery is not proof of new coverage.

## Scope and verification

Pickup window: 06:00-20:00. The existing monitor cadence and Windows schedules are
not changed by this branch. The existing `$waitsPastGuard` PostClose timing formula
is retained verbatim. No recurring paid authority is granted by this document.

Offline tests cover publication no-write guards, recovery integrity, exact-byte
delivery, advisory/USMI unknown-value safety, lock deferral, and PlanOnly runner
ordering and skip switches. The GEX assertions use the stable step prefix rather
than coupling to its display label; no GEX acquisition change is included.

Branch base: the already-pushed `high-convexity-watchlist` revision f4968c7. Only
delivery dependencies and selected runner/builder wiring are added; unrelated live
producer, GEX-refresh, futures-refresh, Lab, board and pipeline edits are excluded.
