# Short-horizon direction study (1–5 sessions and intraday): results (7 Oct 2026)

- **Pre-registration:** `SHORT_HORIZON_DIRECTION_STUDY_PREREG_20261007.md`.
- **Script:** `short_horizon_direction_study.py`.
- **Raw output:** `short_horizon_direction_study_20261007.json`; records in `short_horizon_*_records_20261007.parquet`.
- **Scope:** read-only.
- **Data:**
  - daily: survivorship-free point-in-time top 3,122, 880 sessions, 2023-04 → 2026-09;
  - ETFs: 16;
  - intraday: 5-minute bars, 2025-09 → 2026-10;
  - pipeline side: replay panels.
- **Excess:** hit minus reference, in points.

## Primary family (Holm, 14 tests): nothing passes on its pre-registered side

| Test | Hit | Excess [95%] | Halves | Verdict |
|---|---|---|---|---|
| S1 top-down, stocks top 100, h=1 / h=5 (next open) | 49.3% / 49.2% | −0.2 / −0.4 | − / − | Not accepted |
| S2 5-day reversal, stocks, h=1 / h=5 | 49.9% / 49.8% | −0.1 / −0.1 | mixed | Not accepted |
| S3 previous-day continuation, stocks, h=1 / h=5 | 49.3% / 48.8% | −0.7 / **−1.2 [−1.9, −0.6]** | − / − | Not accepted (**significant reversal**, below) |
| S1 top-down, ETFs, h=1 / h=5 | 51.0% / 49.9% | +0.4 / −1.5 | +2.5 −1.5 / −0.3 −2.8 | Not accepted |
| S3 previous-day continuation, ETFs, h=1 / h=5 | 49.9% / 50.1% | −0.3 / −0.5 | mixed | Not accepted |
| **S4 the pipeline's own side**, h=1 / h=5 | 49.3% / 49.2% | +0.0 / +0.1 | ≈0 / ≈0 | Not accepted |
| I1 15-minute opening range, ETFs (09:45 → close) | 48.2% | −2.0 [−4.6, +0.6] | −3.3 / −0.5 | Not accepted |
| I1 15-minute opening range, stocks top 100 | 48.6% | −0.5 | −1.1 / +0.1 | Not accepted |

## What stands out (reported per the pre-registration)
- **Big one-day moves reverse in stocks.** S3 is significantly **negative** in both halves, at h=1 (close-to-close −1.6 [−2.3, −1.0]) and h=5 (−1.2 to −1.6). The day's biggest movers tend to give some of it back over the next 1–5 days. This is the documented short-term reversal.
  - **Status:** a confirmation candidate for the **opposite** side. The pre-registration says a significant negative is reported as reversal; it was not tested as its own primary.
- **Asymmetry in 5-day extremes (S2, exploratory).**
  - The 100 biggest 5-day **gainers fall** more than the market afterwards: DOWN side +4.3 to +4.6 at h=5.
  - The 100 biggest **losers keep falling**: the UP side is −2.6 to −4.6.
  - Both point to the **put side on extreme movers**. Exploratory only.
- **The opening-range day trade does not work on ETFs.** The first 15 minutes' direction does not carry to the close (48% hit). When it agrees with the daily bias it is worse (44%, exploratory).

## What this means
1. **At day and swing horizons, the pipeline's side, the top-down read and the opening range all call direction at a coin-flip rate**, consistent with the 20–60-session results.
2. **Measured short-horizon effects so far, all small, all candidates only:**
   - (a) EPS surprise on the event day (earnings study, pre-registered pass, +0.16% per trade);
   - (b) earnings gap agreeing with the pipeline's bias (exploratory, about +0.6% per trade on the day);
   - (c) reversal after big one-day moves in stocks;
   - (d) misses and 5-day gainers drifting down (the put side).
3. **These test direction only.** Whether a correct direction call is monetised by the selected option (ACK, 7 Oct) is a separate, conditional question, awaiting ACK's report.
