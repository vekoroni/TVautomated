# P0-8 — Outcome Scorer (C12 pulled forward): Design

| Item | Value |
|---|---|
| Version | 1.0 (17 Sep 2026) |
| Status | **APPROVED by ACK (17 Sep 2026)**: include August books (reported separately), underlying outcomes first, macro and market conditions as analysis labels (§6a). Configuration values (§9) registered as PROVISIONAL. |
| Context | C12 Outcome (early, scoring **legacy** predictions); feeds C13 Validation reports |
| Governed by | Specification v1.1 §15–§17, Invariant E as amended (AM-1: point-in-time labels with right-censoring), §24; knowledge notes 01 and 06; `CLAUDE.md` |
| Depends on | P0-2 configuration registry, P0-3 run context / XNYS calendar (done) |

---

## 1. Purpose

Score every prediction the pipeline has **already recorded** — and every new one from now on — against what the market actually did, without trading anything:

> "On evidence session *t*, ticker XYZ was published as BULL with invalidation 47 and target 52. Over sessions 1–20 after *t*: did price reach the target first, the invalidation first, or neither — on which session — and what would the selected contract have been worth?"

This starts the hindsight-free evidence record immediately, measures how good the legacy decisions really are (baseline the rebuild must beat), and becomes the outcome engine the new contexts reuse.

It is **measurement only**: it never changes a decision, never feeds back into legacy logic, and never grants authority.

## 2. Inputs (verified 17 Sep 2026)

| Input | Location | Notes |
|---|---|---|
| Recorded predictions | `data/output/runs/<run_id>/intelligence_lab/final_opportunity_book_<run_id>.csv` | 27 runs with a book (4 Aug – 16 Sep 2026). September books carry `thesis_id` (`TICKER:DIRECTION:SESSION:OLM2`); August books do not and store missing targets as `0` |
| Run facts | `data/output/runs/<run_id>/run_meta.json` | `run_status`, `pipeline_mode` (EOD / MORNING_VALIDATION), `session_date`, `run_condition`, `evidence_cutoff_utc` (recent runs only) |
| Daily bars | `data/canonical/historical_prices.sqlite` `ohlcv_daily` | 3,618 tickers, 2021-08-23 → 2026-09-16, Polygon split-adjusted, current every evening |
| Option marks | `data/phantom/phantom_history.db` `chain_snapshots` | Daily full panel for 28 Aug → 15 Sep (backfill), candidates on 11/14 Sep, weekly before 28 Aug |
| Calendar | `avshunter/shared/xnys_calendar.py` | Sessions, holidays, early closes |
| Macro view at prediction time | `data/output/runs/<run_id>/macro_snapshot.json` (saved by every run with a book) | `regime_label`, `regime_state`, `regime_probability`, `macro_conviction`, `risk_on_off_switch`, `credit_state`, `net_liquidity_score`, `rates_impulse`, `sector_lead`, `sector_avoid`, `as_of_utc`, `report_date`, `source` |
| Scheduled macro routine | `dropbox/macro/thesis/macro_thesis_YYYY-MM-DD.md` (and `macro_context_YYYY-MM-DD.json` once the routine writes it) | One thesis file so far (2026-09-14); used when present for the evidence session |

Book fields used: `ticker`, `direction` / `final_direction`, `thesis_id`, `underlying_price` (reference), `invalidation_price`, `target_price` / `structural_target`, `contract_symbol`, `contract_bid` / `contract_ask`, `dte`, `lab_rank`, `priority_rank`, `tier`, `lab_verdict`, `final_action`, `thesis_state`, `ev3_absolute_state`, legacy EV fields, plus any other label columns recorded for grouping.

## 3. Domain model

### 3.1 PredictionRecord (immutable, written once)

```text
prediction_id           sha256(run_id, ticker, direction, evidence_session, reference, invalidation, target, contract_symbol)[:24]
run_id, pipeline_mode, run_condition
book_path, book_sha256, book_mtime_utc, ingested_at_utc
provenance_class        RECORDED_AT_RUN | RETROSPECTIVE_UNVERIFIED (§4.2)
ticker, direction       BULL | BEAR (from CALL | PUT)
evidence_session        XNYS session the prediction is based on (§4.1)
evidence_session_source THESIS_ID | RUN_META | DERIVED_FROM_RUN_ID
reference_price
invalidation_price, invalidation_state   VALID | MISSING | WRONG_SIDE | NON_POSITIVE
target_price, target_state               LEVEL | NONE | INVALID_LEGACY (0, negative or wrong side)
contract_symbol, contract_state          VALID | MISSING | SIDE_MISMATCH (e.g. CALL thesis with a put contract)
entry_ask, entry_bid
labels                  {lab_rank, priority_rank, tier, lab_verdict, final_action, thesis_state, ev3_absolute_state, legacy_ev_status, ...}
scorer_version
```

No field is ever defaulted. Invalid legacy values are kept as recorded and classified.

### 3.2 UnderlyingOutcome (append-only, one row per prediction per as-of session)

```text
prediction_id, as_of_session, scorer_version
sessions_observed        k = XNYS sessions after evidence_session with final bars, up to as_of (≤ 20)
state                    TARGET_FIRST | STOP_FIRST | AMBIGUOUS | OPEN_CENSORED | TIMEOUT | DATA_GAP | NOT_SCORABLE
resolution_session       1..20 when resolved
exit_price               target / stop fill (§5.2) / close at session 20
return_to_exit_pct, r_multiple (target or exit move ÷ invalidation distance)
mfe_pct, mae_pct         over observed sessions
reason                   for DATA_GAP / NOT_SCORABLE
terminal                 true once TARGET_FIRST / STOP_FIRST / AMBIGUOUS / TIMEOUT / NOT_SCORABLE
```

### 3.3 ExpressionOutcome (append-only, when a contract exists)

```text
prediction_id, as_of_session, scorer_version
exit_session, exit_reason        resolution | timeout | contract last usable session (expiry − exit buffer)
exit_bid, mark_source            chain_snapshots row (quote_date, option_symbol)
state                            MARKED | MARK_UNAVAILABLE | ENTRY_NOT_VALUED | CONTRACT_INVALID
pnl_per_contract, return_on_premium (entry at ask, exit at bid)
```

## 4. Rules

### 4.1 Evidence session
1. `thesis_id` session date when present and a valid XNYS session.
2. Otherwise `run_meta.session_date`.
3. Otherwise derived: the last XNYS session completed at the run's start (run_id is a UTC timestamp) → `DERIVED_FROM_RUN_ID`.
Morning-validation books score the **same** evidence session as the thesis they validate; their morning labels (`final_action`) are stored as additional labels, not new predictions (deduplicated by `prediction_id`).

### 4.2 Provenance (hindsight guard)
- `RECORDED_AT_RUN`: book `mtime` is before the close of session 1 after the evidence session **and** `book_sha256` is recorded at first ingest.
- `RETROSPECTIVE_UNVERIFIED`: otherwise (e.g. the book was rewritten later). Scored, but excluded from headline evidence and reported separately.
- From first ingest onward, any later change to a book's hash is recorded as a new version and never overwrites the original prediction.

### 4.3 Point-in-time (spec AM-1)
- Scoring as of session *S* uses only bars for sessions ≤ *S* with final bar status.
- Unresolved predictions are `OPEN_CENSORED` at `sessions_observed`; they are re-evaluated each day until terminal.
- Nothing is re-scored retroactively under a different scorer version without a new `scorer_version` row set.

## 5. Algorithms

### 5.1 First passage (per prediction, sessions k = 1..20)
For BULL (mirrored for BEAR):
- Target touched on session k if `high_k ≥ target` (only when `target_state = LEVEL`).
- Invalidation touched if `low_k ≤ invalidation`.
- Both on the same session → `AMBIGUOUS` at k (counted as stop-first in estimators; count reported).
- First touch ends the path. No touch through session 20 → `TIMEOUT` with exit at session-20 close.
- A missing bar inside the window → `DATA_GAP` at that session (censored before it), with reason.
- `invalidation_state ≠ VALID` → `NOT_SCORABLE` (reason). `target_state ≠ LEVEL` → scored as stop / timeout only, with the target class recorded (this measures the legacy 3R / missing-target problem directly).

### 5.2 Fills
- Target: exit at the target level.
- Invalidation: exit at the **worse of the invalidation level and that session's open** (gap risk).
- Timeout: session-20 close.

### 5.3 Expression marks
- Entry at the recorded `contract_ask` (> 0), else `ENTRY_NOT_VALUED`.
- Exit at the contract's bid on the exit session from `chain_snapshots`; if the session has no row for that `option_symbol`, `MARK_UNAVAILABLE` (no nearest-date substitution).
- Contract side must match direction; otherwise `CONTRACT_INVALID`.

### 5.4 Base rate (what "better than chance" means)
For each prediction, the **matched base rate** is the first-passage outcome distribution, over the same evidence session and window, of **all tickers in the price store** using the same barrier distances expressed in each ticker's ATR(14) units at the evidence session. This controls for market conditions on that date and for barrier distance.

### 5.5 Estimators and uncertainty
- Cumulative incidence of target-first and stop-first by session (Aalen-Johansen with censoring) per group.
- Expectancy in R and return-to-exit per group.
- **Independent unit = evidence session**: intervals by block bootstrap over evidence sessions; the report states the number of sessions, not just rows.
- No verdict is printed for a group with fewer than `outcome.min_sessions_for_verdict` distinct evidence sessions; below that, results are labelled INSUFFICIENT_SESSIONS.
- The report lists the number of groups compared (multiple comparisons).

## 6. Reports

Daily report (Markdown + JSON) in `Enhancements/outcomes/<as_of_session>/` (moves under `data/` after the build phase):

| Section | Content |
|---|---|
| Coverage | predictions by run, provenance class, scorable / not scorable with reasons, target class counts (LEVEL / NONE / INVALID_LEGACY), contract validity |
| Resolution | states by sessions observed; newly resolved today |
| Legacy labels vs outcome | cumulative incidence and expectancy vs matched base rate by `tier`, `lab_verdict`, `final_action`, `thesis_state`, `ev3_absolute_state`, legacy EV status, rank decile, direction |
| Timing | resolution-session distribution |
| Expressions | marked coverage; return on premium by label group |
| Caveats | sessions available, INSUFFICIENT_SESSIONS groups, number of comparisons |

## 6a. Conditions: macro view and objective market state (ACK request 17 Sep 2026)

Purpose: understand **under which conditions** predictions succeed or fail, so the learning loop builds knowledge of the market, not just of the pipeline.

**Guard (spec §14, `CLAUDE.md`):** condition labels are **analysis dimensions in outcome reports only**. They are never read by any gate, score, rank, valuation or thesis. Whether a condition later earns a decision role is decided only through C13 validation and ACK approval (spec Invariant G).

### ConditionRecord (immutable, one per prediction)

```text
prediction_id
macro_source            RUN_SNAPSHOT | ROUTINE_THESIS | NONE
macro_as_of_utc, macro_report_date
macro_freshness         CURRENT (report_date = evidence session) | STALE (older, with sessions of lag) | MISSING
macro_regime_label, macro_regime_state, macro_regime_probability, macro_conviction,
risk_on_off_switch, credit_state, net_liquidity_score, rates_impulse
ticker_sector, sector_in_macro_lead, sector_in_macro_avoid
market_trend_state      SPY close vs 50/200-session averages at the evidence session (from the price store)
market_vol_state        SPY 20-session realised volatility percentile over the prior 252 sessions
market_breadth          share of price-store tickers above their 50-session average
market_drawdown_pct     SPY distance from its 252-session high
condition_version
```

Rules:
- **Point-in-time:** macro fields come from the run's own `macro_snapshot.json` (what the run actually saw) or the routine thesis dated for the evidence session; never from today's `macro_intelligence_latest.json`, which is overwritten. A snapshot whose `report_date` is older than the evidence session is labelled `STALE` with its lag.
- **Objective market state** is computed from the canonical price store as of the evidence session, so condition analysis does not depend only on LLM-produced labels.
- **Known label-quality caveat:** `macro_conviction` equalled the prompt example value 0.63 in 13 of 32 runs (decision-path map DM-36); conviction is reported with that caveat and never used as a precise number.

Report section **Conditions**: cumulative incidence, expectancy and resolution timing vs matched base rate by macro regime, macro freshness, sector lead/avoid alignment with direction, market trend / volatility / breadth states — with session counts and INSUFFICIENT_SESSIONS labelling as in §5.5.

## 7. Storage

- `data/canonical/outcome_scoring.sqlite` (append-only): `prediction_records`, `condition_records`, `underlying_outcomes`, `expression_outcomes`, `scorer_runs` (scorer_version, config_snapshot_id, as_of_session, inputs hashes, counts).
- Idempotent: primary keys `(prediction_id)` and `(prediction_id, as_of_session, scorer_version)`; re-running a day writes nothing new.
- A view gives the latest state per prediction.

## 8. Code layout

```text
avshunter/c12_outcome/
  model.py        PredictionRecord, UnderlyingOutcome, ExpressionOutcome, enums (pure)
  geometry.py     normalisation and classification of legacy levels (pure)
  passage.py      first-passage evaluation with censoring and fills (pure)
  estimators.py   Aalen-Johansen cumulative incidence, block bootstrap by session (pure, numpy)
  base_rate.py    matched base rate (pure over provided bar arrays)
  adapters/books.py, adapters/prices.py (read-only SQLite), adapters/chains.py (read-only), adapters/storage.py
  report.py
  __main__.py     python -m avshunter.c12_outcome ingest|score|report --as-of <session|latest>
```

Scheduling: run manually first; then as a launcher step after a completed evening BUILD (P0-3 increment 2). Read-only against Phantom and the price store; the only writes are the scoring database and reports.

## 9. Configuration (registry entries, PROVISIONAL)

| Key | Proposed value | Unit |
|---|---|---|
| `outcome.window_sessions` | 20 | sessions |
| `outcome.ambiguous_policy` | `STOP_FIRST_FOR_ESTIMATION` | none |
| `outcome.stop_fill_policy` | `WORSE_OF_LEVEL_AND_OPEN` | none |
| `outcome.contract_exit_buffer` | 2 | sessions |
| `outcome.base_rate_distance_unit` | `ATR14` | none |
| `outcome.bootstrap_resamples` | 2000 | count |
| `outcome.min_sessions_for_verdict` | 20 | sessions |
| `outcome.first_session_provenance_cutoff` | `SESSION_1_CLOSE` | none |

## 10. Tests (tests_rebuild)

1. Geometry classification: zero / negative / wrong-side targets → `INVALID_LEGACY`; wrong-side invalidation → `NOT_SCORABLE`; CALL thesis with put contract → `CONTRACT_INVALID`.
2. First passage: target first, stop first, same-session ambiguity, gap-through-stop fill at open, timeout at session 20, BEAR mirror.
3. Censoring: prediction scored as of session 3 is `OPEN_CENSORED(3)`; re-scored at 20 resolves; no bars beyond as-of are read.
4. Data gap: missing bar mid-window → `DATA_GAP` with reason.
5. Holidays and early closes in session counting.
6. Aalen-Johansen against a hand-computed example with censoring; bootstrap uses session blocks.
7. Base rate on synthetic bars equals the analytic answer.
8. Provenance: mtime after session-1 close → `RETROSPECTIVE_UNVERIFIED`; changed book hash recorded as new version.
9. Idempotency: re-running an as-of session writes no rows.
10. Package purity (no wall clock, no literals, no `sys.path`).

## 11. Deliverables and effort

| Step | Effort |
|---|---|
| Domain (geometry, passage, estimators, base rate) + tests | 1–2 days |
| Adapters, storage, ingest of the 27 existing books | ~1 day |
| Reports and first scored report | ~1 day |
| Expression marks | ~1 day |

No API calls; no changes to legacy code.

## 12. Decisions (ACK, 17 Sep 2026)

1. Design **approved**.
2. August books **included**, reported separately (`DERIVED_FROM_RUN_ID`, provenance classified per §4.2).
3. Configuration values (§9) registered as PROVISIONAL.
4. Order: **underlying outcomes and base rate first**, then conditions (§6a), then expression marks.
5. Macro and market conditions added as analysis-only labels (§6a) so the loop learns the conditions behind outcomes.

Build order: domain (geometry, passage, estimators, base rate) → ingest 27 books → underlying outcomes → conditions → first report → expression marks.

## 13. Implementation status (17 Sep 2026)

| Increment | Status |
|---|---|
| 1 — ingest, first passage, Aalen-Johansen, report | Done (commit 1912f75). 25 books, 18,330 predictions. |
| 2 — matched base rate (§5.4), ConditionRecord (§6a), fast bootstrap | Done, uncommitted. Base rate `c12-base-rate-v1.0.0`: vectorised over the full price store (3,618 tickers); predictions enter the same estimator as fractional events; paired session-block bootstrap gives observed − base intervals. Conditions `c12-conditions-v1.0.0`: run's own `macro_snapshot.json` + SPY trend / volatility percentile / breadth / drawdown; ticker sector not yet available (`MISSING_TICKER_SECTOR`). Nine `outcome.condition.*` keys registered PROVISIONAL. Guard test: nothing outside C12 imports it. Full run 45 s (was 19 min). |
| 3 — expression marks (§5.3) | Next. |

First comparison vs chance (as of 2026-09-16, all INSUFFICIENT_SESSIONS): overall target-first excess +0.3% (−0.2 to +0.8), stop-first excess +2.1% (+1.4 to +2.8). `thesis_state` TARGET_REALIZED / INVALIDATED describe levels already crossed when the book was written (44 of 45 and 32 of 32 resolve on session 1); they are not predictions and must not be read as skill. Conditions coverage is narrow: SPY above its 200-session average throughout; `risk_on_off_switch` identical on all 19 sessions.
