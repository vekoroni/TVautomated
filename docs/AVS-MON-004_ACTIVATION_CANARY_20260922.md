# AVS-MON-004 — outcome-capture activation canary

**Executed:** 22 September 2026, 09:18 UTC
**Decision:** routine capture remains **OFF**.
**Scope:** production databases opened SQLite `mode=ro` and `query_only`; the scheduler-index write test used a disposable key-only mini-store. No live label, cursor, index, provider request, model activation, or trade-authority change was made.

## Tested read path and capacity

| Measure | Result |
| --- | ---: |
| Control-plane database | 4,763,688,960 bytes |
| Disk free on its volume | 61,509,083,136 bytes |
| DOI families / assessments / labels | 12,337 / 90,998 / 0 |
| Existing scan cursor / proposed scan index | absent / absent |
| Live first-page read, 100 families | 257 ms cold; 352 ms warm median, 413 ms warm maximum over five repeats |
| Mini-store keys copied | 12,337 |
| Mini-store index growth / WAL before checkpoint | 1,183,744 / 1,194,832 bytes |
| Mini-store index build | 0.027 seconds |

The mini-store reproduces only the family scan keys. Its index and WAL sizes **do not** establish the size, lock duration, or rollback needs of a write against the 4.76 GB live control plane. The bounded capture budget of 100 scanned families per run would require at least 124 runs to make one pass over today's 12,337 families; quote/price reads and coverage queries were not included in that estimate.

## Exact-contract coverage probe

The probe sampled the oldest and newest 20 assessments per governed direction: **80 total**, 40 CALL and 40 PUT. Their source sessions were 11 September (40) and 21 September (40). This is a deliberately edge-weighted, **non-random** sample. Forty 11 September assessments had at least five completed underlying sessions; the 21 September cohort had not yet matured. Neither cohort had ten or twenty completed underlying sessions. No conclusion about 10/20-session coverage is possible today.

For the **40 mature assessments**, the same exact OCC symbol was checked against registered control-plane observations and read-only Phantom `chain_snapshots` on each completed underlying session:

| Mature horizon | Source | Full raw path | Full positive-bid, non-crossed two-sided path | No raw path |
| --- | --- | ---: | ---: | ---: |
| 1 session | Control plane | 14/40 | 11/40 | 26/40 |
| 1 session | Phantom | 38/40 | 27/40 | 2/40 |
| 5 sessions | Control plane | 0/40 | 0/40 | 18/40 |
| 5 sessions | Phantom | 11/40 | 9/40 | 1/40 |

The other five-session paths were partial: control plane 22/40 raw and 18/40 two-sided; Phantom 28/40 raw and 19/40 two-sided. This comparison measures structural data presence, **not** point-in-time entitlement, quote quality beyond displayed bid/ask, achievable fills, or strategy returns. Phantom snapshot provenance and source availability timestamps must be validated before its rows can become governed label inputs.

## Root cause and activation decision

The bounded capture reader currently reads `option_contract_observations` in the control plane, not Phantom's denser daily `chain_snapshots`. Thus the scheduler and correction mechanism work, but most matured assessments in this sample would receive partial or unavailable option outcomes. Turning on routine capture would create many labels without resolving the intended 1–20-session exact-contract learning path. The current sample also cannot validate 10/20 sessions because those horizons are not yet mature.

**Do not enable** `AVSHUNTER_OPTION_OUTCOME_CAPTURE_ENABLED` yet. Before activation:

1. Build a read-only, exact-symbol Phantom outcome-source adapter that preserves `quote_date`, provider quote/update time, ingestion availability time, source row identity/hash, and the assessment's point-in-time cutoff. It must not overwrite a registered provider observation or manufacture an executable quote from a midpoint.
2. Compare control-plane and Phantom rows for identical symbol/session; deduplicate by governed source precedence and reject conflicting provenance. Feed the selected observations to the existing append-only correction service, preserving the distinction between hypothetical market path and realised fills.
3. Replay the 11 September cohort and a wider time-stratified sample. Reconcile exact-contract full/partial/zero paths by 1/5/10/20 sessions as the horizons mature, separately for CALL and PUT.
4. Measure a bounded capture batch, cursor writes, coverage-query latency, WAL growth, and rollback on an isolated **representative** store before any live database index migration. Define an operational throughput target for the historical backlog; 100 families per Evening run is not sufficient for prompt coverage.

The reproducible, read-only probe is `python -m tools.avs_mon004_canary`. Its synthetic safety/arithmetic tests and the outcome regressions passed **31/31**. Routine activation awaits the source bridge and controlled writer canary; no claim of a proven HARC or monetisation model is made.
