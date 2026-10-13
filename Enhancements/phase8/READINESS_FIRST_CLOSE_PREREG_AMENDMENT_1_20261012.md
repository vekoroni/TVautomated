# Amendment 1 to the readiness pre-registration (12 Oct 2026, written before the re-run)

The original pre-registration (`READINESS_FIRST_CLOSE_PREREG_20261012.md`) and its result
(`readiness_first_close_test.json`) are kept unchanged. This amendment follows ACK's review
(`AVSHUNTER_Discovery_Entry_Timing_Requirements_v1.docx`, "Review of the supplied readiness preregistration") and
applies to the re-run only. Original wording corrected: the first result showed **no demonstrated improvement** from
waiting; it did not show that acceptance adds nothing.

## Cohort (frozen before outcomes)

- BEH-001 replay panels eval_v4 (original) and eval_v4_holdout, timeframe 1d, state DETECTED at the cut, directed,
  trigger present; one record per candidate id (earliest cut).
- **Episode** = ticker + side + trigger level (rounded to 0.01) + cut; several candidates with the same episode key are one
  opportunity. Cross-panel overlap of ticker-date episodes is counted and reported.
- Eligibility uses only the candidate's state at its cut (point in time). Every cohort episode stays in every policy's
  denominator; a policy that never enters records NO_ENTRY.

## Policies (decomposed; each on the same cohort, 20 sessions after the cut)

| Policy | Signal (at a completed daily close) |
|---|---|
| P0 | first close beyond the trigger (no buffer, one close) |
| P1 | first close at least 0.25 ATR beyond (buffer, one close) |
| P2 | two consecutive closes beyond (no buffer, two closes) |
| P3 | two consecutive closes each at least 0.25 ATR beyond - the live readiness moment (provisional accepted break) |
| P4 | P3 and the next two closes do not close back across the trigger - the engine's full ACCEPTED, signalled at the second of those closes |

ATR: 14-session simple true range at each signal close (frozen there). Each close tested against its own session ATR,
as the engine does.

## Feasible fill and outcomes

- Fill at the **next session's open** after the signal close (information is only available at the close).
- Barriers +-1 ATR (frozen at the signal close) from the fill price; window = the fill session and the next 9 sessions.
- Primary: +1 ATR before -1 ATR. Same-bar ambiguity reported three ways: loss (primary), win, excluded.
- Secondary: return in ATR at the 10th session close; +1 ATR within 3 sessions (p_fast).
- Underlying only, gross of costs (options are a separate assessment); stated.

## Comparisons and decisions (declared now)

1. **Relative timing (non-inferiority):** P0 is non-inferior to P3 if, in **both** panels, the lower bound of (P0 - P3) hit
   rate is above **-2.0 points** and the lower bound of the per-entry 10-session ATR return difference is above **-0.05
   ATR**. Decomposition (P1 vs P0 = buffer; P2 vs P0 = second close; P3 vs P2; P4 vs P3) is descriptive.
2. **Edge (separate test):** each policy against a matched all-days control - same ticker and side, fill at the next open
   on each session in the 60 sessions before the cut, each ticker-side-date counted once. A policy has edge only if the
   lower bound of (policy - control) hit rate is above zero in both panels.
3. **Policy level:** entries per cohort episode, and expectancy per episode in ATR with NO_ENTRY counted as 0.
4. **Decision rule:** if P0 is non-inferior, the breakout-family policy in the N3 registry may move to P0 timing
   (earlier, labelled). No policy is promoted as an edge without test 2. Event families other than daily trigger
   crossings (spring tests, retests, upthrust failures) are not decided by this test.

Intervals: bootstrap over cut dates (2,000 resamples, fixed seed). Setup-type splits are descriptive only.

## Controls (hard assertions in the harness)

Frozen cohort; point-in-time eligibility; unique episodes (idempotent); fill strictly after the signal close and outcomes
from bars after the fill only. A synthetic positive control (one manipulated run per invariant) must be rejected by the
assertions before the real result is reported.
