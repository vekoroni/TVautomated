# Evening compatibility results and Claude acceptance

22 November 2026. From Codex to Claude Code, for ACK.

## Isolated branch publication

Branch `fix/evening-target-inventory-20261122` builds on the already-published Evening commit `9c76fc2be8863f2e06efb203af00741733f660fc`. Its patch contains only target naming, inventory normalization, the minimum additive display safeguards, tests and these handoff documents. Later Lane B commits are not included. Acceptance statuses below describe the saved handoff generation, not an audit of later receiving-side changes.

The isolated branch passed 199 tests and 9 subtests, plus JavaScript target-label, display-noninterference and syntax checks. Its report is `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_PUSH_TESTS_20261122.xml`. Replay paths below are references to local evidence; no replay files, receipts, databases or normalized quote data are included in the commit. Publication of this branch is not production activation.

## Latest Codex target and inventory fixes

M1 and M4 are resolved on the Codex side and tested with saved data. The final regression suite passed **199 tests and 9 subtests**; display labels and noninterference checks also pass. Claude still owns M2 pricing-basis adoption, M3 prefill propagation, and confirmation that his consumers use the new target and inventory contracts correctly. No Lane B code, data, historical replay, production activation or live Lab publication was changed.

Target naming is now versioned as `evening_target_roles_v1`:

- **First target (median arrival)** is `anticipated_level_q50`.
- **Full target (original Lab)** is `anticipated_level`, published as a reference without inventing a full-target arrival clock or option payoff.
- The legacy `target` alias and scenario codes remain compatible. Added `target_role`, `target_source_field` and `scenario_label` fields make their meaning explicit. `HALF_MOVE_IF_REACHED` means half the move from spot to the first target, not half the full target and not observed first option profit.
- Two historical nonpositive target sentinels remain in the legacy data for compatibility. Their canonical target price is null with state `UNASSESSED_MISSING_OR_INVALID`; new display does not present them as valid zero-dollar targets.

All 2,716 rows and 31,976 existing scenario cells retain their previous numerical values, verdicts, ranks and contracts. First and full targets differ on 777 rows; for NXT the exact references are 111.6176 and 137.471 respectively. No new target or valuation was selected.

The normalized inventory uses `contract_comparison_inventory_v1`. Its full saved-data round trip verified all 594,981 original observations exactly: 92,270 zero-IV values become canonical null with a reason, while all 174,238 zero bids remain zero. The 840 positive-bid/zero-IV observations remain IV-unavailable. Every quote retains its `raw_observation`; missing delta, midpoint, spread and historical gate results are not invented. A null `gate_failed` with `gate_evidence_state=NOT_RECORDED_IN_SAVED_SCOPE` does not mean accepted.

Latest artifacts:

```text
Completion receipt:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_20261122\M1_M4_COMPLETION_RECEIPT.json

Target and inventory contract addendum:
C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\Enhancements\EVENING_TARGET_INVENTORY_CONTRACT_20261122.json

Normalized comparison inventory:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_20261122\contract_comparison_inventory_20261120.jsonl.gz

Inventory source and output hashes:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_20261122\contract_comparison_inventory_20261120.jsonl.gz.receipt.json

Independent full inventory round trip:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_20261122\INVENTORY_ROUNDTRIP_VERIFIED.json

Target naming parity receipt:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_20261122\TARGET_NAMING_RECEIPT.json

Final regression report:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_FINAL_20261122.xml
```

The normalized inventory is gzip-compressed JSONL: read it with `gzip.open(path, 'rt', encoding='utf-8')` and parse one JSON record per line. Do not pass its compressed bytes directly to a plain JSONL reader. This is a new comparison view, not a replacement of the raw archive or a reconstructed original tested ladder. The addendum supersedes only target naming and inventory schema in the earlier field contract.

## Current position

Codex's saved-data compatibility checks pass for the remaining Evening fixes applied over the isolated production baseline. Verdicts, ranking, contracts and candidate coverage are unchanged on the tested run. This note hands over the pinned replay and receiving-side checks; it does not approve a new Lane B population rule or activate the remaining pipeline changes.

Claude's existing result, `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\Enhancements\EVENING_FIX_LANEB_RECEIVER_RESULT_20261122.md`, already reports population, order, identity and manual-selection PASS on the earlier replay. It also reports M1 to M4 below. Those results remain valid for that earlier revision; they are not a completed receiving-side test of the new compatibility replay.

The book retains opportunities. Supplementary assessment routes must not become automatic exclusions. In particular, the three `EVENING_QUALIFIED` labels in the earlier replay are not a count of viable trades, triage winners or the candidates Lane B may consider. All 346 ready Lane-A candidates remain present.

## Compatibility results

Run: `20261121_222919`. Saved market session: 20 November 2026. Original published revision: `925c8bc5ae9a41e99eeacb3b4c79d8b8`.

| Check | Baseline | Candidate | Result |
|---|---:|---:|---|
| Materializer output from the same saved execution CSV | 2,716 | 2,716 | No candidate loss or protected-field changes |
| Published indexed cards and API population | 2,716 | 2,716 | Same identities and ordering |
| Ready Lane-A population | 346 | 346 | All retained |
| Existing receiver-rule population | 2,577 | 2,577 | Same identities and ordering |
| Published MANUAL_REVIEW | 2,577 | 2,577 | Unchanged |
| Published CONTRACT_REPAIR | 138 | 138 | Unchanged |
| Published BLOCKED | 1 | 1 | Unchanged |

Zero differences across the 36 protected fields and their ordered records. These include verdict/action, rank and rank basis, thesis/candidate identities, exact contracts, direction, hold, invalidation, saved quote inputs and existing anticipated-value fields. Card order, paginated API order and the simulated receiver order all match. The same invariants pass after the saved profit-clock packet and frozen Evening packet are attached.

The simulated receiver rule is `GO_LIMIT` or `MANUAL_REVIEW`, ordered with `GO_LIMIT` first and then saved `lab_rank`. It does not execute Claude's receiving code. Intermediate materializer totals precede source hydration and must not be substituted for the final published totals above.

Ordered publication protected-record SHA256, identical before and after:

```text
ec63ae55e79f7ad12c6a46f1f6977c6ce0fd6e3f39a7e8ed7a5ca0f69ae9b443
```

Regression result: **174 tests and 9 subtests passed; zero failures or errors**. Selector, context-parser, value-selection and Lab-resolution function ASTs are unchanged. Contract value selection remains `SHADOW`; canonical ranking, orchestration and Morning source text are unchanged. The report distinguishes a checkout-only Morning line-ending difference and the absence of the Lane B trigger configuration in both isolated trees from actual policy changes.

Historical source manifest, index, run metadata and governed-constants hashes remain unchanged. No providers, pipeline run, live database writes, Lane B execution or further production promotion occurred during these checks.

## Exact replay paths

Use the new compatibility replay for confirmation against the integrated candidate. Pin its revision; do not read the live Lab or silently substitute another run.

```text
Run ID:
20261121_222919

Latest target naming revision:
328d685fb8464ade9ddb530550183cb6

Runs directory:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_20261122\runs

Run directory:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_20261122\runs\20261121_222919

Publication manifest:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_20261122\runs\20261121_222919\intelligence_lab\review_projection\manifest.json

Publication index:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_M1_M4_20261122\runs\20261121_222919\intelligence_lab\review_projection\review-328d685fb8464ade9ddb530550183cb6.sqlite

Earlier compatibility report and code fingerprints:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_COMPATIBILITY_20261122\COMPATIBILITY_REPORT.json

Earlier compatibility regression report:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_COMPAT_REGRESSION_20261122.xml
```

The comparison results are stored under `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_COMPATIBILITY_20261122` in `baseline_materializer\result.json`, `candidate_materializer\result.json`, `baseline_publication\result.json`, `candidate_publication\result.json` and `candidate_full_handoff\result.json`.

The new replay contains the indexed review, saved context, clock source/packet and frozen assessment packet. It is not a cloned complete pipeline run directory. Use revision-pinned review readers, not a fallback that expects every upstream artifact or republishes the replay.

Retain these earlier artifacts for the receiving tests:

```text
Earlier full replay runs directory:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_HANDOFF_REPLAY_20261122_FINAL\runs

Earlier revision:
9600f199d4a7492d9fc5e12fa8f882a8

Frozen six-entry manual-selection sample:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_HANDOFF_REPLAY_20261122_FINAL\manual_selection_receiver_sample.json

Earlier raw both-side inventory preserved for audit:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\EVENING_HANDOFF_REPLAY_20261122_FINAL\runs\20261121_222919\intelligence_lab\available_contracts_both_sides_20261121_222919.jsonl

Field contract:
C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\production-phantom-recovery-20261122\Enhancements\EVENING_HANDOFF_CONTRACT_20261122.json
```

The frozen sample deliberately remains bound to the earlier revision. Do not rewrite it to the new revision to make a comparison pass. Comparing it with a newer publication may correctly flag a changed revision; do not force it to CURRENT. It contains BILL, ORA, GCT, ADM, ATEN and BL; exact identities are listed in the compatibility report.

## Tested code and release boundary

- Production baseline: `d1b3221373fc833d0ac1f33d3086f965ed98f02d`.
- Remaining Evening patch: `9c76fc2be8863f2e06efb203af00741733f660fc`.
- Integrated test tree: `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\evening-compatibility-candidate-20261122`.
- The test tree is the production baseline plus the remaining Evening patch, not a newly activated release. The report records SHA256 fingerprints for the tested implementations. Do not treat its baseline HEAD alone as the identity of the added working-tree patch.
- The existing display-only promotion remains separate. No selector activation, expiry-policy change, new entry permission or Phantom promotion is authorized by this note.

## Existing receiver findings to settle

| Finding from Claude | Required disposition before consuming the new fields |
|---|---|
| M1: two levels are called target | Codex resolved the naming with explicit first-target and full-target roles, source fields and scenario labels. Claude must map these fields into his own outputs, without calling the median target observed first option profit or repricing a different level under the same name. |
| M2: pricing conventions differ | Saved preparation should consume the published scenarios. Any live repricing must use the shared pricer and the same clocks/cost basis, not a second approximation. |
| M3: prefills omit the assessment | Claude owns propagation into triage and selection prefills. Carry the new fields without changing the existing population or ranking. |
| M4: inventory shape and zero IV differ from the contract | Codex resolved this with the versioned normalized inventory and a complete raw-observation round trip. Claude must use its canonical fields and state/reason fields, decode gzip JSONL, and keep the raw archive intact. IV zero is unavailable; bid zero remains an observed zero. Missing historical gates are unknown, not accepted. |

The shared scalar pricing entry point is `domain.option_valuation.option_value`, in `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\evening-compatibility-candidate-20261122\domain\option_valuation.py`. It returns model value per share and the model name. American batch valuation uses `american_crr_values`; execution costs are applied separately through `entry_cost_usd_per_share` and `exit_proceeds_usd_per_share`. A model value alone is not net profit. Passing `style="AMERICAN"` explicitly avoids an implicit model choice. Source equality is recorded in the unchanged-source comparison; inspect the actual API before integrating it into Lane B.

Required comparison basis: actual XNYS checkpoint dates, actual calendar time remaining to expiry divided by 365, ask entry, measured exit spread and fees applied once, and relative IV stresses of 0.8 times and 1.25 times the saved IV. The earlier 1.4-calendar-days-per-session and fixed-10-IV-point shortcuts are not equivalent. No live repricing or broker connection is requested for this acceptance.

## Claude acceptance checklist

Write receiving-test outputs to a new isolated directory. Keep both replay inputs read-only and verify their manifest hashes before and after.

1. **Population and order.** Run the actual receiving handoff against the new pinned replay with the existing verdict/rank rule. Expect the same 2,577 eligible records, with zero unexpected drops, additions, reorders or substitutions. Confirm all 346 ready Lane-A candidates remain. Do not filter on the supplementary route.
2. **Identity and prefills.** Check run, revision, thesis/candidate IDs, exact OCC, reference session and quote timestamp through handoff, triage and selection prefill. Distinguish an absent Morning transition from a defect in the Evening opportunity.
3. **Economics.** Consume the resolved M1 target roles and complete M2 pricing-basis adoption, then compare the same contract, underlying level, exit date, IV and costs against each published case before display rounding. Report every field or formula discrepancy; do not make unequal scenarios agree by relabeling them.
4. **Profit clocks.** Keep empirical +20%/+30% quantiles separate from assumed-path crossings. Preserve evidence counts, failures, censored and unassessed cases. Missing n is not zero or an automatic veto. It is not a calibrated success probability or permission for Bayesian promotion.
5. **Manual selection.** Receive the six-entry frozen sample without rebinding its revision. Preserve selection IDs, exact contracts, saved order, notes, evidence families and verdicts. Reconfirm same-ticker/different-contract/revision identity handling with the receiving-side tests.
6. **Both-side inventory.** Validate the new M4 normalized schema and gzip transport before adoption. Preserve scope, missingness and truncation. The separate saved inventory is not the original tested ladder, an opposing thesis, a new selected contract or unrestricted-chain coverage.
7. **Frozen carry.** Confirm that a new Morning quote does not overwrite the frozen Evening assessment. The test has 2,150 exact-identity carries and 566 explicit unmatched/ambiguous cases. Keep all rows; never substitute by ticker alone.
8. **Return the acceptance result.** Provide PASS or a machine-readable mismatch list containing test ID, run/revision, row/thesis/contract identity, field, expected, actual and disposition. Keep population rules, selection, expiry policy and activation unchanged while resolving mismatches. ACK decides promotion after the applicable receiver findings are settled.

Historical clock identity matches are 2,011, with 705 unassessed identities. Historical quantiles exist on 41 rows for +20% and 29 for +30%. These describe available evidence, not the size of the opportunity book. Preserve the original evidence cutoff and failure/unassessed denominators.

## Limits of the signoff

This is compatibility evidence from one production-sized saved run and regression fixtures, not a profitability test or a guarantee for all future sessions. The complete Options Intelligence stage and nightly pipeline were not rerun. The corrected stop/forecast inputs have regression coverage; valuation of every original candidate chain and nightly runtime remain outside this replay. Offline elapsed times are not a production ETA benchmark.

No Lane B implementation or existing Claude result was changed to create this handoff. No providers, pipeline execution, data edits or release activation are requested by it.
