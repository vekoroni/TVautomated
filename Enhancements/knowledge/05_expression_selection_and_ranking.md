# 05 — Expression Generation, Selection and Ranking

Status: **Draft v2** (reconciled to specification v1.1, 16 Sep 2026) · Capabilities: O3 Expression search, O5 Ranking, O6 Morning decision · Contexts: **C6 Expression, C9 Ranking, C10 Execution Readiness** · Governing: spec §6, §10, §13, §14; addendum §6

## Question this method answers

> Of all the credible ways to trade this thesis — options and shares — which is strongest by risk-adjusted EV, where is the money (option or ticker), and across all theses what is the best order to consider them, excluding only what is invalid or untradeable?

## 1. Generate the expression set (per frozen thesis, C6)

Business-approved scope (ACK, 15–16 Sep 2026):

| BULL thesis | BEAR thesis |
|---|---|
| long call | long put |
| debit call vertical | debit put vertical |
| long shares | short shares (subject to borrow) |

Only families allowed by the ticker's **instrument capabilities** (C2) are generated; a ticker without an option chain (`OPTIONS_DATA_UNAVAILABLE`) still gets its share expression.

**Bounded generation** — "all" means a defined set derived from the thesis, not every listed contract, and **no contract is pre-selected by a heuristic score, delta band or reachability filter**:

| Expression | Candidate generation (bands and limits from configuration) |
|---|---|
| Long option | Thesis side; listed expiries whose `last_exit_session` falls in the useful part of the window, up to maximum DTE; strikes within a band around reference price and target (or invalidation when `target_state = NONE`) |
| Debit vertical | `target_state = LEVEL`: long leg from the long-option strike set, short leg at or beyond the target, approved widths, 0 < debit < width. `target_state = NONE`: approved fixed-width variants only, else `VERTICALS_NOT_APPLICABLE_NO_TARGET` |
| Long / short shares | One expression; short shares require borrow available and fee known (`BORROW_DATA_UNAVAILABLE` otherwise) |
| Exit policies | Base policy (target / invalidation / last exit session) plus approved time-stop variants, each a separate expression |

**Last exit session** (spec C3, S5): `last_exit_session = min(window Day 20, last session before expiry − exit buffer)`, stored as an **absolute session**, immutable. Shorter-dated options are allowed; the thesis window is never shortened. A different contract found later is a new expression with a new `expression_id`.

Expressions are generated **after** the thesis is frozen and **before** valuation. The context records counts generated, excluded and why.

## 2. Tradeability (the only per-expression exclusion)

Two-sided, fresh quote; spread fraction ≤ execution limit; minimum size / open interest; expiry not before the minimum usable session; for short shares, borrow available and fee known. Failing expressions are recorded with reason codes and not valued.

Liquidity *within* limits is not a gate — its cost enters valuation through entry/exit prices.

## 3. Value every tradeable expression (note 03)

Same path set, same cost conventions, per-expression forced exit → EV, R, EV/R distribution, EV_LB, **RAEV = EV_LB ÷ R**, time-normalised return, stress results; cheap-convexity profile attached for display (note 04).

## 4. Strongest expression and money location (C9)

- `strongest = argmax RAEV` over valued expressions of the thesis; tie-breaks: **time-normalised return** (desc), then **liquidity cost** (asc), then `expression_id`.
- Money location: OPTION / TICKER / BOTH / NONE (RAEV > 0 test on option families vs the share expression), NOT_VALUED with reason. Shares for both BULL and BEAR make the "option or ticker" question answerable in both directions.
- **Hysteresis** for day-to-day stability: keep the previous run's strongest expression unless the new leader's RAEV exceeds it by more than switching cost plus a noise margin (from bootstrap interval overlap; `ranking.hysteresis_margin`). Never keeps an expression with RAEV ≤ 0 or no longer tradeable; every application recorded.

## 5. Rank instead of gate

```
Rank key = (RAEV desc, time_normalised_return desc, liquidity_cost asc, expression_id)
```

- All former gates become inputs to EV or uncertainty: opposed or unsupported evidence (lower probabilities — the thesis is still valued, spec S1), weak evidence (wider intervals → lower EV_LB), rich IV (pricing), missing target (stop / forced-exit paths only), wide-but-allowed spreads (costs).
- `RAEV ≤ 0` stays visible, labelled `NO_POSITIVE_EDGE`; theses with all expressions `NOT_VALUED` stay visible with reasons.
- Cheap convexity, dealer positioning (GEX) and trigger/timing features are displayed, **not** rank keys, until validated.
- No hand-weighted composite scores inside the ranking objective.
- The OpportunityBook contains every valued expression with its rank, not only leaders.

## 6. Portfolio awareness (ranking is not independent bets)

Many tickers move together (sector, market beta). A top-ranked list can be one bet repeated.
- Report **cluster/sector concentration** of the top N and the average pairwise return correlation of their underlyings — reported, not applied to rank.
- Optional diversified shortlist for display: greedy selection taking the next-best RAEV whose correlation with already-selected names is below a threshold.
- Sizing (when approved): fractional Kelly on calibrated EV and variance only after validation; full Kelly is too aggressive under estimation error (Thorp [verify]; MacLean, Thorp & Ziemba [verify]).

## 7. Morning (live) decision (C10)

Manual run ~15 minutes after the US open:
1. Scope: strongest expression of every thesis with RAEV > 0, plus open positions (`execution.revalue_scope`); everything else stays recorded.
2. **Thesis check first**: invalidated or resolved since the evidence session → `INVALIDATED` / outcome recorded, not re-ranked.
3. Remaining window from the original clock; each expression's `remaining_sessions_to_last_exit` from its immutable `last_exit_session`.
4. Refresh quotes → tradeability → valuation over the remaining window (same C8 service) → re-rank with hysteresis.
5. Action: `BUY_NOW` / `BUY_SMALL` / `MONITOR` / `NO_EDGE` / `INVALIDATED`; data problems recorded as data states, never invented verdicts; no later overrides.
6. Macro and event context displayed for manual review only.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| One contract chosen by weighted greeks score, liquidity checked afterwards | Contract selector; EV3 rejects 525 for liquidity |
| Serial gates on labels before valuation | Vanguard regime floors, EIL EOD verdict, EOD status rules, tier thresholds, monetisability BLOCK |
| Rank recomputed with different weights after publication | Lab UI server `_compute_priority_score` |
| Gates removing better opportunities | Filters removed CALL rows with higher target-hit rate (11.4% vs 8.1%) |
| Invented upstream verdict in the morning | Execution gate `READY_EXECUTE/BUY_NOW` from missing campaign verdict |
| DTE required to cover a fixed hold bucket | `dte_sessions ≥ hold + buffer` rule |

## Validation (gate G4)

1. **Rank monotonicity**: realised expression P&L per $ at risk increases across RAEV deciles (Spearman rank IC > 0 with interval excluding 0, walk-forward).
2. **Strongest expression**: realised return of the chosen expression ≥ average of the other valued (non-selected) expressions of the same thesis — requires outcomes for non-selected expressions (C12).
3. **Money location**: option-vs-share choices agree with realised relative returns more often than chance.
4. **No-gate check**: expressions the legacy gates would have excluded (including OPPOSED theses) perform in line with their RAEV decile.
5. **Hysteresis**: stability gained without a material loss of realised RAEV.
6. **Concentration**: top-decile results not driven by a single cluster/date.

## References

- Grinold, R. & Kahn, R. (1999). *Active Portfolio Management*. McGraw-Hill — information coefficient, fundamental law [verify]
- Thorp, E. (2006). The Kelly criterion in blackjack, sports betting and the stock market. *Handbook of Asset and Liability Management* [verify]
- MacLean, L., Thorp, E. & Ziemba, W. (2011). *The Kelly Capital Growth Investment Criterion*. World Scientific [verify]
- Sinclair, E. (2020). *Positional Option Trading*. Wiley — choosing option structures for a directional view [verify]
