# AVSHUNTER Post-Run Pipeline Audit

**Audit date:** 2026-09-07  
**Macro/evening run:** `20260906_213931`  
**Run state:** `DISPATCH_COMPLETE` / technically completed  
**Scope:** read-only assessment of run completion, data lineage and reuse, direction continuity, completed Market Profile, Vanguard, Options Intelligence, liquidity lifecycle, EIL/trigger handoff, Intelligence Lab, macro advisory data, canonical stores, Decision and Outcome Ledger, and regression evidence.  
**Production changes:** none.

## Executive decision

The evening pipeline completed and produced a substantially improved, internally coherent EOD opportunity book. The run is suitable for **human EOD thesis review and the next Morning Gate validation**. It is **not yet accepted for unattended live-capital operation or completion of the digital trading platform**.

The decisive positives are:

- Direction is preserved end to end for every comparable candidate.
- Completed-session Market Profile is now real rather than fabricated: all 1,304 usable profiles have populated POC/VAH/VAL.
- Options acquisition overwhelmingly reused canonical MarketData chains; Polygon options fallback was not used.
- Trigger fields, hold horizons and Lab candidate direction are populated coherently.
- Macro, EV3 and Interpreter reasoning remain advisory and do not grant capital permission.

Four closure defects remain material:

1. Seventeen Lab candidates carry `contract_ask=0.0` instead of an explicit unavailable/null state.
2. The Decision and Outcome Ledger cannot mature candidates because essential lineage and horizon fields are absent.
3. The DDD run plan predicts zero provider requests and the completion receipt records no dataset IDs, while the run actually made 1,540 physical MarketData requests and registered 2,615 datasets.
4. Handoff/system-defect reporting disagrees about 165 missing governed invalidation values.

Morning Validation is still pending, so the run has not yet proved that overnight gaps, current price, quote changes and lifecycle transitions correctly preserve or invalidate the EOD thesis.

## 1. Run completion and promotion state

| Check | Evidence | Assessment |
|---|---:|---|
| Run status | `COMPLETED`; final dispatch at 00:55:59 | PASS |
| Run artefacts | 1,665 files | PASS |
| Technical health | 97/100, technical PASS | PASS with exceptions |
| Semantic checks | PASS | PASS |
| Morning Validation | PENDING | Expected for EOD, acceptance incomplete |
| Tradeable/capital state | `tradeable=false`; no final capital permission | Correct before Morning Gate |
| Final handoff audit | Overall FAIL: 1 FAIL and 1 WARN | BLOCKER for unattended publication |

Key row flow:

| Stage | Rows |
|---|---:|
| Discovery | 1,587 |
| Completed Market Profile | 1,304 usable |
| Vanguard | 1,537 |
| Options / EIL / execution | 1,461 |
| Morning candidates / Intelligence Lab | 264 |

There are no duplicate ticker rows in the inspected Discovery, Vanguard, Options, execution, EIL, Morning candidate or Lab outputs.

## 2. Direction and thesis continuity

Discovery direction distribution:

- CALL: 850
- PUT: 480
- STRANGLE: 131
- UNRESOLVED: 126

Options direction distribution:

- CALL: 832
- PUT: 460
- STRANGLE: 129
- UNRESOLVED: 40

For all **1,292 comparable directional rows**, Discovery, governed direction and Options direction agree. There are **zero direction mismatches**. The 264 Lab candidates also have zero mismatches: 170 CALL and 94 PUT.

This resolves the earlier uncontrolled CALL-to-PUT/PUT-to-CALL concern on the current run. The remaining 40 unresolved rows are explicit unresolved states rather than silent direction changes. They must remain non-executable unless subsequently resolved by governed evidence.

## 3. Completed-session Market Profile

| Result | Count |
|---|---:|
| Input tickers | 1,587 |
| Usable profiles | 1,304 |
| Single distributions | 1,125 |
| Double distributions | 179 |
| Inactive/provider no-data deferrals | 233 |
| Schema-invalid/hard failures | 50 |

All 1,304 usable profiles have non-zero POC, VAH and VAL. The previous state in which every profile was `INSUFFICIENT_DATA` with zero levels is not present.

Usable coverage is 96.31%; the 3.15% hard-failure rate is within the configured 5% guard. The 233 unavailable tickers are explicitly deferred rather than assigned false zero levels.

Concern: completed-profile acquisition caused 1,537 physical provider requests. The feature works, but reuse and request planning are not yet consistent with the DDD run plan.

## 4. Canonical data reuse and DDD execution evidence

The run plan declares:

- reuse `CANONICAL_COMPLETED_DATA`;
- estimated physical requests: 0;
- zero estimated requests for each required dataset.

The canonical request ledger records:

| Metric | Count |
|---|---:|
| Request ledger records | 4,369 |
| Physical MarketData requests | 1,540 |
| Completed-profile physical requests | 1,537 |
| Options physical requests/errors | 3 |
| Cache hits | 1,289 |
| Provider fetches | 1,304 |
| Provider no-data | 233 |
| Provider errors | 3 |

The data registry contains 2,615 datasets for the run:

- 1,304 `INTRADAY_BAR`
- 1,304 `MARKET_STRUCTURE`
- 7 `LIVE_OPTION`
- 2,610 COMPLETE and 5 PARTIAL

However, the completed thesis receipt contains empty `dataset_ids` for every stage. This is a lineage defect: the data was registered, but the receipt cannot prove which immutable datasets supported the thesis.

**Required correction:** the planning service must distinguish forecast cache availability from actual provider demand, and the completion receipt must be populated from the registry/publisher results. Acceptance should reconcile `planned`, `actual physical`, `cache`, `no-data`, `error` and `dataset_id` counts.

## 5. Options Intelligence and liquidity lifecycle

Options processed 1,461 rows:

| Classification | Count |
|---|---:|
| EXECUTE | 97 |
| ARMED | 90 |
| STAND_DOWN | 1,274 |
| GO_REVIEW route | 164 |
| ARMED_HALF route | 564 |
| PROBE_ONLY route | 396 |
| BLOCKED route | 337 |

Canonical acquisition behaviour is healthy:

- worklist authorised: 1,292;
- excluded before options acquisition: 245;
- cache hits: 1,289;
- physical calls: 3;
- MarketData fetch successes: 0 because the three misses returned empty/error;
- Polygon options fallback: 0 and disabled;
- missed tickers: NLST, AEBI and DEC.

Lifecycle persistence completed for 1,077 candidates, with 212 thesis-only states and zero lifecycle persistence errors.

The repair selector retained 540 contracts with OI below 50 and 393 zero-volume contracts as developing opportunities. This is consistent with the agreed lifecycle design: OI and volume are ranking evidence, not universal permanent rejection gates. Quote, spread and geometry remain governed separately.

Quote evidence:

- TWO_SIDED: 1,186
- ONE_SIDED: 83
- unavailable/null: 192
- session aligned: 1,010
- synthetic non-executable: 67
- unavailable: 20

No selected Options row has a zero ask. The zero-ask defect is introduced later in the handoff/Lab materialisation boundary.

## 6. EV3 advisory computation

EV3 has no capital authority, which matches the current policy. Its technical stage passed, but functional status is `DEGRADED_NO_EVALUATIONS`:

- evaluated: 0
- rejected: 1,270
- not applicable: 191
- quote-stale rejection: 788
- no evaluable contract: 352
- thesis-price issue: 130

This does not block the current human-reviewed pipeline because EV3 is advisory. It does mean its displayed output cannot currently be treated as useful comparative economics for this weekend EOD run. The strict real-time freshness convention is inappropriate for completed-session advisory evaluation unless the output explicitly distinguishes historical EOD economics from an executable quote.

The integrity reports also disagree: the final manifest reports zero missing selected invalidation values, while EV3/pipeline-integrity evidence reports 165. One scoped definition must be adopted or the reports must explicitly identify different populations.

## 7. EIL, triggers and Intelligence Lab

Trigger Layer results across 1,461 rows:

- VOL_COMPRESSION: 583
- RANGE_BREAK_EARLY: 313
- RANGE_BREAK: 32
- NONE: 533
- STRONG quality: 188
- SINGLE quality: 740
- NONE quality: 533

The handoff guard safely downgraded 23 execution-like rows whose evidence conflicted with execution status.

The Lab receives 264 candidates:

| Field | Result |
|---|---|
| Direction | 170 CALL, 94 PUT |
| Hold | 185 at 1–5d / 5 sessions; 79 at 6–10d / 10 sessions |
| Monetisability | 204 MONETISABLE, 12 LIMITED, 23 NOT_MONETISABLE, 25 DATA_MISSING |
| Candidate state | 174 REPAIR_AT_OPEN, 83 TRIGGER_REQUIRED, 4 READY_VALIDATION, 3 WATCH_ONLY |
| Verdict | 247 MANUAL_REVIEW, 17 CONTRACT_REPAIR |
| Final capital permission | null for all, appropriate before Morning Gate |

Current handoff defects:

- **17 rows contain `contract_ask=0.0`.** Unavailable prices must be null with an explicit evidence-quality state; zero is a tradable numerical value and must not represent missing data.
- `options_hard_vetoes` exists but is empty for all 264 rows. If no veto applies it should contain an explicit `NONE`; if the field is obsolete it should be removed from the governed contract.
- WBS is populated for only 67 rows. The other 197 should state `NOT_APPLICABLE`, `INSUFFICIENT_EVIDENCE` or another governed reason rather than display a blank.

There is no executed Pipeline Interpreter output in this evening run. The enabled setting prepares the handoff; it does not itself execute interpretation. This is acceptable before the Morning Gate/Interpreter workflow, but the digital platform cannot be accepted until that handoff is exercised.

## 8. Macro advisory layer

The macro package is present and advisory-only. It includes:

- the US Money Index in `extras.us_money_index` and the macro quant packet;
- GEX availability and local canonical GEX dataset lineage;
- a 0.75 GEX regime score;
- USMI state `SELECTIVE_US_CAPITAL_CONCENTRATION` with `PARTIAL_UNVERIFIED` quality;
- gamma state `AT_FLIP_BOUNDARY`.

Macro does not grant capital permission or override governed ticker direction, as intended.

Remaining advisory-data concerns:

- bond yield-curve state is marked stale and should be displayed as stale advisory context;
- unresolved macro conflicts include the quarantined USSLIND issue and ENERGY theme versus base XLE avoid;
- an informational VIX metric distinction is still represented among active conflicts and should be reclassified if it is not an actual contradiction.

These issues affect explanation and sector context, not the EOD ticker authority chain.

## 9. Decision and Outcome Ledger

This is the most important digital-platform blocker.

The ledger contains 559 events:

- 558 `CANDIDATE_DECISION` events;
- 1 test `OUTCOME` event;
- 264 candidate decisions from the current run;
- 294 from the previous run.

Outcome maturation reports 558 candidates, but zero are eligible and zero outcomes are evaluated or appended. Candidate payloads are missing the fields needed to identify and mature a governed observation:

- `completed_session`
- `planned_hold_sessions`
- `selected_contract_symbol`
- `direction_decision_id`
- `evidence_dataset_ids`
- populated `execution_eligibility_state`
- `formula_version`

Until these fields are written from their canonical producers, the system cannot measure MFE/MAE, thesis success, contract evolution, rejected-candidate outcomes or model calibration. The ledger is append-only in form but not yet functional as a learning loop.

## 10. Database status

### Phantom options database

The live Phantom database is 16.8 GB. Latest completed-Friday session is 2026-09-04:

| Table | Latest session rows | Tickers |
|---|---:|---:|
| `chain_snapshots` | 245,448 | 2,869 |
| `options_greeks_history` | 245,448 | 2,869 |
| `iv_surface_history` | 11,988 | 2,869 |

The latest Greeks audit processed all 245,448 rows:

- successful/updated: 241,739 (98.49%)
- failed/quality-exception: 3,709 (1.51%)
- primary-key identities enforce uniqueness on ticker/session/contract in both chain and Greeks tables;
- IV-surface uniqueness is enforced on ticker/session/DTE bucket/side.

The full 16.8 GB integrity scan was deliberately stopped after it exceeded the audit time budget without output. No corruption signal was observed, but this audit does not claim a completed full-page integrity check. Operational row/session/audit evidence is healthy.

### Other canonical stores

The control plane, historical price store, run-plan store and Decision/Outcome Ledger opened read-only and served the audit queries. No write lock, migration or production mutation was performed.

## 11. Regression evidence

The current repository contains approximately 1,455 tests. Results are mixed because historical audit tests are still shipped alongside active regression tests.

- Full collection stopped at the configured failure ceiling: 23 failed, 213 passed, 4 skipped, 47 subtests passed.
- Most failures under `tests/msi` assert that previously identified defects remain. They now fail because those defects were fixed (size propagation, NBBO producers, freshness callers, quote comparison and Lab v3 materialisation). These are obsolete audit assertions, not product regressions.
- Focused DDD, liquidity, lifecycle, direction and governance suites: 61 passed.
- Canonical data/historical price suites: 35 passed, 1 failed. The remaining failure expects a direct backfill script to succeed without an allowed provider source, while current governance returns `NO_SOURCE_ALLOWED`. The test or the direct-launch contract must be reconciled.
- Two vocabulary differences remain between old design tests and production: positive size quality `OBSERVED_POSITIVE` versus `OBSERVED`, and crossed quote `INVALID` versus `CROSSED`.

Therefore the audit cannot honestly certify a completely green repository-wide regression suite. The core current functionality is much stronger than the raw failure count suggests, but the test estate needs versioning and retirement of inverted historical checks.

## 12. Severity-ranked closure register

| Priority | Finding | Required action |
|---|---|---|
| P0 | Decision/Outcome Ledger candidates cannot mature | Populate governed session, hold, contract, direction decision, evidence IDs, eligibility and formula version; replay maturation tests |
| P1 | 17 Lab asks fabricated as zero | Preserve null and explicit quote-unavailable state through handoff/materialiser; fail capital eligibility, not the whole pipeline |
| P1 | Plan/actual request and receipt lineage disagree | Reconcile planned and actual demand; write registry dataset IDs into the completion receipt |
| P1 | Missing-invalidation count conflicts across reports | Establish one scoped metric or label the population in every report |
| P1 | Morning Gate not yet executed | Run against this exact EOD run and validate gap/thesis, quote/lifecycle, capital and Lab handoff |
| P2 | EV3 produces zero advisory evaluations | Separate completed-session advisory economics from live executable freshness |
| P2 | WBS and hard-veto blanks are ambiguous | Emit governed explicit states or remove obsolete fields |
| P2 | 50 completed-profile hard failures | Quarantine by ticker/reason and investigate without aborting healthy tickers |
| P2 | Historical/audit tests conflict with current contracts | Split active regression from historical defect reproductions; update vocabulary deliberately |
| P3 | Macro quality/conflict classifications | Preserve stale/partial labelling and distinguish information from real contradiction |

## 13. Acceptance recommendation

Use this run as the controlled EOD input to Morning Gate, not as final live-capital approval.

Minimum acceptance sequence:

1. Correct the 17 zero-ask handoff rows and rerun the handoff audit to PASS.
2. Reconcile the missing-invalidation metric and completion-receipt lineage.
3. Execute Morning Gate for run `20260906_213931` when valid session evidence is available.
4. Confirm overnight gap handling, current underlying price, refreshed contract quote, lifecycle transition and Lab display for every promoted ticker.
5. Confirm no thesis-invalidated row receives capital permission and no missing quote is represented as zero.
6. Repair the Decision/Outcome Ledger contract before declaring the digital trading platform’s learning loop operational.

**Final classification:** EOD pipeline operational for governed human review; Morning acceptance pending; unattended production and digital-platform closure not yet approved.

## Evidence inspected

- `data/output/runs/20260906_213931/run_meta.json`
- `data/output/runs/20260906_213931/final_run_manifest.json`
- `data/output/runs/20260906_213931/diagnostics/handoff_contract_audit_20260906_213931.json`
- Discovery, Vanguard, Options, EIL, execution, Morning candidate and Intelligence Lab CSV/JSON artefacts in the run directory
- `data/output/run_plans/run_plan_inv_3f44dcdb0f5d69ba30ec4f88.json`
- `data/output/run_plans/completed_thesis_receipt_inv_3f44dcdb0f5d69ba30ec4f88.json`
- `data/canonical/control_plane.sqlite`
- `data/canonical/decision_outcome_ledger.sqlite`
- `data/phantom/phantom_history.db`
- current macro, GEX and bond sidecars captured by the run
- focused and repository-level pytest evidence described above
