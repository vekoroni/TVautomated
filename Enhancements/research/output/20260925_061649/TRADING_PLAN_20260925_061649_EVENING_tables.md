# Trading plan — evening run 20260925_061649 · for the US session of 2026-09-25

Research plan built read-only from the completed evening book. State EXPLORATORY_NO_AUTHORITY. Sizing HUMAN DETERMINED. Nothing here alters the pipeline or the run book.
Generated 2026-09-25 13:18Z · source CSV `trading_plan_20260925_061649_v2.csv`

## 1. Summary

| Item | Value |
|---|---|
| Rows in the evening book | 1,549 (all MANUAL_REVIEW or BLOCKED; GO verdicts arise only at morning validation) |
| Candidate trades listed | 86 (44 CALL, 42 PUT) |
| Tier A — asymmetric, executable, break-even p ≤ 0.40 | **26** |
| Tier B — asymmetric, executable, break-even p > 0.40 | 57 |
| Tier C — positive grid EV outside A/B | 3 |
| Tier A macro alignment | 3 aligned · 11 neutral · 12 against |
| Tier A rows with a review flag | 14 |

## 2. Macro overlay (display-only; never a gate)

| Factor | Tonight's reading | What it means for the plan |
|---|---|---|
| Regime | TRANSITIONAL_BEARISH · drift DRIFTING_BEARISH · conviction 50.75 | Selective, trigger-confirmed entries only |
| Filter | NO_GO (Fung-Hsieh, accuracy 55.6%) | Size modifier 0.70× on all positions; direction does not abstain; no ticker is blocked |
| Rates | 10Y 5.11%, 30Y 5.40%, both above deterioration gates; impulse RATES_UP | No broad QQQ/SPY/IWM calls until 10Y < 5.05%; rate-sensitive puts armed |
| Breadth | RSP−SPY −5.63%, Z −2.31, narrowing | Individual relative-strength confirmation required before any call |
| Volatility | VIX 15.67 (COMPRESSED_CONTANGO_LOW_VOL), contango, CBOE/yfinance conflict, VVIX escalating | Treat as ELEVATED_CAUTION; puts activate only on VIX > 16 CBOE close |
| Credit / liquidity | HY OAS 2.73 benign · liquidity CONTRACTING (RRP exhausted, TGA building) | No systemic stress; medium-term exposure reduced |
| Dealer gamma | NEGATIVE_GAMMA · GEX source unavailable | No dealer-flow confirmation available tonight |
| Sectors | Preferred: Energy, Information Technology, Communication Services · Avoid: Utilities, Real Estate, Financials, Materials, Consumer Staples · rotation TECH_LED_RISK_ON | Drives the ALIGNED / NEUTRAL / AGAINST column below |
| Horizon 1_5d | SELECTIVE_LONG_PLATFORM_AI_MEGA_CAP_RS_ONLY · bias MILDLY_BULLISH | Advisory size modifier 0.63 |
| Horizon 6_10d | HOLD_SELECTIVE_LONGS_MONITOR_RATE_GATE · bias MILDLY_BULLISH | Advisory size modifier 0.56 |
| Horizon 11_20d | REDUCE_TO_CORE_POSITIONS_AWAIT_REGIME_CLARITY · bias MILDLY_BULLISH | Advisory size modifier 0.49 |
| Calls rule | Permitted for exceptional platform AI and cash-generative mega-cap with confirmed relative strength only. No broad QQQ/SPY/IWM calls until 10Y reverses below 5.05%. Energy calls permitted on price confirmation only. All call entries require trigger confirmation given conviction below threshold. | |
| Puts rule | ARMED on rate-sensitive sectors (XLU, XLRE, XLP, XLF). Require VIX confirmation above 16-18 and breadth Z deterioration beyond -2.50 for full put activation. QQQ puts permitted on confirmed structure failure. IWM puts on relative weakness confirmation. | |

## 3. Candidate trades

Columns: **Contract (DTE)** is the pipeline's selected contract · **Spot → Target / Inval** are end-of-day spot, structural target and invalidation · **Spread** is the EOD spread as % of mid · **Reach / Flat / Inval** are net returns on premium at the exit session if spot reaches the vol-budget target, stays flat, or hits the invalidation (entry at ask, exit at modelled bid) · **p\*** is the probability of target-before-invalidation you must believe to break even · **Legacy p** is the pipeline's uncalibrated probability and whether it clears p\* · **Macro** is the overlay · **EIL** is the pipeline's edge verdict · **Flag** is a review flag explained in section 4.

### Tier A — asymmetric, executable, break-even p ≤ 0.40 (26)

| # | Ticker | Dir | Sector | Contract (DTE) | Spot → Target / Inval | Spread | Reach / Flat / Inval | p\* | Legacy p | Macro | EIL | Flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **WBD** | CALL | Communication Services | WBD261016C00030500 (16) | 30.84 → 47.17 / 25.39 | 2.1% | +748 / -30 / -100 | 0.12 | 0.30 ✓ | ALIGNED | EXECUTE | OUTLIER; FORECAST_ABOVE_IV |
| 2 | **HON** | CALL | Industrials | HON261218C00195000 (60) | 211.79 → 256.22 / 196.98 | 10.6% | +57 / +27 / -9 | 0.13 | 0.31 ✓ | NEUTRAL | BLOCKED | STOCK_LIKE; compare with shares |
| 3 | **SNEX** | CALL | Financials | SNEX261016C00075000 (16) | 69.52 → 88.09 / 63.33 | 10.5% | +316 / -100 / -100 | 0.24 | 0.40 ✓ | AGAINST | BLOCKED | OUTLIER |
| 4 | **PAYX** | CALL | Industrials | PAYX261120C00100000 (41) | 101.59 → 101.91 / 101.48 | 14.5% | +84 / -26 / -27 | 0.24 | 0.35 ✓ | NEUTRAL | BLOCKED | DEGENERATE_GEOMETRY; p* not meaningful |
| 5 | **TSM** | PUT | Information Technology | TSM261120P00450000 (41) | 451.15 → 445.96 / 452.88 | 3.8% | +113 / -35 / -39 | 0.25 | 0.32 ✓ | AGAINST | EXECUTE | DEGENERATE_GEOMETRY; p* not meaningful |
| 6 | **SNY** | CALL | Health Care | SNY261218C00040000 (60) | 40.94 → 41.04 / 40.91 | 7.1% | +48 / -21 / -22 | 0.31 | 0.34 ✓ | NEUTRAL | EXEC_CAUTION | DEGENERATE_GEOMETRY; p* not meaningful |
| 7 | **MRVL** | PUT | Information Technology | MRVL261120P00260000 (41) | 258.95 → 237.80 / 266.00 | 2.6% | +72 / -24 / -35 | 0.33 | 0.33 ✓ | AGAINST | EXEC_CAUTION | — |
| 8 | **CRWD** | PUT | Information Technology | CRWD261120P00255000 (41) | 259.67 → 247.07 / 263.87 | 3.3% | +72 / -27 / -36 | 0.33 | 0.30 ✗ | AGAINST | EXEC_CAUTION | — |
| 9 | **AMTM** | CALL | Industrials | AMTM261016C00020000 (16) | 19.40 → 19.97 / 19.21 | 9.5% | +144 / -61 / -70 | 0.33 | 0.34 ✓ | NEUTRAL | EXEC_CAUTION | DEGENERATE_GEOMETRY; p* not meaningful |
| 10 | **TSLA** | PUT | Consumer Discretionary | TSLA261120P00380000 (41) | 377.94 → 351.66 / 386.70 | 1.2% | +75 / -23 / -38 | 0.34 | 0.09 ✗ | NEUTRAL | EXECUTE | — |
| 11 | **ABT** | CALL | Health Care | ABT261120C00100000 (41) | 101.07 → 103.29 / 100.33 | 5.6% | +58 / -23 / -30 | 0.34 | 0.39 ✓ | NEUTRAL | EXECUTE | DEGENERATE_GEOMETRY; p* not meaningful |
| 12 | **MGY** | CALL | Energy | MGY261016C00025000 (16) | 24.74 → 28.01 / 23.65 | 13.3% | +193 / -86 / -100 | 0.34 | 0.49 ✓ | ALIGNED | BLOCKED | — |
| 13 | **ARWR** | CALL | Health Care | ARWR261016C00065000 (16) | 66.07 → 70.78 / 64.50 | 11.8% | +105 / -40 / -57 | 0.35 | 0.46 ✓ | NEUTRAL | WATCHLIST | — |
| 14 | **BWA** | CALL | Consumer Discretionary | BWA261120C00057500 (41) | 58.48 → 59.62 / 58.10 | 11.8% | +76 / -36 / -40 | 0.35 | 0.41 ✓ | NEUTRAL | BLOCKED | DEGENERATE_GEOMETRY; p* not meaningful |
| 15 | **AKAM** | PUT | Information Technology | AKAM261218P00140000 (60) | 110.41 → 60.52 / 127.04 | 9.2% | +46 / +1 / -26 | 0.36 | 0.46 ✓ | AGAINST | BLOCKED | STOCK_LIKE; compare with shares |
| 16 | **CRWV** | CALL | Information Technology | CRWV261120C00100000 (41) | 90.13 → 157.87 / 67.55 | 1.9% | +171 / -47 / -97 | 0.36 | 0.58 ✓ | ALIGNED | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 17 | **OKLO** | CALL | Utilities | OKLO261120C00040000 (41) | 38.29 → 50.02 / 34.38 | 3.8% | +120 / -40 / -75 | 0.38 | 0.35 ✗ | AGAINST | EXEC_CAUTION | — |
| 18 | **RIO** | CALL | Materials | RIO261218C00095000 (60) | 94.47 → 97.05 / 93.61 | 12.6% | +56 / -27 / -34 | 0.38 | 0.33 ✗ | AGAINST | BLOCKED | DEGENERATE_GEOMETRY; p* not meaningful |
| 19 | **AAP** | CALL | Consumer Discretionary | AAP261120C00042500 (41) | 41.43 → 43.74 / 40.66 | 12.5% | +72 / -34 / -44 | 0.38 | 0.33 ✗ | NEUTRAL | BLOCKED | — |
| 20 | **BTI** | CALL | Consumer Staples | BTI261218C00055000 (60) | 56.02 → 61.18 / 54.30 | 9.8% | +81 / -23 / -52 | 0.39 | 0.35 ✗ | AGAINST | EXECUTE | — |
| 21 | **SMCI** | PUT | Information Technology | SMCI261218P00040000 (60) | 41.51 → 37.94 / 42.70 | 4.9% | +55 / -27 / -35 | 0.39 | 0.09 ✗ | AGAINST | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 22 | **BMNR** | PUT | Information Technology | BMNR261120P00028000 (41) | 28.03 → 25.54 / 28.86 | 6.1% | +60 / -28 / -38 | 0.39 | 0.34 ✗ | AGAINST | EXEC_CAUTION | — |
| 23 | **IWM** | CALL | ETF | IWM261120C00285000 (41) | 281.66 → 289.51 / 279.05 | 0.9% | +82 / -38 / -52 | 0.39 | 0.05 ✗ | AGAINST | EXECUTE | DEGENERATE_GEOMETRY; p* not meaningful |
| 24 | **BEN** | CALL | Financials | BEN261120C00033000 (41) | 32.55 → 34.00 / 32.06 | 12.2% | +86 / -41 / -55 | 0.39 | 0.31 ✗ | AGAINST | BLOCKED | — |
| 25 | **KBH** | CALL | Consumer Discretionary | KBH261016C00045000 (16) | 47.65 → 50.86 / 46.58 | 11.4% | +68 / -24 / -45 | 0.40 | 0.40 ✓ | NEUTRAL | BLOCKED | — |
| 26 | **IBIT** | PUT | ETF | IBIT261120P00048000 (41) | 47.81 → 43.58 / 49.22 | 1.4% | +67 / -23 / -44 | 0.40 | 0.34 ✗ | NEUTRAL | EXECUTE | — |

### Tier B — asymmetric, executable, break-even p > 0.40 (57)

| # | Ticker | Dir | Sector | Contract (DTE) | Spot → Target / Inval | Spread | Reach / Flat / Inval | p\* | Legacy p | Macro | EIL | Flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **APLD** | CALL | Information Technology | APLD261120C00030000 (41) | 27.06 → 38.07 / 23.39 | 3.0% | +123 / -46 / -83 | 0.40 | 0.58 ✓ | ALIGNED | EXEC_CAUTION | — |
| 2 | **MRNA** | CALL | Health Care | MRNA261120C00220000 (41) | 194.82 → 621.30 / 52.66 | 8.2% | +146 / -38 / -100 | 0.41 | 0.31 ✗ | NEUTRAL | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 3 | **SLV** | CALL | ETF | SLV261218C00060000 (60) | 57.62 → 77.12 / 51.12 | 3.0% | +128 / -38 / -88 | 0.41 | 0.58 ✓ | NEUTRAL | EXECUTE | — |
| 4 | **AVGO** | CALL | Information Technology | AVGO261120C00360000 (41) | 350.36 → 394.00 / 335.81 | 1.1% | +83 / -28 / -59 | 0.41 | 0.29 ✗ | ALIGNED | EXECUTE | — |
| 5 | **MSTR** | PUT | Information Technology | MSTR261218P00160000 (60) | 161.61 → 132.87 / 171.19 | 1.7% | +60 / -23 / -41 | 0.41 | 0.34 ✗ | AGAINST | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 6 | **HOOD** | PUT | Financials | HOOD261120P00120000 (41) | 120.82 → 103.06 / 126.74 | 2.2% | +64 / -25 / -44 | 0.41 | 0.33 ✗ | ALIGNED | EXEC_CAUTION | — |
| 7 | **CSCO** | CALL | Information Technology | CSCO261218C00110000 (60) | 106.97 → 114.35 / 104.51 | 3.8% | +70 / -33 / -48 | 0.41 | 0.41 ✓ | ALIGNED | EXECUTE | — |
| 8 | **QBTS** | CALL | Information Technology | QBTS261120C00018000 (41) | 17.48 → 22.49 / 15.81 | 4.0% | +87 / -29 / -63 | 0.42 | 0.52 ✓ | ALIGNED | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 9 | **WULF** | PUT | Information Technology | WULF261120P00017000 (41) | 16.29 → 6.18 / 19.66 | 1.6% | +101 / -27 / -74 | 0.42 | 0.37 ✗ | AGAINST | EXEC_CAUTION | — |
| 10 | **ZIM** | PUT | Industrials | ZIM261016P00029000 (16) | 29.38 → 24.64 / 30.96 | 8.7% | +112 / -47 / -83 | 0.42 | 0.32 ✗ | NEUTRAL | EXEC_CAUTION | — |
| 11 | **NOG** | CALL | Energy | NOG261120C00024000 (41) | 23.60 → 28.67 / 22.30 | 7.1% | +80 / -24 / -60 | 0.43 | 0.35 ✗ | ALIGNED | BLOCKED | — |
| 12 | **RGTI** | PUT | Information Technology | RGTI261120P00017000 (41) | 16.50 → 7.91 / 19.36 | 3.5% | +98 / -30 / -74 | 0.43 | 0.58 ✓ | AGAINST | EXEC_CAUTION | — |
| 13 | **SYY** | CALL | Consumer Staples | SYY261120C00077500 (41) | 78.19 → 81.76 / 77.00 | 12.1% | +59 / -27 / -44 | 0.43 | 0.41 ✗ | AGAINST | BLOCKED | — |
| 14 | **CTAS** | CALL | Industrials | CTAS261120C00200000 (41) | 197.68 → 217.45 / 191.09 | 6.6% | +96 / -40 / -71 | 0.43 | 0.18 ✗ | NEUTRAL | BLOCKED | — |
| 15 | **ASTS** | PUT | Information Technology | ASTS261120P00065000 (41) | 61.06 → 19.00 / 75.08 | 6.0% | +99 / -28 / -78 | 0.44 | 0.35 ✗ | AGAINST | EXEC_CAUTION | — |
| 16 | **FSLY** | PUT | Information Technology | FSLY261218P00030000 (60) | 26.68 → 12.73 / 31.33 | 8.6% | +64 / -22 / -50 | 0.44 | 0.43 ✗ | AGAINST | BLOCKED | — |
| 17 | **AMKR** | PUT | Energy | AMKR261218P00055000 (60) | 52.69 → 24.07 / 62.23 | 8.8% | +91 / -28 / -70 | 0.44 | 0.52 ✓ | AGAINST | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 18 | **MOD** | PUT | Consumer Discretionary | MOD261120P00200000 (41) | 196.95 → 127.86 / 219.98 | 11.3% | +88 / -36 / -68 | 0.44 | 0.51 ✓ | NEUTRAL | BLOCKED | — |
| 19 | **CDE** | CALL | Materials | CDE261120C00020000 (41) | 18.94 → 32.25 / 14.51 | 6.7% | +119 / -45 / -98 | 0.45 | 0.34 ✗ | AGAINST | EXEC_CAUTION | — |
| 20 | **RKLB** | PUT | Information Technology | RKLB261218P00080000 (60) | 73.61 → 33.95 / 86.83 | 7.4% | +78 / -24 / -62 | 0.45 | 0.52 ✓ | AGAINST | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 21 | **ARM** | PUT | Information Technology | ARM261120P00310000 (41) | 306.34 → 214.42 / 336.98 | 4.2% | +67 / -25 / -55 | 0.45 | 0.41 ✗ | AGAINST | EXEC_CAUTION | — |
| 22 | **BB** | PUT | Information Technology | BB261120P00009000 (41) | 8.73 → 6.90 / 9.34 | 10.9% | +70 / -34 / -59 | 0.45 | 0.59 ✓ | AGAINST | BLOCKED | — |
| 23 | **MSFT** | CALL | Information Technology | MSFT261120C00510000 (41) | 497.93 → 694.40 / 432.44 | 2.7% | +115 / -41 / -98 | 0.46 | 0.32 ✗ | ALIGNED | EXECUTE | — |
| 24 | **IBM** | PUT | Information Technology | IBM261218P00220000 (60) | 227.06 → 152.80 / 251.81 | 3.4% | +90 / -30 / -76 | 0.46 | 0.35 ✗ | AGAINST | EXECUTE | FORECAST_ABOVE_IV |
| 25 | **NUAI** | PUT | Energy | NUAI261120P00007500 (41) | 6.94 → 3.94 / 7.94 | 6.1% | +56 / -23 / -47 | 0.46 | 0.33 ✗ | AGAINST | WATCHLIST | FORECAST_ABOVE_IV |
| 26 | **ONON** | PUT | Consumer Discretionary | ONON261120P00030000 (41) | 30.46 → 4.69 / 39.05 | 6.6% | +116 / -38 / -98 | 0.46 | 0.34 ✗ | NEUTRAL | EXECUTE | — |
| 27 | **STM** | PUT | Information Technology | STM261120P00050000 (41) | 51.58 → 35.20 / 57.04 | 7.8% | +93 / -42 / -77 | 0.46 | 0.54 ✓ | AGAINST | EXEC_CAUTION | — |
| 28 | **CRCL** | PUT | Information Technology | CRCL261218P00100000 (60) | 93.00 → 62.16 / 103.28 | 4.3% | +50 / -19 / -45 | 0.47 | 0.09 ✗ | AGAINST | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 29 | **W** | PUT | Consumer Discretionary | W261218P00100000 (60) | 97.67 → 35.76 / 118.31 | 10.0% | +88 / -30 / -78 | 0.47 | 0.29 ✗ | NEUTRAL | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 30 | **MCD** | PUT | Consumer Discretionary | MCD261120P00235000 (41) | 237.02 → 112.97 / 278.37 | 9.2% | +114 / -44 / -100 | 0.47 | 0.41 ✗ | NEUTRAL | EXECUTE | — |
| 31 | **VG** | PUT | Energy | VG261120P00012500 (41) | 13.23 → 4.03 / 16.30 | 10.5% | +104 / -47 / -94 | 0.47 | 0.29 ✗ | AGAINST | EXEC_CAUTION | — |
| 32 | **AAPL** | PUT | Information Technology | AAPL261120P00335000 (41) | 335.92 → 307.66 / 345.34 | 3.3% | +59 / -25 / -54 | 0.48 | 0.31 ✗ | AGAINST | EXECUTE | — |
| 33 | **MARA** | PUT | Financials | MARA261120P00013000 (41) | 12.92 → 9.74 / 13.98 | 2.9% | +52 / -24 / -48 | 0.48 | 0.34 ✗ | ALIGNED | EXEC_CAUTION | — |
| 34 | **IE** | CALL | Materials | IE261120C00010000 (41) | 9.99 → 13.83 / 8.71 | 8.0% | +81 / -38 / -78 | 0.49 | 0.31 ✗ | AGAINST | BLOCKED | — |
| 35 | **SOFI** | CALL | Financials | SOFI261218C00018000 (60) | 16.80 → 21.42 / 15.26 | 2.3% | +78 / -38 / -75 | 0.49 | 0.35 ✗ | AGAINST | EXECUTE | — |
| 36 | **CRDO** | CALL | Information Technology | CRDO261120C00210000 (41) | 195.97 → 336.46 / 149.14 | 4.5% | +94 / -33 / -94 | 0.50 | 0.50 ✓ | ALIGNED | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 37 | **SA** | CALL | Materials | SA261120C00030000 (41) | 29.98 → 44.34 / 25.19 | 11.2% | +87 / -40 / -88 | 0.50 | 0.35 ✗ | AGAINST | WATCHLIST | — |
| 38 | **GOOGL** | PUT | Communication Services | GOOGL261120P00340000 (41) | 342.36 → 216.00 / 384.48 | 2.7% | +90 / -34 / -92 | 0.50 | 0.35 ✗ | AGAINST | EXECUTE | — |
| 39 | **IREN** | CALL | Information Technology | IREN261120C00050000 (41) | 46.15 → 87.64 / 32.32 | 4.1% | +94 / -34 / -96 | 0.51 | 0.30 ✗ | ALIGNED | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 40 | **WMT** | PUT | Consumer Staples | WMT261218P00110000 (60) | 107.59 → 79.75 / 116.87 | 7.8% | +71 / -27 / -78 | 0.52 | 0.18 ✗ | ALIGNED | EXECUTE | — |
| 41 | **AG** | CALL | Materials | AG261218C00020000 (60) | 18.76 → 32.71 / 14.11 | 5.6% | +87 / -38 / -95 | 0.52 | 0.52 ✗ | AGAINST | EXEC_CAUTION | — |
| 42 | **FLR** | PUT | Industrials | FLR261120P00052500 (41) | 50.63 → 27.47 / 58.35 | 12.0% | +75 / -33 / -83 | 0.52 | 0.31 ✗ | NEUTRAL | EXEC_CAUTION | — |
| 43 | **PLTR** | CALL | Information Technology | PLTR261218C00210000 (60) | 192.59 → 411.50 / 119.62 | 5.1% | +88 / -42 / -100 | 0.53 | 0.32 ✗ | ALIGNED | EXEC_CAUTION | — |
| 44 | **AVO** | CALL | Consumer Staples | AVO261120C00012500 (41) | 12.96 → 16.77 / 11.69 | 9.5% | +69 / -31 / -83 | 0.54 | 0.40 ✗ | AGAINST | EXECUTE | — |
| 45 | **GLD** | CALL | ETF | GLD261120C00400000 (41) | 391.69 → 460.83 / 368.64 | 1.9% | +73 / -33 / -87 | 0.54 | 0.35 ✗ | NEUTRAL | EXECUTE | — |
| 46 | **ZS** | CALL | Information Technology | ZS261120C00220000 (41) | 214.64 → 427.00 / 143.85 | 6.8% | +81 / -16 / -98 | 0.55 | 0.36 ✗ | ALIGNED | EXEC_CAUTION | — |
| 47 | **CMG** | PUT | Consumer Discretionary | CMG261120P00032500 (41) | 32.01 → 10.77 / 39.09 | 3.4% | +65 / -18 / -91 | 0.58 | 0.43 ✗ | NEUTRAL | EXECUTE | — |
| 48 | **WHD** | CALL | Energy | WHD261120C00065000 (41) | 65.20 → 95.80 / 55.00 | 7.2% | +69 / -28 / -94 | 0.58 | 0.34 ✗ | ALIGNED | BLOCKED | — |
| 49 | **ORCL** | PUT | Information Technology | ORCL261120P00140000 (41) | 139.54 → 46.06 / 170.70 | 2.2% | +65 / -24 / -90 | 0.58 | 0.40 ✗ | AGAINST | EXECUTE | — |
| 50 | **ATO** | PUT | Utilities | ATO261016P00160000 (16) | 156.42 → 93.42 / 177.42 | 13.0% | +71 / -26 / -100 | 0.58 | 0.40 ✗ | ALIGNED | BLOCKED | — |
| 51 | **SBAC** | PUT | Real Estate | SBAC261120P00175000 (41) | 166.12 → 81.79 / 194.23 | 14.9% | +70 / -29 / -96 | 0.58 | 0.42 ✗ | ALIGNED | EXEC_CAUTION | — |
| 52 | **CORZ** | PUT | Information Technology | CORZ261218P00019000 (60) | 18.12 → 1.68 / 23.60 | 10.7% | +59 / -29 / -83 | 0.58 | 0.37 ✗ | AGAINST | EXEC_CAUTION | — |
| 53 | **CMPS** | PUT | Health Care | CMPS261120P00015000 (41) | 13.09 → 12.09 / 16.19 | 7.3% | +46 / -18 / -69 | 0.60 | 0.33 ✗ | NEUTRAL | BLOCKED | — |
| 54 | **NVS** | PUT | Health Care | NVS261120P00145000 (41) | 143.57 → 80.84 / 164.48 | 5.0% | +66 / -27 / -98 | 0.60 | 0.37 ✗ | NEUTRAL | EXECUTE | — |
| 55 | **GTES** | PUT | Industrials | GTES261120P00028000 (41) | 26.26 → 14.02 / 30.34 | 9.7% | +46 / -20 / -83 | 0.65 | 0.35 ✗ | NEUTRAL | BLOCKED | — |
| 56 | **AA** | PUT | Materials | AA261218P00045000 (60) | 42.68 → 5.57 / 55.05 | 6.8% | +44 / -21 / -89 | 0.67 | 0.37 ✗ | ALIGNED | EXECUTE | — |
| 57 | **PFE** | CALL | Health Care | PFE261218C00029000 (60) | 28.41 → 39.99 / 24.55 | 5.8% | +44 / -20 / -96 | 0.68 | 0.32 ✗ | NEUTRAL | EXECUTE | — |

### Tier C — positive grid EV, outside A/B (3)

| # | Ticker | Dir | Sector | Contract (DTE) | Spot → Target / Inval | Spread | Reach / Flat / Inval | p\* | Legacy p | Macro | EIL | Flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **NLY** | CALL | Real Estate | NLY261218C00020000 (60) | 20.60 → 20.75 / 20.55 | 19.1% | +70 / +2 / -2 | 0.03 | 0.42 ✓ | AGAINST | BLOCKED | DEGENERATE_GEOMETRY; p* not meaningful; STOCK_LIKE; compare with shares |
| 2 | **OMER** | CALL | Health Care | OMER261016C00022000 (16) | 20.13 → 46.41 / 11.37 | 20.0% | +510 / -100 / -100 | 0.16 | 0.09 ✗ | NEUTRAL | BLOCKED | OUTLIER; FORECAST_ABOVE_IV |
| 3 | **HMC** | CALL | Consumer Discretionary | HMC261016C00032500 (16) | 32.19 → 40.00 / 29.59 | 20.0% | +304 / -91 / -100 | 0.25 | 0.30 ✓ | NEUTRAL | BLOCKED | OUTLIER |

## 4. Review flags

| Flag | Meaning | What to check | Rows |
|---|---|---|---|
| DEGENERATE_GEOMETRY | Target or invalidation within 1% of spot | The thesis geometry is not a trade; p* and the invalidation payoff are not meaningful until the Thesis owner publishes a real level | PAYX, TSM, SNY, AMTM, ABT, BWA, RIO, IWM, NLY |
| OUTLIER | Reachable payoff above 300% | Forecast vol versus contract IV; the number is forecast-driven and ALG-10 is unvalidated | WBD, SNEX, OMER, HMC |
| STOCK_LIKE | Positive return even if spot stays flat: deep in the money | Compare with holding the shares; the option is a stock substitute, not convexity | HON, AKAM, NLY |
| FORECAST_ABOVE_IV | Forecast vol more than 15 points above IV | If the forecast is biased high, the reachable payoff shrinks first | WBD, CRWV, SMCI, MRNA, MSTR, QBTS, AMKR, RKLB, IBM, NUAI, CRCL, W, CRDO, IREN, OMER |

## 5. Macro alignment of the Tier A list

| Alignment | Tickers | Reading |
|---|---|---|
| ALIGNED | WBD C, MGY C, CRWV C | Sector on the preferred list for a call, or on the avoid list for a put |
| NEUTRAL | HON C, PAYX C, SNY C, AMTM C, TSLA P, ABT C, ARWR C, BWA C, AAP C, KBH C, IBIT P | Sector on neither list; the calls/puts rule still applies |
| AGAINST | SNEX C, TSM P, MRVL P, CRWD P, AKAM P, OKLO C, RIO C, BTI C, SMCI P, BMNR P, IWM C, BEN C | Call in an avoid sector, put against tech leadership, or a broad index call the packet forbids |

## 6. Morning checklist (every row, before any order)

| Step | Check | Pass condition |
|---|---|---|
| 1 | Requote the selected contract | Two-sided, provider timestamp present, spread ≤ 15% of mid |
| 2 | Spot versus trigger | CALL: spot above trigger_price · PUT: spot below trigger_price (trigger_primary in the CSV) |
| 3 | Invalidation | Still on the correct side of spot; if crossed overnight the thesis is INVALIDATED, not re-entered |
| 4 | Macro overlay | Read the alignment and rule; AGAINST is information for the reviewer, not a kill |
| 5 | Review flag | Resolve any flag in section 4 before sizing |
| 6 | Exit policy | Target or invalidation first; time-stop at the horizon hold (Day 5 or Day 10); hard last exit at Day 20 or expiry minus buffer |
| 7 | Size | HUMAN DETERMINED; the packet's 0.63 / 0.56 / 0.49 modifiers are advisory text only |

## 7. What this plan is not

| Limit | Why it matters |
|---|---|
| Not a pipeline output | Built from the book by a research harness; the pipeline's own morning validation still runs unchanged |
| Not a validated probability | p\* is what you must believe; the legacy probability shown beside it is uncalibrated |
| Not a validated forecast | Reachable payoffs scale with the unvalidated vol forecast; a 15% error moves the Tier A count by roughly 2× |
| Not a fill | EOD quotes are wide; the morning requote decides executability |
| Not a size | Capital and Kelly are outside AVSHUNTER by design |