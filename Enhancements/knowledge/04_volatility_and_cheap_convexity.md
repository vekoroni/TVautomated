# 04 — Volatility and Cheap Convexity

Status: **Draft v2** (reconciled to specification v1.1, 16 Sep 2026) · Capability: O4 Cheap convexity · Contexts: **C7 Volatility & Convexity** (inputs from C1 Market Data; outputs to C8 Valuation, C9 display, C14) · Governing: spec §11; addendum §5

## Question this method answers

> What volatility do we expect over the part of the 1–20 session window that matters for this thesis, what volatility is the option market charging, and is this option's convexity cheap — priced below expected volatility with a payoff that magnifies the thesis move?

## 1. Realised volatility (what actually happened)

Estimators on daily bars, annualised with √252:
- **Close-to-close**: standard deviation of log returns — simple, noisy.
- **Parkinson**: uses high/low range — more efficient, ignores gaps and drift.
- **Garman-Klass** and **Rogers-Satchell**: use OHLC; Rogers-Satchell handles drift.
- **Yang-Zhang**: combines overnight, open-to-close and Rogers-Satchell; robust to gaps — a good default for equities (Yang & Zhang, 2000 [verify]; Sinclair, *Volatility Trading* [verify]).

Windows: 10, 20, 60 sessions; always computed point-in-time.

## 2. Forecast volatility (term structure over sessions 1–20)

- **HAR-RV** (Heterogeneous Autoregressive model of realised volatility): regress future RV on daily, weekly and monthly RV components. Simple, robust, hard to beat (Corsi, 2009 [verify]).
- **GARCH/EGARCH**: alternative; state which model and store its parameters (the legacy "GARCH" layer is actually HAR_RV).
- Forecast a **term structure** σ_forecast(n) for n = 1..20 sessions (cumulative variance to session n). Values at 5, 10 and 20 sessions are **forecast checkpoints** for reporting and replication R1 — they are not thesis holding buckets.
- Valuation uses the forecast matching each path's holding sessions; metrics below use the thesis's median expected resolution session m (or an expression's forced exit F where stated).
- Output: `sigma_forecast_by_session[1..20]`, model, fit window, fit error, parameters.

## 3. Implied volatility measures (what the market charges)

- **ATM IV by expiry** from the chain (backed out from mids; placeholder IVs ≤ 0.001 and zero gamma are quality states, excluded).
- **Constant-maturity 30-day IV** interpolated in total variance between expiries — stored **daily** per ticker as a point-in-time series.
- **IV percentile (IVP)**: share of the last 252 sessions where 30-day IV was below today's — requires the **daily IV series**; comparing IV with a realised-vol range is not IVP. Interim: weekly Phantom chain history (per-contract IV, weekly since ~May 2024) may seed a weekly percentile, disclosed as such.
- **IV rank**: (IV − min)/(max − min) over 252 sessions of IV history.
- **Term structure**: IV(front expiry ≥ 7 DTE) vs IV(next expiry) from actually listed expiries.
- **Skew**: IV at 25-delta put minus IV at 25-delta call per expiry (interpolated in delta), stored in decimal units.
- **IV dynamics for valuation**: fitted spot-vol slope β_d and stress shifts Δ used by C8 to price exits (note 03).

## 4. Event variance (earnings)

Earnings add a one-day jump to variance. Separate it before calling IV "rich" or "cheap":
- Implied event move from the term structure: total variance of the expiry containing earnings minus diffusive variance estimated from neighbouring expiries.
- `sigma_ex_event² = (sigma² · T − event_variance) / (T − 1 day)`.
- Compare the implied earnings move with the historical distribution of that stock's earnings-day moves.
(Common practitioner method; see Sinclair; Bennett, *Trading Volatility* [verify].)

Event information is displayed for manual review (spec §14); it is not an automated gate.

## 5. The variance risk premium (the core fact)

On average implied volatility exceeds subsequently realised volatility — option buyers pay a premium (Carr & Wu, 2009; Bollerslev, Tauchen & Zhou, 2009 [verify]). In the cross-section of stocks, options where IV is high relative to historical/forecast volatility tend to have lower subsequent returns, and vice versa (Goyal & Saretto, 2009 [verify]; related: Cao & Han, 2013 [verify]).

**Implication:** "cheap convexity" is a relative statement — cheap versus the stock's own expected volatility and versus peers — and buying options is a negative-expectation activity unless selection genuinely identifies underpricing or a directional edge large enough to pay the premium.

## 6. Cheap-convexity profile (per option expression)

m = thesis median expected resolution session; F = the expression's forced exit session.

| Metric | Formula | Cheap when |
|---|---|---|
| Model cheapness | (V(S₀, K, τ₀, σ_forecast(m)) − ask) / ask | > 0 |
| Variance risk premium | IV_ATM(matched tenor) − σ_forecast(matched sessions) | < 0 (or low vs peers) |
| IV / RV | IV_ATM / RV_20 (and RV_60) | low |
| IV percentile | point-in-time 252-session IVP from daily IV series | low |
| Breakeven ÷ expected move | \|breakeven − S₀\| / S₀ ÷ (σ_forecast(m) · √(m/252)) | < 1 |
| Convexity at target | (π_option(target)/R) ÷ (\|target − S₀\|/S₀); n/a when `target_state = NONE` | high |
| Gamma per premium $ | Γ · S₀² · 0.01 / ask | high |
| Theta burden | \|Θ\| · m ÷ expected option gain from the forecast move | low |
| Term slope | IV_next − IV_front | positive (front relatively cheap) |
| Thesis-side skew | BEAR: IV_25Δput − IV_25Δcall; BULL: reverse | low |
| Event load | earnings before `last_exit_session`; implied vs historical event move | flag; separates event from structural cheapness |
| Upper-tail share | E[π · 1{top decile}] / R on the path set | high |

Composite: cross-sectional percentile ranks, equal weight until outcome data justifies weights; publish the number of metrics used; missing metric excluded, never neutral.

**Authority:** cheap convexity is an **explanatory** profile. The money effect of cheap or expensive volatility is already inside EV through σ_forecast and IV dynamics (note 03), so using it again as a ranking key would double-count. It is displayed (composite with authority state `SHADOW`) and becomes a ranking input only if C13 validation shows incremental value beyond RAEV (spec Invariant G).

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| "IVP 252d" computed against realised-vol range | `avshunter_options_intelligence.py:3929-3947`; 26.5% of rows at 100 |
| Convexity score counts missing data as passes | Constant 2 on all rows |
| Skew stored ×100 vs IV in decimals | `put_25d_iv`, `call_25d_iv` |
| Term structure windows that miss listed expiries | `term_ratio` 27% populated |
| Earnings from a non-existent field | Morning gate `earningsAnnouncement` |
| Placeholder IVs (≤ 0.001) not filtered | 5.7% of sampled contracts |
| Named GARCH, actually HAR_RV; horizon not tied to anything | Layer 3 |
| IV history weekly, stale since session 2026-09-04, never projected daily | Phantom / `iv_history_cache.db` |

## Validation (gate G4)

1. Forecast accuracy: HAR-RV term forecast beats naive RV_20 on out-of-sample QLIKE / MSE of realised variance at the 5/10/20 checkpoints (replication R1).
2. VRP sign: average IV − subsequent RV > 0 across the universe (replication R2).
3. Cheapness pays **incrementally**: after controlling for RAEV, realised expression returns higher in the cheapest quintile than the richest (required before convexity may become a ranking input).
4. IV dynamics: realised exit IV vs assumed σ_exit — bias within tolerance.

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
