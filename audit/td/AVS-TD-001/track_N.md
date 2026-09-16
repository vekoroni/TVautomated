# Track N — Invariants (NFR-01…10, every stage)
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.
Runs used: 20260910_150045 → 20260911_115904 (both TEST, dirty, commit 00baa2b; pre-remediation). Ledger and journal copies span runs 20260905_151448 … 20260911_115904, run_001, and journal trades from 2026-03 to 2026-06.
Data sources: `db_copies/control_plane.sqlite` (`option_contract_observations` 10,522 rows, `option_contract_selection_events` 11,108 rows, `doi_contract_assessments`), `db_copies/decision_outcome_ledger.sqlite` (`ledger_events` 8,290), `db_copies/trade_journal.db` (`trades`, `closed_trades`), all opened `mode=ro`; production source at `cc509cb`; `pytest/junit_full.xml`; Track B/G/H/I results cross-referenced.
Probes: `probes/p17_IN_nfr05_immutability.py` → `p17_IN_nfr05_immutability.json/.csv`; `probes/p17_IN_nfr06_fills.py` → `p17_IN_nfr06_fills.json/.csv`; Track I probes `p17_IN_environ_*`, `p17_IN_governed_*`, `p17_IN_manifest_*`; Track B `p11_B_*`; Track G `p16_G_nfr07_arith.json`.

## Results
| REQ ID | check (how / on what) | CALL result | PUT result | OTHER result | source evidence (file:line) | run evidence (run_id, artefact, field, value) | verdict | closed-offline? |
|---|---|---|---|---|---|---|---|---|
| NFR-01 | grep assignments `row["governed_direction"|"structural_target*"|"invalidation_*"|"planned_hold_sessions"] =` in tracked production .py | direction-agnostic writers | same | same | 8 subscript writers outside the Thesis context: `morning_gate.py:3746` `planned_hold_sessions` (falls back to horizon-bucket upper bound, source `ROUTED_HORIZON_UPPER_BOUND`), `:3712` `invalidation_spot` (coalesce of 4 aliases); `intelligent_orchestrator.py:3488` `planned_hold_sessions` re-derived from final router bucket; `vanguard/ev3_stage0.py:349` (canonicalises copy); `contracts/lab_control.py:3508` `structural_target ← target_price`, `:3510` blanks it, `:1555` `invalidation_spot`; `execution_intelligence_runner.py:2352` `invalidation_state`. Dict-literal emitters of `governed_direction`/`planned_hold_sessions` in 14 further files not classified | not run-testable (no remediated run) | OPEN — UAT-D-N1 | no |
| NFR-02 | junit status of macro-invariance property tests; run-level mutation impossible (no pipeline runs permitted) | tests are direction-generic | same | same | `tests/test_dynamic_session_phase2.py:29,55,76`, `tests/test_morning_gate_authority.py:116,149`, `tests/test_production_readiness_guardrails.py:87`, `tests/msi/test_logic.py:1276` | junit: 5 named tests passed (`junit_full.xml`). The acceptance property test ("mutate every macro input; assert direction, row count, preferred symbol and `contracts_at_budget` unchanged") was not located by name grep | NOT TESTED at run level; acceptance test as specified not located | no |
| NFR-03 | Track B B5: inventory sites + `silent_zero_violations` counter in run summaries | ABSENT counter | ABSENT | ABSENT | `audit/silent_defaults_inventory.md` exists, cites absent `domain/capacity_suggestion.py`, omits `eod_candidate_engine.py:353-360`, `vanguard/ev_engine_v3.py:445,640`; no producer of `silent_zero_violations` (grep 0) | 20260911_115904 summaries: counter ABSENT | OPEN — UAT-D-B5 (P2) | partial (5/5 sampled inventory sites verified) |
| NFR-04 | Track B B2/B3: `> 1` / `/ 100` grep in `domain/`; unit consistency of spread fields in stored artefacts | 349 rows wrongly BLOCK on mixed spread unit | 235 | 0 | 15 `domain/` hits, none a unit guess; `contracts/lab_control.py:2639` mixed-unit `spread_pct`; `eod_candidate_engine.py:2695-2696` legacy differenced field relabelled cumulative | 20260911_115904 Lab book `spread_pct` MIXED units; `spread_fraction_mid` ABSENT | OPEN — UAT-D-B1 (P2), UAT-D-B2 (P1), UAT-D-B3 (P2) | grep part only |
| NFR-05 | Artefacts: `option_contract_observations` / `option_contract_selection_events` across 20260910_150045 → 20260911_115904 (join on ticker+side, same `thesis_id`); `doi_contract_assessments` | obs 653→1,011; sel 653→1,266; contract changed 49: `previous_contract_symbol` NULL 49/49; same contract 575: new observation_id 575/575 but identical `quote_as_of` 575/575, `delta` differs 572; in-run morning requote reusing the EOD observation 255; in-run replacement link broken 28/34 | obs 367→522; sel 367→720; changed 21: prev NULL 21/21; same 328: new id 328/328, same quote_as_of 328/328, delta differs 328; requote reusing observation 198; replacement link broken 16/18 | 0 rows (CHECK `option_side IN ('CALL','PUT')`; 188 OTHER strangles never enter the table) | append-only triggers `trg_option_observation_no_update/_no_delete`, `trg_option_selection_no_update/_no_delete`, `trg_doi_assessment_no_update/_no_delete` present (rows cannot be mutated); `UNIQUE(thesis_id, run_id, contract_symbol, quote_as_of)` keys identity per run, not per quote | `economics_recomputed = 1` on 3,006/3,006 events (constant). `supersedes_event_id` non-null 0. `doi_contract_assessments` **0 rows** — no `assessment_id` persisted on any run | OPEN — UAT-D-N2 | no (immutability of rows holds; identity/lineage fails) |
| NFR-06 | Artefacts: ledger decision counts and fill counts as two separate queries per run × direction; fill-like keys in decision payloads; OUTCOME predecessor type. Journal copy rows vs ledger fills | decisions (all runs) CANDIDATE 3,023 / VALIDATION 949 / EXECUTION 949; FILL_RECORDED 0; fill-like keys 0; OUTCOME 1 (run_001, no predecessor, `is_counterfactual=False`); journal closed CALL 5 | CANDIDATE 1,720 / VALIDATION 542 / EXECUTION 542; FILL 0; fill-like 0; journal closed PUT 8 | CANDIDATE 188 / VALIDATION 188 / EXECUTION 188 (20260911 only); FILL 0; journal closed blank-direction 1 | `domain/decision_outcome.py:23-35` separate `FILL_RECORDED` type; `canonical_data/decision_outcome_ledger.py:267-286` `fill_record_v1`; **`avshunter_trade_journal.py:993-997` chains a trade OUTCOME to the latest `FILL_RECORDED`, else `TRADE_ENTRY`, else `EXECUTION_DECISION`** | ledger copy: 0 position episodes, 0 fills, 0 decision payloads with `fill/position/episode/filled/quantity/entry_price` keys. `trade_journal.db`: `trades` 0, `closed_trades` 14 (`journal_entry_source` BROKER_CONFIRMATION_IMPORT 8 / NULL 6; matching ledger `FILL_RECORDED` 0/14) | OPEN — UAT-D-N3 (code fallback infers a trade's predecessor from a decision); no episode inferred in stored data | partial (separation of types) |
| NFR-07 | Track G: AST scan of Lab projection for arithmetic; fallback literals; plus NFR-01 grep | 0 arithmetic nodes | 0 | 0 | `contracts/lab_control.py:2391-3018` + 20 helpers, `domain/lab_signal_book_v4.py`, `domain/presentation.py`: 0 BinOp/round/min/max; `domain/lab_signal_book_v4.py:9-28` 7 invented fallbacks; `contracts/lab_control.py:3508` writes `structural_target` from `target_price` | n/a | OPEN — UAT-D-G7 (P2), UAT-D-N1 | arithmetic part CLOSED OFFLINE |
| NFR-08 | Track I I3: Annex keys in `config/governed_constants_v1.json`; name-anchored literal grep in 24 decision-path files | run-agnostic | same | same | 9/29 keys absent; key-level owner only `profit_floor`; 13 literal hits in 7 files (`domain/contract_economics_v2.py:68,71,112`, `domain/reachability.py:27`, `domain/option_contract_liquidity.py:142`, …) | n/a | OPEN — UAT-D-I3, UAT-D-I7 (P1) | no |
| NFR-09 | Track I I2: classified env reads vs release profile; run_meta profile hash | run-agnostic | same | same | 20 gating/threshold env vars on import graph, 0 documented; `contracts/dynamic_session_contract.py:138-160` profile env-disable-able | both runs `run_meta.ddd_runtime_profile.sha256=054a76be…bb9d` (= current file); env-gated CDS/EV3/stage-gating values not recorded | OPEN — UAT-D-I2 (P1) | no |
| NFR-10 | Track I I1: replay harness + expected-difference manifest | n/a | n/a | n/a | no book-replay harness; `release/expected_diffs/` absent | none | NOT IMPLEMENTED — UAT-D-I1 (P1) | no |

## Per-check notes
**NFR-01.** `git grep -nE "\[[\"'](governed_direction|structural_target[a-z_]*|invalidation_[a-z_]*|planned_hold_sessions)[\"']\]\s*=[^=]" -- '*.py' ':!tests' ':!backups' ':!audit'`: 8 lines, none in `contracts/thesis_geometry.py` / `contracts/direction_governance.py` / Discovery / Vanguard thesis builders. Two of these originate a value rather than copying it. Morning Gate (`morning_gate.py:3731-3746`) invents a hold from the horizon label when `planned_hold_sessions` is missing. The orchestrator (`:3487-3490`) overwrites hold from the router bucket. The Lab (`contracts/lab_control.py:3505-3508`) promotes `target_price` into `structural_target`. `vanguard/ev3_stage0.py:349` and `morning_gate.py:3712` are alias normalisers on local copies. No `governed_direction` subscript writer was found outside the Thesis context. Dict-literal emitters (14 files) were counted but not read.
**NFR-05.** `python probes/p17_IN_nfr05_immutability.py`. The thesis_id format (`VITL:CALL:2026-09-10:OLM2`) is identical in both runs, so contract replacement across runs is directly observable.
- Row immutability holds: six no-update/no-delete triggers.
- Identity fails in three ways. (a) All 70 cross-run contract replacements (CALL 49 / PUT 21) have `previous_contract_symbol = NULL`; the replaced contract is not linked to the new one. Within 20260911_115904, 44 of 52 morning repair replacements (CALL 28/34, PUT 16/18) link to a symbol other than the prior event's. (b) `economics_recomputed` is 1 on every one of 3,006 events, including 453 `MORNING_EXACT_CONTRACT_REQUOTE` events (CALL 255 / PUT 198) that reference the same `selected_observation_id` as the EOD selection, i.e. no new quote observation exists. The flag is a constant, not evidence of recomputation. These 453 are the prior-session quotes Track A found (A4). (c) 903 same-contract pairs (CALL 575 / PUT 328) were re-recorded in 20260911_115904 under new observation ids with the same provider `quote_as_of` as 20260910_150045, and `delta` differs on 900 (CALL 572 / PUT 328; 1 CALL also differs on `liquidity_state`). The same quote observation therefore carries two different contract-specific value sets under two ids; identity is keyed on run, not on the quote.
- Correct behaviour also seen: 488 in-run requotes (CALL 344 / PUT 144) with a different `quote_as_of` got a new observation id.
- `doi_contract_assessments` has 0 rows, so the `assessment_id` NFR-05 names is not persisted on either run.

These rows were written by pre-remediation code (00baa2b).
**NFR-06.** `python probes/p17_IN_nfr06_fills.py`. Decision counts (`p17_IN_nfr06_fills.csv`, query=decision) and fill counts (query=fill: no rows) come from separate passes. No decision/validation payload carries a fill-, position- or quantity-like key. The single OUTCOME has no predecessor. The journal's 14 closed trades (all pre-ledger, 2026-03 to 2026-06) have no ledger fill. They are legacy journal records, not fills under `fill_record_v1` (Track H H2); direction split CALL 5 / PUT 8 / blank 1 is from Track H. In code, the journal close path (`avshunter_trade_journal.py:993-1004`) sets the trade OUTCOME's `previous_event_id` to an `EXECUTION_DECISION` when no fill or trade-entry exists. That join treats a decision as the origin of a position result.
**NFR-02 / -03 / -04 / -07.** Cross-referenced; no re-measurement. NFR-02: macro-invariance tests pass in the full run, but a run-level mutation needs a pipeline run (prohibited).

## Defects (UAT-D-N<n>)
**UAT-D-N1** — NFR-01. Severity P1. Exposure CALL/PUT/OTHER (every row passing the writers). Thesis-owned fields are written outside the Thesis context:
- `morning_gate.py:3746` `planned_hold_sessions`, with invented fallback at `:3736-3745`;
- `intelligent_orchestrator.py:3488` `planned_hold_sessions` from the router bucket;
- `contracts/lab_control.py:3508` `structural_target ← target_price`;
- alias writers `morning_gate.py:3712`, `contracts/lab_control.py:1555`, `vanguard/ev3_stage0.py:349`, `execution_intelligence_runner.py:2352`.

Evidence: grep in NFR-01 note. Reproduce: run that grep. A fix closes when the grep's writers all resolve to the Thesis context, and downstream modules read (never write) these fields, failing with a named state when absent.
TRACE: NFR-01 | ALG-NONE | WP-NONE | STAGE-ALL | TRACK-N | EVIDENCE-morning_gate.py:3746 | N=8

**UAT-D-N2** — NFR-05 (REQ-WP2 contract identity). Severity P1. Exposure CALL 49 + 28 + 255 + 575; PUT 21 + 16 + 198 + 328; OTHER 0 (not representable).
- Contract replacements lose lineage: `previous_contract_symbol` NULL on 70/70 cross-run replacements; 44/52 in-run morning repairs link to the wrong prior symbol.
- `economics_recomputed` is a constant 1 (3,006/3,006), including 453 requote events that reuse the EOD observation (no new quote).
- 903 identical provider quotes are re-observed under new ids with different `delta`.
- No `assessment_id` is persisted (`doi_contract_assessments` 0 rows).

Evidence: `probes/p17_IN_nfr05_immutability.json` (`cross_run`, `within_B_sequences`, `same_quote_multi_obs`, `economics_recomputed_values`, `doi_contract_assessments_rows`). Reproduce: `python probes/p17_IN_nfr05_immutability.py`. A fix closes when, on a stored run pair, every contract replacement event names its predecessor. It must also show a recompute flag that is derived (0 when no new observation), one assessment id per (OCC symbol, quote observation) with all contract-specific fields recomputed on change, and assessment rows persisted.
TRACE: NFR-05 | ALG-06 | WP-2 | STAGE-2 | TRACK-N | EVIDENCE-p17_IN_nfr05_immutability.json | N=3006

**UAT-D-N3** — NFR-06. Severity P2. Exposure CALL/PUT (journal-closed trades). `avshunter_trade_journal.py:993-997` links a trade OUTCOME to an `EXECUTION_DECISION` when no `FILL_RECORDED`/`TRADE_ENTRY` exists, so position-result lineage is inferred from a decision. No stored ledger row shows this yet (1 OUTCOME, no predecessor), so exposure is code-level. Reproduce: read the cited lines; `python probes/p17_IN_nfr06_fills.py` (`outcome_previous_event_type`). A fix closes when an OUTCOME for a taken position can only chain to a `FILL_RECORDED`, and a close without a fill records a named data exception instead.
TRACE: NFR-06 | ALG-NONE | WP-7A | STAGE-6 | TRACK-N | EVIDENCE-avshunter_trade_journal.py:993 | N=0

Cross-referenced (not re-filed): UAT-D-B1/B2/B3/B5 (NFR-03/04), UAT-D-G7 (NFR-07), UAT-D-I1/I2/I3/I7 (NFR-08/09/10), UAT-D-I4 (stale quote executable, invariant).

## Deviations
| claimed | found | evidence | severity |
|---|---|---|---|
| Schema `option_contract_selection_events.economics_recomputed` implies a recorded recomputation fact | Constant 1 on 3,006/3,006 events, including 453 requotes with no new observation | `p17_IN_nfr05_immutability.json` | P1 (UAT-D-N2) |
| Stage 6 manifest: "decision and fill are separate append-only events" | Separate types confirmed; the journal close path still falls back to EXECUTION_DECISION as the trade predecessor | `avshunter_trade_journal.py:993-997` | P2 (UAT-D-N3) |
| NFR-01: only the Thesis context writes direction/target/invalidation/hold | Morning Gate, orchestrator router patch and Lab write hold/target | NFR-01 grep | P1 (UAT-D-N1) |
| NFR-05 three-direction scope | Observation schema admits only CALL/PUT; OTHER (188 strangle rows on 20260911_115904) have no contract observation or selection lineage at all | `option_contract_observations` DDL CHECK | P2 |

## Premise notes
| spec | measured | gap size |
|---|---|---|
| NFR-05: "a new OCC symbol or new quote observation produces a new `assessment_id`" | The stored identity key is (thesis, run, symbol, quote_as_of); an unchanged provider quote carried into a later run gets a new id and different greeks, so "new observation" is operationally "new run" | 903 of 973 same-thesis cross-run pairs |

## Not tested / blocked
- NFR-02 run-level mutation test: NOT TESTED. It requires executing the pipeline with mutated macro inputs (prohibited). The acceptance property test as specified was not located by name grep; 5 narrower invariance tests pass.
- NFR-01 dict-literal emitters (14 files): NOT TESTED individually.
- NFR-05 / NFR-06 on remediated code: NOT TESTED. No run, observation row or ledger row was produced by `cc509cb`.
- NFR-06 manual fill path: NOT TESTED. Nothing was entered, per rule.

## Expectation vs actual
| row | expectation (E) | actual | gap |
|---|---|---|---|
| N NFR-01..10 | NFR-02, -05, -06, -09 fail or NOT TESTED at run level; NFR-03, -04, -08 partially met offline | -01 OPEN (not predicted); -02 NOT TESTED run level; -03 OPEN; -04 OPEN; -05 OPEN on artefacts (lineage, constant flag, no assessment_id); -06 OPEN P2 (holds vacuously in data; code fallback); -07 OPEN (arithmetic clean, fallbacks invented); -08 OPEN P1; -09 OPEN P1; -10 NOT IMPLEMENTED. Passing NFRs: 0 of 10 | worse than expected on -01, -08 (not "partially met"); -05 measured, not NOT TESTED |

## State log lines
step,state,n,duration,note
N01,OPEN,8,~2m,8 subscript writers of thesis fields outside Thesis context (morning_gate hold/invalidation; orchestrator hold; lab_control structural_target)
N02,NOT_TESTED,5,~1m,run-level macro mutation prohibited; 5 invariance tests pass; specified acceptance test not located
N03,OPEN,0,0s,cross-ref Track B: silent_zero_violations counter absent; inventory incomplete
N04,OPEN,15,0s,cross-ref Track B: domain grep clean; mixed spread units in Lab writer and quote_change_evidence
N05,OPEN,3006,~30s,triggers present; prev_contract NULL 70/70 cross-run; economics_recomputed constant 1; 453 requotes reuse observation; doi_contract_assessments 0
N06,OPEN,8290,~20s,FILL_RECORDED 0; 0 fill-like keys in decisions; journal 14 closed trades no ledger fill; journal close falls back to EXECUTION_DECISION
N07,OPEN,7,0s,cross-ref Track G: 0 arithmetic; 7 invented fallbacks; lab_control writes structural_target
N08,OPEN,29,0s,cross-ref Track I I3: 9/29 keys absent; 13 literal hits
N09,OPEN,20,0s,cross-ref Track I I2: 20 undocumented gating env vars on import graph
N10,NOT_IMPLEMENTED,0,0s,cross-ref Track I I1: no replay harness or expected-diff manifest
