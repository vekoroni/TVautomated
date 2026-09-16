# Decision-path field coverage — run 20260914_214012

Compared with: 20260913_143230, 20260911_115904

## Fields absent from every stage file

relative_strength_20d

## Constant / near-constant fields (latest run)

| Field | Stage | Distinct | Top value | Top share % | Constant in runs |
|---|---|---:|---|---:|---:|
| rr_underlying | 5_morning_candidates | 38 | 0.0 | 97.4 | 0/3 |
| quote_freshness | 6_lab | 3 | SESSION_ALIGNED | 95.5 | 1/3 |
| convexity_score | 3_options | 1 | 2.0 | 100.0 | 3/3 |
| convexity_score | 4_execution | 1 | 2.0 | 100.0 | 3/3 |
| convexity_campaign | 3_options | 1 | STAGED | 100.0 | 3/3 |
| convexity_campaign | 4_execution | 1 | STAGED | 100.0 | 3/3 |
| convexity_campaign | 5_morning_candidates | 1 | STAGED | 100.0 | 2/3 |
| convexity_campaign | 6_lab | 1 | STAGED | 100.0 | 3/3 |
| liquidity_friction_score | 2_vanguard | 1 | 32.0 | 100.0 | 3/3 |
| liquidity_friction_score | 4_execution | 1 | 32.0 | 100.0 | 3/3 |
| liquidity_friction_score | 5_morning_candidates | 1 | 32.0 | 100.0 | 2/3 |
| liquidity_friction_score | 6_lab | 1 | 32.0 | 100.0 | 3/3 |
| macro_conviction_score | 1_discovery | 1 | 63.0 | 100.0 | 3/3 |
| macro_conviction_score | 2_vanguard | 1 | 63.0 | 100.0 | 3/3 |
| macro_conviction_score | 3_options | 1 | 63.0 | 100.0 | 3/3 |
| macro_conviction_score | 4_execution | 1 | 63.0 | 100.0 | 3/3 |
| macro_conviction_score | 5_morning_candidates | 1 | 63.0 | 100.0 | 2/3 |
| sector_conviction_context | 3_options | 1 | 0.63 | 100.0 | 3/3 |
| sector_conviction_context | 4_execution | 1 | 0.63 | 100.0 | 3/3 |

## Vanguard physics inputs defaulted (% of rows)

{"avg_volume": 100.0, "beta": 100.0, "gap_pct": 100.0, "iv_rank": 100.0, "return_10d": 100.0, "return_5d": 100.0, "spread_pct_mid": 100.0}

## Per-field profile across stages (latest run)

| Segment | Field | Stage | Null % | Zero % | Distinct | Top value (share %) |
|---|---|---|---:|---:|---:|---|
| A_direction | discovery_direction_preliminary | 1_discovery | 0.0 | nan | 4 | CALL (59.6) |
| A_direction | discovery_direction_preliminary | 3_options | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | discovery_direction_preliminary | 4_execution | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | discovery_direction_preliminary | 5_morning_candidates | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | discovery_direction_preliminary | 6_lab | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | direction | 1_discovery | 0.0 | nan | 4 | CALL (59.6) |
| A_direction | direction | 5_morning_candidates | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | direction | 6_lab | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | governed_direction | 3_options | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | governed_direction | 4_execution | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | governed_direction | 5_morning_candidates | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | governed_direction | 6_lab | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | governed_direction_basis | 3_options | 0.0 | nan | 16 | precor_intent=BUY_SETUP (53.6) |
| A_direction | governed_direction_basis | 4_execution | 0.0 | nan | 16 | precor_intent=BUY_SETUP (53.6) |
| A_direction | governed_direction_basis | 5_morning_candidates | 0.0 | nan | 16 | precor_intent=BUY_SETUP (53.6) |
| A_direction | governed_direction_basis | 6_lab | 0.0 | nan | 16 | precor_intent=BUY_SETUP (53.6) |
| A_direction | direction_resolution_call_score | 3_options | 0.0 | 66.4 | 5 | 0.0 (66.4) |
| A_direction | direction_resolution_call_score | 4_execution | 0.0 | 66.4 | 5 | 0.0 (66.4) |
| A_direction | direction_resolution_call_score | 5_morning_candidates | 0.0 | 66.4 | 5 | 0.0 (66.4) |
| A_direction | direction_resolution_call_score | 6_lab | 0.0 | 66.4 | 5 | 0.0 (66.4) |
| A_direction | direction_resolution_put_score | 3_options | 0.0 | 17.5 | 4 | 1.0 (40.4) |
| A_direction | direction_resolution_put_score | 4_execution | 0.0 | 17.5 | 4 | 1.0 (40.4) |
| A_direction | direction_resolution_put_score | 5_morning_candidates | 0.0 | 17.5 | 4 | 1.0 (40.4) |
| A_direction | direction_resolution_put_score | 6_lab | 0.0 | 17.5 | 4 | 1.0 (40.4) |
| A_direction | direction_resolution_path | 3_options | 0.0 | nan | 2 | DIRECTION_CONFIRMED (91.0) |
| A_direction | direction_resolution_path | 4_execution | 0.0 | nan | 2 | DIRECTION_CONFIRMED (91.0) |
| A_direction | direction_resolution_path | 5_morning_candidates | 0.0 | nan | 2 | DIRECTION_CONFIRMED (91.0) |
| A_direction | direction_resolution_path | 6_lab | 0.0 | nan | 2 | DIRECTION_CONFIRMED (91.0) |
| A_direction | final_direction | 3_options | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | final_direction | 4_execution | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | final_direction | 5_morning_candidates | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | final_direction | 6_lab | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | canonical_direction | 3_options | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | canonical_direction | 4_execution | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | canonical_direction | 5_morning_candidates | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | canonical_direction | 6_lab | 0.0 | nan | 4 | CALL (63.6) |
| A_direction | vanguard_edge_direction | 4_execution | 50.9 | nan | 2 | PUT (80.0) |
| A_direction | layer2__edge_direction | 2_vanguard | 49.6 | nan | 2 | PUT (81.2) |
| A_direction | layer2__edge_direction | 3_options | 50.9 | nan | 2 | PUT (80.0) |
| A_direction | layer2__edge_direction | 4_execution | 50.9 | nan | 2 | PUT (80.0) |
| A_direction | directional_force | 2_vanguard | 0.0 | 0.0 | 4 | -15.0 (42.7) |
| A_direction | directional_force | 4_execution | 0.0 | 0.0 | 4 | -15.0 (42.1) |
| A_direction | directional_force | 5_morning_candidates | 0.0 | 0.0 | 4 | -15.0 (42.1) |
| A_direction | directional_force | 6_lab | 0.0 | 0.0 | 4 | -15.0 (42.1) |
| A_direction | catalyst_direction_bias | 1_discovery | 99.4 | nan | 2 | CALL (88.9) |
| A_direction | catalyst_direction_bias | 2_vanguard | 99.4 | nan | 2 | CALL (88.9) |
| A_direction | catalyst_direction_bias | 3_options | 99.4 | nan | 2 | CALL (88.9) |
| A_direction | catalyst_direction_bias | 4_execution | 99.4 | nan | 2 | CALL (88.9) |
| A_direction | catalyst_direction_bias | 5_morning_candidates | 99.4 | nan | 2 | CALL (88.9) |
| A_direction | catalyst_direction_bias | 6_lab | 99.4 | nan | 2 | CALL (88.9) |
| B_geometry | stock_price | 1_discovery | 0.0 | 0.0 | 1488 | 11.72 (0.2) |
| B_geometry | entry_spot | 3_options | 0.0 | 0.0 | 1368 | 11.72 (0.2) |
| B_geometry | entry_spot | 4_execution | 0.0 | 0.0 | 1368 | 11.72 (0.2) |
| B_geometry | signal_price | 5_morning_candidates | 0.0 | 0.0 | 1368 | 19.88 (0.2) |
| B_geometry | signal_price | 6_lab | 0.0 | 0.0 | 1368 | 13.6 (0.2) |
| B_geometry | underlying_price | 3_options | 0.0 | 0.0 | 1368 | 11.72 (0.2) |
| B_geometry | underlying_price | 4_execution | 0.0 | 0.0 | 1368 | 11.72 (0.2) |
| B_geometry | underlying_price | 6_lab | 0.0 | 0.0 | 1368 | 13.6 (0.2) |
| B_geometry | ATR_14 | 1_discovery | 0.0 | 0.0 | 598 | 1.22 (1.0) |
| B_geometry | structural_stop | 1_discovery | 0.0 | 0.0 | 1502 | 42.76 (0.2) |
| B_geometry | governed_invalidation_spot | 1_discovery | 24.8 | 0.0 | 1156 | 20.27 (0.2) |
| B_geometry | invalidation_spot | 3_options | 20.7 | 0.0 | 1121 | 33.4 (0.2) |
| B_geometry | invalidation_spot | 4_execution | 20.7 | 0.0 | 1121 | 33.4 (0.2) |
| B_geometry | invalidation_spot | 5_morning_candidates | 20.7 | 0.0 | 1121 | 17.65 (0.2) |
| B_geometry | invalidation_price | 6_lab | 20.7 | 0.0 | 1121 | 163.04 (0.2) |
| B_geometry | exit_invalidation_price | 5_morning_candidates | 0.0 | 20.7 | 1108 | 0.0 (20.7) |
| B_geometry | structural_target | 1_discovery | 95.0 | 0.0 | 79 | 53.91 (1.3) |
| B_geometry | structural_target | 3_options | 21.1 | 0.0 | 1139 | 24.21 (0.2) |
| B_geometry | structural_target | 4_execution | 21.1 | 0.0 | 1139 | 24.21 (0.2) |
| B_geometry | structural_target | 6_lab | 18.8 | 0.0 | 1172 | 27.789999999999992 (0.2) |
| B_geometry | target_spot | 3_options | 20.7 | 0.0 | 1145 | 24.21 (0.2) |
| B_geometry | target_spot | 4_execution | 20.7 | 0.0 | 1145 | 24.21 (0.2) |
| B_geometry | target_price | 5_morning_candidates | 23.5 | 0.0 | 1105 | 91.37000000000003 (0.2) |
| B_geometry | target_price | 6_lab | 23.5 | 0.0 | 1105 | 27.789999999999992 (0.2) |
| B_geometry | trigger_price | 6_lab | 20.8 | 0.0 | 211 | 40.2 (3.4) |
| B_geometry | rr_underlying | 1_discovery | 97.1 | 0.0 | 45 | 0.59 (2.2) |
| B_geometry | rr_underlying | 5_morning_candidates | 0.0 | 97.4 | 38 | 0.0 (97.4) |
| B_geometry | expected_move_pct | 3_options | 9.5 | 0.0 | 1306 | 17.04 (0.2) |
| B_geometry | expected_move_pct | 4_execution | 9.5 | 0.0 | 1306 | 17.04 (0.2) |
| B_geometry | garch_expected_move_11_20d | 6_lab | 0.0 | 0.0 | 573 | 2.88 (0.7) |
| B_geometry | planned_hold_sessions | 3_options | 9.0 | 0.0 | 2 | 10.0 (76.9) |
| B_geometry | planned_hold_sessions | 4_execution | 9.0 | 0.0 | 2 | 10.0 (76.9) |
| B_geometry | planned_hold_sessions | 5_morning_candidates | 9.0 | 0.0 | 2 | 10.0 (76.9) |
| C_contract | contract_symbol | 5_morning_candidates | 9.5 | nan | 1312 | HIMS261002C00030000 (0.1) |
| C_contract | contract_symbol | 6_lab | 9.5 | nan | 1312 | HRB261016C00045000 (0.1) |
| C_contract | strike | 1_discovery | 100.0 | nan | 0 |  (nan) |
| C_contract | strike | 3_options | 9.5 | 0.0 | 236 | 35.0 (3.5) |
| C_contract | strike | 4_execution | 9.5 | 0.0 | 236 | 35.0 (3.5) |
| C_contract | strike | 5_morning_candidates | 0.0 | 9.5 | 237 | 0.0 (9.5) |
| C_contract | strike | 6_lab | 9.5 | 0.0 | 236 | 35.0 (3.5) |
| C_contract | contract_strike | 3_options | 9.5 | 0.0 | 236 | 35.0 (3.5) |
| C_contract | contract_strike | 4_execution | 9.5 | 0.0 | 236 | 35.0 (3.5) |
| C_contract | expiry | 1_discovery | 100.0 | nan | 0 |  (nan) |
| C_contract | expiry | 3_options | 9.5 | nan | 5 | 2026-10-16 (75.7) |
| C_contract | expiry | 4_execution | 9.5 | nan | 5 | 2026-10-16 (75.7) |
| C_contract | expiry | 5_morning_candidates | 9.5 | nan | 5 | 2026-10-16 (75.7) |
| C_contract | expiry | 6_lab | 9.5 | nan | 5 | 2026-10-16 (75.7) |
| C_contract | dte | 1_discovery | 0.0 | 0.0 | 5 | 38 (54.4) |
| C_contract | dte | 3_options | 9.5 | 0.0 | 5 | 32.0 (75.7) |
| C_contract | dte | 4_execution | 9.5 | 0.0 | 5 | 32.0 (75.7) |
| C_contract | dte | 5_morning_candidates | 0.0 | 0.0 | 6 | 32.0 (68.5) |
| C_contract | dte | 6_lab | 9.5 | 0.0 | 5 | 32.0 (75.7) |
| C_contract | contract_dte | 3_options | 9.5 | 0.0 | 5 | 32.0 (75.7) |
| C_contract | contract_dte | 4_execution | 9.5 | 0.0 | 5 | 32.0 (75.7) |
| C_contract | contract_dte | 5_morning_candidates | 9.5 | 0.0 | 5 | 24.0 (75.7) |
| C_contract | contract_dte | 6_lab | 9.5 | 0.0 | 5 | 24.0 (75.7) |
| C_contract | minimum_required_dte | 3_options | 23.5 | 0.0 | 2 | 13.0 (68.1) |
| C_contract | minimum_required_dte | 4_execution | 23.5 | 0.0 | 2 | 13.0 (68.1) |
| C_contract | minimum_required_dte | 5_morning_candidates | 23.5 | 0.0 | 2 | 13.0 (68.1) |
| C_contract | minimum_required_dte | 6_lab | 23.5 | 0.0 | 2 | 13.0 (68.1) |
| C_contract | delta_band | 3_options | 23.5 | nan | 5 | NEAR_ATM_035_060 (88.9) |
| C_contract | delta_band | 4_execution | 23.5 | nan | 5 | NEAR_ATM_035_060 (88.9) |
| C_contract | delta_band | 5_morning_candidates | 23.5 | nan | 5 | NEAR_ATM_035_060 (88.9) |
| C_contract | delta_band | 6_lab | 23.5 | nan | 5 | NEAR_ATM_035_060 (88.9) |
| C_contract | contract_delta | 3_options | 9.5 | 0.1 | 1312 | -0.4666671306221862 (0.1) |
| C_contract | contract_delta | 4_execution | 9.5 | 0.1 | 1312 | -0.4666671306221862 (0.1) |
| C_contract | contract_delta | 5_morning_candidates | 0.0 | 9.5 | 1312 | 0.0 (9.5) |
| C_contract | contract_delta | 6_lab | 9.5 | 0.1 | 1312 | 0.5940055851656791 (0.1) |
| C_contract | contract_iv | 3_options | 9.5 | 0.0 | 1203 | 0.6271 (0.2) |
| C_contract | contract_iv | 4_execution | 9.5 | 0.0 | 1203 | 0.6271 (0.2) |
| C_contract | contract_iv | 5_morning_candidates | 0.0 | 9.5 | 1204 | 0.0 (9.5) |
| C_contract | contract_iv | 6_lab | 9.5 | 0.0 | 1203 | 0.2607 (0.2) |
| C_contract | iv_rank | 1_discovery | 100.0 | nan | 0 |  (nan) |
| C_contract | iv_rank | 2_vanguard | 100.0 | nan | 0 |  (nan) |
| C_contract | iv_rank | 3_options | 9.2 | 0.3 | 546 | 100.0 (29.2) |
| C_contract | iv_rank | 4_execution | 9.2 | 0.3 | 546 | 100.0 (29.2) |
| C_contract | iv_rank | 5_morning_candidates | 9.2 | 0.3 | 546 | 100.0 (29.2) |
| C_contract | iv_rank | 6_lab | 9.2 | 0.3 | 546 | 100.0 (29.2) |
| C_contract | ivp_label | 3_options | 9.2 | nan | 3 | EXPENSIVE (59.3) |
| C_contract | ivp_label | 4_execution | 9.2 | nan | 3 | EXPENSIVE (59.3) |
| C_contract | ivp_label | 6_lab | 9.2 | nan | 3 | EXPENSIVE (59.3) |
| C_contract | contract_bid | 3_options | 9.5 | 3.7 | 284 | 0.0 (4.1) |
| C_contract | contract_bid | 4_execution | 9.5 | 3.7 | 284 | 0.0 (4.1) |
| C_contract | contract_bid | 5_morning_candidates | 9.5 | 3.7 | 284 | 0.0 (4.1) |
| C_contract | contract_bid | 6_lab | 9.5 | 3.7 | 284 | 0.0 (4.1) |
| C_contract | contract_ask | 3_options | 9.5 | 0.0 | 300 | 3.7 (2.0) |
| C_contract | contract_ask | 4_execution | 9.5 | 0.0 | 300 | 3.7 (2.0) |
| C_contract | contract_ask | 5_morning_candidates | 0.0 | 9.5 | 301 | 0.0 (9.5) |
| C_contract | contract_ask | 6_lab | 9.5 | 0.0 | 300 | 3.7 (2.0) |
| C_contract | contract_mid | 3_options | 9.5 | 0.0 | 504 | 1.25 (1.3) |
| C_contract | contract_mid | 4_execution | 9.5 | 0.0 | 504 | 1.25 (1.3) |
| C_contract | contract_mid | 5_morning_candidates | 0.0 | 9.5 | 505 | 0.0 (9.5) |
| C_contract | contract_mid | 6_lab | 9.5 | 0.0 | 504 | 1.25 (1.3) |
| C_contract | contract_spread_pct | 3_options | 9.5 | 0.0 | 850 | 2.0 (4.1) |
| C_contract | contract_spread_pct | 4_execution | 9.5 | 0.0 | 850 | 2.0 (4.1) |
| C_contract | contract_spread_pct | 5_morning_candidates | 0.0 | 9.5 | 851 | 0.0 (9.5) |
| C_contract | spread_fraction_mid | 6_lab | 9.5 | 0.0 | 850 | 2.0 (4.1) |
| C_contract | quote_freshness | 3_options | 9.2 | nan | 4 | SESSION_ALIGNED (80.8) |
| C_contract | quote_freshness | 4_execution | 9.2 | nan | 4 | SESSION_ALIGNED (80.8) |
| C_contract | quote_freshness | 5_morning_candidates | 9.2 | nan | 4 | SESSION_ALIGNED (80.8) |
| C_contract | quote_freshness | 6_lab | 23.2 | nan | 3 | SESSION_ALIGNED (95.5) |
| C_contract | contract_repair_status | 3_options | 0.0 | nan | 2 | CONTRACT_REPAIR_REQUIRED (77.9) |
| C_contract | contract_repair_status | 4_execution | 0.0 | nan | 2 | CONTRACT_REPAIR_REQUIRED (77.9) |
| C_contract | contract_repair_status | 5_morning_candidates | 0.0 | nan | 3 | CONTRACT_REPAIR_REQUIRED (87.9) |
| C_contract | contract_repair_status | 6_lab | 0.0 | nan | 3 | CONTRACT_REPAIR_REQUIRED (87.9) |
| C_contract | heston_fit_error | 3_options | 100.0 | nan | 0 |  (nan) |
| C_contract | heston_fit_error | 4_execution | 100.0 | nan | 0 |  (nan) |
| D_economics | breakeven_price | 3_options | 23.5 | 0.0 | 1016 | 10.8 (0.5) |
| D_economics | breakeven_price | 4_execution | 23.5 | 0.0 | 1016 | 10.8 (0.5) |
| D_economics | breakeven_price | 6_lab | 23.5 | 0.0 | 1016 | 10.8 (0.5) |
| D_economics | rr_options | 3_options | 23.5 | 0.1 | 1040 | -1.0 (2.2) |
| D_economics | rr_options | 4_execution | 23.5 | 0.1 | 1040 | -1.0 (2.2) |
| D_economics | monetisability_state | 5_morning_candidates | 0.0 | nan | 4 | MONETISABLE (61.1) |
| D_economics | monetisability_state | 6_lab | 0.0 | nan | 4 | MONETISABLE (61.1) |
| D_economics | monetisability_target_profit_pct | 5_morning_candidates | 23.5 | 0.0 | 1077 | -100.0 (2.2) |
| D_economics | monetisability_target_profit_pct | 6_lab | 23.5 | 0.0 | 1077 | -100.0 (2.2) |
| D_economics | ev3_status | 3_options | 0.0 | nan | 3 | REJECTED (73.6) |
| D_economics | ev3_status | 4_execution | 0.0 | nan | 3 | REJECTED (73.6) |
| D_economics | ev3_status | 5_morning_candidates | 0.0 | nan | 3 | REJECTED (73.6) |
| D_economics | ev3_status | 6_lab | 0.0 | nan | 3 | REJECTED (73.6) |
| D_economics | ev3_p_target | 3_options | 83.1 | 0.0 | 174 | 0.0478556558751329 (2.0) |
| D_economics | ev3_p_target | 4_execution | 83.1 | 0.0 | 174 | 0.0478556558751329 (2.0) |
| D_economics | ev3_p_target | 5_morning_candidates | 83.1 | 0.0 | 174 | 0.0478556558751329 (2.0) |
| D_economics | ev3_p_target | 6_lab | 83.1 | 0.0 | 174 | 0.0478556558751329 (2.0) |
| D_economics | win_probability | 1_discovery | 0.0 | 0.0 | 61 | 51.0 (22.9) |
| D_economics | win_probability | 3_options | 9.5 | 0.0 | 60 | 51.0 (24.7) |
| D_economics | win_probability | 4_execution | 9.5 | 0.0 | 60 | 51.0 (24.7) |
| D_economics | win_prob_predicted | 6_lab | 0.0 | 0.0 | 33 | 0.4989840262225056 (15.0) |
| D_economics | layer2__raw_prob_target_hit | 2_vanguard | 0.0 | 0.0 | 158 | 0.3466624435822313 (7.4) |
| D_economics | layer2__raw_prob_target_hit | 3_options | 0.0 | 0.0 | 157 | 0.3466624435822313 (7.0) |
| D_economics | layer2__raw_prob_target_hit | 4_execution | 0.0 | 0.0 | 157 | 0.3466624435822313 (7.0) |
| D_economics | layer2__raw_prob_target_hit | 5_morning_candidates | 0.0 | 0.0 | 157 | 0.3466624435822313 (7.0) |
| D_economics | layer2__raw_prob_target_hit | 6_lab | 0.0 | 0.0 | 157 | 0.3466624435822313 (7.0) |
| E_scores | composite_score | 1_discovery | 0.0 | 0.0 | 96 | 44.0 (22.9) |
| E_scores | composite_score | 6_lab | 0.0 | 0.0 | 90 | 44.0 (24.2) |
| E_scores | options_score | 3_options | 0.0 | 23.5 | 67 | 0.0 (23.5) |
| E_scores | options_score | 4_execution | 0.0 | 23.5 | 67 | 0.0 (23.5) |
| E_scores | options_score | 5_morning_candidates | 0.0 | 23.5 | 67 | 0.0 (23.5) |
| E_scores | options_score | 6_lab | 0.0 | 23.5 | 67 | 0.0 (23.5) |
| E_scores | convexity_score | 3_options | 9.5 | 0.0 | 1 | 2.0 (100.0) |
| E_scores | convexity_score | 4_execution | 9.5 | 0.0 | 1 | 2.0 (100.0) |
| E_scores | convexity_score | 5_morning_candidates | 0.0 | 9.5 | 2 | 2.0 (90.5) |
| E_scores | convexity_score | 6_lab | 0.0 | 9.5 | 2 | 2.0 (90.5) |
| E_scores | convexity_campaign | 3_options | 9.5 | nan | 1 | STAGED (100.0) |
| E_scores | convexity_campaign | 4_execution | 9.5 | nan | 1 | STAGED (100.0) |
| E_scores | convexity_campaign | 5_morning_candidates | 9.5 | nan | 1 | STAGED (100.0) |
| E_scores | convexity_campaign | 6_lab | 9.5 | nan | 1 | STAGED (100.0) |
| E_scores | campaign_verdict | 4_execution | 0.0 | nan | 2 | REJECT (82.5) |
| E_scores | campaign_verdict | 6_lab | 0.0 | nan | 2 | STAGED (90.5) |
| E_scores | liquidity_friction_score | 2_vanguard | 0.0 | 0.0 | 1 | 32.0 (100.0) |
| E_scores | liquidity_friction_score | 4_execution | 0.0 | 0.0 | 1 | 32.0 (100.0) |
| E_scores | liquidity_friction_score | 5_morning_candidates | 0.0 | 0.0 | 1 | 32.0 (100.0) |
| E_scores | liquidity_friction_score | 6_lab | 0.0 | 0.0 | 1 | 32.0 (100.0) |
| E_scores | macro_conviction_score | 1_discovery | 0.0 | 0.0 | 1 | 63.0 (100.0) |
| E_scores | macro_conviction_score | 2_vanguard | 0.0 | 0.0 | 1 | 63.0 (100.0) |
| E_scores | macro_conviction_score | 3_options | 0.0 | 0.0 | 1 | 63.0 (100.0) |
| E_scores | macro_conviction_score | 4_execution | 0.0 | 0.0 | 1 | 63.0 (100.0) |
| E_scores | macro_conviction_score | 5_morning_candidates | 0.0 | 0.0 | 1 | 63.0 (100.0) |
| E_scores | sector_conviction_context | 3_options | 0.0 | 0.0 | 1 | 0.63 (100.0) |
| E_scores | sector_conviction_context | 4_execution | 0.0 | 0.0 | 1 | 0.63 (100.0) |
| E_scores | market_energy_score | 2_vanguard | 0.0 | 0.0 | 1519 | 43.4473 (0.1) |
| E_scores | market_energy_score | 4_execution | 0.0 | 0.0 | 1440 | 51.2911 (0.1) |
| E_scores | market_energy_score | 5_morning_candidates | 0.0 | 0.0 | 1440 | 35.4171 (0.1) |
| E_scores | market_energy_score | 6_lab | 0.0 | 0.0 | 1440 | 45.1058 (0.1) |
| E_scores | force_alignment_score | 2_vanguard | 0.0 | 0.0 | 4 | 100.0 (61.8) |
| E_scores | force_alignment_score | 4_execution | 0.0 | 0.0 | 4 | 100.0 (61.7) |
| E_scores | force_alignment_score | 5_morning_candidates | 0.0 | 0.0 | 4 | 100.0 (61.7) |
| E_scores | force_alignment_score | 6_lab | 0.0 | 0.0 | 4 | 100.0 (61.7) |
| E_scores | priority_score | 6_lab | 0.0 | 9.2 | 1119 | 0.0 (9.2) |
| F_verdict | tier | 1_discovery | 0.0 | 38.2 | 4 | 0 (38.2) |
| F_verdict | tier | 3_options | 0.0 | 40.4 | 3 | 0 (40.4) |
| F_verdict | tier | 4_execution | 0.0 | 40.4 | 3 | 0 (40.4) |
| F_verdict | tier | 6_lab | 0.0 | nan | 4 | C (40.9) |
| F_verdict | opportunity_tier | 6_lab | 0.0 | nan | 4 | BLOCK (72.0) |
| F_verdict | eil_signal_verdict | 4_execution | 0.0 | nan | 5 | BLOCKED (73.3) |
| F_verdict | eil_signal_verdict | 5_morning_candidates | 0.0 | nan | 5 | BLOCKED (73.3) |
| F_verdict | eil_signal_verdict | 6_lab | 0.0 | nan | 5 | BLOCKED (73.3) |
| F_verdict | eod_candidate_status | 5_morning_candidates | 0.0 | nan | 3 | EOD_THESIS_READY_REPAIR_AT_OPEN (68.8) |
| F_verdict | eod_candidate_status | 6_lab | 0.0 | nan | 3 | EOD_THESIS_READY_REPAIR_AT_OPEN (68.8) |
| F_verdict | lab_status | 6_lab | 0.0 | nan | 3 | MANUAL_REVIEW (88.1) |
| F_verdict | lab_verdict | 6_lab | 0.0 | nan | 3 | MANUAL_REVIEW (88.1) |
| F_verdict | priority_rank | 6_lab | 0.0 | 0.0 | 1449 | 1 (0.1) |