# Direction edge study: results (7 Oct 2026)

- **Pre-registration:** `DIRECTION_EDGE_STUDY_PREREG_20261007.md`.
- **Script:** `direction_edge_study.py`.
- **Raw output:** `direction_edge_study_20261007.json`.
- **Scope:** read-only, stored panels plus canonical bars. Original panel 276 tickers, holdout 295 tickers, 102 cuts from Sep 2022 to Sep 2026.
- **Pass test (pre-set):** holdout 95% lower bound > 0, **and** a positive point estimate in both periods on both panels.

## Part A: do setups reach their level more than a placebo with the same geometry and drift?
Edge = observed − placebo. The placebo is 5 other tickers at the same cut, same side, same distances in ATR.

| Group (holdout n) | Holdout edge [95%] | Original edge [95%] | Verdict |
|---|---|---|---|
| All setups (52,878) | **+0.2 pt** [−0.6, +0.9] | −0.7 [−1.5, +0.0] | No edge |
| Lane A (5,936) | **+0.8** [−0.7, +2.2] | −0.2 [−1.9, +1.6] | No edge (lane hit rates are geometry) |
| Daily / weekly / monthly | −0.3 / +0.4 / +1.4 | −0.9 / −0.8 / +0.7 | No edge |
| Activated / detected | −0.3 / +0.2 | −0.9 / −0.7 | No edge |
| BULL / BEAR | −0.1 / +0.4 | −1.1 / −0.2 | No edge (the 7 Oct BULL/BEAR split was drift) |

**Setup types that pass the pre-set test.** 3 of 39 groups, all bearish and on higher timeframes:

| Setup | Holdout edge [95%] | Original edge [95%] | Periods (orig P1/P2, hold P1/P2) | Note |
|---|---|---|---|---|
| **SOW → LPSY, 1w, activated** | **+7.1** [+2.9, +11.8] | +4.5 [+0.7, +8.6] | +5.2 / +3.8 / +4.1 / +9.6 | In today's lane A |
| **SOW → LPSY, 1mo, detected** | **+4.4** [+1.4, +6.9] | +11.7 [+4.6, +18.1] | +3.6 / +12.9 / +6.4 / +3.9 | Lane C today |
| **Seller Absorption Breakdown, 1mo, detected** | **+8.4** [+3.8, +13.0] | +20.5 [+11.2, +30.4] | +4.3 / +24.0 / +12.4 / +7.1 | Lane C today |

One more group, SOS → LPS 1mo activated, showed +10.0 on the holdout but **fails**: it was not estimable on the original panel, and its holdout P1 was −1.0.

**Caveat:** 39 groups were tested. Requiring both panels and both periods guards against chance, but these three are candidates to confirm with C12 forward data, not certainties.

## Part B: does any side rule beat market drift at "which way first" (±k ATR, 60 sessions)?
| Rule (coverage) | k = 2 holdout excess [95%] | Original | Hit rate | Verdict |
|---|---|---|---|---|
| R0 today's rule (63%) | −0.5 pt [−1.6, +0.6] | −0.7 | 48.2% | Fails |
| R1 price-checked (61%) | −0.3 [−1.4, +0.7] | −0.7 | 48.4% | Fails |
| R2 + evidence tie-break (73%) | −0.3 [−1.4, +0.7] | −0.3 | 48.7% | Fails |
| R3 trend only (40%) | +0.0 [−1.3, +1.2] | −0.4 | 49.8% | Fails |
| R4 R2 then trend (84%) | −0.3 [−1.3, +0.6] | −0.2 | 48.8% | Fails |

The same holds at k = 1 and k = 3. **No side rule, including chart-style trend reading, calls direction better than the market's drift** on this universe and period.

## What this means
1. **Direction.** Neither the production rule nor any tested alternative has a measured edge. Making MSFT "bullish" via price checks or trend would not, on this evidence, make direction calls more accurate. It would only change which tickers get a side.
2. **Lanes.** Lane A's 55–70% "level before invalidation" is geometry plus drift. On a matched placebo, lane A shows no edge.
3. **Where edge exists.** Three bearish, higher-timeframe distribution setups (SOW → LPSY weekly activated; SOW → LPSY and Seller Absorption monthly detected) beat their placebo on both panels in both periods.
4. **Not invalidated.** This study measures direction and level-reaching. It does not measure option payoff, entry timing ("pre-herd") or scenario value. Those need their own outcome tests (C12).
