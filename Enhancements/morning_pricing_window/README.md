# Morning pricing-start guard

## Current rule (ACK, 14 November 2026) — supersedes the 13 November rule below

ACK: "The morning gate should have the flexibility to run anytime during market hours."

- Policy `morning_pricing_policy_v2` in `config/morning_pricing_policy_v1.json` (file name kept; version inside).
- A post-open Morning start at any time from the XNYS open to the close (early closes included) **prices**.
- 09:35-09:45 ET is the preferred window, not a limit. The run is labelled in
  `postopen_contract_refresh_window_state`: `BEFORE_PREFERRED_WINDOW`, `DEFAULT_WINDOW` or `AFTER_PREFERRED_WINDOW`.
  The verifier's R01 still WARNs on a start outside the preferred window; R19 still checks each quote's age.
- Only a start outside market hours is refused (before the open, at or after the close, weekend, holiday):
  `MORNING_PRICING_WINDOW_CLOSED`, before any setup or provider work.
- The second check immediately before the live-data batch now guards the close, not 09:45.
- Tests: `tests/test_morning_pricing_window.py`, 30 pass (13 failed on the 13 November rule before the change).
- Built by Claude Code on ACK's instruction. No provider call, no pipeline run. Forward acceptance on a real
  Morning is outstanding.

---

# 13 November 2026 record (superseded: refused any start outside 09:35-09:45 ET)

Status: implemented and tested in the working checkout; not committed or pushed.
ACK authorized continuing the Codex-owned reliability fixes after the GARCH-only
release. No providers or pipeline execution authorized or performed. Lane B is
untouched. This does not create a scheduler or start a Morning run.

## Root cause and scope

`run_morning_gate` labelled starts outside 09:35–09:45 ET as
`PERMITTED_LATE_REFRESH` and continued. The orchestrator could perform catalyst
work before reaching that decision. The verifier also used a manifest creation
timestamp for quote age, which could belong to the preceding Evening run.

## Repair

- One pure, versioned start policy in `config/morning_pricing_policy_v1.json`.
- Both supported entry paths reject a post-open pricing start outside
  09:35–09:45 ET (inclusive clock minutes) or on a non-XNYS session.
- The gate checks before rate/store setup and again immediately before its
  live-data batch, so preparation cannot turn permission into a late start.
- The orchestrator rejects before catalyst or downstream Morning stages.
- The direct CLI returns exit 2 on a closed pricing window, without finalizing.
- Pre-open thesis-only mode is preserved; it does not gain option-pricing authority.
- This is a START guard, not a batch-completion deadline. An in-window batch may
  finish later; each quote still requires its existing freshness checks.
- Publish pricing-start UTC and completion UTC separately. Keep the original
  Evening creation timestamp. Verifier R01 uses pricing start when available;
  R19 uses Morning completion for independent quote age. Historical files are
  never relabelled or rewritten. Engine version becomes `avs_verify_v1_3`.

No scoring, contract selection, expiry selection, macro authority or Lane B
logic is changed. The separate live-entry sub-60-second quote requirement (#3)
is not implemented by this change.

## Offline proof

Initial entry-point tests: six failed before the guard, five existing compatible
cases passed. Final focused suite: **19 passed**. Covers early/late starts,
weekends, holidays, DST offsets, early-close days, valid boundary minutes,
pre-open mode, invalid clocks/configuration, preparation crossing the window,
both entry points, separate verifier clocks and manifest preservation.

Compatibility suites:

| File | Passed |
|---|---:|
| test_morning_gate_quote_reuse.py | 3 |
| test_morning_gate_cds_bootstrap.py | 3 |
| test_morning_gate_authority.py | 20 |
| test_avs_morning_gate_lanes.py | 3 |
| test_morning_handoff_finalizer.py | 11 |

Total **59 passed**, plus three unittest subtests. Network connections are
blocked by the offline plugin. One initial handoff-suite attempt failed on
sandbox temporary-directory permissions; rerunning with a short writable
temporary root passed all 11 tests without a code change to that suite.

Saved report replay (`SAVED_REPLAY_20261113.json`):

- 11 November Morning started 10:06:29 ET: would stop before pricing.
- 12 November Morning started 09:55:57 ET: would stop before pricing.
- Both were previously labelled `PERMITTED_LATE_REFRESH`.
- Saved report bytes unchanged, with SHA256 receipts recorded.

These historical late starts demonstrate the defect and its corrected guard;
they are not five successful forward sessions. R01/R19 forward acceptance on
five sessions remains outstanding. No current Lab or trading output rebuilt.

## Next work

Proceed to #3, live-entry quote contract/freshness enforcement, first offline.
Actual Tastytrade collection and live sub-60-second verification remain outside
the current no-provider restriction. Then monetisation publication, shadow
contract coverage/economics, ordered alternatives, and in-window/WATCH flags.
