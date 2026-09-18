# Making a long call / long put strategy work — research programme

18 September 2026 · ACK · grounded in published results, mapped to data we already hold

Our own studies show no edge in predicting direction from daily bars. The published literature does not claim one
either. What it does document is a set of **conditional** edges — mostly inside the options market itself — that a
long call / long put book can be built on. Each is stated below with its published effect size, what it needs, and
what we already have.

---

## 1. The finding that changes our economics first

**Muravyev and Pearson (2020), *Options Trading Costs Are Lower than You Think*, RFS 33(11).**
Effective spreads for traders who time execution are **20–40% of the quoted spread**; the average effective spread
is a quarter smaller than conventional estimates.

Our backtest assumed the worst case — buy at the ask, sell at the bid — so a 10% quoted spread cost the full 10%
round trip. At 30% effectiveness that cost is nearer 3%.

| Backtest result | Full quoted spread | At 30% effective spread (approx.) |
|---|---|---|
| Top cautious quintile, guard applied | −22.7% | ≈ **−15%** |
| Top 5 per session, ranked | −18.8% | ≈ **−11%** |

Still negative, but it says a meaningful part of our measured loss is an execution assumption rather than a market
fact. **Action: re-run the harness with mid-price and timed-limit fill models and report all three.**

## 2. Buy options only when volatility is cheap

**Goyal and Saretto (2009), *Cross-section of option returns and volatility*, JFE 94, 310–326.**
Sorting on the difference between historical realised volatility and at-the-money implied volatility, the long leg
(realised ≫ implied) earns an economically and statistically significant monthly return on straddles and
delta-hedged options; robust to liquidity, industry and risk factors.

Our own data agrees without our having looked for it: backtest winners were bought at implied volatility
**0.69×** our forecast, losers at 0.86×.

**We have everything needed**: HAR-RV forecast per ticker per session, realised volatility from the price store,
implied volatility per contract in the stored chains.

## 3. Read the options market, don't predict the stock

| Study | Published effect | Our equivalent |
|---|---|---|
| **Cremers and Weinbaum (2010)**, JFQA 45, 335–367 — deviations from put-call parity | Stocks with relatively expensive calls beat those with expensive puts by **50 bps per week** | This is our **O2** (call-put IV spread); we measured IC 0.015, t 2.7, stable across halves |
| **Pan and Poteshman (2006)**, RFS 19(3) — put-call **volume** ratio | Low put-call ratio beats high by **40 bps next day, > 1% next week**; driven by non-public information | We only built the **open-interest** version (O4, IC −0.015, t −3.3). The stronger volume version is computable from stored chains |
| **Johnson and So (2012)**, JFE — option-to-stock **volume** ratio (O/S) | Lowest decile beats highest by **0.34% per week (19.3% a year)** | Not built. Needs option volume (chains, present) and share volume (price store, present) |

These are cross-sectional and modest per name, which is exactly why they need breadth — and why the expression
must be chosen by edge size (shares for small edges, options where the expected move is large).

## 4. Where the large multiples actually live: events

**Chung and Louis (2016), *Earnings announcements and option returns*; Xing, Zhang and others on straddles around
announcements.** Straddles bought **before** earnings earn positive average returns, against the well-documented
negative average for straddles generally. Traders underestimate volatility before announcements and overestimate
it after; a long-before / short-after portfolio earned about **14.4% over a one-month holding period**, strongest
when pre-formation volatility was low.

This is the best-documented route to the outcome ACK wants (large multiples), and the pipeline already has an
earnings calendar and catalyst engine. We have never tested a single event strategy.

## 5. What to avoid: lottery strikes

**Boyer and Vorkink (2014), *Stock Options as Lotteries*, Journal of Finance 69(4).** Options with high expected
skewness — cheap, far out-of-the-money — are systematically overpriced; the gap between low- and high-skew options
runs **10–50% per week**. Investors pay a premium for the lottery, and intermediaries collect it.

Our far-out-of-the-money study measured exactly this: −62% at 10% out, −73% at 17% out, −78% at 19% out, with
quoted spreads of 73–120% of mid. **Stay at or near the money.** The 100x trade is a documented losing bet as a
policy.

---

## The strategy this implies

A long call / long put book with four conditions, each drawn from a published result and testable on our harness:

1. **Volatility is cheap** — implied below our realised-volatility forecast by a governed margin (Goyal-Saretto).
2. **The options market points the same way** — the combination of call-put IV spread, put-call volume ratio and
   option-to-stock volume ratio (Cremers-Weinbaum, Pan-Poteshman, Johnson-So).
3. **Strike near the money, contract outliving the plan** — avoid the skew premium (Boyer-Vorkink) and the expiry
   cap (our own backtest).
4. **Execution timed, not taken** — limit orders inside the quote, cost measured against all three fill models
   (Muravyev-Pearson).

Plus an **event sleeve**: buy volatility into dated earnings, exit at the announcement (Chung and Louis).

Weak-signal names are traded in **shares**; only names whose expected move clears the effective spread get an
option. That is the "expression by edge size" rule, now with published effect sizes to calibrate it.

## Build order

| # | Step | Data | Output |
|---|---|---|---|
| 1 | Re-run the existing backtest under mid and timed-limit fills | In hand | True economics of what we already do |
| 2 | Build O/S ratio and put-call **volume** ratio; add to the signal set | Chains + price store | Two new signals with published effect sizes |
| 3 | Volatility-mispricing screen (implied vs forecast), Goyal-Saretto style | In hand | The entry condition for buying options at all |
| 4 | Composite cross-sectional score; decile spread with costs, by year | In hand | Information ratio; shares book viability |
| 5 | Earnings sleeve: buy before, exit at announcement | Earnings calendar + chains | Convex book with documented prior |
| 6 | Expression rule: shares vs long option on expected move versus effective spread | Above | The daily ticket list |

Every step is measured on the existing harness, pre-registered, with costs subtracted and multiple-testing control.
Published effects decay after publication and are usually gross of costs, so each must survive **our** data and
**our** fills before it earns size.

## Sources

- Goyal and Saretto (2009), JFE — https://personal.utdallas.edu/~axs125732/CrossOptionsJFE.pdf
- Muravyev and Pearson (2020), RFS — https://academic.oup.com/rfs/article-abstract/33/11/4973/5732665
- Cremers and Weinbaum (2010), JFQA — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968237
- Pan and Poteshman (2006), RFS — https://www.mit.edu/~junpan/volume.pdf
- Johnson and So (2012), JFE — https://www.travislakejohnson.com/pdfs/Johnson%20So%20OS%202012%20(JFE).pdf
- Boyer and Vorkink (2014), JF — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1787365
- Chung and Louis (2016), earnings announcements and option returns — https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2886040_code402462.pdf
- Xing, Zhang, straddles around earnings — https://www.ruf.rice.edu/~yxing/straddle_201305_03.pdf
