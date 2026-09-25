# D3 — Book stability as a manifest diagnostic, split by cause, morning to morning

**Date:** 2026-09-25 · **Owner of the change:** `contracts/lab_control.build_final_run_manifest`, existing owner of the run manifest · **Authority:** none; diagnostic only, no flag, no health penalty, no label change (reviewer amendment: "D3 as a diagnostic rather than a run-health failure") · **Requested by:** ACK ("carry on with D3")

## 1. Why

The research harness found near-zero overlap of its positive set between consecutive books, and the register called it a fault to find. The pipeline itself publishes no measure of how much its actionable set changes from one morning to the next, nor why. Without that number and its cause split, "the book has no memory" cannot be separated from "the open re-priced the spreads", which is a legitimate cause.

## 2. What the data says (offline, 24 → 25 Sep morning books)

| Measure | Value |
|---|---|
| Previous actionable (routed GO / GO_LIMIT) | 401 |
| Current actionable | 273 |
| Retained | 197 (49%) |
| New entrants | 76 |
| Dropped | 204 |
| Dropped: quote not executable (wide spread 106, liquidity review 46, requote 1) | 153 |
| Dropped: geometry missing today (had it yesterday) | 24 |
| Dropped: routed out (monitor liquidity 9, stand-down direction 7, wait for pullback 7, upstream authority 1) | 24 |
| Dropped: absent from today's book | 3 |

Two readings. The pipeline's own actionable set is far more stable (49%) than the harness's positive set (13%), which shows the harness number was mostly measuring its own valuation's sensitivity. And three-quarters of the churn is the open re-pricing spreads, a market cause; the 24 rows that lost their geometry overnight are the Thesis owner's instability and belong with A1.

## 3. Design (additive, diagnostic)

`_book_stability(run_id, runs_dir, mode, run_meta, current_validated_rows)`:

1. Applies only when `mode ∈ {MORNING_VALIDATION, LIVE}` and the current run has validated-trades rows; otherwise `state = NOT_APPLICABLE_<mode>`.
2. Previous book: the newest run folder older than this run whose `run_meta.json` says `pipeline_mode = MORNING_VALIDATION` (or LIVE) and whose `morning_validated_trades_<run>.csv` has rows. EOD folders in between are skipped. None found → `state = NO_PRIOR_MORNING_BOOK`.
3. Actionable set = tickers with `morning_execution_route ∈ {GO, GO_LIMIT}` in each book.
4. Dropped rows are attributed in this order, first match wins: `ABSENT_FROM_BOOK` (ticker not in today's validated rows); `GEOMETRY_MISSING` (`target_price` or `invalidation_spot` empty today); `QUOTE_NOT_EXECUTABLE` by `execution_viability_state` (anything other than `EXECUTABLE_QUOTE`); `ROUTED_OUT` by today's route.
5. Output block `book_stability` with `basis`, `state`, `previous_run_id`, `previous_session_date`, `current_session_date`, `sessions_between`, `previous_actionable`, `current_actionable`, `retained`, `retained_share`, `new_entrants`, `dropped`, `dropped_by_cause`, `authority = DIAGNOSTIC_ONLY`.
6. No stale flag, no change to `run_health_score`, `run_tradeable`, the label or the permissions. Asymmetry is not a cause the pipeline can name; it remains a harness measure.

## 4. Tests (written first), `tests/test_d3_book_stability_diagnostic.py`

- Characterisation: a morning run with no prior morning book has `state = NO_PRIOR_MORNING_BOOK` and every other manifest field exactly as before (label, permissions, stale flags, health).
- Retained, new and dropped counts with the cause split on a two-run fixture; retained share; sessions between from `run_meta` session dates.
- An EOD folder between two morning runs is skipped.
- An EOD run reports `NOT_APPLICABLE_EOD`.
- The block never adds a stale flag or changes the health score.

## 5. Result (implemented 25 Sep 2026, uncommitted pending ACK)

| Item | Outcome |
|---|---|
| Change | `contracts/lab_control.py` +84 lines: `_book_stability(run_id, runs_dir, mode, run_meta, current_rows)`, the call in the builder, the `book_stability` field. No flag, no health change, no label or permission change |
| Tests written first | `tests/test_d3_book_stability_diagnostic.py`: 1 characterisation, 5 business rules; all pass. One fixture correction during the build: a row that loses its geometry is routed out in production, so the fixture says so |
| Regression | D2 6/6, big-bang phases 6–7 3/3, Lab ranking export 2/2, morning gate authority 20/20, options liquidity morning Lab 7/7, ILA golden 7/7, book integrity 24/24 |
| Preview on this morning's real run (in memory, not written) | previous `20260924_085940` (session 23 Sep) → current (session 24 Sep), 1 session apart; actionable 401 → 273; retained 197 (49.1%); new 76; dropped 204: quote not executable 153 (wide spread 106, liquidity review 46, requote 1), geometry missing 24, routed out 24, absent 3. Label EXECUTION_READY and health 89 unchanged |

## 6. Acceptance

Monday's morning manifest reports the 25 → 28 Sep comparison with the cause split; the number to watch over the following sessions is `retained_share` and the `GEOMETRY_MISSING` cause, which should fall to zero once A1 lands.
