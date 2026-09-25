# C1 — Scenario values on every row, with conspicuous assumptions: root cause and design

**Date:** 2026-09-25 · **Owner of the change:** Lab presentation (`contracts/lab_control.opportunity_book_row`, C14, read-only projection). The valuation itself is DOI's (`canonical_data/dynamic_options_valuation`, ALG-04 `scenario_valuation_v2`) and is not changed · **Authority:** none; display only · **Requested by:** ACK ("carry on with C1"); reviewer amendments C1–C2 ("show reachable, flat, structural and invalidation payoffs with assumptions and friction, not as a predicted return"; "publish p\* as review information, not a gate"; "do not describe the scenario EV as measured expectancy")

## 1. What exists and what the trader sees

| Fact | Evidence (25 Sep morning book, 273 actionable rows) |
|---|---|
| ALG-04 is implemented and runs in production: DOI values the governed contract on a grid of 6 paths (FLAT, FAVOURABLE_1SIGMA, FAVOURABLE_2SIGMA, REACHABLE, STRUCTURAL_DISCLOSURE, ADVERSE_INVALIDATION) × 3 timings (EARLY, MID, LATE) × 3 IV stresses (CONTRACTED, BASE, EXPANDED), with exit after friction | `doi_scenarios_json`: 54 scenarios per row, populated on 138 of 273 actionable rows; on all 138 the DOI governed contract equals the selected contract |
| The other 135 actionable rows have no scenarios because DOI did not rank the family (`doi_projection_state = NOT_EVALUATED`, `doi_projection_reason = DOI_FAMILY_NOT_RANKED`) | not a data defect; a DOI-side gate, to be stated |
| The trader sees none of it as a number: the six headline payoffs live inside a 54-element JSON with no flat column, no friction label, no validation state | book field list |
| The headline the trader does see, `rr_predicted` / `rr_premium_expected`, is intrinsic value at the structural target with no time value and no friction (fix item F2), and nothing on the row says so | `lab_control.py:3169, 3459-3461` |
| No `friction_assumption` label exists anywhere in the code, although ALG-04 requires one | grep |
| `doi_p_target_before_invalidation` is never populated (ALG-09 pending), so no probability can be shown; the break-even the trader must believe can be | 0 of 273 |

## 2. Design (presentation only, additive)

A pure function `scenario_disclosure_from_row(sig)` in `lab_control`, called from `opportunity_book_row`, producing:

| Field | Value |
|---|---|
| `scenario_state` | `AVAILABLE` · `NOT_ASSESSED` (with `scenario_reason` = the DOI projection reason) · `CONTRACT_MISMATCH` (DOI governed symbol ≠ selected) · `NOT_APPLICABLE` (no contract) |
| `scenario_contract_symbol`, `scenario_basis = LATE_TIMING_BASE_IV_AT_GOVERNED_TIME_STOP`, `scenario_pricing_model_version` (`doi_assessment_calculation_version`) | identity and basis |
| `payoff_flat_net_return_fraction`, `payoff_1sigma_…`, `payoff_2sigma_…`, `payoff_reachable_…`, `payoff_structural_…`, `payoff_invalidation_…` | the LATE / BASE `net_return_fraction` of each path, entry at ask, exit after friction (ALG-04 headline names) |
| `payoff_reachable_iv_stress_range` | [CONTRACTED, EXPANDED] at LATE, so the IV sensitivity is visible |
| `friction_assumption = CURRENT_SPREAD_PROXY_CAPPED`, `friction_spread_cap`, `scenario_valuation_version` | from `config/governed_constants_v1.json` `contract_economics` |
| `volatility_budget_validation_state`, `volatility_budget_bias_multiplier` | from `volatility_budget` (today `UNVALIDATED`, 1.0). After C3 this is the most important label on the row |
| `breakeven_p_target_two_outcome` = −inval ÷ (reach − inval), `breakeven_basis = TWO_OUTCOME_LOWER_BOUND_REACHABLE_VS_INVALIDATION` | review information; the timeout outcome is not in it, so it is a lower bound |
| `scenario_is_expected_return = False` | conspicuous |
| `rr_predicted_basis = INTRINSIC_AT_STRUCTURAL_TARGET_NO_TIME_VALUE_NO_FRICTION`, `rr_predicted_is_expected_return = False` | the legacy number relabelled; the number itself unchanged for its consumers |

Nothing is computed that DOI did not compute; the Lab flattens and labels. No ranking, verdict or route reads any of these fields.

## 3. Tests (written first), `tests/test_c1_scenario_disclosure.py`

- A row with a synthetic 54-scenario JSON for the selected contract → the six LATE/BASE payoffs, the stress range, the break-even, the labels.
- No JSON with a DOI reason → `NOT_ASSESSED` and the reason; every payoff `None`.
- JSON for a different contract → `CONTRACT_MISMATCH`, no payoffs.
- Reachable below invalidation → break-even `None`, never clipped.
- The fields are in `FINAL_BOOK_FIELDS`; the golden's additive list is extended.

## 4. Result (implemented 25 Sep 2026, uncommitted pending ACK)

| Item | Outcome |
|---|---|
| Change | `contracts/lab_control.py` +111: `scenario_disclosure_from_row`, a cached reader of the governed friction and vol-budget constants, 22 disclosure fields in the book list and projection. Golden additive list extended |
| Finding during the build | The Lab deliberately strips every `rr_*` field before publishing ("R:R is retained in upstream research artefacts only", `lab_control.py:4805`), so `rr_predicted` never reached the book in the first place; the relabel fields are named `legacy_rr_basis` / `legacy_rr_is_expected_return` and describe the upstream number |
| Tests written first | `tests/test_c1_scenario_disclosure.py`: 8 rules; all pass |
| Regression | ILA golden 7/7, book integrity E3–E7 31/31, book integrity L1–L3 24/24, Lab ranking export 2/2, options liquidity morning Lab 7/7, pretrade focus 9/9, evening thesis 17/17, A1 7/7, D2 6/6, F1.b 7/7; `--evening --plan-only` exit 0 |
| Preview on this morning's real actionable rows (in memory) | 135 AVAILABLE, 138 NOT_ASSESSED (135 `DOI_FAMILY_NOT_RANKED`, 3 `NO_COMPARABLE_CONTRACT_UTILITY`). Medians on the 135: FLAT −42%, 1σ +79%, REACHABLE +159%, STRUCTURAL +205%, INVALIDATION −85%; break-even p\* median 0.32, 112 rows ≤ 0.40. Labels on every row: `CURRENT_SPREAD_PROXY_CAPPED` 0.15, `volatility_budget_validation_state = UNVALIDATED`, `scenario_valuation_v2` |

**Reading.** DOI's reachable payoff is roughly three times the research harness's for the same rows (+159% against +56%), because DOI values at the 20-session governed time stop with a 20-session vol budget, while the harness valued at the horizon hold. Both are labelled now. With C3 having found the forecast about 30% high, the disclosed `UNVALIDATED` state beside a +159% reachable payoff is exactly the warning the reviewer asked for: the number is a scenario under an assumption the data does not yet support, not an expectation.

## 5. Acceptance

Monday's morning book: 138-type rows show the six payoffs beside `friction_assumption` and `volatility_budget_validation_state = UNVALIDATED`; the 135-type rows read `NOT_ASSESSED: DOI_FAMILY_NOT_RANKED`; `rr_predicted_basis` on every row that has an `rr_predicted`.
