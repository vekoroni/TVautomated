# Replication Plan — "Replicate before we innovate"

Status: **Draft** · Gate: G4 Validation (data and method sanity) · Prepared 16 Sep 2026

## Why

Before trusting any new AVSHUNTER logic, reproduce well-established results on **our own stored data** with **our own production-style code path**. If a known effect does not appear, the data, the point-in-time handling or the method is wrong — and any proprietary logic built on top would be untrustworthy.

Each replication is read-only research: it reads stored data, writes results to `audit/replications/<id>/`, and changes no pipeline code.

## Summary

| ID | Known result | Tests which AVSHUNTER capability | Data readiness | Effort |
|---|---|---|---|---|
| R1 | HAR-RV forecasts realised volatility better than a simple trailing RV | O4 forecast volatility; bar data quality | **Ready** (bars 2021→) | Small |
| R2 | Implied volatility exceeds subsequently realised volatility on average (variance risk premium) | O4 IV measurement; chain/IV data | **Partial** (weekly IV history ~1 year for ~150 tickers; daily chains since 28 Aug 2026) | Small–medium |
| R3 | Price momentum / short-term reversal patterns in the cross-section, and survivorship sensitivity | O8 universe and point-in-time integrity | **Ready** (bars), survivorship check needs delisted tickers | Medium |
| R4 | Triple-barrier outcome probabilities conditional on structural state do or do not beat the unconditional base rate out of sample | O1 evidence — the core premise of the pipeline | **Ready** (bars) after outlier cleaning | Medium |

Recommended order: R1 → R4 → R3 → R2 (R2 improves as daily chain capture accumulates).

---

## R1 — Volatility forecasting (HAR-RV vs trailing RV)

- **Known result**: HAR-RV using daily, weekly and monthly realised-volatility components forecasts future realised volatility better than single-window estimators (Corsi, 2009 [verify]).
- **Data**: `data/canonical/historical_prices.sqlite` `ohlcv_daily`, liquid universe, 2021-10 → 2026-09.
- **Method**:
  1. Compute daily Yang-Zhang (or close-to-close) variance per ticker.
  2. Targets: realised variance over next 5, 10, 20 sessions.
  3. Models: naive RV_20; HAR-RV fitted walk-forward (expanding or 2-year rolling window, monthly refit), pooled across tickers with ticker-level scaling.
  4. Loss: QLIKE and MSE on variance; Diebold-Mariano test for difference.
- **Pass**: HAR-RV lower out-of-sample loss than RV_20 at all three horizons, significant at 5%.
- **If it fails**: bar data quality, adjustment or return calculation problems; fix before any volatility-based logic.
- **Output**: loss table by horizon and liquidity bucket; forecast bias; chosen model spec for note 04.

## R2 — Variance risk premium sign

- **Known result**: implied volatility is on average above subsequently realised volatility for equity options (Carr & Wu, 2009; Bollerslev, Tauchen & Zhou, 2009 [verify]); in the cross-section, high IV relative to historical volatility predicts lower option returns (Goyal & Saretto, 2009 [verify]).
- **Data**: `data/cache/iv_history_cache.db` (weekly ATM IV, 2025-07 → 2026-09; ~154 tickers with ≥ 52 observations — confirm whether `phantom_history` rows are observed or synthetic before use); canonical daily chains from 2026-08-28; bars for realised volatility.
- **Method**:
  1. For each (ticker, week) with ATM IV at ~30 DTE, compute realised volatility over the following 21 sessions.
  2. VRP = IV − RV_forward; average across tickers and time with block-bootstrap CI.
  3. Cross-section (when ≥ 6 months of daily chains): sort tickers by IV/RV_60 into quintiles; compare subsequent ATM straddle or delta-hedged option returns using bid/ask.
- **Pass**: mean VRP > 0 with CI excluding 0; (later) quintile spread in the expected direction.
- **If it fails**: IV extraction, units or timing wrong; do not build cheap-convexity metrics until resolved.
- **Output**: VRP distribution by sector/liquidity; data-quality notes on IV sources.

## R3 — Cross-sectional momentum / reversal and survivorship check

- **Known result**: stocks with high returns over the past 3–12 months (skipping the most recent month) tend to continue outperforming in the following months; the most recent month's returns tend to reverse (Jegadeesh & Titman, 1993; Jegadeesh, 1990 [verify]). Effects are weaker in recent decades and among large caps, but should not be absent or reversed in a clean, survivorship-free sample.
- **Data**: bars 2021-10 → 2026-09; universe as available; list of delisted tickers if obtainable.
- **Method**:
  1. Monthly rebalance: rank by 12-1 month return and by 1-month return; decile portfolios, equal-weighted, next-month returns.
  2. Run twice: (a) current-universe only; (b) point-in-time universe including delisted names when available.
  3. Report spread, t-stat with Newey-West errors, and the difference between (a) and (b).
- **Pass**: results directionally consistent with literature; the (a)–(b) difference quantifies survivorship bias.
- **If it fails**: universe construction, price adjustment or point-in-time handling problems.
- **Output**: survivorship bias estimate to apply as a caution to all actuarial statistics until the universe is fixed.

## R4 — Does structural state carry evidence? (core premise)

- **Known result to test against**: in liquid equities, most simple technical states have little out-of-sample predictive power after multiple-testing adjustment; an informative state must beat the unconditional base rate out of sample (Harvey, Liu & Zhu, 2016; White, 2000 [verify]).
- **Data**: bars (cleaned: outliers rejected, adjusted), current Discovery state definitions reproduced point-in-time from bars (phase, trend, volatility regime).
- **Method**:
  1. Build triple-barrier labels per note 01 for BULL and BEAR at h ∈ {5, 10, 20} with barriers at ±k·σ_h (k ∈ {1, 1.5}) and at structural levels where definable.
  2. Walk-forward with purging and embargo: estimate per-state probabilities on the past (with shrinkage), predict the next month.
  3. Compare out-of-sample Brier / log loss with the unconditional base rate for the same barrier settings; reliability diagrams; count of states/variants tried.
  4. Report deflated statistics and PBO for the best variant.
- **Pass**: at least some states beat the base rate out of sample with CI excluding zero after adjustment for the number of variants.
- **If it fails**: the pipeline's structural states do not carry directional evidence as defined — the thesis logic must change (different features, different horizons, or options-only edges from volatility mispricing rather than direction).
- **Output**: evidence table per state/horizon; recommendation for the evidence packet design (note 01) and the thesis stage (note 02).

---

## Deliverables and governance

- Each replication: `audit/replications/<ID>/REPORT.md` (question, data, method, results with CIs, pass/fail, implications), plus code in `audit/replications/<ID>/` using the future domain services where possible.
- Results reviewed with ACK and, for R2 and R4, an independent quant reviewer.
- Outcomes feed back into method notes 01–05 (status Draft → Standard or revised).

## References

- Corsi, F. (2009). *Journal of Financial Econometrics* [verify]
- Carr, P. & Wu, L. (2009). *Review of Financial Studies* [verify]
- Bollerslev, T., Tauchen, G. & Zhou, H. (2009). *Review of Financial Studies* [verify]
- Goyal, A. & Saretto, A. (2009). *Journal of Financial Economics* [verify]
- Jegadeesh, N. & Titman, S. (1993). Returns to buying winners and selling losers. *Journal of Finance* [verify]
- Jegadeesh, N. (1990). Evidence of predictable behavior of security returns. *Journal of Finance* [verify]
- Harvey, C., Liu, Y. & Zhu, H. (2016). *Review of Financial Studies* [verify]
- White, H. (2000). *Econometrica* [verify]
- Diebold, F. & Mariano, R. (1995). Comparing predictive accuracy. *Journal of Business & Economic Statistics* [verify]
- Newey, W. & West, K. (1987). *Econometrica* [verify]
