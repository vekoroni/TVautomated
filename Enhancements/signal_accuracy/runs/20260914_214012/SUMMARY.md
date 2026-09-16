# Signal accuracy audit — run 20260914_214012

Session 2026-09-14 · code `avs-baseline-20260906-48-g0810908-dirty` · generated 2026-09-15T06:00:26+00:00

Each published field was recomputed independently from raw inputs (point-in-time OHLCV in `historical_prices.sqlite`, raw MarketData chain observations) and compared across stages. Read-only; nothing in the pipeline was modified.

## Headline

- Tickers: discovery 1578, options 1449, directional with a contract 1312, trigger-ready 150
- Checks run: 97,891 → PASS 94,120, WARN 2,077, FAIL 1,238, NOT_EVALUABLE 416, INFO 40
- Tickers with at least one FAIL: 384
- **Clean** directional candidates with a contract (zero FAILs): **1065**; of which trigger-ready: **147**

## Checks ranked by failure rate

| Check | Evaluated | FAIL | WARN | Fail rate | Typical reason | Sample tickers |
|---|---:|---:|---:|---:|---|---|
| Z01_ZERO_AS_MISSING | 711 | 711 | 0 | 100.0% | invalidation published as 0.0 (missing value disguised as a price) | ABT,ACHC,ACN,ADC,ADEA,ADSK,AEHL,AGCO,AGI,AMRX,APA,APG |
| G01_INVALIDATION_PRESENT | 338 | 338 | 0 | 100.0% | CALL candidate has no invalidation level | ADC,AGCO,APA,ARKK,ASND,ATRC,AVTR,BABA,BBW,BBY,BE,BEPC |
| G04_TARGET_PRESENT | 378 | 38 | 340 | 10.1% | CALL candidate has no target | AAP,ADC,AEHL,AGCO,ALMS,AMRC,APA,ARKK,ASND,ATRC,AVTR,BABA |
| R04_DELTA_VS_INDEPENDENT_BS | 2624 | 116 | 136 | 4.4% | published delta off by 0.06 vs BS | ACIW,ADNT,AESI,AGRO,ALMS,AMH,AOS,ASC,ATEC,BBNX,BKKT,BLMN |
| G05_TARGET_POSITIVE | 2258 | 35 | 0 | 1.6% | target price is not positive | AAP,AEHL,ALMS,AMRC,BIRK,BRBR,BYND,CAPR,CAVA,CHRW,CIFR,COLL |
| C01_STRIKE_MATCHES_SYMBOL | 2624 | 0 | 0 | 0.0% |  |  |
| C02_EXPIRY_MATCHES_SYMBOL | 2624 | 0 | 0 | 0.0% |  |  |
| C03_SIDE_MATCHES_DIRECTION | 2624 | 0 | 0 | 0.0% |  |  |
| C04_CALENDAR_DTE | 2624 | 0 | 0 | 0.0% |  |  |
| C05_SESSION_DTE | 2624 | 0 | 0 | 0.0% |  |  |
| C06_MID_RECOMPUTE | 2624 | 0 | 0 | 0.0% |  |  |
| C07_SPREAD_FRACTION | 3733 | 0 | 0 | 0.0% |  |  |
| C08_SPREAD_PERCENT | 3733 | 0 | 0 | 0.0% |  |  |
| C10_DELTA_SIGN | 2624 | 0 | 0 | 0.0% |  |  |
| C11_QUOTE_FROM_SESSION | 2624 | 0 | 0 | 0.0% |  |  |
| G02_INVALIDATION_SIDE | 2298 | 0 | 0 | 0.0% |  |  |
| G03_INVALIDATION_DISTANCE_ATR | 2298 | 0 | 240 | 0.0% | invalidation 0.1 ATR from spot | AAP,AEE,ALGM,ALMS,AMPL,APAM,AROC,ASST,AVA,AVGO,AXS,BBIO |
| G06_TARGET_SIDE | 2258 | 0 | 0 | 0.0% |  |  |
| G07_TARGET_DISTANCE_ATR | 2223 | 0 | 379 | 0.0% | target 17.1 ATR from spot | ABNB,ACM,AEP,AGIO,ALLE,AMCR,AMCX,AMGN,AMPL,ANF,AON,AOS |
| R00_CONTRACT_IN_RAW_CHAIN | 2624 | 0 | 0 | 0.0% |  |  |
| R01_BID_MATCHES_RAW | 2624 | 0 | 0 | 0.0% |  |  |
| R02_ASK_MATCHES_RAW | 2624 | 0 | 0 | 0.0% |  |  |
| R03_IV_MATCHES_RAW | 2624 | 0 | 0 | 0.0% |  |  |
| R06_SPOT_MATCHES_CHAIN_UNDERLYING | 2624 | 0 | 68 | 0.0% | signal spot differs from chain underlying by 1.5% | ALGM,BLZE,BOOT,CAKE,CHPT,CON,CRSR,CVI,DFH,DK,EXK,EYE |
| T01_READY_BUT_UNTRADEABLE_SPREAD | 2286 | 0 | 812 | 0.0% | EOD_THESIS_READY_REPAIR_AT_OPEN with 200% spread | A,ABTC,ACAD,ACGL,ACIW,ADNT,ADPT,AEO,AER,AGIO,AIP,AKAM |
| T02_READY_WITH_ZERO_BID | 94 | 0 | 94 | 0.0% | EOD_THESIS_READY_REPAIR_AT_OPEN contract has no bid | ACGL,AMH,AORT,BBT,BLFS,BRX,CBSH,COLL,CUZ,DNOW,DRVN,EBC |
| T03_IV_PLAUSIBLE | 2624 | 0 | 8 | 0.0% | implausible implied volatility | KURA,MGTX,OLMA,PLAY |
| U01_BARS_CURRENT | 1528 | 0 | 0 | 0.0% |  |  |
| U03_CLOSE_MATCH | 1528 | 0 | 0 | 0.0% |  |  |
| U04_PRICE_IS_SESSION_CLOSE | 1528 | 0 | 0 | 0.0% |  |  |
| U05_ATR14 | 1528 | 0 | 0 | 0.0% |  |  |
| U06_ATR_PCT | 1528 | 0 | 0 | 0.0% |  |  |
| U07_GAP_PCT | 1528 | 0 | 0 | 0.0% |  |  |
| U08_RANGE_PCT | 1528 | 0 | 0 | 0.0% |  |  |
| U09_ADX14 | 1528 | 0 | 0 | 0.0% |  |  |
| X02_DIRECTION_CONSISTENT | 2898 | 0 | 0 | 0.0% |  |  |
| X03_SPOT_CONSISTENT | 4347 | 0 | 0 | 0.0% |  |  |
| X04_INVALIDATION_CONSISTENT | 4596 | 0 | 0 | 0.0% |  |  |
| X05_TARGET_CONSISTENT | 2218 | 0 | 0 | 0.0% |  |  |
| X06_CONTRACT_CONSISTENT | 1312 | 0 | 0 | 0.0% |  |  |
| X07_CONTRACT_FIELDS_CONSISTENT | 7872 | 0 | 0 | 0.0% |  |  |

## Trigger-ready candidates only

| Check | Evaluated | FAIL | WARN | Fail rate |
|---|---:|---:|---:|---:|
| R04_DELTA_VS_INDEPENDENT_BS | 300 | 6 | 16 | 2.0% |
| G03_INVALIDATION_DISTANCE_ATR | 300 | 0 | 16 | 0.0% |
| G07_TARGET_DISTANCE_ATR | 300 | 0 | 68 | 0.0% |
| R06_SPOT_MATCHES_CHAIN_UNDERLYING | 300 | 0 | 8 | 0.0% |

## Files

- `checks.csv` — one row per check (ticker, stage, field, published, recomputed, status, reason)
- `summary_by_check.csv`, `summary_by_stage_field.csv`, `summary_by_check_trigger_ready.csv`
- `golden_reference.csv` — stratified sample of independently recomputed values, reusable as a regression reference
- `summary.json` — machine-readable totals and the clean trigger-ready list
