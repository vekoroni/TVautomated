# AVS-W3-SD-001 — Worker 3 governed source bridge

Status: implemented, installed disabled
Authority: advisory only
Production data writes: none
Provider/API calls: none

## Purpose

This slice moves the tested Worker 3 foundation into the AVSHUNTER repository
and gives it one governed source boundary. The boundary prepares evidence from
an explicit completed pipeline run; it does not start a model worker and does
not participate in trading authority.

## Accepted source flow

```text
explicit run_id
  -> run_meta_v2 + final_run_manifest (completed/healthy)
  -> exact lab_signal_book_v2 (one exact ticker row)
  -> canonical registry (read-only, immutable SQLite URI)
       -> exact OPTION_CHAIN dataset
       -> exact selected LIVE_OPTION quote
       -> completed MARKET_STRUCTURE profile when present
  -> content-hash verification
  -> typed immutable analyst_evidence_v1 bundle
  -> native Lab document attachment
  -> EVIDENCE_PREPARED or per-ticker DATA_EXCEPTION
```

The bridge never searches for a "latest" file, never fetches fresh data, never
substitutes a contract, and never converts missing/non-finite values to zero.

## Identity and time contracts

- Run ID, invocation ID, completed trading session, market evidence cutoff and
  plan hash come from the governed dynamic plan.
- Direction comes only from `governed_direction`.
- Hold sessions use the governed bucket endpoint: `1_5d=5`, `6_10d=10`,
  `11_20d=20`; option DTE is never used as holding period.
- Contract identity requires both `selected_structure_id` and a canonical OCC
  symbol. The OCC side must equal governed direction.
- The market cutoff and the bundle availability cutoff are separate. The latter
  is the latest governed artefact time, so derived pipeline evidence is never
  falsely claimed to have existed before it was produced.

## Evidence rules

- Lab values retain the Lab book byte hash.
- Canonical option-chain, selected-quote and profile payloads are resolved by
  dataset ID or exact ticker/session query, confined to `data/canonical`, and
  verified against their registry content hash.
- Bid/ask/Greeks/IV/OI/volume come from the canonical selected-quote payload,
  not a second API call. Relevant Lab values are reconciled against that payload.
- A missing selected quote is a ticker data exception. A missing completed
  profile is explicit unavailable advisory evidence and is not fabricated.
- A bad ticker cannot abort other worklist entries.

## Regression boundaries

The integration tests cover completed-run enforcement, exact identity, CALL and
PUT contract-side integrity, hold mapping, canonical hash checking, missing
profile handling, quote mismatch isolation, duplicate worklists and zero
provider/write accounting. The pre-existing Worker 3 foundation suite remains
the calculation and behavioural regression baseline.

## Deployment state and next phase

The package is present in `worker3/`, but `contracts/worker3_integration_v1.json`
keeps runtime activation and provider access false. The next phase may add a
durable job repository and coordinator behind this contract. It must consume
only `EVIDENCE_PREPARED` bundles, record provider/model/prompt versions and
idempotency keys, and remain advisory. No orchestrator or Intelligence Lab
runtime is wired by this slice.

## Implementation validation — 2026-09-07

- New bridge tests: 9 passed, 0 failed.
- Existing Worker 3 regression pack: 279 passed, 0 failed.
- Compilation and diff whitespace checks: passed.
- Read-only smoke against completed run `20260906_213931`: 264 requested,
  256 evidence bundles prepared and 8 ticker data exceptions.
- The eight exceptions all have a selected contract in the Lab book but no
  `selected_quote_dataset_id` and no matching registered `LIVE_OPTION` dataset.
  They were isolated exactly as designed; no provider fallback or production
  write occurred.
- Prepared population: 170 CALL and 86 PUT bundles, including 17 theses with no
  selected contract. No contract identity was fabricated for those 17.
