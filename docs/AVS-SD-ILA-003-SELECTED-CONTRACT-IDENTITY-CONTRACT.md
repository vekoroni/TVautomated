# AVS-SD-ILA-003 — `selected_contract_symbol` identity contract (fix design)

**Status:** approved by ACK 2026-09-23; implemented test-first 2026-09-24 (section 10), not committed, live acceptance on the next Morning run outstanding. No run output or trading state changed.  
**Root cause:** `AVS-ILA-EVENING-MORNING-SOURCE-MAPPING-20260923.md` section 4a (accepted handoff overlay rejected on every row).  
**Extends:** `AVS-SD-ILA-002-GOVERNED-EVENING-MORNING-READ-MODEL.md` (step 2a of the source mapping's implementation order).  
**Governing references:** specification v1.1 Invariant A (one owner per business fact), Invariant B (unknown means unknown), Invariant C (published aggregates are immutable); design rules R1, R2, R3, R5, R7 in `Enhancements/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md`; CLAUDE.md rule 4 (fix in place, test-first, one defect at a time).  
**Evidence run:** `20260922_223221` (1,550 book rows, 359 accepted handoff rows), cross-checked on `20260922_000106` and `20260920_203115`.

## 1. Business rule being restored

Every actionable candidate in the accepted Morning handoff must have its accepted evidence visible on its Lab row. The governed selected-contract identity is one business fact: it is published once, by its owner, and every downstream reader (handoff materializer, Lab merge, Morning finalizer, Interpreter Desk, browser) reads that published value rather than re-deriving it.

Today that fact is derived independently in three places (`contracts/interpreter_handoff_materializer.py::_canonical_contract`, `morning_handoff_finalizer.py::_contract_identity`, and implicitly by `domain/dynamic_options_projection.py::merge_all_opportunities` expecting it on the book row) and published in none. The merge is therefore correct to reject: the book row genuinely has no `selected_contract_symbol`. The defect is missing publication, not an over-strict check.

## 2. Decision: publish the fact in the book (Option A), do not relax the merge (Option B)

| | Option A — book publishes `selected_contract_symbol` | Option B — merge accepts the materializer's alias chain |
|---|---|---|
| Owner (R2, Invariant A) | One publisher (`_economics_identity`, which already publishes `selected_structure_id`, `selected_contract_symbols`, `selected_quote_snapshot_id`); materializer, finalizer and merge become readers | Keeps three derivations of the same fact; adds a fourth inside the merge |
| Typed absence (R1, Invariant B) | `NOT_SELECTED` / `MULTI_LEG` states published with the row | Absence stays implicit (empty string) |
| Vocabulary (R3) | The name already used by the handoff CSV identity columns, the evidence bundle top level, the authority map (`MORNING_GATE_SELECTED_CONTRACT`), the UI and the Interpreter Desk | Book keeps a different name from every consumer |
| Other consumers | Browser reference and Interpreter confluence `selected_contract_symbol or contract_symbol` start receiving the governed value | Still empty for UI and Interpreter |
| Change surface | Two additive fields, one publisher function, one status-reporting fix | Merge rule change plus a new alias resolver in the domain module |
| Reselection safety | Value comes from the governed `selected_contract_symbols` list, which `_economics_identity` already ranks above copied producer aliases | Alias order would be decided in the merge, a reader, not the owner |

**Choose A.** Option B is rejected because it multiplies owners and leaves the browser and Interpreter readers empty.

Evidence that A changes no existing behaviour on the sampled run: of 1,550 book rows, 1,368 have exactly one governed symbol in `selected_contract_symbols` and 182 have none; the single symbol equals `morning_selected_contract_symbol` and `contract_symbol` in every one of the 1,368 rows (0 conflicts). Replaying the merge with only this field filled overlays 359 of 359 with no other mismatch.

## 3. Contract change (additive to `lab_signal_book_v4`)

Two fields, added to `FINAL_BOOK_FIELDS` in `contracts/lab_control.py` immediately after `selected_contract_symbols`, and returned by `_economics_identity` (so both `opportunity_book_row` call sites and the finalizer republish path publish them through the existing `_enforce_economics_identity` provenance mechanism):

| Field | Type | Rule | Provenance label |
|---|---|---|---|
| `selected_contract_symbol` | OCC symbol, upper case, no `O:` prefix, no spaces; `""` when absent | `selected_contract_symbols[0]` when the governed list has exactly one element; otherwise `""`. Never derived from `contract_symbol`, `morning_selected_contract_symbol`, `live_*` or `recommended_contract` in this function | `economics_identity:selected_contract_symbols` |
| `selected_contract_identity_state` | enum | `SINGLE` (exactly one symbol), `NOT_SELECTED` (empty list), `MULTI_LEG` (more than one symbol) | `economics_identity:selected_contract_symbols` |

Expected population on the sampled run: `SINGLE` 1,368 (all `LONG_SINGLE`), `NOT_SELECTED` 182 (all already typed `contract_data_state=NOT_APPLICABLE_NO_SELECTED_CONTRACT`, actions BLOCK/CONTRACT_REPAIR/MANUAL_REVIEW), `MULTI_LEG` 0.

Schema version stays `lab_signal_book_v4`; the Lab reader already accepts additive v4 publication. No existing field changes meaning or value. `PROTECTED_AUTHORITY_FIELDS` already contains `selected_contract_symbol`, so the accepted handoff still cannot overwrite it.

## 4. Merge and reporting changes

- `merge_all_opportunities`: **no rule change.** Strict equality on the published fact is the required behaviour.
- `intelligence-lab/intelligence_lab.py::_governed_lab_book`: stop overwriting the merge's `status` with the manifest's `reconciliation_status`. Publish both: `status` = merge outcome (`PASS` / `PARTIAL`), `handoff_reconciliation_status` = manifest value.
- Run health: when `actionable_rows_rejected > 0`, add `LAB_HANDOFF_OVERLAY_REJECTED:<n>` to the run-health flags the header shows, and set `lab_data_notice` accordingly. A rejected overlay must be visible (R12, "fresh or flagged"), never silent.

## 5. Readers: what changes and what does not

| Reader | Today | After |
|---|---|---|
| `interpreter_handoff_materializer._canonical_contract` | derives from alias chain | first branch hits the published field; alias chain retained as fallback for books published before this release. No code change |
| `morning_handoff_finalizer._contract_identity` (uncommitted) | alias chain, `selected_contract_symbol` first | unchanged; now reads the published value |
| `merge_all_opportunities` | rejects every row | overlays every identity-matched row |
| Browser `index.html` (`selected_contract_symbol` reference, register row 787) | empty | populated; no UI change required |
| `pipeline_interpreter/confluence_evidence.py` contract link | falls back to `contract_symbol` | reads governed value. The separate `invalidation_spot` and `morning_thesis_result` name defects are **out of scope** here (follow-on slice 2b in the source mapping) |
| `contracts/interpreter_handoff.py` handoff-book vs bundle identity check | compares handoff CSV to bundle | unchanged |
| Frozen EOD snapshot (`interactive_snapshot.py`) | hash-bound package | packages already published are unaffected; new EOD books carry the fields |

## 6. Test-first sequence

All tests use synthetic rows and `tmp_path`; none read live `data/` or the network. Order is mandatory.

1. **Characterisation (pin, then retire).** `tests/test_ila_selected_contract_identity.py::test_characterise_book_publishes_no_singular_identity_so_handoff_overlay_is_rejected`: publish one `LONG_SINGLE` row with `write_final_opportunity_book`, materialise its handoff identity with the materializer's `_identity`, merge, assert `actionable_rows_rejected == 1` with reason `ACTIONABLE_IDENTITY_MISMATCH:selected_contract_symbol`. Green before the change. Deleted in the same commit as the fix, replaced by test 4.
2. **Business rule, red.** `test_published_single_contract_row_carries_governed_singular_identity`: the published row has `selected_contract_symbol == json.loads(selected_contract_symbols)[0]`, `selected_contract_identity_state == "SINGLE"`, and provenance `economics_identity:selected_contract_symbols`.
3. **Business rule, red.** `test_absent_and_multi_leg_contracts_publish_typed_state_not_blank`: empty list publishes `""` and `NOT_SELECTED`; two-symbol list publishes `""` and `MULTI_LEG`. A row whose copied `contract_symbol` differs from the governed list still publishes the governed list's symbol (reselection case: `previous_contract_symbol` set, `contract_repair_status=CONTRACT_REPAIR_REQUIRED`).
4. **Business rule, red.** `test_accepted_handoff_overlays_every_actionable_row_of_its_own_book`: publish a five-row book (three with contracts, one `NOT_SELECTED`, one reselected), materialise handoff rows for the three actionable ones, merge, assert overlaid 3, rejected 0, population 5, and that a `quote_timestamp_utc` supplied by the handoff appears on exactly those three rows.
5. **Coverage gate, red.** Add both fields to `REQUIRED_GOVERNED_FIELDS` in `tests/test_ila_release_coverage_gate.py` so the static and dynamic layers guard them.
6. **Reporting, red.** `test_lab_reports_merge_status_and_flags_rejected_overlay` using the Flask test client pattern in `tests/test_ila_event_projection_v1.py`: a book without the field plus an accepted handoff yields `lab_reconciliation.status == "PARTIAL"`, `handoff_reconciliation_status == "PASS"`, and the run-health flag; a book with the field yields `PASS` and no flag.
7. **Book-unchanged guard (R5).** `test_fix_adds_only_the_two_identity_fields`: publish the same synthetic rows before and after; every pre-existing field is byte-identical.
8. **Minimal change**, then run: the new file, `tests/test_ila_release_coverage_gate.py`, `tests/test_doi10_projection_integration.py`, `tests/test_ila_event_projection_v1.py`, `tests/test_interactive_desk_end_to_end.py`, `tests/test_morning_handoff_finalizer.py`, one file per process with `--basetemp=%TEMP%\avs_pt`.

## 7. Acceptance against reality

This is a read-model publication defect. It changes no thesis, direction, contract, score, rank or execution field, so the outcome scorer has no metric to move and is not the acceptance instrument. Acceptance is:

1. **Stored-run replay (read-only).** A script under `Enhancements/assessment/` replays `20260922_223221`, `20260922_000106` and `20260920_203115`: books re-published to a temporary directory from their source Morning CSVs must reconcile 359/359, 249/249 and 206/206, and every pre-existing field must equal the stored book. Output recorded in the release note.
2. **Next live Morning run.** `lab_reconciliation.actionable_rows_overlaid == actionable_handoff_count`, `actionable_rows_rejected == 0`, no run-health overlay flag, and the 17 allow-listed quote-change fields populated on every handoff member (measured list in source mapping section 4a).
3. **Browser.** MSI pane quote timestamp shows the exact Morning quote time for a handoff member (screenshot `162007` case), and the header shows no overlay warning.

## 8. Decisions requested from ACK

- **D1 — books already published without the field.** Recommend **no serve-time derivation** in the Lab for pre-fix books. A compatibility view would be a fourth derivation of the fact (contradicts R2) and would hide which runs were published under the defect. Stored runs are reconciled through the replay in section 7 and remain inspectable; live use resumes on the next Morning run after release. If ACK needs earlier stored runs to overlay in the browser before then, the alternative is a one-off, logged republish of the affected books through the finalizer path, not a Lab-side alias.
- **D2 — state field.** Recommend publishing `selected_contract_identity_state` rather than reusing `contract_data_state`, because `MULTI_LEG` is a distinct identity case that no existing state types. If ACK prefers fewer fields, `contract_data_state` covers `NOT_SELECTED` and only the multi-leg case is left untyped.

## 9. Scope boundaries

In scope: the two book fields, the publisher function, the Lab status reporting, the tests above, register rows 787 (`selected_contract_symbol`) and a new row for the state field, and the source mapping section 4a disposition line.

Out of scope, each its own slice: Interpreter confluence field names (`invalidation_price`, `validation_transition`); full-population Morning event materialisation into the book (ILA-002 step 2); the Lab payload size; Interpreter failure receipts not recording the validation rule.

Authority gates G1–G4 and specification section 24 do not apply: no logic gains or changes decision authority.

## 10. Implementation record (2026-09-24)

**Status:** implemented test-first as designed; not committed (ACK commits). Decisions D1 (no serve-time derivation for pre-fix books) and D2 (new state field) applied as recommended.

**Production changes (minimal, in place):**

| File | Change |
|---|---|
| `contracts/lab_control.py` | `FINAL_BOOK_FIELDS` gains `selected_contract_symbol`, `selected_contract_identity_state` after `selected_contract_symbols`; `_economics_identity` publishes both from the governed list; `_enforce_economics_identity` labels their provenance `economics_identity:selected_contract_symbols` |
| `intelligence-lab/intelligence_lab.py` | `_governed_lab_book` reports the merge's `status` and the manifest's value as `handoff_reconciliation_status`; `_load_run` adds `LAB_HANDOFF_OVERLAY_REJECTED:<n>` to `run_health.conflict_flags` and extends `lab_data_notice` when any row is rejected |
| `pipeline_interpreter/confluence_evidence.py` | thesis link reads `invalidation_price`; Morning link reads `validation_transition`, `validation_current_price`, `validation_event_id`, `validation_reason` |
| `pipeline_interpreter/interactive_desk.py` | `EVIDENCE_FIELDS` carries `invalidation_price`; `_morning_evidence` extracts the governed validation names; supportive Morning status is `THESIS_CONFIRMED` (retired `VALIDATED`, `DEVELOPED`, which no producer emits) |

Merge rule, materializer, browser and handoff validation unchanged, as designed.

**Tests (one file per process, `--basetemp` short):**

| Step | File | Result |
|---|---|---|
| 1 characterisation (green before change, retired with the fix) | `tests/test_ila_selected_contract_identity.py`, `tests/test_interactive_desk_end_to_end.py` | both green pre-fix, then replaced |
| 2 to 4, 6, 7 business rules | `tests/test_ila_selected_contract_identity.py` | 7 passed (red before the change) |
| 5 coverage gate | `tests/test_ila_release_coverage_gate.py` | 3 passed (2 red before the change) |
| slice 2b Interpreter names | `tests/test_interactive_desk_end_to_end.py` | 23 passed (7 red before the change; fixtures aligned to book column `invalidation_price`) |
| regression | `test_doi10_projection_integration` 14, `test_ila_event_projection_v1` 10, `test_morning_handoff_finalizer` 9, `test_interactive_desk_snapshot` 5, `test_pi_lab_interactive_contract` 12, `msi/test_flow` 19, `test_book_integrity_e3_e4_e5_e7` 31, `test_book_integrity_reselected_liquidity` 17, `test_contract_value_selection` 10, `test_evening_thesis_decision` 17, `test_big_bang_phase_6_7` 3, `test_avs_fix_001_w13` 7, `test_avs_fix_001_w15` 14, `test_ila_morning_state_separation` 5 | all passed |

Pre-existing failures unrelated to this change, left for their owners: `tests/test_openai_desk_provider.py` (3: tests call `report` without `evidence_refs`, which the uncommitted provider guard rejects), `tests/test_msi_interpreter_handoff.py` (1: looks for a page heading the uncommitted `index.html` edit removed), `tests/test_avs_fix_001_w35_opportunity_tier.py` (20: tier unit tests, module reads none of the new fields).

**Acceptance on reality (section 7), read-only replay `Enhancements/assessment/ila003_stored_run_replay.py`:**

| Run | Source rows | Republished | `selected_contract_symbol` populated | States | Handoff rows | Overlaid | Rejected |
|---|---|---|---|---|---|---|---|
| `20260922_223221` | 1,550 | 1,550 | 1,368 | SINGLE 1,368 · NOT_SELECTED 182 · MULTI_LEG 0 | 359 | **359** | 0 |
| `20260922_000106` | 1,543 | 1,543 | 1,370 | SINGLE 1,370 · NOT_SELECTED 173 · MULTI_LEG 0 | 249 | **249** | 0 |
| `20260920_203115` | 1,547 | 1,547 | 1,356 | SINGLE 1,356 · NOT_SELECTED 191 · MULTI_LEG 0 | 206 | **206** | 0 |

**A/B additivity on real data (`--ab`, run `20260922_223221`):** the same 1,550 Morning rows published with the fix and with the pre-fix publisher emulated in-process. Fields differing besides the two identity fields: **none** (0 of 1,550 rows on every other field). Provenance gains exactly the two labels `selected_contract_symbol`, `selected_contract_identity_state` on all 1,550 rows. Fields present only after the fix: exactly the two identity fields.

The comparison against the *stored* book file is not a valid book-unchanged proof: the replay publishes into a temporary directory without the finalizer's side inputs (execution, macro advisory, GARCH, validation events), so advisory and execution fields differ for that reason alone. The A/B replay on identical inputs is the guard used instead, together with test 7 on synthetic rows.

**Live acceptance still open:** the next Morning run must show `actionable_rows_overlaid == actionable_handoff_count`, no `LAB_HANDOFF_OVERLAY_REJECTED` flag, the 17 quote-change fields populated on every handoff member, and the MSI pane quote timestamp for a handoff member. Stored books published before the fix still lack the field and still overlay nothing (D1).

**Lab restart check (2026-09-24, ACK request).** The port-5002 server was restarted on the fixed code (provider ready). Serving the stored run `20260922_223221` it now reports `lab_reconciliation.status=PARTIAL`, `handoff_reconciliation_status=PASS`, overlaid 0, rejected 359, `run_health.conflict_flags` contains `LAB_HANDOFF_OVERLAY_REJECTED:359`, and the data notice names the rejection. This is the designed D1 behaviour for a pre-fix book: the defect is now visible instead of masked, and the overlay will apply from the first book published after the fix.

**Republish of the stored book (2026-09-24, ACK request; D1 alternative executed).** `Enhancements/assessment/ila003_republish_book.py` reproduced the finalizer's offline replay for the book only: Morning CSV -> Execution Gate in memory (artefacts to a temp folder; decisions cross-checked equal to the stored `trades/` output on final_action, permission, direction, contract identity, OLM disposition and capital permission) -> stored macro packet `MACRO:188aae25943d5e5d480a2ca0` -> persisted validation events (1,550 attached, 0 issues) -> `write_final_opportunity_book`. A preview into a mirrored runs folder showed every published field identical to the stored book except the two identity fields, the validation-event fields, `morning_execution_mode` (now published) and provenance. The three book files were backed up to `backups/ila003_republish_20260922_223221_prechange_20260923_234623/` (with `republish_record.json` holding before/after hashes) and republished at 23:54 UTC. Disclosed evidence change: `source_payload_json` now records the replay input row (a superset of the original snapshot, gate timestamp at replay time, and for the 359 actionable rows a leg object without the live Morning quote that the original in-process run had fetched). Those quotes remain in the published quote columns, the handoff bundles and the backup. No trades/, manifest, handoff or summary artefact was rewritten.

**Lab after republish (served payload):** `lab_reconciliation.status=PASS`, `handoff_reconciliation_status=PASS`, overlaid 359, rejected 0, no conflict flag; `selected_contract_symbol` on 1,368 rows (SINGLE 1,368, NOT_SELECTED 182); overlay APPLIED on 359 rows with `quote_timestamp_utc`, `comparison_status` and `contract_mid_change_pct` populated on all of them; `morning_execution_mode` and `validation_event_id` on all 1,550 rows. `quote_age_seconds` and `current_quote_snapshot_id` are overlaid but dropped by the slim browser projection (`_compact_lab_signal` allow-list), a separate presentation item.
