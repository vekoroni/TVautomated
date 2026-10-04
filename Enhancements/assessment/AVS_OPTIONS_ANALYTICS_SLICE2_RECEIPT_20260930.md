# AVS options analytics framework — EV v2 out of ranking + slice 2 receipt (30 Sep 2026)

Approval: ACK, 30 Sep 2026: "approved, remove EV v2 from priority score and start slice 2". Plan:
`Enhancements/decision_map/AVS_OPTIONS_ANALYTICS_FRAMEWORK_BUILD_PLAN_20260930.md`. Status: **TESTED_UNCOMMITTED**
(commit only when ACK asks).

## A. Legacy EV v2 removed from the Lab ranking and the journal

| Change | Where | Test (failing first) |
|---|---|---|
| Priority score no longer uses `ev2_ev_conf_adj` (was 10 %); the remaining weights (0.90) are scaled by 1/0.90, so a row maxing every dimension still scores 100 and the relative order of weights is unchanged | `intelligence-lab/intelligence_lab.py` `_compute_priority_score` (`_PRIORITY_WEIGHT_TOTAL`) | `tests/test_lab_priority_and_journal_ev_no_legacy.py` (3) |
| Journal entries record the book's EV3 advisory value (`ev_predicted`, set only when EV3 valued the selected contract) or none — the trade-entry call had been passing EV v2 under the name `ev_predicted` | same file, new `_journal_ev`, both journal writers | same file (4) |
| The Vanguard trade contract accepts a missing entry EV (null, never 0) | `vanguard/trade_contract.py` `create_contract` | same file (1) |

Ranking effect: rows' research priority scores change because the EV v2 term (which could add up to 10 points) is
gone and the rest is rescaled; this reorders the Lab's default view. The approval covered this.

Not changed (outside the approval): the `/api` filter `ev_min` and the sector summary's `avg_ev` (no longer displayed)
still read EV v2; EIL and superbrain still compute it; the DATA WEAK badge reads the EV v2 status.

## B. Slice 2 — the contract analytics block

One pure function, `contracts/selected_contract_economics.contract_analytics` (fields `CONTRACT_ANALYTICS_FIELDS`,
version `avs-contract-analytics-v1`), display only:

- intrinsic value at the current spot; mid; extrinsic at the mid and at the ask, and its share of the premium;
- expiry breakeven at the ask (call K + ask, put K − ask) and the signed stock move to it;
- maximum loss per position = ask × 100 × contracts; delta exposure (shares) and dollar delta;
- theta in USD per position per calendar day; vega in USD per position per IV point;
- spread % of mid via the canonical `quote_spread_fraction`;
- market-implied move = IV × √(days/365) to expiry and over the planned hold (sessions × 7/5), with the IV source;
- state COMPLETE / PARTIAL (missing inputs named in `ca_missing_fields`, only dependent figures blank) /
  NOT_APPLICABLE (no direction, non-positive spot or strike).

Wiring:
- **Evening:** `scripts/avshunter_options_intelligence.py` `evening_contract_analytics` on the selected contract;
  a synthetic mark's bid/ask are treated as missing (never priced from a fabricated quote); hold = governed thesis
  window.
- **Candidate book:** `eod_candidate_engine.py` passes `contract_greeks_source` and the block through, and clears
  them when a contract is voided for the wrong direction.
- **Morning:** `morning_gate._recompute_selected_contract_economics` clears the Evening block and recomputes it for
  the contract actually quoted (LONG_SINGLE; live price; hydrated leg; planned hold; IV source PROVIDER_MORNING_QUOTE).
- **Lab:** the book carries the block under the quote-ownership gate; the signal modal shows it after the Greeks via
  `contractAnalyticsRows` (formats published fields only; missing = dash).

Tests: `tests/test_contract_analytics_slice2.py` (13: worked call and put examples, OTM, contract scaling, missing
inputs, not-applicable, Evening real and synthetic quote, Morning recompute and failed-hydration clearing, book,
candidate passthrough, voided contract) and `tests/js/test_fix13_contract_analytics_display.js`.

## Regression

30 Sep 2026: every test file importing `morning_gate`, `lab_control`, `ev_engine_v3`, `ev3_stage0`, `run_ev3_shadow`,
`apply_ev3_authority`, `intelligence_lab`, `eod_candidate_engine`, `selected_contract_economics`,
`avshunter_options_intelligence`, `trade_contract` or reading the Lab page / sector patch — 152 files, one per
process. Checked for failures explicitly (an earlier summary filter hid them; see the corrections in the slice 1 and
28 Sep receipts). Result after two test updates: **2 failing tests, both from the uncommitted TEV-001 work**:

- `tests/test_avs_int001_stage0.py::test_named_production_imports_are_in_the_git_index` — production imports three
  untracked TEV-001 modules (`contracts/descriptive_forecast_packet.py`, `expression_candidate_packet.py`,
  `expression_valuation_packet.py`); the TEV-001 build plan's P0 item.
- `tests/test_ila_selected_contract_identity.py::test_fix_adds_only_the_two_identity_fields` — 15 TEV-001
  forecast/research-EV book fields not yet listed as approved additions (left to that work's owner).

Updated for this build: `tests/test_layer3_volatility_integrity.py` (the half-weight of a measured neutral tailwind is
now 2.5/0.90 points after the approved rescale; the missing-earns-nothing rule unchanged) and
`tests/test_ila_selected_contract_identity.py` (the 28 Sep EV3 move-window fields and the slice 1e/2 fields listed as
approved additive book fields). Every other file passes.
