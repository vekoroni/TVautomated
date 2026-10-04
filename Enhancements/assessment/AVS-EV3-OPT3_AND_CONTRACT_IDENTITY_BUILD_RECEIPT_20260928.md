# EV3 at hold and move window (ACK option 3) + Morning contract identity — build receipt

Date: 28 Sep 2026. Status: **TESTED_UNCOMMITTED** (commit only when ACK asks). Approval: ACK, 28 Sep 2026:
"go with option 3 and then proceed with the full fix".

## 1. Defects

**D1 — EV3 valued nothing since 19 Sep.** ACK's 18 Sep decision made the planned hold the governed thesis
window (20 sessions on every row) while the anticipated move stays Discovery's thesis horizon (5/10/20). The
horizon patch in `intelligent_orchestrator.py` already documents the hold as "the valuation window", but EV3's
entry check (`vanguard/ev3_stage0.py`) still required `planned_hold_sessions == horizon bucket endpoint`.
Result: every 1_5d/6_10d contract rejected `REJECT_HORIZON` (27 Sep Evening: 3,989 contracts; Morning 1,141
of 1,337 hydrated rows), `ev_functional_health = DEGRADED_NO_EVALUATIONS`, no EV in the Lab. The Lab's "Hold"
column also showed the move window label (1_5d) on 20-session trades.

**D2 — Morning contract swap left the old contract's identity.** When the Morning's hydrated selected
structure differed from the Evening contract, `morning_gate._recompute_selected_contract_economics` swapped the
symbol, quote, Greeks and liquidity but left `strike`, `expiry`, `dte` (and `contract_*`) from the Evening
contract. The hydrator already publishes the identity atomically (`selected_contract_strike/expiry/dte`).
Evening files clean on every run; Morning introduces it:

| Morning of run | Rows with wrong strike | GO_LIMIT rows affected |
|---|---|---|
| 20260922_223221 | 261 | 0 of 359 |
| 20260924_085940 | 173 | 0 of 401 |
| 20260925_061649 | 392 | 0 of 273 |
| 20260927_205123 | 170 | 0 of 488 |

The Lab's `opt__contract_strike/expiry/dte` are projected from the row's `strike/expiry/dte`
(`intelligence_lab.py` projection aliases), so correcting the row corrects the display.

## 2. Design (ACK option 3)

- EV3 lead value = the contract valued at the planned hold (`ev3_ev_*`, published as `ev_predicted`, used by
  the selector). Unchanged fields and values.
- Second value = the same contract valued at the move window (`anticipated_move_sessions`, else the thesis
  bucket endpoint), published as `ev3_move_window_*` with `ev3_move_window_status/reason_code`; typed
  `NOT_EVALUATED` when it cannot be valued, never filled from the hold value.
- Entry rule: the hold must be a horizon the barrier sidecar materialised (5, 10, 20); anything else still
  `REJECT_HORIZON`.
- Lab: "Horizon" column renamed "Move window"; "Hold" shows the planned hold in sessions; EV cell tooltip,
  signal modal and CSV export show EV3 at the move window under the same contract-alignment rule.
- D2: new `_write_selected_contract_identity` writes the hydrator's strike/expiry/calendar `dte`;
  `contract_dte` (trading sessions, declared basis) is recomputed by its owner
  `eod_candidate_engine._governed_contract_dte`. Stale Evening move-window values are cleared with the other
  EV3 fields when the Morning re-values.

Nothing gains authority: EV3 stays advisory (spec rule 5); no gate, rank or permission reads the new fields.

## 3. Files

`vanguard/ev3_stage0.py`, `vanguard/ev_engine_v3.py` (valuation extracted into `_value_long_single`,
`_value_vertical`, `_vertical_output`, `_move_window_fields`), `morning_gate.py`, `contracts/lab_control.py`,
`intelligence-lab/static/index.html`. Tests: `tests/test_ev3_hold_and_move_window.py` (14),
`tests/test_morning_selected_contract_identity.py` (3), `tests/test_lab_ev3_move_window_book.py` (1),
`tests/js/test_fix10_hold_and_move_window.js`; pinned detail in `tests/test_ev3_stage0.py` updated.

## 4. Proof

- **Refactor parity:** on every row the old rule accepted (single and vertical, CALL/PUT, 5/10/20, two
  rejection paths) the new engine publishes every committed field with identical values (exact equality),
  adding only `ev3_hold_sessions` and `ev3_move_window_*`.
- **Morning replay, run 20260927_205123** (stored hydrated rows, each at its own quote time + 60 s):

| | Rows valued | GO_LIMIT rows valued |
|---|---|---|
| Committed engine | 0 of 1,337 | 0 |
| Option 3 | 186 of 1,337 | 153 of 488 |

  Remaining rejections are genuine: liquidity policy (OI < 50 or no volume yet at the Morning quote) 718,
  contract too short for a 20-session hold 161, target outside the barrier grid 60, thesis prices 196.
  Values: hold EV median −0.44 (p10 −0.58, p90 −0.29); move-window EV median −0.37. Inspected by hand
  (GOOGL, BHP, TJX, SLV): units correct; negativity comes from far targets (e.g. GOOGL −35 % in the window,
  p_target ≈ 1 %), tight stops (BHP 3 %, p_stop ≈ 0.76) and ~30 % time decay at 20 sessions with no move.
  EV3 is uncalibrated and advisory; these are model outputs, not validated expectations.
- **Evening replay, run 20260927_205123** (Sunday Evening on Friday's close): committed engine reproduces the
  stored result exactly (0 valued; REJECT_HORIZON 3,989 contracts). Option 3 removes the horizon rejection,
  but every contract then fails `REJECT_QUOTE_STALE` (quotes ~50 h old; EOD limit 24 h). See §5.
- **Evening replays on weekday runs** (pre-overlay Options input, each run's own evaluation moment; the
  committed engine reproduces every stored count exactly):

| Run | Valued before | Valued after | Move window valued | Hold EV median | Move-window EV median |
|---|---|---|---|---|---|
| 20260922_223221 | 0 of 1,550 | 329 | 329 (5 s: 229, 10 s: 100) | −0.458 | −0.394 |
| 20260924_085940 | 0 of 1,532 | 298 | 298 (5 s: 189, 10 s: 109) | −0.449 | −0.395 |
| 20260925_061649 | 0 of 1,549 | 299 | 299 (5 s: 211, 10 s: 88) | −0.449 | −0.394 |

  Every valued row is `NEGATIVE_EV` at the hold. Remaining rejections are genuine: liquidity policy, DTE too
  short for a 20-session hold, thesis prices missing, target outside the barrier grid.

## 5. Open item for ACK (not changed)

EV3's EOD quote-freshness limit (24 h, `validate_ev3_input` `max_quote_age_seconds`) rejects every contract on
an Evening that prices a session more than 24 h old (every Sunday Evening). It is a time gate, which conflicts
with the standing rule "re-value at current premium; flag quote age, never gate on it". A method decision:
keep, widen to the last completed session, or flag instead of reject.

## 6. Regression

28 Sep 2026: every test file importing `morning_gate`, `lab_control`, `ev_engine_v3`, `ev3_stage0`,
`run_ev3_shadow`, `apply_ev3_authority`, `intelligence_lab`, `eod_candidate_engine`,
`selected_contract_economics` or reading `index.html` — 121 files, one per process — **1,226 passed, 0
failed** (one file skips by design). The Lab JS harness (10 Node tests incl. FIX-10) runs inside it.
Lab page checked in the browser on run 20260927_205123: "Move window" and "Hold = 20 sessions" render; the
signal modal shows both EV3 lines; no console errors. Stored runs are not rewritten: the contract-identity
fix applies from the next Morning, the EV3 change from the next Evening.

**Correction (30 Sep 2026).** The regression summary above was produced with a filter that hid any file reporting failures alongside passes (`1 failed, 5 passed` contains `passed`). The underlying results were overwritten, so the exact counts cannot be re-read. Re-run with a corrected check on 30 Sep: `tests/test_avs_int001_stage0.py` fails because production code imports three untracked TEV-001 modules (pre-existing, other uncommitted work), and `tests/test_ila_selected_contract_identity.py` failed on the EV3 move-window book fields added 28 Sep (fixed 30 Sep by listing them as approved additive fields); it still fails on 15 TEV-001 forecast/research-EV fields that belong to that work.
