# Trading plan — run 20260925_061649 MORNING · US session of 2026-09-25

Research plan built read-only from the completed evening book. State EXPLORATORY_NO_AUTHORITY. Sizing HUMAN DETERMINED. Nothing here alters the pipeline or the run book.
Generated 2026-09-25 14:34Z · source CSV `trading_plan_20260925_061649_v2.csv`

## 1. Summary

| Item | Value |
|---|---|
| Rows in the evening book | 1,549 (all MANUAL_REVIEW or BLOCKED; GO verdicts arise only at morning validation) |
| Candidate trades listed | 91 (49 CALL, 42 PUT) |
| Tier A — asymmetric, executable, break-even p ≤ 0.40 | **22** |
| Tier B — asymmetric, executable, break-even p > 0.40 | 56 |
| Tier C — positive grid EV outside A/B | 13 |
| Tier A macro alignment | 3 aligned · 4 neutral · 15 against |
| Tier A rows with a review flag | 12 |

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

### Tier A — asymmetric, executable, break-even p ≤ 0.40 (22)

| # | Ticker | Dir | Sector | Contract (DTE) | Spot → Target / Inval | Spread | Reach / Flat / Inval | p\* | Legacy p | Macro | EIL | Flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **RYN** | CALL | Real Estate | RYN261120C00017500 (56) | 19.06 → 19.07 / 19.05 | 5.4% | +44 / +2 / +2 | -0.04 | 0.41 ✓ | AGAINST | BLOCKED | DEGENERATE_GEOMETRY; p* not meaningful; STOCK_LIKE; compare with shares |
| 2 | **CLX** | CALL | Consumer Staples | CLX261120C00075000 (56) | 81.80 → 82.01 / 81.73 | 8.0% | +42 / -7 / -8 | 0.15 | 0.48 ✓ | AGAINST | BLOCKED | DEGENERATE_GEOMETRY; p* not meaningful |
| 3 | **HON** | CALL | Industrials | HON261218C00195000 (60) | 211.79 → 256.22 / 196.98 | 9.5% | +54 / +24 / -10 | 0.16 | 0.31 ✓ | NEUTRAL | BLOCKED | STOCK_LIKE; compare with shares |
| 4 | **PEP** | CALL | Consumer Staples | PEP261030C00125000 (35) | 128.15 → 128.66 / 127.98 | 13.7% | +96 / -16 / -18 | 0.16 | 0.40 ✓ | AGAINST | EXEC_CAUTION | DEGENERATE_GEOMETRY; p* not meaningful |
| 5 | **TSM** | PUT | Information Technology | TSM261120P00450000 (41) | 451.15 → 445.96 / 452.88 | 1.8% | +125 / -32 / -35 | 0.22 | 0.32 ✓ | AGAINST | EXECUTE | DEGENERATE_GEOMETRY; p* not meaningful |
| 6 | **SNY** | CALL | Health Care | SNY261218C00040000 (60) | 40.94 → 41.04 / 40.91 | 7.5% | +54 / -19 / -19 | 0.26 | 0.34 ✓ | NEUTRAL | EXEC_CAUTION | DEGENERATE_GEOMETRY; p* not meaningful |
| 7 | **MRVL** | PUT | Information Technology | MRVL261120P00260000 (41) | 258.95 → 237.80 / 266.00 | 3.1% | +87 / -19 / -32 | 0.27 | 0.33 ✓ | AGAINST | EXEC_CAUTION | — |
| 8 | **BTI** | CALL | Consumer Staples | BTI261218C00055000 (60) | 56.02 → 61.18 / 54.30 | 7.5% | +113 / -11 / -44 | 0.28 | 0.35 ✓ | AGAINST | EXECUTE | — |
| 9 | **FANG** | CALL | Energy | FANG261120C00185000 (56) | 189.01 → 205.51 / 183.51 | 12.9% | +91 / -15 / -37 | 0.29 | 0.49 ✓ | ALIGNED | EXEC_CAUTION | — |
| 10 | **MS** | CALL | Financials | MS261106C00190000 (42) | 196.32 → 201.03 / 194.75 | 14.8% | +67 / -24 / -31 | 0.31 | 0.49 ✓ | AGAINST | EXECUTE | DEGENERATE_GEOMETRY; p* not meaningful |
| 11 | **ARM** | PUT | Information Technology | ARM261120P00310000 (41) | 306.34 → 214.42 / 336.98 | 5.3% | +98 / -11 / -46 | 0.32 | 0.41 ✓ | AGAINST | EXEC_CAUTION | — |
| 12 | **RIO** | CALL | Materials | RIO261218C00095000 (60) | 94.47 → 97.05 / 93.61 | 7.4% | +66 / -25 / -32 | 0.33 | 0.33 ✓ | AGAINST | BLOCKED | DEGENERATE_GEOMETRY; p* not meaningful |
| 13 | **SMCI** | PUT | Information Technology | SMCI261218P00040000 (60) | 41.51 → 37.94 / 42.70 | 8.3% | +62 / -22 / -30 | 0.33 | 0.09 ✗ | AGAINST | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 14 | **XLK** | PUT | ETF | XLK261218P00195000 (60) | 194.71 → 188.80 / 196.68 | 12.2% | +71 / -27 / -36 | 0.34 | 0.31 ✗ | AGAINST | BLOCKED | — |
| 15 | **CRWV** | CALL | Information Technology | CRWV261120C00100000 (41) | 90.13 → 157.87 / 67.55 | 4.0% | +180 / -46 / -97 | 0.35 | 0.58 ✓ | ALIGNED | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 16 | **QCOM** | PUT | Information Technology | QCOM261218P00200000 (60) | 194.26 → 178.20 / 199.61 | 9.5% | +50 / -15 / -27 | 0.35 | 0.39 ✓ | AGAINST | EXEC_CAUTION | — |
| 17 | **MNST** | CALL | Consumer Staples | MNST261120C00043000 (56) | 42.67 → 44.12 / 42.19 | 15.0% | +46 / -15 / -26 | 0.36 | 0.35 ✗ | AGAINST | BLOCKED | — |
| 18 | **MRNA** | CALL | Health Care | MRNA261120C00220000 (41) | 194.82 → 621.30 / 52.66 | 3.2% | +167 / -34 / -100 | 0.37 | 0.31 ✗ | NEUTRAL | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 19 | **BMNR** | PUT | Information Technology | BMNR261120P00028000 (41) | 28.03 → 25.54 / 28.86 | 4.4% | +60 / -27 / -37 | 0.38 | 0.34 ✗ | AGAINST | EXEC_CAUTION | — |
| 20 | **RKLB** | PUT | Information Technology | RKLB261218P00080000 (60) | 73.61 → 33.95 / 86.83 | 3.3% | +93 / -18 / -59 | 0.39 | 0.52 ✓ | AGAINST | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 21 | **CLF** | PUT | Materials | CLF261030P00013000 (35) | 12.50 → 10.69 / 13.11 | 11.1% | +59 / -18 / -39 | 0.39 | 0.09 ✗ | ALIGNED | EXEC_CAUTION | — |
| 22 | **IBIT** | PUT | ETF | IBIT261120P00048000 (41) | 47.81 → 43.58 / 49.22 | 0.7% | +69 / -24 / -44 | 0.39 | 0.34 ✗ | NEUTRAL | EXECUTE | — |

### Tier B — asymmetric, executable, break-even p > 0.40 (56)

| # | Ticker | Dir | Sector | Contract (DTE) | Spot → Target / Inval | Spread | Reach / Flat / Inval | p\* | Legacy p | Macro | EIL | Flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **APLD** | CALL | Information Technology | APLD261120C00030000 (41) | 27.06 → 38.07 / 23.39 | 8.6% | +122 / -46 / -83 | 0.40 | 0.58 ✓ | ALIGNED | EXEC_CAUTION | — |
| 2 | **LOAR** | CALL | Industrials | LOAR261016C00070000 (21) | 65.43 → 75.95 / 61.92 | 12.2% | +116 / -39 / -81 | 0.41 | 0.41 ✗ | NEUTRAL | EXEC_CAUTION | — |
| 3 | **HOOD** | PUT | Financials | HOOD261120P00120000 (41) | 120.82 → 103.06 / 126.74 | 2.2% | +64 / -25 / -45 | 0.41 | 0.33 ✗ | ALIGNED | EXEC_CAUTION | — |
| 4 | **TSLA** | PUT | Consumer Discretionary | TSLA261120P00380000 (41) | 377.94 → 351.66 / 386.70 | 1.6% | +61 / -29 / -43 | 0.41 | 0.09 ✗ | NEUTRAL | EXECUTE | — |
| 5 | **ZS** | CALL | Information Technology | ZS261120C00220000 (41) | 214.64 → 427.00 / 143.85 | 5.6% | +136 / -4 / -99 | 0.42 | 0.36 ✗ | ALIGNED | EXEC_CAUTION | — |
| 6 | **TEL** | PUT | Information Technology | TEL261120P00230000 (56) | 213.67 → 188.75 / 221.97 | 12.0% | +41 / -8 / -30 | 0.42 | 0.33 ✗ | AGAINST | BLOCKED | — |
| 7 | **APD** | CALL | Materials | APD261120C00270000 (56) | 284.49 → 299.85 / 279.37 | 15.0% | +42 / -14 / -30 | 0.42 | 0.46 ✓ | AGAINST | BLOCKED | — |
| 8 | **SLV** | CALL | ETF | SLV261218C00060000 (60) | 57.62 → 77.12 / 51.12 | 2.9% | +122 / -39 / -88 | 0.42 | 0.58 ✓ | NEUTRAL | EXECUTE | — |
| 9 | **ASTS** | PUT | Information Technology | ASTS261120P00065000 (41) | 61.06 → 19.00 / 75.08 | 5.2% | +108 / -25 / -77 | 0.42 | 0.35 ✗ | AGAINST | EXEC_CAUTION | — |
| 10 | **RCAT** | CALL | Information Technology | RCAT261120C00007000 (41) | 6.80 → 8.09 / 6.37 | 11.9% | +74 / -33 / -54 | 0.42 | 0.35 ✗ | ALIGNED | WATCHLIST | FORECAST_ABOVE_IV |
| 11 | **IREN** | CALL | Information Technology | IREN261120C00050000 (41) | 46.15 → 87.64 / 32.32 | 2.4% | +126 / -22 / -95 | 0.43 | 0.30 ✗ | ALIGNED | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 12 | **OXY** | CALL | Energy | OXY261218C00060000 (60) | 58.05 → 71.22 / 53.66 | 7.5% | +101 / -27 / -75 | 0.43 | 0.32 ✗ | ALIGNED | EXECUTE | — |
| 13 | **HIMS** | CALL | Health Care | HIMS261120C00032000 (41) | 29.28 → 44.40 / 24.24 | 6.5% | +118 / -43 / -88 | 0.43 | 0.52 ✓ | NEUTRAL | EXEC_CAUTION | — |
| 14 | **AMKR** | PUT | Energy | AMKR261218P00055000 (60) | 52.69 → 24.07 / 62.23 | 12.8% | +88 / -27 / -67 | 0.43 | 0.52 ✓ | AGAINST | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 15 | **MSTR** | PUT | Information Technology | MSTR261218P00160000 (60) | 161.61 → 132.87 / 171.19 | 1.9% | +56 / -25 / -42 | 0.43 | 0.34 ✗ | AGAINST | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 16 | **STM** | PUT | Information Technology | STM261120P00050000 (41) | 51.58 → 35.20 / 57.04 | 5.3% | +100 / -40 / -77 | 0.43 | 0.54 ✓ | AGAINST | EXEC_CAUTION | — |
| 17 | **DRI** | CALL | Consumer Discretionary | DRI261120C00195000 (56) | 207.24 → 222.81 / 202.05 | 14.5% | +41 / -11 / -32 | 0.44 | 0.20 ✗ | NEUTRAL | BLOCKED | — |
| 18 | **RGTI** | PUT | Information Technology | RGTI261120P00017000 (41) | 16.50 → 7.91 / 19.36 | 6.3% | +96 / -31 / -74 | 0.44 | 0.58 ✓ | AGAINST | EXEC_CAUTION | — |
| 19 | **QBTS** | CALL | Information Technology | QBTS261120C00018000 (41) | 17.48 → 22.49 / 15.81 | 8.6% | +80 / -32 / -64 | 0.45 | 0.52 ✓ | ALIGNED | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 20 | **FSLY** | PUT | Information Technology | FSLY261218P00030000 (60) | 26.68 → 12.73 / 31.33 | 10.1% | +63 / -24 / -52 | 0.45 | 0.43 ✗ | AGAINST | BLOCKED | — |
| 21 | **OKLO** | CALL | Utilities | OKLO261120C00040000 (41) | 38.29 → 50.02 / 34.38 | 10.7% | +94 / -47 / -77 | 0.45 | 0.35 ✗ | AGAINST | EXEC_CAUTION | — |
| 22 | **LPTH** | CALL | Information Technology | LPTH261120C00010000 (56) | 10.06 → 14.14 / 8.70 | 12.1% | +66 / -18 / -55 | 0.46 | 0.55 ✓ | ALIGNED | WATCHLIST | — |
| 23 | **PZZA** | CALL | Consumer Discretionary | PZZA261120C00020000 (41) | 20.22 → 22.05 / 19.61 | 2.1% | +40 / -20 / -34 | 0.46 | 0.34 ✗ | NEUTRAL | BLOCKED | — |
| 24 | **AVGO** | CALL | Information Technology | AVGO261120C00360000 (41) | 350.36 → 394.00 / 335.81 | 2.8% | +72 / -34 / -63 | 0.47 | 0.29 ✗ | ALIGNED | EXECUTE | — |
| 25 | **WULF** | PUT | Information Technology | WULF261120P00017000 (41) | 16.29 → 6.18 / 19.66 | 3.7% | +87 / -33 / -76 | 0.47 | 0.37 ✗ | AGAINST | EXEC_CAUTION | — |
| 26 | **GOOGL** | PUT | Communication Services | GOOGL261120P00340000 (41) | 342.36 → 216.00 / 384.48 | 6.6% | +99 / -32 / -91 | 0.48 | 0.35 ✗ | AGAINST | EXECUTE | — |
| 27 | **AAPL** | PUT | Information Technology | AAPL261120P00335000 (41) | 335.92 → 307.66 / 345.34 | 3.7% | +58 / -26 / -54 | 0.48 | 0.31 ✗ | AGAINST | EXECUTE | — |
| 28 | **SOFI** | CALL | Financials | SOFI261218C00018000 (60) | 16.80 → 21.42 / 15.26 | 3.2% | +82 / -38 / -74 | 0.48 | 0.35 ✗ | AGAINST | EXECUTE | — |
| 29 | **TRGP** | CALL | Energy | TRGP261120C00280000 (56) | 283.15 → 367.36 / 255.08 | 12.7% | +83 / -16 / -79 | 0.49 | 0.17 ✗ | ALIGNED | BLOCKED | — |
| 30 | **LOGI** | PUT | Information Technology | LOGI261218P00100000 (60) | 99.56 → 69.98 / 109.42 | 6.1% | +75 / -25 / -72 | 0.49 | 0.39 ✗ | AGAINST | BLOCKED | — |
| 31 | **PANW** | CALL | Information Technology | PANW261218C00440000 (60) | 389.92 → 620.55 / 313.05 | 12.7% | +93 / -40 / -94 | 0.50 | 0.34 ✗ | ALIGNED | WATCHLIST | — |
| 32 | **CDE** | CALL | Materials | CDE261120C00020000 (41) | 18.94 → 32.25 / 14.51 | 12.9% | +99 / -50 / -98 | 0.50 | 0.34 ✗ | AGAINST | EXEC_CAUTION | — |
| 33 | **W** | PUT | Consumer Discretionary | W261218P00100000 (60) | 97.67 → 35.76 / 118.31 | 11.7% | +80 / -34 / -80 | 0.50 | 0.29 ✗ | NEUTRAL | EXEC_CAUTION | FORECAST_ABOVE_IV |
| 34 | **XOM** | CALL | Energy | XOM261218C00165000 (60) | 162.14 → 201.29 / 149.09 | 5.3% | +77 / -26 / -80 | 0.51 | 0.33 ✗ | ALIGNED | EXECUTE | — |
| 35 | **DIOD** | PUT | Information Technology | DIOD261218P00105000 (60) | 94.74 → 48.63 / 110.11 | 14.5% | +60 / -23 / -62 | 0.51 | 0.35 ✗ | AGAINST | BLOCKED | — |
| 36 | **PM** | CALL | Consumer Staples | PM261218C00195000 (60) | 191.50 → 222.97 / 181.01 | 14.1% | +69 / -32 / -71 | 0.51 | 0.17 ✗ | AGAINST | EXEC_CAUTION | — |
| 37 | **IBM** | PUT | Information Technology | IBM261218P00220000 (60) | 227.06 → 152.80 / 251.81 | 12.3% | +73 / -36 / -78 | 0.51 | 0.35 ✗ | AGAINST | EXECUTE | FORECAST_ABOVE_IV |
| 38 | **FERG** | CALL | Industrials | FERG261120C00220000 (56) | 220.17 → 244.29 / 212.13 | 14.1% | +42 / -19 / -44 | 0.52 | 0.13 ✗ | NEUTRAL | BLOCKED | — |
| 39 | **XLF** | PUT | ETF | XLF261120P00055000 (41) | 54.53 → 42.32 / 58.60 | 4.2% | +88 / -26 / -96 | 0.52 | 0.42 ✗ | ALIGNED | EXEC_CAUTION | — |
| 40 | **LH** | CALL | Health Care | LH261120C00300000 (56) | 308.95 → 352.78 / 294.34 | 14.2% | +44 / -12 / -51 | 0.53 | 0.16 ✗ | NEUTRAL | BLOCKED | — |
| 41 | **RL** | CALL | Consumer Discretionary | RL261120C00350000 (56) | 351.86 → 414.65 / 330.93 | 14.2% | +49 / -16 / -55 | 0.53 | 0.32 ✗ | NEUTRAL | BLOCKED | — |
| 42 | **WMT** | PUT | Consumer Staples | WMT261218P00110000 (60) | 107.59 → 79.75 / 116.87 | 6.0% | +69 / -27 / -77 | 0.53 | 0.18 ✗ | ALIGNED | EXECUTE | — |
| 43 | **COP** | CALL | Energy | COP261218C00135000 (60) | 129.34 → 173.23 / 114.71 | 14.0% | +80 / -36 / -92 | 0.53 | 0.18 ✗ | ALIGNED | EXECUTE | — |
| 44 | **CRL** | CALL | Health Care | CRL261120C00300000 (56) | 294.44 → 495.62 / 227.38 | 13.8% | +77 / -19 / -94 | 0.55 | 0.29 ✗ | NEUTRAL | BLOCKED | — |
| 45 | **GLD** | CALL | ETF | GLD261120C00400000 (41) | 391.69 → 460.83 / 368.64 | 0.9% | +72 / -34 / -87 | 0.55 | 0.35 ✗ | NEUTRAL | EXECUTE | — |
| 46 | **SHOP** | CALL | Information Technology | SHOP261120C00145000 (41) | 145.16 → 234.83 / 115.27 | 6.5% | +69 / -18 / -88 | 0.56 | 0.35 ✗ | ALIGNED | EXEC_CAUTION | — |
| 47 | **NVS** | PUT | Health Care | NVS261120P00145000 (41) | 143.57 → 80.84 / 164.48 | 7.4% | +78 / -23 / -98 | 0.56 | 0.37 ✗ | NEUTRAL | EXECUTE | — |
| 48 | **VST** | PUT | Utilities | VST261120P00135000 (41) | 137.94 → 80.79 / 156.99 | 11.0% | +65 / -31 / -86 | 0.57 | 0.18 ✗ | ALIGNED | EXECUTE | — |
| 49 | **INTC** | CALL | Information Technology | INTC261218C00140000 (60) | 127.39 → 254.14 / 85.14 | 1.7% | +69 / -25 / -97 | 0.58 | 0.34 ✗ | ALIGNED | EXEC_CAUTION | — |
| 50 | **ORCL** | PUT | Information Technology | ORCL261120P00140000 (41) | 139.54 → 46.06 / 170.70 | 3.6% | +66 / -24 / -90 | 0.58 | 0.40 ✗ | AGAINST | EXECUTE | — |
| 51 | **CORZ** | PUT | Information Technology | CORZ261218P00019000 (60) | 18.12 → 1.68 / 23.60 | 7.6% | +58 / -28 / -81 | 0.58 | 0.37 ✗ | AGAINST | EXEC_CAUTION | — |
| 52 | **RMBS** | CALL | Information Technology | RMBS261120C00120000 (56) | 104.55 → 178.20 / 80.00 | 12.5% | +62 / -28 / -89 | 0.59 | 0.36 ✗ | ALIGNED | BLOCKED | — |
| 53 | **GNRC** | PUT | Industrials | GNRC261218P00200000 (60) | 198.05 → 96.54 / 231.89 | 14.5% | +49 / -21 / -73 | 0.60 | 0.61 ✓ | NEUTRAL | BLOCKED | — |
| 54 | **VICR** | CALL | Information Technology | VICR261120C00280000 (56) | 276.06 → 586.56 / 172.56 | 14.5% | +61 / -24 / -94 | 0.61 | 0.37 ✗ | ALIGNED | BLOCKED | — |
| 55 | **EWG** | PUT | ETF | EWG261218P00042000 (60) | 41.87 → 32.93 / 44.85 | 7.4% | +54 / -26 / -85 | 0.61 | 0.42 ✗ | NEUTRAL | BLOCKED | — |
| 56 | **ALL** | PUT | Financials | ALL261120P00240000 (56) | 227.17 → 82.51 / 275.39 | 14.2% | +44 / -18 / -96 | 0.69 | 0.43 ✗ | ALIGNED | BLOCKED | — |

### Tier C — positive grid EV, outside A/B (13)

| # | Ticker | Dir | Sector | Contract (DTE) | Spot → Target / Inval | Spread | Reach / Flat / Inval | p\* | Legacy p | Macro | EIL | Flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **CAPR** | PUT | Health Care | CAPR261218P00006000 (60) | 8.57 → 1.28 / 11.00 | 13.6% | +413 / +294 / +244 | -1.44 | 0.57 ✓ | NEUTRAL | BLOCKED | STOCK_LIKE; compare with shares; OUTLIER |
| 2 | **AKAM** | PUT | Information Technology | AKAM261106P00119000 (60) | 110.41 → 60.52 / 127.04 | 23.0% | +268 / +135 / +51 | -0.24 | 0.46 ✓ | AGAINST | BLOCKED | STOCK_LIKE; compare with shares |
| 3 | **RTX** | CALL | Industrials | RTX261030C00195000 (41) | 188.61 → 193.32 / 187.04 | 28.2% | +132 / +11 / -2 | 0.02 | 0.35 ✓ | NEUTRAL | EXEC_CAUTION | DEGENERATE_GEOMETRY; p* not meaningful; STOCK_LIKE; compare with shares |
| 4 | **EXR** | CALL | Real Estate | EXR261016C00125000 (60) | 132.23 → 132.89 / 132.01 | 28.9% | +68 / -4 / -6 | 0.07 | 0.35 ✓ | AGAINST | BLOCKED | DEGENERATE_GEOMETRY; p* not meaningful |
| 5 | **VKTX** | PUT | Health Care | VKTX261120P00032500 (41) | 36.75 → 26.98 / 43.96 | 21.5% | +447 / +73 / -44 | 0.09 | 0.41 ✓ | NEUTRAL | WATCHLIST | STOCK_LIKE; compare with shares; OUTLIER; FORECAST_ABOVE_IV |
| 6 | **QURE** | CALL | Health Care | QURE261016C00040000 (41) | 38.32 → 42.82 / 36.82 | 21.3% | +124 / -0 / -14 | 0.10 | 0.51 ✓ | NEUTRAL | BLOCKED | — |
| 7 | **MAA** | CALL | Real Estate | MAA261016C00110000 (60) | 117.26 → 119.00 / 116.68 | 27.9% | +53 / -2 / -6 | 0.11 | 0.40 ✓ | AGAINST | BLOCKED | DEGENERATE_GEOMETRY; p* not meaningful |
| 8 | **COMP** | CALL | Information Technology | COMP261016C00009000 (41) | 9.29 → 9.99 / 9.05 | 20.7% | +93 / -5 / -20 | 0.18 | 0.42 ✓ | ALIGNED | BLOCKED | — |
| 9 | **FLEX** | CALL | Information Technology | FLEX261016C00115000 (41) | 112.40 → 142.85 / 102.25 | 25.6% | +142 / +2 / -55 | 0.28 | 0.55 ✓ | ALIGNED | EXEC_CAUTION | STOCK_LIKE; compare with shares |
| 10 | **ADI** | PUT | Information Technology | ADI261106P00385000 (42) | 382.61 → 330.60 / 398.36 | 15.2% | +81 / -4 / -37 | 0.31 | 0.31 ✓ | AGAINST | BLOCKED | — |
| 11 | **D** | PUT | Utilities | D261016P00060000 (60) | 60.40 → 29.23 / 70.79 | 18.2% | +162 / +15 / -98 | 0.38 | 0.41 ✓ | ALIGNED | BLOCKED | STOCK_LIKE; compare with shares |
| 12 | **CPRT** | PUT | Industrials | CPRT261016P00027500 (60) | 28.04 → 8.28 / 34.62 | 24.0% | +157 / +10 / -98 | 0.38 | 0.42 ✓ | NEUTRAL | BLOCKED | STOCK_LIKE; compare with shares |
| 13 | **LPLA** | PUT | Financials | LPLA261120P00320000 (56) | 302.76 → 74.04 / 379.00 | 15.9% | +69 / +6 / -88 | 0.56 | 0.44 ✗ | ALIGNED | BLOCKED | STOCK_LIKE; compare with shares |

## 4. Review flags

| Flag | Meaning | What to check | Rows |
|---|---|---|---|
| DEGENERATE_GEOMETRY | Target or invalidation within 1% of spot | The thesis geometry is not a trade; p* and the invalidation payoff are not meaningful until the Thesis owner publishes a real level | RYN, CLX, PEP, TSM, SNY, MS, RIO, RTX, EXR, MAA |
| OUTLIER | Reachable payoff above 300% | Forecast vol versus contract IV; the number is forecast-driven and ALG-10 is unvalidated | CAPR, VKTX |
| STOCK_LIKE | Positive return even if spot stays flat: deep in the money | Compare with holding the shares; the option is a stock substitute, not convexity | RYN, HON, CAPR, AKAM, RTX, VKTX, FLEX, D, CPRT, LPLA |
| FORECAST_ABOVE_IV | Forecast vol more than 15 points above IV | If the forecast is biased high, the reachable payoff shrinks first | SMCI, CRWV, MRNA, RKLB, RCAT, IREN, AMKR, MSTR, QBTS, W, IBM, VKTX |

## 5. Macro alignment of the Tier A list

| Alignment | Tickers | Reading |
|---|---|---|
| ALIGNED | FANG C, CRWV C, CLF P | Sector on the preferred list for a call, or on the avoid list for a put |
| NEUTRAL | HON C, SNY C, MRNA C, IBIT P | Sector on neither list; the calls/puts rule still applies |
| AGAINST | RYN C, CLX C, PEP C, TSM P, MRVL P, BTI C, MS C, ARM P, RIO C, SMCI P, XLK P, QCOM P, MNST C, BMNR P, RKLB P | Call in an avoid sector, put against tech leadership, or a broad index call the packet forbids |

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