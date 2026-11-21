# Short-horizon direction study (1–5 sessions and intraday): pre-registration (7 Oct 2026)

Locked before any result is read. Read-only, with no provider calls. ACK, 7 Oct 2026:
- "our preferred trading is day or swing"
- "20–60-session horizons … this was me being over cautious … use what we have to make informed decisions and build from that"
- "if we can trade ETFs/QQQ/SPY most of these will be day trades"

## Why
- **Earlier tests used the wrong horizon.** They measured direction at 20–60 sessions, where 5 years of data give few independent periods.
- **Short horizons give hundreds of independent days** from the same data, and they are ACK's trading horizon.

## Data
- **Daily:** Polygon grouped daily (survivorship-free, split-adjusted), 2021-10-08 → 2026-10-06. Point-in-time universe: the top 3,122 by 20-session median dollar volume at each session.
- **ETFs:** SPY, QQQ, IWM, DIA, XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY, SMH (16).
- **Intraday:** canonical 5-minute regular-session bars (`data/canonical/payloads/intraday_bar`), 2025-09-02 → 2026-10-05.
  - Universe: the 16 ETFs, plus each session's top 300 stocks by 20-session median dollar volume (point-in-time) that have bars.
  - If one session holds several files, the most recently acquired is used.
- **Pipeline sides:** the stored replay panels (`eval_v4`, `eval_v4_holdout`) at their 10-session cuts.

## Outcomes
- **Daily:**
  - the sign of the close-to-close return over h = 1, 3, 5 sessions from the signal session's close;
  - and, as an executable variant, from the **next session's open** to the close h sessions after the signal (ACK enters after the open).
- **Intraday (day trade):**
  - entry at the close of the first 15 minutes (3 bars, ~09:45 ET, the morning-run time), exit at the session close;
  - variants: the 30-minute opening range (6 bars, entry ~10:00), and exit at the next session's close.
- **References:**
  - **stocks:** the same-session share of the universe moving up over the same window (cross-sectional drift);
  - **ETFs:** each ETF's own up-share over the whole period, for the same window (time-series base rate; for SPY, the market's own direction is the thing being judged).
- **Excess** = hit (1/0) − reference for the side called (reference, or 1 − reference for DOWN).

## Signals (fixed rules; nothing fitted)
- **S1, top-down bias** (the locked top-down rule, amendment A1): daily cut at every session.
  - Stocks: the top 100 by weekly-and-daily trending count, then weekly ADX, then daily ADX.
  - ETFs: all biased ETF-days.
- **S2, short-term reversal (stocks):** the 5-session return.
  - The 100 most negative → UP; the 100 most positive → DOWN.
- **S3, previous-day continuation:** the side of the previous session's close-to-close return.
  - Stocks: the 100 largest moves up (→ UP) and the 100 largest down (→ DOWN), by |return| / ATR(14).
  - ETFs: every ETF-day.
  - A significantly negative excess means **reversal**, and is reported as such.
- **S4, the pipeline's own side (R0, production `handoff_thesis`)** at the panel cuts. All ticker-cuts with a side; h = 1, 3, 5.
- **I1, opening-range direction (intraday):** the sign of (close of the 3rd bar − open of the 1st bar).
  - ETFs: every ETF-day.
  - Stocks: the top 100 by |first-15-minute return| / daily ATR%.
- **I2:** I1 when it agrees with the daily S1 bias from the previous close. Secondary.

## Inference and acceptance
- **Bootstrap:** date blocks of 20 sessions (daily signals) or 10 sessions (intraday); 2,000 resamples, seed 20261007.
- **Minimum:** at least 8 blocks, or no inference.
- **Overlap:** for h > 1, signals on consecutive sessions overlap. The block length (≥ 4 × h) absorbs this, and "independent windows" (n ÷ h per name) are reported.
- **Primary family (Holm, α = 0.05; 14 tests):**
  - S1, S2, S3, S4 on stocks at h = 1 and h = 5 (executable next-open entry; S4 from the cut close);
  - S1 and S3 on ETFs at h = 1 and h = 5;
  - I1 on ETFs and on stocks (exit at the close).
- **Pass:** Holm-adjusted p < 0.05; the 95% lower bound of excess > 0; positive in both halves of the period; and, for the daily signals, positive on both the close-to-close and next-open variants.
- **If it passes:** a C12 forward-confirmation candidate. No authority (CLAUDE.md rules 5 and 6; G1–G4).

## Also reported (not in the family)
- h = 3;
- the top 200;
- by side;
- I2;
- 30-minute opening range;
- next-day exit;
- per-ETF results.

## Pending (separate pre-registrations)
- Post-earnings drift: needs the earnings history fetch; the cost is measured, awaiting ACK.
- The ETF macro board's lean: pending the point-in-time replay check.
