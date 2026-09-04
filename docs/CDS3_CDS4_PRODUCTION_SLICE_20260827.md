# CDS-3/CDS-4 Production Slice — 27 August 2026

## Outcome

The production command `python intelligent_orchestrator.py --evening` now
enforces the governed Discovery-to-Packages worklist and publishes the exact
post-direction Options option-chain worklist before acquisition.

The Options layer now resolves one canonical EOD chain per ticker/session/scope.
MarketData is called first. Polygon full-chain retrieval occurs only when the
MarketData response is empty or fails. Successful responses are persisted as
Parquet, registered in the CDS dataset registry and reused on a same-session
rerun. Missing deliverable multipliers continue to use the existing bounded
selected-contract reference lookup; a second full Polygon chain is no longer
required for every ticker.

This release does not mix EOD chains with Morning live quotes.

## Production controls

- `AVSHUNTER_STAGE_GATING_ENFORCED` defaults to `1` in the orchestrator.
- Explicitly setting it to `0` remains the rollback switch.
- Missing lifecycle records, changed same-run worklists and failed
  reconciliation abort before provider acquisition.
- A failed or empty Options output aborts the enforced Evening workflow; the
  pipeline cannot continue to a superficially healthy but unusable Lab book.
- `STRANGLE`, `UNRESOLVED`, parse-defect and scope-excluded rows remain in the
  Options audit output but receive no option-chain authority.
- Every cache miss, provider attempt, cache hit and blocked request is recorded
  in `data/canonical/control_plane.sqlite`.

## Persistence

- Registry: `data/canonical/control_plane.sqlite`
- Payloads: `data/canonical/options/<session>/<ticker>/<scope>.parquet`
- Dataset type: `OPTION_CHAIN`
- Schema: `option_chain_v1`
- Identity: ticker + session + normalised scope + content hash

## Verification

- Python compilation: passed.
- CDS-3/CDS-4, control-plane and CDS-2 regression: 37 tests passed.
- Post-optimisation CDS-3/CDS-4 and control-plane regression: 24 tests passed.
- Direction-governance focused checks: 14 passed.
- Orchestrator startup self-test: `CDS-3 stage gating: ENFORCED` and CDS-2 child
  inheritance passed.
- Primary/fallback integration: MarketData success generated zero Polygon
  calls; MarketData empty generated exactly one Polygon fallback.
- 1,500-ticker worklist performance test: reconciled 1,200 authorised and 300
  equity-only rows in 0.179 seconds.
- No live API or production Evening workflow was executed during testing.

## Backup and rollback

Pre-change archive:

`backups/cds3_cds4_prechange_20260827_2/prechange.zip`

SHA-256:

`93C7419508A9670DC3ED7BD311B1392659639ADF3B26B72325170CD4A9408B78`

Fast rollback is to set `AVSHUNTER_STAGE_GATING_ENFORCED=0`. Full code rollback
is restoration from the archive followed by hash verification.

## Scheduled Evening acceptance

The first scheduled Evening run must prove:

1. Discovery/Packages reconciliation with `enforcement_enabled=true`.
2. An Options `OPTION_CHAIN` worklist exists for the current run.
3. Non-directional rows have no provider ledger entries.
4. MarketData successes have no Polygon full-chain entry.
5. Polygon entries are paired with an explicit MarketData primary failure.
6. Every persisted chain has a dataset registry record and readable payload.
7. Options outputs, GDR artifacts and final run manifest complete normally.

## Remaining CDS boundary

This closes the production-critical Packages/Options acquisition slice, not the
whole CDS programme. Remaining work is current-run GARCH and Morning worklists,
the Morning live TTL namespace, Scanner reuse of the canonical chain, shared
sector-derived caching, gateway-only static enforcement, offline replay and
legacy retirement.
