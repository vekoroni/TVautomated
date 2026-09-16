# 04 — Volatility and Cheap Convexity

Status: **Draft** · Capability: O4 Cheap convexity · Contexts: C1 Market Data, C7 Valuation

## Question this method answers

> Is this option's convexity cheap — is it priced below the volatility we expect over the holding period, and does its payoff magnify the thesis move enough to be worth the premium?

## 1. Realised volatility (what actually happened)

Estimators on daily bars, annualised with √252:
- **Close-to-close**: standard deviation of log returns — simple, noisy.
- **Parkinson**: uses high/low range — more efficient, ignores gaps and drift.
- **Garman-Klass** and **Rogers-Satchell**: use OHLC; Rogers-Satchell handles drift.
- **Yang-Zhang**: combines overnight, open-to-close and Rogers-Satchell; robust to gaps — a good default for equities (Yang & Zhang, 2000 [verify]; Sinclair, *Volatility Trading* [verify]).

Windows: 10, 20, 60 sessions; always computed point-in-time.

## 2. Forecast volatility (what we expect over the hold)

- **HAR-RV** (Heterogeneous Autoregressive model of realised volatility): regress future RV on daily, weekly and monthly RV components. Simple, robust, hard to beat (Corsi, 2009 [verify]).
- **GARCH/EGARCH**: alternative; state which model and store its parameters.
- Forecast horizon must equal the **thesis hold** (and optionally the option's remaining life), not a fixed bucket.
- Output: `sigma_forecast_h`, model, fit window, fit error, parameters.

## 3. Implied volatility measures (what the market charges)

- **ATM IV by expiry** from the chain (backed out from mids, placeholder IVs ≤ 0.001 excluded).
- **Constant-maturity 30-day IV** interpolated in total variance between expiries.
- **IV percentile (IVP)**: share of the last 252 sessions where 30-day IV was below today's — requires a **daily IV history**; comparing IV with a realised-vol range is not IVP.
- **IV rank**: (IV − min)/(max − min) over 252 sessions of IV history.
- **Term structure**: IV(front expiry ≥ 7 DTE) vs IV(next expiry); contango/backwardation.
- **Skew**: IV at 25-delta put minus IV at 25-delta call per expiry (interpolated in delta), stored in decimal units.

## 4. Event variance (earnings)

Earnings add a one-day jump to variance. Separate it before calling IV "rich" or "cheap":
- Implied event move from the term structure: total variance of the expiry containing earnings minus diffusive variance estimated from neighbouring expiries.
- `sigma_ex_event² = (sigma² · T − event_variance) / (T − 1 day)`.
- Compare the implied earnings move with the historical distribution of that stock's earnings-day moves.
(Common practitioner method; see Sinclair; Bennett, *Trading Volatility* [verify].)

## 5. The variance risk premium (the core fact)

On average implied volatility exceeds subsequently realised volatility — option buyers pay a premium (Carr & Wu, 2009; Bollerslev, Tauchen & Zhou, 2009 [verify]). In the cross-section of stocks, options where IV is high relative to historical/forecast volatility tend to have lower subsequent returns, and vice versa (Goyal & Saretto, 2009 [verify]; related: Cao & Han, 2013 [verify]).

**Implication:** "cheap convexity" is a relative statement — cheap versus the stock's own expected volatility and versus peers — and buying options is a negative-expectation activity unless selection genuinely identifies underpricing or a directional edge large enough to pay the premium.

## 6. Cheap-convexity profile (per option expression)

| Metric | Formula | Cheap when |
|---|---|---|
| Model cheapness | (BS(S₀, K, τ₀, σ_forecast_h) − ask) / ask | > 0 |
| Variance risk premium | IV_ATM,h − σ_forecast_h | < 0 (or low vs peers) |
| IV / RV | IV_ATM / RV_20 (and RV_60) | low |
| IV percentile | point-in-time 252-session IVP | low (needs IV history) |
| Breakeven ÷ expected move | |breakeven − S₀| / S₀ ÷ (σ_forecast_h · √(h/252)) | < 1 |
| Convexity at target | (π_option(target)/R) ÷ (|target − S₀|/S₀) | high (requires structural target) |
| Gamma per premium $ | Γ · S₀² · 0.01 / ask | high |
| Theta burden | |Θ| · h ÷ expected option gain from the forecast move | low |
| Term slope | IV_next − IV_front | positive (front relatively cheap) |
| Thesis-side skew | BEAR: IV_25Δput − IV_25Δcall; BULL: reverse | low |
| Event load | earnings inside DTE; implied vs historical event move | flag; separate event from structural cheapness |

Composite: cross-sectional percentile ranks, equal weight until outcome data justifies weights; publish the number of metrics used; missing metric excluded, never neutral.
Cheap convexity is a **ranking and explanation signal**; money is decided by EV (note 03), which already uses σ_forecast in its pricing assumptions.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| "IVP 252d" computed against realised-vol range | `avshunter_options_intelligence.py:3929-3947`; 26.5% of rows at 100 |
| Convexity score counts missing data as passes | Constant 2 on all rows |
| Skew stored ×100 vs IV in decimals | `put_25d_iv`, `call_25d_iv` |
| Term structure windows that miss listed expiries | `term_ratio` 27% populated |
| Earnings from a non-existent field | Morning gate `earningsAnnouncement` |
| Placeholder IVs (≤ 0.001) not filtered | 5.7% of sampled contracts |
| Named GARCH, actually HAR_RV; horizon not tied to hold | Layer 3 |

## Validation (gate G4)

1. Forecast accuracy: HAR-RV forecast beats naive RV_20 on out-of-sample QLIKE / MSE of realised variance (replication R1).
2. VRP sign: average IV − subsequent RV > 0 across the universe (replication R2).
3. Cheapness pays: realised option returns (or delta-hedged returns) higher in the cheapest quintile than the richest, controlling for thesis quality.

## References

- Sinclair, E. (2013). *Volatility Trading*, 2nd ed. Wiley [verify]
- Bennett, C. (2014). *Trading Volatility*. [verify]
- Corsi, F. (2009). A simple approximate long-memory model of realized volatility. *Journal of Financial Econometrics* [verify]
- Yang, D. & Zhang, Q. (2000). Drift-independent volatility estimation based on high, low, open, and close prices. *Journal of Business* [verify]
- Carr, P. & Wu, L. (2009). Variance risk premiums. *Review of Financial Studies* [verify]
- Bollerslev, T., Tauchen, G. & Zhou, H. (2009). Expected stock returns and variance risk premia. *Review of Financial Studies* [verify]
- Goyal, A. & Saretto, A. (2009). Cross-section of option returns and volatility. *Journal of Financial Economics* [verify]
- Cao, J. & Han, B. (2013). Cross section of option returns and idiosyncratic stock volatility. *Journal of Financial Economics* [verify]
- Patton, A. (2011). Volatility forecast comparison using imperfect volatility proxies (QLIKE loss). *Journal of Econometrics* [verify]
