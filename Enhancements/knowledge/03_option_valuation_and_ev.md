# 03 — Option Valuation and Expected Value

Status: **Draft v2** (reconciled to specification v1.1, 16 Sep 2026) · Capabilities: O2 Money measurement, O3 Expression search · Context: **C8 Valuation** (inputs from C4, C5, C6, C7) · Governing: spec §12; addendum §4, §7.2

## Question this method answers

> For a given thesis, how much money do we expect to make, after all costs and with honest uncertainty, per dollar at risk — for each way of expressing it (options and shares) — given that the thesis can resolve on any session from Day 1 to Day 20 and each expression can only be held until its own last exit session?

## Core principle

**Expected value = probability-weighted payoff over the paths the evidence says can happen, priced at the prices we would actually trade, on the session we would actually exit.**
Anything that treats a target as certain, prices exits at mid, values unresolved paths at unchanged spot, ignores time decay to the exit session, or uses a probability that is not calibrated is **not** an expected value. No legacy engine output (EV v2, EV3) is an expected value in AVSHUNTER.

## 1. Outcome model (shared by every expression of a thesis)

Use the thesis's selected geometry (exact invalidation L and target U, or no target) and its evidence packet (note 01).

For each expression define its **forced exit session** F = min(`last_exit_session`, time-stop session if its exit policy has one), counted within the window (F ≤ 20). `last_exit_session` is read from the expression, never recomputed.

Preferred — **path replay** on a common path set: for each historical analogue path j with weight w_j (same conditioning as the evidence packet):
- exit session k_j = first touch of U or L if it occurs by F, else F;
- exit spot S_j: U on target; **worse of L and that session's open** on stop; S₀ × (path close-to-close return to F) if unresolved at F;
- path volatility scaled to the C7 forecast where the analogue sample's realised volatility differs.

The path set must **reconcile** with the evidence packet: its cumulative incidence by session matches the packet within tolerance, otherwise the thesis is `NOT_VALUED`.

Alternative — **per-session incidence**: q_U(k), q_L(k) for k ≤ F, survival s(F), and the return distribution of paths unresolved at F (note 01).

Never collapse unresolved paths to "price unchanged": option value is convex in spot and the unresolved distribution carries the drift. With `target_state = NONE` there is no target barrier and no substitute reference level.

## 2. Pricing an option at exit

- **Model**: Black-Scholes-Merton with continuous dividend yield for European-style approximation; **American** (binomial CRR or Bjerksund-Stensland) for puts and for calls on dividend payers near ex-date (Hull, *Options, Futures and Other Derivatives* [verify]).
- **Implied volatility at entry**: back out σ₀ per contract from the mid (not a vendor IV of unknown timing).
- **IV at exit**: from C7 IV dynamics, e.g. σ_exit = σ₀ + β_d · ln(S_exit/S₀) + δ, where β_d is a fitted spot-vol slope; δ = 0 base, ± stress. State sticky-strike or sticky-delta (Natenberg; Derman on volatility regimes [verify]).
- **Time**: τ_exit = calendar time remaining to expiry after the exit session (sessions → calendar days via the exchange calendar).
- **Rate and dividends**: from data; missing → `NOT_VALUED` (no defaults).

## 3. Trading costs (the most common source of false edge)

- **Entry at the ask** (or ask + slippage); **exit at the bid**.
- Spreads at exit: `max(absolute floor, proportional share of value)` — out-of-the-money options have small values but similar absolute spreads; a proportional-only model overstates exit bids.
- **Commissions** per contract / share per side (matter for premiums < $1).
- **Borrow fee** for short shares over sessions held; day-count convention from configuration.
- Empirical note: effective spreads can be smaller than quoted spreads, but a rule must be validated on our fills before using anything better than quoted (Muravyev & Pearson, 2020 [verify]).

## 4. Payoff per expression

Let π_j be profit per unit on path j, R capital at risk per unit.

| Expression | Entry | Exit on path j | R |
|---|---|---|---|
| Long call / put (K) | A = ask + slip + c | V_j = bid-model(S_j, K, τ_j, σ_j) − c | A |
| Debit vertical (long K₁, short K₂, width W) | D = ask₁ − bid₂ + slips + 2c, require 0 < D < W | clip(bid₁,j − ask₂,j, 0, W) − 2c; at expiry intrinsic spread | D |
| Long shares (BULL thesis) | ask + c | bid_exit − c | (entry − S_L) incl. gap allowance + costs |
| Short shares (BEAR thesis) | proceeds = bid − c | − ask_exit − borrow_fee × S₀ × sessions_j (configured convention) − c | (S_L − bid) incl. gap allowance + expected borrow + costs |

π_j = exit − entry (short shares: proceeds − buy-back − fees). Carry per-share and per-contract units; ratios are unitless.

Early-assignment risk on the short leg of a vertical and hard-to-borrow recall risk on short shares are flagged, not ignored. Verticals when `target_state = NONE` exist only as approved fixed-width variants (note 05); the short strike caps payoff and is never a barrier.

## 5. Expected value, uncertainty and time normalisation

```
EV   = Σ_j w_j · π_j
EV/R = EV ÷ R
expected_sessions_held = Σ_j w_j · (sessions held on path j)
time_normalised_return = (EV/R) ÷ expected_sessions_held
```

**EV lower bound (single definition, addendum §4.3):**

```
for each stress scenario s ∈ {base, IV −Δ, IV +Δ, exit spread × m, stop gap}:
    EV_s(b), b = 1..B week-block bootstrap resamples of the path set
    LB_s = q-th percentile of EV_s(b)        (q from configuration)
EV_LB = min_s LB_s
RAEV  = EV_LB ÷ R
```

- RAEV is the ranking measure; time-normalised return is the first tie-break (spec C9).
- Evidence shrinkage is applied in C4; valuation does not re-shrink.
- Also report: forced-exit share (paths exiting at F), exit session distribution, stress results.

## 6. Consistency rules

1. All expressions of a thesis use **the same path set** (makes "option vs ticker" and "strongest expression" comparable).
2. One pricer, one cost convention, one session convention (XNYS sessions) for the whole pipeline; one EV_LB definition.
3. Exits at the earliest of resolution, `last_exit_session`, time stop, Day 20 — per expression.
4. Missing input (IV, quote, borrow, evidence, rate) → `NOT_VALUED` with reason; no defaults.
5. q_U + q_L + s = 1; EV reproducible from stored inputs and configuration versions.
6. Morning revaluation uses the same service over the remaining window (`remaining_sessions_to_last_exit`); it never moves `last_exit_session`.

## Known results to respect

- Expected returns on options are strongly negative for OTM puts and near zero or negative for many calls on average, largely because implied volatility exceeds realised volatility (volatility risk premium). A model that finds positive EV in most long options is likely wrong (Coval & Shumway, 2001; Bakshi & Kapadia, 2003 [verify]).
- Option returns are highly sensitive to transaction costs; many academic anomalies vanish after realistic costs.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| Heuristic "probability" and multipliers that improve negative EV; passed every row | Legacy `vanguard/ev_engine_v2.py` v2.1.0 (loaded) and root `ev_engine_v2.py` |
| Timeout at unchanged spot | EV3 |
| Probabilities at snapped grid, payoff at exact levels | EV3 |
| Proportional exit spread, no commissions, 25 bp exit | EV3, DOI-5 |
| Target treated as certain | Monetisability, contract economics v2, DOI-5 |
| Fixed hold buckets; model-limit rejections for holds ≠ 5/10/20 | EV3 |
| Three BS pricers, six "value at target" definitions | Valuation modules |

## Validation (gate G4)

1. **Calibration by RAEV / EV decile**: realised expression P&L per $ at risk increases monotonically across predicted deciles; predicted mean within the interval of realised per decile (C12 expression outcomes).
2. **Forced exits**: realised P&L of expressions exiting at `last_exit_session` consistent with valuation.
3. **Cost realism**: modelled entry/exit prices vs actual fills (journal) — bias within tolerance.
4. **Sanity vs literature**: unconditional average EV of long options across the universe is not materially positive before any selection.
5. **Time normalisation**: tie-break by time-normalised return does not reduce realised return per session.

## References

- Hull, J. *Options, Futures, and Other Derivatives*. Pearson — pricing, American exercise, binomial trees [verify]
- Natenberg, S. (2015). *Option Volatility and Pricing*, 2nd ed. McGraw-Hill [verify]
- Coval, J. & Shumway, T. (2001). Expected option returns. *Journal of Finance* [verify]
- Bakshi, G. & Kapadia, N. (2003). Delta-hedged gains and the negative market volatility risk premium. *Review of Financial Studies* [verify]
- Muravyev, D. & Pearson, N. (2020). Options trading costs are lower than you think. *Review of Financial Studies* [verify]
- Bjerksund, P. & Stensland, G. (2002). Closed form valuation of American options. Working paper, NHH [verify]
- Derman, E. (1999). Regimes of volatility. *Risk* [verify]
