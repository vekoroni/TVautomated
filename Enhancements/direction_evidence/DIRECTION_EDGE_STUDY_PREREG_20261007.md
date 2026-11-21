# Direction edge study: pre-registration (ACK 7 Oct 2026, "yes, run the study")

Written **before any result is read**. The script `direction_edge_study.py` implements exactly this. Read-only: stored replay panels plus canonical completed daily bars. No provider calls.

## Why
- **Lane hit rates may not be edge.** Lane A "level before invalidation" rates (55–70%) are mostly what a random walk gives from setup geometry. On the holdout check of 7 Oct, all setups were +0.7 pts above geometry and lane A +1.9 pts.
- **The side split looks like market drift.** BULL was +7.0 and BEAR −8.8, the pattern a rising market produces.
- **The question.** Do any setups, or any side rule, carry directional edge beyond **geometry and market drift**?

## Data
- **Panels:**
  - original: `Enhancements/outcomes/beh001/eval_v4`, 276 tickers;
  - holdout: `eval_v4_holdout`, 295 tickers never used to design a rule.
- **Coverage:** 102 cuts every 10 sessions, 2022-09-16 → 2026-09-28. Live setups (DETECTED / ACTIVATED) on 1d / 1w / 1mo, with close, trigger, invalidation, outcome level and ATR at the cut.
- **Bars:** canonical completed daily bars (`dir002_replay.read_bars`). Daily ATR(14) is the simple mean of the true range over 14 sessions.

## Part A: setup edge beyond geometry and drift
- **Population:** each directional setup whose level and invalidation are on opposite sides of the cut close (a = side × (level − close) > 0, b = side × (close − invalidation) > 0). Setups already past either are counted and excluded.
- **Outcome:** from the cut close, which is touched first with daily highs and lows, the level or the invalidation.
  - Horizon by timeframe: 1d **60**, 1w **120**, 1mo **250** sessions.
  - Both on one bar = AMBIGUOUS, excluded. Neither = CENSORED, excluded.
- **Geometry baseline:** b / (a + b), the driftless random-walk probability of reaching the level first.
- **Placebo (geometry + drift + volatility):** for each setup, **5 other tickers at the same cut** (seeded random, seed 20261007). Each gets the same side and the same a and b in units of its own daily ATR. The placebo rate is the share of placebo bets reaching the level first. It carries no setup information.
- **Edge = observed − placebo**, per setup: the outcome (1/0) minus its placebo rate. Geometry edge is also reported.
- **Groups:**
  - all; timeframe; state; side; timeframe × state;
  - lane A (`config/beh001_lanes_v1.json` `lane_a_trade_now`) vs not;
  - setup type × timeframe × state where n ≥ 200.
- **Statistic:** mean edge with a date-block bootstrap (blocks of 2 consecutive cuts), 2,000 resamples, seed 20261007, 95% interval. Reported for both panels and both periods (2022-09 → 2024-09-15, 2024-09-16 → 2026-09).
- **Real edge (pre-set):** holdout 95% lower bound > 0, **and** the point estimate positive on both panels in both periods.

## Part B: side rules (ticker direction)
- **Unit:** ticker-cut with at least one live setup.
- **Outcome:** first touch of ±k × daily ATR(14) within 60 sessions from the cut close, k ∈ {1, **2**, 3}, giving UP_FIRST / DOWN_FIRST. Ambiguous and neither are excluded.
- **Drift reference:** the same-cut share of UP_FIRST among all evaluated ticker-cuts in the panel.
- **Excess** for a pick = hit − (drift share for UP picks, or 1 − drift share for DOWN picks).
- **Rules** (each picks UP, DOWN or abstains):

| Rule | Definition |
|---|---|
| **R0** | Production `engine.handoff_thesis` on the ticker-cut's live setups (1d, plus 1w / 1mo for the conflict walk) |
| **R1** | R0 on a **price-checked** live set: drop setups whose cut close is past their invalidation or past their level |
| **R2** | R1. When R1 is unassigned with live setups on both sides, score each side by the best `p_event_at_limit` of its live setups (duration evidence v3, own group, all ages). Pick the higher side if the margin is ≥ 0.05; otherwise abstain |
| **R3** | Trend only. Score = sign(close − SMA20) + sign(SMA20 − SMA20 five sessions earlier) + sign(ROC12 − mean of ROC12 over the last 6 sessions). UP if ≥ +2, DOWN if ≤ −2, otherwise abstain |
| **R4** | The R2 pick where R2 picks; otherwise the R3 pick |

- **Statistic:** mean excess, date-block bootstrap as in Part A, plus coverage, for both panels and both periods.
- **Adopt (pre-set, as for the 1–2 Oct rules):** holdout k = 2 excess 95% lower bound > 0, **and** the point estimate positive in both periods on both panels.

## Not decided by this study
Nothing gets authority from this study. Its output is evidence for an ACK decision on what the side rule, lanes and rank are built on (CLAUDE.md rules 5 and 6).
