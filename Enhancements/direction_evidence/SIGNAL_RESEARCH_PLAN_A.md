# Signal research plan A — pre-registration

Status: **pre-registered 17 Sep 2026, before any result for these signals was computed** · ACK decision: A and B in parallel, A first.

## Why
The item 4 evidence (commits `36d4f13`, `5682c46`) showed the pipeline's direction logic has no demonstrable edge over 2022–2026. Before any directional input can reach the value model (drift / conditional probabilities), it must pass this plan. Pre-registering hypotheses, horizons, splits and pass criteria limits data mining.

## Data and split
- Price store `ohlcv_daily`, all tickers with ≥ 320 complete bars; DQ-12 windows excluded (one-bar move ≥ 10×, sub-cent).
- Evaluation dates: every 5th session (non-overlapping for h ≤ 5), cross-sections with ≥ 100 tickers.
- **Train: 2022-09 → 2024-12. Test: 2025-01 → 2026-08.** Signals, sign and horizon are fixed on train; test is looked at once.
- Liquidity universe: 20-session median dollar volume ≥ $5M (optionable proxy), stated and also reported without the filter.

## Hypotheses (sign expected, horizons 5 / 10 / 20 sessions — the option holding window)
| ID | Signal | Definition (point-in-time) | Expected sign | Literature / prior evidence |
|---|---|---|---|---|
| H1 | Short-term reversal | − past 5-session return | + | Jegadeesh 1990; replay IC −0.05 at 1 session |
| H2 | Residual reversal | − past 5-session return net of the cross-sectional median | + | Blitz et al. 2013 |
| H3 | Intermediate momentum | past 252 − past 21 session return | + | Jegadeesh-Titman 1993 |
| H4 | 52-week-high proximity | close / 252-session high | + | George-Hwang 2004 |
| H5 | 52-week-low distance | close / 252-session low − 1 | + | replay: improves discovery thesis |
| H6 | Stale move | sessions since the last 20-session high/low break (move age) | − | replay move_age_bars IC −0.014 (5/5 years) |
| H7 | Close vs 20-session VWAP proxy | close / (Σ typical price × volume / Σ volume) − 1 | − (contrarian) | replay vwap_bias −7.7 bps (5/5 years) |
| H8 | Abnormal volume with return | 1-session return sign × log(volume / 20-session median volume) | + (continuation after informed volume) | Gervais et al. 2001 |
| H9 | Gap drift | overnight gap ≥ 2 ATR with volume ≥ 2× median: sign of gap (event proxy) | + over 20 sessions | post-event drift |
| H10 | Low volatility | − 60-session realised volatility | + | Ang et al. 2006 |
| H11 | Idiosyncratic volatility | − residual volatility vs the cross-sectional median return | + | Ang et al. 2006 |
| H12 | Trend quality | 60-session return / 60-session realised volatility (risk-adjusted trend) | + | time-series momentum |

Options-based hypotheses (stored weekly chains Sep 2025 → Sep 2026; single period, no train/test split possible — reported as exploratory, confirmation required on forward sessions):
| ID | Signal | Expected sign | Literature |
|---|---|---|---|
| O1 | Implied skew: 25-delta put IV − ATM call IV | − | Xing-Zhang-Zhao 2010 |
| O2 | Call-put IV spread at the same strike | + | Cremers-Weinbaum 2010 |
| O3 | IV − realised volatility forecast | − | Bali-Hovakimian 2009 |
| O4 | Put/call open-interest ratio | − | Pan-Poteshman 2006 |
| O5 | Change in ATM IV over 1 week | − | Ang et al. 2010 |

## Metrics
Per date: Spearman IC of the signal vs forward log return net of the date's cross-sectional median; top-minus-bottom quintile net return. Across dates: mean, Newey-West t (lag = ceil(h / 5)), share of positive dates, per-year means.

## Pass criteria (all required)
1. Train: sign as expected, |t| ≥ 2.5, positive-date share ≥ 55%.
2. Test: same sign, |t| ≥ 2.0, Benjamini-Hochberg q = 0.10 across all hypothesis × horizon pairs tested on test.
3. Same sign in at least 4 of 5 calendar years.
4. Economic size: the top-minus-bottom quintile 10-session net return must exceed the median round-trip share spread (Abdi-Ranaldo) of the traded names; for an options expression, the expected move must be large enough that the path valuation model (increment 2/3) turns positive after option spreads.
5. Not explained by H1 (reversal): partial IC controlling for past 5-session return stays same-signed and |t| ≥ 2.0 on test.

A signal passing 1–5 becomes a **candidate direction input** (shadow only) and is re-tested on forward sessions by the outcome scorer before any authority (G1–G4).

## Addendum 1 — H9 gap drift as an event study (pre-registered 17 Sep 2026, before any H9 event result)

The cross-sectional design could not evaluate H9 (fewer than 100 events per date). It is re-specified as an event study.

- **Event:** session t with |open_t − close_(t−1)| ≥ 2 × ATR14 (ending t−1) and volume_t ≥ 2 × median volume of the 20 sessions before t. Universe: liquid (20-session median dollar volume ≥ $5M, ending t−1), DQ-12 clean over [t−260, t+20]. At most one event per ticker per 20 sessions (the first), so outcome windows do not overlap within a ticker.
- **Entry:** close of the event session t (point-in-time: the gap and its volume are known by then). **Outcome:** log return from close_t to close_(t+h), h = 5 / 10 / 20, net of the median return of the liquid universe over the same window, signed by the gap direction (+ for gap up, − for gap down).
- **Expected sign:** + (post-event drift in the gap direction). Reported split by (a) gap up / gap down and (b) whether session t closed beyond its open in the gap direction ("held") or not ("faded") — pre-declared as the only two splits.
- **Statistics:** mean signed net return with standard errors clustered by event date; share positive; train 2022-09 → 2024-12, test 2025-01 → 2026-08; per-year means.
- **Pass:** train mean > 0 with t ≥ 2.5; test same sign with t ≥ 2.0 (Benjamini-Hochberg q = 0.10 across horizon × split); same sign in at least 4 of 5 years; economic — mean signed 10-session net return greater than the median round-trip share spread of the event names (and reported against the median ATM straddle cost where chain data exists).

## Addendum 2 — forward test of the gap-up reversal (H9R), pre-registered 17 Sep 2026 (ACK)

Source of the hypothesis: the H9 event study test period (2025-01 → 2026-08) showed gap-up events reversing (−105 bps at 10 sessions, t −3.5), the opposite of the pre-registered H9 sign. Because it was found after seeing test data, it is **not** evidence; it is tested only on sessions **from 2026-09-17 onward**.

- **Event:** identical to Addendum 1 (gap ≥ 2 × ATR14, volume ≥ 2 × prior 20-session median, liquid ≥ $5M, DQ-12 clean, first event per ticker in 20 sessions), direction UP only for the primary test; DOWN tracked as a secondary report.
- **Primary prediction:** mean 10-session log return from the event-session close, net of the liquid-universe median, is **negative** for gap-up events. Secondary: 5 and 20 sessions.
- **Tracking:** C12 outcome scorer (measurement only, no authority), from events on or after 2026-09-17; outcomes scored when close(t+h) exists; no revision of the definition during the test.
- **Evaluation gate:** no judgement before ≥ 30 distinct event dates and ≥ 200 gap-up events with a 10-session outcome.
- **Pass:** clustered-by-date t ≤ −2.0 for the primary horizon, and |mean| greater than the median round-trip share spread of the event names. A pass makes H9R a candidate direction input (shadow); authority still requires G1–G4.

**Decision (ACK, 17 Sep 2026, before any forward data):** gap-down stays **secondary** — reported alongside, never part of the H9R pass verdict. No multiple-testing adjustment is applied to the primary test.
