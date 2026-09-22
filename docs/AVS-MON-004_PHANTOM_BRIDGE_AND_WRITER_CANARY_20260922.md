# AVS-MON-004 — Phantom outcome bridge and writer canary

**Date:** 22 September 2026
**Production activation:** **OFF** (`AVSHUNTER_OPTION_OUTCOME_CAPTURE_ENABLED` was unset).
**Authority:** hypothetical outcome research only; no market-data fetch, broker call, trade decision, realised-fill claim, or capital permission.

## Build

- `PhantomOutcomeSourceReader` opens the control-plane registry and Phantom in SQLite read-only/query-only mode. It asks for an exact ticker, OCC symbol, and completed-session dates. A row is admitted only if its immutable revision hash, projection receipt, and complete MarketData canonical dataset reconcile. Provider quote time, dataset as-of, creation, registration, and projection availability must precede the evaluation cutoff. Multiple same-as-of conflicting revisions fail closed.
- The outcome capture service uses registered control-plane observations first and asks Phantom only for missing exact-contract sessions. A verified quote is frozen into a separate append-only `doi_outcome_source_quotes` research table; it is **not** inserted into live `option_contract_observations` or used to reopen a terminal thesis. Outcome labels can reference that quote only after the persisted source ID, exact symbol, ticker, canonical dataset, and availability time validate.
- A backfilled quote can append a superseding label without altering the earlier label. The label's evidence cutoff now advances to the latest availability time of every source used; the underlying horizon date remains separately recorded. This fixes a test-reproduced temporal defect where a late option backfill appeared to have been known at the earlier underlying-bar close.
- The opt-in Evening hook is wired to the bridge. Missing Phantom defers capture; routine activation remains off. Source table creation happens only on this opt-in path, not during normal pipeline initialisation.

## Real-data replay, read-only

The 80-edge-sample canary contains 40 assessments from the 11 September session and 40 from 21 September. Forty had enough completed underlying data for a five-session evaluation. The raw `chain_snapshots` table had 11/40 complete exact-contract five-session paths, but the **verified canonical revision reader had 0/40**. For the mature one-session horizon it verified **37/40** exact-contract paths, 26/40 with two-sided quotes, with **zero provenance exceptions**. The difference is substantive: some `chain_snapshots` rows were written by direct backfill paths without a corresponding immutable `canonical_option_chain_revisions` record. They are not silently promoted to governed evidence.

Neither cohort has a matured 10- or 20-session underlying horizon. No win-rate or long-horizon model claim follows from this replay.

## Representative isolated writer canary

One real 11 September assessment, its 14 September completed price bar, run, family, origin observation, and both canonical dataset records were copied into a disposable dependency-closed SQLite store. The production control, price, and Phantom databases remained read-only. With the verified Phantom revision supplying its missing next-session quote:

| Check | Result |
| --- | ---: |
| First batch | 1 family scanned; 1 source row and 1 hypothetical label appended |
| Repeat batch | 1 family scanned; 0 new labels or sources |
| Coverage | 1 expected / 1 final / 0 pending |
| Foreign-key errors | 0 |
| First capture / repeat | 0.263 / 0.156 seconds |
| Temporary control-plane growth | 24,576 bytes |
| Temporary WAL before checkpoint | 111,272 bytes |

This proves a bounded append-only writer and replay path on a **one-assessment isolated copy**, not the latency or WAL growth of a production-scale capture batch. The small writer sample does not license a live schema/index migration.

## Acceptance and remaining work

The read-only bridge, one-session replay, isolated writer, correction lineage, and point-in-time cutoff are implemented and tested. Routine capture is still **not accepted** because the verified source cannot yet furnish a complete five-session path for this mature sample. Next, identify the direct-backfill rows' original source manifests and either produce independently verifiable immutable revisions or classify them explicitly as lower-trust research-only observations. Then replay a time-stratified CALL/PUT panel after 10/20-session horizons actually mature, and benchmark a larger bounded writer batch with a date-scoped rollback package and operational throughput target.

Do not relax the provenance check merely to increase label counts. Do not feed partial hypothetical labels or unverified historical chain marks into live trading authority or model activation.

## Verification

The bridge/capture/canary focused suite passed **40 tests**. The broader adjacent regression passed **172 tests plus 2 subtests** before the final additional unversioned-snapshot exclusion test, which then passed in the focused suite. Python compilation and the tracked-file whitespace check passed. The live control-plane still has **zero** DOI outcome labels and neither the outcome-source table nor scan cursor; the activation flag remained unset. All temporary canary databases were removed automatically.
