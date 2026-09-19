# Ticket ranking key re-check after the calibration fix

19 September 2026 · re-run of `signal_ticket_backtest.py` (shipped rules, point-in-time inputs, read-only) with the
calibrated valuation (commit 22761ee). The 17 Sep output files were restored unchanged; the new rows are kept in
the session scratchpad.

**Question (ACK):** should tickets rank on the central return per dollar instead of the cautious return?

| Measure (closed option results) | Cautious (current key) | Central |
|---|---|---|
| Rank correlation with realised return, before calibration (n = 2,870) | 0.439 | 0.309 |
| Rank correlation with realised return, calibrated (n = 3,078) | **0.518** | 0.429 |
| Daily top 5, calibrated: mean return on premium (n = 45) | **−13.4%** | −33.2% |
| Daily top 5, calibrated: median | **−23.5%** | −50.0% |
| Daily top 5, calibrated: share profitable | **22%** | 11% |

Quintiles by cautious return (calibrated): mean −77.9%, −62.8%, −58.4%, −41.8%, −24.7%; share profitable 5%, 9%,
9%, 15%, 19% — monotonic.

**Decision (19 Sep 2026):** tickets keep ranking on the cautious return. Every bucket still loses money on these
sessions; the ranking orders outcomes, it does not yet make them profitable.

**Follow-on:** the contract value selection (675b5e3, SHADOW) measures the central return; this evidence favours
the cautious return there too. Revisit before any switch to ACTIVE.
