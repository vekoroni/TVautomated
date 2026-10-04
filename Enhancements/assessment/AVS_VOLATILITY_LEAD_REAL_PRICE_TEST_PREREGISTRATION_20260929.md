# Volatility lead — real option price test, pre-registration (29 Sep 2026)

Approved by ACK, 29 Sep 2026: "approved, test the volatility lead on Phantom option prices". Written before any
result is seen. Read-only: `data/phantom/phantom_history.db` (`chain_snapshots`, end-of-day MarketData chains with
bid, ask, IV, Greeks; weekly from about May 2024 for most tickers) and the 29 Sep replay rows.

## The lead being tested

The replay (`AVS_HISTORICAL_REPLAY_STUDY_PREREGISTRATION_20260929.md`, exploratory section) found that long options
on calm stocks (bottom third of ATR percentile within the session) beat same-side options by 3–6 points at about
39 sessions, calls and puts alike, every year — but options were priced at 1.1 × realised volatility.

## Questions

1. **Premium:** is real implied volatility on calm stocks' options a larger multiple of realised volatility than on
   other stocks? (If so, the modelled edge is at least partly an artefact.)
2. **Real returns:** from the real ask at entry to the real bid at exit, do calm stocks' options beat same-side
   options on the same date?

## Design (fixed now)

- **Feature, point in time:** the replay row's Discovery `atr_percentile_rank` at its session *s*; tercile within
  that session across all replayed tickers. Entry date *d* = the first Phantom quote date after *s* and within 7
  calendar days (the feature is known before entry).
- **Contracts, both sides for every ticker-date:** the call and the put with DTE nearest 90 (75–110), strike nearest
  5 % in the money (call K ≈ 0.95 S, put K ≈ 1.05 S); a second pair nearest-ATM with DTE nearest 45 (30–60).
  Entry requires bid > 0, ask > 0 and spread ≤ 35 % of mid (same filter for every group).
- **Entry and exit:** buy at the entry date's ask; sell the same OCC symbol at the bid on the first quote date at
  least 28 calendar days (≈ 20 sessions) and, separately, 56 calendar days (≈ 40 sessions) later, within a 10-day
  window; otherwise missing (reported). Exit bid of 0 is a real −100 %.
- **Excess:** return minus the mean return of all contracts of the same side and type entered that date.
- **Periods:** entries in 2024, 2025, 2026 (to the last date with a matured exit). Uncertainty: bootstrap over
  entry-date blocks of four weeks, 90 % intervals.
- **Modelled vs real:** for the same contracts, the replay's model return (Black–Scholes at 1.1 × 20-day realised
  volatility, 6 % round-trip spread) is computed beside the real return, to measure the artefact directly.
- **Criterion (pre-registered):** the lead is confirmed if calm stocks' real excess is positive with the 90 %
  interval above zero in at least two of the three periods and positive in the third, for the ITM 90-day contract
  at the 40-session exit.

## Amendment before results (29 Sep 2026, data limit found in a 3-ticker trial; no result examined)

Phantom snapshots store expiries only up to 56 days (checked AAPL and KO, every month 2024–2026), so the 90-day
contract and the 56-day exit do not exist in the data. Amended design:

- **Primary contract:** 5 % in the money, DTE nearest 56 (40–60), exit at the first quote date ≥ 28 calendar days
  later (≈ 20 sessions). **Second contract:** nearest ATM, DTE nearest 45 (30–60), same exit.
- **Benchmark:** the replay's modelled excess for the calm tercile at hold 20 sessions (computed after this
  amendment, like-for-like), and the model return of the same real contracts (1.1 × realised volatility).
- **IV:** where the snapshot's `iv` is missing (e.g. KO before Jul 2024, ~half of rows from mid-2026), it is
  inverted from the quoted mid with Black–Scholes.
- **Criterion unchanged in form:** calm-stock real excess positive with the 90 % interval above zero in at least two
  of the three periods and positive in the third, primary contract, 28-day exit.

## Not claimed

Advisory research only; no gate, rank or authority.

## Results (appended 30 Sep 2026; design as amended above)

Run: `Enhancements/direction_evidence/volatility_lead_real_price_test_20260929.py` → 320,839 real contracts,
1,755 tickers, 150 weekly entry dates (5 Jan 2024 – 25 Sep 2026), 93.4 % with a 28-day exit quote; IV from the
snapshot for 287,617, inverted from the mid for 33,222. Analysis `volatility_lead_real_price_analysis_20260929.py`;
data `.claude_scratch/int001/vol_lead/`.

**Q1 — premium.** Median real implied / 20-day realised volatility: calm tercile 1.21–1.25, middle 1.08–1.13,
volatile 0.89–0.98 (both contract types, every year). The replay's 1.1 assumption under-priced calm stocks' options
and over-priced volatile stocks' options.

**Q2 — real returns, 28 days, ask entry / bid exit.** Pre-registered criterion (ITM56, calm): **NOT CONFIRMED.**
Calm-tercile excess over same-side, same-date contracts: +0.34 % (2024, interval −0.01 % to +0.83 %), −0.27 % (2025),
−0.15 % (2026). ATM45 calm: +1.0 %, 0.0 %, −0.9 %. No tercile shows a consistent excess.

**The artefact, measured directly.** The same contracts priced with the replay's model (1.1 × realised volatility)
show calm excess +12.2 % / +5.1 % / +6.0 % (ITM56) and +16.1 % / +9.3 % / +7.2 % (ATM45), all intervals above zero.
The volatility lead was produced by the pricing assumption, not by the market.

**Absolute real cost of a long option.** Mean real return after 28 days: −18 % to −22 % in every tercile, contract
type and year; about 30 % of contracts gained. The replay's modelled option returns (about −4 % at 20 sessions) were
far too optimistic; real option EV on these signals is much more negative.

**Conclusion.** No evidence of an option edge from volatility compression. Together with the replay (no directional
edge from price-derived attributes), the pipeline currently has no measured source of positive EV for long options.
