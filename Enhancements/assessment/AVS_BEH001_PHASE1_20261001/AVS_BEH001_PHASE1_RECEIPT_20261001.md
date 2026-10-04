# BEH-001 Phase 1 receipt (1 Oct 2026)

Scope: the Part 4 decisions in `Enhancements/decision_map/AVS_SD_BEH_001_AMENDMENT_A2_DECISIONS_20261001.md`, phase 1. ACK added two instructions on 1 Oct during the build; both are applied here:
- "once an outcome is reached it can enter another stage unless the ticker is not trading and has been delisted";
- "we want our product (tickers) to reenter the line as new so it can be evaluated again through the whole cycle even when we are already in the trade".

Nothing is committed. Production direction stays on `legacy_rollback`.

## 1. Built

| Item | Change | Tests |
|---|---|---|
| RQ-1 outcome per signal type | `domain/structure_behaviour/signals.py`. Each candidate gets `Outcome_Level` and an `Outcome_Definition` rule: range boundary, nearest swing beyond the trigger, or a measured move; monitoring observations get `NONE:`. `Age_Bars` is added. | `tests/test_beh001_outcome_and_lineage.py` (8), including mirror symmetry of outcome levels |
| RQ-1 activation is not outcome | New state `OUTCOME_REACHED`: a close at or beyond the outcome after activation, before invalidation is accepted (`config/beh001_behaviour_v1.json` → `outcome.reached_closes`). It is never handed off as a live side. | same file |
| RQ-2 failure → next logic | A Failed Spring or Upthrust continuation names the failed event's candidate in `Parent_Candidate_ID`. | same file |
| ACK: outcome ends a stage, not the ticker | An `OUTCOME_REACHED` candidate states its next stage. Later candidates on the same ticker, timeframe and scope name it as parent. Field `Outcome_Reached_As_Of`. | `test_reaching_an_outcome_ends_the_stage_not_the_ticker`. This test was written after the change; it was not seen red. |
| C-03 core candidate ledger | `domain/structure_behaviour/lifecycle.py` (pure rules) and `canonical_data/behavioural_candidate_ledger.py`. Append-only SQLite at `data/canonical/behavioural_candidate_ledger.sqlite`, with no-update and no-delete triggers. Events: FIRST_SEEN, STATE_CHANGED, LEVELS_REVISED, NO_LONGER_DETECTED (only for a ticker read this run), REAPPEARED, TICKER_NOT_TRADING (last bar more than `ledger.not_trading_after_sessions` = 5 business days behind the run). Candidates are annotated with `Lifecycle_Event`, `First_Seen_Run` and `First_Seen_As_Of`. The ledger annotates; it never filters. | `tests/test_beh001_candidate_ledger.py` (10) |
| Discovery wiring | `avshunter_discovery_ULTIMATE.py`: read set, last bar per ticker, `_beh001_record_ledger` (never fails the run; `LEDGER_UNAVAILABLE` plus manifest status `behavioural_candidate_ledger`). | ledger test 8; the test caught a `logger` NameError in the failure path, now fixed |
| ACK: a held ticker re-enters as new | `scripts/run_vanguard_from_packages.py`. An open Trade Contract no longer skips the ticker. Governance runs alongside, and `stamp_governance` writes `governance__open_contract`, `governance__verdict` and `governance__reason` on pass and reject rows. VNG-11 is amended. One open contract per ticker (`vanguard/trade_contract.py`) is an execution rule and is left to Execution. No open contracts exist today. | `tests/test_avs_dir002_open_contract_reconciliation.py` (3) |

Existing owners reused rather than rebuilt:
- C12 `passage.evaluate_passage`, `estimators` (Aalen–Johansen, block resampling) and `base_rate.matched_incidence` for the evaluation;
- the Decision and Outcome Ledger's append-only pattern for the candidate ledger. Candidates are not written into that ledger, because it records decisions on a thesis and candidates are pre-thesis observations. Phase 2 links the two.

## 2. Corrected evaluation (A2-1)

**Scripts** (in `Enhancements/direction_evidence/`):
- `beh001_eval_candidates.py`: stage A, candidates at each cut, with Discovery eligibility replicated;
- `beh001_eval_v2.py`: stage B, C12 scoring;
- `beh001_eval_v2_report.py`.

**Rules fixed before reading:**
- Each candidate is followed on bars of its own timeframe, built from completed daily bars after the cut. Limits: 250 daily, 104 weekly, 24 monthly bars.
- C12 passage rules apply: same-bar AMBIGUOUS counts as a stop; data gap and open trades are censored.
- The baseline applies the same ATR-unit barriers on the same date, in the same direction, to 492 tickers. There is no 50% reference.
- Aalen–Johansen cumulative incidence. Block bootstrap: 2,000 resamples, seed 20261001; blocks are 2 cuts (1d), 6 cuts (1w) and 12 cuts (1mo).
- ESTIMABLE needs at least 100 scorable cases and at least 20 blocks.

**Population:**
- 500 hash-selected tickers. 276 have the 260 bars of history needed before a cut. 215 have fewer than 260 bars in the canonical database (a parked data item), and 8 have no bars.
- 102 cuts, 2022-09-16 to 2026-09-28, with data to 2026-09-29.

**Runs:**
- `Enhancements/outcomes/beh001/eval_v2/`: engine before the OUTCOME_REACHED fix.
- `Enhancements/outcomes/beh001/eval_v3/`: final engine; this is the result of record.
- `uncapped_v1` is superseded (provisional design).

### Finding that changed the build
In eval_v2, 51% of daily, 48% of weekly and 41% of monthly ACTIVATED candidates had already reached their own outcome level at the cut, yet were published as live. After the fix (eval_v3), unscorable ACTIVATED candidates fell from 6,075 of 11,525 to 24 of 4,622.

### Results (eval_v3; excess = observed − matched, 95% interval)

| Test | TF | Scorable | Excess, short horizon | Excess, long horizon | Status |
|---|---|---|---|---|---|
| Activation (trigger before invalidation) | 1d | 20,629 | h20 −0.1 pt [−0.8, +0.6] | h250 −0.5 [−1.2, +0.2] | ESTIMABLE |
| Outcome after activation | 1d | 4,598 | h20 −1.0 [−2.4, +0.5] | h250 +1.6 [−0.1, +3.3] | ESTIMABLE |
| Outcome from detection | 1d | 24,712 | h20 −0.8 [−1.3, −0.2] | h250 −0.8 [−1.5, −0.1] | ESTIMABLE |
| Activation | 1w | 19,955 | h13 −0.1 [−1.2, +0.8] | h104 −0.2 [−1.2, +0.7] | NOT_ESTIMABLE (17 blocks) |
| Activation | 1mo | 9,880 | h6 +3.1 [+2.0, +4.1] | h24 +2.1 [+1.4, +3.1] | NOT_ESTIMABLE (6 blocks) |
| Outcome from detection | 1mo | 10,345 | h6 −1.5 [−2.3, −0.4] | h24 +3.9 [+2.4, +5.2] | NOT_ESTIMABLE (6 blocks) |

- **Type level:** 4 of 47 estimable groups have intervals excluding zero; about 2–3 would be expected by chance.
  - Three are slightly negative: SOW→LPSY and SOS→LPS activation at campaign scope (each −2.4 pt), and the local SOS→LPS outcome from detection (−1.7).
  - One is positive: the bullish campaign "Trend Continuation after Shallow Test", outcome after activation, +10.2 pt [+5.7, +14.4] on 557 cases. It is a hypothesis for held-out confirmation, not a finding.
- **Original vs newly admitted:** daily results are alike. Weekly and monthly newly admitted candidates are below the matched base. For example, weekly outcome after activation is −6.1 [−11.9, −0.9], and monthly activation is −1.5 [−3.6, −0.1]. This supports C-01 as decided: liquidity is an Options-stage check recorded per candidate, not a removal.

**Reading.** BEH-001 reads behaviour symmetrically and honestly, but on these tickers the behavioural candidates do not by themselves beat the same-date, same-geometry market. This is consistent with ACK's edge definition (enter before the crowd; statistical proof is later validation). It is also why phase 2 carries this evidence with each candidate rather than gating on it. The monthly figures are the most interesting and the least reliable; more history or blocks are needed before they mean anything.

## 3. Regression
`regression_results.txt` in this folder: 122 test files (BEH-001, DIR-002, Vanguard, Morning, Discovery, Evening, Options, governance, handoff, thesis, macro, orchestrator, package), one process per file, failures counted per file.

**Result:** 997 passed, 1 skipped, and 4 failed in 2 files. Both files fail exactly as at the 1 Oct baseline (`Enhancements/assessment/AVS_DIR002_STEP1_BASELINE_20261001/`), so this build introduced no new failures:
- `tests/test_vanguard_reference_input_p2.py`: 3 failed, 3 passed, as in the baseline re-run. The retained real run's packages carry `dcv_valid` False; this depends on the stored data's age, not on code.
- `tests/test_macro_builder_governed_integration.py::test_current_market_data_builds_complete_governed_prompt`: same failure ID as the baseline. The live market-data source reports `SOURCE_NOT_PUBLISHED`.

Both are listed for continuous improvement; neither is in BEH-001 scope.

## 4. Live effect on the next Evening run (additive)
- Discovery creates `data/canonical/behavioural_candidate_ledger.sqlite` and adds these columns to `behavioural_candidates_*.csv`: `Outcome_Level`, `Outcome_Definition`, `Outcome_Reached_As_Of`, `Parent_Candidate_ID`, `Age_Bars`, `Lifecycle_Event`, `First_Seen_Run`, `First_Seen_As_Of`. The manifest gains `behavioural_candidate_ledger`.
- Vanguard rows gain `governance__*` columns. With no open contracts, all values are `False` or empty.

## 5. Next (phase 2)
- Candidate-level handoff (C-03 handoff, C-01, C-02, C-07): Options interrogates each live candidate, monitoring observations travel separately, and liquidity is recorded as an Options attribute.
- Duration evidence (C-04, C-05, RQ-3): time to activation, outcome and invalidation from the eval_v3 incidence curves, conditioned on `Age_Bars`.
- Phase 3: C-06.

## 6. Parked by ACK (1 Oct 2026)
- **DCV-CLOCK:** the data-contract staleness verdict has two owners and two clocks.
  - The manifest judges against the run session (`avshunter/c0_run/canonical_manifest.py:128`).
  - Vanguard's `DCV.validate` judges against today's date (`scripts/data_contract_validator.py:210`; thin-package `today` default at `avshunter/c0_run/thin_package.py:134`).
  - Impact: none on same-day Evening runs (0 stale rejects in the runs of 26, 27 and 30 Sep). Re-running Vanguard more than 5 calendar days after a run rejects every ticker as `DATA_FAILURE_STALE_DATA`. Stored packages carry a pre-attachment `NO_OHLCV` annotation.
  - Proposed fix: the manifest verdict is the single owner; reference date = run session, counted in sessions; test first.
  - Open decision for ACK: whether truly stale history rejects or is flagged.
  - `tests/test_vanguard_reference_input_p2.py` stays red until this is fixed.
- **NO_OHLCV-50:** 50 `DATA_FAILURE_NO_OHLCV` Vanguard rejects per run. These likely overlap the short-history tickers (215 of 500 sampled have under 260 bars) and belong to the parked data-coverage item.
