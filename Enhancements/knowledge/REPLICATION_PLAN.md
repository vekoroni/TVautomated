# Replication Plan — "Replicate before we innovate"

Status: **Draft v2** (reconciled to specification v1.1, 16 Sep 2026) · Gate: G4 Validation (data and method sanity) · Governing: spec §24; note 06 §2

## Why

Before trusting any new AVSHUNTER logic, reproduce well-established results on **our own stored data** with **our own production-style code path**. If a known effect does not appear, the data, the point-in-time handling or the method is wrong — and any proprietary logic built on top would be untrustworthy.

## How replications relate to the build (spec §24)

- The contexts a replication exercises (C4 Evidence, C7 Volatility & Convexity, C5 Thesis) **may be built** in non-authoritative shadow form so that the replication runs through the same domain services production will use. They gain no decision authority until the replication and subsequent validation gates pass.
- A **lightweight research replication** may be run earlier to de-risk a method before its context is built; it does not replace replication through the production services.
- Replications run only on data that passes the C1 freshness and coverage gates; the missed-session **backfill is the first Phase 0 data task**.
- Replications are read-only with respect to the legacy pipeline: they read stored data and write results to `Enhancements/replications/<ID>/`.

## Summary

| ID | Known result | Tests which AVSHUNTER capability | Data readiness | Effort |
|---|---|---|---|---|
| R1 | HAR-RV forecasts realised volatility better than a simple trailing RV | O4 forecast volatility (C7); bar data quality | **Ready** (bars 2021→) | Small |
| R2 | Implied volatility exceeds subsequently realised volatility on average (variance risk premium) | O4 IV measurement; chain/IV data | **Partial** (weekly per-contract IV in Phantom since ~May 2024, gaps; daily candidate chains since 28 Aug 2026) — improves after backfill and daily panel capture | Small–medium |
| R3 | Price momentum / short-term reversal patterns in the cross-section, and survivorship sensitivity | O8 universe and point-in-time integrity (C2) | **Ready** (bars); survivorship check needs delisted tickers | Medium |
| R4 | First-passage outcomes and timing conditional on structural state and candidate geometry do or do not beat the unconditional base rate out of sample; the R-H geometry rule beats alternatives | O1 evidence and thesis (C3, C4, C5) — the core premise | **Ready** (bars) after outlier exclusion and path store | Medium–large |

Recommended order: R1 → R4 → R3 → R2 (R2 improves as daily panel capture accumulates).

---

## R1 — Volatility forecasting (HAR-RV vs trailing RV)

- **Known result**: HAR-RV using daily, weekly and monthly realised-volatility components forecasts future realised volatility better than single-window estimators (Corsi, 2009 [verify]).
- **Data**: `data/canonical/historical_prices.sqlite` `ohlcv_daily`, liquid universe, 2021-10 → 2026-09.
- **Method**:
  1. Compute daily Yang-Zhang (or close-to-close) variance per ticker.
  2. Targets: realised variance over the next n sessions for the **forecast checkpoints** n = 5, 10, 20 (and the full term structure 1..20 for the C7 forecast).
  3. Models: naive RV_20; HAR-RV fitted walk-forward (expanding or 2-year rolling window, monthly refit), pooled across tickers with ticker-level scaling.
  4. Loss: QLIKE and MSE on variance; Diebold-Mariano test for difference.
- **Pass**: HAR-RV lower out-of-sample loss than RV_20 at all three checkpoints, significant at 5%.
- **If it fails**: bar data quality, adjustment or return calculation problems; fix before any volatility-based logic.
- **Output**: loss table by checkpoint and liquidity bucket; forecast bias; chosen model spec for note 04 and C7.

## R2 — Variance risk premium sign

- **Known result**: implied volatility is on average above subsequently realised volatility for equity options (Carr & Wu, 2009; Bollerslev, Tauchen & Zhou, 2009 [verify]); in the cross-section, high IV relative to historical volatility predicts lower option returns (Goyal & Saretto, 2009 [verify]).
- **Data**: Phantom `chain_snapshots` (per-contract IV, weekly since ~May 2024; confirm observed vs derived IV via `greeks_source` / `options_greeks_history.quality_status`; placeholder IVs excluded); `iv_history_cache.db` (sparse, cross-check only); daily chains from 2026-08-28 plus backfill; bars for realised volatility.
- **Method**:
  1. For each (ticker, week) derive 30-day constant-maturity ATM IV from the chain; compute realised volatility over the following 21 sessions.
  2. VRP = IV − RV_forward; average across tickers and time with block-bootstrap intervals.
  3. Cross-section (when ≥ 6 months of daily panel chains): sort tickers by IV/RV_60 into quintiles; compare subsequent ATM straddle or delta-hedged option returns using bid/ask.
- **Pass**: mean VRP > 0 with interval excluding 0; (later) quintile spread in the expected direction.
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
- **Output**: survivorship bias estimate to apply as a caution to all evidence statistics until the universe is fixed.

## R4 — Does structural state carry evidence over the 1–20 session window? (core premise)

- **Known result to test against**: in liquid equities, most simple technical states have little out-of-sample predictive power after multiple-testing adjustment; an informative state must beat the unconditional base rate out of sample (Harvey, Liu & Zhu, 2016; White, 2000 [verify]).
- **Data**: bars (cleaned: failing returns excluded with reason, adjusted), path store for sessions 1..20; current structural state definitions and candidate geometries reproduced point-in-time from bars (phase, trend, volatility regime; structural invalidation and target levels).
- **Method** (through the C3/C4/C5 shadow services where built):
  1. For each state date, generate candidate geometries per note 02 (structural invalidation required; target `LEVEL` or `NONE`) for BULL and BEAR; as a control, also volatility-scaled barriers at ±k·σ (k ∈ {1, 1.5}).
  2. Label first passage by session 1..20 per note 01 (intraday touches, `AMBIGUOUS` counted as stop-first, gap at stop).
  3. Estimate **competing-risks cumulative incidence** of target-first and stop-first by session (Aalen-Johansen or discrete hazard) per state and geometry type, with shrinkage to pooled hazards, `n_eff` by time blocks, block-bootstrap intervals.
  4. Walk-forward with purging (20-session windows) and embargo: estimate on the past, predict the next month.
  5. Compare out-of-sample **integrated Brier score** (sessions 1–20), checkpoint Brier (sessions 5, 10, 20) and log loss with the unconditional base rate for the same geometry distances; reliability of cumulative incidence (whether **and when**).
  6. **Direction symmetry**: mirrored price series give mirrored results.
  7. **Geometry rule (R-H)**: compare realised underlying expectancy in σ of the R-H choice (highest lower-bound expectancy) against alternatives — nearest structural target, highest target-first probability, structural priority only.
  8. Direction states: realised expectancy for SUPPORTED > UNSUPPORTED > OPPOSED.
  9. Report the number of states, geometry rules and variants tried; deflated statistics and PBO for the best variant.
- **Pass**:
  - at least some states beat the base rate out of sample (outcome and timing) with intervals excluding zero after adjustment for the number of variants;
  - R-H geometry selection is not worse than the alternatives (required to move R-H from `IMPLEMENTED_FOR_REPLICATION` towards authority).
- **If it fails**: the structural states do not carry directional evidence as defined — the thesis logic must change (different features or geometries, or options-only edges from volatility mispricing rather than direction). If only R-H fails, the geometry rule is revised before C5 gains authority.
- **Output**: evidence table per state and geometry type (cumulative incidence, calibration, lift); R-H comparison; recommendations for notes 01 and 02 and the C4/C5 designs.

---

## Deliverables and governance

- Each replication: `Enhancements/replications/<ID>/REPORT.md` (question, data and freshness checks, method, results with intervals, pass/fail, implications), plus code using the domain services where built.
- Results reviewed with ACK and, for R2 and R4, an independent quant reviewer.
- Outcomes feed back into method notes 01–05 (status Draft → Standard or revised) and into authority states of the related contexts.

## References

- Corsi, F. (2009). *Journal of Financial Econometrics* [verify]
- Carr, P. & Wu, L. (2009). *Review of Financial Studies* [verify]
- Bollerslev, T., Tauchen, G. & Zhou, H. (2009). *Review of Financial Studies* [verify]
- Goyal, A. & Saretto, A. (2009). *Journal of Financial Economics* [verify]
- Jegadeesh, N. & Titman, S. (1993). Returns to buying winners and selling losers. *Journal of Finance* [verify]
- Jegadeesh, N. (1990). Evidence of predictable behavior of security returns. *Journal of Finance* [verify]
- Harvey, C., Liu, Y. & Zhu, H. (2016). *Review of Financial Studies* [verify]
- White, H. (2000). *Econometrica* [verify]
- Aalen, O. & Johansen, S. (1978). *Scandinavian Journal of Statistics* [verify]
- Graf, E. et al. (1999). *Statistics in Medicine* — integrated Brier score [verify]
- Diebold, F. & Mariano, R. (1995). Comparing predictive accuracy. *Journal of Business & Economic Statistics* [verify]
- Newey, W. & West, K. (1987). *Econometrica* [verify]
