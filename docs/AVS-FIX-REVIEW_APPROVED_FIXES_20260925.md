# AVS-FIX-REVIEW — Approved fixes, verified and detailed

**Date:** 2026-09-25 · **Branch:** `avs-fix-001` · **Reference run:** `20260924_085940`
**Status:** review only. No code, config or data was changed while the pipeline is running.
**Scope:** the seven-item assessment table (edge ranking, rr_predicted, sizing, GARCH/convexity, invalidation, multi-session paths, prospective record). Each claim was re-checked against the working tree and the 24 September artefacts before the fix was detailed.

---

## 0. Verification summary

| # | Claim in the table | Result | Evidence |
|---|---|---|---|
| 1 | Rank is shadow and uncalibrated; ALG-09 specifies calibration | **Confirmed** | `dropbox/macro/coaching/rank/AVS-RANK-001_rank_not_gate.md` §4–5 (shadow since 14 Sep, `win_prob_predicted` 0.50–0.51 on most rows); `docs/requirements/AVS-REQ-FIX-002_Annex_A_algorithms_and_models.md` ALG-09 (lines 201–235) |
| 2 | rr_predicted is intrinsic value at the structural target, not a holding-period expectancy; 24 Sep Lab book has none populated | **Confirmed, and stronger** | `scripts/avshunter_options_intelligence.py:6622-6634` (`option_value_at_target = max(target − strike, 0)`); `contracts/selected_contract_economics.py:573-587` (same geometry, entry at ask); `contracts/lab_control.py:3248,3811`. In the Lab book the keys `rr_predicted` and `rr_premium_expected` are **absent from all 1,532 rows**, not merely empty |
| 3 | Sizing is out of scope by design | **Confirmed** | Lab book: `position_size_display = HUMAN DETERMINED` on 1,532/1,532; `execution_can_grant_capital = False` on 1,532/1,532; no Kelly or capital field exists |
| 4 | Legacy forward-variance differences 10d−5d; pre-trade focus reads the legacy 6–10d field; convexity gets an empty dashboard; score only 0/2/3; bias multiplier unapproved | **Confirmed, with one correction** | `layer3_forward_variance.py:690-692`; `domain/pretrade_focus.py:248-253`; `scripts/avshunter_options_intelligence.py:8672-8673` passes `{}`; `config/governed_constants_v1.json:13-16` (`bias_multiplier_approved: false`, `UNVALIDATED`). Correction: the Lab book's `convexity_score` maps 1:1 to `campaign_verdict` (REJECT→0.0 ×200, STAGED→2.0 ×1,049, CORE_CAMPAIGN→3.0 ×283) and `convexity_score_source` is blank on every row. It is a verdict encoding, not a five-condition score |
| 5 | 185 missing `invalidation_spot` in the manifest; 375/1,532 Lab rows lack `invalidation_price`, all BLOCKED, no GO/GO_LIMIT lacks it | **Confirmed, and one further defect** | `final_run_manifest.json`: `missing_selected_handoff.invalidation_spot = 185`, `semantic_defect_count = 185`, yet `run_tradeable = true`, `run_tradeable_label = EXECUTION_READY`. Lab book: 375 missing, all `lab_verdict = BLOCKED` and all `morning_execution_route = STAND_DOWN_UPSTREAM_AUTHORITY`; 169 GO + 232 GO_LIMIT all populated. `invalidation_spot` as a key is absent from every Lab row |
| 6 | 37/40 verified one-session paths, 0/40 five-session; no standalone AVS-BT-001 | **Confirmed, one correction** | `docs/AVS-MON-004_PROVENANCE_AND_CLOSURE_ASSESSMENT_20260922.md:21`. No file named `*BT-001*` under `docs/`, `audit/` or `dropbox/`. Correction: the walk-forward specification is **not** in `docs/requirements/`; it is in `docs/AVS-SD-MON-003_PATH_AWARE_MONETISATION_AND_EXPRESSION.md` and the backtest report |
| 7 | +10.9% is a hindsight-selected result | **Confirmed** | `Enhancements/backtest/BACKTEST_STRESS_TEST_OUTCOME_REPORT_20260920.md` §1 and §5.6: 5% priority band, n = 254, joint contract-and-exit oracle, state `EXPLORATORY_NO_AUTHORITY`, "uses future outcomes to choose the contract and exit day" |

---

## 1. Edge ranking (AVS-RANK-001 / ALG-09)

**Verdict.** Valid gap. The rank engine is a v0.1 prototype in shadow; its direction probability is the pipeline's `win_prob_predicted`, which sits at 0.50–0.51 on most rows and 1.0 on a few tiny actuarial buckets. Nothing is waiting on a switch.

**Approved fix, in order.**

1. **Outcome labels first.** For every historical decision row with direction, target, invalidation and hold window, compute the three mutually exclusive classes ALG-09 requires: `TARGET_FIRST`, `INVALIDATION_FIRST`, `TIMEOUT`. Labels look up to 20 sessions ahead, so the label writer must record the session at which the label became knowable.
2. **Calibration table on time-separated partitions.** Train ≤ T₁, validation (T₁, T₂], test > T₂, with the 20-session purge/embargo at each boundary (ALG-09 "Partitions"). Key = `hidden_state_label | phase | compression_bucket | direction | hold_bucket`, hierarchical backoff with κ = 50 shrinkage, `n_min = 200`. Output `calibration_table.json` in DOI vocabulary (`p_target_before_invalidation`).
3. **Probability quality before trading utility.** Report, per direction × hold stratum on test: multiclass Brier, `Brier_skill`, classwise ECE, log loss, ROC-AUC and PR-AUC for `TARGET_FIRST`, top-quintile lift, and coverage. The activation gate in ALG-09 (coverage ≥ 0.60, ECE ≤ 0.10 overall, ≤ 0.15 per stratum, `Brier_skill > 0`, AUC > 0.50, lift > 1.0) is the minimum. The 200-case floor is a policy threshold, not proof of edge.
4. **Then the trading test.** Only after the gate passes: rank the scoreable rows of stored books and compare executable ask-to-bid option outcomes of the rank's top-N against the current desk-gate shortlist on the same sessions. Report both, and report the case where no stratum beats its base rate, because ALG-09 says that result "must be reported, not tuned away".

**Acceptance.** `rk_p_source = CALIBRATION_TABLE` on ≥ 60% of scoreable rows; a reliability curve per stratum in the report; the comparison against the desk gate uses the same friction model as item 2.

**Do not.** Do not promote the rank engine to selection on the basis of the shadow portfolio's `rk_ev_net_pct` alone. That number still depends on the unvalidated vol budget (item 4) and the uncalibrated p.

---

## 2. rr_predicted

**Verdict.** Valid meaning gap. Both computation paths (Options Intelligence line 6622 and `selected_contract_economics.py:573`) return `(intrinsic value at the structural target − entry cost) / entry cost`. That is a payoff at a scenario spot with zero time value, not an expectancy over the planned hold. The Lab book for 24 September does not carry the field at all.

**Approved fix.**

1. **Rename and label, keep the number.** Retain the structural-target intrinsic scenario and expose it under a name that says what it is (`rr_structural_intrinsic_scenario` or the ALG-04 `payoff_structural_net_return_fraction`, "disclosure only"). Any row that still shows `rr_predicted` must carry `rr_calculation_version` and a `scenario_basis` field. Never present it as "predicted".
2. **Add the reachable-path assessment** exactly as ALG-04 already specifies: Black–Scholes at constant IV, scenario grid FLAT / 1σ / 2σ / REACHABLE (k × e_h from the vol budget) / STRUCTURAL / INVALIDATION, at EARLY / MID / LATE timings, IV stresses 0.8 / 1.0 / 1.2, entry at ask, exit at modelled bid with `friction_model_v1` (haircut = min(s/2, 0.15)). Headline the LATE / BASE fields (`payoff_reachable_net_return_fraction`, `payoff_flat_net_return_fraction`, `payoff_invalidation_net_return_fraction`).
3. **Expected return only when the paths are validated.** Combine the ALG-04 payoffs with ALG-09 probabilities into ALG-07 (`calibrated_utility_v2`) only after the ALG-09 gate passes. Until then the row shows the scenario payoffs and `validation_state = UNVALIDATED`.
4. **Populate the Lab book.** `lab_control.py:3248` writes `rr_predicted` only when `quote_owned`; the 24 Sep book has neither `rr_predicted` nor `rr_premium_expected` as keys. Trace why the mapping at line 3811 produced no column and fix the projection so the scenario fields appear, empty where unavailable, on every row.

**Acceptance.** ALG-04 worked example reproduces within ±0.5% (S₀ = 100, K = 105, 30 DTE, σ = 0.30: FLAT −32.3%, REACHABLE +115.3%, STRUCTURAL +331.9%, INVALIDATION −67.5%). The structural +332% and the reachable +115% appear side by side with their basis labels.

---

## 3. Sizing

**Verdict.** Not a pipeline gap. The boundary is intentional and the 24 September book honours it: every row is `HUMAN DETERMINED` and `execution_can_grant_capital = False`.

**Approved position.**

- Keep capital, Kelly fractions and percent-of-capital rules out of AVSHUNTER output. "25–50% Kelly" and "1–2% of capital" are not universal defaults, and for long options the full premium is at risk.
- What may be shown, once validated, is evidence: calibrated `p_target_first`, the ALG-04 outcome range, and the friction assumption. Those are inputs a human sizer can use, not a size.
- `wbs_size_guidance` (values such as "50% of campaign size only", "Full campaign + 25% boost") is relative to a campaign size the pipeline never defines. Leave it, but label it as relative guidance so it cannot be read as capital.
- `position_sizing_engine.py` is modified in the working tree. Whatever it changes must not introduce a capital-denominated field into the Lab book or the manifest.

---

## 4. GARCH horizon and convexity

**Verdict.** Valid, partly implemented. Two horizon definitions coexist and convexity is not being computed where the Lab book reads it.

**Evidence.**

- Canonical: `domain/volatility_budget.py:62` computes the cumulative move `vol × m × sqrt(hold/252)` with a `bias_multiplier` and `bias_multiplier_applied` flag.
- Legacy: `layer3_forward_variance.py:691-692` still emits `em_6_10 = EM(10) − EM(5)` and `em_11_20 = EM(20) − EM(10)`, incremental bands that are not a cumulative budget.
- Consumer: `domain/pretrade_focus.py:248-253` selects `garch_expected_move_6_10d` / `_11_20d` by horizon and compares the target move against it for `TARGET_BEYOND_EXPECTED_MOVE_REVIEW_BAND`. A 6–10D target is therefore judged against the increment for sessions 6–10, not the cumulative move by session 10. `contracts/lab_control.py` also reads the legacy field.
- Governance: `config/governed_constants_v1.json` `volatility_budget`: `bias_multiplier 1.0`, `bias_multiplier_approved false`, `validation_state UNVALIDATED`, `held_out_validation_passed false`.
- Convexity: `scripts/avshunter_options_intelligence.py:8672-8673` calls `compute_convexity_score_oi(dict(signal_row), {})` twice with an empty dashboard, so C2 (signed notional) is always false and C3/C4 fall back to whatever the signal row carries. The Lab book's `convexity_score` is exactly {0, 2, 3} and equals a re-encoding of `campaign_verdict`; `convexity_score_source` is blank on all 1,532 rows.

**Approved fix.**

1. **Field-by-field reconciliation.** Produce a table of every field carrying an expected move (`garch_expected_move_1_5d/6_10d/11_20d`, the canonical budget fields, DOI reachability fields) with producer, consumer, and definition (cumulative vs incremental). Every consumer moves to the cumulative definition from `domain/volatility_budget.py`. Rename or version the incremental fields so they cannot be read as budgets; do not silently change their values.
2. **Repair convexity at source.** Pass the real GEX dashboard (the `_load_dashboard` result already used by Superbrain at `avshunter_superbrain_layer.py:2360`) into the Options Intelligence call, or drop the OI-side call and take the Superbrain result with `convexity_score_source` stamped. A row with no signed notional must report C2 as `DATA_INSUFFICIENT`, not `False`, and the total must be a genuine 0–5 (or 0–6 with C6 vanna) count with `convexity_score_max` populated.
3. **Validate the forecast before approving a multiplier.** Run ALG-10 (`tools/validate_forecast_vol.py` already exists): `RV_h / σ_f,h` per horizon h ∈ {5, 10, 20} and per hidden-state bucket, out of sample on the time-ordered test partition. Report median ratio, IQR, n, `coverage_1σ`, bias, and QLIKE on the **variance** forecast (σ²), not on σ. Pass criteria are already governed: median ratio ∈ [0.90, 1.10] and coverage_1σ ∈ [0.60, 0.76] with the multiplier applied. Only then flip `bias_multiplier_approved` with a `validation_report_id`.

**Acceptance.** `pretrade_focus` review band uses the cumulative budget; no Lab row has `convexity_score` without `convexity_score_source`; the distribution of scores is no longer a function of `campaign_verdict`; `volatility_budget.validation_state` is `VALIDATED` only with a report id.

---

## 5. Invalidation

**Verdict.** Valid source-completeness gap. The proposed blanket release rule is too broad, and the two counts have different denominators.

| Count | Denominator | Population | Value |
|---|---|---|---|
| `missing_selected_handoff.invalidation_spot` | selected-handoff rows (manifest) | pipeline handoff | 185 |
| `invalidation_price` missing | all Lab rows | 1,532 | 375, all BLOCKED / STAND_DOWN_UPSTREAM_AUTHORITY |
| GO or GO_LIMIT rows missing invalidation | actionable rows | 401 | 0 |

**Additional defect found.** The manifest records 185 semantic defects and `pipeline_semantic_health = DEGRADED`, yet `run_tradeable = true` and `run_tradeable_label = EXECUTION_READY`. Technical health should not be allowed to label a run execution-ready while a selected-handoff field is missing on any row that could become actionable.

**Approved fix.**

1. **Execution-ready requires an authoritative invalidation.** A row may reach GO / GO_LIMIT / `HUMAN_APPROVAL_REQUIRED` only with a populated `invalidation_price` (and `invalidation_spot` in the handoff) carrying a source and version. Missing or inferred invalidation on an actionable row is the release blocker.
2. **Retain, do not drop.** Rows lacking invalidation stay in the book as `BLOCKED` with a reason code that names the missing field, so the upstream gap remains investigable. That is today's behaviour for the 375 and it is correct.
3. **Repair provenance upstream.** Trace why 185 selected-handoff rows arrive without `invalidation_spot` (the key is absent from every Lab row, so the projection never carries it) and fix the producer, not the consumer.
4. **Track both counts.** The manifest must report the handoff count and the Lab-book count separately, with denominators, and `run_tradeable_label` must be downgraded when the actionable-row count is non-zero.

**Acceptance.** For the next run: actionable rows missing invalidation = 0 (already true); manifest shows both counts with denominators; `run_tradeable_label` reflects semantic health.

---

## 6. Multi-session paths (AVS-MON-004)

**Verdict.** Valid and fundamental. In the purposive sample, 37/40 one-session paths were verified and 0/40 five-session paths were complete. Purging and embargo control leakage once labels exist; they cannot create exact-contract quotes that were never captured.

**Approved fix, in order.**

1. **Provenance on new captures.** Every quote row written from now on carries provider timestamp, session date, capture instant, contract identity and a writer version. Unversioned or raw-only cells are counted, never promoted.
2. **Coverage test on stored data.** Measure 5-, 10- and 20-session CALL and PUT exact-contract coverage on the existing store, by session and by contract, before any capture change. Publish the fraction of complete verified paths at each horizon.
3. **Writer/storage canary.** Run the production-scale writer in isolation for a full session and verify row counts, sizes and provider-timestamp coverage against the `provider_completeness` thresholds in `config/governed_constants_v1.json` (late-window coverage ≥ 0.10, provider-timestamp coverage ≥ 0.80, session-date coverage ≥ 0.80).
4. **Then routine capture and walk-forward.** Activate routine multi-session capture only after the canary passes. Walk-forward evaluation follows the purged design in `docs/AVS-SD-MON-003_PATH_AWARE_MONETISATION_AND_EXPRESSION.md` and the 20 September backtest report. The table's reference to a requirements-folder walk-forward spec and to AVS-BT-001 should be corrected: there is no AVS-BT-001 document, and the specification lives in AVS-SD-MON-003.
5. **Never backfill.** Historical gaps stay gaps. No snapshot of unverified provenance is inserted to complete a path.

**Acceptance.** A published coverage table per horizon and side; a canary report with pass/fail against the governed thresholds; walk-forward folds whose training windows end before the test session begins.

---

## 7. Prospective record

**Verdict.** Valid. The +10.9% figure is the 5% priority band of a hindsight oracle that chose both contract and exit day (n = 254, five sessions). The report itself states it is not deployable.

**Approved fix.**

1. **Freeze the rule and the decision record.** Write down the candidate selection rule, the contract selector, the exit rule and every threshold, with a hash, before the next session. Any later change starts a new cohort; earlier cohorts are not re-scored under the new rule.
2. **Log selected and rejected.** Every session, record the full candidate list, which rows were selected, which were rejected and why, at decision time, with the quote used.
3. **Score at ask-to-bid.** Outcome is entry at the recorded ask and exit at the recorded bid at the frozen exit rule. Paper quotes are not fills; label them as such.
4. **Matched comparators.** Compare against (a) the current desk-gate process on the same sessions and (b) a simple matched alternative with the same instrument, horizon and direction, such as the nearest liquid ATM contract held for the same window. An index buy-and-hold comparison alone mismatches risk and horizon and is not sufficient.
5. **Guard against backtest overfitting.** Count every historical variant tried and report it with the prospective result. The 20 September tournament already ran many variants; that count is part of the record.

**Acceptance.** A cohort file with rule hash, start session, per-session decision log and outcome ledger; no result quoted without its cohort id and variant count.

---

## 8. Sequencing and dependencies

```
Item 5 (invalidation provenance)  ──┐
Item 4.1 (horizon reconciliation)  ──┼──► Item 1.1 outcome labels ──► Item 1.2–1.3 calibration ──► Item 2.3 utility ──► Item 1.4 rank vs desk gate
Item 4.3 (ALG-10 vol validation)   ──┘                                                                  │
Item 4.2 (convexity at source)      independent, can run now                                            │
Item 2.1–2.2, 2.4 (scenario fields) independent, can run now                                            │
Item 6.1–6.3 (provenance, coverage, canary) independent, can run now ──► Item 6.4 walk-forward ─────────┘
Item 7 (freeze rule, start cohort)  start at the next session, then untouched
Item 3                               no work; keep the boundary
```

Items 1.1, 1.2 and 4.3 are computations on stored data and need no live trade. Item 7 must begin before any of the model changes above land, otherwise the first cohort is contaminated.

## 9. Not verified in this review

- The 2026-09-14 rank-engine funnel figures (1,444 → 288 → 55 → 10) were taken from the coaching note, not recomputed.
- The 37/40 and 0/40 provenance figures were taken from the assessment document, not recomputed against the store.
- `position_sizing_engine.py`, `contracts/lab_control.py` and `scripts/avshunter_options_intelligence.py` are modified in the working tree; this review read the working-tree versions, not the committed ones.
