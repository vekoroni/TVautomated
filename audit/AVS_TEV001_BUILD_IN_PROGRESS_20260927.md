# AVS-TEV-001 build status — 27 September 2026

Status: **BUILD IN PROGRESS — NOT DONE, NOT TESTED, NOT SHIPPED.** Do not run a
production Evening/Morning using this worktree until the remaining build and
offline regression are completed. No broker or pipeline run was started here.

## Implemented in this worktree, awaiting tests

- Discovery/Vanguard-sourced, immutable descriptive C5 packet before option
  acquisition, with pass/reject ticker partition and separate structure,
  compression, auction and opposing-evidence fields.
- Run-linked C6 exact-option candidate enumeration from canonical
  Parquet `option_chain_v1` and JSON `option_chain_v2` registry entries,
  retaining no-chain/invalid-chain and per-row rejection states. The stored
  `20260926_173730` chain is v2 JSON; both formats now have contract tests.
- Immutable, explicitly non-numeric C8 disposition per C6 candidate. Neither
  legacy EV nor contract quote can create a calibrated ticker probability.
- Separate research-only numeric EV baseline from non-overlapping historical
  ticker paths available at the current run cutoff. It values each exact
  contract at ask entry and bid-like exit, with a constant-IV base, adverse
  IV/friction scenario and block-bootstrap interval. The baseline is
  unconditional, not Wyckoff/Vanguard-conditioned, not held-out calibrated,
  not a C4 posterior and cannot rank or authorise a trade. Missing IV,
  multiplier or 12 independent paths produces a typed non-value. A missing
  governed target/stop uses a labelled time-only exit rather than pretending
  the barriers exist. The accelerated research pricer has parity tests against
  the reference path pricer for calls, puts, barriers, time-only and adverse
  friction. These are current-known historical bars, not a certified PIT
  training panel or a predictive forecast.
- Lab C5/C6/C8 provenance, an all-ticker forecast API and ticker-first Lab
  forecast view, including names without an option or legacy Lab row.
- Dated Morning validation observations against the frozen C5 hash. Historical
  pre-cutover runs remain readable without reconstructing a past C5 packet.
- Pure C3 structure transitions, point-in-time C4 support-floor/competing-risk
  baseline with 20-session block intervals, and pure C8 path-valuation code.

## Still required before the user-defined “done” boundary

- Complete C3 episode replay/transition publication and verified Vanguard
  Layer 1/2 corrections on the same historical feature version.
- Build and audit the full point-in-time, geometry-labelled training panel;
  reconcile canonical bars with actuarial and run-frozen feature versions.
  The six-run audit found 195 preliminarily eligible starts, only four evidence
  sessions and zero mature 20-session paths as of this date. Historical row
  volume alone is not calibrated C4 support.
- Fit, chronologically calibrate and evaluate C4; publish C5 numeric paths only
  where the pre-registered floors and held-out criteria pass. Otherwise the
  descriptive path remains the truthful output.
- Implement C7 volatility scenarios and C8 candidate-by-candidate valuation
  packet from the supported *same* C4 path set; rank only after valuation.
- Complete Morning C6/C8 re-quote/revaluation, Interpreter and decision-journal
  parity, and final row/contract/decision/manifest reconciliation.
- After the full build: focused, whole-suite, chronological, UI and offline
  end-to-end tests. The user will initiate the Evening proof run manually.

No grade 0/1/2 defect may remain for shipment. Grade 3 requires a documented
workaround. A non-numeric descriptive result is honest but does not satisfy the
signed objective of a supported C4/C8 monetary valuation.

## Offline checks so far

The v1 Parquet and v2 JSON canonical chain formats both have passing focused
tests. The stored `20260926_173730` VST chain was read without changing its
run package: 672 contracts; the PUT search found 20 bounded candidates and
accounted for 336 wrong-side and 316 overflow rows. Its historical price
source supplied 62 non-overlapping 20-session paths. One exact VST PUT
produced an uncalibrated time-only research EV (base -47.6%; adverse -54.8%).
This is a smoke example, not a performance conclusion or production acceptance.
Focused tests: 19 passed for research pricing/C5/C6 contracts; the two format
tests passed after directing pytest's temporary output to a writable folder.
The read-only one-candidate-per-ticker canary on that stored run checked all
1,370 descriptive tickers: 1,347 produced `RESEARCH_EV_UNCALIBRATED`, 11 had
no chain dataset, one had no suitable option, one had thin history and ten
missed pricing inputs. This only measures coverage, not model skill or live
contract executability. A 50-ticker rerun after vectorisation completed in
39.33 seconds. Twelve focused pricing/schema tests passed, including four
vectorised-versus-reference parity cases. Whole-suite regression,
Morning/Interpreter parity, a full actual C6/C8 packet replay with all
candidates, and manual Evening proof remain outstanding.
