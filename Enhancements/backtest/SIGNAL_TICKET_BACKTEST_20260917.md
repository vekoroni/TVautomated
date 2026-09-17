# Signal ticket backtest — recorded books, 31 Aug to 16 Sep 2026 (ACK 17 Sep 2026)

The shipped ticket rules (`avshunter.c12_outcome.signals.decide` / `plan_exit` / `mark_signal` / `evaluate` and
`empirical_option_ev.compute_path_expression_ev`) replayed on every recorded evening book. Point-in-time inputs:
the thesis, contract and its end-of-day quote as each run recorded them; the Layer 3 volatility forecast and DQ-12
state recomputed from bars up to that session; the share spread from the same bars.

Script: `Enhancements/backtest/signal_ticket_backtest.py` · rows: `signal_ticket_backtest_rows.csv` ·
summary: `signal_ticket_backtest_summary.json`.

## Coverage

9 sessions (31 Aug, 1, 2, 4, 9, 10, 11, 14, 16 Sep 2026), 8,950 valued candidates, **91 tickets**. Runs before
31 Aug do not record a governed direction, so they produce no candidates. 15,423 rows were skipped before
valuation: 13,657 with no CALL/PUT direction, 1,623 with an incomplete thesis or quote, 137 with no contract,
6 with a price-history break.

## Result 1 — the value model ranks outcomes well

Across 2,870 closed candidates (entry at the recorded ask, exit at the stored chain bid on the exit session):

| Cautious-return quintile | Closed | Mean return on premium | Median | Share profitable |
|---|---|---|---|---|
| 1 (lowest) | 574 | −77.1% | −90.0% | 4.2% |
| 2 | 574 | −61.5% | −75.3% | 9.4% |
| 3 | 574 | −54.6% | −68.4% | 11.5% |
| 4 | 574 | −45.6% | −60.3% | 12.7% |
| 5 (highest) | 574 | −28.9% | −38.8% | 17.6% |

Rank correlation between the cautious return and the realised return is **0.44** (n = 2,870); the central return
gives 0.31. The ordering is monotonic across all five quintiles. This confirms the earlier evaluation (0.394 on
1,961 marks) on a fresh, point-in-time sample.

## Result 2 — ranking did not turn into profit in this window

| | Tickets | Rejected candidates |
|---|---|---|
| Candidates | 91 | 8,859 |
| Closed option results | **19** | 2,973 |
| Mean return on premium | **−50.5%** | −55.2% |
| Median | −50.0% | −68.6% |
| Share profitable | 5.3% | 10.7% |
| Median quote spread | **9.5% of mid** | 37.6% |
| Thesis reached target | 1 of 21 (4.8%) | 615 of 3,296 (18.7%) |
| Verdict at the registered gate | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE |

The filter halved the spread paid and improved the median outcome, but every bucket still lost money, and the
ticket sample is far too small and too concentrated to claim anything: 19 closed results over 5 sessions, with
BMNR appearing 6 times and OKLO 3.

## Result 3 — the stop is the binding constraint

| Median | Tickets | Rejected |
|---|---|---|
| Stop distance | 16.7% | 6.4% |
| Stop distance in expected moves over the hold | **0.63** | 0.53 |
| Target distance in expected moves | 1.76 | 1.36 |
| Sessions to stop | **2** (25th percentile 1) | 2 |

The invalidation level sits about **0.6 of one expected move** away while the target sits about **1.8 moves**
away. Ordinary volatility therefore reaches the stop first: 20 of 21 scored tickets stopped out, at a median of
two sessions, long before the thesis had room to work. That geometry, not contract selection, dominates the
result.

## Conditions and limits

- **One regime, two weeks.** SPY −2.0% and IWM −4.0% over the window, while the books were 64% CALL.
- **Entry at the evening close ask**, not the morning intraday quote: no morning requote, no delayed-quote
  adjustment, no morning gate. Live tickets enter later and re-value at that moment.
- **Exit marks come from the stored chain on the exit session only** (no nearest-date substitution): 325 exits
  could not be marked, and 5,633 positions are still open at the data edge.
- **Stops and targets are the pipeline's existing structural levels**, which the direction studies already found
  to carry no edge.

## What this supports

1. **Keep the cautious-return filter.** It orders outcomes reliably (IC 0.44) and cuts the spread paid by four
   times, which is the one cost we can control.
2. **Do not expect profit from tickets as they stand.** In this sample the best-valued fifth still lost 29%.
3. **The next fix to investigate is the exit geometry**, not the selector: a stop inside one expected move gets
   hit by noise. Candidates worth testing, each against this same harness: a stop at or beyond ~1.5 expected
   moves; an exit driven by the option's own re-valuation rather than an underlying level; or no stop at all
   within the planned hold (the premium is already the maximum loss).
4. **Forward measurement stands.** The registered gate (40 closed signals over 15 issue sessions with the lower
   bound above zero) remains the decision point; nothing here passes it.
