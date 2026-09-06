# AVSHUNTER DDD closure claim sheet — 2026-09-05

## Release decision

The closure implementation is ready for a controlled evening integration cycle. It is not yet marked production-accepted because its newly generated artefacts and the following Morning Gate have not run.

## Implemented claims

1. **One Options evidence session.** Contract-selected and contract-repair rows use the CDS run session; quote timestamps cannot mint a second thesis session.
2. **One aggregate run identity.** The orchestrator owns `pipeline_run_id` and passes it into Discovery. Discovery no longer generates a downstream timestamp when a governed run ID is supplied.
3. **Immutable build receipt.** A successful dynamic `BUILD_THESIS` run must reconcile all five domain stages and publish an immutable, plan-hash-bound receipt.
4. **Correct provider boundary.** The MarketData adapter converts the canonical inclusive final-bar range to MarketData's exclusive `to` boundary by adding one interval.
5. **Usable-profile acceptance.** A profile run now fails closed when completed-profile coverage is below 90%, even when the transport failure rate is zero.
6. **Earlier geometry enforcement.** A directional candidate without governed invalidation is classified `DATA_REPAIR_REQUIRED` before EOD candidate authorisation.
7. **Correct manifest population.** Lab semantic health is measured over the selected candidate handoff. The latest pre-fix run now reports 100% selected-handoff coverage rather than inheriting 164 upstream Options defects.
8. **Truthful telemetry.** Options request telemetry counts only `OPTIONS/OPTION_CHAIN` ledger entries; completed-profile calls are reported by their own stage.
9. **Macro remains advisory.** The horizon summary now separates the applied direction-agnostic core route from non-applied macro advisory biases.
10. **Governed activation and rollback.** Runtime profile `AVS-DDD-CLOSURE-20260905` enables the supervised DDD capabilities, with autonomous dispatch still disabled and all rollback flags retained as false.

## Test evidence

- Nine production modules compile successfully.
- Focused closure pack: **91 passed, 0 failed**.
- Isolated affected release pack: **396 passed, 16 subtests passed, 0 assertion failures**.
- One retired morning-thesis-validator module intentionally skips at module scope.
- The historical recursive MSI characterization pack was not used as the release gate. It contains tests that deliberately assert absent behavior and a Sunday fixture (`2026-08-30`) that fails before lifecycle authorization is reached.
- Read-only CLI plan preflight passed and resolved: `DISCOVERY -> COMPLETED_MARKET_PROFILE -> VANGUARD -> OPTIONS -> PUBLISH_THESIS`, authority ceiling `EOD_PREPARED`, completed session `2026-09-04`.

## Latest run disposition

Run `20260905_151448` is valid evidence of the pre-fix problem, not acceptance evidence. The amended manifest correctly gives its completed-profile stage `FAIL` because it produced zero usable profiles. It simultaneously reports the actual selected Lab handoff at 100% semantic coverage with zero missing invalidations.

## Remaining closure gates

1. Execute one controlled evening run through the normal command.
2. Confirm the run creates a plan-bound completed-thesis receipt and at least 90% usable completed profiles.
3. Confirm all stage identities and completed-session dates agree.
4. On the next trading session, run Morning Gate against that exact accepted run.
5. Confirm Morning lifecycle transitions, capital permission, Intelligence Lab output and Pipeline Interpreter handoff agree before marking the release production-accepted.

## Rollback

The pre-change application files and canonical databases are preserved under `backups/ddd_closure_prechange_20260905`. No rollback was triggered by offline testing.

---

# Corrections (6 Sep) — AVS-FIX-001 W0.4

Issued under AVS-FIX-001 W0.4, correcting QT-D08, QT-D09 and QT-D10 against
AVS-TST-QT-001. The corrections are recorded here rather than by editing the
claims above, so the original wording and its correction are both visible.

## C1 — Claim 5 misdescribes its own change (QT-D08)

**Claim 5 said:** "A profile run now fails closed when completed-profile
coverage is below 90%, even when the transport failure rate is zero."

That sentence conflates two different quantities and implies a gate was
*lowered*. Neither is accurate.

* **The per-profile coverage gate was `>= 0.95` before the closure and is
  `>= 0.95` after it.** It was never lowered. It governs the fraction of
  expected bars present within one ticker's session.
* **The `0.90` is a NEW stage-level `min_usable_ratio`**, over the fraction of
  *tickers* that produced a usable profile. It is a different quantity at a
  different level, and it is a *stricter* posture, not a looser one: before the
  closure there was no stage-level coverage gate at all. It is what would have
  stopped run `20260905_151448`, which produced zero usable profiles.

**The stated rationale was also wrong.** Claim 5's motivating case was a frame
with 77 of 78 bars. That frame fails at **98.7% coverage**, far above both 0.95
and 0.90 — no coverage threshold could have rescued it. It failed on
`last_region`, which is a hard `and` in the usability expression: the missing
bar was the 15:55 bar, so the final region was unrepresented. The fix that
actually shipped in the same release was the exclusive-`to` `+1 interval`
change, which is unrelated to any threshold.

**Corrected claim 5.** *The per-profile coverage gate is unchanged at 0.95. A
new stage-level `min_usable_ratio` of 0.90 fails the profile stage closed when
fewer than 90% of observable tickers produce a usable profile, independently of
the transport failure rate. The 77/78 frames were fixed by the exclusive-`to`
interval change, not by any threshold.*

AVS-FIX-001 W1.4 has since corrected the `usable_ratio` denominator: it is now
`processed / (input − deferred)`, so tickers that did not trade no longer count
against coverage, and the stage publishes one named `guard_decision`.

## C2 — The 17 test-file edits are now documented (QT-D09)

QT-D09 recorded 17 test files modified since `pre-tidy-20260904` with 16 of
them undocumented in any claim sheet. All 17 are now classified in
`audit/pipeline_map/AVS-IMP-FIX-001/test_edits_register.csv` with the change,
the rationale, and its T2 classification.

| T2 classification | Files |
|---|---|
| `UNRELATED` (pure addition, 0 lines deleted) | 12 |
| `OBSOLETE_ASSERTION_CORRECTED` | 4 |
| `FIXTURE_CORRECTED` | 1 |
| `PROTECTION_WEAKENED` | **0** |

**On QT-D05's "one weakening".** The closest candidate is
`test_dynamic_session_phase6.py`, where
`test_completed_profile_stage_uses_frozen_thesis_flag` was replaced by
`test_completed_profile_stage_has_independent_runtime_flag`. The old test
asserted that the completed-profile stage was *coupled* to the thesis flag;
AVS-SD-002 Rev 1.1 makes every capability an independently reversible switch,
so that coupling is the thing the release retired — the edit is
`OBSOLETE_ASSERTION_CORRECTED`, not a weakening.

The replacement does, however, assert that the stage **defaults to enabled**
when its environment variable is unset. That is recorded in the register as a
residual observation for the tester rather than dismissed. It is covered three
ways — the governed runtime profile sets the flag explicitly, AVS-FIX-001 W0.2
now pins that profile's SHA-256 against the release manifest so it cannot
change without a reviewable artefact, and
`AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL` still returns every flag to off — but
**the tester should confirm the unset-default is what ACK intends.**

## C3 — Retroactive backup records (QT-D10)

`contracts/dynamic_session_authority_v1.json` and
`canonical_data/request_ledger.py` were changed on 4–5 Sep with no pre-change
backup, which AVS-SD-003 requires.

That moment has passed and cannot be recreated. What now exists, under
`backups/avs_fix_001_QT-D10_retroactive_pre-tidy-20260904_20260906_152146/`, is
the file content at the `pre-tidy-20260904` tag — the last committed state
before the change — with the SHA-256 at the tag and the SHA-256 now, so the
delta is inspectable and reversible. Both files did change.

**It is labelled `retroactive: true` in its manifest and is not a pre-change
backup.** QT-D10 is mitigated, not closed.

## C4 — `CLOSED OFFLINE` is retired as a status

Per AVS-FIX-001 §0 rule 10 and the register's §7, `CLOSED` requires a
run-artefact count. `CLOSED OFFLINE` is a different state and must never appear
in the same column as `CLOSED`. The statuses in use from 6 Sep are:
`IMPLEMENTED — OFFLINE VERIFIED`, `IMPLEMENTED — AWAITING RUN`, `BLOCKED`,
`DEFERRED`. Nothing in AVS-FIX-001 is reported as `CLOSED`; that is the
tester's assignment after a run artefact shows the item firing.

## C5 — The Sunday fixture named under "Test evidence" is fixed

The note above records that the MSI characterization pack "contains ... a
Sunday fixture (`2026-08-30`) that fails before lifecycle authorization is
reached", and uses that as part of the reason the pack was not the release
gate.

That fixture is now corrected (AVS-FIX-001 W0.3): the session dates move to
Friday `2026-08-28`, and the five `tests/fixtures/marketdata/` payloads
timestamped `1788120000` — the same Sunday at 20:00Z — move with them, since
the chain resolver's 80% quote/session rule rejected them otherwise. Six tests
that had never reached their own assertions now run. The deliberately-Sunday
instant that proves the CLOSED session state is untouched.

`tests/msi/` is now inside the acceptance matrix. The pack's remaining 24
failures are filed with root cause in
`audit/pipeline_map/AVS-IMP-FIX-001/W0.3_msi_matrix_defects.md`; none is a
regression, and the reason they were invisible is that the pack was excluded.
