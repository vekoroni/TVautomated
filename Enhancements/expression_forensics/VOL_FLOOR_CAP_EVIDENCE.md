# Layer 3 forecast floor (5%) and cap (250%): evidence (V5, 17 Sep 2026)

**Question.** `layer3_forward_variance.py` clipped every forecast to 5%–250% annualised, in three places (HAR-RV literal `0.05, 2.50`, `_annualise` for GARCH/EWMA/ATR, and the final clip), with no trace. Does clipping improve the forecast, or does it hide information?

**Method.** `vol_floor_cap_study.py` (read-only; results in `vol_floor_cap_study.json`). Production path `compute_forward_variance` (regime `''`, code at `8d1e04c`) with clipping disabled to see the raw model output; clipped value = min(max(raw, 5%), 250%) (verified against the unpatched path on 200 cases). Canonical price store `ohlcv_daily` (COMPLETE bars), every ticker, every 20th session from 2022-01-01, 252-bar window (the runner's `PRICE_BARS`). Scored against close-to-close volatility delivered over the next 20 sessions. **85,253 forecasts, 1,937 tickers** (tickers with at least 272 bars); all HAR-RV.

## Results

| | Below floor (raw < 5%) | Above cap (raw > 250%) | All forecasts |
|---|---|---|---|
| Cases (share) | 48 (0.056%), 12 tickers | 148 (0.17%), 57 tickers | 85,253 |
| Raw forecast, median (10th–90th pct) | 3.8% (2.3–4.7%) | 336% (266–655%); max 2,449% | 39% |
| Delivered, median (10th–90th pct) | 2.9% (1.2–6.5%) | 95% (48–261%); max 5,874% | 35% |
| Delivered beyond the bound | 83% delivered below 5% | 12.8% delivered above 250% | 0.24% below 5%, 0.19% above 250% |
| QLIKE mean, raw → clipped | 0.864 → 0.761 | **2.22 → 5.18** | 0.3542 → 0.3593 |
| QLIKE median, raw → clipped | 0.503 → 0.529 | 1.77 → 1.14 | 0.1199 → 0.1199 |
| Mean abs log error, raw → clipped | **0.520 → 0.679** | 1.358 → 0.984 | 0.3131 → 0.3125 |
| Median log(forecast/delivered), raw → clipped | +0.20 → +0.54 | +1.25 → +0.96 | +0.138 → +0.138 |
| Clipped value closer to delivered | 27% | 93% | 0.2% |

Who is out of range: below the floor are stale or near-cash instruments (SPAC trusts, bond ETFs such as HYG/LQD; median 26% of daily returns exactly zero). Above the cap are micro-cap / squeeze / possibly mis-adjusted series (e.g. SOLS raw 2,449% vs delivered 32%).

## Findings

1. **The floor hides information.** 83% of floor cases really delivered less than 5%; clipping moves the forecast further from reality in typical error (abs log error 0.52 → 0.68, bias +20% → +54%). It only looks better on mean QLIKE, because 5% is a conservative over-forecast for the few that moved.
2. **The cap is two-sided.** Above 250% the raw model over-forecasts by ~3.5× at the median, so the cap is closer in typical error (93% of cases), but it under-forecasts the 12.8% of cases that really delivered more than 250% and more than doubles mean QLIKE (2.22 → 5.18) — the costly error when buying premium.
3. **Overall effect is negligible** (QLIKE 0.354 vs 0.359; abs log error 0.3131 vs 0.3125): 0.23% of forecasts are out of range. Neither bound is a validated accuracy improvement; outside 5%–250% the forecast itself is unreliable.

## Decision implemented (test-first, `tests/test_layer3_volatility_leftovers.py` V5)

- Bounds kept as a **range guard** (downstream values stay bounded), moved to governed configuration `config/governed_constants_v1.json` → `layer3_forecast_bounds` (`validation_state = RANGE_GUARD_NOT_ACCURACY_IMPROVEMENT`), loaded fail-closed.
- Clipping happens once, in `compute_forward_variance`, for every model (HAR-RV, GARCH, EWMA, ATR). A bounded forecast carries `l3_forecast_state = CLIPPED_AT_FLOOR | CLIPPED_AT_CAP`; the unbounded model output is always in `l3_forward_realised_vol_raw`. A clipped value is never labelled `FORECAST_OK`.
- Open for ACK: whether CLIPPED rows should be excluded from value decisions (they are forecasts outside the range where the model is reliable), and a data-quality check for series such as SOLS.
