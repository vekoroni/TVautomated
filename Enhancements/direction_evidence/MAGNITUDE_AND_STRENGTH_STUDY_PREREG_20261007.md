# Magnitude and relative-strength study: pre-registration (7 Oct 2026)

**Locked before any result is read.** Quant decision under ACK's delegation ("assume the responsibility of a quant trader"). Read-only; nothing gains authority.

## Why
- **No direction edge so far.** Three tests found none from price patterns: the pipeline's setups (7 Oct + WP1), five side rules, and the top-down trend read.
- **Magnitude is what options are paid for.** ACK's expressions are long calls, long puts or combinations. A long option pays on **magnitude** in its direction; a combination pays on magnitude either way.
- **Where the literature finds edge:**
  - volatility compression precedes expansion (magnitude);
  - **cross-sectional** relative strength over months (12-1 momentum, 52-week-high proximity) predicts relative returns.
- **This study tests those, with fixed rules and nothing fitted.**

## Data and universe
- **Source:** the same as the top-down study. Survivorship-free point-in-time top 3,122 by 20-session median dollar volume. Polygon grouped daily, 2021-10-08 → 2026-10-06.
- **Cuts:** every 10 sessions, from the first cut with 252 sessions of history.

## Part M: magnitude (does a big move come?)
- **Event BIG:** first passage of **±3 × daily ATR(14), either side**, within **20 sessions** (primary) and 60. Measured on highs/lows and on closes.
- **Move vs volatility:** |20-session close return| / (20-session realised volatility before the cut × √20). Above 1 means the move beat the volatility the market had seen, which is roughly what an option prices.
- **Fixed signals:**
  - **M1, coiled:** daily ATR(14)/close at or below the 20th percentile of the name's own previous 250 sessions, **and** weekly ADX < 20. Ranked by that percentile, lowest first.
  - **M2, pressure at the edge:** 5-session average volume ≥ 1.5 × the 50-session average, **and** close within 1 ATR of the 20-session high or low. Ranked by the volume ratio.
- **Statistic:** P(BIG) minus the same-cut base rate (all point-in-time names); and the mean move-vs-volatility ratio minus the same-cut mean. Reported for the **top 100**, the top 200 and all flagged names.

## Part R: relative strength (direction, cross-sectional)
- **Fixed signals:**
  - **R1, 12-1 momentum:** return from t−252 to t−21. Top 100 → UP, bottom 100 → DOWN.
  - **R2, 52-week-high proximity:** close / 252-session max high. The 100 nearest the high → UP; the 100 farthest → DOWN.
- **Outcomes:**
  - (a) first passage of ±2 ATR within 60 sessions, excess over same-cut drift, as in earlier studies;
  - (b) **relative 60-session return:** the name's return minus the universe median at that cut, signed by side.

## Inference and acceptance (same rules as before)
- **Episodes:** a name staying in the top list on consecutive cuts counts once.
- **Bootstrap:** date blocks of 6 cuts (60 sessions); **at least 8 blocks**, or no inference is made.
- **Accepted** when all of these hold:
  - the top 100 has a 95% lower bound > 0 on the primary outcome (M: P(BIG) excess at 20 sessions on highs/lows; R: relative 60-session return);
  - the point estimate is positive in both halves of the period;
  - the result is positive on both closes and highs/lows (M), or on both outcomes (a) and (b) (R).
- **Correction:** Holm across the four primary tests (M1, M2, R1, R2).
- **If accepted:** a candidate for C12 forward measurement, with no authority (CLAUDE.md rules 5 and 6; G1–G4).
