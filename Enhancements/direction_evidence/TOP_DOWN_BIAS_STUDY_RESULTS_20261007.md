# Top-down bias study: results (7 Oct 2026)

- **Pre-registration:** `TOP_DOWN_BIAS_STUDY_PREREG_20261007.md`, locked, plus amendment A1 made before any result.
- **Script:** `top_down_bias_study.py`.
- **Raw output:** `top_down_bias_study_20261007.json`; records in `top_down_bias_records_20261007.parquet`.
- **Scope:** read-only.
- **Universe:** survivorship-free point-in-time top 3,122 by dollar volume. 89 cuts, 2023-04-03 → 2026-10-06; 277,858 name-cuts.
- **Indicators:** validated against ACK's MSFT charts (A1).

## What the rule produced
- **Bias counts:** UP 36,344, DOWN 34,343, NO BIAS 195,817, UNAVAILABLE 11,354.
- **Per cut:** about 800 names biased; the top 100 and top 200 are ranked from those.

## Results
Excess over same-cut drift, in points. Episodes counted once at first entry. Blocks of 60 sessions.

| Event | Top 100 [95%] | Top 100 hit rate | Top 200 | All biased | Halves (top 100) |
|---|---|---|---|---|---|
| **±2 ATR, 60 sessions, highs/lows (primary)** | **−0.4** [−3.0, +2.0] | 50.3% | +0.1 [−1.7, +1.8] | +0.1 [−1.2, +1.4] | −1.3 / +0.6 |
| ±2 ATR, 60 sessions, closes | −0.6 [−3.0, +1.9] | 50.2% | −0.1 | +0.1 | −1.7 / +0.7 |
| ±2 ATR, 20 sessions, highs/lows | −0.2 [−2.9, +2.4] | 50.5% | −0.2 | −0.2 | −1.4 / +0.9 |
| ±3 ATR, 20 sessions, closes | +0.7 [−3.0, +4.6] | 52.0% | +0.3 | −0.8 | −1.5 / +2.8 |
| ±3 ATR, 60 sessions, highs/lows | −0.7 [−3.6, +2.7] | 50.7% | −0.5 | +0.0 | −2.4 / +1.2 |

- **By side:** UP and DOWN are both within ±1 point everywhere.
- **Secondary (fitted, 27 patterns):** no pattern survives Holm correction on the training half, so nothing reached the test half.
- **Verdict: NOT ACCEPTED** on all three pre-set checks.

## What this means
1. **A classic top-down trend read does not call direction better than the market's drift** on liquid US stocks over 3.5 years, survivorship-free.
   - The read: monthly not against; weekly and daily aligned on MA5, ROC vs its average, and ADX/DMI.
   - It fails for the top 100, the top 200 and every biased name, on closes and on highs/lows, at both distances and horizons.
   - Its first-half results are negative and its second-half results slightly positive, which is what noise looks like.
2. **Three independent tests now agree:**
   - the pipeline's setups (7 Oct study plus the WP1 audit);
   - five side rules, including a simple trend rule;
   - this top-down read.
   **Price-pattern direction, on its own, has no measurable edge in this universe.** This matches the published evidence that short-horizon direction in liquid stocks is close to unpredictable from price alone.
3. **What this does not test:**
   - **Magnitude:** whether a big move comes, either way, which is what long options and combinations are paid for.
   - **Cross-sectional relative strength** over months (documented momentum effects).
   - **Event-driven drift.**
   - **Entry timing inside a move** (ACK's pre-herd edge).
   These are the candidates where evidence of an edge exists in the literature, and they are the next pre-registered tests.
