# 05 — Expression Selection and Ranking

Status: **Draft** · Capabilities: O3 Expression search, O5 Ranking, O6 Morning decision · Contexts: C6 Expression, C8 Ranking, C9 Execution Readiness

## Question this method answers

> Of all the ways to trade this thesis, which is strongest — and across all theses, what is the best order to consider them, excluding only what is invalid or untradeable?

## 1. Generate the expression set (per thesis)

Business-approved set (15 Sep 2026): **long calls / long puts, debit verticals, short shares for BEAR theses** (long shares for BULL theses: open question Q1).

| Expression | Candidate generation |
|---|---|
| Long option | Thesis side; expiries with `dte_sessions ≥ hold + exit_buffer`; strikes spanning delta ≈ 0.15–0.85 |
| Debit vertical | Long leg from the long-option set; short leg at or beyond the structural target, or at fixed widths when no target; 0 < debit < width |
| Short shares | BEAR thesis only; requires borrow available and fee known |

Expressions are generated **after** the thesis is frozen and **before** any valuation — no contract is "selected" by a heuristic score.

## 2. Tradeability (the only per-expression exclusion)

Two-sided quote; spread fraction ≤ execution limit for the hold bucket; minimum size/open interest; quote age within limit; for shorts, borrow available. Failing expressions are recorded with reason codes and not ranked.

Liquidity *within* limits is not a gate — its cost enters valuation through entry/exit prices.

## 3. Value every tradeable expression (note 03)

Same path set, same cost conventions → EV, R, EV/R distribution, **RAEV = EV_LB per $ at risk**, stress results, cheap-convexity profile (note 04).

## 4. Strongest expression and money location

- `strongest = argmax RAEV` over valued expressions of the thesis; tie-break by higher cheap-convexity score, then lower spread cost, then shorter DTE.
- Money location: OPTION / TICKER / BOTH / NONE (RAEV > 0 test), NOT_VALUED with reason.
- Hysteresis for day-to-day stability: keep yesterday's strongest expression unless the new one's RAEV exceeds it by more than the cost of switching plus a noise margin (derived from bootstrap CI overlap).

## 5. Rank instead of gate

```
Rank key = (RAEV desc, cheap_convexity_score desc, liquidity_cost asc, thesis_id)
```

- All former gates become inputs to EV or uncertainty: opposed evidence (lower probabilities), weak evidence (wider CI → lower EV_LB), rich IV (pricing), missing target (stop/timeout only), wide-but-allowed spreads (costs).
- `RAEV ≤ 0` stays visible, labelled `NO_POSITIVE_EDGE`.
- No hand-weighted composite scores inside the ranking objective.

## 6. Portfolio awareness (ranking is not independent bets)

Many tickers move together (sector, market beta). A top-ranked list can be one bet repeated.
- Report **cluster/sector concentration** of the top N and the average pairwise return correlation of their underlyings.
- Optional diversified shortlist: greedy selection taking the next-best RAEV whose correlation with already-selected names is below a threshold.
- Sizing (when approved): fractional Kelly on calibrated EV and variance only after validation; full Kelly is too aggressive under estimation error (Thorp [verify]; MacLean, Thorp & Ziemba [verify]).

## 7. Morning (live) decision

Manual run ~15 minutes after the US open:
1. Re-hydrate live quotes for ranked expressions.
2. Thesis check: live price through invalidation → thesis invalidated (record outcome), not re-ranked.
3. Re-run tradeability and valuation with live prices (same core); re-rank.
4. Action from rank position and live RAEV (e.g. BUY_NOW / BUY_SMALL / MONITOR / NO_EDGE) under one policy; no later overrides.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| One contract chosen by weighted greeks score, liquidity checked afterwards | Contract selector; EV3 rejects 525 for liquidity |
| Serial gates on labels before valuation | Vanguard regime floors, EIL EOD verdict, EOD status rules, tier thresholds |
| Rank recomputed with different weights after publication | Lab UI server `_compute_priority_score` |
| Gates removing better opportunities | Filters removed CALL rows with higher target-hit rate (11.4% vs 8.1%) |
| Invented upstream verdict in the morning | Execution gate `READY_EXECUTE/BUY_NOW` from missing campaign verdict |

## Validation (gate G4)

1. **Rank monotonicity**: realised P&L per $ at risk increases across RAEV deciles (Spearman rank IC > 0 with CI excluding 0, walk-forward).
2. **Strongest expression**: realised return of the chosen expression ≥ average of the other valued expressions of the same thesis.
3. **No-gate check**: expressions that the old gates would have excluded but rank highly perform in line with their RAEV decile.
4. **Concentration**: top-decile results not driven by a single cluster/date.

## References

- Grinold, R. & Kahn, R. (1999). *Active Portfolio Management*. McGraw-Hill — information coefficient, fundamental law [verify]
- Thorp, E. (2006). The Kelly criterion in blackjack, sports betting and the stock market. *Handbook of Asset and Liability Management* [verify]
- MacLean, L., Thorp, E. & Ziemba, W. (2011). *The Kelly Capital Growth Investment Criterion*. World Scientific [verify]
- Sinclair, E. (2020). *Positional Option Trading*. Wiley — choosing option structures for a directional view [verify]
