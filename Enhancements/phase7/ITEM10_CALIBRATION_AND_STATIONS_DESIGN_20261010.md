# Item 10 — Calibration (C-1) and station inspections (C-2)

Status: design for build (ACK 10 Oct 2026: build items 9-11, commit, then one run before Monday). Owners mapped on
10 Oct (search of the repository); this design extends them and builds only what is missing.

## What exists and what is missing

| Need | Exists | Missing |
|---|---|---|
| Outcome event and labels | `avshunter/c12_outcome/passage.py` (first passage; same-bar = AMBIGUOUS; gaps priced; DATA_GAP censored), fixed 20-session window | the window = the trade's planned hold; the setup on each record |
| Forward record | C12 `prediction_records` (45,062 rows, 32 sessions 22 Jul-8 Oct), ledger + item-8 dispositions, outcome maturation | the thesis setup / stated rate on the record (books before ~5 Oct have no thesis engine) |
| Rates shown to the trader | lane table `config/beh001_lanes_v1.json` (per timeframe x type x state, original/held-out, n), geometry (lower panel + Wilson), duration evidence (q50/q80, p_event) | per-setup lane-B rates (one pooled hit for 3 types); shrinkage; calibration slope/intercept; an "uncalibrated" state |
| Calibration maths | DOI-8 `canonical_data/dynamic_options_probability` (Platt, ECE, Brier) - not wired; `outcome_learning.assess_model_activation` gate (held-out metrics never computed) | a calibration report for the trader-facing rates |
| Station checks | pipeline_integrity, score_integrity, handoff audit, drop-off audit, manifest semantic health / geometry completeness / book stability, provider finality, `worklist_gate` (the only raise-to-stop pattern) | a per-station defect report; integrity defects that stop the line |
| End-of-line verifier | `tools/avs_verify/avs_verify.py` (data, calculation, structure rules; run by hand) | wiring into the run; calibration and trading-performance scorecards |

## Part 10.1 — Per-setup rates and calibration from the replay panels (evidence now)

- One owner `domain/setup_calibration.py` builds `config/setup_rates_v1.json` from the eval_v5 / eval_v5_holdout
  duration records (the evidence behind the lane table):
  - Event, stated exactly: **the setup's outcome level reached before its invalidation within the planned hold**
    (the setup's own q80 time, the governed runway). Censored or later = not reached; same-bar ambiguity follows the
    evaluator's label (counted as not reached).
  - Per setup (timeframe x type x state x side): n, hits, rate, Wilson interval, for both panels; lane B split per
    type (today one pooled rate for three types).
  - Shrinkage: beta-binomial (empirical Bayes) toward the parent pool (timeframe x state), prior strength from the
    pool's between-setup variance - small setups borrow strength, large ones keep their own rate.
  - Calibration: the original-panel (shrunk) rate as the prediction, the held-out panel as reality: reliability by
    bin, calibration slope and intercept (logistic fit of held-out outcomes on logit(predicted), weighted by n),
    ECE and Brier. Reported, not only "within ±10".
- Display: the card states each rate with its event, n, interval and calibration state.
- **Decision-relevant switch held for ACK:** the lane table and geometry keep their current rates until ACK sees the
  replay deltas (which setups would change lane; how many GOs geometry would change).

## Part 10.2 — Forward calibration state ("uncalibrated" until enough outcomes)

- C12 ingests the setup and stated rates with each prediction (book columns `trade_lane_setup`, `trade_lane`,
  `geometry_measured_hit_rate`, `anticipated_p_outcome_by_limit`, `planned_hold_sessions`) and scores the event within
  the planned hold (passage window = hold, not a fixed 20).
- Per setup: forward n and observed rate against the stated rate; state `UNCALIBRATED_FORWARD` until a governed
  minimum (config) of resolved outcomes over a minimum number of distinct sessions; then CALIBRATED / MISCALIBRATED
  with slope and intercept. Ticker clustering: intervals by session x ticker blocks (today sessions only).
- Card: "replay rate 68% (n 1,099, held out) · forward: uncalibrated (n 0 of 100)".

**As built (10 Oct 2026).** `domain/forward_calibration.py`; C12 `LABEL_COLUMNS` carry `trade_lane_setup`,
`trade_lane`, `trade_lane_side`, `planned_hold_sessions`, `setup_rate_within_hold`, `setup_hold_bars`,
`geometry_measured_hit_rate`, `anticipated_p_outcome_by_limit` from the next ingested book. Config
`forward_calibration`: 100 resolved over 20 distinct sessions; bars -> sessions 1 / 5 / 21 (1d / 1w / 1mo).
- The event uses the hold the stated rate was measured on (`setup_hold_bars`, converted), not the book's planned hold.
- **Maturity (added on evidence):** only outcomes whose hold (capped at the scorer window) has fully elapsed since the
  evidence session count. The first receipt without it read 500 resolved, one setup 28 of 28 - fast resolutions only
  (hits and stops land early, timeouts never do). With it: 15 matured of 1,051 (`ot10_forward_receipt.json`).
- Scorecard calibration section reads the store (`forward_state`, setups, resolved, calibrated / miscalibrated; a
  missing store is NOT_AVAILABLE; any MISCALIBRATED setup sets the section FAIL - report only). The latest report is
  written to `data/canonical/forward_calibration_latest.json`; the trade lane reads it into `setup_forward_state` /
  `setup_forward_text` for the card (no report: "forward: not measured").
- **Not built here (open):** (1) passage window = hold. C12 scores a fixed 20-session window; 62 of 78 setups hold
  longer (13 of 26 1d, 25 of 26 1w, 24 of 26 1mo), so their window TIMEOUTs are BEYOND_SCORER_WINDOW, never misses.
  Extending C12's window per prediction changes the measurement owner and re-scores the store; no labelled prediction
  can pass 20 sessions before about 3 Nov 2026, so it follows the Monday run (ACK). (2) Session x ticker block
  intervals: plain Wilson for now; clustering matters once n is near the minimum.

## Part 10.3 — Station inspections (C-2)

- One owner `domain/station_inspection.py`; run after Discovery, Options, EOD candidates, the Lab book and the
  Morning gate; each writes `diagnostics/station_<name>_<run>.json` (checks, counts, defects with rows).
- Two classes, governed in config:
  - **STOP (integrity invariants)**: rows in = rows out + accounted drops; unique tickers; a directed row's side equals
    its governed direction record; no future timestamps; prices and premiums positive; target and invalidation on the
    correct sides of the reference on rows that carry both; required identity fields present. A STOP defect raises
    (the `worklist_gate` pattern) with the station, check and rows - the line stops with the reason.
  - **REPORT (quality)**: fill rates, coverage, distributions, semantic health - reported, never stopping.
- Before any check is STOP, it is replayed on the 8 Oct run: it must be zero there (or the defect is real and fixed
  first), so the next run cannot be stopped by an unproven check.

## Part 10.4 — End-of-line scorecards

- `tools/avs_verify` runs at the end of the Evening and the Morning (non-blocking), and a scorecard
  `diagnostics/scorecard_<run>.json` reports five sections: data (provider finality, missing fields, freshness),
  calculation (avs_verify P0 rules, station checks), structure (thesis/geometry completeness, dispositions),
  calibration (10.1 / 10.2 states), trading performance (C12 signal outcomes, forward record).

## Order

10.3 first (it protects the run before Monday), then 10.1, 10.4, 10.2. Exact-option outcome capture
(`AVSHUNTER_OPTION_OUTCOME_CAPTURE_ENABLED`, off pending canary) is a separate decision for ACK.
