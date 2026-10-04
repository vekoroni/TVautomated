# C12 outcome ledger — status as verified 21 Sep 2026

This is a point-in-time finding, not a permanent fact — re-check by reading
the latest `Enhancements/outcomes/{date}/outcome_report.md` before relying on
any number below. It answers a specific question ACK asked: **is there
enough outcome data yet for calibration work (AVS-CAL-001-style) to run
meaningfully?** Short answer: **not yet, and the reason is calendar age, not
a bug** — see "Why this isn't fixable by re-running anything" below.

## What actually exists

- `data/canonical/decision_outcome_ledger.sqlite` (408MB) and
  `data/canonical/outcome_scoring.sqlite` (81MB) are live and were both
  written to as of 20 Sep 2026 — this is real, running infrastructure, not
  a stub.
- `avshunter/c12_outcome` is a full CLI
  (`python -m avshunter.c12_outcome {ingest|score|conditions|base-rate|
  expressions|hypotheses|signals|signal-scores|report|all}`) with a scorer
  version (`c12-outcome-scorer-v1.0.0` as of the report read) and reports
  written to `Enhancements/outcomes/{date}/outcome_report.{md,json}`.
- Three dated report folders exist: `2026-09-16`, `2026-09-17`,
  `2026-09-18` — i.e. this scoring system started running almost exactly
  when the current `CLAUDE.md` was approved (16 Sep 2026). It is under one
  week old as of 21 Sep.

## Two separate things are being measured — don't conflate them

**1. Legacy-signal backtest** (scoring historical legacy pipeline
predictions against real price outcomes, using the base-rate/Aalen-Johansen
methodology in method note 06):
- 19,070–22,951 individual predictions scored (depending on filter), but
  only **21 distinct evidence sessions** of history exist to compute
  against, because `data/output/runs/` only goes back to 15 Aug 2026 (~5
  weeks, and non-daily before Sep). One "session" = one distinct evidence
  day; thousands of same-day predictions count as one session for the
  purpose of independence, which is why the sample sizes look huge but the
  verdicts don't.
- **Headline verdict (ALL / BULL / BEAR) = OK** at 21 sessions — but the
  actual result is not encouraging: target-hit excess over the matched ATR
  base rate is ~0 (+0.1pp point estimate, interval straddles zero — no
  demonstrated edge at hitting target vs. a naive baseline), while
  stop-hit excess is **+2.0pp** (stops fire *more* often than the naive
  baseline predicts). This is a real, measured result, not a data gap —
  worth ACK seeing directly rather than filed away.
- Every finer breakdown that would matter for calibration —
  `ev3_absolute_state`, `final_action`, `lab_verdict`, `tier`, `thesis_state`,
  direction × regime interactions — comes back `INSUFFICIENT_SESSIONS`.
  These are exactly the buckets AVS-CAL-001 needs a calibration table over.
- The option-contract-vs-underlying comparison (actual $ P&L had these
  legacy predictions been traded as options) is worse and also entirely
  `INSUFFICIENT_SESSIONS`: 3,582 marked expressions, 14% win rate, mean
  return on premium **-45.8%**, vs. -1.6% for the underlying over the same
  predictions. That gap (options losing far more than the underlying moved
  against them) is consistent with the paying-for-expensive-vol pattern
  flagged in earlier audits, now with a real number attached — but at 19
  sessions it's not yet a validated finding, just a strong prior.

**2. Live signal-ticket track record** (the new C11/C12 architecture's own
issued tickets — this is what actually matters going forward, since it's
measuring the current design, not the legacy engine):
- 1,499 candidates considered, **5 tickets issued, 2 closed**. Both closed
  trades were losers (mean -38.2%, worst -65.1%). One issue session.
  Verdict: `INSUFFICIENT_EVIDENCE` (correctly — 2 trades tells you nothing).
- The pre-registered forward hypothesis test `H9R_GAP_UP_REVERSAL` (needs
  ≥30 event dates and ≥200 events before it can report) has **0 events
  recorded** across all horizons as of this report.

## Why this isn't fixable by re-running anything

`data/output/runs/` genuinely only contains ~5 weeks of history (oldest:
`20260815_091604`), and the legacy-backtest ingest already appears to be
using the full available range (22,951 predictions across the runs that
exist). There is no larger backlog sitting unread — the 21-session ceiling
*is* the current history. It grows by roughly one evidence session per
trading day from here; there's no shortcut except time and continuing to
run `ingest`/`score`/`signal-scores` daily so nothing gets missed.

## What this means for prioritisation (answers ACK's original question)

- **AVS-CAL-001 (calibration table by bucket) cannot run meaningfully yet.**
  The infrastructure to produce it exists and is correct; the input data
  doesn't yet clear its own `INSUFFICIENT_SESSIONS` bar. Running it now
  would produce a table that looks authoritative but isn't — the exact
  failure mode the spec's Invariant B is designed to prevent.
- **The live signal-ticket process is the one to watch weekly, not the
  legacy backtest.** It's the actual product going forward; right now it
  has 2 outcomes. A useful cadence: re-read the outcome report weekly and
  track "tickets issued / closed" and "H9R events recorded" as the two
  leading indicators of when calibration becomes meaningful — not a fixed
  calendar date.
- **The stop-rate excess (+2.0pp) and the options-vs-underlying return gap
  (-45.8% vs -1.6%) are worth ACK's attention now, independent of
  calibration readiness** — they're measured on the headline `OK` cohort
  (21 sessions, no `INSUFFICIENT_SESSIONS` caveat), so they're as solid as
  this system currently gets. If real, they say the legacy engine's options
  selection has been paying for vol/timing that the underlying move doesn't
  justify — consistent with, and now more precisely evidenced than, the
  IV-premium concerns raised in earlier audits.

## How to re-check this yourself

```
python -m avshunter.c12_outcome all --as-of <latest completed XNYS session>
```
then read `Enhancements/outcomes/{as_of_date}/outcome_report.md`. The
"Coverage" and "Signal track record" sections at the top/bottom are the
fastest way to see whether sample sizes have moved since this was written.
