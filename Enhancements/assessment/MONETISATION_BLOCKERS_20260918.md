# Why the pipeline cannot yet produce monetisable trades — end-to-end assessment

18 September 2026 · prepared for ACK · evidence-based, no recommendations without measurement

Every claim below is tied to a measurement in this repository. Where something is unmeasured, it says so. The
pipeline is not broken in one place; it fails to produce a tradeable edge for eleven separate reasons, and fixing
any one of them alone changes nothing.

---

## 0. The one-paragraph answer

The pipeline picks a direction it cannot predict, expresses it in contracts that expire before the thesis can play
out, protects it with a stop that ordinary volatility hits in two sessions, pays a spread that consumes a third of
the premium, and then filters the survivors with a rule that rejects every large winner. Each defect is
independently measured. Together they turn a book of 1,500 names into four tickets a day whose expected return is
negative.

---

## 1. Direction: no demonstrated edge (fatal, unresolved)

| Study | Scope | Result |
|---|---|---|
| Direction input evidence (`Enhancements/direction_evidence/`) | Recorded runs | Nothing passes |
| Discovery replay 2022–2026 | 4 years, full universe | 50.9% at 1 session; not significant |
| Plan A H1–H12 (pre-registered) | 2022–2026, train/test | None passes |
| H9 gap drift event study | 8,337 events | Fails; sign flips between train and test |
| O1–O5 options signals | 1 year of weekly chains | O4 and O2 exploratory only (IC ±0.015) |
| Study B, volatility selling | 576,852 trades | No edge after fills and tails |

The pipeline's own CALL/PUT split is ~51%. **Everything downstream — targets, stops, contract choice, sizing —
is built on a direction call with no measured skill.** This is the root cause; the rest are amplifiers.

Robust findings worth keeping: 5-session reversal at 1 day, and distance from the 52-week low improving the thesis
(IC +0.02). Both are cross-sectional tilts, not per-name calls.

## 2. The issuing rule rejects the winners (fatal, fix designed)

`signals.decide()` requires the **cautious** value (worst of three volatility scenarios, exit at the bid) above
zero, governed as `outcome.signal.min_cautious_return`.

| Rule | Closed | Mean | Profitable | ≥ +100% |
|---|---|---|---|---|
| Everything bought | 2,992 | −55.2% | 10.7% | 2.24% |
| **Cautious > 0 (shipped)** | **20** | **−49.7%** | **5.0%** | **0.00%** |
| Spread ≤ 10% of mid (one filter) | 196 | −31.5% | 16.8% | 4.59% |
| Top 5 per session by cautious rank | 45 (16 closed) | −18.8% | 25.0% | 6.25% |

Every one of the backtest's largest winners (+479%, +471%, +320%, +275%) had a **negative** cautious value. The
rule also violates design rule R11 ("rank, don't gate"): hard exclusions are permitted for integrity, eligibility
and tradeability — not for a forecast. The same number used as a *ranking* is strong (correlation 0.44, monotonic
across quintiles).

## 3. Exit geometry destroys the thesis before it resolves (major, evidence complete)

| Median | Tickets | All candidates |
|---|---|---|
| Stop distance in expected moves over the hold | **0.63** | 0.53 |
| Target distance in expected moves | 1.76 | 1.36 |
| Sessions to stop | **2** | 2 |

20 of 21 scored tickets stopped out. Paired test over 638 trades: removing the stop inside the hold improves the
mean by **+2.9 points (t = 3.21)** and raises the profitable share from 30.7% to 36.5%. The premium already caps
the loss, so an underlying stop inside the hold costs value without limiting risk.

## 4. Contracts expire before the plan ends (major, guard added, source unfixed)

- Tickets held contracts covering a median **0.54** of their planned hold.
- The most common exit under every rule is the expiry cap (364–515 of ~1,000 exits), with time value gone.
- Contracts with ≤ 10 days to expiry returned **−75.6%** (219 closed); 21–30 days returned −44.9%.

**Root cause is an internal contradiction**, visible in tonight's run: the macro router assigns most names the
6–10 day horizon, the actuarial layer recommends a **20-session** hold, and the selector buys a **15–29 day**
contract. Three components disagree about how long the trade lasts.

## 5. Execution cost consumes the edge (major, partly fixed)

- Legacy contracts: round-trip spread ≈ **35% of premium**; realised loss −45% mean.
- Pre-fix selector: median chosen spread **40% of mid**. After today's fix: **13.3%** (tonight's run).
- Far out-of-the-money contracts quote at **73–120% of mid** — buying at the ask and selling at the bid loses half
  the value immediately. This is why the "cheap lottery ticket" approach fails: mean −62% to −78%.

## 6. The tail we are hunting is not in the instruments we buy (structural)

Across 12,462 rebuilt contracts and 2,992 real ones: **2.24% returned ≥ +100%**, 0.43% ≥ +200%, best **+515%**.
No 100x exists anywhere in the recorded data. A 100x needs a far out-of-the-money contract with months of life;
**stored chains only ever captured 8–45 days to expiry**, so the strategy cannot even be tested, let alone traded.

## 7. Data the pipeline does not have (structural, needs purchase or capture)

| Missing | Consequence |
|---|---|
| Real-time option quotes (entitlement is **delayed 15 minutes**) | Tickets are priced on a stale premium; delta adjustment is a first-order patch |
| Long-dated chains (> 45 DTE) | Convex, event-driven strategies untestable |
| Trade-level flow (sweeps, blocks) | The signal most competing products use is unavailable |
| Intraday bars beyond ~200 tickers | Quote adjustment mostly falls back to "not adjusted" |
| Point-in-time event calendar | No event study possible on history; earnings convexity untested |
| Full universe (3,320 of 6,500 target; scanner manifest 28 days stale) | Half the opportunity set is never seen |

## 8. Data integrity faults (moderate, partly fixed)

- **DQ-12 price history**: 47 of 3,618 tickers carry breaks (splits, ticker reuse). Fixed 17 Sep; 5 truncated in
  tonight's run.
- **Corporate actions in the price store**: unrepaired; the forecast and base rates inherit them.
- **GEX (10 defects, `Enhancements/gex/GEX_INVESTIGATION_20260914_214012.md`)**: the gamma flip algorithm is wrong
  (median published flip 22.3% from spot versus 5.5% recomputed), walls are open-interest walls, the execution
  layer **invents** a GEX map from hard-coded anchors, and market-level GEX has never been delivered because the
  chain request always sends a `date` parameter the provider rejects for the current session. Consumers that
  change decisions: execution gate (0.75× size on 81.6% of rows), wall-break scorer, catastrophe gate, exit engine.
- **US Money Index**: headline 35 versus components summing to 32 — rejected every run, correctly.
- **Macro**: display-only by decision, but still 28-day-stale scanner input and PARTIAL quality.

## 9. Gate architecture produces empty days (major, design-level)

Tonight's book: 1,498 rows → 738 CONTRACT_REPAIR, 594 MANUAL_REVIEW, 166 BLOCK, **0 actionable**. Only 521 rows
have a contract at all. Of those, 108 pass quality tests, 5 have a positive cautious value, and **0 survive the
contract guard**.

The legacy pipeline is gate-heavy by construction (execution gate, EIL verdicts, final actions, catastrophe gate,
monetisability), and the rebuild's R11 ("rank, don't gate") has only reached the measurement and configuration
layers. Gates compound multiplicatively: eleven 70%-pass gates leave 2% of the book.

## 10. Nothing has been validated forward (process)

- EV3 authority retired; the new value model runs in shadow with no authority.
- The signal ticket trust gate (40 closed signals over 15 issue sessions, lower bound above zero) has **0 tickets**
  so far.
- The gap-up reversal forward test began yesterday: 5 events recorded.
- Scoring infrastructure is real: 19,910 prediction records, 17,164 option marks, automatic after every run.

Measurement is the one part of this system that works as designed.

## 11. Product framing (strategic)

The pipeline is built to answer "what will this stock do?" and to prove profitability on average. Competing tools
mostly answer "what is unusual right now?" and publish candidates, showing winners without the denominator. Our own
data reconciles the two: at 2.24% of trades returning ≥ +100%, a service publishing 100 alerts a day produces two
200% winners a week while its average alert loses money. **We have been solving a harder problem than the products
we are comparing ourselves with, using thinner data.**

---

## What is NOT the problem

- **Contract selection quality** — fixed today: median spread 40% → 13.3%.
- **The valuation engine** — ranks option outcomes at 0.44 correlation, monotonic across quintiles, and is roughly
  calibrated (predicted −39% versus realised −47%).
- **Measurement and governance** — scoring, base rates, expression marks, configuration registry and forward tests
  all work.
- **Morning quote handling** — three defects found and fixed on 17 Sep (delayed-feed staleness, quote capture,
  same-day quote reuse).

---

## Ordered remediation

| # | Fix | Why this order | Effort |
|---|---|---|---|
| 1 | Replace the issuing gate with quality rules plus ranked daily cap (R11) | Ends zero-trade days, uses the measure that works | Hours |
| 2 | Resolve horizon / hold / contract-DTE contradiction; require the contract to outlive the hold | Removes the expiry-cap exit that ends most trades | 1 day |
| 3 | Remove the underlying stop inside the hold; keep target, hold and expiry cap | Measured +2.9 points, t = 3.21 | Hours |
| 4 | Event convexity research (earnings first): buy cheap volatility into dated catalysts | Where large multiples actually cluster; data already present | 1–2 days |
| 5 | Cross-sectional score (O4, O2, reversal, 52-week-low distance) across many names | Turns small ICs into a book-level edge | 2 days |
| 6 | Extend chain capture to 3–12 months; price trade-level flow with the provider | Makes convex and flow strategies testable at all | Days, plus cost |
| 7 | Restore the universe (scanner run; 3,320 → 6,500) | Doubles the opportunity set | Hours |
| 8 | Retire or repair GEX; fix the money index producer | Stops broken inputs reaching size and exit decisions | 1–2 days |
| 9 | Keep the forward record running throughout | Only route to authority under G1–G4 | Continuous |

**Honest expectation:** items 1–3 stop the pipeline destroying value and will produce daily tickets with a smaller
negative expectation. Items 4–6 are where a positive edge could plausibly come from. Nothing measured so far
supports trading size today.
