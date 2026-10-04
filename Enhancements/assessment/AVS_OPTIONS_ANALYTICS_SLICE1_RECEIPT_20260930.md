# AVS options analytics framework — slice 1 receipt (30 Sep 2026)

Approval: ACK, 30 Sep 2026: "approved, retire EV v2 and start slice 1". Plan:
`Enhancements/decision_map/AVS_OPTIONS_ANALYTICS_FRAMEWORK_BUILD_PLAN_20260930.md`. Status: **TESTED_UNCOMMITTED**
(commit only when ACK asks). Display and measurement only; no gate, rank or permission changed.

| # | Defect | Change | Test (failing first) |
|---|---|---|---|
| 1a | `vega_risk_pct` 100× too small: a per-share 10-point loss divided by the per-contract premium (provider and Heston vega are both per IV point) | `scripts/avshunter_options_intelligence.py` `compute_trade_economics`: loss per contract = vega × 10 × 100 (MTDR: 0.14 % → 14.33 %) | `tests/test_options_analytics_slice1.py` (3) |
| 1b | Convexity strike map "too late" check: every PUT used the call wall, ignoring its recorded stop and invalidation (operator precedence) | same file `build_convexity_strike_map`: CALL order unchanged; PUT = stop_loss → invalidation → call wall (structural support is on the wrong side of a put) | same file (4, incl. CALL characterisation) |
| 1c | Lab printed "+" before every breakeven %, so a put needing a 4 % fall read "+4 %" | `index.html` `frozenBreakevenLabel`: signed stock move (calls +, puts −; a passed breakeven flips; missing = dash; a real 0 kept) | `tests/js/test_fix11_breakeven_sign.js` |
| 1d | Legacy EV v2 (not an expected value; wrong for puts; IV sign inverted) shown in the Lab as a fallback EV, hint badges, Q-score, export columns, journal note, sector average; the book's `ev_predicted` fell back to it; LEGACY_EV_* advisory flags | Lab shows EV3 advisory only; legacy hint/Q-score badges, `EV_Decision`/`EV_Quality` export columns, journal-note EV and sector "Legacy EV" average removed; book `ev_predicted` from EV3 only; LEGACY_EV_* flags no longer raised | `tests/js/test_fix12_legacy_ev_retired.js`; `tests/test_lab_legacy_ev_retired.py`; pinned legacy assertions updated in `tests/test_big_bang_phase_6_7.py`, `tests/test_lab_governed_handoff.py`, `tests/js/test_fix4_ev_precision.js` |
| 1e | Provider Greeks replaced by Heston/BSM Greeks at the ATM variance with no provenance | `contract_greeks_source` (PROVIDER_EOD_CHAIN / HESTON_ATM_VARIANCE_MODEL / PROVIDER_MORNING_QUOTE / UNAVAILABLE) published by Options Intelligence and the Morning, carried by the book under the quote-ownership gate, shown in the signal modal | `tests/test_options_analytics_slice1.py` (7) |

**Notes.**
- 1d, book: the committed book builder already blanked a legacy-only `ev_predicted` through the contract-alignment
  rule, so the book change removes a dead fallback; the live leak was the Lab page, which fell back to the server's
  legacy fields (FIX-12 failed on the old page).
- 1d, not changed (outside "display"; needs ACK): EV v2 remains 10 % of the Lab's research priority score
  (`intelligence-lab/intelligence_lab.py` `_compute_priority_score`), the server still fills `ev`/`ev_final`/`ev_net`
  from it, the sector summary still computes `avg_ev` from it (no longer displayed), an API filter `ev_min` reads it,
  and the journal's `ev` field on trade entry is filled from it. EIL and superbrain still compute it. The DATA WEAK
  badge reads the EV v2 status (it describes missing actuarial data, not an EV).
- 1a changes a displayed number only; nothing gates or scores on `vega_risk_pct`.
- 1b changes when a PUT is labelled TOO_LATE by the convexity strike map (CSM verdict, advisory).

## Regression

30 Sep 2026: every test file importing `morning_gate`, `lab_control`, `ev_engine_v3`, `ev3_stage0`, `run_ev3_shadow`,
`apply_ev3_authority`, `intelligence_lab`, `eod_candidate_engine`, `selected_contract_economics`,
`avshunter_options_intelligence` or reading the Lab page / sector patch — 150 files, one per process — **1,505 passed,
0 failed** (one file skips by design). The Lab JS harness (incl. FIX-10, FIX-11, FIX-12) runs inside it.
Browser check (Lab restarted on port 5002, run 20260927_205123): 1,550 rows render; no legacy EV text anywhere; a put's
breakeven reads "$61.5 (−4.61% stock move)"; the Greeks-source row shows a dash on this stored run (field added after
it was produced); no console errors.

**Correction (30 Sep 2026).** The regression summary above was produced with a filter that hid any file reporting failures alongside passes (`1 failed, 5 passed` contains `passed`). The underlying results were overwritten, so the exact counts cannot be re-read. Re-run with a corrected check on 30 Sep: `tests/test_avs_int001_stage0.py` fails because production code imports three untracked TEV-001 modules (pre-existing, other uncommitted work), and `tests/test_ila_selected_contract_identity.py` failed on the EV3 move-window book fields added 28 Sep (fixed 30 Sep by listing them as approved additive fields); it still fails on 15 TEV-001 forecast/research-EV fields that belong to that work.
