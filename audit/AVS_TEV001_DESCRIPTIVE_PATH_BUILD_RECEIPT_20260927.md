# AVS-TEV-001 descriptive-only handoff — build receipt

Date: 2026-09-27  
Scope: frozen pre-option Discovery description into Intelligence Lab and the structured Interpreter input. This is **not** a numeric C4/C8 release or trading authority.

## Signed point-in-time boundary

- The Evening packet is built only from the run's Discovery CSV and run metadata. It records the source SHA-256, evidence session, cutoff, run ID, packet version and advisory authority. Publication is once-only; Morning reads the same hash-verified packet and cannot rewrite the Evening claim.
- A directional forecast is `DESCRIPTIVE_ONLY` only with governed direction, same-session non-stale bar, positive reference spot and side-correct pre-option geometry when supplied. Missing target or stop stays null and is explained. Invalid/missing inputs remain `DATA_INSUFFICIENT`; no candidate is silently dropped.
- CALL/PUT is translated one-way to BULL/BEAR at the legacy Discovery boundary. The packet contains no option symbol, quote, premium or option-derived target. Selected contracts cannot improve the ticker forecast.
- `c4_reliability_state=NOT_ESTIMABLE`, `c8_valuation_state=NOT_VALUED_STATISTICAL_SUPPORT` and `c8_numeric_ev=null` are explicit for every projected row. The existing EV-3 fields are not relabelled as C8. `option_expression_state` is separate from `forecast_state`.
- Historical bars acquired after their purported observation date do not meet the signed point-in-time training standard. No calibrated probability, physical-measure path set or numeric C8 EV was fitted from them.

## Wired outputs

The packet and receipt live in `data/output/runs/<run_id>/forecast/ticker_forecast_descriptive_v1/`. `final_opportunity_book_<run_id>.json`, its CSV and the Lab triage CSV carry the typed forecast and expression states; the Lab API and structured Interpreter input read those same fields. The Lab detail panel labels ticker forecast and option expression separately. The Lab book includes packet source location and reconciliation counts for projected, descriptive, insufficient and unvalued rows; its population-preserved boolean must remain true.

The current Lab decisions and execution permission are unchanged. The descriptive path is additive and advisory, not an opt-in switch, trade gate or route to an order.

## Offline verification

- TDD: the new Lab reconciliation assertion failed before its implementation, then passed.
- Focused Lab/Interpreter/forecast/WAR suite: **64 passed**. `git diff --check` passed for modified tracked files.
- Full suite of tests calling the Lab book writer: **220 passed, 3 subtests passed**. The pre-existing ILA-003 golden allow-list was amended only to recognise the new additive fields; its comparison of all older values and provenance remains intact.
- Read-only in-memory replay against stored run `20260926_173730`: 1,666 Discovery rows and 1,554 Lab rows; all 1,554 Lab rows matched a Discovery ticker and received a typed projection. Of those Lab rows, 1,362 were `DESCRIPTIVE_ONLY` and 192 `DATA_INSUFFICIENT`; all 1,554 had C8 `NOT_VALUED_STATISTICAL_SUPPORT`. No old run package was rewritten.

## Remaining acceptance boundary

No user-started Evening/Morning run or provider canary was performed here. The next manual run must verify terminal pipeline completion, packet receipt/hash, Discovery-to-Lab row identity, Lab and Interpreter field parity, frozen Evening claim after Morning, and that no numeric C8 EV or new execution authority appears. The signed C3/C4/C5/C6/C8 quantitative design remains subject to point-in-time provenance and independent outcome support; this descriptive path does not substitute for it.
