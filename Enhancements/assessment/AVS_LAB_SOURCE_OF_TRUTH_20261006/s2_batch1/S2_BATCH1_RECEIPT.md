# S2 batch 1 receipt: E12, H1, E15 and the staleness decisions (6 Oct 2026)

**Status:** built and TESTED_UNCOMMITTED. The full regression suite is running, one file per process. Batch acceptance is that suite plus ACK's next Evening and Morning runs (ACK: "why do we have to do this now instead of implementing the fixes" → fixes are batched and accepted together, each with its own tests and receipt). S2-1 is in `s2_lineage/S2-1_BUILD_RECEIPT.md`.

## E12: an option with no computed value is an option-review FLAG (ACK "Yes")
- **Test first:** `tests/test_avs_e12_option_review.py` (3 of 4 failed before the change; 4 pass after).
- **Change:** `morning_gate.py`. The new `_OPTION_VALUE_NOT_ASSESSED` map turns NOT_COMPUTED → `OPTION_VALUE_NOT_COMPUTED` and NOT_ASSESSED_VOLATILITY_ONLY → `OPTION_VALUE_VOLATILITY_ONLY`. These now give FLAG / `OPTION_REVIEW` / `MANUAL_REVIEW`. The unlock condition reads "The ticker assessment is unchanged…". PAYS stays GO, and DOES_NOT_PAY keeps its own FLAG.
- **Superseded tests, updated in the same change with the reason:**
  - `test_avs_sot_s0_characterisation.py` (the pinned GO now flips to FLAG);
  - `test_avs_step5_move_pays.py` (the 3 Oct rule "NOT_COMPUTED does not block on its own" is replaced).
- **Frozen-run effect:** the 7 GO rows without a value become option-review FLAGs. After S2-1 all 7 regain a level, so on the next run E12 only catches rows that still lack one.
- **Related tests:** Morning lanes 3, Morning authority 20, repair/runway recompute 6, contract repair 7, move-pays 4. All pass.

## H1: the execution-gate file keeps every column
- **Test:** the S0 characterisation test was flipped to state the fix: the header is the union of all rows, and each row keeps its own values.
- **Change:** `execution_gate._write_csv` builds its header from the union of row keys in first-seen order. It used to be `rows[0]` only, which lost 71 columns on 20261006.
- **Related tests:** direction governance contract 17, GEX/macro display-only 3, runtime adapters 4, DDD execution authority 16, monetisability gate 9, OLM execution authority 27. All pass.

## E15: spread units, thresholds to config, 30% check removed (ACK "E15 a remove 30%"), and the staleness decisions ("include both")
- **Test first:** `tests/test_avs_e15_spread_units.py` (6 failed before the change; 10 pass after).
- **Config:** `config/governed_constants_v1.json` gains:
  - `spread_policy` v1, unit FRACTION_OF_MID, with **values unchanged**: executable 0.18, reviewable 0.25, execution-gate full size 0.08, research pass 0.15, tier bands 0.15/0.25, EOD repair 0.15/0.25;
  - `trigger_freshness` v1 (max source age 2 sessions).
- **Readers moved to config:**
  - `domain/long_option_execution.py` (`load_spread_policy`, `SPREAD_POLICY`; the 18/25 percent constants are derived from it);
  - `execution_gate.ExecutionGateConfig.SPREAD_FULL`;
  - OI `OPTIONS_SPREAD_PASS_FRACTION` / `OPTIONS_SPREAD_HARD_FRACTION` (renamed: they held fractions under `_PCT` names);
  - `contracts/opportunity_tier.py` (tier bands, `SPREAD_TIER_2_MAX`);
  - the EOD repair profile;
  - `trigger_layer.TRIGGER_MAX_AGE_SESSIONS`.
- **Unit guesses removed:**
  - `eod_candidate_engine._spread_pct_from_row` now reads `contract_spread_pct` as a fraction and `eil_spread_pct_live` as a percent.
  - `dynamic_options_probability._spread_fraction` reads the supplied value as the owner's fraction.
  - **Effect:** a 140% spread is no longer read as 1.4%. The EOD repair profile now flags `SPREAD_REPAIR_NEEDED` for such contracts. `contract_spread_pct_eod` is consistently a percent; S0 found it straddling both units.
- **Removed:** the EIL 30-percent spread reason label (it decided nothing; `allowed` is unchanged), and the dormant macro-age 0.85× haircut in `regime_consensus.py` (rule 6; quarantined per K-4).

## Tidy (ACK standing instruction) in this batch
- Removed: the EIL spread variable and its dead check; the macro haircut block; the two unit-guess branches.
- Renamed: fraction constants that carried `_PCT` names (OI).
- Retired from decisions: the "NOT_COMPUTED does not block" rule (E12).

## Still to do in this batch
- Full regression suite (running).
- A1 and #3 need ACK sign-off on their designs: `S2_DESIGNS_A1_AND_3.md`.

## Full regression suite (6–7 Oct 2026; batch S2-1, E12, H1, E15)
- **Coverage:** 434 files, one process each: **3,593 passed, 8 failed** (in 5 files).
- **Caused by this batch:** `test_eod_options_research_handoff` (2). The fixture wrote `contract_spread_pct` as a percent (5.0 / 30.0), which only worked through the removed unit guess. Run 20261006 confirms the field is the owner's fraction on 1,041 of 1,041 rows, including all 79 above 1. The fixture was corrected to 0.05 / 0.30, and the file passes.
- **Not caused by this batch:**
  - `msi/test_regression` (1) and `test_avs_intraday_bulk_persist` (1) pass when re-run alone (load-flaky).
  - `test_canonical_manifest_p1` (1) and `test_vanguard_reference_input_p2` (3) depend on today's date: they compare frozen late-September runs whose bars are now 11 days old (`dcv_valid` False), the known DCV-clock failures.
- **MSI files:** `msi/test_functionality` (62 passed, 1 skipped) and `msi/test_logic` (95 passed) pass when re-run; they had printed no summary line in the batch log.

## A1: keep an aged share price (ACK "approve A1")
- **Test first:** `tests/test_avs_a1_aged_share_price.py` (4 of 5 failed before the change; 5 pass after).
- **Change:**
  - `morning_gate.py`: the 300-second literal and the `STALE_PROVIDER_PRICE` rejection are removed. A valid SmartMid is kept, with `live_price_age_seconds`, `live_price_updated_utc` and `live_price_state` (CURRENT / AGED_REFERENCE from config `share_price_label`, DISPLAY_ONLY 300 s). Future-dated or missing timestamps and invalid midpoints are still rejected.
  - Book: `live_price_age_seconds` and `live_price_state` are added (`FINAL_BOOK_FIELDS`, `opportunity_book_row`).
  - Card: §8 "Share price · N min old · aged reference".
- **Superseded test updated:** `test_morning_marketdata_stock_price` (the 16-minute rejection becomes kept, AGED_REFERENCE).
- **No other code reads the price age** (checked across the code), so nothing downstream can gate on it.
- **Acceptance:** the rejected prices of the 17 rows on 20261006 were not stored, so the effect is measured on the next live Morning run.

## S2-3 (#3): strikes against the valued level (ACK "approve #3")
- **Test first:** `tests/test_avs_s2_3_strike_level.py` (4 failed before the change; 4 pass after).
- **Change** (`scripts/avshunter_options_intelligence.py`):
  - `strike_selection_level()` calls the same `domain.anticipated_move.anticipated_move_fields` as the EOD valuation, on the governing setup's thesis fields, and returns `anticipated_level_q50`.
  - `filter_strikes_to_level()` replaces the inline filter that used `structural_target or target_reachable`.
  - The context publishes `strike_filter_level`, `strike_filter_basis` (ANTICIPATED_LEVEL_Q50 / NO_ANTICIPATED_LEVEL) and `prior_range_extreme` (supporting).
  - No level means no filter, stated; there is never a fallback to the range extreme.
- **Measured on the frozen GOs:**
  - 47 of 51 have a level;
  - 46 selected strikes still pass;
  - 1 would be excluded: KMT, 35C vs a valued level of 33.73;
  - the filter is looser than the range extreme on 30 and tighter on 13.
  - Contract changes follow from scoring on the next live run.
- **Not in this change (next):**
  - monetisability still uses the legacy target chain (link 5, role AUDIT);
  - the `structural_target` field keeps its name for its other readers (OIS wall points, Morning lifecycle fallback). Those readers move with the resolver work (E1 addition, `resolve_target`).

## Options Intelligence regression after #3
All 66 test files that load Options Intelligence pass, including `msi/test_functionality` (62) and `msi/test_regression` (29).

## Monetisability at the valued level (ACK "carry on with monetisability", 7 Oct 2026)
- **Test first:** `tests/test_avs_monetisability_anticipated_level.py` (4 failed before the change; 4 pass after).
- **Change:**
  - `contracts/selected_contract_economics.evaluate_long_option_monetisability` values the contract at `anticipated_level_q50` only. The legacy chain `target_spot` → `target_price` → `structural_target` (the prior range extreme) is removed.
  - Missing level: `DATA_MISSING` / `ANTICIPATED_LEVEL_MISSING`, never a fallback.
  - Output renamed to say what was measured: `monetisability_structural_target_spot` → `monetisability_target_spot`, plus `monetisability_target_basis`.
  - Reason renamed: `ANTICIPATED_LEVEL_DOES_NOT_CLEAR_BREAKEVEN`.
- **Readers renamed with it:** the time-value companion, `lab_control` (book fields, row), `direction_governance:973`, and the Morning swap reset list.
- **EOD engine:** monetisability is now computed **after** the anticipated move, at the candidate's `anticipated_level_q50`. It used to be computed before the anticipated move existed.
- **Superseded tests updated** (each with its reason): the S0 characterisation (flipped), `test_selected_contract_economics`, the w34 time-value fixtures and reason, and the `test_eod_options_research_handoff` fixture (now supplies the governing setup's evidence).
- **Test result:** all 42 monetisability-related files pass.
- **Measured on the frozen GOs at the anticipated level:**
  - NOT_MONETISABLE falls from 38 to 24 (11 become MONETISABLE, 4 LIMITED);
  - "PAYS but NOT_MONETISABLE" falls from 33 to 22.
- **Why 22 remain:** monetisability is **intrinsic at expiry** (no time value), while PAYS values the option with its remaining time value. These are legitimately different measures (glossary: monetisability = AUDIT).
- **Open (link 5, needs ACK):** monetisability still *decides*:
  - `lab_control.py:1697–1704` turns an EOD Lab GO/PROBE into CONTRACT_REPAIR;
  - `pretrade_focus.py:157` sets the focus lane;
  - `opportunity_tier.py:242` sets the tier.

  Under the approved field-role registry its role is AUDIT, so these reads would move to the decision owner (the anticipated move's pays state).

## Round 2 (ACK 7 Oct 2026 decisions: 1/L5, 4/L4, 5/L3 option b, 6/A2-A3, 7/A7, 8/Phantom; commit after the live run)

### L5 + A7: monetisability out of decisions; a prior-session quote is not a conflict
- **Test first:** `tests/test_avs_l5_monetisability_out_of_decisions.py` (6 failed before the change; 7 pass after, including the book-level test).
- **Change:**
  - `contracts/lab_control._economics_identity`: economics are comparable when the anticipated value was computed for the exact selected contract. New reasons: `ANTICIPATED_VALUE_NOT_COMPUTED_FOR_SELECTED_CONTRACT` / `…_CONTRACT_IDENTITY_MISSING` / `…_CONTRACT_MISMATCH`.
  - `domain/pretrade_focus.project_pretrade_focus`: the focus lane follows the pays state. Lanes renamed `WATCH_MOVE_DOES_NOT_PAY` and `OPTION_VALUE_REVIEW`; LIMITED is retired. A7: the session-date conflict is removed, and only symbol plus quote-dataset identity is checked.
  - `project_evening_thesis` (a fourth monetisability reader found while building): reads the pays state.
  - `contracts/opportunity_tier`: a tier requires PAYS. Three monetisability weaknesses and `_MONETISABLE_STATES` are retired.
  - `anticipated_contract_symbol` is recorded by the EOD engine and the Morning swap recompute, and added to `ANTICIPATED_MOVE_FIELDS` so it reaches the book.
- **Defect found by the fixture update and fixed:** the book row dropped `anticipated_contract_symbol`, which would have locked every PAYS row to CONTRACT_REPAIR. A book-level test was added.
- **Superseded tests updated** (11 files, each change commented): opportunity tier, runtime adapters, the INT-001 horizon and scenario files, evening thesis, ILA golden allowlist (rename plus A1 fields), Lab governed handoff, legacy EV retired, Morning-Lab replacement, pre-trade focus.

### L4: execution-gate GEX warnings display only
- **Test first:** `tests/test_avs_l4_gex_display_only_gate.py` (3 failed before the change; 5 pass after).
- **Change:** `execution_gate.py`.
  - The low-runway, above-gamma-flip and target-beyond-runway warnings go to `gate_display_warnings` and never change `final_action`.
  - Decision warnings (spread, IV, delta) are unchanged.
  - Runway is direction-aware: a call measures to the call wall, a put to the put wall, with the gamma-flip proxy for puts. It used the put wall for both.
  - Thresholds move to config `execution_gate` at unchanged values.
- **Related tests pass:** D6/D7 display-only 3, OLM execution 27, DDD execution 16.

### L3: no evidence hold means no minimum DTE (ACK option b)
- **Test first:** `tests/test_avs_l3_no_evidence_hold.py` (4 failed before the change; 4 pass after).
- **Change:**
  - `domain/option_contract_liquidity.calculate_dte_requirement(None)` gives `minimum_required_dte=None`, `dte_requirement_basis=NO_EVIDENCE_HOLD`; the minimum holdable DTE is kept.
  - The {5, 10, 20} restriction and `GOVERNED_HOLD_SESSIONS` are removed. A stated hold gives basis STATED_HOLD and an evidence hold gives EVIDENCE_HOLD.
  - The executability wrapper applies only the holdable floor when there is no minimum, with reason `NO_EVIDENCE_HOLD`.
  - `LifecycleInputs.remaining_hold_sessions` is optional.
  - `morning_gate._morning_hold_sessions` reads only the DURATION_EVIDENCE planned hold. The fallbacks to remaining/EV3/L2 holds and to numbers parsed from labels are removed, and hold is no longer a required lifecycle input.
- **Scope kept:** the contract-selection runway floor (the OI governed 20-session window for rows without evidence) is unchanged. ACK is asked separately.

### A2/A3: the Interpreter discloses evidence age and never blocks on it
- **Test first:** `tests/test_avs_a2_a3_interpreter_age_disclosed.py` (3 failed before the change; 4 pass after).
- **Change:**
  - `pipeline_interpreter/evidence_resolver._refresh_requirement`: STALE domains are disclosed (`AGE_DISCLOSED`, `aged_domains`); only MISSING or INVALID block.
  - `pipeline_interpreter/assessment_contract.build_assessment`: STALE gives the finding `EVIDENCE_AGE_DISCLOSED:<domain>`; MISSING or INVALID still rejects, with the finding `BUNDLE_EVIDENCE_MISSING_OR_INVALID`. The status name is kept for compatibility.
- **Superseded tests updated:** `test_msi_interpreter_handoff` (the aged-quote test) and `msi/test_flow` (W-05).

### Phantom: its own fields only
- **Test first:** `tests/test_avs_phantom_writes_own_fields.py` (2 failed before the change; 2 pass after).
- **Change:** `scripts/phantom_engine.apply_payload` adds Phantom's evidence and never rewrites `options_score`, `options_route_verdict` or `positive_factors`. `phantom_execution_authority` is `EVIDENCE_ONLY` (or `NO_OVERRIDE_HARD_VETO`).
- **Tidy:** the dead `run_phantom_layer`, the `PHANTOM_RUNNER` config and the `scripts/run_phantom.py` wrapper are removed (unstaged; commit after the live run). `test_ev3_orchestrator_order` slice end updated.

### Contract runway: C (pooled evidence) with B (volatility) fallback (ACK "build C with B fallback")
- **Test first:** `tests/test_avs_runway_pooled_and_vol_fallback.py` (failed at import before the change; 6 pass after).
- **Change:**
  - `domain/structure_behaviour/duration.pooled_level_q80`: longest sufficient q80 across scope and age for the same timeframe, type, direction and test.
  - `domain/anticipated_move.runway_fallback`: C, then B (t = 252 × (|level/spot − 1| / (k × vol))²), then NO_RUNWAY_ESTIMATE.
  - OI `contract_runway_policy` no longer calls `governed_thesis_window_sessions()`. With no estimate, the floor is the minimum holdable DTE. The unused horizon key is removed.
  - The OI context computes the fallback when the setup has no own evidence.
  - The EOD lifecycle uses the same hold as selection (`contract_runway_hold_sessions`), and the hold is optional.
- **Measured on run 20261006, the 667 rows without their own evidence:**

  | Basis | Rows | Floor (calendar days) |
  |---|---|---|
  | Pooled evidence (C) | 24 | 20–111, median 30 |
  | Volatility (B) | 17 | 13–19 |
  | No estimate | 626 | 9 (holdable past issue only) |

  - 584 of the 626 have no resolved direction and are blocked anyway.
  - **Among GO and FLAG rows, 30 have no estimate (3 GO, 27 FLAG).** Contract selection can now pick contracts as short as 9 days for them; the floor was 40 before. Raised with ACK.
  - 658 floors are below the old 40 days and 7 are above.

### Calibrated B (ACK "build the calibrated B", 7 Oct 2026)
- **Reality check:** how much of real level hits each runway covers (target about 80%).

  | Runway | Daily | Weekly | Monthly | Note |
  |---|---|---|---|---|
  | Own evidence | 82% | 84% | 88% | Realistic |
  | Pooled C | — | 58% (33 hits) | 100% (15 hits) | Rare; only 185 holdout cases |
  | B uncalibrated | **30%** | | | Actual time was a median 2× and a q80 5.9× B |
  | Setups with no pooled evidence | 0 of 687 reached their level | | | |

- **Calibration** (fit on eval_v4, tested on eval_v4_holdout; script `calibrate_runway_volatility.py`):

  | Timeframe | q80 multiplier | Held-out coverage |
  |---|---|---|
  | Daily | ×6.22 | 83% |
  | Weekly | ×6.00 | 86% |
  | Monthly | ×3.00 | 85% |

- **Config:** `runway_volatility_calibration` v1 records the multipliers, the panels, the coverage and the volatility proxy (ATR / close / 1.25).
- **Change:** `domain/anticipated_move.runway_fallback` applies the multiplier (basis `VOLATILITY_TIME_TO_LEVEL_CALIBRATED_Q80`). Timeframes without a multiplier get no B estimate.
- **Tests:** 8 pass (2 failed before the change), including the evidence-band test (coverage 70–90%) and the uncalibrated-timeframe test.
- **Frozen run:** volatility-based floors move from 13–19 to **21–56 days** (median 21). Pooled (24 rows) and no-estimate (626 rows) are unchanged.
- **Known limit:** the calibration used an ATR volatility proxy, while the runtime uses `sigma_daily_log_20`. Watch this with C12 forward data.
