# IV history inventory (16 Sep 2026)

Question: before building a daily IV history capture, is IV history already held in any database? Read-only checks.

## What exists

| Store | Content | Coverage |
|---|---|---|
| `data/phantom/phantom_history.db` → `chain_snapshots` | Per contract: bid/ask/mid, OI, volume, IV, delta, gamma, theta, vega, underlying price, source | **Weekly (Friday)** snapshots, ~2,900 tickers. Most tickers from 2024-05-17 (~114 weeks); some from 2021 (NVDA 265 weeks). |
| same → `options_greeks_history` | Solver-recomputed greeks with `quality_status` | Same weekly dates. 2026-09-04 run: 229,584 OK, 12,155 OK_ADJUSTED_NO_ARB, ~3.8k flagged. |
| same → `iv_surface_history` | ATM IV, median IV, IV entropy, 25d skew, put/call IV spread by DTE bucket (0_7, 8_30, 31_60) | Only 10 weekly dates (2026-05-22 → 2026-09-04) |
| `data/cache/iv_history_cache.db` → `iv_history` | ATM IV per ticker (marketdata / phantom) | Sparse: 19,935 rows, 2,953 tickers, avg 6.75 samples per ticker; last 2026-09-04 |
| `data/canonical/market_observations/option_chain/<date>/<ticker>/` | Raw daily chains from the evening run | 9 dates since 2026-08-28 (08-28, 08-31, 09-02, 09-03, 09-04, 09-08, 09-10, 09-11, 09-14); 937–1,316 tickers (candidates only) |

## Gaps and defects

1. **Weekly, not daily.** Enough for a first IV percentile (~100 weekly observations over two years), but not a daily series.
2. **Missing weeks in 2026:** 04-03, 06-19, 07-03, 07-24, 08-07, 08-14, 08-21. Between 05-22 and 07-17 only about half the tickers were captured (sample: 27–28 of 57).
3. **Daily projection only partly working.** The evening run projects canonical chains to Phantom (`intelligent_orchestrator.py` ~L5188, outbox `PHANTOM_OPTION_CHAIN_V1`, added ~13 Sep). Only 2026-09-11 and 09-14 were projected (plus 2 tickers for 09-03). Canonical chains for 08-28 → 09-10 exist on disk but are not in history (recoverable).
4. **Selection bias.** Daily capture covers only that day's candidates, so a ticker's daily IV series has entries only on days it was a candidate.
5. **No derived series.** There is no daily constant-maturity (e.g. 30-day) ATM IV per ticker, which IV percentile, variance risk premium and cheap-convexity measures need (knowledge note 04). The current `ivp_252d` compares IV with a realised-vol range, not IV history.

## Recommended work (replaces "start a daily IV capture")

1. **Backfill** the 7 unprojected canonical chain dates into Phantom history.
2. **Fixed IV panel:** capture the eligible universe every evening, not only candidates (check MarketData credit cost first).
3. **Derived series:** a daily 30-day constant-maturity ATM IV (plus 25d skew and term slope) per ticker, built from weekly history plus daily data going forward, with explicit `observation_frequency` and quality state.
4. **Fill missing weeks** from MarketData historical chains if the plan allows.
5. **Integrity checks:** IV placeholders (e.g. 0.0001), zero gamma, missing OI → explicit quality state, never a neutral value.
