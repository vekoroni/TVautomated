# Top-down bias study: pre-registration (ACK 7 Oct 2026)

**Status: LOCKED, 7 Oct 2026.** ACK delegated the open choices: "assume the responsibility of a quant trader to identify the best solution to the queries". The decisions are in §7 with their reasons. No result had been read when this was locked. Read-only research; nothing changes the pipeline or gains authority.

## 1. Why
- **The pipeline's bias isn't evidence.** It comes from whichever daily setup is live (`engine.handoff_thesis`).
- **The audit says the flaw is in that logic.** WP1 (`WP1_DIRECTION_AUDIT_RESULTS_20261007.md`) found no direction edge in live setups as a whole, after episodes, matched placebos, seeds, closes and survivorship checks. The only consistent signal is on the **monthly** timeframe.
- **ACK's process:** read monthly, weekly and daily (then intraday) with the same indicators, before the detailed analysis.
- **ACK's rule:** "the pipeline should always establish its bias based on evidence".

## 2. Universe and data (survivorship-free)
- **Universe:** the point-in-time universe from `survivorship/` (top 3,122 by 20-session median dollar volume at each cut), delisted names included.
- **Bars:** Polygon grouped daily (split-adjusted), 2021-10-08 → 2026-10-06. This is the plan's 5-year limit.
- **Cuts:** every 10 sessions, from the first cut at which every timeframe's indicators are computable (monthly ROC(12) plus its 6-bar MA needs 18 months, so about Apr 2023) to the last cut with a full 60-session horizon.
- **Forming bars:** monthly and weekly bars are built from daily bars up to the cut. The current week or month is a **forming** bar: it's labelled with its completion and computed exactly as a trader sees it at the cut. Nothing after the cut is used.
- **Intraday (phase 2):** 60/15/5-minute bars from Polygon 5-minute data (Sep 2024 onwards, liquid universe), tested only as an **entry-timing** layer.

## 3. Each timeframe's state (ACK's chart indicators)
For each timeframe (M, W, D):

| Element | Indicator | Reading |
|---|---|---|
| Trend | MA5 | close vs MA5; MA5 vs its prior bar (rising/falling) |
| Momentum | ROC(12) and its 6-bar MA | ROC above/below ROCMA |
| Strength and its direction | ADX(14) with +DI/−DI (Wilder DMI) | TRENDING when ADX ≥ 25 and rising; its direction is the sign of (+DI − −DI) |
| Volatility | ATR(14) | expanding/contracting vs 5 bars earlier. Context only |
| Participation | Volume | bar volume vs its 20-bar average. Context only |

- **Timeframe state:**
  - **UP** when close > MA5, MA5 rising and ROC > ROCMA.
  - **DOWN** for the mirror.
  - **MIXED** otherwise.
- **Strength tag:** TRENDING_UP / TRENDING_DOWN when the ADX condition holds, otherwise WEAK.
- **Secondary only:** anchored VWAP (§7 Q2).

## 4. Outcome ("right direction")
- **Event:** first passage of ±k × daily ATR(14) from the cut close, with k = 2 (primary) and 3, within 60 sessions (primary) and 20.
- **Measured both ways:** on closes and on highs/lows, reported separately.
- **Reported in full:** UP-first, DOWN-first, NEITHER, AMBIGUOUS and DELISTED_BEFORE_RESOLUTION, with P(proposed), P(opposing) and P(unresolved), plus a Brier score.
- **Drift reference:** the same-cut UP share across the whole point-in-time universe.

## 5. The rule being tested
1. **Primary (fixed rule, nothing fitted):** a hierarchical top-down screen.
   - **Bias UP:** weekly UP **and** daily UP **and** monthly not DOWN.
   - **Bias DOWN:** the mirror.
   - **Otherwise NO BIAS**, which is a valid output.
2. **Ranking (fixed, for the top slice).** Order by:
   1. the number of timeframes (M, W, D) whose strength tag is TRENDING in the bias direction;
   2. then weekly ADX;
   3. then daily ADX;
   4. then ticker, for a deterministic tie-break.
3. **Secondary (exploratory, fitted).**
   - Train on the first half of the cuts, using all 27 (M, W, D) state patterns.
   - A pattern earns a side when its Holm-corrected excess over drift is > 0.
   - Test on the second half.
   - Exploratory only; it cannot pass §6 on its own.
4. **Entry timing (phase 2).** Among primary-biased tickers, does an aligned 60/15/5-minute state at the morning check improve the first-passage rate or the time to the move? This is ACK's pre-herd entry.
5. **Comparison:** the production rule's side (R0) on the same names and cuts, where it can be computed.

## 6. Acceptance (pre-set)
- **Test:** precision vs drift of the **top 100** primary-biased tickers per cut, with the 95% lower bound > 0.
  - Date-block bootstrap, blocks of 6 cuts (60 sessions, the horizon); **at least 8 blocks**, or no inference is made.
  - Episodes: a ticker whose bias persists across consecutive cuts counts once, at its first cut.
- **Robustness:**
  - positive point estimate in both halves of the period;
  - positive on closes and on highs/lows at k = 2;
  - the top 200 is also reported.
- **If it passes:** a confirmation candidate for C12 forward measurement. No decision authority (CLAUDE.md rules 5 and 6; G1–G4).

## 7. Decisions on the open questions (quant judgement, ACK's delegation, 7 Oct 2026)
1. **ADX direction → +DI/−DI.**
   - ADX is built from Wilder's directional movement; +DI and −DI are its own directional components. That makes them the textbook-consistent way to read the direction of a trend ADX calls strong.
   - Direction itself comes from price vs MA5 and momentum. DI only confirms the strength tag.
2. **VWAP on daily/weekly/monthly charts → anchored at the start of the parent period** (daily chart: week-to-date; weekly: month-to-date; monthly: year-to-date). It reads whether this period's buyers are in profit.
   - **Secondary only:** an anchor choice is an extra degree of freedom, and session VWAP has no meaning on a daily bar.
3. **Technical-signal dots → excluded.** They are platform-proprietary and can't be reproduced or measured. The pipeline's own setup detectors fill that role and are measured separately (WP1).
4. **Timeframe weighting → hierarchical, with monthly as a veto only.**
   - **Fewer degrees of freedom:** a fixed rule with nothing fitted can be tested on the whole period without a multiple-testing penalty.
   - **Monthly as a veto:** 5 years of data hold only ~4 independent monthly stretches (WP1), so monthly patterns can't be validated, only used to avoid trading against them.
   - **Weekly and daily decide:** they carry the timing a 20–60-session option trade needs.
   - **Fitted weights** are the exploratory secondary.

## Amendment A1 (7 Oct 2026, before any result was read)
- **Indicator validation against ACK's MSFT charts.** The last bar is the 6 Oct close.

| Indicator | ACK's chart | Study code |
|---|---|---|
| Daily MA5 / ADX / ATR / ROCMA | 519.54 / 39.23 / 12.21 / 4.26 | 519.54 / 39.22 / 12.21 / 4.26 |
| Weekly MA5 / ADX | 510.48 / 30.44 | 510.48 / 30.36 |
| Monthly MA5 / ROCMA | 477.13 / −5.70 | 477.45 / −6.46 (the gap is dividend adjustment) |
| Monthly ADX | 12.57 | 23.50 |

- **The monthly ADX miss.** Wilder smoothing needs far more than the 61 monthly bars that 5 years provide.
- **Amendment:** the ranking's strength count (§5.2, item 1) uses **weekly and daily only**. Monthly strength is recorded but not ranked. Monthly stays a veto (§7 Q4). Everything else is unchanged.
