# WP1 direction-study audit: pre-registration (ACK 7 Oct 2026, "start the read only work")

Written **before any result is read**. Read-only. It re-runs the 7 Oct direction study, Part A (`direction_edge_study.py`) with the corrections the independent review asked for (`AVSHUNTER_Ticker_Direction_Review_and_Rectification_Plan_20261007.docx`). The same panels (`eval_v4`, `eval_v4_holdout`), cuts and horizons are used.

## Corrections
1. **Episodes, not repeats.**
   - The panel repeats one setup at every cut while it stays live (36% of holdout rows; up to 49 cuts). It also repeats it under both LOCAL and CAMPAIGN scope.
   - **Episode** = (ticker, timeframe, setup type, setup date from the ID, state), counted once at its **first** cut.
2. **Dependence.** Date-block bootstrap with blocks of **12 cuts (~120 sessions)** instead of 2. Horizons: 1d 60, 1w 120, 1mo 250 sessions.
3. **Unresolved published.**
   - For observed setups, the counts of LEVEL_FIRST, INVALIDATION_FIRST, NEITHER (no touch within the horizon), AMBIGUOUS (both on one bar) and NO_HORIZON (cut too recent) are reported.
   - Edge is still computed on resolved setups only, as before, and labelled as such.
4. **Closes and highs/lows.** First touch is measured on daily highs/lows (as before) **and** on daily closes, reported separately.
5. **Placebo robustness:**
   - **Seeds:** the original placebo (5 donors, same cut, same side, same ATR distances), run with **5 seeds** (20261007 … 20261011).
   - **Matched:** a **matched placebo** of 5 donors from the same sector (`data/universe/polygon_liquid_universe.csv`) and the same ATR%-of-price quintile at the cut. If the cell has fewer than 5 donors, it falls back to the same quintile, and the fallback share is reported.
   - Beta matching is not done (no index series in this pass), and that is stated.
6. **Multiple testing.** The two-sided bootstrap p-value (2 × the smaller tail share at 0) for every setup-type group with **≥ 100 episodes** on the holdout. **Holm** correction across that family, at α = 0.05.
7. **Survivorship.** Both panels are survivor-only (today's `config/tickers.csv`). This is stated on every result. Its size is measured separately (`survivorship/`).

## Reported per group
Groups: all; timeframe; state; side; lane A; and setup type × timeframe × state. Each group reports:
- the number of episodes;
- the edge vs placebo, per seed and pooled;
- the edge vs the matched placebo;
- the edge vs geometry;
- by period (split 2024-09-15);
- on highs/lows and on closes;
- the Holm-adjusted p-value.

## How the three 7 Oct survivors are judged
SOW → LPSY 1w ACTIVATED; SOW → LPSY 1mo DETECTED; Seller Absorption Breakdown 1mo DETECTED.

- **Survives the audit** if, on episodes, all of the following hold:
  - the holdout matched-placebo edge is positive with a 95% lower bound > 0;
  - the edge is positive on both highs/lows and closes;
  - it is positive in both periods on both panels;
  - its Holm-adjusted p < 0.05.
- **Otherwise** it is reported as **not confirmed**.

Either way, it gains no authority: a survivor only becomes a forward-confirmation candidate (C12).
