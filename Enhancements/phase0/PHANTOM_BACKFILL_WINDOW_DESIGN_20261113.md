# PHANTOM backfill window — evidence and design for ACK

13 November 2026. **Design only; no tooling changes or paid requests. Part A stopped at preflight.**

## 1. Verified facts

No matching Python pipeline/backfill/Greek/maintenance worker was running at preflight. The database drive had **47.09 GiB free**, above the 15 GiB guard. The literal CSV roster has **3,320** unique identities, including `NAN` and `SYM`.

The saved research `option_entry` table contains **272 entries, 175 with reference quotes: 64.3%**. Independent exact ticker/session/OCC lookups reproduce 175/272. No scorer or collector was run. Of the 272 named contracts, **144 (52.9%) exceed 60 calendar DTE**; median 63, maximum 156.

Source: `scripts/run_phantom_backfill_parallel.py`, `params_for` (lines 146–155): historical `date`, expiries `date+7` through `date+60`, `strikeLimit=40`, `range=all`, `minOpenInterest=1`. Thus the expiry-window cause is confirmed. Strike/OI filters can impose additional exclusions; counts alone cannot attribute every difference to expiry.

Indexed read-only samples from `chain_snapshots` (`WHERE ticker=? AND quote_date=? GROUP BY source`):

| Ticker | 13 Oct source; rows; stored DTE range | 14 Oct source; rows; stored DTE range |
|---|---|---|
| AAL | MARKETDATA; 548; 3–94 | marketdata.app; 222; 9–44 |
| BILI | MARKETDATA; 164; 3–94 | marketdata.app; 29; 37–37 |
| SPY | MARKETDATA; 7,444; 1–108 | marketdata.app; 831; 7–47 |
| QQQ | MARKETDATA; 6,944; 1–94 | marketdata.app; 837; 7–47 |

Expiry timestamps agree with these bounds. `EXPLAIN QUERY PLAN` confirmed use of `idx_chain_ticker_date`, not a date-only table scan. These samples verify narrower stored coverage, not unrestricted completeness of evening captures.

All **33** missing named contracts on dates with a chain are >60 DTE: 14 Oct 20; 19 Oct 2; 22 Oct 9; 11 Nov 2. On 20 Oct another 24 entry contracts lack a chain: 11 >60 DTE, 13 <=60. On 12 Nov, 40 lack a chain: 22 >60, 18 <=60.

**Acceptance ceiling:** Part A excludes 12 Nov. With the frozen 272-entry population and current window, adding 20 Oct/9 Nov can recover at most 13 entry quotes: **188/272 = 69.1%**, below 70%. Nine November can repair horizon observations but has no named decision-session entry in this population. This is an upper bound, not a promise of fills; sub-7-DTE, strike, OI, mapping or availability restrictions can reduce it further. The report's 75.7% scenario includes later recovery of 12 Nov and is not the result of this two-session task.

## 2. Execution blockers — no workaround performed

- `backfill_runbook.py` passes `--credit-cap` unchanged to each session (lines 76–79, 103): 4,000 is **per invocation/session**, not one cumulative 4,000 allowance. The brief estimates approximately 6,640 total. ACK must confirm the intended cumulative authority.
- The runner checks estimated consumption **after** responses, permits in-flight overshoot (`--credit-cap` help, line 358; accounting lines 506/519), and does not reconcile provider-header consumption or reserve a hard cumulative ceiling before requests.
- The runner rejects literal `NAN` and `SYM` (`INVALID_TICKERS`, line 36), contrary to the complete-roster policy.
- It records request errors but ultimately returns zero (line 551). Therefore the wrapper's nonzero-exit STOP rule does not guarantee a stop on authentication/provider errors. Mapping errors are not managed through the approved skip/collate quarantine policy, and the normalizer needs explicit identity validation before ingestion.
- Upsert uses `ON CONFLICT ... DO UPDATE` (lines 206–217). The wrapper normally avoids existing pairs, but this is not an insert-only preservation guarantee. Its preservation receipt compares ticker **counts**, not full identities/row hashes, and does not prove other dates unchanged.
- `plan` is not strictly write-free: the wrapper creates the receipt directory before planning; the delegated runner opens audit storage without `mode=ro`. Its `session_state` performs date-only chain scans. The supplied plan command was **not run**; full-panel present/missing counts remain unverified.
- The ingestion helper completes Greeks on exact written rows, but its final `drain_pending(max_pairs=100000)` is **global**, not restricted to this batch. The proposed weekly command accepts both dates, but repairs all stored pairs on those dates, labels up to its bound, and drains the global IV queue. It cannot prove “exactly the rows written / no other-date changes.”
- Null Greeks can remain for explicit solver/underlying-input failures. Zero pending-without-quality is an auditable requirement; zero null numbers cannot be promised by fabricating values. Missing underlying must remain flagged, not filled with guessed values.

No original plan, execute, maintenance or rescore command was launched. No ingestion receipt is claimed. Existing rows/databases and the research package were not edited; the journal was not opened. Diagnostic code reads returned exit 0. Part A is **BLOCKED, not partially completed**.

## 3. NO_DATA and 12 November

Confirmed in code: `load_completed_keys` treats both `OK` and `NO_DATA` as completed for the same ticker/date/parameter hash (lines 157–165); the worker skips those keys. Identical-query NO_DATA is not automatically retried. Changing parameters changes the key, but must not be used to evade final NO_DATA policy without explicit approval.

The seven-day lag applies only when `--end-date` is omitted. An explicit end date bypasses it. **12 Nov was not requested and remains deferred until 19 Nov or later**, as instructed. Also, 9 Nov is only four calendar days before this task: running it now overrides the tool's default safety lag. The brief explicitly requests that date, but ACK should understand the risk of finalising a temporarily unavailable chain as NO_DATA. No paid availability probe was made.

## 4. Options for approval

Costs below are **request/estimator scenarios, not verified provider billing quotes**. The old runner estimates `max(1, ceil(normalized_rows/1000))`; actual consumption must be checked against archived provider receipts/headers. Reuse saved exact responses first, charge reservations cumulatively, and never repeat uncertain requests.

| Option | Changes, cost basis and dates repaired | Existing-row risk and first failing business-rule test |
|---|---|---|
| A — Wider full-panel chains | Approve a parameter version covering needed expiries, e.g. through 160 DTE for this frozen sample. New full session nominally starts at ~3,320 one-credit requests, **plus** larger-chain/multiple-credit effects; a wider window may cost more. Current runbook skips existing-chain tickers, so widening alone does **not** repair 14 Oct or 22 Oct–6 Nov; also include observed 19 Oct/11 Nov gaps in a separate approved scope. Minimum 7 DTE still excludes near-expiry observations. | Existing upsert is unsafe for top-ups. Require insert-only exact identities, pre-existing row hashes unchanged, versioned scope and before/after source receipts. Failing test: a named 94-DTE OCC must be requested/included while every previously captured value remains unchanged; rerunning reuses the receipt and spends nothing. **strikeLimit 40 does not guarantee every card strike**: prove membership of the exact named OCC list, or explicitly request those strikes/contracts; do not infer completeness from `range=all`. |
| B — Contract-level supplement into PHANTOM | Build an exact missing `(canonical ticker, OCC, session)` worklist from reference and horizon needs. Repairs already-backfilled 14 Oct and 22 Oct–6 Nov without repeating whole chains; include 19 Oct/11 Nov if approved. At most **272 × 11 = 2,992 contract-session observations** before deduplication, saved reuse, maturity and expiry restrictions; this is not necessarily 2,992 HTTP calls or credits. Endpoint batching/billing/access must be verified. | Inserts only where the exact key is absent; provenance names endpoint, quote timestamp and capture time. No guessing roots or overwriting vendor values. Failing tests: existing chain lacking one long-dated OCC gains only that OCC; a conflicting archived row is refused/quarantined; zero duplicate request on resume; budget exhaustion blocks before dispatch. Exact written-key Greek/IV completion and hash checks on untouched dates are required. |
| C — Research package fetches named contracts itself | Same deduplicated contract-session demand as B, not merely 272 requests: reference plus ten path sessions are needed. Can cover all specified reference/horizon gaps once data is available. Leaves PHANTOM unchanged but creates a separate research source and does not repair pipeline-wide history. Requires ACK to relax “options from PHANTOM” for that package. | No PHANTOM row-write risk, but material research-package ownership/provenance change, currently out of scope. Failing tests: a missing PHANTOM quote remains visibly missing there while an independently sourced exact quote is labelled in research; no future quote/capture leakage; ask-entry/bid-exit basis and missing-data counts remain explicit. Reconcile conflicts rather than silently preferring the new source. |

**Recommendation for approval:** B is the targeted shared-data repair; A is a separate full-panel coverage policy. C is reasonable only if ACK deliberately wants a research-only supplement. No option is built or selected by this note. The present tools need a separately approved safe execution route before Part A can proceed: complete identities, insert-only preservation, hard cumulative reservations/receipts, failure classification, mapping quarantine and exact-batch local finalisation. Confirm whether the intended cap is 4,000 total or 4,000 per session (up to 8,000 combined); no recurring spend is authorised.
