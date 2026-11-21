# WP1 direction-study audit: results (7 Oct 2026)

- **Pre-registration:** `WP1_DIRECTION_AUDIT_PREREG_20261007.md`.
- **Script:** `wp1_direction_audit.py`.
- **Raw output:** `wp1_direction_audit_20261007.json`.
- **Scope:** read-only. Same panels as the 7 Oct study; both panels are survivor-only. Survivorship was measured separately and does not bias direction (`survivorship/SURVIVORSHIP_RESULTS_20261007.md`).
- **Edge** = observed − placebo, in points. Episodes: each setup counted once, at its first cut. Bootstrap blocks: 12 cuts (~120 sessions).

## What the audit changed
- **Rows → episodes.** Original panel 77,811 rows → 57,995 episodes; holdout 84,171 → 63,097. About a quarter of the 7 Oct sample was the same setup counted again.
- **Unresolved, now published (holdout, highs/lows).** Level first 15,081; invalidation first 26,924; **neither within the horizon 4,757 (10%)**; ambiguous 30; cut too recent 7,912. On closes, neither rises to 13%.
- **Matched placebo.** Same sector and volatility quintile; 26% fell back to volatility-only matching.

## Results (holdout, highs/lows unless stated)

| Group | Episodes | Matched edge [95%] | On closes | 5 seeds (original placebo) | Original panel, matched |
|---|---|---|---|---|---|
| All setups | 42,035 | **+0.2** [−0.7, +1.1] | +0.2 | +0.1 / −0.1 / +0.1 / +0.1 / +0.0 | −0.1 |
| Lane A | 4,120 | −0.2 [−1.3, +0.9] | +0.3 | +0.4 / −0.0 / +0.7 / +0.7 / +0.2 | +0.4 |
| Daily | 24,314 | −0.2 | −0.4 | ≈ −0.5 | −0.4 |
| Weekly | 14,312 | +0.4 | +0.7 | ≈ +0.5 | −0.3 |
| **Monthly** | 3,409 | **+2.6** [+0.8, +4.7] | +2.8 | +1.5 … +2.9 | **+3.6** [+0.8, +7.2] |
| BULL / BEAR | 22,772 / 19,263 | −0.1 / +0.6 | −0.2 / +0.6 | | −0.1 / −0.0 |

**The three 7 Oct candidates: none survives.**

| Setup | Holdout matched | Closes | Original | Verdict |
|---|---|---|---|---|
| SOW → LPSY 1w ACTIVATED (240 episodes) | +1.1 [−2.5, +5.1] | +2.6 | +3.3 | Not confirmed. P1 −2.3; the 7 Oct +7.1 shrinks to +1.1 on a matched placebo |
| SOW → LPSY 1mo DETECTED (352) | **−0.5** [−1.9, +2.0] | −0.5 | +9.4 | **Rejected.** The 7 Oct +4.4 came from repeated rows |
| Seller Absorption Breakdown 1mo DETECTED (512) | **+5.5** [−0.6, +12.5] | **+5.7** [+0.4, +11.2] | +22.9 | Not confirmed. Positive in both periods, on both panels and both event types, but not significant after correction. **The best candidate** |

## A limit of the method (disclosed, not fixed after the fact)
- **Monthly groups span only 4 bootstrap blocks** (~4 independent 120-session stretches). With 4 blocks the bootstrap cannot test anything.
- **The two Holm "passes" are artefacts.** Buyer Absorption Breakout 1mo DETECTED and Crabel Compression Breakout 1mo DETECTED have p = 0.0 only because all 4 blocks had the same sign. Buyer Absorption is −0.7 on the original panel anyway. **Neither is a finding.**
- **Fix for the pre-registration:** future pre-registrations require ≥ 8 blocks before a p-value is reported.

## What this means
1. **The 7 Oct null result stands, and is not a method artefact.**
   - Counting episodes, matching the placebo on sector and volatility, varying the seed, using closes or highs/lows, and checking survivorship all leave **no direction edge in the live setups as a whole or in lane A**.
   - The flaw is in the logic. Daily setup presence does not call direction.
2. **Monthly structure carries the only consistent signal.**
   - +2.6 (holdout) and +3.6 (original) points over the matched placebo, on both event types, with every seed positive.
   - **Statistically it cannot be confirmed with 4 years of data** (4 independent periods).
   - It fits ACK's top-down view: the higher timeframe is where direction lives.
3. **Seller Absorption Breakdown 1mo** is the one setup worth forward confirmation (C12). Nothing gains authority.
4. **Data constraint.** Polygon on this plan gives 5 years. Confirming monthly evidence needs 15–20 years of survivorship-free daily bars, which is a data purchase decision for ACK.
