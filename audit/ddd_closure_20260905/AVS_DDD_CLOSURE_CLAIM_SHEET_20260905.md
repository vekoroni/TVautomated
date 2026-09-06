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
