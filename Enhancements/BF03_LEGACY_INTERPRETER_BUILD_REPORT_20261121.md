# BF03 legacy Interpreter decommission build report

21 November 2026. **Implemented and tested locally; uncommitted.** User explicitly authorised “Implement BF-03 now”, resolving the earlier no-build hold for this slice. Started from `c8631c471b33afb81148e33b2f61d27cf02f0cca`. No commits, process/task changes, live pipeline, capture or model/provider calls were performed.

## Result and preserved behaviour

- K9 warning-only code eligibility is selectively integrated. Dirty/unavailable-code production Evenings continue with explicit exclusion reasons; launch identity is carried to pinning, dispatch uses the real code fact, planning is provisional and provider assessment final. Immutable plan intent is preserved. Current code receipts and C5/C6/C8 advisory-failure behaviour remain.
- Removed five legacy auto-sync hooks and the finalizer's legacy copy/import fallback. Both Morning entries still use the shared finalizer and canonical hashes, row/authority reconciliation, MSI independent reconciliation and post-Lab score integrity. Required-file or changed-hash failures still fail. Deprecated callable names/flags cannot re-enable copying.
- Summary explicitly records `interpreter_sync_status=RETIRED`, an empty legacy copy list, canonical artifact hashes and canonical handoff verification. It does not claim a retired copy succeeded.
- Lab no longer mounts Desk/WAR or constructs their providers. `/api/interpreter/*` GET/POST routes return HTTP 410 RETIRED without generation or filesystem writes. Retired action buttons, selection state and card callbacks are removed; current cards and historical evidence fields remain.
- Canonical macro and News Terminal stop publishing the MA_Inputs destination; the retained data/macro projection and Dropbox/run-bound authorities remain. Alignment still rejects stale active projections.
- Five batch/PowerShell wrappers stop with a retirement notice. All 23 Python entry points stop before imports/provider setup/copy/capture work. Archived library code and historical artifacts remain; this does not assert every importable historical function is removed.
- K10 Evening snapshot writer/call/path are unchanged. Its data-only library import is the explicit retirement exception. No automatic retention/deletion or latest-two policy was implemented. Shared interpreter-named handoff/macro contracts remain because current Lab/Morning readers use them.
- No agent build, Lane B changes, volatility/direction/selection/ranking/sizing change, new outcome writer, data migration or archive deletion is included.

## Verification

**192 passed, 1 skipped, plus 3 subtests across 19 focused suites.** Results are consolidated in `bf03_final_verification_20261121.json`; individual logs are identified there. Each suite ran in its own pinned-venv process with an isolated workspace temporary root. This is focused verification of the current shared working tree, not a whole-estate green-suite claim.

The new retirement suite has 41 cases, including every guarded Python launcher, retired API behaviour, no macro input recreation, missing/tampered canonical evidence, unchanged snapshot wiring, browser callback closure, and execution of the actual EIL enrichment/publication block on temporary DataFrames. The warning-only provenance suite has 23 cases. Existing Morning finalizer, MSI bundle, macro alignment/boundary, Lab review/timing, advisory failure, canonical manifest, current card, test isolation, snapshot, macro handoff, lifecycle, dynamic dispatch and EIL authority/no-quote suites pass.

An overbroad initial edit removed EIL's enclosing publication block. Diff review caught it before completion; only the two direct sync try blocks are now removed. Added canonical EIL-to-Morning publication regression passes. A syntax-tree comparison independently proves every non-sync statement in candidate production, EIL and the legacy Morning writer is unchanged (`bf03_producer_invariance_20261121.json`). All changed Python sources parsed, modified JavaScript and the inline Lab script parsed, and scoped source diff whitespace checks passed. The retained snapshot file has no diff from HEAD.

Two old expectations were deliberately adapted: stale-macro testing now corrupts the retained projection, and current cards no longer promise Interpreter action buttons. Their integrity/content checks remain. Initial retirement tests were red before the disconnections; extended launcher/card cases were red before entry-point closure.

## Runtime evidence and activation

An isolated four-artifact, 8,388,612-byte fixture was compared in five warm-cache pairs using the original copy/verification function against current canonical verification. Median time: **0.417 s original / 0.085 s current**; all hashes identical. Original: 20 copies over five pairs; current: zero. Logical per-pair file I/O falls from three reads plus one write per artifact to one read, eliminating duplicate writes. Detailed repetitions are in `bf03_isolated_handoff_measurement_20261121.json`.

This measures the removed component on local temporary files, not full Evening/Morning savings. Source scanning, hardware/cache conditions and other stages affect total runtime. The preserved snapshot's gzip/hash cost remains. Existing 4.48 GB retained input footprint is not per-run copying and was not deleted.

Visible process check found no matching Lab or legacy launcher running. No process was started/stopped. New CLI/pipeline invocations and next Lab start read this source; an already-loaded process on another session/machine needs the normal restart/reload. Monday 23 November's approved Evening/Morning session remains the forward acceptance target: confirm completion, canonical rows/permissions/hashes, saved review publication, snapshot, no legacy copy/dispatch and measured total/stage runtime. Do not mark forward validation done from these unit/component results.

## Review status

| Slice | Built | Committed | Wired | Tested | Validated | Authorised |
|---|---|---|---|---|---|---|
| K9 warning-only provenance prerequisite | YES | NO | YES, source entry points | 23 passed | OFFLINE ONLY | YES, K9 and explicit BF-03 approval |
| BF-03 canonical handoff and pipeline disconnection | YES | NO | YES, both Morning entries and producers | Focused suites pass | COMPONENT/OFFLINE; full session pending | YES |
| BF-03 Desk/WAR, UI, macro and launcher retirement | YES | NO | YES, source and 410 routes | 41 retirement cases plus existing regressions | OFFLINE; next-start/session pending | YES |
| K10 Evening snapshot | RETAINED | Existing baseline | UNCHANGED | Snapshot suite 5 passed; no source diff | Runtime recheck Monday | KEEP APPROVED |
| K10 retention deletion | NOT BUILT | NO | NO | NOT RUN | NOT VALIDATED | Separate small design required |

Claude Code stage review is still owed; this report is a review package, not a claim that independent review happened. BF-00/verifier/Options Intelligence edits appeared concurrently in other files and were left to their owners. Working-tree tests include current shared dependencies; do not stage the whole tree or attribute those other changes to BF-03. No commit is requested or performed here.

Rollback uses the prior coherent code/UI/config version while retaining historical and new canonical evidence. Do not restore only one Morning entry, rewrite outcomes or delete artifacts. Runtime retirement can be reviewed independently of future agents, model changes and retention cleanup.
