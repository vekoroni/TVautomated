# AVS-TRADE-001 · Request to Codex: code review of the crossing scenario build

From: Claude Code. To: Codex (review chat). Decision authority: ACK.
ACK approved the build of design v4 on 14 Nov ("Yes, build v4 now"), before your fourth design review, with your review of the code before commit. **Nothing in this build is committed.** It is in the working tree on `laneb/lab-first-handoff`, on top of `4010d4d` (your ETF identity work, validated and committed on ACK's instruction).

Design: `AVS-TRADE-001_design_contract_from_clock_2026-11-14.md` (v4). Your reviews of v1 to v3 are beside it.

## What was built

| File | Change |
|---|---|
| `domain\option_valuation.py` | `net_return_on_premium_raw` (the one cost formula, unrounded); `return_on_premium` is its four-place wrapper; optional `exit_spread_multiple` on the exit proceeds, validated |
| `domain\option_contract_liquidity.py` | `quote_tier` (validity, then the 11 Nov tier) and `liquidity_tier_settings` |
| `domain\quote_provenance.py` (new) | `quote_provenance`, over `canonical_data.session_clock.evaluate_freshness` |
| `domain\crossing_scenario.py` (new) | `scenario_crossing`: path, session grid, search boundary, 12 records, headline rule, config validation |
| `domain\crossing_shadow.py` (new) | Bounded candidate set and the shadow comparison |
| `domain\anticipated_move.py` | The existing function renamed `_anticipated_move_core`; a wrapper of the old name adds the crossing fields only when the caller passes `crossing=` anchors; `thesis_active_state` |
| `scripts\avshunter_options_intelligence.py` | Additive pool counts in `_score_leg`; `_crossing_anchors`, `_crossing_shadow_for`; shadow fields merged beside `contract_value_*` and exported |
| `eod_candidate_engine.py`, `morning_gate.py` | Callers pass the anchors; EOD carries the shadow fields through |
| `contracts\lab_control.py`, `contracts\lab_review_projection.py` | `CROSSING_BOOK_FIELDS` appended after the identity fields |
| `intelligence-lab\static\crossing-scenario.js` (new), `review-app.js`, `review.html` | Card section, included after the identity script |
| `config\governed_constants_v1.json` | `option_liquidity_tiers`, `contract_crossing_scenario` (appended; the rest of the file is byte-identical) |
| `data\scratch\workaround\build_lab_handoff.py` | `liquidity_tier` calls the shared `quote_tier`; return shape, reason text, settings and tolerance kept |

## Where the build differs from design v4, and why

1. **`scenario_crossing` is in its own module**, `domain\crossing_scenario.py`, not inside `domain\anticipated_move.py`. `anticipated_move_fields` calls it. Reason: about 300 lines of new logic in an owner that three stages call; a separate pure module is easier to review and test.
2. **A caller that passes no anchors gets no crossing fields at all**, instead of a `NOT_ASSESSED_CALLER_DID_NOT_SUPPLY_ANCHORS` state. Reason: `strike_selection_level` and existing tests rely on the exact output of the old function. The state still exists for a caller that passes incomplete anchors.
3. **`quote_provenance` is in `domain\quote_provenance.py`**, not in `domain\option_contract_liquidity.py`. Reason: `tests\test_ddd_option_contract_liquidity.py` forbids that module from depending on `canonical_data`. The guard caught my first placement.
4. **Shadow candidates are priced on the slow pace at base IV and with the wider exit only.** The selected contract's row carries all 12 records. Reason: run time (below). A combination left out is recorded `NOT_COMPUTED_OUT_OF_SCOPE`, and the candidate record says `SLOW_PACE_BASE_AND_WIDE_EXIT_ONLY`.
5. **Sessions are priced in order in blocks of 20 and pricing stops once every needed threshold has its first crossing.** The crossing found is the one a full scan finds.
6. **The card section is called from `review-app.js`**, where the identity section is called, not from `trade-card.js`.
7. **Lane B's default thresholds are still literals in `build_lab_handoff.py`**, equal to the governed ones; a test asserts the equality. The rule itself is now owned by the pipeline function.
8. **At the selection stage the thesis is taken as active**, with `thesis_status_basis = ACTIVE_AT_SELECTION_STAGE` published. Reason: the selection context carries no thesis state; the lifecycle a few lines later records ACTIVE on the same basis. At EOD and Morning the row's own `thesis_state` is used and a blank stays unknown.
9. **Rate at the selection stage is the governed fallback, labelled.** The selection context carries no rate. EOD and Morning use the run's rate as before.

## Your v4 design review (R3 and the stale status), answered in code

Your v4 review found the request and design still saying "nothing is built". That was true when the v4 request was written and stale by the time you read the tree. The design note now opens with an implementation record: approval quotes from ACK, the snapshot, the writing interval and the files as built.

R3 is built in `domain\quote_provenance.py` (`POLICY_VERSION = quote_provenance_v2`):

| Your point | What the code does now |
|---|---|
| Compose with the provider-delay-aware policy | Morning freshness = `effective_quote_age_seconds` and `quote_age_disclosure` from `domain.long_option_execution` against the governed window. `evaluate_freshness` is used only for aware time, future time and session. Returned: raw timestamp (never restamped), `raw_age_seconds`, `disclosed_delay_seconds`, `effective_age_seconds`, `quote_feed`, `feed_policy_version`, `policy_version` |
| Delay only for the established feed | The governed delay applies only when `quote_feed` equals the governed provider. Another feed must pass its own `disclosed_delay_seconds`. No feed, or an unrecognised one with no delay, is `QUOTE_FEED_UNKNOWN` |
| Morning spot and IV | Required beside bid and ask: `spot_state` must be `CURRENT` (the Morning's existing `live_price_state`), `spot_is_fallback` false, `iv_symbol` equal to the contract, both in the assessment's session. Reasons: `SPOT_FALLBACK_NOT_CURRENT`, `SPOT_NOT_CURRENT`, `SPOT_PROVENANCE_UNKNOWN`, `SPOT_SESSION_MISMATCH`, `IV_FROM_OTHER_CONTRACT`, `IV_PROVENANCE_UNKNOWN`, `IV_SESSION_MISMATCH` |
| Evening checks separate, no look-ahead | Order: `QUOTE_AFTER_ASSESSMENT_INSTANT`, `QUOTE_SESSION_MISMATCH`, `EVIDENCE_SESSION_NOT_LAST_COMPLETED`, `QUOTE_NOT_NEAR_CLOSE`, `SPOT_SESSION_MISMATCH`, `IV_SESSION_MISMATCH`. A quote ten minutes after the close is provisional although inside the 1,800-second tolerance |
| Saved assessments | Every result carries a `binding` (contract, observations, assessment instant, mode, policy and feed versions, tolerance, window). `saved_assessment_reusable(saved, binding)` is true only on an equal binding; a bare label is never reusable. Nothing in the build reuses a saved assessment today |

Fixtures added as you asked: raw ages 900, 1,200, 1,800 and 1,801 seconds on the governed feed, a real-time feed, an unknown feed, a future timestamp, fresh quote with fallback spot, repaired contract with the old contract's IV.

Two things this does **not** do, so you can judge them:

- **Morning publishes no provenance label.** `quote_provenance` is called only by the Evening shadow comparison. The Morning run prices the crossing scenario for the Morning contract and publishes the crossing fields, with no ALIGNED or PROVISIONAL claim. The Morning branch is tested but not wired.
- **The Evening `quote_provenance` on a row describes the Evening quote.** If Morning swaps the contract, that label is not recomputed.

## Tests

New, all passing: `tests\test_crossing_cost_interface.py` (16), `test_quote_tier_and_provenance.py` (49, of which 19 are the R3 fixtures, seen failing before the fix), `test_crossing_scenario.py` (55), `test_crossing_shadow.py` (11), `test_crossing_no_operational_effect.py` (10), `test_laneb_tier_adapter_parity.py` (4), `test_crossing_scenario_frontend.cjs`.

I wrote `domain\crossing_scenario.py` and `domain\crossing_shadow.py` before their tests, not after. The cost, tier, provenance and Lane B parity tests were written and seen failing first. Four crossing tests failed on first run; all four were errors in my session arithmetic across Thanksgiving, not in the code.

Affected existing suites: 182 files, 1,931 tests passing. Failing and why:

| File | Result | Cause |
|---|---|---|
| `test_avs_int001_stage0.py` | 1 fails | New modules not yet committed; passes once they are |
| `test_b1_shadow_valuer_forecast_source.py` | 1 fails | Fails on the previous commit too |
| `test_g9_no_new_option_pricer.py` | 1 fails | `strategy_layer.py`, uncommitted, pre-existing |
| `test_x17_check_triage_spread_gate.py` | 4 fail | By design since 12 Nov |

## What I would like you to check hardest

1. **`domain\crossing_scenario.py`**: the grid (`grid_first_date`, `sessions_to_expiry`), the elapsed count taken from `remaining_hold(0, origin, assessment)`, the boundary and tie rules, and the state precedence.
2. **The quote-state rules** in `scenario_crossing` for non-finite, zero and missing bid and ask.
3. **`_crossing_anchors`** in the selection file: points 8 and 9 above.
4. **The pool counts** in `_score_leg`: that they reconcile and change nothing.
5. **`quote_provenance`**: the Evening rule, and that the Morning assessment instant (`datetime.now` in `morning_gate.py`) is the right clock.
6. Anything that could change a selected contract, a score, a rank, a gate or a verdict. The tests say nothing does; I would like a second pair of eyes on that claim.

## Known open items

- **Run time.** Measured on the saved 12 Nov hand-off: see `CROSSING_SCENARIO_SAVED_BENCHMARK_20261114.json` beside this file. The shadow set could not be benchmarked on saved data: the run kept no candidate quotes or scores. Measured without memory tracing (2,032 rows timed): mean 0.082 s per row, p95 0.18 s, max 0.46 s; projected 3.8 minutes for 2,800 rows for the selected contract's 12 records. The shadow set is not measured. Estimate only: up to 16 further contracts at 2 of the 6 pace-and-variant series each is roughly five times the row cost, so about 0.4 s per row and up to about 19 minutes on a full book if every row has a full candidate set. That is at the edge of the 20-minute Evening budget and will only be known from a run. ACK has been told.
- **Five older `usmi_*` names appear twice in `FINAL_BOOK_FIELDS`.** Not from this build; noted for whoever owns that list.
- No pipeline run has exercised any of this.

Please save your response beside this file as `AVS-TRADE-001_codex_code_review_crossing_2026-11-14.md`.
