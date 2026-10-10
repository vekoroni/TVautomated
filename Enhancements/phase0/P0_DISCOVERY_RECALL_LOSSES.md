# P0 — Discovery recall losses, run 20261006_060401

Phase 0 characterisation (read-only). Nothing outside `Enhancements/phase0/` was changed, no pipeline was run and no provider was called.
Evidence script: `Enhancements/phase0/p0_recall_losses.py`. Its output is in `Enhancements/phase0/p0_recall_losses_evidence.json`.
Price store: `data/canonical/historical_prices.sqlite`, opened read-only with `mode=ro`. It reads `ohlcv_daily`, POLYGON_SPLIT_ADJUSTED bars with status COMPLETE, cut at trading_date <= 2026-10-05. The last write to the store was on 2026-10-06 at 07:17Z, during this run, so the store reflects the run's state.

## 1. Lifecycle file counts

File: `data/output/runs/20261006_060401/discovery/discovery_lifecycle_20261006_060401.csv`. It has 3,325 rows, one per ticker, and 7 columns.

| outcome | lifecycle_state | reason_code | tickers |
|---|---|---|---|
| SURVIVE | ACTIVE_CORE | DISCOVERY_SURVIVOR | 1,814 |
| DROP | DROPPED_STAGE | INTRADAY_ONLY_UNTESTED | 1,036 |
| DROP | DROPPED_STAGE | NO_LIVE_SETUP | 331 |
| DROP | DROPPED_STAGE | ELIG_INSUFFICIENT_BARS | 109 |
| DROP | DROPPED_TERMINAL_DATA | NO_PRICE_DATA | 28 |
| ERROR | ERROR_STAGE | SCAN_EXCEPTION_ValueError | 7 |

## 2. The deciding fact: how much daily history each group had

The table shows stored daily bars per ticker, cut at 2026-10-05. A ticker is "current" if its last bar is on or after 2026-09-28; otherwise it is "stale".

| reason_code | current, <120 bars | current, >=120 | stale, <120 | stale, >=120 |
|---|---|---|---|---|
| DISCOVERY_SURVIVOR | 1 | **1,703** | 1 | 109 |
| INTRADAY_ONLY_UNTESTED | **918** | 71 | 34 | 13 |
| NO_LIVE_SETUP | **303** | 5 | 10 | 13 |
| ELIG_INSUFFICIENT_BARS | 5 | 0 | 104 | 0 |
| NO_PRICE_DATA | 0 (no rows at all) | – | 28 | – |
| SCAN_EXCEPTION_ValueError | 0 | 0 | 0 | 7 |

Survival rate by history length (from the lifecycle file):
- 30–119 stored bars: 2 of 1,266 tickers survive (0.2%).
- 260 or more stored bars: 1,788 of 1,891 tickers survive (94.6%).

Of the 1,265 short-history drops (INTRADAY_ONLY_UNTESTED plus NO_LIVE_SETUP), 939 + 303 start on exactly 2026-05-26 with 92 bars. All 1,265 were first written on 2026-08-22 by `MIGRATION_DAILY_CACHE`, which seeded them from `data/daily/*.csv`. Those CSV files held only Discovery's 90-calendar-day fetch window. In 400 of the INTRADAY_ONLY_UNTESTED CSVs checked, 342 have exactly 92 rows.

## 3. INTRADAY_ONLY_UNTESTED (1,036): recall defect for 918 tickers

**Branch that assigns it.**
- `domain/structure_behaviour/trade_lane.py:142-180` (`_best_lane`) ranks live setups. Live means state DETECTED or ACTIVATED and the outcome level is not already passed. Tested timeframes rank first (key element at :155). If the best surviving setup is on an untested timeframe (`untested_timeframes` = 60m/15m/5m, `config/beh001_lanes_v1.json:169`), lines :171-176 return lane `INTRADAY_ONLY_UNTESTED`. This was ACK's 5 Oct change 1.
- `select_governing` (:96-131) returns it unchanged when the side is unassigned (:120-124). Only `NO_LIVE_SETUP` is converted to lane C at :127.
- Discovery then drops the ticker in `_scan_with_lifecycle`, `avshunter_discovery_ULTIMATE.py:2732-2736`. The lane is computed at `avshunter_discovery_ULTIMATE.py:1726-1728`.

**Plain condition.** The ticker has a live intraday setup but no live, unpassed 1mo/1w/1d setup.

**Why there was no daily setup for 918 of them.** BEH-001 needs 120 daily bars to read the daily timeframe (`config/beh001_behaviour_v1.json:64-66`), 60 weekly bars (:58-60) and 36 monthly bars (:52-54). Below those counts, `build_sequences` returns `NOT_EVALUATED_INSUFFICIENT_BARS` (`domain/structure_behaviour/sequences.py:254-256`). With the daily timeframe not evaluated, `handoff_thesis` sets the side to UNASSIGNED (`domain/structure_behaviour/engine.py:199-201`). The tickers had 92 daily bars, so all three tested timeframes were silently empty. Only intraday could produce a setup. Discovery's own eligibility floor is 30 bars (`avshunter_discovery_ULTIMATE.py:131`, checked at :1432), so these tickers pass eligibility and are then labelled as having no tested setup.

**Run evidence** (`behavioural_candidates_20261006_060401.csv`): 0 of the 1,036 tickers had a directed DETECTED/ACTIVATED candidate on 1mo/1w/1d. All 1,036 had one intraday.

**Replay.** I ran `analyse_ticker(t, daily<=2026-10-05, None, load_policy(), intraday_status="HISTORICAL_REPLAY")`, then `select_governing` with Discovery's side, price and ATR14:

| sample | 1d evaluated | directed live daily/weekly/monthly | lane |
|---|---|---|---|
| 20 random short-history INTRADAY_ONLY_UNTESTED | 0/20 (all `NOT_EVALUATED_INSUFFICIENT_BARS`) | 0/20 | NO_LIVE_SETUP 20 |
| All 84 INTRADAY_ONLY_UNTESTED with >=120 bars | 84/84 | 13/84 | NO_LIVE_SETUP 71; A 5, B 2, C 6 (all 13 are stale, see below) |
| 30 random full-history survivors | 30/30 | 30/30 | A 6, B 1, C 22, NO_LIVE 1 |
| **Same 30 survivors cut to their last 92 bars** | **0/30** | **0/30** | **NO_LIVE_SETUP 30** |

The counterfactual in the last row is the proof. Take good survivors, give them the 92-bar history the dropped tickers have, and every one loses all of its daily, weekly and monthly setups.

**Conclusion, split three ways:**
- **918 current, short-history tickers: recall defect (history depth).** The cause is not missing intraday data; these tickers *had* intraday data. The cause is missing daily history. No code path ever backfills older history:
  - `load_bars` fetches `now - lookback_days` (default 90, `avshunter_discovery_ULTIMATE.py:2758`, window at :1021-1031). The orchestrator always passes `--force-update` (`intelligent_orchestrator.py:1970-1976`).
  - Incremental refresh only appends forward.
  - These tickers reach 120 daily bars around mid-November 2026, 60 weekly bars around mid-2027 and 36 monthly bars around 2029.
  - The label also breaks R1 and R6: the drop says "only untested intraday setups" when the truth is "daily not evaluated: insufficient history".
  - Expected recovery: current tickers with full history survive at 1,703 / 1,779 = 95.7%. That is an estimate, not a measurement.
- **47 stale tickers (34 + 13): correct outcome, wrong reason.** These are dead or renamed symbols, with last bars from 2025-12 to 2026-02 (e.g. CADE, CMA, MMC, AXL, REVG). Polygon returned "No data" for them in this run, so `load_bars` fell back to the stale CSV (:1090-1112). That CSV has about 42 bars, and the stored intraday bars are months old. A replay on the full stored daily history even gives lanes A/B/C for 13 of them, which shows that data months old is treated as current. This is a universe hygiene and freshness defect (R12), not a recall loss.
- **71 current tickers with full history: genuine absence and by design.** The daily, weekly and monthly timeframes were evaluated and had no live directed setup (71/71 in the replay). They were dropped because only untested intraday setups were live (ACK 5 Oct).
  - Latent asymmetry, not triggered in this run: at `trade_lane.py:127`, a trade-side `INTRADAY_ONLY_UNTESTED` is not converted to lane C even when a live daily setup exists on the other side. `NO_LIVE_SETUP` *is* converted.

## 4. The other drop groups

**NO_LIVE_SETUP (331).** Same branch: `trade_lane.py:164-168` with no live setup at any timeframe, dropped at `avshunter_discovery_ULTIMATE.py:2732`.
- 303 are current with 92 bars and no intraday live setup. This is the **same history-depth defect**: the replay sample gave 1d `NOT_EVALUATED_INSUFFICIENT_BARS` for 20/20.
- 23 are stale or dead symbols (hygiene).
- 5 are current with full history. These are **genuine**: the replay of all 18 full-history NO_LIVE_SETUP tickers gives NO_LIVE_SETUP for 18/18.

**ELIG_INSUFFICIENT_BARS (109).** `scan_ticker_ultimate` rejects frames with fewer than `UltimateConfig.min_bars = 30` bars (`avshunter_discovery_ULTIMATE.py:131`, :1432-1433).
- Stored bars: 1–29, median 4. **0 of 109 have 260 or more bars** (or even 30) in the store.
- 104 have a last bar before 2026-09-28, and 100 of the 109 got "No data" from Polygon in this run. These are dead or renamed symbols that hold only one or a few migrated bars. Some names look active (BK, ATGE, AMRK hold 1 bar each and Polygon returned no data for them), so the symbol mapping needs checking with the provider. I did not check it here because no network calls were allowed.
- 5 are current but sparse: PSPW 2, PWCO 3, ASRE 5, SUME 14, DYNA 29.
- **Verdict: the rule is correct. The losses come from data acquisition and universe hygiene, not Discovery logic.**

**NO_PRICE_DATA (28).** `load_bars` returned nothing. These tickers have no store rows, no `data/daily` CSV, and Polygon returned "No data". The row is written at `avshunter_discovery_ULTIMATE.py:2922-2931`.
- The symbols include index tickers SPX and SPXW (not equities), a class-share form CWE.A, and delisted or renamed names (OAK, PGLOD, …).
- **Verdict: Discovery behaves correctly. The universe lists symbols the price provider cannot serve, which is a hygiene defect.**

**SCAN_EXCEPTION_ValueError (7).** Tickers: ESTE, LTHM, LVOX, OFC, PCYG, PNT, THRN. All are delisted, with last bars between 2023-09 and 2024-01.
- Polygon returned no data, so the frame came from the stale `data/daily/*.csv` fallback (`avshunter_discovery_ULTIMATE.py:1090-1112`).
- Those CSVs mix date strings, `'2023-08-28 04:00:00'` and `'2023-08-29'`. `pd.to_datetime(bars["date"])` at `WyckoffEngine_3101_v2.py:1534` raises a ValueError; it is reached from `avshunter_discovery_ULTIMATE.py:1447`. I reproduced this for all 7.
- `_scan_with_lifecycle` turns the exception into an ERROR row at :2726-2728.
- **Verdict: not a real recall loss, because the tickers are dead. It is a latent robustness defect: any live ticker whose frame has mixed date formats would ERROR.**

## 5. Where the universe comes from

- `intelligent_orchestrator.py:458` names the base file `data/universe/polygon_liquid_universe.csv`, which holds 3,320 tickers and was last modified 23 Sep.
- `build_augmented_universe` (`intelligent_orchestrator.py:824-848`) prepends 5 scanner tickers that are not in that file: ARKF, GOOG, SQQQ, TQQQ, ARKG. The result is 3,325 tickers, written to `runs/20261006_060401/universe/scanner_augmented_universe_20261006_060401.csv`.
- **All 3,325 appear in the lifecycle file and no ticker is missing either way.**
- The universe is stale: 278 of its symbols got "No data for X" from Polygon in this run's log (`logs/orchestrator.log`).

## 6. Side finding (out of scope, for the redesign backlog)

102 of the 1,814 survivors also got "No data" from Polygon in this run, and 110 survivors have a last stored bar before 2026-09-28. Discovery passes them forward on months-old bars with no freshness gate or flag. That conflicts with R12 ("fresh or flagged").

## Summary of root causes

| group | count | root cause | defect? |
|---|---|---|---|
| INTRADAY_ONLY_UNTESTED, current, short history | 918 | Store holds 92 daily bars (90-day migration seed, never backfilled); BEH-001 needs 120 daily / 60 weekly / 36 monthly bars, so all tested timeframes are silently NOT_EVALUATED | **Recall defect** (history depth + mislabelled reason) |
| NO_LIVE_SETUP, current, short history | 303 | Same | **Recall defect** |
| INTRADAY_ONLY_UNTESTED / NO_LIVE_SETUP, stale | 47 + 23 | Dead or renamed symbols analysed on stale CSV and intraday data | Hygiene and freshness defect; the outcome is right |
| INTRADAY_ONLY_UNTESTED / NO_LIVE_SETUP, current, full history | 71 + 5 | No live daily, weekly or monthly setup; untested intraday held out (ACK 5 Oct) | Not a defect (by design) |
| ELIG_INSUFFICIENT_BARS | 109 | Fewer than 30 bars; mostly symbols Polygon no longer serves | Rule correct; data and universe defect |
| NO_PRICE_DATA | 28 | No data anywhere (indices, class shares, delisted names) | Universe hygiene |
| SCAN_EXCEPTION_ValueError | 7 | Mixed date formats in stale CSVs of delisted tickers break `pd.to_datetime` | Latent robustness defect |
