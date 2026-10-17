# G5 + G9 minimal build receipt — American pricing for decisions in both lanes, live rate, daily option closes

17 Oct 2026. Built test-first to the minimal version ACK approved (design `G5_G9_ONE_PRICER_ONE_BASIS_DESIGN_20261017.md`,
status section; D1–D3 approved). ACK: "ensure both Lane A and B remain giving us the business outcome required"; "the rest
of the fixes next Saturday" (reminder set for Sat 24 Oct 09:00 UK). Nothing committed.

## What changed

| Item | Where | Change |
|---|---|---|
| 1. Lane B American with dividends | `data/scratch/workaround/avshunter_options_standalone.py` v2.7 (v2.6 backup in `prev\`) | Every contract the shortlist can choose from is valued by the pipeline's pricing module: the American tree, or the exact closed form for calls on stocks with no dividend; the ticker's tastytrade dividend; the observed rate of the ledger's source run. The European values are kept beside them (`*_european`). New columns on each row: `value_model`, `value_rate`, `value_rate_basis`, `value_dividend_yield`, `value_dividend_basis`. Lane B's selection rules, $5 cap and output files are otherwise unchanged. If the repo modules can't be imported, it runs on the old basis and labels every row. |
| 2. Card engine live rate | `canonical_data/market_rate_observation.py` (`rate_inputs`), `eod_candidate_engine.py`, `morning_gate.py` (`set_morning_rate_inputs`) | The Evening and the Morning pass the run's observed 3-month T-bill (macro snapshot) to the card engine, with its source and run named, in place of the 8 Oct fallback. With no observed rate, the governed fallback is used and labelled. |
| Speed (needed for item 1) | `domain/option_valuation.py` | The module owns its American tree (`american_crr_value`, plus `american_crr_values` for many contracts at once), with the same model and arithmetic as EV3's, which stays frozen (D3). The card engine now uses it. |
| 4. Daily option closes | `data/scratch/workaround/capture_option_closes.py` (new); `avs_day.ps1` v3.1 `eod` (v3 backup in `prev\`) | After the close, records bid, ask, mid, last, IV, OI and stock price for every TRADE / WATCH / ENTER card from the last 10 sessions, and every held contract (held first), into `monitor\option_closes.csv` (existing columns, one row per contract per session). No Claude credits; about one MarketData credit per contract. |
| Guard | `tests/test_g9_no_new_option_pricer.py` | Fails on any new option pricer outside the module. Lists every existing copy with its status. |

The guard scan found **more existing pricers than the 17 Oct review counted**: the macro board's own Black-Scholes (`macro_board/scenarios.py`), Lane B's capture scorer (`capture_score.py`, 4% rate, no dividend), and the research path engine's `_option_mark`. They're listed for the 24 Oct bundle.

## Tests (test-first; characterisation first)

- `test_g5_card_live_rate.py`: 5 tests.
- `test_g5_lane_b_american_pricing.py`: 7 tests. Characterisation of the European value kept unchanged; candidates valued by the module with dividend and rate; non-candidates labelled European; an ITM put worth at least its European value; the pay decision follows the American value; the run rate read from the ledger's source run; the closed form for calls with no dividend.
- `test_g5_owner_crr_tree.py`: 327 tests. The module's tree equals EV3's to 1e-9 on 324 cases; many-at-once equals one-at-a-time; speed.
- `test_g5_capture_option_closes.py`: 5 tests, including "a held contract stays held when a newer card names it again" (found on the real folders: BILI).
- `test_g9_no_new_option_pricer.py`: 1 test.
- Regression: every test file importing the EOD engine, the Morning gate, the rate module, the pricing module or the anticipated move, plus the G4/G5/G9 files. One process per file: 117 files, 1,450 tests, 1,448 passed, 2 failed, 0 errors. The 2 failures are `test_avs_fix_002_stages2_5.py` stored-run rate replays (10 and 11 Sep runs return `RATE_UNAVAILABLE`), the same failures seen on the pre-change baseline earlier on 17 Oct, so they predate this build.
- Not in git: the Lane B tool, `capture_option_closes.py` and `avs_day.ps1` live in the git-ignored `data\scratch\workaround`. Backups: `prev\avshunter_options_standalone_v2_6.py`, `prev\avs_day_v3_2026-10-17.ps1`.

## Business outcome, both lanes

**Lane A** (15 Oct Lab cards; card returns reproduced exactly on 1,127 of 1,127):
- with the live rate (0.0428 against 0.0422), the target return changes by at most 0.8 points (p99 0.18);
- **0** pay decisions flip, at 0% or at +20%;
- the **top-50 card rank is identical**.

The card, Lab book and Morning are otherwise unchanged.

**Lane B** (16 Oct replay offline, old v2.6 against new v2.7, the same chains):

| | Old (European, no dividend, 0.042) | New |
|---|---|---|
| Theses / shortlisted contracts | 435 / 874 | 435 / 874 (every old column kept, 12 added) |
| Pricing of shortlisted contracts | European | 700 American tree, 174 exact closed form (calls, no dividend) |
| Rate | 0.042 constant | 0.0428, `MACRO:T3M run 20261015_225021` |
| Dividend payers priced with their dividend | 0 of 444 | 444 of 444 |
| Pay decisions changed | — | 17 of 874 (target return change p10 / p50 / p90: −2.1 / +0.1 / +1.8 points) |
| Best contract changed | — | 5 of 435 theses (CNXN, COUR, ED, LINE, WMB) |
| Run time | 178 s | 393 s (+3.6 min; within the 5-minute budget) |

**Daily capture, dry run on the real folders (16 Oct):** 19 contracts, 1 held (BILI Jan 15P).
- The OI Dec 5P you hold has no decisions file, so it can't be captured until one exists (inbox W16-11).
- The first live capture runs at your next `avs_day.ps1 eod`.

## Closure checks (next runs)

1. Lane A, first Evening plus Morning: cards show `valuation_rate_basis = MACRO:T3M ... run <run_id>`.
2. Lane B, first `avs_day.ps1 evening`: the pricing line prints the source run's rate; the shortlist has `value_model` filled.
3. `avs_day.ps1 eod`: new rows in `monitor\option_closes.csv` for that session.
4. Rerun `g5_basis_measure.py` after a week to see the effect on real runs.

## Not in this build (Saturday 24 Oct bundle)

- D2: IV re-implied from the mid.
- Moving the remaining Lane A copies onto the module (DOI, empirical EV, Greek backfill, Options Intelligence copies, scanner, GEX, selected-contract economics, the macro board, capture scorer, path engine).
- DOI's dividend label.
- Then G2, G1/G7 and G3, decided on the captured bids.
