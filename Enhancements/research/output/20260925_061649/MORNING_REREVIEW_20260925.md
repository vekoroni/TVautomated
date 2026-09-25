# Morning re-review — run 20260925_061649 after morning validation

**State:** research, read-only. The morning run wrote its validation into the same run folder; the evening plan was preserved as `trading_plan_20260925_061649_EVENING.csv` before the morning rebuild. Morning plan: `trading_plan_20260925_061649_v2.csv` and `TRADING_PLAN_20260925_061649_MORNING_tables.md`.

## 1. The morning book

| Item | Value |
|---|---|
| Manifest | MORNING_VALIDATION · EXECUTION_READY · semantic health DEGRADED · 175 rows missing invalidation (same defect as yesterday) |
| Lab verdicts | GO 57 · GO_LIMIT 216 · MANUAL_REVIEW 804 · BLOCKED 426 · CONTRACT_REPAIR 46 |
| Morning plan (harness rule on morning quotes) | 91 rows: Tier A 22 · Tier B 56 · Tier C 13 |
| Tier A + B by Lab verdict | 68 GO or GO_LIMIT · 4 MANUAL_REVIEW · 6 BLOCKED |

## 2. What happened to last night's list

| Evening tier | Rows | Morning GO | GO_LIMIT | MANUAL_REVIEW | BLOCKED | Still in plan (A / B / C) | Dropped |
|---|---|---|---|---|---|---|---|
| A | 26 | 10 | 5 | 8 | 3 | 10 / 2 / 1 | 13 |
| B | 57 | 23 | 15 | 19 | 0 | 3 / 25 / 0 | 29 |

Why the 13 evening Tier A rows dropped:

| Cause | Rows | Tickers (evening spread → morning spread) |
|---|---|---|
| Spread widened past 15% at the open | 11 | SNEX 10.5→38.1 · PAYX 14.5→45.6 · ARWR 11.8→37.2 · KBH 11.4→34.3 · BEN 12.2→28.6 · BWA 11.8→25.2 · AKAM 9.2→23.0 · AMTM 9.5→20.0 · ABT 5.6→17.8 · AAP 12.5→17.6 · MGY 13.3→16.9 |
| Zero bid at requote | 1 | WBD |
| Asymmetry fell on the requote (still GO) | 1 | IWM (also AGAINST the packet's index-call rule) |

Two rows moved from A to B because the break-even rose (TSLA 0.34→0.41, OKLO 0.38→0.45). Ten rows kept Tier A on morning quotes: HON, TSM, SNY, MRVL, CRWV, RIO, BTI, SMCI, BMNR, IBIT.

## 3. Where the pipeline and the valuation disagree this morning

| Case | Rows | Reading |
|---|---|---|
| Pipeline GO/GO_LIMIT, valuation Tier A, no review flag | 8 | MRVL P, BTI C, FANG C, ARM P, XLK P, MNST C, BMNR P, IBIT P. The two agree |
| Pipeline BLOCKED by `STAND_DOWN_DIRECTION`, quote executable, valuation Tier A | 3 | SNY C, SMCI P, and evening SNY. A direction score killed an executable, asymmetric row |
| Pipeline GO, valuation dropped the row | 6 | CRWD P, ABT C, MGY C, AAP C, IWM C, plus evening Tier B rows. Spread or asymmetry failed on the morning quote while the gate passed |
| Pipeline GO/GO_LIMIT, valuation Tier A, but geometry degenerate | 4 | TSM P, MS C, RIO C, HON C (stock-like). The verdict is on a thesis whose target or invalidation is within 1% of spot |

## 4. Morning Tier A (22), full table

| # | Ticker | Dir | Sector | Contract (DTE) | Spread | Reach / Flat / Inval | p\* | Macro | Lab | EIL | Flag |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | RYN | CALL | Real Estate | RYN261120C00017500 (56) | 5.4% | +44 / +2 / +2 | — | AGAINST | BLOCKED | BLOCKED | DEGENERATE_GEOMETRY; STOCK_LIKE |
| 2 | CLX | CALL | Consumer Staples | CLX261120C00075000 (56) | 8.0% | +42 / −7 / −8 | — | AGAINST | BLOCKED | BLOCKED | DEGENERATE_GEOMETRY |
| 3 | HON | CALL | Industrials | HON261218C00195000 (60) | 9.5% | +54 / +24 / −10 | 0.16 | NEUTRAL | GO_LIMIT | BLOCKED | STOCK_LIKE |
| 4 | PEP | CALL | Consumer Staples | PEP261030C00125000 (35) | 13.7% | +96 / −16 / −18 | — | AGAINST | BLOCKED | EXEC_CAUTION | DEGENERATE_GEOMETRY |
| 5 | TSM | PUT | Information Technology | TSM261120P00450000 (41) | 1.8% | +125 / −32 / −35 | — | AGAINST | GO | EXECUTE | DEGENERATE_GEOMETRY |
| 6 | SNY | CALL | Health Care | SNY261218C00040000 (60) | 7.5% | +54 / −19 / −19 | — | NEUTRAL | BLOCKED | EXEC_CAUTION | DEGENERATE_GEOMETRY |
| 7 | MRVL | PUT | Information Technology | MRVL261120P00260000 (41) | 3.1% | +87 / −19 / −32 | 0.27 | AGAINST | GO | EXEC_CAUTION | — |
| 8 | BTI | CALL | Consumer Staples | BTI261218C00055000 (60) | 7.5% | +113 / −11 / −44 | 0.28 | AGAINST | GO | EXECUTE | — |
| 9 | FANG | CALL | Energy | FANG261120C00185000 (56) | 12.9% | +91 / −15 / −37 | 0.29 | ALIGNED | GO_LIMIT | EXEC_CAUTION | — |
| 10 | MS | CALL | Financials | MS261106C00190000 (42) | 14.8% | +67 / −24 / −31 | — | AGAINST | GO_LIMIT | EXECUTE | DEGENERATE_GEOMETRY |
| 11 | ARM | PUT | Information Technology | ARM261120P00310000 (41) | 5.3% | +98 / −11 / −46 | 0.32 | AGAINST | GO | EXEC_CAUTION | — |
| 12 | RIO | CALL | Materials | RIO261218C00095000 (60) | 7.4% | +66 / −25 / −32 | — | AGAINST | GO | BLOCKED | DEGENERATE_GEOMETRY |
| 13 | SMCI | PUT | Information Technology | SMCI261218P00040000 (60) | 8.3% | +62 / −22 / −30 | 0.33 | AGAINST | BLOCKED | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 14 | XLK | PUT | Technology ETF | XLK261218P00195000 (60) | 12.2% | +71 / −27 / −36 | 0.34 | AGAINST | GO_LIMIT | BLOCKED | — |
| 15 | CRWV | CALL | Information Technology | CRWV261120C00100000 (41) | 4.0% | +180 / −46 / −97 | 0.35 | ALIGNED | GO | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 16 | QCOM | PUT | Information Technology | QCOM261218P00200000 (60) | 9.5% | +50 / −15 / −27 | 0.35 | AGAINST | BLOCKED | EXEC_CAUTION | — |
| 17 | MNST | CALL | Consumer Staples | MNST261120C00043000 (56) | 15.0% | +46 / −15 / −26 | 0.36 | AGAINST | GO_LIMIT | BLOCKED | — |
| 18 | MRNA | CALL | Health Care | MRNA261120C00220000 (41) | 3.2% | +167 / −34 / −100 | 0.37 | NEUTRAL | MANUAL_REVIEW | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 19 | BMNR | PUT | Information Technology | BMNR261120P00028000 (41) | 4.4% | +60 / −27 / −37 | 0.38 | AGAINST | GO | EXEC_CAUTION | — |
| 20 | RKLB | PUT | Information Technology | RKLB261218P00080000 (60) | 3.3% | +93 / −18 / −59 | 0.39 | AGAINST | GO | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 21 | CLF | PUT | Materials | CLF261030P00013000 (35) | 11.1% | +59 / −18 / −39 | 0.39 | ALIGNED | MANUAL_REVIEW | EXEC_CAUTION | — |
| 22 | IBIT | PUT | Crypto ETF | IBIT261120P00048000 (41) | 0.7% | +69 / −24 / −44 | 0.39 | NEUTRAL | GO | EXECUTE | — |

p\* is shown as — where the geometry is degenerate, because the number is not meaningful there.

## 5. The short list after flags and macro

| Group | Tickers | Note |
|---|---|---|
| Clean, GO/GO_LIMIT, macro ALIGNED or NEUTRAL | FANG C, IBIT P | The only two rows where valuation, pipeline and macro all agree |
| Clean, GO/GO_LIMIT, macro AGAINST | MRVL P, ARM P, BMNR P, XLK P (tech puts against tech leadership) · BTI C, MNST C (calls in an avoid sector) | Executable and asymmetric; the macro overlay is the reviewer's call |
| Clean, valuation Tier A, pipeline did not pass | QCOM P (BLOCKED), CLF P (MANUAL_REVIEW, macro ALIGNED) | Worth the reviewer's look at why the gate fired |
| Flagged | The remaining 12 | Resolve the flag first: degenerate geometry (7), stock-like (2), forecast above IV (4) |

## 6. What this morning shows about the pipeline

1. **The open is the filter.** 11 of 26 evening Tier A rows lost executability on spread alone at the requote. Evening spreads are not a screen; the plan must be re-cut on morning quotes, which is what the morning validation is for.
2. **Direction gates kill executable asymmetric rows.** SNY and SMCI were BLOCKED by `STAND_DOWN_DIRECTION` with a valid quote and Tier A economics. That is the P1 finding again, on live rows.
3. **Degenerate geometry reaches GO.** TSM, MS and RIO carry GO or GO_LIMIT with a target or invalidation within 1% of spot. The Thesis owner is publishing levels that are not levels, and the gates do not notice. That belongs with the F5 / P3 geometry fix.
4. **The positive set still does not persist.** 13 of 26 evening Tier A rows dropped by the morning; 9 new Tier A rows appeared. Overlap measured on quotes, not theses, is the fair metric, and it is still low.
