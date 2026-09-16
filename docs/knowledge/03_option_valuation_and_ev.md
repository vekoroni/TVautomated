# 03 — Option Valuation and Expected Value

Status: **Draft** · Capabilities: O2 Money measurement, O3 Expression search · Context: C7 Valuation

## Question this method answers

> For a given thesis, how much money do we expect to make, after all costs and with honest uncertainty, per dollar at risk — for each way of expressing it?

## Core principle

**Expected value = probability-weighted payoff over the outcomes the evidence says can happen, priced at the prices we would actually trade, at the time we would actually exit.**
Anything that treats a target as certain, prices exits at mid, ignores time decay to the exit day, or uses a probability that is not calibrated is **not** an expected value.

## 1. Outcome model (shared by every expression)

Use the evidence packet (note 01) for the thesis state, direction d, hold h, with the thesis's exact invalidation L and target U.

Preferred — **path replay**: for each historical analogue path j with weight w_j:
- exit session k_j = first touch of U or L, else h
- exit spot S_j: U on target; worse of L and that session's open on stop; S₀ × (path close-to-close return) on timeout.

Alternative — **per-session probabilities**: q_U(k), q_L(k), timeout probability and timeout return distribution.
Never collapse timeout to "price unchanged": option value is convex in spot and the timeout distribution carries the drift.

## 2. Pricing an option at exit

- **Model**: Black-Scholes-Merton with continuous dividend yield for European-style approximation; **American** (binomial CRR or Bjerksund-Stensland) for puts and for calls on dividend payers near ex-date (Hull, *Options, Futures and Other Derivatives* [verify]).
- **Implied volatility at entry**: back out σ₀ per contract from the mid (not a vendor IV of unknown timing).
- **IV at exit**: explicit assumption, e.g. σ_exit = σ₀ + β_d · ln(S_exit/S₀) + δ, where β_d is a fitted spot-vol slope (IV typically rises as equity prices fall); δ = 0 base, ± stress. State whether sticky-strike or sticky-delta is assumed (Natenberg; Derman on volatility regimes [verify]).
- **Time**: τ_exit = calendar time remaining after the exit session (sessions → calendar days via the exchange calendar).
- **Rate and dividends**: from data; if defaulted, flag.

## 3. Trading costs (the most common source of false edge)

- **Entry at the ask** (or ask + slippage); **exit at the bid**.
- Spreads at exit: model as `max(absolute floor, proportional share of value)` — out-of-the-money options have small values but similar absolute spreads; a proportional-only model overstates exit bids.
- **Commissions** per contract per side (matter for premiums < $1).
- Empirical note: effective spreads can be smaller than quoted spreads, but a rule must be validated on our fills before using anything better than quoted (Muravyev & Pearson, 2020 [verify]).

## 4. Payoff per expression

Let π_j be profit per unit on path j, R capital at risk per unit.

| Expression | Entry | Exit on path j | R |
|---|---|---|---|
| Long call / put (K) | A = ask + slip + c | V_j = bid-model(S_j, K, τ_j, σ_j) − c | A |
| Debit vertical (long K₁, short K₂, width W) | D = ask₁ − bid₂ + slips + 2c, require 0 < D < W | clip(bid₁,j − ask₂,j, 0, W) − 2c; at expiry intrinsic spread | D |
| Short shares (BEAR thesis) | proceeds = bid − c | − ask_exit − borrow_fee × S₀ × days_j/360 − c | (L × (1 + half-spread) − bid) + expected gap + borrow over h |

π_j = exit − entry (short shares: proceeds − buy-back − fees). Carry per-share and per-contract units; ratios are unitless.

Early-assignment risk on the short leg of a vertical and hard-to-borrow recall risk on short shares are flagged, not ignored.

## 5. Expected value and uncertainty

```
EV   = Σ_j w_j · π_j
EV/R = EV ÷ R
```
- **Uncertainty**: block bootstrap over time blocks of the analogue paths (or posterior draws of probabilities) → distribution of EV/R.
- **Stress**: IV −Δ and +Δ at exit, spread ×1.5 at exit, gap at stop.
- **EV_LB** = lower quantile (e.g. 20th percentile) of EV/R across bootstrap × stress. **RAEV = EV_LB** (already per $ at risk).
- Compare horizons on EV per session or expected log growth E[ln(1 + π/R)] when holds differ.

## 6. Consistency rules

1. All expressions of a thesis use **the same path set** (makes "option vs ticker" and "strongest expression" comparable).
2. One pricer, one cost convention, one horizon convention (XNYS sessions) for the whole pipeline.
3. Missing input (IV, quote, borrow, evidence) → `NOT_VALUED` with reason; no defaults.
4. Probabilities must sum to 1; EV reproducible from stored inputs.

## Known results to respect

- Expected returns on options are strongly negative for OTM puts and near zero or negative for many calls on average, largely because implied volatility exceeds realised volatility (volatility risk premium). A model that finds positive EV in most long options is likely wrong (Coval & Shumway, 2001; Bakshi & Kapadia, 2003 [verify]).
- Option returns are highly sensitive to transaction costs; many academic anomalies vanish after realistic costs.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| Heuristic "probability" and multipliers that improve negative EV | `ev_engine_v2.py` (decides verdicts) |
| Timeout at unchanged spot | EV3 |
| Probabilities at snapped grid, payoff at exact levels | EV3 |
| Proportional exit spread, no commissions, 25 bp exit | EV3, DOI-5 |
| Target treated as certain | Monetisability, contract economics v2, DOI-5 |
| Three BS pricers, six "value at target" definitions | Valuation modules |

## Validation (gate G4)

1. **Calibration by EV decile**: realised P&L per $ at risk increases monotonically across predicted EV/R deciles; predicted mean within CI of realised per decile.
2. **Cost realism**: modelled entry/exit prices vs actual fills (journal) — bias within tolerance.
3. **Sanity vs literature**: unconditional average EV of long options across the universe is not materially positive before any selection.

## References

- Hull, J. *Options, Futures, and Other Derivatives*. Pearson — pricing, American exercise, binomial trees [verify]
- Natenberg, S. (2015). *Option Volatility and Pricing*, 2nd ed. McGraw-Hill [verify]
- Coval, J. & Shumway, T. (2001). Expected option returns. *Journal of Finance* [verify]
- Bakshi, G. & Kapadia, N. (2003). Delta-hedged gains and the negative market volatility risk premium. *Review of Financial Studies* [verify]
- Muravyev, D. & Pearson, N. (2020). Options trading costs are lower than you think. *Review of Financial Studies* [verify]
- Bjerksund, P. & Stensland, G. (2002). Closed form valuation of American options. Working paper, NHH [verify]
- Derman, E. (1999). Regimes of volatility. *Risk* [verify]
