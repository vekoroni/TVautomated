# Phase 6, corrected results: interpretation (9 Oct 2026)

**Correction.** The first run joined model rows on a non-unique key (several setups share a contract on the same
Friday), multiplying rows. Both scripts now join on a unique row id with one-to-one checks; the counts match the input
(121,407 trades; 12,023 setup ATM test trades, the same as the universe test). Numbers below are from the fixed run
(`PH6_RESULTS.md`, `PH6B_RESULTS.md`).

## Pre-registered results

| Family | Result |
|---|---|
| **V, cheap volatility** (IV / HAR-RV forecast) | **V2 passes:** CHEAP − RICH, setup trades = +16.9 pts, CI [+7.0, +26.1], both halves. **V3 passes:** CHEAP − RICH, random entries = +11.8 pts, CI [+8.4, +14.8], both halves. V1 fails: CHEAP alone −28%. |
| **E, exits into strength** | No rule beats the weekly herd exit (E1 −1.7, E2 −1.2, E3 −0.5, E4 +0.1 pts). Median option peak 0.99 × entry; 21% ever reach +50%. |
| **S, short holds** | No hold beats it significantly (S1 +1.7, S2 +1.1, S3 +1.5, S5 +2.4 pts; Holm p ≥ 0.28). A one-session hold already averages −37%. |

## Exploratory (not pre-registered): the entry spread dominates

Setup trades, ATM, test period, by entry spread (ask − bid) / mid:

| Spread | n | Mean | Median | Hit |
|---|---|---|---|---|
| ≤ 5% | 408 | −2.1% | −11.2% | 48% |
| 5–10% | 1,066 | −13.3% | −32.2% | 42% |
| 10–20% | 2,623 | −20.6% | −47.9% | 38% |
| 20–40% | 2,970 | −27.4% | −50.0% | 32% |
| > 40% | 4,956 | −56.5% | −80.0% | 13% |

Median spread 30%. Spread ≤ 10% and CHEAP: n 169, mean −4.7%, median −4.1%, hit 49%. The live pipeline's contract
selection already applies a 25% spread limit (ACK E15); the universe test's simple ATM rule did not.

## Routes forward

1. Pre-register the liquidity rule (spread ≤ 10% vs wider; × CHEAP; vs random; halves).
2. Entry at the mid by limit order (ACK executes): show the mid and the spread cost on every card.
3. Rank by expectancy after costs: spread cost and vol ratio as rank inputs once confirmed (rank, never gate).
4. Then timing: trigger acceptance plus the intraday build-up.
