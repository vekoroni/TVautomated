# Macro Operating Cycle Phase 1 — Codex implementation / Claude read-only acceptance

**Later same-day integration amendment:** `E2E_INTEGRATION_HANDOFF_20261126.md` supersedes the sidecar-only publication order and deferred board/Lab reader statements below. Both consumers now share the canonical narrative through one committed publication bundle. Original Phase 1 test/replay evidence below remains historical; the end-to-end suite is 127 Python tests plus two JavaScript harnesses. Authored content remains explicitly incomplete and scheduling disabled.

ACK approved 26 November 2026. Scope: macro/ETFs only, ADVISORY_ONLY. No ticker judgement, score, rank, filter, contract, gate or veto. Lane B unchanged. No provider requests, paid builds or pipeline executions authorised or performed for this build. No commit or deployment certification implied by this note.

## Implementation sequence and owners

| Item | Implementation | Acceptance / limits |
|---|---|---|
| MAC-03 | `macro_board/cycle_evidence.py:driver_readings` | One owned record per driver. Level versus momentum versus policy kept distinct. Credit fixed-threshold NEUTRAL preserved as superseded for this narrative only. Commodity/paper detector is not general sector rotation. Missing policy/inflation/growth interpretation remains explicit; measured values remain available. |
| MAC-07 | Same module; `config/macro_operating_cycle_v1.json` | USSLIND and discontinued FRED OECD distribution excluded from new current evidence, raw histories preserved. Direct OECD replacement remains separate. Unknown observation clocks and stale source flags remain visible; capture clock never substitutes. Existing FRED policy is reused, not relaxed. |
| MAC-04 | `short_windows`, `operating_cycle.make_windows`, additive measured-sheet section | Five/twenty session changes, signed percentile and absolute unusualness, 252-session trailing sample (minimum 126). No missing-session bridging. FRED aligns using existing release-lag rules. Turning point means unusual change, not forecast reversal. |
| MAC-05 | `forced_calendar` and dated `calendars/` artifacts | XNYS holidays/half-days, adjusted third-Friday options expiry, month/quarter/year-end, explicit provisional tax-loss review window through 15 December. 20/50/100/200 averages require complete session windows. Calendar date is not a flow prediction. |
| MAC-08 | `cycle_narrative.py`, `cycle_io.py` | All nine sections, immutable dated JSON/Markdown, hashed captures, runtime/config/source lineage, latest pointer, correction reason, advisory authority. Two/three wrong worlds with explicit measurable tripwires; no authored input fabricated. |
| MAC-06 | `cycle_scoring.py`, archived-call inventory | Preserve all source rows; evaluate explicitly cumulative next-open-to-close 5/10/20 XNYS sessions; source bucket label retained. First available session open uses seasonal XNYS clock, including early closes. Same source bytes do not become new calls on board refresh. Reconstructed score percentages remain UNCALIBRATED_SCORE_TRANSFORM. |
| MAC-09 | `authored_calls.jsonl`, `daily_scores.jsonl` | Wrong worlds/events/playbook/forced-flow calls recorded immutably. Maturation needs independent saved boolean outcome receipt and source hash. Unobserved is UNASSESSED_OUTCOME, not failure. Unknown probabilities have no Brier score. All categories tested with clearly synthetic receipts; no real authored calls available in saved replay. |

## Integration and authority boundary

Only two pre-existing code files are edited: `macro_board/build_board.py` and `macro_board/measured_sheet.py`. The board adds short-window context after its decisions have been calculated, and calls the local cycle adapter after successful board/ETF publication. A sidecar error is printed as FAILED and has its own failure receipt; it never becomes a successful silent retry or a new ticker veto. Existing runner, FULL, API budgets, schedules, PostClose guard, board scoring, ticker authorities and Lane B code are not edited.

The adapter executes on ordinary board publications, including Evening/PreOpen/off-session. Tripwires are checked against available saved inputs at those cycles; unsupported/missing/stale series stay unassessed. There is **no new continuously running intraday collector** and no new scheduler task. MAC-15 screen integration and broader live driver acquisition stay Phase 2. The sidecar does not claim that the ETF board screen already displays the full nine-section narrative.

Automatic future outputs: `macro_board/output/operating_cycle/`. Dated narratives, calendars and run receipts are immutable. `latest.json` and `run_latest.json` are pointers/views. Raw captures use full content SHA-256 names, not mutable filenames. Dedicated directories are outside existing rolling-retention targets. Journals are append-only with identity conflicts/truncated records failing closed. No automatic stale-lock takeover.

## Authored input contract — ACK/Claude next action

Template: `Enhancements/macro_operating_cycle/macro_narrative_input.example.json`. It is documentation, **not an installed or approved market view**. Supply the actual authored file at `dropbox/macro/macro_narrative_input.json`, authority ADVISORY_ONLY, author, aware as_of_utc, input_revision. Include transmission, house statement/probability, two/three wrong worlds, central-bank-versus-price, ETF book and invalidation. Unknown values must be null, not 0/50% guesses.

Each wrong-world/event/playbook/flow prediction needs a unique call_id, event description, due_at_utc, resolution_rule, and optional authored probability [0,1]. Wrong worlds additionally need `tripwire: {series, operator, level}`, where operator is GT/GE/LT/LE/EQ. Supported saved series: DGS2, DGS10, WALCL, WTREGEN, RRPONTSYD, VIXCLS, DEXUSEU, SPREAD_2Y10Y, SPY.close, QQQ.close, IWM.close. Unsupported identities are never guessed. All ETF expressions require killer_event, covering_position (explicit null allowed), and world_marks keyed HOUSE plus every wrong-world call_id; values WIN/FLAT/LOSE/UNASSESSED. Worlds count is calculated from those marks.

World probabilities only sum to 1 when worlds_partition is explicitly MUTUALLY_EXCLUSIVE_EXHAUSTIVE. A changed forecast needs a new call_id/correction lineage; never revise an old call/outcome. `supersedes` on a narrative requires correction_reason. Wrong-world probability changes compare stable/superseded call identities.

Outcome input: `dropbox/macro/macro_narrative_outcomes.json`, JSON array of `{call_id, observed_at_utc, outcome: true|false, source, source_path, source_sha256}`. The assembler reads the local source_path, verifies the actual bytes against source_sha256 and preserves them in its capture store. No URL fetch is permitted. Use actual independent saved evidence, not the prediction itself. The local scorer does not interpret prose to decide that a world happened.

Until that input is supplied, the honest narrative status is INCOMPLETE_AUTHORED_INPUT. This is not COMPLETE economic analysis; functioning infrastructure does not manufacture a house view. Policy, inflation and growth states without a governed interpretation remain missing alongside their dated values. A priced Fed path is not invented (MAC-10).

## Replay and evidence

Saved board describes 25 November close, published 26 November 11:35:33 UTC. Replay cutoff is the publication clock, not a pretended 25 November knowledge cutoff. Histories are saved **as-read** and may contain later revisions; not vintage-certified causal backtesting.

Final replay folder: `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_CYCLE_PHASE1_FINAL_20261126`.

Expected: credit WIDE_WARNING; rates EASING with source stale flag; defensive broadening qualified by missing participation. DGS2 five-session -17bp, absolute unusualness 91.67%, twenty-session -7bp. Calendar includes 27 Nov half-day, 30 Nov month-end, 18 Dec expiry, 31 Dec quarter/year-end.

Archive: 34 saved forward CSV artifacts, 27 linked to hash-verified board publication clocks -> 81 call rows. Seven unlinked artifacts remain excluded, not assigned a filename-derived timezone. Missing archived-byte snapshot references are collated separately. Scoring includes all calls with separate matured/no-direction/pending/gap states. Overlapping calls imply only 2 non-overlapping five-session windows and 1 ten-session window in this replay; no claim of calibrated probabilities, robust predictive performance or option P&L.

## Independent acceptance checklist

Final Codex checks: 29 new operating-cycle tests, 10 measured-sheet tests, 63 existing board-rule tests, 1 macro-never-scores boundary test and 6 interpreter advisory handoff tests passed (109 total). Per-file JUnit evidence: `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_CYCLE_TESTS_FINAL_20261126`. Independent verifier imports no production cycle assembly/scoring code; verified 17 capture hashes, independently recomputed -17bp/91.67%, checked all 12 moving averages and archive accounting. Schema validator PASS; narrative content remains INCOMPLETE_AUTHORED_INPUT.

1. Re-run offline tests, inspect source hashes and the nine ordered sections.
2. Validate driver values against captured raw inputs; check NEUTRAL is preserved, not erased.
3. Check restrictive policy label versus easing market momentum are separate dimensions.
4. Check freshness at use, missing participation qualification and dead-series exclusion.
5. Confirm -17bp five-session value and percentile, not only the old 20-session score.
6. Confirm calendar/trend artifacts and complete-session requirements.
7. Verify archive accounting, correct DST/half-day entries, no missing-bar compression, no call duplication on refresh.
8. Verify immutable files/journals, strict hash checks, locks and retry tests.
9. Confirm no ticker/Lane B authority changes and no schedule/budget/FULL/PostClose edits.
10. Supply real authored input/outcome receipts before claiming authored-call operational closure. A scheduled real board artifact remains AWAITING_RUN; no paid run was made to obtain it.

Ready-to-paste PowerShell tests (offline):

```powershell
Set-Location "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; & "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe" -B -m pytest "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\tests\test_macro_operating_cycle.py" -q -p no:cacheprovider --basetemp="C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\pt_mac_claude"
```

Saved-only replay, separate output folder (no Macro Inputs/provider/pipeline):

```powershell
Set-Location "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; & "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe" -B "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\tools\run_macro_operating_cycle.py" --board "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\macro_board\output\etf_macro_board.html" --output "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_CYCLE_CLAUDE_REPLAY_20261126" --backfill-forward
```

## Phase 2 — plan only

| ID | Need/source options | Approval/cost questions |
|---|---|---|
| MAC-10 | Timestamped fed-funds/SOFR futures path, contract calendar, expected-rate methodology; exchange/licensed vendor or existing entitled broker feed | Entitlement, historical settlements, redistribution and conventions; no priced path inferred from news probabilities |
| MAC-11 | Release-specific timestamped consensus and vintage actuals; licensed calendar/vendor or explicitly sourced research exports | Consensus licensing, snapshot cutoff, revision handling; own-trend z-score is not consensus surprise |
| MAC-12 | Inventory existing FRED Fed-input series first, extend only gaps; official releases; structured Fed-speak/dissent rows with original text links | Source cadence, transcript rights and independent provenance; author judgement not measured data |
| MAC-13 | Futures, Treasury yields, FX/oil/volatility, VIX9D, breadth, 0-7DTE straddles via entitled provider/broker | Real-time vs delayed entitlement, option NBBO access, refresh cost and dedicated intraday lane; no new acquisition authorised |
| MAC-14 | Official UK/DE/JP rate sources; licensed MOVE; separately governed Brent/WTI contracts | MOVE licence; settlement/spot/contract identity and clock; choose oil benchmark explicitly, do not average incompatible quotes |
| MAC-15 | ETF board narrative reader, context-only triage reference, live tripwire/countdown/divergence views keyed to the same narrative ID | UI acceptance and refresh cadence; no ticker decision authority, new screen or Lane B code built in Phase 1 |
