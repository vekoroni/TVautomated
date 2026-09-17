# Exit-rule study — recorded books, 31 Aug to 16 Sep 2026 (ACK 17 Sep 2026)

The 17 Sep backtest found the exit, not contract selection, to be the binding constraint. This replays the same
recorded candidates under four exit rules, changing nothing else (`Enhancements/backtest/exit_rule_study.py`).

| Rule | Exit |
|---|---|
| `baseline` | shipped rule: first of stop touch, target touch, planned hold, last usable session |
| `wide_stop` | stop moved to 1.5 expected moves over the hold; target, hold and last usable unchanged |
| `no_stop` | no underlying stop inside the hold (the premium is already the maximum loss) |
| `revalue` | no underlying stop; each session with a stored quote, the option is re-valued at that session's ask and closed when its cautious return is no longer above zero |

## Like-for-like comparison — 638 trades closed under all four rules (top cautious quintile)

| Rule | Mean return on premium | Median | Share profitable | Median sessions held | Mean difference vs baseline |
|---|---|---|---|---|---|
| baseline | −18.8% | −39.0% | 30.7% | 5 | — |
| **wide_stop** | **−15.9%** | −27.7% | **36.5%** | 7 | **+2.9 points, t = 3.21** |
| **no_stop** | **−15.9%** | −27.7% | **36.5%** | 7 | **+2.9 points, t = 3.21** |
| revalue | −16.1% | **−22.1%** | 29.0% | 1 | +2.8 points, t = 0.99 |

Unpaired totals over the whole quintile (1,702 candidates) agree in direction: baseline −27.6% on 914 closed,
wide_stop −17.1% on 652, no_stop −17.1% on 649, revalue −17.4% on 1,459.

## What each rule shows

- **Widening or removing the stop is a real, small improvement.** The mean rises by 2.9 points with t = 3.21 on
  paired trades, and the profitable share rises from 30.7% to 36.5%. It changes the outcome in only 12% of trades
  — precisely those the old stop would have closed. At 1.5 expected moves the stop is never reached, so
  `wide_stop` and `no_stop` are the same rule in this sample; the simpler statement is that **an underlying stop
  inside the planned hold destroys value without limiting loss**, because the premium already caps the loss.
- **The re-valuation rule as coded is degenerate.** It closed after one session in 87% of cases, because it asks
  "would I buy this again, paying the ask?" — after a day of time decay the answer is almost always no. It
  improves the median (−22.1%) simply by cutting exposure short, and its mean gain is not significant (t = 0.99).
  A fair version must compare the value of holding against the **bid** that selling would realise, not re-purchase
  at the ask. Until that is rebuilt, this rule is not evidence for anything.
- **Nothing here makes the tickets profitable.** The best rule still loses about 16% of premium on average in this
  window.

## The largest finding is not an exit rule

**The contract expires before the plan ends.** Under every rule the most common exit is the last usable session
(baseline 364 of 1,009 exits, wide_stop 510, no_stop 515): the planned hold, often 20 sessions, exceeds what the
selected contract has left, so positions are closed two sessions before expiry with the time value gone. Only 143
of 1,009 baseline exits reached target.

That is a **contract selection** rule, not an exit rule: a contract should have at least the planned hold plus the
exit buffer in sessions. It is the next thing to fix and test on this harness.

## Conditions and limits

- Two weeks, one regime (SPY −2.0%, IWM −4.0%) against a 64% CALL book.
- Entry at the recorded evening close ask; no morning requote or delayed-quote adjustment.
- Exits marked from the stored chain on the exit session only; unmarked exits are excluded, which is why the
  unpaired closed counts differ between rules. The paired table above removes that bias.
- The registered forward gate (40 closed signals over 15 issue sessions, lower bound above zero) is not met by any
  rule; none of this grants decision authority.
