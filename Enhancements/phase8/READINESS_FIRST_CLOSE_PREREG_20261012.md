# Pre-registration: does Discovery's acceptance rule improve on the first close beyond the trigger? (12 Oct 2026)

Written before any outcome is computed. Lessons L1 / L2 and requirement R1
(`LESSONS_AND_REQUIREMENTS_REGISTER_20261012.md`): enter at the first allowed close; no extra confirmation unless it beats
the all-days control on 200+ cross-ticker cases.

## Question

Discovery's readiness waits for an accepted break: two consecutive closes each at least 0.25 ATR beyond the trigger
(`config/beh001_behaviour_v1.json` acceptance; `domain/structure_behaviour/behaviour.acceptance`). Does that wait improve
what follows, compared with acting at the first close beyond the trigger?

## Data

- Candidates: BEH-001 replay panels `Enhancements/outcomes/beh001/eval_v4/candidates.jsonl` (original) and
  `eval_v4_holdout/candidates.jsonl` (hold-out), timeframe 1d, state DETECTED at the cut (trigger not yet crossed),
  one record per candidate id (its earliest cut), directed (BULL / BEAR).
- Bars: canonical daily bars (`data/canonical/historical_prices.sqlite`), split-adjusted.
- ATR: 14-session simple average true range at the entry close.

## Entries

- **A, first close:** the first session within 20 sessions after the cut whose close is beyond the trigger on the
  candidate's side (above for BULL, below for BEAR).
- **B, accepted break:** the second of two consecutive closes each beyond the trigger by at least 0.25 ATR, within the
  same 20 sessions (the engine's rule at its earliest moment).
- A candidate can produce A without B (crossed, never accepted).

## Outcomes (side-signed, from the entry close)

- Primary: +1 ATR before -1 ATR within 10 sessions (hit).
- Secondary: return in ATR at 10 sessions; +1 ATR within 3 sessions (p_fast, R2).

## Comparisons and decision rule

1. **B vs A:** hit rate and mean 10-session ATR return. If B does not beat A by at least 3 points on hit rate, with the
   session-block bootstrap 95% interval above zero, in **both** panels, acceptance adds nothing: readiness should fire at
   the first close, with acceptance kept as a label.
2. **Each against the all-days control:** same tickers and side, every session within 60 sessions of the cut.
3. Informational: A entries that were later accepted vs never accepted.

Intervals: bootstrap over cut dates (2,000 resamples). Trials counted: 2 primary (B-A in each panel).
